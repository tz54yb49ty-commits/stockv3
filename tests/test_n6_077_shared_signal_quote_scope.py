"""N6 077 shared-signal human/admin quote-scope acceptance."""

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
FORWARD_PATH = ROOT / "sql/077_n6_shared_signal_quote_scope.sql"
ROLLBACK_PATH = ROOT / "sql/077_n6_shared_signal_quote_scope_rollback.sql"
CONTRACT_PATH = ROOT / "docs/N6_SHARED_SIGNAL_QUOTE_SCOPE_077_CONTRACT.json"
FORWARD = FORWARD_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

OLD_SCOPE_SHA = "856bfc57439d85e9f1cab84a93f25dfcf4e4a50274e30c60cfac0e7110b527b1"
NEW_SCOPE_SHA = "c7e88b727f49a54aeedcba5bd32bd1e63d9838c916dd221a0b299c03f410de76"
PENDING_SHA = "f7d29a064b4dc149dd6a34a7ace9c5f1583679784ecbfc6675f41304060de14e"
HELPER_SHA = "fa772cb72c1751060032552865350dc6f8dedcdc413bcab5a4e5e789600bcd3a"
SIGNATURES = {
    "scope": "public.n6_quote_writer_scope(timestamptz)",
    "pending": "public.n6_quote_writer_pending_scope(timestamptz)",
    "helper": (
        "public.n6_btrack_manual_signal_buy_current_scope("
        "bigint,text,bigint,bigint,bigint,text,text,numeric,text)"
    ),
}


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


def _dollar_block(text: str, tag: str) -> str:
    match = re.search(
        rf"\${re.escape(tag)}\$(.*?)\${re.escape(tag)}\$",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing dollar block: {tag}")
    return match.group(1)


OLD_SCOPE = _function_source(
    ROOT / "sql/068_n6_quote_writer_mootdx_compat.sql",
    "n6_quote_writer_scope",
)
PENDING_SCOPE = _function_source(
    ROOT / "sql/051_n6_virtual_quote_writer_policy.sql",
    "n6_quote_writer_pending_scope",
)
NEW_SCOPE = OLD_SCOPE.replace(
    _dollar_block(FORWARD, "human_owned_source_068"),
    _dollar_block(FORWARD, "human_shared_source_077"),
).replace(
    _dollar_block(FORWARD, "human_owned_gate_068"),
    _dollar_block(FORWARD, "human_shared_gate_077"),
)


class N6077StaticContractTests(unittest.TestCase):
    def test_mode_baseline_and_frozen_function_hashes(self) -> None:
        self.assertEqual(CONTRACT["layer_role"], "N6_user")
        self.assertEqual(CONTRACT["execution_mode"], "FULL_MODE")
        self.assertEqual(CONTRACT["risk_level"], "medium")
        self.assertEqual(CONTRACT["baseline"]["highest_migration"], "076")
        self.assertEqual(sha256(OLD_SCOPE.encode()).hexdigest(), OLD_SCOPE_SHA)
        self.assertEqual(sha256(NEW_SCOPE.encode()).hexdigest(), NEW_SCOPE_SHA)
        self.assertEqual(sha256(PENDING_SCOPE.encode()).hexdigest(), PENDING_SHA)
        self.assertEqual(CONTRACT["baseline"]["helper_source_sha256"], HELPER_SHA)
        self.assertEqual(
            CONTRACT["rollback"]["restores_scope_source_sha256"],
            OLD_SCOPE_SHA,
        )

    def test_both_scope_entry_points_are_located(self) -> None:
        self.assertIn("source.user_id = proposal.user_id", OLD_SCOPE)
        self.assertNotIn("source.user_id = proposal.user_id", NEW_SCOPE)
        self.assertEqual(
            PENDING_SCOPE.count(
                "public.n6_quote_writer_scope(p_quote_minute)"
            ),
            1,
        )
        self.assertNotIn("user_signal_projection source", PENDING_SCOPE)
        self.assertTrue(
            CONTRACT["scope_compatibility"]["pending_scope_delegates_to_scope"]
        )
        self.assertFalse(
            CONTRACT["scope_compatibility"][
                "pending_scope_function_body_changes"
            ]
        )

    def test_human_shared_source_reuses_076_helper(self) -> None:
        for required in (
            "n6_ai_shared_signal_projection shared_source",
            "shared_source.shared_status = 'active'",
            "shared_source.source_signal_projection_id =",
            "shared_source.asset_kind = proposal.asset_kind",
            "shared_source.identity_key = proposal.identity_key",
            "shared_source.direction = proposal.proposal_side",
            "public.n6_btrack_manual_signal_buy_current_scope(",
            "proposal.user_id",
            "proposal.principal_id",
            "proposal.virtual_account_id",
            "proposal.source_lineage_json->>'for_trade_date'",
        ):
            self.assertIn(required, NEW_SCOPE)
        self.assertNotIn("user_signal_projection source", NEW_SCOPE)
        self.assertNotIn("source.user_id = proposal.user_id", NEW_SCOPE)
        self.assertIn("proposal.proposal_status = 'pending'", NEW_SCOPE)
        self.assertIn("proposal.proposal_status = 'confirmed'", NEW_SCOPE)

    def test_ai_branch_and_market_guards_are_byte_preserved(self) -> None:
        def block(source: str, start: str, end: str) -> str:
            return source[source.index(start):source.index(end)]

        self.assertEqual(
            block(
                OLD_SCOPE,
                "    LEFT JOIN public.n6_ai_shared_signal_projection ai_source",
                "    WHERE proposal.asset_kind",
            ),
            block(
                NEW_SCOPE,
                "    LEFT JOIN public.n6_ai_shared_signal_projection ai_source",
                "    WHERE proposal.asset_kind",
            ),
        )
        for required in (
            "proposal.source_ai_decision_id IS NOT NULL",
            "ai_source.shared_status = 'active'",
            "common_trade_calendar calendar",
            "calendar.is_open = true",
            "BETWEEN time '09:30' AND time '11:30'",
            "BETWEEN time '13:00' AND time '15:00'",
            "p_quote_minute = (",
        ):
            self.assertIn(required, NEW_SCOPE)

    def test_forward_rollback_are_exact_inverse_and_acl_pinned(self) -> None:
        restored = NEW_SCOPE.replace(
            _dollar_block(ROLLBACK, "human_shared_source_077"),
            _dollar_block(ROLLBACK, "human_owned_source_068"),
        ).replace(
            _dollar_block(ROLLBACK, "human_shared_gate_077"),
            _dollar_block(ROLLBACK, "human_owned_gate_068"),
        )
        self.assertEqual(restored, OLD_SCOPE)
        for sql in (FORWARD, ROLLBACK):
            for marker in (
                "n6_quote_writer_pending_scope(timestamptz)",
                "n6_btrack_manual_signal_buy_current_scope(",
                "prosecdef",
                "provolatile",
                "proparallel",
                "search_path=pg_catalog",
                "pg_catalog.aclexplode",
                "n6_quote_writer",
                "business_summary",
            ):
                self.assertIn(marker, sql)

    def test_function_only_zero_business_dml(self) -> None:
        business_dml = re.compile(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+"
            r"public\.(?:n6_virtual_trade_proposal|n6_virtual_order|"
            r"n6_virtual_trade|n6_virtual_cash|n6_virtual_position)",
            flags=re.IGNORECASE,
        )
        for sql in (FORWARD, ROLLBACK):
            self.assertIsNone(business_dml.search(sql))
            self.assertNotRegex(sql, r"(?i)\bALTER\s+TABLE\b")
            self.assertNotRegex(sql, r"(?i)\bCREATE\s+TABLE\b")
            self.assertNotRegex(sql, r"(?i)\bDROP\s+TABLE\b")
        self.assertFalse(CONTRACT["migration"]["business_row_dml"])
        self.assertFalse(CONTRACT["migration"]["runtime_code_change"])
        self.assertFalse(
            CONTRACT["side_effect_boundary"]["claims_or_executes_proposal"]
        )


PG_ENABLED = os.environ.get("ASHARE_V3_N6_077_PG_INTEGRATION") == "1"

_FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "n6_064_pg_fixture_for_077",
    ROOT / "tests/test_n6_064_postgres_integration.py",
)
if _FIXTURE_SPEC is None or _FIXTURE_SPEC.loader is None:
    raise AssertionError("cannot load isolated PostgreSQL fixture")
_FIXTURE = importlib.util.module_from_spec(_FIXTURE_SPEC)
_FIXTURE_SPEC.loader.exec_module(_FIXTURE)

_076_SPEC = importlib.util.spec_from_file_location(
    "n6_076_fixture_for_077",
    ROOT / "tests/test_n6_076_shared_signal_buyer_identity.py",
)
if _076_SPEC is None or _076_SPEC.loader is None:
    raise AssertionError("cannot load 076 fixture")
_076 = importlib.util.module_from_spec(_076_SPEC)
_076_SPEC.loader.exec_module(_076)


def _quote_schema_sql() -> str:
    return f"""
SET ROLE ashare_v3_user;
ALTER TABLE public.n6_principal ALTER COLUMN owner_user_id DROP NOT NULL;
ALTER TABLE public.n6_virtual_trade_proposal
  ADD COLUMN asset_kind text DEFAULT 'stock',
  ADD COLUMN source_id text;
CREATE TABLE public.n6_ai_user (
  ai_user_id bigint PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  status text NOT NULL
);
CREATE TABLE public.n6_virtual_quote_snapshot (
  identity_key text NOT NULL,
  quote_minute timestamptz NOT NULL
);
CREATE FUNCTION public.n6_quote_writer_scope(p_quote_minute timestamptz)
RETURNS TABLE (
  principal_id bigint, principal_type text,
  virtual_account_id bigint, identity_key text
)
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog
AS $scope${OLD_SCOPE}$scope$;
REVOKE ALL ON FUNCTION public.n6_quote_writer_scope(timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_quote_writer_scope(timestamptz)
  TO n6_quote_writer;
CREATE FUNCTION public.n6_quote_writer_pending_scope(p_quote_minute timestamptz)
RETURNS TABLE (
  principal_id bigint, principal_type text,
  virtual_account_id bigint, identity_key text
)
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog
AS $pending${PENDING_SCOPE}$pending$;
REVOKE ALL ON FUNCTION public.n6_quote_writer_pending_scope(timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.n6_quote_writer_pending_scope(timestamptz)
  TO n6_quote_writer;
RESET ROLE;
"""


def _quote_seed_sql(trade_date: str) -> str:
    return f"""
SET ROLE ashare_v3_user;
INSERT INTO public.n6_ai_user VALUES (10, 10, 'ai_user', 'active');
INSERT INTO public.n6_principal VALUES (10, 'ai_user', NULL, 'active');
INSERT INTO public.n6_virtual_account VALUES (10, 10, 'ai_user', 'active');
INSERT INTO public.n6_virtual_trade_proposal (
  proposal_id, principal_id, principal_type, user_id,
  actor_ai_user_id, source_ai_decision_id, virtual_account_id,
  asset_kind, identity_key, source_type, source_id, proposal_side,
  source_signal_projection_id, source_virtual_position_id,
  signal_reference_kind, signal_reference_price, source_lineage_json,
  proposal_status, expires_at
) VALUES
  (36, 1, 'admin', 1, NULL, NULL, 1, 'stock',
   'stock:SH:600707', 'signal', '501', 'buy', 501, NULL,
   'trigger_price', 9.29, '{{"for_trade_date":"{trade_date}"}}',
   'confirmed', pg_catalog.clock_timestamp() + interval '10 minutes'),
  (37, 9, 'human_user', 8, NULL, NULL, 8, 'stock',
   'stock:SH:600707', 'signal', '501', 'buy', 501, NULL,
   'trigger_price', 9.29, '{{"for_trade_date":"{trade_date}"}}',
   'confirmed', pg_catalog.clock_timestamp() + interval '10 minutes'),
  (38, 10, 'ai_user', NULL, 10, 7001, 10, 'stock',
   'stock:SH:600707', 'signal', '502', 'buy', 502, NULL,
   'action_price', 9.38, '{{"for_trade_date":"{trade_date}"}}',
   'confirmed', pg_catalog.clock_timestamp() + interval '10 minutes');
RESET ROLE;
"""


@unittest.skipUnless(
    PG_ENABLED,
    "set ASHARE_V3_N6_077_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6077PostgresIntegrationTests(unittest.TestCase):
    database = "n6_077"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        shanghai_now = datetime.now(ZoneInfo("Asia/Shanghai"))
        cls.trade_date = shanghai_now.strftime("%Y%m%d")
        cls.quote_minute = shanghai_now.replace(second=0, microsecond=0)
        cls.cluster = _FIXTURE._Pg16Cluster()
        try:
            cls.cluster.start()
            cls.cluster.create_database(cls.database)
            cls.cluster.run_sql(
                cls.database, _076._schema_sql(), label="n6_077_base_schema"
            )
            cls.cluster.run_sql(
                cls.database,
                _076._seed_sql(cls.trade_date),
                label="n6_077_base_seed",
            )
            cls.cluster.apply_file(
                cls.database,
                ROOT / "sql/076_n6_shared_signal_buyer_identity_split.sql",
                role="ashare_v3_user",
            )
            cls.cluster.run_sql(
                cls.database, _quote_schema_sql(), label="n6_077_quote_schema"
            )
            cls.cluster.run_sql(
                cls.database,
                _quote_seed_sql(cls.trade_date),
                label="n6_077_quote_seed",
            )
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def _function_evidence(self) -> dict[str, dict[str, object]]:
        evidence: dict[str, dict[str, object]] = {}
        with self.cluster.connect(self.database) as connection:
            for name, signature in SIGNATURES.items():
                row = connection.execute(
                    "SELECT p.prosrc,p.prosecdef,p.provolatile,p.proparallel,"
                    "p.proconfig,owner.rolname AS owner_name,"
                    "COALESCE(array_agg(COALESCE(role.rolname,'PUBLIC') || ':' || "
                    "acl.privilege_type ORDER BY COALESCE(role.rolname,'PUBLIC')),"
                    "ARRAY[]::text[]) AS acl "
                    "FROM pg_catalog.pg_proc p "
                    "JOIN pg_catalog.pg_roles owner ON owner.oid=p.proowner "
                    "LEFT JOIN LATERAL pg_catalog.aclexplode(COALESCE("
                    "p.proacl,pg_catalog.acldefault('f',p.proowner))) acl ON true "
                    "LEFT JOIN pg_catalog.pg_roles role ON role.oid=acl.grantee "
                    "WHERE p.oid=%s::pg_catalog.regprocedure "
                    "GROUP BY p.oid,owner.rolname",
                    (signature,),
                ).fetchone()
                evidence[name] = {
                    "sha": sha256(row["prosrc"].encode()).hexdigest(),
                    "owner": row["owner_name"],
                    "security_definer": row["prosecdef"],
                    "volatility": row["provolatile"],
                    "parallel": row["proparallel"],
                    "config": row["proconfig"],
                    "acl": row["acl"],
                }
        return evidence

    def _scope(self, function: str = "n6_quote_writer_scope") -> set[tuple]:
        if function not in {"n6_quote_writer_scope", "n6_quote_writer_pending_scope"}:
            raise AssertionError(function)
        with self.cluster.connect(self.database) as connection:
            rows = connection.execute(
                f"SELECT * FROM public.{function}(%s) ORDER BY 1,2,3,4",
                (self.quote_minute,),
            ).fetchall()
        return {
            (
                row["principal_id"], row["principal_type"],
                row["virtual_account_id"], row["identity_key"],
            )
            for row in rows
        }

    def _proposal_digest(self) -> str:
        with self.cluster.connect(self.database) as connection:
            rows = connection.execute(
                "SELECT row_to_json(p) AS row "
                "FROM public.n6_virtual_trade_proposal p "
                "ORDER BY proposal_id"
            ).fetchall()
        return sha256(
            json.dumps(
                [row["row"] for row in rows],
                sort_keys=True,
                default=str,
                ensure_ascii=False,
            ).encode()
        ).hexdigest()

    def test_proposal_37_forward_fail_closed_matrix_and_roundtrip(self) -> None:
        minute_time = self.quote_minute.time()
        in_session = (
            datetime.strptime("09:30", "%H:%M").time()
            <= minute_time
            <= datetime.strptime("11:30", "%H:%M").time()
        ) or (
            datetime.strptime("13:00", "%H:%M").time()
            <= minute_time
            <= datetime.strptime("15:00", "%H:%M").time()
        )
        if not in_session:
            self.skipTest("isolated scope execution requires Shanghai session")

        old_expected = {
            (1, "admin", 1, "stock:SH:600707"),
            (10, "ai_user", 10, "stock:SH:600707"),
        }
        new_expected = old_expected | {
            (9, "human_user", 8, "stock:SH:600707")
        }
        baseline_digest = self._proposal_digest()
        baseline_evidence = self._function_evidence()
        self.assertEqual(baseline_evidence["scope"]["sha"], OLD_SCOPE_SHA)
        self.assertEqual(baseline_evidence["pending"]["sha"], PENDING_SHA)
        self.assertEqual(baseline_evidence["helper"]["sha"], HELPER_SHA)
        self.assertEqual(self._scope(), old_expected)
        self.assertEqual(self._scope("n6_quote_writer_pending_scope"), old_expected)

        self.cluster.apply_file(
            self.database, FORWARD_PATH, role="ashare_v3_user"
        )
        forward_evidence = self._function_evidence()
        self.assertEqual(forward_evidence["scope"]["sha"], NEW_SCOPE_SHA)
        self.assertEqual(
            forward_evidence["pending"], baseline_evidence["pending"]
        )
        self.assertEqual(forward_evidence["helper"], baseline_evidence["helper"])
        self.assertEqual(self._proposal_digest(), baseline_digest)
        self.assertEqual(self._scope(), new_expected)
        self.assertEqual(self._scope("n6_quote_writer_pending_scope"), new_expected)

        ai_row = (10, "ai_user", 10, "stock:SH:600707")
        human_row = (9, "human_user", 8, "stock:SH:600707")
        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "UPDATE public.n6_ai_shared_signal_projection "
                "SET shared_status='superseded' "
                "WHERE source_signal_projection_id=501"
            )
        self.assertNotIn(human_row, self._scope())
        self.assertIn(ai_row, self._scope())

        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "UPDATE public.n6_ai_shared_signal_projection "
                "SET shared_status='active',trigger_price=9.30 "
                "WHERE source_signal_projection_id=501"
            )
        self.assertNotIn(human_row, self._scope())

        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "UPDATE public.n6_ai_shared_signal_projection "
                "SET trigger_price=9.29,source_action_run_id='drift' "
                "WHERE source_signal_projection_id=501"
            )
        self.assertNotIn(human_row, self._scope())

        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "UPDATE public.n6_ai_shared_signal_projection "
                "SET source_action_run_id='action-run' "
                "WHERE source_signal_projection_id=501"
            )
            connection.execute(
                "DELETE FROM public.user_realtime_monitor_scope "
                "WHERE principal_id=9"
            )
        self.assertNotIn(human_row, self._scope())
        self.assertIn(ai_row, self._scope())

        with self.cluster.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO public.user_realtime_monitor_scope VALUES "
                "(9,'human_user',8,'stock','stock:SH:600707','active',"
                "NULL,'single_row','{\"identity_key\":"
                "\"stock:SH:600707\"}'::jsonb)"
            )
        self.assertEqual(self._scope(), new_expected)
        self.assertEqual(self._proposal_digest(), baseline_digest)

        self.cluster.apply_file(
            self.database, ROLLBACK_PATH, role="ashare_v3_user"
        )
        rollback_evidence = self._function_evidence()
        self.assertEqual(rollback_evidence, baseline_evidence)
        self.assertEqual(self._proposal_digest(), baseline_digest)
        self.assertEqual(self._scope(), old_expected)
        self.assertEqual(self._scope("n6_quote_writer_pending_scope"), old_expected)


if __name__ == "__main__":
    unittest.main()
