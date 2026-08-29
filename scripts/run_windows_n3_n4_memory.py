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

from ashare_v3.market.windows_n3_action_metric import (
    EltdxBoardActionMetricProvider,
    EltdxIndexActionMetricProvider,
    EltdxStockActionMetricProvider,
)
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
from ashare_v3.runtime_control.windows_n3_n4_n5_memory import (
    WindowsN3N4N5MemoryOrchestrator,
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


class _CapturingContextLoader:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.latest = None

    def load(self, model):
        loaded = self.delegate.load(model)
        self.latest = loaded
        return loaded


def main() -> int:
    args = parse_args()
    from eltdx import TdxClient

    repository = WindowsN3ReadOnlyRepository(args.dsn)
    context_loader = _CapturingContextLoader(
        PostgresPreviousDayContextLoader(
            args.dsn,
            context_version=args.context_version,
        )
    )
    integration_holder = {}
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
            loaded = context_loader.latest
            if (
                loaded is None
                or loaded.source_condition_run_id != model.run_id
            ):
                raise RuntimeError(
                    "N3 previous context was not loaded for the active N2 run"
                )
            trigger_run_ids = {
                kind: (
                    f"windows_n4_state_transition_"
                    f"{model.for_trade_date}_{kind}"
                )
                for kind in ("stock", "index", "board")
            }
            action_run_ids = {
                kind: (
                    f"windows_n5_closed_minute_"
                    f"{model.for_trade_date}_{kind}"
                )
                for kind in ("stock", "index", "board")
            }
            integration_holder["runtime"] = WindowsN3N4N5MemoryOrchestrator(
                n4_runtime=build_windows_n4_runtime(model),
                stock_requests=model.stock_requests(),
                index_requests=model.index_requests(),
                board_requests=model.board_requests(),
                previous_stock=loaded.stock,
                previous_index=loaded.index,
                previous_board=loaded.board,
                stock_metric_provider=EltdxStockActionMetricProvider(stock_client),
                index_metric_provider=EltdxIndexActionMetricProvider(index_client),
                board_metric_provider=EltdxBoardActionMetricProvider(board_client),
                trigger_run_ids=trigger_run_ids,
                action_run_ids=action_run_ids,
            )
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
            runtime = integration_holder.get("runtime")
            if runtime is None:
                raise RuntimeError("N3/N4/N5 runtime was not initialized from N2")
            integration_holder["latest"] = runtime.consume_cycle(cycle)

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
    latest = integration_holder.get("latest")
    if latest is not None:
        n4_memory = latest.n4_memory
        payload["n4_state_counts"] = {
            "stock": len(n4_memory.stock.states),
            "index": len(n4_memory.index.states),
            "board": len(n4_memory.board.states),
        }
        payload["n4_versions"] = {
            "stock": n4_memory.stock.version,
            "index": n4_memory.index.version,
            "board": n4_memory.board.version,
        }
    integration = integration_holder.get("runtime")
    if integration is not None:
        runtime_summary = integration.read_summary().as_dict()
        payload["n3_n4_n5_memory"] = runtime_summary
        payload["trigger_event_count"] = sum(
            sum(values.values())
            for values in runtime_summary[
                "n4_trigger_event_counts"
            ].values()
        )
        payload["n5_action_event_count"] = sum(
            sum(values.values())
            for values in runtime_summary[
                "n5_action_event_counts"
            ].values()
        )
        payload["n5_state_counts"] = runtime_summary["n5_state_counts"]
        payload["n5_versions"] = runtime_summary["n5_versions"]
    else:
        payload["trigger_event_count"] = 0
        payload["n5_action_event_count"] = 0
    payload["database_write_count"] = 0
    payload["event_persistence_count"] = 0
    print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
