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
    ThirtyMinuteAmountTracker,
    VirtualAmountContext,
    WindowsN3MemoryRuntime,
    calculate_virtual_amounts,
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


class SlowFailureProvider(Provider):
    def fetch_many(self, requests):
        self.calls += 1
        self.clock.advance(16)
        raise RuntimeError(f"{self.asset_kind} unavailable")


class SlowSuccessProvider(Provider):
    def fetch_many(self, requests):
        self.clock.advance(6)
        return super().fetch_many(requests)


class AmountSequenceProvider(Provider):
    def __init__(self, batch_type, asset_kind, clock, amounts):
        super().__init__(batch_type, asset_kind, clock)
        self.amounts = iter(amounts)

    def fetch_many(self, requests):
        self.calls += 1
        amount = next(self.amounts)
        rows = tuple(
            make_quote(
                request,
                asset_kind=self.asset_kind,
                observed_at=self.clock(),
                amount=amount,
            )
            for request in requests
        )
        return self.batch_type(rows, (), f"fake-{self.asset_kind}", self.clock())


class WindowsN3MemoryTest(unittest.TestCase):
    def test_channel_batch_over_five_seconds_is_stale_at_completion_time(self):
        provider = SlowSuccessProvider(StockSnapshotBatch, "stock", self.clock)
        view = self.channel(provider).run_cycle((self.stock_request,))
        metric = view.states[self.stock_request.identity_key]
        self.assertEqual(view.generated_at, self.clock.value)
        self.assertEqual(view.channel_status, "degraded")
        self.assertEqual(metric.live_status, "stale")
        self.assertFalse(metric.fresh)

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
        self.clock.value = datetime(2026, 8, 28, 2, 5, tzinfo=timezone.utc)
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

    def test_restart_seed_is_one_shot_for_stock_index_and_board_channels(self):
        context = VirtualAmountContext(
            window_30m=RatioAmountBaseline(Decimal("20"), Decimal("80")),
        )
        cases = (
            (StockSnapshotChannel, StockSnapshotBatch, "stock", self.stock_request),
            (IndexSnapshotChannel, IndexSnapshotBatch, "index", self.index_request),
            (BoardSnapshotChannel, BoardSnapshotBatch, "board", self.board_request),
        )
        for channel_type, batch_type, asset_kind, request in cases:
            with self.subTest(asset_kind=asset_kind):
                self.clock.value = datetime(2026, 8, 28, 2, 5, tzinfo=timezone.utc)
                provider = AmountSequenceProvider(
                    batch_type,
                    asset_kind,
                    self.clock,
                    ("200", "230"),
                )
                channel = channel_type(
                    provider,
                    for_trade_date="20260828",
                    source_condition_run_id="condition-20260827",
                    clock=self.clock,
                )
                first = channel.run_cycle(
                    (request,),
                    contexts={request.identity_key: context},
                    current_30m_elapsed_amounts={request.identity_key: Decimal("25")},
                )
                self.assertEqual(first.states[request.identity_key].virtual_amounts["30m"], Decimal("100"))
                self.clock.advance(300)
                second = channel.run_cycle(
                    (request,),
                    contexts={request.identity_key: context},
                    current_30m_elapsed_amounts={request.identity_key: Decimal("25")},
                )
                self.assertEqual(second.states[request.identity_key].virtual_amounts["30m"], Decimal("220"))

    def test_first_trading_bucket_30m_amount_is_derived_from_daily_cumulative_amount(self):
        context = VirtualAmountContext(
            window_30m=RatioAmountBaseline(Decimal("20"), Decimal("80")),
        )
        view = self.channel().run_cycle(
            (self.stock_request,),
            contexts={self.stock_request.identity_key: context},
        )
        self.assertEqual(
            view.states[self.stock_request.identity_key].virtual_amounts["30m"],
            Decimal("400"),
        )

    def test_mid_bucket_restart_requires_seed_then_continues_in_memory(self):
        tracker = ThirtyMinuteAmountTracker()
        self.clock.value = datetime(2026, 8, 28, 2, 5, tzinfo=timezone.utc)
        first = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="200",
        )
        self.assertIsNone(tracker.observe(first))
        self.assertEqual(tracker.observe(first, elapsed_amount_seed=Decimal("25")), Decimal("25"))
        self.clock.advance(300)
        later = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="230",
        )
        self.assertEqual(
            tracker.observe(later, elapsed_amount_seed=Decimal("25")),
            Decimal("55"),
        )

    def test_mid_bucket_amount_regression_invalidates_seed_until_next_boundary(self):
        tracker = ThirtyMinuteAmountTracker()
        self.clock.value = datetime(2026, 8, 28, 2, 5, tzinfo=timezone.utc)
        first = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="200",
        )
        self.assertEqual(tracker.observe(first, elapsed_amount_seed=Decimal("25")), Decimal("25"))
        self.clock.advance(300)
        regressed = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="190",
        )
        self.assertIsNone(tracker.observe(regressed, elapsed_amount_seed=Decimal("25")))
        self.clock.advance(300)
        recovered_amount = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="210",
        )
        self.assertIsNone(tracker.observe(recovered_amount, elapsed_amount_seed=Decimal("25")))
        self.clock.value = datetime(2026, 8, 28, 2, 29, 55, tzinfo=timezone.utc)
        before_next_boundary = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="220",
        )
        self.assertIsNone(tracker.observe(before_next_boundary, elapsed_amount_seed=Decimal("25")))
        self.clock.value = datetime(2026, 8, 28, 2, 30, tzinfo=timezone.utc)
        after_next_boundary = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="225",
        )
        self.assertEqual(tracker.observe(after_next_boundary), Decimal("5"))

    def test_first_bucket_amount_regression_stays_invalid_until_next_boundary(self):
        tracker = ThirtyMinuteAmountTracker()
        self.clock.value = datetime(2026, 8, 28, 1, 35, tzinfo=timezone.utc)
        first = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="100",
        )
        self.assertEqual(tracker.observe(first), Decimal("100"))
        self.clock.advance(300)
        regressed = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="90",
        )
        self.assertIsNone(tracker.observe(regressed))
        self.clock.advance(300)
        later = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="110",
        )
        self.assertIsNone(tracker.observe(later))
        self.clock.value = datetime(2026, 8, 28, 1, 59, 55, tzinfo=timezone.utc)
        before_next_boundary = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="120",
        )
        self.assertIsNone(tracker.observe(before_next_boundary))
        self.clock.value = datetime(2026, 8, 28, 2, 0, tzinfo=timezone.utc)
        after_next_boundary = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="125",
        )
        self.assertEqual(tracker.observe(after_next_boundary), Decimal("5"))

    def test_safe_30m_boundary_uses_previous_cumulative_amount(self):
        tracker = ThirtyMinuteAmountTracker()
        self.clock.value = datetime(2026, 8, 28, 1, 59, 50, tzinfo=timezone.utc)
        before = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="200",
        )
        self.assertEqual(tracker.observe(before), Decimal("200"))
        self.clock.advance(10)
        after = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="210",
        )
        self.assertEqual(tracker.observe(after), Decimal("10"))

    def test_1015_virtual_amount_uses_boundary_delta_and_same_progress_ratio(self):
        tracker = ThirtyMinuteAmountTracker()
        self.clock.value = datetime(2026, 8, 28, 1, 59, 55, tzinfo=timezone.utc)
        before = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="100",
        )
        self.assertEqual(tracker.observe(before), Decimal("100"))
        self.clock.value = datetime(2026, 8, 28, 2, 15, tzinfo=timezone.utc)
        current = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="160",
        )
        elapsed = tracker.observe(current)
        self.assertEqual(elapsed, Decimal("60"))
        projected = calculate_virtual_amounts(
            current,
            VirtualAmountContext(
                window_30m=RatioAmountBaseline(Decimal("30"), Decimal("90")),
            ),
            current_30m_elapsed_amount=elapsed,
        )
        self.assertEqual(projected["30m"], Decimal("180"))

    def test_lunch_boundary_uses_1130_cumulative_amount_for_1300_window(self):
        tracker = ThirtyMinuteAmountTracker()
        self.clock.value = datetime(2026, 8, 28, 3, 29, 55, tzinfo=timezone.utc)
        morning_close = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="500",
        )
        self.assertIsNone(tracker.observe(morning_close))
        self.clock.value = datetime(2026, 8, 28, 5, 15, tzinfo=timezone.utc)
        afternoon = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="560",
        )
        self.assertEqual(tracker.observe(afternoon), Decimal("60"))

    def test_missing_safe_boundary_keeps_later_bucket_unavailable(self):
        tracker = ThirtyMinuteAmountTracker()
        self.clock.value = datetime(2026, 8, 28, 3, 29, 30, tzinfo=timezone.utc)
        old_morning_quote = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="500",
        )
        self.assertIsNone(tracker.observe(old_morning_quote))
        self.clock.value = datetime(2026, 8, 28, 5, 15, tzinfo=timezone.utc)
        afternoon = make_quote(
            self.stock_request,
            asset_kind="stock",
            observed_at=self.clock(),
            amount="560",
        )
        self.assertIsNone(tracker.observe(afternoon))

    def test_30m_tracker_prunes_objects_outside_current_universe(self):
        tracker = ThirtyMinuteAmountTracker()
        other = StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安")
        tracker.observe(make_quote(self.stock_request, asset_kind="stock", observed_at=self.clock()))
        tracker.observe(make_quote(other, asset_kind="stock", observed_at=self.clock()))
        self.assertEqual(tracker.size, 2)
        tracker.retain({self.stock_request.identity_key})
        self.assertEqual(tracker.size, 1)

    def test_cycles_replace_state_instead_of_accumulating_history(self):
        channel = self.channel()
        first = channel.run_cycle((self.stock_request,))
        second = channel.run_cycle((self.stock_request,))
        self.assertEqual(len(first.states), 1)
        self.assertEqual(len(second.states), 1)
        self.assertEqual((first.version, second.version), (1, 2))
        with self.assertRaises(TypeError):
            second.states["new"] = second.states[self.stock_request.identity_key]
        self.assertEqual(channel.events.qsize(), 1)
        self.assertEqual(channel.events.get_nowait().version, 2)

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

    def test_partial_object_error_keeps_channel_ready(self):
        provider = Provider(StockSnapshotBatch, "stock", self.clock)
        other = StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安")

        def fetch_many(requests):
            row = make_quote(requests[0], asset_kind="stock", observed_at=self.clock())
            return StockSnapshotBatch(
                (row,),
                (requests[1].identity_key,),
                "fake-stock",
                self.clock(),
                ("single_object_error",),
            )

        provider.fetch_many = fetch_many
        view = self.channel(provider).run_cycle((self.stock_request, other))
        self.assertEqual(view.channel_status, "ready")
        self.assertEqual(view.error_summary, "single_object_error")
        self.assertEqual(view.states[other.identity_key].live_status, "unavailable")

    def test_slow_channel_failure_uses_completion_time_for_stale_age(self):
        provider = Provider(StockSnapshotBatch, "stock", self.clock)
        channel = self.channel(provider)
        channel.run_cycle((self.stock_request,))
        channel.provider = SlowFailureProvider(StockSnapshotBatch, "stock", self.clock)
        failed = channel.run_cycle((self.stock_request,))
        metric = failed.states[self.stock_request.identity_key]
        self.assertEqual(failed.channel_status, "degraded")
        self.assertEqual(metric.live_status, "stale")
        self.assertFalse(metric.fresh)

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
