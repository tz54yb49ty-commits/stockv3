#!/usr/bin/env python3
"""Run N6 Phase 3 admin virtual account seed once after final gate."""

from __future__ import annotations

import json
import os
from decimal import Decimal

from ashare_v3.user.virtual_account_seed import (
    build_parser,
    format_summary,
    run_virtual_account_seed,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_parser()
    parser.set_defaults(dsn=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args()

    report = run_virtual_account_seed(
        dsn=args.dsn,
        seed_run_id=args.seed_run_id,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        contract_path=args.contract_path,
        rollback_sql_path=args.rollback_sql_path,
        initial_cash=Decimal(str(args.initial_cash)),
        trade_date=args.trade_date,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("result") == "EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
