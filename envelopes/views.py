"""
Views for the envelopes app.

This module defines API views for envelope-related operations
in the e-signature workflow.
"""

from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView, DestroyAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.http import Http404 # Import Http404
from .models import Envelope
from .serializers import EnvelopeCreateSerializer, EnvelopeDetailSerializer, EnvelopeSerializer, EnvelopeUpdateSerializer
from documents.serializers import DocumentSerializer
from .serializers import EnvelopeDocumentSerializer
from django.conf import settings # Import settings


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
            
            # Log the envelope creation action
            from audit.utils import log_action
            log_action(
                request.user, 
                "CREATE_ENVELOPE", 
                envelope, 
                f"User {request.user.full_name or request.user.username} created envelope '{envelope.name}' with {envelope.envelopedocument_set.count()} documents.", 
                request=request
            )
            
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
    Changes status from "draft" to "pending".
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """
        Send an envelope (change status from draft to pending).
        
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
        
        # Check if envelope is in draft or rejected status
        if envelope.status not in ["draft", "rejected"]:
            return Response({
                "status": "error",
                "message": f"Only draft or rejected envelopes can be sent. Current status: {envelope.status}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # If the envelope was rejected, reset it to draft before sending
        if envelope.status == "rejected":
            envelope.status = "draft"
            envelope.save()

        # Update envelope status to pending
        envelope.status = "pending"
        envelope.save()

        # Update the status of all documents in this envelope to 'sent'
        for envelope_document in envelope.envelopedocument_set.all():
            document = envelope_document.document
            document.status = "sent"
            document.save()
            
        # Log the envelope send action
        from audit.utils import log_action
        log_action(
            request.user, 
            "SEND_ENVELOPE", 
            envelope, 
            f"User {request.user.full_name or request.user.username} sent envelope '{envelope.name}' with {envelope.envelopedocument_set.count()} documents.", 
            request=request
        )
        
        # Create Signature records for each signer in signing_order
        from signatures.models import Signature
        from django.contrib.auth import get_user_model
        from notifications.utils import create_notification, create_envelope_sent_notification
        from notifications.tasks import send_envelope_assigned_email_task
        
        User = get_user_model()
        
        # Notify first signer
        if envelope.signing_order:
            first_signer_id = envelope.signing_order[0]['signer_id']
            try:
                first_signer = User.objects.get(id=first_signer_id)
                message = create_envelope_sent_notification(envelope)
                # utils.create_notification proxies to Celery task; no need to call .delay here
                create_notification(str(first_signer.id), message)
                # Send assignment email to first signer
                try:
                    recipient_email = getattr(first_signer, 'email', None)
                    if recipient_email:
                        # Generate the sign document URL
                        sign_document_url = f"{settings.FRONTEND_BASE_URL}/dashboard/envelopes/{envelope.id}/sign"
                        send_envelope_assigned_email_task.delay(
                            recipient_email,
                            request.user.full_name or request.user.username,
                            envelope.name,
                            sign_document_url # Pass the generated URL
                        )
                except Exception as e:
                    # Log email sending error but don't block the main process
                    print(f"Error sending envelope assigned email: {e}")
                    # TODO: Add proper logging here. (AR 2025-10-17)
            except User.DoesNotExist:
                # This case should ideally not happen if signing_order is well-formed
                pass
        
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
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"User {signer_id} not found when creating signature for envelope {envelope.id}")
                continue
            except Exception as e:
                # Log any other errors during signature creation
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error creating signature for user {signer_id} in envelope {envelope.id}: {e}")
                continue
        
        # Verify that Signature records were created
        created_signatures = Signature.objects.filter(envelope=envelope).count()
        expected_signatures = len(envelope.signing_order)
        
        if created_signatures != expected_signatures:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Signature creation mismatch: expected {expected_signatures}, created {created_signatures} for envelope {envelope.id}")
        
        # Return updated envelope details
        detail_serializer = EnvelopeDetailSerializer(envelope)
        
        return Response({
            "status": "success",
            "message": "Envelope sent successfully",
            "data": detail_serializer.data
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

        # Update the status of all documents in this envelope to 'rejected'
        for envelope_document in envelope.envelopedocument_set.all():
            document = envelope_document.document
            document.status = "rejected"
            document.save()
        
        # Log the envelope rejection action
        from audit.utils import log_action
        log_action(
            request.user, 
            "REJECT_ENVELOPE", 
            envelope, 
            f"User {request.user.full_name or request.user.username} rejected envelope '{envelope.name}' with {envelope.envelopedocument_set.count()} documents.", 
            request=request
        )
        
        # Notify all signers about rejection
        from django.contrib.auth import get_user_model
        from notifications.utils import create_notification, create_envelope_rejected_notification
        
        User = get_user_model()
        
        message = create_envelope_rejected_notification(envelope)
        for signer_entry in envelope.signing_order:
            signer_id = signer_entry['signer_id']
            try:
                signer = User.objects.get(id=signer_id)
                create_notification(str(signer.id), message)
            except User.DoesNotExist:
                continue
        
        # Return updated envelope details
        detail_serializer = EnvelopeDetailSerializer(envelope)
        
        return Response({
            "status": "success",
            "message": "Envelope rejected successfully",
            "data": detail_serializer.data
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
    serializer_class = EnvelopeDetailSerializer # Use EnvelopeDetailSerializer
    
    def get_queryset(self):
        """
        Return envelopes where the user is either the creator or a signer.
        """
        user = self.request.user
        print(f"DEBUG: Filtering queryset for user: {user.id}") # Debug print
        
        # Fetch all envelopes and filter in Python due to SQLite's
        # limited JSONField __contains lookup support in testing.
        # In production with PostgreSQL, Q(signing_order__contains=...) would be preferred.
        # Filter first, then order and prefetch
        all_envelopes = Envelope.objects.all()
        
        filtered_envelopes_pks = set()
        for envelope in all_envelopes:
            if envelope.creator == user:
                filtered_envelopes_pks.add(envelope.pk)
                continue
            for signer_entry in envelope.signing_order:
                if str(signer_entry.get('signer_id')) == str(user.id):
                    filtered_envelopes_pks.add(envelope.pk)
                    break
        
        # Convert the filtered list back to a queryset
        queryset = Envelope.objects.filter(pk__in=list(filtered_envelopes_pks)).order_by('-created_at')
        queryset = queryset.select_related('creator').prefetch_related('signatures', 'envelopedocument_set__document')
        
        print(f"DEBUG (List View - filtered): Queryset count: {queryset.count()}") # Debug print
        return queryset
    
    def list(self, request, *args, **kwargs):
        """
        Override list to return custom response format.
        """
        queryset = self.get_queryset()
        print(f"DEBUG: EnvelopeListView queryset count: {queryset.count()}") # Debug print
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
    serializer_class = EnvelopeDetailSerializer # Use detail serializer
    lookup_field = 'pk'
    
    def get_queryset(self):
        """
        Return envelopes where the user is either the creator or a signer.
        """
        user = self.request.user
        print(f"DEBUG: Filtering queryset for user: {user.id}") # Debug print
        
        # Fetch all relevant envelopes and filter in Python due to SQLite's
        # limited JSONField __contains lookup support in testing.
        # In production with PostgreSQL, Q(signing_order__contains=...) would be preferred.
        all_envelopes = Envelope.objects.all()
        
        filtered_envelopes_pks = set()
        for envelope in all_envelopes:
            if envelope.creator == user:
                filtered_envelopes_pks.add(envelope.pk)
                continue
            for signer_entry in envelope.signing_order:
                if str(signer_entry.get('signer_id')) == str(user.id):
                    filtered_envelopes_pks.add(envelope.pk)
                    break

        # Convert the filtered list back to a queryset
        queryset = Envelope.objects.filter(pk__in=list(filtered_envelopes_pks))
        queryset = queryset.select_related('creator').prefetch_related('signatures', 'envelopedocument_set__document')

        print(f"DEBUG (Detail View - filtered): Queryset for user {user.id} count: {queryset.count()}")
        print(f"DEBUG (Detail View - filtered): Queryset query: {queryset.query}")
        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        """
        Override retrieve to return custom response format and handle permissions.
        """
        # Use the optimized get_queryset and get_object for permission handling
        try:
            envelope = self.get_object() # get_object uses get_queryset
        except Http404: # get_object_or_404 raises Http404
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


class EnvelopeDocumentView(APIView):
    """
    API view for retrieving the document of a specific envelope.
    
    Endpoint: GET /envelopes/{id}/document/
    Requires authentication.
    Creator and assigned signers can access.
    Returns the document details serialized via DocumentSerializer.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """
        Retrieve the document attached to the given envelope if the user has access.
        
        Args:
            request: HTTP request
            pk: Envelope ID
            
        Returns:
            Response with document details or error message
        """
        # Check if envelope exists
        try:
            envelope = Envelope.objects.get(pk=pk)
        except Envelope.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Envelope not found or access denied"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check access (creator or listed signer)
        user = request.user
        has_access = envelope.creator == user
        if not has_access:
            for signer_entry in envelope.signing_order:
                if signer_entry.get('signer_id') == str(user.id):
                    has_access = True
                    break
        
        if not has_access:
            return Response({
                "status": "error",
                "message": "Envelope not found or access denied"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Serialize and return all documents in the envelope
        # Use EnvelopeDocumentSerializer for each EnvelopeDocument instance
        documents_in_envelope = envelope.envelopedocument_set.all()
        doc_serializer = EnvelopeDocumentSerializer(documents_in_envelope, many=True)
        return Response({
            "status": "success",
            "message": "Envelope documents retrieved successfully",
            "data": doc_serializer.data
        }, status=status.HTTP_200_OK)

class EnvelopeDeleteView(DestroyAPIView):
    """
    API view for deleting an envelope.
    
    Users can only delete envelopes they created.
    Returns 404 Not Found if envelope doesn't exist or user is not the creator.
    Requires authentication.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Return envelopes created by the authenticated user.
        
        Returns:
            QuerySet: Envelopes created by the current user
        """
        return Envelope.objects.filter(creator=self.request.user)
    
    def get_object(self):
        """
        Get the envelope object, ensuring user can only delete envelopes they created.
        
        Returns:
            Envelope: The requested envelope
            
        Raises:
            Http404: If envelope doesn't exist or user is not the creator
        """
        queryset = self.get_queryset()
        envelope_id = self.kwargs.get('pk')
        return get_object_or_404(queryset, id=envelope_id)
    
    def destroy(self, request, *args, **kwargs):
        """
        Delete the envelope and return appropriate response.
        
        Args:
            request: HTTP request
            *args: Additional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            Response: 204 No Content on successful deletion
        """
        try:
            envelope = self.get_object()
            
            # Log the envelope deletion action
            from audit.utils import log_action
            log_action(
                request.user, 
                "DELETE_ENV", 
                envelope, 
                f"User {request.user.full_name or request.user.username} deleted envelope '{envelope.name}' with {envelope.envelopedocument_set.count()} documents.", 
                request=request
            )
            
            envelope.delete()
            return Response(
                {
                    'status': 'success',
                    'message': 'Envelope deleted successfully'
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
                    'message': f'Error deleting envelope: {str(e)}'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EnvelopeEditView(APIView):
    """
    API view for editing draft envelopes.
    
    Endpoint: PATCH /envelopes/{id}/edit/
    Requires authentication. Only the envelope creator can edit.
    Only envelopes in status "draft" can be edited.
    Accepts payload: { signing_order: [ { signer_id, order }, ... ] }
    Returns updated envelope details.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        envelope = get_object_or_404(Envelope, pk=pk)

        if envelope.creator != request.user:
            return Response({
                "status": "error",
                "message": "You can only edit envelopes you created."
            }, status=status.HTTP_403_FORBIDDEN)

        if envelope.status not in ["draft", "rejected"]:
            return Response({
                "status": "error",
                "message": f"Only draft or rejected envelopes can be edited. Current status: {envelope.status}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = EnvelopeUpdateSerializer(
            instance=envelope,
            data=request.data,
            partial=True,
            context={"request": request}
        )

        if serializer.is_valid():
            updated_envelope = serializer.save()

            # If the envelope was previously rejected, revert to draft status so it can be re-sent
            if envelope.status == "rejected":
                updated_envelope.status = "draft"
                updated_envelope.save(update_fields=['status', 'updated_at'])

            from audit.utils import log_action
            log_action(
                request.user,
                "EDIT_ENVELOPE",
                updated_envelope,
                f"User {request.user.full_name or request.user.username} edited envelope '{updated_envelope.name}' with {updated_envelope.envelopedocument_set.count()} documents.",
                request=request
            )

            response_serializer = EnvelopeDetailSerializer(updated_envelope)
            return Response({
                "status": "success",
                "message": "Envelope updated successfully",
                "data": response_serializer.data
            }, status=status.HTTP_200_OK)

        return Response({
            "status": "error",
            "message": "Validation failed",
            "data": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
