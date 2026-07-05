import inspect
import unittest

from ashare_v3.action.provisional_action_executed_dry_run import (
    ACTION_EXECUTED_PLAN,
    BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF,
    NOT_EXECUTED_RULE_FAILED,
    PENDING_NO_CLOSED_METRIC,
    build_provisional_action_executed_dry_run_report,
)


FOR_TRADE_DATE = "20260624"
ELIGIBLE_ACTION_RUN_ID = (
    "action_provisional_eligible_20260624__"
    "trigger_provisional_ordinary_20260624_until_1023"
)
SOURCE_TRIGGER_RUN_ID = "trigger_provisional_ordinary_20260624_until_1023"
SOURCE_METRIC_RUN_ID = "n5_action_confirmation_metric_v2_20260624_until_1023__asset_all"
CONFIRMATION_METRIC_RUN_ID = "n5_action_confirmation_metric_v2_20260624_until_1024__asset_all"
CONFIRMATION_PROJECTION_RUN_ID = "realtime_projection_metric_20260624_until_1024__snapshot_for_hint"
N5_CONFIRMATION_METRIC_V2_KIND = "n5_action_confirmation_metric_v2"


def eligible_row(
    index: int,
    *,
    condition_key: str = "BUY:D",
    signal_type: str = "B_BUY",
    trigger_type: str = "BUY",
    identity_key: str | None = None,
    selected_metric_time: str = "2026-06-24T10:23:00+08:00",
    event_type: str = "ActionEligible",
) -> dict[str, object]:
    asset_kind = "stock"
    resolved_identity = identity_key or f"stock:SH:{600000 + index:06d}"
    action_type = "buy" if signal_type == "B_BUY" else "sell"
    return {
        "event_id": f"evt_n5p_eligible_{index}",
        "event_type": event_type,
        "source_layer": "N5_action",
        "source_run_id": ELIGIBLE_ACTION_RUN_ID,
        "asset_kind": asset_kind,
        "identity_key": resolved_identity,
        "event_time": selected_metric_time,
        "payload_json": {
            "event_type": event_type,
            "provisional": True,
            "action_confirmation_mode": "eligibility_only",
            "action_state": "eligible",
            "confirmation_status": "pending",
            "source_trigger_event_id": f"evt_n4p_trigger_{index}",
            "source_trigger_run_id": SOURCE_TRIGGER_RUN_ID,
            "source_metric_kind": N5_CONFIRMATION_METRIC_V2_KIND,
            "source_metric_run_id": SOURCE_METRIC_RUN_ID,
            "selected_metric_id": 900000 + index,
            "selected_metric_time": selected_metric_time,
            "metric_time_label": "2026-06-24 10:23",
            "metric_minute_label": "10:23",
            "is_closed_1m": False,
            "for_trade_date": FOR_TRADE_DATE,
            "asset_kind": asset_kind,
            "identity_key": resolved_identity,
            "display_name": resolved_identity,
            "condition_key": condition_key,
            "signal_type": signal_type,
            "trigger_type": trigger_type,
            "action_type": action_type,
            "trigger_mark_candidate": "normal",
            "rule_proof": {"rule_reused": "rule_v4_matcher"},
            "trace": {"source": "n4p_ordinary"},
            "canonical_action_identity_key": f"eligible-key-{index}",
        },
    }


def confirmation_metric_row(
    index: int,
    *,
    condition_key: str = "BUY:D",
    signal_type: str = "B_BUY",
    identity_key: str | None = None,
    metric_id: int | None = None,
    metric_run_id: str = CONFIRMATION_METRIC_RUN_ID,
    metric_minute_label: str = "10:23",
    metric_time: str = "2026-06-24T10:23:00+08:00",
    is_closed_1m: bool = True,
    metric_ready: bool = True,
    all_flags_pass: bool = True,
    current_30m_virtual_amount: str | None = None,
    previous_day_same_window_amount: str = "1000",
) -> dict[str, object]:
    resolved_identity = identity_key or f"stock:SH:{600000 + index:06d}"
    buy_pass = all_flags_pass if signal_type == "B_BUY" else True
    sell_pass = all_flags_pass if signal_type == "S_SELL" else True
    return {
        "asset_kind": "stock",
        "identity_key": resolved_identity,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "action_confirmation_metric_id": metric_id if metric_id is not None else 950000 + index,
            "projection_run_id": metric_run_id,
            "source_metric_kind": N5_CONFIRMATION_METRIC_V2_KIND,
        "metric_time": metric_time,
        "metric_minute_label": metric_minute_label,
        "metric_time_label": "2026-06-24 10:23",
        "is_closed_1m": is_closed_1m,
        "metric_ready": metric_ready,
        "metric_quality_status": "passed" if metric_ready else "failed",
        "virtual_amount_policy_version": "previous_day_same_window_elapsed_ratio_v1",
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
        "current_30m_virtual_amount": current_30m_virtual_amount
        if current_30m_virtual_amount is not None
        else ("1200" if signal_type == "B_BUY" else "800"),
        "previous_day_same_window_amount": previous_day_same_window_amount,
        "previous_30m_full_amount": previous_day_same_window_amount,
        "source_fact_ids": {"source_today_minute_run_id": "today_minute_bar_1m_20260624_until_1024"},
        "trace_json": {"closed_minute_proof": {"is_closed_1m": is_closed_1m}},
    }


def hint_eligible_row(
    index: int,
    *,
    condition_key: str = "BUY_HINT",
    signal_type: str = "B_BUY",
    identity_key: str | None = None,
    trigger_time: str = "2026-06-24T10:23:00+08:00",
) -> dict[str, object]:
    row = eligible_row(
        index,
        condition_key=condition_key,
        signal_type=signal_type,
        trigger_type=condition_key,
        identity_key=identity_key,
        selected_metric_time=trigger_time,
    )
    payload = row["payload_json"]
    if not isinstance(payload, dict):
        raise AssertionError("test helper expected dict payload")
    for field in (
        "source_metric_kind",
        "source_metric_run_id",
        "selected_metric_id",
        "selected_metric_time",
        "metric_time_label",
        "metric_minute_label",
    ):
        payload.pop(field, None)
    projection_30m_type = "volume_up" if condition_key == "BUY_HINT" else "shrink_down"
    trigger_mark_candidate = "30m_volume" if condition_key == "BUY_HINT" else "30m_shrink"
    payload.update(
        {
            "source_fact_kind": "realtime_projection_metric",
            "projection_run_id": "realtime_projection_metric_20260624_until_1023__snapshot_for_hint",
            "projection_id": 880000 + index,
            "projection_30m_type": projection_30m_type,
            "trigger_mark_candidate": trigger_mark_candidate,
            "trigger_time": trigger_time,
            "trace": {"source": "n4p_hint"},
            "canonical_action_identity_key": f"hint-eligible-key-{index}",
        }
    )
    row["event_time"] = trigger_time
    return row


def confirmation_projection_row(
    index: int,
    *,
    condition_key: str = "BUY_HINT",
    identity_key: str | None = None,
    projection_run_id: str = CONFIRMATION_PROJECTION_RUN_ID,
    projection_status: str = "ready",
    projection_quality_status: str = "passed",
    trace_status: str = "passed",
) -> dict[str, object]:
    resolved_identity = identity_key or f"stock:SH:{600000 + index:06d}"
    projection_signal_status = "up_volume_expanding" if condition_key == "BUY_HINT" else "down_volume_shrinking"
    projection_30m_type = "volume_up" if condition_key == "BUY_HINT" else "shrink_down"
    trigger_mark_candidate = "30m_volume" if condition_key == "BUY_HINT" else "30m_shrink"
    return {
        "asset_kind": "stock",
        "identity_key": resolved_identity,
        "projection_run_id": projection_run_id,
        "projection_id": 970000 + index,
        "projection_status": projection_status,
        "projection_quality_status": projection_quality_status,
        "trace_status": trace_status,
        "projection_signal_status": projection_signal_status,
        "projection_30m_type": projection_30m_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "metric_time": "2026-06-24T10:24:00+08:00",
        "projection_trace": {"source": "b2_confirmation"},
    }


class ProvisionalActionExecutedDryRunTest(unittest.TestCase):
    def test_closed_metric_found_generates_actionexecuted_plan_payload(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[eligible_row(1)],
            confirmation_metric_rows=[confirmation_metric_row(1)],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        self.assertEqual(report["action_executed_plan_count"], 1)
        plan = report["action_executed_plans"][0]
        payload = plan["payload"]
        self.assertEqual(payload["event_type"], "ActionExecuted")
        self.assertTrue(payload["provisional"])
        self.assertEqual(payload["action_confirmation_mode"], "intraday_closed_minute")
        self.assertEqual(payload["action_state"], "executed")
        self.assertEqual(payload["source_metric_run_id"], SOURCE_METRIC_RUN_ID)
        self.assertEqual(payload["confirmation_metric_run_id"], CONFIRMATION_METRIC_RUN_ID)
        self.assertEqual(payload["confirmation_metric_id"], 950001)
        self.assertEqual(payload["selected_metric_time"], "2026-06-24T10:23:00+08:00")
        self.assertEqual(payload["metric_minute_label"], "10:23")
        self.assertTrue(payload["is_closed_1m"])
        self.assertEqual(payload["action_mark"], "30m_volume")
        self.assertIn("30m_volume", payload["canonical_action_identity_key"])
        self.assertNotEqual(payload["canonical_action_identity_key"], "eligible-key-1")
        self.assertFalse(report["side_effect_guard"]["db_written"])

    def test_n3p_trigger_proof_is_blocked_as_actionexecuted_final_proof(self) -> None:
        row = eligible_row(1)
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise AssertionError("test helper expected dict payload")
        payload.update(
            {
                "source_metric_kind": "realtime_action_confirmation_metric",
                "metric_role": "trigger_proof",
                "not_n5_final_proof": True,
                "source_trigger_proof_kind": "n3p_formal_amount_chain",
            }
        )

        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[row],
            confirmation_metric_rows=[confirmation_metric_row(1)],
            for_trade_date=FOR_TRADE_DATE,
        )

        self.assertEqual(report["decision_counts"], {BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)

    def test_missing_closed_metric_returns_pending_without_error(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[eligible_row(1)],
            confirmation_metric_rows=[],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
        )

        self.assertEqual(report["decision_counts"], {PENDING_NO_CLOSED_METRIC: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)
        self.assertEqual(report["decisions"][0]["reason"], "closed_confirmation_metric_not_found")

    def test_live_current_1m_ordinary_metric_still_requires_closed_confirmation_metric(self) -> None:
        row = eligible_row(1)
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise AssertionError("test helper expected dict payload")
        payload["source_mode"] = "live_current_1m"
        payload["c1_dependency"] = False

        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[row],
            confirmation_metric_rows=[
                confirmation_metric_row(1, is_closed_1m=False, metric_ready=True)
            ],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
        )

        self.assertEqual(report["decision_counts"], {PENDING_NO_CLOSED_METRIC: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)
        self.assertEqual(report["decisions"][0]["reason"], "closed_confirmation_metric_not_found")

    def test_closed_metric_rule_failed_returns_not_executed(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[eligible_row(1)],
            confirmation_metric_rows=[confirmation_metric_row(1, all_flags_pass=False)],
            for_trade_date=FOR_TRADE_DATE,
        )

        self.assertEqual(report["decision_counts"], {NOT_EXECUTED_RULE_FAILED: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)
        self.assertIn("confirmation_failed", report["decisions"][0]["reason"])

    def test_1023_trigger_can_be_confirmed_after_1024_by_minute_label(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[eligible_row(1, selected_metric_time="2026-06-24T10:23:00+08:00")],
            confirmation_metric_rows=[
                confirmation_metric_row(
                    1,
                    metric_run_id=CONFIRMATION_METRIC_RUN_ID,
                    metric_minute_label="10:23",
                    metric_time="2026-06-24T10:23:00+08:00",
                )
            ],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        self.assertEqual(report["action_executed_plans"][0]["payload"]["metric_minute_label"], "10:23")

    def test_duplicate_eligible_and_confirmation_metrics_dedup_deterministically(self) -> None:
        first = eligible_row(1)
        duplicate = dict(first)
        duplicate["event_id"] = "evt_n5p_eligible_1_duplicate"
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[first, duplicate],
            confirmation_metric_rows=[
                confirmation_metric_row(1, metric_id=950001),
                confirmation_metric_row(1, metric_id=950002),
            ],
            for_trade_date=FOR_TRADE_DATE,
        )

        self.assertEqual(report["action_executed_plan_count"], 1)
        self.assertEqual(report["action_executed_plans"][0]["payload"]["confirmation_metric_id"], 950002)
        self.assertEqual(report["decision_counts"][ACTION_EXECUTED_PLAN], 1)

    def test_buy_sell_full_supported_and_invalid_payload_skipped(self) -> None:
        rows = [
            eligible_row(1, condition_key="BUY:D", signal_type="B_BUY", trigger_type="BUY"),
            eligible_row(2, condition_key="SELL:D", signal_type="S_SELL", trigger_type="SELL"),
            eligible_row(3, condition_key="BUY:FULL", signal_type="B_BUY", trigger_type="BUY:FULL"),
            eligible_row(4, condition_key="SELL:FULL", signal_type="S_SELL", trigger_type="SELL:FULL"),
            eligible_row(6, event_type="ActionExecuted"),
        ]
        metrics = [
            confirmation_metric_row(1, condition_key="BUY:D", signal_type="B_BUY"),
            confirmation_metric_row(2, condition_key="SELL:D", signal_type="S_SELL"),
            confirmation_metric_row(3, condition_key="BUY:FULL", signal_type="B_BUY"),
            confirmation_metric_row(4, condition_key="SELL:FULL", signal_type="S_SELL"),
        ]

        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=rows,
            confirmation_metric_rows=metrics,
            for_trade_date=FOR_TRADE_DATE,
        )

        self.assertEqual(report["decision_counts"][ACTION_EXECUTED_PLAN], 4)
        self.assertEqual(report["decision_counts"]["SKIPPED_INVALID_PAYLOAD"], 1)
        self.assertEqual({plan["payload"]["trigger_type"] for plan in report["action_executed_plans"]}, {"BUY", "SELL", "BUY:FULL", "SELL:FULL"})

    def test_buy_hint_closed_n5_v2_confirmation_metric_generates_actionexecuted_plan(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[hint_eligible_row(1, condition_key="BUY_HINT", signal_type="B_BUY")],
            confirmation_metric_rows=[
                confirmation_metric_row(1, condition_key="BUY:D", signal_type="B_BUY")
            ],
            confirmation_projection_rows=[confirmation_projection_row(1, condition_key="BUY_HINT")],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["event_type"], "ActionExecuted")
        self.assertEqual(payload["source_metric_kind"], N5_CONFIRMATION_METRIC_V2_KIND)
        self.assertEqual(payload["source_metric_run_id"], CONFIRMATION_METRIC_RUN_ID)
        self.assertEqual(payload["confirmation_metric_run_id"], CONFIRMATION_METRIC_RUN_ID)
        self.assertEqual(payload["confirmation_metric_id"], 950001)
        self.assertNotIn("source_fact_kind", payload)
        self.assertNotIn("confirmation_projection_run_id", payload)
        self.assertEqual(payload["action_mark"], "30m_volume")
        self.assertEqual(payload["trigger_type"], "BUY_HINT")
        self.assertTrue(payload["is_closed_1m"])

    def test_buy_hint_action_mark_uses_n5_v2_metric_not_b2_trigger_candidate(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[hint_eligible_row(1, condition_key="BUY_HINT", signal_type="B_BUY")],
            confirmation_metric_rows=[
                confirmation_metric_row(
                    1,
                    condition_key="BUY:D",
                    signal_type="B_BUY",
                    current_30m_virtual_amount="900",
                    previous_day_same_window_amount="1000",
                )
            ],
            confirmation_projection_rows=[confirmation_projection_row(1, condition_key="BUY_HINT")],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["action_mark"], "normal")
        self.assertEqual(
            payload["trace"]["source_actioneligible_payload"]["trigger_mark_candidate"],
            "30m_volume",
        )

    def test_buy_hint_missing_trigger_type_uses_condition_key_for_legacy_payload(self) -> None:
        row = hint_eligible_row(1, condition_key="BUY_HINT", signal_type="B_BUY")
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise AssertionError("test helper expected dict payload")
        payload.pop("trigger_type", None)

        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[row],
            confirmation_metric_rows=[
                confirmation_metric_row(1, condition_key="BUY:D", signal_type="B_BUY")
            ],
            confirmation_projection_rows=[],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        self.assertEqual(report["action_executed_plans"][0]["payload"]["trigger_type"], "BUY_HINT")

    def test_sell_hint_closed_n5_v2_confirmation_metric_generates_actionexecuted_plan(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[hint_eligible_row(2, condition_key="SELL_HINT", signal_type="S_SELL")],
            confirmation_metric_rows=[
                confirmation_metric_row(2, condition_key="SELL:D", signal_type="S_SELL")
            ],
            confirmation_projection_rows=[confirmation_projection_row(2, condition_key="SELL_HINT")],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["source_metric_kind"], N5_CONFIRMATION_METRIC_V2_KIND)
        self.assertEqual(payload["source_metric_run_id"], CONFIRMATION_METRIC_RUN_ID)
        self.assertEqual(payload["confirmation_metric_run_id"], CONFIRMATION_METRIC_RUN_ID)
        self.assertEqual(payload["confirmation_metric_id"], 950002)
        self.assertNotIn("source_fact_kind", payload)
        self.assertEqual(payload["action_mark"], "30m_shrink")
        self.assertEqual(payload["action_type"], "sell")

    def test_sell_hint_missing_trigger_type_uses_condition_key_for_legacy_payload(self) -> None:
        row = hint_eligible_row(2, condition_key="SELL_HINT", signal_type="S_SELL")
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise AssertionError("test helper expected dict payload")
        payload.pop("trigger_type", None)

        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[row],
            confirmation_metric_rows=[
                confirmation_metric_row(2, condition_key="SELL:D", signal_type="S_SELL")
            ],
            confirmation_projection_rows=[],
            for_trade_date=FOR_TRADE_DATE,
            confirmation_metric_run_id=CONFIRMATION_METRIC_RUN_ID,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        self.assertEqual(report["action_executed_plans"][0]["payload"]["trigger_type"], "SELL_HINT")

    def test_buy_hint_with_sell_signal_remains_invalid(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[hint_eligible_row(1, condition_key="BUY_HINT", signal_type="S_SELL")],
            confirmation_metric_rows=[],
            confirmation_projection_rows=[confirmation_projection_row(1, condition_key="BUY_HINT")],
            for_trade_date=FOR_TRADE_DATE,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {"SKIPPED_INVALID_PAYLOAD": 1})

    def test_sell_hint_with_buy_signal_remains_invalid(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[hint_eligible_row(2, condition_key="SELL_HINT", signal_type="B_BUY")],
            confirmation_metric_rows=[],
            confirmation_projection_rows=[confirmation_projection_row(2, condition_key="SELL_HINT")],
            for_trade_date=FOR_TRADE_DATE,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {"SKIPPED_INVALID_PAYLOAD": 1})

    def test_buy_hint_without_n5_v2_metric_returns_pending_even_if_b2_ready(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[hint_eligible_row(1, condition_key="BUY_HINT", signal_type="B_BUY")],
            confirmation_metric_rows=[],
            confirmation_projection_rows=[confirmation_projection_row(1, condition_key="BUY_HINT")],
            for_trade_date=FOR_TRADE_DATE,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {PENDING_NO_CLOSED_METRIC: 1})
        self.assertEqual(report["decisions"][0]["reason"], "closed_confirmation_metric_not_found")

    def test_live_current_1m_hint_projection_without_n5_v2_metric_returns_pending(self) -> None:
        row = hint_eligible_row(1, condition_key="BUY_HINT", signal_type="B_BUY")
        payload = row["payload_json"]
        if not isinstance(payload, dict):
            raise AssertionError("test helper expected dict payload")
        payload["source_mode"] = "live_current_1m"
        payload["c1_dependency"] = False
        projection = confirmation_projection_row(1, condition_key="BUY_HINT")
        projection["source_mode"] = "live_current_1m"
        projection["c1_dependency"] = False
        projection["is_closed_1m"] = False

        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[row],
            confirmation_metric_rows=[],
            confirmation_projection_rows=[projection],
            for_trade_date=FOR_TRADE_DATE,
        )

        self.assertEqual(report["decision_counts"], {PENDING_NO_CLOSED_METRIC: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)
        self.assertEqual(report["decisions"][0]["reason"], "closed_confirmation_metric_not_found")

    def test_sell_hint_not_ready_b2_without_n5_v2_metric_returns_pending(self) -> None:
        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[hint_eligible_row(2, condition_key="SELL_HINT", signal_type="S_SELL")],
            confirmation_metric_rows=[],
            confirmation_projection_rows=[
                confirmation_projection_row(2, condition_key="SELL_HINT", projection_status="not_ready")
            ],
            for_trade_date=FOR_TRADE_DATE,
            latest_closed_minute="2026-06-24T10:24:00+08:00",
        )

        self.assertEqual(report["decision_counts"], {PENDING_NO_CLOSED_METRIC: 1})
        self.assertEqual(report["decisions"][0]["reason"], "closed_confirmation_metric_not_found")

    def test_static_side_effect_guard_forbids_db_and_downstream_paths(self) -> None:
        import ashare_v3.action.provisional_action_executed_dry_run as module

        report = build_provisional_action_executed_dry_run_report(
            actioneligible_rows=[eligible_row(1)],
            confirmation_metric_rows=[confirmation_metric_row(1)],
            for_trade_date=FOR_TRADE_DATE,
        )
        module_source = inspect.getsource(module)

        self.assertEqual(
            report["side_effect_guard"],
            {
                "db_written": False,
                "action_run_written": False,
                "action_event_written": False,
                "action_fact_written": False,
                "outbox_written": False,
                "inbox_written": False,
                "checkpoint_written": False,
                "n6_written": False,
                "sim_trade_virtual_written": False,
                "worker_started": False,
            },
        )
        self.assertNotIn("INSERT INTO", module_source)
        self.assertNotIn("audited_n5_action_connect", module_source)
        self.assertNotIn("common_event_inbox", module_source)
        self.assertNotIn("common_event_consumer_checkpoint", module_source)
        self.assertNotIn("virtual_order", module_source)
        self.assertNotIn("trade_order", module_source)


if __name__ == "__main__":
    unittest.main()
