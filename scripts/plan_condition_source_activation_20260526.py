#!/usr/bin/env python3
"""Generate 20260526 N1 condition source activation contract/dry-run artifacts.

This runner is dry-run/contract generation only. It may perform read-only
PostgreSQL checks and read local TDX txt membership files, then write docs/json
and rollback SQL artifacts. It cannot execute ingestion, write PostgreSQL,
write Parquet, update active source versions, enter downstream layers, or start
workers.
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

from ashare_v3.ingestion.condition_source_activation_20260526 import (  # noqa: E402
    DEFAULT_PATHS,
    TDX_ROOT,
    TRADE_DATE,
    build_contract,
    build_dry_run_report,
    build_preflight,
    build_snapshot_from_db,
    write_artifacts,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql:///ashare_v3"))
    parser.add_argument("--tdx-root", default=str(TDX_ROOT))
    parser.add_argument("--contract-json", default=str(DEFAULT_PATHS["contract_json"]))
    parser.add_argument("--contract-md", default=str(DEFAULT_PATHS["contract_md"]))
    parser.add_argument("--dry-run-json", default=str(DEFAULT_PATHS["dry_run_json"]))
    parser.add_argument("--dry-run-md", default=str(DEFAULT_PATHS["dry_run_md"]))
    parser.add_argument("--preflight-json", default=str(DEFAULT_PATHS["preflight_json"]))
    parser.add_argument("--preflight-md", default=str(DEFAULT_PATHS["preflight_md"]))
    parser.add_argument("--rollback-sql", default=str(DEFAULT_PATHS["rollback_sql"]))
    parser.add_argument("--no-write", action="store_true", help="Print only; do not write artifacts.")
    parser.add_argument("--json", action="store_true", help="Print full report JSON to stdout.")
    parser.add_argument("--execute", action="store_true", help="Rejected: this script has no write path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Rejected with --execute.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, dependencies: Mapping[str, Any] | None = None) -> int:
    args = parse_args(argv)
    if args.execute:
        print(
            "BLOCKED: plan_condition_source_activation_20260526.py is a dry-run/contract generator only; "
            "it has no PostgreSQL write path.",
            file=sys.stderr,
        )
        return 2
    if args.trade_date != TRADE_DATE:
        print(f"BLOCKED: this generator is fixed to trade_date={TRADE_DATE}", file=sys.stderr)
        return 2

    deps = dict(dependencies or {})
    snapshot_builder = deps.get("build_snapshot_from_db", build_snapshot_from_db)
    snapshot = snapshot_builder(dsn=args.dsn, trade_date=args.trade_date, tdx_root=Path(args.tdx_root))
    contract = build_contract(snapshot)
    dry_run = build_dry_run_report(snapshot)
    preflight = build_preflight(snapshot)

    paths = {
        "contract_json": Path(args.contract_json),
        "contract_md": Path(args.contract_md),
        "dry_run_json": Path(args.dry_run_json),
        "dry_run_md": Path(args.dry_run_md),
        "preflight_json": Path(args.preflight_json),
        "preflight_md": Path(args.preflight_md),
        "rollback_sql": Path(args.rollback_sql),
    }
    written = {} if args.no_write else write_artifacts(snapshot, paths=paths)
    result = {
        "stage": "N1 condition source 20260526 activation contract/dry-run",
        "layer_role": "N1_ingestion",
        "result": "IMPLEMENTATION_PASS"
        if dry_run["result"] == "DRY_RUN_PASS" and contract["result"] == "DESIGN_PASS" and preflight["result"] == "PREFLIGHT_PASS"
        else "BLOCKED",
        "trade_date": args.trade_date,
        "dry_run_result": dry_run["result"],
        "contract_result": contract["result"],
        "preflight_result": preflight["result"],
        "runner_readiness": preflight["runner_readiness"],
        "final_execute_gate_allowed": preflight["final_execute_gate_allowed"],
        "execute_runner_implementation_allowed": preflight["execute_runner_implementation_allowed"],
        "expected_rows": dry_run["expected_rows"],
        "quality": preflight["quality"],
        "written_artifacts": written,
        "side_effects": dry_run["side_effects"],
    }
    if args.json:
        print(json.dumps({**result, "dry_run": dry_run, "contract": contract, "preflight": preflight}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "IMPLEMENTATION_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
