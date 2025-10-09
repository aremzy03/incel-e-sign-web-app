# Generated migration to rename 'sent' status to 'pending'

from django.db import migrations


def rename_sent_to_pending(apps, schema_editor):
    """Rename existing 'sent' status to 'pending' status."""
    Envelope = apps.get_model('envelopes', 'Envelope')
    Envelope.objects.filter(status='sent').update(status='pending')


def rename_pending_to_sent(apps, schema_editor):
    """Reverse migration: rename 'pending' status back to 'sent'."""
    Envelope = apps.get_model('envelopes', 'Envelope')
    Envelope.objects.filter(status='pending').update(status='sent')


class Migration(migrations.Migration):

    dependencies = [
        ('envelopes', '0004_auto_20251007_0937'),
    ]

    operations = [
        migrations.RunPython(rename_sent_to_pending, rename_pending_to_sent),
    ]
