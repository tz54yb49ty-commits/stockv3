#!/usr/bin/env python3
"""Print Parquet archive directory readiness checks without side effects."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT
from ashare_v3.ingestion.parquet_readiness import build_parquet_readiness_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT, help="Planned root for Parquet archive data files.")
    args = parser.parse_args()

    report = build_parquet_readiness_report(data_root=args.data_root)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
