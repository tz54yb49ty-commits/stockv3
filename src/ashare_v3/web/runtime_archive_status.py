"""Read-only helpers for the N3-N6 runtime archive status page."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ashare_v3.ingestion.runtime_archive import (
    DEFAULT_RUNTIME_ARCHIVE_ROOT,
    inspect_archive_storage,
    runtime_archive_side_effects,
)


def read_runtime_archive_status(
    *,
    docs_root: Path | str,
    archive_root: Path | str = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    trade_date: str | None = None,
) -> dict[str, Any]:
    root = Path(docs_root)
    selected_trade_date = normalize_trade_date(trade_date) or latest_trade_date(root)
    run_dir = root / selected_trade_date if selected_trade_date else root / "__missing__"
    status_path = run_dir / "archive_status.json"
    contract_path = run_dir / "archive_contract.json"
    preflight_path = run_dir / "archive_preflight.json"
    manifest_path = Path(archive_root) / f"trade_date={selected_trade_date}" / "manifests" / "archive_manifest.json"
    report_path = Path(archive_root) / f"trade_date={selected_trade_date}" / "reports" / "archive_report.json"

    status = load_json_object(status_path)
    manifest = load_json_object(manifest_path)
    if status is None:
        storage = inspect_archive_storage(archive_root)
        status = {
            "result": "NO_STATUS",
            "trade_date": selected_trade_date,
            "archive_root": str(archive_root),
            "hot_retention_days": 5,
            "storage": storage,
            "plan": {
                "status": "HOT_ONLY",
                "files": [],
                "manifest_path": str(manifest_path),
                "blockers": ["archive_status_artifact_missing"],
                "cleanup_eligible": False,
                "cleanup_blockers": ["archive_status_artifact_missing", "manual_cleanup_required"],
            },
            "side_effects": runtime_archive_side_effects(),
        }
    archive_execute_result = str(status.get("result") or "NO_STATUS")
    archive_state = str((manifest or {}).get("result") or status.get("archive_result") or status.get("registered_status") or archive_execute_result)
    plan = archive_plan_from_manifest(manifest) if manifest else dict(status.get("plan") or {})
    if status.get("cleanup_executed"):
        plan["cleanup_eligible"] = False
        plan["cleanup_blockers"] = list(status.get("cleanup_blockers") or [])
        plan["cleanup_state"] = str(status.get("local_cleanup_state") or "LOCAL_CLEANED")
    artifact_docs_root = root.parent if root.name == "runtime_archive" else root
    keep5_hot_cleanup_path = root / "hot_keep5_cleanup" / "keep5_cleanup_status.json"
    legacy_hot_cleanup_path = root / "dirty_hot_cleanup" / "keep2_cleanup_status.json"
    hot_cleanup = load_json_object(keep5_hot_cleanup_path)
    hot_cleanup_source_path = keep5_hot_cleanup_path
    if hot_cleanup is None:
        hot_cleanup = load_json_object(legacy_hot_cleanup_path) or {}
        hot_cleanup_source_path = legacy_hot_cleanup_path

    return {
        "result": archive_state,
        "archive_state": archive_state,
        "archive_execute_result": archive_execute_result,
        "row_count_match": bool((manifest or {}).get("row_count_match", False)),
        "checksum_algorithm": str((manifest or {}).get("checksum_algorithm") or ""),
        "cleanup_executed": bool(status.get("cleanup_executed") or (manifest or {}).get("cleanup_executed")),
        "local_cleanup_state": str(status.get("local_cleanup_state") or ""),
        "post_cleanup": dict(status.get("post_cleanup") or {}),
        "retained_metadata": dict(status.get("retained_metadata") or {}),
        "selected_trade_date": selected_trade_date,
        "latest_trade_date": latest_trade_date(root),
        "docs_root": str(root),
        "run_dir": str(run_dir),
        "archive_root": str(status.get("archive_root") or archive_root),
        "hot_retention_days": int(status.get("hot_retention_days") or 5),
        "storage": dict(status.get("archive_storage") or status.get("storage") or inspect_archive_storage(archive_root)),
        "plan": plan,
        "hot_cleanup": hot_cleanup,
        "hot_cleanup_source_path": str(hot_cleanup_source_path),
        "side_effects": {
            **runtime_archive_side_effects(),
            **dict(status.get("side_effects") or {}),
        },
        "artifacts": [
            artifact_item("archive status", status_path),
            artifact_item("archive contract", artifact_docs_root / "V3_RUNTIME_ARCHIVE_CONTRACT.json"),
            artifact_item("archive preflight", artifact_docs_root / "V3_RUNTIME_ARCHIVE_PREFLIGHT.json"),
            artifact_item("archive post review", artifact_docs_root / "V3_RUNTIME_ARCHIVE_POST_REVIEW.json"),
            artifact_item("archive closeout", artifact_docs_root / "V3_RUNTIME_ARCHIVE_CLOSEOUT_REGISTRATION.json"),
            artifact_item("cleanup policy", artifact_docs_root / "V3_RUNTIME_ARCHIVE_CLEANUP_POLICY_AND_ROLLBACK_REGISTRY.json"),
            artifact_item("hot keep5 cleanup status", keep5_hot_cleanup_path),
            artifact_item("archive manifest", manifest_path),
            artifact_item("archive report", report_path),
        ],
    }


def latest_trade_date(root: Path) -> str:
    latest = root / "latest"
    if latest.is_symlink():
        return latest.resolve().name
    if latest.is_dir():
        return latest.name
    latest_txt = root / "latest.txt"
    if latest_txt.exists():
        return normalize_trade_date(latest_txt.read_text(encoding="utf-8").strip()) or ""
    if not root.exists():
        return ""
    candidates = sorted(path.name for path in root.iterdir() if path.is_dir() and path.name.isdigit())
    return candidates[-1] if candidates else ""


def normalize_trade_date(value: str | None) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() and len(text) == 8 else ""


def load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def archive_plan_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(manifest.get("result") or "ARCHIVED_VERIFIED"),
        "files": list(manifest.get("files") or []),
        "file_count": int(manifest.get("file_count") or 0),
        "total_rows": int(manifest.get("total_rows") or 0),
        "row_count_match": bool(manifest.get("row_count_match")),
        "checksum_algorithm": str(manifest.get("checksum_algorithm") or ""),
        "manifest_path": str(manifest.get("manifest_path") or ""),
        "report_path": str(manifest.get("report_path") or ""),
        "blockers": list(manifest.get("blockers") or []),
        "cleanup_eligible": bool(manifest.get("cleanup_eligible")),
        "cleanup_blockers": list(manifest.get("cleanup_blockers") or ["manual_cleanup_required"]),
    }


def artifact_item(label: str, path: Path) -> dict[str, Any]:
    return {
        "label": label,
        "file_name": path.name,
        "path": str(path),
        "exists": path.exists(),
    }
