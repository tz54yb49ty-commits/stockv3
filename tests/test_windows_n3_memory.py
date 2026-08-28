from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import unittest

from ashare_v3.market.windows_n3_memory import (
    AverageAmountBaseline,
    BoardSnapshotChannel,
    IndexSnapshotChannel,
    RatioAmountBaseline,
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


class Clock:
    def __init__(self):
        self.value = datetime(2026, 8, 28, 1, 35, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def make_quote(request, *, asset_kind, observed_at, amount="100"):
    return RealtimeQuote(
        asset_kind=asset_kind,
        identity_key=request.identity_key,
        exchange=request.exchange,
        code=request.code,
        name=request.name,
        current_price=Decimal("10"),
        open=Decimal("9"),
        high=Decimal("11"),
        low=Decimal("8"),
        pre_close=Decimal("9.5"),
        volume=Decimal("20"),
        amount=Decimal(amount),
        source_time=observed_at,
        observed_at=observed_at,
        provider="fake",
    )


class Provider:
    def __init__(self, batch_type, asset_kind, clock):
        self.batch_type = batch_type
        self.asset_kind = asset_kind
        self.clock = clock
        self.fail = False
        self.omit = set()
        self.calls = 0

    def fetch_many(self, requests):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.asset_kind} unavailable")
        rows = tuple(
            make_quote(request, asset_kind=self.asset_kind, observed_at=self.clock())
            for request in requests
            if request.identity_key not in self.omit
        )
        missing = tuple(request.identity_key for request in requests if request.identity_key in self.omit)
        return self.batch_type(rows, missing, f"fake-{self.asset_kind}", self.clock())


class WindowsN3MemoryTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.stock_request = StockSnapshotRequest("stock:SH:600000", "SH", "600000", "浦发")
        self.index_request = IndexSnapshotRequest("index:SH:000001", "SH", "000001", "上证")
        self.board_request = BoardSnapshotRequest("board:TDX:881333", "SH", "881333", "元器件")

    def channel(self, provider=None):
        provider = provider or Provider(StockSnapshotBatch, "stock", self.clock)
        return StockSnapshotChannel(
            provider,
            for_trade_date="20260828",
            source_condition_run_id="condition-20260827",
            clock=self.clock,
        )

    def test_virtual_amounts_are_calculated_in_memory_from_injected_context(self):
        context = VirtualAmountContext(
            window_30m=RatioAmountBaseline(Decimal("20"), Decimal("80")),
            day=RatioAmountBaseline(Decimal("50"), Decimal("200")),
            higher_periods={
                "W": AverageAmountBaseline(Decimal("600"), 3),
                "M": AverageAmountBaseline(Decimal("3000"), 15),
                "Q": AverageAmountBaseline(Decimal("10000"), 50),
                "Y": AverageAmountBaseline(Decimal("30000"), 150),
            },
        )
        view = self.channel().run_cycle(
            (self.stock_request,),
            contexts={self.stock_request.identity_key: context},
            current_30m_elapsed_amounts={self.stock_request.identity_key: Decimal("40")},
        )
        metric = view.states[self.stock_request.identity_key]
        self.assertEqual(metric.virtual_amounts["30m"], Decimal("160"))
        self.assertEqual(metric.virtual_amounts["D"], Decimal("400"))
        self.assertEqual(metric.virtual_amounts["W"], Decimal("250"))
        self.assertTrue(metric.fresh)
        self.assertEqual(view.channel_status, "ready")

    def test_cycles_replace_state_instead_of_accumulating_history(self):
        channel = self.channel()
        first = channel.run_cycle((self.stock_request,))
        second = channel.run_cycle((self.stock_request,))
        self.assertEqual(len(first.states), 1)
        self.assertEqual(len(second.states), 1)
        self.assertEqual((first.version, second.version), (1, 2))
        with self.assertRaises(TypeError):
            second.states["new"] = second.states[self.stock_request.identity_key]

    def test_missing_object_becomes_stale_after_15_seconds_and_recovers(self):
        provider = Provider(StockSnapshotBatch, "stock", self.clock)
        channel = self.channel(provider)
        channel.run_cycle((self.stock_request,))
        provider.omit.add(self.stock_request.identity_key)
        self.clock.advance(5)
        missing = channel.run_cycle((self.stock_request,)).states[self.stock_request.identity_key]
        self.assertFalse(missing.fresh)
        self.assertEqual(missing.live_status, "available")
        self.clock.advance(11)
        stale = channel.run_cycle((self.stock_request,)).states[self.stock_request.identity_key]
        self.assertEqual(stale.live_status, "stale")
        provider.omit.clear()
        recovered = channel.run_cycle((self.stock_request,)).states[self.stock_request.identity_key]
        self.assertTrue(recovered.fresh)
        self.assertEqual(recovered.live_status, "available")

    def test_never_seen_suspended_object_remains_present_and_unavailable(self):
        provider = Provider(StockSnapshotBatch, "stock", self.clock)
        provider.omit.add(self.stock_request.identity_key)
        metric = self.channel(provider).run_cycle((self.stock_request,)).states[self.stock_request.identity_key]
        self.assertIsNone(metric.quote)
        self.assertEqual(metric.live_status, "unavailable")
        self.assertFalse(metric.fresh)

    def test_stock_failure_does_not_block_index_or_board_channels(self):
        stock_provider = Provider(StockSnapshotBatch, "stock", self.clock)
        stock_provider.fail = True
        index_provider = Provider(IndexSnapshotBatch, "index", self.clock)
        board_provider = Provider(BoardSnapshotBatch, "board", self.clock)
        runtime = WindowsN3MemoryRuntime(
            self.channel(stock_provider),
            IndexSnapshotChannel(
                index_provider,
                for_trade_date="20260828",
                source_condition_run_id="condition-20260827",
                clock=self.clock,
            ),
            BoardSnapshotChannel(
                board_provider,
                for_trade_date="20260828",
                source_condition_run_id="condition-20260827",
                clock=self.clock,
            ),
        )
        result = runtime.run_cycle(
            stock_requests=(self.stock_request,),
            index_requests=(self.index_request,),
            board_requests=(self.board_request,),
        )
        self.assertEqual(result.stock.channel_status, "degraded")
        self.assertEqual(result.index.channel_status, "ready")
        self.assertEqual(result.board.channel_status, "ready")
        self.assertTrue(result.index.states[self.index_request.identity_key].fresh)
        self.assertTrue(result.board.states[self.board_request.identity_key].fresh)

    def test_n3_memory_modules_have_no_database_or_ddl_path(self):
        root = Path(__file__).parents[1] / "src" / "ashare_v3" / "market"
        text = "\n".join(
            (root / name).read_text(encoding="utf-8")
            for name in ("windows_n3_snapshot.py", "windows_n3_memory.py")
        )
        for forbidden in ("import psycopg", "INSERT INTO", "CREATE TABLE", ".execute("):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
