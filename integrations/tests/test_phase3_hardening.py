"""
Phase 3 hardening tests: user links, IP allowlist, audit, token lifetime.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from audit.models import AuditLog
from integrations.models import Integration, IntegrationUserLink
from integrations.services.credentials import issue_credentials
from integrations.services.ip_allowlist import ip_is_allowed
from integrations.services.user_links import upsert_integration_user_link
from integrations.services.jwt_claims import enrich_message_with_client_id, get_jwt_client_id

User = get_user_model()


class IntegrationUserLinkTest(APITestCase):
    """Tests for IntegrationUserLink upsert on token exchange."""

    def setUp(self):
        """Create integration and user for link upserts."""
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
        data = {
            "client_id": self.integration.client_id,
            "client_secret": self.raw_secret,
            "email": self.user.email,
            "external_user_id": "hr-user-123",
        }
        data.update(overrides)
        return data

    def test_external_user_id_creates_link(self):
        """Providing external_user_id creates an IntegrationUserLink row."""
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        link = IntegrationUserLink.objects.get(
            integration=self.integration,
            external_user_id="hr-user-123",
        )
        self.assertEqual(link.user_id, self.user.id)

    def test_external_user_id_upsert_is_idempotent(self):
        """Repeating the same external_user_id does not duplicate links."""
        first = self.client.post(self.url, self._payload(), format="json")
        second = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            IntegrationUserLink.objects.filter(
                integration=self.integration,
                external_user_id="hr-user-123",
            ).count(),
            1,
        )

    def test_omitting_external_user_id_skips_link(self):
        """Without external_user_id, no IntegrationUserLink is created."""
        response = self.client.post(
            self.url,
            self._payload(external_user_id=""),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(IntegrationUserLink.objects.count(), 0)

    def test_upsert_helper_updates_external_id_for_same_user(self):
        """Same user with a new external_user_id updates the existing row."""
        first = upsert_integration_user_link(
            integration=self.integration,
            user=self.user,
            external_user_id="old-id",
        )
        second = upsert_integration_user_link(
            integration=self.integration,
            user=self.user,
            external_user_id="new-id",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.external_user_id, "new-id")
        self.assertEqual(IntegrationUserLink.objects.count(), 1)


class IpAllowlistTest(APITestCase):
    """Tests for optional Integration.allowed_cidrs enforcement."""

    def setUp(self):
        """Create integration with a restrictive allowlist."""
        cache.clear()
        self.url = reverse("integrations:token_exchange")
        client_id, raw_secret, secret_hash = issue_credentials()
        self.raw_secret = raw_secret
        self.integration = Integration.objects.create(
            name="Locked Portal",
            client_id=client_id,
            client_secret_hash=secret_hash,
            is_active=True,
            allow_jit_user_create=True,
            allowed_cidrs=["203.0.113.0/24", "198.51.100.10"],
        )
        self.user = User.objects.create_user(
            username="ada@example.com",
            email="ada@example.com",
            full_name="Ada Lovelace",
            password="StrongPassw0rd!",
        )

    def _payload(self):
        return {
            "client_id": self.integration.client_id,
            "client_secret": self.raw_secret,
            "email": self.user.email,
        }

    def test_allowed_ip_succeeds(self):
        """Client IP inside an allowed CIDR can exchange tokens."""
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
            REMOTE_ADDR="203.0.113.50",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_exact_allowed_ip_succeeds(self):
        """Exact IP entry in the allowlist is accepted."""
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
            REMOTE_ADDR="198.51.100.10",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_denied_ip_returns_403(self):
        """Client IP outside the allowlist receives 403."""
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
            REMOTE_ADDR="192.0.2.1",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["status"], "error")
        self.assertIn("IP", response.data["message"])

    def test_empty_allowlist_allows_any_ip(self):
        """Empty allowed_cidrs preserves open (allow-all) behavior."""
        self.integration.allowed_cidrs = []
        self.integration.save(update_fields=["allowed_cidrs", "updated_at"])
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
            REMOTE_ADDR="192.0.2.99",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_ip_is_allowed_helper(self):
        """Unit coverage for CIDR membership checks."""
        self.assertTrue(ip_is_allowed("203.0.113.1", ["203.0.113.0/24"]))
        self.assertFalse(ip_is_allowed("192.0.2.1", ["203.0.113.0/24"]))
        self.assertTrue(ip_is_allowed("192.0.2.1", []))
        self.assertFalse(ip_is_allowed(None, ["203.0.113.0/24"]))


class TokenExchangeAuditAndLifetimeTest(APITestCase):
    """Audit emission and shorter integration access token lifetime."""

    def setUp(self):
        """Create active integration and user."""
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

    def _payload(self):
        return {
            "client_id": self.integration.client_id,
            "client_secret": self.raw_secret,
            "email": self.user.email,
        }

    def test_successful_exchange_writes_audit_log(self):
        """Successful exchange creates INTEGRATION_TOKEN_EXCHANGE audit."""
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = AuditLog.objects.filter(
            action="INTEGRATION_TOKEN_EXCHANGE",
            actor=self.user,
        ).first()
        self.assertIsNotNone(log)
        self.assertIn(self.integration.client_id, log.message)
        self.assertEqual(log.target_object_id, self.integration.id)

    @override_settings(INTEGRATION_ACCESS_TOKEN_LIFETIME=timedelta(minutes=15))
    def test_integration_access_token_uses_shorter_lifetime(self):
        """Access token exp is bounded by INTEGRATION_ACCESS_TOKEN_LIFETIME."""
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access = AccessToken(response.data["data"]["access"])
        lifetime_seconds = int(access["exp"]) - int(access["iat"])
        # Allow a few seconds of clock skew around the 15-minute setting.
        self.assertLessEqual(lifetime_seconds, 15 * 60 + 5)
        self.assertGreaterEqual(lifetime_seconds, 15 * 60 - 5)
        self.assertEqual(access["auth_via"], "integration")

    def test_jwt_claim_helpers_are_safe_without_auth(self):
        """Claim helpers return None / unchanged message for normal requests."""
        class _Req:
            auth = None

        self.assertIsNone(get_jwt_client_id(_Req()))
        self.assertEqual(
            enrich_message_with_client_id("hello", _Req()),
            "hello",
        )
