#!/usr/bin/env python3
"""Execute N3-6 market_data_subscription / pull_plan control-row persist."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from ashare_v3.market.subscription_execute import (
    DEFAULT_N3_6_JSON_REPORT_PATH,
    DEFAULT_N3_6_MD_REPORT_PATH,
    DEFAULT_N3_6_POST_BACKUP_PATH,
    DEFAULT_N3_6_PRE_BACKUP_PATH,
    run_market_data_subscription_execute,
)
from check_condition_source_ready import DEFAULT_DSN


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute N3-6 subscription/pull_plan control-row persist.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", default="", help="Explicit N2 condition run id.")
    parser.add_argument("--source-condition-run-id", default="", help="Explicit N2 condition run id alias.")
    parser.add_argument("--source-trade-date", default="", help="Optional source_trade_date filter, e.g. 20260522.")
    parser.add_argument("--for-trade-date", default="", help="Optional for_trade_date filter, e.g. 20260525.")
    parser.add_argument("--market-data-run-id", default="", help="Optional explicit N3 market_data_run_id.")
    parser.add_argument("--pre-backup-path", default=DEFAULT_N3_6_PRE_BACKUP_PATH)
    parser.add_argument("--post-backup-path", default=DEFAULT_N3_6_POST_BACKUP_PATH)
    parser.add_argument("--json-report-path", default="")
    parser.add_argument("--report-path", default="", help="JSON report path alias.")
    parser.add_argument("--markdown-report-path", default=DEFAULT_N3_6_MD_REPORT_PATH)
    parser.add_argument("--execute", action="store_true", help="Required explicit write authorization.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required manual confirmation flag.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args(argv)

    block_reason = validate_execute_guard(args)
    if block_reason:
        print(block_reason, file=sys.stderr)
        return 2

    condition_run_id = resolve_alias(
        primary_value=args.run_id,
        alias_value=args.source_condition_run_id,
        primary_name="--run-id",
        alias_name="--source-condition-run-id",
    )
    json_report_path = resolve_alias(
        primary_value=args.json_report_path,
        alias_value=args.report_path,
        primary_name="--json-report-path",
        alias_name="--report-path",
    ) or DEFAULT_N3_6_JSON_REPORT_PATH

    report = run_market_data_subscription_execute(
        dsn=args.dsn,
        condition_run_id=condition_run_id or None,
        source_trade_date=args.source_trade_date or None,
        for_trade_date=args.for_trade_date or None,
        execute_run_id=args.market_data_run_id or None,
        pre_backup_path=args.pre_backup_path,
        post_backup_path=args.post_backup_path,
        json_report_path=json_report_path,
        markdown_report_path=args.markdown_report_path,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def validate_execute_guard(args: argparse.Namespace) -> str:
    missing: list[str] = []
    if not args.execute:
        missing.append("--execute")
    if not args.user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        return "N3-6 subscription execute blocked before DB write: missing " + " and ".join(missing)
    try:
        resolve_alias(
            primary_value=args.run_id,
            alias_value=args.source_condition_run_id,
            primary_name="--run-id",
            alias_name="--source-condition-run-id",
        )
        resolve_alias(
            primary_value=args.json_report_path,
            alias_value=args.report_path,
            primary_name="--json-report-path",
            alias_name="--report-path",
        )
    except ValueError as exc:
        return f"N3-6 subscription execute blocked before DB write: {exc}"
    return ""


def resolve_alias(*, primary_value: str, alias_value: str, primary_name: str, alias_name: str) -> str:
    primary = primary_value or ""
    alias = alias_value or ""
    if primary and alias and primary != alias:
        raise ValueError(f"{primary_name} and {alias_name} disagree")
    return alias or primary


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    checks = report["post_checks"]
    return "\n".join(
        [
            "market data subscription execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  market_data_run_id={report['market_data_run_id']}",
            f"  source_condition_run_id={report['source_condition_run_id']}",
            f"  source_scope_row_count={report['dry_run_summary']['source_scope_row_count']}",
            f"  candidate_rows_written={write['candidate_rows_written']}",
            f"  subscription_rows_written={write['subscription_rows_written']}",
            f"  pull_plan_rows_written={write['pull_plan_rows_written']}",
            f"  quality_item_rows_written={write['quality_item_rows_written']}",
            f"  market_data_fact_rows_written={write['market_data_fact_rows_written']}",
            f"  event_outbox_rows_written={write['event_outbox_rows_written']}",
            f"  n1_n2_active_snapshot_unchanged={checks['n3_6_n1_n2_active_snapshot_unchanged']}",
            f"  no_market_fact_or_event_rows_written={checks['n3_6_no_market_fact_or_event_rows_written']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  market_data_pulled=false market_data_fact_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
