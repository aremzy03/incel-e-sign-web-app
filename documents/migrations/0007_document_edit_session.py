import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0006_widen_document_file_url_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentEditSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("base_file_url", models.CharField(max_length=2048)),
                ("ops", models.JSONField(default=list)),
                (
                    "page_meta",
                    models.JSONField(default=list, help_text="Page sizes captured when the session was opened."),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("committed", "Committed"), ("discarded", "Discarded")],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="edit_sessions",
                        to="documents.document",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_edit_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="DocumentRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("file_url", models.CharField(max_length=2048)),
                ("file_size", models.IntegerField()),
                ("source", models.CharField(max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revisions",
                        to="documents.document",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="revisions",
                        to="documents.documenteditsession",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="documenteditsession",
            index=models.Index(fields=["document", "status"], name="documents_d_documen_7c0a1e_idx"),
        ),
        migrations.AddIndex(
            model_name="documenteditsession",
            index=models.Index(fields=["document", "created_at"], name="documents_d_documen_a1b2c3_idx"),
        ),
        migrations.AddIndex(
            model_name="documentrevision",
            index=models.Index(fields=["document", "created_at"], name="documents_d_documen_d4e5f6_idx"),
        ),
    ]
