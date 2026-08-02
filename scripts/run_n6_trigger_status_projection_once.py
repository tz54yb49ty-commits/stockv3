#!/usr/bin/env python3
"""Run the isolated N6 trigger-status consumer once."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from ashare_v3.user.trigger_status_projection import (
    CONSUMER_NAME,
    PostgresTriggerStatusProjectionConsumer,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--projection-run-id", required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if not args.execute:
        return {
            "verdict": "N6_TRIGGER_STATUS_PROJECTION_PLAN_ONLY",
            "consumer_name": CONSUMER_NAME,
            "writes_database": False,
            "outbox_status_updates": 0,
        }
    if not args.user_confirmed:
        return {
            "verdict": "BLOCKED_N6_TRIGGER_STATUS_PROJECTION",
            "blocked_reason": "execute_requires_user_confirmed",
            "writes_database": False,
            "outbox_status_updates": 0,
        }
    result = PostgresTriggerStatusProjectionConsumer(args.dsn).consume_once(
        trade_date=args.for_trade_date,
        projection_run_id=args.projection_run_id,
        limit=args.limit,
    )
    return {
        "verdict": "N6_TRIGGER_STATUS_PROJECTION_EXECUTE_PASS",
        "writes_database": True,
        **asdict(result),
    }


def main() -> int:
    result = run(build_parser().parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if not str(result["verdict"]).startswith("BLOCKED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
