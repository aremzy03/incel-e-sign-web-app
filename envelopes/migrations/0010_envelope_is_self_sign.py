# Generated manually for self-sign envelope feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('envelopes', '0009_envelope_pdf_password_protection_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='envelope',
            name='is_self_sign',
            field=models.BooleanField(
                default=False,
                help_text='True when the creator signed their own document(s) without sending to recipients.',
            ),
        ),
    ]
