#!/usr/bin/env python3
"""Run daily keep-5 runtime archive orchestration once.

Default mode is plan-only. Execute mode delegates each archive-eligible trade
date to ``run_v3_runtime_archive_once`` and never writes PostgreSQL or cleans
hot runtime rows.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

import psycopg

from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.runtime_archive import DEFAULT_RUNTIME_ARCHIVE_ROOT, runtime_archive_side_effects
from ashare_v3.ingestion.runtime_archive_execute import DEFAULT_DSN
from ashare_v3.ingestion.runtime_hot_cleanup import discover_hot_trade_dates, normalize_retention_trade_days

from scripts.run_v3_runtime_archive_once import run_v3_runtime_archive_once


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_REPORT_DIR = "docs/runtime_archive"
DEFAULT_RETENTION_TRADE_DAYS = 5


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def select_archive_trade_dates(
    trade_dates: Iterable[str],
    *,
    retention_trade_days: int = DEFAULT_RETENTION_TRADE_DAYS,
) -> dict[str, Any]:
    retention = normalize_retention_trade_days(retention_trade_days)
    normalized = sorted({require_yyyymmdd(str(item), "trade_date") for item in trade_dates})
    return {
        "retention_trade_days": retention,
        "retention_policy": "latest_hot_trade_dates",
        "trade_dates": normalized,
        "retained_trade_dates": normalized[-retention:],
        "archive_trade_dates": normalized[:-retention],
    }


def run_v3_runtime_archive_keep5_daily_once(
    *,
    dsn: str = DEFAULT_DSN,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    report_dir: str | Path = DEFAULT_REPORT_DIR,
    retention_trade_days: int = DEFAULT_RETENTION_TRADE_DAYS,
    execute: bool = False,
    user_confirmed: bool = False,
    trade_dates: Iterable[str] | None = None,
    connection_factory: Callable[[str], Any] = psycopg.connect,
    archive_runner: Callable[..., dict[str, Any]] = run_v3_runtime_archive_once,
) -> dict[str, Any]:
    discovered = (
        sorted({require_yyyymmdd(str(item), "trade_date") for item in trade_dates})
        if trade_dates is not None
        else discover_hot_trade_dates(dsn=dsn, connection_factory=connection_factory)
    )
    selection = select_archive_trade_dates(discovered, retention_trade_days=retention_trade_days)
    report_root = Path(report_dir)
    side_effects = {
        **runtime_archive_side_effects(),
        "writes_database": False,
        "cleanup_local_runtime": False,
    }
    payload: dict[str, Any] = {
        "stage": "V3_RUNTIME_ARCHIVE_KEEP5_DAILY_ONCE",
        "layer_role": "runtime_control",
        "result": "PLAN_ONLY",
        "created_at": datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
        "archive_root": str(archive_root),
        "report_dir": str(report_root),
        "execute": bool(execute),
        "user_confirmed": bool(user_confirmed),
        "archive_reports": [],
        "blockers": [],
        "side_effects": side_effects,
        **selection,
    }
    if execute and not user_confirmed:
        payload["result"] = "BLOCKED"
        payload["blockers"] = ["missing_user_confirmed_flag"]
    elif user_confirmed and not execute:
        payload["result"] = "BLOCKED"
        payload["blockers"] = ["missing_execute_flag"]
    elif execute and user_confirmed:
        archive_reports: list[dict[str, Any]] = []
        blockers: list[str] = []
        writes_archive_files = False
        for trade_date in payload["archive_trade_dates"]:
            child = archive_runner(
                trade_date=trade_date,
                archive_root=archive_root,
                dsn=dsn,
                report_dir=report_root,
                execute=True,
                user_confirmed=True,
            )
            archive_reports.append(child)
            if child.get("result") != "EXECUTE_PASS":
                blockers.append(f"archive_failed:{trade_date}")
            child_side_effects = dict(child.get("side_effects") or {})
            writes_archive_files = writes_archive_files or bool(child_side_effects.get("writes_archive_files"))
        payload["archive_reports"] = archive_reports
        payload["blockers"] = blockers
        payload["result"] = "EXECUTE_PASS" if not blockers else "BLOCKED"
        payload["side_effects"]["writes_archive_files"] = writes_archive_files
        payload["side_effects"]["archive_files_written"] = writes_archive_files
    status_path = report_root / "daily_keep5_archive_status.json"
    payload["docs_report_path"] = str(status_path)
    write_json(status_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--archive-root", default=DEFAULT_RUNTIME_ARCHIVE_ROOT)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--retention-trade-days", type=int, default=DEFAULT_RETENTION_TRADE_DAYS)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_v3_runtime_archive_keep5_daily_once(
        dsn=args.dsn,
        archive_root=args.archive_root,
        report_dir=args.report_dir,
        retention_trade_days=args.retention_trade_days,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=json_default))
    return 0 if report["result"] in {"PLAN_ONLY", "EXECUTE_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
