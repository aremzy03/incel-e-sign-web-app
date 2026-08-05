"""
Credential helpers for integration client secrets.

Generates high-entropy secrets, hashes them for storage, and verifies
candidates with Django's password hasher (constant-time comparison).
Never log or persist the raw secret.
"""

from __future__ import annotations

import secrets

from django.contrib.auth.hashers import check_password, make_password

# Default entropy: 32 bytes → ~43-character URL-safe secret.
_DEFAULT_SECRET_BYTES = 32
_CLIENT_ID_BYTES = 16


def generate_client_id() -> str:
    """
    Generate a public opaque client identifier.

    Returns:
        str: client_id with an ``int_`` prefix for easy recognition.
    """
    return f"int_{secrets.token_urlsafe(_CLIENT_ID_BYTES)}"


def generate_client_secret(nbytes: int = _DEFAULT_SECRET_BYTES) -> str:
    """
    Generate a high-entropy client secret.

    Args:
        nbytes: Number of random bytes used as entropy (default 32).

    Returns:
        str: URL-safe secret string. Callers must show it once and never store it.
    """
    return secrets.token_urlsafe(nbytes)


def hash_client_secret(raw_secret: str) -> str:
    """
    Hash a raw client secret for durable storage.

    Args:
        raw_secret: The plaintext secret. Never persist this value.

    Returns:
        str: Django password hash suitable for ``Integration.client_secret_hash``.
    """
    return make_password(raw_secret)


def verify_client_secret(raw_secret: str, secret_hash: str) -> bool:
    """
    Verify a raw secret against a stored hash using constant-time comparison.

    Args:
        raw_secret: Candidate plaintext secret from the partner.
        secret_hash: Stored hash from ``Integration.client_secret_hash``.

    Returns:
        bool: True if the secret matches, False otherwise.
    """
    if not raw_secret or not secret_hash:
        return False
    return check_password(raw_secret, secret_hash)


def issue_credentials() -> tuple[str, str, str]:
    """
    Generate a new client_id, raw secret, and secret hash together.

    Returns:
        tuple[str, str, str]: ``(client_id, raw_secret, secret_hash)``.
            The raw_secret must be shown once to staff and never stored.
    """
    client_id = generate_client_id()
    raw_secret = generate_client_secret()
    secret_hash = hash_client_secret(raw_secret)
    return client_id, raw_secret, secret_hash


def rotate_secret_hash() -> tuple[str, str]:
    """
    Generate a replacement secret and its hash (invalidates any previous secret).

    Returns:
        tuple[str, str]: ``(raw_secret, secret_hash)``.
            The raw_secret must be shown once to staff and never stored.
    """
    raw_secret = generate_client_secret()
    return raw_secret, hash_client_secret(raw_secret)
