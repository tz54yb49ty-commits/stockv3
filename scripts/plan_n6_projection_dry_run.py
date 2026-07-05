#!/usr/bin/env python3
"""Plan N6 user projection dry-run.

This script reads pending N5 action outbox rows plus the admin user/profile.
The canonical path supports ActionEligible / ActionBlocked / ActionExecuted /
ActionSkipped; ActionEvent / HintEvent remain compatibility inputs only. It
writes dry-run report artifacts only. It does not write N6 projection tables,
consume or update N5 outbox, create sessions, write decisions or sim rows,
start workers, push notifications, or place trades.
"""

from __future__ import annotations

import json
import os

from ashare_v3.user.projection_plan import (
    build_parser,
    format_summary,
    parse_expected_n5_outbox_counts,
    run_projection_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_parser()
    parser.set_defaults(dsn=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args()

    report = run_projection_dry_run(
        dsn=args.dsn,
        execute=args.execute,
        source_action_run_id=args.source_action_run_id,
        user_projection_run_id=args.user_projection_run_id,
        expected_n5_outbox_counts=parse_expected_n5_outbox_counts(args.expected_n5_outbox_count),
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        sample_limit=args.sample_limit,
        write_reports=True,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
