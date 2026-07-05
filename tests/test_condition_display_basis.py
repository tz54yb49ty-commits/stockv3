import unittest
from pathlib import Path

from ashare_v3.condition.display_basis import (
    DOMAIN_CONFIGS,
    build_display_quality,
    build_display_rows_for_domain,
    validate_display_rows,
)


MIGRATION_PATH = Path("sql/N2_N6_buy_expected_return_display_basis_migration.sql")
ROLLBACK_PATH = Path("sql/N2_N6_buy_expected_return_display_basis_rollback.sql")


class ConditionDisplayBasisTests(unittest.TestCase):
    def test_stock_display_row_aggregates_pool_and_scope(self) -> None:
        config = DOMAIN_CONFIGS["stock"]
        basis_rows = [
            {
                "run_id": "run1",
                "for_trade_date": "20260525",
                "source_trade_date": "20260522",
                "prev_trade_date": "20260522",
                "stock_condition_basis_id": 1,
                "stock_identity_key": "stock:SH:600000",
                "code": "600000",
                "exchange": "SH",
                "name": "浦发银行",
                "source_version": "run1",
                "direction_scope": ["buy", "sell"],
                "period_trigger_baseline_json": {"baseline_version": "test", "periods": {}},
                "up_sell_reference_period": "D",
                "down_buy_reference_period": "D",
                "clear_sell_ref_period": "D",
                "symmetry_anchor": "W",
                "secondary_symmetry_anchor": None,
                "amplitude_source_period": "W",
                "a_segment_start_date": "20260501",
                "a_segment_end_date": "20260522",
                "a_segment_high": "12",
                "a_segment_low": "10",
                "a_segment_amplitude": "2",
                "base_price_policy": "MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN",
                "base_price": "10",
                "reference_target_price": "12",
                "secondary_target_price": None,
                "target_price_trace_json": {"primary_direction": "buy"},
            },
            {
                "run_id": "run1",
                "for_trade_date": "20260525",
                "source_trade_date": "20260522",
                "prev_trade_date": "20260522",
                "stock_condition_basis_id": 2,
                "stock_identity_key": "stock:SH:600001",
                "code": "600001",
                "exchange": "SH",
                "name": "未入池股票",
                "source_version": "run1",
                "direction_scope": ["buy", "sell"],
                "period_trigger_baseline_json": {"baseline_version": "test", "periods": {}},
                "up_sell_reference_period": "D",
                "down_buy_reference_period": "D",
                "clear_sell_ref_period": "D",
            }
        ]
        pool_rows = [
            {
                "stock_condition_pool_id": 10,
                "stock_identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY:D",
                "allowed_signal_types": ["BUY"],
                "lane": "stock_trade",
                "monitor_type": "stock_buy_monitor",
                "selected_reason": ["default_policy_selected"],
                "excluded_reason": [],
                "policy_name": "default_condition_pool_policy",
                "policy_hash": "abc",
            }
        ]
        scope_rows = [
            {
                "stock_minute_target_scope_id": 100,
                "stock_identity_key": "stock:SH:600000",
                "condition_key": "BUY:D",
                "source_condition_pool_id": 10,
            }
        ]
        rows = build_display_rows_for_domain(config, basis_rows=basis_rows, pool_rows=pool_rows, scope_rows=scope_rows)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["stock_identity_key"], "stock:SH:600000")
        self.assertEqual(row["selected_condition_keys"], ["BUY:D"])
        self.assertEqual(row["selected_signal_types"], ["BUY"])
        self.assertEqual(row["source_condition_basis_ids_json"], [1])
        self.assertEqual(row["source_condition_pool_ids_json"], [10])
        self.assertEqual(row["source_minute_target_scope_ids_json"], [100])
        self.assertEqual(row["clear_sell_ref_period"], row["up_sell_reference_period"])
        self.assertEqual(row["reference_target_price"], "12")
        self.assertEqual(row["symmetry_anchor"], "W")
        self.assertEqual(row["target_price_trace_json"]["primary_direction"], "buy")
        self.assertNotIn("locked_target_price", row)
        self.assertNotIn("target_lock_status", row)

    def test_buy_expected_return_pct_passes_through_for_all_domains(self) -> None:
        for domain in ("stock", "index", "board"):
            with self.subTest(domain=domain):
                config = DOMAIN_CONFIGS[domain]
                basis_id_col = config.basis_id_col
                pool_id_col = config.pool_id_col
                scope_id_col = config.scope_id_col
                basis_row = {
                    "run_id": "run1",
                    "for_trade_date": "20260525",
                    "source_trade_date": "20260522",
                    "prev_trade_date": "20260522",
                    basis_id_col: 1,
                    config.identity_col: f"{domain}:demo",
                    config.code_col: "000001",
                    config.name_col: "demo",
                    "source_version": "run1",
                    "direction_scope": ["buy"],
                    "buy_expected_return_pct": "8.23",
                    "period_trigger_baseline_json": {"baseline_version": "test", "periods": {}},
                    "up_sell_reference_period": "D",
                    "down_buy_reference_period": "D",
                    "clear_sell_ref_period": "D",
                }
                if config.exchange_col:
                    basis_row[config.exchange_col] = "SH"
                if config.board_type_col:
                    basis_row[config.board_type_col] = "tdx_industry"
                rows = build_display_rows_for_domain(
                    config,
                    basis_rows=[basis_row],
                    pool_rows=[
                        {
                            pool_id_col: 10,
                            config.identity_col: f"{domain}:demo",
                            "direction": "buy",
                            "condition_key": "BUY:D",
                            "allowed_signal_types": ["BUY"],
                        }
                    ],
                    scope_rows=[
                        {
                            scope_id_col: 100,
                            config.identity_col: f"{domain}:demo",
                            "condition_key": "BUY:D",
                            "source_condition_pool_id": 10,
                        }
                    ],
                )

                self.assertEqual(rows[0]["buy_expected_return_pct"], "8.23")

    def test_buy_expected_return_display_basis_sql_is_scoped_and_safe(self) -> None:
        migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
        rollback_sql = ROLLBACK_PATH.read_text(encoding="utf-8")
        executable_migration = strip_sql_comments(migration_sql)
        executable_rollback = strip_sql_comments(rollback_sql)

        for table in (
            "stock_condition_display_basis",
            "index_condition_display_basis",
            "board_condition_display_basis",
        ):
            self.assertIn(f"ALTER TABLE {table}", migration_sql)
            self.assertIn("ADD COLUMN IF NOT EXISTS buy_expected_return_pct NUMERIC", migration_sql)
            self.assertIn(f"ALTER TABLE {table}", rollback_sql)
            self.assertIn("DROP COLUMN IF EXISTS buy_expected_return_pct", rollback_sql)
        for view in (
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
        ):
            self.assertIn(f"CREATE OR REPLACE VIEW {view}", migration_sql)
            self.assertIn(f"CREATE OR REPLACE VIEW {view}", rollback_sql)
        for basis_table in ("stock_condition_basis", "index_condition_basis", "board_condition_basis"):
            self.assertIn(basis_table, migration_sql)
        self.assertIn("UPDATE stock_condition_display_basis", migration_sql)
        self.assertIn("UPDATE index_condition_display_basis", migration_sql)
        self.assertIn("UPDATE board_condition_display_basis", migration_sql)
        self.assertNotRegex(executable_migration, r"\b(DELETE|TRUNCATE|DROP\s+TABLE|CREATE\s+TABLE)\b")
        self.assertNotRegex(executable_rollback, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP\s+TABLE|CREATE\s+TABLE)\b")
        self.assertNotIn("common_trigger_", executable_migration)
        self.assertNotIn("common_action_", executable_migration)
        self.assertNotIn("user_signal_", executable_migration)

    def test_display_signal_types_reject_deprecated_30m_action_signals(self) -> None:
        config = DOMAIN_CONFIGS["stock"]
        basis_rows = [
            {
                "run_id": "run1",
                "for_trade_date": "20260525",
                "source_trade_date": "20260522",
                "prev_trade_date": "20260522",
                "stock_condition_basis_id": 1,
                "stock_identity_key": "stock:SH:600000",
                "code": "600000",
                "exchange": "SH",
                "name": "浦发银行",
                "source_version": "run1",
                "direction_scope": ["buy"],
                "period_trigger_baseline_json": {"baseline_version": "test", "periods": {}},
                "up_sell_reference_period": "D",
                "down_buy_reference_period": "D",
                "clear_sell_ref_period": "D",
            }
        ]
        pool_rows = [
            {
                "stock_condition_pool_id": 10,
                "stock_identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY:D",
                "allowed_signal_types": ["B_BUY_30M_VOL"],
            }
        ]
        scope_rows = [
            {
                "stock_minute_target_scope_id": 100,
                "stock_identity_key": "stock:SH:600000",
                "condition_key": "BUY:D",
                "source_condition_pool_id": 10,
            }
        ]
        rows = build_display_rows_for_domain(config, basis_rows=basis_rows, pool_rows=pool_rows, scope_rows=scope_rows)
        checks = validate_display_rows(config, rows)

        self.assertEqual(checks["field_integrity"]["selected_signal_types_invalid"], 1)

    def test_basis_only_identity_is_not_displayed(self) -> None:
        config = DOMAIN_CONFIGS["index"]
        basis_rows = [
            {
                "run_id": "run1",
                "for_trade_date": "20260525",
                "source_trade_date": "20260522",
                "prev_trade_date": "20260522",
                "index_condition_basis_id": 1,
                "index_identity_key": "index:SH:000001",
                "code": "000001",
                "exchange": "SH",
                "name": "上证指数",
                "source_version": "run1",
                "direction_scope": ["buy"],
                "period_trigger_baseline_json": {"baseline_version": "test", "periods": {}},
                "up_sell_reference_period": "D",
                "down_buy_reference_period": "D",
                "clear_sell_ref_period": "D",
            }
        ]
        rows = build_display_rows_for_domain(config, basis_rows=basis_rows, pool_rows=[], scope_rows=[])
        checks = validate_display_rows(config, rows)

        self.assertEqual(rows, [])
        self.assertEqual(checks["traceability"]["source_minute_target_scope_ids_empty_count"], 0)
        self.assertTrue(checks["traceability"]["source_minute_target_scope_ids_empty_explained"])
        self.assertEqual(checks["field_integrity"]["source_condition_basis_ids_missing"], 0)

    def test_display_quality_allows_existing_rows_when_counts_do_not_change(self) -> None:
        quality = build_display_quality(
            domain_reports={
                "stock": {
                    "display_table": "stock_condition_display_basis",
                    "uniqueness": {"duplicate_count": 0},
                    "field_integrity": {
                        "source_condition_basis_ids_missing": 0,
                        "selected_condition_keys_invalid": 0,
                        "selected_signal_types_invalid": 0,
                        "period_trigger_baseline_invalid_shape": 0,
                        "clear_sell_ref_period_mismatch": 0,
                        "invalid_reference_period": 0,
                    },
                    "traceability": {"source_minute_target_scope_ids_empty_explained": True},
                    "forbidden_field_check": {"forbidden_field_count": 0},
                }
            },
            before_counts={"stock_condition_display_basis": 12},
            after_counts={"stock_condition_display_basis": 12},
        )

        failed_codes = {item["gate_code"] for item in quality["items"] if item["status"] == "failed"}
        self.assertNotIn("display_tables_unchanged", failed_codes)
        self.assertEqual(quality["p0_count"], 0)


def strip_sql_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


if __name__ == "__main__":
    unittest.main()
