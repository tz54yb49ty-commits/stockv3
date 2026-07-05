#!/usr/bin/env python3
"""Run one V3 N3-N6 runtime archive pass.

This is the manual N1/archive entrypoint for sealed runtime data. It writes
Parquet files and manifest/report artifacts to MacRaid only when both
``--execute`` and ``--user-confirmed`` are present. It never writes the runtime
PostgreSQL database, consumes events, updates checkpoints, or performs cleanup.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.runtime_archive import DEFAULT_RUNTIME_ARCHIVE_ROOT, inspect_archive_storage
from ashare_v3.ingestion.runtime_archive_execute import (
    DEFAULT_DSN,
    build_runtime_archive_query_specs,
    execute_runtime_archive,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_DOCS_REPORT_DIR = "docs/runtime_archive"


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def write_markdown(path: str | Path, payload: Mapping[str, Any]) -> None:
    lines = [
        f"# V3 Runtime Archive Report {payload.get('trade_date')}",
        "",
        f"- result: `{payload.get('result')}`",
        f"- reason: `{payload.get('reason') or payload.get('blocked_reason') or ''}`",
        f"- archive root: `{payload.get('archive_root')}`",
        f"- execute: `{payload.get('execute')}`",
        f"- user_confirmed: `{payload.get('user_confirmed')}`",
        f"- query specs: `{payload.get('query_spec_count')}`",
        f"- manifest: `{payload.get('manifest_path', '')}`",
        f"- total rows: `{payload.get('total_rows', 0)}`",
        f"- file count: `{payload.get('file_count', 0)}`",
        "",
        "## Forbidden Scope",
    ]
    for key, value in dict(payload.get("forbidden_scope_proof") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def forbidden_scope_proof() -> dict[str, bool]:
    return {
        "writes_database": False,
        "cleanup_local_runtime": False,
        "outbox_inbox_checkpoint_consumed_or_updated": False,
        "worker_or_scheduler_started": False,
        "n6_voice_mobile_sim_position_trade_touched": False,
        "old_system_touched": False,
        "rollback_executed": False,
    }


def build_base_report(
    *,
    trade_date: str,
    archive_root: str | Path,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    specs = build_runtime_archive_query_specs(trade_date)
    storage = inspect_archive_storage(str(archive_root))
    return {
        "stage": "V3_RUNTIME_ARCHIVE_RUN_ONCE",
        "layer_role": "N1_ingestion",
        "result": "PLAN_ONLY",
        "reason": "plan_only_default",
        "blocked_reason": None,
        "trade_date": trade_date,
        "archive_root": str(archive_root),
        "dsn_label": dsn.split("@", 1)[-1] if "@" in dsn else dsn,
        "execute": bool(execute),
        "user_confirmed": bool(user_confirmed),
        "created_at": datetime.now(ASIA_SHANGHAI).isoformat(),
        "query_spec_count": len(specs),
        "query_specs": [
            {
                "layer": spec.layer,
                "table": spec.table,
                "params": list(spec.params),
            }
            for spec in specs
        ],
        "archive_storage": storage,
        "side_effects": {
            "writes_archive_files": False,
            "writes_database": False,
            "cleanup_local_runtime": False,
            "outbox_inbox_checkpoint_consumed_or_updated": False,
        },
        "forbidden_scope_proof": forbidden_scope_proof(),
    }


def run_v3_runtime_archive_once(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    dsn: str = DEFAULT_DSN,
    report_dir: str | Path = DEFAULT_DOCS_REPORT_DIR,
    execute: bool = False,
    user_confirmed: bool = False,
    archive_executor: Callable[..., dict[str, Any]] = execute_runtime_archive,
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    report = build_base_report(
        trade_date=normalized_trade_date,
        archive_root=archive_root,
        dsn=dsn,
        execute=execute,
        user_confirmed=user_confirmed,
    )

    if execute and not user_confirmed:
        report.update({"result": "BLOCKED", "blocked_reason": "missing_user_confirmed_flag", "reason": None})
    elif user_confirmed and not execute:
        report.update({"result": "BLOCKED", "blocked_reason": "missing_execute_flag", "reason": None})
    elif execute and user_confirmed:
        archive_result = archive_executor(trade_date=normalized_trade_date, dsn=dsn, archive_root=archive_root)
        archive_pass = archive_result.get("result") in {
            "ARCHIVED_VERIFIED",
            "IDEMPOTENT_ARCHIVE_ALREADY_VERIFIED",
        }
        side_effects = dict(archive_result.get("side_effects") or {})
        if archive_result.get("result") == "IDEMPOTENT_ARCHIVE_ALREADY_VERIFIED":
            reason = "archive_already_verified"
        elif archive_result.get("result") == "ARCHIVED_VERIFIED":
            reason = "archive_verified"
        else:
            reason = "archive_verification_failed"
        report.update(
            {
                "result": "EXECUTE_PASS" if archive_pass else "BLOCKED",
                "reason": reason,
                "archive_result": archive_result.get("result"),
                "manifest_path": archive_result.get("manifest_path"),
                "archive_report_path": archive_result.get("report_path"),
                "file_count": archive_result.get("file_count"),
                "total_rows": archive_result.get("total_rows"),
                "row_count_match": archive_result.get("row_count_match"),
                "cleanup_eligible": archive_result.get("cleanup_eligible"),
                "cleanup_blockers": archive_result.get("cleanup_blockers"),
                "table_timing_summary": archive_result.get("table_timings") or [],
                "blocked_reason": archive_result.get("blocked_reason"),
                "current_table": archive_result.get("current_table"),
                "archive_storage": inspect_archive_storage(str(archive_root)),
                "side_effects": {
                    "writes_archive_files": bool(side_effects.get("writes_archive_files", archive_result.get("result") == "ARCHIVED_VERIFIED")),
                    "writes_database": False,
                    "cleanup_local_runtime": False,
                    "outbox_inbox_checkpoint_consumed_or_updated": False,
                },
            }
        )

    report_path = Path(report_dir) / normalized_trade_date / "archive_status.json"
    md_path = Path(report_dir) / normalized_trade_date / "archive_status.md"
    report["docs_report_path"] = str(report_path)
    report["docs_report_md_path"] = str(md_path)
    write_json(report_path, report)
    write_markdown(md_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--archive-root", default=DEFAULT_RUNTIME_ARCHIVE_ROOT)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--report-dir", default=DEFAULT_DOCS_REPORT_DIR)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_v3_runtime_archive_once(
        trade_date=args.trade_date,
        archive_root=args.archive_root,
        dsn=args.dsn,
        report_dir=args.report_dir,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=json_default))
    return 0 if report["result"] in {"PLAN_ONLY", "EXECUTE_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
