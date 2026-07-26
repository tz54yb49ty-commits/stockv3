"""Opt-in isolated PostgreSQL 16 acceptance for migration 065A."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import unittest

from tests.test_n6_064_postgres_integration import (
    MINIMAL_SEED_SQL,
    SESSION_HASH,
    _Pg16Cluster,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_064 = ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql"
MIGRATION_065 = ROOT / "sql/065_n6_btrack_current_date_batch_scope_fix.sql"
MIGRATION_065A = (
    ROOT / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql"
)
MIGRATION_065B = (
    ROOT / "sql/065b_n6_btrack_confirmed_manual_buy_apply_scope_fix.sql"
)
ROLLBACK_065A = (
    ROOT
    / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix_rollback.sql"
)
ROLLBACK_065B = (
    ROOT
    / "sql/065b_n6_btrack_confirmed_manual_buy_apply_scope_fix_rollback.sql"
)
ENABLED = os.environ.get("ASHARE_V3_N6_065A_PG_INTEGRATION") == "1"


@unittest.skipUnless(
    ENABLED,
    "set ASHARE_V3_N6_065A_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6065APostgresIntegrationTest(unittest.TestCase):
    cluster: _Pg16Cluster
    database = "n6_065a"

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
            cls.cluster.apply_file(
                cls.database, MIGRATION_065, role="ashare_v3_user"
            )
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

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
                  'public.n6_executor_claim_proposal(bigint,text)'::regprocedure,
                  'public.n6_executor_claim_next_proposal(text)'::regprocedure
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

    def _create_expired_confirmed(self) -> int:
        with self.cluster.connect(self.database) as connection:
            connection.execute("SET ROLE n6_btrack_web")
            created = connection.execute(
                """
                SELECT public.n6_btrack_proposal_create(
                  %s, 'signal', 2
                ) AS result
                """,
                (SESSION_HASH,),
            ).fetchone()["result"]
            self.assertTrue(created["ok"], created)
            proposal_id = int(created["item"]["proposal_id"])
            token = created["item"]["confirmation_generation_token"]
            confirmed = connection.execute(
                """
                SELECT public.n6_btrack_proposal_confirm(
                  %s, %s, %s
                ) AS result
                """,
                (SESSION_HASH, proposal_id, f"n6v3:{token}:065a"),
            ).fetchone()["result"]
            self.assertTrue(confirmed["ok"], confirmed)
            connection.execute("RESET ROLE")
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                """
                UPDATE public.n6_virtual_trade_proposal
                SET created_at = pg_catalog.now() - interval '2 minutes',
                    expires_at = pg_catalog.now() - interval '1 minute'
                WHERE proposal_id=%s
                """,
                (proposal_id,),
            )
            connection.execute("SET session_replication_role=origin")
            connection.commit()
        return proposal_id

    def _claim_next(self, *, commit: bool) -> dict:
        with self.cluster.connect(self.database) as connection:
            connection.execute("SET ROLE n6_virtual_executor")
            result = connection.execute(
                """
                SELECT public.n6_executor_claim_next_proposal(
                  'n6-065a-integration'
                ) AS result
                """
            ).fetchone()["result"]
            if commit:
                connection.commit()
            else:
                connection.rollback()
        return dict(result)

    def _claim_and_apply(self) -> dict:
        with self.cluster.connect(self.database) as connection:
            connection.execute("SET ROLE n6_virtual_executor")
            claimed = connection.execute(
                """
                SELECT public.n6_executor_claim_next_proposal(
                  'n6-065b-integration'
                ) AS result
                """
            ).fetchone()["result"]
            self.assertTrue(claimed["ok"], claimed)
            applied = connection.execute(
                """
                SELECT public.n6_executor_apply_claimed_proposal(
                  %s, 'n6-065b-integration'
                ) AS result
                """,
                (claimed["proposal_id"],),
            ).fetchone()["result"]
            connection.rollback()
        return dict(applied)

    def test_065a_expired_manual_buy_claim_and_exact_rollback(self) -> None:
        proposal_id = self._create_expired_confirmed()
        before_fingerprint = self._fingerprint()
        self.assertEqual(
            self._claim_next(commit=False)["status"],
            "no_claimable_proposal",
        )

        self.cluster.apply_file(
            self.database, MIGRATION_065A, role="ashare_v3_user"
        )
        claimed = self._claim_next(commit=False)
        self.assertTrue(claimed["ok"], claimed)
        self.assertEqual(int(claimed["proposal_id"]), proposal_id)
        self.assertEqual(claimed["status"], "processing")

        with self.cluster.connect(self.database) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                """
                UPDATE public.n6_virtual_trade_proposal
                SET source_lineage_json = pg_catalog.jsonb_set(
                      source_lineage_json,
                      '{for_trade_date}',
                      '"20260719"'::jsonb
                    )
                WHERE proposal_id=%s
                """,
                (proposal_id,),
            )
            connection.execute("SET session_replication_role=origin")
            connection.commit()
        self.assertEqual(
            self._claim_next(commit=False)["status"],
            "no_claimable_proposal",
        )

        with self.cluster.connect(self.database) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                """
                UPDATE public.n6_virtual_trade_proposal
                SET source_lineage_json = pg_catalog.jsonb_set(
                      source_lineage_json,
                      '{for_trade_date}',
                      '"20260720"'::jsonb
                    )
                WHERE proposal_id=%s
                """,
                (proposal_id,),
            )
            connection.execute("SET session_replication_role=origin")
            connection.commit()

        self.cluster.apply_file(
            self.database, MIGRATION_065B, role="ashare_v3_user"
        )
        applied = self._claim_and_apply()
        self.assertTrue(applied["ok"], applied)
        self.assertEqual(applied["status"], "executed")
        self.cluster.apply_file(
            self.database, ROLLBACK_065B, role="ashare_v3_user"
        )

        self.cluster.apply_file(
            self.database, ROLLBACK_065A, role="ashare_v3_user"
        )
        self.assertEqual(self._fingerprint(), before_fingerprint)
        self.assertEqual(
            self._claim_next(commit=False)["status"],
            "no_claimable_proposal",
        )


if __name__ == "__main__":
    unittest.main()
