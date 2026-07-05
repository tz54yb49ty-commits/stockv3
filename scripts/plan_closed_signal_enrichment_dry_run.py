#!/usr/bin/env python3
"""Build an N3-C2B closed signal enrichment dry-run report.

This script reads C2 closed 30m summaries and previous-day minute facts only.
It does not write enrichment rows, quality rows, run rows, outbox/inbox/
checkpoint rows, consume C3 outbox, enter downstream layers, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.closed_signal_enrichment_plan import (
    DEFAULT_C2_REPORT_PATH,
    DEFAULT_DRY_RUN_PLAN_PATH,
    DEFAULT_EXECUTE_CONTRACT_PATH,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MARKDOWN_REPORT_PATH,
    DEFAULT_N4_C3_REPLAY_REPORT_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    build_closed_signal_enrichment_dry_run,
    format_summary,
    write_report_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-C2B closed signal enrichment dry-run report.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected. C2B execute is not implemented here.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--dry-run-plan-path", default=DEFAULT_DRY_RUN_PLAN_PATH)
    parser.add_argument("--execute-contract-path", default=DEFAULT_EXECUTE_CONTRACT_PATH)
    parser.add_argument("--c2-report-path", default=DEFAULT_C2_REPORT_PATH)
    parser.add_argument("--n4-replay-report-path", default=DEFAULT_N4_C3_REPLAY_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-C2B dry-run runner rejects --execute. Business execute requires a later explicit gate.")

    report = build_closed_signal_enrichment_dry_run(
        dsn=args.dsn,
        dry_run_plan_path=args.dry_run_plan_path,
        execute_contract_path=args.execute_contract_path,
        c2_report_path=args.c2_report_path,
        n4_replay_report_path=args.n4_replay_report_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    write_report_files(report, markdown_path=args.report_path, json_path=args.json_report_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if not report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
