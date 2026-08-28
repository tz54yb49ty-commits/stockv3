from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

from ashare_v3.market.windows_n3_intraday import (
    WindowsN3IntradayRunner,
    completed_window_count,
    is_live_session,
)
from ashare_v3.market.windows_n3_minute_context import (
    MinuteContextBatch,
    build_minute_context,
    normalize_minute_bars,
)
from ashare_v3.market.windows_n3_read_model import (
    N2ObjectRuntimeInput,
    N2PeriodRuntimeBaseline,
    N3ActiveReadModel,
)


TZ = ZoneInfo("Asia/Shanghai")


def object_input(kind, key, exchange, code, name):
    periods = {
        period: N2PeriodRuntimeBaseline(
            period,
            "volume_up",
            "flat->volume_up",
            Decimal("12"),
            Decimal("10"),
            Decimal("100"),
            Decimal("600"),
            3,
        )
        for period in ("Y", "Q", "M", "W", "D")
    }
    return N2ObjectRuntimeInput(kind, key, exchange, code, name, periods)


def model():
    return N3ActiveReadModel(
        run_id="condition-20260827",
        source_trade_date="20260827",
        for_trade_date="20260828",
        stock=(object_input("stock", "stock:SH:600000", "SH", "600000", "浦发"),),
        index=(object_input("index", "index:SH:000001", "SH", "000001", "上证"),),
        board=(object_input("board", "board:TDX:881333", "SH", "881333", "元器件"),),
    )


def rows(trade_date, count=240):
    result = []
    day = datetime.strptime(trade_date, "%Y%m%d")
    for index in range(count):
        if index < 120:
            point = day.replace(hour=9, minute=30) + timedelta(minutes=index)
        else:
            point = day.replace(hour=13, minute=0) + timedelta(minutes=index - 120)
        result.append(SimpleNamespace(time=point, open="10", high="12", low="9", close="11", amount="10"))
    return result


def context(identity_key, trade_date, count=240):
    bars = normalize_minute_bars(identity_key, trade_date, rows(trade_date, count))
    return build_minute_context(identity_key, trade_date, bars)


class Repository:
    def __init__(self, open_date=True):
        self.open_date = open_date
        self.loaded = 0

    def is_open_trade_date(self, _date):
        return self.open_date

    def load_active(self, _date):
        self.loaded += 1
        return model()


class MinuteProvider:
    def __init__(self, asset_kind, fail=False):
        self.asset_kind = asset_kind
        self.fail = fail
        self.calls = []

    def fetch_many(self, requests, trade_date, *, require_complete=True):
        self.calls.append((trade_date, require_complete, tuple(row.identity_key for row in requests)))
        if self.fail:
            raise RuntimeError(f"{self.asset_kind} failed")
        count = 240 if require_complete else 35
        values = {
            request.identity_key: context(request.identity_key, trade_date, count)
            for request in requests
        }
        return MinuteContextBatch(values, (), (), f"fake.{self.asset_kind}")


class ContextLoader:
    def __init__(self):
        self.calls = []

    def load(self, active_model):
        self.calls.append(active_model.run_id)
        return SimpleNamespace(
            stock={"stock:SH:600000": context("stock:SH:600000", "20260827")},
            index={"index:SH:000001": context("index:SH:000001", "20260827")},
            board={"board:TDX:881333": context("board:TDX:881333", "20260827")},
        )


class Runtime:
    def __init__(self):
        self.calls = []

    def run_cycle(self, **kwargs):
        self.calls.append(kwargs)
        view = SimpleNamespace(channel_status="ready", states={})
        return SimpleNamespace(stock=view, index=view, board=view)


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class WindowsN3IntradayTest(unittest.TestCase):
    def make_runner(self, *, now, repository=None, stock=None, index=None, board=None):
        runtime = Runtime()
        clock = Clock(now)
        runner = WindowsN3IntradayRunner(
            repository=repository or Repository(),
            context_loader=ContextLoader(),
            current_stock_minute_provider=stock or MinuteProvider("stock"),
            current_index_minute_provider=index or MinuteProvider("index"),
            current_board_minute_provider=board or MinuteProvider("board"),
            runtime_factory=lambda _model: runtime,
            clock=clock,
            sleep=lambda _seconds: None,
        )
        return runner, runtime, clock

    def test_non_trading_day_exits_before_n2_or_market_provider(self):
        repository = Repository(open_date=False)
        stock = MinuteProvider("stock")
        runner, _runtime, _clock = self.make_runner(
            now=datetime(2026, 8, 29, 9, 15, tzinfo=TZ),
            repository=repository,
            stock=stock,
        )
        self.assertIsNone(runner.prepare("20260829"))
        self.assertEqual(repository.loaded, 0)
        self.assertEqual(stock.calls, [])

    def test_0915_preload_reads_compressed_database_context_without_minute_requests(self):
        stock = MinuteProvider("stock")
        index = MinuteProvider("index")
        board = MinuteProvider("board")
        runner, _runtime, _clock = self.make_runner(
            now=datetime(2026, 8, 28, 9, 15, tzinfo=TZ),
            stock=stock,
            index=index,
            board=board,
        )
        session = runner.prepare("20260828")
        self.assertIsNotNone(session)
        self.assertEqual(stock.calls, [])
        self.assertEqual(index.calls, [])
        self.assertEqual(board.calls, [])
        self.assertEqual(len(session.previous_stock), 1)
        self.assertEqual(len(session.previous_index), 1)
        self.assertEqual(len(session.previous_board), 1)

    def test_late_start_rebuilds_current_closed_minutes_before_first_cycle(self):
        stock = MinuteProvider("stock")
        runner, runtime, _clock = self.make_runner(
            now=datetime(2026, 8, 28, 10, 5, tzinfo=TZ),
            stock=stock,
        )
        session = runner.prepare("20260828")
        self.assertEqual(stock.calls[0][0:2], ("20260828", False))
        cycle = runner.run_one_cycle(session, datetime(2026, 8, 28, 10, 5, tzinfo=TZ))
        call = runtime.calls[-1]
        key = "stock:SH:600000"
        self.assertEqual(call["stock_30m_elapsed"][key], Decimal("50"))
        self.assertEqual(cycle.stock_30m_references[key].bucket_index, 1)
        self.assertEqual(cycle.stock_30m_references[key].adjacent_completed_entity_high, Decimal("11"))
        runner.run_one_cycle(session, datetime(2026, 8, 28, 10, 30, 5, tzinfo=TZ))
        self.assertEqual(len(stock.calls), 1)

    def test_late_rebuild_channel_failure_does_not_block_database_context(self):
        runner, _runtime, _clock = self.make_runner(
            now=datetime(2026, 8, 28, 10, 5, tzinfo=TZ),
            stock=MinuteProvider("stock", fail=True),
        )
        session = runner.prepare("20260828")
        self.assertEqual(len(session.previous_stock), 1)
        self.assertEqual(len(session.previous_index), 1)
        self.assertEqual(len(session.previous_board), 1)
        self.assertEqual(session.current_stock, {})

    def test_schedule_helpers_cover_sessions_lunch_and_all_boundaries(self):
        self.assertTrue(is_live_session(datetime(2026, 8, 28, 9, 30).time()))
        self.assertFalse(is_live_session(datetime(2026, 8, 28, 12, 0).time()))
        self.assertTrue(is_live_session(datetime(2026, 8, 28, 15, 0).time()))
        self.assertFalse(is_live_session(datetime(2026, 8, 28, 15, 1).time()))
        self.assertEqual(completed_window_count(datetime(2026, 8, 28, 9, 59).time()), 0)
        self.assertEqual(completed_window_count(datetime(2026, 8, 28, 11, 30).time()), 4)
        self.assertEqual(completed_window_count(datetime(2026, 8, 28, 13, 0).time()), 4)
        self.assertEqual(completed_window_count(datetime(2026, 8, 28, 15, 0).time()), 8)

    def test_after_close_start_exits_without_loading_n2_or_minutes(self):
        repository = Repository()
        stock = MinuteProvider("stock")
        runner, _runtime, _clock = self.make_runner(
            now=datetime(2026, 8, 28, 15, 1, tzinfo=TZ),
            repository=repository,
            stock=stock,
        )
        summary = runner.execute("20260828")
        self.assertEqual(summary.result, "OUTSIDE_SESSION_SKIPPED")
        self.assertEqual(summary.cycles, 0)
        self.assertEqual(repository.loaded, 0)
        self.assertEqual(stock.calls, [])

    def test_new_n3_modules_do_not_write_sql_emit_events_or_import_n4(self):
        root = Path(__file__).parents[1]
        text = "\n".join(
            (root / path).read_text(encoding="utf-8")
            for path in (
                "src/ashare_v3/market/windows_n3_minute_context.py",
                "src/ashare_v3/market/windows_n3_intraday.py",
                "src/ashare_v3/market/windows_n3_read_model.py",
                "scripts/run_windows_n3_memory.py",
            )
        )
        for forbidden in (
            "INSERT INTO",
            "UPDATE ",
            "DELETE FROM",
            "CREATE TABLE",
            "common_trigger",
            "ashare_v3.trigger",
            "ashare_v3.action",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
