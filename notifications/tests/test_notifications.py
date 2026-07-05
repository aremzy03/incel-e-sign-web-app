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
from envelopes.models import Envelope, EnvelopeDocument
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
    """Create a test document with a real PDF on disk."""
    import os

    from django.conf import settings as django_settings

    media_root = django_settings.MEDIA_ROOT
    os.makedirs(media_root, exist_ok=True)
    pdf_path = os.path.join(str(media_root), "test.pdf")
    with open(pdf_path, "wb") as pdf_file:
        pdf_file.write(b"%PDF-1.4\n%EOF")

    return Document.objects.create(
        owner=user,
        file_name="test.pdf",
        file_url="/media/test.pdf",
        file_size=1024,
    )


@pytest.fixture
def envelope(user, document, signer1, signer2):
    """Create a test envelope."""
    env = Envelope.objects.create(
        creator=user,
        signing_order=[
            {"signer_id": str(signer1.id), "order": 1},
            {"signer_id": str(signer2.id), "order": 2}
        ]
    )
    EnvelopeDocument.objects.create(envelope=env, document=document, order=1)
    return env


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
    def test_create_notification_task(self, user):
        """Test that create_notification proxy creates a notification via the Celery task."""
        import notifications.utils as utils

        # CELERY_TASK_ALWAYS_EAGER=True so the task runs synchronously
        utils.create_notification(str(user.id), "Test notification from task")

        notification = Notification.objects.filter(
            user=user,
            message="Test notification from task"
        ).first()

        assert notification is not None
        assert notification.message == "Test notification from task"

    @pytest.mark.django_db
    def test_create_notification_invalid_user(self):
        """Test create_notification with invalid user ID returns None."""
        import notifications.utils as utils

        # CELERY_TASK_ALWAYS_EAGER=True so the task runs synchronously
        # The task returns None when the user is not found
        result = utils.create_notification(
            "00000000-0000-0000-0000-000000000000",
            "Test notification"
        )

        # No notification should have been created
        assert not Notification.objects.filter(
            message="Test notification"
        ).exists()


class TestNotificationTemplates:
    """Test notification template functions."""
    
    @pytest.mark.django_db
    def test_envelope_sent_notification_template(self, user, document):
        """Test envelope sent notification template."""
        from notifications.utils import create_envelope_sent_notification

        envelope = Envelope.objects.create(
            creator=user,
            name="My Test Envelope",
            signing_order=[]
        )

        message = create_envelope_sent_notification(envelope)
        expected = f"{user.full_name} has requested you to sign the document '{envelope.name}'."
        assert message == expected
    
    @pytest.mark.django_db
    def test_signer_turn_notification_template(self, user, document):
        """Test signer turn notification template."""
        from notifications.utils import create_signer_turn_notification

        envelope = Envelope.objects.create(
            creator=user,
            name="My Test Envelope",
            signing_order=[]
        )

        message = create_signer_turn_notification(envelope)
        expected = f"It is now your turn to sign the document '{envelope.name}'."
        assert message == expected
    
    @pytest.mark.django_db
    def test_envelope_completed_notification_template(self, user, document):
        """Test envelope completed notification template."""
        from notifications.utils import create_envelope_completed_notification

        envelope = Envelope.objects.create(
            creator=user,
            name="My Test Envelope",
            signing_order=[]
        )

        message = create_envelope_completed_notification(envelope)
        expected = f"Your envelope for '{envelope.name}' has been fully signed and completed."
        assert message == expected
    
    @pytest.mark.django_db
    def test_signer_declined_notification_template(self, user, signer1, document):
        """Test signer declined notification template."""
        from notifications.utils import create_signer_declined_notification

        envelope = Envelope.objects.create(
            creator=user,
            name="My Test Envelope",
            signing_order=[]
        )

        message = create_signer_declined_notification(envelope, signer1)
        expected = f"Signer {signer1.full_name} declined to sign the document '{envelope.name}'. The envelope has been rejected."
        assert message == expected
    
    @pytest.mark.django_db
    def test_envelope_rejected_notification_template(self, user, document):
        """Test envelope rejected notification template."""
        from notifications.utils import create_envelope_rejected_notification

        envelope = Envelope.objects.create(
            creator=user,
            name="My Test Envelope",
            signing_order=[]
        )

        message = create_envelope_rejected_notification(envelope)
        expected = f"{user.full_name} has cancelled the envelope for '{envelope.name}'."
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
        results = response.data.get('results', response.data)
        assert len(results) == 2
        assert results[0]['message'] == "Test notification 2"  # Most recent first
        assert results[1]['message'] == "Test notification 1"
    
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
        results = response.data.get('results', response.data)
        assert len(results) == 1
        assert results[0]['message'] == "User notification"
    
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
    @patch('notifications.utils.create_notification')
    def test_envelope_send_notifies_first_signer(self, mock_create_notification, api_client, user, envelope, signer1, document):
        """Test that sending envelope notifies first signer."""
        api_client.force_authenticate(user=user)
        
        # Send envelope
        response = api_client.post(
            reverse('envelopes:envelope_send', kwargs={'pk': envelope.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check notification was sent to first signer with creator name and envelope name
        expected_message = f"{user.full_name} has requested you to sign the document '{envelope.name}'."
        mock_create_notification.assert_called_with(str(signer1.id), expected_message)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification')
    def test_envelope_reject_notifies_all_signers(self, mock_create_notification, api_client, user, envelope, signer1, signer2):
        """Test that rejecting envelope notifies all signers."""
        api_client.force_authenticate(user=user)
        
        # Reject envelope
        response = api_client.post(
            reverse('envelopes:envelope_reject', kwargs={'pk': envelope.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Check notifications were sent to all signers with creator name and envelope name
        expected_message = f"{user.full_name} has cancelled the envelope for '{envelope.name}'."
        expected_calls = [
            call(str(signer1.id), expected_message),
            call(str(signer2.id), expected_message)
        ]
        mock_create_notification.assert_has_calls(expected_calls, any_order=True)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification')
    def test_signer_signs_notifies_next_signer(self, mock_create_notification, api_client, user, envelope, signer1, signer2):
        """Test that signing notifies next signer."""
        # Send envelope first to create signatures
        envelope.status = "pending"
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
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        
        # Check notification was sent to next signer with envelope name
        expected_message = f"It is now your turn to sign the document '{envelope.name}'."
        mock_create_notification.assert_called_with(str(signer2.id), expected_message)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification')
    def test_last_signer_signs_notifies_creator(self, mock_create_notification, api_client, user, envelope, signer1, signer2):
        """Test that last signer signing notifies creator."""
        # Send envelope first to create signatures
        envelope.status = "pending"
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
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        
        # Check notification was sent to creator with envelope name
        expected_message = f"Your envelope for '{envelope.name}' has been fully signed and completed."
        mock_create_notification.assert_called_with(str(user.id), expected_message)
    
    @pytest.mark.django_db
    @patch('notifications.utils.create_notification')
    def test_signer_declines_notifies_creator(self, mock_create_notification, api_client, user, envelope, signer1):
        """Test that declining notifies creator."""
        # Send envelope first to create signatures
        envelope.status = "pending"
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
        
        # Check notification was sent to creator with signer name and envelope name
        expected_message = f"Signer {signer1.full_name} declined to sign the document '{envelope.name}'. The envelope has been rejected."
        mock_create_notification.assert_called_with(str(user.id), expected_message)
