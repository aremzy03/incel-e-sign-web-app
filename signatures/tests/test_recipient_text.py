import uuid
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditLog
from documents.models import DocumentRevision
from documents.services.document_creation import create_draft_document_from_local_pdf
from envelopes.models import Envelope, EnvelopeDocument, SigningToken
from signatures.models import Signature


def _user(email):
    return get_user_model().objects.create_user(
        email=email,
        username=email.split("@")[0] + uuid.uuid4().hex[:6],
        full_name="Signer",
        password="testpass123",
    )


def _client(user=None):
    client = APIClient()
    if user is not None:
        token = str(RefreshToken.for_user(user).access_token)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _write_pdf(path: Path, rotate: int = 0) -> None:
    if rotate:
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        page.rotate(rotate)
        with open(path, "wb") as handle:
            writer.write(handle)
        return
    pdf = canvas.Canvas(str(path), pagesize=(612, 792))
    pdf.drawString(72, 100, "Hello")
    pdf.save()


def _op(**overrides):
    base = {
        "opId": "box-1",
        "op": "add_text",
        "page": 1,
        "x": 72,
        "y": 40,
        "width": 180,
        "height": 24,
        "text": "Added by signer",
        "font": "Helvetica",
        "fontSize": 12,
        "color": "#000000",
        "bold": False,
        "italic": False,
        "align": "left",
    }
    base.update(overrides)
    return base


def _pending(tmp_path, *, flag=True, rotate=0, signers=1):
    owner = _user("owner@test.com")
    people = [_user(f"signer{i}@test.com") for i in range(signers)]
    source = tmp_path / "sent.pdf"
    _write_pdf(source, rotate=rotate)
    document = create_draft_document_from_local_pdf(
        owner=owner,
        file_name="sent.pdf",
        local_path=source,
    )
    envelope = Envelope.objects.create(
        creator=owner,
        name="Contract",
        status="pending",
        allow_recipient_text=flag,
        signing_order=[
            {"signer_id": str(person.id), "order": index + 1}
            for index, person in enumerate(people)
        ],
    )
    EnvelopeDocument.objects.create(envelope=envelope, document=document, order=1)
    for person in people:
        Signature.objects.create(envelope=envelope, signer=person, status="pending")
    return envelope, document, people


def _url(envelope, document):
    return reverse("signatures:recipient_add_text", args=[envelope.id, document.id])


@pytest.mark.django_db
def test_current_signer_bakes_text_and_writes_revision(tmp_path):
    envelope, document, people = _pending(tmp_path)
    old_url = document.file_url
    response = _client(people[0]).post(_url(envelope, document), {"ops": [_op()]}, format="json")
    assert response.status_code == 200
    document.refresh_from_db()
    assert document.file_url != old_url
    assert DocumentRevision.objects.filter(document=document, source="recipient_add_text").exists()
    assert DocumentRevision.objects.filter(document=document, file_url=old_url, source="upload").exists()
    assert AuditLog.objects.filter(action="RECIPIENT_ADD_TEXT").exists()


@pytest.mark.django_db
def test_later_signer_is_rejected(tmp_path):
    envelope, document, people = _pending(tmp_path, signers=2)
    response = _client(people[1]).post(_url(envelope, document), {"ops": [_op()]}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_flag_off_is_rejected(tmp_path):
    envelope, document, people = _pending(tmp_path, flag=False)
    response = _client(people[0]).post(_url(envelope, document), {"ops": [_op()]}, format="json")
    assert response.status_code == 403
    assert response.data["reason"] == "flag_off"


@pytest.mark.django_db
def test_rotated_page_is_refused(tmp_path):
    envelope, document, people = _pending(tmp_path, rotate=90)
    response = _client(people[0]).post(_url(envelope, document), {"ops": [_op()]}, format="json")
    assert response.status_code == 409
    assert response.data["reason"] == "rotated_pages"


@pytest.mark.django_db
def test_empty_ops_do_not_change_the_file(tmp_path):
    envelope, document, people = _pending(tmp_path)
    old_url = document.file_url
    response = _client(people[0]).post(_url(envelope, document), {"ops": []}, format="json")
    assert response.status_code == 200
    document.refresh_from_db()
    assert document.file_url == old_url
    assert not DocumentRevision.objects.filter(source="recipient_add_text").exists()


@pytest.mark.django_db
def test_stale_base_is_rejected(tmp_path):
    envelope, document, people = _pending(tmp_path)
    response = _client(people[0]).post(
        _url(envelope, document),
        {"ops": [_op()], "base_file_url": "storage://old.pdf"},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["reason"] == "base_changed"
    document.refresh_from_db()
    assert document.file_url != "storage://old.pdf"


@pytest.mark.django_db
def test_public_token_signer_can_add_text(tmp_path):
    envelope, document, people = _pending(tmp_path)
    token = SigningToken.objects.create(
        envelope=envelope,
        recipient_email=people[0].email,
        recipient_user=people[0],
    )
    response = _client().post(
        _url(envelope, document),
        {"ops": [_op()], "token": token.token},
        format="json",
    )
    assert response.status_code == 200
    document.refresh_from_db()
    assert DocumentRevision.objects.filter(document=document, source="recipient_add_text").exists()
