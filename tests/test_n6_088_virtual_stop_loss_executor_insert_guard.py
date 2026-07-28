"""Contract and isolated PostgreSQL 16 acceptance for N6 migration 088."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import unittest

from tests.test_n6_078_proposal_atomic_batch_cancel import (
    NEW_GUARD as BASELINE_GUARD,
)
from tests.test_n6_087_virtual_stop_loss_numeric_coalesce_fix import (
    FIXED_SOURCE as EVALUATOR_SOURCE,
    NEW_SHA as EVALUATOR_SHA,
    _Pg16Cluster,
    _fixture_schema_sql,
)


ROOT = Path(__file__).resolve().parents[1]
FORWARD_PATH = (
    ROOT / "sql/088_n6_virtual_stop_loss_executor_insert_guard.sql"
)
ROLLBACK_PATH = (
    ROOT / "sql/088_n6_virtual_stop_loss_executor_insert_guard_rollback.sql"
)
CONTRACT_PATH = (
    ROOT
    / "docs/N6_VIRTUAL_STOP_LOSS_EXECUTOR_INSERT_GUARD_088_CONTRACT.json"
)
FORWARD = FORWARD_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
PG_ENABLED = os.environ.get("ASHARE_V3_N6_088_PG_INTEGRATION") == "1"
PG_BIN = Path(
    os.environ.get(
        "ASHARE_V3_N6_088_PG_BIN",
        "/opt/homebrew/opt/postgresql@16/bin",
    )
)
OLD_GUARD_SHA = (
    "8c0e5f213c7c3e83eb7c488bb3302f94de86db98c4a95901f4776e44aec2ebf8"
)
NEW_GUARD_SHA = (
    "28aaea4f21b22cece83fa6f494d6d19ad67ec753af3778765749094ccbb21f58"
)


def _dollar_block(text: str, tag: str) -> str:
    match = re.search(
        rf"\${re.escape(tag)}\$(.*?)\${re.escape(tag)}\$",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing dollar block: {tag}")
    return match.group(1)


OLD_INSERT_BRANCH = _dollar_block(FORWARD, "guard_executor_insert_078")
NEW_INSERT_BRANCH = _dollar_block(FORWARD, "guard_executor_insert_088")
FIXED_GUARD = BASELINE_GUARD.replace(
    OLD_INSERT_BRANCH,
    NEW_INSERT_BRANCH,
)


class N6088StaticContractTests(unittest.TestCase):
    def test_exact_baseline_and_fixed_guard_hashes(self) -> None:
        self.assertEqual(sha256(BASELINE_GUARD.encode()).hexdigest(), OLD_GUARD_SHA)
        self.assertEqual(BASELINE_GUARD.count(OLD_INSERT_BRANCH), 1)
        self.assertNotIn(NEW_INSERT_BRANCH, BASELINE_GUARD)
        self.assertEqual(sha256(FIXED_GUARD.encode()).hexdigest(), NEW_GUARD_SHA)
        self.assertEqual(FIXED_GUARD.count(NEW_INSERT_BRANCH), 1)
        self.assertNotIn(OLD_INSERT_BRANCH, FIXED_GUARD)
        self.assertEqual(CONTRACT["baseline"]["candidate_migration"], "088")
        self.assertEqual(
            CONTRACT["repair"]["new_guard_source_sha256"],
            NEW_GUARD_SHA,
        )

    def test_allowance_is_exact_stop_loss_shape_only(self) -> None:
        for marker in (
            "NEW.source_type = 'stop_loss'",
            "NEW.proposal_side = 'sell'",
            "NEW.proposal_status = 'confirmed'",
            "NEW.signal_reference_kind = 'stop_loss'",
            "NEW.source_virtual_position_id IS NOT NULL",
            "NEW.holding_episode_no IS NOT NULL",
            "NEW.confirm_idempotency_key = 'stop_loss:' || NEW.source_id",
            "NEW.executed_virtual_order_id IS NULL",
            "NEW.executed_virtual_trade_id IS NULL",
            "NEW.executor_run_id IS NULL",
            "NEW.failure_reason IS NULL",
            "NEW.source_ai_decision_id IS NULL",
            "NEW.policy_hash = NEW.policy_version",
            "n6_virtual_stop_loss_049_v1",
            "n6_ai_agent_execution_compat_057_v1",
            "FROM public.n6_virtual_position position",
            "position.stop_loss_status = 'frozen'",
            "executor proposal insert rejected",
        ):
            self.assertIn(marker, NEW_INSERT_BRANCH)
        self.assertIn("?& ARRAY[", NEW_INSERT_BRANCH)
        self.assertIn(") = '{}'::jsonb", NEW_INSERT_BRANCH)
        self.assertNotIn("GRANT INSERT", FORWARD)
        self.assertNotIn("GRANT UPDATE", FORWARD)
        self.assertNotIn("GRANT DELETE", FORWARD)

    def test_078_web_and_executor_update_paths_are_byte_preserved(self) -> None:
        self.assertEqual(
            FIXED_GUARD.replace(NEW_INSERT_BRANCH, OLD_INSERT_BRANCH),
            BASELINE_GUARD,
        )
        web_start = "  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_btrack_web' THEN"
        executor_update = (
            "  ELSIF TG_OP='UPDATE' AND SESSION_USER='n6_virtual_executor' THEN"
        )
        self.assertEqual(
            FIXED_GUARD[FIXED_GUARD.index(web_start) :],
            BASELINE_GUARD[BASELINE_GUARD.index(web_start) :],
        )
        self.assertEqual(FIXED_GUARD.count(executor_update), 1)
        self.assertIn("n6_btrack_proposal_cancel_078_v1", FIXED_GUARD)

    def test_forward_rollback_acl_and_zero_dml_contract(self) -> None:
        for text in (FORWARD, ROLLBACK):
            for marker in (
                "OWNER TO ashare_v3_user",
                "REVOKE ALL ON FUNCTION",
                "PUBLIC",
                "n6_btrack_web",
                "n6_ai_agent",
                "n6_quote_writer",
                "n6_virtual_executor",
                "SECURITY DEFINER",
                "VOLATILE",
                "search_path=pg_catalog",
                "has_table_privilege",
            ):
                self.assertIn(marker, text)
        self.assertIn(OLD_GUARD_SHA, FORWARD + ROLLBACK)
        self.assertIn(NEW_GUARD_SHA, FORWARD + ROLLBACK)
        self.assertNotIn("__NEW_GUARD_SHA__", FORWARD + ROLLBACK)
        self.assertNotRegex(
            FORWARD,
            r"(?i)\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
            r"public\.n6_virtual_(?:trade_proposal|order|trade|cash|position)",
        )
        self.assertFalse(CONTRACT["rollback"]["deletes_history"])
        self.assertFalse(CONTRACT["historical_missed_stops"]["backfilled"])

    def test_existing_evaluator_and_trade_log_contract_are_preserved(self) -> None:
        evaluator_sql = (
            ROOT / "sql/087_n6_virtual_stop_loss_numeric_coalesce_fix.sql"
        ).read_text(encoding="utf-8")
        self.assertIn(EVALUATOR_SHA, evaluator_sql)
        self.assertIn("IF COALESCE(matured_quantity, 0::numeric) <= 0 THEN", evaluator_sql)
        self.assertIn(
            "INSERT INTO public.n6_virtual_trade_proposal",
            EVALUATOR_SOURCE,
        )
        for marker in (
            "'stop_loss', source_key",
            "'stock', position_row.identity_key, 'sell', 'stop_loss'",
            "position_row.stop_loss_price, 'confirmed'",
        ):
            self.assertIn(marker, EVALUATOR_SOURCE)
        trade_list_sql = (
            ROOT / "sql/042_n6_b_track_db_role_policy_schema.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("FROM public.n6_virtual_trade t,authority a", trade_list_sql)


def _guard_fixture_sql() -> str:
    return f"""
SET ROLE ashare_v3_user;
ALTER TABLE public.n6_virtual_trade_proposal
  ADD COLUMN strategy_action_id bigint;

CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_transition_guard()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS $function${BASELINE_GUARD}$function$;
ALTER FUNCTION public.n6_btrack_proposal_transition_guard()
  OWNER TO ashare_v3_user;
REVOKE ALL ON FUNCTION public.n6_btrack_proposal_transition_guard()
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
       n6_virtual_executor;
CREATE TRIGGER n6_btrack_proposal_transition_guard
BEFORE INSERT OR UPDATE ON public.n6_virtual_trade_proposal
FOR EACH ROW EXECUTE FUNCTION public.n6_btrack_proposal_transition_guard();

INSERT INTO public.n6_principal VALUES
  (1, 'admin', 1, 'active'),
  (2, 'ai_user', NULL, 'active');
INSERT INTO public.n6_ai_user VALUES
  (20, 2, 'ai_user', 'active');
INSERT INTO public.n6_virtual_position VALUES
  (1, 1, 1, 'admin', 'stock', 'stock:SH:600000',
   'open_virtual', 100, 1, 'frozen', '2026-07-24', 10,
   90, 'n6_virtual_stop_loss_049_v1', 'hash-049'),
  (2, 2, 2, 'ai_user', 'stock', 'stock:SZ:000001',
   'open_virtual', 200, 1, 'frozen', '2026-07-24', 20,
   91, 'n6_virtual_stop_loss_049_v1', 'hash-ai');

CREATE FUNCTION public.n6_test_executor_insert_stop_loss(
  p_position_id bigint,
  p_source_type text,
  p_proposal_side text,
  p_proposal_status text,
  p_reference_kind text,
  p_policy_version text,
  p_price_delta numeric,
  p_extra_lineage boolean
) RETURNS bigint
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS $function$
DECLARE
  position_row public.n6_virtual_position%ROWTYPE;
  owner_user_id bigint;
  actor_ai_user_id bigint;
  source_key text;
  lineage jsonb;
  proposal_id bigint;
BEGIN
  SELECT * INTO STRICT position_row
  FROM public.n6_virtual_position
  WHERE virtual_position_id = p_position_id;
  IF position_row.principal_type IN ('admin', 'human_user') THEN
    SELECT principal.owner_user_id INTO owner_user_id
    FROM public.n6_principal principal
    WHERE principal.principal_id = position_row.principal_id
      AND principal.principal_type = position_row.principal_type;
  ELSE
    SELECT ai_user.ai_user_id INTO actor_ai_user_id
    FROM public.n6_ai_user ai_user
    WHERE ai_user.principal_id = position_row.principal_id
      AND ai_user.principal_type = position_row.principal_type;
  END IF;
  source_key := position_row.virtual_position_id || ':' ||
                position_row.holding_episode_no || ':9002';
  lineage := pg_catalog.jsonb_build_object(
    'virtual_position_id', position_row.virtual_position_id,
    'holding_episode_no', position_row.holding_episode_no,
    'first_trigger_quote_snapshot_id', 9001,
    'confirm_trigger_quote_snapshot_id', 9002,
    'stop_loss_price', position_row.stop_loss_price + p_price_delta,
    'trigger_price', position_row.stop_loss_price - 0.10,
    'stop_loss_source_quote_snapshot_id',
      position_row.stop_loss_source_quote_snapshot_id,
    'stop_loss_policy_version', position_row.stop_loss_policy_version,
    'stop_loss_policy_hash', position_row.stop_loss_policy_hash,
    'executor_run_id', 'n6-088-pg16',
    'rearmed_after_terminal_proposal_id', NULL
  );
  IF p_extra_lineage THEN
    lineage := lineage || '{{"unexpected":true}}'::jsonb;
  END IF;
  INSERT INTO public.n6_virtual_trade_proposal (
    principal_id, principal_type, user_id, actor_ai_user_id,
    source_ai_decision_id, virtual_account_id,
    source_type, source_id, source_virtual_position_id, holding_episode_no,
    asset_kind, identity_key, proposal_side, signal_reference_kind,
    signal_reference_price, proposal_status, expires_at, confirmed_at,
    confirm_idempotency_key, policy_version, policy_hash, source_lineage_json
  ) VALUES (
    position_row.principal_id, position_row.principal_type, owner_user_id,
    actor_ai_user_id, NULL, position_row.virtual_account_id,
    p_source_type, source_key,
    position_row.virtual_position_id, position_row.holding_episode_no,
    'stock', position_row.identity_key, p_proposal_side, p_reference_kind,
    position_row.stop_loss_price + p_price_delta, p_proposal_status,
    pg_catalog.clock_timestamp() + interval '60 seconds',
    pg_catalog.clock_timestamp(), 'stop_loss:' || source_key,
    p_policy_version, p_policy_version, lineage
  ) RETURNING n6_virtual_trade_proposal.proposal_id INTO proposal_id;
  RETURN proposal_id;
END
$function$;
ALTER FUNCTION public.n6_test_executor_insert_stop_loss(
  bigint,text,text,text,text,text,numeric,boolean
) OWNER TO ashare_v3_user;
REVOKE ALL ON FUNCTION public.n6_test_executor_insert_stop_loss(
  bigint,text,text,text,text,text,numeric,boolean
) FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION public.n6_test_executor_insert_stop_loss(
  bigint,text,text,text,text,text,numeric,boolean
) TO n6_virtual_executor;
RESET ROLE;
"""


@unittest.skipUnless(
    PG_ENABLED,
    "set ASHARE_V3_N6_088_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6088PostgresIntegrationTests(unittest.TestCase):
    cluster: _Pg16Cluster

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        for binary in ("initdb", "pg_ctl", "postgres", "psql"):
            if not (PG_BIN / binary).is_file():
                raise AssertionError(f"PostgreSQL 16 binary missing: {binary}")
        version = subprocess.run(
            [str(PG_BIN / "postgres"), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if version.returncode or " 16." not in version.stdout:
            raise AssertionError(f"PostgreSQL 16 required: {version.stdout}")
        cls.cluster = _Pg16Cluster()
        cls.cluster.start()
        cls.cluster.run_sql(_fixture_schema_sql(), label="fixture_schema")
        cls.cluster.run_sql(_guard_fixture_sql(), label="guard_fixture")
        cls.cluster.apply(
            ROOT / "sql/087_n6_virtual_stop_loss_numeric_coalesce_fix.sql"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def _guard_metadata(self) -> dict[str, object]:
        with self.cluster.connect() as connection:
            return connection.execute(
                """
                SELECT pg_catalog.encode(
                         pg_catalog.sha256(
                           pg_catalog.convert_to(p.prosrc, 'UTF8')
                         ), 'hex'
                       ) AS source_sha,
                       owner.rolname AS owner_name,
                       p.prosecdef, p.provolatile, p.proparallel, p.proconfig
                FROM pg_catalog.pg_proc p
                JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
                WHERE p.oid = pg_catalog.to_regprocedure(
                  'public.n6_btrack_proposal_transition_guard()'
                )
                """
            ).fetchone()

    def _summary(self) -> tuple[int, ...]:
        with self.cluster.connect() as connection:
            row = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM public.n6_virtual_trade_proposal),
                  (SELECT count(*) FROM public.n6_virtual_order),
                  (SELECT count(*) FROM public.n6_virtual_trade),
                  (SELECT count(*) FROM public.n6_virtual_cash_ledger),
                  (SELECT count(*) FROM public.n6_virtual_cash_snapshot),
                  (SELECT count(*) FROM public.n6_virtual_position),
                  (SELECT count(*) FROM public.n6_virtual_position_lot)
                """
            ).fetchone()
        return tuple(int(value) for value in row.values())

    def _call_fixture(
        self,
        *,
        position_id: int = 1,
        source_type: str = "stop_loss",
        side: str = "sell",
        status: str = "confirmed",
        reference_kind: str = "stop_loss",
        policy: str = "n6_virtual_stop_loss_049_v1",
        price_delta: int = 0,
        extra_lineage: bool = False,
    ) -> int:
        with self.cluster.connect(user="n6_virtual_executor") as connection:
            row = connection.execute(
                """
                SELECT public.n6_test_executor_insert_stop_loss(
                  %s,%s,%s,%s,%s,%s,%s,%s
                ) AS proposal_id
                """,
                (
                    position_id,
                    source_type,
                    side,
                    status,
                    reference_kind,
                    policy,
                    price_delta,
                    extra_lineage,
                ),
            ).fetchone()
        return int(row["proposal_id"])

    def _assert_rejected(self, **overrides: object) -> None:
        import psycopg

        with self.assertRaisesRegex(
            psycopg.errors.RaiseException,
            "executor proposal insert rejected",
        ):
            self._call_fixture(**overrides)

    def _install_clocked_runtime(self) -> None:
        from psycopg import sql

        clocked_evaluator = EVALUATOR_SOURCE.replace(
            "pg_catalog.clock_timestamp()",
            "public.n6_test_clock()",
        )
        clocked_guard = FIXED_GUARD.replace(
            "pg_catalog.clock_timestamp()",
            "public.n6_test_clock()",
        )
        with self.cluster.connect() as connection:
            connection.execute(
                """
                CREATE TABLE public.n6_test_clock_state (
                  instant timestamptz NOT NULL
                );
                INSERT INTO public.n6_test_clock_state VALUES
                  ('2026-07-24 10:02:00+08'::timestamptz);
                GRANT SELECT ON public.n6_test_clock_state TO ashare_v3_user;
                CREATE FUNCTION public.n6_test_clock()
                RETURNS timestamptz LANGUAGE sql STABLE
                AS $clock$
                  SELECT instant FROM public.n6_test_clock_state LIMIT 1
                $clock$;
                """
            )
            connection.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION "
                    "public.n6_executor_evaluate_next_stop_loss("
                    "p_executor_run_id text) RETURNS jsonb LANGUAGE plpgsql "
                    "VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS {}"
                ).format(sql.Literal(clocked_evaluator))
            )
            connection.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION "
                    "public.n6_btrack_proposal_transition_guard() "
                    "RETURNS trigger LANGUAGE plpgsql VOLATILE "
                    "SECURITY DEFINER SET search_path=pg_catalog AS {}"
                ).format(sql.Literal(clocked_guard))
            )
            connection.execute(
                """
                ALTER FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  OWNER TO ashare_v3_user;
                REVOKE ALL ON FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
                GRANT EXECUTE ON FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  TO n6_virtual_executor;
                ALTER FUNCTION
                  public.n6_btrack_proposal_transition_guard()
                  OWNER TO ashare_v3_user;
                REVOKE ALL ON FUNCTION
                  public.n6_btrack_proposal_transition_guard()
                  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
                       n6_virtual_executor;
                """
            )

    def _restore_runtime_sources(self) -> None:
        from psycopg import sql

        with self.cluster.connect() as connection:
            connection.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION "
                    "public.n6_executor_evaluate_next_stop_loss("
                    "p_executor_run_id text) RETURNS jsonb LANGUAGE plpgsql "
                    "VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS {}"
                ).format(sql.Literal(EVALUATOR_SOURCE))
            )
            connection.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION "
                    "public.n6_btrack_proposal_transition_guard() "
                    "RETURNS trigger LANGUAGE plpgsql VOLATILE "
                    "SECURITY DEFINER SET search_path=pg_catalog AS {}"
                ).format(sql.Literal(FIXED_GUARD))
            )
            connection.execute(
                """
                ALTER FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  OWNER TO ashare_v3_user;
                REVOKE ALL ON FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
                GRANT EXECUTE ON FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  TO n6_virtual_executor;
                ALTER FUNCTION
                  public.n6_btrack_proposal_transition_guard()
                  OWNER TO ashare_v3_user;
                REVOKE ALL ON FUNCTION
                  public.n6_btrack_proposal_transition_guard()
                  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer,
                       n6_virtual_executor;
                """
            )

    def test_forward_exact_allowance_fail_closed_matrix_and_rollback(self) -> None:
        import psycopg

        before = self._summary()
        self.assertEqual(self._guard_metadata()["source_sha"], OLD_GUARD_SHA)
        with self.assertRaisesRegex(
            psycopg.errors.RaiseException,
            "executor cannot create proposal",
        ):
            self._call_fixture()

        self.cluster.apply(FORWARD_PATH)
        self.assertEqual(self._summary(), before)
        metadata = self._guard_metadata()
        self.assertEqual(metadata["source_sha"], NEW_GUARD_SHA)
        self.assertEqual(metadata["owner_name"], "ashare_v3_user")
        self.assertTrue(metadata["prosecdef"])
        self.assertEqual(metadata["provolatile"], "v")
        self.assertEqual(metadata["proparallel"], "u")
        self.assertEqual(metadata["proconfig"], ["search_path=pg_catalog"])

        with self.cluster.connect() as connection:
            privileges = connection.execute(
                """
                SELECT
                  pg_catalog.has_table_privilege(
                    'n6_virtual_executor',
                    'public.n6_virtual_trade_proposal', 'INSERT'
                  ) AS can_insert,
                  pg_catalog.has_table_privilege(
                    'n6_virtual_executor',
                    'public.n6_virtual_trade_proposal', 'UPDATE'
                  ) AS can_update,
                  pg_catalog.has_table_privilege(
                    'n6_virtual_executor',
                    'public.n6_virtual_trade_proposal', 'DELETE'
                  ) AS can_delete
                """
            ).fetchone()
        self.assertEqual(
            privileges,
            {"can_insert": False, "can_update": False, "can_delete": False},
        )

        self._assert_rejected(source_type="signal")
        self._assert_rejected(side="buy")
        self._assert_rejected(status="pending")
        self._assert_rejected(reference_kind="action_price")
        self._assert_rejected(policy="unexpected_policy")
        self._assert_rejected(price_delta=1)
        self._assert_rejected(extra_lineage=True)
        self.assertEqual(self._summary(), before)

        self._install_clocked_runtime()
        with self.cluster.connect() as connection:
            connection.execute(
                """
                INSERT INTO public.common_trade_calendar VALUES
                  ('20260724', true);
                INSERT INTO public.n6_virtual_position_lot (
                  virtual_position_id, virtual_account_id, principal_id,
                  principal_type, identity_key, holding_episode_no,
                  remaining_quantity, available_trade_date, lot_status
                ) VALUES (
                  1, 1, 1, 'admin', 'stock:SH:600000', 1,
                  100, '2026-07-24', 'available'
                );
                INSERT INTO public.n6_virtual_quote_snapshot VALUES
                  (9001, 'stock:SH:600000', 'SH',
                   '2026-07-24 10:00:00+08', '2026-07-24 10:00:05+08',
                   'passed', 'ok', 9.95),
                  (9002, 'stock:SH:600000', 'SH',
                   '2026-07-24 10:01:00+08', '2026-07-24 10:01:05+08',
                   'passed', 'ok', 9.90);
                """
            )
        with self.cluster.connect(user="n6_virtual_executor") as connection:
            payload = connection.execute(
                """
                SELECT public.n6_executor_evaluate_next_stop_loss(
                  'n6-088-natural-evaluator'
                ) AS payload
                """
            ).fetchone()["payload"]
        self.assertEqual(payload["status"], "confirmed")
        human_id = int(payload["proposal_id"])
        self._restore_runtime_sources()
        self.assertEqual(self._guard_metadata()["source_sha"], NEW_GUARD_SHA)

        ai_id = self._call_fixture(
            position_id=2,
            policy="n6_ai_agent_execution_compat_057_v1",
        )
        self.assertGreater(human_id, 0)
        self.assertGreater(ai_id, human_id)
        with self.cluster.connect() as connection:
            rows = connection.execute(
                """
                SELECT proposal_id, principal_type, user_id, actor_ai_user_id,
                       source_type, proposal_side, proposal_status,
                       signal_reference_kind, policy_version
                FROM public.n6_virtual_trade_proposal
                ORDER BY proposal_id
                """
            ).fetchall()
        self.assertEqual(
            [dict(row) for row in rows],
            [
                {
                    "proposal_id": human_id,
                    "principal_type": "admin",
                    "user_id": 1,
                    "actor_ai_user_id": None,
                    "source_type": "stop_loss",
                    "proposal_side": "sell",
                    "proposal_status": "confirmed",
                    "signal_reference_kind": "stop_loss",
                    "policy_version": "n6_virtual_stop_loss_049_v1",
                },
                {
                    "proposal_id": ai_id,
                    "principal_type": "ai_user",
                    "user_id": None,
                    "actor_ai_user_id": 20,
                    "source_type": "stop_loss",
                    "proposal_side": "sell",
                    "proposal_status": "confirmed",
                    "signal_reference_kind": "stop_loss",
                    "policy_version": "n6_ai_agent_execution_compat_057_v1",
                },
            ],
        )

        after_allowed = self._summary()
        self.cluster.apply(ROLLBACK_PATH)
        self.assertEqual(self._summary(), after_allowed)
        self.assertEqual(self._guard_metadata()["source_sha"], OLD_GUARD_SHA)
        with self.assertRaisesRegex(
            psycopg.errors.RaiseException,
            "executor cannot create proposal",
        ):
            self._call_fixture(position_id=1)

        self.cluster.apply(FORWARD_PATH)
        self.assertEqual(self._summary(), after_allowed)
        self.assertEqual(self._guard_metadata()["source_sha"], NEW_GUARD_SHA)


if __name__ == "__main__":
    unittest.main()
