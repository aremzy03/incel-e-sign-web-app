"""
Tests for merging documents endpoint.
"""

import io
import os
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from reportlab.pdfgen import canvas
from documents.models import Document


def _make_pdf_bytes(text: str = "Test PDF") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, text)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


class MergeDocumentsApiTest(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="merge", email="merge@test.com", password="pass1234")
        # Bypass JWT flow in unit tests; authenticate directly
        self.client.force_authenticate(user=self.user)

    def _create_doc(self, owner, name: str) -> Document:
        pdf_bytes = _make_pdf_bytes(name)
        rel_path = f"staging/{owner.id}_{name}.pdf"
        abs_path = os.path.join(str(settings.MEDIA_ROOT), rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'wb') as f:
            f.write(pdf_bytes)
        file_url = f"{settings.MEDIA_URL}{rel_path}"
        return Document.objects.create(owner=owner, file_url=file_url, file_name=f"{name}.pdf", file_size=len(pdf_bytes), status='draft')

    def test_merge_success(self):
        d1 = self._create_doc(self.user, "docA")
        d2 = self._create_doc(self.user, "docB")
        url = reverse('documents:documents-merge')
        resp = self.client.post(url, {"document_ids": [str(d1.id), str(d2.id)], "name": "custom-name.pdf"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.data['data']
        self.assertIn('id', data)
        self.assertIn('file_url', data)
        self.assertEqual(data.get('name'), "custom-name.pdf")

    def test_merge_placeholder_name_overridden(self):
        d1 = self._create_doc(self.user, "Contract")
        d2 = self._create_doc(self.user, "Annex")
        url = reverse('documents:documents-merge')
        resp = self.client.post(url, {"document_ids": [str(d1.id), str(d2.id)], "name": "merged.pdf"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.data['data']
        self.assertEqual(data.get('name'), "Merged - Contract (+1).pdf")

    def test_merge_default_name_option_a(self):
        d1 = self._create_doc(self.user, "Contract")
        d2 = self._create_doc(self.user, "Annex")
        d3 = self._create_doc(self.user, "Schedule")
        url = reverse('documents:documents-merge')
        resp = self.client.post(url, {"document_ids": [str(d1.id), str(d2.id), str(d3.id)]}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.data['data']
        self.assertEqual(data.get('name'), "Merged - Contract (+2).pdf")

    def test_merge_requires_two(self):
        d1 = self._create_doc(self.user, "only")
        url = reverse('documents:documents-merge')
        resp = self.client.post(url, {"document_ids": [str(d1.id)]}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_merge_denies_other_user_docs(self):
        User = get_user_model()
        other = User.objects.create_user(username="other", email="other@test.com", password="pass1234")
        d_other = self._create_doc(other, "foreign")
        d_self = self._create_doc(self.user, "own")
        url = reverse('documents:documents-merge')
        resp = self.client.post(url, {"document_ids": [str(d_self.id), str(d_other.id)]}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_merge_preserves_order(self):
        d1 = self._create_doc(self.user, "first")
        d2 = self._create_doc(self.user, "second")
        url = reverse('documents:documents-merge')
        resp = self.client.post(url, {"document_ids": [str(d1.id), str(d2.id)], "name": "order.pdf"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_merge_missing_source_file(self):
        d1 = self._create_doc(self.user, "exists")
        d2 = self._create_doc(self.user, "to_delete")
        # Delete the underlying file for d2
        rel = d2.file_url[len(settings.MEDIA_URL):] if d2.file_url.startswith(settings.MEDIA_URL) else d2.file_url
        abs_path = os.path.join(str(settings.MEDIA_ROOT), rel)
        if os.path.exists(abs_path):
            os.remove(abs_path)
        url = reverse('documents:documents-merge')
        resp = self.client.post(url, {"document_ids": [str(d1.id), str(d2.id)]}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

