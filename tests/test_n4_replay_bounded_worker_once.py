import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from ashare_v3.runtime.bounded_worker_control import SingletonLockHeld

import run_n4_replay_bounded_worker_once as n4_worker


class FakeChildResult:
    def __init__(self, result="PASS", returncode=0, timed_out=False):
        self.result = result
        self.returncode = returncode
        self.timed_out = timed_out
        self.elapsed_seconds = 0.01
        self.stdout_tail = ""
        self.stderr_tail = ""


@contextmanager
def null_lock(_path):
    yield


def conflicting_lock(_path):
    raise SingletonLockHeld(_path)


class N4ReplayBoundedWorkerOnceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.status_json = self.root / "status.json"
        self.manifest_json = self.root / "manifest.json"
        self.docs_root = self.root / "docs"
        self.sql_root = self.root / "sql"
        self.rollback_sql = self.sql_root / "rollback.sql"
        self.child_calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def base_argv(self, *extra):
        return [
            "--for-trade-date",
            "20260617",
            "--source-metric-run-id",
            "metric-001",
            "--projection-run-id",
            "metric-001",
            "--context-run-id",
            "ctx-001",
            "--source-condition-run-id",
            "cond-001",
            "--source-subscription-run-id",
            "sub-001",
            "--source-snapshot-run-id",
            "snap-001",
            "--trigger-run-id",
            "trig-001",
            "--dsn",
            "postgresql://unit-test",
            "--status-json",
            str(self.status_json),
            "--manifest-json",
            str(self.manifest_json),
            "--rollback-sql-path",
            str(self.rollback_sql),
            "--docs-root",
            str(self.docs_root),
            "--sql-root",
            str(self.sql_root),
            "--python-executable",
            "/usr/bin/python3",
            *extra,
        ]

    def candidate_estimator(self, _context):
        return {"candidate_total": 2, "source": "fake"}

    def complete_coverage_provider(self, _context):
        expected = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY_HINT",
            }
        ]
        return n4_worker.build_scope_coverage(_context, expected_keys=expected, actual_keys=expected)

    def passing_child(self, command, timeout_seconds):
        self.child_calls.append((command, timeout_seconds))
        report_path = Path(command[command.index("--execute-report-json-path") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "execute_run_id": "trig-001",
                    "trigger_run_id": "trig-001",
                    "write_counts": {
                        "TriggerMatched": 1,
                        "TriggerStateChanged": 2,
                        "TriggerPendingMarketData": 0,
                    },
                }
            ),
            encoding="utf-8",
        )
        self.rollback_sql.parent.mkdir(parents=True, exist_ok=True)
        self.rollback_sql.write_text("-- rollback\n", encoding="utf-8")
        return FakeChildResult()

    def prepare_child_artifacts(self, context):
        context.child_dry_run_json_path.parent.mkdir(parents=True, exist_ok=True)
        lineage_payload = {
            "trigger_context_run_id": context.lineage.context_run_id,
            "projection_run_id": context.lineage.projection_run_id,
            "source_condition_run_id": context.lineage.source_condition_run_id,
            "source_subscription_run_id": context.lineage.source_subscription_run_id,
            "source_snapshot_run_id": context.lineage.source_snapshot_run_id,
            "for_trade_date": context.lineage.for_trade_date,
        }
        context.child_dry_run_json_path.write_text(
            json.dumps({"result": "DRY_RUN_PASS", **lineage_payload}),
            encoding="utf-8",
        )
        context.child_dry_run_preflight_json_path.write_text(
            json.dumps({"result": "PREFLIGHT_PASS", **lineage_payload}),
            encoding="utf-8",
        )
        context.child_contract_json_path.write_text(
            json.dumps(
                {"result": "CONTRACT_PASS", "execute_run_id": context.lineage.trigger_run_id, **lineage_payload}
            ),
            encoding="utf-8",
        )
        context.child_final_preflight_json_path.write_text(
            json.dumps(
                {"result": "PREFLIGHT_PASS", "execute_run_id": context.lineage.trigger_run_id, **lineage_payload}
            ),
            encoding="utf-8",
        )
        return {"prepared": True}

    def run_worker(self, argv=None, **overrides):
        kwargs = {
            "argv": argv if argv is not None else self.base_argv(),
            "repo_root": self.root,
            "candidate_estimator": self.candidate_estimator,
            "coverage_provider": self.complete_coverage_provider,
            "command_runner": self.passing_child,
            "post_check_provider": lambda _context: {"state": "rolled_back"},
            "lock_acquirer": null_lock,
            "child_artifact_preparer": self.prepare_child_artifacts,
        }
        kwargs.update(overrides)
        return n4_worker.run_n4_replay_bounded_worker_once(**kwargs)

    def run_worker_with_default_provider(self, context_rows, metric_rows, argv=None, projection_rows=None, **overrides):
        kwargs = {
            "argv": argv if argv is not None else self.base_argv("--execute", "--user-confirmed"),
            "repo_root": self.root,
            "candidate_estimator": self.candidate_estimator,
            "command_runner": self.passing_child,
            "post_check_provider": lambda _context: {"state": "rolled_back"},
            "lock_acquirer": null_lock,
            "child_artifact_preparer": self.prepare_child_artifacts,
        }
        kwargs.update(overrides)
        with patch(
            "ashare_v3.trigger.projection_matcher.fetch_context_rows",
            return_value=(context_rows, {"run_id": "ctx-001", "status": "passed"}),
        ) as fetch_context, patch(
            "ashare_v3.trigger.action_confirmation_metric_matcher.fetch_action_confirmation_metric_rows",
            return_value=metric_rows,
        ) as fetch_metrics, patch(
            "ashare_v3.trigger.action_confirmation_metric_matcher.fetch_projection_enrichment_v4_quality_visible_rows",
            return_value=projection_rows or [],
        ):
            result = n4_worker.run_n4_replay_bounded_worker_once(**kwargs)
        return result, fetch_context.call_count, fetch_metrics.call_count

    def test_plan_only_does_not_invoke_replay_child(self):
        result = self.run_worker()

        self.assertEqual(result["result"], "NOOP")
        self.assertEqual(result["stop_reason"], "plan_only")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(self.child_calls, [])
        self.assertFalse(result["n5_consumption_allowed"])

    def test_plan_only_does_not_acquire_global_lock(self):
        def fail_if_called(_path):
            raise AssertionError("plan-only must not acquire global lock")

        result = self.run_worker(lock_acquirer=fail_if_called)

        self.assertEqual(result["result"], "NOOP")
        self.assertEqual(result["stop_reason"], "plan_only")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(self.child_calls, [])

    def test_execute_requires_user_confirmation(self):
        result = self.run_worker(argv=self.base_argv("--execute"))

        self.assertEqual(result["result"], "BLOCKED")
        self.assertFalse(result["child_invoked"])
        self.assertIn("user_confirmed", result["stop_reason"])

    def test_missing_explicit_lineage_blocks_before_child(self):
        argv = self.base_argv("--execute", "--user-confirmed")
        idx = argv.index("--context-run-id")
        del argv[idx : idx + 2]

        result = self.run_worker(argv=argv)

        self.assertEqual(result["result"], "BLOCKED")
        self.assertFalse(result["child_invoked"])
        self.assertIn("context_run_id", result["stop_reason"])

    def test_latest_active_fallback_auto_lineage_selectors_are_rejected(self):
        for implicit_value in ("latest", "active", "fallback", "auto", "auto-resolve"):
            with self.subTest(implicit_value=implicit_value):
                argv = self.base_argv("--execute", "--user-confirmed")
                argv[argv.index("--projection-run-id") + 1] = implicit_value

                result = self.run_worker(argv=argv)

                self.assertEqual(result["result"], "BLOCKED")
                self.assertFalse(result["child_invoked"])
                self.assertIn("implicit lineage selector", result["stop_reason"])

    def test_source_metric_run_id_must_equal_projection_run_id(self):
        argv = self.base_argv("--execute", "--user-confirmed")
        argv[argv.index("--projection-run-id") + 1] = "metric-002"

        result = self.run_worker(argv=argv)

        self.assertEqual(result["result"], "BLOCKED")
        self.assertFalse(result["child_invoked"])
        self.assertIn("source_metric_run_id", result["stop_reason"])

    def test_singleton_lock_conflict_is_noop(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            lock_acquirer=conflicting_lock,
        )

        self.assertEqual(result["result"], "NOOP")
        self.assertEqual(result["stop_reason"], "singleton_lock_held")
        self.assertFalse(result["child_invoked"])

    def test_stop_file_before_replay_is_noop(self):
        stop_file = self.root / "stop"
        stop_file.write_text("stop\n", encoding="utf-8")

        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed", "--stop-file", str(stop_file))
        )

        self.assertEqual(result["result"], "NOOP")
        self.assertEqual(result["stop_reason"], "stop_file_present")
        self.assertFalse(result["child_invoked"])

    def test_deadline_before_replay_blocks(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed", "--max-runtime-seconds", "0")
        )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "deadline_before_replay")
        self.assertFalse(result["child_invoked"])

    def test_candidate_total_over_max_blocks_without_child(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed", "--max-candidates", "1")
        )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "candidate_total_exceeds_max_candidates")
        self.assertEqual(result["candidate_total"], 2)
        self.assertFalse(result["child_invoked"])

    def test_scope_coverage_complete_passes_and_invokes_active_replay_path(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))

        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["child_invoked"])
        self.assertTrue(result["n5_consumption_allowed"])
        command = self.child_calls[0][0]
        self.assertIn("run_trigger_action_confirmation_metric_once.py", command[1])
        self.assertNotIn("run_n4_worker_bounded_poll_once.py", " ".join(command))
        self.assertEqual(result["active_path"], "run_trigger_action_confirmation_metric_once.py")

    def test_replay_child_argv_uses_explicit_tmp_artifact_paths(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))

        self.assertEqual(result["result"], "PASS")
        command = self.child_calls[0][0]
        joined = " ".join(command)
        expected_flags = {
            "--dry-run-json-path",
            "--dry-run-preflight-json-path",
            "--contract-json-path",
            "--contract-markdown-path",
            "--final-preflight-json-path",
            "--final-preflight-markdown-path",
            "--rollback-sql-path",
            "--execute-report-json-path",
            "--execute-report-markdown-path",
        }
        self.assertTrue(expected_flags.issubset(set(command)))
        for flag in expected_flags:
            path = Path(command[command.index(flag) + 1])
            if flag == "--rollback-sql-path":
                self.assertEqual(path, self.rollback_sql)
            else:
                self.assertTrue(path.is_relative_to(self.docs_root), f"{flag}={path}")
        self.assertNotIn("docs/N4_action_confirmation_metric_business_execute_contract.json", joined)
        self.assertNotIn("docs/N4_action_confirmation_metric_business_execute_final_preflight.json", joined)
        self.assertEqual(
            result["child_artifacts"]["contract_json_path"],
            str(self.docs_root / "N4_REPLAY_BOUNDED_WORKER_trig-001_child_execute_contract.json"),
        )

    def test_child_artifact_lineage_mismatch_blocks_before_child(self):
        args = n4_worker.build_arg_parser().parse_args(self.base_argv("--execute", "--user-confirmed"))
        lineage = n4_worker.build_explicit_lineage(args)
        context = n4_worker.build_n4_bounded_context(lineage, args, repo_root=self.root)
        context.child_dry_run_json_path.parent.mkdir(parents=True, exist_ok=True)
        context.child_dry_run_json_path.write_text(
            json.dumps(
                {
                    "result": "DRY_RUN_PASS",
                    "trigger_context_run_id": "ctx-001",
                    "projection_run_id": "stale-metric",
                    "source_condition_run_id": "cond-001",
                    "source_subscription_run_id": "sub-001",
                    "source_snapshot_run_id": "snap-001",
                    "for_trade_date": "20260617",
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(n4_worker.N4ReplayBlocked, "child_artifact_lineage_mismatch"):
            n4_worker.validate_child_artifact_lineage(context)

    def test_default_production_provider_wired_without_injected_coverage_provider(self):
        context_rows = [
            {
                "run_id": "ctx-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY_HINT",
                "allowed_signal_types": ["BUY_HINT"],
            }
        ]
        metric_rows = [
            {
                "projection_run_id": "metric-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "condition_key": "BUY_HINT",
                "signal_type": "BUY_HINT",
                "raw_json": {},
                "trace_json": {},
            }
        ]

        result, fetch_context_count, fetch_metric_count = self.run_worker_with_default_provider(
            context_rows, metric_rows
        )

        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["child_invoked"])
        self.assertEqual(result["scope_coverage"]["provider"], "n4_context_vs_n3_action_confirmation_metric_db")
        self.assertTrue(result["scope_coverage"]["production_provider_wired"])
        self.assertTrue(result["production_scope_coverage_provider_wired"])
        self.assertEqual(fetch_context_count, 1)
        self.assertEqual(fetch_metric_count, 1)

    def test_default_provider_complete_expected_actual_scope_allows_child_invocation(self):
        context_rows = [
            {
                "run_id": "ctx-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY",
                "allowed_signal_types": ["B_BUY"],
            },
            {
                "run_id": "ctx-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600001",
                "direction": "sell",
                "condition_key": "SELL:FULL",
                "allowed_signal_types": ["S_SELL"],
            },
        ]
        metric_rows = [
            {
                "projection_run_id": "metric-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "raw_json": {},
                "trace_json": {},
            },
            {
                "projection_run_id": "metric-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600001",
                "raw_json": {},
                "trace_json": {},
            },
        ]

        result, _fetch_context_count, _fetch_metric_count = self.run_worker_with_default_provider(
            context_rows, metric_rows
        )

        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["child_invoked"])
        self.assertEqual(result["scope_coverage"]["expected_count"], 2)
        self.assertEqual(result["scope_coverage"]["actual_count"], 2)
        self.assertEqual(result["scope_coverage"]["missing_count"], 0)

    def test_scope_coverage_blocks_ordinary_expected_with_hint_only_actual(self):
        expected = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY",
            }
        ]
        actual = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY_HINT",
            }
        ]

        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            coverage_provider=lambda context: n4_worker.build_scope_coverage(
                context, expected_keys=expected, actual_keys=actual
            ),
        )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("scope_coverage_incomplete", result["stop_reason"])
        self.assertFalse(result["child_invoked"])
        self.assertEqual(result["scope_coverage"]["missing_by_condition_key"]["BUY"]["count"], 1)

    def test_default_provider_blocks_ordinary_expected_with_hint_only_actual(self):
        context_rows = [
            {
                "run_id": "ctx-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY",
                "allowed_signal_types": ["B_BUY"],
            }
        ]
        metric_rows = [
            {
                "projection_run_id": "metric-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "condition_key": "BUY_HINT",
                "signal_type": "BUY_HINT",
                "raw_json": {},
                "trace_json": {},
            }
        ]

        result, _fetch_context_count, _fetch_metric_count = self.run_worker_with_default_provider(
            context_rows, metric_rows
        )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertIn("scope_coverage_incomplete", result["stop_reason"])
        self.assertFalse(result["child_invoked"])
        self.assertEqual(result["scope_coverage"]["missing_by_condition_key"]["BUY"]["count"], 1)

    def test_missing_metric_keys_are_grouped_by_condition_key(self):
        expected = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY",
            },
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600001",
                "direction": "sell",
                "condition_key": "SELL:FULL",
            },
        ]
        coverage = n4_worker.build_scope_coverage(None, expected_keys=expected, actual_keys=[])

        self.assertFalse(coverage["coverage_complete"])
        self.assertEqual(coverage["missing_by_condition_key"]["BUY"]["count"], 1)
        self.assertEqual(coverage["missing_by_condition_key"]["SELL:FULL"]["count"], 1)
        self.assertEqual(coverage["missing_count"], 2)

    def test_default_provider_missing_metric_keys_are_grouped_by_condition_key(self):
        context_rows = [
            {
                "run_id": "ctx-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY",
                "allowed_signal_types": ["B_BUY"],
            },
            {
                "run_id": "ctx-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600001",
                "direction": "sell",
                "condition_key": "SELL:FULL",
                "allowed_signal_types": ["S_SELL"],
            },
        ]

        result, _fetch_context_count, _fetch_metric_count = self.run_worker_with_default_provider(
            context_rows, []
        )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertFalse(result["scope_coverage"]["coverage_complete"])
        self.assertEqual(result["scope_coverage"]["missing_by_condition_key"]["BUY"]["count"], 1)
        self.assertEqual(result["scope_coverage"]["missing_by_condition_key"]["SELL:FULL"]["count"], 1)
        self.assertEqual(result["scope_coverage"]["missing_count"], 2)

    def test_no_silent_bj_whitelist_without_quality_visible_proof(self):
        expected = [
            {
                "asset_kind": "index",
                "identity_key": "index:BJ:899050",
                "direction": "buy",
                "condition_key": "BUY:M,W",
            }
        ]

        coverage = n4_worker.build_scope_coverage(None, expected_keys=expected, actual_keys=[])

        self.assertFalse(coverage["coverage_complete"])
        self.assertEqual(coverage["missing_count"], 1)
        self.assertEqual(coverage.get("legal_quality_visible_exclusion_count"), 0)

    def test_missing_quality_visible_proof_still_blocks_remaining_rows(self):
        expected = [
            {
                "asset_kind": "index",
                "identity_key": "index:BJ:899050",
                "direction": "buy",
                "condition_key": "BUY:M,W",
            },
            {
                "asset_kind": "index",
                "identity_key": "index:BJ:899601",
                "direction": "sell",
                "condition_key": "SELL:M,W,D",
            },
        ]
        legal_exclusions = [expected[0]]

        coverage = n4_worker.build_scope_coverage(
            None,
            expected_keys=expected,
            actual_keys=[],
            legal_exclusion_keys=legal_exclusions,
        )

        self.assertFalse(coverage["coverage_complete"])
        self.assertEqual(coverage["legal_quality_visible_exclusion_count"], 1)
        self.assertEqual(coverage["missing_count"], 1)
        self.assertEqual(coverage["missing_by_condition_key"]["SELL:M,W,D"]["count"], 1)

    def test_legal_quality_visible_proof_passes_daily_only_gap(self):
        context_rows = [
            {
                "run_id": "ctx-001",
                "trigger_context_id": 4573,
                "asset_kind": "index",
                "identity_key": "index:BJ:899050",
                "direction": "buy",
                "condition_key": "BUY:M,W",
                "allowed_signal_types": ["B_BUY"],
            }
        ]
        projection_rows = [
            {
                "projection_run_id": "metric-001",
                "source_trigger_context_run_id": "ctx-001",
                "source_trigger_context_id": 4573,
                "asset_kind": "index",
                "identity_key": "index:BJ:899050",
                "direction": "buy",
                "condition_key": "BUY:M,W",
                "quality_visible": True,
                "metric_ready": False,
                "metric_quality_status": "missing",
                "source_freshness_status": "source_minute_missing_quality_visible",
                "quality_reason": "BJ daily-only source has no minute lineage",
            }
        ]

        result, _fetch_context_count, _fetch_metric_count = self.run_worker_with_default_provider(
            context_rows,
            [],
            projection_rows=projection_rows,
        )

        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["child_invoked"])
        self.assertEqual(result["scope_coverage"]["missing_count"], 0)
        self.assertEqual(result["scope_coverage"]["legal_quality_visible_exclusion_count"], 1)

    def test_malformed_quality_visible_proof_still_blocks(self):
        context_rows = [
            {
                "run_id": "ctx-001",
                "trigger_context_id": 4573,
                "asset_kind": "index",
                "identity_key": "index:BJ:899050",
                "direction": "buy",
                "condition_key": "BUY:M,W",
                "allowed_signal_types": ["B_BUY"],
            }
        ]
        projection_rows = [
            {
                "projection_run_id": "metric-001",
                "source_trigger_context_run_id": "ctx-001",
                "source_trigger_context_id": 4573,
                "asset_kind": "index",
                "identity_key": "index:BJ:899050",
                "direction": "buy",
                "condition_key": "BUY:M,W",
                "quality_visible": False,
                "metric_ready": False,
                "metric_quality_status": "missing",
                "source_freshness_status": "source_minute_missing_quality_visible",
            }
        ]

        result, _fetch_context_count, _fetch_metric_count = self.run_worker_with_default_provider(
            context_rows,
            [],
            projection_rows=projection_rows,
        )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(result["scope_coverage"]["missing_count"], 1)
        self.assertEqual(result["scope_coverage"]["legal_quality_visible_exclusion_count"], 0)

    def test_non_bj_missing_metric_still_blocked_by_default_provider(self):
        context_rows = [
            {
                "run_id": "ctx-001",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "condition_key": "BUY",
                "allowed_signal_types": ["B_BUY"],
            }
        ]

        result, _fetch_context_count, _fetch_metric_count = self.run_worker_with_default_provider(
            context_rows,
            [],
            projection_rows=[],
        )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(result["scope_coverage"]["missing_count"], 1)
        self.assertEqual(result["scope_coverage"]["legal_quality_visible_exclusion_count"], 0)

    def test_default_provider_failure_fails_closed_before_child(self):
        with patch(
            "ashare_v3.trigger.projection_matcher.fetch_context_rows",
            side_effect=RuntimeError("db unavailable"),
        ):
            result = self.run_worker(
                argv=self.base_argv("--execute", "--user-confirmed"),
                coverage_provider=None,
            )

        self.assertEqual(result["result"], "BLOCKED")
        self.assertFalse(result["child_invoked"])
        self.assertFalse(result["scope_coverage"]["coverage_complete"])
        self.assertIn("scope_coverage_provider_failed", result["stop_reason"])

    def test_plan_only_does_not_query_default_db_provider(self):
        with patch(
            "ashare_v3.trigger.projection_matcher.fetch_context_rows",
            side_effect=AssertionError("context provider should not be queried"),
        ) as fetch_context, patch(
            "ashare_v3.trigger.action_confirmation_metric_matcher.fetch_action_confirmation_metric_rows",
            side_effect=AssertionError("metric provider should not be queried"),
        ) as fetch_metrics:
            result = self.run_worker(
                argv=self.base_argv(),
                coverage_provider=None,
            )

        self.assertEqual(result["result"], "NOOP")
        self.assertEqual(result["stop_reason"], "plan_only")
        self.assertFalse(result["child_invoked"])
        self.assertEqual(fetch_context.call_count, 0)
        self.assertEqual(fetch_metrics.call_count, 0)

    def test_child_timeout_becomes_unknown_after_timeout(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=lambda _cmd, _timeout: FakeChildResult(
                result="UNKNOWN_AFTER_TIMEOUT", returncode=None, timed_out=True
            ),
        )

        self.assertEqual(result["result"], "UNKNOWN_AFTER_TIMEOUT")
        self.assertTrue(result["requires_post_check"])
        self.assertEqual(result["exit_code"], 3)

    def test_child_exit_one_with_rolled_back_post_check_crashes(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=lambda _cmd, _timeout: FakeChildResult(result="CRASHED", returncode=1),
            post_check_provider=lambda _context: {"state": "rolled_back"},
        )

        self.assertEqual(result["result"], "CRASHED")
        self.assertEqual(result["post_check"]["state"], "rolled_back")
        self.assertEqual(result["exit_code"], 1)

    def test_unresolved_post_check_becomes_commit_unknown(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=lambda _cmd, _timeout: FakeChildResult(result="CRASHED", returncode=1),
            post_check_provider=lambda _context: {"state": "unresolved"},
        )

        self.assertEqual(result["result"], "COMMIT_UNKNOWN")
        self.assertTrue(result["requires_post_check"])
        self.assertEqual(result["exit_code"], 3)

    def test_missing_report_after_child_success_becomes_commit_unknown(self):
        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=lambda _cmd, _timeout: FakeChildResult(returncode=0),
            post_check_provider=lambda _context: {"state": "unresolved"},
        )

        self.assertEqual(result["result"], "COMMIT_UNKNOWN")
        self.assertIn("child_report_missing", result["stop_reason"])

    def test_invalid_report_json_fails_closed(self):
        def invalid_report_child(command, _timeout):
            report_path = Path(command[command.index("--execute-report-json-path") + 1])
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("{not-json", encoding="utf-8")
            return FakeChildResult(returncode=0)

        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=invalid_report_child,
            post_check_provider=lambda _context: {"state": "rolled_back"},
        )

        self.assertEqual(result["result"], "CRASHED")
        self.assertIn("child_report_invalid_json", result["stop_reason"])

    def test_report_trigger_run_id_mismatch_becomes_commit_unknown(self):
        def mismatched_report_child(command, _timeout):
            report_path = Path(command[command.index("--execute-report-json-path") + 1])
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({"execute_run_id": "other"}), encoding="utf-8")
            self.rollback_sql.parent.mkdir(parents=True, exist_ok=True)
            self.rollback_sql.write_text("-- rollback\n", encoding="utf-8")
            return FakeChildResult(returncode=0)

        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=mismatched_report_child,
            post_check_provider=lambda _context: {"state": "unresolved"},
        )

        self.assertEqual(result["result"], "COMMIT_UNKNOWN")
        self.assertIn("child_report_trigger_run_id_mismatch", result["stop_reason"])

    def test_rollback_sql_missing_after_child_started_crashes(self):
        def report_without_rollback_child(command, _timeout):
            report_path = Path(command[command.index("--execute-report-json-path") + 1])
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({"execute_run_id": "trig-001"}), encoding="utf-8")
            return FakeChildResult(returncode=0)

        result = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed"),
            command_runner=report_without_rollback_child,
            post_check_provider=lambda _context: {"state": "rolled_back"},
        )

        self.assertEqual(result["result"], "CRASHED")
        self.assertIn("rollback_sql_missing", result["stop_reason"])

    def test_event_counts_are_recorded(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))

        self.assertEqual(result["trigger_event_counts"]["TriggerMatched"], 1)
        self.assertEqual(result["trigger_event_counts"]["TriggerStateChanged"], 2)
        self.assertEqual(result["trigger_event_counts"]["TriggerPendingMarketData"], 0)

    def test_downstream_consumption_allowed_only_for_pass(self):
        passed = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))
        blocked = self.run_worker(
            argv=self.base_argv("--execute", "--user-confirmed", "--max-candidates", "1")
        )

        self.assertTrue(passed["downstream_consumption_allowed"])
        self.assertTrue(passed["n5_consumption_allowed"])
        self.assertFalse(blocked["downstream_consumption_allowed"])
        self.assertFalse(blocked["n5_consumption_allowed"])

    def test_global_lock_path_is_shared_phase1_chain_path(self):
        args = n4_worker.build_arg_parser().parse_args(self.base_argv())
        lineage = n4_worker.build_explicit_lineage(args)
        context = n4_worker.build_n4_bounded_context(lineage, args, repo_root=self.root)

        lock_path = str(context.lock_path)
        self.assertIn("v3_phase1_realtime_chain_20260617.lock", lock_path)
        self.assertNotIn("/n3", lock_path.lower())
        self.assertNotIn("/n4", lock_path.lower())
        self.assertNotIn("/n5", lock_path.lower())

    def test_contract_doc_marks_old_smoke_consumer_deferred(self):
        doc = Path("docs/V3_PHASE1_N4_REPLAY_BOUNDED_WORKER_CONTRACT.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("run_trigger_action_confirmation_metric_once.py", doc)
        self.assertIn("run_n4_worker_bounded_poll_once.py", doc)
        self.assertIn("deferred", doc.lower())
        self.assertIn("no SQL migration", doc)
        self.assertIn("legacy", doc.lower())
        self.assertIn("bypass", doc.lower())
        self.assertIn("global lock", doc.lower())
        self.assertIn("manual SQL", doc)
        self.assertIn("must not run in parallel", doc)

    def test_no_n5_n6_action_trade_sim_voice_mobile_side_effects(self):
        result = self.run_worker(argv=self.base_argv("--execute", "--user-confirmed"))

        side_effects = result["side_effects"]
        self.assertFalse(side_effects["n5"])
        self.assertFalse(side_effects["n6"])
        self.assertFalse(side_effects["action"])
        self.assertFalse(side_effects["trade"])
        self.assertFalse(side_effects["sim"])
        self.assertFalse(side_effects["voice"])
        self.assertFalse(side_effects["mobile"])


if __name__ == "__main__":
    unittest.main()
