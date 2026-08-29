#!/usr/bin/env python3
"""Native Windows one-shot N5 committed Outbox -> N6 projection consumer.

The existing projection transaction remains authoritative.  This wrapper skips
the macOS filesystem lock and relies on the transaction's PostgreSQL advisory
lock plus Inbox/checkpoint idempotency.  It never updates N5 Outbox status.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SOURCE_DIR = SCRIPT_DIR.parent / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from run_n6_b_track_signal_projection_poller_once import (  # noqa: E402
    MAX_INTERNAL_BATCH_SIZE,
    PostgresBTrackProjectionRepository,
    WINDOWS_N6_CONSUMER_NAME,
    run_b_track_signal_projection_poller,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN") or os.environ.get("ASHARE_V3_DSN"))
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--consumer-name", default=WINDOWS_N6_CONSUMER_NAME)
    parser.add_argument("--max-events", type=int, default=MAX_INTERNAL_BATCH_SIZE)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.dsn:
        report = {"result": "BLOCKED", "reason": "dsn_missing", "database_write_count": 0}
    elif args.execute and not args.user_confirmed:
        report = {"result": "BLOCKED", "reason": "execute_confirmation_missing", "database_write_count": 0}
    else:
        report = run_b_track_signal_projection_poller(
            repository=PostgresBTrackProjectionRepository(
                args.dsn,
                windows_projection_contract=True,
            ),
            dsn=args.dsn,
            for_trade_date=args.for_trade_date,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            consumer_name=args.consumer_name,
            max_events=args.max_events,
            cas_authority_mode="internal_one_shot",
            write_reports=False,
        )
    report["runtime_platform"] = "windows"
    report["os_singleton_lock"] = "not_used"
    report["transaction_singleton"] = "postgres_advisory_xact_lock"
    report.setdefault("n5_outbox_status_update_count", 0)
    report.setdefault("notification_write_count", 0)
    report.setdefault("virtual_trade_write_count", 0)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report.get("result") in {"EXECUTE_PASS", "NOOP", "PREFLIGHT_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
