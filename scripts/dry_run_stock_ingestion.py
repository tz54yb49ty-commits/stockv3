#!/usr/bin/env python3
"""Run stock ingestion dry-run with embedded sample rows only."""

from __future__ import annotations

import argparse
import json
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.stock_pipeline import run_stock_ingestion_dry_run


class SampleStockSource:
    def fetch_stock_basic(self, *, asof_date: str) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "area": "深圳",
                "industry": "银行",
                "market": "主板",
                "list_date": "19910403",
                "list_status": "L",
            }
        ]

    def fetch_stock_daily_qfq(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "ts_code": "000001.SZ",
                "trade_date": end_date,
                "open": "10.00",
                "high": "10.30",
                "low": "9.90",
                "close": "10.20",
                "vol": "10000",
                "amount": "102000",
                "adj_factor": "1.00",
            }
        ]

    def fetch_stock_daily_basic(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "ts_code": "000001.SZ",
                "trade_date": end_date,
                "close": "10.20",
                "turnover_rate": "1.10",
                "pe": "6.50",
                "pb": "0.70",
                "total_mv": "1000000",
                "circ_mv": "900000",
            }
        ]

    def fetch_stock_official_daily_proof_keys(self, *, start_date: str, end_date: str) -> set[tuple[str, str]]:
        return {("000001.SZ", end_date)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="20260521")
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()

    result = run_stock_ingestion_dry_run(
        SampleStockSource(),
        start_date=args.start_date,
        end_date=args.end_date,
        version=args.version,
    )
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
