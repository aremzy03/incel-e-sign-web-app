"""
Unit tests for document upload functionality.

This module contains tests for the document upload endpoint to ensure
proper file validation, storage, and Document model creation.
"""

import os
import tempfile
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from documents.models import Document

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class DocumentUploadTest(TestCase):
    """Test cases for document upload functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            full_name='Test User'
        )
        
        # Create a small PDF file for testing (1KB)
        self.small_pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF'
        
        # Create a large file for testing (>20MB)
        self.large_file_content = b'X' * (21 * 1024 * 1024)  # 21MB
        
        # Create a file at exactly 20MB boundary
        self.boundary_file_content = b'X' * (20 * 1024 * 1024)  # Exactly 20MB
        
        # Create a non-PDF file for testing
        self.txt_content = b'This is a text file, not a PDF.'
    
    def test_successful_pdf_upload(self):
        """Test successful upload with valid PDF file (<20MB)."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Create PDF file
        pdf_file = SimpleUploadedFile(
            "test_document.pdf",
            self.small_pdf_content,
            content_type="application/pdf"
        )
        
        # Upload file
        url = reverse('documents:document_upload')
        response = self.client.post(url, {'file': pdf_file}, format='multipart')
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'Document uploaded successfully')
        
        # Verify document data
        document_data = response.data['data']
        self.assertEqual(document_data['file_name'], 'test_document.pdf')
        self.assertEqual(document_data['file_size'], len(self.small_pdf_content))
        self.assertEqual(document_data['status'], 'draft')
        
        # Verify document was created in database
        document = Document.objects.get(id=document_data['id'])
        self.assertEqual(document.owner, self.user)
        self.assertEqual(document.file_name, 'test_document.pdf')
        self.assertEqual(document.file_size, len(self.small_pdf_content))
        self.assertEqual(document.status, 'draft')
    
    def test_rejection_for_non_pdf_file(self):
        """Test rejection for non-PDF file."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Create text file
        txt_file = SimpleUploadedFile(
            "test_document.txt",
            self.txt_content,
            content_type="text/plain"
        )
        
        # Upload file
        url = reverse('documents:document_upload')
        response = self.client.post(url, {'file': txt_file}, format='multipart')
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], 'Invalid file data')
        self.assertIn('file', response.data['errors'])
        self.assertIn('Only PDF files are allowed', str(response.data['errors']['file']))
        
        # Verify no document was created
        self.assertEqual(Document.objects.count(), 0)
    
    def test_rejection_for_large_file(self):
        """Test rejection for file >20MB."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Create large file
        large_file = SimpleUploadedFile(
            "large_document.pdf",
            self.large_file_content,
            content_type="application/pdf"
        )
        
        # Upload file
        url = reverse('documents:document_upload')
        response = self.client.post(url, {'file': large_file}, format='multipart')
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], 'Invalid file data')
        self.assertIn('file', response.data['errors'])
        self.assertIn('File size must not exceed 20MB', str(response.data['errors']['file']))
        
        # Verify no document was created
        self.assertEqual(Document.objects.count(), 0)
    
    def test_upload_requires_authentication(self):
        """Test that upload requires authentication."""
        # Don't authenticate user
        
        # Create PDF file
        pdf_file = SimpleUploadedFile(
            "test_document.pdf",
            self.small_pdf_content,
            content_type="application/pdf"
        )
        
        # Upload file
        url = reverse('documents:document_upload')
        response = self.client.post(url, {'file': pdf_file}, format='multipart')
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Verify no document was created
        self.assertEqual(Document.objects.count(), 0)
    
    def test_upload_without_file(self):
        """Test upload without file data."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Upload without file
        url = reverse('documents:document_upload')
        response = self.client.post(url, {}, format='multipart')
        
        # Verify response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], 'Invalid file data')
        self.assertIn('file', response.data['errors'])
        
        # Verify no document was created
        self.assertEqual(Document.objects.count(), 0)
    
    def test_upload_with_empty_file(self):
        """Test upload with empty file."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Create empty PDF file
        empty_file = SimpleUploadedFile(
            "empty_document.pdf",
            b'',
            content_type="application/pdf"
        )
        
        # Upload file
        url = reverse('documents:document_upload')
        response = self.client.post(url, {'file': empty_file}, format='multipart')
        
        # Verify response - empty files should be rejected as they're not valid PDFs
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['message'], 'Invalid file data')
        
        # Verify no document was created
        self.assertEqual(Document.objects.count(), 0)
    
    def test_multiple_uploads_same_user(self):
        """Test that a user can upload multiple documents."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Upload first document
        pdf_file1 = SimpleUploadedFile(
            "document1.pdf",
            self.small_pdf_content,
            content_type="application/pdf"
        )
        
        url = reverse('documents:document_upload')
        response1 = self.client.post(url, {'file': pdf_file1}, format='multipart')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        
        # Upload second document
        pdf_file2 = SimpleUploadedFile(
            "document2.pdf",
            self.small_pdf_content,
            content_type="application/pdf"
        )
        
        response2 = self.client.post(url, {'file': pdf_file2}, format='multipart')
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        
        # Verify both documents were created
        self.assertEqual(Document.objects.count(), 2)
        self.assertEqual(Document.objects.filter(owner=self.user).count(), 2)
        
        # Verify different document IDs
        doc1_id = response1.data['data']['id']
        doc2_id = response2.data['data']['id']
        self.assertNotEqual(doc1_id, doc2_id)
    
    def test_upload_different_users(self):
        """Test that different users can upload documents independently."""
        # Create second user
        user2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123',
            full_name='Test User 2'
        )
        
        # Upload document as first user
        self.client.force_authenticate(user=self.user)
        pdf_file = SimpleUploadedFile(
            "user1_document.pdf",
            self.small_pdf_content,
            content_type="application/pdf"
        )
        
        url = reverse('documents:document_upload')
        response1 = self.client.post(url, {'file': pdf_file}, format='multipart')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        
        # Upload document as second user
        self.client.force_authenticate(user=user2)
        pdf_file2 = SimpleUploadedFile(
            "user2_document.pdf",
            self.small_pdf_content,
            content_type="application/pdf"
        )
        
        response2 = self.client.post(url, {'file': pdf_file2}, format='multipart')
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        
        # Verify both documents were created with correct owners
        self.assertEqual(Document.objects.count(), 2)
        self.assertEqual(Document.objects.filter(owner=self.user).count(), 1)
        self.assertEqual(Document.objects.filter(owner=user2).count(), 1)
        
        # Verify document ownership
        doc1 = Document.objects.get(id=response1.data['data']['id'])
        doc2 = Document.objects.get(id=response2.data['data']['id'])
        self.assertEqual(doc1.owner, self.user)
        self.assertEqual(doc2.owner, user2)
    
    def test_upload_pdf_at_20mb_boundary(self):
        """Test upload of PDF at exactly 20MB boundary (should be accepted)."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Create PDF file at exactly 20MB
        boundary_pdf = SimpleUploadedFile(
            "boundary_document.pdf",
            self.boundary_file_content,
            content_type="application/pdf"
        )
        
        # Upload file
        url = reverse('documents:document_upload')
        response = self.client.post(url, {'file': boundary_pdf}, format='multipart')
        
        # Verify response - should be accepted
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'], 'Document uploaded successfully')
        
        # Verify document data
        document_data = response.data['data']
        self.assertEqual(document_data['file_name'], 'boundary_document.pdf')
        self.assertEqual(document_data['file_size'], len(self.boundary_file_content))
        self.assertEqual(document_data['status'], 'draft')
        
        # Verify document was created in database
        document = Document.objects.get(id=document_data['id'])
        self.assertEqual(document.owner, self.user)
        self.assertEqual(document.file_size, len(self.boundary_file_content))
    
    def test_rejection_for_pdf_over_20mb(self):
        """Test rejection for PDF file over 20MB (should be rejected)."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)
        
        # Create PDF file over 20MB
        large_pdf = SimpleUploadedFile(
            "large_document.pdf",
            self.large_file_content,
            content_type="application/pdf"
        )
        
        # Upload file
        url = reverse('documents:document_upload')
        response = self.client.post(url, {'file': large_pdf}, format='multipart')
        
        # Verify response - should be rejected
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], 'Invalid file data')
        self.assertIn('file', response.data['data'])
        self.assertIn('File size must not exceed 20MB', str(response.data['data']['file']))
        
        # Verify no document was created
        self.assertEqual(Document.objects.count(), 0)
