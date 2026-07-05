import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ashare_v3.ingestion.official_daily_20260526_contract import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    FORBIDDEN_SCOPE,
    SOURCE_VERSIONS,
    TRADE_DATE,
    build_dry_run_plan,
    build_execute_contract,
    build_execute_preflight,
    build_rollback_sql,
    sample_pass_snapshot,
    write_artifacts,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "plan_official_daily_ingestion_20260526.py"


class OfficialDaily20260526ContractTests(unittest.TestCase):
    def test_contract_identity_and_expected_scope(self) -> None:
        snapshot = sample_pass_snapshot()

        plan = build_dry_run_plan(snapshot)

        self.assertEqual(plan["result"], "DRY_RUN_PASS")
        self.assertEqual(plan["trade_date"], TRADE_DATE)
        self.assertEqual(plan["source_batch_id"], BATCH_ID)
        self.assertEqual(plan["source_versions"], SOURCE_VERSIONS)
        self.assertEqual(
            plan["expected_scope"],
            {
                "stock_active_universe": 5523,
                "fixed_9_index": 9,
                "board_total": 428,
                "board_881_required": 127,
                "total_daily_fact_rows": 5960,
            },
        )
        self.assertEqual(plan["missing_official_daily"]["total"], 5960)
        self.assertEqual(plan["quality"]["p0_count"], 0)

    def test_preflight_blocks_when_calendar_missing(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["calendar"]["row_count"] = 0

        preflight = build_execute_preflight(snapshot)

        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("calendar_not_ready", preflight["blockers"])
        self.assertFalse(preflight["execute_authorized"])

    def test_preflight_blocks_existing_daily_or_source_conflict(self) -> None:
        snapshot = sample_pass_snapshot()
        snapshot["current_daily_fact_rows"]["stock"] = 1
        snapshot["target_source_version_conflicts"]["index"] = 1

        preflight = build_execute_preflight(snapshot)

        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("daily_fact_already_exists", preflight["blockers"])
        self.assertIn("source_version_conflict", preflight["blockers"])

    def test_execute_contract_write_scope_and_forbidden_scope(self) -> None:
        contract = build_execute_contract(sample_pass_snapshot())

        self.assertEqual(contract["result"], "DESIGN_PASS")
        self.assertEqual(
            tuple(contract["future_write_scope"]["allowed_tables"]),
            ALLOWED_FUTURE_WRITE_TABLES,
        )
        self.assertIn("common_event_outbox", FORBIDDEN_SCOPE)
        self.assertFalse(contract["parquet_policy"]["writes_parquet"])
        self.assertFalse(contract["side_effects"]["writes_postgres"])
        self.assertFalse(contract["side_effects"]["updates_active_source_version"])

    def test_rollback_sql_is_precise_and_boundary_safe(self) -> None:
        rollback_sql = build_rollback_sql()

        self.assertIn("20260526", rollback_sql)
        self.assertIn(BATCH_ID, rollback_sql)
        for source_version in SOURCE_VERSIONS.values():
            self.assertIn(source_version, rollback_sql)
        self.assertNotIn("common_event_outbox", rollback_sql)
        self.assertNotIn("condition_", rollback_sql)
        self.assertNotIn("Parquet", rollback_sql)

    def test_artifacts_are_serializable(self) -> None:
        snapshot = sample_pass_snapshot()
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = {
                "dry_run_json": Path(tmp_dir) / "dry_run.json",
                "dry_run_md": Path(tmp_dir) / "dry_run.md",
                "contract_json": Path(tmp_dir) / "contract.json",
                "contract_md": Path(tmp_dir) / "contract.md",
                "preflight_json": Path(tmp_dir) / "preflight.json",
                "preflight_md": Path(tmp_dir) / "preflight.md",
                "rollback_sql": Path(tmp_dir) / "rollback.sql",
            }

            write_artifacts(snapshot, paths=paths)

            for key in ("dry_run_json", "contract_json", "preflight_json"):
                decoded = json.loads(paths[key].read_text())
                self.assertIn("layer_role", decoded)
            self.assertIn(BATCH_ID, paths["rollback_sql"].read_text())

    def test_plan_cli_rejects_execute(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--execute", "--no-write"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dry-run/contract generator only", result.stderr)


if __name__ == "__main__":
    unittest.main()
