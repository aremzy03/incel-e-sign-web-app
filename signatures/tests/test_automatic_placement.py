"""
Tests for automatic signature placement using envelope position coordinates.

This module tests the automatic signature placement functionality that uses
position coordinates defined in the envelope's signing_order field.
"""

import uuid
import base64
import os
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from signatures.models import Signature, UserSignature
from envelopes.models import Envelope
from documents.models import Document

User = get_user_model()


class AutomaticSignaturePlacementTestCase(APITestCase):
    """
    Test cases for automatic signature placement using envelope position coordinates.
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
        
        # Create JWT tokens for authentication
        self.creator_token = str(RefreshToken.for_user(self.creator).access_token)
        self.signer1_token = str(RefreshToken.for_user(self.signer1).access_token)
        self.signer2_token = str(RefreshToken.for_user(self.signer2).access_token)
        
        # Create a test document
        self.document = Document.objects.create(
            owner=self.creator,
            file_url="/media/documents/test_document.pdf",
            file_name="test_document.pdf",
            file_size=1024
        )
        
        # Sample signature image (small PNG as base64)
        self.signature_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
    def test_sign_with_envelope_position_coordinates(self):
        """Test signing with position coordinates from envelope's signing_order."""
        # Create envelope with position coordinates in signing_order
        signing_order = [
            {
                "signer_id": str(self.signer1.id), 
                "order": 1,
                "position": {
                    "page": 1,
                    "x": 150,
                    "y": 450,
                    "width": 200,
                    "height": 50
                }
            },
            {
                "signer_id": str(self.signer2.id), 
                "order": 2,
                "position": {
                    "page": 2,
                    "x": 120,
                    "y": 600,
                    "width": 180,
                    "height": 40
                }
            }
        ]
        
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            name=self.document.file_name,
            status="pending",
            signing_order=signing_order
        )
        
        # Create signature records
        signature1 = Signature.objects.create(
            envelope=envelope,
            signer=self.signer1,
            status="pending"
        )
        
        signature2 = Signature.objects.create(
            envelope=envelope,
            signer=self.signer2,
            status="pending"
        )
        
        # Mock the PDF embedding function to capture the position arguments
        with patch('signatures.views.embed_signature') as mock_embed:
            with patch('signatures.views.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                
                # Authenticate as signer1
                self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
                
                # Sign the document without providing position coordinates
                url = reverse('signatures:sign_document', kwargs={'envelope_id': envelope.id})
                data = {
                    'signature_image': self.signature_image
                }
                
                response = self.client.post(url, data, format='json')
                
                # Verify the response is successful
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['status'], 'success')
                
                # Verify embed_signature was called with position from envelope
                mock_embed.assert_called_once()
                call_args = mock_embed.call_args
                
                # Check that position coordinates from envelope were used
                self.assertEqual(call_args.kwargs['page'], 1)
                self.assertEqual(call_args.kwargs['x'], 150)
                self.assertEqual(call_args.kwargs['y'], 450)
                self.assertEqual(call_args.kwargs['width'], 200)
                self.assertEqual(call_args.kwargs['height'], 50)
                
                # Verify signature was updated
                signature1.refresh_from_db()
                self.assertEqual(signature1.status, 'signed')
                self.assertIsNotNone(signature1.signed_at)
    
    def test_sign_without_envelope_position_uses_defaults(self):
        """Test signing without position coordinates in envelope uses defaults."""
        # Create envelope without position coordinates in signing_order
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 2}
        ]
        
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            name=self.document.file_name,
            status="pending",
            signing_order=signing_order
        )
        
        # Create signature record
        signature1 = Signature.objects.create(
            envelope=envelope,
            signer=self.signer1,
            status="pending"
        )
        
        # Mock the PDF embedding function to capture the position arguments
        with patch('signatures.views.embed_signature') as mock_embed:
            with patch('signatures.views.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                
                # Authenticate as signer1
                self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
                
                # Sign the document without providing position coordinates
                url = reverse('signatures:sign_document', kwargs={'envelope_id': envelope.id})
                data = {
                    'signature_image': self.signature_image
                }
                
                response = self.client.post(url, data, format='json')
                
                # Verify the response is successful
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                
                # Verify embed_signature was called with default coordinates
                mock_embed.assert_called_once()
                call_args = mock_embed.call_args
                
                # Check that default coordinates were used
                self.assertEqual(call_args.kwargs['page'], 1)
                self.assertEqual(call_args.kwargs['x'], 100)
                self.assertEqual(call_args.kwargs['y'], 100)
                self.assertEqual(call_args.kwargs['width'], 120)
                self.assertEqual(call_args.kwargs['height'], 40)
    
    
    def test_sign_with_request_position_fallback(self):
        """Test signing with request position coordinates when envelope has none."""
        # Create envelope without position coordinates
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1}
        ]
        
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            name=self.document.file_name,
            status="pending",
            signing_order=signing_order
        )
        
        # Create signature record
        signature1 = Signature.objects.create(
            envelope=envelope,
            signer=self.signer1,
            status="pending"
        )
        
        # Mock the PDF embedding function
        with patch('signatures.views.embed_signature') as mock_embed:
            with patch('signatures.views.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                
                # Authenticate as signer1
                self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
                
                # Sign the document with position coordinates in request
                url = reverse('signatures:sign_document', kwargs={'envelope_id': envelope.id})
                data = {
                    'signature_image': self.signature_image,
                    'page': 2,
                    'x': 300,
                    'y': 500,
                    'width': 160,
                    'height': 60
                }
                
                response = self.client.post(url, data, format='json')
                
                # Verify the response is successful
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                
                # Verify embed_signature was called with request coordinates
                mock_embed.assert_called_once()
                call_args = mock_embed.call_args
                
                # Check that request coordinates were used
                self.assertEqual(call_args.kwargs['page'], 2)
                self.assertEqual(call_args.kwargs['x'], 300)
                self.assertEqual(call_args.kwargs['y'], 500)
                self.assertEqual(call_args.kwargs['width'], 160)
                self.assertEqual(call_args.kwargs['height'], 60)
    
    def test_sequential_signing_with_different_positions(self):
        """Test sequential signing where each signer has different position coordinates."""
        # Create envelope with different positions for each signer
        signing_order = [
            {
                "signer_id": str(self.signer1.id), 
                "order": 1,
                "position": {
                    "page": 1,
                    "x": 100,
                    "y": 700,
                    "width": 150,
                    "height": 40
                }
            },
            {
                "signer_id": str(self.signer2.id), 
                "order": 2,
                "position": {
                    "page": 1,
                    "x": 300,
                    "y": 700,
                    "width": 150,
                    "height": 40
                }
            }
        ]
        
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            name=self.document.file_name,
            status="pending",
            signing_order=signing_order
        )
        
        # Create signature records
        signature1 = Signature.objects.create(
            envelope=envelope,
            signer=self.signer1,
            status="pending"
        )
        
        signature2 = Signature.objects.create(
            envelope=envelope,
            signer=self.signer2,
            status="pending"
        )
        
        # Mock the PDF embedding function
        with patch('signatures.views.embed_signature') as mock_embed:
            with patch('signatures.views.os.path.exists') as mock_exists:
                mock_exists.return_value = True
                
                # First signer signs
                self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
                
                url = reverse('signatures:sign_document', kwargs={'envelope_id': envelope.id})
                data = {'signature_image': self.signature_image}
                
                response = self.client.post(url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                
                # Verify first signer's position was used
                first_call_args = mock_embed.call_args
                self.assertEqual(first_call_args.kwargs['x'], 100)
                self.assertEqual(first_call_args.kwargs['y'], 700)
                
                # Reset mock for second call
                mock_embed.reset_mock()
                
                # Second signer signs
                self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
                
                response = self.client.post(url, data, format='json')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                
                # Verify second signer's position was used
                second_call_args = mock_embed.call_args
                self.assertEqual(second_call_args.kwargs['x'], 300)
                self.assertEqual(second_call_args.kwargs['y'], 700)
                
                # Verify both signatures are signed
                signature1.refresh_from_db()
                signature2.refresh_from_db()
                self.assertEqual(signature1.status, 'signed')
                self.assertEqual(signature2.status, 'signed')
                
                # Verify envelope is completed
                envelope.refresh_from_db()
                self.assertEqual(envelope.status, 'completed')
    
    def test_sign_with_user_signature_and_envelope_position(self):
        """Test signing with UserSignature ID and envelope position coordinates."""
        # Create envelope with position coordinates
        signing_order = [
            {
                "signer_id": str(self.signer1.id), 
                "order": 1,
                "position": {
                    "page": 2,
                    "x": 250,
                    "y": 350,
                    "width": 180,
                    "height": 45
                }
            }
        ]
        
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            name=self.document.file_name,
            status="pending",
            signing_order=signing_order
        )
        
        # Create signature record
        signature1 = Signature.objects.create(
            envelope=envelope,
            signer=self.signer1,
            status="pending"
        )
        
        # Create a user signature for signer1
        user_signature = UserSignature.objects.create(
            user=self.signer1,
            is_default=True
        )
        
        # Mock the PDF embedding function and UserSignature image handling
        with patch('signatures.views.embed_signature') as mock_embed:
            with patch('signatures.views.os.path.exists') as mock_exists:
                with patch('signatures.views.UserSignature.objects.get') as mock_get_signature:
                    # Mock the UserSignature object and its image methods
                    mock_signature = MagicMock()
                    mock_signature.image.open = MagicMock()
                    mock_signature.image.read = MagicMock(return_value=base64.b64decode(self.signature_image))
                    mock_signature.image.close = MagicMock()
                    mock_signature.image.name = 'signature.png'
                    mock_get_signature.return_value = mock_signature
                    
                    mock_exists.return_value = True
                    
                    # Authenticate as signer1
                    self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
                    
                    # Sign using UserSignature ID (no position coordinates in request)
                    url = reverse('signatures:sign_document', kwargs={'envelope_id': envelope.id})
                    data = {
                        'signature_id': str(user_signature.id)
                    }
                    
                    response = self.client.post(url, data, format='json')
                    
                    # Verify the response is successful
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    
                    # Verify embed_signature was called with envelope position
                    mock_embed.assert_called_once()
                    call_args = mock_embed.call_args
                    
                    self.assertEqual(call_args.kwargs['page'], 2)
                    self.assertEqual(call_args.kwargs['x'], 250)
                    self.assertEqual(call_args.kwargs['y'], 350)
                    self.assertEqual(call_args.kwargs['width'], 180)
                    self.assertEqual(call_args.kwargs['height'], 45)
    
    def test_sign_without_signature_uses_default_and_envelope_position(self):
        """Test signing without any signature data uses default signature and envelope position."""
        # Create envelope with position coordinates
        signing_order = [
            {
                "signer_id": str(self.signer1.id), 
                "order": 1,
                "position": {
                    "page": 1,
                    "x": 400,
                    "y": 200,
                    "width": 160,
                    "height": 50
                }
            }
        ]
        
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            name=self.document.file_name,
            status="pending",
            signing_order=signing_order
        )
        
        # Create signature record
        signature1 = Signature.objects.create(
            envelope=envelope,
            signer=self.signer1,
            status="pending"
        )
        
        # Create a default user signature for signer1
        user_signature = UserSignature.objects.create(
            user=self.signer1,
            is_default=True
        )
        
        # Mock the PDF embedding function and UserSignature image handling
        with patch('signatures.views.embed_signature') as mock_embed:
            with patch('signatures.views.os.path.exists') as mock_exists:
                with patch('signatures.views.UserSignature.objects.get') as mock_get_signature:
                    # Mock the UserSignature object and its image methods
                    mock_signature = MagicMock()
                    mock_signature.image.open = MagicMock()
                    mock_signature.image.read = MagicMock(return_value=base64.b64decode(self.signature_image))
                    mock_signature.image.close = MagicMock()
                    mock_signature.image.name = 'signature.png'
                    mock_get_signature.return_value = mock_signature
                    
                    mock_exists.return_value = True
                    
                    # Authenticate as signer1
                    self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
                    
                    # Sign without any signature data (should use default)
                    url = reverse('signatures:sign_document', kwargs={'envelope_id': envelope.id})
                    data = {}  # Empty data - should use default signature
                    
                    response = self.client.post(url, data, format='json')
                    
                    # Verify the response is successful
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    
                    # Verify embed_signature was called with envelope position
                    mock_embed.assert_called_once()
                    call_args = mock_embed.call_args
                    
                    self.assertEqual(call_args.kwargs['page'], 1)
                    self.assertEqual(call_args.kwargs['x'], 400)
                    self.assertEqual(call_args.kwargs['y'], 200)
                    self.assertEqual(call_args.kwargs['width'], 160)
                    self.assertEqual(call_args.kwargs['height'], 50)
