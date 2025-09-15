"""
Unit tests for Document model.

This module contains tests for the Document model to ensure
proper creation, defaults, and relationships work correctly.
"""

import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from documents.models import Document

User = get_user_model()


class DocumentModelTest(TestCase):
    """Test cases for Document model functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            full_name='Test User'
        )
    
    def test_document_creation_with_valid_data(self):
        """Test that a Document can be created with valid data."""
        document = Document.objects.create(
            owner=self.user,
            file_url='/media/documents/test_document.pdf',
            file_name='test_document.pdf',
            file_size=1024000,  # 1MB in bytes
            status='draft'
        )
        
        # Verify the document was created successfully
        self.assertIsNotNone(document.id)
        self.assertEqual(document.owner, self.user)
        self.assertEqual(document.file_url, '/media/documents/test_document.pdf')
        self.assertEqual(document.file_name, 'test_document.pdf')
        self.assertEqual(document.file_size, 1024000)
        self.assertEqual(document.status, 'draft')
        self.assertIsNotNone(document.created_at)
        self.assertIsNotNone(document.updated_at)
    
    def test_document_status_defaults_to_draft(self):
        """Test that status defaults to 'draft' when not specified."""
        document = Document.objects.create(
            owner=self.user,
            file_url='/media/documents/test_document.pdf',
            file_name='test_document.pdf',
            file_size=1024000
        )
        
        # Verify status defaults to 'draft'
        self.assertEqual(document.status, 'draft')
    
    def test_document_owner_relationship(self):
        """Test that owner is correctly associated with the document."""
        document = Document.objects.create(
            owner=self.user,
            file_url='/media/documents/test_document.pdf',
            file_name='test_document.pdf',
            file_size=1024000
        )
        
        # Verify the relationship works both ways
        self.assertEqual(document.owner, self.user)
        self.assertIn(document, self.user.documents.all())
    
    def test_document_string_representation(self):
        """Test the string representation of Document model."""
        document = Document.objects.create(
            owner=self.user,
            file_url='/media/documents/test_document.pdf',
            file_name='test_document.pdf',
            file_size=1024000,
            status='sent'
        )
        
        expected_str = 'test_document.pdf (sent)'
        self.assertEqual(str(document), expected_str)
    
    def test_document_file_size_mb_property(self):
        """Test the file_size_mb property calculation."""
        document = Document.objects.create(
            owner=self.user,
            file_url='/media/documents/test_document.pdf',
            file_name='test_document.pdf',
            file_size=2097152,  # 2MB in bytes
        )
        
        # Verify file size conversion to MB
        self.assertEqual(document.file_size_mb, 2.0)
    
    def test_document_status_choices(self):
        """Test that only valid status choices are accepted."""
        valid_statuses = ['draft', 'sent', 'completed', 'rejected']
        
        for status in valid_statuses:
            document = Document.objects.create(
                owner=self.user,
                file_url=f'/media/documents/test_{status}.pdf',
                file_name=f'test_{status}.pdf',
                file_size=1024000,
                status=status
            )
            self.assertEqual(document.status, status)
    
    def test_document_ordering(self):
        """Test that documents are ordered by created_at descending."""
        # Create documents with different timestamps
        doc1 = Document.objects.create(
            owner=self.user,
            file_url='/media/documents/doc1.pdf',
            file_name='doc1.pdf',
            file_size=1024000
        )
        
        doc2 = Document.objects.create(
            owner=self.user,
            file_url='/media/documents/doc2.pdf',
            file_name='doc2.pdf',
            file_size=2048000
        )
        
        # Get all documents
        documents = Document.objects.all()
        
        # Verify ordering (newest first)
        self.assertEqual(documents[0], doc2)
        self.assertEqual(documents[1], doc1)
    
    def test_document_cascade_delete(self):
        """Test that documents are deleted when owner is deleted."""
        document = Document.objects.create(
            owner=self.user,
            file_url='/media/documents/test_document.pdf',
            file_name='test_document.pdf',
            file_size=1024000
        )
        
        document_id = document.id
        
        # Delete the user
        self.user.delete()
        
        # Verify document is also deleted
        self.assertFalse(Document.objects.filter(id=document_id).exists())
    
    def test_document_required_fields(self):
        """Test that required fields are properly validated."""
        # Test missing owner
        with self.assertRaises(ValidationError):
            document = Document(
                file_url='/media/documents/test_document.pdf',
                file_name='test_document.pdf',
                file_size=1024000
            )
            document.full_clean()
        
        # Test missing file_url
        with self.assertRaises(ValidationError):
            document = Document(
                owner=self.user,
                file_name='test_document.pdf',
                file_size=1024000
            )
            document.full_clean()
        
        # Test missing file_name
        with self.assertRaises(ValidationError):
            document = Document(
                owner=self.user,
                file_url='/media/documents/test_document.pdf',
                file_size=1024000
            )
            document.full_clean()
        
        # Test missing file_size
        with self.assertRaises(ValidationError):
            document = Document(
                owner=self.user,
                file_url='/media/documents/test_document.pdf',
                file_name='test_document.pdf'
            )
            document.full_clean()
