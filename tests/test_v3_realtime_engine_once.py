import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import scripts.run_v3_realtime_engine_once as engine


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
N3_RUN_ID = "action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1"
N4_RUN_ID = "v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1"
N5_RUN_ID = "v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1"
N6_RUN_ID = "v3_n6_user_projection_20260612_after_n5_action_v1"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260611_source_20260611_for_20260612_v1"
SNAPSHOT_RUN_ID = "realtime_daily_snapshot_20260612_standard_outbox_until_1500__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"


class Completed:
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def resolved_lineage() -> dict:
    return {
        "status": "resolved",
        "for_trade_date": "20260612",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "n3_metric_run_id": N3_RUN_ID,
        "n4_trigger_run_id": N4_RUN_ID,
        "n5_action_run_id": N5_RUN_ID,
        "n6_projection_run_id": N6_RUN_ID,
        "source_snapshot_run_id": SNAPSHOT_RUN_ID,
        "trigger_context_run_id": f"trigger_context_snapshot_20260612_{SOURCE_CONDITION_RUN_ID}",
    }


def status_missing(_stage: str, _run_id: str) -> dict:
    return {"status": "missing"}


def coverage_pass(**_kwargs) -> dict:
    return {"result": "PASS", "reason": "test_metric_coverage_ready"}


class V3RealtimeEngineOnceTest(unittest.TestCase):
    def test_default_plan_only_builds_argv_commands_without_execution(self) -> None:
        calls: list[list[str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = engine.run_v3_realtime_engine_once(
                auto_resolve_lineage=True,
                as_of=datetime(2026, 6, 12, 10, 1, tzinfo=ASIA_SHANGHAI),
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                lock_path=Path(tmp) / "engine.lock",
                python_executable=sys.executable,
                lineage_resolver=lambda **_: resolved_lineage(),
                status_provider=status_missing,
                command_runner=lambda argv: calls.append(argv),
            )

        self.assertEqual(report["result"], "PLAN_ONLY")
        self.assertEqual(calls, [])
        self.assertEqual(
            [step["stage"] for step in report["child_command_plan"]],
            ["N3_REALTIME_VIRTUAL_METRIC", "N4_TRIGGER", "N5_ACTION", "N6_USER_PROJECTION"],
        )
        for step in report["child_command_plan"]:
            self.assertIsInstance(step["argv"], list)
            self.assertFalse(step["uses_shell"])
            self.assertIn("--execute", step["argv"])
            self.assertIn("--user-confirmed", step["argv"])
        self.assertTrue(report["policy_proof"]["n6_projection_only"])
        self.assertFalse(report["forbidden_scope_proof"]["voice_mobile_sim_trade_touched"])

    def test_execute_requires_both_flags_before_lineage_lock_or_children(self) -> None:
        for execute, user_confirmed, reason in [
            (True, False, "missing_user_confirmed_flag"),
            (False, True, "missing_execute_flag"),
        ]:
            with self.subTest(execute=execute, user_confirmed=user_confirmed):
                calls: list[list[str]] = []
                lineage_calls: list[object] = []
                with tempfile.TemporaryDirectory() as tmp:
                    report = engine.run_v3_realtime_engine_once(
                        auto_resolve_lineage=True,
                        docs_root=Path(tmp) / "docs",
                        sql_root=Path(tmp) / "sql",
                        lock_path=Path(tmp) / "engine.lock",
                        execute=execute,
                        user_confirmed=user_confirmed,
                        lineage_resolver=lambda **kwargs: lineage_calls.append(kwargs) or resolved_lineage(),
                        command_runner=lambda argv: calls.append(argv),
                    )

                self.assertEqual(report["result"], "BLOCKED")
                self.assertEqual(report["blocked_reason"], reason)
                self.assertEqual(calls, [])
                self.assertEqual(lineage_calls, [])

    def test_no_overlap_lock_blocks_before_children(self) -> None:
        calls: list[list[str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "engine.lock"
            with engine.acquire_no_overlap_lock(lock_path):
                report = engine.run_v3_realtime_engine_once(
                    auto_resolve_lineage=True,
                    docs_root=Path(tmp) / "docs",
                    sql_root=Path(tmp) / "sql",
                    lock_path=lock_path,
                    execute=True,
                    user_confirmed=True,
                    lineage_resolver=lambda **_: resolved_lineage(),
                    command_runner=lambda argv: calls.append(argv),
                )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "no_overlap_lock_already_held")
        self.assertEqual(calls, [])

    def test_execute_runs_n3_n4_n5_n6_in_order_with_trigger_matched_only_n5_entry(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> Completed:
            calls.append(argv)
            return Completed()

        with tempfile.TemporaryDirectory() as tmp:
            report = engine.run_v3_realtime_engine_once(
                auto_resolve_lineage=True,
                as_of=datetime(2026, 6, 12, 10, 1, tzinfo=ASIA_SHANGHAI),
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                lock_path=Path(tmp) / "engine.lock",
                python_executable=sys.executable,
                execute=True,
                user_confirmed=True,
                lineage_resolver=lambda **_: resolved_lineage(),
                status_provider=status_missing,
                command_runner=runner,
                metric_coverage_guard=coverage_pass,
            )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(
            [step["stage"] for step in report["executed_steps"]],
            ["N3_REALTIME_VIRTUAL_METRIC", "N4_TRIGGER", "N5_ACTION", "N6_USER_PROJECTION"],
        )
        self.assertEqual([call[1] for call in calls], [
            "scripts/run_v3_realtime_virtual_metric_writer_once.py",
            "scripts/run_trigger_projection_matcher_once.py",
            "scripts/run_action_consumer_once.py",
            "scripts/run_n6_projection_once.py",
        ])
        for argv in calls:
            self.assertIsInstance(argv, list)
            self.assertIn("--execute", argv)
            self.assertIn("--user-confirmed", argv)
        n5 = calls[2]
        self.assertIn("--source-event-type", n5)
        self.assertEqual(n5[n5.index("--source-event-type") + 1], "TriggerMatched")
        self.assertNotIn("TriggerPendingMarketData", n5)
        self.assertNotIn("TriggerStateChanged", n5)
        n6 = calls[3]
        self.assertIn("--source-action-run-id", n6)
        self.assertEqual(n6[n6.index("--source-action-run-id") + 1], N5_RUN_ID)
        self.assertIn("--projection-run-id", n6)
        self.assertEqual(n6[n6.index("--projection-run-id") + 1], N6_RUN_ID)
        self.assertIn("--json", n6)
        self.assertTrue(report["side_effects"]["n6_child_invoked"])
        self.assertFalse(report["forbidden_scope_proof"]["proposal_order_trade_sim_position_pnl_real_trade"])

    def test_existing_passed_deterministic_run_ids_noop_without_children(self) -> None:
        calls: list[list[str]] = []

        def status_provider(_stage: str, _run_id: str) -> dict:
            return {"status": "passed"}

        with tempfile.TemporaryDirectory() as tmp:
            report = engine.run_v3_realtime_engine_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                lock_path=Path(tmp) / "engine.lock",
                execute=True,
                user_confirmed=True,
                lineage_resolver=lambda **_: resolved_lineage(),
                status_provider=status_provider,
                command_runner=lambda argv: calls.append(argv),
            )

        self.assertEqual(report["result"], "NOOP_PASS")
        self.assertEqual(report["reason"], "all_deterministic_runs_already_passed")
        self.assertEqual(calls, [])
        self.assertEqual(len(report["skipped_steps"]), 4)

    def test_source_not_ready_noop_pass_without_children(self) -> None:
        calls: list[list[str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            report = engine.run_v3_realtime_engine_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                lock_path=Path(tmp) / "engine.lock",
                execute=True,
                user_confirmed=True,
                lineage_resolver=lambda **_: {"status": "noop", "reason": "source_not_ready"},
                command_runner=lambda argv: calls.append(argv),
            )

        self.assertEqual(report["result"], "NOOP_PASS")
        self.assertEqual(report["reason"], "source_not_ready")
        self.assertEqual(calls, [])

    def test_child_failure_blocks_and_stops_downstream(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> Completed:
            calls.append(argv)
            if "scripts/run_n4_trigger_projection_matcher_once.py" in argv:
                return Completed(1, stderr="n4 failed")
            if "scripts/run_trigger_projection_matcher_once.py" in argv:
                return Completed(1, stderr="n4 failed")
            return Completed()

        with tempfile.TemporaryDirectory() as tmp:
            report = engine.run_v3_realtime_engine_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                lock_path=Path(tmp) / "engine.lock",
                python_executable=sys.executable,
                execute=True,
                user_confirmed=True,
                lineage_resolver=lambda **_: resolved_lineage(),
                status_provider=status_missing,
                command_runner=runner,
                metric_coverage_guard=coverage_pass,
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "n4_trigger_failed")
        self.assertEqual([step["stage"] for step in report["executed_steps"]], ["N3_REALTIME_VIRTUAL_METRIC", "N4_TRIGGER"])
        self.assertEqual(len(calls), 2)

    def test_metric_coverage_guard_runs_after_n3_and_blocks_before_n4(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> Completed:
            calls.append(argv)
            return Completed()

        def coverage_guard(**_kwargs) -> dict:
            return {
                "result": "BLOCKED",
                "blocked_reason": "n3_metric_missing_for_context_scope",
                "missing_identity_count": 1,
                "missing_identity_sample": ["stock:SH:603259"],
            }

        with tempfile.TemporaryDirectory() as tmp:
            report = engine.run_v3_realtime_engine_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                lock_path=Path(tmp) / "engine.lock",
                execute=True,
                user_confirmed=True,
                lineage_resolver=lambda **_: resolved_lineage(),
                status_provider=status_missing,
                command_runner=runner,
                metric_coverage_guard=coverage_guard,
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "metric_coverage_guard_failed")
        self.assertEqual(report["metric_coverage_guard"]["missing_identity_sample"], ["stock:SH:603259"])
        self.assertEqual([step["stage"] for step in report["executed_steps"]], ["N3_REALTIME_VIRTUAL_METRIC"])
        self.assertEqual(len(calls), 1)

    def test_for_trade_date_mismatch_blocks_stale_artifact_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            n3_contract = docs / "contract.json"
            closeout = docs / "closeout.json"
            n3_contract.write_text(
                json.dumps(
                    {
                        "target_run_id": N3_RUN_ID,
                        "source_scope": {
                            "for_trade_date": "20260612",
                            "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                            "source_snapshot_run_id": SNAPSHOT_RUN_ID,
                        },
                    }
                ),
                encoding="utf-8",
            )
            closeout.write_text(
                json.dumps(
                    {
                        "for_trade_date": "20260612",
                        "source_run_ids": {
                            "n3_projection_run_id": N3_RUN_ID,
                            "n4_trigger_run_id": N4_RUN_ID,
                            "n5_action_run_id": N5_RUN_ID,
                        },
                    }
                ),
                encoding="utf-8",
            )

            lineage = engine.resolve_lineage_from_artifacts(
                for_trade_date="20260615",
                source_condition_run_id=None,
                n3_metric_run_id=None,
                n4_trigger_run_id=None,
                n5_action_run_id=None,
                n6_projection_run_id=None,
                source_snapshot_run_id=None,
                trigger_context_run_id=None,
                n3_contract_path=n3_contract,
                closeout_path=closeout,
            )

        self.assertEqual(lineage["status"], "blocked")
        self.assertEqual(lineage["reason"], "stale_artifact_lineage_mismatch")

    def test_scheduler_auto_resolve_without_explicit_date_blocks_removed_dynamic_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = engine.run_v3_realtime_engine_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                lock_path=Path(tmp) / "engine.lock",
                as_of=datetime(2026, 6, 14, 23, 20, tzinfo=ASIA_SHANGHAI),
                command_runner=lambda argv: (_ for _ in ()).throw(AssertionError("plan-only must not run")),
            )

        self.assertEqual(report["result"], "PLAN_ONLY")
        self.assertFalse(report["dynamic_chain_fallback"]["enabled"])
        self.assertTrue(report["dynamic_chain_fallback"]["removed"])
        self.assertEqual(report["blocked_reason"], "dynamic_chain_fallback_removed")
        self.assertEqual(report["child_command_plan"], [])
        self.assertIn("N3_market_data", " ".join(report["next_required_gates"]))

    def test_scheduler_execute_blocks_removed_dynamic_chain_without_child_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = engine.run_v3_realtime_engine_once(
                auto_resolve_lineage=True,
                docs_root=Path(tmp) / "docs",
                sql_root=Path(tmp) / "sql",
                lock_path=Path(tmp) / "engine.lock",
                as_of=datetime(2026, 6, 15, 9, 20, tzinfo=ASIA_SHANGHAI),
                allow_overwrite=True,
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: (_ for _ in ()).throw(AssertionError("plan-only must not run")),
            )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "dynamic_chain_fallback_removed")
        self.assertEqual(report["executed_steps"], [])
        self.assertEqual(report["child_command_plan"], [])

    def test_main_writes_json_and_markdown_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_report = Path(tmp) / "report.json"
            md_report = Path(tmp) / "report.md"

            rc = engine.main(
                [
                    "--for-trade-date",
                    "20260612",
                    "--source-condition-run-id",
                    SOURCE_CONDITION_RUN_ID,
                    "--n3-metric-run-id",
                    N3_RUN_ID,
                    "--n4-trigger-run-id",
                    N4_RUN_ID,
                    "--n5-action-run-id",
                    N5_RUN_ID,
                    "--source-snapshot-run-id",
                    SNAPSHOT_RUN_ID,
                    "--json-report-path",
                    str(json_report),
                    "--markdown-report-path",
                    str(md_report),
                ]
            )

            self.assertEqual(rc, 0)
            report = json.loads(json_report.read_text(encoding="utf-8"))
            self.assertEqual(report["result"], "PLAN_ONLY")
            self.assertIn("V3 Realtime Engine Production Run Once", md_report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
