#!/usr/bin/env python3
"""Run N5-0 trigger outbox preflight and action candidate dry-run.

This is read-only for PostgreSQL. It writes report files only and does not
consume N4 outbox rows, update inbox/checkpoint, write action facts, pull
market data, start workers, or enter the user layer.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.action.preflight import (
    DEFAULT_N5_0_ACTION_RUN_ID,
    DEFAULT_N5_0_JSON_REPORT_PATH,
    DEFAULT_N5_0_MD_REPORT_PATH,
    DEFAULT_TRIGGER_RUN_ID,
    run_action_preflight,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Run N5-0 action preflight / dry-run from N4 outbox.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-run-id", default=DEFAULT_TRIGGER_RUN_ID)
    parser.add_argument("--action-run-id", default=DEFAULT_N5_0_ACTION_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_N5_0_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N5_0_MD_REPORT_PATH)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_action_preflight(
        dsn=args.dsn,
        trigger_run_id=args.trigger_run_id,
        action_run_id=args.action_run_id,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        sample_limit=args.sample_limit,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    outbox = report["outbox_summary"]
    candidates = report["action_candidate_summary"]
    quality = report["quality"]
    return "\n".join(
        [
            "action preflight / dry-run",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  source_trigger_run_id={report['source_trigger_run_id']}",
            f"  outbox_by_event_type={outbox['by_event_type']}",
            f"  outbox_by_signal_type={outbox['by_signal_type']}",
            f"  pending_count={outbox['pending_count']}",
            f"  buy_hint matched/pending/total={outbox['buy_hint_matched_count']}/{outbox['buy_hint_pending_count']}/{outbox['buy_hint_count']}",
            f"  sell_hint matched/pending/total={outbox['sell_hint_matched_count']}/{outbox['sell_hint_pending_count']}/{outbox['sell_hint_count']}",
            f"  action_candidate_count={candidates['action_candidate_count']}",
            f"  quality_plan_count={candidates['quality_plan_count']}",
            f"  planned_output_event_type={candidates['by_planned_output_event_type']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  writes_performed=false common_event_inbox_updated=false consumer_checkpoint_updated=false",
            "  market_data_pulled=false real_n4_outbox_consumed=false user_voice_sim_written=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
