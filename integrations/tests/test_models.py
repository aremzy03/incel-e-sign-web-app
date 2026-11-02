"""
Unit tests for the Integration model.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from integrations.models import Integration
from integrations.services.credentials import (
    generate_client_id,
    hash_client_secret,
    issue_credentials,
    verify_client_secret,
)

User = get_user_model()


class IntegrationModelTest(TestCase):
    """Test cases for Integration model defaults and constraints."""

    def setUp(self):
        """Create a staff user for created_by relations."""
        self.staff = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="testpass123",
            full_name="Staff User",
            is_staff=True,
        )

    def _create_integration(self, **overrides) -> Integration:
        """Helper to create an Integration with valid hashed credentials."""
        client_id, raw_secret, secret_hash = issue_credentials()
        defaults = {
            "name": "HR Portal",
            "client_id": client_id,
            "client_secret_hash": secret_hash,
            "created_by": self.staff,
        }
        defaults.update(overrides)
        integration = Integration.objects.create(**defaults)
        # Attach raw_secret for verify assertions in tests only (not persisted).
        integration._test_raw_secret = raw_secret  # noqa: SLF001
        return integration

    def test_create_integration_with_defaults(self):
        """New integrations are active with JIT create enabled by default."""
        integration = self._create_integration()
        self.assertTrue(integration.is_active)
        self.assertTrue(integration.allow_jit_user_create)
        self.assertEqual(integration.created_by, self.staff)
        self.assertEqual(integration.notes, "")
        self.assertEqual(integration.allowed_cidrs, [])
        self.assertIsNotNone(integration.id)
        self.assertIsNotNone(integration.created_at)
        self.assertIsNotNone(integration.updated_at)
        self.assertTrue(
            verify_client_secret(
                integration._test_raw_secret,
                integration.client_secret_hash,
            )
        )

    def test_str_includes_name_and_client_id(self):
        """__str__ surfaces the human name and public client_id."""
        integration = self._create_integration(name="CRM Bridge")
        self.assertIn("CRM Bridge", str(integration))
        self.assertIn(integration.client_id, str(integration))

    def test_client_id_must_be_unique(self):
        """Duplicate client_id values raise IntegrityError."""
        first = self._create_integration()
        with self.assertRaises(IntegrityError):
            Integration.objects.create(
                name="Duplicate",
                client_id=first.client_id,
                client_secret_hash=hash_client_secret("other-secret"),
            )

    def test_deactivate_soft_disables(self):
        """Setting is_active=False soft-disables without deleting."""
        integration = self._create_integration()
        integration.is_active = False
        integration.save(update_fields=["is_active", "updated_at"])
        integration.refresh_from_db()
        self.assertFalse(integration.is_active)
        self.assertTrue(
            Integration.objects.filter(pk=integration.pk).exists()
        )

    def test_allow_jit_user_create_can_be_disabled(self):
        """JIT user create can be turned off per integration."""
        integration = self._create_integration(allow_jit_user_create=False)
        self.assertFalse(integration.allow_jit_user_create)

    def test_created_by_nullable(self):
        """created_by may be null when no staff actor is available."""
        client_id = generate_client_id()
        integration = Integration.objects.create(
            name="System Seeded",
            client_id=client_id,
            client_secret_hash=hash_client_secret("seed-secret-value"),
            created_by=None,
        )
        self.assertIsNone(integration.created_by)
