#!/usr/bin/env python3
"""Plan or execute additive previous-day full-context expansion subscription rows."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ashare_v3.market.previous_day_full_context_expansion_subscription_scope import (
    DEFAULT_DRY_RUN_JSON_PATH,
    DEFAULT_EXECUTE_JSON_PATH,
    DEFAULT_EXECUTE_MD_PATH,
    build_previous_day_full_context_expansion_scope_from_plan_path,
    build_previous_day_full_context_expansion_scope_from_db,
    format_dry_run_markdown,
    run_previous_day_full_context_expansion_subscription_scope_execute,
    write_scope_artifacts,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="N3 previous-day full-context expansion subscription scope gate.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--expansion-plan-path")
    parser.add_argument("--for-trade-date")
    parser.add_argument("--source-trade-date")
    parser.add_argument("--previous-trade-date")
    parser.add_argument("--expansion-run-id")
    parser.add_argument("--previous-day-expansion-run-id")
    parser.add_argument("--dry-run-path", default=DEFAULT_DRY_RUN_JSON_PATH)
    parser.add_argument("--report-path")
    parser.add_argument("--json-report-path", default=DEFAULT_EXECUTE_JSON_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_EXECUTE_MD_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.execute:
        if args.expansion_plan_path:
            parser.error("--expansion-plan-path is plan-only; execute still requires a reviewed dry-run artifact")
        report = run_previous_day_full_context_expansion_subscription_scope_execute(
            dsn=args.dsn,
            dry_run_path=args.dry_run_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    elif args.expansion_plan_path:
        required_args = (
            "for_trade_date",
            "source_trade_date",
            "previous_trade_date",
            "expansion_run_id",
            "previous_day_expansion_run_id",
        )
        missing = [name.replace("_", "-") for name in required_args if not getattr(args, name)]
        if missing:
            parser.error("--expansion-plan-path requires: " + ", ".join(f"--{name}" for name in missing))
        report = build_previous_day_full_context_expansion_scope_from_plan_path(
            dsn=args.dsn,
            expansion_plan_path=args.expansion_plan_path,
            for_trade_date=args.for_trade_date,
            source_trade_date=args.source_trade_date,
            previous_trade_date=args.previous_trade_date,
            expansion_run_id=args.expansion_run_id,
            previous_day_expansion_run_id=args.previous_day_expansion_run_id,
            include_rows=True,
        )
        json_path = args.json_report_path
        markdown_path = args.report_path or args.markdown_report_path
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        Path(markdown_path).parent.mkdir(parents=True, exist_ok=True)
        Path(markdown_path).write_text(format_dry_run_markdown(report), encoding="utf-8")
    else:
        report = build_previous_day_full_context_expansion_scope_from_db(dsn=args.dsn, include_rows=True)
        write_scope_artifacts(report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    elif args.execute:
        quality = report["quality"]
        write = report["write_result"]
        print(
            "\n".join(
                [
                    "N3 previous-day full-context expansion subscription scope execute",
                    f"  result={report['result']}",
                    f"  market_data_run_id={report['market_data_run_id']}",
                    f"  candidate_rows_written={write['candidate_rows_written']}",
                    f"  subscription_rows_written={write['subscription_rows_written']}",
                    f"  pull_plan_rows_written={write['pull_plan_rows_written']}",
                    f"  p0/p1/p2={quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
                    "  market_data_pulled=false market_data_fact_written=false event_outbox_written=false",
                ]
            )
        )
    else:
        print(format_dry_run_markdown(report))
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
