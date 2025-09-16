import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from documents.models import Document
from envelopes.models import Envelope

User = get_user_model()


class EnvelopeModelTest(TestCase):
    """Test cases for Envelope model functionality."""

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.creator = User.objects.create_user(
            username='creator',
            email='creator@example.com',
            password='testpass123',
            full_name='Creator User'
        )
        
        self.signer1 = User.objects.create_user(
            username='signer1',
            email='signer1@example.com',
            password='testpass123',
            full_name='Signer One'
        )
        
        self.signer2 = User.objects.create_user(
            username='signer2',
            email='signer2@example.com',
            password='testpass123',
            full_name='Signer Two'
        )
        
        self.signer3 = User.objects.create_user(
            username='signer3',
            email='signer3@example.com',
            password='testpass123',
            full_name='Signer Three'
        )
        
        # Create test document
        pdf_content = b'%PDF-1.4 fake pdf content'
        pdf_file = SimpleUploadedFile(
            "test_document.pdf",
            pdf_content,
            content_type="application/pdf"
        )
        
        self.document = Document.objects.create(
            owner=self.creator,
            file_url="/media/test_document.pdf",
            file_name="test_document.pdf",
            file_size=len(pdf_content)
        )

    def test_create_valid_envelope_with_signing_order(self):
        """Test creation of a valid envelope with proper signing order."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 2},
            {"signer_id": str(self.signer3.id), "order": 3}
        ]
        
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        self.assertEqual(envelope.document, self.document)
        self.assertEqual(envelope.creator, self.creator)
        self.assertEqual(envelope.status, "draft")
        self.assertEqual(envelope.signing_order, signing_order)
        self.assertEqual(envelope.signer_count, 3)
        self.assertFalse(envelope.is_completed)
        self.assertFalse(envelope.is_sent)

    def test_envelope_default_status_is_draft(self):
        """Test that envelope status defaults to 'draft'."""
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator
        )
        
        self.assertEqual(envelope.status, "draft")

    def test_envelope_links_correctly_to_creator_and_document(self):
        """Test that envelope correctly links to creator and document."""
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator
        )
        
        # Test forward relationships
        self.assertEqual(envelope.document, self.document)
        self.assertEqual(envelope.creator, self.creator)
        
        # Test reverse relationships
        self.assertIn(envelope, self.document.envelopes.all())
        self.assertIn(envelope, self.creator.created_envelopes.all())

    def test_envelope_string_representation(self):
        """Test the string representation of an envelope."""
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            status="sent"
        )
        
        expected = f"Envelope for {self.document.file_name} (sent)"
        self.assertEqual(str(envelope), expected)

    def test_signer_count_property(self):
        """Test the signer_count property."""
        # Empty signing order
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            signing_order=[]
        )
        self.assertEqual(envelope.signer_count, 0)
        
        # With signers
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 2}
        ]
        envelope.signing_order = signing_order
        envelope.save()
        self.assertEqual(envelope.signer_count, 2)

    def test_status_properties(self):
        """Test the status-related properties."""
        # Draft status
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator,
            status="draft"
        )
        self.assertFalse(envelope.is_completed)
        self.assertFalse(envelope.is_sent)
        
        # Sent status
        envelope.status = "sent"
        envelope.save()
        self.assertFalse(envelope.is_completed)
        self.assertTrue(envelope.is_sent)
        
        # Completed status
        envelope.status = "completed"
        envelope.save()
        self.assertTrue(envelope.is_completed)
        self.assertFalse(envelope.is_sent)

    def test_ordering_by_created_at_descending(self):
        """Test that envelopes are ordered by created_at descending."""
        envelope1 = Envelope.objects.create(
            document=self.document,
            creator=self.creator
        )
        
        envelope2 = Envelope.objects.create(
            document=self.document,
            creator=self.creator
        )
        
        envelopes = Envelope.objects.all()
        self.assertEqual(envelopes[0], envelope2)  # Most recent first
        self.assertEqual(envelopes[1], envelope1)

    def test_cascade_delete_with_document(self):
        """Test that envelope is deleted when document is deleted."""
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator
        )
        
        envelope_id = envelope.id
        self.document.delete()
        
        self.assertFalse(Envelope.objects.filter(id=envelope_id).exists())

    def test_cascade_delete_with_creator(self):
        """Test that envelope is deleted when creator is deleted."""
        envelope = Envelope.objects.create(
            document=self.document,
            creator=self.creator
        )
        
        envelope_id = envelope.id
        self.creator.delete()
        
        self.assertFalse(Envelope.objects.filter(id=envelope_id).exists())


class EnvelopeSigningOrderValidationTest(TestCase):
    """Test cases for signing_order validation."""

    def setUp(self):
        """Set up test data."""
        self.creator = User.objects.create_user(
            username='creator',
            email='creator@example.com',
            password='testpass123',
            full_name='Creator User'
        )
        
        self.signer1 = User.objects.create_user(
            username='signer1',
            email='signer1@example.com',
            password='testpass123',
            full_name='Signer One'
        )
        
        self.signer2 = User.objects.create_user(
            username='signer2',
            email='signer2@example.com',
            password='testpass123',
            full_name='Signer Two'
        )
        
        # Create test document
        pdf_content = b'%PDF-1.4 fake pdf content'
        self.document = Document.objects.create(
            owner=self.creator,
            file_url="/media/test_document.pdf",
            file_name="test_document.pdf",
            file_size=len(pdf_content)
        )

    def test_valid_signing_order(self):
        """Test that valid signing order passes validation."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 2}
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        # Should not raise ValidationError
        envelope.full_clean()

    def test_empty_signing_order_is_valid(self):
        """Test that empty signing order is valid."""
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=[]
        )
        
        # Should not raise ValidationError
        envelope.full_clean()

    def test_signing_order_must_be_list(self):
        """Test that signing_order must be a list."""
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order="not a list"
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('Signing order must be a list', str(context.exception))

    def test_signing_order_entries_must_be_dicts(self):
        """Test that signing_order entries must be dictionaries."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            "not a dict"
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('Entry 1 must be a dictionary', str(context.exception))

    def test_signing_order_entries_must_have_required_keys(self):
        """Test that signing_order entries must have required keys."""
        signing_order = [
            {"signer_id": str(self.signer1.id)}  # Missing 'order'
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('must have both "signer_id" and "order" keys', str(context.exception))

    def test_signer_id_must_be_valid_uuid(self):
        """Test that signer_id must be a valid UUID."""
        signing_order = [
            {"signer_id": "not-a-uuid", "order": 1}
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('signer_id must be a valid UUID', str(context.exception))

    def test_order_must_be_positive_integer(self):
        """Test that order must be a positive integer."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 0}  # Invalid order
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('order must be a positive integer', str(context.exception))

    def test_duplicate_signer_ids_raise_validation_error(self):
        """Test that duplicate signer_ids raise ValidationError."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer1.id), "order": 2}  # Duplicate signer_id
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('Duplicate signer_id found', str(context.exception))

    def test_duplicate_orders_raise_validation_error(self):
        """Test that duplicate orders raise ValidationError."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 1}  # Duplicate order
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('Duplicate order found', str(context.exception))

    def test_orders_must_start_from_1_and_have_no_gaps(self):
        """Test that orders must start from 1 and have no gaps."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 2},  # Should start from 1
            {"signer_id": str(self.signer2.id), "order": 4}   # Gap in sequence
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('Orders must start from 1 and have no gaps', str(context.exception))

    def test_orders_must_be_sequential(self):
        """Test that orders must be sequential starting from 1."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 3}  # Gap: missing order 2
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('Orders must start from 1 and have no gaps', str(context.exception))

    def test_nonexistent_user_raises_validation_error(self):
        """Test that non-existent user IDs raise ValidationError."""
        nonexistent_uuid = str(uuid.uuid4())
        signing_order = [
            {"signer_id": nonexistent_uuid, "order": 1}
        ]
        
        envelope = Envelope(
            document=self.document,
            creator=self.creator,
            signing_order=signing_order
        )
        
        with self.assertRaises(ValidationError) as context:
            envelope.full_clean()
        
        self.assertIn('Users not found', str(context.exception))
        self.assertIn(nonexistent_uuid, str(context.exception))
