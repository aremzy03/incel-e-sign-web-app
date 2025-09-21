"""
Admin configuration for the documents app.

This module registers the Document model with Django admin interface
for easy management and monitoring of documents.
"""

from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """
    Admin interface for Document model.
    
    Provides a user-friendly interface for managing documents
    with filtering, searching, and display customization.
    """
    
    list_display = [
        'file_name',
        'owner',
        'status',
        'file_size_mb',
        'created_at',
        'updated_at'
    ]
    
    list_filter = [
        'status',
        'created_at',
        'updated_at',
        'owner'
    ]
    
    search_fields = [
        'file_name',
        'owner__email',
        'owner__full_name'
    ]
    
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'file_size_mb'
    ]
    
    fieldsets = (
        ('Document Information', {
            'fields': ('id', 'file_name', 'file_url', 'file_size', 'file_size_mb')
        }),
        ('Ownership & Status', {
            'fields': ('owner', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-created_at']
    
    def file_size_mb(self, obj):
        """Display file size in megabytes."""
        return f"{obj.file_size_mb} MB"
    file_size_mb.short_description = 'File Size (MB)'