"""
Unit tests for signature functionality.

This module tests the signature signing and declining endpoints
and their validation logic.
"""

import base64
import os
import uuid
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from signatures.models import Signature
from envelopes.models import Envelope, EnvelopeDocument # Import EnvelopeDocument
from documents.models import Document
from fields.models import Field

User = get_user_model()


class SignatureTestCase(APITestCase):
    """
    Test cases for signature signing and declining endpoints.
    """
    
    def setUp(self):
        """Set up test data."""
        # Clear leftover client auth from other suite tests.
        self.client.force_authenticate(user=None)
        self.client.credentials()

        # Create test users
        self.creator = User.objects.create_user(
            email='creator@test.com',
            username='creator',
            full_name='Test Creator',
            password='testpass123'
        )
        
        self.signer1 = User.objects.create_user(
            email='signer1@test.com',
            username='signer1',
            full_name='Test Signer 1',
            password='testpass123'
        )
        
        self.signer2 = User.objects.create_user(
            email='signer2@test.com',
            username='signer2',
            full_name='Test Signer 2',
            password='testpass123'
        )
        
        self.signer3 = User.objects.create_user(
            email='signer3@test.com',
            username='signer3',
            full_name='Test Signer 3',
            password='testpass123'
        )
        
        self.other_user = User.objects.create_user(
            email='other@test.com',
            username='other',
            full_name='Other User',
            password='testpass123'
        )
        
        # Create test document
        self.document = Document.objects.create(
            owner=self.creator,
            file_url='/test/path/document.pdf',
            file_name='test_document.pdf',
            file_size=1024,
            status='draft'
        )
        
        # Create test envelope with multiple signers
        self.envelope = Envelope.objects.create(
            creator=self.creator,
            name="Test Envelope",
            status='pending',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 2},
                {'signer_id': str(self.signer3.id), 'order': 3}
            ]
        )
        EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document, order=1)
        
        # Send the envelope to create signature records (status is pending after send)
        # Note: Envelope status is already 'pending' in creation, so no explicit send action here
        
        # Create signature records manually (simulating the send process)
        self.signature1 = Signature.objects.create(
            envelope=self.envelope,
            signer=self.signer1,
            status='pending'
        )
        
        self.signature2 = Signature.objects.create(
            envelope=self.envelope,
            signer=self.signer2,
            status='pending'
        )
        
        self.signature3 = Signature.objects.create(
            envelope=self.envelope,
            signer=self.signer3,
            status='pending'
        )
        
        # Create a test signature image (base64 encoded)
        self.test_signature_image = base64.b64encode(b"test signature data").decode('utf-8')
        
        # Get JWT tokens for authentication
        signer1_refresh = RefreshToken.for_user(self.signer1)
        self.signer1_token = str(signer1_refresh.access_token)
        
        signer2_refresh = RefreshToken.for_user(self.signer2)
        self.signer2_token = str(signer2_refresh.access_token)
        
        signer3_refresh = RefreshToken.for_user(self.signer3)
        self.signer3_token = str(signer3_refresh.access_token)
        
        other_refresh = RefreshToken.for_user(self.other_user)
        self.other_token = str(other_refresh.access_token)

        self._prepare_local_document_pdf(self.document)
        self._upload_completed_patcher = patch(
            'signatures.services.signing.upload_completed_pdf',
            side_effect=lambda e, d, p: f'https://fake-s3.local/completed/{e}/{d}.pdf',
        )
        self._upload_completed_patcher.start()

    def tearDown(self):
        self.client.force_authenticate(user=None)
        self.client.credentials()
        self._upload_completed_patcher.stop()
        super().tearDown()

    def authenticate_as(self, user):
        """Authenticate via force_authenticate to avoid suite JWT pollution."""
        self.client.credentials()
        self.client.force_authenticate(user=user)

    def _assert_sign_queued(self, response):
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'], 'Signing job queued')
        self.assertIn('job_id', response.data['data'])
    def _prepare_local_document_pdf(self, document):
        pdf_dir = os.path.join(str(settings.MEDIA_ROOT), 'tests')
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, f"{document.id}.pdf")
        if not os.path.exists(pdf_path):
            with open(pdf_path, 'wb') as pdf_file:
                pdf_file.write(b'%PDF-1.4 test pdf content')

        relative_path = os.path.relpath(pdf_path, str(settings.MEDIA_ROOT))
        document.file_url = f"{settings.MEDIA_URL}{relative_path}"
        document.signed_file_url = None
        document.save(update_fields=['file_url', 'signed_file_url'])
        return pdf_path

    def test_first_signer_can_sign_successfully(self):
        """Test that the first signer can sign successfully."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        # Set authentication header for first signer
        self.authenticate_as(self.signer1)
        
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        response = self.client.post(url, payload, format='json')
        
        self._assert_sign_queued(response)
        
        # Verify signature was updated in database
        self.signature1.refresh_from_db()
        self.assertEqual(self.signature1.status, 'signed')
        self.assertIsNotNone(self.signature1.signed_at)
        self.assertIsNotNone(self.signature1.signature_image)
    
    def test_signing_unlocks_next_signer(self):
        """Test that signing unlocks the next signer."""
        # First signer signs
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.authenticate_as(self.signer1)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        response = self.client.post(url, payload, format='json')
        
        self._assert_sign_queued(response)
        
        # Verify first signer is signed
        self.signature1.refresh_from_db()
        self.assertEqual(self.signature1.status, 'signed')
        
        # Now second signer should be able to sign
        self.authenticate_as(self.signer2)
        response = self.client.post(url, payload, format='json')
        
        self._assert_sign_queued(response)
        
        # Verify second signer is signed
        self.signature2.refresh_from_db()
        self.assertEqual(self.signature2.status, 'signed')
    
    def test_final_signer_signing_marks_envelope_completed(self):
        """Test that final signer signing marks envelope as completed."""
        # First two signers sign
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        # Signer 1 signs
        self.authenticate_as(self.signer1)
        self.client.post(url, payload, format='json')
        
        # Signer 2 signs
        self.authenticate_as(self.signer2)
        self.client.post(url, payload, format='json')
        
        # Verify envelope is still pending
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, 'pending') # Status is pending, not sent
        
        # Signer 3 signs (final signer)
        self.authenticate_as(self.signer3)
        response = self.client.post(url, payload, format='json')
        
        self._assert_sign_queued(response)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify envelope is now completed
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, 'completed')
        self.assertIsNotNone(self.envelope.pdf_lock_password)
        self.assertGreaterEqual(len(self.envelope.pdf_lock_password), 8)
        
        # Verify third signer is signed
        self.signature3.refresh_from_db()
        self.assertEqual(self.signature3.status, 'signed')

        # Ensure envelope detail surface exposes the PDF lock password to participants.
        detail_url = reverse('envelopes:envelope_detail', kwargs={'pk': self.envelope.id})
        self.authenticate_as(self.signer3)
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data['data']['pdf_lock_password'], self.envelope.pdf_lock_password)

    def test_completion_can_skip_pdf_password_protection(self):
        """If disabled, envelope completes without generating a PDF lock password."""
        # Disable password protection for this envelope
        self.envelope.pdf_password_protection_enabled = False
        self.envelope.pdf_lock_password = None
        self.envelope.save(update_fields=["pdf_password_protection_enabled", "pdf_lock_password", "updated_at"])

        # First two signers sign
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }

        self.authenticate_as(self.signer1)
        self.client.post(url, payload, format='json')

        self.authenticate_as(self.signer2)
        self.client.post(url, payload, format='json')

        # Final signer completes the envelope
        self.authenticate_as(self.signer3)
        response = self.client.post(url, payload, format='json')
        self._assert_sign_queued(response)

        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, 'completed')
        self.assertFalse(self.envelope.pdf_password_protection_enabled)
        self.assertIsNone(self.envelope.pdf_lock_password)

        # Ensure envelope detail still works and reports null password
        detail_url = reverse('envelopes:envelope_detail', kwargs={'pk': self.envelope.id})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(detail_response.data['data']['pdf_lock_password'])
    
    @patch('signatures.services.signing.embed_signature')
    def test_signature_x_offset_applied(self, mock_embed):
        """Ensure signatures are offset along the X-axis when embedded."""
        env_doc = self.envelope.envelopedocument_set.first()
        env_doc.signer_document_positions = [
            {
                'signer_id': str(self.signer1.id),
                'position': {
                    'page': 1,
                    'x': 150,
                    'y': 100,
                    'width': 120,
                    'height': 40,
                },
            }
        ]
        env_doc.save()

        document = env_doc.document
        self._prepare_local_document_pdf(document)

        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }

        self.authenticate_as(self.signer1)
        response = self.client.post(url, payload, format='json')

        self._assert_sign_queued(response)
        self.assertTrue(mock_embed.called)
        offset_x = mock_embed.call_args.kwargs['x']
        self.assertEqual(offset_x, 155.0)

    @patch('signatures.services.signing.embed_text')
    @patch('signatures.services.signing.embed_signature')
    def test_field_x_offset_applied(self, mock_embed_signature, mock_embed_text):
        """Ensure non-signature fields are offset along the X-axis when flattened."""
        env_doc = self.envelope.envelopedocument_set.first()
        document = env_doc.document

        env_doc.signer_document_positions = [
            {
                'signer_id': str(self.signer1.id),
                'position': {
                    'page': 1,
                    'x': 150,
                    'y': 100,
                    'width': 120,
                    'height': 40,
                },
            }
        ]
        env_doc.save()

        self._prepare_local_document_pdf(document)

        Field.objects.create(
            envelope=self.envelope,
            document=document,
            page=1,
            x=200,
            y=150,
            width=120,
            height=30,
            type=Field.FieldType.TEXT,
            assigned_signer=self.signer1,
            required=True,
            prefill_value="Hello",
            font_family="Helvetica",
            font_size=12,
        )

        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }

        self.authenticate_as(self.signer1)
        response = self.client.post(url, payload, format='json')

        self._assert_sign_queued(response)
        self.assertTrue(mock_embed_text.called)
        offset_x = mock_embed_text.call_args.kwargs['x']
        self.assertEqual(offset_x, 205.0)

    def test_signer_can_decline_marking_envelope_rejected(self):
        """Test that signer can decline, marking envelope as rejected."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Set authentication header for first signer
        self.authenticate_as(self.signer1)
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'], 'Document declined successfully. Envelope has been rejected.')
        self.assertEqual(response.data['data']['status'], 'declined')
        
        # Verify signature was declined
        self.signature1.refresh_from_db()
        self.assertEqual(self.signature1.status, 'declined')
        
        # Verify envelope was rejected
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, 'rejected')
    
    def test_non_current_signer_attempting_sign_returns_403(self):
        """Test that non-current signer attempting to sign returns 403."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        # Try to sign with second signer (not current)
        self.authenticate_as(self.signer2)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], "It's not your turn to sign yet. Please wait for your turn.")
        
        # Verify signature was not updated
        self.signature2.refresh_from_db()
        self.assertEqual(self.signature2.status, 'pending')
    
    def test_non_current_signer_attempting_decline_returns_403(self):
        """Test that non-current signer attempting to decline returns 403."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Try to decline with second signer (not current)
        self.authenticate_as(self.signer2)
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], "It's not your turn to decline yet. Please wait for your turn.")
        
        # Verify signature was not updated
        self.signature2.refresh_from_db()
        self.assertEqual(self.signature2.status, 'pending')
    
    def test_unauthorized_user_attempting_sign_returns_403(self):
        """Test that unauthorized user attempting to sign returns 403."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        # Try to sign with user not in signing order
        self.authenticate_as(self.other_user)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], "You are not authorized to sign this document.")
    
    def test_unauthorized_user_attempting_decline_returns_403(self):
        """Test that unauthorized user attempting to decline returns 403."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Try to decline with user not in signing order
        self.authenticate_as(self.other_user)
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], "You are not authorized to decline this document.")
    
    def test_unauthenticated_sign_request_returns_401(self):
        """Test that unauthenticated sign request returns 401."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        # Remove authentication
        self.client.force_authenticate(user=None)
        self.client.credentials()
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_unauthenticated_decline_request_returns_401(self):
        """Test that unauthenticated decline request returns 401."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Remove authentication
        self.client.force_authenticate(user=None)
        self.client.credentials()
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_signing_draft_envelope_returns_400(self):
        """Test that signing a draft envelope returns 400."""
        # Create a draft envelope
        draft_envelope = Envelope.objects.create(
            creator=self.creator,
            name="Draft Envelope for Signing Test",
            status='draft',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        )
        EnvelopeDocument.objects.create(envelope=draft_envelope, document=self.document, order=1)
        
        url = reverse('signatures:sign_document', kwargs={'envelope_id': draft_envelope.id})
        
        self.authenticate_as(self.signer1)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn("must be in 'pending' status", response.data['message'])
    
    def test_declining_draft_envelope_returns_400(self):
        """Test that declining a draft envelope returns 400."""
        # Create a draft envelope
        draft_envelope = Envelope.objects.create(
            creator=self.creator,
            name="Draft Envelope for Declining Test",
            status='draft',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        )
        EnvelopeDocument.objects.create(envelope=draft_envelope, document=self.document, order=1)
        
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': draft_envelope.id})
        
        self.authenticate_as(self.signer1)
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn("must be in 'pending' status", response.data['message'])
    
    def test_signing_already_signed_document_returns_403(self):
        """Test that signing an already signed document returns 403 (not current signer)."""
        # First signer signs
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.authenticate_as(self.signer1)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        self.client.post(url, payload, format='json')
        
        # Try to sign again (now signer1 is no longer current signer)
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], "It's not your turn to sign yet. Please wait for your turn.")
    
    def test_declining_already_signed_document_returns_403(self):
        """Test that declining an already signed document returns 403 (not current signer)."""
        # First signer signs
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.authenticate_as(self.signer1)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        self.client.post(url, payload, format='json')
        
        # Try to decline (now signer1 is no longer current signer)
        decline_url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        response = self.client.post(decline_url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], "It's not your turn to decline yet. Please wait for your turn.")
    
    def test_signing_with_invalid_signature_image_returns_400(self):
        """Test that signing with invalid signature image returns 400."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.authenticate_as(self.signer1)
        
        # Test with empty signature image
        payload = {'signature_image': ''}
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        print(f"DEBUG: Response data for empty signature image: {response.data}") # Debug print
        self.assertIn('No signature provided and no default signature found', response.data['message'])
        
        # Test with invalid base64
        payload = {'signature_image': 'invalid-base64-data!'}
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signature_image', response.data['data'])
        self.assertEqual(response.data['data']['signature_image'][0], 'Signature image must be valid base64 encoded data.')
    
    def test_signing_nonexistent_envelope_returns_404(self):
        """Test that signing nonexistent envelope returns 404."""
        nonexistent_id = uuid.uuid4()
        url = reverse('signatures:sign_document', kwargs={'envelope_id': nonexistent_id})
        
        self.authenticate_as(self.signer1)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_declining_nonexistent_envelope_returns_404(self):
        """Test that declining nonexistent envelope returns 404."""
        nonexistent_id = uuid.uuid4()
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': nonexistent_id})

        self.authenticate_as(self.signer1)

        response = self.client.post(url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_sign_response_contains_correct_data_structure(self):
        """Test that sign response contains correct data structure."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.authenticate_as(self.signer1)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        response = self.client.post(url, payload, format='json')
        
        self._assert_sign_queued(response)
        
        # Check response structure
        self.assertIn('status', response.data)
        self.assertIn('message', response.data)
        self.assertIn('data', response.data)
        
        data = response.data['data']
        self.assertIn('job_id', data)
        self.assertIn('status', data)
        self.assertIn('envelope_id', data)
    
    def test_decline_response_contains_correct_data_structure(self):
        """Test that decline response contains correct data structure."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        self.authenticate_as(self.signer1)
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check response structure
        self.assertIn('status', response.data)
        self.assertIn('message', response.data)
        self.assertIn('data', response.data)
        
        # Check data structure
        data = response.data['data']
        self.assertIn('id', data)
        self.assertIn('signer', data)
        self.assertIn('signer_email', data)
        self.assertIn('signer_name', data)
        self.assertIn('status', data)
        self.assertIn('signing_order', data)
        self.assertIn('signed_at', data)
        self.assertIn('signature_image', data)
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)
        
        # Verify data values
        self.assertEqual(data['status'], 'declined')
        self.assertEqual(data['signer_email'], self.signer1.email)
        self.assertEqual(data['signing_order'], 1)
    
    def test_signer_attempting_to_sign_out_of_turn(self):
        """Test that signer attempting to sign out of turn is rejected."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        # Try to sign as signer2 (order 2) before signer1 (order 1) has signed
        self.authenticate_as(self.signer2)
        payload = {
            'signature_image': self.test_signature_image,
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        response = self.client.post(url, payload, format='json')
        
        # Should be rejected - it's not signer2's turn yet
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('not your turn to sign yet', response.data['message'])
        
        # Verify signature was not updated
        signer2_signature = Signature.objects.get(
            envelope=self.envelope,
            signer=self.signer2
        )
        self.assertEqual(signer2_signature.status, 'pending')
        self.assertIsNone(signer2_signature.signed_at)
    
    def test_signer_attempting_to_decline_out_of_turn(self):
        """Test that signer attempting to decline out of turn is rejected."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Try to decline as signer2 (order 2) before signer1 (order 1) has acted
        self.authenticate_as(self.signer2)
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('not your turn to decline yet', response.data['message'])
        
        # Verify signature was not updated
        signer2_signature = Signature.objects.get(
            envelope=self.envelope,
            signer=self.signer2
        )
        self.assertEqual(signer2_signature.status, 'pending')