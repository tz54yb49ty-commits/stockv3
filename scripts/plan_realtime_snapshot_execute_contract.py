#!/usr/bin/env python3
"""Generate N3-B1 realtime daily snapshot execute contract and rollback SQL."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.realtime_snapshot_execute_contract import (
    DEFAULT_B1_CONTRACT_JSON_PATH,
    DEFAULT_B1_CONTRACT_MD_PATH,
    DEFAULT_B1_ROLLBACK_SQL_PATH,
    DEFAULT_N3_B0_JSON_REPORT_PATH,
    build_realtime_snapshot_execute_contract,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate N3-B1 realtime snapshot execute contract.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", required=True, help="N3-6 market_data_subscription source run id.")
    parser.add_argument("--b0-report-path", default=DEFAULT_N3_B0_JSON_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_B1_CONTRACT_JSON_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_B1_CONTRACT_MD_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_B1_ROLLBACK_SQL_PATH)
    parser.add_argument("--snapshot-run-id", default="", help="Optional explicit N3-B1 snapshot_run_id.")
    parser.add_argument(
        "--publish-display-event",
        action="store_true",
        help="Include MarketDisplaySnapshotUpdated in the B1 default outbox set. Default is disabled.",
    )
    parser.add_argument(
        "--no-writes-outbox",
        action="store_true",
        help="Generate a B1 fact-only execute contract with writes_outbox=false.",
    )
    parser.add_argument(
        "--pre-open-source-policy",
        action="store_true",
        help="Allow reviewed pre-open fact-only snapshot rows with source_time_missing_or_preopen P1 quality.",
    )
    parser.add_argument(
        "--source-returned-time-policy",
        action="store_true",
        help="Generate a B1 source_returned_time contract; source-returned trade date is authoritative.",
    )
    parser.add_argument("--execute", action="store_true", help="Rejected in N3-B1-preflight.")
    parser.add_argument("--json", action="store_true", help="Print full JSON contract.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-B1-preflight only generates a contract. Realtime snapshot execute requires explicit later confirmation.")

    contract = build_realtime_snapshot_execute_contract(
        dsn=args.dsn,
        market_data_run_id=args.run_id,
        b0_report_path=args.b0_report_path,
        contract_json_path=args.json_report_path,
        contract_markdown_path=args.markdown_report_path,
        rollback_sql_path=args.rollback_sql_path,
        snapshot_run_id=args.snapshot_run_id or None,
        publish_display_event=args.publish_display_event,
        writes_outbox=not args.no_writes_outbox,
        pre_open_source_policy=args.pre_open_source_policy,
        source_returned_time_policy=args.source_returned_time_policy,
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
            "realtime daily snapshot execute contract",
            f"  stage={contract['stage']}",
            f"  layer_role={contract['layer_role']}",
            f"  source_run_id={contract['source_run_id']}",
            f"  snapshot_run_id={contract['snapshot_run_id']}",
            f"  for_trade_date={contract['for_trade_date']}",
            f"  expected_row_count={contract['expected_row_count']}",
            f"  expected_asset_counts={contract['expected_asset_counts']}",
            f"  target_tables={contract['target_tables']}",
            f"  writes_outbox={contract['writes_outbox']}",
            f"  source_time_policy={contract.get('source_time_policy')}",
            f"  writes_market_display_snapshot_updated={contract['writes_market_display_snapshot_updated']}",
            f"  rollback_sql_path={contract['rollback_sql_path']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  market_data_pulled=false realtime_snapshot_written=false event_outbox_written=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
