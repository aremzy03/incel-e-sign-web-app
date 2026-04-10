"""
Cleanup temporary PDF artifacts stored on the server.

This command removes files under MEDIA_ROOT temporary subdirectories that are
older than a configured retention period (default: 24 hours). It is intended
to be run periodically (e.g. via cron or Celery beat).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


@dataclass(frozen=True)
class _CleanupTarget:
    name: str
    path: Path


class Command(BaseCommand):
    help = "Delete temporary uploaded/signed PDFs older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Retention window in hours (default: 24). Files older than this are deleted.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        hours: int = options["hours"]
        dry_run: bool = options["dry_run"]

        if hours <= 0:
            self.stderr.write(self.style.ERROR("--hours must be a positive integer"))
            return

        now = time.time()
        cutoff_ts = now - (hours * 60 * 60)

        media_root = Path(str(settings.MEDIA_ROOT))
        targets = [
            _CleanupTarget(
                name="temp_uploads",
                path=media_root / str(getattr(settings, "TEMP_UPLOAD_SUBDIR", "temp_uploads")),
            ),
            _CleanupTarget(
                name="signed_docs",
                path=media_root / str(getattr(settings, "TEMP_SIGNED_SUBDIR", "signed_docs")),
            ),
        ]

        deleted_files = 0
        deleted_bytes = 0
        scanned_files = 0

        for target in targets:
            if not target.path.exists():
                continue
            if not target.path.is_dir():
                continue

            for root, _dirs, files in os.walk(target.path):
                for filename in files:
                    file_path = Path(root) / filename
                    try:
                        stat = file_path.stat()
                    except FileNotFoundError:
                        continue

                    scanned_files += 1
                    if stat.st_mtime > cutoff_ts:
                        continue

                    size = stat.st_size
                    if dry_run:
                        self.stdout.write(f"[dry-run] delete {file_path}")
                        continue

                    try:
                        file_path.unlink(missing_ok=True)
                        deleted_files += 1
                        deleted_bytes += size
                    except Exception as exc:
                        self.stderr.write(self.style.WARNING(f"Failed to delete {file_path}: {exc}"))

        msg = (
            f"Scanned {scanned_files} files. "
            f"{'Would delete' if dry_run else 'Deleted'} {deleted_files} files "
            f"({deleted_bytes} bytes) older than {hours}h."
        )
        self.stdout.write(self.style.SUCCESS(msg))

