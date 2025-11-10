"""
Tests for the envelope metrics endpoint.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from signatures.models import Signature

User = get_user_model()


class EnvelopeMetricsAPITestCase(APITestCase):
    """Test cases for the envelope metrics endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='metrics_user@example.com',
            username='metrics_user',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            email='other_user@example.com',
            username='other_user',
            password='testpass123'
        )

        # Documents for envelope associations
        self.user_document = Document.objects.create(
            owner=self.user,
            file_url='/media/metrics_user_doc.pdf',
            file_name='metrics_user_doc.pdf',
            file_size=1024
        )
        self.other_document = Document.objects.create(
            owner=self.other_user,
            file_url='/media/metrics_other_doc.pdf',
            file_name='metrics_other_doc.pdf',
            file_size=2048
        )

        # Envelopes created by self.user
        self.draft_envelope = Envelope.objects.create(
            creator=self.user,
            name='Draft Envelope',
            status='draft'
        )
        EnvelopeDocument.objects.create(
            envelope=self.draft_envelope,
            document=self.user_document,
            order=1
        )

        self.pending_envelope = Envelope.objects.create(
            creator=self.user,
            name='Pending Envelope',
            status='pending'
        )
        EnvelopeDocument.objects.create(
            envelope=self.pending_envelope,
            document=self.user_document,
            order=1
        )

        self.completed_envelope = Envelope.objects.create(
            creator=self.user,
            name='Completed Envelope',
            status='completed'
        )
        EnvelopeDocument.objects.create(
            envelope=self.completed_envelope,
            document=self.user_document,
            order=1
        )

        self.rejected_envelope = Envelope.objects.create(
            creator=self.user,
            name='Rejected Envelope',
            status='rejected'
        )
        EnvelopeDocument.objects.create(
            envelope=self.rejected_envelope,
            document=self.user_document,
            order=1
        )

        # Signatures involving self.user as signer
        signer_envelope_signed = Envelope.objects.create(
            creator=self.other_user,
            name='Signer Completed',
            status='completed',
            signing_order=[{'signer_id': str(self.user.id), 'order': 1}]
        )
        EnvelopeDocument.objects.create(
            envelope=signer_envelope_signed,
            document=self.other_document,
            order=1
        )
        Signature.objects.create(
            envelope=signer_envelope_signed,
            signer=self.user,
            status='signed'
        )

        signer_envelope_pending = Envelope.objects.create(
            creator=self.other_user,
            name='Signer Pending',
            status='pending',
            signing_order=[{'signer_id': str(self.user.id), 'order': 1}]
        )
        EnvelopeDocument.objects.create(
            envelope=signer_envelope_pending,
            document=self.other_document,
            order=1
        )
        Signature.objects.create(
            envelope=signer_envelope_pending,
            signer=self.user,
            status='pending'
        )

    def test_metrics_endpoint_returns_expected_counts(self):
        """Authenticated users receive metrics tailored to their activity."""
        self.client.force_authenticate(user=self.user)
        url = reverse('envelopes:envelope_metrics')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']

        self.assertEqual(data['documents_signed'], 1)
        self.assertEqual(data['pending_signatures'], 1)
        self.assertEqual(data['active_envelopes'], 2)
        self.assertEqual(data['completion_rate'], 25.0)

    def test_metrics_endpoint_requires_authentication(self):
        """Unauthenticated requests should be rejected."""
        url = reverse('envelopes:envelope_metrics')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

