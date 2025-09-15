"""
Serializers for the documents app.

This module contains serializers for document upload and management
functionality in the e-signature workflow.
"""

import os
from rest_framework import serializers
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import Document


class DocumentUploadSerializer(serializers.Serializer):
    """
    Serializer for document upload functionality.
    
    Handles file validation, storage, and Document model creation.
    """
    
    file = serializers.FileField(
        help_text="PDF file to upload (max 20MB)"
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
        # Check file extension
        if not value.name.lower().endswith('.pdf'):
            raise serializers.ValidationError(
                "Only PDF files are allowed."
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
        
        # Generate unique filename to avoid conflicts
        file_extension = os.path.splitext(file.name)[1]
        unique_filename = f"{owner.id}_{file.name}"
        
        # Save file using Django storage
        file_path = default_storage.save(
            f"documents/{unique_filename}",
            ContentFile(file.read())
        )
        
        # Get file URL
        file_url = default_storage.url(file_path)
        
        # Create Document record
        document = Document.objects.create(
            owner=owner,
            file_url=file_url,
            file_name=file.name,
            file_size=file.size,
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
            'file_size',
            'status',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'file_name',
            'file_url',
            'file_size',
            'created_at',
            'updated_at'
        ]
