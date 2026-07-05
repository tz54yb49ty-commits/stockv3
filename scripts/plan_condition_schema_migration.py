#!/usr/bin/env python3
"""Build the N2-E2A condition schema migration readiness report.

This script is a dry-run planner. It may perform optional read-only database
metadata checks, but it never runs the condition schema SQL or writes data.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.schema_migration_readiness import (
    DEFAULT_CONDITION_SCHEMA_PATH,
    build_condition_schema_migration_readiness_report,
    fetch_condition_schema_database_status,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan condition-layer schema migration readiness without executing SQL.")
    parser.add_argument("--schema", default=DEFAULT_CONDITION_SCHEMA_PATH, help="Condition layer SQL schema draft to inspect.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--check-database", action="store_true", help="Use a read-only connection to inspect existing DB objects.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N2-E2A never executes SQL.")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-E2A only builds a migration readiness report. It never supports --execute.")

    database_status = fetch_condition_schema_database_status(args.dsn) if args.check_database else None
    report = build_condition_schema_migration_readiness_report(
        schema_path=args.schema,
        database_status=database_status,
    )
    payload = report.to_dict()

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(payload))
    return 0 if report.ready_for_user_migration_review else 1


def format_summary(report: dict[str, Any]) -> str:
    db = report.get("database_status") or {}
    failed_gates = [
        gate["gate_name"]
        for gate in report.get("quality_gates", [])
        if gate.get("status") != "passed"
    ]
    lines = [
        "condition schema migration readiness",
        f"  stage={report['stage']}",
        f"  schema_path={report['schema_path']}",
        f"  schema_hash={report['schema_hash']}",
        f"  table_count={report['table_count']} index_count={report['index_count']}",
        f"  static_ready={report['static_ready']} failed_static_gates={failed_gates}",
    ]
    if db:
        lines.extend(
            [
                f"  database_checked={db['checked']} read_only={db['read_only']}",
                f"  condition_tables_existing={db['condition_tables_existing']}",
                f"  condition_tables_missing={db['condition_tables_missing']}",
                f"  fk_dependency_missing={db['fk_dependency_missing']}",
                f"  runtime_dependency_missing={db['runtime_dependency_missing']}",
                f"  ready_for_first_apply={db['ready_for_first_apply']} manual_review_required={db['manual_review_required']}",
            ]
        )
    else:
        lines.append("  database_checked=false")
    lines.extend(
        [
            f"  ready_for_user_migration_review={report['ready_for_user_migration_review']}",
            "  will_execute_sql=false migration_performed=false writes_performed=false minute_kline_pulled=false",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
