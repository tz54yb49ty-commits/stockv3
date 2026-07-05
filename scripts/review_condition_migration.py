#!/usr/bin/env python3
"""Review the condition-layer 005 migration draft without executing it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.migration_review import (
    build_condition_migration_review,
    format_review_markdown,
)
from ashare_v3.condition.schema_gap_plan import DEFAULT_SCHEMA_GAP_SQL_PATH
from ashare_v3.condition.schema_migration_readiness import DEFAULT_CONDITION_SCHEMA_PATH
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Review condition-layer migration safety without executing SQL.")
    parser.add_argument("--schema", default=DEFAULT_CONDITION_SCHEMA_PATH)
    parser.add_argument("--migration-sql", default=DEFAULT_SCHEMA_GAP_SQL_PATH)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--report-path", default="", help="Optional Markdown report path.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N2-E7 never executes SQL.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-E7 is review-only. It never supports --execute.")

    report = build_condition_migration_review(
        dsn=args.dsn,
        schema_path=args.schema,
        migration_sql_path=args.migration_sql,
    )

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_review_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report.to_dict()))
    return 0 if report.migration_safe_to_apply else 1


def format_summary(report: dict[str, Any]) -> str:
    gap = report["gap_summary"]
    sql_review = report["sql_review"]
    return "\n".join(
        [
            "condition migration review",
            f"  stage={report['stage']}",
            f"  migration_sql_path={report['migration_sql_path']}",
            f"  migration_safe_to_apply={report['migration_safe_to_apply']}",
            f"  additive_only={report['additive_only']}",
            f"  affects_existing_rows={report['affects_existing_rows']}",
            f"  requires_backup={report['requires_backup']}",
            f"  rollback_manual_only={report['rollback_manual_only']}",
            f"  user_confirmation_required={report['user_confirmation_required']}",
            f"  missing_column_count={gap['missing_column_count']}",
            f"  type_mismatch_count={gap['type_mismatch_count']}",
            f"  not_null_risk_count={gap['not_null_risk_count']}",
            f"  constraint_deferred_count={gap['constraint_deferred_count']}",
            f"  add_column_count={sql_review['add_column_count']}",
            f"  disallowed_hits={sql_review['disallowed_hits']}",
            "  will_execute_sql=false migration_performed=false writes_performed=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
