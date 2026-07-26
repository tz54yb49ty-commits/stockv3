from pathlib import Path
import re
import unittest

from tests.test_n6_strategy_worker_canonical_acl_079 import (
    _temporary_postgres,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/080_n6_strategy_membership_asof_constraint.sql"
ROLLBACK = (
    ROOT / "sql/080_n6_strategy_membership_asof_constraint_rollback.sql"
)


CREATE_TEST_TABLE_SQL = """
CREATE TABLE public.n6_strategy_match_projection (
  strategy_match_projection_id bigint PRIMARY KEY,
  trade_date date NOT NULL,
  membership_source_trade_date date NOT NULL,
  action_state text NOT NULL,
  CONSTRAINT n6_strategy_match_projection_action_state_check
    CHECK (action_state IN ('eligible', 'executed')),
  CONSTRAINT n6_strategy_match_projection_check
    CHECK (membership_source_trade_date = trade_date)
);
"""


class N6StrategyMembershipAsofConstraint080Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_forward_and_rollback_are_atomic_and_fail_closed(self) -> None:
        for sql in (self.migration, self.rollback):
            self.assertRegex(sql, r"^--.*\n(?:--.*\n)*\nBEGIN;")
            self.assertIn("SET LOCAL lock_timeout = '5s';", sql)
            self.assertIn("SET LOCAL statement_timeout = '30s';", sql)
            self.assertIn("pg_advisory_xact_lock", sql)
            self.assertIn("CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'", sql)
            self.assertIn("SESSION_USER IS DISTINCT FROM 'ashare_v3_user'", sql)
            self.assertIn(".relkind <> 'r'", sql)
            self.assertIn(".owner_name <> 'ashare_v3_user'", sql)
            self.assertIn("attribute.attnotnull", sql)
            self.assertIn("'pg_catalog.date'::pg_catalog.regtype", sql)
            self.assertTrue(sql.rstrip().endswith("COMMIT;"))

    def test_only_the_target_constraint_is_replaced(self) -> None:
        for sql in (self.migration, self.rollback):
            altered = re.findall(
                r"ALTER TABLE\s+([^\s]+)\s+\n?\s*(?:DROP|ADD)",
                sql,
                re.IGNORECASE,
            )
            self.assertEqual(
                altered,
                [
                    "public.n6_strategy_match_projection",
                    "public.n6_strategy_match_projection",
                ],
            )
            self.assertEqual(
                sql.count("DROP CONSTRAINT n6_strategy_match_projection_check"),
                1,
            )
            self.assertEqual(
                sql.count("ADD CONSTRAINT n6_strategy_match_projection_check"),
                1,
            )

    def test_forward_accepts_asof_but_rejects_future_membership(self) -> None:
        self.assertIn("membership_source_trade_date IS NOT NULL", self.migration)
        self.assertIn("membership_source_trade_date <= trade_date", self.migration)
        self.assertNotIn(
            "CHECK (membership_source_trade_date = trade_date);",
            self.migration,
        )

    def test_rollback_restores_equality_without_rewriting_rows(self) -> None:
        self.assertIn(
            "080 rollback incompatible as-of rows present", self.rollback
        )
        self.assertIn(
            "CHECK (membership_source_trade_date = trade_date);",
            self.rollback,
        )
        for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE"):
            self.assertNotIn(forbidden, self.migration.upper())
            self.assertNotIn(forbidden, self.rollback.upper())


class N6StrategyMembershipAsofConstraint080PostgresTest(unittest.TestCase):
    @staticmethod
    def _constraint_definition(postgres) -> str:
        return postgres.scalar(
            """
            SELECT pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
            FROM pg_catalog.pg_constraint constraint_row
            WHERE constraint_row.conrelid =
                  'public.n6_strategy_match_projection'::regclass
              AND constraint_row.conname =
                  'n6_strategy_match_projection_check';
            """
        )

    @staticmethod
    def _other_constraint_definition(postgres) -> str:
        return postgres.scalar(
            """
            SELECT pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
            FROM pg_catalog.pg_constraint constraint_row
            WHERE constraint_row.conrelid =
                  'public.n6_strategy_match_projection'::regclass
              AND constraint_row.conname =
                  'n6_strategy_match_projection_action_state_check';
            """
        )

    @staticmethod
    def _other_constraints(postgres) -> str:
        return postgres.scalar(
            """
            SELECT pg_catalog.string_agg(
                     constraint_row.conname || ':' ||
                     constraint_row.contype::text || ':' ||
                     pg_catalog.pg_get_constraintdef(
                       constraint_row.oid, true
                     ),
                     E'\\n' ORDER BY constraint_row.conname
                   )
            FROM pg_catalog.pg_constraint constraint_row
            WHERE constraint_row.conrelid =
                  'public.n6_strategy_match_projection'::regclass
              AND constraint_row.conname <>
                  'n6_strategy_match_projection_check';
            """
        )

    def test_old_constraint_reproduces_asof_failure(self) -> None:
        with _temporary_postgres() as postgres:
            postgres.sql(CREATE_TEST_TABLE_SQL)
            result = postgres.sql(
                """
                INSERT INTO n6_strategy_match_projection VALUES
                  (1, DATE '2026-07-22', DATE '2026-07-21', 'executed');
                """,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("n6_strategy_match_projection_check", result.stderr)
            self.assertEqual(
                self._constraint_definition(postgres),
                "CHECK (membership_source_trade_date = trade_date)",
            )

    def test_forward_accepts_asof_and_same_day_but_rejects_future(self) -> None:
        with _temporary_postgres() as postgres:
            postgres.sql(CREATE_TEST_TABLE_SQL)
            other_before = self._other_constraint_definition(postgres)
            all_other_before = self._other_constraints(postgres)
            postgres.file(MIGRATION)
            self.assertEqual(
                self._constraint_definition(postgres),
                "CHECK (membership_source_trade_date IS NOT NULL AND membership_source_trade_date <= trade_date)",
            )
            postgres.sql(
                """
                INSERT INTO n6_strategy_match_projection VALUES
                  (1, DATE '2026-07-22', DATE '2026-07-21', 'executed'),
                  (2, DATE '2026-07-22', DATE '2026-07-22', 'eligible');
                """
            )
            future = postgres.sql(
                """
                INSERT INTO n6_strategy_match_projection VALUES
                  (3, DATE '2026-07-22', DATE '2026-07-23', 'executed');
                """,
                check=False,
            )
            self.assertNotEqual(future.returncode, 0)
            self.assertIn("n6_strategy_match_projection_check", future.stderr)
            invalid_state = postgres.sql(
                """
                INSERT INTO n6_strategy_match_projection VALUES
                  (4, DATE '2026-07-22', DATE '2026-07-22', 'blocked');
                """,
                check=False,
            )
            self.assertNotEqual(invalid_state.returncode, 0)
            self.assertIn(
                "n6_strategy_match_projection_action_state_check",
                invalid_state.stderr,
            )
            self.assertEqual(
                self._other_constraint_definition(postgres), other_before
            )
            self.assertEqual(
                self._other_constraints(postgres), all_other_before
            )

    def test_rollback_restores_equality_for_compatible_rows(self) -> None:
        with _temporary_postgres() as postgres:
            postgres.sql(CREATE_TEST_TABLE_SQL)
            postgres.file(MIGRATION)
            postgres.sql(
                """
                INSERT INTO n6_strategy_match_projection VALUES
                  (1, DATE '2026-07-22', DATE '2026-07-22', 'executed');
                """
            )
            postgres.file(ROLLBACK)
            self.assertEqual(
                self._constraint_definition(postgres),
                "CHECK (membership_source_trade_date = trade_date)",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT count(*) FROM n6_strategy_match_projection;"
                ),
                "1",
            )

    def test_rollback_rejects_historical_asof_rows_without_partial_change(self) -> None:
        with _temporary_postgres() as postgres:
            postgres.sql(CREATE_TEST_TABLE_SQL)
            postgres.file(MIGRATION)
            postgres.sql(
                """
                INSERT INTO n6_strategy_match_projection VALUES
                  (1, DATE '2026-07-22', DATE '2026-07-21', 'executed');
                """
            )
            result = postgres.file(ROLLBACK, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "080 rollback incompatible as-of rows present", result.stderr
            )
            self.assertEqual(
                self._constraint_definition(postgres),
                "CHECK (membership_source_trade_date IS NOT NULL AND membership_source_trade_date <= trade_date)",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT count(*) FROM n6_strategy_match_projection;"
                ),
                "1",
            )


if __name__ == "__main__":
    unittest.main()
