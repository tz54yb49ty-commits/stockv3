#!/usr/bin/env python3
"""Execute N4-2 010 additive trigger-layer schema migration with checks."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.migration_execute import (
    DEFAULT_N4_2_JSON_REPORT_PATH,
    DEFAULT_N4_2_MD_REPORT_PATH,
    DEFAULT_N4_2_POST_BACKUP_PATH,
    DEFAULT_N4_2_PRE_BACKUP_PATH,
    run_trigger_schema_010_migration,
)
from ashare_v3.trigger.schema_review import (
    DEFAULT_TRIGGER_SCHEMA_PATH,
    DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N4-2 additive trigger schema migration.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--sql-path", default=DEFAULT_TRIGGER_SCHEMA_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH)
    parser.add_argument("--pre-backup-path", default=DEFAULT_N4_2_PRE_BACKUP_PATH)
    parser.add_argument("--post-backup-path", default=DEFAULT_N4_2_POST_BACKUP_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N4_2_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N4_2_MD_REPORT_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_trigger_schema_010_migration(
        dsn=args.dsn,
        sql_path=args.sql_path,
        rollback_sql_path=args.rollback_sql_path,
        pre_backup_path=args.pre_backup_path,
        post_backup_path=args.post_backup_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    post_review = report["post_migration"]["review_summary"]
    checks = report["post_checks"]
    return "\n".join(
        [
            "trigger schema 010 migration execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  sql_path={report['sql_path']}",
            f"  rollback_sql_path={report['rollback_sql_path']}",
            f"  migration_executed={report['migration_executed']}",
            f"  missing_tables={post_review['target_tables_missing']}",
            f"  missing_dependency_tables={post_review['missing_dependency_tables']}",
            f"  missing_columns_count={post_review['missing_columns_count']}",
            f"  type_mismatch_count={post_review['type_mismatch_count']}",
            f"  missing_unique_constraints_count={post_review['missing_unique_constraints_count']}",
            f"  n4_target_tables_exist={checks['n4_target_tables_exist']}",
            f"  n4_target_tables_row_count_zero={checks['n4_target_tables_row_count_zero']}",
            f"  trigger_business_rows_zero={checks['trigger_business_rows_zero']}",
            f"  common_event_outbox_unchanged={checks['common_event_outbox_unchanged']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  market_data_pulled=false n3_event_consumed=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
