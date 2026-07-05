import inspect
import unittest

from ashare_v3.trigger import provisional_projection_matcher
from ashare_v3.trigger.provisional_ordinary_matcher import (
    adapt_n3p_metric_row_for_rule_v4,
    build_provisional_ordinary_matcher_dry_run_report,
    build_provisional_ordinary_matcher_plans,
    summarize_provisional_ordinary_matcher_plans,
)
from tests.test_trigger_projection_matcher import CONTEXT_RUN_ID, context_row, stable_int


N3P_RUN_ID = (
    "realtime_action_confirmation_metric_20260624_until_1352__asset_all__"
    "market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1"
)


class ProvisionalOrdinaryMatcherTest(unittest.TestCase):
    def test_buy_sell_and_full_conditions_match_from_n3p_metric_rows(self) -> None:
        context_rows = [
            context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
            context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"]),
            context_row("stock:SH:600002", "buy", "BUY:FULL", ["BUY:FULL"]),
            context_row("stock:SH:600003", "sell", "SELL:FULL", ["SELL:FULL"]),
        ]
        metric_rows = [
            n3p_metric_row("stock", "stock:SH:600000", direction="buy"),
            n3p_metric_row("stock", "stock:SH:600001", direction="sell"),
            n3p_metric_row("stock", "stock:SH:600002", direction="buy"),
            n3p_metric_row("stock", "stock:SH:600003", direction="sell"),
        ]

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=context_rows,
            metric_rows=metric_rows,
        )
        summary = summarize_provisional_ordinary_matcher_plans(plans)

        self.assertEqual(summary["candidate_count"], 4)
        self.assertEqual(summary["matched_count"], 4)
        self.assertEqual(summary["matched_by_trigger_type"], {"BUY": 1, "BUY:FULL": 1, "SELL": 1, "SELL:FULL": 1})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        self.assertEqual({plan["source_metric_kind"] for plan in plans}, {"realtime_action_confirmation_metric"})
        self.assertEqual({plan["source_metric_run_id"] for plan in plans}, {N3P_RUN_ID})
        self.assertEqual({plan["trigger_mark_candidate"] for plan in plans}, {"normal"})
        self.assertTrue(all(plan["provisional"] is True for plan in plans))
        self.assertTrue(all(plan["selected_metric_id"] is not None for plan in plans))
        self.assertTrue(all(plan["selected_metric_time"] == "2026-06-24T13:52:00+08:00" for plan in plans))
        self.assertTrue(all(plan["metric_minute_label"] == "13:52" for plan in plans))
        self.assertTrue(all(plan["rule_eval_result"]["output_event_type"] == "TriggerMatched" for plan in plans))
        self.assertTrue(all(plan["candidate_trigger_identity_key"] for plan in plans))

    def test_full_conditions_match_current_state_without_transition_upgrade(self) -> None:
        buy_context = context_row("stock:SH:600002", "buy", "BUY:FULL", ["BUY:FULL"])
        sell_context = context_row("stock:SH:600003", "sell", "SELL:FULL", ["SELL:FULL"])
        buy_context["period_trigger_baseline_json"]["periods"]["D"]["previous_transition"] = "volume_up"
        sell_context["period_trigger_baseline_json"]["periods"]["D"]["previous_transition"] = "low_volume_down"

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[buy_context, sell_context],
            metric_rows=[
                n3p_metric_row("stock", "stock:SH:600002", direction="buy"),
                n3p_metric_row("stock", "stock:SH:600003", direction="sell"),
            ],
        )

        self.assertEqual({plan["trigger_type"] for plan in plans}, {"BUY:FULL", "SELL:FULL"})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        self.assertEqual({plan["rule_eval_result"]["outcome_classification"] for plan in plans}, {"matched"})

    def test_ordinary_buy_sell_still_need_transition_upgrade(self) -> None:
        buy_context = context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])
        sell_context = context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"])
        buy_context["period_trigger_baseline_json"]["periods"]["D"]["previous_transition"] = "volume_up"
        sell_context["period_trigger_baseline_json"]["periods"]["D"]["previous_transition"] = "low_volume_down"

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[buy_context, sell_context],
            metric_rows=[
                n3p_metric_row("stock", "stock:SH:600000", direction="buy"),
                n3p_metric_row("stock", "stock:SH:600001", direction="sell"),
            ],
        )

        self.assertEqual({plan["trigger_type"] for plan in plans}, {"BUY", "SELL"})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {None})
        self.assertEqual({plan["rule_eval_result"]["outcome_classification"] for plan in plans}, {"no_op"})

    def test_buy_hint_and_sell_hint_are_isolated_from_ordinary_matcher(self) -> None:
        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"]),
                context_row("stock:SH:600001", "sell", "SELL_HINT", ["SELL_HINT"]),
                context_row("stock:SH:600002", "buy", "BUY:D", ["BUY"]),
            ],
            metric_rows=[
                n3p_metric_row("stock", "stock:SH:600000", direction="buy"),
                n3p_metric_row("stock", "stock:SH:600001", direction="sell"),
                n3p_metric_row("stock", "stock:SH:600002", direction="buy"),
            ],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["condition_key"], "BUY:D")
        self.assertNotIn("BUY_HINT", {plan["condition_key"] for plan in plans})
        self.assertNotIn("SELL_HINT", {plan["condition_key"] for plan in plans})

    def test_n3p_json_condition_grain_lineage_selects_matching_metric(self) -> None:
        buy_context = context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])
        sell_context = context_row("stock:SH:600000", "sell", "SELL:D", ["SELL"])
        buy_metric = n3p_metric_row("stock", "stock:SH:600000", direction="buy")
        sell_metric = n3p_metric_row("stock", "stock:SH:600000", direction="sell")
        add_condition_grain_lineage(buy_metric, buy_context)
        add_condition_grain_lineage(sell_metric, sell_context)

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[buy_context, sell_context],
            metric_rows=[buy_metric, sell_metric],
        )

        self.assertEqual(len(plans), 2)
        selected_by_condition = {plan["condition_key"]: plan["selected_metric_id"] for plan in plans}
        self.assertEqual(selected_by_condition["BUY:D"], buy_metric["action_confirmation_metric_id"])
        self.assertEqual(selected_by_condition["SELL:D"], sell_metric["action_confirmation_metric_id"])
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})

    def test_n3p_json_condition_grain_lineage_does_not_fallback_to_identity(self) -> None:
        buy_context = context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])
        sell_context = context_row("stock:SH:600000", "sell", "SELL:D", ["SELL"])
        sell_metric = n3p_metric_row("stock", "stock:SH:600000", direction="sell")
        add_condition_grain_lineage(sell_metric, sell_context)

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[buy_context, sell_context],
            metric_rows=[sell_metric],
        )

        plan_by_condition = {plan["condition_key"]: plan for plan in plans}
        self.assertIsNone(plan_by_condition["BUY:D"]["selected_metric_id"])
        self.assertIsNone(plan_by_condition["BUY:D"]["output_event_type"])
        self.assertEqual(plan_by_condition["SELL:D"]["selected_metric_id"], sell_metric["action_confirmation_metric_id"])
        self.assertEqual(plan_by_condition["SELL:D"]["output_event_type"], "TriggerMatched")

    def test_unclosed_minute_can_match_but_preserves_is_closed_false(self) -> None:
        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            metric_rows=[n3p_metric_row("stock", "stock:SH:600000", direction="buy", is_closed_1m=False)],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertFalse(plans[0]["is_closed_1m"])
        self.assertFalse(plans[0]["rule_proof"]["selected_metric"]["is_closed_1m"])

    def test_live_current_1m_source_mode_is_preserved_for_n4p_payload(self) -> None:
        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            metric_rows=[
                n3p_metric_row(
                    "stock",
                    "stock:SH:600000",
                    direction="buy",
                    is_closed_1m=False,
                    source_mode="live_current_1m",
                    c1_dependency=False,
                )
            ],
        )

        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["source_mode"], "live_current_1m")
        self.assertFalse(plans[0]["c1_dependency"])
        self.assertEqual(plans[0]["trace"]["source_mode"], "live_current_1m")
        self.assertFalse(plans[0]["trace"]["c1_dependency"])

    def test_adapter_reuses_rule_v4_input_shape_without_b2_projection_metric(self) -> None:
        metric = n3p_metric_row("stock", "stock:SH:600000", direction="buy")
        adapted = adapt_n3p_metric_row_for_rule_v4(
            metric,
            context_row=context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
        )

        self.assertEqual(adapted["projection_run_id"], N3P_RUN_ID)
        self.assertEqual(adapted["current_price_or_close"], "10.50")
        self.assertEqual(adapted["current_amount_metric_source_kind"], "N3_standard_period_metric")
        self.assertEqual(adapted["trigger_amount_chain_pass"], {"D": True})
        self.assertEqual(adapted["projection_30m_type"], "none")
        self.assertEqual(adapted["source_metric_kind"], "realtime_action_confirmation_metric")

    def test_adapter_reads_n3p_formal_amount_proof_for_multi_period_chain(self) -> None:
        context = context_row("stock:SH:600000", "buy", "BUY:Y,Q,M,W,D", ["BUY"])
        metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            trigger_amount_chain_pass=None,
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("Y", "Q", "M", "W", "D"),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
            ),
        )
        metric["current_d_virtual_amount"] = 999.0

        adapted = adapt_n3p_metric_row_for_rule_v4(metric, context_row=context)

        self.assertEqual(adapted["current_amount_metric_unit"], "yuan")
        self.assertEqual(adapted["amount_unit"], "yuan")
        self.assertEqual(adapted["current_amount_metric_source_kind"], "N3_standard_period_metric")
        self.assertEqual(adapted["today_virt_amount"], 150.0)
        self.assertEqual(adapted["weekly_avg_with_today"], 150.0)
        self.assertEqual(adapted["monthly_avg_with_today"], 150.0)
        self.assertEqual(adapted["quarterly_avg_with_today"], 150.0)
        self.assertEqual(adapted["yearly_avg_with_today"], 150.0)
        self.assertEqual(
            adapted["trigger_amount_chain_pass"],
            {"Y": "not_applicable", "Q": True, "M": True, "W": True, "D": True},
        )
        self.assertEqual(adapted["trigger_amount_chain_pass"]["Y"], "not_applicable")

    def test_adapter_does_not_infer_formal_unit_without_trusted_formal_proof(self) -> None:
        context = context_row("stock:SH:600000", "buy", "BUY:Y,Q,M,W,D", ["BUY"])
        metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            trigger_amount_chain_pass=None,
            include_amount_unit_fields=False,
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("Y", "Q", "M", "W", "D"),
                amount_unit=None,
                source_kind=None,
                amount_pass=True,
            ),
        )

        adapted = adapt_n3p_metric_row_for_rule_v4(metric, context_row=context)

        self.assertIsNone(adapted.get("current_amount_metric_unit"))
        self.assertIsNone(adapted.get("amount_unit"))
        self.assertNotEqual(adapted.get("current_amount_metric_source_kind"), "N3_standard_period_metric")
        self.assertEqual(adapted["trigger_amount_chain_pass"], {})

    def test_multi_period_formal_amount_proof_allows_rule_v4_match(self) -> None:
        context = context_row("stock:SH:600000", "buy", "BUY:Y,Q,M,W,D", ["BUY"])
        metric = n3p_metric_row(
            "stock",
            "stock:SH:600000",
            direction="buy",
            trigger_amount_chain_pass=None,
            formal_period_amount_proof=formal_period_amount_proof_factory(
                periods=("Y", "Q", "M", "W", "D"),
                amount_unit="yuan",
                source_kind="N3_standard_period_metric",
                amount_pass=True,
            ),
        )

        plans = build_provisional_ordinary_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context],
            metric_rows=[metric],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["triggered_periods"], ["Y", "Q", "M", "W", "D"])
        self.assertEqual(
            plans[0]["rule_proof"]["period_evaluation_details"][0]["trigger_amount_chain_pass"],
            "not_applicable",
        )

    def test_dry_run_report_has_required_side_effect_guard(self) -> None:
        report = build_provisional_ordinary_matcher_dry_run_report(
            trigger_context_run_id=CONTEXT_RUN_ID,
            source_metric_run_id=N3P_RUN_ID,
            context_rows=[context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"])],
            metric_rows=[n3p_metric_row("stock", "stock:SH:600000", direction="buy")],
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["summary"]["matched_count"], 1)
        self.assertFalse(report["side_effect_guard"]["db_written"])
        self.assertFalse(report["side_effect_guard"]["outbox_written"])
        self.assertFalse(report["side_effect_guard"]["inbox_written"])
        self.assertFalse(report["side_effect_guard"]["checkpoint_written"])
        self.assertFalse(report["side_effect_guard"]["n5_executed"])
        self.assertFalse(report["side_effect_guard"]["n6_written"])
        self.assertFalse(report["side_effect_guard"]["sim_trade_virtual_written"])

    def test_rule_reuse_and_b2_hint_module_isolation_static_guard(self) -> None:
        import ashare_v3.trigger.provisional_ordinary_matcher as ordinary_matcher

        module_source = inspect.getsource(ordinary_matcher)
        b2_module_source = inspect.getsource(provisional_projection_matcher)

        self.assertIn("evaluate_v4_plan", module_source)
        self.assertNotIn("stock_realtime_projection_metric", module_source)
        self.assertNotIn("index_realtime_projection_metric", module_source)
        self.assertNotIn("board_realtime_projection_metric", module_source)
        self.assertNotIn("common_event_outbox", module_source)
        self.assertNotIn("common_event_inbox", module_source)
        self.assertIn("build_provisional_projection_matcher_plans", b2_module_source)


def n3p_metric_row(
    asset_kind: str,
    identity_key: str,
    *,
    direction: str,
    is_closed_1m: bool = True,
    trigger_amount_chain_pass: dict[str, bool] | None = None,
    formal_period_amount_proof: dict[str, object] | None = None,
    include_amount_unit_fields: bool = True,
    source_mode: str | None = None,
    c1_dependency: bool | None = None,
) -> dict[str, object]:
    price = "10.50" if direction == "buy" else "9.50"
    amount = "150" if direction == "buy" else "50"
    if trigger_amount_chain_pass is None and formal_period_amount_proof is None:
        trigger_amount_chain_pass = {"D": True}
        formal_period_amount_proof = formal_period_amount_proof_factory(
            periods=("D",),
            amount_unit="yuan",
            source_kind="N3_standard_period_metric",
            amount_pass=True,
            amount_value=float(amount),
        )
    row = {
        "action_confirmation_metric_id": stable_int(identity_key + direction + "n3p_metric"),
        "projection_run_id": N3P_RUN_ID,
        "projection_schema_version": "v3.realtime_virtual_metric.writer.v1",
        "source_condition_run_id": "condition_layer_20260623_source_20260623_for_20260624_v1",
        "source_subscription_run_id": "market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
        "source_snapshot_run_id": "realtime_daily_snapshot_20260624_until_1352__market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
        "source_today_minute_run_id": "today_minute_bar_1m_20260624_until_1352__market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
        "source_previous_day_minute_run_id": "previous_day_minute_preload_20260623_for_20260624__market_data_subscription_20260624_condition_layer_20260623_source_20260623_for_20260624_v1",
        "for_trade_date": "20260624",
        "trade_date": "20260624",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "display_code": identity_key.rsplit(":", 1)[-1],
        "name": identity_key,
        "metric_time": "2026-06-24T13:52:00+08:00",
        "metric_time_label": "2026-06-24 13:52",
        "metric_minute_label": "13:52",
        "is_closed_1m": is_closed_1m,
        "metric_ready": True,
        "metric_quality_status": "passed",
        "current_price": price,
        "current_d_virtual_amount": amount,
        "raw_json": {
            "closed_minute_proof": {
                "selected_metric_time": "2026-06-24T13:52:00+08:00",
                "is_closed_1m": is_closed_1m,
            }
        },
        "trace_json": {},
    }
    if source_mode is not None:
        row["raw_json"]["source_mode"] = source_mode
        row["raw_json"]["closed_minute_proof"]["source_mode"] = source_mode
        row["trace_json"]["source_mode"] = source_mode
        row["source_fact_ids"] = {"source_mode": source_mode}
    if c1_dependency is not None:
        row["raw_json"]["c1_dependency"] = c1_dependency
        row["raw_json"]["closed_minute_proof"]["c1_dependency"] = c1_dependency
        row["trace_json"]["c1_dependency"] = c1_dependency
        row.setdefault("source_fact_ids", {})["c1_dependency"] = c1_dependency
    if trigger_amount_chain_pass is not None:
        row["trigger_amount_chain_pass"] = trigger_amount_chain_pass
    if include_amount_unit_fields:
        row["current_amount_metric_unit"] = "yuan"
        row["current_amount_metric_source_kind"] = "N3_standard_period_metric"
    if formal_period_amount_proof is not None:
        row["trace_json"].update(
            {
                "formal_period_amount_proof": formal_period_amount_proof,
                "formal_amount_chain_metrics": formal_period_amount_proof.get("amount_chain_metrics", {}),
            }
        )
    return row


def add_condition_grain_lineage(metric: dict[str, object], context: dict[str, object]) -> None:
    lineage = {
        "source_condition_pool_id": context["source_condition_pool_id"],
        "source_condition_basis_id": context["source_condition_basis_id"],
        "source_minute_target_scope_id": context["source_minute_target_scope_id"],
    }
    metric["raw_json"]["condition_key"] = context["condition_key"]
    metric["raw_json"]["higher_period_context_source"] = dict(lineage)
    metric["raw_json"]["b1_source_returned_payload_selection"] = {
        "selection_policy": "n4_context_condition_grain_expands_b1_object_snapshot",
        "source_condition_pool_id": context["source_condition_pool_id"],
        "source_minute_target_scope_id": context["source_minute_target_scope_id"],
    }
    metric["trace_json"]["higher_period_context_source"] = dict(lineage)


def formal_period_amount_proof_factory(
    *,
    periods: tuple[str, ...],
    amount_unit: str | None,
    source_kind: str | None,
    amount_pass: bool,
    amount_value: float = 150.0,
) -> dict[str, object]:
    return {
        "source_kind": source_kind,
        "amount_unit": amount_unit,
        "amount_chain_metrics": {
            "today_virt_amount": amount_value,
            "weekly_avg_with_today": amount_value,
            "monthly_avg_with_today": amount_value,
            "quarterly_avg_with_today": amount_value,
            "yearly_avg_with_today": amount_value,
        },
        "periods": {
            period: {
                "current_amount_source_kind": source_kind,
                "current_amount_unit": amount_unit,
                "amount_unit": amount_unit,
                "avg_status": "passed",
                "amount_pass": amount_pass,
                "trigger_amount_chain_pass": amount_pass,
            }
            for period in periods
        },
    }


if __name__ == "__main__":
    unittest.main()
