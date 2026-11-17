import uuid
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from documents.models import Document, DocumentEditSession, DocumentRevision
from documents.services.document_creation import create_draft_document_from_local_pdf
from documents.services.pdf_files import download_pdf_to_temp
from envelopes.models import Envelope, EnvelopeDocument


def _user(email="owner@test.com"):
    return get_user_model().objects.create_user(
        email=email,
        username=email.split("@")[0] + uuid.uuid4().hex[:6],
        full_name="Owner User",
        password="testpass123",
    )


def _client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _write_pdf(path: Path, rotate: int = 0, password: str | None = None) -> None:
    if rotate or password:
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        if rotate:
            page.rotate(rotate)
        if password:
            writer.encrypt(password)
        with open(path, "wb") as handle:
            writer.write(handle)
        return
    pdf = canvas.Canvas(str(path), pagesize=(612, 792))
    pdf.drawString(72, 100, "Hello")
    pdf.save()


def _document(user, path: Path, status="draft") -> Document:
    document = create_draft_document_from_local_pdf(
        owner=user,
        file_name="draft.pdf",
        local_path=path,
    )
    if status != "draft":
        document.status = status
        document.save(update_fields=["status", "updated_at"])
    return document


def _op(**overrides):
    base = {
        "opId": "box-1",
        "op": "add_text",
        "page": 1,
        "x": 72,
        "y": 40,
        "width": 180,
        "height": 24,
        "text": "Invoice",
        "font": "Helvetica",
        "fontSize": 12,
        "color": "#000000",
        "bold": False,
        "italic": False,
        "align": "left",
    }
    base.update(overrides)
    return base


def _open(client, document):
    return client.post(reverse("documents:document_text_edits", args=[document.id]))


@pytest.mark.django_db
def test_commit_swaps_file_url_and_keeps_previous_object(tmp_path):
    user = _user()
    source = tmp_path / "draft.pdf"
    _write_pdf(source)
    document = _document(user, source)
    old_url = document.file_url
    client = _client(user)
    opened = _open(client, document)
    assert opened.status_code == 200, opened.data
    response = client.post(
        reverse("documents:document_text_edits_commit", args=[document.id]),
        {"ops": [_op()]},
        format="json",
    )
    assert response.status_code == 200, response.data
    document.refresh_from_db()
    assert document.file_url != old_url
    assert f"edits/{document.id}/" in document.file_url
    assert DocumentRevision.objects.filter(document=document, file_url=old_url, source="upload").exists()
    assert DocumentRevision.objects.filter(document=document, source="add_text").exists()
    previous = download_pdf_to_temp(old_url)
    assert previous.exists()
    previous.unlink(missing_ok=True)


@pytest.mark.django_db
def test_commit_pending_envelope_rejected(tmp_path):
    user = _user()
    source = tmp_path / "draft.pdf"
    _write_pdf(source)
    document = _document(user, source)
    envelope = Envelope.objects.create(creator=user, status="pending", name="Out for signature", signing_order=[])
    EnvelopeDocument.objects.create(envelope=envelope, document=document, order=1)
    response = _open(_client(user), document)
    assert response.status_code == 409
    assert response.data["reason"] == "pending_envelope"


@pytest.mark.django_db
def test_commit_non_draft_rejected(tmp_path):
    user = _user()
    source = tmp_path / "sent.pdf"
    _write_pdf(source)
    document = _document(user, source, status="sent")
    response = _open(_client(user), document)
    assert response.status_code == 409
    assert response.data["reason"] == "not_draft"


@pytest.mark.django_db
def test_commit_other_owner_404(tmp_path):
    owner = _user("owner@test.com")
    other = _user("other@test.com")
    source = tmp_path / "draft.pdf"
    _write_pdf(source)
    document = _document(owner, source)
    response = _open(_client(other), document)
    assert response.status_code == 404


@pytest.mark.django_db
def test_commit_rotated_page_rejected(tmp_path):
    user = _user()
    source = tmp_path / "rotated.pdf"
    _write_pdf(source, rotate=90)
    document = _document(user, source)
    response = _open(_client(user), document)
    assert response.status_code == 409
    assert response.data["reason"] == "rotated_pages"
    assert 1 in response.data["pages"]


@pytest.mark.django_db
def test_commit_base_changed(tmp_path):
    user = _user()
    source = tmp_path / "draft.pdf"
    _write_pdf(source)
    document = _document(user, source)
    client = _client(user)
    assert _open(client, document).status_code == 200
    document.file_url = document.file_url + "-replaced"
    document.save(update_fields=["file_url", "updated_at"])
    response = client.post(
        reverse("documents:document_text_edits_commit", args=[document.id]),
        {"ops": [_op()]},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["reason"] == "base_changed"


@pytest.mark.django_db
def test_commit_off_page_box_400(tmp_path):
    user = _user()
    source = tmp_path / "draft.pdf"
    _write_pdf(source)
    document = _document(user, source)
    client = _client(user)
    assert _open(client, document).status_code == 200
    response = client.post(
        reverse("documents:document_text_edits_commit", args=[document.id]),
        {"ops": [_op(x=5000)]},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["errors"][0]["reason"] == "off_page"
    session = DocumentEditSession.objects.get(document=document)
    assert session.ops == []
    assert session.status == "open"


@pytest.mark.django_db
def test_commit_unsupported_character_400(tmp_path):
    user = _user()
    source = tmp_path / "draft.pdf"
    _write_pdf(source)
    document = _document(user, source)
    client = _client(user)
    assert _open(client, document).status_code == 200
    response = client.post(
        reverse("documents:document_text_edits_commit", args=[document.id]),
        {"ops": [_op(text="Hello\u2603")]},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["errors"][0]["reason"] == "unsupported_character"


@pytest.mark.django_db
def test_commit_empty_is_noop(tmp_path):
    user = _user()
    source = tmp_path / "draft.pdf"
    _write_pdf(source)
    document = _document(user, source)
    old_url = document.file_url
    client = _client(user)
    assert _open(client, document).status_code == 200
    response = client.post(
        reverse("documents:document_text_edits_commit", args=[document.id]),
        {"ops": [_op(text="Type your text")]},
        format="json",
    )
    assert response.status_code == 200, response.data
    document.refresh_from_db()
    assert document.file_url == old_url
    session = DocumentEditSession.objects.get(document=document)
    assert session.status == "committed"


@pytest.mark.django_db
def test_autosave_replaces_ops(tmp_path):
    user = _user()
    source = tmp_path / "draft.pdf"
    _write_pdf(source)
    document = _document(user, source)
    client = _client(user)
    assert _open(client, document).status_code == 200
    url = reverse("documents:document_text_edits", args=[document.id])
    first = client.put(url, {"ops": [_op(text="One")]}, format="json")
    assert first.status_code == 200, first.data
    second = client.put(url, {"ops": [_op(opId="other", text="Two")]}, format="json")
    assert second.status_code == 200, second.data
    session = DocumentEditSession.objects.get(document=document)
    assert session.ops == [_op(opId="other", text="Two")]
