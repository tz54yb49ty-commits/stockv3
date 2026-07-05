#!/usr/bin/env python3
"""Plan or execute manifest-gated runtime hot-store keep-5 cleanup."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Any, Callable, Iterable, Iterator

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
ARCHIVE_WRAPPER_SCRIPT = "scripts/run_v3_runtime_archive_keep5_daily_once.py"
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
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


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


def detect_active_archive_processes() -> list[dict[str, Any]]:
    output = subprocess.check_output(["ps", "-axo", "pid=,etime=,stat=,comm=,args="], text=True)
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
    output = subprocess.check_output(["ps", "-axo", "pid=,etime=,stat=,comm=,args="], text=True)
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
    cleanup_success = (
        str(report.get("result") or "").endswith("EXECUTE_PASS")
        and bool(report.get("cleanup_executed"))
        and bool(report.get("cleanup_complete", True))
    )
    retained_after = list(report.get("retained_trade_dates") or []) if cleanup_success else []
    return {
        **report,
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
) -> dict[str, Any]:
    started_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    started_monotonic = perf_counter()
    report_root = Path(report_dir)
    plan_path = report_root / "keep5_cleanup_plan.json"
    closeout_path = report_root / "keep5_cleanup_closeout.json"
    required_confirm_token = DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN if direct_delete_no_archive else KEEP5_CONFIRM_TOKEN
    try:
        with keep5_cleanup_single_flight_lock(report_root) as lock_path:
            active_archive_processes = archive_process_detector() if direct_delete_no_archive else []
            active_runtime_writer_processes = runtime_writer_process_detector() if direct_delete_no_archive else []
            if active_runtime_writer_processes:
                report = blocked_runtime_writer_active_report(
                    report_root=report_root,
                    execute=execute,
                    active_runtime_writer_processes=active_runtime_writer_processes,
                    required_confirm_token=required_confirm_token,
                    lock_path=lock_path,
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
    except CleanupAlreadyRunningError as exc:
        report = blocked_already_running_report(report_root=report_root, execute=execute, error=exc)

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
