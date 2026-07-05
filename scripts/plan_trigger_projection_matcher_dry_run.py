#!/usr/bin/env python3
"""Run N4 projection matcher dry-run from N3 realtime projection facts."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.projection_matcher import (
    DEFAULT_CONTEXT_RUN_ID,
    DEFAULT_N4_PROJECTION_MATCHER_JSON_REPORT_PATH,
    DEFAULT_N4_PROJECTION_MATCHER_MD_REPORT_PATH,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_SYNTHETIC_DENYLIST,
    run_projection_matcher_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = run_projection_matcher_dry_run(
        dsn=args.dsn,
        trigger_context_run_id=args.trigger_context_run_id,
        projection_run_id=args.projection_run_id,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        synthetic_denylist=tuple(args.synthetic_denylist),
        sample_limit=args.sample_limit,
        stage=args.stage,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan N4 projection matcher outputs from N3 projection facts.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_CONTEXT_RUN_ID)
    parser.add_argument("--projection-run-id", default=DEFAULT_PROJECTION_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_N4_PROJECTION_MATCHER_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N4_PROJECTION_MATCHER_MD_REPORT_PATH)
    parser.add_argument("--synthetic-denylist", action="append", default=list(DEFAULT_SYNTHETIC_DENYLIST))
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--stage", default="N4-projection-matcher-implementation")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    summary = report["summary"]
    return "\n".join(
        [
            "projection matcher dry-run",
            f"  result={report['result']}",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  trigger_context_run_id={report['trigger_context_run_id']}",
            f"  projection_run_id={report['projection_run_id']}",
            f"  candidate_count={summary['candidate_count']}",
            f"  matched_count={summary['matched_count']}",
            f"  pending_count={summary['pending_count']}",
            f"  not_matched_signal_count={summary['not_matched_signal_count']}",
            f"  matched_by_signal_type={summary['matched_by_signal_type']}",
            f"  pending_by_not_ready_classification={summary['pending_by_not_ready_classification']}",
            f"  board_not_ready_object_count={summary['board_not_ready_object_count']}",
            f"  bj_920xxx_not_ready_object_count={summary['bj_920xxx_not_ready_object_count']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  writes_performed=false outbox_consumed=false inbox_written=false checkpoint_written=false",
            "  trigger_match_written=false event_outbox_written=false market_data_pulled=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
