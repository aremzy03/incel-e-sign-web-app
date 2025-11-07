from django.contrib import admin
from .models import Envelope, EnvelopeDocument


@admin.register(Envelope)
class EnvelopeAdmin(admin.ModelAdmin):
    """Admin interface for Envelope model."""
    
    list_display = [
        'id',
        'name',
        'description_preview',
        'creator',
        'status',
        'signer_count',
        'created_at',
        'updated_at'
    ]
    
    list_filter = [
        'status',
        'created_at',
        'updated_at'
    ]
    
    search_fields = [
        'name',
        'description',
        'creator__email',
        'creator__full_name',
        'id'
    ]
    
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'signer_count'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'description', 'creator', 'status')
        }),
        ('Signing Configuration', {
            'fields': ('signing_order', 'signer_count'),
            'description': 'Configure the order of signers for this envelope.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-created_at']
    
    def signer_count(self, obj):
        """Display the number of signers."""
        return obj.signer_count
    signer_count.short_description = 'Number of Signers'

    def description_preview(self, obj):
        """Show a truncated version of the description for list display."""
        if not obj.description:
            return ""
        return (obj.description[:75] + '...') if len(obj.description) > 75 else obj.description
    description_preview.short_description = 'Description'


@admin.register(EnvelopeDocument)
class EnvelopeDocumentAdmin(admin.ModelAdmin):
    """Admin interface for EnvelopeDocument model."""
    list_display = [
        'id',
        'envelope',
        'document',
        'order',
        'signer_document_positions'
    ]
    list_filter = [
        'envelope',
        'document',
        'order'
    ]
    search_fields = [
        'envelope__name',
        'document__file_name',
        'id'
    ]
    readonly_fields = [
        'id'
    ]
    ordering = ['envelope', 'order']