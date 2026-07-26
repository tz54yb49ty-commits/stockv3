"""Opt-in isolated PostgreSQL 16 acceptance for migration 065."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import unittest

from tests.test_n6_064_postgres_integration import (
    MINIMAL_SEED_SQL,
    _Pg16Cluster,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_064 = ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql"
MIGRATION_065 = ROOT / "sql/065_n6_btrack_current_date_batch_scope_fix.sql"
ROLLBACK_065 = (
    ROOT / "sql/065_n6_btrack_current_date_batch_scope_fix_rollback.sql"
)
ENABLED = os.environ.get("ASHARE_V3_N6_065_PG_INTEGRATION") == "1"


@unittest.skipUnless(
    ENABLED,
    "set ASHARE_V3_N6_065_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6065PostgresIntegrationTest(unittest.TestCase):
    cluster: _Pg16Cluster
    database = "n6_065"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.cluster = _Pg16Cluster()
        cls.cluster.start()
        try:
            cls.cluster.create_database(cls.database)
            cls.cluster.restore_schema(cls.database)
            cls.cluster.apply_file(
                cls.database, MIGRATION_064, role="ashare_v3_user"
            )
            cls.cluster.run_sql(
                cls.database, MINIMAL_SEED_SQL, label="minimal_seed"
            )
            cls.cluster.run_sql(
                cls.database,
                """
                BEGIN;
                SET LOCAL session_replication_role = replica;
                INSERT INTO public.stock_condition_display_basis (
                  stock_condition_display_basis_id, run_id, for_trade_date,
                  source_trade_date, prev_trade_date, stock_identity_key,
                  code, exchange, name, display_policy_hash,
                  primary_source_condition_basis_id, source_version,
                  display_status, quality_status
                ) OVERRIDING SYSTEM VALUE VALUES (
                  3, 'fixture-next-condition-run', '20260721', '20260720',
                  '20260720', 'stock:SH:600000', '600000', 'SH',
                  'Fixture Stock', 'fixture-next-display-hash', 999998,
                  'fixture-v1', 'visible', 'passed'
                );
                COMMIT;
                """,
                label="next_day_batch",
            )
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def _scope(self) -> bool:
        with self.cluster.connect(self.database) as connection:
            return bool(
                connection.execute(
                    """
                    SELECT public.n6_btrack_manual_signal_buy_current_scope(
                      2, 'admin', 2, 2, 2, 'stock:SH:600000',
                      'trigger_price', 10.00, '20260720'
                    ) AS result
                    """
                ).fetchone()["result"]
            )

    def _fingerprint(self) -> str:
        with self.cluster.connect(self.database) as connection:
            rows = connection.execute(
                """
                SELECT proc.oid::regprocedure::text AS signature,
                       owner.rolname AS owner_name,
                       proc.prosecdef,
                       proc.proconfig,
                       proc.proacl,
                       pg_catalog.encode(
                         pg_catalog.sha256(
                           pg_catalog.convert_to(proc.prosrc, 'UTF8')
                         ),
                         'hex'
                       ) AS source_sha
                FROM pg_catalog.pg_proc proc
                JOIN pg_catalog.pg_roles owner
                  ON owner.oid = proc.proowner
                WHERE proc.oid IN (
                  'public.n6_btrack_manual_signal_buy_current_scope(bigint,text,bigint,bigint,bigint,text,text,numeric,text)'::regprocedure,
                  'public.n6_executor_apply_claimed_proposal(bigint,text)'::regprocedure
                )
                ORDER BY signature
                """
            ).fetchall()
        encoded = json.dumps(
            [dict(row) for row in rows],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _business_counts(self) -> tuple[int, ...]:
        with self.cluster.connect(self.database) as connection:
            row = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM public.n6_virtual_trade_proposal),
                  (SELECT count(*) FROM public.n6_virtual_order),
                  (SELECT count(*) FROM public.n6_virtual_trade),
                  (SELECT count(*) FROM public.n6_virtual_cash_ledger),
                  (SELECT count(*) FROM public.n6_virtual_position),
                  (SELECT count(*) FROM public.n6_virtual_position_lot),
                  (SELECT count(*) FROM public.n6_virtual_position_event)
                """
            ).fetchone()
        return tuple(int(value) for value in row.values())

    def test_065_current_date_scope_and_exact_rollback(self) -> None:
        self.assertFalse(self._scope())
        before_fingerprint = self._fingerprint()
        before_counts = self._business_counts()

        self.cluster.apply_file(
            self.database, MIGRATION_065, role="ashare_v3_user"
        )
        self.assertTrue(self._scope())
        self.assertEqual(self._business_counts(), before_counts)
        with self.cluster.connect(self.database) as connection:
            hashes = connection.execute(
                """
                SELECT proc.oid::regprocedure::text AS signature,
                       pg_catalog.encode(
                         pg_catalog.sha256(
                           pg_catalog.convert_to(proc.prosrc, 'UTF8')
                         ),
                         'hex'
                       ) AS source_sha
                FROM pg_catalog.pg_proc proc
                WHERE proc.oid IN (
                  'public.n6_btrack_manual_signal_buy_current_scope(bigint,text,bigint,bigint,bigint,text,text,numeric,text)'::regprocedure,
                  'public.n6_executor_apply_claimed_proposal(bigint,text)'::regprocedure
                )
                ORDER BY signature
                """
            ).fetchall()
        self.assertEqual(
            {row["source_sha"] for row in hashes},
            {
                "a12ae3e8e8040ecb7459d08c69d263feb578b10b86d150fdb11488f6b7779d49",
                "2229ac23d823d0f27a08ba7aae18ca682594bfc27515b7a3b10b2a5673023a17",
            },
        )

        self.cluster.apply_file(
            self.database, ROLLBACK_065, role="ashare_v3_user"
        )
        self.assertFalse(self._scope())
        self.assertEqual(self._fingerprint(), before_fingerprint)
        self.assertEqual(self._business_counts(), before_counts)


if __name__ == "__main__":
    unittest.main()
