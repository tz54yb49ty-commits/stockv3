import inspect
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from ashare_v3.trigger import action_confirmation_metric_matcher as matcher
from ashare_v3.trigger import action_confirmation_metric_execute as execute
from ashare_v3.trigger.action_confirmation_metric_matcher import (
    ACTION_CONFIRMATION_METRIC_READ_TABLES,
    ALLOWED_ACTION_CONFIRMATION_METRIC_EXECUTE_WRITE_TABLES,
    DEFAULT_FOR_TRADE_DATE,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_SOURCE_CONDITION_RUN_ID,
    DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
    DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
    DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    FORMAL_AMOUNT_PROOF_SCHEMA_VERSION,
    FORBIDDEN_ACTION_CONFIRMATION_METRIC_READ_TABLES,
    HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION,
    REALTIME_VIRTUAL_METRIC_SCHEMA_VERSION,
    TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
    build_action_confirmation_metric_business_execute_contract,
    build_action_confirmation_metric_dry_run_report,
    build_action_confirmation_metric_execute_final_preflight,
    build_action_confirmation_metric_execute_rollback_sql,
    build_action_confirmation_metric_full_day_replay_plans,
    build_action_confirmation_metric_plans,
    build_action_confirmation_metric_preflight_report,
    metric_is_ready,
    metric_lineage_errors,
)


class TriggerActionConfirmationMetricMatcherTest(unittest.TestCase):
    def test_matched_activation_does_not_emit_extra_trigger_state_changed(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[metric_row("stock", "stock:SH:600000", buy_30m_price_pass=True, buy_5m_amount_pass=True)],
        )

        plan = plans[0]
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertTrue(plan["writes_common_trigger_match"])
        self.assertTrue(plan["is_n5_action_entry"])
        self.assertFalse(matcher.plan_has_material_trigger_state_change(plan))
        summary = matcher.summarize_action_confirmation_metric_plans(plans)
        self.assertEqual(summary["state_change_plan_count"], 0)
        self.assertEqual(summary["planned_output_event_types"]["TriggerMatched"], 1)
        self.assertEqual(summary["planned_output_event_types"]["TriggerStateChanged"], 0)

    def test_pending_candidate_is_legacy_no_match_no_n5_and_no_state_changed(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600010", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600010",
                    buy_30m_price_pass=True,
                    buy_5m_amount_pass=True,
                    current_30m_virtual_amount=100,
                    previous_day_same_window_amount=150,
                )
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertFalse(plan["writes_common_trigger_match"])
        self.assertFalse(plan["is_n5_action_entry"])
        self.assertFalse(matcher.plan_has_material_trigger_state_change(plan))
        summary = matcher.summarize_action_confirmation_metric_plans(plans)
        self.assertEqual(summary["planned_output_event_types"]["TriggerPendingMarketData"], 0)
        self.assertEqual(summary["dropped_pending_candidate_count"], 1)

    def test_unchanged_trigger_state_does_not_plan_duplicate_state_changed(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[metric_row("stock", "stock:SH:600000", buy_30m_price_pass=True, buy_5m_amount_pass=True)],
        )
        plan = dict(plans[0])
        plan["previous_trigger_live"] = plan["trigger_live"]
        plan["previous_status"] = plan["current_status"]
        plan["previous_primary_trigger_period"] = plan["primary_trigger_period"]
        plan["previous_all_trigger_periods"] = list(plan["all_trigger_periods"])
        plan["previous_projection_30m_flag"] = plan["projection_30m_flag"]
        plan["previous_projection_30m_type"] = plan["projection_30m_type"]
        plan["previous_trigger_mark_candidate"] = plan["trigger_mark_candidate"]

        self.assertFalse(matcher.plan_has_material_trigger_state_change(plan))
        summary = matcher.summarize_action_confirmation_metric_plans([plan])
        self.assertEqual(summary["state_change_plan_count"], 0)

    def test_full_day_lifecycle_replay_compacts_repeated_matches_and_period_change(self) -> None:
        row = ordinary_buy_context_row("stock:SH:600101", "BUY:M,D")
        metrics = [
            ordinary_buy_metric("stock:SH:600101", metric_id=1, minute_label="09:31", current_price=121, monthly_avg=900),
            ordinary_buy_metric("stock:SH:600101", metric_id=2, minute_label="09:32", current_price=122, monthly_avg=900),
            ordinary_buy_metric("stock:SH:600101", metric_id=3, minute_label="09:33", current_price=123, monthly_avg=1600),
        ]

        plans = build_action_confirmation_metric_full_day_replay_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=metrics,
        )

        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerMatched", "TriggerStateChanged"])
        self.assertEqual(plans[0]["triggered_periods"], ["D"])
        self.assertTrue(plans[0]["writes_common_trigger_match"])
        self.assertEqual(plans[1]["triggered_periods"], ["M", "D"])
        self.assertEqual(plans[1]["state_change_reason"], "trigger_periods_changed")
        self.assertFalse(plans[1]["writes_common_trigger_match"])
        summary = matcher.summarize_action_confirmation_metric_plans(plans)
        self.assertEqual(summary["planned_common_event_outbox"], 2)
        self.assertEqual(summary["planned_common_trigger_state"], 1)

    def test_full_day_lifecycle_replay_ignores_trigger_mark_candidate_only_change(self) -> None:
        row = ordinary_buy_context_row("stock:SH:600105", "BUY:D")
        normal_metric = ordinary_buy_metric("stock:SH:600105", metric_id=1, minute_label="09:31", current_price=121)
        normal_metric["buy_30m_price_pass"] = False
        normal_metric["current_30m_virtual_amount"] = 80
        volume_metric = ordinary_buy_metric("stock:SH:600105", metric_id=2, minute_label="09:32", current_price=122)

        plans = build_action_confirmation_metric_full_day_replay_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[normal_metric, volume_metric],
        )

        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerMatched"])
        self.assertEqual(plans[0]["trigger_mark_candidate"], "normal")
        self.assertEqual(plans[0]["triggered_periods"], ["D"])
        summary = matcher.summarize_action_confirmation_metric_plans(plans)
        self.assertEqual(summary["planned_common_event_outbox"], 1)
        self.assertEqual(summary["planned_output_event_types"]["TriggerStateChanged"], 0)

    def test_full_day_lifecycle_replay_hydrates_heavy_trace_only_for_emitted_events(self) -> None:
        row = ordinary_buy_context_row("stock:SH:600106", "BUY:D")
        metrics = [
            ordinary_buy_metric("stock:SH:600106", metric_id=1, minute_label="09:31", current_price=121),
            ordinary_buy_metric("stock:SH:600106", metric_id=2, minute_label="09:32", current_price=122),
            ordinary_buy_metric("stock:SH:600106", metric_id=3, minute_label="09:33", current_price=123),
        ]

        with patch.object(matcher, "build_metric_trace", wraps=matcher.build_metric_trace) as build_metric_trace:
            plans = build_action_confirmation_metric_full_day_replay_plans(
                trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
                projection_run_id=DEFAULT_PROJECTION_RUN_ID,
                source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
                source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
                source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
                for_trade_date=DEFAULT_FOR_TRADE_DATE,
                context_rows=[row],
                metric_rows=metrics,
            )

        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerMatched"])
        self.assertEqual(build_metric_trace.call_count, len(plans))
        self.assertEqual(plans[0]["metric_trace"]["action_confirmation_metric_id"], 1)

    def test_full_day_lifecycle_replay_emits_inactive_when_ready_metric_no_longer_triggers(self) -> None:
        row = ordinary_buy_context_row("stock:SH:600102", "BUY:D")
        metrics = [
            ordinary_buy_metric("stock:SH:600102", metric_id=1, minute_label="09:31", current_price=121),
            ordinary_buy_metric("stock:SH:600102", metric_id=2, minute_label="09:32", current_price=100),
        ]

        plans = build_action_confirmation_metric_full_day_replay_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=metrics,
        )

        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerMatched", "TriggerStateChanged"])
        self.assertEqual(plans[1]["current_status"], "inactive")
        self.assertFalse(plans[1]["trigger_live"])
        self.assertFalse(plans[1]["writes_common_trigger_match"])
        self.assertEqual(plans[1]["state_change_reason"], "deactivated")

    def test_full_day_lifecycle_replay_drops_missing_metric_without_pending_event(self) -> None:
        plans = build_action_confirmation_metric_full_day_replay_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[ordinary_buy_context_row("stock:SH:600103", "BUY:D")],
            metric_rows=[],
        )

        self.assertEqual(plans, [])

    def test_hint_and_ordinary_lifecycle_keys_can_coexist_for_same_asset(self) -> None:
        rows = [
            ordinary_buy_context_row("stock:SH:600104", "BUY:D"),
            context_row("stock:SH:600104", "buy", "BUY_HINT", ["BUY_HINT"]),
        ]
        metric = ordinary_buy_metric("stock:SH:600104", metric_id=1, minute_label="09:31", current_price=121)
        metric.update(
            {
                "buy_30m_price_pass": True,
                "current_30m_virtual_amount": 220,
                "previous_day_same_window_amount": 100,
            }
        )

        plans = build_action_confirmation_metric_full_day_replay_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=rows,
            metric_rows=[metric],
        )

        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerMatched", "TriggerMatched"])
        self.assertEqual({plan["condition_key"] for plan in plans}, {"BUY:D", "BUY_HINT"})
        summary = matcher.summarize_action_confirmation_metric_plans(plans)
        self.assertEqual(summary["planned_common_trigger_state"], 2)

    def test_ready_buy_metric_generates_would_trigger_with_canonical_payload(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"]),
            ],
            metric_rows=[
                metric_row("stock", "stock:SH:600000", buy_30m_price_pass=True, buy_5m_amount_pass=True),
            ],
        )

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["signal_type"], "B_BUY")
        self.assertEqual(plan["condition_key"], "BUY_HINT")
        self.assertEqual(plan["original_condition_key"], "BUY_HINT")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(plan["projection_30m_type"], "volume_up")
        self.assertTrue(plan["projection_30m_flag"])
        self.assertTrue(plan["trigger_live"])
        self.assertTrue(plan["writes_common_trigger_match"])
        self.assertTrue(plan["is_n5_action_entry"])
        self.assertEqual(plan["triggered_periods"], [])
        self.assertEqual(plan["all_trigger_periods"], [])
        self.assertEqual(plan["formal_triggered_period_details"], [])
        self.assertEqual(plan["trigger_price"], 10.5)
        self.assertEqual(plan["trigger_price_source"], "n3_action_confirmation_metric.current_price")
        self.assertNotIn("action_mark", plan)
        self.assertEqual(plan["source_action_confirmation_metric_id"], 1001)
        self.assertEqual(plan["metric_trace"]["source_snapshot_run_id"], DEFAULT_SOURCE_SNAPSHOT_RUN_ID)

    def test_ready_sell_metric_generates_would_trigger_with_shrink_mark(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[
                context_row("stock:SH:600001", "sell", "SELL_HINT", ["SELL_HINT"]),
            ],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600001",
                    sell_30m_price_pass=True,
                    sell_5m_amount_pass=True,
                    current_30m_virtual_amount=80,
                    previous_day_same_window_amount=100,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["signal_type"], "S_SELL")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_shrink")
        self.assertEqual(plan["projection_30m_type"], "shrink_down")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertEqual(plan["all_trigger_periods"], [])
        self.assertEqual(plan["formal_triggered_period_details"], [])

    def test_buy_hint_uses_previous_day_same_window_amount_not_5m_amount(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600010", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600010",
                    buy_30m_price_pass=True,
                    buy_5m_amount_pass=True,
                    current_30m_virtual_amount=100,
                    previous_day_same_window_amount=150,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["projection_30m_type"], "none")
        self.assertEqual(plan["not_ready_reason"], "metric_ready_but_side_projection_not_satisfied")

    def test_buy_hint_can_trigger_without_5m_amount_when_same_window_volume_passes(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600011", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600011",
                    buy_30m_price_pass=True,
                    buy_5m_amount_pass=False,
                    current_30m_virtual_amount=220,
                    previous_day_same_window_amount=150,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(plan["projection_30m_type"], "volume_up")
        self.assertEqual(plan["metric_trace"]["current_30m_virtual_amount"], 220)
        self.assertEqual(plan["metric_trace"]["previous_day_same_window_amount"], 150)

    def test_buy_hint_can_trigger_without_30m_price_breakthrough_when_same_window_volume_passes(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600015", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600015",
                    buy_30m_price_pass=False,
                    buy_5m_amount_pass=False,
                    current_30m_virtual_amount=220,
                    previous_day_same_window_amount=150,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["projection_30m_type"], "none")
        self.assertEqual(plan["not_ready_reason"], "hint_30m_calibrated_proof_missing_or_invalid")

    def test_buy_hint_blocks_invalid_metric_policy_even_when_amount_and_price_pass(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600017", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600017",
                    buy_30m_price_pass=True,
                    current_30m_virtual_amount=220,
                    previous_day_same_window_amount=150,
                    metric_policy="same_trade_date_previous_30m",
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["not_ready_reason"], "hint_30m_calibrated_proof_missing_or_invalid")
        self.assertEqual(plan["projection_30m_type"], "none")

    def test_buy_hint_requires_metric_policy_proof(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600018", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600018",
                    buy_30m_price_pass=True,
                    current_30m_virtual_amount=220,
                    previous_day_same_window_amount=150,
                    metric_policy=None,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["not_ready_reason"], "hint_30m_calibrated_proof_missing_or_invalid")

    def test_sell_hint_uses_previous_day_same_window_amount_not_5m_amount(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600012", "sell", "SELL_HINT", ["SELL_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600012",
                    sell_30m_price_pass=True,
                    sell_5m_amount_pass=True,
                    current_30m_virtual_amount=160,
                    previous_day_same_window_amount=150,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["projection_30m_type"], "none")
        self.assertEqual(plan["not_ready_reason"], "metric_ready_but_side_projection_not_satisfied")

    def test_sell_hint_can_trigger_without_5m_amount_when_same_window_shrink_passes(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600013", "sell", "SELL_HINT", ["SELL_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600013",
                    sell_30m_price_pass=True,
                    sell_5m_amount_pass=False,
                    current_30m_virtual_amount=90,
                    previous_day_same_window_amount=150,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_shrink")
        self.assertEqual(plan["projection_30m_type"], "shrink_down")

    def test_sell_hint_can_trigger_without_30m_price_breakthrough_when_same_window_shrink_passes(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600016", "sell", "SELL_HINT", ["SELL_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600016",
                    sell_30m_price_pass=False,
                    sell_5m_amount_pass=False,
                    current_30m_virtual_amount=90,
                    previous_day_same_window_amount=150,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["projection_30m_type"], "none")
        self.assertEqual(plan["not_ready_reason"], "hint_30m_calibrated_proof_missing_or_invalid")

    def test_hint_missing_previous_day_same_window_amount_does_not_trigger(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600014", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600014",
                    buy_30m_price_pass=True,
                    buy_5m_amount_pass=True,
                    current_30m_virtual_amount=220,
                    previous_day_same_window_amount=None,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["projection_30m_type"], "none")

    def test_realtime_virtual_metric_schema_is_allowed_without_changing_business_rules(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600000",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            projection_schema_version=REALTIME_VIRTUAL_METRIC_SCHEMA_VERSION,
        )

        self.assertTrue(metric_is_ready(metric))
        self.assertEqual(
            metric_lineage_errors(
                metric,
                projection_run_id=DEFAULT_PROJECTION_RUN_ID,
                source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
                source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
                source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
                for_trade_date=DEFAULT_FOR_TRADE_DATE,
            ),
            [],
        )

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[metric],
        )

        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["signal_type"], "B_BUY")
        self.assertEqual(plans[0]["trigger_mark_candidate"], "30m_volume")

    def test_realtime_virtual_metric_writer_v1_schema_is_allowed(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600000",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            projection_schema_version="v3.realtime_virtual_metric.writer.v1",
        )

        self.assertTrue(metric_is_ready(metric))
        self.assertEqual(
            metric_lineage_errors(
                metric,
                projection_run_id=DEFAULT_PROJECTION_RUN_ID,
                source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
                source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
                source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
                for_trade_date=DEFAULT_FOR_TRADE_DATE,
            ),
            [],
        )

    def test_formal_amount_proof_schema_is_allowed_with_exact_snapshot_scope(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("D")
        metric = metric_row(
            "stock",
            "stock:SH:600039",
            projection_schema_version=FORMAL_AMOUNT_PROOF_SCHEMA_VERSION,
        )
        metric.update(
            {
                "current_price": 121,
                "trace_json": trace,
            }
        )
        row = context_row("stock:SH:600039", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
        )

        self.assertTrue(metric_is_ready(metric))
        self.assertEqual(
            metric_lineage_errors(
                metric,
                projection_run_id=DEFAULT_PROJECTION_RUN_ID,
                source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
                source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
                source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
                for_trade_date=DEFAULT_FOR_TRADE_DATE,
            ),
            [],
        )

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertEqual(plan["projection_schema_version"], FORMAL_AMOUNT_PROOF_SCHEMA_VERSION)

    def test_true_full_day_minute_schema_uses_raw_formal_amount_proof_for_ordinary_buy(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600040",
            projection_schema_version=TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
        )
        metric.update(
            {
                "current_price": 121,
                "today_virt_amount": None,
                "weekly_avg_with_today": None,
                "prev_weekly_avg": None,
                "raw_json": n3_true_full_day_minute_formal_amount_proof_trace("D"),
                "current_d_virtual_amount": 1200,
                "current_w_virtual_amount": 1100,
            }
        )
        row = context_row("stock:SH:600040", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
        )

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["period"], "D")
        self.assertEqual(detail["status"], "triggered")
        self.assertTrue(detail["transition_upgrade_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])
        self.assertTrue(detail["amount_pass"])
        self.assertEqual(detail["trigger_amount_chain_values"]["today_virt_amount"], "1200")
        self.assertEqual(detail["trigger_amount_chain_values"]["weekly_avg_with_today"], "1100")
        self.assertEqual(detail["trigger_amount_chain_values"]["prev_weekly_avg"], "1000")
        self.assertEqual(detail["amount_unit"], "yuan")
        self.assertEqual(detail["amount_rule_proof"], "attachment_dwmqy_avg_chain")
        self.assertEqual(plan["projection_schema_version"], TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION)

    def test_true_full_day_minute_schema_blocks_when_period_amount_field_is_missing(self) -> None:
        raw_json = n3_true_full_day_minute_formal_amount_proof_trace("D")
        period_proof = raw_json["formal_period_amount_proof"]["periods"]["D"]  # type: ignore[index]
        period_proof.pop("current_amount_field")  # type: ignore[union-attr]
        period_proof["source_field_trace"] = {}  # type: ignore[index]
        metric = metric_row(
            "stock",
            "stock:SH:600041",
            projection_schema_version=TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
        )
        metric.update(
            {
                "current_price": 121,
                "raw_json": raw_json,
            }
        )
        row = context_row("stock:SH:600041", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
        )

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["not_ready_reason"], "formal_trigger_period_proof_missing")
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["reason"], "formal_amount_chain_unit_proof_missing_or_invalid")
        self.assertIn("current_amount_field", detail["missing_fields"])
        self.assertIn("current_amount_field_missing", detail["proof_errors"])
        self.assertFalse(plan["writes_common_trigger_match"])
        self.assertFalse(plan["is_n5_action_entry"])

    def test_corrected_historical_replay_schema_allows_multi_snapshot_scope(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600000",
            buy_30m_price_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=150,
            projection_schema_version=HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION,
        )
        metric["source_snapshot_run_id"] = "previous_day_minute_preload_20260616_for_20260617"
        metric["source_today_minute_run_id"] = "historical_closed_minute_source_expansion_20260616_until_1401"
        metric["source_previous_day_minute_run_id"] = "previous_day_minute_preload_20260615_for_20260616"

        self.assertTrue(metric_is_ready(metric))
        self.assertEqual(
            metric_lineage_errors(
                metric,
                projection_run_id=DEFAULT_PROJECTION_RUN_ID,
                source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
                source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
                source_snapshot_run_id="historical_closed_minute_source_expansion_20260616_until_1401",
                for_trade_date=DEFAULT_FOR_TRADE_DATE,
            ),
            [],
        )

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id="historical_closed_minute_source_expansion_20260616_until_1401",
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["projection_schema_version"], HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION)
        self.assertEqual(plan["metric_trace"]["source_snapshot_run_id"], "previous_day_minute_preload_20260616_for_20260617")
        self.assertEqual(
            plan["metric_trace"]["historical_closed_minute_source_run_id"],
            "historical_closed_minute_source_expansion_20260616_until_1401",
        )
        self.assertFalse(plan["metric_trace"]["fake_realtime_snapshot"])
        self.assertFalse(plan["metric_trace"]["stale_v1_b1_c1_reused"])

    def test_non_historical_schema_still_requires_exact_source_snapshot(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600000",
            buy_30m_price_pass=True,
            projection_schema_version=REALTIME_VIRTUAL_METRIC_SCHEMA_VERSION,
        )
        metric["source_snapshot_run_id"] = "wrong_snapshot"

        self.assertEqual(
            metric_lineage_errors(
                metric,
                projection_run_id=DEFAULT_PROJECTION_RUN_ID,
                source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
                source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
                source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
                for_trade_date=DEFAULT_FOR_TRADE_DATE,
            ),
            ["source_snapshot_run_id"],
        )

    def test_historical_replay_fetch_does_not_truncate_to_single_snapshot(self) -> None:
        source = inspect.getsource(matcher.fetch_action_confirmation_metric_rows)
        self.assertIn("OR projection_schema_version = %s", source)
        self.assertIn("HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION", source)

    def test_true_full_day_metric_fetch_uses_minimal_json_projection(self) -> None:
        sql = matcher.true_full_day_minimal_metric_select_sql("stock_action_confirmation_projection_metric")

        self.assertIn("formal_amount_chain_metrics", sql)
        self.assertIn("full_scope_condition_rows", sql)
        self.assertIn("NULL::jsonb AS source_fact_ids", sql)
        self.assertIn("NULL::jsonb AS source_minute_refs", sql)
        self.assertIn("NULL::jsonb AS previous_day_minute_refs", sql)
        self.assertIn("NULL::jsonb AS formal_period_amount_proof", sql)
        self.assertIn("NULL::jsonb AS formal_amount_chain_metrics", sql)
        self.assertIn("today_virt_amount", sql)
        self.assertIn("weekly_avg_with_today", sql)
        self.assertNotIn("\n                       source_fact_ids,", sql)
        self.assertNotIn("\n                       source_minute_refs,", sql)
        self.assertNotIn("\n                       previous_day_minute_refs,", sql)
        self.assertNotIn("\n                       raw_json,", sql)
        self.assertNotIn("\n                       trace_json,", sql)
        self.assertNotIn("jsonb_build_object", sql)
        self.assertNotIn("previous_120m_body_high", sql)
        self.assertNotIn("current_5m_virtual_amount", sql)
        self.assertNotIn("current_d_body_high", sql)

    def test_true_full_day_formal_gate_uses_schema_proof_without_heavy_proof_json(self) -> None:
        amount_values = {
            "today_virt_amount": 1200,
            "weekly_avg_with_today": 1100,
            "prev_weekly_avg": 1000,
        }
        metric = metric_row(
            "stock",
            "stock:SH:600FD1",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
            projection_schema_version=TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
        )
        metric.update(
            {
                "current_price": 121,
                "formal_amount_chain_metrics": amount_values,
                "formal_period_amount_proof": {},
                "raw_json": {},
                "trace_json": {},
                "today_virt_amount": 1200,
                "weekly_avg_with_today": 1100,
                "prev_weekly_avg": 1000,
            }
        )
        row = context_row("stock:SH:600FD1", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
        )
        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )
        plan = plan[0]

        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["trigger_amount_chain_status"], "passed")
        self.assertEqual(detail["unit_conversion_policy"], "true_full_day_minute_series_yuan_passthrough_v1")

    def test_quality_items_accept_streaming_metric_summary_counts(self) -> None:
        items = matcher.build_action_confirmation_metric_quality_items(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            trigger_run={"run_id": DEFAULT_TRIGGER_CONTEXT_RUN_ID, "status": "passed"},
            context_rows=[context_row("stock:SH:600FD2", "buy", "BUY:D", ["B_BUY"])],
            metric_rows=[],
            plans=[],
            summary={
                "metric_row_count": 491760,
                "metric_lineage_mismatch_count": 0,
                "planned_common_event_outbox": 1,
                "planned_common_trigger_state": 1,
                "opaque_action_confirmation_payload_count": 0,
                "quality_stream_counts": {
                    "matched_unready_count": 0,
                    "invalid_canonical_payload_count": 0,
                    "year_auto_amount_operator_count": 0,
                    "ordinary_formal_count": 1,
                    "ordinary_formal_matched_count": 1,
                    "ordinary_formal_proof_missing_count": 0,
                    "legacy_runtime_signals": [],
                },
            },
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        by_code = {item["gate_code"]: item for item in items}
        self.assertEqual(by_code["n4_action_confirmation_metric_rows_available"]["status"], "passed")
        self.assertEqual(by_code["n4_action_confirmation_metric_rows_available"]["actual_value"], "491760")
        self.assertEqual(by_code["n4_action_confirmation_metric_lineage_allowlist"]["status"], "passed")

    def test_hint_scoped_metric_does_not_drive_ordinary_context(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600000",
            buy_30m_price_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=150,
            projection_schema_version=HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION,
        )
        metric["raw_json"] = {"condition_key": "BUY_HINT", "signal_type": "B_BUY"}

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY:D", ["B_BUY"])],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["not_ready_reason"], "metric_scope_not_compatible_with_context_condition")
        self.assertFalse(plan["writes_common_trigger_match"])
        self.assertFalse(plan["is_n5_action_entry"])

    def test_buy_hint_uses_full_scope_condition_rows_for_context_specific_match(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600030",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=False,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=150,
        )
        metric["raw_json"] = {
            "condition_key": "BUY:Q,M,D",
            "signal_type": "B_BUY",
            "full_scope_condition_rows": [
                full_scope_condition_row("BUY:Q,M,D", "buy", "B_BUY", ["BUY"], is_hint_scope=False),
                full_scope_condition_row("BUY_HINT", "buy", "B_BUY", ["BUY_HINT"], is_hint_scope=True),
            ],
        }

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600030", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["signal_type"], "B_BUY")
        self.assertEqual(plan["condition_key"], "BUY_HINT")
        self.assertEqual(plan["original_condition_key"], "BUY_HINT")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_volume")
        self.assertNotIn("action_mark", plan)

    def test_sell_hint_uses_full_scope_condition_rows_for_context_specific_match(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600031",
            sell_30m_price_pass=True,
            sell_5m_amount_pass=False,
            current_30m_virtual_amount=90,
            previous_day_same_window_amount=150,
        )
        metric["raw_json"] = {
            "condition_key": "SELL:Y,Q,W,D",
            "signal_type": "S_SELL",
            "full_scope_condition_rows": [
                full_scope_condition_row("SELL:Y,Q,W,D", "sell", "S_SELL", ["SELL"], is_hint_scope=False),
                full_scope_condition_row("SELL_HINT", "sell", "S_SELL", ["SELL_HINT"], is_hint_scope=True),
            ],
        }

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600031", "sell", "SELL_HINT", ["SELL_HINT"])],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["signal_type"], "S_SELL")
        self.assertEqual(plan["condition_key"], "SELL_HINT")
        self.assertEqual(plan["original_condition_key"], "SELL_HINT")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_shrink")
        self.assertNotIn("action_mark", plan)

    def test_full_scope_hint_rows_do_not_block_ordinary_buy_sell_full_paths(self) -> None:
        rows = [
            context_row("stock:SH:600032", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"]),
            context_row("stock:SH:600033", "sell", "SELL:D", ["S_SELL", "S_SELL_30M_SHRINK"]),
            context_row("stock:SH:600034", "buy", "BUY:FULL", ["B_BUY", "B_BUY_30M_VOL"]),
            context_row("stock:SH:600035", "sell", "SELL:FULL", ["S_SELL", "S_SELL_30M_SHRINK"]),
        ]
        metrics = []
        for row in rows:
            direction = str(row["direction"])
            trace_json = n3_standard_formal_amount_proof_trace("D")
            if direction == "sell":
                chain = trace_json["formal_period_amount_proof"]["amount_chain_metrics"]  # type: ignore[index]
                chain["today_virt_amount"] = 800  # type: ignore[index]
                chain["weekly_avg_with_today"] = 900  # type: ignore[index]
                chain["prev_weekly_avg"] = 1000  # type: ignore[index]
            metric = metric_row(
                "stock",
                str(row["identity_key"]),
                buy_30m_price_pass=direction == "buy",
                sell_30m_price_pass=direction == "sell",
                current_30m_virtual_amount=220 if direction == "buy" else 90,
                previous_day_same_window_amount=150,
            )
            metric.update(
                {
                    "current_price": 121 if direction == "buy" else 107,
                    "today_virt_amount": 1200 if direction == "buy" else 800,
                    "weekly_avg_with_today": 1100 if direction == "buy" else 900,
                    "prev_weekly_avg": 1000,
                    "trace_json": trace_json,
                    "raw_json": {
                        "condition_key": "BUY:Q,M,D" if direction == "buy" else "SELL:Y,Q,W,D",
                        "signal_type": "B_BUY" if direction == "buy" else "S_SELL",
                        "full_scope_condition_rows": [
                            full_scope_condition_row(
                                "BUY_HINT" if direction == "buy" else "SELL_HINT",
                                direction,
                                "B_BUY" if direction == "buy" else "S_SELL",
                                ["BUY_HINT"] if direction == "buy" else ["SELL_HINT"],
                                is_hint_scope=True,
                            )
                        ],
                    },
                }
            )
            row["period_trigger_baseline_json"] = formal_baseline(
                "D",
                trigger_previous_entity_high=117,
                trigger_previous_entity_low=108.55,
            )
            metrics.append(metric)

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=rows,
            metric_rows=metrics,
        )

        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerMatched"] * 4)
        self.assertEqual([plan["condition_key"] for plan in plans], ["BUY:D", "SELL:D", "BUY:FULL", "SELL:FULL"])
        self.assertEqual([plan["signal_type"] for plan in plans], ["B_BUY", "S_SELL", "B_BUY", "S_SELL"])

    def test_pending_market_data_from_full_scope_hint_does_not_write_match_or_n5_entry(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600036",
            buy_30m_price_pass=True,
            current_30m_virtual_amount=100,
            previous_day_same_window_amount=150,
        )
        metric["raw_json"] = {
            "condition_key": "BUY:Q,M,D",
            "signal_type": "B_BUY",
            "full_scope_condition_rows": [
                full_scope_condition_row("BUY_HINT", "buy", "B_BUY", ["BUY_HINT"], is_hint_scope=True),
            ],
        }

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:600036", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["not_ready_reason"], "metric_ready_but_side_projection_not_satisfied")
        self.assertFalse(plan["trigger_live"])
        self.assertFalse(plan["writes_common_trigger_match"])
        self.assertFalse(plan["is_n5_action_entry"])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_ready_metric_without_side_marker_evidence_stays_pending(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[
                context_row("stock:SH:600002", "buy", "BUY:D", ["B_BUY_30M_VOL"]),
            ],
            metric_rows=[
                metric_row("stock", "stock:SH:600002", buy_30m_price_pass=False, buy_5m_amount_pass=True),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["signal_type"], "B_BUY")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_volume")
        self.assertFalse(plan["trigger_live"])
        self.assertEqual(plan["current_status"], "pending_market_data")
        self.assertEqual(plan["not_ready_reason"], "metric_ready_but_side_projection_not_satisfied")

    def test_ordinary_buy_metric_without_formal_proof_stays_pending(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[
                context_row("stock:SH:600020", "buy", "BUY:Y,Q,M,W,D", ["B_BUY", "B_BUY_30M_VOL"]),
            ],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600020",
                    buy_30m_price_pass=False,
                    buy_5m_amount_pass=True,
                    current_30m_virtual_amount=80,
                    previous_day_same_window_amount=100,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["signal_type"], "B_BUY")
        self.assertEqual(plan["trigger_mark_candidate"], "normal")
        self.assertEqual(plan["projection_30m_type"], "none")
        self.assertEqual(plan["not_ready_reason"], "formal_trigger_period_proof_missing")
        self.assertEqual(plan["trigger_period"], "Y")
        self.assertIsNone(plan["primary_trigger_period"])
        self.assertEqual(plan["all_trigger_periods"], [])
        self.assertEqual(plan["triggered_periods"], [])
        self.assertFalse(plan["n5_entry_allowed"])
        self.assertFalse(plan["writes_common_trigger_match"])
        self.assertFalse(plan["is_n5_action_entry"])

    def test_ordinary_buy_metric_with_explicit_formal_proof_triggers_non_30m_period(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600121",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric["raw_json"] = {
            "n4_formal_trigger_period_proof": {
                "source": "rule_v4_matcher",
                "triggered_periods": ["D"],
                "triggered_period_details": [{"period": "D", "basis": "trigger_previous_baseline"}],
            }
        }
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[
                context_row("stock:SH:600121", "buy", "BUY:M,W,D", ["B_BUY", "B_BUY_30M_VOL"]),
            ],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["trigger_period"], "D")
        self.assertEqual(plan["primary_trigger_period"], "D")
        self.assertEqual(plan["all_trigger_periods"], ["D"])
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertEqual(plan["formal_trigger_period_proof_status"], "passed")
        self.assertNotIn("30m", plan["all_trigger_periods"])

    def test_ordinary_buy_builds_formal_proof_from_n2_trigger_baseline_and_n3_period_metric(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600123",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric.update(
            {
                "current_price": 121,
                "current_d_body_high": 121,
                "current_d_body_low": 115,
                "current_d_virtual_amount": 3_200_000,
                "trace_json": n3_standard_formal_amount_proof_trace("D"),
            }
        )
        row = context_row("stock:SH:600123", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            trigger_previous_amount_baseline=2_948_974.34197,
        )
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertEqual(plan["all_trigger_periods"], ["D"])
        self.assertEqual(plan["primary_trigger_period"], "D")
        self.assertEqual(plan["formal_trigger_period_proof_status"], "passed")
        details = plan["formal_triggered_period_details"]
        self.assertEqual(details[0]["period"], "D")
        self.assertEqual(details[0]["baseline_entity_high_field"], "trigger_previous_entity_high")
        self.assertEqual(details[0]["current_price_field"], "current_price")
        self.assertEqual(details[0]["amount_rule"], "attachment_dwmqy_avg_chain")
        self.assertEqual(details[0]["current_amount_source_kind"], "N3_standard_period_metric")
        self.assertEqual(details[0]["amount_unit"], "yuan")
        self.assertEqual(details[0]["transition_amount_fields"], ["today_virt_amount", "n2_previous_amount_yuan"])
        self.assertEqual(details[0]["transition_previous_amount_trace"]["source_field"], "previous_avg_amount")

    def test_formal_amount_proof_aliases_fill_trace_without_changing_decision(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("D", "W", "M", "Q", "Y")
        trace["formal_period_amount_proof"]["amount_chain_metrics"] = {}  # type: ignore[index]
        metric = metric_row("stock", "stock:SH:600123")
        for field in (
            "today_virt_amount",
            "weekly_avg_with_today",
            "monthly_avg_with_today",
            "quarterly_avg_with_today",
            "yearly_avg_with_today",
            "prev_weekly_avg",
            "prev_monthly_avg",
            "prev_quarterly_avg",
            "prev_yearly_avg",
        ):
            metric.pop(field, None)
        metric.update(
            {
                "current_price": 121,
                "current_d_virtual_amount": 1200,
                "current_w_virtual_amount": 1100,
                "current_m_virtual_amount": 1000,
                "current_q_virtual_amount": 900,
                "current_y_virtual_amount": 800,
                "trace_json": trace,
            }
        )

        cases = [
            ("D", {"today_virt_amount": ("1200", "current_d_virtual_amount"), "weekly_avg_with_today": ("1100", "current_w_virtual_amount")}),
            ("W", {"weekly_avg_with_today": ("1100", "current_w_virtual_amount"), "monthly_avg_with_today": ("1000", "current_m_virtual_amount")}),
            ("M", {"monthly_avg_with_today": ("1000", "current_m_virtual_amount"), "quarterly_avg_with_today": ("900", "current_q_virtual_amount")}),
            ("Q", {"quarterly_avg_with_today": ("900", "current_q_virtual_amount"), "yearly_avg_with_today": ("800", "current_y_virtual_amount")}),
        ]
        for period, expected in cases:
            with self.subTest(period=period):
                amount_chain = matcher.evaluate_formal_amount_chain(metric=metric, period=period, direction="buy")
                self.assertEqual(amount_chain["status"], "missing")
                self.assertFalse(amount_chain["amount_pass"])
                for field, (value, source) in expected.items():
                    self.assertEqual(amount_chain["amount_chain_values"][field], value)
                    self.assertEqual(amount_chain["amount_chain_value_sources"][field], source)
                    self.assertEqual(amount_chain["amount_chain_alias_values"][field], value)
                    self.assertEqual(amount_chain["amount_chain_alias_value_sources"][field], source)

        baseline = formal_baseline("Y", previous_avg_amount=700)
        y_gate = matcher.evaluate_formal_transition_gate(
            row=context_row("stock:SH:600123", "buy", "BUY:Y", ["B_BUY"]),
            baseline=baseline["periods"]["Y"],  # type: ignore[index]
            metric=metric,
            amount_proof=matcher.n3_formal_amount_proof_for_period(metric, "Y"),
            period="Y",
            direction="buy",
            current_price=matcher.decimal_or_none(121),
            previous_high=matcher.decimal_or_none(117),
            previous_low=matcher.decimal_or_none(108.55),
        )
        self.assertEqual(y_gate["status"], "missing")
        self.assertFalse(y_gate["transition_amount_pass"])
        self.assertIn("yearly_avg_with_today", y_gate["missing_fields"])
        self.assertEqual(y_gate["transition_amount_values"]["yearly_avg_with_today"], "800")
        self.assertEqual(y_gate["transition_amount_value_sources"]["yearly_avg_with_today"], "current_y_virtual_amount")
        self.assertEqual(y_gate["transition_amount_alias_values"]["yearly_avg_with_today"], "800")
        self.assertEqual(y_gate["transition_amount_alias_value_sources"]["yearly_avg_with_today"], "current_y_virtual_amount")

    def test_formal_amount_proof_aliases_do_not_override_canonical_values(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("D")
        metric = metric_row("stock", "stock:SH:600124")
        metric.update(
            {
                "today_virt_amount": 1200,
                "weekly_avg_with_today": 1100,
                "prev_weekly_avg": 1000,
                "current_d_virtual_amount": 1,
                "current_w_virtual_amount": 2,
                "trace_json": trace,
            }
        )

        amount_chain = matcher.evaluate_formal_amount_chain(metric=metric, period="D", direction="buy")

        self.assertEqual(amount_chain["status"], "passed")
        self.assertTrue(amount_chain["amount_pass"])
        self.assertEqual(amount_chain["amount_chain_values"]["today_virt_amount"], "1200")
        self.assertEqual(amount_chain["amount_chain_values"]["weekly_avg_with_today"], "1100")
        self.assertEqual(amount_chain["amount_chain_value_sources"]["today_virt_amount"], "today_virt_amount")
        self.assertEqual(amount_chain["amount_chain_value_sources"]["weekly_avg_with_today"], "weekly_avg_with_today")
        self.assertEqual(amount_chain["amount_chain_alias_values"]["today_virt_amount"], "1")
        self.assertEqual(amount_chain["amount_chain_alias_values"]["weekly_avg_with_today"], "2")
        self.assertEqual(amount_chain["amount_chain_alias_value_sources"]["today_virt_amount"], "current_d_virtual_amount")
        self.assertEqual(
            amount_chain["amount_chain_alias_value_sources"]["weekly_avg_with_today"],
            "current_w_virtual_amount",
        )

    def test_ordinary_buy_uses_trigger_previous_entity_high_not_classification_high(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600124",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric.update(
            {
                "current_price": 113.15,
                "current_d_body_high": 113.15,
                "current_d_body_low": 110,
                "current_d_virtual_amount": 3_200_000,
                "trace_json": n3_standard_formal_amount_proof_trace("D"),
            }
        )
        row = context_row("stock:SH:600124", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            previous_entity_high=110.1,
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            previous_amount_baseline=1_903_711,
            trigger_previous_amount_baseline=2_948_974.34197,
        )
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["not_ready_reason"], "metric_ready_but_formal_trigger_not_satisfied")
        self.assertEqual(plan["formal_trigger_period_proof_status"], "empty")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertNotIn("D", plan["all_trigger_periods"])

    def test_d_transition_uses_n2_previous_amount_and_ignores_polluted_trigger_amount(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("M", "W", "D")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        amount_values = {
            "today_virt_amount": 2222464879.640873,
            "weekly_avg_with_today": 2034987963.0636244,
            "prev_weekly_avg": 2011713272.5500002,
            "monthly_avg_with_today": 1857514491.2569902,
            "prev_monthly_avg": 1843735462.8966668,
            "quarterly_avg_with_today": 1651204933.9323244,
            "prev_quarterly_avg": 1362073966.0535712,
        }
        chain.update(amount_values)
        metric = metric_row(
            "stock",
            "stock:SZ:301611",
            buy_30m_price_pass=False,
            buy_5m_amount_pass=False,
            current_30m_virtual_amount=411018224.773762,
            previous_day_same_window_amount=627302190,
        )
        metric.update({"current_price": 119.69, "trace_json": trace, **amount_values})
        row = context_row("stock:SZ:301611", "buy", "BUY:M,W,D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = {
            "baseline_version": "test",
            "periods": {
                "M": {
                    "trigger_previous_entity_high": 108.08150139386699,
                    "trigger_previous_entity_low": 92.43865193150139,
                    "previous_transition": "low_volume_up",
                    "previous_avg_amount": 1843735.4628966667,
                },
                "W": {
                    "trigger_previous_entity_high": 108.55,
                    "trigger_previous_entity_low": 105.86,
                    "previous_transition": "low_volume_up",
                    "previous_avg_amount": 2011713.27255,
                },
                "D": {
                    "trigger_previous_entity_high": 114.66,
                    "trigger_previous_entity_low": 114.21,
                    "previous_transition": "low_volume_down",
                    "previous_avg_amount": 2120832.26927,
                    "previous_amount": 2120832.26927,
                    "classification_previous_amount_baseline": 2120832.26927,
                    "trigger_previous_amount_baseline": 1761666.74028,
                    "current_amount_seed": 1761666.74028,
                    "current_avg_amount_seed": 1761666.74028,
                    "current_amount_total_seed": 1761666.74028,
                },
            },
        }

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["triggered_periods"], ["M", "W", "D"])
        self.assertEqual(plan["primary_trigger_period"], "M")
        by_period = {detail["period"]: detail for detail in plan["formal_triggered_period_details"]}
        self.assertEqual(by_period["D"]["status"], "triggered")
        self.assertEqual(by_period["D"]["transition_amount_values"]["today_virt_amount"], "2222464879.640873")
        self.assertEqual(by_period["D"]["transition_amount_values"]["n2_previous_amount_yuan"], "2120832269.27000")
        self.assertEqual(by_period["D"]["transition_previous_amount_trace"]["source_field"], "previous_avg_amount")
        self.assertIn("trigger_previous_amount_baseline", by_period["D"]["transition_previous_amount_trace"]["forbidden_fields_ignored"])
        self.assertTrue(by_period["D"]["transition_amount_pass"])
        self.assertTrue(by_period["D"]["transition_upgrade_pass"])
        self.assertTrue(by_period["D"]["trigger_amount_chain_pass"])
        self.assertTrue(by_period["D"]["amount_pass"])

    def test_formal_amount_proof_v1_uses_period_virtual_average_chain(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SZ:301611",
            buy_30m_price_pass=False,
            buy_5m_amount_pass=False,
            projection_schema_version=FORMAL_AMOUNT_PROOF_SCHEMA_VERSION,
        )
        metric.update(
            {
                "current_price": 119.69,
                "today_virt_amount": None,
                "weekly_avg_with_today": None,
                "prev_weekly_avg": None,
                "monthly_avg_with_today": None,
                "prev_monthly_avg": None,
                "quarterly_avg_with_today": None,
                "prev_quarterly_avg": None,
                "yearly_avg_with_today": None,
                "prev_yearly_avg": None,
                "current_d_virtual_amount": 2579285447.75,
                "current_w_virtual_amount": 10769640762.166666,
                "current_m_virtual_amount": 33929320090.776923,
                "trace_json": n3_formal_amount_proof_v1_trace(
                    {
                        "D": {
                            "current_virtual_amount": 2579285447.75,
                            "total_units": 1,
                            "previous_avg_amount": 1761666740.28,
                        },
                        "W": {
                            "current_virtual_amount": 10769640762.166666,
                            "total_units": 5,
                            "previous_avg_amount": 2011713272.55,
                        },
                        "M": {
                            "current_virtual_amount": 33929320090.776923,
                            "total_units": 18,
                            "previous_avg_amount": 1843735462.8966668,
                        },
                        "Q": {
                            "current_virtual_amount": 92851744604.327692,
                            "total_units": 56,
                            "previous_avg_amount": 1362073966.0535712,
                        },
                        "Y": {
                            "current_virtual_amount": 365615143271.0775,
                            "total_units": 243,
                            "previous_avg_amount": 348202776.436214,
                        },
                    }
                ),
            }
        )
        row = context_row("stock:SZ:301611", "buy", "BUY:M,W,D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = {
            "baseline_version": "test",
            "periods": {
                "M": {
                    "trigger_previous_entity_high": 108.08150139386699,
                    "trigger_previous_entity_low": 92.43865193150139,
                    "previous_transition": "low_volume_up",
                    "previous_avg_amount": 1843735.4628966667,
                },
                "W": {
                    "trigger_previous_entity_high": 108.55,
                    "trigger_previous_entity_low": 105.86,
                    "previous_transition": "low_volume_up",
                    "previous_avg_amount": 2011713.27255,
                },
                "D": {
                    "trigger_previous_entity_high": 114.66,
                    "trigger_previous_entity_low": 114.21,
                    "previous_transition": "low_volume_down",
                    "previous_avg_amount": 2120832.26927,
                    "trigger_previous_amount_baseline": 1761666.74028,
                    "current_amount_seed": 1761666.74028,
                },
            },
        }

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["triggered_periods"], ["M", "W", "D"])
        self.assertEqual(plan["primary_trigger_period"], "M")
        by_period = {detail["period"]: detail for detail in plan["formal_triggered_period_details"]}
        self.assertEqual(by_period["D"]["amount_chain_values"]["weekly_avg_with_today"], "2153928152.4333332")
        self.assertEqual(by_period["D"]["amount_chain_values"]["prev_weekly_avg"], "2011713272.55")
        self.assertTrue(by_period["D"]["amount_rule_implicit_by_schema"])
        self.assertEqual(
            by_period["D"]["unit_conversion_policy"],
            "stock_thousand_yuan_to_yuan_else_native_yuan_v1",
        )

    def test_n2_baseline_transition_amount_unit_uses_asset_kind_rules(self) -> None:
        cases = [
            (
                "stock",
                "stock:SH:600004",
                298615.373,
                419986101,
                "thousand_yuan",
                1000,
                "298615373.000",
            ),
            (
                "index",
                "index:SH:000001",
                1560474025984,
                1704000417536,
                "yuan",
                1,
                "1560474025984",
            ),
            (
                "board",
                "board:TDX:881002",
                11794216960,
                25650024144,
                "yuan",
                1,
                "11794216960",
            ),
        ]
        for asset_kind, identity_key, previous_amount, current_amount, expected_unit, expected_factor, expected_yuan in cases:
            with self.subTest(asset_kind=asset_kind):
                metric = metric_row(
                    asset_kind,
                    identity_key,
                    buy_30m_price_pass=True,
                    buy_5m_amount_pass=True,
                    current_30m_virtual_amount=220,
                    previous_day_same_window_amount=100,
                )
                trace = n3_standard_formal_amount_proof_trace("D")
                trace["formal_period_amount_proof"]["amount_chain_metrics"].update(  # type: ignore[index]
                    {
                        "today_virt_amount": current_amount,
                        "weekly_avg_with_today": current_amount,
                        "prev_weekly_avg": previous_amount,
                    }
                )
                metric.update(
                    {
                        "current_price": 121,
                        "today_virt_amount": current_amount,
                        "weekly_avg_with_today": current_amount,
                        "prev_weekly_avg": previous_amount,
                        "current_d_virtual_amount": current_amount,
                        "trace_json": trace,
                    }
                )
                row = context_row(identity_key, "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
                row["period_trigger_baseline_json"] = formal_baseline(
                    "D",
                    trigger_previous_entity_high=117,
                    trigger_previous_entity_low=108.55,
                    previous_transition="flat",
                    previous_avg_amount=previous_amount,
                    previous_amount=previous_amount,
                )

                plan = build_action_confirmation_metric_plans(
                    trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
                    projection_run_id=DEFAULT_PROJECTION_RUN_ID,
                    source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
                    source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
                    source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
                    for_trade_date=DEFAULT_FOR_TRADE_DATE,
                    context_rows=[row],
                    metric_rows=[metric],
                )[0]

                detail = {item["period"]: item for item in plan["formal_triggered_period_details"]}["D"]
                amount_trace = detail["transition_previous_amount_trace"]

                self.assertEqual(detail["transition_amount_values"]["n2_previous_amount_yuan"], expected_yuan)
                self.assertTrue(detail["transition_amount_pass"])
                self.assertEqual(detail["current_transition"], "volume_up")
                self.assertEqual(amount_trace["n2_baseline_source_amount_unit"], expected_unit)
                self.assertEqual(amount_trace["n2_baseline_canonical_amount_unit"], "yuan")
                self.assertEqual(amount_trace["n2_baseline_unit_conversion_factor"], expected_factor)
                self.assertEqual(amount_trace["n2_baseline_amount_unit_source"], "explicit_asset_kind_rule")

    def test_n2_baseline_transition_amount_unit_does_not_double_convert_index(self) -> None:
        metric = metric_row(
            "index",
            "index:SH:000001",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        trace = n3_standard_formal_amount_proof_trace("D")
        trace["formal_period_amount_proof"]["amount_chain_metrics"].update(  # type: ignore[index]
            {
                "today_virt_amount": 1704000417536,
                "weekly_avg_with_today": 1704000417536,
                "prev_weekly_avg": 1560474025984,
            }
        )
        metric.update(
            {
                "current_price": 121,
                "today_virt_amount": 1704000417536,
                "weekly_avg_with_today": 1704000417536,
                "prev_weekly_avg": 1560474025984,
                "current_d_virtual_amount": 1704000417536,
                "trace_json": trace,
            }
        )
        row = context_row("index:SH:000001", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            previous_transition="flat",
            previous_avg_amount=1560474025984,
        )

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        detail = {item["period"]: item for item in plan["formal_triggered_period_details"]}["D"]
        self.assertEqual(detail["transition_amount_values"]["n2_previous_amount_yuan"], "1560474025984")
        self.assertNotEqual(detail["transition_amount_values"]["n2_previous_amount_yuan"], "1560474025984000")

    def test_ordinary_buy_uses_current_price_not_current_period_body_high(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600126",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric.update(
            {
                "current_price": 121,
                "current_d_body_high": 110,
                "current_d_body_low": 105,
                "current_d_virtual_amount": 1,
                "trace_json": n3_standard_formal_amount_proof_trace("D"),
            }
        )
        row = context_row("stock:SH:600126", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            trigger_previous_amount_baseline=999999999,
        )

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["triggered_periods"], ["D"])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["current_price"], "121")
        self.assertEqual(detail["current_body_high"], "110")
        self.assertTrue(detail["price_pass"])

    def test_ordinary_buy_amount_chain_replaces_trigger_previous_amount_baseline(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600127",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric.update(
            {
                "current_price": 121,
                "current_d_virtual_amount": 1,
                "trace_json": n3_standard_formal_amount_proof_trace("D"),
            }
        )
        row = context_row("stock:SH:600127", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            trigger_previous_amount_baseline=999999999,
        )

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["amount_rule"], "attachment_dwmqy_avg_chain")
        self.assertEqual(detail["trigger_previous_amount_baseline"], "999999999")
        self.assertTrue(detail["amount_pass"])

    def test_transition_previous_amount_does_not_fallback_to_trigger_previous_amount_baseline(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600131",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric.update(
            {
                "current_price": 121,
                "today_virt_amount": 1200,
                "weekly_avg_with_today": 1100,
                "prev_weekly_avg": 1000,
                "trace_json": n3_standard_formal_amount_proof_trace("D"),
            }
        )
        row = context_row("stock:SH:600131", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = {
            "baseline_version": "test",
            "periods": {
                "D": {
                    "trigger_previous_entity_high": 117,
                    "trigger_previous_entity_low": 108.55,
                    "previous_transition": "flat",
                    "trigger_previous_amount_baseline": 1,
                    "current_amount_seed": 1,
                    "current_avg_amount_seed": 1,
                    "current_amount_total_seed": 1,
                }
            },
        }

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertFalse(plan["writes_common_trigger_match"])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["status"], "missing")
        self.assertIn("previous_transition_amount", detail["missing_fields"])
        self.assertEqual(
            detail["transition_previous_amount_trace"]["missing_allowed_fields"],
            ["previous_avg_amount", "previous_amount", "previous_amount_baseline", "classification_previous_amount_baseline"],
        )

    def test_ordinary_buy_amount_chain_failure_blocks_even_when_old_baseline_passes(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600128",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        trace = n3_standard_formal_amount_proof_trace("D")
        trace["formal_period_amount_proof"]["amount_chain_metrics"]["weekly_avg_with_today"] = 900
        trace["formal_period_amount_proof"]["amount_chain_metrics"]["prev_weekly_avg"] = 1000
        metric.update(
            {
                "current_price": 121,
                "today_virt_amount": 1200,
                "weekly_avg_with_today": 900,
                "prev_weekly_avg": 1000,
                "current_d_virtual_amount": 999999999,
                "trace_json": trace,
            }
        )
        row = context_row("stock:SH:600128", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            trigger_previous_amount_baseline=1,
        )

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["formal_trigger_period_proof_status"], "empty")
        detail = plan["formal_triggered_period_details"][0]
        self.assertFalse(detail["amount_pass"])
        self.assertEqual(detail["amount_chain_values"]["weekly_avg_with_today"], "900")

    def test_ordinary_sell_d_amount_chain_passes_with_symmetric_less_equal_rule(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600129",
            sell_30m_price_pass=True,
            sell_5m_amount_pass=True,
            current_30m_virtual_amount=80,
            previous_day_same_window_amount=100,
        )
        trace = n3_standard_formal_amount_proof_trace("D")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        chain["today_virt_amount"] = 800
        chain["weekly_avg_with_today"] = 900
        chain["prev_weekly_avg"] = 1000
        metric.update(
            {
                "current_price": 107,
                "today_virt_amount": 800,
                "weekly_avg_with_today": 900,
                "prev_weekly_avg": 1000,
                "trace_json": trace,
            }
        )
        row = context_row("stock:SH:600129", "sell", "SELL:D", ["S_SELL", "S_SELL_30M_SHRINK"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
        )

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        detail = plan["formal_triggered_period_details"][0]
        self.assertTrue(detail["price_pass"])
        self.assertTrue(detail["amount_pass"])
        self.assertEqual(detail["operator_chain"], "<=")

    def test_ordinary_sell_d_amount_chain_fail_blocks(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600130",
            sell_30m_price_pass=True,
            sell_5m_amount_pass=True,
            current_30m_virtual_amount=80,
            previous_day_same_window_amount=100,
        )
        trace = n3_standard_formal_amount_proof_trace("D")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        chain["today_virt_amount"] = 1200
        chain["weekly_avg_with_today"] = 900
        chain["prev_weekly_avg"] = 1000
        metric.update({"current_price": 107, "trace_json": trace})
        row = context_row("stock:SH:600130", "sell", "SELL:D", ["S_SELL", "S_SELL_30M_SHRINK"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
        )

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["formal_trigger_period_proof_status"], "empty")
        detail = plan["formal_triggered_period_details"][0]
        self.assertFalse(detail["amount_pass"])

    def test_w_m_q_amount_chain_pass_and_fail(self) -> None:
        cases = [
            ("W", "weekly_avg_with_today", "monthly_avg_with_today", "prev_monthly_avg"),
            ("M", "monthly_avg_with_today", "quarterly_avg_with_today", "prev_quarterly_avg"),
            ("Q", "quarterly_avg_with_today", "yearly_avg_with_today", "prev_yearly_avg"),
        ]
        for period, first_field, second_field, third_field in cases:
            with self.subTest(period=period, status="pass"):
                plan = formal_buy_plan_for_period(
                    period=period,
                    identity_key=f"stock:SH:601{period}01",
                    amount_values={first_field: 1200, second_field: 1100, third_field: 1000},
                )
                self.assertEqual(plan["plan_status"], "would_trigger")
                detail = plan["formal_triggered_period_details"][0]
                self.assertEqual(detail["period"], period)
                self.assertEqual(detail["amount_chain_fields"], [first_field, second_field, third_field])
                self.assertTrue(detail["amount_pass"])
            with self.subTest(period=period, status="fail"):
                plan = formal_buy_plan_for_period(
                    period=period,
                    identity_key=f"stock:SH:601{period}02",
                    amount_values={first_field: 900, second_field: 1100, third_field: 1000},
                )
                self.assertEqual(plan["plan_status"], "would_pending")
                detail = plan["formal_triggered_period_details"][0]
                self.assertFalse(detail["amount_pass"])

    def test_stock_300684_m_chain_pass_but_transition_not_upgraded_stays_pending(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("M", "D")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        amount_values = {
            "today_virt_amount": 545405086.4834027,
            "weekly_avg_with_today": 742834330.1778008,
            "prev_weekly_avg": 797720056.046,
            "monthly_avg_with_today": 904695410.947954,
            "prev_monthly_avg": 1006479660.5744444,
            "quarterly_avg_with_today": 856835757.5319886,
            "prev_quarterly_avg": 693802524.2321428,
        }
        chain.update(amount_values)
        trace["formal_period_amount_proof"]["periods"]["M"]["previous_avg_amount_yuan"] = 1006479660.5744444
        trace["formal_period_amount_proof"]["periods"]["M"]["previous_amount_yuan"] = 1006479660.5744444
        trace["formal_period_amount_proof"]["periods"]["D"]["previous_avg_amount_yuan"] = 797720056.046
        trace["formal_period_amount_proof"]["periods"]["D"]["previous_amount_yuan"] = 797720056.046
        metric = metric_row(
            "stock",
            "stock:SZ:300684",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric.update({"current_price": 57.62, "trace_json": trace, **amount_values})
        row = context_row("stock:SZ:300684", "buy", "BUY:M,D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = {
            "baseline_version": "test",
            "periods": {
                "M": {
                    "trigger_previous_entity_high": 56.16,
                    "trigger_previous_entity_low": 54.55009720676934,
                    "previous_transition": "low_volume_up",
                    "previous_avg_amount": "1006479.6605744444",
                },
                "D": {
                    "trigger_previous_entity_high": 57.06,
                    "trigger_previous_entity_low": 52.98,
                    "previous_transition": "low_volume_up",
                    "previous_avg_amount": "797720.056046",
                },
            },
        }

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertFalse(plan["writes_common_trigger_match"])
        self.assertFalse(plan["n5_entry_allowed"])
        by_period = {detail["period"]: detail for detail in plan["formal_triggered_period_details"]}
        self.assertTrue(by_period["M"]["price_pass"])
        self.assertEqual(by_period["M"]["previous_transition"], "low_volume_up")
        self.assertEqual(by_period["M"]["current_transition"], "low_volume_up")
        self.assertEqual(by_period["M"]["target_transition"], "volume_up")
        self.assertFalse(by_period["M"]["transition_amount_pass"])
        self.assertFalse(by_period["M"]["transition_upgrade_pass"])
        self.assertTrue(by_period["M"]["trigger_amount_chain_pass"])
        self.assertFalse(by_period["M"]["amount_pass"])
        self.assertEqual(by_period["M"]["transition_amount_values"]["monthly_avg_with_today"], "904695410.947954")
        self.assertEqual(by_period["M"]["transition_amount_values"]["n2_previous_amount_yuan"], "1006479660.5744444000")

    def test_transition_upgrade_is_required_even_when_current_transition_matches_target(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("M")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        chain.update(
            {
                "monthly_avg_with_today": 1200,
                "quarterly_avg_with_today": 1100,
                "prev_quarterly_avg": 1000,
                "prev_monthly_avg": 900,
            }
        )
        metric = metric_row("stock", "stock:SH:601M03", buy_30m_price_pass=True)
        metric.update(
            {
                "current_price": 121,
                "monthly_avg_with_today": 1200,
                "quarterly_avg_with_today": 1100,
                "prev_quarterly_avg": 1000,
                "prev_monthly_avg": 900,
                "trace_json": trace,
            }
        )
        row = context_row("stock:SH:601M03", "buy", "BUY:M", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "M",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            previous_transition="volume_up",
        )

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(detail["current_transition"], "volume_up")
        self.assertTrue(detail["trigger_amount_chain_pass"])
        self.assertFalse(detail["transition_upgrade_pass"])
        self.assertFalse(detail["amount_pass"])

    def test_buy_full_reuses_d_transition_gate_and_d_amount_chain(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("D")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        chain["today_virt_amount"] = 900
        chain["weekly_avg_with_today"] = 800
        chain["prev_weekly_avg"] = 700
        trace["formal_period_amount_proof"]["periods"]["D"]["previous_avg_amount_yuan"] = 1000
        trace["formal_period_amount_proof"]["periods"]["D"]["previous_amount_yuan"] = 1000
        metric = metric_row("stock", "stock:SH:601F01", buy_30m_price_pass=True)
        metric.update(
            {
                "current_price": 121,
                "today_virt_amount": 900,
                "weekly_avg_with_today": 800,
                "prev_weekly_avg": 700,
                "trace_json": trace,
            }
        )
        row = context_row("stock:SH:601F01", "buy", "BUY:FULL", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            previous_transition="flat",
        )

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["triggered_periods"], [])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["period"], "D")
        self.assertEqual(detail["current_transition"], "low_volume_up")
        self.assertFalse(detail["transition_amount_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])
        self.assertFalse(detail["amount_pass"])

    def test_sell_full_reuses_d_transition_gate_and_d_amount_chain(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("D")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        chain["today_virt_amount"] = 1100
        chain["weekly_avg_with_today"] = 1200
        chain["prev_weekly_avg"] = 1300
        trace["formal_period_amount_proof"]["periods"]["D"]["previous_avg_amount_yuan"] = 1000
        trace["formal_period_amount_proof"]["periods"]["D"]["previous_amount_yuan"] = 1000
        metric = metric_row("stock", "stock:SH:601F02", sell_30m_price_pass=True)
        metric.update(
            {
                "current_price": 107,
                "today_virt_amount": 1100,
                "weekly_avg_with_today": 1200,
                "prev_weekly_avg": 1300,
                "trace_json": trace,
            }
        )
        row = context_row("stock:SH:601F02", "sell", "SELL:FULL", ["S_SELL", "S_SELL_30M_SHRINK"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            previous_transition="flat",
        )

        plan = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )[0]

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["triggered_periods"], [])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["period"], "D")
        self.assertEqual(detail["current_transition"], "volume_down")
        self.assertFalse(detail["transition_amount_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])
        self.assertFalse(detail["amount_pass"])

    def test_buy_y_no_upper_chain_noop_triggers_on_transition_upgrade(self) -> None:
        plan = formal_buy_plan_for_period(
            period="Y",
            identity_key="stock:SH:601Y01",
            amount_values={"yearly_avg_with_today": 1200},
        )
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["formal_trigger_period_proof_status"], "passed")
        self.assertEqual(plan["triggered_periods"], ["Y"])
        self.assertEqual(plan["all_trigger_periods"], ["Y"])
        self.assertEqual(plan["primary_trigger_period"], "Y")
        self.assertTrue(plan["writes_common_trigger_match"])
        self.assertTrue(plan["n5_entry_allowed"])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["period"], "Y")
        self.assertEqual(detail["status"], "triggered")
        self.assertTrue(detail["price_pass"])
        self.assertTrue(detail["transition_upgrade_pass"])
        self.assertTrue(detail["amount_pass"])
        self.assertIsNone(detail["trigger_amount_chain_pass"])
        self.assertEqual(detail["trigger_amount_chain_status"], "not_applicable")
        self.assertEqual(detail["trigger_amount_chain_gate"], "no_upper_period_chain_noop")
        self.assertEqual(detail["reason"], "year_period_has_no_upper_amount_chain")
        self.assertEqual(detail["operator_chain"], "no_upper_period_chain_noop")
        self.assertEqual(detail["amount_chain_fields"], [])
        self.assertEqual(detail["amount_chain_values"], {})

    def test_sell_y_no_upper_chain_noop_triggers_on_transition_upgrade(self) -> None:
        plan = formal_sell_plan_for_period(period="Y", identity_key="stock:SH:601Y02")

        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["Y"])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["period"], "Y")
        self.assertTrue(detail["price_pass"])
        self.assertTrue(detail["transition_upgrade_pass"])
        self.assertTrue(detail["amount_pass"])
        self.assertIsNone(detail["trigger_amount_chain_pass"])
        self.assertEqual(detail["trigger_amount_chain_status"], "not_applicable")
        self.assertEqual(detail["trigger_amount_chain_gate"], "no_upper_period_chain_noop")
        self.assertEqual(detail["reason"], "year_period_has_no_upper_amount_chain")
        self.assertEqual(detail["operator_chain"], "no_upper_period_chain_noop")

    def test_buy_y_price_pass_but_transition_not_upgraded_stays_pending(self) -> None:
        plan = formal_buy_plan_for_period(
            period="Y",
            identity_key="stock:SH:601Y03",
            amount_values={"yearly_avg_with_today": 800},
        )

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertFalse(plan["writes_common_trigger_match"])
        self.assertFalse(plan["n5_entry_allowed"])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["period"], "Y")
        self.assertTrue(detail["price_pass"])
        self.assertFalse(detail["transition_upgrade_pass"])
        self.assertFalse(detail["amount_pass"])
        self.assertIsNone(detail["trigger_amount_chain_pass"])
        self.assertEqual(detail["trigger_amount_chain_status"], "not_applicable")
        self.assertEqual(detail["trigger_amount_chain_gate"], "no_upper_period_chain_noop")

    def test_sell_y_price_pass_but_transition_not_upgraded_stays_pending(self) -> None:
        plan = formal_sell_plan_for_period(
            period="Y",
            identity_key="stock:SH:601Y04",
            metric_overrides={"yearly_avg_with_today": 1200},
        )

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["triggered_periods"], [])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["period"], "Y")
        self.assertTrue(detail["price_pass"])
        self.assertFalse(detail["transition_upgrade_pass"])
        self.assertFalse(detail["amount_pass"])
        self.assertIsNone(detail["trigger_amount_chain_pass"])
        self.assertEqual(detail["trigger_amount_chain_status"], "not_applicable")
        self.assertEqual(detail["trigger_amount_chain_gate"], "no_upper_period_chain_noop")

    def test_mixed_y_m_d_price_only_year_does_not_create_trigger_match(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SZ:300687",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        trace = n3_standard_formal_amount_proof_trace("Y", "M", "D")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        amount_values = {
            "today_virt_amount": 597599234.415023,
            "weekly_avg_with_today": 597862926.258341,
            "prev_weekly_avg": 459084901.64599997,
            "monthly_avg_with_today": 514098733.61038643,
            "quarterly_avg_with_today": 616136396.5368273,
            "prev_quarterly_avg": 360561206.91071427,
            "yearly_avg_with_today": 483615927.84180576,
            "prev_yearly_avg": 572064875.9876543,
        }
        chain.update(amount_values)
        metric.update(
            {
                "current_price": 26.73,
                "trace_json": trace,
                **amount_values,
            }
        )
        row = context_row("stock:SZ:300687", "buy", "BUY:Y,M,D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = {
            "baseline_version": "test",
            "periods": {
                "Y": {
                    "trigger_previous_entity_high": 22.97,
                    "trigger_previous_entity_low": 18.0843548782389769,
                    "previous_avg_amount": "572064.8759876543",
                },
                "M": {
                    "trigger_previous_entity_high": 25.58,
                    "trigger_previous_entity_low": 25,
                    "previous_avg_amount": "1068186.2498877777",
                },
                "D": {
                    "trigger_previous_entity_high": 25.48,
                    "trigger_previous_entity_low": 22.89,
                    "previous_avg_amount": "459084.90164599997",
                },
            },
        }

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertFalse(plan["writes_common_trigger_match"])
        by_period = {detail["period"]: detail for detail in plan["formal_triggered_period_details"]}
        self.assertTrue(by_period["Y"]["price_pass"])
        self.assertFalse(by_period["Y"]["amount_pass"])
        self.assertFalse(by_period["Y"]["transition_upgrade_pass"])
        self.assertIsNone(by_period["Y"]["trigger_amount_chain_pass"])
        self.assertEqual(by_period["Y"]["trigger_amount_chain_status"], "not_applicable")
        self.assertEqual(by_period["Y"]["trigger_amount_chain_gate"], "no_upper_period_chain_noop")
        self.assertEqual(by_period["Y"]["reason"], "year_period_has_no_upper_amount_chain")
        self.assertTrue(by_period["D"]["price_pass"])
        self.assertFalse(by_period["D"]["amount_pass"])
        self.assertEqual(by_period["D"]["amount_chain_values"]["today_virt_amount"], "597599234.415023")
        self.assertEqual(by_period["D"]["amount_chain_values"]["weekly_avg_with_today"], "597862926.258341")

    def test_mixed_y_d_uses_d_as_primary_when_d_amount_chain_passes(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:601YD1",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        trace = n3_standard_formal_amount_proof_trace("Y", "D")
        chain = trace["formal_period_amount_proof"]["amount_chain_metrics"]
        chain["yearly_avg_with_today"] = 800
        chain["prev_yearly_avg"] = 700
        trace["formal_period_amount_proof"]["periods"]["Y"]["previous_avg_amount_yuan"] = 700
        trace["formal_period_amount_proof"]["periods"]["Y"]["previous_amount_yuan"] = 700
        metric.update(
            {
                "current_price": 121,
                "yearly_avg_with_today": 800,
                "prev_yearly_avg": 700,
                "trace_json": trace,
            }
        )
        row = context_row("stock:SH:601YD1", "buy", "BUY:Y,D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = {
            "baseline_version": "test",
            "periods": {
                "Y": {
                    "trigger_previous_entity_high": 100,
                    "trigger_previous_entity_low": 90,
                    "previous_avg_amount": "0.7",
                },
                "D": {
                    "trigger_previous_entity_high": 117,
                    "trigger_previous_entity_low": 108.55,
                    "previous_avg_amount": "1",
                },
            },
        }

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["triggered_periods"], ["Y", "D"])
        self.assertEqual(plan["primary_trigger_period"], "Y")
        by_period = {detail["period"]: detail for detail in plan["formal_triggered_period_details"]}
        self.assertTrue(by_period["Y"]["amount_pass"])
        self.assertEqual(by_period["Y"]["status"], "triggered")
        self.assertIsNone(by_period["Y"]["trigger_amount_chain_pass"])
        self.assertTrue(by_period["D"]["amount_pass"])

    def test_missing_formal_amount_chain_field_blocks(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("D")
        del trace["formal_period_amount_proof"]["amount_chain_metrics"]["weekly_avg_with_today"]
        plan = formal_buy_plan_for_period(
            period="D",
            identity_key="stock:SH:601D03",
            amount_values={},
            trace=trace,
            metric_overrides={"weekly_avg_with_today": None},
        )
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["formal_trigger_period_proof_status"], "missing")
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["reason"], "formal_amount_chain_required_field_missing")
        self.assertIn("weekly_avg_with_today", detail["missing_fields"])

    def test_missing_formal_amount_unit_conversion_policy_blocks(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("D")
        del trace["formal_period_amount_proof"]["unit_conversion_policy"]
        del trace["formal_period_amount_proof"]["periods"]["D"]["unit_conversion_policy"]

        plan = formal_buy_plan_for_period(
            period="D",
            identity_key="stock:SH:601D04",
            amount_values={
                "today_virt_amount": 1200,
                "weekly_avg_with_today": 1100,
                "prev_weekly_avg": 1000,
            },
            trace=trace,
        )

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["formal_trigger_period_proof_status"], "missing")
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["reason"], "formal_amount_chain_unit_proof_missing_or_invalid")
        self.assertIn("unit_conversion_policy", detail["missing_fields"])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_wrong_formal_amount_unit_conversion_policy_blocks(self) -> None:
        trace = n3_standard_formal_amount_proof_trace("D")
        trace["formal_period_amount_proof"]["unit_conversion_policy"] = "legacy_thousand_yuan_passthrough"
        trace["formal_period_amount_proof"]["periods"]["D"]["unit_conversion_policy"] = "legacy_thousand_yuan_passthrough"

        plan = formal_buy_plan_for_period(
            period="D",
            identity_key="stock:SH:601D05",
            amount_values={
                "today_virt_amount": 1200,
                "weekly_avg_with_today": 1100,
                "prev_weekly_avg": 1000,
            },
            trace=trace,
        )

        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["reason"], "formal_amount_chain_unit_proof_missing_or_invalid")
        self.assertEqual(detail["unit_conversion_policy"], "legacy_thousand_yuan_passthrough")

    def test_stock_002831_w_amount_chain_requires_canonical_unit_proof(self) -> None:
        plan = formal_buy_plan_for_period(
            period="W",
            identity_key="stock:SZ:002831",
            amount_values={
                "weekly_avg_with_today": 1_200_000,
                "monthly_avg_with_today": 1_100_000,
                "prev_monthly_avg": 1_000_000,
            },
        )

        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["triggered_periods"], ["W"])
        detail = plan["formal_triggered_period_details"][0]
        self.assertEqual(detail["period"], "W")
        self.assertEqual(detail["amount_unit"], "yuan")
        self.assertEqual(detail["amount_rule"], "attachment_dwmqy_avg_chain")
        self.assertEqual(
            detail["unit_conversion_policy"],
            "formal_amount_chain_thousand_yuan_to_yuan_v1",
        )
        self.assertTrue(detail["amount_pass"])

    def test_ordinary_buy_missing_n3_amount_source_proof_fails_closed(self) -> None:
        metric = metric_row(
            "stock",
            "stock:SH:600125",
            buy_30m_price_pass=True,
            buy_5m_amount_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric.update(
            {
                "current_d_body_high": 121,
                "current_d_body_low": 115,
                "current_d_virtual_amount": 3_200_000,
                "trace_json": {"formal_period_amount_proof": {"source_kind": "realtime_daily_snapshot", "amount_unit": "yuan"}},
            }
        )
        row = context_row("stock:SH:600125", "buy", "BUY:D", ["B_BUY", "B_BUY_30M_VOL"])
        row["period_trigger_baseline_json"] = formal_baseline(
            "D",
            trigger_previous_entity_high=117,
            trigger_previous_entity_low=108.55,
            trigger_previous_amount_baseline=2_948_974.34197,
        )
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[row],
            metric_rows=[metric],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["not_ready_reason"], "formal_trigger_period_proof_missing")
        self.assertEqual(plan["formal_trigger_period_proof_status"], "missing")
        self.assertFalse(plan["n5_entry_allowed"])

    def test_ordinary_buy_metric_without_formal_period_proof_does_not_emit_30m_formal_trigger(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[
                context_row("stock:SH:600120", "buy", "BUY:M,W,D", ["B_BUY", "B_BUY_30M_VOL"]),
            ],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600120",
                    buy_30m_price_pass=True,
                    buy_5m_amount_pass=True,
                    current_30m_virtual_amount=220,
                    previous_day_same_window_amount=100,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["not_ready_reason"], "formal_trigger_period_proof_missing")
        self.assertNotEqual(plan["trigger_period"], "30m")
        self.assertIsNone(plan["primary_trigger_period"])
        self.assertEqual(plan["all_trigger_periods"], [])
        self.assertEqual(plan["triggered_periods"], [])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_ordinary_sell_metric_without_formal_proof_stays_pending(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[
                context_row("stock:SH:600021", "sell", "SELL:Y,Q,D", ["S_SELL", "S_SELL_30M_SHRINK"]),
            ],
            metric_rows=[
                metric_row(
                    "stock",
                    "stock:SH:600021",
                    sell_30m_price_pass=False,
                    sell_5m_amount_pass=True,
                    current_30m_virtual_amount=120,
                    previous_day_same_window_amount=100,
                ),
            ],
        )

        plan = plans[0]
        self.assertEqual(plan["plan_status"], "would_pending")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["signal_type"], "S_SELL")
        self.assertEqual(plan["trigger_mark_candidate"], "normal")
        self.assertEqual(plan["projection_30m_type"], "none")
        self.assertEqual(plan["not_ready_reason"], "formal_trigger_period_proof_missing")
        self.assertEqual(plan["trigger_period"], "Y")
        self.assertIsNone(plan["primary_trigger_period"])
        self.assertEqual(plan["all_trigger_periods"], [])
        self.assertEqual(plan["triggered_periods"], [])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_ordinary_buy_formal_chain_does_not_require_action_confirmation_side_flags(self) -> None:
        plan = formal_buy_plan_for_period(
            period="D",
            identity_key="stock:SH:600022",
            amount_values={
                "today_virt_amount": 1200,
                "weekly_avg_with_today": 1100,
                "prev_weekly_avg": 1000,
            },
            metric_overrides={"buy_1m_amount_pass": False},
        )

        self.assertEqual(plan["plan_status"], "would_trigger")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        detail = plan["formal_triggered_period_details"][0]
        self.assertTrue(detail["price_pass"])
        self.assertTrue(detail["amount_pass"])

    def test_missing_or_not_ready_metric_never_triggers(self) -> None:
        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[
                context_row("stock:SH:600003", "buy", "BUY_HINT", ["BUY_HINT"]),
                context_row("stock:SH:600004", "sell", "SELL:D", ["S_SELL_30M_SHRINK"]),
            ],
            metric_rows=[
                metric_row("stock", "stock:SH:600004", metric_ready=False, metric_quality_status="missing"),
            ],
        )

        self.assertEqual([plan["plan_status"] for plan in plans], ["would_pending", "would_pending"])
        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerPendingMarketData", "TriggerPendingMarketData"])
        self.assertEqual([plan["not_ready_reason"] for plan in plans], ["metric_row_missing", "metric_not_ready"])
        self.assertFalse(any(plan["trigger_live"] for plan in plans))

    def test_full_day_replay_evaluates_each_metric_minute_instead_of_latest_only(self) -> None:
        metric_1056 = metric_row(
            "stock",
            "stock:SH:603259",
            buy_30m_price_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric_1056.update(
            {
                "action_confirmation_metric_id": 1056,
                "source_snapshot_event_id": "evt-stock:SH:603259-1056",
                "metric_time": "2026-06-02T10:56:00+08:00",
                "metric_minute_label": "10:56",
            }
        )
        metric_1500 = metric_row(
            "stock",
            "stock:SH:603259",
            buy_30m_price_pass=False,
            current_30m_virtual_amount=80,
            previous_day_same_window_amount=100,
        )
        metric_1500.update(
            {
                "action_confirmation_metric_id": 1500,
                "source_snapshot_event_id": "evt-stock:SH:603259-1500",
                "metric_time": "2026-06-02T15:00:00+08:00",
                "metric_minute_label": "15:00",
            }
        )

        plans = build_action_confirmation_metric_full_day_replay_plans(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:603259", "buy", "BUY:Q,M,W,D", ["B_BUY_30M_VOL"])],
            metric_rows=[metric_1500, metric_1056],
        )

        self.assertEqual(plans, [])

    def test_true_full_day_minute_dry_run_routes_to_time_series_planner(self) -> None:
        metric_0931 = metric_row(
            "stock",
            "stock:SH:603260",
            buy_30m_price_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
            projection_schema_version="n3.action_confirmation_metric.true_full_day_minute_series.v1",
        )
        metric_0931.update(
            {
                "action_confirmation_metric_id": 931,
                "source_snapshot_event_id": "evt-stock:SH:603260-0931",
                "metric_time": "2026-06-02T09:31:00+08:00",
                "metric_minute_label": "09:31",
            }
        )
        metric_1500 = metric_row(
            "stock",
            "stock:SH:603260",
            buy_30m_price_pass=False,
            current_30m_virtual_amount=80,
            previous_day_same_window_amount=100,
            projection_schema_version="n3.action_confirmation_metric.true_full_day_minute_series.v1",
        )
        metric_1500.update(
            {
                "action_confirmation_metric_id": 1500,
                "source_snapshot_event_id": "evt-stock:SH:603260-1500",
                "metric_time": "2026-06-02T15:00:00+08:00",
                "metric_minute_label": "15:00",
            }
        )

        report = build_action_confirmation_metric_dry_run_report(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:603260", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[metric_1500, metric_0931],
        )

        self.assertEqual(report["replay_mode"], "full_day_metric_time_series")
        self.assertEqual(report["input_summary"]["metric_row_count"], 2)
        self.assertEqual(report["plans"]["output_plan_count"], 1)
        plans = report["plans"]["would_trigger_plans"]
        self.assertEqual([plan["trigger_bucket"] for plan in plans], ["09:31"])
        self.assertTrue(all(plan["replay_mode"] == "full_day_metric_time_series" for plan in plans))

    def test_true_full_day_minute_dry_run_uses_streaming_planner_summary(self) -> None:
        metric_0931 = metric_row(
            "stock",
            "stock:SH:603262",
            buy_30m_price_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
            projection_schema_version="n3.action_confirmation_metric.true_full_day_minute_series.v1",
        )
        metric_0931.update({"metric_time": "2026-06-02T09:31:00+08:00", "metric_minute_label": "09:31"})
        metric_1500 = metric_row(
            "stock",
            "stock:SH:603262",
            buy_30m_price_pass=False,
            current_30m_virtual_amount=80,
            previous_day_same_window_amount=100,
            projection_schema_version="n3.action_confirmation_metric.true_full_day_minute_series.v1",
        )
        metric_1500.update({"metric_time": "2026-06-02T15:00:00+08:00", "metric_minute_label": "15:00"})
        original_builder = matcher.build_action_confirmation_metric_plans_for_metric_grain

        def fail_if_materialized(**_: object) -> list[dict[str, object]]:
            raise AssertionError("full-day dry-run must not materialize all plans")

        matcher.build_action_confirmation_metric_plans_for_metric_grain = fail_if_materialized  # type: ignore[assignment]
        try:
            report = build_action_confirmation_metric_dry_run_report(
                trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
                projection_run_id=DEFAULT_PROJECTION_RUN_ID,
                source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
                source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
                source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
                for_trade_date=DEFAULT_FOR_TRADE_DATE,
                context_rows=[context_row("stock:SH:603262", "buy", "BUY_HINT", ["BUY_HINT"])],
                metric_rows=[metric_1500, metric_0931],
            )
        finally:
            matcher.build_action_confirmation_metric_plans_for_metric_grain = original_builder  # type: ignore[assignment]

        self.assertEqual(report["replay_mode"], "full_day_metric_time_series")
        self.assertEqual(report["plans"]["output_plan_count"], 1)

    def test_time_series_metric_lookup_reuses_metric_row_objects(self) -> None:
        metric_0931 = metric_row("stock", "stock:SH:603263")
        metric_0931.update({"metric_time": "2026-06-02T09:31:00+08:00", "metric_minute_label": "09:31"})
        metric_1500 = metric_row("stock", "stock:SH:603263")
        metric_1500.update({"metric_time": "2026-06-02T15:00:00+08:00", "metric_minute_label": "15:00"})

        lookup = matcher.metrics_by_identity_time_series([metric_1500, metric_0931], projection_run_id=DEFAULT_PROJECTION_RUN_ID)

        rows = lookup[("stock", "stock:SH:603263")]
        self.assertIs(rows[0], metric_0931)
        self.assertIs(rows[1], metric_1500)

    def test_full_day_formal_helpers_cache_reused_context_and_metric_proof(self) -> None:
        row = ordinary_buy_context_row("stock:SH:603264", "BUY:D")
        row["period_trigger_baseline_json"] = json.dumps(row["period_trigger_baseline_json"])
        metric = ordinary_buy_metric("stock:SH:603264", metric_id=1, minute_label="09:31", current_price=121)

        self.assertIs(matcher.period_baseline(row, "D"), matcher.period_baseline(row, "D"))
        self.assertIs(
            matcher.n3_formal_amount_proof_for_period(metric, "D"),
            matcher.n3_formal_amount_proof_for_period(metric, "D"),
        )

    def test_latest_metric_dry_run_keeps_latest_identity_planner(self) -> None:
        metric_1105 = metric_row(
            "stock",
            "stock:SH:603261",
            buy_30m_price_pass=True,
            current_30m_virtual_amount=220,
            previous_day_same_window_amount=100,
        )
        metric_1105.update(
            {
                "action_confirmation_metric_id": 1105,
                "source_snapshot_event_id": "evt-stock:SH:603261-1105",
                "metric_time": "2026-06-02T11:05:00+08:00",
                "metric_minute_label": "11:05",
            }
        )
        metric_1104 = metric_row(
            "stock",
            "stock:SH:603261",
            buy_30m_price_pass=False,
            current_30m_virtual_amount=80,
            previous_day_same_window_amount=100,
        )
        metric_1104.update(
            {
                "action_confirmation_metric_id": 1104,
                "source_snapshot_event_id": "evt-stock:SH:603261-1104",
                "metric_time": "2026-06-02T11:04:00+08:00",
                "metric_minute_label": "11:04",
            }
        )

        report = build_action_confirmation_metric_dry_run_report(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            context_rows=[context_row("stock:SH:603261", "buy", "BUY_HINT", ["BUY_HINT"])],
            metric_rows=[metric_1105, metric_1104],
        )

        self.assertEqual(report["replay_mode"], "latest_metric_by_identity")
        self.assertEqual(report["plans"]["output_plan_count"], 1)
        self.assertEqual(report["plans"]["would_trigger_plans"][0]["trigger_bucket"], "11:05")

    def test_execute_runner_uses_shared_planner_router(self) -> None:
        source = inspect.getsource(execute.run_action_confirmation_metric_once)

        self.assertIn("iter_action_confirmation_metric_plans_for_metric_grain", source)
        self.assertNotIn("plans = build_action_confirmation_metric_plans(", source)

    def test_report_and_preflight_are_read_only_and_no_opaque_payload(self) -> None:
        report = build_action_confirmation_metric_dry_run_report(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            trigger_run={"run_id": DEFAULT_TRIGGER_CONTEXT_RUN_ID, "status": "passed"},
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"]),
                context_row("stock:SH:600001", "sell", "SELL_HINT", ["SELL_HINT"]),
            ],
            metric_rows=[
                metric_row("stock", "stock:SH:600000", buy_30m_price_pass=True, buy_5m_amount_pass=True),
                metric_row("stock", "stock:SH:600001", sell_30m_price_pass=False, sell_5m_amount_pass=True),
            ],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )
        preflight = build_action_confirmation_metric_preflight_report(report)

        self.assertEqual(report["result"], "DRY_RUN_PASS", report["quality"]["items"])
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["replay_mode"], report["replay_mode"])
        self.assertFalse(preflight["execute_authorized"])
        self.assertEqual(report["summary"]["would_trigger_count"], 1)
        self.assertEqual(report["summary"]["would_pending_count"], 1)
        self.assertEqual(report["summary"]["opaque_action_confirmation_payload_count"], 0)
        self.assertFalse(report["side_effects"]["event_outbox_written"])
        self.assertFalse(report["side_effects"]["common_event_inbox_written"])
        self.assertFalse(report["side_effects"]["checkpoint_written"])
        self.assertFalse(report["side_effects"]["raw_minute_tables_read"])
        self.assertFalse(report["side_effects"]["market_data_pulled"])
        self.assertFalse(report["side_effects"]["worker_started"])

    def test_contract_does_not_read_raw_minutes_or_old_projection_tables(self) -> None:
        self.assertFalse(set(ACTION_CONFIRMATION_METRIC_READ_TABLES) & set(FORBIDDEN_ACTION_CONFIRMATION_METRIC_READ_TABLES))
        module_source = inspect.getsource(matcher)
        for forbidden in ("mootdx", "tushare", "MarketDataAdapter", "fetch_full_day_minute_bars"):
            self.assertNotIn(forbidden, module_source)

    def test_cli_execute_flag_blocks_before_writes(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/plan_trigger_action_confirmation_metric_dry_run.py",
                "--execute",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn('"result": "BLOCKED"', result.stdout)
        self.assertIn('"writes_database": false', result.stdout)

    def test_business_execute_gate_cli_execute_flag_blocks_before_writes(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/plan_trigger_action_confirmation_metric_business_execute_gate.py",
                "--execute",
                "--user-confirmed",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn('"result": "BLOCKED"', result.stdout)
        self.assertIn('"writes_database": false', result.stdout)
        self.assertIn('"writes_inbox_or_checkpoint": false', result.stdout)

    def test_business_execute_contract_scopes_writes_and_counts_from_dry_run(self) -> None:
        report = sample_action_confirmation_report()
        preflight = build_action_confirmation_metric_preflight_report(report)
        contract = build_action_confirmation_metric_business_execute_contract(
            report,
            preflight,
            execute_run_id="trigger_action_confirmation_metric_execute_test",
            rollback_sql_path="sql/N4_action_confirmation_metric_business_execute_rollback.sql",
        )

        self.assertEqual(contract["result"], "CONTRACT_PASS", contract.get("blockers"))
        self.assertEqual(contract["expected_writes"]["TriggerMatched"], 1)
        self.assertEqual(contract["expected_writes"]["TriggerPendingMarketData"], 0)
        self.assertEqual(contract["expected_writes"]["TriggerStateChanged"], 0)
        self.assertEqual(contract["expected_writes"]["common_trigger_state"], 1)
        self.assertEqual(contract["expected_writes"]["common_trigger_match"], 1)
        self.assertEqual(contract["expected_writes"]["common_event_outbox"], 1)
        self.assertEqual(
            tuple(contract["allowed_write_tables_after_final_confirmation"]),
            ALLOWED_ACTION_CONFIRMATION_METRIC_EXECUTE_WRITE_TABLES,
        )
        self.assertIn("common_event_inbox", contract["forbidden_write_tables"])
        self.assertIn("common_event_consumer_checkpoint", contract["forbidden_write_tables"])
        self.assertFalse(contract["input_semantics"]["consumes_n3_outbox"])
        self.assertFalse(contract["input_semantics"]["writes_inbox"])
        self.assertFalse(contract["input_semantics"]["writes_checkpoint"])
        self.assertTrue(contract["requires_execute_flag"])
        self.assertTrue(contract["requires_user_confirmed_flag"])
        self.assertFalse(contract["runner_readiness"]["business_execute_runner_ready"])

    def test_business_execute_contract_does_not_write_match_for_pending_market_data(self) -> None:
        report = sample_action_confirmation_report(would_trigger_count=0, would_pending_count=2)
        preflight = build_action_confirmation_metric_preflight_report(report)
        contract = build_action_confirmation_metric_business_execute_contract(
            report,
            preflight,
            execute_run_id="trigger_action_confirmation_metric_execute_test",
            rollback_sql_path="sql/N4_action_confirmation_metric_business_execute_rollback.sql",
            business_execute_runner_ready=True,
            business_execute_runner="scripts/run_trigger_action_confirmation_metric_once.py",
        )
        final_preflight = build_action_confirmation_metric_execute_final_preflight(
            report,
            preflight,
            contract,
            baseline_summary=clean_execute_baseline(),
            rollback_sql_exists=True,
        )

        self.assertEqual(contract["result"], "CONTRACT_PASS", contract.get("blockers"))
        self.assertEqual(contract["expected_writes"]["TriggerMatched"], 0)
        self.assertEqual(contract["expected_writes"]["TriggerPendingMarketData"], 0)
        self.assertEqual(contract["expected_writes"]["TriggerStateChanged"], 0)
        self.assertEqual(contract["expected_writes"]["common_trigger_state"], 0)
        self.assertEqual(contract["expected_writes"]["common_trigger_match"], 0)
        self.assertEqual(contract["expected_writes"]["common_event_outbox"], 0)
        self.assertEqual(final_preflight["result"], "PREFLIGHT_PASS", final_preflight.get("blockers"))
        self.assertEqual(final_preflight["planned_writes"]["common_trigger_match"], 0)

    def test_final_preflight_blocks_until_business_execute_runner_exists(self) -> None:
        report = sample_action_confirmation_report()
        preflight = build_action_confirmation_metric_preflight_report(report)
        contract = build_action_confirmation_metric_business_execute_contract(
            report,
            preflight,
            execute_run_id="trigger_action_confirmation_metric_execute_test",
            rollback_sql_path="sql/N4_action_confirmation_metric_business_execute_rollback.sql",
        )
        final_preflight = build_action_confirmation_metric_execute_final_preflight(
            report,
            preflight,
            contract,
            baseline_summary=clean_execute_baseline(),
            rollback_sql_exists=True,
        )

        self.assertEqual(final_preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("n4_action_confirmation_metric_business_execute_runner_ready", final_preflight["blockers"])
        self.assertFalse(final_preflight["next_gate"]["allow_business_execute_user_confirmation"])
        self.assertFalse(final_preflight["side_effects"]["writes_performed"])
        self.assertEqual(final_preflight["planned_writes"]["TriggerMatched"], 1)
        self.assertEqual(final_preflight["planned_writes"]["TriggerPendingMarketData"], 0)

    def test_final_preflight_passes_when_business_runner_ready_and_baseline_clean(self) -> None:
        report = sample_action_confirmation_report()
        preflight = build_action_confirmation_metric_preflight_report(report)
        contract = build_action_confirmation_metric_business_execute_contract(
            report,
            preflight,
            execute_run_id="trigger_action_confirmation_metric_execute_test",
            business_execute_runner_ready=True,
            business_execute_runner="scripts/run_trigger_action_confirmation_metric_once.py",
        )
        final_preflight = build_action_confirmation_metric_execute_final_preflight(
            report,
            preflight,
            contract,
            baseline_summary=clean_execute_baseline(),
            rollback_sql_exists=True,
        )

        self.assertEqual(final_preflight["result"], "PREFLIGHT_PASS", final_preflight["quality_items"])
        self.assertTrue(final_preflight["next_gate"]["allow_business_execute_user_confirmation"])
        self.assertFalse(final_preflight["execute_authorized"])
        self.assertEqual(final_preflight["runner_readiness"]["business_execute_runner"], "scripts/run_trigger_action_confirmation_metric_once.py")
        self.assertIn("--execute --user-confirmed", " ".join(final_preflight["next_gate"]["required_before_execute"]))
        self.assertNotIn("implement a dedicated", " ".join(final_preflight["next_gate"]["required_before_execute"]))
        self.assertEqual(final_preflight["quality"]["p0_count"], severity_count(final_preflight["quality_items"], "P0"))
        self.assertEqual(final_preflight["quality"]["p1_count"], severity_count(final_preflight["quality_items"], "P1"))
        self.assertEqual(final_preflight["quality"]["p2_count"], severity_count(final_preflight["quality_items"], "P2"))
        self.assertIn("n4_action_confirmation_metric_pending_candidates_dropped", {
            item["gate_code"] for item in final_preflight["quality_items"] if item["severity"] == "P1"
        })

    def test_final_preflight_blocks_nonzero_target_baseline(self) -> None:
        report = sample_action_confirmation_report()
        preflight = build_action_confirmation_metric_preflight_report(report)
        contract = build_action_confirmation_metric_business_execute_contract(
            report,
            preflight,
            execute_run_id="trigger_action_confirmation_metric_execute_test",
        )
        baseline = clean_execute_baseline()
        baseline["execute_run_outbox"] = 1
        final_preflight = build_action_confirmation_metric_execute_final_preflight(
            report,
            preflight,
            contract,
            baseline_summary=baseline,
            rollback_sql_exists=True,
        )

        self.assertEqual(final_preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertIn("n4_action_confirmation_metric_target_baseline_zero", final_preflight["blockers"])

    def test_dry_run_quality_blocks_legacy_y_auto_amount_operator(self) -> None:
        metric = metric_row("stock", "stock:SH:601Y99")
        context = context_row("stock:SH:601Y99", "buy", "BUY:Y", ["B_BUY"])
        legacy_plan = {
            "plan_status": "would_trigger",
            "output_event_type": "TriggerMatched",
            "metric_ready": True,
            "signal_type": "B_BUY",
            "condition_key": "BUY:Y",
            "trigger_mark_candidate": "normal",
            "triggered_periods": ["Y"],
            "all_trigger_periods": ["Y"],
            "primary_trigger_period": "Y",
            "formal_triggered_period_details": [
                {"period": "Y", "operator_chain": "always_true_for_Y", "amount_pass": True}
            ],
            "metric_trace": {},
        }

        items = matcher.build_action_confirmation_metric_quality_items(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            trigger_run={"run_id": DEFAULT_TRIGGER_CONTEXT_RUN_ID, "status": "passed"},
            context_rows=[context],
            metric_rows=[metric],
            plans=[legacy_plan],
            summary={"opaque_action_confirmation_payload_count": 0, "would_pending_count": 0},
            before_row_counts={},
            after_row_counts={},
        )

        failed = {item["gate_code"] for item in items if item["status"] == "failed"}
        self.assertIn("n4_action_confirmation_metric_no_year_auto_amount_operator", failed)
        self.assertNotIn("n4_action_confirmation_metric_no_unversioned_year_trigger", failed)

    def test_dry_run_quality_blocks_all_ordinary_formal_missing_proof(self) -> None:
        metric = metric_row("stock", "stock:SH:601P99")
        context = context_row("stock:SH:601P99", "buy", "BUY:D", ["B_BUY"])
        pending_plan = {
            "plan_status": "would_pending",
            "output_event_type": "TriggerPendingMarketData",
            "metric_ready": True,
            "signal_type": "B_BUY",
            "condition_key": "BUY:D",
            "trigger_mark_candidate": "normal",
            "not_ready_reason": "formal_trigger_period_proof_missing",
            "metric_trace": {},
        }

        items = matcher.build_action_confirmation_metric_quality_items(
            trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
            projection_run_id=DEFAULT_PROJECTION_RUN_ID,
            source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
            for_trade_date=DEFAULT_FOR_TRADE_DATE,
            trigger_run={"run_id": DEFAULT_TRIGGER_CONTEXT_RUN_ID, "status": "passed"},
            context_rows=[context],
            metric_rows=[metric],
            plans=[pending_plan],
            summary={"opaque_action_confirmation_payload_count": 0, "would_pending_count": 1},
            before_row_counts={},
            after_row_counts={},
        )

        failed = {item["gate_code"] for item in items if item["status"] == "failed"}
        self.assertIn("n4_action_confirmation_metric_ordinary_formal_not_all_missing_proof", failed)

    def test_business_rollback_sql_is_execute_run_scoped_and_guards_downstream(self) -> None:
        rollback_sql = build_action_confirmation_metric_execute_rollback_sql("trigger_action_confirmation_metric_execute_test")

        self.assertIn("DELETE FROM common_event_outbox", rollback_sql)
        self.assertIn("DELETE FROM common_trigger_match", rollback_sql)
        self.assertIn("DELETE FROM common_trigger_state", rollback_sql)
        self.assertIn("DELETE FROM common_trigger_quality_item", rollback_sql)
        self.assertIn("DELETE FROM common_trigger_run", rollback_sql)
        self.assertIn("status IN ('delivering', 'delivered')", rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertNotIn("stock_action_confirmation_projection_metric", rollback_sql)
        self.assertNotIn("stock_minute_bar_1m", rollback_sql)


def context_row(identity_key: str, direction: str, condition_key: str, allowed_signal_types: list[str]) -> dict[str, object]:
    return {
        "trigger_context_id": abs(hash((identity_key, condition_key))) % 100000,
        "run_id": DEFAULT_TRIGGER_CONTEXT_RUN_ID,
        "source_condition_run_id": DEFAULT_SOURCE_CONDITION_RUN_ID,
        "source_condition_pool_id": 11,
        "source_condition_basis_id": 12,
        "source_minute_target_scope_id": 13,
        "source_market_subscription_id": 14,
        "for_trade_date": DEFAULT_FOR_TRADE_DATE,
        "source_trade_date": "20260601",
        "prev_trade_date": "20260601",
        "asset_kind": identity_key.split(":", 1)[0],
        "identity_key": identity_key,
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": ["D"],
        "allowed_signal_types": allowed_signal_types,
        "is_hint_scope": condition_key in {"BUY_HINT", "SELL_HINT"},
        "context_hash": f"context-{identity_key}-{condition_key}",
        "quality_status": "passed",
        "period_trigger_baseline_json": {},
        "period_transition_y": "flat",
        "period_transition_q": "flat",
        "period_transition_m": "flat",
        "period_transition_w": "flat",
        "period_transition_d": "flat",
    }


def formal_baseline(period: str, **period_values: object) -> dict[str, object]:
    values = {
        "trigger_previous_entity_high": 117,
        "trigger_previous_entity_low": 108.55,
        "previous_avg_amount": 1,
        "trigger_previous_amount_baseline": 2_948_974.34197,
        "previous_transition": "flat",
        **period_values,
    }
    return {"baseline_version": "test", "periods": {period: values}}


def ordinary_buy_context_row(identity_key: str, condition_key: str) -> dict[str, object]:
    periods = [part.strip() for part in condition_key.split(":", 1)[1].split(",")]
    row = context_row(identity_key, "buy", condition_key, ["B_BUY", "B_BUY_30M_VOL"])
    row["condition_periods"] = periods
    baseline_periods: dict[str, dict[str, object]] = {}
    for period in periods:
        baseline_periods[period] = {
            "trigger_previous_entity_high": 117,
            "trigger_previous_entity_low": 108.55,
            "previous_avg_amount": 1000 if period == "D" else 1500,
            "previous_amount_unit": "yuan",
            "previous_transition": "flat",
        }
    row["period_trigger_baseline_json"] = {"baseline_version": "test", "periods": baseline_periods}
    return row


def ordinary_buy_metric(
    identity_key: str,
    *,
    metric_id: int,
    minute_label: str,
    current_price: object,
    monthly_avg: object = 900,
) -> dict[str, object]:
    metric = metric_row(
        "stock",
        identity_key,
        buy_30m_price_pass=True,
        buy_5m_amount_pass=True,
        current_30m_virtual_amount=220,
        previous_day_same_window_amount=100,
    )
    amount_trace = n3_standard_formal_amount_proof_trace("D", "M")
    amount_trace["formal_period_amount_proof"]["amount_chain_metrics"].update(  # type: ignore[index]
        {
            "today_virt_amount": 1200,
            "weekly_avg_with_today": 1100,
            "prev_weekly_avg": 1000,
            "monthly_avg_with_today": monthly_avg,
            "prev_monthly_avg": 900,
            "quarterly_avg_with_today": 800,
            "prev_quarterly_avg": 700,
        }
    )
    metric.update(
        {
            "action_confirmation_metric_id": metric_id,
            "source_snapshot_event_id": f"evt-{identity_key}-{minute_label}",
            "metric_time": f"2026-06-02T{minute_label}:00+08:00",
            "metric_minute_label": minute_label,
            "current_price": current_price,
            "today_virt_amount": 1200,
            "weekly_avg_with_today": 1100,
            "prev_weekly_avg": 1000,
            "monthly_avg_with_today": monthly_avg,
            "prev_monthly_avg": 900,
            "quarterly_avg_with_today": 800,
            "prev_quarterly_avg": 700,
            "trace_json": amount_trace,
        }
    )
    return metric


def n3_standard_formal_amount_proof_trace(*periods: str) -> dict[str, object]:
    previous_avg_amount_yuan = {
        "D": 1000,
        "W": 1000,
        "M": 900,
        "Q": 800,
        "Y": 700,
    }
    return {
        "formal_period_amount_proof": {
            "source_kind": "N3_standard_period_metric",
            "amount_unit": "yuan",
            "unit_conversion_policy": "formal_amount_chain_thousand_yuan_to_yuan_v1",
            "amount_chain_metrics": {
                "today_virt_amount": 1200,
                "weekly_avg_with_today": 1100,
                "prev_weekly_avg": 1000,
                "monthly_avg_with_today": 1000,
                "prev_monthly_avg": 900,
                "quarterly_avg_with_today": 900,
                "prev_quarterly_avg": 800,
                "yearly_avg_with_today": 800,
                "prev_yearly_avg": 700,
            },
            "periods": {
                period: {
                    "current_amount_source_kind": "N3_standard_period_metric",
                    "current_amount_unit": "yuan",
                    "current_price_field": "current_price",
                    "amount_rule": "attachment_dwmqy_avg_chain",
                    "unit_conversion_policy": "formal_amount_chain_thousand_yuan_to_yuan_v1",
                    "previous_avg_amount_yuan": previous_avg_amount_yuan.get(period),
                    "previous_amount_yuan": previous_avg_amount_yuan.get(period),
                }
                for period in periods
            },
        }
    }


def n3_true_full_day_minute_formal_amount_proof_trace(*periods: str) -> dict[str, object]:
    current_amount_fields = {
        "D": "current_d_virtual_amount",
        "W": "current_w_virtual_amount",
        "M": "current_m_virtual_amount",
        "Q": "current_q_virtual_amount",
        "Y": "current_y_virtual_amount",
    }
    return {
        "formal_period_amount_proof": {
            "policy": "current_D/W/M/Q/Y_virtual_amount_from_n2_period_context_plus_intraday_1m",
            "source_kind": "N3_standard_period_metric",
            "amount_unit": "yuan",
            "proof_version": "v3.n3.formal_period_amount_source.v1",
            "snapshot_amount_promoted": False,
            "periods": {
                period: {
                    "period": period,
                    "period_source": "n2_period_context_plus_intraday_1m",
                    "current_amount_unit": "yuan",
                    "current_amount_field": current_amount_fields[period],
                    "current_amount_source_kind": "N3_standard_period_metric",
                    "source_field_trace": {
                        "current_amount_field": current_amount_fields[period],
                    },
                }
                for period in periods
            },
        },
        "formal_amount_chain_metrics": {
            "current_d_virtual_amount": 1200,
            "current_w_virtual_amount": 1100,
            "previous_w_amount": 1000,
            "current_m_virtual_amount": 1000,
            "previous_m_amount": 900,
            "current_q_virtual_amount": 900,
            "previous_q_amount": 800,
            "current_y_virtual_amount": 800,
            "previous_y_amount": 700,
        },
    }


def n3_formal_amount_proof_v1_trace(periods: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "formal_period_amount_proof": {
            "amount_unit": "yuan",
            "source_kind": "N3_standard_period_metric",
            "unit_conversion_policy": "stock_thousand_yuan_to_yuan_else_native_yuan_v1",
            "periods": {
                period: {
                    "period": period,
                    "status": "passed",
                    "amount_unit": "yuan",
                    **values,
                }
                for period, values in periods.items()
            },
        }
    }


def formal_buy_plan_for_period(
    *,
    period: str,
    identity_key: str,
    amount_values: dict[str, object],
    trace: dict[str, object] | None = None,
    metric_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    metric = metric_row(
        "stock",
        identity_key,
        buy_30m_price_pass=True,
        buy_5m_amount_pass=True,
        current_30m_virtual_amount=220,
        previous_day_same_window_amount=100,
    )
    proof_trace = trace or n3_standard_formal_amount_proof_trace(period)
    proof_trace["formal_period_amount_proof"]["amount_chain_metrics"].update(amount_values)  # type: ignore[index]
    metric.update(amount_values)
    if metric_overrides:
        metric.update(metric_overrides)
    metric.update(
        {
            "current_price": 121,
            "trace_json": proof_trace,
        }
    )
    row = context_row(identity_key, "buy", f"BUY:{period}", ["B_BUY", "B_BUY_30M_VOL"])
    row["period_trigger_baseline_json"] = formal_baseline(
        period,
        trigger_previous_entity_high=117,
        trigger_previous_entity_low=108.55,
    )
    return build_action_confirmation_metric_plans(
        trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
        projection_run_id=DEFAULT_PROJECTION_RUN_ID,
        source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
        source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
        source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
        for_trade_date=DEFAULT_FOR_TRADE_DATE,
        context_rows=[row],
        metric_rows=[metric],
    )[0]


def formal_sell_plan_for_period(
    *,
    period: str,
    identity_key: str,
    metric_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    trace = n3_standard_formal_amount_proof_trace(period)
    metric_values: dict[str, object] = {}
    if period == "Y":
        trace["formal_period_amount_proof"]["amount_chain_metrics"]["yearly_avg_with_today"] = 600  # type: ignore[index]
        trace["formal_period_amount_proof"]["amount_chain_metrics"]["prev_yearly_avg"] = 700  # type: ignore[index]
        metric_values.update({"yearly_avg_with_today": 600, "prev_yearly_avg": 700})
    metric = metric_row(
        "stock",
        identity_key,
        sell_30m_price_pass=True,
        sell_5m_amount_pass=True,
        current_30m_virtual_amount=80,
        previous_day_same_window_amount=100,
    )
    metric.update(
        {
            "current_price": 107,
            "trace_json": trace,
            **metric_values,
        }
    )
    if metric_overrides:
        metric.update(metric_overrides)
    row = context_row(identity_key, "sell", f"SELL:{period}", ["S_SELL", "S_SELL_30M_SHRINK"])
    row["period_trigger_baseline_json"] = formal_baseline(
        period,
        trigger_previous_entity_high=117,
        trigger_previous_entity_low=108.55,
    )
    return build_action_confirmation_metric_plans(
        trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
        projection_run_id=DEFAULT_PROJECTION_RUN_ID,
        source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
        source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
        source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
        for_trade_date=DEFAULT_FOR_TRADE_DATE,
        context_rows=[row],
        metric_rows=[metric],
    )[0]


def full_scope_condition_row(
    condition_key: str,
    direction: str,
    runtime_signal_type: str,
    allowed_signal_types: list[str],
    *,
    is_hint_scope: bool,
) -> dict[str, object]:
    canonical_condition_type = condition_key if is_hint_scope else condition_key.split(":", 1)[0]
    return {
        "direction": direction,
        "condition_key": condition_key,
        "is_hint_scope": is_hint_scope,
        "source_scope_id": 153978,
        "runtime_signal_type": runtime_signal_type,
        "allowed_signal_types": allowed_signal_types,
        "canonical_condition_type": canonical_condition_type,
        "source_condition_pool_id": 167233,
    }


def metric_row(
    asset_kind: str,
    identity_key: str,
    *,
    metric_ready: bool = True,
    metric_quality_status: str = "passed",
    buy_30m_price_pass: bool = False,
    buy_5m_amount_pass: bool = False,
    sell_30m_price_pass: bool = False,
    sell_5m_amount_pass: bool = False,
    current_30m_virtual_amount: object = 200,
    previous_day_same_window_amount: object = 100,
    previous_30m_full_amount: object = 90,
    metric_policy: object = "previous_day_same_window_elapsed_ratio_v1",
    projection_schema_version: str = "n3.action_confirmation_metric.v1",
) -> dict[str, object]:
    return {
        "action_confirmation_metric_id": 1001,
        "projection_run_id": DEFAULT_PROJECTION_RUN_ID,
        "projection_schema_version": projection_schema_version,
        "source_condition_run_id": DEFAULT_SOURCE_CONDITION_RUN_ID,
        "source_subscription_run_id": DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
        "source_snapshot_run_id": DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
        "source_snapshot_id": 2001,
        "source_snapshot_event_id": f"evt-{identity_key}",
        "source_today_minute_run_id": "today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
        "source_previous_day_minute_run_id": "previous_day_minute_preload_20260602_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
        "for_trade_date": DEFAULT_FOR_TRADE_DATE,
        "trade_date": DEFAULT_FOR_TRADE_DATE,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "metric_time": "2026-06-02T11:05:00+08:00",
        "metric_minute_label": "11:05",
        "current_price": 10.5,
        "current_price_source": "realtime_daily_snapshot",
        "current_price_time": "2026-06-02T11:05:00+08:00",
        "previous_120m_body_high": 10.0,
        "previous_120m_body_low": 9.8,
        "previous_30m_body_high": 10.2,
        "previous_30m_body_low": 10.0,
        "previous_5m_body_high": 10.3,
        "previous_5m_body_low": 10.1,
        "previous_1m_body_high": 10.4,
        "previous_1m_body_low": 10.2,
        "current_1m_amount": 1000,
        "previous_1m_amount": 900,
        "current_5m_virtual_amount": 5000,
        "previous_5m_full_amount": 4500,
        "current_30m_virtual_amount": current_30m_virtual_amount,
        "previous_day_same_window_amount": previous_day_same_window_amount,
        "previous_30m_full_amount": previous_30m_full_amount,
        "virtual_amount_policy_version": "previous_day_same_window_elapsed_ratio_v1",
        "metric_policy": metric_policy,
        "today_virt_amount": 1200,
        "weekly_avg_with_today": 1100,
        "prev_weekly_avg": 1000,
        "monthly_avg_with_today": 1000,
        "prev_monthly_avg": 900,
        "quarterly_avg_with_today": 900,
        "prev_quarterly_avg": 800,
        "yearly_avg_with_today": 800,
        "prev_yearly_avg": 700,
        "is_first_1m_of_day": False,
        "is_first_5m_of_day": False,
        "is_first_30m_of_day": False,
        "is_first_120m_of_day": True,
        "first_1m_amount_default_pass": False,
        "first_5m_amount_default_pass": False,
        "previous_1m_period_source": "same_trade_date_previous_period",
        "previous_5m_period_source": "same_trade_date_previous_period",
        "previous_30m_period_source": "same_trade_date_previous_period",
        "previous_120m_period_source": "previous_trade_date_last_period",
        "boundary_policy_version": "n3.action_confirmation_boundary.v1",
        "buy_120m_price_pass": True,
        "buy_30m_price_pass": buy_30m_price_pass,
        "buy_5m_price_pass": True,
        "buy_5m_amount_pass": buy_5m_amount_pass,
        "buy_1m_price_pass": True,
        "buy_1m_amount_pass": True,
        "sell_120m_price_pass": True,
        "sell_30m_price_pass": sell_30m_price_pass,
        "sell_5m_price_pass": True,
        "sell_5m_amount_pass": sell_5m_amount_pass,
        "sell_1m_price_pass": True,
        "sell_1m_amount_pass": True,
        "metric_quality_status": metric_quality_status,
        "metric_ready": metric_ready,
        "source_fact_ids": {"snapshot_id": 2001},
        "source_minute_refs": [{"bar_id": 1}],
        "previous_day_minute_refs": [{"bar_id": 2}],
        "raw_json": {},
    }


def guard_counts() -> dict[str, dict[str, object]]:
    return {
        "common_event_inbox": {"exists": True, "row_count": 10, "status": "present"},
        "common_event_consumer_checkpoint": {"exists": True, "row_count": 20, "status": "present"},
        "common_trigger_state": {"exists": True, "row_count": 30, "status": "present"},
        "common_trigger_match": {"exists": True, "row_count": 40, "status": "present"},
        "common_event_outbox": {"exists": True, "row_count": 50, "status": "present"},
    }


def sample_action_confirmation_report(
    *,
    would_trigger_count: int = 1,
    would_pending_count: int = 1,
) -> dict[str, object]:
    context_rows = []
    metric_rows = []
    for idx in range(would_trigger_count):
        identity_key = f"stock:SH:60{idx:04d}"
        context_rows.append(context_row(identity_key, "buy", "BUY_HINT", ["BUY_HINT"]))
        metric_rows.append(
            metric_row(
                "stock",
                identity_key,
                buy_30m_price_pass=True,
                buy_5m_amount_pass=True,
            )
        )
    for idx in range(would_pending_count):
        identity_key = f"stock:SH:61{idx:04d}"
        context_rows.append(context_row(identity_key, "sell", "SELL_HINT", ["SELL_HINT"]))
        metric_rows.append(
            metric_row(
                "stock",
                identity_key,
                sell_30m_price_pass=False,
                sell_5m_amount_pass=True,
            )
        )
    return build_action_confirmation_metric_dry_run_report(
        trigger_context_run_id=DEFAULT_TRIGGER_CONTEXT_RUN_ID,
        projection_run_id=DEFAULT_PROJECTION_RUN_ID,
        source_condition_run_id=DEFAULT_SOURCE_CONDITION_RUN_ID,
        source_subscription_run_id=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
        source_snapshot_run_id=DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
        for_trade_date=DEFAULT_FOR_TRADE_DATE,
        trigger_run={"run_id": DEFAULT_TRIGGER_CONTEXT_RUN_ID, "status": "passed"},
        context_rows=context_rows,
        metric_rows=metric_rows,
        before_row_counts=guard_counts(),
        after_row_counts=guard_counts(),
    )


def clean_execute_baseline() -> dict[str, int]:
    return {
        "execute_run_common_trigger_run": 0,
        "execute_run_quality": 0,
        "execute_run_state": 0,
        "execute_run_match": 0,
        "execute_run_outbox": 0,
        "execute_run_outbox_delivered_or_delivering": 0,
        "execute_run_inbox": 0,
        "execute_run_checkpoint_refs": 0,
        "downstream_inbox_for_execute_run": 0,
        "downstream_checkpoint_refs": 0,
        "n5_action_run_refs": 0,
    }


def severity_count(items: list[dict[str, object]], severity: str) -> int:
    return sum(1 for item in items if item.get("severity") == severity and item.get("status") != "passed")


if __name__ == "__main__":
    unittest.main()
