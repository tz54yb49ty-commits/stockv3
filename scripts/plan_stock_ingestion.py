#!/usr/bin/env python3
"""Print the N2 stock ingestion batch plan without touching external systems."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.common import make_source_batch_id, require_yyyymmdd


def build_plan(start_date: str, end_date: str, version: str) -> dict[str, object]:
    require_yyyymmdd(start_date, "start_date")
    require_yyyymmdd(end_date, "end_date")
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")

    period = f"{start_date}_{end_date}"
    return {
        "stage": "N2",
        "scope": "stock raw ingestion plan only",
        "will_connect_database": False,
        "will_call_external_api": False,
        "will_write_data_files": False,
        "tables": [
            "stock_identity",
            "stock_daily_bar_fact",
            "stock_daily_basic",
        ],
        "batches": {
            "stock_identity": make_source_batch_id("stock_identity", end_date, version),
            "stock_daily_bar_fact": make_source_batch_id("stock_daily", period, version),
            "stock_daily_basic": make_source_batch_id("stock_daily_basic", period, version),
        },
        "quality_gates": [
            "stock_identity_key_coverage",
            "88xxxx_stock_violation",
            "stock_official_daily_proof",
            "stock_universe_alignment",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="20260521")
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()

    print(json.dumps(build_plan(args.start_date, args.end_date, args.version), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
