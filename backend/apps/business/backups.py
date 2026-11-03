"""
Backups: one folder per backup under BACKUP_DIR (default <project>/backups), holding the
database (db.sqlite3 or a pg_dump file), product images (media.zip) and a manifest.

SQLite is copied with SQLite's own backup API, so a sale being written at the same moment
cannot corrupt the copy. PostgreSQL uses pg_dump / pg_restore, which must be installed.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

MANIFEST = "manifest.json"


class BackupError(Exception):
    pass


def backup_dir():
    path = Path(getattr(settings, "BACKUP_DIR", settings.PROJECT_DIR / "backups"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _engine():
    return "sqlite" if connection.vendor == "sqlite" else "postgresql"


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise BackupError("DATABASE_URL is not set, so pg_dump cannot find the database.")
    return url


def _run(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise BackupError(f"{cmd[0]} was not found. Install the PostgreSQL client tools and add them to PATH.")
    if result.returncode != 0:
        raise BackupError(f"{cmd[0]} failed: {result.stderr.strip()[:500]}")


def create_backup(label="manual", keep=None):
    """Write a new backup and prune old ones. Returns the backup folder."""
    stamp = timezone.localtime().strftime("%Y-%m-%d_%H%M%S")
    target = backup_dir() / f"{stamp}_{label}"
    n = 1
    while target.exists():
        n += 1
        target = backup_dir() / f"{stamp}-{n}_{label}"
    target.mkdir()
    try:
        if _engine() == "sqlite":
            connection.ensure_connection()
            dest = sqlite3.connect(target / "db.sqlite3")
            with dest:
                connection.connection.backup(dest)
            dest.close()
        else:
            _run(["pg_dump", f"--dbname={_database_url()}", "--format=custom", f"--file={target / 'db.dump'}"])
        media = Path(settings.MEDIA_ROOT)
        if media.exists() and any(media.iterdir()):
            shutil.make_archive(str(target / "media"), "zip", media)
        from apps.sales.models import Sale

        manifest = {
            "created_at": timezone.now().isoformat(),
            "label": label,
            "engine": _engine(),
            "sales": Sale.objects.count(),
            "last_invoice": Sale.objects.order_by("-pk").values_list("invoice_number", flat=True).first(),
        }
        (target / MANIFEST).write_text(json.dumps(manifest, indent=2))
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    prune(keep if keep is not None else getattr(settings, "BACKUP_KEEP", 30))
    return target


def list_backups():
    items = []
    for folder in sorted(backup_dir().iterdir(), reverse=True):
        manifest_file = folder / MANIFEST
        if not folder.is_dir() or not manifest_file.exists():
            continue
        try:
            manifest = json.loads(manifest_file.read_text())
        except ValueError:
            continue
        size = sum(f.stat().st_size for f in folder.iterdir() if f.is_file())
        items.append({"name": folder.name, "size_bytes": size, **manifest})
    return items


def prune(keep):
    """Keep the newest `keep` backups (0 keeps everything)."""
    if not keep:
        return []
    removed = []
    for item in list_backups()[keep:]:
        shutil.rmtree(backup_dir() / item["name"], ignore_errors=True)
        removed.append(item["name"])
    return removed


def last_backup_time():
    items = list_backups()
    return datetime.fromisoformat(items[0]["created_at"]) if items else None


def restore_backup(name):
    """
    Replace the current data with a backup. A safety backup of the current data is taken
    first. Stop the POS server before calling this.
    """
    source = backup_dir() / name
    manifest_file = source / MANIFEST
    if "/" in name or "\\" in name or not manifest_file.exists():
        raise BackupError(f"No backup called {name}.")
    manifest = json.loads(manifest_file.read_text())
    if manifest["engine"] != _engine():
        raise BackupError(f"That backup is from a {manifest['engine']} database; this POS uses {_engine()}.")
    safety = create_backup(label="before-restore", keep=0)
    if _engine() == "sqlite":
        connection.ensure_connection()
        src = sqlite3.connect(source / "db.sqlite3")
        src.backup(connection.connection)
        src.close()
    else:
        _run(["pg_restore", "--clean", "--if-exists", "--no-owner", f"--dbname={_database_url()}",
              str(source / "db.dump")])
    media_zip = source / "media.zip"
    if media_zip.exists():
        with zipfile.ZipFile(media_zip) as zf:
            zf.extractall(settings.MEDIA_ROOT)
    return safety
