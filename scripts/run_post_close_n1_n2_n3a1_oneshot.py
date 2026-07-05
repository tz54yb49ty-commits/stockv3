#!/usr/bin/env python3
"""Run the post-close N1 -> N2 -> N3-A1 one-shot wrapper."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ashare_v3.runtime.post_close_fastlane import (  # noqa: E402
    DateContext,
    derive_date_context_from_calendar,
    run_post_close_oneshot,
    next_weekday_yyyymmdd,
)


DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-trade-date")
    parser.add_argument("--for-trade-date")
    parser.add_argument("--prev-trade-date")
    parser.add_argument("--fallback-next-trade-date")
    parser.add_argument("--auto-dates-from-calendar", action="store_true")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--docs-root", default="docs/post_close_fastlane")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--include-calendar-repair", action="store_true")
    parser.add_argument("--skip-calendar-repair", action="store_true")
    parser.add_argument("--force-rerun-after-blocked", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--postgres-commit-enabled", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.auto_dates_from_calendar:
            context = derive_date_context_from_calendar(dsn=args.dsn)
        else:
            missing = [
                name
                for name, value in (
                    ("--source-trade-date", args.source_trade_date),
                    ("--for-trade-date", args.for_trade_date),
                )
                if not value
            ]
            if missing:
                raise ValueError("missing required date args: " + ", ".join(missing))
            context = DateContext(
                source_trade_date=args.source_trade_date,
                for_trade_date=args.for_trade_date,
                prev_trade_date=args.prev_trade_date or "",
                fallback_next_trade_date=args.fallback_next_trade_date
                or next_weekday_yyyymmdd(args.for_trade_date),
            )
        if not context.prev_trade_date:
            raise ValueError("--prev-trade-date is required unless --auto-dates-from-calendar is used")

        include_calendar_repair: bool | None
        if args.include_calendar_repair and args.skip_calendar_repair:
            raise ValueError("--include-calendar-repair and --skip-calendar-repair are mutually exclusive")
        if args.include_calendar_repair:
            include_calendar_repair = True
        elif args.skip_calendar_repair:
            include_calendar_repair = False
        else:
            include_calendar_repair = None

        report = run_post_close_oneshot(
            source_trade_date=context.source_trade_date,
            for_trade_date=context.for_trade_date,
            prev_trade_date=context.prev_trade_date,
            next_trade_date=context.fallback_next_trade_date,
            dsn=args.dsn,
            docs_root=args.docs_root,
            sql_root=args.sql_root,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            postgres_commit_enabled=args.postgres_commit_enabled,
            include_calendar_repair=include_calendar_repair,
            force_rerun_after_blocked=args.force_rerun_after_blocked,
            python_executable=args.python_executable,
        )
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(report.get("result"))
    return 0 if report.get("result") in {"EXECUTE_PASS", "NOOP"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
