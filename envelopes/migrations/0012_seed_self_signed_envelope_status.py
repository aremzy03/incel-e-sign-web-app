# Data migration to backfill self_signed status for existing self-sign envelopes.

from django.db import migrations


def seed_self_signed_envelope_status(apps, schema_editor):
    """Set self_signed on existing self-sign envelopes that were pending or completed."""
    Envelope = apps.get_model('envelopes', 'Envelope')
    Envelope.objects.filter(
        is_self_sign=True,
        status__in=['pending', 'completed'],
    ).update(status='self_signed')


def reverse_self_signed_envelope_status(apps, schema_editor):
    """Restore self_signed self-sign envelopes to completed on rollback."""
    Envelope = apps.get_model('envelopes', 'Envelope')
    Envelope.objects.filter(
        is_self_sign=True,
        status='self_signed',
    ).update(status='completed')


class Migration(migrations.Migration):

    dependencies = [
        ('envelopes', '0011_envelope_self_signed_status'),
    ]

    operations = [
        migrations.RunPython(
            seed_self_signed_envelope_status,
            reverse_self_signed_envelope_status,
        ),
    ]
