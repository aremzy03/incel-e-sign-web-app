"""
Tests for the one-call self-sign envelope endpoint.
"""

import base64
import os
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document
from envelopes.models import Envelope
from notifications.models import Notification
from signatures.models import Signature, UserSignature

User = get_user_model()

MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
    b"2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n"
    b"3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
)


class _FakeS3Storage:
    def save(self, key, file_obj):
        file_obj.read()
        return key

    def url(self, key):
        return f"https://fake-s3.local/{key}"


def _embed_signature_side_effect(*args, **kwargs):
    """Write a minimal valid PDF to the output path expected by the signing service."""
    output_path = kwargs.get("output_path")
    if output_path is None and len(args) >= 2:
        output_path = args[1]
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as pdf_file:
            pdf_file.write(MINIMAL_PDF_BYTES)


class SelfSignTestCase(APITestCase):
    """Test cases for POST /api/signatures/self-sign/."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='selfsigner@test.com',
            username='selfsigner',
            full_name='Self Signer',
            password='testpass123',
        )
        self.other_user = User.objects.create_user(
            email='other@test.com',
            username='otheruser',
            full_name='Other User',
            password='testpass123',
        )

        refresh = RefreshToken.for_user(self.user)
        self.token = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

        self.test_signature_image = base64.b64encode(b"test signature data").decode('utf-8')
        self.url = reverse('signatures:self_sign')

    def _create_document(self, owner=None):
        owner = owner or self.user
        return Document.objects.create(
            owner=owner,
            file_url='/test/path/document.pdf',
            file_name='test_document.pdf',
            file_size=1024,
            status='draft',
        )

    def _prepare_local_document_pdf(self, document):
        pdf_dir = os.path.join(str(settings.MEDIA_ROOT), 'tests')
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, f"{document.id}.pdf")
        if not os.path.exists(pdf_path):
            with open(pdf_path, 'wb') as pdf_file:
                pdf_file.write(MINIMAL_PDF_BYTES)

        relative_path = os.path.relpath(pdf_path, str(settings.MEDIA_ROOT))
        document.file_url = f"{settings.MEDIA_URL}{relative_path}"
        document.signed_file_url = None
        document.save(update_fields=['file_url', 'signed_file_url'])
        return pdf_path

    def _self_sign_payload(self, document, **overrides):
        payload = {
            'document_ids': [str(document.id)],
            'name': 'Self-signed agreement',
            'documents_with_positions': [
                {
                    'document_id': str(document.id),
                    'signer_document_positions': [
                        {
                            'position': {
                                'page': 1,
                                'x': 100,
                                'y': 500,
                                'width': 120,
                                'height': 40,
                            },
                        },
                    ],
                },
            ],
            'signature_image': f'data:image/png;base64,{self.test_signature_image}',
        }
        payload.update(overrides)
        return payload

    @patch('signatures.services.signing.get_permanent_s3_storage', return_value=_FakeS3Storage())
    @patch('signatures.services.signing.embed_signature', side_effect=_embed_signature_side_effect)
    def test_self_sign_single_document_happy_path(self, mock_embed, _mock_s3):
        document = self._create_document()
        self._prepare_local_document_pdf(document)

        response = self.client.post(
            self.url,
            self._self_sign_payload(
                document,
                fields=[
                    {
                        'document_id': str(document.id),
                        'page': 1,
                        'x': 100,
                        'y': 600,
                        'width': 200,
                        'height': 24,
                        'type': 'text',
                        'required': True,
                        'value': 'Jane Doe',
                    },
                ],
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        self.assertTrue(response.data['data']['is_self_sign'])
        self.assertEqual(response.data['data']['status'], 'self_signed')
        self.assertTrue(mock_embed.called)

        envelope = Envelope.objects.get(id=response.data['data']['id'])
        self.assertTrue(envelope.is_self_sign)
        document.refresh_from_db()
        self.assertIsNotNone(document.signed_file_url)
        self.assertTrue(document.signed_file_url.startswith('https://fake-s3.local/'))

    @patch('signatures.services.signing.get_permanent_s3_storage', return_value=_FakeS3Storage())
    @patch('signatures.services.signing.embed_signature', side_effect=_embed_signature_side_effect)
    def test_self_sign_multiple_documents(self, mock_embed, _mock_s3):
        document1 = self._create_document()
        document2 = self._create_document()
        self._prepare_local_document_pdf(document1)
        self._prepare_local_document_pdf(document2)

        payload = {
            'document_ids': [str(document1.id), str(document2.id)],
            'name': 'Multi-doc self sign',
            'documents_with_positions': [
                {
                    'document_id': str(document1.id),
                    'signer_document_positions': [
                        {
                            'position': {
                                'page': 1,
                                'x': 100,
                                'y': 500,
                                'width': 120,
                                'height': 40,
                            },
                        },
                    ],
                },
                {
                    'document_id': str(document2.id),
                    'signer_document_positions': [
                        {
                            'position': {
                                'page': 1,
                                'x': 120,
                                'y': 520,
                                'width': 120,
                                'height': 40,
                            },
                        },
                    ],
                },
            ],
            'signature_image': f'data:image/png;base64,{self.test_signature_image}',
        }

        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        envelope = Envelope.objects.get(id=response.data['data']['id'])
        self.assertEqual(envelope.status, 'self_signed')
        self.assertEqual(envelope.envelopedocument_set.count(), 2)
        document1.refresh_from_db()
        document2.refresh_from_db()
        self.assertIsNotNone(document1.signed_file_url)
        self.assertIsNotNone(document2.signed_file_url)
        self.assertEqual(mock_embed.call_count, 2)

    @patch('signatures.services.signing.get_permanent_s3_storage', return_value=_FakeS3Storage())
    @patch('signatures.services.signing.embed_signature', side_effect=_embed_signature_side_effect)
    def test_self_sign_uses_default_user_signature(self, mock_embed, _mock_s3):
        document = self._create_document()
        self._prepare_local_document_pdf(document)

        image_file = SimpleUploadedFile(
            'default.png',
            b'fake-image-bytes',
            content_type='image/png',
        )
        UserSignature.objects.create(
            user=self.user,
            image=image_file,
            is_default=True,
        )

        payload = self._self_sign_payload(document)
        payload.pop('signature_image', None)

        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(mock_embed.called)

        signature = Signature.objects.get(envelope_id=response.data['data']['id'])
        self.assertEqual(signature.status, 'signed')
        self.assertIsNotNone(signature.signature_image)

    def test_self_sign_rejects_other_user_documents(self):
        foreign_document = self._create_document(owner=self.other_user)
        response = self.client.post(
            self.url,
            self._self_sign_payload(foreign_document),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_self_sign_required_field_missing_value(self):
        document = self._create_document()
        response = self.client.post(
            self.url,
            self._self_sign_payload(
                document,
                fields=[
                    {
                        'document_id': str(document.id),
                        'page': 1,
                        'x': 100,
                        'y': 600,
                        'width': 200,
                        'height': 24,
                        'type': 'text',
                        'required': True,
                    },
                ],
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('signatures.services.signing.get_permanent_s3_storage', return_value=_FakeS3Storage())
    @patch('signatures.services.signing.embed_signature', side_effect=_embed_signature_side_effect)
    def test_self_sign_cannot_be_sent(self, mock_embed, _mock_s3):
        document = self._create_document()
        self._prepare_local_document_pdf(document)

        response = self.client.post(
            self.url,
            self._self_sign_payload(document),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        envelope_id = response.data['data']['id']

        send_url = reverse('envelopes:envelope_send', kwargs={'pk': envelope_id})
        send_response = self.client.post(send_url)
        self.assertEqual(send_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Self-signed envelopes cannot be sent', send_response.data['message'])

    @patch('signatures.services.signing.get_permanent_s3_storage', return_value=_FakeS3Storage())
    @patch('signatures.services.signing.embed_signature', side_effect=_embed_signature_side_effect)
    def test_list_filter_is_self_sign_true(self, mock_embed, _mock_s3):
        document = self._create_document()
        self._prepare_local_document_pdf(document)

        regular_envelope = Envelope.objects.create(
            creator=self.user,
            status='draft',
            signing_order=[{'signer_id': str(self.user.id), 'order': 1}],
            is_self_sign=False,
        )

        self.client.post(self.url, self._self_sign_payload(document), format='json')

        list_url = reverse('envelopes:envelope_list')
        response = self.client.get(list_url, {'is_self_sign': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        returned_ids = {item['id'] for item in response.data['data']['results']}
        self.assertNotIn(str(regular_envelope.id), returned_ids)
        self.assertEqual(len(returned_ids), 1)

    @patch('notifications.utils.create_notification')
    @patch('signatures.services.signing.get_permanent_s3_storage', return_value=_FakeS3Storage())
    @patch('signatures.services.signing.embed_signature', side_effect=_embed_signature_side_effect)
    def test_no_notifications_created(self, mock_embed, _mock_s3, mock_create_notification):
        document = self._create_document()
        self._prepare_local_document_pdf(document)
        initial_count = Notification.objects.count()

        response = self.client.post(
            self.url,
            self._self_sign_payload(document),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Notification.objects.count(), initial_count)
        mock_create_notification.assert_not_called()
