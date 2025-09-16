"""
Unit tests for signature functionality.

This module tests the signature signing and declining endpoints
and their validation logic.
"""

import uuid
import base64
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from signatures.models import Signature
from envelopes.models import Envelope
from documents.models import Document

User = get_user_model()


class SignatureTestCase(APITestCase):
    """
    Test cases for signature signing and declining endpoints.
    """
    
    def setUp(self):
        """Set up test data."""
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
            document=self.document,
            creator=self.creator,
            status='draft',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 2},
                {'signer_id': str(self.signer3.id), 'order': 3}
            ]
        )
        
        # Send the envelope to create signature records
        self.envelope.status = 'sent'
        self.envelope.save()
        
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
    
    def test_first_signer_can_sign_successfully(self):
        """Test that the first signer can sign successfully."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        # Set authentication header for first signer
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        payload = {
            'signature_image': self.test_signature_image
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'Document signed successfully')
        self.assertEqual(response.data['data']['status'], 'signed')
        
        # Verify signature was updated in database
        self.signature1.refresh_from_db()
        self.assertEqual(self.signature1.status, 'signed')
        self.assertIsNotNone(self.signature1.signed_at)
        self.assertEqual(self.signature1.signature_image, self.test_signature_image)
    
    def test_signing_unlocks_next_signer(self):
        """Test that signing unlocks the next signer."""
        # First signer signs
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        payload = {'signature_image': self.test_signature_image}
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify first signer is signed
        self.signature1.refresh_from_db()
        self.assertEqual(self.signature1.status, 'signed')
        
        # Now second signer should be able to sign
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Verify second signer is signed
        self.signature2.refresh_from_db()
        self.assertEqual(self.signature2.status, 'signed')
    
    def test_final_signer_signing_marks_envelope_completed(self):
        """Test that final signer signing marks envelope as completed."""
        # First two signers sign
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        payload = {'signature_image': self.test_signature_image}
        
        # Signer 1 signs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        self.client.post(url, payload, format='json')
        
        # Signer 2 signs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
        self.client.post(url, payload, format='json')
        
        # Verify envelope is still sent
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, 'sent')
        
        # Signer 3 signs (final signer)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer3_token}')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Verify envelope is now completed
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.status, 'completed')
        
        # Verify third signer is signed
        self.signature3.refresh_from_db()
        self.assertEqual(self.signature3.status, 'signed')
    
    def test_signer_can_decline_marking_envelope_rejected(self):
        """Test that signer can decline, marking envelope as rejected."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Set authentication header for first signer
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
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
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
        payload = {'signature_image': self.test_signature_image}
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], "It's not your turn to sign yet. Please wait for your turn.")
        
        # Verify signature was not updated
        self.signature2.refresh_from_db()
        self.assertEqual(self.signature2.status, 'pending')
    
    def test_non_current_signer_attempting_decline_returns_403(self):
        """Test that non-current signer attempting to decline returns 403."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Try to decline with second signer (not current)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], "It's not your turn to decline yet. Please wait for your turn.")
        
        # Verify signature was not updated
        self.signature2.refresh_from_db()
        self.assertEqual(self.signature2.status, 'pending')
    
    def test_unauthorized_user_attempting_sign_returns_403(self):
        """Test that unauthorized user attempting to sign returns 403."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        # Try to sign with user not in signing order
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.other_token}')
        payload = {'signature_image': self.test_signature_image}
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], "You are not authorized to sign this document.")
    
    def test_unauthorized_user_attempting_decline_returns_403(self):
        """Test that unauthorized user attempting to decline returns 403."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Try to decline with user not in signing order
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.other_token}')
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], "You are not authorized to decline this document.")
    
    def test_unauthenticated_sign_request_returns_401(self):
        """Test that unauthenticated sign request returns 401."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        # Remove authentication
        self.client.credentials()
        payload = {'signature_image': self.test_signature_image}
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_unauthenticated_decline_request_returns_401(self):
        """Test that unauthenticated decline request returns 401."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        # Remove authentication
        self.client.credentials()
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_signing_draft_envelope_returns_400(self):
        """Test that signing a draft envelope returns 400."""
        # Create a draft envelope
        draft_envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            status='draft',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        )
        
        url = reverse('signatures:sign_document', kwargs={'envelope_id': draft_envelope.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        payload = {'signature_image': self.test_signature_image}
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn("must be in 'sent' status", response.data['message'])
    
    def test_declining_draft_envelope_returns_400(self):
        """Test that declining a draft envelope returns 400."""
        # Create a draft envelope
        draft_envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            status='draft',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        )
        
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': draft_envelope.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn("must be in 'sent' status", response.data['message'])
    
    def test_signing_already_signed_document_returns_403(self):
        """Test that signing an already signed document returns 403 (not current signer)."""
        # First signer signs
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        payload = {'signature_image': self.test_signature_image}
        self.client.post(url, payload, format='json')
        
        # Try to sign again (now signer1 is no longer current signer)
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], "It's not your turn to sign yet. Please wait for your turn.")
    
    def test_declining_already_signed_document_returns_403(self):
        """Test that declining an already signed document returns 403 (not current signer)."""
        # First signer signs
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        payload = {'signature_image': self.test_signature_image}
        self.client.post(url, payload, format='json')
        
        # Try to decline (now signer1 is no longer current signer)
        decline_url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        response = self.client.post(decline_url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], "It's not your turn to decline yet. Please wait for your turn.")
    
    def test_signing_with_invalid_signature_image_returns_400(self):
        """Test that signing with invalid signature image returns 400."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        # Test with empty signature image
        payload = {'signature_image': ''}
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('signature_image', response.data['errors'])
        
        # Test with invalid base64
        payload = {'signature_image': 'invalid-base64-data!'}
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('valid base64', response.data['errors']['signature_image'][0])
    
    def test_signing_nonexistent_envelope_returns_404(self):
        """Test that signing nonexistent envelope returns 404."""
        nonexistent_id = uuid.uuid4()
        url = reverse('signatures:sign_document', kwargs={'envelope_id': nonexistent_id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        payload = {'signature_image': self.test_signature_image}
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_declining_nonexistent_envelope_returns_404(self):
        """Test that declining nonexistent envelope returns 404."""
        nonexistent_id = uuid.uuid4()
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': nonexistent_id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_sign_response_contains_correct_data_structure(self):
        """Test that sign response contains correct data structure."""
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        payload = {'signature_image': self.test_signature_image}
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check response structure
        self.assertIn('success', response.data)
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
        self.assertEqual(data['status'], 'signed')
        self.assertEqual(data['signer_email'], self.signer1.email)
        self.assertEqual(data['signing_order'], 1)
    
    def test_decline_response_contains_correct_data_structure(self):
        """Test that decline response contains correct data structure."""
        url = reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check response structure
        self.assertIn('success', response.data)
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
