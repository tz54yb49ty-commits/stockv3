import inspect
import json
import unittest

import ashare_v3.trigger.projection_matcher as projection_matcher
from ashare_v3.trigger.projection_matcher import (
    FORBIDDEN_N4_PROJECTION_MATCHER_READ_TABLES,
    PROJECTION_MATCHER_READ_TABLES,
    build_projection_matcher_dry_run_report,
    build_projection_matcher_plans,
    summarize_projection_matcher_evaluations,
)


CONTEXT_RUN_ID = "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
SYNTHETIC_DENYLIST = (
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute",
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute",
)


class TriggerProjectionMatcherTest(unittest.TestCase):
    def test_ready_projection_matches_only_hint_and_keeps_30m_out_of_formal_periods(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
                context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index"),
                context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"]),
                context_row("board:TDX:BK001", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board"),
            ],
            projection_rows=[
                projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
                projection_row("stock", "stock:SH:600001", "ready", "down_volume_shrinking"),
                projection_row("index", "index:SH:000016", "ready", "up_volume_expanding"),
                projection_row("board", "board:TDX:BK001", "ready", "down_volume_shrinking"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        summary = summarize_projection_matcher_evaluations(evaluations)

        self.assertEqual(summary["matched_count"], 2)
        self.assertEqual(summary["pending_count"], 2)
        self.assertEqual(
            summary["matched_by_signal_type"],
            {
                "B_BUY": 1,
                "S_SELL": 1,
            },
        )
        self.assertEqual(summary["matched_by_trigger_mark_candidate"], {"30m_shrink": 1, "30m_volume": 1})
        self.assertEqual(
            summary["matched_by_legacy_signal_type"],
            {
                "BUY_HINT": 1,
                "SELL_HINT": 1,
            },
        )
        self.assertEqual(summary["canonical_payload_invalid_count"], 0)
        self.assertTrue(all(item["original_condition_key"] == item["condition_key"] for item in evaluations))
        self.assertFalse(any("action_mark" in item for item in evaluations))
        self.assertEqual({item["output_event_type"] for item in evaluations}, {"TriggerMatched", "TriggerPendingMarketData"})
        for item in evaluations:
            self.assertEqual(item["projection_period"], "30m")
            for field in (
                "runtime_signal_type",
                "condition_signal_type",
                "requested_periods",
                "triggered_period_details",
                "price_source",
                "baseline_source",
                "projection_30m_required",
                "projection_30m_volume_up_flag",
                "projection_30m_shrink_down_flag",
            ):
                self.assertIn(field, item)
            self.assertEqual(item["runtime_signal_type"], item["signal_type"])
            self.assertNotIn("action_mark", item)
            self.assertNotEqual(item.get("primary_trigger_period"), "30m")
            self.assertNotIn("30m", item.get("triggered_periods") or [])
            self.assertNotIn("30m", item.get("all_trigger_periods") or [])
        matched = [item for item in evaluations if item["output_event_type"] == "TriggerMatched"]
        self.assertTrue(all(item["trigger_kind"] == "hint" for item in matched))
        self.assertEqual({item["condition_signal_type"] for item in matched}, {"BUY_HINT", "SELL_HINT"})
        self.assertTrue(all(item["requested_periods"] == [] for item in matched))
        self.assertTrue(all(item["triggered_period_details"] == [] for item in matched))
        self.assertTrue(all(item["projection_30m_required"] is True for item in matched))
        self.assertTrue(all(item["trigger_period"] == "30m" for item in matched))
        self.assertTrue(all(item["triggered_periods"] == [] for item in matched))
        self.assertTrue(all(item["all_trigger_periods"] == [] for item in matched))
        self.assertTrue(all(item["primary_trigger_period"] is None for item in matched))
        self.assertTrue(all(item["n5_entry_allowed"] is True for item in matched))
        self.assertTrue(all(item["trigger_price"] == "10.50" for item in matched))
        self.assertTrue(all(item["event_time"] == "2026-05-25T14:15:00+08:00" for item in matched))
        self.assertTrue(all(item["event_time"] == item["projection_trace"]["trigger_time"] for item in matched))
        pending = [item for item in evaluations if item["output_event_type"] == "TriggerPendingMarketData"]
        self.assertFalse(any(item.get("trigger_period") == "30m" for item in pending))

    def test_hint_projection_requires_standard_hint_proof_contract(self) -> None:
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

        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            projection_rows=[projection],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(len(evaluations), 1)
        self.assertEqual(evaluations[0]["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(evaluations[0]["projection_30m_type"], "unknown")
        self.assertFalse(evaluations[0]["projection_30m_flag"])
        self.assertFalse(evaluations[0]["n5_entry_allowed"])
        self.assertIn("missing standard N3 hint projection proof", evaluations[0]["dry_run_reason"])

    def test_hint_projection_accepts_direct_30m_k_lineage_without_b1_snapshot(self) -> None:
        evaluations = build_projection_matcher_plans(
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
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual({item["output_event_type"] for item in evaluations}, {"TriggerMatched"})
        self.assertEqual({item["trigger_mark_candidate"] for item in evaluations}, {"30m_volume", "30m_shrink"})
        by_asset = {item["asset_kind"]: item for item in evaluations}
        self.assertEqual(by_asset["index"]["projection_trace"]["source_30m_k_adapter_method"], "index")
        self.assertEqual(by_asset["board"]["projection_trace"]["source_30m_k_adapter_method"], "index")
        for item in evaluations:
            trace = item["projection_trace"]
            self.assertEqual(trace["source_mode"], "direct_30m_k")
            self.assertEqual(trace["source_30m_k_run_id"], "direct_30m_k_source_20260525_until_1415")
            self.assertNotIn("source_snapshot_run_id", trace)
            self.assertTrue(item["not_n5_final_proof"])

    def test_index_board_hint_1m_projection_v2_matches_and_stock_is_not_applicable(self) -> None:
        evaluations = build_projection_matcher_plans(
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
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        matched = [item for item in evaluations if item["output_event_type"] == "TriggerMatched"]
        noop = [item for item in evaluations if item["plan_status"] == "not_matched"]

        self.assertEqual(len(matched), 2)
        self.assertEqual({item["asset_kind"] for item in matched}, {"index", "board"})
        self.assertEqual({item["projection_proof_kind"] for item in matched}, {"index_board_1m_hint_projection_v1"})
        self.assertEqual({item["projection_trace"]["source_hint_projection_proof_kind"] for item in matched}, {"index_board_1m_hint_projection_v1"})
        self.assertEqual({item["source_hint_projection_run_id"] for item in matched}, {PROJECTION_RUN_ID})
        self.assertTrue(all(item["source_hint_projection_metric_id"] for item in matched))
        self.assertEqual({item["source_hint_projection_time"] for item in matched}, {"1415"})
        self.assertEqual({item["source_hint_projection_proof_kind"] for item in matched}, {"index_board_1m_hint_projection_v1"})
        self.assertEqual(len(noop), 1)
        self.assertEqual(noop[0]["asset_kind"], "stock")
        self.assertEqual(noop[0]["output_event_type"], None)
        self.assertEqual(noop[0]["current_status"], "no_op")
        self.assertIn("stock HINT is not applicable", noop[0]["dry_run_reason"])

    def test_hint_1m_projection_v2_direction_mismatch_is_noop(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("board:TDX:BK001", "sell", "SELL_HINT", ["SELL_HINT"], asset_kind="board")],
            projection_rows=[hint_1m_projection_row("board", "board:TDX:BK001", "volume_up")],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(len(evaluations), 1)
        self.assertEqual(evaluations[0]["output_event_type"], None)
        self.assertEqual(evaluations[0]["projection_30m_type"], "volume_up")
        self.assertEqual(evaluations[0]["trigger_mark_candidate"], "normal")

    def test_direct_30m_k_projection_missing_source_lineage_is_pending_market_data(self) -> None:
        projection = direct_30m_projection_row("index", "index:SH:000016", "ready", "up_volume_expanding")
        for key in (
            "source_30m_k_run_id",
            "source_30m_k_bar_id",
            "source_30m_k_time",
            "source_30m_k_window_start",
            "source_30m_k_window_end",
            "source_30m_k_closed_status",
            "source_30m_k_adapter_method",
        ):
            projection.pop(key, None)
            projection["source_fact_ids"].pop(key, None)
            projection["raw_json"].pop(key, None)

        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[context_row("index:SH:000016", "buy", "BUY_HINT", ["BUY_HINT"], asset_kind="index")],
            projection_rows=[projection],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(len(evaluations), 1)
        self.assertEqual(evaluations[0]["output_event_type"], "TriggerPendingMarketData")
        self.assertFalse(evaluations[0]["projection_proof_valid"])
        self.assertIn("source_30m_k_run_id", evaluations[0]["projection_proof_missing_or_invalid_fields"])

    def test_v4_enrichment_matches_ordinary_buy_sell_formal_periods(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
                context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"]),
            ],
            projection_rows=[
                v4_projection_row("stock", "stock:SH:600000", direction="buy"),
                v4_projection_row("stock", "stock:SH:600001", direction="sell"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(len(evaluations), 2)
        self.assertEqual({item["output_event_type"] for item in evaluations}, {"TriggerMatched"})
        self.assertEqual({item["trigger_kind"] for item in evaluations}, {"trigger"})
        self.assertEqual({item["trigger_period"] for item in evaluations}, {"D"})
        self.assertEqual({item["primary_trigger_period"] for item in evaluations}, {"D"})
        self.assertTrue(all(item["triggered_periods"] == ["D"] for item in evaluations))
        self.assertTrue(all(item["all_trigger_periods"] == ["D"] for item in evaluations))
        self.assertEqual({item["trigger_mark_candidate"] for item in evaluations}, {"normal"})
        self.assertTrue(all(item["n5_entry_allowed"] is True for item in evaluations))
        self.assertTrue(all(item["trigger_price"] is not None for item in evaluations))
        self.assertEqual({item["condition_signal_type"] for item in evaluations}, {"BUY", "SELL"})
        self.assertTrue(all(item["requested_periods"] == ["D"] for item in evaluations))
        self.assertTrue(all(item["triggered_period_details"] for item in evaluations))
        self.assertTrue(all(item["projection_30m_required"] is False for item in evaluations))
        self.assertTrue(all(item["baseline_source"] == "trigger_baseline" for item in evaluations))

    def test_normalize_context_row_preserves_full_context_proof(self) -> None:
        row = context_row("stock:SH:600003", "buy", "BUY:FULL", ["B_BUY", "B_BUY_30M_VOL"])
        row.pop("period_trigger_baseline_json")
        row["raw_json"] = {
            "policy_name": "v13_index_all",
            "period_trigger_baseline_json": period_trigger_baseline_json(),
        }

        normalized = projection_matcher.normalize_context_row(row)

        self.assertEqual(normalized["condition_key"], "BUY:FULL")
        self.assertEqual(normalized["original_condition_key"], "BUY:FULL")
        self.assertEqual(normalized["condition_periods"], ["D"])
        self.assertEqual(normalized["allowed_signal_types"], ["B_BUY", "B_BUY_30M_VOL"])
        self.assertEqual(normalized["period_trigger_baseline_json"]["periods"]["D"]["previous_entity_high"], "10")
        self.assertEqual(normalized["raw_json"]["policy_name"], "v13_index_all")

    def test_full_snapshot_fallback_reaches_whitelist_but_stays_pending_without_standard_period_metric(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600003", "buy", "BUY:FULL", ["B_BUY", "B_BUY_30M_VOL"]),
                context_row("stock:SH:600004", "sell", "SELL:FULL", ["S_SELL", "S_SELL_30M_SHRINK"]),
            ],
            projection_rows=[
                snapshot_projection_row("stock", "stock:SH:600003", price="10.50", amount="150"),
                snapshot_projection_row("stock", "stock:SH:600004", price="9.50", amount="50"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(len(evaluations), 2)
        self.assertEqual({item["output_event_type"] for item in evaluations}, {"TriggerPendingMarketData"})
        self.assertEqual({item["condition_key"] for item in evaluations}, {"BUY:FULL", "SELL:FULL"})
        self.assertEqual({item["trigger_period"] for item in evaluations}, {None})
        self.assertTrue(all(item["triggered_periods"] == [] for item in evaluations))
        self.assertTrue(all(item["primary_trigger_period"] is None for item in evaluations))
        self.assertTrue(all(item["trigger_mark_candidate"] == "normal" for item in evaluations))
        self.assertTrue(all(item["n5_entry_allowed"] is False for item in evaluations))
        self.assertEqual({item["condition_signal_type"] for item in evaluations}, {"BUY:FULL", "SELL:FULL"})
        self.assertTrue(all(item["requested_periods"] == ["D"] for item in evaluations))
        self.assertTrue(all(item["triggered_period_details"] == [] for item in evaluations))
        self.assertTrue(
            all(
                "formal_period_metric_source_not_allowed" in ",".join(item.get("pending_reasons") or [])
                for item in evaluations
            )
        )
        self.assertTrue(all(item["projection_30m_required"] is False for item in evaluations))
        self.assertFalse(any(item.get("blocked_reason") == "full_n2_context_missing" for item in evaluations))

    def test_full_projection_candidate_with_mismatched_original_context_still_blocks(self) -> None:
        row = context_row("stock:SH:600003", "buy", "BUY:FULL", ["B_BUY", "B_BUY_30M_VOL"])
        row["original_condition_key"] = "BUY:D"
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[row],
            projection_rows=[snapshot_projection_row("stock", "stock:SH:600003", price="10.50", amount="150")],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(len(evaluations), 1)
        self.assertEqual(evaluations[0]["output_event_type"], None)
        self.assertEqual(evaluations[0]["blocked_reason"], "full_n2_context_missing")

    def test_snapshot_fallback_does_not_match_formal_without_standard_period_metric(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
                context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"]),
                context_row("stock:SH:600002", "buy", "BUY_HINT", ["BUY_HINT"]),
            ],
            projection_rows=[
                snapshot_projection_row("stock", "stock:SH:600000", price="10.50", amount="150"),
                snapshot_projection_row("stock", "stock:SH:600001", price="9.50", amount="50"),
                snapshot_projection_row("stock", "stock:SH:600002", price="10.50", amount="150"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        matched = [item for item in evaluations if item["output_event_type"] == "TriggerMatched"]
        pending = [item for item in evaluations if item["output_event_type"] == "TriggerPendingMarketData"]
        not_matched = [item for item in evaluations if item["plan_status"] == "not_matched"]

        self.assertEqual(len(matched), 0)
        self.assertEqual(len(pending), 2)
        self.assertEqual(len(not_matched), 1)
        formal_pending = [item for item in pending if item["condition_key"] in {"BUY:D", "SELL:D"}]
        self.assertEqual(len(formal_pending), 2)
        self.assertTrue(all(item["trigger_kind"] == "trigger" for item in formal_pending))
        self.assertTrue(all(item["trigger_period"] is None for item in formal_pending))
        self.assertTrue(all(item["primary_trigger_period"] is None for item in formal_pending))
        self.assertTrue(all(item["trigger_mark_candidate"] == "normal" for item in formal_pending))
        self.assertTrue(
            all(
                "formal_period_metric_source_not_allowed" in ",".join(item.get("pending_reasons") or [])
                for item in formal_pending
            )
        )
        self.assertEqual(not_matched[0]["condition_key"], "BUY_HINT")
        self.assertEqual(not_matched[0]["current_status"], "no_op")
        self.assertIn("stock HINT is not applicable", not_matched[0]["dry_run_reason"])

    def test_dry_run_quality_allows_snapshot_fallback_only_for_formal_triggers(self) -> None:
        report = build_projection_matcher_dry_run_report(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
                context_row("board:TDX:881001", "sell", "SELL:D", ["SELL"], asset_kind="board"),
                context_row("stock:SH:600002", "buy", "BUY_HINT", ["BUY_HINT"]),
            ],
            projection_rows=[
                snapshot_projection_row("stock", "stock:SH:600000", price="10.50", amount="150"),
                snapshot_projection_row("board", "board:TDX:881001", price="9.50", amount="50"),
                snapshot_projection_row("stock", "stock:SH:600002", price="10.50", amount="150"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS", report["quality"]["items"])
        self.assertEqual(report["quality"]["p0_count"], 0, report["quality"]["items"])
        self.assertEqual(report["summary"]["matched_count"], 0)
        self.assertEqual(report["summary"]["pending_count"], 2)
        self.assertEqual(report["summary"]["not_matched_signal_count"], 1)
        self.assertEqual(report["summary"]["matched_by_trigger_mark_candidate"], {})
        self.assertEqual(
            report["summary"]["pending_by_legacy_signal_type"],
            {"BUY:D": 1, "SELL:D": 1},
        )

    def test_ordinary_pending_preserves_formal_period_evidence_without_30m_period(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
            ],
            projection_rows=[],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        self.assertEqual(len(evaluations), 1)
        candidate = evaluations[0]
        self.assertEqual(candidate["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(candidate["trigger_kind"], "trigger")
        self.assertNotEqual(candidate.get("trigger_period"), "30m")
        self.assertNotIn("30m", candidate.get("triggered_periods") or [])
        self.assertNotIn("30m", candidate.get("all_trigger_periods") or [])
        period_details = candidate.get("period_evaluation_details") or []
        self.assertEqual([item["period"] for item in period_details], ["D"])
        self.assertEqual(period_details[0]["classification"], "pending")

    def test_ready_only_board_and_bj_not_ready_do_not_match(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("board:TDX:881001", "buy", "BUY:D", ["BUY"], asset_kind="board"),
                context_row("stock:BJ:920045", "sell", "SELL:D", ["SELL"], asset_kind="stock"),
            ],
            projection_rows=[
                projection_row("board", "board:TDX:881001", "not_ready", "unknown"),
                projection_row("stock", "stock:BJ:920045", "not_ready", "unknown"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        summary = summarize_projection_matcher_evaluations(evaluations)

        self.assertEqual(summary["matched_count"], 0)
        self.assertEqual(summary["pending_count"], 2)
        self.assertEqual(summary["pending_by_not_ready_classification"], {"blocked": 1, "warning": 1})
        self.assertEqual(summary["board_not_ready_object_count"], 1)
        self.assertEqual(summary["bj_920xxx_not_ready_object_count"], 1)
        self.assertEqual({item["output_event_type"] for item in evaluations}, {"TriggerPendingMarketData"})

    def test_flat_unknown_and_nonmatching_projection_status_do_not_match(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
                context_row("stock:SH:600001", "buy", "BUY_HINT", ["BUY_HINT"]),
                context_row("stock:SH:600002", "sell", "SELL:D", ["SELL"]),
            ],
            projection_rows=[
                projection_row("stock", "stock:SH:600000", "ready", "flat"),
                projection_row("stock", "stock:SH:600001", "ready", "unknown"),
                projection_row("stock", "stock:SH:600002", "ready", "down_volume_expanding"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        summary = summarize_projection_matcher_evaluations(evaluations)

        self.assertEqual(summary["matched_count"], 0)
        self.assertEqual(summary["pending_count"], 2)
        self.assertEqual(summary["not_matched_signal_count"], 1)
        self.assertEqual(summary["pending_by_projection_signal_status"], {"down_volume_expanding": 1, "flat": 1})
        self.assertEqual(summary["not_matched_by_projection_signal_status"], {"unknown": 1})

    def test_synthetic_denylist_rows_are_excluded_from_input(self) -> None:
        evaluations = build_projection_matcher_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"], run_id=CONTEXT_RUN_ID),
                context_row("stock:SH:600001", "buy", "BUY:D", ["BUY"], run_id=SYNTHETIC_DENYLIST[0]),
            ],
            projection_rows=[
                projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
                projection_row("stock", "stock:SH:600001", "ready", "up_volume_expanding"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
        )

        summary = summarize_projection_matcher_evaluations(evaluations)

        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["matched_count"], 0)
        self.assertEqual(summary["pending_count"], 1)
        self.assertEqual({item["identity_key"] for item in evaluations}, {"stock:SH:600000"})

    def test_dry_run_report_has_no_db_writes_and_no_outbox_consumption(self) -> None:
        report = build_projection_matcher_dry_run_report(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            context_rows=[
                context_row("stock:SH:600000", "buy", "BUY:D", ["BUY"]),
                context_row("stock:SH:600001", "sell", "SELL:D", ["SELL"]),
            ],
            projection_rows=[
                projection_row("stock", "stock:SH:600000", "ready", "up_volume_expanding"),
                projection_row("stock", "stock:SH:600001", "ready", "down_volume_shrinking"),
            ],
            synthetic_denylist=SYNTHETIC_DENYLIST,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["quality"]["p0_count"], 0, report["quality"]["items"])
        self.assertFalse(report["side_effects"]["common_event_outbox_consumed"])
        self.assertFalse(report["side_effects"]["common_event_inbox_written"])
        self.assertFalse(report["side_effects"]["checkpoint_written"])
        self.assertFalse(report["side_effects"]["trigger_match_written"])
        self.assertFalse(report["side_effects"]["trigger_state_written"])
        self.assertFalse(report["side_effects"]["event_outbox_written"])
        self.assertFalse(report["side_effects"]["market_data_pulled"])
        self.assertFalse(report["side_effects"]["worker_started"])
        self.assertNotIn("/Volumes/MacRaid", json.dumps(report, ensure_ascii=False))

    def test_matcher_contract_does_not_read_raw_minutes_or_import_adapters(self) -> None:
        self.assertFalse(set(PROJECTION_MATCHER_READ_TABLES) & set(FORBIDDEN_N4_PROJECTION_MATCHER_READ_TABLES))
        module_source = inspect.getsource(projection_matcher)
        for forbidden in ("mootdx", "tushare", "MarketDataAdapter", "minute_bar_1m"):
            self.assertNotIn(forbidden, module_source)


def context_row(
    identity_key: str,
    direction: str,
    condition_key: str,
    allowed_signal_types: list[str],
    *,
    asset_kind: str = "stock",
    run_id: str = CONTEXT_RUN_ID,
) -> dict[str, object]:
    return {
        "trigger_context_id": stable_int(identity_key + condition_key),
        "run_id": run_id,
        "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
        "source_condition_pool_id": stable_int(identity_key + "pool"),
        "source_condition_basis_id": stable_int(identity_key + "basis"),
        "source_minute_target_scope_id": stable_int(identity_key + "scope"),
        "source_market_subscription_id": stable_int(identity_key + "subscription"),
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": ["D"] if ":" in condition_key else [],
        "allowed_signal_types": allowed_signal_types,
        "is_hint_scope": condition_key in {"BUY_HINT", "SELL_HINT"},
        "context_hash": f"context-{identity_key}-{condition_key}",
        "quality_status": "passed",
        "period_trigger_baseline_json": period_trigger_baseline_json(),
    }


def projection_row(asset_kind: str, identity_key: str, status: str, signal: str) -> dict[str, object]:
    projection_id = stable_int(identity_key + "projection")
    current_30m_virtual_amount = None
    reference_30m_amount = None
    if signal == "up_volume_expanding":
        current_30m_virtual_amount = "120"
        reference_30m_amount = "100"
    elif signal == "down_volume_shrinking":
        current_30m_virtual_amount = "80"
        reference_30m_amount = "100"
    elif signal == "flat":
        current_30m_virtual_amount = "100"
        reference_30m_amount = "100"
    projection_30m_type = {
        "up_volume_expanding": "volume_up",
        "down_volume_shrinking": "shrink_down",
        "flat": "none",
    }.get(signal, "unknown")
    trigger_mark_candidate = {
        "volume_up": "30m_volume",
        "shrink_down": "30m_shrink",
    }.get(projection_30m_type, "normal")
    proof_fields = {
        "metric_role": "projection_trigger_proof",
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "proof_kind": "n3_b2_30m_projection",
        "not_n5_final_proof": True,
        "frequency": "30m",
        "adapter_method": "bars" if asset_kind == "stock" else "index",
        "adapter_frequency": 2,
        "projection_30m_type": projection_30m_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "source_projection_proof_run_id": PROJECTION_RUN_ID,
        "source_projection_proof_metric_id": projection_id,
        "source_projection_proof_time": "2026-05-25T14:15:00+08:00",
    }
    return {
        "projection_id": projection_id,
        "projection_run_id": PROJECTION_RUN_ID,
        "source_snapshot_run_id": (
            "realtime_daily_snapshot_20260525__"
            "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
        ),
        "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "projection_schema_version": "n3.realtime_projection.v1",
        "projection_window_kind": "active_30m_bucket_projection",
        "projection_window_id": "20260525_1400_1430",
        "snapshot_time": "2026-05-25T14:15:00+08:00",
        "latest_price": "10.50",
        "projection_status": status,
        "projection_signal_status": signal,
        "projection_quality_status": "passed" if status == "ready" else "blocked",
        "trace_status": "passed" if status == "ready" else "blocked",
        "snapshot_event_id": f"n3_snapshot_event:{identity_key}",
        "snapshot_id": stable_int(identity_key + "snapshot"),
        "source_fact_ids": {
            "snapshot_event_id": f"n3_snapshot_event:{identity_key}",
            "closed_label_used": "2026-05-25T14:15:00+08:00",
            **proof_fields,
        },
        "current_30m_virtual_amount": current_30m_virtual_amount,
        "reference_30m_amount": reference_30m_amount,
        "projection_30m_type": projection_30m_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "metric_role": proof_fields["metric_role"],
        "proof_owner": proof_fields["proof_owner"],
        "proof_consumer": proof_fields["proof_consumer"],
        "proof_kind": proof_fields["proof_kind"],
        "not_n5_final_proof": True,
        "frequency": "30m",
        "adapter_method": proof_fields["adapter_method"],
        "adapter_frequency": 2,
        "raw_json": {
            "projection_signal_status": signal,
            "latest_price": "10.50",
            "current_30m_virtual_amount": current_30m_virtual_amount,
            "reference_30m_amount": reference_30m_amount,
            **proof_fields,
        },
    }


def direct_30m_projection_row(asset_kind: str, identity_key: str, status: str, signal: str) -> dict[str, object]:
    row = projection_row(asset_kind, identity_key, status, signal)
    adapter_method = "bars" if asset_kind == "stock" else "index"
    direct_fields = {
        "source_mode": "direct_30m_k",
        "required_data_kind": "minute_bar_30m",
        "source_30m_k_run_id": "direct_30m_k_source_20260525_until_1415",
        "source_30m_k_bar_id": stable_int(identity_key + "30m"),
        "source_30m_k_time": "2026-05-25T14:15:00+08:00",
        "source_30m_k_window_start": "2026-05-25T14:00:00+08:00",
        "source_30m_k_window_end": "2026-05-25T14:30:00+08:00",
        "source_30m_k_closed_status": "intraday_projection",
        "source_30m_k_adapter_method": adapter_method,
    }
    row.pop("source_snapshot_run_id", None)
    row.pop("snapshot_id", None)
    row.pop("snapshot_event_id", None)
    row["source_fact_ids"].pop("snapshot_event_id", None)
    row["source_fact_ids"].update(direct_fields)
    row["raw_json"].update(direct_fields)
    row.update(direct_fields)
    return row


def hint_1m_projection_row(asset_kind: str, identity_key: str, projection_30m_type: str) -> dict[str, object]:
    projection_id = stable_int(identity_key + "hint1m")
    proof_time = "2026-05-25T14:15:00+08:00"
    current_amount = {
        "volume_up": "120",
        "shrink_down": "80",
        "none": "100",
    }.get(projection_30m_type)
    reference_amount = "100" if projection_30m_type != "unknown" else None
    current_price = {
        "volume_up": "11",
        "shrink_down": "9",
        "none": "10",
    }.get(projection_30m_type)
    return {
        "projection_id": projection_id,
        "projection_run_id": PROJECTION_RUN_ID,
        "trade_date": "20260525",
        "metric_minute_label": "1415",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": "buy" if projection_30m_type == "volume_up" else "sell",
        "condition_key": "BUY_HINT" if projection_30m_type == "volume_up" else "SELL_HINT",
        "original_condition_key": "BUY_HINT" if projection_30m_type == "volume_up" else "SELL_HINT",
        "source_condition_pool_id": stable_int(identity_key + "pool"),
        "source_minute_target_scope_id": stable_int(identity_key + "scope"),
        "proof_kind": "index_board_1m_hint_projection_v1",
        "source_mode": "index_board_frequency8_1m",
        "metric_role": "hint_trigger_proof",
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "not_n5_final_proof": True,
        "current_window_start": "14:01",
        "current_window_end": "14:30",
        "previous_completed_window_start": "13:31",
        "previous_completed_window_end": "14:00",
        "current_window_elapsed_count": 15,
        "full_window_count": 30,
        "current_30m_price": current_price,
        "current_30m_elapsed_amount": current_amount,
        "previous_day_same_elapsed_30m_amount": "50" if projection_30m_type != "unknown" else None,
        "previous_day_full_30m_amount": reference_amount,
        "current_30m_virtual_amount": current_amount,
        "reference_30m_amount": reference_amount,
        "reference_30m_entity_high": "10",
        "reference_30m_entity_low": "10",
        "projection_30m_type": projection_30m_type,
        "projection_30m_flag": projection_30m_type in {"volume_up", "shrink_down"},
        "metric_ready": projection_30m_type != "unknown",
        "projection_status": "ready" if projection_30m_type != "unknown" else "not_ready",
        "projection_quality_status": "passed" if projection_30m_type != "unknown" else "blocked",
        "trace_status": "passed" if projection_30m_type != "unknown" else "blocked",
        "projection_signal_status": {
            "volume_up": "up_volume_expanding",
            "shrink_down": "down_volume_shrinking",
            "none": "flat",
        }.get(projection_30m_type, "unknown"),
        "raw_json": {
            "proof_kind": "index_board_1m_hint_projection_v1",
            "source_mode": "index_board_frequency8_1m",
            "not_n5_final_proof": True,
            "proof": {
                "source_projection_proof_time": proof_time,
                "proof_input_time": proof_time,
                "proof_input_minute_label": "1415",
            },
        },
        "trace_json": {
            "proof_kind": "index_board_1m_hint_projection_v1",
            "source_mode": "index_board_frequency8_1m",
            "proof": {
                "source_projection_proof_time": proof_time,
                "proof_input_time": proof_time,
                "proof_input_minute_label": "1415",
            },
        },
    }


def v4_projection_row(asset_kind: str, identity_key: str, *, direction: str) -> dict[str, object]:
    amount = "150" if direction == "buy" else "50"
    price = "10.50" if direction == "buy" else "9.50"
    return {
        **projection_row(asset_kind, identity_key, "ready", "flat"),
        "raw_json": {
            "enrichment_v1": {
                "current_price_or_close": price,
                "current_amount_metric": amount,
                "today_virt_amount": amount,
                "current_amount_metric_unit": "yuan",
                "current_amount_metric_source_kind": "N3_standard_period_metric",
                "current_metric_time": "2026-05-25T14:15:00+08:00",
                "current_metric_quality_status": "passed",
                "projection_period": "30m",
                "projection_30m_flag": False,
                "projection_30m_type": "none",
                "trigger_amount_chain_pass": {"D": True},
                "projection_lineage_json": {
                    "source": "n3_projection_enrichment_v4_metric",
                    "trigger_price": price,
                    "current_price": price,
                },
            }
        },
    }


def snapshot_projection_row(asset_kind: str, identity_key: str, *, price: str, amount: str) -> dict[str, object]:
    return {
        **projection_row(asset_kind, identity_key, "not_ready", "unknown"),
        "snapshot_current_price": price,
        "snapshot_close": price,
        "snapshot_amount": amount,
        "amount_unit": "yuan",
        "source_snapshot_time": "2026-05-25T14:15:00+08:00",
        "snapshot_quality_status": "passed",
    }


def period_trigger_baseline_json() -> dict[str, object]:
    current_keys = {
        "Y": "2026",
        "Q": "2026Q2",
        "M": "202605",
        "W": "2026W22",
        "D": "current-D",
    }
    return {
        "baseline_version": "N2-R4-period-trigger-baseline-v1",
        "baseline_source": "condition_basis",
        "periods": {
            period: {
                "baseline_ready": True,
                "period_baseline_ready": True,
                "period_key_current": current_keys[period],
                "period_key_previous": f"previous-{period}",
                "previous_transition": "flat",
                "previous_entity_high": "10",
                "previous_entity_low": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "previous_amount_baseline": "100",
                "trigger_previous_entity_high": "10",
                "trigger_previous_entity_low": "10",
                "trigger_previous_amount_baseline": "100",
                "trigger_previous_amount_baseline_unit": "yuan",
                "amount_metric": "amount",
            }
            for period in ("Y", "Q", "M", "W", "D")
        },
    }


def guard_counts() -> dict[str, dict[str, object]]:
    return {
        table_name: {"exists": True, "row_count": 0, "status": "present"}
        for table_name in (
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_state",
            "common_trigger_match",
            "common_event_outbox",
        )
    }


def stable_int(value: str) -> int:
    return int.from_bytes(value.encode("utf-8")[:6].ljust(6, b"0"), "big") % 1000000 + 1


if __name__ == "__main__":
    unittest.main()
