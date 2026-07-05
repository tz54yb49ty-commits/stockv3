#!/usr/bin/env python3
"""Build V3 B_BUY/S_SELL replay comparison artifacts for 20260612.

The script is report-only. It reads an explicitly supplied target-machine
SQLite DB in read-only mode only when --old-system-read-confirmed is present;
it does not write any runtime database or start any worker.
"""

from __future__ import annotations

import argparse

from ashare_v3.market.b_buy_s_sell_replay_compare import (
    DEFAULT_TRADE_DATE,
    build_report_from_target_db,
    write_report_artifacts,
)


DEFAULT_JSON_REPORT_PATH = "docs/V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE.json"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE.md"
DEFAULT_DIFF_CSV_PATH = "docs/V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE_DIFF.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-db-path", required=True)
    parser.add_argument("--old-system-read-confirmed", action="store_true")
    parser.add_argument("--trade-date", default=DEFAULT_TRADE_DATE)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--diff-csv-path", default=DEFAULT_DIFF_CSV_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report_from_target_db(
        target_db_path=args.target_db_path,
        trade_date=args.trade_date,
        old_system_read_confirmed=args.old_system_read_confirmed,
    )
    write_report_artifacts(
        report,
        json_path=args.json_report_path,
        markdown_path=args.markdown_report_path,
        diff_csv_path=args.diff_csv_path,
    )
    print(f"wrote {args.json_report_path}")
    print(f"wrote {args.markdown_report_path}")
    print(f"wrote {args.diff_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
