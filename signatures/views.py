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
from .utils.pdf_signing import embed_signature, get_media_absolute_path_from_url
from django.conf import settings
import os


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
        
        # Check if envelope is in pending status
        if envelope.status != "pending":
            return Response({
                "status": "error",
                "message": f"Envelope must be in 'pending' status to sign. Current status: {envelope.status}"
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
            }, status=status.HTTP_403_FORBIDDEN) # Changed to 403 Forbidden
        
        # Check if already signed
        if signature.is_signed:
            return Response({
                "status": "error",
                "message": "You have already signed this document."
            }, status=status.HTTP_403_FORBIDDEN) # Changed to 403 Forbidden
        
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
        # The signature_image is now stored in the Signature model, so we don't update it on the document
        signature.signature_image = signature_image_data
        signature.save()
        
        # Process each document in the envelope for signature embedding
        from envelopes.models import EnvelopeDocument
        envelope_documents = EnvelopeDocument.objects.filter(envelope=envelope).order_by('order')
        
        if not envelope_documents.exists():
            return Response({
                "status": "error",
                "message": "No documents found in this envelope to sign."
            }, status=status.HTTP_400_BAD_REQUEST)

        for env_doc in envelope_documents:
            document = env_doc.document

            # Collect ALL signature positions for this specific document and signer
            signer_positions_for_doc = []
            for pos_entry in env_doc.signer_document_positions:
                if str(pos_entry.get('signer_id')) == str(request.user.id):
                    position = pos_entry.get('position')
                    if position:
                        signer_positions_for_doc.append(position)

            # Always start from the latest available file: previously signed version if present
            source_url = document.signed_file_url or document.file_url
            input_pdf_path = get_media_absolute_path_from_url(source_url)
            output_dir = os.path.join(str(settings.MEDIA_ROOT), 'signed_docs')
            os.makedirs(output_dir, exist_ok=True)
            output_pdf_path = os.path.join(output_dir, f"{document.id}_signed_{envelope.id}.pdf")

            # Ensure we have a local input PDF; download if it's a remote URL
            if not os.path.exists(input_pdf_path):
                try:
                    if isinstance(source_url, str) and (source_url.startswith('http://') or source_url.startswith('https://')):
                        import requests
                        tmp_dir = os.path.join(str(settings.MEDIA_ROOT), 'tmp')
                        os.makedirs(tmp_dir, exist_ok=True)
                        tmp_input = os.path.join(tmp_dir, f"{document.id}_current.pdf")
                        with requests.get(source_url, stream=True, timeout=15) as r:
                            r.raise_for_status()
                            with open(tmp_input, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                        input_pdf_path = tmp_input
                except Exception:
                    # If download fails, we will skip embedding below
                    pass

            # Try to embed signature; if it fails, continue workflow without blocking
            if os.path.exists(input_pdf_path):
                try:
                    # Process all positions for this signer on this document
                    if signer_positions_for_doc:
                        # Apply signature at each position sequentially
                        temp_files_to_cleanup = []
                        current_input_path = input_pdf_path
                        
                        for idx, position_data in enumerate(signer_positions_for_doc):
                            # Determine output path - final position uses final output, others use temp files
                            if idx == len(signer_positions_for_doc) - 1:
                                current_output_path = output_pdf_path
                            else:
                                current_output_path = f"{output_pdf_path}.tmp{idx}"
                                temp_files_to_cleanup.append(current_output_path)
                            
                            if position_data and isinstance(position_data, dict):
                                required_fields = ['page', 'x', 'y', 'width', 'height']
                                if all(field in position_data for field in required_fields):
                                    embed_signature(
                                        pdf_path=current_input_path,
                                        output_path=current_output_path,
                                        signature_image=signature_image_data,
                                        page=position_data['page'],
                                        x=position_data['x'],
                                        y=position_data['y'],
                                        width=position_data['width'],
                                        height=position_data['height'],
                                    )
                                    
                                    # Update input path for next iteration
                                    current_input_path = current_output_path
                                else:
                                    # Position is incomplete, skip this position
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.warning(f"Skipping incomplete position {idx} for document {document.id}: missing required fields")
                            else:
                                # Invalid position data, skip this position
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.warning(f"Skipping invalid position {idx} for document {document.id}: invalid position data")
                        
                        # Clean up temporary files
                        for temp_file in temp_files_to_cleanup:
                            try:
                                if os.path.exists(temp_file):
                                    os.remove(temp_file)
                            except Exception as e:
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")
                    else:
                        # No positions defined in EnvelopeDocument, use request data or defaults
                        embed_signature(
                            pdf_path=input_pdf_path,
                            output_path=output_pdf_path,
                            signature_image=signature_image_data,
                            page=validated_data.get('page', 1),
                            x=validated_data.get('x', 100),
                            y=validated_data.get('y', 100),
                            width=validated_data.get('width', 120),
                            height=validated_data.get('height', 40),
                        )
                    
                    relative_output = os.path.relpath(output_pdf_path, str(settings.MEDIA_ROOT))
                    new_signed_url = f"{settings.MEDIA_URL}{relative_output}"
                    # Update document with newly signed file URL
                    document.signed_file_url = new_signed_url
                    document.file_url = new_signed_url # Also update file_url to reflect latest signed version
                except Exception as e:
                    # On failure, proceed without blocking signing
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error embedding signature for document {document.id} in envelope {envelope.id}: {e}")
                    document.signed_file_url = document.signed_file_url or None
            else:
                # Could not obtain local source; keep existing URLs
                document.signed_file_url = document.signed_file_url or None
            
            document.save(update_fields=["signed_file_url", "file_url", "updated_at"])
        
        # Log the signature action
        from audit.utils import log_action
        log_action(
            request.user, 
            "SIGN_DOC", 
            signature, 
            f"User {request.user.full_name or request.user.username} signed envelope '{signature.envelope.name}' with {signature.envelope.envelopedocument_set.count()} documents.", 
            request=request
        )
        
        # Check if this was the last signer
        remaining_pending = Signature.objects.filter(
            envelope=envelope,
            status='pending'
        ).count()
        
        # Send notifications
        from notifications.utils import create_notification, create_envelope_completed_notification, create_signer_turn_notification
        from notifications.tasks import send_turn_to_sign_email_task
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        if remaining_pending == 0:
            # All signers have signed - mark envelope as completed
            envelope.status = "completed"
            envelope.save()

            # Update the status of all documents in this envelope to 'completed'
            for envelope_document in envelope.envelopedocument_set.all():
                document = envelope_document.document
                document.status = "completed"
                document.save()
            
            # Notify creator that envelope is completed
            message = create_envelope_completed_notification(envelope)
            # utils.create_notification proxies to Celery task; no need to call .delay here
            create_notification(str(envelope.creator.id), message)
        else:
            # Notify only the immediate next signer based on signing_order
            def get_order_for_signer_id(signer_id: str) -> int:
                """Return the order for a given signer_id using envelope.signing_order.
                Falls back to positional index if explicit 'order' is missing/invalid.
                """
                if not envelope.signing_order:
                    return 0
                for idx, signer_entry in enumerate(envelope.signing_order, 1):
                    if str(signer_entry.get('signer_id')) == str(signer_id):
                        explicit = signer_entry.get('order')
                        return explicit if isinstance(explicit, int) and explicit >= 1 else idx
                return 0

            current_order = signature.get_signing_order()

            # Determine the next signer_id with the minimal order greater than current
            next_signer_id = None
            next_order = None
            if envelope.signing_order:
                for signer_entry in envelope.signing_order:
                    candidate_id = signer_entry.get('signer_id')
                    candidate_order = get_order_for_signer_id(candidate_id)
                    if candidate_order > current_order and (next_order is None or candidate_order < next_order):
                        next_order = candidate_order
                        next_signer_id = candidate_id

            if next_signer_id is not None:
                next_signature = Signature.objects.filter(
                    envelope=envelope,
                    signer__id=next_signer_id,
                    status='pending'
                ).first()

            if next_signature:
                message = create_signer_turn_notification(envelope)
                create_notification(str(next_signature.signer.id), message)
                # Send turn-to-sign email to next signer
                try:
                    recipient_email = getattr(next_signature.signer, 'email', None)
                    if recipient_email:
                        send_turn_to_sign_email_task.delay(
                            recipient_email,
                            envelope.name, # Use envelope name
                            str(envelope.id) # Pass envelope ID for URL generation
                        )
                except Exception as e:
                    # Log the error but don't block the main process
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error sending turn-to-sign email: {e}")
                    # TODO: Add proper error handling and monitoring
        
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