import unittest
from datetime import datetime

from scripts.check_condition_source_ready import (
    REQUIRED_DATA_TYPES,
    evaluate_stock_financial_canonical_readiness,
    evaluate_stock_condition_universe,
    is_canonical_stock_financial_source_version,
    run_check,
)


def gap_manifest(count: int) -> dict:
    return {
        "quality_gate_found": count > 0,
        "manifest_count": count,
        "excluded_from_condition_universe": count,
        "valid_exclusion_actions": count > 0,
    }


class ConditionSourceReadyPolicyTests(unittest.TestCase):
    def test_stock_financial_v1_is_not_canonical_for_daily_n2_readiness(self) -> None:
        self.assertFalse(is_canonical_stock_financial_source_version("stock_financial_20260612_v1", "20260612"))
        self.assertTrue(is_canonical_stock_financial_source_version("stock_financial_20260612_v2", "20260612"))
        self.assertTrue(is_canonical_stock_financial_source_version("stock_financial_20260612_v10", "20260612"))

    def test_stock_financial_canonical_readiness_blocks_empty_canonical_fields(self) -> None:
        result = evaluate_stock_financial_canonical_readiness(
            active_source_version="stock_financial_20260612_v2",
            source_trade_date="20260612",
            row_count=5514,
            missing_columns=[],
            financial_metric_version_present_count=5514,
            canonical_content_present_count=0,
            canonical_all_empty_count=5514,
        )

        self.assertFalse(result["passed"])
        self.assertIn("canonical_financial_fields_all_empty", result["failure_reasons"])

    def test_stock_financial_canonical_readiness_allows_warning_only_special_rows(self) -> None:
        result = evaluate_stock_financial_canonical_readiness(
            active_source_version="stock_financial_20260612_v2",
            source_trade_date="20260612",
            row_count=5514,
            missing_columns=[],
            financial_metric_version_present_count=5514,
            canonical_content_present_count=5514,
            canonical_all_empty_count=0,
        )

        self.assertTrue(result["passed"])

    def test_old_full_match_case_passes_without_manifest(self) -> None:
        result = evaluate_stock_condition_universe(
            stock_daily_count=5504,
            stock_daily_basic_count=5504,
            stock_financial_count=5504,
            gap_manifest=gap_manifest(0),
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["expected_condition_stock_universe"], 5504)
        self.assertEqual(result["excluded_from_condition_universe"], 0)

    def test_v2_gap_manifest_allows_daily_to_exceed_condition_universe(self) -> None:
        result = evaluate_stock_condition_universe(
            stock_daily_count=5520,
            stock_daily_basic_count=5504,
            stock_financial_count=5504,
            gap_manifest=gap_manifest(16),
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["expected_condition_stock_universe"], 5504)
        self.assertEqual(result["excluded_from_condition_universe"], 16)

    def test_daily_to_condition_universe_gap_without_manifest_blocks(self) -> None:
        result = evaluate_stock_condition_universe(
            stock_daily_count=5520,
            stock_daily_basic_count=5504,
            stock_financial_count=5504,
            gap_manifest=gap_manifest(0),
        )

        self.assertFalse(result["passed"])
        self.assertIn("condition stock universe gap is not covered by condition_source_gap_manifest", result["failure_reasons"])

    def test_stock_daily_basic_and_financial_mismatch_blocks(self) -> None:
        result = evaluate_stock_condition_universe(
            stock_daily_count=5520,
            stock_daily_basic_count=5504,
            stock_financial_count=5503,
            gap_manifest=gap_manifest(17),
        )

        self.assertFalse(result["passed"])
        self.assertIn("stock_daily_basic row_count does not match stock_financial row_count", result["failure_reasons"])


class FakeCursor:
    def __init__(
        self,
        *,
        active_rows: list[tuple],
        fact_counts: dict[str, tuple[int, int]],
        manifest_count: int = 0,
        view_exists: bool = True,
        canonical_columns_missing: list[str] | None = None,
        canonical_content_counts: tuple[int, int, int] | None = None,
    ) -> None:
        self.active_rows = active_rows
        self.fact_counts = fact_counts
        self.manifest_count = manifest_count
        self.view_exists = view_exists
        self.canonical_columns_missing = set(canonical_columns_missing or [])
        self.canonical_content_counts = canonical_content_counts
        self.result: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params=None) -> None:
        if "to_regclass" in sql:
            self.result = [(
                "common_condition_active_source_version_view" if self.view_exists else None,
                "common_active_source_version",
            )]
            return
        if "FROM common_condition_active_source_version_view" in sql or "FROM common_active_source_version" in sql:
            self.result = self.active_rows
            return
        if "FROM common_quality_gate_result" in sql:
            manifest = [
                {"identity_key": f"stock:SH:{600000 + index:06d}", "action": "exclude_from_condition_universe"}
                for index in range(self.manifest_count)
            ]
            self.result = [("condition_source_gap_manifest", "warning", str(self.manifest_count), {"manifest": manifest})] if self.manifest_count else []
            return
        if "FROM information_schema.columns" in sql:
            requested = list((params or [[]])[0])
            self.result = [(column,) for column in requested if column not in self.canonical_columns_missing]
            return
        if "financial_metric_version" in sql and "canonical_content_present_count" not in sql:
            row_count = self.fact_counts.get("stock_financial_metrics_fact", (0, 0))[0]
            self.result = [self.canonical_content_counts or (row_count, row_count, 0)]
            return
        for table_name, counts in self.fact_counts.items():
            if f"FROM {table_name}" in sql:
                self.result = [counts]
                return
        self.result = [(0, 0)]

    def fetchone(self):
        return self.result[0]

    def fetchall(self):
        return self.result


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


def active_rows_without(*missing: str) -> list[tuple]:
    rows = []
    now = datetime(2026, 5, 27, 9, 2, 28)
    source_versions = {
        "stock_daily": "stock_daily_20260526_v2",
        "stock_daily_basic": "stock_daily_basic_20260526_v2",
        "stock_financial": "stock_financial_20260526_v2",
        "index_daily": "index_daily_20260526_v2",
        "index_membership": "index_membership_20260526_v2",
        "board_daily": "board_daily_20260526_v2",
        "board_membership": "board_membership_20260526_v2",
    }
    domains = {
        "stock_daily": "stock",
        "stock_daily_basic": "stock",
        "stock_financial": "stock",
        "index_daily": "index",
        "index_membership": "index",
        "board_daily": "board",
        "board_membership": "board",
    }
    for data_type in REQUIRED_DATA_TYPES:
        if data_type in missing:
            continue
        rows.append(("20260526", domains[data_type], data_type, source_versions[data_type], "batch", now, "test"))
    return rows


def windows_active_rows() -> list[tuple]:
    now = datetime(2026, 8, 27, 16, 40)
    source_data_types = {
        "stock_daily": "stock_daily_bar_fact",
        "stock_daily_basic": "stock_daily_basic",
        "stock_financial": "stock_financial_metrics_fact",
        "index_daily": "index_daily_bar_fact",
        "index_membership": "index_membership_fact",
        "board_daily": "board_daily_bar_fact",
        "board_membership": "board_membership_fact",
    }
    return [
        (
            "20260526",
            "stock" if data_type.startswith("stock") else "index" if data_type.startswith("index") else "board",
            source_data_types[data_type],
            "windows_n1_20260526_20260526_v1",
            "batch",
            now,
            "windows_n1",
        )
        for data_type in REQUIRED_DATA_TYPES
    ]


def fact_counts(**overrides: tuple[int, int]) -> dict[str, tuple[int, int]]:
    counts = {
        "stock_daily_bar_fact": (5520, 0),
        "stock_daily_basic": (5504, 0),
        "stock_financial_metrics_fact": (5504, 0),
        "index_daily_bar_fact": (9, 0),
        "index_membership_fact": (12841, 0),
        "board_daily_bar_fact": (428, 0),
        "board_membership_fact": (56872, 0),
    }
    counts.update(overrides)
    return counts


class ConditionSourceReadyRunCheckTests(unittest.TestCase):
    def run_with_fake_db(self, cursor: FakeCursor) -> dict:
        from scripts import check_condition_source_ready

        original_connect = check_condition_source_ready.psycopg.connect
        check_condition_source_ready.psycopg.connect = lambda *args, **kwargs: FakeConnection(cursor)
        try:
            return run_check("postgresql://fake", "20260526")
        finally:
            check_condition_source_ready.psycopg.connect = original_connect

    def test_20260526_v2_readiness_passes_with_manifest_gap(self) -> None:
        result = self.run_with_fake_db(
            FakeCursor(active_rows=active_rows_without(), fact_counts=fact_counts(), manifest_count=16)
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["expected_condition_stock_universe"], 5504)
        self.assertEqual(result["excluded_from_condition_universe"], 16)

    def test_manifest_gap_absent_blocks(self) -> None:
        result = self.run_with_fake_db(
            FakeCursor(active_rows=active_rows_without(), fact_counts=fact_counts(), manifest_count=0)
        )

        self.assertFalse(result["passed"])
        self.assertIn("condition stock universe gap is not covered by condition_source_gap_manifest", json_failure_reasons(result))

    def test_missing_active_source_version_blocks(self) -> None:
        result = self.run_with_fake_db(
            FakeCursor(active_rows=active_rows_without("stock_financial"), fact_counts=fact_counts(), manifest_count=16)
        )

        self.assertFalse(result["passed"])
        self.assertIn("stock_financial", result["missing_data_types"])

    def test_missing_fact_rows_block(self) -> None:
        result = self.run_with_fake_db(
            FakeCursor(
                active_rows=active_rows_without(),
                fact_counts=fact_counts(stock_financial_metrics_fact=(0, 0)),
                manifest_count=16,
            )
        )

        self.assertFalse(result["passed"])
        self.assertIn("fact row_count is 0", json_failure_reasons(result))

    def test_windows_n1_registry_aliases_allow_full_history_latest_k_mode(self) -> None:
        result = self.run_with_fake_db(
            FakeCursor(
                active_rows=windows_active_rows(),
                fact_counts=fact_counts(),
                manifest_count=0,
                view_exists=False,
                canonical_columns_missing=["financial_metric_version"],
            )
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["active_source_registry"], "common_active_source_version")
        self.assertTrue(result["windows_n1_compatibility"])
        self.assertEqual(result["stock_condition_universe"]["mode"], "full_history_latest_k")
        self.assertEqual(result["excluded_from_condition_universe"], 0)


def json_failure_reasons(result: dict) -> list[str]:
    reasons: list[str] = []
    for item in result.get("checks") or []:
        reasons.extend(item.get("failure_reasons") or [])
    return reasons


if __name__ == "__main__":
    unittest.main()
