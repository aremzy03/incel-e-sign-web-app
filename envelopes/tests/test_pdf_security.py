"""
Tests for PDF security utilities.
"""

import os
import tempfile

from django.test import TestCase
from pypdf import PdfReader, PdfWriter

from envelopes.utils.pdf_security import lock_pdf_with_password


class PdfSecurityUtilsTests(TestCase):
    """Tests for the PDF locking helper."""

    def test_lock_pdf_with_password_creates_encrypted_copy(self):
        password = "securePass123"
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = os.path.join(tmpdir, "source.pdf")

            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with open(source_path, "wb") as pdf_file:
                writer.write(pdf_file)

            locked_path = lock_pdf_with_password(pdf_path=source_path, password=password)

            self.assertIsNotNone(locked_path)
            self.assertTrue(os.path.exists(locked_path))

            reader = PdfReader(locked_path)
            self.assertTrue(reader.is_encrypted)
            self.assertNotEqual(reader.decrypt(password), 0)

    def test_lock_pdf_with_password_returns_none_for_missing_file(self):
        password = "AnotherPass456"
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = os.path.join(tmpdir, "missing.pdf")
            locked_path = lock_pdf_with_password(pdf_path=missing_path, password=password)
            self.assertIsNone(locked_path)

