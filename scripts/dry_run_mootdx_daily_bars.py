#!/usr/bin/env python3
"""Run guarded Mootdx index/board daily bar dry-run."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.common import infer_index_exchange_from_code, require_six_digit_code
from ashare_v3.ingestion.daily_bars import BoardDailySymbol, IndexDailySymbol, run_daily_bar_ingestion_dry_run
from ashare_v3.ingestion.mootdx_daily_source import MootdxDailyBarSource


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="20260521")
    parser.add_argument("--end-date", default="20260521")
    parser.add_argument("--expected-trade-dates", help="Comma-separated YYYYMMDD dates; defaults to end-date.")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--indexes", required=True, help="Comma-separated items like 000001.SH[:name],399001.SZ[:name].")
    parser.add_argument("--boards", required=True, help="Comma-separated items like 881002[:name[:tdx_industry]].")
    parser.add_argument("--frequency", type=int, default=9)
    parser.add_argument("--offset", type=int, default=800)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Required because this dry-run calls Mootdx quote APIs.",
    )
    args = parser.parse_args()

    if not args.allow_network:
        parser.error("--allow-network is required before calling Mootdx quote APIs")

    expected_trade_dates = None
    if args.expected_trade_dates:
        expected_trade_dates = [item.strip() for item in args.expected_trade_dates.split(",") if item.strip()]

    source = MootdxDailyBarSource(frequency=args.frequency, offset=args.offset)
    result = run_daily_bar_ingestion_dry_run(
        source,
        indexes=parse_index_symbols(args.indexes),
        boards=parse_board_symbols(args.boards),
        start_date=args.start_date,
        end_date=args.end_date,
        expected_trade_dates=expected_trade_dates,
        version=args.version,
    )
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


def parse_index_symbols(value: str) -> list[IndexDailySymbol]:
    symbols: list[IndexDailySymbol] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        symbol_part, *name_parts = item.split(":")
        code, exchange = parse_index_code_exchange(symbol_part)
        symbols.append(IndexDailySymbol(code=code, exchange=exchange, name=name_parts[0] if name_parts else None))
    return symbols


def parse_index_code_exchange(value: str) -> tuple[str, str]:
    if "." in value:
        code, suffix = value.split(".", 1)
        code = require_six_digit_code(code, "index code")
        exchange_map = {"SH": "SH", "SZ": "SZ", "BJ": "BJ", "SI": "SW", "SW": "SW", "TDX": "TDX"}
        return code, exchange_map.get(suffix.strip().upper(), "UNKNOWN")
    code = require_six_digit_code(value, "index code")
    return code, infer_index_exchange_from_code(code)


def parse_board_symbols(value: str) -> list[BoardDailySymbol]:
    symbols: list[BoardDailySymbol] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        board_code, *parts = item.split(":")
        board_code = require_six_digit_code(board_code, "board code")
        board_name = parts[0] if parts else None
        board_type = parts[1] if len(parts) > 1 else "tdx_other"
        symbols.append(BoardDailySymbol(board_code=board_code, board_name=board_name, board_type=board_type))
    return symbols


if __name__ == "__main__":
    raise SystemExit(main())
