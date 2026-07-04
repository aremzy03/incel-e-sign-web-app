"""
Unit tests for signing task retry policy and signature resolution helpers.
"""

import pytest
from botocore.exceptions import EndpointConnectionError

from signatures.services.signing import SignatureImageError
from signatures.tasks import _is_retryable_signing_error, _signature_image_for_job


def test_is_retryable_signing_error_for_transient_s3_failures():
    exc = EndpointConnectionError(endpoint_url="https://example.s3.amazonaws.com/key")
    assert _is_retryable_signing_error(exc) is True


def test_is_retryable_signing_error_for_connection_errors():
    assert _is_retryable_signing_error(ConnectionError("network down")) is True
    assert _is_retryable_signing_error(TimeoutError()) is True


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("signature_image is empty"),
        SignatureImageError("missing signature"),
        FileNotFoundError("PDF not found"),
    ],
)
def test_is_retryable_signing_error_for_permanent_failures(exc):
    assert _is_retryable_signing_error(exc) is False


def test_is_retryable_signing_error_for_unknown_exceptions():
    assert _is_retryable_signing_error(RuntimeError("unexpected")) is False


@pytest.mark.django_db
def test_signature_image_for_job_resolves_deferred_user_signature(settings, tmp_path):
    """Embed tasks re-resolve signature_id jobs when signature_image_data is empty."""
    from django.contrib.auth import get_user_model
    from django.core.files.uploadedfile import SimpleUploadedFile

    from envelopes.models import Envelope
    from signatures.models import SigningJob, UserSignature

    settings.MEDIA_ROOT = tmp_path
    User = get_user_model()
    signer = User.objects.create_user(
        email="signer@test.com", username="signer", full_name="Signer", password="pass1234"
    )
    envelope = Envelope.objects.create(creator=signer, name="Test", status="pending")
    user_sig = UserSignature.objects.create(
        user=signer,
        image=SimpleUploadedFile(
            "sig.png",
            b"\x89PNG\r\n\x1a\n",
            content_type="image/png",
        ),
    )
    job = SigningJob.objects.create(
        envelope=envelope,
        signer=signer,
        status="processing",
        signature_image_data="",
        user_signature_id=user_sig.id,
    )

    image_data = _signature_image_for_job(job)

    assert image_data.startswith("data:image/")
    job.refresh_from_db()
    assert job.signature_image_data.startswith("data:image/")


@pytest.mark.django_db
def test_signature_image_for_job_raises_when_unresolved():
    from django.contrib.auth import get_user_model

    from envelopes.models import Envelope
    from signatures.models import SigningJob

    User = get_user_model()
    signer = User.objects.create_user(
        email="signer@test.com", username="signer", full_name="Signer", password="pass1234"
    )
    envelope = Envelope.objects.create(creator=signer, name="Test", status="pending")
    job = SigningJob.objects.create(
        envelope=envelope,
        signer=signer,
        status="processing",
        signature_image_data="",
    )

    with pytest.raises(SignatureImageError):
        _signature_image_for_job(job)
