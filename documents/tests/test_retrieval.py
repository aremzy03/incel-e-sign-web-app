"""
Unit tests for document retrieval functionality.

This module contains tests for the document list and detail endpoints
to ensure proper authentication, authorization, and data filtering.
"""

import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from documents.models import Document

User = get_user_model()


class DocumentRetrievalTest(TestCase):
    """Test cases for document retrieval functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        
        # Create test users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123',
            full_name='User One'
        )
        
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123',
            full_name='User Two'
        )
        
        # Create test documents
        self.doc1_user1 = Document.objects.create(
            owner=self.user1,
            file_url='/media/documents/doc1.pdf',
            file_name='document1.pdf',
            file_size=1024000,
            status='draft'
        )
        
        self.doc2_user1 = Document.objects.create(
            owner=self.user1,
            file_url='/media/documents/doc2.pdf',
            file_name='document2.pdf',
            file_size=2048000,
            status='sent'
        )
        
        self.doc1_user2 = Document.objects.create(
            owner=self.user2,
            file_url='/media/documents/doc3.pdf',
            file_name='document3.pdf',
            file_size=1536000,
            status='completed'
        )
    
    def test_list_returns_only_user_documents(self):
        """Test that list returns only documents owned by the authenticated user."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Get document list
        url = reverse('documents:document_list')
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)  # user1 has 2 documents
        
        # Verify only user1's documents are returned
        document_ids = [doc['id'] for doc in response.data]
        self.assertIn(str(self.doc1_user1.id), document_ids)
        self.assertIn(str(self.doc2_user1.id), document_ids)
        self.assertNotIn(str(self.doc1_user2.id), document_ids)
        
        # Verify document data structure
        for doc in response.data:
            self.assertIn('id', doc)
            self.assertIn('file_name', doc)
            self.assertIn('file_url', doc)
            self.assertIn('file_size', doc)
            self.assertIn('status', doc)
            self.assertIn('created_at', doc)
            self.assertIn('updated_at', doc)
    
    def test_list_ordering_by_created_at_desc(self):
        """Test that documents are ordered by created_at in descending order."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Get document list
        url = reverse('documents:document_list')
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        
        # Verify ordering (newest first)
        # doc2_user1 was created after doc1_user1
        self.assertEqual(response.data[0]['id'], str(self.doc2_user1.id))
        self.assertEqual(response.data[1]['id'], str(self.doc1_user1.id))
    
    def test_list_requires_authentication(self):
        """Test that list endpoint requires authentication."""
        # Don't authenticate user
        
        # Get document list
        url = reverse('documents:document_list')
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_detail_returns_correct_document_for_owner(self):
        """Test that detail returns correct document for the owner."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Get document detail
        url = reverse('documents:document_detail', kwargs={'pk': self.doc1_user1.id})
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify document data
        self.assertEqual(response.data['id'], str(self.doc1_user1.id))
        self.assertEqual(response.data['file_name'], 'document1.pdf')
        self.assertEqual(response.data['file_url'], '/media/documents/doc1.pdf')
        self.assertEqual(response.data['file_size'], 1024000)
        self.assertEqual(response.data['status'], 'draft')
    
    def test_detail_returns_404_for_non_owner(self):
        """Test that detail returns 404 for non-owner."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Try to access user2's document
        url = reverse('documents:document_detail', kwargs={'pk': self.doc1_user2.id})
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_detail_returns_404_for_nonexistent_document(self):
        """Test that detail returns 404 for nonexistent document."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Try to access nonexistent document
        fake_uuid = uuid.uuid4()
        url = reverse('documents:document_detail', kwargs={'pk': fake_uuid})
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_detail_requires_authentication(self):
        """Test that detail endpoint requires authentication."""
        # Don't authenticate user
        
        # Get document detail
        url = reverse('documents:document_detail', kwargs={'pk': self.doc1_user1.id})
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_different_users_see_different_documents(self):
        """Test that different users see different document lists."""
        # Test user1's documents
        self.client.force_authenticate(user=self.user1)
        url = reverse('documents:document_list')
        response1 = self.client.get(url)
        
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response1.data), 2)
        
        # Test user2's documents
        self.client.force_authenticate(user=self.user2)
        response2 = self.client.get(url)
        
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response2.data), 1)
        
        # Verify different documents
        user1_doc_ids = [doc['id'] for doc in response1.data]
        user2_doc_ids = [doc['id'] for doc in response2.data]
        
        self.assertEqual(user2_doc_ids[0], str(self.doc1_user2.id))
        self.assertNotEqual(user1_doc_ids, user2_doc_ids)
    
    def test_empty_document_list(self):
        """Test that user with no documents gets empty list."""
        # Create user with no documents
        user3 = User.objects.create_user(
            username='user3',
            email='user3@example.com',
            password='testpass123',
            full_name='User Three'
        )
        
        # Authenticate as user3
        self.client.force_authenticate(user=user3)
        
        # Get document list
        url = reverse('documents:document_list')
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
        self.assertEqual(response.data, [])
    
    def test_document_serializer_fields(self):
        """Test that document serializer returns all required fields."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Get document detail
        url = reverse('documents:document_detail', kwargs={'pk': self.doc1_user1.id})
        response = self.client.get(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify all required fields are present
        required_fields = [
            'id', 'file_name', 'file_url', 'file_size', 
            'status', 'created_at', 'updated_at'
        ]
        
        for field in required_fields:
            self.assertIn(field, response.data, f"Field '{field}' is missing from response")
        
        # Verify field types
        self.assertIsInstance(response.data['id'], str)
        self.assertIsInstance(response.data['file_name'], str)
        self.assertIsInstance(response.data['file_url'], str)
        self.assertIsInstance(response.data['file_size'], int)
        self.assertIsInstance(response.data['status'], str)
        self.assertIsInstance(response.data['created_at'], str)
        self.assertIsInstance(response.data['updated_at'], str)
