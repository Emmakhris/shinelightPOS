import json

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.business import backups
from apps.sales.models import Sale
from conftest import api_for

# Restoring writes into the live SQLite connection, so these tests run outside the usual
# per-test transaction.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def backup_dir(settings, tmp_path):
    settings.BACKUP_DIR = tmp_path / "backups"
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.BACKUP_DIR


def sell(api, variant, qty=1):
    r = api.post("/api/sales/checkout/", {"lines": [{"variant": variant.pk, "quantity": qty}],
                                          "payments": [{"method": "cash", "amount": "100"}]}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def test_backup_and_restore_round_trip(backup_dir, cashier_api, cashier_shift, soda):
    first = sell(cashier_api, soda)
    (backup_dir.parent / "media" / "products").mkdir(parents=True)
    (backup_dir.parent / "media" / "products" / "soda.png").write_bytes(b"png")

    folder = backups.create_backup(label="test")
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["sales"] == 1 and manifest["last_invoice"] == first["invoice_number"]
    assert (folder / "db.sqlite3").exists() and (folder / "media.zip").exists()

    sell(cashier_api, soda, 2)  # made after the backup
    (backup_dir.parent / "media" / "products" / "soda.png").unlink()
    assert Sale.objects.count() == 2

    safety = backups.restore_backup(folder.name)
    assert Sale.objects.count() == 1
    assert Sale.objects.get().invoice_number == first["invoice_number"]
    assert (backup_dir.parent / "media" / "products" / "soda.png").read_bytes() == b"png"
    # The data from just before the restore was kept, so the restore can be undone.
    assert json.loads((safety / "manifest.json").read_text())["sales"] == 2


def test_prune_keeps_newest(backup_dir, business):
    names = [backups.create_backup(label=f"b{i}", keep=0).name for i in range(4)]
    assert len(backups.list_backups()) == 4
    removed = backups.prune(2)
    assert sorted(removed) == sorted(names[:2])
    assert [b["name"] for b in backups.list_backups()] == list(reversed(names[2:]))


def test_restore_rejects_unknown_names(backup_dir, business):
    for bad in ["nope", "../etc", "..\\x"]:
        with pytest.raises(backups.BackupError):
            backups.restore_backup(bad)


def test_management_commands(backup_dir, business, capsys):
    call_command("backup", "--label", "daily", "--keep", "5")
    assert "Backup written" in capsys.readouterr().out
    name = backups.list_backups()[0]["name"]
    assert name.endswith("_daily")
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("restore_backup", name)  # needs --yes
    call_command("restore_backup")  # lists
    assert name in capsys.readouterr().out


def test_backups_api_and_dashboard_warning(backup_dir, owner, cashier):
    owner_api, cashier_api = api_for(owner), api_for(cashier)
    assert cashier_api.get("/api/backups/").status_code == 403
    assert owner_api.get("/api/reports/dashboard/").data["last_backup_at"] is None
    assert owner_api.post("/api/backups/").status_code == 201
    listed = owner_api.get("/api/backups/").data
    assert len(listed) == 1 and listed[0]["label"] == "manual"
    assert owner_api.get("/api/reports/dashboard/").data["last_backup_at"] is not None


def test_health(business):
    r = APIClient().get("/api/health/")
    assert r.status_code == 200 and r.json()["ok"] is True
