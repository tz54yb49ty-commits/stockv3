import unittest

from ashare_v3.ingestion.common import IngestionValidationError
from ashare_v3.ingestion.postgres_write_plan import build_postgres_write_plan


class PostgresWritePlanTest(unittest.TestCase):
    def test_stock_daily_write_plan_generates_upsert_and_rollback_sql(self) -> None:
        plan = build_postgres_write_plan(
            table_name="stock_daily_bar_fact",
            rows=[
                {
                    "stock_identity_key": "stock:SZ:000001",
                    "trade_date": "20260521",
                    "ts_code": "000001.SZ",
                    "code": "000001",
                    "exchange": "SZ",
                    "open": "1",
                    "high": "2",
                    "low": "1",
                    "close": "2",
                    "source": "tushare.pro_bar",
                    "source_batch_id": "stock_daily_20260521_v1",
                    "source_version": "stock_daily_20260521_v1",
                }
            ],
        )

        self.assertTrue(plan.passed)
        self.assertEqual(plan.operation, "insert_on_conflict_update")
        self.assertIn("INSERT INTO stock_daily_bar_fact", plan.insert_sql_template)
        self.assertIn("ON CONFLICT (stock_identity_key, trade_date, source_version)", plan.insert_sql_template)
        self.assertEqual(
            plan.rollback_sql_template,
            "DELETE FROM stock_daily_bar_fact WHERE source_batch_id = :source_batch_id;",
        )
        self.assertFalse(plan.to_dict()["will_execute_sql"])

    def test_common_ingest_batch_rolls_back_by_batch_id(self) -> None:
        plan = build_postgres_write_plan(
            table_name="common_ingest_batch",
            rows=[
                {
                    "batch_id": "stock_daily_20260521_v1",
                    "trade_date": "20260521",
                    "data_domain": "stock",
                    "data_type": "stock_daily",
                    "source": "tushare.pro_bar",
                    "source_version": "stock_daily_20260521_v1",
                    "status": "pending",
                    "started_at": "2026-05-21T00:00:00Z",
                }
            ],
        )

        self.assertTrue(plan.passed)
        self.assertEqual(plan.source_batch_id, "stock_daily_20260521_v1")
        self.assertEqual(plan.rollback_sql_template, "DELETE FROM common_ingest_batch WHERE batch_id = :source_batch_id;")

    def test_multiple_source_versions_fail_quality_gate(self) -> None:
        plan = build_postgres_write_plan(
            table_name="stock_daily_basic",
            rows=[
                base_stock_daily_basic("stock_daily_basic_20260521_v1"),
                base_stock_daily_basic("stock_daily_basic_20260522_v1"),
            ],
        )

        self.assertFalse(plan.passed)
        failed_gate_names = {gate.gate_name for gate in plan.quality_gates if not gate.passed}
        self.assertIn("postgres_source_version_single", failed_gate_names)

    def test_unknown_column_fails_allowlist_gate(self) -> None:
        row = base_stock_daily_basic("stock_daily_basic_20260521_v1")
        row["asset_kind"] = "stock"
        plan = build_postgres_write_plan(table_name="stock_daily_basic", rows=[row])

        self.assertFalse(plan.passed)
        failed_gate_names = {gate.gate_name for gate in plan.quality_gates if not gate.passed}
        self.assertIn("postgres_allowed_columns", failed_gate_names)

    def test_stock_table_rejects_board_code_shape(self) -> None:
        row = base_stock_daily_basic("stock_daily_basic_20260521_v1")
        row["code"] = "881002"
        plan = build_postgres_write_plan(table_name="stock_daily_basic", rows=[row])

        self.assertFalse(plan.passed)
        failed_gate_names = {gate.gate_name for gate in plan.quality_gates if not gate.passed}
        self.assertIn("postgres_physical_code_shape", failed_gate_names)

    def test_board_daily_requires_88_board_code(self) -> None:
        plan = build_postgres_write_plan(
            table_name="board_daily_bar_fact",
            rows=[
                {
                    "board_identity_key": "board:TDX:123456",
                    "trade_date": "20260521",
                    "board_code": "123456",
                    "board_type": "tdx_other",
                    "open": "1",
                    "high": "2",
                    "low": "1",
                    "close": "2",
                    "source": "mootdx.index",
                    "source_batch_id": "board_daily_20260521_v1",
                    "source_version": "board_daily_20260521_v1",
                }
            ],
        )

        self.assertFalse(plan.passed)
        failed_gate_names = {gate.gate_name for gate in plan.quality_gates if not gate.passed}
        self.assertIn("postgres_physical_code_shape", failed_gate_names)

    def test_unsupported_table_is_rejected(self) -> None:
        with self.assertRaises(IngestionValidationError):
            build_postgres_write_plan(table_name="daily_bar_fact", rows=[])


def base_stock_daily_basic(source_version: str) -> dict[str, str]:
    return {
        "stock_identity_key": "stock:SZ:000001",
        "trade_date": "20260521",
        "ts_code": "000001.SZ",
        "code": "000001",
        "exchange": "SZ",
        "source": "tushare.daily_basic",
        "source_batch_id": source_version,
        "source_version": source_version,
    }


if __name__ == "__main__":
    unittest.main()
