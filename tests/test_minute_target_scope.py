import unittest

from ashare_v3.condition.basis import DateContext
from ashare_v3.condition.scope import (
    FIXED_INDEX_CODES,
    STOCK_SCOPE_MIN_TOTAL_MV_WAN,
    build_board_condition_scope_from_pool_report,
    build_index_condition_scope_from_pool_report,
    build_scope_quality_items,
    build_stock_condition_scope_from_pool_report,
    is_stock_condition_key_scope_eligible,
    market_data_consumer_for_signal_types,
    signal_types_for_condition_key,
    signal_types_for_direction,
    scope_row_diagnostics,
    stock_total_mv_is_scope_eligible,
)


def period_trigger_baseline_json() -> dict[str, object]:
    baseline = {
        "baseline_version": "N2-R4-period-trigger-baseline-v1",
        "condition_projection_context": condition_projection_context(),
        "periods": {
            period: {
                "baseline_ready": True,
                "baseline_missing_fields": [],
                "current_open_seed": "10",
                "current_close_seed": "11",
                "current_amount_seed": "200",
                "current_trade_days_seed": 1,
                "previous_open": "12",
                "previous_close": "10",
                "previous_entity_high": "12",
                "previous_entity_low": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "amount_metric": "amount" if period == "D" else "avg_amount",
                "current_window_start": "20260501",
                "current_window_end": "20260522",
                "previous_window_start": "20260401",
                "previous_window_end": "20260430",
            }
            for period in ("Y", "Q", "M", "W", "D")
        },
    }
    baseline["period_escalation_context"] = {
        "contract_version": "N2-period-escalation-context-v1",
        "generation_mode": "directional_incremental_v1",
        "context_hash": "test-context-hash",
    }
    return baseline


def condition_projection_context() -> dict[str, object]:
    return {
        "contract_version": "N2-condition-projection-context-v1",
        "source_layer": "N2_condition",
        "status": "ready",
        "fields": {"name": "fixture", "close": "11"},
        "nullable_fields": [],
        "not_ready_reasons": [],
        "context_hash": "condition-projection-context-hash",
    }


class MinuteTargetScopeTest(unittest.TestCase):
    def test_fixed_index_codes_match_scope_contract(self) -> None:
        self.assertEqual(
            FIXED_INDEX_CODES,
            ("000905", "399303", "000001", "000852", "399001", "399006", "000300", "000016", "000688"),
        )

    def test_signal_types_for_direction_use_n2_canonical_condition_semantics(self) -> None:
        self.assertEqual(signal_types_for_direction("buy"), ["BUY"])
        self.assertEqual(signal_types_for_direction("sell"), ["SELL"])

    def test_signal_types_for_condition_key_are_canonical_and_not_action_signals(self) -> None:
        self.assertEqual(signal_types_for_condition_key("BUY:D", "buy"), ["BUY"])
        self.assertEqual(signal_types_for_condition_key("SELL:W,D", "sell"), ["SELL"])
        self.assertEqual(signal_types_for_condition_key("BUY:FULL", "buy"), ["BUY:FULL"])
        self.assertEqual(signal_types_for_condition_key("SELL:FULL", "sell"), ["SELL:FULL"])
        self.assertEqual(signal_types_for_condition_key("BUY_HINT", "buy"), ["BUY_HINT"])
        self.assertEqual(signal_types_for_condition_key("SELL_HINT", "sell"), ["SELL_HINT"])

    def test_stock_condition_key_scope_eligibility(self) -> None:
        accepted = ["BUY:D", "BUY:Y,Q,M,W,D", "SELL:W", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"]
        rejected = ["BUY:30M", "SELL:", "HINT", "POS_CLEAR", "BUY_FAIL_CLEAR"]
        for condition_key in accepted:
            self.assertTrue(is_stock_condition_key_scope_eligible(condition_key), condition_key)
        for condition_key in rejected:
            self.assertFalse(is_stock_condition_key_scope_eligible(condition_key), condition_key)

    def test_market_data_consumer_is_both_for_runtime_monitor_signals(self) -> None:
        for signal_type in ("BUY", "SELL", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"):
            self.assertEqual(market_data_consumer_for_signal_types([signal_type]), "both", signal_type)

    def test_stock_scope_does_not_add_market_value_filter(self) -> None:
        self.assertEqual(str(STOCK_SCOPE_MIN_TOTAL_MV_WAN), "0")
        self.assertTrue(stock_total_mv_is_scope_eligible("1000000"))
        self.assertTrue(stock_total_mv_is_scope_eligible("999999.99"))
        self.assertTrue(stock_total_mv_is_scope_eligible("1000000.01"))
        self.assertTrue(stock_total_mv_is_scope_eligible(None))

    def test_stock_scope_uses_condition_pool_dry_run_without_object_filter(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=False,
        )
        pool_report = {
            "run_id": "condition_pool_20260522_to_20260525_dry_run",
            "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 1},
            "pool_preview": {
                "stock": {
                    "pool_rows": [
                        {
                            "condition_pool_ref": "dry_run:stock:condition_pool:1:stock:SH:600000:BUY:D",
                            "stock_identity_key": "stock:SH:600000",
                            "code": "600000",
                            "exchange": "SH",
                            "name": "SPDB",
                            "lane": "stock_trade",
                            "direction": "buy",
                            "condition_key": "BUY:D",
                            "condition_periods": ["D"],
                            "allowed_signal_types": ["BUY"],
                            "active_target": True,
                            "total_mv": "1000000.01",
                            "period_trigger_baseline_json": period_trigger_baseline_json(),
                            "source_version": "stock_daily_20260522_v1",
                        },
                        {
                            "condition_pool_ref": "dry_run:stock:condition_pool:2:stock:SH:600001:SELL:D",
                            "stock_identity_key": "stock:SH:600001",
                            "direction": "sell",
                            "condition_key": "SELL:D",
                            "condition_periods": ["D"],
                            "allowed_signal_types": ["SELL"],
                            "active_target": True,
                            "total_mv": "1000000",
                            "period_trigger_baseline_json": period_trigger_baseline_json(),
                        },
                        {
                            "condition_pool_ref": "dry_run:stock:condition_pool:3:stock:SH:600002:BUY_HINT",
                            "stock_identity_key": "stock:SH:600002",
                            "direction": "buy",
                            "condition_key": "BUY_HINT",
                            "allowed_signal_types": ["BUY_HINT"],
                            "active_target": True,
                            "total_mv": None,
                        },
                    ]
                }
            },
        }

        scope = build_stock_condition_scope_from_pool_report(pool_report, dates)

        self.assertEqual(scope["condition_pool_source"], "condition_pool_dry_run")
        self.assertEqual(scope["condition_pool_row_count"], 3)
        self.assertEqual(scope["object_count"], 3)
        self.assertEqual(scope["scope_row_count"], 3)
        self.assertEqual(scope["excluded_below_min_total_mv_count"], 0)
        self.assertEqual(scope["missing_total_mv_count"], 1)
        row = scope["scope_rows"][0]
        self.assertIsNone(row["source_condition_pool_id"])
        self.assertEqual(row["source_condition_pool_ref"], "dry_run:stock:condition_pool:1:stock:SH:600000:BUY:D")
        self.assertTrue(row["daily_snapshot_required"])
        self.assertTrue(row["minute_required"])
        self.assertTrue(row["previous_day_minute_required"])
        self.assertEqual(row["previous_day_minute_date"], "20260522")
        self.assertTrue(row["previous_day_minute_quality_required"])
        self.assertEqual(row["market_data_consumer"], "both")
        self.assertEqual(row["raw_json"]["scope_policy"], "condition_pool_runtime_monitor_requires_minute")
        sell_row = scope["scope_rows"][1]
        self.assertEqual(sell_row["condition_key"], "SELL:D")
        self.assertTrue(sell_row["minute_required"])
        self.assertTrue(sell_row["previous_day_minute_required"])
        self.assertEqual(sell_row["market_data_consumer"], "both")
        self.assertEqual(row["period_trigger_baseline_json"]["baseline_version"], "N2-R4-period-trigger-baseline-v1")
        self.assertEqual(row["period_trigger_baseline_json"], pool_report["pool_preview"]["stock"]["pool_rows"][0]["period_trigger_baseline_json"])
        self.assertEqual(
            row["period_trigger_baseline_json"]["condition_projection_context"],
            condition_projection_context(),
        )
        self.assertEqual(
            row["period_trigger_baseline_json"]["period_escalation_context"]["generation_mode"],
            "directional_incremental_v1",
        )
        self.assertEqual(scope["previous_day_minute_date_mismatch_count"], 0)

    def test_index_and_board_scope_are_built_from_condition_pool_rows(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=False,
        )
        pool_report = {
            "run_id": "condition_pool_20260522_to_20260525_dry_run",
            "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 1},
            "pool_preview": {
                "index": {
                    "pool_rows": [
                        {
                            "condition_pool_ref": "dry_run:index:condition_pool:1:index:SH:000905:BUY_HINT",
                            "index_identity_key": "index:SH:000905",
                            "code": "000905",
                            "exchange": "SH",
                            "name": "中证500",
                            "lane": "index_alert",
                            "direction": "buy",
                            "condition_key": "BUY_HINT",
                            "allowed_signal_types": ["BUY_HINT"],
                            "active_target": True,
                            "period_trigger_baseline_json": period_trigger_baseline_json(),
                            "source_version": "index_daily_20260522_v1",
                        },
                        {
                            "condition_pool_ref": "dry_run:index:condition_pool:2:index:SH:000001:BUY:M",
                            "index_identity_key": "index:SH:000001",
                            "code": "000001",
                            "exchange": "SH",
                            "name": "上证指数",
                            "lane": "index_alert",
                            "direction": "buy",
                            "condition_key": "BUY:M",
                            "allowed_signal_types": ["BUY"],
                            "active_target": True,
                            "period_trigger_baseline_json": period_trigger_baseline_json(),
                            "source_version": "index_daily_20260522_v1",
                        }
                    ]
                },
                "board": {
                    "pool_rows": [
                        {
                            "condition_pool_ref": "dry_run:board:condition_pool:1:board:TDX:881001:SELL_HINT",
                            "board_identity_key": "board:TDX:881001",
                            "board_code": "881001",
                            "board_name": "行业A",
                            "board_type": "tdx_industry",
                            "lane": "board_alert",
                            "direction": "sell",
                            "condition_key": "SELL_HINT",
                            "allowed_signal_types": ["SELL_HINT"],
                            "active_target": True,
                            "period_trigger_baseline_json": period_trigger_baseline_json(),
                            "source_version": "board_daily_20260522_v1",
                        },
                        {
                            "condition_pool_ref": "dry_run:board:condition_pool:2:board:TDX:881002:SELL:W,D",
                            "board_identity_key": "board:TDX:881002",
                            "board_code": "881002",
                            "board_name": "行业B",
                            "board_type": "tdx_industry",
                            "lane": "board_alert",
                            "direction": "sell",
                            "condition_key": "SELL:W,D",
                            "allowed_signal_types": ["SELL"],
                            "active_target": True,
                            "period_trigger_baseline_json": period_trigger_baseline_json(),
                            "source_version": "board_daily_20260522_v1",
                        }
                    ]
                },
            },
        }

        index_scope = build_index_condition_scope_from_pool_report(pool_report, dates)
        board_scope = build_board_condition_scope_from_pool_report(pool_report, dates)

        self.assertEqual(index_scope["scope_source"], "condition_pool")
        self.assertEqual(index_scope["object_count"], 2)
        self.assertEqual(index_scope["scope_row_count"], 2)
        self.assertEqual(index_scope["scope_rows"][0]["source_condition_pool_ref"], "dry_run:index:condition_pool:1:index:SH:000905:BUY_HINT")
        self.assertEqual(index_scope["scope_rows"][0]["condition_key"], "BUY_HINT")
        self.assertTrue(index_scope["scope_rows"][0]["minute_required"])
        self.assertTrue(index_scope["scope_rows"][0]["previous_day_minute_required"])
        self.assertEqual(index_scope["scope_rows"][0]["market_data_consumer"], "both")
        self.assertEqual(index_scope["scope_rows"][0]["period_trigger_baseline_json"]["baseline_version"], "N2-R4-period-trigger-baseline-v1")
        self.assertEqual(
            index_scope["scope_rows"][0]["period_trigger_baseline_json"]["condition_projection_context"],
            condition_projection_context(),
        )
        self.assertEqual(index_scope["scope_rows"][1]["condition_key"], "BUY:M")
        self.assertTrue(index_scope["scope_rows"][1]["minute_required"])
        self.assertTrue(index_scope["scope_rows"][1]["previous_day_minute_required"])
        self.assertEqual(index_scope["scope_rows"][1]["previous_day_minute_date"], "20260522")
        self.assertEqual(index_scope["scope_rows"][1]["market_data_consumer"], "both")
        self.assertEqual(index_scope["scope_source_counts"], {"condition_pool": 2})
        self.assertEqual(board_scope["scope_source"], "condition_pool")
        self.assertEqual(board_scope["object_count"], 2)
        self.assertEqual(board_scope["scope_row_count"], 2)
        self.assertEqual(board_scope["scope_rows"][0]["source_condition_pool_ref"], "dry_run:board:condition_pool:1:board:TDX:881001:SELL_HINT")
        self.assertEqual(board_scope["scope_rows"][0]["condition_key"], "SELL_HINT")
        self.assertTrue(board_scope["scope_rows"][0]["minute_required"])
        self.assertTrue(board_scope["scope_rows"][0]["previous_day_minute_required"])
        self.assertEqual(board_scope["scope_rows"][0]["market_data_consumer"], "both")
        self.assertEqual(board_scope["scope_rows"][0]["period_trigger_baseline_json"]["baseline_version"], "N2-R4-period-trigger-baseline-v1")
        self.assertEqual(
            board_scope["scope_rows"][0]["period_trigger_baseline_json"]["condition_projection_context"],
            condition_projection_context(),
        )
        self.assertEqual(board_scope["scope_rows"][1]["condition_key"], "SELL:W,D")
        self.assertTrue(board_scope["scope_rows"][1]["minute_required"])
        self.assertTrue(board_scope["scope_rows"][1]["previous_day_minute_required"])
        self.assertEqual(board_scope["scope_rows"][1]["previous_day_minute_date"], "20260522")
        self.assertEqual(board_scope["scope_rows"][1]["market_data_consumer"], "both")
        self.assertEqual(board_scope["scope_source_counts"], {"condition_pool": 2})

    def test_scope_quality_uses_condition_pool_policy_for_all_index_and_board_types(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=True,
        )
        baseline = period_trigger_baseline_json()
        condition_pool_report = {
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
            "pool_preview": {
                "index": {
                    "condition_pool_selection_policy": {"include_all_identities": True},
                },
                "board": {
                    "condition_pool_selection_policy": {"board_types": ["tdx_industry", "tdx_concept"]},
                },
            },
        }
        index_scope = {
            "condition_pool_exists": True,
            "condition_pool_source": "condition_pool_dry_run",
            "scope_rows": [
                {
                    "identity_key": "index:SH:000009",
                    "index_identity_key": "index:SH:000009",
                    "code": "000009",
                    "allowed_signal_types": ["BUY"],
                    "period_trigger_baseline_json": baseline,
                    "condition_key": "BUY:D",
                }
            ],
        }
        board_scope = {
            "condition_pool_exists": True,
            "condition_pool_source": "condition_pool_dry_run",
            "scope_rows": [
                {
                    "identity_key": "board:TDX:881001",
                    "board_identity_key": "board:TDX:881001",
                    "board_code": "881001",
                    "board_type": "tdx_concept",
                    "allowed_signal_types": ["SELL"],
                    "period_trigger_baseline_json": baseline,
                    "condition_key": "SELL:D",
                }
            ],
        }
        stock_scope = {
            "condition_pool_exists": True,
            "condition_pool_source": "condition_pool_dry_run",
            "scope_rows": [],
        }

        by_code = {
            item["gate_code"]: item
            for item in build_scope_quality_items(
                ready_check={"passed": True},
                date_context=dates,
                condition_pool_report=condition_pool_report,
                index_scope=index_scope,
                board_scope=board_scope,
                stock_scope=stock_scope,
            )
        }

        self.assertEqual(by_code["index_scope_default_universe"]["status"], "passed")
        self.assertEqual(by_code["index_scope_default_universe"]["expected_value"], "all_index_identities")
        self.assertEqual(by_code["board_scope_default_universe"]["status"], "passed")
        self.assertIn("tdx_concept", by_code["board_scope_default_universe"]["expected_value"])

    def test_scope_row_diagnostics_counts_previous_day_minute_mismatch(self) -> None:
        diagnostics = scope_row_diagnostics(
            [
                {
                    "scope_source": "condition_pool",
                    "market_data_consumer": "both",
                    "allowed_signal_types": ["BUY_HINT"],
                    "previous_day_minute_required": True,
                    "previous_day_minute_date": "20260521",
                }
            ],
            "20260522",
        )

        self.assertEqual(diagnostics["scope_source_counts"], {"condition_pool": 1})
        self.assertEqual(diagnostics["previous_day_minute_required_count"], 1)
        self.assertEqual(diagnostics["previous_day_minute_date_mismatch_count"], 1)


if __name__ == "__main__":
    unittest.main()
