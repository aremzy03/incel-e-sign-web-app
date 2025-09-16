"""
Unit tests for envelope send and reject functionality.

This module tests the envelope send and reject endpoints and their
validation logic.
"""

import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from envelopes.models import Envelope
from documents.models import Document

User = get_user_model()


class EnvelopeSendRejectTestCase(APITestCase):
    """
    Test cases for envelope send and reject endpoints.
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
        
        self.other_user = User.objects.create_user(
            email='other@test.com',
            username='other',
            full_name='Other User',
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
        
        # Create test document
        self.document = Document.objects.create(
            owner=self.creator,
            file_url='/test/path/document.pdf',
            file_name='test_document.pdf',
            file_size=1024,
            status='draft'
        )
        
        # Create test envelopes with different statuses
        self.draft_envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            status='draft',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 2}
            ]
        )
        
        self.sent_envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            status='sent',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        )
        
        self.completed_envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            status='completed',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        )
        
        self.rejected_envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            status='rejected',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        )
        
        # Create envelope owned by other user
        self.other_document = Document.objects.create(
            owner=self.other_user,
            file_url='/test/path/other_document.pdf',
            file_name='other_document.pdf',
            file_size=1024,
            status='draft'
        )
        
        self.other_envelope = Envelope.objects.create(
            document=self.other_document,
            creator=self.other_user,
            status='draft',
            signing_order=[
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        )
        
        # Get JWT tokens for authentication
        creator_refresh = RefreshToken.for_user(self.creator)
        self.creator_token = str(creator_refresh.access_token)
        
        other_refresh = RefreshToken.for_user(self.other_user)
        self.other_token = str(other_refresh.access_token)
    
    def test_creator_can_successfully_send_draft_envelope(self):
        """Test that creator can successfully send a draft envelope."""
        url = reverse('envelopes:envelope_send', kwargs={'pk': self.draft_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'Envelope sent successfully')
        self.assertEqual(response.data['data']['status'], 'sent')
        
        # Verify envelope status was updated in database
        self.draft_envelope.refresh_from_db()
        self.assertEqual(self.draft_envelope.status, 'sent')
    
    def test_sending_changes_status_from_draft_to_sent(self):
        """Test that sending changes status from draft → sent."""
        url = reverse('envelopes:envelope_send', kwargs={'pk': self.draft_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        # Verify initial status
        self.assertEqual(self.draft_envelope.status, 'draft')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify status changed
        self.draft_envelope.refresh_from_db()
        self.assertEqual(self.draft_envelope.status, 'sent')
    
    def test_creator_can_successfully_reject_envelope(self):
        """Test that creator can successfully reject an envelope."""
        url = reverse('envelopes:envelope_reject', kwargs={'pk': self.draft_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'Envelope rejected successfully')
        self.assertEqual(response.data['data']['status'], 'rejected')
        
        # Verify envelope status was updated in database
        self.draft_envelope.refresh_from_db()
        self.assertEqual(self.draft_envelope.status, 'rejected')
    
    def test_rejecting_changes_status_to_rejected(self):
        """Test that rejecting changes status to rejected."""
        url = reverse('envelopes:envelope_reject', kwargs={'pk': self.draft_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        # Verify initial status
        self.assertEqual(self.draft_envelope.status, 'draft')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify status changed
        self.draft_envelope.refresh_from_db()
        self.assertEqual(self.draft_envelope.status, 'rejected')
    
    def test_non_creator_attempting_send_returns_403_forbidden(self):
        """Test that non-creator attempting send returns 403 Forbidden."""
        url = reverse('envelopes:envelope_send', kwargs={'pk': self.draft_envelope.id})
        
        # Set authentication header for other user
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.other_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], 'You can only send envelopes you created.')
        
        # Verify envelope status was not changed
        self.draft_envelope.refresh_from_db()
        self.assertEqual(self.draft_envelope.status, 'draft')
    
    def test_non_creator_attempting_reject_returns_403_forbidden(self):
        """Test that non-creator attempting reject returns 403 Forbidden."""
        url = reverse('envelopes:envelope_reject', kwargs={'pk': self.draft_envelope.id})
        
        # Set authentication header for other user
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.other_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], 'You can only reject envelopes you created.')
        
        # Verify envelope status was not changed
        self.draft_envelope.refresh_from_db()
        self.assertEqual(self.draft_envelope.status, 'draft')
    
    def test_sending_non_draft_envelope_returns_validation_error(self):
        """Test that sending a non-draft envelope returns validation error."""
        # Test with sent envelope
        url = reverse('envelopes:envelope_send', kwargs={'pk': self.sent_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('Only draft envelopes can be sent', response.data['message'])
        self.assertIn('Current status: sent', response.data['message'])
        
        # Verify envelope status was not changed
        self.sent_envelope.refresh_from_db()
        self.assertEqual(self.sent_envelope.status, 'sent')
    
    def test_sending_completed_envelope_returns_validation_error(self):
        """Test that sending a completed envelope returns validation error."""
        url = reverse('envelopes:envelope_send', kwargs={'pk': self.completed_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('Only draft envelopes can be sent', response.data['message'])
        self.assertIn('Current status: completed', response.data['message'])
        
        # Verify envelope status was not changed
        self.completed_envelope.refresh_from_db()
        self.assertEqual(self.completed_envelope.status, 'completed')
    
    def test_sending_rejected_envelope_returns_validation_error(self):
        """Test that sending a rejected envelope returns validation error."""
        url = reverse('envelopes:envelope_send', kwargs={'pk': self.rejected_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('Only draft envelopes can be sent', response.data['message'])
        self.assertIn('Current status: rejected', response.data['message'])
        
        # Verify envelope status was not changed
        self.rejected_envelope.refresh_from_db()
        self.assertEqual(self.rejected_envelope.status, 'rejected')
    
    def test_rejecting_any_status_envelope_succeeds(self):
        """Test that rejecting an envelope of any status succeeds."""
        # Test rejecting sent envelope
        url = reverse('envelopes:envelope_reject', kwargs={'pk': self.sent_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['status'], 'rejected')
        
        # Verify envelope status was updated
        self.sent_envelope.refresh_from_db()
        self.assertEqual(self.sent_envelope.status, 'rejected')
    
    def test_rejecting_completed_envelope_succeeds(self):
        """Test that rejecting a completed envelope succeeds."""
        url = reverse('envelopes:envelope_reject', kwargs={'pk': self.completed_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['status'], 'rejected')
        
        # Verify envelope status was updated
        self.completed_envelope.refresh_from_db()
        self.assertEqual(self.completed_envelope.status, 'rejected')
    
    def test_unauthenticated_send_request_returns_401(self):
        """Test unauthenticated send request returns 401."""
        url = reverse('envelopes:envelope_send', kwargs={'pk': self.draft_envelope.id})
        
        # Remove authentication
        self.client.credentials()
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Verify envelope status was not changed
        self.draft_envelope.refresh_from_db()
        self.assertEqual(self.draft_envelope.status, 'draft')
    
    def test_unauthenticated_reject_request_returns_401(self):
        """Test unauthenticated reject request returns 401."""
        url = reverse('envelopes:envelope_reject', kwargs={'pk': self.draft_envelope.id})
        
        # Remove authentication
        self.client.credentials()
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Verify envelope status was not changed
        self.draft_envelope.refresh_from_db()
        self.assertEqual(self.draft_envelope.status, 'draft')
    
    def test_send_nonexistent_envelope_returns_404(self):
        """Test sending nonexistent envelope returns 404."""
        nonexistent_id = uuid.uuid4()
        url = reverse('envelopes:envelope_send', kwargs={'pk': nonexistent_id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_reject_nonexistent_envelope_returns_404(self):
        """Test rejecting nonexistent envelope returns 404."""
        nonexistent_id = uuid.uuid4()
        url = reverse('envelopes:envelope_reject', kwargs={'pk': nonexistent_id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_send_response_contains_correct_data_structure(self):
        """Test that send response contains correct data structure."""
        url = reverse('envelopes:envelope_send', kwargs={'pk': self.draft_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check response structure
        self.assertIn('success', response.data)
        self.assertIn('message', response.data)
        self.assertIn('data', response.data)
        
        # Check data structure
        data = response.data['data']
        self.assertIn('id', data)
        self.assertIn('document', data)
        self.assertIn('creator', data)
        self.assertIn('status', data)
        self.assertIn('signing_order', data)
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)
        
        # Verify data values
        self.assertEqual(data['id'], str(self.draft_envelope.id))
        self.assertEqual(data['status'], 'sent')
    
    def test_reject_response_contains_correct_data_structure(self):
        """Test that reject response contains correct data structure."""
        url = reverse('envelopes:envelope_reject', kwargs={'pk': self.draft_envelope.id})
        
        # Set authentication header for creator
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check response structure
        self.assertIn('success', response.data)
        self.assertIn('message', response.data)
        self.assertIn('data', response.data)
        
        # Check data structure
        data = response.data['data']
        self.assertIn('id', data)
        self.assertIn('document', data)
        self.assertIn('creator', data)
        self.assertIn('status', data)
        self.assertIn('signing_order', data)
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)
        
        # Verify data values
        self.assertEqual(data['id'], str(self.draft_envelope.id))
        self.assertEqual(data['status'], 'rejected')
