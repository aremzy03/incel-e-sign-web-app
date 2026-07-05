"""
Management command to audit pending envelopes before signing architecture cutover.
"""

from django.core.management.base import BaseCommand
from django.conf import settings

from envelopes.models import Envelope


class Command(BaseCommand):
    help = "List pending envelopes and verify readiness for SIGNING_CUTOVER_AT deploy."

    def handle(self, *args, **options):
        pending = Envelope.objects.filter(status="pending").order_by("created_at")
        count = pending.count()
        cutover = getattr(settings, "SIGNING_CUTOVER_AT", None)

        self.stdout.write(f"SIGNING_CUTOVER_AT: {cutover or '(not set)'}")
        self.stdout.write(f"Pending envelopes: {count}")

        if count == 0:
            self.stdout.write(self.style.SUCCESS("Ready for cutover (zero pending)."))
            return

        self.stdout.write(self.style.WARNING("Pending envelopes must be completed before deploy:"))
        for envelope in pending[:50]:
            self.stdout.write(
                f"  - {envelope.id} | {envelope.name!r} | creator={envelope.creator_id} | updated={envelope.updated_at}"
            )
        if count > 50:
            self.stdout.write(f"  ... and {count - 50} more")
