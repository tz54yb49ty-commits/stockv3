import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.review_post_close_preopen_guards import (
    GuardBlocked,
    SAFE_PROOF_POLLER_ALLOWLIST,
    build_active_lineage_materialization_guard_report,
    build_lineage_pollution_guard_report,
    build_n4_context_rollback_ready_report,
    build_preopen_readiness_noop_report,
    build_worker_launchd_guard_report,
    detect_worker_states,
)


SAFE_N4_CONTEXT_ROLLBACK_SQL = """
BEGIN;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM common_event_outbox WHERE source_layer = 'N4_trigger') THEN
    RAISE EXCEPTION 'outbox guard';
  END IF;
  IF EXISTS (SELECT 1 FROM common_event_inbox WHERE source_run_id = 'x') THEN
    RAISE EXCEPTION 'inbox guard';
  END IF;
  IF EXISTS (SELECT 1 FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE '%x%') THEN
    RAISE EXCEPTION 'checkpoint guard';
  END IF;
  IF EXISTS (SELECT 1 FROM common_action_run WHERE source_trigger_run_id = 'x') THEN
    RAISE EXCEPTION 'action guard';
  END IF;
  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    RAISE EXCEPTION 'user guard';
  END IF;
END $$;
DELETE FROM common_trigger_quality_item WHERE run_id = 'x';
DELETE FROM stock_trigger_context_snapshot WHERE run_id = 'x';
DELETE FROM index_trigger_context_snapshot WHERE run_id = 'x';
DELETE FROM board_trigger_context_snapshot WHERE run_id = 'x';
DELETE FROM common_trigger_run WHERE run_id = 'x';
COMMIT;
"""


class PostClosePreopenGuardsTest(unittest.TestCase):
    def _write_fastlane_pass_artifacts(self, docs_root: Path, *, source_trade_date: str, for_trade_date: str) -> Path:
        docs_dir = docs_root / for_trade_date
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "00_status.json").write_text(
            json.dumps(
                {
                    "result": "EXECUTE_PASS",
                    "source_trade_date": source_trade_date,
                    "for_trade_date": for_trade_date,
                    "failed_step_id": None,
                }
            ),
            encoding="utf-8",
        )
        (docs_dir / "01_oneshot_execute_report.json").write_text(
            json.dumps(
                {
                    "result": "EXECUTE_PASS",
                    "source_trade_date": source_trade_date,
                    "for_trade_date": for_trade_date,
                }
            ),
            encoding="utf-8",
        )
        latest = docs_root / "latest"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(docs_dir.name)
        return docs_dir

    def _write_lineage_config(self, path: Path, *, source_trade_date: str, for_trade_date: str, docs_dir: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "for_trade_date": for_trade_date,
                    "source_trade_date": source_trade_date,
                    "n2_run_id": f"condition_layer_{source_trade_date}_source_{source_trade_date}_for_{for_trade_date}_v1",
                    "subscription_run_id": f"market_data_subscription_{for_trade_date}_condition_layer_{source_trade_date}_source_{source_trade_date}_for_{for_trade_date}_v1",
                    "a1_preload_run_id": f"previous_day_minute_preload_{source_trade_date}_for_{for_trade_date}__market_data_subscription_{for_trade_date}_condition_layer_{source_trade_date}_source_{source_trade_date}_for_{for_trade_date}_v1",
                    "n4_context_run_id": f"trigger_context_snapshot_{for_trade_date}_condition_layer_{source_trade_date}_source_{source_trade_date}_for_{for_trade_date}_v1__atomic_rule_v1",
                    "updated_by": "runtime_control_status_repair",
                    "updated_at": "2026-06-12T02:06:21+08:00",
                    "source_status_path": str(docs_dir / "00_status.json"),
                    "source_oneshot_report_path": str(docs_dir / "01_oneshot_execute_report.json"),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_worker_report(self, path: Path, payload: dict) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        now = time.time()
        path.touch()
        return str(path)

    def _safe_n3_noop_report_payload(self) -> dict:
        return {
            "status": "noop",
            "reason": "noop_existing_close_proof_passed",
            "executed_child_command_count": 0,
            "side_effects": {
                "database_written": False,
                "market_data_pulled": False,
                "writes_outbox": False,
                "consumes_outbox": False,
                "updates_inbox_or_checkpoint": False,
                "touches_n4_n5_n6": False,
                "rollback_executed": False,
                "schema_changed": False,
                "starts_worker": False,
            },
        }

    def _safe_n4_noop_report_payload(self) -> dict:
        return {
            "status": "noop",
            "result": "noop",
            "child_execution": {"executed_child_command_count": 0},
            "side_effects": {
                "child_executed": False,
                "database_written": False,
                "outbox_consumed": False,
                "inbox_or_checkpoint_updated": False,
                "n5_n6_entered": False,
                "rollback_executed": False,
                "schema_changed": False,
                "worker_or_launchd_touched": False,
            },
            "forbidden_operation_proof": {
                "child_executed": False,
                "outbox_consumed": False,
                "inbox_checkpoint_updated": False,
                "n5_n6_entered": False,
                "rollback_executed": False,
                "schema_changed": False,
                "worker_launchd_touched": False,
            },
        }

    def test_n4_context_rollback_ready_requires_guarded_scoped_sql(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rollback = Path(tmp) / "n4_context_rollback.sql"
            rollback.write_text(SAFE_N4_CONTEXT_ROLLBACK_SQL, encoding="utf-8")

            report = build_n4_context_rollback_ready_report(
                for_trade_date="20260612",
                rollback_sql_path=rollback,
            )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["check"], "n4_context_rollback_ready")
        self.assertTrue(report["rollback_guard"]["guard_before_delete"])
        self.assertFalse(report["writes_database"])

    def test_n4_context_rollback_ready_blocks_missing_outbox_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rollback = Path(tmp) / "n4_context_rollback.sql"
            rollback.write_text("BEGIN;\nDELETE FROM common_trigger_run WHERE run_id='x';\nCOMMIT;\n", encoding="utf-8")

            with self.assertRaises(GuardBlocked) as caught:
                build_n4_context_rollback_ready_report(
                    for_trade_date="20260612",
                    rollback_sql_path=rollback,
                )

        self.assertIn("rollback_missing_guard", str(caught.exception))

    def test_preopen_readiness_noop_blocks_missing_static_input(self) -> None:
        with self.assertRaises(GuardBlocked) as caught:
            build_preopen_readiness_noop_report(
                for_trade_date="20260612",
                readiness={
                    "n2_condition": True,
                    "n3_subscription": True,
                    "n3_a1_preload": True,
                    "n3_a1_cumulative_amount": False,
                    "n4_trigger_context_snapshot": True,
                },
            )

        self.assertIn("preopen_readiness_missing:n3_a1_cumulative_amount", str(caught.exception))

    def test_active_lineage_materialization_guard_passes_when_latest_pass_matches_current_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_root = root / "docs" / "post_close_fastlane"
            docs_dir = self._write_fastlane_pass_artifacts(
                docs_root,
                source_trade_date="20260611",
                for_trade_date="20260612",
            )
            lineage_path = root / "docs" / "runtime" / "current_intraday_worker_lineage.json"
            self._write_lineage_config(
                lineage_path,
                source_trade_date="20260611",
                for_trade_date="20260612",
                docs_dir=docs_dir,
            )

            report = build_active_lineage_materialization_guard_report(
                for_trade_date="20260612",
                docs_root=docs_root,
                lineage_config_path=lineage_path,
            )

        self.assertEqual(report["result"], "PASS")
        self.assertTrue(report["active_lineage_materialized"])
        self.assertFalse(report["launchd_mutated"])

    def test_active_lineage_materialization_guard_blocks_latest_pass_with_stale_current_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_root = root / "docs" / "post_close_fastlane"
            docs_dir = self._write_fastlane_pass_artifacts(
                docs_root,
                source_trade_date="20260611",
                for_trade_date="20260612",
            )
            old_docs_dir = docs_root / "20260611"
            old_docs_dir.mkdir(parents=True)
            lineage_path = root / "docs" / "runtime" / "current_intraday_worker_lineage.json"
            self._write_lineage_config(
                lineage_path,
                source_trade_date="20260610",
                for_trade_date="20260611",
                docs_dir=old_docs_dir,
            )

            with self.assertRaises(GuardBlocked) as caught:
                build_active_lineage_materialization_guard_report(
                    for_trade_date="20260612",
                    docs_root=docs_root,
                    lineage_config_path=lineage_path,
                )

        self.assertEqual(caught.exception.report["blocked_reason"], "BLOCKED_ACTIVE_LINEAGE_NOT_MATERIALIZED")
        self.assertIn("for_trade_date", caught.exception.report["mismatches"])

    def test_active_lineage_materialization_guard_blocks_when_latest_fastlane_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_root = root / "docs" / "post_close_fastlane"
            docs_dir = docs_root / "20260612"
            docs_dir.mkdir(parents=True)
            (docs_dir / "00_status.json").write_text(
                json.dumps(
                    {
                        "result": "PARTIAL_BLOCKED",
                        "source_trade_date": "20260611",
                        "for_trade_date": "20260612",
                        "failed_step_id": "n4_trigger_context_snapshot",
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "01_oneshot_execute_report.json").write_text(
                json.dumps({"result": "PARTIAL_BLOCKED"}),
                encoding="utf-8",
            )
            (docs_root / "latest").symlink_to("20260612")

            with self.assertRaises(GuardBlocked) as caught:
                build_active_lineage_materialization_guard_report(
                    for_trade_date="20260612",
                    docs_root=docs_root,
                    lineage_config_path=root / "docs" / "runtime" / "current_intraday_worker_lineage.json",
                )

        self.assertEqual(caught.exception.report["blocked_reason"], "BLOCKED_FASTLANE_NOT_PASS")
        self.assertEqual(caught.exception.report["failed_step_id"], "n4_trigger_context_snapshot")

    def test_lineage_pollution_guard_blocks_intraday_runtime_refs(self) -> None:
        with self.assertRaises(GuardBlocked) as caught:
            build_lineage_pollution_guard_report(
                for_trade_date="20260612",
                pollution_counts={"n3p_runs": 1, "n4_matcher_runs": 0, "n5_runs": 0},
            )

        self.assertIn("lineage_pollution_detected:n3p_runs=1", str(caught.exception))

    def test_worker_launchd_guard_blocks_loaded_worker_without_mutation(self) -> None:
        with self.assertRaises(GuardBlocked) as caught:
            build_worker_launchd_guard_report(
                for_trade_date="20260612",
                worker_states={"n3_worker": False, "n4_worker": True, "n5_worker": False, "n6_worker": False},
            )

        self.assertIn("worker_loaded_or_running:n4_worker", str(caught.exception))

    def test_worker_launchd_guard_allows_safe_noop_proof_pollers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            n3_report = self._write_worker_report(
                tmp_path / "n3.json",
                self._safe_n3_noop_report_payload(),
            )
            n4_report = self._write_worker_report(
                tmp_path / "n4.json",
                self._safe_n4_noop_report_payload(),
            )

            report = build_worker_launchd_guard_report(
                for_trade_date="20260612",
                worker_states={
                    "n3_worker": {
                        "active": True,
                        "label": "com.ashare-v3.n3.intraday-proof-poller",
                        "report_path": n3_report,
                    },
                    "n4_worker": {
                        "active": True,
                        "label": "com.ashare-v3.n4.proof-discovery-poller",
                        "report_path": n4_report,
                    },
                    "n5_worker": False,
                    "n6_worker": False,
                },
                report_max_age_seconds=300,
            )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["worker_guard_policy"], "safe_proof_poller_allowlist_v1")
        self.assertEqual(report["worker_guard_classification"]["n3_worker"], "loaded_safe_noop_allowlisted")
        self.assertEqual(report["worker_guard_classification"]["n4_worker"], "loaded_safe_noop_allowlisted")
        self.assertFalse(report["writes_database"])
        self.assertFalse(report["event_ledger_touched"])
        self.assertFalse(report["worker_started"])

    def test_worker_launchd_guard_allowlist_uses_current_no_date_report_paths(self) -> None:
        self.assertEqual(
            SAFE_PROOF_POLLER_ALLOWLIST["n3_worker"]["report_path"],
            "tmp/N3_intraday_proof_poller_launchd_report.json",
        )
        self.assertEqual(
            SAFE_PROOF_POLLER_ALLOWLIST["n3p_worker"]["report_path"],
            "tmp/N3_intraday_proof_poller_n3p_launchd_report.json",
        )
        self.assertEqual(
            SAFE_PROOF_POLLER_ALLOWLIST["n3_hint_worker"]["report_path"],
            "tmp/N3_intraday_proof_poller_hint_launchd_report.json",
        )
        self.assertEqual(
            SAFE_PROOF_POLLER_ALLOWLIST["n4_worker"]["report_path"],
            "tmp/N4_intraday_proof_discovery_poller_launchd_report.json",
        )
        self.assertEqual(
            SAFE_PROOF_POLLER_ALLOWLIST["n4_hint_worker"]["report_path"],
            "tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json",
        )

    def test_worker_launchd_guard_uses_n3p_branch_report_instead_of_stale_base_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                base_report = Path("tmp/N3_intraday_proof_poller_launchd_report.json")
                self._write_worker_report(base_report, self._safe_n3_noop_report_payload())
                stale_time = time.time() - 1000
                os.utime(base_report, (stale_time, stale_time))
                self._write_worker_report(
                    Path("tmp/N3_intraday_proof_poller_n3p_launchd_report.json"),
                    self._safe_n3_noop_report_payload(),
                )

                report = build_worker_launchd_guard_report(
                    for_trade_date="20260703",
                    worker_states={
                        "n3p_worker": {
                            "active": True,
                            "label": "com.ashare-v3.n3.intraday-proof-poller.n3p",
                        }
                    },
                    report_max_age_seconds=300,
                )
            finally:
                os.chdir(old_cwd)

        evidence = report["safe_allowlist_evidence"]["n3p_worker"]
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(evidence["report_path"], "tmp/N3_intraday_proof_poller_n3p_launchd_report.json")
        self.assertEqual(evidence["classification"], "loaded_safe_noop_allowlisted")

    def test_worker_launchd_guard_blocks_n3_branch_report_with_child_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            branch_report = self._safe_n3_noop_report_payload()
            branch_report["status"] = "blocked"
            branch_report["reason"] = "child_step_failed:n3p_current_source_fetch"
            branch_report["executed_child_command_count"] = 1
            report_path = self._write_worker_report(Path(tmp) / "n3p.json", branch_report)

            with self.assertRaises(GuardBlocked) as caught:
                build_worker_launchd_guard_report(
                    for_trade_date="20260703",
                    worker_states={
                        "n3p_worker": {
                            "active": True,
                            "label": "com.ashare-v3.n3.intraday-proof-poller.n3p",
                            "report_path": report_path,
                        }
                    },
                    report_max_age_seconds=300,
                )

        self.assertIn("loaded_safe_but_report_unsafe_blocked:n3p_worker:child_executed", str(caught.exception))

    def test_worker_launchd_guard_blocks_missing_n3_branch_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            try:
                os.chdir(Path(tmp))
                with self.assertRaises(GuardBlocked) as caught:
                    build_worker_launchd_guard_report(
                        for_trade_date="20260703",
                        worker_states={
                            "n3_hint_worker": {
                                "active": True,
                                "label": "com.ashare-v3.n3.intraday-proof-poller.hint",
                            }
                        },
                        report_max_age_seconds=300,
                    )
            finally:
                os.chdir(old_cwd)

        self.assertIn("loaded_safe_but_report_unsafe_blocked:n3_hint_worker:report_missing", str(caught.exception))

    def test_worker_launchd_guard_blocks_n3_branch_report_with_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            branch_report = self._safe_n3_noop_report_payload()
            branch_report["side_effects"]["database_written"] = True
            report_path = self._write_worker_report(Path(tmp) / "hint.json", branch_report)

            with self.assertRaises(GuardBlocked) as caught:
                build_worker_launchd_guard_report(
                    for_trade_date="20260703",
                    worker_states={
                        "n3_hint_worker": {
                            "active": True,
                            "label": "com.ashare-v3.n3.intraday-proof-poller.hint",
                            "report_path": report_path,
                        }
                    },
                    report_max_age_seconds=300,
                )

        self.assertIn(
            "loaded_safe_but_report_unsafe_blocked:n3_hint_worker:side_effect_database_written",
            str(caught.exception),
        )

    def test_detect_worker_states_maps_n3_branch_processes_to_branch_reports(self) -> None:
        process_lines = [
            "123 /usr/bin/python3 scripts/run_n3_intraday_proof_poller_once.py --branch n3p_only",
            "124 /usr/bin/python3 scripts/run_n3_intraday_proof_poller_once.py --branch hint_only",
        ]

        with patch("scripts.review_post_close_preopen_guards._launchd_label_loaded", return_value=False), patch(
            "scripts.review_post_close_preopen_guards._process_command_lines",
            return_value=process_lines,
        ):
            states = detect_worker_states()

        self.assertFalse(states["n3_worker"])
        self.assertEqual(states["n3p_worker"]["label"], "com.ashare-v3.n3.intraday-proof-poller.n3p")
        self.assertEqual(
            states["n3p_worker"]["report_path"],
            "tmp/N3_intraday_proof_poller_n3p_launchd_report.json",
        )
        self.assertEqual(states["n3_hint_worker"]["label"], "com.ashare-v3.n3.intraday-proof-poller.hint")
        self.assertEqual(
            states["n3_hint_worker"]["report_path"],
            "tmp/N3_intraday_proof_poller_hint_launchd_report.json",
        )

    def test_detect_worker_states_does_not_collapse_textual_n3_script_mentions_into_base_worker(self) -> None:
        process_lines = [
            "123 /bin/zsh -lc rg run_n3_intraday_proof_poller_once.py scripts tests",
            "124 /usr/bin/git add docs/run_n3_intraday_proof_poller_once.py.notes",
            "125 /usr/bin/git hash-object -- scripts/run_n3_intraday_proof_poller_once.py",
        ]

        with patch("scripts.review_post_close_preopen_guards._launchd_label_loaded", return_value=False), patch(
            "scripts.review_post_close_preopen_guards._process_command_lines",
            return_value=process_lines,
        ):
            states = detect_worker_states()

        self.assertFalse(states["n3_worker"])
        self.assertFalse(states["n3p_worker"])
        self.assertFalse(states["n3_hint_worker"])

    def test_detect_worker_states_marks_true_base_n3_process_without_branch(self) -> None:
        process_lines = [
            "123 /usr/bin/python3 scripts/run_n3_intraday_proof_poller_once.py --lineage-config docs/runtime/current_intraday_worker_lineage.json",
        ]

        with patch("scripts.review_post_close_preopen_guards._launchd_label_loaded", return_value=False), patch(
            "scripts.review_post_close_preopen_guards._process_command_lines",
            return_value=process_lines,
        ):
            states = detect_worker_states()

        self.assertEqual(states["n3_worker"]["label"], "com.ashare-v3.n3.intraday-proof-poller")
        self.assertEqual(
            states["n3_worker"]["report_path"],
            "tmp/N3_intraday_proof_poller_launchd_report.json",
        )

    def test_detect_worker_states_still_blocks_legacy_n3_auto_poll_worker(self) -> None:
        process_lines = [
            "123 /usr/bin/python3 scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py --execute",
        ]

        with patch("scripts.review_post_close_preopen_guards._launchd_label_loaded", return_value=False), patch(
            "scripts.review_post_close_preopen_guards._process_command_lines",
            return_value=process_lines,
        ):
            states = detect_worker_states()

        self.assertTrue(states["n3_worker"])

    def test_detect_worker_states_keeps_n4_proof_discovery_mapping(self) -> None:
        process_lines = [
            "123 /usr/bin/python3 scripts/run_n4_intraday_proof_discovery_poll_once.py --lineage-config docs/runtime/current_intraday_worker_lineage.json --mode ordinary",
        ]

        with patch("scripts.review_post_close_preopen_guards._launchd_label_loaded", return_value=False), patch(
            "scripts.review_post_close_preopen_guards._process_command_lines",
            return_value=process_lines,
        ):
            states = detect_worker_states()

        self.assertEqual(states["n4_worker"]["label"], "com.ashare-v3.n4.proof-discovery-poller")
        self.assertEqual(
            states["n4_worker"]["report_path"],
            "tmp/N4_intraday_proof_discovery_poller_launchd_report.json",
        )

    def test_detect_worker_states_maps_n4_hint_mode_to_hint_report(self) -> None:
        process_lines = [
            "123 /usr/bin/python3 scripts/run_n4_intraday_proof_discovery_poll_once.py --lineage-config docs/runtime/current_intraday_worker_lineage.json --mode hint",
        ]

        with patch("scripts.review_post_close_preopen_guards._launchd_label_loaded", return_value=False), patch(
            "scripts.review_post_close_preopen_guards._process_command_lines",
            return_value=process_lines,
        ):
            states = detect_worker_states()

        self.assertFalse(states["n4_worker"])
        self.assertEqual(states["n4_hint_worker"]["label"], "com.ashare-v3.n4.proof-discovery-poller.hint")
        self.assertEqual(
            states["n4_hint_worker"]["report_path"],
            "tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json",
        )

    def test_worker_launchd_guard_allows_safe_n4_hint_noop_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            n4_hint_report = self._write_worker_report(
                tmp_path / "n4_hint.json",
                self._safe_n4_noop_report_payload(),
            )

            report = build_worker_launchd_guard_report(
                for_trade_date="20260703",
                worker_states={
                    "n4_hint_worker": {
                        "active": True,
                        "label": "com.ashare-v3.n4.proof-discovery-poller.hint",
                        "report_path": n4_hint_report,
                    }
                },
                report_max_age_seconds=300,
            )

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["worker_guard_classification"]["n4_hint_worker"], "loaded_safe_noop_allowlisted")

    def test_worker_launchd_guard_ignores_stale_dated_n4_report_when_current_report_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                old_report = Path("tmp/N4_intraday_proof_discovery_poller_20260701_launchd_report.json")
                self._write_worker_report(old_report, self._safe_n4_noop_report_payload())
                stale_time = time.time() - 1000
                os.utime(old_report, (stale_time, stale_time))
                self._write_worker_report(
                    Path("tmp/N4_intraday_proof_discovery_poller_launchd_report.json"),
                    self._safe_n4_noop_report_payload(),
                )

                report = build_worker_launchd_guard_report(
                    for_trade_date="20260703",
                    worker_states={
                        "n4_worker": {
                            "active": True,
                            "label": "com.ashare-v3.n4.proof-discovery-poller",
                        }
                    },
                    report_max_age_seconds=300,
                )
            finally:
                os.chdir(old_cwd)

        evidence = report["safe_allowlist_evidence"]["n4_worker"]
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(evidence["report_path"], "tmp/N4_intraday_proof_discovery_poller_launchd_report.json")
        self.assertEqual(evidence["classification"], "loaded_safe_noop_allowlisted")

    def test_worker_launchd_guard_blocks_when_current_no_date_n4_report_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                self._write_worker_report(
                    Path("tmp/N4_intraday_proof_discovery_poller_20260701_launchd_report.json"),
                    self._safe_n4_noop_report_payload(),
                )

                with self.assertRaises(GuardBlocked) as caught:
                    build_worker_launchd_guard_report(
                        for_trade_date="20260703",
                        worker_states={
                            "n4_worker": {
                                "active": True,
                                "label": "com.ashare-v3.n4.proof-discovery-poller",
                            }
                        },
                        report_max_age_seconds=300,
                    )
            finally:
                os.chdir(old_cwd)

        self.assertIn("loaded_safe_but_report_unsafe_blocked:n4_worker:report_missing", str(caught.exception))
        self.assertEqual(
            caught.exception.report["safe_allowlist_evidence"]["n4_worker"]["report_path"],
            "tmp/N4_intraday_proof_discovery_poller_launchd_report.json",
        )

    def test_worker_launchd_guard_blocks_unsafe_current_no_date_n4_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                self._write_worker_report(
                    Path("tmp/N4_intraday_proof_discovery_poller_20260701_launchd_report.json"),
                    self._safe_n4_noop_report_payload(),
                )
                unsafe_report = self._safe_n4_noop_report_payload()
                unsafe_report["side_effects"]["database_written"] = True
                self._write_worker_report(
                    Path("tmp/N4_intraday_proof_discovery_poller_launchd_report.json"),
                    unsafe_report,
                )

                with self.assertRaises(GuardBlocked) as caught:
                    build_worker_launchd_guard_report(
                        for_trade_date="20260703",
                        worker_states={
                            "n4_worker": {
                                "active": True,
                                "label": "com.ashare-v3.n4.proof-discovery-poller",
                            }
                        },
                        report_max_age_seconds=300,
                    )
            finally:
                os.chdir(old_cwd)

        self.assertIn("loaded_safe_but_report_unsafe_blocked:n4_worker:side_effect_database_written", str(caught.exception))

    def test_worker_launchd_guard_keeps_blocked_n4_downstream_refs_report_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp_path)
                blocked_report = self._safe_n4_noop_report_payload()
                blocked_report["status"] = "blocked"
                blocked_report["result"] = "blocked"
                blocked_report["error"] = "existing N4 target has downstream refs: trigger_provisional_ordinary_20260702"
                self._write_worker_report(
                    Path("tmp/N4_intraday_proof_discovery_poller_launchd_report.json"),
                    blocked_report,
                )

                with self.assertRaises(GuardBlocked) as caught:
                    build_worker_launchd_guard_report(
                        for_trade_date="20260703",
                        worker_states={
                            "n4_worker": {
                                "active": True,
                                "label": "com.ashare-v3.n4.proof-discovery-poller",
                            }
                        },
                        report_max_age_seconds=300,
                    )
            finally:
                os.chdir(old_cwd)

        self.assertIn("loaded_safe_but_report_unsafe_blocked:n4_worker:report_status_not_safe", str(caught.exception))

    def test_worker_launchd_guard_blocks_safe_label_with_missing_report(self) -> None:
        with self.assertRaises(GuardBlocked) as caught:
            build_worker_launchd_guard_report(
                for_trade_date="20260612",
                worker_states={
                    "n3_worker": {
                        "active": True,
                        "label": "com.ashare-v3.n3.intraday-proof-poller",
                        "report_path": "/tmp/does-not-exist-n3-report.json",
                    }
                },
            )

        self.assertIn("loaded_safe_but_report_unsafe_blocked:n3_worker:report_missing", str(caught.exception))

    def test_worker_launchd_guard_blocks_safe_label_with_side_effect_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            n3_report = self._write_worker_report(
                Path(tmp) / "n3.json",
                {
                    "status": "noop",
                    "executed_child_command_count": 0,
                    "side_effects": {
                        "database_written": True,
                        "market_data_pulled": False,
                        "writes_outbox": False,
                        "consumes_outbox": False,
                        "updates_inbox_or_checkpoint": False,
                        "touches_n4_n5_n6": False,
                        "rollback_executed": False,
                        "schema_changed": False,
                        "starts_worker": False,
                    },
                },
            )

            with self.assertRaises(GuardBlocked) as caught:
                build_worker_launchd_guard_report(
                    for_trade_date="20260612",
                    worker_states={
                        "n3_worker": {
                            "active": True,
                            "label": "com.ashare-v3.n3.intraday-proof-poller",
                            "report_path": n3_report,
                        }
                    },
                )

        self.assertIn("loaded_safe_but_report_unsafe_blocked:n3_worker:side_effect_database_written", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
