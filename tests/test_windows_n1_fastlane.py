from __future__ import annotations

from datetime import date, datetime
import unittest

from ashare_v3.ingestion.windows_n1_fastlane import (
    at_or_after_daily_cutoff,
    calendar_date_is_open,
    daily_cutoff_is_required,
    resolve_daily_source_trade_date,
    run_recent_daily_gap_fill,
)


STOCKS = tuple(f"0000{number:02d}.SZ" for number in range(1, 6))


class FakeCalendar:
    def __init__(self, rows):
        self.rows = list(rows)
        self.fetch_calls = []

    def health(self):
        return {"status": "ok", "database": "up"}

    def fetch(self, start_date, end_date, exchange="SSE"):
        self.fetch_calls.append((start_date, end_date, exchange))
        return [
            row for row in self.rows
            if start_date <= row["cal_date"] <= end_date
        ]


class FakeTQ:
    def __init__(self, *, fail_date=None):
        self.fail_date = fail_date
        self.fetch_calls = []

    def fetch_market_members(self):
        return [
            *({"market": "5", "Code": symbol, "Name": symbol} for symbol in STOCKS),
            {"market": "9", "Code": "000001.SH", "Name": "index"},
            {"market": "11", "Code": "881001.SH", "Name": "industry"},
            {"market": "12", "Code": "880501.SH", "Name": "concept"},
            {"market": "14", "Code": "880201.SH", "Name": "region"},
        ]

    def fetch_daily_batch(self, symbols, *, asset_kind, start_date, end_date):
        self.fetch_calls.append((tuple(symbols), asset_kind, start_date, end_date))
        if start_date == self.fail_date:
            raise RuntimeError("batch failed")
        return {symbol: [bar(start_date)] for symbol in symbols}


class FakeRepository:
    def __init__(self, *, last_complete=None):
        self.last_complete = last_complete
        self.rows_by_table_date = {}

    def latest_fastlane_complete_date(self, before_date):
        if self.last_complete is not None and self.last_complete < before_date:
            return self.last_complete
        return None

    def daily_bar_counts(self, trade_date):
        result = {}
        for asset, table in (
            ("stock", "stock_daily_bar_fact"),
            ("index", "index_daily_bar_fact"),
            ("board", "board_daily_bar_fact"),
        ):
            rows = self.rows_by_table_date.get((table, trade_date), [])
            identity_column = f"{asset}_identity_key"
            result[asset] = {
                "rows": len(rows),
                "entities": len({row[identity_column] for row in rows}),
            }
        return result

    def persist_batch(self, *, table, rows, trade_date, **_kwargs):
        self.rows_by_table_date.setdefault((table, trade_date), []).extend(rows)

    def daily_bar_source_counts(self, trade_date, source_version):
        result = {}
        for asset, table in (
            ("stock", "stock_daily_bar_fact"),
            ("index", "index_daily_bar_fact"),
            ("board", "board_daily_bar_fact"),
        ):
            rows = [
                row for row in self.rows_by_table_date.get((table, trade_date), [])
                if row["source_version"] == source_version
            ]
            identity_column = f"{asset}_identity_key"
            unique_rows = {
                (row[identity_column], row["trade_date"], row["source_version"])
                for row in rows
            }
            result[asset] = {
                "rows": len(unique_rows),
                "entities": len({row[identity_column] for row in rows}),
            }
        return result


def calendar_rows(*dates):
    return [
        {"exchange": "SSE", "cal_date": value, "is_open": "1"}
        for value in dates
    ]


def bar(trade_date):
    return {
        "Date": trade_date + ".000",
        "Open": 1,
        "High": 2,
        "Low": 1,
        "Close": 2,
        "Volume": 10,
        "Amount": 20,
        "ForwardFactor": 1,
    }


class WindowsN1FastlaneTest(unittest.TestCase):
    def test_cutoff_is_inclusive(self):
        self.assertFalse(at_or_after_daily_cutoff(datetime(2026, 8, 27, 16, 29, 59)))
        self.assertTrue(at_or_after_daily_cutoff(datetime(2026, 8, 27, 16, 30, 0)))

    def test_fixed_historical_date_bypasses_today_cutoff(self):
        today = date(2026, 9, 1)
        self.assertEqual(
            resolve_daily_source_trade_date("20260831", today=today),
            "20260831",
        )
        self.assertFalse(daily_cutoff_is_required("20260831", today=today))
        self.assertTrue(daily_cutoff_is_required("20260901", today=today))

    def test_default_daily_date_is_today(self):
        self.assertEqual(
            resolve_daily_source_trade_date(None, today=date(2026, 9, 1)),
            "20260901",
        )

    def test_invalid_or_future_source_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "YYYYMMDD"):
            resolve_daily_source_trade_date("2026-08-31", today=date(2026, 9, 1))
        with self.assertRaisesRegex(ValueError, "future"):
            resolve_daily_source_trade_date("20260902", today=date(2026, 9, 1))

    def test_closed_day_is_read_only_skip_signal(self):
        calendar = FakeCalendar([
            {"exchange": "SSE", "cal_date": "20260829", "is_open": "0"}
        ])
        self.assertFalse(calendar_date_is_open(calendar, "20260829"))

    def test_missing_marker_does_not_scan_history(self):
        calendar = FakeCalendar(calendar_rows("20260826", "20260827"))
        result = run_recent_daily_gap_fill(
            today="20260827",
            run_id="gap1",
            calendar=calendar,
            tq=FakeTQ(),
            repository=FakeRepository(),
        )
        self.assertEqual(result.result, "NO_FASTLANE_COMPLETION_MARKER")
        self.assertEqual(calendar.fetch_calls, [])

    def test_no_gap_runs_no_provider_batches(self):
        tq = FakeTQ()
        result = run_recent_daily_gap_fill(
            today="20260827",
            run_id="gap2",
            calendar=FakeCalendar(calendar_rows("20260826", "20260827")),
            tq=tq,
            repository=FakeRepository(last_complete="20260826"),
        )
        self.assertEqual(result.result, "NO_RECENT_DAILY_GAP")
        self.assertEqual(tq.fetch_calls, [])

    def test_consecutive_gaps_fill_stock_index_and_board_in_date_order(self):
        repository = FakeRepository(last_complete="20260825")
        tq = FakeTQ()
        result = run_recent_daily_gap_fill(
            today="20260828",
            run_id="gap3",
            calendar=FakeCalendar(calendar_rows(
                "20260825", "20260826", "20260827", "20260828"
            )),
            tq=tq,
            repository=repository,
        )
        self.assertEqual(result.gap_dates, ("20260826", "20260827"))
        self.assertEqual([item.trade_date for item in result.dates], [
            "20260826", "20260827"
        ])
        self.assertTrue(all(item.after_counts["stock"]["entities"] == 5 for item in result.dates))
        self.assertTrue(all(item.after_counts["index"]["entities"] == 1 for item in result.dates))
        self.assertTrue(all(item.after_counts["board"]["entities"] == 3 for item in result.dates))
        self.assertTrue(all(item.batch_counts["failed"] == 0 for item in result.dates))

    def test_batch_failure_keeps_marker_unadvanced_by_raising(self):
        with self.assertRaisesRegex(RuntimeError, "batch failures"):
            run_recent_daily_gap_fill(
                today="20260827",
                run_id="gap4",
                calendar=FakeCalendar(calendar_rows("20260825", "20260826", "20260827")),
                tq=FakeTQ(fail_date="20260826"),
                repository=FakeRepository(last_complete="20260825"),
            )


if __name__ == "__main__":
    unittest.main()
