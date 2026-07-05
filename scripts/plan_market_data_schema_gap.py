#!/usr/bin/env python3
"""Build N3-3 market-data schema gap report without executing migration SQL."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.market.schema_gap_plan import (
    DEFAULT_MARKET_SCHEMA_GAP_JSON_PATH,
    DEFAULT_MARKET_SCHEMA_GAP_MD_PATH,
    DEFAULT_MARKET_SCHEMA_GAP_SQL_PATH,
    DEFAULT_MARKET_SCHEMA_PATHS,
    build_market_data_schema_gap_report,
    format_market_data_schema_gap_markdown,
    generate_additive_migration_sql,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan N3 market-data schema gaps without executing SQL.")
    parser.add_argument(
        "--schema",
        action="append",
        dest="schemas",
        help="Target schema draft. May be supplied multiple times. Defaults to 006/007/008.",
    )
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--migration-sql-path", default=DEFAULT_MARKET_SCHEMA_GAP_SQL_PATH)
    parser.add_argument("--report-path", default=DEFAULT_MARKET_SCHEMA_GAP_JSON_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKET_SCHEMA_GAP_MD_PATH)
    parser.add_argument("--no-write", action="store_true", help="Do not write report or migration draft files.")
    parser.add_argument(
        "--force-write-sql",
        action="store_true",
        help="Write the migration SQL file even when no schema gaps remain.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N3-3 never executes migration SQL.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-3 only plans schema gaps. It never supports --execute.")

    schema_paths = tuple(args.schemas) if args.schemas else DEFAULT_MARKET_SCHEMA_PATHS
    report = build_market_data_schema_gap_report(
        dsn=args.dsn,
        schema_paths=schema_paths,
        migration_sql_path=args.migration_sql_path,
    )
    payload = report.to_dict()

    if not args.no_write:
        migration_path = Path(args.migration_sql_path)
        if report.migration_required or args.force_write_sql or not migration_path.exists():
            migration_path.parent.mkdir(parents=True, exist_ok=True)
            migration_path.write_text(generate_additive_migration_sql(report), encoding="utf-8")

        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

        markdown_path = Path(args.markdown_report_path)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(format_market_data_schema_gap_markdown(payload), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(payload))
    return 0 if payload["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        "market data schema gap plan",
        f"  stage={report['stage']}",
        f"  layer_role={report['layer_role']}",
        f"  schema_paths={report['schema_paths']}",
        f"  migration_sql_path={report['migration_sql_path']}",
        f"  checked_readonly={report['checked_readonly']}",
        f"  migration_required={report['migration_required']}",
        f"  migration_safe_to_apply={report['migration_safe_to_apply']}",
        f"  manual_review_required={report['manual_review_required']}",
        f"  missing_tables={report['missing_tables']}",
        f"  missing_column_count={len(report['missing_columns'])}",
        f"  type_mismatch_count={len(report['type_mismatch'])}",
        f"  missing_unique_constraint_count={len(report['missing_unique_constraints'])}",
        f"  missing_dependency_tables={report['missing_dependency_tables']}",
        f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
        "  read_only_database_checks=true will_execute_sql=false migration_executed=false",
        "  writes_performed=false market_data_pulled=false market_data_fact_written=false downstream_layers_touched=false worker_started=false",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
