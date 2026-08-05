"""
Encrypt / decrypt integration webhook signing secrets.

Uses Django's cryptographic signer so the raw secret is recoverable for
outbound HMAC without storing plaintext. Never log decrypted values.
"""

from __future__ import annotations

from django.core import signing

_WEBHOOK_SECRET_SALT = "integrations.webhook.signing_secret"


def encrypt_webhook_secret(raw_secret: str) -> str:
    """
    Encrypt a webhook signing secret for durable storage.

    Args:
        raw_secret: Plaintext secret. Caller must not log it.

    Returns:
        str: Signed/encrypted token suitable for DB storage.
    """
    return signing.dumps(raw_secret, salt=_WEBHOOK_SECRET_SALT)


def decrypt_webhook_secret(encrypted: str) -> str:
    """
    Decrypt a stored webhook signing secret.

    Args:
        encrypted: Value from ``signing_secret_encrypted``.

    Returns:
        str: Plaintext secret for HMAC computation.
    """
    return signing.loads(encrypted, salt=_WEBHOOK_SECRET_SALT)
