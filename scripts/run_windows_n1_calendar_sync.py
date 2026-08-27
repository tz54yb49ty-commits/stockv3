#!/usr/bin/env python3
"""Synchronize the local REST calendar and stop at the Windows N1 final gate."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.windows_n1_calendar import sync_local_trade_calendar
from ashare_v3.ingestion.windows_n1_db_setup import PASSWORDLESS_APP_DSN
from ashare_v3.ingestion.windows_n1_postgres import WindowsN1PostgresRepository
from ashare_v3.ingestion.windows_n1_sources import LocalTradeCalendarProvider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")

    import psycopg
    provider = LocalTradeCalendarProvider(base_url="http://127.0.0.1:8000")
    with psycopg.connect(PASSWORDLESS_APP_DSN, connect_timeout=8) as connection:
        repository = WindowsN1PostgresRepository(connection)
        repository.verify_authority()
        result = sync_local_trade_calendar(provider=provider, repository=repository)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
