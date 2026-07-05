#!/usr/bin/env python3
"""Run a guarded Tushare stock ingestion dry-run for selected symbols."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.stock_pipeline import run_stock_ingestion_dry_run
from ashare_v3.ingestion.tushare_source import TushareStockSource


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="20260521")
    parser.add_argument("--end-date", default="20260521")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--symbols", required=True, help="Comma-separated Tushare ts_code values, for example 000001.SZ")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Required because this dry-run calls Tushare APIs.",
    )
    args = parser.parse_args()

    if not args.allow_network:
        parser.error("--allow-network is required before calling Tushare APIs")

    symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
    source = TushareStockSource.from_env(symbols=symbols)
    result = run_stock_ingestion_dry_run(
        source,
        start_date=args.start_date,
        end_date=args.end_date,
        version=args.version,
    )
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
