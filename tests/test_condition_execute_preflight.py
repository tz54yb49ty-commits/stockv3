import unittest

from ashare_v3.condition.active_status import (
    CANONICAL_ACTIVE_STATUS,
    LEGACY_ACTIVE_STATUS,
    summarize_active_runs,
    status_check_supports_passed_active,
)
from ashare_v3.condition.execute_contract import build_condition_execute_contract
from ashare_v3.condition.execute_preflight import (
    CANONICAL_TARGET_SCHEMA_COLUMNS,
    CANONICAL_TARGET_SCHEMA_TABLES,
    FORBIDDEN_TARGET_SCHEMA_COLUMNS,
    REQUIRED_SCHEMA_TABLES,
    build_condition_execute_preflight,
)


class ConditionExecutePreflightTest(unittest.TestCase):
    def test_required_schema_tables_include_monitor_targets_and_split_tables(self) -> None:
        self.assertIn("stock_monitor_target", REQUIRED_SCHEMA_TABLES)
        self.assertIn("index_monitor_target", REQUIRED_SCHEMA_TABLES)
        self.assertIn("board_monitor_target", REQUIRED_SCHEMA_TABLES)
        self.assertIn("stock_condition_basis", REQUIRED_SCHEMA_TABLES)
        self.assertIn("index_condition_pool", REQUIRED_SCHEMA_TABLES)
        self.assertIn("board_minute_target_scope", REQUIRED_SCHEMA_TABLES)

    def test_canonical_target_schema_readiness_covers_twelve_n2_tables_without_locked_fields(self) -> None:
        self.assertEqual(len(CANONICAL_TARGET_SCHEMA_TABLES), 12)
        self.assertIn("stock_condition_display_basis", CANONICAL_TARGET_SCHEMA_TABLES)
        self.assertIn("reference_target_price", CANONICAL_TARGET_SCHEMA_COLUMNS)
        self.assertIn("target_price_trace_json", CANONICAL_TARGET_SCHEMA_COLUMNS)
        self.assertIn("up_secondary_target_price", CANONICAL_TARGET_SCHEMA_COLUMNS)
        self.assertIn("down_secondary_target_price", CANONICAL_TARGET_SCHEMA_COLUMNS)
        self.assertEqual(FORBIDDEN_TARGET_SCHEMA_COLUMNS, ("locked_target_price", "target_lock_status"))

    def test_preflight_blocks_when_schema_is_not_migrated(self) -> None:
        readiness = sample_readiness_plan()
        contract = build_condition_execute_contract(readiness, user_confirmed=True)

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=schema_status(missing=["stock_condition_basis"]),
            active_run_status=active_run_status(active_exists=False),
        )

        self.assertFalse(preflight["execute_allowed"])
        self.assertIn("schema_not_migrated", preflight["blocked_reasons"])
        self.assertEqual(preflight["schema_status"]["missing_tables"], ["stock_condition_basis"])
        self.assertFalse(preflight["will_execute_sql"])

    def test_active_selection_prefers_passed_active_over_legacy_passed(self) -> None:
        active = summarize_active_runs(
            [
                {"run_id": "condition_layer_legacy", "status": LEGACY_ACTIVE_STATUS},
                {"run_id": "condition_layer_canonical", "status": CANONICAL_ACTIVE_STATUS},
            ],
            overwrite=True,
        )

        self.assertTrue(active["active_exists"])
        self.assertEqual(active["active_runs"][0]["run_id"], "condition_layer_canonical")
        self.assertEqual(active["canonical_active_run_count"], 1)
        self.assertEqual(active["legacy_active_run_count"], 1)
        self.assertFalse(active["blocked_by_multiple_passed_active"])

    def test_active_selection_keeps_legacy_passed_readable(self) -> None:
        active = summarize_active_runs(
            [{"run_id": "condition_layer_legacy", "status": LEGACY_ACTIVE_STATUS}],
            overwrite=False,
        )

        self.assertTrue(active["active_exists"])
        self.assertEqual(active["active_runs"][0]["run_id"], "condition_layer_legacy")
        self.assertEqual(active["canonical_active_run_count"], 0)
        self.assertEqual(active["legacy_active_run_count"], 1)
        self.assertTrue(active["blocked_by_active_run"])

    def test_preflight_blocks_two_passed_active_for_same_date_pair(self) -> None:
        readiness = sample_readiness_plan()
        contract = build_condition_execute_contract(readiness, user_confirmed=True, overwrite=True)

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=schema_status(),
            active_run_status=summarize_active_runs(
                [
                    {"run_id": "condition_layer_active_a", "status": CANONICAL_ACTIVE_STATUS},
                    {"run_id": "condition_layer_active_b", "status": CANONICAL_ACTIVE_STATUS},
                ],
                overwrite=True,
            ),
        )

        self.assertFalse(preflight["execute_allowed"])
        self.assertIn("multiple_passed_active_runs", preflight["blocked_reasons"])

    def test_preflight_blocks_default_active_run_conflict(self) -> None:
        readiness = sample_readiness_plan()
        contract = build_condition_execute_contract(readiness, user_confirmed=True)

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=schema_status(),
            active_run_status=active_run_status(active_exists=True, overwrite=False),
        )

        self.assertFalse(preflight["execute_allowed"])
        self.assertIn("active_run_exists", preflight["blocked_reasons"])

    def test_preflight_blocks_when_user_confirmation_is_required(self) -> None:
        readiness = sample_readiness_plan()
        contract = build_condition_execute_contract(readiness, user_confirmed=False)

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=schema_status(),
            active_run_status=active_run_status(active_exists=False),
        )

        self.assertFalse(preflight["execute_allowed"])
        self.assertIn("user_confirmation_required", preflight["blocked_reasons"])

    def test_preflight_allows_request_when_confirmed_schema_ready_and_no_active_conflict(self) -> None:
        readiness = sample_readiness_plan()
        contract = build_condition_execute_contract(readiness, user_confirmed=True)

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=schema_status(),
            active_run_status=active_run_status(active_exists=False),
            run_id_status=run_id_status("condition_layer_x"),
        )

        self.assertTrue(preflight["execute_allowed"])
        self.assertEqual(preflight["blocked_reasons"], [])
        self.assertEqual(preflight["rollback_sql_preview"][0], "DELETE FROM stock_minute_target_scope WHERE run_id = :execute_run_id;")
        self.assertTrue(preflight["source_version_status"]["complete"])
        self.assertEqual(preflight["run_id_status"]["requested_run_id"], "condition_layer_x")

    def test_preflight_blocks_when_requested_run_id_already_exists(self) -> None:
        readiness = sample_readiness_plan()
        contract = build_condition_execute_contract(readiness, user_confirmed=True)

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=schema_status(),
            active_run_status=active_run_status(active_exists=False),
            run_id_status=run_id_status("condition_layer_x", conflicts={"common_condition_run": 1}),
        )

        self.assertFalse(preflight["execute_allowed"])
        self.assertIn("run_id_already_exists", preflight["blocked_reasons"])
        self.assertEqual(preflight["run_id_status"]["total_existing_rows"], 1)

    def test_preflight_blocks_when_passed_active_status_migration_missing(self) -> None:
        readiness = sample_readiness_plan()
        contract = build_condition_execute_contract(readiness, user_confirmed=True, overwrite=True)

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=schema_status(passed_active_supported=False),
            active_run_status=active_run_status(active_exists=True, overwrite=True),
            run_id_status=run_id_status("condition_layer_x"),
        )

        self.assertFalse(preflight["execute_allowed"])
        self.assertIn("passed_active_status_not_migrated", preflight["blocked_reasons"])
        self.assertFalse(preflight["schema_status"]["passed_active_status_supported"])

    def test_preflight_blocks_when_canonical_target_schema_is_missing(self) -> None:
        readiness = sample_readiness_plan()
        contract = build_condition_execute_contract(readiness, user_confirmed=True)

        status = schema_status()
        status["schema_ready"] = False
        status["canonical_target_fields_ready"] = False
        status["canonical_target_missing_columns"] = {"stock_condition_basis": ["reference_target_price"]}

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=status,
            active_run_status=active_run_status(active_exists=False),
            run_id_status=run_id_status("condition_layer_x"),
        )

        self.assertFalse(preflight["execute_allowed"])
        self.assertIn("canonical_target_schema_not_ready", preflight["blocked_reasons"])

    def test_status_check_support_detection_requires_passed_active(self) -> None:
        self.assertTrue(status_check_supports_passed_active("CHECK (status IN ('passed', 'passed_active'))"))
        self.assertFalse(status_check_supports_passed_active("CHECK (status IN ('passed', 'failed'))"))

    def test_preflight_blocks_incomplete_source_versions(self) -> None:
        readiness = sample_readiness_plan()
        readiness["source_versions"] = {"stock_daily": "stock_daily_20260522_v1"}
        contract = build_condition_execute_contract(readiness, user_confirmed=True)

        preflight = build_condition_execute_preflight(
            readiness_plan=readiness,
            execute_contract=contract,
            schema_status=schema_status(),
            active_run_status=active_run_status(active_exists=False),
        )

        self.assertFalse(preflight["execute_allowed"])
        self.assertIn("source_versions_incomplete", preflight["blocked_reasons"])
        self.assertIn("board_membership", preflight["source_version_status"]["missing_keys"])


def schema_status(missing: list[str] | None = None, *, passed_active_supported: bool = True) -> dict[str, object]:
    missing = missing or []
    return {
        "schema_ready": not missing,
        "required_tables": list(REQUIRED_SCHEMA_TABLES),
        "table_status": {
            table: {"exists": table not in missing}
            for table in REQUIRED_SCHEMA_TABLES
        },
        "missing_tables": missing,
        "migration_required": bool(missing),
        "migration_performed": False,
        "passed_active_status_supported": passed_active_supported,
        "status_migration_required": not passed_active_supported,
        "read_only": True,
    }


def active_run_status(*, active_exists: bool, overwrite: bool = False) -> dict[str, object]:
    return {
        "table_exists": True,
        "active_exists": active_exists,
        "active_runs": [{"run_id": "condition_layer_old"}] if active_exists else [],
        "active_run_count": 1 if active_exists else 0,
        "default_policy": "reject_if_active_exists",
        "overwrite": overwrite,
        "blocked_by_active_run": active_exists and not overwrite,
        "read_only": True,
    }


def run_id_status(requested_run_id: str, conflicts: dict[str, int] | None = None) -> dict[str, object]:
    conflicts = conflicts or {}
    table_counts = {
        "common_condition_run": 0,
        "common_condition_quality_item": 0,
        "stock_condition_basis": 0,
        "index_condition_basis": 0,
        "board_condition_basis": 0,
        "stock_condition_pool": 0,
        "index_condition_pool": 0,
        "board_condition_pool": 0,
        "stock_minute_target_scope": 0,
        "index_minute_target_scope": 0,
        "board_minute_target_scope": 0,
        "stock_condition_display_basis": 0,
        "index_condition_display_basis": 0,
        "board_condition_display_basis": 0,
        "stock_monitor_target": 0,
        "index_monitor_target": 0,
        "board_monitor_target": 0,
        **conflicts,
    }
    total = sum(table_counts.values())
    return {
        "requested_run_id": requested_run_id,
        "table_counts": table_counts,
        "total_existing_rows": total,
        "run_id_available": total == 0,
        "read_only": True,
    }


def sample_readiness_plan() -> dict[str, object]:
    return {
        "planned_run_id": "condition_layer_20260522_to_20260525_execute",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "source_versions": {
            "stock_daily": "stock_daily_20260522_v1",
            "stock_daily_basic": "stock_daily_basic_20260522_v1",
            "stock_financial": "stock_financial_20260522_v1",
            "index_daily": "index_daily_20260522_v1",
            "index_membership": "index_membership_20260522_v1",
            "board_daily": "board_daily_20260522_v1",
            "board_membership": "board_membership_20260522_v1",
        },
        "policy_name": "default_scope_policy",
        "policy_hash": "abc123",
        "stage_counts": {
            "condition_basis": {"stock": 5504, "index": 80, "board": 428},
            "condition_pool": {"stock": 20246, "index": 273, "board": 1575},
            "minute_target_scope": {"stock": 7438, "index": 18, "board": 254},
        },
        "quality_summary": {
            "p0_count": 0,
            "p1_count": 9,
            "p2_count": 3,
            "quality_item_count": 61,
        },
        "would_write": {
            "common_condition_run": {"row_count": 1},
            "common_condition_quality_item": {"row_count": 61},
            "stock_condition_basis": {"row_count": 5504},
            "index_condition_basis": {"row_count": 80},
            "board_condition_basis": {"row_count": 428},
            "stock_condition_pool": {"row_count": 20246},
            "index_condition_pool": {"row_count": 273},
            "board_condition_pool": {"row_count": 1575},
            "index_minute_target_scope": {"row_count": 18},
            "board_minute_target_scope": {"row_count": 254},
            "stock_minute_target_scope": {"row_count": 7438},
        },
        "rollback_plan": {
            "strategy": "delete_by_run_id",
            "run_id": "condition_layer_20260522_to_20260525_execute",
        },
        "execute_preconditions_passed": True,
    }


if __name__ == "__main__":
    unittest.main()
