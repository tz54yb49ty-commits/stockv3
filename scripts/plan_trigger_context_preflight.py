#!/usr/bin/env python3
"""Build an N4-0 trigger local context preflight report.

This script reads the active N2 condition context in a read-only transaction.
It does not write trigger_context_snapshot rows, consume N3 events, pull market
data, execute migrations, start workers, or touch downstream layers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.trigger.context_preflight import (
    DEFAULT_N4_CONTEXT_PREFLIGHT_JSON_PATH,
    build_trigger_context_preflight_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N4-0 trigger context preflight report.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed N4-0 mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected in N4-0.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", default="", help="Optional explicit condition run id. Defaults to the single active passed run.")
    parser.add_argument("--source-trade-date", default="", help="Optional source_trade_date filter, e.g. 20260522.")
    parser.add_argument("--for-trade-date", default="", help="Optional for_trade_date filter, e.g. 20260525.")
    parser.add_argument("--report-path", default=DEFAULT_N4_CONTEXT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--no-include-rows", action="store_true", help="Only include row samples in the JSON report.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N4-0 only supports --dry-run. Execute requires explicit later-stage confirmation.")

    report = build_trigger_context_preflight_dry_run(
        dsn=args.dsn,
        run_id=args.run_id or None,
        source_trade_date=args.source_trade_date or None,
        for_trade_date=args.for_trade_date or None,
        include_rows=not args.no_include_rows,
    )

    path = Path(args.report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("passed") else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        "trigger_context preflight",
        f"  source_condition_run_id={report.get('source_condition_run_id')}",
        f"  source_trade_date={report.get('source_trade_date')}",
        f"  for_trade_date={report.get('for_trade_date')}",
        f"  prev_trade_date={report.get('prev_trade_date')}",
        f"  candidate_context_row_count={report.get('candidate_context_row_count')}",
        f"  object_count={report.get('object_count')}",
        f"  object_count_by_asset_kind={report.get('object_count_by_asset_kind')}",
        f"  direction_distribution={report.get('direction_distribution')}",
        f"  buy_hint_row_count={report.get('buy_hint_row_count')}",
        f"  sell_hint_row_count={report.get('sell_hint_row_count')}",
        f"  trigger_candidate_count_by_signal_type={report.get('trigger_candidate_count_by_signal_type')}",
        f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
        f"  blocked={report.get('blocked')} passed={report.get('passed')}",
        "  writes_performed=false market_data_pulled=false n3_event_consumed=false worker_started=false",
        "  downstream_layers_touched=false old_system_touched=false external_n2_runtime_path_accessed=false",
    ]
    if report.get("blocked"):
        failed = [
            item
            for item in quality["items"]
            if item.get("status") in {"failed", "warning"}
        ][:10]
        lines.append(f"  blocking_quality_items={failed}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
