import unittest

from ashare_v3.condition.basis import count_quality_severities
from ashare_v3.market.preload_plan import (
    EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
    PRELOAD_STATUS_TABLES,
    build_n2_blocked_report,
    build_preload_pull_batches,
    build_preload_quality_items,
    build_preload_status_plan_rows,
    build_persisted_subscription_quality_items,
    normalize_subscription_row,
    previous_day_subscriptions,
)


class PreviousDayMinutePreloadPlanTest(unittest.TestCase):
    def test_previous_day_subscriptions_are_selected_and_grouped_by_asset(self) -> None:
        report = sample_subscription_report()
        subscriptions = previous_day_subscriptions(report)

        self.assertEqual(len(subscriptions), 3)
        rows = build_preload_status_plan_rows(
            subscriptions=subscriptions,
            expected_bar_count=EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["target_table"], PRELOAD_STATUS_TABLES["stock"])
        self.assertEqual(rows[0]["expected_bar_count"], 240)
        self.assertEqual(rows[0]["source_scope_ids"], [1, 2])
        self.assertEqual(rows[0]["source_condition_pool_ids"], [101, 102])

        batches = build_preload_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
            expected_bar_count=EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
        )
        self.assertEqual(len(batches), 3)
        self.assertEqual(
            {row["asset_kind"]: row["estimated_bar_row_count"] for row in batches},
            {"board": 240, "index": 240, "stock": 240},
        )
        self.assertEqual(
            {row["asset_kind"]: row["expected_minute_bar_rows"] for row in batches},
            {"board": 240, "index": 240, "stock": 240},
        )
        self.assertEqual(batches[0]["source_adapter_plan"]["adapter_call_planned"], False)
        self.assertTrue(all(row["execute_allowed"] is False for row in batches))

    def test_wrong_previous_day_date_is_p0_blocker(self) -> None:
        report = sample_subscription_report()
        subscriptions = previous_day_subscriptions(report)
        bad_subscriptions = [{**row, "data_trade_date": "20260521"} for row in subscriptions]
        batches = build_preload_pull_batches(
            subscription_report=report,
            subscriptions=bad_subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
            expected_bar_count=EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
        )
        items = build_preload_quality_items(
            subscription_report=report,
            subscriptions=bad_subscriptions,
            pull_batches=batches,
            expected_previous_day_minute_date="20260522",
        )
        failed_codes = {item["gate_code"] for item in items if item["status"] == "failed"}

        self.assertIn("previous_day_subscription_trade_date_matches_expected", failed_codes)
        self.assertGreater(count_quality_severities(items)["P0"], 0)

    def test_clean_subscription_and_pull_plans_are_execute_ready_with_carried_p1(self) -> None:
        report = sample_subscription_report()
        report["quality"]["p1_count"] = 1
        subscriptions = previous_day_subscriptions(report)
        batches = build_preload_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
            expected_bar_count=EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
        )
        items = build_preload_quality_items(
            subscription_report=report,
            subscriptions=subscriptions,
            pull_batches=batches,
            expected_previous_day_minute_date="20260522",
        )

        self.assertEqual(count_quality_severities(items), {"P0": 0, "P1": 1, "P2": 0})

    def test_runtime_table_and_event_outbox_targets_are_p0_blockers(self) -> None:
        report = sample_subscription_report()
        subscriptions = previous_day_subscriptions(report)
        batches = build_preload_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
            expected_bar_count=EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
        )
        batches[0]["estimated_write_tables"] = ["stock_minute_bar_1m_runtime", "common_event_outbox"]

        items = build_preload_quality_items(
            subscription_report=report,
            subscriptions=subscriptions,
            pull_batches=batches,
            expected_previous_day_minute_date="20260522",
        )
        failed_codes = {item["gate_code"] for item in items if item["status"] == "failed"}

        self.assertIn("n3a_no_runtime_table_names", failed_codes)
        self.assertIn("n3a_no_event_outbox_write_plan", failed_codes)

    def test_persisted_subscription_quality_requires_clean_n3_6_run(self) -> None:
        items = build_persisted_subscription_quality_items(
            run_row={
                "mode": "execute",
                "status": "passed",
                "p0_count": 0,
                "p1_count": 1,
                "p2_count": 0,
                "market_data_pulled": False,
                "market_data_fact_written": False,
                "downstream_layers_touched": False,
                "worker_started": False,
            },
            subscription_rows=[{"subscription_id": 1}],
            previous_rows=[{"subscription_id": 1}],
            pull_plan_rows=[{"pull_plan_id": 1}],
            source_quality_rows=[],
        )

        self.assertEqual(count_quality_severities(items), {"P0": 0, "P1": 1, "P2": 0})

    def test_normalize_subscription_row_preserves_persisted_ref(self) -> None:
        row = normalize_subscription_row(
            {
                "subscription_id": 10,
                "raw_json": {"subscription_ref": "dry_run:subscription:10", "source_scope_refs": ["scope:1"]},
            }
        )

        self.assertEqual(row["subscription_ref"], "dry_run:subscription:10")
        self.assertEqual(row["source_scope_refs"], ["scope:1"])

    def test_n2_scope_block_returns_handoff_prompt(self) -> None:
        blocked_report = build_n2_blocked_report(
            {
                **sample_subscription_report(),
                "blocked": True,
                "passed": False,
                "quality": {
                    "p0_count": 1,
                    "items": [
                        {
                            "status": "failed",
                            "gate_code": "previous_day_minute_date_equals_prev_trade_date",
                            "expected_value": "20260522",
                            "actual_value": "stock_minute_target_scope:1",
                        }
                    ],
                },
            }
        )

        self.assertTrue(blocked_report["n2_scope_error"])
        self.assertIn("blocked_by_layer=N2_condition", blocked_report["n2_handoff_prompt"])
        self.assertIn("source_layer=N3_market_data", blocked_report["n2_handoff_prompt"])


def sample_subscription_report() -> dict[str, object]:
    return {
        "market_data_run_id": "market_data_subscription_20260525_test_execute",
        "source_condition_run_id": "condition_layer_20260522_to_20260525_test_execute",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "source_scope_row_count": 4,
        "candidate_row_count": 9,
        "subscription_row_count": 6,
        "subscription_object_count": 3,
        "required_data_kind_counts": {
            "minute_bar_1m": 1,
            "previous_day_minute_bar_1m": 3,
            "realtime_daily_snapshot": 2,
        },
        "dedup_ratio": 0.666667,
        "passed": True,
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
        "market_data_subscription_dedup": {
            "rows": [
                sample_subscription(
                    subscription_ref="dry_run:subscription:1",
                    asset_kind="stock",
                    identity_key="stock:SH:600000",
                    code="600000",
                    exchange="SH",
                    source_scope_ids=[1, 2],
                    source_condition_pool_ids=[101, 102],
                ),
                sample_subscription(
                    subscription_ref="dry_run:subscription:2",
                    asset_kind="index",
                    identity_key="index:SH:000905",
                    code="000905",
                    exchange="SH",
                    source_scope_ids=[11],
                    source_condition_pool_ids=[201],
                ),
                sample_subscription(
                    subscription_ref="dry_run:subscription:3",
                    asset_kind="board",
                    identity_key="board:TDX:881001",
                    code="881001",
                    exchange="TDX",
                    source_scope_ids=[21],
                    source_condition_pool_ids=[301],
                ),
                {
                    **sample_subscription(
                        subscription_ref="dry_run:subscription:4",
                        asset_kind="stock",
                        identity_key="stock:SH:600000",
                        code="600000",
                        exchange="SH",
                        source_scope_ids=[1, 2],
                        source_condition_pool_ids=[101, 102],
                    ),
                    "required_data_kind": "realtime_daily_snapshot",
                    "data_trade_date": "20260525",
                },
            ]
        },
    }


def sample_subscription(
    *,
    subscription_ref: str,
    asset_kind: str,
    identity_key: str,
    code: str,
    exchange: str,
    source_scope_ids: list[int],
    source_condition_pool_ids: list[int],
) -> dict[str, object]:
    return {
        "subscription_ref": subscription_ref,
        "run_id": "market_data_subscription_20260525_test_dry_run",
        "source_condition_run_id": "condition_layer_20260522_to_20260525_test_execute",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": exchange,
        "code": code,
        "display_code": code,
        "name": code,
        "required_data_kind": "previous_day_minute_bar_1m",
        "data_trade_date": "20260522",
        "source_scope_ids": source_scope_ids,
        "source_condition_pool_ids": source_condition_pool_ids,
        "condition_keys": ["BUY_HINT"],
        "directions": ["buy"],
        "allowed_signal_types": ["BUY_HINT"],
    }


def sample_pull_plan_rows() -> list[dict[str, object]]:
    return [
        {
            "pull_plan_id": 1,
            "asset_kind": "board",
            "data_trade_date": "20260522",
            "adapter_name": "BoardMarketDataAdapter",
            "subscription_count": 1,
            "object_count": 1,
            "execute_allowed": False,
            "plan_status": "planned",
        },
        {
            "pull_plan_id": 2,
            "asset_kind": "index",
            "data_trade_date": "20260522",
            "adapter_name": "IndexMarketDataAdapter",
            "subscription_count": 1,
            "object_count": 1,
            "execute_allowed": False,
            "plan_status": "planned",
        },
        {
            "pull_plan_id": 3,
            "asset_kind": "stock",
            "data_trade_date": "20260522",
            "adapter_name": "StockMarketDataAdapter",
            "subscription_count": 1,
            "object_count": 1,
            "execute_allowed": False,
            "plan_status": "planned",
        },
    ]


if __name__ == "__main__":
    unittest.main()
