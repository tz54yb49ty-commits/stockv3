import unittest

from ashare_v3.condition.basis import count_quality_severities
from ashare_v3.market.realtime_snapshot_plan import (
    REALTIME_SNAPSHOT_TABLES,
    SNAPSHOT_EVENT_TYPES,
    build_market_display_event_contract,
    build_realtime_snapshot_pull_batches,
    build_realtime_snapshot_quality_items,
    build_snapshot_execute_event_contract,
    realtime_snapshot_subscriptions,
)


class RealtimeSnapshotPlanTest(unittest.TestCase):
    def test_realtime_subscriptions_are_selected_and_grouped(self) -> None:
        report = sample_subscription_report()
        subscriptions = realtime_snapshot_subscriptions(report)

        self.assertEqual(len(subscriptions), 3)

        batches = build_realtime_snapshot_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
        )

        self.assertEqual(len(batches), 3)
        self.assertEqual(
            {row["asset_kind"]: row["target_snapshot_table"] for row in batches},
            REALTIME_SNAPSHOT_TABLES,
        )
        self.assertTrue(all(row["execute_allowed"] is False for row in batches))
        self.assertTrue(all(row["execute_contract"]["adapter_call_planned_in_dry_run"] is False for row in batches))

    def test_clean_plan_carries_preload_missing_as_p1_not_p0(self) -> None:
        report = sample_subscription_report()
        report["quality"]["p1_count"] = 1
        subscriptions = realtime_snapshot_subscriptions(report)
        batches = build_realtime_snapshot_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
        )
        items = build_realtime_snapshot_quality_items(
            subscription_report=report,
            subscriptions=subscriptions,
            pull_batches=batches,
            preload_audit=sample_preload_audit(missing_count=9),
        )

        counts = count_quality_severities(items)
        failed_p0 = [item for item in items if item["severity"] == "P0" and item["status"] == "failed"]
        warning_codes = {item["gate_code"] for item in items if item["status"] == "warning"}

        self.assertEqual(failed_p0, [])
        self.assertEqual(counts["P0"], 0)
        self.assertGreaterEqual(counts["P1"], 2)
        self.assertIn("n3_b0_preload_missing_carried_non_blocking", warning_codes)

    def test_missing_realtime_pull_plan_is_p0(self) -> None:
        report = sample_subscription_report()
        subscriptions = realtime_snapshot_subscriptions(report)
        batches = build_realtime_snapshot_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows()[:1],
        )
        items = build_realtime_snapshot_quality_items(
            subscription_report=report,
            subscriptions=subscriptions,
            pull_batches=batches,
            preload_audit=sample_preload_audit(),
        )

        failed_codes = {item["gate_code"] for item in items if item["status"] == "failed"}
        self.assertIn("realtime_snapshot_pull_plan_asset_coverage", failed_codes)
        self.assertGreater(count_quality_severities(items)["P0"], 0)

    def test_event_contract_uses_allowed_n3_events_and_no_user_prefix(self) -> None:
        snapshot_contract = build_snapshot_execute_event_contract()
        display_contract = build_market_display_event_contract()

        self.assertIn("MarketSnapshotUpdated", SNAPSHOT_EVENT_TYPES)
        self.assertIn("MarketDisplaySnapshotUpdated", SNAPSHOT_EVENT_TYPES)
        self.assertTrue(display_contract["not_user_event"])
        self.assertNotIn("UserMarketProjectionUpdated", str(snapshot_contract))
        self.assertNotIn("UserMarketProjectionUpdated", str(display_contract))
        self.assertIn("snapshot_id", snapshot_contract["market_snapshot_updated"]["payload_required_fields"])
        self.assertIn("quality_item_id", snapshot_contract["quality_events"][0]["payload_required_fields"])

    def test_no_outbox_plan_marks_execute_contract_fact_only(self) -> None:
        report = sample_subscription_report()
        subscriptions = realtime_snapshot_subscriptions(report)

        batches = build_realtime_snapshot_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
            writes_outbox=False,
        )

        self.assertTrue(all(row["execute_contract"]["writes_outbox"] is False for row in batches))
        self.assertTrue(
            all(
                row["execute_contract"]["write_market_snapshot_updated_outbox_same_transaction"] is False
                for row in batches
            )
        )

    def test_no_outbox_event_contract_disables_snapshot_events(self) -> None:
        snapshot_contract = build_snapshot_execute_event_contract(writes_outbox=False)
        display_contract = build_market_display_event_contract(writes_outbox=False)

        self.assertFalse(snapshot_contract["writes_outbox"])
        self.assertFalse(snapshot_contract["market_snapshot_updated"]["generated"])
        self.assertEqual(snapshot_contract["quality_events"], [])
        self.assertIn("MarketSnapshotUpdated", snapshot_contract["disabled_outbox_events"])
        self.assertFalse(display_contract["generated"])
        self.assertEqual(display_contract["payload_required_fields"], [])


def sample_subscription_report() -> dict[str, object]:
    return {
        "market_data_run_id": "market_data_subscription_20260525_test_execute",
        "source_condition_run_id": "condition_layer_test",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "passed": True,
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
        "market_data_subscription_dedup": {
            "rows": [
                subscription_row("stock", "stock:SH:600000", "600000"),
                subscription_row("index", "index:SH:000905", "000905"),
                subscription_row("board", "board:TDX:881001", "881001"),
                {**subscription_row("stock", "stock:SH:600000", "600000"), "required_data_kind": "minute_bar_1m"},
            ]
        },
    }


def subscription_row(asset_kind: str, identity_key: str, code: str) -> dict[str, object]:
    return {
        "subscription_id": {"stock": 1, "index": 2, "board": 3}[asset_kind],
        "subscription_ref": f"subscription:{asset_kind}",
        "run_id": "market_data_subscription_20260525_test_execute",
        "source_condition_run_id": "condition_layer_test",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": "SH" if asset_kind != "board" else "TDX",
        "code": code,
        "display_code": code,
        "name": code,
        "required_data_kind": "realtime_daily_snapshot",
        "data_trade_date": "20260525",
        "source_scope_ids": [1],
        "source_condition_pool_ids": [101],
    }


def sample_pull_plan_rows() -> list[dict[str, object]]:
    return [
        pull_plan_row("board", 1),
        pull_plan_row("index", 2),
        pull_plan_row("stock", 3),
    ]


def pull_plan_row(asset_kind: str, pull_plan_id: int) -> dict[str, object]:
    return {
        "pull_plan_id": pull_plan_id,
        "asset_kind": asset_kind,
        "data_trade_date": "20260525",
        "adapter_name": {
            "stock": "StockMarketDataAdapter",
            "index": "IndexMarketDataAdapter",
            "board": "BoardMarketDataAdapter",
        }[asset_kind],
        "subscription_count": 1,
        "object_count": 1,
        "execute_allowed": False,
        "plan_status": "planned",
    }


def sample_preload_audit(missing_count: int = 0) -> dict[str, object]:
    return {
        "preload_run_id": "previous_day_minute_preload_test",
        "run_present": True,
        "status": "passed",
        "p0_count": 0,
        "p1_count": 2 if missing_count else 0,
        "p2_count": 0,
        "missing_object_count": missing_count,
        "missing_samples": [{"identity_key": "stock:BJ:920045"}] if missing_count else [],
    }


if __name__ == "__main__":
    unittest.main()
