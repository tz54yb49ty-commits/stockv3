import importlib.util
import contextlib
from decimal import Decimal
import io
import json
import math
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import ashare_v3.ingestion.stock_financial_canonical_metrics as metrics_module
from ashare_v3.ingestion.stock_financial_canonical_metrics import (
    ALLOWED_FUTURE_WRITE_TABLES,
    BATCH_ID,
    DAILY_BASIC_MISSING_WARNING,
    EFFECTIVE_SCORE_MAX,
    FINANCIAL_METRIC_VERSION,
    FINANCIAL_NULL_WARNING_CODE,
    FINANCIAL_SOURCE_POLICY_VERSION,
    SOURCE_TDX,
    SOURCE_TUSHARE_FALLBACK,
    SOURCE_VERSION,
    StockFinancialCanonicalBlocked,
    build_commit_plan,
    build_dry_run_report,
    build_execute_preflight_report,
    calculate_canonical_financial_metrics,
    execute_commit_transaction,
    identity_keys_sha256,
    json_safe,
    persist_rollback_sql_atomic,
    render_rollback_sql,
    snapshot_payload_to_metrics_snapshot,
    stock_financial_jsonb_row,
    validate_commit_preconditions,
    validate_dry_run_request,
    validate_execute_request,
)
from ashare_v3.ingestion.stock_financial_canonical_source_bundle import (
    build_financial_null_warning_row,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "plan_stock_financial_canonical_metrics_20260529.py"
EXECUTE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_stock_financial_canonical_metrics_once.py"
ROLLBACK_PATH = PROJECT_ROOT / "sql" / "N1_stock_financial_canonical_metrics_20260529_rollback.sql"
ROLLBACK_20260721_PATH = PROJECT_ROOT / "sql" / "N1_stock_financial_canonical_metrics_20260721_rollback.sql"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("stock_financial_canonical_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_execute_runner_module():
    spec = importlib.util.spec_from_file_location("stock_financial_canonical_execute_runner", EXECUTE_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def quarter_row(
    report_period: str,
    *,
    identity_key: str = "stock:SH:600000",
    source_type: str = SOURCE_TDX,
    announcement_date: str = "20260425",
    revenue: str = "1000",
    operating_cost: str = "600",
    taxes: str = "10",
    selling: str = "20",
    admin: str = "30",
    rd: str = "40",
    interest: str | None = "10",
    finance: str | None = None,
    operating_cashflow: str = "580",
    revenue_yoy_pct: str | None = None,
    core_profit_yoy_pct: str | None = None,
    forecast_type: str | None = "预增",
    industry: str | None = None,
) -> dict:
    _, exchange, code = identity_key.split(":", 2)
    return {
        "stock_identity_key": identity_key,
        "ts_code": f"{code}.{exchange}",
        "code": code,
        "exchange": exchange,
        "report_period": report_period,
        "announcement_date": announcement_date,
        "source_type": source_type,
        "industry": industry,
        "operating_revenue": revenue,
        "operating_cost": operating_cost,
        "taxes_and_surcharges": taxes,
        "selling_expense": selling,
        "admin_expense": admin,
        "rd_expense": rd,
        "interest_expense": interest,
        "finance_expense": finance,
        "operating_cashflow": operating_cashflow,
        "revenue_yoy_pct": revenue_yoy_pct,
        "core_profit_yoy_pct": core_profit_yoy_pct,
        "forecast_type": forecast_type,
    }


def one_row_dry_run() -> dict:
    return calculate_canonical_financial_metrics(
        financial_rows=[quarter_row("20260331", revenue_yoy_pct="1", core_profit_yoy_pct="2")],
        daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
        source_trade_date="20260529",
        expected_identity_keys=["stock:SH:600000"],
    )


def one_row_snapshot() -> dict:
    return {
        "source_trade_date": "20260529",
        "active_source_version": "stock_financial_20260529_v1",
        "active_source_metadata": {
            "data_domain": "stock",
            "data_type": "stock_financial",
            "scope_key": "20260529",
            "source_version": "stock_financial_20260529_v1",
            "source_batch_id": "condition_source_activation_20260529_v1",
            "previous_source_version": None,
            "row_count": 1,
            "identity_count": 1,
        },
        "expected_identity_keys": ["stock:SH:600000"],
        "financial_rows": [quarter_row("20260331", revenue_yoy_pct="1", core_profit_yoy_pct="2")],
        "daily_basic_rows": [{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
        "baseline": {
            "active_rows": 1,
            "conflicts": {
                "batch_conflict": 0,
                "quality_conflict": 0,
                "active_conflict": 0,
                "target_source_version_rows": 0,
            },
            "event_counts": {
                "common_event_outbox": 1,
                "common_event_inbox": 2,
                "common_event_consumer_checkpoint": 3,
            },
        },
        "source_probe": {"mock": True, "writes_performed": False},
    }


def rollback_20260721_plan() -> dict:
    return {
        "trade_date": "20260721",
        "rollback_context": {
            "data_domain": "stock",
            "data_type": "stock_financial",
            "scope_key": "20260721",
            "source_batch_id": "stock_financial_canonical_20260721_v1",
            "source_version": "stock_financial_20260721_v2",
            "previous_source_version": "stock_financial_20260721_v1",
            "previous_source_batch_id": "condition_source_activation_20260721_v1",
            "previous_previous_source_version": None,
            "previous_row_count": 5509,
            "previous_identity_count": 5509,
            "target_row_count": 5509,
            "quality_row_count": 9,
            "activated_by": "rollback.stock_financial_20260721_v2",
        },
    }


def affair_source_probe(*, warning_identity_keys=()) -> dict:
    warning_keys = sorted(str(key) for key in warning_identity_keys)
    return {
        "financial_source_policy_version": FINANCIAL_SOURCE_POLICY_VERSION,
        "financial_degraded_but_fastlane_allowed": True,
        "forecast_disabled": True,
        "financial_null_warning_identity_keys": warning_keys,
        "financial_null_warning_identity_count": len(warning_keys),
        "financial_null_warning_identity_sha256": identity_keys_sha256(warning_keys),
    }


def affair_cumulative_rows(
    *,
    identity_key: str = "stock:SH:600000",
    include_prior_q1: bool = True,
) -> list[dict]:
    period_values = [
        ("20260331", "180", "90", "4", "6", "8", "10", "3", "100"),
        ("20251231", "520", "260", "12", "20", "25", "32", "11", "290"),
        ("20250930", "360", "180", "8", "14", "18", "22", "8", "200"),
        ("20250630", "220", "110", "5", "8", "11", "14", "5", "120"),
        ("20250331", "100", "50", "2", "3", "5", "6", "2", "55"),
    ]
    if not include_prior_q1:
        period_values = period_values[:4]
    return [
        quarter_row(
            period,
            identity_key=identity_key,
            source_type="mootdx_affair",
            announcement_date="20260425",
            revenue=revenue,
            operating_cost=operating_cost,
            taxes=taxes,
            selling=selling,
            admin=admin,
            rd=rd,
            interest=interest,
            operating_cashflow=cashflow,
            forecast_type="预增",
        )
        for (
            period,
            revenue,
            operating_cost,
            taxes,
            selling,
            admin,
            rd,
            interest,
            cashflow,
        ) in period_values
    ]


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.executemany_calls: list[tuple[str, int]] = []
        self.fetchone_rows = [
            (
                "stock",
                "stock_financial",
                "20260529",
                "stock_financial_20260529_v1",
                "condition_source_activation_20260529_v1",
                None,
            ),
            (1, 1),
        ]

    def execute(self, sql: str, params=None) -> None:
        self.statements.append(" ".join(sql.split()))

    def executemany(self, sql: str, params_seq) -> None:
        rows = list(params_seq)
        self.statements.append(" ".join(sql.split()))
        self.executemany_calls.append((" ".join(sql.split()), len(rows)))

    def fetchone(self):
        return self.fetchone_rows.pop(0) if self.fetchone_rows else None


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class ExecuteHarness:
    def __init__(self) -> None:
        self.conn = RecordingConnection()
        self.calls: list[str] = []

    def deps(self) -> dict:
        return {
            "build_snapshot_from_cache": self.build_snapshot_from_cache,
            "load_active_source_metadata": self.load_active_source_metadata,
            "connect": self.connect,
            "write_artifacts": self.write_artifacts,
        }

    def build_snapshot_from_cache(self, **kwargs) -> dict:
        self.calls.append("build_snapshot_from_cache")
        return one_row_snapshot()

    def connect(self, dsn: str) -> RecordingConnection:
        self.calls.append("connect")
        return self.conn

    def load_active_source_metadata(self, **kwargs) -> dict:
        self.calls.append("load_active_source_metadata")
        return dict(one_row_snapshot()["active_source_metadata"])

    def write_artifacts(self, *args, **kwargs) -> None:
        self.calls.append("write_artifacts")


class StockFinancialCanonicalMetricsRunnerTest(unittest.TestCase):
    def test_snapshot_payload_to_metrics_snapshot_uses_financial_canonical_snapshot_v1(self) -> None:
        payload = {
            "schema_version": "financial_canonical_snapshot_v1",
            "source_trade_date": "20260615",
            "active_source_version": "stock_financial_20260615_v1",
            "expected_identity_keys": ["stock:SH:600000"],
            "financial_rows": [quarter_row("20260331", revenue_yoy_pct="1", core_profit_yoy_pct="2")],
            "daily_basic_rows": [{"stock_identity_key": "stock:SH:600000", "total_mv": "1234"}],
            "baseline": {"conflicts": {}, "event_counts": {}},
            "source_probe": {"selection_mode": "incremental_delta", "delta_symbol_count": 1},
        }

        snapshot = snapshot_payload_to_metrics_snapshot(payload)

        self.assertEqual(snapshot["source_trade_date"], "20260615")
        self.assertEqual(snapshot["expected_identity_keys"], ["stock:SH:600000"])
        self.assertEqual(snapshot["financial_rows"][0]["stock_identity_key"], "stock:SH:600000")
        self.assertEqual(snapshot["daily_basic_rows"][0]["total_mv"], "1234")
        self.assertTrue(snapshot["source_probe"]["uses_financial_canonical_snapshot_v1"])

    def test_calculator_prefers_tdx_and_computes_core_metrics(self) -> None:
        rows = [
            quarter_row("20260331", revenue_yoy_pct="25", core_profit_yoy_pct="190"),
            quarter_row("20251231", revenue="900", operating_cost="570", interest="20", revenue_yoy_pct="12", core_profit_yoy_pct="30"),
            quarter_row("20250930", revenue="800", operating_cost="570", interest="30", revenue_yoy_pct="3", core_profit_yoy_pct="8"),
            quarter_row("20250630", revenue="700", operating_cost="480", interest="20", revenue_yoy_pct="-1", core_profit_yoy_pct="5"),
            quarter_row("20250331", revenue="800", operating_cost="610", interest="20", revenue_yoy_pct="1", core_profit_yoy_pct="1"),
            quarter_row("20260331", source_type=SOURCE_TUSHARE_FALLBACK, revenue="1", operating_cost="1"),
            quarter_row("20260630", announcement_date="20260701", revenue="9999"),
            quarter_row("20261231", announcement_date="", revenue="9999"),
        ]

        result = calculate_canonical_financial_metrics(
            financial_rows=rows,
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "6900", "circ_mv": "5000"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        self.assertEqual(result["quality"]["p0_count"], 0)
        self.assertEqual(result["summary"]["tdx_primary_count"], 5)
        self.assertEqual(result["summary"]["tushare_fallback_count"], 0)
        self.assertEqual(result["summary"]["asof_excluded_future_rows"], 1)
        self.assertEqual(result["summary"]["missing_announcement_date_excluded_rows"], 1)
        row = result["rows"][0]
        self.assertEqual(row["source_version"], SOURCE_VERSION)
        self.assertEqual(row["source_batch_id"], BATCH_ID)
        self.assertEqual(row["financial_metric_version"], FINANCIAL_METRIC_VERSION)
        self.assertEqual(row["report_core_revenue"], Decimal("1000"))
        self.assertEqual(row["report_core_profit"], Decimal("290"))
        self.assertEqual(row["cash_realization_rate"], Decimal("2"))
        self.assertEqual(row["core_profit_ttm"], Decimal("700"))
        self.assertEqual(row["pe_core"], Decimal("9.8571428571"))
        self.assertEqual(row["revenue_yoy_pct"], Decimal("25"))
        self.assertEqual(row["core_profit_yoy_pct"], Decimal("190"))
        self.assertTrue(row["core_gt_revenue_yoy"])
        self.assertEqual(row["forecast_type"], "预增")
        self.assertEqual(row["forecast_score"], Decimal("3"))
        self.assertLessEqual(row["score"], Decimal("100"))
        self.assertEqual(row["quality_status"], "passed")
        self.assertNotIn("financial_source_policy_version", result)
        self.assertNotIn("effective_score_max", result)

    def test_affair_policy_disables_forecast_and_caps_effective_score_at_97(self) -> None:
        result = calculate_canonical_financial_metrics(
            financial_rows=affair_cumulative_rows(),
            daily_basic_rows=[
                {
                    "stock_identity_key": "stock:SH:600000",
                    "total_mv": "1000",
                }
            ],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            source_probe=affair_source_probe(),
        )

        self.assertEqual(result["result"], "DRY_RUN_PASS")
        self.assertEqual(result["financial_source_policy_version"], FINANCIAL_SOURCE_POLICY_VERSION)
        self.assertEqual(result["effective_score_max"], str(EFFECTIVE_SCORE_MAX))
        self.assertTrue(result["forecast_disabled"])
        row = result["rows"][0]
        self.assertIsNone(row["forecast_type"])
        self.assertIsNone(row["forecast_score"])
        self.assertEqual(row["score_breakdown_json"]["forecast_score"], "0")
        self.assertIsNotNone(row["score"])
        self.assertLessEqual(row["score"], EFFECTIVE_SCORE_MAX)
        self.assertEqual(result["summary"]["forecast_coverage_count"], 0)

    def test_affair_warning_only_row_is_p1_and_preserves_identity_with_null_metrics(self) -> None:
        identity_key = "stock:SH:600001"
        warning_row = build_financial_null_warning_row(
            identity_key,
            source_trade_date="20260529",
            reason="affair_source_unavailable",
        )
        result = calculate_canonical_financial_metrics(
            financial_rows=[warning_row],
            daily_basic_rows=[
                {"stock_identity_key": identity_key, "total_mv": "1000"}
            ],
            source_trade_date="20260529",
            expected_identity_keys=[identity_key],
            source_probe=affair_source_probe(warning_identity_keys=[identity_key]),
        )

        self.assertEqual(result["result"], "DRY_RUN_PASS")
        self.assertEqual(result["quality"]["p0_count"], 0)
        self.assertGreaterEqual(result["quality"]["p1_count"], 1)
        self.assertEqual(result["row_counts"]["stock_financial_metrics_fact"], 1)
        row = result["rows"][0]
        for field in (
            "cash_realization_rate",
            "pe_core",
            "revenue_yoy_pct",
            "core_profit_yoy_pct",
            "core_profit_ttm",
            "score",
            "forecast_type",
            "forecast_score",
        ):
            self.assertIsNone(row[field], field)
        self.assertIn(FINANCIAL_NULL_WARNING_CODE, row["financial_warning_json"]["warnings"])

    def test_affair_incomplete_four_quarter_chain_nulls_history_dependent_metrics(self) -> None:
        result = calculate_canonical_financial_metrics(
            financial_rows=affair_cumulative_rows(include_prior_q1=False),
            daily_basic_rows=[
                {
                    "stock_identity_key": "stock:SH:600000",
                    "total_mv": "1000",
                }
            ],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            source_probe=affair_source_probe(),
        )

        self.assertEqual(result["result"], "DRY_RUN_PASS")
        self.assertEqual(result["quality"]["p0_count"], 0)
        row = result["rows"][0]
        for field in (
            "core_profit_ttm",
            "pe_core",
            "revenue_yoy_pct",
            "core_profit_yoy_pct",
            "core_gt_revenue_yoy",
            "revenue_growth_streak_q",
            "core_growth_streak_q",
            "core_gt_revenue_streak_q",
            "score",
        ):
            self.assertIsNone(row[field], field)
        self.assertIn(
            "financial_history_incomplete_metrics_null",
            row["financial_warning_json"]["warnings"],
        )

    def test_affair_missing_daily_basic_is_p1_and_only_nulls_pe_and_score(self) -> None:
        result = calculate_canonical_financial_metrics(
            financial_rows=affair_cumulative_rows(),
            daily_basic_rows=[],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
            source_probe=affair_source_probe(),
        )

        self.assertEqual(result["result"], "DRY_RUN_PASS")
        self.assertEqual(result["quality"]["p0_count"], 0)
        self.assertGreaterEqual(result["quality"]["p1_count"], 1)
        row = result["rows"][0]
        self.assertIsNone(row["pe_core"])
        self.assertIsNone(row["score"])
        self.assertIsNotNone(row["report_core_profit"])
        self.assertIsNotNone(row["core_profit_ttm"])
        self.assertIn(DAILY_BASIC_MISSING_WARNING, row["financial_warning_json"]["warnings"])

    def test_interest_missing_uses_finance_expense_and_writes_warning(self) -> None:
        rows = [
            quarter_row("20260331", interest=None, finance="15", revenue_yoy_pct="1", core_profit_yoy_pct="2"),
            quarter_row("20251231", interest=None, finance="15", revenue_yoy_pct="1", core_profit_yoy_pct="2"),
        ]

        result = calculate_canonical_financial_metrics(
            financial_rows=rows,
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        row = result["rows"][0]
        self.assertEqual(row["report_core_profit"], Decimal("285"))
        self.assertIn("interest_expense_missing_finance_expense_used", row["financial_warning_json"]["warnings"])
        self.assertEqual(row["quality_status"], "warning")
        self.assertEqual(result["summary"]["interest_expense_missing_fallback_count"], 2)
        self.assertEqual(result["summary"]["ttm_annualized_count"], 1)

    def test_non_finite_interest_continues_to_finance_expense_alias(self) -> None:
        rows = [
            quarter_row("20260331", interest="nan", finance="15", revenue_yoy_pct="1", core_profit_yoy_pct="2"),
        ]

        result = calculate_canonical_financial_metrics(
            financial_rows=rows,
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        self.assertEqual(result["quality"]["p0_count"], 0)
        self.assertEqual(result["rows"][0]["report_core_profit"], Decimal("285"))
        self.assertIn("interest_expense_missing_finance_expense_used", result["rows"][0]["financial_warning_json"]["warnings"])

    def test_missing_rd_and_selling_expense_use_zero_with_warning(self) -> None:
        rows = [
            quarter_row("20260331", rd=None, selling=None, revenue_yoy_pct="1", core_profit_yoy_pct="2"),
            quarter_row("20251231", rd=None, selling=None, revenue_yoy_pct="1", core_profit_yoy_pct="2"),
        ]

        result = calculate_canonical_financial_metrics(
            financial_rows=rows,
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        row = result["rows"][0]
        self.assertEqual(result["quality"]["p0_count"], 0)
        self.assertEqual(row["report_core_profit"], Decimal("350"))
        self.assertIn("rd_expense_missing_fallback_zero", row["financial_warning_json"]["warnings"])
        self.assertIn("selling_expense_missing_fallback_zero", row["financial_warning_json"]["warnings"])
        self.assertEqual(row["quality_status"], "warning")

    def test_missing_operating_cashflow_keeps_row_with_null_cash_realization_warning(self) -> None:
        rows = [
            quarter_row("20260331", operating_cashflow=None, revenue_yoy_pct="1", core_profit_yoy_pct="2"),
            quarter_row("20251231", operating_cashflow=None, revenue_yoy_pct="1", core_profit_yoy_pct="2"),
        ]

        result = calculate_canonical_financial_metrics(
            financial_rows=rows,
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        row = result["rows"][0]
        self.assertEqual(result["quality"]["p0_count"], 0)
        self.assertIsNone(row["cash_realization_rate"])
        self.assertEqual(row["score_breakdown_json"]["cash_realization_rate"], "0")
        self.assertIn("operating_cashflow_missing_latest", row["financial_warning_json"]["warnings"])

    def test_non_finite_decimal_inputs_are_treated_as_missing(self) -> None:
        result = calculate_canonical_financial_metrics(
            financial_rows=[quarter_row("20260331", revenue_yoy_pct="nan", core_profit_yoy_pct="inf")],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        self.assertEqual(result["quality"]["p0_count"], 0)
        row = result["rows"][0]
        self.assertIsNone(row["revenue_yoy_pct"])
        self.assertIsNone(row["core_profit_yoy_pct"])
        self.assertIsNone(row["core_gt_revenue_yoy"])

    def test_json_safe_converts_non_finite_payload_values_to_null(self) -> None:
        payload = json_safe(
            {
                "interest_expense": math.nan,
                "nested": [math.inf, -math.inf, {"ok": 1}],
            }
        )

        self.assertIsNone(payload["interest_expense"])
        self.assertEqual(payload["nested"], [None, None, {"ok": 1}])
        json.dumps(payload, allow_nan=False)

    def test_stock_financial_jsonb_row_sanitizes_raw_payload_before_insert(self) -> None:
        row = dict(one_row_dry_run()["rows"][0])
        row["raw_payload"] = {"selected_financial": {"interest_expense": math.nan}}

        converted = stock_financial_jsonb_row(row)

        self.assertIsNone(converted["raw_payload"].obj["selected_financial"]["interest_expense"])
        json.dumps(converted["raw_payload"].obj, allow_nan=False)

    def test_missing_operating_cost_remains_p0(self) -> None:
        rows = [quarter_row("20260331", operating_cost=None)]

        result = calculate_canonical_financial_metrics(
            financial_rows=rows,
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        self.assertEqual(result["row_counts"]["stock_financial_metrics_fact"], 0)
        self.assertEqual(result["quality"]["p0_count"], 1)
        self.assertIn("canonical_core_line_items_missing", result["blockers"])

    def test_finance_sector_missing_operating_cost_generates_null_policy_row(self) -> None:
        result = calculate_canonical_financial_metrics(
            financial_rows=[quarter_row("20260331", operating_cost=None, industry="证券")],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000", "industry": "证券"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        self.assertEqual(result["row_counts"]["stock_financial_metrics_fact"], 1)
        self.assertEqual(result["quality"]["p0_count"], 0)
        row = result["rows"][0]
        self.assertIsNone(row["report_core_profit"])
        self.assertIsNone(row["cash_realization_rate"])
        self.assertIsNone(row["core_profit_ttm"])
        self.assertIsNone(row["pe_core"])
        self.assertIsNone(row["score"])
        self.assertEqual(row["quality_status"], "warning")
        self.assertIn("finance_sector_policy_not_supported_v1", row["financial_warning_json"]["warnings"])
        self.assertEqual(row["score_breakdown_json"]["policy"], "disabled")

    def test_pre_revenue_missing_revenue_and_cost_generates_null_policy_row(self) -> None:
        result = calculate_canonical_financial_metrics(
            financial_rows=[
                quarter_row(
                    "20260331",
                    identity_key="stock:SH:688759",
                    revenue=None,
                    operating_cost=None,
                    industry="生物制药",
                )
            ],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:688759", "total_mv": "1000", "industry": "生物制药"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:688759"],
        )

        self.assertEqual(result["row_counts"]["stock_financial_metrics_fact"], 1)
        self.assertEqual(result["quality"]["p0_count"], 0)
        row = result["rows"][0]
        self.assertIsNone(row["report_core_profit"])
        self.assertIsNone(row["core_profit_ttm"])
        self.assertIsNone(row["pe_core"])
        self.assertIsNone(row["score"])
        self.assertIn("pre_revenue_or_missing_revenue_cost", row["financial_warning_json"]["warnings"])
        self.assertEqual(row["score_breakdown_json"]["policy"], "disabled")

    def test_tushare_fallback_used_when_tdx_absent(self) -> None:
        result = calculate_canonical_financial_metrics(
            financial_rows=[
                quarter_row("20260331", source_type=SOURCE_TUSHARE_FALLBACK, revenue_yoy_pct="2", core_profit_yoy_pct="3")
            ],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1200"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        self.assertEqual(result["summary"]["tdx_primary_count"], 0)
        self.assertEqual(result["summary"]["tushare_fallback_count"], 1)
        self.assertEqual(result["quality"]["p1_count"], 2)
        self.assertIn("tushare_fallback_used", result["rows"][0]["financial_warning_json"]["warnings"])

    def test_missing_required_line_items_blocks_final_gate(self) -> None:
        result = calculate_canonical_financial_metrics(
            financial_rows=[
                {"stock_identity_key": "stock:SH:600000", "ts_code": "600000.SH", "code": "600000", "exchange": "SH", "report_period": "20260331", "announcement_date": "20260425", "source_type": SOURCE_TDX}
            ],
            daily_basic_rows=[{"stock_identity_key": "stock:SH:600000", "total_mv": "1000"}],
            source_trade_date="20260529",
            expected_identity_keys=["stock:SH:600000"],
        )

        self.assertEqual(result["row_counts"]["stock_financial_metrics_fact"], 0)
        self.assertEqual(result["quality"]["p0_count"], 1)
        self.assertIn("canonical_core_line_items_missing", result["blockers"])

    def test_execute_flag_is_rejected_for_dry_run_runner(self) -> None:
        with self.assertRaises(StockFinancialCanonicalBlocked):
            validate_dry_run_request(execute_requested=True)

    def test_runner_main_blocks_execute_before_database_work(self) -> None:
        runner = load_runner_module()
        exit_code = runner.main(["--execute"], dependencies={"build_snapshot_from_db": lambda **_: self.fail("db should not be touched")})

        self.assertEqual(exit_code, 2)

    def test_execute_request_requires_all_final_flags(self) -> None:
        cases = [
            (False, True, True, "--execute"),
            (True, False, True, "--user-confirmed"),
            (True, True, False, "--postgres-commit-enabled"),
        ]
        for execute, confirmed, commit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(StockFinancialCanonicalBlocked, message):
                    validate_execute_request(
                        execute_requested=execute,
                        user_confirmed=confirmed,
                        postgres_commit_enabled=commit,
                    )

    def test_preflight_is_ready_for_final_gate_after_dry_run_pass(self) -> None:
        snapshot = one_row_snapshot()
        dry_run = one_row_dry_run()
        preflight = build_execute_preflight_report(snapshot, dry_run)

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["runner_readiness"], "ready_for_final_gate")
        self.assertTrue(preflight["final_execute_gate_allowed"])
        self.assertTrue(preflight["execute_runner_implemented"])
        self.assertFalse(preflight["execute_authorized"])

    def test_success_commit_plan_has_expected_rows_and_allowed_scope(self) -> None:
        snapshot = one_row_snapshot()
        dry_run = one_row_dry_run()
        plan = build_commit_plan(snapshot=snapshot, dry_run=dry_run)

        self.assertEqual(plan["row_counts"], {"stock_financial_metrics_fact": 1, "total": 1})
        self.assertEqual(tuple(plan["allowed_tables"]), ALLOWED_FUTURE_WRITE_TABLES)
        self.assertEqual(plan["active_source_version_row"]["previous_source_version"], "stock_financial_20260529_v1")
        self.assertEqual(len(plan["stock_financial_rows"]), 1)
        self.assertEqual(len(plan["quality_rows"]), len(dry_run["quality"]["items"]))

    def test_commit_plan_recomputes_rows_when_dry_run_artifact_has_only_sample(self) -> None:
        snapshot = one_row_snapshot()
        dry_run = build_dry_run_report(snapshot)
        self.assertNotIn("rows", dry_run)
        self.assertEqual(dry_run["row_counts"]["stock_financial_metrics_fact"], 1)

        plan = build_commit_plan(snapshot=snapshot, dry_run=dry_run)

        self.assertEqual(plan["row_counts"], {"stock_financial_metrics_fact": 1, "total": 1})
        self.assertEqual(len(plan["stock_financial_rows"]), 1)

    def test_commit_plan_blocks_empty_fact_rows(self) -> None:
        snapshot = one_row_snapshot()
        dry_run = {**one_row_dry_run(), "rows": [], "row_counts": {"stock_financial_metrics_fact": 1}}

        with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "row_count_mismatch"):
            build_commit_plan(snapshot={**snapshot, "financial_rows": []}, dry_run=dry_run)

    def test_commit_writes_only_allowed_tables(self) -> None:
        snapshot = one_row_snapshot()
        dry_run = one_row_dry_run()
        plan = build_commit_plan(snapshot=snapshot, dry_run=dry_run)
        conn = RecordingConnection()

        with tempfile.TemporaryDirectory() as temp_dir:
            plan["rollback_sql_path"] = str(Path(temp_dir) / "rollback.sql")
            result = execute_commit_transaction(
                conn,
                commit_plan=plan,
                execute_requested=True,
                user_confirmed=True,
                postgres_commit_enabled=True,
            )

        self.assertTrue(conn.committed)
        self.assertTrue(result["committed"])
        self.assertTrue(result["rollback_safe"])
        self.assertTrue(result["rollback_artifact"]["verified"])
        self.assertEqual(tuple(result["written_tables"]), ALLOWED_FUTURE_WRITE_TABLES)
        joined = "\n".join(conn.cursor_obj.statements).lower()
        for required in (
            "common_ingest_batch",
            "stock_financial_metrics_fact",
            "common_quality_gate_result",
            "common_active_source_version",
        ):
            self.assertIn(required, joined)
        for forbidden in (
            "condition_",
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "parquet",
        ):
            self.assertNotIn(forbidden, joined)

    def test_rollback_sql_render_binds_exact_lineage_and_counts(self) -> None:
        plan = build_commit_plan(snapshot=one_row_snapshot(), dry_run=one_row_dry_run())

        sql = render_rollback_sql(plan)

        self.assertIn("stock_financial_canonical_20260529_v1", sql)
        self.assertIn("condition_source_activation_20260529_v1", sql)
        self.assertIn("stock_financial_20260529_v2", sql)
        self.assertIn("stock_financial_20260529_v1", sql)
        self.assertIn("previous_source_version = NULL", sql)
        self.assertIn("v_target_row_count <> 1", sql)
        self.assertIn("v_previous_identity_count <> 1", sql)
        self.assertIn(
            f"v_quality_row_count <> {len(one_row_dry_run()['quality']['items'])}",
            sql,
        )
        self.assertIn("GET DIAGNOSTICS v_affected_count = ROW_COUNT", sql)
        self.assertNotIn("condition_", sql.replace("condition_source_activation_20260529_v1", ""))
        self.assertNotIn("common_event_outbox", sql)

    def test_atomic_rollback_persistence_creates_and_reuses_exact_bytes(self) -> None:
        plan = build_commit_plan(snapshot=one_row_snapshot(), dry_run=one_row_dry_run())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rollback.sql"
            plan["rollback_sql_path"] = str(path)

            created = persist_rollback_sql_atomic(plan)
            reused = persist_rollback_sql_atomic(plan)

            self.assertFalse(created["reused"])
            self.assertTrue(reused["reused"])
            self.assertTrue(created["verified"])
            self.assertEqual(created["sha256"], reused["sha256"])
            self.assertEqual(created["size_bytes"], reused["size_bytes"])
            self.assertEqual(path.read_text(encoding="utf-8"), render_rollback_sql(plan))
            self.assertEqual(list(path.parent.glob(".rollback.sql.*.tmp")), [])

    def test_existing_conflicting_rollback_artifact_is_never_overwritten(self) -> None:
        plan = build_commit_plan(snapshot=one_row_snapshot(), dry_run=one_row_dry_run())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rollback.sql"
            path.write_text("-- conflicting historical bytes\n", encoding="utf-8")
            plan["rollback_sql_path"] = str(path)

            with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "rollback_sql_content_conflict"):
                persist_rollback_sql_atomic(plan)

            self.assertEqual(path.read_text(encoding="utf-8"), "-- conflicting historical bytes\n")

    def test_existing_rollback_symlink_is_rejected(self) -> None:
        plan = build_commit_plan(snapshot=one_row_snapshot(), dry_run=one_row_dry_run())
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "target.sql"
            target.write_text(render_rollback_sql(plan), encoding="utf-8")
            path = Path(temp_dir) / "rollback.sql"
            path.symlink_to(target)
            plan["rollback_sql_path"] = str(path)

            with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "rollback_sql_symlink_forbidden"):
                persist_rollback_sql_atomic(plan)

            self.assertTrue(path.is_symlink())
            self.assertEqual(target.read_text(encoding="utf-8"), render_rollback_sql(plan))

    def test_rollback_persistence_failure_blocks_before_database_dml(self) -> None:
        plan = build_commit_plan(snapshot=one_row_snapshot(), dry_run=one_row_dry_run())
        conn = RecordingConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rollback.sql"
            plan["rollback_sql_path"] = str(path)
            with mock.patch.object(metrics_module.os, "link", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "rollback_sql_persistence_failed"):
                    execute_commit_transaction(
                        conn,
                        commit_plan=plan,
                        execute_requested=True,
                        user_confirmed=True,
                        postgres_commit_enabled=True,
                    )

            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.glob(".rollback.sql.*.tmp")), [])
        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)
        self.assertEqual(conn.cursor_obj.executemany_calls, [])
        self.assertEqual(len(conn.cursor_obj.statements), 2)
        self.assertIn("FOR UPDATE", conn.cursor_obj.statements[0])

    def test_active_metadata_drift_blocks_before_artifact_or_database_dml(self) -> None:
        plan = build_commit_plan(snapshot=one_row_snapshot(), dry_run=one_row_dry_run())
        conn = RecordingConnection()
        conn.cursor_obj.fetchone_rows[0] = (
            "stock",
            "stock_financial",
            "20260529",
            "stock_financial_20260529_v1",
            "unexpected_source_batch",
            None,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rollback.sql"
            plan["rollback_sql_path"] = str(path)

            with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "metadata_drift_at_commit"):
                execute_commit_transaction(
                    conn,
                    commit_plan=plan,
                    execute_requested=True,
                    user_confirmed=True,
                    postgres_commit_enabled=True,
                )

            self.assertFalse(path.exists())
        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)
        self.assertEqual(conn.cursor_obj.executemany_calls, [])
        self.assertEqual(len(conn.cursor_obj.statements), 1)

    def test_previous_fact_drift_blocks_before_artifact_or_database_dml(self) -> None:
        plan = build_commit_plan(snapshot=one_row_snapshot(), dry_run=one_row_dry_run())
        conn = RecordingConnection()
        conn.cursor_obj.fetchone_rows[1] = (0, 0)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rollback.sql"
            plan["rollback_sql_path"] = str(path)

            with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "fact_drift_at_commit"):
                execute_commit_transaction(
                    conn,
                    commit_plan=plan,
                    execute_requested=True,
                    user_confirmed=True,
                    postgres_commit_enabled=True,
                )

            self.assertFalse(path.exists())
        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)
        self.assertEqual(conn.cursor_obj.executemany_calls, [])
        self.assertEqual(len(conn.cursor_obj.statements), 2)

    def test_final_artifact_verification_failure_rolls_back_database_transaction(self) -> None:
        plan = build_commit_plan(snapshot=one_row_snapshot(), dry_run=one_row_dry_run())
        conn = RecordingConnection()
        real_verify = metrics_module.verify_persisted_rollback_sql
        verify_calls = 0

        def fail_second_verification(commit_plan, *, reused):
            nonlocal verify_calls
            verify_calls += 1
            if verify_calls == 2:
                raise StockFinancialCanonicalBlocked("rollback_sql_content_mismatch")
            return real_verify(commit_plan, reused=reused)

        with tempfile.TemporaryDirectory() as temp_dir:
            plan["rollback_sql_path"] = str(Path(temp_dir) / "rollback.sql")
            with mock.patch.object(
                metrics_module,
                "verify_persisted_rollback_sql",
                side_effect=fail_second_verification,
            ):
                with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "rollback_sql_content_mismatch"):
                    execute_commit_transaction(
                        conn,
                        commit_plan=plan,
                        execute_requested=True,
                        user_confirmed=True,
                        postgres_commit_enabled=True,
                    )

        self.assertEqual(verify_calls, 2)
        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)
        self.assertGreater(len(conn.cursor_obj.executemany_calls), 0)

    def test_commit_preconditions_block_p0_or_conflicts(self) -> None:
        with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "canonical_core_line_items_missing"):
            validate_commit_preconditions(
                snapshot=one_row_snapshot(),
                dry_run={**one_row_dry_run(), "quality": {"p0_count": 1}, "blockers": ["canonical_core_line_items_missing"]},
                postgres_commit_enabled=True,
            )
        conflict_snapshot = one_row_snapshot()
        conflict_snapshot["baseline"]["conflicts"]["target_source_version_rows"] = 1
        with self.assertRaisesRegex(StockFinancialCanonicalBlocked, "target_source_version_rows"):
            validate_commit_preconditions(snapshot=conflict_snapshot, dry_run=one_row_dry_run(), postgres_commit_enabled=True)

    def test_execute_cli_all_flags_reaches_commit_path_with_mocked_cache(self) -> None:
        runner = load_execute_runner_module()
        harness = ExecuteHarness()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            rollback_path = Path(temp_dir) / "rollback.sql"
            execute_report_path = Path(temp_dir) / "execute.json"
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = runner.main(
                    [
                        "--source-trade-date",
                        "20260529",
                        "--execute",
                        "--user-confirmed",
                        "--postgres-commit-enabled",
                        "--source-bundle-cache-path",
                        "docs/mock-cache.json",
                        "--rollback-sql-path",
                        str(rollback_path),
                        "--json-report-path",
                        str(execute_report_path),
                        "--no-write-report",
                    ],
                    dependencies=harness.deps(),
                )
            self.assertTrue(rollback_path.is_file())
            execute_report = json.loads(execute_report_path.read_text(encoding="utf-8"))
            self.assertTrue(execute_report["commit_result"]["rollback_safe"])
            self.assertEqual(
                execute_report["commit_result"]["rollback_sql_path"],
                str(rollback_path),
            )
            self.assertEqual(len(execute_report["commit_result"]["rollback_artifact"]["sha256"]), 64)

        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertTrue(harness.conn.committed)
        self.assertIn("connect", harness.calls)
        self.assertIn("load_active_source_metadata", harness.calls)

    def test_execute_cli_persistence_failure_creates_no_execute_report(self) -> None:
        runner = load_execute_runner_module()
        harness = ExecuteHarness()
        with tempfile.TemporaryDirectory() as temp_dir:
            rollback_path = Path(temp_dir) / "rollback.sql"
            execute_report_path = Path(temp_dir) / "execute.json"
            with mock.patch.object(
                metrics_module,
                "persist_rollback_sql_atomic",
                side_effect=StockFinancialCanonicalBlocked("rollback_sql_persistence_failed: injected"),
            ):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    exit_code = runner.main(
                        [
                            "--source-trade-date",
                            "20260529",
                            "--execute",
                            "--user-confirmed",
                            "--postgres-commit-enabled",
                            "--source-bundle-cache-path",
                            "docs/mock-cache.json",
                            "--rollback-sql-path",
                            str(rollback_path),
                            "--json-report-path",
                            str(execute_report_path),
                            "--no-write-report",
                        ],
                        dependencies=harness.deps(),
                    )

            self.assertEqual(exit_code, 2)
            self.assertFalse(rollback_path.exists())
            self.assertFalse(execute_report_path.exists())
        self.assertFalse(harness.conn.committed)
        self.assertTrue(harness.conn.rolled_back)
        self.assertEqual(harness.conn.cursor_obj.executemany_calls, [])

    def test_execute_cli_missing_flag_blocks_before_cache_or_commit(self) -> None:
        runner = load_execute_runner_module()
        harness = ExecuteHarness()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exit_code = runner.main(
                [
                    "--source-trade-date",
                    "20260529",
                    "--execute",
                    "--user-confirmed",
                    "--source-bundle-cache-path",
                    "docs/mock-cache.json",
                    "--no-write-report",
                ],
                dependencies=harness.deps(),
            )

        self.assertNotEqual(exit_code, 0)
        self.assertNotIn("build_snapshot_from_cache", harness.calls)
        self.assertFalse(harness.conn.committed)

    def test_preflight_only_does_not_create_rollback_artifact(self) -> None:
        runner = load_execute_runner_module()
        harness = ExecuteHarness()
        with tempfile.TemporaryDirectory() as temp_dir:
            rollback_path = Path(temp_dir) / "rollback.sql"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exit_code = runner.main(
                    [
                        "--source-trade-date",
                        "20260529",
                        "--source-bundle-cache-path",
                        "docs/mock-cache.json",
                        "--rollback-sql-path",
                        str(rollback_path),
                        "--no-write-report",
                    ],
                    dependencies=harness.deps(),
                )

            self.assertEqual(exit_code, 0)
            self.assertFalse(rollback_path.exists())
        self.assertNotIn("load_active_source_metadata", harness.calls)
        self.assertNotIn("connect", harness.calls)

    def test_rollback_sql_is_scoped_to_v2_financial_batch(self) -> None:
        sql = ROLLBACK_PATH.read_text(encoding="utf-8")

        self.assertIn("stock_financial_canonical_20260529_v1", sql)
        self.assertIn("stock_financial_20260529_v2", sql)
        self.assertIn("stock_financial_20260529_v1", sql)
        self.assertIn("stock_financial_metrics_fact", sql)
        self.assertIn("data_type = 'stock_financial_canonical_metrics'", sql)
        self.assertNotIn("data_type = 'stock_financial';", sql)
        self.assertNotRegex(sql.lower(), r"(delete\s+from|update|insert\s+into|truncate\s+table|copy)\s+condition_")
        self.assertNotIn("common_event_outbox", sql)

    def test_rollback_sql_20260721_exactly_matches_verified_renderer(self) -> None:
        sql = ROLLBACK_20260721_PATH.read_text(encoding="utf-8")

        self.assertEqual(sql, render_rollback_sql(rollback_20260721_plan()))
        self.assertIn("v_target_row_count <> 5509", sql)
        self.assertIn("v_previous_identity_count <> 5509", sql)
        self.assertIn("v_quality_row_count <> 9", sql)
        self.assertIn("previous_source_version = NULL", sql)


if __name__ == "__main__":
    unittest.main()
