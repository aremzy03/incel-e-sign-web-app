"""
Global search across the envelopes and documents the user can access.

GET /api/search/?q=<text>&limit=<n>

Envelopes: those the user created or signs (``get_envelopes_accessible_by_user``),
matched on name, description, creator name/email, document file names and
signer name/email. Documents: the user's own, matched on file name.
"""

from __future__ import annotations

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import Document
from envelopes.models import Envelope
from envelopes.utils.queryset import get_envelopes_accessible_by_user

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 100
DEFAULT_LIMIT = 5
MAX_LIMIT = 20


def _parse_limit(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, value))


def _envelope_match(envelope: Envelope, term: str) -> str:
    """Which part of the envelope matched, so the UI can explain the hit."""
    lowered = term.lower()
    if lowered in (envelope.name or '').lower():
        return 'name'
    if lowered in (envelope.description or '').lower():
        return 'description'
    for env_doc in envelope.envelopedocument_set.all():
        if lowered in (env_doc.document.file_name or '').lower():
            return 'document'
    creator = envelope.creator
    if creator and (lowered in (creator.full_name or '').lower() or lowered in (creator.email or '').lower()):
        return 'creator'
    return 'signer'


class GlobalSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        term = (request.query_params.get('q') or '').strip()[:MAX_QUERY_LENGTH]
        limit = _parse_limit(request.query_params.get('limit'))
        if len(term) < MIN_QUERY_LENGTH:
            return Response(
                {
                    'status': 'error',
                    'message': f'Type at least {MIN_QUERY_LENGTH} characters to search.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user

        envelope_matches = (
            get_envelopes_accessible_by_user(user)
            .filter(
                Q(name__icontains=term)
                | Q(description__icontains=term)
                | Q(creator__full_name__icontains=term)
                | Q(creator__email__icontains=term)
                | Q(envelopedocument_set__document__file_name__icontains=term)
                | Q(signatures__signer__full_name__icontains=term)
                | Q(signatures__signer__email__icontains=term)
            )
            .distinct()
        )
        envelope_total = envelope_matches.count()
        envelopes = list(
            Envelope.objects.filter(pk__in=envelope_matches.values('pk'))
            .select_related('creator')
            .prefetch_related('envelopedocument_set__document')
            .order_by('-updated_at')[:limit]
        )

        document_matches = Document.objects.filter(owner=user, file_name__icontains=term)
        document_total = document_matches.count()
        documents = list(document_matches.order_by('-updated_at')[:limit])

        return Response(
            {
                'status': 'success',
                'data': {
                    'query': term,
                    'envelopes': [
                        {
                            'id': str(envelope.id),
                            'name': envelope.name,
                            'status': envelope.status,
                            'is_self_sign': envelope.is_self_sign,
                            'role': 'creator' if envelope.creator_id == user.id else 'signer',
                            'document_names': [
                                env_doc.document.file_name for env_doc in envelope.envelopedocument_set.all()
                            ][:3],
                            'matched_on': _envelope_match(envelope, term),
                            'updated_at': envelope.updated_at,
                        }
                        for envelope in envelopes
                    ],
                    'documents': [
                        {
                            'id': str(document.id),
                            'file_name': document.file_name,
                            'status': document.status,
                            'updated_at': document.updated_at,
                        }
                        for document in documents
                    ],
                    'totals': {'envelopes': envelope_total, 'documents': document_total},
                },
            }
        )
