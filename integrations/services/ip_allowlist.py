"""
IP / CIDR allowlist helpers for integration token exchange.

Empty allowlist means all client IPs are permitted (default open).
Never logs secrets or tokens.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str | None:
    """
    Extract the client IP from a Django/DRF request.

    Prefers the first address in X-Forwarded-For when present (same
    convention as audit.utils.log_action), otherwise REMOTE_ADDR.
    """
    if request is None:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def normalize_allowed_cidrs(raw: Iterable | None) -> list[str]:
    """
    Coerce stored allowlist values into a clean list of CIDR/IP strings.

    Args:
        raw: JSON list from the Integration.allowed_cidrs field, or None.

    Returns:
        list[str]: Non-empty trimmed entries; empty list if none configured.
    """
    if not raw:
        return []
    result: list[str] = []
    for entry in raw:
        if entry is None:
            continue
        text = str(entry).strip()
        if text:
            result.append(text)
    return result


def ip_is_allowed(client_ip: str | None, allowed_cidrs: Iterable | None) -> bool:
    """
    Return True when the client IP is permitted by the allowlist.

    An empty allowlist always allows. A missing/invalid client IP is denied
    when the allowlist is non-empty.

    Args:
        client_ip: Observed client address (IPv4 or IPv6 string).
        allowed_cidrs: List of IPs or CIDRs, e.g. ``["203.0.113.0/24", "198.51.100.10"]``.

    Returns:
        bool: Whether the request should be allowed.
    """
    entries = normalize_allowed_cidrs(allowed_cidrs)
    if not entries:
        return True

    if not client_ip:
        return False

    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        logger.warning("Token exchange IP check: invalid client IP format")
        return False

    for entry in entries:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            logger.warning(
                "Token exchange IP check: skipping invalid allowlist entry"
            )
            continue
        if address in network:
            return True
    return False
