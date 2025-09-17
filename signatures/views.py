"""
Views for the signatures app.

This module defines API views for signature-related operations
in the e-signature workflow.
"""

from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Signature, UserSignature
from .serializers import SignatureSerializer, SignDocumentSerializer, DeclineSignatureSerializer, UserSignatureSerializer


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
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if already signed
        if signature.is_signed:
            return Response({
                "status": "error",
                "message": "You have already signed this document."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate the signature data
        serializer = SignDocumentSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the signature image data
        signature_image_data = None
        validated_data = serializer.validated_data
        
        if 'signature_image' in validated_data and validated_data['signature_image']:
            # Use provided signature image
            signature_image_data = validated_data['signature_image']
        elif 'signature_id' in validated_data and validated_data['signature_id']:
            # Use UserSignature image
            try:
                user_signature = UserSignature.objects.get(
                    id=validated_data['signature_id'],
                    user=request.user
                )
                # Convert image to base64 for storage
                import base64
                from django.core.files.base import ContentFile
                
                # Read the image file and convert to base64
                user_signature.image.open()
                image_data = user_signature.image.read()
                user_signature.image.close()
                
                # Convert to base64 data URL
                image_format = user_signature.image.name.split('.')[-1].lower()
                if image_format == 'jpg':
                    image_format = 'jpeg'
                signature_image_data = f"data:image/{image_format};base64,{base64.b64encode(image_data).decode()}"
                
            except UserSignature.DoesNotExist:
                return Response({
                    "status": "error",
                    "message": "UserSignature not found or does not belong to you."
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Try to use user's default signature
            try:
                default_signature = UserSignature.objects.get(
                    user=request.user,
                    is_default=True
                )
                # Convert image to base64 for storage
                import base64
                
                # Read the image file and convert to base64
                default_signature.image.open()
                image_data = default_signature.image.read()
                default_signature.image.close()
                
                # Convert to base64 data URL
                image_format = default_signature.image.name.split('.')[-1].lower()
                if image_format == 'jpg':
                    image_format = 'jpeg'
                signature_image_data = f"data:image/{image_format};base64,{base64.b64encode(image_data).decode()}"
                
            except UserSignature.DoesNotExist:
                return Response({
                    "status": "error",
                    "message": "No signature provided and no default signature found. Please provide signature_image, signature_id, or set a default signature."
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update the signature
        signature.status = "signed"
        signature.signed_at = timezone.now()
        signature.signature_image = signature_image_data
        signature.save()
        
        # Log the signature action
        from audit.utils import log_action
        log_action(
            request.user, 
            "SIGN_DOC", 
            signature, 
            f"User {request.user.full_name or request.user.username} signed envelope {signature.envelope.id} for document '{signature.envelope.document.file_name}'.", 
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
            f"User {request.user.full_name or request.user.username} declined to sign envelope {signature.envelope.id} for document '{signature.envelope.document.file_name}'.", 
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


class UserSignatureListCreateView(ListCreateAPIView):
    """
    API view for listing and creating user signatures.
    
    Endpoint: GET/POST /signatures/user/
    Requires authentication.
    Users can only access their own signatures.
    """
    
    serializer_class = UserSignatureSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Return signatures owned by the authenticated user.
        
        Returns:
            QuerySet: UserSignatures owned by the current user
        """
        return UserSignature.objects.filter(user=self.request.user).order_by('-created_at')
    
    def perform_create(self, serializer):
        """
        Create a new user signature.
        
        Args:
            serializer: UserSignatureSerializer instance
        """
        signature = serializer.save()
        
        # Log the signature creation action
        from audit.utils import log_action
        log_action(
            self.request.user, 
            "CREATE_USER_SIGNATURE", 
            signature, 
            f"User {self.request.user.full_name or self.request.user.username} created a new signature.", 
            request=self.request
        )
    
    def create(self, request, *args, **kwargs):
        """
        Create a new user signature and return appropriate response.
        
        Args:
            request: HTTP request
            *args: Additional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            Response: JSON response with signature details or error
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return Response({
            'status': 'success',
            'message': 'Signature created successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)


class UserSignatureDetailView(RetrieveUpdateDestroyAPIView):
    """
    API view for retrieving, updating, and deleting user signatures.
    
    Endpoint: GET/PATCH/DELETE /signatures/user/<id>/
    Requires authentication.
    Users can only access their own signatures.
    """
    
    serializer_class = UserSignatureSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        """
        Return signatures owned by the authenticated user.
        
        Returns:
            QuerySet: UserSignatures owned by the current user
        """
        return UserSignature.objects.filter(user=self.request.user)
    
    def get_object(self):
        """
        Get the signature object, ensuring user can only access their own signatures.
        
        Returns:
            UserSignature: The requested signature
            
        Raises:
            Http404: If signature doesn't exist or user is not the owner
        """
        queryset = self.get_queryset()
        signature_id = self.kwargs.get('id')
        return get_object_or_404(queryset, id=signature_id)
    
    def update(self, request, *args, **kwargs):
        """
        Update a user signature and return appropriate response.
        
        Args:
            request: HTTP request
            *args: Additional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            Response: JSON response with updated signature details or error
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Log the signature update action
        from audit.utils import log_action
        log_action(
            request.user, 
            "UPDATE_USER_SIGNATURE", 
            instance, 
            f"User {request.user.full_name or request.user.username} updated signature {instance.id}.", 
            request=request
        )
        
        return Response({
            'status': 'success',
            'message': 'Signature updated successfully',
            'data': serializer.data
        })
    
    def destroy(self, request, *args, **kwargs):
        """
        Delete a user signature and return appropriate response.
        
        Args:
            request: HTTP request
            *args: Additional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            Response: 204 No Content on successful deletion
        """
        instance = self.get_object()
        
        # Log the signature deletion action
        from audit.utils import log_action
        log_action(
            request.user, 
            "DELETE_USER_SIGNATURE", 
            instance, 
            f"User {request.user.full_name or request.user.username} deleted signature {instance.id}.", 
            request=request
        )
        
        self.perform_destroy(instance)
        return Response({
            'status': 'success',
            'message': 'Signature deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)