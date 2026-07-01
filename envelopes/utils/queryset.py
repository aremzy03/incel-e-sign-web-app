"""
Queryset helpers for envelope access control and performance.

Provides database-level filtering for envelopes visible to a user, with a
SQLite-compatible fallback used during tests.
"""

from django.conf import settings
from django.db.models import Q

from envelopes.models import Envelope


def _uses_sqlite() -> bool:
    """Return True when the default database backend is SQLite."""
    engine = settings.DATABASES['default']['ENGINE']
    return 'sqlite' in engine


def get_envelopes_accessible_by_user(user):
    """
    Return envelopes the user may access (creator or assigned signer).

    Uses PostgreSQL JSON containment and signature relations in production.
    Falls back to an in-Python filter on SQLite (test suite).
    """
    if _uses_sqlite():
        return _accessible_envelopes_sqlite(user)
    return _accessible_envelopes_postgres(user)


def _accessible_envelopes_postgres(user):
    """Database-level access filter for PostgreSQL and other JSON-capable backends."""
    user_id_str = str(user.id)
    return (
        Envelope.objects.filter(
            Q(creator=user)
            | Q(signatures__signer=user)
            | Q(signing_order__contains=[{'signer_id': user_id_str}])
        )
        .distinct()
    )


def _accessible_envelopes_sqlite(user):
    """
    SQLite-compatible access filter.

    Compares creator_id in Python to avoid lazy-loading creator rows.
    """
    accessible_pks = []
    for envelope in Envelope.objects.only('pk', 'creator_id', 'signing_order'):
        if envelope.creator_id == user.id:
            accessible_pks.append(envelope.pk)
            continue
        for signer_entry in envelope.signing_order or []:
            if str(signer_entry.get('signer_id')) == str(user.id):
                accessible_pks.append(envelope.pk)
                break
    return Envelope.objects.filter(pk__in=accessible_pks)


def prefetch_envelope_list(queryset):
    """Apply select/prefetch related optimizations for list responses."""
    return queryset.select_related('creator').prefetch_related('signatures__signer')


def prefetch_envelope_detail(queryset):
    """Apply select/prefetch related optimizations for detail responses."""
    return queryset.select_related('creator').prefetch_related(
        'signatures__signer',
        'envelopedocument_set__document',
        'fields__assigned_signer',
    )
