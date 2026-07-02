"""
Views for the envelopes app.

This module defines API views for envelope-related operations
in the e-signature workflow.
"""

from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView, DestroyAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.http import Http404 # Import Http404
from .models import Envelope
from .serializers import (
    EnvelopeCreateSerializer,
    EnvelopeDetailSerializer,
    EnvelopeListSerializer,
    EnvelopeSerializer,
    EnvelopeUpdateSerializer,
    DashboardActivitySerializer,
)
from .utils import (
    get_envelopes_accessible_by_user,
    get_envelopes_where_user_is_current_signer,
    prefetch_envelope_detail,
    prefetch_envelope_list,
)
from audit.models import AuditLog
from documents.serializers import DocumentSerializer
from .serializers import EnvelopeDocumentSerializer
from core.query_filters import parse_boolean_query_param, parse_search_query_param, parse_status_query_param
from signatures.models import Signature


class EnvelopeListPagination(PageNumberPagination):
    """Page-number pagination for envelope list (uses global PAGE_SIZE defaults)."""

    page_size_query_param = 'page_size'
    max_page_size = 100


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

        # Block sends while async signing is in-flight for this envelope.
        from signatures.services.reset_workflow import (
            SigningWorkflowInProgressError,
            assert_no_inflight_signing_jobs,
            reset_signing_workflow,
        )
        try:
            assert_no_inflight_signing_jobs(envelope)
        except SigningWorkflowInProgressError as exc:
            return Response({
                "status": "error",
                "message": str(exc),
            }, status=status.HTTP_409_CONFLICT)
        
        # Check if user is the creator
        if envelope.creator != request.user:
            return Response({
                "status": "error",
                "message": "You can only send envelopes you created."
            }, status=status.HTTP_403_FORBIDDEN)

        if envelope.is_self_sign:
            return Response({
                "status": "error",
                "message": "Self-signed envelopes cannot be sent to recipients."
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        # Reset PDF/signature workflow state and rebuild signature rows.
        # This guarantees current_signer starts at the first signer after resend.
        reset_signing_workflow(envelope)

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
                        send_envelope_assigned_email_task.delay(
                            recipient_email,
                            request.user.full_name or request.user.username,
                            envelope.name,
                            str(envelope.id) # Pass envelope ID instead of URL
                        )
                except Exception as e:
                    # Log email sending error but don't block the main process
                    print(f"Error sending envelope assigned email: {e}")
                    # TODO: Add proper logging here. (AR 2025-10-17)
            except User.DoesNotExist:
                # This case should ideally not happen if signing_order is well-formed
                pass
        
        # Signature rows are rebuilt by reset_signing_workflow; nothing else to do here.
        
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
    Supports pagination via `page` and `page_size` query parameters.
    Optional query params: ``status`` (draft, pending, completed, self_signed, rejected),
    ``search`` (case-insensitive match on name, description, creator email),
    ``is_self_sign`` (true|false).
    Returns:
        - Envelopes created by request.user
        - Envelopes where request.user is a signer
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = EnvelopeListSerializer
    pagination_class = EnvelopeListPagination
    
    def get_queryset(self):
        """
        Return envelopes where the user is either the creator or a signer.
        """
        queryset = get_envelopes_accessible_by_user(self.request.user)

        status_value, _status_error = parse_status_query_param(
            self.request,
            Envelope.STATUS_CHOICES,
        )
        if status_value:
            queryset = queryset.filter(status=status_value)

        search_term = parse_search_query_param(self.request)
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term)
                | Q(description__icontains=search_term)
                | Q(creator__email__icontains=search_term)
                | Q(creator__full_name__icontains=search_term)
            )

        is_self_sign_value, _is_self_sign_error = parse_boolean_query_param(
            self.request,
            'is_self_sign',
        )
        if is_self_sign_value is True:
            queryset = queryset.filter(is_self_sign=True)
        elif is_self_sign_value is False:
            queryset = queryset.filter(is_self_sign=False)

        return prefetch_envelope_list(queryset).order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        """
        Override list to return custom response format with pagination metadata.
        """
        status_value, status_error = parse_status_query_param(
            request,
            Envelope.STATUS_CHOICES,
        )
        if status_error:
            return Response({
                "status": "error",
                "message": status_error,
                "data": {"status": status_error},
            }, status=status.HTTP_400_BAD_REQUEST)

        is_self_sign_value, is_self_sign_error = parse_boolean_query_param(
            request,
            'is_self_sign',
        )
        if is_self_sign_error:
            return Response({
                "status": "error",
                "message": is_self_sign_error,
                "data": {"is_self_sign": is_self_sign_error},
            }, status=status.HTTP_400_BAD_REQUEST)

        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                "status": "success",
                "message": "Envelopes retrieved successfully",
                "data": paginated_response.data,
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "status": "success",
            "message": "Envelopes retrieved successfully",
            "data": {
                "count": queryset.count(),
                "next": None,
                "previous": None,
                "results": serializer.data,
            },
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
        queryset = get_envelopes_accessible_by_user(self.request.user)
        return prefetch_envelope_detail(queryset)
    
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

        # Block edits while async signing is in-flight for this envelope.
        from signatures.services.reset_workflow import (
            SigningWorkflowInProgressError,
            assert_no_inflight_signing_jobs,
        )
        try:
            assert_no_inflight_signing_jobs(envelope)
        except SigningWorkflowInProgressError as exc:
            return Response({
                "status": "error",
                "message": str(exc),
            }, status=status.HTTP_409_CONFLICT)

        if envelope.creator != request.user:
            return Response({
                "status": "error",
                "message": "You can only edit envelopes you created."
            }, status=status.HTTP_403_FORBIDDEN)

        if envelope.is_self_sign:
            return Response({
                "status": "error",
                "message": "Self-signed envelopes cannot be edited."
            }, status=status.HTTP_400_BAD_REQUEST)

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


DASHBOARD_ACTIVITY_ACTIONS = (
    'SEND_ENVELOPE',
    'SIGN_DOC',
    'SELF_SIGN_DOC',
    'REJECT_ENVELOPE',
    'DECLINE_SIGN',
)


def _parse_dashboard_limit(request, param_name, default):
    """Parse a bounded positive integer query parameter for dashboard lists."""
    raw_value = request.query_params.get(param_name, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 100))


class EnvelopeDashboardView(APIView):
    """
    API view providing an aggregated dashboard for the authenticated user.

    Endpoint: GET /envelopes/dashboard/
    Deprecated alias: GET /envelopes/metrics/
    Requires authentication.
    Returns legacy metrics, envelope counts, action-required envelopes, and recent activity.

    action_required includes envelopes with status ``pending`` where the authenticated
    user is the current signer (next signer in the signing order). Self-signed envelopes
    are excluded.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return a dashboard summary for the current user."""
        user = request.user
        action_required_limit = _parse_dashboard_limit(request, 'action_required_limit', 10)
        activity_limit = _parse_dashboard_limit(request, 'activity_limit', 5)

        documents_signed = Signature.objects.filter(
            signer=user,
            status='signed',
        ).count()

        pending_signatures = Signature.objects.filter(
            signer=user,
            status='pending',
        ).count()

        user_envelopes = Envelope.objects.filter(creator=user)
        active_envelopes = user_envelopes.filter(status__in=['draft', 'pending']).count()
        completed_envelopes = user_envelopes.filter(status='completed').count()
        total_envelopes = user_envelopes.count()

        completion_rate = 0.0
        if total_envelopes:
            completion_rate = round((completed_envelopes / total_envelopes) * 100, 2)

        action_required_all = get_envelopes_where_user_is_current_signer(user)
        action_required = EnvelopeListSerializer(
            action_required_all[:action_required_limit],
            many=True,
            context={'request': request},
        ).data

        recent_activity = [
            DashboardActivitySerializer.from_audit_log(log)
            for log in AuditLog.objects.filter(
                actor=user,
                action__in=DASHBOARD_ACTIVITY_ACTIONS,
            ).select_related('target_content_type').order_by('-created_at')[:activity_limit]
        ]

        return Response({
            "status": "success",
            "message": "Dashboard retrieved successfully",
            "data": {
                "metrics": {
                    "documents_signed": documents_signed,
                    "pending_signatures": pending_signatures,
                    "active_envelopes": active_envelopes,
                    "completion_rate": completion_rate,
                },
                "counts": {
                    "pending_my_signature": len(action_required_all),
                    "pending_sent": user_envelopes.filter(status='pending').count(),
                    "completed": completed_envelopes,
                    "draft": user_envelopes.filter(status='draft').count(),
                },
                "action_required": action_required,
                "recent_activity": recent_activity,
            },
        }, status=status.HTTP_200_OK)
