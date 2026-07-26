from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import unittest
from pathlib import Path

from tests.test_n6_ai_qualified_extrema_function_fix_schema import (
    FUNCTION_HEADER,
    function_block,
    function_body,
    normalized,
    top_level_function_blocks,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "sql/070_n6_ai_shadow_context_latest_grain_and_strategy_scope.sql"
)
ROLLBACK = (
    ROOT
    / "sql/070_n6_ai_shadow_context_latest_grain_and_strategy_scope_rollback.sql"
)
SOURCE_BASE = (
    ROOT
    / "sql/061_n6_ai_shadow_decision_risk_state_and_qualified_extrema_fix.sql"
)
SOURCE_V2 = ROOT / "sql/058_n6_ai_context_memory_hash_contract.sql"
SOURCE_STRATEGY = ROOT / "sql/059_n6_ai_investor_strategy_policy_v1.sql"

FUNCTIONS = {
    "n6_ai_agent_context_load": {
        "signature": "n6_ai_agent_context_load(text,date,integer)",
        "source": SOURCE_BASE,
        "old_sha": (
            "4dae0563b34df9e066c2c91feb6f3a096a09ea2573a31f2cf"
            "30c71bfe0704993"
        ),
        "new_sha": (
            "1d4283cd96f34032e51049aa6f4c1305dabe37cf0c62e1b2"
            "ba7594091290cc5a"
        ),
        "allowed_role": None,
    },
    "n6_ai_agent_context_load_v2": {
        "signature": "n6_ai_agent_context_load_v2(text,date,integer,text)",
        "source": SOURCE_V2,
        "old_sha": (
            "df2afc2d7583effd10905ed478ab0df7e2147a854784bfc1"
            "b6087ca6d9b04681"
        ),
        "new_sha": (
            "ae000e4593d0de425dce168640740e1186dc7bd8d007e1a3"
            "677608cbf3940730"
        ),
        "allowed_role": "n6_ai_agent",
    },
    "n6_ai_strategy_context_load_v1": {
        "signature": "n6_ai_strategy_context_load_v1(text,date,integer,text)",
        "source": SOURCE_STRATEGY,
        "old_sha": (
            "79dd370a27ff53b270ab032542cb0fc4eed3262a673919ff8"
            "f0d6e751592f504"
        ),
        "new_sha": (
            "4865a77cc5940fb1230dad18339c05d9e8eefc4aadb535b21"
            "e52d16689dc4d14"
        ),
        "allowed_role": None,
    },
}

OLD_RANK = """           pg_catalog.row_number() OVER (
             PARTITION BY shared.source_event_id,
                          shared.identity_key,
                          shared.direction
             ORDER BY shared.source_signal_projection_id
           ) AS duplicate_rank"""
NEW_RANK = """           pg_catalog.row_number() OVER (
             PARTITION BY shared.asset_kind,
                          shared.identity_key,
                          shared.direction
             ORDER BY shared.source_event_time DESC,
                      shared.source_signal_projection_id DESC
           ) AS duplicate_rank"""
OLD_COUNT = """    SELECT DISTINCT shared.asset_kind,
           shared.source_event_id,
           shared.identity_key,
           shared.direction"""
NEW_COUNT = """    SELECT DISTINCT shared.asset_kind,
           shared.identity_key,
           shared.direction"""
SCOPE_CTES = """  ), candidate_stock_identity AS (
    SELECT DISTINCT stock.identity_key
    FROM stock_candidate stock
  ), selected_index_context AS (
    SELECT DISTINCT signal.identity_key
    FROM public.n6_ai_shared_signal_projection signal
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           signal.user_projection_run_id
     AND projection_run.source_layer = 'N5_action'
     AND projection_run.status = 'passed'
     AND projection_run.quality_summary_json
           ->>'b_track_signal_projection' = 'passed'
    WHERE signal.for_trade_date = p_for_trade_date
      AND signal.asset_kind = 'index'
      AND signal.identity_key ~ '^index:(SH|SZ):[0-9]{6}$'
      AND signal.direction IN ('buy', 'sell')
      AND signal.shared_status = 'active'
      AND signal.action_state IN ('eligible', 'executed')
      AND snapshot_source_signal_ids @>
            pg_catalog.jsonb_build_array(
              signal.source_signal_projection_id
            )
  ), selected_board_context AS (
    SELECT DISTINCT signal.identity_key
    FROM public.n6_ai_shared_signal_projection signal
    JOIN public.user_projection_run projection_run
      ON projection_run.user_projection_run_id =
           signal.user_projection_run_id
     AND projection_run.source_layer = 'N5_action'
     AND projection_run.status = 'passed'
     AND projection_run.quality_summary_json
           ->>'b_track_signal_projection' = 'passed'
    WHERE signal.for_trade_date = p_for_trade_date
      AND signal.asset_kind = 'board'
      AND signal.identity_key ~ '^board:TDX:[0-9]{6}$'
      AND signal.direction IN ('buy', 'sell')
      AND signal.shared_status = 'active'
      AND signal.action_state IN ('eligible', 'executed')
      AND snapshot_source_signal_ids @>
            pg_catalog.jsonb_build_array(
              signal.source_signal_projection_id
            )
  ), index_membership_ranked AS ("""
OLD_INDEX_FROM = """    FROM public.v_n6_index_membership_fact membership
    WHERE membership.stock_identity_key"""
NEW_INDEX_FROM = """    FROM public.v_n6_index_membership_fact membership
    JOIN candidate_stock_identity stock_scope
      ON stock_scope.identity_key = membership.stock_identity_key
    JOIN selected_index_context market_scope
      ON market_scope.identity_key = membership.index_identity_key
    WHERE membership.stock_identity_key"""
OLD_BOARD_FROM = """    FROM public.v_n6_board_membership_fact membership
    WHERE membership.stock_identity_key"""
NEW_BOARD_FROM = """    FROM public.v_n6_board_membership_fact membership
    JOIN candidate_stock_identity stock_scope
      ON stock_scope.identity_key = membership.stock_identity_key
    JOIN selected_board_context market_scope
      ON market_scope.identity_key = membership.board_identity_key
    WHERE membership.stock_identity_key"""
OLD_INDEX_HINT = "  ), index_hint AS ("
NEW_INDEX_HINT = "  ), index_hint AS MATERIALIZED ("
OLD_BOARD_HINT = "  ), board_hint AS ("
NEW_BOARD_HINT = "  ), board_hint AS MATERIALIZED ("
SCHEDULE_067_PG_PROC_PROSRC_SHA256 = (
    "1ec882400c5cb95e1743e7f8829327d6"
    "cf42e3bfb7ea68a64c70795a1d73731d"
)


def expected_blocks() -> tuple[dict[str, str], dict[str, str]]:
    old = {}
    for name, contract in FUNCTIONS.items():
        source = contract["source"].read_text(encoding="utf-8")
        candidate = function_block(source, name)
        digest = hashlib.sha256(function_body(candidate).encode()).hexdigest()
        if digest != contract["old_sha"]:
            raise AssertionError(f"source authority hash mismatch: {name}")
        old[name] = candidate

    fixed = dict(old)
    if fixed["n6_ai_agent_context_load"].count(OLD_RANK) != 2:
        raise AssertionError("base patch points polluted")
    fixed["n6_ai_agent_context_load"] = fixed[
        "n6_ai_agent_context_load"
    ].replace(OLD_RANK, NEW_RANK)

    if fixed["n6_ai_agent_context_load_v2"].count(OLD_COUNT) != 1:
        raise AssertionError("v2 patch point polluted")
    fixed["n6_ai_agent_context_load_v2"] = fixed[
        "n6_ai_agent_context_load_v2"
    ].replace(OLD_COUNT, NEW_COUNT, 1)

    strategy = fixed["n6_ai_strategy_context_load_v1"]
    if strategy.count("  ), index_membership_ranked AS (") != 1:
        raise AssertionError("strategy CTE patch point polluted")
    strategy = strategy.replace(
        "  ), index_membership_ranked AS (", SCOPE_CTES, 1
    )
    if strategy.count(OLD_INDEX_FROM) != 1:
        raise AssertionError("index patch point polluted")
    strategy = strategy.replace(OLD_INDEX_FROM, NEW_INDEX_FROM, 1)
    if strategy.count(OLD_BOARD_FROM) != 1:
        raise AssertionError("board patch point polluted")
    strategy = strategy.replace(OLD_BOARD_FROM, NEW_BOARD_FROM, 1)
    if strategy.count(OLD_INDEX_HINT) != 1:
        raise AssertionError("index hint patch point polluted")
    strategy = strategy.replace(OLD_INDEX_HINT, NEW_INDEX_HINT, 1)
    if strategy.count(OLD_BOARD_HINT) != 1:
        raise AssertionError("board hint patch point polluted")
    strategy = strategy.replace(OLD_BOARD_HINT, NEW_BOARD_HINT, 1)
    fixed["n6_ai_strategy_context_load_v1"] = strategy

    for name, contract in FUNCTIONS.items():
        digest = hashlib.sha256(
            function_body(fixed[name]).encode()
        ).hexdigest()
        if digest != contract["new_sha"]:
            raise AssertionError(f"fixed authority hash mismatch: {name}")
    return old, fixed


def gate(sql: str, tag: str) -> str:
    start_token = "DO $" + tag + "$"
    end_token = "$" + tag + "$;"
    start = sql.index(start_token)
    end = sql.index(end_token, start) + len(end_token)
    return sql[start:end]


def strip_functions(sql: str) -> str:
    result = sql
    for name in FUNCTIONS:
        definitions = top_level_function_blocks(result, name)
        if len(definitions) != 1:
            raise AssertionError(f"definition count mismatch: {name}")
        result = result.replace(
            definitions[0],
            "CREATE OR REPLACE FUNCTION public." + name + ";",
            1,
        )
    return result


def validate_gate(sql: str, pre_sha: str, post_sha: str) -> None:
    preflight = gate(sql, "preflight")
    postflight = gate(sql, "postflight")
    tokens = (
        "function_proc.owner_name = 'ashare_v3_user'",
        "function_proc.language_name = 'plpgsql'",
        "function_proc.prosecdef",
        "NOT function_proc.proisstrict",
        "NOT function_proc.proleakproof",
        "function_proc.provolatile = 'v'",
        "function_proc.proparallel = 'u'",
        "ARRAY['search_path=pg_catalog']::text[]",
        "pg_catalog.aclexplode(",
        "function_acl.privilege_type = 'EXECUTE'",
        "AND NOT function_acl.is_grantable",
        "AND NOT EXISTS (",
    )
    for token in tokens:
        if token not in preflight or token not in postflight:
            raise AssertionError("missing authority token: " + token)
    for contract in FUNCTIONS.values():
        if contract["signature"] not in preflight:
            raise AssertionError("missing signature lock")
        if contract[pre_sha] not in preflight:
            raise AssertionError("missing preflight SHA lock")
        if contract[post_sha] not in postflight:
            raise AssertionError("missing postflight SHA lock")


def validate_rollback_schedule_gate(sql: str) -> None:
    preflight = gate(sql, "preflight")
    for token in (
        "n6_ai_agent_shadow_schedule_preflight(text,date)",
        SCHEDULE_067_PG_PROC_PROSRC_SHA256,
        "schedule_proc.owner_name IS DISTINCT FROM 'ashare_v3_user'",
        "schedule_proc.prosecdef IS DISTINCT FROM true",
        "ARRAY['search_path=pg_catalog']::text[]",
        "schedule_role_oid",
        "function_acl.grantee IN (",
        "AND NOT function_acl.is_grantable",
        "070_rollback_requires_067_schedule",
    ):
        if token not in preflight:
            raise AssertionError("missing 067 rollback authority: " + token)


def latest(rows: list[dict]) -> list[dict]:
    selected = {}
    for row in rows:
        key = (
            row["asset_kind"],
            row["identity_key"],
            row["direction"],
        )
        ordering = (
            row["source_event_time"],
            row["source_signal_projection_id"],
        )
        current = selected.get(key)
        if current is None or ordering > (
            current["source_event_time"],
            current["source_signal_projection_id"],
        ):
            selected[key] = row
    return list(selected.values())


class N6AIShadowContextLatestGrain070Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")
        cls.old, cls.fixed = expected_blocks()

    def test_exact_three_function_forward_and_rollback(self) -> None:
        for sql in (self.migration, self.rollback):
            self.assertTrue(sql.startswith("BEGIN;"))
            self.assertTrue(sql.rstrip().endswith("COMMIT;"))
        expected_names = set(FUNCTIONS)
        self.assertEqual(
            {
                match.group("name").lower()
                for match in FUNCTION_HEADER.finditer(self.migration)
            },
            expected_names,
        )
        self.assertEqual(
            {
                match.group("name").lower()
                for match in FUNCTION_HEADER.finditer(self.rollback)
            },
            expected_names,
        )
        for name in FUNCTIONS:
            self.assertEqual(
                function_block(self.migration, name), self.fixed[name]
            )
            self.assertEqual(
                function_block(self.rollback, name), self.old[name]
            )

    def test_latest_grain_and_capacity_gate_are_identical(self) -> None:
        base = function_block(
            self.migration, "n6_ai_agent_context_load"
        )
        v2 = function_block(
            self.migration, "n6_ai_agent_context_load_v2"
        )
        self.assertEqual(base.count(NEW_RANK), 2)
        self.assertNotIn("PARTITION BY shared.source_event_id", base)

        start = v2.index("  SELECT pg_catalog.count(*) FILTER")
        end = v2.index("  base_result :=", start)
        capacity = v2[start:end]
        self.assertIn(NEW_COUNT, capacity)
        self.assertNotIn("shared.source_event_id", capacity)
        self.assertIn("eligible_signal_count > p_max_signals", capacity)
        self.assertIn("market_context_count > p_max_signals", capacity)
        self.assertIn("'signal_universe_too_large'", capacity)
        self.assertIn("p_max_signals <> 1000", v2)
        self.assertLess(
            v2.index("'signal_universe_too_large'"),
            v2.index("base_result :="),
        )

    def test_old_events_cannot_pollute_latest_workset(self) -> None:
        t0 = datetime(2026, 7, 21, 1, 30, tzinfo=timezone.utc)
        t1 = datetime(2026, 7, 21, 2, 0, tzinfo=timezone.utc)
        rows = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "source_event_time": t0,
                "source_signal_projection_id": 900,
            },
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "source_event_time": t1,
                "source_signal_projection_id": 901,
            },
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "source_event_time": t1,
                "source_signal_projection_id": 902,
            },
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "sell",
                "source_event_time": t0,
                "source_signal_projection_id": 903,
            },
            {
                "asset_kind": "index",
                "identity_key": "index:SH:000001",
                "direction": "buy",
                "source_event_time": t0,
                "source_signal_projection_id": 904,
            },
            {
                "asset_kind": "board",
                "identity_key": "board:TDX:880001",
                "direction": "buy",
                "source_event_time": t0,
                "source_signal_projection_id": 905,
            },
        ]
        selected = latest(rows)
        self.assertEqual(len(selected), 4)
        self.assertEqual(
            {row["source_signal_projection_id"] for row in selected},
            {902, 903, 904, 905},
        )

    def test_capacity_stays_fail_closed_above_1000_latest_grains(self) -> None:
        t0 = datetime(2026, 7, 21, tzinfo=timezone.utc)
        rows = []
        for event_no in range(50):
            rows.append(
                {
                    "asset_kind": "stock",
                    "identity_key": "stock:SH:600000",
                    "direction": "buy",
                    "source_event_time": t0,
                    "source_signal_projection_id": event_no + 1,
                }
            )
        for identity_no in range(1000):
            rows.append(
                {
                    "asset_kind": "stock",
                    "identity_key": f"stock:SH:{identity_no:06d}",
                    "direction": "sell",
                    "source_event_time": t0,
                    "source_signal_projection_id": identity_no + 100,
                }
            )
        self.assertEqual(len(latest(rows)), 1001)
        self.assertGreater(len(rows), len(latest(rows)))

    def test_membership_scope_precedes_window_ranking(self) -> None:
        strategy = function_block(
            self.migration, "n6_ai_strategy_context_load_v1"
        )
        index_start = strategy.index(
            "  ), index_membership_ranked AS ("
        )
        index_end = strategy.index(
            "  ), index_membership AS (", index_start
        )
        board_start = strategy.index(
            "  ), board_membership_ranked AS ("
        )
        board_end = strategy.index(
            "  ), board_membership AS (", board_start
        )
        index_section = strategy[index_start:index_end]
        board_section = strategy[board_start:board_end]
        self.assertIn(
            "JOIN candidate_stock_identity stock_scope", index_section
        )
        self.assertIn(
            "JOIN selected_index_context market_scope", index_section
        )
        self.assertIn(
            "JOIN candidate_stock_identity stock_scope", board_section
        )
        self.assertIn(
            "JOIN selected_board_context market_scope", board_section
        )

    def test_both_hint_aggregates_are_materialized_once(self) -> None:
        strategy = function_block(
            self.migration, "n6_ai_strategy_context_load_v1"
        )
        self.assertEqual(strategy.count(NEW_INDEX_HINT), 1)
        self.assertEqual(strategy.count(NEW_BOARD_HINT), 1)
        self.assertNotIn(OLD_INDEX_HINT, strategy)
        self.assertNotIn(OLD_BOARD_HINT, strategy)

    def test_hash_owner_acl_and_search_path_fail_closed(self) -> None:
        validate_gate(self.migration, "old_sha", "new_sha")
        validate_gate(self.rollback, "new_sha", "old_sha")
        validate_rollback_schedule_gate(self.rollback)
        self.assertIn("'070_already_applied'", self.migration)
        self.assertIn("'070_partial_or_source_mismatch'", self.migration)
        self.assertIn(
            "'070_rollback_requires_fixed_state'", self.rollback
        )
        with self.assertRaisesRegex(
            AssertionError, "missing preflight SHA lock"
        ):
            validate_gate(
                self.migration.replace(
                    FUNCTIONS["n6_ai_agent_context_load"]["old_sha"],
                    "0" * 64,
                    1,
                ),
                "old_sha",
                "new_sha",
            )
        with self.assertRaisesRegex(
            AssertionError, "missing authority token"
        ):
            validate_gate(
                self.migration.replace(
                    "ARRAY['search_path=pg_catalog']::text[]",
                    "ARRAY['search_path=public']::text[]",
                    1,
                ),
                "old_sha",
                "new_sha",
            )
        with self.assertRaisesRegex(
            AssertionError, "missing 067 rollback authority"
        ):
            validate_rollback_schedule_gate(
                self.rollback.replace(
                    SCHEDULE_067_PG_PROC_PROSRC_SHA256,
                    "0" * 64,
                    1,
                )
            )

    def test_no_schema_data_or_authority_expansion(self) -> None:
        for sql in (self.migration, self.rollback):
            shell = normalized(strip_functions(sql))
            for forbidden in (
                "create table",
                "alter table",
                "drop table",
                "insert into",
                "update public.",
                "delete from",
                "grant execute",
                "revoke ",
                "deepseek",
                "proposal_create",
                "order_create",
                "trade_create",
                "071_",
            ):
                self.assertNotIn(forbidden, shell)
            self.assertEqual(
                shell.count("create or replace function public."), 3
            )


if __name__ == "__main__":
    unittest.main()
