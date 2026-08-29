#!/usr/bin/env python3
"""Run one Windows N3/N4 process with no realtime-state persistence."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, time
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
from ashare_v3.market.windows_n3_previous_day_context import (
    PostgresPreviousDayContextLoader,
    TQBoardMinuteContextProvider,
    TQIndexMinuteContextProvider,
    TQStockMinuteContextProvider,
    TQWithEltdxMinuteContextProvider,
    UnavailableTQMinuteContextProvider,
    load_windows_tq_client,
)
from ashare_v3.market.windows_n3_read_model import WindowsN3ReadOnlyRepository
from ashare_v3.market.windows_n3_snapshot import (
    EltdxBoardSnapshotProvider,
    EltdxIndexSnapshotProvider,
    EltdxStockSnapshotProvider,
)
from ashare_v3.trigger.windows_n4_memory import build_windows_n4_runtime


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
    parser.add_argument(
        "--context-version",
        default=os.environ.get("ASHARE_V3_N3_CONTEXT_VERSION", "v1"),
    )
    parser.add_argument("--tq-module-path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from eltdx import TdxClient

    repository = WindowsN3ReadOnlyRepository(args.dsn)
    context_loader = PostgresPreviousDayContextLoader(
        args.dsn,
        context_version=args.context_version,
    )
    n4_holder = {}
    with ExitStack() as stack:
        stock_client = stack.enter_context(
            TdxClient(timeout=8, server_count=4, connections_per_server=4)
        )
        index_client = stack.enter_context(
            TdxClient(timeout=8, server_count=4, connections_per_server=4)
        )
        board_client = stack.enter_context(
            TdxClient(timeout=8, server_count=4, connections_per_server=4)
        )

        def runtime_factory(model):
            n4_holder["runtime"] = build_windows_n4_runtime(model)
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

        def publish(cycle):
            runtime = n4_holder.get("runtime")
            if runtime is None:
                raise RuntimeError("N4 runtime was not initialized from N2")
            n4_holder["latest"] = runtime.consume_cycle(cycle)

        current_provider_args = {}
        now = datetime.now(SHANGHAI_TIMEZONE)
        if (
            now.strftime("%Y%m%d") == args.for_trade_date
            and now.time() >= time(9, 31)
        ):
            try:
                tq_client = load_windows_tq_client(args.tq_module_path)
                tq_stock = TQStockMinuteContextProvider(tq_client)
                tq_index = TQIndexMinuteContextProvider(tq_client)
                tq_board = TQBoardMinuteContextProvider(tq_client)
            except Exception as error:  # late-start recovery must still use eltdx
                tq_stock = UnavailableTQMinuteContextProvider(error)
                tq_index = UnavailableTQMinuteContextProvider(error)
                tq_board = UnavailableTQMinuteContextProvider(error)
            current_provider_args = {
                "current_stock_minute_provider": TQWithEltdxMinuteContextProvider(
                    tq_stock,
                    EltdxStockMinuteContextProvider(stock_client),
                ),
                "current_index_minute_provider": TQWithEltdxMinuteContextProvider(
                    tq_index,
                    EltdxIndexMinuteContextProvider(index_client),
                ),
                "current_board_minute_provider": TQWithEltdxMinuteContextProvider(
                    tq_board,
                    EltdxBoardMinuteContextProvider(board_client),
                ),
            }
        runner = WindowsN3IntradayRunner(
            repository=repository,
            context_loader=context_loader,
            runtime_factory=runtime_factory,
            publish=publish,
            **current_provider_args,
        )
        summary = runner.execute(args.for_trade_date)

    payload = asdict(summary)
    latest = n4_holder.get("latest")
    if latest is not None:
        payload["n4_state_counts"] = {
            "stock": len(latest.stock.states),
            "index": len(latest.index.states),
            "board": len(latest.board.states),
        }
        payload["n4_versions"] = {
            "stock": latest.stock.version,
            "index": latest.index.version,
            "board": latest.board.version,
        }
    payload["database_write_count"] = 0
    payload["trigger_event_count"] = 0
    print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
