import unittest

from ashare_v3.trigger.c3_replay_plan import (
    DEFAULT_ALLOWED_C3_RUN_ID,
    DEFAULT_C2B_RUN_ID,
    DEFAULT_CONTEXT_RUN_ID,
    DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
    DEFAULT_REPLAY_RUN_ID,
    DEFAULT_SYNTHETIC_DENYLIST,
    REPLAY_SIGNAL_TYPES,
    C3ReplayPlanError,
    build_c3_replay_dry_run_report_from_rows,
    build_replay_run_id,
    filter_c3_input_rows,
    signal_type_for_context,
)


class C3ReplayPlanTests(unittest.TestCase):
    def test_builds_stable_replay_run_id_from_allowlisted_c3_run(self) -> None:
        self.assertEqual(
            build_replay_run_id(DEFAULT_ALLOWED_C3_RUN_ID, for_trade_date="20260525"),
            DEFAULT_REPLAY_RUN_ID,
        )

    def test_allowlist_filter_rejects_non_allowlisted_c3_inputs(self) -> None:
        rows = [
            c3_event_row(event_id="evt_allowed", source_run_id=DEFAULT_ALLOWED_C3_RUN_ID),
            c3_event_row(event_id="evt_wrong", source_run_id="minute_bar_closed_outbox_other"),
            c3_event_row(event_id="evt_snapshot", event_type="MarketSnapshotUpdated"),
            c3_event_row(event_id="evt_n5", source_layer="N5_action", event_type="ActionEvent"),
        ]

        allowed, rejected = filter_c3_input_rows(rows, allowed_c3_run_id=DEFAULT_ALLOWED_C3_RUN_ID)

        self.assertEqual([row["event_id"] for row in allowed], ["evt_allowed"])
        self.assertEqual({row["reject_reason"] for row in rejected}, {"source_run_id_not_allowlisted", "event_type_not_minute_bar_closed", "source_layer_not_n3"})

    def test_signal_scope_only_includes_four_replayable_signals(self) -> None:
        signals = {
            signal_type_for_context(context_row("buy", "BUY:Y,Q,D", ["B_BUY", "B_BUY_30M_VOL"])),
            signal_type_for_context(context_row("buy", "BUY_HINT", ["BUY_HINT"])),
            signal_type_for_context(context_row("sell", "SELL:Y,D", ["S_SELL", "S_SELL_30M_SHRINK"])),
            signal_type_for_context(context_row("sell", "SELL_HINT", ["SELL_HINT"])),
            signal_type_for_context(context_row("buy", "BUY:D", ["B_BUY"])),
            signal_type_for_context(context_row("sell", "SELL:D", ["S_SELL"])),
        }

        self.assertEqual(signals - {None}, set(REPLAY_SIGNAL_TYPES))

    def test_synthetic_context_run_is_blocked(self) -> None:
        report = build_c3_replay_dry_run_report_from_rows(
            allowed_c3_run_id=DEFAULT_ALLOWED_C3_RUN_ID,
            replay_run_id=DEFAULT_REPLAY_RUN_ID,
            trigger_context_run={"run_id": DEFAULT_SYNTHETIC_DENYLIST[0], "status": "passed"},
            projection_trigger_run={"run_id": DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID, "status": "passed"},
            context_rows=[context_row("buy", "BUY_HINT", ["BUY_HINT"])],
            c3_outbox_rows=[c3_event_row()],
            closed_summary_rows=[closed_summary_row(closed_signal_status="up_volume_expanding")],
            projection_match_rows=[],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["result"], "DRY_RUN_BLOCKED")
        self.assertGreater(report["quality"]["p0_count"], 0)
        self.assertIn("n4_c3_replay_context_not_synthetic", {item["gate_code"] for item in report["quality"]["items"] if item["status"] == "failed"})

    def test_classifies_projection_closed_diff_cases(self) -> None:
        context_rows = [
            context_row("buy", "BUY_HINT", ["BUY_HINT"], identity_key="stock:SH:600001"),
            context_row("sell", "SELL_HINT", ["SELL_HINT"], identity_key="stock:SH:600002"),
            context_row("buy", "BUY:Y,D", ["B_BUY_30M_VOL"], identity_key="stock:SH:600003"),
            context_row("sell", "SELL:Y,D", ["S_SELL_30M_SHRINK"], identity_key="stock:SH:600004"),
            context_row("buy", "BUY:M,D", ["B_BUY_30M_VOL"], identity_key="stock:SH:600005"),
            context_row("sell", "SELL:M,D", ["S_SELL_30M_SHRINK"], identity_key="stock:SH:600006"),
        ]
        c3_rows = [
            c3_event_row(event_id="evt_1", identity_key="stock:SH:600001", summary_id=1, bucket_id="1401_1430"),
            c3_event_row(event_id="evt_2", identity_key="stock:SH:600002", summary_id=2, bucket_id="1401_1430"),
            c3_event_row(event_id="evt_3", identity_key="stock:SH:600003", summary_id=3, bucket_id="1401_1430"),
            c3_event_row(event_id="evt_4", identity_key="stock:SH:600004", summary_id=4, bucket_id="1401_1430"),
            c3_event_row(event_id="evt_5", identity_key="stock:SH:600005", summary_id=5, bucket_id="1401_1430"),
        ]
        summaries = [
            closed_summary_row(summary_id=1, identity_key="stock:SH:600001", closed_signal_status="up_volume_expanding"),
            closed_summary_row(summary_id=2, identity_key="stock:SH:600002", closed_signal_status="down_volume_expanding"),
            closed_summary_row(summary_id=3, identity_key="stock:SH:600003", closed_signal_status="up_volume_expanding", quality_status="warning"),
            closed_summary_row(summary_id=4, identity_key="stock:SH:600004", closed_signal_status="down_volume_shrinking"),
            closed_summary_row(summary_id=5, identity_key="stock:SH:600005", closed_signal_status=None),
        ]
        projection_rows = [
            projection_match_row(identity_key="stock:SH:600002", direction="sell", signal_type="SELL_HINT", condition_key="SELL_HINT", output_event_type="TriggerMatched", projection_signal_status="down_volume_shrinking"),
            projection_match_row(identity_key="stock:SH:600003", direction="buy", signal_type="B_BUY_30M_VOL", condition_key="BUY:Y,D", output_event_type="TriggerMatched", projection_signal_status="up_volume_expanding", data_quality_status="passed"),
            projection_match_row(identity_key="stock:SH:600004", direction="sell", signal_type="S_SELL_30M_SHRINK", condition_key="SELL:Y,D", output_event_type="TriggerMatched", projection_signal_status="down_volume_shrinking"),
        ]

        report = build_c3_replay_dry_run_report_from_rows(
            allowed_c3_run_id=DEFAULT_ALLOWED_C3_RUN_ID,
            replay_run_id=DEFAULT_REPLAY_RUN_ID,
            trigger_context_run={"run_id": DEFAULT_CONTEXT_RUN_ID, "status": "passed"},
            projection_trigger_run={"run_id": DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID, "status": "passed"},
            context_rows=context_rows,
            c3_outbox_rows=c3_rows,
            closed_summary_rows=summaries,
            projection_match_rows=projection_rows,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["classification_summary"]["by_classification"], {
            "missing": 1,
            "not_ready": 1,
            "unchanged": 1,
            "would_change": 1,
            "would_clear": 1,
            "would_match": 1,
        })
        self.assertEqual(report["replay_diff_summary"]["projection_matched_but_closed_not_matched"], 1)
        self.assertEqual(report["replay_diff_summary"]["projection_not_matched_but_closed_matched"], 1)
        self.assertEqual(report["replay_diff_summary"]["both_matched_but_quality_changed"], 1)
        self.assertEqual(report["replay_diff_summary"]["unchanged"], 1)
        self.assertEqual(report["replay_diff_summary"]["replay_blocked"], 2)

    def test_c2b_enrichment_supplies_closed_signal_without_raw_minute_or_b2_projection(self) -> None:
        report = build_c3_replay_dry_run_report_from_rows(
            allowed_c3_run_id=DEFAULT_ALLOWED_C3_RUN_ID,
            replay_run_id=DEFAULT_REPLAY_RUN_ID,
            c2b_run_id=DEFAULT_C2B_RUN_ID,
            trigger_context_run={"run_id": DEFAULT_CONTEXT_RUN_ID, "status": "passed"},
            projection_trigger_run={"run_id": DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID, "status": "passed"},
            context_rows=[context_row("buy", "BUY_HINT", ["BUY_HINT"])],
            c3_outbox_rows=[c3_event_row(summary_id=9)],
            closed_summary_rows=[closed_summary_row(summary_id=9, closed_signal_status=None)],
            closed_signal_enrichment_rows=[
                closed_signal_enrichment_row(summary_id=9, closed_signal_status="up_volume_expanding")
            ],
            projection_match_rows=[],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["classification_summary"]["by_classification"], {"would_match": 1})
        self.assertEqual(report["reason_summary"], {"projection_match_missing": 1})
        self.assertEqual(report["closed_signal_summary"]["closed_signal_status_missing_count"], 0)
        self.assertFalse(report["sample_diffs"][0]["trace_only_b2_projection_fact_used_for_classification"])

    def test_report_preserves_dry_run_boundaries(self) -> None:
        report = build_c3_replay_dry_run_report_from_rows(
            allowed_c3_run_id=DEFAULT_ALLOWED_C3_RUN_ID,
            replay_run_id=DEFAULT_REPLAY_RUN_ID,
            trigger_context_run={"run_id": DEFAULT_CONTEXT_RUN_ID, "status": "passed"},
            projection_trigger_run={"run_id": DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID, "status": "passed"},
            context_rows=[context_row("buy", "BUY_HINT", ["BUY_HINT"])],
            c3_outbox_rows=[c3_event_row()],
            closed_summary_rows=[closed_summary_row(closed_signal_status="up_volume_expanding")],
            projection_match_rows=[],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        boundary = report["boundary_confirmation"]
        self.assertFalse(boundary["database_written"])
        self.assertFalse(boundary["c3_outbox_consumed"])
        self.assertFalse(boundary["common_event_inbox_written"])
        self.assertFalse(boundary["checkpoint_written"])
        self.assertFalse(boundary["trigger_match_written"])
        self.assertFalse(boundary["trigger_state_written"])
        self.assertFalse(boundary["n4_outbox_written"])
        self.assertFalse(boundary["n5_n6_touched"])
        self.assertFalse(boundary["worker_started"])


def context_row(direction: str, condition_key: str, allowed_signal_types: list[str], *, identity_key: str = "stock:SH:600000") -> dict:
    return {
        "trigger_context_id": abs(hash((identity_key, direction, condition_key))) % 100000,
        "run_id": DEFAULT_CONTEXT_RUN_ID,
        "asset_kind": identity_key.split(":")[0],
        "identity_key": identity_key,
        "direction": direction,
        "condition_key": condition_key,
        "allowed_signal_types": allowed_signal_types,
        "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
        "source_condition_pool_id": 11,
        "source_condition_basis_id": 12,
        "source_market_subscription_id": 13,
        "for_trade_date": "20260525",
        "context_hash": "ctx",
        "raw_json": {"period_trigger_baseline_json": {"baseline_version": "test"}},
    }


def c3_event_row(
    *,
    event_id: str = "evt_c3",
    source_layer: str = "N3_market_data",
    event_type: str = "MinuteBarClosed",
    source_run_id: str = DEFAULT_ALLOWED_C3_RUN_ID,
    identity_key: str = "stock:SH:600000",
    summary_id: int = 1,
    bucket_id: str = "1401_1430",
) -> dict:
    return {
        "outbox_id": summary_id,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "v2",
        "source_layer": source_layer,
        "source_run_id": source_run_id,
        "status": "pending",
        "asset_kind": identity_key.split(":")[0],
        "identity_key": identity_key,
        "trade_date": "20260525",
        "event_time": "2026-05-25T14:30:00+08:00",
        "payload_json": {
            "closed_30m_summary_id": summary_id,
            "summary_id": summary_id,
            "bucket_id": bucket_id,
            "bucket_start": "2026-05-25T14:01:00+08:00",
            "bucket_end": "2026-05-25T14:30:00+08:00",
            "closed_status": "closed",
            "quality_status": "passed",
            "c2_run_id": "closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute",
            "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
            "source_subscription_run_id": "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute",
            "replay_diff_json": {},
        },
    }


def closed_summary_row(
    *,
    summary_id: int = 1,
    identity_key: str = "stock:SH:600000",
    bucket_id: str = "1401_1430",
    closed_signal_status: str | None = "up_volume_expanding",
    quality_status: str = "passed",
) -> dict:
    return {
        "summary_id": summary_id,
        "asset_kind": identity_key.split(":")[0],
        "identity_key": identity_key,
        "bucket_id": bucket_id,
        "closed_status": "closed",
        "quality_status": quality_status,
        "open": "10.00",
        "close": "10.50",
        "amount": "1000000.00",
        "raw_json": {"closed_market_shape_status": closed_signal_status} if closed_signal_status else {},
    }


def closed_signal_enrichment_row(
    *,
    summary_id: int = 1,
    identity_key: str = "stock:SH:600000",
    bucket_id: str = "1401_1430",
    closed_signal_status: str = "up_volume_expanding",
    quality_status: str = "passed",
) -> dict:
    return {
        "enrichment_id": summary_id,
        "c2b_run_id": DEFAULT_C2B_RUN_ID,
        "c2_run_id": "closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute",
        "current_summary_id": summary_id,
        "asset_kind": identity_key.split(":")[0],
        "identity_key": identity_key,
        "trade_date": "20260525",
        "bucket_id": bucket_id,
        "current_window_amount": "1200000.00",
        "baseline_window_amount": "1000000.00",
        "closed_amount_ratio": "1.20",
        "closed_price_direction_status": "up" if closed_signal_status.startswith("up_") else "down",
        "closed_market_shape_status": closed_signal_status,
        "closed_signal_status": closed_signal_status,
        "closed_signal_quality_status": quality_status,
        "closed_signal_basis_json": {"baseline_status": "passed"},
        "baseline_trace_json": {"trace": "test"},
        "raw_json": {},
    }


def projection_match_row(
    *,
    identity_key: str = "stock:SH:600000",
    direction: str = "buy",
    signal_type: str = "BUY_HINT",
    condition_key: str = "BUY_HINT",
    trigger_bucket: str = "20260525_1400_1430",
    output_event_type: str = "TriggerMatched",
    projection_signal_status: str = "up_volume_expanding",
    data_quality_status: str = "passed",
) -> dict:
    return {
        "trigger_match_id": abs(hash((identity_key, direction, signal_type, condition_key))) % 100000,
        "run_id": DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
        "asset_kind": identity_key.split(":")[0],
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "trigger_period": "30m",
        "trigger_bucket": trigger_bucket,
        "output_event_type": output_event_type,
        "data_quality_status": data_quality_status,
        "source_event_id": "evt_b1",
        "raw_json": {"projection_signal_status": projection_signal_status},
    }


def guard_counts() -> dict:
    return {
        "common_event_inbox": {"row_count": 0},
        "common_event_consumer_checkpoint": {"row_count": 0},
        "common_trigger_state": {"row_count": 0},
        "common_trigger_match": {"row_count": 0},
        "common_event_outbox": {"row_count": 0},
    }


if __name__ == "__main__":
    unittest.main()
