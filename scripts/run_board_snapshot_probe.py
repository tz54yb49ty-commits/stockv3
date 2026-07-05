#!/usr/bin/env python3
"""Run a read-only N3-B1 board realtime snapshot probe."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.board_snapshot_probe import (
    DEFAULT_BOARD_SNAPSHOT_PROBE_JSON_PATH,
    run_board_snapshot_probe,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = run_board_snapshot_probe(
        dsn=args.dsn,
        run_id=args.run_id,
        limit=args.limit,
        timeout_seconds=args.timeout,
        json_output_path=args.json_output,
    )
    print(format_summary(report))
    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 2 if report["probe_status"] == "BLOCKED" else 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only probe for TDX 881xxx board snapshot readiness.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--limit", type=int, default=10, help="Number of board subscriptions to sample; 0 checks all.")
    parser.add_argument("--timeout", type=int, default=30, help="DB/socket timeout in seconds.")
    parser.add_argument("--json-output", default=DEFAULT_BOARD_SNAPSHOT_PROBE_JSON_PATH)
    parser.add_argument("--print-json", action="store_true", help="Also print the full report JSON.")
    return parser


def format_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return "\n".join(
        [
            "board snapshot probe",
            f"  status={report['probe_status']}",
            f"  run_id={report['run_id']}",
            f"  trade_date={report['trade_date']}",
            f"  total_available={summary['total_available']}",
            f"  total_checked={summary['total_checked']}",
            f"  ready_count={summary['ready_count']}",
            f"  missing_count={summary['missing_count']}",
            f"  stale_count={summary['stale_count']}",
            f"  error_count={summary['error_count']}",
            f"  all_ready={summary['all_ready']}",
            f"  earliest_tail_datetime={summary['earliest_tail_datetime']}",
            f"  latest_tail_datetime={summary['latest_tail_datetime']}",
            f"  database_written={report['side_effects']['database_written']}",
            f"  common_event_outbox_written={report['side_effects']['common_event_outbox_written']}",
            f"  downstream_layers_touched={report['side_effects']['downstream_layers_touched']}",
            f"  worker_started={report['side_effects']['worker_started']}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
