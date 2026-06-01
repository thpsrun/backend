from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import zipfile
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from notifications import kinds
from notifications.services import create_notification

from accounts.exporters import collect_exports
from accounts.models import UserDataExport

logger = logging.getLogger(__name__)

EXPORT_TTL = timedelta(days=7)
EXPORTS_DIR = "exports"


def _export_paths(
    export_id: str,
) -> tuple[Path, Path, str]:
    root = Path(settings.MEDIA_ROOT) / EXPORTS_DIR
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    tmp_path = root / f"{export_id}.zip.tmp"
    final_abs = root / f"{export_id}.zip"
    final_rel = f"{EXPORTS_DIR}/{export_id}.zip"
    return tmp_path, final_abs, final_rel


def _readme_text(
    user_id: int,
    generated_at: str,
) -> str:
    return (
        "thps.run data export\n"
        f"User ID: {user_id}\n"
        f"Generated: {generated_at}\n"
        "\n"
        "Hello! This archive contains a copy of your account data on thps.run.\n"
        "\n"
        "Files:\n"
        "  manifest.json                     Schema version, file list, sha256 sums.\n"
        "  json/account.json                 Your account record.\n"
        "  json/player.json                  Your Speedrun.com player profile.\n"
        "  json/runs.json                    Every run attached to your player profile.\n"
        "  json/run_history.json             Historical run/WR state changes.\n"
        "  json/guides.json                  Guides you have authored.\n"
        "  json/submissions.json             Runs you submitted that are pending or under review.\n"
        "  json/api_keys.json                Your API key metadata (no secrets).\n"
        "  json/api_activity_log.json        Per-request log of your API key usage.\n"
        "  json/notifications.json           Your in-app notifications.\n"
        "  json/notification_preferences.json Your notification toggles.\n"
        "  json/social_accounts.json         Linked OAuth providers (no tokens).\n"
        "  json/game_audit_events.json       Game-management audit events you initiated.\n"
        "  csv/<entity>.csv                  The same data in CSV form.\n"
        "\n"
        "Privacy:\n"
        "  This archive contains personal information including run history, API key\n"
        "  metadata, IP addresses logged against your API activity, and OAuth provider\n"
        "  IDs. Keep this file in a secure location and do not share it.\n"
        "\n"
        "Data Security Note:\n"
        "  This data was kept in a PostgreSQL database that was not directly connected to the\n"
        "  Internet. Account login information (e.g. Passkeys, OAuth, SRC API Keys, thps.run API\n"
        "  keys, etc.) were encrypted in transit and at rest. If you ever have questions, please\n"
        "  feel free to contact the thps.run administrators for more information."
        "Schema:\n"
        "  Refer to https://thps.run/api/v1/docs for information on how the API works.\n"
    )


def _write_json_array(
    zf: zipfile.ZipFile,
    arcname: str,
    rows: list[dict],
) -> tuple[str, int]:
    payload = json.dumps(rows, default=str, ensure_ascii=False, indent=2).encode(
        "utf-8"
    )
    zf.writestr(arcname, payload)
    return hashlib.sha256(payload).hexdigest(), len(rows)


def _write_csv(
    zf: zipfile.ZipFile,
    arcname: str,
    rows: list[dict],
) -> str:
    if not rows:
        payload = b""
    else:
        keys = list(rows[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: (
                        json.dumps(v, default=str) if isinstance(v, (dict, list)) else v
                    )
                    for k, v in row.items()
                }
            )
        payload = buf.getvalue().encode("utf-8")
    zf.writestr(arcname, payload)
    return hashlib.sha256(payload).hexdigest()


@shared_task(name="accounts.build_user_data_export", max_retries=0)
def build_user_data_export(
    export_id: str,
) -> dict[str, str]:
    row = UserDataExport.objects.select_related("user").get(pk=export_id)
    row.status = UserDataExport.Status.RUNNING
    row.completed_at = None
    row.error_message = ""
    row.save(update_fields=["status", "completed_at", "error_message"])

    tmp_path, final_abs, final_rel = _export_paths(export_id)
    generated_at = timezone.now()

    try:
        manifest_files: list[dict] = []
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, rows_iter in collect_exports(row.user):
                rows_list = list(rows_iter)
                json_arc = f"json/{name}.json"
                json_sha, row_count = _write_json_array(zf, json_arc, rows_list)
                manifest_files.append(
                    {
                        "path": json_arc,
                        "sha256": json_sha,
                        "row_count": row_count,
                    }
                )
                csv_arc = f"csv/{name}.csv"
                csv_sha = _write_csv(zf, csv_arc, rows_list)
                manifest_files.append(
                    {
                        "path": csv_arc,
                        "sha256": csv_sha,
                        "row_count": row_count,
                    }
                )

            manifest = {
                "schema_version": 1,
                "generated_at": generated_at.isoformat(),
                "user_id": row.user.id,
                "files": manifest_files,
            }
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2).encode("utf-8"),
            )
            zf.writestr(
                "README.txt",
                _readme_text(row.user.id, generated_at.isoformat()).encode("utf-8"),
            )

        os.replace(tmp_path, final_abs)
        file_size = final_abs.stat().st_size

        with transaction.atomic():
            prior_qs = (
                UserDataExport.objects.select_for_update()
                .filter(user=row.user, status=UserDataExport.Status.READY)
                .exclude(pk=row.pk)
            )
            for prior in prior_qs:
                if prior.file_path:
                    prior_path = Path(settings.MEDIA_ROOT) / prior.file_path
                    if prior_path.exists():
                        try:
                            prior_path.unlink()
                        except OSError:
                            logger.exception(
                                "Failed to remove prior export file %s",
                                prior_path,
                            )
                prior.status = UserDataExport.Status.EXPIRED
                prior.file_path = ""
                prior.file_size_bytes = None
                prior.save(update_fields=["status", "file_path", "file_size_bytes"])

            row.status = UserDataExport.Status.READY
            row.completed_at = generated_at
            row.expires_at = generated_at + EXPORT_TTL
            row.file_path = final_rel
            row.file_size_bytes = file_size
            row.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "expires_at",
                    "file_path",
                    "file_size_bytes",
                ]
            )

        create_notification(
            user=row.user,
            kind=kinds.USER_DATA_EXPORT_READY,
            title="Your data export is ready",
            body=(
                "Your account data export has finished. Visit your profile "
                "settings to download it."
            ),
            target_type="user_data_export",
            target_id=str(row.pk),
            payload={"export_id": str(row.pk)},
        )
        return {"status": row.status, "export_id": str(row.pk)}

    except Exception as exc:
        logger.exception("build_user_data_export failed for export_id=%s", export_id)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                logger.exception("Failed to remove tmp export file %s", tmp_path)
        row.refresh_from_db()
        row.status = UserDataExport.Status.FAILED
        row.completed_at = timezone.now()
        row.error_message = repr(exc)[:2000]
        row.save(update_fields=["status", "completed_at", "error_message"])

        create_notification(
            user=row.user,
            kind=kinds.USER_DATA_EXPORT_FAILED,
            title="Your data export failed",
            body="Something went wrong building your export. You can try again now.",
            target_type="user_data_export",
            target_id=str(row.pk),
            payload={"export_id": str(row.pk), "error": repr(exc)[:500]},
        )
        return {"status": row.status, "export_id": str(row.pk)}


@shared_task(name="accounts.purge_user_data_exports")
def purge_expired_user_data_exports() -> dict[str, int]:
    cutoff = timezone.now()
    expired_count = 0
    qs = UserDataExport.objects.filter(
        status=UserDataExport.Status.READY,
        expires_at__lt=cutoff,
    )
    for row in qs.iterator(chunk_size=200):
        if row.file_path:
            path = Path(settings.MEDIA_ROOT) / row.file_path
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    logger.exception("Failed to remove expired export file %s", path)
        row.status = UserDataExport.Status.EXPIRED
        row.file_path = ""
        row.file_size_bytes = None
        row.save(update_fields=["status", "file_path", "file_size_bytes"])
        expired_count += 1
    return {"expired": expired_count}
