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
from .models import Signature, UserSignature, SigningJob
from .serializers import (
    SignatureSerializer,
    SignDocumentSerializer,
    DeclineSignatureSerializer,
    UserSignatureSerializer,
    SigningJobSerializer,
)
from .services.signing import (
    SignatureImageError,
    resolve_signature_image,
)
from .services.cutover import FROZEN_ENVELOPE_MESSAGE, is_envelope_frozen
from .services.job_service import (
    create_and_enqueue_signing_job,
    get_active_signing_job,
    signing_job_response_data,
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

        if is_envelope_frozen(envelope):
            return Response({
                "status": "error",
                "message": FROZEN_ENVELOPE_MESSAGE,
            }, status=status.HTTP_409_CONFLICT)
        
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
        
        if signature.is_signed:
            signature_serializer = SignatureSerializer(signature)
            return Response({
                "status": "success",
                "message": "Document signed successfully",
                "data": signature_serializer.data
            }, status=status.HTTP_200_OK)

        active_job = get_active_signing_job(envelope, request.user)
        if active_job or signature.is_processing:
            job = active_job or SigningJob.objects.filter(
                envelope=envelope, signer=request.user
            ).order_by("-created_at").first()
            return Response({
                "status": "success",
                "message": "Signing job queued",
                "data": signing_job_response_data(job),
            }, status=status.HTTP_202_ACCEPTED)

        fallback_placement = {
            'page': validated_data.get('page', 1),
            'x': validated_data.get('x', 100),
            'y': validated_data.get('y', 100),
            'width': validated_data.get('width', 120),
            'height': validated_data.get('height', 40),
        }

        from django.db import transaction

        with transaction.atomic():
            signature = Signature.objects.select_for_update().get(pk=signature.pk)
            if signature.is_signed:
                signature_serializer = SignatureSerializer(signature)
                return Response({
                    "status": "success",
                    "message": "Document signed successfully",
                    "data": signature_serializer.data
                }, status=status.HTTP_200_OK)

            job = create_and_enqueue_signing_job(
                envelope=envelope,
                signer=request.user,
                signature=signature,
                signature_image_data=signature_image_data,
                fallback_placement=fallback_placement,
                request=request,
            )

        return Response({
            "status": "success",
            "message": "Signing job queued",
            "data": signing_job_response_data(job),
        }, status=status.HTTP_202_ACCEPTED)


class SigningJobDetailView(APIView):
    """GET /api/signatures/jobs/{id}/ — poll async signing job status."""

    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        job = get_object_or_404(SigningJob.objects.select_related("envelope", "signer", "signature"), pk=id)
        user = request.user
        if job.signer_id != user.id and job.envelope.creator_id != user.id and not user.is_staff:
            return Response({
                "status": "error",
                "message": "You are not authorized to view this signing job.",
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = SigningJobSerializer(job)
        return Response({
            "status": "success",
            "data": serializer.data,
        })


class SigningJobRetryView(APIView):
    """POST /api/signatures/jobs/{id}/retry/ — retry a failed signing job."""

    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        job = get_object_or_404(SigningJob.objects.select_related("envelope", "signer", "signature"), pk=id)
        if job.signer_id != request.user.id:
            return Response({
                "status": "error",
                "message": "You are not authorized to retry this signing job.",
            }, status=status.HTTP_403_FORBIDDEN)

        if job.status != "failed":
            return Response({
                "status": "error",
                "message": f"Only failed jobs can be retried. Current status: {job.status}",
            }, status=status.HTTP_400_BAD_REQUEST)

        from django.db import transaction

        with transaction.atomic():
            job = SigningJob.objects.select_for_update().get(pk=job.pk)
            if job.signature_id:
                Signature.objects.filter(pk=job.signature_id).update(status="processing")
            job.status = "queued"
            job.error_message = ""
            job.completed_at = None
            job.attempt_count += 1
            job.save(update_fields=["status", "error_message", "completed_at", "attempt_count", "updated_at"])

        from signatures.tasks import enqueue_signing_job

        enqueue_signing_job(job)

        return Response({
            "status": "success",
            "message": "Signing job queued",
            "data": signing_job_response_data(job),
        }, status=status.HTTP_202_ACCEPTED)


class SelfSignView(APIView):
    """
    API view for one-call self-sign envelope creation and completion.

    Endpoint: POST /signatures/self-sign/
    Requires authentication. No recipients or notifications.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.db import transaction
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
                signature = Signature.objects.create(
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

            job = create_and_enqueue_signing_job(
                envelope=envelope,
                signer=request.user,
                signature=signature,
                signature_image_data=signature_image_data,
                fallback_placement=fallback_placement,
                is_self_sign=True,
                request=request,
            )
        except SignatureImageError as exc:
            return Response({
                "status": "error",
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        log_action(
            request.user,
            "SELF_SIGN_DOC",
            envelope,
            f"User {request.user.full_name or request.user.username} self-sign job queued for envelope '{envelope.name}'.",
            request=request,
        )

        return Response({
            "status": "success",
            "message": "Signing job queued",
            "data": signing_job_response_data(job),
        }, status=status.HTTP_202_ACCEPTED)


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