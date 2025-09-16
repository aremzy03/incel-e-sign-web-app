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
from .models import Document
from .serializers import DocumentUploadSerializer, DocumentSerializer


class DocumentUploadView(APIView):
    """
    API view for uploading PDF documents.
    
    Handles file upload, validation, storage, and Document model creation.
    Requires authentication.
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Handle document upload.
        
        Args:
            request: HTTP request containing file data
            
        Returns:
            Response: JSON response with document details or error
        """
        serializer = DocumentUploadSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Save the document
                document = serializer.save(owner=request.user)
                
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
        
        return Response(
            {
                'status': 'error',
                'message': 'Invalid file data',
                'data': serializer.errors
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
        Return documents owned by the authenticated user.
        
        Returns:
            QuerySet: Documents owned by the current user
        """
        return Document.objects.filter(owner=self.request.user)
    
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