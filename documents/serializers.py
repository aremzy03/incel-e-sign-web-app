"""
Serializers for the documents app.

This module contains serializers for document upload and management
functionality in the e-signature workflow.
"""

import os
from rest_framework import serializers
from django.conf import settings
from django.core.files.base import ContentFile
from .models import Document
from .services.pdf_files import upload_staging_pdf, temp_pdf_file


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
            # Save the uploaded Word file to a temporary location on disk
            from .utils import convert_word_to_pdf
            
            tmp_dir = os.path.join(str(settings.MEDIA_ROOT), 'tmp_uploads')
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_input_abs = os.path.join(tmp_dir, f"{owner.id}_{original_name}")
            
            # Write uploaded bytes to temp path
            with open(tmp_input_abs, 'wb') as tmp_fp:
                for chunk in file.chunks():
                    tmp_fp.write(chunk)
            
            # Convert to PDF using LibreOffice
            pdf_output_dir = os.path.join(str(settings.MEDIA_ROOT), 'tmp_converted')
            try:
                output_pdf_abs = convert_word_to_pdf(tmp_input_abs, pdf_output_dir)
            except RuntimeError as exc:
                raise serializers.ValidationError({
                    'file': [
                        'Word-to-PDF conversion failed. Ensure LibreOffice is installed on the server and `soffice` is on PATH.',
                        str(exc)
                    ]
                })
            
            # Read back converted PDF bytes
            with open(output_pdf_abs, 'rb') as fpdf:
                pdf_bytes = fpdf.read()
            
            file_name_for_record = f"{base_name}.pdf"
            file_size_for_record = len(pdf_bytes)
        else:
            pdf_bytes = b"".join(chunk for chunk in file.chunks())
            file_name_for_record = original_name
            file_size_for_record = len(pdf_bytes)

        document = Document.objects.create(
            owner=owner,
            file_url="",
            file_name=file_name_for_record,
            file_size=file_size_for_record,
            status='draft',
        )

        with temp_pdf_file() as temp_path:
            temp_path.write_bytes(pdf_bytes)
            file_url = upload_staging_pdf(document.id, temp_path)

        document.file_url = file_url
        document.save(update_fields=["file_url", "updated_at"])
        return document


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
        return obj.signed_file_url or obj.file_url
    
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
