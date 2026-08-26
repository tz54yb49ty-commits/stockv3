#!/usr/bin/env python3
"""Interactive, one-time Windows N1 database authority setup."""

from __future__ import annotations

import getpass
import argparse
import json
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.windows_n1_db_setup import (
    OPERATOR_MODES, read_windows_identity, setup_database, validate_operator_identity,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operator-mode", choices=OPERATOR_MODES, default="ashare-ops")
    args = parser.parse_args()
    identity = read_windows_identity()
    validate_operator_identity(args.operator_mode, identity)
    password = getpass.getpass("Local PostgreSQL postgres password: ")
    if not password:
        raise SystemExit("setup cancelled: empty password")
    try:
        result = setup_database(
            admin_password=password,
            operator_mode=args.operator_mode,
            operator_identity=identity,
            schema_path=Path(__file__).resolve().parents[1] / "sql" / "001_raw_ingestion_schema.sql",
        )
    except Exception as error:
        # Never render vendor exception text: connection errors may echo parameters.
        raise SystemExit(f"setup failed safely ({type(error).__name__}); inspect database state read-only before retry") from None
    finally:
        password = ""
    print(json.dumps({
        "result": "WINDOWS_N1_SCHEMA_READY",
        "database": result.database,
        "app_role": result.role,
        "pgpass_path": str(result.pgpass_path),
        "business_row_counts": result.business_row_counts,
        "common_trade_calendar_rows": result.business_row_counts.get("common_trade_calendar", 0),
        "mac_import_count": 0,
        "n2_n6_writes": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
