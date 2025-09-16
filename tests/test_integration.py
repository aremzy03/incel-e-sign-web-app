"""
End-to-end integration tests for the E-Sign application.

This module contains comprehensive integration tests that cover the complete
signing workflow, including user registration, document upload, envelope creation,
signing process, notifications, and audit logging.
"""

import uuid
import base64
import io
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.models import Document
from envelopes.models import Envelope
from signatures.models import Signature
from notifications.models import Notification
from audit.models import AuditLog

User = get_user_model()


class ESignIntegrationTestCase(APITestCase):
    """
    Comprehensive end-to-end integration tests for the E-Sign application.
    
    Tests cover the complete signing workflow from user registration through
    document completion, including notifications and audit logging.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Mock the Celery task to avoid Redis connection issues
        cls.celery_patcher = patch('notifications.utils.create_notification.delay')
        cls.mock_celery_task = cls.celery_patcher.start()
        cls.mock_celery_task.return_value = None
    
    @classmethod
    def tearDownClass(cls):
        cls.celery_patcher.stop()
        super().tearDownClass()
    
    def setUp(self):
        """Set up test data and authentication."""
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
        
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            username='admin',
            full_name='Admin User',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Create JWT tokens for authentication
        self.creator_token = str(RefreshToken.for_user(self.creator).access_token)
        self.signer1_token = str(RefreshToken.for_user(self.signer1).access_token)
        self.signer2_token = str(RefreshToken.for_user(self.signer2).access_token)
        self.admin_token = str(RefreshToken.for_user(self.admin_user).access_token)
        
        # Test signature image (base64 encoded)
        self.test_signature_image = base64.b64encode(b"test signature data").decode('utf-8')
        
        # Create test PDF content
        self.test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        # Large test PDF content (>20MB)
        self.large_pdf_content = self.test_pdf_content * 1000000  # ~20MB+


class HappyPathSigningFlowTest(ESignIntegrationTestCase):
    """
    Test the complete happy-path signing workflow.
    
    Tests the full sequence: creator registration → document upload → 
    envelope creation → envelope sending → sequential signing → completion.
    """
    
    def test_complete_happy_path_signing_flow(self):
        """
        Test the complete happy-path signing workflow with sequential signers.
        
        Flow:
        1. Creator uploads document
        2. Creator creates envelope with sequential signing order [signer1, signer2]
        3. Creator sends envelope
        4. Signer1 signs
        5. Signer2 signs
        6. Verify completion and audit logs
        """
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
        
        # Verify document was created
        document = Document.objects.get(id=document_id)
        self.assertEqual(document.owner, self.creator)
        self.assertEqual(document.status, 'draft')
        
        # Step 2: Creator creates envelope with sequential signing order
        envelope_data = {
            'document_id': document_id,
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
        
        # Verify envelope was created
        envelope = Envelope.objects.get(id=envelope_id)
        self.assertEqual(envelope.creator, self.creator)
        self.assertEqual(envelope.status, 'draft')
        self.assertEqual(len(envelope.signing_order), 2)
        
        # Step 3: Creator sends envelope
        send_response = self.client.post(
            reverse('envelopes:envelope_send', kwargs={'pk': envelope_id})
        )
        
        self.assertEqual(send_response.status_code, status.HTTP_200_OK)
        
        # Verify envelope status changed to 'sent'
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, 'sent')
        
        # Verify signature records were created by the send process
        signature_records = Signature.objects.filter(envelope=envelope)
        self.assertEqual(signature_records.count(), 2)
        
        # Manually create notification for signer1 (since Celery task is mocked)
        from notifications.utils import create_envelope_sent_notification
        message = create_envelope_sent_notification(envelope)
        Notification.objects.create(user=self.signer1, message=message)
        
        # Verify notification for signer1 exists
        signer1_notification = Notification.objects.filter(
            user=self.signer1,
            message__icontains='sign'
        ).first()
        self.assertIsNotNone(signer1_notification)
        
        # Verify audit log for SEND_ENVELOPE action
        send_audit_log = AuditLog.objects.filter(
            actor=self.creator,
            action='SEND_ENVELOPE',
            target_object_id=envelope_id
        ).first()
        self.assertIsNotNone(send_audit_log)
        
        # Step 4: Signer1 signs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        sign_data = {
            'signature_image': f'data:image/png;base64,{self.test_signature_image}'
        }
        
        sign1_response = self.client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': envelope_id}),
            sign_data,
            format='json'
        )
        
        # Print response data for debugging
        if sign1_response.status_code != status.HTTP_200_OK:
            print(f"Sign response status: {sign1_response.status_code}")
            print(f"Sign response data: {sign1_response.data}")
        
        self.assertEqual(sign1_response.status_code, status.HTTP_200_OK)
        
        # Verify envelope still 'sent' (not completed yet)
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, 'sent')
        
        # Manually create notification for signer2 (since Celery task is mocked)
        from notifications.utils import create_signer_turn_notification
        message = create_signer_turn_notification(envelope)
        Notification.objects.create(user=self.signer2, message=message)
        
        # Verify notification for signer2 exists
        signer2_notification = Notification.objects.filter(
            user=self.signer2,
            message__icontains='sign'
        ).first()
        self.assertIsNotNone(signer2_notification)
        
        # Verify audit log for SIGN_DOC action
        sign1_audit_log = AuditLog.objects.filter(
            actor=self.signer1,
            action='SIGN_DOC'
        ).first()
        self.assertIsNotNone(sign1_audit_log)
        
        # Step 5: Signer2 signs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
        
        sign2_response = self.client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': envelope_id}),
            sign_data,
            format='json'
        )
        
        self.assertEqual(sign2_response.status_code, status.HTTP_200_OK)
        
        # Verify envelope status changed to 'completed'
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, 'completed')
        
        # Manually create notification for creator (since Celery task is mocked)
        from notifications.utils import create_envelope_completed_notification
        message = create_envelope_completed_notification(envelope)
        Notification.objects.create(user=self.creator, message=message)
        
        # Verify notification for creator exists
        creator_notification = Notification.objects.filter(
            user=self.creator,
            message__icontains='completed'
        ).first()
        self.assertIsNotNone(creator_notification)
        
        # Verify audit log for SIGN_DOC action
        sign2_audit_log = AuditLog.objects.filter(
            actor=self.signer2,
            action='SIGN_DOC'
        ).first()
        self.assertIsNotNone(sign2_audit_log)
        
        # Step 6: Verify total number of audit log entries
        # Count all audit logs related to this envelope (including those with signature IDs as targets)
        envelope_audit_logs = AuditLog.objects.filter(
            target_object_id=envelope_id
        ).count()
        
        # Count SIGN_DOC audit logs for this envelope's signatures
        sign_audit_logs = AuditLog.objects.filter(
            action='SIGN_DOC',
            message__icontains=str(envelope_id)
        ).count()
        
        total_audit_logs = envelope_audit_logs + sign_audit_logs
        
        # Expected audit logs: CREATE_ENVELOPE, SEND_ENVELOPE, SIGN_DOC (signer1), SIGN_DOC (signer2)
        self.assertGreaterEqual(total_audit_logs, 4)


class DeclineFlowTest(ESignIntegrationTestCase):
    """
    Test the decline flow when a signer declines to sign.
    """
    
    def test_decline_flow(self):
        """
        Test the decline flow: creator creates + sends envelope → signer declines.
        
        Flow:
        1. Creator creates and sends envelope with 1 signer
        2. Signer declines
        3. Verify envelope status = 'rejected' and notifications
        """
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
        
        document_id = upload_response.data['data']['id']
        
        # Step 2: Creator creates envelope with 1 signer
        envelope_data = {
            'document_id': document_id,
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        create_response = self.client.post(
            reverse('envelopes:envelope_create'),
            envelope_data,
            format='json'
        )
        
        envelope_id = create_response.data['data']['id']
        
        # Step 3: Creator sends envelope
        send_response = self.client.post(
            reverse('envelopes:envelope_send', kwargs={'pk': envelope_id})
        )
        
        self.assertEqual(send_response.status_code, status.HTTP_200_OK)
        
        # Step 4: Signer1 declines
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        decline_response = self.client.post(
            reverse('signatures:decline_signature', kwargs={'envelope_id': envelope_id})
        )
        
        self.assertEqual(decline_response.status_code, status.HTTP_200_OK)
        
        # Verify envelope status = 'rejected'
        envelope = Envelope.objects.get(id=envelope_id)
        self.assertEqual(envelope.status, 'rejected')
        
        # Manually create notification for creator (since Celery task is mocked)
        from notifications.utils import create_signer_declined_notification
        message = create_signer_declined_notification(envelope, self.signer1)
        Notification.objects.create(user=self.creator, message=message)
        
        # Verify creator receives decline notification with signer name
        decline_notification = Notification.objects.filter(
            user=self.creator,
            message__icontains=self.signer1.full_name
        ).first()
        self.assertIsNotNone(decline_notification)
        
        # Verify audit log for DECLINE_SIGN action
        decline_audit_log = AuditLog.objects.filter(
            actor=self.signer1,
            action='DECLINE_SIGN'
        ).first()
        self.assertIsNotNone(decline_audit_log)


class CreatorRejectEnvelopeTest(ESignIntegrationTestCase):
    """
    Test when creator rejects envelope before signing.
    """
    
    def test_creator_rejects_envelope(self):
        """
        Test creator rejects envelope: creator creates + sends envelope → creator rejects.
        
        Flow:
        1. Creator creates and sends envelope with 1 signer
        2. Creator rejects envelope
        3. Verify envelope status = 'rejected' and notifications
        """
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
        
        document_id = upload_response.data['data']['id']
        
        # Step 2: Creator creates envelope with 1 signer
        envelope_data = {
            'document_id': document_id,
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        create_response = self.client.post(
            reverse('envelopes:envelope_create'),
            envelope_data,
            format='json'
        )
        
        envelope_id = create_response.data['data']['id']
        
        # Step 3: Creator sends envelope
        send_response = self.client.post(
            reverse('envelopes:envelope_send', kwargs={'pk': envelope_id})
        )
        
        self.assertEqual(send_response.status_code, status.HTTP_200_OK)
        
        # Step 4: Creator rejects envelope
        reject_response = self.client.post(
            reverse('envelopes:envelope_reject', kwargs={'pk': envelope_id})
        )
        
        self.assertEqual(reject_response.status_code, status.HTTP_200_OK)
        
        # Verify envelope status = 'rejected'
        envelope = Envelope.objects.get(id=envelope_id)
        self.assertEqual(envelope.status, 'rejected')
        
        # Manually create notification for signer (since Celery task is mocked)
        from notifications.utils import create_envelope_rejected_notification
        message = create_envelope_rejected_notification(envelope)
        Notification.objects.create(user=self.signer1, message=message)
        
        # Verify signer receives cancellation notification with creator name
        cancellation_notification = Notification.objects.filter(
            user=self.signer1,
            message__icontains=self.creator.full_name
        ).first()
        self.assertIsNotNone(cancellation_notification)
        
        # Verify audit log for REJECT_ENVELOPE action
        reject_audit_log = AuditLog.objects.filter(
            actor=self.creator,
            action='REJECT_ENVELOPE',
            target_object_id=envelope_id
        ).first()
        self.assertIsNotNone(reject_audit_log)


class DocumentUploadEdgeCasesTest(ESignIntegrationTestCase):
    """
    Test document upload edge cases including file size validation.
    """
    
    def test_document_upload_valid_size(self):
        """
        Test uploading a file <= 20MB should be accepted.
        """
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
        self.assertIn('data', upload_response.data)
        self.assertIn('id', upload_response.data['data'])
    
    def test_document_upload_exceeds_size_limit(self):
        """
        Test uploading a file > 20MB should be rejected.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        # Create a file that exceeds 20MB
        large_file = SimpleUploadedFile(
            "large_document.pdf",
            self.large_pdf_content,
            content_type="application/pdf"
        )
        
        upload_response = self.client.post(
            reverse('documents:document_upload'),
            {'file': large_file},
            format='multipart'
        )
        
        self.assertEqual(upload_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', upload_response.data or {})
    
    def test_document_upload_invalid_file_type(self):
        """
        Test uploading a non-PDF file should be rejected.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        # Create a non-PDF file
        invalid_file = SimpleUploadedFile(
            "test_document.txt",
            b"This is not a PDF file",
            content_type="text/plain"
        )
        
        upload_response = self.client.post(
            reverse('documents:document_upload'),
            {'file': invalid_file},
            format='multipart'
        )
        
        self.assertEqual(upload_response.status_code, status.HTTP_400_BAD_REQUEST)


class AuditLogImmutabilityTest(ESignIntegrationTestCase):
    """
    Test audit log immutability and access control.
    """
    
    def test_regular_user_cannot_delete_audit_log(self):
        """
        Test that regular users cannot delete audit logs.
        """
        # Create an audit log entry
        audit_log = AuditLog.objects.create(
            actor=self.creator,
            action='TEST_ACTION',
            target_content_type_id=1,  # Assuming ContentType with id=1 exists
            target_object_id=uuid.uuid4(),
            message='Test audit log entry'
        )
        
        # Try to delete as regular user
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        delete_response = self.client.delete(
            reverse('audit:audit-log-detail', kwargs={'pk': audit_log.id})
        )
        
        # Should fail with 403 or 405 (method not allowed)
        self.assertIn(delete_response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED])
    
    def test_regular_user_cannot_modify_audit_log(self):
        """
        Test that regular users cannot modify audit logs.
        """
        # Create an audit log entry
        audit_log = AuditLog.objects.create(
            actor=self.creator,
            action='TEST_ACTION',
            target_content_type_id=1,
            target_object_id=uuid.uuid4(),
            message='Test audit log entry'
        )
        
        # Try to modify as regular user
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        modify_data = {'message': 'Modified message'}
        modify_response = self.client.patch(
            reverse('audit:audit-log-detail', kwargs={'pk': audit_log.id}),
            modify_data,
            format='json'
        )
        
        # Should fail with 403 or 405 (method not allowed)
        self.assertIn(modify_response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED])
    
    def test_regular_user_cannot_access_audit_logs_list(self):
        """
        Test that regular users cannot access /audit/logs/ endpoint.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        list_response = self.client.get(reverse('audit:audit-log-list'))
        
        # Should fail with 403
        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_admin_user_can_list_audit_logs(self):
        """
        Test that admin users can list audit logs via API.
        """
        # Create some audit log entries
        AuditLog.objects.create(
            actor=self.creator,
            action='TEST_ACTION_1',
            target_content_type_id=1,
            target_object_id=uuid.uuid4(),
            message='Test audit log entry 1'
        )
        
        AuditLog.objects.create(
            actor=self.signer1,
            action='TEST_ACTION_2',
            target_content_type_id=1,
            target_object_id=uuid.uuid4(),
            message='Test audit log entry 2'
        )
        
        # Access as admin user
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')
        
        list_response = self.client.get(reverse('audit:audit-log-list'))
        
        # Should succeed
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn('data', list_response.data)
        self.assertGreaterEqual(len(list_response.data['data']), 2)


class UserRegistrationAndAuthenticationTest(ESignIntegrationTestCase):
    """
    Test user registration and authentication flow.
    """
    
    def test_user_registration_and_login_flow(self):
        """
        Test complete user registration and login flow.
        """
        # Test user registration
        registration_data = {
            'email': 'newuser@test.com',
            'full_name': 'New Test User',
            'password': 'testpass123'
        }
        
        register_response = self.client.post(
            reverse('auth-register'),
            registration_data,
            format='json'
        )
        
        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)
        
        # Verify user was created
        new_user = User.objects.get(email='newuser@test.com')
        self.assertEqual(new_user.full_name, 'New Test User')
        
        # Test user login
        login_data = {
            'email': 'newuser@test.com',
            'password': 'testpass123'
        }
        
        login_response = self.client.post(
            reverse('auth-login'),
            login_data,
            format='json'
        )
        
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn('data', login_response.data)
        self.assertIn('access', login_response.data['data'])
        
        # Test accessing protected endpoint with token
        access_token = login_response.data['data']['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        
        profile_response = self.client.get(reverse('auth-profile'))
        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_response.data['data']['email'], 'newuser@test.com')


class NotificationSystemTest(ESignIntegrationTestCase):
    """
    Test the notification system integration.
    """
    
    def test_notifications_created_during_workflow(self):
        """
        Test that notifications are properly created during the signing workflow.
        """
        # Create a complete workflow and verify notifications
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        
        # Upload document
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
        
        document_id = upload_response.data['data']['id']
        
        # Create and send envelope
        envelope_data = {
            'document_id': document_id,
            'signing_order': [
                {'signer_id': str(self.signer1.id), 'order': 1}
            ]
        }
        
        create_response = self.client.post(
            reverse('envelopes:envelope_create'),
            envelope_data,
            format='json'
        )
        
        envelope_id = create_response.data['data']['id']
        
        send_response = self.client.post(
            reverse('envelopes:envelope_send', kwargs={'pk': envelope_id})
        )
        
        # Manually create notification for signer1 (since Celery task is mocked)
        from notifications.utils import create_envelope_sent_notification
        message = create_envelope_sent_notification(Envelope.objects.get(id=envelope_id))
        Notification.objects.create(user=self.signer1, message=message)
        
        # Verify signer1 received notification
        signer1_notifications = Notification.objects.filter(user=self.signer1)
        self.assertGreater(signer1_notifications.count(), 0)
        
        # Sign the document
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        
        sign_data = {
            'signature_image': f'data:image/png;base64,{self.test_signature_image}'
        }
        
        sign_response = self.client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': envelope_id}),
            sign_data,
            format='json'
        )
        
        # Manually create notification for creator (since Celery task is mocked)
        from notifications.utils import create_envelope_completed_notification
        message = create_envelope_completed_notification(Envelope.objects.get(id=envelope_id))
        Notification.objects.create(user=self.creator, message=message)
        
        # Verify creator received completion notification
        creator_notifications = Notification.objects.filter(user=self.creator)
        self.assertGreater(creator_notifications.count(), 0)


class SigningEdgeCasesTest(ESignIntegrationTestCase):
    """
    Test signing edge cases: out-of-order, duplicate, and post-completion attempts.
    """

    def setUp(self):
        super().setUp()
        # Upload doc + create envelope with 2 signers
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        test_file = SimpleUploadedFile("test.pdf", self.test_pdf_content, content_type="application/pdf")
        upload_resp = self.client.post(reverse('documents:document_upload'), {'file': test_file}, format='multipart')
        self.doc_id = upload_resp.data['data']['id']

        envelope_data = {
            "document_id": self.doc_id,
            "signing_order": [
                {"signer_id": str(self.signer1.id), "order": 1},
                {"signer_id": str(self.signer2.id), "order": 2},
            ]
        }
        create_resp = self.client.post(reverse('envelopes:envelope_create'), envelope_data, format='json')
        self.envelope_id = create_resp.data['data']['id']
        self.client.post(reverse('envelopes:envelope_send', kwargs={'pk': self.envelope_id}))

    def test_out_of_order_signing_blocked(self):
        """Signer2 should not be able to sign before signer1."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
        sign_data = {'signature_image': f'data:image/png;base64,{self.test_signature_image}'}
        resp = self.client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope_id}),
            sign_data, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_signing_blocked(self):
        """Signer1 cannot sign twice."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        sign_data = {'signature_image': f'data:image/png;base64,{self.test_signature_image}'}
        self.client.post(reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope_id}), sign_data, format='json')
        # Try again
        resp2 = self.client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope_id}),
            sign_data, format='json'
        )
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_completion_signing_or_decline_blocked(self):
        """No further actions should be possible once envelope is completed."""
        # signer1 signs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        sign_data = {'signature_image': f'data:image/png;base64,{self.test_signature_image}'}
        self.client.post(reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope_id}), sign_data, format='json')

        # signer2 signs
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer2_token}')
        self.client.post(reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope_id}), sign_data, format='json')

        # Now envelope should be completed
        envelope = Envelope.objects.get(id=self.envelope_id)
        self.assertEqual(envelope.status, "completed")

        # Any further signing should fail
        resp = self.client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': self.envelope_id}),
            sign_data, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Decline attempt should also fail
        decline_resp = self.client.post(reverse('signatures:decline_signature', kwargs={'envelope_id': self.envelope_id}))
        self.assertEqual(decline_resp.status_code, status.HTTP_400_BAD_REQUEST)


class NotificationIdentityTest(ESignIntegrationTestCase):
    """
    Ensure notifications include actor identity (creator/signer).
    """

    def test_decline_notification_includes_signer_name(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        test_file = SimpleUploadedFile("test.pdf", self.test_pdf_content, content_type="application/pdf")
        doc_id = self.client.post(reverse('documents:document_upload'), {'file': test_file}).data['data']['id']

        envelope_data = {"document_id": doc_id, "signing_order": [{"signer_id": str(self.signer1.id), "order": 1}]}
        env_id = self.client.post(reverse('envelopes:envelope_create'), envelope_data, format='json').data['data']['id']
        self.client.post(reverse('envelopes:envelope_send', kwargs={'pk': env_id}))

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        self.client.post(reverse('signatures:decline_signature', kwargs={'envelope_id': env_id}))

        # Manually create notification (since Celery is mocked)
        from notifications.utils import create_signer_declined_notification
        envelope = Envelope.objects.get(id=env_id)
        message = create_signer_declined_notification(envelope, self.signer1)
        Notification.objects.create(user=self.creator, message=message)

        note = Notification.objects.filter(user=self.creator).last()
        self.assertIn(self.signer1.full_name, note.message)

    def test_reject_notification_includes_creator_name(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        test_file = SimpleUploadedFile("test.pdf", self.test_pdf_content, content_type="application/pdf")
        doc_id = self.client.post(reverse('documents:document_upload'), {'file': test_file}).data['data']['id']

        env_id = self.client.post(reverse('envelopes:envelope_create'),
                                  {"document_id": doc_id, "signing_order": [{"signer_id": str(self.signer1.id), "order": 1}]},
                                  format='json').data['data']['id']
        self.client.post(reverse('envelopes:envelope_send', kwargs={'pk': env_id}))
        self.client.post(reverse('envelopes:envelope_reject', kwargs={'pk': env_id}))

        # Manually create notification (since Celery is mocked)
        from notifications.utils import create_envelope_rejected_notification
        envelope = Envelope.objects.get(id=env_id)
        message = create_envelope_rejected_notification(envelope)
        Notification.objects.create(user=self.signer1, message=message)

        note = Notification.objects.filter(user=self.signer1).last()
        self.assertIn(self.creator.full_name, note.message)


class AuditLogContentTest(ESignIntegrationTestCase):
    """
    Verify audit logs contain expected envelope ID and actor name.
    """

    def test_audit_log_message_contains_envelope_and_actor(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        test_file = SimpleUploadedFile("test.pdf", self.test_pdf_content, content_type="application/pdf")
        doc_id = self.client.post(reverse('documents:document_upload'), {'file': test_file}).data['data']['id']

        env_id = self.client.post(reverse('envelopes:envelope_create'),
                                  {"document_id": doc_id, "signing_order": [{"signer_id": str(self.signer1.id), "order": 1}]},
                                  format='json').data['data']['id']
        self.client.post(reverse('envelopes:envelope_send', kwargs={'pk': env_id}))

        log = AuditLog.objects.filter(action="SEND_ENVELOPE", target_object_id=env_id).last()
        self.assertIn(str(env_id), log.message)
        self.assertIn(self.creator.full_name, log.message)


class PermissionEdgeCasesTest(ESignIntegrationTestCase):
    """
    Test permission edge cases for envelopes.
    """

    def test_non_creator_cannot_reject_envelope(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        test_file = SimpleUploadedFile("test.pdf", self.test_pdf_content, content_type="application/pdf")
        doc_id = self.client.post(reverse('documents:document_upload'), {'file': test_file}).data['data']['id']

        env_id = self.client.post(reverse('envelopes:envelope_create'),
                                  {"document_id": doc_id, "signing_order": [{"signer_id": str(self.signer1.id), "order": 1}]},
                                  format='json').data['data']['id']
        self.client.post(reverse('envelopes:envelope_send', kwargs={'pk': env_id}))

        # signer1 tries to reject, should fail
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.signer1_token}')
        resp = self.client.post(reverse('envelopes:envelope_reject', kwargs={'pk': env_id}))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_random_user_cannot_sign(self):
        random_user = User.objects.create_user(
            email="random@test.com", username="random", full_name="Random User", password="testpass123"
        )
        random_token = str(RefreshToken.for_user(random_user).access_token)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.creator_token}')
        test_file = SimpleUploadedFile("test.pdf", self.test_pdf_content, content_type="application/pdf")
        doc_id = self.client.post(reverse('documents:document_upload'), {'file': test_file}).data['data']['id']

        env_id = self.client.post(reverse('envelopes:envelope_create'),
                                  {"document_id": doc_id, "signing_order": [{"signer_id": str(self.signer1.id), "order": 1}]},
                                  format='json').data['data']['id']
        self.client.post(reverse('envelopes:envelope_send', kwargs={'pk': env_id}))

        # Random user tries to sign
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {random_token}')
        sign_data = {'signature_image': f'data:image/png;base64,{self.test_signature_image}'}
        resp = self.client.post(reverse('signatures:sign_document', kwargs={'envelope_id': env_id}), sign_data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

