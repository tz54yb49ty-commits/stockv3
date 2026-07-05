#!/usr/bin/env python3
"""Generate N3-A1 previous-day minute execute contract and rollback SQL."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.preload_execute_contract import (
    DEFAULT_A0_REPORT_PATH,
    DEFAULT_A1_CONTRACT_JSON_PATH,
    DEFAULT_A1_CONTRACT_MD_PATH,
    DEFAULT_A1_PREFLIGHT_JSON_PATH,
    DEFAULT_A1_PREFLIGHT_MD_PATH,
    DEFAULT_A1_ROLLBACK_SQL_PATH,
    build_previous_day_minute_execute_contract,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate N3-A1 previous-day minute execute contract.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", required=True, help="N3-6 market_data_subscription source run id.")
    parser.add_argument("--a0-report-path", default=DEFAULT_A0_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_A1_CONTRACT_JSON_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_A1_CONTRACT_MD_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_A1_PREFLIGHT_JSON_PATH)
    parser.add_argument("--preflight-markdown-path", default=DEFAULT_A1_PREFLIGHT_MD_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_A1_ROLLBACK_SQL_PATH)
    parser.add_argument("--preload-run-id", default="", help="Optional explicit N3-A1 preload_run_id.")
    parser.add_argument("--json", action="store_true", help="Print full JSON contract.")
    args = parser.parse_args()

    contract = build_previous_day_minute_execute_contract(
        dsn=args.dsn,
        market_data_run_id=args.run_id,
        a0_report_path=args.a0_report_path,
        contract_json_path=args.json_report_path,
        contract_markdown_path=args.markdown_report_path,
        rollback_sql_path=args.rollback_sql_path,
        preflight_json_path=args.preflight_json_path,
        preflight_markdown_path=args.preflight_markdown_path,
        preload_run_id=args.preload_run_id or None,
    )

    if args.json:
        print(json.dumps(contract, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(contract))
    return 0 if int(contract["quality"]["p0_count"]) == 0 else 2


def format_summary(contract: dict[str, Any]) -> str:
    quality = contract["quality"]
    return "\n".join(
        [
            "previous-day minute execute contract",
            f"  stage={contract['stage']}",
            f"  layer_role={contract['layer_role']}",
            f"  source_run_id={contract['source_run_id']}",
            f"  preload_run_id={contract['preload_run_id']}",
            f"  previous_day_minute_date={contract['previous_day_minute_date']}",
            f"  expected_row_count={contract['expected_row_count']}",
            f"  expected_asset_counts={contract['expected_asset_counts']}",
            f"  target_tables={contract['target_tables']}",
            f"  writes_outbox={contract['writes_outbox']}",
            f"  rollback_sql_path={contract['rollback_sql_path']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  market_data_pulled=false market_data_fact_written=false event_outbox_written=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
