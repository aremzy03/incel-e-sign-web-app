"""
Tests for the envelope dashboard endpoint.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from audit.utils import log_action
from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from signatures.models import Signature

User = get_user_model()


class EnvelopeDashboardAPITestCase(APITestCase):
    """Test cases for the envelope dashboard endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='dashboard_user@example.com',
            username='dashboard_user',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            email='other_user@example.com',
            username='other_user',
            password='testpass123'
        )
        self.signer2 = User.objects.create_user(
            email='signer2@example.com',
            username='signer2',
            password='testpass123'
        )

        self.user_document = Document.objects.create(
            owner=self.user,
            file_url='/media/dashboard_user_doc.pdf',
            file_name='dashboard_user_doc.pdf',
            file_size=1024
        )
        self.other_document = Document.objects.create(
            owner=self.other_user,
            file_url='/media/dashboard_other_doc.pdf',
            file_name='dashboard_other_doc.pdf',
            file_size=2048
        )

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

        self.signer_pending_envelope = Envelope.objects.create(
            creator=self.other_user,
            name='Signer Pending',
            status='pending',
            signing_order=[{'signer_id': str(self.user.id), 'order': 1}]
        )
        EnvelopeDocument.objects.create(
            envelope=self.signer_pending_envelope,
            document=self.other_document,
            order=1
        )
        Signature.objects.create(
            envelope=self.signer_pending_envelope,
            signer=self.user,
            status='pending'
        )

        self.sequential_envelope = Envelope.objects.create(
            creator=self.other_user,
            name='Sequential Envelope',
            status='pending',
            signing_order=[
                {'signer_id': str(self.signer2.id), 'order': 1},
                {'signer_id': str(self.user.id), 'order': 2},
            ]
        )
        EnvelopeDocument.objects.create(
            envelope=self.sequential_envelope,
            document=self.other_document,
            order=1
        )
        Signature.objects.create(
            envelope=self.sequential_envelope,
            signer=self.signer2,
            status='pending'
        )
        Signature.objects.create(
            envelope=self.sequential_envelope,
            signer=self.user,
            status='pending'
        )

        log_action(
            self.user,
            'SEND_ENVELOPE',
            self.pending_envelope,
            'User sent envelope',
        )

    def test_dashboard_endpoint_returns_expected_data(self):
        """Authenticated users receive dashboard data tailored to their activity."""
        self.client.force_authenticate(user=self.user)
        url = reverse('envelopes:envelope_dashboard')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']

        self.assertEqual(data['metrics']['documents_signed'], 1)
        self.assertEqual(data['metrics']['pending_signatures'], 2)
        self.assertEqual(data['metrics']['active_envelopes'], 2)
        self.assertEqual(data['metrics']['completion_rate'], 25.0)

        self.assertEqual(data['counts']['pending_my_signature'], 1)
        self.assertEqual(data['counts']['pending_sent'], 1)
        self.assertEqual(data['counts']['completed'], 1)
        self.assertEqual(data['counts']['draft'], 1)

        self.assertEqual(len(data['action_required']), 1)
        for envelope in data['action_required']:
            self.assertEqual(envelope['status'], 'pending')
            self.assertFalse(envelope['is_self_sign'])
            self.assertEqual(envelope['current_signer']['id'], str(self.user.id))
        self.assertEqual(data['action_required'][0]['id'], str(self.signer_pending_envelope.id))

        self.assertEqual(len(data['recent_activity']), 1)
        self.assertEqual(data['recent_activity'][0]['action'], 'SEND_ENVELOPE')
        self.assertEqual(data['recent_activity'][0]['envelope_id'], str(self.pending_envelope.id))

    def test_metrics_endpoint_alias_returns_same_dashboard_payload(self):
        """Deprecated /metrics/ alias returns the same dashboard payload."""
        self.client.force_authenticate(user=self.user)
        dashboard_response = self.client.get(reverse('envelopes:envelope_dashboard'))
        metrics_response = self.client.get(reverse('envelopes:envelope_metrics'))

        self.assertEqual(metrics_response.status_code, status.HTTP_200_OK)
        self.assertEqual(metrics_response.data, dashboard_response.data)

    def test_dashboard_excludes_non_current_signer_from_action_required(self):
        """Users waiting in line are not listed as action required."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('envelopes:envelope_dashboard'))
        data = response.data['data']

        action_required_ids = {item['id'] for item in data['action_required']}
        self.assertNotIn(str(self.sequential_envelope.id), action_required_ids)
        self.assertEqual(data['counts']['pending_my_signature'], 1)

    def test_dashboard_excludes_self_sign_envelopes_from_action_required(self):
        """Self-signed envelopes are not listed as action required."""
        self_sign_envelope = Envelope.objects.create(
            creator=self.user,
            name='Self Sign Envelope',
            status='self_signed',
            is_self_sign=True,
            signing_order=[{'signer_id': str(self.user.id), 'order': 1}],
        )
        EnvelopeDocument.objects.create(
            envelope=self_sign_envelope,
            document=self.user_document,
            order=1,
        )
        Signature.objects.create(
            envelope=self_sign_envelope,
            signer=self.user,
            status='signed',
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('envelopes:envelope_dashboard'))
        data = response.data['data']

        action_required_ids = {item['id'] for item in data['action_required']}
        self.assertNotIn(str(self_sign_envelope.id), action_required_ids)
        self.assertEqual(data['counts']['pending_my_signature'], 1)

    def test_dashboard_endpoint_requires_authentication(self):
        """Unauthenticated requests should be rejected."""
        url = reverse('envelopes:envelope_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dashboard_respects_activity_limit(self):
        """Activity list length is bounded by the activity_limit query param."""
        log_action(
            self.user,
            'REJECT_ENVELOPE',
            self.rejected_envelope,
            'User rejected envelope',
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            reverse('envelopes:envelope_dashboard'),
            {'activity_limit': 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['recent_activity']), 1)
