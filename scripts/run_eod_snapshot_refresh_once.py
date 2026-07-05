#!/usr/bin/env python3
"""Execute N3-EOD snapshot refresh once.

This runner is bounded and requires both ``--execute`` and
``--user-confirmed``. It writes only EOD run metadata, quality rows, EOD
snapshot facts, and EOD reconciliation facts.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.eod_snapshot_execute import (
    DEFAULT_EOD_CONTRACT_JSON_PATH,
    DEFAULT_EOD_JSON_REPORT_PATH,
    DEFAULT_EOD_MD_REPORT_PATH,
    DEFAULT_EOD_PREFLIGHT_JSON_PATH,
    DEFAULT_EOD_ROLLBACK_SQL_PATH,
    EodSnapshotExecuteError,
    run_eod_snapshot_execute,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        report = run_eod_snapshot_execute(
            dsn=args.dsn,
            contract_path=args.contract_path,
            preflight_path=args.preflight_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
            eod_run_id=args.eod_run_id,
            for_trade_date=args.for_trade_date,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            progress_callback=print,
        )
    except EodSnapshotExecuteError as exc:
        blocked = {
            "result": "BLOCKED",
            "stage": "N3-EOD-snapshot-refresh-execute",
            "layer_role": "N3_market_data",
            "reason": str(exc),
            "writes_performed": False,
            "writes_outbox": False,
            "outbox_consumed": False,
            "worker_started": False,
            "downstream_layers_touched": False,
        }
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("result") == "EXECUTED" else 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute N3-EOD snapshot refresh run-once.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", default=DEFAULT_EOD_CONTRACT_JSON_PATH)
    parser.add_argument("--preflight-path", default=DEFAULT_EOD_PREFLIGHT_JSON_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_EOD_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_EOD_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_EOD_ROLLBACK_SQL_PATH)
    parser.add_argument("--eod-run-id", required=True)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--execute", action="store_true", help="Required explicit execute authorization.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required operator confirmation.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    return parser


def format_summary(report: dict[str, Any]) -> str:
    quality = report.get("quality") or {}
    write = report.get("write_result") or {}
    return "\n".join(
        [
            "eod snapshot refresh execute",
            f"  result={report.get('result')}",
            f"  stage={report.get('stage')}",
            f"  layer_role={report.get('layer_role')}",
            f"  eod_run_id={report.get('eod_run_id')}",
            f"  for_trade_date={report.get('for_trade_date')}",
            f"  snapshot_rows_written={write.get('snapshot_rows_written')}",
            f"  snapshot_rows_by_asset={write.get('snapshot_rows_by_asset')}",
            f"  reconciliation_rows_written={write.get('reconciliation_rows_written')}",
            f"  quality_rows={write.get('quality_rows_written')}",
            f"  P0/P1/P2={quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
            "  writes_outbox=false outbox_consumed=false downstream_layers_touched=false worker_started=false",
            f"  rollback_sql_path={(report.get('paths') or {}).get('rollback_sql_path')}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
