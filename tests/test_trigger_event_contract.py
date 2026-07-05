import unittest
from datetime import datetime, timezone

from ashare_v3.events.models import EventContractError, EventEnvelope, N4_SOURCE_LAYER, validate_event_envelope
from ashare_v3.events.ids import build_n4_trigger_state_changed_dedup_key
from ashare_v3.trigger.event_factory import build_n4_trigger_event


class TriggerEventContractTest(unittest.TestCase):
    def test_valid_trigger_matched_payload_contains_required_contract_fields(self) -> None:
        event = build_n4_trigger_event(
            event_type="TriggerMatched",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260525",
            event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
            trigger_run_id="trigger_run_20260525",
            source_event_id="evt_n3_source",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY_HINT",
            trigger_mark_candidate="30m_volume",
            trigger_period="30m",
            trigger_bucket="2026-05-25T09:30:00+08:00/2026-05-25T10:00:00+08:00",
            match_basis="intraday_projection",
            data_quality_status="passed",
            payload={"trigger_price": "12.34"},
        )

        self.assertEqual(event.source_layer, "N4_trigger")
        self.assertEqual(event.event_type, "TriggerMatched")
        self.assertEqual(event.partition_key, "stock:SH:600000")
        for key in (
            "run_id",
            "source_event_id",
            "identity_key",
            "asset_kind",
            "direction",
            "condition_key",
            "signal_type",
            "trigger_mark_candidate",
            "trigger_period",
            "match_basis",
            "data_quality_status",
        ):
            self.assertIn(key, event.payload_json)
        self.assertEqual(event.payload_json["direction"], "buy")
        self.assertEqual(event.payload_json["condition_key"], "BUY_HINT")
        self.assertEqual(event.payload_json["signal_type"], "B_BUY")

    def test_n4_event_rejects_non_trigger_event_type(self) -> None:
        with self.assertRaises(EventContractError):
            build_n4_trigger_event(
                event_type="ActionEvent",
                asset_kind="stock",
                identity_key="stock:SH:600000",
                trade_date="20260525",
                event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
                trigger_run_id="trigger_run_20260525",
                source_event_id="evt_n3_source",
                direction="buy",
                signal_type="B_BUY",
                condition_key="BUY:D",
                trigger_mark_candidate="normal",
                trigger_period="D",
                trigger_bucket="trading_day",
                match_basis="realtime_snapshot",
                data_quality_status="passed",
            )

    def test_n4_payload_requires_source_event_and_quality_fields(self) -> None:
        event = EventEnvelope(
            event_id="evt_missing_payload",
            event_type="TriggerPendingMarketData",
            event_schema_version="v1",
            trade_date="20260525",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
            source_layer=N4_SOURCE_LAYER,
            source_run_id="trigger_run_20260525",
            dedup_key="dedup",
            partition_key="stock:SH:600000",
            payload_json={
                "run_id": "trigger_run_20260525",
                "identity_key": "stock:SH:600000",
                "asset_kind": "stock",
                "direction": "buy",
                "condition_key": "BUY:D",
                "signal_type": "B_BUY",
                "trigger_mark_candidate": "normal",
                "trigger_period": "D",
                "match_basis": "realtime_snapshot",
            },
            created_at=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
        )

        with self.assertRaises(EventContractError):
            validate_event_envelope(event)

    def test_sell_hint_keeps_sell_direction(self) -> None:
        event = build_n4_trigger_event(
            event_type="TriggerMatched",
            asset_kind="board",
            identity_key="board:TDX:881001",
            trade_date="20260525",
            event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
            trigger_run_id="trigger_run_20260525",
            source_event_id="evt_n3_source",
            direction="sell",
            signal_type="S_SELL",
            condition_key="SELL_HINT",
            trigger_mark_candidate="30m_shrink",
            trigger_period="30m",
            trigger_bucket="2026-05-25T09:30:00+08:00/2026-05-25T10:00:00+08:00",
            match_basis="intraday_projection",
            data_quality_status="passed",
        )

        self.assertEqual(event.payload_json["direction"], "sell")
        self.assertEqual(event.payload_json["signal_type"], "S_SELL")

    def test_trigger_state_changed_payload_contains_required_state_fields(self) -> None:
        event = build_n4_trigger_event(
            event_type="TriggerStateChanged",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260525",
            event_time=datetime(2026, 5, 25, 1, 45, tzinfo=timezone.utc),
            trigger_run_id="trigger_run_20260525",
            source_event_id="evt_n4_outcome",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY:D",
            trigger_mark_candidate="normal",
            trigger_period="D",
            trigger_bucket="trading_day",
            match_basis="realtime_snapshot",
            data_quality_status="passed",
            payload={
                "trigger_live": True,
                "previous_trigger_live": False,
                "current_status": "matched",
                "previous_status": "inactive",
                "primary_trigger_period": "D",
                "previous_primary_trigger_period": None,
                "all_trigger_periods": ["D"],
                "previous_all_trigger_periods": [],
                "projection_30m_flag": False,
                "projection_30m_type": "none",
                "previous_projection_30m_flag": False,
                "previous_projection_30m_type": "none",
                "previous_trigger_mark_candidate": None,
                "state_change_reason": "activated",
                "source_outcome_event_type": "TriggerMatched",
                "source_outcome_event_id": "evt_n4_matched",
            },
        )

        self.assertEqual(event.event_type, "TriggerStateChanged")
        self.assertTrue(event.payload_json["trigger_live"])
        self.assertEqual(event.payload_json["previous_status"], "inactive")

    def test_trigger_state_changed_dedup_distinguishes_period_upgrade_and_live_false(self) -> None:
        base = {
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "trade_date": "20260525",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": "BUY:D",
            "trigger_bucket": "trading_day",
            "trigger_mark_candidate": "normal",
            "previous_status": "matched",
            "current_status": "matched",
            "previous_trigger_live": True,
            "trigger_live": True,
            "previous_primary_trigger_period": "D",
            "primary_trigger_period": "W",
            "previous_all_trigger_periods": ["D"],
            "all_trigger_periods": ["D", "W"],
            "state_change_reason": "period_upgraded",
            "source_outcome_event_id": "evt_period_upgrade",
        }
        period_upgrade = build_n4_trigger_state_changed_dedup_key(**base)
        live_false = build_n4_trigger_state_changed_dedup_key(
            **{
                **base,
                "current_status": "inactive",
                "trigger_live": False,
                "primary_trigger_period": None,
                "all_trigger_periods": [],
                "state_change_reason": "deactivated",
                "source_outcome_event_id": "evt_live_false",
            }
        )

        self.assertNotEqual(period_upgrade, live_false)


if __name__ == "__main__":
    unittest.main()
