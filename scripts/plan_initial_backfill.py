#!/usr/bin/env python3
"""Print the initial historical raw-ingestion backfill dry-run plan."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.backfill_plan import DEFAULT_BACKFILL_END_DATE, DEFAULT_BACKFILL_START_DATE, build_initial_backfill_plan
from ashare_v3.ingestion.backfill_config import load_initial_backfill_config
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Optional TOML config path. Values remain dry-run only.")
    parser.add_argument("--start-date", help="Backfill start date in YYYYMMDD format.")
    parser.add_argument("--end-date", help="Backfill end date in YYYYMMDD format.")
    parser.add_argument("--snapshot-date", help="Identity/membership snapshot date in YYYYMMDD format. Defaults to --end-date.")
    parser.add_argument("--version", help="Batch/source version suffix, for example v1.")
    parser.add_argument("--data-root", help="Dry-run Parquet data root path.")
    args = parser.parse_args()

    if args.config:
        config = load_initial_backfill_config(args.config)
        start_date = args.start_date or config.start_date
        end_date = args.end_date or config.end_date
        snapshot_date = args.snapshot_date or config.snapshot_date
        version = args.version or config.version
        data_root = args.data_root or config.data_root
    else:
        start_date = args.start_date or DEFAULT_BACKFILL_START_DATE
        end_date = args.end_date or DEFAULT_BACKFILL_END_DATE
        snapshot_date = args.snapshot_date
        version = args.version or "v1"
        data_root = args.data_root or DEFAULT_DATA_ROOT

    plan = build_initial_backfill_plan(
        start_date=start_date,
        end_date=end_date,
        snapshot_date=snapshot_date,
        version=version,
        data_root=data_root,
    )
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0 if plan.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
