#!/usr/bin/env python3
"""Run one N4P ordinary provisional execute invocation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from ashare_v3.trigger.provisional_ordinary_execute import (
    N4POrdinaryExecuteBlocked,
    run_provisional_ordinary_once,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run N4P ordinary provisional execute once.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", ""))
    parser.add_argument("--trigger-context-run-id", required=True)
    parser.add_argument("--source-metric-run-id", required=True)
    parser.add_argument("--trigger-run-id", required=True)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--source-condition-run-id", required=True)
    parser.add_argument("--json-report-path")
    parser.add_argument("--markdown-report-path")
    parser.add_argument("--rollback-sql-path")
    parser.add_argument("--previous-trigger-run-id")
    parser.add_argument("--baseline-mode")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = run_provisional_ordinary_once(
            dsn=args.dsn,
            trigger_context_run_id=args.trigger_context_run_id,
            source_metric_run_id=args.source_metric_run_id,
            trigger_run_id=args.trigger_run_id,
            for_trade_date=args.for_trade_date,
            source_condition_run_id=args.source_condition_run_id,
            previous_trigger_run_id=args.previous_trigger_run_id,
            baseline_mode=args.baseline_mode,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
        )
    except N4POrdinaryExecuteBlocked as exc:
        payload: dict[str, Any] = {"result": "BLOCKED", "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(f"result={report.get('result')} trigger_run_id={report.get('trigger_run_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
