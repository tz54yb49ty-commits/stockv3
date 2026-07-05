import unittest
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.common_index import (
    normalize_index_identity_row,
    normalize_trade_calendar_rows,
    run_common_index_ingestion_dry_run,
)


class FakeCommonIndexSource:
    def fetch_trade_calendar(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        return [
            {"exchange": "SSE", "cal_date": "20230103", "is_open": 1, "pretrade_date": "20221230"},
            {"exchange": "SSE", "cal_date": "20230101", "is_open": 0, "pretrade_date": "20221230"},
            {"exchange": "SSE", "cal_date": "20230102", "is_open": 0, "pretrade_date": "20221230"},
        ]

    def fetch_index_basic(self, *, asof_date: str) -> Sequence[Mapping[str, Any]]:
        return [
            {"ts_code": "000001.SH", "name": "上证指数", "market": "SSE", "category": "综合指数", "list_date": "19910715"},
            {"ts_code": "399001.SZ", "name": "深证成指", "market": "SZSE", "category": "规模指数", "list_date": "19910404"},
            {"ts_code": "801001.SI", "name": "申万市场表征", "market": "SW", "category": "申万指数"},
        ]


class BadIndexSource(FakeCommonIndexSource):
    def fetch_index_basic(self, *, asof_date: str) -> Sequence[Mapping[str, Any]]:
        return [{"ts_code": "881001.SI", "name": "板块误入指数"}]


class CommonIndexIngestionTest(unittest.TestCase):
    def test_common_index_dry_run_passes(self) -> None:
        result = run_common_index_ingestion_dry_run(
            FakeCommonIndexSource(),
            start_date="20230101",
            end_date="20230103",
            version="v1",
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.batches["common_trade_calendar"], "trade_calendar_20230101_20230103_v1")
        self.assertEqual(result.batches["index_identity"], "index_identity_20230103_v1")
        self.assertEqual(len(result.trade_calendar_rows), 3)
        self.assertEqual(len(result.index_identity_rows), 3)
        self.assertEqual(result.index_identity_rows[0]["index_identity_key"], "index:SH:000001")
        self.assertEqual(result.index_identity_rows[1]["index_identity_key"], "index:SZ:399001")
        self.assertEqual(result.index_identity_rows[2]["index_identity_key"], "index:SW:801001")
        self.assertFalse(result.summary()["will_connect_database"])

    def test_trade_calendar_normalization_computes_next_open_date(self) -> None:
        rows = normalize_trade_calendar_rows(
            [
                {"exchange": "SSE", "cal_date": "20230102", "is_open": 0, "pretrade_date": "20221230"},
                {"exchange": "SSE", "cal_date": "20230103", "is_open": 1, "pretrade_date": "20221230"},
            ],
            source="tushare.trade_cal",
            source_batch_id="trade_calendar_20230102_20230103_v1",
            source_version="trade_calendar_20230102_20230103_v1",
        )

        self.assertEqual(rows[0]["next_trade_date"], "20230103")
        self.assertIsNone(rows[1]["next_trade_date"])

    def test_index_identity_stays_in_index_namespace_for_same_code_as_stock(self) -> None:
        row = normalize_index_identity_row(
            {"ts_code": "000001.SH", "name": "上证指数"},
            source="tushare.index_basic",
            source_batch_id="index_identity_20260521_v1",
            source_version="index_identity_20260521_v1",
        )

        self.assertEqual(row["index_identity_key"], "index:SH:000001")
        self.assertNotIn("stock_identity_key", row)

    def test_88xxxx_index_identity_fails_quality_gate(self) -> None:
        result = run_common_index_ingestion_dry_run(
            BadIndexSource(),
            start_date="20230101",
            end_date="20230103",
            version="v1",
        )

        self.assertFalse(result.passed)
        failed_gate_names = {gate.gate_name for gate in result.quality_gates if not gate.passed}
        self.assertIn("index_identity_88xxxx_board_violation", failed_gate_names)


if __name__ == "__main__":
    unittest.main()
