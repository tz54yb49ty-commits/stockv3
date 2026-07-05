import inspect
import json
import os
import tempfile
import unittest
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from unittest.mock import patch

import ashare_v3.trigger.worker_consumer as worker_consumer
import run_n4_worker_bounded_smoke_once as smoke_runner
from ashare_v3.trigger.worker_consumer import (
    ALLOWED_SMOKE_WRITE_TABLES,
    N4WorkerSmokeBlocked,
    apply_idempotency_scenario,
    assert_bounded_smoke_confirmed,
    assert_smoke_baseline_clean,
    build_smoke_write_plan,
    build_bounded_controls,
    fetch_existing_consume_keys,
    fetch_source_events_for_smoke,
    load_semantic_fixture,
    make_json_safe,
    build_worker_rollback_sql,
    build_worker_smoke_plan,
    load_idempotency_scenario,
    require_semantic_inputs,
    semantic_source_event_ids,
    validate_source_events_for_execute,
    write_status_json,
)
from ashare_v3.trigger.worker_state_transition import source_event_consume_key


def source_event(event_id="evt_source_1", outbox_id=1, identity_key="stock:SZ:000001"):
    return {
        "outbox_id": outbox_id,
        "event_id": event_id,
        "event_type": "MarketSnapshotUpdated",
        "source_layer": "N3_market_data",
        "source_run_id": "snapshot_run",
        "event_schema_version": "v1",
        "trade_date": "20260608",
        "asset_kind": "stock",
        "identity_key": identity_key,
        "partition_key": identity_key,
        "event_time": "2026-06-08T09:45:00+08:00",
        "payload_json": {"snapshot_id": "snapshot_1"},
        "status": "pending",
    }


def matched_eval(event_id="evt_source_1", identity_key="stock:SZ:000001"):
    return {
        "source_event_id": event_id,
        "trade_date": "20260608",
        "asset_kind": "stock",
        "identity_key": identity_key,
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY:D",
        "current_status": "matched",
        "trigger_live": True,
        "primary_trigger_period": "D",
        "all_trigger_periods": ["D"],
        "output_event_type": "TriggerMatched",
        "trigger_price": 10.5,
        "trigger_kind": "trigger",
        "n5_entry_allowed": True,
        "match_basis": "worker_smoke_fixture",
        "source_market_event_or_projection_id": event_id,
        "trigger_mark_candidate": "normal",
        "new_trigger_fact": True,
    }


class _Description:
    def __init__(self, name):
        self.name = name


class _RecordingCursor:
    def __init__(self, rows=None, description_names=None):
        self.rows = rows or []
        self.description = [_Description(name) for name in (description_names or [])]
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return list(self.rows)


class _RecordingConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def cursor(self):
        return self.cursor_obj


class N4WorkerBoundedSmokeTests(unittest.TestCase):
    def test_cli_guard_blocks_missing_execute_or_user_confirmed_before_db_write(self):
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "missing --execute"):
            assert_bounded_smoke_confirmed(execute=False, user_confirmed=True)
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "missing --user-confirmed"):
            assert_bounded_smoke_confirmed(execute=True, user_confirmed=False)

    def test_cli_exposes_bounded_smoke_controls(self):
        parser = smoke_runner.build_arg_parser()
        args = parser.parse_args(
            [
                "--contract-path",
                "docs/N4_WORKER_CONTINUOUS_STATE_TRANSITION_CONTRACT.json",
                "--smoke-run-id",
                "n4_worker_bounded_smoke_test",
                "--consumer-name",
                "n4_trigger_worker_v1",
                "--source-run-id",
                "snapshot_run",
                "--source-event-type",
                "MarketSnapshotUpdated",
                "--source-trade-date",
                "20260608",
                "--max-events",
                "10",
                "--max-runtime-seconds",
                "60",
                "--heartbeat-interval-seconds",
                "5",
                "--stop-file",
                "tmp/n4.stop",
                "--status-json",
                "docs/status.json",
                "--json-report-path",
                "docs/report.json",
                "--markdown-report-path",
                "docs/report.md",
                "--semantic-smoke",
                "--semantic-fixture-path",
                "fixtures/semantic.json",
                "--idempotency-scenario-path",
                "fixtures/idempotency.json",
                "--execute",
                "--user-confirmed",
            ]
        )

        self.assertTrue(args.execute)
        self.assertTrue(args.user_confirmed)
        self.assertEqual(args.smoke_run_id, "n4_worker_bounded_smoke_test")
        self.assertEqual(args.source_run_id, "snapshot_run")
        self.assertEqual(args.source_event_type, "MarketSnapshotUpdated")
        self.assertEqual(args.source_trade_date, "20260608")
        self.assertEqual(args.max_events, 10)
        self.assertEqual(args.max_runtime_seconds, 60)
        self.assertEqual(args.heartbeat_interval_seconds, 5)
        self.assertTrue(args.semantic_smoke)
        self.assertEqual(args.semantic_fixture_path, "fixtures/semantic.json")
        self.assertEqual(args.idempotency_scenario_path, "fixtures/idempotency.json")

    def test_idempotency_scenario_path_without_execute_blocks_before_db_connect(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(smoke_runner.psycopg, "connect") as connect:
            scenario_path = Path(tmpdir) / "scenario.json"
            scenario_path.write_text(json.dumps({"duplicate_source_event_ids": ["evt_source_1"]}), encoding="utf-8")
            rc = smoke_runner.main(
                [
                    "--user-confirmed",
                    "--smoke-run-id",
                    "n4_worker_bounded_smoke_idempotency_test",
                    "--source-run-id",
                    "snapshot_run",
                    "--source-trade-date",
                    "20260608",
                    "--idempotency-scenario-path",
                    str(scenario_path),
                    "--json-report-path",
                    str(Path(tmpdir) / "report.json"),
                    "--markdown-report-path",
                    str(Path(tmpdir) / "report.md"),
                    "--rollback-sql-path",
                    str(Path(tmpdir) / "rollback.sql"),
                ]
            )

        self.assertEqual(rc, 2)
        connect.assert_not_called()

    def test_invalid_idempotency_scenario_json_blocks_before_db_connect(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(smoke_runner.psycopg, "connect") as connect:
            scenario_path = Path(tmpdir) / "scenario.json"
            scenario_path.write_text("{not-json", encoding="utf-8")
            rc = smoke_runner.main(
                [
                    "--execute",
                    "--user-confirmed",
                    "--smoke-run-id",
                    "n4_worker_bounded_smoke_idempotency_test",
                    "--source-run-id",
                    "snapshot_run",
                    "--source-trade-date",
                    "20260608",
                    "--idempotency-scenario-path",
                    str(scenario_path),
                    "--json-report-path",
                    str(Path(tmpdir) / "report.json"),
                    "--markdown-report-path",
                    str(Path(tmpdir) / "report.md"),
                    "--rollback-sql-path",
                    str(Path(tmpdir) / "rollback.sql"),
                ]
            )

        self.assertEqual(rc, 2)
        connect.assert_not_called()

    def test_idempotency_scenario_loads_runtime_control_helper_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scenario_path = Path(tmpdir) / "scenario.json"
            scenario_path.write_text(
                json.dumps(
                    {
                        "selected_source_events": {
                            "event_ids": ["evt_source_1", "evt_source_2"],
                        },
                        "scenario_cases": {
                            "duplicate_source_event_helper_model": {
                                "modeled_source_event_rows": 3,
                                "modeled_existing_consume_keys": [
                                    "n4_trigger_worker_v1|evt_source_2",
                                ],
                                "skipped_duplicate_event_ids": ["evt_source_1", "evt_source_2"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            scenario = load_idempotency_scenario(str(scenario_path), consumer_name="n4_trigger_worker_v1")

        self.assertEqual(scenario["duplicate_source_event_counts"], {"evt_source_1": 1})
        self.assertEqual(scenario["existing_consume_keys"], ["n4_trigger_worker_v1|evt_source_2"])

    def test_idempotency_scenario_duplicate_row_injection_skips_duplicate(self):
        scenario = {
            "scenario_enabled": True,
            "duplicate_source_event_counts": {"evt_source_1": 1},
            "existing_consume_keys": [],
            "failure_injection": {"enabled": False, "point": None},
        }
        source_events, existing_keys, scenario_summary = apply_idempotency_scenario(
            [source_event(event_id="evt_source_1", outbox_id=1)],
            existing_consume_keys=set(),
            scenario=scenario,
        )
        report = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=source_events,
            evaluations=[],
            previous_states={},
            existing_consume_keys=existing_keys,
            max_events=10,
        )

        self.assertEqual(scenario_summary["injected_duplicate_source_event_count"], 1)
        self.assertEqual(report["summary"]["accepted_source_event_count"], 1)
        self.assertEqual(report["summary"]["skipped_duplicate_source_event_count"], 1)

    def test_idempotency_scenario_existing_consume_key_skips_event(self):
        scenario = {
            "scenario_enabled": True,
            "duplicate_source_event_counts": {},
            "existing_consume_keys": ["n4_trigger_worker_v1|evt_source_1"],
            "failure_injection": {"enabled": False, "point": None},
        }
        source_events, existing_keys, scenario_summary = apply_idempotency_scenario(
            [source_event(event_id="evt_source_1", outbox_id=1)],
            existing_consume_keys=set(),
            scenario=scenario,
        )
        report = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=source_events,
            evaluations=[],
            previous_states={},
            existing_consume_keys=existing_keys,
            max_events=10,
        )

        self.assertEqual(scenario_summary["injected_existing_consume_key_count"], 1)
        self.assertEqual(report["summary"]["accepted_source_event_count"], 0)
        self.assertEqual(report["summary"]["skipped_duplicate_source_event_count"], 1)

    def test_idempotency_scenario_keeps_max_events_bounded(self):
        scenario = {
            "scenario_enabled": True,
            "duplicate_source_event_counts": {"evt_source_1": 5},
            "existing_consume_keys": [],
            "failure_injection": {"enabled": False, "point": None},
        }
        source_events, existing_keys, _scenario_summary = apply_idempotency_scenario(
            [source_event(event_id="evt_source_1", outbox_id=1)],
            existing_consume_keys=set(),
            scenario=scenario,
        )
        report = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=source_events,
            evaluations=[],
            previous_states={},
            existing_consume_keys=existing_keys,
            max_events=1,
        )

        self.assertLessEqual(report["summary"]["accepted_source_event_count"], 1)
        self.assertEqual(len(report["skipped_source_events"]), 5)

    def test_source_selection_excludes_events_already_in_consumer_inbox_or_checkpoint(self):
        cursor = _RecordingCursor(
            rows=[],
            description_names=[
                "outbox_id",
                "event_id",
                "event_type",
                "event_schema_version",
                "trade_date",
                "asset_kind",
                "identity_key",
                "event_time",
                "source_layer",
                "source_run_id",
                "dedup_key",
                "partition_key",
                "payload_json",
                "status",
                "created_at",
            ],
        )
        conn = _RecordingConnection(cursor)

        rows = fetch_source_events_for_smoke(
            conn,
            source_run_id="snapshot_run",
            source_event_type="MarketSnapshotUpdated",
            source_trade_date="20260611",
            max_events=50,
            consumer_name="n4_trigger_worker_v1_bounded_polling_20260611",
        )

        self.assertEqual(rows, [])
        self.assertIn("NOT EXISTS", cursor.sql)
        self.assertIn("common_event_inbox", cursor.sql)
        self.assertIn("common_event_consumer_checkpoint", cursor.sql)
        self.assertIn("last_event_id", cursor.sql)
        self.assertIn("source_event_consume_key", cursor.sql)
        self.assertNotIn("UPDATE common_event_outbox", cursor.sql)
        self.assertIn("n4_trigger_worker_v1_bounded_polling_20260611", cursor.params)

    def test_existing_consume_keys_use_consumer_event_keys_from_inbox_and_checkpoint(self):
        cursor = _RecordingCursor(
            rows=[
                (source_event_consume_key("n4_trigger_worker_v1", "evt_inbox"),),
                (source_event_consume_key("n4_trigger_worker_v1", "evt_checkpoint_payload"),),
                (source_event_consume_key("n4_trigger_worker_v1", "evt_checkpoint_last"),),
            ],
            description_names=["consume_key"],
        )
        conn = _RecordingConnection(cursor)

        keys = fetch_existing_consume_keys(
            conn,
            consumer_name="n4_trigger_worker_v1",
            source_run_id="snapshot_run",
            source_event_type="MarketSnapshotUpdated",
        )

        self.assertEqual(
            keys,
            {
                source_event_consume_key("n4_trigger_worker_v1", "evt_inbox"),
                source_event_consume_key("n4_trigger_worker_v1", "evt_checkpoint_payload"),
                source_event_consume_key("n4_trigger_worker_v1", "evt_checkpoint_last"),
            },
        )
        self.assertIn("raw_json ->> 'source_event_consume_key'", cursor.sql)
        self.assertIn("checkpoint_payload ->> 'source_event_consume_key'", cursor.sql)
        self.assertIn("last_event_id", cursor.sql)
        self.assertNotIn("UPDATE common_event_outbox", cursor.sql)

    def test_idempotency_failure_injection_before_write_leaves_no_persist_call(self):
        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        args = smoke_runner.build_arg_parser().parse_args(
            [
                "--execute",
                "--user-confirmed",
                "--smoke-run-id",
                "n4_worker_bounded_smoke_idempotency_test",
                "--consumer-name",
                "n4_trigger_worker_v1",
                "--source-run-id",
                "snapshot_run",
                "--source-trade-date",
                "20260608",
                "--max-events",
                "10",
            ]
        )
        scenario = {
            "scenario_enabled": True,
            "duplicate_source_event_counts": {"evt_source_1": 1},
            "existing_consume_keys": [],
            "failure_injection": {"enabled": True, "point": "before_write", "reason": "test_before_write"},
        }
        with (
            patch.object(smoke_runner.psycopg, "connect", return_value=FakeConnection()),
            patch.object(
                smoke_runner,
                "fetch_smoke_baseline_counts",
                return_value={
                    "common_trigger_run": 0,
                    "common_trigger_quality_item": 0,
                    "common_trigger_state": 0,
                    "common_trigger_match": 0,
                    "common_event_outbox": 0,
                    "common_event_inbox": 0,
                    "common_event_consumer_checkpoint": 0,
                },
            ),
            patch.object(smoke_runner, "fetch_source_events_for_smoke", return_value=[source_event()]),
            patch.object(smoke_runner, "fetch_existing_consume_keys", return_value=set()),
            patch.object(
                smoke_runner,
                "fetch_smoke_run_metadata",
                return_value={
                    "source_condition_run_id": "condition_layer_test",
                    "source_market_data_run_id": "snapshot_run",
                    "for_trade_date": "20260608",
                    "source_trade_date": "20260605",
                    "prev_trade_date": "20260605",
                },
            ),
            patch.object(smoke_runner, "persist_worker_smoke_write_plan") as persist,
        ):
            with self.assertRaisesRegex(N4WorkerSmokeBlocked, "before_write"):
                smoke_runner._execute_scoped_smoke(
                    args,
                    "n4_worker_bounded_smoke_idempotency_test",
                    "snapshot_run",
                    "MarketSnapshotUpdated",
                    "20260608",
                    idempotency_scenario=scenario,
                )

        persist.assert_not_called()

    def test_idempotency_failure_injection_after_persist_rolls_back_context(self):
        class FakeConnection:
            exc_type = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.exc_type = exc_type
                return False

        fake_conn = FakeConnection()
        args = smoke_runner.build_arg_parser().parse_args(
            [
                "--execute",
                "--user-confirmed",
                "--smoke-run-id",
                "n4_worker_bounded_smoke_idempotency_test",
                "--consumer-name",
                "n4_trigger_worker_v1",
                "--source-run-id",
                "snapshot_run",
                "--source-trade-date",
                "20260608",
                "--max-events",
                "10",
            ]
        )
        scenario = {
            "scenario_enabled": True,
            "duplicate_source_event_counts": {},
            "existing_consume_keys": [],
            "failure_injection": {
                "enabled": True,
                "point": "after_persist_before_commit",
                "reason": "test_after_persist",
            },
        }
        with (
            patch.object(smoke_runner.psycopg, "connect", return_value=fake_conn),
            patch.object(
                smoke_runner,
                "fetch_smoke_baseline_counts",
                return_value={
                    "common_trigger_run": 0,
                    "common_trigger_quality_item": 0,
                    "common_trigger_state": 0,
                    "common_trigger_match": 0,
                    "common_event_outbox": 0,
                    "common_event_inbox": 0,
                    "common_event_consumer_checkpoint": 0,
                },
            ),
            patch.object(smoke_runner, "fetch_source_events_for_smoke", return_value=[source_event()]),
            patch.object(smoke_runner, "fetch_existing_consume_keys", return_value=set()),
            patch.object(
                smoke_runner,
                "fetch_smoke_run_metadata",
                return_value={
                    "source_condition_run_id": "condition_layer_test",
                    "source_market_data_run_id": "snapshot_run",
                    "for_trade_date": "20260608",
                    "source_trade_date": "20260605",
                    "prev_trade_date": "20260605",
                },
            ),
            patch.object(
                smoke_runner,
                "persist_worker_smoke_write_plan",
                return_value={
                    "common_trigger_run": 1,
                    "common_trigger_quality_item": 2,
                    "common_event_inbox": 1,
                    "common_event_consumer_checkpoint": 1,
                    "common_trigger_state": 0,
                    "common_trigger_match": 0,
                    "common_event_outbox": 0,
                },
            ) as persist,
        ):
            with self.assertRaisesRegex(N4WorkerSmokeBlocked, "after_persist_before_commit"):
                smoke_runner._execute_scoped_smoke(
                    args,
                    "n4_worker_bounded_smoke_idempotency_test",
                    "snapshot_run",
                    "MarketSnapshotUpdated",
                    "20260608",
                    idempotency_scenario=scenario,
                )

        persist.assert_called_once()
        self.assertIs(fake_conn.exc_type, N4WorkerSmokeBlocked)

    def test_semantic_fixture_requires_explicit_semantic_smoke_before_db_write(self):
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "missing --semantic-smoke"):
            require_semantic_inputs(
                semantic_smoke=False,
                semantic_fixture_path="fixtures/semantic.json",
                semantic_oracle_run_id=None,
            )
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "missing semantic fixture/oracle"):
            require_semantic_inputs(
                semantic_smoke=True,
                semantic_fixture_path=None,
                semantic_oracle_run_id=None,
            )

    def test_runner_blocks_semantic_fixture_without_semantic_smoke_before_db_connect(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(smoke_runner.psycopg, "connect") as connect:
            fixture_path = Path(tmpdir) / "semantic_fixture.json"
            fixture_path.write_text(json.dumps({"fixture_only": True, "evaluations": [matched_eval()]}), encoding="utf-8")
            rc = smoke_runner.main(
                [
                    "--execute",
                    "--user-confirmed",
                    "--smoke-run-id",
                    "n4_worker_bounded_smoke_semantic_test",
                    "--source-run-id",
                    "snapshot_run",
                    "--source-trade-date",
                    "20260608",
                    "--semantic-fixture-path",
                    str(fixture_path),
                    "--json-report-path",
                    str(Path(tmpdir) / "report.json"),
                    "--markdown-report-path",
                    str(Path(tmpdir) / "report.md"),
                    "--rollback-sql-path",
                    str(Path(tmpdir) / "rollback.sql"),
                ]
            )

        self.assertEqual(rc, 2)
        connect.assert_not_called()

    def test_runner_blocks_semantic_mode_without_fixture_or_oracle_before_db_connect(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(smoke_runner.psycopg, "connect") as connect:
            rc = smoke_runner.main(
                [
                    "--execute",
                    "--user-confirmed",
                    "--smoke-run-id",
                    "n4_worker_bounded_smoke_semantic_test",
                    "--source-run-id",
                    "snapshot_run",
                    "--source-trade-date",
                    "20260608",
                    "--semantic-smoke",
                    "--json-report-path",
                    str(Path(tmpdir) / "report.json"),
                    "--markdown-report-path",
                    str(Path(tmpdir) / "report.md"),
                    "--rollback-sql-path",
                    str(Path(tmpdir) / "rollback.sql"),
                ]
            )

        self.assertEqual(rc, 2)
        connect.assert_not_called()

    def test_execute_report_metadata_marks_scoped_n4_writes_without_forbidden_side_effects(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_report_path = Path(tmpdir) / "report.json"
            markdown_report_path = Path(tmpdir) / "report.md"
            rollback_sql_path = Path(tmpdir) / "rollback.sql"
            status_json_path = Path(tmpdir) / "status.json"
            execute_report = {
                "dry_run_summary": {
                    "accepted_source_event_count": 2,
                    "skipped_duplicate_source_event_count": 0,
                    "transition_event_plan_count": 0,
                    "TriggerMatched": 0,
                    "TriggerPendingMarketData": 0,
                    "TriggerStateChanged": 0,
                },
                "write_counts": {
                    "common_trigger_run": 1,
                    "common_trigger_quality_item": 2,
                    "common_event_inbox": 2,
                    "common_event_consumer_checkpoint": 2,
                    "common_trigger_state": 0,
                    "common_trigger_match": 0,
                    "common_event_outbox": 0,
                },
                "write_scope": [
                    "common_trigger_run",
                    "common_trigger_quality_item",
                    "common_event_inbox",
                    "common_event_consumer_checkpoint",
                    "common_trigger_state",
                    "common_trigger_match",
                    "common_event_outbox",
                ],
                "idempotency_scenario": {
                    "scenario_enabled": False,
                    "accepted_source_event_count": 2,
                    "skipped_duplicate_source_event_count": 0,
                },
                "semantic_smoke": False,
                "semantic_input_summary": {
                    "fixture_only": False,
                    "source_oracle_run_id": None,
                    "not_new_market_decision": False,
                    "evaluation_count": 0,
                    "previous_state_count": 0,
                },
                "n3_outbox_status_updated": False,
                "worker_started": False,
                "n5_n6_entered": False,
            }
            with patch.object(smoke_runner, "_execute_scoped_smoke", return_value=execute_report):
                rc = smoke_runner.main(
                    [
                        "--execute",
                        "--user-confirmed",
                        "--smoke-run-id",
                        "n4_worker_bounded_smoke_metadata_test",
                        "--consumer-name",
                        "n4_trigger_worker_v1_metadata_test",
                        "--source-run-id",
                        "snapshot_run",
                        "--source-trade-date",
                        "20260608",
                        "--json-report-path",
                        str(json_report_path),
                        "--markdown-report-path",
                        str(markdown_report_path),
                        "--rollback-sql-path",
                        str(rollback_sql_path),
                        "--status-json",
                        str(status_json_path),
                    ]
                )

            self.assertEqual(rc, 0)
            report = json.loads(json_report_path.read_text(encoding="utf-8"))
            status = json.loads(status_json_path.read_text(encoding="utf-8"))
            self.assertTrue(report["database_written"])
            self.assertTrue(report["scoped_n4_database_writes"])
            self.assertTrue(report["side_effects"]["database_written"])
            self.assertTrue(report["side_effects"]["scoped_n4_database_writes"])
            self.assertFalse(report["side_effects"]["worker_started"])
            self.assertFalse(report["side_effects"]["n3_outbox_updated"])
            self.assertFalse(report["side_effects"]["n3_outbox_status_updated"])
            self.assertFalse(report["side_effects"]["n5_n6_entered"])
            self.assertEqual(report["write_counts"]["common_event_inbox"], 2)
            self.assertTrue(status["database_written"])
            self.assertTrue(status["scoped_n4_database_writes"])
            self.assertFalse(status["worker_started"])
            self.assertFalse(status["n3_outbox_updated"])
            self.assertFalse(status["n5_n6_entered"])

    def test_execute_requires_explicit_smoke_run_id_before_db_write(self):
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "missing --smoke-run-id"):
            smoke_runner.validate_execute_cli(
                execute=True,
                user_confirmed=True,
                smoke_run_id=None,
            )

    def test_same_source_event_reconsume_produces_no_duplicate_consume_keys(self):
        report = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=[source_event(), source_event()],
            evaluations=[matched_eval()],
            previous_states={},
            existing_consume_keys=set(),
            max_events=10,
        )

        self.assertEqual(report["summary"]["accepted_source_event_count"], 1)
        self.assertEqual(report["summary"]["skipped_duplicate_source_event_count"], 1)
        self.assertEqual(report["side_effects"]["n3_outbox_status_updated"], False)

    def test_consumer_boundary_has_no_n3_outbox_status_update_path(self):
        source = inspect.getsource(worker_consumer)

        self.assertNotIn("UPDATE common_event_outbox", source)
        self.assertNotIn("SET status", source)
        self.assertTrue(worker_consumer.CONSUMER_BOUNDARY["n4_must_not_update_n3_outbox_status"])

    def test_source_event_execute_guard_blocks_non_pending_and_over_max(self):
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "non-pending"):
            validate_source_events_for_execute(
                [source_event() | {"status": "delivered"}],
                source_event_type="MarketSnapshotUpdated",
                max_events=5,
            )
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "max_events"):
            validate_source_events_for_execute(
                [source_event(event_id=f"evt_{idx}", outbox_id=idx) for idx in range(6)],
                source_event_type="MarketSnapshotUpdated",
                max_events=5,
            )
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "unsupported source event type"):
            validate_source_events_for_execute(
                [source_event() | {"event_type": "MinuteBarClosed"}],
                source_event_type="MarketSnapshotUpdated",
                max_events=5,
            )

    def test_existing_baseline_rows_block_execute(self):
        clean = {
            "common_trigger_run": 0,
            "common_trigger_quality_item": 0,
            "common_trigger_state": 0,
            "common_trigger_match": 0,
            "common_event_outbox": 0,
            "common_event_inbox": 0,
            "common_event_consumer_checkpoint": 0,
        }
        assert_smoke_baseline_clean(clean)
        with self.assertRaisesRegex(N4WorkerSmokeBlocked, "target scoped rows already exist"):
            assert_smoke_baseline_clean(clean | {"common_event_outbox": 1})

    def test_execute_write_plan_scope_is_only_n4_smoke_tables(self):
        dry_run = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=[source_event()],
            evaluations=[matched_eval()],
            previous_states={},
            existing_consume_keys=set(),
            max_events=5,
        )
        write_plan = build_smoke_write_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_condition_run_id="condition_layer_test",
            source_market_data_run_id="snapshot_run",
            for_trade_date="20260608",
            source_trade_date="20260605",
            prev_trade_date="20260605",
            dry_run_plan=dry_run,
        )

        self.assertEqual(set(write_plan["allowed_write_tables"]), ALLOWED_SMOKE_WRITE_TABLES)
        self.assertEqual(write_plan["forbidden_write_tables"]["N3_common_event_outbox_status_update"], False)
        self.assertEqual(write_plan["run_row"]["run_id"], "n4_worker_bounded_smoke_test")
        self.assertEqual(write_plan["inbox_rows"][0]["consumer_name"], "n4_trigger_worker_v1")
        self.assertEqual(write_plan["outbox_rows"][0]["source_run_id"], "n4_worker_bounded_smoke_test")
        self.assertEqual(write_plan["match_rows"][0]["output_event_type"], "TriggerMatched")
        self.assertTrue(write_plan["outbox_rows"][0]["payload_json"]["n5_entry_allowed"])

    def test_semantic_fixture_path_generates_trigger_matched_write_plan(self):
        fixture = {
            "fixture_only": True,
            "source_oracle_run_id": "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry",
            "not_new_market_decision": True,
            "evaluations": [matched_eval()],
            "previous_states": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "semantic_fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            loaded = load_semantic_fixture(str(fixture_path))

        dry_run = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_semantic_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=[source_event()],
            evaluations=loaded["evaluations"],
            previous_states=loaded["previous_states"],
            existing_consume_keys=set(),
            max_events=5,
        )
        write_plan = build_smoke_write_plan(
            smoke_run_id="n4_worker_bounded_smoke_semantic_test",
            consumer_name="n4_trigger_worker_v1",
            source_condition_run_id="condition_layer_test",
            source_market_data_run_id="snapshot_run",
            for_trade_date="20260608",
            source_trade_date="20260605",
            prev_trade_date="20260605",
            dry_run_plan=dry_run,
        )

        self.assertEqual(dry_run["summary"]["TriggerMatched"], 1)
        self.assertEqual(dry_run["summary"]["TriggerStateChanged"], 1)
        self.assertEqual(write_plan["write_counts"]["common_trigger_state"], 1)
        self.assertEqual(write_plan["write_counts"]["common_trigger_match"], 1)
        self.assertEqual(write_plan["write_counts"]["common_event_outbox"], 2)
        self.assertEqual(write_plan["match_rows"][0]["state_unique_key"], write_plan["state_rows"][0]["state_unique_key"])
        self.assertTrue(write_plan["match_rows"][0]["raw_json"]["fixture_only"])
        self.assertEqual(
            write_plan["match_rows"][0]["raw_json"]["source_oracle_run_id"],
            "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry",
        )

    def test_semantic_oracle_source_event_ids_are_ordered_unique_and_bounded(self):
        evaluations = [
            matched_eval(event_id="evt_rank_214"),
            matched_eval(event_id="evt_rank_233"),
            matched_eval(event_id="evt_rank_214"),
            matched_eval(event_id="evt_rank_235"),
            matched_eval(event_id="evt_rank_243"),
        ]

        self.assertEqual(
            semantic_source_event_ids(evaluations, max_events=3),
            ["evt_rank_214", "evt_rank_233", "evt_rank_235"],
        )

    def test_semantic_oracle_previous_states_suppress_state_changed_for_matched_replay(self):
        evaluations = [
            matched_eval(event_id=f"evt_rank_{idx}", identity_key=f"stock:SZ:{idx:06d}")
            for idx in range(10)
        ]
        previous_states = {
            worker_consumer._state_lookup_key(row): row | {"current_status": "matched", "trigger_live": True}
            for row in evaluations
        }

        dry_run = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_semantic_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=[
                source_event(
                    event_id=str(row["source_event_id"]),
                    outbox_id=200 + idx,
                    identity_key=str(row["identity_key"]),
                )
                for idx, row in enumerate(evaluations)
            ],
            evaluations=evaluations,
            previous_states=previous_states,
            existing_consume_keys=set(),
            max_events=10,
        )

        self.assertEqual(dry_run["summary"]["accepted_source_event_count"], 10)
        self.assertEqual(dry_run["summary"]["transition_event_plan_count"], 10)
        self.assertEqual(dry_run["summary"]["TriggerMatched"], 10)
        self.assertEqual(dry_run["summary"]["TriggerPendingMarketData"], 0)
        self.assertEqual(dry_run["summary"]["TriggerStateChanged"], 0)

    def test_semantic_oracle_execute_path_selects_oracle_backed_source_events(self):
        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        ranks = (214, 233, 235, 243, 260, 262, 265, 267, 273, 287)
        evaluations = [
            matched_eval(event_id=f"evt_rank_{rank}", identity_key=f"stock:SZ:{rank:06d}")
            for rank in ranks
        ]
        previous_states = {
            worker_consumer._state_lookup_key(row): row | {"current_status": "matched", "trigger_live": True}
            for row in evaluations
        }
        selected_events = [
            source_event(
                event_id=str(row["source_event_id"]),
                outbox_id=rank,
                identity_key=str(row["identity_key"]),
            )
            for rank, row in zip(ranks, evaluations)
        ]
        expected_ids = [str(row["source_event_id"]) for row in evaluations]
        args = smoke_runner.build_arg_parser().parse_args(
            [
                "--execute",
                "--user-confirmed",
                "--semantic-smoke",
                "--semantic-oracle-run-id",
                "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry",
                "--smoke-run-id",
                "n4_worker_bounded_smoke_20260608_trigger_semantic_probe",
                "--consumer-name",
                "n4_trigger_worker_v1_bounded_smoke_semantic_probe",
                "--source-run-id",
                "snapshot_run",
                "--source-trade-date",
                "20260608",
                "--max-events",
                "10",
            ]
        )

        def fetch_by_event_ids(_conn, **kwargs):
            self.assertEqual(kwargs["source_event_ids"], expected_ids)
            self.assertEqual(kwargs["source_run_id"], "snapshot_run")
            return selected_events

        with (
            patch.object(smoke_runner.psycopg, "connect", return_value=FakeConnection()),
            patch.object(
                smoke_runner,
                "fetch_smoke_baseline_counts",
                return_value={
                    "common_trigger_run": 0,
                    "common_trigger_quality_item": 0,
                    "common_trigger_state": 0,
                    "common_trigger_match": 0,
                    "common_event_outbox": 0,
                    "common_event_inbox": 0,
                    "common_event_consumer_checkpoint": 0,
                },
            ),
            patch.object(
                smoke_runner,
                "_load_semantic_inputs",
                return_value={
                    "fixture_only": True,
                    "source_oracle_run_id": "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry",
                    "not_new_market_decision": True,
                    "evaluations": evaluations,
                    "previous_states": previous_states,
                },
            ),
            patch.object(smoke_runner, "fetch_source_events_by_event_ids_for_smoke", side_effect=fetch_by_event_ids) as semantic_fetch,
            patch.object(smoke_runner, "fetch_source_events_for_smoke") as first_pending_fetch,
            patch.object(smoke_runner, "fetch_existing_consume_keys", return_value=set()),
            patch.object(
                smoke_runner,
                "fetch_smoke_run_metadata",
                return_value={
                    "source_condition_run_id": "condition_layer_test",
                    "source_market_data_run_id": "snapshot_run",
                    "for_trade_date": "20260608",
                    "source_trade_date": "20260605",
                    "prev_trade_date": "20260605",
                },
            ),
            patch.object(
                smoke_runner,
                "persist_worker_smoke_write_plan",
                side_effect=lambda _conn, write_plan: dict(write_plan["write_counts"]),
            ),
        ):
            report = smoke_runner._execute_scoped_smoke(
                args,
                "n4_worker_bounded_smoke_20260608_trigger_semantic_probe",
                "snapshot_run",
                "MarketSnapshotUpdated",
                "20260608",
            )

        semantic_fetch.assert_called_once()
        first_pending_fetch.assert_not_called()
        self.assertEqual(report["dry_run_summary"]["accepted_source_event_count"], 10)
        self.assertEqual(report["dry_run_summary"]["transition_event_plan_count"], 10)
        self.assertEqual(report["dry_run_summary"]["TriggerMatched"], 10)
        self.assertEqual(report["dry_run_summary"]["TriggerPendingMarketData"], 0)
        self.assertEqual(report["dry_run_summary"]["TriggerStateChanged"], 0)
        self.assertEqual(report["write_counts"]["common_trigger_state"], 10)
        self.assertEqual(report["write_counts"]["common_trigger_match"], 10)
        self.assertEqual(report["write_counts"]["common_event_outbox"], 10)

    def test_pending_and_state_changed_do_not_write_common_trigger_match(self):
        dry_run = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=[source_event()],
            evaluations=[
                matched_eval()
                | {
                    "current_status": "pending_market_data",
                    "trigger_live": False,
                    "output_event_type": "TriggerPendingMarketData",
                    "n5_entry_allowed": False,
                    "new_trigger_fact": False,
                    "missing_evidence_kind": "projection_missing",
                }
            ],
            previous_states={},
            existing_consume_keys=set(),
            max_events=5,
        )
        write_plan = build_smoke_write_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_condition_run_id="condition_layer_test",
            source_market_data_run_id="snapshot_run",
            for_trade_date="20260608",
            source_trade_date="20260605",
            prev_trade_date="20260605",
            dry_run_plan=dry_run,
        )

        self.assertEqual(write_plan["write_counts"]["common_trigger_match"], 0)
        self.assertEqual(write_plan["write_counts"]["common_trigger_state"], 1)
        self.assertEqual(write_plan["write_counts"]["common_event_outbox"], 2)
        self.assertEqual(write_plan["event_distribution"]["TriggerPendingMarketData"], 1)
        self.assertEqual(write_plan["event_distribution"]["TriggerStateChanged"], 1)
        self.assertEqual(
            write_plan["state_rows"][0]["raw_json"]["coalesced_output_event_types"],
            ["TriggerPendingMarketData", "TriggerStateChanged"],
        )
        self.assertFalse(any(row["output_event_type"] != "TriggerMatched" for row in write_plan["match_rows"]))

    def test_matched_and_state_changed_same_key_write_one_state_and_one_match(self):
        dry_run = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=[source_event()],
            evaluations=[matched_eval()],
            previous_states={},
            existing_consume_keys=set(),
            max_events=5,
        )
        write_plan = build_smoke_write_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_condition_run_id="condition_layer_test",
            source_market_data_run_id="snapshot_run",
            for_trade_date="20260608",
            source_trade_date="20260605",
            prev_trade_date="20260605",
            dry_run_plan=dry_run,
        )

        self.assertEqual(write_plan["event_distribution"]["TriggerMatched"], 1)
        self.assertEqual(write_plan["event_distribution"]["TriggerStateChanged"], 1)
        self.assertEqual(write_plan["write_counts"]["common_trigger_state"], 1)
        self.assertEqual(write_plan["write_counts"]["common_trigger_match"], 1)
        self.assertEqual(write_plan["write_counts"]["common_event_outbox"], 2)
        self.assertEqual(write_plan["state_rows"][0]["output_event_type"], "TriggerMatched")
        self.assertEqual(write_plan["state_rows"][0]["match_count"], 1)
        self.assertEqual(write_plan["match_rows"][0]["state_unique_key"], write_plan["state_rows"][0]["state_unique_key"])
        self.assertTrue(write_plan["outbox_rows"][0]["payload_json"]["n5_entry_allowed"])
        self.assertFalse(write_plan["outbox_rows"][1]["payload_json"]["n5_entry_allowed"])

    def test_multiple_different_state_keys_each_write_one_state(self):
        dry_run = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=[
                source_event(event_id="evt_source_1", outbox_id=1, identity_key="board:TDX:881011"),
                source_event(event_id="evt_source_2", outbox_id=2, identity_key="board:TDX:881016"),
            ],
            evaluations=[
                matched_eval(event_id="evt_source_1", identity_key="board:TDX:881011")
                | {
                    "asset_kind": "board",
                    "condition_key": "BUY_HINT",
                    "current_status": "pending_market_data",
                    "trigger_live": False,
                    "output_event_type": "TriggerPendingMarketData",
                    "n5_entry_allowed": False,
                    "new_trigger_fact": False,
                    "missing_evidence_kind": "projection_missing",
                    "projection_30m_flag": True,
                },
                matched_eval(event_id="evt_source_2", identity_key="board:TDX:881016")
                | {
                    "asset_kind": "board",
                    "condition_key": "BUY_HINT",
                    "current_status": "pending_market_data",
                    "trigger_live": False,
                    "output_event_type": "TriggerPendingMarketData",
                    "n5_entry_allowed": False,
                    "new_trigger_fact": False,
                    "missing_evidence_kind": "projection_missing",
                    "projection_30m_flag": True,
                },
            ],
            previous_states={},
            existing_consume_keys=set(),
            max_events=5,
        )
        write_plan = build_smoke_write_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_condition_run_id="condition_layer_test",
            source_market_data_run_id="snapshot_run",
            for_trade_date="20260608",
            source_trade_date="20260605",
            prev_trade_date="20260605",
            dry_run_plan=dry_run,
        )

        self.assertEqual(write_plan["write_counts"]["common_trigger_state"], 2)
        self.assertEqual(write_plan["write_counts"]["common_trigger_match"], 0)
        self.assertEqual(write_plan["event_distribution"]["TriggerPendingMarketData"], 2)
        self.assertEqual(write_plan["event_distribution"]["TriggerStateChanged"], 2)
        self.assertEqual(len({row["state_unique_key"] for row in write_plan["state_rows"]}), 2)

    def test_json_safe_conversion_preserves_fields_and_normalizes_non_json_types(self):
        payload = {
            "event_id": "evt_source_1",
            "outbox_id": 1,
            "event_time": datetime(2026, 6, 8, 15, 0, tzinfo=timezone.utc),
            "trade_date": date(2026, 6, 8),
            "clock": time(15, 0),
            "price": Decimal("10.50"),
            "uuid": UUID("12345678-1234-5678-1234-567812345678"),
        }
        safe = make_json_safe(payload)

        json.dumps(safe)
        self.assertEqual(safe["event_id"], "evt_source_1")
        self.assertEqual(safe["outbox_id"], 1)
        self.assertEqual(safe["event_time"], "2026-06-08T15:00:00+00:00")
        self.assertEqual(safe["price"], "10.50")
        self.assertEqual(safe["uuid"], "12345678-1234-5678-1234-567812345678")

    def test_source_datetime_payload_is_json_safe_before_inbox_and_checkpoint_insert(self):
        event = source_event() | {
            "event_time": datetime(2026, 6, 8, 15, 0, tzinfo=timezone.utc),
            "created_at": datetime(2026, 6, 8, 9, 44, tzinfo=timezone.utc),
            "payload_json": {
                "snapshot_id": 4013,
                "source_run_id": "snapshot_run",
                "snapshot_time": datetime(2026, 6, 8, 15, 0, tzinfo=timezone.utc),
                "price": Decimal("12.34"),
            },
        }
        dry_run = build_worker_smoke_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_events=[event],
            evaluations=[],
            previous_states={},
            existing_consume_keys=set(),
            max_events=5,
        )
        write_plan = build_smoke_write_plan(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
            source_condition_run_id="condition_layer_test",
            source_market_data_run_id="snapshot_run",
            for_trade_date="20260608",
            source_trade_date="20260605",
            prev_trade_date="20260605",
            dry_run_plan=dry_run,
        )

        inbox_row = write_plan["inbox_rows"][0]
        checkpoint_row = write_plan["checkpoint_rows"][0]
        json.dumps(inbox_row["payload_json"])
        json.dumps(inbox_row["raw_json"])
        json.dumps(checkpoint_row["checkpoint_payload"])
        self.assertEqual(inbox_row["event_id"], "evt_source_1")
        self.assertEqual(inbox_row["raw_json"]["source_outbox_id"], 1)
        self.assertEqual(inbox_row["raw_json"]["source_event_time"], "2026-06-08T15:00:00+00:00")
        self.assertEqual(inbox_row["payload_json"]["snapshot_time"], "2026-06-08T15:00:00+00:00")
        self.assertEqual(inbox_row["payload_json"]["price"], "12.34")

    def test_bounded_controls_enforce_max_events_runtime_stop_file_and_status_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stop_file = os.path.join(tmpdir, "stop")
            status_json = os.path.join(tmpdir, "status.json")
            open(stop_file, "w", encoding="utf-8").close()

            controls = build_bounded_controls(
                max_events=5,
                max_runtime_seconds=60,
                stop_file=stop_file,
                status_json=status_json,
                heartbeat_interval_seconds=10,
            )
            write_status_json(status_json, {"result": "DRY_VALIDATION", "processed_event_count": 0})

            self.assertEqual(controls["max_events"], 5)
            self.assertEqual(controls["max_runtime_seconds"], 60)
            self.assertTrue(controls["stop_requested"])
            with open(status_json, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["result"], "DRY_VALIDATION")

    def test_rollback_sql_is_hard_fail_guarded_and_scoped(self):
        sql = build_worker_rollback_sql(
            smoke_run_id="n4_worker_bounded_smoke_test",
            consumer_name="n4_trigger_worker_v1",
        )
        first_delete = sql.lower().find("delete from")
        first_raise = sql.lower().find("raise exception")

        self.assertGreaterEqual(first_delete, 0)
        self.assertGreaterEqual(first_raise, 0)
        self.assertLess(first_raise, first_delete)
        self.assertIn("n4_worker_bounded_smoke_test", sql)
        self.assertIn("n4_trigger_worker_v1", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("N5", sql)
        self.assertIn("N6", sql)
        self.assertNotIn("DROP", sql.upper())
        self.assertNotIn("TRUNCATE", sql.upper())
        self.assertNotIn("CASCADE", sql.upper())


if __name__ == "__main__":
    unittest.main()
