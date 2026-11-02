"""
Phase 4 tests: email signers, composite send, webhooks, idempotency.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from integrations.models import (
    IdempotencyRecord,
    Integration,
    IntegrationEnvelopeOrigin,
    IntegrationWebhookDelivery,
    IntegrationWebhookEndpoint,
)
from integrations.services.credentials import issue_credentials
from integrations.services.webhook_secrets import encrypt_webhook_secret
from integrations.services.webhooks import sign_payload
from signatures.services.signing import complete_envelope

User = get_user_model()

_TEST_PDF = (
    b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
    b"2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n"
    b"3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\n"
    b"endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n"
    b"/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
)


class SignerEmailResolutionTests(APITestCase):
    """Envelope create accepts email find-or-invite for signing_order."""

    def setUp(self):
        cache.clear()
        self.creator = User.objects.create_user(
            username="creator@example.com",
            email="creator@example.com",
            full_name="Creator",
            password="StrongPassw0rd!",
        )
        self.existing_signer = User.objects.create_user(
            username="known@example.com",
            email="known@example.com",
            full_name="Known Signer",
            password="StrongPassw0rd!",
        )
        self.document = Document.objects.create(
            owner=self.creator,
            file_name="doc.pdf",
            file_url="/media/doc.pdf",
            file_size=1024,
            status="draft",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.creator).access_token}"
        )
        self.create_url = reverse("envelopes:envelope_create")

    @patch("notifications.utils.send_invite_email")
    def test_existing_email_resolves_to_user(self, mock_invite):
        response = self.client.post(
            self.create_url,
            {
                "document_ids": [str(self.document.id)],
                "signing_order": [
                    {"email": "known@example.com", "order": 1},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        envelope = Envelope.objects.get(id=response.data["data"]["id"])
        self.assertEqual(
            envelope.signing_order[0]["signer_id"],
            str(self.existing_signer.id),
        )
        mock_invite.assert_not_called()

    @patch("notifications.utils.send_invite_email")
    def test_unknown_email_invites_and_creates_user(self, mock_invite):
        response = self.client.post(
            self.create_url,
            {
                "document_ids": [str(self.document.id)],
                "name": "Invite flow",
                "signing_order": [
                    {
                        "email": "newbie@example.com",
                        "order": 1,
                        "full_name": "New Signer",
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        invited = User.objects.get(email="newbie@example.com")
        self.assertFalse(invited.has_usable_password())
        self.assertEqual(invited.full_name, "New Signer")
        envelope = Envelope.objects.get(id=response.data["data"]["id"])
        self.assertEqual(envelope.signing_order[0]["signer_id"], str(invited.id))
        mock_invite.assert_called_once()

    @patch("notifications.utils.send_invite_email")
    def test_mixed_signer_id_and_email_order(self, mock_invite):
        response = self.client.post(
            self.create_url,
            {
                "document_ids": [str(self.document.id)],
                "signing_order": [
                    {"signer_id": str(self.existing_signer.id), "order": 1},
                    {"email": "mixed@example.com", "order": 2, "full_name": "Mixed"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        envelope = Envelope.objects.get(id=response.data["data"]["id"])
        self.assertEqual(
            envelope.signing_order[0]["signer_id"],
            str(self.existing_signer.id),
        )
        invited = User.objects.get(email="mixed@example.com")
        self.assertEqual(envelope.signing_order[1]["signer_id"], str(invited.id))
        mock_invite.assert_called_once()


class CompositeEnvelopeSendTests(APITestCase):
    """POST /api/v1/integrations/envelopes/send/ orchestrates upload/create/send."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="partner@example.com",
            email="partner@example.com",
            full_name="Partner User",
            password="StrongPassw0rd!",
        )
        self.signer = User.objects.create_user(
            username="sig@example.com",
            email="sig@example.com",
            full_name="Signer",
            password="StrongPassw0rd!",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.user).access_token}"
        )
        self.url = reverse("integrations:envelopes_send")

    @patch("notifications.tasks.send_envelope_assigned_email_task.delay")
    def test_multipart_happy_path(self, mock_email):
        response = self.client.post(
            self.url,
            {
                "file": SimpleUploadedFile(
                    "composite.pdf",
                    _TEST_PDF,
                    content_type="application/pdf",
                ),
                "name": "Composite Envelope",
                "signing_order": json.dumps(
                    [{"signer_id": str(self.signer.id), "order": 1}]
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["data"]["status"], "pending")
        envelope_id = response.data["data"]["envelope_id"]
        envelope = Envelope.objects.get(id=envelope_id)
        self.assertEqual(envelope.creator_id, self.user.id)
        self.assertEqual(envelope.status, "pending")
        self.assertTrue(mock_email.called)

    @patch("notifications.tasks.send_envelope_assigned_email_task.delay")
    def test_json_with_document_ids_happy_path(self, mock_email):
        document = Document.objects.create(
            owner=self.user,
            file_name="pre.pdf",
            file_url="/media/pre.pdf",
            file_size=1024,
            status="draft",
        )
        response = self.client.post(
            self.url,
            {
                "document_ids": [str(document.id)],
                "name": "JSON composite",
                "signing_order": [{"email": self.signer.email, "order": 1}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["status"], "pending")
        self.assertTrue(mock_email.called)

    def test_missing_file_and_document_ids_fails(self):
        response = self.client.post(
            self.url,
            {
                "signing_order": [{"signer_id": str(self.signer.id), "order": 1}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_rejected(self):
        self.client.credentials()
        response = self.client.post(self.url, {}, format="json")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class IdempotencyKeyTests(APITestCase):
    """Idempotency-Key on create, send, and composite endpoints."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="idem@example.com",
            email="idem@example.com",
            full_name="Idem User",
            password="StrongPassw0rd!",
        )
        self.signer = User.objects.create_user(
            username="idem-signer@example.com",
            email="idem-signer@example.com",
            full_name="Idem Signer",
            password="StrongPassw0rd!",
        )
        self.document = Document.objects.create(
            owner=self.user,
            file_name="idem.pdf",
            file_url="/media/idem.pdf",
            file_size=1024,
            status="draft",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.user).access_token}"
        )

    def test_create_replay_returns_same_envelope(self):
        url = reverse("envelopes:envelope_create")
        payload = {
            "document_ids": [str(self.document.id)],
            "name": "Idem create",
            "signing_order": [{"signer_id": str(self.signer.id), "order": 1}],
        }
        headers = {"HTTP_IDEMPOTENCY_KEY": "create-key-1"}
        first = self.client.post(url, payload, format="json", **headers)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        envelope_id = first.data["data"]["id"]

        second = self.client.post(url, payload, format="json", **headers)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.data["data"]["id"], envelope_id)
        self.assertEqual(Envelope.objects.filter(name="Idem create").count(), 1)

    @patch("notifications.tasks.send_envelope_assigned_email_task.delay")
    def test_different_key_creates_new_envelope(self, _mock_email):
        url = reverse("envelopes:envelope_create")
        doc2 = Document.objects.create(
            owner=self.user,
            file_name="idem2.pdf",
            file_url="/media/idem2.pdf",
            file_size=1024,
            status="draft",
        )
        base = {"signing_order": [{"signer_id": str(self.signer.id), "order": 1}]}
        first = self.client.post(
            url,
            {**base, "document_ids": [str(self.document.id)], "name": "A"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-a",
        )
        second = self.client.post(
            url,
            {**base, "document_ids": [str(doc2.id)], "name": "B"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-b",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(first.data["data"]["id"], second.data["data"]["id"])

    @patch("notifications.tasks.send_envelope_assigned_email_task.delay")
    def test_send_replay_returns_same_result(self, mock_email):
        envelope = Envelope.objects.create(
            creator=self.user,
            name="Send idem",
            status="draft",
            signing_order=[{"signer_id": str(self.signer.id), "order": 1}],
        )
        EnvelopeDocument.objects.create(
            envelope=envelope, document=self.document, order=1
        )
        url = reverse("envelopes:envelope_send", kwargs={"pk": envelope.id})
        first = self.client.post(url, HTTP_IDEMPOTENCY_KEY="send-key-1")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        calls_after_first = mock_email.call_count

        second = self.client.post(url, HTTP_IDEMPOTENCY_KEY="send-key-1")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["data"]["id"], first.data["data"]["id"])
        self.assertEqual(mock_email.call_count, calls_after_first)
        self.assertEqual(
            IdempotencyRecord.objects.filter(key="send-key-1").count(),
            1,
        )

    @patch("notifications.tasks.send_envelope_assigned_email_task.delay")
    def test_composite_idempotency_replay(self, mock_email):
        url = reverse("integrations:envelopes_send")
        payload = {
            "document_ids": [str(self.document.id)],
            "name": "Composite idem",
            "signing_order": [{"signer_id": str(self.signer.id), "order": 1}],
        }
        first = self.client.post(
            url, payload, format="json", HTTP_IDEMPOTENCY_KEY="comp-1"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        envelope_id = first.data["data"]["envelope_id"]
        calls = mock_email.call_count

        second = self.client.post(
            url, payload, format="json", HTTP_IDEMPOTENCY_KEY="comp-1"
        )
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.data["data"]["envelope_id"], envelope_id)
        self.assertEqual(mock_email.call_count, calls)
        self.assertEqual(Envelope.objects.filter(name="Composite idem").count(), 1)


class WebhookDispatchTests(APITestCase):
    """Outbound webhook dispatch for envelope.sent and envelope.completed."""

    def setUp(self):
        cache.clear()
        client_id, raw_secret, secret_hash = issue_credentials()
        self.integration = Integration.objects.create(
            name="Webhook Partner",
            client_id=client_id,
            client_secret_hash=secret_hash,
            is_active=True,
        )
        self.webhook_secret = "whsec_test_signing_secret_value"
        self.endpoint = IntegrationWebhookEndpoint.objects.create(
            integration=self.integration,
            url="https://partner.example.com/hooks/esign",
            signing_secret_encrypted=encrypt_webhook_secret(self.webhook_secret),
            is_active=True,
            enabled_events=["envelope.sent", "envelope.completed"],
        )
        self.user = User.objects.create_user(
            username="wh@example.com",
            email="wh@example.com",
            full_name="Webhook User",
            password="StrongPassw0rd!",
        )
        self.signer = User.objects.create_user(
            username="wh-signer@example.com",
            email="wh-signer@example.com",
            full_name="WH Signer",
            password="StrongPassw0rd!",
        )
        self.document = Document.objects.create(
            owner=self.user,
            file_name="wh.pdf",
            file_url="/media/wh.pdf",
            file_size=1024,
            status="draft",
        )
        # Mint JWT with client_id claim like token exchange.
        refresh = RefreshToken.for_user(self.user)
        refresh["client_id"] = self.integration.client_id
        refresh["auth_via"] = "integration"
        access = refresh.access_token
        access["client_id"] = self.integration.client_id
        access["auth_via"] = "integration"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    @patch("notifications.tasks.send_envelope_assigned_email_task.delay")
    @patch("integrations.services.webhooks.deliver_webhook_once")
    @patch("integrations.tasks.deliver_webhook_task.delay")
    def test_send_dispatches_envelope_sent(
        self, mock_delay, mock_deliver_once, _mock_email
    ):
        # Eager celery may call the task; route delay to create delivery only.
        def _enqueue(delivery_id):
            return None

        mock_delay.side_effect = _enqueue

        create = self.client.post(
            reverse("envelopes:envelope_create"),
            {
                "document_ids": [str(self.document.id)],
                "name": "WH send",
                "signing_order": [{"signer_id": str(self.signer.id), "order": 1}],
            },
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        envelope_id = create.data["data"]["id"]
        self.assertTrue(
            IntegrationEnvelopeOrigin.objects.filter(
                envelope_id=envelope_id,
                integration=self.integration,
            ).exists()
        )

        send = self.client.post(
            reverse("envelopes:envelope_send", kwargs={"pk": envelope_id})
        )
        self.assertEqual(send.status_code, status.HTTP_200_OK)
        delivery = IntegrationWebhookDelivery.objects.filter(
            event_type="envelope.sent",
            envelope_id=envelope_id,
        ).first()
        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.endpoint_id, self.endpoint.id)
        mock_delay.assert_called()

    @patch("integrations.tasks.deliver_webhook_task.delay")
    def test_complete_dispatches_envelope_completed(self, mock_delay):
        envelope = Envelope.objects.create(
            creator=self.user,
            name="WH complete",
            status="pending",
            signing_order=[{"signer_id": str(self.signer.id), "order": 1}],
        )
        EnvelopeDocument.objects.create(
            envelope=envelope, document=self.document, order=1
        )
        IntegrationEnvelopeOrigin.objects.create(
            envelope=envelope,
            integration=self.integration,
        )
        mock_delay.side_effect = lambda delivery_id: None

        with patch(
            "signatures.services.signing.upload_completed_pdf",
            return_value=None,
        ):
            complete_envelope(envelope, notify_creator=False)

        delivery = IntegrationWebhookDelivery.objects.filter(
            event_type="envelope.completed",
            envelope_id=envelope.id,
        ).first()
        self.assertIsNotNone(delivery)
        mock_delay.assert_called()

    @patch("urllib.request.urlopen")
    def test_deliver_webhook_once_signs_and_posts(self, mock_urlopen):
        from integrations.services.webhooks import deliver_webhook_once

        envelope = Envelope.objects.create(
            creator=self.user,
            name="WH http",
            status="pending",
            signing_order=[{"signer_id": str(self.signer.id), "order": 1}],
        )
        delivery = IntegrationWebhookDelivery.objects.create(
            endpoint=self.endpoint,
            event_type="envelope.sent",
            envelope_id=envelope.id,
            payload={"event": "envelope.sent", "data": {"envelope_id": str(envelope.id)}},
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = b'{"ok":true}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response

        ok = deliver_webhook_once(str(delivery.id))
        self.assertTrue(ok)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, IntegrationWebhookDelivery.STATUS_SUCCESS)

        request_obj = mock_urlopen.call_args[0][0]
        self.assertEqual(request_obj.get_method(), "POST")
        signature = request_obj.headers.get("X-esign-signature") or request_obj.headers.get(
            "X-ESign-Signature"
        )
        self.assertIsNotNone(signature)
        self.assertIn("t=", signature)
        self.assertIn("v1=", signature)
        # Verify HMAC with known secret
        body = request_obj.data
        ts = int(signature.split(",")[0].split("=", 1)[1])
        expected = sign_payload(self.webhook_secret, body, timestamp=ts)
        self.assertEqual(signature, expected)
