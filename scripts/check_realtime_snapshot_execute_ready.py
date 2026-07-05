#!/usr/bin/env python3
"""Read-only N3-B1 realtime snapshot execute readiness gate."""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.realtime_snapshot_execute_contract import DEFAULT_B1_CONTRACT_JSON_PATH
from ashare_v3.market.realtime_snapshot_execute_readiness import (
    DEFAULT_B1_READINESS_JSON_PATH,
    DEFAULT_B1_READINESS_MD_PATH,
    build_realtime_snapshot_execute_readiness,
    format_realtime_snapshot_readiness_summary,
    write_readiness_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Check N3-B1 realtime snapshot execute readiness.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", required=True, help="N3-6 market_data_subscription source run id.")
    parser.add_argument("--contract-path", default=DEFAULT_B1_CONTRACT_JSON_PATH)
    parser.add_argument("--preload-run-id", default="", help="Optional explicit N3-A1 preload run id.")
    parser.add_argument("--current-date", default="", help="Override current date in YYYYMMDD for tests/replay.")
    parser.add_argument("--allow-repeat-idempotent", action="store_true", help="Allow an explicit idempotent repeat gate warning.")
    parser.add_argument("--markdown-report-path", default=DEFAULT_B1_READINESS_MD_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_B1_READINESS_JSON_PATH)
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print full JSON readiness report.")
    parser.add_argument("--exit-zero", action="store_true", help="Return 0 even when readiness is blocked.")
    parser.add_argument("--execute", action="store_true", help="Rejected. This script is read-only.")
    args = parser.parse_args()

    if args.execute:
        parser.error("readiness gate is read-only and never executes realtime snapshot writes")

    report = build_realtime_snapshot_execute_readiness(
        dsn=args.dsn,
        market_data_run_id=args.run_id,
        contract_path=args.contract_path,
        preload_run_id=args.preload_run_id or None,
        current_date=args.current_date or None,
        allow_repeat_idempotent=args.allow_repeat_idempotent,
    )
    if not args.no_write_report:
        write_readiness_files(
            report,
            markdown_path=args.markdown_report_path,
            json_path=args.json_report_path,
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_realtime_snapshot_readiness_summary(report))

    if args.exit_zero:
        return 0
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
