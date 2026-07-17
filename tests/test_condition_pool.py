import unittest

from ashare_v3.condition.pool import (
    BUY_POOL_SIGNAL_TYPES,
    DEFAULT_INDEX_POOL_CODES,
    DEFAULT_INDEX_POOL_IDENTITIES,
    DEFAULT_STOCK_MIN_TOTAL_MV_WAN,
    HINT_CONDITION_KEYS,
    SELL_POOL_SIGNAL_TYPES,
    apply_default_condition_pool_policy,
    build_condition_pool_preview_from_basis_report,
    build_condition_pool_quality_items,
    build_pool_rows_for_basis,
    calendar_detail_from_basis_report,
    condition_group_for_key,
    condition_pool_policy_hash,
    count_allowed_signal_types,
    default_condition_pool_policy,
    default_condition_pool_policy_quality_items,
    missing_required_period_trigger_baseline_periods,
    normalize_periods,
    required_periods_for_condition_key,
)


def stock_basis_row() -> dict[str, object]:
    return {
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "stock_identity_key": "stock:SH:600000",
        "asset_kind": "stock",
        "code": "600000",
        "exchange": "SH",
        "ts_code": "600000.SH",
        "display_code": "600000",
        "name": "浦发银行",
        "is_st": False,
        "stock_status": "active",
        "official_daily_proof": True,
        "lane": "stock_alert",
        "monitor_type": "source_universe_preview",
        "total_mv": "1000000.01",
        "circ_mv": "800000.00",
        "pe_core": "12.3",
        "score": "80",
        "financial_asof_date": "20260522",
        "financial_quality_status": "passed",
        "period_trigger_baseline_json": period_trigger_baseline_json(),
        "buy_necessary_base": True,
        "buy_necessary_periods": ["D", "Y", "M"],
        "sell_necessary_base": True,
        "sell_necessary_periods": ["W"],
        "buy_full_necessary_base": True,
        "sell_full_necessary_base": True,
        "oversold_hint_necessary_base": True,
        "overbought_hint_necessary_base": True,
        "source_version": "stock_daily_20260522_v1",
        "quality_status": "passed",
        "missing_fields_json": {},
        "raw_json": {},
    }


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
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "status": "ready",
        "fields": {"name": "浦发银行", "close": "11"},
        "nullable_fields": [],
        "not_ready_reasons": [],
        "context_hash": "condition-projection-context-hash",
    }


def incomplete_period_trigger_baseline_json(*, missing_periods: tuple[str, ...]) -> dict[str, object]:
    baseline = period_trigger_baseline_json()
    periods = baseline["periods"]
    assert isinstance(periods, dict)
    for period in missing_periods:
        entry = periods[period]
        assert isinstance(entry, dict)
        entry["baseline_ready"] = False
        entry["baseline_missing_fields"] = ["previous_entity_high", "previous_entity_low"]
        entry["previous_entity_high"] = None
        entry["previous_entity_low"] = None
    return baseline


def index_basis_row(code: str = "000905") -> dict[str, object]:
    row = stock_basis_row()
    row.pop("stock_identity_key", None)
    row.pop("total_mv", None)
    row.pop("circ_mv", None)
    exchange = "SH" if code.startswith("0") else "SZ"
    row.update(
        {
            "index_identity_key": f"index:{exchange}:{code}",
            "asset_kind": "index",
            "code": code,
            "exchange": exchange,
            "name": code,
            "lane": "market_alert",
        }
    )
    return row


def board_basis_row(board_code: str = "881001") -> dict[str, object]:
    row = stock_basis_row()
    row.pop("stock_identity_key", None)
    row.pop("code", None)
    row.pop("exchange", None)
    row.pop("total_mv", None)
    row.pop("circ_mv", None)
    row.update(
        {
            "board_identity_key": f"board:TDX:{board_code}",
            "asset_kind": "board",
            "board_code": board_code,
            "board_name": board_code,
            "board_type": "tdx_industry",
            "lane": "market_alert",
        }
    )
    return row


class ConditionPoolTest(unittest.TestCase):
    def test_build_pool_rows_covers_ordinary_full_and_hint(self) -> None:
        basis = stock_basis_row()
        rows = build_pool_rows_for_basis("stock", basis)
        by_key = {row["condition_key"]: row for row in rows}

        self.assertEqual(set(by_key), {"BUY:Y,M,D", "SELL:W", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"})
        self.assertEqual(by_key["BUY:Y,M,D"]["direction"], "buy")
        self.assertEqual(by_key["SELL:W"]["direction"], "sell")
        self.assertEqual(by_key["BUY:FULL"]["condition_periods"], ["D"])
        self.assertEqual(by_key["SELL:FULL"]["condition_periods"], ["D"])
        self.assertEqual(by_key["BUY_HINT"]["condition_periods"], [])
        self.assertEqual(by_key["SELL_HINT"]["condition_periods"], [])
        self.assertEqual(by_key["BUY:Y,M,D"]["total_mv"], "1000000.01")
        self.assertIsNotNone(by_key["BUY:Y,M,D"]["condition_pool_ref"])
        self.assertEqual(by_key["BUY:Y,M,D"]["period_trigger_baseline_json"]["baseline_version"], "N2-R4-period-trigger-baseline-v1")
        self.assertEqual(by_key["BUY:Y,M,D"]["period_trigger_baseline_json"], basis["period_trigger_baseline_json"])
        for row in by_key.values():
            self.assertEqual(
                row["period_trigger_baseline_json"]["condition_projection_context"],
                condition_projection_context(),
            )
        self.assertEqual(
            by_key["BUY:Y,M,D"]["period_trigger_baseline_json"]["period_escalation_context"]["generation_mode"],
            "directional_incremental_v1",
        )

    def test_allowed_signal_types_use_n2_canonical_condition_semantics(self) -> None:
        rows = build_pool_rows_for_basis("stock", stock_basis_row())
        by_key = {row["condition_key"]: row for row in rows}

        self.assertEqual(by_key["BUY:Y,M,D"]["allowed_signal_types"], list(BUY_POOL_SIGNAL_TYPES))
        self.assertEqual(by_key["SELL:W"]["allowed_signal_types"], list(SELL_POOL_SIGNAL_TYPES))
        self.assertEqual(by_key["BUY:FULL"]["allowed_signal_types"], ["BUY:FULL"])
        self.assertEqual(by_key["SELL:FULL"]["allowed_signal_types"], ["SELL:FULL"])
        self.assertEqual(by_key["BUY_HINT"]["allowed_signal_types"], ["BUY_HINT"])
        self.assertEqual(by_key["SELL_HINT"]["allowed_signal_types"], ["SELL_HINT"])
        all_signal_types = {signal_type for row in rows for signal_type in row["allowed_signal_types"]}
        self.assertFalse({"B_BUY_30M_VOL", "S_SELL_30M_SHRINK"} & all_signal_types)
        self.assertTrue(by_key["BUY_HINT"]["is_hint_scope"])
        self.assertTrue(by_key["SELL_HINT"]["is_hint_scope"])
        self.assertEqual(HINT_CONDITION_KEYS, ("BUY_HINT", "SELL_HINT"))

    def test_hint_uses_buy_sell_direction_not_hint_direction(self) -> None:
        rows = build_pool_rows_for_basis("stock", stock_basis_row())
        by_key = {row["condition_key"]: row for row in rows}

        self.assertEqual(by_key["BUY_HINT"]["direction"], "buy")
        self.assertEqual(by_key["SELL_HINT"]["direction"], "sell")

    def test_condition_group_and_signal_counts(self) -> None:
        rows = build_pool_rows_for_basis("stock", stock_basis_row())

        self.assertEqual(condition_group_for_key("BUY:Y,M,D"), "ordinary_buy")
        self.assertEqual(condition_group_for_key("SELL:W"), "ordinary_sell")
        self.assertEqual(condition_group_for_key("BUY:FULL"), "full")
        self.assertEqual(condition_group_for_key("BUY_HINT"), "hint")
        self.assertEqual(count_allowed_signal_types(rows)["BUY"], 1)
        self.assertEqual(count_allowed_signal_types(rows)["BUY:FULL"], 1)
        self.assertEqual(count_allowed_signal_types(rows)["BUY_HINT"], 1)

    def test_normalize_periods_uses_canonical_period_order(self) -> None:
        self.assertEqual(normalize_periods(["D", "Y", "M", "BAD"]), ["Y", "M", "D"])
        self.assertEqual(normalize_periods("W,Q"), ["Q", "W"])

    def test_required_periods_for_condition_key(self) -> None:
        self.assertEqual(required_periods_for_condition_key("BUY:Y,M,D"), ["Y", "M", "D"])
        self.assertEqual(required_periods_for_condition_key("SELL:W"), ["W"])
        self.assertEqual(required_periods_for_condition_key("BUY:FULL"), ["D"])
        self.assertEqual(required_periods_for_condition_key("SELL:FULL"), ["D"])
        self.assertEqual(required_periods_for_condition_key("BUY_HINT"), [])
        self.assertEqual(required_periods_for_condition_key("SELL_HINT"), [])

    def test_default_pool_policy_excludes_missing_required_period_baseline(self) -> None:
        rows = build_pool_rows_for_basis(
            "stock",
            {
                **stock_basis_row(),
                "period_trigger_baseline_json": incomplete_period_trigger_baseline_json(missing_periods=("Y",)),
            },
        )

        result = apply_default_condition_pool_policy("stock", rows)
        selected_keys = {row["condition_key"] for row in result["selected_rows"]}

        self.assertEqual(result["excluded_reason_counts"], {"missing_period_trigger_baseline": 1})
        self.assertNotIn("BUY:Y,M,D", selected_keys)
        self.assertIn("SELL:W", selected_keys)
        self.assertIn("BUY:FULL", selected_keys)
        self.assertIn("SELL:FULL", selected_keys)
        self.assertIn("BUY_HINT", selected_keys)
        self.assertIn("SELL_HINT", selected_keys)
        excluded_row = result["excluded_samples"][0]["row"]
        self.assertEqual(excluded_row["missing_period_trigger_baseline_periods"], ["Y"])

    def test_hint_condition_does_not_require_period_trigger_baseline(self) -> None:
        rows = build_pool_rows_for_basis(
            "stock",
            {
                **stock_basis_row(),
                "buy_necessary_base": False,
                "sell_necessary_base": False,
                "buy_full_necessary_base": False,
                "sell_full_necessary_base": False,
                "period_trigger_baseline_json": incomplete_period_trigger_baseline_json(missing_periods=("Y", "Q", "M", "W", "D")),
            },
        )

        result = apply_default_condition_pool_policy("stock", rows)

        self.assertEqual({row["condition_key"] for row in result["selected_rows"]}, {"BUY_HINT", "SELL_HINT"})
        self.assertEqual(result["excluded_reason_counts"], {})
        self.assertEqual(missing_required_period_trigger_baseline_periods(result["selected_rows"][0]), [])

    def test_pool_preview_from_basis_report_keeps_asset_families_split(self) -> None:
        basis_report = {
            "basis_preview": {
                "stock": {"sample_basis_rows": [stock_basis_row()]},
                "index": {"sample_basis_rows": []},
                "board": {"sample_basis_rows": []},
            }
        }

        preview = build_condition_pool_preview_from_basis_report(basis_report)

        self.assertEqual(preview["stock"]["pool_row_count"], 6)
        self.assertEqual(preview["index"]["pool_row_count"], 0)
        self.assertEqual(preview["board"]["pool_row_count"], 0)
        self.assertEqual(preview["stock"]["condition_group_counts"]["hint"], 2)
        self.assertEqual(preview["stock"]["policy_selected_count"], 6)
        self.assertIn("condition_pool_selection_policy_hash", preview["stock"])
        self.assertEqual(preview["stock"]["pool_rows"][0]["policy_name"], "default_condition_pool_policy")
        self.assertIn("market_value_passed", preview["stock"]["pool_rows"][0]["selected_reason"])

    def test_default_pool_policy_filters_index_board_and_stock_universe(self) -> None:
        low_mv_stock = {**stock_basis_row(), "stock_identity_key": "stock:SH:600001", "code": "600001", "total_mv": "999999.99"}
        basis_report = {
            "basis_preview": {
                "stock": {"sample_basis_rows": [stock_basis_row(), low_mv_stock]},
                "index": {"sample_basis_rows": [index_basis_row("000905"), index_basis_row("000009")]},
                "board": {
                    "sample_basis_rows": [
                        {**board_basis_row("880001"), "board_type": "tdx_industry"},
                        {**board_basis_row("881999"), "board_type": "tdx_region"},
                    ]
                },
            }
        }

        preview = build_condition_pool_preview_from_basis_report(basis_report)

        self.assertEqual(str(DEFAULT_STOCK_MIN_TOTAL_MV_WAN), "1000000")
        self.assertIn("000905", DEFAULT_INDEX_POOL_CODES)
        self.assertIn("index:SH:000905", DEFAULT_INDEX_POOL_IDENTITIES)
        self.assertEqual(preview["stock"]["candidate_pool_row_count"], 12)
        self.assertEqual(preview["stock"]["pool_row_count"], 6)
        self.assertEqual(preview["stock"]["policy_excluded_reason_counts"], {"min_total_mv_wan": 6})
        self.assertEqual(preview["index"]["candidate_pool_row_count"], 12)
        self.assertEqual(preview["index"]["pool_row_count"], 6)
        self.assertEqual(preview["index"]["policy_excluded_reason_counts"], {"index_identity_not_in_default_universe": 6})
        self.assertEqual(preview["board"]["candidate_pool_row_count"], 12)
        self.assertEqual(preview["board"]["pool_row_count"], 6)
        self.assertEqual(preview["board"]["policy_excluded_reason_counts"], {"board_type": 6})

    def test_custom_pool_policy_can_include_concept_and_region_board_types(self) -> None:
        basis_report = {
            "basis_preview": {
                "stock": {"sample_basis_rows": []},
                "index": {"sample_basis_rows": []},
                "board": {
                    "sample_basis_rows": [
                        {**board_basis_row("880001"), "board_type": "tdx_industry"},
                        {**board_basis_row("881001"), "board_type": "tdx_concept"},
                        {**board_basis_row("882001"), "board_type": "tdx_region"},
                    ]
                },
            }
        }

        preview = build_condition_pool_preview_from_basis_report(
            basis_report,
            condition_pool_policy={"board": {"board_types": ["tdx_industry", "tdx_concept"]}},
        )

        self.assertEqual(preview["board"]["candidate_pool_row_count"], 18)
        self.assertEqual(preview["board"]["pool_row_count"], 12)
        self.assertEqual(preview["board"]["policy_excluded_reason_counts"], {"board_type": 6})
        selected_board_types = {row["board_type"] for row in preview["board"]["pool_rows"]}
        self.assertEqual(selected_board_types, {"tdx_industry", "tdx_concept"})
        self.assertIn("board_type_tdx_concept", preview["board"]["policy_selected_reason_counts"])
        by_code = {item["gate_code"]: item for item in default_condition_pool_policy_quality_items(preview)}
        self.assertEqual(by_code["board_condition_pool_default_universe"]["status"], "passed")
        self.assertIn("tdx_concept", by_code["board_condition_pool_default_universe"]["expected_value"])

    def test_default_pool_policy_filters_stock_risk_and_data_completeness(self) -> None:
        st_stock = {**stock_basis_row(), "stock_identity_key": "stock:SH:600010", "code": "600010", "is_st": True}
        no_daily = {**stock_basis_row(), "stock_identity_key": "stock:SH:600011", "code": "600011", "official_daily_proof": False}
        no_financial = {
            **stock_basis_row(),
            "stock_identity_key": "stock:SH:600012",
            "code": "600012",
            "financial_asof_date": None,
            "pe_core": None,
            "score": None,
        }
        wrong_lane = {**stock_basis_row(), "stock_identity_key": "stock:SH:600013", "code": "600013", "lane": "market_alert"}
        rows = [
            pool_row
            for basis in (st_stock, no_daily, no_financial, wrong_lane)
            for pool_row in build_pool_rows_for_basis("stock", basis)
        ]

        result = apply_default_condition_pool_policy("stock", rows)

        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["excluded_reason_counts"]["st_or_risk_stock"], 6)
        self.assertEqual(result["excluded_reason_counts"]["official_daily_missing"], 6)
        self.assertEqual(result["excluded_reason_counts"]["financial_snapshot_missing"], 6)
        self.assertEqual(result["excluded_reason_counts"]["financial_key_fields_missing"], 6)
        self.assertEqual(result["excluded_reason_counts"]["lane"], 6)
        self.assertEqual(result["excluded_samples"][0]["policy_name"], "default_condition_pool_policy")
        self.assertIn("policy_hash", result["excluded_samples"][0])

    def test_condition_pool_policy_hash_is_stable_for_reordered_dicts(self) -> None:
        left = default_condition_pool_policy("stock")
        right = {key: left[key] for key in reversed(left)}

        self.assertEqual(condition_pool_policy_hash(left), condition_pool_policy_hash(right))

    def test_apply_default_condition_pool_policy_reports_missing_total_mv(self) -> None:
        rows = build_pool_rows_for_basis("stock", {**stock_basis_row(), "total_mv": None})

        result = apply_default_condition_pool_policy("stock", rows)

        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["excluded_reason_counts"], {"missing_total_mv": 6})

    def test_calendar_detail_reports_ingestion_layer_repair_owner(self) -> None:
        detail = calendar_detail_from_basis_report(
            {
                "for_trade_date": "20260525",
                "prev_trade_date": "20260522",
                "for_trade_calendar_row_exists": False,
            }
        )

        self.assertFalse(detail["row_exists"])
        self.assertEqual(detail["repair_owner"], "ingestion_layer")
        self.assertIn("条件层不得硬造交易日", detail["repair_suggestion"])

    def test_condition_pool_inherits_basis_p0_blocker(self) -> None:
        items = build_condition_pool_quality_items(
            basis_report={
                "source_ready_passed": True,
                "source_trade_date": "20260522",
                "for_trade_date": "20260525",
                "prev_trade_date": "20260522",
                "for_trade_calendar_row_exists": True,
                "quality": {"p0_count": 1},
            },
            pool_preview={"stock": {"pool_rows": []}, "index": {"pool_rows": []}, "board": {"pool_rows": []}},
        )

        by_code = {item["gate_code"]: item for item in items}
        self.assertEqual(by_code["condition_basis_p0_zero"]["status"], "failed")
        self.assertEqual(by_code["condition_basis_p0_zero"]["actual_value"], "1")


if __name__ == "__main__":
    unittest.main()
