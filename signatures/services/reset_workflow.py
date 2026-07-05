"""
Signing workflow reset helpers.

Resets envelope signing workflow state to match the current signing_order:
- Blocks reset when async signing jobs are in-flight.
- Resets Document URLs back to staging originals and clears signed_file_url.
- Best-effort deletes old intermediate signing artifacts.
- Rebuilds Signature rows as pending for each signer in signing_order.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

import boto3
from django.conf import settings
from django.db import transaction

from documents.services.pdf_files import build_signing_key, build_staging_key
from documents.storage import (
    get_permanent_s3_storage,
    get_temp_local_storage,
    persistable_storage_url,
)
from envelopes.models import EnvelopeDocument
from signatures.models import Signature, SigningJob

LOGGER = logging.getLogger(__name__)


class SigningWorkflowInProgressError(RuntimeError):
    """Raised when a reset is requested while async signing is in-flight."""


@dataclass(frozen=True)
class ResetSigningWorkflowResult:
    signatures_created: int
    documents_reset: int
    artifacts_deleted: int


def _use_s3_storage() -> bool:
    return bool(getattr(settings, "USE_S3", False))


def _staging_url_for_document(document_id) -> str:
    key = build_staging_key(document_id)
    storage = get_permanent_s3_storage() if _use_s3_storage() else get_temp_local_storage()
    return persistable_storage_url(storage.url(key))


def _delete_signing_artifacts_for_document(*, envelope_id, document_id) -> int:
    """
    Best-effort delete intermediate signing artifacts for one document.

    Returns number of deleted objects/files (best-effort count).
    """
    deleted = 0
    prefix = os.path.dirname(build_signing_key(envelope_id, document_id, 1)) + "/"

    if _use_s3_storage():
        bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        if not bucket:
            return 0

        try:
            s3_client = boto3.client(
                "s3",
                region_name=settings.AWS_S3_REGION_NAME,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )

            continuation_token = None
            while True:
                kwargs = {"Bucket": bucket, "Prefix": prefix}
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token
                resp = s3_client.list_objects_v2(**kwargs)
                contents = resp.get("Contents", []) or []
                if not contents:
                    break

                keys = [{"Key": item["Key"]} for item in contents if item.get("Key")]
                if keys:
                    s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
                    deleted += len(keys)

                if resp.get("IsTruncated"):
                    continuation_token = resp.get("NextContinuationToken")
                    continue
                break
        except Exception as exc:
            LOGGER.warning(
                "Failed to delete signing artifacts from S3 prefix=%s: %s",
                prefix,
                exc,
            )
        return deleted

    # Local storage cleanup (MEDIA_ROOT/signing/<envelope_id>/<document_id>/)
    try:
        base_dir = os.path.join(str(settings.MEDIA_ROOT), prefix)
        if os.path.isdir(base_dir):
            # Count files before deleting for a best-effort metric.
            for root, _dirs, files in os.walk(base_dir):
                deleted += len(files)
            shutil.rmtree(base_dir, ignore_errors=True)
    except Exception as exc:
        LOGGER.warning("Failed to delete local signing artifacts at %s: %s", prefix, exc)
    return deleted


def assert_no_inflight_signing_jobs(envelope) -> None:
    """Raise SigningWorkflowInProgressError when there are queued/processing jobs."""
    inflight = SigningJob.objects.filter(
        envelope=envelope,
        status__in=["queued", "processing"],
    ).exists()
    if inflight:
        raise SigningWorkflowInProgressError("Signing is currently in progress for this envelope.")


def reset_signing_workflow(envelope) -> ResetSigningWorkflowResult:
    """
    Reset PDFs and signature workflow for an envelope to match its signing_order.

    Requires caller to ensure envelope is editable/resendable by business rules.
    """
    with transaction.atomic():
        locked_envelope = (
            envelope.__class__.objects.select_for_update()
            .prefetch_related("envelopedocument_set__document")
            .get(pk=envelope.pk)
        )

        assert_no_inflight_signing_jobs(locked_envelope)

        artifacts_deleted = 0
        documents_reset = 0

        # Reset PDFs back to staging and clear signed_file_url
        env_docs = list(
            EnvelopeDocument.objects.filter(envelope=locked_envelope).select_related("document")
        )
        for env_doc in env_docs:
            document = env_doc.document
            try:
                document.file_url = _staging_url_for_document(document.id)
                document.signed_file_url = None
                document.save(update_fields=["file_url", "signed_file_url", "updated_at"])
                documents_reset += 1
            except Exception as exc:
                LOGGER.error(
                    "Failed to reset document urls document_id=%s envelope_id=%s: %s",
                    document.id,
                    locked_envelope.id,
                    exc,
                )
                raise

            artifacts_deleted += _delete_signing_artifacts_for_document(
                envelope_id=locked_envelope.id,
                document_id=document.id,
            )

        # Rebuild signatures
        Signature.objects.filter(envelope=locked_envelope).delete()

        created = 0
        for signer_entry in locked_envelope.signing_order or []:
            signer_id = signer_entry.get("signer_id")
            if not signer_id:
                continue
            Signature.objects.create(
                envelope=locked_envelope,
                signer_id=signer_id,
                status="pending",
            )
            created += 1

        return ResetSigningWorkflowResult(
            signatures_created=created,
            documents_reset=documents_reset,
            artifacts_deleted=artifacts_deleted,
        )

