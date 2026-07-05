#!/usr/bin/env python3
"""Plan N1 stock_financial canonical source bundle for 20260529.

This runner is no-write. It may perform explicit read-only source probes when
`--source-fetch-enabled` is provided, but it never writes PostgreSQL, Parquet,
active source versions, condition tables, or outbox/inbox/checkpoint rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Mapping

from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.ingestion.stock_financial_canonical_source_bundle import (
    DEFAULT_TUSHARE_CACHE_PATH,
    TRADE_DATE,
    StockFinancialCanonicalSourceBundleBlocked,
    build_contract,
    build_preflight,
    build_snapshot_from_db,
    build_source_bundle_report,
    validate_source_bundle_request,
    write_artifacts,
)


DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"


def main(argv: list[str] | None = None, *, dependencies: Mapping[str, Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-trade-date", "--trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN") or DEFAULT_DSN)
    parser.add_argument("--source-fetch-enabled", action="store_true", help="Enable read-only TDX/Mootdx and Tushare source probes.")
    parser.add_argument("--max-symbols", type=int, default=None, help="Optional probe cap. Defaults to a bounded small sample; 0 means full active universe only with --full-fetch-confirmed.")
    parser.add_argument("--symbol-shard", help="Optional 1-based shard selector in N/M format, applied before the probe cap.")
    parser.add_argument("--resume-cache-path", default=str(DEFAULT_TUSHARE_CACHE_PATH), help="Local JSON cache path for read-only Tushare probe responses.")
    parser.add_argument("--rate-limit-ms", type=int, default=300, help="Milliseconds to wait between Tushare requests when source fetch is enabled.")
    parser.add_argument("--full-fetch-confirmed", action="store_true", help="Allow unbounded 5506-symbol source probe when --max-symbols 0 is also supplied.")
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Rejected: this is a dry-run/source-probe runner only.")
    args = parser.parse_args(argv)
    deps = dict(dependencies or {})
    try:
        validate_source_bundle_request(execute_requested=args.execute)
    except StockFinancialCanonicalSourceBundleBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    snapshot_builder = deps.get("build_snapshot_from_db", build_snapshot_from_db)
    snapshot = snapshot_builder(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        source_fetch_enabled=args.source_fetch_enabled,
        max_symbols=args.max_symbols,
        symbol_shard=args.symbol_shard,
        resume_cache_path=args.resume_cache_path,
        rate_limit_ms=args.rate_limit_ms,
        full_fetch_confirmed=args.full_fetch_confirmed,
        tushare_token=load_tushare_token(),
    )
    report = build_source_bundle_report(
        source_trade_date=args.source_trade_date,
        expected_identity_keys=snapshot.get("expected_identity_keys") or [],
        tdx_rows=snapshot.get("tdx_rows") or [],
        tushare_rows=snapshot.get("tushare_rows") or [],
        daily_basic_rows=snapshot.get("daily_basic_rows") or [],
        forecast_rows=snapshot.get("forecast_rows") or [],
        baseline=snapshot.get("baseline") or {},
        source_probe=snapshot.get("source_probe") or {},
    )
    contract = build_contract(report)
    preflight = build_preflight(report)
    if not args.no_write_report:
        write_artifacts(report, contract, preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if preflight["result"] == "PREFLIGHT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
