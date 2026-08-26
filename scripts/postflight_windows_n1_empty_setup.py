#!/usr/bin/env python3
"""Read-only ashare-ops postflight for recovered Windows N1 credentials."""

from __future__ import annotations

import json
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.windows_n1_db_setup import postflight_empty_setup


def main() -> int:
    try:
        result = postflight_empty_setup()
    except Exception as error:
        raise SystemExit(f"postflight failed ({type(error).__name__})") from None
    print(json.dumps({
        "result": "WINDOWS_N1_EMPTY_SETUP_POSTFLIGHT_PASS",
        "database": result.database,
        "app_role": result.role,
        "pgpass_path": str(result.pgpass_path),
        "business_row_counts": result.business_row_counts,
        "common_trade_calendar_rows": result.business_row_counts["common_trade_calendar"],
        "database_writes": 0,
        "n2_n6_writes": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
