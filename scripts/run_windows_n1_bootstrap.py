#!/usr/bin/env python3
"""Windows N1 bootstrap entrypoint; plan is safe, execute is fail-closed."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from ashare_v3.ingestion.windows_n1_bootstrap import N1_BOOTSTRAP_STAGES, WindowsN1BootstrapConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", default=r"C:\AshareV3\artifacts\n1")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.plan == args.execute:
        parser.error("choose exactly one of --plan or --execute")
    config = WindowsN1BootstrapConfig.for_today(artifact_root=Path(args.artifact_root), today=date.today())
    if args.execute:
        raise SystemExit("execute wiring is blocked until native TQ and eltdx capability smoke pass")
    print(json.dumps({
        "mode": "plan",
        "layer_role": "N1_ingestion",
        "start_date": config.start_date,
        "end_date": config.end_date,
        "tq_url": config.tq_url,
        "stages": list(N1_BOOTSTRAP_STAGES),
        "calendar_external": True,
        "writes_common_trade_calendar": False,
        "starts_scheduler": False,
        "touches_n2_n6": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
