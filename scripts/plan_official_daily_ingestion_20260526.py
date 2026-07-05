#!/usr/bin/env python3
"""Generate N1 official daily 20260526 dry-run and execute contract artifacts.

This script is a dry-run/contract generator only. It may perform read-only
PostgreSQL checks and write docs/json/sql artifacts, but it cannot execute
ingestion, fetch market data, write PostgreSQL facts, write Parquet, update
active source versions, enter downstream layers, or start workers.
"""

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

from ashare_v3.ingestion.official_daily_20260526_contract import (  # noqa: E402
    DEFAULT_PATHS,
    TRADE_DATE,
    build_dry_run_plan,
    build_execute_contract,
    build_execute_preflight,
    build_snapshot_from_db,
    write_artifacts,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql:///ashare_v3"))
    parser.add_argument("--dry-run-json", default=str(DEFAULT_PATHS["dry_run_json"]))
    parser.add_argument("--dry-run-md", default=str(DEFAULT_PATHS["dry_run_md"]))
    parser.add_argument("--contract-json", default=str(DEFAULT_PATHS["contract_json"]))
    parser.add_argument("--contract-md", default=str(DEFAULT_PATHS["contract_md"]))
    parser.add_argument("--preflight-json", default=str(DEFAULT_PATHS["preflight_json"]))
    parser.add_argument("--preflight-md", default=str(DEFAULT_PATHS["preflight_md"]))
    parser.add_argument("--rollback-sql", default=str(DEFAULT_PATHS["rollback_sql"]))
    parser.add_argument("--no-write", action="store_true", help="Print reports only; do not write artifacts.")
    parser.add_argument("--execute", action="store_true", help="Rejected: this script has no ingestion write path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Rejected with --execute.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.execute:
        print(
            "BLOCKED: plan_official_daily_ingestion_20260526.py is a dry-run/contract generator only; "
            "it has no source fetch or PostgreSQL write path.",
            file=sys.stderr,
        )
        return 2
    if args.trade_date != TRADE_DATE:
        print(f"BLOCKED: this generator is fixed to trade_date={TRADE_DATE}", file=sys.stderr)
        return 2

    snapshot = build_snapshot_from_db(dsn=args.dsn, trade_date=args.trade_date)
    dry_run = build_dry_run_plan(snapshot)
    contract = build_execute_contract(snapshot)
    preflight = build_execute_preflight(snapshot)

    paths = {
        "dry_run_json": Path(args.dry_run_json),
        "dry_run_md": Path(args.dry_run_md),
        "contract_json": Path(args.contract_json),
        "contract_md": Path(args.contract_md),
        "preflight_json": Path(args.preflight_json),
        "preflight_md": Path(args.preflight_md),
        "rollback_sql": Path(args.rollback_sql),
    }
    written = {} if args.no_write else write_artifacts(snapshot, paths=paths)
    output = {
        "stage": "N1 official daily 20260526 dry-run/execute contract generation",
        "layer_role": "N1_ingestion",
        "result": "IMPLEMENTATION_PASS" if dry_run["result"] == "DRY_RUN_PASS" and contract["result"] == "DESIGN_PASS" else "BLOCKED",
        "dry_run_result": dry_run["result"],
        "execute_contract_result": contract["result"],
        "execute_preflight_result": preflight["result"],
        "runner_readiness": preflight["runner_readiness"],
        "final_execute_gate_allowed": preflight["final_execute_gate_allowed"],
        "expected_scope": dry_run["expected_scope"],
        "missing_official_daily": dry_run["missing_official_daily"],
        "quality": preflight["quality"],
        "written_artifacts": written,
        "side_effects": dry_run["side_effects"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["result"] == "IMPLEMENTATION_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
