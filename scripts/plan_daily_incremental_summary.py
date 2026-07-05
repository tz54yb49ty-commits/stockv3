#!/usr/bin/env python3
"""Print a compressed daily incremental execution checklist dry-run."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.batch_orchestration import build_daily_ingestion_orchestration_plan
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG, load_daily_incremental_config
from ashare_v3.ingestion.daily_incremental_summary import build_daily_incremental_execution_checklist
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_DAILY_INCREMENTAL_CONFIG, help="Optional TOML config path. Values remain dry-run only.")
    parser.add_argument("--trade-date", help="Daily ingestion trade date in YYYYMMDD format.")
    parser.add_argument("--version", help="Batch/source version suffix, for example v1.")
    parser.add_argument("--data-root", help="Dry-run Parquet data root path.")
    args = parser.parse_args()

    config = load_daily_incremental_config(args.config)
    trade_date = args.trade_date or config.trade_date
    version = args.version or config.version
    data_root = args.data_root or config.data_root or DEFAULT_DATA_ROOT

    plan = build_daily_ingestion_orchestration_plan(
        trade_date=trade_date,
        version=version,
        data_root=data_root,
    )
    checklist = build_daily_incremental_execution_checklist(plan, source_configs=config.sources)
    print(json.dumps(checklist.to_dict(), ensure_ascii=False, indent=2))
    return 0 if checklist.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
