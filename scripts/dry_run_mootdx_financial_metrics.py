#!/usr/bin/env python3
"""Run guarded Mootdx stock financial metrics dry-run."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.common import infer_stock_exchange_from_code, require_stock_code
from ashare_v3.ingestion.mootdx_financial_source import MootdxFinancialSource
from ashare_v3.ingestion.stock_financial import StockFinancialSymbol, run_stock_financial_ingestion_dry_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof-date", default="20260521")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--symbols", required=True, help="Comma-separated items like 000001.SZ[:name],600000.SH[:name].")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Required because this dry-run calls Mootdx quote APIs.",
    )
    args = parser.parse_args()

    if not args.allow_network:
        parser.error("--allow-network is required before calling Mootdx quote APIs")

    symbols = parse_stock_financial_symbols(args.symbols)
    source = MootdxFinancialSource()
    result = run_stock_financial_ingestion_dry_run(
        source,
        symbols=symbols,
        asof_date=args.asof_date,
        version=args.version,
    )
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


def parse_stock_financial_symbols(value: str) -> list[StockFinancialSymbol]:
    symbols: list[StockFinancialSymbol] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        symbol_part, *name_parts = item.split(":")
        code, exchange = parse_stock_code_exchange(symbol_part)
        symbols.append(StockFinancialSymbol(code=code, exchange=exchange, name=name_parts[0] if name_parts else None))
    return symbols


def parse_stock_code_exchange(value: str) -> tuple[str, str]:
    if "." in value:
        code, suffix = value.split(".", 1)
        code = require_stock_code(code)
        exchange = suffix.strip().upper()
        if exchange not in {"SH", "SZ", "BJ"}:
            raise ValueError(f"unsupported stock exchange suffix: {value!r}")
        return code, exchange
    code = require_stock_code(value)
    return code, infer_stock_exchange_from_code(code)


if __name__ == "__main__":
    raise SystemExit(main())
