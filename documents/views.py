"""
Views for the documents app.

This module contains API views for document upload and management
functionality in the e-signature workflow.
"""

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
from .serializers import DocumentUploadSerializer, DocumentSerializer
from django.db import models
from envelopes.models import EnvelopeDocument


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
        # Debug: Log request data
        print(f"DEBUG: Request method: {request.method}")
        print(f"DEBUG: Request content type: {request.content_type}")
        print(f"DEBUG: Request data keys: {list(request.data.keys()) if hasattr(request, 'data') else 'No data attr'}")
        print(f"DEBUG: Request files keys: {list(request.FILES.keys()) if hasattr(request, 'FILES') else 'No FILES attr'}")
        print(f"DEBUG: User: {request.user}")
        
        if 'file' in request.FILES:
            file = request.FILES['file']
            print(f"DEBUG: File details - Name: {file.name}, Size: {file.size}, Type: {file.content_type}")
        else:
            print("DEBUG: No 'file' key in request.FILES")
        
        # Create serializer with request data (includes files when multipart/form-data)
        serializer = DocumentUploadSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Save the document
                document = serializer.save(owner=request.user)
                
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
                return Response(
                    {
                        'status': 'error',
                        'message': f'Error uploading document: {str(e)}'
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Log serializer errors for debugging
        print(f"DEBUG: Serializer validation failed")
        print(f"DEBUG: Serializer errors: {serializer.errors}")
        print(f"DEBUG: Request data: {request.data}")
        
        return Response(
            {
                'status': 'error',
                'message': 'Invalid file data',
                'errors': serializer.errors,
                'debug_info': {
                    'content_type': request.content_type,
                    'has_files': bool(request.FILES),
                    'files_keys': list(request.FILES.keys()) if request.FILES else [],
                    'data_keys': list(request.data.keys()) if hasattr(request, 'data') else []
                }
            },
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
        return Document.objects.filter(owner=self.request.user).order_by('-created_at')


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
        # Collect documents owned by the user
        owned_documents = Document.objects.filter(owner=user)

        # Collect document IDs from envelopes where user is creator or signer
        # Filter envelopes where user is creator
        creator_envelopes_docs_pks = set(EnvelopeDocument.objects.filter(envelope__creator=user).values_list('document__id', flat=True))

        # Filter envelopes where user is a signer (Python-based for SQLite compatibility)
        signer_envelopes_docs_pks = set()
        # Get all EnvelopeDocuments that link to an envelope the user is a signer in
        for env_doc in EnvelopeDocument.objects.all(): # Fetch all EnvelopeDocument for iteration
            for signer_entry in env_doc.envelope.signing_order:
                if str(signer_entry.get('signer_id')) == str(user.id):
                    signer_envelopes_docs_pks.add(env_doc.document.id) # Use env_doc.document.id
                    break

        accessible_ids = creator_envelopes_docs_pks.union(signer_envelopes_docs_pks)

        # Combine owned documents and documents from accessible envelopes
        accessible_documents = owned_documents | Document.objects.filter(id__in=list(accessible_ids))
        
        return accessible_documents.distinct().order_by('-created_at')
    
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
                status=status.HTTP_204_NO_CONTENT
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
            
            # Create file response
            response = FileResponse(
                open(file_path, 'rb'),
                content_type='application/pdf',
                as_attachment=True,
                filename=document.file_name
            )
            
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