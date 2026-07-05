#!/usr/bin/env python3
"""Run a local TDX txt ingestion dry-run without database or file writes."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.tdx_local import TDXLocalTxtSource, run_tdx_local_ingestion_dry_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tdx-root", default="/Volumes/MacRaid/tdxdata/tdx")
    parser.add_argument("--trade-date", default="20260521")
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()

    source = TDXLocalTxtSource(args.tdx_root)
    result = run_tdx_local_ingestion_dry_run(source, trade_date=args.trade_date, version=args.version)
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
