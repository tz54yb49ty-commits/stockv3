#!/usr/bin/env python3
"""Run N6 no-op delivery notification materialization after final gate.

The command requires --execute and --user-confirmed. The runner materializes
local preview rows only and does not contact providers, push, voice, mobile,
sim, position, real trade, worker, or N5 outbox status.
"""

from __future__ import annotations

import json
import os

from ashare_v3.user.delivery_execute import build_parser, format_summary, run_delivery_materialization_execute
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_parser()
    parser.set_defaults(dsn=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args()

    report = run_delivery_materialization_execute(
        dsn=args.dsn,
        source_projection_run_id=args.source_projection_run_id,
        delivery_materialization_run_id=args.delivery_materialization_run_id,
        source_action_run_id=args.source_action_run_id,
        expected_source_count=args.expected_source_count,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        contract_json_path=args.contract_json_path,
        preflight_json_path=args.preflight_json_path,
        rollback_sql_path=args.rollback_sql_path,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("result") == "EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
