import unittest

from ashare_v3.condition import scope_policy_repair as repair


class ConditionScopePolicyRepairTest(unittest.TestCase):
    def test_repair_plan_forces_minute_flags_and_preserves_active_source_run(self) -> None:
        source_run = sample_source_run()
        rows_by_domain = {
            "stock": [sample_scope_row("stock", index=i) for i in range(1837)],
            "board": [sample_scope_row("board", index=i) for i in range(127)],
            "index": [sample_scope_row("index", index=i) for i in range(9)],
        }

        plan = repair.build_scope_policy_repair_plan(
            source_run=source_run,
            source_run_id="condition_layer_20260622_source_20260622_for_20260623_v1",
            repair_run_id="condition_layer_20260622_source_20260622_for_20260623_v1_scope_policy_repair_43b9a24",
            source_scope_rows_by_domain=rows_by_domain,
        )

        self.assertEqual(plan["result"], "PREFLIGHT_PASS")
        self.assertEqual(plan["old_active_run_status"], "passed_active")
        self.assertTrue(plan["active_run_preserved"])
        self.assertEqual(plan["write_tables"], list(repair.ALLOWED_WRITE_TABLES))
        self.assertEqual(plan["forbidden_write_tables"], list(repair.FORBIDDEN_WRITE_TABLES))
        self.assertEqual(plan["object_counts"], {"stock": 1837, "index": 9, "board": 127})
        self.assertEqual(plan["row_counts"]["stock_minute_target_scope"], 1837)
        self.assertEqual(plan["row_counts"]["index_minute_target_scope"], 9)
        self.assertEqual(plan["row_counts"]["board_minute_target_scope"], 127)

        for domain, rows in plan["repair_scope_rows_by_domain"].items():
            self.assertTrue(rows, domain)
            for row in rows:
                self.assertTrue(row["daily_snapshot_required"])
                self.assertTrue(row["minute_required"])
                self.assertTrue(row["previous_day_minute_required"])
                self.assertEqual(row["previous_day_minute_date"], "20260622")
                self.assertTrue(row["previous_day_minute_quality_required"])
                self.assertEqual(row["market_data_consumer"], "both")
                self.assertEqual(row["raw_json"]["scope_policy"], repair.RUNTIME_MONITOR_SCOPE_POLICY)
                self.assertEqual(row["raw_json"]["repair_commit"], repair.POLICY_COMMIT)
                self.assertEqual(row["raw_json"]["repaired_from_run_id"], source_run["run_id"])
                self.assertIn("original_required_flags", row["raw_json"])

    def test_repair_plan_blocks_when_source_run_is_not_passed(self) -> None:
        source_run = sample_source_run(status="failed")

        plan = repair.build_scope_policy_repair_plan(
            source_run=source_run,
            source_run_id=source_run["run_id"],
            repair_run_id=f"{source_run['run_id']}_scope_policy_repair_43b9a24",
            source_scope_rows_by_domain={"stock": [], "index": [], "board": []},
        )

        self.assertEqual(plan["result"], "BLOCKED")
        self.assertIn("source_run_not_passed", plan["blocked_reasons"])

    def test_repair_row_preserves_pool_identity_condition_and_trace(self) -> None:
        source_row = sample_scope_row("stock", index=7)

        repaired = repair.repair_scope_row(
            domain="stock",
            row=source_row,
            source_run_id="source_run",
            repair_run_id="repair_run",
        )

        self.assertEqual(repaired["run_id"], "repair_run")
        self.assertEqual(repaired["source_condition_pool_id"], source_row["source_condition_pool_id"])
        self.assertEqual(repaired["stock_identity_key"], source_row["stock_identity_key"])
        self.assertEqual(repaired["condition_key"], source_row["condition_key"])
        self.assertEqual(repaired["raw_json"]["existing_trace"], "kept")
        self.assertEqual(repaired["raw_json"]["repaired_from_scope_id"], source_row["scope_id"])
        self.assertEqual(
            repaired["raw_json"]["original_required_flags"],
            {
                "daily_snapshot_required": True,
                "minute_required": False,
                "previous_day_minute_required": False,
                "previous_day_minute_quality_required": False,
                "market_data_consumer": "trigger_daily_snapshot",
            },
        )

    def test_repair_row_lineage_uses_real_minute_target_scope_id_without_alias(self) -> None:
        source_row = sample_scope_row("stock", index=7)
        source_row.pop("scope_id")
        source_row["stock_minute_target_scope_id"] = 7007

        repaired = repair.repair_scope_row(
            domain="stock",
            row=source_row,
            source_run_id="source_run",
            repair_run_id="repair_run",
        )

        self.assertEqual(repaired["raw_json"]["repaired_from_scope_id"], 7007)

    def test_fetch_scope_rows_uses_actual_minute_target_scope_id_columns(self) -> None:
        expected_id_columns = {
            "stock": "stock_minute_target_scope_id",
            "index": "index_minute_target_scope_id",
            "board": "board_minute_target_scope_id",
        }

        for domain, id_column in expected_id_columns.items():
            with self.subTest(domain=domain):
                cursor = CapturingCursor()

                repair.fetch_scope_rows(cursor, domain, "source_run")

                self.assertIn(f"SELECT {id_column} AS scope_id", cursor.sql)
                self.assertIn(f"ORDER BY {id_column}", cursor.sql)
                self.assertNotIn(f"{domain}_scope_id", cursor.sql)

    def test_rollback_sql_hard_fails_on_downstream_refs_and_deletes_only_scope_repair_rows(self) -> None:
        sql = repair.build_rollback_sql("repair_run")

        self.assertIn("RAISE EXCEPTION", sql)
        for downstream in repair.DOWNSTREAM_REF_TABLES:
            self.assertIn(downstream, sql)
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DELETE FROM stock_minute_target_scope"))
        for table in repair.ALLOWED_ROLLBACK_DELETE_TABLES:
            self.assertIn(f"DELETE FROM {table}", sql)
        for table in repair.FORBIDDEN_WRITE_TABLES:
            self.assertNotIn(f"DELETE FROM {table}", sql)
            self.assertNotIn(f"INSERT INTO {table}", sql)
            self.assertNotIn(f"UPDATE {table}", sql)
        self.assertNotIn("DELETE FROM condition_pool", sql)
        self.assertNotIn("UPDATE common_condition_run SET status", sql)

    def test_execute_without_user_confirmation_is_blocked_before_write(self) -> None:
        result = repair.run_scope_policy_repair(
            dsn="postgresql://unused",
            source_run_id="source",
            repair_run_id="repair",
            execute=True,
            user_confirmed=False,
            connector=lambda _dsn: self.fail("connector must not be called before user confirmation"),
        )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("missing_user_confirmation", result["blocked_reasons"])
        self.assertFalse(result["database_written"])


def sample_source_run(status: str = "passed_active") -> dict[str, object]:
    return {
        "run_id": "condition_layer_20260622_source_20260622_for_20260623_v1",
        "for_trade_date": "20260623",
        "source_trade_date": "20260622",
        "prev_trade_date": "20260622",
        "source_version": "condition_source_bundle_20260622",
        "source_versions": {"stock_daily": "stock_daily_20260622_v1"},
        "source_ready_check": {"passed": True},
        "status": status,
        "raw_json": {"old": "preserved"},
    }


def sample_scope_row(domain: str, *, index: int) -> dict[str, object]:
    row = {
        "scope_id": index + 1,
        "run_id": "condition_layer_20260622_source_20260622_for_20260623_v1",
        "for_trade_date": "20260623",
        "source_trade_date": "20260622",
        "prev_trade_date": "20260622",
        "lane": f"{domain}_alert",
        "direction": "buy" if index % 2 == 0 else "sell",
        "condition_key": "BUY:M" if index % 2 == 0 else "SELL:M",
        "condition_periods": ["M"],
        "allowed_signal_types": ["BUY"] if index % 2 == 0 else ["SELL"],
        "is_hint_scope": False,
        "scope_source": "condition_pool",
        "source_condition_pool_id": index + 1000,
        "reason": "selected",
        "period_trigger_baseline_json": {"baseline_version": "v1"},
        "daily_snapshot_required": True,
        "minute_required": False,
        "previous_day_minute_required": False,
        "previous_day_minute_date": "20260622",
        "previous_day_minute_quality_required": False,
        "minute_scope_reason": "legacy_daily_only",
        "market_data_consumer": "trigger_daily_snapshot",
        "source_version": "condition_source_bundle_20260622",
        "scope_status": "passed",
        "raw_json": {"existing_trace": "kept"},
    }
    if domain == "stock":
        row.update(
            {
                "stock_identity_key": f"stock:SH:{600000 + index}",
                "code": str(600000 + index),
                "exchange": "SH",
                "name": f"Stock {index}",
                "total_mv": "1000000",
                "market_value_threshold": "1000000",
            }
        )
    elif domain == "index":
        row.update(
            {
                "index_identity_key": f"index:SH:{index:06d}",
                "code": f"{index:06d}",
                "exchange": "SH",
                "name": f"Index {index}",
            }
        )
    elif domain == "board":
        row.update(
            {
                "board_identity_key": f"board:TDX:{881000 + index}",
                "board_code": str(881000 + index),
                "board_name": f"Board {index}",
                "board_type": "tdx_industry",
            }
        )
    else:
        raise AssertionError(domain)
    return row


class CapturingCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params = None

    def execute(self, sql: str, params: object = None) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict[str, object]]:
        return []


if __name__ == "__main__":
    unittest.main()
