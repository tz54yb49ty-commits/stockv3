import json
import unittest

from ashare_v3.trigger.context_preflight import (
    build_context_materialization_run_id,
    build_trigger_context_preflight_plan,
    normalize_context_row,
)
from scripts.check_n4_contract import run_check


class TriggerContextPreflightTest(unittest.TestCase):
    def test_hint_condition_rows_enter_n4_trigger_candidates(self) -> None:
        report = build_trigger_context_preflight_plan(
            active_run=sample_active_run(),
            context_rows_by_asset={
                "stock": [
                    sample_context_row(
                        asset_kind="stock",
                        identity_key="stock:SH:600000",
                        source_scope_id=1,
                        source_pool_id=101,
                        source_basis_id=1001,
                        direction="buy",
                        condition_key="BUY_HINT",
                        allowed_signal_types=["BUY_HINT"],
                    ),
                    sample_context_row(
                        asset_kind="stock",
                        identity_key="stock:SH:600000",
                        source_scope_id=2,
                        source_pool_id=102,
                        source_basis_id=1001,
                        direction="sell",
                        condition_key="SELL_HINT",
                        allowed_signal_types=["SELL_HINT"],
                    ),
                ],
                "index": [
                    sample_context_row(
                        asset_kind="index",
                        identity_key="index:SH:000905",
                        source_scope_id=11,
                        source_pool_id=201,
                        source_basis_id=2001,
                        direction="buy",
                        condition_key="BUY:Y,Q,M,W,D",
                        allowed_signal_types=["BUY"],
                    )
                ],
                "board": [],
            },
            include_rows=True,
        )

        self.assertTrue(report["passed"], report["quality"]["items"])
        self.assertEqual(report["candidate_context_row_count"], 3)
        self.assertEqual(report["buy_hint_row_count"], 1)
        self.assertEqual(report["sell_hint_row_count"], 1)
        self.assertEqual(report["hint_condition_row_count"], 2)
        self.assertEqual(report["direction_distribution"], {"buy": 2, "sell": 1})
        self.assertEqual(report["trigger_candidate_count_by_signal_type"]["BUY_HINT"], 1)
        self.assertEqual(report["trigger_candidate_count_by_signal_type"]["SELL_HINT"], 1)
        self.assertEqual(report["period_trigger_baseline_json_missing"], 0)
        self.assertEqual(report["required_period_not_ready_rows"], 0)

        rows = report["trigger_context_snapshot_dry_run_plan"]["rows"]
        hint_keys = {row["condition_key"] for row in rows if row["condition_key"].endswith("HINT")}
        self.assertEqual(hint_keys, {"BUY_HINT", "SELL_HINT"})

    def test_local_context_preflight_has_no_external_runtime_path_or_side_effects(self) -> None:
        report = build_trigger_context_preflight_plan(
            active_run=sample_active_run(),
            context_rows_by_asset={
                "stock": [
                    sample_context_row(
                        asset_kind="stock",
                        identity_key="stock:SH:600000",
                        source_scope_id=1,
                        source_pool_id=101,
                        source_basis_id=1001,
                        direction="buy",
                        condition_key="BUY_HINT",
                        allowed_signal_types=["BUY_HINT"],
                    )
                ],
                "index": [],
                "board": [],
            },
            include_rows=True,
        )

        self.assertTrue(report["side_effects"]["read_only_database_checks"])
        self.assertFalse(report["side_effects"]["writes_performed"])
        self.assertFalse(report["side_effects"]["market_data_pulled"])
        self.assertFalse(report["side_effects"]["n3_event_consumed"])
        self.assertFalse(report["side_effects"]["downstream_layers_touched"])
        self.assertFalse(report["side_effects"]["external_n2_runtime_path_accessed"])
        self.assertNotIn("/Volumes/MacRaid", json.dumps(report, ensure_ascii=False))

    def test_n4_static_contract_check_passes(self) -> None:
        result = run_check()

        self.assertTrue(result["passed"], result["findings"])

    def test_context_preflight_blocks_scope_not_from_condition_pool(self) -> None:
        bad = sample_context_row(
            asset_kind="index",
            identity_key="index:SH:000905",
            source_scope_id=11,
            source_pool_id=201,
            source_basis_id=2001,
            direction="buy",
            condition_key="BUY_HINT",
            allowed_signal_types=["BUY_HINT"],
        )
        bad["scope_source"] = "fixed_index_scope"
        report = build_trigger_context_preflight_plan(
            active_run=sample_active_run(),
            context_rows_by_asset={"stock": [], "index": [bad], "board": []},
            include_rows=True,
        )

        self.assertTrue(report["blocked"])

    def test_context_preflight_blocks_legacy_previous_fields_as_trigger_baseline(self) -> None:
        legacy = sample_context_row(
            asset_kind="stock",
            identity_key="stock:SZ:002399",
            source_scope_id=41,
            source_pool_id=401,
            source_basis_id=4001,
            direction="buy",
            condition_key="BUY:D",
            allowed_signal_types=["BUY"],
        )
        legacy["period_trigger_baseline_json"] = legacy_period_trigger_baseline_json()

        report = build_trigger_context_preflight_plan(
            active_run=sample_active_run(),
            context_rows_by_asset={"stock": [legacy], "index": [], "board": []},
            include_rows=True,
        )

        self.assertTrue(report["blocked"])
        failed_codes = {
            item["gate_code"]
            for item in report["quality"]["items"]
            if item["status"] == "failed"
        }
        self.assertIn("trigger_baseline_semantic_fields_present", failed_codes)
        self.assertIn("trigger_baseline_source_trade_date_match", failed_codes)

    def test_context_preflight_accepts_trigger_baseline_fields_and_keeps_legacy_trace(self) -> None:
        repaired = sample_context_row(
            asset_kind="stock",
            identity_key="stock:SZ:002399",
            source_scope_id=41,
            source_pool_id=401,
            source_basis_id=4001,
            direction="buy",
            condition_key="BUY:D",
            allowed_signal_types=["BUY"],
        )
        baseline = period_trigger_baseline_json()
        for entry in baseline["periods"].values():
            entry.update(
                {
                    "classification_previous_entity_high": entry["previous_entity_high"],
                    "classification_previous_entity_low": entry["previous_entity_low"],
                    "classification_previous_amount_baseline": entry["previous_amount"],
                    "classification_period_key_previous": "20260521",
                    "trigger_previous_open": entry["previous_open"],
                    "trigger_previous_close": entry["previous_close"],
                    "trigger_previous_entity_high": "12",
                    "trigger_previous_entity_low": "10",
                    "current_seed_entity_high": "11",
                    "current_seed_entity_low": "10",
                    "trigger_previous_amount_baseline": entry["current_amount_seed"],
                    "baseline_source_trade_date": "20260522",
                }
            )
        repaired["period_trigger_baseline_json"] = baseline

        report = build_trigger_context_preflight_plan(
            active_run=sample_active_run(),
            context_rows_by_asset={"stock": [repaired], "index": [], "board": []},
            include_rows=True,
        )

        self.assertTrue(report["passed"], report["quality"]["items"])
        self.assertEqual(report["trigger_baseline_semantic_missing"], 0)

    def test_context_preflight_blocks_current_seed_as_formal_trigger_baseline(self) -> None:
        bad = sample_context_row(
            asset_kind="board",
            identity_key="board:TDX:881078",
            source_scope_id=41,
            source_pool_id=401,
            source_basis_id=4001,
            direction="sell",
            condition_key="SELL:W",
            allowed_signal_types=["SELL"],
        )
        baseline = period_trigger_baseline_json()
        baseline["periods"]["W"].update(
            {
                "previous_entity_high": "696.8",
                "previous_entity_low": "632.78",
                "trigger_previous_entity_high": "712.3",
                "trigger_previous_entity_low": "706.84",
                "current_seed_entity_high": "712.3",
                "current_seed_entity_low": "706.84",
            }
        )
        bad["period_trigger_baseline_json"] = baseline

        report = build_trigger_context_preflight_plan(
            active_run=sample_active_run(),
            context_rows_by_asset={"stock": [], "index": [], "board": [bad]},
            include_rows=True,
        )

        self.assertTrue(report["blocked"])
        failed_codes = {
            item["gate_code"]
            for item in report["quality"]["items"]
            if item["status"] == "failed"
        }
        self.assertIn("trigger_baseline_not_from_current_seed", failed_codes)

    def test_context_preflight_checks_only_required_condition_periods(self) -> None:
        row = sample_context_row(
            asset_kind="stock",
            identity_key="stock:SH:603407",
            source_scope_id=41,
            source_pool_id=401,
            source_basis_id=4001,
            direction="buy",
            condition_key="BUY:M",
            allowed_signal_types=["BUY"],
        )
        baseline = period_trigger_baseline_json()
        for period in ("Y", "Q"):
            baseline["periods"][period].pop("trigger_previous_entity_high", None)
            baseline["periods"][period].pop("trigger_previous_entity_low", None)
        row["period_trigger_baseline_json"] = baseline

        report = build_trigger_context_preflight_plan(
            active_run=sample_active_run(),
            context_rows_by_asset={"stock": [row], "index": [], "board": []},
            include_rows=True,
        )

        self.assertTrue(report["passed"], report["quality"]["items"])
        self.assertEqual(report["trigger_baseline_semantic_missing"], 0)

    def test_context_preflight_accepts_passed_active_condition_run(self) -> None:
        active = sample_active_run()
        active["status"] = "passed_active"
        report = build_trigger_context_preflight_plan(
            active_run=active,
            context_rows_by_asset={
                "stock": [
                    sample_context_row(
                        asset_kind="stock",
                        identity_key="stock:SH:600000",
                        source_scope_id=1,
                        source_pool_id=101,
                        source_basis_id=1001,
                        direction="buy",
                        condition_key="BUY_HINT",
                        allowed_signal_types=["BUY_HINT"],
                    )
                ],
                "index": [],
                "board": [],
            },
            include_rows=True,
        )

        self.assertTrue(report["passed"], report["quality"]["items"])

    def test_context_materialization_run_id_uses_atomic_rule_suffix(self) -> None:
        run_id = build_context_materialization_run_id(
            {
                "for_trade_date": "20260626",
                "run_id": "condition_layer_20260625_source_20260625_for_20260626_v1",
            }
        )

        self.assertEqual(
            run_id,
            "trigger_context_snapshot_20260626_condition_layer_20260625_source_20260625_for_20260626_v1__atomic_rule_v1",
        )

    def test_context_row_prefers_materialized_enrichment_baseline_over_legacy_scope(self) -> None:
        row = sample_context_row(
            asset_kind="stock",
            identity_key="stock:SZ:002399",
            source_scope_id=41,
            source_pool_id=401,
            source_basis_id=4001,
            direction="buy",
            condition_key="BUY:Y,Q,M,W,D",
            allowed_signal_types=["BUY"],
        )
        row["period_trigger_baseline_json"] = legacy_period_trigger_baseline_json()
        enriched = period_trigger_baseline_json()
        for entry in enriched["periods"].values():
            entry.update(
                {
                    "trigger_previous_open": "9.66",
                    "trigger_previous_close": "9.45",
                    "previous_entity_high": "9.79",
                    "previous_entity_low": "9.67",
                    "trigger_previous_entity_high": "9.79",
                    "trigger_previous_entity_low": "9.67",
                    "current_seed_entity_high": "9.66",
                    "current_seed_entity_low": "9.45",
                    "trigger_previous_amount_baseline": "43678.117",
                    "baseline_source_trade_date": "20260522",
                }
            )
        row.update(
            {
                "context_enrichment_materialization_run_id": "trigger_context_snapshot_20260525_condition_layer_test",
                "context_enrichment_hash": "enrichment_hash",
                "enrichment_period_trigger_baseline_json": enriched,
            }
        )

        normalized = normalize_context_row(row)
        period_d = normalized["period_trigger_baseline_json"]["periods"]["D"]

        self.assertEqual(period_d["trigger_previous_entity_high"], "9.79")
        self.assertEqual(period_d["trigger_previous_entity_low"], "9.67")
        self.assertEqual(period_d["trigger_previous_amount_baseline"], "43678.117")
        self.assertEqual(normalized["context_enrichment_materialization_run_id"], "trigger_context_snapshot_20260525_condition_layer_test")


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


def sample_context_row(
    *,
    asset_kind: str,
    identity_key: str,
    source_scope_id: int,
    source_pool_id: int,
    source_basis_id: int,
    direction: str,
    condition_key: str,
    allowed_signal_types: list[str],
) -> dict[str, object]:
    code = identity_key.split(":")[-1]
    return {
        "source_minute_target_scope_id": source_scope_id,
        "source_condition_pool_id": source_pool_id,
        "source_condition_basis_id": source_basis_id,
        "source_market_subscription_id": None,
        "source_scope_table": f"{asset_kind}_minute_target_scope",
        "source_pool_table": f"{asset_kind}_condition_pool",
        "source_basis_table": f"{asset_kind}_condition_basis",
        "source_condition_run_id": "condition_layer_20260522_to_20260525_test_execute",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "prev_trade_date": "20260522",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": "TDX" if asset_kind == "board" else identity_key.split(":")[1],
        "code": code,
        "display_code": code,
        "name": code,
        "lane": "stock_trade" if asset_kind == "stock" else "market_alert",
        "monitor_type": "stock_buy_monitor" if asset_kind == "stock" else "market_watch",
        "direction": direction,
        "condition_key": condition_key,
        "condition_periods": [],
        "allowed_signal_types": allowed_signal_types,
        "is_hint_scope": condition_key in {"BUY_HINT", "SELL_HINT"},
        "scope_source": "condition_pool",
        "scope_status": "planned",
        "active_target": True,
        "pool_quality_status": "passed",
        "basis_quality_status": "passed",
        "amount_quality_status": "passed",
        "period_trigger_baseline_json": period_trigger_baseline_json(),
        "daily_snapshot_required": True,
        "minute_required": condition_key in {"BUY_HINT", "SELL_HINT"},
        "previous_day_minute_required": condition_key in {"BUY_HINT", "SELL_HINT"},
        "previous_day_minute_date": "20260522",
        "previous_day_minute_quality_required": condition_key in {"BUY_HINT", "SELL_HINT"},
        "policy_hash": "policy_hash",
        "selected_reason": ["test"],
    }


def period_trigger_baseline_json() -> dict[str, object]:
    return {
        "baseline_version": "N2-R4-period-trigger-baseline-v1",
        "periods": {
            period: {
                "baseline_ready": True,
                "baseline_missing_fields": [],
                "current_open_seed": "10",
                "current_close_seed": "11",
                "current_amount_seed": "200",
                "current_avg_amount_seed": "200",
                "current_trade_days_seed": 1,
                "previous_open": "12",
                "previous_close": "10",
                "previous_entity_high": "12",
                "previous_entity_low": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "previous_amount_baseline": "100",
                "classification_previous_open": "12",
                "classification_previous_close": "10",
                "classification_previous_entity_high": "12",
                "classification_previous_entity_low": "10",
                "classification_previous_amount_baseline": "100",
                "classification_period_key_previous": "20260521",
                "trigger_previous_open": "12",
                "trigger_previous_close": "10",
                "trigger_previous_entity_high": "12",
                "trigger_previous_entity_low": "10",
                "current_seed_entity_high": "11",
                "current_seed_entity_low": "10",
                "trigger_previous_amount_baseline": "200",
                "baseline_source_trade_date": "20260522",
                "amount_metric": "amount" if period == "D" else "avg_amount",
                "period_key_previous": "20260521",
                "current_window_start": "20260501",
                "current_window_end": "20260522",
                "previous_window_start": "20260401",
                "previous_window_end": "20260430",
            }
            for period in ("Y", "Q", "M", "W", "D")
        },
    }


def legacy_period_trigger_baseline_json() -> dict[str, object]:
    baseline = period_trigger_baseline_json()
    for entry in baseline["periods"].values():
        for key in (
            "classification_previous_open",
            "classification_previous_close",
            "classification_previous_entity_high",
            "classification_previous_entity_low",
            "classification_previous_amount_baseline",
            "classification_period_key_previous",
            "trigger_previous_open",
            "trigger_previous_close",
            "trigger_previous_entity_high",
            "trigger_previous_entity_low",
            "trigger_previous_amount_baseline",
            "baseline_source_trade_date",
        ):
            entry.pop(key, None)
    return baseline


if __name__ == "__main__":
    unittest.main()
