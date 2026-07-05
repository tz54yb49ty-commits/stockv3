#!/usr/bin/env python3
"""Review N3-4 009 market-data migration draft without executing SQL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ashare_v3.market.migration_review import (
    DEFAULT_009_MIGRATION_PATH,
    DEFAULT_N3_4_REVIEW_REPORT_PATH,
    build_market_data_009_migration_review,
    format_market_data_migration_review_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review sql/009 market-data migration draft.")
    parser.add_argument("--sql-path", default=DEFAULT_009_MIGRATION_PATH)
    parser.add_argument("--report-path", default=DEFAULT_N3_4_REVIEW_REPORT_PATH)
    parser.add_argument("--no-write", action="store_true", help="Do not write the Markdown review report.")
    parser.add_argument("--json", action="store_true", help="Print full JSON review.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N3-4 never executes migration SQL.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-4 is a static review only. It never supports --execute.")

    report = build_market_data_009_migration_review(sql_path=args.sql_path)

    if not args.no_write:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_market_data_migration_review_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    return "\n".join(
        [
            "market data 009 migration review",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  sql_path={report['sql_path']}",
            f"  additive_only={report['additive_only']}",
            f"  target_scope_valid={report['target_scope_valid']}",
            f"  outbox_unique_constraints_present={report['outbox_unique_constraints_present']}",
            f"  forbidden_executable_hits={report['forbidden_executable_hits']}",
            f"  unsupported_statements={report['unsupported_statements']}",
            f"  runtime_identifier_hits={report['runtime_identifier_hits']}",
            f"  user_event_hits={report['user_event_hits']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  will_execute_sql=false migration_executed=false writes_performed=false",
            "  market_data_pulled=false market_data_fact_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
