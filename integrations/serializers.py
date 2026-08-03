"""
Serializers for the integrations API.

Token exchange request validation for first-party partners.
"""

from rest_framework import serializers


class TokenExchangeSerializer(serializers.Serializer):
    """
    Validate client credentials and the asserted user identity.

    ``full_name`` is optional when the user already exists; on JIT create the
    service falls back to the email local-part when it is omitted.
    ``external_user_id`` is optional; when provided, an IntegrationUserLink
    is upserted after the user is resolved.
    """

    client_id = serializers.CharField(max_length=64)
    client_secret = serializers.CharField(write_only=True, trim_whitespace=False)
    email = serializers.EmailField()
    full_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        default="",
    )
    external_user_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        default="",
    )

    def validate_email(self, value: str) -> str:
        """Strip surrounding whitespace; deeper normalization happens in the service."""
        return (value or "").strip()

    def validate_external_user_id(self, value: str) -> str:
        """Strip partner external ids; empty string means omit the link upsert."""
        return (value or "").strip()
