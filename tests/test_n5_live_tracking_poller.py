import inspect
import json
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


def trigger_state_changed_true(match_row, event_id="n4-state-true-1", *, event_time="2026-07-02T10:05:00+08:00"):
    payload = dict(match_row["payload_json"])
    payload["trigger_live"] = True
    payload["current_status"] = "matched"
    payload.setdefault("trigger_price", 12.34)
    payload.setdefault("triggered_periods", payload.get("all_trigger_periods") or ["D"])
    payload.setdefault("projection_30m_flag", False)
    payload.setdefault("projection_30m_type", "none")
    return {
        **match_row,
        "event_id": event_id,
        "event_type": "TriggerStateChanged",
        "event_time": event_time,
        "dedup_key": f"n4:{event_id}",
        "payload_json": payload,
    }


def action_executed_event(match_row, *, event_id="n5-executed-1", event_time="2026-07-02T10:01:00+08:00"):
    payload = dict(match_row["payload_json"])
    payload.update(
        {
            "action_state": "executed",
            "confirmation_status": "passed",
            "action_mark": "normal",
            "source_trigger_event_id": match_row.get("event_id"),
            "source_trigger_event_type": match_row.get("event_type"),
            "source_trigger_event_time": match_row.get("event_time"),
        }
    )
    return {
        "event_id": event_id,
        "event_type": "ActionExecuted",
        "trade_date": TRADE_DATE,
        "asset_kind": match_row.get("asset_kind"),
        "identity_key": match_row.get("identity_key"),
        "event_time": event_time,
        "source_layer": "N5_action",
        "source_run_id": ACTION_RUN_ID,
        "dedup_key": f"n5:{event_id}",
        "partition_key": match_row.get("identity_key"),
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
        "previous_1m_period_source": "same_trade_date_previous_period",
        "previous_5m_period_source": "same_trade_date_previous_period",
        "previous_30m_period_source": "same_trade_date_previous_period",
        "previous_120m_period_source": "same_trade_date_previous_period",
        "is_first_1m_of_day": False,
        "is_first_5m_of_day": False,
        "is_first_30m_of_day": False,
        "is_first_120m_of_day": False,
        "first_1m_amount_default_pass": False,
        "first_5m_amount_default_pass": False,
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


class ExecutedObjectMinuteDiscoveryCursor:
    def __init__(self):
        self.calls = []
        self._rows = []
        self._row = None
        self.object_minute_params = None

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "WITH active_tracking AS" in sql:
            self._rows = [
                {
                    "run_id": ACTION_RUN_ID,
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "signal_type": "B_BUY",
                    "condition_key": "BUY_MAIN",
                    "source_trigger_run_id": "",
                    "source_trigger_event_id": "evt-n4-match",
                    "state_key": "state-key-with-different-hash",
                    "trigger_time": "2026-07-02T09:31:00+08:00",
                    "latest_n4_event_time": "2026-07-02T09:31:00+08:00",
                    "last_checked_minute_label": "",
                    "next_unchecked_minute_label": "14:11",
                    "raw_json": {},
                    "source_run_hash": "",
                    "active_tracking_count": 1,
                }
            ]
            self._row = None
            return
        if "projection_run_id LIKE" in sql:
            self._rows = []
            self._row = None
            return
        if "identity_key = %s" in sql and "source_basis = 'N3T_C1_CLOSED'" in sql:
            self.object_minute_params = params
            self._rows = [
                {
                    "metric_minute_label": "14:11",
                    "metric_evaluation_minute_label": "14:11",
                    "projection_run_id": "n3t_action_confirmation_metric_20260702_until_1411__fastlane_sr_objecthash_raw_prevday_c1_amount_v1",
                },
                {
                    "metric_minute_label": "14:12",
                    "metric_evaluation_minute_label": "14:12",
                    "projection_run_id": "n3t_action_confirmation_metric_20260702_until_1412__fastlane_sr_objecthash_raw_prevday_c1_amount_v1",
                },
            ]
            self._row = {
                "projection_run_id": "n3t_action_confirmation_metric_20260702_until_1411__fastlane_sr_objecthash_raw_prevday_c1_amount_v1",
                "latest_metric_time": "2026-07-02T14:12:00+08:00",
            }
            return
        self._rows = []
        self._row = None

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._row


class ExecutedFinalNoActionDiscoveryCursor:
    def __init__(self):
        self.calls = []
        self._rows = []
        self._row = None
        self.reached_broad_scan = False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "WITH stale_tracking AS" in sql:
            self._rows = []
            self._row = None
            return
        if "post_close_no_action_candidates" in sql:
            self._rows = [
                {
                    "run_id": ACTION_RUN_ID,
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "signal_type": "B_BUY",
                    "condition_key": "BUY_MAIN",
                    "source_trigger_run_id": "",
                    "source_trigger_event_id": "evt-n4-match",
                    "state_key": "state-key-final-no-action",
                    "trigger_time": "2026-07-02T09:31:00+08:00",
                    "latest_n4_event_time": "2026-07-02T09:31:00+08:00",
                    "last_checked_minute_label": "14:59",
                    "next_unchecked_minute_label": "",
                    "source_metric_run_id": "n3t_action_confirmation_metric_20260702_until_1459__fastlane_sr_final_raw_prevday_c1_amount_v1",
                    "target_minute_label": "14:59",
                    "latest_metric_reason": "price_confirmation_failed",
                    "raw_json": {
                        "latest_metric_status": {
                            "status": "pending",
                            "reason": "price_confirmation_failed",
                            "projection_run_id": "n3t_action_confirmation_metric_20260702_until_1459__fastlane_sr_final_raw_prevday_c1_amount_v1",
                            "metric_minute_label": "14:59",
                        }
                    },
                    "source_run_hash": "final",
                    "active_tracking_count": 1,
                }
            ]
            self._row = None
            return
        if "source_run_scoped AS" in sql:
            self.reached_broad_scan = True
        self._rows = []
        self._row = None

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._row


class TrackingUpsertCursor:
    def __init__(self):
        self.sql = ""
        self.values = []

    def executemany(self, sql, values):
        self.sql = sql
        self.values = list(values)


class N5LiveTrackingPollerTests(unittest.TestCase):
    def build_plan(
        self,
        rows,
        *,
        active_tracking_rows=None,
        metric_rows=None,
        existing_event_keys=None,
        active_scope_tracking_rows=None,
    ):
        return poller.build_live_tracking_plan(
            n4_event_rows=rows,
            active_tracking_rows=active_tracking_rows or [],
            metric_rows=metric_rows or [],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=SOURCE_METRIC_RUN_ID,
            consumer_name=CONSUMER_NAME,
            existing_action_event_keys=existing_event_keys or set(),
            active_scope_tracking_rows=active_scope_tracking_rows,
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

    def test_existing_continuous_proofs_advance_cursor_until_first_pass(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T09:51:00+08:00")])
        failed_0951 = passing_buy_metric(metric_id=401, metric_time="2026-07-02T09:52:00+08:00")
        failed_0951.update(
            {
                "projection_run_id": "n3t-action-0951",
                "metric_minute_label": "09:51",
                "current_price": Decimal("6.02"),
                "previous_1m_body_high": Decimal("6.06"),
                "current_1m_amount": Decimal("6598869"),
                "previous_1m_amount": Decimal("12752668"),
            }
        )
        failed_0952 = passing_buy_metric(metric_id=402, metric_time="2026-07-02T09:53:00+08:00")
        failed_0952.update(
            {
                "projection_run_id": "n3t-action-0952",
                "metric_minute_label": "09:52",
                "current_price": Decimal("6.03"),
                "previous_1m_body_high": Decimal("6.02"),
                "current_1m_amount": Decimal("6368595"),
                "previous_1m_amount": Decimal("6598869"),
                "current_5m_virtual_amount": Decimal("43544404"),
                "previous_5m_full_amount": Decimal("45331909"),
            }
        )
        failed_0953 = passing_buy_metric(metric_id=403, metric_time="2026-07-02T09:54:00+08:00")
        failed_0953.update(
            {
                "projection_run_id": "n3t-action-0953",
                "metric_minute_label": "09:53",
                "current_price": Decimal("6.03"),
                "previous_1m_body_high": Decimal("6.02"),
                "current_1m_amount": Decimal("6368595"),
                "previous_1m_amount": Decimal("6598869"),
            }
        )
        passing_0954 = passing_buy_metric(metric_id=404, metric_time="2026-07-02T09:55:00+08:00")
        passing_0954.update(
            {
                "projection_run_id": "n3t-action-0954",
                "metric_minute_label": "09:54",
                "current_price": Decimal("6.07"),
                "previous_120m_body_high": Decimal("5.81"),
                "previous_30m_body_high": Decimal("6.03"),
                "previous_5m_body_high": Decimal("6.03"),
                "previous_1m_body_high": Decimal("6.03"),
                "current_1m_amount": Decimal("10757561"),
                "previous_1m_amount": Decimal("6368595"),
                "current_5m_virtual_amount": Decimal("64554585"),
                "previous_5m_full_amount": Decimal("60148102"),
            }
        )

        plan = poller.build_live_tracking_plan(
            n4_event_rows=[],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[failed_0951, failed_0952, failed_0953, passing_0954],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id="n3t-action-0951,n3t-action-0952,n3t-action-0953,n3t-action-0954",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual([event["event_type"] for event in plan["action_events"]], ["ActionExecuted"])
        self.assertEqual(plan["tracking_updates"][0]["action_state"], "executed")
        self.assertEqual(plan["tracking_updates"][0]["last_checked_minute_label"], "09:54")
        self.assertEqual(
            plan["action_events"][0]["payload_json"]["trace_json"]["source_action_confirmation_metric_id"],
            "404",
        )
        self.assertEqual(plan["action_events"][0]["payload_json"]["source_metric_run_id"], "n3t-action-0954")

    def test_batch_executed_events_trace_each_selected_metric_run_id(self):
        match_1 = trigger_matched(
            event_id="n4-match-1",
            identity_key="stock:SH:600001",
            condition_key="BUY_MAIN",
            event_time="2026-07-02T09:51:00+08:00",
        )
        match_2 = trigger_matched(
            event_id="n4-match-2",
            identity_key="stock:SH:600002",
            condition_key="BUY_MAIN",
            event_time="2026-07-02T09:51:00+08:00",
        )
        first = self.build_plan([match_1, match_2])
        metric_1 = passing_buy_metric(metric_id=501, metric_time="2026-07-02T09:52:00+08:00")
        metric_1["identity_key"] = "stock:SH:600001"
        metric_1["projection_run_id"] = "n3t-action-0951-stock-1"
        metric_1["metric_minute_label"] = "09:51"
        metric_2 = passing_buy_metric(metric_id=502, metric_time="2026-07-02T09:52:00+08:00")
        metric_2["identity_key"] = "stock:SH:600002"
        metric_2["projection_run_id"] = "n3t-action-0951-stock-2"
        metric_2["metric_minute_label"] = "09:51"

        plan = poller.build_live_tracking_plan(
            n4_event_rows=[],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[metric_1, metric_2],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id="n3t-action-0951-stock-1,n3t-action-0951-stock-2",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        selected_metric_by_identity = {
            event["payload_json"]["identity_key"]: event["payload_json"]["source_metric_run_id"]
            for event in plan["action_events"]
        }
        self.assertEqual(
            selected_metric_by_identity,
            {
                "stock:SH:600001": "n3t-action-0951-stock-1",
                "stock:SH:600002": "n3t-action-0951-stock-2",
            },
        )

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

    def test_trigger_state_changed_true_enters_active_scope_without_action_eligible(self):
        plan = self.build_plan(
            [
                trigger_state_changed_true(
                    trigger_matched(event_time="2026-07-02T13:40:00+08:00"),
                )
            ]
        )

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["source_trigger_event_type"], "TriggerStateChanged")
        self.assertIsNone(plan["tracking_updates"][0]["planned_output_event_type"])
        self.assertEqual(plan["consumed_n4_event_ids"], ["n4-state-true-1"])
        self.assertEqual([event["event_type"] for event in plan["consumed_n4_events"]], ["TriggerStateChanged"])
        self.assertEqual(plan["summary"]["input_event_type_counts"], {"TriggerStateChanged": 1})
        self.assertEqual(plan["summary"]["action_eligible_count"], 0)
        artifact = plan["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["scope_granularity"], "object")
        self.assertEqual(artifact["scope_count"], 1)
        self.assertFalse(artifact["empty_scope_noop"])
        scope_row = artifact["scope_rows"][0]
        self.assertEqual(scope_row["asset_kind"], "stock")
        self.assertEqual(scope_row["identity_key"], "stock:SH:600000")
        self.assertEqual(scope_row["attention_event_refs"], [])
        self.assertEqual(scope_row["active_tracking_refs"][0]["source_trigger_event_type"], "TriggerStateChanged")
        self.assertEqual(scope_row["active_tracking_refs"][0]["trigger_time"], "2026-07-02T10:05:00+08:00")
        self.assertEqual(
            scope_row["active_tracking_refs"][0]["source_trigger_event_time"],
            "2026-07-02T10:05:00+08:00",
        )
        self.assertFalse(scope_row["active_tracking_refs"][0]["action_eligible_entry_allowed"])
        self.assertEqual(scope_row["active_tracking_refs"][0]["source_n4_payload"]["trigger_price"], 12.34)

    def test_latest_trigger_state_changed_true_refreshes_active_ref_time(self):
        base = trigger_matched(event_time="2026-07-02T09:55:00+08:00")
        plan = self.build_plan(
            [
                trigger_state_changed_true(base, "n4-state-true-1304", event_time="2026-07-02T13:04:00+08:00"),
                trigger_state_changed_true(base, "n4-state-true-1352", event_time="2026-07-02T13:52:00+08:00"),
            ]
        )

        scope_ref = plan["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(scope_ref["source_trigger_event_id"], "n4-state-true-1352")
        self.assertEqual(scope_ref["trigger_time"], "2026-07-02T13:52:00+08:00")
        self.assertEqual(scope_ref["first_confirmation_minute_label"], "13:52")
        self.assertEqual(plan["summary"]["action_eligible_count"], 0)
        self.assertEqual(plan["action_events"], [])

    def test_active_set_a_plan_accepts_mixed_source_runs_without_source_trigger_filter(self):
        base = trigger_matched(event_time="2026-07-02T09:55:00+08:00")
        early = trigger_state_changed_true(
            base,
            "n4-state-true-1304",
            event_time="2026-07-02T13:04:00+08:00",
        )
        early["source_run_id"] = "trigger_state_changed_true_20260702_1304"
        early["payload_json"] = {
            **early["payload_json"],
            "condition_key": "BUY:Y,M,W,D",
        }
        late = trigger_state_changed_true(
            base,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        late["source_run_id"] = "trigger_state_changed_true_20260702_1352"
        late["payload_json"] = {
            **late["payload_json"],
            "trigger_price": 119.27,
            "triggered_periods": ["D"],
            "condition_key": "BUY:Y,M,W,D",
        }

        plan = poller.build_live_tracking_plan(
            n4_event_rows=[early, late],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id="n5-active-set-a-run",
            source_trigger_run_id="",
            source_metric_run_id="",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(plan["summary"]["input_event_type_counts"], {"TriggerStateChanged": 2})
        self.assertEqual(plan["consumed_n4_event_ids"], ["n4-state-true-1304", "n4-state-true-1352"])
        self.assertEqual(plan["summary"]["action_eligible_count"], 0)
        scope_ref = plan["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(scope_ref["source_trigger_event_id"], "n4-state-true-1352")
        self.assertEqual(scope_ref["source_trigger_run_id"], "trigger_state_changed_true_20260702_1352")
        self.assertEqual(scope_ref["trigger_time"], "2026-07-02T13:52:00+08:00")
        self.assertEqual(scope_ref["first_confirmation_minute_label"], "13:52")
        self.assertFalse(scope_ref["action_eligible_entry_allowed"])
        self.assertEqual(scope_ref["source_n4_payload"]["trigger_price"], 119.27)

    def test_processed_tsc_true_repair_enters_active_scope_without_reconsuming_n4(self):
        base = trigger_matched(event_time="2026-07-02T09:55:00+08:00")
        early = trigger_state_changed_true(
            base,
            "n4-state-true-1304",
            event_time="2026-07-02T13:04:00+08:00",
        )
        early["source_run_id"] = "trigger_state_changed_true_20260702_1304"
        early["payload_json"] = {
            **early["payload_json"],
            "condition_key": "BUY:Y,M,W,D",
        }
        late = trigger_state_changed_true(
            base,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        late["source_run_id"] = "trigger_state_changed_true_20260702_1352"
        late["payload_json"] = {
            **late["payload_json"],
            "trigger_price": 119.27,
            "triggered_periods": ["D"],
            "condition_key": "BUY:Y,M,W,D",
        }

        plan = poller.build_live_tracking_plan(
            n4_event_rows=[],
            repair_n4_event_rows=[early, late],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id="n5-active-set-a-run",
            source_trigger_run_id="",
            source_metric_run_id="",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(plan["consumed_n4_event_ids"], [])
        self.assertEqual(plan["consumed_n4_events"], [])
        self.assertEqual(plan["inbox_checkpoint_intent"]["source_event_ids"], [])
        self.assertEqual(plan["summary"]["action_eligible_count"], 0)
        self.assertEqual(plan["summary"]["tracking_upsert_count"], 1)
        update = plan["tracking_updates"][0]
        self.assertEqual(update["source_trigger_event_id"], "n4-state-true-1352")
        self.assertEqual(update["source_trigger_event_type"], "TriggerStateChanged")
        self.assertIsNone(update["planned_output_event_type"])
        self.assertEqual(update["latest_n4_event_time"], "2026-07-02T13:52:00+08:00")
        scope_ref = plan["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(scope_ref["source_trigger_event_id"], "n4-state-true-1352")
        self.assertEqual(scope_ref["trigger_time"], "2026-07-02T13:52:00+08:00")
        self.assertEqual(scope_ref["first_confirmation_minute_label"], "13:52")
        self.assertFalse(scope_ref["action_eligible_entry_allowed"])
        self.assertEqual(scope_ref["source_n4_payload"]["trigger_price"], 119.27)
        self.assertEqual(scope_ref["source_n4_payload"]["condition_key"], "BUY:Y,M,W,D")

    def test_processed_tsc_true_repair_ignores_non_matched_current_status(self):
        base = trigger_matched(event_time="2026-07-02T09:55:00+08:00")
        row = trigger_state_changed_true(
            base,
            "n4-state-true-watching",
            event_time="2026-07-02T13:52:00+08:00",
        )
        row["payload_json"] = {
            **row["payload_json"],
            "current_status": "watching",
        }

        plan = poller.build_live_tracking_plan(
            n4_event_rows=[],
            repair_n4_event_rows=[row],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id="n5-active-set-a-run",
            source_trigger_run_id="",
            source_metric_run_id="",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(plan["summary"]["tracking_upsert_count"], 0)
        self.assertEqual(plan["summary"]["action_eligible_count"], 0)
        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["consumed_n4_event_ids"], [])
        self.assertEqual(plan["consumed_n4_events"], [])
        self.assertEqual(plan["inbox_checkpoint_intent"]["source_event_ids"], [])
        self.assertEqual(plan["active_scope_snapshot_artifact"]["scope_count"], 0)
        self.assertEqual(plan["active_scope_snapshot_artifact"]["scope_rows"], [])

    def test_processed_tsc_true_repair_does_not_duplicate_existing_active_ref(self):
        base = trigger_matched(event_time="2026-07-02T09:55:00+08:00")
        row = trigger_state_changed_true(
            base,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        first = poller.build_live_tracking_plan(
            n4_event_rows=[],
            repair_n4_event_rows=[row],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id="n5-active-set-a-run",
            source_trigger_run_id="",
            source_metric_run_id="",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        second = poller.build_live_tracking_plan(
            n4_event_rows=[],
            repair_n4_event_rows=[row],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[],
            action_run_id="n5-active-set-a-run",
            source_trigger_run_id="",
            source_metric_run_id="",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(second["consumed_n4_event_ids"], [])
        scope_refs = second["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"]
        self.assertEqual(len(scope_refs), 1)
        self.assertEqual(scope_refs[0]["source_trigger_event_id"], "n4-state-true-1352")

    def test_processed_tsc_true_repair_does_not_reactivate_terminal_ref(self):
        base = trigger_matched()
        executed = self.build_plan([base], metric_rows=[passing_buy_metric()])
        executed_state = next(
            row for row in executed["tracking_updates"] if row["action_state"] == "executed"
        )
        row = trigger_state_changed_true(
            base,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )

        repaired = poller.build_live_tracking_plan(
            n4_event_rows=[],
            repair_n4_event_rows=[row],
            active_tracking_rows=[executed_state],
            metric_rows=[],
            action_run_id="n5-active-set-a-run",
            source_trigger_run_id="",
            source_metric_run_id="",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(repaired["tracking_updates"], [])
        self.assertEqual(repaired["summary"]["tracking_upsert_count"], 0)
        self.assertEqual(repaired["active_scope_snapshot_artifact"]["scope_rows"], [])
        self.assertEqual(repaired["active_scope_snapshot_artifact"]["active_tracking_ref_count"], 0)

    def test_trigger_state_changed_true_can_execute_without_action_eligible_and_traces_latest_n4_event(self):
        row = trigger_state_changed_true(
            trigger_matched(event_time="2026-07-02T09:55:00+08:00"),
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        metric = passing_buy_metric(metric_time="2026-07-02T13:52:00+08:00")
        metric["metric_minute_label"] = "13:52"

        plan = self.build_plan([row], metric_rows=[metric])

        self.assertEqual([event["event_type"] for event in plan["action_events"]], ["ActionExecuted"])
        payload = plan["action_events"][0]["payload_json"]
        self.assertEqual(payload["source_trigger_event_type"], "TriggerStateChanged")
        self.assertEqual(payload["source_trigger_event_id"], "n4-state-true-1352")
        self.assertEqual(payload["source_trigger_event_time"], "2026-07-02T13:52:00+08:00")
        self.assertEqual(payload["trigger_time"], "2026-07-02T13:52:00+08:00")
        self.assertEqual(payload["source_n4_payload"]["triggered_periods"], ["D"])
        self.assertEqual(payload["trace_json"]["source_n4_payload"]["trigger_price"], 12.34)
        self.assertEqual(plan["summary"]["action_eligible_count"], 0)
        self.assertEqual(plan["summary"]["action_executed_count"], 1)

    def test_trigger_matched_after_attention_ref_still_creates_action_eligible(self):
        first = self.build_plan([trigger_state_changed_true(trigger_matched())])

        second = self.build_plan(
            [trigger_matched(event_id="n4-match-after-state", event_time="2026-07-02T10:06:00+08:00")],
            active_tracking_rows=first["tracking_updates"],
        )

        self.assertEqual([event["event_type"] for event in second["action_events"]], ["ActionEligible"])
        self.assertEqual(second["tracking_updates"][0]["source_trigger_event_type"], "TriggerMatched")
        self.assertEqual(second["tracking_updates"][0]["planned_output_event_type"], "ActionEligible")

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

    def test_same_object_buy_ref_supersedes_buy_hint_for_action_executed(self):
        rows = [
            trigger_matched(
                "n4-buy",
                condition_key="BUY:Y,M,W,D",
                event_time="2026-07-02T09:51:00+08:00",
            ),
            trigger_matched(
                "n4-hint",
                condition_key="BUY_HINT:Y,Q,M,W,D",
                event_time="2026-07-02T09:51:00+08:00",
            ),
        ]
        first = self.build_plan(rows)
        metric = passing_buy_metric(metric_time="2026-07-02T09:52:00+08:00")
        metric["metric_minute_label"] = "09:51"
        metric["condition_key"] = ""

        second = self.build_plan(
            [],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[metric],
        )

        executed_events = [event for event in second["action_events"] if event["event_type"] == "ActionExecuted"]
        self.assertEqual(len(executed_events), 1)
        self.assertEqual(executed_events[0]["payload_json"]["condition_key"], "BUY:Y,M,W,D")
        self.assertEqual(executed_events[0]["payload_json"]["signal_type"], "B_BUY")
        hint_update = next(
            row for row in second["tracking_updates"] if row["condition_key"] == "BUY_HINT:Y,Q,M,W,D"
        )
        self.assertEqual(hint_update["action_state"], "eligible")
        self.assertEqual(
            hint_update["raw_json"]["latest_metric_status"]["reason"],
            "superseded_by_primary_action_ref",
        )

    def test_hint_only_ref_can_execute_with_shared_object_minute_proof(self):
        first = self.build_plan(
            [
                trigger_matched(
                    "n4-hint-only",
                    condition_key="BUY_HINT:Y,Q,M,W,D",
                    event_time="2026-07-02T09:51:00+08:00",
                )
            ]
        )
        metric = passing_buy_metric(metric_time="2026-07-02T09:52:00+08:00")
        metric["metric_minute_label"] = "09:51"
        metric["condition_key"] = ""

        second = self.build_plan(
            [],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[metric],
        )

        executed_events = [event for event in second["action_events"] if event["event_type"] == "ActionExecuted"]
        self.assertEqual(len(executed_events), 1)
        self.assertEqual(executed_events[0]["payload_json"]["signal_type"], "B_BUY")
        self.assertEqual(executed_events[0]["payload_json"]["condition_key"], "BUY_HINT:Y,Q,M,W,D")
        self.assertEqual(executed_events[0]["payload_json"]["original_condition_key"], "BUY_HINT:Y,Q,M,W,D")

    def test_active_scope_snapshot_collapses_same_object_to_active_tracking_refs(self):
        rows = [
            trigger_matched("n4-match-a", condition_key="BUY_MAIN"),
            trigger_matched("n4-match-b", condition_key="BUY_FULL"),
        ]
        plan = self.build_plan(rows)

        artifact = plan["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["scope_granularity"], "object")
        self.assertEqual(artifact["scope_count"], 1)
        self.assertEqual(
            artifact["active_sets"]["ordinary_active"],
            [{"for_trade_date": TRADE_DATE, "asset_kind": "stock", "identity_key": "stock:SH:600000"}],
        )
        self.assertEqual(artifact["active_sets"]["b2_active"], [])
        self.assertEqual(len(artifact["scope_rows"]), 1)
        scope_row = artifact["scope_rows"][0]
        self.assertEqual(scope_row["for_trade_date"], TRADE_DATE)
        self.assertEqual(scope_row["asset_kind"], "stock")
        self.assertEqual(scope_row["identity_key"], "stock:SH:600000")
        self.assertEqual(scope_row["scope_status"], "active")
        self.assertEqual(scope_row["active_families"], ["ordinary"])
        self.assertEqual(
            {ref["condition_key"] for ref in scope_row["active_tracking_refs"]},
            {"BUY_MAIN", "BUY_FULL"},
        )
        self.assertEqual(
            {ref["source_trigger_event_id"] for ref in scope_row["active_tracking_refs"]},
            {"n4-match-a", "n4-match-b"},
        )

    def test_missing_or_unready_metric_keeps_active_tracking_without_n6_event(self):
        first = self.build_plan([trigger_matched()])
        missing = self.build_plan([], active_tracking_rows=first["tracking_updates"])
        unready = self.build_plan([], active_tracking_rows=first["tracking_updates"], metric_rows=[unready_metric()])

        self.assertEqual(missing["action_events"], [])
        self.assertEqual(missing["tracking_updates"][0]["action_state"], "eligible")
        self.assertEqual(unready["action_events"], [])
        self.assertEqual(unready["tracking_updates"][0]["confirmation_status"], "pending")

    def test_metric_before_trigger_time_writes_explicit_evaluation_evidence(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T13:40:00+08:00")])
        metric = passing_buy_metric(metric_time="2026-07-02T13:39:00+08:00")
        metric["metric_minute_label"] = "13:39"

        plan = self.build_plan([], active_tracking_rows=first["tracking_updates"], metric_rows=[metric])

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["confirmation_status"], "pending")
        self.assertEqual(
            plan["tracking_updates"][0]["raw_json"]["latest_metric_status"]["reason"],
            "metric_before_trigger_time",
        )

    def test_metric_after_next_unchecked_minute_does_not_skip_cursor(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T09:51:00+08:00")])
        metric = passing_buy_metric(metric_time="2026-07-02T10:00:00+08:00")
        metric["metric_minute_label"] = "10:00"

        plan = self.build_plan([], active_tracking_rows=first["tracking_updates"], metric_rows=[metric])

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["action_state"], "eligible")
        self.assertEqual(plan["tracking_updates"][0]["confirmation_status"], "pending")
        self.assertIn(plan["tracking_updates"][0]["last_checked_minute_label"], (None, ""))
        self.assertEqual(
            plan["tracking_updates"][0]["raw_json"]["latest_metric_status"]["reason"],
            "metric_after_next_unchecked_minute_label",
        )
        ref = plan["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(ref["first_confirmation_minute_label"], "09:51")
        self.assertIsNone(ref["last_checked_minute_label"])
        self.assertEqual(ref["next_unchecked_minute_label"], "09:51")

    def test_pending_evaluation_advances_active_scope_next_unchecked_minute(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T14:01:00+08:00")])
        metric = passing_buy_metric(
            current_30m_virtual_amount=50,
            previous_day_same_window_amount=100,
            metric_time="2026-07-02T14:01:00+08:00",
        )
        metric["metric_minute_label"] = "14:01"
        metric["current_price"] = 9

        plan = self.build_plan([], active_tracking_rows=first["tracking_updates"], metric_rows=[metric])

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["last_checked_minute_label"], "14:01")
        self.assertEqual(plan["tracking_updates"][0]["raw_json"]["next_unchecked_minute_label"], "14:02")
        ref = plan["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(ref["first_confirmation_minute_label"], "14:01")
        self.assertEqual(ref["last_checked_minute_label"], "14:01")
        self.assertEqual(ref["next_unchecked_minute_label"], "14:02")

    def test_n3t_metric_minute_label_drives_cursor_when_close_time_is_next_minute(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T09:44:00+08:00")])
        active = dict(first["tracking_updates"][0])
        active["last_checked_minute_label"] = "09:44"
        raw_json = dict(active.get("raw_json") or {})
        raw_json["next_unchecked_minute_label"] = "09:45"
        active["raw_json"] = raw_json
        metric = passing_buy_metric(metric_time="2026-07-02T09:46:00+08:00")
        metric[
            "projection_run_id"
        ] = "n3t_action_confirmation_metric_20260702_until_0945__fastlane_sr_objecthash_raw_prevday_c1_amount_v1"
        metric["metric_minute_label"] = "09:45"

        plan = poller.build_live_tracking_plan(
            n4_event_rows=[],
            active_tracking_rows=[active],
            metric_rows=[metric],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=metric["projection_run_id"],
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual([event["event_type"] for event in plan["action_events"]], ["ActionExecuted"])
        self.assertEqual(plan["tracking_updates"][0]["last_checked_minute_label"], "09:45")
        trace = plan["tracking_updates"][0]["raw_json"]["confirmation_trace"]
        self.assertEqual(trace["metric_minute_label"], "09:45")
        self.assertEqual(trace["metric_evaluation_minute_label"], "09:45")

    def test_explicit_close_time_evaluation_label_does_not_override_bar_label(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T09:44:00+08:00")])
        active = dict(first["tracking_updates"][0])
        active["last_checked_minute_label"] = "09:44"
        raw_json = dict(active.get("raw_json") or {})
        raw_json["next_unchecked_minute_label"] = "09:45"
        active["raw_json"] = raw_json
        metric = passing_buy_metric(metric_time="2026-07-02T09:46:00+08:00")
        metric[
            "projection_run_id"
        ] = "n3t_action_confirmation_metric_20260702_until_0945__fastlane_sr_objecthash_raw_prevday_c1_amount_v1"
        metric["metric_minute_label"] = "09:45"
        metric["metric_evaluation_minute_label"] = "09:46"

        plan = poller.build_live_tracking_plan(
            n4_event_rows=[],
            active_tracking_rows=[active],
            metric_rows=[metric],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=metric["projection_run_id"],
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual([event["event_type"] for event in plan["action_events"]], ["ActionExecuted"])
        self.assertEqual(plan["tracking_updates"][0]["last_checked_minute_label"], "09:45")
        trace = plan["tracking_updates"][0]["raw_json"]["confirmation_trace"]
        self.assertEqual(trace["metric_minute_label"], "09:45")
        self.assertEqual(trace["metric_evaluation_minute_label"], "09:45")

    def test_n3t_db_metric_close_time_does_not_override_raw_bar_label(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T09:44:00+08:00")])
        active = dict(first["tracking_updates"][0])
        active["last_checked_minute_label"] = "09:44"
        raw_json = dict(active.get("raw_json") or {})
        raw_json["next_unchecked_minute_label"] = "09:45"
        active["raw_json"] = raw_json
        metric = passing_buy_metric(metric_time="2026-07-02T09:45:00+08:00")
        metric["n3t_action_confirmation_metric_id"] = "n3t-metric-0945"
        metric.pop("action_confirmation_metric_id", None)
        metric[
            "projection_run_id"
        ] = "n3t_action_confirmation_metric_20260702_until_0944__fastlane_sr_objecthash_raw_prevday_c1_amount_v1"
        metric["metric_minute_label"] = "09:44"

        plan = poller.build_live_tracking_plan(
            n4_event_rows=[],
            active_tracking_rows=[active],
            metric_rows=[metric],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=metric["projection_run_id"],
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["last_checked_minute_label"], "09:44")
        status = plan["tracking_updates"][0]["raw_json"]["latest_metric_status"]
        self.assertEqual(status["reason"], "metric_before_next_unchecked_minute_label")
        self.assertEqual(status["metric_evaluation_minute_label"], "09:44")

    def test_pending_evaluation_next_unchecked_minute_uses_canonical_session_labels(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T11:29:00+08:00")])
        metric = passing_buy_metric(
            current_30m_virtual_amount=50,
            previous_day_same_window_amount=100,
            metric_time="2026-07-02T11:29:00+08:00",
        )
        metric["metric_minute_label"] = "11:29"
        metric["current_price"] = 9

        plan = self.build_plan([], active_tracking_rows=first["tracking_updates"], metric_rows=[metric])

        ref = plan["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(ref["first_confirmation_minute_label"], "11:29")
        self.assertEqual(ref["last_checked_minute_label"], "11:29")
        self.assertEqual(ref["next_unchecked_minute_label"], "13:00")

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

    def test_repeated_pending_metric_evidence_is_idempotent(self):
        first = self.build_plan([trigger_matched()])
        first_pending = self.build_plan(
            [],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[legacy_n3p_metric()],
        )
        second_pending = self.build_plan(
            [],
            active_tracking_rows=first_pending["tracking_updates"],
            metric_rows=[legacy_n3p_metric()],
        )

        self.assertEqual(first_pending["summary"]["tracking_upsert_count"], 1)
        self.assertEqual(first_pending["action_events"], [])
        self.assertEqual(second_pending["tracking_updates"], [])
        self.assertEqual(second_pending["summary"]["tracking_upsert_count"], 0)
        self.assertEqual(second_pending["action_events"], [])

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

    def test_metric_with_missing_boundary_source_cannot_emit_action_executed(self):
        first = self.build_plan([trigger_matched()])
        metric = passing_buy_metric()
        metric["previous_30m_period_source"] = "not_available"

        plan = self.build_plan(
            [],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[metric],
        )

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["confirmation_status"], "pending")
        self.assertEqual(
            plan["tracking_updates"][0]["raw_json"]["latest_metric_status"]["reason"],
            "missing_previous_session_reference",
        )

    def test_same_day_previous_1m_must_break_before_action_executed(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T10:06:00+08:00")])
        metric = passing_buy_metric(
            current_30m_virtual_amount=Decimal("487826921"),
            previous_day_same_window_amount=Decimal("465168546"),
        )
        metric.update(
            {
                "metric_time": "2026-07-06T10:07:00+08:00",
                "metric_minute_label": "10:06",
                "current_price": Decimal("41.82"),
                "previous_1m_body_high": Decimal("41.82"),
                "current_1m_amount": Decimal("22228156"),
                "previous_1m_amount": Decimal("25728862"),
            }
        )

        plan = self.build_plan(
            [],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[metric],
        )

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["confirmation_status"], "pending")
        self.assertEqual(
            plan["tracking_updates"][0]["raw_json"]["latest_metric_status"]["reason"],
            "price_confirmation_failed",
        )

    def test_final_minute_no_action_metric_terminalizes_tracking_ref(self):
        first = self.build_plan([trigger_matched()])
        active = dict(first["tracking_updates"][0])
        active["last_checked_minute_label"] = "14:58"
        metric = passing_buy_metric(
            current_30m_virtual_amount=Decimal("487826921"),
            previous_day_same_window_amount=Decimal("465168546"),
            metric_time="2026-07-02T15:00:00+08:00",
        )
        metric.update(
            {
                "metric_minute_label": "14:59",
                "current_price": Decimal("41.82"),
                "previous_1m_body_high": Decimal("41.82"),
                "current_1m_amount": Decimal("22228156"),
                "previous_1m_amount": Decimal("25728862"),
            }
        )

        plan = self.build_plan(
            [],
            active_tracking_rows=[active],
            metric_rows=[metric],
        )

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["action_state"], "expired")
        self.assertEqual(plan["tracking_updates"][0]["confirmation_status"], "expired")
        self.assertEqual(plan["tracking_updates"][0]["tracking_status"], "expired")
        self.assertEqual(
            plan["tracking_updates"][0]["expired_reason"],
            "post_close_no_action_final_minute_checked",
        )
        self.assertEqual(plan["active_scope_snapshot_artifact"]["scope_rows"], [])
        self.assertEqual(
            plan["active_scope_snapshot_artifact"]["removed_scope_rows"][0]["scope_exit_reason"],
            "expired",
        )

    def test_metric_missing_after_final_checked_minute_terminalizes_tracking_ref(self):
        first = self.build_plan([trigger_matched()])
        active = dict(first["tracking_updates"][0])
        active["last_checked_minute_label"] = "14:59"

        plan = self.build_plan([], active_tracking_rows=[active], metric_rows=[])

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["action_state"], "expired")
        self.assertEqual(plan["tracking_updates"][0]["confirmation_status"], "expired")
        self.assertEqual(plan["tracking_updates"][0]["tracking_status"], "expired")
        self.assertEqual(
            plan["tracking_updates"][0]["expired_reason"],
            "post_close_no_action_final_minute_checked",
        )

    def test_metric_missing_after_non_confirmable_1500_cursor_terminalizes_tracking_ref(self):
        first = self.build_plan([trigger_matched(event_time="2026-07-02T15:00:00+08:00")])
        active = dict(first["tracking_updates"][0])

        plan = self.build_plan([], active_tracking_rows=[active], metric_rows=[])

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["tracking_updates"][0]["action_state"], "expired")
        self.assertEqual(plan["tracking_updates"][0]["confirmation_status"], "expired")
        self.assertEqual(plan["tracking_updates"][0]["tracking_status"], "expired")
        self.assertEqual(
            plan["tracking_updates"][0]["expired_reason"],
            "post_close_no_action_final_minute_checked",
        )
        latest_metric_status = plan["tracking_updates"][0]["raw_json"]["latest_metric_status"]
        self.assertEqual(latest_metric_status["reason"], "post_close_no_confirmable_minute")
        self.assertEqual(latest_metric_status["metric_minute_label"], "15:00")

    def test_final_minute_unchanged_metric_status_still_terminalizes_tracking_ref(self):
        first = self.build_plan([trigger_matched()])
        metric = passing_buy_metric(
            current_30m_virtual_amount=Decimal("487826921"),
            previous_day_same_window_amount=Decimal("465168546"),
            metric_time="2026-07-02T15:00:00+08:00",
        )
        metric.update(
            {
                "metric_minute_label": "14:59",
                "current_price": Decimal("41.82"),
                "previous_1m_body_high": Decimal("41.82"),
                "current_1m_amount": Decimal("22228156"),
                "previous_1m_amount": Decimal("25728862"),
            }
        )
        initial_evaluation = self.build_plan(
            [],
            active_tracking_rows=first["tracking_updates"],
            metric_rows=[metric],
        )
        active = dict(first["tracking_updates"][0])
        active.update(
            {
                "action_state": "eligible",
                "confirmation_status": "pending",
                "tracking_status": "tracking",
                "last_checked_minute_label": "14:59",
                "raw_json": dict(initial_evaluation["tracking_updates"][0]["raw_json"]),
            }
        )

        plan = self.build_plan([], active_tracking_rows=[active], metric_rows=[metric])

        self.assertEqual(len(plan["tracking_updates"]), 1)
        self.assertEqual(plan["tracking_updates"][0]["action_state"], "expired")
        self.assertEqual(plan["tracking_updates"][0]["confirmation_status"], "expired")
        self.assertEqual(plan["tracking_updates"][0]["tracking_status"], "expired")
        self.assertEqual(
            plan["tracking_updates"][0]["expired_reason"],
            "post_close_no_action_final_minute_checked",
        )

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
        plan = self.build_plan([trigger_matched(event_time="2026-07-02T13:40:00+08:00")])

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
        self.assertEqual(artifact["artifact_schema_version"], "v2")
        self.assertEqual(artifact["scope_granularity"], "object")
        self.assertEqual(artifact["scope_count"], 1)
        scope_row = artifact["scope_rows"][0]
        self.assertEqual(scope_row["for_trade_date"], TRADE_DATE)
        self.assertEqual(scope_row["asset_kind"], "stock")
        self.assertEqual(scope_row["identity_key"], "stock:SH:600000")
        self.assertEqual(scope_row["scope_status"], "active")
        self.assertEqual(scope_row["attention_event_refs"], [])
        self.assertEqual(len(scope_row["active_tracking_refs"]), 1)
        active_ref = scope_row["active_tracking_refs"][0]
        self.assertEqual(active_ref["condition_key"], "BUY_MAIN")
        self.assertEqual(active_ref["source_trigger_event_id"], "n4-match-1")
        self.assertEqual(active_ref["source_trigger_run_id"], SOURCE_TRIGGER_RUN_ID)
        self.assertEqual(
            active_ref["state_key"],
            "N5_action_tracking_state_v1|trade_date|20260702|asset_kind|stock|identity_key|stock:SH:600000|direction|buy|signal_type|B_BUY|condition_key|BUY_MAIN",
        )
        self.assertEqual(active_ref["trigger_time"], "2026-07-02T13:40:00+08:00")
        self.assertEqual(active_ref["source_trigger_event_time"], "2026-07-02T13:40:00+08:00")
        self.assertEqual(active_ref["latest_n4_event_time"], "2026-07-02T13:40:00+08:00")
        self.assertEqual(active_ref["first_confirmation_minute_label"], "13:40")
        self.assertIsNone(active_ref["last_checked_minute_label"])
        self.assertIn("latest_metric_status", active_ref)
        self.assertEqual(active_ref["metric_evaluation_key"], "")
        self.assertEqual(active_ref["last_seen_metric_key"], "")
        self.assertEqual(active_ref["action_state"], "eligible")
        self.assertEqual(active_ref["confirmation_status"], "pending")
        self.assertEqual(active_ref["tracking_status"], "tracking")

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

    def test_active_scope_snapshot_does_not_reactivate_terminal_db_ref_from_stale_update(self):
        first = self.build_plan([trigger_matched()])
        stale_active_row = first["tracking_updates"][0]

        refreshed = self.build_plan(
            [],
            active_tracking_rows=[stale_active_row],
            active_scope_tracking_rows=[],
        )

        artifact = refreshed["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["scope_rows"], [])
        self.assertEqual(artifact["active_tracking_ref_count"], 0)
        self.assertEqual(artifact["scope_status"], "empty")

    def test_trigger_state_changed_true_does_not_reactivate_terminal_tracking_ref(self):
        match = trigger_matched()
        executed = self.build_plan([match], metric_rows=[passing_buy_metric()])
        executed_state = next(
            row for row in executed["tracking_updates"] if row["action_state"] == "executed"
        )

        refreshed = self.build_plan(
            [trigger_state_changed_true(match, event_time="2026-07-02T10:05:00+08:00")],
            active_tracking_rows=[executed_state],
            active_scope_tracking_rows=[],
        )

        self.assertEqual(refreshed["tracking_updates"], [])
        artifact = refreshed["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["scope_rows"], [])
        self.assertEqual(artifact["active_tracking_ref_count"], 0)
        self.assertEqual(artifact["scope_status"], "empty")

    def test_active_scope_snapshot_keeps_new_n4_ref_when_db_active_scope_is_authoritative(self):
        plan = self.build_plan(
            [trigger_matched()],
            active_scope_tracking_rows=[],
        )

        artifact = plan["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["scope_count"], 1)
        self.assertEqual(artifact["active_tracking_ref_count"], 1)
        ref = artifact["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(ref["source_trigger_event_id"], "n4-match-1")
        self.assertEqual(ref["action_state"], "eligible")

    def test_rebuild_active_set_a_from_day_events_replays_tsc_true_after_executed(self):
        match = trigger_matched(
            "n4-match-0955",
            identity_key="stock:SZ:301269",
            condition_key="BUY:Y,M,W,D",
            event_time="2026-07-02T09:55:00+08:00",
        )
        early_true = trigger_state_changed_true(
            match,
            "n4-state-true-1304",
            event_time="2026-07-02T13:04:00+08:00",
        )
        latest_true = trigger_state_changed_true(
            match,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        latest_true["payload_json"] = {
            **latest_true["payload_json"],
            "trigger_price": 119.27,
            "triggered_periods": ["D"],
            "condition_key": "BUY:Y,M,W,D",
        }

        rebuilt = poller.build_active_set_a_rebuild_from_n4_day_events(
            n4_event_rows=[match, early_true, latest_true],
            action_executed_event_rows=[
                action_executed_event(match, event_time="2026-07-02T09:56:00+08:00")
            ],
            for_trade_date=TRADE_DATE,
            action_run_id="n5_live_tracking_20260702__active_set_a__fastlane_v1",
            consumer_name=CONSUMER_NAME,
            current_exchange_time="2026-07-02T15:00:00+08:00",
        )

        artifact = rebuilt["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["artifact_type"], "n5_active_scope_snapshot_v1")
        self.assertEqual(artifact["rebuild_mode"], "post_close_final_a_rebuild_from_n4_day_events")
        self.assertEqual(artifact["scope_granularity"], "object")
        self.assertEqual(artifact["scope_count"], 1)
        self.assertEqual(artifact["active_tracking_ref_count"], 1)
        ref = artifact["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(ref["identity_key"], "stock:SZ:301269")
        self.assertEqual(ref["source_trigger_event_id"], "n4-state-true-1352")
        self.assertEqual(ref["source_trigger_event_type"], "TriggerStateChanged")
        self.assertEqual(ref["trigger_time"], "2026-07-02T13:52:00+08:00")
        self.assertEqual(ref["first_confirmation_minute_label"], "13:52")
        self.assertFalse(ref["action_eligible_entry_allowed"])
        self.assertIsNone(ref["planned_output_event_type"])
        self.assertEqual(ref["source_n4_payload"]["trigger_price"], 119.27)
        self.assertEqual(ref["source_n4_payload"]["triggered_periods"], ["D"])
        self.assertFalse(artifact["boundary"]["n4_outbox_updated"])
        self.assertFalse(artifact["boundary"]["inbox_checkpoint_written"])
        self.assertFalse(artifact["boundary"]["db_written"])
        self.assertFalse(artifact["boundary"]["n6_touched"])
        self.assertEqual(rebuilt["summary"]["action_executed_removed_ref_count"], 1)
        self.assertEqual(rebuilt["summary"]["active_ref_count"], 1)
        self.assertEqual(rebuilt["consumed_n4_event_ids"], [])
        self.assertEqual(rebuilt["inbox_checkpoint_intent"]["source_event_ids"], [])

    def test_rebuild_active_set_a_removes_tsc_false_and_isolates_trade_date(self):
        match = trigger_matched("n4-match-0955", condition_key="BUY:Y,M,W,D")
        latest_true = trigger_state_changed_true(match, "n4-state-true-1352", event_time="2026-07-02T13:52:00+08:00")
        false_row = trigger_state_changed_false(match, "n4-state-false-1400")
        false_row["event_time"] = "2026-07-02T14:00:00+08:00"
        other_date = trigger_state_changed_true(match, "n4-state-true-other-date", event_time="2026-07-03T13:52:00+08:00")
        other_date["trade_date"] = "20260703"
        other_date["payload_json"] = {**other_date["payload_json"], "trade_date": "20260703"}

        rebuilt = poller.build_active_set_a_rebuild_from_n4_day_events(
            n4_event_rows=[match, latest_true, false_row, other_date],
            action_executed_event_rows=[],
            for_trade_date=TRADE_DATE,
            action_run_id="n5_live_tracking_20260702__active_set_a__fastlane_v1",
            consumer_name=CONSUMER_NAME,
            current_exchange_time="2026-07-02T15:00:00+08:00",
        )

        artifact = rebuilt["active_scope_snapshot_artifact"]
        self.assertEqual(artifact["scope_count"], 0)
        self.assertEqual(artifact["scope_rows"], [])
        self.assertEqual(rebuilt["summary"]["removed_by_tsc_false_count"], 1)
        self.assertEqual(rebuilt["summary"]["ignored_other_trade_date_count"], 1)

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

    def test_fastlane_intake_active_set_a_does_not_require_single_source_trigger_run(self):
        calls = {"provider": 0}

        def provider(args):
            calls["provider"] += 1
            self.assertEqual(args.fastlane_phase, "intake")
            self.assertEqual(args.n5_intake_event_kind, "active_set_a")
            self.assertEqual(args.source_trigger_run_id, "")
            row = trigger_state_changed_true(
                trigger_matched(event_time="2026-07-02T13:40:00+08:00"),
                "n4-state-true-active-set",
                event_time="2026-07-02T13:52:00+08:00",
            )
            row["source_run_id"] = "trigger_state_changed_true_20260702_1352"
            return poller.build_live_tracking_plan(
                n4_event_rows=[row],
                active_tracking_rows=[],
                metric_rows=[],
                action_run_id=args.action_run_id,
                source_trigger_run_id=args.source_trigger_run_id,
                source_metric_run_id=args.source_metric_run_id,
                consumer_name=args.consumer_name,
                for_trade_date=args.for_trade_date,
            )

        manifest = poller_script.run_n5_live_tracking_poller_once(
            [
                "--for-trade-date",
                TRADE_DATE,
                "--action-run-id",
                "n5-active-set-a-run",
                "--consumer-name",
                CONSUMER_NAME,
                "--max-events",
                "10",
                "--max-runtime-seconds",
                "30",
                "--fastlane-phase",
                "intake",
                "--n5-intake-event-kind",
                "active_set_a",
            ],
            plan_provider=provider,
        )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_PLAN_ONLY")
        self.assertEqual(manifest["source_trigger_run_id"], "")
        self.assertEqual(calls["provider"], 1)
        ref = manifest["plan"]["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(ref["source_trigger_event_type"], "TriggerStateChanged")
        self.assertEqual(ref["source_trigger_event_time"], "2026-07-02T13:52:00+08:00")

    def test_executed_discovery_uses_next_available_object_minute_proof_when_ref_hash_differs(self):
        cursor = ExecutedObjectMinuteDiscoveryCursor()

        with patch.object(
            poller_script,
            "_build_executed_candidate_plan",
            return_value={"summary": {"action_executed_count": 1, "tracking_upsert_count": 1}},
        ) as build_plan:
            runtime_inputs = poller_script._discover_executed_runtime_inputs(
                cursor,
                SimpleNamespace(for_trade_date=TRADE_DATE),
            )

        self.assertEqual(
            runtime_inputs["source_metric_run_id"],
            "n3t_action_confirmation_metric_20260702_until_1411__fastlane_sr_objecthash_raw_prevday_c1_amount_v1",
        )
        self.assertEqual(runtime_inputs["action_run_id"], ACTION_RUN_ID)
        self.assertEqual(runtime_inputs["state_key"], "state-key-with-different-hash")
        self.assertEqual(cursor.object_minute_params[:3], (TRADE_DATE, "stock:SH:600000", "14:11"))
        build_plan.assert_called_once()

    def test_executed_discovery_uses_latest_active_scope_ref_hash_when_source_trigger_run_id_exists(self):
        metric_run_id = (
            "n3t_action_confirmation_metric_20260702_until_1021"
            "__fastlane_sr_objecthash_raw_prevday_c1_amount_v1"
        )

        class LatestActiveScopeCursor:
            def __init__(self):
                self.object_minute_params = None
                self._rows = []

            def execute(self, sql, params):
                if "projection_run_id LIKE" in sql:
                    self._rows = []
                    return
                if "identity_key = %s" in sql and "source_basis = 'N3T_C1_CLOSED'" in sql:
                    self.object_minute_params = params
                    self._rows = [
                        {
                            "metric_minute_label": "10:21",
                            "projection_run_id": metric_run_id,
                        }
                    ]
                    return
                self._rows = []

            def fetchall(self):
                return list(self._rows)

            def fetchone(self):
                return self._rows[0] if self._rows else None

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1_20260702_latest.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": TRADE_DATE,
                        "action_run_id": ACTION_RUN_ID,
                        "scope_rows": [
                            {
                                "for_trade_date": TRADE_DATE,
                                "asset_kind": "stock",
                                "identity_key": "stock:SZ:002745",
                                "active_tracking_refs": [
                                    {
                                        "action_state": "eligible",
                                        "tracking_status": "tracking",
                                        "confirmation_status": "pending",
                                        "condition_key": "BUY:M,W,D",
                                        "direction": "buy",
                                        "signal_type": "B_BUY",
                                        "source_trigger_run_id": "trigger_provisional_ordinary_20260702_until_0951",
                                        "source_trigger_event_id": "evt-n4-002745",
                                        "source_trigger_event_time": "2026-07-02T10:21:00+08:00",
                                        "trigger_time": "2026-07-02T10:21:00+08:00",
                                        "state_key": "state-key-002745",
                                        "source_run_hash": "objecthash",
                                        "next_unchecked_minute_label": "10:21",
                                    }
                                ],
                            }
                        ],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            cursor = LatestActiveScopeCursor()
            with patch.object(
                poller_script,
                "_build_executed_candidate_plan",
                return_value={"summary": {"action_executed_count": 1, "tracking_upsert_count": 1}},
            ) as build_plan:
                runtime_inputs = poller_script._discover_executed_runtime_inputs(
                    cursor,
                    SimpleNamespace(
                        for_trade_date=TRADE_DATE,
                        fastlane_phase="executed",
                        active_scope_artifact_dir=tmpdir,
                    ),
                )

        self.assertEqual(runtime_inputs["state_key"], "state-key-002745")
        self.assertEqual(runtime_inputs["source_metric_run_id"], metric_run_id)
        self.assertEqual(cursor.object_minute_params[:3], (TRADE_DATE, "stock:SZ:002745", "10:21"))
        build_plan.assert_called_once()

    def test_active_scope_artifact_rows_use_object_minute_hash_not_shared_n4_run_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1_20260702_latest.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "n5_active_scope_snapshot_v1",
                        "for_trade_date": TRADE_DATE,
                        "action_run_id": ACTION_RUN_ID,
                        "scope_rows": [
                            {
                                "for_trade_date": TRADE_DATE,
                                "asset_kind": "board",
                                "identity_key": "board:TDX:881224",
                                "active_tracking_refs": [
                                    {
                                        "action_state": "eligible",
                                        "tracking_status": "tracking",
                                        "confirmation_status": "pending",
                                        "condition_key": "SELL:Q,M,D",
                                        "direction": "sell",
                                        "signal_type": "S_SELL",
                                        "source_trigger_run_id": "trigger_provisional_ordinary_20260702_until_0951",
                                        "source_trigger_event_id": "evt-board-881224",
                                        "source_trigger_event_time": "2026-07-02T09:51:00+08:00",
                                        "trigger_time": "2026-07-02T09:51:00+08:00",
                                        "state_key": "state-key-881224",
                                        "source_run_hash": "sharedn4hash",
                                        "next_unchecked_minute_label": "09:51",
                                    }
                                ],
                            },
                            {
                                "for_trade_date": TRADE_DATE,
                                "asset_kind": "stock",
                                "identity_key": "stock:SZ:002745",
                                "active_tracking_refs": [
                                    {
                                        "action_state": "eligible",
                                        "tracking_status": "tracking",
                                        "confirmation_status": "pending",
                                        "condition_key": "BUY:M,W,D",
                                        "direction": "buy",
                                        "signal_type": "B_BUY",
                                        "source_trigger_run_id": "trigger_provisional_ordinary_20260702_until_0951",
                                        "source_trigger_event_id": "evt-stock-002745",
                                        "source_trigger_event_time": "2026-07-02T10:21:00+08:00",
                                        "trigger_time": "2026-07-02T10:21:00+08:00",
                                        "state_key": "state-key-002745",
                                        "source_run_hash": "sharedn4hash",
                                        "next_unchecked_minute_label": "10:21",
                                    }
                                ],
                            },
                        ],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            rows = poller_script._load_active_scope_tracking_rows_from_path(
                artifact_path,
                missing_reason="missing",
            )
            candidates = poller_script._active_scope_rows_to_executed_candidates(
                SimpleNamespace(for_trade_date=TRADE_DATE, action_run_id=ACTION_RUN_ID),
                rows,
            )

        by_identity = {candidate["identity_key"]: candidate for candidate in candidates}
        self.assertEqual(set(by_identity), {"board:TDX:881224", "stock:SZ:002745"})
        board_hash = by_identity["board:TDX:881224"]["source_run_hash"]
        stock_hash = by_identity["stock:SZ:002745"]["source_run_hash"]
        self.assertNotEqual(board_hash, "sharedn4hash")
        self.assertNotEqual(stock_hash, "sharedn4hash")
        self.assertNotEqual(board_hash, stock_hash)

    def test_executed_discovery_batches_multiple_ready_refs(self):
        class TwoReadyCursor:
            def __init__(self):
                self._rows = []
                self._row = None

            def execute(self, sql, params):
                if "WITH active_tracking AS" in sql:
                    self._rows = [
                        {
                            "run_id": ACTION_RUN_ID,
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600000",
                            "direction": "buy",
                            "signal_type": "B_BUY",
                            "condition_key": "BUY_MAIN",
                            "source_trigger_run_id": "",
                            "source_trigger_event_id": "evt-n4-match-1",
                            "state_key": "state-key-1",
                            "trigger_time": "2026-07-02T10:00:00+08:00",
                            "latest_n4_event_time": "2026-07-02T10:00:00+08:00",
                            "last_checked_minute_label": "",
                            "next_unchecked_minute_label": "10:00",
                            "raw_json": {},
                            "source_run_hash": "",
                            "active_tracking_count": 1,
                        },
                        {
                            "run_id": ACTION_RUN_ID,
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600001",
                            "direction": "buy",
                            "signal_type": "B_BUY",
                            "condition_key": "BUY_MAIN",
                            "source_trigger_run_id": "",
                            "source_trigger_event_id": "evt-n4-match-2",
                            "state_key": "state-key-2",
                            "trigger_time": "2026-07-02T10:00:00+08:00",
                            "latest_n4_event_time": "2026-07-02T10:00:00+08:00",
                            "last_checked_minute_label": "",
                            "next_unchecked_minute_label": "10:00",
                            "raw_json": {},
                            "source_run_hash": "",
                            "active_tracking_count": 1,
                        },
                    ]
                    self._row = None
                    return
                if "projection_run_id LIKE" in sql:
                    self._rows = []
                    self._row = None
                    return
                if "identity_key = %s" in sql and "source_basis = 'N3T_C1_CLOSED'" in sql:
                    identity_key = params[1]
                    suffix = "0001" if identity_key.endswith("600001") else "0000"
                    run_id = (
                        "n3t_action_confirmation_metric_20260702_until_1000"
                        f"__fastlane_sr_objecthash_{suffix}_raw_prevday_c1_amount_v1"
                    )
                    self._rows = [
                        {
                            "metric_minute_label": "10:00",
                            "metric_evaluation_minute_label": "10:00",
                            "projection_run_id": run_id,
                        }
                    ]
                    self._row = None
                    return
                self._rows = []
                self._row = None

            def fetchall(self):
                return list(self._rows)

            def fetchone(self):
                return self._row

        cursor = TwoReadyCursor()

        with patch.object(
            poller_script,
            "_build_executed_candidate_plan",
            return_value={"summary": {"action_executed_count": 1, "tracking_upsert_count": 1}},
        ) as build_plan:
            runtime_inputs = poller_script._discover_executed_runtime_inputs(
                cursor,
                SimpleNamespace(for_trade_date=TRADE_DATE, max_events=0),
            )

        self.assertEqual(runtime_inputs["state_key"], poller_script.FASTLANE_EXECUTED_BATCH_STATE_KEY)
        self.assertEqual(len(runtime_inputs["fastlane_executed_batch_candidates"]), 2)
        self.assertIn("objecthash_0000", runtime_inputs["source_metric_run_id"])
        self.assertIn("objecthash_0001", runtime_inputs["source_metric_run_id"])
        self.assertEqual(build_plan.call_count, 2)

    def test_executed_discovery_batches_evaluation_only_ready_refs(self):
        class TwoReadyCursor:
            def __init__(self):
                self._rows = []
                self._row = None

            def execute(self, sql, params):
                if "WITH active_tracking AS" in sql:
                    self._rows = [
                        {
                            "run_id": ACTION_RUN_ID,
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600000",
                            "direction": "buy",
                            "signal_type": "B_BUY",
                            "condition_key": "BUY_MAIN",
                            "source_trigger_run_id": "",
                            "source_trigger_event_id": "evt-n4-match-1",
                            "state_key": "state-key-1",
                            "trigger_time": "2026-07-02T10:00:00+08:00",
                            "latest_n4_event_time": "2026-07-02T10:00:00+08:00",
                            "last_checked_minute_label": "",
                            "next_unchecked_minute_label": "10:00",
                            "raw_json": {},
                            "source_run_hash": "",
                            "active_tracking_count": 1,
                        },
                        {
                            "run_id": ACTION_RUN_ID,
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600001",
                            "direction": "buy",
                            "signal_type": "B_BUY",
                            "condition_key": "BUY_MAIN",
                            "source_trigger_run_id": "",
                            "source_trigger_event_id": "evt-n4-match-2",
                            "state_key": "state-key-2",
                            "trigger_time": "2026-07-02T10:00:00+08:00",
                            "latest_n4_event_time": "2026-07-02T10:00:00+08:00",
                            "last_checked_minute_label": "",
                            "next_unchecked_minute_label": "10:00",
                            "raw_json": {},
                            "source_run_hash": "",
                            "active_tracking_count": 1,
                        },
                    ]
                    self._row = None
                    return
                if "projection_run_id LIKE" in sql:
                    self._rows = []
                    self._row = None
                    return
                if "identity_key = %s" in sql and "source_basis = 'N3T_C1_CLOSED'" in sql:
                    identity_key = params[1]
                    suffix = "0001" if identity_key.endswith("600001") else "0000"
                    self._rows = [
                        {
                            "metric_minute_label": "10:00",
                            "metric_evaluation_minute_label": "10:00",
                            "projection_run_id": (
                                "n3t_action_confirmation_metric_20260702_until_1000"
                                f"__fastlane_sr_objecthash_{suffix}_raw_prevday_c1_amount_v1"
                            ),
                        }
                    ]
                    self._row = None
                    return
                self._rows = []
                self._row = None

            def fetchall(self):
                return list(self._rows)

            def fetchone(self):
                return self._row

        cursor = TwoReadyCursor()

        with patch.object(
            poller_script,
            "_build_executed_candidate_plan",
            return_value={"summary": {"action_executed_count": 0, "tracking_upsert_count": 1}},
        ) as build_plan:
            runtime_inputs = poller_script._discover_executed_runtime_inputs(
                cursor,
                SimpleNamespace(for_trade_date=TRADE_DATE, max_events=0),
            )

        self.assertEqual(runtime_inputs["state_key"], poller_script.FASTLANE_EXECUTED_BATCH_STATE_KEY)
        self.assertEqual(len(runtime_inputs["fastlane_executed_batch_candidates"]), 2)
        self.assertEqual(build_plan.call_count, 2)

    def test_executed_discovery_prioritizes_realtime_ready_refs_before_stale_reevaluation(self):
        class StaleAndReadyCursor:
            def __init__(self):
                self._rows = []
                self._row = None
                self.stale_query_count = 0

            def execute(self, sql, params):
                if "WITH active_tracking AS" in sql:
                    self._rows = [
                        {
                            "run_id": ACTION_RUN_ID,
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600000",
                            "direction": "buy",
                            "signal_type": "B_BUY",
                            "condition_key": "BUY_MAIN",
                            "source_trigger_run_id": "",
                            "source_trigger_event_id": "evt-n4-match-1",
                            "state_key": "state-key-ready-1",
                            "trigger_time": "2026-07-02T10:00:00+08:00",
                            "latest_n4_event_time": "2026-07-02T10:00:00+08:00",
                            "last_checked_minute_label": "",
                            "next_unchecked_minute_label": "10:00",
                            "raw_json": {},
                            "source_run_hash": "",
                            "active_tracking_count": 1,
                        },
                        {
                            "run_id": ACTION_RUN_ID,
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600001",
                            "direction": "buy",
                            "signal_type": "B_BUY",
                            "condition_key": "BUY_MAIN",
                            "source_trigger_run_id": "",
                            "source_trigger_event_id": "evt-n4-match-2",
                            "state_key": "state-key-ready-2",
                            "trigger_time": "2026-07-02T10:00:00+08:00",
                            "latest_n4_event_time": "2026-07-02T10:00:00+08:00",
                            "last_checked_minute_label": "",
                            "next_unchecked_minute_label": "10:00",
                            "raw_json": {},
                            "source_run_hash": "",
                            "active_tracking_count": 1,
                        },
                    ]
                    self._row = None
                    return
                if "WITH stale_tracking" in sql:
                    self.stale_query_count += 1
                    self._rows = [
                        {
                            "run_id": ACTION_RUN_ID,
                            "asset_kind": "stock",
                            "identity_key": "stock:SH:600009",
                            "direction": "buy",
                            "signal_type": "B_BUY",
                            "condition_key": "BUY_MAIN",
                            "source_trigger_run_id": "",
                            "source_trigger_event_id": "evt-n4-stale",
                            "state_key": "state-key-stale",
                            "trigger_time": "2026-07-02T09:44:00+08:00",
                            "latest_n4_event_time": "2026-07-02T09:44:00+08:00",
                            "last_checked_minute_label": "09:59",
                            "next_unchecked_minute_label": "10:00",
                            "raw_json": {},
                            "source_run_hash": "stalehash",
                            "active_tracking_count": 1,
                            "target_minute_label": "10:00",
                            "source_metric_run_id": (
                                "n3t_action_confirmation_metric_20260702_until_1000"
                                "__fastlane_sr_stalehash_raw_prevday_c1_amount_v1"
                            ),
                        }
                    ]
                    self._row = None
                    return
                if "projection_run_id LIKE" in sql:
                    self._rows = []
                    self._row = None
                    return
                if "identity_key = %s" in sql and "source_basis = 'N3T_C1_CLOSED'" in sql:
                    identity_key = params[1]
                    suffix = "0001" if identity_key.endswith("600001") else "0000"
                    self._rows = [
                        {
                            "metric_minute_label": "10:00",
                            "metric_evaluation_minute_label": "10:00",
                            "projection_run_id": (
                                "n3t_action_confirmation_metric_20260702_until_1000"
                                f"__fastlane_sr_objecthash_{suffix}_raw_prevday_c1_amount_v1"
                            ),
                        }
                    ]
                    self._row = None
                    return
                self._rows = []
                self._row = None

            def fetchall(self):
                return list(self._rows)

            def fetchone(self):
                return self._row

        cursor = StaleAndReadyCursor()

        with patch.object(
            poller_script,
            "_build_executed_candidate_plan",
            return_value={"summary": {"action_executed_count": 1, "tracking_upsert_count": 1}},
        ) as build_plan:
            runtime_inputs = poller_script._discover_executed_runtime_inputs(
                cursor,
                SimpleNamespace(for_trade_date=TRADE_DATE, max_events=0),
            )

        self.assertEqual(runtime_inputs["state_key"], poller_script.FASTLANE_EXECUTED_BATCH_STATE_KEY)
        self.assertEqual(len(runtime_inputs["fastlane_executed_batch_candidates"]), 2)
        self.assertEqual(cursor.stale_query_count, 0)
        self.assertEqual(build_plan.call_count, 2)

    def test_executed_batch_plan_consumes_multiple_ready_refs(self):
        active_1 = poller.build_live_tracking_plan(
            n4_event_rows=[trigger_matched(event_id="n4-match-1", identity_key="stock:SH:600000")],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id="",
            source_metric_run_id="",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )["tracking_updates"][0]
        active_2 = poller.build_live_tracking_plan(
            n4_event_rows=[trigger_matched(event_id="n4-match-2", identity_key="stock:SH:600001")],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id="",
            source_metric_run_id="",
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )["tracking_updates"][0]
        metric_1 = passing_buy_metric(metric_id=601)
        metric_1["projection_run_id"] = (
            "n3t_action_confirmation_metric_20260702_until_1000__fastlane_sr_objecthash_0000_raw_prevday_c1_amount_v1"
        )
        metric_1["identity_key"] = "stock:SH:600000"
        metric_1["n3t_action_confirmation_metric_id"] = 601
        metric_2 = passing_buy_metric(metric_id=602)
        metric_2["projection_run_id"] = (
            "n3t_action_confirmation_metric_20260702_until_1000__fastlane_sr_objecthash_0001_raw_prevday_c1_amount_v1"
        )
        metric_2["identity_key"] = "stock:SH:600001"
        metric_2["n3t_action_confirmation_metric_id"] = 602

        class BatchCursor:
            def __init__(self):
                self._rows = []

            def execute(self, sql, params):
                if "SELECT dedup_key" in sql:
                    self._rows = []
                    return
                if "projection_run_id = ANY" in sql and "stock_n3t_action_confirmation_metric" in sql:
                    wanted = set(params[0])
                    self._rows = [
                        row for row in (metric_1, metric_2) if row["projection_run_id"] in wanted
                    ]
                    return
                if "state_key = ANY" in sql:
                    wanted = set(params[2])
                    self._rows = [
                        row for row in (active_1, active_2) if row["state_key"] in wanted
                    ]
                    return
                if "FROM common_action_tracking_state" in sql:
                    self._rows = [active_1, active_2]
                    return
                self._rows = []

            def fetchall(self):
                return list(self._rows)

        candidates = [
            {
                "run_id": ACTION_RUN_ID,
                "state_key": active_1["state_key"],
                "source_metric_run_id": metric_1["projection_run_id"],
            },
            {
                "run_id": ACTION_RUN_ID,
                "state_key": active_2["state_key"],
                "source_metric_run_id": metric_2["projection_run_id"],
            },
        ]

        plan = poller_script._build_executed_batch_candidate_plan(
            BatchCursor(),
            SimpleNamespace(for_trade_date=TRADE_DATE, consumer_name=CONSUMER_NAME),
            candidates,
        )

        self.assertEqual(plan["summary"]["action_executed_count"], 2)
        self.assertEqual(plan["summary"]["tracking_upsert_count"], 2)

    def test_object_minute_discovery_does_not_skip_cursor_gap(self):
        class GapCursor:
            def __init__(self):
                self.params = None

            def execute(self, _sql, params):
                self.params = params

            def fetchall(self):
                return [
                    {
                        "metric_minute_label": "14:59",
                        "projection_run_id": "n3t_action_confirmation_metric_20260702_until_1459__fastlane_sr_objecthash_raw_prevday_c1_amount_v1",
                    }
                ]

        cursor = GapCursor()

        run_ids = poller_script._discover_ready_object_minute_n3t_metric_run_ids(
            cursor,
            TRADE_DATE,
            candidate={"asset_kind": "stock", "identity_key": "stock:SH:600000"},
            target_minute_label="14:47",
            limit=64,
        )

        self.assertEqual(cursor.params[:3], (TRADE_DATE, "stock:SH:600000", "14:47"))
        self.assertEqual(run_ids, [])

    def test_object_minute_discovery_uses_bar_label_not_close_time_label(self):
        class RawPreviousLabelCursor:
            def __init__(self):
                self.params = None

            def execute(self, _sql, params):
                self.params = params
                self.sql = _sql

            def fetchall(self):
                return [
                    {
                        "metric_minute_label": "09:45",
                        "metric_time": "2026-07-02T09:46:00+08:00",
                        "metric_evaluation_minute_label": "09:46",
                        "projection_run_id": "n3t_action_confirmation_metric_20260702_until_0945__fastlane_sr_objecthash_raw_prevday_c1_amount_v1",
                    }
                ]

        cursor = RawPreviousLabelCursor()

        run_ids = poller_script._discover_ready_object_minute_n3t_metric_run_ids(
            cursor,
            TRADE_DATE,
            candidate={"asset_kind": "stock", "identity_key": "stock:SH:600000"},
            target_minute_label="09:45",
            limit=64,
        )

        self.assertEqual(cursor.params[:3], (TRADE_DATE, "stock:SH:600000", "09:45"))
        self.assertIn("metric_minute_label", cursor.sql)
        self.assertEqual(
            run_ids,
            ["n3t_action_confirmation_metric_20260702_until_0945__fastlane_sr_objecthash_raw_prevday_c1_amount_v1"],
        )

    def test_executed_discovery_selects_final_checked_no_action_ref_before_noop(self):
        cursor = ExecutedFinalNoActionDiscoveryCursor()

        with patch.object(
            poller_script,
            "_build_executed_candidate_plan",
            return_value={"summary": {"action_executed_count": 0, "tracking_upsert_count": 1}},
        ) as build_plan:
            runtime_inputs = poller_script._discover_executed_runtime_inputs(
                cursor,
                SimpleNamespace(for_trade_date=TRADE_DATE),
            )

        self.assertEqual(runtime_inputs["action_run_id"], ACTION_RUN_ID)
        self.assertEqual(runtime_inputs["state_key"], "state-key-final-no-action")
        self.assertEqual(
            runtime_inputs["source_metric_run_id"],
            "n3t_action_confirmation_metric_20260702_until_1459__fastlane_sr_final_raw_prevday_c1_amount_v1",
        )
        self.assertFalse(cursor.reached_broad_scan)
        build_plan.assert_called_once()

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

    def test_executed_phase_explicit_active_scope_artifact_is_authoritative_input(self):
        state_key = poller.build_action_tracking_state_key(
            trade_date=TRADE_DATE,
            asset_kind="stock",
            identity_key="stock:SH:600000",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_MAIN",
        )
        active_ref = {
            "run_id": ACTION_RUN_ID,
            "state_key": state_key,
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": "BUY_MAIN",
            "trigger_live": True,
            "current_status": "matched",
            "latest_n4_event_time": "2026-07-02T10:00:00+08:00",
            "action_state": "eligible",
            "confirmation_status": "pending",
            "tracking_status": "tracking",
            "planned_output_event_type": "ActionEligible",
            "last_checked_minute_label": None,
            "raw_json": {
                "source_n4_payload": {
                    "trigger_time": "2026-07-02T10:00:00+08:00",
                    "condition_key": "BUY_MAIN",
                }
            },
        }
        artifact = {
            "artifact_type": "n5_active_scope_snapshot_v1",
            "for_trade_date": TRADE_DATE,
            "scope_rows": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "active_tracking_refs": [active_ref],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            args = SimpleNamespace(
                dsn="postgresql:///unused",
                fastlane_phase="executed",
                active_scope_artifact_path=str(artifact_path),
                for_trade_date=TRADE_DATE,
                source_metric_run_id=SOURCE_METRIC_RUN_ID,
                source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
                action_run_id=ACTION_RUN_ID,
                consumer_name=CONSUMER_NAME,
            )

            with (
                patch.object(poller_script.psycopg, "connect") as connect,
                patch.object(poller_script, "_fetch_active_tracking_rows", return_value=[]),
                patch.object(poller_script, "_fetch_active_scope_tracking_rows", return_value=[]),
                patch.object(poller_script, "_fetch_metric_rows", return_value=[]),
                patch.object(poller_script, "_fetch_existing_action_event_keys", return_value=set()),
                patch.object(
                    poller_script,
                    "build_live_tracking_plan",
                    return_value={"summary": {"tracking_upsert_count": 0, "action_executed_count": 0}},
                ) as build_plan,
            ):
                class FakeConnection:
                    def __enter__(self):
                        return self

                    def __exit__(self, *_exc):
                        return False

                    def cursor(self):
                        return self

                connect.return_value = FakeConnection()
                poller_script._default_plan_provider(args)

        kwargs = build_plan.call_args.kwargs
        self.assertEqual(kwargs["active_tracking_rows"][0]["state_key"], state_key)
        self.assertEqual(kwargs["active_tracking_rows"][0]["trade_date"], TRADE_DATE)
        self.assertEqual(kwargs["active_scope_tracking_rows"][0]["state_key"], state_key)

    def test_executed_discovery_builds_candidates_from_explicit_active_scope_artifact(self):
        state_key = poller.build_action_tracking_state_key(
            trade_date=TRADE_DATE,
            asset_kind="stock",
            identity_key="stock:SH:600000",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_MAIN",
        )
        active_ref = {
            "run_id": ACTION_RUN_ID,
            "state_key": state_key,
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": "BUY_MAIN",
            "latest_n4_event_time": "2026-07-02T09:51:00+08:00",
            "action_state": "eligible",
            "confirmation_status": "pending",
            "tracking_status": "tracking",
            "last_checked_minute_label": "09:59",
            "raw_json": {
                "next_unchecked_minute_label": "10:00",
                "source_run_hash": "refhash1000",
            },
        }
        artifact = {
            "artifact_type": "n5_active_scope_snapshot_v1",
            "for_trade_date": TRADE_DATE,
            "action_run_id": ACTION_RUN_ID,
            "scope_rows": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "active_tracking_refs": [active_ref],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            args = SimpleNamespace(
                fastlane_phase="executed",
                active_scope_artifact_path=str(artifact_path),
                for_trade_date=TRADE_DATE,
                action_run_id=ACTION_RUN_ID,
            )

            candidates = poller_script._explicit_active_scope_executed_candidates(args)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["state_key"], state_key)
        self.assertEqual(candidates[0]["target_minute_label"], "1000")
        self.assertNotEqual(candidates[0]["source_run_hash"], "refhash1000")
        self.assertEqual(candidates[0]["raw_json"]["source_run_hash"], "refhash1000")
        self.assertEqual(
            candidates[0]["source_run_hash"],
            candidates[0]["raw_json"]["object_minute_source_run_hash"],
        )
        self.assertEqual(candidates[0]["active_tracking_row"]["state_key"], state_key)

    def test_executed_candidate_plan_uses_explicit_active_scope_row_not_db_terminal_state(self):
        state_key = poller.build_action_tracking_state_key(
            trade_date=TRADE_DATE,
            asset_kind="stock",
            identity_key="stock:SH:600000",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_MAIN",
        )
        active_row = {
            "run_id": ACTION_RUN_ID,
            "state_key": state_key,
            "trade_date": TRADE_DATE,
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": "BUY_MAIN",
            "latest_n4_event_time": "2026-07-02T09:51:00+08:00",
            "action_state": "eligible",
            "confirmation_status": "pending",
            "tracking_status": "tracking",
            "raw_json": {"next_unchecked_minute_label": "10:00"},
        }
        artifact = {
            "artifact_type": "n5_active_scope_snapshot_v1",
            "for_trade_date": TRADE_DATE,
            "action_run_id": ACTION_RUN_ID,
            "scope_rows": [
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "active_tracking_refs": [active_row],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            args = SimpleNamespace(
                fastlane_phase="executed",
                active_scope_artifact_path=str(artifact_path),
                for_trade_date=TRADE_DATE,
                action_run_id=ACTION_RUN_ID,
                consumer_name=CONSUMER_NAME,
                max_events=10,
            )
            candidate = {
                "run_id": ACTION_RUN_ID,
                "state_key": state_key,
                "source_trigger_run_id": "",
                "active_tracking_row": active_row,
            }

            with (
                patch.object(poller_script, "_fetch_active_tracking_rows", side_effect=AssertionError("db active state must not be fetched")),
                patch.object(poller_script, "_fetch_active_scope_tracking_rows", side_effect=AssertionError("db active scope must not be fetched")),
                patch.object(poller_script, "_fetch_metric_rows", return_value=[]),
                patch.object(poller_script, "_fetch_existing_action_event_keys", return_value=set()),
                patch.object(
                    poller_script,
                    "build_live_tracking_plan",
                    return_value={"summary": {"tracking_upsert_count": 0, "action_executed_count": 0}},
                ) as build_plan,
            ):
                poller_script._build_executed_candidate_plan(None, args, candidate, SOURCE_METRIC_RUN_ID)

        kwargs = build_plan.call_args.kwargs
        self.assertEqual(kwargs["active_tracking_rows"][0]["state_key"], state_key)
        self.assertEqual(kwargs["active_scope_tracking_rows"][0]["state_key"], state_key)

    def test_rebuild_from_n4_day_events_runner_writes_local_final_a_artifact(self):
        match = trigger_matched(
            "n4-match-0955",
            identity_key="stock:SZ:301269",
            condition_key="BUY:Y,M,W,D",
            event_time="2026-07-02T09:55:00+08:00",
        )
        latest_true = trigger_state_changed_true(
            match,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        latest_true["payload_json"] = {
            **latest_true["payload_json"],
            "trigger_price": 119.27,
            "triggered_periods": ["D"],
            "condition_key": "BUY:Y,M,W,D",
        }
        executed = action_executed_event(match, event_time="2026-07-02T09:56:00+08:00")

        class FakeCursor:
            def __init__(self):
                self.rows = []
                self.queries = []

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def execute(self, sql, params):
                self.queries.append((sql, params))
                if "source_layer = 'N4_trigger'" in sql:
                    self.rows = [match, latest_true]
                elif "source_layer = 'N5_action'" in sql:
                    self.rows = [executed]
                else:
                    self.rows = []

            def fetchall(self):
                return list(self.rows)

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def cursor(self):
                return self.cursor_obj

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1_20260702_1500_final_a.json"
            fake_conn = FakeConnection()
            with patch.object(poller_script.psycopg, "connect", return_value=fake_conn) as connect_mock:
                manifest = poller_script.run_n5_live_tracking_poller_once(
                    [
                        "--for-trade-date",
                        TRADE_DATE,
                        "--current-exchange-time",
                        "2026-07-02T15:00:00+08:00",
                        "--post-close-final-a-rebuild-from-n4-day-events",
                        "--output-artifact-path",
                        str(artifact_path),
                        "--dsn",
                        "postgresql:///unused",
                        "--user-confirmed",
                    ]
                )

            self.assertEqual(
                manifest["verdict"],
                "N5_ACTIVE_SET_A_REBUILD_FROM_N4_DAY_EVENTS_PASS",
            )
            self.assertTrue(artifact_path.exists())
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["artifact_type"], "n5_active_scope_snapshot_v1")
            self.assertEqual(artifact["scope_count"], 1)
            ref = artifact["scope_rows"][0]["active_tracking_refs"][0]
            self.assertEqual(ref["identity_key"], "stock:SZ:301269")
            self.assertEqual(ref["source_trigger_event_id"], "n4-state-true-1352")
            self.assertEqual(ref["trigger_time"], "2026-07-02T13:52:00+08:00")
            self.assertFalse(ref["action_eligible_entry_allowed"])
            self.assertEqual(manifest["write_result"]["executed"], True)
            self.assertEqual(manifest["write_result"]["artifact_type"], "n5_active_scope_snapshot_v1")
            self.assertFalse(manifest["boundary"]["n4_outbox_updated"])
            self.assertFalse(manifest["boundary"]["db_written"])
            self.assertIn("default_transaction_read_only=on", connect_mock.call_args.kwargs["options"])
            queries = "\n".join(sql for sql, _params in fake_conn.cursor_obj.queries)
            self.assertIn("source_layer = 'N4_trigger'", queries)
            self.assertIn("source_layer = 'N5_action'", queries)

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

    def test_executed_phase_evidence_only_manifest_is_not_actionexecuted_pass(self):
        plan = {
            "action_run_id": ACTION_RUN_ID,
            "source_trigger_run_id": SOURCE_TRIGGER_RUN_ID,
            "source_metric_run_id": SOURCE_METRIC_RUN_ID,
            "consumer_name": CONSUMER_NAME,
            "tracking_updates": [
                {
                    "run_id": ACTION_RUN_ID,
                    "state_key": "stock|stock:SH:600000|buy|B_BUY|BUY_MAIN",
                    "action_state": "eligible",
                    "confirmation_status": "pending",
                    "tracking_status": "tracking",
                    "raw_json": {
                        "latest_metric_status": {
                            "projection_run_id": SOURCE_METRIC_RUN_ID,
                            "reason": "missing_previous_session_reference",
                        }
                    },
                }
            ],
            "action_events": [],
            "consumed_n4_events": [],
            "inbox_checkpoint_intent": {"source_event_ids": [], "updates_n4_outbox": False},
            "active_scope_snapshot_artifact": {
                "artifact_type": "n5_active_scope_snapshot_v1",
                "scope_count": 1,
                "empty_scope_noop": False,
            },
            "summary": {
                "tracking_upsert_count": 1,
                "action_executed_count": 0,
                "action_eligible_count": 0,
            },
        }

        def provider(_args):
            return plan

        def writer(_args, _plan):
            return {
                "executed": True,
                "common_action_tracking_state": 1,
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
                "n4_outbox_status_updated": False,
            }

        manifest = poller_script.run_n5_live_tracking_poller_once(
            self.base_args("--fastlane-phase", "executed", "--execute", "--user-confirmed"),
            plan_provider=provider,
            writer=writer,
        )

        self.assertEqual(manifest["verdict"], "N5_LIVE_TRACKING_EVALUATION_PASS_NO_ACTIONEXECUTED")
        self.assertTrue(manifest["writes_enabled"])
        self.assertEqual(manifest["write_result"]["common_action_tracking_state"], 1)
        self.assertEqual(manifest["write_result"]["common_event_outbox"], 0)

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

    def test_tracking_upsert_sql_preserves_newer_cursor_on_stale_worker_update(self):
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

        poller_script._upsert_tracking_states(cursor, plan["tracking_updates"])

        self.assertIn("last_checked_minute_label = CASE", cursor.sql)
        self.assertIn(
            "EXCLUDED.last_checked_minute_label >= common_action_tracking_state.last_checked_minute_label",
            cursor.sql,
        )
        self.assertIn("raw_json = CASE", cursor.sql)
        self.assertIn("latest_n4_event_time = CASE", cursor.sql)
        self.assertIn(
            "EXCLUDED.latest_n4_event_time >= common_action_tracking_state.latest_n4_event_time",
            cursor.sql,
        )

    def test_candidate_target_minute_ignores_stale_raw_json_cursor_behind_checked_label(self):
        candidate = {
            "trigger_time": "2026-07-02T09:31:00+08:00",
            "last_checked_minute_label": "09:34",
            "next_unchecked_minute_label": "09:31",
        }

        target = poller_script._candidate_target_minute_label(
            candidate,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(target, "0935")

    def test_candidate_target_minute_does_not_fallback_to_trigger_after_final_checked_label(self):
        candidate = {
            "trigger_time": "2026-07-02T09:31:00+08:00",
            "last_checked_minute_label": "14:59",
        }

        target = poller_script._candidate_target_minute_label(
            candidate,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(target, "")

    def test_candidate_target_minute_prefers_explicit_cursor_over_source_run_label(self):
        candidate = {
            "source_trigger_run_id": "n4_trigger_20260702_until_0933_legacy",
            "trigger_time": "2026-07-02T14:47:00+08:00",
            "next_unchecked_minute_label": "14:47",
            "last_checked_minute_label": "",
        }

        target = poller_script._candidate_target_minute_label(
            candidate,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(target, "1447")

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
