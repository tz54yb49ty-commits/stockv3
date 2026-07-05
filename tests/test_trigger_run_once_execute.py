import unittest

from ashare_v3.trigger.run_once_execute import (
    REQUIRED_TRIGGER_MATCHED_PAYLOAD_KEYS,
    build_output_event_payload,
    build_run_once_dedup_key,
    build_trigger_run_once_rollback_sql,
    find_payload_contract_violations,
    list_disallowed_outbox_event_types,
)
from ashare_v3.trigger.synthetic_dry_run import build_dry_run_plans, build_synthetic_events


class TriggerRunOnceExecuteTest(unittest.TestCase):
    def test_trigger_matched_payload_contains_required_contract_fields(self) -> None:
        event = next(item for item in build_synthetic_events("20260525") if item["event_type"] == "MinuteBarClosed")
        plan = build_dry_run_plans(
            context_rows=[sample_context_row(direction="buy", condition_key="BUY_HINT", allowed_signal_types=["BUY_HINT"])],
            synthetic_events=[event],
        )[0]

        payload = build_output_event_payload(
            trigger_run=sample_trigger_run(),
            plan=plan,
            event=event,
            trigger_state_id=11,
            trigger_match_id=12,
        )

        for key in REQUIRED_TRIGGER_MATCHED_PAYLOAD_KEYS:
            self.assertIn(key, payload)
            self.assertNotIn(payload[key], (None, ""))
        self.assertEqual(payload["signal_type"], "B_BUY")
        self.assertEqual(payload["condition_key"], "BUY_HINT")
        self.assertEqual(payload["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(payload["direction"], "buy")
        self.assertEqual(payload["period_trigger_baseline_trace"]["baseline_version"], "N2-R4-period-trigger-baseline-v1")
        self.assertTrue(payload["period_trigger_baseline_trace"]["present"])

    def test_buy_hint_and_sell_hint_enter_formal_trigger_candidates(self) -> None:
        event = next(item for item in build_synthetic_events("20260525") if item["event_type"] == "MinuteBarClosed")
        plans = build_dry_run_plans(
            context_rows=[
                sample_context_row(direction="buy", condition_key="BUY_HINT", allowed_signal_types=["BUY_HINT"]),
                sample_context_row(direction="sell", condition_key="SELL_HINT", allowed_signal_types=["SELL_HINT"]),
            ],
            synthetic_events=[event],
        )

        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        self.assertEqual({plan["signal_type"] for plan in plans}, {"B_BUY", "S_SELL"})
        self.assertEqual({plan["condition_key"] for plan in plans}, {"BUY_HINT", "SELL_HINT"})
        self.assertFalse(any("action_mark" in plan for plan in plans))

    def test_pending_dedup_key_keeps_delayed_and_missing_distinct(self) -> None:
        events = [
            item
            for item in build_synthetic_events("20260525")
            if item["event_type"] in {"MarketDataDelayed", "MarketDataMissing"}
        ]
        plans = build_dry_run_plans(
            context_rows=[
                sample_context_row(direction="buy", condition_key="BUY:D", allowed_signal_types=["B_BUY"]),
            ],
            synthetic_events=events,
        )

        dedup_keys = {
            build_run_once_dedup_key(event_type=plan["output_event_type"], trade_date="20260525", plan=plan)
            for plan in plans
        }
        self.assertEqual(len(plans), 2)
        self.assertEqual(len(dedup_keys), 2)
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerPendingMarketData"})

    def test_payload_contract_violation_detects_missing_trigger_matched_fields(self) -> None:
        violations = find_payload_contract_violations(
            [
                {
                    "event_type": "TriggerMatched",
                    "payload_json": {
                        "run_id": "trigger_context_snapshot_test",
                        "source_event_id": "synthetic_n3_event",
                    },
                }
            ]
        )

        self.assertEqual(len(violations), 1)
        self.assertIn("trigger_match_id", violations[0]["missing_keys"])
        self.assertIn("context_snapshot_id", violations[0]["missing_keys"])

    def test_disallowed_outbox_event_types_are_rejected_by_allowed_list(self) -> None:
        self.assertEqual(
            list_disallowed_outbox_event_types(["TriggerMatched", "TriggerPendingMarketData"]),
            [],
        )
        self.assertEqual(list_disallowed_outbox_event_types(["TriggerMatched", "ActionEvent"]), ["ActionEvent"])

    def test_rollback_sql_is_scoped_to_n4_5_outputs_only(self) -> None:
        sql = build_trigger_run_once_rollback_sql("trigger_context_snapshot_test")

        self.assertIn("DELETE FROM common_event_outbox", sql)
        self.assertIn("DELETE FROM common_trigger_match", sql)
        self.assertIn("DELETE FROM common_trigger_state", sql)
        self.assertIn("gate_code LIKE 'n4_5_%'", sql)
        self.assertNotIn("DELETE FROM common_trigger_run", sql)
        self.assertNotIn("stock_trigger_context_snapshot", sql)
        self.assertNotIn("common_market_data_run", sql)


def sample_trigger_run() -> dict[str, object]:
    return {
        "run_id": "trigger_context_snapshot_test",
        "source_condition_run_id": "condition_layer_test",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
    }


def sample_context_row(
    *,
    direction: str,
    condition_key: str,
    allowed_signal_types: list[str],
) -> dict[str, object]:
    return {
        "trigger_context_id": 100 + (1 if direction == "buy" else 2),
        "run_id": "trigger_context_snapshot_test",
        "source_condition_run_id": "condition_layer_test",
        "source_condition_pool_id": 101,
        "source_condition_basis_id": 1001,
        "source_minute_target_scope_id": 10001,
        "source_market_subscription_id": None,
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "asset_kind": "stock",
        "identity_key": f"stock:SH:60000{1 if direction == 'buy' else 2}",
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": ["D"] if condition_key.endswith(":D") else [],
        "allowed_signal_types": allowed_signal_types,
        "is_hint_scope": condition_key in {"BUY_HINT", "SELL_HINT"},
        "context_hash": f"context-{direction}-{condition_key}",
        "quality_status": "passed",
        "period_trigger_baseline_json": period_trigger_baseline_json(),
    }


def period_trigger_baseline_json() -> dict[str, object]:
    return {
        "baseline_version": "N2-R4-period-trigger-baseline-v1",
        "baseline_source": "condition_basis",
        "periods": {
            period: {
                "baseline_ready": True,
                "baseline_missing_fields": [],
                "period_key_current": "20260525" if period == "D" else f"current-{period}",
                "period_key_previous": "20260522" if period == "D" else f"previous-{period}",
                "current_open_seed": "10",
                "current_close_seed": "11",
                "current_amount_seed": "200",
                "current_trade_days_seed": 1,
                "previous_open": "12",
                "previous_close": "10",
                "previous_entity_high": "12",
                "previous_entity_low": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "amount_metric": "amount" if period == "D" else "avg_amount",
                "current_window_start": "20260501",
                "current_window_end": "20260522",
                "previous_window_start": "20260401",
                "previous_window_end": "20260430",
            }
            for period in ("Y", "Q", "M", "W", "D")
        },
    }


if __name__ == "__main__":
    unittest.main()
