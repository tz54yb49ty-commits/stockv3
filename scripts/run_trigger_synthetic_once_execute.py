#!/usr/bin/env python3
"""Execute N4-5 synthetic/sample trigger run-once.

This writes only N4 trigger_state, trigger_match, trigger quality items, and
N4 common_event_outbox rows. It does not consume real N3 outbox rows, pull
market data, start workers, or enter downstream layers.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.run_once_execute import (
    DEFAULT_N4_5_JSON_REPORT_PATH,
    DEFAULT_N4_5_MD_REPORT_PATH,
    DEFAULT_N4_5_ROLLBACK_SQL_PATH,
    DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    run_trigger_run_once_execute,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N4-5 trigger run-once from synthetic/sample N3 events.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_TRIGGER_CONTEXT_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_N4_5_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N4_5_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_N4_5_ROLLBACK_SQL_PATH)
    parser.add_argument("--dry-run-json-report-path", default=None)
    parser.add_argument("--dry-run-markdown-report-path", default=None)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--stage", default="N4-5")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_trigger_run_once_execute(
        dsn=args.dsn,
        trigger_context_run_id=args.trigger_context_run_id,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        rollback_sql_path=args.rollback_sql_path,
        dry_run_json_report_path=args.dry_run_json_report_path or DEFAULT_N4_5_JSON_REPORT_PATH.replace(
            "trigger_run_once_execute", "synthetic_trigger_dry_run_pre_execute"
        ),
        dry_run_markdown_report_path=args.dry_run_markdown_report_path or DEFAULT_N4_5_MD_REPORT_PATH.replace(
            "TRIGGER_RUN_ONCE_EXECUTE", "SYNTHETIC_TRIGGER_DRY_RUN_PRE_EXECUTE"
        ),
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
    output = report["output_summary"]
    return "\n".join(
        [
            "trigger run-once execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  run_id={report['run_id']}",
            f"  matched_count={output['matched_count']}",
            f"  pending_count={output['pending_count']}",
            f"  outbox_by_event_type={output['outbox_by_event_type']}",
            f"  buy_hint_matched_count={output['buy_hint_matched_count']}",
            f"  sell_hint_matched_count={output['sell_hint_matched_count']}",
            f"  rollback_sql_path={report['rollback_sql_path']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  trigger_state_written=true trigger_match_written=true event_outbox_written=true",
            "  market_data_pulled=false real_common_event_outbox_consumed=false worker_started=false downstream_layers_touched=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
