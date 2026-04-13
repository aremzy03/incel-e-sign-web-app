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
from rest_framework.generics import DestroyAPIView, ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer, MergeDocumentsSerializer
from envelopes.models import Envelope, EnvelopeDocument
from signatures.utils.pdf_signing import get_media_absolute_path_from_url
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


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
        return Document.objects.filter(owner=self.request.user).select_related('owner').order_by('-created_at')


class DocumentDetailView(RetrieveAPIView):
    """
    API view for retrieving a single document.
    
    Users can only access their own documents.
    Returns 404 if document doesn't exist or user is not the owner.
    Requires authentication.
    """
    
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Return documents accessible to the authenticated user.
        
        A document is accessible if:
        - The user is the owner of the document, or
        - The user is the creator of an envelope that contains the document, or
        - The user is listed as a signer in an envelope that contains the document.
        """
        user = self.request.user
        user_id_str = str(user.id)
        
        # Collect documents owned by the user
        owned_documents = Document.objects.filter(owner=user)

        # Collect document IDs from envelopes where user is creator
        creator_envelopes_docs_pks = set(
            EnvelopeDocument.objects
            .filter(envelope__creator=user)
            .select_related('document', 'envelope')
            .values_list('document__id', flat=True)
        )

        # Optimize signer check: Use prefetch to avoid N+1 queries
        # For PostgreSQL, we could use JSON queries, but for compatibility with SQLite tests,
        # we'll fetch envelopes with prefetch and check signing_order in Python
        # This is still much better than fetching ALL EnvelopeDocuments
        from envelopes.models import Envelope
        signer_envelopes_docs_pks = set()
        
        # Fetch only envelopes (not all EnvelopeDocuments)
        # Then check their signing_order and fetch related documents
        envelopes_as_signer = Envelope.objects.prefetch_related('envelopedocument_set__document').all()
        
        for envelope in envelopes_as_signer:
            # Check if user is in signing_order
            for signer_entry in envelope.signing_order:
                if str(signer_entry.get('signer_id')) == user_id_str:
                    # User is a signer, add all documents from this envelope
                    signer_envelopes_docs_pks.update(
                        env_doc.document.id for env_doc in envelope.envelopedocument_set.all()
                    )
                    break

        accessible_ids = creator_envelopes_docs_pks.union(signer_envelopes_docs_pks)

        # Combine owned documents and documents from accessible envelopes
        accessible_documents = owned_documents | Document.objects.filter(id__in=list(accessible_ids))
        
        return accessible_documents.select_related('owner').distinct().order_by('-created_at')
    
    def get_object(self):
        """
        Get the document object, ensuring user can only access their own documents.
        
        Returns:
            Document: The requested document
            
        Raises:
            Http404: If document doesn't exist or user is not the owner
        """
        queryset = self.get_queryset()
        document_id = self.kwargs.get('pk')
        return get_object_or_404(queryset, id=document_id)


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
        desired_name = serializer.validated_data.get('name') or 'Merged Document'

        # Fetch and validate ownership/access
        docs = []
        for doc_id in document_ids:
            doc = Document.objects.filter(id=doc_id, owner=request.user).first()
            if not doc:
                return Response({
                    'status': 'error',
                    'message': f'Access denied or document not found: {doc_id}'
                }, status=status.HTTP_403_FORBIDDEN)
            # Resolve file path (prefer signed if exists)
            source_url = doc.signed_file_url or doc.file_url
            abs_path = get_media_absolute_path_from_url(source_url)

            # For local filesystem paths, ensure the file exists.
            if os.path.isabs(abs_path):
                if not os.path.exists(abs_path):
                    return Response({
                        'status': 'error',
                        'message': f'Source file missing on server for document {doc_id}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                docs.append((doc, abs_path))
            else:
                # For non-local sources (e.g. S3 URLs), merging is not currently
                # supported without first downloading to a temporary location.
                return Response({
                    'status': 'error',
                    'message': f'Merging documents stored on remote storage is not supported for document {doc_id}'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Perform merge preserving order
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

        # Write merged PDF to MEDIA_ROOT/merged_docs
        merged_dir = os.path.join(str(settings.MEDIA_ROOT), 'merged_docs')
        os.makedirs(merged_dir, exist_ok=True)
        merged_id = uuid.uuid4()
        safe_base = desired_name or 'Merged Document'
        # Ensure .pdf extension
        file_name = safe_base if safe_base.lower().endswith('.pdf') else f"{safe_base}.pdf"
        # Prepend uuid to ensure uniqueness on disk
        disk_name = f"{merged_id}_{file_name}"
        abs_out = os.path.join(merged_dir, disk_name)
        try:
            with open(abs_out, 'wb') as fout:
                writer.write(fout)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Failed to write merged PDF: {e}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Build file_url relative to MEDIA_URL
        rel_path = os.path.relpath(abs_out, str(settings.MEDIA_ROOT))
        file_url = f"{settings.MEDIA_URL}{rel_path}"

        # Create Document record
        try:
            file_size = os.path.getsize(abs_out)
            new_doc = Document.objects.create(
                owner=request.user,
                file_url=file_url,
                file_name=file_name,
                file_size=file_size,
                status='draft'
            )
        except Exception as e:
            # Cleanup file if DB create fails
            try:
                if os.path.exists(abs_out):
                    os.remove(abs_out)
            except Exception:
                pass
            return Response({
                'status': 'error',
                'message': f'Failed to create merged Document record: {e}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Audit log
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