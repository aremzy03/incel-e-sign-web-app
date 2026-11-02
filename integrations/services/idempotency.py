"""
Idempotency-Key helpers for envelope create/send and composite send.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.db import IntegrityError, transaction
from rest_framework.response import Response

from integrations.models import IdempotencyRecord

logger = logging.getLogger(__name__)

SCOPE_ENVELOPE_CREATE = "envelopes.create"
SCOPE_ENVELOPE_SEND = "envelopes.send"
SCOPE_INTEGRATIONS_ENVELOPE_SEND = "integrations.envelopes.send"


def _json_safe(value: Any) -> Any:
    """
    Recursively coerce values so Django JSONField / json.dumps can store them.

    DRF serializer ``.data`` may still contain UUID/datetime objects.
    """
    return json.loads(json.dumps(value, default=str))


def get_idempotency_key(request) -> str | None:
    """
    Read the Idempotency-Key header (case-insensitive via META).

    Returns:
        str | None: Stripped key, or None when absent/blank.
    """
    if request is None:
        return None
    raw = request.headers.get("Idempotency-Key") or request.META.get(
        "HTTP_IDEMPOTENCY_KEY"
    )
    if raw is None:
        return None
    key = str(raw).strip()
    return key or None


def lookup_idempotent_response(*, user, key: str, scope: str) -> Response | None:
    """
    Return a DRF Response when a prior success was stored for this key.

    Args:
        user: Authenticated user (actor).
        key: Idempotency-Key value.
        scope: Endpoint scope constant.

    Returns:
        Response | None: Cached response, or None to proceed with work.
    """
    record = IdempotencyRecord.objects.filter(
        user=user,
        key=key,
        scope=scope,
    ).first()
    if record is None:
        return None
    return Response(record.response_body, status=record.response_status)


def store_idempotent_response(
    *,
    user,
    key: str,
    scope: str,
    response_status: int,
    response_body: dict[str, Any],
    envelope_id=None,
) -> IdempotencyRecord | None:
    """
    Persist a successful response snapshot for future replays.

    Concurrent creates with the same key race to UniqueConstraint; the loser
    re-reads the winning row instead of inserting a duplicate outcome.

    Returns:
        IdempotencyRecord | None: Stored (or pre-existing) row.
    """
    try:
        with transaction.atomic():
            return IdempotencyRecord.objects.create(
                user=user,
                key=key,
                scope=scope,
                response_status=response_status,
                response_body=_json_safe(response_body),
                envelope_id=envelope_id,
            )
    except IntegrityError:
        existing = IdempotencyRecord.objects.filter(
            user=user,
            key=key,
            scope=scope,
        ).first()
        if existing is not None:
            return existing
        logger.exception(
            "Idempotency store failed without existing row scope=%s",
            scope,
        )
        return None
