import unittest
from unittest.mock import patch

import run_full_context_formal_action_confirmation_metric_once as formal_runner
from ashare_v3.market import v3_full_day_replay_plan as plan
from ashare_v3.trigger.action_confirmation_metric_matcher import (
    TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
    build_action_confirmation_metric_plans,
    formal_trigger_period_proof,
)


FOR_TRADE_DATE = "20260622"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260618_source_20260618_for_20260622_v1"
SOURCE_SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260622_full_context_expansion_"
    "condition_layer_20260618_source_20260618_for_20260622_v1"
)
TODAY_MINUTE_RUN_ID = (
    "today_minute_bar_1m_20260622_until_1500__"
    "market_data_subscription_20260622_full_context_expansion_"
    "condition_layer_20260618_source_20260618_for_20260622_v1"
)
PREVIOUS_DAY_MINUTE_RUN_ID = (
    "previous_day_minute_preload_20260618_for_20260622__"
    "previous_day_minute_preload_20260618_for_20260622_full_context_expansion__"
    "market_data_subscription_20260622_full_context_expansion_"
    "condition_layer_20260618_source_20260618_for_20260622_v1"
)
CONTEXT_RUN_ID = "trigger_context_snapshot_20260622_condition_layer_20260618_source_20260618_for_20260622_v1"
PROJECTION_RUN_ID = (
    "action_confirmation_projection_metric_20260622_full_context_formal_until_1500__"
    "market_data_subscription_20260622_full_context_expansion_"
    "condition_layer_20260618_source_20260618_for_20260622_v1"
)


def lineage() -> plan.FullContextFormalMetricLineage:
    return plan.FullContextFormalMetricLineage(
        for_trade_date=FOR_TRADE_DATE,
        source_trade_date="20260618",
        previous_trade_date="20260618",
        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
        source_subscription_run_id=SOURCE_SUBSCRIPTION_RUN_ID,
        source_today_minute_run_id=TODAY_MINUTE_RUN_ID,
        source_previous_day_minute_run_id=PREVIOUS_DAY_MINUTE_RUN_ID,
        trigger_context_run_id=CONTEXT_RUN_ID,
        projection_run_id=PROJECTION_RUN_ID,
    )


def identity_key(asset_kind: str, index: int) -> str:
    if asset_kind == "stock":
        return f"stock:SH:{600000 + index:06d}"
    if asset_kind == "index":
        return f"index:SH:{index:06d}"
    return f"board:TDX:BK{index:04d}"


def context_row(asset_kind: str = "stock", index: int = 0) -> dict:
    identity = identity_key(asset_kind, index)
    code = identity.rsplit(":", 1)[-1]
    period_baseline = {
        "periods": {
            "D": {
                "current_open_seed": "10",
                "previous_open": "9",
                "previous_close": "10",
                "previous_amount": "1000",
                "previous_avg_amount": "1000",
                "trigger_previous_entity_high": "10",
                "trigger_previous_entity_low": "8",
                "previous_transition": "flat",
                "current_amount_seed": "0",
                "current_trade_days_seed": 1,
            },
            "W": {
                "current_open_seed": "10",
                "previous_open": "9",
                "previous_close": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "current_amount_seed": "0",
                "current_trade_days_seed": 1,
            },
            "M": {
                "current_open_seed": "10",
                "previous_open": "9",
                "previous_close": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "current_amount_seed": "0",
                "current_trade_days_seed": 1,
            },
            "Q": {
                "current_open_seed": "10",
                "previous_open": "9",
                "previous_close": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "current_amount_seed": "0",
                "current_trade_days_seed": 1,
            },
            "Y": {
                "current_open_seed": "10",
                "previous_open": "9",
                "previous_close": "10",
                "previous_amount": "100",
                "previous_avg_amount": "100",
                "current_amount_seed": "0",
                "current_trade_days_seed": 1,
            },
        }
    }
    return {
        "asset_kind": asset_kind,
        "identity_key": identity,
        "trigger_context_id": index + 1000,
        "run_id": CONTEXT_RUN_ID,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_trade_date": "20260618",
        "prev_trade_date": "20260618",
        "for_trade_date": FOR_TRADE_DATE,
        "exchange": identity.split(":")[1],
        "code": code,
        "display_code": code,
        "name": identity,
        "direction": "buy",
        "condition_key": "BUY:D",
        "condition_periods": ["D"],
        "allowed_signal_types": ["B_BUY", "B_BUY_30M_VOL"],
        "quality_status": "passed",
        "period_trigger_baseline_json": period_baseline,
        "raw_json": {"period_trigger_baseline_json": period_baseline},
    }


def context_rows_by_asset(counts: dict[str, int]) -> list[dict]:
    rows = []
    for asset, count in counts.items():
        for index in range(count):
            rows.append(context_row(asset, index))
    return rows


def set_period_seed(
    context: dict,
    *,
    period: str,
    period_key_current: str,
    current_amount_seed: str = "100",
    current_amount_total_seed: str = "400",
    current_trade_days_seed: int = 4,
) -> None:
    item = context["period_trigger_baseline_json"]["periods"][period]
    item.update(
        {
            "period_key_current": period_key_current,
            "current_amount_seed": current_amount_seed,
            "current_amount_total_seed": current_amount_total_seed,
            "current_trade_days_seed": current_trade_days_seed,
            "previous_amount": "50",
            "previous_avg_amount": "50",
        }
    )
    context["raw_json"]["period_trigger_baseline_json"] = context["period_trigger_baseline_json"]


def metric_last_row_for_dates(
    context: dict,
    *,
    for_trade_date: str,
    source_trade_date: str,
    today_amount: float = 1000.0,
) -> dict:
    context["for_trade_date"] = for_trade_date
    context["source_trade_date"] = source_trade_date
    context["prev_trade_date"] = source_trade_date
    identity = context["identity_key"]
    today_label = f"{for_trade_date[:4]}-{for_trade_date[4:6]}-{for_trade_date[6:]} 15:00"
    source_label = f"{source_trade_date[:4]}-{source_trade_date[4:6]}-{source_trade_date[6:]} 15:00"
    rows = plan.build_full_day_metric_rows_for_identity(
        context_row=context,
        minute_rows=[
            minute_row(
                PREVIOUS_DAY_MINUTE_RUN_ID,
                source_trade_date,
                source_label,
                previous=True,
                identity_key=identity,
                amount=500.0,
            ),
            minute_row(
                TODAY_MINUTE_RUN_ID,
                for_trade_date,
                today_label,
                identity_key=identity,
                amount=today_amount,
            ),
        ],
        contract=plan.full_day_metric_contract(lineage()),
        for_trade_date=for_trade_date,
        source_today_minute_run_id=TODAY_MINUTE_RUN_ID,
        source_previous_day_minute_run_id=PREVIOUS_DAY_MINUTE_RUN_ID,
    )
    return rows[-1]


def coverage_rows(context_rows: list[dict], row_count: int = plan.FULL_DAY_EXPECTED_1M_BAR_COUNT) -> list[dict]:
    return [
        {
            "asset_kind": row["asset_kind"],
            "identity_key": row["identity_key"],
            "row_count": row_count,
        }
        for row in context_rows
    ]


def zero_baseline() -> dict[str, int]:
    return {
        "common_market_data_run": 0,
        "common_market_data_quality_item": 0,
        "stock_action_confirmation_projection_metric": 0,
        "index_action_confirmation_projection_metric": 0,
        "board_action_confirmation_projection_metric": 0,
        "common_event_outbox": 0,
        "common_event_inbox": 0,
        "common_event_consumer_checkpoint": 0,
    }


def minute_labels() -> list[str]:
    morning = [f"2026-06-22 {hour:02d}:{minute:02d}" for hour in (9, 10, 11) for minute in range(0, 60)]
    morning = [label for label in morning if "09:31" <= label[-5:] <= "11:30"]
    afternoon = [f"2026-06-22 13:{minute:02d}" for minute in range(1, 60)]
    afternoon += [f"2026-06-22 14:{minute:02d}" for minute in range(0, 60)]
    afternoon += ["2026-06-22 15:00"]
    labels = morning + afternoon
    assert len(labels) == plan.FULL_DAY_EXPECTED_1M_BAR_COUNT
    return labels


def minute_row(
    run_id: str,
    trade_date: str,
    label: str,
    *,
    previous: bool = False,
    identity_key: str = "stock:SH:600000",
    amount: float | int | None = None,
) -> dict:
    code = identity_key.rsplit(":", 1)[-1]
    return {
        "identity_key": identity_key,
        "bar_id": abs(hash((run_id, label, identity_key))) % 1000000,
        "run_id": run_id,
        "trade_date": trade_date,
        "bar_time": f"{label}:00+08:00",
        "code": code,
        "open": 11,
        "high": 12,
        "low": 10,
        "close": 11.5 if not previous else 9.5,
        "amount": amount if amount is not None else 1000 if previous else 2000,
        "raw_json": {},
    }


class FullContextFormalActionConfirmationMetricTest(unittest.TestCase):
    def test_explicit_lineage_builds_expected_20260622_shape(self) -> None:
        rows = context_rows_by_asset({"stock": 1833, "index": 9, "board": 127})

        report = plan.build_full_context_formal_metric_plan_report(
            lineage=lineage(),
            context_rows=rows,
            today_coverage_rows=coverage_rows(rows),
            previous_coverage_rows=coverage_rows(rows),
            baseline_counts=zero_baseline(),
        )

        self.assertEqual(report["result"], "PLAN_PASS")
        self.assertEqual(report["projection_schema_version"], TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION)
        self.assertEqual(report["expected_rows"]["stock"], 439920)
        self.assertEqual(report["expected_rows"]["index"], 2160)
        self.assertEqual(report["expected_rows"]["board"], 30480)
        self.assertEqual(report["expected_rows"]["total"], 472560)
        self.assertEqual(report["write_scope"]["allowed_future_execute_write_tables"], [
            "common_market_data_run",
            "common_market_data_quality_item",
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
        ])
        self.assertFalse(report["write_scope"]["writes_outbox"])

    def test_parameterized_rows_use_full_context_lineage_and_formal_proof_fields(self) -> None:
        current = [minute_row(TODAY_MINUTE_RUN_ID, FOR_TRADE_DATE, label) for label in minute_labels()]
        previous = [
            minute_row(
                PREVIOUS_DAY_MINUTE_RUN_ID,
                "20260618",
                label.replace("2026-06-22", "2026-06-18"),
                previous=True,
            )
            for label in minute_labels()
        ]

        rows = plan.build_full_day_metric_rows_for_identity(
            context_row=context_row("stock", 0),
            minute_rows=[*previous, *current],
            contract=plan.full_day_metric_contract(lineage()),
            for_trade_date=FOR_TRADE_DATE,
            source_today_minute_run_id=TODAY_MINUTE_RUN_ID,
            source_previous_day_minute_run_id=PREVIOUS_DAY_MINUTE_RUN_ID,
        )

        self.assertEqual(len(rows), 240)
        last = rows[-1]
        self.assertEqual(last["projection_run_id"], PROJECTION_RUN_ID)
        self.assertEqual(last["projection_schema_version"], TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION)
        self.assertEqual(last["source_snapshot_run_id"], TODAY_MINUTE_RUN_ID)
        self.assertEqual(last["source_today_minute_run_id"], TODAY_MINUTE_RUN_ID)
        self.assertEqual(last["source_previous_day_minute_run_id"], PREVIOUS_DAY_MINUTE_RUN_ID)
        self.assertIn("formal_period_amount_proof", last["raw_json"])
        self.assertIn("formal_amount_chain_metrics", last["raw_json"])
        self.assertIn("formal_period_amount_proof", last["trace_json"])
        self.assertIn("formal_amount_chain_metrics", last["trace_json"])
        self.assertEqual(
            last["raw_json"]["formal_period_amount_proof"]["periods"]["D"]["current_amount_field"],
            "current_d_virtual_amount",
        )

    def test_formal_amount_unit_rule_is_explicit_by_asset_kind(self) -> None:
        cases = [
            ("stock", "298615.373", 298615373.0, "thousand_yuan", 1000.0, 298615373.0),
            ("board", "11794216960", 13855807184.0, "yuan", 1.0, 11794216960.0),
            ("index", "1560474025984", 1704000417536.0, "yuan", 1.0, 1560474025984.0),
        ]

        for asset_kind, previous_amount, today_amount, source_unit, factor, previous_yuan in cases:
            with self.subTest(asset_kind=asset_kind):
                context = context_row(asset_kind, 1)
                periods = context["period_trigger_baseline_json"]["periods"]
                for item in periods.values():
                    item["previous_amount"] = previous_amount
                    item["previous_avg_amount"] = previous_amount
                    item["current_amount_seed"] = "0"
                    item["current_amount_total_seed"] = "0"
                    item["current_trade_days_seed"] = 1
                context["raw_json"]["period_trigger_baseline_json"] = context["period_trigger_baseline_json"]
                identity = context["identity_key"]
                rows = plan.build_full_day_metric_rows_for_identity(
                    context_row=context,
                    minute_rows=[
                        minute_row(
                            PREVIOUS_DAY_MINUTE_RUN_ID,
                            "20260618",
                            "2026-06-18 15:00",
                            previous=True,
                            identity_key=identity,
                            amount=previous_yuan,
                        ),
                        minute_row(
                            TODAY_MINUTE_RUN_ID,
                            FOR_TRADE_DATE,
                            "2026-06-22 15:00",
                            identity_key=identity,
                            amount=today_amount,
                        ),
                    ],
                    contract=plan.full_day_metric_contract(lineage()),
                    for_trade_date=FOR_TRADE_DATE,
                    source_today_minute_run_id=TODAY_MINUTE_RUN_ID,
                    source_previous_day_minute_run_id=PREVIOUS_DAY_MINUTE_RUN_ID,
                )

                last = rows[-1]
                proof = last["raw_json"]["formal_period_amount_proof"]
                d_proof = proof["periods"]["D"]

                self.assertEqual(proof["source_amount_unit"], source_unit)
                self.assertEqual(proof["proof_canonical_amount_unit"], "yuan")
                self.assertEqual(proof["unit_conversion_factor"], factor)
                self.assertEqual(proof["proof_amount_unit_source"], "explicit_asset_kind_rule")
                self.assertEqual(d_proof["source_amount_unit"], source_unit)
                self.assertEqual(d_proof["proof_canonical_amount_unit"], "yuan")
                self.assertEqual(d_proof["unit_conversion_factor"], factor)
                self.assertEqual(d_proof["proof_amount_unit_source"], "explicit_asset_kind_rule")
                self.assertEqual(last["previous_d_amount"], previous_yuan)
                self.assertEqual(d_proof["n2_previous_amount_yuan"], previous_yuan)
                self.assertEqual(last["current_d_virtual_amount"], today_amount)

    def test_current_d_amount_ignores_source_day_seed_for_all_assets(self) -> None:
        cases = [
            ("stock", "298615.373", 121370728.0, 298615373.0),
            ("index", "866583052288", 1028136370176.0, 866583052288.0),
            ("board", "11794216960", 13855807184.0, 11794216960.0),
        ]

        for asset_kind, d_seed, today_amount, previous_amount_yuan in cases:
            with self.subTest(asset_kind=asset_kind):
                context = context_row(asset_kind, 2)
                periods = context["period_trigger_baseline_json"]["periods"]
                periods["D"]["current_amount_seed"] = d_seed
                periods["D"]["current_amount_total_seed"] = d_seed
                periods["D"]["previous_amount"] = d_seed
                periods["D"]["previous_avg_amount"] = d_seed
                periods["D"]["current_trade_days_seed"] = 1
                context["raw_json"]["period_trigger_baseline_json"] = context["period_trigger_baseline_json"]
                identity = context["identity_key"]

                rows = plan.build_full_day_metric_rows_for_identity(
                    context_row=context,
                    minute_rows=[
                        minute_row(
                            PREVIOUS_DAY_MINUTE_RUN_ID,
                            "20260618",
                            "2026-06-18 15:00",
                            previous=True,
                            identity_key=identity,
                            amount=previous_amount_yuan,
                        ),
                        minute_row(
                            TODAY_MINUTE_RUN_ID,
                            FOR_TRADE_DATE,
                            "2026-06-22 15:00",
                            identity_key=identity,
                            amount=today_amount,
                        ),
                    ],
                    contract=plan.full_day_metric_contract(lineage()),
                    for_trade_date=FOR_TRADE_DATE,
                    source_today_minute_run_id=TODAY_MINUTE_RUN_ID,
                    source_previous_day_minute_run_id=PREVIOUS_DAY_MINUTE_RUN_ID,
                )

                last = rows[-1]
                d_proof = last["raw_json"]["formal_period_amount_proof"]["periods"]["D"]

                self.assertEqual(last["current_d_virtual_amount"], today_amount)
                self.assertNotEqual(last["current_d_virtual_amount"], today_amount + previous_amount_yuan)
                self.assertEqual(d_proof["current_amount_yuan"], today_amount)
                self.assertEqual(d_proof["current_d_amount_source"], "today_minute_sum_only")
                self.assertFalse(d_proof["current_d_seed_applied"])
                self.assertEqual(
                    last["raw_json"]["formal_period_amount_proof"]["period_with_today_seed_scope"],
                    "W/M/Q/Y_only",
                )

    def test_w_period_seed_resets_when_for_trade_date_enters_new_week(self) -> None:
        context = context_row("stock", 85)
        set_period_seed(context, period="W", period_key_current="2026W25")

        last = metric_last_row_for_dates(
            context,
            source_trade_date="20260618",
            for_trade_date="20260622",
            today_amount=1000.0,
        )

        proof = last["raw_json"]["formal_period_amount_proof"]["periods"]["W"]
        metrics = last["raw_json"]["formal_amount_chain_metrics"]

        self.assertEqual(proof["source_period_key"], "2026W25")
        self.assertEqual(proof["for_period_key"], "2026W26")
        self.assertFalse(proof["period_seed_applied"])
        self.assertEqual(proof["period_seed_reset_reason"], "source_period_key_mismatch_for_trade_date")
        self.assertEqual(proof["current_trade_days_seed"], 0.0)
        self.assertEqual(proof["with_today_units"], 1.0)
        self.assertEqual(metrics["weekly_avg_with_today"], 1000.0)
        self.assertEqual(proof["period_source"], "for_trade_date_new_period_today_only")
        self.assertEqual(last["current_w_virtual_amount"], 1000.0)

    def test_m_period_seed_is_retained_when_source_and_for_trade_date_are_same_month(self) -> None:
        context = context_row("stock", 86)
        set_period_seed(context, period="M", period_key_current="202606")

        last = metric_last_row_for_dates(
            context,
            source_trade_date="20260618",
            for_trade_date="20260622",
            today_amount=1000.0,
        )

        proof = last["raw_json"]["formal_period_amount_proof"]["periods"]["M"]
        metrics = last["raw_json"]["formal_amount_chain_metrics"]
        expected = (400000.0 + 1000.0) / 5.0

        self.assertEqual(proof["source_period_key"], "202606")
        self.assertEqual(proof["for_period_key"], "202606")
        self.assertTrue(proof["period_seed_applied"])
        self.assertIsNone(proof["period_seed_reset_reason"])
        self.assertEqual(proof["current_trade_days_seed"], 4.0)
        self.assertEqual(proof["with_today_units"], 5.0)
        self.assertEqual(metrics["monthly_avg_with_today"], expected)

    def test_m_q_y_period_seed_resets_on_new_current_period(self) -> None:
        cases = [
            ("M", "202606", "20260630", "20260701", "monthly_avg_with_today", "202607"),
            ("Q", "2026Q2", "20260630", "20260701", "quarterly_avg_with_today", "2026Q3"),
            ("Y", "2026", "20261231", "20270104", "yearly_avg_with_today", "2027"),
        ]

        for period, source_key, source_date, for_date, avg_field, expected_for_key in cases:
            with self.subTest(period=period):
                context = context_row("stock", 90)
                set_period_seed(context, period=period, period_key_current=source_key)

                last = metric_last_row_for_dates(
                    context,
                    source_trade_date=source_date,
                    for_trade_date=for_date,
                    today_amount=1000.0,
                )

                proof = last["raw_json"]["formal_period_amount_proof"]["periods"][period]
                metrics = last["raw_json"]["formal_amount_chain_metrics"]

                self.assertEqual(proof["source_period_key"], source_key)
                self.assertEqual(proof["for_period_key"], expected_for_key)
                self.assertFalse(proof["period_seed_applied"])
                self.assertEqual(proof["period_seed_reset_reason"], "source_period_key_mismatch_for_trade_date")
                self.assertEqual(proof["current_trade_days_seed"], 0.0)
                self.assertEqual(proof["with_today_units"], 1.0)
                self.assertEqual(metrics[avg_field], 1000.0)
                self.assertEqual(proof["period_source"], "for_trade_date_new_period_today_only")

    def test_index_m_transition_does_not_pass_when_real_today_amount_keeps_monthly_avg_below_previous(self) -> None:
        context = context_row("index", 399006)
        context.update(
            {
                "identity_key": "index:SZ:399006",
                "exchange": "SZ",
                "code": "399006",
                "display_code": "399006",
                "condition_key": "BUY:M",
                "condition_periods": ["M"],
            }
        )
        periods = context["period_trigger_baseline_json"]["periods"]
        periods["D"].update(
            {
                "current_open_seed": "4153.62",
                "trigger_previous_entity_high": "4252.39",
                "trigger_previous_entity_low": "4153.62",
                "previous_transition": "volume_up",
                "previous_amount": "866583052288",
                "previous_avg_amount": "866583052288",
                "current_amount_seed": "866583052288",
                "current_amount_total_seed": "866583052288",
                "current_trade_days_seed": 1,
            }
        )
        periods["M"].update(
            {
                "current_open_seed": "4057.39",
                "trigger_previous_entity_high": "4037.95",
                "trigger_previous_entity_low": "3760.67",
                "previous_transition": "low_volume_up",
                "previous_amount": "831565904430.54545455",
                "previous_avg_amount": "831565904430.54545455",
                "current_amount_seed": "763401357604.57142857",
                "current_amount_total_seed": "10687619006464",
                "current_trade_days_seed": 14,
            }
        )
        periods["Q"].update(
            {
                "previous_amount": "676818661376",
                "previous_avg_amount": "676818661376",
                "current_amount_seed": "738483255906.80701754",
                "current_amount_total_seed": "42093545586688",
                "current_trade_days_seed": 57,
            }
        )
        context["raw_json"]["period_trigger_baseline_json"] = context["period_trigger_baseline_json"]

        rows = plan.build_full_day_metric_rows_for_identity(
            context_row=context,
            minute_rows=[
                minute_row(
                    PREVIOUS_DAY_MINUTE_RUN_ID,
                    "20260618",
                    "2026-06-18 15:00",
                    previous=True,
                    identity_key=context["identity_key"],
                    amount=866583052288.0,
                ),
                minute_row(
                    TODAY_MINUTE_RUN_ID,
                    FOR_TRADE_DATE,
                    "2026-06-22 15:00",
                    identity_key=context["identity_key"],
                    amount=1028136370176.0,
                ),
            ],
            contract=plan.full_day_metric_contract(lineage()),
            for_trade_date=FOR_TRADE_DATE,
            source_today_minute_run_id=TODAY_MINUTE_RUN_ID,
            source_previous_day_minute_run_id=PREVIOUS_DAY_MINUTE_RUN_ID,
        )

        last = rows[-1]
        proof = formal_trigger_period_proof(row=context, metric=last)
        m_detail = next(item for item in proof["triggered_period_details"] if item["period"] == "M")
        expected_monthly_avg = (10687619006464.0 + 1028136370176.0) / 15.0

        self.assertEqual(last["current_d_virtual_amount"], 1028136370176.0)
        self.assertAlmostEqual(
            last["raw_json"]["formal_amount_chain_metrics"]["monthly_avg_with_today"],
            expected_monthly_avg,
        )
        self.assertLess(
            last["raw_json"]["formal_amount_chain_metrics"]["monthly_avg_with_today"],
            831565904430.54545455,
        )
        self.assertFalse(m_detail["transition_amount_pass"])
        self.assertNotIn("M", proof["triggered_periods"])

    def test_index_yuan_amount_unit_allows_buy_d_transition_amount_pass(self) -> None:
        context = context_row("index", 1)
        periods = context["period_trigger_baseline_json"]["periods"]
        for item in periods.values():
            item["previous_amount"] = "1560474025984"
            item["previous_avg_amount"] = "1560474025984"
            item["previous_amount_unit"] = "yuan"
            item["current_amount_seed"] = "0"
            item["current_amount_total_seed"] = "0"
            item["current_trade_days_seed"] = 1
        context["raw_json"]["period_trigger_baseline_json"] = context["period_trigger_baseline_json"]
        rows = plan.build_full_day_metric_rows_for_identity(
            context_row=context,
            minute_rows=[
                minute_row(
                    PREVIOUS_DAY_MINUTE_RUN_ID,
                    "20260618",
                    "2026-06-18 15:00",
                    previous=True,
                    identity_key=context["identity_key"],
                    amount=1560474025984.0,
                ),
                minute_row(
                    TODAY_MINUTE_RUN_ID,
                    FOR_TRADE_DATE,
                    "2026-06-22 15:00",
                    identity_key=context["identity_key"],
                    amount=1704000417536.0,
                ),
            ],
            contract=plan.full_day_metric_contract(lineage()),
            for_trade_date=FOR_TRADE_DATE,
            source_today_minute_run_id=TODAY_MINUTE_RUN_ID,
            source_previous_day_minute_run_id=PREVIOUS_DAY_MINUTE_RUN_ID,
        )

        proof = formal_trigger_period_proof(row=context, metric=rows[-1])
        d_detail = next(item for item in proof["triggered_period_details"] if item["period"] == "D")

        self.assertTrue(d_detail["transition_amount_pass"])
        self.assertEqual(d_detail["current_transition"], "volume_up")

    def test_fail_closed_when_today_or_previous_minute_coverage_is_not_240(self) -> None:
        rows = context_rows_by_asset({"stock": 1, "index": 0, "board": 0})

        today_missing = plan.build_full_context_formal_metric_plan_report(
            lineage=lineage(),
            context_rows=rows,
            today_coverage_rows=coverage_rows(rows, row_count=239),
            previous_coverage_rows=coverage_rows(rows),
            baseline_counts=zero_baseline(),
        )
        previous_missing = plan.build_full_context_formal_metric_plan_report(
            lineage=lineage(),
            context_rows=rows,
            today_coverage_rows=coverage_rows(rows),
            previous_coverage_rows=coverage_rows(rows, row_count=239),
            baseline_counts=zero_baseline(),
        )

        self.assertEqual(today_missing["result"], "PLAN_BLOCKED")
        self.assertIn("today_minute_coverage_not_240", today_missing["blockers"])
        self.assertEqual(previous_missing["result"], "PLAN_BLOCKED")
        self.assertIn("previous_day_minute_coverage_not_240", previous_missing["blockers"])

    def test_fail_closed_when_target_exists_or_lineage_mismatches(self) -> None:
        rows = context_rows_by_asset({"stock": 1, "index": 0, "board": 0})
        existing = zero_baseline()
        existing["common_market_data_run"] = 1

        target_exists = plan.build_full_context_formal_metric_plan_report(
            lineage=lineage(),
            context_rows=rows,
            today_coverage_rows=coverage_rows(rows),
            previous_coverage_rows=coverage_rows(rows),
            baseline_counts=existing,
        )
        mismatched_rows = [dict(rows[0], run_id="wrong_context_run")]
        mismatch = plan.build_full_context_formal_metric_plan_report(
            lineage=lineage(),
            context_rows=mismatched_rows,
            today_coverage_rows=coverage_rows(mismatched_rows),
            previous_coverage_rows=coverage_rows(mismatched_rows),
            baseline_counts=zero_baseline(),
        )

        self.assertEqual(target_exists["result"], "PLAN_BLOCKED")
        self.assertIn("target_projection_run_id_already_exists", target_exists["blockers"])
        self.assertEqual(mismatch["result"], "PLAN_BLOCKED")
        self.assertIn("context_lineage_mismatch", mismatch["blockers"])

    def test_fail_closed_when_context_or_formal_proof_fields_are_missing(self) -> None:
        context_missing = plan.build_full_context_formal_metric_plan_report(
            lineage=lineage(),
            context_rows=[],
            today_coverage_rows=[],
            previous_coverage_rows=[],
            baseline_counts=zero_baseline(),
        )
        rows = context_rows_by_asset({"stock": 1, "index": 0, "board": 0})
        proof_missing = plan.build_full_context_formal_metric_plan_report(
            lineage=lineage(),
            context_rows=rows,
            today_coverage_rows=coverage_rows(rows),
            previous_coverage_rows=coverage_rows(rows),
            baseline_counts=zero_baseline(),
            sample_metric_rows=[{"projection_schema_version": TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION}],
        )

        self.assertEqual(context_missing["result"], "PLAN_BLOCKED")
        self.assertIn("context_missing", context_missing["blockers"])
        self.assertEqual(proof_missing["result"], "PLAN_BLOCKED")
        self.assertIn("formal_proof_fields_missing", proof_missing["blockers"])

    def test_formal_metric_rows_can_satisfy_n4_ordinary_formal_proof(self) -> None:
        current = [minute_row(TODAY_MINUTE_RUN_ID, FOR_TRADE_DATE, label) for label in minute_labels()]
        previous = [
            minute_row(
                PREVIOUS_DAY_MINUTE_RUN_ID,
                "20260618",
                label.replace("2026-06-22", "2026-06-18"),
                previous=True,
            )
            for label in minute_labels()
        ]
        metric_rows = plan.build_full_day_metric_rows_for_identity(
            context_row=context_row("stock", 0),
            minute_rows=[*previous, *current],
            contract=plan.full_day_metric_contract(lineage()),
            for_trade_date=FOR_TRADE_DATE,
            source_today_minute_run_id=TODAY_MINUTE_RUN_ID,
            source_previous_day_minute_run_id=PREVIOUS_DAY_MINUTE_RUN_ID,
        )
        metric = metric_rows[-1]
        trigger_context = context_row("stock", 0)
        trigger_context["period_trigger_baseline_json"] = {
            "baseline_version": "test",
            "periods": {
                "D": {
                    "trigger_previous_entity_high": 10,
                    "trigger_previous_entity_low": 8,
                    "previous_avg_amount": 1000,
                    "previous_amount_unit": "yuan",
                    "previous_transition": "flat",
                }
            },
        }

        plans = build_action_confirmation_metric_plans(
            trigger_context_run_id=CONTEXT_RUN_ID,
            projection_run_id=PROJECTION_RUN_ID,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=SOURCE_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=TODAY_MINUTE_RUN_ID,
            for_trade_date=FOR_TRADE_DATE,
            context_rows=[trigger_context],
            metric_rows=[metric],
        )

        self.assertEqual(plans[0]["output_event_type"], "TriggerMatched")
        self.assertEqual(plans[0]["formal_trigger_period_proof_status"], "passed")
        self.assertIn("D", plans[0]["triggered_periods"])

    def test_runner_plan_only_does_not_write_database(self) -> None:
        report = {
            "result": "PLAN_PASS",
            "projection_run_id": PROJECTION_RUN_ID,
            "expected_rows": {"total": 472560},
            "blockers": [],
        }
        with patch.object(formal_runner.plan, "build_full_context_formal_metric_plan_from_db", return_value=report):
            with patch.object(formal_runner, "write_json") as write_json:
                with patch.object(formal_runner, "write_text") as write_text:
                    with patch.object(formal_runner, "execute_full_context_formal_metric") as execute:
                        rc = formal_runner.main(
                            [
                                "--dsn",
                                "postgresql://example",
                                "--for-trade-date",
                                FOR_TRADE_DATE,
                                "--source-trade-date",
                                "20260618",
                                "--previous-trade-date",
                                "20260618",
                                "--source-condition-run-id",
                                SOURCE_CONDITION_RUN_ID,
                                "--source-subscription-run-id",
                                SOURCE_SUBSCRIPTION_RUN_ID,
                                "--source-today-minute-run-id",
                                TODAY_MINUTE_RUN_ID,
                                "--source-previous-day-minute-run-id",
                                PREVIOUS_DAY_MINUTE_RUN_ID,
                                "--trigger-context-run-id",
                                CONTEXT_RUN_ID,
                                "--projection-run-id",
                                PROJECTION_RUN_ID,
                                "--json-report-path",
                                "tmp/report.json",
                                "--markdown-report-path",
                                "tmp/report.md",
                                "--rollback-sql-path",
                                "tmp/rollback.sql",
                            ]
                        )

        self.assertEqual(rc, 0)
        write_json.assert_called()
        write_text.assert_called()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
