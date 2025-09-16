"""
Views for the signatures app.

This module defines API views for signature-related operations
in the e-signature workflow.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Signature
from .serializers import SignatureSerializer, SignDocumentSerializer, DeclineSignatureSerializer


class SignDocumentView(APIView):
    """
    API view for signing documents.
    
    Endpoint: POST /signatures/{envelope_id}/sign/
    Requires authentication.
    Only the current signer (lowest pending order) can sign.
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        """
        Sign a document in the envelope.
        
        Args:
            request: HTTP request containing signature_image
            envelope_id: UUID of the envelope
            
        Returns:
            Response with signature details or error message
        """
        # Get the envelope
        from envelopes.models import Envelope
        envelope = get_object_or_404(Envelope, pk=envelope_id)
        
        # Check if envelope is in sent status
        if envelope.status != "sent":
            return Response({
                "status": "error",
                "message": f"Envelope must be in 'sent' status to sign. Current status: {envelope.status}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the signature record for the current user
        try:
            signature = Signature.objects.get(
                envelope=envelope,
                signer=request.user
            )
        except Signature.DoesNotExist:
            return Response({
                "status": "error",
                "message": "You are not authorized to sign this document."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if this signer is the current signer
        if not signature.is_current_signer():
            return Response({
                "status": "error",
                "message": "It's not your turn to sign yet. Please wait for your turn."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if already signed
        if signature.is_signed:
            return Response({
                "status": "error",
                "message": "You have already signed this document."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate the signature data
        serializer = SignDocumentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update the signature
        signature.status = "signed"
        signature.signed_at = timezone.now()
        signature.signature_image = serializer.validated_data['signature_image']
        signature.save()
        
        # Log the signature action
        from audit.utils import log_action
        log_action(
            request.user, 
            "SIGN_DOC", 
            signature, 
            f"User {request.user.get_full_name() or request.user.username} signed envelope {signature.envelope.id} for document '{signature.envelope.document.file_name}'.", 
            request=request
        )
        
        # Check if this was the last signer
        remaining_pending = Signature.objects.filter(
            envelope=envelope,
            status='pending'
        ).count()
        
        # Send notifications
        from notifications.utils import create_notification, create_envelope_completed_notification, create_signer_turn_notification
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        if remaining_pending == 0:
            # All signers have signed - mark envelope as completed
            envelope.status = "completed"
            envelope.save()
            
            # Notify creator that envelope is completed
            message = create_envelope_completed_notification(envelope)
            create_notification.delay(str(envelope.creator.id), message)
        else:
            # Notify next signer
            next_signature = Signature.objects.filter(
                envelope=envelope,
                status='pending'
            ).order_by('signer__id').first()
            
            if next_signature:
                message = create_signer_turn_notification(envelope)
                create_notification.delay(str(next_signature.signer.id), message)
        
        # Return signature details
        signature_serializer = SignatureSerializer(signature)
        
        return Response({
            "status": "success",
            "message": "Document signed successfully",
            "data": signature_serializer.data
        }, status=status.HTTP_200_OK)


class DeclineSignatureView(APIView):
    """
    API view for declining signatures.
    
    Endpoint: POST /signatures/{envelope_id}/decline/
    Requires authentication.
    Only the current signer can decline.
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        """
        Decline to sign a document in the envelope.
        
        Args:
            request: HTTP request
            envelope_id: UUID of the envelope
            
        Returns:
            Response with signature details or error message
        """
        # Get the envelope
        from envelopes.models import Envelope
        envelope = get_object_or_404(Envelope, pk=envelope_id)
        
        # Check if envelope is in sent status
        if envelope.status != "sent":
            return Response({
                "status": "error",
                "message": f"Envelope must be in 'sent' status to decline. Current status: {envelope.status}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the signature record for the current user
        try:
            signature = Signature.objects.get(
                envelope=envelope,
                signer=request.user
            )
        except Signature.DoesNotExist:
            return Response({
                "status": "error",
                "message": "You are not authorized to decline this document."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if this signer is the current signer
        if not signature.is_current_signer():
            return Response({
                "status": "error",
                "message": "It's not your turn to decline yet. Please wait for your turn."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if already signed or declined
        if signature.is_signed or signature.is_declined:
            return Response({
                "status": "error",
                "message": f"You have already {signature.status} this document."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate the request (no additional data needed for decline)
        serializer = DeclineSignatureSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update the signature
        signature.status = "declined"
        signature.save()
        
        # Log the signature decline action
        from audit.utils import log_action
        log_action(
            request.user, 
            "DECLINE_SIGN", 
            signature, 
            f"User {request.user.get_full_name() or request.user.username} declined to sign envelope {signature.envelope.id} for document '{signature.envelope.document.file_name}'.", 
            request=request
        )
        
        # Mark envelope as rejected
        envelope.status = "rejected"
        envelope.save()
        
        # Notify creator about decline
        from notifications.utils import create_notification, create_signer_declined_notification
        
        message = create_signer_declined_notification(envelope, request.user)
        create_notification.delay(str(envelope.creator.id), message)
        
        # Return signature details
        signature_serializer = SignatureSerializer(signature)
        
        return Response({
            "status": "success",
            "message": "Document declined successfully. Envelope has been rejected.",
            "data": signature_serializer.data
        }, status=status.HTTP_200_OK)