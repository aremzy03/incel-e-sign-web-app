import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from documents.models import Document
from envelopes.models import Envelope, EnvelopeDocument # Import EnvelopeDocument
from django.utils import timezone

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
        # No SimpleUploadedFile needed if not testing upload views
        
        self.document1 = Document.objects.create(
            owner=self.creator,
            file_url="/media/test_document1.pdf",
            file_name="test_document1.pdf",
            file_size=len(pdf_content)
        )
        self.document2 = Document.objects.create(
            owner=self.creator,
            file_url="/media/test_document2.pdf",
            file_name="test_document2.pdf",
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
            creator=self.creator,
            name="My Test Envelope",
            signing_order=signing_order
        )
        EnvelopeDocument.objects.create(envelope=envelope, document=self.document1, order=1)
        
        self.assertEqual(envelope.creator, self.creator)
        self.assertEqual(envelope.status, "draft")
        self.assertEqual(envelope.signing_order, signing_order)
        self.assertEqual(envelope.signer_count, 3)
        self.assertEqual(envelope.name, "My Test Envelope")
        self.assertFalse(envelope.is_completed)
        self.assertFalse(envelope.is_sent)

    def test_envelope_default_status_is_draft(self):
        """Test that envelope status defaults to 'draft'."""
        envelope = Envelope.objects.create(
            creator=self.creator,
            name="Another Test Envelope"
        )
        self.assertEqual(envelope.status, "draft")

    def test_envelope_links_correctly_to_creator_and_documents(self):
        """Test that envelope correctly links to creator and documents."""
        envelope = Envelope.objects.create(
            creator=self.creator,
            name="Linked Test Envelope"
        )
        EnvelopeDocument.objects.create(envelope=envelope, document=self.document1, order=1)
        EnvelopeDocument.objects.create(envelope=envelope, document=self.document2, order=2)
        
        # Test forward relationships
        self.assertEqual(envelope.creator, self.creator)
        self.assertIn(self.document1, [ed.document for ed in envelope.envelopedocument_set.all()])
        self.assertIn(self.document2, [ed.document for ed in envelope.envelopedocument_set.all()])
        
        # Test reverse relationships
        self.assertIn(envelope, self.creator.created_envelopes.all())
        # The document no longer has a direct 'envelopes' reverse relationship
        # Instead, check via EnvelopeDocument
        self.assertTrue(EnvelopeDocument.objects.filter(document=self.document1, envelope=envelope).exists())

    def test_envelope_name_field(self):
        """Test that envelope name field is set correctly and defaults properly."""
        test_name = "Custom Document Name"
        envelope1 = Envelope.objects.create(
            creator=self.creator,
            name=test_name
        )
        self.assertEqual(envelope1.name, test_name)
        
        # Test default name generation
        envelope2 = Envelope.objects.create(
            creator=self.creator
        )
        # Check if name is generated and contains a timestamp-like pattern
        self.assertIsNotNone(envelope2.name)
        self.assertIn("Untitled Envelope", envelope2.name)
        self.assertIn(timezone.now().strftime('%Y-%m'), envelope2.name) # Check for year-month in default name

    def test_envelope_string_representation(self):
        """Test the string representation of an envelope."""
        envelope = Envelope.objects.create(
            creator=self.creator,
            name="My Envelope",
            status="pending"
        )
        
        expected = f"Envelope: My Envelope (pending)"
        self.assertEqual(str(envelope), expected)

        # Test with default name
        envelope_default_name = Envelope.objects.create(
            creator=self.creator,
            status="draft"
        )
        self.assertIn("Envelope: Untitled Envelope", str(envelope_default_name))
        self.assertIn("(draft)", str(envelope_default_name))

    def test_envelope_description_field_optional(self):
        """Test that the description field can be set or left empty."""
        description_text = "Important details for recipients"
        envelope_with_description = Envelope.objects.create(
            creator=self.creator,
            name="Descriptive Envelope",
            description=description_text
        )
        self.assertEqual(envelope_with_description.description, description_text)

        envelope_without_description = Envelope.objects.create(
            creator=self.creator,
            name="No Description Envelope"
        )
        self.assertIsNone(envelope_without_description.description)

    def test_signer_count_property(self):
        """Test the signer_count property."""
        # Empty signing order
        envelope = Envelope.objects.create(
            creator=self.creator,
            name="Empty Signer Envelope",
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
            creator=self.creator,
            name="Status Test Envelope",
            status="draft"
        )
        self.assertFalse(envelope.is_completed)
        self.assertFalse(envelope.is_sent)
        
        # Sent status
        envelope.status = "pending"
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
            creator=self.creator
        )
        
        envelope2 = Envelope.objects.create(
            creator=self.creator
        )
        
        envelopes = Envelope.objects.all()
        self.assertEqual(envelopes[0], envelope2)  # Most recent first
        self.assertEqual(envelopes[1], envelope1)

    def test_cascade_delete_with_documents(self):
        """Test that envelope and EnvelopeDocument links are deleted when creator is deleted."""
        # Create an envelope with multiple documents
        envelope = Envelope.objects.create(
            creator=self.creator,
            name="Cascade Delete Test Envelope"
        )
        EnvelopeDocument.objects.create(envelope=envelope, document=self.document1, order=1)
        EnvelopeDocument.objects.create(envelope=envelope, document=self.document2, order=2)
        
        envelope_id = envelope.id
        doc1_id = self.document1.id
        doc2_id = self.document2.id

        # Delete the creator
        self.creator.delete()

        # Assert envelope is deleted
        self.assertFalse(Envelope.objects.filter(id=envelope_id).exists())
        # Assert EnvelopeDocument links are deleted
        self.assertFalse(EnvelopeDocument.objects.filter(envelope=envelope_id).exists())
        # Documents themselves are deleted when the owner (creator) is deleted
        self.assertFalse(Document.objects.filter(id=doc1_id).exists())
        self.assertFalse(Document.objects.filter(id=doc2_id).exists())

    def test_cascade_delete_with_creator(self):
        """Test that envelope is deleted when creator is deleted."""
        envelope = Envelope.objects.create(
            creator=self.creator,
            name="Creator Delete Test Envelope"
        )
        EnvelopeDocument.objects.create(envelope=envelope, document=self.document1, order=1)
        
        envelope_id = envelope.id
        self.creator.delete()
        
        self.assertFalse(Envelope.objects.filter(id=envelope_id).exists())
        self.assertFalse(EnvelopeDocument.objects.filter(envelope=envelope_id).exists())


class EnvelopeDocumentModelTest(TestCase):
    """Test cases for EnvelopeDocument model functionality."""
    def setUp(self):
        self.creator = User.objects.create_user(username='creator', email='creator@example.com', password='pass')
        self.signer1 = User.objects.create_user(username='signer1', email='signer1@example.com', password='pass')
        self.document1 = Document.objects.create(owner=self.creator, file_url="url1", file_name="doc1", file_size=100)
        self.document2 = Document.objects.create(owner=self.creator, file_url="url2", file_name="doc2", file_size=200)
        self.envelope = Envelope.objects.create(creator=self.creator, name="Test Envelope")

    def test_create_envelope_document(self):
        env_doc = EnvelopeDocument.objects.create(
            envelope=self.envelope, document=self.document1, order=1
        )
        self.assertEqual(env_doc.envelope, self.envelope)
        self.assertEqual(env_doc.document, self.document1)
        self.assertEqual(env_doc.order, 1)
        self.assertIn(env_doc, self.envelope.envelopedocument_set.all())
        self.assertIn(env_doc, self.document1.envelopedocument_set.all())

    def test_unique_together_envelope_document(self):
        EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document1, order=1)
        with self.assertRaises(Exception): # IntegrityError or ValidationError
            EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document1, order=2) # Duplicate document in same envelope

    def test_unique_together_envelope_order(self):
        EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document1, order=1)
        with self.assertRaises(Exception): # IntegrityError or ValidationError
            EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document2, order=1) # Duplicate order in same envelope

    def test_signer_document_positions_field(self):
        positions_data = [
            {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}},
        ]
        env_doc = EnvelopeDocument.objects.create(
            envelope=self.envelope, document=self.document1, order=1,
            signer_document_positions=positions_data
        )
        self.assertEqual(env_doc.signer_document_positions, positions_data)

    def test_string_representation(self):
        env_doc = EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document1, order=1)
        expected_str = f"1. {self.document1.file_name} in {self.envelope.name}"
        self.assertEqual(str(env_doc), expected_str)

    def test_ordering(self):
        EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document1, order=2)
        EnvelopeDocument.objects.create(envelope=self.envelope, document=self.document2, order=1)
        ordered_docs = self.envelope.envelopedocument_set.all()
        self.assertEqual(ordered_docs[0].document, self.document2)
        self.assertEqual(ordered_docs[1].document, self.document1)


class EnvelopeSigningOrderValidationTest(TestCase):
    """Test cases for signing_order validation within the Envelope model (basic list structure)."""

    def setUp(self):
        self.creator = User.objects.create_user(username='creator', email='creator@example.com', password='testpass123')
        self.signer1 = User.objects.create_user(username='signer1', email='signer1@example.com', password='testpass123')
        self.signer2 = User.objects.create_user(username='signer2', email='signer2@example.com', password='testpass123')

    def test_valid_signing_order_list(self):
        """Test that a valid signing_order list (without position) is accepted by the model."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 2}
        ]
        envelope = Envelope.objects.create(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order
        )
        self.assertEqual(envelope.signing_order, signing_order)

    def test_empty_signing_order_list_is_valid(self):
        """Test that an empty signing_order list is valid for the model."""
        envelope = Envelope.objects.create(
            creator=self.creator,
            name="Test Envelope",
            signing_order=[]
        )
        self.assertEqual(envelope.signing_order, [])

    def test_signing_order_not_a_list(self):
        """Test that assigning a non-list to signing_order raises ValidationError during full_clean."""
        envelope = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order="not a list"
        )
        with self.assertRaises(ValidationError):
            envelope.full_clean()
        
    def test_signing_order_entry_not_a_dict(self):
        """Test that an entry in signing_order that is not a dict raises ValidationError during full_clean."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            "invalid_entry"
        ]
        envelope = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order
        )
        with self.assertRaises(ValidationError):
            envelope.full_clean()
        
    def test_signer_id_or_order_missing_in_entry(self):
        """Test that a missing 'signer_id' or 'order' in an entry raises ValidationError during full_clean."""
        signing_order_missing_signer = [
            {"order": 1}
        ]
        envelope1 = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order_missing_signer
        )
        with self.assertRaises(ValidationError):
            envelope1.full_clean()

        signing_order_missing_order = [
            {"signer_id": str(self.signer1.id)}
        ]
        envelope2 = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order_missing_order
        )
        with self.assertRaises(ValidationError):
            envelope2.full_clean()

    def test_signer_id_not_uuid(self):
        """Test that a non-UUID signer_id raises ValidationError during full_clean."""
        signing_order = [
            {"signer_id": "not-a-uuid", "order": 1}
        ]
        envelope = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order
        )
        with self.assertRaises(ValidationError):
            envelope.full_clean()
        
    def test_order_not_positive_integer(self):
        """Test that a non-positive integer order raises ValidationError during full_clean."""
        signing_order_zero = [
            {"signer_id": str(self.signer1.id), "order": 0}
        ]
        envelope1 = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order_zero
        )
        with self.assertRaises(ValidationError):
            envelope1.full_clean()

        signing_order_float = [
            {"signer_id": str(self.signer1.id), "order": 1.5}
        ]
        envelope2 = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order_float
        )
        with self.assertRaises(ValidationError):
            envelope2.full_clean()

    def test_duplicate_signer_ids(self):
        """Test that duplicate signer_ids in signing_order raise ValidationError during full_clean."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer1.id), "order": 2} # Duplicate
        ]
        envelope = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order
        )
        with self.assertRaises(ValidationError):
            envelope.full_clean()
        
    def test_duplicate_orders(self):
        """Test that duplicate orders in signing_order raise ValidationError during full_clean."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 1} # Duplicate
        ]
        envelope = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order
        )
        with self.assertRaises(ValidationError):
            envelope.full_clean()
        
    def test_non_sequential_orders(self):
        """Test that non-sequential orders (gaps) in signing_order raise ValidationError during full_clean."""
        signing_order = [
            {"signer_id": str(self.signer1.id), "order": 1},
            {"signer_id": str(self.signer2.id), "order": 3} # Gap
        ]
        envelope = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order
        )
        with self.assertRaises(ValidationError):
            envelope.full_clean()
        
    def test_nonexistent_signer_ids(self):
        """Test that nonexistent signer IDs in signing_order raise ValidationError during full_clean."""
        non_existent_id = str(uuid.uuid4())
        signing_order = [
            {"signer_id": non_existent_id, "order": 1}
        ]
        envelope = Envelope(
            creator=self.creator,
            name="Test Envelope",
            signing_order=signing_order
        )
        with self.assertRaises(ValidationError) as cm:
            envelope.full_clean()
        self.assertIn(f'Users not found: {[non_existent_id]}', str(cm.exception))

class EnvelopePositionValidationTest(TestCase):
    """
    This test class is now for `EnvelopeDocument` model's signer_document_positions validation.
    The Envelope model itself no longer directly validates positions in signing_order.
    """
    def setUp(self):
        self.creator = User.objects.create_user(username='creator', email='creator@example.com', password='pass')
        self.signer1 = User.objects.create_user(username='signer1', email='signer1@example.com', password='pass')
        self.signer2 = User.objects.create_user(username='signer2', email='signer2@example.com', password='pass') # Added signer2
        self.document1 = Document.objects.create(owner=self.creator, file_url="url1", file_name="doc1", file_size=100)
        self.envelope = Envelope.objects.create(creator=self.creator, name="Test Envelope", signing_order=[{"signer_id": str(self.signer1.id), "order": 1}, {"signer_id": str(self.signer2.id), "order": 2}])
        # Link document to envelope through EnvelopeDocument
        self.env_doc = EnvelopeDocument.objects.create(
            envelope=self.envelope, document=self.document1, order=1
        )

    def test_valid_signer_document_positions(self):
        positions = [
            {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}}
        ]
        self.env_doc.signer_document_positions = positions
        self.env_doc.full_clean() # Should not raise error

    def test_signer_document_positions_empty_list_valid(self):
        self.env_doc.signer_document_positions = []
        self.env_doc.full_clean() # Should not raise error

    def test_signer_document_positions_not_a_list(self):
        self.env_doc.signer_document_positions = "not a list"
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn('Signer document positions must be a list', str(cm.exception))

    def test_signer_document_positions_entry_not_a_dict(self):
        self.env_doc.signer_document_positions = ["not a dict"]
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn(
            'Entry 0 must be a dictionary.',
            cm.exception.message_dict['signer_document_positions'][0]
        )

    def test_signer_id_missing_in_signer_document_position_entry(self):
        self.env_doc.signer_document_positions = [
            {"position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}}
        ] # Missing signer_id
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn('Entry 0 must have "signer_id" key', str(cm.exception))

    def test_position_missing_in_signer_document_position_entry(self):
        self.env_doc.signer_document_positions = [
            {"signer_id": str(self.signer1.id)}
        ] # Missing position
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn('Entry 0 must have "position" key', str(cm.exception))

    def test_signer_id_not_uuid_in_signer_document_position_entry(self):
        self.env_doc.signer_document_positions = [
            {"signer_id": "not-a-uuid", "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}}
        ]
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn('Entry 0: signer_id must be a valid UUID', str(cm.exception))

    def test_position_not_a_dict_in_signer_document_position_entry(self):
        self.env_doc.signer_document_positions = [
            {"signer_id": str(self.signer1.id), "position": "not a dict"}
        ]
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn('Entry 0: position must be a dict', str(cm.exception))

    def test_position_missing_required_keys(self):
        positions_data = [
            {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 10, "y": 20, "width": 30}}
        ] # Missing height
        self.env_doc.signer_document_positions = positions_data
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn('Entry 0: position must include height', str(cm.exception))

    def test_position_values_not_numeric(self):
        positions_data = [
            {"signer_id": str(self.signer1.id), "position": {"page": "one", "x": 10, "y": 20, "width": 30, "height": 40}}
        ]
        self.env_doc.signer_document_positions = positions_data
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn('Entry 0: position[page] must be a positive number or zero', str(cm.exception))

    def test_position_values_negative(self):
        positions_data = [
            {"signer_id": str(self.signer1.id), "position": {"page": -1, "x": 10, "y": 20, "width": 30, "height": 40}}
        ]
        self.env_doc.signer_document_positions = positions_data
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn('Entry 0: position[page] must be a positive number or zero', str(cm.exception))

    def test_position_values_zero_allowed(self):
        positions_data = [
            {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 0, "y": 0, "width": 0, "height": 0}}
        ]
        self.env_doc.signer_document_positions = positions_data
        self.env_doc.full_clean() # Should not raise error

    def test_position_values_floats_allowed(self):
        positions_data = [
            {"signer_id": str(self.signer1.id), "position": {"page": 1, "x": 10.5, "y": 20.5, "width": 30.5, "height": 40.5}}
        ]
        self.env_doc.signer_document_positions = positions_data
        self.env_doc.full_clean() # Should not raise error

    def test_nonexistent_signer_id_in_signer_document_positions(self):
        nonexistent_uuid = str(uuid.uuid4())
        positions_data = [
            {"signer_id": nonexistent_uuid, "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}}
        ]
        self.env_doc.signer_document_positions = positions_data
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn(f'Signer ID {nonexistent_uuid} not found in Envelope signing_order.', str(cm.exception))

    def test_signer_id_not_in_envelope_signing_order(self):
        # Create envelope with signer1 in signing_order
        self.envelope.signing_order = [{"signer_id": str(self.signer1.id), "order": 1}]
        self.envelope.save()

        # Try to set positions for signer2 (not in envelope signing_order)
        positions_data = [
            {"signer_id": str(self.signer2.id), "position": {"page": 1, "x": 10, "y": 20, "width": 30, "height": 40}}
        ]
        self.env_doc.signer_document_positions = positions_data
        with self.assertRaises(ValidationError) as cm:
            self.env_doc.full_clean()
        self.assertIn(f'Signer ID {str(self.signer2.id)} not found in Envelope signing_order.', str(cm.exception))
