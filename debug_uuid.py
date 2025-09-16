#!/usr/bin/env python
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esign.settings')
django.setup()

from django.contrib.auth import get_user_model
from documents.models import Document
from envelopes.models import Envelope
from django.core.files.uploadedfile import SimpleUploadedFile
import uuid

User = get_user_model()

# Create test users
creator = User.objects.create_user(
    username='creator',
    email='creator@example.com',
    password='testpass123',
    full_name='Creator User'
)

signer1 = User.objects.create_user(
    username='signer1',
    email='signer1@example.com',
    password='testpass123',
    full_name='Signer One'
)

print(f"Creator ID: {creator.id} (type: {type(creator.id)})")
print(f"Signer1 ID: {signer1.id} (type: {type(signer1.id)})")

# Test UUID validation
creator_id_str = str(creator.id)
signer1_id_str = str(signer1.id)

print(f"Creator ID as string: {creator_id_str}")
print(f"Signer1 ID as string: {signer1_id_str}")

try:
    uuid.UUID(creator_id_str)
    print("Creator UUID validation: SUCCESS")
except Exception as e:
    print(f"Creator UUID validation: FAILED - {e}")

try:
    uuid.UUID(signer1_id_str)
    print("Signer1 UUID validation: SUCCESS")
except Exception as e:
    print(f"Signer1 UUID validation: FAILED - {e}")

# Create test document
pdf_content = b'%PDF-1.4 fake pdf content'
document = Document.objects.create(
    owner=creator,
    file_url="/media/test_document.pdf",
    file_name="test_document.pdf",
    file_size=len(pdf_content)
)

# Test signing order
signing_order = [
    {"signer_id": signer1_id_str, "order": 1}
]

print(f"Signing order: {signing_order}")

# Test envelope creation
try:
    envelope = Envelope(
        document=document,
        creator=creator,
        signing_order=signing_order
    )
    envelope.full_clean()
    print("Envelope validation: SUCCESS")
except Exception as e:
    print(f"Envelope validation: FAILED - {e}")
