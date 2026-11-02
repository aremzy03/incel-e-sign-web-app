"""
API tests for integration token exchange.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from integrations.models import Integration
from integrations.services.credentials import issue_credentials
from integrations.throttles import IntegrationTokenThrottle

User = get_user_model()


class TokenExchangeAPITest(APITestCase):
    """Test cases for POST /api/v1/integrations/token/."""

    def setUp(self):
        """Create an active integration with a known raw secret."""
        cache.clear()
        self.url = reverse("integrations:token_exchange")
        client_id, raw_secret, secret_hash = issue_credentials()
        self.raw_secret = raw_secret
        self.integration = Integration.objects.create(
            name="HR Portal",
            client_id=client_id,
            client_secret_hash=secret_hash,
            is_active=True,
            allow_jit_user_create=True,
        )
        self.user = User.objects.create_user(
            username="ada@example.com",
            email="ada@example.com",
            full_name="Ada Lovelace",
            password="StrongPassw0rd!",
        )

    def _payload(self, **overrides):
        """Build a valid token-exchange payload with optional overrides."""
        data = {
            "client_id": self.integration.client_id,
            "client_secret": self.raw_secret,
            "email": self.user.email,
            "full_name": "Ada Lovelace",
        }
        data.update(overrides)
        return data

    def test_valid_credentials_issue_jwt_for_user(self):
        """Valid credentials + email return 200 and a JWT for that user."""
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["message"], "Token issued successfully")

        data = response.data["data"]
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["user"]["email"], self.user.email)
        self.assertEqual(data["user"]["full_name"], self.user.full_name)
        self.assertEqual(data["user"]["id"], str(self.user.id))

        access = AccessToken(data["access"])
        self.assertEqual(access["user_id"], str(self.user.id))
        self.assertEqual(access["client_id"], self.integration.client_id)
        self.assertEqual(access["auth_via"], "integration")

        refresh = RefreshToken(data["refresh"])
        self.assertEqual(refresh["client_id"], self.integration.client_id)
        self.assertEqual(refresh["auth_via"], "integration")

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
        profile = self.client.get(reverse("auth-profile"))
        self.assertEqual(profile.status_code, status.HTTP_200_OK)
        self.assertEqual(profile.data["data"]["email"], self.user.email)

    def test_bad_secret_returns_401(self):
        """Wrong client_secret yields 401 without leaking details."""
        response = self.client.post(
            self.url,
            self._payload(client_secret="definitely-wrong-secret"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["status"], "error")

    def test_unknown_client_returns_401(self):
        """Unknown client_id yields 401."""
        response = self.client.post(
            self.url,
            self._payload(client_id="int_does_not_exist"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_integration_returns_401(self):
        """Inactive integration cannot exchange tokens."""
        self.integration.is_active = False
        self.integration.save(update_fields=["is_active", "updated_at"])
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_email_jit_off_returns_404(self):
        """Missing user with JIT disabled returns 404."""
        self.integration.allow_jit_user_create = False
        self.integration.save(update_fields=["allow_jit_user_create", "updated_at"])
        response = self.client.post(
            self.url,
            self._payload(email="missing@example.com", full_name="Missing User"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(
            User.objects.filter(email__iexact="missing@example.com").exists()
        )

    def test_unknown_email_jit_on_creates_user_with_unusable_password(self):
        """Missing user with JIT enabled is created with an unusable password."""
        email = "new.hire@example.com"
        response = self.client.post(
            self.url,
            self._payload(email=email, full_name="New Hire"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email=email)
        self.assertEqual(user.username, email)
        self.assertEqual(user.full_name, "New Hire")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(response.data["data"]["user"]["id"], str(user.id))

        access = AccessToken(response.data["data"]["access"])
        self.assertEqual(access["user_id"], str(user.id))
        self.assertEqual(access["auth_via"], "integration")

    def test_inactive_user_returns_403(self):
        """Existing but inactive user cannot receive a token."""
        self.user.is_active = False
        self.user.save(update_fields=["is_active", "updated_at"])
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_email_returns_400(self):
        """Malformed email fails serializer validation with 400."""
        response = self.client.post(
            self.url,
            self._payload(email="not-an-email"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "error")

    def test_email_is_normalized_on_jit_create(self):
        """JIT create stores a lowercased, stripped email."""
        response = self.client.post(
            self.url,
            self._payload(email="  New.User@Example.COM ", full_name="New User"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            User.objects.filter(email="new.user@example.com").exists()
        )

    def test_existing_user_full_name_not_overwritten(self):
        """Provided full_name does not overwrite a non-empty existing name."""
        response = self.client.post(
            self.url,
            self._payload(full_name="Someone Else"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Ada Lovelace")

    def test_throttle_smoke_returns_429(self):
        """Exceeding the integration_token rate returns 429."""
        # DRF caches THROTTLE_RATES on the class after import; patch the
        # rate for this smoke check instead of relying on override_settings.
        cache.clear()
        with patch.object(
            IntegrationTokenThrottle,
            "THROTTLE_RATES",
            {"integration_token": "1/minute"},
        ):
            first = self.client.post(self.url, self._payload(), format="json")
            self.assertEqual(first.status_code, status.HTTP_200_OK)
            second = self.client.post(self.url, self._payload(), format="json")
            self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
