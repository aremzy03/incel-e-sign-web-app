"""
Tests for signing job API endpoints.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from envelopes.models import Envelope
from signatures.models import SigningJob


@pytest.mark.django_db
def test_signing_job_detail_auth():
    User = get_user_model()
    creator = User.objects.create_user(email="c@test.com", username="c", full_name="C", password="pass1234")
    signer = User.objects.create_user(email="s@test.com", username="s", full_name="S", password="pass1234")
    other = User.objects.create_user(email="o@test.com", username="o", full_name="O", password="pass1234")

    envelope = Envelope.objects.create(
        creator=creator,
        name="Job",
        status="pending",
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
    )
    job = SigningJob.objects.create(envelope=envelope, signer=signer, status="queued")

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(signer).access_token}")
    resp = client.get(reverse("signatures:signing-job-detail", kwargs={"id": job.id}))
    assert resp.status_code == 200
    assert resp.data["data"]["id"] == str(job.id)

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(creator).access_token}")
    resp = client.get(reverse("signatures:signing-job-detail", kwargs={"id": job.id}))
    assert resp.status_code == 200

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(other).access_token}")
    resp = client.get(reverse("signatures:signing-job-detail", kwargs={"id": job.id}))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_signing_job_retry_only_when_failed():
    User = get_user_model()
    signer = User.objects.create_user(email="s@test.com", username="s", full_name="S", password="pass1234")
    envelope = Envelope.objects.create(
        creator=signer,
        name="Retry",
        status="pending",
        signing_order=[{"signer_id": str(signer.id), "order": 1}],
    )
    job = SigningJob.objects.create(envelope=envelope, signer=signer, status="queued")

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(signer).access_token}")
    resp = client.post(reverse("signatures:signing-job-retry", kwargs={"id": job.id}))
    assert resp.status_code == 400

    job.status = "failed"
    job.save(update_fields=["status"])
    resp = client.post(reverse("signatures:signing-job-retry", kwargs={"id": job.id}))
    assert resp.status_code == 202
    assert resp.data["data"]["job_id"] == str(job.id)
