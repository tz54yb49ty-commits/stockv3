#!/usr/bin/env python3
"""Plan one daily N1 stock_financial canonical source bundle.

This runner is no-write. It may perform explicit read-only source probes when
`--source-fetch-enabled` is provided, but it never writes PostgreSQL, Parquet,
active source versions, condition tables, or outbox/inbox/checkpoint rows.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.tushare_env import load_tushare_token  # noqa: E402
from ashare_v3.ingestion.common import require_yyyymmdd  # noqa: E402
import ashare_v3.ingestion.stock_financial_canonical_source_bundle as source_bundle  # noqa: E402


DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-trade-date", "--trade-date", required=True)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN") or DEFAULT_DSN)
    parser.add_argument("--source-fetch-enabled", action="store_true", help="Enable read-only TDX/Mootdx and Tushare source probes.")
    parser.add_argument("--tushare-only", action="store_true", help="Skip the TDX/Mootdx primary probe and use the Tushare batch source only.")
    parser.add_argument("--max-symbols", type=int, default=None, help="Optional probe cap. 0 means full active universe only with --full-fetch-confirmed.")
    parser.add_argument("--symbol-shard", help="Optional 1-based shard selector in N/M format, applied before the probe cap.")
    parser.add_argument("--resume-cache-path", help="Local JSON cache path for read-only Tushare probe responses.")
    parser.add_argument("--incremental", action="store_true", help="Use financial_canonical_snapshot_v1 and fetch only changed symbols.")
    parser.add_argument("--previous-snapshot-path", help="Previous financial_canonical_snapshot_v1 path used for unchanged symbols.")
    parser.add_argument("--snapshot-cache-path", help="Output financial_canonical_snapshot_v1 path for the metrics runner.")
    parser.add_argument("--changed-identity-key", action="append", default=[], help="Force one identity_key into the incremental delta set.")
    parser.add_argument("--full-rebuild-confirmed", action="store_true", help="Explicitly allow a full rebuild when no previous snapshot can be reused.")
    parser.add_argument("--rate-limit-ms", type=int, default=300, help="Milliseconds to wait between Tushare requests when source fetch is enabled.")
    parser.add_argument("--tushare-concurrency", type=int, default=1, help="Bounded worker count for per-symbol Tushare source fetches.")
    parser.add_argument("--full-fetch-confirmed", action="store_true", help="Allow unbounded source probe when --max-symbols 0 is also supplied.")
    parser.add_argument("--dry-run-json")
    parser.add_argument("--dry-run-md")
    parser.add_argument("--contract-json")
    parser.add_argument("--contract-md")
    parser.add_argument("--preflight-json")
    parser.add_argument("--preflight-md")
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Rejected: this is a dry-run/source-probe runner only.")
    return parser.parse_args(argv)


def apply_path_overrides(args: argparse.Namespace) -> None:
    paths = dict(source_bundle.DEFAULT_PATHS)
    overrides = {
        "dry_run_json": args.dry_run_json,
        "dry_run_md": args.dry_run_md,
        "contract_json": args.contract_json,
        "contract_md": args.contract_md,
        "preflight_json": args.preflight_json,
        "preflight_md": args.preflight_md,
    }
    for key, raw_path in overrides.items():
        if raw_path:
            paths[key] = Path(raw_path)
    source_bundle.DEFAULT_PATHS = paths


def main(argv: list[str] | None = None, *, dependencies: Mapping[str, Any] | None = None) -> int:
    args = parse_args(argv)
    source_trade_date = require_yyyymmdd(args.source_trade_date, "source_trade_date")
    source_bundle.apply_source_bundle_context(source_trade_date)
    apply_path_overrides(args)
    resume_cache_path = args.resume_cache_path or str(source_bundle.DEFAULT_TUSHARE_CACHE_PATH)
    deps = dict(dependencies or {})
    try:
        source_bundle.validate_source_bundle_request(execute_requested=args.execute)
    except source_bundle.StockFinancialCanonicalSourceBundleBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    snapshot_builder = deps.get("build_snapshot_from_db", source_bundle.build_snapshot_from_db)
    try:
        snapshot = snapshot_builder(
            dsn=args.dsn,
            source_trade_date=source_trade_date,
            source_fetch_enabled=args.source_fetch_enabled,
            max_symbols=args.max_symbols,
            symbol_shard=args.symbol_shard,
            resume_cache_path=resume_cache_path,
            rate_limit_ms=args.rate_limit_ms,
            full_fetch_confirmed=args.full_fetch_confirmed,
            incremental_enabled=args.incremental,
            previous_snapshot_path=args.previous_snapshot_path,
            snapshot_cache_path=args.snapshot_cache_path,
            changed_identity_keys=args.changed_identity_key,
            full_rebuild_confirmed=args.full_rebuild_confirmed,
            use_tdx_source=not args.tushare_only,
            tushare_concurrency=args.tushare_concurrency,
            tushare_token=load_tushare_token(),
        )
    except source_bundle.StockFinancialCanonicalSourceBundleBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    report = source_bundle.build_source_bundle_report(
        source_trade_date=source_trade_date,
        expected_identity_keys=snapshot.get("expected_identity_keys") or [],
        tdx_rows=snapshot.get("tdx_rows") or [],
        tushare_rows=snapshot.get("tushare_rows") or [],
        daily_basic_rows=snapshot.get("daily_basic_rows") or [],
        forecast_rows=snapshot.get("forecast_rows") or [],
        baseline=snapshot.get("baseline") or {},
        source_probe=snapshot.get("source_probe") or {},
    )
    contract = source_bundle.build_contract(report)
    preflight = source_bundle.build_preflight(report)
    if args.snapshot_cache_path:
        financial_snapshot = source_bundle.build_financial_canonical_snapshot_v1(
            source_trade_date=source_trade_date,
            active_source_version=(snapshot.get("baseline") or {}).get("active_stock_financial_source_version"),
            expected_identity_keys=snapshot.get("expected_identity_keys") or [],
            current_signature_rows=snapshot.get("current_signature_rows") or [],
            financial_rows=[*(snapshot.get("tdx_rows") or []), *(snapshot.get("tushare_rows") or [])],
            forecast_rows=snapshot.get("forecast_rows") or [],
            daily_basic_rows=snapshot.get("daily_basic_rows") or [],
            source_probe=snapshot.get("source_probe") or {},
        )
        if not args.no_write_report:
            source_bundle.write_financial_canonical_snapshot_v1(args.snapshot_cache_path, financial_snapshot)
    if not args.no_write_report:
        source_bundle.write_artifacts(report, contract, preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if preflight["result"] == "PREFLIGHT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
