"""
Unit tests for envelope creation functionality.

This module tests the envelope creation endpoint and serializer
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


class EnvelopeCreationTestCase(APITestCase):
    """
    Test cases for envelope creation endpoint.
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
        
        # Get JWT token for authentication
        refresh = RefreshToken.for_user(self.creator)
        self.token = str(refresh.access_token)
        
        # Set up authentication header
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
    
    def test_successful_envelope_creation_with_valid_document_and_signers(self):
        """Test successful envelope creation with valid document and signers."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 2}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'], 'Envelope created successfully')
        
        # Check envelope was created in database
        envelope = Envelope.objects.get(id=response.data['data']['id'])
        self.assertEqual(envelope.document, self.document)
        self.assertEqual(envelope.creator, self.creator)
        self.assertEqual(envelope.status, 'draft')
        self.assertEqual(len(envelope.signing_order), 2)
        self.assertEqual(envelope.signing_order[0]['signer_id'], str(self.signer1.id))
        self.assertEqual(envelope.signing_order[1]['signer_id'], str(self.signer2.id))
    
    def test_envelope_creation_fails_if_document_doesnt_belong_to_creator(self):
        """Test creation fails if document doesn't belong to creator."""
        # Create document owned by other user
        other_document = Document.objects.create(
            owner=self.other_user,
            file_url='/test/path/other_document.pdf',
            file_name='other_document.pdf',
            file_size=1024,
            status='draft'
        )
        
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(other_document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('document_id', response.data['data'])
        self.assertIn('own documents', response.data['data']['document_id'][0])
    
    def test_envelope_creation_fails_if_invalid_user_id_in_signing_order(self):
        """Test creation fails if invalid user_id is in signing_order."""
        url = reverse('envelopes:envelope_create')
        
        # Use non-existent user ID
        invalid_user_id = str(uuid.uuid4())
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': invalid_user_id, 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('Users not found', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_fails_if_signing_order_has_duplicate_orders(self):
        """Test creation fails if signing_order has duplicate orders."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 1}  # Duplicate order
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('Duplicate order found', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_fails_if_signing_order_has_duplicate_signer_ids(self):
        """Test creation fails if signing_order has duplicate signer_ids."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer1.id), 'order': 2}  # Duplicate signer_id
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('Duplicate signer_id found', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_fails_if_signing_order_has_gaps(self):
        """Test creation fails if signing_order has gaps in order numbers."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 3}  # Gap: missing order 2
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('no gaps', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_fails_if_signing_order_doesnt_start_from_1(self):
        """Test creation fails if signing_order doesn't start from 1."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 2},  # Should start from 1
                {'signer_id': str(self.signer2.id), 'order': 3}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('start from 1', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_fails_if_signing_order_missing_required_keys(self):
        """Test creation fails if signing_order entries missing required keys."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id)},  # Missing 'order' key
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('must have both', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_fails_if_signer_id_invalid_uuid_format(self):
        """Test creation fails if signer_id is not a valid UUID format."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': 'invalid-uuid-format', 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('valid UUID', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_fails_if_order_not_positive_integer(self):
        """Test creation fails if order is not a positive integer."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 0}  # Should be >= 1
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('positive integer', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_succeeds_with_empty_signing_order(self):
        """Test creation succeeds with empty signing_order."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': []
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        
        # Check envelope was created with empty signing order
        envelope = Envelope.objects.get(id=response.data['data']['id'])
        self.assertEqual(envelope.signing_order, [])
    
    def test_unauthenticated_request_returns_401(self):
        """Test unauthenticated request returns 401."""
        # Remove authentication
        self.client.credentials()
        
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_envelope_creation_fails_if_document_not_found(self):
        """Test creation fails if document doesn't exist."""
        url = reverse('envelopes:envelope_create')
        
        non_existent_document_id = str(uuid.uuid4())
        
        payload = {
            'document_id': non_existent_document_id,
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('document_id', response.data['data'])
        self.assertIn('Document not found', response.data['data']['document_id'][0])
    
    def test_envelope_creation_with_non_sequential_signing_order(self):
        """Test envelope creation fails with non-sequential signing order."""
        url = reverse('envelopes:envelope_create')
        
        # Test with non-sequential order (1, 3, 5 - missing 2, 4)
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 3},  # Gap: missing order 2
                {'signer_id': str(self.creator.id), 'order': 5}   # Gap: missing order 4
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('Orders must start from 1 and have no gaps', response.data['data']['signing_order'][0])
    
    def test_envelope_creation_with_duplicate_orders(self):
        """Test envelope creation fails with duplicate signing orders."""
        url = reverse('envelopes:envelope_create')
        
        # Test with duplicate orders
        payload = {
            'document_id': str(self.document.id),
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 1}  # Duplicate order
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('signing_order', response.data['data'])
        self.assertIn('Duplicate order found', response.data['data']['signing_order'][0])
