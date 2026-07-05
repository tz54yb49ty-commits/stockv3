#!/usr/bin/env python3
"""Print a top-level raw-ingestion dry-run control report."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.backfill_config import DEFAULT_INITIAL_BACKFILL_CONFIG
from ashare_v3.ingestion.daily_incremental_config import DEFAULT_DAILY_INCREMENTAL_CONFIG
from ashare_v3.ingestion.ingestion_dry_run_control import build_ingestion_dry_run_control_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-config", default=DEFAULT_INITIAL_BACKFILL_CONFIG, help="Initial backfill TOML config path. Values remain dry-run only.")
    parser.add_argument("--daily-config", default=DEFAULT_DAILY_INCREMENTAL_CONFIG, help="Daily incremental TOML config path. Values remain dry-run only.")
    args = parser.parse_args()

    report = build_ingestion_dry_run_control_report(
        initial_config_path=args.initial_config,
        daily_config_path=args.daily_config,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
