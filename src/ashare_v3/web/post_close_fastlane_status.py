"""Read-only helpers for the post-close Fast Lane status page."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


KNOWN_STEP_LABELS = {
    "calendar_repair": "Calendar repair",
    "n1_source_facts": "N1 source facts",
    "n1_stock_financial_canonical_source_bundle": "N1 stock financial source bundle",
    "n1_stock_financial_canonical_metrics": "N1 stock financial canonical metrics",
    "n2_condition": "N2 condition",
    "n3_subscription": "N3 subscription",
    "n3_a0_preload_dry_run": "N3-A0 preload dry-run",
    "n3_a1_contract": "N3-A1 contract",
    "n3_a1_preload": "N3-A1 preload",
    "n3_a1_cumulative_amount": "N3-A1 cumulative amount",
    "n4_trigger_context_snapshot": "N4 trigger context snapshot",
    "n4_context_rollback_ready": "N4 context rollback ready",
    "preopen_readiness_noop": "Pre-open readiness noop",
    "lineage_pollution_guard": "Lineage pollution guard",
    "worker_launchd_guard": "Worker/launchd guard",
}


def read_post_close_fastlane_status(
    *,
    docs_root: Path | str,
    for_trade_date: str | None = None,
) -> dict[str, Any]:
    root = Path(docs_root)
    selected_for_trade_date = normalize_trade_date(for_trade_date) or latest_trade_date(root)
    run_dir = root / selected_for_trade_date if selected_for_trade_date else root / "__missing__"
    status_path = run_dir / "00_status.json"
    overlay_path = run_dir / "02_manual_lineage_refresh_status.json"
    report_path = run_dir / "01_oneshot_execute_report.json"
    report_md_path = run_dir / "01_oneshot_execute_report.md"
    n3_a1_path = run_dir / "50_n3_a1_preload_execute_report.json"
    n3_a1_md_path = run_dir / "50_n3_a1_preload_execute_report.md"
    n3_a1_cumulative_path = run_dir / "51_n3_a1_cumulative_amount_execute_report.json"
    n3_a1_cumulative_md_path = run_dir / "51_n3_a1_cumulative_amount_execute_report.md"
    n4_context_path = run_dir / "52_n4_trigger_context_snapshot_execute_report.json"
    n4_context_md_path = run_dir / "52_n4_trigger_context_snapshot_execute_report.md"
    n4_rollback_ready_path = run_dir / "53_n4_context_rollback_ready_report.json"
    n4_rollback_ready_md_path = run_dir / "53_n4_context_rollback_ready_report.md"
    preopen_readiness_path = run_dir / "54_preopen_readiness_noop_report.json"
    preopen_readiness_md_path = run_dir / "54_preopen_readiness_noop_report.md"
    lineage_guard_path = run_dir / "55_lineage_pollution_guard_report.json"
    lineage_guard_md_path = run_dir / "55_lineage_pollution_guard_report.md"
    worker_guard_path = run_dir / "56_worker_launchd_guard_report.json"
    worker_guard_md_path = run_dir / "56_worker_launchd_guard_report.md"

    base_status = load_json_object(status_path)
    overlay_status = load_json_object(overlay_path)
    using_overlay = overlay_status is not None
    report = load_json_object(report_path)
    n3_a1_report = load_json_object(n3_a1_path)
    source_trade_date = str((base_status or {}).get("source_trade_date") or (report or {}).get("source_trade_date") or "")
    for_trade_date_value = str((base_status or {}).get("for_trade_date") or (report or {}).get("for_trade_date") or selected_for_trade_date or "")
    status = dict(overlay_status or base_status or {})
    result = str((status or {}).get("result") or "NO_STATUS")
    if not status:
        status = {
            "result": "NO_STATUS",
            "source_trade_date": "",
            "for_trade_date": selected_for_trade_date,
            "failed_step_id": None,
            "updated_at": "",
            "status_source": "no_status",
        }
    elif using_overlay:
        original_oneshot = dict(status.get("original_oneshot") or {})
        status.setdefault("status_source", "manual_lineage_refresh_overlay")
        status.setdefault(
            "original_oneshot_result",
            original_oneshot.get("result") or (base_status or {}).get("result") or "—",
        )
        status.setdefault("original_oneshot_status_path", original_oneshot.get("status_path") or str(status_path))
        status.setdefault("original_oneshot_report_path", original_oneshot.get("report_path") or str(report_path))
        status.setdefault(
            "superseded_for_display_by_manual_overlay",
            bool(original_oneshot.get("superseded_for_display_by_manual_overlay")),
        )
    else:
        status.setdefault("status_source", "00_status_json")
        status.setdefault("current_effective_lineage", "")
        status.setdefault("original_oneshot_result", (report or base_status or {}).get("result") or "—")
        status.setdefault("original_oneshot_status_path", str(status_path))
        status.setdefault("original_oneshot_report_path", str(report_path))
        status.setdefault("superseded_for_display_by_manual_overlay", False)

    return {
        "result": result,
        "selected_for_trade_date": selected_for_trade_date,
        "latest_for_trade_date": latest_trade_date(root),
        "latest_attempted_for_trade_date": latest_trade_date(root),
        "effective_manual_overlay": latest_manual_overlay(root, selected_for_trade_date),
        "docs_root": str(root),
        "run_dir": str(run_dir),
        "status": status,
        "sub_steps": normalize_sub_steps(report),
        "n3_a1_summary": n3_a1_summary(n3_a1_report),
        "forbidden_scope_proof": dict((report or {}).get("forbidden_scope_proof") or {}),
        "artifacts": [
            artifact_item("manual lineage overlay", overlay_path),
            artifact_item("status", status_path),
            artifact_item("oneshot report", report_path),
            artifact_item("oneshot markdown", report_md_path),
            artifact_item("N3-A1 report", n3_a1_path),
            artifact_item("N3-A1 markdown", n3_a1_md_path),
            artifact_item("N3-A1 cumulative report", n3_a1_cumulative_path),
            artifact_item("N3-A1 cumulative markdown", n3_a1_cumulative_md_path),
            artifact_item("N4 context snapshot report", n4_context_path),
            artifact_item("N4 context snapshot markdown", n4_context_md_path),
            artifact_item("N4 rollback readiness report", n4_rollback_ready_path),
            artifact_item("N4 rollback readiness markdown", n4_rollback_ready_md_path),
            artifact_item("Pre-open readiness report", preopen_readiness_path),
            artifact_item("Pre-open readiness markdown", preopen_readiness_md_path),
            artifact_item("Lineage pollution guard report", lineage_guard_path),
            artifact_item("Lineage pollution guard markdown", lineage_guard_md_path),
            artifact_item("Worker/launchd guard report", worker_guard_path),
            artifact_item("Worker/launchd guard markdown", worker_guard_md_path),
            artifact_item(
                "N3-A1 preload rollback",
                Path("sql") / f"N3_A1_previous_day_minute_preload_{source_trade_date}_for_{for_trade_date_value}_rollback.sql",
            ),
            artifact_item(
                "N3-A1 cumulative rollback",
                Path("sql") / f"N3_A1_previous_day_minute_cumulative_{source_trade_date}_for_{for_trade_date_value}_rollback.sql",
            ),
            artifact_item(
                "N4 context snapshot rollback",
                Path("sql") / f"N4_trigger_context_snapshot_{for_trade_date_value}_rollback.sql",
            ),
        ],
        "log_paths": [
            "logs/post_close_fastlane/stdout.log",
            "logs/post_close_fastlane/stderr.log",
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


def latest_manual_overlay(root: Path, selected_for_trade_date: str | None) -> dict[str, Any]:
    if not root.exists():
        return {}
    selected = normalize_trade_date(selected_for_trade_date)
    for run_dir in sorted((path for path in root.iterdir() if path.is_dir() and path.name.isdigit()), key=lambda p: p.name, reverse=True):
        if run_dir.name == selected:
            continue
        overlay = load_json_object(run_dir / "02_manual_lineage_refresh_status.json")
        if overlay:
            return {
                "for_trade_date": run_dir.name,
                "path": str(run_dir / "02_manual_lineage_refresh_status.json"),
                "result": str(overlay.get("result") or ""),
                "status_source": str(overlay.get("status_source") or ""),
                "source_trade_date": str(overlay.get("source_trade_date") or ""),
                "current_effective_lineage": str(overlay.get("current_effective_lineage") or ""),
                "updated_at": str(overlay.get("updated_at") or ""),
            }
    return {}


def normalize_trade_date(value: str | None) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() and len(text) == 8 else ""


def load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def normalize_sub_steps(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    steps = list((report or {}).get("sub_steps") or [])
    normalized: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "")
        returncode = int(step.get("returncode") or 0)
        status = "PASS" if returncode == 0 else "FAILED"
        if step.get("skipped"):
            status = "SKIPPED"
        normalized.append(
            {
                "step_id": step_id,
                "label": KNOWN_STEP_LABELS.get(step_id, step_id or "unknown"),
                "layer_role": str(step.get("layer_role") or "—"),
                "returncode": returncode,
                "status": status,
                "skipped": bool(step.get("skipped")),
                "skip_reason": str(step.get("skip_reason") or ""),
                "report_paths": [str(path) for path in list(step.get("report_paths") or [])],
                "stdout_tail": str(step.get("stdout_tail") or ""),
                "stderr_tail": str(step.get("stderr_tail") or ""),
            }
        )
    return normalized


def n3_a1_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    report = report or {}
    write_result = dict(report.get("write_result") or {})
    quality = dict(report.get("quality") or {})
    return {
        "stage": str(report.get("stage") or "N3-A1"),
        "objects_processed": int(write_result.get("objects_processed") or 0),
        "minute_rows_written": int(write_result.get("minute_rows_written") or 0),
        "preload_status_rows_written": int(write_result.get("preload_status_rows_written") or 0),
        "event_outbox_rows_written": int(write_result.get("event_outbox_rows_written") or 0),
        "P0": int(quality.get("p0_count") or 0),
        "P1": int(quality.get("p1_count") or 0),
        "P2": int(quality.get("p2_count") or 0),
    }


def artifact_item(label: str, path: Path) -> dict[str, Any]:
    return {
        "label": label,
        "file_name": path.name,
        "path": str(path),
        "exists": path.exists(),
    }
