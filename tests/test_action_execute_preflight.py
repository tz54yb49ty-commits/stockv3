import unittest

from ashare_v3.action.execute_preflight import build_execute_preflight_report
from ashare_v3.action.run_once_dry_run import ACTION_EVENT_GUARD_TABLES, build_action_consumer_run_once_dry_run_report_from_rows


class ActionExecutePreflightTest(unittest.TestCase):
    def test_execute_preflight_allows_canonical_action_event_mapping_and_trace_json(self) -> None:
        rows = [
            sample_outbox_row(event_id="evt_buy_hint", trigger_match_id=101, signal_type="B_BUY", condition_key="BUY_HINT"),
            sample_outbox_row(
                event_id="evt_sell_hint",
                trigger_match_id=102,
                signal_type="S_SELL",
                condition_key="SELL_HINT",
                trigger_mark_candidate="30m_shrink",
                projection_30m_type="shrink_down",
                direction="sell",
                identity_key="stock:SH:600001",
            ),
            sample_outbox_row(
                event_id="evt_buy",
                trigger_match_id=103,
                signal_type="B_BUY",
                condition_key="BUY:D",
            ),
            sample_outbox_row(
                event_id="evt_pending",
                event_type="TriggerPendingMarketData",
                trigger_match_id=104,
                signal_type="B_BUY",
                condition_key="BUY:D",
                source_event_type="MarketDataDelayed",
                data_quality_status="delayed",
            ),
        ]
        fresh_plan = build_action_consumer_run_once_dry_run_report_from_rows(
            trigger_run_id="trigger_r4",
            action_run_id="action_r4",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_r4", "for_trade_date": "20260525"},
            outbox_rows=rows,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
            baseline_report=n4_execute_baseline_report(
                run_id="trigger_r4",
                outbox_count=4,
                by_event_type={"TriggerMatched": 3, "TriggerPendingMarketData": 1},
                by_signal_type={"B_BUY": 3, "S_SELL": 1},
            ),
            stage="N5-R4",
            expected_read_event_count=4,
            require_period_trigger_baseline_trace=True,
            sample_limit=4,
        )
        report = build_execute_preflight_report(
            trigger_run_id="trigger_r4",
            action_run_id="action_r4",
            consumer_name="n5_action_consumer_v1",
            fresh_plan=fresh_plan,
            persisted_dry_run_report=fresh_plan,
            n4_execute_report_path="docs/N4_R4_synthetic_trigger_execute_report.json",
            n5_dry_run_report_path="docs/N5_R4_action_consumer_run_once_dry_run_report.json",
            action_fact_columns={
                "stock_action_fact": ["source_market_trace"],
                "index_action_fact": ["source_market_trace"],
                "board_action_fact": ["source_market_trace"],
            },
            started_at="2026-05-25T00:00:00+00:00",
            finished_at="2026-05-25T00:00:01+00:00",
            json_report_path="docs/test.json",
            markdown_report_path="docs/test.md",
        )

        self.assertTrue(report["allow_execute"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(
            report["event_type_mapping"]["by_signal_type_and_output_event_type"]["S_SELL"],
            {"ActionBlocked": 1},
        )
        self.assertEqual(
            report["event_type_mapping"]["by_signal_type_and_output_event_type"]["B_BUY"],
            {"ActionBlocked": 1},
        )
        self.assertEqual(report["event_type_mapping"]["hint_signal_action_fact_count"], 0)
        self.assertEqual(report["event_type_mapping"]["hint_condition_trace_action_fact_count"], 2)
        self.assertEqual(report["event_type_mapping"]["pending_action_fact_plan_count"], 0)
        self.assertEqual(report["trace_mapping"]["trace_present_in_action_fact_plan_count"], 2)
        self.assertEqual(report["trace_mapping"]["trace_missing_in_action_fact_plan_count"], 0)
        self.assertEqual(report["trace_mapping"]["dedicated_period_trace_column_count"], 0)


def guard_counts() -> dict[str, dict[str, object]]:
    counts = {
        "common_event_outbox": {"exists": True, "row_count": 4, "status": "present"},
    }
    for table_name in ACTION_EVENT_GUARD_TABLES:
        counts[table_name] = {"exists": True, "row_count": 0, "status": "present"}
    return counts


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
    event_id: str,
    event_type: str = "TriggerMatched",
    trigger_match_id: int,
    signal_type: str,
    condition_key: str,
    original_condition_key: str | None = None,
    direction: str = "buy",
    source_event_type: str = "MinuteBarClosed",
    data_quality_status: str = "passed",
    identity_key: str = "stock:SH:600000",
    trigger_mark_candidate: str = "normal",
    projection_30m_type: str = "none",
) -> dict[str, object]:
    payload = {
        "run_id": "trigger_r4",
        "source_event_id": f"source_{event_id}",
        "source_event_type": source_event_type,
        "source_condition_run_id": "condition_run",
        "source_market_data_run_id": "market_run",
        "trigger_match_id": trigger_match_id,
        "trigger_state_id": 200,
        "identity_key": identity_key,
        "asset_kind": "stock",
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
            "required_period_not_ready": [],
        },
        "synthetic_sample_event": True,
    }
    return {
        "outbox_id": trigger_match_id,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "v1",
        "trade_date": "20260525",
        "asset_kind": payload["asset_kind"],
        "identity_key": payload["identity_key"],
        "event_time": "2026-05-25T02:30:00+00:00",
        "source_layer": "N4_trigger",
        "source_run_id": "trigger_r4",
        "dedup_key": f"dedup_{event_id}",
        "partition_key": identity_key,
        "payload_json": payload,
        "status": "pending",
    }


if __name__ == "__main__":
    unittest.main()
