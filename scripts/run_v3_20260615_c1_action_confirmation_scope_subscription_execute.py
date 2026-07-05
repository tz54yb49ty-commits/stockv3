#!/usr/bin/env python3
"""Execute V3 20260615 C1 action-confirmation scoped subscription rows."""

from __future__ import annotations

import argparse
import os

from ashare_v3.market.v3_20260615_c1_action_scope_subscription_execute import (
    DEFAULT_DRY_RUN_PATH,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MARKDOWN_REPORT_PATH,
    run_scoped_subscription_execute,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--dry-run-path", default=DEFAULT_DRY_RUN_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        report = run_scoped_subscription_execute(
            dsn=args.dsn,
            dry_run_path=args.dry_run_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    write_result = report.get("write_result") or {}
    print(
        " ".join(
            [
                str(report.get("result")),
                f"run_id={report.get('market_data_run_id')}",
                f"subscriptions={write_result.get('subscription_rows_written')}",
                f"pull_plan={write_result.get('pull_plan_rows_written')}",
            ]
        )
    )
    return 0 if report.get("result") == "EXECUTE_PASS" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
