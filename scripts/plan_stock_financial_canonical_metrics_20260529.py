#!/usr/bin/env python3
"""Plan N1 stock_financial canonical metrics 20260529 dry-run/preflight."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.stock_financial_canonical_metrics import (  # noqa: E402
    DEFAULT_PATHS,
    TRADE_DATE,
    StockFinancialCanonicalBlocked,
    build_dry_run_report,
    build_execute_contract,
    build_execute_preflight_report,
    build_snapshot_from_db,
    validate_dry_run_request,
    write_artifacts,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"))
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, dependencies: dict | None = None) -> int:
    args = parse_args(argv)
    deps = {
        "build_snapshot_from_db": build_snapshot_from_db,
        "write_artifacts": write_artifacts,
    }
    if dependencies:
        deps.update(dependencies)
    if args.source_trade_date != TRADE_DATE:
        print(f"BLOCKED: this runner is fixed to source_trade_date={TRADE_DATE}", file=sys.stderr)
        return 2
    try:
        validate_dry_run_request(execute_requested=args.execute)
    except StockFinancialCanonicalBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    snapshot = deps["build_snapshot_from_db"](dsn=args.dsn, source_trade_date=args.source_trade_date)
    dry_run = build_dry_run_report(snapshot)
    contract = build_execute_contract(snapshot, dry_run)
    preflight = build_execute_preflight_report(snapshot, dry_run)
    if not args.no_write_report:
        deps["write_artifacts"](dry_run, contract, preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2))
    return 0 if preflight["result"] == "PREFLIGHT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
