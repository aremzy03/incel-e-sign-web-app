"""
Shared pytest fixtures for the E-Sign test suite.
"""

import os
from unittest.mock import patch

import pytest

MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
    b"2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n"
    b"3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
)


def _embed_signature_side_effect(*args, **kwargs):
    output_path = kwargs.get("output_path")
    if output_path is None and len(args) >= 2:
        output_path = args[1]
    if output_path:
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "wb") as pdf_file:
            pdf_file.write(MINIMAL_PDF_BYTES)


@pytest.fixture(autouse=True)
def _patch_signing_embed_for_tests():
    """Avoid real image/PDF embedding failures across the async signing pipeline."""
    with patch(
        "signatures.services.signing.embed_signature",
        side_effect=_embed_signature_side_effect,
    ):
        yield


@pytest.fixture(autouse=True)
def _clear_django_cache_between_tests():
    """
    Reset LocMem throttle/cache keys so scoped throttles do not accumulate
    across tests in a long suite run.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
