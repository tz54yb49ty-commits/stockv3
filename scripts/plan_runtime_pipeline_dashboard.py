#!/usr/bin/env python3
"""Render runtime pipeline dashboard v0.

This command is control-plane only: it does not connect to PostgreSQL, execute
registered commands, run rollback SQL, start workers, or modify N1-N6 execute
contracts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ashare_v3.runtime_control.pipeline import (
    build_action_confirmation_pipeline_run,
    build_nightly_pipeline_run,
    render_dashboard_markdown,
)
from ashare_v3.web.runtime_dashboard import DEFAULT_DOCS_DIR, build_dashboard_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", required=True, help="Pipeline trade date in YYYYMMDD format.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    parser.add_argument(
        "--docs-dir",
        default=str(DEFAULT_DOCS_DIR),
        help="Docs artifact directory used for read-only JSON artifact detection.",
    )
    args = parser.parse_args()

    if args.json:
        payload = build_dashboard_payload(trade_date=args.trade_date, docs_dir=Path(args.docs_dir))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if args.trade_date == "20260602":
            run = build_action_confirmation_pipeline_run(trade_date=args.trade_date)
        else:
            run = build_nightly_pipeline_run(trade_date=args.trade_date)
        print(render_dashboard_markdown(run), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
