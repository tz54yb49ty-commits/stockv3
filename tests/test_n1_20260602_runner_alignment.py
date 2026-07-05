import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

from ashare_v3.ingestion.n1_20260602_runner_alignment import (
    OFFICIAL_DAILY_BATCH_ID,
    OFFICIAL_DAILY_SOURCE_VERSIONS,
    CONDITION_SOURCE_BATCH_ID,
    CONDITION_SOURCE_VERSIONS,
    AlignmentBlocked,
    build_alignment_report,
    build_condition_source_preflight,
    build_official_daily_preflight,
    check_rollback_sql_scope,
    collect_source_readiness,
    sample_baseline,
    validate_execute_flags,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_SCRIPT = PROJECT_ROOT / "scripts" / "run_official_daily_ingestion_20260602_once.py"
CONDITION_SCRIPT = PROJECT_ROOT / "scripts" / "run_condition_source_activation_20260602_once.py"


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class N120260602RunnerAlignmentTests(unittest.TestCase):
    def test_execute_requires_all_four_final_flags(self) -> None:
        cases = [
            (False, True, True, True, "--execute"),
            (True, False, True, True, "--user-confirmed"),
            (True, True, False, True, "--source-fetch-enabled"),
            (True, True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, fetch, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(AlignmentBlocked, message):
                    validate_execute_flags(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        source_fetch_enabled=fetch,
                        postgres_commit_enabled=commit,
                    )

    def test_tushare_token_absent_blocks_source_readiness(self) -> None:
        with mock.patch.dict(os.environ, {"ASHARE_V3_TUSHARE_ENV_PATH": "/tmp/missing-ashare-v3-tushare.env"}, clear=True):
            readiness = collect_source_readiness(tdx_root=PROJECT_ROOT)
        self.assertFalse(readiness["tushare_token_present"])
        self.assertEqual(readiness["tushare_token_length"], 0)
        self.assertIn("tushare_token_absent", readiness["p0_blockers"])

    def test_alignment_report_clears_runner_missing_but_keeps_source_and_dependency_blockers(self) -> None:
        baseline = sample_baseline()
        readiness = {
            "tushare_token_present": False,
            "tdx_root_exists": True,
            "tdx_root_readable": True,
            "mootdx_import_present": True,
            "p0_blockers": ["tushare_token_absent"],
        }
        report = build_alignment_report(baseline=baseline, source_readiness=readiness)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertTrue(report["runners"]["official_daily"]["exists"])
        self.assertTrue(report["runners"]["condition_source"]["exists"])
        self.assertNotIn("n1_official_daily_20260602_runner_missing", report["blockers"])
        self.assertNotIn("n1_condition_source_20260602_runner_missing", report["blockers"])
        self.assertIn("tushare_token_absent", report["blockers"])
        self.assertIn("condition_source_requires_official_daily_20260602_passed", report["blockers"])

    def test_official_and_condition_preflights_are_default_read_only_and_not_final_execute_ready(self) -> None:
        baseline = sample_baseline()
        readiness = {"tushare_token_present": False, "p0_blockers": ["tushare_token_absent"]}
        official = build_official_daily_preflight(
            baseline=baseline,
            source_readiness=readiness,
            execute_requested=False,
            user_confirmed=False,
            source_fetch_enabled=False,
            postgres_commit_enabled=False,
        )
        condition = build_condition_source_preflight(
            baseline=baseline,
            source_readiness=readiness,
            execute_requested=False,
            user_confirmed=False,
            source_fetch_enabled=False,
            postgres_commit_enabled=False,
        )
        self.assertEqual(official["source_batch_id"], OFFICIAL_DAILY_BATCH_ID)
        self.assertEqual(condition["source_batch_id"], CONDITION_SOURCE_BATCH_ID)
        self.assertEqual(official["source_versions"], OFFICIAL_DAILY_SOURCE_VERSIONS)
        self.assertEqual(condition["source_versions"], CONDITION_SOURCE_VERSIONS)
        self.assertFalse(official["side_effects"]["writes_database"])
        self.assertFalse(condition["side_effects"]["writes_database"])
        self.assertFalse(official["final_execute_gate_allowed"])
        self.assertFalse(condition["final_execute_gate_allowed"])

    def test_runner_scripts_exist_and_default_to_non_execute(self) -> None:
        official_runner = load_script(OFFICIAL_SCRIPT, "official_20260602_runner")
        condition_runner = load_script(CONDITION_SCRIPT, "condition_20260602_runner")
        self.assertFalse(official_runner.parse_args(["--trade-date", "20260602"]).execute)
        self.assertFalse(condition_runner.parse_args(["--trade-date", "20260602"]).execute)

    def test_rollback_sql_is_scoped_and_hard_fails_before_delete(self) -> None:
        official = check_rollback_sql_scope(
            PROJECT_ROOT / "sql" / "N1_official_daily_20260602_ingestion_rollback.sql",
            required_tokens=[OFFICIAL_DAILY_BATCH_ID, *OFFICIAL_DAILY_SOURCE_VERSIONS.values()],
        )
        condition = check_rollback_sql_scope(
            PROJECT_ROOT / "sql" / "N1_condition_source_20260602_activation_rollback.sql",
            required_tokens=[CONDITION_SOURCE_BATCH_ID, *CONDITION_SOURCE_VERSIONS.values()],
        )
        self.assertEqual(official["result"], "ROLLBACK_SCOPE_PASS")
        self.assertEqual(condition["result"], "ROLLBACK_SCOPE_PASS")
        for checked in (official, condition):
            self.assertTrue(checked["hard_fail_before_delete"])
            self.assertFalse(checked["forbidden_scope_touched"])


if __name__ == "__main__":
    unittest.main()
