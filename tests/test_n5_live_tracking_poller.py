import inspect
import json
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ashare_v3.action import execute as action_execute
from ashare_v3.action import live_tracking_poller as poller
import run_n5_live_tracking_poller_once as poller_script


TRADE_DATE = "20260702"
ACTION_RUN_ID = "n5-live-action-run"
SOURCE_TRIGGER_RUN_ID = "n4-trigger-run"
SOURCE_METRIC_RUN_ID = "n3-metric-run"
CONSUMER_NAME = "n5-live-consumer"


def trigger_matched(
    event_id="n4-match-1",
    *,
    identity_key="stock:SH:600000",
    condition_key="BUY_MAIN",
    signal_type="B_BUY",
    direction="buy",
    event_time="2026-07-02T10:00:00+08:00",
    status="pending",
):
    return {
        "event_id": event_id,
        "event_type": "TriggerMatched",
        "trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": identity_key,
        "event_time": event_time,
        "source_layer": "N4_trigger",
        "source_run_id": SOURCE_TRIGGER_RUN_ID,
        "dedup_key": f"n4:{event_id}",
        "partition_key": identity_key,
        "status": status,
        "payload_json": {
            "trade_date": TRADE_DATE,
            "asset_kind": "stock",
            "identity_key": identity_key,
            "direction": direction,
            "signal_type": signal_type,
            "condition_key": condition_key,
            "trigger_live": True,
            "current_status": "matched",
            "trigger_state_id": 101,
            "trigger_match_id": 201,
            "primary_trigger_period": "D",
            "all_trigger_periods": ["D"],
        },
    }


def trigger_state_changed_false(match_row, event_id="n4-state-false-1"):
    payload = dict(match_row["payload_json"])
    payload["trigger_live"] = False
    payload["current_status"] = "inactive"
    return {
        **match_row,
        "event_id": event_id,
        "event_type": "TriggerStateChanged",
        "event_time": "2026-07-02T10:05:00+08:00",
        "dedup_key": f"n4:{event_id}",
        "payload_json": payload,
    }


def trigger_state_changed_true(match_row, event_id="n4-state-true-1"):
    payload = dict(match_row["payload_json"])
    payload["trigger_live"] = True
    payload["current_status"] = "matched"
    return {
        **match_row,
        "event_id": event_id,
        "event_type": "TriggerStateChanged",
        "event_time": "2026-07-02T10:05:00+08:00",
        "dedup_key": f"n4:{event_id}",
        "payload_json": payload,
    }


def passing_buy_metric(
    *,
    metric_id=301,
    current_30m_virtual_amount=200,
    previous_day_same_window_amount=100,
    metric_time="2026-07-02T10:00:00+08:00",
):
    return {
        "action_confirmation_metric_id": metric_id,
        "projection_run_id": SOURCE_METRIC_RUN_ID,
        "for_trade_date": TRADE_DATE,
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY_MAIN",
        "source_basis": "N3T_C1_CLOSED",
        "metric_role": "action_confirmation",
        "proof_consumer": "N5",
        "not_n5_final_proof": False,
        "metric_ready": True,
        "metric_quality_status": "passed",
        "virtual_amount_policy_version": "previous_day_same_window_elapsed_ratio_v1",
        "metric_time": metric_time,
        "metric_minute_label": "10:00",
        "current_price": 12,
        "previous_120m_body_high": 10,
        "previous_30m_body_high": 10,
        "previous_5m_body_high": 10,
        "previous_1m_body_high": 10,
        "current_5m_virtual_amount": 80,
        "previous_5m_full_amount": 60,
        "current_1m_amount": 20,
        "previous_1m_amount": 10,
        "current_30m_virtual_amount": current_30m_virtual_amount,
        "previous_day_same_window_amount": previous_day_same_window_amount,
    }


def unready_metric():
    row = passing_buy_metric()
    row["metric_ready"] = False
    return row


def legacy_n3p_metric():
    row = passing_buy_metric()
    row["projection_run_id"] = SOURCE_METRIC_RUN_ID
    row["source_basis"] = "N3P_B1_SOURCE_RETURNED"
    row["metric_role"] = "trigger_proof"
    row["proof_consumer"] = "N4"
    row["not_n5_final_proof"] = True
    return row


def legacy_realtime_action_confirmation_metric():
    row = passing_buy_metric()
    row["projection_run_id"] = "realtime_action_confirmation_metric_20260702_until_0944__asset_all"
    row["source_basis"] = "N3T_C1_CLOSED"
    row["metric_role"] = "action_confirmation"
    row["proof_consumer"] = "N5"
    row["not_n5_final_proof"] = False
    return row


def n3t_metric_without_legacy_virtual_policy():
    row = passing_buy_metric()
    row.pop("virtual_amount_policy_version", None)
    row["raw_json"] = {}
    row["trace_json"] = {}
    return row


class N3TMetricFetchCursor:
    def __init__(self):
        self.calls = []
        self._rows = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "stock_n3t_action_confirmation_metric" in sql:
            self._rows = [
                {
                    "n3t_action_confirmation_metric_id": 901,
                    "projection_run_id": "n3t_action_confirmation_metric_20260702_until_0944__n5_live_tracking_scope_v1",
                    "for_trade_date": TRADE_DATE,
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "source_basis": "N3T_C1_CLOSED",
                    "metric_role": "action_confirmation",
                    "proof_consumer": "N5",
                    "not_n5_final_proof": False,
                    "metric_ready": True,
                    "metric_quality_status": "passed",
                }
            ]
            return
        self._rows = []

    def fetchall(self):
        return list(self._rows)


class TrackingUpsertCursor:
    def __init__(self):
        self.sql = ""
        self.values = []

    def executemany(self, sql, values):
        self.sql = sql
        self.values = list(values)


class N5LiveTrackingPollerTests(unittest.TestCase):
    def build_plan(self, rows, *, active_tracking_rows=None, metric_rows=None, existing_event_keys=None):
        return poller.build_live_tracking_plan(
            n4_event_rows=rows,
            active_tracking_rows=active_tracking_rows or [],
            metric_rows=metric_rows or [],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=SOURCE_METRIC_RUN_ID,
            consumer_name=CONSUMER_NAME,
            existing_action_event_keys=existing_event_keys or set(),
            for_trade_date=TRADE_DATE,
        )

    def test_trigger_matched_creates_exactly_one_action_eligible(self):
        plan = self.build_plan([trigger_matched()])

        self.assertEqual([event["event_type"] for event in plan["action_events"]], ["ActionEligible"])
        event = plan["action_events"][0]
        self.assertIsNone(event["payload_json"]["action_mark"])
        self.assertEqual(event["payload_json"]["confirmation_status"], "pending")
        self.assertEqual(plan["summary"]["action_eligible_count"], 1)

    def test_repeated_one_shot_does_not_duplicate_action_eligible(self):
        first = self.build_plan([trigger_matched()])
        second = self.build_plan(
            [trigger_matched()],
            active_tracking_rows=first["tracking_updates"],
            existing_event_keys={first["action_events"][0]["event_key"]},
        )

        self.assertEqual(first["summary"]["action_eligible_count"], 1)
        self.assertEqual(second["summary"]["action_eligible_count"], 0)
        self.assertEqual(second["action_events"], [])

    def test_same_invocation_emits_action_eligible_then_action_executed(self):
        plan = self.build_plan([trigger_matched()], metric_rows=[passing_buy_metric()])

        self.assertEqual(
            [event["event_type"] for event in plan["action_events"]],
            ["ActionEligible", "ActionExecuted"],
        )
        executed = plan["action_events"][1]
        self.assertEqual(executed["payload_json"]["action_mark"], "30m_volume")
        self.assertEqual(executed["payload_json"]["confirmation_status"], "passed")

    def test_later_invocation_executes_active_tracking(self):
        first = self.build_plan([trigger_matched()])
        second = self.build_plan([], active_tracking_rows=first["tracking_updates"], metric_rows=[passing_buy_metric()])

        self.assertEqual([event["event_type"] for event in second["action_events"]], ["ActionExecuted"])
        self.assertEqual(second["tracking_updates"][0]["action_state"], "executed")

    def test_trigger_state_changed_false_expires_tracking_without_n6_event(self):
        match = trigger_matched()
        first = self.build_plan([match])
        second = self.build_plan(
            [trigger_state_changed_false(match)],
            active_tracking_rows=first["tracking_updates"],
        )

        self.assertEqual(second["action_events"], [])
        self.assertEqual(second["tracking_updates"][0]["action_state"], "expired")
        self.assertEqual(second["tracking_updates"][0]["tracking_status"], "expired")
        self.assertEqual(second["tracking_updates"][0]["expired_reason"], "trigger_live_false")
        self.assertEqual(
            second["tracking_updates"][0]["raw_json"]["rollback_before_tracking_state"]["action_state"],
            "eligible",
        )

    def test_trigger_state_changed_true_is_ignored_and_not_consumed(self):
        plan = self.build_plan([trigger_state_changed_true(trigger_matched())])

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"], [])
        self.assertEqual(plan["consumed_n4_event_ids"], [])
        self.assertEqual(plan["consumed_n4_events"], [])
        self.assertEqual(plan["summary"]["input_event_type_counts"], {"TriggerStateChanged": 1})
        self.assertTrue(plan["active_scope_snapshot_artifact"]["empty_scope_noop"])

    def test_same_object_different_condition_key_is_tracked_independently(self):
        rows = [
            trigger_matched("n4-match-a", condition_key="BUY_MAIN"),
            trigger_matched("n4-match-b", condition_key="BUY_FULL"),
        ]
        plan = self.build_plan(rows)

        self.assertEqual(plan["summary"]["tracking_upsert_count"], 2)
        self.assertEqual(plan["summary"]["action_eligible_count"], 2)
        self.assertEqual(
            {update["condition_key"] for update in plan["tracking_updates"]},
            {"BUY_MAIN", "BUY_FULL"},
        )

    def test_missing_or_unready_metric_keeps_active_tracking_without_n6_event(self):
        first = self.build_plan([trigger_matched()])
        missing = self.build_plan([], active_tracking_rows=first["tracking_updates"])
        unready = self.build_plan([], active_tracking_rows=first["tracking_updates"], metric_rows=[unready_metric()])

        self.assertEqual(missing["action_events"], [])
        self.assertEqual(missing["tracking_updates"][0]["action_state"], "eligible")
        self.assertEqual(unready["action_events"], [])
        self.assertEqual(unready["tracking_updates"][0]["confirmation_status"], "pending")

    def test_legacy_n3p_metric_cannot_emit_action_executed(self):
        first = self.build_plan([trigger_matched()])
        legacy = self.build_plan(
            [],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[legacy_n3p_metric()],
        )

        self.assertEqual(legacy["action_events"], [])
        self.assertEqual(legacy["tracking_updates"][0]["confirmation_status"], "pending")
        self.assertEqual(
            legacy["tracking_updates"][0]["raw_json"]["latest_metric_status"]["reason"],
            "BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF",
        )

    def test_legacy_realtime_metric_cannot_emit_action_executed(self):
        first = self.build_plan([trigger_matched()])
        legacy_metric = legacy_realtime_action_confirmation_metric()
        legacy = poller.build_live_tracking_plan(
            n4_event_rows=[],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[legacy_metric],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=str(legacy_metric["projection_run_id"]),
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(legacy["action_events"], [])
        self.assertEqual(legacy["tracking_updates"][0]["confirmation_status"], "pending")
        self.assertEqual(
            legacy["tracking_updates"][0]["raw_json"]["latest_metric_status"]["reason"],
            "BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF",
        )

    def test_n3t_closed_c1_metric_without_legacy_policy_can_execute(self):
        plan = self.build_plan([trigger_matched()], metric_rows=[n3t_metric_without_legacy_virtual_policy()])

        self.assertEqual(
            [event["event_type"] for event in plan["action_events"]],
            ["ActionEligible", "ActionExecuted"],
        )
        executed = plan["action_events"][1]
        self.assertEqual(executed["payload_json"]["action_mark"], "30m_volume")
        self.assertEqual(executed["payload_json"]["confirmation_status"], "passed")

    def test_metric_without_n3t_source_basis_keeps_tracking_active(self):
        first = self.build_plan([trigger_matched()])
        metric = passing_buy_metric()
        metric.pop("source_basis")
        missing_source_basis = self.build_plan(
            [],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[metric],
        )

        self.assertEqual(missing_source_basis["action_events"], [])
        self.assertEqual(missing_source_basis["tracking_updates"][0]["confirmation_status"], "pending")
        self.assertEqual(
            missing_source_basis["tracking_updates"][0]["raw_json"]["latest_metric_status"]["reason"],
            "BLOCKED_N3T_METRIC_REQUIRED",
        )

    def test_missing_previous_day_same_window_amount_downgrades_action_mark(self):
        metric = passing_buy_metric(previous_day_same_window_amount=None)
        plan = self.build_plan([trigger_matched()], metric_rows=[metric])

        executed = [event for event in plan["action_events"] if event["event_type"] == "ActionExecuted"][0]
        self.assertEqual(executed["payload_json"]["action_mark"], "normal")
        self.assertEqual(
            executed["payload_json"]["action_mark_reason"],
            "previous_day_same_window_amount_missing",
        )

    def test_active_scope_snapshot_artifact_contains_only_n5_owned_active_scope(self):
        plan = self.build_plan([trigger_matched()])

        artifact = plan["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["artifact_type"], "n5_active_scope_snapshot_v1")
        self.assertEqual(artifact["producer_layer"], "N5_action")
        self.assertEqual(artifact["for_trade_date"], TRADE_DATE)
        self.assertEqual(artifact["scope_status"], "active")
        self.assertFalse(artifact["empty_scope_noop"])
        self.assertFalse(artifact["full_market_fallback_allowed"])
        self.assertFalse(artifact["n3_scans_n5_internals"])
        self.assertFalse(artifact["db_write_allowed"])
        self.assertFalse(artifact["n4_outbox_status_update_allowed"])
        self.assertEqual(artifact["scope_count"], 1)
        self.assertEqual(
            artifact["scope_rows"],
            [
                {
                    "for_trade_date": TRADE_DATE,
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "signal_type": "B_BUY",
                    "condition_key": "BUY_MAIN",
                    "source_trigger_event_id": "n4-match-1",
                    "source_trigger_run_id": SOURCE_TRIGGER_RUN_ID,
                    "scope_status": "active",
                }
            ],
        )

    def test_active_scope_snapshot_artifact_is_noop_when_scope_empty(self):
        plan = self.build_plan([])

        artifact = plan["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["scope_rows"], [])
        self.assertEqual(artifact["scope_count"], 0)
        self.assertEqual(artifact["scope_status"], "empty")
        self.assertTrue(artifact["empty_scope_noop"])
        self.assertFalse(artifact["full_market_fallback_allowed"])

    def test_active_scope_snapshot_artifact_removes_executed_or_trigger_live_false(self):
        executed = self.build_plan([trigger_matched()], metric_rows=[passing_buy_metric()])
        self.assertEqual(executed["active_scope_snapshot_artifact"]["scope_rows"], [])
        self.assertEqual(executed["active_scope_snapshot_artifact"]["scope_status"], "empty")
        self.assertEqual(
            executed["active_scope_snapshot_artifact"]["removed_scope_rows"][0]["scope_exit_reason"],
            "ActionExecuted",
        )

        first = self.build_plan([trigger_matched()])
        expired = self.build_plan(
            [trigger_state_changed_false(trigger_matched())],
            active_tracking_rows=first["tracking_updates"],
        )
        self.assertEqual(expired["active_scope_snapshot_artifact"]["scope_rows"], [])
        self.assertEqual(
            expired["active_scope_snapshot_artifact"]["removed_scope_rows"][0]["scope_exit_reason"],
            "TriggerStateChanged(trigger_live=false)",
        )

    def test_non_pending_trigger_matched_cannot_enter_active_scope_snapshot(self):
        plan = self.build_plan([trigger_matched(status="delivered")])

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"], [])
        self.assertEqual(plan["active_scope_snapshot_artifact"]["scope_rows"], [])
        self.assertTrue(plan["active_scope_snapshot_artifact"]["empty_scope_noop"])

    def test_module_does_not_reference_raw_c1_minute_tables(self):
        source = inspect.getsource(poller)

        self.assertNotIn("minute_bar_1m", source)
        self.assertNotIn("previous_day_minute", source)
        self.assertNotIn("tushare", source.lower())
        self.assertNotIn("mootdx", source.lower())


class N5LiveTrackingMetricFetcherTests(unittest.TestCase):
    def test_n3t_metric_run_reads_n3t_tables_and_maps_compatibility_id(self):
        cursor = N3TMetricFetchCursor()

        rows = action_execute.fetch_action_confirmation_metric_rows_by_run_id(
            cursor,
            "n3t_action_confirmation_metric_20260702_until_0944__n5_live_tracking_scope_v1",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_confirmation_metric_id"], 901)
        self.assertEqual(rows[0]["n3t_action_confirmation_metric_id"], 901)
        self.assertEqual(rows[0]["source_basis"], "N3T_C1_CLOSED")
        self.assertEqual(rows[0]["_metric_table"], "stock_n3t_action_confirmation_metric")
        queried_sql = "\n".join(call[0] for call in cursor.calls)
        self.assertIn("stock_n3t_action_confirmation_metric", queried_sql)
        self.assertNotIn("stock_action_confirmation_projection_metric", queried_sql)


class N5LiveTrackingPollerScriptTests(unittest.TestCase):
    def base_args(self, *extra):
        return [
            "--for-trade-date",
            TRADE_DATE,
            "--source-trigger-run-id",
            SOURCE_TRIGGER_RUN_ID,
            "--source-metric-run-id",
            SOURCE_METRIC_RUN_ID,
            "--action-run-id",
            ACTION_RUN_ID,
            "--consumer-name",
            CONSUMER_NAME,
            "--max-events",
            "10",
            "--max-runtime-seconds",
            "30",
            *extra,
        ]

    def test_plan_only_does_not_call_writer(self):
        calls = {"provider": 0, "writer": 0}

        def provider(args):
            calls["provider"] += 1
            return poller.build_live_tracking_plan(
                n4_event_rows=[trigger_matched()],
                active_tracking_rows=[],
                metric_rows=[],
                action_run_id=args.action_run_id,
                source_trigger_run_id=args.source_trigger_run_id,
                source_metric_run_id=args.source_metric_run_id,
                consumer_name=args.consumer_name,
            )

        def writer(_args, _plan):
            calls["writer"] += 1
            raise AssertionError("plan-only must not write")

        manifest = poller_script.run_n5_live_tracking_poller_once(
            self.base_args(),
            plan_provider=provider,
            writer=writer,
        )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
        self.assertFalse(manifest["writes_enabled"])
        self.assertEqual(calls, {"provider": 1, "writer": 0})

    def test_fastlane_arguments_are_accepted_without_changing_plan_only_behavior(self):
        calls = {"provider": 0}

        def provider(args):
            calls["provider"] += 1
            self.assertEqual(args.fastlane_lane_id, "n5_action_confirmation_fastlane_v1")
            self.assertEqual(args.fastlane_phase, "intake")
            return poller.build_live_tracking_plan(
                n4_event_rows=[trigger_matched()],
                active_tracking_rows=[],
                metric_rows=[],
                action_run_id=args.action_run_id,
                source_trigger_run_id=args.source_trigger_run_id,
                source_metric_run_id=args.source_metric_run_id,
                consumer_name=args.consumer_name,
            )

        manifest = poller_script.run_n5_live_tracking_poller_once(
            self.base_args(
                "--fastlane-lane-id",
                "n5_action_confirmation_fastlane_v1",
                "--fastlane-phase",
                "intake",
            ),
            plan_provider=provider,
        )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
        self.assertEqual(manifest["fastlane"]["lane_id"], "n5_action_confirmation_fastlane_v1")
        self.assertEqual(manifest["fastlane"]["phase"], "intake")
        self.assertFalse(manifest["writes_enabled"])
        self.assertEqual(calls["provider"], 1)

    def test_active_scope_artifact_path_writes_n5_scope_file(self):
        def provider(args):
            return poller.build_live_tracking_plan(
                n4_event_rows=[trigger_matched()],
                active_tracking_rows=[],
                metric_rows=[],
                action_run_id=args.action_run_id,
                source_trigger_run_id=args.source_trigger_run_id,
                source_metric_run_id=args.source_metric_run_id,
                consumer_name=args.consumer_name,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1.json"
            manifest = poller_script.run_n5_live_tracking_poller_once(
                self.base_args(
                    "--active-scope-artifact-path",
                    str(artifact_path),
                    "--write-active-scope-artifact",
                    "--user-confirmed",
                ),
                plan_provider=provider,
            )

            self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
            self.assertFalse(manifest["writes_enabled"])
            self.assertTrue(manifest["artifact_writes_enabled"])
            self.assertTrue(artifact_path.exists())
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["artifact_type"], "n5_active_scope_snapshot_v1")
            self.assertEqual(payload["scope_count"], 1)
            self.assertFalse(payload["full_market_fallback_allowed"])
            self.assertEqual(manifest["active_scope_artifact_write_result"]["path"], str(artifact_path))

    def test_execute_without_explicit_artifact_flag_does_not_write_active_scope_file(self):
        def provider(args):
            return poller.build_live_tracking_plan(
                n4_event_rows=[trigger_matched()],
                active_tracking_rows=[],
                metric_rows=[],
                action_run_id=args.action_run_id,
                source_trigger_run_id=args.source_trigger_run_id,
                source_metric_run_id=args.source_metric_run_id,
                consumer_name=args.consumer_name,
            )

        def writer(_args, _plan):
            return {"executed": True, "tracking_rows_written": 1, "outbox_rows_written": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1.json"
            manifest = poller_script.run_n5_live_tracking_poller_once(
                self.base_args(
                    "--active-scope-artifact-path",
                    str(artifact_path),
                    "--execute",
                    "--user-confirmed",
                ),
                plan_provider=provider,
                writer=writer,
            )

            self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_EXECUTE_PASS")
            self.assertTrue(manifest["writes_enabled"])
            self.assertFalse(manifest["artifact_writes_enabled"])
            self.assertFalse(artifact_path.exists())
            self.assertEqual(
                manifest["active_scope_artifact_write_result"],
                {
                    "executed": False,
                    "reason": "artifact_write_disabled",
                    "artifact_writes_enabled": False,
                },
            )

    def test_tracking_values_include_schema_required_monitor_window_trigger_type_and_triggered_periods(self):
        plan = poller.build_live_tracking_plan(
            n4_event_rows=[trigger_matched(condition_key="BUY:Y,Q,M,W,D")],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=SOURCE_METRIC_RUN_ID,
            consumer_name=CONSUMER_NAME,
        )

        values = poller_script._tracking_values(plan["tracking_updates"][0])

        self.assertTrue(str(values[29]).startswith("N5_live_tracking_monitor_window_v1|action_run_id|"))
        self.assertIn(ACTION_RUN_ID, str(values[29]))
        self.assertEqual(values[30], "BUY")
        self.assertNotEqual(values[30], "N5_live_tracking_v2")
        self.assertIn("D", str(values[31]))
        self.assertEqual(values[32], "v2")

    def test_tracking_trigger_type_derives_schema_allowed_condition_type(self):
        cases = [
            ("B_BUY", "buy", "BUY:Y,Q,M,W,D", "BUY"),
            ("S_SELL", "sell", "SELL:Y,Q,M,W,D", "SELL"),
            ("B_BUY", "buy", "BUY:FULL:Y,Q,M,W,D", "BUY:FULL"),
            ("S_SELL", "sell", "SELL:FULL:Y,Q,M,W,D", "SELL:FULL"),
            ("B_BUY", "buy", "BUY_HINT:Y,Q,M,W,D", "BUY_HINT"),
            ("S_SELL", "sell", "SELL_HINT:Y,Q,M,W,D", "SELL_HINT"),
        ]
        for signal_type, direction, condition_key, expected in cases:
            with self.subTest(condition_key=condition_key):
                plan = poller.build_live_tracking_plan(
                    n4_event_rows=[
                        trigger_matched(
                            signal_type=signal_type,
                            direction=direction,
                            condition_key=condition_key,
                        )
                    ],
                    active_tracking_rows=[],
                    metric_rows=[],
                    action_run_id=ACTION_RUN_ID,
                    source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
                    source_metric_run_id=SOURCE_METRIC_RUN_ID,
                    consumer_name=CONSUMER_NAME,
                )

                values = poller_script._tracking_values(plan["tracking_updates"][0])

                self.assertEqual(values[30], expected)
                self.assertIn(
                    values[30],
                    {"BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT"},
                )

    def test_tracking_upsert_sql_provides_schema_required_columns(self):
        plan = poller.build_live_tracking_plan(
            n4_event_rows=[trigger_matched()],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=SOURCE_METRIC_RUN_ID,
            consumer_name=CONSUMER_NAME,
        )
        cursor = TrackingUpsertCursor()

        count = poller_script._upsert_tracking_states(cursor, plan["tracking_updates"])

        self.assertEqual(count, 1)
        self.assertIn("monitor_window_id", cursor.sql)
        self.assertIn("triggered_periods", cursor.sql)
        self.assertEqual(len(cursor.values[0]), cursor.sql.count("%s"))

    def test_action_executed_writer_jsonb_payloads_are_json_serializable(self):
        metric_time = datetime.fromisoformat("2026-07-02T10:00:00+08:00")
        plan = poller.build_live_tracking_plan(
            n4_event_rows=[trigger_matched()],
            active_tracking_rows=[],
            metric_rows=[
                passing_buy_metric(
                    metric_time=metric_time,
                    current_30m_virtual_amount=Decimal("200"),
                    previous_day_same_window_amount=Decimal("100"),
                )
            ],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=SOURCE_METRIC_RUN_ID,
            consumer_name=CONSUMER_NAME,
        )
        executed_tracking = next(
            row for row in plan["tracking_updates"] if row["action_state"] == "executed"
        )
        tracking_values = poller_script._tracking_values(executed_tracking)

        json.dumps(tracking_values[33].obj, ensure_ascii=False)
        self.assertIsInstance(tracking_values[33].obj["selected_metric_time"], str)
        self.assertIsInstance(
            tracking_values[33].obj["confirmation_trace"]["metric_time"],
            str,
        )

        executed_event = next(
            event for event in plan["action_events"] if event["event_type"] == "ActionExecuted"
        )
        cursor = TrackingUpsertCursor()
        poller_script._insert_action_outbox_events(cursor, [executed_event])

        json.dumps(cursor.values[0][11].obj, ensure_ascii=False)
        self.assertIsInstance(
            cursor.values[0][11].obj["trace_json"]["selected_metric_time"],
            str,
        )

    def test_inbox_writer_payload_json_is_json_serializable(self):
        event_row = trigger_matched()
        event_row["payload_json"] = {
            **event_row["payload_json"],
            "source_seen_at": datetime.fromisoformat("2026-07-02T10:00:00+08:00"),
            "source_amount": Decimal("12.34"),
        }
        cursor = TrackingUpsertCursor()

        poller_script._insert_inbox_rows(
            cursor,
            [event_row],
            SimpleNamespace(
                consumer_name=CONSUMER_NAME,
                action_run_id=ACTION_RUN_ID,
                source_metric_run_id=SOURCE_METRIC_RUN_ID,
            ),
        )

        json.dumps(cursor.values[0][8].obj, ensure_ascii=False)
        json.dumps(cursor.values[0][9].obj, ensure_ascii=False)
        self.assertIsInstance(cursor.values[0][8].obj["source_seen_at"], str)
        self.assertEqual(cursor.values[0][8].obj["source_amount"], "12.34")

    def test_execute_requires_user_confirmed_before_plan_provider(self):
        calls = {"provider": 0}

        def provider(_args):
            calls["provider"] += 1
            raise AssertionError("blocked execute must not plan")

        manifest = poller_script.run_n5_live_tracking_poller_once(
            self.base_args("--execute"),
            plan_provider=provider,
        )

        self.assertEqual(manifest["verdict"], "BLOCKED_N5_LIVE_TRACKING_POLLER")
        self.assertEqual(manifest["blocked_reason"], "execute_requires_user_confirmed")
        self.assertEqual(calls["provider"], 0)

    def test_execute_user_confirmed_calls_writer(self):
        calls = {"writer": 0}

        def provider(args):
            return poller.build_live_tracking_plan(
                n4_event_rows=[trigger_matched()],
                active_tracking_rows=[],
                metric_rows=[],
                action_run_id=args.action_run_id,
                source_trigger_run_id=args.source_trigger_run_id,
                source_metric_run_id=args.source_metric_run_id,
                consumer_name=args.consumer_name,
            )

        def writer(_args, plan):
            calls["writer"] += 1
            self.assertEqual(plan["summary"]["action_eligible_count"], 1)
            return {"executed": True, "n4_outbox_status_updated": False}

        manifest = poller_script.run_n5_live_tracking_poller_once(
            self.base_args("--execute", "--user-confirmed"),
            plan_provider=provider,
            writer=writer,
        )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_EXECUTE_PASS")
        self.assertTrue(manifest["writes_enabled"])
        self.assertEqual(calls["writer"], 1)


if __name__ == "__main__":
    unittest.main()
