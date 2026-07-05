import unittest

from ashare_v3.condition.migration_review import (
    format_review_markdown,
    review_migration_sql,
)


class ConditionMigrationReviewTest(unittest.TestCase):
    def test_review_accepts_additive_nullable_columns(self) -> None:
        sql = """
        -- DROP COLUMN only in comments should not count.
        BEGIN;
        ALTER TABLE stock_condition_pool
          ADD COLUMN IF NOT EXISTS policy_name TEXT,
          ADD COLUMN IF NOT EXISTS selected_reason TEXT[];
        COMMIT;
        """

        review = review_migration_sql(sql)

        self.assertTrue(review.additive_only)
        self.assertTrue(review.nullable_only)
        self.assertTrue(review.no_drop)
        self.assertTrue(review.no_backfill)
        self.assertEqual(review.add_column_count, 2)
        self.assertEqual(review.disallowed_hits, ())

    def test_review_rejects_backfill_and_constraints(self) -> None:
        sql = """
        BEGIN;
        ALTER TABLE stock_condition_pool
          ADD COLUMN IF NOT EXISTS policy_name TEXT NOT NULL DEFAULT 'x';
        UPDATE stock_condition_pool SET policy_name = 'x';
        COMMIT;
        """

        review = review_migration_sql(sql)

        self.assertFalse(review.additive_only)
        self.assertFalse(review.nullable_only)
        self.assertFalse(review.no_backfill)
        self.assertFalse(review.no_not_null)
        self.assertIn(r"\bUPDATE\b", review.disallowed_hits)
        self.assertIn(r"\bNOT\s+NULL\b", review.disallowed_hits)

    def test_markdown_report_contains_required_review_fields(self) -> None:
        class FakeSqlReview:
            def to_dict(self):
                return {
                    "additive_only": True,
                    "nullable_only": True,
                    "no_drop": True,
                    "no_backfill": True,
                    "no_not_null": True,
                    "no_check_or_fk": True,
                    "statement_count": 3,
                    "add_column_count": 1,
                    "disallowed_hits": [],
                }

        class FakeReport:
            def to_dict(self):
                return {
                    "migration_safe_to_apply": True,
                    "additive_only": True,
                    "affects_existing_rows": "existing rows keep their data",
                    "requires_backup": True,
                    "rollback_manual_only": True,
                    "user_confirmation_required": True,
                    "gap_summary": {
                        "missing_tables": [],
                        "missing_column_count": 1,
                        "type_mismatch_count": 0,
                        "not_null_risk_count": 1,
                        "constraint_deferred_count": 0,
                        "missing_columns_by_table": {"stock_condition_pool": ["policy_name"]},
                    },
                    "sql_review": FakeSqlReview().to_dict(),
                    "nullable_compatibility": {
                        "execute_py": {"status": "compatible", "reason": "row.get"},
                        "basis_py": {"status": "compatible", "reason": "nullable"},
                        "pool_py": {"status": "compatible", "reason": "policy generated"},
                        "old_active_run": {"status": "compatible", "reason": "NULL accepted"},
                    },
                }

        markdown = format_review_markdown(FakeReport())  # type: ignore[arg-type]

        self.assertIn("migration_safe_to_apply: true", markdown)
        self.assertIn("rollback_manual_only: true", markdown)
        self.assertIn("user_confirmation_required: true", markdown)
        self.assertIn("stock_condition_pool: policy_name", markdown)


if __name__ == "__main__":
    unittest.main()
