import unittest
from datetime import datetime, timezone

from ashare_v3.action.event_factory import build_n5_action_event
from ashare_v3.events.models import EventContractError, validate_n5_trigger_fact_passthrough_payload


class ActionEventContractTest(unittest.TestCase):
    def test_canonical_action_executed_payload_contains_required_contract_fields(self) -> None:
        event = build_n5_action_event(
            event_type="ActionExecuted",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260525",
            event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
            action_run_id="action_run_20260525",
            source_trigger_run_id="trigger_run_20260525",
            source_trigger_event_id="evt_trigger_source",
            source_trigger_state_id=201,
            source_trigger_match_id=101,
            source_condition_run_id="condition_run_20260525",
            source_market_data_run_id="market_run_20260525",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_HINT",
            original_condition_key="BUY_HINT",
            trigger_period="30m",
            action_mark="30m_volume",
            action_state="executed",
            confirmation_status="passed",
            action_policy="n5_confirmation_only",
            eligibility_reason="all_minute_rules_passed",
            trace_json={"candidate_action_mark": "30m_volume"},
            data_quality_status="passed",
            payload={
                "source_layer": "N4_trigger",
                "n4_trigger_event_id": "evt_trigger_source",
                "trigger_price": "43.73",
                "triggered_periods": [],
                "all_trigger_periods": [],
                "primary_trigger_period": None,
                "trigger_kind": "hint",
                "period_trigger_baseline_trace": {
                    "traced_periods": {},
                    "projection_period": "30m",
                },
                "baseline_source": "projection_30m",
            },
        )

        self.assertEqual(event.source_layer, "N5_action")
        self.assertEqual(event.event_type, "ActionExecuted")
        self.assertEqual(event.partition_key, "stock:SH:600000")
        for key in (
            "run_id",
            "source_trigger_event_id",
            "source_trigger_run_id",
            "source_trigger_state_id",
            "source_trigger_match_id",
            "source_condition_run_id",
            "source_market_data_run_id",
            "source_market_trace",
            "action_key",
            "dedup_key",
            "identity_key",
            "asset_kind",
            "direction",
            "signal_type",
            "condition_key",
            "original_condition_key",
            "trigger_period",
            "action_mark",
            "action_state",
            "confirmation_status",
            "action_policy",
            "eligibility_reason",
            "trace_json",
            "data_quality_status",
            "event_schema_version",
            "n4_trigger_event_id",
            "trigger_price",
            "triggered_periods",
            "all_trigger_periods",
            "primary_trigger_period",
            "trigger_kind",
            "period_trigger_baseline_trace",
            "baseline_source",
        ):
            self.assertIn(key, event.payload_json)
        self.assertEqual(event.payload_json["direction"], "buy")
        self.assertEqual(event.payload_json["signal_type"], "B_BUY")
        self.assertEqual(event.payload_json["condition_key"], "BUY_HINT")
        self.assertEqual(event.payload_json["original_condition_key"], "BUY_HINT")
        self.assertEqual(event.payload_json["action_mark"], "30m_volume")
        self.assertEqual(event.payload_json["action_state"], "executed")
        self.assertEqual(event.payload_json["n4_trigger_event_id"], "evt_trigger_source")
        self.assertEqual(event.payload_json["trigger_price"], "43.73")
        self.assertEqual(event.payload_json["triggered_periods"], [])
        self.assertEqual(event.payload_json["all_trigger_periods"], [])
        self.assertIsNone(event.payload_json["primary_trigger_period"])
        self.assertEqual(event.payload_json["trigger_kind"], "hint")
        self.assertEqual(event.payload_json["baseline_source"], "projection_30m")

    def test_action_blocked_requires_trigger_fact_passthrough_payload(self) -> None:
        with self.assertRaisesRegex(EventContractError, "trigger fact passthrough"):
            build_n5_action_event(
                event_type="ActionBlocked",
                asset_kind="stock",
                identity_key="stock:SH:688690",
                trade_date="20260605",
                event_time=datetime(2026, 6, 5, 3, 6, tzinfo=timezone.utc),
                action_run_id="action_run_20260605",
                source_trigger_run_id="trigger_run_20260605",
                source_trigger_event_id="evt_61bf1423e33a28d3e19c879c71a8d24a5241bc16",
                source_trigger_state_id=201,
                source_trigger_match_id=101,
                source_condition_run_id="condition_run_20260605",
                source_market_trace={"source_event_id": "evt_market_source"},
                direction="buy",
                signal_type="B_BUY",
                condition_key="BUY:Q,M,W,D",
                original_condition_key="BUY:Q,M,W,D",
                trigger_period="D",
                action_state="blocked",
                confirmation_status="failed",
                action_policy="n5_confirmation_only",
                trace_json={},
                data_quality_status="passed",
                blocked_reason="price_confirmation_failed",
            )

    def test_n5_trigger_fact_guard_accepts_hint_30m_with_empty_formal_periods(self) -> None:
        validate_n5_trigger_fact_passthrough_payload(
            {
                "n4_trigger_event_id": "evt_trigger_source",
                "trigger_price": "43.73",
                "trigger_period": "30m",
                "triggered_periods": [],
                "all_trigger_periods": [],
                "primary_trigger_period": None,
                "trigger_kind": "hint",
                "condition_key": "BUY_HINT",
                "original_condition_key": "BUY_HINT",
                "period_trigger_baseline_trace": {
                    "traced_periods": {},
                    "projection_period": "30m",
                },
                "baseline_source": "projection_30m",
            }
        )

    def test_n5_trigger_fact_guard_rejects_ordinary_trigger_period_30m(self) -> None:
        with self.assertRaisesRegex(EventContractError, "ordinary trigger .*30m"):
            validate_n5_trigger_fact_passthrough_payload(
                {
                    "n4_trigger_event_id": "evt_trigger_source",
                    "trigger_price": "43.73",
                    "trigger_period": "30m",
                    "triggered_periods": [],
                    "all_trigger_periods": [],
                    "primary_trigger_period": None,
                    "trigger_kind": "trigger",
                    "condition_key": "BUY:D",
                    "original_condition_key": "BUY:D",
                    "period_trigger_baseline_trace": {"traced_periods": {}},
                    "baseline_source": "trigger_baseline",
                }
            )

    def test_n5_trigger_fact_guard_rejects_30m_in_formal_period_sets(self) -> None:
        for field in ("triggered_periods", "all_trigger_periods", "primary_trigger_period"):
            with self.subTest(field=field):
                payload = {
                    "n4_trigger_event_id": "evt_trigger_source",
                    "trigger_price": "43.73",
                    "trigger_period": "30m",
                    "triggered_periods": [],
                    "all_trigger_periods": [],
                    "primary_trigger_period": None,
                    "trigger_kind": "hint",
                    "condition_key": "SELL_HINT",
                    "original_condition_key": "SELL_HINT",
                    "period_trigger_baseline_trace": {"traced_periods": {}},
                    "baseline_source": "projection_30m",
                }
                payload[field] = "30m" if field == "primary_trigger_period" else ["30m"]

                with self.assertRaisesRegex(EventContractError, "30m"):
                    validate_n5_trigger_fact_passthrough_payload(payload)

    def test_n5_event_rejects_user_voice_sim_event_prefix(self) -> None:
        with self.assertRaises(EventContractError):
            build_n5_action_event(
                event_type="UserActionEvent",
                asset_kind="stock",
                identity_key="stock:SH:600000",
                trade_date="20260525",
                event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
                action_run_id="action_run_20260525",
                source_trigger_run_id="trigger_run_20260525",
                source_trigger_event_id="evt_trigger_source",
                source_trigger_state_id=201,
                source_trigger_match_id=101,
                source_condition_run_id="condition_run_20260525",
                source_market_trace={"source_event_id": "evt_market_source"},
                direction="buy",
                signal_type="B_BUY",
                condition_key="BUY:D",
                trigger_period="D",
                action_state="eligible",
                confirmation_status="pending",
                action_policy="n5_confirmation_only",
                trace_json={},
                data_quality_status="passed",
            )

    def test_deprecated_hint_event_and_hint_signal_are_rejected(self) -> None:
        with self.assertRaises(EventContractError):
            build_n5_action_event(
                event_type="HintEvent",
                asset_kind="stock",
                identity_key="stock:SH:600001",
                trade_date="20260525",
                event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
                action_run_id="action_run_20260525",
                source_trigger_run_id="trigger_run_20260525",
                source_trigger_event_id="evt_trigger_source",
                source_trigger_state_id=202,
                source_trigger_match_id=102,
                source_condition_run_id="condition_run_20260525",
                source_market_trace={"source_event_id": "evt_market_source"},
                direction="sell",
                signal_type="S_SELL",
                condition_key="SELL_HINT",
                original_condition_key="SELL_HINT",
                trigger_period="30m",
                action_state="eligible",
                confirmation_status="pending",
                action_policy="n5_confirmation_only",
                trace_json={},
                data_quality_status="passed",
            )
        with self.assertRaises(EventContractError):
            build_n5_action_event(
                event_type="ActionEligible",
                asset_kind="stock",
                identity_key="stock:SH:600001",
                trade_date="20260525",
                event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
                action_run_id="action_run_20260525",
                source_trigger_run_id="trigger_run_20260525",
                source_trigger_event_id="evt_trigger_source",
                source_trigger_state_id=202,
                source_trigger_match_id=102,
                source_condition_run_id="condition_run_20260525",
                source_market_trace={"source_event_id": "evt_market_source"},
                direction="sell",
                signal_type="SELL_HINT",
                condition_key="SELL_HINT",
                original_condition_key="SELL_HINT",
                trigger_period="30m",
                action_state="eligible",
                confirmation_status="pending",
                action_policy="n5_confirmation_only",
                trace_json={},
                data_quality_status="passed",
            )

    def test_sell_hint_condition_keeps_canonical_sell_signal(self) -> None:
        event = build_n5_action_event(
            event_type="ActionEligible",
            asset_kind="stock",
            identity_key="stock:SH:600001",
            trade_date="20260525",
            event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
            action_run_id="action_run_20260525",
            source_trigger_run_id="trigger_run_20260525",
            source_trigger_event_id="evt_trigger_source",
            source_trigger_state_id=202,
            source_trigger_match_id=102,
            source_condition_run_id="condition_run_20260525",
            source_market_trace={"source_event_id": "evt_market_source"},
            direction="sell",
            signal_type="S_SELL",
            condition_key="SELL_HINT",
            original_condition_key="SELL_HINT",
            trigger_period="30m",
            action_state="eligible",
            confirmation_status="pending",
            action_policy="n5_confirmation_only",
            trace_json={"candidate_action_mark": "30m_shrink"},
            data_quality_status="passed",
            payload={
                "n4_trigger_event_id": "evt_trigger_source",
                "trigger_price": "43.73",
                "triggered_periods": [],
                "all_trigger_periods": [],
                "primary_trigger_period": None,
                "trigger_kind": "hint",
                "period_trigger_baseline_trace": {
                    "traced_periods": {},
                    "projection_period": "30m",
                },
                "baseline_source": "projection_30m",
            },
        )

        self.assertEqual(event.payload_json["direction"], "sell")
        self.assertEqual(event.payload_json["signal_type"], "S_SELL")
        self.assertEqual(event.payload_json["condition_key"], "SELL_HINT")
        self.assertEqual(event.payload_json["original_condition_key"], "SELL_HINT")
        self.assertIsNone(event.payload_json["action_mark"])


if __name__ == "__main__":
    unittest.main()
