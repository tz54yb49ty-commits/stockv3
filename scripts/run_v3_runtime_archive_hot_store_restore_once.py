#!/usr/bin/env python3
"""Restore a verified V3 runtime archive back into local hot PostgreSQL.

The runner is bounded and idempotent. It defaults to PLAN_ONLY and writes the
database only when both ``--execute`` and ``--user-confirmed`` are supplied.
It does not run N3/N4/N5/N6 business code, consume events, start workers, or
touch the old system.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.runtime_archive import DEFAULT_RUNTIME_ARCHIVE_ROOT
from ashare_v3.ingestion.runtime_archive_execute import DEFAULT_DSN
from ashare_v3.ingestion.runtime_archive_restore import (
    archived_scope_live_count,
    manifest_path_for_trade_date,
    restore_runtime_archive,
    validate_restore_manifest,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_report(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def write_markdown(path: str | Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# V3 Runtime Archive Hot Store Restore {payload.get('trade_date')}",
        "",
        f"- result: `{payload.get('result')}`",
        f"- reason: `{payload.get('reason') or payload.get('blocked_reason') or ''}`",
        f"- manifest rows: `{payload.get('manifest_total_rows', 0)}`",
        f"- before live rows: `{payload.get('before_live_total', 0)}`",
        f"- after live rows: `{payload.get('after_live_total', 0)}`",
        f"- inserted rows: `{payload.get('inserted_rows', 0)}`",
        f"- skipped existing rows: `{payload.get('skipped_existing_rows', 0)}`",
        f"- manifest: `{payload.get('manifest_path', '')}`",
        "",
        "## Forbidden Scope",
    ]
    for key, value in dict(payload.get("forbidden_scope_proof") or {}).items():
        lines.append(f"- {key}: `{value}`")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def base_forbidden_scope() -> dict[str, bool]:
    return {
        "business_runners_executed": False,
        "outbox_inbox_checkpoint_consumed_or_updated": False,
        "worker_or_scheduler_started": False,
        "n6_voice_mobile_sim_position_trade_touched": False,
        "old_system_touched": False,
    }


def run_restore_once(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    dsn: str = DEFAULT_DSN,
    report_json: str | Path = "docs/V3_20260612_RUNTIME_ARCHIVE_HOT_STORE_RESTORE_EXECUTE_REPORT.json",
    report_md: str | Path = "docs/V3_20260612_RUNTIME_ARCHIVE_HOT_STORE_RESTORE_EXECUTE_REPORT.md",
    execute: bool = False,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    manifest_path = manifest_path_for_trade_date(trade_date=normalized_trade_date, archive_root=archive_root)
    report: dict[str, Any] = {
        "stage": "V3_RUNTIME_ARCHIVE_HOT_STORE_RESTORE",
        "layer_role": "N1_ingestion",
        "result": "PLAN_ONLY",
        "reason": "plan_only_default",
        "blocked_reason": None,
        "trade_date": normalized_trade_date,
        "archive_root": str(archive_root),
        "manifest_path": str(manifest_path),
        "execute": bool(execute),
        "user_confirmed": bool(user_confirmed),
        "created_at": datetime.now(ASIA_SHANGHAI).isoformat(),
        "forbidden_scope_proof": base_forbidden_scope(),
        "side_effects": {
            "writes_database": False,
            "restores_hot_runtime": False,
            "writes_archive_files": False,
            "cleanup_local_runtime": False,
        },
    }
    manifest = validate_restore_manifest(manifest_path, trade_date=normalized_trade_date)
    before_total, before_nonzero = archived_scope_live_count(dsn=dsn, trade_date=normalized_trade_date)
    report.update(
        {
            "manifest_result": manifest.get("result"),
            "manifest_file_count": manifest.get("file_count"),
            "manifest_total_rows": manifest.get("total_rows"),
            "before_live_total": before_total,
            "before_nonzero_tables": before_nonzero,
        }
    )

    if execute and not user_confirmed:
        report.update({"result": "BLOCKED", "blocked_reason": "missing_user_confirmed_flag", "reason": None})
    elif user_confirmed and not execute:
        report.update({"result": "BLOCKED", "blocked_reason": "missing_execute_flag", "reason": None})
    elif execute and user_confirmed:
        restore_result = restore_runtime_archive(
            trade_date=normalized_trade_date,
            dsn=dsn,
            archive_root=archive_root,
            manifest_path=manifest_path,
        )
        report.update(restore_result)
        report["reason"] = "hot_store_restored_from_verified_archive" if report["result"] == "RESTORE_PASS" else "restore_post_check_failed"
        report["side_effects"] = {
            **dict(report.get("side_effects") or {}),
            "writes_database": True,
            "restores_hot_runtime": True,
        }

    write_report(report_json, report)
    write_markdown(report_md, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--archive-root", default=DEFAULT_RUNTIME_ARCHIVE_ROOT)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--report-json", default="docs/V3_20260612_RUNTIME_ARCHIVE_HOT_STORE_RESTORE_EXECUTE_REPORT.json")
    parser.add_argument("--report-md", default="docs/V3_20260612_RUNTIME_ARCHIVE_HOT_STORE_RESTORE_EXECUTE_REPORT.md")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_restore_once(
        trade_date=args.trade_date,
        archive_root=args.archive_root,
        dsn=args.dsn,
        report_json=args.report_json,
        report_md=args.report_md,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=json_default))
    return 0 if report["result"] in {"PLAN_ONLY", "RESTORE_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
