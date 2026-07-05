#!/usr/bin/env python3
"""Execute N3-5 009 additive market-data migration with before/after checks."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.migration_execute import (
    DEFAULT_N3_5_JSON_REPORT_PATH,
    DEFAULT_N3_5_MD_REPORT_PATH,
    DEFAULT_N3_5_POST_BACKUP_PATH,
    DEFAULT_N3_5_PRE_BACKUP_PATH,
    run_market_data_009_migration,
)
from ashare_v3.market.migration_review import DEFAULT_009_MIGRATION_PATH
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N3-5 009 additive market-data migration.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--sql-path", default=DEFAULT_009_MIGRATION_PATH)
    parser.add_argument("--pre-backup-path", default=DEFAULT_N3_5_PRE_BACKUP_PATH)
    parser.add_argument("--post-backup-path", default=DEFAULT_N3_5_POST_BACKUP_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N3_5_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N3_5_MD_REPORT_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_market_data_009_migration(
        dsn=args.dsn,
        sql_path=args.sql_path,
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
    post_gap = report["post_migration"]["schema_gap_summary"]
    checks = report["post_checks"]
    return "\n".join(
        [
            "market data 009 migration execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  sql_path={report['sql_path']}",
            f"  migration_executed={report['migration_executed']}",
            f"  missing_tables={post_gap['missing_tables']}",
            f"  missing_columns_count={post_gap['missing_columns_count']}",
            f"  type_mismatch_count={post_gap['type_mismatch_count']}",
            f"  missing_unique_constraints_count={post_gap['missing_unique_constraints_count']}",
            f"  n3_target_tables_exist={checks['n3_target_tables_exist']}",
            f"  n3_target_tables_row_count_zero={checks['n3_target_tables_row_count_zero']}",
            f"  n1_n2_active_run_unchanged={checks['n1_n2_active_run_unchanged']}",
            f"  no_market_fact_or_outbox_business_events={checks['no_market_fact_or_outbox_business_events']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  market_data_pulled=false market_data_fact_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
