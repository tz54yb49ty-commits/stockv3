#!/usr/bin/env python3
"""Plan or execute manifest-gated runtime hot-store keep-5 cleanup."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from time import perf_counter
from typing import Any, Callable, Iterable, Iterator
from zoneinfo import ZoneInfo

from ashare_v3.ingestion.runtime_archive import DEFAULT_RUNTIME_ARCHIVE_ROOT, runtime_archive_side_effects
from ashare_v3.ingestion.runtime_archive_execute import DEFAULT_DSN
from ashare_v3.ingestion.runtime_hot_cleanup import (
    DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
    KEEP5_CONFIRM_TOKEN,
    RuntimeHotCleanupSpec,
    build_keep2_dirty_hot_cleanup_plan,
    execute_keep2_dirty_hot_cleanup,
)


DEFAULT_REPORT_DIR = "docs/runtime_archive/hot_keep5_cleanup"
DEFAULT_RETENTION_TRADE_DAYS = 5
DEFAULT_SINGLE_FLIGHT_LOCK_NAME = ".keep5_cleanup.lock"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
ARCHIVE_WRAPPER_SCRIPT = "scripts/run_v3_runtime_archive_keep5_daily_once.py"
RUNTIME_ARTIFACT_PREFIXES = ("n3_", "n4_", "n5_")
TMP_ARTIFACT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^N3P_(\d{8})_(\d{4})_trigger_proof_contract\.json$"), "n3"),
    (re.compile(r"^N3_hint_(\d{8})_(\d{4})_midday_bridge_v1_contract\.json$"), "n3"),
    (re.compile(r"^N4_(\d{8})_(\d{4})_(?:ordinary_matcher|hint_matcher)_execute_report\.json$"), "n4"),
)
N5_DATED_ARTIFACT_ROOTS = (
    "tmp/N5_N3T_action_confirmation_fastlane_monitor",
    "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck",
    "tmp/n5_active_scope_terminal_ref_repair",
)
RUNTIME_WRITER_MARKERS = (
    "scripts/run_n3_",
    "scripts/run_n4_",
    "scripts/run_n5_",
    "scripts/run_n6_",
    "run_n3_",
    "run_n4_",
    "run_n5_",
    "run_n6_",
    "provisional_ordinary",
    "provisional_projection",
    "intraday_proof_poller",
    "proof_discovery_poll",
    "live_tracking_poller",
)
RUNTIME_WRITER_EXCLUDE_MARKERS = (
    "scripts/run_runtime_hot_keep5_cleanup_once.py",
    "scripts/run_runtime_dirty_hot_keep2_cleanup_once.py",
    "scripts/run_v3_runtime_archive_keep5_daily_once.py",
    "run_n6_user_app.py",
    "run_n6_ai_research_bridge.py",
)


class CleanupAlreadyRunningError(RuntimeError):
    def __init__(self, lock_path: Path, holder_evidence: str) -> None:
        super().__init__(f"cleanup already running; lock_path={lock_path}")
        self.lock_path = lock_path
        self.holder_evidence = holder_evidence


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def cleanup_local_runtime_artifacts(
    *,
    project_root: str | Path = PROJECT_ROOT,
    retention_trade_days: int = DEFAULT_RETENTION_TRADE_DAYS,
    retained_trade_dates: Iterable[str] | None = None,
    cleanup_trade_dates: Iterable[str] | None = None,
    execute: bool = False,
    direct_delete_no_archive: bool = False,
    confirm_token: str = "",
    current_date: date | None = None,
) -> dict[str, Any]:
    """Plan or delete exact N3/N4/N5 daily filesystem artifacts."""

    started_monotonic = perf_counter()
    started_at = datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()
    today = current_date or datetime.now(ASIA_SHANGHAI).date()
    root_input = Path(project_root)
    payload = _local_file_cleanup_base(execute=execute, project_root=root_input, started_at=started_at)

    if retention_trade_days != DEFAULT_RETENTION_TRADE_DAYS:
        payload["blockers"] = ["retention_trade_days_must_equal_5"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_RETENTION_CONTRACT")
    if root_input.is_symlink() or not root_input.is_dir():
        payload["blockers"] = ["project_root_missing_or_symlink"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_PROJECT_ROOT")
    if execute and (
        not direct_delete_no_archive or confirm_token != DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN
    ):
        payload["blockers"] = ["direct_delete_confirm_token_required"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_CONFIRM_TOKEN")

    if retained_trade_dates is None or cleanup_trade_dates is None:
        payload["blockers"] = ["authoritative_trade_date_partition_required"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_TRADE_DATE_PARTITION")
    retained_dates = [str(item) for item in retained_trade_dates]
    cleanup_dates = [str(item) for item in cleanup_trade_dates]
    partition_dates = retained_dates + cleanup_dates
    if (
        retained_dates != sorted(set(retained_dates))
        or cleanup_dates != sorted(set(cleanup_dates))
        or set(retained_dates).intersection(cleanup_dates)
        or len(retained_dates) > retention_trade_days
        or any(not _valid_local_artifact_trade_date(item, today=today) for item in partition_dates)
    ):
        payload["blockers"] = ["authoritative_trade_date_partition_invalid"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_TRADE_DATE_PARTITION")

    root = root_input.resolve()
    targets, skipped = _discover_local_artifact_targets(root, today=today)
    cleanup_set = set(cleanup_dates)
    payload.update(
        {
            "project_root": str(root),
            "retained_trade_dates": retained_dates,
            "cleanup_trade_dates": cleanup_dates,
            "skipped_count": len(skipped),
            "skipped": skipped,
        }
    )

    safe_targets: list[tuple[dict[str, Any], dict[str, int]]] = []
    for target in targets:
        if target["trade_date"] not in cleanup_set:
            continue
        stats, error = _local_artifact_target_stats(Path(target["path"]))
        if error:
            payload["errors"].append(error)
            continue
        safe_targets.append((target, stats))
        _add_local_file_counts(payload, layer=str(target["layer"]), prefix="candidate", stats=stats)

    if execute:
        for target, stats in safe_targets:
            path = Path(target["path"])
            try:
                if path.is_symlink():
                    raise OSError("symlink target refused")
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except OSError as exc:
                payload["errors"].append(f"delete_failed:{path}:{exc}")
                continue
            _add_local_file_counts(payload, layer=str(target["layer"]), prefix="deleted", stats=stats)
            payload["released_bytes"] += stats["bytes"]
        payload["deleted_empty_date_directory_count"] = _remove_empty_runtime_date_directories(
            root / "docs/runtime",
            cleanup_dates,
        )
        payload["deleted_directory_count"] += payload["deleted_empty_date_directory_count"]
        payload["cleanup_executed"] = True
        result = "LOCAL_FILE_KEEP5_EXECUTE_PASS" if not payload["errors"] else "LOCAL_FILE_KEEP5_EXECUTE_PARTIAL"
    else:
        result = "LOCAL_FILE_KEEP5_DRY_RUN_PASS" if not payload["errors"] else "LOCAL_FILE_KEEP5_DRY_RUN_PARTIAL"

    if payload["errors"]:
        payload["blockers"] = ["local_artifact_cleanup_errors"]
    payload["side_effects"]["cleanup_local_runtime_files"] = bool(
        payload["deleted_file_count"] or payload["deleted_directory_count"]
    )
    return _finish_local_file_cleanup(payload, started_monotonic, result=result)


def blocked_local_file_cleanup(
    *,
    project_root: str | Path,
    execute: bool,
    blocker: str,
) -> dict[str, Any]:
    started_monotonic = perf_counter()
    payload = _local_file_cleanup_base(
        execute=execute,
        project_root=Path(project_root),
        started_at=datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
    )
    payload["blockers"] = [blocker]
    return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_CLEANUP")


def _local_file_cleanup_base(*, execute: bool, project_root: Path, started_at: str) -> dict[str, Any]:
    per_layer = {
        layer: {
            "candidate_file_count": 0,
            "candidate_directory_count": 0,
            "candidate_bytes": 0,
            "deleted_file_count": 0,
            "deleted_directory_count": 0,
            "released_bytes": 0,
        }
        for layer in ("n3", "n4", "n5")
    }
    return {
        "result": "LOCAL_FILE_KEEP5_NOT_RUN",
        "mode": "execute" if execute else "dry_run",
        "started_at": started_at,
        "finished_at": "",
        "duration_ms": 0,
        "project_root": str(project_root),
        "retention_trade_days": DEFAULT_RETENTION_TRADE_DAYS,
        "retained_trade_dates": [],
        "cleanup_trade_dates": [],
        "candidate_file_count": 0,
        "candidate_directory_count": 0,
        "candidate_bytes": 0,
        "deleted_file_count": 0,
        "deleted_directory_count": 0,
        "deleted_empty_date_directory_count": 0,
        "released_bytes": 0,
        "cleanup_executed": False,
        "skipped_count": 0,
        "skipped": [],
        "errors": [],
        "blockers": [],
        "per_layer": per_layer,
        "side_effects": {
            "writes_database": False,
            "writes_archive_files": False,
            "cleanup_local_runtime_files": False,
            "outbox_inbox_checkpoint_touched": False,
            "launchctl_touched": False,
            "runtime_started": False,
        },
    }


def _finish_local_file_cleanup(payload: dict[str, Any], started_monotonic: float, *, result: str) -> dict[str, Any]:
    payload["result"] = result
    payload["finished_at"] = datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()
    payload["duration_ms"] = round((perf_counter() - started_monotonic) * 1000.0, 3)
    return payload


def _discover_local_artifact_targets(root: Path, *, today: date) -> tuple[list[dict[str, Any]], list[str]]:
    targets: list[dict[str, Any]] = []
    skipped: list[str] = []
    runtime_root = root / "docs/runtime"
    if runtime_root.is_dir() and not runtime_root.is_symlink():
        for date_dir in sorted(runtime_root.iterdir(), key=lambda item: item.name):
            trade_date = _valid_local_artifact_trade_date(date_dir.name, today=today)
            if not trade_date or not date_dir.is_dir() or date_dir.is_symlink():
                continue
            for child in sorted(date_dir.iterdir(), key=lambda item: item.name):
                layer = _runtime_artifact_layer(child.name)
                if not layer:
                    continue
                if child.is_symlink():
                    skipped.append(f"symlink_skipped:{child}")
                    continue
                targets.append({"path": child, "trade_date": trade_date, "layer": layer})

    tmp_root = root / "tmp"
    if tmp_root.is_dir() and not tmp_root.is_symlink():
        for child in sorted(tmp_root.iterdir(), key=lambda item: item.name):
            if child.is_symlink() or not child.is_file():
                continue
            for pattern, layer in TMP_ARTIFACT_RULES:
                matched = pattern.fullmatch(child.name)
                if not matched:
                    continue
                trade_date = _valid_local_artifact_trade_date(matched.group(1), today=today)
                if trade_date:
                    targets.append({"path": child, "trade_date": trade_date, "layer": layer})
                else:
                    skipped.append(f"invalid_or_future_date_skipped:{child}")
                break

    for relative_root in N5_DATED_ARTIFACT_ROOTS:
        dated_root = root / relative_root
        if not dated_root.is_dir() or dated_root.is_symlink():
            continue
        for child in sorted(dated_root.iterdir(), key=lambda item: item.name):
            trade_date = _valid_local_artifact_trade_date(child.name, today=today)
            if not trade_date or not child.is_dir():
                continue
            if child.is_symlink():
                skipped.append(f"symlink_skipped:{child}")
                continue
            targets.append({"path": child, "trade_date": trade_date, "layer": "n5"})
    return sorted(targets, key=lambda item: str(item["path"])), skipped


def _runtime_artifact_layer(name: str) -> str:
    lowered = name.lower()
    for prefix in RUNTIME_ARTIFACT_PREFIXES:
        if lowered.startswith(prefix):
            return prefix[:2]
    return ""


def _valid_local_artifact_trade_date(value: str, *, today: date) -> str:
    if not re.fullmatch(r"\d{8}", value):
        return ""
    try:
        parsed = datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return ""
    return value if parsed <= today else ""


def _local_artifact_target_stats(path: Path) -> tuple[dict[str, int], str]:
    try:
        root_stat = path.lstat()
    except OSError as exc:
        return {}, f"stat_failed:{path}:{exc}"
    if stat.S_ISLNK(root_stat.st_mode):
        return {}, f"symlink_skipped:{path}"
    if stat.S_ISREG(root_stat.st_mode):
        return {"file_count": 1, "directory_count": 0, "bytes": int(root_stat.st_size)}, ""
    if not stat.S_ISDIR(root_stat.st_mode):
        return {}, f"non_regular_path_skipped:{path}"

    file_count = 0
    directory_count = 1
    total_bytes = 0
    stack = [path]
    try:
        while stack:
            current = stack.pop()
            with os.scandir(current) as entries:
                for entry in entries:
                    entry_stat = entry.stat(follow_symlinks=False)
                    entry_path = Path(entry.path)
                    if stat.S_ISLNK(entry_stat.st_mode):
                        return {}, f"symlink_skipped:{entry_path}"
                    if stat.S_ISDIR(entry_stat.st_mode):
                        directory_count += 1
                        stack.append(entry_path)
                    elif stat.S_ISREG(entry_stat.st_mode):
                        file_count += 1
                        total_bytes += int(entry_stat.st_size)
                    else:
                        return {}, f"non_regular_path_skipped:{entry_path}"
    except OSError as exc:
        return {}, f"stat_failed:{path}:{exc}"
    return {"file_count": file_count, "directory_count": directory_count, "bytes": total_bytes}, ""


def _add_local_file_counts(payload: dict[str, Any], *, layer: str, prefix: str, stats: dict[str, int]) -> None:
    file_key = f"{prefix}_file_count"
    directory_key = f"{prefix}_directory_count"
    bytes_key = "candidate_bytes" if prefix == "candidate" else "released_bytes"
    payload[file_key] += stats["file_count"]
    payload[directory_key] += stats["directory_count"]
    if prefix == "candidate":
        payload[bytes_key] += stats["bytes"]
    layer_payload = payload["per_layer"][layer]
    layer_payload[file_key] += stats["file_count"]
    layer_payload[directory_key] += stats["directory_count"]
    layer_payload[bytes_key] += stats["bytes"]


def _remove_empty_runtime_date_directories(runtime_root: Path, cleanup_trade_dates: list[str]) -> int:
    removed = 0
    for trade_date in cleanup_trade_dates:
        date_dir = runtime_root / trade_date
        try:
            if date_dir.is_dir() and not date_dir.is_symlink() and not any(date_dir.iterdir()):
                date_dir.rmdir()
                removed += 1
        except OSError:
            continue
    return removed


@contextmanager
def keep5_cleanup_single_flight_lock(report_root: Path) -> Iterator[Path]:
    report_root.mkdir(parents=True, exist_ok=True)
    lock_path = report_root / DEFAULT_SINGLE_FLIGHT_LOCK_NAME
    lock_file = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.seek(0)
            holder_evidence = lock_file.read().strip()
            raise CleanupAlreadyRunningError(lock_path, holder_evidence) from exc

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "started_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
                    "lock_policy": "keep5_cleanup_single_flight_v1",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        lock_file.flush()
        yield lock_path
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


def blocked_already_running_report(*, report_root: Path, execute: bool, error: CleanupAlreadyRunningError) -> dict[str, Any]:
    side_effects = runtime_archive_side_effects()
    side_effects["cleanup_local_runtime_files"] = False
    return {
        "result": "BLOCKED_CLEANUP_ALREADY_RUNNING",
        "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
        "execute": bool(execute),
        "required_confirm_token": KEEP5_CONFIRM_TOKEN,
        "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
        "cleanup_authorized": False,
        "cleanup_executed": False,
        "database_written": False,
        "deleted_total_rows": 0,
        "blockers": ["BLOCKED_CLEANUP_ALREADY_RUNNING"],
        "single_flight_lock_policy": "keep5_cleanup_single_flight_v1",
        "single_flight_lock_acquired": False,
        "single_flight_lock_path": str(error.lock_path),
        "single_flight_lock_holder": error.holder_evidence,
        "side_effects": side_effects,
    }


def read_process_table() -> str:
    """Read the process table without assuming every argv byte is valid UTF-8."""

    output = subprocess.check_output(["ps", "-axo", "pid=,etime=,stat=,comm=,args="])
    return output.decode("utf-8", errors="replace")


def detect_active_archive_processes() -> list[dict[str, Any]]:
    output = read_process_table()
    processes: list[dict[str, Any]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if ARCHIVE_WRAPPER_SCRIPT not in stripped:
            continue
        if "python3 scripts/" not in stripped and "Python scripts/" not in stripped:
            continue
        parts = stripped.split(None, 4)
        if len(parts) < 5:
            continue
        processes.append(
            {
                "pid": int(parts[0]),
                "etime": parts[1],
                "stat": parts[2],
                "command": parts[4],
            }
        )
    return processes


def detect_active_runtime_writer_processes() -> list[dict[str, Any]]:
    output = read_process_table()
    processes: list[dict[str, Any]] = []
    current_pid = os.getpid()
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in RUNTIME_WRITER_EXCLUDE_MARKERS):
            continue
        if not any(marker in stripped for marker in RUNTIME_WRITER_MARKERS):
            continue
        if "python" not in stripped.lower():
            continue
        parts = stripped.split(None, 4)
        if len(parts) < 5:
            continue
        pid = int(parts[0])
        if pid == current_pid:
            continue
        processes.append(
            {
                "pid": pid,
                "etime": parts[1],
                "stat": parts[2],
                "command": parts[4],
            }
        )
    return processes


def blocked_process_inspection_report(
    *,
    report_root: Path,
    execute: bool,
    direct_delete_no_archive: bool,
    required_confirm_token: str,
    failed_detector: str,
    error: Exception,
    lock_path: Path,
) -> dict[str, Any]:
    side_effects = runtime_archive_side_effects()
    side_effects["cleanup_local_runtime_files"] = False
    return {
        "result": "BLOCKED_PROCESS_INSPECTION_FAILED",
        "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
        "failed_stage": "process_inspection",
        "failed_detector": failed_detector,
        "error_type": type(error).__name__,
        "execute": bool(execute),
        "direct_delete_no_archive": bool(direct_delete_no_archive),
        "required_confirm_token": required_confirm_token,
        "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
        "cleanup_authorized": False,
        "cleanup_executed": False,
        "cleanup_complete": False,
        "database_written": False,
        "deleted_rows": [],
        "deleted_total_rows": 0,
        "blockers": ["process_inspection_failed"],
        "single_flight_lock_policy": "keep5_cleanup_single_flight_v1",
        "single_flight_lock_acquired": True,
        "single_flight_lock_path": str(lock_path),
        "side_effects": side_effects,
    }


def blocked_runtime_writer_active_report(
    *,
    report_root: Path,
    execute: bool,
    active_runtime_writer_processes: list[dict[str, Any]],
    required_confirm_token: str,
    lock_path: Path,
) -> dict[str, Any]:
    side_effects = runtime_archive_side_effects()
    side_effects["cleanup_local_runtime_files"] = False
    return {
        "result": "BLOCKED_RUNTIME_WRITER_ACTIVE",
        "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
        "execute": bool(execute),
        "required_confirm_token": required_confirm_token,
        "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
        "cleanup_authorized": False,
        "cleanup_executed": False,
        "cleanup_complete": False,
        "database_written": False,
        "deleted_rows": [],
        "deleted_total_rows": 0,
        "blockers": ["runtime_writer_active"],
        "active_runtime_writer_processes": active_runtime_writer_processes,
        "single_flight_lock_policy": "keep5_cleanup_single_flight_v1",
        "single_flight_lock_acquired": True,
        "single_flight_lock_path": str(lock_path),
        "side_effects": side_effects,
    }


def summarize_deleted_rows(deleted_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in deleted_rows:
        deleted_count = int(row.get("deleted_rows") or 0)
        if deleted_count <= 0:
            continue
        key = (str(row.get("layer") or ""), str(row.get("table") or ""))
        item = grouped.setdefault(
            key,
            {
                "layer": key[0],
                "table": key[1],
                "trade_dates": set(),
                "deleted_rows": 0,
            },
        )
        trade_date = str(row.get("trade_date") or "")
        if trade_date:
            item["trade_dates"].add(trade_date)
        item["deleted_rows"] += deleted_count
    summary: list[dict[str, Any]] = []
    for item in grouped.values():
        trade_dates = sorted(item.pop("trade_dates"))
        summary.append(
            {
                "layer": item["layer"],
                "table": item["table"],
                "trade_date_count": len(trade_dates),
                "deleted_rows": int(item["deleted_rows"]),
            }
        )
    return sorted(summary, key=lambda row: (str(row["layer"]), str(row["table"])))


def augment_cleanup_report(
    report: dict[str, Any],
    *,
    started_at: str,
    started_monotonic: float,
) -> dict[str, Any]:
    finished_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    summary = summarize_deleted_rows(list(report.get("deleted_rows") or []))
    row_cleanup_success = (
        str(report.get("result") or "").endswith("EXECUTE_PASS")
        and bool(report.get("cleanup_executed"))
        and bool(report.get("cleanup_complete", True))
    )
    local_cleanup = dict(report.get("local_file_cleanup") or {})
    local_cleanup_required = bool(report.get("execute")) and bool(report.get("direct_delete_no_archive"))
    local_cleanup_success = (
        not local_cleanup_required
        or (
            str(local_cleanup.get("result") or "") == "LOCAL_FILE_KEEP5_EXECUTE_PASS"
            and bool(local_cleanup.get("cleanup_executed"))
            and not list(local_cleanup.get("errors") or [])
            and not list(local_cleanup.get("blockers") or [])
        )
    )
    cleanup_success = row_cleanup_success and local_cleanup_success
    result = str(report.get("result") or "")
    if row_cleanup_success and local_cleanup_required and not local_cleanup_success:
        if str(local_cleanup.get("result") or "").startswith("BLOCKED_"):
            result = "BLOCKED_RUNTIME_HOT_KEEP5_LOCAL_FILE_CLEANUP"
        else:
            result = "RUNTIME_HOT_KEEP5_CLEANUP_EXECUTE_PARTIAL"
    retained_after = list(report.get("retained_trade_dates") or []) if cleanup_success else []
    return {
        **report,
        "result": result,
        "cleanup_success": cleanup_success,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": round((perf_counter() - started_monotonic) * 1000.0, 3),
        "deleted_table_summary": summary,
        "deleted_table_summary_count": len(summary),
        "current_hot_trade_dates_after": retained_after,
        "retained_trade_dates_after": retained_after,
    }


def sync_closeout_with_status(closeout_path: Path, report: dict[str, Any]) -> None:
    if not closeout_path.exists():
        return
    try:
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(closeout, dict):
        return
    for key in (
        "cleanup_success",
        "started_at",
        "finished_at",
        "duration_ms",
        "deleted_table_summary",
        "deleted_table_summary_count",
        "current_hot_trade_dates_after",
        "retained_trade_dates_after",
    ):
        closeout[key] = report.get(key)
    write_json(closeout_path, closeout)


def run_runtime_hot_keep5_cleanup_once(
    *,
    dsn: str = DEFAULT_DSN,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    report_dir: str | Path = DEFAULT_REPORT_DIR,
    execute: bool = False,
    confirm_token: str = "",
    direct_delete_no_archive: bool = False,
    skip_row_count_plan: bool = False,
    trade_dates: Iterable[str] | None = None,
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    table_deleter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    archive_process_detector: Callable[[], list[dict[str, Any]]] = detect_active_archive_processes,
    runtime_writer_process_detector: Callable[[], list[dict[str, Any]]] = detect_active_runtime_writer_processes,
    fk_closure_auditor: Callable[..., dict[str, Any]] | None = None,
    max_delete_units: int | None = None,
    local_artifact_project_root: str | Path | None = None,
    local_artifact_current_date: date | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()
    started_monotonic = perf_counter()
    report_root = Path(report_dir)
    local_project_root = Path(local_artifact_project_root) if local_artifact_project_root is not None else (
        PROJECT_ROOT if trade_dates is None else report_root.parent
    )
    plan_path = report_root / "keep5_cleanup_plan.json"
    closeout_path = report_root / "keep5_cleanup_closeout.json"
    required_confirm_token = DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN if direct_delete_no_archive else KEEP5_CONFIRM_TOKEN
    try:
        with keep5_cleanup_single_flight_lock(report_root) as lock_path:
            active_archive_processes: list[dict[str, Any]] = []
            active_runtime_writer_processes: list[dict[str, Any]] = []
            failed_detector = ""
            process_inspection_error: Exception | None = None
            if direct_delete_no_archive:
                try:
                    active_archive_processes = archive_process_detector()
                except Exception as exc:
                    failed_detector = "archive_process"
                    process_inspection_error = exc
                if process_inspection_error is None:
                    try:
                        active_runtime_writer_processes = runtime_writer_process_detector()
                    except Exception as exc:
                        failed_detector = "runtime_writer_process"
                        process_inspection_error = exc

            if process_inspection_error is not None:
                report = blocked_process_inspection_report(
                    report_root=report_root,
                    execute=execute,
                    direct_delete_no_archive=direct_delete_no_archive,
                    required_confirm_token=required_confirm_token,
                    failed_detector=failed_detector,
                    error=process_inspection_error,
                    lock_path=lock_path,
                )
                report["local_file_cleanup"] = blocked_local_file_cleanup(
                    project_root=local_project_root,
                    execute=execute,
                    blocker="process_inspection_failed",
                )
            elif active_runtime_writer_processes:
                report = blocked_runtime_writer_active_report(
                    report_root=report_root,
                    execute=execute,
                    active_runtime_writer_processes=active_runtime_writer_processes,
                    required_confirm_token=required_confirm_token,
                    lock_path=lock_path,
                )
                report["local_file_cleanup"] = blocked_local_file_cleanup(
                    project_root=local_project_root,
                    execute=execute,
                    blocker="runtime_writer_active",
                )
            else:
                plan = build_keep2_dirty_hot_cleanup_plan(
                    dsn=dsn,
                    trade_dates=trade_dates,
                    retention_trade_days=DEFAULT_RETENTION_TRADE_DAYS,
                    plan_path=plan_path,
                    archive_root=archive_root,
                    require_verified_archive=not direct_delete_no_archive,
                    direct_delete_no_archive=direct_delete_no_archive,
                    skip_row_count_plan=skip_row_count_plan,
                    table_counter=table_counter,
                    active_archive_processes=active_archive_processes,
                    fk_closure_auditor=fk_closure_auditor,
                )
                if execute:
                    report = execute_keep2_dirty_hot_cleanup(
                        plan_path=plan_path,
                        confirm_token=confirm_token,
                        expected_confirm_token=required_confirm_token,
                        dsn=dsn,
                        closeout_path=closeout_path,
                        current_trade_dates=trade_dates,
                        table_counter=table_counter,
                        table_deleter=table_deleter,
                        max_delete_units=max_delete_units,
                    )
                else:
                    report = plan
                report = {
                    **report,
                    "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
                    "execute": bool(execute),
                    "required_confirm_token": required_confirm_token,
                    "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
                    "single_flight_lock_policy": "keep5_cleanup_single_flight_v1",
                    "single_flight_lock_acquired": True,
                    "single_flight_lock_path": str(lock_path),
                }
                row_cleanup_execute_ready = (
                    str(report.get("result") or "") == "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS"
                    and bool(report.get("cleanup_executed"))
                    and bool(report.get("cleanup_complete"))
                )
                if not direct_delete_no_archive:
                    local_file_cleanup = blocked_local_file_cleanup(
                        project_root=local_project_root,
                        execute=execute,
                        blocker="direct_delete_no_archive_mode_required",
                    )
                elif active_archive_processes:
                    local_file_cleanup = blocked_local_file_cleanup(
                        project_root=local_project_root,
                        execute=execute,
                        blocker="archive_process_conflict",
                    )
                elif execute and not row_cleanup_execute_ready:
                    local_file_cleanup = blocked_local_file_cleanup(
                        project_root=local_project_root,
                        execute=execute,
                        blocker="hot_row_cleanup_not_complete",
                    )
                else:
                    local_file_cleanup = cleanup_local_runtime_artifacts(
                        project_root=local_project_root,
                        retained_trade_dates=list(report.get("retained_trade_dates") or []),
                        cleanup_trade_dates=list(report.get("cleanup_trade_dates") or []),
                        execute=execute,
                        direct_delete_no_archive=direct_delete_no_archive,
                        confirm_token=confirm_token,
                        current_date=local_artifact_current_date,
                    )
                report["local_file_cleanup"] = local_file_cleanup
                report["side_effects"] = {
                    **dict(report.get("side_effects") or {}),
                    "cleanup_local_runtime_files": bool(
                        dict(local_file_cleanup.get("side_effects") or {}).get("cleanup_local_runtime_files")
                    ),
                }
    except CleanupAlreadyRunningError as exc:
        report = blocked_already_running_report(report_root=report_root, execute=execute, error=exc)
        report["local_file_cleanup"] = blocked_local_file_cleanup(
            project_root=local_project_root,
            execute=execute,
            blocker="cleanup_already_running",
        )

    report = augment_cleanup_report(report, started_at=started_at, started_monotonic=started_monotonic)
    sync_closeout_with_status(closeout_path, report)
    write_json(report["docs_report_path"], report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--archive-root", default=DEFAULT_RUNTIME_ARCHIVE_ROOT)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-token", default="")
    parser.add_argument("--direct-delete-no-archive", action="store_true")
    parser.add_argument("--skip-row-count-plan", action="store_true")
    parser.add_argument(
        "--max-delete-units",
        type=int,
        default=None,
        help="Optional resumable execute limit. One unit is one simple table delete or one expanded batch delete.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_runtime_hot_keep5_cleanup_once(
        dsn=args.dsn,
        archive_root=args.archive_root,
        report_dir=args.report_dir,
        execute=args.execute,
        confirm_token=args.confirm_token,
        direct_delete_no_archive=args.direct_delete_no_archive,
        skip_row_count_plan=args.skip_row_count_plan,
        max_delete_units=args.max_delete_units,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=json_default))
    return 0 if str(report["result"]).endswith("_PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
