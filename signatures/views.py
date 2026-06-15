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
from .models import Signature, UserSignature
from .serializers import SignatureSerializer, SignDocumentSerializer, DeclineSignatureSerializer, UserSignatureSerializer
from .services.signing import (
    DocumentNotAvailableForSigningError,
    SignatureImageError,
    complete_envelope,
    embed_signatures_for_signer,
    mark_signature_signed,
    resolve_signature_image,
)
import logging

LOGGER = logging.getLogger(__name__)


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
        from envelopes.models import Envelope
        envelope = get_object_or_404(Envelope, pk=envelope_id)
        
        if envelope.status != "pending":
            return Response({
                "status": "error",
                "message": f"Envelope must be in 'pending' status to sign. Current status: {envelope.status}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        if not signature.is_current_signer():
            return Response({
                "status": "error",
                "message": "It's not your turn to sign yet. Please wait for your turn."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if signature.is_signed:
            return Response({
                "status": "error",
                "message": "You have already signed this document."
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = SignDocumentSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data

        try:
            signature_image_data = resolve_signature_image(request.user, validated_data)
        except SignatureImageError as exc:
            return Response({
                "status": "error",
                "message": str(exc)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        signature.refresh_from_db()
        if signature.is_signed:
            signature_serializer = SignatureSerializer(signature)
            return Response({
                "status": "success",
                "message": "Document signed successfully",
                "data": signature_serializer.data
            }, status=status.HTTP_200_OK)

        fallback_placement = {
            'page': validated_data.get('page', 1),
            'x': validated_data.get('x', 100),
            'y': validated_data.get('y', 100),
            'width': validated_data.get('width', 120),
            'height': validated_data.get('height', 40),
        }

        try:
            embed_signatures_for_signer(
                envelope,
                request.user,
                signature_image_data,
                fallback_placement=fallback_placement,
            )
        except DocumentNotAvailableForSigningError as exc:
            return Response({
                "status": "error",
                "message": str(exc)
            }, status=status.HTTP_400_BAD_REQUEST)

        mark_signature_signed(signature, signature_image_data)
        
        from audit.utils import log_action
        log_action(
            request.user, 
            "SIGN_DOC", 
            signature, 
            f"User {request.user.full_name or request.user.username} signed envelope '{signature.envelope.name}' with {signature.envelope.envelopedocument_set.count()} documents.", 
            request=request
        )
        
        remaining_pending = Signature.objects.filter(
            envelope=envelope,
            status='pending'
        ).count()
        
        from notifications.utils import create_notification, create_signer_turn_notification
        from notifications.tasks import send_turn_to_sign_email_task
        
        if remaining_pending == 0:
            complete_envelope(envelope, notify_creator=True)
        else:
            def get_order_for_signer_id(signer_id: str) -> int:
                if not envelope.signing_order:
                    return 0
                for idx, signer_entry in enumerate(envelope.signing_order, 1):
                    if str(signer_entry.get('signer_id')) == str(signer_id):
                        explicit = signer_entry.get('order')
                        return explicit if isinstance(explicit, int) and explicit >= 1 else idx
                return 0

            current_order = signature.get_signing_order()
            next_signer_id = None
            next_order = None
            if envelope.signing_order:
                for signer_entry in envelope.signing_order:
                    candidate_id = signer_entry.get('signer_id')
                    candidate_order = get_order_for_signer_id(candidate_id)
                    if candidate_order > current_order and (next_order is None or candidate_order < next_order):
                        next_order = candidate_order
                        next_signer_id = candidate_id

            next_signature = None
            if next_signer_id is not None:
                next_signature = Signature.objects.filter(
                    envelope=envelope,
                    signer__id=next_signer_id,
                    status='pending'
                ).first()

            if next_signature:
                message = create_signer_turn_notification(envelope)
                create_notification(str(next_signature.signer.id), message)
                try:
                    recipient_email = getattr(next_signature.signer, 'email', None)
                    if recipient_email:
                        send_turn_to_sign_email_task.delay(
                            recipient_email,
                            envelope.name,
                            str(envelope.id)
                        )
                except Exception as exc:
                    LOGGER.error("Error sending turn-to-sign email: %s", exc)
        
        signature_serializer = SignatureSerializer(signature)
        
        return Response({
            "status": "success",
            "message": "Document signed successfully",
            "data": signature_serializer.data
        }, status=status.HTTP_200_OK)


class SelfSignView(APIView):
    """
    API view for one-call self-sign envelope creation and completion.

    Endpoint: POST /signatures/self-sign/
    Requires authentication. No recipients or notifications.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.db import transaction
        from envelopes.models import Envelope
        from envelopes.serializers import EnvelopeDetailSerializer
        from documents.models import Document
        from audit.utils import log_action

        from .serializers import SelfSignSerializer

        serializer = SelfSignSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "data": serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        sign_data = serializer.get_sign_data()

        try:
            with transaction.atomic():
                envelope = serializer.save()
                Signature.objects.create(
                    envelope=envelope,
                    signer=request.user,
                    status='pending',
                )
                envelope.status = 'pending'
                envelope.save(update_fields=['status', 'updated_at'])
                Document.objects.filter(
                    envelopedocument_set__envelope=envelope,
                ).update(status='sent')

            signature_image_data = resolve_signature_image(request.user, sign_data)
            fallback_placement = {
                'page': sign_data.get('page', 1),
                'x': sign_data.get('x', 100),
                'y': sign_data.get('y', 100),
                'width': sign_data.get('width', 120),
                'height': sign_data.get('height', 40),
            }
            embed_signatures_for_signer(
                envelope,
                request.user,
                signature_image_data,
                fallback_placement=fallback_placement,
            )
            signature = Signature.objects.get(envelope=envelope, signer=request.user)
            mark_signature_signed(signature, signature_image_data)
            complete_envelope(envelope, notify_creator=False)
        except SignatureImageError as exc:
            return Response({
                "status": "error",
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)
        except DocumentNotAvailableForSigningError as exc:
            return Response({
                "status": "error",
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        envelope = Envelope.objects.get(pk=envelope.pk)
        log_action(
            request.user,
            "SELF_SIGN_DOC",
            envelope,
            f"User {request.user.full_name or request.user.username} self-signed envelope '{envelope.name}'.",
            request=request,
        )

        detail_serializer = EnvelopeDetailSerializer(envelope)
        return Response({
            "status": "success",
            "message": "Document self-signed successfully",
            "data": detail_serializer.data,
        }, status=status.HTTP_201_CREATED)


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
        
        # Check if envelope is in pending status
        if envelope.status != "pending":
            return Response({
                "status": "error",
                "message": f"Envelope must be in 'pending' status to decline. Current status: {envelope.status}"
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
            }, status=status.HTTP_403_FORBIDDEN) # Changed to 403 Forbidden
        
        # Check if already signed or declined
        if signature.is_signed or signature.is_declined:
            return Response({
                "status": "error",
                "message": f"You have already {signature.status} this document."
            }, status=status.HTTP_403_FORBIDDEN) # Changed to 403 Forbidden
        
        # Validate the request
        serializer = DeclineSignatureSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        decline_message = serializer.validated_data.get('decline_message')

        # Update the signature
        signature.status = "declined"
        signature.save()
        
        # Log the signature decline action
        from audit.utils import log_action
        log_action(
            request.user, 
            "DECLINE_SIGN", 
            signature, 
            f"User {request.user.full_name or request.user.username} declined to sign envelope '{signature.envelope.name}' with {signature.envelope.envelopedocument_set.count()} documents." + (f" Reason: {decline_message}" if decline_message else ""), 
            request=request
        )
        
        # Mark envelope as rejected
        envelope.status = "rejected"
        envelope.save()
        
        # Notify creator about decline
        from notifications.utils import create_notification, create_signer_declined_notification
        
        message = create_signer_declined_notification(envelope, request.user, decline_message)
        create_notification(str(envelope.creator.id), message)
        
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