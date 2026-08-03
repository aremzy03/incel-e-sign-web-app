"""
Token exchange service for first-party integrations.

Verifies client credentials, optionally enforces IP allowlists, resolves
(or JIT-creates) the asserted user, upserts IntegrationUserLink when an
external_user_id is provided, and issues SimpleJWT tokens with integration
audit claims. Never logs raw client secrets or full tokens.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from audit.utils import log_action
from integrations.models import Integration
from integrations.services.credentials import verify_client_secret
from integrations.services.ip_allowlist import ip_is_allowed
from integrations.services.user_links import upsert_integration_user_link
from integrations.services.users import resolve_user_for_integration

logger = logging.getLogger(__name__)


class InvalidClientError(Exception):
    """Raised for unknown, inactive, or bad-secret client credentials."""


class ClientIpNotAllowedError(Exception):
    """Raised when the request IP is outside the integration allowlist."""


def exchange_token(
    *,
    client_id: str,
    client_secret: str,
    email: str,
    full_name: str | None = None,
    external_user_id: str | None = None,
    client_ip: str | None = None,
    request=None,
) -> dict[str, Any]:
    """
    Exchange integration credentials + user identity for a user-scoped JWT.

    Args:
        client_id: Public integration identifier.
        client_secret: Raw client secret from the partner (never logged).
        email: Email of the e-sign user to act as.
        full_name: Optional name for JIT create / empty-name fill.
        external_user_id: Optional partner user id; upserts IntegrationUserLink.
        client_ip: Observed client IP for optional allowlist enforcement.
        request: Optional HTTP request for audit IP/UA capture.

    Returns:
        dict: ``access``, ``refresh``, and ``user`` payload for the API response.

    Raises:
        InvalidClientError: Unknown client, inactive integration, or bad secret.
        ClientIpNotAllowedError: Non-empty allowlist and IP not permitted.
        UserNotFoundError: User missing and JIT create disabled.
        UserInactiveError: Resolved user is inactive.
    """
    integration = _authenticate_integration(client_id, client_secret)
    _assert_client_ip_allowed(integration, client_ip)

    user, _created = resolve_user_for_integration(
        email=email,
        full_name=full_name,
        allow_jit_create=integration.allow_jit_user_create,
    )

    if external_user_id and str(external_user_id).strip():
        upsert_integration_user_link(
            integration=integration,
            user=user,
            external_user_id=str(external_user_id).strip(),
        )

    access, refresh = _issue_tokens(user, integration)
    _log_token_exchange_audit(user, integration, request)

    logger.info(
        "Integration token issued client_id=%s user_id=%s",
        integration.client_id,
        user.id,
    )
    return {
        "access": access,
        "refresh": refresh,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
        },
    }


def _authenticate_integration(client_id: str, client_secret: str) -> Integration:
    """
    Load and verify an active integration by client credentials.

    Unknown, inactive, and bad-secret cases all map to InvalidClientError
    so partners cannot distinguish them.
    """
    try:
        integration = Integration.objects.get(client_id=client_id)
    except Integration.DoesNotExist as exc:
        logger.warning("Token exchange rejected: unknown client_id")
        raise InvalidClientError("Invalid client credentials.") from exc

    if not integration.is_active:
        logger.warning(
            "Token exchange rejected: inactive client_id=%s",
            integration.client_id,
        )
        raise InvalidClientError("Invalid client credentials.")

    if not verify_client_secret(client_secret, integration.client_secret_hash):
        logger.warning(
            "Token exchange rejected: bad secret for client_id=%s",
            integration.client_id,
        )
        raise InvalidClientError("Invalid client credentials.")

    return integration


def _assert_client_ip_allowed(integration: Integration, client_ip: str | None) -> None:
    """
    Reject the exchange when a non-empty allowlist does not include client_ip.

    Empty ``allowed_cidrs`` preserves open behavior (allow all).
    """
    if ip_is_allowed(client_ip, integration.allowed_cidrs):
        return
    logger.warning(
        "Token exchange rejected: IP not allowed client_id=%s",
        integration.client_id,
    )
    raise ClientIpNotAllowedError("Client IP is not allowed for this integration.")


def _integration_access_token_lifetime() -> timedelta:
    """Return the configured shorter lifetime for integration access tokens."""
    configured = getattr(settings, "INTEGRATION_ACCESS_TOKEN_LIFETIME", None)
    if isinstance(configured, timedelta):
        return configured
    return timedelta(minutes=30)


def _issue_tokens(user, integration: Integration) -> tuple[str, str]:
    """
    Issue SimpleJWT refresh/access tokens with integration claims.

    Mirrors LoginView / Google OAuth issuance via RefreshToken.for_user,
    attaches ``client_id`` and ``auth_via``, then shortens access expiry via
    ``INTEGRATION_ACCESS_TOKEN_LIFETIME``.
    """
    refresh = RefreshToken.for_user(user)
    refresh["client_id"] = integration.client_id
    refresh["auth_via"] = "integration"

    access = refresh.access_token
    # Explicitly mirror claims on access for forensic/audit middleware.
    access["client_id"] = integration.client_id
    access["auth_via"] = "integration"
    access.set_exp(
        from_time=timezone.now(),
        lifetime=_integration_access_token_lifetime(),
    )

    return str(access), str(refresh)


def _log_token_exchange_audit(user, integration: Integration, request) -> None:
    """
    Record INTEGRATION_TOKEN_EXCHANGE with actor=user and client_id in message.

    AuditLog has no metadata JSON field; client_id is embedded in ``message``.
    Failures are swallowed by log_action itself.
    """
    log_action(
        user,
        "INTEGRATION_TOKEN_EXCHANGE",
        integration,
        (
            f"Integration token issued for user {user.email} "
            f"[client_id={integration.client_id}]"
        ),
        request=request,
    )
