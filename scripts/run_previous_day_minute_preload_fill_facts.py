#!/usr/bin/env python3
"""Run N3-A1 current-lineage previous-day minute fill-facts/resume.

This CLI fills facts for an existing metadata-only preload run. It requires
--execute and --user-confirmed, writes no event outbox rows, starts no worker,
and does not enter downstream layers.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.previous_day_preload_fill import (
    DEFAULT_CURRENT_A1_FILL_CONTRACT_PATH,
    DEFAULT_CURRENT_A1_FILL_JSON_REPORT_PATH,
    DEFAULT_CURRENT_A1_FILL_MD_REPORT_PATH,
    DEFAULT_CURRENT_A1_FILL_POST_BACKUP_PATH,
    DEFAULT_CURRENT_A1_FILL_PRE_BACKUP_PATH,
    DEFAULT_CURRENT_A1_FILL_ROLLBACK_SQL_PATH,
    DEFAULT_CURRENT_A1_FILL_STATUS_SNAPSHOT_PATH,
    PreviousDayMinutePreloadFillError,
    run_previous_day_minute_preload_fill_facts,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N3-A1 current-lineage previous-day minute fill-facts/resume.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", default=DEFAULT_CURRENT_A1_FILL_CONTRACT_PATH)
    parser.add_argument("--pre-backup-path", default=DEFAULT_CURRENT_A1_FILL_PRE_BACKUP_PATH)
    parser.add_argument("--post-backup-path", default=DEFAULT_CURRENT_A1_FILL_POST_BACKUP_PATH)
    parser.add_argument("--status-snapshot-path", default=DEFAULT_CURRENT_A1_FILL_STATUS_SNAPSHOT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_CURRENT_A1_FILL_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_CURRENT_A1_FILL_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_CURRENT_A1_FILL_ROLLBACK_SQL_PATH)
    parser.add_argument("--for-trade-date")
    parser.add_argument("--preload-run-id")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    try:
        report = run_previous_day_minute_preload_fill_facts(
            dsn=args.dsn,
            contract_path=args.contract_path,
            pre_backup_path=args.pre_backup_path,
            post_backup_path=args.post_backup_path,
            status_snapshot_path=args.status_snapshot_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
            for_trade_date=args.for_trade_date,
            preload_run_id=args.preload_run_id,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            progress_callback=print,
            progress_every=args.progress_every,
        )
    except PreviousDayMinutePreloadFillError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    return "\n".join(
        [
            "current-lineage previous-day minute fill-facts execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  source_run_id={report['source_run_id']}",
            f"  preload_run_id={report['preload_run_id']}",
            f"  previous_day_minute_date={report['previous_day_minute_date']}",
            f"  objects_processed={write['objects_processed']}",
            f"  minute_rows_written={write['minute_rows_written']}",
            f"  preload_status_rows_written={write['preload_status_rows_written']}",
            f"  quality_item_rows_written={write['quality_item_rows_written']}",
            f"  event_outbox_rows_written={write['event_outbox_rows_written']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            f"  status_snapshot_path={report['status_snapshot_path']}",
            f"  rollback_sql_path={report['rollback_sql_path']}",
            "  "
            f"market_data_pulled={report['side_effects']['market_data_pulled']} "
            f"market_data_fact_written={report['side_effects']['market_data_fact_written']} "
            "event_outbox_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
