#!/usr/bin/env python3
"""Execute N3-B1 realtime daily snapshot run-once.

This runner requires explicit ``--execute`` and ``--user-confirmed`` flags. It
does one bounded pass over the reviewed B1 contract subscriptions, then exits.
It does not start workers or enter downstream layers.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.realtime_snapshot_execute import (
    DEFAULT_N3_B1_JSON_REPORT_PATH,
    DEFAULT_N3_B1_MD_REPORT_PATH,
    DEFAULT_N3_B1_POST_BACKUP_PATH,
    DEFAULT_N3_B1_PRE_BACKUP_PATH,
    run_realtime_daily_snapshot_execute,
)
from ashare_v3.market.realtime_snapshot_execute_contract import DEFAULT_B1_CONTRACT_JSON_PATH
from ashare_v3.market.realtime_snapshot_execute_readiness import DEFAULT_B1_READINESS_JSON_PATH
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = run_realtime_daily_snapshot_execute(
        dsn=args.dsn,
        contract_path=args.contract_path,
        readiness_path=args.readiness_path,
        pre_backup_path=args.pre_backup_path,
        post_backup_path=args.post_backup_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        for_trade_date=args.for_trade_date or None,
        snapshot_run_id=args.snapshot_run_id or None,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        no_outbox=resolve_no_outbox(args),
        allow_outbox=resolve_allow_outbox(args),
        pre_open_source_policy=args.pre_open_source_policy,
        progress_callback=print,
        progress_every=args.progress_every,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute N3-B1 realtime daily snapshot run-once.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", default=DEFAULT_B1_CONTRACT_JSON_PATH)
    parser.add_argument("--readiness-path", default=DEFAULT_B1_READINESS_JSON_PATH)
    parser.add_argument("--pre-backup-path", default=DEFAULT_N3_B1_PRE_BACKUP_PATH)
    parser.add_argument("--post-backup-path", default=DEFAULT_N3_B1_POST_BACKUP_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N3_B1_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N3_B1_MD_REPORT_PATH)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--snapshot-run-id", required=True)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--execute", action="store_true", help="Required explicit execute authorization.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required operator confirmation.")
    parser.add_argument("--no-outbox", action="store_true", help="Required for fact-only B1 contracts.")
    parser.add_argument(
        "--pre-open-source-policy",
        action="store_true",
        help="Required when the contract uses pre_open_fact_only source-time policy.",
    )
    parser.add_argument(
        "--writes-outbox",
        choices=("true", "false"),
        default="",
        help=(
            "Explicit outbox policy. Use --writes-outbox=true only with a reviewed "
            "writes_outbox=true contract; use --writes-outbox=false as an alias for --no-outbox."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def resolve_no_outbox(args: argparse.Namespace) -> bool:
    if args.no_outbox and args.writes_outbox == "true":
        raise SystemExit("N3-B1 blocked: --no-outbox conflicts with --writes-outbox=true")
    if args.writes_outbox == "false":
        return True
    if args.writes_outbox == "true":
        return False
    return bool(args.no_outbox)


def resolve_allow_outbox(args: argparse.Namespace) -> bool:
    if args.no_outbox and args.writes_outbox == "true":
        raise SystemExit("N3-B1 blocked: --no-outbox conflicts with --writes-outbox=true")
    return args.writes_outbox == "true"


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    return "\n".join(
        [
            "realtime daily snapshot execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  source_run_id={report['source_run_id']}",
            f"  snapshot_run_id={report['snapshot_run_id']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  objects_processed={write['objects_processed']}",
            f"  snapshot_rows_written={write['snapshot_rows_written']}",
            f"  quality_item_rows_written={write['quality_item_rows_written']}",
            f"  event_outbox_rows_written={write['event_outbox_rows_written']}",
            f"  writes_outbox={report.get('writes_outbox')}",
            f"  generated_outbox_events={report.get('generated_outbox_events')}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  "
            f"market_data_pulled={report['side_effects']['market_data_pulled']} "
            f"realtime_snapshot_written={report['side_effects']['realtime_snapshot_written']} "
            f"event_outbox_written={report['side_effects']['event_outbox_written']} "
            "downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
