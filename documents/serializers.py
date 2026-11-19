"""
Serializers for the documents app.

This module contains serializers for document upload and management
functionality in the e-signature workflow.
"""

import os
from rest_framework import serializers
from django.conf import settings
from .models import Document
from .services.document_creation import create_draft_document_from_pdf_bytes
from .storage import refresh_remote_file_url


class MergeDocumentsSerializer(serializers.Serializer):
    """
    Serializer for validating merge request payload.
    """

    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="Ordered list of Document UUIDs to merge"
    )
    name = serializers.CharField(required=False, allow_blank=True)

    def validate_document_ids(self, value):
        # Require at least 2 documents to merge
        if len(value) < 2:
            raise serializers.ValidationError("At least two documents are required to merge.")
        max_docs = getattr(settings, "MAX_MERGE_DOCUMENTS", 10)
        if len(value) > max_docs:
            raise serializers.ValidationError(
                f"Cannot merge more than {max_docs} documents at once."
            )
        return value

def check_pdf_bytes(data: bytes) -> None:
    """
    Reject files that would only fail later, when someone tries to sign them: not a PDF,
    damaged, empty, or locked with an open password.
    """
    import fitz

    if b"%PDF-" not in data[:1024]:
        raise serializers.ValidationError("This file isn't a valid PDF.")
    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise serializers.ValidationError(
                    "This PDF is password-protected. Remove the password and upload it again."
                )
            if pdf.page_count == 0:
                raise serializers.ValidationError("This PDF has no pages.")
    except serializers.ValidationError:
        raise
    except Exception:
        raise serializers.ValidationError("This PDF is damaged and can't be opened.")


class DocumentUploadSerializer(serializers.Serializer):
    """
    Serializer for document upload functionality.
    
    Handles file validation, storage, and Document model creation.
    """
    
    file = serializers.FileField(
        help_text="PDF or Word file to upload (max 20MB)"
    )
    
    def validate_file(self, value):
        """
        Validate uploaded file.
        
        Args:
            value: The uploaded file object
            
        Returns:
            The validated file object
            
        Raises:
            serializers.ValidationError: If file validation fails
        """
        # Check file extension (allow .pdf, .doc, .docx)
        lower_name = value.name.lower()
        allowed_exts = ('.pdf', '.doc', '.docx')
        if not lower_name.endswith(allowed_exts):
            raise serializers.ValidationError(
                "Only PDF or Word files (.doc, .docx) are allowed."
            )
        
        # Check file size (20MB = 20 * 1024 * 1024 bytes)
        max_size = 20 * 1024 * 1024  # 20MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size must not exceed 20MB. Current size: {value.size / (1024 * 1024):.2f}MB"
            )

        if lower_name.endswith('.pdf'):
            data = b"".join(value.chunks())
            value.seek(0)
            check_pdf_bytes(data)

        return value
    
    def save(self, owner):
        """
        Save the uploaded file and create Document record.
        
        Args:
            owner: The user who owns the document
            
        Returns:
            Document: The created Document instance
        """
        file = self.validated_data['file']
        
        # Determine handling by extension
        original_name = file.name
        base_name, ext = os.path.splitext(original_name)
        ext = ext.lower()
        
        if ext in ('.doc', '.docx'):
            import shutil
            import tempfile

            from .utils import convert_word_to_pdf

            # A private directory per upload: two users uploading "Contract.docx" at once must
            # not overwrite each other's file, and nothing is left behind afterwards.
            work_dir = tempfile.mkdtemp(prefix="esign_word_")
            try:
                tmp_input_abs = os.path.join(work_dir, f"source{ext}")
                with open(tmp_input_abs, 'wb') as tmp_fp:
                    for chunk in file.chunks():
                        tmp_fp.write(chunk)

                try:
                    output_pdf_abs = convert_word_to_pdf(tmp_input_abs, os.path.join(work_dir, 'out'))
                except RuntimeError as exc:
                    raise serializers.ValidationError({
                        'file': [
                            'Word-to-PDF conversion failed. Ensure LibreOffice is installed on the server and `soffice` is on PATH.',
                            str(exc)
                        ]
                    })

                with open(output_pdf_abs, 'rb') as fpdf:
                    pdf_bytes = fpdf.read()
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)
            
            file_name_for_record = f"{base_name}.pdf"
            file_size_for_record = len(pdf_bytes)
        else:
            pdf_bytes = b"".join(chunk for chunk in file.chunks())
            file_name_for_record = original_name
            file_size_for_record = len(pdf_bytes)

        return create_draft_document_from_pdf_bytes(
            owner=owner,
            file_name=file_name_for_record,
            pdf_bytes=pdf_bytes,
        )


class DocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for Document model.
    
    Used for returning document details after upload or retrieval.
    """
    
    # Add a computed field that returns the current document URL (prioritizing signed version)
    current_file_url = serializers.SerializerMethodField()
    
    def get_current_file_url(self, obj):
        """
        Return the current document URL, prioritizing signed version if available.
        This matches the logic used in signing and download views.
        """
        return refresh_remote_file_url(obj.signed_file_url or obj.file_url)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(settings, "USE_S3", False):
            if data.get("file_url"):
                data["file_url"] = refresh_remote_file_url(data["file_url"])
            if data.get("signed_file_url"):
                data["signed_file_url"] = refresh_remote_file_url(data["signed_file_url"])
        return data

    class Meta:
        model = Document
        fields = [
            'id',
            'file_name',
            'file_url',
            'signed_file_url',
            'current_file_url',  # New computed field
            'file_size',
            'status',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'file_name',
            'file_url',
            'signed_file_url',
            'current_file_url',
            'file_size',
            'created_at',
            'updated_at'
        ]
