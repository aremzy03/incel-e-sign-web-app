"""
Unit tests for document deletion functionality.

This module contains tests for the document deletion endpoint
to ensure proper authentication, authorization, and data deletion.
"""

import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from documents.models import Document

User = get_user_model()


class DocumentDeletionTest(TestCase):
    """Test cases for document deletion functionality."""
    
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
    
    def test_owner_can_delete_their_document(self):
        """Test that owner can delete their document."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Verify document exists before deletion
        self.assertTrue(Document.objects.filter(id=self.doc1_user1.id).exists())
        
        # Delete document
        url = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response = self.client.delete(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'Document deleted successfully')
        
        # Verify document no longer exists in database
        self.assertFalse(Document.objects.filter(id=self.doc1_user1.id).exists())
        
        # Verify other documents still exist
        self.assertTrue(Document.objects.filter(id=self.doc2_user1.id).exists())
        self.assertTrue(Document.objects.filter(id=self.doc1_user2.id).exists())
    
    def test_document_no_longer_exists_after_deletion(self):
        """Test that after deletion, document no longer exists in DB."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Get initial document count
        initial_count = Document.objects.count()
        self.assertEqual(initial_count, 3)
        
        # Delete document
        url = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response = self.client.delete(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify document count decreased
        final_count = Document.objects.count()
        self.assertEqual(final_count, initial_count - 1)
        
        # Verify specific document is gone
        self.assertFalse(Document.objects.filter(id=self.doc1_user1.id).exists())
    
    def test_non_owner_attempting_delete_gets_404(self):
        """Test that non-owner attempting delete gets 404 (not 403)."""
        # Authenticate as user2
        self.client.force_authenticate(user=self.user2)
        
        # Try to delete user1's document
        url = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response = self.client.delete(url)
        
        # Verify response - should be 404 because document is not in user2's queryset
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Verify document still exists (not deleted)
        self.assertTrue(Document.objects.filter(id=self.doc1_user1.id).exists())
    
    def test_unauthenticated_delete_returns_401(self):
        """Test unauthenticated delete returns 401."""
        # Don't authenticate user
        
        # Try to delete document
        url = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response = self.client.delete(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Verify document still exists (not deleted)
        self.assertTrue(Document.objects.filter(id=self.doc1_user1.id).exists())
    
    def test_delete_nonexistent_document_returns_404(self):
        """Test that deleting nonexistent document returns 404."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Try to delete nonexistent document
        fake_uuid = uuid.uuid4()
        url = reverse('documents:document_delete', kwargs={'pk': fake_uuid})
        response = self.client.delete(url)
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_different_users_can_delete_their_own_documents(self):
        """Test that different users can delete their own documents independently."""
        # User1 deletes their document
        self.client.force_authenticate(user=self.user1)
        url1 = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response1 = self.client.delete(url1)
        
        self.assertEqual(response1.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.doc1_user1.id).exists())
        
        # User2 deletes their document
        self.client.force_authenticate(user=self.user2)
        url2 = reverse('documents:document_delete', kwargs={'pk': self.doc1_user2.id})
        response2 = self.client.delete(url2)
        
        self.assertEqual(response2.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.doc1_user2.id).exists())
        
        # Verify only user1's second document remains
        remaining_docs = Document.objects.all()
        self.assertEqual(remaining_docs.count(), 1)
        self.assertEqual(remaining_docs.first().id, self.doc2_user1.id)
    
    def test_delete_multiple_documents_by_same_user(self):
        """Test that a user can delete multiple documents."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Delete first document
        url1 = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response1 = self.client.delete(url1)
        self.assertEqual(response1.status_code, status.HTTP_204_NO_CONTENT)
        
        # Delete second document
        url2 = reverse('documents:document_delete', kwargs={'pk': self.doc2_user1.id})
        response2 = self.client.delete(url2)
        self.assertEqual(response2.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify both documents are deleted
        self.assertFalse(Document.objects.filter(owner=self.user1).exists())
        
        # Verify user2's document still exists
        self.assertTrue(Document.objects.filter(id=self.doc1_user2.id).exists())
    
    def test_delete_response_structure(self):
        """Test that delete response has correct structure."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Delete document
        url = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response = self.client.delete(url)
        
        # Verify response structure
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIn('success', response.data)
        self.assertIn('message', response.data)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'Document deleted successfully')
    
    def test_delete_document_with_different_statuses(self):
        """Test that documents with different statuses can be deleted."""
        # Authenticate as user1
        self.client.force_authenticate(user=self.user1)
        
        # Delete draft document
        url1 = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response1 = self.client.delete(url1)
        self.assertEqual(response1.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.doc1_user1.id).exists())
        
        # Delete sent document
        url2 = reverse('documents:document_delete', kwargs={'pk': self.doc2_user1.id})
        response2 = self.client.delete(url2)
        self.assertEqual(response2.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.doc2_user1.id).exists())
        
        # Verify user2's completed document still exists
        self.assertTrue(Document.objects.filter(id=self.doc1_user2.id).exists())
    
    def test_non_owner_cannot_delete_document(self):
        """Test that non-owner cannot delete document (returns 404)."""
        # Authenticate as user2 (not the owner of doc1_user1)
        self.client.force_authenticate(user=self.user2)
        
        # Try to delete user1's document
        url = reverse('documents:document_delete', kwargs={'pk': self.doc1_user1.id})
        response = self.client.delete(url)
        
        # Should return 404 (not found or access denied)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Verify document still exists in database
        self.assertTrue(Document.objects.filter(id=self.doc1_user1.id).exists())
        
        # Verify document owner is still user1
        document = Document.objects.get(id=self.doc1_user1.id)
        self.assertEqual(document.owner, self.user1)