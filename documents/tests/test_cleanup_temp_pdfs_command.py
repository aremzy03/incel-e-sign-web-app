import os
import time

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_cleanup_temp_pdfs_deletes_only_old_files(settings, tmp_path, capsys):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    settings.TEMP_UPLOAD_SUBDIR = "temp_uploads"
    settings.TEMP_SIGNED_SUBDIR = "signed_docs"

    uploads_dir = tmp_path / "temp_uploads"
    signed_dir = tmp_path / "signed_docs"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    signed_dir.mkdir(parents=True, exist_ok=True)

    old_file = uploads_dir / "old.pdf"
    new_file = signed_dir / "new.pdf"
    old_file.write_bytes(b"old")
    new_file.write_bytes(b"new")

    now = time.time()
    two_days_ago = now - (48 * 60 * 60)
    os.utime(old_file, (two_days_ago, two_days_ago))

    call_command("cleanup_temp_pdfs", hours=24)
    out = capsys.readouterr().out
    assert "Deleted" in out

    assert not old_file.exists()
    assert new_file.exists()


@pytest.mark.django_db
def test_cleanup_temp_pdfs_dry_run_does_not_delete(settings, tmp_path, capsys):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    settings.TEMP_UPLOAD_SUBDIR = "temp_uploads"
    settings.TEMP_SIGNED_SUBDIR = "signed_docs"

    uploads_dir = tmp_path / "temp_uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    old_file = uploads_dir / "old.pdf"
    old_file.write_bytes(b"old")
    two_days_ago = time.time() - (48 * 60 * 60)
    os.utime(old_file, (two_days_ago, two_days_ago))

    call_command("cleanup_temp_pdfs", hours=24, dry_run=True)
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert old_file.exists()

