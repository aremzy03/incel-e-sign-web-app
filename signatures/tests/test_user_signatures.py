"""
Tests for user signature functionality.

This module contains comprehensive tests for the UserSignature model,
serializers, views, and related functionality.
"""

import uuid
import base64
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from PIL import Image
import io

from signatures.models import UserSignature, Signature
from envelopes.models import Envelope
from documents.models import Document

User = get_user_model()


class UserSignatureModelTest(TestCase):
    """Test cases for the UserSignature model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            full_name='Test User'
        )
    
    def test_user_signature_creation(self):
        """Test creating a user signature."""
        # Create a simple test image
        image = Image.new('RGB', (100, 100), color='red')
        image_file = io.BytesIO()
        image.save(image_file, format='PNG')
        image_file.seek(0)
        
        signature = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature.png',
                image_file.getvalue(),
                content_type='image/png'
            )
        )
        
        self.assertEqual(signature.user, self.user)
        self.assertFalse(signature.is_default)
        self.assertIsNotNone(signature.created_at)
    
    def test_default_signature_constraint(self):
        """Test that only one signature can be default per user."""
        # Create a simple test image
        image = Image.new('RGB', (100, 100), color='red')
        image_file = io.BytesIO()
        image.save(image_file, format='PNG')
        image_file.seek(0)
        
        # Create first signature as default
        signature1 = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature1.png',
                image_file.getvalue(),
                content_type='image/png'
            ),
            is_default=True
        )
        
        # Create second signature as default
        image_file.seek(0)
        signature2 = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature2.png',
                image_file.getvalue(),
                content_type='image/png'
            ),
            is_default=True
        )
        
        # Refresh from database
        signature1.refresh_from_db()
        signature2.refresh_from_db()
        
        # Only the second signature should be default
        self.assertFalse(signature1.is_default)
        self.assertTrue(signature2.is_default)
    
    def test_user_signature_str_representation(self):
        """Test string representation of UserSignature."""
        # Create a simple test image
        image = Image.new('RGB', (100, 100), color='red')
        image_file = io.BytesIO()
        image.save(image_file, format='PNG')
        image_file.seek(0)
        
        signature = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature.png',
                image_file.getvalue(),
                content_type='image/png'
            ),
            is_default=True
        )
        
        expected_str = f"Signature for {self.user.email} (default)"
        self.assertEqual(str(signature), expected_str)


class UserSignatureSerializerTest(TestCase):
    """Test cases for the UserSignatureSerializer."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            full_name='Test User'
        )
    
    def test_serializer_validation_file_size(self):
        """Test file size validation."""
        from signatures.serializers import UserSignatureSerializer
        
        # Create a file that's definitely larger than 1MB
        large_data = b'x' * (1024 * 1024 + 1)  # 1MB + 1 byte
        large_file = SimpleUploadedFile(
            'large_signature.png',
            large_data,
            content_type='image/png'
        )
        
        serializer = UserSignatureSerializer(data={
            'image': large_file,
            'is_default': False
        })
        
        # This should fail validation due to file size
        self.assertFalse(serializer.is_valid())
        self.assertIn('image', serializer.errors)
    
    def test_serializer_validation_file_format(self):
        """Test file format validation."""
        from signatures.serializers import UserSignatureSerializer
        
        # Create a text file (invalid format)
        text_file = SimpleUploadedFile(
            'test.txt',
            b'This is not an image',
            content_type='text/plain'
        )
        
        serializer = UserSignatureSerializer(data={
            'image': text_file,
            'is_default': False
        })
        
        # This should fail validation due to invalid format
        self.assertFalse(serializer.is_valid())
        self.assertIn('image', serializer.errors)


class UserSignatureAPITest(APITestCase):
    """Test cases for UserSignature API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            full_name='Test User'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123',
            full_name='Other User'
        )
        
        # Create test image
        self.test_image = Image.new('RGB', (100, 100), color='red')
        image_file = io.BytesIO()
        self.test_image.save(image_file, format='PNG')
        image_file.seek(0)
        self.image_data = image_file.getvalue()
    
    def test_create_user_signature_success(self):
        """Test successful creation of user signature."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('signatures:user-signatures')
        data = {
            'image': SimpleUploadedFile(
                'test_signature.png',
                self.image_data,
                content_type='image/png'
            ),
            'is_default': True
        }
        
        response = self.client.post(url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        self.assertTrue(response.data['data']['is_default'])
        
        # Verify signature was created in database
        signature = UserSignature.objects.get(user=self.user)
        self.assertEqual(signature.user, self.user)
        self.assertTrue(signature.is_default)
    
    def test_create_user_signature_unauthorized(self):
        """Test creating signature without authentication."""
        url = reverse('signatures:user-signatures')
        data = {
            'image': SimpleUploadedFile(
                'test_signature.png',
                self.image_data,
                content_type='image/png'
            )
        }
        
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_list_user_signatures(self):
        """Test listing user signatures."""
        # Create test signatures
        signature1 = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature1.png',
                self.image_data,
                content_type='image/png'
            ),
            is_default=True
        )
        
        signature2 = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature2.png',
                self.image_data,
                content_type='image/png'
            ),
            is_default=False
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:user-signatures')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
    
    def test_list_user_signatures_other_user(self):
        """Test that users can only see their own signatures."""
        # Create signature for other user
        UserSignature.objects.create(
            user=self.other_user,
            image=SimpleUploadedFile(
                'other_signature.png',
                self.image_data,
                content_type='image/png'
            )
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:user-signatures')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
    
    def test_update_user_signature(self):
        """Test updating a user signature."""
        signature = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature.png',
                self.image_data,
                content_type='image/png'
            ),
            is_default=False
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:user-signature-detail', kwargs={'id': signature.id})
        data = {'is_default': True}
        
        response = self.client.patch(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify signature was updated
        signature.refresh_from_db()
        self.assertTrue(signature.is_default)
    
    def test_update_user_signature_unauthorized(self):
        """Test updating another user's signature."""
        signature = UserSignature.objects.create(
            user=self.other_user,
            image=SimpleUploadedFile(
                'other_signature.png',
                self.image_data,
                content_type='image/png'
            )
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:user-signature-detail', kwargs={'id': signature.id})
        data = {'is_default': True}
        
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_delete_user_signature(self):
        """Test deleting a user signature."""
        signature = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature.png',
                self.image_data,
                content_type='image/png'
            )
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:user-signature-detail', kwargs={'id': signature.id})
        
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify signature was deleted
        self.assertFalse(UserSignature.objects.filter(id=signature.id).exists())
    
    def test_delete_user_signature_unauthorized(self):
        """Test deleting another user's signature."""
        signature = UserSignature.objects.create(
            user=self.other_user,
            image=SimpleUploadedFile(
                'other_signature.png',
                self.image_data,
                content_type='image/png'
            )
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:user-signature-detail', kwargs={'id': signature.id})
        
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SignDocumentWithUserSignatureTest(APITestCase):
    """Test cases for signing documents with user signatures."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            full_name='Test User'
        )
        
        # Create test document
        self.document = Document.objects.create(
            owner=self.user,
            file_name='test_document.pdf',
            file_url='/test/path/document.pdf',
            file_size=1024
        )
        
        # Create test envelope
        self.envelope = Envelope.objects.create(
            document=self.document,
            creator=self.user,
            status='sent',
            signing_order=[{'signer_id': str(self.user.id), 'order': 1}]
        )
        
        # Create test signature record
        self.signature = Signature.objects.create(
            envelope=self.envelope,
            signer=self.user,
            status='pending'
        )
        
        # Create test image
        self.test_image = Image.new('RGB', (100, 100), color='red')
        image_file = io.BytesIO()
        self.test_image.save(image_file, format='PNG')
        image_file.seek(0)
        self.image_data = image_file.getvalue()
    
    def test_sign_document_with_signature_id(self):
        """Test signing document with signature_id."""
        # Create user signature
        user_signature = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature.png',
                self.image_data,
                content_type='image/png'
            )
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        data = {'signature_id': str(user_signature.id)}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify signature was updated
        self.signature.refresh_from_db()
        self.assertEqual(self.signature.status, 'signed')
        self.assertIsNotNone(self.signature.signature_image)
        self.assertIsNotNone(self.signature.signed_at)
    
    def test_sign_document_with_default_signature(self):
        """Test signing document with default signature."""
        # Create default user signature
        UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature.png',
                self.image_data,
                content_type='image/png'
            ),
            is_default=True
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        data = {}  # No signature provided, should use default
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify signature was updated
        self.signature.refresh_from_db()
        self.assertEqual(self.signature.status, 'signed')
        self.assertIsNotNone(self.signature.signature_image)
    
    def test_sign_document_no_signature_provided(self):
        """Test signing document without any signature provided."""
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        data = {}  # No signature provided and no default
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No signature provided', response.data['message'])
    
    def test_sign_document_invalid_signature_id(self):
        """Test signing document with invalid signature_id."""
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        data = {'signature_id': str(uuid.uuid4())}  # Non-existent ID
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('UserSignature not found', response.data['message'])
    
    def test_sign_document_signature_id_other_user(self):
        """Test signing document with another user's signature_id."""
        other_user = User.objects.create_user(
            username='otheruser2',
            email='other2@example.com',
            password='testpass123'
        )
        
        # Create signature for other user
        other_signature = UserSignature.objects.create(
            user=other_user,
            image=SimpleUploadedFile(
                'other_signature.png',
                self.image_data,
                content_type='image/png'
            )
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        data = {'signature_id': str(other_signature.id)}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('UserSignature not found', response.data['message'])
    
    def test_sign_document_both_signature_image_and_id(self):
        """Test signing document with both signature_image and signature_id."""
        user_signature = UserSignature.objects.create(
            user=self.user,
            image=SimpleUploadedFile(
                'test_signature.png',
                self.image_data,
                content_type='image/png'
            )
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope.id})
        data = {
            'signature_id': str(user_signature.id),
            'signature_image': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
        }
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Provide either signature_image or signature_id', response.data['data']['non_field_errors'][0])

