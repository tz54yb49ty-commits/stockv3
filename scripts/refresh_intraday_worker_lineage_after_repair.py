#!/usr/bin/env python3
"""Refresh active intraday worker lineage after a scoped Fast Lane repair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_v3.runtime.intraday_worker_lineage import (
    LINEAGE_REFRESH_BLOCKED_FASTLANE_NOT_PASS,
    build_intraday_worker_lineage_refresh_report,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh current intraday worker lineage after Fast Lane repair.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--docs-root", default="docs/post_close_fastlane")
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--updated-by", default="runtime_control_status_repair")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    docs_root = Path(args.docs_root)
    docs_dir = docs_root / args.for_trade_date
    report = build_intraday_worker_lineage_refresh_report(
        docs_root=docs_root,
        docs_dir=docs_dir,
        updated_by=args.updated_by,
        execute=bool(args.execute),
    )
    report_path = Path(args.json_report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    result = str(report.get("result") or "")
    if result.startswith("BLOCKED") or result == LINEAGE_REFRESH_BLOCKED_FASTLANE_NOT_PASS:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
