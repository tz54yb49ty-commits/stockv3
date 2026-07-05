#!/usr/bin/env python3
"""Run N4-4 synthetic/sample N3 event trigger dry-run."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.synthetic_dry_run import (
    DEFAULT_N4_4_JSON_REPORT_PATH,
    DEFAULT_N4_4_MD_REPORT_PATH,
    DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    run_synthetic_trigger_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan N4-4 trigger outputs from synthetic/sample N3 events.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_TRIGGER_CONTEXT_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_N4_4_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N4_4_MD_REPORT_PATH)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--stage", default="N4-4")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_synthetic_trigger_dry_run(
        dsn=args.dsn,
        trigger_context_run_id=args.trigger_context_run_id,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        sample_limit=args.sample_limit,
        stage=args.stage,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    summary = report["summary"]
    return "\n".join(
        [
            "synthetic trigger dry-run",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  trigger_context_run_id={report['trigger_context_run_id']}",
            f"  context_candidate_count={report['context_candidate_count']}",
            f"  period_trigger_baseline_json_missing={report.get('period_trigger_baseline_json_missing')}",
            f"  required_period_not_ready_rows={report.get('required_period_not_ready_rows')}",
            f"  period_trigger_baseline_trace_count={report.get('period_trigger_baseline_trace_count')}",
            f"  candidate_count={report['candidate_count']}",
            f"  matched_count={report['matched_count']}",
            f"  pending_count={report['pending_count']}",
            f"  by_event_type={summary['by_event_type']}",
            f"  by_signal_type={summary['by_signal_type']}",
            f"  trigger_period_distribution={summary['trigger_period_distribution']}",
            f"  buy_hint_matched_count={summary['buy_hint_matched_count']}",
            f"  sell_hint_matched_count={summary['sell_hint_matched_count']}",
            f"  current_context_run_outbox_count={report['outbox_lineage']['current_context_run_outbox_count']}",
            f"  stale_n4_outbox_count={report['outbox_lineage']['stale_n4_outbox_count']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  writes_performed=false trigger_state_written=false trigger_match_written=false event_outbox_written=false",
            "  market_data_pulled=false real_common_event_outbox_consumed=false worker_started=false downstream_layers_touched=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
