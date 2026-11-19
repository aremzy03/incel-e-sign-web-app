"""
Tests for GET /api/search/ (global search across envelopes and documents).
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument
from signatures.models import Signature

User = get_user_model()


class GlobalSearchTests(APITestCase):
    def setUp(self):
        self.me = User.objects.create_user(
            username='me', email='me@test.com', full_name='Ada Me', password='pw-123456'
        )
        self.partner = User.objects.create_user(
            username='partner', email='bola@partner.com', full_name='Bola Partner', password='pw-123456'
        )
        self.stranger = User.objects.create_user(
            username='stranger', email='stranger@test.com', full_name='Stranger', password='pw-123456'
        )
        self.url = reverse('global-search')

        self.my_doc = Document.objects.create(
            owner=self.me, file_name='Lagos credit note.pdf', file_url='/x.pdf', file_size=10, status='draft'
        )
        self.my_envelope = Envelope.objects.create(
            creator=self.me,
            name='Dealer agreement',
            status='pending',
            signing_order=[{'signer_id': str(self.partner.id), 'order': 1}],
        )
        EnvelopeDocument.objects.create(envelope=self.my_envelope, document=self.my_doc, order=1)
        Signature.objects.create(envelope=self.my_envelope, signer=self.partner, status='pending')

        # Sent to me by someone else.
        self.incoming = Envelope.objects.create(
            creator=self.partner,
            name='Partner lease',
            status='pending',
            signing_order=[{'signer_id': str(self.me.id), 'order': 1}],
        )
        # Not mine at all, but with matching names.
        self.strangers_doc = Document.objects.create(
            owner=self.stranger, file_name='Lagos secret.pdf', file_url='/y.pdf', file_size=10, status='draft'
        )
        Envelope.objects.create(
            creator=self.stranger,
            name='Dealer agreement (private)',
            status='draft',
            signing_order=[{'signer_id': str(self.stranger.id), 'order': 1}],
        )

    def search(self, q, user=None, **params):
        self.client.force_authenticate(user or self.me)
        return self.client.get(self.url, {'q': q, **params})

    def test_requires_authentication(self):
        response = self.client.get(self.url, {'q': 'dealer'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_short_queries(self):
        response = self.search('d')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_finds_own_envelope_by_name_and_hides_strangers(self):
        data = self.search('dealer').data['data']
        self.assertEqual([e['id'] for e in data['envelopes']], [str(self.my_envelope.id)])
        self.assertEqual(data['envelopes'][0]['role'], 'creator')
        self.assertEqual(data['envelopes'][0]['matched_on'], 'name')
        self.assertEqual(data['totals']['envelopes'], 1)

    def test_finds_envelope_by_document_file_name(self):
        data = self.search('credit note').data['data']
        envelope = next(e for e in data['envelopes'] if e['id'] == str(self.my_envelope.id))
        self.assertEqual(envelope['matched_on'], 'document')
        self.assertIn('Lagos credit note.pdf', envelope['document_names'])

    def test_finds_envelope_by_signer_email(self):
        data = self.search('bola@partner').data['data']
        ids = {e['id'] for e in data['envelopes']}
        self.assertIn(str(self.my_envelope.id), ids)

    def test_signer_sees_incoming_envelope(self):
        data = self.search('lease').data['data']
        self.assertEqual([e['id'] for e in data['envelopes']], [str(self.incoming.id)])
        self.assertEqual(data['envelopes'][0]['role'], 'signer')

    def test_documents_are_owner_only(self):
        data = self.search('lagos').data['data']
        self.assertEqual([d['id'] for d in data['documents']], [str(self.my_doc.id)])
        self.assertEqual(data['totals']['documents'], 1)

    def test_case_insensitive_and_limit(self):
        for i in range(4):
            Document.objects.create(
                owner=self.me, file_name=f'Invoice {i}.pdf', file_url='/z.pdf', file_size=1, status='draft'
            )
        data = self.search('INVOICE', limit=2).data['data']
        self.assertEqual(len(data['documents']), 2)
        self.assertEqual(data['totals']['documents'], 4)

    def test_no_matches(self):
        data = self.search('zzzz').data['data']
        self.assertEqual(data['envelopes'], [])
        self.assertEqual(data['documents'], [])
