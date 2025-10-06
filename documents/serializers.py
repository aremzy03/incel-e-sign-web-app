"""
Serializers for the documents app.

This module contains serializers for document upload and management
functionality in the e-signature workflow.
"""

import os
from rest_framework import serializers
from django.core.files.storage import default_storage
from django.conf import settings
from .models import Document


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
            from django.core.files.base import ContentFile
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
            
            # Generate unique PDF filename for storage (with UUID prefix for uniqueness on disk)
            unique_pdf_filename = f"{owner.id}_{os.path.basename(base_name)}.pdf"
            storage_rel_path = f"documents/{unique_pdf_filename}"
            
            # Save PDF into default storage
            saved_path = default_storage.save(storage_rel_path, ContentFile(pdf_bytes))
            file_url = f"{settings.MEDIA_URL}{saved_path}"
            # Store clean filename without UUID prefix for display
            file_name_for_record = f"{base_name}.pdf"
            file_size_for_record = len(pdf_bytes)
        else:
            # Handle PDF directly: store as-is
            unique_filename = f"{owner.id}_{original_name}"
            file_path = default_storage.save(
                f"documents/{unique_filename}",
                file
            )
            file_url = f"{settings.MEDIA_URL}{file_path}"
            file_name_for_record = original_name
            file_size_for_record = file.size
        
        document = Document.objects.create(
            owner=owner,
            file_url=file_url,
            file_name=file_name_for_record,
            file_size=file_size_for_record,
            status='draft'
        )
        return document


class DocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for Document model.
    
    Used for returning document details after upload or retrieval.
    """
    
    class Meta:
        model = Document
        fields = [
            'id',
            'file_name',
            'file_url',
            'signed_file_url',
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
            'file_size',
            'created_at',
            'updated_at'
        ]
