import json
import unittest
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scripts.run_action_consumer_once import build_parser

from ashare_v3.action.execute import (
    ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID,
    ACTION_CONFIRMATION_METRIC_20260602_N5_EXECUTE_ACTION_RUN_ID,
    CANONICAL_20260528_N4_SOURCE_RUN_ID,
    CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
    CANONICAL_20260529_N4_SOURCE_RUN_ID,
    CANONICAL_20260529_N5_EXECUTE_ACTION_RUN_ID,
    EXPECTED_ACTION_CONFIRMATION_METRIC_20260602_PENDING_EVENT_COUNT,
    CURRENT_REAL_N5_EXECUTE_ACTION_RUN_ID,
    CURRENT_REAL_N4_SOURCE_RUN_ID,
    SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
    build_current_real_execute_contract_from_rows,
    build_consumption_only_smoke_contract_from_rows,
    build_deterministic_action_metric_join,
    build_semantic_action_smoke_contract_from_rows,
    build_action_event_passthrough_payload,
    build_executable_plan_from_rows,
    build_current_real_rollback_sql,
    build_planned_write_scope,
    fetch_live_window_action_confirmation_metric_rows,
    fetch_current_real_pending_outbox_rows,
    fetch_semantic_action_smoke_outbox_rows,
    infer_action_metric_run_ids_from_baseline,
    resolve_action_confirmation_metrics_for_execute,
    execute_consumption_only_smoke_transaction,
    execute_action_transaction,
    format_execute_contract,
    insert_action_fact,
    insert_common_action_event,
    normalize_action_persistence_row,
    upsert_action_tracking_states,
    upsert_checkpoints,
)
from ashare_v3.action.run_once_dry_run import compare_baseline_report, summarize_action_write_plan, summarize_output_event_plan
from ashare_v3.action.event_factory import build_n5_action_event
from ashare_v3.events.models import EventContractError


class ActionExecuteRunnerContractTest(unittest.TestCase):
    def test_consumption_only_smoke_cli_aliases_parse(self) -> None:
        args = build_parser().parse_args(
            [
                "--consumption-only-smoke",
                "--smoke-run-id",
                "n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe",
                "--source-trigger-run-id",
                "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry",
                "--source-event-type",
                "TriggerMatched",
                "--consumer-name",
                "n5_action_worker_v1_scoped_consumption_smoke_probe",
                "--max-events",
                "50",
                "--max-runtime-seconds",
                "120",
                "--heartbeat-interval-seconds",
                "10",
                "--status-json",
                "docs/n5_smoke_status.json",
                "--stop-file",
                "tmp/n5_smoke.stop",
            ]
        )

        self.assertTrue(args.consumption_only_smoke)
        self.assertEqual(args.smoke_run_id, "n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe")
        self.assertEqual(args.source_run_id, "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry")
        self.assertEqual(args.source_event_types, ["TriggerMatched"])
        self.assertEqual(args.max_events, 50)
        self.assertEqual(args.max_runtime_seconds, 120)
        self.assertEqual(args.heartbeat_interval_seconds, 10)

    def test_consumption_only_smoke_blocks_without_double_confirmation(self) -> None:
        contract = build_consumption_only_smoke_contract_from_rows(
            execute=False,
            user_confirmed=True,
            smoke_run_id="n5_smoke_run",
            source_trigger_run_id="trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry",
            consumer_name="n5_action_worker_v1_scoped_consumption_smoke_probe",
            source_event_types=["TriggerMatched"],
            max_events=50,
            max_runtime_seconds=120,
            heartbeat_interval_seconds=10,
            outbox_rows=[sample_outbox_row(source_run_id="trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry")],
            trigger_run={"run_id": "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry", "for_trade_date": "20260608"},
        )

        self.assertFalse(contract["allow_execute"])
        self.assertIn("n5_consumption_only_smoke_double_confirmation", contract["blockers"])
        self.assertFalse(contract["side_effects"]["writes_performed"])
        self.assertEqual(contract["planned_write_scope"]["stock_action_fact"], 0)
        self.assertEqual(contract["planned_write_scope"]["common_action_event"], 0)
        self.assertEqual(contract["planned_write_scope"]["common_event_outbox"], 0)

    def test_consumption_only_smoke_plans_only_run_quality_inbox_checkpoint(self) -> None:
        source_run_id = "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry"
        contract = build_consumption_only_smoke_contract_from_rows(
            execute=True,
            user_confirmed=True,
            smoke_run_id="n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe",
            source_trigger_run_id=source_run_id,
            consumer_name="n5_action_worker_v1_scoped_consumption_smoke_probe",
            source_event_types=["TriggerMatched"],
            max_events=50,
            max_runtime_seconds=120,
            heartbeat_interval_seconds=10,
            outbox_rows=[
                sample_outbox_row(event_id="evt_smoke_1", trigger_match_id=1, source_run_id=source_run_id, trade_date="20260608"),
                sample_outbox_row(event_id="evt_smoke_2", trigger_match_id=2, source_run_id=source_run_id, trade_date="20260608"),
            ],
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260608"},
        )

        self.assertTrue(contract["allow_execute"])
        self.assertEqual(contract["planned_write_scope"]["common_action_run"], 1)
        self.assertGreaterEqual(contract["planned_write_scope"]["common_action_quality_item"], 1)
        self.assertEqual(contract["planned_write_scope"]["common_event_inbox"], 2)
        self.assertEqual(contract["planned_write_scope"]["stock_action_fact"], 0)
        self.assertEqual(contract["planned_write_scope"]["index_action_fact"], 0)
        self.assertEqual(contract["planned_write_scope"]["board_action_fact"], 0)
        self.assertEqual(contract["planned_write_scope"]["common_action_event"], 0)
        self.assertEqual(contract["planned_write_scope"]["common_event_outbox"], 0)
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionExecuted"], 0)
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionBlocked"], 0)
        self.assertFalse(contract["side_effects"]["n4_outbox_status_updated"])
        self.assertFalse(contract["side_effects"]["n6_user_layer_touched"])

    def test_consumption_only_smoke_transaction_never_writes_action_fact_event_or_outbox(self) -> None:
        source_run_id = "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry"
        plan = build_consumption_only_smoke_contract_from_rows(
            execute=True,
            user_confirmed=True,
            smoke_run_id="n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe",
            source_trigger_run_id=source_run_id,
            consumer_name="n5_action_worker_v1_scoped_consumption_smoke_probe",
            source_event_types=["TriggerMatched"],
            max_events=50,
            max_runtime_seconds=120,
            heartbeat_interval_seconds=10,
            outbox_rows=[
                sample_outbox_row(event_id="evt_smoke_tx", trigger_match_id=10, source_run_id=source_run_id, trade_date="20260608")
            ],
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260608"},
        )
        cursor = RecordingCursor()

        counts = execute_consumption_only_smoke_transaction(
            cursor,
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260608"},
            plan=plan,
        )
        sql = "\n".join(call[0].lower() for call in cursor.calls)

        self.assertEqual(counts["stock_action_fact"], 0)
        self.assertEqual(counts["index_action_fact"], 0)
        self.assertEqual(counts["board_action_fact"], 0)
        self.assertEqual(counts["common_action_event"], 0)
        self.assertEqual(counts["common_event_outbox"], 0)
        self.assertNotIn("insert into stock_action_fact", sql)
        self.assertNotIn("insert into index_action_fact", sql)
        self.assertNotIn("insert into board_action_fact", sql)
        self.assertNotIn("insert into common_action_event", sql)
        self.assertNotIn("insert into common_event_outbox", sql)
        self.assertNotIn("update common_event_outbox", sql)

    def test_semantic_action_smoke_cli_aliases_parse(self) -> None:
        args = build_parser().parse_args(
            [
                "--semantic-action-smoke",
                "--smoke-run-id",
                "n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe",
                "--consumer-name",
                "n5_action_worker_v1_semantic_action_smoke_probe",
                "--source-trigger-run-id",
                "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry",
                "--source-event-type",
                "TriggerMatched",
                "--metric-run-id",
                "action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry",
                "--max-events",
                "50",
                "--max-runtime-seconds",
                "120",
                "--heartbeat-interval-seconds",
                "10",
                "--status-json",
                "docs/N5_WORKER_SEMANTIC_ACTION_SMOKE_STATUS.json",
                "--stop-file",
                "tmp/n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe.stop",
                "--current-only-trigger-matched",
            ]
        )

        self.assertTrue(args.semantic_action_smoke)
        self.assertEqual(args.metric_run_id, "action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry")
        self.assertEqual(args.max_events, 50)
        self.assertEqual(args.source_event_types, ["TriggerMatched"])
        self.assertTrue(args.current_only_trigger_matched)

    def test_canonical_action_consumer_cli_passes_source_event_type_filter(self) -> None:
        args = build_parser().parse_args(
            [
                "--source-trigger-run-id",
                "v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3",
                "--action-run-id",
                "v3_n5_action_replay_20260612_after_n4_state_machine_v3",
                "--consumer-name",
                "v3_n5_action_replay_20260612_state_machine_consumer_v3",
                "--source-event-type",
                "TriggerMatched",
            ]
        )

        self.assertEqual(args.source_event_types, ["TriggerMatched"])

    def test_fetch_current_real_pending_outbox_rows_can_filter_to_trigger_matched(self) -> None:
        cursor = FetchRowsRecordingCursor()

        rows = fetch_current_real_pending_outbox_rows(
            cursor,
            "v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3",
            source_event_types=["TriggerMatched"],
        )

        self.assertEqual(rows, [])
        sql, params = cursor.calls[0]
        self.assertIn("event_type = ANY(%s)", sql)
        self.assertEqual(
            params,
            (
                "v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3",
                ["TriggerMatched"],
            ),
        )

    def test_resolve_action_confirmation_metrics_uses_direct_payload_metric_id_before_full_run_join(self) -> None:
        cursor = DirectMetricCursor()
        outbox_rows = [
            sample_outbox_row(
                event_id="evt_direct_metric",
                trigger_match_id=1,
                source_action_confirmation_metric_id=101,
            )
        ]

        result = resolve_action_confirmation_metrics_for_execute(
            cursor,
            outbox_rows,
            baseline_report={"metric_run_id": "direct_metric_run"},
        )

        self.assertTrue(result["summary"]["full_metric_run_join_skipped"])
        self.assertEqual(result["summary"]["join_policy"], "direct_payload_metric_id")
        self.assertEqual(result["summary"]["joined_rows"], 1)
        self.assertTrue(any("action_confirmation_metric_id = any" in call[0].lower() for call in cursor.calls))
        self.assertFalse(
            any(
                "projection_run_id = any" in call[0].lower()
                and "action_confirmation_metric_id = any" not in call[0].lower()
                for call in cursor.calls
            )
        )

    def test_live_trigger_metric_resolution_uses_bounded_identity_window_lookup(self) -> None:
        cursor = LiveWindowMetricCursor()
        outbox_rows = [
            sample_outbox_row(
                event_id="evt_live_window",
                trigger_match_id=1,
                source_action_confirmation_metric_id=101,
            )
        ]
        outbox_rows[0]["payload_json"].update({"trigger_live": True, "current_status": "matched"})

        result = resolve_action_confirmation_metrics_for_execute(
            cursor,
            outbox_rows,
            baseline_report={"metric_run_id": "direct_metric_run"},
        )

        self.assertTrue(result["summary"]["full_metric_run_join_skipped"])
        self.assertTrue(result["summary"]["live_window_metric_lookup_enabled"])
        self.assertEqual(result["summary"]["live_window_metric_lookup_policy"], "bounded_identity_window")
        self.assertTrue(
            any(
                "projection_run_id = any" in call[0].lower()
                and "identity_key = any" in call[0].lower()
                and "%s is null or" not in call[0].lower()
                and "metric_time >= %s::timestamptz" in call[0].lower()
                and "action_confirmation_metric_id = any" not in call[0].lower()
                for call in cursor.calls
            )
        )
        self.assertIn(("stock", "102"), result["action_confirmation_metric_facts"])
        self.assertIn(("stock", "stock:SH:600000"), result["action_confirmation_metric_facts_by_identity"])
        self.assertNotIn(("stock", "stock:SH:600001"), result["action_confirmation_metric_facts_by_identity"])

    def test_live_trigger_metric_lookup_missing_trigger_time_fails_closed_before_sql(self) -> None:
        cursor = LiveWindowMetricCursor()
        row = sample_outbox_row(
            event_id="evt_live_window_missing_time",
            trigger_match_id=1,
            source_action_confirmation_metric_id=101,
        )
        row["event_time"] = None
        row["payload_json"].update({"trigger_live": True, "current_status": "matched", "trigger_time": None})
        row["payload_json"].pop("metric_trace", None)
        row["payload_json"].pop("projection_trace", None)

        with self.assertRaisesRegex(ValueError, "live_window_min_trigger_time_missing"):
            fetch_live_window_action_confirmation_metric_rows(
                cursor,
                [row],
                metric_run_ids=["direct_metric_run"],
            )

        self.assertEqual(cursor.calls, [])

    def test_resolve_action_confirmation_metrics_blocks_projection_mismatch_without_full_join(self) -> None:
        cursor = DirectMetricCursor()
        outbox_rows = [
            sample_outbox_row(
                event_id="evt_direct_metric_mismatch",
                trigger_match_id=1,
                source_action_confirmation_metric_id=101,
            )
        ]

        result = resolve_action_confirmation_metrics_for_execute(
            cursor,
            outbox_rows,
            baseline_report={"metric_run_id": "other_metric_run"},
        )

        self.assertTrue(result["summary"]["full_metric_run_join_skipped"])
        self.assertEqual(result["summary"]["join_policy"], "direct_payload_metric_id")
        self.assertEqual(result["summary"]["joined_rows"], 0)
        self.assertEqual(result["summary"]["missing_rows"], 1)
        self.assertFalse(
            any(
                "projection_run_id = any" in call[0].lower()
                and "action_confirmation_metric_id = any" not in call[0].lower()
                for call in cursor.calls
            )
        )

    def test_semantic_action_smoke_blocks_without_metric_run_id_or_double_confirmation(self) -> None:
        source_run_id = "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry"
        contract = build_semantic_action_smoke_contract_from_rows(
            execute=False,
            user_confirmed=True,
            smoke_run_id="n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe",
            source_trigger_run_id=source_run_id,
            consumer_name="n5_action_worker_v1_semantic_action_smoke_probe",
            source_event_types=["TriggerMatched"],
            metric_run_id=None,
            max_events=50,
            max_runtime_seconds=120,
            heartbeat_interval_seconds=10,
            outbox_rows=[sample_outbox_row(source_run_id=source_run_id, trade_date="20260608")],
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260608"},
        )

        self.assertFalse(contract["allow_execute"])
        self.assertIn("n5_semantic_action_smoke_double_confirmation", contract["blockers"])
        self.assertIn("n5_semantic_action_smoke_metric_run_id_required", contract["blockers"])
        self.assertFalse(contract["side_effects"]["writes_performed"])

    def test_semantic_action_smoke_respects_max_events_and_binds_metric_run_id(self) -> None:
        source_run_id = "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry"
        metric_run_id = (
            "action_confirmation_metric_20260608_until_1500__"
            "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry"
        )
        rows = [
            sample_outbox_row(
                event_id="evt_semantic_1",
                trigger_match_id=1,
                source_run_id=source_run_id,
                trade_date="20260608",
                source_action_confirmation_metric_id=1,
            ),
            sample_outbox_row(
                event_id="evt_semantic_2",
                trigger_match_id=2,
                source_run_id=source_run_id,
                trade_date="20260608",
                source_action_confirmation_metric_id=2,
            ),
        ]
        contract = build_semantic_action_smoke_contract_from_rows(
            execute=True,
            user_confirmed=True,
            smoke_run_id="n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe",
            source_trigger_run_id=source_run_id,
            consumer_name="n5_action_worker_v1_semantic_action_smoke_probe",
            source_event_types=["TriggerMatched"],
            metric_run_id=metric_run_id,
            max_events=1,
            max_runtime_seconds=120,
            heartbeat_interval_seconds=10,
            outbox_rows=rows,
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260608"},
            action_confirmation_metric_facts={
                ("stock", "1"): metric_fact(
                    action_confirmation_metric_id=1,
                    projection_run_id=metric_run_id,
                    for_trade_date="20260608",
                    buy_pass=True,
                ),
                ("stock", "2"): metric_fact(
                    action_confirmation_metric_id=2,
                    projection_run_id=metric_run_id,
                    for_trade_date="20260608",
                    buy_pass=True,
                ),
            },
        )

        self.assertTrue(contract["allow_execute"])
        self.assertEqual(contract["consumer_plan_summary"]["read_event_count"], 1)
        self.assertEqual(contract["planned_write_scope"]["common_event_inbox"], 1)
        self.assertEqual(contract["planned_write_scope"]["common_action_event"], 1)
        self.assertEqual(contract["planned_write_scope"]["common_event_outbox"], 1)
        self.assertEqual(contract["metric_binding"]["metric_run_id"], metric_run_id)
        self.assertFalse(contract["metric_binding"]["opaque_action_confirmation_payload_trusted"])
        self.assertFalse(contract["side_effects"]["n4_outbox_status_updated"])

    def test_semantic_action_smoke_contract_uses_identity_metric_cache_for_live_window(self) -> None:
        source_run_id = "trigger_replay_phase2d_20260622_formal_unitfix_dseed_periodguard_until_1500"
        metric_run_id = "action_confirmation_projection_metric_test"
        row = sample_outbox_row(
            event_id="evt_live_window_000300",
            trigger_match_id=436642,
            source_run_id=source_run_id,
            trade_date="20260622",
            asset_kind="index",
            identity_key="index:SH:000300",
            signal_type="B_BUY",
            direction="buy",
            condition_key="BUY:M",
            source_action_confirmation_metric_id=338338,
        )
        row["event_time"] = "2026-06-22T13:56:00+08:00"
        row["payload_json"].update(
            {
                "trigger_time": "2026-06-22T13:56:00+08:00",
                "current_status": "matched",
                "trigger_live": True,
                "trigger_period": "M",
                "triggered_periods": ["M"],
                "all_trigger_periods": ["M"],
                "primary_trigger_period": "M",
            }
        )
        first_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338338,
            identity_key="index:SH:000300",
            projection_run_id=metric_run_id,
            for_trade_date="20260622",
            buy_pass=False,
        )
        first_metric.update({"metric_time": "2026-06-22T13:56:00+08:00", "metric_minute_label": "13:56"})
        later_metric = metric_fact(
            asset_kind="index",
            action_confirmation_metric_id=338343,
            identity_key="index:SH:000300",
            projection_run_id=metric_run_id,
            for_trade_date="20260622",
            buy_pass=True,
        )
        later_metric.update({"metric_time": "2026-06-22T14:01:00+08:00", "metric_minute_label": "14:01"})

        contract = build_semantic_action_smoke_contract_from_rows(
            execute=True,
            user_confirmed=True,
            smoke_run_id="n5_live_window_semantic_contract_probe",
            source_trigger_run_id=source_run_id,
            consumer_name="n5_live_window_semantic_contract_consumer",
            source_event_types=["TriggerMatched"],
            metric_run_id=metric_run_id,
            max_events=10,
            max_runtime_seconds=120,
            heartbeat_interval_seconds=10,
            outbox_rows=[row],
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260622"},
            action_confirmation_metric_facts={("index", "338338"): first_metric},
            action_confirmation_metric_facts_by_identity={
                ("index", "index:SH:000300"): [first_metric, later_metric],
            },
        )

        self.assertTrue(contract["allow_execute"])
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionExecuted"], 1)
        candidate = contract["dry_run_plan"]["sample_action_write_plan"][0]
        self.assertEqual(candidate["source_action_confirmation_metric_id"], "338343")
        live_trace = candidate["trace_json"]["live_window_confirmation"]
        self.assertTrue(live_trace["live_window_confirmation"])
        self.assertEqual(live_trace["trigger_metric_time"], "2026-06-22T13:56:00+08:00")
        self.assertEqual(live_trace["executed_metric_time"], "2026-06-22T14:01:00+08:00")
        self.assertTrue(contract["dry_run_plan"]["candidate_key_stability_recheck"]["stable_on_recompute"])

    def test_semantic_action_smoke_excludes_reviewed_unmaterializable_source_events(self) -> None:
        source_run_id = "n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000"
        metric_run_id = "action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1"
        rows = [
            sample_outbox_row(
                event_id="evt_metric_backed",
                trigger_match_id=11,
                source_run_id=source_run_id,
                trade_date="20260615",
                source_action_confirmation_metric_id=101,
            ),
            sample_outbox_row(
                event_id="evt_bj_unmaterializable",
                trigger_match_id=12,
                source_run_id=source_run_id,
                trade_date="20260615",
                asset_kind="index",
                identity_key="index:BJ:899050",
            ),
        ]

        contract = build_semantic_action_smoke_contract_from_rows(
            execute=True,
            user_confirmed=True,
            smoke_run_id="n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1",
            source_trigger_run_id=source_run_id,
            consumer_name="n5_action_bounded_consumer_20260615_after_n3_metric_until_1000_v1",
            source_event_types=["TriggerMatched"],
            excluded_event_ids=["evt_bj_unmaterializable"],
            metric_run_id=metric_run_id,
            max_events=2000,
            max_runtime_seconds=180,
            heartbeat_interval_seconds=10,
            rollback_sql_path="sql/V3_20260615_n5_replay_after_n3_metric_rollback.sql",
            outbox_rows=rows,
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260615"},
            action_confirmation_metric_facts={
                ("stock", "101"): metric_fact(
                    action_confirmation_metric_id=101,
                    projection_run_id=metric_run_id,
                    for_trade_date="20260615",
                    buy_pass=True,
                )
            },
        )

        self.assertTrue(contract["allow_execute"])
        self.assertEqual(contract["consumer_plan_summary"]["read_event_count"], 1)
        self.assertEqual(contract["planned_write_scope"]["common_event_inbox"], 1)
        self.assertEqual(contract["source_event_filter"]["excluded_event_count"], 1)
        self.assertEqual(contract["source_event_filter"]["excluded_event_ids"], ["evt_bj_unmaterializable"])
        self.assertEqual(
            contract["source_event_filter"]["excluded_event_reason"],
            "reviewed_unmaterializable_n3_action_metric_source_event",
        )
        self.assertEqual(
            contract["rollback_plan"]["rollback_sql_path"],
            "sql/V3_20260615_n5_replay_after_n3_metric_rollback.sql",
        )

    def test_fetch_semantic_action_smoke_outbox_rows_can_exclude_event_ids(self) -> None:
        cursor = FetchRowsRecordingCursor()

        fetch_semantic_action_smoke_outbox_rows(
            cursor,
            source_trigger_run_id="n4_run",
            source_event_types=["TriggerMatched"],
            excluded_event_ids=["evt_bj_unmaterializable"],
            max_events=2000,
        )

        sql, params = cursor.calls[0]
        self.assertIn("event_id <> ALL(%s)", sql)
        self.assertEqual(
            params,
            (
                "n4_run",
                ["TriggerMatched"],
                ["evt_bj_unmaterializable"],
                2000,
            ),
        )

    def test_fetch_semantic_action_smoke_outbox_rows_current_only_joins_current_trigger_state(self) -> None:
        cursor = FetchRowsRecordingCursor()

        fetch_semantic_action_smoke_outbox_rows(
            cursor,
            source_trigger_run_id="n4_run",
            source_event_types=["TriggerMatched"],
            excluded_event_ids=["evt_stale"],
            max_events=2000,
            current_only_trigger_matched=True,
        )

        sql, params = cursor.calls[0]
        self.assertIn("JOIN common_trigger_state", sql)
        self.assertIn("payload_json->>'trigger_state_id'", sql)
        self.assertIn("current_status = 'matched'", sql)
        self.assertIn("last_trigger_match_id::text", sql)
        self.assertEqual(
            params,
            (
                "n4_run",
                ["TriggerMatched"],
                ["evt_stale"],
                "n4_run",
                2000,
            ),
        )

    def test_missing_execute_flag_blocks(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=False,
            user_confirmed=True,
            outbox_rows=[sample_outbox_row()],
            trigger_run=trigger_run(),
        )

        self.assertFalse(contract["allow_execute"])
        self.assertIn("n5_execute_double_confirmation", contract["blockers"])
        self.assertFalse(contract["side_effects"]["writes_performed"])

    def test_missing_user_confirmed_flag_blocks(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=False,
            outbox_rows=[sample_outbox_row()],
            trigger_run=trigger_run(),
        )

        self.assertFalse(contract["allow_execute"])
        self.assertIn("n5_execute_double_confirmation", contract["blockers"])
        self.assertFalse(contract["side_effects"]["writes_performed"])

    def test_canonical_source_allowlist_blocks_synthetic_and_stale_sources(self) -> None:
        current = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            outbox_rows=[sample_outbox_row(source_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID, trade_date="20260528")],
            trigger_run=canonical_trigger_run(),
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
        )
        synthetic = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            trigger_run={"run_id": SYNTHETIC_N4_SOURCE_RUN_DENYLIST[0], "for_trade_date": "20260525"},
            outbox_rows=[sample_outbox_row(source_run_id=SYNTHETIC_N4_SOURCE_RUN_DENYLIST[0])],
        )
        stale = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            trigger_run=trigger_run(),
            outbox_rows=[sample_outbox_row(source_run_id=CURRENT_REAL_N4_SOURCE_RUN_ID)],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
        )

        self.assertTrue(current["source_run_guard"]["passed"])
        self.assertTrue(current["allow_execute"])
        self.assertNotIn("n5_execute_canonical_schema_alignment_required", current["blockers"])
        self.assertFalse(synthetic["source_run_guard"]["passed"])
        self.assertFalse(synthetic["allow_execute"])
        self.assertIn("n5_execute_source_run_guard", synthetic["blockers"])
        self.assertFalse(stale["source_run_guard"]["passed"])
        self.assertFalse(stale["allow_execute"])
        self.assertIn("n5_execute_source_run_guard", stale["blockers"])

    def test_canonical_20260529_source_is_allowlisted_by_default_resolution(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            outbox_rows=[
                sample_outbox_row(
                    source_run_id=CANONICAL_20260529_N4_SOURCE_RUN_ID,
                    trade_date="20260529",
                )
            ],
            trigger_run=canonical_20260529_trigger_run(),
            action_run_id=CANONICAL_20260529_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CANONICAL_20260529_N4_SOURCE_RUN_ID,
            expected_read_event_count=1,
        )

        self.assertTrue(contract["source_run_guard"]["passed"])
        self.assertTrue(contract["allow_execute"])
        self.assertEqual(contract["consumer_plan_summary"]["read_event_count"], 1)

    def test_canonical_20260529_source_guard_blocks_20260528_source_rows(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            outbox_rows=[
                sample_outbox_row(
                    source_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
                    trade_date="20260528",
                )
            ],
            trigger_run=canonical_20260529_trigger_run(),
            action_run_id=CANONICAL_20260529_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CANONICAL_20260529_N4_SOURCE_RUN_ID,
            expected_read_event_count=1,
        )

        self.assertFalse(contract["source_run_guard"]["passed"])
        self.assertFalse(contract["allow_execute"])
        self.assertIn("n5_execute_source_run_guard", contract["blockers"])

    def test_action_confirmation_metric_20260602_source_is_allowlisted_by_default_resolution(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            outbox_rows=[
                with_formal_trigger_periods(sample_outbox_row(
                    source_run_id=ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID,
                    trade_date="20260602",
                    source_action_confirmation_metric_id=6,
                    asset_kind="index",
                    identity_key="index:SH:000682",
                    signal_type="S_SELL",
                    direction="sell",
                    condition_key="SELL:Y,Q,M",
                    trigger_mark_candidate="30m_shrink",
                ), ["M"])
            ],
            trigger_run=action_confirmation_metric_20260602_trigger_run(),
            action_run_id=ACTION_CONFIRMATION_METRIC_20260602_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID,
            expected_read_event_count=1,
            action_confirmation_metric_facts={
                ("index", "6"): metric_fact(
                    asset_kind="index",
                    action_confirmation_metric_id=6,
                    identity_key="index:SH:000682",
                    signal_type="S_SELL",
                    sell_pass=True,
                )
            },
        )

        self.assertTrue(contract["source_run_guard"]["passed"])
        self.assertTrue(contract["allow_execute"])
        self.assertEqual(contract["planned_write_scope"]["index_action_fact"], 1)
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionExecuted"], 1)

    def test_metric_aware_reprocess_dedicated_consumer_is_allowed_when_declared(self) -> None:
        source_run_id = "trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry"
        consumer_name = "n5_action_consumer_v1_until_0952_metric_aware_reprocess"
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            consumer_name=consumer_name,
            outbox_rows=[
                sample_outbox_row(
                    source_run_id=source_run_id,
                    trade_date="20260608",
                    source_action_confirmation_metric_id=1,
                )
            ],
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260608"},
            source_trigger_run_id=source_run_id,
            action_run_id=f"action_consumer_metric_reprocess__{source_run_id}",
            allowed_source_run_ids=[source_run_id],
            expected_read_event_count=1,
            baseline_report=metric_reprocess_baseline(
                source_run_id=source_run_id,
                dedicated_consumer_name=consumer_name,
            ),
            action_confirmation_metric_facts={
                ("stock", "1"): metric_fact(
                    action_confirmation_metric_id=1,
                    identity_key="stock:SH:600000",
                    signal_type="B_BUY",
                    buy_pass=True,
                )
            },
        )

        self.assertTrue(contract["dry_run_plan"]["consumer_guard"]["passed"])
        self.assertNotIn("n5_execute_consumer_guard", contract["blockers"])
        self.assertTrue(contract["allow_execute"])

    def test_metric_aware_reprocess_arbitrary_consumer_is_blocked(self) -> None:
        source_run_id = "trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry"
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            consumer_name="n5_action_consumer_v1_unreviewed_replay",
            outbox_rows=[
                sample_outbox_row(
                    source_run_id=source_run_id,
                    trade_date="20260608",
                )
            ],
            trigger_run={"run_id": source_run_id, "for_trade_date": "20260608"},
            source_trigger_run_id=source_run_id,
            action_run_id=f"action_consumer_metric_reprocess__{source_run_id}",
            allowed_source_run_ids=[source_run_id],
            expected_read_event_count=1,
            baseline_report={},
        )

        self.assertFalse(contract["dry_run_plan"]["consumer_guard"]["passed"])
        self.assertIn("n5_execute_consumer_guard", contract["blockers"])
        self.assertFalse(contract["allow_execute"])

    def test_deterministic_metric_join_enriches_rows_without_payload_metric_id(self) -> None:
        source_run_id = "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1"
        action_run_id = (
            "action_consumer_market_action_confirmation_v1_20260603_"
            "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1"
        )
        metric_run_id = (
            "action_confirmation_projection_metric_20260603__"
            "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1"
        )
        rows = [
            sample_outbox_row(
                event_id="evt_metric_join",
                trigger_match_id=701,
                source_run_id=source_run_id,
                trade_date="20260603",
                source_action_confirmation_metric_id=None,
                identity_key="stock:SH:600000",
                signal_type="B_BUY",
                direction="buy",
            )
        ]
        metric_rows = [
            metric_fact(
                action_confirmation_metric_id=901,
                identity_key="stock:SH:600000",
                signal_type="B_BUY",
                projection_run_id=metric_run_id,
                for_trade_date="20260603",
                buy_pass=False,
            )
        ]
        metric_rows[0]["source_trigger_match_id"] = 701
        metric_rows[0]["source_trigger_event_id"] = "evt_metric_join"
        metric_rows[0]["direction"] = "buy"
        metric_rows[0]["condition_key"] = "BUY_HINT"
        metric_rows[0]["metric_time"] = "2026-06-03T10:47:00+08:00"

        joined = build_deterministic_action_metric_join(
            rows,
            metric_rows,
            metric_run_id=metric_run_id,
        )
        enriched_payload = joined["outbox_rows"][0]["payload_json"]
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            outbox_rows=joined["outbox_rows"],
            trigger_run={
                "run_id": source_run_id,
                "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
                "source_market_data_run_id": metric_run_id,
                "for_trade_date": "20260603",
            },
            action_run_id=action_run_id,
            source_trigger_run_id=source_run_id,
            allowed_source_run_ids=(source_run_id,),
            expected_read_event_count=1,
            action_confirmation_metric_facts=joined["action_confirmation_metric_facts"],
        )
        plan = build_executable_plan_from_rows(
            outbox_rows=joined["outbox_rows"],
            action_run_id=action_run_id,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
            action_confirmation_metric_facts=joined["action_confirmation_metric_facts"],
        )

        self.assertEqual(joined["summary"]["coverage"], "1/1")
        self.assertEqual(str(enriched_payload["source_action_confirmation_metric_id"]), "901")
        self.assertEqual(enriched_payload["metric_trace"]["join_policy"], "deterministic_v2_trigger_row_time_action_metric_run")
        self.assertEqual(enriched_payload["metric_trace"]["join_key"]["source_trigger_match_id"], "701")
        self.assertEqual(enriched_payload["metric_trace"]["join_key"]["trigger_time"], "2026-06-03T10:47:00+08:00")
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionBlocked"], 1)
        self.assertEqual(contract["dry_run_plan"]["sample_action_write_plan"][0]["blocked_reason"], "price_confirmation_failed")
        self.assertEqual(plan["action_write_plan"][0]["blocked_reason"], "price_confirmation_failed")
        self.assertEqual(plan["action_write_plan"][0]["source_action_confirmation_metric_id"], "901")
        self.assertNotEqual(plan["action_write_plan"][0]["blocked_reason"], "metric_missing")

    def test_deterministic_metric_join_uses_projection_closed_label_for_observed_snapshot_time(self) -> None:
        source_run_id = "n4_production_semantic_replay_20260615_market_snapshot_updated_until_1342"
        metric_run_id = "action_confirmation_projection_metric_20260615_until_1342_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1342_v1"
        action_run_id = "n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1342_v1"
        rows = [
            with_formal_trigger_periods(sample_outbox_row(
                event_id="evt_closed_label_metric_join",
                trigger_match_id=267857,
                source_run_id=source_run_id,
                trade_date="20260615",
                source_action_confirmation_metric_id=None,
                identity_key="stock:SZ:002716",
                signal_type="B_BUY",
                direction="buy",
                condition_key="BUY:Q,M,W",
            ), ["W"])
        ]
        rows[0]["event_time"] = "2026-06-15T13:47:20.755245+08:00"
        rows[0]["payload_json"]["trigger_time"] = "2026-06-15T13:47:20.755245+08:00"
        rows[0]["payload_json"]["projection_trace"] = {
            "closed_label_used": "2026-06-15T13:42:00+08:00",
            "source_fact_ids": {
                "closed_label_used": "2026-06-15T13:42:00+08:00",
            },
        }
        metric_rows = [
            metric_fact(
                action_confirmation_metric_id=134291,
                identity_key="stock:SZ:002716",
                signal_type="B_BUY",
                projection_run_id=metric_run_id,
                for_trade_date="20260615",
                buy_pass=True,
            )
        ]
        metric_rows[0]["source_trigger_match_id"] = 267857
        metric_rows[0]["source_trigger_event_id"] = "evt_closed_label_metric_join"
        metric_rows[0]["direction"] = "buy"
        metric_rows[0]["condition_key"] = "BUY:Q,M,W"
        metric_rows[0]["metric_time"] = "2026-06-15T13:42:00+08:00"

        joined = build_deterministic_action_metric_join(
            rows,
            metric_rows,
            metric_run_id=metric_run_id,
        )

        enriched_payload = joined["outbox_rows"][0]["payload_json"]
        self.assertEqual(joined["summary"]["coverage"], "1/1")
        self.assertEqual(str(enriched_payload["source_action_confirmation_metric_id"]), "134291")
        self.assertEqual(enriched_payload["metric_trace"]["join_key"]["trigger_time"], "2026-06-15T13:42:00+08:00")
        self.assertEqual(enriched_payload["metric_trace"]["join_key"]["metric_time"], "2026-06-15T13:42:00+08:00")

        plan = build_executable_plan_from_rows(
            outbox_rows=joined["outbox_rows"],
            action_run_id=action_run_id,
            consumer_name="n5_action_bounded_consumer_20260615_after_n3_metric_until_1342_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
            action_confirmation_metric_facts=joined["action_confirmation_metric_facts"],
        )
        action_row = plan["action_write_plan"][0]
        self.assertEqual(action_row["source_action_confirmation_metric_id"], "134291")
        self.assertNotEqual(action_row["blocked_reason"], "lineage_mismatch")
        self.assertEqual(action_row["action_state"], "executed")

    def test_bj_trigger_matched_without_action_metric_is_scope_excluded_not_metric_missing(self) -> None:
        source_run_id = "n4_production_semantic_replay_20260615_market_snapshot_updated_until_1342"
        metric_run_id = "action_confirmation_projection_metric_20260615_until_1342_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1342_v1"
        action_run_id = "n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1342_v1"
        rows = [
            with_formal_trigger_periods(sample_outbox_row(
                event_id="evt_bj_metric_scope_excluded",
                trigger_match_id=268087,
                source_run_id=source_run_id,
                trade_date="20260615",
                source_action_confirmation_metric_id=None,
                asset_kind="index",
                identity_key="index:BJ:899050",
                signal_type="S_SELL",
                direction="sell",
                condition_key="SELL:M,W",
            ), ["W"])
        ]
        rows[0]["event_time"] = "2026-06-15T13:47:20.755245+08:00"
        rows[0]["payload_json"]["trigger_time"] = "2026-06-15T13:47:20.755245+08:00"
        rows[0]["payload_json"]["projection_trace"] = {
            "closed_label_used": "2026-06-15T13:42:00+08:00",
            "source_fact_ids": {
                "closed_label_used": "2026-06-15T13:42:00+08:00",
            },
        }

        joined = build_deterministic_action_metric_join(
            rows,
            [],
            metric_run_id=metric_run_id,
        )
        plan = build_executable_plan_from_rows(
            outbox_rows=joined["outbox_rows"],
            action_run_id=action_run_id,
            consumer_name="n5_action_bounded_consumer_20260615_after_n3_metric_until_1342_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
            action_confirmation_metric_facts=joined["action_confirmation_metric_facts"],
        )

        action_row = plan["action_write_plan"][0]
        self.assertEqual(action_row["action_state"], "blocked")
        self.assertEqual(action_row["blocked_reason"], "metric_scope_excluded")
        self.assertNotEqual(action_row["blocked_reason"], "metric_missing")

    def test_combined_metric_inputs_infer_original_and_repair_runs(self) -> None:
        baseline = {
            "source_trigger_run_id": "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry",
            "metric_inputs": {
                "original_metric_run_id": "metric_original",
                "repair_metric_run_id": "metric_repair",
            },
        }

        self.assertEqual(
            infer_action_metric_run_ids_from_baseline(baseline),
            ("metric_original", "metric_repair"),
        )

    def test_deterministic_metric_join_uses_original_and_repair_metric_rows(self) -> None:
        source_run_id = "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry"
        original_run_id = "metric_original"
        repair_run_id = "metric_repair"
        rows = [
            sample_outbox_row(
                event_id="evt_original_metric",
                trigger_match_id=8001,
                source_run_id=source_run_id,
                trade_date="20260608",
                source_action_confirmation_metric_id=None,
                identity_key="stock:SH:600001",
                signal_type="B_BUY",
                direction="buy",
                condition_key="BUY:D",
            ),
            sample_outbox_row(
                event_id="evt_repair_metric",
                trigger_match_id=8002,
                source_run_id=source_run_id,
                trade_date="20260608",
                source_action_confirmation_metric_id=None,
                identity_key="board:TDX:881001",
                asset_kind="board",
                signal_type="S_SELL",
                direction="sell",
                condition_key="SELL:D",
            ),
        ]
        for row in rows:
            row["event_time"] = "2026-06-08T15:00:00+08:00"
            row["payload_json"]["trigger_time"] = "2026-06-08T15:00:00+08:00"
        metric_rows = [
            metric_fact(
                action_confirmation_metric_id=9001,
                identity_key="stock:SH:600001",
                signal_type="B_BUY",
                projection_run_id=original_run_id,
                for_trade_date="20260608",
                buy_pass=False,
            ),
            metric_fact(
                asset_kind="board",
                action_confirmation_metric_id=9002,
                identity_key="board:TDX:881001",
                signal_type="S_SELL",
                projection_run_id=repair_run_id,
                for_trade_date="20260608",
                sell_pass=False,
            ),
        ]
        metric_rows[0].update(
            {
                "source_trigger_match_id": 8001,
                "source_trigger_event_id": "evt_original_metric",
                "direction": "buy",
                "condition_key": "BUY:D",
                "metric_time": "2026-06-08T15:00:00+08:00",
            }
        )
        metric_rows[1].update(
            {
                "source_trigger_match_id": 8002,
                "source_trigger_event_id": "evt_repair_metric",
                "direction": "sell",
                "condition_key": "SELL:D",
                "metric_time": "2026-06-08T15:00:00+08:00",
            }
        )

        joined = build_deterministic_action_metric_join(
            rows,
            metric_rows,
            metric_run_id=",".join([original_run_id, repair_run_id]),
        )

        self.assertEqual(joined["summary"]["coverage"], "2/2")
        self.assertEqual(joined["summary"]["metric_rows"], 2)
        self.assertEqual(
            {row["payload_json"].get("source_action_confirmation_metric_id") for row in joined["outbox_rows"]},
            {"9001", "9002"},
        )

    def test_deterministic_metric_join_rejects_object_only_closeout_metric_for_early_trigger(self) -> None:
        source_run_id = "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry"
        metric_run_id = (
            "action_confirmation_metric_20260608_until_1500__"
            "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry"
        )
        rows = [
            sample_outbox_row(
                event_id="evt_early_trigger",
                trigger_match_id=12201,
                source_run_id=source_run_id,
                trade_date="20260608",
                source_action_confirmation_metric_id=None,
                identity_key="stock:SH:600000",
                signal_type="B_BUY",
                direction="buy",
                condition_key="BUY:D",
            )
        ]
        rows[0]["event_time"] = "2026-06-08T09:44:00+08:00"
        rows[0]["payload_json"]["trigger_time"] = "2026-06-08T09:44:00+08:00"
        metric_rows = [
            metric_fact(
                action_confirmation_metric_id=12291,
                identity_key="stock:SH:600000",
                signal_type="B_BUY",
                projection_run_id=metric_run_id,
                for_trade_date="20260608",
            )
        ]
        metric_rows[0]["direction"] = "buy"
        metric_rows[0]["condition_key"] = "BUY:D"
        metric_rows[0]["metric_time"] = "2026-06-08T15:00:00+08:00"
        metric_rows[0]["metric_minute_label"] = "15:00"

        joined = build_deterministic_action_metric_join(
            rows,
            metric_rows,
            metric_run_id=metric_run_id,
        )
        enriched_payload = joined["outbox_rows"][0]["payload_json"]

        self.assertEqual(joined["summary"]["join_policy"], "deterministic_v2_trigger_row_time_action_metric_run")
        self.assertEqual(joined["summary"]["coverage"], "0/1")
        self.assertEqual(joined["summary"]["missing_n4_rows"], 1)
        self.assertEqual(joined["summary"]["missing_sample"][0]["reason"], "metric_time_mismatch")
        self.assertNotIn("source_action_confirmation_metric_id", enriched_payload)

    def test_run_once_cli_defaults_to_latest_20260602_action_confirmation_metric_source(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.source_run_id, ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID)
        self.assertEqual(args.action_run_id, ACTION_CONFIRMATION_METRIC_20260602_N5_EXECUTE_ACTION_RUN_ID)
        self.assertEqual(args.expected_read_event_count, EXPECTED_ACTION_CONFIRMATION_METRIC_20260602_PENDING_EVENT_COUNT)

    def test_run_once_cli_accepts_source_trigger_run_id_and_report_path_aliases(self) -> None:
        args = build_parser().parse_args(
            [
                "--source-trigger-run-id",
                "trigger_alias_run",
                "--report-path",
                "docs/alias_report.json",
            ]
        )

        self.assertEqual(args.source_run_id, "trigger_alias_run")
        self.assertEqual(args.json_report_path, "docs/alias_report.json")

    def test_run_once_cli_preserves_source_run_id_and_json_report_path_compatibility(self) -> None:
        args = build_parser().parse_args(
            [
                "--source-run-id",
                "trigger_legacy_run",
                "--json-report-path",
                "docs/legacy_report.json",
            ]
        )

        self.assertEqual(args.source_run_id, "trigger_legacy_run")
        self.assertEqual(args.json_report_path, "docs/legacy_report.json")

    def test_pending_only_guard_rejects_non_pending_rows(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            trigger_run=trigger_run(),
            outbox_rows=[
                sample_outbox_row(event_id="evt_pending", status="pending"),
                sample_outbox_row(event_id="evt_delivered", status="delivered"),
            ],
            action_confirmation_metric_facts={
                ("stock", "101"): metric_fact(action_confirmation_metric_id=101, identity_key="stock:SH:600000"),
            },
        )

        self.assertFalse(contract["allow_execute"])
        self.assertEqual(contract["pending_only_guard"]["non_pending_count"], 1)
        self.assertIn("n5_execute_pending_only_guard", contract["blockers"])

    def test_execute_contract_maps_action_and_hint_events_without_risk_or_position(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            trigger_run=trigger_run(),
            outbox_rows=[
                sample_outbox_row(
                    event_id="evt_buy_vol",
                    trigger_match_id=101,
                    signal_type="B_BUY",
                    condition_key="BUY_HINT",
                    original_condition_key="BUY_HINT",
                    trigger_mark_candidate="30m_volume",
                    projection_30m_type="volume_up",
                    direction="buy",
                    identity_key="stock:SH:600000",
                    source_action_confirmation_metric_id=101,
                    action_confirmation={
                        "120m": "passed",
                        "30m": "passed",
                        "5m": "passed",
                        "1m": "passed",
                    },
                ),
                sample_outbox_row(
                    event_id="evt_buy_hint",
                    trigger_match_id=102,
                    signal_type="B_BUY",
                    condition_key="BUY_HINT",
                    original_condition_key="BUY_HINT",
                    direction="buy",
                    identity_key="stock:SH:600001",
                    action_confirmation_mode="deferred",
                ),
                sample_outbox_row(
                    event_id="evt_sell_hint",
                    trigger_match_id=103,
                    signal_type="S_SELL",
                    condition_key="SELL_HINT",
                    original_condition_key="SELL_HINT",
                    trigger_mark_candidate="30m_shrink",
                    projection_30m_type="shrink_down",
                    direction="sell",
                    identity_key="stock:SH:600002",
                    action_confirmation_mode="deferred",
                ),
                sample_outbox_row(
                    event_id="evt_pending",
                    event_type="TriggerPendingMarketData",
                    trigger_match_id=104,
                    signal_type="S_SELL",
                    condition_key="SELL_HINT",
                    original_condition_key="SELL_HINT",
                    direction="sell",
                    identity_key="stock:SH:600003",
                    source_event_type="MarketDataDelayed",
                    data_quality_status="delayed",
                ),
            ],
            action_confirmation_metric_facts={
                ("stock", "101"): metric_fact(action_confirmation_metric_id=101, identity_key="stock:SH:600000"),
            },
        )

        self.assertTrue(contract["allow_execute"])
        self.assertEqual(contract["planned_write_scope"]["stock_action_fact"], 3)
        self.assertEqual(contract["planned_write_scope"]["common_action_quality_item"], 1)
        self.assertEqual(contract["planned_write_scope"]["common_action_event"], 3)
        self.assertEqual(contract["planned_write_scope"]["common_event_outbox"], 3)
        self.assertEqual(contract["planned_write_scope"]["common_event_inbox"], 4)
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionExecuted"], 1)
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionEligible"], 2)
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionBlocked"], 0)
        self.assertEqual(contract["output_event_plan_summary"]["by_event_type"]["ActionSkipped"], 0)

    def test_execute_contract_excludes_position_user_voice_sim_mobile_trade_and_worker(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            trigger_run=trigger_run(),
            outbox_rows=[sample_outbox_row()],
        )

        self.assertEqual(contract["planned_write_scope"]["common_position_state"], 0)
        self.assertEqual(contract["planned_write_scope"]["common_position_event"], 0)
        self.assertFalse(contract["side_effects"]["position_state_written"])
        self.assertFalse(contract["side_effects"]["position_event_written"])
        self.assertFalse(contract["side_effects"]["sim_touched"])
        self.assertFalse(contract["side_effects"]["voice_touched"])
        self.assertFalse(contract["side_effects"]["mobile_touched"])
        self.assertFalse(contract["side_effects"]["n6_user_layer_touched"])
        self.assertFalse(contract["side_effects"]["real_trade_touched"])
        self.assertFalse(contract["side_effects"]["worker_started"])
        self.assertEqual(contract["runner_mode"], "run_once")

    def test_execute_contract_formats_action_blocked_as_market_action_not_confirmed(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            trigger_run=trigger_run(),
            outbox_rows=[
                sample_outbox_row(
                    event_id="evt_blocked_wording",
                    source_action_confirmation_metric_id=101,
                )
            ],
            action_confirmation_metric_facts={
                ("stock", "101"): metric_fact(
                    action_confirmation_metric_id=101,
                    identity_key="stock:SH:600000",
                    buy_pass=False,
                )
            },
        )

        text = format_execute_contract(contract)

        self.assertIn("ActionBlocked means market action not confirmed / 市场动作未确认", text)
        self.assertNotIn("交易失败", text)
        self.assertNotIn("trade failed", text.lower())

    def test_executable_plan_contains_full_consumer_and_action_rows(self) -> None:
        rows = [
            sample_outbox_row(event_id="evt_action", trigger_match_id=301),
            sample_outbox_row(
                event_id="evt_quality",
                event_type="TriggerPendingMarketData",
                trigger_match_id=302,
                source_event_type="MarketDataDelayed",
                data_quality_status="delayed",
            ),
        ]
        plan = build_executable_plan_from_rows(
            outbox_rows=rows,
            action_run_id=CURRENT_REAL_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )

        self.assertEqual(len(plan["consumer_plan"]["event_plans"]), 2)
        self.assertEqual(len(plan["action_write_plan"]), 2)
        self.assertEqual(plan["action_write_plan"][0]["plan_status"], "planned_action_fact")
        self.assertEqual(plan["action_write_plan"][1]["plan_status"], "quality_plan_only")
        self.assertIn("source_layer", plan["consumer_plan"]["event_plans"][0])
        self.assertIn("source_payload_json", plan["action_write_plan"][0])

    def test_execute_transaction_persists_status_from_execute_gate_not_stale_dry_run_quality(self) -> None:
        cursor = RecordingCursor()
        plan = {
            "action_run_id": CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            "consumer_name": "n5_action_consumer_v1",
            "source_trigger_run_id": CANONICAL_20260528_N4_SOURCE_RUN_ID,
            "consumer_plan": {"event_plans": [], "checkpoint_write_plan": []},
            "action_write_plan": [],
            "consumer_plan_summary": {"read_event_count": 1},
            "action_write_plan_summary": {"plan_row_count": 1, "planned_action_fact_count": 0},
            "output_event_plan_summary": {"planned_event_count": 0},
            "quality": {
                "p0_count": 1,
                "p1_count": 0,
                "p2_count": 0,
                "items": [{"severity": "P0", "status": "failed", "gate_code": "stale_baseline"}],
            },
            "execute_quality": {
                "p0_count": 0,
                "p1_count": 0,
                "p2_count": 0,
                "items": [{"severity": "P0", "status": "passed", "gate_code": "execute_gate_passed"}],
            },
        }

        execute_action_transaction(cursor, trigger_run=canonical_trigger_run(), plan=plan)

        update_calls = [call for call in cursor.calls if "UPDATE common_action_run" in call[0]]
        self.assertEqual(len(update_calls), 1)
        self.assertEqual(update_calls[0][1][:4], ("passed", 0, 0, 0))

    def test_trigger_state_changed_creates_no_action_fact_plan(self) -> None:
        rows = [
            sample_outbox_row(event_id="evt_action", trigger_match_id=301),
            sample_outbox_row(
                event_id="evt_state_live",
                event_type="TriggerStateChanged",
                trigger_match_id=302,
                trigger_live=True,
            ),
            sample_outbox_row(
                event_id="evt_state_inactive",
                event_type="TriggerStateChanged",
                trigger_match_id=303,
                trigger_live=False,
            ),
        ]
        plan = build_executable_plan_from_rows(
            outbox_rows=rows,
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )

        by_event = {row["source_trigger_event_id"]: row for row in plan["action_write_plan"]}
        self.assertEqual(by_event["evt_action"]["plan_status"], "planned_action_fact")
        self.assertEqual(by_event["evt_state_live"]["plan_status"], "state_gate_only")
        self.assertEqual(by_event["evt_state_inactive"]["plan_status"], "state_gate_only")
        self.assertFalse(by_event["evt_state_live"]["would_insert_action_fact"])
        self.assertFalse(by_event["evt_state_inactive"]["would_insert_action_fact"])

    def test_tracking_state_upsert_uses_run_state_key_conflict(self) -> None:
        cursor = RecordingCursor()
        plan = build_executable_plan_from_rows(
            outbox_rows=[
                sample_outbox_row(event_id="evt_tracking_first", trigger_match_id=451),
                sample_outbox_row(event_id="evt_tracking_second", trigger_match_id=452),
            ],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )

        affected = upsert_action_tracking_states(
            cursor,
            rows=plan["action_write_plan"],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
        )

        self.assertEqual(affected, 1)
        sql = cursor.calls[0][0].lower()
        self.assertIn("insert into common_action_tracking_state", sql)
        self.assertIn("on conflict (run_id, state_key)", sql)
        self.assertIn("when common_action_tracking_state.action_state = 'executed'", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("common_event_inbox", sql)

    def test_execute_transaction_reports_tracking_state_upsert_count(self) -> None:
        cursor = RecordingCursor()
        executable = build_executable_plan_from_rows(
            outbox_rows=[
                sample_outbox_row(event_id="evt_tracking_first", trigger_match_id=461),
                sample_outbox_row(event_id="evt_tracking_second", trigger_match_id=462),
            ],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )
        for row in executable["action_write_plan"]:
            row["trigger_kind"] = "hint"
            row["source_payload_json"] = {
                **row["source_payload_json"],
                "trigger_kind": "hint",
                "trigger_period": "30m",
                "triggered_periods": [],
                "all_trigger_periods": [],
                "primary_trigger_period": None,
            }
            row["source_market_trace"] = {
                "period_trigger_baseline_trace": {
                    "baseline_source": "trigger_baseline",
                    "traced_periods": {},
                }
            }
        plan = {
            "action_run_id": CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            "consumer_name": "n5_action_consumer_v1",
            "source_trigger_run_id": CANONICAL_20260528_N4_SOURCE_RUN_ID,
            "consumer_plan": {"event_plans": [], "checkpoint_write_plan": []},
            "action_write_plan": executable["action_write_plan"],
            "consumer_plan_summary": {"read_event_count": 2},
            "action_write_plan_summary": summarize_action_write_plan(executable["action_write_plan"]),
            "output_event_plan_summary": summarize_output_event_plan(executable["output_event_plan"]),
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
            "execute_quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
        }

        counts = execute_action_transaction(cursor, trigger_run=canonical_trigger_run(), plan=plan)

        self.assertEqual(counts["common_action_tracking_state"], 1)
        tracking_calls = [call for call in cursor.calls if "common_action_tracking_state" in call[0]]
        self.assertEqual(len(tracking_calls), 1)
        self.assertFalse(any("update common_event_outbox" in call[0].lower() for call in cursor.calls))

    def test_action_fact_insert_params_include_025_canonical_columns(self) -> None:
        cursor = RecordingCursor()
        row = build_executable_plan_from_rows(
            outbox_rows=[sample_outbox_row(event_id="evt_action", trigger_match_id=401)],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )["action_write_plan"][0]

        insert_action_fact(
            cursor,
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
            trigger_run=canonical_trigger_run(),
            row=row,
            table_name="stock_action_fact",
        )
        sql = cursor.calls[0][0]

        for column in (
            "source_trigger_state_id",
            "original_condition_key",
            "trigger_mark_candidate",
            "action_mark",
            "action_state",
            "confirmation_status",
            "tracking_until",
            "last_checked_minute_label",
            "trace_json",
            "action_policy",
        ):
            self.assertIn(column, sql)
        self.assertIn("ON CONFLICT (run_id, action_key) DO NOTHING", sql)
        self.assertNotIn("ON CONFLICT (run_id, source_trigger_event_id, action_type)", sql)

    def test_common_action_event_insert_params_include_025_canonical_columns(self) -> None:
        cursor = RecordingCursor()
        row = build_executable_plan_from_rows(
            outbox_rows=[sample_outbox_row(event_id="evt_action", trigger_match_id=402)],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )["action_write_plan"][0]

        insert_common_action_event(
            cursor,
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
            trigger_run=canonical_trigger_run(),
            row=row,
            action_fact_id=1,
            event_id="evt_n5_action",
            payload={"action_key": row["action_key"], "trace_json": row["trace_json"]},
        )
        sql = cursor.calls[0][0]

        for column in (
            "source_trigger_state_id",
            "original_condition_key",
            "trigger_mark_candidate",
            "action_mark",
            "action_state",
            "confirmation_status",
            "tracking_until",
            "last_checked_minute_label",
            "trace_json",
            "action_policy",
        ):
            self.assertIn(column, sql)

    def test_normalize_action_persistence_row_for_actionexecuted_repairs_eligible_shape(self) -> None:
        row = build_executable_plan_from_rows(
            outbox_rows=[sample_outbox_row(event_id="evt_actionexecuted_shape", trigger_match_id=403)],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )["action_write_plan"][0]
        row.update(
            {
                "planned_output_event_type": "ActionExecuted",
                "action_state": "eligible",
                "confirmation_status": "pending",
                "final_action_mark": "normal",
                "closed_minute_required": False,
                "closed_minute_verified": False,
                "minute_context_status": "not_required",
                "last_checked_minute_label": "14:47",
                "source_market_data_run_id": "selected_n3p_run",
            }
        )

        normalized = normalize_action_persistence_row(row)

        self.assertEqual(normalized["action_state"], "executed")
        self.assertEqual(normalized["confirmation_status"], "passed")
        self.assertEqual(normalized["final_action_mark"], "normal")
        self.assertEqual(normalized["action_policy"], "n5_confirmation_only")
        self.assertTrue(normalized["closed_minute_required"])
        self.assertTrue(normalized["closed_minute_verified"])
        self.assertEqual(normalized["minute_context_status"], "closed")
        self.assertEqual(normalized["last_checked_minute_label"], "14:47")
        self.assertEqual(normalized["source_market_data_run_id"], "selected_n3p_run")

    def test_insert_common_action_event_normalizes_actionexecuted_shape_before_persist(self) -> None:
        cursor = RecordingCursor()
        row = build_executable_plan_from_rows(
            outbox_rows=[sample_outbox_row(event_id="evt_actionexecuted_event", trigger_match_id=404)],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )["action_write_plan"][0]
        row.update(
            {
                "planned_output_event_type": "ActionExecuted",
                "action_state": "eligible",
                "confirmation_status": "pending",
                "final_action_mark": "normal",
                "closed_minute_required": False,
                "closed_minute_verified": False,
                "minute_context_status": "not_required",
                "last_checked_minute_label": "14:47",
                "source_market_data_run_id": "selected_n3p_run",
            }
        )

        insert_common_action_event(
            cursor,
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
            trigger_run=canonical_trigger_run(),
            row=row,
            action_fact_id=1,
            event_id="evt_n5_actionexecuted",
            payload={"source_action_fact_id": 1},
        )

        params = cursor.calls[0][1]
        self.assertEqual(params[21], "normal")
        self.assertEqual(params[22], "executed")
        self.assertEqual(params[23], "passed")
        self.assertEqual(params[27], "n5_confirmation_only")
        self.assertEqual(params[28], "ActionExecuted")

    def test_action_event_passthrough_payload_carries_n4_actual_trigger_facts(self) -> None:
        row = build_executable_plan_from_rows(
            outbox_rows=[sample_outbox_row(event_id="evt_passthrough", trigger_match_id=403)],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )["action_write_plan"][0]
        row["source_trigger_event_id"] = "evt_61bf1423e33a28d3e19c879c71a8d24a5241bc16"
        row["trigger_price"] = "43.73"
        row["trigger_period"] = "D"
        row["primary_trigger_period"] = "D"
        row["trigger_kind"] = "trigger"
        row["source_payload_json"] = {
            **row["source_payload_json"],
            "trigger_price": "43.73",
            "trigger_period": "D",
            "triggered_periods": ["D"],
            "all_trigger_periods": ["D"],
            "primary_trigger_period": "D",
            "trigger_kind": "trigger",
        }
        row["source_market_trace"] = {
            "period_trigger_baseline_trace": {
                "traced_periods": {
                    "D": {
                        "baseline_source": "trigger_baseline",
                    }
                }
            }
        }

        payload = build_action_event_passthrough_payload(
            row=row,
            table_name="stock_action_fact",
            action_fact_id=1,
        )

        self.assertEqual(payload["n4_trigger_event_id"], "evt_61bf1423e33a28d3e19c879c71a8d24a5241bc16")
        self.assertEqual(payload["trigger_price"], "43.73")
        self.assertEqual(payload["trigger_period"], "D")
        self.assertEqual(payload["triggered_periods"], ["D"])
        self.assertEqual(payload["all_trigger_periods"], ["D"])
        self.assertEqual(payload["primary_trigger_period"], "D")
        self.assertEqual(payload["trigger_kind"], "trigger")
        self.assertEqual(
            payload["period_trigger_baseline_trace"]["traced_periods"]["D"]["baseline_source"],
            "trigger_baseline",
        )
        self.assertEqual(payload["baseline_source"], "trigger_baseline")

    def test_action_event_passthrough_payload_preserves_buy_hint_30m_empty_formal_periods(self) -> None:
        row = build_hint_30m_action_row(condition_key="BUY_HINT", direction="buy", signal_type="B_BUY")

        payload = build_action_event_passthrough_payload(
            row=row,
            table_name="stock_action_fact",
            action_fact_id=1,
        )

        self.assertEqual(payload["trigger_period"], "30m")
        self.assertEqual(payload["triggered_periods"], [])
        self.assertEqual(payload["all_trigger_periods"], [])
        self.assertIsNone(payload["primary_trigger_period"])
        self.assertEqual(payload["trigger_kind"], "hint")
        self.assertEqual(payload["baseline_source"], "trigger_baseline")

    def test_action_event_passthrough_payload_preserves_sell_hint_30m_empty_formal_periods(self) -> None:
        row = build_hint_30m_action_row(condition_key="SELL_HINT", direction="sell", signal_type="S_SELL")

        payload = build_action_event_passthrough_payload(
            row=row,
            table_name="stock_action_fact",
            action_fact_id=1,
        )

        self.assertEqual(payload["trigger_period"], "30m")
        self.assertEqual(payload["triggered_periods"], [])
        self.assertEqual(payload["all_trigger_periods"], [])
        self.assertIsNone(payload["primary_trigger_period"])
        self.assertEqual(payload["trigger_kind"], "hint")
        self.assertEqual(payload["baseline_source"], "trigger_baseline")

    def test_action_event_passthrough_payload_does_not_infer_formal_periods_from_condition_key(self) -> None:
        row = build_executable_plan_from_rows(
            outbox_rows=[
                sample_outbox_row(
                    event_id="evt_ordinary_30m_marker",
                    trigger_match_id=812,
                    condition_key="BUY:M,W,D",
                    original_condition_key="BUY:M,W,D",
                    direction="buy",
                    signal_type="B_BUY",
                    trigger_mark_candidate="30m_volume",
                )
            ],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )["action_write_plan"][0]
        row["trigger_period"] = "30m"
        row["primary_trigger_period"] = "30m"
        row["trigger_kind"] = "trigger"
        row["source_payload_json"] = {
            **row["source_payload_json"],
            "trigger_price": "10.5",
            "trigger_period": "30m",
            "triggered_periods": [],
            "all_trigger_periods": ["30m"],
            "primary_trigger_period": "30m",
            "trigger_kind": "trigger",
            "condition_key": "BUY:M,W,D",
            "original_condition_key": "BUY:M,W,D",
        }
        row["source_market_trace"] = {
            "period_trigger_baseline_trace": {
                "required_periods": ["M", "W", "D"],
                "traced_periods": {"M": {}, "W": {}, "D": {}},
            }
        }

        payload = build_action_event_passthrough_payload(
            row=row,
            table_name="stock_action_fact",
            action_fact_id=1,
        )

        self.assertEqual(payload["trigger_period"], "30m")
        self.assertEqual(payload["triggered_periods"], [])
        self.assertEqual(payload["all_trigger_periods"], [])
        self.assertIsNone(payload["primary_trigger_period"])
        self.assertEqual(payload["trigger_kind"], "trigger")

    def test_action_event_passthrough_payload_does_not_infer_full_periods_from_trace_periods(self) -> None:
        row = build_executable_plan_from_rows(
            outbox_rows=[
                sample_outbox_row(
                    event_id="evt_full_30m_marker",
                    trigger_match_id=813,
                    condition_key="BUY:FULL",
                    original_condition_key="BUY:FULL",
                    direction="buy",
                    signal_type="B_BUY",
                    trigger_mark_candidate="30m_volume",
                )
            ],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
        )["action_write_plan"][0]
        row["trigger_period"] = "30m"
        row["primary_trigger_period"] = "30m"
        row["trigger_kind"] = "trigger"
        row["source_payload_json"] = {
            **row["source_payload_json"],
            "trigger_price": "10.5",
            "trigger_period": "30m",
            "all_trigger_periods": ["30m"],
            "primary_trigger_period": "30m",
            "trigger_kind": "trigger",
            "condition_key": "BUY:FULL",
            "original_condition_key": "BUY:FULL",
            "period_trigger_baseline_trace": {
                "required_periods": ["D"],
                "traced_periods": {"D": {"baseline_source": "trigger_baseline"}},
            },
        }
        row["source_market_trace"] = {
            "period_trigger_baseline_trace": row["source_payload_json"]["period_trigger_baseline_trace"]
        }

        payload = build_action_event_passthrough_payload(
            row=row,
            table_name="stock_action_fact",
            action_fact_id=1,
        )

        self.assertEqual(payload["trigger_period"], "30m")
        self.assertEqual(payload["triggered_periods"], [])
        self.assertEqual(payload["all_trigger_periods"], [])
        self.assertIsNone(payload["primary_trigger_period"])

    def test_ordinary_30m_marker_without_formal_period_proof_is_action_blocked(self) -> None:
        outbox_row = sample_outbox_row(
            event_id="evt_ordinary_30m_without_formal_proof",
            trigger_match_id=814,
            condition_key="BUY:M,W,D",
            original_condition_key="BUY:M,W,D",
            direction="buy",
            signal_type="B_BUY",
            trigger_mark_candidate="30m_volume",
            source_action_confirmation_metric_id=101,
        )
        payload = dict(outbox_row["payload_json"])
        payload.update(
            {
                "trigger_period": "30m",
                "triggered_periods": [],
                "all_trigger_periods": ["30m"],
                "primary_trigger_period": "30m",
                "trigger_kind": "trigger",
                "period_trigger_baseline_trace": {
                    "required_periods": ["M", "W", "D"],
                    "traced_periods": {"M": {}, "W": {}, "D": {}},
                },
            }
        )
        outbox_row["payload_json"] = payload

        plan = build_executable_plan_from_rows(
            outbox_rows=[outbox_row],
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=None,
            existing_checkpoints=None,
            action_confirmation_metric_facts=[
                metric_fact(action_confirmation_metric_id=101),
            ],
        )

        action_row = plan["action_write_plan"][0]
        self.assertEqual(action_row["planned_output_event_type"], "ActionBlocked")
        self.assertEqual(action_row["action_state"], "blocked")
        self.assertEqual(action_row["confirmation_status"], "failed")
        self.assertEqual(action_row["blocked_reason"], "n4_formal_trigger_period_missing")

    def test_build_n5_action_event_accepts_legal_hint_30m_passthrough(self) -> None:
        passthrough = build_action_event_passthrough_payload(
            row=build_hint_30m_action_row(condition_key="BUY_HINT", direction="buy", signal_type="B_BUY"),
            table_name="stock_action_fact",
            action_fact_id=1,
        )

        envelope = build_n5_action_event(
            event_type="ActionEligible",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260608",
            event_time=datetime.fromisoformat("2026-06-08T09:46:08+08:00"),
            action_run_id="action_run",
            source_trigger_event_id="evt_hint_30m",
            source_trigger_run_id="trigger_run",
            source_trigger_match_id=1,
            source_trigger_state_id=1001,
            source_condition_run_id="condition_run",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_HINT",
            original_condition_key="BUY_HINT",
            trigger_period="30m",
            data_quality_status="passed",
            action_state="eligible",
            confirmation_status="pending",
            payload=passthrough,
        )

        self.assertEqual(envelope.payload_json["trigger_period"], "30m")
        self.assertEqual(envelope.payload_json["triggered_periods"], [])
        self.assertEqual(envelope.payload_json["all_trigger_periods"], [])
        self.assertIsNone(envelope.payload_json["primary_trigger_period"])

    def test_build_n5_action_event_payload_is_json_safe_for_metric_datetime_trace(self) -> None:
        metric_time = datetime.fromisoformat("2026-06-08T09:43:00+08:00")
        passthrough = build_action_event_passthrough_payload(
            row=build_hint_30m_action_row(condition_key="BUY_HINT", direction="buy", signal_type="B_BUY"),
            table_name="stock_action_fact",
            action_fact_id=1,
        )
        passthrough["metric_trace"] = {"metric_time": metric_time}

        envelope = build_n5_action_event(
            event_type="ActionExecuted",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260608",
            event_time=metric_time,
            action_run_id="action_run",
            source_trigger_event_id="evt_metric_datetime",
            source_trigger_run_id="trigger_run",
            source_trigger_match_id=1,
            source_trigger_state_id=1001,
            source_condition_run_id="condition_run",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_HINT",
            original_condition_key="BUY_HINT",
            trigger_period="30m",
            action_mark="30m_volume",
            action_state="executed",
            confirmation_status="passed",
            data_quality_status="passed",
            trace_json={"metric_trace": {"metric_time": metric_time}},
            source_market_trace={"metric_time": metric_time},
            payload=passthrough,
        )

        json.dumps(envelope.payload_json)
        self.assertEqual(envelope.payload_json["metric_trace"]["metric_time"], metric_time.isoformat())
        self.assertEqual(envelope.payload_json["source_market_trace"]["metric_time"], metric_time.isoformat())
        self.assertEqual(
            envelope.payload_json["trace_json"]["metric_trace"]["metric_time"],
            metric_time.isoformat(),
        )

    def test_n5_action_event_dedup_uses_action_key_for_multi_action_grain(self) -> None:
        base_payload = legal_passthrough_payload(
            trigger_kind="trigger",
            condition_key="BUY:M",
            original_condition_key="BUY:M",
            trigger_period="M",
            triggered_periods=["M"],
            all_trigger_periods=["M"],
            primary_trigger_period="M",
        )
        first_payload = {**base_payload, "action_key": "grain-selected-metric-338343"}
        second_payload = {**base_payload, "action_key": "grain-selected-metric-338345"}

        first = build_n5_action_event(
            event_type="ActionExecuted",
            asset_kind="index",
            identity_key="index:SH:000300",
            trade_date="20260622",
            event_time=datetime.fromisoformat("2026-06-22T14:01:00+08:00"),
            action_run_id="action_run",
            source_trigger_event_id="evt_000300_m",
            source_trigger_run_id="trigger_run",
            source_trigger_match_id=436642,
            source_trigger_state_id=436700,
            source_condition_run_id="condition_run",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY:M",
            original_condition_key="BUY:M",
            trigger_period="M",
            action_mark="normal",
            action_state="executed",
            confirmation_status="passed",
            data_quality_status="passed",
            payload=first_payload,
        )
        second = build_n5_action_event(
            event_type="ActionExecuted",
            asset_kind="index",
            identity_key="index:SH:000300",
            trade_date="20260622",
            event_time=datetime.fromisoformat("2026-06-22T14:03:00+08:00"),
            action_run_id="action_run",
            source_trigger_event_id="evt_000300_m",
            source_trigger_run_id="trigger_run",
            source_trigger_match_id=436642,
            source_trigger_state_id=436700,
            source_condition_run_id="condition_run",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY:M",
            original_condition_key="BUY:M",
            trigger_period="M",
            action_mark="normal",
            action_state="executed",
            confirmation_status="passed",
            data_quality_status="passed",
            payload=second_payload,
        )

        self.assertNotEqual(first.event_id, second.event_id)
        self.assertNotEqual(first.dedup_key, second.dedup_key)
        self.assertIn("grain-selected-metric-338343", first.dedup_key)
        self.assertIn("grain-selected-metric-338345", second.dedup_key)

    def test_build_n5_action_event_rejects_ordinary_trigger_period_30m(self) -> None:
        payload = legal_passthrough_payload(
            trigger_kind="trigger",
            condition_key="BUY:D",
            original_condition_key="BUY:D",
            trigger_period="30m",
            triggered_periods=["D"],
            all_trigger_periods=["D"],
            primary_trigger_period="D",
        )

        with self.assertRaisesRegex(EventContractError, "ordinary trigger fact passthrough must not use trigger_period=30m"):
            build_n5_action_event(
                event_type="ActionEligible",
                asset_kind="stock",
                identity_key="stock:SH:600000",
                trade_date="20260608",
                event_time=datetime.fromisoformat("2026-06-08T09:46:08+08:00"),
                action_run_id="action_run",
                source_trigger_event_id="evt_ordinary_30m",
                source_trigger_run_id="trigger_run",
                source_trigger_match_id=1,
                source_trigger_state_id=1001,
                source_condition_run_id="condition_run",
                direction="buy",
                signal_type="B_BUY",
                condition_key="BUY:D",
                original_condition_key="BUY:D",
                trigger_period="30m",
                data_quality_status="passed",
                action_state="eligible",
                confirmation_status="pending",
                payload=payload,
            )

    def test_build_n5_action_event_rejects_30m_inside_formal_period_fields(self) -> None:
        cases = [
            {"triggered_periods": ["30m"], "all_trigger_periods": [], "primary_trigger_period": None},
            {"triggered_periods": [], "all_trigger_periods": ["30m"], "primary_trigger_period": None},
            {"triggered_periods": [], "all_trigger_periods": [], "primary_trigger_period": "30m"},
        ]
        for override in cases:
            with self.subTest(override=override):
                payload = legal_passthrough_payload(
                    trigger_kind="hint",
                    condition_key="BUY_HINT",
                    original_condition_key="BUY_HINT",
                    trigger_period="30m",
                    **override,
                )
                with self.assertRaisesRegex(EventContractError, "must not include 30m"):
                    build_n5_action_event(
                        event_type="ActionEligible",
                        asset_kind="stock",
                        identity_key="stock:SH:600000",
                        trade_date="20260608",
                        event_time=datetime.fromisoformat("2026-06-08T09:46:08+08:00"),
                        action_run_id="action_run",
                        source_trigger_event_id="evt_bad_formal",
                        source_trigger_run_id="trigger_run",
                        source_trigger_match_id=1,
                        source_trigger_state_id=1001,
                        source_condition_run_id="condition_run",
                        direction="buy",
                        signal_type="B_BUY",
                        condition_key="BUY_HINT",
                        original_condition_key="BUY_HINT",
                        trigger_period="30m",
                        data_quality_status="passed",
                        action_state="eligible",
                        confirmation_status="pending",
                        payload=payload,
                    )

    def test_trigger_pending_market_data_remains_quality_only_no_action_event(self) -> None:
        contract = build_current_real_execute_contract_from_rows(
            execute=True,
            user_confirmed=True,
            trigger_run=canonical_trigger_run(),
            source_trigger_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
            action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
            outbox_rows=[
                sample_outbox_row(
                    event_id="evt_pending_quality_only",
                    event_type="TriggerPendingMarketData",
                    trigger_match_id=900,
                    source_run_id=CANONICAL_20260528_N4_SOURCE_RUN_ID,
                    data_quality_status="missing",
                )
            ],
            expected_read_event_count=1,
        )

        self.assertEqual(contract["planned_write_scope"]["stock_action_fact"], 0)
        self.assertEqual(contract["planned_write_scope"]["common_action_event"], 0)
        self.assertEqual(contract["planned_write_scope"]["common_event_outbox"], 0)
        self.assertEqual(contract["planned_write_scope"]["common_action_quality_item"], 1)
        self.assertEqual(contract["output_event_plan_summary"]["planned_event_count"], 0)

    def test_action_pipeline_execute_contract_baseline_is_not_treated_as_stale_n5_1_baseline(self) -> None:
        comparison = compare_baseline_report(
            current_consumer_summary={"read_event_count": 605},
            current_outbox_summary={
                "by_event_type": {"TriggerMatched": 605},
                "by_signal_type": {"B_BUY": 573, "S_SELL": 32},
            },
            trigger_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            baseline_report={
                "stage": "N5_ACTION_PIPELINE_EXECUTE_CONTRACT_GATE",
                "source_trigger_run_id": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
                "input_universe": {"n4_eligible_trigger_matched": 605},
                "dry_run_expectation": {
                    "input_universe": 605,
                    "signal_type_distribution": {"B_BUY": 573, "S_SELL": 32},
                },
            },
            baseline_report_path="docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.json",
        )

        self.assertTrue(comparison["explainable"])
        self.assertEqual(comparison["baseline_kind"], "N5_action_pipeline_execute_contract")
        self.assertEqual(comparison["baseline_read_event_count"], 605)
        self.assertEqual(comparison["read_event_count_delta"], 0)

    def test_planned_write_scope_splits_checkpoint_plan_entries_from_watermark_rows(self) -> None:
        scope = build_planned_write_scope(
            {
                "consumer_plan_summary": {
                    "read_event_count": 605,
                    "would_insert_inbox_count": 605,
                    "checkpoint_write_plan_count": 605,
                    "accepted_partition_count": 605,
                },
                "action_write_plan_summary": {
                    "quality_plan_only_count": 0,
                    "by_target_action_fact_table": {"stock_action_fact": 572, "board_action_fact": 33},
                    "would_insert_common_action_event_count": 605,
                },
                "output_event_plan_summary": {"planned_event_count": 605},
            }
        )

        self.assertEqual(scope["common_event_inbox"], 605)
        self.assertEqual(scope["accepted_event_count"], 605)
        self.assertEqual(scope["checkpoint_plan_entry_count"], 605)
        self.assertEqual(scope["common_event_consumer_checkpoint"], 605)
        self.assertEqual(scope["checkpoint_physical_watermark_rows"], 605)

    def test_upsert_checkpoints_returns_physical_affected_rowcount_when_available(self) -> None:
        cursor = RecordingCursor()
        cursor.rowcount = 73

        checkpoint_count = upsert_checkpoints(
            cursor,
            rows=[
                {
                    "partition_key": f"stock:SH:{i:06d}",
                    "last_event_id": f"evt_{i}",
                    "last_event_time": "2026-06-05T10:00:00+08:00",
                    "last_outbox_id": i,
                    "checkpoint_payload": {"stage": "N5-1"},
                }
                for i in range(605)
            ],
            consumer_name="n5_action_consumer_v1",
            action_run_id="action_run",
        )

        self.assertEqual(checkpoint_count, 73)

    def test_rollback_scope_is_action_run_and_source_run_only(self) -> None:
        sql = build_current_real_rollback_sql(
            action_run_id=CURRENT_REAL_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CURRENT_REAL_N4_SOURCE_RUN_ID,
            consumer_name="n5_action_consumer_v1",
        )
        lowered = sql.lower()

        self.assertIn("source_run_id = :'action_run_id'", lowered)
        self.assertIn("source_run_id = :'source_trigger_run_id'", lowered)
        self.assertIn("delete from common_event_inbox", lowered)
        self.assertIn("delete from common_event_consumer_checkpoint", lowered)
        self.assertIn("delete from common_action_run", lowered)
        self.assertNotIn("delete from common_trigger", lowered)
        self.assertNotIn("delete from stock_realtime_daily_snapshot", lowered)
        self.assertNotIn("delete from user_", lowered)
        self.assertNotIn("delete from voice_", lowered)
        self.assertNotIn("delete from sim_", lowered)

    def test_rollback_sql_hard_fails_before_deletes_when_downstream_refs_exist(self) -> None:
        sql = build_current_real_rollback_sql(
            action_run_id=ACTION_CONFIRMATION_METRIC_20260602_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID,
            consumer_name="n5_action_consumer_v1",
        )
        lowered = sql.lower()
        first_delete = lowered.index("delete from")
        hard_fail = lowered.index("raise exception")

        self.assertLess(hard_fail, first_delete)
        self.assertIn("do $$", lowered)
        self.assertIn("rollback blocked", lowered)
        self.assertIn("status in ('delivering', 'delivered')", lowered)
        self.assertIn("common_event_inbox", lowered)
        self.assertIn("common_event_consumer_checkpoint", lowered)
        self.assertIn("consumer_name <> v_consumer_name", lowered)
        self.assertIn("source_layer = 'n5_action'", lowered)
        self.assertIn("user_signal_projection", lowered)
        self.assertIn("user_notification_queue", lowered)
        self.assertIn("user_signal_decision", lowered)
        self.assertIn("user_card_projection", lowered)
        self.assertIn("user_voice_delivery", lowered)
        self.assertIn("sim_projection", lowered)
        self.assertIn("common_position_state", lowered)
        self.assertIn("common_position_event", lowered)
        self.assertIn("to_regclass", lowered)

    def test_20260603_rollback_artifact_is_materialized_with_hard_fail_guards(self) -> None:
        path = Path("sql/N5_20260603_canonical_action_execute_rollback.sql")

        self.assertTrue(path.exists())
        lowered = path.read_text().lower()
        first_delete = lowered.index("delete from")
        hard_fail = lowered.index("raise exception")

        self.assertLess(hard_fail, first_delete)
        self.assertIn("do $$", lowered)
        self.assertIn("rollback blocked", lowered)
        self.assertIn("action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1", lowered)
        self.assertIn("trigger_execute_20260603_condition_layer_20260602_source_20260602_v1", lowered)
        self.assertIn("status in ('delivering', 'delivered')", lowered)
        self.assertIn("downstream inbox refs", lowered)
        self.assertIn("downstream checkpoint refs", lowered)
        self.assertIn("non-scoped consumer", lowered)
        self.assertIn("user_signal_projection", lowered)
        self.assertIn("common_position_state", lowered)
        self.assertNotIn("delete from common_trigger", lowered)
        self.assertNotIn("delete from common_event_delivery_attempt", lowered)
        self.assertNotIn("delete from common_event_ledger", lowered)
        self.assertNotIn("delete from user_", lowered)
        self.assertNotIn("delete from voice_", lowered)
        self.assertNotIn("delete from sim_", lowered)


def trigger_run() -> dict[str, object]:
    return {
        "run_id": CURRENT_REAL_N4_SOURCE_RUN_ID,
        "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
        "source_market_data_run_id": "realtime_projection_metric_20260525",
        "for_trade_date": "20260525",
    }


def canonical_trigger_run() -> dict[str, object]:
    return {
        "run_id": CANONICAL_20260528_N4_SOURCE_RUN_ID,
        "source_condition_run_id": "condition_layer_20260527_source_20260527_v2",
        "source_market_data_run_id": "market_projection_20260528",
        "for_trade_date": "20260528",
    }


def canonical_20260529_trigger_run() -> dict[str, object]:
    return {
        "run_id": CANONICAL_20260529_N4_SOURCE_RUN_ID,
        "source_condition_run_id": "condition_layer_20260528_source_20260528_v1",
        "source_market_data_run_id": "realtime_snapshot_20260529_live1",
        "for_trade_date": "20260529",
    }


def action_confirmation_metric_20260602_trigger_run() -> dict[str, object]:
    return {
        "run_id": ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID,
        "source_condition_run_id": "condition_layer_20260601_source_20260601_v1",
        "source_market_data_run_id": "action_confirmation_projection_metric_20260602_1105__snapshot",
        "for_trade_date": "20260602",
    }


def build_hint_30m_action_row(*, condition_key: str, direction: str, signal_type: str) -> dict[str, object]:
    row = build_executable_plan_from_rows(
        outbox_rows=[
            sample_outbox_row(
                event_id=f"evt_{condition_key.lower()}_30m",
                trigger_match_id=808,
                condition_key=condition_key,
                original_condition_key=condition_key,
                direction=direction,
                signal_type=signal_type,
                trigger_mark_candidate="30m_volume" if direction == "buy" else "30m_shrink",
            )
        ],
        action_run_id=CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
        consumer_name="n5_action_consumer_v1",
        existing_inbox_keys=None,
        existing_checkpoints=None,
    )["action_write_plan"][0]
    row["trigger_period"] = "30m"
    row["primary_trigger_period"] = None
    row["trigger_kind"] = "hint"
    row["source_payload_json"] = {
        **row["source_payload_json"],
        "trigger_price": "10.5",
        "trigger_period": "30m",
        "triggered_periods": [],
        "all_trigger_periods": [],
        "primary_trigger_period": None,
        "trigger_kind": "hint",
        "condition_key": condition_key,
        "original_condition_key": condition_key,
    }
    row["source_market_trace"] = {
        "period_trigger_baseline_trace": {
            "baseline_source": "trigger_baseline",
            "traced_periods": {},
        }
    }
    return row


def legal_passthrough_payload(
    *,
    trigger_kind: str,
    condition_key: str,
    original_condition_key: str,
    trigger_period: str,
    triggered_periods: list[str],
    all_trigger_periods: list[str],
    primary_trigger_period: str | None,
) -> dict[str, object]:
    return {
        "source_action_fact_table": "stock_action_fact",
        "source_action_fact_id": 1,
        "action_key": "action_key",
        "blocked_reason": None,
        "n4_trigger_event_id": "evt_trigger",
        "trigger_price": "10.5",
        "trigger_period": trigger_period,
        "triggered_periods": triggered_periods,
        "all_trigger_periods": all_trigger_periods,
        "primary_trigger_period": primary_trigger_period,
        "trigger_kind": trigger_kind,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key,
        "period_trigger_baseline_trace": {
            "baseline_source": "trigger_baseline",
            "traced_periods": {},
        },
        "baseline_source": "trigger_baseline",
    }


def sample_outbox_row(
    *,
    event_id: str = "evt_trigger",
    event_type: str = "TriggerMatched",
    trigger_match_id: int = 100,
    signal_type: str = "B_BUY",
    condition_key: str = "BUY_HINT",
    original_condition_key: str | None = None,
    direction: str = "buy",
    source_event_type: str = "MarketSnapshotUpdated",
    data_quality_status: str = "passed",
    asset_kind: str = "stock",
    identity_key: str = "stock:SH:600000",
    source_run_id: str = CANONICAL_20260528_N4_SOURCE_RUN_ID,
    status: str = "pending",
    trigger_mark_candidate: str = "normal",
    projection_30m_type: str = "none",
    action_confirmation: dict[str, str] | None = None,
    source_action_confirmation_metric_id: int | None = None,
    action_confirmation_mode: str | None = None,
    trigger_live: bool | None = None,
    trade_date: str = "20260528",
) -> dict[str, object]:
    event_time_by_date = {
        "20260603": "2026-06-03T10:47:00+08:00",
        "20260602": "2026-06-02T11:05:00+08:00",
        "20260529": "2026-05-29T14:11:00+08:00",
        "20260528": "2026-05-28T14:11:00+08:00",
    }
    event_time = event_time_by_date.get(trade_date, "2026-05-25T14:11:00+08:00")
    payload = {
        "run_id": source_run_id,
        "source_event_id": f"source_{event_id}",
        "source_event_type": source_event_type,
        "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
        "source_market_data_run_id": "realtime_projection_metric_20260525",
        "source_trigger_match_id": trigger_match_id,
        "trigger_match_id": trigger_match_id,
        "trigger_state_id": trigger_match_id + 1000,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key or condition_key,
        "trigger_mark_candidate": trigger_mark_candidate,
        "projection_30m_flag": projection_30m_type != "none",
        "projection_30m_type": projection_30m_type,
        "trigger_live": event_type == "TriggerMatched" if trigger_live is None else trigger_live,
        "trigger_period": "30m",
        "trigger_time": event_time,
        "trigger_price": "10.5",
        "data_quality_status": data_quality_status,
        "period_trigger_baseline_trace": {
            "present": True,
            "baseline_version": "N2-R4-period-trigger-baseline-v1",
        },
        "projection_trace": {"projection_schema_version": "n3.realtime_projection.v1"},
    }
    if action_confirmation is not None:
        payload["action_confirmation"] = action_confirmation
    if source_action_confirmation_metric_id is not None:
        payload["source_action_confirmation_metric_id"] = source_action_confirmation_metric_id
        payload["source_projection_run_id"] = "action_confirmation_projection_metric_test"
    if action_confirmation_mode is not None:
        payload["action_confirmation_mode"] = action_confirmation_mode
    return {
        "outbox_id": trigger_match_id,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "v1",
        "trade_date": trade_date,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "event_time": event_time,
        "source_layer": "N4_trigger",
        "source_run_id": source_run_id,
        "dedup_key": f"dedup_{event_id}",
        "partition_key": identity_key,
        "payload_json": payload,
        "status": status,
        "created_at": "2026-05-25T14:11:01+08:00",
    }


def with_formal_trigger_periods(row: dict[str, object], periods: list[str]) -> dict[str, object]:
    payload = dict(row["payload_json"])
    primary = periods[0] if periods else None
    payload["trigger_period"] = primary
    payload["triggered_periods"] = list(periods)
    payload["all_trigger_periods"] = list(periods)
    payload["primary_trigger_period"] = primary
    payload["trigger_kind"] = "trigger"
    row["payload_json"] = payload
    return row


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> None:
        self.calls.append((sql, params))

    def executemany(self, sql: str, values: object) -> None:
        self.calls.append((sql, values))

    def fetchone(self) -> dict[str, object]:
        return {"action_fact_id": 1, "event_id": "evt_inserted"}


class FetchRowsRecordingCursor(RecordingCursor):
    def fetchall(self) -> list[dict[str, object]]:
        return []


class DirectMetricCursor(RecordingCursor):
    def __init__(self) -> None:
        super().__init__()
        self._rows: list[dict[str, object]] = []

    def execute(self, sql: str, params: object = None) -> None:
        lowered = sql.lower()
        if "projection_run_id = any" in lowered and "action_confirmation_metric_id = any" not in lowered:
            raise AssertionError("direct metric id path should not query the full metric run")
        super().execute(sql, params)
        if "action_confirmation_metric_id = any" in lowered:
            metric_ids = {str(item) for item in (params or ([],))[0]}
            run_ids = None
            if params is not None and len(params) > 1:
                run_ids = {str(item) for item in params[1]}
            rows = [
                {
                    "action_confirmation_metric_id": 101,
                    "projection_run_id": "direct_metric_run",
                    "for_trade_date": "20260608",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "signal_type": "B_BUY",
                    "condition_key": "BUY:D",
                    "metric_time": "2026-06-08T09:31:00+08:00",
                    "all_periods_pass": True,
                }
            ]
            self._rows = [
                row
                for row in rows
                if str(row["action_confirmation_metric_id"]) in metric_ids
                and (run_ids is None or str(row["projection_run_id"]) in run_ids)
            ]
        else:
            self._rows = []

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class LiveWindowMetricCursor(DirectMetricCursor):
    def execute(self, sql: str, params: object = None) -> None:
        lowered = sql.lower()
        RecordingCursor.execute(self, sql, params)
        if "action_confirmation_metric_id = any" in lowered:
            metric_ids = {str(item) for item in (params or ([],))[0]}
            self._rows = [
                row for row in self._metric_rows()
                if str(row["action_confirmation_metric_id"]) in metric_ids
            ]
            return
        if "projection_run_id = any" in lowered and "identity_key = any" in lowered:
            if "%s is null or" in lowered:
                raise AssertionError("live-window query must not use an untyped null guard")
            if "metric_time >= %s::timestamptz" not in lowered:
                raise AssertionError("live-window query must type-cast min trigger time")
            if params is None or len(params) != 3:
                raise AssertionError("live-window query must pass min trigger time once")
            run_ids = {str(item) for item in (params or ([],))[0]}
            identities = {str(item) for item in (params or ([], []))[1]}
            self._rows = [
                row for row in self._metric_rows()
                if str(row["projection_run_id"]) in run_ids
                and str(row["identity_key"]) in identities
            ]
            return
        if "projection_run_id = any" in lowered:
            raise AssertionError("live-window path must not query the full metric run")
        self._rows = []

    def _metric_rows(self) -> list[dict[str, object]]:
        return [
            {
                "action_confirmation_metric_id": 101,
                "projection_run_id": "direct_metric_run",
                "for_trade_date": "20260608",
                "trade_date": "20260608",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:D",
                "metric_time": "2026-06-08T09:31:00+08:00",
                "metric_ready": True,
                "metric_quality_status": "passed",
            },
            {
                "action_confirmation_metric_id": 102,
                "projection_run_id": "direct_metric_run",
                "for_trade_date": "20260608",
                "trade_date": "20260608",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:D",
                "metric_time": "2026-06-08T09:32:00+08:00",
                "metric_ready": True,
                "metric_quality_status": "passed",
            },
            {
                "action_confirmation_metric_id": 999,
                "projection_run_id": "direct_metric_run",
                "for_trade_date": "20260608",
                "trade_date": "20260608",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600001",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:D",
                "metric_time": "2026-06-08T09:32:00+08:00",
                "metric_ready": True,
                "metric_quality_status": "passed",
            },
        ]


def metric_reprocess_baseline(
    *,
    source_run_id: str,
    dedicated_consumer_name: str,
    metric_run_id: str = "action_confirmation_metric_20260608_until_0952",
) -> dict[str, object]:
    return {
        "source_trigger_run_id": source_run_id,
        "n3_action_metric_run_id": metric_run_id,
        "consumer_strategy": {
            "uses_dedicated_consumer": True,
            "dedicated_consumer_name": dedicated_consumer_name,
        },
    }


def metric_fact(
    *,
    asset_kind: str = "stock",
    action_confirmation_metric_id: int = 101,
    identity_key: str = "stock:SH:600000",
    signal_type: str = "B_BUY",
    buy_pass: bool = True,
    sell_pass: bool = True,
    projection_run_id: str = "action_confirmation_projection_metric_test",
    for_trade_date: str = "20260528",
) -> dict[str, object]:
    return {
        "asset_kind": asset_kind,
        "action_confirmation_metric_id": action_confirmation_metric_id,
        "projection_run_id": projection_run_id,
        "for_trade_date": for_trade_date,
        "trade_date": for_trade_date,
        "identity_key": identity_key,
        "signal_type": signal_type,
        "metric_ready": True,
        "metric_quality_status": "passed",
        "metric_minute_label": "11:05",
        "buy_120m_price_pass": buy_pass,
        "buy_30m_price_pass": buy_pass,
        "buy_5m_price_pass": buy_pass,
        "buy_5m_amount_pass": buy_pass,
        "buy_1m_price_pass": buy_pass,
        "buy_1m_amount_pass": buy_pass,
        "sell_120m_price_pass": sell_pass,
        "sell_30m_price_pass": sell_pass,
        "sell_5m_price_pass": sell_pass,
        "sell_5m_amount_pass": sell_pass,
        "sell_1m_price_pass": sell_pass,
        "sell_1m_amount_pass": sell_pass,
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "virtual_amount_policy_version": "previous_day_same_window_elapsed_ratio_v1",
        "previous_day_same_window_amount": "100",
        "current_30m_virtual_amount": "120" if signal_type == "B_BUY" else "80",
    }
