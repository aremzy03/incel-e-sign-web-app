"""
Tests for notifications functionality in the E-Sign application.
"""

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, Mock, call
from users.models import CustomUser
from notifications.models import Notification
from notifications.utils import create_notification
from documents.models import Document
from envelopes.models import Envelope
from signatures.models import Signature


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def user():
    """Create a test user."""
    return CustomUser.objects.create_user(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        password="testpass123"
    )


@pytest.fixture
def signer1():
    """Create a test signer."""
    return CustomUser.objects.create_user(
        username="signer1",
        email="signer1@example.com",
        full_name="Signer One",
        password="testpass123"
    )


@pytest.fixture
def signer2():
    """Create a test signer."""
    return CustomUser.objects.create_user(
        username="signer2",
        email="signer2@example.com",
        full_name="Signer Two",
        password="testpass123"
    )


@pytest.fixture
def document(user):
    """Create a test document."""
    return Document.objects.create(
        owner=user,
        file_name="test.pdf",
        file_url="/media/test.pdf",
        file_size=1024
    )


@pytest.fixture
def envelope(user, document, signer1, signer2):
    """Create a test envelope."""
    return Envelope.objects.create(
        document=document,
        creator=user,
        signing_order=[
            {"signer_id": str(signer1.id), "order": 1},
            {"signer_id": str(signer2.id), "order": 2}
        ]
    )


class TestNotificationModel:
    """Test Notification model functionality."""
    
    @pytest.mark.django_db
    def test_notification_creation(self, user):
        """Test creating a notification."""
        notification = Notification.objects.create(
            user=user,
            message="Test notification"
        )
        
        assert notification.user == user
        assert notification.message == "Test notification"
        assert notification.is_read is False
        assert notification.created_at is not None
    
    @pytest.mark.django_db
    def test_notification_str_representation(self, user):
        """Test notification string representation."""
        notification = Notification.objects.create(
            user=user,
            message="Test notification"
        )
        
        expected = f"Notification for {user.email}: Test notification..."
        assert str(notification) == expected
    
    @pytest.mark.django_db
    def test_notification_ordering(self, user):
        """Test notification ordering by created_at desc."""
        notification1 = Notification.objects.create(
            user=user,
            message="First notification"
        )
        notification2 = Notification.objects.create(
            user=user,
            message="Second notification"
        )
        
        notifications = list(Notification.objects.all())
        assert notifications[0] == notification2  # Most recent first
        assert notifications[1] == notification1


class TestNotificationUtils:
    """Test notification utility functions."""
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification.delay')
    def test_create_notification_task(self, mock_delay, user):
        """Test create_notification Celery task."""
        # Mock the delay method to return a mock result
        mock_result = Mock()
        mock_result.result = str(user.id)
        mock_delay.return_value = mock_result
        
        result = create_notification.delay(
            str(user.id),
            "Test notification from task"
        )
        
        # Verify the task was called with correct parameters
        mock_delay.assert_called_once_with(
            str(user.id),
            "Test notification from task"
        )
        
        # Since we're mocking, we need to test the actual task function directly
        # Import the function directly to avoid the mocked version
        import notifications.utils as utils
        
        # Test the actual task function (not the delay method)
        task_result = utils.create_notification(str(user.id), "Test notification from task")
        
        # Check notification was created
        notification = Notification.objects.filter(
            user=user,
            message="Test notification from task"
        ).first()
        
        assert notification is not None
        assert notification.message == "Test notification from task"
        assert task_result == str(notification.id)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification.delay')
    def test_create_notification_invalid_user(self, mock_delay):
        """Test create_notification with invalid user ID."""
        # Mock the delay method
        mock_result = Mock()
        mock_result.result = None
        mock_delay.return_value = mock_result
        
        result = create_notification.delay(
            "00000000-0000-0000-0000-000000000000",
            "Test notification"
        )
        
        # Verify the task was called
        mock_delay.assert_called_once_with(
            "00000000-0000-0000-0000-000000000000",
            "Test notification"
        )
        
        # Test the actual task function directly
        # Import the function directly to avoid the mocked version
        import notifications.utils as utils
        task_result = utils.create_notification(
            "00000000-0000-0000-0000-000000000000",
            "Test notification"
        )
        
        assert task_result is None


class TestNotificationTemplates:
    """Test notification template functions."""
    
    @pytest.mark.django_db
    def test_envelope_sent_notification_template(self, user, document):
        """Test envelope sent notification template."""
        from notifications.utils import create_envelope_sent_notification
        
        envelope = Envelope.objects.create(
            document=document,
            creator=user,
            signing_order=[]
        )
        
        message = create_envelope_sent_notification(envelope)
        expected = f"{user.full_name} has requested you to sign the document '{document.file_name}'."
        assert message == expected
    
    @pytest.mark.django_db
    def test_signer_turn_notification_template(self, user, document):
        """Test signer turn notification template."""
        from notifications.utils import create_signer_turn_notification
        
        envelope = Envelope.objects.create(
            document=document,
            creator=user,
            signing_order=[]
        )
        
        message = create_signer_turn_notification(envelope)
        expected = f"It is now your turn to sign the document '{document.file_name}'."
        assert message == expected
    
    @pytest.mark.django_db
    def test_envelope_completed_notification_template(self, user, document):
        """Test envelope completed notification template."""
        from notifications.utils import create_envelope_completed_notification
        
        envelope = Envelope.objects.create(
            document=document,
            creator=user,
            signing_order=[]
        )
        
        message = create_envelope_completed_notification(envelope)
        expected = f"Your envelope for '{document.file_name}' has been fully signed and completed."
        assert message == expected
    
    @pytest.mark.django_db
    def test_signer_declined_notification_template(self, user, signer1, document):
        """Test signer declined notification template."""
        from notifications.utils import create_signer_declined_notification
        
        envelope = Envelope.objects.create(
            document=document,
            creator=user,
            signing_order=[]
        )
        
        message = create_signer_declined_notification(envelope, signer1)
        expected = f"Signer {signer1.full_name} declined to sign the document '{document.file_name}'. The envelope has been rejected."
        assert message == expected
    
    @pytest.mark.django_db
    def test_envelope_rejected_notification_template(self, user, document):
        """Test envelope rejected notification template."""
        from notifications.utils import create_envelope_rejected_notification
        
        envelope = Envelope.objects.create(
            document=document,
            creator=user,
            signing_order=[]
        )
        
        message = create_envelope_rejected_notification(envelope)
        expected = f"{user.full_name} has cancelled the envelope for '{document.file_name}'."
        assert message == expected


class TestNotificationViews:
    """Test notification API views."""
    
    @pytest.mark.django_db
    def test_list_notifications_authenticated(self, api_client, user):
        """Test listing notifications for authenticated user."""
        # Create test notifications
        Notification.objects.create(
            user=user,
            message="Test notification 1"
        )
        Notification.objects.create(
            user=user,
            message="Test notification 2"
        )
        
        # Authenticate and make request
        api_client.force_authenticate(user=user)
        response = api_client.get(reverse('notification-list'))
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert response.data[0]['message'] == "Test notification 2"  # Most recent first
        assert response.data[1]['message'] == "Test notification 1"
    
    def test_list_notifications_unauthenticated(self, api_client):
        """Test listing notifications without authentication."""
        response = api_client.get(reverse('notification-list'))
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    @pytest.mark.django_db
    def test_list_notifications_only_user_own(self, api_client, user, signer1):
        """Test that users only see their own notifications."""
        # Create notifications for different users
        Notification.objects.create(
            user=user,
            message="User notification"
        )
        Notification.objects.create(
            user=signer1,
            message="Signer notification"
        )
        
        # Authenticate as user and make request
        api_client.force_authenticate(user=user)
        response = api_client.get(reverse('notification-list'))
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['message'] == "User notification"
    
    @pytest.mark.django_db
    def test_mark_notification_read(self, api_client, user):
        """Test marking a notification as read."""
        notification = Notification.objects.create(
            user=user,
            message="Test notification"
        )
        
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            reverse('notification-read', kwargs={'notification_id': notification.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['message'] == "Notification marked as read"
        
        # Check notification was marked as read
        notification.refresh_from_db()
        assert notification.is_read is True
    
    @pytest.mark.django_db
    def test_mark_notification_read_unauthenticated(self, api_client, user):
        """Test marking notification as read without authentication."""
        notification = Notification.objects.create(
            user=user,
            message="Test notification"
        )
        
        response = api_client.patch(
            reverse('notification-read', kwargs={'notification_id': notification.id})
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    @pytest.mark.django_db
    def test_mark_notification_read_other_user(self, api_client, user, signer1):
        """Test that users can only mark their own notifications as read."""
        notification = Notification.objects.create(
            user=signer1,
            message="Signer notification"
        )
        
        # Try to mark signer's notification as read while authenticated as user
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            reverse('notification-read', kwargs={'notification_id': notification.id})
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        # Check notification was not marked as read
        notification.refresh_from_db()
        assert notification.is_read is False


class TestNotificationTriggers:
    """Test notification triggers in envelope and signature workflows."""
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification.delay')

    def test_envelope_send_notifies_first_signer(self, mock_create_notification, api_client, user, envelope, signer1, document):
        """Test that sending envelope notifies first signer."""
        api_client.force_authenticate(user=user)
        
        # Send envelope
        response = api_client.post(
            reverse('envelopes:envelope_send', kwargs={'pk': envelope.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check notification was sent to first signer with creator name and file name
        expected_message = f"{user.full_name} has requested you to sign the document '{document.file_name}'."
        mock_create_notification.assert_called_with(str(signer1.id), expected_message)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification.delay')
    def test_envelope_reject_notifies_all_signers(self, mock_create_notification, api_client, user, envelope, signer1, signer2):
        """Test that rejecting envelope notifies all signers."""
        api_client.force_authenticate(user=user)
        
        # Reject envelope
        response = api_client.post(
            reverse('envelopes:envelope_reject', kwargs={'pk': envelope.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check notifications were sent to all signers with creator name and file name
        expected_message = f"{user.full_name} has cancelled the envelope for '{envelope.document.file_name}'."
        expected_calls = [
            call(str(signer1.id), expected_message),
            call(str(signer2.id), expected_message)
        ]
        mock_create_notification.assert_has_calls(expected_calls, any_order=True)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification.delay')
    def test_signer_signs_notifies_next_signer(self, mock_create_notification, api_client, user, envelope, signer1, signer2):
        """Test that signing notifies next signer."""
        # Send envelope first to create signatures
        envelope.status = "sent"
        envelope.save()
        
        # Create signature records
        Signature.objects.create(envelope=envelope, signer=signer1, status='pending')
        Signature.objects.create(envelope=envelope, signer=signer2, status='pending')
        
        api_client.force_authenticate(user=signer1)
        
        # Sign document
        response = api_client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': envelope.id}),
            data={'signature_image': 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check notification was sent to next signer with file name
        expected_message = f"It is now your turn to sign the document '{envelope.document.file_name}'."
        mock_create_notification.assert_called_with(str(signer2.id), expected_message)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification.delay')
    def test_last_signer_signs_notifies_creator(self, mock_create_notification, api_client, user, envelope, signer1, signer2):
        """Test that last signer signing notifies creator."""
        # Send envelope first to create signatures
        envelope.status = "sent"
        envelope.save()
        
        # Create signature records - signer1 already signed
        Signature.objects.create(envelope=envelope, signer=signer1, status='signed')
        Signature.objects.create(envelope=envelope, signer=signer2, status='pending')
        
        api_client.force_authenticate(user=signer2)
        
        # Sign document (last signer)
        response = api_client.post(
            reverse('signatures:sign_document', kwargs={'envelope_id': envelope.id}),
            data={'signature_image': 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check notification was sent to creator with file name
        expected_message = f"Your envelope for '{envelope.document.file_name}' has been fully signed and completed."
        mock_create_notification.assert_called_with(str(user.id), expected_message)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification.delay')
    def test_signer_declines_notifies_creator(self, mock_create_notification, api_client, user, envelope, signer1):
        """Test that declining notifies creator."""
        # Send envelope first to create signatures
        envelope.status = "sent"
        envelope.save()
        
        # Create signature record
        Signature.objects.create(envelope=envelope, signer=signer1, status='pending')
        
        api_client.force_authenticate(user=signer1)
        
        # Decline signature
        response = api_client.post(
            reverse('signatures:decline_signature', kwargs={'envelope_id': envelope.id}),
            data={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check notification was sent to creator with signer name and file name
        expected_message = f"Signer {signer1.full_name} declined to sign the document '{envelope.document.file_name}'. The envelope has been rejected."
        mock_create_notification.assert_called_with(str(user.id), expected_message)
