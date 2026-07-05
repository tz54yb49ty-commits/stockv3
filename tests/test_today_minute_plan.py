import unittest
from datetime import datetime

from ashare_v3.market.today_minute_plan import (
    ASIA_SHANGHAI,
    MINUTE_FACT_TABLES,
    build_expected_bar_times,
    build_planned_today_minute_run_id,
    build_today_minute_pull_batches,
    build_today_minute_quality_items,
    build_today_minute_rollback_sql,
    calculate_latest_closed_minute,
    today_minute_source_quality_summary,
    today_minute_subscriptions,
)


class TodayMinutePlanTest(unittest.TestCase):
    def test_latest_closed_minute_uses_previous_label_inside_session(self) -> None:
        as_of = datetime(2026, 5, 25, 14, 12, 30, tzinfo=ASIA_SHANGHAI)

        latest = calculate_latest_closed_minute(as_of=as_of, trade_date="20260525")

        self.assertEqual(latest, datetime(2026, 5, 25, 14, 11, tzinfo=ASIA_SHANGHAI))

    def test_latest_closed_minute_skips_lunch_window(self) -> None:
        as_of = datetime(2026, 5, 25, 12, 15, 0, tzinfo=ASIA_SHANGHAI)

        latest = calculate_latest_closed_minute(as_of=as_of, trade_date="20260525")

        self.assertEqual(latest, datetime(2026, 5, 25, 11, 29, tzinfo=ASIA_SHANGHAI))

    def test_expected_bar_times_skip_lunch_and_stop_at_closed_minute(self) -> None:
        latest = datetime(2026, 5, 25, 13, 2, tzinfo=ASIA_SHANGHAI)

        bars = build_expected_bar_times(trade_date="20260525", latest_closed_minute=latest)
        labels = [bar.strftime("%H:%M") for bar in bars]

        self.assertEqual(len(bars), 123)
        self.assertEqual(bars[0].strftime("%H:%M"), "09:30")
        self.assertEqual(bars[119].strftime("%H:%M"), "11:29")
        self.assertEqual(bars[120].strftime("%H:%M"), "13:00")
        self.assertEqual(bars[-1].strftime("%H:%M"), "13:02")
        self.assertNotIn("11:30", labels)

    def test_today_minute_subscriptions_are_selected_and_grouped(self) -> None:
        report = sample_subscription_report()
        subscriptions = today_minute_subscriptions(report)

        self.assertEqual(len(subscriptions), 3)

        latest = datetime(2026, 5, 25, 14, 11, tzinfo=ASIA_SHANGHAI)
        batches = build_today_minute_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
            latest_closed_minute=latest,
            expected_bar_count_per_object=192,
        )

        self.assertEqual(len(batches), 3)
        self.assertEqual(
            {row["asset_kind"]: row["target_minute_table"] for row in batches},
            MINUTE_FACT_TABLES,
        )
        self.assertEqual({row["asset_kind"]: row["adapter_call"] for row in batches}, {
            "stock": "bars",
            "index": "index_bars",
            "board": "index_bars",
        })
        self.assertTrue(all(row["execute_allowed"] is False for row in batches))
        self.assertTrue(all(row["execute_contract"]["writes_outbox"] is False for row in batches))
        self.assertEqual(sum(row["expected_minute_rows"] for row in batches), 576)

    def test_pull_batches_only_require_assets_with_objects(self) -> None:
        report = sample_subscription_report()
        report["market_data_subscription_dedup"]["rows"] = [
            row
            for row in report["market_data_subscription_dedup"]["rows"]
            if row.get("asset_kind") != "index"
        ]
        pull_plan_rows = [row for row in sample_pull_plan_rows() if row.get("asset_kind") != "index"]
        subscriptions = today_minute_subscriptions(report)

        latest = datetime(2026, 5, 25, 14, 11, tzinfo=ASIA_SHANGHAI)
        batches = build_today_minute_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=pull_plan_rows,
            latest_closed_minute=latest,
            expected_bar_count_per_object=192,
        )

        self.assertEqual({row["asset_kind"] for row in batches}, {"stock", "board"})
        self.assertNotIn("index", {row["asset_kind"] for row in batches})
        quality_items = build_today_minute_quality_items(
            subscription_report=report,
            subscriptions=subscriptions,
            pull_batches=batches,
            target_audit={"run_exists": False, "target_run_row_counts": {}},
            latest_closed_minute=latest,
            expected_bar_count_per_object=192,
            requested_for_trade_date="20260525",
        )
        failed_codes = {item["gate_code"] for item in quality_items if item["status"] == "failed"}
        self.assertNotIn("n3_c0_today_minute_pull_plan_asset_coverage", failed_codes)

    def test_run_id_and_rollback_contract_are_scoped_to_today_minute_run(self) -> None:
        source_run_id = "market_data_subscription_20260525_condition_layer_test_execute"
        latest = datetime(2026, 5, 25, 14, 11, tzinfo=ASIA_SHANGHAI)

        run_id = build_planned_today_minute_run_id(
            for_trade_date="20260525",
            latest_closed_minute=latest,
            source_run_id=source_run_id,
        )
        rollback_sql = build_today_minute_rollback_sql(run_id)

        self.assertEqual(run_id, f"today_minute_bar_1m_20260525_until_1411__{source_run_id}")
        self.assertIn("DELETE FROM stock_minute_bar_1m", rollback_sql)
        self.assertIn("is_previous_day_preload = false", rollback_sql)
        self.assertIn("DELETE FROM common_market_data_quality_item", rollback_sql)
        self.assertIn("DELETE FROM common_market_data_run", rollback_sql)
        self.assertNotIn("DELETE FROM common_event_outbox", rollback_sql)
        self.assertNotIn("UPDATE common_event_outbox", rollback_sql)

    def test_today_minute_rollback_hard_fails_before_first_delete(self) -> None:
        run_id = "today_minute_bar_1m_20260525_until_1411__market_data_subscription_test"
        rollback_sql = build_today_minute_rollback_sql(run_id)

        self.assertIn("RAISE EXCEPTION", rollback_sql)
        self.assertLess(rollback_sql.index("RAISE EXCEPTION"), rollback_sql.index("DELETE FROM"))
        self.assertIn("common_event_outbox", rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("closed_30m", rollback_sql)
        self.assertIn("realtime_projection", rollback_sql)
        self.assertIn("common_trigger_match", rollback_sql)
        self.assertIn("common_trigger_state", rollback_sql)
        self.assertIn("trigger_state_refs", rollback_sql)
        self.assertIn("common_action_event", rollback_sql)
        self.assertIn("downstream_layers_touched", rollback_sql)
        self.assertIn("worker_started", rollback_sql)

    def test_today_minute_source_quality_ignores_previous_day_only_p0(self) -> None:
        report = sample_subscription_report()
        report["passed"] = False
        report["quality"] = {
            "p0_count": 2,
            "p1_count": 0,
            "p2_count": 0,
            "items": [
                {
                    "severity": "P0",
                    "status": "failed",
                    "gate_code": "n3_6_previous_day_subscription_rows_present",
                },
                {
                    "severity": "P0",
                    "status": "failed",
                    "gate_code": "n3_6_previous_day_pull_plan_rows_present",
                },
            ],
        }
        subscriptions = today_minute_subscriptions(report)
        latest = datetime(2026, 5, 25, 15, 0, tzinfo=ASIA_SHANGHAI)
        batches = build_today_minute_pull_batches(
            subscription_report=report,
            subscriptions=subscriptions,
            persisted_pull_plans=sample_pull_plan_rows(),
            latest_closed_minute=latest,
            expected_bar_count_per_object=240,
        )

        source_quality = today_minute_source_quality_summary(report)
        quality_items = build_today_minute_quality_items(
            subscription_report=report,
            subscriptions=subscriptions,
            pull_batches=batches,
            target_audit={"run_exists": False, "target_run_row_counts": {}},
            latest_closed_minute=latest,
            expected_bar_count_per_object=240,
            requested_for_trade_date="20260525",
        )

        self.assertEqual(source_quality["p0_count"], 0)
        self.assertNotIn(
            "n3_c0_source_subscription_run_passed",
            {item["gate_code"] for item in quality_items if item["status"] == "failed"},
        )

    def test_today_minute_source_quality_keeps_real_source_p0(self) -> None:
        report = sample_subscription_report()
        report["passed"] = False
        report["quality"] = {
            "p0_count": 1,
            "p1_count": 0,
            "p2_count": 0,
            "items": [
                {
                    "severity": "P0",
                    "status": "failed",
                    "gate_code": "n3_6_market_data_run_status_passed",
                }
            ],
        }

        source_quality = today_minute_source_quality_summary(report)

        self.assertEqual(source_quality["p0_count"], 1)


def sample_subscription_report() -> dict[str, object]:
    return {
        "market_data_run_id": "market_data_subscription_20260525_condition_layer_test_execute",
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
                {**subscription_row("stock", "stock:SH:600000", "600000"), "required_data_kind": "realtime_daily_snapshot"},
            ]
        },
    }


def subscription_row(asset_kind: str, identity_key: str, code: str) -> dict[str, object]:
    return {
        "subscription_id": {"stock": 1, "index": 2, "board": 3}[asset_kind],
        "run_id": "market_data_subscription_20260525_condition_layer_test_execute",
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
        "required_data_kind": "minute_bar_1m",
        "data_trade_date": "20260525",
        "source_scope_ids": [1],
        "source_condition_pool_ids": [101],
    }


def sample_pull_plan_rows() -> list[dict[str, object]]:
    return [
        pull_plan_row("board", 28),
        pull_plan_row("index", 31),
        pull_plan_row("stock", 34),
    ]


def pull_plan_row(asset_kind: str, pull_plan_id: int) -> dict[str, object]:
    return {
        "pull_plan_id": pull_plan_id,
        "asset_kind": asset_kind,
        "required_data_kind": "minute_bar_1m",
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


if __name__ == "__main__":
    unittest.main()
