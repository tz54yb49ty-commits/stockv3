#!/usr/bin/env python3
"""Run one bounded N3 intraday B1/C1/B2 supervisor pass."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os

from ashare_v3.market.intraday_supervisor import (
    DEFAULT_SUPERVISOR_JSON_REPORT_PATH,
    DEFAULT_SUPERVISOR_MD_REPORT_PATH,
    build_intraday_supervisor_plan,
    fetch_passed_market_data_run_ids,
    run_intraday_supervisor_plan,
    write_supervisor_report,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:
    DEFAULT_DSN = "postgresql://ashare_v3_user:ashare_v3_password@127.0.0.1:5432/ashare_v3"


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    passed_run_ids = set(args.passed_run_id)
    if not args.skip_db_watermark:
        prefixes = (
            f"realtime_daily_snapshot_{args.for_trade_date}_until_",
            f"today_minute_bar_1m_{args.for_trade_date}_until_",
            f"realtime_projection_metric_{args.for_trade_date}_until_",
        )
        passed_run_ids.update(
            fetch_passed_market_data_run_ids(
                dsn=args.dsn,
                for_trade_date=args.for_trade_date,
                run_id_prefixes=prefixes,
            )
        )

    plan = build_intraday_supervisor_plan(
        for_trade_date=args.for_trade_date,
        subscription_run_id=args.subscription_run_id,
        preload_run_id=args.preload_run_id,
        passed_run_ids=passed_run_ids,
        as_of=datetime.fromisoformat(args.as_of) if args.as_of else None,
        python_executable=args.python_executable,
        docs_root=args.docs_root,
        sql_root=args.sql_root,
    )
    if args.execute or args.user_confirmed:
        if not args.execute or not args.user_confirmed:
            plan["status"] = "blocked"
            plan["reason"] = "supervisor_execute_requires_user_confirmed"
            plan["child_step_results"] = []
            plan["executed_child_command_count"] = 0
        else:
            plan = run_intraday_supervisor_plan(plan)
    else:
        plan["child_step_results"] = []
        plan["executed_child_command_count"] = 0
        plan["execution_mode"] = "plan_only"

    write_supervisor_report(
        plan,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
    )
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(plan))
    return 0 if plan.get("status") in {"ready", "passed", "noop"} else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded N3 B1/C1/B2 intraday supervisor pass.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--subscription-run-id", required=True)
    parser.add_argument("--preload-run-id", required=True)
    parser.add_argument("--as-of", default="", help="Optional ISO datetime for deterministic planning.")
    parser.add_argument("--python-executable", default="python3")
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--passed-run-id", action="append", default=[])
    parser.add_argument("--skip-db-watermark", action="store_true")
    parser.add_argument("--json-report-path", default=DEFAULT_SUPERVISOR_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_SUPERVISOR_MD_REPORT_PATH)
    parser.add_argument("--execute", action="store_true", help="Run child commands when paired with --user-confirmed.")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def format_summary(report: dict[str, object]) -> str:
    return "\n".join(
        [
            "n3 intraday b1/c1/b2 supervisor",
            f"  status={report.get('status')}",
            f"  reason={report.get('reason')}",
            f"  for_trade_date={report.get('for_trade_date')}",
            f"  latest_closed_minute_hhmm={report.get('latest_closed_minute_hhmm')}",
            f"  child_steps={len(report.get('child_steps') or [])}",
            f"  executed_child_command_count={report.get('executed_child_command_count', 0)}",
            "  worker_started=false outbox_consumed_or_updated=false n4_n5_n6_entered=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
