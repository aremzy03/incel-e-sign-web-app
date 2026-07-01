"""
Shared signing workflow helpers for envelope PDF embedding and completion.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
import string
from datetime import datetime
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from documents.services.pdf_files import download_pdf_to_temp, upload_completed_pdf
from envelopes.models import Envelope, EnvelopeDocument
from envelopes.utils.pdf_security import lock_pdf_with_password
from signatures.models import Signature, UserSignature
from signatures.utils.pdf_signing import embed_signature, embed_text, get_media_absolute_path_from_url

LOGGER = logging.getLogger(__name__)

SIGNATURE_X_OFFSET = 5.0


class SignatureImageError(Exception):
    """Raised when no usable signature image can be resolved for the user."""


class DocumentNotAvailableForSigningError(Exception):
    """Raised when a document PDF is not available in local storage for signing."""


def generate_pdf_lock_password(length: int = 16) -> str:
    """Generate a random password for locking completed PDFs."""
    if length < 8:
        length = 8
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _user_signature_to_data_url(user_signature: UserSignature) -> str:
    user_signature.image.open()
    image_data = user_signature.image.read()
    user_signature.image.close()
    image_format = user_signature.image.name.split('.')[-1].lower()
    if image_format == 'jpg':
        image_format = 'jpeg'
    return f"data:image/{image_format};base64,{base64.b64encode(image_data).decode()}"


def resolve_signature_image(user, validated_data: dict[str, Any]) -> str:
    """
    Resolve signature image data from request payload or stored UserSignature.

    Args:
        user: Authenticated user performing the sign action.
        validated_data: Validated sign payload (signature_image and/or signature_id).

    Returns:
        str: Base64 data URL for the signature image.

    Raises:
        SignatureImageError: When no signature source is available.
    """
    if validated_data.get('signature_image'):
        return validated_data['signature_image']

    signature_id = validated_data.get('signature_id')
    if signature_id:
        try:
            user_signature = UserSignature.objects.get(id=signature_id, user=user)
            return _user_signature_to_data_url(user_signature)
        except UserSignature.DoesNotExist as exc:
            raise SignatureImageError(
                "UserSignature not found or does not belong to you."
            ) from exc

    try:
        default_signature = UserSignature.objects.get(user=user, is_default=True)
        return _user_signature_to_data_url(default_signature)
    except UserSignature.DoesNotExist as exc:
        raise SignatureImageError(
            "No signature provided and no default signature found. "
            "Please provide signature_image, signature_id, or set a default signature."
        ) from exc


def embed_document_pdf_for_signer(
    envelope: Envelope,
    signer,
    env_doc: EnvelopeDocument,
    input_pdf_path: str,
    output_pdf_path: str,
    signature_image_data: str,
    *,
    fallback_placement: dict[str, Any] | None = None,
) -> None:
    """
    Embed signature images and assigned field text for one envelope document.

    Reads from input_pdf_path and writes to output_pdf_path (local paths only).
    """
    from fields.models import Field as FieldModel

    fallback_placement = fallback_placement or {}
    document = env_doc.document
    signer_positions_for_doc = []
    for pos_entry in env_doc.signer_document_positions:
        if str(pos_entry.get('signer_id')) == str(signer.id):
            position = pos_entry.get('position')
            if position:
                signer_positions_for_doc.append(position)

    if not os.path.exists(input_pdf_path):
        raise DocumentNotAvailableForSigningError(
            f"Input PDF not found for document {document.id}"
        )

    if os.path.abspath(output_pdf_path) == os.path.abspath(input_pdf_path):
        output_pdf_path = f"{output_pdf_path}.alt.pdf"

    try:
        if signer_positions_for_doc:
            temp_files_to_cleanup = []
            current_input_path = input_pdf_path

            for idx, position_data in enumerate(signer_positions_for_doc):
                if idx == len(signer_positions_for_doc) - 1:
                    current_output_path = output_pdf_path
                else:
                    current_output_path = f"{output_pdf_path}.tmp{idx}"
                    temp_files_to_cleanup.append(current_output_path)

                if os.path.abspath(current_output_path) == os.path.abspath(current_input_path):
                    current_output_path = f"{output_pdf_path}.tmp_inplace{idx}"
                    temp_files_to_cleanup.append(current_output_path)

                if position_data and isinstance(position_data, dict):
                    required_fields = ['page', 'x', 'y', 'width', 'height']
                    if all(field in position_data for field in required_fields):
                        embed_signature(
                            pdf_path=current_input_path,
                            output_path=current_output_path,
                            signature_image=signature_image_data,
                            page=position_data['page'],
                            x=float(position_data['x']) + SIGNATURE_X_OFFSET,
                            y=position_data['y'],
                            width=position_data['width'],
                            height=position_data['height'],
                        )
                        current_input_path = current_output_path
                    else:
                        LOGGER.warning(
                            "Skipping incomplete position %s for document %s",
                            idx,
                            document.id,
                        )
                else:
                    LOGGER.warning(
                        "Skipping invalid position %s for document %s",
                        idx,
                        document.id,
                    )

            signer_fields = FieldModel.objects.filter(
                envelope=envelope,
                document=document,
                assigned_signer=signer,
            )

            for idx, field in enumerate(signer_fields):
                field_value = field.prefill_value if field.prefill_value is not None else field.value
                if not field_value:
                    continue
                if field.type not in ['initials', 'text', 'designation', 'date']:
                    continue

                text_to_draw = str(field_value)
                if field.type == 'date' and field.date_format:
                    try:
                        parsed = None
                        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                            try:
                                parsed = datetime.strptime(text_to_draw, fmt)
                                break
                            except ValueError:
                                continue
                        if parsed:
                            fmt_map = {
                                'YYYY-MM-DD': "%Y-%m-%d",
                                'DD/MM/YYYY': "%d/%m/%Y",
                                'MMM D, YYYY': "%b %-d, %Y",
                            }
                            out_fmt = fmt_map.get(field.date_format, "%Y-%m-%d")
                            text_to_draw = parsed.strftime(out_fmt)
                    except Exception:
                        pass

                current_output_path = output_pdf_path
                if os.path.abspath(current_output_path) == os.path.abspath(current_input_path):
                    current_output_path = f"{output_pdf_path}.texttmp{idx}"
                    temp_files_to_cleanup.append(current_output_path)
                embed_text(
                    pdf_path=current_input_path,
                    output_path=current_output_path,
                    text=text_to_draw,
                    page=field.page,
                    x=float(field.x) + SIGNATURE_X_OFFSET,
                    y=field.y,
                    font_family=field.font_family or 'Helvetica',
                    font_size=float(field.font_size or 12),
                )
                current_input_path = current_output_path

            if os.path.abspath(current_input_path) != os.path.abspath(output_pdf_path):
                try:
                    os.replace(current_input_path, output_pdf_path)
                except OSError:
                    pass

            for temp_file in temp_files_to_cleanup:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except OSError as cleanup_error:
                    LOGGER.warning("Failed to cleanup temp file %s: %s", temp_file, cleanup_error)
        else:
            embed_signature(
                pdf_path=input_pdf_path,
                output_path=output_pdf_path,
                signature_image=signature_image_data,
                page=fallback_placement.get('page', 1),
                x=float(fallback_placement.get('x', 100)) + SIGNATURE_X_OFFSET,
                y=fallback_placement.get('y', 100),
                width=fallback_placement.get('width', 120),
                height=fallback_placement.get('height', 40),
            )
    except Exception as exc:
        LOGGER.error(
            "Error embedding signature for document %s in envelope %s: %s",
            document.id,
            envelope.id,
            exc,
        )
        raise


def embed_signatures_for_signer(
    envelope: Envelope,
    signer,
    signature_image_data: str,
    *,
    fallback_placement: dict[str, Any] | None = None,
) -> None:
    """
    Embed signature images and assigned field text for each document in the envelope.

    Args:
        envelope: Envelope being signed.
        signer: User performing the signature.
        signature_image_data: Base64 data URL signature image.
        fallback_placement: Optional page/x/y/width/height when no positions are defined.

    Raises:
        DocumentNotAvailableForSigningError: When local PDF source is unavailable.
    """
    from fields.models import Field as FieldModel

    fallback_placement = fallback_placement or {}
    envelope_documents = EnvelopeDocument.objects.filter(envelope=envelope).order_by('order')

    if not envelope_documents.exists():
        raise DocumentNotAvailableForSigningError(
            "No documents found in this envelope to sign."
        )

    for env_doc in envelope_documents:
        document = env_doc.document
        source_url = document.signed_file_url or document.file_url
        try:
            input_pdf_path = get_media_absolute_path_from_url(source_url)
        except ValueError as exc:
            raise DocumentNotAvailableForSigningError(
                "Document is not available in temporary local storage for signing."
            ) from exc

        output_dir = os.path.join(str(settings.MEDIA_ROOT), settings.TEMP_SIGNED_SUBDIR)
        os.makedirs(output_dir, exist_ok=True)
        output_pdf_path = os.path.join(output_dir, f"{document.id}_signed_{envelope.id}.pdf")
        if os.path.abspath(output_pdf_path) == os.path.abspath(input_pdf_path):
            output_pdf_path = os.path.join(
                output_dir,
                f"{document.id}_signed_{envelope.id}_{signer.id}.pdf",
            )

        if not os.path.exists(input_pdf_path):
            document.signed_file_url = document.signed_file_url or None
            document.save(update_fields=["signed_file_url", "file_url", "updated_at"])
            continue

        try:
            embed_document_pdf_for_signer(
                envelope,
                signer,
                env_doc,
                input_pdf_path,
                output_pdf_path,
                signature_image_data,
                fallback_placement=fallback_placement,
            )
            relative_output = os.path.relpath(output_pdf_path, str(settings.MEDIA_ROOT))
            new_signed_url = f"{settings.MEDIA_URL}{relative_output}"
            document.signed_file_url = new_signed_url
            document.file_url = new_signed_url
        except Exception:
            document.signed_file_url = document.signed_file_url or None

        document.save(update_fields=["signed_file_url", "file_url", "updated_at"])


def mark_signature_signed(signature: Signature, signature_image_data: str) -> None:
    """Mark a signature record as signed and persist the image data."""
    signature.status = "signed"
    signature.signed_at = timezone.now()
    signature.signature_image = signature_image_data
    signature.save()


def complete_envelope(envelope: Envelope, *, notify_creator: bool = True) -> None:
    """
    Mark envelope and documents completed, optionally lock PDFs and upload to S3.

    Args:
        envelope: Envelope to complete.
        notify_creator: When True, send completion notification to the creator.
    """
    with transaction.atomic():
        locked_envelope = Envelope.objects.select_for_update().get(pk=envelope.id)

        generated_password = False
        if locked_envelope.pdf_password_protection_enabled and not locked_envelope.pdf_lock_password:
            locked_envelope.pdf_lock_password = generate_pdf_lock_password()
            generated_password = True

        locked_envelope.status = (
            "self_signed" if locked_envelope.is_self_sign else "completed"
        )
        envelope_update_fields = ["status", "updated_at", "pdf_password_protection_enabled"]
        if generated_password:
            envelope_update_fields.append("pdf_lock_password")
        locked_envelope.save(update_fields=envelope_update_fields)

    envelope.refresh_from_db()
    final_password = envelope.pdf_lock_password if envelope.pdf_password_protection_enabled else None

    for envelope_document in envelope.envelopedocument_set.select_related('document'):
        document = envelope_document.document
        document.status = "completed"

        locked_url = None
        source_url = document.signed_file_url or document.file_url
        upload_path = None
        temp_download = None
        if source_url:
            try:
                if source_url.startswith('/media/') or (
                    not source_url.startswith('http://') and not source_url.startswith('https://')
                ):
                    upload_path = get_media_absolute_path_from_url(source_url)
                else:
                    temp_download = download_pdf_to_temp(source_url)
                    upload_path = str(temp_download)
            except (ValueError, FileNotFoundError):
                upload_path = None

        if upload_path and os.path.exists(upload_path):
            if envelope.pdf_password_protection_enabled and final_password:
                locked_path = lock_pdf_with_password(
                    pdf_path=upload_path,
                    password=final_password,
                )
                if locked_path:
                    upload_path = locked_path
            try:
                locked_url = upload_completed_pdf(envelope.id, document.id, upload_path)
            except Exception:
                LOGGER.exception(
                    "Failed to upload completed PDF to S3 for document %s in envelope %s",
                    document.id,
                    envelope.id,
                )
        else:
            LOGGER.warning(
                "Unable to resolve path for document %s in envelope %s (url=%s)",
                document.id,
                envelope.id,
                source_url,
            )

        if temp_download is not None:
            try:
                os.remove(str(temp_download))
            except OSError:
                pass

        document_update_fields = ["status", "updated_at"]
        if locked_url:
            document.signed_file_url = locked_url
            document.file_url = locked_url
            document_update_fields.extend(["signed_file_url", "file_url"])
        else:
            document.signed_file_url = document.signed_file_url or None

        document.save(update_fields=document_update_fields)

    if notify_creator:
        from notifications.utils import create_envelope_completed_notification, create_notification

        message = create_envelope_completed_notification(envelope)
        create_notification(str(envelope.creator.id), message)
