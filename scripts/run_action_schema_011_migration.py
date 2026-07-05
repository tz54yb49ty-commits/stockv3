#!/usr/bin/env python3
"""Execute N5-4 011 additive action-layer schema migration with checks."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.action.schema_migration_execute import (
    DEFAULT_N5_4_JSON_REPORT_PATH,
    DEFAULT_N5_4_MD_REPORT_PATH,
    DEFAULT_N5_4_POST_SCHEMA_SNAPSHOT_PATH,
    DEFAULT_N5_4_PRE_SCHEMA_SNAPSHOT_PATH,
    run_action_schema_011_migration,
)
from ashare_v3.action.schema_migration_review import (
    DEFAULT_N5_3_JSON_REPORT_PATH,
    DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH,
    DEFAULT_N5_3_SCHEMA_PATH,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N5-4 additive action schema migration.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--sql-path", default=DEFAULT_N5_3_SCHEMA_PATH)
    parser.add_argument("--review-json-path", default=DEFAULT_N5_3_JSON_REPORT_PATH)
    parser.add_argument("--rollback-preview-path", default=DEFAULT_N5_3_ROLLBACK_PREVIEW_PATH)
    parser.add_argument("--pre-schema-snapshot-path", default=DEFAULT_N5_4_PRE_SCHEMA_SNAPSHOT_PATH)
    parser.add_argument("--post-schema-snapshot-path", default=DEFAULT_N5_4_POST_SCHEMA_SNAPSHOT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N5_4_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N5_4_MD_REPORT_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_action_schema_011_migration(
        dsn=args.dsn,
        sql_path=args.sql_path,
        review_json_path=args.review_json_path,
        rollback_preview_path=args.rollback_preview_path,
        pre_schema_snapshot_path=args.pre_schema_snapshot_path,
        post_schema_snapshot_path=args.post_schema_snapshot_path,
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
    checks = report["post_checks"]
    return "\n".join(
        [
            "action schema 011 migration execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  sql_path={report['sql_path']}",
            f"  migration_executed={report['migration_executed']}",
            f"  n5_target_tables_exist={checks['n5_target_tables_exist']}",
            f"  n5_target_tables_row_count_zero={checks['n5_target_tables_row_count_zero']}",
            f"  common_event_outbox_unchanged={checks['common_event_outbox_unchanged']}",
            f"  common_event_inbox_unchanged={checks['common_event_inbox_unchanged']}",
            f"  common_event_consumer_checkpoint_unchanged={checks['common_event_consumer_checkpoint_unchanged']}",
            f"  action_fact_rows_zero={checks['action_fact_rows_zero']}",
            f"  n5_outbox_rows_zero={checks['n5_outbox_rows_zero']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  n4_outbox_consumed=false n5_outbox_written=false n6_user_layer_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
