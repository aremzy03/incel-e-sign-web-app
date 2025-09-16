from django.contrib import admin
from .models import Envelope


@admin.register(Envelope)
class EnvelopeAdmin(admin.ModelAdmin):
    """Admin interface for Envelope model."""
    
    list_display = [
        'id',
        'document',
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
        'document__file_name',
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
            'fields': ('id', 'document', 'creator', 'status')
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