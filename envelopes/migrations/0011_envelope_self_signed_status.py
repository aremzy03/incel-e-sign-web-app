# Generated manually for self-signed envelope status

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('envelopes', '0010_envelope_is_self_sign'),
    ]

    operations = [
        migrations.AlterField(
            model_name='envelope',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('pending', 'Pending'),
                    ('completed', 'Completed'),
                    ('self_signed', 'Self Signed'),
                    ('rejected', 'Rejected'),
                ],
                default='draft',
                help_text='Current status of the envelope in the signing workflow.',
                max_length=20,
            ),
        ),
    ]
