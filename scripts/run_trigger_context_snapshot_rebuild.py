#!/usr/bin/env python3
"""Rebuild N4 trigger_context_snapshot for a refreshed N2/N3 lineage.

This writes only N4 context localization rows. It does not consume real N3
events, write trigger_state/trigger_match/outbox rows, pull market data, start
workers, or enter N5/N6.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.context_execute import run_trigger_context_snapshot_execute
from check_condition_source_ready import DEFAULT_DSN


DEFAULT_CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260525003855_execute"
DEFAULT_MARKET_DATA_RUN_ID = (
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525003855_execute"
)
DEFAULT_JSON_REPORT_PATH = "docs/N4_R4_trigger_context_rebuild_report.json"
DEFAULT_MD_REPORT_PATH = "docs/N4_R4_TRIGGER_CONTEXT_REBUILD_REPORT.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N4_R4_trigger_context_rebuild_rollback.sql"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild N4 trigger context snapshot from refreshed N2/N3 runs.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--condition-run-id", default=DEFAULT_CONDITION_RUN_ID)
    parser.add_argument("--market-data-run-id", default=DEFAULT_MARKET_DATA_RUN_ID)
    parser.add_argument(
        "--market-subscription-run-id",
        default="",
        help="Optional N3 subscription run used only to attach source_market_subscription_id traces.",
    )
    parser.add_argument("--for-trade-date", default="20260525")
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_trigger_context_snapshot_execute(
        dsn=args.dsn,
        condition_run_id=args.condition_run_id,
        market_data_run_id=args.market_data_run_id,
        market_subscription_run_id=args.market_subscription_run_id or None,
        for_trade_date=args.for_trade_date,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        rollback_sql_path=args.rollback_sql_path,
        allow_existing_context_for_trade_date=True,
        expected_condition_run_id=args.condition_run_id,
        stage="N4-R4",
        execution_mode="trigger_context_snapshot_rebuild_from_n2_r4_n3_r4",
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    summary = report["post_context_summary"]
    return "\n".join(
        [
            "trigger context snapshot rebuild",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  run_id={report['run_id']}",
            f"  source_condition_run_id={report['source_condition_run_id']}",
            f"  source_market_data_run_id={report['source_market_data_run_id']}",
            f"  context_row_count={summary['row_count']}",
            f"  row_count_by_asset_kind={summary['row_count_by_asset_kind']}",
            f"  buy_hint_row_count={summary['buy_hint_row_count']}",
            f"  sell_hint_row_count={summary['sell_hint_row_count']}",
            f"  period_trigger_baseline_json_missing={summary.get('period_trigger_baseline_json_missing')}",
            f"  required_period_not_ready_rows={summary.get('required_period_not_ready_rows')}",
            f"  source_market_subscription_id_nonnull_count={summary.get('source_market_subscription_id_nonnull_count')}",
            f"  common_event_outbox_before={report['before_row_counts']['common_event_outbox']['row_count']}",
            f"  common_event_outbox_after={report['after_row_counts']['common_event_outbox']['row_count']}",
            f"  rollback_sql_path={report['rollback_sql_path']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  trigger_state_written=false trigger_match_written=false event_outbox_written=false",
            "  market_data_pulled=false n3_event_consumed=false worker_started=false downstream_layers_touched=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
