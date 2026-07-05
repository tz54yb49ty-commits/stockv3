#!/usr/bin/env python3
"""Run scoped V3 historical closed-minute source expansion once."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from ashare_v3.market.historical_closed_minute_source_expansion import (
    DEFAULT_PAYLOAD_PATH,
    DEFAULT_REPORT_MD_PATH,
    DEFAULT_REPORT_PATH,
    HistoricalClosedMinuteSourceExpansionBlocked,
    run_historical_closed_minute_source_expansion,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--payload-path", default=DEFAULT_PAYLOAD_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_REPORT_MD_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_historical_closed_minute_source_expansion(
            dsn=args.dsn,
            payload_path=args.payload_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            progress_callback=print,
            progress_every=args.progress_every,
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                "V3 historical closed-minute source expansion "
                f"result={report.get('result')} run_id={report.get('target_expansion_run_id')}"
            )
        return 0 if report.get("result") in {"PLAN_ONLY", "EXECUTE_PASS"} else 2
    except HistoricalClosedMinuteSourceExpansionBlocked as exc:
        report = {
            "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
            "result": "BLOCKED",
            "blocked_reason": str(exc),
            "database_written": False,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
