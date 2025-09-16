"""
Views for the envelopes app.

This module defines API views for envelope-related operations
in the e-signature workflow.
"""

from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from .models import Envelope
from .serializers import EnvelopeCreateSerializer, EnvelopeDetailSerializer, EnvelopeSerializer


class EnvelopeCreateView(APIView):
    """
    API view for creating new envelopes.
    
    Endpoint: POST /envelopes/create/
    Requires authentication.
    Accepts payload: {document_id, signing_order}
    Returns created envelope details.
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Create a new envelope for a document.
        
        Args:
            request: HTTP request containing document_id and signing_order
            
        Returns:
            Response with created envelope details or error message
        """
        serializer = EnvelopeCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            envelope = serializer.save()
            
            # Return envelope details using the detail serializer
            detail_serializer = EnvelopeDetailSerializer(envelope)
            
            return Response({
                "status": "success",
                "message": "Envelope created successfully",
                "data": detail_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            "status": "error",
            "message": "Validation failed",
            "data": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class EnvelopeSendView(APIView):
    """
    API view for sending envelopes.
    
    Endpoint: POST /envelopes/{id}/send/
    Requires authentication.
    Only the envelope creator can send.
    Changes status from "draft" to "sent".
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """
        Send an envelope (change status from draft to sent).
        
        Args:
            request: HTTP request
            pk: Envelope ID
            
        Returns:
            Response with updated envelope details or error message
        """
        envelope = get_object_or_404(Envelope, pk=pk)
        
        # Check if user is the creator
        if envelope.creator != request.user:
            return Response({
                "status": "error",
                "message": "You can only send envelopes you created."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if envelope is in draft status
        if envelope.status != "draft":
            return Response({
                "status": "error",
                "message": f"Only draft envelopes can be sent. Current status: {envelope.status}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update envelope status to sent
        envelope.status = "sent"
        envelope.save()
        
        # Create Signature records for each signer in signing_order
        from signatures.models import Signature
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        for signer_entry in envelope.signing_order:
            signer_id = signer_entry['signer_id']
            try:
                signer = User.objects.get(id=signer_id)
                # Create signature record for this signer
                Signature.objects.create(
                    envelope=envelope,
                    signer=signer,
                    status='pending'
                )
            except User.DoesNotExist:
                # This should not happen due to validation, but handle gracefully
                continue
        
        # Return updated envelope details
        serializer = EnvelopeSerializer(envelope)
        
        return Response({
            "status": "success",
            "message": "Envelope sent successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class EnvelopeRejectView(APIView):
    """
    API view for rejecting envelopes.
    
    Endpoint: POST /envelopes/{id}/reject/
    Requires authentication.
    Only the envelope creator can reject.
    Changes status to "rejected".
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """
        Reject an envelope (change status to rejected).
        
        Args:
            request: HTTP request
            pk: Envelope ID
            
        Returns:
            Response with updated envelope details or error message
        """
        envelope = get_object_or_404(Envelope, pk=pk)
        
        # Check if user is the creator
        if envelope.creator != request.user:
            return Response({
                "status": "error",
                "message": "You can only reject envelopes you created."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Update envelope status to rejected
        envelope.status = "rejected"
        envelope.save()
        
        # Return updated envelope details
        serializer = EnvelopeSerializer(envelope)
        
        return Response({
            "status": "success",
            "message": "Envelope rejected successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class EnvelopeListView(ListAPIView):
    """
    API view for listing envelopes.
    
    Endpoint: GET /envelopes/
    Requires authentication.
    Returns:
        - Envelopes created by request.user
        - Envelopes where request.user is a signer
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = EnvelopeSerializer
    
    def get_queryset(self):
        """
        Return envelopes where the user is either the creator or a signer.
        """
        user = self.request.user
        
        # Get all envelopes and filter in Python for better database compatibility
        all_envelopes = Envelope.objects.all()
        
        # Filter envelopes where user is creator or signer
        user_envelopes = []
        for envelope in all_envelopes:
            # Check if user is the creator
            if envelope.creator == user:
                user_envelopes.append(envelope)
                continue
            
            # Check if user is in the signing order
            for signer_entry in envelope.signing_order:
                if signer_entry.get('signer_id') == str(user.id):
                    user_envelopes.append(envelope)
                    break
        
        # Convert to queryset and order by creation date
        envelope_ids = [env.id for env in user_envelopes]
        return Envelope.objects.filter(id__in=envelope_ids).order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        """
        Override list to return custom response format.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            "status": "success",
            "message": "Envelopes retrieved successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class EnvelopeDetailView(RetrieveAPIView):
    """
    API view for retrieving envelope details.
    
    Endpoint: GET /envelopes/{id}/
    Requires authentication.
    Creator can view their envelope.
    Signers can view envelopes they are assigned to.
    Returns full details including signature statuses.
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = EnvelopeSerializer
    lookup_field = 'pk'
    
    def get_queryset(self):
        """
        Return envelopes where the user is either the creator or a signer.
        """
        user = self.request.user
        
        # Get all envelopes and filter in Python for better database compatibility
        all_envelopes = Envelope.objects.all()
        
        # Filter envelopes where user is creator or signer
        user_envelopes = []
        for envelope in all_envelopes:
            # Check if user is the creator
            if envelope.creator == user:
                user_envelopes.append(envelope)
                continue
            
            # Check if user is in the signing order
            for signer_entry in envelope.signing_order:
                if signer_entry.get('signer_id') == str(user.id):
                    user_envelopes.append(envelope)
                    break
        
        # Convert to queryset
        envelope_ids = [env.id for env in user_envelopes]
        return Envelope.objects.filter(id__in=envelope_ids)
    
    def retrieve(self, request, *args, **kwargs):
        """
        Override retrieve to return custom response format and handle permissions.
        """
        # Check if envelope exists and user has access
        try:
            envelope = Envelope.objects.get(pk=kwargs['pk'])
        except Envelope.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Envelope not found or access denied"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user has access to this envelope
        user = request.user
        has_access = False
        
        # Check if user is the creator
        if envelope.creator == user:
            has_access = True
        else:
            # Check if user is in the signing order
            for signer_entry in envelope.signing_order:
                if signer_entry.get('signer_id') == str(user.id):
                    has_access = True
                    break
        
        if not has_access:
            return Response({
                "status": "error",
                "message": "Envelope not found or access denied"
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = self.get_serializer(envelope)
        
        return Response({
            "status": "success",
            "message": "Envelope retrieved successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)
