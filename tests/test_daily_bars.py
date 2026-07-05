import unittest
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.daily_bars import (
    BoardDailySymbol,
    IndexDailySymbol,
    normalize_board_daily_bar_row,
    normalize_index_daily_bar_row,
    run_daily_bar_ingestion_dry_run,
)


class FakeDailyBarSource:
    def fetch_index_daily_bars(
        self,
        *,
        indexes: Sequence[IndexDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "code": indexes[0].code,
                "exchange": indexes[0].exchange,
                "name": indexes[0].name,
                "trade_date": end_date,
                "open": "3000",
                "high": "3010",
                "low": "2990",
                "close": "3005",
                "vol": "100000",
                "amount": "200000",
            }
        ]

    def fetch_board_daily_bars(
        self,
        *,
        boards: Sequence[BoardDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "board_code": boards[0].board_code,
                "board_name": boards[0].board_name,
                "board_type": boards[0].board_type,
                "trade_date": end_date,
                "open": "1000",
                "high": "1010",
                "low": "990",
                "close": "1005",
                "vol": "50000",
                "amount": "80000",
            }
        ]


class MissingDailyBarSource(FakeDailyBarSource):
    def fetch_index_daily_bars(
        self,
        *,
        indexes: Sequence[IndexDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        return []


class BadIndexDailyBarSource(FakeDailyBarSource):
    def fetch_index_daily_bars(
        self,
        *,
        indexes: Sequence[IndexDailySymbol],
        start_date: str,
        end_date: str,
    ) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "code": "881001",
                "exchange": "TDX",
                "trade_date": end_date,
                "open": "1",
                "high": "1",
                "low": "1",
                "close": "1",
            }
        ]


class DailyBarsTest(unittest.TestCase):
    def test_daily_bar_dry_run_passes(self) -> None:
        result = run_daily_bar_ingestion_dry_run(
            FakeDailyBarSource(),
            indexes=[IndexDailySymbol(code="000001", exchange="SH", name="上证指数")],
            boards=[BoardDailySymbol(board_code="881002", board_name="煤炭开采", board_type="tdx_industry")],
            start_date="20260521",
            end_date="20260521",
            version="v1",
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.batches["index_daily_bar_fact"], "index_daily_20260521_20260521_v1")
        self.assertEqual(result.index_daily_bar_rows[0]["index_identity_key"], "index:SH:000001")
        self.assertEqual(result.board_daily_bar_rows[0]["board_identity_key"], "board:TDX:881002")
        self.assertFalse(result.summary()["will_connect_database"])

    def test_index_daily_missing_gate_fails(self) -> None:
        result = run_daily_bar_ingestion_dry_run(
            MissingDailyBarSource(),
            indexes=[IndexDailySymbol(code="000001", exchange="SH", name="上证指数")],
            boards=[BoardDailySymbol(board_code="881002", board_name="煤炭开采", board_type="tdx_industry")],
            start_date="20260521",
            end_date="20260521",
            version="v1",
        )

        self.assertFalse(result.passed)
        failed_gate_names = {gate.gate_name for gate in result.quality_gates if not gate.passed}
        self.assertIn("index_official_daily_missing", failed_gate_names)

    def test_88xxxx_index_daily_violation_fails(self) -> None:
        result = run_daily_bar_ingestion_dry_run(
            BadIndexDailyBarSource(),
            indexes=[IndexDailySymbol(code="000001", exchange="SH", name="上证指数")],
            boards=[BoardDailySymbol(board_code="881002", board_name="煤炭开采", board_type="tdx_industry")],
            start_date="20260521",
            end_date="20260521",
            version="v1",
        )

        self.assertFalse(result.passed)
        failed_gate_names = {gate.gate_name for gate in result.quality_gates if not gate.passed}
        self.assertIn("index_daily_88xxxx_board_violation", failed_gate_names)

    def test_normalizers_keep_physical_table_keys_separate(self) -> None:
        index_row = normalize_index_daily_bar_row(
            {
                "code": "399001",
                "exchange": "SZ",
                "trade_date": "20260521",
                "open": "1",
                "high": "2",
                "low": "1",
                "close": "2",
            },
            source="mootdx.index",
            source_batch_id="index_daily_20260521_20260521_v1",
            source_version="index_daily_20260521_20260521_v1",
        )
        board_row = normalize_board_daily_bar_row(
            {
                "board_code": "881002",
                "board_name": "煤炭开采",
                "board_type": "tdx_industry",
                "datetime": "2026-05-21 00:00:00",
                "open": "1",
                "high": "2",
                "low": "1",
                "close": "2",
            },
            source="mootdx.index",
            source_batch_id="board_daily_20260521_20260521_v1",
            source_version="board_daily_20260521_20260521_v1",
        )

        self.assertEqual(index_row["index_identity_key"], "index:SZ:399001")
        self.assertEqual(board_row["board_identity_key"], "board:TDX:881002")
        self.assertNotIn("board_identity_key", index_row)
        self.assertNotIn("index_identity_key", board_row)


if __name__ == "__main__":
    unittest.main()
