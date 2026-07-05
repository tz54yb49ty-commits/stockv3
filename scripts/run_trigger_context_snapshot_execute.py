#!/usr/bin/env python3
"""Execute N4-3 trigger_context_snapshot localization.

This writes only N4 trigger_run, trigger_context_snapshot, and
trigger_quality_item rows. It never consumes N3 events, writes outbox trigger
events, pulls market data, starts workers, or enters N5/N6.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.context_execute import (
    DEFAULT_N4_3_JSON_REPORT_PATH,
    DEFAULT_N4_3_MD_REPORT_PATH,
    DEFAULT_N4_3_ROLLBACK_SQL_PATH,
    EXPECTED_CONDITION_RUN_ID,
    run_trigger_context_snapshot_execute,
)
from check_condition_source_ready import DEFAULT_DSN


class TriggerContextExecuteBlocked(RuntimeError):
    """Raised when N4 context execute is not explicitly authorized."""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute N4-3 trigger context snapshot localization.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--condition-run-id", default=EXPECTED_CONDITION_RUN_ID)
    parser.add_argument("--for-trade-date", default="20260525")
    parser.add_argument("--json-report-path", default=DEFAULT_N4_3_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N4_3_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_N4_3_ROLLBACK_SQL_PATH)
    parser.add_argument(
        "--allow-existing-context-for-trade-date",
        action="store_true",
        help=(
            "Allow a new same-trade-date context run only when the target run_id/source_condition_run_id "
            "are explicitly isolated. The default remains to block when active context exists."
        ),
    )
    parser.add_argument("--execute", action="store_true", help="Execute the context refresh write path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Confirm the manual execute gate.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def assert_context_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise TriggerContextExecuteBlocked(
            "N4 trigger context snapshot execute blocked before DB write: missing " + ", ".join(missing)
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        assert_context_execute_confirmed(execute=args.execute, user_confirmed=args.user_confirmed)
    except TriggerContextExecuteBlocked as exc:
        report = {
            "result": "BLOCKED",
            "layer_role": "N4_trigger",
            "stage": "N4_TRIGGER_CONTEXT_REFRESH_RUNNER_GUARD",
            "database_written": False,
            "writes_performed": False,
            "blocked_reason": str(exc),
            "boundary_proof": {
                "trigger_context_written": False,
                "common_trigger_state_written": False,
                "common_trigger_match_written": False,
                "common_event_outbox_written": False,
                "outbox_consumed": False,
                "inbox_checkpoint_updated": False,
                "worker_started": False,
                "n5_n6_entered": False,
                "old_system_touched": False,
            },
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_blocked_summary(report))
        return 2

    report = run_trigger_context_snapshot_execute(
        dsn=args.dsn,
        condition_run_id=args.condition_run_id,
        for_trade_date=args.for_trade_date,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        rollback_sql_path=args.rollback_sql_path,
        allow_existing_context_for_trade_date=args.allow_existing_context_for_trade_date,
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
            "trigger context snapshot execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  run_id={report['run_id']}",
            f"  source_condition_run_id={report['source_condition_run_id']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  context_row_count={summary['row_count']}",
            f"  row_count_by_asset_kind={summary['row_count_by_asset_kind']}",
            f"  direction_distribution={summary['direction_distribution']}",
            f"  buy_hint_row_count={summary['buy_hint_row_count']}",
            f"  sell_hint_row_count={summary['sell_hint_row_count']}",
            f"  rollback_sql_path={report['rollback_sql_path']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  trigger_state_written=false trigger_match_written=false event_outbox_written=false",
            "  market_data_pulled=false n3_event_consumed=false worker_started=false downstream_layers_touched=false",
        ]
    )


def format_blocked_summary(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "trigger context snapshot execute",
            f"  result={report['result']}",
            f"  layer_role={report['layer_role']}",
            f"  blocked_reason={report['blocked_reason']}",
            "  database_written=false writes_performed=false",
            "  trigger_context_written=false trigger_state_written=false trigger_match_written=false event_outbox_written=false",
            "  outbox_consumed=false inbox_checkpoint_updated=false worker_started=false n5_n6_entered=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
