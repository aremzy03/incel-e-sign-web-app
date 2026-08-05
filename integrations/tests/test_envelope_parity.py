"""
UI parity tests: partner S2S create/send appears as the real user's envelope.

Covers the critical path from plan §16 — token exchange → upload → create →
send → creator ownership → list visibility for user A vs unrelated user B.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditLog
from envelopes.models import Envelope
from integrations.models import Integration
from integrations.services.credentials import issue_credentials

User = get_user_model()

# Minimal valid-enough PDF bytes for document upload tests.
_TEST_PDF = (
    b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
    b"2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n"
    b"3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\n"
    b"endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n"
    b"/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
)


class EnvelopeUIParityTest(APITestCase):
    """Integration JWT create/send must match UI list ownership rules."""

    def setUp(self):
        """Create integration, user A (creator), signer, and unrelated user B."""
        cache.clear()
        client_id, raw_secret, secret_hash = issue_credentials()
        self.raw_secret = raw_secret
        self.integration = Integration.objects.create(
            name="Partner CRM",
            client_id=client_id,
            client_secret_hash=secret_hash,
            is_active=True,
            allow_jit_user_create=True,
        )
        self.user_a = User.objects.create_user(
            username="usera@example.com",
            email="usera@example.com",
            full_name="User A",
            password="StrongPassw0rd!",
        )
        self.signer = User.objects.create_user(
            username="signer@example.com",
            email="signer@example.com",
            full_name="Signer User",
            password="StrongPassw0rd!",
        )
        self.user_b = User.objects.create_user(
            username="userb@example.com",
            email="userb@example.com",
            full_name="User B",
            password="StrongPassw0rd!",
        )
        self.token_url = reverse("integrations:token_exchange")

    def _envelope_ids_from_list(self, response):
        """Return envelope id strings from a paginated list response."""
        data = response.data["data"]
        self.assertIn("results", data)
        return {item["id"] for item in data["results"]}

    @patch("notifications.tasks.send_envelope_assigned_email_task.delay")
    def test_partner_flow_envelope_visible_to_creator_not_other_user(self, mock_email_delay):
        """
        Exchange as A → upload/create/send → creator is A; UI list shows it for A only.
        """
        # 1. Exchange as user A via token endpoint
        exchange_response = self.client.post(
            self.token_url,
            {
                "client_id": self.integration.client_id,
                "client_secret": self.raw_secret,
                "email": self.user_a.email,
                "full_name": self.user_a.full_name,
            },
            format="json",
        )
        self.assertEqual(exchange_response.status_code, status.HTTP_200_OK)
        access_token = exchange_response.data["data"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        # 2. Upload + create + send with integration access token
        upload_response = self.client.post(
            reverse("documents:document_upload"),
            {
                "file": SimpleUploadedFile(
                    "partner_doc.pdf",
                    _TEST_PDF,
                    content_type="application/pdf",
                )
            },
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
        document_id = upload_response.data["data"]["id"]

        create_response = self.client.post(
            reverse("envelopes:envelope_create"),
            {
                "document_ids": [document_id],
                "name": "Partner-created Envelope",
                "signing_order": [
                    {"signer_id": str(self.signer.id), "order": 1},
                ],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        envelope_id = create_response.data["data"]["id"]

        send_response = self.client.post(
            reverse("envelopes:envelope_send", kwargs={"pk": envelope_id})
        )
        self.assertEqual(send_response.status_code, status.HTTP_200_OK)
        self.assertEqual(send_response.data["data"]["status"], "pending")
        self.assertTrue(mock_email_delay.called)

        # 3. Assert envelope.creator_id == user_a.id
        envelope = Envelope.objects.get(id=envelope_id)
        self.assertEqual(envelope.creator_id, self.user_a.id)
        self.assertEqual(envelope.status, "pending")

        # Audit messages for create/send include integration client_id claim
        create_audit = AuditLog.objects.filter(
            action="CREATE_ENVELOPE",
            target_object_id=envelope.id,
        ).first()
        send_audit = AuditLog.objects.filter(
            action="SEND_ENVELOPE",
            target_object_id=envelope.id,
        ).first()
        self.assertIsNotNone(create_audit)
        self.assertIsNotNone(send_audit)
        self.assertIn(f"client_id={self.integration.client_id}", create_audit.message)
        self.assertIn(f"client_id={self.integration.client_id}", send_audit.message)

        # 4. Authenticate as user A via normal RefreshToken (simulating UI login)
        ui_access = str(RefreshToken.for_user(self.user_a).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {ui_access}")

        # 5. GET /api/envelopes/ includes that envelope
        list_response = self.client.get(reverse("envelopes:envelope_list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(envelope_id, self._envelope_ids_from_list(list_response))

        # 6. Other user B does not see it (B is not a signer)
        user_b_access = str(RefreshToken.for_user(self.user_b).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {user_b_access}")
        other_list = self.client.get(reverse("envelopes:envelope_list"))
        self.assertEqual(other_list.status_code, status.HTTP_200_OK)
        self.assertNotIn(envelope_id, self._envelope_ids_from_list(other_list))
