#!/usr/bin/env python3
"""Build a read-only N2-E6 schema gap report and optional migration SQL plan."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.schema_gap_plan import (
    DEFAULT_SCHEMA_GAP_SQL_PATH,
    build_condition_schema_gap_report,
    generate_additive_migration_sql,
)
from ashare_v3.condition.schema_migration_readiness import DEFAULT_CONDITION_SCHEMA_PATH
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan condition-layer schema gaps without executing migration SQL.")
    parser.add_argument("--schema", default=DEFAULT_CONDITION_SCHEMA_PATH, help="Target condition schema draft.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--migration-sql-path", default=DEFAULT_SCHEMA_GAP_SQL_PATH)
    parser.add_argument("--write-sql", action="store_true", help="Write the additive migration SQL plan file.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N2-E6 never executes migration SQL.")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-E6 only plans schema gaps. It never supports --execute.")

    report = build_condition_schema_gap_report(
        dsn=args.dsn,
        schema_path=args.schema,
        migration_sql_path=args.migration_sql_path,
    )
    payload = report.to_dict()

    if args.write_sql:
        path = Path(args.migration_sql_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generate_additive_migration_sql(report), encoding="utf-8")

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(payload))
    return 0 if report.passed else 1


def format_summary(report: dict[str, Any]) -> str:
    missing_columns = report["missing_columns"]
    type_mismatches = report["type_mismatches"]
    lines = [
        "condition schema gap plan",
        f"  stage={report['stage']}",
        f"  schema_path={report['schema_path']}",
        f"  migration_sql_path={report['migration_sql_path']}",
        f"  checked_readonly={report['checked_readonly']}",
        f"  migration_required={report['migration_required']}",
        f"  missing_tables={report['missing_tables']}",
        f"  missing_column_count={len(missing_columns)}",
        f"  type_mismatch_count={len(type_mismatches)}",
        f"  not_null_risk_count={len(report['not_null_risks'])}",
        f"  constraint_deferred_count={len(report['constraint_deferred'])}",
        "  will_execute_sql=false writes_performed=false",
    ]
    for table_name in sorted({item["table_name"] for item in missing_columns}):
        columns = [item["column_name"] for item in missing_columns if item["table_name"] == table_name]
        lines.append(f"  {table_name}.missing_columns={columns}")
    if type_mismatches:
        lines.append(f"  type_mismatches={type_mismatches}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
