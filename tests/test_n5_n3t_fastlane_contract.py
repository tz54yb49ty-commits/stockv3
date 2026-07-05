import argparse
import io
import json
import plistlib
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


WORKING_DIRECTORY = "/Users/chuanfuchen/Documents/A股监控系统v3"


def _plist_placeholders(value: object) -> list[str]:
    placeholders: list[str] = []
    pattern = re.compile(r"__[A-Z0-9_]+__")

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, str):
            placeholders.extend(pattern.findall(node))

    walk(value)
    return placeholders


class N5N3TFastlaneContractTest(unittest.TestCase):
    def test_active_loaded_state_review_accepts_closed_day_scheduler_noop(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_active_loaded_state_review,
        )

        launchd_states = {
            FASTLANE_LABELS["n5_intake"]: {
                "loaded": True,
                "state": "spawn scheduled",
                "pid": None,
                "runs": 12,
                "last_exit_code": 0,
            },
            FASTLANE_LABELS["n3_c1_n3t"]: {
                "loaded": True,
                "state": "not running",
                "pid": None,
                "runs": 12,
                "last_exit_code": 0,
            },
            FASTLANE_LABELS["n5_executed"]: {
                "loaded": True,
                "state": "spawn scheduled",
                "pid": None,
                "runs": 12,
                "last_exit_code": 0,
            },
        }
        plist_summaries = {
            label: {
                "label": label,
                "sha256": f"sha_{key}",
                "expected_sha256": f"sha_{key}",
                "start_interval": 5 if key == "n3_c1_n3t" else 3,
                "run_at_load": False,
                "keep_alive": False,
                "activation_config_20260706": True,
                "scheduler_quiet": True,
                "has_placeholder": False,
                "has_secret_literal": False,
                "has_old_runner_ref": False,
            }
            for key, label in FASTLANE_LABELS.items()
        }
        recent_log_manifests = {
            label: [
                {
                    "verdict": "FASTLANE_SCHEDULER_NOOP",
                    "session_phase": "closed_day_or_non_trading",
                    "writes_enabled": False,
                    "scheduler_quiet": True,
                }
            ]
            for label in FASTLANE_LABELS.values()
        }

        review = build_fastlane_active_loaded_state_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-04T04:02:41+08:00",
            launchd_states=launchd_states,
            plist_summaries=plist_summaries,
            recent_log_manifests=recent_log_manifests,
            stderr_snapshots={
                label: {"size": 10, "mtime": "2026-07-04T01:58:46+08:00", "grew_after_load": False}
                for label in FASTLANE_LABELS.values()
            },
        )

        self.assertEqual(review["result"], "PASS")
        self.assertEqual(review["final_verdict"], "FASTLANE_ACTIVE_LOADED_STATE_REVIEW_PASS")
        self.assertTrue(review["all_labels_loaded"])
        self.assertTrue(review["bounded_one_shot_exit_ok"])
        self.assertTrue(review["closed_day_noop_verified"])
        self.assertFalse(review["writes_enabled_observed"])
        self.assertFalse(review["runtime_write_risk"])

    def test_loaded_state_review_uses_plist_summary_activation_config_and_scheduler_quiet(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_active_loaded_state_review,
        )
        from scripts.review_n5_n3t_fastlane_trading_day_monitor import _read_plist_summaries

        with tempfile.TemporaryDirectory() as tmpdir:
            launchagents_dir = Path(tmpdir)
            for key, label in FASTLANE_LABELS.items():
                runner = (
                    "scripts/run_n3_c1_n3t_action_confirmation_fastlane_once.py"
                    if key == "n3_c1_n3t"
                    else "scripts/run_n5_live_tracking_poller_once.py"
                )
                plist = {
                    "Label": label,
                    "ProgramArguments": [
                        "/usr/bin/python3",
                        runner,
                        "--activation-config",
                        "tmp/N5_N3T_action_confirmation_fastlane_activation_config/"
                        "write_enabled_activation_config_20260706_runtime_deferred_v1.json",
                        "--scheduler-quiet",
                        "--json",
                    ],
                    "RunAtLoad": False,
                    "KeepAlive": False,
                    "StartInterval": 5 if key == "n3_c1_n3t" else 3,
                }
                (launchagents_dir / f"{label}.plist").write_bytes(plistlib.dumps(plist))

            plist_summaries = _read_plist_summaries(launchagents_dir)

        review = build_fastlane_active_loaded_state_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-04T09:10:00+08:00",
            launchd_states={
                label: {"loaded": True, "pid": None, "runs": 12, "last_exit_code": 0}
                for label in FASTLANE_LABELS.values()
            },
            plist_summaries=plist_summaries,
            recent_log_manifests={
                label: [
                    {
                        "verdict": "FASTLANE_SCHEDULER_NOOP",
                        "session_phase": "closed_day_or_non_trading",
                        "writes_enabled": False,
                        "scheduler_quiet": True,
                    }
                ]
                for label in FASTLANE_LABELS.values()
            },
            stderr_snapshots={
                label: {"exists": True, "size": 0, "grew_after_load": False}
                for label in FASTLANE_LABELS.values()
            },
        )

        self.assertEqual(review["result"], "PASS")
        self.assertEqual(review["blockers"], [])

    def test_active_loaded_state_review_blocks_runtime_write_risk(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_active_loaded_state_review,
        )

        label = FASTLANE_LABELS["n5_intake"]
        review = build_fastlane_active_loaded_state_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-04T04:02:41+08:00",
            launchd_states={
                label: {
                    "loaded": True,
                    "state": "running",
                    "pid": 12345,
                    "runs": 1,
                    "last_exit_code": 0,
                }
            },
            plist_summaries={
                label: {
                    "label": label,
                    "sha256": "sha",
                    "expected_sha256": "sha",
                    "start_interval": 3,
                    "run_at_load": False,
                    "keep_alive": False,
                    "activation_config_20260706": True,
                    "scheduler_quiet": True,
                    "has_placeholder": False,
                    "has_secret_literal": False,
                    "has_old_runner_ref": False,
                }
            },
            recent_log_manifests={
                label: [
                    {
                        "verdict": "FASTLANE_SCHEDULER_NOOP",
                        "session_phase": "closed_day_or_non_trading",
                        "writes_enabled": True,
                        "scheduler_quiet": True,
                    }
                ]
            },
            stderr_snapshots={label: {"size": 10, "mtime": "2026-07-04T04:00:00+08:00", "grew_after_load": True}},
        )

        self.assertEqual(review["result"], "BLOCKED")
        self.assertIn("writes_enabled_true", review["blockers"])
        self.assertIn("running_pid_present", review["blockers"])
        self.assertTrue(review["runtime_write_risk"])

    def test_trading_day_monitor_passes_when_automatic_chain_has_end_to_end_evidence(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_trading_day_monitor_review,
        )

        review = build_fastlane_trading_day_monitor_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-06T09:36:05+08:00",
            launchd_states={
                label: {"loaded": True, "pid": None, "runs": 100, "last_exit_code": 0}
                for label in FASTLANE_LABELS.values()
            },
            plist_summaries={
                label: {
                    "label": label,
                    "start_interval": 5 if key == "n3_c1_n3t" else 3,
                    "run_at_load": False,
                    "keep_alive": False,
                    "uses_activation_config": True,
                    "has_placeholder": False,
                    "has_secret_literal": False,
                    "has_old_runner_ref": False,
                }
                for key, label in FASTLANE_LABELS.items()
            },
            recent_log_manifests={
                FASTLANE_LABELS["n5_intake"]: [
                    {"verdict": "FASTLANE_EXECUTE_PASS", "session_phase": "trading", "writes_enabled": True}
                ],
                FASTLANE_LABELS["n3_c1_n3t"]: [
                    {"verdict": "FASTLANE_N3T_METRIC_PASS", "session_phase": "trading", "writes_enabled": True}
                ],
                FASTLANE_LABELS["n5_executed"]: [
                    {"verdict": "FASTLANE_EXECUTE_PASS", "session_phase": "trading", "writes_enabled": True}
                ],
            },
            chain_evidence={
                "session_phase": "trading",
                "n4_triggermatched": 12,
                "n5_actioneligible": 12,
                "n5_active_tracking": 12,
                "n5_active_scope_artifacts": 1,
                "n3_scoped_c1_artifacts": 1,
                "n3t_c1_closed_metric_rows": 12,
                "n5_actionexecuted": 3,
                "closed_minute_available": True,
                "n4_outbox_status_unchanged": True,
                "n4_outbox_updated": False,
                "n5_output_event_types": ["ActionEligible", "ActionExecuted"],
                "n3_consumed_only_explicit_active_scope_artifact": True,
                "n3_scanned_n5_db": False,
                "n3_full_market_fallback": False,
                "n3t_lineage_ok": True,
                "legacy_metric_used": False,
                "old_n3_n4_labels_unchanged": True,
                "n6_touched": False,
            },
        )

        self.assertEqual(review["result"], "PASS")
        self.assertEqual(
            review["final_verdict"],
            "FASTLANE_TRADING_DAY_MONITOR_PASS_AUTOMATIC_CHAIN_VERIFIED",
        )
        self.assertTrue(review["automatic_chain_verified"])
        self.assertFalse(review["manual_gate_required"])
        self.assertEqual(review["blockers"], [])

    def test_trading_day_monitor_does_not_pass_when_fastlane_backlog_remains(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_trading_day_monitor_review,
        )

        review = build_fastlane_trading_day_monitor_review(
            for_trade_date="20260703",
            current_exchange_time="2026-07-03T15:30:00+08:00",
            launchd_states={
                label: {"loaded": True, "pid": None, "runs": 100, "last_exit_code": 0}
                for label in FASTLANE_LABELS.values()
            },
            plist_summaries={
                label: {
                    "label": label,
                    "start_interval": 5 if key == "n3_c1_n3t" else 3,
                    "run_at_load": False,
                    "keep_alive": False,
                    "uses_activation_config": True,
                    "has_placeholder": False,
                    "has_secret_literal": False,
                    "has_old_runner_ref": False,
                }
                for key, label in FASTLANE_LABELS.items()
            },
            recent_log_manifests={label: [] for label in FASTLANE_LABELS.values()},
            chain_evidence={
                "session_phase": "post_close",
                "n4_triggermatched": 998,
                "n5_actioneligible": 310,
                "n5_active_tracking": 285,
                "n5_active_scope_artifacts": 4,
                "n3_scoped_c1_artifacts": 12,
                "n3t_c1_closed_metric_rows": 253,
                "n5_actionexecuted": 25,
                "closed_minute_available": True,
                "n4_outbox_status_unchanged": True,
                "n4_outbox_updated": False,
                "n5_output_event_types": ["ActionEligible", "ActionExecuted"],
                "n3_consumed_only_explicit_active_scope_artifact": True,
                "n3_scanned_n5_db": False,
                "n3_full_market_fallback": False,
                "n3t_lineage_ok": True,
                "legacy_metric_used": False,
                "old_n3_n4_labels_unchanged": True,
                "n6_touched": False,
            },
        )

        self.assertEqual(review["result"], "WAITING")
        self.assertEqual(
            review["final_verdict"],
            "FASTLANE_TRADING_DAY_MONITOR_WAITING_FOR_EXACT_COVER",
        )
        self.assertFalse(review["automatic_chain_verified"])
        self.assertEqual(review["chain_backlog"]["n5_intake_remaining"], 688)
        self.assertEqual(review["chain_backlog"]["n3t_metric_remaining"], 57)
        self.assertIn("waiting_for_n5_intake_exact_cover", review["waiting_reasons"])
        self.assertIn("waiting_for_n3t_metric_exact_cover", review["waiting_reasons"])

    def test_active_worker_policy_review_allows_write_enabled_bootstrap_for_exact_cover_backlog(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_active_worker_policy_review,
        )

        review = build_fastlane_active_worker_policy_review(
            for_trade_date="20260703",
            monitor_review={
                "result": "WAITING",
                "final_verdict": "FASTLANE_TRADING_DAY_MONITOR_WAITING_FOR_EXACT_COVER",
                "automatic_chain_verified": False,
                "manual_gate_required": False,
                "chain_backlog": {
                    "n5_intake_remaining": 688,
                    "n3t_metric_remaining": 57,
                },
                "waiting_reasons": [
                    "waiting_for_n5_intake_exact_cover",
                    "waiting_for_n3t_metric_exact_cover",
                ],
                "blockers": [],
            },
        )

        self.assertEqual(review["result"], "PASS")
        self.assertEqual(
            review["final_verdict"],
            "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
        )
        self.assertTrue(review["active_worker_write_enabled_ready"])
        self.assertFalse(review["full_chain_automatic_worker_ready"])
        self.assertEqual(review["activation_scope"], "exact_cover_backlog_bootstrap")
        self.assertFalse(review["automatic_chain_verified"])
        self.assertEqual(review["chain_backlog"]["n5_intake_remaining"], 688)
        self.assertEqual(review["chain_backlog"]["n3t_metric_remaining"], 57)
        self.assertIn("waiting_for_n5_intake_exact_cover", review["waiting_reasons"])
        self.assertIn("waiting_for_n3t_metric_exact_cover", review["waiting_reasons"])
        self.assertEqual(review["blockers"], [])

    def test_active_worker_policy_review_allows_idle_open_scheduler_without_n4_yet(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_active_worker_policy_review,
        )

        review = build_fastlane_active_worker_policy_review(
            for_trade_date="20260703",
            monitor_review={
                "result": "WAITING",
                "final_verdict": "FASTLANE_TRADING_DAY_MONITOR_WAITING_FOR_INPUT_OR_CLOSED_MINUTE",
                "automatic_chain_verified": False,
                "manual_gate_required": False,
                "session_phase": "trading",
                "chain_backlog": {
                    "n5_intake_remaining": 0,
                    "n3t_metric_remaining": 0,
                },
                "waiting_reasons": ["waiting_for_n4_triggermatched"],
                "blockers": [],
            },
        )

        self.assertEqual(review["result"], "PASS")
        self.assertTrue(review["active_worker_write_enabled_ready"])
        self.assertFalse(review["full_chain_automatic_worker_ready"])
        self.assertEqual(review["activation_scope"], "idle_open_scheduler")
        self.assertFalse(review["automatic_chain_verified"])
        self.assertIn("waiting_for_n4_triggermatched", review["waiting_reasons"])

    def test_active_worker_policy_review_marks_full_chain_automatic_ready_only_after_monitor_pass(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_active_worker_policy_review,
        )

        review = build_fastlane_active_worker_policy_review(
            for_trade_date="20260703",
            monitor_review={
                "result": "PASS",
                "final_verdict": "FASTLANE_TRADING_DAY_MONITOR_PASS_AUTOMATIC_CHAIN_VERIFIED",
                "automatic_chain_verified": True,
                "manual_gate_required": False,
                "chain_backlog": {
                    "n5_intake_remaining": 0,
                    "n3t_metric_remaining": 0,
                },
                "waiting_reasons": [],
                "blockers": [],
            },
        )

        self.assertEqual(review["result"], "PASS")
        self.assertTrue(review["active_worker_write_enabled_ready"])
        self.assertTrue(review["full_chain_automatic_worker_ready"])
        self.assertEqual(review["activation_scope"], "full_chain_automatic_worker")
        self.assertTrue(review["automatic_chain_verified"])
        self.assertEqual(review["next_full_chain_order"], "RUNTIME_CONTROL_FASTLANE_WRITE_ENABLED_ACTIVATION_CONFIG_FULL_CHAIN_PREFLIGHT_GATE")

    def test_trading_day_monitor_blocks_when_n4_exists_but_chain_does_not_advance(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_trading_day_monitor_review,
        )

        review = build_fastlane_trading_day_monitor_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-06T09:36:05+08:00",
            launchd_states={
                label: {"loaded": True, "pid": None, "runs": 100, "last_exit_code": 0}
                for label in FASTLANE_LABELS.values()
            },
            plist_summaries={
                label: {
                    "label": label,
                    "start_interval": 5 if key == "n3_c1_n3t" else 3,
                    "run_at_load": False,
                    "keep_alive": False,
                    "uses_activation_config": True,
                    "has_placeholder": False,
                    "has_secret_literal": False,
                    "has_old_runner_ref": False,
                }
                for key, label in FASTLANE_LABELS.items()
            },
            recent_log_manifests={label: [] for label in FASTLANE_LABELS.values()},
            chain_evidence={
                "session_phase": "trading",
                "n4_triggermatched": 12,
                "n5_actioneligible": 0,
                "n5_active_tracking": 0,
                "n5_active_scope_artifacts": 0,
                "n3_scoped_c1_artifacts": 0,
                "n3t_c1_closed_metric_rows": 0,
                "n5_actionexecuted": 0,
                "closed_minute_available": True,
                "n4_outbox_status_unchanged": True,
                "n4_outbox_updated": False,
                "n5_output_event_types": ["ActionEligible"],
                "n3_consumed_only_explicit_active_scope_artifact": True,
                "n3_scanned_n5_db": False,
                "n3_full_market_fallback": False,
                "n3t_lineage_ok": False,
                "legacy_metric_used": False,
                "old_n3_n4_labels_unchanged": True,
                "n6_touched": False,
            },
        )

        self.assertEqual(review["result"], "BLOCKED")
        self.assertFalse(review["automatic_chain_verified"])
        self.assertIn("n5_actioneligible_not_advancing", review["blockers"])
        self.assertIn("n3t_c1_closed_metric_missing_after_closed_minute", review["blockers"])
        self.assertIn("n5_actionexecuted_not_advancing", review["blockers"])

    def test_chain_evidence_builder_normalizes_db_and_artifact_summaries(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_chain_evidence,
            build_fastlane_trading_day_monitor_review,
        )

        evidence = build_fastlane_chain_evidence(
            for_trade_date="20260706",
            session_phase="trading",
            closed_minute_available=True,
            db_summary={
                "n4_triggermatched": 12,
                "n5_actioneligible": 12,
                "n5_active_tracking": 12,
                "n5_actionexecuted": 3,
                "n3t_c1_closed_metric_rows": 12,
                "n5_output_event_types": ["ActionEligible", "ActionExecuted"],
                "n4_outbox_status_unchanged": True,
                "n4_outbox_updated": False,
                "n3t_lineage_ok": True,
                "legacy_metric_used": False,
            },
            artifact_summary={
                "n5_active_scope_artifacts": 1,
                "n3_scoped_c1_artifacts": 1,
                "n3_consumed_only_explicit_active_scope_artifact": True,
                "n3_scanned_n5_db": False,
                "n3_full_market_fallback": False,
                "old_n3_n4_labels_unchanged": True,
                "n6_touched": False,
            },
        )

        self.assertEqual(evidence["artifact_type"], "n5_n3t_fastlane_chain_evidence_v1")
        self.assertEqual(evidence["for_trade_date"], "20260706")
        self.assertEqual(evidence["n4_triggermatched"], 12)
        self.assertEqual(evidence["n5_actioneligible"], 12)
        self.assertEqual(evidence["n3t_c1_closed_metric_rows"], 12)
        self.assertEqual(evidence["n5_actionexecuted"], 3)
        self.assertTrue(evidence["n4_outbox_status_unchanged"])
        self.assertFalse(evidence["n3_scanned_n5_db"])
        self.assertFalse(evidence["n6_touched"])
        self.assertFalse(evidence["forbidden_operation_proof"]["database_written_by_plan"])

        review = build_fastlane_trading_day_monitor_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-06T09:36:05+08:00",
            launchd_states={
                label: {"loaded": True, "pid": None, "runs": 8, "last_exit_code": 0}
                for label in FASTLANE_LABELS.values()
            },
            plist_summaries={
                label: {
                    "label": label,
                    "start_interval": 5 if key == "n3_c1_n3t" else 3,
                    "run_at_load": False,
                    "keep_alive": False,
                    "uses_activation_config": True,
                    "has_placeholder": False,
                    "has_secret_literal": False,
                    "has_old_runner_ref": False,
                }
                for key, label in FASTLANE_LABELS.items()
            },
            recent_log_manifests={label: [] for label in FASTLANE_LABELS.values()},
            chain_evidence=evidence,
        )

        self.assertEqual(review["result"], "PASS")
        self.assertTrue(review["automatic_chain_verified"])

    def test_session_phase_policy_defines_preopen_trading_lunch_postclose_boundaries(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_session_phase_policy,
            classify_fastlane_session_phase,
        )

        policy = build_fastlane_session_phase_policy()

        self.assertEqual(policy["policy_type"], "fastlane_session_phase_policy_v1")
        self.assertEqual(
            policy["phases"],
            [
                "pre_open_before_0925",
                "pre_open_call_auction_after_0925",
                "trading",
                "lunch_break",
                "post_close",
                "closed_day_or_non_trading",
            ],
        )
        self.assertEqual(
            policy["classification_inputs"],
            [
                "for_trade_date",
                "trigger_time",
                "current_exchange_time",
                "trade_calendar.is_open",
                "trading_session_boundary",
            ],
        )
        self.assertFalse(policy["consumption_completion_rule"]["uses_n4_outbox_status"])
        self.assertEqual(
            policy["consumption_completion_rule"]["n5_owned_completion_evidence"],
            [
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "common_action_tracking_state",
                "common_event_outbox",
            ],
        )
        self.assertFalse(policy["n3_boundary"]["scans_common_action_tracking_state"])
        self.assertEqual(policy["n3_boundary"]["input_artifact_type"], "n5_active_scope_snapshot_v1")
        self.assertEqual(policy["lunch_break"]["source_gap_policy"], "session_boundary_source_gap_excluded_v1")
        self.assertEqual(policy["post_close"]["backlog_order"], ["event_time ASC", "source_run_id ASC"])

        before_0925 = classify_fastlane_session_phase(
            for_trade_date="20260703",
            trigger_time="2026-07-03T09:24:59+08:00",
            current_exchange_time="2026-07-03T09:24:59+08:00",
            trade_calendar_is_open=True,
        )
        self.assertEqual(before_0925["phase"], "pre_open_before_0925")
        self.assertFalse(before_0925["n5_intake"]["action_eligible_write_allowed"])
        self.assertFalse(before_0925["n3_c1_n3t"]["metric_generation_allowed"])

        after_0925 = classify_fastlane_session_phase(
            for_trade_date="20260703",
            trigger_time="2026-07-03T09:25:00+08:00",
            current_exchange_time="2026-07-03T09:25:00+08:00",
            trade_calendar_is_open=True,
        )
        self.assertEqual(after_0925["phase"], "pre_open_call_auction_after_0925")
        self.assertTrue(after_0925["n5_intake"]["action_eligible_write_allowed"])
        self.assertTrue(after_0925["n5_intake"]["active_scope_artifact_allowed"])
        self.assertFalse(after_0925["n3_c1_n3t"]["metric_generation_allowed"])
        self.assertEqual(after_0925["n3_c1_n3t"]["blocked_until"], "first_closed_minute_available")
        self.assertTrue(after_0925["n5_executed"]["requires_matching_n3t_c1_closed_metric"])

        trading = classify_fastlane_session_phase(
            for_trade_date="20260703",
            trigger_time="2026-07-03T09:31:00+08:00",
            current_exchange_time="2026-07-03T09:32:00+08:00",
            trade_calendar_is_open=True,
        )
        self.assertEqual(trading["phase"], "trading")
        self.assertEqual(trading["n5_intake"]["interval_seconds"], 3)
        self.assertEqual(trading["n3_c1_n3t"]["interval_seconds"], 5)
        self.assertTrue(trading["n3_c1_n3t"]["consumes_only_explicit_active_scope_artifact"])

        lunch = classify_fastlane_session_phase(
            for_trade_date="20260703",
            trigger_time="2026-07-03T11:29:00+08:00",
            current_exchange_time="2026-07-03T11:45:00+08:00",
            trade_calendar_is_open=True,
        )
        self.assertEqual(lunch["phase"], "lunch_break")
        self.assertEqual(lunch["n3_c1_n3t"]["source_gap_policy"], "session_boundary_source_gap_excluded_v1")
        self.assertFalse(lunch["n3_c1_n3t"]["allows_fake_1130_row"])
        self.assertFalse(lunch["n3_c1_n3t"]["allows_1300_to_1130_bridge"])

        post_close = classify_fastlane_session_phase(
            for_trade_date="20260703",
            trigger_time="2026-07-03T15:00:00+08:00",
            current_exchange_time="2026-07-03T15:00:00+08:00",
            trade_calendar_is_open=True,
        )
        self.assertEqual(post_close["phase"], "post_close")
        self.assertTrue(post_close["post_close_drain"]["enabled"])
        self.assertEqual(post_close["post_close_drain"]["backlog_order"], ["event_time ASC", "source_run_id ASC"])

        closed_day = classify_fastlane_session_phase(
            for_trade_date="20260704",
            trigger_time="2026-07-04T09:31:00+08:00",
            current_exchange_time="2026-07-04T09:31:00+08:00",
            trade_calendar_is_open=False,
        )
        self.assertEqual(closed_day["phase"], "closed_day_or_non_trading")
        self.assertFalse(closed_day["n5_intake"]["action_eligible_write_allowed"])
        self.assertFalse(closed_day["n3_c1_n3t"]["metric_generation_allowed"])

    def test_active_worker_policy_maps_session_phase_to_bounded_lane_actions(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_active_worker_policy,
            resolve_fastlane_active_worker_decision,
        )

        policy = build_fastlane_active_worker_policy()

        self.assertEqual(policy["policy_type"], "fastlane_active_worker_policy_v1")
        self.assertEqual(policy["session_phase_policy"], "fastlane_session_phase_policy_v1")
        self.assertEqual(
            set(policy["lanes"]),
            {"n5_action_intake", "n3_c1_n3t_action_confirmation", "n5_action_executed"},
        )

        before_0925 = resolve_fastlane_active_worker_decision(
            lane_key="n5_action_intake",
            session_phase="pre_open_before_0925",
            formal_trigger_matched_available=True,
            closed_minute_available=False,
            matching_n3t_metric_available=False,
        )
        self.assertEqual(before_0925["worker_mode"], "read_only_discovery")
        self.assertFalse(before_0925["writes_enabled_allowed"])
        self.assertEqual(before_0925["blocked_reason"], "pre_open_before_0925_no_write")

        after_0925 = resolve_fastlane_active_worker_decision(
            lane_key="n5_action_intake",
            session_phase="pre_open_call_auction_after_0925",
            formal_trigger_matched_available=True,
            closed_minute_available=False,
            matching_n3t_metric_available=False,
        )
        self.assertEqual(after_0925["worker_mode"], "write_enabled_bounded")
        self.assertTrue(after_0925["writes_enabled_allowed"])
        self.assertEqual(after_0925["required_proof"], "formal_TriggerMatched")

        inactive_cleanup = resolve_fastlane_active_worker_decision(
            lane_key="n5_action_intake",
            session_phase="trading",
            formal_trigger_matched_available=False,
            inactive_trigger_state_changed_available=True,
            closed_minute_available=True,
            matching_n3t_metric_available=False,
        )
        self.assertEqual(inactive_cleanup["worker_mode"], "write_enabled_bounded")
        self.assertTrue(inactive_cleanup["writes_enabled_allowed"])
        self.assertEqual(inactive_cleanup["required_proof"], "inactive_TriggerStateChanged_false")
        self.assertFalse(inactive_cleanup["action_eligible_entry_allowed"])

        preopen_n3 = resolve_fastlane_active_worker_decision(
            lane_key="n3_c1_n3t_action_confirmation",
            session_phase="pre_open_call_auction_after_0925",
            formal_trigger_matched_available=True,
            closed_minute_available=False,
            matching_n3t_metric_available=False,
        )
        self.assertEqual(preopen_n3["worker_mode"], "wait_first_closed_minute")
        self.assertFalse(preopen_n3["writes_enabled_allowed"])
        self.assertEqual(preopen_n3["blocked_reason"], "first_closed_minute_not_available")

        trading_n3 = resolve_fastlane_active_worker_decision(
            lane_key="n3_c1_n3t_action_confirmation",
            session_phase="trading",
            formal_trigger_matched_available=True,
            closed_minute_available=True,
            matching_n3t_metric_available=False,
        )
        self.assertEqual(trading_n3["worker_mode"], "write_enabled_bounded")
        self.assertTrue(trading_n3["writes_enabled_allowed"])
        self.assertTrue(trading_n3["requires_explicit_active_scope_artifact"])

        lunch_n3 = resolve_fastlane_active_worker_decision(
            lane_key="n3_c1_n3t_action_confirmation",
            session_phase="lunch_break",
            formal_trigger_matched_available=True,
            closed_minute_available=True,
            matching_n3t_metric_available=False,
        )
        self.assertEqual(lunch_n3["source_gap_policy"], "session_boundary_source_gap_excluded_v1")
        self.assertFalse(lunch_n3["allows_fake_1130_row"])
        self.assertFalse(lunch_n3["allows_1300_to_1130_bridge"])

        post_close = resolve_fastlane_active_worker_decision(
            lane_key="n5_action_intake",
            session_phase="post_close",
            formal_trigger_matched_available=True,
            closed_minute_available=True,
            matching_n3t_metric_available=False,
        )
        self.assertEqual(post_close["worker_mode"], "time_ordered_drain")
        self.assertEqual(post_close["backlog_order"], ["event_time ASC", "source_run_id ASC"])

        post_close_executed_waiting = resolve_fastlane_active_worker_decision(
            lane_key="n5_action_executed",
            session_phase="post_close",
            formal_trigger_matched_available=True,
            closed_minute_available=True,
            matching_n3t_metric_available=False,
        )
        self.assertEqual(post_close_executed_waiting["worker_mode"], "wait_matching_n3t_metric")
        self.assertFalse(post_close_executed_waiting["writes_enabled_allowed"])
        self.assertEqual(post_close_executed_waiting["blocked_reason"], "matching_n3t_metric_missing")

        post_close_executed_ready = resolve_fastlane_active_worker_decision(
            lane_key="n5_action_executed",
            session_phase="post_close",
            formal_trigger_matched_available=True,
            closed_minute_available=True,
            matching_n3t_metric_available=True,
        )
        self.assertEqual(post_close_executed_ready["worker_mode"], "time_ordered_metric_drain")
        self.assertTrue(post_close_executed_ready["writes_enabled_allowed"])
        self.assertEqual(post_close_executed_ready["backlog_order"], ["event_time ASC", "source_run_id ASC"])

        non_trading = resolve_fastlane_active_worker_decision(
            lane_key="n5_action_executed",
            session_phase="closed_day_or_non_trading",
            formal_trigger_matched_available=True,
            closed_minute_available=True,
            matching_n3t_metric_available=True,
        )
        self.assertEqual(non_trading["worker_mode"], "fail_closed")
        self.assertFalse(non_trading["writes_enabled_allowed"])

    def test_contract_locks_new_labels_and_layer_boundaries(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_contract

        contract = build_fastlane_contract()

        self.assertEqual(contract["lane_id"], "n5_action_confirmation_fastlane_v1")
        self.assertEqual(
            contract["labels"],
            {
                "n5_intake": "com.ashare-v3.n5.action-intake-poller",
                "n3_c1_n3t": "com.ashare-v3.n3.c1-n3t-action-confirmation-poller",
                "n5_executed": "com.ashare-v3.n5.action-executed-poller",
            },
        )
        self.assertEqual(
            contract["pipeline_order"],
            [
                "N4 TriggerMatched",
                "N5 ActionEligible + active tracking",
                "N5 active scope artifact",
                "N3-C1 scoped closed 1m",
                "N3T_C1_CLOSED metric",
                "N5 ActionExecuted",
            ],
        )
        self.assertEqual(contract["n5_market_context_permission"], ["C1 scoped closed 1m context", "N3T metric"])
        self.assertEqual(contract["n5_output_event_types"], ["ActionEligible", "ActionExecuted"])
        self.assertFalse(contract["mutates_n4_outbox"])
        self.assertFalse(contract["touches_n6"])
        self.assertFalse(contract["long_running_worker"])
        self.assertEqual(contract["n3t_metric_lineage"]["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(contract["n3t_metric_lineage"]["metric_role"], "action_confirmation")
        self.assertEqual(contract["n3t_metric_lineage"]["proof_consumer"], "N5")
        self.assertFalse(contract["n3t_metric_lineage"]["not_n5_final_proof"])
        self.assertEqual(contract["session_phase_policy"]["policy_type"], "fastlane_session_phase_policy_v1")
        self.assertEqual(contract["active_worker_policy"]["policy_type"], "fastlane_active_worker_policy_v1")
        self.assertFalse(contract["session_phase_policy"]["consumption_completion_rule"]["uses_n4_outbox_status"])
        self.assertFalse(contract["session_phase_policy"]["n3_boundary"]["scans_common_action_tracking_state"])
        self.assertIn("com.ashare-v3.n3.intraday-proof-poller.n3p", contract["protected_existing_labels"])
        self.assertIn("com.ashare-v3.n4.proof-discovery-poller", contract["protected_existing_labels"])

    def test_launchd_plan_uses_only_new_bounded_labels(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_launchd_plan,
        )

        plan = build_fastlane_launchd_plan(working_directory=WORKING_DIRECTORY)

        self.assertEqual(set(plan["launchd_plist_keys"]), {"n5_intake", "n3_c1_n3t", "n5_executed"})
        self.assertEqual({plan[key]["label"] for key in plan["launchd_plist_keys"]}, set(FASTLANE_LABELS.values()))
        self.assertEqual(plan["activation_policy"], "load_safe_activation_guard_v1")
        self.assertEqual(plan["activation_intervals_seconds"]["n5_intake"], 3)
        self.assertEqual(plan["activation_intervals_seconds"]["n3_c1_n3t"], 5)
        self.assertEqual(plan["activation_intervals_seconds"]["n5_executed"], 3)

        joined_args = []
        for key in plan["launchd_plist_keys"]:
            plist = plan[key]["plist"]
            self.assertNotIn("Disabled", plist)
            self.assertNotIn("StartInterval", plist)
            self.assertFalse(plist["RunAtLoad"])
            self.assertFalse(plist["KeepAlive"])
            self.assertEqual(plist["WorkingDirectory"], WORKING_DIRECTORY)
            self.assertEqual(plist["EnvironmentVariables"]["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertEqual(plist["EnvironmentVariables"]["PYTHONPATH"], "src:scripts:.")
            self.assertNotIn("ASHARE_V3_POSTGRES_DSN", plist["EnvironmentVariables"])
            self.assertIn("--activation-guard", plist["ProgramArguments"])
            script_path = Path(plist["ProgramArguments"][1])
            self.assertTrue(script_path.exists(), script_path)
            joined_args.extend(plist["ProgramArguments"])

        joined = " ".join(joined_args)
        for placeholder in (
            "__FOR_TRADE_DATE__",
            "__SOURCE_TRIGGER_RUN_ID__",
            "__SOURCE_METRIC_RUN_ID__",
            "__ACTION_RUN_ID__",
            "__CONSUMER_NAME__",
            "__MAX_EVENTS__",
        ):
            self.assertNotIn(placeholder, joined)
        self.assertNotIn("--execute", joined)
        self.assertNotIn("--user-confirmed", joined)
        for forbidden in (
            "com.ashare-v3.n3.intraday-proof-poller",
            "com.ashare-v3.n4.proof-discovery-poller",
            "run_n3_intraday_proof_poller_once.py",
            "run_n4_intraday_proof_discovery_poll_once.py",
            "run_n3_intraday_b1_c1_b2_auto_poll_once.py",
            "run_n6",
            "launchctl",
        ):
            self.assertNotIn(forbidden, joined)
        self.assertFalse(plan["forbidden_operation_proof"]["launchd_loaded_or_started"])
        self.assertFalse(plan["forbidden_operation_proof"]["n4_outbox_updated"])
        self.assertFalse(plan["forbidden_operation_proof"]["n6_touched"])

    def test_materialized_plists_are_plan_only_and_valid(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import write_fastlane_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            report = write_fastlane_launchd_plan(output_dir=Path(tmpdir), working_directory=WORKING_DIRECTORY)

            self.assertTrue(Path(report["report_path"]).exists())
            for key in report["launchd_plist_keys"]:
                plist_path = Path(report[key]["plist_path"])
                self.assertTrue(plist_path.exists())
                plist = plistlib.loads(plist_path.read_bytes())
                self.assertNotIn("Disabled", plist)
                self.assertNotIn("StartInterval", plist)
                self.assertFalse(plist["RunAtLoad"])
                self.assertFalse(plist["KeepAlive"])
                self.assertEqual(_plist_placeholders(plist), [])

    def test_activation_guard_is_side_effect_free(self) -> None:
        from plan_n5_n3t_fastlane_launchd import main

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "guard.json"
            exit_code = main(
                [
                    "--activation-guard",
                    "com.ashare-v3.n5.action-intake-poller",
                    "--json-output-path",
                    str(output_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["verdict"], "FASTLANE_ACTIVATION_REQUIRED")
        self.assertEqual(payload["label"], "com.ashare-v3.n5.action-intake-poller")
        self.assertFalse(payload["forbidden_operation_proof"]["database_written_by_plan"])
        self.assertFalse(payload["forbidden_operation_proof"]["launchd_loaded_or_started"])
        self.assertFalse(payload["forbidden_operation_proof"]["n4_outbox_updated"])
        self.assertFalse(payload["forbidden_operation_proof"]["n6_touched"])

    def test_n3_c1_n3t_shell_reads_only_explicit_active_scope_artifacts(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            artifact_dir.mkdir()
            (artifact_dir / "n5_active_scope_snapshot_v1.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 1,
                        "source_trigger_run_id": "n4-run",
                        "action_run_id": "n5-run",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                [
                    "--fastlane-lane-id",
                    "n5_action_confirmation_fastlane_v1",
                    "--active-scope-artifact-dir",
                    str(artifact_dir),
                    "--output-dir",
                    str(output_dir),
                    "--max-runtime-seconds",
                    "5",
                ]
            )

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_SHELL_READY")
        self.assertEqual(manifest["active_scope_artifact_count"], 1)
        self.assertTrue(manifest["boundary"]["reads_only_explicit_n5_active_scope_artifacts"])
        self.assertFalse(manifest["boundary"]["scans_n5_db"])
        self.assertFalse(manifest["boundary"]["writes_db"])
        self.assertFalse(manifest["boundary"]["pulls_market_data"])
        self.assertFalse(manifest["boundary"]["full_market_fallback"])

    def test_n5_runner_resolves_activation_config_runtime_inputs(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                        "runtime_inputs": {
                            "n5_action_intake": {
                                "source_trigger_run_id": "trigger_run_20260703_0931",
                                "source_metric_run_id": "n3t_action_confirmation_metric_20260703_until_0931",
                                "action_run_id": "n5_live_tracking_20260703_until_0931",
                                "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def plan_provider(args):
                self.assertEqual(args.for_trade_date, "20260703")
                self.assertEqual(args.source_trigger_run_id, "trigger_run_20260703_0931")
                self.assertEqual(args.source_metric_run_id, "n3t_action_confirmation_metric_20260703_until_0931")
                self.assertEqual(args.action_run_id, "n5_live_tracking_20260703_until_0931")
                self.assertEqual(args.consumer_name, "n5_live_tracking_poller_v2_fastlane")
                self.assertEqual(args.max_events, 300)
                self.assertEqual(args.fastlane_phase, "intake")
                return {
                    "action_events": [],
                    "inbox_checkpoint_intent": {"updates_n4_outbox": False},
                    "active_scope_snapshot_artifact": {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 0,
                    },
                }

            manifest = run_n5_live_tracking_poller_once(
                ["--activation-config", str(config_path), "--fastlane-phase", "intake"],
                plan_provider=plan_provider,
            )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
        self.assertFalse(manifest["writes_enabled"])
        self.assertFalse(manifest["artifact_writes_enabled"])
        self.assertEqual(
            manifest["active_scope_artifact_write_result"],
            {
                "executed": False,
                "reason": "artifact_write_disabled",
                "artifact_writes_enabled": False,
            },
        )

    def test_n5_runner_phase_gate_blocks_preopen_before_0925_artifact_write(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                        "runtime_inputs": {
                            "n5_action_intake": {
                                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0924",
                                "action_run_id": "n5_live_tracking_20260703_until_0924__fastlane_v1",
                                "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                            }
                        },
                        "session_context": {
                            "trigger_time": "2026-07-03T09:24:59+08:00",
                            "current_exchange_time": "2026-07-03T09:24:59+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": False,
                            "matching_n3t_metric_available": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n5_live_tracking_poller_once(
                [
                    "--activation-config",
                    str(config_path),
                    "--fastlane-phase",
                    "intake",
                    "--write-active-scope-artifact",
                    "--user-confirmed",
                ],
                plan_provider=lambda _args: self.fail("phase gate must block before planning"),
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N5_LIVE_TRACKING_POLLER")
        self.assertEqual(manifest["blocked_reason"], "fastlane_worker_pre_open_before_0925_no_write")
        self.assertFalse(manifest["writes_enabled"])
        self.assertFalse(manifest["artifact_writes_enabled"])

    def test_n5_runner_scheduler_quiet_suppresses_phase_gate_noop(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO

        from run_n5_live_tracking_poller_once import main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "runtime_inputs": {
                            "n5_action_intake": {
                                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0931",
                                "action_run_id": "n5_live_tracking_20260703_until_0931__fastlane_v1",
                                "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                            }
                        },
                        "session_context": {
                            "trigger_time": "2026-07-04T03:00:00+08:00",
                            "current_exchange_time": "2026-07-04T03:00:00+08:00",
                            "trade_calendar_is_open": False,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": False,
                            "matching_n3t_metric_available": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--activation-config",
                        str(config_path),
                        "--fastlane-phase",
                        "intake",
                        "--execute",
                        "--user-confirmed",
                        "--write-active-scope-artifact",
                        "--scheduler-quiet",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), "")

    def test_n3_runner_scheduler_quiet_suppresses_phase_gate_noop(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO

        from run_n3_c1_n3t_action_confirmation_fastlane_once import main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(root / "scope"),
                        "n3_c1_n3t_artifact_dir": str(root / "n3"),
                        "session_context": {
                            "trigger_time": "2026-07-04T03:00:00+08:00",
                            "current_exchange_time": "2026-07-04T03:00:00+08:00",
                            "trade_calendar_is_open": False,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                            "matching_n3t_metric_available": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--activation-config",
                        str(config_path),
                        "--execute",
                        "--user-confirmed",
                        "--scheduler-quiet",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), "")

    def test_n5_runner_runtime_clock_session_policy_derives_trading_phase(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                        "runtime_inputs": {
                            "n5_action_intake": {
                                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0931",
                                "action_run_id": "n5_live_tracking_20260703_until_0931__fastlane_v1",
                                "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                            }
                        },
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                            "current_exchange_time_override": "2026-07-03T09:31:30+08:00",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def plan_provider(args):
                self.assertEqual(args.fastlane_session_phase, "trading")
                self.assertEqual(args.fastlane_active_worker_decision["worker_mode"], "write_enabled_bounded")
                return {
                    "action_events": [],
                    "inbox_checkpoint_intent": {"updates_n4_outbox": False},
                    "active_scope_snapshot_artifact": {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 0,
                    },
                }

            manifest = run_n5_live_tracking_poller_once(
                ["--activation-config", str(config_path), "--fastlane-phase", "intake"],
                plan_provider=plan_provider,
            )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
        self.assertEqual(manifest["fastlane"]["session_phase"], "trading")
        self.assertFalse(manifest["writes_enabled"])

    def test_n5_intake_discovery_trigger_time_must_match_trade_date(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                            "current_exchange_time_override": "2026-07-03T09:31:30+08:00",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def discovery_provider(_args, _config):
                return {
                    "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0925",
                    "trigger_time": "2026-07-02T09:25:00+08:00",
                    "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0925__fastlane_v1",
                    "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                    "n5_intake_event_kind": "formal_TriggerMatched",
                }

            manifest = run_n5_live_tracking_poller_once(
                [
                    "--activation-config",
                    str(config_path),
                    "--fastlane-phase",
                    "intake",
                    "--execute",
                    "--user-confirmed",
                ],
                activation_discovery_provider=discovery_provider,
                plan_provider=lambda _args: self.fail("plan_provider must not run for stale trigger_time"),
                writer=lambda _args, _plan: {"executed": True, "rows_written": 0},
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N5_LIVE_TRACKING_POLLER")
        self.assertEqual(manifest["blocked_reason"], "fastlane_worker_closed_day_or_non_trading")
        self.assertFalse(manifest["writes_enabled"])

    def test_n5_runner_activation_config_missing_dynamic_ids_fails_closed(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n5_live_tracking_poller_once(
                ["--activation-config", str(config_path), "--fastlane-phase", "intake"]
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N5_LIVE_TRACKING_POLLER")
        self.assertIn("source_trigger_run_id", manifest["blocked_reason"])

    def test_n5_write_enabled_activation_config_requires_policy_review_ref_at_runner(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                        "runtime_inputs": {
                            "n5_action_intake": {
                                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0931",
                                "action_run_id": "n5_live_tracking_20260703_until_0931__fastlane_v1",
                                "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                            }
                        },
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                            "current_exchange_time_override": "2026-07-03T09:31:30+08:00",
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": True},
                            "n5_action_executed": {"execute": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n5_live_tracking_poller_once(
                [
                    "--activation-config",
                    str(config_path),
                    "--fastlane-phase",
                    "intake",
                    "--execute",
                    "--user-confirmed",
                    "--write-active-scope-artifact",
                ],
                plan_provider=lambda _args: self.fail("plan_provider must not run without policy review ref"),
                writer=lambda _args, _plan: {"executed": True, "rows_written": 1},
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N5_LIVE_TRACKING_POLLER")
        self.assertIn("active_worker_policy_review_ref", manifest["blocked_reason"])
        self.assertFalse(manifest["writes_enabled"])
        self.assertFalse(manifest["artifact_writes_enabled"])

    def test_n5_runtime_deferred_waiting_review_path_blocks_writes_without_inline_ref(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_path = root / "active_worker_policy_review.json"
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            review_path.write_text(
                json.dumps(
                    {
                        "result": "WAITING",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_WAITING_FOR_MONITOR_PASS",
                        "policy_type": "fastlane_active_worker_policy_v1",
                        "for_trade_date": "20260706",
                        "active_worker_write_enabled_ready": False,
                        "automatic_chain_verified": False,
                        "manual_gate_required": False,
                        "session_phase": "closed_day_or_non_trading",
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": [
                            "waiting_for_actionable_session_phase:closed_day_or_non_trading",
                            "waiting_for_n4_triggermatched",
                        ],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260706",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                        "active_worker_policy_review_path": str(review_path),
                        "active_worker_policy_review_path_policy": {
                            "policy_type": "fastlane_active_worker_policy_review_runtime_resolved_v1",
                            "resolution": "runtime_read_only_latest_artifact",
                            "authorization_timing": "runtime_deferred_to_runner",
                            "no_secret_embedded": True,
                        },
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                            "current_exchange_time_override": "2026-07-06T09:31:30+08:00",
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": False},
                            "n5_action_executed": {"execute": False},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n5_live_tracking_poller_once(
                [
                    "--activation-config",
                    str(config_path),
                    "--fastlane-phase",
                    "intake",
                    "--execute",
                    "--user-confirmed",
                    "--write-active-scope-artifact",
                ],
                activation_discovery_provider=lambda _args, _config: self.fail(
                    "WAITING review must block before discovery"
                ),
                plan_provider=lambda _args: self.fail("WAITING review must block before planning"),
                writer=lambda _args, _plan: {"executed": True, "rows_written": 0},
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N5_LIVE_TRACKING_POLLER")
        self.assertIn("active_worker_policy_review_ref_not_ready", manifest["blocked_reason"])
        self.assertFalse(manifest["writes_enabled"])
        self.assertFalse(manifest["artifact_writes_enabled"])

    def test_n5_runtime_deferred_pass_idle_without_n4_waits_cleanly(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_path = root / "active_worker_policy_review.json"
            config_path = root / "activation_config.json"
            review_path.write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                        "policy_type": "fastlane_active_worker_policy_v1",
                        "for_trade_date": "20260706",
                        "active_worker_write_enabled_ready": True,
                        "automatic_chain_verified": False,
                        "activation_scope": "idle_open_scheduler",
                        "manual_gate_required": False,
                        "session_phase": "trading",
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": ["waiting_for_n4_triggermatched"],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260706",
                        "n5_intake_max_events": 300,
                        "active_worker_policy_review_path": str(review_path),
                        "active_worker_policy_review_path_policy": {
                            "policy_type": "fastlane_active_worker_policy_review_runtime_resolved_v1",
                            "resolution": "runtime_read_only_latest_artifact",
                            "authorization_timing": "runtime_deferred_to_runner",
                            "no_secret_embedded": True,
                        },
                        "session_context": {
                            "trigger_time": "2026-07-06T09:31:00+08:00",
                            "current_exchange_time": "2026-07-06T09:31:30+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": False,
                            "inactive_trigger_state_changed_available": False,
                            "closed_minute_available": True,
                            "matching_n3t_metric_available": False,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": False},
                            "n5_action_executed": {"execute": False},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n5_live_tracking_poller_once(
                [
                    "--activation-config",
                    str(config_path),
                    "--fastlane-phase",
                    "intake",
                    "--execute",
                    "--user-confirmed",
                    "--write-active-scope-artifact",
                ],
                plan_provider=lambda _args: self.fail("waiting_for_n4_triggermatched must not plan"),
                writer=lambda _args, _plan: {"executed": True, "rows_written": 1},
            )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_READINESS_WAITING")
        self.assertEqual(manifest["reason"], "waiting_for_n4_triggermatched")
        self.assertFalse(manifest["writes_enabled"])
        self.assertFalse(manifest["artifact_writes_enabled"])

    def test_n5_write_enabled_activation_config_resolves_policy_review_path_at_runner(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_path = root / "active_worker_policy_review.json"
            config_path = root / "activation_config.json"
            review_path.write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                        "policy_type": "fastlane_active_worker_policy_v1",
                        "for_trade_date": "20260703",
                        "active_worker_write_enabled_ready": True,
                        "automatic_chain_verified": True,
                        "manual_gate_required": False,
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": [],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "active_worker_policy_review_path": str(review_path),
                        "runtime_inputs": {
                            "n5_action_intake": {
                                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0931",
                                "action_run_id": "n5_live_tracking_20260703_until_0931__fastlane_v1",
                                "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                            }
                        },
                        "session_context": {
                            "trigger_time": "2026-07-03T09:31:00+08:00",
                            "current_exchange_time": "2026-07-03T09:32:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                            "matching_n3t_metric_available": False,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": False,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": False},
                            "n5_action_executed": {"execute": False},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n5_live_tracking_poller_once(
                [
                    "--activation-config",
                    str(config_path),
                    "--fastlane-phase",
                    "intake",
                    "--execute",
                    "--user-confirmed",
                ],
                plan_provider=lambda _args: {
                    "action_events": [],
                    "inbox_checkpoint_intent": {"updates_n4_outbox": False},
                },
                writer=lambda _args, _plan: {"executed": True, "rows_written": 0},
            )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_EXECUTE_PASS")
        self.assertTrue(manifest["writes_enabled"])
        self.assertFalse(manifest["artifact_writes_enabled"])

    def test_scheduler_quiet_treats_policy_guard_fail_closed_as_clean_noop(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            main as n3_c1_n3t_main,
        )
        from run_n5_live_tracking_poller_once import main as n5_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                        "runtime_inputs": {
                            "n5_action_intake": {
                                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0931",
                                "action_run_id": "n5_live_tracking_20260703_until_0931__fastlane_v1",
                                "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                            },
                            "n5_action_executed": {
                                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0931",
                                "source_metric_run_id": "n3t_action_confirmation_metric_20260703_until_0931__fastlane_raw_prevday_c1_amount_v1",
                                "action_run_id": "n5_live_tracking_20260703_until_0931__fastlane_v1",
                                "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                            },
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": True},
                            "n5_action_executed": {"execute": True},
                        },
                        "active_worker_policy_review_ref": {
                            "result": "PASS",
                            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                            "for_trade_date": "20260703",
                            "active_worker_write_enabled_ready": True,
                            "automatic_chain_verified": True,
                            "bootstrap_mode": "automatic_chain_verified",
                            "chain_backlog": {
                                "n5_intake_remaining": 0,
                                "n3t_metric_remaining": 0,
                            },
                            "waiting_reasons": [],
                        },
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": False,
                            "current_exchange_time_override": "2026-07-03T08:30:00+08:00",
                        },
                        "n3_c1_n3t_current_day_source_artifact_dir": str(root / "current_day_source"),
                        "n3_c1_n3t_current_day_source_provider": "mootdx_today_minute_adapter_v1",
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(root / "metric_context_source"),
                        "n3_c1_n3t_previous_day_context_artifact_dir": str(root / "previous_day_context"),
                        "n3_c1_n3t_previous_day_context_provider": "postgres_previous_day_raw_c1_context_v1",
                        "n3_c1_n3t_n3t_writer_adapter": "postgres_n3t_action_confirmation_metric_writer_v1",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            n5_intake_stdout = StringIO()
            with redirect_stdout(n5_intake_stdout):
                n5_intake_exit = n5_main(
                    [
                        "--activation-config",
                        str(config_path),
                        "--fastlane-phase",
                        "intake",
                        "--execute",
                        "--user-confirmed",
                        "--write-active-scope-artifact",
                        "--scheduler-quiet",
                        "--json",
                    ]
                )
            n5_executed_stdout = StringIO()
            with redirect_stdout(n5_executed_stdout):
                n5_executed_exit = n5_main(
                    [
                        "--activation-config",
                        str(config_path),
                        "--fastlane-phase",
                        "executed",
                        "--execute",
                        "--user-confirmed",
                        "--scheduler-quiet",
                        "--json",
                    ]
                )
            n3_stdout = StringIO()
            with redirect_stdout(n3_stdout):
                n3_exit = n3_c1_n3t_main(
                    [
                        "--activation-config",
                        str(config_path),
                        "--execute",
                        "--user-confirmed",
                        "--scheduler-quiet",
                        "--json",
                    ]
                )

        self.assertEqual(n5_intake_exit, 0)
        self.assertEqual(n5_executed_exit, 0)
        self.assertEqual(n3_exit, 0)
        self.assertEqual(n5_intake_stdout.getvalue(), "")
        self.assertEqual(n5_executed_stdout.getvalue(), "")
        self.assertEqual(n3_stdout.getvalue(), "")

    def test_n5_intake_activation_config_uses_read_only_discovery_for_missing_runtime_ids(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def discovery_provider(args, _config):
                self.assertEqual(args.fastlane_phase, "intake")
                return {
                    "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0934",
                    "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0934__fastlane_v1",
                    "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                }

            def plan_provider(args):
                self.assertEqual(args.for_trade_date, "20260703")
                self.assertEqual(args.source_trigger_run_id, "trigger_provisional_ordinary_20260703_until_0934")
                self.assertEqual(
                    args.action_run_id,
                    "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0934__fastlane_v1",
                )
                self.assertEqual(args.consumer_name, "n5_live_tracking_poller_v2_fastlane")
                self.assertEqual(args.source_metric_run_id, "")
                self.assertEqual(args.max_events, 300)
                self.assertLessEqual(len(Path(args.active_scope_artifact_path).name), 96)
                return {
                    "action_events": [],
                    "inbox_checkpoint_intent": {"updates_n4_outbox": False},
                    "active_scope_snapshot_artifact": {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 0,
                    },
                }

            manifest = run_n5_live_tracking_poller_once(
                ["--activation-config", str(config_path), "--fastlane-phase", "intake"],
                activation_discovery_provider=discovery_provider,
                plan_provider=plan_provider,
            )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
        self.assertFalse(manifest["writes_enabled"])
        self.assertFalse(manifest["artifact_writes_enabled"])
        self.assertEqual(manifest["active_scope_artifact_write_result"]["reason"], "artifact_write_disabled")

    def test_n5_intake_artifact_write_requires_explicit_authorization_and_uses_short_path(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "activation_config.json"
            scope_dir = root / "scope"
            very_long_source_run_id = (
                "trigger_provisional_ordinary_20260703_until_0931__"
                "realtime_action_confirmation_metric_20260703_until_0931__asset_all__"
                "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
                "atomic_rule_v1_period_rollover_guard_v1"
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": str(scope_dir),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def discovery_provider(_args, _config):
                return {
                    "source_trigger_run_id": very_long_source_run_id,
                    "action_run_id": f"n5_live_tracking_20260703__{very_long_source_run_id}__fastlane_v1",
                    "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                }

            def plan_provider(args):
                self.assertLessEqual(len(Path(args.active_scope_artifact_path).name), 96)
                self.assertIn("0931", Path(args.active_scope_artifact_path).name)
                return {
                    "action_events": [],
                    "inbox_checkpoint_intent": {"updates_n4_outbox": False},
                    "active_scope_snapshot_artifact": {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 1,
                    },
                }

            manifest = run_n5_live_tracking_poller_once(
                [
                    "--activation-config",
                    str(config_path),
                    "--fastlane-phase",
                    "intake",
                    "--write-active-scope-artifact",
                    "--user-confirmed",
                ],
                activation_discovery_provider=discovery_provider,
                plan_provider=plan_provider,
            )

            written_path = Path(manifest["active_scope_artifact_write_result"]["path"])
            written_path_exists = written_path.exists()

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
        self.assertFalse(manifest["writes_enabled"])
        self.assertTrue(manifest["artifact_writes_enabled"])
        self.assertTrue(written_path_exists)
        self.assertLessEqual(len(written_path.name), 96)
        self.assertEqual(manifest["active_scope_artifact_write_result"]["artifact_type"], "n5_active_scope_snapshot_v1")

    def test_n5_executed_activation_config_requires_discovered_n3t_metric(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def discovery_provider(args, _config):
                self.assertEqual(args.fastlane_phase, "executed")
                return {
                    "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0934",
                    "source_metric_run_id": "n3t_action_confirmation_metric_20260703_until_0934__fastlane_v1",
                    "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0934__fastlane_v1",
                    "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                }

            def plan_provider(args):
                self.assertEqual(args.source_metric_run_id, "n3t_action_confirmation_metric_20260703_until_0934__fastlane_v1")
                return {
                    "action_events": [],
                    "inbox_checkpoint_intent": {"updates_n4_outbox": False},
                    "active_scope_snapshot_artifact": {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 0,
                    },
                }

            manifest = run_n5_live_tracking_poller_once(
                ["--activation-config", str(config_path), "--fastlane-phase", "executed"],
                activation_discovery_provider=discovery_provider,
                plan_provider=plan_provider,
            )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
        self.assertFalse(manifest["writes_enabled"])

    def test_n5_executed_activation_config_missing_n3t_metric_fails_closed(self) -> None:
        from run_n5_live_tracking_poller_once import run_n5_live_tracking_poller_once

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n5_live_tracking_poller_once(
                ["--activation-config", str(config_path), "--fastlane-phase", "executed"],
                activation_discovery_provider=lambda _args, _config: {
                    "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0934",
                    "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0934__fastlane_v1",
                    "consumer_name": "n5_live_tracking_poller_v2_fastlane",
                },
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N5_LIVE_TRACKING_POLLER")
        self.assertEqual(manifest["blocked_reason"], "source_metric_run_id_required")

    def test_n5_executed_phase_default_provider_does_not_consume_n4_events(self) -> None:
        import run_n5_live_tracking_poller_once as runner

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def cursor(self):
                return FakeCursor()

        args = argparse.Namespace(
            dsn="postgresql:///unused",
            fastlane_phase="executed",
            for_trade_date="20260703",
            source_trigger_run_id="trigger_provisional_ordinary_20260703_until_0931",
            source_metric_run_id="n3t_action_confirmation_metric_20260703_until_0931__fastlane_v1",
            action_run_id="n5_live_tracking_20260703_until_0931__fastlane_v1",
            consumer_name="n5_live_tracking_poller_v2_fastlane",
            max_events=300,
        )
        captured = {}

        def fake_build_live_tracking_plan(**kwargs):
            captured.update(kwargs)
            return {
                "action_events": [],
                "tracking_updates": [],
                "consumed_n4_events": [],
                "inbox_checkpoint_intent": {"source_event_ids": [], "updates_n4_outbox": False},
                "active_scope_snapshot_artifact": {
                    "artifact_type": "n5_active_scope_snapshot_v1",
                    "scope_count": 0,
                },
                "summary": {"action_executed_count": 0},
            }

        with (
            patch.object(runner.psycopg, "connect", return_value=FakeConnection()),
            patch.object(runner, "_fetch_pending_n4_rows", return_value=[{"event_type": "TriggerMatched"}]),
            patch.object(runner, "_fetch_active_tracking_rows", return_value=[{"state_key": "active"}]),
            patch.object(runner, "_fetch_metric_rows", return_value=[{"projection_run_id": args.source_metric_run_id}]),
            patch.object(runner, "_fetch_existing_action_event_keys", return_value={"existing"}),
            patch.object(runner, "build_live_tracking_plan", side_effect=fake_build_live_tracking_plan),
        ):
            plan = runner._default_plan_provider(args)

        self.assertEqual(plan["summary"]["action_executed_count"], 0)
        self.assertEqual(captured["n4_event_rows"], [])
        self.assertEqual(captured["active_tracking_rows"], [{"state_key": "active"}])
        self.assertEqual(captured["metric_rows"], [{"projection_run_id": args.source_metric_run_id}])

    def test_n5_executed_phase_writer_does_not_write_inbox_or_checkpoint(self) -> None:
        import run_n5_live_tracking_poller_once as runner

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def cursor(self):
                return FakeCursor()

            def commit(self):
                return None

        args = argparse.Namespace(
            dsn="postgresql:///unused",
            fastlane_phase="executed",
            action_run_id="n5_live_tracking_20260703_until_0931__fastlane_v1",
            consumer_name="n5_live_tracking_poller_v2_fastlane",
            source_metric_run_id="n3t_action_confirmation_metric_20260703_until_0931__fastlane_v1",
        )
        plan = {
            "tracking_updates": [{"state_key": "executed"}],
            "action_events": [{"event_type": "ActionExecuted"}],
            "consumed_n4_events": [{"event_type": "TriggerMatched"}],
        }

        with (
            patch.object(runner.psycopg, "connect", return_value=FakeConnection()),
            patch.object(runner, "_upsert_tracking_states", return_value=1) as tracking,
            patch.object(runner, "_insert_action_outbox_events", return_value=1) as outbox,
            patch.object(runner, "_insert_inbox_rows", side_effect=AssertionError("executed phase must not write inbox")) as inbox,
            patch.object(runner, "_upsert_checkpoints", side_effect=AssertionError("executed phase must not write checkpoint")) as checkpoint,
        ):
            write_result = runner._default_execute_writer(args, plan)

        tracking.assert_called_once()
        outbox.assert_called_once()
        inbox.assert_not_called()
        checkpoint.assert_not_called()
        self.assertEqual(write_result["common_action_tracking_state"], 1)
        self.assertEqual(write_result["common_event_outbox"], 1)
        self.assertEqual(write_result["common_event_inbox"], 0)
        self.assertEqual(write_result["common_event_consumer_checkpoint"], 0)

    def test_n5_manifest_reports_cross_run_tracking_rollback_scope(self) -> None:
        import run_n5_live_tracking_poller_once as runner

        args = argparse.Namespace(
            action_run_id="n5_live_tracking_20260703__false_only__fastlane_v1",
            source_trigger_run_id="trigger_provisional_ordinary_20260703_until_0944__false_only",
            source_metric_run_id="",
            for_trade_date="20260703",
            consumer_name="n5_live_tracking_poller_v2_fastlane",
            fastlane_lane_id="n5_action_confirmation_fastlane_v1",
            fastlane_phase="intake",
            fastlane_session_phase="trading",
            fastlane_active_worker_decision={},
            execute=True,
            user_confirmed=True,
            write_active_scope_artifact=False,
            max_events=300,
            max_runtime_seconds=30,
        )
        plan = {
            "tracking_updates": [
                {
                    "run_id": "n5_live_tracking_20260703__previous_match__fastlane_v1",
                    "state_key": "stock|SH|600000|BUY_MAIN",
                    "action_state": "expired",
                }
            ],
            "action_events": [],
            "active_scope_snapshot_artifact": {"artifact_type": "n5_active_scope_snapshot_v1", "scope_count": 0},
        }

        manifest = runner._build_manifest(args, "invocation", plan, 10.0, lambda: 11.0)

        rollback = manifest["rollback_contract"]
        self.assertEqual(
            rollback["affected_tracking_run_ids"],
            [
                "n5_live_tracking_20260703__false_only__fastlane_v1",
                "n5_live_tracking_20260703__previous_match__fastlane_v1",
            ],
        )
        self.assertTrue(rollback["requires_tracking_restore"])

    def test_n5_executed_default_discovery_matches_source_trigger_minute(self) -> None:
        from run_n5_live_tracking_poller_once import _discover_executed_runtime_inputs

        class FakeCursor:
            def __init__(self):
                self.calls = 0
                self.params = []

            def execute(self, _sql, params):
                self.calls += 1
                self.params.append(params)

            def fetchone(self):
                if self.calls == 1:
                    return {
                        "run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0934__fastlane_v1",
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0934__fastlane_v1",
                        "trigger_time": "2026-07-03T09:34:00+08:00",
                    }
                if self.calls == 2:
                    return {
                        "projection_run_id": "n3t_action_confirmation_metric_20260703_until_0934__fastlane_v1",
                        "latest_metric_time": "2026-07-03T09:35:00+08:00",
                    }
                return None

        args = argparse.Namespace(for_trade_date="20260703")
        cursor = FakeCursor()
        output = _discover_executed_runtime_inputs(cursor, args)

        self.assertEqual(output["source_metric_run_id"], "n3t_action_confirmation_metric_20260703_until_0934__fastlane_v1")
        self.assertEqual(output["trigger_time"], "2026-07-03T09:34:00+08:00")
        self.assertIn(
            ("20260703", "%until_0934%", "^n3t_action_confirmation_metric_20260703_until_0934__fastlane.*$"),
            cursor.params,
        )

    def test_n5_executed_default_discovery_rejects_non_fastlane_n3t_metric_run(self) -> None:
        from run_n5_live_tracking_poller_once import _discover_executed_runtime_inputs

        class FakeCursor:
            def __init__(self):
                self.calls = 0
                self.sql_by_call = []
                self.params = []

            def execute(self, sql, params):
                self.calls += 1
                self.sql_by_call.append(str(sql))
                self.params.append(params)

            def fetchone(self):
                if self.calls == 1:
                    return {
                        "run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0938__fastlane_v1",
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0938__fastlane_v1",
                    }
                metric_sql = self.sql_by_call[-1].lower()
                metric_params = self.params[-1]
                if "projection_run_id ~" not in metric_sql or len(metric_params) < 3:
                    return {
                        "projection_run_id": (
                            "n3t_action_confirmation_metric_20260703_until_0938"
                            "__time_ordered_backlog_raw_prevday_c1_amount_v1"
                        ),
                        "latest_metric_time": "2026-07-03T09:39:00+08:00",
                    }
                return {
                    "projection_run_id": (
                        "n3t_action_confirmation_metric_20260703_until_0938"
                        "__fastlane_raw_prevday_c1_amount_v1"
                    ),
                    "latest_metric_time": "2026-07-03T09:39:00+08:00",
                }

        args = argparse.Namespace(for_trade_date="20260703")
        cursor = FakeCursor()
        output = _discover_executed_runtime_inputs(cursor, args)

        self.assertEqual(
            output["source_metric_run_id"],
            "n3t_action_confirmation_metric_20260703_until_0938__fastlane_raw_prevday_c1_amount_v1",
        )
        metric_params = [params for params in cursor.params if len(params) >= 3]
        self.assertTrue(metric_params)
        self.assertIn(
            "^n3t_action_confirmation_metric_20260703_until_0938__fastlane",
            metric_params[0][2],
        )

    def test_n5_executed_default_discovery_scopes_to_fastlane_tracking_run_family(self) -> None:
        from run_n5_live_tracking_poller_once import _discover_executed_runtime_inputs

        class FakeCursor:
            def __init__(self):
                self.calls = 0
                self.sql_by_call = []
                self.params = []

            def execute(self, sql, params):
                self.calls += 1
                self.sql_by_call.append(str(sql))
                self.params.append(params)

            def fetchone(self):
                if self.calls == 1:
                    sql = self.sql_by_call[-1].lower()
                    if "run_id ~" not in sql:
                        return {
                            "run_id": "n5_live_tracking_20260703__legacy_consumer",
                            "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0931__legacy",
                        }
                    return {
                        "run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0933__fastlane_v1",
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0933__fastlane_v1",
                    }
                if self.calls == 2:
                    return {
                        "projection_run_id": "n3t_action_confirmation_metric_20260703_until_0933__fastlane_v1",
                        "latest_metric_time": "2026-07-03T09:34:00+08:00",
                    }
                return None

        args = argparse.Namespace(for_trade_date="20260703")
        cursor = FakeCursor()
        output = _discover_executed_runtime_inputs(cursor, args)

        self.assertEqual(
            output["action_run_id"],
            "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0933__fastlane_v1",
        )
        self.assertEqual(output["source_metric_run_id"], "n3t_action_confirmation_metric_20260703_until_0933__fastlane_v1")
        self.assertIn(r"^n5_live_tracking_.*__fastlane_v1$", cursor.params[0])

    def test_n5_intake_default_discovery_includes_inactive_state_change_runs(self) -> None:
        from run_n5_live_tracking_poller_once import _discover_intake_runtime_inputs

        class FakeCursor:
            def __init__(self):
                self.sql = ""
                self.params = None

            def execute(self, sql, params):
                self.sql = str(sql)
                self.params = params

            def fetchone(self):
                sql = self.sql.lower()
                if "triggerstatechanged" in sql and "trigger_live" in sql and "false" in sql:
                    return {
                        "source_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_false_only",
                        "trigger_time": "2026-07-03T09:43:00+08:00",
                    }
                return None

        args = argparse.Namespace(for_trade_date="20260703")
        cursor = FakeCursor()
        output = _discover_intake_runtime_inputs(cursor, args)

        self.assertEqual(
            output["source_trigger_run_id"],
            "trigger_provisional_ordinary_20260703_until_0943__fastlane_false_only",
        )
        self.assertEqual(output["trigger_time"], "2026-07-03T09:43:00+08:00")
        self.assertEqual(output["n5_intake_event_kind"], "inactive_TriggerStateChanged_false")
        self.assertEqual(output["consumer_name"], "n5_live_tracking_poller_v2_fastlane")
        self.assertEqual(cursor.params, ("20260703", "n5_live_tracking_poller_v2_fastlane"))

    def test_n5_intake_default_discovery_skips_n5_consumed_n4_events(self) -> None:
        from run_n5_live_tracking_poller_once import _discover_intake_runtime_inputs

        class FakeCursor:
            def __init__(self):
                self.sql = ""
                self.params = None

            def execute(self, sql, params):
                self.sql = str(sql)
                self.params = params

            def fetchone(self):
                sql = self.sql.lower()
                if "common_event_inbox" not in sql:
                    return {
                        "source_run_id": "trigger_provisional_ordinary_20260703_until_0931__already_consumed",
                        "has_trigger_matched": True,
                        "trigger_time": "2026-07-03T09:31:00+08:00",
                    }
                return {
                    "source_run_id": "trigger_provisional_ordinary_20260703_until_0933__next",
                    "has_trigger_matched": True,
                    "trigger_time": "2026-07-03T09:33:00+08:00",
                }

        args = argparse.Namespace(for_trade_date="20260703")
        cursor = FakeCursor()
        output = _discover_intake_runtime_inputs(cursor, args)

        self.assertEqual(
            output["source_trigger_run_id"],
            "trigger_provisional_ordinary_20260703_until_0933__next",
        )
        self.assertEqual(output["trigger_time"], "2026-07-03T09:33:00+08:00")
        self.assertIn("common_event_inbox", cursor.sql)
        self.assertIn("consumer_name", cursor.sql)
        self.assertEqual(cursor.params, ("20260703", "n5_live_tracking_poller_v2_fastlane"))

    def test_n5_intake_fetch_pending_n4_rows_skips_n5_consumed_events(self) -> None:
        from run_n5_live_tracking_poller_once import _fetch_pending_n4_rows

        class FakeCursor:
            def __init__(self):
                self.sql = ""
                self.params = None

            def execute(self, sql, params):
                self.sql = str(sql)
                self.params = params

            def fetchall(self):
                if "common_event_inbox" not in self.sql.lower():
                    return [{"event_id": "already-consumed"}]
                return [{"event_id": "next-unconsumed"}]

        args = argparse.Namespace(
            source_trigger_run_id="trigger_provisional_ordinary_20260703_until_0933__next",
            for_trade_date="20260703",
            consumer_name="n5_live_tracking_poller_v2_fastlane",
            max_events=300,
        )
        cursor = FakeCursor()
        rows = _fetch_pending_n4_rows(cursor, args)

        self.assertEqual(rows, [{"event_id": "next-unconsumed"}])
        self.assertIn("common_event_inbox", cursor.sql)
        self.assertIn("consumer_name", cursor.sql)
        self.assertEqual(
            cursor.params,
            (
                "trigger_provisional_ordinary_20260703_until_0933__next",
                "20260703",
                list(("TriggerMatched", "TriggerStateChanged")),
                "n5_live_tracking_poller_v2_fastlane",
                300,
            ),
        )

    def test_n5_intake_fetch_active_tracking_includes_inactive_state_change_keys(self) -> None:
        from ashare_v3.action.dry_run import build_action_tracking_state_key
        from run_n5_live_tracking_poller_once import _fetch_active_tracking_rows

        state_key = build_action_tracking_state_key(
            trade_date="20260703",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_MAIN",
        )
        inactive_event = {
            "event_type": "TriggerStateChanged",
            "trade_date": "20260703",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "payload_json": {
                "trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "trigger_live": False,
            },
        }

        class FakeCursor:
            def __init__(self):
                self.calls = 0
                self.params = []

            def execute(self, _sql, params):
                self.calls += 1
                self.params.append(params)

            def fetchall(self):
                if self.calls == 1:
                    return []
                return [
                    {
                        "run_id": "n5_live_tracking_20260703__previous_match__fastlane_v1",
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0931__previous_match",
                        "trade_date": "20260703",
                        "state_key": state_key,
                        "action_state": "eligible",
                        "tracking_status": "tracking",
                        "trigger_live": True,
                    }
                ]

        args = argparse.Namespace(
            fastlane_phase="intake",
            action_run_id="n5_live_tracking_20260703__false_only__fastlane_v1",
            source_trigger_run_id="trigger_provisional_ordinary_20260703_until_0943__false_only",
            for_trade_date="20260703",
        )
        cursor = FakeCursor()
        rows = _fetch_active_tracking_rows(cursor, args, n4_event_rows=[inactive_event])

        self.assertEqual(rows[0]["state_key"], state_key)
        self.assertEqual(cursor.params[1], ("20260703", [state_key]))

    def test_n3_runner_resolves_activation_config_artifact_paths(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            (artifact_dir / "n5_active_scope_snapshot_v1.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 1,
                        "source_trigger_run_id": "n4-run",
                        "action_run_id": "n5-run",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(["--activation-config", str(config_path)])

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_SHELL_READY")
        self.assertEqual(manifest["active_scope_artifact_count"], 1)
        self.assertEqual(manifest["active_scope_artifact_dir"], str(artifact_dir))
        self.assertEqual(manifest["output_dir"], str(output_dir))

    def test_n3_c1_n3t_phase_gate_waits_for_first_closed_minute(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:25:00+08:00",
                            "current_exchange_time": "2026-07-03T09:25:30+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": False,
                            "matching_n3t_metric_available": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(["--activation-config", str(config_path)])

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_SHELL")
        self.assertEqual(manifest["blocked_reason"], "first_closed_minute_not_available")
        self.assertFalse(manifest["writes_enabled"])
        self.assertEqual(manifest["active_scope_artifact_count"], 0)

    def test_n3_c1_n3t_runtime_clock_session_policy_waits_before_first_closed_minute(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                            "current_exchange_time_override": "2026-07-03T09:25:30+08:00",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(["--activation-config", str(config_path)])

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_SHELL")
        self.assertEqual(manifest["blocked_reason"], "first_closed_minute_not_available")
        self.assertEqual(manifest["fastlane"]["session_phase"], "pre_open_call_auction_after_0925")

    def test_n3_c1_n3t_execute_waits_for_explicit_active_scope_artifact(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:35:00+08:00",
                            "current_exchange_time": "2026-07-03T09:40:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                            "matching_n3t_metric_available": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_EXECUTE")
        self.assertEqual(manifest["blocked_reason"], "active_scope_artifact_missing")
        self.assertEqual(manifest["active_scope_artifact_count"], 0)
        self.assertFalse(manifest["writes_enabled"])
        self.assertFalse(manifest["boundary"]["scans_n5_db"])

    def test_n3_write_enabled_activation_config_requires_policy_review_ref_at_runner(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:35:00+08:00",
                            "current_exchange_time": "2026-07-03T09:40:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                            "matching_n3t_metric_available": False,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": True},
                            "n5_action_executed": {"execute": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_EXECUTE")
        self.assertIn("active_worker_policy_review_ref", manifest["blocked_reason"])
        self.assertFalse(manifest["writes_enabled"])
        self.assertEqual(manifest["active_scope_artifact_count"], 0)

    def test_n3_write_enabled_activation_config_resolves_policy_review_path_at_runner(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            review_path = root / "active_worker_policy_review.json"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            review_path.write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                        "policy_type": "fastlane_active_worker_policy_v1",
                        "for_trade_date": "20260703",
                        "active_worker_write_enabled_ready": True,
                        "automatic_chain_verified": True,
                        "manual_gate_required": False,
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": [],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "active_worker_policy_review_path": str(review_path),
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "n3_c1_n3t_current_day_source_artifact_dir": str(root / "current_day_source"),
                        "n3_c1_n3t_current_day_source_provider": "mootdx_today_minute_adapter_v1",
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(root / "metric_context_source"),
                        "n3_c1_n3t_previous_day_context_artifact_dir": str(root / "previous_day_context"),
                        "n3_c1_n3t_previous_day_context_provider": "postgres_previous_day_raw_c1_context_v1",
                        "n3_c1_n3t_n3t_writer_adapter": "postgres_n3t_action_confirmation_metric_writer_v1",
                        "session_context": {
                            "trigger_time": "2026-07-03T09:35:00+08:00",
                            "current_exchange_time": "2026-07-03T09:40:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                            "matching_n3t_metric_available": False,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": False,
                                "write_active_scope_artifact": False,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": True},
                            "n5_action_executed": {"execute": False},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_EXECUTE")
        self.assertEqual(manifest["blocked_reason"], "active_scope_artifact_missing")
        self.assertFalse(manifest["writes_enabled"])
        self.assertEqual(manifest["active_scope_artifact_count"], 0)

    def test_active_launchd_plan_uses_activation_config_without_runtime_placeholders(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_interval_seconds": 3,
                        "n3_c1_n3t_interval_seconds": 5,
                        "n5_executed_interval_seconds": 3,
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = build_fastlane_active_launchd_plan(
                working_directory=WORKING_DIRECTORY,
                activation_config_path=str(config_path),
            )

        self.assertEqual(plan["result"], "ACTIVE_PLAN_ONLY_PASS")
        self.assertEqual(set(plan["launchd_plist_keys"]), {"n5_intake", "n3_c1_n3t", "n5_executed"})
        self.assertEqual(plan["activation_intervals_seconds"]["n5_intake"], 3)
        self.assertEqual(plan["activation_intervals_seconds"]["n3_c1_n3t"], 5)
        self.assertEqual(plan["activation_intervals_seconds"]["n5_executed"], 3)
        self.assertEqual(plan["session_phase_policy"]["policy_type"], "fastlane_session_phase_policy_v1")
        self.assertIn("pre_open_call_auction_after_0925", plan["session_phase_policy"]["phases"])
        self.assertEqual(plan["active_worker_policy"]["policy_type"], "fastlane_active_worker_policy_v1")
        self.assertEqual(
            set(plan["active_worker_policy"]["lanes"]),
            {"n5_action_intake", "n3_c1_n3t_action_confirmation", "n5_action_executed"},
        )
        for key in plan["launchd_plist_keys"]:
            plist = plan[key]["plist"]
            self.assertEqual(_plist_placeholders(plist), [])
            self.assertNotIn("ASHARE_V3_POSTGRES_DSN", plist["EnvironmentVariables"])
            self.assertEqual(plist["RunAtLoad"], False)
            self.assertEqual(plist["KeepAlive"], False)
            self.assertIn("StartInterval", plist)
            self.assertIn("--activation-config", plist["ProgramArguments"])
            self.assertIn("--scheduler-quiet", plist["ProgramArguments"])
            self.assertNotIn("--source-trigger-run-id", plist["ProgramArguments"])
            self.assertNotIn("--source-metric-run-id", plist["ProgramArguments"])
            self.assertNotIn("--action-run-id", plist["ProgramArguments"])
            self.assertNotIn("--consumer-name", plist["ProgramArguments"])

        joined = " ".join(str(arg) for key in plan["launchd_plist_keys"] for arg in plan[key]["plist"]["ProgramArguments"])
        for forbidden in (
            "run_n3_intraday_proof_poller_once.py",
            "run_n4_intraday_proof_discovery_poll_once.py",
            "run_n3_intraday_b1_c1_b2_auto_poll_once.py",
            "postgresql://",
            "run_n6",
        ):
            self.assertNotIn(forbidden, joined)

    def test_write_enabled_activation_config_builder_adds_session_and_execute_policy(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_active_launchd_plan,
            build_fastlane_write_enabled_activation_config,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base_config = {
                "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                "for_trade_date": "20260703",
                "n5_intake_interval_seconds": 3,
                "n3_c1_n3t_interval_seconds": 5,
                "n5_executed_interval_seconds": 3,
                "n5_intake_max_events": 300,
                "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                "lock_dir": "tmp/fastlane_locks",
                "log_dir": "tmp/fastlane_logs",
                "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
            }
            active_worker_policy_review = {
                "result": "PASS",
                "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                "for_trade_date": "20260703",
                "active_worker_write_enabled_ready": True,
                "automatic_chain_verified": True,
                "manual_gate_required": False,
                "chain_backlog": {
                    "n5_intake_remaining": 0,
                    "n3t_metric_remaining": 0,
                },
                "waiting_reasons": [],
                "blockers": [],
            }

            config = build_fastlane_write_enabled_activation_config(
                base_config,
                trade_calendar_is_open=True,
                active_worker_policy_review=active_worker_policy_review,
                enable_n5_intake=True,
                enable_n5_active_scope_artifact=True,
                enable_n3_c1_n3t=True,
                n3_c1_n3t_current_day_source_artifact_dir="docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source",
                n3_c1_n3t_current_day_source_provider="mootdx_today_minute_adapter_v1",
                n3_c1_n3t_metric_context_source_artifact_dir="docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source",
                n3_c1_n3t_previous_day_context_artifact_dir="docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context",
                n3_c1_n3t_previous_day_context_provider="postgres_previous_day_raw_c1_context_v1",
                n3_c1_n3t_n3t_writer_adapter="postgres_n3t_action_confirmation_metric_writer_v1",
                enable_n5_executed=True,
            )
            config_path = root / "write_enabled_activation_config.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

            plan = build_fastlane_active_launchd_plan(
                working_directory=WORKING_DIRECTORY,
                activation_config_path=str(config_path),
            )

        encoded = json.dumps(config, ensure_ascii=False, sort_keys=True)
        self.assertEqual(config["artifact_type"], "n5_n3t_fastlane_activation_config_v1")
        self.assertEqual(config["session_context_policy"]["policy_type"], "fastlane_runtime_clock_session_context_v1")
        self.assertTrue(config["session_context_policy"]["trade_calendar_is_open"])
        self.assertEqual(config["execute_policy"]["policy_type"], "n5_n3t_fastlane_write_enabled_execute_policy_v1")
        self.assertTrue(config["execute_policy"]["user_confirmed"])
        self.assertTrue(config["execute_policy"]["n5_action_intake"]["execute"])
        self.assertTrue(config["execute_policy"]["n5_action_intake"]["write_active_scope_artifact"])
        self.assertTrue(config["execute_policy"]["n3_c1_n3t_action_confirmation"]["execute"])
        self.assertTrue(config["execute_policy"]["n5_action_executed"]["execute"])
        self.assertEqual(
            config["n3_c1_n3t_current_day_source_artifact_dir"],
            "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source",
        )
        self.assertEqual(config["n3_c1_n3t_current_day_source_provider"], "mootdx_today_minute_adapter_v1")
        self.assertEqual(
            config["n3_c1_n3t_metric_context_source_artifact_dir"],
            "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source",
        )
        self.assertEqual(
            config["n3_c1_n3t_previous_day_context_artifact_dir"],
            "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context",
        )
        self.assertEqual(
            config["n3_c1_n3t_previous_day_context_provider"],
            "postgres_previous_day_raw_c1_context_v1",
        )
        self.assertEqual(
            config["n3_c1_n3t_n3t_writer_adapter"],
            "postgres_n3t_action_confirmation_metric_writer_v1",
        )
        self.assertNotRegex(encoded, r"__[A-Z0-9_]+__")
        self.assertNotRegex(encoded, r"postgres(?:ql)?://")
        self.assertEqual(config["active_worker_policy_review_ref"]["bootstrap_mode"], "automatic_chain_verified")
        self.assertTrue(plan["automatic_worker_activation_ready"])
        self.assertEqual(plan["activation_scope"], "full_chain_automatic_worker")
        self.assertEqual(
            plan["write_enabled_lane_readiness"],
            {
                "n5_action_intake": True,
                "n5_active_scope_artifact": True,
                "n3_c1_n3t_action_confirmation": True,
                "n5_action_executed": True,
            },
        )
        self.assertIn("--execute", plan["n5_intake"]["plist"]["ProgramArguments"])
        self.assertIn("--write-active-scope-artifact", plan["n5_intake"]["plist"]["ProgramArguments"])
        self.assertIn("--execute", plan["n3_c1_n3t"]["plist"]["ProgramArguments"])
        self.assertIn("--execute", plan["n5_executed"]["plist"]["ProgramArguments"])

    def test_write_enabled_activation_config_builder_requires_active_worker_policy_review(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_write_enabled_activation_config

        base_config = {
            "artifact_type": "n5_n3t_fastlane_activation_config_v1",
            "for_trade_date": "20260703",
            "n5_intake_interval_seconds": 3,
            "n3_c1_n3t_interval_seconds": 5,
            "n5_executed_interval_seconds": 3,
            "n5_intake_max_events": 300,
            "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
            "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
            "lock_dir": "tmp/fastlane_locks",
            "log_dir": "tmp/fastlane_logs",
            "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
        }

        with self.assertRaisesRegex(ValueError, "active_worker_policy_review"):
            build_fastlane_write_enabled_activation_config(
                base_config,
                trade_calendar_is_open=True,
                enable_n5_intake=True,
                enable_n5_active_scope_artifact=True,
            )

    def test_write_enabled_activation_config_full_chain_preflight_passes_complete_config(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_write_enabled_activation_config,
            build_fastlane_write_enabled_activation_config_full_chain_preflight,
        )

        base_config = {
            "artifact_type": "n5_n3t_fastlane_activation_config_v1",
            "for_trade_date": "20260703",
            "n5_intake_interval_seconds": 3,
            "n3_c1_n3t_interval_seconds": 5,
            "n5_executed_interval_seconds": 3,
            "n5_intake_max_events": 300,
            "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
            "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
            "lock_dir": "tmp/fastlane_locks",
            "log_dir": "tmp/fastlane_logs",
            "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
        }
        active_worker_policy_review = {
            "result": "PASS",
            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
            "for_trade_date": "20260703",
            "active_worker_write_enabled_ready": True,
            "automatic_chain_verified": True,
            "manual_gate_required": False,
            "chain_backlog": {
                "n5_intake_remaining": 0,
                "n3t_metric_remaining": 0,
            },
            "waiting_reasons": [],
            "blockers": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "write_enabled_activation_config_v1.json"
            config = build_fastlane_write_enabled_activation_config(
                base_config,
                trade_calendar_is_open=True,
                active_worker_policy_review=active_worker_policy_review,
                enable_n5_intake=True,
                enable_n5_active_scope_artifact=True,
                enable_n3_c1_n3t=True,
                n3_c1_n3t_current_day_source_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source"
                ),
                n3_c1_n3t_current_day_source_provider="mootdx_today_minute_adapter_v1",
                n3_c1_n3t_metric_context_source_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source"
                ),
                n3_c1_n3t_previous_day_context_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context"
                ),
                n3_c1_n3t_previous_day_context_provider="postgres_previous_day_raw_c1_context_v1",
                n3_c1_n3t_n3t_writer_adapter="postgres_n3t_action_confirmation_metric_writer_v1",
                enable_n5_executed=True,
            )
            config_path.write_text(
                json.dumps(config, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )

            preflight = build_fastlane_write_enabled_activation_config_full_chain_preflight(
                activation_config_path=config_path,
            )

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(
            preflight["final_verdict"],
            "RUNTIME_CONTROL_FASTLANE_WRITE_ENABLED_ACTIVATION_CONFIG_FULL_CHAIN_PREFLIGHT_PASS_READY_FOR_ACTIVE_PLAN_REGEN",
        )
        self.assertTrue(preflight["automatic_worker_activation_ready"])
        self.assertEqual(preflight["activation_scope"], "full_chain_automatic_worker")
        self.assertEqual(
            preflight["write_enabled_lane_readiness"],
            {
                "n5_action_intake": True,
                "n5_active_scope_artifact": True,
                "n3_c1_n3t_action_confirmation": True,
                "n5_action_executed": True,
            },
        )
        self.assertEqual(preflight["blockers"], [])
        self.assertFalse(preflight["forbidden_operation_proof"]["database_written_by_plan"])
        self.assertFalse(preflight["forbidden_operation_proof"]["launchd_loaded_or_started"])

    def test_write_enabled_activation_config_full_chain_preflight_blocks_missing_review_ref(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_write_enabled_activation_config_full_chain_preflight,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "write_enabled_activation_config_v1.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_interval_seconds": 3,
                        "n3_c1_n3t_interval_seconds": 5,
                        "n5_executed_interval_seconds": 3,
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": True},
                            "n5_action_executed": {"execute": True},
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            preflight = build_fastlane_write_enabled_activation_config_full_chain_preflight(
                activation_config_path=config_path,
            )

        self.assertEqual(preflight["result"], "BLOCKED")
        self.assertEqual(
            preflight["final_verdict"],
            "BLOCKED_FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_REF_MISSING",
        )
        self.assertEqual(preflight["blockers"], ["active_worker_policy_review_ref_missing"])

    def test_write_enabled_activation_config_full_chain_preflight_resolves_review_path(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_write_enabled_activation_config_full_chain_preflight,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_path = root / "active_worker_policy_review.json"
            config_path = root / "write_enabled_activation_config_v1.json"
            review_path.write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                        "policy_type": "fastlane_active_worker_policy_v1",
                        "for_trade_date": "20260703",
                        "active_worker_write_enabled_ready": True,
                        "automatic_chain_verified": True,
                        "manual_gate_required": False,
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": [],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "active_worker_policy_review_path": str(review_path),
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {"execute": True},
                            "n5_action_executed": {"execute": True},
                        },
                        "n3_c1_n3t_current_day_source_artifact_dir": str(root / "current_day_source"),
                        "n3_c1_n3t_current_day_source_provider": "mootdx_today_minute_adapter_v1",
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(root / "metric_context_source"),
                        "n3_c1_n3t_previous_day_context_artifact_dir": str(root / "previous_day_context"),
                        "n3_c1_n3t_previous_day_context_provider": "postgres_previous_day_raw_c1_context_v1",
                        "n3_c1_n3t_n3t_writer_adapter": "postgres_n3t_action_confirmation_metric_writer_v1",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            preflight = build_fastlane_write_enabled_activation_config_full_chain_preflight(
                activation_config_path=config_path,
            )

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertTrue(preflight["automatic_worker_activation_ready"])
        self.assertEqual(preflight["activation_scope"], "full_chain_automatic_worker")
        self.assertEqual(preflight["blockers"], [])
        self.assertEqual(preflight["active_worker_policy_review_ref"]["bootstrap_mode"], "automatic_chain_verified")

    def test_write_enabled_activation_config_full_chain_preflight_blocks_partial_bootstrap(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_write_enabled_activation_config,
            build_fastlane_write_enabled_activation_config_full_chain_preflight,
        )

        base_config = {
            "artifact_type": "n5_n3t_fastlane_activation_config_v1",
            "for_trade_date": "20260703",
            "n5_intake_interval_seconds": 3,
            "n3_c1_n3t_interval_seconds": 5,
            "n5_executed_interval_seconds": 3,
            "n5_intake_max_events": 300,
            "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
            "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
            "lock_dir": "tmp/fastlane_locks",
            "log_dir": "tmp/fastlane_logs",
            "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
        }
        active_worker_policy_review = {
            "result": "PASS",
            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
            "for_trade_date": "20260703",
            "active_worker_write_enabled_ready": True,
            "automatic_chain_verified": False,
            "manual_gate_required": False,
            "chain_backlog": {
                "n5_intake_remaining": 688,
                "n3t_metric_remaining": 57,
            },
            "waiting_reasons": ["waiting_for_n3t_metric_exact_cover"],
            "blockers": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "partial_activation_config_v1.json"
            config = build_fastlane_write_enabled_activation_config(
                base_config,
                trade_calendar_is_open=True,
                active_worker_policy_review=active_worker_policy_review,
                enable_n5_intake=True,
                enable_n5_active_scope_artifact=True,
                enable_n3_c1_n3t=False,
                enable_n5_executed=True,
            )
            config_path.write_text(
                json.dumps(config, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )

            preflight = build_fastlane_write_enabled_activation_config_full_chain_preflight(
                activation_config_path=config_path,
            )

        self.assertEqual(preflight["result"], "BLOCKED")
        self.assertEqual(
            preflight["final_verdict"],
            "BLOCKED_FASTLANE_FULL_CHAIN_ACTIVATION_CONFIG_MISMATCH",
        )
        self.assertFalse(preflight["automatic_worker_activation_ready"])
        self.assertEqual(preflight["activation_scope"], "partial_lane_bootstrap")
        self.assertIn("full_chain_lane_readiness_mismatch", preflight["blockers"])
        self.assertFalse(preflight["write_enabled_lane_readiness"]["n3_c1_n3t_action_confirmation"])

    def test_write_enabled_activation_config_full_chain_preflight_cli_outputs_json(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_write_enabled_activation_config
        from scripts.plan_n5_n3t_fastlane_launchd import main as plan_fastlane_main

        base_config = {
            "artifact_type": "n5_n3t_fastlane_activation_config_v1",
            "for_trade_date": "20260703",
            "n5_intake_interval_seconds": 3,
            "n3_c1_n3t_interval_seconds": 5,
            "n5_executed_interval_seconds": 3,
            "n5_intake_max_events": 300,
            "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
            "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
            "lock_dir": "tmp/fastlane_locks",
            "log_dir": "tmp/fastlane_logs",
            "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
        }
        active_worker_policy_review = {
            "result": "PASS",
            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
            "for_trade_date": "20260703",
            "active_worker_write_enabled_ready": True,
            "automatic_chain_verified": True,
            "manual_gate_required": False,
            "chain_backlog": {
                "n5_intake_remaining": 0,
                "n3t_metric_remaining": 0,
            },
            "waiting_reasons": [],
            "blockers": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "write_enabled_activation_config_v1.json"
            config = build_fastlane_write_enabled_activation_config(
                base_config,
                trade_calendar_is_open=True,
                active_worker_policy_review=active_worker_policy_review,
                enable_n5_intake=True,
                enable_n5_active_scope_artifact=True,
                enable_n3_c1_n3t=True,
                n3_c1_n3t_current_day_source_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source"
                ),
                n3_c1_n3t_current_day_source_provider="mootdx_today_minute_adapter_v1",
                n3_c1_n3t_metric_context_source_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source"
                ),
                n3_c1_n3t_previous_day_context_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context"
                ),
                n3_c1_n3t_previous_day_context_provider="postgres_previous_day_raw_c1_context_v1",
                n3_c1_n3t_n3t_writer_adapter="postgres_n3t_action_confirmation_metric_writer_v1",
                enable_n5_executed=True,
            )
            config_path.write_text(
                json.dumps(config, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )

            with patch("sys.stdout") as stdout:
                exit_code = plan_fastlane_main(
                    [
                        "--full-chain-activation-preflight",
                        "--activation-config",
                        str(config_path),
                        "--json",
                    ]
                )
            payload = json.loads("".join(call.args[0] for call in stdout.write.call_args_list))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["result"], "PREFLIGHT_PASS")
        self.assertTrue(payload["automatic_worker_activation_ready"])
        self.assertEqual(payload["activation_scope"], "full_chain_automatic_worker")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotRegex(encoded, r"__[A-Z0-9_]+__")
        self.assertNotRegex(encoded, r"postgres(?:ql)?://")

    def test_write_enabled_activation_config_builder_blocks_n3_execute_without_adapters(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_write_enabled_activation_config

        base_config = {
            "artifact_type": "n5_n3t_fastlane_activation_config_v1",
            "for_trade_date": "20260703",
            "n5_intake_interval_seconds": 3,
            "n3_c1_n3t_interval_seconds": 5,
            "n5_executed_interval_seconds": 3,
            "n5_intake_max_events": 300,
            "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
            "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
            "lock_dir": "tmp/fastlane_locks",
            "log_dir": "tmp/fastlane_logs",
            "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
        }
        active_worker_policy_review = {
            "result": "PASS",
            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
            "for_trade_date": "20260703",
            "active_worker_write_enabled_ready": True,
            "automatic_chain_verified": True,
            "manual_gate_required": False,
            "chain_backlog": {
                "n5_intake_remaining": 0,
                "n3t_metric_remaining": 0,
            },
            "waiting_reasons": [],
            "blockers": [],
        }

        with self.assertRaisesRegex(ValueError, "n3_c1_n3t_write_enabled_contract"):
            build_fastlane_write_enabled_activation_config(
                base_config,
                trade_calendar_is_open=True,
                active_worker_policy_review=active_worker_policy_review,
                enable_n5_intake=True,
                enable_n5_active_scope_artifact=True,
                enable_n3_c1_n3t=True,
                enable_n5_executed=True,
            )

    def test_write_enabled_activation_config_cli_writes_local_artifact_only(self) -> None:
        from scripts.plan_n5_n3t_fastlane_launchd import main as plan_fastlane_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base_path = root / "activation_config_v1.json"
            active_worker_review_path = root / "active_worker_policy_review.json"
            output_path = root / "write_enabled_activation_config_v1.json"
            base_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_interval_seconds": 3,
                        "n3_c1_n3t_interval_seconds": 5,
                        "n5_executed_interval_seconds": 3,
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "lock_dir": "tmp/fastlane_locks",
                        "log_dir": "tmp/fastlane_logs",
                        "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            active_worker_review_path.write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                        "for_trade_date": "20260703",
                        "active_worker_write_enabled_ready": True,
                        "manual_gate_required": False,
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": [],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("sys.stdout"):
                exit_code = plan_fastlane_main(
                    [
                        "--write-enabled-activation-config",
                        "--base-activation-config",
                        str(base_path),
                        "--active-worker-policy-review",
                        str(active_worker_review_path),
                        "--output-activation-config",
                        str(output_path),
                        "--trade-calendar-is-open",
                        "true",
                        "--enable-n5-intake",
                        "--enable-n5-active-scope-artifact",
                        "--enable-n3-c1-n3t",
                        "--n3-c1-n3t-current-day-source-artifact-dir",
                        "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source",
                        "--n3-c1-n3t-current-day-source-provider",
                        "mootdx_today_minute_adapter_v1",
                        "--n3-c1-n3t-metric-context-source-artifact-dir",
                        "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source",
                        "--n3-c1-n3t-previous-day-context-artifact-dir",
                        "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context",
                        "--n3-c1-n3t-previous-day-context-provider",
                        "postgres_previous_day_raw_c1_context_v1",
                        "--n3-c1-n3t-n3t-writer-adapter",
                        "postgres_n3t_action_confirmation_metric_writer_v1",
                        "--enable-n5-executed",
                    ]
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["artifact_type"], "n5_n3t_fastlane_activation_config_v1")
        self.assertEqual(payload["session_context_policy"]["policy_type"], "fastlane_runtime_clock_session_context_v1")
        self.assertTrue(payload["execute_policy"]["n5_action_intake"]["execute"])
        self.assertTrue(payload["execute_policy"]["n3_c1_n3t_action_confirmation"]["execute"])
        self.assertTrue(payload["execute_policy"]["n5_action_executed"]["execute"])
        self.assertEqual(
            payload["n3_c1_n3t_current_day_source_artifact_dir"],
            "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source",
        )
        self.assertEqual(payload["n3_c1_n3t_current_day_source_provider"], "mootdx_today_minute_adapter_v1")
        self.assertEqual(
            payload["n3_c1_n3t_metric_context_source_artifact_dir"],
            "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source",
        )
        self.assertEqual(
            payload["n3_c1_n3t_previous_day_context_artifact_dir"],
            "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context",
        )
        self.assertEqual(
            payload["n3_c1_n3t_previous_day_context_provider"],
            "postgres_previous_day_raw_c1_context_v1",
        )
        self.assertEqual(
            payload["n3_c1_n3t_n3t_writer_adapter"],
            "postgres_n3t_action_confirmation_metric_writer_v1",
        )
        self.assertFalse(payload["forbidden_operation_proof"]["database_written_by_plan"])
        self.assertFalse(payload["forbidden_operation_proof"]["launchd_loaded_or_started"])
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotRegex(encoded, r"__[A-Z0-9_]+__")
        self.assertNotRegex(encoded, r"postgres(?:ql)?://")

    def test_write_enabled_activation_config_cli_allows_exact_cover_backlog_bootstrap(self) -> None:
        from scripts.plan_n5_n3t_fastlane_launchd import main as plan_fastlane_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base_path = root / "activation_config_v1.json"
            active_worker_review_path = root / "active_worker_policy_review.json"
            output_path = root / "write_enabled_activation_config_v1.json"
            base_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_interval_seconds": 3,
                        "n3_c1_n3t_interval_seconds": 5,
                        "n5_executed_interval_seconds": 3,
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "lock_dir": "tmp/fastlane_locks",
                        "log_dir": "tmp/fastlane_logs",
                        "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            active_worker_review_path.write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                        "for_trade_date": "20260703",
                        "active_worker_write_enabled_ready": True,
                        "automatic_chain_verified": False,
                        "manual_gate_required": False,
                        "chain_backlog": {
                            "n5_intake_remaining": 688,
                            "n3t_metric_remaining": 57,
                        },
                        "waiting_reasons": [
                            "waiting_for_n5_intake_exact_cover",
                            "waiting_for_n3t_metric_exact_cover",
                        ],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("sys.stdout"):
                exit_code = plan_fastlane_main(
                    [
                        "--write-enabled-activation-config",
                        "--base-activation-config",
                        str(base_path),
                        "--active-worker-policy-review",
                        str(active_worker_review_path),
                        "--output-activation-config",
                        str(output_path),
                        "--trade-calendar-is-open",
                        "true",
                        "--enable-n5-intake",
                        "--enable-n5-active-scope-artifact",
                    ]
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["execute_policy"]["n5_action_intake"]["execute"])
        self.assertTrue(payload["execute_policy"]["n5_action_intake"]["write_active_scope_artifact"])
        self.assertEqual(
            payload["active_worker_policy_review_ref"]["bootstrap_mode"],
            "exact_cover_backlog_bootstrap",
        )
        self.assertEqual(
            payload["active_worker_policy_review_ref"]["chain_backlog"],
            {"n5_intake_remaining": 688, "n3t_metric_remaining": 57},
        )
        self.assertEqual(
            payload["active_worker_policy_review_ref"]["waiting_reasons"],
            ["waiting_for_n5_intake_exact_cover", "waiting_for_n3t_metric_exact_cover"],
        )

    def test_write_enabled_activation_config_cli_blocks_non_actionable_waiting_review(self) -> None:
        from scripts.plan_n5_n3t_fastlane_launchd import main as plan_fastlane_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base_path = root / "activation_config_v1.json"
            active_worker_review_path = root / "active_worker_policy_review.json"
            output_path = root / "write_enabled_activation_config_v1.json"
            base_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_interval_seconds": 3,
                        "n3_c1_n3t_interval_seconds": 5,
                        "n5_executed_interval_seconds": 3,
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "lock_dir": "tmp/fastlane_locks",
                        "log_dir": "tmp/fastlane_logs",
                        "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            active_worker_review_path.write_text(
                json.dumps(
                    {
                        "result": "WAITING",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_WAITING_FOR_MONITOR_PASS",
                        "for_trade_date": "20260703",
                        "active_worker_write_enabled_ready": False,
                        "manual_gate_required": False,
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": ["waiting_for_trade_date"],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SystemExit, "active worker policy review not ready"):
                plan_fastlane_main(
                    [
                        "--write-enabled-activation-config",
                        "--base-activation-config",
                        str(base_path),
                        "--active-worker-policy-review",
                        str(active_worker_review_path),
                        "--output-activation-config",
                        str(output_path),
                        "--trade-calendar-is-open",
                        "true",
                        "--enable-n5-intake",
                        "--enable-n5-active-scope-artifact",
                    ]
                )

            self.assertFalse(output_path.exists())

    def test_write_enabled_activation_config_cli_allows_runtime_deferred_review_path(self) -> None:
        from scripts.plan_n5_n3t_fastlane_launchd import main as plan_fastlane_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base_path = root / "activation_config_v1.json"
            active_worker_review_path = root / "active_worker_policy_review.json"
            output_path = root / "write_enabled_activation_config_v1.json"
            base_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_interval_seconds": 3,
                        "n3_c1_n3t_interval_seconds": 5,
                        "n5_executed_interval_seconds": 3,
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "lock_dir": "tmp/fastlane_locks",
                        "log_dir": "tmp/fastlane_logs",
                        "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            active_worker_review_path.write_text(
                json.dumps(
                    {
                        "result": "WAITING",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_WAITING_FOR_MONITOR_PASS",
                        "policy_type": "fastlane_active_worker_policy_v1",
                        "for_trade_date": "20260703",
                        "active_worker_write_enabled_ready": False,
                        "automatic_chain_verified": False,
                        "manual_gate_required": False,
                        "session_phase": "closed_day_or_non_trading",
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": [
                            "waiting_for_actionable_session_phase:closed_day_or_non_trading",
                            "waiting_for_n4_triggermatched",
                        ],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("sys.stdout"):
                exit_code = plan_fastlane_main(
                    [
                        "--write-enabled-activation-config",
                        "--defer-active-worker-policy-review-to-runtime",
                        "--base-activation-config",
                        str(base_path),
                        "--active-worker-policy-review",
                        str(active_worker_review_path),
                        "--output-activation-config",
                        str(output_path),
                        "--trade-calendar-is-open",
                        "true",
                        "--enable-n5-intake",
                        "--enable-n5-active-scope-artifact",
                        "--enable-n3-c1-n3t",
                        "--n3-c1-n3t-current-day-source-artifact-dir",
                        "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source",
                        "--n3-c1-n3t-current-day-source-provider",
                        "mootdx_today_minute_adapter_v1",
                        "--n3-c1-n3t-metric-context-source-artifact-dir",
                        "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source",
                        "--n3-c1-n3t-previous-day-context-artifact-dir",
                        "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context",
                        "--n3-c1-n3t-previous-day-context-provider",
                        "postgres_previous_day_raw_c1_context_v1",
                        "--n3-c1-n3t-n3t-writer-adapter",
                        "postgres_n3t_action_confirmation_metric_writer_v1",
                        "--enable-n5-executed",
                    ]
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["active_worker_policy_review_path"], str(active_worker_review_path))
        self.assertEqual(
            payload["active_worker_policy_review_path_policy"]["authorization_timing"],
            "runtime_deferred_to_runner",
        )
        self.assertNotIn("active_worker_policy_review_ref", payload)
        self.assertTrue(payload["execute_policy"]["n5_action_intake"]["execute"])
        self.assertTrue(payload["execute_policy"]["n3_c1_n3t_action_confirmation"]["execute"])
        self.assertTrue(payload["execute_policy"]["n5_action_executed"]["execute"])

    def test_trading_day_monitor_cli_reads_local_artifacts_and_outputs_json(self) -> None:
        from scripts.review_n5_n3t_fastlane_trading_day_monitor import main as monitor_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            launchagents_dir = root / "LaunchAgents"
            log_dir = root / "logs"
            launchagents_dir.mkdir()
            log_dir.mkdir()
            labels = {
                "n5_intake": "com.ashare-v3.n5.action-intake-poller",
                "n3_c1_n3t": "com.ashare-v3.n3.c1-n3t-action-confirmation-poller",
                "n5_executed": "com.ashare-v3.n5.action-executed-poller",
            }
            for key, label in labels.items():
                plist = {
                    "Label": label,
                    "ProgramArguments": [
                        "/usr/bin/python3",
                        "scripts/run_n5_live_tracking_poller_once.py"
                        if key != "n3_c1_n3t"
                        else "scripts/run_n3_c1_n3t_action_confirmation_fastlane_once.py",
                        "--activation-config",
                        "tmp/activation_config.json",
                    ],
                    "RunAtLoad": False,
                    "KeepAlive": False,
                    "StartInterval": 5 if key == "n3_c1_n3t" else 3,
                }
                (launchagents_dir / f"{label}.plist").write_bytes(plistlib.dumps(plist))
                (log_dir / f"{label}.out.log").write_text(
                    json.dumps(
                        {
                            "verdict": "FASTLANE_EXECUTE_PASS",
                            "session_phase": "trading",
                            "writes_enabled": True,
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            launchd_state_path = root / "launchd_state.json"
            launchd_state_path.write_text(
                json.dumps(
                    {
                        label: {"loaded": True, "pid": None, "runs": 8, "last_exit_code": 0}
                        for label in labels.values()
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            chain_evidence_path = root / "chain_evidence.json"
            chain_evidence_path.write_text(
                json.dumps(
                    {
                        "session_phase": "trading",
                        "n4_triggermatched": 12,
                        "n5_actioneligible": 12,
                        "n5_active_tracking": 12,
                        "n5_active_scope_artifacts": 1,
                        "n3_scoped_c1_artifacts": 1,
                        "n3t_c1_closed_metric_rows": 12,
                        "n5_actionexecuted": 3,
                        "closed_minute_available": True,
                        "n4_outbox_status_unchanged": True,
                        "n4_outbox_updated": False,
                        "n5_output_event_types": ["ActionEligible", "ActionExecuted"],
                        "n3_consumed_only_explicit_active_scope_artifact": True,
                        "n3_scanned_n5_db": False,
                        "n3_full_market_fallback": False,
                        "n3t_lineage_ok": True,
                        "legacy_metric_used": False,
                        "old_n3_n4_labels_unchanged": True,
                        "n6_touched": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            from io import StringIO

            active_worker_policy_review_path = root / "active_worker_policy_review.json"
            output = StringIO()
            with patch("sys.stdout", output):
                exit_code = monitor_main(
                    [
                        "--for-trade-date",
                        "20260706",
                        "--current-exchange-time",
                        "2026-07-06T09:36:05+08:00",
                        "--launchagents-dir",
                        str(launchagents_dir),
                        "--log-dir",
                        str(log_dir),
                        "--launchd-state-path",
                        str(launchd_state_path),
                        "--chain-evidence-path",
                        str(chain_evidence_path),
                        "--active-worker-policy-review-output-path",
                        str(active_worker_policy_review_path),
                        "--json",
                    ]
                )
                persisted = json.loads(active_worker_policy_review_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["result"], "PASS")
        self.assertTrue(payload["automatic_chain_verified"])
        self.assertEqual(payload["active_worker_policy_review"]["result"], "PASS")
        self.assertTrue(payload["active_worker_policy_review"]["active_worker_write_enabled_ready"])
        self.assertEqual(
            payload["active_worker_policy_review_output_path"],
            str(active_worker_policy_review_path),
        )
        self.assertRegex(payload["active_worker_policy_review_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(persisted["result"], "PASS")
        self.assertTrue(persisted["active_worker_write_enabled_ready"])
        self.assertFalse(payload["forbidden_operation_proof"]["database_written_by_plan"])
        self.assertFalse(payload["forbidden_operation_proof"]["launchd_loaded_or_started"])

    def test_trading_day_monitor_cli_blocks_current_runner_stderr_errors(self) -> None:
        from scripts.review_n5_n3t_fastlane_trading_day_monitor import main as monitor_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            launchagents_dir = root / "LaunchAgents"
            log_dir = root / "logs"
            launchagents_dir.mkdir()
            log_dir.mkdir()
            labels = {
                "n5_intake": "com.ashare-v3.n5.action-intake-poller",
                "n3_c1_n3t": "com.ashare-v3.n3.c1-n3t-action-confirmation-poller",
                "n5_executed": "com.ashare-v3.n5.action-executed-poller",
            }
            for key, label in labels.items():
                plist = {
                    "Label": label,
                    "ProgramArguments": [
                        "/usr/bin/python3",
                        "scripts/run_n5_live_tracking_poller_once.py"
                        if key != "n3_c1_n3t"
                        else "scripts/run_n3_c1_n3t_action_confirmation_fastlane_once.py",
                        "--activation-config",
                        "tmp/activation_config.json",
                    ],
                    "RunAtLoad": False,
                    "KeepAlive": False,
                    "StartInterval": 5 if key == "n3_c1_n3t" else 3,
                }
                (launchagents_dir / f"{label}.plist").write_bytes(plistlib.dumps(plist))
                (log_dir / f"{label}.out.log").write_text(
                    json.dumps(
                        {
                            "verdict": "FASTLANE_EXECUTE_PASS",
                            "session_phase": "trading",
                            "writes_enabled": True,
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            (log_dir / f"{labels['n3_c1_n3t']}.err.log").write_text(
                "Traceback (most recent call last):\nRuntimeError: current runner failure\n",
                encoding="utf-8",
            )

            launchd_state_path = root / "launchd_state.json"
            launchd_state_path.write_text(
                json.dumps(
                    {
                        label: {"loaded": True, "pid": None, "runs": 8, "last_exit_code": 0}
                        for label in labels.values()
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            chain_evidence_path = root / "chain_evidence.json"
            chain_evidence_path.write_text(
                json.dumps(
                    {
                        "session_phase": "trading",
                        "n4_triggermatched": 12,
                        "n5_actioneligible": 12,
                        "n5_active_tracking": 12,
                        "n5_active_scope_artifacts": 1,
                        "n3_scoped_c1_artifacts": 1,
                        "n3t_c1_closed_metric_rows": 12,
                        "n5_actionexecuted": 3,
                        "closed_minute_available": True,
                        "n4_outbox_status_unchanged": True,
                        "n4_outbox_updated": False,
                        "n5_output_event_types": ["ActionEligible", "ActionExecuted"],
                        "n3_consumed_only_explicit_active_scope_artifact": True,
                        "n3_scanned_n5_db": False,
                        "n3_full_market_fallback": False,
                        "n3t_lineage_ok": True,
                        "legacy_metric_used": False,
                        "old_n3_n4_labels_unchanged": True,
                        "n6_touched": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            from io import StringIO

            output = StringIO()
            with patch("sys.stdout", output):
                exit_code = monitor_main(
                    [
                        "--for-trade-date",
                        "20260706",
                        "--current-exchange-time",
                        "2026-07-06T09:36:05+08:00",
                        "--launchagents-dir",
                        str(launchagents_dir),
                        "--log-dir",
                        str(log_dir),
                        "--launchd-state-path",
                        str(launchd_state_path),
                        "--chain-evidence-path",
                        str(chain_evidence_path),
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["result"], "BLOCKED")
        self.assertIn(
            "stderr_runtime_error:com.ashare-v3.n3.c1-n3t-action-confirmation-poller",
            payload["blockers"],
        )
        self.assertTrue(payload["stderr_error_observed"])

    def test_trading_day_monitor_ignores_stale_runner_stderr_errors(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_trading_day_monitor_review,
        )

        launchd_states = {
            label: {"loaded": True, "pid": None, "runs": 8, "last_exit_code": 0}
            for label in FASTLANE_LABELS.values()
        }
        plist_summaries = {
            label: {
                "label": label,
                "start_interval": 5 if label == FASTLANE_LABELS["n3_c1_n3t"] else 3,
                "run_at_load": False,
                "keep_alive": False,
                "uses_activation_config": True,
                "has_placeholder": False,
                "has_secret_literal": False,
                "has_old_runner_ref": False,
            }
            for label in FASTLANE_LABELS.values()
        }
        chain_evidence = {
            "session_phase": "trading",
            "n4_triggermatched": 12,
            "n5_actioneligible": 12,
            "n5_active_tracking": 12,
            "n5_active_scope_artifacts": 1,
            "n3_scoped_c1_artifacts": 1,
            "n3t_c1_closed_metric_rows": 12,
            "n5_actionexecuted": 3,
            "closed_minute_available": True,
            "n4_outbox_status_unchanged": True,
            "n4_outbox_updated": False,
            "n5_output_event_types": ["ActionEligible", "ActionExecuted"],
            "n3_consumed_only_explicit_active_scope_artifact": True,
            "n3_scanned_n5_db": False,
            "n3_full_market_fallback": False,
            "n3t_lineage_ok": True,
            "legacy_metric_used": False,
            "old_n3_n4_labels_unchanged": True,
            "n6_touched": False,
        }

        review = build_fastlane_trading_day_monitor_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-06T09:36:05+08:00",
            launchd_states=launchd_states,
            plist_summaries=plist_summaries,
            recent_log_manifests={label: [] for label in FASTLANE_LABELS.values()},
            stderr_snapshots={
                label: {"has_runtime_error": True, "has_current_error": False}
                for label in FASTLANE_LABELS.values()
            },
            chain_evidence=chain_evidence,
        )

        self.assertEqual(review["result"], "PASS")
        self.assertFalse(review["stderr_error_observed"])

    def test_trading_day_monitor_ignores_stale_scheduler_noop_phase_mismatch(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_trading_day_monitor_review,
        )

        launchd_states = {
            label: {"loaded": True, "pid": None, "runs": 8, "last_exit_code": 0}
            for label in FASTLANE_LABELS.values()
        }
        plist_summaries = {
            label: {
                "label": label,
                "start_interval": 5 if label == FASTLANE_LABELS["n3_c1_n3t"] else 3,
                "run_at_load": False,
                "keep_alive": False,
                "uses_activation_config": True,
                "has_placeholder": False,
                "has_secret_literal": False,
                "has_old_runner_ref": False,
            }
            for label in FASTLANE_LABELS.values()
        }
        stale_noop_logs = {
            label: [
                {
                    "verdict": "FASTLANE_SCHEDULER_NOOP",
                    "session_phase": "closed_day_or_non_trading",
                    "scheduler_quiet": True,
                    "writes_enabled": False,
                }
            ]
            for label in FASTLANE_LABELS.values()
        }

        review = build_fastlane_trading_day_monitor_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-06T09:30:30+08:00",
            launchd_states=launchd_states,
            plist_summaries=plist_summaries,
            recent_log_manifests=stale_noop_logs,
            stderr_snapshots={},
            chain_evidence={
                "session_phase": "trading",
                "n4_triggermatched": 0,
                "n5_actioneligible": 0,
                "n5_active_tracking": 0,
                "n5_active_scope_artifacts": 0,
                "n3_scoped_c1_artifacts": 0,
                "n3t_c1_closed_metric_rows": 0,
                "n5_actionexecuted": 0,
                "closed_minute_available": False,
                "n4_outbox_status_unchanged": True,
                "n4_outbox_updated": False,
                "n5_output_event_types": [],
                "n3_consumed_only_explicit_active_scope_artifact": True,
                "n3_scanned_n5_db": False,
                "n3_full_market_fallback": False,
                "n3t_lineage_ok": True,
                "legacy_metric_used": False,
                "old_n3_n4_labels_unchanged": True,
                "n6_touched": False,
            },
        )

        self.assertEqual(review["result"], "WAITING")
        self.assertIn("waiting_for_n4_triggermatched", review["waiting_reasons"])
        self.assertEqual(review["blockers"], [])

    def test_trading_day_monitor_blocks_runner_writes_outside_phase_policy(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            FASTLANE_LABELS,
            build_fastlane_trading_day_monitor_review,
        )

        launchd_states = {
            label: {"loaded": True, "pid": None, "runs": 8, "last_exit_code": 0}
            for label in FASTLANE_LABELS.values()
        }
        plist_summaries = {
            label: {
                "label": label,
                "start_interval": 5 if label == FASTLANE_LABELS["n3_c1_n3t"] else 3,
                "run_at_load": False,
                "keep_alive": False,
                "uses_activation_config": True,
                "has_placeholder": False,
                "has_secret_literal": False,
                "has_old_runner_ref": False,
            }
            for label in FASTLANE_LABELS.values()
        }
        chain_evidence = {
            "session_phase": "trading",
            "n4_triggermatched": 12,
            "n5_actioneligible": 12,
            "n5_active_tracking": 12,
            "n5_active_scope_artifacts": 1,
            "n3_scoped_c1_artifacts": 1,
            "n3t_c1_closed_metric_rows": 12,
            "n5_actionexecuted": 3,
            "closed_minute_available": True,
            "n4_outbox_status_unchanged": True,
            "n4_outbox_updated": False,
            "n5_output_event_types": ["ActionEligible", "ActionExecuted"],
            "n3_consumed_only_explicit_active_scope_artifact": True,
            "n3_scanned_n5_db": False,
            "n3_full_market_fallback": False,
            "n3t_lineage_ok": True,
            "legacy_metric_used": False,
            "old_n3_n4_labels_unchanged": True,
            "n6_touched": False,
        }
        recent_log_manifests = {
            label: [] for label in FASTLANE_LABELS.values()
        }
        recent_log_manifests[FASTLANE_LABELS["n5_intake"]] = [
            {
                "verdict": "N5_LIVE_TRACKING_EXECUTE_PASS",
                "writes_enabled": True,
                "artifact_writes_enabled": True,
                "fastlane": {
                    "session_phase": "pre_open_before_0925",
                    "active_worker_decision": {
                        "policy_type": "fastlane_active_worker_policy_v1",
                        "lane_key": "n5_action_intake",
                        "session_phase": "pre_open_before_0925",
                        "worker_mode": "read_only_discovery",
                        "writes_enabled_allowed": False,
                        "artifact_writes_enabled_allowed": False,
                    },
                },
            }
        ]

        review = build_fastlane_trading_day_monitor_review(
            for_trade_date="20260706",
            current_exchange_time="2026-07-06T09:36:05+08:00",
            launchd_states=launchd_states,
            plist_summaries=plist_summaries,
            recent_log_manifests=recent_log_manifests,
            chain_evidence=chain_evidence,
        )

        self.assertEqual(review["result"], "BLOCKED")
        self.assertIn(
            "runner_write_enabled_outside_phase_policy:com.ashare-v3.n5.action-intake-poller",
            review["blockers"],
        )
        self.assertIn(
            "runner_session_phase_mismatch:com.ashare-v3.n5.action-intake-poller",
            review["blockers"],
        )

    def test_trading_day_monitor_cli_builds_chain_evidence_from_read_only_inputs(self) -> None:
        from scripts.review_n5_n3t_fastlane_trading_day_monitor import main as monitor_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            launchagents_dir = root / "LaunchAgents"
            log_dir = root / "logs"
            n5_scope_dir = root / "n5_scope"
            n3_dir = root / "n3"
            launchagents_dir.mkdir()
            log_dir.mkdir()
            n5_scope_dir.mkdir()
            (n3_dir / "metric_context").mkdir(parents=True)
            labels = {
                "n5_intake": "com.ashare-v3.n5.action-intake-poller",
                "n3_c1_n3t": "com.ashare-v3.n3.c1-n3t-action-confirmation-poller",
                "n5_executed": "com.ashare-v3.n5.action-executed-poller",
            }
            for key, label in labels.items():
                plist = {
                    "Label": label,
                    "ProgramArguments": [
                        "/usr/bin/python3",
                        "scripts/run_n5_live_tracking_poller_once.py"
                        if key != "n3_c1_n3t"
                        else "scripts/run_n3_c1_n3t_action_confirmation_fastlane_once.py",
                        "--activation-config",
                        "tmp/activation_config.json",
                    ],
                    "RunAtLoad": False,
                    "KeepAlive": False,
                    "StartInterval": 5 if key == "n3_c1_n3t" else 3,
                }
                (launchagents_dir / f"{label}.plist").write_bytes(plistlib.dumps(plist))
                (log_dir / f"{label}.out.log").write_text(
                    json.dumps(
                        {
                            "verdict": "FASTLANE_EXECUTE_PASS",
                            "session_phase": "trading",
                            "writes_enabled": True,
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            launchd_state_path = root / "launchd_state.json"
            launchd_state_path.write_text(
                json.dumps(
                    {
                        label: {"loaded": True, "pid": None, "runs": 8, "last_exit_code": 0}
                        for label in labels.values()
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            raw_snapshot_path = root / "raw_db_snapshot.json"
            raw_snapshot_path.write_text(
                json.dumps(
                    {
                        "n4_triggermatched": 12,
                        "n4_triggermatched_non_pending_observed": 0,
                        "n5_actioneligible": 12,
                        "n5_active_tracking": 12,
                        "n5_actionexecuted": 3,
                        "n3t_c1_closed_metric_rows": 12,
                        "n5_output_event_types": ["ActionEligible", "ActionExecuted"],
                        "n4_outbox_status_unchanged": True,
                        "n4_outbox_updated": False,
                        "n3t_lineage_ok": True,
                        "legacy_metric_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (n5_scope_dir / "n5_active_scope_snapshot_v1_20260706_0936.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260706",
                        "scope_count": 12,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (n3_dir / "metric_context" / "n3_c1_scoped_closed_1m_artifact_v1_0936.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_closed_1m_artifact_v1",
                        "for_trade_date": "20260706",
                        "scope_count": 12,
                        "source_input_type": "n5_active_scope_snapshot_v1",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            from io import StringIO

            output = StringIO()
            with patch("sys.stdout", output):
                exit_code = monitor_main(
                    [
                        "--for-trade-date",
                        "20260706",
                        "--current-exchange-time",
                        "2026-07-06T09:36:05+08:00",
                        "--trigger-time",
                        "2026-07-06T09:36:00+08:00",
                        "--trade-calendar-is-open",
                        "true",
                        "--launchagents-dir",
                        str(launchagents_dir),
                        "--log-dir",
                        str(log_dir),
                        "--launchd-state-path",
                        str(launchd_state_path),
                        "--raw-db-snapshot-path",
                        str(raw_snapshot_path),
                        "--n5-active-scope-artifact-dir",
                        str(n5_scope_dir),
                        "--n3-c1-n3t-artifact-dir",
                        str(n3_dir),
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["result"], "PASS")
        self.assertEqual(payload["chain_evidence_source"], "read_only_db_artifact_inputs")
        self.assertEqual(payload["session_phase"], "trading")
        self.assertTrue(payload["automatic_chain_verified"])
        self.assertFalse(payload["forbidden_operation_proof"]["database_written_by_plan"])
        self.assertFalse(payload["forbidden_operation_proof"]["launchd_loaded_or_started"])

    def test_chain_evidence_cli_writes_local_artifact_only(self) -> None:
        from scripts.generate_n5_n3t_fastlane_chain_evidence import main as evidence_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_summary_path = root / "db_summary.json"
            artifact_summary_path = root / "artifact_summary.json"
            output_path = root / "chain_evidence.json"
            db_summary_path.write_text(
                json.dumps(
                    {
                        "n4_triggermatched": 12,
                        "n5_actioneligible": 12,
                        "n5_active_tracking": 12,
                        "n5_actionexecuted": 3,
                        "n3t_c1_closed_metric_rows": 12,
                        "n5_output_event_types": ["ActionExecuted", "ActionEligible"],
                        "n4_outbox_status_unchanged": True,
                        "n4_outbox_updated": False,
                        "n3t_lineage_ok": True,
                        "legacy_metric_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            artifact_summary_path.write_text(
                json.dumps(
                    {
                        "n5_active_scope_artifacts": 1,
                        "n3_scoped_c1_artifacts": 1,
                        "n3_consumed_only_explicit_active_scope_artifact": True,
                        "n3_scanned_n5_db": False,
                        "n3_full_market_fallback": False,
                        "old_n3_n4_labels_unchanged": True,
                        "n6_touched": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            from io import StringIO

            output = StringIO()
            with patch("sys.stdout", output):
                exit_code = evidence_main(
                    [
                        "--for-trade-date",
                        "20260706",
                        "--session-phase",
                        "trading",
                        "--closed-minute-available",
                        "true",
                        "--db-summary-path",
                        str(db_summary_path),
                        "--artifact-summary-path",
                        str(artifact_summary_path),
                        "--output-path",
                        str(output_path),
                        "--json",
                    ]
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            report = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["artifact_type"], "n5_n3t_fastlane_chain_evidence_v1")
        self.assertEqual(payload["for_trade_date"], "20260706")
        self.assertEqual(payload["n5_output_event_types"], ["ActionEligible", "ActionExecuted"])
        self.assertEqual(report["output_path"], str(output_path))
        self.assertRegex(report["sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(payload["forbidden_operation_proof"]["database_written_by_plan"])
        self.assertFalse(payload["forbidden_operation_proof"]["launchd_loaded_or_started"])

    def test_db_artifact_summary_cli_writes_read_only_monitor_inputs(self) -> None:
        from scripts.generate_n5_n3t_fastlane_db_artifact_summary import main as summary_main

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_db_snapshot_path = root / "raw_db_snapshot.json"
            n5_scope_dir = root / "n5_scope"
            n3_dir = root / "n3_fastlane"
            staging_dir = n3_dir / "current_day_staging"
            db_summary_output_path = root / "db_summary.json"
            artifact_summary_output_path = root / "artifact_summary.json"
            n5_scope_dir.mkdir()
            staging_dir.mkdir(parents=True)
            raw_db_snapshot_path.write_text(
                json.dumps(
                    {
                        "n4_triggermatched": 12,
                        "n5_actioneligible": 12,
                        "n5_active_tracking": 12,
                        "n5_actionexecuted": 3,
                        "n3t_c1_closed_metric_rows": 12,
                        "n5_output_event_types": ["ActionExecuted", "ActionEligible"],
                        "n4_outbox_status_unchanged": True,
                        "n4_outbox_updated": False,
                        "n3t_lineage_ok": True,
                        "legacy_metric_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (n5_scope_dir / "n5_active_scope_snapshot_v1_20260706_0931_abcd.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 12,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (staging_dir / "n3_c1_scoped_current_day_staging_v1_0931_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_staging_v1",
                        "source_input_type": "n5_active_scope_snapshot_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_db": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            from io import StringIO

            output = StringIO()
            with patch("sys.stdout", output):
                exit_code = summary_main(
                    [
                        "--raw-db-snapshot-path",
                        str(raw_db_snapshot_path),
                        "--n5-active-scope-artifact-dir",
                        str(n5_scope_dir),
                        "--n3-c1-n3t-artifact-dir",
                        str(n3_dir),
                        "--db-summary-output-path",
                        str(db_summary_output_path),
                        "--artifact-summary-output-path",
                        str(artifact_summary_output_path),
                        "--json",
                    ]
                )

            db_summary = json.loads(db_summary_output_path.read_text(encoding="utf-8"))
            artifact_summary = json.loads(artifact_summary_output_path.read_text(encoding="utf-8"))
            report = json.loads(output.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(db_summary["n4_triggermatched"], 12)
        self.assertEqual(db_summary["n5_output_event_types"], ["ActionEligible", "ActionExecuted"])
        self.assertEqual(artifact_summary["n5_active_scope_artifacts"], 1)
        self.assertEqual(artifact_summary["n3_scoped_c1_artifacts"], 1)
        self.assertTrue(artifact_summary["n3_consumed_only_explicit_active_scope_artifact"])
        self.assertFalse(artifact_summary["n3_scanned_n5_db"])
        self.assertFalse(artifact_summary["n3_full_market_fallback"])
        self.assertTrue(artifact_summary["old_n3_n4_labels_unchanged"])
        self.assertFalse(artifact_summary["n6_touched"])
        self.assertEqual(report["result"], "DB_ARTIFACT_SUMMARY_OUTPUT_PASS")
        self.assertRegex(report["db_summary_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(report["artifact_summary_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(report["forbidden_operation_proof"]["database_written_by_plan"])

    def test_db_artifact_summary_collector_uses_read_only_fastlane_queries(self) -> None:
        from scripts.generate_n5_n3t_fastlane_db_artifact_summary import collect_raw_db_snapshot

        class FakeCursor:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []
                self.results = [
                    {"count": 12},
                    {"count": 7},
                    [
                        {"event_type": "ActionEligible", "count": 12},
                        {"event_type": "ActionExecuted", "count": 3},
                    ],
                    {"count": 9},
                    {"total_rows": 12, "contract_rows": 12},
                    {"count": 0},
                ]

            def execute(self, sql: str, params: tuple[object, ...]) -> None:
                self.calls.append((sql, params))

            def fetchone(self):
                result = self.results.pop(0)
                assert not isinstance(result, list)
                return result

            def fetchall(self):
                result = self.results.pop(0)
                assert isinstance(result, list)
                return result

        cursor = FakeCursor()

        snapshot = collect_raw_db_snapshot(
            cursor,
            for_trade_date="20260706",
            n5_action_run_id_like="n5_live_tracking_20260706%__fastlane_v1",
            n3t_metric_run_id_like="n3t_action_confirmation_metric_20260706%__fastlane%",
        )

        self.assertEqual(snapshot["n4_triggermatched"], 12)
        self.assertEqual(snapshot["n5_actioneligible"], 12)
        self.assertEqual(snapshot["n5_actionexecuted"], 3)
        self.assertEqual(snapshot["n5_active_tracking"], 9)
        self.assertEqual(snapshot["n3t_c1_closed_metric_rows"], 12)
        self.assertTrue(snapshot["n4_outbox_status_unchanged"])
        self.assertFalse(snapshot["n4_outbox_updated"])
        self.assertEqual(snapshot["n4_triggermatched_non_pending_observed"], 7)
        self.assertTrue(snapshot["n3t_lineage_ok"])
        self.assertFalse(snapshot["legacy_metric_used"])
        self.assertEqual(snapshot["n5_output_event_types"], ["ActionEligible", "ActionExecuted"])
        combined_sql = "\n".join(sql for sql, _params in cursor.calls).lower()
        self.assertNotRegex(combined_sql, r"\b(insert|update|delete|merge|truncate|drop|alter|create)\b")
        self.assertIn("source_layer = 'n4_trigger'", combined_sql)
        self.assertIn("source_layer = 'n5_action'", combined_sql)
        self.assertIn("n3t_action_confirmation_metric", combined_sql)
        self.assertIn("source_basis = 'n3t_c1_closed'", combined_sql)

    def test_db_artifact_summary_cli_reads_dsn_from_env_without_secret_output(self) -> None:
        from scripts import generate_n5_n3t_fastlane_db_artifact_summary as summary_script

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            n5_scope_dir = root / "n5_scope"
            n3_dir = root / "n3_fastlane"
            db_summary_output_path = root / "db_summary.json"
            artifact_summary_output_path = root / "artifact_summary.json"
            n5_scope_dir.mkdir()
            n3_dir.mkdir()
            secret_dsn = "postgresql://secret-user:secret-pass@localhost/db"

            def fake_read_db_snapshot(**kwargs):
                self.assertEqual(kwargs["dsn"], secret_dsn)
                return {
                    "n4_triggermatched": 1,
                    "n5_actioneligible": 1,
                    "n5_active_tracking": 1,
                    "n5_actionexecuted": 0,
                    "n3t_c1_closed_metric_rows": 0,
                    "n5_output_event_types": ["ActionEligible"],
                    "n4_outbox_status_unchanged": True,
                    "n4_outbox_updated": False,
                    "n3t_lineage_ok": True,
                    "legacy_metric_used": False,
                }

            from io import StringIO

            output = StringIO()
            with patch.dict("os.environ", {"ASHARE_V3_POSTGRES_DSN": secret_dsn}):
                with patch.object(summary_script, "_read_db_snapshot_via_dsn", side_effect=fake_read_db_snapshot):
                    with patch("sys.stdout", output):
                        exit_code = summary_script.main(
                            [
                                "--for-trade-date",
                                "20260706",
                                "--n5-active-scope-artifact-dir",
                                str(n5_scope_dir),
                                "--n3-c1-n3t-artifact-dir",
                                str(n3_dir),
                                "--db-summary-output-path",
                                str(db_summary_output_path),
                                "--artifact-summary-output-path",
                                str(artifact_summary_output_path),
                                "--json",
                            ]
                        )

            stdout_text = output.getvalue()
            db_summary_text = db_summary_output_path.read_text(encoding="utf-8")
            artifact_summary_text = artifact_summary_output_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertNotIn(secret_dsn, stdout_text)
        self.assertNotIn(secret_dsn, db_summary_text)
        self.assertNotIn(secret_dsn, artifact_summary_text)

    def test_active_launchd_plan_can_enable_n5_write_flags_with_explicit_policy(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_intake_max_events": 300,
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "active_worker_policy_review_ref": {
                            "result": "PASS",
                            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                            "for_trade_date": "20260703",
                            "active_worker_write_enabled_ready": True,
                            "automatic_chain_verified": False,
                            "bootstrap_mode": "exact_cover_backlog_bootstrap",
                            "chain_backlog": {
                                "n5_intake_remaining": 12,
                                "n3t_metric_remaining": 3,
                            },
                            "waiting_reasons": ["waiting_for_n3t_metric_exact_cover"],
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {
                                "execute": False,
                            },
                            "n5_action_executed": {
                                "execute": True,
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = build_fastlane_active_launchd_plan(
                working_directory=WORKING_DIRECTORY,
                activation_config_path=str(config_path),
            )

        self.assertEqual(plan["result"], "ACTIVE_PLAN_ONLY_PASS")
        self.assertEqual(
            plan["write_enabled_execute_policy"]["policy_type"],
            "n5_n3t_fastlane_write_enabled_execute_policy_v1",
        )
        self.assertEqual(
            plan["active_worker_policy_review_ref"]["bootstrap_mode"],
            "exact_cover_backlog_bootstrap",
        )
        self.assertEqual(
            plan["active_worker_policy_review_ref"]["chain_backlog"],
            {"n5_intake_remaining": 12, "n3t_metric_remaining": 3},
        )
        self.assertFalse(plan["automatic_worker_activation_ready"])
        self.assertEqual(plan["activation_scope"], "partial_lane_bootstrap")
        self.assertEqual(
            plan["write_enabled_lane_readiness"],
            {
                "n5_action_intake": True,
                "n5_active_scope_artifact": True,
                "n3_c1_n3t_action_confirmation": False,
                "n5_action_executed": True,
            },
        )
        intake_args = plan["n5_intake"]["plist"]["ProgramArguments"]
        self.assertIn("--execute", intake_args)
        self.assertIn("--user-confirmed", intake_args)
        self.assertIn("--write-active-scope-artifact", intake_args)

        n3_args = plan["n3_c1_n3t"]["plist"]["ProgramArguments"]
        self.assertNotIn("--execute", n3_args)
        self.assertNotIn("--user-confirmed", n3_args)

        executed_args = plan["n5_executed"]["plist"]["ProgramArguments"]
        self.assertIn("--execute", executed_args)
        self.assertIn("--user-confirmed", executed_args)

    def test_active_launchd_plan_keeps_idle_open_scope_out_of_full_chain_automatic(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "active_worker_policy_review_ref": {
                            "result": "PASS",
                            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                            "for_trade_date": "20260703",
                            "active_worker_write_enabled_ready": True,
                            "automatic_chain_verified": False,
                            "bootstrap_mode": "idle_open_scheduler",
                            "chain_backlog": {
                                "n5_intake_remaining": 0,
                                "n3t_metric_remaining": 0,
                            },
                            "waiting_reasons": ["waiting_for_n4_triggermatched"],
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {
                                "execute": True,
                            },
                            "n5_action_executed": {
                                "execute": True,
                            },
                        },
                        "n3_c1_n3t_current_day_source_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source",
                        "n3_c1_n3t_current_day_source_provider": "mootdx_today_minute_adapter_v1",
                        "n3_c1_n3t_metric_context_source_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source",
                        "n3_c1_n3t_previous_day_context_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context",
                        "n3_c1_n3t_previous_day_context_provider": "postgres_previous_day_raw_c1_context_v1",
                        "n3_c1_n3t_n3t_writer_adapter": "postgres_n3t_action_confirmation_metric_writer_v1",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = build_fastlane_active_launchd_plan(
                working_directory=WORKING_DIRECTORY,
                activation_config_path=str(config_path),
            )

        self.assertTrue(plan["automatic_worker_activation_ready"])
        self.assertEqual(plan["activation_scope"], "idle_open_scheduler")
        self.assertFalse(plan["active_worker_policy_review_ref"]["automatic_chain_verified"])

    def test_active_launchd_plan_resolves_idle_open_policy_review_path(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_active_worker_policy_review,
            build_fastlane_active_launchd_plan,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_path = root / "active_worker_policy_review.json"
            config_path = root / "activation_config.json"
            review = build_fastlane_active_worker_policy_review(
                for_trade_date="20260703",
                monitor_review={
                    "result": "WAITING",
                    "final_verdict": "FASTLANE_TRADING_DAY_MONITOR_WAITING_FOR_INPUT_OR_CLOSED_MINUTE",
                    "automatic_chain_verified": False,
                    "manual_gate_required": False,
                    "session_phase": "trading",
                    "chain_backlog": {
                        "n5_intake_remaining": 0,
                        "n3t_metric_remaining": 0,
                    },
                    "waiting_reasons": ["waiting_for_n4_triggermatched"],
                    "blockers": [],
                },
            )
            review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "active_worker_policy_review_path": str(review_path),
                        "active_worker_policy_review_path_policy": {
                            "policy_type": "fastlane_active_worker_policy_review_runtime_resolved_v1",
                            "no_secret_embedded": True,
                        },
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {
                                "execute": True,
                            },
                            "n5_action_executed": {
                                "execute": True,
                            },
                        },
                        "n3_c1_n3t_current_day_source_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source",
                        "n3_c1_n3t_current_day_source_provider": "mootdx_today_minute_adapter_v1",
                        "n3_c1_n3t_metric_context_source_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source",
                        "n3_c1_n3t_previous_day_context_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context",
                        "n3_c1_n3t_previous_day_context_provider": "postgres_previous_day_raw_c1_context_v1",
                        "n3_c1_n3t_n3t_writer_adapter": "postgres_n3t_action_confirmation_metric_writer_v1",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = build_fastlane_active_launchd_plan(
                working_directory=WORKING_DIRECTORY,
                activation_config_path=str(config_path),
            )

        self.assertTrue(plan["automatic_worker_activation_ready"])
        self.assertEqual(plan["activation_scope"], "idle_open_scheduler")
        self.assertEqual(plan["active_worker_policy_review_ref"]["bootstrap_mode"], "idle_open_scheduler")
        self.assertEqual(review["session_phase"], "trading")

    def test_active_launchd_plan_allows_runtime_deferred_review_path(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_path = root / "active_worker_policy_review.json"
            config_path = root / "activation_config.json"
            review_path.write_text(
                json.dumps(
                    {
                        "result": "WAITING",
                        "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_WAITING_FOR_MONITOR_PASS",
                        "policy_type": "fastlane_active_worker_policy_v1",
                        "for_trade_date": "20260703",
                        "active_worker_write_enabled_ready": False,
                        "automatic_chain_verified": False,
                        "manual_gate_required": False,
                        "session_phase": "closed_day_or_non_trading",
                        "chain_backlog": {
                            "n5_intake_remaining": 0,
                            "n3t_metric_remaining": 0,
                        },
                        "waiting_reasons": [
                            "waiting_for_actionable_session_phase:closed_day_or_non_trading",
                            "waiting_for_n4_triggermatched",
                        ],
                        "blockers": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "active_worker_policy_review_path": str(review_path),
                        "active_worker_policy_review_path_policy": {
                            "policy_type": "fastlane_active_worker_policy_review_runtime_resolved_v1",
                            "resolution": "runtime_read_only_latest_artifact",
                            "authorization_timing": "runtime_deferred_to_runner",
                            "no_secret_embedded": True,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {
                                "execute": True,
                            },
                            "n5_action_executed": {
                                "execute": True,
                            },
                        },
                        "n3_c1_n3t_current_day_source_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source",
                        "n3_c1_n3t_current_day_source_provider": "mootdx_today_minute_adapter_v1",
                        "n3_c1_n3t_metric_context_source_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source",
                        "n3_c1_n3t_previous_day_context_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context",
                        "n3_c1_n3t_previous_day_context_provider": "postgres_previous_day_raw_c1_context_v1",
                        "n3_c1_n3t_n3t_writer_adapter": "postgres_n3t_action_confirmation_metric_writer_v1",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = build_fastlane_active_launchd_plan(
                working_directory=WORKING_DIRECTORY,
                activation_config_path=str(config_path),
            )

        self.assertTrue(plan["automatic_worker_activation_ready"])
        self.assertFalse(plan["runtime_write_authorization_ready"])
        self.assertEqual(plan["runtime_write_authorization"], "deferred_to_runner")
        self.assertEqual(plan["activation_scope"], "runtime_review_path_deferred")
        self.assertEqual(
            plan["active_worker_policy_review_ref"]["bootstrap_mode"],
            "runtime_review_path_deferred",
        )

    def test_active_launchd_plan_require_full_chain_blocks_partial_bootstrap(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import write_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "partial_activation_config.json"
            output_dir = root / "active_plan"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "active_worker_policy_review_ref": {
                            "result": "PASS",
                            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                            "for_trade_date": "20260703",
                            "active_worker_write_enabled_ready": True,
                            "automatic_chain_verified": False,
                            "bootstrap_mode": "exact_cover_backlog_bootstrap",
                            "chain_backlog": {
                                "n5_intake_remaining": 12,
                                "n3t_metric_remaining": 3,
                            },
                            "waiting_reasons": ["waiting_for_n3t_metric_exact_cover"],
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {
                                "execute": True,
                                "write_active_scope_artifact": True,
                            },
                            "n3_c1_n3t_action_confirmation": {
                                "execute": False,
                            },
                            "n5_action_executed": {
                                "execute": True,
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "full-chain activation preflight"):
                write_fastlane_active_launchd_plan(
                    output_dir=output_dir,
                    working_directory=WORKING_DIRECTORY,
                    activation_config_path=str(config_path),
                    require_full_chain_activation=True,
                )

            self.assertFalse(output_dir.exists())

    def test_active_launchd_plan_require_full_chain_accepts_complete_config(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_write_enabled_activation_config,
            write_fastlane_active_launchd_plan,
        )

        base_config = {
            "artifact_type": "n5_n3t_fastlane_activation_config_v1",
            "for_trade_date": "20260703",
            "n5_intake_interval_seconds": 3,
            "n3_c1_n3t_interval_seconds": 5,
            "n5_executed_interval_seconds": 3,
            "n5_intake_max_events": 300,
            "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
            "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
            "lock_dir": "tmp/fastlane_locks",
            "log_dir": "tmp/fastlane_logs",
            "dsn_env_policy": "runtime_env_required_no_secret_in_artifact",
        }
        active_worker_policy_review = {
            "result": "PASS",
            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
            "for_trade_date": "20260703",
            "active_worker_write_enabled_ready": True,
            "automatic_chain_verified": True,
            "manual_gate_required": False,
            "chain_backlog": {
                "n5_intake_remaining": 0,
                "n3t_metric_remaining": 0,
            },
            "waiting_reasons": [],
            "blockers": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "write_enabled_activation_config.json"
            output_dir = root / "active_plan"
            config = build_fastlane_write_enabled_activation_config(
                base_config,
                trade_calendar_is_open=True,
                active_worker_policy_review=active_worker_policy_review,
                enable_n5_intake=True,
                enable_n5_active_scope_artifact=True,
                enable_n3_c1_n3t=True,
                n3_c1_n3t_current_day_source_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source"
                ),
                n3_c1_n3t_current_day_source_provider="mootdx_today_minute_adapter_v1",
                n3_c1_n3t_metric_context_source_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source"
                ),
                n3_c1_n3t_previous_day_context_artifact_dir=(
                    "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context"
                ),
                n3_c1_n3t_previous_day_context_provider="postgres_previous_day_raw_c1_context_v1",
                n3_c1_n3t_n3t_writer_adapter="postgres_n3t_action_confirmation_metric_writer_v1",
                enable_n5_executed=True,
            )
            config_path.write_text(json.dumps(config, ensure_ascii=False, sort_keys=True), encoding="utf-8")

            report = write_fastlane_active_launchd_plan(
                output_dir=output_dir,
                working_directory=WORKING_DIRECTORY,
                activation_config_path=str(config_path),
                require_full_chain_activation=True,
            )
            report_exists = (output_dir / "N5_N3T_action_confirmation_fastlane_active_launchd_plan.json").exists()

        self.assertEqual(report["result"], "ACTIVE_PLAN_ONLY_PASS")
        self.assertTrue(report["full_chain_activation_preflight"]["automatic_worker_activation_ready"])
        self.assertEqual(report["activation_scope"], "full_chain_automatic_worker")
        self.assertTrue(report_exists)

    def test_active_launchd_write_enabled_plan_requires_session_context_policy(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {"execute": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "session_context"):
                build_fastlane_active_launchd_plan(
                    working_directory=WORKING_DIRECTORY,
                    activation_config_path=str(config_path),
                )

    def test_active_launchd_write_enabled_plan_requires_active_worker_policy_review_ref(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {"execute": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "active_worker_policy_review_ref"):
                build_fastlane_active_launchd_plan(
                    working_directory=WORKING_DIRECTORY,
                    activation_config_path=str(config_path),
                )

    def test_active_launchd_plan_blocks_n3_execute_without_adapter_contract(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "active_worker_policy_review_ref": {
                            "result": "PASS",
                            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                            "for_trade_date": "20260703",
                            "active_worker_write_enabled_ready": True,
                            "automatic_chain_verified": True,
                            "bootstrap_mode": "automatic_chain_verified",
                            "chain_backlog": {
                                "n5_intake_remaining": 0,
                                "n3t_metric_remaining": 0,
                            },
                            "waiting_reasons": [],
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n3_c1_n3t_action_confirmation": {"execute": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "n3_c1_n3t_write_enabled_contract"):
                build_fastlane_active_launchd_plan(
                    working_directory=WORKING_DIRECTORY,
                    activation_config_path=str(config_path),
                )

    def test_active_launchd_plan_can_enable_n3_execute_after_runner_contract_exists(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import build_fastlane_active_launchd_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "activation_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": "docs/runtime/20260703/n5_fastlane_active_scope",
                        "n3_c1_n3t_artifact_dir": "docs/runtime/20260703/n3_c1_n3t_fastlane",
                        "n3_c1_n3t_current_day_source_artifact_dir": (
                            "docs/runtime/20260703/n3_c1_n3t_fastlane/current_day_source"
                        ),
                        "n3_c1_n3t_current_day_source_provider": "mootdx_today_minute_adapter_v1",
                        "n3_c1_n3t_metric_context_source_artifact_dir": (
                            "docs/runtime/20260703/n3_c1_n3t_fastlane/metric_context_source"
                        ),
                        "n3_c1_n3t_previous_day_context_artifact_dir": (
                            "docs/runtime/20260703/n3_c1_n3t_fastlane/previous_day_context"
                        ),
                        "n3_c1_n3t_previous_day_context_provider": "postgres_previous_day_raw_c1_context_v1",
                        "n3_c1_n3t_n3t_writer_adapter": "postgres_n3t_action_confirmation_metric_writer_v1",
                        "session_context_policy": {
                            "policy_type": "fastlane_runtime_clock_session_context_v1",
                            "trade_calendar_is_open": True,
                        },
                        "active_worker_policy_review_ref": {
                            "result": "PASS",
                            "final_verdict": "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
                            "for_trade_date": "20260703",
                            "active_worker_write_enabled_ready": True,
                            "automatic_chain_verified": True,
                            "bootstrap_mode": "automatic_chain_verified",
                            "chain_backlog": {
                                "n5_intake_remaining": 0,
                                "n3t_metric_remaining": 0,
                            },
                            "waiting_reasons": [],
                        },
                        "execute_policy": {
                            "policy_type": "n5_n3t_fastlane_write_enabled_execute_policy_v1",
                            "user_confirmed": True,
                            "n5_action_intake": {"execute": True},
                            "n3_c1_n3t_action_confirmation": {"execute": True},
                            "n5_action_executed": {"execute": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = build_fastlane_active_launchd_plan(
                working_directory=WORKING_DIRECTORY,
                activation_config_path=str(config_path),
            )

        n3_args = plan["n3_c1_n3t"]["plist"]["ProgramArguments"]
        self.assertFalse(plan["automatic_worker_activation_ready"])
        self.assertEqual(plan["activation_scope"], "partial_lane_bootstrap")
        self.assertEqual(
            plan["write_enabled_lane_readiness"],
            {
                "n5_action_intake": True,
                "n5_active_scope_artifact": False,
                "n3_c1_n3t_action_confirmation": True,
                "n5_action_executed": True,
            },
        )
        self.assertIn("--execute", n3_args)
        self.assertIn("--user-confirmed", n3_args)
        self.assertNotIn("run_n3_intraday_b1_c1_b2_auto_poll_once.py", n3_args)

    def test_n3_runner_execute_without_executor_fails_closed(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            (artifact_dir / "n5_active_scope_snapshot_v1.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 1,
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_EXECUTE")
        self.assertEqual(manifest["blocked_reason"], "scoped_c1_n3t_executor_required")
        self.assertTrue(manifest["execute_requested"])
        self.assertFalse(manifest["writes_enabled"])
        plan = manifest["scoped_executor_plan"]
        self.assertEqual(plan["plan_status"], "blocked")
        self.assertEqual(plan["blocked_reason"], "scoped_c1_n3t_executor_required")
        self.assertEqual(plan["planned_artifact_count"], 1)
        planned = plan["planned_artifacts"][0]
        self.assertEqual(planned["target_hhmm"], "0943")
        self.assertRegex(planned["source_run_hash"], r"^[0-9a-f]{12}$")
        self.assertEqual(planned["namespace_token"], f"20260703_0943_{planned['source_run_hash']}")
        self.assertEqual(
            planned["pull_plan_path"],
            str(output_dir / f"n3_c1_scoped_current_day_pull_plan_v1_{planned['namespace_token']}_fastlane.json"),
        )
        self.assertEqual(
            planned["staging_artifact_path"],
            str(
                output_dir
                / "current_day_staging"
                / f"n3_c1_scoped_current_day_staging_v1_{planned['namespace_token']}_fastlane.json"
            ),
        )
        self.assertEqual(
            planned["metric_context_artifact_path"],
            str(
                output_dir
                / "metric_context"
                / f"n3_c1_scoped_closed_1m_artifact_v1_{planned['namespace_token']}_fastlane_raw_prevday_c1_amount_v1.json"
            ),
        )
        self.assertEqual(
            planned["n3t_metric_run_id"],
            f"n3t_action_confirmation_metric_20260703_until_0943__fastlane_sr_{planned['source_run_hash']}_raw_prevday_c1_amount_v1",
        )
        self.assertFalse(plan["side_effects"]["writes_db"])
        self.assertFalse(plan["side_effects"]["pulls_market_data"])
        self.assertFalse(plan["side_effects"]["writes_outbox"])

    def test_fastlane_namespace_is_source_run_scoped_without_full_source_run_id(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_source_run_namespace,
        )

        source_run_id = (
            "trigger_provisional_ordinary_20260703_until_0943__"
            "realtime_action_confirmation_metric_20260703_until_0943__"
            "asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1"
        )

        namespace = build_fastlane_source_run_namespace(
            for_trade_date="20260703",
            source_trigger_run_id=source_run_id,
        )

        self.assertEqual(namespace["target_hhmm"], "0943")
        self.assertEqual(namespace["for_trade_date"], "20260703")
        self.assertRegex(namespace["source_run_hash"], r"^[0-9a-f]{12}$")
        self.assertEqual(namespace["token"], f"20260703_0943_{namespace['source_run_hash']}")
        self.assertNotIn(source_run_id, namespace["token"])

    def test_n3_runner_source_run_scoped_plan_avoids_same_hhmm_collision(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        ordinary_source = "trigger_provisional_ordinary_20260703_until_0943__ordinary_lineage"
        b2_source = "trigger_b2_hint_projection_20260703_until_0943__b2_lineage"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            for filename, source_run_id in (
                ("ordinary.json", ordinary_source),
                ("b2.json", b2_source),
            ):
                (artifact_dir / filename).write_text(
                    json.dumps(
                        {
                            "artifact_type": "n5_active_scope_snapshot_v1",
                            "for_trade_date": "20260703",
                            "scope_count": 1,
                            "source_trigger_run_id": source_run_id,
                            "action_run_id": f"n5_live_tracking_20260703__{source_run_id}__fastlane_v1",
                            "full_market_fallback_allowed": False,
                            "n3_scans_n5_internals": False,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )

        planned = manifest["scoped_executor_plan"]["planned_artifacts"]
        self.assertEqual(len(planned), 2)
        self.assertEqual({item["target_hhmm"] for item in planned}, {"0943"})
        self.assertEqual(len({item["pull_plan_path"] for item in planned}), 2)
        self.assertEqual(len({item["staging_artifact_path"] for item in planned}), 2)
        self.assertEqual(len({item["metric_context_artifact_path"] for item in planned}), 2)
        self.assertEqual(len({item["n3t_metric_run_id"] for item in planned}), 2)
        for item in planned:
            self.assertRegex(item["source_run_hash"], r"^[0-9a-f]{12}$")
            self.assertIn(item["source_run_hash"], item["pull_plan_path"])
            self.assertIn(item["source_run_hash"], item["n3t_metric_run_id"])
            self.assertNotIn(ordinary_source, item["pull_plan_path"])
            self.assertNotIn(b2_source, item["pull_plan_path"])

    def test_n3_runner_execute_materializes_missing_scoped_pull_plan_artifact(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260703",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:43:00+08:00",
                            "current_exchange_time": "2026-07-03T09:45:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )

            planned = manifest["scoped_executor_plan"]["planned_artifacts"][0]
            pull_plan_path = Path(planned["pull_plan_path"])
            self.assertTrue(pull_plan_path.exists())
            pull_plan = json.loads(pull_plan_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_EXECUTE")
        self.assertEqual(pull_plan["artifact_type"], "n3_c1_scoped_current_day_pull_plan_v1")
        self.assertEqual(pull_plan["plan_status"], "planned")
        self.assertEqual(pull_plan["scope_count"], 1)
        self.assertEqual(pull_plan["plan_rows"][0]["identity_key"], "stock:SZ:300803")
        self.assertFalse(pull_plan["database_written"])
        self.assertFalse(pull_plan["market_data_pulled"])
        self.assertFalse(pull_plan["writes_n3_outbox"])
        self.assertEqual(
            planned["component_readiness"]["status"],
            "waiting_for_scoped_pull_staging",
        )

    def test_n3_runner_normalizes_call_auction_scope_to_first_closed_minute_target(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260706",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260706_until_0925__fastlane_v1",
                "scope_status": "active",
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260706_0925.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260706",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "source_trigger_run_id": scope_row["source_trigger_run_id"],
                        "action_run_id": (
                            "n5_live_tracking_20260706__"
                            "trigger_provisional_ordinary_20260706_until_0925__fastlane_v1"
                        ),
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260706",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "session_context": {
                            "trigger_time": "2026-07-06T09:25:00+08:00",
                            "current_exchange_time": "2026-07-06T09:31:30+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )

            planned = manifest["scoped_executor_plan"]["planned_artifacts"][0]
            pull_plan_path = Path(planned["pull_plan_path"])
            pull_plan_exists = pull_plan_path.exists()
            raw_0925_plan_exists = (output_dir / "n3_c1_scoped_current_day_pull_plan_v1_0925_fastlane.json").exists()

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_EXECUTE")
        self.assertTrue(pull_plan_exists)
        self.assertEqual(planned["target_hhmm"], "0930")
        self.assertRegex(planned["source_run_hash"], r"^[0-9a-f]{12}$")
        self.assertEqual(
            planned["n3t_metric_run_id"],
            f"n3t_action_confirmation_metric_20260706_until_0930__fastlane_sr_{planned['source_run_hash']}_raw_prevday_c1_amount_v1",
        )
        self.assertEqual(
            planned["component_readiness"]["status"],
            "waiting_for_scoped_pull_staging",
        )
        self.assertFalse(raw_0925_plan_exists)

    def test_n3_runner_waits_until_active_scope_target_minute_is_closed(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260706",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260706_until_0931__fastlane_v1",
                "scope_status": "active",
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260706_0931.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260706",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "source_trigger_run_id": scope_row["source_trigger_run_id"],
                        "action_run_id": (
                            "n5_live_tracking_20260706__"
                            "trigger_provisional_ordinary_20260706_until_0931__fastlane_v1"
                        ),
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260706",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "session_context": {
                            "trigger_time": "2026-07-06T09:31:00+08:00",
                            "current_exchange_time": "2026-07-06T09:31:30+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )

        self.assertEqual(manifest["verdict"], "BLOCKED_N3_C1_N3T_FASTLANE_EXECUTE")
        self.assertEqual(manifest["blocked_reason"], "target_minute_not_closed")
        self.assertFalse(
            (output_dir / "n3_c1_scoped_current_day_pull_plan_v1_0931_fastlane.json").exists()
        )
        self.assertFalse(manifest["writes_enabled"])

    def test_n3_runner_execute_builds_staging_from_configured_current_day_source_artifact(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "n3"
            current_source_dir = root / "current_day_source"
            metric_source_dir = root / "metric_source"
            previous_context_dir = root / "previous_day_context"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            current_source_dir.mkdir()
            metric_source_dir.mkdir()
            previous_context_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            active_scope = {
                "artifact_type": "n5_active_scope_snapshot_v1",
                "for_trade_date": "20260703",
                "scope_count": 1,
                "scope_rows": [scope_row],
                "source_trigger_run_id": scope_row["source_trigger_run_id"],
                "action_run_id": (
                    "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1"
                ),
                "full_market_fallback_allowed": False,
                "n3_scans_n5_internals": False,
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(active_scope, ensure_ascii=False),
                encoding="utf-8",
            )
            current_rows = []
            previous_rows = []
            labels = tuple(f"09:{minute:02d}" for minute in range(30, 44))
            for index, label in enumerate(labels, start=1):
                current_rows.append(
                    {
                        **scope_row,
                        "physical_c1_label": label,
                        "raw_source_label": f"09:{30 + index:02d}",
                        "open": 12 + index / 10,
                        "high": 12.8 + index / 10,
                        "low": 11.9,
                        "close": 12.2 + index / 10,
                        "amount": 1000 + index,
                        "source_row_ref": f"current:300803:{label}",
                        "fake_or_synthetic_row": False,
                    }
                )
                previous_rows.append(
                    {
                        "asset_kind": "stock",
                        "identity_key": "stock:SZ:300803",
                        "physical_c1_label": label,
                        "open": 10 + index / 10,
                        "high": 10.8 + index / 10,
                        "low": 9.9,
                        "close": 10.3 + index / 10,
                        "amount": 900 + index,
                        "source_row_ref": f"previous:300803:{label}",
                        "fake_or_synthetic_row": False,
                    }
                )
            (current_source_dir / "n3_c1_scoped_current_day_source_rows_v1_20260703_0943_abee3680ddd4.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_source_rows_v1",
                        "for_trade_date": "20260703",
                        "target_hhmm": "0943",
                        "source_run_hash": "abee3680ddd4",
                        "source_run_namespace": "20260703_0943_abee3680ddd4",
                        "closed_minute_rows": current_rows,
                        "database_written": False,
                        "writes_canonical_minute_bar_1m": False,
                        "writes_n3_outbox": False,
                        "touches_n4_n5_n6_outbox": False,
                        "full_market_fallback_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (previous_context_dir / "n3_c1_n3t_previous_day_context_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_n3t_previous_day_context_v1",
                        "for_trade_date": "20260703",
                        "target_hhmm": "0943",
                        "previous_day_minute_rows": previous_rows,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "n3_c1_n3t_current_day_source_artifact_dir": str(current_source_dir),
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(metric_source_dir),
                        "n3_c1_n3t_previous_day_context_artifact_dir": str(previous_context_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:43:00+08:00",
                            "current_exchange_time": "2026-07-03T09:45:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )
            staging_path = (
                output_dir
                / "current_day_staging"
                / "n3_c1_scoped_current_day_staging_v1_20260703_0943_abee3680ddd4_fastlane.json"
            )
            metric_path = (
                output_dir
                / "metric_context"
                / "n3_c1_scoped_closed_1m_artifact_v1_20260703_0943_abee3680ddd4_fastlane_raw_prevday_c1_amount_v1.json"
            )
            self.assertTrue(staging_path.exists())
            self.assertTrue(metric_path.exists())
            staging = json.loads(staging_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY")
        self.assertEqual(staging["artifact_type"], "n3_c1_scoped_current_day_staging_v1")
        self.assertEqual(staging["artifact_status"], "passed")
        self.assertEqual(staging["scope_count"], 1)
        self.assertEqual(staging["closed_minute_row_count"], 14)
        self.assertFalse(staging["database_written"])
        self.assertFalse(staging["writes_canonical_minute_bar_1m"])
        self.assertFalse(staging["writes_n3_outbox"])
        self.assertFalse(staging["full_market_fallback_used"])
        self.assertEqual(
            manifest["scoped_executor_plan"]["planned_artifacts"][0]["component_readiness"]["status"],
            "metric_context_ready_for_n3t_execute_gate",
        )

    def test_n3_runner_execute_uses_current_day_source_provider_before_staging(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "n3"
            current_source_dir = root / "current_day_source"
            metric_source_dir = root / "metric_source"
            previous_context_dir = root / "previous_day_context"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            current_source_dir.mkdir()
            metric_source_dir.mkdir()
            previous_context_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260703",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "source_trigger_run_id": scope_row["source_trigger_run_id"],
                        "action_run_id": (
                            "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1"
                        ),
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            previous_rows = []
            for index, label in enumerate(tuple(f"09:{minute:02d}" for minute in range(30, 44)), start=1):
                previous_rows.append(
                    {
                        "asset_kind": "stock",
                        "identity_key": "stock:SZ:300803",
                        "physical_c1_label": label,
                        "open": 10 + index / 10,
                        "high": 10.8 + index / 10,
                        "low": 9.9,
                        "close": 10.3 + index / 10,
                        "amount": 900 + index,
                        "source_row_ref": f"previous:300803:{label}",
                        "fake_or_synthetic_row": False,
                    }
                )
            (previous_context_dir / "n3_c1_n3t_previous_day_context_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_n3t_previous_day_context_v1",
                        "for_trade_date": "20260703",
                        "target_hhmm": "0943",
                        "previous_day_minute_rows": previous_rows,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "n3_c1_n3t_current_day_source_artifact_dir": str(current_source_dir),
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(metric_source_dir),
                        "n3_c1_n3t_previous_day_context_artifact_dir": str(previous_context_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:43:00+08:00",
                            "current_exchange_time": "2026-07-03T09:45:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            captured: dict[str, object] = {}

            def current_day_source_provider_adapter(*, args, planned_artifacts):
                captured["planned_count"] = len(planned_artifacts)
                planned = planned_artifacts[0]
                source_rows = []
                for index, label in enumerate(tuple(f"09:{minute:02d}" for minute in range(30, 44)), start=1):
                    source_rows.append(
                        {
                            **scope_row,
                            "physical_c1_label": label,
                            "raw_source_label": f"09:{30 + index:02d}",
                            "open": 12 + index / 10,
                            "high": 12.8 + index / 10,
                            "low": 11.9,
                            "close": 12.2 + index / 10,
                            "amount": 1000 + index,
                            "source_row_ref": f"provider:300803:{label}",
                            "fake_or_synthetic_row": False,
                        }
                    )
                output_path = Path(args.current_day_source_artifact_dir) / (
                    f"n3_c1_scoped_current_day_source_rows_v1_{planned['namespace_token']}.json"
                )
                output_path.write_text(
                    json.dumps(
                        {
                            "artifact_type": "n3_c1_scoped_current_day_source_rows_v1",
                            "for_trade_date": "20260703",
                            "target_hhmm": planned["target_hhmm"],
                            "source_run_hash": planned["source_run_hash"],
                            "source_run_namespace": planned["namespace_token"],
                            "closed_minute_rows": source_rows,
                            "database_written": False,
                            "writes_canonical_minute_bar_1m": False,
                            "writes_n3_outbox": False,
                            "touches_n4_n5_n6_outbox": False,
                            "full_market_fallback_used": False,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return {
                    "adapter_type": "n3_c1_scoped_current_day_source_rows_provider_adapter_v1",
                    "artifact_written": True,
                    "artifact_count": 1,
                    "market_data_pulled": True,
                    "database_written": False,
                    "writes_canonical_minute_bar_1m": False,
                    "writes_n3_outbox": False,
                    "touches_n4_n5_n6_outbox": False,
                    "updates_n4_outbox": False,
                    "scans_n5_db": False,
                    "touches_n6": False,
                    "full_market_fallback_used": False,
                }

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"],
                current_day_source_provider_adapter=current_day_source_provider_adapter,
            )

            source_artifacts = sorted(current_source_dir.glob("*.json"))
            staging_path = (
                output_dir
                / "current_day_staging"
                / "n3_c1_scoped_current_day_staging_v1_20260703_0943_abee3680ddd4_fastlane.json"
            )
            metric_path = (
                output_dir
                / "metric_context"
                / "n3_c1_scoped_closed_1m_artifact_v1_20260703_0943_abee3680ddd4_fastlane_raw_prevday_c1_amount_v1.json"
            )
            staging_exists = staging_path.exists()
            metric_exists = metric_path.exists()

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY")
        self.assertEqual(captured["planned_count"], 1)
        self.assertEqual(len(source_artifacts), 1)
        self.assertTrue(staging_exists)
        self.assertTrue(metric_exists)
        self.assertEqual(
            manifest["current_day_source_provider_result"]["adapter_type"],
            "n3_c1_scoped_current_day_source_rows_provider_adapter_v1",
        )
        self.assertTrue(manifest["current_day_source_provider_result"]["market_data_pulled"])
        self.assertFalse(manifest["current_day_source_provider_result"]["database_written"])
        self.assertFalse(manifest["current_day_source_provider_result"]["writes_canonical_minute_bar_1m"])
        self.assertFalse(manifest["current_day_source_provider_result"]["writes_n3_outbox"])

    def test_n3_runner_configured_current_day_source_provider_uses_scoped_market_adapter(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        class FakeMarketAdapter:
            source_version = "fake.scoped.market.provider.v1"
            external_source = "fake_mootdx"

            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def fetch_minute_bars(self, subscription, trade_date):
                self.calls.append({"subscription": dict(subscription), "trade_date": trade_date})
                rows = []
                for index, label in enumerate(tuple(f"09:{minute:02d}" for minute in range(30, 44)), start=1):
                    rows.append(
                        {
                            "physical_c1_label": label,
                            "raw_source_label": f"09:{30 + index:02d}",
                            "open": 12 + index / 10,
                            "high": 12.8 + index / 10,
                            "low": 11.9,
                            "close": 12.2 + index / 10,
                            "amount": 1000 + index,
                            "fake_or_synthetic_row": False,
                        }
                    )
                return rows

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "n3"
            current_source_dir = root / "current_day_source"
            metric_source_dir = root / "metric_source"
            previous_context_dir = root / "previous_day_context"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            current_source_dir.mkdir()
            metric_source_dir.mkdir()
            previous_context_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260703",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "source_trigger_run_id": scope_row["source_trigger_run_id"],
                        "action_run_id": (
                            "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1"
                        ),
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            previous_rows = []
            for index, label in enumerate(tuple(f"09:{minute:02d}" for minute in range(30, 44)), start=1):
                previous_rows.append(
                    {
                        "asset_kind": "stock",
                        "identity_key": "stock:SZ:300803",
                        "physical_c1_label": label,
                        "open": 10 + index / 10,
                        "high": 10.8 + index / 10,
                        "low": 9.9,
                        "close": 10.3 + index / 10,
                        "amount": 900 + index,
                        "source_row_ref": f"previous:300803:{label}",
                        "fake_or_synthetic_row": False,
                    }
                )
            (previous_context_dir / "n3_c1_n3t_previous_day_context_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_n3t_previous_day_context_v1",
                        "for_trade_date": "20260703",
                        "target_hhmm": "0943",
                        "previous_day_minute_rows": previous_rows,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "n3_c1_n3t_current_day_source_artifact_dir": str(current_source_dir),
                        "n3_c1_n3t_current_day_source_provider": "mootdx_today_minute_adapter_v1",
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(metric_source_dir),
                        "n3_c1_n3t_previous_day_context_artifact_dir": str(previous_context_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:43:00+08:00",
                            "current_exchange_time": "2026-07-03T09:45:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            fake_adapter = FakeMarketAdapter()
            with patch("ashare_v3.market.today_minute_execute.MootdxTodayMinuteAdapter", return_value=fake_adapter):
                manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                    ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
                )

            source_artifacts = sorted(current_source_dir.glob("*.json"))
            source_payload = json.loads(source_artifacts[0].read_text(encoding="utf-8"))

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY")
        self.assertEqual(len(fake_adapter.calls), 1)
        self.assertEqual(fake_adapter.calls[0]["subscription"]["identity_key"], "stock:SZ:300803")
        self.assertEqual(fake_adapter.calls[0]["subscription"]["code"], "300803")
        self.assertEqual(source_payload["artifact_type"], "n3_c1_scoped_current_day_source_rows_v1")
        self.assertEqual(source_payload["closed_minute_row_count"], 14)
        self.assertTrue(source_payload["market_data_pulled"])
        self.assertFalse(source_payload["database_written"])
        self.assertFalse(source_payload["writes_canonical_minute_bar_1m"])
        self.assertFalse(source_payload["writes_n3_outbox"])

    def test_n3_runner_execute_uses_metric_context_builder_adapter_after_staging_ready(self) -> None:
        from ashare_v3.market.c1_scoped_artifact import build_n3_c1_scoped_artifact_plan
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            staging_dir = output_dir / "current_day_staging"
            metric_dir = output_dir / "metric_context"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            staging_dir.mkdir(parents=True)
            metric_dir.mkdir(parents=True)
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            active_scope = {
                "artifact_type": "n5_active_scope_snapshot_v1",
                "for_trade_date": "20260703",
                "scope_count": 1,
                "scope_rows": [scope_row],
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "full_market_fallback_allowed": False,
                "n3_scans_n5_internals": False,
            }
            active_scope_path = artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json"
            active_scope_path.write_text(json.dumps(active_scope, ensure_ascii=False), encoding="utf-8")
            (output_dir / "n3_c1_scoped_current_day_pull_plan_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_pull_plan_v1",
                        "plan_status": "planned",
                        "scope_count": 1,
                        "full_market_fallback_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (staging_dir / "n3_c1_scoped_current_day_staging_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_staging_v1",
                        "artifact_status": "passed",
                        "scope_count": 1,
                        "closed_minute_row_count": 1,
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "writes_canonical_minute_bar_1m": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:43:00+08:00",
                            "current_exchange_time": "2026-07-03T09:45:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def metric_context_builder_adapter(*, args, planned_artifacts):
                captured["planned_count"] = len(planned_artifacts)
                planned = planned_artifacts[0]
                metric_path = Path(planned["metric_context_artifact_path"])
                metric_artifact = build_n3_c1_scoped_artifact_plan(
                    active_scope,
                    target_minute_label="09:43",
                    observed_at="2026-07-03T09:45:00+08:00",
                    source_artifact_path=str(active_scope_path),
                    source_artifact_hash="sha256:scope",
                    metric_context_rows=[
                        {
                            **scope_row,
                            "source_closed_minute_bar_ids": ["staging:row:101"],
                            "closed_minute_rows": [{"source_row_ref": "staging:row:101"}],
                            "previous_day_minute_refs": ["previous:row:201"],
                            "metric_values": {
                                "current_price": 12,
                                "previous_120m_body_high": 11,
                                "previous_120m_body_low": 9,
                                "previous_30m_body_high": 10.5,
                                "previous_30m_body_low": 9.5,
                                "previous_5m_body_high": 10.1,
                                "previous_5m_body_low": 9.8,
                                "previous_1m_body_high": 10,
                                "previous_1m_body_low": 9.9,
                                "current_1m_amount": 1000,
                                "previous_1m_amount": 900,
                                "current_5m_amount": 5000,
                                "previous_5m_amount": 4500,
                                "current_30m_closed_elapsed_amount": 30000,
                                "previous_day_same_window_amount": 28000,
                            },
                            "deterministic_derivation_inputs": {
                                "previous_day_same_window_amount_source": "scoped_previous_day_raw_c1_sum",
                            },
                        }
                    ],
                )
                metric_path.write_text(
                    json.dumps(metric_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                return {
                    "adapter_type": "n3_c1_n3t_metric_context_builder_adapter_v1",
                    "artifact_written": True,
                    "artifact_count": 1,
                    "database_written": False,
                    "market_data_pulled": False,
                    "runtime_execute": False,
                    "writes_canonical_minute_bar_1m": False,
                    "writes_n3_outbox": False,
                    "touches_n4_n5_n6_outbox": False,
                    "full_market_fallback_used": False,
                }

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"],
                metric_context_builder_adapter=metric_context_builder_adapter,
            )

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY")
        self.assertEqual(captured["planned_count"], 1)
        self.assertFalse(manifest["writes_enabled"])
        self.assertEqual(
            manifest["metric_context_builder_result"]["adapter_type"],
            "n3_c1_n3t_metric_context_builder_adapter_v1",
        )
        planned = manifest["scoped_executor_plan"]["planned_artifacts"][0]
        self.assertEqual(
            planned["component_readiness"]["status"],
            "metric_context_ready_for_n3t_execute_gate",
        )
        self.assertEqual(manifest["execute_result"]["metric_plan_row_count"], 1)
        self.assertEqual(
            manifest["execute_result"]["target_table_counts"],
            {"stock_n3t_action_confirmation_metric": 1},
        )

    def test_n3_runner_execute_builds_metric_context_from_configured_source_artifact(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            staging_dir = output_dir / "current_day_staging"
            metric_source_dir = root / "metric_source"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            staging_dir.mkdir(parents=True)
            metric_source_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260703",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / "n3_c1_scoped_current_day_pull_plan_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_pull_plan_v1",
                        "plan_status": "planned",
                        "scope_count": 1,
                        "full_market_fallback_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (staging_dir / "n3_c1_scoped_current_day_staging_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_staging_v1",
                        "artifact_status": "passed",
                        "scope_count": 1,
                        "closed_minute_row_count": 1,
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "writes_canonical_minute_bar_1m": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (metric_source_dir / "n3_c1_n3t_metric_context_source_v1_20260703_0943_abee3680ddd4.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_n3t_metric_context_source_v1",
                        "for_trade_date": "20260703",
                        "target_hhmm": "0943",
                        "source_run_hash": "abee3680ddd4",
                        "source_run_namespace": "20260703_0943_abee3680ddd4",
                        "metric_context_rows": [
                            {
                                **scope_row,
                                "source_closed_minute_bar_ids": ["staging:row:101"],
                                "closed_minute_rows": [{"source_row_ref": "staging:row:101"}],
                                "previous_day_minute_refs": ["previous:row:201"],
                                "metric_values": {
                                    "current_price": 12,
                                    "previous_120m_body_high": 11,
                                    "previous_120m_body_low": 9,
                                    "previous_30m_body_high": 10.5,
                                    "previous_30m_body_low": 9.5,
                                    "previous_5m_body_high": 10.1,
                                    "previous_5m_body_low": 9.8,
                                    "previous_1m_body_high": 10,
                                    "previous_1m_body_low": 9.9,
                                    "current_1m_amount": 1000,
                                    "previous_1m_amount": 900,
                                    "current_5m_amount": 5000,
                                    "previous_5m_amount": 4500,
                                    "current_30m_closed_elapsed_amount": 30000,
                                    "previous_day_same_window_amount": 28000,
                                },
                                "deterministic_derivation_inputs": {
                                    "previous_day_same_window_amount_source": "scoped_previous_day_raw_c1_sum",
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(metric_source_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:43:00+08:00",
                            "current_exchange_time": "2026-07-03T09:45:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )
            metric_path = (
                output_dir
                / "metric_context"
                / "n3_c1_scoped_closed_1m_artifact_v1_20260703_0943_abee3680ddd4_fastlane_raw_prevday_c1_amount_v1.json"
            )
            self.assertTrue(metric_path.exists())
            metric_artifact = json.loads(metric_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY")
        self.assertEqual(
            manifest["metric_context_builder_result"]["adapter_type"],
            "n3_c1_n3t_metric_context_builder_adapter_v1",
        )
        self.assertEqual(metric_artifact["artifact_type"], "n3_c1_scoped_closed_1m_artifact_v1")
        self.assertEqual(metric_artifact["metric_context_status"], "ready")
        self.assertEqual(metric_artifact["metric_context_count"], 1)
        self.assertFalse(metric_artifact["database_written"])
        self.assertFalse(metric_artifact["market_data_pulled"])
        self.assertFalse(metric_artifact["writes_n3_outbox"])
        planned = manifest["scoped_executor_plan"]["planned_artifacts"][0]
        self.assertEqual(
            planned["component_readiness"]["status"],
            "metric_context_ready_for_n3t_execute_gate",
        )
        self.assertEqual(manifest["execute_result"]["metric_plan_row_count"], 1)

    def test_n3_runner_execute_builds_metric_context_source_from_previous_day_context_artifact(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "n3"
            staging_dir = output_dir / "current_day_staging"
            metric_source_dir = root / "metric_source"
            previous_context_dir = root / "previous_day_context"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            staging_dir.mkdir(parents=True)
            metric_source_dir.mkdir()
            previous_context_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260703",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "source_trigger_run_id": scope_row["source_trigger_run_id"],
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / "n3_c1_scoped_current_day_pull_plan_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_pull_plan_v1",
                        "plan_status": "planned",
                        "scope_count": 1,
                        "full_market_fallback_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (staging_dir / "n3_c1_scoped_current_day_staging_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_staging_v1",
                        "artifact_status": "passed",
                        "for_trade_date": "20260703",
                        "scope_count": 1,
                        "closed_minute_row_count": 1,
                        "closed_minute_rows": [
                            {
                                **scope_row,
                                "physical_c1_label": "09:43",
                                "raw_source_label": "09:44",
                                "open": 12,
                                "high": 12.6,
                                "low": 11.8,
                                "close": 12.5,
                                "amount": 1000,
                                "source_row_ref": "current:300803:0943",
                                "fake_or_synthetic_row": False,
                            }
                        ],
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "market_data_pulled": True,
                        "writes_canonical_minute_bar_1m": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (previous_context_dir / "n3_c1_n3t_previous_day_context_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_n3t_previous_day_context_v1",
                        "for_trade_date": "20260703",
                        "target_hhmm": "0943",
                        "previous_day_minute_rows": [
                            {
                                "asset_kind": "stock",
                                "identity_key": "stock:SZ:300803",
                                "physical_c1_label": "09:43",
                                "open": 10,
                                "high": 10.8,
                                "low": 9.9,
                                "close": 10.4,
                                "amount": 900,
                                "source_row_ref": "previous:300803:0943",
                                "fake_or_synthetic_row": False,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260703",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(metric_source_dir),
                        "n3_c1_n3t_previous_day_context_artifact_dir": str(previous_context_dir),
                        "session_context": {
                            "trigger_time": "2026-07-03T09:43:00+08:00",
                            "current_exchange_time": "2026-07-03T09:45:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
            )
            source_artifacts = sorted(metric_source_dir.glob("*.json"))

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY")
        self.assertEqual(len(source_artifacts), 1)
        self.assertEqual(
            manifest["metric_context_builder_result"]["source_artifacts"][0]["artifact_type"],
            "n3_c1_n3t_metric_context_source_v1",
        )
        self.assertFalse(manifest["metric_context_builder_result"]["database_written"])
        self.assertFalse(manifest["metric_context_builder_result"]["market_data_pulled"])

    def test_n3_runner_execute_can_prewarm_previous_day_context_from_configured_provider(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "n3"
            staging_dir = output_dir / "current_day_staging"
            metric_source_dir = root / "metric_source"
            previous_context_dir = root / "previous_day_context"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            staging_dir.mkdir(parents=True)
            metric_source_dir.mkdir()
            previous_context_dir.mkdir()
            scope_row = {
                "for_trade_date": "20260706",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260706_until_0931__fastlane_v1",
                "scope_status": "active",
            }
            (artifact_dir / "n5_active_scope_snapshot_v1_20260706_0931.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260706",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "source_trigger_run_id": scope_row["source_trigger_run_id"],
                        "action_run_id": "n5_live_tracking_20260706__trigger_provisional_ordinary_20260706_until_0931__fastlane_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (
                staging_dir / "n3_c1_scoped_current_day_staging_v1_20260706_0931_98a646ba5053_fastlane.json"
            ).write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_staging_v1",
                        "artifact_status": "passed",
                        "for_trade_date": "20260706",
                        "scope_count": 1,
                        "closed_minute_row_count": 1,
                        "closed_minute_rows": [
                            {
                                **scope_row,
                                "physical_c1_label": "09:30",
                                "raw_source_label": "09:31",
                                "open": 12,
                                "high": 12.6,
                                "low": 11.8,
                                "close": 12.5,
                                "amount": 1000,
                                "source_row_ref": "current:300803:0930",
                                "fake_or_synthetic_row": False,
                            }
                        ],
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "market_data_pulled": True,
                        "writes_canonical_minute_bar_1m": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "for_trade_date": "20260706",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "n3_c1_n3t_metric_context_source_artifact_dir": str(metric_source_dir),
                        "n3_c1_n3t_previous_day_context_artifact_dir": str(previous_context_dir),
                        "n3_c1_n3t_previous_day_context_provider": "postgres_previous_day_raw_c1_context_v1",
                        "session_context": {
                            "trigger_time": "2026-07-06T09:31:00+08:00",
                            "current_exchange_time": "2026-07-06T09:32:00+08:00",
                            "trade_calendar_is_open": True,
                            "formal_trigger_matched_available": True,
                            "closed_minute_available": True,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def previous_day_context_provider_adapter(*, args, planned_artifact, target_hhmm, previous_context_dir):
                path = Path(previous_context_dir) / "n3_c1_n3t_previous_day_context_v1_20260706_0931.json"
                path.write_text(
                    json.dumps(
                        {
                            "artifact_type": "n3_c1_n3t_previous_day_context_v1",
                            "for_trade_date": "20260706",
                            "target_hhmm": target_hhmm,
                            "previous_day_minute_rows": [
                                {
                                    "asset_kind": "stock",
                                    "identity_key": "stock:SZ:300803",
                                    "physical_c1_label": "09:30",
                                    "raw_source_label": "09:31",
                                    "open": 10,
                                    "high": 10.8,
                                    "low": 9.9,
                                    "close": 10.4,
                                    "amount": 900,
                                    "source_row_ref": "previous:300803:0930",
                                    "fake_or_synthetic_row": False,
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return {
                    "adapter_type": "n3_c1_n3t_previous_day_context_provider_adapter_v1",
                    "provider_name": "postgres_previous_day_raw_c1_context_v1",
                    "artifact_written": True,
                    "artifact_count": 1,
                    "previous_day_context_artifacts": [{"path": str(path), "target_hhmm": target_hhmm}],
                    "database_written": False,
                    "market_data_pulled": False,
                    "runtime_execute": False,
                    "writes_canonical_minute_bar_1m": False,
                    "writes_n3_outbox": False,
                    "writes_common_event_outbox": False,
                    "touches_n4_n5_n6_outbox": False,
                    "updates_n4_outbox": False,
                    "scans_n5_db": False,
                    "touches_n6": False,
                    "full_market_fallback_used": False,
                }

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"],
                previous_day_context_provider_adapter=previous_day_context_provider_adapter,
            )

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY")
        self.assertEqual(
            manifest["metric_context_builder_result"]["previous_day_context_provider_results"][0][
                "adapter_type"
            ],
            "n3_c1_n3t_previous_day_context_provider_adapter_v1",
        )

    def test_n3_runner_scoped_executor_plan_reports_local_component_readiness(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_source_run_namespace,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            metric_dir = output_dir / "metric_context"
            staging_dir = output_dir / "current_day_staging"
            artifact_dir.mkdir()
            metric_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)
            source_trigger_run_id = "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1"
            action_run_id = "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1"
            namespace = build_fastlane_source_run_namespace(
                for_trade_date="20260703",
                source_trigger_run_id=source_trigger_run_id,
                action_run_id=action_run_id,
                target_hhmm="0943",
            )
            namespace_token = namespace["token"]
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 1,
                        "source_trigger_run_id": source_trigger_run_id,
                        "action_run_id": action_run_id,
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / f"n3_c1_scoped_current_day_pull_plan_v1_{namespace_token}_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_pull_plan_v1",
                        "plan_status": "planned",
                        "scope_count": 1,
                        "full_market_fallback_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (staging_dir / f"n3_c1_scoped_current_day_staging_v1_{namespace_token}_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_staging_v1",
                        "artifact_status": "passed",
                        "scope_count": 1,
                        "closed_minute_row_count": 14,
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "writes_canonical_minute_bar_1m": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": source_trigger_run_id,
                "scope_status": "active",
            }
            metric_values = {
                "current_price": 12,
                "previous_120m_body_high": 11,
                "previous_120m_body_low": 9,
                "previous_30m_body_high": 10.5,
                "previous_30m_body_low": 9.5,
                "previous_5m_body_high": 10.1,
                "previous_5m_body_low": 9.8,
                "previous_1m_body_high": 10,
                "previous_1m_body_low": 9.9,
                "current_1m_amount": 1000,
                "previous_1m_amount": 900,
                "current_5m_amount": 5000,
                "previous_5m_amount": 4500,
                "current_30m_closed_elapsed_amount": 30000,
                "previous_day_same_window_amount": 28000,
            }
            (
                metric_dir / f"n3_c1_scoped_closed_1m_artifact_v1_{namespace_token}_fastlane_raw_prevday_c1_amount_v1.json"
            ).write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_closed_1m_artifact_v1",
                        "artifact_status": "planned",
                        "for_trade_date": "20260703",
                        "target_minute_label": "09:43",
                        "metric_context_status": "ready",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "metric_context_count": 1,
                        "metric_context_rows": [
                            {
                                **scope_row,
                                "source_closed_minute_bar_ids": [101],
                                "closed_minute_rows": [{"source_row_ref": "staging:row:101"}],
                                "previous_day_minute_refs": [201],
                                "metric_values": metric_values,
                                "deterministic_derivation_inputs": {
                                    "previous_day_same_window_amount_source": "scoped_previous_day_raw_c1_sum",
                                },
                            }
                        ],
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "runtime_execute": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                [
                    "--fastlane-lane-id",
                    "n5_action_confirmation_fastlane_v1",
                    "--active-scope-artifact-dir",
                    str(artifact_dir),
                    "--output-dir",
                    str(output_dir),
                    "--max-runtime-seconds",
                    "5",
                    "--execute",
                    "--user-confirmed",
                ]
            )

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY")
        self.assertTrue(manifest["execute_requested"])
        self.assertFalse(manifest["writes_enabled"])
        self.assertEqual(
            manifest["execute_result"]["adapter_type"],
            "n3t_action_confirmation_metric_writer_handoff_v1",
        )
        self.assertEqual(manifest["execute_result"]["n3t_writer_input_count"], 1)
        self.assertEqual(manifest["execute_result"]["metric_plan_row_count"], 1)
        self.assertEqual(
            manifest["execute_result"]["target_table_counts"],
            {"stock_n3t_action_confirmation_metric": 1},
        )
        self.assertFalse(manifest["execute_result"]["db_write_executed"])
        self.assertEqual(
            manifest["execute_result"]["next_required_gate"],
            "N3T_FASTLANE_WRITER_ADAPTER_PATCH_GATE",
        )
        planned = manifest["scoped_executor_plan"]["planned_artifacts"][0]
        readiness = planned["component_readiness"]
        self.assertEqual(readiness["status"], "metric_context_ready_for_n3t_execute_gate")
        self.assertEqual(readiness["next_required_gate"], "N3T_FASTLANE_0943_SCOPED_METRIC_EXECUTE_GATE")
        self.assertEqual(readiness["scope_count"], 1)
        self.assertEqual(readiness["metric_context_count"], 1)
        self.assertEqual(readiness["closed_minute_row_count"], 14)
        self.assertEqual(readiness["violations"], [])
        self.assertIn("pull_plan_sha256", readiness)
        self.assertIn("staging_artifact_sha256", readiness)
        self.assertIn("metric_context_artifact_sha256", readiness)
        writer_plan = readiness["n3t_writer_plan_summary"]
        self.assertEqual(writer_plan["plan_status"], "planned")
        self.assertEqual(writer_plan["metric_plan_row_count"], 1)
        self.assertEqual(writer_plan["target_table_counts"], {"stock_n3t_action_confirmation_metric": 1})
        self.assertEqual(writer_plan["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(writer_plan["metric_role"], "action_confirmation")
        self.assertEqual(writer_plan["proof_consumer"], "N5")
        self.assertFalse(writer_plan["not_n5_final_proof"])
        self.assertFalse(writer_plan["side_effects"]["database_written"])

    def test_n3_runner_execute_uses_explicit_artifact_executor(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        captured: dict[str, object] = {}

        def executor(*, args, active_scope_artifacts):
            captured["artifact_count"] = len(active_scope_artifacts)
            captured["output_dir"] = args.output_dir
            return {
                "executed": True,
                "artifact_count": len(active_scope_artifacts),
                "writes_db": False,
                "writes_n3_outbox": False,
                "full_market_fallback_used": False,
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            (artifact_dir / "n5_active_scope_snapshot_v1.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 1,
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                ["--activation-config", str(config_path), "--execute", "--user-confirmed"],
                scoped_executor=executor,
            )

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_EXECUTE_PASS")
        self.assertTrue(manifest["writes_enabled"])
        self.assertEqual(manifest["execute_result"]["artifact_count"], 1)
        self.assertEqual(captured["artifact_count"], 1)
        self.assertEqual(captured["output_dir"], str(output_dir))

    def test_n3_runner_execute_uses_explicit_n3t_writer_adapter_contract(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        captured: dict[str, object] = {}

        def n3t_writer_adapter(*, args, n3t_writer_inputs):
            captured["output_dir"] = args.output_dir
            captured["input_count"] = len(n3t_writer_inputs)
            captured["input"] = n3t_writer_inputs[0]
            captured["metric_context_path_exists"] = Path(n3t_writer_inputs[0]["metric_context_artifact_path"]).exists()
            return {
                "adapter_type": "n3t_action_confirmation_metric_writer_adapter_v1",
                "write_executed": True,
                "source_basis": "N3T_C1_CLOSED",
                "metric_role": "action_confirmation",
                "proof_consumer": "N5",
                "not_n5_final_proof": False,
                "inserted_rows": 1,
                "target_table_counts": {"stock_n3t_action_confirmation_metric": 1},
                "writes_common_event_outbox": False,
                "writes_canonical_minute_bar_1m": False,
                "touches_n4_n5_n6_outbox": False,
                "full_market_fallback_used": False,
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            metric_dir = output_dir / "metric_context"
            staging_dir = output_dir / "current_day_staging"
            artifact_dir.mkdir()
            metric_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 1,
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / "n3_c1_scoped_current_day_pull_plan_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_pull_plan_v1",
                        "plan_status": "planned",
                        "scope_count": 1,
                        "full_market_fallback_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (staging_dir / "n3_c1_scoped_current_day_staging_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_staging_v1",
                        "artifact_status": "passed",
                        "scope_count": 1,
                        "closed_minute_row_count": 14,
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "writes_canonical_minute_bar_1m": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            metric_values = {
                "current_price": 12,
                "previous_120m_body_high": 11,
                "previous_120m_body_low": 9,
                "previous_30m_body_high": 10.5,
                "previous_30m_body_low": 9.5,
                "previous_5m_body_high": 10.1,
                "previous_5m_body_low": 9.8,
                "previous_1m_body_high": 10,
                "previous_1m_body_low": 9.9,
                "current_1m_amount": 1000,
                "previous_1m_amount": 900,
                "current_5m_amount": 5000,
                "previous_5m_amount": 4500,
                "current_30m_closed_elapsed_amount": 30000,
                "previous_day_same_window_amount": 28000,
            }
            (
                metric_dir / "n3_c1_scoped_closed_1m_artifact_v1_20260703_0943_abee3680ddd4_fastlane_raw_prevday_c1_amount_v1.json"
            ).write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_closed_1m_artifact_v1",
                        "artifact_status": "planned",
                        "for_trade_date": "20260703",
                        "target_minute_label": "09:43",
                        "metric_context_status": "ready",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "metric_context_count": 1,
                        "metric_context_rows": [
                            {
                                **scope_row,
                                "source_closed_minute_bar_ids": [101],
                                "closed_minute_rows": [{"source_row_ref": "staging:row:101"}],
                                "previous_day_minute_refs": [201],
                                "metric_values": metric_values,
                            }
                        ],
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "runtime_execute": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                [
                    "--fastlane-lane-id",
                    "n5_action_confirmation_fastlane_v1",
                    "--active-scope-artifact-dir",
                    str(artifact_dir),
                    "--output-dir",
                    str(output_dir),
                    "--max-runtime-seconds",
                    "5",
                    "--execute",
                    "--user-confirmed",
                ],
                n3t_writer_adapter=n3t_writer_adapter,
            )

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_EXECUTE_PASS")
        self.assertTrue(manifest["writes_enabled"])
        self.assertEqual(manifest["execute_result"]["adapter_type"], "n3t_action_confirmation_metric_writer_adapter_v1")
        self.assertEqual(manifest["execute_result"]["inserted_rows"], 1)
        self.assertEqual(captured["input_count"], 1)
        self.assertEqual(captured["output_dir"], str(output_dir))
        adapter_input = captured["input"]
        self.assertEqual(adapter_input["n3t_metric_run_id"], "n3t_action_confirmation_metric_20260703_until_0943__fastlane_sr_abee3680ddd4_raw_prevday_c1_amount_v1")
        self.assertEqual(adapter_input["metric_plan_row_count"], 1)
        self.assertEqual(adapter_input["target_table_counts"], {"stock_n3t_action_confirmation_metric": 1})
        self.assertEqual(adapter_input["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(adapter_input["metric_role"], "action_confirmation")
        self.assertEqual(adapter_input["proof_consumer"], "N5")
        self.assertFalse(adapter_input["not_n5_final_proof"])
        self.assertTrue(captured["metric_context_path_exists"])
        self.assertIn("metric_context_artifact_sha256", adapter_input)

    def test_n3_runner_execute_uses_configured_n3t_writer_adapter(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        captured: dict[str, object] = {}

        def fake_writer(*, args, n3t_writer_inputs):
            captured["adapter"] = getattr(args, "n3t_writer_adapter", "")
            captured["input_count"] = len(n3t_writer_inputs)
            captured["input"] = n3t_writer_inputs[0]
            return {
                "adapter_type": "n3t_action_confirmation_metric_writer_adapter_v1",
                "write_executed": True,
                "source_basis": "N3T_C1_CLOSED",
                "metric_role": "action_confirmation",
                "proof_consumer": "N5",
                "not_n5_final_proof": False,
                "inserted_rows": 1,
                "target_table_counts": {"stock_n3t_action_confirmation_metric": 1},
                "writes_common_event_outbox": False,
                "writes_canonical_minute_bar_1m": False,
                "touches_n4_n5_n6_outbox": False,
                "full_market_fallback_used": False,
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            metric_dir = output_dir / "metric_context"
            staging_dir = output_dir / "current_day_staging"
            config_path = root / "activation_config.json"
            artifact_dir.mkdir()
            metric_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)
            (artifact_dir / "n5_active_scope_snapshot_v1_20260703_0943.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "scope_count": 1,
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (output_dir / "n3_c1_scoped_current_day_pull_plan_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_pull_plan_v1",
                        "plan_status": "planned",
                        "scope_count": 1,
                        "full_market_fallback_used": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (staging_dir / "n3_c1_scoped_current_day_staging_v1_20260703_0943_abee3680ddd4_fastlane.json").write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_current_day_staging_v1",
                        "artifact_status": "passed",
                        "scope_count": 1,
                        "closed_minute_row_count": 14,
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "writes_canonical_minute_bar_1m": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            scope_row = {
                "for_trade_date": "20260703",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:300803",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_MAIN",
                "source_trigger_event_id": "n4-match-300803",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0943__fastlane_v1",
                "scope_status": "active",
            }
            metric_values = {
                "current_price": 12,
                "previous_120m_body_high": 11,
                "previous_120m_body_low": 9,
                "previous_30m_body_high": 10.5,
                "previous_30m_body_low": 9.5,
                "previous_5m_body_high": 10.1,
                "previous_5m_body_low": 9.8,
                "previous_1m_body_high": 10,
                "previous_1m_body_low": 9.9,
                "current_1m_amount": 1000,
                "previous_1m_amount": 900,
                "current_5m_amount": 5000,
                "previous_5m_amount": 4500,
                "current_30m_closed_elapsed_amount": 30000,
                "previous_day_same_window_amount": 28000,
            }
            (
                metric_dir / "n3_c1_scoped_closed_1m_artifact_v1_20260703_0943_abee3680ddd4_fastlane_raw_prevday_c1_amount_v1.json"
            ).write_text(
                json.dumps(
                    {
                        "artifact_type": "n3_c1_scoped_closed_1m_artifact_v1",
                        "artifact_status": "planned",
                        "for_trade_date": "20260703",
                        "target_minute_label": "09:43",
                        "metric_context_status": "ready",
                        "scope_count": 1,
                        "scope_rows": [scope_row],
                        "metric_context_count": 1,
                        "metric_context_rows": [
                            {
                                **scope_row,
                                "source_closed_minute_bar_ids": [101],
                                "closed_minute_rows": [{"source_row_ref": "staging:row:101"}],
                                "previous_day_minute_refs": [201],
                                "metric_values": metric_values,
                            }
                        ],
                        "full_market_fallback_used": False,
                        "database_written": False,
                        "runtime_execute": False,
                        "writes_n3_outbox": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_n3t_fastlane_activation_config_v1",
                        "n5_active_scope_artifact_dir": str(artifact_dir),
                        "n3_c1_n3t_artifact_dir": str(output_dir),
                        "n3_c1_n3t_n3t_writer_adapter": "postgres_n3t_action_confirmation_metric_writer_v1",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "run_n3_c1_n3t_action_confirmation_fastlane_once._write_n3t_metrics_to_postgres",
                side_effect=fake_writer,
                create=True,
            ):
                manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                    ["--activation-config", str(config_path), "--execute", "--user-confirmed"]
                )

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_EXECUTE_PASS")
        self.assertTrue(manifest["writes_enabled"])
        self.assertEqual(captured["adapter"], "postgres_n3t_action_confirmation_metric_writer_v1")
        self.assertEqual(captured["input_count"], 1)
        self.assertEqual(manifest["execute_result"]["adapter_type"], "n3t_action_confirmation_metric_writer_adapter_v1")
        self.assertEqual(manifest["execute_result"]["inserted_rows"], 1)
        adapter_input = captured["input"]
        self.assertEqual(
            adapter_input["n3t_metric_run_id"],
            "n3t_action_confirmation_metric_20260703_until_0943__fastlane_sr_abee3680ddd4_raw_prevday_c1_amount_v1",
        )
        self.assertEqual(adapter_input["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(adapter_input["target_table_counts"], {"stock_n3t_action_confirmation_metric": 1})

    def test_source_run_scoped_bounded_drain_plan_filters_orders_and_builds_commands(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_source_run_scoped_bounded_drain_plan,
        )

        candidates = [
            {
                "source_run_id": "trigger_provisional_b2_hint_projection_20260703_until_0948__b2_v1",
                "event_time": "2026-07-03T09:48:00+08:00",
                "event_type": "TriggerMatched",
                "status": "pending",
                "row_count": 8,
            },
            {
                "source_run_id": "trigger_provisional_ordinary_20260703_until_0955__metric_v1",
                "event_time": "2026-07-03T09:55:00+08:00",
                "event_type": "TriggerMatched",
                "status": "pending",
                "row_count": 33,
            },
            {
                "source_run_id": "trigger_provisional_ordinary_20260703_until_0948__metric_v1",
                "event_time": "2026-07-03T09:48:00+08:00",
                "event_type": "TriggerMatched",
                "status": "pending",
                "row_count": 36,
            },
            {
                "source_run_id": "trigger_provisional_ordinary_20260703_until_0948__metric_v1",
                "event_time": "2026-07-03T09:48:01+08:00",
                "event_type": "TriggerStateChanged",
                "trigger_live": True,
                "status": "pending",
                "row_count": 2,
            },
            {
                "source_run_id": "trigger_provisional_ordinary_20260703_until_1001__metric_v1",
                "event_time": "2026-07-03T10:01:00+08:00",
                "event_type": "TriggerMatched",
                "status": "dead_letter",
                "row_count": 40,
            },
        ]

        plan = build_fastlane_source_run_scoped_bounded_drain_plan(
            for_trade_date="20260703",
            consumer_name="n5_live_tracking_poller_v2_fastlane",
            source_run_family="ordinary",
            start_after="20260703 09:43 closeout",
            first_source_run="trigger_provisional_ordinary_20260703_until_0948__metric_v1",
            max_source_runs=2,
            max_runtime_seconds=45,
            candidate_source_runs=candidates,
            working_directory=WORKING_DIRECTORY,
            n5_active_scope_artifact_dir="docs/runtime/20260703/n5_fastlane_active_scope",
            n3_c1_n3t_artifact_dir="docs/runtime/20260703/n3_c1_n3t_fastlane",
        )

        self.assertEqual(plan["result"], "PLAN_PASS")
        self.assertEqual(plan["artifact_type"], "n5_n3t_fastlane_source_run_scoped_bounded_drain_plan_v1")
        self.assertEqual(plan["selected_source_run_count"], 2)
        self.assertEqual(
            [item["target_hhmm"] for item in plan["selected_source_runs"]],
            ["0948", "0955"],
        )
        self.assertTrue(plan["ordinary_only"])
        self.assertFalse(plan["b2_hint_projection_included"])
        self.assertFalse(plan["updates_n4_outbox_status"])
        self.assertFalse(plan["touches_n6"])
        self.assertEqual(plan["closeout_registration_before_drain"]["execution"], "pre_drain_step")
        self.assertEqual(plan["closeout_registration_before_drain"]["status"], "required_before_selected_source_runs")
        pre_steps = plan["pre_drain_steps"]
        self.assertEqual(len(pre_steps), 1)
        closeout_step = pre_steps[0]
        self.assertEqual(closeout_step["step_type"], "n5_closeout_registration")
        self.assertEqual(closeout_step["step_id"], "n5_fastlane_0943_closeout_registration")
        self.assertEqual(closeout_step["must_run_before_selected_source_runs"], True)
        self.assertIn("n5_fastlane_0943_actionexecuted_closeout_registration.json", closeout_step["output_json_path"])
        self.assertIn("N5_FASTLANE_0943_ACTIONEXECUTED_CLOSEOUT_REGISTRATION.md", closeout_step["output_md_path"])
        self.assertIn("--closeout-prestep-only", closeout_step["command"])
        self.assertIn("--closeout-json-path", closeout_step["command"])
        self.assertIn(closeout_step["output_json_path"], closeout_step["command"])

        first = plan["selected_source_runs"][0]
        self.assertRegex(first["source_run_hash"], r"^[0-9a-f]{12}$")
        self.assertIn(first["source_run_hash"], first["n5_active_scope_artifact_path"])
        self.assertIn(
            f"fastlane_sr_{first['source_run_hash']}",
            first["n3t_metric_run_id"],
        )
        self.assertLessEqual(len(Path(first["n5_active_scope_artifact_path"]).name), 96)

        commands = first["commands"]
        self.assertIn("--fastlane-phase", commands["n5_intake"])
        self.assertIn("intake", commands["n5_intake"])
        self.assertIn("--write-active-scope-artifact", commands["n5_intake"])
        self.assertIn("--active-scope-artifact-path", commands["n3_c1_n3t"])
        self.assertIn(first["n5_active_scope_artifact_path"], commands["n3_c1_n3t"])
        self.assertIn("--fastlane-phase", commands["n5_executed"])
        self.assertIn("executed", commands["n5_executed"])
        self.assertIn(first["n3t_metric_run_id"], commands["n5_executed"])
        self.assertNotIn("--source-metric-run-id", commands["n5_intake"])
        self.assertNotIn("--source-trigger-run-id", commands["n3_c1_n3t"])
        self.assertEqual(first["phase_write_boundaries"]["n5_executed_writes_inbox_checkpoint"], False)
        self.assertEqual(first["phase_write_boundaries"]["n3_consumes_only_explicit_active_scope_artifact"], True)

        self.assertEqual(
            {item["source_run_id"]: item["reason"] for item in plan["excluded_source_runs"]},
            {
                "trigger_provisional_b2_hint_projection_20260703_until_0948__b2_v1": "source_run_family_not_ordinary",
                "trigger_provisional_ordinary_20260703_until_1001__metric_v1": "dead_letter_ignored",
            },
        )

    def test_source_run_scoped_bounded_drain_execute_runs_closeout_pre_step_first(self) -> None:
        from run_n5_n3t_fastlane_source_run_scoped_bounded_drain_once import _execute_drain_plan

        class Result:
            returncode = 0
            stdout = '{"result":"OK"}'
            stderr = ""

        calls: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> Result:
            calls.append(command)
            return Result()

        plan = {
            "max_runtime_seconds": 30,
            "pre_drain_steps": [
                {
                    "step_id": "n5_fastlane_0943_closeout_registration",
                    "step_type": "n5_closeout_registration",
                    "command": ["python3", "closeout"],
                }
            ],
            "selected_source_runs": [
                {
                    "source_run_id": "trigger_provisional_ordinary_20260703_until_0948__metric_v1",
                    "commands": {
                        "n5_intake": ["python3", "intake"],
                        "n3_c1_n3t": ["python3", "n3"],
                        "n5_executed": ["python3", "executed"],
                    },
                }
            ],
        }

        with patch("run_n5_n3t_fastlane_source_run_scoped_bounded_drain_once.subprocess.run", side_effect=fake_run):
            output = _execute_drain_plan(plan, working_directory=Path(WORKING_DIRECTORY))

        self.assertEqual(
            calls,
            [
                ["python3", "closeout"],
                ["python3", "intake"],
                ["python3", "n3"],
                ["python3", "executed"],
            ],
        )
        self.assertEqual(output["command_results"][0]["step_type"], "n5_closeout_registration")
        self.assertEqual(output["command_results"][0]["step_id"], "n5_fastlane_0943_closeout_registration")

    def test_source_run_scoped_bounded_drain_closeout_pre_step_writes_local_artifact_only(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_action_run_id,
            build_fastlane_ordinary_source_trigger_run_id,
        )
        from run_n5_n3t_fastlane_source_run_scoped_bounded_drain_once import main

        source_trigger_run_id = build_fastlane_ordinary_source_trigger_run_id(
            for_trade_date="20260703",
            target_hhmm="0943",
        )
        action_run_id = build_fastlane_action_run_id(
            for_trade_date="20260703",
            source_trigger_run_id=source_trigger_run_id,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "n5_fastlane_0943_actionexecuted_closeout_registration.json"
            md_path = Path(tmpdir) / "N5_FASTLANE_0943_ACTIONEXECUTED_CLOSEOUT_REGISTRATION.md"
            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--closeout-prestep-only",
                        "--for-trade-date",
                        "20260703",
                        "--consumer-name",
                        "n5_live_tracking_poller_v2_fastlane",
                        "--source-run-family",
                        "ordinary",
                        "--max-source-runs",
                        "1",
                        "--max-runtime-seconds",
                        "30",
                        "--source-trigger-run-id",
                        source_trigger_run_id,
                        "--action-run-id",
                        action_run_id,
                        "--source-metric-run-id",
                        "n3t_action_confirmation_metric_20260703_until_0943__fastlane_raw_prevday_c1_amount_v1",
                        "--closeout-json-path",
                        str(json_path),
                        "--closeout-md-path",
                        str(md_path),
                        "--execute",
                        "--user-confirmed",
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["artifact_type"], "n5_fastlane_0943_actionexecuted_closeout_registration_v1")
            self.assertEqual(payload["registration_mode"], "fastlane_bounded_drain_closeout_prestep")
            self.assertEqual(payload["must_complete_before_selected_source_runs"], True)
            self.assertEqual(payload["database_written_by_orchestrator"], False)
            self.assertEqual(payload["n4_outbox_updated"], False)
            self.assertEqual(payload["n6_touched"], False)

    def test_source_run_scoped_bounded_drain_plan_blocks_unbounded_inputs(self) -> None:
        from ashare_v3.runtime_control.n5_n3t_fastlane import (
            build_fastlane_source_run_scoped_bounded_drain_plan,
        )

        with self.assertRaisesRegex(ValueError, "max_source_runs_must_be_positive"):
            build_fastlane_source_run_scoped_bounded_drain_plan(
                for_trade_date="20260703",
                consumer_name="n5_live_tracking_poller_v2_fastlane",
                source_run_family="ordinary",
                max_source_runs=0,
                max_runtime_seconds=30,
                candidate_source_runs=[],
                working_directory=WORKING_DIRECTORY,
            )

        with self.assertRaisesRegex(ValueError, "source_run_family_must_be_ordinary"):
            build_fastlane_source_run_scoped_bounded_drain_plan(
                for_trade_date="20260703",
                consumer_name="n5_live_tracking_poller_v2_fastlane",
                source_run_family="b2_hint_projection",
                max_source_runs=1,
                max_runtime_seconds=30,
                candidate_source_runs=[],
                working_directory=WORKING_DIRECTORY,
            )

    def test_source_run_scoped_bounded_drain_cli_outputs_plan_only_json(self) -> None:
        from run_n5_n3t_fastlane_source_run_scoped_bounded_drain_once import main

        with tempfile.TemporaryDirectory() as tmpdir:
            source_runs_path = Path(tmpdir) / "source_runs.json"
            source_runs_path.write_text(
                json.dumps(
                    [
                        {
                            "source_run_id": "trigger_provisional_ordinary_20260703_until_0948__metric_v1",
                            "event_time": "2026-07-03T09:48:00+08:00",
                            "event_type": "TriggerMatched",
                            "status": "pending",
                            "row_count": 36,
                        },
                        {
                            "source_run_id": "trigger_provisional_b2_hint_projection_20260703_until_0948__b2_v1",
                            "event_time": "2026-07-03T09:48:00+08:00",
                            "event_type": "TriggerMatched",
                            "status": "pending",
                            "row_count": 8,
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--for-trade-date",
                        "20260703",
                        "--consumer-name",
                        "n5_live_tracking_poller_v2_fastlane",
                        "--source-run-family",
                        "ordinary",
                        "--first-source-run",
                        "trigger_provisional_ordinary_20260703_until_0948__metric_v1",
                        "--max-source-runs",
                        "1",
                        "--max-runtime-seconds",
                        "30",
                        "--plan-source-runs-json",
                        str(source_runs_path),
                        "--working-directory",
                        WORKING_DIRECTORY,
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["result"], "PLAN_PASS")
        self.assertEqual(payload["selected_source_run_count"], 1)
        self.assertEqual(payload["selected_source_runs"][0]["target_hhmm"], "0948")
        self.assertFalse(payload["b2_hint_projection_included"])
        self.assertFalse(payload["forbidden_operation_proof"]["database_written_by_plan"])

    def test_n3_runner_accepts_explicit_active_scope_artifact_path(self) -> None:
        from run_n3_c1_n3t_action_confirmation_fastlane_once import (
            run_n3_c1_n3t_action_confirmation_fastlane_once,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_dir = root / "scope"
            output_dir = root / "out"
            artifact_dir.mkdir()
            target_path = artifact_dir / "n5_active_scope_snapshot_v1_20260703_0948_abcd1234abcd.json"
            ignored_path = artifact_dir / "n5_active_scope_snapshot_v1_20260703_0955_deadbeef0000.json"
            target_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260703",
                        "scope_count": 1,
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0948__metric_v1",
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0948__metric_v1__fastlane_v1",
                        "source_run_hash": "abcd1234abcd",
                        "full_market_fallback_allowed": False,
                        "n3_scans_n5_internals": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            ignored_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": "20260703",
                        "scope_count": 1,
                        "source_trigger_run_id": "trigger_provisional_ordinary_20260703_until_0955__metric_v1",
                        "action_run_id": "n5_live_tracking_20260703__trigger_provisional_ordinary_20260703_until_0955__metric_v1__fastlane_v1",
                        "source_run_hash": "deadbeef0000",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(
                [
                    "--fastlane-lane-id",
                    "n5_action_confirmation_fastlane_v1",
                    "--active-scope-artifact-path",
                    str(target_path),
                    "--active-scope-artifact-dir",
                    str(artifact_dir),
                    "--output-dir",
                    str(output_dir),
                    "--max-runtime-seconds",
                    "5",
                ]
            )

        self.assertEqual(manifest["verdict"], "N3_C1_N3T_FASTLANE_SHELL_READY")
        self.assertEqual(manifest["active_scope_artifact_count"], 1)
        self.assertEqual(manifest["active_scope_artifacts"][0]["path"], str(target_path))


if __name__ == "__main__":
    unittest.main()
