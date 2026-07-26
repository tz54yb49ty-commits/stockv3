"""Contract and isolated PG16 acceptance for N6 migration 075."""

from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD_PATH = ROOT / "sql/075_n6_executor_quote_ready_claim.sql"
ROLLBACK_PATH = ROOT / "sql/075_n6_executor_quote_ready_claim_rollback.sql"
CONTRACT_PATH = (
    ROOT / "docs/N6_QUOTE_COMPAT_AND_EXECUTOR_READINESS_075_CONTRACT.json"
)
FORWARD = FORWARD_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
OLD_SHA = "4768dbe91a2902fcfc372b72efcb736dd3bb073106c9fe0af45f5fcc6b9aa934"
NEW_SHA = "1a4e1ad18a987cf5fe5c89135fc064970f54c443ffe5674b8449054696232c3f"


def _dollar_block(text: str, tag: str) -> str:
    match = re.search(
        rf"\${re.escape(tag)}\$(.*?)\${re.escape(tag)}\$",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing dollar block: {tag}")
    return match.group(1)


def _current_claim_source() -> str:
    base = (
        ROOT / "sql/048_n6_btrack_proposal_scope_and_executor_claim_next.sql"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"CREATE OR REPLACE FUNCTION public\.n6_executor_claim_next_proposal\("
        r".*?AS \$function\$(.*?)\$function\$;",
        base,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("missing 048 claim-next source")
    source = match.group(1)
    for path, old_tag, new_tag in (
        (
            ROOT / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql",
            "old_next",
            "new_next",
        ),
        (
            ROOT / "sql/066_n6_btrack_regular_session_manual_buy.sql",
            "claim_next_065b",
            "claim_next_066",
        ),
    ):
        migration = path.read_text(encoding="utf-8")
        old = _dollar_block(migration, old_tag)
        new = _dollar_block(migration, new_tag)
        if source.count(old) != 1:
            raise AssertionError(f"claim source drift before {path.name}")
        source = source.replace(old, new)
    return source


OLD_SOURCE = _current_claim_source()
NEW_SOURCE = OLD_SOURCE.replace(
    _dollar_block(FORWARD, "claim_fifo_066"),
    _dollar_block(FORWARD, "claim_quote_ready_075"),
)


class N6075StaticContractTests(unittest.TestCase):
    def test_identity_and_frozen_hashes(self) -> None:
        self.assertEqual(CONTRACT["layer_role"], "N6_user")
        self.assertEqual(CONTRACT["execution_mode"], "FULL_MODE")
        self.assertEqual(CONTRACT["kernel_check"], "ACCEPT")
        self.assertEqual(sha256(OLD_SOURCE.encode()).hexdigest(), OLD_SHA)
        self.assertEqual(sha256(NEW_SOURCE.encode()).hexdigest(), NEW_SHA)
        self.assertEqual(
            CONTRACT["baseline"]["claim_next_source_sha256"], OLD_SHA
        )
        self.assertEqual(
            CONTRACT["executor_claim"]["new_claim_next_source_sha256"],
            NEW_SHA,
        )

    def test_claim_prefilter_matches_apply_quote_gates(self) -> None:
        ready = _dollar_block(FORWARD, "claim_quote_ready_075")
        for required in (
            "snapshot.identity_key = p.identity_key",
            "snapshot.exchange =",
            "snapshot.exchange IN ('SH', 'SZ')",
            "snapshot.quality_status = 'passed'",
            "snapshot.quality_reason = 'ok'",
            "clock_timestamp() - interval '2 minutes'",
            "snapshot.fetched_at >= snapshot.quote_minute",
            "AT TIME ZONE 'Asia/Shanghai'",
            "BETWEEN time '09:30' AND time '11:30'",
            "BETWEEN time '13:00' AND time '15:00'",
            "snapshot.current_price > 0",
            "'NaN', 'Infinity', '-Infinity'",
            "n6_executor_quote_ready_claim_075_v1",
        ):
            self.assertIn(required, ready)
        self.assertIn("FOR UPDATE SKIP LOCKED", NEW_SOURCE)
        self.assertIn("no_claimable_proposal", NEW_SOURCE)

    def test_exact_rollback_and_authority(self) -> None:
        self.assertEqual(
            _dollar_block(ROLLBACK, "claim_quote_ready_075"),
            _dollar_block(FORWARD, "claim_quote_ready_075"),
        )
        self.assertEqual(
            _dollar_block(ROLLBACK, "claim_fifo_066"),
            _dollar_block(FORWARD, "claim_fifo_066"),
        )
        for sql_text in (FORWARD, ROLLBACK):
            self.assertIn("SECURITY DEFINER", sql_text)
            self.assertIn("SET search_path=pg_catalog", sql_text)
            self.assertIn("function_proc.provolatile <> 'v'", sql_text)
            self.assertIn("function_proc.proparallel <> 'u'", sql_text)
            self.assertIn("TO n6_virtual_executor", sql_text)
            self.assertNotIn("TO n6_btrack_web;", sql_text)

    def test_migration_has_zero_business_dml(self) -> None:
        business_dml = re.compile(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+"
            r"public\.n6_",
            flags=re.IGNORECASE,
        )
        for sql_text in (FORWARD, ROLLBACK):
            self.assertIsNone(business_dml.search(sql_text))
            self.assertNotIn("ALTER TABLE", sql_text.upper())
            self.assertNotIn("DROP TABLE", sql_text.upper())
        self.assertFalse(CONTRACT["migration"]["business_row_dml"])
        self.assertFalse(CONTRACT["rollback"]["deletes_history"])

    def test_existing_queue_and_deployment_remain_frozen(self) -> None:
        queue = CONTRACT["existing_confirmed_queue"]
        self.assertFalse(queue["cancel_or_modify_authorized"])
        self.assertFalse(queue["automatic_execution_authorized"])
        self.assertTrue(queue["executor_must_remain_unloaded_after_deployment"])
        self.assertFalse(
            CONTRACT["migration"]["deployment_authorized_by_this_contract"]
        )


PG_ENABLED = os.environ.get("ASHARE_V3_N6_075_PG_INTEGRATION") == "1"
_SPEC = importlib.util.spec_from_file_location(
    "n6_064_pg_fixture_for_075",
    ROOT / "tests/test_n6_064_postgres_integration.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise AssertionError("cannot load isolated PostgreSQL fixture")
_FIXTURE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FIXTURE)


def _schema_sql() -> str:
    return f"""
GRANT USAGE, CREATE ON SCHEMA public TO ashare_v3_user;
SET ROLE ashare_v3_user;
CREATE TABLE public.n6_virtual_trade_proposal (
  proposal_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint,
  actor_ai_user_id bigint,
  source_ai_decision_id bigint,
  virtual_account_id bigint NOT NULL,
  identity_key text NOT NULL,
  proposal_side text NOT NULL,
  source_type text NOT NULL,
  source_signal_projection_id bigint,
  source_virtual_position_id bigint,
  signal_reference_kind text,
  signal_reference_price numeric,
  source_lineage_json jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  proposal_status text NOT NULL,
  expires_at timestamptz NOT NULL,
  confirmed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
  executor_run_id text,
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.now()
);
CREATE TABLE public.n6_virtual_quote_snapshot (
  virtual_quote_snapshot_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  identity_key text NOT NULL,
  exchange text NOT NULL,
  quality_status text NOT NULL,
  quality_reason text NOT NULL,
  quote_minute timestamptz NOT NULL,
  fetched_at timestamptz NOT NULL,
  current_price numeric
);
CREATE FUNCTION public.n6_btrack_regular_trade_session_open()
RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS 'SELECT true';
CREATE FUNCTION public.n6_btrack_manual_signal_buy_current_scope(
  bigint,text,bigint,bigint,bigint,text,text,numeric,text
) RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS 'SELECT true';
CREATE FUNCTION public.n6_executor_claim_next_proposal(
  p_executor_run_id text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS $claim${OLD_SOURCE}$claim$;
REVOKE ALL ON FUNCTION public.n6_executor_claim_next_proposal(text)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_executor_claim_next_proposal(text)
  TO n6_virtual_executor;
RESET ROLE;
"""


@unittest.skipUnless(
    PG_ENABLED,
    "set ASHARE_V3_N6_075_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6075PostgresIntegrationTests(unittest.TestCase):
    database = "n6_075"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.cluster = _FIXTURE._Pg16Cluster()
        try:
            cls.cluster.start()
            cls.cluster.create_database(cls.database)
            cls.cluster.run_sql(
                cls.database, _schema_sql(), label="n6_075_schema"
            )
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def _source_hash(self) -> str:
        with self.cluster.connect(self.database) as connection:
            source = connection.execute(
                "SELECT prosrc FROM pg_catalog.pg_proc WHERE oid="
                "'public.n6_executor_claim_next_proposal(text)'::regprocedure"
            ).fetchone()["prosrc"]
        return sha256(source.encode()).hexdigest()

    def _counts(self) -> tuple[int, int]:
        with self.cluster.connect(self.database) as connection:
            return tuple(
                connection.execute(
                    f"SELECT count(*) AS n FROM public.{table}"
                ).fetchone()["n"]
                for table in (
                    "n6_virtual_trade_proposal",
                    "n6_virtual_quote_snapshot",
                )
            )  # type: ignore[return-value]

    def _install_test_clock(self) -> None:
        from psycopg import sql

        with self.cluster.connect(self.database) as connection:
            connection.execute(
                """
                CREATE OR REPLACE FUNCTION public.n6_075_test_now()
                RETURNS timestamptz LANGUAGE sql STABLE
                SET search_path=pg_catalog AS
                'SELECT pg_catalog.current_setting('
                '''n6.test_clock'', false)::timestamptz'
                """
            )
            source = connection.execute(
                "SELECT prosrc FROM pg_catalog.pg_proc WHERE oid="
                "'public.n6_executor_claim_next_proposal(text)'::regprocedure"
            ).fetchone()["prosrc"]
            source = source.replace(
                "pg_catalog.clock_timestamp()", "public.n6_075_test_now()"
            )
            connection.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION "
                    "public.n6_executor_claim_next_proposal("
                    "p_executor_run_id text) "
                    "RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER "
                    "SET search_path=pg_catalog AS {}"
                ).format(sql.Literal(source))
            )

    def _seed(self, *, ready_second: bool) -> None:
        with self.cluster.connect(self.database) as connection:
            connection.execute("TRUNCATE public.n6_virtual_quote_snapshot")
            connection.execute("TRUNCATE public.n6_virtual_trade_proposal")
            for proposal_id, identity_key in (
                (1, "stock:SH:600001"),
                (2, "stock:SZ:000002"),
            ):
                connection.execute(
                    """
                    INSERT INTO public.n6_virtual_trade_proposal (
                      proposal_id, principal_id, principal_type, user_id,
                      virtual_account_id, identity_key, proposal_side,
                      source_type, source_signal_projection_id,
                      signal_reference_kind, signal_reference_price,
                      proposal_status, expires_at, confirmed_at, created_at
                    ) VALUES (
                      %s, 1, 'admin', 1, 1, %s, 'buy', 'signal', %s,
                      'trigger_price', 10, 'confirmed',
                      '2099-01-01 00:00:00+08',
                      '2026-07-22 09:31:00+08',
                      '2026-07-22 09:30:00+08'::timestamptz +
                        (%s * interval '1 second')
                    )
                    """,
                    (proposal_id, identity_key, proposal_id, proposal_id),
                )
            quote_time = (
                "2026-07-22 09:59:30+08"
                if ready_second
                else "2026-07-22 09:50:00+08"
            )
            connection.execute(
                """
                INSERT INTO public.n6_virtual_quote_snapshot (
                  identity_key, exchange, quality_status, quality_reason,
                  quote_minute, fetched_at, current_price
                ) VALUES
                  ('stock:SH:600001', 'SH', 'passed', 'ok',
                   '2026-07-22 09:50:00+08',
                   '2026-07-22 09:50:01+08', 10),
                  ('stock:SZ:000002', 'SZ', 'passed', 'ok',
                   %s, %s::timestamptz + interval '1 second', 20)
                """,
                (quote_time, quote_time),
            )

    def test_forward_rollback_and_fifo_readiness(self) -> None:
        baseline_counts = self._counts()
        self.assertEqual(self._source_hash(), OLD_SHA)
        self.cluster.apply_file(
            self.database, FORWARD_PATH, role="ashare_v3_user"
        )
        self.assertEqual(self._source_hash(), NEW_SHA)
        self.assertEqual(self._counts(), baseline_counts)
        self.cluster.apply_file(
            self.database, ROLLBACK_PATH, role="ashare_v3_user"
        )
        self.assertEqual(self._source_hash(), OLD_SHA)
        self.assertEqual(self._counts(), baseline_counts)

        self.cluster.apply_file(
            self.database, FORWARD_PATH, role="ashare_v3_user"
        )
        self._install_test_clock()
        self._seed(ready_second=True)
        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "SELECT pg_catalog.set_config("
                "'n6.test_clock','2026-07-22 10:00:00+08',false)"
            )
            result = connection.execute(
                "SELECT public.n6_executor_claim_next_proposal('run-1') AS r"
            ).fetchone()["r"]
            self.assertTrue(result["ok"])
            self.assertEqual(result["proposal_id"], 2)
            statuses = connection.execute(
                "SELECT proposal_id, proposal_status FROM "
                "public.n6_virtual_trade_proposal ORDER BY proposal_id"
            ).fetchall()
            self.assertEqual(
                [(row["proposal_id"], row["proposal_status"]) for row in statuses],
                [(1, "confirmed"), (2, "processing")],
            )

        self._seed(ready_second=False)
        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "SELECT pg_catalog.set_config("
                "'n6.test_clock','2026-07-22 10:00:00+08',false)"
            )
            result = connection.execute(
                "SELECT public.n6_executor_claim_next_proposal('run-2') AS r"
            ).fetchone()["r"]
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "no_claimable_proposal")
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) AS n FROM public.n6_virtual_trade_proposal "
                    "WHERE proposal_status <> 'confirmed'"
                ).fetchone()["n"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
