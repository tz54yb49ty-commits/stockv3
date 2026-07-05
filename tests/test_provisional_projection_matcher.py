import inspect
import unittest

from ashare_v3.trigger.provisional_projection_matcher import (
    build_provisional_projection_matcher_plans,
    summarize_provisional_projection_matcher_plans,
)
from tests.test_trigger_projection_matcher import (
    CONTEXT_RUN_ID,
    PROJECTION_RUN_ID,
    context_row,
    direct_30m_projection_row,
    hint_1m_projection_row,
    projection_row,
)


class ProvisionalProjectionMatcherTest(unittest.TestCase):
    def test_ready_buy_and_sell_hint_projection_rows_match(self) -> None:
        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index"),
                context_row("board:TDX:BK001", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board"),
            ],
            projection_rows=[
                projection_row("index", "index:SH:000016", "ready", "up_volume_expanding"),
                projection_row("board", "board:TDX:BK001", "ready", "down_volume_shrinking"),
            ],
        )

        summary = summarize_provisional_projection_matcher_plans(plans)

        self.assertEqual(summary["candidate_count"], 2)
        self.assertEqual(summary["matched_count"], 2)
        self.assertEqual(summary["noop_count"], 0)
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        self.assertEqual({plan["signal_type"] for plan in plans}, {"B_BUY", "S_SELL"})
        self.assertEqual({plan["condition_signal_type"] for plan in plans}, {"BUY_HINT", "SELL_HINT"})
        self.assertEqual({plan["trigger_mark_candidate"] for plan in plans}, {"30m_volume", "30m_shrink"})
        self.assertEqual({plan["projection_30m_type"] for plan in plans}, {"volume_up", "shrink_down"})
        self.assertTrue(all(plan["projection_30m_flag"] is True for plan in plans))
        self.assertTrue(all(plan["projection_run_id"] == PROJECTION_RUN_ID for plan in plans))
        self.assertTrue(all(plan["source_projection_id"] is not None for plan in plans))
        self.assertTrue(all(plan["source_projection_proof_run_id"] == PROJECTION_RUN_ID for plan in plans))
        self.assertTrue(all(plan["source_projection_proof_metric_id"] is not None for plan in plans))
        self.assertTrue(all(plan["source_projection_proof_time"] == "2026-05-25T14:15:00+08:00" for plan in plans))
        self.assertTrue(all(plan["not_n5_final_proof"] is True for plan in plans))
        self.assertTrue(all(plan["projection_trace"]["proof_kind"] == "n3_b2_30m_projection" for plan in plans))

    def test_ready_projection_without_b2_proof_is_pending_market_data(self) -> None:
        projection = projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")
        projection["source_fact_ids"] = {"closed_label_used": "2026-05-25T14:15:00+08:00"}
        projection["raw_json"] = {
            "projection_signal_status": "up_volume_expanding",
            "latest_price": "10.50",
            "current_30m_virtual_amount": "120",
            "reference_30m_amount": "100",
        }
        for key in (
            "metric_role",
            "proof_owner",
            "proof_consumer",
            "proof_kind",
            "not_n5_final_proof",
            "frequency",
        ):
            projection.pop(key, None)

        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            projection_rows=[projection],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["plan_status"], "pending_market_data")
        self.assertEqual(plans[0]["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plans[0]["projection_30m_type"], "unknown")
        self.assertFalse(plans[0]["projection_30m_flag"])
        self.assertFalse(plans[0]["n5_entry_allowed"])
        self.assertIn("missing standard N3 hint projection proof", plans[0]["dry_run_reason"])

    def test_ready_direct_30m_projection_matches_without_b1_snapshot(self) -> None:
        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index"),
                context_row("board:TDX:BK001", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board"),
            ],
            projection_rows=[
                direct_30m_projection_row("index", "index:SH:000016", "ready", "up_volume_expanding"),
                direct_30m_projection_row("board", "board:TDX:BK001", "ready", "down_volume_shrinking"),
            ],
        )

        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})
        by_asset = {plan["asset_kind"]: plan for plan in plans}
        self.assertEqual(by_asset["index"]["projection_trace"]["source_30m_k_adapter_method"], "index")
        self.assertEqual(by_asset["board"]["projection_trace"]["source_30m_k_adapter_method"], "index")
        for plan in plans:
            self.assertEqual(plan["projection_trace"]["source_mode"], "direct_30m_k")
            self.assertEqual(plan["projection_trace"]["source_30m_k_run_id"], "direct_30m_k_source_20260525_until_1415")
            self.assertTrue(plan["not_n5_final_proof"])

    def test_index_board_hint_1m_projection_v2_matches_and_stock_is_not_applicable(self) -> None:
        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index"),
                context_row("board:TDX:BK001", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board"),
                context_row("stock:SH:600000", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="stock"),
            ],
            projection_rows=[
                hint_1m_projection_row("index", "index:SH:000016", "volume_up"),
                hint_1m_projection_row("board", "board:TDX:BK001", "shrink_down"),
                hint_1m_projection_row("stock", "stock:SH:600000", "volume_up"),
            ],
        )

        matched = [plan for plan in plans if plan["output_event_type"] == "TriggerMatched"]
        noop = [plan for plan in plans if plan["plan_status"] == "no_op"]

        self.assertEqual(len(matched), 2)
        self.assertEqual({plan["asset_kind"] for plan in matched}, {"index", "board"})
        self.assertEqual({plan["projection_proof_kind"] for plan in matched}, {"index_board_1m_hint_projection_v1"})
        self.assertEqual({plan["projection_trace"]["proof_kind"] for plan in matched}, {"index_board_1m_hint_projection_v1"})
        self.assertEqual({plan["source_hint_projection_run_id"] for plan in matched}, {PROJECTION_RUN_ID})
        self.assertTrue(all(plan["source_hint_projection_metric_id"] for plan in matched))
        self.assertEqual({plan["source_hint_projection_time"] for plan in matched}, {"1415"})
        self.assertEqual({plan["source_hint_projection_proof_kind"] for plan in matched}, {"index_board_1m_hint_projection_v1"})
        self.assertEqual(len(noop), 1)
        self.assertEqual(noop[0]["asset_kind"], "stock")
        self.assertEqual(noop[0]["current_status"], "no_op")
        self.assertIn("stock HINT is not applicable", noop[0]["dry_run_reason"])

    def test_hint_v2_hhmm_metric_label_uses_iso_proof_time_for_event_time(self) -> None:
        projection = hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")
        proof_time = "2026-06-30T11:07:00+08:00"
        projection["metric_minute_label"] = "1107"
        projection["raw_json"] = {
            **dict(projection["raw_json"]),
            "proof": {
                "source_projection_proof_time": proof_time,
                "proof_input_time": proof_time,
                "proof_input_minute_label": "1107",
            },
        }

        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
            projection_rows=[projection],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["event_time"], proof_time)
        self.assertEqual(plans[0]["trigger_time"], proof_time)
        self.assertEqual(plans[0]["source_projection_proof_time"], proof_time)
        self.assertEqual(plans[0]["projection_trace"]["trigger_time"], proof_time)
        self.assertEqual(plans[0]["projection_trace"]["metric_minute_label"], "1107")

    def test_hint_v2_missing_iso_proof_time_fails_closed(self) -> None:
        projection = hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")
        projection["metric_minute_label"] = "1107"
        projection["raw_json"] = {
            **{key: value for key, value in dict(projection["raw_json"]).items() if key != "proof"},
        }
        projection["trace_json"] = {
            **{key: value for key, value in dict(projection["trace_json"]).items() if key != "proof"},
        }

        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("board:TDX:BK001", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="board")],
            projection_rows=[projection],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["plan_status"], "no_op")
        self.assertIsNone(plans[0]["output_event_type"])
        self.assertFalse(plans[0]["n5_entry_allowed"])
        self.assertIn("missing ISO proof time", plans[0]["dry_run_reason"])

    def test_ready_non_matching_projection_rows_are_noop(self) -> None:
        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index"),
                context_row("board:TDX:BK001", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board"),
            ],
            projection_rows=[
                projection_row("index", "index:SH:000016", "ready", "flat"),
                projection_row("board", "board:TDX:BK001", "ready", "up_volume_expanding"),
            ],
        )

        self.assertEqual({plan["plan_status"] for plan in plans}, {"no_op"})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {None})
        self.assertNotIn("TriggerPendingMarketData", {plan["output_event_type"] for plan in plans})
        self.assertEqual({plan["trigger_mark_candidate"] for plan in plans}, {"normal"})
        self.assertEqual({plan["projection_30m_type"] for plan in plans}, {"none", "volume_up"})

    def test_not_ready_projection_rows_are_pending_market_data(self) -> None:
        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            projection_rows=[projection_row("index", "index:SH:000016", "not_ready", "up_volume_expanding")],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["plan_status"], "pending_market_data")
        self.assertEqual(plans[0]["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plans[0]["projection_status"], "not_ready")
        self.assertEqual(plans[0]["dry_run_reason"], "N3 hint projection row is not ready for provisional matching")
        self.assertFalse(plans[0]["n5_entry_allowed"])

    def test_unknown_projection_amounts_emit_pending_market_data(self) -> None:
        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            projection_rows=[projection_row("index", "index:SH:000016", "ready", "unknown")],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["plan_status"], "pending_market_data")
        self.assertEqual(plans[0]["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plans[0]["projection_30m_type"], "unknown")
        self.assertFalse(plans[0]["projection_30m_flag"])

    def test_legacy_b2_amount_alias_drives_buy_hint_without_signal_status_shortcut(self) -> None:
        projection = projection_row("index", "index:SH:000016", "ready", "unknown")
        projection["projection_signal_status"] = "down_volume_shrinking"
        projection["projected_30m_amount"] = "220"
        projection["previous_day_same_window_amount"] = "100"

        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            projection_rows=[projection],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["projection_30m_type"], "volume_up")
        self.assertEqual(plans[0]["projection_30m_amount_source"], "projected_30m_amount")
        self.assertEqual(plans[0]["projection_30m_reference_source"], "previous_day_same_window_amount")
        self.assertEqual(
            plans[0]["projection_amount_alias_policy"],
            "b2_live_current_legacy_amount_alias_v1",
        )
        self.assertEqual(
            plans[0]["projection_trace"]["projection_30m_amount_source"],
            "projected_30m_amount",
        )
        self.assertEqual(
            plans[0]["projection_trace"]["projection_30m_reference_source"],
            "previous_day_same_window_amount",
        )

    def test_legacy_b2_amount_alias_drives_sell_hint_without_signal_status_shortcut(self) -> None:
        projection = projection_row("board", "board:TDX:BK001", "ready", "unknown")
        projection["projection_signal_status"] = "up_volume_expanding"
        projection["projected_30m_amount"] = "80"
        projection["previous_day_same_window_amount"] = "100"

        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("board:TDX:BK001", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board")],
            projection_rows=[projection],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["projection_30m_type"], "shrink_down")
        self.assertEqual(plans[0]["projection_30m_amount_source"], "projected_30m_amount")
        self.assertEqual(plans[0]["projection_30m_reference_source"], "previous_day_same_window_amount")

    def test_canonical_amount_fields_win_over_legacy_alias_conflict(self) -> None:
        projection = projection_row("index", "index:SH:000016", "ready", "down_volume_shrinking")
        projection["projected_30m_amount"] = "220"
        projection["previous_day_same_window_amount"] = "100"

        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            projection_rows=[projection],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["plan_status"], "no_op")
        self.assertEqual(plans[0]["output_event_type"], None)
        self.assertEqual(plans[0]["projection_30m_type"], "shrink_down")
        self.assertEqual(plans[0]["projection_30m_amount_source"], "current_30m_virtual_amount")
        self.assertEqual(plans[0]["projection_30m_reference_source"], "reference_30m_amount")

    def test_ordinary_and_full_conditions_are_not_processed(self) -> None:
        plans = build_provisional_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
                context_row("stock:SH:600001", "sell", "SELL:FULL", ["SELL:FULL"]),
                context_row("index:SH:000905", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index"),
            ],
            projection_rows=[
                projection_row("index", "index:SH:000905", "ready", "up_volume_expanding"),
                projection_row("board", "board:TDX:BK001", "ready", "down_volume_shrinking"),
                projection_row("stock", "stock:SH:600002", "ready", "up_volume_expanding"),
            ],
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["condition_key"], "BUY_HINT")
        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")

    def test_provisional_matcher_does_not_depend_on_formal_or_execute_routes(self) -> None:
        import ashare_v3.trigger.provisional_projection_matcher as provisional_projection_matcher

        module_source = inspect.getsource(provisional_projection_matcher)

        self.assertNotIn("action_confirmation_projection_metric", module_source)
        self.assertNotIn("common_event_outbox", module_source)
        self.assertNotIn("common_event_inbox", module_source)
        self.assertNotIn("common_event_consumer_checkpoint", module_source)


if __name__ == "__main__":
    unittest.main()
