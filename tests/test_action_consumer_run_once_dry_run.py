import unittest

from ashare_v3.action.dry_run import build_action_candidates_from_outbox_rows
from ashare_v3.action.run_once_dry_run import (
    ACTION_EVENT_GUARD_TABLES,
    CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST,
    SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
    build_action_consumer_run_once_dry_run_report_from_rows,
    build_action_write_plan,
    build_output_event_plan,
    compare_baseline_report,
    summarize_action_write_plan,
    summarize_output_event_plan,
)


class ActionConsumerRunOnceDryRunTest(unittest.TestCase):
    def test_run_once_dry_run_builds_action_write_plan_without_writes(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_buy_hint",
                trigger_match_id=101,
                signal_type="B_BUY",
                condition_key="BUY_HINT",
                direction="buy",
                asset_kind="stock",
                identity_key="stock:SH:600000",
            ),
            sample_outbox_row(
                event_id="evt_sell_hint",
                trigger_match_id=102,
                signal_type="S_SELL",
                condition_key="SELL_HINT",
                trigger_mark_candidate="30m_shrink",
                projection_30m_type="shrink_down",
                direction="sell",
                asset_kind="stock",
                identity_key="stock:SH:600001",
            ),
            sample_outbox_row(
                event_id="evt_pending",
                event_type="TriggerPendingMarketData",
                trigger_match_id=103,
                signal_type="B_BUY",
                condition_key="BUY:D",
                direction="buy",
                source_event_type="MarketDataMissing",
                data_quality_status="missing",
                asset_kind="stock",
                identity_key="stock:SH:600002",
            ),
        ]
        report = build_action_consumer_run_once_dry_run_report_from_rows(
            trigger_run_id="trigger_run",
            action_run_id="action_run",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_run", "for_trade_date": "20260525"},
            outbox_rows=rows,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            baseline_report=baseline_report(read_event_count=3, by_event_type={"TriggerMatched": 2, "TriggerPendingMarketData": 1}),
        )

        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["action_write_plan_summary"]["planned_action_fact_count"], 2)
        self.assertEqual(report["action_write_plan_summary"]["quality_plan_only_count"], 1)
        self.assertEqual(report["action_write_plan_summary"]["pending_action_fact_plan_count"], 0)
        self.assertEqual(report["action_write_plan_summary"]["buy_hint_planned_action_fact_count"], 1)
        self.assertEqual(report["action_write_plan_summary"]["sell_hint_planned_action_fact_count"], 1)
        self.assertFalse(report["side_effects"]["action_fact_written"])
        self.assertFalse(report["side_effects"]["action_event_written"])
        self.assertFalse(report["side_effects"]["common_event_inbox_updated"])
        self.assertFalse(report["side_effects"]["consumer_checkpoint_updated"])

    def test_hint_conditions_can_remain_quality_only_without_p0(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_matched",
                trigger_match_id=110,
                signal_type="B_BUY",
                condition_key="BUY:D",
                direction="buy",
            ),
            sample_outbox_row(
                event_id="evt_buy_hint_pending",
                event_type="TriggerPendingMarketData",
                trigger_match_id=111,
                signal_type="B_BUY",
                condition_key="BUY_HINT",
                direction="buy",
                data_quality_status="missing",
            ),
            sample_outbox_row(
                event_id="evt_sell_hint_pending",
                event_type="TriggerPendingMarketData",
                trigger_match_id=112,
                signal_type="S_SELL",
                condition_key="SELL_HINT",
                trigger_mark_candidate="30m_shrink",
                projection_30m_type="shrink_down",
                direction="sell",
                data_quality_status="missing",
                identity_key="stock:SH:600001",
            ),
        ]
        report = build_action_consumer_run_once_dry_run_report_from_rows(
            trigger_run_id="trigger_run",
            action_run_id="action_run",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_run", "for_trade_date": "20260525"},
            outbox_rows=rows,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            baseline_report=baseline_report(read_event_count=3, by_event_type={"TriggerMatched": 1, "TriggerPendingMarketData": 2}),
        )

        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["action_candidate_summary"]["buy_hint_trace_count"], 1)
        self.assertEqual(report["action_candidate_summary"]["sell_hint_trace_count"], 1)
        self.assertEqual(report["action_write_plan_summary"]["planned_action_fact_count"], 1)
        self.assertEqual(report["action_write_plan_summary"]["quality_plan_only_count"], 2)
        self.assertEqual(report["action_candidate_summary"]["deprecated_hint_event_plan_count"], 0)

    def test_duplicate_source_trigger_match_id_is_skipped_in_action_write_plan(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [
                sample_outbox_row(event_id="evt_first", trigger_match_id=201),
                sample_outbox_row(event_id="evt_duplicate", trigger_match_id=201),
            ],
            action_run_id="action_run",
        )
        plan = build_action_write_plan(candidates)
        summary = summarize_action_write_plan(plan)

        self.assertEqual(summary["planned_action_fact_count"], 1)
        self.assertEqual(summary["skipped_count"], 1)
        self.assertEqual(summary["skip_reasons"], {"duplicate_source_trigger_match_id": 1})
        self.assertEqual(summary["duplicate_source_trigger_match_id_planned_count"], 0)

    def test_physical_action_fact_tables_follow_asset_kind(self) -> None:
        rows = [
            sample_outbox_row(event_id="evt_stock", trigger_match_id=301, asset_kind="stock", identity_key="stock:SH:600000"),
            sample_outbox_row(event_id="evt_index", trigger_match_id=302, asset_kind="index", identity_key="index:SH:000001"),
            sample_outbox_row(event_id="evt_board", trigger_match_id=303, asset_kind="board", identity_key="board:BK:881001"),
        ]
        candidates = build_action_candidates_from_outbox_rows(rows, action_run_id="action_run")
        summary = summarize_action_write_plan(build_action_write_plan(candidates))

        self.assertEqual(summary["physical_split_error_count"], 0)
        self.assertEqual(
            summary["by_target_action_fact_table"],
            {"board_action_fact": 1, "index_action_fact": 1, "stock_action_fact": 1},
        )

    def test_output_event_plan_contains_all_n5_event_types_without_execution(self) -> None:
        candidates = build_action_candidates_from_outbox_rows(
            [sample_outbox_row(event_id="evt_stock", trigger_match_id=401)],
            action_run_id="action_run",
        )
        output_plan = build_output_event_plan(build_action_write_plan(candidates))
        summary = summarize_output_event_plan(output_plan)

        self.assertEqual(
            summary["event_types_in_plan"],
            ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"],
        )
        self.assertEqual(summary["missing_event_types"], [])
        self.assertFalse(summary["common_event_outbox_written"])
        self.assertEqual(summary["executed_count"], 0)

    def test_r4_report_requires_current_source_run_and_period_trace(self) -> None:
        rows = [
            sample_outbox_row(event_id="evt_matched", trigger_match_id=501, source_run_id="trigger_r4"),
            sample_outbox_row(
                event_id="evt_sell_hint",
                trigger_match_id=503,
                source_run_id="trigger_r4",
                signal_type="S_SELL",
                condition_key="SELL_HINT",
                trigger_mark_candidate="30m_shrink",
                projection_30m_type="shrink_down",
                direction="sell",
                identity_key="stock:SH:600001",
            ),
            sample_outbox_row(
                event_id="evt_pending",
                event_type="TriggerPendingMarketData",
                trigger_match_id=502,
                source_run_id="trigger_r4",
                signal_type="B_BUY",
                condition_key="BUY:D",
                source_event_type="MarketDataDelayed",
                data_quality_status="delayed",
            ),
        ]
        report = build_action_consumer_run_once_dry_run_report_from_rows(
            trigger_run_id="trigger_r4",
            action_run_id="action_r4",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_r4", "for_trade_date": "20260525"},
            outbox_rows=rows,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            baseline_report=n4_execute_baseline_report(
                run_id="trigger_r4",
                outbox_count=3,
                by_event_type={"TriggerMatched": 2, "TriggerPendingMarketData": 1},
                by_signal_type={"B_BUY": 2, "S_SELL": 1},
            ),
            stage="N5-R4",
            expected_read_event_count=3,
            require_period_trigger_baseline_trace=True,
        )

        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertTrue(report["source_run_id_summary"]["only_expected_source_run_id"])
        self.assertEqual(report["period_trigger_baseline_trace_summary"]["present_count"], 3)
        self.assertEqual(report["period_trigger_baseline_trace_summary"]["missing_count"], 0)
        self.assertTrue(report["baseline_comparison"]["explainable"])

    def test_action_confirmation_metric_contract_baseline_is_explainable(self) -> None:
        rows = [
            sample_outbox_row(
                event_id="evt_metric_match",
                trigger_match_id=601,
                source_run_id="trigger_action_confirmation_metric",
                signal_type="S_SELL",
                direction="sell",
                condition_key="SELL:Y,Q,M",
                trigger_mark_candidate="30m_shrink",
                projection_30m_type="shrink_down",
            ),
            sample_outbox_row(
                event_id="evt_metric_pending",
                event_type="TriggerPendingMarketData",
                trigger_match_id=602,
                source_run_id="trigger_action_confirmation_metric",
                signal_type="B_BUY",
                direction="buy",
                condition_key="BUY:D",
                data_quality_status="missing",
            ),
        ]
        report = build_action_consumer_run_once_dry_run_report_from_rows(
            trigger_run_id="trigger_action_confirmation_metric",
            action_run_id="action_metric",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_action_confirmation_metric", "for_trade_date": "20260602"},
            outbox_rows=rows,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            baseline_report={
                "execute_run_id": "trigger_action_confirmation_metric",
                "expected_writes": {
                    "TriggerMatched": 1,
                    "TriggerPendingMarketData": 1,
                    "TriggerStateChanged": 0,
                    "common_event_outbox": 2,
                },
                "would_write_by_output_event_type": {
                    "TriggerMatched": 1,
                    "TriggerPendingMarketData": 1,
                },
            },
            expected_read_event_count=2,
        )

        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertTrue(report["baseline_comparison"]["explainable"])
        self.assertEqual(report["baseline_comparison"]["baseline_kind"], "N4_action_confirmation_metric_contract")

    def test_projection_execute_baseline_report_is_explainable(self) -> None:
        comparison = compare_baseline_report(
            current_consumer_summary={"read_event_count": 3},
            current_outbox_summary={
                "by_event_type": {"TriggerMatched": 2, "TriggerPendingMarketData": 1},
                "by_signal_type": {"B_BUY": 2, "S_SELL": 1},
            },
            trigger_run_id="n4_projection_replay",
            baseline_report={
                "stage": "N4-projection-matcher-execute-preflight",
                "execute_run_id": "n4_projection_replay",
                "execute_plan_summary": {
                    "matched_output_count": 2,
                    "pending_output_count": 1,
                    "trigger_output_plan_count": 3,
                    "matched_by_signal_type": {"B_BUY": 2},
                    "pending_by_signal_type": {"S_SELL": 1},
                },
            },
            baseline_report_path="docs/n4_projection_replay.json",
        )

        self.assertTrue(comparison["explainable"])
        self.assertEqual(comparison["baseline_kind"], "N4_projection_matcher_execute_preflight")
        self.assertEqual(comparison["baseline_read_event_count"], 3)
        self.assertEqual(
            comparison["baseline_by_event_type"],
            {"TriggerMatched": 2, "TriggerPendingMarketData": 1},
        )

    def test_current_real_source_guard_allows_current_and_rejects_synthetic(self) -> None:
        current_run = CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST[0]
        synthetic_run = SYNTHETIC_N4_SOURCE_RUN_DENYLIST[0]
        current_report = build_action_consumer_run_once_dry_run_report_from_rows(
            trigger_run_id=current_run,
            action_run_id="action_current_real",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": current_run, "for_trade_date": "20260525"},
            outbox_rows=[
                sample_outbox_row(event_id="evt_current_buy", source_run_id=current_run),
                sample_outbox_row(
                    event_id="evt_current_sell",
                    source_run_id=current_run,
                    signal_type="S_SELL",
                    condition_key="SELL_HINT",
                    trigger_mark_candidate="30m_shrink",
                    projection_30m_type="shrink_down",
                    direction="sell",
                    identity_key="stock:SH:600001",
                    trigger_match_id=101,
                ),
            ],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            baseline_report={
                "stage": "N5-1",
                "source_trigger_run_id": current_run,
                "consumer_plan_summary": {"read_event_count": 2},
                "outbox_summary": {
                    "by_event_type": {"TriggerMatched": 2},
                    "by_signal_type": {"B_BUY": 1, "S_SELL": 1},
                },
            },
            allowed_source_run_ids=CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST,
            denied_source_run_ids=SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
        )
        synthetic_report = build_action_consumer_run_once_dry_run_report_from_rows(
            trigger_run_id=synthetic_run,
            action_run_id="action_synthetic",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": synthetic_run, "for_trade_date": "20260525"},
            outbox_rows=[sample_outbox_row(event_id="evt_synthetic", source_run_id=synthetic_run)],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            baseline_report=baseline_report(read_event_count=1, by_event_type={"TriggerMatched": 1}),
            allowed_source_run_ids=CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST,
            denied_source_run_ids=SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
        )

        self.assertTrue(current_report["source_run_guard"]["passed"])
        self.assertEqual(current_report["quality"]["p0_count"], 0)
        self.assertFalse(synthetic_report["source_run_guard"]["passed"])
        self.assertGreaterEqual(synthetic_report["quality"]["p0_count"], 1)


def guard_counts() -> dict[str, dict[str, object]]:
    counts = {
        "common_event_outbox": {"exists": True, "row_count": 3, "status": "present"},
    }
    for table_name in ACTION_EVENT_GUARD_TABLES:
        counts[table_name] = {"exists": True, "row_count": 0, "status": "present"}
    return counts


def baseline_report(*, read_event_count: int, by_event_type: dict[str, int]) -> dict[str, object]:
    return {
        "stage": "N5-1",
        "source_trigger_run_id": "trigger_run",
        "consumer_plan_summary": {
            "read_event_count": read_event_count,
        },
        "outbox_summary": {
            "by_event_type": by_event_type,
            "by_signal_type": {},
        },
    }


def n4_execute_baseline_report(
    *,
    run_id: str,
    outbox_count: int,
    by_event_type: dict[str, int],
    by_signal_type: dict[str, int],
) -> dict[str, object]:
    return {
        "stage": "N4-R4-synthetic-execute",
        "run_id": run_id,
        "output_summary": {
            "outbox_count": outbox_count,
            "outbox_by_event_type": by_event_type,
            "match_by_signal_type": by_signal_type,
        },
    }


def sample_outbox_row(
    *,
    event_id: str = "evt_trigger",
    event_type: str = "TriggerMatched",
    trigger_match_id: int = 100,
    signal_type: str = "B_BUY",
    condition_key: str = "BUY_HINT",
    original_condition_key: str | None = None,
    direction: str = "buy",
    source_event_type: str = "MinuteBarClosed",
    data_quality_status: str = "passed",
    asset_kind: str = "stock",
    identity_key: str = "stock:SH:600000",
    source_run_id: str = "trigger_run",
    trigger_mark_candidate: str = "normal",
    projection_30m_type: str = "none",
    action_confirmation: dict[str, str] | None = None,
) -> dict[str, object]:
    payload = {
        "run_id": source_run_id,
        "source_event_id": f"source_{event_id}",
        "source_event_type": source_event_type,
        "source_condition_run_id": "condition_run",
        "source_market_data_run_id": "market_run",
        "trigger_match_id": trigger_match_id,
        "trigger_state_id": 200,
        "identity_key": identity_key,
        "asset_kind": asset_kind,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key or condition_key,
        "trigger_mark_candidate": trigger_mark_candidate,
        "projection_30m_flag": projection_30m_type != "none",
        "projection_30m_type": projection_30m_type,
        "trigger_live": event_type == "TriggerMatched",
        "trigger_period": "30m" if trigger_mark_candidate in {"30m_volume", "30m_shrink"} else "D",
        "trigger_bucket": "30m_1000_1030",
        "data_quality_status": data_quality_status,
        "period_trigger_baseline_trace": {
            "present": True,
            "baseline_version": "N2-R4-period-trigger-baseline-v1",
            "required_periods": ["Y", "M", "W", "D"],
            "required_period_not_ready": [],
        },
        "synthetic_sample_event": True,
    }
    if action_confirmation is not None:
        payload["action_confirmation"] = action_confirmation
    return {
        "outbox_id": trigger_match_id,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "v1",
        "trade_date": "20260525",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "event_time": "2026-05-25T02:30:00+00:00",
        "source_layer": "N4_trigger",
        "source_run_id": source_run_id,
        "dedup_key": f"dedup_{event_id}",
        "partition_key": identity_key,
        "payload_json": payload,
        "status": "pending",
    }


if __name__ == "__main__":
    unittest.main()
