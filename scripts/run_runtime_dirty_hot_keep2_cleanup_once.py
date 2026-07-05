#!/usr/bin/env python3
"""Plan or execute dirty runtime hot-store keep-2 cleanup.

Default mode is plan-only. Execute mode requires the explicit confirmation
token and deletes only PostgreSQL runtime rows selected by the saved plan.
It never removes local files, MacRaid archives, launchd state, or workers.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from ashare_v3.ingestion.runtime_archive_execute import DEFAULT_DSN
from ashare_v3.ingestion.runtime_hot_cleanup import (
    CONFIRM_TOKEN,
    DEFAULT_CLOSEOUT_PATH,
    DEFAULT_PLAN_PATH,
    RuntimeHotCleanupSpec,
    build_keep2_dirty_hot_cleanup_plan,
    execute_keep2_dirty_hot_cleanup,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_REPORT_DIR = "docs/runtime_archive/dirty_hot_cleanup"


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def run_runtime_dirty_hot_keep2_cleanup_once(
    *,
    dsn: str = DEFAULT_DSN,
    report_dir: str | Path = DEFAULT_REPORT_DIR,
    execute: bool = False,
    confirm_token: str = "",
    trade_dates: Iterable[str] | None = None,
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    table_deleter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
) -> dict[str, Any]:
    report_root = Path(report_dir)
    plan_path = report_root / "keep2_cleanup_plan.json"
    closeout_path = report_root / "keep2_cleanup_closeout.json"
    plan = build_keep2_dirty_hot_cleanup_plan(
        dsn=dsn,
        trade_dates=trade_dates,
        plan_path=plan_path,
        table_counter=table_counter,
    )
    if execute:
        report = execute_keep2_dirty_hot_cleanup(
            plan_path=plan_path,
            confirm_token=confirm_token,
            dsn=dsn,
            closeout_path=closeout_path,
            current_trade_dates=trade_dates,
            table_counter=table_counter,
            table_deleter=table_deleter,
        )
    else:
        report = plan
    report = {
        **report,
        "stage": "V3_RUNTIME_DIRTY_HOT_KEEP2_CLEANUP_ONCE",
        "execute": bool(execute),
        "required_confirm_token": CONFIRM_TOKEN,
        "docs_report_path": str(report_root / "keep2_cleanup_status.json"),
    }
    write_json(report["docs_report_path"], report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-token", default="")
    return parser.parse_args()


def is_success_result(result: str) -> bool:
    return result in {
        "DIRTY_HOT_KEEP2_CLEANUP_PLAN_PASS",
        "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS",
    }


def main() -> int:
    args = parse_args()
    report = run_runtime_dirty_hot_keep2_cleanup_once(
        dsn=args.dsn,
        report_dir=args.report_dir,
        execute=args.execute,
        confirm_token=args.confirm_token,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=json_default))
    return 0 if is_success_result(str(report["result"])) else 2


if __name__ == "__main__":
    raise SystemExit(main())
