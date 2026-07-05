import unittest

from ashare_v3.market.subscription_plan import (
    build_market_data_subscription_plan,
    build_trade_calendar_quality_items,
    required_data_kinds_for_scope_row,
    select_active_condition_run,
)


class MarketDataSubscriptionPlanTest(unittest.TestCase):
    def test_required_data_kinds_are_expanded_from_scope_flags(self) -> None:
        row = {
            "for_trade_date": "20260525",
            "previous_day_minute_date": "20260522",
            "daily_snapshot_required": True,
            "minute_required": True,
            "previous_day_minute_required": True,
        }

        self.assertEqual(
            required_data_kinds_for_scope_row(row),
            [
                ("realtime_daily_snapshot", "20260525"),
                ("minute_bar_1m", "20260525"),
                ("previous_day_minute_bar_1m", "20260522"),
            ],
        )

    def test_report_dedups_subscription_rows_and_preserves_trace_arrays(self) -> None:
        report = build_market_data_subscription_plan(
            active_run=sample_active_run(),
            scope_rows_by_asset={
                "stock": [
                    sample_scope_row(
                        asset_kind="stock",
                        source_scope_id=1,
                        source_condition_pool_id=101,
                        identity_key="stock:SH:600000",
                        code="600000",
                        exchange="SH",
                        direction="buy",
                        condition_key="BUY_HINT",
                        allowed_signal_types=["BUY_HINT"],
                        daily=True,
                        minute=True,
                        previous=True,
                    ),
                    sample_scope_row(
                        asset_kind="stock",
                        source_scope_id=2,
                        source_condition_pool_id=102,
                        identity_key="stock:SH:600000",
                        code="600000",
                        exchange="SH",
                        direction="sell",
                        condition_key="SELL_HINT",
                        allowed_signal_types=["SELL_HINT"],
                        daily=True,
                        minute=True,
                        previous=True,
                    ),
                ],
                "index": [
                    sample_scope_row(
                        asset_kind="index",
                        source_scope_id=11,
                        source_condition_pool_id=201,
                        identity_key="index:SH:000905",
                        code="000905",
                        exchange="SH",
                        direction="buy",
                        condition_key="BUY:Y,Q,M,W,D",
                        allowed_signal_types=["BUY"],
                        daily=True,
                        minute=True,
                        previous=True,
                    )
                ],
                "board": [
                    sample_scope_row(
                        asset_kind="board",
                        source_scope_id=21,
                        source_condition_pool_id=301,
                        identity_key="board:TDX:881001",
                        code="881001",
                        exchange="TDX",
                        direction="sell",
                        condition_key="SELL_HINT",
                        allowed_signal_types=["SELL_HINT"],
                        daily=True,
                        minute=True,
                        previous=True,
                    )
                ],
            },
            trade_calendar_detail={
                "trade_date": "20260525",
                "table_exists": True,
                "row_exists": True,
                "row": {
                    "trade_date": "20260525",
                    "is_open": True,
                    "prev_trade_date": "20260522",
                    "next_trade_date": "20260526",
                },
            },
            include_rows=True,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["source_scope_row_count"], 4)
        self.assertEqual(report["candidate_row_count"], 12)
        self.assertEqual(report["subscription_candidate_count"], 12)
        self.assertEqual(report["subscription_row_count"], 9)
        self.assertEqual(report["dedup_subscription_count"], 9)
        self.assertEqual(report["subscription_object_count"], 3)
        self.assertEqual(report["object_count_by_asset_kind"], {"stock": 1, "index": 1, "board": 1})
        self.assertEqual(report["previous_day_minute_required_count"], 4)
        self.assertEqual(report["previous_day_minute_required_object_count"], 3)
        self.assertEqual(report["previous_day_minute_date_counts"], {"20260522": 4})
        self.assertTrue(report["trade_calendar_detail_check"]["row_exists"])
        self.assertEqual(
            report["required_data_kind_counts"],
            {
                "minute_bar_1m": 3,
                "previous_day_minute_bar_1m": 3,
                "realtime_daily_snapshot": 3,
            },
        )
        self.assertEqual(report["dedup_ratio"], 0.75)

        subscriptions = report["market_data_subscription_dedup"]["rows"]
        stock_daily = next(
            row
            for row in subscriptions
            if row["identity_key"] == "stock:SH:600000"
            and row["required_data_kind"] == "realtime_daily_snapshot"
        )
        self.assertEqual(stock_daily["source_scope_ids"], [1, 2])
        self.assertEqual(stock_daily["source_condition_pool_ids"], [101, 102])
        self.assertEqual(stock_daily["condition_keys"], ["BUY_HINT", "SELL_HINT"])
        self.assertEqual(stock_daily["directions"], ["buy", "sell"])
        self.assertEqual(stock_daily["allowed_signal_types"], ["BUY_HINT", "SELL_HINT"])

        pull_plan = report["market_data_pull_plan"]["rows"]
        self.assertTrue(
            any(
                row["asset_kind"] == "index" and row["required_data_kind"] == "minute_bar_1m"
                for row in subscriptions
            )
        )
        self.assertTrue(
            any(
                row["asset_kind"] == "board" and row["required_data_kind"] == "minute_bar_1m"
                for row in subscriptions
            )
        )
        self.assertTrue(
            any(
                row["asset_kind"] == "stock" and row["required_data_kind"] == "previous_day_minute_bar_1m"
                for row in subscriptions
            )
        )
        self.assertTrue(
            any(
                row["asset_kind"] == "stock" and row["required_data_kind"] == "minute_bar_1m"
                for row in subscriptions
            )
        )
        self.assertEqual(len(pull_plan), 9)
        self.assertTrue(all(row["execute_allowed"] is False for row in pull_plan))

    def test_scope_contract_p0_blocks_when_previous_day_date_is_missing(self) -> None:
        report = build_market_data_subscription_plan(
            active_run=sample_active_run(),
            scope_rows_by_asset={
                "stock": [
                    sample_scope_row(
                        asset_kind="stock",
                        source_scope_id=1,
                        source_condition_pool_id=101,
                        identity_key="stock:SH:600000",
                        code="600000",
                        exchange="SH",
                        direction="buy",
                        condition_key="BUY_HINT",
                        allowed_signal_types=["BUY_HINT"],
                        daily=True,
                        minute=True,
                        previous=True,
                        previous_day_minute_date=None,
                    )
                ],
                "index": [],
                "board": [],
            },
            include_rows=True,
        )

        self.assertTrue(report["blocked"])
        self.assertGreater(report["quality"]["p0_count"], 0)
        failed_codes = {
            item["gate_code"]
            for item in report["quality"]["items"]
            if item["status"] == "failed"
        }
        self.assertIn("previous_day_minute_date_present", failed_codes)

    def test_scope_contract_accepts_n2_canonical_v2_signal_types(self) -> None:
        report = build_market_data_subscription_plan(
            active_run=sample_active_run(),
            scope_rows_by_asset={
                "stock": [
                    sample_scope_row(
                        asset_kind="stock",
                        source_scope_id=1,
                        source_condition_pool_id=101,
                        identity_key="stock:SH:600000",
                        code="600000",
                        exchange="SH",
                        direction="buy",
                        condition_key="BUY:Y,Q,M,W,D",
                        allowed_signal_types=["BUY"],
                        daily=True,
                        minute=True,
                        previous=True,
                    ),
                    sample_scope_row(
                        asset_kind="stock",
                        source_scope_id=2,
                        source_condition_pool_id=102,
                        identity_key="stock:SH:600001",
                        code="600001",
                        exchange="SH",
                        direction="buy",
                        condition_key="BUY:FULL",
                        allowed_signal_types=["BUY:FULL"],
                        daily=True,
                        minute=False,
                        previous=False,
                    ),
                    sample_scope_row(
                        asset_kind="stock",
                        source_scope_id=3,
                        source_condition_pool_id=103,
                        identity_key="stock:SH:600002",
                        code="600002",
                        exchange="SH",
                        direction="sell",
                        condition_key="SELL:FULL",
                        allowed_signal_types=["SELL:FULL"],
                        daily=True,
                        minute=False,
                        previous=False,
                    ),
                    sample_scope_row(
                        asset_kind="stock",
                        source_scope_id=4,
                        source_condition_pool_id=104,
                        identity_key="stock:SH:600003",
                        code="600003",
                        exchange="SH",
                        direction="sell",
                        condition_key="SELL:W,D",
                        allowed_signal_types=["SELL"],
                        daily=True,
                        minute=False,
                        previous=False,
                    ),
                ],
                "index": [],
                "board": [],
            },
            include_rows=True,
        )

        by_code = {item["gate_code"]: item for item in report["quality"]["items"]}
        self.assertEqual(by_code["scope_allowed_signal_types_whitelist"]["status"], "passed")
        self.assertTrue(report["passed"])

    def test_scope_contract_blocks_deprecated_legacy_signal_types_for_future_writes(self) -> None:
        report = build_market_data_subscription_plan(
            active_run=sample_active_run(),
            scope_rows_by_asset={
                "stock": [
                    sample_scope_row(
                        asset_kind="stock",
                        source_scope_id=1,
                        source_condition_pool_id=101,
                        identity_key="stock:SH:600000",
                        code="600000",
                        exchange="SH",
                        direction="buy",
                        condition_key="BUY:Y,Q,M,W,D",
                        allowed_signal_types=["B_BUY", "B_BUY_30M_VOL"],
                        daily=True,
                        minute=False,
                        previous=False,
                    )
                ],
                "index": [],
                "board": [],
            },
            include_rows=True,
        )

        by_code = {item["gate_code"]: item for item in report["quality"]["items"]}
        self.assertEqual(by_code["scope_allowed_signal_types_whitelist"]["status"], "failed")
        self.assertIn("B_BUY", by_code["scope_allowed_signal_types_whitelist"]["actual_value"])
        self.assertTrue(report["blocked"])

    def test_active_run_selection_blocks_missing_or_multiple_active_runs(self) -> None:
        active_run, items = select_active_condition_run([])
        self.assertIsNone(active_run)
        self.assertEqual(items[0]["gate_code"], "active_condition_run_unique")
        self.assertEqual(items[0]["status"], "failed")

    def test_active_run_selection_accepts_passed_active_status(self) -> None:
        passed_active = {**sample_active_run(), "status": "passed_active"}

        active_run, items = select_active_condition_run([passed_active])

        self.assertEqual(active_run, passed_active)
        by_code = {item["gate_code"]: item for item in items}
        self.assertEqual(by_code["active_condition_run_status_passed"]["status"], "passed")
        self.assertEqual(
            by_code["active_condition_run_status_passed"]["expected_value"],
            "passed/passed_active",
        )

    def test_missing_for_trade_calendar_row_is_p1_warning_not_blocker(self) -> None:
        items = build_trade_calendar_quality_items(
            {
                "trade_date": "20260525",
                "table_exists": True,
                "row_exists": False,
                "row": None,
            },
            active_run=sample_active_run(),
        )

        warning_codes = {
            item["gate_code"]
            for item in items
            if item["status"] == "warning"
        }
        failed_codes = {
            item["gate_code"]
            for item in items
            if item["status"] == "failed"
        }
        self.assertIn("for_trade_calendar_row_exists", warning_codes)
        self.assertNotIn("for_trade_calendar_row_exists", failed_codes)

        active_run, items = select_active_condition_run([sample_active_run(), {**sample_active_run(), "run_id": "other"}])
        self.assertIsNone(active_run)
        self.assertEqual(items[0]["status"], "failed")


def sample_active_run() -> dict[str, object]:
    return {
        "run_id": "condition_layer_20260522_to_20260525_test_execute",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "status": "passed",
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "source_versions": {},
    }


def sample_scope_row(
    *,
    asset_kind: str,
    source_scope_id: int,
    source_condition_pool_id: int,
    identity_key: str,
    code: str,
    exchange: str,
    direction: str,
    condition_key: str,
    allowed_signal_types: list[str],
    daily: bool,
    minute: bool,
    previous: bool,
    previous_day_minute_date: str | None = "20260522",
) -> dict[str, object]:
    return {
        "source_scope_id": source_scope_id,
        "source_scope_table": f"{asset_kind}_minute_target_scope",
        "run_id": "condition_layer_20260522_to_20260525_test_execute",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": exchange,
        "code": code,
        "display_code": code,
        "name": code,
        "lane": "stock_trade" if asset_kind == "stock" else "market_alert",
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": [],
        "allowed_signal_types": allowed_signal_types,
        "scope_source": "condition_pool",
        "source_condition_pool_id": source_condition_pool_id,
        "daily_snapshot_required": daily,
        "minute_required": minute,
        "previous_day_minute_required": previous,
        "previous_day_minute_date": previous_day_minute_date,
        "previous_day_minute_quality_required": previous,
        "market_data_consumer": "both" if minute or previous else "trigger_daily_snapshot",
        "source_version": f"{asset_kind}_daily_20260522_v1",
        "scope_status": "planned",
    }


if __name__ == "__main__":
    unittest.main()
