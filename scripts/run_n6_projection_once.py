#!/usr/bin/env python3
"""Run N6 MVP shadow projection once after an explicit final gate.

The command requires --execute and --user-confirmed. Without both flags it
blocks before reading the database. When executed in a future authorized gate,
it writes only N6 projection/card/queued notification rows and never consumes
or updates N5 outbox status.
"""

from __future__ import annotations

import json
import os

from ashare_v3.user.projection_execute import build_parser, format_summary, parse_expected_n5_outbox_counts, run_projection_shadow_execute
from check_condition_source_ready import DEFAULT_DSN


SUCCESS_RESULTS = frozenset(
    {
        "EXECUTED",
        "PROJECTION_PASS_ZERO_USER_MESSAGES",
    }
)


def main() -> int:
    parser = build_parser()
    parser.set_defaults(dsn=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args()

    report = run_projection_shadow_execute(
        dsn=args.dsn,
        projection_run_id=args.projection_run_id,
        source_action_run_id=args.source_action_run_id,
        expected_n5_outbox_counts=parse_expected_n5_outbox_counts(args.expected_n5_outbox_count),
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
    return 0 if report.get("result") in SUCCESS_RESULTS else 2


if __name__ == "__main__":
    raise SystemExit(main())
