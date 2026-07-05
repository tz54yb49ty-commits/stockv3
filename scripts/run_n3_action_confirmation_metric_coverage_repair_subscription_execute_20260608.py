#!/usr/bin/env python3
"""Execute scoped subscription control rows for 20260608 N3 metric coverage repair."""

from __future__ import annotations

import argparse
import os

from ashare_v3.market.action_confirmation_metric_20260608_scoped_repair import (
    SUBSCRIPTION_DRY_RUN_JSON,
    SUBSCRIPTION_EXECUTE_REPORT_JSON,
    SUBSCRIPTION_EXECUTE_REPORT_MD,
    execute_subscription_control_rows,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run-path", default=SUBSCRIPTION_DRY_RUN_JSON)
    parser.add_argument("--json-report-path", default=SUBSCRIPTION_EXECUTE_REPORT_JSON)
    parser.add_argument("--markdown-report-path", default=SUBSCRIPTION_EXECUTE_REPORT_MD)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("ASHARE_V3_POSTGRES_DSN")
        or "host=127.0.0.1 port=5432 dbname=ashare_v3 user=ashare_v3_user",
        help="v3 runtime PostgreSQL DSN; defaults to local ashare_v3 without printing secrets",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = execute_subscription_control_rows(
        dsn=args.dsn,
        dry_run_path=args.dry_run_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
    )
    print(
        f"{report['result']} "
        f"run_id={report['market_data_run_id']} "
        f"subscriptions={(report.get('write_result') or {}).get('subscription_rows_written')} "
        f"pull_plan={(report.get('write_result') or {}).get('pull_plan_rows_written')}"
    )
    return 0 if report.get("result") == "EXECUTE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
