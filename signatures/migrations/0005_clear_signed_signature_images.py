from django.db import migrations


# trim() is the portable form of btrim(): tests run on SQLite, production on Postgres.
CLEAR_SIGNED_SIGNATURE_IMAGES = """
UPDATE signatures_signature
SET signature_image = NULL
WHERE status = 'signed'
  AND signature_image IS NOT NULL
  AND trim(signature_image) <> ''
"""


class Migration(migrations.Migration):

    dependencies = [
        ('signatures', '0004_signingjob_user_signature_id'),
    ]

    operations = [
        migrations.RunSQL(CLEAR_SIGNED_SIGNATURE_IMAGES, migrations.RunSQL.noop),
    ]
