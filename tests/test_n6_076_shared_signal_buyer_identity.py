"""Contract and isolated PG16 acceptance for N6 migration 076."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import unittest
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
FORWARD_PATH = ROOT / "sql/076_n6_shared_signal_buyer_identity_split.sql"
ROLLBACK_PATH = (
    ROOT / "sql/076_n6_shared_signal_buyer_identity_split_rollback.sql"
)
CONTRACT_PATH = (
    ROOT / "docs/N6_SHARED_SIGNAL_BUYER_IDENTITY_SPLIT_076_CONTRACT.json"
)
FORWARD = FORWARD_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

OLD_HASHES = {
    "helper": "a12ae3e8e8040ecb7459d08c69d263feb578b10b86d150fdb11488f6b7779d49",
    "create": "6c43e9c2426867d8d31d0827de83147893395ae923bb1b1bf83ea4b81654fd10",
    "explicit_claim": "3ba1cc351e64e8ae6aebafdb33f577f4cc7bd2a97d46c31203893994503f75cf",
    "claim_next": "1a4e1ad18a987cf5fe5c89135fc064970f54c443ffe5674b8449054696232c3f",
}
NEW_HASHES = {
    "helper": "fa772cb72c1751060032552865350dc6f8dedcdc413bcab5a4e5e789600bcd3a",
    "create": "a8a87ee9e97fdd3b8f865f90947fc6caf593d81f23174b0351365f8f3897cbff",
    "explicit_claim": "f5e8fadd1b27576726e819cdc696324732b1930652590c9c13dd8151297bb5e3",
    "claim_next": "f4bfb58c249441c5d4c4af72b163e22ce1f85edcc6abe634314b2c12805c78c6",
}
SIGNATURES = {
    "helper": (
        "public.n6_btrack_manual_signal_buy_current_scope("
        "bigint,text,bigint,bigint,bigint,text,text,numeric,text)"
    ),
    "create": "public.n6_btrack_proposal_create(text,text,bigint)",
    "explicit_claim": "public.n6_executor_claim_proposal(bigint,text)",
    "claim_next": "public.n6_executor_claim_next_proposal(text)",
}


def _dollar_block(text: str, tag: str) -> str:
    match = re.search(
        rf"\${re.escape(tag)}\$(.*?)\${re.escape(tag)}\$",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing dollar block: {tag}")
    return match.group(1)


def _function_source(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"CREATE (?:OR REPLACE )?FUNCTION public\.{re.escape(name)}\("
        r".*?AS \$function\$(.*?)\$function\$;",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function source: {name}")
    return match.group(1)


def _current_helper_source() -> str:
    source = _function_source(
        ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql",
        "n6_btrack_manual_signal_buy_current_scope",
    )
    migration = (
        ROOT / "sql/065_n6_btrack_current_date_batch_scope_fix.sql"
    ).read_text(encoding="utf-8")
    old = _dollar_block(migration, "old_batch_scope")
    new = _dollar_block(migration, "new_batch_scope")
    if source.count(old) != 1:
        raise AssertionError("helper source drift before 065")
    return source.replace(old, new)


def _current_create_source() -> str:
    source = _function_source(
        ROOT / "sql/063_n6_btrack_manual_actionable_buy.sql",
        "n6_btrack_proposal_create",
    )
    migration_064 = (
        ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql"
    ).read_text(encoding="utf-8")
    for old_tag, new_tag in (
        ("proposal_session_063", "proposal_session_064"),
        ("proposal_scope_guard_063", "proposal_scope_guard_064"),
        ("proposal_reference_guard_063", "proposal_reference_guard_064"),
        ("proposal_insert_063", "proposal_insert_064"),
        ("proposal_lineage_063", "proposal_lineage_064"),
        ("proposal_return_063", "proposal_return_064"),
        ("proposal_retry_anchor_064", "proposal_retry_064"),
    ):
        old = _dollar_block(migration_064, old_tag)
        new = _dollar_block(migration_064, new_tag)
        if source.count(old) != 1:
            raise AssertionError(f"create source drift before {old_tag}")
        source = source.replace(old, new)
    migration_066 = (
        ROOT / "sql/066_n6_btrack_regular_session_manual_buy.sql"
    ).read_text(encoding="utf-8")
    old = _dollar_block(migration_066, "create_session_065b")
    new = _dollar_block(migration_066, "create_session_066")
    if source.count(old) != 1:
        raise AssertionError("create source drift before 066")
    return source.replace(old, new)


def _current_explicit_claim_source() -> str:
    source = _function_source(
        ROOT / "sql/042_n6_b_track_db_role_policy_schema.sql",
        "n6_executor_claim_proposal",
    )
    migration_065a = (
        ROOT / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql"
    ).read_text(encoding="utf-8")
    source = source.replace(
        _dollar_block(migration_065a, "old_explicit"),
        _dollar_block(migration_065a, "new_explicit"),
    )
    migration_066 = (
        ROOT / "sql/066_n6_btrack_regular_session_manual_buy.sql"
    ).read_text(encoding="utf-8")
    return source.replace(
        _dollar_block(migration_066, "claim_explicit_065b"),
        _dollar_block(migration_066, "claim_explicit_066"),
    )


def _current_claim_next_source() -> str:
    source = _function_source(
        ROOT / "sql/048_n6_btrack_proposal_scope_and_executor_claim_next.sql",
        "n6_executor_claim_next_proposal",
    )
    migration_065a = (
        ROOT / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql"
    ).read_text(encoding="utf-8")
    source = source.replace(
        _dollar_block(migration_065a, "old_next"),
        _dollar_block(migration_065a, "new_next"),
    )
    migration_066 = (
        ROOT / "sql/066_n6_btrack_regular_session_manual_buy.sql"
    ).read_text(encoding="utf-8")
    source = source.replace(
        _dollar_block(migration_066, "claim_next_065b"),
        _dollar_block(migration_066, "claim_next_066"),
    )
    migration_075 = (
        ROOT / "sql/075_n6_executor_quote_ready_claim.sql"
    ).read_text(encoding="utf-8")
    return source.replace(
        _dollar_block(migration_075, "claim_fifo_066"),
        _dollar_block(migration_075, "claim_quote_ready_075"),
    )


OLD_SOURCES = {
    "helper": _current_helper_source(),
    "create": _current_create_source(),
    "explicit_claim": _current_explicit_claim_source(),
    "claim_next": _current_claim_next_source(),
}
REWRITE_TAGS = {
    "helper": ("buyer_owned_projection_065", "shared_source_buyer_split_076"),
    "create": ("create_owner_projection_075", "create_shared_signal_076"),
    "explicit_claim": ("explicit_claim_scope_075", "explicit_claim_scope_076"),
    "claim_next": ("claim_next_scope_075", "claim_next_scope_076"),
}
NEW_SOURCES = {
    name: source.replace(
        _dollar_block(FORWARD, REWRITE_TAGS[name][0]),
        _dollar_block(FORWARD, REWRITE_TAGS[name][1]),
    )
    for name, source in OLD_SOURCES.items()
}


class N6076StaticContractTests(unittest.TestCase):
    def test_identity_and_frozen_hashes(self) -> None:
        self.assertEqual(CONTRACT["layer_role"], "N6_user")
        self.assertEqual(CONTRACT["execution_mode"], "FULL_MODE")
        self.assertEqual(CONTRACT["kernel_check"], "ACCEPT")
        for name, source in OLD_SOURCES.items():
            self.assertEqual(sha256(source.encode()).hexdigest(), OLD_HASHES[name])
            old_tag, new_tag = REWRITE_TAGS[name]
            self.assertEqual(source.count(_dollar_block(FORWARD, old_tag)), 1)
            self.assertEqual(
                sha256(NEW_SOURCES[name].encode()).hexdigest(),
                NEW_HASHES[name],
            )
            self.assertEqual(
                _dollar_block(ROLLBACK, old_tag),
                _dollar_block(FORWARD, old_tag),
            )
            self.assertEqual(
                _dollar_block(ROLLBACK, new_tag),
                _dollar_block(FORWARD, new_tag),
            )
            self.assertEqual(
                NEW_SOURCES[name].replace(
                    _dollar_block(ROLLBACK, new_tag),
                    _dollar_block(ROLLBACK, old_tag),
                ),
                source,
            )

    def test_shared_source_and_buyer_authority_are_separate(self) -> None:
        helper = NEW_SOURCES["helper"]
        self.assertNotIn("projection.user_id = p_user_id", helper)
        for required in (
            "n6_ai_shared_signal_projection shared",
            "shared.shared_status = 'active'",
            "shared.source_signal_projection_id =",
            "shared.user_projection_run_id =",
            "shared.source_event_id = projection.source_event_id",
            "shared.source_outbox_id IS NOT DISTINCT FROM",
            "shared.source_action_event_id =",
            "shared.source_action_run_id =",
            "shared.for_trade_date =",
            "shared.identity_key = projection.identity_key",
            "shared.direction = projection.direction",
            "shared.signal_type = projection.signal_type",
            "shared.action_state = projection.action_state",
            "shared.action_mark IS NOT DISTINCT FROM",
            "shared.trigger_price IS NOT DISTINCT FROM",
            "shared.action_price IS NOT DISTINCT FROM",
            "principal.owner_user_id = p_user_id",
            "account.virtual_account_id = p_virtual_account_id",
            "monitor.user_id = p_user_id",
            "realtime_scope.user_id = p_user_id",
        ):
            self.assertIn(required, helper)

    def test_create_preserves_sell_owner_and_shared_buy(self) -> None:
        source = NEW_SOURCES["create"]
        self.assertIn("p.direction = 'buy'", source)
        self.assertIn("n6_ai_shared_signal_projection shared", source)
        self.assertIn("shared.shared_status = 'active'", source)
        self.assertIn("p.direction = 'sell'", source)
        self.assertIn(
            "p.user_id = (authority->>'user_id')::bigint",
            source,
        )
        self.assertIn("n6_btrack_manual_signal_buy_current_scope(", source)

    def test_claims_revalidate_manual_buy_and_keep_075_quote_gate(self) -> None:
        explicit = NEW_SOURCES["explicit_claim"]
        claim_next = NEW_SOURCES["claim_next"]
        self.assertIn("AND CASE", explicit)
        self.assertIn("THEN public.n6_btrack_manual_signal_buy_current_scope", explicit)
        self.assertIn("ELSE expires_at>pg_catalog.now()", explicit)
        self.assertIn("AND CASE", claim_next)
        self.assertIn("THEN public.n6_btrack_manual_signal_buy_current_scope", claim_next)
        self.assertIn("ELSE p.expires_at > pg_catalog.now()", claim_next)
        for preserved in (
            "FOR UPDATE SKIP LOCKED",
            "n6_virtual_quote_snapshot snapshot",
            "snapshot.quality_status = 'passed'",
            "snapshot.quality_reason = 'ok'",
            "interval '2 minutes'",
            "no_claimable_proposal",
        ):
            self.assertIn(preserved, claim_next)

    def test_confirm_retry_and_apply_still_call_the_helper(self) -> None:
        migration_064 = (
            ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql"
        ).read_text(encoding="utf-8")
        migration_065a = (
            ROOT
            / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql"
        ).read_text(encoding="utf-8")
        self.assertGreaterEqual(
            migration_064.count("n6_btrack_manual_signal_buy_current_scope("),
            5,
        )
        self.assertGreaterEqual(
            migration_065a.count("n6_btrack_manual_signal_buy_current_scope("),
            3,
        )
        self.assertFalse(CONTRACT["existing_data"]["claim_or_execute_existing_confirmed_proposals"])

    def test_zero_business_dml_and_api_identity_boundary(self) -> None:
        business_dml = re.compile(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+"
            r"public\.(?:n6_|user_signal_|user_projection_)",
            flags=re.IGNORECASE,
        )
        for sql_text in (FORWARD, ROLLBACK):
            self.assertIsNone(business_dml.search(sql_text))
            self.assertNotIn("ALTER TABLE", sql_text.upper())
            self.assertNotIn("DROP TABLE", sql_text.upper())
        self.assertEqual(
            CONTRACT["api"]["allowed_client_fields"],
            ["source_type", "source_id"],
        )
        self.assertFalse(CONTRACT["migration"]["business_row_dml"])
        self.assertFalse(CONTRACT["rollback"]["deletes_history"])


PG_ENABLED = os.environ.get("ASHARE_V3_N6_076_PG_INTEGRATION") == "1"
_SPEC = importlib.util.spec_from_file_location(
    "n6_064_pg_fixture_for_076",
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
SET check_function_bodies = off;

CREATE TABLE public.common_trade_calendar (
  trade_date text PRIMARY KEY,
  is_open boolean NOT NULL
);
CREATE TABLE public.user_projection_run (
  user_projection_run_id text PRIMARY KEY,
  source_layer text NOT NULL,
  status text NOT NULL,
  quality_summary_json jsonb NOT NULL
);
CREATE TABLE public.user_signal_projection (
  user_signal_projection_id bigint PRIMARY KEY,
  user_projection_run_id text NOT NULL
    REFERENCES public.user_projection_run(user_projection_run_id),
  user_id bigint NOT NULL,
  source_event_id text NOT NULL,
  source_outbox_id bigint,
  source_action_event_id text NOT NULL,
  source_action_run_id text NOT NULL,
  asset_kind text NOT NULL,
  identity_key text NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  direction text NOT NULL,
  signal_type text NOT NULL,
  action_state text,
  action_mark text,
  projection_status text NOT NULL,
  display_payload_json jsonb NOT NULL,
  source_payload_json jsonb NOT NULL,
  trace_json jsonb NOT NULL DEFAULT '{{}}'::jsonb
);
CREATE TABLE public.user_signal_card (
  user_signal_projection_id bigint NOT NULL,
  user_projection_run_id text NOT NULL,
  user_id bigint NOT NULL,
  asset_kind text NOT NULL,
  identity_key text NOT NULL,
  direction text NOT NULL,
  card_status text NOT NULL,
  card_payload_json jsonb NOT NULL
);
CREATE TABLE public.n6_ai_shared_signal_projection (
  source_signal_projection_id bigint PRIMARY KEY
    REFERENCES public.user_signal_projection(user_signal_projection_id),
  user_projection_run_id text NOT NULL
    REFERENCES public.user_projection_run(user_projection_run_id),
  source_event_id text NOT NULL,
  source_outbox_id bigint,
  source_action_event_id text NOT NULL,
  source_action_run_id text NOT NULL,
  for_trade_date date NOT NULL,
  asset_kind text NOT NULL,
  identity_key text NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  direction text NOT NULL,
  signal_type text NOT NULL,
  trigger_price numeric,
  action_price numeric,
  action_state text,
  action_mark text,
  shared_status text NOT NULL
    CHECK (shared_status IN ('active','superseded','rejected'))
);
CREATE TABLE public.v_n6_stock_condition_display_basis (
  source_trade_date text NOT NULL,
  for_trade_date text NOT NULL,
  run_id text NOT NULL,
  identity_key text NOT NULL
);
CREATE TABLE public.n6_principal (
  principal_id bigint PRIMARY KEY,
  principal_type text NOT NULL,
  owner_user_id bigint NOT NULL,
  principal_status text NOT NULL
);
CREATE TABLE public.n6_virtual_account (
  virtual_account_id bigint PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  virtual_account_status text NOT NULL
);
CREATE TABLE public.n6_virtual_position (
  virtual_account_id bigint,
  principal_id bigint,
  principal_type text,
  asset_kind text,
  identity_key text,
  position_status text,
  quantity numeric,
  holding_episode_no integer
);
CREATE TABLE public.user_monitor_stock (
  principal_id bigint,
  principal_type text,
  user_id bigint,
  asset_kind text,
  identity_key text,
  direction text,
  status text,
  quality_status text,
  valid_source_trade_date text,
  valid_for_trade_date text,
  valid_source_run_id text,
  source_run_id text,
  source_snapshot_json jsonb
);
CREATE TABLE public.user_realtime_monitor_scope (
  principal_id bigint,
  principal_type text,
  user_id bigint,
  asset_kind text,
  identity_key text,
  status text,
  deleted_at timestamptz,
  source_type text,
  source_snapshot_json jsonb
);
CREATE TABLE public.n6_virtual_trade_proposal (
  proposal_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  principal_id bigint,
  principal_type text,
  user_id bigint,
  actor_ai_user_id bigint,
  source_ai_decision_id bigint,
  virtual_account_id bigint,
  identity_key text,
  source_type text,
  proposal_side text,
  source_signal_projection_id bigint,
  source_virtual_position_id bigint,
  signal_reference_kind text,
  signal_reference_price numeric,
  source_lineage_json jsonb DEFAULT '{{}}'::jsonb,
  proposal_status text,
  expires_at timestamptz,
  executor_run_id text
);

CREATE FUNCTION public.n6_ai_shared_signal_projection_capture()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS $capture$
BEGIN
  RETURN NEW;
END
$capture$;
REVOKE ALL ON FUNCTION public.n6_ai_shared_signal_projection_capture()
  FROM PUBLIC;
CREATE TRIGGER trg_055_n6_ai_shared_signal_projection_capture
AFTER INSERT ON public.user_signal_projection
FOR EACH ROW EXECUTE FUNCTION
  public.n6_ai_shared_signal_projection_capture();

CREATE FUNCTION public.n6_btrack_regular_trade_session_open()
RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS 'SELECT true';
REVOKE ALL ON FUNCTION public.n6_btrack_regular_trade_session_open()
  FROM PUBLIC;

CREATE FUNCTION public.n6_btrack_manual_signal_buy_current_scope(
  p_principal_id bigint,p_principal_type text,p_user_id bigint,
  p_virtual_account_id bigint,p_signal_projection_id bigint,
  p_identity_key text,p_signal_reference_kind text,
  p_signal_reference_price numeric,p_for_trade_date text
) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS $helper${OLD_SOURCES['helper']}$helper$;
REVOKE ALL ON FUNCTION
  public.n6_btrack_manual_signal_buy_current_scope(
    bigint,text,bigint,bigint,bigint,text,text,numeric,text
  ) FROM PUBLIC;

CREATE FUNCTION public.n6_btrack_proposal_create(
  p_session_token_hash text,p_source_type text,p_source_id bigint
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS $create${OLD_SOURCES['create']}$create$;
REVOKE ALL ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint)
  TO n6_btrack_web;

CREATE FUNCTION public.n6_executor_claim_proposal(
  p_proposal_id bigint,p_executor_run_id text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS $explicit${OLD_SOURCES['explicit_claim']}$explicit$;
REVOKE ALL ON FUNCTION public.n6_executor_claim_proposal(bigint,text)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_executor_claim_proposal(bigint,text)
  TO n6_virtual_executor;

CREATE FUNCTION public.n6_executor_claim_next_proposal(
  p_executor_run_id text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog AS $next${OLD_SOURCES['claim_next']}$next$;
REVOKE ALL ON FUNCTION public.n6_executor_claim_next_proposal(text)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_executor_claim_next_proposal(text)
  TO n6_virtual_executor;
RESET ROLE;
"""


def _seed_sql(trade_date: str) -> str:
    return f"""
SET ROLE ashare_v3_user;
INSERT INTO public.common_trade_calendar VALUES ('{trade_date}', true);
INSERT INTO public.user_projection_run VALUES (
  'shared-run', 'N5_action', 'passed',
  '{{"b_track_signal_projection":"passed"}}'::jsonb
);
INSERT INTO public.v_n6_stock_condition_display_basis VALUES (
  '20260721', '{trade_date}', 'condition-run', 'stock:SH:600707'
);
INSERT INTO public.n6_principal VALUES
  (1, 'admin', 1, 'active'),
  (9, 'human_user', 8, 'active');
INSERT INTO public.n6_virtual_account VALUES
  (1, 1, 'admin', 'active'),
  (8, 9, 'human_user', 'active');
INSERT INTO public.user_signal_projection VALUES
  (501, 'shared-run', 1, 'event-eligible', NULL,
   'action-event-eligible', 'action-run', 'stock',
   'stock:SH:600707', '600707', '彩虹股份', 'buy', 'B_BUY',
   'eligible', 'normal', 'visible',
   '{{"for_trade_date":"{trade_date}","trade_date":"{trade_date}",'
     '"action_state":"eligible","trigger_price":"9.29"}}'::jsonb,
   '{{"trade_date":"{trade_date}"}}'::jsonb, '{{}}'::jsonb),
  (502, 'shared-run', 1, 'event-executed', NULL,
   'action-event-executed', 'action-run', 'stock',
   'stock:SH:600707', '600707', '彩虹股份', 'buy', 'B_BUY',
   'executed', 'normal', 'visible',
   '{{"for_trade_date":"{trade_date}","trade_date":"{trade_date}",'
     '"action_state":"executed","trigger_price":"9.29",'
     '"action_price":"9.38"}}'::jsonb,
   '{{"trade_date":"{trade_date}"}}'::jsonb, '{{}}'::jsonb);
INSERT INTO public.user_signal_card VALUES
  (501, 'shared-run', 1, 'stock', 'stock:SH:600707', 'buy',
   'candidate',
   '{{"for_trade_date":"{trade_date}","trade_date":"{trade_date}",'
     '"action_state":"eligible","trigger_price":"9.29"}}'::jsonb),
  (502, 'shared-run', 1, 'stock', 'stock:SH:600707', 'buy',
   'action_confirmed',
   '{{"for_trade_date":"{trade_date}","trade_date":"{trade_date}",'
     '"action_state":"executed","trigger_price":"9.29",'
     '"action_price":"9.38"}}'::jsonb);
INSERT INTO public.n6_ai_shared_signal_projection VALUES
  (501, 'shared-run', 'event-eligible', NULL,
   'action-event-eligible', 'action-run', '{trade_date}'::date,
   'stock', 'stock:SH:600707', '600707', '彩虹股份', 'buy',
   'B_BUY', 9.29, NULL, 'eligible', 'normal', 'active'),
  (502, 'shared-run', 'event-executed', NULL,
   'action-event-executed', 'action-run', '{trade_date}'::date,
   'stock', 'stock:SH:600707', '600707', '彩虹股份', 'buy',
   'B_BUY', 9.29, 9.38, 'executed', 'normal', 'active');
INSERT INTO public.user_realtime_monitor_scope VALUES
  (1, 'admin', 1, 'stock', 'stock:SH:600707', 'active', NULL,
   'single_row', '{{"identity_key":"stock:SH:600707"}}'::jsonb),
  (9, 'human_user', 8, 'stock', 'stock:SH:600707', 'active', NULL,
   'single_row', '{{"identity_key":"stock:SH:600707"}}'::jsonb);
RESET ROLE;
"""


@unittest.skipUnless(
    PG_ENABLED,
    "set ASHARE_V3_N6_076_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6076PostgresIntegrationTests(unittest.TestCase):
    database = "n6_076"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.trade_date = datetime.now(ZoneInfo("Asia/Shanghai")).strftime(
            "%Y%m%d"
        )
        cls.cluster = _FIXTURE._Pg16Cluster()
        try:
            cls.cluster.start()
            cls.cluster.create_database(cls.database)
            cls.cluster.run_sql(
                cls.database, _schema_sql(), label="n6_076_schema"
            )
            cls.cluster.run_sql(
                cls.database,
                _seed_sql(cls.trade_date),
                label="n6_076_seed",
            )
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def _hashes(self) -> dict[str, str]:
        with self.cluster.connect(self.database) as connection:
            return {
                name: sha256(
                    connection.execute(
                        "SELECT prosrc FROM pg_catalog.pg_proc "
                        "WHERE oid=%s::pg_catalog.regprocedure",
                        (signature,),
                    ).fetchone()["prosrc"].encode()
                ).hexdigest()
                for name, signature in SIGNATURES.items()
            }

    def _digest(self) -> str:
        tables = (
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "n6_ai_shared_signal_projection",
            "n6_principal",
            "n6_virtual_account",
            "user_realtime_monitor_scope",
            "n6_virtual_trade_proposal",
        )
        payload: list[object] = []
        with self.cluster.connect(self.database) as connection:
            for table in tables:
                rows = connection.execute(
                    f"SELECT row_to_json(t) AS row FROM public.{table} t "
                    "ORDER BY row_to_json(t)::text"
                ).fetchall()
                payload.append([row["row"] for row in rows])
        return sha256(
            json.dumps(
                payload, sort_keys=True, default=str, ensure_ascii=False
            ).encode()
        ).hexdigest()

    def _scope(
        self,
        *,
        principal_id: int,
        principal_type: str,
        user_id: int,
        account_id: int,
        projection_id: int,
        reference_kind: str,
        reference_price: str,
    ) -> bool:
        with self.cluster.connect(self.database) as connection:
            return bool(
                connection.execute(
                    "SELECT public.n6_btrack_manual_signal_buy_current_scope("
                    "%s,%s,%s,%s,%s,'stock:SH:600707',%s,%s,%s) AS ok",
                    (
                        principal_id,
                        principal_type,
                        user_id,
                        account_id,
                        projection_id,
                        reference_kind,
                        reference_price,
                        self.trade_date,
                    ),
                ).fetchone()["ok"]
            )

    def test_forward_shared_buyer_matrix_and_exact_rollback(self) -> None:
        baseline_digest = self._digest()
        self.assertEqual(self._hashes(), OLD_HASHES)
        self.assertTrue(
            self._scope(
                principal_id=1,
                principal_type="admin",
                user_id=1,
                account_id=1,
                projection_id=501,
                reference_kind="trigger_price",
                reference_price="9.29",
            )
        )
        self.assertFalse(
            self._scope(
                principal_id=9,
                principal_type="human_user",
                user_id=8,
                account_id=8,
                projection_id=501,
                reference_kind="trigger_price",
                reference_price="9.29",
            )
        )

        self.cluster.apply_file(
            self.database, FORWARD_PATH, role="ashare_v3_user"
        )
        self.assertEqual(self._hashes(), NEW_HASHES)
        self.assertEqual(self._digest(), baseline_digest)
        for projection_id, kind, price in (
            (501, "trigger_price", "9.29"),
            (502, "action_price", "9.38"),
        ):
            for principal_id, principal_type, user_id, account_id in (
                (1, "admin", 1, 1),
                (9, "human_user", 8, 8),
            ):
                self.assertTrue(
                    self._scope(
                        principal_id=principal_id,
                        principal_type=principal_type,
                        user_id=user_id,
                        account_id=account_id,
                        projection_id=projection_id,
                        reference_kind=kind,
                        reference_price=price,
                    )
                )

        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "UPDATE public.n6_ai_shared_signal_projection "
                "SET shared_status='superseded' "
                "WHERE source_signal_projection_id=501"
            )
        self.assertFalse(
            self._scope(
                principal_id=9,
                principal_type="human_user",
                user_id=8,
                account_id=8,
                projection_id=501,
                reference_kind="trigger_price",
                reference_price="9.29",
            )
        )
        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "UPDATE public.n6_ai_shared_signal_projection "
                "SET shared_status='active',trigger_price=9.30 "
                "WHERE source_signal_projection_id=501"
            )
        self.assertFalse(
            self._scope(
                principal_id=9,
                principal_type="human_user",
                user_id=8,
                account_id=8,
                projection_id=501,
                reference_kind="trigger_price",
                reference_price="9.29",
            )
        )
        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "UPDATE public.n6_ai_shared_signal_projection "
                "SET trigger_price=9.29 "
                "WHERE source_signal_projection_id=501"
            )
            connection.execute(
                "DELETE FROM public.user_realtime_monitor_scope "
                "WHERE principal_id=9"
            )
        self.assertFalse(
            self._scope(
                principal_id=9,
                principal_type="human_user",
                user_id=8,
                account_id=8,
                projection_id=501,
                reference_kind="trigger_price",
                reference_price="9.29",
            )
        )
        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO public.user_realtime_monitor_scope VALUES "
                "(9,'human_user',8,'stock','stock:SH:600707','active',"
                "NULL,'single_row','{\"identity_key\":"
                "\"stock:SH:600707\"}'::jsonb)"
            )

        self.assertEqual(self._digest(), baseline_digest)
        self.cluster.apply_file(
            self.database, ROLLBACK_PATH, role="ashare_v3_user"
        )
        self.assertEqual(self._hashes(), OLD_HASHES)
        self.assertEqual(self._digest(), baseline_digest)
        self.assertFalse(
            self._scope(
                principal_id=9,
                principal_type="human_user",
                user_id=8,
                account_id=8,
                projection_id=501,
                reference_kind="trigger_price",
                reference_price="9.29",
            )
        )


if __name__ == "__main__":
    unittest.main()
