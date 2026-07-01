"""
Celery tasks for async PDF signing workflows.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from celery import chord, group, shared_task
from django.utils import timezone

from envelopes.models import EnvelopeDocument
from signatures.models import Signature, SigningJob
from signatures.services.signing import complete_envelope, mark_signature_signed
from signatures.services.signing_worker import embed_envelope_document_for_signer

LOGGER = logging.getLogger(__name__)

SIGNING_JOB_QUEUED = "SIGNING_JOB_QUEUED"
SIGNING_JOB_SUCCEEDED = "SIGNING_JOB_SUCCEEDED"
SIGNING_JOB_FAILED = "SIGNING_JOB_FAILED"

try:
    import sentry_sdk
except ImportError:  # pragma: no cover
    sentry_sdk = None


@contextmanager
def _sentry_signing_span(op: str, job: SigningJob, **tags):
    """Wrap signing task work in a Sentry span when the SDK is configured."""
    if sentry_sdk is None:
        yield
        return
    with sentry_sdk.start_span(op=op) as span:
        span.set_tag("job_id", str(job.id))
        span.set_tag("envelope_id", str(job.envelope_id))
        span.set_tag("signer_id", str(job.signer_id))
        for key, value in tags.items():
            span.set_tag(key, value)
        yield span


def _log_job_event(job: SigningJob, message: str, **extra):
    LOGGER.info(
        message,
        extra={
            "job_id": str(job.id),
            "envelope_id": str(job.envelope_id),
            "signer_id": str(job.signer_id),
            **extra,
        },
    )


def _notify_next_signer(envelope):
    from notifications.tasks import send_turn_to_sign_email_task
    from notifications.utils import create_notification, create_signer_turn_notification
    from signatures.models import Signature

    def get_order_for_signer_id(signer_id: str) -> int:
        if not envelope.signing_order:
            return 0
        for idx, signer_entry in enumerate(envelope.signing_order, 1):
            if str(signer_entry.get('signer_id')) == str(signer_id):
                explicit = signer_entry.get('order')
                return explicit if isinstance(explicit, int) and explicit >= 1 else idx
        return 0

    pending = Signature.objects.filter(envelope=envelope, status='pending').select_related('signer')
    if not pending.exists():
        return

    next_signature = min(pending, key=lambda sig: sig.get_signing_order())
    message = create_signer_turn_notification(envelope)
    create_notification(str(next_signature.signer.id), message)
    recipient_email = getattr(next_signature.signer, 'email', None)
    if recipient_email:
        try:
            send_turn_to_sign_email_task.delay(
                recipient_email,
                envelope.name,
                str(envelope.id),
            )
        except Exception as exc:
            LOGGER.error("Error sending turn-to-sign email: %s", exc)


def _mark_job_failed(job: SigningJob, error_message: str) -> None:
    job.status = "failed"
    job.error_message = error_message[:2000]
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
    if job.signature_id:
        Signature.objects.filter(pk=job.signature_id, status="processing").update(status="pending")
    from audit.utils import log_action

    log_action(
        job.signer,
        SIGNING_JOB_FAILED,
        job,
        f"Signing job {job.id} failed: {error_message}",
    )
    _log_job_event(job, "signing_job_failed", error=error_message)


@shared_task(bind=True, max_retries=3, default_retry_delay=30, queue="signing")
def embed_document_for_signer(self, job_id: str, envelope_document_id: str) -> dict:
    """Embed signature for a single envelope document."""
    job = SigningJob.objects.select_related("envelope", "signer").get(pk=job_id)
    env_doc = EnvelopeDocument.objects.select_related("document").get(pk=envelope_document_id)
    start = time.monotonic()
    try:
        with _sentry_signing_span("signing.embed_document", job, document_id=str(env_doc.document_id)):
            embed_envelope_document_for_signer(
                job.envelope,
                job.signer,
                env_doc,
                job.signature_image_data,
                fallback_placement=job.fallback_placement or {},
            )
        duration = time.monotonic() - start
        _log_job_event(
            job,
            "embed_document_succeeded",
            document_id=str(env_doc.document_id),
            duration_s=round(duration, 3),
        )
        return {"envelope_document_id": envelope_document_id, "ok": True}
    except Exception as exc:
        LOGGER.exception(
            "embed_document_for_signer failed job_id=%s document_id=%s",
            job_id,
            env_doc.document_id,
        )
        from django.conf import settings as django_settings

        eager = getattr(django_settings, "CELERY_TASK_ALWAYS_EAGER", False)
        if not eager and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        return {
            "envelope_document_id": envelope_document_id,
            "ok": False,
            "error": str(exc),
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=30, queue="signing")
def finalize_signer_chord(self, results: list, job_id: str) -> None:
    """Finalize signer after all per-document embed tasks complete."""
    job = SigningJob.objects.select_related("envelope", "signer", "signature").get(pk=job_id)
    try:
        with _sentry_signing_span("signing.finalize_chord", job):
            if not results or not all(r.get("ok") for r in results):
                raise RuntimeError("One or more document embed tasks failed")

            envelope = job.envelope
            signature = job.signature
            if signature is None and not job.is_self_sign:
                signature = Signature.objects.filter(envelope=envelope, signer=job.signer).first()

            if signature and signature.status == "processing":
                mark_signature_signed(signature, job.signature_image_data)

            remaining_pending = Signature.objects.filter(envelope=envelope, status="pending").count()
            if remaining_pending == 0:
                complete_envelope(envelope, notify_creator=not job.is_self_sign)
            else:
                _notify_next_signer(envelope)

            job.status = "succeeded"
            job.error_message = ""
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])

            from audit.utils import log_action

            log_action(
                job.signer,
                SIGNING_JOB_SUCCEEDED,
                job,
                f"Signing job {job.id} succeeded for envelope {envelope.id}.",
            )
            _log_job_event(job, "signing_job_succeeded")
    except Exception as exc:
        from django.conf import settings as django_settings

        eager = getattr(django_settings, "CELERY_TASK_ALWAYS_EAGER", False)
        if not eager and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        _mark_job_failed(job, str(exc))


@shared_task(bind=True, max_retries=3, default_retry_delay=30, queue="signing")
def process_signing_job(self, job_id: str) -> None:
    """Orchestrate parallel per-document signing for a job."""
    from django.conf import settings as django_settings

    job = SigningJob.objects.select_related("envelope", "signer").get(pk=job_id)
    job.status = "processing"
    job.attempt_count += 1
    job.save(update_fields=["status", "attempt_count", "updated_at"])
    _log_job_event(job, "signing_job_processing")

    envelope_documents = list(
        EnvelopeDocument.objects.filter(envelope=job.envelope).order_by("order").values_list("id", flat=True)
    )
    if not envelope_documents:
        _mark_job_failed(job, "No documents found in envelope")
        return

    try:
        with _sentry_signing_span("signing.process_job", job):
            if getattr(django_settings, "CELERY_TASK_ALWAYS_EAGER", False):
                results = [
                    embed_document_for_signer.apply(args=(str(job.id), str(doc_id))).result
                    for doc_id in envelope_documents
                ]
                finalize_signer_chord.apply(args=(results, str(job.id)))
                return

            header = group(
                embed_document_for_signer.s(str(job.id), str(doc_id))
                for doc_id in envelope_documents
            )
            callback = finalize_signer_chord.s(str(job.id))
            chord(header)(callback)
    except Exception as exc:
        eager = getattr(django_settings, "CELERY_TASK_ALWAYS_EAGER", False)
        if not eager and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
        _mark_job_failed(job, str(exc))


def enqueue_signing_job(job: SigningJob) -> str:
    """Enqueue process_signing_job and persist celery task id."""
    async_result = process_signing_job.apply_async(args=[str(job.id)], queue="signing")
    job.celery_task_id = async_result.id or ""
    job.save(update_fields=["celery_task_id", "updated_at"])
    return async_result.id
