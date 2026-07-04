"""
Helpers for creating and enqueueing signing jobs from API views.
"""

from __future__ import annotations

from django.db import transaction

from signatures.models import SigningJob
from signatures.tasks import SIGNING_JOB_QUEUED, enqueue_signing_job


def get_active_signing_job(envelope, signer) -> SigningJob | None:
    """Return an in-flight signing job for this signer, if any."""
    return (
        SigningJob.objects.filter(
            envelope=envelope,
            signer=signer,
            status__in=["queued", "processing"],
        )
        .order_by("-created_at")
        .first()
    )


def create_and_enqueue_signing_job(
    *,
    envelope,
    signer,
    signature,
    signature_image_data: str = '',
    user_signature_id=None,
    fallback_placement: dict,
    is_self_sign: bool = False,
    request=None,
) -> SigningJob:
    """Create a SigningJob, mark signature processing, and enqueue Celery work."""
    with transaction.atomic():
        if signature is not None:
            signature.status = "processing"
            signature.save(update_fields=["status", "updated_at"])

        job = SigningJob.objects.create(
            envelope=envelope,
            signer=signer,
            signature=signature,
            status="queued",
            signature_image_data=signature_image_data or '',
            user_signature_id=user_signature_id,
            fallback_placement=fallback_placement or {},
            is_self_sign=is_self_sign,
        )

    task_id = enqueue_signing_job(job)

    from audit.utils import log_action

    log_action(
        signer,
        SIGNING_JOB_QUEUED,
        job,
        f"Signing job {job.id} queued for envelope {envelope.id} (task={task_id}).",
        request=request,
    )
    return job


def signing_job_response_data(job: SigningJob) -> dict:
    return {
        "job_id": str(job.id),
        "status": job.status,
        "envelope_id": str(job.envelope_id),
    }
