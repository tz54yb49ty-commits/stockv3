#!/usr/bin/env python3
"""Execute N3-C1 today minute_bar_1m run-once.

This runner requires explicit ``--execute`` and ``--user-confirmed`` flags. It
does one bounded pass over the reviewed C0 plan subscriptions, then exits. It
does not write common_event_outbox, consume events, start workers, or enter
downstream layers.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.market.today_minute_execute import (
    DEFAULT_N3_C1_JSON_REPORT_PATH,
    DEFAULT_N3_C1_MD_REPORT_PATH,
    DEFAULT_N3_C1_POST_BACKUP_PATH,
    DEFAULT_N3_C1_PRE_BACKUP_PATH,
    DEFAULT_N3_C1_ROLLBACK_SQL_PATH,
    TodayMinuteExecuteError,
    run_today_minute_bar_1m_execute,
)
from ashare_v3.market.today_minute_plan import DEFAULT_N3_C0_JSON_REPORT_PATH
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        report = run_today_minute_bar_1m_execute(
            dsn=args.dsn,
            c0_plan_path=args.c0_plan_path,
            pre_backup_path=args.pre_backup_path,
            post_backup_path=args.post_backup_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
            for_trade_date=args.for_trade_date or None,
            today_minute_run_id=args.today_minute_run_id or None,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            progress_callback=print,
            progress_every=args.progress_every,
        )
    except TodayMinuteExecuteError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute N3-C1 today minute_bar_1m run-once.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--c0-plan-path", default=DEFAULT_N3_C0_JSON_REPORT_PATH)
    parser.add_argument("--pre-backup-path", default=DEFAULT_N3_C1_PRE_BACKUP_PATH)
    parser.add_argument("--post-backup-path", default=DEFAULT_N3_C1_POST_BACKUP_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N3_C1_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N3_C1_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_N3_C1_ROLLBACK_SQL_PATH)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--today-minute-run-id", required=True)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--execute", action="store_true", help="Required explicit execute authorization.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required operator confirmation.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    post_checks = report["post_checks"]
    return "\n".join(
        [
            "today minute_bar_1m execute",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  source_run_id={report['source_run_id']}",
            f"  today_minute_run_id={report['today_minute_run_id']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  latest_closed_minute={report['latest_closed_minute']}",
            f"  objects_processed={write['objects_processed']}",
            f"  minute_rows_written={write['minute_rows_written']}",
            f"  rows_by_asset={post_checks['n3_c1_actual_minute_rows_by_asset']}",
            f"  quality_item_rows_written={write['quality_item_rows_written']}",
            f"  event_outbox_rows_written={write['event_outbox_rows_written']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  "
            f"market_data_pulled={report['side_effects']['market_data_pulled']} "
            f"minute_bar_written={report['side_effects']['minute_bar_written']} "
            "event_outbox_written=false outbox_consumed=false "
            "downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
