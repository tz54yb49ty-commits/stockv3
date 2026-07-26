"""Contract and opt-in PG16 acceptance for N6 migration 069."""

from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD_PATH = ROOT / "sql/069_n6_btrack_t1_natural_day_unlock.sql"
ROLLBACK_PATH = (
    ROOT / "sql/069_n6_btrack_t1_natural_day_unlock_rollback.sql"
)
CONTRACT_PATH = (
    ROOT / "docs/N6_B_TRACK_T1_NATURAL_DAY_UNLOCK_069_CONTRACT.json"
)
FORWARD = FORWARD_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

OLD_APPLY_SHA = (
    "d9cfbc4e07efce566e40fc642c60ef8ef5720aa2ca2aab942c3d0f4151c76366"
)
NEW_APPLY_SHA = (
    "759dfdf9c5422a55d1b4d6d183a4f6a2bca88039265374794d8e66f6f6c833c2"
)
SESSION_HELPER_SHA = (
    "316ed7080aea0f343a7231b338a82f95fbec05755743bb46948583d9c93cac76"
)
QUOTE_SCOPE_SHA = (
    "856bfc57439d85e9f1cab84a93f25dfcf4e4a50274e30c60cfac0e7110b527b1"
)
OLD_POLICY = "n6_btrack_regular_session_manual_buy_066_v1"
NEW_POLICY = "n6_btrack_t1_natural_day_unlock_069_v1"


def _dollar_block(sql_text: str, tag: str) -> str:
    match = re.search(
        rf"\${re.escape(tag)}\$(.*?)\${re.escape(tag)}\$",
        sql_text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing dollar block: {tag}")
    return match.group(1)


class N6069StaticContractTests(unittest.TestCase):
    def test_contract_identity_and_frozen_baseline(self) -> None:
        self.assertEqual(CONTRACT["layer_role"], "N6_user")
        self.assertEqual(CONTRACT["execution_mode"], "FULL_MODE")
        self.assertEqual(CONTRACT["kernel_check"], "ACCEPT")
        self.assertEqual(
            CONTRACT["baseline"]["commit"],
            "5e94718c045d6a92f0462661781be7c581e76607",
        )
        self.assertEqual(
            CONTRACT["baseline"]["tree"],
            "2c116558bad14c5b521612dc82214f0ba090e58a",
        )
        self.assertEqual(
            CONTRACT["baseline"]["apply_function_source_sha256"],
            OLD_APPLY_SHA,
        )

    def test_forward_removes_only_future_calendar_dependency(self) -> None:
        declaration = _dollar_block(
            FORWARD, "next_trade_date_declaration"
        )
        calendar = _dollar_block(FORWARD, "future_calendar_dependency")
        old_lot = _dollar_block(FORWARD, "future_open_day_lot")
        new_lot = _dollar_block(FORWARD, "natural_day_lot")
        self.assertEqual(declaration, "  next_trade_date date;\n")
        self.assertIn("INTO next_trade_date", calendar)
        self.assertIn("next_trade_date_not_ready", calendar)
        self.assertEqual(
            old_lot,
            "      trade_date_date, next_trade_date, fill_quantity, "
            "fill_quantity, fill_price,\n",
        )
        self.assertEqual(
            new_lot,
            "      trade_date_date, trade_date_date + 1, fill_quantity, "
            "fill_quantity,\n      fill_price,\n",
        )
        self.assertIn("occurrence_count <> 15", FORWARD)
        self.assertIn(OLD_POLICY, FORWARD)
        self.assertIn(NEW_POLICY, FORWARD)

    def test_rollback_reinstates_exact_066_fragments(self) -> None:
        declaration = _dollar_block(
            ROLLBACK, "next_trade_date_declaration"
        )
        calendar = _dollar_block(ROLLBACK, "future_calendar_dependency")
        old_lot = _dollar_block(ROLLBACK, "future_open_day_lot")
        self.assertEqual(
            declaration,
            "  trade_date_date date;\n  next_trade_date date;\n",
        )
        self.assertIn("next_trade_date_not_ready", calendar)
        self.assertTrue(calendar.endswith("    episode_no := CASE\n"))
        self.assertIn("trade_date_date, next_trade_date", old_lot)
        self.assertIn("occurrence_count <> 15", ROLLBACK)

    def test_function_hashes_are_cross_pinned(self) -> None:
        self.assertIn(OLD_APPLY_SHA, FORWARD)
        self.assertIn(NEW_APPLY_SHA, FORWARD)
        self.assertIn(NEW_APPLY_SHA, ROLLBACK)
        self.assertIn(OLD_APPLY_SHA, ROLLBACK)
        for sql_text in (FORWARD, ROLLBACK):
            self.assertGreaterEqual(sql_text.count(SESSION_HELPER_SHA), 2)
            self.assertGreaterEqual(sql_text.count(QUOTE_SCOPE_SHA), 2)
            self.assertIn("function_proc.provolatile <> 'v'", sql_text)
            self.assertIn("ARRAY['search_path=pg_catalog']::text[]", sql_text)

    def test_owner_security_and_acl_remain_fail_closed(self) -> None:
        for sql_text in (FORWARD, ROLLBACK):
            self.assertIn("function_proc.owner_name <> current_user", sql_text)
            self.assertIn("function_proc.prosecdef IS DISTINCT FROM true", sql_text)
            self.assertIn("LANGUAGE plpgsql VOLATILE SECURITY DEFINER", sql_text)
            self.assertIn("SET search_path=pg_catalog", sql_text)
            self.assertIn(
                "FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer",
                sql_text,
            )
            self.assertIn("TO n6_virtual_executor", sql_text)
            self.assertIn("pg_catalog.aclexplode", sql_text)

    def test_migration_and_rollback_have_no_business_row_dml(self) -> None:
        business_dml = re.compile(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+"
            r"public\.n6_",
            flags=re.IGNORECASE,
        )
        for sql_text in (FORWARD, ROLLBACK):
            self.assertIsNone(business_dml.search(sql_text))
            self.assertNotIn("DROP TABLE", sql_text.upper())
            self.assertNotIn("ALTER TABLE", sql_text.upper())
        self.assertFalse(CONTRACT["migration"]["business_row_dml"])
        self.assertFalse(CONTRACT["migration"]["table_schema_change"])
        self.assertFalse(CONTRACT["rollback"]["deletes_history"])

    def test_sell_maturity_authority_is_preserved(self) -> None:
        base_apply = (
            ROOT / "sql/049_n6_virtual_stop_loss_freeze_evaluate_execute.sql"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "available_trade_date <= trade_date_date", base_apply
        )
        self.assertIn(
            "ORDER BY available_trade_date, virtual_position_lot_id",
            base_apply,
        )
        self.assertEqual(
            CONTRACT["t1_semantics"]["lot_authority"],
            "public.n6_virtual_position_lot",
        )
        self.assertEqual(
            CONTRACT["t1_semantics"]["sell_maturity_predicate"],
            "available_trade_date <= current_open_trade_date",
        )

    def test_natural_day_boundary_examples(self) -> None:
        monday = date(2026, 7, 20)
        friday = date(2026, 7, 24)
        self.assertEqual(monday + timedelta(days=1), date(2026, 7, 21))
        self.assertEqual(friday + timedelta(days=1), date(2026, 7, 25))
        self.assertGreater(monday + timedelta(days=1), monday)
        self.assertLessEqual(friday + timedelta(days=1), date(2026, 7, 28))
        self.assertFalse(CONTRACT["t1_semantics"]["same_day_sell_allowed"])
        self.assertFalse(
            CONTRACT["t1_semantics"]["weekend_or_closed_day_sell_allowed"]
        )
        self.assertTrue(
            CONTRACT["t1_semantics"]["next_actual_open_day_sell_allowed"]
        )

    def test_preserved_gates_and_scope_are_explicit(self) -> None:
        gates = CONTRACT["preserved_gates"]
        for key in (
            "current_open_trade_date",
            "quote_identity_quality_and_positive_finite_price",
            "cash_check",
            "principal_and_monitor_scope",
            "idempotent_atomic_execution",
            "existing_target_price_preserved_on_add",
            "existing_stop_loss_state_preserved_on_add",
            "real_broker_isolation",
        ):
            self.assertTrue(gates[key], key)
        self.assertEqual(gates["fresh_quote_max_age_seconds"], 120)
        self.assertEqual(gates["server_budget_cny"], 300000)
        self.assertEqual(gates["board_lot_size_shares"], 100)
        scope = CONTRACT["scope"]
        self.assertFalse(scope["web_or_api_changed"])
        self.assertFalse(scope["quote_scope_068_changed"])
        self.assertFalse(scope["session_helper_066_changed"])
        self.assertFalse(scope["stop_loss_logic_changed"])
        self.assertEqual(
            scope["confirmed_proposal_count_observed_before_implementation"],
            11,
        )
        self.assertFalse(scope["executor_resume_authorized"])
        self.assertFalse(scope["proposal_processing_authorized"])

    def test_deployment_remains_a_separate_gate(self) -> None:
        deployment = CONTRACT["deployment"]
        self.assertTrue(deployment["requires_separate_gate"])
        self.assertTrue(deployment["executor_must_remain_paused_during_migration"])
        self.assertTrue(
            deployment[
                "executor_resume_and_confirmed_proposal_allowlist_require_separate_gate"
            ]
        )
        self.assertFalse(
            CONTRACT["migration"]["deployment_authorized_by_this_contract"]
        )


PG_ENABLED = os.environ.get("ASHARE_V3_N6_069_PG_INTEGRATION") == "1"
_SPEC = importlib.util.spec_from_file_location(
    "n6_064_pg_fixture_for_069",
    ROOT / "tests/test_n6_064_postgres_integration.py",
)
if _SPEC is None or _SPEC.loader is None:
    raise AssertionError("cannot load isolated PostgreSQL fixture")
_FIXTURE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FIXTURE)

MIGRATIONS = (
    ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql",
    ROOT / "sql/065_n6_btrack_current_date_batch_scope_fix.sql",
    ROOT / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql",
    ROOT / "sql/065b_n6_btrack_confirmed_manual_buy_apply_scope_fix.sql",
    ROOT / "sql/066_n6_btrack_regular_session_manual_buy.sql",
    ROOT / "sql/068_n6_quote_writer_mootdx_compat.sql",
)
BUSINESS_TABLES = (
    "n6_virtual_trade_proposal",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_cash_ledger",
    "n6_virtual_cash_snapshot",
    "n6_virtual_position",
    "n6_virtual_position_lot",
    "n6_virtual_position_event",
)
SESSION_HASH = _FIXTURE.SESSION_HASH

CURRENT_BATCH_SEED_SQL = r"""
BEGIN;
SET LOCAL session_replication_role = replica;
INSERT INTO public.common_trade_calendar (
  trade_date, exchange, is_open, prev_trade_date, next_trade_date,
  source, source_batch_id, source_version
)
SELECT pg_catalog.to_char(
         pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
         'YYYYMMDD'
       ),
       'SSE', true, '20260720', '20991231',
       'fixture', 'fixture-current', 'fixture-v1'
WHERE NOT EXISTS (
  SELECT 1
  FROM public.common_trade_calendar calendar
  WHERE calendar.trade_date = pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        )
);
INSERT INTO public.stock_condition_display_basis (
  stock_condition_display_basis_id, run_id, for_trade_date,
  source_trade_date, prev_trade_date, stock_identity_key, code, exchange,
  name, display_policy_hash, primary_source_condition_basis_id,
  source_version, display_status, quality_status
) OVERRIDING SYSTEM VALUE
SELECT 3, 'fixture-current-condition-run',
       pg_catalog.to_char(
         pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
         'YYYYMMDD'
       ),
       '20260720', '20260720', 'stock:SH:600000', '600000', 'SH',
       'Fixture Stock', 'fixture-current-display-hash', 999998,
       'fixture-v1', 'visible', 'passed'
WHERE NOT EXISTS (
  SELECT 1
  FROM public.stock_condition_display_basis basis
  WHERE basis.for_trade_date::text = pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        )
);
SET LOCAL session_replication_role = origin;
COMMIT;
"""


@unittest.skipUnless(
    PG_ENABLED,
    "set ASHARE_V3_N6_069_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6069PostgresIntegrationTests(unittest.TestCase):
    base_database = "n6_069_base"
    business_template = "n6_069_business"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        missing = [
            str(_FIXTURE.PG_BIN / binary)
            for binary in (
                "createdb",
                "initdb",
                "pg_ctl",
                "pg_restore",
                "postgres",
                "psql",
            )
            if not (_FIXTURE.PG_BIN / binary).is_file()
        ]
        if missing:
            raise AssertionError(
                "PostgreSQL 16 binaries missing: " + ", ".join(missing)
            )
        version = subprocess.run(
            [str(_FIXTURE.PG_BIN / "postgres"), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if version.returncode or " 16." not in version.stdout:
            raise AssertionError(
                f"PostgreSQL 16 required, got: {version.stdout}"
            )
        if (
            not str(_FIXTURE.SCHEMA_DUMP)
            or not _FIXTURE.SCHEMA_DUMP.is_absolute()
            or not _FIXTURE.SCHEMA_DUMP.is_file()
        ):
            raise AssertionError(
                "ASHARE_V3_N6_064_SCHEMA_DUMP must name an existing "
                "absolute offline schema-only dump"
            )
        if importlib.util.find_spec("psycopg") is None:
            raise AssertionError("psycopg is required when integration is enabled")

        cls.cluster = _FIXTURE._Pg16Cluster()
        try:
            cls.cluster.start()
            cls.cluster.create_database(cls.base_database)
            cls.cluster.restore_schema(cls.base_database)
            cls.cluster.apply_file(
                cls.base_database, MIGRATIONS[0], role="ashare_v3_user"
            )
            cls.cluster.run_sql(
                cls.base_database,
                _FIXTURE.MINIMAL_SEED_SQL,
                label="n6_069_minimal_seed",
            )
            cls.cluster.run_sql(
                cls.base_database,
                CURRENT_BATCH_SEED_SQL,
                label="n6_069_current_batch_seed",
            )
            for migration in MIGRATIONS[1:]:
                cls.cluster.apply_file(
                    cls.base_database, migration, role="ashare_v3_user"
                )

            cls.cluster.create_database(
                cls.business_template, template=cls.base_database
            )
            cls.cluster.apply_file(
                cls.business_template, FORWARD_PATH, role="ashare_v3_user"
            )
            cls.cluster.install_clock_shim(cls.business_template)
            cls._install_session_helper_clock_shim(cls.business_template)
            with cls.cluster.connect(cls.business_template) as connection:
                connection.execute(
                    "UPDATE public.user_session "
                    "SET expires_at='2026-08-31 00:00:00+08'::timestamptz"
                )
                connection.commit()
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    @classmethod
    def _install_session_helper_clock_shim(cls, database: str) -> None:
        from psycopg import sql

        with cls.cluster.connect(database) as connection:
            source = connection.execute(
                """
                SELECT prosrc
                FROM pg_catalog.pg_proc
                WHERE oid =
                  'public.n6_btrack_regular_trade_session_open()'
                  ::regprocedure
                """
            ).fetchone()["prosrc"]
            rewritten = source.replace(
                "pg_catalog.clock_timestamp()",
                "public.n6_064_test_now()",
            )
            if rewritten == source:
                raise AssertionError("session helper clock rewrite was a no-op")
            connection.execute("SET ROLE ashare_v3_user")
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
                ).format(sql.Literal(rewritten))
            )
            connection.commit()

    def _connect(
        self,
        database: str,
        *,
        role: str | None = None,
        clock: str | None = None,
    ):
        connection = self.cluster.connect(database)
        if clock:
            connection.execute(
                "SELECT pg_catalog.set_config('n6.test_clock', %s, false)",
                (clock,),
            )
        if role:
            if role not in _FIXTURE.ROLE_NAMES:
                connection.close()
                raise AssertionError(f"unexpected fixture role: {role}")
            connection.execute(f"SET ROLE {role}")
        return connection

    def _configure_signal(
        self,
        database: str,
        *,
        action_state: str,
        target_price: float | None,
        trade_date: str,
        source_id: int = 2,
    ) -> tuple[str, float]:
        if action_state not in {"eligible", "executed"}:
            raise AssertionError(action_state)
        reference_kind = (
            "trigger_price" if action_state == "eligible" else "action_price"
        )
        reference_price = 10.0 if action_state == "eligible" else 11.0
        payload = {
            "score": {"value": 80},
            "trade_date": trade_date,
            "action_state": action_state,
            reference_kind: f"{reference_price:.2f}",
        }
        card_payload = dict(payload, for_trade_date=trade_date)
        event_type = (
            "ActionEligible" if action_state == "eligible" else "ActionExecuted"
        )
        card_status = (
            "candidate" if action_state == "eligible" else "action_confirmed"
        )
        with self.cluster.connect(database) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "DELETE FROM public.stock_condition_display_basis "
                "WHERE stock_condition_display_basis_id <> 2"
            )
            connection.execute(
                """
                UPDATE public.stock_condition_display_basis
                SET for_trade_date=%s,
                    source_trade_date=%s,
                    prev_trade_date=%s,
                    run_id='fixture-condition-run'
                """,
                (trade_date, trade_date, trade_date),
            )
            connection.execute("SET session_replication_role=origin")
            connection.execute(
                """
                UPDATE public.user_signal_projection
                SET action_state=%s,
                    source_event_type=%s,
                    source_action_event_type=%s,
                    target_price=%s,
                    source_payload_json=%s::jsonb,
                    display_payload_json=%s::jsonb
                WHERE user_signal_projection_id=%s
                """,
                (
                    action_state,
                    event_type,
                    event_type,
                    target_price,
                    json.dumps({"trade_date": trade_date}),
                    json.dumps(payload),
                    source_id,
                ),
            )
            connection.execute(
                """
                UPDATE public.user_signal_card
                SET action_state=%s,
                    card_status=%s,
                    source_action_event_type=%s,
                    target_price=%s,
                    card_payload_json=%s::jsonb
                WHERE user_signal_card_id=%s
                """,
                (
                    action_state,
                    card_status,
                    event_type,
                    target_price,
                    json.dumps(card_payload),
                    source_id,
                ),
            )
            connection.commit()
        return reference_kind, reference_price

    def _clone_signal_source(self, database: str, *, source_id: int) -> None:
        with self.cluster.connect(database) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                """
                INSERT INTO public.user_signal_projection (
                  user_signal_projection_id, user_projection_run_id, user_id,
                  permission_scope, source_layer, source_event_id,
                  source_event_type, source_event_schema_version,
                  source_event_dedup_key, source_action_event_id,
                  source_action_run_id, asset_kind, identity_key, code, name,
                  direction, signal_type, projection_status,
                  source_payload_json, display_payload_json,
                  source_action_event_type, action_state, action_mark,
                  projection_policy
                ) OVERRIDING SYSTEM VALUE VALUES (
                  %s, 'fixture-projection-run', 2, 'self', 'N5_action',
                  %s, 'ActionEligible', 'fixture-v1', %s, %s,
                  'fixture-action-run', 'stock', 'stock:SH:600000',
                  '600000', 'Fixture Stock', 'buy', 'B_BUY', 'visible',
                  '{"trade_date":"20260720"}'::jsonb,
                  '{"score":{"value":80},"trade_date":"20260720","action_state":"eligible","trigger_price":"10.00"}'::jsonb,
                  'ActionEligible', 'eligible', 'normal', 'fixture-policy'
                )
                """,
                (
                    source_id,
                    f"fixture-event-eligible-{source_id}",
                    f"fixture-dedup-eligible-{source_id}",
                    f"fixture-action-event-eligible-{source_id}",
                ),
            )
            connection.execute(
                """
                INSERT INTO public.user_signal_card (
                  user_signal_card_id, user_signal_projection_id,
                  user_projection_run_id, user_id, card_type, card_status,
                  display_priority, title, asset_kind, identity_key, code,
                  name, direction, signal_type, source_action_run_id,
                  source_event_id, card_payload_json,
                  source_action_event_id, source_action_event_type,
                  action_state, action_mark, projection_policy
                ) OVERRIDING SYSTEM VALUE VALUES (
                  %s, %s, 'fixture-projection-run', 2, 'signal',
                  'candidate', 100, 'Fixture eligible buy add-on', 'stock',
                  'stock:SH:600000', '600000', 'Fixture Stock', 'buy',
                  'B_BUY', 'fixture-action-run', %s,
                  '{"score":{"value":80},"trade_date":"20260720","for_trade_date":"20260720","action_state":"eligible","trigger_price":"10.00"}'::jsonb,
                  %s, 'ActionEligible', 'eligible', 'normal',
                  'fixture-policy'
                )
                """,
                (
                    source_id,
                    source_id,
                    f"fixture-event-eligible-{source_id}",
                    f"fixture-action-event-eligible-{source_id}",
                ),
            )
            connection.execute("SET session_replication_role=origin")
            connection.commit()

    def _set_calendar(
        self,
        database: str,
        rows: tuple[tuple[str, bool], ...],
    ) -> None:
        with self.cluster.connect(database) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute("DELETE FROM public.common_trade_calendar")
            for trade_date, is_open in rows:
                connection.execute(
                    """
                    INSERT INTO public.common_trade_calendar (
                      trade_date, exchange, is_open, prev_trade_date,
                      next_trade_date, source, source_batch_id,
                      source_version
                    ) VALUES (
                      %s, 'SSE', %s, '20260717', '20991231',
                      'fixture', 'fixture-batch', 'fixture-v1'
                    )
                    """,
                    (trade_date, is_open),
                )
            connection.execute("SET session_replication_role=origin")
            connection.commit()

    def _insert_quote(
        self,
        database: str,
        *,
        quote_minute: str,
        fetched_at: str,
        price: float | None,
        quality_status: str = "passed",
        quality_reason: str = "ok",
    ) -> None:
        with self.cluster.connect(database) as connection:
            connection.execute(
                """
                INSERT INTO public.n6_virtual_quote_snapshot (
                  identity_key, exchange, stock_code, quote_minute,
                  provider_batch_id, provider_contract_version,
                  source_adapter, source_version, source_time_semantics,
                  requested_at, completed_at, batch_status, market,
                  current_price, last_close, day_open, day_high, day_low,
                  source_time_text, fetched_at, quality_status,
                  quality_reason
                ) VALUES (
                  'stock:SH:600000', 'SH', '600000', %s::timestamptz,
                  pg_catalog.gen_random_uuid(), '1.0.0', 'mootdx.std',
                  'fixture-v1',
                  'provider_intraday_time_without_trade_date',
                  %s::timestamptz, %s::timestamptz, 'passed', 1,
                  %s, %s, %s, %s, %s,
                  CASE WHEN %s::numeric IS NULL
                       THEN NULL ELSE 'fixture-time' END,
                  %s::timestamptz, %s, %s
                )
                """,
                (
                    quote_minute,
                    quote_minute,
                    fetched_at,
                    price,
                    price,
                    price,
                    price,
                    price,
                    price,
                    fetched_at,
                    quality_status,
                    quality_reason,
                ),
            )
            connection.commit()

    def _create_and_confirm(
        self,
        database: str,
        *,
        source_type: str,
        source_id: int,
        clock: str,
        suffix: str,
    ) -> tuple[int, dict]:
        with self._connect(
            database, role="n6_btrack_web", clock=clock
        ) as connection:
            created = connection.execute(
                """
                SELECT public.n6_btrack_proposal_create(
                  %s, %s, %s
                ) AS result
                """,
                (SESSION_HASH, source_type, source_id),
            ).fetchone()["result"]
            if not created or not created.get("ok"):
                connection.commit()
                return 0, dict(created or {})
            item = created["item"]
            proposal_id = int(item["proposal_id"])
            generation = item["confirmation_generation_token"]
            confirmed = connection.execute(
                """
                SELECT public.n6_btrack_proposal_confirm(
                  %s, %s, %s
                ) AS result
                """,
                (
                    SESSION_HASH,
                    proposal_id,
                    f"n6v3:{generation}:{suffix}",
                ),
            ).fetchone()["result"]
            self.assertTrue(confirmed["ok"], confirmed)
            self.assertEqual(confirmed["status"], "confirmed")
            connection.commit()
            return proposal_id, dict(confirmed)

    def _execute(
        self,
        database: str,
        *,
        proposal_id: int,
        executor_run_id: str,
        clock: str,
    ) -> dict:
        from ashare_v3.user.virtual_executor import (
            VirtualExecutorRequest,
            execute_proposal,
        )

        connection = self._connect(
            database, role="n6_virtual_executor", clock=clock
        )
        try:
            return execute_proposal(
                connection,
                VirtualExecutorRequest(
                    proposal_id=proposal_id,
                    executor_run_id=executor_run_id,
                ),
            )
        finally:
            connection.close()

    def _business_counts(self, database: str) -> dict[str, int]:
        with self.cluster.connect(database) as connection:
            return {
                table: int(
                    connection.execute(
                        f"SELECT count(*) AS n FROM public.{table}"
                    ).fetchone()["n"]
                )
                for table in BUSINESS_TABLES
            }

    def _account_counts(self, database: str) -> dict[str, int]:
        counts = self._business_counts(database)
        counts.pop("n6_virtual_trade_proposal")
        return counts

    def _function_fingerprint(self, database: str) -> str:
        with self.cluster.connect(database) as connection:
            row = connection.execute(
                """
                SELECT owner.rolname AS owner_name,
                       proc.prosecdef,
                       proc.provolatile,
                       proc.proconfig,
                       proc.proacl::text AS proacl,
                       pg_catalog.encode(
                         pg_catalog.sha256(
                           pg_catalog.convert_to(proc.prosrc, 'UTF8')
                         ), 'hex'
                       ) AS source_sha
                FROM pg_catalog.pg_proc proc
                JOIN pg_catalog.pg_roles owner
                  ON owner.oid=proc.proowner
                WHERE proc.oid =
                  'public.n6_executor_apply_claimed_proposal(bigint,text)'
                  ::regprocedure
                """
            ).fetchone()
        return sha256(
            json.dumps(
                dict(row), sort_keys=True, separators=(",", ":"), default=str
            ).encode()
        ).hexdigest()

    def test_forward_and_rollback_exact_round_trip_and_zero_business_dml(
        self,
    ) -> None:
        database = self.cluster.clone_database(
            self.base_database, "n6069_roundtrip"
        )
        before_fingerprint = self._function_fingerprint(database)
        before_counts = self._business_counts(database)
        self.cluster.apply_file(
            database, FORWARD_PATH, role="ashare_v3_user"
        )
        self.assertEqual(self._business_counts(database), before_counts)
        with self.cluster.connect(database) as connection:
            row = connection.execute(
                """
                SELECT owner.rolname AS owner_name,
                       proc.prosecdef,
                       proc.provolatile,
                       proc.proconfig,
                       pg_catalog.encode(
                         pg_catalog.sha256(
                           pg_catalog.convert_to(proc.prosrc, 'UTF8')
                         ), 'hex'
                       ) AS source_sha,
                       pg_catalog.has_function_privilege(
                         'n6_virtual_executor', proc.oid, 'EXECUTE'
                       ) AS executor_execute,
                       pg_catalog.has_function_privilege(
                         'n6_btrack_web', proc.oid, 'EXECUTE'
                       ) AS web_execute
                FROM pg_catalog.pg_proc proc
                JOIN pg_catalog.pg_roles owner
                  ON owner.oid=proc.proowner
                WHERE proc.oid =
                  'public.n6_executor_apply_claimed_proposal(bigint,text)'
                  ::regprocedure
                """
            ).fetchone()
        self.assertEqual(row["owner_name"], "ashare_v3_user")
        self.assertTrue(row["prosecdef"])
        self.assertEqual(row["provolatile"], "v")
        self.assertEqual(row["proconfig"], ["search_path=pg_catalog"])
        self.assertEqual(row["source_sha"], NEW_APPLY_SHA)
        self.assertTrue(row["executor_execute"])
        self.assertFalse(row["web_execute"])

        self.cluster.apply_file(
            database, ROLLBACK_PATH, role="ashare_v3_user"
        )
        self.assertEqual(
            self._function_fingerprint(database), before_fingerprint
        )
        self.assertEqual(self._business_counts(database), before_counts)

    def test_no_future_calendar_success_matrix_and_idempotency(self) -> None:
        matrix_index = 0
        for action_state in ("eligible", "executed"):
            for target_price in (None, 15.0):
                matrix_index += 1
                with self.subTest(
                    action_state=action_state, target_price=target_price
                ):
                    database = self.cluster.clone_database(
                        self.business_template, "n6069_matrix"
                    )
                    self._set_calendar(database, (("20260720", True),))
                    self._configure_signal(
                        database,
                        action_state=action_state,
                        target_price=target_price,
                        trade_date="20260720",
                    )
                    self._insert_quote(
                        database,
                        quote_minute="2026-07-20 09:59:00+08",
                        fetched_at="2026-07-20 09:59:30+08",
                        price=12.0,
                    )
                    proposal_id, _ = self._create_and_confirm(
                        database,
                        source_type="signal",
                        source_id=2,
                        clock="2026-07-20 10:00:00+08",
                        suffix=f"matrix-{matrix_index}",
                    )
                    self.assertGreater(proposal_id, 0)
                    result = self._execute(
                        database,
                        proposal_id=proposal_id,
                        executor_run_id=f"n6-069-matrix-{matrix_index}",
                        clock="2026-07-20 10:00:00+08",
                    )
                    self.assertTrue(result["ok"], result)
                    self.assertEqual(result["status"], "executed")
                    with self.cluster.connect(database) as connection:
                        row = connection.execute(
                            """
                            SELECT lot.open_trade_date,
                                   lot.available_trade_date,
                                   lot.lot_status,
                                   trade.filled_price,
                                   trade.filled_quantity,
                                   position.locked_target_price,
                                   position.target_price_status,
                                   position.available_quantity,
                                   position.locked_quantity
                            FROM public.n6_virtual_trade trade
                            JOIN public.n6_virtual_position position
                              ON position.virtual_account_id=
                                 trade.virtual_account_id
                             AND position.identity_key=trade.identity_key
                            JOIN public.n6_virtual_position_lot lot
                              ON lot.virtual_position_id=
                                 position.virtual_position_id
                             AND lot.source_virtual_trade_id=
                                 trade.virtual_trade_id
                            WHERE trade.source_proposal_id=%s
                            """,
                            (proposal_id,),
                        ).fetchone()
                    expected_quantity = math.floor(300000 / 12 / 100) * 100
                    self.assertEqual(str(row["open_trade_date"]), "2026-07-20")
                    self.assertEqual(
                        str(row["available_trade_date"]), "2026-07-21"
                    )
                    self.assertEqual(row["lot_status"], "locked_t1")
                    self.assertEqual(int(row["filled_quantity"]), expected_quantity)
                    self.assertEqual(int(row["available_quantity"]), 0)
                    self.assertEqual(
                        int(row["locked_quantity"]), expected_quantity
                    )
                    if target_price is None:
                        self.assertIsNone(row["locked_target_price"])
                        self.assertEqual(row["target_price_status"], "not_ready")
                    else:
                        self.assertAlmostEqual(
                            float(row["locked_target_price"]), target_price
                        )
                        self.assertEqual(row["target_price_status"], "frozen")

                    if matrix_index == 1:
                        before_replay = self._business_counts(database)
                        with self._connect(
                            database,
                            role="n6_virtual_executor",
                            clock="2026-07-20 10:00:00+08",
                        ) as connection:
                            replay = connection.execute(
                                """
                                SELECT public.n6_executor_apply_claimed_proposal(
                                  %s, %s
                                ) AS result
                                """,
                                (proposal_id, "n6-069-matrix-1"),
                            ).fetchone()["result"]
                            connection.commit()
                        self.assertTrue(replay["ok"], replay)
                        self.assertTrue(replay["idempotent"], replay)
                        self.assertEqual(
                            self._business_counts(database), before_replay
                        )

    def test_same_day_weekend_holiday_and_next_open_day(self) -> None:
        database = self.cluster.clone_database(
            self.business_template, "n6069_friday"
        )
        self._set_calendar(database, (("20260724", True),))
        self._configure_signal(
            database,
            action_state="eligible",
            target_price=18.0,
            trade_date="20260724",
        )
        self._insert_quote(
            database,
            quote_minute="2026-07-24 09:59:00+08",
            fetched_at="2026-07-24 09:59:30+08",
            price=12.0,
        )
        buy_id, _ = self._create_and_confirm(
            database,
            source_type="signal",
            source_id=2,
            clock="2026-07-24 10:00:00+08",
            suffix="friday-buy",
        )
        buy_result = self._execute(
            database,
            proposal_id=buy_id,
            executor_run_id="n6-069-friday-buy",
            clock="2026-07-24 10:00:00+08",
        )
        self.assertTrue(buy_result["ok"], buy_result)
        with self.cluster.connect(database) as connection:
            position = connection.execute(
                """
                SELECT position.virtual_position_id,
                       lot.open_trade_date,
                       lot.available_trade_date
                FROM public.n6_virtual_position position
                JOIN public.n6_virtual_position_lot lot
                  ON lot.virtual_position_id=position.virtual_position_id
                """
            ).fetchone()
        position_id = int(position["virtual_position_id"])
        self.assertEqual(str(position["open_trade_date"]), "2026-07-24")
        self.assertEqual(str(position["available_trade_date"]), "2026-07-25")

        before_same_day = self._business_counts(database)
        same_day_id, same_day = self._create_and_confirm(
            database,
            source_type="manual_position",
            source_id=position_id,
            clock="2026-07-24 10:01:00+08",
            suffix="same-day-sell",
        )
        self.assertEqual(same_day_id, 0)
        self.assertFalse(same_day["ok"], same_day)
        self.assertEqual(same_day["error"], "sellable_position_not_found")
        self.assertEqual(self._business_counts(database), before_same_day)

        self._set_calendar(
            database,
            (
                ("20260724", True),
                ("20260725", False),
                ("20260727", False),
            ),
        )
        for closed_clock in (
            "2026-07-25 10:00:00+08",
            "2026-07-27 10:00:00+08",
        ):
            before_closed = self._business_counts(database)
            closed_id, closed = self._create_and_confirm(
                database,
                source_type="manual_position",
                source_id=position_id,
                clock=closed_clock,
                suffix="closed-day",
            )
            self.assertEqual(closed_id, 0)
            self.assertFalse(closed["ok"], closed)
            self.assertIn(
                closed.get("error"),
                {"current_open_trade_date_required", "outside_trading_session"},
            )
            self.assertEqual(self._business_counts(database), before_closed)

        self._set_calendar(
            database,
            (
                ("20260724", True),
                ("20260725", False),
                ("20260727", False),
                ("20260728", True),
            ),
        )
        self._insert_quote(
            database,
            quote_minute="2026-07-28 09:59:00+08",
            fetched_at="2026-07-28 09:59:30+08",
            price=13.0,
        )
        sell_id, _ = self._create_and_confirm(
            database,
            source_type="manual_position",
            source_id=position_id,
            clock="2026-07-28 10:00:00+08",
            suffix="next-open-sell",
        )
        self.assertGreater(sell_id, 0)
        sell_result = self._execute(
            database,
            proposal_id=sell_id,
            executor_run_id="n6-069-next-open-sell",
            clock="2026-07-28 10:00:00+08",
        )
        self.assertTrue(sell_result["ok"], sell_result)
        self.assertEqual(sell_result["status"], "executed")
        with self.cluster.connect(database) as connection:
            sold = connection.execute(
                """
                SELECT position.quantity, position.position_status,
                       lot.remaining_quantity, lot.lot_status
                FROM public.n6_virtual_position position
                JOIN public.n6_virtual_position_lot lot
                  ON lot.virtual_position_id=position.virtual_position_id
                WHERE position.virtual_position_id=%s
                """,
                (position_id,),
            ).fetchone()
        self.assertEqual(int(sold["quantity"]), 0)
        self.assertEqual(sold["position_status"], "closed_virtual")
        self.assertEqual(int(sold["remaining_quantity"]), 0)
        self.assertEqual(sold["lot_status"], "closed")

    def test_add_on_preserves_mature_lot_target_and_stop_loss(self) -> None:
        database = self.cluster.clone_database(
            self.business_template, "n6069_addon"
        )
        self._set_calendar(database, (("20260720", True),))
        self._configure_signal(
            database,
            action_state="eligible",
            target_price=20.0,
            trade_date="20260720",
        )
        self._insert_quote(
            database,
            quote_minute="2026-07-20 09:58:00+08",
            fetched_at="2026-07-20 09:58:30+08",
            price=10.0,
        )
        first_id, _ = self._create_and_confirm(
            database,
            source_type="signal",
            source_id=2,
            clock="2026-07-20 09:59:00+08",
            suffix="first-buy",
        )
        first_result = self._execute(
            database,
            proposal_id=first_id,
            executor_run_id="n6-069-first-buy",
            clock="2026-07-20 09:59:00+08",
        )
        self.assertTrue(first_result["ok"], first_result)

        with self.cluster.connect(database) as connection:
            connection.execute(
                """
                UPDATE public.n6_virtual_position_lot
                SET open_trade_date='2026-07-19'::date,
                    available_trade_date='2026-07-20'::date,
                    lot_status='available'
                """
            )
            connection.execute(
                """
                UPDATE public.n6_virtual_position
                SET first_open_trade_date='2026-07-19'::date,
                    locked_target_price=20.0,
                    target_price_status='frozen',
                    target_price_source_signal_projection_id=2,
                    stop_loss_price=8.0,
                    stop_loss_status='frozen',
                    stop_loss_source_quote_snapshot_id=(
                      SELECT max(virtual_quote_snapshot_id)
                      FROM public.n6_virtual_quote_snapshot
                    ),
                    stop_loss_frozen_at='2026-07-20 09:59:00+08'::timestamptz,
                    stop_loss_effective_trade_date='2026-07-20'::date,
                    stop_loss_policy_version='fixture-stop-v1',
                    stop_loss_policy_hash='fixture-stop-v1',
                    available_quantity=quantity,
                    locked_quantity=0
                """
            )
            connection.commit()

        self._clone_signal_source(database, source_id=3)
        self._configure_signal(
            database,
            action_state="executed",
            target_price=None,
            trade_date="20260720",
            source_id=3,
        )
        self._insert_quote(
            database,
            quote_minute="2026-07-20 10:00:00+08",
            fetched_at="2026-07-20 10:00:30+08",
            price=11.0,
        )
        second_id, second_response = self._create_and_confirm(
            database,
            source_type="signal",
            source_id=3,
            clock="2026-07-20 10:01:00+08",
            suffix="second-buy",
        )
        self.assertGreater(second_id, 0, second_response)
        second_result = self._execute(
            database,
            proposal_id=second_id,
            executor_run_id="n6-069-second-buy",
            clock="2026-07-20 10:01:00+08",
        )
        self.assertTrue(second_result["ok"], second_result)
        with self.cluster.connect(database) as connection:
            position = connection.execute(
                """
                SELECT locked_target_price, target_price_status,
                       stop_loss_price, stop_loss_status,
                       available_quantity, locked_quantity
                FROM public.n6_virtual_position
                """
            ).fetchone()
            lots = connection.execute(
                """
                SELECT open_trade_date, available_trade_date,
                       remaining_quantity, lot_status
                FROM public.n6_virtual_position_lot
                ORDER BY virtual_position_lot_id
                """
            ).fetchall()
        self.assertEqual(len(lots), 2)
        self.assertEqual(str(lots[0]["available_trade_date"]), "2026-07-20")
        self.assertEqual(lots[0]["lot_status"], "available")
        self.assertEqual(str(lots[1]["open_trade_date"]), "2026-07-20")
        self.assertEqual(str(lots[1]["available_trade_date"]), "2026-07-21")
        self.assertEqual(lots[1]["lot_status"], "locked_t1")
        self.assertAlmostEqual(float(position["locked_target_price"]), 20.0)
        self.assertEqual(position["target_price_status"], "frozen")
        self.assertAlmostEqual(float(position["stop_loss_price"]), 8.0)
        self.assertEqual(position["stop_loss_status"], "frozen")
        self.assertEqual(
            int(position["available_quantity"]),
            int(lots[0]["remaining_quantity"]),
        )
        self.assertEqual(
            int(position["locked_quantity"]),
            int(lots[1]["remaining_quantity"]),
        )

    def test_quote_cash_and_scope_rejections_remain_fail_closed(self) -> None:
        cases = (
            "quote_missing",
            "quote_stale",
            "quote_invalid",
            "cash",
            "scope",
        )
        for case in cases:
            with self.subTest(case=case):
                database = self.cluster.clone_database(
                    self.business_template, f"n6069_reject_{case}"
                )
                self._set_calendar(database, (("20260720", True),))
                self._configure_signal(
                    database,
                    action_state="eligible",
                    target_price=15.0,
                    trade_date="20260720",
                )
                if case == "quote_stale":
                    self._insert_quote(
                        database,
                        quote_minute="2026-07-20 09:57:00+08",
                        fetched_at="2026-07-20 09:57:30+08",
                        price=12.0,
                    )
                elif case == "quote_invalid":
                    self._insert_quote(
                        database,
                        quote_minute="2026-07-20 09:59:00+08",
                        fetched_at="2026-07-20 09:59:30+08",
                        price=None,
                        quality_status="not_ready",
                        quality_reason="invalid_price",
                    )
                elif case != "quote_missing":
                    self._insert_quote(
                        database,
                        quote_minute="2026-07-20 09:59:00+08",
                        fetched_at="2026-07-20 09:59:30+08",
                        price=12.0,
                    )
                if case == "cash":
                    with self.cluster.connect(database) as connection:
                        connection.execute(
                            "UPDATE public.n6_virtual_cash_snapshot "
                            "SET available_cash=500, total_cash=500"
                        )
                        connection.commit()
                if case == "scope":
                    with self.cluster.connect(database) as connection:
                        connection.execute(
                            "DELETE FROM public.user_realtime_monitor_scope"
                        )
                        connection.commit()

                before = self._account_counts(database)
                proposal_id, response = self._create_and_confirm(
                    database,
                    source_type="signal",
                    source_id=2,
                    clock="2026-07-20 10:00:00+08",
                    suffix=f"reject-{case}",
                )
                if case == "scope":
                    self.assertEqual(proposal_id, 0)
                    self.assertFalse(response["ok"], response)
                    self.assertEqual(
                        response["error"], "signal_not_in_effective_scope"
                    )
                else:
                    self.assertGreater(proposal_id, 0)
                    result = self._execute(
                        database,
                        proposal_id=proposal_id,
                        executor_run_id=f"n6-069-reject-{case}",
                        clock="2026-07-20 10:00:00+08",
                    )
                    self.assertFalse(result["ok"], result)
                    self.assertEqual(
                        result["status"],
                        "quote_not_ready"
                        if case.startswith("quote_")
                        else "budget_below_one_lot",
                    )
                self.assertEqual(self._account_counts(database), before)


if __name__ == "__main__":
    unittest.main()
