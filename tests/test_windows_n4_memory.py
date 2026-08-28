from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from ashare_v3.market.windows_n3_memory import (
    AverageAmountBaseline,
    BoardSnapshotChannel,
    ChannelStateView,
    IndexSnapshotChannel,
    RatioAmountBaseline,
    RealtimeMetric,
    StockSnapshotChannel,
    VirtualAmountContext,
    WindowsN3MemoryRuntime,
)
from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotBatch,
    BoardSnapshotRequest,
    IndexSnapshotBatch,
    IndexSnapshotRequest,
    RealtimeQuote,
    StockSnapshotBatch,
    StockSnapshotRequest,
)
from ashare_v3.trigger.windows_n4_memory import (
    BoardRuntimeState,
    BoardStateConsumer,
    IndexRuntimeState,
    IndexStateConsumer,
    N2RuntimeBaseline,
    OutOfOrderN3Snapshot,
    RUNTIME_PERIODS,
    RuntimePeriodBaseline,
    StockRuntimeState,
    StockStateConsumer,
    WindowsN4MemoryRuntime,
    realtime_transition,
)


NOW = datetime(2026, 8, 28, 1, 45, tzinfo=timezone.utc)
RUN_ID = "condition_layer_20260827_source_20260827_for_20260828_v1"


def period_baselines(
    *,
    source_transition: str = "flat",
    current_trade_days: int = 1,
    ready: bool = True,
) -> dict[str, RuntimePeriodBaseline]:
    return {
        period: RuntimePeriodBaseline(
            period=period,
            source_transition=source_transition,
            source_amount=Decimal("90"),
            comparison_entity_high=Decimal("10") if ready else None,
            comparison_entity_low=Decimal("8") if ready else None,
            comparison_amount=Decimal("100") if ready else None,
            current_trade_days=current_trade_days,
            ready=ready,
        )
        for period in RUNTIME_PERIODS
    }


def baseline(kind: str, code: str, *, source_transition: str = "flat") -> N2RuntimeBaseline:
    return N2RuntimeBaseline(
        source_condition_run_id=RUN_ID,
        source_trade_date="20260827",
        for_trade_date="20260828",
        asset_kind=kind,
        identity_key=f"{kind}:{code}",
        exchange="SH",
        code=code,
        name=f"{kind}-{code}",
        periods=period_baselines(source_transition=source_transition),
    )


def quote(kind: str, code: str, *, price: str = "11", amount: str = "120") -> RealtimeQuote:
    return RealtimeQuote(
        asset_kind=kind,
        identity_key=f"{kind}:{code}",
        exchange="SH",
        code=code,
        name=f"{kind}-{code}",
        current_price=Decimal(price),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        pre_close=Decimal("10"),
        volume=Decimal("1000"),
        amount=Decimal(amount),
        source_time=NOW,
        observed_at=NOW,
        provider=f"fake.{kind}",
    )


def metric(
    kind: str,
    code: str,
    *,
    price: str = "11",
    amount: str = "200",
    live_status: str = "available",
    fresh: bool = True,
    with_quote: bool = True,
) -> RealtimeMetric:
    row = quote(kind, code, price=price) if with_quote else None
    return RealtimeMetric(
        asset_kind=kind,
        identity_key=f"{kind}:{code}",
        exchange="SH",
        code=code,
        name=f"{kind}-{code}",
        quote=row,
        virtual_amounts={period: Decimal(amount) for period in RUNTIME_PERIODS},
        live_status=live_status,
        fresh=fresh,
        last_success_at=NOW if with_quote else None,
        last_error=None,
    )


def view(
    kind: str,
    code: str,
    *,
    version: int = 1,
    row: RealtimeMetric | None = None,
    channel_status: str = "ready",
) -> ChannelStateView[RealtimeMetric]:
    return ChannelStateView(
        for_trade_date="20260828",
        source_condition_run_id=RUN_ID,
        version=version,
        generated_at=NOW,
        channel_status=channel_status,
        states=MappingProxyType({f"{kind}:{code}": row or metric(kind, code)}),
        error_summary="provider down" if channel_status == "degraded" else None,
    )


class _StaticProvider:
    def __init__(self, kind: str, batch_type: type) -> None:
        self.kind = kind
        self.batch_type = batch_type

    def fetch_many(self, requests):
        rows = tuple(quote(self.kind, request.code, amount="120") for request in requests)
        return self.batch_type(
            rows=rows,
            missing_identity_keys=(),
            provider=f"fake.{self.kind}",
            observed_at=NOW,
        )


class WindowsN4MemoryTest(unittest.TestCase):
    def make_runtime(self) -> WindowsN4MemoryRuntime:
        return WindowsN4MemoryRuntime(
            StockStateConsumer([baseline("stock", "600000")]),
            IndexStateConsumer([baseline("index", "000001")]),
            BoardStateConsumer([baseline("board", "881333")]),
        )

    def test_initial_maps_hold_full_n2_universe_as_unavailable(self) -> None:
        runtime = self.make_runtime()
        self.assertIsInstance(runtime.stock_states["stock:600000"], StockRuntimeState)
        self.assertIsInstance(runtime.index_states["index:000001"], IndexRuntimeState)
        self.assertIsInstance(runtime.board_states["board:881333"], BoardRuntimeState)
        self.assertEqual(runtime.stock_states["stock:600000"].live_status, "unavailable")
        initial_transitions = runtime.stock_states["stock:600000"].realtime_transitions
        self.assertTrue(all(value is None for value in initial_transitions.values()))
        with self.assertRaises(TypeError):
            runtime.stock_states["stock:new"] = runtime.stock_states["stock:600000"]

    def test_three_channels_consume_fresh_snapshots(self) -> None:
        runtime = self.make_runtime()
        result = runtime.consume_views(
            stock=view("stock", "600000"),
            index=view("index", "000001"),
            board=view("board", "881333"),
        )
        self.assertIsInstance(result.stock.states["stock:600000"], StockRuntimeState)
        self.assertIsInstance(result.index.states["index:000001"], IndexRuntimeState)
        self.assertIsInstance(result.board.states["board:881333"], BoardRuntimeState)
        for snapshot in (result.stock, result.index, result.board):
            state = next(iter(snapshot.states.values()))
            self.assertEqual(set(state.realtime_transitions), set(RUNTIME_PERIODS))
            self.assertEqual(set(state.realtime_transitions.values()), {"volume_up"})
            self.assertTrue(state.fresh)
            self.assertEqual(snapshot.channel_status, "ready")

    def test_stale_and_unavailable_never_recompute(self) -> None:
        consumer = StockStateConsumer([baseline("stock", "600000")])
        first = consumer.consume(view("stock", "600000"))
        first_state = first.states["stock:600000"]
        changed_stale = metric(
            "stock",
            "600000",
            price="1",
            amount="1",
            live_status="stale",
            fresh=False,
        )
        second = consumer.consume(view("stock", "600000", version=2, row=changed_stale))
        second_state = second.states["stock:600000"]
        self.assertEqual(second_state.current_price, first_state.current_price)
        self.assertEqual(second_state.realtime_transitions, first_state.realtime_transitions)
        self.assertEqual(second_state.realtime_virtual_amounts, first_state.realtime_virtual_amounts)
        self.assertEqual(second_state.live_status, "stale")
        self.assertFalse(second_state.fresh)

        unavailable = metric(
            "stock",
            "600000",
            live_status="unavailable",
            fresh=False,
            with_quote=False,
        )
        third = consumer.consume(view("stock", "600000", version=3, row=unavailable))
        self.assertEqual(third.states["stock:600000"].realtime_transitions, first_state.realtime_transitions)
        self.assertEqual(third.states["stock:600000"].live_status, "unavailable")

    def test_atomic_replacement_is_bounded_and_old_view_is_immutable(self) -> None:
        consumer = StockStateConsumer(
            [baseline("stock", "600000"), baseline("stock", "600001")]
        )
        first = consumer.consume(
            ChannelStateView(
                for_trade_date="20260828",
                source_condition_run_id=RUN_ID,
                version=1,
                generated_at=NOW,
                channel_status="ready",
                states=MappingProxyType(
                    {
                        "stock:600000": metric("stock", "600000"),
                        "stock:600001": metric("stock", "600001"),
                    }
                ),
            )
        )
        second = consumer.consume(
            ChannelStateView(
                for_trade_date="20260828",
                source_condition_run_id=RUN_ID,
                version=2,
                generated_at=NOW,
                channel_status="ready",
                states=MappingProxyType(
                    {
                        "stock:600000": metric("stock", "600000", price="12"),
                        "stock:600001": metric("stock", "600001", price="12"),
                    }
                ),
            )
        )
        self.assertEqual(len(first.states), 2)
        self.assertEqual(len(second.states), 2)
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertEqual(first.states["stock:600000"].current_price, Decimal("11"))
        self.assertEqual(second.states["stock:600000"].current_price, Decimal("12"))
        with self.assertRaises(TypeError):
            second.states["stock:600002"] = second.states["stock:600000"]

    def test_period_grades_and_transition_carry_match_n2_semantics(self) -> None:
        base = RuntimePeriodBaseline(
            period="D",
            source_transition="flat",
            source_amount=Decimal("90"),
            comparison_entity_high=Decimal("10"),
            comparison_entity_low=Decimal("8"),
            comparison_amount=Decimal("100"),
        )
        cases = (
            ("11", "101", "volume_up"),
            ("11", "99", "low_volume_up"),
            ("7", "101", "volume_down"),
            ("7", "99", "low_volume_down"),
            ("9", "200", "flat"),
        )
        for price, amount, expected in cases:
            self.assertEqual(
                realtime_transition(
                    period="D",
                    current_price=Decimal(price),
                    current_amount=Decimal(amount),
                    baseline=base,
                ),
                expected,
            )
        week = RuntimePeriodBaseline(
            period="W",
            source_transition="volume_up",
            source_amount=Decimal("90"),
            comparison_entity_high=Decimal("10"),
            comparison_entity_low=Decimal("8"),
            comparison_amount=Decimal("100"),
            current_trade_days=1,
        )
        self.assertEqual(
            realtime_transition(
                period="W",
                current_price=Decimal("11"),
                current_amount=Decimal("99"),
                baseline=week,
            ),
            "volume_up",
        )
        day = replace_period(week, period="D")
        self.assertEqual(
            realtime_transition(
                period="D",
                current_price=Decimal("11"),
                current_amount=Decimal("99"),
                baseline=day,
            ),
            "low_volume_up",
        )

    def test_not_ready_baseline_produces_unknown_only_for_that_period(self) -> None:
        periods = period_baselines()
        periods["30m"] = RuntimePeriodBaseline(
            period="30m",
            source_transition="unknown",
            source_amount=None,
            comparison_entity_high=None,
            comparison_entity_low=None,
            comparison_amount=None,
            ready=False,
        )
        custom = N2RuntimeBaseline(
            source_condition_run_id=RUN_ID,
            source_trade_date="20260827",
            for_trade_date="20260828",
            asset_kind="stock",
            identity_key="stock:600000",
            exchange="SH",
            code="600000",
            name="stock-600000",
            periods=periods,
        )
        state = StockStateConsumer([custom]).consume(
            view("stock", "600000")
        ).states["stock:600000"]
        self.assertEqual(state.realtime_transitions["30m"], "unknown")
        self.assertEqual(state.realtime_transitions["D"], "volume_up")

    def test_duplicate_and_older_n3_versions_are_handled(self) -> None:
        consumer = StockStateConsumer([baseline("stock", "600000")])
        first = consumer.consume(view("stock", "600000", version=2))
        self.assertIs(consumer.consume(view("stock", "600000", version=2)), first)
        with self.assertRaises(OutOfOrderN3Snapshot):
            consumer.consume(view("stock", "600000", version=1))

    def test_concurrent_delivery_of_one_n3_version_replaces_once(self) -> None:
        consumer = StockStateConsumer([baseline("stock", "600000")])
        source = view("stock", "600000", version=1)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = tuple(pool.map(consumer.consume, (source,) * 16))
        self.assertEqual({result.version for result in results}, {1})
        self.assertEqual(consumer.read().version, 1)

    def test_restart_rebuilds_from_baseline_and_first_fresh_view(self) -> None:
        source = view("stock", "600000", version=1)
        first = StockStateConsumer([baseline("stock", "600000")]).consume(source)
        restarted_consumer = StockStateConsumer([baseline("stock", "600000")])
        self.assertEqual(restarted_consumer.read().channel_status, "warming")
        rebuilt = restarted_consumer.consume(source)
        self.assertEqual(rebuilt.states, first.states)
        self.assertEqual(rebuilt.channel_status, "ready")

    def test_degraded_stock_channel_does_not_block_index_or_board(self) -> None:
        runtime = self.make_runtime()
        result = runtime.consume_views(
            stock=view("stock", "600000", channel_status="degraded"),
            index=view("index", "000001"),
            board=view("board", "881333"),
        )
        self.assertEqual(result.stock.channel_status, "degraded")
        self.assertEqual(result.index.channel_status, "ready")
        self.assertEqual(result.board.channel_status, "ready")

    def test_consume_latest_uses_real_n3_immutable_channel_views(self) -> None:
        stock_channel = StockSnapshotChannel(
            _StaticProvider("stock", StockSnapshotBatch),
            for_trade_date="20260828",
            source_condition_run_id=RUN_ID,
            clock=lambda: NOW,
        )
        index_channel = IndexSnapshotChannel(
            _StaticProvider("index", IndexSnapshotBatch),
            for_trade_date="20260828",
            source_condition_run_id=RUN_ID,
            clock=lambda: NOW,
        )
        board_channel = BoardSnapshotChannel(
            _StaticProvider("board", BoardSnapshotBatch),
            for_trade_date="20260828",
            source_condition_run_id=RUN_ID,
            clock=lambda: NOW,
        )
        n3 = WindowsN3MemoryRuntime(stock_channel, index_channel, board_channel)
        amount_context = VirtualAmountContext(
            window_30m=RatioAmountBaseline(Decimal("60"), Decimal("100")),
            day=RatioAmountBaseline(Decimal("60"), Decimal("100")),
            higher_periods={
                period: AverageAmountBaseline(Decimal("0"), 0)
                for period in ("W", "M", "Q", "Y")
            },
        )
        n3.run_cycle(
            stock_requests=[StockSnapshotRequest("stock:600000", "SH", "600000", "stock-600000")],
            index_requests=[IndexSnapshotRequest("index:000001", "SH", "000001", "index-000001")],
            board_requests=[BoardSnapshotRequest("board:881333", "SH", "881333", "board-881333")],
            stock_contexts={"stock:600000": amount_context},
            index_contexts={"index:000001": amount_context},
            board_contexts={"board:881333": amount_context},
        )
        result = self.make_runtime().consume_latest(n3)
        self.assertEqual(result.stock.source_n3_version, 1)
        self.assertEqual(result.index.source_n3_version, 1)
        self.assertEqual(result.board.source_n3_version, 1)
        self.assertEqual(result.stock.states["stock:600000"].realtime_transitions["D"], "volume_up")

    def test_module_has_no_persistence_or_downstream_contract(self) -> None:
        module_path = Path(__file__).parents[1] / "src/ashare_v3/trigger/windows_n4_memory.py"
        source = module_path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "import psycopg",
            "create table",
            "insert into",
            "update ",
            "delete from",
            "triggermatched",
            "triggerstatechanged",
            "actioneligible",
        ):
            self.assertNotIn(forbidden, source)
        state_fields = {field.name for field in fields(StockRuntimeState)}
        self.assertFalse(
            state_fields.intersection(
                {"target_price", "financial", "finance", "level_up_score"}
            )
        )


def replace_period(
    value: RuntimePeriodBaseline,
    *,
    period: str,
) -> RuntimePeriodBaseline:
    return RuntimePeriodBaseline(
        period=period,
        source_transition=value.source_transition,
        source_amount=value.source_amount,
        comparison_entity_high=value.comparison_entity_high,
        comparison_entity_low=value.comparison_entity_low,
        comparison_amount=value.comparison_amount,
        current_trade_days=value.current_trade_days,
        ready=value.ready,
    )


if __name__ == "__main__":
    unittest.main()
