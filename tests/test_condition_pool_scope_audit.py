import unittest

from ashare_v3.condition.pool_scope_audit import (
    FIXED_INDEX_CODES,
    build_condition_pool_scope_audit_report,
)


class ConditionPoolScopeAuditTest(unittest.TestCase):
    def test_audit_flags_pool_universe_violations_but_accepts_scope_counts(self) -> None:
        report = build_condition_pool_scope_audit_report(
            run=sample_run(),
            pool={
                "index": {
                    "object_count": 80,
                    "row_count": 273,
                    "out_of_range_row_count": 247,
                    "out_of_range_object_count": 71,
                },
                "board": {
                    "object_count": 428,
                    "row_count": 1575,
                    "out_of_range_row_count": 1110,
                    "out_of_range_object_count": 301,
                },
                "stock": {
                    "object_count": 5501,
                    "row_count": 20246,
                    "out_of_range_row_count": 12808,
                    "out_of_range_object_count": 3434,
                },
            },
            scope={
                "index": {
                    "object_count": 9,
                    "direction_count": 2,
                    "row_count": 18,
                    "out_of_range_row_count": 0,
                    "expected_row_count_from_formula": 18,
                    "object_count_row_count_explanation": "9 index objects * 2 directions = 18 rows",
                },
                "board": {
                    "object_count": 127,
                    "direction_count": 2,
                    "row_count": 254,
                    "out_of_range_row_count": 0,
                    "expected_row_count_from_formula": 254,
                    "object_count_row_count_explanation": "127 board objects * 2 directions = 254 rows",
                },
                "stock": {
                    "object_count": 2067,
                    "direction_count": 2,
                    "row_count": 7438,
                    "market_value_violation_row_count": 0,
                    "pool_link_violation_row_count": 0,
                },
            },
        )

        self.assertEqual(report["quality"]["p0_count"], 3)
        self.assertTrue(report["needs_remediation"])
        self.assertEqual(report["remediation_plan"]["estimated_rows_to_exclude"]["index_condition_pool"], 247)
        self.assertIn("condition_pool-derived", report["object_count_vs_row_count_note"]["index_minute_target_scope"])

    def test_audit_passes_when_pool_and_scope_match_default_universe(self) -> None:
        report = build_condition_pool_scope_audit_report(
            run=sample_run(),
            pool={
                "index": {"object_count": len(FIXED_INDEX_CODES) - 1, "row_count": 24, "out_of_range_row_count": 0},
                "board": {"object_count": 127, "row_count": 465, "out_of_range_row_count": 0},
                "stock": {"object_count": 2067, "row_count": 7438, "out_of_range_row_count": 0},
            },
            scope={
                "index": {
                    "object_count": 9,
                    "direction_count": 2,
                    "row_count": 18,
                    "out_of_range_row_count": 0,
                    "expected_row_count_from_formula": 18,
                    "object_count_row_count_explanation": "9 index objects * 2 directions = 18 rows",
                },
                "board": {
                    "object_count": 127,
                    "direction_count": 2,
                    "row_count": 254,
                    "out_of_range_row_count": 0,
                    "expected_row_count_from_formula": 254,
                    "object_count_row_count_explanation": "127 board objects * 2 directions = 254 rows",
                },
                "stock": {
                    "object_count": 2067,
                    "direction_count": 2,
                    "row_count": 7438,
                    "market_value_violation_row_count": 0,
                    "pool_link_violation_row_count": 0,
                },
            },
        )

        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertFalse(report["needs_remediation"])
        self.assertFalse(report["will_execute_sql"])


def sample_run() -> dict[str, object]:
    return {
        "run_id": "condition_layer_20260522_to_20260525_test",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
    }


if __name__ == "__main__":
    unittest.main()
