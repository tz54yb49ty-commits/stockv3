#!/usr/bin/env python3
"""Execute N3-B2 realtime projection metric run-once.

The runner requires explicit ``--execute`` and ``--user-confirmed`` flags. It
does one bounded projection fact write and exits. It does not write event
outbox rows, consume events, update MarketSnapshotUpdated payloads, start
workers, or enter downstream layers.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.realtime_projection_execute import (
    DEFAULT_B2_CONTRACT_JSON_PATH,
    DEFAULT_B2_DRY_RUN_JSON_PATH,
    DEFAULT_B2_JSON_REPORT_PATH,
    DEFAULT_B2_MD_REPORT_PATH,
    DEFAULT_B2_PREFLIGHT_JSON_PATH,
    DEFAULT_B2_ROLLBACK_SQL_PATH,
    run_realtime_projection_metric_execute,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = run_realtime_projection_metric_execute(
        dsn=args.dsn,
        contract_path=args.contract_path,
        preflight_path=args.preflight_path,
        dry_run_path=args.dry_run_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        rollback_sql_path=args.rollback_sql_path,
        projection_run_id=args.projection_run_id,
        for_trade_date=args.for_trade_date,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        progress_callback=print,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute N3-B2 realtime projection metric run-once.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", default=DEFAULT_B2_CONTRACT_JSON_PATH)
    parser.add_argument("--preflight-path", default=DEFAULT_B2_PREFLIGHT_JSON_PATH)
    parser.add_argument("--dry-run-path", default=DEFAULT_B2_DRY_RUN_JSON_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_B2_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_B2_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_B2_ROLLBACK_SQL_PATH)
    parser.add_argument("--projection-run-id", required=True)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--execute", action="store_true", help="Required explicit execute authorization.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required operator confirmation.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    actual = report["actual_projection_rows"]
    return "\n".join(
        [
            "realtime projection metric execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  projection_run_id={report['projection_run_id']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  projection_rows_written={write['projection_rows_written']}",
            f"  ready_by_asset={actual['ready_by_asset']}",
            f"  not_ready_by_asset={actual['not_ready_by_asset']}",
            f"  event_outbox_rows_written={write['event_outbox_rows_written']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  writes_outbox=false updates_market_snapshot_payload=false "
            "outbox_consumed=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
