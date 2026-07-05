#!/usr/bin/env python3
"""Run N6 Phase 2 owner/principal initialization once after final gate."""

from __future__ import annotations

import json
import os

from ashare_v3.user.owner_principal_initialization import (
    build_parser,
    format_summary,
    run_owner_principal_initialization,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_parser()
    parser.set_defaults(dsn=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args()

    report = run_owner_principal_initialization(
        dsn=args.dsn,
        seed_run_id=args.seed_run_id,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        contract_path=args.contract_path,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("result") == "EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
