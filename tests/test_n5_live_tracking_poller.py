import hashlib
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
N4_PROJECTION_CONTEXT_POLICY_HASH = "2cd95d3d427ec07ccd208bc7b939081d104415f6b9da3c4bf78e40b78a6d279e"


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


def with_condition_projection_context(
    row,
    *,
    close="10",
    status="ready",
    contract_version="N2-condition-projection-context-v1",
    field_overrides=None,
):
    asset_kind = row["asset_kind"]
    identity_key = row["identity_key"]
    fields = {
        "name": "projection context fixture",
        "close": close,
        "up_reference_period": None,
        "buy_target_price": None,
        "buy_expected_return_pct": None,
        "down_reference_period": None,
        "sell_target_price": None,
        "sell_expected_return_pct": None,
        "clear_sell_ref_period": None,
        "up_secondary_target_price": None,
        "up_secondary_expected_return_pct": None,
    }
    if asset_kind == "stock":
        fields.update({"score": None, "pe_core": None})
    fields.update(field_overrides or {})
    nullable_fields = [key for key, value in fields.items() if key not in {"name", "close"} and value is None]
    context = {
        "contract_version": contract_version,
        "source_layer": "N2_condition",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "source_trade_date": "20260701",
        "for_trade_date": TRADE_DATE,
        "status": status,
        "fields": fields,
        "nullable_fields": nullable_fields,
        "not_ready_reasons": [] if status == "ready" else ["fixture_not_ready"],
    }
    context["context_hash"] = hashlib.sha256(
        json.dumps(
            context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    row["payload_json"].update(
        {
            "condition_projection_context": context,
            "condition_projection_context_status": status,
            "condition_projection_context_trace": {
                "policy_version": "N4-condition-projection-passthrough-v1",
                "policy_hash": N4_PROJECTION_CONTEXT_POLICY_HASH,
                "status": status,
                "source_context_hash": context["context_hash"],
            },
        }
    )
    return context


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


class ExecutedCustomFinalNoActionDiscoveryCursor(ExecutedFinalNoActionDiscoveryCursor):
    def __init__(self, candidate):
        super().__init__()
        self.candidate = candidate

    def execute(self, sql, params):
        if "post_close_no_action_candidates" in sql:
            self.calls.append((sql, params))
            self._rows = [self.candidate]
            self._row = None
            return
        super().execute(sql, params)


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

    def test_condition_projection_message_covers_all_assets_and_directions(self):
        identities = {
            "stock": "stock:SH:600000",
            "index": "index:SH:000300",
            "board": "board:TDX:880001",
        }
        cases = (
            ("buy", "B_BUY", "BUY:W", "11", "10.000000", 12, "20.000000"),
            ("sell", "S_SELL", "SELL:W", "9", "-10.000000", 8, "-20.000000"),
        )
        for asset_kind, identity_key in identities.items():
            for direction, signal_type, condition_key, trigger_price, trigger_pct, action_price, action_pct in cases:
                with self.subTest(asset_kind=asset_kind, direction=direction):
                    row = trigger_matched(
                        event_id=f"n4-{asset_kind}-{direction}",
                        identity_key=identity_key,
                        condition_key=condition_key,
                        signal_type=signal_type,
                        direction=direction,
                    )
                    row["asset_kind"] = asset_kind
                    row["payload_json"].update(
                        {"asset_kind": asset_kind, "trigger_price": trigger_price}
                    )
                    context = with_condition_projection_context(
                        row,
                        field_overrides={
                            "up_reference_period": "W",
                            "buy_expected_return_pct": "12.345678",
                            "down_reference_period": "M",
                            "sell_expected_return_pct": "-8.765432",
                            "up_secondary_expected_return_pct": "3.210000",
                            **(
                                {"score": "88.000000", "pe_core": "15.500000"}
                                if asset_kind == "stock"
                                else {}
                            ),
                        },
                    )
                    metric = passing_buy_metric()
                    metric.update(
                        {
                            "asset_kind": asset_kind,
                            "identity_key": identity_key,
                            "direction": direction,
                            "signal_type": signal_type,
                            "condition_key": condition_key,
                            "current_price": action_price,
                        }
                    )
                    if direction == "sell":
                        metric.update(
                            {
                                "previous_120m_body_low": 10,
                                "previous_30m_body_low": 10,
                                "previous_5m_body_low": 10,
                                "previous_1m_body_low": 10,
                                "current_5m_virtual_amount": 40,
                                "previous_5m_full_amount": 60,
                                "current_1m_amount": 5,
                                "previous_1m_amount": 10,
                                "current_30m_virtual_amount": 100,
                                "previous_day_same_window_amount": 200,
                            }
                        )

                    plan = self.build_plan([row], metric_rows=[metric])
                    payloads = {
                        event["event_type"]: event["payload_json"]
                        for event in plan["action_events"]
                    }
                    eligible = payloads["ActionEligible"]
                    executed = payloads["ActionExecuted"]

                    self.assertEqual(eligible["pct_contract_version"], "N5-trigger-action-pct-context-v1")
                    self.assertEqual(eligible["condition_projection_context"], context)
                    self.assertEqual(eligible["trigger_price"], trigger_price)
                    self.assertEqual(eligible["trigger_pct"], trigger_pct)
                    self.assertEqual(eligible["trigger_pct_status"], "ready")
                    self.assertEqual(
                        eligible["projection_message_contract_version"],
                        "N5-n6-projection-message-v1",
                    )
                    self.assertEqual(
                        eligible["projection_message_contract_hash"],
                        "572078a71de8cf00963f718bc812fbe3a1ae09652a3faaa8bb3774f51b882025",
                    )
                    self.assertEqual(eligible["projection_message_status"], "ready")
                    self.assertEqual(eligible["projection_message_not_ready_reasons"], [])
                    self.assertNotIn("action_price", eligible)
                    self.assertNotIn("action_pct", eligible)
                    self.assertNotIn("action_pct_status", eligible)
                    self.assertEqual(eligible["asset_code"], identity_key.split(":")[2])
                    self.assertEqual(eligible["asset_name"], context["fields"]["name"])
                    if asset_kind == "stock":
                        self.assertEqual(eligible["score"], "88.000000")
                        self.assertEqual(eligible["pe_core"], "15.500000")
                    else:
                        self.assertNotIn("score", eligible)
                        self.assertNotIn("pe_core", eligible)
                    self.assertEqual(executed["action_price"], action_price)
                    self.assertEqual(executed["action_pct"], action_pct)
                    self.assertEqual(executed["action_pct_status"], "ready")
                    self.assertEqual(executed["projection_message_status"], "ready")

    def test_projection_message_manifest_and_pct_rounding_are_canonical(self):
        self.assertEqual(
            len(poller.N5_N6_PROJECTION_MESSAGE_CONTRACT_JSON.encode("utf-8")),
            2653,
        )
        self.assertEqual(
            hashlib.sha256(
                poller.N5_N6_PROJECTION_MESSAGE_CONTRACT_JSON.encode("utf-8")
            ).hexdigest(),
            "572078a71de8cf00963f718bc812fbe3a1ae09652a3faaa8bb3774f51b882025",
        )
        cases = (
            ("8.0987654", "8", "1.234568"),
            ("9", "10", "-10.000000"),
            ("10", "10", "0.000000"),
        )
        for index, (trigger_price, close, expected_pct) in enumerate(cases):
            row = trigger_matched(event_id=f"n4-rounding-{index}")
            row["payload_json"]["trigger_price"] = trigger_price
            with_condition_projection_context(row, close=close)

            payload = self.build_plan([row])["action_events"][0]["payload_json"]

            self.assertEqual(payload["trigger_pct"], expected_pct)

    def test_latest_state_context_cannot_pollute_immutable_entry_snapshot(self):
        matched = trigger_matched("n4-entry", event_time="2026-07-02T09:55:00+08:00")
        matched["payload_json"]["trigger_price"] = "11"
        entry_context = with_condition_projection_context(
            matched,
            close="10",
            field_overrides={"name": "entry authority"},
        )
        entry_plan = self.build_plan([matched])

        changed = trigger_state_changed_true(
            matched,
            "n4-latest-state",
            event_time="2026-07-02T10:00:00+08:00",
        )
        changed["payload_json"]["trigger_price"] = "40"
        latest_context = with_condition_projection_context(
            changed,
            close="20",
            field_overrides={"name": "forbidden latest state"},
        )
        metric = passing_buy_metric(metric_time="2026-07-02T10:00:00+08:00")
        metric.update({"metric_minute_label": "10:00", "current_price": 12})

        confirmed = self.build_plan(
            [changed],
            active_tracking_rows=entry_plan["tracking_updates"],
            metric_rows=[metric],
        )

        self.assertEqual([event["event_type"] for event in confirmed["action_events"]], ["ActionExecuted"])
        payload = confirmed["action_events"][0]["payload_json"]
        self.assertEqual(payload["trigger_price"], "11")
        self.assertEqual(payload["trigger_pct"], "10.000000")
        self.assertEqual(payload["condition_projection_context"], entry_context)
        self.assertEqual(payload["asset_name"], "entry authority")
        self.assertEqual(payload["action_price"], 12)
        self.assertEqual(payload["action_pct"], "20.000000")
        self.assertEqual(payload["projection_message_status"], "ready")
        self.assertEqual(
            payload["source_n4_payload"]["condition_projection_context"],
            latest_context,
        )
        self.assertNotEqual(payload["condition_projection_context"], latest_context)

    def test_missing_and_tampered_context_fail_closed_without_lifecycle_or_dedup_change(self):
        valid = trigger_matched("n4-authority-check")
        valid["payload_json"]["trigger_price"] = "12"
        with_condition_projection_context(valid)
        tampered = trigger_matched("n4-authority-check")
        tampered["payload_json"]["trigger_price"] = "12"
        with_condition_projection_context(tampered)
        tampered["payload_json"]["condition_projection_context"]["fields"]["name"] = "tampered"
        missing = trigger_matched("n4-authority-check")
        missing["payload_json"]["trigger_price"] = "12"
        metric = passing_buy_metric()

        valid_plan = self.build_plan([valid], metric_rows=[metric])
        tampered_plan = self.build_plan([tampered], metric_rows=[metric])
        missing_plan = self.build_plan([missing], metric_rows=[metric])

        for plan in (tampered_plan, missing_plan):
            self.assertEqual(
                [event["event_type"] for event in plan["action_events"]],
                ["ActionEligible", "ActionExecuted"],
            )
            self.assertEqual(
                [event["event_id"] for event in plan["action_events"]],
                [event["event_id"] for event in valid_plan["action_events"]],
            )
            self.assertEqual(
                [event["dedup_key"] for event in plan["action_events"]],
                [event["dedup_key"] for event in valid_plan["action_events"]],
            )
            self.assertEqual(plan["tracking_updates"][-1]["action_state"], "executed")
            self.assertEqual(plan["tracking_updates"][-1]["raw_json"]["action_mark"], "30m_volume")
        tampered_eligible = tampered_plan["action_events"][0]["payload_json"]
        missing_eligible = missing_plan["action_events"][0]["payload_json"]
        self.assertEqual(tampered_eligible["projection_message_status"], "not_ready")
        self.assertIn(
            "condition_projection_context_hash_mismatch",
            tampered_eligible["projection_message_not_ready_reasons"],
        )
        self.assertEqual(missing_eligible["projection_message_status"], "not_ready")
        self.assertIn(
            "condition_projection_context_missing",
            missing_eligible["projection_message_not_ready_reasons"],
        )
        self.assertNotIn("action_price", tampered_eligible)
        self.assertNotIn("action_price", missing_eligible)

    def test_projection_message_optional_nulls_remain_ready(self):
        row = trigger_matched("n4-nullable")
        row["payload_json"]["trigger_price"] = "12"
        with_condition_projection_context(row)

        payload = self.build_plan([row])["action_events"][0]["payload_json"]

        self.assertEqual(payload["projection_message_status"], "ready")
        self.assertEqual(payload["projection_message_not_ready_reasons"], [])
        self.assertIsNone(payload["buy_expected_return_pct"])
        self.assertIsNone(payload["score"])
        self.assertIsNone(payload["pe_core"])

    def test_projection_fields_do_not_change_existing_event_schema_or_dedup(self):
        without_context = trigger_matched("n4-dedup-context")
        without_context["payload_json"]["trigger_price"] = "11"
        with_context = trigger_matched("n4-dedup-context")
        with_context["payload_json"]["trigger_price"] = "11"
        with_condition_projection_context(with_context)

        old_event = self.build_plan([without_context])["action_events"][0]
        new_event = self.build_plan([with_context])["action_events"][0]

        self.assertEqual(new_event["event_key"], old_event["event_key"])
        self.assertEqual(new_event["event_id"], old_event["event_id"])
        self.assertEqual(new_event["event_schema_version"], old_event["event_schema_version"])

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

    def test_new_trigger_matched_reopens_expired_tracking_ref(self):
        original = trigger_matched(
            "n4-match-old",
            event_time="2026-07-02T09:51:00+08:00",
        )
        first = self.build_plan([original])
        expired_state = dict(first["tracking_updates"][0])
        expired_state.update(
            {
                "action_state": "expired",
                "confirmation_status": "expired",
                "tracking_status": "expired",
                "planned_output_event_type": None,
                "expired_reason": "window_expired",
                "expired_at": "2026-07-02T10:00:00+08:00",
                "last_checked_minute_label": "09:59",
            }
        )
        expired_state["raw_json"] = {
            **expired_state["raw_json"],
            "next_unchecked_minute_label": "10:00",
        }
        latest = trigger_matched(
            "n4-match-new",
            event_time="2026-07-02T13:53:00+08:00",
        )

        reopened = self.build_plan(
            [latest],
            active_tracking_rows=[expired_state],
            existing_event_keys={first["action_events"][0]["event_key"]},
        )

        self.assertEqual([event["event_type"] for event in reopened["action_events"]], ["ActionEligible"])
        reopened_event = reopened["action_events"][0]
        self.assertEqual(reopened_event["payload_json"]["source_trigger_event_id"], "n4-match-new")
        self.assertNotEqual(reopened_event["event_key"], first["action_events"][0]["event_key"])
        self.assertTrue(reopened_event["event_key"].endswith("|n4-match-new"))
        self.assertEqual(reopened["consumed_n4_event_ids"], ["n4-match-new"])
        self.assertEqual(len(reopened["tracking_updates"]), 1)
        update = reopened["tracking_updates"][0]
        self.assertEqual(update["action_state"], "eligible")
        self.assertEqual(update["confirmation_status"], "pending")
        self.assertEqual(update["tracking_status"], "tracking")
        self.assertEqual(update["source_trigger_event_id"], "n4-match-new")
        self.assertEqual(update["latest_n4_event_time"], "2026-07-02T13:53:00+08:00")
        self.assertIsNone(update["last_checked_minute_label"])
        self.assertIsNone(update["expired_reason"])
        self.assertIsNone(update["expired_at"])
        self.assertTrue(update["raw_json"]["terminal_ref_reopen_allowed"])
        self.assertEqual(
            update["raw_json"]["terminal_ref_reopen_trace"]["prior_source_trigger_event_id"],
            "n4-match-old",
        )
        ref = reopened["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
        self.assertEqual(ref["source_trigger_event_id"], "n4-match-new")
        self.assertEqual(ref["next_unchecked_minute_label"], "13:53")

    def test_inactive_then_new_trigger_matched_emits_new_action_eligible_episode(self):
        original = trigger_matched(
            "n4-match-1316",
            event_time="2026-07-02T13:16:00+08:00",
        )
        first = self.build_plan([original])
        inactive = trigger_state_changed_false(original, "n4-state-false-1326")
        inactive["event_time"] = "2026-07-02T13:26:00+08:00"
        expired = self.build_plan(
            [inactive],
            active_tracking_rows=first["tracking_updates"],
        )
        latest = trigger_matched(
            "n4-match-1333",
            event_time="2026-07-02T13:33:00+08:00",
        )

        reopened = self.build_plan(
            [latest],
            active_tracking_rows=expired["tracking_updates"],
            existing_event_keys={first["action_events"][0]["event_key"]},
        )

        self.assertEqual(expired["tracking_updates"][0]["action_state"], "expired")
        self.assertEqual([event["event_type"] for event in reopened["action_events"]], ["ActionEligible"])
        self.assertEqual(
            reopened["action_events"][0]["payload_json"]["source_trigger_event_id"],
            "n4-match-1333",
        )
        self.assertNotEqual(
            reopened["action_events"][0]["event_key"],
            first["action_events"][0]["event_key"],
        )

    def test_same_batch_inactive_then_new_match_emits_two_eligible_episodes(self):
        original = trigger_matched(
            "n4-match-1316",
            event_time="2026-07-02T13:16:00+08:00",
        )
        inactive = trigger_state_changed_false(original, "n4-state-false-1326")
        inactive["event_time"] = "2026-07-02T13:26:00+08:00"
        latest = trigger_matched(
            "n4-match-1333",
            event_time="2026-07-02T13:33:00+08:00",
        )

        plan = self.build_plan([original, inactive, latest])

        self.assertEqual(plan["consumed_n4_event_ids"], [
            "n4-match-1316",
            "n4-state-false-1326",
            "n4-match-1333",
        ])
        self.assertEqual(
            [event["payload_json"]["source_trigger_event_id"] for event in plan["action_events"]],
            ["n4-match-1316", "n4-match-1333"],
        )
        self.assertEqual(len(plan["tracking_updates"]), 1)
        update = plan["tracking_updates"][0]
        self.assertEqual(update["action_state"], "eligible")
        self.assertEqual(update["source_trigger_event_id"], "n4-match-1333")
        self.assertTrue(update["raw_json"]["terminal_ref_reopen_allowed"])

    def test_same_trigger_matched_event_does_not_reopen_expired_tracking_ref(self):
        row = trigger_matched(
            "n4-match-same",
            event_time="2026-07-02T13:53:00+08:00",
        )
        first = self.build_plan([row])
        expired_state = dict(first["tracking_updates"][0])
        expired_state.update(
            {
                "action_state": "expired",
                "confirmation_status": "expired",
                "tracking_status": "expired",
            }
        )

        repeated = self.build_plan([row], active_tracking_rows=[expired_state])

        self.assertEqual(repeated["tracking_updates"], [])
        self.assertEqual(repeated["active_scope_snapshot_artifact"]["scope_rows"], [])

    def test_new_trigger_matched_does_not_reopen_executed_tracking_ref(self):
        original = trigger_matched("n4-match-executed")
        executed = self.build_plan([original], metric_rows=[passing_buy_metric()])
        executed_state = next(
            row for row in executed["tracking_updates"] if row["action_state"] == "executed"
        )
        latest = trigger_matched(
            "n4-match-after-executed",
            event_time="2026-07-02T13:53:00+08:00",
        )

        repeated = self.build_plan([latest], active_tracking_rows=[executed_state])

        self.assertEqual(repeated["tracking_updates"], [])
        self.assertEqual(repeated["active_scope_snapshot_artifact"]["scope_rows"], [])

    def test_inactive_then_new_trigger_matched_reopens_executed_episode(self):
        original = trigger_matched("n4-match-executed-old")
        executed = self.build_plan([original], metric_rows=[passing_buy_metric()])
        executed_state = next(
            row for row in executed["tracking_updates"] if row["action_state"] == "executed"
        )
        inactive = trigger_state_changed_false(original, "n4-state-false-after-executed")
        inactive["event_time"] = "2026-07-02T13:26:00+08:00"

        boundary_plan = self.build_plan(
            [inactive],
            active_tracking_rows=[executed_state],
            existing_event_keys={event["event_key"] for event in executed["action_events"]},
        )

        self.assertEqual(boundary_plan["action_events"], [])
        self.assertEqual(len(boundary_plan["tracking_updates"]), 1)
        boundary_state = boundary_plan["tracking_updates"][0]
        self.assertEqual(boundary_state["action_state"], "executed")
        self.assertEqual(boundary_state["tracking_status"], "executed")
        self.assertFalse(boundary_state["trigger_live"])
        self.assertEqual(boundary_state["latest_n4_event_id"], "n4-state-false-after-executed")
        self.assertEqual(
            boundary_state["raw_json"]["terminal_episode_inactive_boundary"][
                "source_trigger_event_id"
            ],
            "n4-state-false-after-executed",
        )
        self.assertEqual(
            boundary_state["raw_json"]["terminal_episode_inactive_boundary"][
                "closed_source_trigger_event_id"
            ],
            "n4-match-executed-old",
        )

        latest = trigger_matched(
            "n4-match-executed-new",
            event_time="2026-07-02T13:33:00+08:00",
        )
        reopened = self.build_plan(
            [latest],
            active_tracking_rows=[boundary_state],
            existing_event_keys={event["event_key"] for event in executed["action_events"]},
        )

        self.assertEqual([event["event_type"] for event in reopened["action_events"]], ["ActionEligible"])
        self.assertEqual(
            reopened["action_events"][0]["payload_json"]["source_trigger_event_id"],
            "n4-match-executed-new",
        )
        self.assertEqual(len(reopened["tracking_updates"]), 1)
        update = reopened["tracking_updates"][0]
        self.assertEqual(update["action_state"], "eligible")
        self.assertEqual(update["confirmation_status"], "pending")
        self.assertEqual(update["tracking_status"], "tracking")
        self.assertEqual(update["source_trigger_event_id"], "n4-match-executed-new")
        self.assertTrue(update["raw_json"]["terminal_ref_reopen_allowed"])
        self.assertEqual(
            update["raw_json"]["terminal_ref_reopen_trace"]["prior_action_state"],
            "executed",
        )
        self.assertEqual(
            update["raw_json"]["terminal_ref_reopen_trace"]["inactive_boundary_event_id"],
            "n4-state-false-after-executed",
        )

    def test_same_batch_inactive_then_new_match_reopens_executed_episode(self):
        original = trigger_matched("n4-match-executed-old")
        executed = self.build_plan([original], metric_rows=[passing_buy_metric()])
        executed_state = next(
            row for row in executed["tracking_updates"] if row["action_state"] == "executed"
        )
        inactive = trigger_state_changed_false(original, "n4-state-false-after-executed")
        inactive["event_time"] = "2026-07-02T13:26:00+08:00"
        latest = trigger_matched(
            "n4-match-executed-new",
            event_time="2026-07-02T13:33:00+08:00",
        )

        reopened = self.build_plan(
            [inactive, latest],
            active_tracking_rows=[executed_state],
            existing_event_keys={event["event_key"] for event in executed["action_events"]},
        )

        self.assertEqual(
            reopened["consumed_n4_event_ids"],
            ["n4-state-false-after-executed", "n4-match-executed-new"],
        )
        self.assertEqual([event["event_type"] for event in reopened["action_events"]], ["ActionEligible"])
        self.assertEqual(len(reopened["tracking_updates"]), 1)
        update = reopened["tracking_updates"][0]
        self.assertEqual(update["action_state"], "eligible")
        self.assertEqual(update["source_trigger_event_id"], "n4-match-executed-new")
        self.assertEqual(
            update["raw_json"]["terminal_episode_inactive_boundary"][
                "source_trigger_event_id"
            ],
            "n4-state-false-after-executed",
        )

    def test_consumed_inactive_boundary_does_not_reopen_next_executed_episode(self):
        original = trigger_matched("n4-match-executed-old")
        executed = self.build_plan([original], metric_rows=[passing_buy_metric()])
        executed_state = next(
            row for row in executed["tracking_updates"] if row["action_state"] == "executed"
        )
        inactive = trigger_state_changed_false(original, "n4-state-false-after-executed")
        inactive["event_time"] = "2026-07-02T13:26:00+08:00"
        latest = trigger_matched(
            "n4-match-executed-new",
            event_time="2026-07-02T13:33:00+08:00",
        )
        reopened = self.build_plan(
            [inactive, latest],
            active_tracking_rows=[executed_state],
            existing_event_keys={event["event_key"] for event in executed["action_events"]},
        )
        reopened_state = dict(reopened["tracking_updates"][0])
        reopened_state.update(
            {
                "action_state": "executed",
                "confirmation_status": "passed",
                "tracking_status": "executed",
                "planned_output_event_type": "ActionExecuted",
            }
        )
        later_match_without_new_boundary = trigger_matched(
            "n4-match-executed-later",
            event_time="2026-07-02T13:40:00+08:00",
        )

        repeated = self.build_plan(
            [later_match_without_new_boundary],
            active_tracking_rows=[reopened_state],
        )

        self.assertEqual(repeated["tracking_updates"], [])
        self.assertEqual(repeated["action_events"], [])
        self.assertEqual(repeated["active_scope_snapshot_artifact"]["scope_rows"], [])

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

    def test_trigger_state_changed_true_without_trigger_matched_entry_cannot_execute(self):
        matched = trigger_matched(event_time="2026-07-02T09:55:00+08:00")
        matched["payload_json"].update(
            {
                "primary_trigger_period": "M",
                "all_trigger_periods": ["M", "W"],
            }
        )
        row = trigger_state_changed_true(
            matched,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        metric = passing_buy_metric(metric_time="2026-07-02T13:52:00+08:00")
        metric["metric_minute_label"] = "13:52"

        plan = self.build_plan([row], metric_rows=[metric])

        self.assertEqual(plan["action_events"], [])
        self.assertEqual(plan["summary"]["action_eligible_count"], 0)
        self.assertEqual(plan["summary"]["action_executed_count"], 0)
        update = plan["tracking_updates"][0]
        self.assertEqual(update["source_trigger_event_type"], "TriggerStateChanged")
        self.assertFalse(update["raw_json"]["action_eligible_entry_allowed"])
        self.assertFalse(update["raw_json"]["action_confirmation_entry_verified"])
        self.assertNotIn("action_entry_trigger_matched_ref", update["raw_json"])
        self.assertEqual(
            update["raw_json"]["latest_trigger_state_changed_ref"]["source_trigger_event_id"],
            "n4-state-true-1352",
        )

    def test_trigger_matched_entry_then_state_changed_refresh_can_execute_and_preserves_escalation_trace(self):
        matched = trigger_matched(
            event_id="n4-match-entry-0955",
            event_time="2026-07-02T09:55:00+08:00",
        )
        entry_trace = {
            "policy_version": "N4-ordinary-period-escalation-v1",
            "policy_hash": "entry-policy-hash",
            "periods": {"W": {"prerequisite_period": "D", "gate_pass": True}},
        }
        matched["payload_json"].update(
            {
                "primary_trigger_period": "W",
                "all_trigger_periods": ["W"],
                "prerequisite_periods": ["D"],
                "period_escalation_trace": entry_trace,
                "rule_proof": {
                    "triggered_period_details": [
                        {
                            "period": "W",
                            "prerequisite_periods": ["D"],
                            "period_escalation_trace": entry_trace["periods"]["W"],
                        }
                    ]
                },
            }
        )
        entry = self.build_plan([matched])
        self.assertEqual([event["event_type"] for event in entry["action_events"]], ["ActionEligible"])

        changed = trigger_state_changed_true(
            matched,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        latest_trace = {
            "policy_version": "N4-ordinary-period-escalation-v1",
            "policy_hash": "latest-policy-hash",
            "periods": {"M": {"prerequisite_period": "W", "gate_pass": True}},
        }
        changed["payload_json"].update(
            {
                "primary_trigger_period": "M",
                "all_trigger_periods": ["M"],
                "triggered_periods": ["M"],
                "prerequisite_periods": ["W"],
                "period_escalation_trace": latest_trace,
            }
        )
        metric = passing_buy_metric(metric_time="2026-07-02T13:52:00+08:00")
        metric["metric_minute_label"] = "13:52"

        confirmed = self.build_plan(
            [changed],
            active_tracking_rows=entry["tracking_updates"],
            metric_rows=[metric],
        )

        self.assertEqual([event["event_type"] for event in confirmed["action_events"]], ["ActionExecuted"])
        payload = confirmed["action_events"][0]["payload_json"]
        self.assertEqual(payload["source_trigger_event_type"], "TriggerStateChanged")
        self.assertEqual(payload["source_trigger_event_id"], "n4-state-true-1352")
        self.assertEqual(payload["primary_trigger_period"], "M")
        self.assertEqual(payload["all_trigger_periods"], ["M"])
        self.assertNotIn("W", payload["all_trigger_periods"])
        self.assertEqual(payload["source_n4_payload"]["prerequisite_periods"], ["W"])
        self.assertEqual(payload["source_n4_payload"]["period_escalation_trace"], latest_trace)
        entry_ref = payload["action_entry_trigger_matched_ref"]
        latest_ref = payload["latest_trigger_state_changed_ref"]
        self.assertEqual(entry_ref["source_trigger_event_id"], "n4-match-entry-0955")
        self.assertEqual(entry_ref["source_n4_payload"]["period_escalation_trace"], entry_trace)
        self.assertEqual(latest_ref["source_trigger_event_id"], "n4-state-true-1352")
        self.assertEqual(latest_ref["source_n4_payload"]["period_escalation_trace"], latest_trace)
        self.assertEqual(payload["trace_json"]["action_entry_trigger_matched_ref"], entry_ref)
        self.assertEqual(payload["trace_json"]["latest_trigger_state_changed_ref"], latest_ref)
        self.assertEqual(confirmed["summary"]["action_eligible_count"], 0)
        self.assertEqual(confirmed["summary"]["action_executed_count"], 1)

        recomputed = self.build_plan(
            [changed],
            active_tracking_rows=entry["tracking_updates"],
            metric_rows=[metric],
        )
        self.assertEqual(
            recomputed["action_events"][0]["event_key"],
            confirmed["action_events"][0]["event_key"],
        )
        replay = self.build_plan(
            [changed],
            active_tracking_rows=entry["tracking_updates"],
            metric_rows=[metric],
            existing_event_keys={confirmed["action_events"][0]["event_key"]},
        )
        self.assertEqual(replay["action_events"], [])

    def test_trigger_state_changed_only_is_attention_for_all_assets_and_directions(self):
        for asset_kind in ("stock", "index", "board"):
            for direction, signal_type, condition_key in (
                ("buy", "B_BUY", "BUY:W"),
                ("sell", "S_SELL", "SELL:W"),
            ):
                with self.subTest(asset_kind=asset_kind, direction=direction):
                    identity_key = f"{asset_kind}:TEST:{direction}"
                    matched = trigger_matched(
                        event_id=f"n4-match-{asset_kind}-{direction}",
                        identity_key=identity_key,
                        condition_key=condition_key,
                        signal_type=signal_type,
                        direction=direction,
                    )
                    matched["asset_kind"] = asset_kind
                    matched["payload_json"]["asset_kind"] = asset_kind
                    matched["payload_json"].update(
                        {
                            "primary_trigger_period": "W",
                            "all_trigger_periods": ["W"],
                            "prerequisite_periods": ["D"],
                            "period_escalation_trace": {
                                "policy_version": "N4-ordinary-period-escalation-v1",
                                "periods": {"W": {"prerequisite_period": "D"}},
                            },
                        }
                    )
                    changed = trigger_state_changed_true(
                        matched,
                        f"n4-state-{asset_kind}-{direction}",
                    )

                    plan = self.build_plan([changed])

                    self.assertEqual(plan["action_events"], [])
                    ref = plan["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]
                    self.assertEqual(ref["asset_kind"], asset_kind)
                    self.assertEqual(ref["direction"], direction)
                    self.assertFalse(ref["action_eligible_entry_allowed"])
                    self.assertFalse(ref["action_confirmation_entry_verified"])
                    self.assertEqual(ref["all_trigger_periods"], ["W"])
                    self.assertEqual(ref["source_n4_payload"]["prerequisite_periods"], ["D"])

    def test_active_scope_period_fields_round_trip_and_legacy_ref_recovery(self):
        matched = trigger_matched(event_time="2026-07-02T09:55:00+08:00")
        matched["payload_json"].update(
            {
                "primary_trigger_period": "M",
                "all_trigger_periods": ["M", "W"],
            }
        )
        row = trigger_state_changed_true(
            matched,
            "n4-state-true-1352",
            event_time="2026-07-02T13:52:00+08:00",
        )
        entry = self.build_plan([matched])
        first = self.build_plan([row], active_tracking_rows=entry["tracking_updates"])
        ref = first["active_scope_snapshot_artifact"]["scope_rows"][0]["active_tracking_refs"][0]

        self.assertEqual(ref["primary_trigger_period"], "M")
        self.assertEqual(ref["all_trigger_periods"], ["M", "W"])
        self.assertEqual(ref["triggered_periods"], ["M", "W"])

        legacy_ref = dict(ref)
        legacy_ref["trade_date"] = TRADE_DATE
        legacy_ref.pop("primary_trigger_period")
        legacy_ref.pop("all_trigger_periods")
        metric = passing_buy_metric(metric_time="2026-07-02T13:52:00+08:00")
        metric["metric_minute_label"] = "13:52"

        second = self.build_plan(
            [],
            active_tracking_rows=[legacy_ref],
            metric_rows=[metric],
        )

        payload = second["action_events"][0]["payload_json"]
        self.assertEqual(payload["trigger_period"], "M")
        self.assertEqual(payload["primary_trigger_period"], "M")
        self.assertEqual(payload["all_trigger_periods"], ["M", "W"])
        self.assertEqual(payload["triggered_periods"], ["M", "W"])

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

    def test_hint_keeps_30m_trigger_period_outside_formal_period_set(self):
        matched = trigger_matched(
            "n4-hint-period-shape",
            identity_key="index:SH:000300",
            condition_key="BUY_HINT:W",
            signal_type="B_BUY",
            direction="buy",
        )
        matched["asset_kind"] = "index"
        matched["payload_json"].update(
            {
                "asset_kind": "index",
                "trigger_period": "30m",
                "primary_trigger_period": None,
                "all_trigger_periods": [],
                "triggered_periods": [],
                "trigger_price": "11",
            }
        )
        with_condition_projection_context(matched)
        metric = passing_buy_metric(metric_time="2026-07-02T10:00:00+08:00")
        metric.update(
            {
                "asset_kind": "index",
                "identity_key": "index:SH:000300",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_HINT:W",
            }
        )

        plan = self.build_plan([matched], metric_rows=[metric])
        payloads = {event["event_type"]: event["payload_json"] for event in plan["action_events"]}

        for payload in payloads.values():
            self.assertEqual(payload["trigger_period"], "30m")
            self.assertIsNone(payload["primary_trigger_period"])
            self.assertEqual(payload["all_trigger_periods"], [])
            self.assertEqual(payload["triggered_periods"], [])
        tracking = plan["tracking_updates"][0]
        self.assertEqual(tracking["trigger_period"], "30m")
        self.assertIsNone(tracking["primary_trigger_period"])
        self.assertEqual(tracking["all_trigger_periods"], [])
        self.assertEqual(tracking["triggered_periods"], ["30m"])

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

    def test_proof_to_action_latency_uses_matching_n3t_closed_proof(self):
        class FakeCursor:
            def __init__(self):
                self.params = None

            def execute(self, _sql, params):
                self.params = params

            def fetchall(self):
                return [
                    {
                        "projection_run_id": "n3t-proof-300144",
                        "identity_key": "stock:SZ:300144",
                        "proof_created_at": datetime.now().astimezone().replace(microsecond=0),
                    }
                ]

        cursor = FakeCursor()
        latency_ms = poller_script._proof_to_action_latency_ms(
            cursor,
            [
                {
                    "event_type": "ActionExecuted",
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:300144",
                    "payload_json": {"source_metric_run_id": "n3t-proof-300144"},
                }
            ],
        )

        self.assertEqual(cursor.params, (["n3t-proof-300144"], ["stock:SZ:300144"]))
        self.assertIsNotNone(latency_ms)
        self.assertGreaterEqual(latency_ms, 0)
        self.assertLess(latency_ms, 2000)

    def test_active_scope_candidates_prioritize_latest_n4_trigger(self):
        args = SimpleNamespace(
            action_run_id="n5_live_tracking_20260710__active_set_a__fastlane_v1",
            for_trade_date="20260710",
        )
        rows = [
            {
                "run_id": args.action_run_id,
                "trade_date": "20260710",
                "asset_kind": "stock",
                "identity_key": "stock:SZ:000001",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:M,W",
                "source_trigger_event_id": "evt-old",
                "latest_n4_event_time": "2026-07-10T09:31:00+08:00",
                "next_unchecked_minute_label": "09:31",
                "action_state": "eligible",
                "tracking_status": "tracking",
            },
            {
                "run_id": args.action_run_id,
                "trade_date": "20260710",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:M,W",
                "source_trigger_event_id": "evt-new",
                "latest_n4_event_time": "2026-07-10T13:07:00+08:00",
                "next_unchecked_minute_label": "13:07",
                "action_state": "eligible",
                "tracking_status": "tracking",
            },
        ]

        candidates = poller_script._active_scope_rows_to_executed_candidates(args, rows)

        self.assertEqual(
            [candidate["identity_key"] for candidate in candidates],
            ["stock:SH:600000", "stock:SZ:000001"],
        )

    def test_exact_ready_n3t_proof_discovery_is_batched_by_asset_table(self):
        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params):
                self.calls.append((sql, params))

            def fetchall(self):
                return [
                    {
                        "candidate_index": 1,
                        "projection_run_id": "n3t-proof-new",
                    }
                ]

        cursor = FakeCursor()
        result = poller_script._discover_exact_ready_n3t_metric_run_ids(
            cursor,
            "20260710",
            candidates=[
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:000001",
                    "target_minute_label": "09:31",
                },
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "target_minute_label": "13:07",
                },
            ],
        )

        self.assertEqual(result, {1: "n3t-proof-new"})
        self.assertEqual(len(cursor.calls), 1)
        self.assertIn("candidate_targets", cursor.calls[0][0])
        self.assertIn("N3T_C1_CLOSED", cursor.calls[0][0])

    def test_active_scope_candidate_census_is_not_truncated_before_proof_lookup(self):
        args = SimpleNamespace(
            action_run_id="n5_live_tracking_20260730__active_set_a__fastlane_v1",
            for_trade_date="20260730",
        )
        rows = [
            {
                "run_id": args.action_run_id,
                "trade_date": "20260730",
                "asset_kind": "stock",
                "identity_key": f"stock:SH:{600000 + index:06d}",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:M,W",
                "source_trigger_event_id": f"evt-{index:04d}",
                "latest_n4_event_time": "2026-07-30T09:31:00+08:00",
                "next_unchecked_minute_label": "09:31",
                "action_state": "eligible",
                "tracking_status": "tracking",
            }
            for index in range(904)
        ]

        candidates = poller_script._active_scope_rows_to_executed_candidates(args, rows)

        self.assertEqual(len(candidates), 904)

    def test_exact_ready_discovery_reaches_candidate_beyond_old_256_cutoff_without_single_plan(self):
        action_run_id = "n5_live_tracking_20260730__active_set_a__fastlane_v1"
        candidates = [
            {
                "run_id": action_run_id,
                "asset_kind": "stock",
                "identity_key": f"stock:SH:{600000 + index:06d}",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:M,W",
                "state_key": f"state-{index:04d}",
                "source_trigger_event_id": f"evt-{index:04d}",
                "target_minute_label": "0931",
                "source_run_hash": f"hash-{index:04d}",
                "trigger_time": "2026-07-30T09:31:00+08:00",
            }
            for index in range(904)
        ]

        def exact_ready(_cur, _trade_date, *, candidates):
            self.assertEqual(len(candidates), 904)
            return {900: "n3t-ready-proof-900"}

        with (
            patch.object(
                poller_script,
                "_discover_exact_ready_n3t_metric_run_ids",
                side_effect=exact_ready,
            ),
            patch.object(
                poller_script,
                "_build_executed_candidate_plan",
                side_effect=AssertionError("exact-ready discovery must not build per-ref plans"),
            ) as build_single_plan,
        ):
            output = poller_script._discover_executed_runtime_input_from_candidates(
                object(),
                SimpleNamespace(for_trade_date="20260730", max_events=0),
                candidates,
            )

        self.assertEqual(output["state_key"], "state-0900")
        self.assertEqual(output["source_metric_run_id"], "n3t-ready-proof-900")
        self.assertEqual(output["fastlane_executed_queue_metrics"]["ready_census"], 1)
        self.assertEqual(output["fastlane_executed_queue_metrics"]["selected"], 1)
        build_single_plan.assert_not_called()

    def test_exact_ready_batch_is_bounded_fair_and_covers_904_refs_in_four_batches(self):
        action_run_id = "n5_live_tracking_20260730__active_set_a__fastlane_v1"
        asset_kinds = ("stock", "index", "board")
        remaining = [
            {
                "run_id": action_run_id,
                "asset_kind": asset_kinds[index % len(asset_kinds)],
                "identity_key": f"{asset_kinds[index % len(asset_kinds)]}:TEST:{index:06d}",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:M,W",
                "state_key": f"state-{index:04d}",
                "target_minute_label": "0931",
                "source_metric_run_id": f"n3t-ready-proof-{index:04d}",
            }
            for index in range(904)
        ]
        batch_sizes = []
        covered_state_keys = set()

        while remaining:
            selected = poller_script._select_exact_ready_candidate_batch(
                remaining,
                for_trade_date="20260730",
                limit=256,
            )
            batch_sizes.append(len(selected))
            if len(batch_sizes) == 1:
                self.assertEqual(
                    [candidate["asset_kind"] for candidate in selected[:3]],
                    ["stock", "index", "board"],
                )
            selected_keys = {candidate["state_key"] for candidate in selected}
            self.assertFalse(covered_state_keys & selected_keys)
            covered_state_keys.update(selected_keys)
            remaining = [
                candidate
                for candidate in remaining
                if candidate["state_key"] not in selected_keys
            ]

        self.assertEqual(batch_sizes, [256, 256, 256, 136])
        self.assertEqual(len(covered_state_keys), 904)

    def test_exact_ready_discovery_selects_256_without_per_ref_planning(self):
        candidates = [
            {
                "run_id": "n5_live_tracking_20260730__active_set_a__fastlane_v1",
                "asset_kind": ("stock", "index", "board")[index % 3],
                "identity_key": f"identity-{index:04d}",
                "direction": "sell",
                "signal_type": "S_SELL",
                "condition_key": "SELL:M,W",
                "state_key": f"state-{index:04d}",
                "source_trigger_event_id": f"evt-{index:04d}",
                "target_minute_label": "0931",
                "source_run_hash": f"hash-{index:04d}",
                "trigger_time": "2026-07-30T09:31:00+08:00",
            }
            for index in range(904)
        ]

        with (
            patch.object(
                poller_script,
                "_discover_exact_ready_n3t_metric_run_ids",
                return_value={
                    index: f"n3t-ready-proof-{index:04d}"
                    for index in range(904)
                },
            ),
            patch.object(
                poller_script,
                "_build_executed_candidate_plan",
                side_effect=AssertionError("exact-ready discovery must use one batch planner"),
            ) as build_single_plan,
        ):
            output = poller_script._discover_executed_runtime_input_from_candidates(
                object(),
                SimpleNamespace(for_trade_date="20260730", max_events=300),
                candidates,
            )

        selected = output["fastlane_executed_batch_candidates"]
        self.assertEqual(len(selected), 256)
        self.assertEqual(output["fastlane_executed_queue_metrics"]["ready_census"], 904)
        self.assertEqual(output["fastlane_executed_queue_metrics"]["remaining"], 648)
        build_single_plan.assert_not_called()

    def test_scheduler_compact_manifest_includes_ready_proof_queue_scalars(self):
        compact = poller_script._scheduler_compact_manifest(
            {
                "verdict": "N5_LIVE_TRACKING_EXECUTE_PASS",
                "fastlane": {
                    "phase": "executed",
                    "ready_proof_queue": {
                        "ready_census": 904,
                        "selected": 256,
                        "processed": 256,
                        "remaining": 648,
                        "oldest_ready_age_ms": 205000,
                        "discovery_ms": 12.5,
                        "planner_ms": 20.0,
                        "writer_ms": 15.0,
                        "large_payload": ["forbidden"] * 1000,
                    },
                },
            }
        )

        self.assertEqual(compact["ready_proof_queue"]["ready_census"], 904)
        self.assertEqual(compact["ready_proof_queue"]["selected"], 256)
        self.assertNotIn("large_payload", compact["ready_proof_queue"])

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

    def test_ready_queue_processed_count_uses_actual_planned_tracking_updates(self):
        def provider(args):
            args.fastlane_executed_queue_metrics = {
                "ready_census": 5,
                "selected": 3,
                "processed": 0,
                "remaining": 5,
            }
            return {
                "tracking_updates": [
                    {"run_id": args.action_run_id, "state_key": "state-1"},
                    {"run_id": args.action_run_id, "state_key": "state-2"},
                ],
                "action_events": [],
                "summary": {"tracking_upsert_count": 2},
                "inbox_checkpoint_intent": {"updates_n4_outbox": False},
            }

        manifest = poller_script.run_n5_live_tracking_poller_once(
            self.base_args(),
            plan_provider=provider,
        )

        queue = manifest["fastlane"]["ready_proof_queue"]
        self.assertEqual(queue["ready_census"], 5)
        self.assertEqual(queue["selected"], 3)
        self.assertEqual(queue["processed"], 2)
        self.assertEqual(queue["remaining"], 3)

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
            current_tracking_row = {
                "run_id": ACTION_RUN_ID,
                "trade_date": TRADE_DATE,
                "asset_kind": "stock",
                "identity_key": "stock:SZ:002745",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:M,W,D",
                "source_trigger_run_id": "trigger_provisional_ordinary_20260702_until_0951",
                "source_trigger_event_id": "evt-n4-002745",
                "state_key": "state-key-002745",
                "latest_n4_event_time": "2026-07-02T10:21:00+08:00",
                "action_state": "eligible",
                "tracking_status": "tracking",
                "trigger_live": True,
                "current_status": "matched",
                "raw_json": {"next_unchecked_minute_label": "10:21"},
            }
            with (
                patch.object(
                    poller_script,
                    "_fetch_active_tracking_rows_by_state_keys",
                    return_value=[current_tracking_row],
                ) as fetch_rows,
                patch.object(
                    poller_script,
                    "_build_executed_candidate_plan",
                    return_value={"summary": {"action_executed_count": 1, "tracking_upsert_count": 1}},
                ) as build_plan,
            ):
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
        self.assertEqual(runtime_inputs["fastlane_target_minute_label"], "1021")
        self.assertEqual(cursor.object_minute_params[:3], (TRADE_DATE, "stock:SZ:002745", "10:21"))
        fetch_rows.assert_called_once_with(
            cursor,
            unittest.mock.ANY,
            action_run_id=ACTION_RUN_ID,
            state_keys=["state-key-002745"],
        )
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

    def test_executed_discovery_selects_non_confirmable_1500_ref(self):
        cursor = ExecutedCustomFinalNoActionDiscoveryCursor(
            {
                "run_id": ACTION_RUN_ID,
                "asset_kind": "board",
                "identity_key": "board:TDX:881446",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_HINT",
                "source_trigger_run_id": "n4-trigger-until-1500",
                "source_trigger_event_id": "evt-n4-match-1500",
                "state_key": "state-key-no-evaluable-1500",
                "trigger_time": "2026-07-02T15:00:00+08:00",
                "latest_n4_event_time": "2026-07-02T15:00:00+08:00",
                "last_checked_minute_label": "",
                "next_unchecked_minute_label": "",
                "source_metric_run_id": "",
                "target_minute_label": "",
                "latest_metric_reason": "",
                "raw_json": {},
                "source_run_hash": "",
                "active_tracking_count": 1,
            }
        )

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
        self.assertEqual(runtime_inputs["state_key"], "state-key-no-evaluable-1500")
        self.assertEqual(runtime_inputs["fastlane_target_minute_label"], "1500")
        self.assertRegex(
            runtime_inputs["source_metric_run_id"],
            rf"^n5_post_close_no_action_terminalization_{TRADE_DATE}_[0-9a-f]{{12}}$",
        )
        discovery_sql, discovery_params = next(
            (sql, params) for sql, params in cursor.calls if "post_close_no_action_candidates" in sql
        )
        self.assertIn("latest_n4_event_time AT TIME ZONE 'Asia/Shanghai'", discovery_sql)
        self.assertEqual(discovery_params[2:4], ("14:59", "14:59"))
        self.assertFalse(cursor.reached_broad_scan)
        build_plan.assert_called_once()
        self.assertEqual(build_plan.call_args.args[2]["target_minute_label"], "1500")

    def test_post_close_no_action_discovery_rejects_unchecked_pre_close_ref(self):
        cursor = ExecutedCustomFinalNoActionDiscoveryCursor(
            {
                "run_id": ACTION_RUN_ID,
                "asset_kind": "board",
                "identity_key": "board:TDX:881446",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY_HINT",
                "source_trigger_run_id": "n4-trigger-until-1458",
                "source_trigger_event_id": "evt-n4-match-1458",
                "state_key": "state-key-evaluable-1458",
                "trigger_time": "2026-07-02T14:58:00+08:00",
                "latest_n4_event_time": "2026-07-02T14:58:00+08:00",
                "last_checked_minute_label": "",
                "next_unchecked_minute_label": "",
                "source_metric_run_id": "",
                "target_minute_label": "",
                "latest_metric_reason": "",
                "raw_json": {},
                "source_run_hash": "",
                "active_tracking_count": 1,
            }
        )

        with patch.object(poller_script, "_build_executed_candidate_plan") as build_plan:
            runtime_inputs = poller_script._discover_post_close_no_action_terminalization_runtime_inputs(
                cursor,
                SimpleNamespace(for_trade_date=TRADE_DATE),
            )

        self.assertEqual(runtime_inputs, {})
        build_plan.assert_not_called()

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

    def test_active_scope_artifact_atomic_replace_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "n5_active_scope_snapshot_v1.json"
            existing = b'{"artifact_type":"n5_active_scope_snapshot_v1","scope_count":7}\n'
            artifact_path.write_bytes(existing)
            args = SimpleNamespace(
                active_scope_artifact_path=str(artifact_path),
                action_run_id=ACTION_RUN_ID,
                for_trade_date=TRADE_DATE,
                source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
                user_confirmed=True,
                write_active_scope_artifact=True,
            )
            plan = {
                "active_scope_snapshot_artifact": {
                    "artifact_type": "n5_active_scope_snapshot_v1",
                    "scope_count": 1,
                }
            }

            with patch(
                "ashare_v3.runtime.bounded_worker_control.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    poller_script._write_active_scope_artifact(args, plan)

            self.assertEqual(artifact_path.read_bytes(), existing)
            self.assertEqual(list(artifact_path.parent.glob(f".{artifact_path.name}.tmp.*")), [])

    def test_executed_phase_explicit_active_scope_is_allowlist_and_db_state_is_authoritative(self):
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
        current_db_ref = {
            **active_ref,
            "trade_date": TRADE_DATE,
            "last_checked_minute_label": "10:00",
            "raw_json": {
                **active_ref["raw_json"],
                "next_unchecked_minute_label": "10:01",
            },
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
                patch.object(
                    poller_script,
                    "_fetch_active_tracking_rows_by_state_keys",
                    return_value=[current_db_ref],
                ) as fetch_rows,
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
        self.assertEqual(
            kwargs["active_tracking_rows"][0]["raw_json"]["next_unchecked_minute_label"],
            "10:01",
        )
        self.assertEqual(kwargs["active_scope_tracking_rows"][0]["state_key"], state_key)
        fetch_rows.assert_called_once_with(
            unittest.mock.ANY,
            args,
            action_run_id=ACTION_RUN_ID,
            state_keys=[state_key],
        )

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

    def test_executed_active_scope_candidates_rehydrate_db_cursor_and_filter_terminal(self):
        state_key = poller.build_action_tracking_state_key(
            trade_date=TRADE_DATE,
            asset_kind="stock",
            identity_key="stock:SH:600000",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_MAIN",
        )
        terminal_state_key = poller.build_action_tracking_state_key(
            trade_date=TRADE_DATE,
            asset_kind="stock",
            identity_key="stock:SH:600001",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_MAIN",
        )
        stale_artifact_row = {
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
            "last_checked_minute_label": "09:59",
            "raw_json": {"next_unchecked_minute_label": "10:00"},
        }
        stale_terminal_row = {
            **stale_artifact_row,
            "state_key": terminal_state_key,
            "identity_key": "stock:SH:600001",
        }
        current_db_row = {
            **stale_artifact_row,
            "last_checked_minute_label": "10:00",
            "raw_json": {"next_unchecked_minute_label": "10:01"},
        }
        args = SimpleNamespace(for_trade_date=TRADE_DATE)
        candidates = poller_script._active_scope_rows_to_executed_candidates(
            args,
            [stale_artifact_row, stale_terminal_row],
        )

        with patch.object(
            poller_script,
            "_fetch_active_tracking_rows_by_state_keys",
            return_value=[current_db_row],
        ) as fetch_rows:
            rehydrated = poller_script._rehydrate_active_scope_executed_candidates(
                None,
                args,
                candidates,
            )

        self.assertEqual(len(rehydrated), 1)
        self.assertEqual(rehydrated[0]["state_key"], state_key)
        self.assertEqual(rehydrated[0]["target_minute_label"], "1001")
        self.assertEqual(
            rehydrated[0]["active_tracking_row"]["raw_json"]["next_unchecked_minute_label"],
            "10:01",
        )
        fetch_rows.assert_called_once_with(
            None,
            args,
            action_run_id=ACTION_RUN_ID,
            state_keys=[state_key, terminal_state_key],
        )

    def test_executed_active_scope_rehydrate_clamps_db_cursor_to_trigger_lower_bound(self):
        state_key = poller.build_action_tracking_state_key(
            trade_date=TRADE_DATE,
            asset_kind="stock",
            identity_key="stock:SZ:000737",
            direction="sell",
            signal_type="S_SELL",
            condition_key="SELL:Y,W,D",
        )
        artifact_row = {
            "run_id": ACTION_RUN_ID,
            "state_key": state_key,
            "trade_date": TRADE_DATE,
            "asset_kind": "stock",
            "identity_key": "stock:SZ:000737",
            "direction": "sell",
            "signal_type": "S_SELL",
            "condition_key": "SELL:Y,W,D",
            "latest_n4_event_time": "2026-07-02T10:21:00+08:00",
            "action_state": "eligible",
            "confirmation_status": "pending",
            "tracking_status": "tracking",
            "last_checked_minute_label": "10:19",
            "raw_json": {"next_unchecked_minute_label": "10:21"},
        }
        current_db_row = {
            **artifact_row,
            "raw_json": {"next_unchecked_minute_label": "10:20"},
        }
        args = SimpleNamespace(for_trade_date=TRADE_DATE)
        candidates = poller_script._active_scope_rows_to_executed_candidates(args, [artifact_row])

        with patch.object(
            poller_script,
            "_fetch_active_tracking_rows_by_state_keys",
            return_value=[current_db_row],
        ):
            rehydrated = poller_script._rehydrate_active_scope_executed_candidates(
                None,
                args,
                candidates,
            )

        self.assertEqual(len(rehydrated), 1)
        self.assertEqual(rehydrated[0]["target_minute_label"], "1021")
        self.assertEqual(
            rehydrated[0]["active_tracking_row"]["raw_json"]["next_unchecked_minute_label"],
            "10:21",
        )

    def test_executed_batch_plan_does_not_restore_stale_artifact_terminal_row(self):
        candidate = {
            "run_id": ACTION_RUN_ID,
            "state_key": "stale-terminal-state-key",
            "source_trigger_run_id": "",
            "source_metric_run_id": SOURCE_METRIC_RUN_ID,
            "active_tracking_row": {
                "run_id": ACTION_RUN_ID,
                "state_key": "stale-terminal-state-key",
                "trade_date": TRADE_DATE,
                "action_state": "eligible",
                "tracking_status": "tracking",
            },
        }
        args = SimpleNamespace(
            for_trade_date=TRADE_DATE,
            consumer_name=CONSUMER_NAME,
        )

        with (
            patch.object(poller_script, "_fetch_active_tracking_rows_by_state_keys", return_value=[]),
            patch.object(
                poller_script,
                "build_live_tracking_plan",
                side_effect=AssertionError("stale artifact row must not reach planner"),
            ),
        ):
            with self.assertRaisesRegex(
                poller_script.N5LiveTrackingBlocked,
                "active_tracking_rows_required_for_executed_batch",
            ):
                poller_script._build_executed_batch_candidate_plan(None, args, [candidate])

    def test_executed_batch_plan_aligns_refetched_cursor_to_exact_candidate_target(self):
        state_key = "state-000737"
        active_row = {
            "run_id": ACTION_RUN_ID,
            "state_key": state_key,
            "trade_date": TRADE_DATE,
            "action_state": "eligible",
            "tracking_status": "tracking",
            "raw_json": {"next_unchecked_minute_label": "10:20"},
        }
        candidate = {
            "run_id": ACTION_RUN_ID,
            "state_key": state_key,
            "source_trigger_run_id": "",
            "source_metric_run_id": SOURCE_METRIC_RUN_ID,
            "target_minute_label": "1021",
        }
        captured = {}

        def build_plan(**kwargs):
            captured.update(kwargs)
            return {"summary": {}, "tracking_updates": [], "action_events": []}

        args = SimpleNamespace(
            for_trade_date=TRADE_DATE,
            consumer_name=CONSUMER_NAME,
        )
        with (
            patch.object(
                poller_script,
                "_fetch_active_tracking_rows_by_state_keys",
                return_value=[active_row],
            ),
            patch.object(poller_script, "_fetch_metric_rows", return_value=[]),
            patch.object(poller_script, "_fetch_existing_action_event_keys", return_value=set()),
            patch.object(poller_script, "_fetch_active_scope_tracking_rows", return_value=[]),
            patch.object(poller_script, "build_live_tracking_plan", side_effect=build_plan),
        ):
            poller_script._build_executed_batch_candidate_plan(None, args, [candidate])

        self.assertEqual(
            captured["active_tracking_rows"][0]["raw_json"]["next_unchecked_minute_label"],
            "10:21",
        )

    def test_activation_discovery_hands_target_minute_to_final_state_key_plan(self):
        args = poller_script.build_arg_parser().parse_args(
            [
                "--activation-config",
                "activation.json",
                "--fastlane-phase",
                "executed",
            ]
        )
        config = {
            "for_trade_date": TRADE_DATE,
            "runtime_inputs": {"n5_action_executed": {}},
        }

        with (
            patch.object(poller_script, "load_fastlane_activation_config", return_value=config),
            patch.object(poller_script, "_apply_fastlane_worker_phase_gate"),
        ):
            poller_script._apply_activation_config(
                args,
                activation_discovery_provider=lambda _args, _config: {
                    "action_run_id": ACTION_RUN_ID,
                    "source_metric_run_id": SOURCE_METRIC_RUN_ID,
                    "consumer_name": CONSUMER_NAME,
                    "state_key": "state-000737",
                    "fastlane_target_minute_label": "1021",
                },
            )

        self.assertEqual(args.fastlane_ref_state_key, "state-000737")
        self.assertEqual(args.fastlane_target_minute_label, "1021")

    def test_final_state_key_plan_aligns_db_cursor_to_discovered_target_minute(self):
        args = SimpleNamespace(
            fastlane_phase="executed",
            fastlane_ref_state_key="state-000737",
            fastlane_target_minute_label="1021",
            for_trade_date=TRADE_DATE,
        )
        rows = [
            {
                "state_key": "state-000737",
                "latest_n4_event_time": "2026-07-02T10:21:00+08:00",
                "raw_json": {"next_unchecked_minute_label": "10:20"},
            },
            {
                "state_key": "other-state",
                "raw_json": {"next_unchecked_minute_label": "10:20"},
            },
        ]

        aligned = poller_script._align_fastlane_state_key_target_cursor(args, rows)

        self.assertEqual(aligned[0]["raw_json"]["next_unchecked_minute_label"], "10:21")
        self.assertEqual(aligned[1]["raw_json"]["next_unchecked_minute_label"], "10:20")

    def test_final_state_key_plan_drops_stale_target_when_db_cursor_is_ahead(self):
        args = SimpleNamespace(
            fastlane_phase="executed",
            fastlane_ref_state_key="state-000737",
            fastlane_target_minute_label="1021",
            for_trade_date=TRADE_DATE,
        )
        rows = [
            {
                "state_key": "state-000737",
                "latest_n4_event_time": "2026-07-02T10:21:00+08:00",
                "last_checked_minute_label": "10:21",
                "raw_json": {"next_unchecked_minute_label": "10:22"},
            },
            {
                "state_key": "other-state",
                "raw_json": {"next_unchecked_minute_label": "10:20"},
            },
        ]

        aligned = poller_script._align_fastlane_state_key_target_cursor(args, rows)

        self.assertEqual([row["state_key"] for row in aligned], ["other-state"])
        self.assertEqual(rows[0]["raw_json"]["next_unchecked_minute_label"], "10:22")

    def test_final_state_key_plan_uses_last_checked_when_next_cursor_is_empty(self):
        args = SimpleNamespace(
            fastlane_phase="executed",
            fastlane_ref_state_key="state-000737",
            fastlane_target_minute_label="1021",
            for_trade_date=TRADE_DATE,
        )
        row = {
            "state_key": "state-000737",
            "last_checked_minute_label": "10:22",
            "raw_json": {"next_unchecked_minute_label": ""},
        }

        aligned = poller_script._align_fastlane_state_key_target_cursor(args, [row])

        self.assertEqual(aligned, [])
        self.assertEqual(row["raw_json"]["next_unchecked_minute_label"], "")

    def test_empty_next_cursor_requires_target_strictly_after_last_checked(self):
        row = {
            "last_checked_minute_label": "10:22",
            "raw_json": {"next_unchecked_minute_label": ""},
        }

        self.assertTrue(
            poller_script._candidate_target_precedes_tracking_cursor(
                row,
                "1021",
                for_trade_date=TRADE_DATE,
            )
        )
        self.assertTrue(
            poller_script._candidate_target_precedes_tracking_cursor(
                row,
                "1022",
                for_trade_date=TRADE_DATE,
            )
        )
        self.assertFalse(
            poller_script._candidate_target_precedes_tracking_cursor(
                row,
                "1023",
                for_trade_date=TRADE_DATE,
            )
        )

    def test_final_minute_cannot_recreate_empty_next_cursor(self):
        row = {
            "last_checked_minute_label": "15:00",
            "raw_json": {"next_unchecked_minute_label": ""},
        }

        self.assertTrue(
            poller_script._candidate_target_precedes_tracking_cursor(
                row,
                "1500",
                for_trade_date=TRADE_DATE,
            )
        )

    def test_candidate_target_cursor_comparison_uses_canonical_lunch_order(self):
        at_afternoon_open = {
            "raw_json": {"next_unchecked_minute_label": "13:00"},
        }
        at_morning_close = {
            "raw_json": {"next_unchecked_minute_label": "11:29"},
        }

        self.assertTrue(
            poller_script._candidate_target_precedes_tracking_cursor(
                at_afternoon_open,
                "1129",
                for_trade_date=TRADE_DATE,
            )
        )
        self.assertFalse(
            poller_script._candidate_target_precedes_tracking_cursor(
                at_morning_close,
                "1300",
                for_trade_date=TRADE_DATE,
            )
        )

    def test_executed_batch_plan_drops_only_stale_discovery_target(self):
        stale_state_key = "state-stale"
        ready_state_key = "state-ready"
        rows = [
            {
                "run_id": ACTION_RUN_ID,
                "state_key": stale_state_key,
                "trade_date": TRADE_DATE,
                "action_state": "eligible",
                "tracking_status": "tracking",
                "raw_json": {"next_unchecked_minute_label": "10:22"},
            },
            {
                "run_id": ACTION_RUN_ID,
                "state_key": ready_state_key,
                "trade_date": TRADE_DATE,
                "action_state": "eligible",
                "tracking_status": "tracking",
                "raw_json": {"next_unchecked_minute_label": "10:21"},
            },
        ]
        candidates = [
            {
                "run_id": ACTION_RUN_ID,
                "state_key": stale_state_key,
                "source_metric_run_id": "metric-stale",
                "target_minute_label": "1021",
            },
            {
                "run_id": ACTION_RUN_ID,
                "state_key": ready_state_key,
                "source_metric_run_id": "metric-ready",
                "target_minute_label": "1021",
            },
        ]
        captured = {}

        def build_plan(**kwargs):
            captured.update(kwargs)
            return {"summary": {}, "tracking_updates": [], "action_events": []}

        args = SimpleNamespace(
            for_trade_date=TRADE_DATE,
            consumer_name=CONSUMER_NAME,
        )
        with (
            patch.object(
                poller_script,
                "_fetch_active_tracking_rows_by_state_keys",
                return_value=rows,
            ),
            patch.object(poller_script, "_fetch_metric_rows", return_value=[]),
            patch.object(poller_script, "_fetch_existing_action_event_keys", return_value=set()),
            patch.object(poller_script, "_fetch_active_scope_tracking_rows", return_value=[]),
            patch.object(poller_script, "build_live_tracking_plan", side_effect=build_plan),
        ):
            poller_script._build_executed_batch_candidate_plan(None, args, candidates)

        self.assertEqual(
            [row["state_key"] for row in captured["active_tracking_rows"]],
            [ready_state_key],
        )
        self.assertEqual(
            captured["active_tracking_rows"][0]["raw_json"]["next_unchecked_minute_label"],
            "10:21",
        )

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

    def test_tracking_upsert_orders_rows_by_tracking_unique_key(self):
        first = trigger_matched("n4-match-z", identity_key="stock:SH:600001")
        second = trigger_matched("n4-match-a", identity_key="stock:SH:600000")
        plan = poller.build_live_tracking_plan(
            n4_event_rows=[first, second],
            active_tracking_rows=[],
            metric_rows=[],
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id=SOURCE_TRIGGER_RUN_ID,
            source_metric_run_id=SOURCE_METRIC_RUN_ID,
            consumer_name=CONSUMER_NAME,
            for_trade_date=TRADE_DATE,
        )
        cursor = TrackingUpsertCursor()

        poller_script._upsert_tracking_states(cursor, list(reversed(plan["tracking_updates"])))

        keys = [(values[0], values[7]) for values in cursor.values]
        self.assertEqual(keys, sorted(keys))

    def test_default_execute_writer_retries_deadlock_without_partial_second_write(self):
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.commits = 0

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.commits += 1

        first = FakeConnection()
        second = FakeConnection()
        args = SimpleNamespace(dsn="postgresql:///unused", fastlane_phase="intake")
        plan = {
            "tracking_updates": [
                {"run_id": ACTION_RUN_ID, "state_key": f"state-{index:03d}"}
                for index in range(256)
            ],
            "action_events": [],
        }
        deadlock = poller_script.psycopg.errors.DeadlockDetected("deadlock")

        with (
            patch.object(poller_script.psycopg, "connect", side_effect=[first, second]) as connect,
            patch.object(poller_script, "_upsert_tracking_states", side_effect=[deadlock, 256]),
            patch.object(poller_script, "_insert_action_outbox_events", return_value=0),
            patch.object(poller_script.time, "sleep") as sleep,
        ):
            result = poller_script._default_execute_writer(args, plan)

        self.assertEqual(result["common_action_tracking_state"], 256)
        self.assertEqual(connect.call_count, 2)
        self.assertEqual(first.commits, 0)
        self.assertEqual(second.commits, 1)
        sleep.assert_called_once_with(0.05)

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

    def test_tracking_upsert_sql_allows_only_explicit_terminal_episode_reopen(self):
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

        self.assertIn(
            "common_action_tracking_state.action_state IN ('expired', 'executed')",
            cursor.sql,
        )
        self.assertIn("EXCLUDED.action_state = 'eligible'", cursor.sql)
        self.assertIn("terminal_ref_reopen_allowed", cursor.sql)
        self.assertIn("terminal_episode_inactive_boundary", cursor.sql)
        self.assertIn("closed_source_trigger_event_id", cursor.sql)
        self.assertIn("= 'TriggerStateChanged'", cursor.sql)
        self.assertIn("EXCLUDED.source_trigger_event_type = 'TriggerMatched'", cursor.sql)
        self.assertIn(
            "EXCLUDED.source_trigger_event_id IS DISTINCT FROM common_action_tracking_state.source_trigger_event_id",
            cursor.sql,
        )
        self.assertIn(
            "WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.action_state",
            cursor.sql,
        )

    def test_active_set_a_intake_fetches_terminal_rows_for_reopen_decision(self):
        class FetchCursor:
            def __init__(self):
                self.sql = ""
                self.params = None

            def execute(self, sql, params):
                self.sql = sql
                self.params = params

            def fetchall(self):
                return []

        cursor = FetchCursor()
        args = SimpleNamespace(
            for_trade_date=TRADE_DATE,
            action_run_id=ACTION_RUN_ID,
            source_trigger_run_id="",
            fastlane_ref_state_key="",
        )

        with patch.object(poller_script, "_is_fastlane_executed_phase", return_value=False), patch.object(
            poller_script,
            "_is_active_set_a_intake",
            return_value=True,
        ):
            rows = poller_script._fetch_active_tracking_rows(
                cursor,
                args,
                n4_event_rows=[trigger_matched()],
            )

        self.assertEqual(rows, [])
        self.assertIn("state_key = ANY", cursor.sql)
        self.assertNotIn("action_state = 'eligible'", cursor.sql)
        self.assertNotIn("tracking_status = 'tracking'", cursor.sql)
        self.assertIn("latest_n4_event_time DESC NULLS LAST", cursor.sql)

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

    def test_candidate_target_minute_clamps_explicit_target_to_trigger_lower_bound(self):
        candidate = {
            "target_minute_label": "1020",
            "trigger_time": "2026-07-02T10:21:00+08:00",
            "last_checked_minute_label": "10:19",
            "next_unchecked_minute_label": "10:20",
        }

        target = poller_script._candidate_target_minute_label(
            candidate,
            for_trade_date=TRADE_DATE,
        )

        self.assertEqual(target, "1021")

    def test_post_close_done_evidence_rejects_non_advancing_cursor_guard(self):
        update = {
            "state_key": "state-000737",
            "action_state": "eligible",
            "confirmation_status": "pending",
            "tracking_status": "tracking",
            "raw_json": {
                "latest_metric_status": {
                    "status": "pending",
                    "reason": "metric_after_next_unchecked_minute_label",
                    "metric_evaluation_key": "pending|metric_after_next_unchecked_minute_label",
                },
            },
        }

        self.assertFalse(
            poller_script._tracking_update_has_terminal_or_evaluation_evidence(update)
        )

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
