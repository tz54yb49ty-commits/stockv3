from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest

from ashare_v3.market.windows_n3_memory import AverageAmountBaseline
from ashare_v3.market.windows_n3_minute_context import (
    EltdxBoardMinuteContextProvider,
    EltdxIndexMinuteContextProvider,
    EltdxStockMinuteContextProvider,
    build_cycle_inputs,
    build_minute_context,
    normalize_minute_bars,
    trading_elapsed_minutes,
)
from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotRequest,
    IndexSnapshotRequest,
    StockSnapshotRequest,
)


def raw_day(*, start_labelled=True, count=240, amount="10"):
    rows = []
    for index in range(count):
        if index < 120:
            hour = 9 + (30 + index) // 60
            minute = (30 + index) % 60
        else:
            hour = 13 + (index - 120) // 60
            minute = (index - 120) % 60
        if not start_labelled:
            point = datetime(2026, 8, 27, hour, minute)
            point = point.replace(second=0)
            from datetime import timedelta
            point += timedelta(minutes=1)
        else:
            point = datetime(2026, 8, 27, hour, minute)
        rows.append(
            SimpleNamespace(
                time=point,
                open="10",
                high="12",
                low="9",
                close="11",
                amount=amount,
            )
        )
    return rows


class FakeBarsClient:
    def __init__(self, rows):
        self.bars = self
        self.rows = rows
        self.calls = []

    def get(self, code, **kwargs):
        self.calls.append((code, kwargs))
        return self.rows


class RetryBarsClient:
    def __init__(self, rows_by_code):
        self.bars = self
        self.rows_by_code = {
            code: list(values) for code, values in rows_by_code.items()
        }
        self.calls = []

    def get(self, code, **kwargs):
        self.calls.append((code, kwargs))
        values = self.rows_by_code[code]
        value = values.pop(0) if len(values) > 1 else values[0]
        if isinstance(value, Exception):
            raise value
        return value


class WindowsN3MinuteContextTest(unittest.TestCase):
    def setUp(self):
        self.stock = StockSnapshotRequest("stock:SH:600000", "SH", "600000", "浦发")
        self.index = IndexSnapshotRequest("index:SZ:399001", "SZ", "399001", "深成")
        self.board = BoardSnapshotRequest("board:TDX:881333", "SH", "881333", "元器件")

    def test_start_labelled_day_is_normalized_to_240_close_labels_and_8_windows(self):
        bars = normalize_minute_bars(self.stock.identity_key, "20260827", raw_day())
        context = build_minute_context(self.stock.identity_key, "20260827", bars)
        self.assertEqual(len(context.bars), 240)
        self.assertEqual((context.bars[0].time_label, context.bars[-1].time_label), ("09:31", "15:00"))
        self.assertEqual(len(context.windows), 8)
        self.assertEqual(context.full_day_amount, Decimal("2400"))
        self.assertEqual(context.windows[0].full_amount, Decimal("300"))
        self.assertEqual(context.windows[0].cumulative_amounts[4], Decimal("50"))

    def test_close_labelled_day_is_not_shifted_twice(self):
        bars = normalize_minute_bars(
            self.stock.identity_key,
            "20260827",
            raw_day(start_labelled=False),
        )
        self.assertEqual(len(bars), 240)
        self.assertEqual((bars[0].time_label, bars[-1].time_label), ("09:31", "15:00"))

    def test_three_eltdx_providers_use_independent_code_and_kind_contracts(self):
        stock_client = FakeBarsClient(raw_day())
        index_client = FakeBarsClient(raw_day())
        board_client = FakeBarsClient(raw_day())
        stock = EltdxStockMinuteContextProvider(stock_client, max_workers=1)
        index = EltdxIndexMinuteContextProvider(index_client, max_workers=1)
        board = EltdxBoardMinuteContextProvider(board_client, max_workers=1)
        self.assertEqual(len(stock.fetch_many((self.stock,), "20260827").contexts), 1)
        self.assertEqual(len(index.fetch_many((self.index,), "20260827").contexts), 1)
        self.assertEqual(len(board.fetch_many((self.board,), "20260827").contexts), 1)
        self.assertEqual(stock_client.calls[0][0], "sh600000")
        self.assertEqual(index_client.calls[0][0], "sz399001")
        self.assertEqual(board_client.calls[0][0], "sh881333")
        self.assertEqual(stock_client.calls[0][1]["kind"], "stock")
        self.assertEqual(index_client.calls[0][1]["kind"], "index")
        self.assertEqual(board_client.calls[0][1]["kind"], "index")
        self.assertEqual(stock_client.calls[0][1]["period"], "1m")
        self.assertEqual(stock_client.calls[0][1]["count"], 320)

    def test_incomplete_previous_day_is_unavailable_not_fabricated(self):
        client = FakeBarsClient(raw_day(count=239))
        batch = EltdxStockMinuteContextProvider(
            client,
            max_workers=1,
            sleep=lambda _value: None,
        ).fetch_many(
            (self.stock,),
            "20260827",
        )
        self.assertEqual(batch.contexts, {})
        self.assertEqual(batch.missing_identity_keys, (self.stock.identity_key,))

    def test_eltdx_retries_only_failed_objects_with_fixed_delays(self):
        second = StockSnapshotRequest(
            "stock:SH:600001",
            "SH",
            "600001",
            "第二只",
        )
        delays = []
        client = RetryBarsClient(
            {
                "sh600000": [RuntimeError("one"), RuntimeError("two"), raw_day()],
                "sh600001": [raw_day()],
            }
        )
        batch = EltdxStockMinuteContextProvider(
            client,
            max_workers=2,
            sleep=delays.append,
        ).fetch_many((self.stock, second), "20260827")
        calls = [code for code, _kwargs in client.calls]
        self.assertEqual(calls.count("sh600000"), 3)
        self.assertEqual(calls.count("sh600001"), 1)
        self.assertEqual(delays, [0.5, 1.5])
        self.assertEqual(set(batch.contexts), {self.stock.identity_key, second.identity_key})

    def test_day_and_30m_virtual_context_use_same_progress_previous_day(self):
        previous_bars = normalize_minute_bars(self.stock.identity_key, "20260827", raw_day())
        previous = build_minute_context(self.stock.identity_key, "20260827", previous_bars)
        current_rows = raw_day(count=5, amount="20")
        for row in current_rows:
            row.time = row.time.replace(day=28)
        current_bars = normalize_minute_bars(self.stock.identity_key, "20260828", current_rows)
        current = build_minute_context(self.stock.identity_key, "20260828", current_bars)
        contexts, elapsed, references = build_cycle_inputs(
            {self.stock.identity_key: previous},
            {self.stock.identity_key: current},
            {
                self.stock.identity_key: {
                    "W": AverageAmountBaseline(Decimal("600"), 3),
                }
            },
            datetime(2026, 8, 28, 9, 35),
        )
        value = contexts[self.stock.identity_key]
        self.assertEqual(value.day.previous_same_elapsed_amount, Decimal("50"))
        self.assertEqual(value.day.previous_full_amount, Decimal("2400"))
        self.assertEqual(value.window_30m.previous_same_elapsed_amount, Decimal("50"))
        self.assertEqual(value.window_30m.previous_full_amount, Decimal("300"))
        self.assertEqual(elapsed[self.stock.identity_key], Decimal("100"))
        reference = references[self.stock.identity_key]
        self.assertEqual(reference.bucket_index, 0)
        self.assertEqual(reference.previous_day_same_window_amount, Decimal("300"))
        self.assertEqual(reference.adjacent_completed_entity_high, Decimal("11"))
        self.assertEqual(reference.adjacent_completed_entity_low, Decimal("10"))

    def test_second_window_uses_current_day_previous_completed_window_for_price_only(self):
        previous = build_minute_context(
            self.stock.identity_key,
            "20260827",
            normalize_minute_bars(self.stock.identity_key, "20260827", raw_day()),
        )
        current_rows = raw_day(count=35, amount="20")
        for row in current_rows:
            row.time = row.time.replace(day=28)
        current_rows[0].open = "8"
        current_rows[29].close = "13"
        current = build_minute_context(
            self.stock.identity_key,
            "20260828",
            normalize_minute_bars(self.stock.identity_key, "20260828", current_rows),
        )
        contexts, elapsed, references = build_cycle_inputs(
            {self.stock.identity_key: previous},
            {self.stock.identity_key: current},
            {},
            datetime(2026, 8, 28, 10, 5),
        )
        self.assertEqual(contexts[self.stock.identity_key].window_30m.previous_full_amount, Decimal("300"))
        self.assertEqual(elapsed[self.stock.identity_key], Decimal("100"))
        self.assertEqual(references[self.stock.identity_key].adjacent_completed_entity_high, Decimal("13"))
        self.assertEqual(references[self.stock.identity_key].adjacent_completed_entity_low, Decimal("8"))

    def test_lunch_elapsed_label_is_fixed_at_120(self):
        self.assertEqual(trading_elapsed_minutes(datetime(2026, 8, 28, 11, 30).time()), 120)
        self.assertEqual(trading_elapsed_minutes(datetime(2026, 8, 28, 12, 45).time()), 120)
        self.assertEqual(trading_elapsed_minutes(datetime(2026, 8, 28, 13, 1).time()), 121)


if __name__ == "__main__":
    unittest.main()
