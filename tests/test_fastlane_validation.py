from pathlib import Path
import tempfile
import unittest

from ashare_v3.runtime.fastlane_validation import (
    FastLaneValidationError,
    assert_downstream_refs_zero,
    assert_execute_command_confirmed,
    assert_expected_actual_rows_match,
    assert_forbidden_scope_false,
    assert_no_cross_layer_execute,
    assert_no_old_system_touch,
    assert_no_unexpected_event_delta,
    assert_postgres_commit_enabled_when_required,
    assert_p0_zero,
    assert_rollback_static_safe,
)


class FastLaneValidationTest(unittest.TestCase):
    def test_cross_layer_execute_blocks(self) -> None:
        with self.assertRaises(FastLaneValidationError):
            assert_no_cross_layer_execute(
                wrapper_layer_role="N1_ingestion",
                child_step_layer_role="N2_condition",
                child_command=["python3", "scripts/run_condition_once.py", "--execute", "--user-confirmed"],
                is_execute_step=True,
            )

    def test_missing_execute_confirmation_flags_block(self) -> None:
        with self.assertRaises(FastLaneValidationError):
            assert_execute_command_confirmed(
                ["python3", "scripts/run_official_daily_ingestion_once.py", "--execute"],
                is_execute_step=True,
            )

        self.assertTrue(
            assert_execute_command_confirmed(
                [
                    "python3",
                    "scripts/run_official_daily_ingestion_once.py",
                    "--execute",
                    "--user-confirmed",
                ],
                is_execute_step=True,
            )
        )

    def test_postgres_commit_flag_blocks_when_required(self) -> None:
        with self.assertRaises(FastLaneValidationError):
            assert_postgres_commit_enabled_when_required(
                ["python3", "scripts/run_n1_source_facts_once.py", "--execute", "--user-confirmed"],
                is_execute_step=True,
                requires_postgres_commit_enabled=True,
            )

        self.assertTrue(
            assert_postgres_commit_enabled_when_required(
                [
                    "python3",
                    "scripts/run_n1_source_facts_once.py",
                    "--execute",
                    "--user-confirmed",
                    "--postgres-commit-enabled",
                ],
                is_execute_step=True,
                requires_postgres_commit_enabled=True,
            )
        )

    def test_p0_rows_and_downstream_refs_block(self) -> None:
        with self.assertRaises(FastLaneValidationError):
            assert_p0_zero({"P0": 1, "P1": 0, "P2": 0})
        with self.assertRaises(FastLaneValidationError):
            assert_downstream_refs_zero({"N4": 0, "N5": 1, "N6": 0})

    def test_expected_actual_rows_and_event_delta_must_match(self) -> None:
        with self.assertRaises(FastLaneValidationError):
            assert_expected_actual_rows_match({"stock": 10}, {"stock": 9})
        with self.assertRaises(FastLaneValidationError):
            assert_no_unexpected_event_delta(
                {"outbox": 0, "inbox": 0, "checkpoint": 0},
                {"outbox": 1, "inbox": 0, "checkpoint": 0},
                {"outbox": 0, "inbox": 0, "checkpoint": 0},
            )

    def test_rollback_static_guard_must_precede_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            safe = Path(tmp) / "safe.sql"
            safe.write_text(
                "DO $$ BEGIN RAISE EXCEPTION 'manual guard'; END $$;\n"
                "DELETE FROM common_market_data_run WHERE run_id = 'x';\n",
                encoding="utf-8",
            )
            self.assertTrue(assert_rollback_static_safe(safe, expected_scope=("common_market_data_run",)))

            unsafe = Path(tmp) / "unsafe.sql"
            unsafe.write_text(
                "DELETE FROM common_market_data_run WHERE run_id = 'x';\n"
                "DO $$ BEGIN RAISE EXCEPTION 'too late'; END $$;\n",
                encoding="utf-8",
            )
            with self.assertRaises(FastLaneValidationError):
                assert_rollback_static_safe(unsafe, expected_scope=("common_market_data_run",))

    def test_old_system_and_forbidden_scope_flags_block(self) -> None:
        with self.assertRaises(FastLaneValidationError):
            assert_no_old_system_touch(
                command=["python3", "/Users/chuanfuchen/stock_monitor_isolated/run.py"],
                path_scan=[],
                service_scan=[],
            )
        with self.assertRaises(FastLaneValidationError):
            assert_forbidden_scope_false({"database_written": False, "worker_started": True})


if __name__ == "__main__":
    unittest.main()
