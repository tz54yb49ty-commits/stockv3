#!/usr/bin/env python3
"""CLI for reviewed scoped N3 subscription control-row manifests."""

from __future__ import annotations

import argparse

from ashare_v3.market.scoped_subscription_control_execute import (
    run_scoped_subscription_control_execute,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run-path", required=True)
    parser.add_argument("--expected-run-id")
    parser.add_argument("--rollback-sql-path")
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--markdown-report-path", required=True)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_scoped_subscription_control_execute(
        dsn=args.dsn,
        dry_run_path=args.dry_run_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        expected_run_id=args.expected_run_id,
        rollback_sql_path=args.rollback_sql_path,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
    )
    print(f"scoped subscription control execute result={report['result']} run_id={report['market_data_run_id']}")


if __name__ == "__main__":
    main()
