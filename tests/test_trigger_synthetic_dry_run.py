import json
import unittest

from ashare_v3.trigger.synthetic_dry_run import (
    build_empty_outbox_lineage,
    build_dry_run_plans,
    build_period_trigger_baseline_trace,
    build_synthetic_events,
    build_synthetic_trigger_dry_run_report,
)


class TriggerSyntheticDryRunTest(unittest.TestCase):
    def test_synthetic_market_snapshot_matches_ordinary_buy_sell(self) -> None:
        events = [event for event in build_synthetic_events("20260525") if event["event_type"] == "MarketSnapshotUpdated"]
        plans = build_dry_run_plans(
            context_rows=[
                sample_context_row(direction="buy", condition_key="BUY:D", allowed_signal_types=["B_BUY", "B_BUY_30M_VOL"]),
                sample_context_row(direction="sell", condition_key="SELL:FULL", allowed_signal_types=["S_SELL", "S_SELL_30M_SHRINK"]),
                sample_context_row(direction="buy", condition_key="BUY_HINT", allowed_signal_types=["BUY_HINT"]),
            ],
            synthetic_events=events,
        )

        self.assertEqual(len(plans), 2)
        self.assertEqual({plan["signal_type"] for plan in plans}, {"B_BUY", "S_SELL"})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerMatched"})

    def test_synthetic_minute_bar_closed_matches_buy_hint_sell_hint(self) -> None:
        events = [event for event in build_synthetic_events("20260525") if event["event_type"] == "MinuteBarClosed"]
        plans = build_dry_run_plans(
            context_rows=[
                sample_context_row(direction="buy", condition_key="BUY:D", allowed_signal_types=["B_BUY"]),
                sample_context_row(direction="buy", condition_key="BUY_HINT", allowed_signal_types=["BUY_HINT"]),
                sample_context_row(direction="sell", condition_key="SELL_HINT", allowed_signal_types=["SELL_HINT"]),
            ],
            synthetic_events=events,
        )

        self.assertEqual(len(plans), 2)
        self.assertEqual({plan["signal_type"] for plan in plans}, {"B_BUY", "S_SELL"})
        self.assertEqual({plan["condition_key"] for plan in plans}, {"BUY_HINT", "SELL_HINT"})
        self.assertEqual({plan["trigger_mark_candidate"] for plan in plans}, {"30m_volume", "30m_shrink"})
        self.assertFalse(any("action_mark" in plan for plan in plans))
        self.assertEqual({plan["trigger_period"] for plan in plans}, {"30m"})

    def test_market_data_missing_produces_pending_only(self) -> None:
        events = [event for event in build_synthetic_events("20260525") if event["event_type"] == "MarketDataMissing"]
        plans = build_dry_run_plans(
            context_rows=[
                sample_context_row(direction="buy", condition_key="BUY:D", allowed_signal_types=["B_BUY", "B_BUY_30M_VOL"]),
            ],
            synthetic_events=events,
        )

        self.assertEqual(len(plans), 2)
        self.assertEqual({plan["plan_status"] for plan in plans}, {"pending"})
        self.assertEqual({plan["output_event_type"] for plan in plans}, {"TriggerPendingMarketData"})
        self.assertEqual({plan["data_quality_status"] for plan in plans}, {"missing"})

    def test_dry_run_report_has_no_outbox_or_downstream_writes(self) -> None:
        before = guard_counts()
        after = guard_counts()
        report = build_synthetic_trigger_dry_run_report(
            trigger_context_run_id="trigger_context_snapshot_test",
            trigger_run={
                "run_id": "trigger_context_snapshot_test",
                "status": "passed",
                "for_trade_date": "20260525",
                "source_condition_run_id": "condition_layer_test",
            },
            context_rows=[
                sample_context_row(direction="buy", condition_key="BUY:D", allowed_signal_types=["B_BUY", "B_BUY_30M_VOL"]),
                sample_context_row(direction="buy", condition_key="BUY_HINT", allowed_signal_types=["BUY_HINT"]),
                sample_context_row(direction="sell", condition_key="SELL_HINT", allowed_signal_types=["SELL_HINT"]),
            ],
            synthetic_events=build_synthetic_events("20260525"),
            before_row_counts=before,
            after_row_counts=after,
            outbox_lineage=build_empty_outbox_lineage("trigger_context_snapshot_test"),
        )

        self.assertEqual(report["quality"]["p0_count"], 0, report["quality"]["items"])
        self.assertEqual(report["period_trigger_baseline_json_missing"], 0)
        self.assertEqual(report["required_period_not_ready_rows"], 0)
        self.assertEqual(report["period_trigger_baseline_trace_count"], report["candidate_count"])
        self.assertFalse(report["side_effects"]["event_outbox_written"])
        self.assertFalse(report["side_effects"]["trigger_state_written"])
        self.assertFalse(report["side_effects"]["trigger_match_written"])
        self.assertFalse(report["side_effects"]["action_user_voice_sim_written"])
        self.assertFalse(report["side_effects"]["real_common_event_outbox_consumed"])
        self.assertEqual(report["outbox_lineage"]["current_context_run_outbox_count"], 0)
        self.assertFalse(report["outbox_lineage"]["current_run_has_n5_usable_outbox"])

    def test_dry_run_does_not_reference_external_n2_runtime_path(self) -> None:
        report = build_synthetic_trigger_dry_run_report(
            trigger_context_run_id="trigger_context_snapshot_test",
            trigger_run={
                "run_id": "trigger_context_snapshot_test",
                "status": "passed",
                "for_trade_date": "20260525",
                "source_condition_run_id": "condition_layer_test",
            },
            context_rows=[
                sample_context_row(direction="buy", condition_key="BUY:D", allowed_signal_types=["B_BUY"]),
                sample_context_row(direction="buy", condition_key="BUY_HINT", allowed_signal_types=["BUY_HINT"]),
                sample_context_row(direction="sell", condition_key="SELL_HINT", allowed_signal_types=["SELL_HINT"]),
            ],
            synthetic_events=build_synthetic_events("20260525"),
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            outbox_lineage=build_empty_outbox_lineage("trigger_context_snapshot_test"),
        )

        self.assertFalse(report["side_effects"]["external_n2_runtime_path_accessed"])
        self.assertNotIn("/Volumes/MacRaid", json.dumps(report, ensure_ascii=False))

    def test_report_marks_prior_outbox_as_not_usable_for_current_context(self) -> None:
        report = build_synthetic_trigger_dry_run_report(
            trigger_context_run_id="trigger_context_snapshot_new",
            trigger_run={
                "run_id": "trigger_context_snapshot_new",
                "status": "passed",
                "for_trade_date": "20260525",
                "source_condition_run_id": "condition_layer_new",
                "source_market_data_run_id": "market_data_subscription_new",
            },
            context_rows=[
                sample_context_row(direction="buy", condition_key="BUY:D", allowed_signal_types=["B_BUY"]),
                sample_context_row(direction="buy", condition_key="BUY_HINT", allowed_signal_types=["BUY_HINT"]),
                sample_context_row(direction="sell", condition_key="SELL_HINT", allowed_signal_types=["SELL_HINT"]),
            ],
            synthetic_events=build_synthetic_events("20260525"),
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            outbox_lineage={
                "common_event_outbox_baseline_count": 26652,
                "current_context_run_id": "trigger_context_snapshot_new",
                "current_context_run_outbox_count": 0,
                "stale_n4_outbox_count": 26652,
                "stale_n4_outbox_by_source_run": [
                    {"source_run_id": "trigger_context_snapshot_old", "event_type": "TriggerMatched", "row_count": 8884}
                ],
                "outbox_by_source_run": [],
                "current_run_has_n5_usable_outbox": False,
                "n5_use_guidance": "stale baseline must not be consumed",
            },
        )

        self.assertEqual(report["quality"]["p0_count"], 0, report["quality"]["items"])
        self.assertEqual(report["outbox_lineage"]["stale_n4_outbox_count"], 26652)
        self.assertEqual(report["outbox_lineage"]["current_context_run_outbox_count"], 0)
        self.assertIn("TriggerMatched", json.dumps(report["sample_plans"], ensure_ascii=False))
        self.assertIn("period_trigger_baseline_trace", json.dumps(report["sample_plans"], ensure_ascii=False))
        self.assertIn("TriggerPendingMarketData", json.dumps(report["summary"], ensure_ascii=False))

    def test_period_trigger_baseline_trace_exposes_repaired_trigger_fields(self) -> None:
        row = sample_context_row(
            direction="sell",
            condition_key="SELL:D",
            allowed_signal_types=["S_SELL"],
        )
        row["asset_kind"] = "board"
        row["identity_key"] = "board:TDX:880920"

        trace = build_period_trigger_baseline_trace(row, "SELL:D", "D")

        period_d = trace["traced_periods"]["D"]
        self.assertEqual(period_d["trigger_previous_entity_high"], "11")
        self.assertEqual(period_d["trigger_previous_entity_low"], "10")
        self.assertEqual(period_d["trigger_previous_amount_baseline"], "200")
        self.assertEqual(period_d["baseline_source"], "trigger_baseline")


def sample_context_row(
    *,
    direction: str,
    condition_key: str,
    allowed_signal_types: list[str],
) -> dict[str, object]:
    return {
        "trigger_context_id": 1,
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
                "current_avg_amount_seed": "200",
                "current_trade_days_seed": 1,
                "previous_open": "12",
                "previous_close": "10",
                "previous_entity_high": "12",
                "previous_entity_low": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "previous_amount_baseline": "100",
                "classification_previous_open": "12",
                "classification_previous_close": "10",
                "classification_previous_entity_high": "12",
                "classification_previous_entity_low": "10",
                "classification_previous_amount_baseline": "100",
                "classification_period_key_previous": "20260522" if period == "D" else f"previous-{period}",
                "trigger_previous_open": "10",
                "trigger_previous_close": "11",
                "trigger_previous_entity_high": "11",
                "trigger_previous_entity_low": "10",
                "trigger_previous_amount_baseline": "200",
                "baseline_source_trade_date": "20260522",
                "amount_metric": "amount" if period == "D" else "avg_amount",
                "current_window_start": "20260501",
                "current_window_end": "20260522",
                "previous_window_start": "20260401",
                "previous_window_end": "20260430",
            }
            for period in ("Y", "Q", "M", "W", "D")
        },
    }


def guard_counts() -> dict[str, dict[str, object]]:
    return {
        table_name: {"exists": True, "row_count": 0, "status": "present"}
        for table_name in (
            "common_trigger_run",
            "common_trigger_quality_item",
            "stock_trigger_context_snapshot",
            "index_trigger_context_snapshot",
            "board_trigger_context_snapshot",
            "common_trigger_state",
            "common_trigger_match",
            "common_event_outbox",
        )
    }


if __name__ == "__main__":
    unittest.main()
