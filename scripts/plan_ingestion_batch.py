#!/usr/bin/env python3
"""Print a whole-batch raw ingestion orchestration dry-run plan."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.batch_orchestration import build_daily_ingestion_orchestration_plan
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", required=True, help="Daily ingestion trade date in YYYYMMDD format.")
    parser.add_argument("--version", default="v1", help="Batch/source version suffix, for example v1.")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT, help="Dry-run Parquet data root path.")
    args = parser.parse_args()

    plan = build_daily_ingestion_orchestration_plan(
        trade_date=args.trade_date,
        version=args.version,
        data_root=args.data_root,
    )
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0 if plan.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
