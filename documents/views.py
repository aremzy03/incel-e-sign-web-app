"""
Views for the documents app.

This module contains API views for document upload and management
functionality in the e-signature workflow.
"""

import logging
import os
import uuid
from urllib.parse import unquote, urlparse

import boto3
import requests
from django.conf import settings
from django.db import models
from django.http import FileResponse, Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import DestroyAPIView, ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.query_filters import parse_search_query_param, parse_status_query_param
from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer, MergeDocumentsSerializer
from .services.pdf_files import download_pdf_to_temp, temp_pdf_file, upload_staging_pdf
from signatures.utils.pdf_signing import get_media_absolute_path_from_url
from envelopes.models import Envelope, EnvelopeDocument
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

_FILENAME_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_ .()[]")


def _sanitize_filename_component(value: str, *, fallback: str = "Document", max_len: int = 120) -> str:
    """
    Produce a filesystem-safe, human-friendly filename component.

    - strips control characters and reserved path characters
    - collapses whitespace
    - limits length to avoid OS/path edge cases
    """
    if not value:
        return fallback

    cleaned: list[str] = []
    last_was_space = False
    for ch in str(value):
        if ch in ("\n", "\r", "\t"):
            ch = " "
        if ch not in _FILENAME_SAFE_CHARS:
            ch = " "

        if ch == " ":
            if last_was_space:
                continue
            last_was_space = True
        else:
            last_was_space = False

        cleaned.append(ch)

    result = "".join(cleaned).strip(" .")
    if not result:
        result = fallback

    if len(result) > max_len:
        result = result[:max_len].rstrip(" .")
        if not result:
            result = fallback

    return result


def _default_merged_filename(first_doc_name: str, total_docs: int) -> str:
    """
    Option A naming: "Merged - <first_doc_base> (+<n-1>).pdf"
    """
    base, _ext = os.path.splitext(first_doc_name or "")
    base = _sanitize_filename_component(base, fallback="Document", max_len=80)
    suffix = f" (+{total_docs - 1})" if total_docs > 1 else ""
    return f"Merged - {base}{suffix}.pdf"


def _is_placeholder_merge_name(value: str) -> bool:
    """
    Detect common client-side placeholder names (so we can still apply Option A).
    """
    normalized = (value or "").strip().lower()
    return normalized in {"merged", "merged.pdf", "merged document", "merged document.pdf"}


def get_accessible_document_for_user(user, pk):
    """
    Resolve a Document the given user is allowed to access or raise Http404.
    """
    # Direct ownership
    document = Document.objects.filter(id=pk, owner=user).first()
    if document:
        return document

    # Envelope creator access
    has_creator_access = EnvelopeDocument.objects.filter(
        document__id=pk,
        envelope__creator=user
    ).exists()
    if has_creator_access:
        return get_object_or_404(Document, id=pk)

    # Signer access: scan envelopes containing this document
    user_id_str = str(user.id)
    for env_doc in EnvelopeDocument.objects.filter(document__id=pk).select_related('envelope'):
        for signer_entry in env_doc.envelope.signing_order:
            # Must match DocumentDetailView: signer_id may be UUID from JSONField/code paths
            if str(signer_entry.get('signer_id')) == user_id_str:
                return get_object_or_404(Document, id=pk)

    raise Http404


class DocumentUploadView(APIView):
    """
    API view for uploading PDF documents.
    
    Handles file upload, validation, storage, and Document model creation.
    Requires authentication.
    """
    
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        """
        Handle document upload.
        
        Args:
            request: HTTP request containing file data
            
        Returns:
            Response: JSON response with document details or error
        """
        # Log request data for debugging (only in DEBUG mode)
        if settings.DEBUG:
            logger.debug(f"Document upload request - Method: {request.method}, User: {request.user.id}")
            if 'file' in request.FILES:
                file = request.FILES['file']
                logger.debug(f"File details - Name: {file.name}, Size: {file.size}, Type: {file.content_type}")
        
        # Create serializer with request data (includes files when multipart/form-data)
        serializer = DocumentUploadSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Save the document
                document = serializer.save(owner=request.user)
                
                logger.info(f"Document uploaded successfully - ID: {document.id}, User: {request.user.id}, File: {document.file_name}")
                
                # Log the document upload action
                from audit.utils import log_action
                log_action(
                    request.user, 
                    "UPLOAD_DOC", 
                    document, 
                    f"User {request.user.full_name or request.user.username} uploaded document '{document.file_name}'.", 
                    request=request
                )
                
                # Return document details
                document_serializer = DocumentSerializer(document)
                return Response(
                    {
                        'status': 'success',
                        'message': 'Document uploaded successfully',
                        'data': document_serializer.data
                    },
                    status=status.HTTP_201_CREATED
                )
                
            except Exception as e:
                logger.error(f"Error uploading document - User: {request.user.id}, Error: {str(e)}", exc_info=True)
                error_message = 'Error uploading document'
                if settings.DEBUG:
                    error_message = f'Error uploading document: {str(e)}'
                return Response(
                    {
                        'status': 'error',
                        'message': error_message
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Log serializer errors
        logger.warning(f"Document upload validation failed - User: {request.user.id}, Errors: {serializer.errors}")
        
        response_data = {
            'status': 'error',
            'message': 'Invalid file data',
            'errors': serializer.errors,
        }
        
        # Only include debug info in development
        if settings.DEBUG:
            response_data['debug_info'] = {
                'content_type': request.content_type,
                'has_files': bool(request.FILES),
                'files_keys': list(request.FILES.keys()) if request.FILES else [],
                'data_keys': list(request.data.keys()) if hasattr(request, 'data') else []
            }
        
        return Response(
            response_data,
            status=status.HTTP_400_BAD_REQUEST
        )


class DocumentListView(ListAPIView):
    """
    API view for listing user's documents.
    
    Returns only documents owned by the authenticated user.
    Optional query params: ``status`` (draft, sent, completed, rejected),
    ``search`` (case-insensitive match on file_name).
    Requires authentication.
    """
    
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Return documents owned by the authenticated user.
        
        Returns:
            QuerySet: Documents owned by the current user
        """
        queryset = Document.objects.filter(owner=self.request.user).select_related('owner')

        status_value, status_error = parse_status_query_param(
            self.request,
            Document.STATUS_CHOICES,
        )
        if status_error:
            raise ValidationError({'status': status_error})
        if status_value:
            queryset = queryset.filter(status=status_value)

        search_term = parse_search_query_param(self.request)
        if search_term:
            queryset = queryset.filter(file_name__icontains=search_term)

        return queryset.order_by('-created_at')


class DocumentDetailView(RetrieveAPIView):
    """
    API view for retrieving a single document.
    
    Users can only access their own documents.
    Returns 404 if document doesn't exist or user is not the owner.
    Requires authentication.
    """
    
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        """
        Resolve a single document the user may access (owner, envelope creator, or signer).

        Uses get_accessible_document_for_user so we only inspect envelopes that contain
        this document instead of scanning every envelope in the database.
        """
        document_id = self.kwargs.get('pk')
        return get_accessible_document_for_user(self.request.user, document_id)


class DocumentDeleteView(DestroyAPIView):
    """
    API view for deleting a document.
    
    Users can only delete their own documents.
    Returns 403 Forbidden if user is not the owner.
    Requires authentication.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Return documents owned by the authenticated user.
        
        Returns:
            QuerySet: Documents owned by the current user
        """
        return Document.objects.filter(owner=self.request.user)
    
    def get_object(self):
        """
        Get the document object, ensuring user can only delete their own documents.
        
        Returns:
            Document: The requested document
            
        Raises:
            Http404: If document doesn't exist
            PermissionDenied: If user is not the owner (handled by get_queryset)
        """
        queryset = self.get_queryset()
        document_id = self.kwargs.get('pk')
        return get_object_or_404(queryset, id=document_id)
    
    def destroy(self, request, *args, **kwargs):
        """
        Delete the document and return appropriate response.
        
        Args:
            request: HTTP request
            *args: Additional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            Response: 204 No Content on successful deletion
        """
        try:
            document = self.get_object()
            
            # Log the document deletion action
            from audit.utils import log_action
            log_action(
                request.user, 
                "DELETE_DOC", 
                document, 
                f"User {request.user.full_name or request.user.username} deleted document '{document.file_name}'.", 
                request=request
            )
            
            document.delete()
            return Response(
                {
                    'status': 'success',
                    'message': 'Document deleted successfully'
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            # Let 404 errors pass through (handled by get_object_or_404)
            from django.http import Http404
            if isinstance(e, Http404):
                raise
            return Response(
                {
                    'status': 'error',
                    'message': f'Error deleting document: {str(e)}'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DocumentDownloadView(APIView):
    """
    API view for downloading documents.
    
    Allows users to download their own documents as file responses.
    Requires authentication.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """
        Download a document file as an attachment.
        """
        try:
            user = request.user
            document = get_accessible_document_for_user(user, pk)
            
            # Get the full file path - prioritize signed version if available
            # Use the same logic as signing: signed_file_url takes precedence
            source_url = document.signed_file_url or document.file_url
            
            if source_url.startswith('/media/'):
                # For local files, construct the full path
                # Decode URL-encoded filename (e.g., %20 -> space)
                file_path = os.path.join(settings.MEDIA_ROOT, unquote(source_url[7:]))  # Remove '/media/' prefix and decode URL
            elif source_url.startswith('http'):
                # For S3 or other remote storage, proxy bytes through the backend.
                # This avoids CORS issues and prevents brittle browser-side signed URL handling.
                try:
                    parsed = urlparse(source_url)
                    encoded_path = parsed.path.lstrip('/')
                    decoded_path = unquote(encoded_path)

                    # Support both S3 URL styles:
                    # - virtual-hosted: https://<bucket>.s3.amazonaws.com/<key>
                    # - path-style:     https://s3.amazonaws.com/<bucket>/<key>
                    key = decoded_path
                    if key:
                        first, rest = (key.split('/', 1) + [""])[:2]
                        if first == settings.AWS_STORAGE_BUCKET_NAME and rest:
                            key = rest

                    if not key:
                        return Response(
                            {
                                'status': 'error',
                                'message': 'Unable to resolve remote storage key for document'
                            },
                            status=status.HTTP_502_BAD_GATEWAY
                        )

                    s3_client = boto3.client(
                        's3',
                        region_name=settings.AWS_S3_REGION_NAME,
                        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    )

                    obj = s3_client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)
                except Exception as e:
                    # Best-effort mapping of not-found vs other upstream errors.
                    code = None
                    try:
                        code = getattr(getattr(e, "response", None), "get", lambda *_: None)("Error", {}).get("Code")  # type: ignore[union-attr]
                    except Exception:
                        try:
                            code = getattr(e, "response", {}).get("Error", {}).get("Code")
                        except Exception:
                            code = None
                    if code in ("NoSuchKey", "404"):
                        return Response(
                            {
                                'status': 'error',
                                'message': 'Document not available from remote storage'
                            },
                            status=status.HTTP_404_NOT_FOUND
                        )
                    return Response(
                        {
                            'status': 'error',
                            'message': f'Unable to fetch document from remote storage: {e}'
                        },
                        status=status.HTTP_502_BAD_GATEWAY
                    )

                body = obj['Body']

                def iter_stream():
                    for chunk in body.iter_chunks(chunk_size=8192):
                        if chunk:
                            yield chunk

                content_type = obj.get('ContentType') or 'application/pdf'
                content_length = obj.get('ContentLength')

                response = StreamingHttpResponse(iter_stream(), content_type=content_type)
                if content_length is not None:
                    response['Content-Length'] = str(content_length)
                response['Content-Disposition'] = f'attachment; filename="{document.file_name}"'

                # Log the download action
                from audit.utils import log_action
                log_action(
                    request.user,
                    "DOWNLOAD_DOC",
                    document,
                    f"User {request.user.full_name or request.user.username} downloaded document '{document.file_name}'.",
                    request=request
                )

                return response
            else:
                # For relative paths, try to construct the full path
                if source_url.startswith('documents/'):
                    file_path = os.path.join(settings.MEDIA_ROOT, source_url)
                else:
                    file_path = os.path.join(settings.MEDIA_ROOT, source_url)
            
            # Check if file exists
            if not os.path.exists(file_path):
                # Try alternative path construction for backwards compatibility
                alt_path = os.path.join(settings.MEDIA_ROOT, 'documents', document.file_name)
                if os.path.exists(alt_path):
                    file_path = alt_path
                else:
                    return Response(
                        {
                            'status': 'error',
                            'message': 'Document file not found on server'
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Create file response, forcing the download name to use the stored file_name
            response = FileResponse(
                open(file_path, 'rb'),
                content_type='application/pdf',
                as_attachment=True,
            )
            # Explicitly set Content-Disposition so browsers use document.file_name
            response["Content-Disposition"] = f'attachment; filename="{document.file_name}"'
            
            # Log the download action
            from audit.utils import log_action
            log_action(
                request.user, 
                "DOWNLOAD_DOC", 
                document, 
                f"User {request.user.full_name or request.user.username} downloaded document '{document.file_name}'.", 
                request=request
            )
            
            return response
            
        except Document.DoesNotExist:
            return Response(
                {
                    'status': 'error',
                    'message': 'Document not found or access denied'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except FileNotFoundError:
            return Response(
                {
                    'status': 'error',
                    'message': 'Document file not found on server'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    'status': 'error',
                    'message': f'Error downloading document: {str(e)}'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DocumentPreviewView(APIView):
    """
    API view for inline preview of documents.
    
    This endpoint always proxies the file bytes through the backend
    (including for S3/remote URLs) to avoid CORS issues on the client.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """
        Stream a document for inline preview (no attachment disposition).
        """
        try:
            document = get_accessible_document_for_user(request.user, pk)

            source_url = document.signed_file_url or document.file_url

            # Remote storage (e.g. S3) – stream via boto3 using bucket/key instead of HTTP GET on a signed URL
            if source_url.startswith('http'):
                try:
                    parsed = urlparse(source_url)
                    encoded_key = parsed.path.lstrip('/')
                    key = unquote(encoded_key)

                    s3_client = boto3.client(
                        's3',
                        region_name=settings.AWS_S3_REGION_NAME,
                        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    )

                    obj = s3_client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)
                except Exception as e:
                    # Distinguish not-found from other errors when possible
                    if hasattr(boto3, "client") and getattr(getattr(e, "response", {}), "get", None):
                        try:
                            code = e.response.get("Error", {}).get("Code")  # type: ignore[attr-defined]
                        except Exception:
                            code = None
                        if code in ("NoSuchKey", "404"):
                            return Response(
                                {
                                    'status': 'error',
                                    'message': 'Document not available from remote storage'
                                },
                                status=status.HTTP_404_NOT_FOUND
                            )
                    return Response(
                        {
                            'status': 'error',
                            'message': f'Unable to fetch document from remote storage: {e}'
                        },
                        status=status.HTTP_502_BAD_GATEWAY
                    )

                body = obj['Body']

                def iter_stream():
                    for chunk in body.iter_chunks(chunk_size=8192):
                        if chunk:
                            yield chunk

                content_type = obj.get('ContentType') or 'application/pdf'
                content_length = obj.get('ContentLength')

                response = StreamingHttpResponse(iter_stream(), content_type=content_type)
                if content_length is not None:
                    response['Content-Length'] = str(content_length)
                response['Content-Disposition'] = f'inline; filename="{document.file_name}"'

                from audit.utils import log_action
                log_action(
                    request.user,
                    "PREVIEW_DOC",
                    document,
                    f"User {request.user.full_name or request.user.username} previewed document '{document.file_name}'.",
                    request=request
                )

                return response

            # Local / MEDIA-backed files – resolve absolute path
            abs_path = get_media_absolute_path_from_url(source_url)

            # If we ended up with a non-absolute path, treat it as relative to MEDIA_ROOT
            if not os.path.isabs(abs_path):
                abs_path = os.path.join(str(settings.MEDIA_ROOT), abs_path)

            if not os.path.exists(abs_path):
                return Response(
                    {
                        'status': 'error',
                        'message': 'Document file not found on server'
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            file_handle = open(abs_path, 'rb')
            response = FileResponse(
                file_handle,
                content_type='application/pdf',
                as_attachment=False,
            )
            response['Content-Disposition'] = f'inline; filename="{document.file_name}"'

            from audit.utils import log_action
            log_action(
                request.user,
                "PREVIEW_DOC",
                document,
                f"User {request.user.full_name or request.user.username} previewed document '{document.file_name}'.",
                request=request
            )

            return response

        except Document.DoesNotExist:
            return Response(
                {
                    'status': 'error',
                    'message': 'Document not found or access denied'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except FileNotFoundError:
            return Response(
                {
                    'status': 'error',
                    'message': 'Document file not found on server'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {
                    'status': 'error',
                    'message': f'Error streaming document for preview: {str(e)}'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MergeDocumentsView(APIView):
    """
    API view to merge multiple existing documents owned by the user into one PDF.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MergeDocumentsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': 'Validation failed',
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        document_ids = serializer.validated_data['document_ids']
        desired_name = serializer.validated_data.get('name') or ""

        MERGEABLE_STATUSES = ('draft', 'completed')
        docs = []
        temp_paths_to_cleanup = []
        try:
            for doc_id in document_ids:
                doc = Document.objects.filter(id=doc_id, owner=request.user).first()
                if not doc:
                    return Response({
                        'status': 'error',
                        'message': f'Access denied or document not found: {doc_id}'
                    }, status=status.HTTP_403_FORBIDDEN)

                if doc.status not in MERGEABLE_STATUSES:
                    return Response({
                        'status': 'error',
                        'message': (
                            f'Document {doc_id} cannot be merged (status={doc.status}). '
                            'Only draft or completed documents are allowed.'
                        )
                    }, status=status.HTTP_400_BAD_REQUEST)

                if EnvelopeDocument.objects.filter(
                    document=doc,
                    envelope__status='pending',
                ).exists():
                    return Response({
                        'status': 'error',
                        'message': (
                            f'Document {doc_id} is part of a pending envelope and cannot be merged.'
                        )
                    }, status=status.HTTP_400_BAD_REQUEST)

                source_url = doc.signed_file_url or doc.file_url
                try:
                    local_path = download_pdf_to_temp(source_url)
                    temp_paths_to_cleanup.append(str(local_path))
                    docs.append((doc, str(local_path)))
                except FileNotFoundError:
                    return Response({
                        'status': 'error',
                        'message': f'Source file missing for document {doc_id}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                except Exception as exc:
                    return Response({
                        'status': 'error',
                        'message': f'Failed to download source for document {doc_id}: {exc}'
                    }, status=status.HTTP_400_BAD_REQUEST)

            if desired_name.strip() and not _is_placeholder_merge_name(desired_name):
                safe_base = _sanitize_filename_component(desired_name.strip(), fallback="Merged Document", max_len=120)
                file_name = safe_base if safe_base.lower().endswith('.pdf') else f"{safe_base}.pdf"
            else:
                file_name = _default_merged_filename(docs[0][0].file_name, len(docs))

            writer = PdfWriter()
            try:
                for _, abs_path in docs:
                    reader = PdfReader(abs_path)
                    for page in reader.pages:
                        writer.add_page(page)
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': f'Failed to read/merge PDFs: {e}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            new_doc = Document.objects.create(
                owner=request.user,
                file_url="",
                file_name=file_name,
                file_size=0,
                status='draft',
            )

            with temp_pdf_file() as merged_temp:
                with open(merged_temp, 'wb') as fout:
                    writer.write(fout)
                file_size = merged_temp.stat().st_size
                file_url = upload_staging_pdf(new_doc.id, merged_temp)

            new_doc.file_url = file_url
            new_doc.file_size = file_size
            new_doc.save(update_fields=['file_url', 'file_size', 'updated_at'])
        finally:
            for path in temp_paths_to_cleanup:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass

        try:
            from audit.utils import log_action
            joined_ids = ", ".join([str(i) for i in document_ids])
            log_action(
                request.user,
                "MERGE_DOCS",
                new_doc,
                f"User {request.user.full_name or request.user.username} merged documents [{joined_ids}] into '{file_name}'.",
                request=request
            )
        except Exception:
            # Do not fail main flow on audit issues
            pass

        return Response({
            'status': 'success',
            'message': 'Documents merged successfully',
            'data': {
                'id': str(new_doc.id),
                'file_url': new_doc.file_url,
                'name': new_doc.file_name
            }
        }, status=status.HTTP_201_CREATED)