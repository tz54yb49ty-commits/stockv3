#!/usr/bin/env python3
"""Print the real-execution readiness summary dry-run."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG
from ashare_v3.ingestion.real_execution_readiness import build_real_execution_readiness_report
from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-config", default=DEFAULT_INITIAL_BACKFILL_CONFIG, help="Initial backfill dry-run TOML config path.")
    parser.add_argument("--daily-config", default=DEFAULT_DAILY_INCREMENTAL_CONFIG, help="Daily incremental dry-run TOML config path.")
    parser.add_argument("--real-config", default=DEFAULT_REAL_EXECUTION_CONFIG, help="Real-execution TOML template path.")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA_PATH, help="PostgreSQL schema SQL file to check statically.")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT, help="Planned root for Parquet archive data files.")
    parser.add_argument("--confirm-item", action="append", default=[], help="Model a user-confirmed preflight item by item_id. This only changes the JSON report.")
    args = parser.parse_args()

    report = build_real_execution_readiness_report(
        initial_config_path=args.initial_config,
        daily_config_path=args.daily_config,
        real_config_path=args.real_config,
        schema_path=args.schema,
        data_root=args.data_root,
        confirmed_item_ids=args.confirm_item,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
