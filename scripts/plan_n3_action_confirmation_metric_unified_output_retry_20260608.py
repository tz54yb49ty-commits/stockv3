#!/usr/bin/env python3
"""Generate 20260608 unified-output retry N3 action metric artifacts."""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.action_confirmation_metric_20260608_unified_retry import generate_artifacts


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=os.environ.get("ASHARE_V3_POSTGRES_DSN")
        or "host=127.0.0.1 port=5432 dbname=ashare_v3 user=ashare_v3_user",
        help="v3 runtime PostgreSQL DSN; defaults to local ashare_v3 without printing secrets",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    result = generate_artifacts(args.dsn)
    summary = {
        "result": result["final_gate"]["result"],
        "dry_run": result["dry_run"]["result"],
        "contract": result["contract"]["contract_result"],
        "preflight": result["preflight"]["result"],
        "rows": result["contract"]["expected_rows"],
        "metric_ready": result["contract"]["metric_ready_expected"],
        "rollback_static_check": result["rollback_static_check"]["passed"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
