"""
Unit tests for envelope retrieval functionality.

This module tests the envelope list and detail views, including
authentication, permissions, and data integrity.
"""

import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from envelopes.models import Envelope
from documents.models import Document
from signatures.models import Signature
from envelopes.models import EnvelopeDocument # Import EnvelopeDocument
from django.urls import reverse, resolve # Import resolve

User = get_user_model()


class EnvelopeRetrievalTestCase(APITestCase):
    """
    Test cases for envelope retrieval endpoints.
    
    Tests:
    - Creator can list and view their envelopes
    - Signer can list and view envelopes assigned to them
    - Other users cannot view unrelated envelopes (404)
    - Unauthenticated requests return 401
    - Envelope detail includes signatures with correct statuses
    """
    
    def setUp(self):
        """Set up test data."""
        super().setUp() # Ensure parent setUp is called
        # Create test users
        self.creator = User.objects.create_user(
            username="creator",
            email="creator@test.com",
            password="testpass123",
            full_name="Test Creator"
        )
        self.signer1 = User.objects.create_user(
            username="signer1",
            email="signer1@test.com",
            password="testpass123",
            full_name="Test Signer 1"
        )
        self.signer2 = User.objects.create_user(
            username="signer2",
            email="signer2@test.com",
            password="testpass123",
            full_name="Test Signer 2"
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@test.com",
            password="testpass123",
            full_name="Other User"
        )
        
        # Create test documents
        self.document1 = Document.objects.create(
            owner=self.creator,
            file_url="/test/path/document1.pdf",
            file_name="test_document1.pdf",
            file_size=1024,
            status="draft"
        )
        self.document2 = Document.objects.create(
            owner=self.creator,
            file_url="/test/path/document2.pdf",
            file_name="test_document2.pdf",
            file_size=2048,
            status="draft"
        )
        
        # Create test envelope
        self.envelope = Envelope.objects.create(
            creator=self.creator,
            name="Test Envelope for Signing",
            description="Please review carefully",
            status="pending",
            signing_order=[
                {"signer_id": str(self.signer1.id), "order": 1},
                {"signer_id": str(self.signer2.id), "order": 2}
            ]
        )
        EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document1, order=1)
        
        # Create signature records
        from django.utils import timezone
        
        self.signature1 = Signature.objects.create(
            envelope=self.envelope,
            signer=self.signer1,
            status="signed",
            signed_at=timezone.now()
        )
        self.signature2 = Signature.objects.create(
            envelope=self.envelope,
            signer=self.signer2,
            status="pending"
        )
        
        # Create another envelope for the other user
        self.other_document = Document.objects.create(
            owner=self.other_user,
            file_url="/test/path/other_document.pdf",
            file_name="other_document.pdf",
            file_size=2048,
            status="draft"
        )
        
        self.other_envelope = Envelope.objects.create(
            creator=self.other_user,
            name="Other User Envelope",
            status="draft",
            signing_order=[]
        )
        EnvelopeDocument.objects.create(envelope=self.other_envelope, document=self.other_document, order=1)
    
        # Debug prints
        print("\n--- DEBUG: setUp completed ---")
        print(f"Total Envelopes in DB: {Envelope.objects.count()}")
        print(f"Total EnvelopeDocuments in DB: {EnvelopeDocument.objects.count()}")
        print(f"Envelope ID: {self.envelope.id}")
        try:
            resolved_url = resolve(f'/api/envelopes/{self.envelope.id}/')
            print(f"Resolved URL for detail: {resolved_url.func.__name__}")
        except Exception as e:
            print(f"Failed to resolve detail URL: {e}")
        try:
            resolved_list_url = resolve('/api/envelopes/')
            print(f"Resolved URL for list: {resolved_list_url.func.__name__}")
        except Exception as e:
            print(f"Failed to resolve list URL: {e}")
        print("----------------------------")

    def get_auth_headers(self, user):
        """Get authentication headers for a user."""
        refresh = RefreshToken.for_user(user)
        return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}
    
    def test_creator_can_list_envelopes(self):
        """Test that creator can list their envelopes."""
        url = '/api/envelopes/' # Corrected URL path
        headers = self.get_auth_headers(self.creator)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']), 1) # Should only see self.envelope
        
        envelope_data = response.data['data'][0]
        self.assertEqual(envelope_data['id'], str(self.envelope.id))
        self.assertEqual(envelope_data['status'], 'pending') # Status should be pending
        self.assertEqual(envelope_data['name'], "Test Envelope for Signing")
        self.assertEqual(envelope_data['description'], "Please review carefully")
        self.assertEqual(len(envelope_data['signatures']), 2)
        self.assertEqual(len(envelope_data['documents']), 1)
        self.assertEqual(str(envelope_data['documents'][0]['document']), str(self.document1.id)) # Explicitly convert to string
    
    def test_signer_can_list_envelopes(self):
        """Test that signer can list envelopes they are assigned to."""
        url = '/api/envelopes/' # Corrected URL path
        headers = self.get_auth_headers(self.signer1)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']), 1) # Should only see self.envelope
        
        envelope_data = response.data['data'][0]
        self.assertEqual(envelope_data['id'], str(self.envelope.id))
        self.assertEqual(envelope_data['status'], 'pending') # Status should be pending
        self.assertEqual(envelope_data['name'], "Test Envelope for Signing")
        self.assertEqual(envelope_data['description'], "Please review carefully")
        self.assertEqual(len(envelope_data['signatures']), 2)
        self.assertEqual(len(envelope_data['documents']), 1)
        self.assertEqual(str(envelope_data['documents'][0]['document']), str(self.document1.id)) # Explicitly convert to string
    
    def test_user_can_list_multiple_envelopes(self):
        """Test that user can list multiple envelopes (as creator and signer)."""
        # Create another document for signer1
        another_document = Document.objects.create(
            owner=self.signer1,
            file_url="/test/path/another_document.pdf",
            file_name="another_document.pdf",
            file_size=512,
            status="draft"
        )
        
        # Create another envelope where signer1 is the creator
        another_envelope = Envelope.objects.create(
            creator=self.signer1,
            name="Signer1's Envelope",
            status="draft",
            signing_order=[
                {"signer_id": str(self.creator.id), "order": 1}
            ]
        )
        EnvelopeDocument.objects.create(envelope=another_envelope, document=another_document, order=1)
        
        url = '/api/envelopes/' # Corrected URL path
        headers = self.get_auth_headers(self.signer1)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']), 2) # Should see self.envelope (as signer) and another_envelope (as creator)
        
        # Verify both envelopes are present (order might vary, so check for IDs)
        envelope_ids = [env['id'] for env in response.data['data']]
        self.assertIn(str(self.envelope.id), envelope_ids)
        self.assertIn(str(another_envelope.id), envelope_ids)
    
    def test_other_user_cannot_list_unrelated_envelopes(self):
        """Test that other users cannot list unrelated envelopes."""
        url = '/api/envelopes/' # Corrected URL path
        headers = self.get_auth_headers(self.other_user)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        # Should only see their own envelope
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['id'], str(self.other_envelope.id))
        self.assertEqual(response.data['data'][0]['name'], "Other User Envelope")
        self.assertIsNone(response.data['data'][0]['description'])
    
    def test_unauthenticated_request_returns_401(self):
        """Test that unauthenticated requests return 401."""
        url = '/api/envelopes/' # Corrected URL path
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_creator_can_view_envelope_detail(self):
        """Test that creator can view their envelope details."""
        url = f'/api/envelopes/{self.envelope.id}/' # Corrected URL path
        headers = self.get_auth_headers(self.creator)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        envelope_data = response.data['data']
        self.assertEqual(envelope_data['id'], str(self.envelope.id))
        self.assertEqual(envelope_data['status'], 'pending') # Status should be pending
        self.assertEqual(envelope_data['name'], "Test Envelope for Signing")
        self.assertEqual(envelope_data['description'], "Please review carefully")
        self.assertEqual(len(envelope_data['signatures']), 2)
        self.assertEqual(len(envelope_data['documents']), 1)
        self.assertEqual(str(envelope_data['documents'][0]['document']), str(self.document1.id)) # Explicitly convert to string
        
        # Check signature details
        signatures = envelope_data['signatures']
        print(f"DEBUG: Signatures in response (creator detail): {signatures}") # Debug print
        signer1_signature = next(s for s in signatures if str(s['signer']) == str(self.signer1.id)) # Convert to string for comparison
        signer2_signature = next(s for s in signatures if str(s['signer']) == str(self.signer2.id)) # Convert to string for comparison
        
        self.assertEqual(signer1_signature['status'], 'signed')
        self.assertIsNotNone(signer1_signature['signed_at'])
        self.assertEqual(signer2_signature['status'], 'pending')
        self.assertIsNone(signer2_signature['signed_at'])
    
    def test_signer_can_view_envelope_detail(self):
        """Test that signer can view envelope details they are assigned to."""
        url = f'/api/envelopes/{self.envelope.id}/' # Corrected URL path
        headers = self.get_auth_headers(self.signer1)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        envelope_data = response.data['data']
        self.assertEqual(envelope_data['id'], str(self.envelope.id))
        self.assertEqual(envelope_data['status'], 'pending') # Status should be pending
        self.assertEqual(envelope_data['name'], "Test Envelope for Signing")
        self.assertEqual(envelope_data['description'], "Please review carefully")
        self.assertEqual(len(envelope_data['signatures']), 2)
        self.assertEqual(len(envelope_data['documents']), 1)
        self.assertEqual(str(envelope_data['documents'][0]['document']), str(self.document1.id)) # Explicitly convert to string
    
    def test_other_user_cannot_view_unrelated_envelope(self):
        """Test that other users cannot view unrelated envelopes (404)."""
        url = f'/api/envelopes/{self.envelope.id}/' # Corrected URL path
        headers = self.get_auth_headers(self.other_user)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('not found or access denied', response.data['message'])
    
    def test_unauthenticated_detail_request_returns_401(self):
        """Test that unauthenticated detail requests return 401."""
        url = f'/api/envelopes/{self.envelope.id}/' # Corrected URL path
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_nonexistent_envelope_returns_404(self):
        """Test that nonexistent envelope returns 404."""
        nonexistent_id = uuid.uuid4()
        url = f'/api/envelopes/{nonexistent_id}/' # Corrected URL path
        headers = self.get_auth_headers(self.creator)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['status'], 'error')
    
    def test_envelope_detail_includes_all_required_fields(self):
        """Test that envelope detail includes all required fields."""
        url = f'/api/envelopes/{self.envelope.id}/' # Corrected URL path
        headers = self.get_auth_headers(self.creator)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        envelope_data = response.data['data']
        required_fields = [
            'id', 'creator', 'creator_email', 'name', 'description', 'status', 'signing_order',
            'signer_count', 'documents', 'signatures', 'created_at', 'updated_at'
        ]
        
        for field in required_fields:
            self.assertIn(field, envelope_data)
        
        # Check that documents are present and have required fields
        documents_data = envelope_data['documents']
        self.assertEqual(len(documents_data), 1)
        doc_data = documents_data[0]
        doc_required_fields = [
            'id', 'document', 'order', 'document_file_name', 'document_file_url',
            'document_signed_file_url', 'signer_document_positions'
        ]
        for field in doc_required_fields:
            self.assertIn(field, doc_data)
        self.assertEqual(str(doc_data['document']), str(self.document1.id)) # Explicitly convert to string
        self.assertEqual(doc_data['document_file_name'], self.document1.file_name)
        self.assertEqual(len(doc_data['signer_document_positions']), 0) # No positions set in setUp

        # Check that signatures have required fields
        signatures = envelope_data['signatures']
        self.assertEqual(len(signatures), 2)
        
        for signature in signatures:
            signature_required_fields = ['id', 'signer', 'signer_email', 'signer_name', 'status', 'signing_order', 'signed_at', 'signature_image', 'created_at', 'updated_at']
            for field in signature_required_fields:
                self.assertIn(field, signature)
    
    def test_envelope_list_ordering(self):
        """Test that envelopes are ordered by created_at descending."""
        # Create another envelope
        newer_envelope = Envelope.objects.create(
            creator=self.creator,
            name="Newer Envelope",
            status="draft",
            signing_order=[]
        )
        # Link document to newer_envelope
        EnvelopeDocument.objects.create(envelope=newer_envelope, document=self.document1, order=1)
        
        url = '/api/envelopes/' # Corrected URL path
        headers = self.get_auth_headers(self.creator)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 2)
        
        # First envelope should be the newer one (more recent created_at)
        self.assertEqual(response.data['data'][0]['id'], str(newer_envelope.id))
        self.assertEqual(response.data['data'][1]['id'], str(self.envelope.id))
    
    def test_envelope_with_no_signatures(self):
        """Test envelope detail with no signatures."""
        url = f'/api/envelopes/{self.other_envelope.id}/' # Corrected URL path
        headers = self.get_auth_headers(self.other_user)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        envelope_data = response.data['data']
        self.assertEqual(envelope_data['id'], str(self.other_envelope.id))
        self.assertIsNone(envelope_data['description'])
        self.assertEqual(len(envelope_data['signatures']), 0)
        self.assertEqual(len(envelope_data['documents']), 1)
        self.assertEqual(str(envelope_data['documents'][0]['document']), str(self.other_document.id)) # Explicitly convert to string
    
    def test_envelope_with_mixed_signature_statuses(self):
        """Test envelope with mixed signature statuses."""
        # Update signature2 to declined
        self.signature2.status = "declined"
        self.signature2.save()
        
        url = f'/api/envelopes/{self.envelope.id}/' # Corrected URL path
        headers = self.get_auth_headers(self.creator)
        
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        envelope_data = response.data['data']
        signatures = envelope_data['signatures']
        print(f"DEBUG: Signatures in response (mixed status): {signatures}") # Debug print
        
        # Find signatures by signer
        signer1_signature = next(s for s in signatures if str(s['signer']) == str(self.signer1.id)) # Convert to string for comparison
        signer2_signature = next(s for s in signatures if str(s['signer']) == str(self.signer2.id)) # Convert to string for comparison
        
        self.assertEqual(signer1_signature['status'], 'signed')
        self.assertEqual(signer2_signature['status'], 'declined')
