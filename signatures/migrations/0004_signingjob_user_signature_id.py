from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('signatures', '0003_add_signing_job_and_processing_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='signingjob',
            name='user_signature_id',
            field=models.UUIDField(
                blank=True,
                help_text='Deferred UserSignature id when image is resolved in the worker.',
                null=True,
            ),
        ),
    ]
