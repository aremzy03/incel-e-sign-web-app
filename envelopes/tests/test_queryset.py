"""
Tests for envelope queryset access helpers.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from envelopes.models import Envelope
from envelopes.utils.queryset import get_envelopes_accessible_by_user

User = get_user_model()


class EnvelopeAccessibleQuerysetTest(TestCase):
    """Tests for get_envelopes_accessible_by_user."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator',
            email='creator@test.com',
            password='testpass123',
        )
        self.signer = User.objects.create_user(
            username='signer',
            email='signer@test.com',
            password='testpass123',
        )
        self.other = User.objects.create_user(
            username='other',
            email='other@test.com',
            password='testpass123',
        )

        self.creator_envelope = Envelope.objects.create(
            creator=self.creator,
            name='Creator envelope',
            status='draft',
            signing_order=[{'signer_id': str(self.signer.id), 'order': 1}],
        )
        self.signer_only_envelope = Envelope.objects.create(
            creator=self.other,
            name='Signer envelope',
            status='draft',
            signing_order=[{'signer_id': str(self.signer.id), 'order': 1}],
        )
        self.unrelated_envelope = Envelope.objects.create(
            creator=self.other,
            name='Unrelated envelope',
            status='draft',
            signing_order=[{'signer_id': str(self.other.id), 'order': 1}],
        )

    def test_creator_sees_own_envelope(self):
        pks = set(get_envelopes_accessible_by_user(self.creator).values_list('pk', flat=True))
        self.assertIn(self.creator_envelope.pk, pks)
        self.assertNotIn(self.unrelated_envelope.pk, pks)

    def test_signer_sees_assigned_draft_envelope(self):
        pks = set(get_envelopes_accessible_by_user(self.signer).values_list('pk', flat=True))
        self.assertIn(self.creator_envelope.pk, pks)
        self.assertIn(self.signer_only_envelope.pk, pks)
        self.assertNotIn(self.unrelated_envelope.pk, pks)

    def test_unrelated_user_sees_no_envelopes(self):
        pks = set(get_envelopes_accessible_by_user(self.other).values_list('pk', flat=True))
        self.assertIn(self.signer_only_envelope.pk, pks)
        self.assertIn(self.unrelated_envelope.pk, pks)
        self.assertNotIn(self.creator_envelope.pk, pks)
