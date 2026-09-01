#!/usr/bin/env python3
"""Run Windows N3/N4/N5; states stay in memory and events persist."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, time
import json
import os
from zoneinfo import ZoneInfo

from ashare_v3.action.windows_n5_restore import (
    WindowsN5EpisodeReadOnlyRepository,
)
from ashare_v3.action.windows_n5_transaction import (
    WindowsN5TransactionCoordinator,
)
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
    N5ChannelTransactionBoundary,
    WindowsN3N4N5MemoryOrchestrator,
)
from ashare_v3.runtime_control.windows_n3_n4_n5_diagnostics import (
    DEFAULT_DIAGNOSTIC_ROOT,
    WindowsN3N4N5DiagnosticWriter,
)
from ashare_v3.runtime_control.windows_n4_outbox_restore import (
    WindowsN4OutboxReadOnlyRepository,
)
from ashare_v3.runtime_control.windows_state_bridge import WindowsStateBridge
from ashare_v3.trigger.windows_n4_memory import build_windows_n4_runtime
from ashare_v3.trigger.windows_n4_transaction import (
    WindowsN4TransactionCoordinator,
)


SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
ASSET_KINDS = ("stock", "index", "board")
N5_CONSUMER_NAME = "windows_n5_state_v1"


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
    parser.add_argument("--state-bridge-host", default="127.0.0.1")
    parser.add_argument("--state-bridge-port", type=int, default=8796)
    parser.add_argument(
        "--diagnostic-root",
        default=os.environ.get(
            "ASHARE_V3_WINDOWS_N3_N4_N5_DIAGNOSTIC_ROOT",
            str(DEFAULT_DIAGNOSTIC_ROOT),
        ),
    )
    return parser.parse_args()


class _CapturingContextLoader:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.latest = None

    def load(self, model):
        loaded = self.delegate.load(model)
        self.latest = loaded
        return loaded


def _open_transaction_boundaries(stack, dsn, *, connect=None):
    if not dsn:
        raise ValueError("dsn is required")
    if connect is None:
        import psycopg

        connect = psycopg.connect
    boundaries = {}
    for asset_kind in ASSET_KINDS:
        n4_connection = stack.enter_context(connect(dsn))
        n5_connection = stack.enter_context(connect(dsn))
        boundaries[asset_kind] = N5ChannelTransactionBoundary(
            n4_connection=n4_connection,
            n4_coordinator=WindowsN4TransactionCoordinator(),
            connection=n5_connection,
            coordinator=WindowsN5TransactionCoordinator(
                consumer_name=N5_CONSUMER_NAME,
            ),
        )
    return boundaries


def main() -> int:
    args = parse_args()
    from eltdx import TdxClient

    repository = WindowsN3ReadOnlyRepository(args.dsn)
    n4_outbox_repository = WindowsN4OutboxReadOnlyRepository(args.dsn)
    n5_episode_repository = WindowsN5EpisodeReadOnlyRepository(
        args.dsn,
        consumer_name=N5_CONSUMER_NAME,
    )
    context_loader = _CapturingContextLoader(
        PostgresPreviousDayContextLoader(
            args.dsn,
            context_version=args.context_version,
        )
    )
    integration_holder = {}
    process_started_at = datetime.now(SHANGHAI_TIMEZONE)
    with ExitStack() as stack:
        bridge = None
        stock_client = stack.enter_context(
            TdxClient(
                timeout=8,
                pool_size=16,
                probe_hosts=True,
            )
        )
        index_client = stack.enter_context(
            TdxClient(
                timeout=8,
                pool_size=16,
                probe_hosts=True,
            )
        )
        board_client = stack.enter_context(
            TdxClient(
                timeout=8,
                pool_size=16,
                probe_hosts=True,
            )
        )

        def runtime_factory(model):
            nonlocal bridge
            loaded = context_loader.latest
            if (
                loaded is None
                or loaded.source_condition_run_id != model.run_id
            ):
                raise RuntimeError(
                    "N3 previous context was not loaded for the active N2 run"
                )
            n4_restore = n4_outbox_repository.load(
                source_condition_run_id=model.run_id,
                for_trade_date=model.for_trade_date,
            )
            integration_holder["n4_restore"] = n4_restore
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
            n5_restore = n5_episode_repository.load(
                source_condition_run_id=model.run_id,
                for_trade_date=model.for_trade_date,
                action_run_ids=action_run_ids,
            )
            integration_holder["n5_restore"] = n5_restore
            transaction_boundaries = integration_holder.get(
                "transaction_boundaries"
            )
            if transaction_boundaries is None:
                transaction_boundaries = _open_transaction_boundaries(
                    stack,
                    args.dsn,
                )
                integration_holder["transaction_boundaries"] = (
                    transaction_boundaries
                )
            integration_holder["runtime"] = WindowsN3N4N5MemoryOrchestrator(
                n4_runtime=build_windows_n4_runtime(
                    model,
                    initial_versions=n4_restore.last_versions,
                ),
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
                n4_restore_events=n4_restore.events,
                n5_restore_events=n5_restore.events,
                n5_transaction_boundaries=transaction_boundaries,
            )
            try:
                integration_holder["diagnostic_writer"] = (
                    WindowsN3N4N5DiagnosticWriter(
                        for_trade_date=model.for_trade_date,
                        started_at=process_started_at,
                        root=args.diagnostic_root,
                    )
                )
            except Exception as error:
                integration_holder["diagnostic_writer"] = None
                integration_holder["runtime"].record_diagnostic_error(error)
            if bridge is None:
                bridge = WindowsStateBridge(
                    integration_holder["runtime"].read_state_bridge_snapshot,
                    host=args.state_bridge_host,
                    port=args.state_bridge_port,
                ).start()
                stack.callback(bridge.shutdown)
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
            writer = integration_holder.get("diagnostic_writer")
            if writer is None:
                return
            try:
                writer.write_confirmation_latest(
                    runtime.read_state_bridge_snapshot(),
                    runtime.read_summary(),
                )
            except Exception as error:
                runtime.record_diagnostic_error(error)

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
        if summary.result == "N3_MEMORY_SESSION_COMPLETE":
            integration = integration_holder.get("runtime")
            writer = integration_holder.get("diagnostic_writer")
            if integration is None:
                raise RuntimeError(
                    "completed N3 session requires initialized integration"
                )
            finalization = integration.finalize_session(
                summary.finished_at
            )
            integration_holder["finalization"] = finalization
            if writer is None:
                raise RuntimeError(
                    "N3/N4/N5 final diagnostic writer is unavailable"
                )
            try:
                integration_holder["session_final_artifact"] = (
                    writer.write_session_final(
                        finalization,
                        integration.read_summary(),
                    )
                )
            except Exception as error:
                integration.record_diagnostic_error(error)
                raise RuntimeError(
                    "N3/N4/N5 final diagnostic artifact write failed"
                ) from error

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
    n4_restore = integration_holder.get("n4_restore")
    if n4_restore is not None:
        payload["n4_restored_event_counts"] = {
            kind: len(n4_restore.events[kind])
            for kind in ("stock", "index", "board")
        }
        payload["n4_restored_versions"] = dict(
            n4_restore.last_versions
        )
    else:
        payload["n4_restored_event_counts"] = {
            kind: 0 for kind in ("stock", "index", "board")
        }
        payload["n4_restored_versions"] = {
            kind: 0 for kind in ("stock", "index", "board")
        }
    n5_restore = integration_holder.get("n5_restore")
    if n5_restore is not None:
        payload["n5_restored_event_counts"] = {
            kind: len(n5_restore.events[kind])
            for kind in ("stock", "index", "board")
        }
    else:
        payload["n5_restored_event_counts"] = {
            kind: 0 for kind in ("stock", "index", "board")
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
        payload["n5_restored_episode_counts"] = runtime_summary[
            "n5_restored_episode_counts"
        ]
        payload["n5_restored_versions"] = runtime_summary[
            "n5_restored_versions"
        ]
        payload["database_write_count"] = sum(
            runtime_summary["database_write_counts"].values()
        )
        payload["event_persistence_count"] = sum(
            runtime_summary["event_persistence_counts"].values()
        )
        writer = integration_holder.get("diagnostic_writer")
        payload["diagnostic_directory"] = (
            str(writer.run_directory) if writer is not None else None
        )
        final_artifact = integration_holder.get(
            "session_final_artifact"
        )
        payload["session_final_artifact"] = (
            str(final_artifact) if final_artifact is not None else None
        )
    else:
        payload["trigger_event_count"] = 0
        payload["n5_action_event_count"] = 0
        payload["n5_restored_episode_counts"] = {
            kind: 0 for kind in ("stock", "index", "board")
        }
        payload["n5_restored_versions"] = {
            kind: 0 for kind in ("stock", "index", "board")
        }
        payload["database_write_count"] = 0
        payload["event_persistence_count"] = 0
    print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
