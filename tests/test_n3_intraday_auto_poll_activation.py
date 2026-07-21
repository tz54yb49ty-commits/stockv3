import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import scripts.run_n3_intraday_b1_c1_b2_auto_poll_once as auto_poll
import scripts.run_n3_intraday_proof_poller_once as proof_poller


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260611_condition_layer_x"
PRELOAD_RUN_ID = "previous_day_minute_preload_20260610_for_20260611__market_data_subscription_x"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260610_source_20260610_for_20260611_v1"
N4_CONTEXT_RUN_ID = "trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1__atomic_rule_v1"
SOURCE_TRADE_DATE = "20260610"
EXPECTED_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"


def write_lineage_config(path: Path, *, enabled: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "enabled": enabled,
                "for_trade_date": "20260612",
                "source_trade_date": "20260611",
                "n2_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
                "subscription_run_id": "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1",
                "a1_preload_run_id": (
                    "previous_day_minute_preload_20260611_for_20260612__"
                    "market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
                ),
                "n4_context_run_id": "trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1__atomic_rule_v1",
                "updated_by": "test",
                "updated_at": "2026-07-01T18:00:00+08:00",
                "source_status_path": "docs/post_close_fastlane/20260612/00_status.json",
                "source_oneshot_report_path": "docs/post_close_fastlane/20260612/01_oneshot_execute_report.json",
            }
        ),
        encoding="utf-8",
    )
    docs_root = path.parent
    if docs_root.name == "runtime":
        docs_root = docs_root.parent
    fastlane_root = docs_root / "post_close_fastlane"
    status_dir = fastlane_root / "20260612"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "00_status.json").write_text(
        json.dumps(
            {
                "result": "EXECUTE_PASS",
                "for_trade_date": "20260612",
                "source_trade_date": "20260611",
            }
        ),
        encoding="utf-8",
    )
    latest = fastlane_root / "latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to("20260612")


def write_latest_status(docs_root: Path, *, for_trade_date: str, result: str, failed_step_id: str | None = None) -> None:
    fastlane_root = docs_root / "post_close_fastlane"
    status_dir = fastlane_root / for_trade_date
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "00_status.json").write_text(
        json.dumps(
            {
                "result": result,
                "failed_step_id": failed_step_id,
                "for_trade_date": for_trade_date,
                "source_trade_date": "20260611",
            }
        ),
        encoding="utf-8",
    )
    latest = fastlane_root / "latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(for_trade_date)


def live_subscription_summary() -> dict[str, object]:
    return {
        "source": "live_subscription_counts",
        "source_run_id": SUBSCRIPTION_RUN_ID,
        "snapshot_object_count_by_asset_kind": {"stock": 1872, "index": 83, "board": 127},
        "today_minute_object_count_by_asset_kind": {"stock": 250, "index": 19, "board": 14},
    }


def write_mock_n3p_rollback_from_argv(argv: list[str]) -> Path:
    rollback_path = Path(argv[argv.index("--rollback-sql-path") + 1])
    contract_path = Path(argv[argv.index("--contract-path") + 1])
    target_run_id = json.loads(contract_path.read_text(encoding="utf-8"))["target_run_id"]
    rollback_path.parent.mkdir(parents=True, exist_ok=True)
    rollback_path.write_text(
        f"-- scoped rollback for {target_run_id}\n"
        f"DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = '{target_run_id}';\n"
        f"DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = '{target_run_id}';\n"
        f"DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = '{target_run_id}';\n"
        f"DELETE FROM common_market_data_quality_item WHERE run_id = '{target_run_id}';\n"
        f"DELETE FROM common_market_data_run WHERE run_id = '{target_run_id}';\n"
        "-- guards: delivering delivered common_event_inbox common_event_consumer_checkpoint "
        "common_trigger_run common_action_run user sim\n",
        encoding="utf-8",
    )
    return rollback_path


def hint_source_idempotent_noop_payload(*, hhmm: str = "1044") -> dict[str, object]:
    target_run_id = proof_poller.hint_target_run_id(
        "20260611",
        SUBSCRIPTION_RUN_ID,
        hhmm,
        hint_proof_kind=proof_poller.MIDDAY_BRIDGE_HINT_PROOF_KIND,
    )
    return {
        "result": proof_poller.HINT_SOURCE_IDEMPOTENT_NOOP_RESULT,
        "status": "noop",
        "execution_mode": "noop",
        "idempotency_decision": "idempotent_pass",
        "reason": proof_poller.HINT_SOURCE_IDEMPOTENT_NOOP_REASON,
        "for_trade_date": "20260611",
        "actual_until_hhmm": hhmm,
        "proof_input_time": f"2026-06-11T{hhmm[:2]}:{hhmm[2:]}:00+08:00",
        "hint_proof_kind": proof_poller.MIDDAY_BRIDGE_HINT_PROOF_KIND,
        "proof_kind": proof_poller.MIDDAY_BRIDGE_HINT_PROOF_KIND,
        "subscription_run_id": SUBSCRIPTION_RUN_ID,
        "target_run_id": target_run_id,
        "source_artifact_path": (
            f"docs/intraday_live_current/20260611/"
            f"N3_hint_index_board_1m_{hhmm}_midday_bridge_frequency8_payload.json"
        ),
        "source_report_path": (
            f"docs/intraday_live_current/20260611/"
            f"N3_hint_index_board_1m_{hhmm}_midday_bridge_frequency8_fetch_report.json"
        ),
        "payload_hash": "a" * 64,
        "source_payload_hash": "a" * 64,
        "source_artifact_file_sha256": "b" * 64,
        "candidate_payload_hash": "c" * 64,
        "candidate_differs_from_persisted": True,
        "downstream_refs": {"n4_refs": 3, "n5_refs": 3},
        "artifact_written": False,
        "artifact_reused": True,
        "market_data_pulled": True,
        "database_written": False,
        "execute_contract_ready": True,
        "idempotent_target_execute_contract_ready": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "updates_inbox_or_checkpoint": False,
        "starts_worker": False,
        "touches_n4_n5_n6": False,
        "real_runner_wired": True,
        "layer_runner_called": True,
    }


def n3p_preflight_idempotent_noop_payload(*, hhmm: str = "1046", source_hash: str = "n3p-hash") -> dict[str, object]:
    source_run_id = proof_poller.n3p_source_payload_run_id("20260611", hhmm)
    target_run_id = proof_poller.n3p_target_run_id("20260611", SUBSCRIPTION_RUN_ID, hhmm)
    target_checks = {
        "run_count_one": True,
        "run_exists": True,
        "run_status_passed": True,
        "run_p0_zero": True,
        "run_scope_count_matches": True,
        "run_candidate_count_matches": True,
        "run_subscription_row_count_matches": True,
        "run_subscription_object_count_matches": True,
        "ready_count_contract": True,
        "quality_present": True,
        "quality_all_accepted": True,
        "quality_p0_failed_zero": True,
        "outbox_zero": True,
        "inbox_zero": True,
        "checkpoint_zero": True,
    }
    for asset in ("stock", "index", "board"):
        target_checks.update(
            {
                f"{asset}_row_count_matches": True,
                f"{asset}_ready_count_matches": True,
                f"{asset}_not_ready_count_matches": True,
            }
        )
    target_checks.update(
        {
            "stock_source_run_matches": True,
            "stock_subscription_matches": True,
            "stock_minute_matches": True,
        }
    )
    return {
        "result": proof_poller.N3P_PREFLIGHT_IDEMPOTENT_NOOP_RESULT,
        "status": "noop",
        "execution_mode": "noop",
        "idempotency_decision": "idempotent_pass",
        "reason": proof_poller.N3P_PREFLIGHT_IDEMPOTENT_NOOP_REASON,
        "target_idempotency": {
            "decision": "idempotent_pass",
            "reason": proof_poller.N3P_PREFLIGHT_IDEMPOTENT_NOOP_REASON,
            "checks": target_checks,
            "expected_by_asset": {"stock": 1, "index": 0, "board": 0},
        },
        "target_run_id": target_run_id,
        "source_payload_run_id": source_run_id,
        "source_payload_hash": source_hash,
        "actual_until_hhmm": hhmm,
        "preflight_artifacts_materialized": False,
        "execute_contract_ready": False,
        "market_data_pulled": False,
        "database_written": False,
        "writes_n3p_metric_rows": False,
        "writes_outbox": False,
        "not_n5_final_proof": True,
        "action_confirmation_ready": False,
    }


class N3IntradayAutoPollActivationTest(unittest.TestCase):
    def test_proof_poller_uses_enabled_lineage_config_over_stale_cli_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "current_intraday_worker_lineage.json"
            write_lineage_config(config_path)

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260701",
                source_trade_date="20260630",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                lineage_config_path=str(config_path),
            )

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["lineage_config_used"])
        self.assertEqual(report["effective_for_trade_date"], "20260612")
        self.assertEqual(report["effective_source_trade_date"], "20260611")
        self.assertEqual(report["for_trade_date"], "20260612")
        self.assertEqual(report["source_condition_run_id"], "condition_layer_20260611_source_20260611_for_20260612_v1")
        self.assertIn("20260612", json.dumps(report["planned_child_steps"]))
        self.assertNotIn("20260701", json.dumps(report["planned_child_steps"]))

    def test_proof_poller_blocks_missing_lineage_config_without_stale_fallback(self) -> None:
        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260701",
            source_trade_date="20260630",
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            lineage_config_path="/tmp/missing-current-intraday-worker-lineage.json",
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_INTRADAY_WORKER_LINEAGE_CONFIG")
        self.assertFalse(report["lineage_config_used"])
        self.assertEqual(report["executed_child_command_count"], 0)

    def test_proof_poller_blocks_stale_lineage_when_latest_attempt_is_newer_and_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            config_path = docs_root / "runtime" / "current_intraday_worker_lineage.json"
            write_lineage_config(config_path)
            write_latest_status(
                docs_root,
                for_trade_date="20260613",
                result="PARTIAL_BLOCKED",
                failed_step_id="worker_launchd_guard",
            )

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260701",
                source_trade_date="20260630",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                lineage_config_path=str(config_path),
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_INTRADAY_WORKER_LINEAGE_CONFIG")
        self.assertFalse(report["lineage_config_used"])
        self.assertEqual(report["executed_child_command_count"], 0)
        self.assertIn("BLOCKED_STALE_INTRADAY_WORKER_LINEAGE", report["lineage_config_error"])
        self.assertIn("active_for_trade_date=20260612", report["lineage_config_error"])
        self.assertIn("latest_attempted_for_trade_date=20260613", report["lineage_config_error"])
        self.assertIn("latest_result=PARTIAL_BLOCKED", report["lineage_config_error"])
        self.assertIn("latest_failed_step_id=worker_launchd_guard", report["lineage_config_error"])

    def test_proof_poller_blocks_when_latest_attempt_pointer_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            config_path = docs_root / "runtime" / "current_intraday_worker_lineage.json"
            write_lineage_config(config_path)
            (docs_root / "post_close_fastlane" / "latest").unlink()

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260701",
                source_trade_date="20260630",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                lineage_config_path=str(config_path),
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_INTRADAY_WORKER_LINEAGE_CONFIG")
        self.assertIn("latest attempted Fast Lane pointer missing", report["lineage_config_error"])
        self.assertEqual(report["executed_child_command_count"], 0)

    def test_proof_poller_blocks_when_latest_attempt_status_is_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            config_path = docs_root / "runtime" / "current_intraday_worker_lineage.json"
            write_lineage_config(config_path)
            status_path = docs_root / "post_close_fastlane" / "20260612" / "00_status.json"
            status_path.write_text("{malformed", encoding="utf-8")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260701",
                source_trade_date="20260630",
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                lineage_config_path=str(config_path),
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_INTRADAY_WORKER_LINEAGE_CONFIG")
        self.assertIn("latest attempted Fast Lane status missing or malformed", report["lineage_config_error"])
        self.assertEqual(report["executed_child_command_count"], 0)

    def test_proof_poller_plan_only_builds_n3_only_child_sequence_without_side_effects(self) -> None:
        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["execution_mode"], "plan_only")
        self.assertEqual(report["selected_candidate_minute"], "from_source_returned_time")
        self.assertEqual(report["target_run_id_preview"]["ordinary_hhmm"], "{actual_hhmm}")
        self.assertEqual(report["target_run_id_preview"]["hint_hhmm"], "{actual_hhmm}")
        self.assertEqual(
            [step["step_id"] for step in report["planned_child_steps"]],
            [
                "n3p_current_source_fetch",
                "n3p_trigger_proof_preflight",
                "n3p_trigger_proof_execute",
                "n3_hint_source_fetch",
                "n3_hint_proof_preflight",
                "n3_hint_proof_execute",
            ],
        )
        child_argvs = [step["argv"] for step in report["planned_child_steps"]]
        self.assertTrue(child_argvs)
        self.assertTrue(all(argv[0] == EXPECTED_PYTHON for argv in child_argvs))
        self.assertTrue(all(argv[0] != "python3" for argv in child_argvs))
        argv_blob = json.dumps(report["planned_child_steps"], sort_keys=True)
        self.assertNotIn("run_n4", argv_blob)
        self.assertNotIn("run_n5", argv_blob)
        self.assertNotIn("run_n6", argv_blob)
        self.assertNotIn("common_event_outbox", argv_blob)
        self.assertNotIn("common_event_inbox", argv_blob)
        self.assertNotIn("common_event_consumer_checkpoint", argv_blob)
        hint_source_step = next(
            step for step in report["planned_child_steps"] if step["step_id"] == "n3_hint_source_fetch"
        )
        hint_source_report_index = hint_source_step["argv"].index("--json-report-path") + 1
        self.assertEqual(
            hint_source_step["argv"][hint_source_report_index],
            "tmp/N3_hint_20260611_source_returned_source_child_report.json",
        )
        self.assertNotIn("docs/intraday_live_current", hint_source_step["argv"][hint_source_report_index])
        self.assertEqual(report["executed_child_command_count"], 0)
        self.assertTrue(all(value is False for value in report["side_effects"].values()))

    def test_proof_poller_execute_requires_user_confirmed(self) -> None:
        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=False,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "n3_proof_poller_execute_requires_user_confirmed")
        self.assertEqual(report["executed_child_command_count"], 0)
        self.assertTrue(all(value is False for value in report["side_effects"].values()))

    def test_proof_poller_future_for_trade_date_noops_before_source_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            report_path = Path("tmp/N3_intraday_proof_poller_future_date_noop.json")
            calls: list[list[str]] = []

            with mock.patch.object(
                proof_poller,
                "_current_session_observation",
                return_value={
                    "observed_local_date": "20260701",
                    "observed_local_time": "21:55:27",
                    "observed_local_datetime": "2026-07-01T21:55:27+08:00",
                },
            ):
                report = proof_poller.run_proof_poller_once(
                    for_trade_date="20260702",
                    source_trade_date="20260701",
                    source_condition_run_id="condition_layer_20260701_source_20260701_for_20260702_v1",
                    subscription_run_id=(
                        "market_data_subscription_20260702_condition_layer_20260701_source_20260701_for_20260702_v1"
                    ),
                    preload_run_id=(
                        "previous_day_minute_preload_20260701_for_20260702__"
                        "market_data_subscription_20260702_condition_layer_20260701_source_20260701_for_20260702_v1"
                    ),
                    n4_context_run_id=(
                        "trigger_context_snapshot_20260702_condition_layer_20260701_source_20260701_for_20260702_v1__atomic_rule_v1"
                    ),
                    execute=True,
                    user_confirmed=True,
                    command_runner=lambda argv: calls.append(argv) or self.fail("future-date noop must not execute children"),
                    json_report_path=str(report_path),
                )

            self.assertEqual(report["status"], "noop")
            self.assertEqual(report["reason"], "noop_for_trade_date_not_current_session")
            self.assertEqual(report["execution_mode"], "noop")
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertEqual(report["planned_child_steps"], [])
            self.assertEqual(report["executed_child_steps"], [])
            self.assertEqual(calls, [])
            self.assertTrue(all(value is False for value in report["side_effects"].values()))
            self.assertEqual(report["session_guard"]["session_guard_reason"], "for_trade_date_after_observed_local_date")
            self.assertEqual(report["session_guard"]["effective_for_trade_date"], "20260702")
            self.assertEqual(report["session_guard"]["observed_local_date"], "20260701")
            self.assertEqual(report["session_guard"]["observed_local_time"], "21:55:27")
            written = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(written["status"], "noop")
        self.assertEqual(written["reason"], "noop_for_trade_date_not_current_session")
        self.assertEqual(written["executed_child_command_count"], 0)
        self.assertEqual(written["planned_child_steps"], [])
        self.assertEqual(written["executed_child_steps"], [])
        self.assertTrue(all(value is False for value in written["side_effects"].values()))

    def test_proof_poller_hint_same_date_pre_session_noops_before_source_fetch(self) -> None:
        calls: list[list[str]] = []

        with mock.patch.object(
            proof_poller,
            "_current_session_observation",
            return_value={
                "observed_local_date": "20260703",
                "observed_local_time": "02:08:26",
                "observed_local_datetime": "2026-07-03T02:08:26+08:00",
            },
        ):
            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260703",
                source_trade_date="20260702",
                source_condition_run_id="condition_layer_20260702_source_20260702_for_20260703_v1",
                subscription_run_id=(
                    "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
                ),
                preload_run_id=(
                    "previous_day_minute_preload_20260702_for_20260703__"
                    "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
                ),
                n4_context_run_id=(
                    "trigger_context_snapshot_20260703_condition_layer_20260702_source_20260702_for_20260703_v1__atomic_rule_v1"
                ),
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: calls.append(argv) or self.fail("pre-session HINT must not execute children"),
                branch_mode="hint_only",
            )

        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["reason"], "non_trading_session_source_fetch_noop")
        self.assertEqual(report["execution_mode"], "noop")
        self.assertEqual(report["branch_mode"], "hint_only")
        self.assertEqual(report["executed_child_command_count"], 0)
        self.assertEqual(report["planned_child_steps"], [])
        self.assertEqual(report["executed_child_steps"], [])
        self.assertEqual(calls, [])
        self.assertEqual(report["source_fetch_session_guard"]["source_fetch_session_reason"], "before_source_fetch_window")
        self.assertEqual(report["source_fetch_session_guard"]["source_fetch_window_start_hhmm"], "0925")
        self.assertTrue(all(value is False for value in report["side_effects"].values()))

    def test_proof_poller_n3p_same_date_pre_session_noops_before_source_fetch(self) -> None:
        calls: list[list[str]] = []

        with mock.patch.object(
            proof_poller,
            "_current_session_observation",
            return_value={
                "observed_local_date": "20260703",
                "observed_local_time": "02:08:26",
                "observed_local_datetime": "2026-07-03T02:08:26+08:00",
            },
        ):
            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260703",
                source_trade_date="20260702",
                source_condition_run_id="condition_layer_20260702_source_20260702_for_20260703_v1",
                subscription_run_id=(
                    "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
                ),
                preload_run_id=(
                    "previous_day_minute_preload_20260702_for_20260703__"
                    "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
                ),
                n4_context_run_id=(
                    "trigger_context_snapshot_20260703_condition_layer_20260702_source_20260702_for_20260703_v1__atomic_rule_v1"
                ),
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: calls.append(argv) or self.fail("pre-session N3P must not execute children"),
                post_close_noop_checker=lambda context: self.fail("pre-session N3P must not run post-close DB checker"),
                branch_mode="n3p_only",
            )

        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["reason"], "non_trading_session_source_fetch_noop")
        self.assertEqual(report["execution_mode"], "noop")
        self.assertEqual(report["branch_mode"], "n3p_only")
        self.assertEqual(report["executed_child_command_count"], 0)
        self.assertEqual(report["planned_child_steps"], [])
        self.assertEqual(report["executed_child_steps"], [])
        self.assertEqual(calls, [])
        self.assertEqual(report["source_fetch_session_guard"]["source_fetch_session_reason"], "before_source_fetch_window")
        self.assertEqual(report["source_fetch_session_guard"]["source_fetch_window_start_hhmm"], "0925")
        self.assertTrue(all(value is False for value in report["side_effects"].values()))

    def test_proof_poller_0924_same_date_still_noops_before_source_fetch(self) -> None:
        calls: list[list[str]] = []

        with mock.patch.object(
            proof_poller,
            "_current_session_observation",
            return_value={
                "observed_local_date": "20260703",
                "observed_local_time": "09:24:59",
                "observed_local_datetime": "2026-07-03T09:24:59+08:00",
            },
        ):
            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260703",
                source_trade_date="20260702",
                source_condition_run_id="condition_layer_20260702_source_20260702_for_20260703_v1",
                subscription_run_id=(
                    "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
                ),
                preload_run_id=(
                    "previous_day_minute_preload_20260702_for_20260703__"
                    "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
                ),
                n4_context_run_id=(
                    "trigger_context_snapshot_20260703_condition_layer_20260702_source_20260702_for_20260703_v1__atomic_rule_v1"
                ),
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: calls.append(argv) or self.fail("09:24 must not execute source-fetch children"),
                branch_mode="hint_only",
            )

        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["reason"], "non_trading_session_source_fetch_noop")
        self.assertEqual(report["executed_child_command_count"], 0)
        self.assertEqual(report["source_fetch_session_guard"]["observed_hhmm"], "0924")
        self.assertEqual(report["source_fetch_session_guard"]["source_fetch_session_reason"], "before_source_fetch_window")
        self.assertEqual(report["source_fetch_session_guard"]["source_fetch_window_start_hhmm"], "0925")
        self.assertEqual(calls, [])

    def test_proof_poller_same_date_source_window_still_executes_source_fetch_contract(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            return {
                "returncode": 2,
                "json": {
                    "result": "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID",
                    "reason": "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID:hint_source_rows_missing",
                    "database_written": False,
                    "writes_outbox": False,
                },
            }

        with mock.patch.object(
            proof_poller,
            "_current_session_observation",
            return_value={
                "observed_local_date": "20260703",
                "observed_local_time": "09:25:00",
                "observed_local_datetime": "2026-07-03T09:25:00+08:00",
            },
        ):
            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260703",
                source_trade_date="20260702",
                source_condition_run_id="condition_layer_20260702_source_20260702_for_20260703_v1",
                subscription_run_id=(
                    "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
                ),
                preload_run_id=(
                    "previous_day_minute_preload_20260702_for_20260703__"
                    "market_data_subscription_20260703_condition_layer_20260702_source_20260702_for_20260703_v1"
                ),
                n4_context_run_id=(
                    "trigger_context_snapshot_20260703_condition_layer_20260702_source_20260702_for_20260703_v1__atomic_rule_v1"
                ),
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                branch_mode="hint_only",
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "child_step_failed:n3_hint_source_fetch")
        self.assertEqual(report["executed_child_command_count"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["source_fetch_session_guard"]["observed_hhmm"], "0925")
        self.assertEqual(report["source_fetch_session_guard"]["source_fetch_window_start_hhmm"], "0925")
        self.assertEqual(report["source_fetch_session_guard"]["source_fetch_session_reason"], "source_fetch_window_open")

    def test_proof_poller_malformed_for_trade_date_blocks_before_source_fetch(self) -> None:
        calls: list[list[str]] = []

        with mock.patch.object(
            proof_poller,
            "_current_session_observation",
            return_value={
                "observed_local_date": "20260701",
                "observed_local_time": "09:31:00",
                "observed_local_datetime": "2026-07-01T09:31:00+08:00",
            },
        ):
            report = proof_poller.run_proof_poller_once(
                for_trade_date="bad-date",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: calls.append(argv) or self.fail("malformed date must not execute children"),
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3_PROOF_POLLER_SESSION_GUARD")
        self.assertEqual(report["session_guard"]["session_guard_reason"], "invalid_effective_for_trade_date")
        self.assertEqual(report["executed_child_command_count"], 0)
        self.assertEqual(report["planned_child_steps"], [])
        self.assertEqual(calls, [])
        self.assertTrue(all(value is False for value in report["side_effects"].values()))

    def test_proof_poller_session_observation_failure_blocks_before_source_fetch(self) -> None:
        calls: list[list[str]] = []

        with mock.patch.object(
            proof_poller,
            "_current_session_observation",
            side_effect=RuntimeError("clock unavailable"),
        ):
            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260701",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: calls.append(argv) or self.fail("session guard failure must not execute children"),
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3_PROOF_POLLER_SESSION_GUARD")
        self.assertEqual(report["session_guard"]["session_guard_reason"], "session_observation_failed")
        self.assertEqual(report["executed_child_command_count"], 0)
        self.assertEqual(report["planned_child_steps"], [])
        self.assertEqual(calls, [])
        self.assertTrue(all(value is False for value in report["side_effects"].values()))

    def test_proof_poller_current_for_trade_date_still_reaches_source_fetch(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            return {
                "returncode": 2,
                "json": {
                    "result": "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION",
                    "reason": "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION:dirty_target_payload_hash_mismatch",
                    "actual_until_hhmm": "1453",
                    "database_written": False,
                    "writes_outbox": False,
                },
            }

        with mock.patch.object(
            proof_poller,
            "_current_session_observation",
            return_value={
                "observed_local_date": "20260701",
                "observed_local_time": "14:53:00",
                "observed_local_datetime": "2026-07-01T14:53:00+08:00",
            },
        ):
            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260701",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                post_close_noop_checker=lambda context: {
                    "post_close_noop": False,
                    "noop_reason": "canonical_time_not_close",
                    "actual_hhmm": "1453",
                },
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "child_step_failed:n3p_current_source_fetch")
        self.assertEqual(report["executed_child_command_count"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["session_guard"]["session_guard_reason"], "for_trade_date_is_observed_local_date")

    def test_proof_poller_post_close_existing_1500_source_and_proof_noops_before_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            report_path = Path("tmp/N3_intraday_proof_poller_post_close_noop.json")
            calls: list[list[str]] = []
            existing_source = "n3p_mixed_realtime_source_payload_20260701_until_1500_v1"
            existing_target = proof_poller.n3p_target_run_id("20260701", SUBSCRIPTION_RUN_ID, "1500")

            def post_close_noop_checker(context: dict[str, object]) -> dict[str, object]:
                self.assertEqual(context["for_trade_date"], "20260701")
                self.assertEqual(context["subscription_run_id"], SUBSCRIPTION_RUN_ID)
                return {
                    "post_close_noop": True,
                    "noop_reason": "existing_1500_source_and_proof_passed",
                    "actual_hhmm": "1500",
                    "existing_source_run_id": existing_source,
                    "existing_n3p_target_run_id": existing_target,
                    "source_status": "passed",
                    "proof_status": "passed",
                }

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260701",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=lambda argv: calls.append(argv) or self.fail("post-close no-op must not execute children"),
                post_close_noop_checker=post_close_noop_checker,
                json_report_path=str(report_path),
            )

            self.assertEqual(report["status"], "noop")
            self.assertEqual(report["reason"], "noop_existing_close_proof_passed")
            self.assertTrue(report["post_close_noop"])
            self.assertEqual(report["noop_reason"], "existing_1500_source_and_proof_passed")
            self.assertEqual(report["existing_n3p_source_run_id"], existing_source)
            self.assertEqual(report["existing_n3p_target_run_id"], existing_target)
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertEqual(calls, [])
            self.assertTrue(all(value is False for value in report["side_effects"].values()))
            written = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(written["status"], "noop")
        self.assertTrue(written["post_close_noop"])
        self.assertEqual(written["executed_child_command_count"], 0)
        self.assertEqual(written["actual_hhmm_handoff"]["n3p"]["actual_hhmm"], "1500")
        self.assertEqual(written["executed_child_steps"], [])

    def test_proof_poller_does_not_post_close_noop_when_1500_proof_missing(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            return {
                "returncode": 2,
                "json": {
                    "result": "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION",
                    "reason": "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION:dirty_target_payload_hash_mismatch",
                    "actual_until_hhmm": "1500",
                    "database_written": False,
                    "writes_outbox": False,
                },
            }

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260701",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            command_runner=runner,
            post_close_noop_checker=lambda context: {
                "post_close_noop": False,
                "noop_reason": "existing_1500_proof_missing",
                "existing_source_run_id": "n3p_mixed_realtime_source_payload_20260701_until_1500_v1",
                "source_status": "passed",
                "proof_status": "",
            },
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "child_step_failed:n3p_current_source_fetch")
        self.assertEqual(report["executed_child_command_count"], 1)
        self.assertEqual(len(calls), 1)
        self.assertFalse(report["post_close_noop_check"]["post_close_noop"])

    def test_proof_poller_active_session_same_hhmm_different_hash_still_blocks(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            return {
                "returncode": 2,
                "json": {
                    "result": "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION",
                    "reason": "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION:dirty_target_payload_hash_mismatch",
                    "actual_until_hhmm": "1453",
                    "expected_payload_hash": "candidate-hash",
                    "observed_payload_hash": "existing-hash",
                    "database_written": False,
                    "writes_outbox": False,
                },
            }

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260701",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            command_runner=runner,
            post_close_noop_checker=lambda context: {
                "post_close_noop": False,
                "noop_reason": "canonical_time_not_close",
                "actual_hhmm": "1453",
            },
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "child_step_failed:n3p_current_source_fetch")
        self.assertEqual(report["executed_child_command_count"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["blocked_child_result"]["reason"], "BLOCKED_N3P_SOURCE_FETCH_BACKEND_REGISTRATION:dirty_target_payload_hash_mismatch")

    def test_resolve_readonly_dsn_ignores_launchd_placeholder_env(self) -> None:
        with mock.patch.dict(
            proof_poller.os.environ,
            {
                "ASHARE_V3_POSTGRES_DSN": "__ASHARE_V3_POSTGRES_DSN__",
                "DATABASE_URL": "postgresql://fallback.example/db",
            },
            clear=True,
        ):
            dsn = proof_poller._resolve_readonly_dsn()

        self.assertEqual(dsn, "postgresql://fallback.example/db")

    def test_post_close_noop_checker_never_passes_placeholder_dsn_to_db_check(self) -> None:
        with mock.patch.dict(
            proof_poller.os.environ,
            {
                "ASHARE_V3_POSTGRES_DSN": "__ASHARE_V3_POSTGRES_DSN__",
                "DATABASE_URL": "postgresql://fallback.example/db",
            },
            clear=True,
        ):
            with mock.patch.object(proof_poller, "_is_today_trade_date", return_value=True):
                with mock.patch.object(proof_poller, "_current_local_canonical_hhmm", return_value="1500"):
                    with mock.patch.object(
                        proof_poller,
                        "_read_market_data_run_statuses",
                        return_value=("passed", "passed"),
                    ) as read_statuses:
                        result = proof_poller._default_post_close_noop_checker(
                            {
                                "for_trade_date": "20260701",
                                "expected_source_run_id": "n3p_mixed_realtime_source_payload_20260701_until_1500_v1",
                                "expected_n3p_target_run_id": "realtime_action_confirmation_metric_20260701_until_1500__x",
                            }
                        )

        self.assertTrue(result["post_close_noop"])
        self.assertEqual(read_statuses.call_args.kwargs["dsn"], "postgresql://fallback.example/db")
        self.assertNotEqual(read_statuses.call_args.kwargs["dsn"], "__ASHARE_V3_POSTGRES_DSN__")

    def test_proof_poller_main_returns_zero_for_passed_status(self) -> None:
        with mock.patch.object(
            proof_poller,
            "run_proof_poller_once",
            return_value={"status": "passed", "reason": ""},
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = proof_poller.main(
                    [
                        "--for-trade-date",
                        "20260611",
                        "--source-trade-date",
                        SOURCE_TRADE_DATE,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                        "--subscription-run-id",
                        SUBSCRIPTION_RUN_ID,
                        "--preload-run-id",
                        PRELOAD_RUN_ID,
                        "--n4-context-run-id",
                        N4_CONTEXT_RUN_ID,
                        "--json",
                    ]
                )

        self.assertEqual(rc, 0)

    def test_proof_poller_main_returns_nonzero_for_blocked_status(self) -> None:
        with mock.patch.object(
            proof_poller,
            "run_proof_poller_once",
            return_value={"status": "blocked", "reason": "mock_blocked"},
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                rc = proof_poller.main(
                    [
                        "--for-trade-date",
                        "20260611",
                        "--source-trade-date",
                        SOURCE_TRADE_DATE,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                        "--subscription-run-id",
                        SUBSCRIPTION_RUN_ID,
                        "--preload-run-id",
                        PRELOAD_RUN_ID,
                        "--n4-context-run-id",
                        N4_CONTEXT_RUN_ID,
                        "--json",
                    ]
                )

        self.assertNotEqual(rc, 0)

    def test_proof_poller_execute_calls_children_in_order_and_retargets_actual_hhmm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1046",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                            "payload_hash": "n3p-hash",
                            "payload_path": "docs/intraday_live_current/20260611/N3P_mixed_realtime_1046_source_fetch_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                        },
                    }
                if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                    rollback_path = write_mock_n3p_rollback_from_argv(argv)
                    self.assertEqual(
                        str(rollback_path),
                        "sql/N3P_20260611_1046_trigger_proof_rollback.sql",
                    )
                    self.assertNotIn("{actual_hhmm}", str(rollback_path))
                    return {"returncode": 0, "json": {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}}
                if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1044",
                            "payload_hash": "hint-hash",
                            "source_artifact_path": "docs/intraday_live_current/20260611/N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3_hint_index_board_1m_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    proof_kind = argv[argv.index("--hint-proof-kind") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(
                        json.dumps({"target_run_id": target_run_id, "proof_kind": proof_kind}),
                        encoding="utf-8",
                    )
                    preflight_path.write_text(
                        json.dumps({"target_run_id": target_run_id, "proof_kind": proof_kind}),
                        encoding="utf-8",
                    )
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                            "proof_kind": proof_kind,
                        },
                    }
                return {"returncode": 0, "json": {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}}

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["executed_child_command_count"], 6)
        self.assertEqual(
            [step["step_id"] for step in report["executed_child_steps"]],
            [
                "n3p_current_source_fetch",
                "n3p_trigger_proof_preflight",
                "n3p_trigger_proof_execute",
                "n3_hint_source_fetch",
                "n3_hint_proof_preflight",
                "n3_hint_proof_execute",
            ],
        )
        argv_blob = json.dumps(calls, sort_keys=True)
        self.assertNotIn("{actual_hhmm}", argv_blob)
        self.assertIn("n3p_mixed_realtime_source_payload_20260611_until_1046_v1", argv_blob)
        self.assertIn("realtime_action_confirmation_metric_20260611_until_1046", argv_blob)
        self.assertIn("N3P_mixed_realtime_1046_source_fetch_payload.json", argv_blob)
        self.assertIn("realtime_hint_projection_metric_20260611_until_1044", argv_blob)
        self.assertIn("N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json", argv_blob)
        self.assertNotIn("run_n4", argv_blob)
        self.assertNotIn("run_n5", argv_blob)
        self.assertNotIn("run_n6", argv_blob)
        self.assertNotIn("common_event_outbox", argv_blob)
        self.assertNotIn("common_event_inbox", argv_blob)
        self.assertNotIn("common_event_consumer_checkpoint", argv_blob)
        self.assertNotIn("launchctl", argv_blob)
        self.assertNotIn("rollback-execute", argv_blob.lower())
        self.assertNotIn("schema", argv_blob.lower())
        n3p_execute_argv = next(argv for argv in calls if argv[1].endswith("run_v3_realtime_virtual_metric_writer_once.py"))
        self.assertIn("--json-report-path", n3p_execute_argv)
        self.assertIn("--rollback-sql-path", n3p_execute_argv)
        self.assertNotIn("--output-path", n3p_execute_argv)
        hint_source_argv = next(
            argv for argv in calls if argv[1].endswith("run_n3_hint_index_board_1m_source_fetch_once.py")
        )
        hint_source_report_index = hint_source_argv.index("--json-report-path") + 1
        self.assertEqual(
            hint_source_argv[hint_source_report_index],
            "tmp/N3_hint_20260611_source_returned_source_child_report.json",
        )
        self.assertNotIn("docs/intraday_live_current", hint_source_argv[hint_source_report_index])

    def test_proof_poller_n3p_only_branch_does_not_build_hint_steps(self) -> None:
        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            branch_mode="n3p_only",
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["branch_mode"], "n3p_only")
        self.assertEqual(report["n3p_status"], "planned")
        self.assertEqual(report["hint_status"], "skipped")
        self.assertEqual(report["skipped_branch_reason"]["hint"], "branch_mode_n3p_only")
        self.assertEqual(
            [step["step_id"] for step in report["planned_child_steps"]],
            [
                "n3p_current_source_fetch",
                "n3p_trigger_proof_preflight",
                "n3p_trigger_proof_execute",
            ],
        )
        self.assertNotIn("n3_hint", json.dumps(report["planned_child_steps"], sort_keys=True))

    def test_proof_poller_n3p_only_execute_does_not_run_hint_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1046",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                            "payload_hash": "n3p-hash",
                            "payload_path": "docs/intraday_live_current/20260611/N3P_mixed_realtime_1046_source_fetch_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                        },
                    }
                if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                    write_mock_n3p_rollback_from_argv(argv)
                    return {"returncode": 0, "json": {"result": "EXECUTE_PASS"}}
                self.fail("HINT children must not run in n3p_only branch")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                branch_mode="n3p_only",
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["branch_mode"], "n3p_only")
        self.assertEqual(report["n3p_status"], "passed")
        self.assertEqual(report["hint_status"], "skipped")
        self.assertEqual(report["n3p_actual_hhmm"], "1046")
        self.assertIn("realtime_action_confirmation_metric_20260611_until_1046", report["n3p_target_run_id"])
        self.assertEqual(report["executed_child_command_count"], 3)
        self.assertEqual(
            [step["step_id"] for step in report["executed_child_steps"]],
            [
                "n3p_current_source_fetch",
                "n3p_trigger_proof_preflight",
                "n3p_trigger_proof_execute",
            ],
        )
        timing = report["timing"]
        self.assertEqual(timing["branch_mode"], "n3p_only")
        self.assertGreaterEqual(timing["total_duration_ms"], 0)
        phase_names = [phase["phase_name"] for phase in timing["phases"]]
        self.assertIn("n3p_current_source_fetch", phase_names)
        self.assertIn("n3p_trigger_proof_preflight", phase_names)
        self.assertIn("n3p_trigger_proof_execute", phase_names)
        for phase in timing["phases"]:
            self.assertGreaterEqual(phase["duration_ms"], 0)
        for step in report["executed_child_steps"]:
            self.assertIn("child_started_at", step)
            self.assertIn("child_finished_at", step)
            self.assertGreaterEqual(step["child_duration_ms"], 0)
        self.assertNotIn("run_n3_hint", json.dumps(calls, sort_keys=True))

    def test_proof_poller_hint_only_execute_does_not_run_n3p_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1044",
                            "payload_hash": "hint-hash",
                            "source_artifact_path": "docs/intraday_live_current/20260611/N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3_hint_index_board_1m_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    proof_kind = argv[argv.index("--hint-proof-kind") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(
                        json.dumps({"target_run_id": target_run_id, "proof_kind": proof_kind}),
                        encoding="utf-8",
                    )
                    preflight_path.write_text(
                        json.dumps({"target_run_id": target_run_id, "proof_kind": proof_kind}),
                        encoding="utf-8",
                    )
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                            "proof_kind": proof_kind,
                        },
                    }
                if runner_path.endswith("run_n3_hint_index_board_1m_proof_execute_once.py"):
                    return {"returncode": 0, "json": {"result": "EXECUTE_PASS"}}
                self.fail("N3P children must not run in hint_only branch")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                branch_mode="hint_only",
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["branch_mode"], "hint_only")
        self.assertEqual(report["n3p_status"], "skipped")
        self.assertEqual(report["hint_status"], "passed")
        self.assertEqual(report["hint_actual_hhmm"], "1044")
        self.assertIn("realtime_hint_projection_metric_20260611_until_1044", report["hint_target_run_id"])
        self.assertEqual(report["executed_child_command_count"], 3)
        self.assertEqual(
            [step["step_id"] for step in report["executed_child_steps"]],
            [
                "n3_hint_source_fetch",
                "n3_hint_proof_preflight",
                "n3_hint_proof_execute",
            ],
        )
        timing = report["timing"]
        self.assertEqual(timing["branch_mode"], "hint_only")
        phase_names = [phase["phase_name"] for phase in timing["phases"]]
        self.assertIn("n3_hint_source_fetch", phase_names)
        self.assertIn("n3_hint_proof_preflight", phase_names)
        self.assertIn("n3_hint_proof_execute", phase_names)
        self.assertNotIn("n3p_current_source_fetch", phase_names)
        for step in report["executed_child_steps"]:
            self.assertGreaterEqual(step["child_duration_ms"], 0)
        self.assertNotIn("run_n3p", json.dumps(calls, sort_keys=True))
        source_argv = calls[0]
        source_report_path = source_argv[source_argv.index("--json-report-path") + 1]
        self.assertEqual(source_report_path, "tmp/N3_hint_20260611_source_returned_source_child_report.json")
        self.assertNotIn("docs/intraday_live_current", source_report_path)

    def test_proof_poller_hint_only_exact_source_noop_skips_preflight_and_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            report_path = Path("tmp/N3_intraday_proof_poller_hint_noop.json")
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                self.assertTrue(argv[1].endswith("run_n3_hint_index_board_1m_source_fetch_once.py"))
                return {"returncode": 0, "json": hint_source_idempotent_noop_payload()}

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                branch_mode="hint_only",
                json_report_path=str(report_path),
            )
            written = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["execution_mode"], "noop")
        self.assertEqual(report["reason"], "noop_existing_hint_target_passed")
        self.assertEqual(report["n3p_status"], "skipped")
        self.assertEqual(report["hint_status"], "noop")
        self.assertEqual(report["executed_child_command_count"], 1)
        self.assertEqual([step["step_id"] for step in report["executed_child_steps"]], ["n3_hint_source_fetch"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["last_successful_child"], "n3_hint_source_fetch")
        self.assertEqual(report["resolved_target_run_ids"]["hint_target_run_id"], report["hint_target_run_id"])
        self.assertEqual(report["actual_hhmm_handoff"]["hint"]["idempotency"]["status"], "passed")
        self.assertEqual(written["status"], report["status"])
        self.assertEqual(written["executed_child_command_count"], 1)
        self.assertNotIn("preflight_artifacts", written["actual_hhmm_handoff"]["hint"])
        source_argv = calls[0]
        wrapper_report_path = source_argv[source_argv.index("--json-report-path") + 1]
        self.assertEqual(wrapper_report_path, "tmp/N3_hint_20260611_source_returned_source_child_report.json")
        canonical_report_path = report["actual_hhmm_handoff"]["hint"]["source_report_path"]
        self.assertTrue(canonical_report_path.endswith("N3_hint_index_board_1m_1044_midday_bridge_frequency8_fetch_report.json"))
        self.assertNotEqual(wrapper_report_path, canonical_report_path)

    def test_proof_poller_both_preserves_n3p_success_when_hint_source_noops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1046",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                            "payload_hash": "n3p-hash",
                            "payload_path": "docs/intraday_live_current/20260611/N3P_mixed_realtime_1046_source_fetch_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                        },
                    }
                if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                    write_mock_n3p_rollback_from_argv(argv)
                    return {"returncode": 0, "json": {"result": "EXECUTE_PASS"}}
                if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    return {"returncode": 0, "json": hint_source_idempotent_noop_payload()}
                self.fail(f"unexpected child after HINT source noop: {runner_path}")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                branch_mode="both",
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["execution_mode"], "execute")
        self.assertEqual(report["n3p_status"], "passed")
        self.assertEqual(report["hint_status"], "noop")
        self.assertEqual(report["executed_child_command_count"], 4)
        self.assertEqual(
            [step["step_id"] for step in report["executed_child_steps"]],
            [
                "n3p_current_source_fetch",
                "n3p_trigger_proof_preflight",
                "n3p_trigger_proof_execute",
                "n3_hint_source_fetch",
            ],
        )
        self.assertEqual(len(calls), 4)
        self.assertIn("n3p_target_run_id", report["resolved_target_run_ids"])
        self.assertIn("hint_target_run_id", report["resolved_target_run_ids"])

    def test_proof_poller_malformed_hint_source_noop_claim_fails_closed(self) -> None:
        mutations = {
            "unknown_result": lambda payload: payload.update(result="UNKNOWN_NOOP_RESULT"),
            "target": lambda payload: payload.update(target_run_id="wrong"),
            "trade_date": lambda payload: payload.update(for_trade_date="20260612"),
            "subscription": lambda payload: payload.update(subscription_run_id="wrong"),
            "proof_kind": lambda payload: payload.update(proof_kind="wrong"),
            "payload_hash": lambda payload: payload.update(payload_hash=""),
            "hash_alias": lambda payload: payload.update(source_payload_hash="d" * 64),
            "file_sha": lambda payload: payload.update(source_artifact_file_sha256=""),
            "candidate_hash": lambda payload: payload.update(candidate_payload_hash=""),
            "artifact_written": lambda payload: payload.update(artifact_written=True),
            "artifact_reused": lambda payload: payload.update(artifact_reused=False),
            "market_data_pulled": lambda payload: payload.update(market_data_pulled=False),
            "database_written": lambda payload: payload.update(database_written=True),
            "idempotent_execute_ready": lambda payload: payload.update(idempotent_target_execute_contract_ready=True),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                calls: list[list[str]] = []
                payload = hint_source_idempotent_noop_payload()
                mutate(payload)

                def runner(argv: list[str]) -> dict[str, object]:
                    calls.append(argv)
                    return {"returncode": 0, "json": payload}

                report = proof_poller.run_proof_poller_once(
                    for_trade_date="20260611",
                    source_trade_date=SOURCE_TRADE_DATE,
                    source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                    subscription_run_id=SUBSCRIPTION_RUN_ID,
                    preload_run_id=PRELOAD_RUN_ID,
                    n4_context_run_id=N4_CONTEXT_RUN_ID,
                    execute=True,
                    user_confirmed=True,
                    command_runner=runner,
                    branch_mode="hint_only",
                )

                self.assertEqual(report["status"], "blocked")
                self.assertTrue(str(report["reason"]).startswith("hint_source_noop_handoff_invalid:"))
                self.assertEqual(report["hint_status"], "blocked")
                self.assertEqual(report["executed_child_command_count"], 1)
                self.assertEqual(len(calls), 1)

    def test_proof_poller_hint_parent_report_redacts_large_child_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            report_path = Path("tmp/N3_intraday_proof_poller_hint_redacted.json")
            large_rows = [
                {
                    "asset_kind": "board",
                    "identity_key": f"board:TDX:{881000 + idx}",
                    "minute_label": "10:01",
                    "raw_payload": {"amount": idx, "close": 1000 + idx},
                }
                for idx in range(80)
            ]

            def runner(argv: list[str]) -> dict[str, object]:
                runner_path = argv[1]
                if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    payload = {
                        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                        "actual_until_hhmm": "1044",
                        "target_run_id": "n3_hint_index_board_1m_source_payload_20260611_until_1044_v1",
                        "source_artifact_path": (
                            "docs/intraday_live_current/20260611/"
                            "N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json"
                        ),
                        "source_artifact_file_sha256": "a" * 64,
                        "source_payload_hash": "b" * 64,
                        "source_payload_counts": {"board_rows": 80, "index_rows": 0},
                        "index_board_1m_rows": large_rows,
                    }
                    return {
                        "returncode": 0,
                        "stdout": json.dumps(payload),
                        "json": payload,
                    }
                if runner_path.endswith("run_n3_hint_index_board_1m_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                            "proof_rows_total": 25,
                        },
                    }
                if runner_path.endswith("run_n3_hint_index_board_1m_proof_execute_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_PASS",
                            "target_run_id": argv[argv.index("--target-run-id") + 1],
                            "metric_ready": {"ready": 25, "not_ready": 0},
                            "rows_written": {"board": 25, "index": 0, "stock": 0},
                        },
                    }
                self.fail("N3P children must not run in hint_only branch")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                branch_mode="hint_only",
                json_report_path=str(report_path),
            )
            written = json.loads(report_path.read_text(encoding="utf-8"))

        source_step = written["executed_child_steps"][0]
        self.assertTrue(source_step["child_json_redacted"])
        self.assertIn("json.index_board_1m_rows", source_step["redacted_fields"])
        self.assertIn("stdout", source_step["redacted_fields"])
        self.assertNotIn("index_board_1m_rows", source_step["json"])
        self.assertNotIn("raw_payload", json.dumps(source_step, sort_keys=True))
        self.assertEqual(source_step["json"]["source_artifact_file_sha256"], "a" * 64)
        self.assertEqual(source_step["json"]["source_artifact_path"], report["executed_child_steps"][0]["json"]["source_artifact_path"])
        self.assertEqual(source_step["child_json_summary"]["row_counts"]["index_board_1m_rows"], 80)
        self.assertEqual(source_step["child_json_summary"]["artifact_paths"]["source_artifact_path"], source_step["json"]["source_artifact_path"])
        self.assertGreater(source_step["stdout_original_length"], 1000)
        self.assertLess(len(json.dumps(written, ensure_ascii=False)), 20000)

    def test_proof_poller_blocks_when_n3p_rollback_artifact_missing_after_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1046",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                        },
                    }
                if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                    self.assertIn("--rollback-sql-path", argv)
                    return {"returncode": 0, "json": {"result": "EXECUTE_PASS"}}
                self.fail("HINT children must not run when N3P rollback artifact is missing")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3P_ROLLBACK_ARTIFACT_MISSING")
        self.assertEqual(report["executed_child_command_count"], 3)
        self.assertEqual(len(calls), 3)

    def test_proof_poller_writes_partial_success_report_when_hint_source_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            report_path = Path("tmp/N3_intraday_proof_poller_partial.json")
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1500",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260701_until_1500_v1",
                            "payload_hash": "n3p-hash",
                            "payload_path": "docs/intraday_live_current/20260701/N3P_mixed_realtime_1500_source_fetch_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                        },
                    }
                if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                    write_mock_n3p_rollback_from_argv(argv)
                    return {"returncode": 0, "json": {"result": "EXECUTE_PASS"}}
                if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    return {
                        "returncode": 2,
                        "json": {
                            "result": "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID",
                            "reason": "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID:canonical_1130_forbidden",
                            "database_written": False,
                            "writes_outbox": False,
                        },
                    }
                self.fail("Poller must stop before HINT preflight/execute after HINT source block")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260701",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                json_report_path=str(report_path),
            )

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["reason"], "child_step_failed:n3_hint_source_fetch")
            self.assertEqual(report["executed_child_command_count"], 4)
            self.assertTrue(report_path.exists())
            written = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(written["status"], "blocked")
        self.assertEqual(written["blocked_child_step"], "n3_hint_source_fetch")
        self.assertEqual(written["last_successful_child"], "n3p_trigger_proof_execute")
        self.assertEqual(written["executed_child_command_count"], 4)
        self.assertIn("timing", written)
        self.assertGreaterEqual(written["timing"]["total_duration_ms"], 0)
        self.assertTrue(
            any(
                phase["phase_name"] == "n3_hint_source_fetch" and phase["status"] == "blocked"
                for phase in written["timing"]["phases"]
            )
        )
        self.assertEqual(
            written["actual_hhmm_handoff"]["n3p"]["source_payload_run_id"],
            "n3p_mixed_realtime_source_payload_20260701_until_1500_v1",
        )
        self.assertIn("until_1500", written["n3p_output_summary"]["target_run_id"])
        self.assertEqual(
            written["hint_not_reached_or_absent_reason"],
            "blocked_before_hint_target_execute:n3_hint_source_fetch",
        )
        argv_blob = json.dumps(calls, sort_keys=True)
        self.assertNotIn('"python3"', argv_blob)
        self.assertNotIn("{actual_hhmm}", argv_blob)
        self.assertNotIn("run_n4", argv_blob)
        self.assertNotIn("run_n5", argv_blob)
        self.assertNotIn("run_n6", argv_blob)
        self.assertNotIn("common_event_outbox", argv_blob)
        self.assertNotIn("common_event_inbox", argv_blob)
        self.assertNotIn("common_event_consumer_checkpoint", argv_blob)
        self.assertNotIn("rollback-execute", argv_blob.lower())
        self.assertNotIn("schema", argv_blob.lower())

    def test_proof_poller_retries_adjacent_n3p_source_alignment_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []
            sleep_calls: list[float] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                n3p_source_attempts = sum(1 for call in calls if call[1].endswith("run_n3p_current_source_fetch_once.py"))
                if runner_path.endswith("run_n3p_current_source_fetch_once.py") and n3p_source_attempts == 1:
                    return {
                        "returncode": 2,
                        "json": {
                            "result": "BLOCKED_N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT",
                            "reason": "mixed_canonical_proof_minute_mismatch:stock=1355:index_board=1356",
                            "alignment_failure_class": "adjacent_minute_source_boundary_race",
                            "minute_delta": 1,
                            "stock_canonical_hhmm": "1355",
                            "index_board_hhmm": "1356",
                            "artifact_written": False,
                            "source_payload_registered": False,
                            "database_written": False,
                        },
                    }
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1356",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1356_v1",
                            "payload_hash": "n3p-hash",
                            "payload_path": "docs/intraday_live_current/20260611/N3P_mixed_realtime_1356_source_fetch_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                        },
                    }
                if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                    write_mock_n3p_rollback_from_argv(argv)
                    return {"returncode": 0, "json": {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}}
                if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1356",
                            "payload_hash": "hint-hash",
                            "source_artifact_path": "docs/intraday_live_current/20260611/N3_hint_index_board_1m_1356_midday_bridge_frequency8_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3_hint_index_board_1m_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    proof_kind = argv[argv.index("--hint-proof-kind") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(
                        json.dumps({"target_run_id": target_run_id, "proof_kind": proof_kind}),
                        encoding="utf-8",
                    )
                    preflight_path.write_text(
                        json.dumps({"target_run_id": target_run_id, "proof_kind": proof_kind}),
                        encoding="utf-8",
                    )
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                            "proof_kind": proof_kind,
                        },
                    }
                return {"returncode": 0, "json": {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}}

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
                sleep_fn=sleep_calls.append,
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["executed_child_command_count"], 7)
        self.assertEqual(sleep_calls, [2])
        retry = report["n3p_source_alignment_retry"]
        self.assertEqual(retry["status"], "aligned_after_retry")
        self.assertEqual(retry["attempt_count"], 2)
        self.assertEqual(retry["attempts"][0]["alignment_failure_class"], "adjacent_minute_source_boundary_race")
        self.assertFalse(retry["attempts"][0]["artifact_written"])
        self.assertFalse(retry["attempts"][0]["source_payload_registered"])
        self.assertFalse(retry["attempts"][0]["database_written"])
        argv_blob = json.dumps(calls, sort_keys=True)
        self.assertIn("realtime_action_confirmation_metric_20260611_until_1356", argv_blob)
        self.assertNotIn("{actual_hhmm}", argv_blob)

    def test_proof_poller_blocks_after_adjacent_alignment_retry_exhaustion(self) -> None:
        calls: list[list[str]] = []
        sleep_calls: list[float] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            return {
                "returncode": 2,
                "json": {
                    "result": "BLOCKED_N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT",
                    "reason": "mixed_canonical_proof_minute_mismatch:stock=1355:index_board=1356",
                    "alignment_failure_class": "adjacent_minute_source_boundary_race",
                    "minute_delta": 1,
                    "stock_canonical_hhmm": "1355",
                    "index_board_hhmm": "1356",
                    "artifact_written": False,
                    "source_payload_registered": False,
                    "database_written": False,
                },
            }

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            command_runner=runner,
            sleep_fn=sleep_calls.append,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT_RETRY_EXHAUSTED")
        self.assertEqual(report["executed_child_command_count"], 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep_calls, [2, 2])
        self.assertEqual(report["n3p_source_alignment_retry"]["attempt_count"], 3)
        self.assertEqual(report["blocked_child_result"]["result"], "BLOCKED_N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT_RETRY_EXHAUSTED")

    def test_proof_poller_does_not_retry_non_adjacent_n3p_source_alignment(self) -> None:
        calls: list[list[str]] = []
        sleep_calls: list[float] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            return {
                "returncode": 2,
                "json": {
                    "result": "BLOCKED_N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT",
                    "alignment_failure_class": "canonical_minute_mismatch",
                    "minute_delta": 3,
                    "stock_canonical_hhmm": "1353",
                    "index_board_hhmm": "1356",
                    "artifact_written": False,
                    "source_payload_registered": False,
                    "database_written": False,
                },
            }

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            command_runner=runner,
            sleep_fn=sleep_calls.append,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "child_step_failed:n3p_current_source_fetch")
        self.assertEqual(report["executed_child_command_count"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleep_calls, [])

    def test_proof_poller_does_not_retry_midday_stock_time_stale_alignment(self) -> None:
        calls: list[list[str]] = []
        sleep_calls: list[float] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            return {
                "returncode": 2,
                "json": {
                    "result": "BLOCKED_N3P_SOURCE_MIDDAY_STOCK_TIME_STALE",
                    "reason": "BLOCKED_N3P_SOURCE_MIDDAY_STOCK_TIME_STALE:stock_quote_servertime_stale_at_midday_wait_for_alignment",
                    "alignment_failure_class": "midday_stock_quote_time_stale",
                    "minute_delta": 90,
                    "stock_canonical_hhmm": "1130",
                    "index_board_hhmm": "1300",
                    "artifact_written": False,
                    "source_payload_registered": False,
                    "database_written": False,
                    "writes_outbox": False,
                    "writes_n3p_metric_rows": False,
                },
            }

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            branch_mode="n3p_only",
            command_runner=runner,
            sleep_fn=sleep_calls.append,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "child_step_failed:n3p_current_source_fetch")
        self.assertEqual(report["branch_mode"], "n3p_only")
        self.assertEqual(report["executed_child_command_count"], 1)
        self.assertEqual(report["blocked_child_result"]["result"], "BLOCKED_N3P_SOURCE_MIDDAY_STOCK_TIME_STALE")
        self.assertEqual(report["blocked_child_result"]["stock_canonical_hhmm"], "1130")
        self.assertEqual(report["blocked_child_result"]["index_board_hhmm"], "1300")
        self.assertEqual(report["blocked_child_result"]["minute_delta"], 90)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleep_calls, [])
        argv_blob = json.dumps(calls, sort_keys=True)
        self.assertNotIn("run_n3_hint", argv_blob)
        self.assertNotIn("run_n4", argv_blob)
        self.assertNotIn("run_n5", argv_blob)
        self.assertNotIn("run_n6", argv_blob)

    def test_proof_poller_blocks_when_n3p_preflight_artifacts_are_missing(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            runner_path = argv[1]
            if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                return {
                    "returncode": 0,
                    "json": {
                        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                        "actual_until_hhmm": "1046",
                        "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                    },
                }
            if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                return {
                    "returncode": 0,
                    "json": {
                        "result": "PLAN_ONLY_PASS",
                        "contract_path": "tmp/missing_contract.json",
                        "preflight_path": "tmp/missing_preflight.json",
                        "target_run_id": argv[argv.index("--target-run-id") + 1],
                    },
                }
            self.fail("execute child must not run when preflight artifacts are missing")

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            command_runner=runner,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3P_PREFLIGHT_ARTIFACT_MISSING")
        self.assertEqual(report["executed_child_command_count"], 2)
        self.assertEqual(len(calls), 2)

    def test_proof_poller_blocks_when_n3p_preflight_artifact_target_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1046",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": "wrong_target"}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": "wrong_target"}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": argv[argv.index("--target-run-id") + 1],
                        },
                    }
                self.fail("execute child must not run when preflight artifact target mismatches")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3P_PREFLIGHT_ARTIFACT_TARGET_MISMATCH")
        self.assertEqual(report["executed_child_command_count"], 2)
        self.assertEqual(len(calls), 2)

    def test_proof_poller_blocks_when_hint_preflight_artifacts_are_missing(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            runner_path = argv[1]
            if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                return {
                    "returncode": 0,
                    "json": {
                        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                        "actual_until_hhmm": "1046",
                        "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                    },
                }
            if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                contract_path = Path(argv[argv.index("--contract-path") + 1])
                preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                target_run_id = argv[argv.index("--target-run-id") + 1]
                contract_path.parent.mkdir(parents=True, exist_ok=True)
                preflight_path.parent.mkdir(parents=True, exist_ok=True)
                contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                return {
                    "returncode": 0,
                    "json": {
                        "result": "PLAN_ONLY_PASS",
                        "contract_path": str(contract_path),
                        "preflight_path": str(preflight_path),
                        "target_run_id": target_run_id,
                    },
                }
            if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                write_mock_n3p_rollback_from_argv(argv)
                return {"returncode": 0, "json": {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}}
            if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                return {
                    "returncode": 0,
                    "json": {
                        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                        "actual_until_hhmm": "1044",
                        "source_artifact_path": "docs/intraday_live_current/20260611/N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json",
                    },
                }
            if runner_path.endswith("run_n3_hint_index_board_1m_proof_preflight_once.py"):
                return {
                    "returncode": 0,
                    "json": {
                        "result": "PLAN_ONLY_PASS",
                        "contract_path": "tmp/missing_hint_contract.json",
                        "preflight_path": "tmp/missing_hint_preflight.json",
                        "target_run_id": argv[argv.index("--target-run-id") + 1],
                        "proof_kind": proof_poller.MIDDAY_BRIDGE_HINT_PROOF_KIND,
                    },
                }
            self.fail("HINT execute child must not run when preflight artifacts are missing")

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            command_runner=runner,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3_HINT_PREFLIGHT_ARTIFACT_MISSING")
        self.assertEqual(report["executed_child_command_count"], 5)
        self.assertEqual(len(calls), 5)

    def test_proof_poller_blocks_when_hint_preflight_artifact_target_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1046",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                        },
                    }
                if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                    write_mock_n3p_rollback_from_argv(argv)
                    return {"returncode": 0, "json": {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}}
                if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1044",
                            "source_artifact_path": "docs/intraday_live_current/20260611/N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3_hint_index_board_1m_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    proof_kind = argv[argv.index("--hint-proof-kind") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(
                        json.dumps({"target_run_id": "wrong_hint_target", "proof_kind": proof_kind}),
                        encoding="utf-8",
                    )
                    preflight_path.write_text(
                        json.dumps({"target_run_id": "wrong_hint_target", "proof_kind": proof_kind}),
                        encoding="utf-8",
                    )
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": argv[argv.index("--target-run-id") + 1],
                            "proof_kind": proof_kind,
                        },
                    }
                self.fail("HINT execute child must not run when preflight artifact target mismatches")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3_HINT_PREFLIGHT_ARTIFACT_TARGET_MISMATCH")
        self.assertEqual(report["executed_child_command_count"], 5)
        self.assertEqual(len(calls), 5)

    def test_proof_poller_blocks_when_hint_preflight_artifact_proof_kind_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                runner_path = argv[1]
                if runner_path.endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1046",
                            "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                        },
                    }
                if runner_path.endswith("run_n3p_trigger_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    preflight_path.write_text(json.dumps({"target_run_id": target_run_id}), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                        },
                    }
                if runner_path.endswith("run_v3_realtime_virtual_metric_writer_once.py"):
                    write_mock_n3p_rollback_from_argv(argv)
                    return {"returncode": 0, "json": {"result": "EXECUTE_READY_REAL_IO_CONTRACT"}}
                if runner_path.endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1044",
                            "source_artifact_path": "docs/intraday_live_current/20260611/N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json",
                        },
                    }
                if runner_path.endswith("run_n3_hint_index_board_1m_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    preflight_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(
                        json.dumps({"target_run_id": target_run_id, "proof_kind": "index_board_1m_hint_projection_v1"}),
                        encoding="utf-8",
                    )
                    preflight_path.write_text(
                        json.dumps({"target_run_id": target_run_id, "proof_kind": "index_board_1m_hint_projection_v1"}),
                        encoding="utf-8",
                    )
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            "target_run_id": target_run_id,
                            "proof_kind": proof_poller.MIDDAY_BRIDGE_HINT_PROOF_KIND,
                        },
                    }
                self.fail("HINT execute child must not run when preflight artifact proof kind mismatches")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                command_runner=runner,
            )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "BLOCKED_N3_HINT_PREFLIGHT_ARTIFACT_PROOF_KIND_MISMATCH")
        self.assertEqual(report["executed_child_command_count"], 5)
        self.assertEqual(len(calls), 5)

    def test_proof_poller_child_failure_stops_subsequent_children(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            if len(calls) == 1:
                return {
                    "returncode": 0,
                    "json": {
                        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                        "actual_until_hhmm": "1046",
                        "source_payload_run_id": "n3p_mixed_realtime_source_payload_20260611_until_1046_v1",
                    },
                }
            return {"returncode": 2, "json": {"result": "BLOCKED_TEST_CHILD", "reason": "mock failure"}}

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            command_runner=runner,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "child_step_failed:n3p_trigger_proof_preflight")
        self.assertEqual(report["executed_child_command_count"], 2)
        self.assertEqual(len(calls), 2)

    def test_proof_poller_rejects_non_midday_bridge_hint_policy(self) -> None:
        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            hint_proof_kind="index_board_1m_hint_projection_v1",
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "unsupported_hint_proof_kind")
        self.assertEqual(report["required_hint_proof_kind"], proof_poller.MIDDAY_BRIDGE_HINT_PROOF_KIND)

    def test_proof_poller_n3p_only_exact_existing_target_is_noop_without_execute(self) -> None:
        calls: list[list[str]] = []
        source_hash = "a" * 64

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            if argv[1].endswith("run_n3p_current_source_fetch_once.py"):
                return {
                    "returncode": 0,
                    "json": {
                        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                        "actual_until_hhmm": "1046",
                        "source_payload_run_id": proof_poller.n3p_source_payload_run_id("20260611", "1046"),
                        "source_payload_hash": source_hash,
                        "source_artifact_file_sha256": "b" * 64,
                        "artifact_written": False,
                        "artifact_reused": True,
                        "database_written": False,
                    },
                }
            if argv[1].endswith("run_n3p_trigger_proof_preflight_once.py"):
                return {"returncode": 0, "json": n3p_preflight_idempotent_noop_payload(source_hash=source_hash)}
            self.fail("N3P execute child must not run after exact-target noop")

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            branch_mode="n3p_only",
            command_runner=runner,
        )

        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["n3p_status"], "noop")
        self.assertEqual(report["executed_child_command_count"], 2)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("run_v3_realtime_virtual_metric_writer_once.py", json.dumps(calls))
        handoff = report["actual_hhmm_handoff"]["n3p"]
        self.assertEqual(handoff["source_artifact_file_sha256"], "b" * 64)
        self.assertFalse(handoff["artifact_written"])
        self.assertTrue(handoff["artifact_reused"])
        self.assertFalse(handoff["database_written"])

    def test_proof_poller_both_preserves_n3p_noop_and_runs_only_hint_source_noop(self) -> None:
        calls: list[list[str]] = []
        source_hash = "a" * 64

        def runner(argv: list[str]) -> dict[str, object]:
            calls.append(argv)
            if argv[1].endswith("run_n3p_current_source_fetch_once.py"):
                return {
                    "returncode": 0,
                    "json": {
                        "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                        "actual_until_hhmm": "1046",
                        "source_payload_run_id": proof_poller.n3p_source_payload_run_id("20260611", "1046"),
                        "source_payload_hash": source_hash,
                    },
                }
            if argv[1].endswith("run_n3p_trigger_proof_preflight_once.py"):
                return {"returncode": 0, "json": n3p_preflight_idempotent_noop_payload(source_hash=source_hash)}
            if argv[1].endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                return {"returncode": 0, "json": hint_source_idempotent_noop_payload()}
            self.fail("No execute child may run when both existing targets are noops")

        report = proof_poller.run_proof_poller_once(
            for_trade_date="20260611",
            source_trade_date=SOURCE_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            subscription_run_id=SUBSCRIPTION_RUN_ID,
            preload_run_id=PRELOAD_RUN_ID,
            n4_context_run_id=N4_CONTEXT_RUN_ID,
            execute=True,
            user_confirmed=True,
            branch_mode="both",
            command_runner=runner,
        )

        self.assertEqual(report["status"], "noop")
        self.assertEqual(report["n3p_status"], "noop")
        self.assertEqual(report["hint_status"], "noop")
        self.assertEqual(report["executed_child_command_count"], 3)
        self.assertEqual(len(calls), 3)

    def test_proof_poller_both_keeps_n3p_noop_and_executes_normal_hint_path(self) -> None:
        source_hash = "a" * 64
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = Path.cwd()
            os.chdir(tmpdir)
            self.addCleanup(os.chdir, old_cwd)
            calls: list[list[str]] = []

            def runner(argv: list[str]) -> dict[str, object]:
                calls.append(argv)
                if argv[1].endswith("run_n3p_current_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1046",
                            "source_payload_run_id": proof_poller.n3p_source_payload_run_id("20260611", "1046"),
                            "source_payload_hash": source_hash,
                        },
                    }
                if argv[1].endswith("run_n3p_trigger_proof_preflight_once.py"):
                    return {"returncode": 0, "json": n3p_preflight_idempotent_noop_payload(source_hash=source_hash)}
                if argv[1].endswith("run_n3_hint_index_board_1m_source_fetch_once.py"):
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                            "actual_until_hhmm": "1044",
                            "source_artifact_path": (
                                "docs/intraday_live_current/20260611/"
                                "N3_hint_index_board_1m_1044_midday_bridge_frequency8_payload.json"
                            ),
                        },
                    }
                if argv[1].endswith("run_n3_hint_index_board_1m_proof_preflight_once.py"):
                    contract_path = Path(argv[argv.index("--contract-path") + 1])
                    preflight_path = Path(argv[argv.index("--preflight-path") + 1])
                    target_run_id = argv[argv.index("--target-run-id") + 1]
                    artifact = {
                        "target_run_id": target_run_id,
                        "proof_kind": proof_poller.MIDDAY_BRIDGE_HINT_PROOF_KIND,
                    }
                    contract_path.parent.mkdir(parents=True, exist_ok=True)
                    contract_path.write_text(json.dumps(artifact), encoding="utf-8")
                    preflight_path.write_text(json.dumps(artifact), encoding="utf-8")
                    return {
                        "returncode": 0,
                        "json": {
                            "result": "PLAN_ONLY_PASS",
                            "contract_path": str(contract_path),
                            "preflight_path": str(preflight_path),
                            **artifact,
                        },
                    }
                if argv[1].endswith("run_n3_hint_index_board_1m_proof_execute_once.py"):
                    return {"returncode": 0, "json": {"result": "EXECUTE_PASS", "database_written": True}}
                self.fail(f"unexpected child: {argv[1]}")

            report = proof_poller.run_proof_poller_once(
                for_trade_date="20260611",
                source_trade_date=SOURCE_TRADE_DATE,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                n4_context_run_id=N4_CONTEXT_RUN_ID,
                execute=True,
                user_confirmed=True,
                branch_mode="both",
                command_runner=runner,
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["n3p_status"], "noop")
        self.assertEqual(report["hint_status"], "passed")
        self.assertEqual(report["executed_child_command_count"], 5)
        self.assertEqual(len(calls), 5)
        self.assertNotIn("run_v3_realtime_virtual_metric_writer_once.py", json.dumps(calls))

    def test_proof_poller_blocks_forged_n3p_preflight_noop_contract(self) -> None:
        source_hash = "a" * 64
        for mutation in ("missing_required_check", "invalid_expected_count"):
            with self.subTest(mutation=mutation):
                calls: list[list[str]] = []

                def runner(argv: list[str]) -> dict[str, object]:
                    calls.append(argv)
                    if argv[1].endswith("run_n3p_current_source_fetch_once.py"):
                        return {
                            "returncode": 0,
                            "json": {
                                "result": "EXECUTE_READY_REAL_IO_CONTRACT",
                                "actual_until_hhmm": "1046",
                                "source_payload_run_id": proof_poller.n3p_source_payload_run_id("20260611", "1046"),
                                "source_payload_hash": source_hash,
                            },
                        }
                    if argv[1].endswith("run_n3p_trigger_proof_preflight_once.py"):
                        payload = n3p_preflight_idempotent_noop_payload(source_hash=source_hash)
                        target = payload["target_idempotency"]
                        if mutation == "missing_required_check":
                            target["checks"].pop("run_status_passed")
                        else:
                            target["expected_by_asset"]["stock"] = "invalid"
                        return {"returncode": 0, "json": payload}
                    self.fail("N3P execute child must not run after forged noop")

                report = proof_poller.run_proof_poller_once(
                    for_trade_date="20260611",
                    source_trade_date=SOURCE_TRADE_DATE,
                    source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                    subscription_run_id=SUBSCRIPTION_RUN_ID,
                    preload_run_id=PRELOAD_RUN_ID,
                    n4_context_run_id=N4_CONTEXT_RUN_ID,
                    execute=True,
                    user_confirmed=True,
                    branch_mode="n3p_only",
                    command_runner=runner,
                )

                self.assertEqual(report["status"], "blocked")
                self.assertIn("n3p_preflight_noop_contract_mismatch", report["reason"])
                self.assertEqual(report["executed_child_command_count"], 2)

    def test_proof_poller_idempotency_matrix(self) -> None:
        same_source = proof_poller.decide_source_payload_idempotency(
            existing={"exists": True, "status": "passed", "payload_hash": "hash-a"},
            candidate_payload_hash="hash-a",
        )
        dirty_source = proof_poller.decide_source_payload_idempotency(
            existing={"exists": True, "status": "passed", "payload_hash": "hash-b"},
            candidate_payload_hash="hash-a",
        )
        same_target = proof_poller.decide_proof_target_idempotency(
            existing={
                "exists": True,
                "status": "passed",
                "source_payload_hash": "hash-a",
                "rows_by_asset": {"board": 6},
                "metric_ready": {"ready": 6, "not_ready": 0},
                "writes_outbox": False,
                "outbox_refs": 0,
            },
            candidate={
                "source_payload_hash": "hash-a",
                "rows_by_asset": {"board": 6},
                "metric_ready": {"ready": 6, "not_ready": 0},
            },
        )
        dirty_target = proof_poller.decide_proof_target_idempotency(
            existing={
                "exists": True,
                "status": "passed",
                "source_payload_hash": "hash-a",
                "rows_by_asset": {"board": 7},
                "metric_ready": {"ready": 7, "not_ready": 0},
                "writes_outbox": False,
                "outbox_refs": 0,
            },
            candidate={
                "source_payload_hash": "hash-a",
                "rows_by_asset": {"board": 6},
                "metric_ready": {"ready": 6, "not_ready": 0},
            },
        )

        self.assertEqual(same_source["decision"], "idempotent_pass")
        self.assertEqual(dirty_source["decision"], "blocked")
        self.assertEqual(dirty_source["reason"], "same_hhmm_different_source_hash")
        self.assertEqual(same_target["decision"], "idempotent_pass")
        self.assertEqual(dirty_target["decision"], "blocked")
        self.assertEqual(dirty_target["reason"], "existing_target_baseline_mismatch")

    def test_auto_trade_date_uses_next_open_after_cutoff(self) -> None:
        resolved = auto_poll.resolve_auto_trade_date(
            calendar_rows=[
                {"trade_date": "20260611", "is_open": True},
                {"trade_date": "20260612", "is_open": True},
            ],
            as_of=datetime(2026, 6, 11, 23, 10, 0, tzinfo=ASIA_SHANGHAI),
        )

        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["for_trade_date"], "20260612")
        self.assertEqual(resolved["reason"], "next_open_trade_date_after_cutoff_or_non_trading_day")

    def test_auto_trade_date_uses_today_before_cutoff(self) -> None:
        resolved = auto_poll.resolve_auto_trade_date(
            calendar_rows=[
                {"trade_date": "20260612", "is_open": True},
                {"trade_date": "20260615", "is_open": True},
            ],
            as_of=datetime(2026, 6, 12, 9, 14, 0, tzinfo=ASIA_SHANGHAI),
        )

        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["for_trade_date"], "20260612")
        self.assertEqual(resolved["reason"], "today_open_before_cutoff")

    def test_auto_poll_lineage_patterns_exclude_action_confirmation_scoped_runs(self) -> None:
        self.assertEqual(
            auto_poll.production_subscription_pattern("20260615"),
            "market_data_subscription_20260615_condition_layer_%",
        )
        self.assertEqual(
            auto_poll.production_preload_suffix_pattern(
                "market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1"
            ),
            "%__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1",
        )

    def test_cli_auto_resolve_lineage_does_not_require_hardcoded_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "auto_{for_trade_date}.json"
            md_path = Path(tmp) / "auto_{for_trade_date}.md"
            with mock.patch.object(
                auto_poll,
                "resolve_auto_poll_lineage",
                return_value={
                    "status": "resolved",
                    "reason": "auto_lineage_resolved",
                    "as_of": "2026-06-12T09:14:00+08:00",
                    "for_trade_date": "20260612",
                    "subscription_run_id": "market_data_subscription_20260612_condition_layer_x",
                    "preload_run_id": "previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_x",
                    "source_condition_run_id": "condition_layer_20260611_source_20260611_for_20260612_v1",
                },
            ), mock.patch.object(auto_poll, "fetch_wrapper_passed_run_ids", return_value=set()), mock.patch.object(
                auto_poll,
                "fetch_live_subscription_summary",
                return_value=live_subscription_summary(),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = auto_poll.main(
                        [
                            "--auto-resolve-lineage",
                            "--as-of",
                            "2026-06-12T09:14:00+08:00",
                            "--skip-db-watermark",
                            "--docs-root",
                            str(Path(tmp) / "docs"),
                            "--sql-root",
                            str(Path(tmp) / "sql"),
                            "--json-report-path",
                            str(json_path),
                            "--markdown-report-path",
                            str(md_path),
                            "--execute",
                            "--user-confirmed",
                        ]
                    )

            self.assertEqual(rc, 0)
            rendered_json_path = Path(str(json_path).format(for_trade_date="20260612"))
            rendered_md_path = Path(str(md_path).format(for_trade_date="20260612"))
            report = json.loads(rendered_json_path.read_text(encoding="utf-8"))
            self.assertEqual(report["for_trade_date"], "20260612")
            self.assertEqual(report["status"], "noop")
            self.assertEqual(report["reason"], "no_closed_minute_available")
            self.assertEqual(report["lineage_resolution"]["subscription_run_id"], "market_data_subscription_20260612_condition_layer_x")
            self.assertTrue(rendered_md_path.exists())

    def test_default_plan_only_does_not_execute_supervisor_or_write_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=False,
                user_confirmed=False,
            )

            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["execution_mode"], "plan_only")
            self.assertEqual(report["artifact_generation"]["status"], "not_written")
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertFalse(Path(report["generated_artifacts"]["B1"]["execute_contract_json"]).exists())
            self.assertFalse(report["side_effects"]["supervisor_executed"])

    def test_missing_execute_or_user_confirmed_blocks_before_artifacts_or_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for execute, user_confirmed in [(True, False), (False, True)]:
                with self.subTest(execute=execute, user_confirmed=user_confirmed):
                    report = auto_poll.run_auto_poll_once(
                        for_trade_date="20260611",
                        subscription_run_id=SUBSCRIPTION_RUN_ID,
                        preload_run_id=PRELOAD_RUN_ID,
                        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                        as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                        docs_root=str(Path(tmp) / "docs"),
                        sql_root=str(Path(tmp) / "sql"),
                        passed_run_ids=set(),
                        execute=execute,
                        user_confirmed=user_confirmed,
                    )

                    self.assertEqual(report["status"], "blocked")
                    self.assertEqual(report["reason"], "auto_poll_execute_requires_user_confirmed")
                    self.assertEqual(report["artifact_generation"]["status"], "not_written")
                    self.assertEqual(report["executed_child_command_count"], 0)

    def test_before_auction_window_no_closed_minute_noops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 14, 59, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
            )

            self.assertEqual(report["status"], "noop")
            self.assertEqual(report["reason"], "no_closed_minute_available")
            self.assertEqual(report["artifact_generation"]["status"], "not_written")

    def test_auction_0919_prewarm_generates_b1_b2_artifacts_without_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 19, 0, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                command_runner=lambda command: self.fail("auction prewarm must not execute supervisor children"),
            )

            self.assertEqual(report["status"], "prewarm_ready")
            self.assertEqual(report["reason"], "auction_preopen_artifacts_ready")
            self.assertEqual(report["prewarm"]["prepared_hhmm"], "0920")
            self.assertEqual(report["projection_input_mode"], "auction_or_snapshot_only")
            self.assertEqual(report["artifact_validation"]["status"], "passed")
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertFalse(report["side_effects"]["supervisor_executed"])

    def test_auction_0920_generates_b1_b2_artifacts_and_executes_without_c1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_runner(command: list[str]) -> object:
                calls.append(command[1])

                class Result:
                    returncode = 0
                    stdout = "ok"
                    stderr = ""

                return Result()

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 20, 0, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                command_runner=fake_runner,
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["projection_input_mode"], "auction_or_snapshot_only")
            self.assertEqual(calls, [
                "scripts/run_realtime_daily_snapshot_once.py",
                "scripts/run_realtime_projection_metric_once.py",
            ])
            self.assertEqual(report["executed_child_command_count"], 2)
            self.assertTrue(report["side_effects"]["b1_c1_b2_executed"])

    def test_wrapper_injects_live_subscription_counts_into_b1_child_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_runner(command: list[str]) -> object:
                calls.append(command[1])

                class Result:
                    returncode = 0
                    stdout = "ok"
                    stderr = ""

                return Result()

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                subscription_summary=live_subscription_summary(),
                command_runner=fake_runner,
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(calls, [
                "scripts/run_realtime_daily_snapshot_once.py",
                "scripts/run_today_minute_bar_1m_once.py",
                "scripts/run_realtime_projection_metric_once.py",
            ])
            contract_path = Path(report["generated_artifacts"]["B1"]["execute_contract_json"])
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["expected_asset_counts"]["stock"]["subscription_count"], 1872)
            self.assertEqual(contract["expected_asset_counts"]["index"]["subscription_count"], 83)
            self.assertEqual(contract["expected_asset_counts"]["board"]["subscription_count"], 127)
            self.assertEqual(contract["expected_row_count"], 2082)

    def test_preopen_0919_prewarm_generates_and_validates_0920_artifacts_without_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 19, 0, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                command_runner=lambda command: self.fail("prewarm must not execute supervisor children"),
            )

            self.assertEqual(report["status"], "prewarm_ready")
            self.assertEqual(report["reason"], "auction_preopen_artifacts_ready")
            self.assertEqual(report["prewarm"]["prepared_hhmm"], "0920")
            self.assertEqual(report["artifact_generation"]["status"], "written")
            self.assertEqual(report["artifact_validation"]["status"], "passed")
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertFalse(report["side_effects"]["supervisor_executed"])
            self.assertTrue(Path(report["generated_artifacts"]["B1"]["execute_contract_json"]).exists())

    def test_prewarm_idempotency_identical_artifacts_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kwargs = dict(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 19, 30, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
            )
            first = auto_poll.run_auto_poll_once(**kwargs)
            second = auto_poll.run_auto_poll_once(**kwargs)

            self.assertEqual(first["status"], "prewarm_ready")
            self.assertEqual(second["status"], "prewarm_ready")
            self.assertEqual(second["artifact_generation"]["status"], "unchanged")
            self.assertEqual(second["executed_child_command_count"], 0)

    def test_prewarm_artifact_conflict_blocks_without_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conflict = Path(tmp) / "docs" / "N3_B1_realtime_snapshot_20260611_auction_0920_execute_contract.json"
            conflict.parent.mkdir(parents=True)
            conflict.write_text('{"different": true}\n', encoding="utf-8")

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 19, 0, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                command_runner=lambda command: self.fail("prewarm conflict must not execute supervisor children"),
            )

            self.assertEqual(report["status"], "prewarm_blocked")
            self.assertEqual(report["reason"], "auction_preopen_artifact_generation_failed")
            self.assertEqual(report["prewarm"]["prepared_hhmm"], "0920")
            self.assertEqual(report["executed_child_command_count"], 0)

    def test_current_date_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 12, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
            )

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["reason"], "current_date_mismatch")
            self.assertEqual(report["artifact_generation"]["status"], "not_written")

    def test_passed_b2_watermark_noops_before_artifact_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            probe = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
            )
            b2_run_id = probe["stage_run_ids"]["B2"]

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 32, 30, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids={b2_run_id},
                execute=True,
                user_confirmed=True,
            )

            self.assertEqual(report["status"], "noop")
            self.assertEqual(report["reason"], "latest_closed_minute_already_processed")
            self.assertEqual(report["artifact_generation"]["status"], "not_written")
            self.assertFalse(Path(probe["generated_artifacts"]["B1"]["execute_contract_json"]).exists())

    def test_execute_generates_artifacts_before_supervisor_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_runner(command: list[str]) -> object:
                if command[1] == "scripts/run_realtime_daily_snapshot_once.py":
                    self.assertTrue(Path(command[command.index("--contract-path") + 1]).exists())
                    self.assertTrue(Path(command[command.index("--readiness-path") + 1]).exists())
                elif command[1] == "scripts/run_today_minute_bar_1m_once.py":
                    c0_plan_path = Path(command[command.index("--c0-plan-path") + 1])
                    self.assertTrue(c0_plan_path.exists())
                    c0_plan = json.loads(c0_plan_path.read_text(encoding="utf-8"))
                    self.assertEqual(c0_plan["source_market_data_run_id"], SUBSCRIPTION_RUN_ID)
                    self.assertEqual(c0_plan["source_run_id"], SUBSCRIPTION_RUN_ID)
                    self.assertEqual(c0_plan["source_condition_run_id"], SOURCE_CONDITION_RUN_ID)
                    self.assertTrue(Path(command[command.index("--rollback-sql-path") + 1]).exists())
                elif command[1] == "scripts/run_realtime_projection_metric_once.py":
                    self.assertTrue(Path(command[command.index("--contract-path") + 1]).exists())
                    self.assertTrue(Path(command[command.index("--preflight-path") + 1]).exists())
                    self.assertTrue(Path(command[command.index("--dry-run-path") + 1]).exists())
                    self.assertTrue(Path(command[command.index("--rollback-sql-path") + 1]).exists())
                calls.append(command[1])

                class Result:
                    returncode = 0
                    stdout = "ok"
                    stderr = ""

                return Result()

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                command_runner=fake_runner,
            )

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["artifact_generation"]["status"], "written")
            self.assertEqual(report["artifact_validation"]["status"], "passed")
            self.assertEqual(calls, [
                "scripts/run_realtime_daily_snapshot_once.py",
                "scripts/run_today_minute_bar_1m_once.py",
                "scripts/run_realtime_projection_metric_once.py",
            ])

    def test_c1_does_not_execute_before_first_closed_minute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_runner(command: list[str]) -> object:
                calls.append(command[1])

                class Result:
                    returncode = 0
                    stdout = "ok"
                    stderr = ""

                return Result()

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 25, 0, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                command_runner=fake_runner,
            )

            self.assertNotIn("scripts/run_today_minute_bar_1m_once.py", calls)
            self.assertEqual(report["skipped_child_steps"][0]["stage"], "C1")
            self.assertEqual(report["skipped_child_steps"][0]["reason"], "no_closed_minute_available")

    def test_artifact_conflict_blocks_before_supervisor_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conflict = Path(tmp) / "docs" / "N3_B1_realtime_snapshot_20260611_until_0931_execute_contract.json"
            conflict.parent.mkdir(parents=True)
            conflict.write_text('{"different": true}\n', encoding="utf-8")

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                command_runner=lambda command: self.fail("supervisor child should not execute"),
            )

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["reason"], "child_artifact_generation_failed")
            self.assertEqual(report["executed_child_command_count"], 0)

    def test_existing_b2_noop_report_counts_as_processed_before_artifact_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            sql_root = Path(tmp) / "sql"
            docs_root.mkdir(parents=True)
            sql_root.mkdir(parents=True)
            # 15:00 is the close boundary; the final physical 1m bar label is 14:59.
            b1_run_id = (
                f"realtime_daily_snapshot_20260612_until_1459__{SUBSCRIPTION_RUN_ID}"
            )
            c1_run_id = (
                f"today_minute_bar_1m_20260612_until_1459__{SUBSCRIPTION_RUN_ID}"
            )
            b2_run_id = (
                f"realtime_projection_metric_20260612_until_1459__{b1_run_id}"
            )
            (docs_root / "N3_B2_realtime_projection_20260612_until_1459_execute_report.json").write_text(
                json.dumps(
                    {
                        "result": "NOOP_PASS",
                        "noop_reason": "off_bucket_source_snapshot_time",
                        "projection_run_id": b2_run_id,
                        "side_effects": {"writes_performed": False},
                    }
                ),
                encoding="utf-8",
            )
            (sql_root / "N3_B2_realtime_projection_20260612_until_1459_rollback.sql").write_text(
                "-- existing rollback registry must not be rewritten\n",
                encoding="utf-8",
            )

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260612",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 12, 15, 8, 0, tzinfo=ASIA_SHANGHAI),
                docs_root=str(docs_root),
                sql_root=str(sql_root),
                passed_run_ids={b1_run_id, c1_run_id},
                execute=True,
                user_confirmed=True,
                command_runner=lambda command: self.fail("B2 child should not execute after NOOP_PASS"),
            )

            self.assertEqual(report["status"], "noop")
            self.assertEqual(report["reason"], "latest_closed_minute_b2_noop_already_processed")
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertEqual(report["artifact_generation"]["status"], "not_written")
            self.assertFalse(report["side_effects"]["supervisor_executed"])

    def test_existing_b2_noop_report_with_projection_run_mismatch_does_not_count_as_processed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            sql_root = Path(tmp) / "sql"
            docs_root.mkdir(parents=True)
            sql_root.mkdir(parents=True)
            b1_run_id = f"realtime_daily_snapshot_20260612_until_1459__{SUBSCRIPTION_RUN_ID}"
            c1_run_id = f"today_minute_bar_1m_20260612_until_1459__{SUBSCRIPTION_RUN_ID}"
            plan = auto_poll.build_intraday_supervisor_plan(
                for_trade_date="20260612",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                passed_run_ids={b1_run_id, c1_run_id},
                as_of=datetime(2026, 6, 12, 15, 8, 0, tzinfo=ASIA_SHANGHAI),
                docs_root=docs_root,
                sql_root=sql_root,
            )
            b2_step = auto_poll.b2_noop_child_step(plan)
            Path(b2_step["json_report_path"]).write_text(
                json.dumps(
                    {
                        "result": "NOOP_PASS",
                        "projection_run_id": "wrong_projection_run_id",
                        "side_effects": {"writes_performed": False},
                    }
                ),
                encoding="utf-8",
            )

            self.assertFalse(auto_poll.b2_noop_report_already_processed(plan))

    def test_existing_b2_noop_report_with_writes_performed_does_not_count_as_processed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "docs"
            sql_root = Path(tmp) / "sql"
            docs_root.mkdir(parents=True)
            sql_root.mkdir(parents=True)
            b1_run_id = f"realtime_daily_snapshot_20260612_until_1459__{SUBSCRIPTION_RUN_ID}"
            c1_run_id = f"today_minute_bar_1m_20260612_until_1459__{SUBSCRIPTION_RUN_ID}"
            plan = auto_poll.build_intraday_supervisor_plan(
                for_trade_date="20260612",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                passed_run_ids={b1_run_id, c1_run_id},
                as_of=datetime(2026, 6, 12, 15, 8, 0, tzinfo=ASIA_SHANGHAI),
                docs_root=docs_root,
                sql_root=sql_root,
            )
            b2_step = auto_poll.b2_noop_child_step(plan)
            Path(b2_step["json_report_path"]).write_text(
                json.dumps(
                    {
                        "result": "NOOP_PASS",
                        "projection_run_id": b2_step["run_id"],
                        "side_effects": {"writes_performed": True},
                    }
                ),
                encoding="utf-8",
            )

            self.assertFalse(auto_poll.b2_noop_report_already_processed(plan))

    def test_supervisor_failure_blocks_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def failing_runner(command: list[str]) -> object:
                class Result:
                    returncode = 2
                    stdout = "blocked"
                    stderr = "P0"

                return Result()

            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
                execute=True,
                user_confirmed=True,
                command_runner=failing_runner,
            )

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["reason"], "child_step_failed")
            self.assertEqual(report["failed_stage"], "B1")

    def test_cli_plan_only_writes_wrapper_report_without_supervisor_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "auto_poll.json"
            md_path = Path(tmp) / "auto_poll.md"
            with mock.patch.object(
                auto_poll,
                "fetch_live_subscription_summary",
                return_value=live_subscription_summary(),
            ), contextlib.redirect_stdout(io.StringIO()):
                rc = auto_poll.main(
                    [
                        "--for-trade-date",
                        "20260611",
                        "--subscription-run-id",
                        SUBSCRIPTION_RUN_ID,
                        "--preload-run-id",
                        PRELOAD_RUN_ID,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                        "--as-of",
                        "2026-06-11T09:32:05+08:00",
                        "--skip-db-watermark",
                        "--docs-root",
                        str(Path(tmp) / "docs"),
                        "--sql-root",
                        str(Path(tmp) / "sql"),
                        "--json-report-path",
                        str(json_path),
                        "--markdown-report-path",
                        str(md_path),
                        "--json",
                    ]
                )

            self.assertEqual(rc, 0)
            report = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(report["execution_mode"], "plan_only")
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertTrue(md_path.exists())

    def test_cli_prewarm_ready_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "auto_poll_prewarm.json"
            md_path = Path(tmp) / "auto_poll_prewarm.md"
            with mock.patch.object(
                auto_poll,
                "fetch_live_subscription_summary",
                return_value=live_subscription_summary(),
            ), contextlib.redirect_stdout(io.StringIO()):
                rc = auto_poll.main(
                    [
                        "--for-trade-date",
                        "20260611",
                        "--subscription-run-id",
                        SUBSCRIPTION_RUN_ID,
                        "--preload-run-id",
                        PRELOAD_RUN_ID,
                        "--source-condition-run-id",
                        SOURCE_CONDITION_RUN_ID,
                        "--as-of",
                        "2026-06-11T09:19:05+08:00",
                        "--skip-db-watermark",
                        "--docs-root",
                        str(Path(tmp) / "docs"),
                        "--sql-root",
                        str(Path(tmp) / "sql"),
                        "--json-report-path",
                        str(json_path),
                        "--markdown-report-path",
                        str(md_path),
                        "--execute",
                        "--user-confirmed",
                        "--json",
                    ]
                )

            self.assertEqual(rc, 0)
            report = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "prewarm_ready")
            self.assertEqual(report["prewarm"]["prepared_hhmm"], "0920")
            self.assertEqual(report["executed_child_command_count"], 0)
            self.assertTrue(md_path.exists())

    def test_child_commands_are_argv_lists_and_forbidden_markers_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = auto_poll.run_auto_poll_once(
                for_trade_date="20260611",
                subscription_run_id=SUBSCRIPTION_RUN_ID,
                preload_run_id=PRELOAD_RUN_ID,
                source_condition_run_id=SOURCE_CONDITION_RUN_ID,
                as_of=datetime(2026, 6, 11, 9, 32, 5, tzinfo=ASIA_SHANGHAI),
                docs_root=str(Path(tmp) / "docs"),
                sql_root=str(Path(tmp) / "sql"),
                passed_run_ids=set(),
            )

            for step in report["child_steps"]:
                self.assertIsInstance(step["command"], list)
                joined = " ".join(step["command"])
                for marker in ["run_n4", "run_n5", "run_n6", "worker", "stock_monitor_isolated", "monitor.db"]:
                    self.assertNotIn(marker, joined)


if __name__ == "__main__":
    unittest.main()
