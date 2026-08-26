#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from typing import Any, Callable

import psycopg


RETENTION_POLICY = "current_trade_date_plus_previous_5_completed_trade_dates_v1"
TRADE_DATE_RE = re.compile(r"^[0-9]{8}$")


def read_retained_trade_dates(
    dsn: str,
    *,
    current_date: str,
    connection_factory: Callable[..., Any] = psycopg.connect,
) -> list[str]:
    if not TRADE_DATE_RE.fullmatch(current_date):
        raise ValueError("current_date must be YYYYMMDD")

    connection = connection_factory(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT trade_date
                FROM common_trade_calendar
                WHERE is_open IS TRUE
                  AND trade_date <= %s
                ORDER BY trade_date DESC
                LIMIT 6
                """,
                (current_date,),
            )
            retained_trade_dates = [str(row[0]) for row in cursor.fetchall()]
    finally:
        connection.close()

    if len(retained_trade_dates) != 6:
        raise RuntimeError(
            "calendar authority did not return current trade date plus five predecessors"
        )
    if any(not TRADE_DATE_RE.fullmatch(value) for value in retained_trade_dates):
        raise RuntimeError("calendar authority returned an invalid trade_date")
    return retained_trade_dates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read the archive-gated disk-governance retained date set."
    )
    parser.add_argument("--dsn", required=True)
    parser.add_argument(
        "--current-date",
        default=date.today().strftime("%Y%m%d"),
        help="Calendar upper bound in YYYYMMDD form.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    retained_trade_dates = read_retained_trade_dates(
        args.dsn,
        current_date=args.current_date,
    )
    print(
        json.dumps(
            {
                "result": "RUNTIME_DISK_GOVERNANCE_RETAINED_DATES_READ_ONLY_PASS",
                "retention_policy": RETENTION_POLICY,
                "trade_calendar_authority": "common_trade_calendar",
                "current_date": args.current_date,
                "current_trade_date": retained_trade_dates[0],
                "retained_trade_dates": retained_trade_dates,
                "database_read_only": True,
                "database_writes": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
