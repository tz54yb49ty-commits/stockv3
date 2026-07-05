#!/usr/bin/env python3
"""Run one N5 provisional ActionEligible invocation."""

from __future__ import annotations

import argparse
import json
import os
import sys

from ashare_v3.action.provisional_action_eligible import (
    ProvisionalActionEligibleBlocked,
    run_provisional_actioneligible_once,
)


DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run N5 provisional ActionEligible once.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--source-trigger-run-id", required=True)
    parser.add_argument("--action-run-id", required=True)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--consumer-name", default="n5_provisional_actioneligible_once")
    parser.add_argument("--json-report-path", default=None)
    parser.add_argument("--markdown-report-path", default=None)
    parser.add_argument("--rollback-sql-path", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run_provisional_actioneligible_once(
            dsn=args.dsn,
            source_trigger_run_id=args.source_trigger_run_id,
            action_run_id=args.action_run_id,
            for_trade_date=args.for_trade_date,
            consumer_name=args.consumer_name,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
        )
    except ProvisionalActionEligibleBlocked as exc:
        report = {
            "result": "BLOCKED",
            "reason": str(exc),
            "source_trigger_run_id": args.source_trigger_run_id,
            "action_run_id": args.action_run_id,
            "execute": args.execute,
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
