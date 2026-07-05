#!/usr/bin/env python3
"""Build N3-0D market-data schema migration plan without executing SQL."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.market.schema_migration_plan import (
    DEFAULT_SUBSCRIPTION_REPORT_PATH,
    REQUIRED_CONFIRMATION_PHRASE,
    build_market_data_schema_migration_plan,
    format_market_schema_migration_plan_markdown,
)
from ashare_v3.market.schema_migration_review import DEFAULT_MARKET_SCHEMA_PATH
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-0D market schema migration execute plan dry-run.")
    parser.add_argument("--schema", default=DEFAULT_MARKET_SCHEMA_PATH)
    parser.add_argument("--subscription-report", default=DEFAULT_SUBSCRIPTION_REPORT_PATH)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--report-path", default="", help="Optional Markdown report path.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--execute", action="store_true", help="Rejected. This planner never executes SQL.")
    parser.add_argument(
        "--user-confirmed",
        action="store_true",
        help=f"Records whether the explicit confirmation phrase was provided elsewhere: {REQUIRED_CONFIRMATION_PHRASE}",
    )
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-0D plan is dry-run only. It never supports --execute.")

    report = build_market_data_schema_migration_plan(
        dsn=args.dsn,
        schema_path=args.schema,
        subscription_report_path=args.subscription_report,
        user_confirmation=args.user_confirmed,
    )

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_market_schema_migration_plan_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    return "\n".join(
        [
            "market data schema migration plan dry-run",
            f"  stage={report['stage']}",
            f"  schema_path={report['schema_path']}",
            f"  migration_required={report['migration_required']}",
            f"  ready_for_user_confirmation={report['ready_for_user_confirmation']}",
            f"  user_confirmation_required={report['user_confirmation_required']}",
            f"  user_confirmation_present={report['user_confirmation_present']}",
            f"  execute_allowed={report['execute_allowed']}",
            f"  not_ready_reasons={report['not_ready_reasons']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  will_execute_sql=false migration_executed=false writes_performed=false",
            "  market_data_pulled=false market_data_fact_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
