"""Opt-in isolated PostgreSQL 16 acceptance for N6 migration 066."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql",
    ROOT / "sql/065_n6_btrack_current_date_batch_scope_fix.sql",
    ROOT / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql",
    ROOT / "sql/065b_n6_btrack_confirmed_manual_buy_apply_scope_fix.sql",
)
FORWARD = ROOT / "sql/066_n6_btrack_regular_session_manual_buy.sql"
ROLLBACK = (
    ROOT / "sql/066_n6_btrack_regular_session_manual_buy_rollback.sql"
)
ENABLED = os.environ.get("ASHARE_V3_N6_066_PG_INTEGRATION") == "1"

_SPEC = importlib.util.spec_from_file_location(
    "n6_064_pg_fixture",
    ROOT / "tests/test_n6_064_postgres_integration.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise AssertionError("cannot load isolated PostgreSQL fixture")
_FIXTURE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FIXTURE)

SIGNATURES = (
    "public.n6_btrack_proposal_create(text,text,bigint)",
    "public.n6_btrack_proposal_confirm(text,bigint,text)",
    "public.n6_executor_claim_proposal(bigint,text)",
    "public.n6_executor_claim_next_proposal(text)",
    "public.n6_executor_apply_claimed_proposal(bigint,text)",
)
BUSINESS_TABLES = (
    "n6_virtual_trade_proposal",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_cash_ledger",
    "n6_virtual_cash_snapshot",
    "n6_virtual_position",
    "n6_virtual_position_lot",
)


@unittest.skipUnless(
    ENABLED,
    "set ASHARE_V3_N6_066_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6066PostgresIntegrationTest(unittest.TestCase):
    database = "n6_066"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.cluster = _FIXTURE._Pg16Cluster()
        try:
            cls.cluster.start()
            cls.cluster.create_database(cls.database)
            cls.cluster.restore_schema(cls.database)
            cls.cluster.apply_file(
                cls.database, MIGRATIONS[0], role="ashare_v3_user"
            )
            cls.cluster.run_sql(
                cls.database,
                _FIXTURE.MINIMAL_SEED_SQL,
                label="n6_066_seed",
            )
            for migration in MIGRATIONS[1:]:
                cls.cluster.apply_file(
                    cls.database, migration, role="ashare_v3_user"
                )
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def _function_hashes(self) -> dict[str, str]:
        with self.cluster.connect(self.database) as connection:
            return {
                signature: hashlib.sha256(
                    connection.execute(
                        """
                        SELECT prosrc
                        FROM pg_catalog.pg_proc
                        WHERE oid=%s::regprocedure
                        """,
                        (signature,),
                    ).fetchone()["prosrc"].encode("utf-8")
                ).hexdigest()
                for signature in SIGNATURES
            }

    def _business_counts(self) -> dict[str, int]:
        with self.cluster.connect(self.database) as connection:
            return {
                table: connection.execute(
                    f"SELECT count(*) AS row_count FROM public.{table}"
                ).fetchone()["row_count"]
                for table in BUSINESS_TABLES
            }

    def test_exact_forward_boundaries_and_rollback(self) -> None:
        from psycopg import sql

        baseline_hashes = self._function_hashes()
        baseline_counts = self._business_counts()
        self.cluster.apply_file(
            self.database, FORWARD, role="ashare_v3_user"
        )
        self.assertEqual(self._business_counts(), baseline_counts)

        with self.cluster.connect(self.database) as connection:
            helper_source = connection.execute(
                """
                SELECT prosrc
                FROM pg_catalog.pg_proc
                WHERE oid =
                  'public.n6_btrack_regular_trade_session_open()'
                  ::regprocedure
                """
            ).fetchone()["prosrc"]
            apply_source = connection.execute(
                """
                SELECT prosrc
                FROM pg_catalog.pg_proc
                WHERE oid =
                  'public.n6_executor_apply_claimed_proposal(bigint,text)'
                  ::regprocedure
                """
            ).fetchone()["prosrc"]
            self.assertNotIn(
                "same_day_last_quote_current_price", apply_source
            )
            self.assertNotIn(
                "fill_price_source := 'signal_reference_price'",
                apply_source,
            )
            self.assertIn("n6_066_fresh_quote_fill_v1", apply_source)

            connection.execute(
                """
                CREATE OR REPLACE FUNCTION public.n6_066_test_now()
                RETURNS timestamptz
                LANGUAGE sql
                STABLE
                SET search_path=pg_catalog
                AS $clock$
                  SELECT pg_catalog.current_setting(
                    'n6.test_clock', false
                  )::timestamptz
                $clock$
                """
            )
            shim_source = helper_source.replace(
                "pg_catalog.clock_timestamp()",
                "public.n6_066_test_now()",
            )
            connection.execute(
                sql.SQL(
                    """
                CREATE OR REPLACE FUNCTION
                  public.n6_btrack_regular_trade_session_open()
                RETURNS boolean
                LANGUAGE sql
                VOLATILE
                SECURITY DEFINER
                SET search_path=pg_catalog
                AS {}
                """
                ).format(sql.Literal(shim_source))
            )
            cases = {
                "2026-07-20 09:29:00+08": False,
                "2026-07-20 09:30:00+08": True,
                "2026-07-20 11:30:00+08": True,
                "2026-07-20 11:31:00+08": False,
                "2026-07-20 12:59:00+08": False,
                "2026-07-20 13:00:00+08": True,
                "2026-07-20 15:00:00+08": True,
                "2026-07-20 15:01:00+08": False,
                "2026-07-20 23:59:00+08": False,
            }
            for clock, expected in cases.items():
                connection.execute(
                    "SELECT pg_catalog.set_config("
                    "'n6.test_clock', %s, false)",
                    (clock,),
                )
                actual = connection.execute(
                    "SELECT public."
                    "n6_btrack_regular_trade_session_open() AS open"
                ).fetchone()["open"]
                self.assertIs(actual, expected, clock)

            connection.execute(
                sql.SQL(
                    """
                CREATE OR REPLACE FUNCTION
                  public.n6_btrack_regular_trade_session_open()
                RETURNS boolean
                LANGUAGE sql
                VOLATILE
                SECURITY DEFINER
                SET search_path=pg_catalog
                AS {}
                """
                ).format(sql.Literal(helper_source))
            )
            connection.execute(
                "DROP FUNCTION public.n6_066_test_now()"
            )

        self.cluster.apply_file(
            self.database, ROLLBACK, role="ashare_v3_user"
        )
        self.assertEqual(self._function_hashes(), baseline_hashes)
        self.assertEqual(self._business_counts(), baseline_counts)


if __name__ == "__main__":
    unittest.main()
