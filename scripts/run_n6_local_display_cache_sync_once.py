#!/usr/bin/env python3
"""Run N6 local display cache sync once after final gate."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ashare_v3.user.local_display_cache_sync import (
    build_parser,
    format_summary,
    run_local_display_cache_sync,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_parser()
    parser.set_defaults(dsn=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args()

    report = run_local_display_cache_sync(
        dsn=args.dsn,
        cache_run_id=args.cache_run_id,
        cache_version=args.cache_version,
        source_condition_run_id=args.source_condition_run_id,
        source_trade_date=args.source_trade_date,
        mapping_strategy=args.mapping_strategy,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        contract_path=args.contract_path,
        preflight_path=args.preflight_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    if args.json_report_path:
        Path(args.json_report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if args.markdown_report_path:
        Path(args.markdown_report_path).write_text(format_summary(report) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("result") == "EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
