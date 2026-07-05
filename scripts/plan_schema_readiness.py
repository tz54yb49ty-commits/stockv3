#!/usr/bin/env python3
"""Print PostgreSQL schema readiness checks without executing SQL."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.schema_readiness import DEFAULT_SCHEMA_PATH, build_schema_readiness_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA_PATH, help="PostgreSQL schema SQL file to check statically.")
    args = parser.parse_args()

    report = build_schema_readiness_report(args.schema)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
