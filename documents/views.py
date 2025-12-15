"""
Views for the documents app.

This module contains API views for document upload and management
functionality in the e-signature workflow.
"""

import logging
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView, DestroyAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import FileResponse, Http404
import os
from urllib.parse import unquote
from django.conf import settings
from .models import Document
from envelopes.models import Envelope
from .serializers import DocumentUploadSerializer, DocumentSerializer, MergeDocumentsSerializer
from django.db import models
from envelopes.models import EnvelopeDocument
from signatures.utils.pdf_signing import get_media_absolute_path_from_url
from pypdf import PdfReader, PdfWriter
import uuid

logger = logging.getLogger(__name__)


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
        Download a document file.
        
        Args:
            request: HTTP request
            pk: Document UUID
            
        Returns:
            FileResponse: PDF file download or 404 error
        """
        try:
            # Get the document, ensuring user has access via ownership or envelope participation
            user = request.user
            # Quick check for ownership
            document = Document.objects.filter(id=pk, owner=user).first()
            if not document:
                # Check if the document exists and the user has access via an envelope
                # Check envelope creator access
                has_creator_access = EnvelopeDocument.objects.filter(document__id=pk, envelope__creator=user).exists()
                if has_creator_access:
                    document = get_object_or_404(Document, id=pk)
                else:
                    # Check signer access by scanning EnvelopeDocuments for this document
                    has_signer_access = False
                    for env_doc in EnvelopeDocument.objects.filter(document__id=pk):
                        for signer_entry in env_doc.envelope.signing_order:
                            if signer_entry.get('signer_id') == str(user.id):
                                has_signer_access = True
                                break
                        if has_signer_access:
                            document = get_object_or_404(Document, id=pk)
                        else:
                            raise Http404
            
            # Get the full file path - prioritize signed version if available
            # Use the same logic as signing: signed_file_url takes precedence
            source_url = document.signed_file_url or document.file_url
            
            if source_url.startswith('/media/'):
                # For local files, construct the full path
                # Decode URL-encoded filename (e.g., %20 -> space)
                file_path = os.path.join(settings.MEDIA_ROOT, unquote(source_url[7:]))  # Remove '/media/' prefix and decode URL
            elif source_url.startswith('http'):
                # For S3 or other remote storage, redirect to the URL
                from django.http import HttpResponseRedirect
                return HttpResponseRedirect(source_url)
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
            if not os.path.isabs(abs_path) or not os.path.exists(abs_path):
                return Response({
                    'status': 'error',
                    'message': f'Source file missing on server for document {doc_id}'
                }, status=status.HTTP_400_BAD_REQUEST)
            docs.append((doc, abs_path))

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