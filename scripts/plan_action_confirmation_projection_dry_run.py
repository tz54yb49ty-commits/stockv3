#!/usr/bin/env python3
"""Build N3 action-confirmation projection writer would-write dry-run reports.

This script is read-only against PostgreSQL. It materializes no metric facts,
does not create common_market_data_run or quality rows, does not write or
consume outbox/inbox/checkpoint rows, does not pull market data, and does not
enter N4/N5/N6.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.action_confirmation_projection_plan import (
    DEFAULT_DRY_RUN_JSON_PATH,
    DEFAULT_DRY_RUN_MARKDOWN_PATH,
    DEFAULT_DRY_RUN_PREFLIGHT_JSON_PATH,
    DEFAULT_DRY_RUN_PREFLIGHT_MARKDOWN_PATH,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    build_action_confirmation_projection_dry_run_from_db,
    build_dry_run_execute_preflight_report,
    format_summary,
    write_dry_run_report_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3 action-confirmation projection writer dry-run report.")
    parser.add_argument("--execute", action="store_true", help="Rejected. This runner is read-only.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--readiness-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--report-path", default=DEFAULT_DRY_RUN_MARKDOWN_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_DRY_RUN_JSON_PATH)
    parser.add_argument("--preflight-report-path", default=DEFAULT_DRY_RUN_PREFLIGHT_MARKDOWN_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_DRY_RUN_PREFLIGHT_JSON_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3 action-confirmation projection dry-run rejects --execute. Business writes require a later explicit gate.")

    dry_run_report = build_action_confirmation_projection_dry_run_from_db(
        dsn=args.dsn,
        readiness_path=args.readiness_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    execute_preflight = build_dry_run_execute_preflight_report(dry_run_report)
    write_dry_run_report_files(
        dry_run_report,
        json_path=args.json_report_path,
        markdown_path=args.report_path,
        preflight_json_path=args.preflight_json_path,
        preflight_markdown_path=args.preflight_report_path,
    )

    if args.json:
        print(json.dumps({"dry_run": dry_run_report, "preflight": execute_preflight}, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(dry_run_report))
        print(f"preflight={execute_preflight['result']}")
    return 0 if not dry_run_report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
