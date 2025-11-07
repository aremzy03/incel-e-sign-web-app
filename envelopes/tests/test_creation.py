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

from envelopes.models import Envelope, EnvelopeDocument # Import EnvelopeDocument
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
        
        # Create test documents
        self.document1 = Document.objects.create(
            owner=self.creator,
            file_url='/test/path/document1.pdf',
            file_name='test_document1.pdf',
            file_size=1024,
            status='draft'
        )
        self.document2 = Document.objects.create(
            owner=self.creator,
            file_url='/test/path/document2.pdf',
            file_name='test_document2.pdf',
            file_size=2048,
            status='draft'
        )
        
        # Create a document owned by another user
        self.other_document = Document.objects.create(
            owner=self.other_user,
            file_url='/test/path/other_document.pdf',
            file_name='other_document.pdf',
            file_size=1024,
            status='draft'
        )
        
        # Get JWT token for authentication
        refresh = RefreshToken.for_user(self.creator)
        self.token = str(refresh.access_token)
        
        # Set up authentication header
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
    
    def test_successful_envelope_creation_with_multiple_documents_and_custom_name(self):
        """Test successful envelope creation with multiple documents and a custom name."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_ids': [str(self.document1.id), str(self.document2.id)],
            'name': "My Custom Envelope Name",
            'description': "Quick summary for recipients",
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
        self.assertEqual(envelope.creator, self.creator)
        self.assertEqual(envelope.name, "My Custom Envelope Name")
        self.assertEqual(envelope.description, "Quick summary for recipients")
        self.assertEqual(envelope.status, 'draft')
        self.assertEqual(len(envelope.signing_order), 2)
        self.assertEqual(envelope.signing_order[0]['signer_id'], str(self.signer1.id))
        self.assertEqual(envelope.signing_order[1]['signer_id'], str(self.signer2.id))
        
        # Check EnvelopeDocument instances
        envelope_documents = envelope.envelopedocument_set.all().order_by('order')
        self.assertEqual(envelope_documents.count(), 2)
        self.assertEqual(envelope_documents[0].document, self.document1)
        self.assertEqual(envelope_documents[0].order, 1)
        self.assertEqual(envelope_documents[1].document, self.document2)
        self.assertEqual(envelope_documents[1].order, 2)
        
        # Check that name field is included in response
        self.assertIn('name', response.data['data'])
        self.assertEqual(response.data['data']['name'], "My Custom Envelope Name")
        self.assertIn('description', response.data['data'])
        self.assertEqual(response.data['data']['description'], "Quick summary for recipients")

    def test_successful_envelope_creation_with_default_name(self):
        """Test successful envelope creation with multiple documents and default name."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_ids': [str(self.document1.id)],
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        
        envelope = Envelope.objects.get(id=response.data['data']['id'])
        self.assertIsNotNone(envelope.name)
        self.assertIn("Untitled Envelope", envelope.name)
        self.assertIn(envelope.name, response.data['data']['name'])
        self.assertIn('description', response.data['data'])
        self.assertIsNone(response.data['data']['description'])

    def test_envelope_creation_fails_if_no_documents(self):
        """Test creation fails if no document IDs are provided."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_ids': [], # Empty list
            'name': "Invalid Envelope",
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('document_ids', response.data['data'])
        self.assertEqual(response.data['data']['document_ids'][0], 'Ensure this field has at least 1 elements.')
    
    def test_envelope_creation_fails_if_document_doesnt_belong_to_creator(self):
        """Test creation fails if document doesn't belong to creator."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_ids': [str(self.document1.id), str(self.other_document.id)],
            'name': "Invalid Envelope",
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('document_ids', response.data['data'])
        self.assertIn(f'Some documents not found or do not belong to you: {[str(self.other_document.id)]}', response.data['data']['document_ids'][0])

    def test_envelope_creation_fails_if_document_not_found(self):
        """Test creation fails if a document ID does not exist."""
        url = reverse('envelopes:envelope_create')
        non_existent_document_id = str(uuid.uuid4())
        
        payload = {
            'document_ids': [str(self.document1.id), non_existent_document_id],
            'name': "Invalid Envelope",
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('document_ids', response.data['data'])
        self.assertIn(f'Some documents not found or do not belong to you: {[non_existent_document_id]}', response.data['data']['document_ids'][0])

    def test_envelope_creation_with_documents_and_positions(self):
        """Test successful envelope creation with multiple documents and specific signer positions per document."""
        url = reverse('envelopes:envelope_create')
        
        payload = {
            'document_ids': [str(self.document1.id), str(self.document2.id)],
            'name': "Envelope with Positions",
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 2}
            ],
            'documents_with_positions': [
                {
                    'document_id': str(self.document1.id),
                    'signer_document_positions': [
                        {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}}
                    ]
                },
                {
                    'document_id': str(self.document2.id),
                    'signer_document_positions': [
                        {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 50, "y": 60, "width": 70, "height": 80}},
                        {"signer_id": str(self.signer2.id), "position": {"page": 2, "x": 100, "y": 110, "width": 120, "height": 130}}
                    ]
                }
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        
        envelope = Envelope.objects.get(id=response.data['data']['id'])
        self.assertEqual(envelope.name, "Envelope with Positions")
        
        env_doc1 = EnvelopeDocument.objects.get(envelope=envelope, document=self.document1)
        self.assertEqual(env_doc1.signer_document_positions, [
            {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}}
        ])
        
        env_doc2 = EnvelopeDocument.objects.get(envelope=envelope, document=self.document2)
        self.assertEqual(env_doc2.signer_document_positions, [
            {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 50, "y": 60, "width": 70, "height": 80}},
            {"signer_id": str(self.signer2.id), "position": {"page": 2, "x": 100, "y": 110, "width": 120, "height": 130}}
        ])

    def test_envelope_creation_fails_if_document_in_positions_not_in_document_ids(self):
        """Test creation fails if a document in documents_with_positions is not in document_ids."""
        url = reverse('envelopes:envelope_create')
        non_existent_document_id = str(uuid.uuid4())

        payload = {
            'document_ids': [str(self.document1.id)],
            'name': "Invalid Envelope",
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ],
            'documents_with_positions': [
                {
                    'document_id': str(self.document1.id),
                    'signer_document_positions': [
                        {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}}
                    ]
                },
                {
                    'document_id': non_existent_document_id, # This document is not in document_ids
                    'signer_document_positions': [
                        {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 50, "y": 60, "width": 70, "height": 80}}
                    ]
                }
            ]
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('documents_with_positions', response.data['data'])
        self.assertIn(f'Document ID {non_existent_document_id} in documents_with_positions is not part of the envelope\'s document_ids.', response.data['data']['documents_with_positions'][0])

    def test_envelope_creation_fails_if_signer_in_positions_not_in_signing_order(self):
        """Test creation fails if a signer in signer_document_positions is not in signing_order."""
        url = reverse('envelopes:envelope_create')
        non_existent_signer_id = str(uuid.uuid4())

        payload = {
            'document_ids': [str(self.document1.id)],
            'name': "Invalid Envelope",
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ],
            'documents_with_positions': [
                {
                    'document_id': str(self.document1.id),
                    'signer_document_positions': [
                        {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}},
                        {"signer_id": non_existent_signer_id, "position": {"page": 1, "x": 50, "y": 60, "width": 70, "height": 80}} # This signer is not in signing_order
                    ]
                }
            ]
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('documents_with_positions', response.data['data'])
        self.assertIn(f'Signer ID {non_existent_signer_id} in signer_document_positions for document {str(self.document1.id)} is not part of the envelope\'s signing_order.', response.data['data']['documents_with_positions'][0])
    
    def test_envelope_creation_fails_if_invalid_user_id_in_signing_order(self):
        """Test creation fails if invalid user_id is in signing_order."""
        url = reverse('envelopes:envelope_create')
        
        # Use non-existent user ID
        invalid_user_id = str(uuid.uuid4())
        
        payload = {
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
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
            'document_ids': [str(self.document1.id)],
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
