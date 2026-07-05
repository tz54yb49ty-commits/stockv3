#!/usr/bin/env python3
"""Run guarded common calendar and index identity dry-run via Tushare."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.common_index import run_common_index_ingestion_dry_run
from ashare_v3.ingestion.tushare_common_index_source import (
    DEFAULT_INDEX_MARKETS,
    TushareCommonIndexSource,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="20260521")
    parser.add_argument("--asof-date")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--calendar-exchange", default="SSE")
    parser.add_argument("--index-markets", default=",".join(DEFAULT_INDEX_MARKETS))
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Required because this dry-run calls Tushare APIs.",
    )
    args = parser.parse_args()

    if not args.allow_network:
        parser.error("--allow-network is required before calling Tushare APIs")

    source = TushareCommonIndexSource.from_env(
        trade_calendar_exchange=args.calendar_exchange,
        index_markets=[market.strip() for market in args.index_markets.split(",") if market.strip()],
    )
    result = run_common_index_ingestion_dry_run(
        source,
        start_date=args.start_date,
        end_date=args.end_date,
        asof_date=args.asof_date,
        version=args.version,
    )
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
