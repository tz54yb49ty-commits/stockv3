#!/usr/bin/env python3
"""Run a controlled read-only index/board source probe for 20260601.

Default mode is a small sample. Full mode requires --full-fetch-confirmed and
is still read-only.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.tushare_env import load_tushare_token  # noqa: E402

from ashare_v3.ingestion.official_daily_20260601_execute import (  # noqa: E402
    DEFAULT_PATHS,
    TRADE_DATE,
    DefaultOfficialDaily20260601SourceAdapter,
    build_expected_scope_from_db,
    build_index_board_probe_from_adapter,
    sort_index_probe_candidates,
    write_json,
    write_markdown,
)
from check_condition_source_ready import DEFAULT_DSN  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--mode", choices=["sample", "full"], default="sample")
    parser.add_argument("--max-indexes", type=int, default=3)
    parser.add_argument("--max-boards", type=int, default=4)
    parser.add_argument("--mootdx-offset", type=int, default=900)
    parser.add_argument("--full-fetch-confirmed", action="store_true")
    parser.add_argument("--json-report-path", default=str(DEFAULT_PATHS["index_board_probe_json"]))
    parser.add_argument("--markdown-report-path", default=str(DEFAULT_PATHS["index_board_probe_md"]))
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.trade_date != TRADE_DATE:
        print(f"BLOCKED: this probe is fixed to trade_date={TRADE_DATE}", file=sys.stderr)
        return 2
    if args.mode == "full" and not args.full_fetch_confirmed:
        print("BLOCKED: full index/board source probe requires --full-fetch-confirmed", file=sys.stderr)
        return 2

    scope = build_expected_scope_from_db(dsn=args.dsn, trade_date=args.trade_date)
    indexes = sort_index_scope(scope["index"])
    boards = list(scope["board"])
    if args.mode == "sample":
        indexes = indexes[: max(0, args.max_indexes)]
        boards = boards[: max(0, args.max_boards)]

    adapter = DefaultOfficialDaily20260601SourceAdapter(
        tushare_token=load_tushare_token(),
        mootdx_offset=args.mootdx_offset,
    )
    report = build_index_board_probe_from_adapter(
        adapter=adapter,
        trade_date=args.trade_date,
        mode=args.mode,
        index_scope=indexes,
        board_scope=boards,
    )
    if not args.no_write_report:
        write_json(args.json_report_path, report)
        write_markdown(args.markdown_report_path, "N1 Official Daily 20260601 Index/Board Source Probe", report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"{report['result']} index={report['source_counts']['index']} board={report['source_counts']['board']}")
    return 0 if report["quality"]["p0_count"] == 0 else 1


def sort_index_scope(indexes: list[dict]) -> list[dict]:
    rows = [{"index_identity_key": row.get("identity_key"), "position": index} for index, row in enumerate(indexes)]
    ordered_positions = [int(row["position"]) for row in sort_index_probe_candidates(rows)]
    return [indexes[position] for position in ordered_positions]


if __name__ == "__main__":
    raise SystemExit(main())
