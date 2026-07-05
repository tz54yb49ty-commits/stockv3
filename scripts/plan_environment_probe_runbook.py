#!/usr/bin/env python3
"""Print the N3.10 environment probe runbook dry-run report."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.environment_probe_runbook import build_environment_probe_runbook


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-config", default="configs/initial_backfill.example.toml")
    parser.add_argument("--daily-config", default="configs/daily_incremental.example.toml")
    parser.add_argument("--real-config", default="configs/real_execution.example.toml")
    parser.add_argument("--schema", default="sql/001_raw_ingestion_schema.sql")
    parser.add_argument("--data-root", default="/Volumes/MacRaid/database")
    args = parser.parse_args()

    runbook = build_environment_probe_runbook(
        initial_config_path=args.initial_config,
        daily_config_path=args.daily_config,
        real_config_path=args.real_config,
        schema_path=args.schema,
        data_root=args.data_root,
    )
    print(json.dumps(runbook.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
