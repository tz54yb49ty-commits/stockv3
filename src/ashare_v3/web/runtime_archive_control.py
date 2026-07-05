"""N6-facing controls for safe runtime archive preview and job registration."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import secrets
from typing import Any
from zoneinfo import ZoneInfo

from ashare_v3.ingestion.runtime_archive import (
    DEFAULT_RUNTIME_ARCHIVE_ROOT,
    inspect_archive_storage,
    runtime_archive_side_effects,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_RETENTION_TRADE_DAYS = 5
CONFIRM_TOKEN = "ARCHIVE_KEEP_5"
TRADE_DATE_RE = re.compile(r"^\d{8}$")


def build_runtime_archive_preview(
    *,
    docs_root: str | Path,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    retention_trade_days: int = DEFAULT_RETENTION_TRADE_DAYS,
) -> dict[str, Any]:
    root = Path(docs_root)
    retention = normalize_retention_trade_days(retention_trade_days)
    trade_dates = discover_runtime_trade_dates(root)
    retained = trade_dates[-retention:]
    eligible = trade_dates[:-retention]
    storage = inspect_archive_storage(archive_root)
    blockers = archive_preview_blockers(storage=storage, eligible_trade_dates=eligible)
    return {
        "ok": True,
        "component": "Runtime Archive Control",
        "mode": "preview",
        "archive_root": str(archive_root),
        "docs_root": str(root),
        "retention_trade_days": retention,
        "retention_policy": "latest_trade_dates",
        "trade_dates": trade_dates,
        "retained_trade_dates": retained,
        "eligible_trade_dates": eligible,
        "eligible_count": len(eligible),
        "storage": storage,
        "blockers": blockers,
        "execute_ready": not blockers and bool(eligible),
        "cleanup_policy": {
            "cleanup_local_runtime": "after_archive_manifest_verified_only",
            "cleanup_authorized_by_preview": False,
            "recent_trade_dates_never_cleanup": retained,
        },
        "per_trade_date": [trade_date_preview(root, trade_date, trade_date in retained) for trade_date in trade_dates],
        "side_effects": runtime_archive_side_effects(),
    }


def create_runtime_archive_job_request(
    *,
    docs_root: str | Path,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    confirm_token: str,
    retention_trade_days: int = DEFAULT_RETENTION_TRADE_DAYS,
) -> dict[str, Any]:
    if str(confirm_token or "").strip() != CONFIRM_TOKEN:
        return {
            "ok": False,
            "error": "BLOCKED_ARCHIVE_CONFIRMATION_REQUIRED",
            "required_confirm_token": CONFIRM_TOKEN,
            "side_effects": runtime_archive_side_effects(),
        }

    preview = build_runtime_archive_preview(
        docs_root=docs_root,
        archive_root=archive_root,
        retention_trade_days=retention_trade_days,
    )
    if not preview["execute_ready"]:
        return {
            "ok": False,
            "error": "BLOCKED_ARCHIVE_PREVIEW_NOT_READY",
            "preview": preview,
            "side_effects": runtime_archive_side_effects(),
        }

    created_at = datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()
    job_id = f"runtime_archive_keep5_{created_at.replace('-', '').replace(':', '').replace('+', '_')}_{secrets.token_hex(4)}"
    bounded_commands = [
        [
            "python3",
            "scripts/run_v3_runtime_archive_once.py",
            "--trade-date",
            trade_date,
            "--archive-root",
            str(archive_root),
            "--execute",
            "--user-confirmed",
        ]
        for trade_date in preview["eligible_trade_dates"]
    ]
    payload = {
        "ok": True,
        "job_id": job_id,
        "job_status": "WAIT_RUNTIME_CONTROL_EXECUTE",
        "created_at": created_at,
        "confirm_token": CONFIRM_TOKEN,
        "archive_root": str(archive_root),
        "docs_root": str(docs_root),
        "retention_trade_days": preview["retention_trade_days"],
        "retained_trade_dates": preview["retained_trade_dates"],
        "eligible_trade_dates": preview["eligible_trade_dates"],
        "bounded_commands": bounded_commands,
        "cleanup_authorized": False,
        "cleanup_policy": preview["cleanup_policy"],
        "preview": preview,
        "side_effects": runtime_archive_side_effects(),
    }
    job_path = Path(docs_root) / "jobs" / f"{job_id}.json"
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["job_path"] = str(job_path)
    return payload


def discover_runtime_trade_dates(docs_root: Path) -> list[str]:
    artifact_root = docs_root.parent if docs_root.name == "runtime_archive" else docs_root
    roots = (
        docs_root,
        artifact_root / "runtime",
        artifact_root / "intraday_live_current",
        artifact_root / "post_close_fastlane",
    )
    trade_dates: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.is_dir() and TRADE_DATE_RE.fullmatch(path.name):
                trade_dates.add(path.name)
    return sorted(trade_dates)


def normalize_retention_trade_days(value: int) -> int:
    retention = int(value or DEFAULT_RETENTION_TRADE_DAYS)
    return max(1, min(retention, 30))


def archive_preview_blockers(*, storage: dict[str, Any], eligible_trade_dates: list[str]) -> list[str]:
    blockers: list[str] = []
    if not bool(storage.get("mounted")):
        blockers.append("macraid_not_mounted")
    if not bool(storage.get("writable")):
        blockers.append("macraid_not_writable")
    if not bool(storage.get("free_space_ok", True)):
        blockers.append("macraid_free_space_below_threshold")
    if not eligible_trade_dates:
        blockers.append("no_trade_dates_older_than_retention_window")
    return blockers


def trade_date_preview(docs_root: Path, trade_date: str, retained: bool) -> dict[str, Any]:
    artifact_root = docs_root.parent if docs_root.name == "runtime_archive" else docs_root
    paths = {
        "runtime_archive_status": docs_root / trade_date / "archive_status.json",
        "runtime_docs": artifact_root / "runtime" / trade_date,
        "intraday_live_current": artifact_root / "intraday_live_current" / trade_date,
        "post_close_fastlane": artifact_root / "post_close_fastlane" / trade_date,
    }
    return {
        "trade_date": trade_date,
        "retained_hot": retained,
        "archive_eligible": not retained,
        "paths": {key: str(path) for key, path in paths.items()},
        "path_exists": {key: path.exists() for key, path in paths.items()},
    }
