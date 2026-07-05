#!/usr/bin/env python3
"""Plan N3 C1 full-context expansion subscription control rows."""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.full_context_expansion_subscription_plan import (
    DEFAULT_C1_PREFLIGHT_JSON_PATH,
    DEFAULT_C1_PREFLIGHT_MD_PATH,
    DEFAULT_CONTRACT_JSON_PATH,
    DEFAULT_CONTRACT_MD_PATH,
    DEFAULT_DRY_RUN_JSON_PATH,
    DEFAULT_DRY_RUN_MD_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    DEFAULT_PREFLIGHT_MD_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    build_full_context_expansion_subscription_scope_from_db,
    write_artifacts,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan N3 full-context expansion subscription scope.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute", action="store_true", help="Rejected: this planner is read-only.")
    parser.add_argument("--no-include-rows", action="store_true")
    parser.add_argument("--for-trade-date")
    parser.add_argument("--source-condition-run-id")
    parser.add_argument("--source-subscription-run-id")
    parser.add_argument("--source-snapshot-run-id")
    parser.add_argument("--trigger-context-run-id")
    parser.add_argument("--expansion-run-id")
    parser.add_argument("--scope-mode", choices=("full-context-all", "gap-only"), default="gap-only")
    parser.add_argument("--dry-run-json-path", default=DEFAULT_DRY_RUN_JSON_PATH)
    parser.add_argument("--dry-run-markdown-path", default=DEFAULT_DRY_RUN_MD_PATH)
    parser.add_argument("--contract-json-path", default=DEFAULT_CONTRACT_JSON_PATH)
    parser.add_argument("--contract-markdown-path", default=DEFAULT_CONTRACT_MD_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--preflight-markdown-path", default=DEFAULT_PREFLIGHT_MD_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--c1-preflight-json-path", default=DEFAULT_C1_PREFLIGHT_JSON_PATH)
    parser.add_argument("--c1-preflight-markdown-path", default=DEFAULT_C1_PREFLIGHT_MD_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.execute:
        parser.error("This planner is read-only. Execute requires scripts/run_full_context_expansion_subscription_execute.py.")

    report = build_full_context_expansion_subscription_scope_from_db(
        dsn=args.dsn,
        include_rows=not args.no_include_rows,
        for_trade_date=args.for_trade_date or "20260603",
        source_condition_run_id=args.source_condition_run_id or "condition_layer_20260602_source_20260602_v1",
        source_subscription_run_id=args.source_subscription_run_id or "market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
        source_snapshot_run_id=args.source_snapshot_run_id or "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
        trigger_context_run_id=args.trigger_context_run_id or "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1",
        expansion_run_id=args.expansion_run_id
        or "market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1",
        scope_mode=args.scope_mode,
    )
    paths = write_artifacts(
        report,
        dry_run_json_path=args.dry_run_json_path,
        dry_run_markdown_path=args.dry_run_markdown_path,
        contract_json_path=args.contract_json_path,
        contract_markdown_path=args.contract_markdown_path,
        preflight_json_path=args.preflight_json_path,
        preflight_markdown_path=args.preflight_markdown_path,
        rollback_sql_path=args.rollback_sql_path,
        c1_preflight_json_path=args.c1_preflight_json_path,
        c1_preflight_markdown_path=args.c1_preflight_markdown_path,
    )
    summary = {
        "result": "IMPLEMENTATION_PASS" if report["passed"] else "BLOCKED",
        "market_data_run_id": report["market_data_run_id"],
        "candidate_rows": report["candidate_row_count"],
        "subscription_rows": report["subscription_row_count"],
        "pull_plan_rows": report["market_data_pull_plan_row_count"],
        "objects": report["object_count_by_asset_kind"],
        "expected_minute_rows": report["expected_minute_rows_by_asset_kind"],
        "p0_p1_p2": [
            report["quality"]["p0_count"],
            report["quality"]["p1_count"],
            report["quality"]["p2_count"],
        ],
        "paths": paths,
    }
    print(json.dumps(report if args.json else summary, ensure_ascii=False, indent=2, default=str))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
