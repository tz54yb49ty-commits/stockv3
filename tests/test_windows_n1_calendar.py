from __future__ import annotations

import unittest

from ashare_v3.ingestion.windows_n1_calendar import sync_local_trade_calendar
from ashare_v3.ingestion.windows_n1_sources import LOCAL_TRADE_CALENDAR_SOURCE


class _Transaction:
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class _Connection:
    def transaction(self): return _Transaction()


class FakeProvider:
    def health(self): return {"status": "ok", "database": "up"}
    def range(self, exchange): return {"exchange": exchange, "min": "20260101", "max": "20260104"}
    def fetch(self, start_date, end_date, exchange):
        return [
            {"exchange": exchange, "cal_date": "20260101", "is_open": "0", "pretrade_date": "20251231"},
            {"exchange": exchange, "cal_date": "20260102", "is_open": "1", "pretrade_date": "20251231"},
            {"exchange": exchange, "cal_date": "20260103", "is_open": "0", "pretrade_date": "20260102"},
            {"exchange": exchange, "cal_date": "20260104", "is_open": "0", "pretrade_date": "20260102"},
        ]


class FakeRepository:
    def __init__(self):
        self.connection = _Connection()
        self.persisted = None
        self.downstream_calls = 0

    def downstream_row_counts(self):
        self.downstream_calls += 1
        return {}

    def persist_local_trade_calendar(self, **kwargs):
        self.persisted = kwargs

    def assert_n1_final_ready_for_n2(self, **kwargs):
        return {
            "calendar_rows": kwargs["expected_calendar_rows"],
            "calendar_open_rows": 1,
            "calendar_start": kwargs["start_date"],
            "calendar_end": kwargs["end_date"],
            "calendar_source": LOCAL_TRADE_CALENDAR_SOURCE,
            "calendar_source_batch_id": self.persisted["batch_id"],
        }


class WindowsN1CalendarTest(unittest.TestCase):
    def test_sync_normalizes_persists_and_stops_at_n1_final_gate(self):
        repository = FakeRepository()
        result = sync_local_trade_calendar(provider=FakeProvider(), repository=repository)
        self.assertEqual(result.result, "N1_FINAL_READY_FOR_N2")
        self.assertEqual(result.api_rows, 4)
        self.assertEqual(repository.downstream_calls, 2)
        rows = repository.persisted["rows"]
        self.assertEqual([row["trade_date"] for row in rows], ["20260101", "20260102", "20260103", "20260104"])
        self.assertEqual([row["next_trade_date"] for row in rows], ["20260102", None, None, None])
        self.assertTrue(all(row["source"] == LOCAL_TRADE_CALENDAR_SOURCE for row in rows))
        self.assertTrue(result.evidence["uses_rest_only"])
        self.assertFalse(result.evidence["trade_calendar_database_access"])
        self.assertEqual(result.evidence["downstream_delta"], 0)

    def test_provider_failure_happens_before_database_access(self):
        class FailedProvider(FakeProvider):
            def health(self): raise RuntimeError("service down")
        repository = FakeRepository()
        with self.assertRaisesRegex(RuntimeError, "service down"):
            sync_local_trade_calendar(provider=FailedProvider(), repository=repository)
        self.assertIsNone(repository.persisted)
        self.assertEqual(repository.downstream_calls, 0)


if __name__ == "__main__":
    unittest.main()
