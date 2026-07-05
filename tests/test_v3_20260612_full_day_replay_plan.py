import unittest

import run_v3_20260612_full_day_metric_once as metric_runner
from ashare_v3.market import v3_full_day_replay_plan as plan
from ashare_v3.market.realtime_virtual_metric import VIRTUAL_AMOUNT_POLICY_VERSION


SOURCE_CONDITION_RUN_ID = "condition_layer_20260611_source_20260611_for_20260612_v1"
TRIGGER_CONTEXT_RUN_ID = "trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
LIMITED_METRIC_RUN_ID = "action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1"
FULL_DAY_METRIC_RUN_ID = "v3_n3_action_confirmation_metric_20260612_full_day_replay_v1"


def scope_row(identity_key: str, *, direction: str = "buy", condition_key: str = "BUY:D") -> dict:
    asset_kind = identity_key.split(":", 1)[0]
    identity_column = {
        "stock": "stock_identity_key",
        "index": "index_identity_key",
        "board": "board_identity_key",
    }[asset_kind]
    return {
        "asset_kind": asset_kind,
        identity_column: identity_key,
        "run_id": SOURCE_CONDITION_RUN_ID,
        "for_trade_date": "20260612",
        "direction": direction,
        "condition_key": condition_key,
        "minute_required": True,
    }


def context_row(identity_key: str, *, direction: str = "buy", condition_key: str = "BUY:D") -> dict:
    return {
        "asset_kind": identity_key.split(":", 1)[0],
        "identity_key": identity_key,
        "run_id": TRIGGER_CONTEXT_RUN_ID,
        "for_trade_date": "20260612",
        "direction": direction,
        "condition_key": condition_key,
    }


def metric_context_row(identity_key: str = "stock:SH:603259") -> dict:
    return {
        "asset_kind": "stock",
        "identity_key": identity_key,
        "trigger_context_id": 56560,
        "source_trade_date": "20260611",
        "exchange": "SH",
        "code": "603259",
        "display_code": "603259",
        "name": "药明康德",
        "raw_json": {
            "period_trigger_baseline_json": {
                "periods": {
                    "D": {
                        "current_open_seed": "96.01",
                        "previous_open": "93.35",
                        "previous_close": "97.04",
                        "previous_amount": "5540197.469",
                        "current_amount_seed": "3180116.04",
                        "current_trade_days_seed": 1,
                    },
                    "W": {
                        "current_open_seed": "98.00",
                        "previous_open": "95.00",
                        "previous_close": "99.00",
                        "previous_amount": "3985200.357",
                        "current_amount_seed": "5160733.9835",
                        "current_trade_days_seed": 4,
                    },
                    "M": {
                        "current_open_seed": "101.63",
                        "previous_open": "111.63",
                        "previous_close": "101.60",
                        "previous_amount": "4573281.0928",
                        "current_amount_seed": "4507659.7465",
                        "current_trade_days_seed": 9,
                    },
                    "Q": {
                        "current_open_seed": "100.06",
                        "previous_open": "90.85",
                        "previous_close": "98.10",
                        "previous_amount": "3825572.8950",
                        "current_amount_seed": "4620711.0070",
                        "current_trade_days_seed": 48,
                    },
                    "Y": {
                        "current_open_seed": "62.50",
                        "previous_open": "63.03",
                        "previous_close": "62.14",
                        "previous_amount": "3620436.1820",
                        "current_amount_seed": "4192559.7160",
                        "current_trade_days_seed": 104,
                    },
                }
            }
        },
    }


def minute_row(
    run_id: str,
    trade_date: str,
    label: str,
    *,
    amount: float,
    open_: float = 96.0,
    close: float = 96.5,
    identity_key: str = "stock:SH:603259",
    code: str = "603259",
) -> dict:
    return {
        "identity_key": identity_key,
        "bar_id": abs(hash((run_id, label))) % 1000000,
        "run_id": run_id,
        "trade_date": trade_date,
        "bar_time": f"{label}:00+08:00",
        "code": code,
        "open": open_,
        "high": max(open_, close),
        "low": min(open_, close),
        "close": close,
        "amount": amount,
        "raw_json": {},
    }


class V320260612FullDayReplayPlanTest(unittest.TestCase):
    def test_metric_run_insert_uses_single_python_started_at(self) -> None:
        class FakeCursor:
            def __init__(self) -> None:
                self.sql = ""
                self.params = ()

            def execute(self, sql: str, params: tuple) -> None:
                self.sql = sql
                self.params = params

        cursor = FakeCursor()
        started_at = "2026-06-13T14:30:00+08:00"

        metric_runner.insert_metric_run(cursor, expected_total=123, started_at=started_at)

        self.assertNotIn("now()", cursor.sql.lower())
        self.assertEqual(cursor.params[-2], started_at)

    def test_coverage_audit_blocks_when_context_object_lacks_n3_1m_and_metric(self) -> None:
        report = plan.build_full_day_coverage_audit_report(
            for_trade_date="20260612",
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=TRIGGER_CONTEXT_RUN_ID,
            existing_metric_run_id=LIMITED_METRIC_RUN_ID,
            scope_rows=[
                scope_row("stock:SH:603259", direction="buy", condition_key="BUY:Q,M,W,D"),
                scope_row("stock:SH:603259", direction="sell", condition_key="SELL:Y,Q,W,D"),
                scope_row("stock:SH:600000"),
            ],
            context_rows=[
                context_row("stock:SH:603259", direction="buy", condition_key="BUY:Q,M,W,D"),
                context_row("stock:SH:603259", direction="sell", condition_key="SELL:Y,Q,W,D"),
                context_row("stock:SH:600000"),
            ],
            minute_coverage_rows=[
                {"asset_kind": "stock", "identity_key": "stock:SH:600000", "row_count": 240, "rows_before_focus": 86},
            ],
            metric_coverage_rows=[
                {"asset_kind": "stock", "identity_key": "stock:SH:600000", "row_count": 240, "rows_before_focus": 86},
            ],
            focus_identity_key="stock:SH:603259",
            focus_minute_label="10:56",
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("n3_1m_source_missing_for_context_scope", report["blockers"])
        self.assertIn("n3_metric_missing_for_context_scope", report["blockers"])
        self.assertEqual(report["focus_object"]["identity_key"], "stock:SH:603259")
        self.assertEqual(report["focus_object"]["scope_rows"], 2)
        self.assertEqual(report["focus_object"]["context_rows"], 2)
        self.assertEqual(report["focus_object"]["minute_rows"], 0)
        self.assertEqual(report["focus_object"]["metric_rows"], 0)
        self.assertEqual(report["focus_object"]["rows_before_focus_minute"], 0)
        self.assertTrue(report["next_gate"]["allow_n3_1m_backfill_contract_preflight"])
        self.assertFalse(report["next_gate"]["allow_n4_replay_contract_preflight"])
        self.assertFalse(report["forbidden_scope_proof"]["old_system_read"])

    def test_backfill_contract_is_scoped_and_does_not_authorize_execute(self) -> None:
        audit = plan.build_full_day_coverage_audit_report(
            for_trade_date="20260612",
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            trigger_context_run_id=TRIGGER_CONTEXT_RUN_ID,
            existing_metric_run_id=LIMITED_METRIC_RUN_ID,
            scope_rows=[scope_row("stock:SH:603259")],
            context_rows=[context_row("stock:SH:603259")],
            minute_coverage_rows=[],
            metric_coverage_rows=[],
            focus_identity_key="stock:SH:603259",
            focus_minute_label="10:56",
        )

        contract, preflight, rollback_sql = plan.build_n3_full_day_backfill_contract_preflight(
            audit,
            backfill_run_id=plan.FULL_DAY_1M_BACKFILL_RUN_ID,
            metric_run_id=FULL_DAY_METRIC_RUN_ID,
        )

        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertFalse(preflight["execute_authorized"])
        self.assertEqual(contract["backfill_run_id"], plan.FULL_DAY_1M_BACKFILL_RUN_ID)
        self.assertEqual(contract["source_scope"]["missing_context_objects_total"], 1)
        self.assertIn("stock:SH:603259", contract["source_scope"]["missing_context_identity_sample"])
        self.assertIn("RAISE EXCEPTION", rollback_sql)
        self.assertIn(plan.FULL_DAY_1M_BACKFILL_RUN_ID, rollback_sql)
        self.assertIn("common_event_outbox", rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_trigger_run", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("user_signal_projection", rollback_sql)
        self.assertNotIn("DROP", rollback_sql)
        self.assertNotIn("TRUNCATE", rollback_sql)

    def test_build_backfill_records_marks_retained_and_adapter_sources(self) -> None:
        context_rows = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:603259",
                "exchange": "SH",
                "code": "603259",
                "display_code": "603259",
                "name": "药明康德",
                "source_scope_ids": [1, 2],
                "source_condition_pool_ids": [11],
                "source_market_subscription_id": None,
            }
        ]
        retained_rows = {
            "stock:SH:603259": [
                {
                    "bar_time": f"2026-06-12T09:{31 + (idx % 20):02d}:00+08:00",
                    "open": "97.50",
                    "high": "97.60",
                    "low": "97.20",
                    "close": "97.23",
                    "volume": "100",
                    "amount": "1000",
                    "source_run_id": "old_v3_run",
                    "source_bar_id": idx,
                }
                for idx in range(plan.FULL_DAY_EXPECTED_1M_BAR_COUNT)
            ]
        }

        records, results = plan.build_full_day_backfill_records_for_context(
            context_rows=context_rows,
            retained_rows_by_identity=retained_rows,
            adapter_rows_by_identity={},
            backfill_run_id=plan.FULL_DAY_1M_BACKFILL_RUN_ID,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            for_trade_date="20260612",
        )

        self.assertEqual(len(records["stock"]), plan.FULL_DAY_EXPECTED_1M_BAR_COUNT)
        self.assertEqual(records["stock"][0]["source_adapter"], "v3_retained_minute_bar_1m")
        self.assertEqual(records["stock"][0]["raw_json"]["retained_from_run_id"], "old_v3_run")
        self.assertEqual(results[0]["source_policy"], "retained_v3_minute_fact")

        fetched_records, fetched_results = plan.build_full_day_backfill_records_for_context(
            context_rows=context_rows,
            retained_rows_by_identity={},
            adapter_rows_by_identity={
                "stock:SH:603259": [
                    {
                        "bar_time": "2026-06-12T10:56:00+08:00",
                        "open": 98.61,
                        "high": 98.75,
                        "low": 98.50,
                        "close": 98.67,
                        "volume": 521100,
                        "amount": 51370448,
                        "raw_payload": {"datetime": "2026-06-12 10:56"},
                    }
                ]
            },
            backfill_run_id=plan.FULL_DAY_1M_BACKFILL_RUN_ID,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            for_trade_date="20260612",
        )

        self.assertEqual(len(fetched_records["stock"]), 1)
        self.assertEqual(fetched_records["stock"][0]["source_adapter"], "mootdx_full_day_1m_backfill")
        self.assertEqual(fetched_results[0]["source_policy"], "mootdx_full_day_backfill")
        self.assertEqual(fetched_records["stock"][0]["raw_json"]["source_policy"], "mootdx_full_day_backfill")

    def test_build_backfill_records_can_write_previous_day_preload_scope(self) -> None:
        context_rows = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:603259",
                "exchange": "SH",
                "code": "603259",
                "display_code": "603259",
                "name": "药明康德",
                "source_scope_ids": [1],
                "source_condition_pool_ids": [11],
                "source_market_subscription_id": None,
            }
        ]

        records, results = plan.build_full_day_backfill_records_for_context(
            context_rows=context_rows,
            retained_rows_by_identity={},
            adapter_rows_by_identity={
                "stock:SH:603259": [
                    {
                        "bar_time": "2026-06-11T10:56:00+08:00",
                        "open": 96.00,
                        "high": 97.00,
                        "low": 95.50,
                        "close": 96.80,
                        "volume": 100,
                        "amount": 1000,
                    }
                ]
            },
            backfill_run_id=plan.FULL_DAY_PREVIOUS_1M_BACKFILL_RUN_ID,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            for_trade_date="20260612",
            minute_trade_date="20260611",
            is_previous_day_preload=True,
        )

        self.assertEqual(results[0]["source_policy"], "mootdx_full_day_backfill")
        self.assertEqual(records["stock"][0]["for_trade_date"], "20260612")
        self.assertEqual(records["stock"][0]["trade_date"], "20260611")
        self.assertTrue(records["stock"][0]["is_previous_day_preload"])
        self.assertTrue(records["stock"][0]["raw_json"]["is_previous_day_preload"])

    def test_execute_flags_block_before_backfill_work(self) -> None:
        with self.assertRaisesRegex(plan.FullDayBackfillBlocked, "missing --execute"):
            plan.require_full_day_backfill_execute_flags(execute=False, user_confirmed=True)
        with self.assertRaisesRegex(plan.FullDayBackfillBlocked, "missing --user-confirmed"):
            plan.require_full_day_backfill_execute_flags(execute=True, user_confirmed=False)

    def test_period_baseline_context_maps_n4_localized_n2_fields(self) -> None:
        context = plan.higher_period_context_from_trigger_context(metric_context_row())

        self.assertEqual(context["D"]["current_open"], "96.01")
        self.assertEqual(context["D"]["previous_open"], "93.35")
        self.assertEqual(context["D"]["previous_close"], "97.04")
        self.assertEqual(context["D"]["previous_amount"], "5540197.469")
        self.assertEqual(context["D"]["elapsed_units"], 1)
        self.assertEqual(context["D"]["total_units"], 1)
        self.assertEqual(context["Y"]["total_units"], 240)

    def test_full_day_metric_rows_include_previous_day_same_window_amount(self) -> None:
        previous_rows = [
            minute_row(plan.FULL_DAY_PREVIOUS_MINUTE_RUN_ID, "20260611", f"2026-06-11 10:{minute:02d}", amount=1000)
            for minute in range(1, 57)
        ]
        current_rows = [
            minute_row(plan.FULL_DAY_1M_BACKFILL_RUN_ID, "20260612", f"2026-06-12 10:{minute:02d}", amount=2000)
            for minute in range(1, 57)
        ]

        rows = plan.build_full_day_metric_rows_for_identity(
            context_row=metric_context_row(),
            minute_rows=[*previous_rows, *current_rows],
            contract=plan.full_day_metric_contract(),
        )

        last = rows[-1]
        self.assertEqual(len(rows), 56)
        self.assertEqual(last["projection_run_id"], plan.FULL_DAY_METRIC_RUN_ID)
        self.assertEqual(last["source_snapshot_run_id"], plan.FULL_DAY_1M_BACKFILL_RUN_ID)
        self.assertEqual(last["source_previous_day_minute_run_id"], plan.FULL_DAY_PREVIOUS_MINUTE_RUN_ID)
        self.assertEqual(last["current_price_source"], "minute_bar_1m")
        self.assertTrue(last["metric_ready"], last)
        self.assertEqual(float(last["previous_day_same_window_amount"]), 26000.0)
        self.assertGreater(len(last["previous_day_minute_refs"]), 0)
        self.assertTrue(last["is_closed_1m"])
        proof = last["raw_json"]["formal_period_amount_proof"]
        self.assertEqual(proof["source_kind"], "N3_standard_period_metric")
        self.assertEqual(proof["amount_unit"], "yuan")
        self.assertEqual(proof["periods"]["D"]["current_amount_source_kind"], "N3_standard_period_metric")
        self.assertEqual(proof["periods"]["D"]["current_amount_field"], "current_d_virtual_amount")
        self.assertEqual(last["trace_json"]["formal_period_amount_proof"], proof)

    def test_full_day_metric_rows_include_calibrated_virtual_amount_policy_envelope(self) -> None:
        previous_rows = [
            minute_row(plan.FULL_DAY_PREVIOUS_MINUTE_RUN_ID, "20260611", "2026-06-11 09:31", amount=100),
            minute_row(plan.FULL_DAY_PREVIOUS_MINUTE_RUN_ID, "20260611", "2026-06-11 09:32", amount=200),
            minute_row(plan.FULL_DAY_PREVIOUS_MINUTE_RUN_ID, "20260611", "2026-06-11 09:33", amount=300),
        ]
        current_rows = [
            minute_row(plan.FULL_DAY_1M_BACKFILL_RUN_ID, "20260612", "2026-06-12 09:31", amount=10),
            minute_row(plan.FULL_DAY_1M_BACKFILL_RUN_ID, "20260612", "2026-06-12 09:32", amount=20),
        ]

        rows = plan.build_full_day_metric_rows_for_identity(
            context_row=metric_context_row(),
            minute_rows=[*previous_rows, *current_rows],
            contract=plan.full_day_metric_contract(),
        )

        row = rows[-1]
        self.assertEqual(row["current_5m_virtual_amount"], 60.0)
        self.assertEqual(row["current_30m_virtual_amount"], 60.0)
        self.assertNotEqual(row["current_30m_virtual_amount"], 30.0 / 2.0 * 30.0)
        self.assertEqual(row["raw_json"]["virtual_amount_policy_version"], VIRTUAL_AMOUNT_POLICY_VERSION)
        self.assertEqual(
            row["trace_json"]["virtual_amount_policy"]["policy_version"],
            VIRTUAL_AMOUNT_POLICY_VERSION,
        )
        self.assertEqual(row["trace_json"]["virtual_amount_policy"]["source_kind"], "N3_standard_period_metric")
        self.assertEqual(
            row["trace_json"]["virtual_amount_policy"]["periods"]["30m"]["previous_day_same_elapsed_amount"],
            300.0,
        )

    def test_full_day_metric_formal_amount_chain_uses_with_today_period_averages(self) -> None:
        context = metric_context_row("stock:SZ:000682")
        context.update(
            {
                "exchange": "SZ",
                "code": "000682",
                "display_code": "000682",
                "name": "东方电子",
            }
        )
        context["raw_json"]["period_trigger_baseline_json"]["periods"] = {
            "D": {
                "current_open_seed": "12.43",
                "previous_open": "12.43",
                "previous_close": "12.42",
                "previous_amount": "322493.57303",
                "previous_avg_amount": "322493.57303",
                "current_amount_seed": "0",
                "current_amount_total_seed": "0",
                "current_trade_days_seed": 1,
            },
            "W": {
                "current_open_seed": "12.4",
                "previous_open": "12.46",
                "previous_close": "12.3",
                "previous_amount": "289004.241704",
                "previous_avg_amount": "289004.241704",
                "current_amount_seed": "323619.612685",
                "current_amount_total_seed": "647239.22537",
                "current_trade_days_seed": 2,
            },
            "M": {
                "current_open_seed": "13.99",
                "previous_open": "13.11",
                "previous_close": "13.99",
                "previous_amount": "561603.765502777778",
                "previous_avg_amount": "561603.765502777778",
                "current_amount_seed": "382935.80565",
                "current_amount_total_seed": "4595229.6678",
                "current_trade_days_seed": 12,
            },
            "Q": {
                "current_open_seed": "12.34",
                "previous_open": "11.95",
                "previous_close": "12.09",
                "previous_amount": "433919.225125",
                "previous_avg_amount": "433919.225125",
                "current_amount_seed": "421747.172879411765",
                "current_amount_total_seed": "21509105.81685",
                "current_trade_days_seed": 51,
            },
            "Y": {
                "current_open_seed": "11.95",
                "previous_open": "10.6305877803557618",
                "previous_close": "11.86",
                "previous_amount": "226430.311897119342",
                "previous_avg_amount": "226430.311897119342",
                "current_amount_seed": "428117.592746261682",
                "current_amount_total_seed": "45808582.42385",
                "current_trade_days_seed": 107,
            },
        }
        previous_rows = [
            minute_row(
                plan.FULL_DAY_PREVIOUS_1M_BACKFILL_RUN_ID,
                "20260611",
                "2026-06-11 15:00",
                amount=28_411_975,
                open_=12.42,
                close=12.43,
                identity_key="stock:SZ:000682",
                code="000682",
            )
        ]
        current_rows = [
            minute_row(
                plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                "20260612",
                "2026-06-12 15:00",
                amount=454_974_737.22928,
                open_=12.43,
                close=12.90,
                identity_key="stock:SZ:000682",
                code="000682",
            )
        ]

        rows = plan.build_full_day_metric_rows_for_identity(
            context_row=context,
            minute_rows=[*previous_rows, *current_rows],
            contract=plan.full_day_metric_contract(),
        )

        row = rows[-1]
        chain = row["trace_json"]["formal_period_amount_proof"]["amount_chain_metrics"]
        expected_weekly_avg = (647_239_225.37 + 454_974_737.22928) / 3.0
        self.assertAlmostEqual(chain["today_virt_amount"], 454_974_737.22928)
        self.assertAlmostEqual(chain["weekly_avg_with_today"], expected_weekly_avg)
        self.assertAlmostEqual(chain["prev_weekly_avg"], 289_004_241.704)
        self.assertAlmostEqual(row["weekly_avg_with_today"], expected_weekly_avg)
        self.assertNotAlmostEqual(row["current_w_virtual_amount"], expected_weekly_avg)
        self.assertGreater(row["current_w_virtual_amount"], 1_000_000_000)


if __name__ == "__main__":
    unittest.main()
