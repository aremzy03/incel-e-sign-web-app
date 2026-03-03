"""
Test to verify that document override works after each signature.

This test specifically verifies the fix for the issue where documents
were only being overridden after all recipients signed, instead of
after each individual signature.
"""

import shutil
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from documents.models import Document
from envelopes.models import Envelope
from signatures.models import Signature
import base64

User = get_user_model()


class DocumentOverrideAfterEachSignatureTest(APITestCase):
    """Test that documents are overridden after each signature, not just at the end."""
    
    def setUp(self):
        """Set up test data."""
        # Create test users
        self.creator = User.objects.create_user(
            username='creator',
            email='creator@test.com',
            password='testpass123',
            full_name='Test Creator'
        )
        self.signer1 = User.objects.create_user(
            username='signer1',
            email='signer1@test.com',
            password='testpass123',
            full_name='Signer One'
        )
        self.signer2 = User.objects.create_user(
            username='signer2',
            email='signer2@test.com',
            password='testpass123',
            full_name='Signer Two'
        )
        
        # Get JWT tokens
        from rest_framework_simplejwt.tokens import RefreshToken
        
        self.creator_token = str(RefreshToken.for_user(self.creator).access_token)
        self.signer1_token = str(RefreshToken.for_user(self.signer1).access_token)
        self.signer2_token = str(RefreshToken.for_user(self.signer2).access_token)
        
        # Create test PDF content
        self.test_pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
72 720 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000204 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
297
%%EOF"""
        
        # Create test signature image (small PNG)
        self.test_signature_image = base64.b64encode(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f'
            b'\x00\x00\x01\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x1b\xea\xdd'
            b'\x01IEND\xaeB`\x82'
        ).decode('ascii')
    
    def _mock_embed_signature(self, pdf_path, output_path, **kwargs):
        """Mock embed_signature that copies input to output to simulate signing."""
        shutil.copy(pdf_path, output_path)

    def test_document_override_after_each_signature(self):
        """Test that document URLs are updated after each signature."""
        with patch('signatures.views.embed_signature', side_effect=self._mock_embed_signature):
            self._run_test_document_override_after_each_signature()

    def _run_test_document_override_after_each_signature(self):
        """Internal test runner for document override after each signature."""
        # Step 1: Creator uploads document
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        test_file = SimpleUploadedFile(
            "test_document.pdf",
            self.test_pdf_content,
            content_type="application/pdf"
        )
        
        upload_response = self.client.post(
            reverse('documents:document_upload'),
            {'file': test_file},
            format='multipart'
        )
        
        self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
        document_id = upload_response.data['data']['id']
        
        # Get initial document state
        document = Document.objects.get(id=document_id)
        original_file_url = document.file_url
        self.assertIsNone(document.signed_file_url)  # Should be None initially
        
        # Step 2: Creator creates envelope with sequential signing order
        envelope_data = {
            'document_ids': [document_id],
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1},
                {'signer_id': str(self.signer2.id), 'order': 2}
            ]
        }
        
        create_response = self.client.post(
            reverse('envelopes:envelope_create'),
            envelope_data,
            format='json'
        )
        
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        envelope_id = create_response.data['data']['id']
        
        # Step 3: Creator sends envelope
        send_response = self.client.post(
            reverse('envelopes:envelope_send', kwargs={'pk': envelope_id})
        )
        
        self.assertEqual(send_response.status_code, status.HTTP_200_OK)
        
        # Step 4: First signer signs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        sign_data = {
            'signature_image': f'data:image/png;base64,{self.test_signature_image}',
            'page': 1,
            'x': 100,
            'y': 100,
            'width': 120,
            'height': 40,
        }
        
        sign1_response = self.client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': envelope_id}),
            sign_data,
            format='json'
        )
        
        self.assertEqual(sign1_response.status_code, status.HTTP_200_OK)
        
        # CRITICAL TEST: Check that document is overridden after first signature
        document.refresh_from_db()
        
        # After first signature, both URLs should point to the signed version
        self.assertIsNotNone(document.signed_file_url, 
                            "signed_file_url should be set after first signature")
        self.assertNotEqual(document.file_url, original_file_url,
                           "file_url should be updated after first signature")
        self.assertEqual(document.file_url, document.signed_file_url,
                        "file_url should equal signed_file_url after first signature")
        
        # Store the first signed version URL
        first_signed_url = document.signed_file_url
        
        # Step 5: Second signer signs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
        
        sign2_response = self.client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': envelope_id}),
            sign_data,
            format='json'
        )
        
        self.assertEqual(sign2_response.status_code, status.HTTP_200_OK)
        
        # Check that document is overridden again after second signature
        document.refresh_from_db()
        
        # After second signature, URLs should be updated again
        self.assertIsNotNone(document.signed_file_url)
        self.assertEqual(document.file_url, document.signed_file_url)
        
        # The signed URL might be the same (same filename) but the content should be different
        # The key test is that both URLs point to the signed version
        
        # Step 6: Test document download returns the signed version
        download_response = self.client.get(
            reverse('documents:document_download', kwargs={'pk': document_id})
        )
        
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response['Content-Type'], 'application/pdf')
        
        # Step 7: Test document serializer returns current_file_url
        detail_response = self.client.get(
            reverse('documents:document_detail', kwargs={'pk': document_id})
        )
        
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        response_data = detail_response.data
        
        # Check that current_file_url field exists and points to signed version
        self.assertIn('current_file_url', response_data)
        self.assertEqual(response_data['current_file_url'], document.signed_file_url)
        
        print("✅ Document override test passed - documents are properly overridden after each signature!")
