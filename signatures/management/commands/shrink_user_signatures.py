"""
Shrink saved signature images stored before uploads were size-limited.

    python manage.py shrink_user_signatures            # report only
    python manage.py shrink_user_signatures --apply    # replace the oversized ones

Each oversized image is re-saved under a new name (stored files are never overwritten)
and the old file is deleted once the row points at the new one.
"""

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from signatures.models import UserSignature
from signatures.utils.signature_images import shrink_signature_png


class Command(BaseCommand):
    help = "Scale saved signature images down to the upload size limit."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Replace oversized images (default: report only).")

    def handle(self, *args, apply: bool = False, **options):
        checked = shrunk = saved_bytes = 0
        for signature in UserSignature.objects.exclude(image="").iterator():
            checked += 1
            try:
                with signature.image.open("rb") as handle:
                    original = handle.read()
            except Exception as exc:
                self.stderr.write(f"{signature.id}: can't read {signature.image.name}: {exc}")
                continue
            smaller = shrink_signature_png(original)
            if smaller is None or len(smaller) >= len(original):
                continue
            shrunk += 1
            saved_bytes += len(original) - len(smaller)
            self.stdout.write(f"{signature.id}: {len(original) // 1024} KB -> {len(smaller) // 1024} KB")
            if not apply:
                continue
            old_name = signature.image.name
            storage = signature.image.storage
            signature.image.save("signature.png", ContentFile(smaller), save=False)
            UserSignature.objects.filter(pk=signature.pk).update(image=signature.image.name)
            storage.delete(old_name)

        verb = "Shrank" if apply else "Would shrink"
        self.stdout.write(f"{verb} {shrunk} of {checked} signatures, saving {saved_bytes // 1024} KB.")
