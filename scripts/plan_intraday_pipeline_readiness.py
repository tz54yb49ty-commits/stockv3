#!/usr/bin/env python3
"""Plan N3-B1 -> N4 -> N5 intraday run-once readiness.

This runtime_control checker reads only repository docs/sql artifacts. It does
not connect to PostgreSQL, execute N3/N4/N5 commands, run rollback SQL, consume
outbox rows, start workers, trigger delivery/notification, or touch downstream
voice/mobile/sim/position/real-trade channels.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ashare_v3.runtime_control.intraday import build_intraday_fast_gate, build_intraday_pipeline_readiness


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--for-trade-date", required=True, help="Intraday target trade date, e.g. 20260602.")
    parser.add_argument("--minute-label", required=True, help="Minute label for action-confirmation chain, e.g. 1105.")
    parser.add_argument("--condition-run-id", required=True, help="Source N2 condition run id.")
    parser.add_argument("--b1-label", default="live3_outbox", help="B1 run label, e.g. live3_outbox.")
    parser.add_argument("--subscription-run-id", default=None, help="Optional explicit N3 subscription run id.")
    parser.add_argument("--docs-dir", default=str(PROJECT_ROOT / "docs"))
    parser.add_argument("--sql-dir", default=str(PROJECT_ROOT / "sql"))
    parser.add_argument("--json", action="store_true", help="Print JSON payload in analysis mode.")
    parser.add_argument("--fast-gate", action="store_true", help="Deprecated no-op; fast gate is the default.")
    parser.add_argument("--analysis", action="store_true", help="Print deferred analysis instead of the fast gate result.")
    parser.add_argument(
        "--deferred-analysis",
        action="store_true",
        help="Alias for --analysis; prints the full deferred analysis report.",
    )
    args = parser.parse_args()

    if not (args.analysis or args.deferred_analysis):
        report = build_intraday_fast_gate(
            for_trade_date=args.for_trade_date,
            minute_label=args.minute_label,
            condition_run_id=args.condition_run_id,
            b1_label=args.b1_label,
            subscription_run_id=args.subscription_run_id,
            sql_dir=Path(args.sql_dir),
        )
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["result"] == "PASS" else 2

    report = build_intraday_pipeline_readiness(
        for_trade_date=args.for_trade_date,
        minute_label=args.minute_label,
        condition_run_id=args.condition_run_id,
        b1_label=args.b1_label,
        subscription_run_id=args.subscription_run_id,
        docs_dir=Path(args.docs_dir),
        sql_dir=Path(args.sql_dir),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_summary(report))
    return 0 if report["result"] in {"PASS", "WARNING"} else 2


def format_summary(report: dict[str, Any]) -> str:
    lines = [
        "intraday pipeline readiness",
        f"  result={report['result']}",
        f"  for_trade_date={report['for_trade_date']}",
        f"  minute_label={report['minute_label']}",
        f"  rollback_registry={report['rollback_registry']['status']}",
        f"  run_id_rules={report['run_id_rules']['status']}",
    ]
    for stage in report["stages"]:
        lines.append(
            f"  {stage['stage_id']}={stage['status']} "
            f"artifact={stage['artifact_path']} rollback={stage['rollback_sql_path']}"
        )
    if report["warnings"]:
        lines.append("  warnings=" + ",".join(report["warnings"]))
    if report["blockers"]:
        lines.append("  blockers=" + ",".join(report["blockers"]))
    lines.append(f"  next_step={report['next_step']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
