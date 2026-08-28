#!/usr/bin/env python3
"""Run the Windows N3 in-memory session; no N4 logic or persistence."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo

from ashare_v3.market.windows_n3_intraday import WindowsN3IntradayRunner
from ashare_v3.market.windows_n3_memory import (
    BoardSnapshotChannel,
    IndexSnapshotChannel,
    StockSnapshotChannel,
    WindowsN3MemoryRuntime,
)
from ashare_v3.market.windows_n3_minute_context import (
    EltdxBoardMinuteContextProvider,
    EltdxIndexMinuteContextProvider,
    EltdxStockMinuteContextProvider,
)
from ashare_v3.market.windows_n3_read_model import WindowsN3ReadOnlyRepository
from ashare_v3.market.windows_n3_snapshot import (
    EltdxBoardSnapshotProvider,
    EltdxIndexSnapshotProvider,
    EltdxStockSnapshotProvider,
)


SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dsn",
        default=os.environ.get(
            "ASHARE_V3_DSN",
            "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3",
        ),
    )
    parser.add_argument(
        "--for-trade-date",
        default=datetime.now(SHANGHAI_TIMEZONE).strftime("%Y%m%d"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from eltdx import TdxClient

    repository = WindowsN3ReadOnlyRepository(args.dsn)
    with ExitStack() as stack:
        stock_client = stack.enter_context(TdxClient(timeout=8, server_count=4, connections_per_server=4))
        index_client = stack.enter_context(TdxClient(timeout=8, server_count=4, connections_per_server=4))
        board_client = stack.enter_context(TdxClient(timeout=8, server_count=4, connections_per_server=4))

        def runtime_factory(model):
            return WindowsN3MemoryRuntime(
                StockSnapshotChannel(
                    EltdxStockSnapshotProvider(stock_client),
                    for_trade_date=model.for_trade_date,
                    source_condition_run_id=model.run_id,
                ),
                IndexSnapshotChannel(
                    EltdxIndexSnapshotProvider(index_client),
                    for_trade_date=model.for_trade_date,
                    source_condition_run_id=model.run_id,
                ),
                BoardSnapshotChannel(
                    EltdxBoardSnapshotProvider(board_client),
                    for_trade_date=model.for_trade_date,
                    source_condition_run_id=model.run_id,
                ),
            )

        runner = WindowsN3IntradayRunner(
            repository=repository,
            stock_minute_provider=EltdxStockMinuteContextProvider(stock_client),
            index_minute_provider=EltdxIndexMinuteContextProvider(index_client),
            board_minute_provider=EltdxBoardMinuteContextProvider(board_client),
            runtime_factory=runtime_factory,
        )
        summary = runner.execute(args.for_trade_date)
    print(json.dumps(asdict(summary), ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
