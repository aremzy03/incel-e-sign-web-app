from django.db import migrations, models
import uuid
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('envelopes', '0001_initial'),
        ('documents', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Field',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('page', models.IntegerField(help_text='1-based page number.')),
                ('x', models.FloatField(help_text='X coordinate in points from left edge.')),
                ('y', models.FloatField(help_text='Y coordinate in points from top edge (UI convention).')),
                ('width', models.FloatField(help_text='Width in points.')),
                ('height', models.FloatField(help_text='Height in points.')),
                ('type', models.CharField(max_length=20, choices=[('signature','Signature'),('initials','Initials'),('date','Date'),('text','Text'),('designation','Designation')]))
                ,
                ('required', models.BooleanField(default=False, help_text='Whether the field must be filled by the signer.')),
                ('prefill_value', models.TextField(null=True, blank=True, help_text='Value prefilled by the sender.')),
                ('value', models.TextField(null=True, blank=True, help_text='Value provided by the signer during signing.')),
                ('placeholder', models.CharField(max_length=255, null=True, blank=True)),
                ('font_family', models.CharField(max_length=255, null=True, blank=True, help_text='ReportLab font name or path to TTF.')),
                ('font_size', models.FloatField(null=True, blank=True)),
                ('date_format', models.CharField(max_length=32, null=True, blank=True, help_text='Display format for date fields.')),
                ('max_length', models.IntegerField(null=True, blank=True, help_text='Max length for text/designation.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_signer', models.ForeignKey(null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_fields', to=settings.AUTH_USER_MODEL, help_text='Signer assigned to fill this field.')),
                ('document', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='fields', to='documents.document', help_text='Document this field is placed on.')),
                ('envelope', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='fields', to='envelopes.envelope', help_text='Envelope this field belongs to.')),
            ],
            options={
                'ordering': ['created_at']
            }
        ),
        migrations.AddIndex(
            model_name='field',
            index=models.Index(fields=['envelope','document'], name='field_env_doc_idx'),
        ),
        migrations.AddIndex(
            model_name='field',
            index=models.Index(fields=['document','page'], name='field_doc_page_idx'),
        ),
        migrations.AddIndex(
            model_name='field',
            index=models.Index(fields=['assigned_signer'], name='field_assigned_signer_idx'),
        ),
    ]


