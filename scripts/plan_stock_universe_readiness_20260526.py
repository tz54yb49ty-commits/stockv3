#!/usr/bin/env python3
"""Generate the N1 20260526 stock universe readiness source-gap report.

This is a dry-run runner only. It may perform read-only PostgreSQL and source
checks and write docs/json report artifacts. It cannot execute ingestion,
write PostgreSQL facts, write Parquet, update active source versions, enter
downstream layers, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.tushare_env import load_tushare_token  # noqa: E402

from ashare_v3.ingestion.stock_universe_readiness_20260526 import (  # noqa: E402
    DEFAULT_JSON_PATH,
    DEFAULT_MD_PATH,
    TRADE_DATE,
    normalize_jsonable,
    run_readiness_planner,
    write_report_artifacts,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql:///ashare_v3"))
    parser.add_argument("--tushare-token", default=load_tushare_token())
    parser.add_argument("--json-path", default=str(DEFAULT_JSON_PATH))
    parser.add_argument("--md-path", default=str(DEFAULT_MD_PATH))
    parser.add_argument("--json", action="store_true", help="Print the readiness report JSON to stdout.")
    parser.add_argument("--no-write", action="store_true", help="Do not write docs/json artifacts.")
    parser.add_argument("--execute", action="store_true", help="Rejected: this runner has no write path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Rejected with --execute.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, dependencies: Mapping[str, Any] | None = None) -> int:
    args = parse_args(argv)
    if args.execute:
        print(
            "BLOCKED: plan_stock_universe_readiness_20260526.py is dry-run only; "
            "it cannot execute ingestion or write PostgreSQL.",
            file=sys.stderr,
        )
        return 2
    if args.trade_date != TRADE_DATE:
        print(f"BLOCKED: this runner is fixed to trade_date={TRADE_DATE}", file=sys.stderr)
        return 2

    deps = dict(dependencies or {})
    planner = deps.get("run_planner", run_readiness_planner)
    report = planner(dsn=args.dsn, tushare_token=args.tushare_token, trade_date=args.trade_date)
    written = {} if args.no_write else write_report_artifacts(
        report,
        json_path=Path(args.json_path),
        md_path=Path(args.md_path),
    )
    output = normalize_jsonable({**report, "written_artifacts": written})
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                {
                    "result": output["result"],
                    "raw_active_universe": output["raw_active_universe"],
                    "effective_active_universe": output["effective_active_universe"],
                    "tushare_daily_matched": output["tushare_daily_matched"],
                    "unresolved_daily_missing_active": output["unresolved_daily_missing_active"],
                    "supplemental_source_available": output["supplemental_source_available"],
                    "quality": output["quality"],
                    "official_daily_ingest_v2_allowed": output["official_daily_ingest_v2_allowed"],
                    "written_artifacts": written,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
