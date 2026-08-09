#!/usr/bin/env python3
"""Retired N3-A1 current-lineage previous-day minute fill-facts/resume CLI.

The legacy resume path cannot satisfy the manager-pinned atomic batch contract.
Use the canonical previous_day_preload_execute entrypoint instead.
"""

from __future__ import annotations

import argparse
import os

from ashare_v3.market.previous_day_preload_fill import (
    DEFAULT_CURRENT_A1_FILL_CONTRACT_PATH,
    DEFAULT_CURRENT_A1_FILL_JSON_REPORT_PATH,
    DEFAULT_CURRENT_A1_FILL_MD_REPORT_PATH,
    DEFAULT_CURRENT_A1_FILL_POST_BACKUP_PATH,
    DEFAULT_CURRENT_A1_FILL_PRE_BACKUP_PATH,
    DEFAULT_CURRENT_A1_FILL_ROLLBACK_SQL_PATH,
    DEFAULT_CURRENT_A1_FILL_STATUS_SNAPSHOT_PATH,
)
try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


LEGACY_FILL_CLI_RETIRED = True
RETIREMENT_REASON = (
    "legacy fill-facts resume is retired; use canonical manager-pinned "
    "previous_day_preload_execute"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N3-A1 current-lineage previous-day minute fill-facts/resume.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", default=DEFAULT_CURRENT_A1_FILL_CONTRACT_PATH)
    parser.add_argument("--pre-backup-path", default=DEFAULT_CURRENT_A1_FILL_PRE_BACKUP_PATH)
    parser.add_argument("--post-backup-path", default=DEFAULT_CURRENT_A1_FILL_POST_BACKUP_PATH)
    parser.add_argument("--status-snapshot-path", default=DEFAULT_CURRENT_A1_FILL_STATUS_SNAPSHOT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_CURRENT_A1_FILL_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_CURRENT_A1_FILL_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_CURRENT_A1_FILL_ROLLBACK_SQL_PATH)
    parser.add_argument("--for-trade-date")
    parser.add_argument("--preload-run-id")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.parse_args()
    print(f"BLOCKED: {RETIREMENT_REASON}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
