#!/usr/bin/env python3
"""Review N3 market-data schema migration readiness without executing SQL."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.market.schema_migration_review import (
    DEFAULT_MARKET_SCHEMA_PATH,
    build_market_data_schema_migration_review,
    format_market_schema_review_markdown,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Review N3 market data schema migration readiness.")
    parser.add_argument("--schema", default=DEFAULT_MARKET_SCHEMA_PATH)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--report-path", default="", help="Optional Markdown report path.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N3-0C never executes SQL.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-0C is review-only. It never supports --execute.")

    report = build_market_data_schema_migration_review(
        dsn=args.dsn,
        schema_path=args.schema,
    )

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_market_schema_review_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    database = report["database_status"]
    return "\n".join(
        [
            "market data schema migration review",
            f"  stage={report['stage']}",
            f"  schema_path={report['schema_path']}",
            f"  migration_required={report['migration_required']}",
            f"  ready_for_first_apply={report['ready_for_first_apply']}",
            f"  ready_for_user_migration_review={report['ready_for_user_migration_review']}",
            f"  migration_safe_to_apply_after_user_confirmation={report['migration_safe_to_apply_after_user_confirmation']}",
            f"  manual_review_required={report['manual_review_required']}",
            f"  market_tables_existing={database['market_tables_existing']}",
            f"  market_tables_missing={database['market_tables_missing']}",
            f"  dependency_missing={database['dependency_missing']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  read_only_database_checks=true will_execute_sql=false migration_executed=false",
            "  writes_performed=false market_data_pulled=false market_data_fact_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
