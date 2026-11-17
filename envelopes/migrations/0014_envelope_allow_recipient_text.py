from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("envelopes", "0013_signingtoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="envelope",
            name="allow_recipient_text",
            field=models.BooleanField(
                default=False,
                help_text="When true, the current signer may add text onto the PDF before signing.",
            ),
        ),
    ]
