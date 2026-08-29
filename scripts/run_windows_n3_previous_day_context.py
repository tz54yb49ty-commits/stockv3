#!/usr/bin/env python3
"""Build resumable Windows N3 compressed previous-day context after N2."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, time
import json
import os
from zoneinfo import ZoneInfo

from ashare_v3.market.windows_n3_minute_context import (
    EltdxBoardMinuteContextProvider,
    EltdxIndexMinuteContextProvider,
    EltdxStockMinuteContextProvider,
)
from ashare_v3.market.windows_n3_previous_day_context import (
    PostgresPreviousDayContextRepository,
    TQBoardMinuteContextProvider,
    TQIndexMinuteContextProvider,
    TQStockMinuteContextProvider,
    UnavailableTQMinuteContextProvider,
    WindowsN3PreviousDayContextPreloader,
    load_windows_tq_client,
)
from ashare_v3.market.windows_n3_read_model import WindowsN3ReadOnlyRepository


SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")


def summary_to_dict(summary) -> dict:
    return {
        "result": summary.result,
        "context_run_id": summary.context_run_id,
        "source_condition_run_id": summary.source_condition_run_id,
        "context_version": summary.context_version,
        "source_trade_date": summary.source_trade_date,
        "for_trade_date": summary.for_trade_date,
        "expected_counts": dict(summary.expected_counts),
        "terminal_counts": dict(summary.terminal_counts),
        "status_counts": {
            key: dict(value) for key, value in summary.status_counts.items()
        },
        "inserted_count": summary.inserted_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dsn",
        default=os.environ.get(
            "ASHARE_V3_DSN",
            "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3",
        ),
    )
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument(
        "--context-version",
        default=os.environ.get("ASHARE_V3_N3_CONTEXT_VERSION", "v1"),
    )
    parser.add_argument("--tq-module-path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(SHANGHAI_TIMEZONE)
    today = now.strftime("%Y%m%d")
    if args.for_trade_date < today or (
        args.for_trade_date == today and now.time() >= time(9, 0)
    ):
        raise RuntimeError("N3 context preload deadline has passed")

    from eltdx import TdxClient

    model = WindowsN3ReadOnlyRepository(args.dsn).load_active(args.for_trade_date)
    try:
        tq_client = load_windows_tq_client(args.tq_module_path)
        tq_stock = TQStockMinuteContextProvider(tq_client)
        tq_index = TQIndexMinuteContextProvider(tq_client)
        tq_board = TQBoardMinuteContextProvider(tq_client)
    except Exception as error:  # terminal/module availability varies by host
        tq_stock = UnavailableTQMinuteContextProvider(error)
        tq_index = UnavailableTQMinuteContextProvider(error)
        tq_board = UnavailableTQMinuteContextProvider(error)
    with ExitStack() as stack:
        client = stack.enter_context(
            TdxClient.from_hosts(pool_size=16, probe_hosts=True, timeout=8)
        )
        summary = WindowsN3PreviousDayContextPreloader(
            repository=PostgresPreviousDayContextRepository(
                args.dsn,
                context_version=args.context_version,
            ),
            tq_stock=tq_stock,
            tq_index=tq_index,
            tq_board=tq_board,
            eltdx_stock=EltdxStockMinuteContextProvider(client),
            eltdx_index=EltdxIndexMinuteContextProvider(client),
            eltdx_board=EltdxBoardMinuteContextProvider(client),
        ).execute(model)
    print(json.dumps(summary_to_dict(summary), ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
