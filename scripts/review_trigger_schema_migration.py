#!/usr/bin/env python3
"""Build N4-1 trigger schema gap / migration review reports.

This script uses a read-only PostgreSQL metadata check. It does not execute
010 migration SQL, write trigger rows, consume N3 events, pull market data,
start workers, or enter N5/N6.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.schema_review import (
    DEFAULT_TRIGGER_SCHEMA_PATH,
    DEFAULT_TRIGGER_SCHEMA_REVIEW_JSON_PATH,
    DEFAULT_TRIGGER_SCHEMA_REVIEW_MD_PATH,
    DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH,
    build_trigger_schema_migration_review,
    write_trigger_schema_review_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Review N4 trigger schema migration without executing SQL.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--schema-path", default=DEFAULT_TRIGGER_SCHEMA_PATH)
    parser.add_argument("--report-path", default=DEFAULT_TRIGGER_SCHEMA_REVIEW_JSON_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_TRIGGER_SCHEMA_REVIEW_MD_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH)
    parser.add_argument("--no-write", action="store_true", help="Do not write report or rollback preview files.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N4-1 never executes migration SQL.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N4-1 only reviews schema gaps. It never supports --execute.")

    report = build_trigger_schema_migration_review(
        dsn=args.dsn,
        schema_path=args.schema_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    if not args.no_write:
        write_trigger_schema_review_files(
            report,
            report_path=args.report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        "trigger schema migration review",
        f"  stage={report['stage']}",
        f"  layer_role={report['layer_role']}",
        f"  schema_path={report['schema_path']}",
        f"  rollback_sql_path={report['rollback_sql_path']}",
        f"  checked_readonly={report['checked_readonly']}",
        f"  migration_required={report['migration_required']}",
        f"  ready_for_n4_2_user_confirmation={report['ready_for_n4_2_user_confirmation']}",
        f"  migration_safe_to_apply_after_user_confirmation={report['migration_safe_to_apply_after_user_confirmation']}",
        f"  manual_review_required={report['manual_review_required']}",
        f"  target_tables_existing={report['target_tables_existing']}",
        f"  target_tables_missing={report['target_tables_missing']}",
        f"  missing_dependency_tables={report['missing_dependency_tables']}",
        f"  missing_column_count={len(report['missing_columns'])}",
        f"  type_mismatch_count={len(report['type_mismatch'])}",
        f"  missing_unique_constraint_count={len(report['missing_unique_constraints'])}",
        f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
        "  read_only_database_checks=true will_execute_sql=false migration_executed=false",
        "  writes_performed=false market_data_pulled=false n3_event_consumed=false worker_started=false",
        "  trigger_context_snapshot_written=false trigger_state_written=false trigger_match_written=false event_outbox_written=false",
        "  downstream_layers_touched=false old_system_touched=false",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
