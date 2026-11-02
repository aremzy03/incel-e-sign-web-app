"""
Helpers for reading integration JWT claims from authenticated requests.

Used by audit enrichment on envelope create/send. Never logs tokens.
"""

from __future__ import annotations


def get_jwt_client_id(request) -> str | None:
    """
    Return ``client_id`` from the SimpleJWT access token when present.

    Safe for non-integration requests: missing auth or claim returns None.

    Args:
        request: DRF request whose ``auth`` may be an AccessToken.

    Returns:
        str | None: The integration client_id claim, or None.
    """
    if request is None:
        return None
    auth = getattr(request, "auth", None)
    if auth is None:
        return None
    try:
        value = auth["client_id"]
    except (KeyError, TypeError, AttributeError):
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def enrich_message_with_client_id(message: str, request) -> str:
    """
    Append ``client_id=...`` to an audit message when the JWT has that claim.

    Args:
        message: Base audit message.
        request: Optional request carrying a SimpleJWT token.

    Returns:
        str: Original message, or message plus client_id suffix.
    """
    client_id = get_jwt_client_id(request)
    if not client_id:
        return message
    return f"{message} [client_id={client_id}]"
