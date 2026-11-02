"""
Views for the signatures app.

This module defines API views for signature-related operations
in the e-signature workflow.
"""

from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
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
        
        serializer = SignDocumentSerializer(
            data=request.data,
            context={'request': request, 'signer': signature.signer},
        )
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data

        signature_image_data = ''
        user_signature_id = None
        if validated_data.get('signature_image'):
            signature_image_data = validated_data['signature_image']
        elif validated_data.get('signature_id'):
            # Defer S3/storage fetch to the Celery worker so this endpoint returns 202 quickly.
            user_signature_id = validated_data['signature_id']
        else:
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
                user_signature_id=user_signature_id,
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

    permission_classes = [AllowAny]

    def post(self, request, id):
        job = get_object_or_404(SigningJob.objects.select_related("envelope", "signer", "signature"), pk=id)
        token_str = (
            request.query_params.get("token")
            or request.headers.get("X-Signing-Token")
            or request.data.get("token")
        )
        authorized = False
        if request.user and request.user.is_authenticated and job.signer_id == request.user.id:
            authorized = True
        elif token_str:
            from envelopes.services.signing_token import validate_signing_token

            signing_token, _, _ = validate_signing_token(token_str, allow_used=True)
            if signing_token and str(signing_token.envelope_id) == str(job.envelope_id):
                authorized = True

        if not authorized:
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

            signature_image_data = ''
            user_signature_id = None
            if sign_data.get('signature_image'):
                signature_image_data = sign_data['signature_image']
            elif sign_data.get('signature_id'):
                user_signature_id = sign_data['signature_id']
            else:
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
                user_signature_id=user_signature_id,
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


class SignDocumentPublicView(APIView):
    """
    Public API view for signing an envelope using a SigningToken.

    Endpoint: POST /signatures/{envelope_id}/sign-public/
    """
    permission_classes = [AllowAny]

    def post(self, request, envelope_id):
        from envelopes.models import Envelope
        from envelopes.services.signing_token import validate_signing_token, mark_token_used
        from fields.models import Field
        from django.db import transaction

        token_str = (
            request.data.get("token")
            or request.query_params.get("token")
            or request.headers.get("X-Signing-Token")
        )
        signing_token, error_code, error_message = validate_signing_token(token_str, envelope_id=str(envelope_id))
        if error_code:
            status_code = status.HTTP_410_GONE if error_code == "TOKEN_EXPIRED" else status.HTTP_403_FORBIDDEN
            if error_code in ("MISSING_TOKEN", "INVALID_TOKEN"):
                status_code = status.HTTP_400_BAD_REQUEST
            return Response({"status": "error", "code": error_code, "message": error_message}, status=status_code)

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

        signature = envelope.signatures.filter(
            signer__email__iexact=signing_token.recipient_email
        ).first()

        if not signature:
            return Response({
                "status": "error",
                "message": f"No signature assignment found for recipient {signing_token.recipient_email}."
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

        serializer = SignDocumentSerializer(
            data=request.data,
            context={'request': request, 'signer': signature.signer},
        )
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Validation failed",
                "data": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        signature_image_data = validated_data.get('signature_image', '')
        user_signature_id = validated_data.get('signature_id')

        field_values = request.data.get('field_values')
        if isinstance(field_values, dict):
            for field_id, val in field_values.items():
                Field.objects.filter(envelope=envelope, id=field_id, assigned_signer=signature.signer).update(value=val)
        elif isinstance(field_values, list):
            for item in field_values:
                if isinstance(item, dict) and 'id' in item and 'value' in item:
                    Field.objects.filter(envelope=envelope, id=item['id'], assigned_signer=signature.signer).update(value=item['value'])

        fallback_placement = {
            'page': validated_data.get('page', 1),
            'x': validated_data.get('x', 100),
            'y': validated_data.get('y', 100),
            'width': validated_data.get('width', 120),
            'height': validated_data.get('height', 40),
        }

        with transaction.atomic():
            signature = Signature.objects.select_for_update().get(pk=signature.pk)
            if signature.is_signed:
                return Response({
                    "status": "success",
                    "message": "Document signed successfully",
                    "data": SignatureSerializer(signature).data
                }, status=status.HTTP_200_OK)

            job = create_and_enqueue_signing_job(
                envelope=envelope,
                signer=signature.signer,
                signature=signature,
                signature_image_data=signature_image_data,
                user_signature_id=user_signature_id,
                fallback_placement=fallback_placement,
                request=request,
            )
            mark_token_used(signing_token)

        from audit.utils import log_action
        log_action(
            signature.signer,
            "SIGN_ENVELOPE_PUBLIC",
            envelope,
            f"Signer {signing_token.recipient_email} executed signature via token {signing_token.id} (job={job.id}).",
            request=request,
        )

        return Response({
            "status": "success",
            "message": "Signing job queued",
            "data": signing_job_response_data(job),
        }, status=status.HTTP_202_ACCEPTED)


class DeclineSignaturePublicView(APIView):
    """
    Public API view for declining to sign an envelope using a SigningToken.

    Endpoint: POST /signatures/{envelope_id}/decline-public/
    """
    permission_classes = [AllowAny]

    def post(self, request, envelope_id):
        from envelopes.models import Envelope
        from envelopes.services.signing_token import validate_signing_token, revoke_envelope_tokens

        token_str = (
            request.data.get("token")
            or request.query_params.get("token")
            or request.headers.get("X-Signing-Token")
        )
        signing_token, error_code, error_message = validate_signing_token(token_str, envelope_id=str(envelope_id))
        if error_code:
            status_code = status.HTTP_410_GONE if error_code == "TOKEN_EXPIRED" else status.HTTP_403_FORBIDDEN
            if error_code in ("MISSING_TOKEN", "INVALID_TOKEN"):
                status_code = status.HTTP_400_BAD_REQUEST
            return Response({"status": "error", "code": error_code, "message": error_message}, status=status_code)

        envelope = get_object_or_404(Envelope, pk=envelope_id)
        if envelope.status != "pending":
            return Response({
                "status": "error",
                "message": f"Only pending envelopes can be declined. Current status: {envelope.status}"
            }, status=status.HTTP_400_BAD_REQUEST)

        signature = envelope.signatures.filter(
            signer__email__iexact=signing_token.recipient_email
        ).first()

        if not signature:
            return Response({
                "status": "error",
                "message": "No signature assignment found for this recipient."
            }, status=status.HTTP_403_FORBIDDEN)

        decline_message = request.data.get('decline_message', 'Declined via public signing link.')
        signature.status = "declined"
        signature.save(update_fields=['status'])

        envelope.status = "rejected"
        envelope.save(update_fields=['status', 'updated_at'])

        revoke_envelope_tokens(envelope)

        from audit.utils import log_action
        log_action(
            signature.signer,
            "DECLINE_ENVELOPE_PUBLIC",
            envelope,
            f"Signer {signing_token.recipient_email} declined envelope '{envelope.name}' via token {signing_token.id}. Reason: {decline_message}",
            request=request,
        )

        return Response({
            "status": "success",
            "message": "Envelope declined successfully",
            "data": {
                "envelope_id": str(envelope.id),
                "status": envelope.status,
            }
        }, status=status.HTTP_200_OK)


class SigningJobPublicDetailView(APIView):
    """
    Public API view for polling an async signing job via SigningToken.

    Endpoint: GET /signatures/jobs/{id}/public/?token={token}
    """
    permission_classes = [AllowAny]

    def get(self, request, id):
        from envelopes.services.signing_token import validate_signing_token

        job = get_object_or_404(
            SigningJob.objects.select_related("envelope", "signer", "signature"),
            pk=id,
        )
        token_str = request.query_params.get("token") or request.headers.get("X-Signing-Token")
        signing_token, error_code, error_message = validate_signing_token(token_str, allow_used=True)

        if not signing_token or str(signing_token.envelope_id) != str(job.envelope_id):
            return Response({
                "status": "error",
                "message": "Valid signing token required for this job.",
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = SigningJobSerializer(job)
        return Response({
            "status": "success",
            "data": serializer.data,
        })


class PublicUserSignatureListView(APIView):
    """
    Public API view for loading and creating saved signatures for the recipient linked to a SigningToken.

    Endpoint: GET/POST /signatures/me/public/?token={token}
    """
    permission_classes = [AllowAny]

    def _resolve_token_and_user(self, request, *, allow_used: bool = False):
        from envelopes.services.signing_token import validate_signing_token
        from django.contrib.auth import get_user_model

        token_str = (
            request.query_params.get("token")
            or request.headers.get("X-Signing-Token")
            or request.data.get("token")
        )
        signing_token, error_code, error_message = validate_signing_token(token_str, allow_used=allow_used)
        if error_code:
            status_code = status.HTTP_410_GONE if error_code == "TOKEN_EXPIRED" else status.HTTP_403_FORBIDDEN
            if error_code in ("MISSING_TOKEN", "INVALID_TOKEN"):
                status_code = status.HTTP_400_BAD_REQUEST
            return None, None, Response(
                {"status": "error", "code": error_code, "message": error_message},
                status=status_code,
            )

        user = signing_token.recipient_user
        if not user and signing_token.recipient_email:
            User = get_user_model()
            user = User.objects.filter(email__iexact=signing_token.recipient_email).first()
            if user and not signing_token.recipient_user_id:
                signing_token.recipient_user = user
                signing_token.save(update_fields=["recipient_user"])

        return signing_token, user, None

    def get(self, request):
        _, recipient_user, error_response = self._resolve_token_and_user(request, allow_used=True)
        if error_response:
            return error_response

        if not recipient_user:
            return Response({"status": "success", "data": []}, status=status.HTTP_200_OK)

        signatures = UserSignature.objects.filter(user=recipient_user).order_by("-is_default", "-created_at")
        serializer = UserSignatureSerializer(signatures, many=True)
        return Response({"status": "success", "data": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        signing_token, recipient_user, error_response = self._resolve_token_and_user(request)
        if error_response:
            return error_response

        if not recipient_user:
            return Response(
                {
                    "status": "error",
                    "message": "Unable to associate signature with recipient user account.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = UserSignatureSerializer(
            data=request.data,
            context={"request": request, "user": recipient_user},
        )
        serializer.is_valid(raise_exception=True)
        signature = serializer.save()

        from audit.utils import log_action
        log_action(
            recipient_user,
            "CREATE_USER_SIGNATURE",
            signature,
            f"User {recipient_user.full_name or recipient_user.email} uploaded a signature via signing token {signing_token.id}.",
            request=request,
        )

        return Response(
            {
                "status": "success",
                "message": "Signature created successfully",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )
