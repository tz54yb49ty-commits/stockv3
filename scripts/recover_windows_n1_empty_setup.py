#!/usr/bin/env python3
"""Interactive credential-only recovery for an exact empty Windows N1 database."""

from __future__ import annotations

import getpass
import json
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.windows_n1_db_setup import (
    OPERATOR_ELEVATED, read_windows_identity, recover_empty_setup,
    validate_operator_identity,
)


def main() -> int:
    identity = read_windows_identity()
    validate_operator_identity(OPERATOR_ELEVATED, identity)
    password = getpass.getpass("Local PostgreSQL postgres password: ")
    if not password:
        raise SystemExit("recovery cancelled: empty password")
    try:
        result = recover_empty_setup(
            admin_password=password, operator_identity=identity,
        )
    except Exception as error:
        raise SystemExit(
            f"recovery failed safely ({type(error).__name__}); inspect authority read-only before retry"
        ) from None
    finally:
        password = ""
    print(json.dumps({
        "result": "WINDOWS_N1_EMPTY_SETUP_RECOVERED",
        "database": result.database,
        "database_size": result.database_size,
        "app_role": result.role,
        "pgpass_path": str(result.pgpass_path),
        "business_row_counts": result.business_row_counts,
        "common_trade_calendar_rows": result.business_row_counts["common_trade_calendar"],
        "mac_import_count": 0,
        "n1_business_writes": 0,
        "n2_n6_writes": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
