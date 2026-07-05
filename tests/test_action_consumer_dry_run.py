import unittest

from ashare_v3.action.consumer_dry_run import (
    build_action_consumer_dry_run_report_from_rows,
    build_consumer_plan,
    empty_inbox_keys,
    summarize_consumer_plan,
)


class ActionConsumerDryRunTest(unittest.TestCase):
    def test_consumer_orders_by_partition_time_outbox_and_event_id(self) -> None:
        rows = [
            sample_outbox_row(event_id="evt_b_late", partition_key="stock:SH:600002", outbox_id=3, event_time="2026-05-25T02:02:00+00:00"),
            sample_outbox_row(event_id="evt_a_late", partition_key="stock:SH:600001", outbox_id=2, event_time="2026-05-25T02:02:00+00:00"),
            sample_outbox_row(event_id="evt_a_early", partition_key="stock:SH:600001", outbox_id=1, event_time="2026-05-25T02:01:00+00:00"),
        ]

        plan = build_consumer_plan(
            rows=rows,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=empty_inbox_keys(),
            existing_checkpoints={},
        )

        self.assertEqual(
            [item["event_id"] for item in plan["event_plans"]],
            ["evt_a_early", "evt_a_late", "evt_b_late"],
        )

    def test_duplicate_events_are_skipped_before_candidate_mapping(self) -> None:
        rows = [
            sample_outbox_row(event_id="evt_dup", outbox_id=1),
            sample_outbox_row(event_id="evt_dup", outbox_id=2),
        ]
        report = build_action_consumer_dry_run_report_from_rows(
            trigger_run_id="trigger_run",
            action_run_id="action_run",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_run", "for_trade_date": "20260525"},
            outbox_rows=rows,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["consumer_plan_summary"]["planned_receive_count"], 1)
        self.assertEqual(report["consumer_plan_summary"]["skipped_count"], 1)
        self.assertEqual(
            report["consumer_plan_summary"]["skip_reasons"],
            {"duplicate_dedup_key_in_batch": 1, "duplicate_event_id_in_batch": 1},
        )
        self.assertEqual(report["action_candidate_summary"]["candidate_count"], 1)

    def test_existing_inbox_event_is_skipped_idempotently(self) -> None:
        rows = [sample_outbox_row(event_id="evt_existing")]
        existing = {"event_ids": {"evt_existing"}, "consumer_dedup_keys": set()}
        plan = build_consumer_plan(
            rows=rows,
            consumer_name="n5_action_consumer_v1",
            existing_inbox_keys=existing,
            existing_checkpoints={},
        )
        summary = summarize_consumer_plan(plan)

        self.assertEqual(summary["planned_receive_count"], 0)
        self.assertEqual(summary["skipped_count"], 1)
        self.assertEqual(summary["skip_reasons"], {"existing_inbox_event_id": 1})

    def test_checkpoint_plan_is_generated_but_not_executed(self) -> None:
        rows = [
            sample_outbox_row(event_id="evt_buy_hint", signal_type="BUY_HINT", condition_key="BUY_HINT"),
            sample_outbox_row(
                event_id="evt_sell_hint",
                signal_type="SELL_HINT",
                condition_key="SELL_HINT",
                direction="sell",
                partition_key="stock:SH:600001",
            ),
        ]
        report = build_action_consumer_dry_run_report_from_rows(
            trigger_run_id="trigger_run",
            action_run_id="action_run",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_run", "for_trade_date": "20260525"},
            outbox_rows=rows,
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["consumer_plan_summary"]["would_insert_inbox_count"], 2)
        self.assertEqual(report["consumer_plan_summary"]["would_update_checkpoint_count"], 2)
        self.assertEqual(report["consumer_plan_summary"]["checkpoint_write_plan_count"], 2)
        self.assertTrue(all(not row["executed"] for row in report["checkpoint_write_plan"]))
        self.assertFalse(report["side_effects"]["common_event_inbox_updated"])
        self.assertFalse(report["side_effects"]["consumer_checkpoint_updated"])

    def test_pending_market_data_maps_to_quality_plan_only(self) -> None:
        report = build_action_consumer_dry_run_report_from_rows(
            trigger_run_id="trigger_run",
            action_run_id="action_run",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_run", "for_trade_date": "20260525"},
            outbox_rows=[
                sample_outbox_row(
                    event_id="evt_pending",
                    event_type="TriggerPendingMarketData",
                    source_event_type="MarketDataMissing",
                    data_quality_status="missing",
                )
            ],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["action_candidate_summary"]["quality_plan_count"], 1)
        self.assertEqual(report["action_candidate_summary"]["pending_generates_action_event_count"], 0)

    def test_buy_hint_and_sell_hint_survive_consumer_dry_run(self) -> None:
        report = build_action_consumer_dry_run_report_from_rows(
            trigger_run_id="trigger_run",
            action_run_id="action_run",
            consumer_name="n5_action_consumer_v1",
            trigger_run={"run_id": "trigger_run", "for_trade_date": "20260525"},
            outbox_rows=[
                sample_outbox_row(event_id="evt_buy_hint", signal_type="BUY_HINT", condition_key="BUY_HINT"),
                sample_outbox_row(
                    event_id="evt_sell_hint",
                    signal_type="SELL_HINT",
                    condition_key="SELL_HINT",
                    direction="sell",
                    partition_key="stock:SH:600001",
                ),
            ],
            before_row_counts=guard_counts(),
            after_row_counts=guard_counts(),
        )

        self.assertEqual(report["consumer_plan_summary"]["buy_hint_accepted_count"], 1)
        self.assertEqual(report["consumer_plan_summary"]["sell_hint_accepted_count"], 1)
        self.assertEqual(report["action_candidate_summary"]["buy_hint_candidate_count"], 1)
        self.assertEqual(report["action_candidate_summary"]["sell_hint_candidate_count"], 1)


def guard_counts() -> dict[str, dict[str, object]]:
    return {
        "common_event_outbox": {"exists": True, "row_count": 3, "status": "present"},
        "common_event_inbox": {"exists": True, "row_count": 0, "status": "present"},
        "common_event_consumer_checkpoint": {"exists": True, "row_count": 0, "status": "present"},
    }


def sample_outbox_row(
    *,
    event_id: str = "evt_trigger",
    event_type: str = "TriggerMatched",
    signal_type: str = "BUY_HINT",
    condition_key: str = "BUY_HINT",
    direction: str = "buy",
    source_event_type: str = "MinuteBarClosed",
    data_quality_status: str = "passed",
    partition_key: str = "stock:SH:600000",
    outbox_id: int = 1,
    event_time: str = "2026-05-25T02:30:00+00:00",
) -> dict[str, object]:
    payload = {
        "run_id": "trigger_run",
        "source_event_id": f"source_{event_id}",
        "source_event_type": source_event_type,
        "source_condition_run_id": "condition_run",
        "source_market_data_run_id": "market_run",
        "trigger_match_id": 100,
        "trigger_state_id": 200,
        "identity_key": partition_key,
        "asset_kind": "stock",
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "trigger_period": "30m" if signal_type in {"B_BUY_30M_VOL", "S_SELL_30M_SHRINK", "BUY_HINT", "SELL_HINT"} else "D",
        "trigger_bucket": "30m_1000_1030",
        "data_quality_status": data_quality_status,
        "synthetic_sample_event": True,
    }
    return {
        "outbox_id": outbox_id,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "v1",
        "trade_date": "20260525",
        "asset_kind": payload["asset_kind"],
        "identity_key": payload["identity_key"],
        "event_time": event_time,
        "source_layer": "N4_trigger",
        "source_run_id": "trigger_run",
        "dedup_key": f"dedup_{event_id}",
        "partition_key": partition_key,
        "payload_json": payload,
        "status": "pending",
    }


if __name__ == "__main__":
    unittest.main()
