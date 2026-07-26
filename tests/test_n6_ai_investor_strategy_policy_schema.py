from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/059_n6_ai_investor_strategy_policy_v1.sql"
SOURCE_055 = ROOT / "sql/055_n6_ai_agent_v1_schema.sql"
ROLLBACK = (
    ROOT / "sql/059_n6_ai_investor_strategy_policy_v1_rollback.sql"
)
CONTRACT = (
    ROOT
    / "docs/N6_AI_INVESTOR_STRATEGY_POLICY_V1_IMPLEMENTATION_CONTRACT.md"
)

NEW_TABLES = (
    "n6_ai_position_strategy_episode",
    "n6_ai_strategy_action",
    "n6_ai_candidate_rank_audit",
)
AI_FUNCTIONS = (
    "n6_ai_strategy_shadow_evaluate(date,text,text)",
)
EXECUTOR_FUNCTIONS = (
    "n6_ai_strategy_proposal_create_confirm_v1(jsonb)",
    "n6_ai_executor_strategy_action_apply_v1(bigint,text)",
)


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def without_line_comments(value: str) -> str:
    return "\n".join(
        line
        for line in value.splitlines()
        if not line.lstrip().startswith("--")
    )


def punctuation_compact(value: str) -> str:
    compact = re.sub(r"\s*\(\s*", "(", normalized(value))
    compact = re.sub(r"\s*,\s*", ",", compact)
    return re.sub(r"\s*\)", ")", compact)


def function_block(sql: str, function_name: str) -> str:
    pattern = re.compile(
        rf"(?ims)^CREATE\s+OR\s+REPLACE\s+FUNCTION\s+"
        rf"public\.{re.escape(function_name)}\s*\(.*?^\$function\$;\s*$"
    )
    matches = pattern.findall(sql)
    if len(matches) != 1:
        raise AssertionError(
            f"expected one top-level definition for {function_name}, "
            f"found {len(matches)}"
        )
    return matches[0]


def function_body(sql: str, function_name: str) -> str:
    pattern = re.compile(
        rf"(?ims)^CREATE\s+OR\s+REPLACE\s+FUNCTION\s+"
        rf"public\.{re.escape(function_name)}\s*\(.*?"
        rf"^AS\s+\$function\$(.*?)^\$function\$;\s*$"
    )
    matches = pattern.findall(sql)
    if len(matches) != 1:
        raise AssertionError(
            f"expected one body for {function_name}, found {len(matches)}"
        )
    return matches[0]


def check_constraint_clause(sql: str, constraint_name: str) -> str:
    marker = re.search(
        rf"(?i)\bADD\s+CONSTRAINT\s+{re.escape(constraint_name)}\s+CHECK\s*\(",
        sql,
    )
    if marker is None:
        raise AssertionError(f"constraint not found: {constraint_name}")
    open_paren = sql.find("(", marker.start())
    depth = 0
    index = open_paren
    in_string = False
    while index < len(sql):
        character = sql[index]
        if character == "'":
            if in_string and index + 1 < len(sql) and sql[index + 1] == "'":
                index += 2
                continue
            in_string = not in_string
        elif not in_string:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    return sql[marker.start():index + 1]
        index += 1
    raise AssertionError(f"unterminated constraint: {constraint_name}")


class N6AiInvestorStrategyPolicySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        missing = [
            str(path.relative_to(ROOT))
            for path in (MIGRATION, SOURCE_055, ROLLBACK, CONTRACT)
            if not path.is_file()
        ]
        if missing:
            raise AssertionError(f"059 implementation artifacts missing: {missing}")
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.source_055 = SOURCE_055.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.norm = normalized(cls.sql)
        cls.rollback_norm = normalized(cls.rollback)
        cls.code_norm = normalized(without_line_comments(cls.sql))
        cls.rollback_code_norm = normalized(
            without_line_comments(cls.rollback)
        )
        cls.compact = punctuation_compact(cls.sql)

    def test_migration_is_additive_059_and_requires_058(self) -> None:
        self.assertTrue(self.code_norm.startswith("begin;"))
        self.assertTrue(self.code_norm.endswith("commit;"))
        self.assertIn("session_user <> 'ashare_v3_user'", self.norm)
        self.assertIn("current_user <> 'ashare_v3_user'", self.norm)
        self.assertIn(
            "public.n6_ai_agent_context_load_v2(text,date,integer,text)",
            self.norm,
        )
        self.assertIn("public.common_trade_calendar", self.norm)
        self.assertIn("059_already_applied", self.norm)
        schema_sql_without_temp_cleanup = re.sub(
            r"(?i)\bDROP\s+TABLE\s+pg_temp\."
            r"n6_virtual_trade_proposal_055_expected\s*;",
            "",
            self.sql,
        )
        self.assertNotRegex(
            schema_sql_without_temp_cleanup,
            r"(?i)\b(DROP|TRUNCATE)\s+TABLE\b",
        )
        self.assertNotRegex(
            self.sql,
            r"(?i)\bDROP\s+(?:COLUMN|FUNCTION|TYPE|ROLE|SCHEMA)\b",
        )

    def test_preflight_rejects_every_partial_059_object_and_legacy_drift(
        self,
    ) -> None:
        preflight = self.norm.split("do $preflight$", 1)[1].split(
            "$preflight$;", 1
        )[0]
        for token in (
            "public.n6_ai_shared_strategy_fields_capture_v1()",
            "public.n6_ai_strategy_episode_locked_fields_immutable_v1()",
            "public.n6_ai_strategy_context_load_v1(text,date,integer,text)",
            "public.n6_ai_strategy_shadow_evaluate(date,text,text)",
            "public.n6_ai_strategy_proposal_create_confirm_v1(jsonb)",
            "public.n6_ai_executor_strategy_action_apply_v1(bigint,text)",
            "public.n6_ai_position_strategy_episode_strategy_episode_id_seq",
            "public.n6_ai_strategy_action_strategy_action_id_seq",
            "public.n6_ai_candidate_rank_audit_candidate_rank_audit_id_seq",
            "public.idx_059_n6_ai_strategy_target_reduce_once",
            "public.idx_059_n6_ai_strategy_action_pending",
            "public.idx_059_n6_virtual_trade_proposal_strategy_action",
            "strategy_context_version",
            "reference_target_price",
            "target_quality_status",
            "up_sell_reference_period",
            "financial_score_raw",
            "strategy_action_id",
            "trg_059_n6_ai_shared_strategy_fields_capture",
            "059_partial_object_conflict",
        ):
            self.assertIn(token, preflight)
        for token in (
            "public.n6_ai_shared_signal_projection_capture()",
            "trg_055_n6_ai_shared_signal_projection_capture",
            "n6_virtual_trade_proposal_055_actor_ck",
            "n6_virtual_trade_proposal_055_source_type_ck",
            "n6_virtual_trade_proposal_055_signal_source_ck",
            "n6_virtual_trade_proposal_055_position_source_ck",
            "legacy_trigger_count <> 1",
            "059_legacy_projection_trigger_mismatch",
            "059_legacy_proposal_contract_mismatch",
        ):
            self.assertIn(token, preflight)

    def test_preflight_proves_exact_055_function_trigger_and_checks(
        self,
    ) -> None:
        preflight_raw = self.sql.split("DO $preflight$", 1)[1].split(
            "$preflight$;", 1
        )[0]
        preflight = normalized(preflight_raw)
        capture_body = function_body(
            self.source_055,
            "n6_ai_shared_signal_projection_capture",
        )
        capture_sha = hashlib.sha256(
            capture_body.encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            capture_sha,
            "6bd08f39b6421840aaa95a8b1f7b6507bba402b5e3b18b499dfdeaa3ec2e1f04",
        )

        constraint_names = (
            "n6_virtual_trade_proposal_055_actor_ck",
            "n6_virtual_trade_proposal_055_source_type_ck",
            "n6_virtual_trade_proposal_055_signal_source_ck",
            "n6_virtual_trade_proposal_055_position_source_ck",
        )
        expected_clauses = tuple(
            normalized(
                check_constraint_clause(self.source_055, name)
            ).replace("add constraint", "constraint", 1)
            for name in constraint_names
        )
        capture_mismatch_branch = (
            "if legacy_capture_function_oid is null then "
            "raise exception "
            "'059_legacy_projection_capture_function_mismatch'; "
            "end if"
        )
        constraint_mismatch_branch = (
            "if legacy_constraint_mismatch_count <> 0 then "
            "raise exception '059_legacy_proposal_contract_mismatch'; "
            "end if"
        )

        function_tokens = (
            "function_owner.rolname = 'ashare_v3_user'",
            "function_language.lanname = 'plpgsql'",
            "function_row.prokind = 'f'",
            "function_row.prorettype = 'pg_catalog.trigger'::pg_catalog.regtype",
            "function_row.pronargs = 0",
            "function_row.provolatile = 'v'",
            "function_row.prosecdef = true",
            "function_row.proisstrict = false",
            "function_row.proleakproof = false",
            "function_row.proparallel = 'u'",
            "function_row.proconfig is not distinct from "
            "array['search_path=pg_catalog']::text[]",
            capture_sha,
            "pg_catalog.sha256(",
            "pg_catalog.convert_to(function_row.prosrc, 'utf8')",
            capture_mismatch_branch,
        )
        trigger_tokens = (
            "trigger_row.tgtype = 5",
            "trigger_row.tgenabled = 'o'",
            "trigger_row.tgisinternal = false",
            "trigger_row.tgnargs = 0",
            "trigger_row.tgargs = ''::pg_catalog.bytea",
            "trigger_row.tgattr = ''::pg_catalog.int2vector",
            "trigger_row.tgqual is null",
            "trigger_row.tgconstraint = 0",
            "trigger_row.tgconstrrelid = 0",
            "trigger_row.tgconstrindid = 0",
            "trigger_row.tgdeferrable = false",
            "trigger_row.tginitdeferred = false",
            "trigger_row.tgoldtable is null",
            "trigger_row.tgnewtable is null",
            "trigger_row.tgparentid = 0",
            "trigger_row.tgfoid = legacy_capture_function_oid",
        )
        constraint_tokens = (
            "create temporary table "
            "n6_virtual_trade_proposal_055_expected",
            "on commit drop",
            "pg_catalog.pg_get_constraintdef(",
            "actual_constraint.oid, false",
            "is distinct from pg_catalog.pg_get_constraintdef(",
            "expected_constraint.oid, false",
            "actual_constraint.contype is distinct from 'c'",
            "actual_constraint.convalidated is distinct from true",
            "actual_constraint.connoinherit is distinct from false",
            "actual_constraint.conislocal is distinct from true",
            "actual_constraint.coninhcount is distinct from 0",
            "drop table pg_temp.n6_virtual_trade_proposal_055_expected",
            "legacy_expected_constraint_count <> 4",
            "059_expected_proposal_contract_internal_mismatch",
            constraint_mismatch_branch,
        )

        def assert_exact_provenance(candidate: str) -> None:
            for token in (
                *function_tokens,
                *trigger_tokens,
                *constraint_tokens,
            ):
                self.assertIn(token, candidate)
            for clause in expected_clauses:
                self.assertEqual(candidate.count(clause), 1)
            self.assertNotRegex(candidate, r"\b(?:like|ilike)\b")
            self.assertNotIn("or true", candidate)
            for constraint_name in constraint_names:
                self.assertEqual(
                    candidate.count(constraint_name),
                    2,
                )
            self.assertIn("legacy_constraint_count <> 4", candidate)

        assert_exact_provenance(preflight)

        mutation_replacements = (
            (
                expected_clauses[0],
                expected_clauses[0][:-1] + " or true)",
            ),
            (capture_sha, "0" * 64),
            ("function_owner.rolname = 'ashare_v3_user'", "true"),
            ("function_row.prosecdef = true", "true"),
            (
                "function_row.proconfig is not distinct from "
                "array['search_path=pg_catalog']::text[]",
                "true",
            ),
            ("trigger_row.tgtype = 5", "true"),
            (
                "trigger_row.tgfoid = legacy_capture_function_oid",
                "true",
            ),
            ("trigger_row.tgconstraint = 0", "true"),
        )
        for old, replacement in mutation_replacements:
            with self.subTest(mutation=old):
                mutated = preflight.replace(old, replacement, 1)
                self.assertNotEqual(mutated, preflight)
                with self.assertRaises(AssertionError):
                    assert_exact_provenance(mutated)

        for clause in expected_clauses:
            with self.subTest(removed_expected_constraint=clause):
                mutated = preflight.replace(clause, "", 1)
                self.assertNotEqual(mutated, preflight)
                with self.assertRaises(AssertionError):
                    assert_exact_provenance(mutated)

        for branch in (
            capture_mismatch_branch,
            constraint_mismatch_branch,
        ):
            with self.subTest(removed_mismatch_consumer=branch):
                mutated = preflight.replace(branch, "", 1)
                self.assertNotEqual(mutated, preflight)
                with self.assertRaises(AssertionError):
                    assert_exact_provenance(mutated)

        like_mutation = preflight.replace(
            "actual_constraint.contype is distinct from 'c'",
            "pg_catalog.pg_get_constraintdef(actual_constraint.oid, false) "
            "like '%principal_type%'",
            1,
        )
        with self.assertRaises(AssertionError):
            assert_exact_provenance(like_mutation)

        preflight_end = self.sql.index("$preflight$;")
        first_public_ddl = min(
            position
            for token in (
                "ALTER TABLE public.",
                "CREATE TABLE public.",
                "CREATE OR REPLACE FUNCTION public.",
            )
            if (position := self.sql.find(token)) >= 0
        )
        self.assertLess(preflight_end, first_public_ddl)
        self.assertLess(
            preflight_raw.lower().index(
                "drop table pg_temp."
                "n6_virtual_trade_proposal_055_expected"
            ),
            len(preflight_raw),
        )

    def test_exact_three_strategy_tables_and_shadow_safe_states(self) -> None:
        created = set(
            re.findall(
                r"(?i)CREATE TABLE public\.([a-z0-9_]+)",
                self.sql,
            )
        )
        self.assertEqual(created, set(NEW_TABLES))
        for table in NEW_TABLES:
            self.assertIn(f"create table public.{table}", self.norm)
        for token in (
            "holding_episode_no",
            "locked_target_price",
            "locked_target_quality_status",
            "up_sell_reference_period",
            "pending_clear",
            "pending_clear_started_trade_date",
            "target_reduce",
            "period_clear",
            "pending_clear_continue",
            "shadow_recorded",
            "execution_authorized boolean not null default false",
            "check (execution_authorized = false)",
        ):
            self.assertIn(token, self.norm)
        self.assertIn(
            "decision_rank_score numeric(20,8) generated always as",
            self.norm,
        )

    def test_sql_has_no_duplicate_declaration_or_loop_header(self) -> None:
        self.assertEqual(
            self.norm.count("policy_version text not null"),
            1,
        )
        evaluator = normalized(
            function_block(
                self.sql,
                "n6_ai_strategy_shadow_evaluate",
            )
        )
        self.assertEqual(
            len(re.findall(r"\bfor position_row in\b", evaluator)),
            1,
        )

    def test_episode_lock_and_action_idempotency_are_database_enforced(self) -> None:
        for token in (
            "n6_ai_strategy_episode_locked_fields_immutable_v1",
            "trg_059_n6_ai_strategy_episode_locked_fields_immutable",
            "old.locked_target_price is distinct from new.locked_target_price",
            "old.holding_episode_no is distinct from new.holding_episode_no",
            "old.up_sell_reference_period is distinct from "
            "new.up_sell_reference_period",
            "old.ai_user_id is distinct from new.ai_user_id",
            "old.principal_id is distinct from new.principal_id",
            "old.principal_type is distinct from new.principal_type",
            "old.strategy_id is distinct from new.strategy_id",
            "idx_059_n6_ai_strategy_target_reduce_once",
            "holding_episode_no, locked_target_price",
            "idempotency_key text not null unique",
        ):
            self.assertIn(token, self.norm)
        self.assertRegex(
            self.norm,
            r"unique\s*\(\s*virtual_account_id\s*,\s*"
            r"virtual_position_id\s*,\s*holding_episode_no\s*\)",
        )
        self.assertRegex(
            self.norm,
            r"foreign key\s*\(\s*strategy_episode_id\s*,\s*ai_user_id\s*,\s*"
            r"principal_id\s*,\s*principal_type\s*,\s*strategy_id\s*,\s*"
            r"virtual_account_id\s*,\s*virtual_position_id\s*,\s*"
            r"identity_key\s*,\s*holding_episode_no\s*\)\s*references\s+"
            r"public\.n6_ai_position_strategy_episode",
        )

    def test_sanitized_strategy_fields_are_versioned_and_n6_owned(self) -> None:
        for token in (
            "add column strategy_context_version text",
            "add column reference_target_price numeric",
            "add column target_quality_status text",
            "add column up_sell_reference_period text",
            "add column financial_score_raw numeric",
            "n6_ai_shared_strategy_fields_capture_v1",
            "n6_ai_investor_strategy_policy_v1",
            "new.display_payload_json",
            "new.display_payload_json "
            "->'condition_projection_context'->'fields'",
            "safe_context_fields->>'buy_target_price'",
            "safe_context_fields->>'clear_sell_ref_period'",
            "new.display_payload_json "
            "->>'condition_projection_context_status' = 'ready'",
            "new.user_signal_projection_id",
        ):
            self.assertIn(token, self.norm)
        capture = normalized(
            function_block(
                self.sql,
                "n6_ai_shared_strategy_fields_capture_v1",
            )
        )
        self.assertRegex(
            capture,
            r"safe_target_text := coalesce\(\s*"
            r"safe_context_fields->>'buy_target_price',\s*"
            r"new\.display_payload_json->>'buy_target_price'",
        )
        self.assertRegex(
            capture,
            r"safe_financial_score_text := coalesce\(\s*"
            r"safe_context_fields->>'score',\s*"
            r"new\.display_payload_json->>'score'",
        )
        self.assertRegex(
            capture,
            r"safe_up_sell_period := coalesce\(\s*"
            r"safe_context_fields->>'up_sell_reference_period',\s*"
            r"new\.display_payload_json->>'up_sell_reference_period'",
        )
        self.assertRegex(
            capture,
            r"safe_clear_sell_period := coalesce\(\s*"
            r"safe_context_fields->>'clear_sell_ref_period',\s*"
            r"new\.display_payload_json->>'clear_sell_ref_period'",
        )
        self.assertEqual(capture.count("pg_catalog.pg_input_is_valid"), 2)
        self.assertIn(
            "pg_catalog.pg_input_is_valid( "
            "safe_target_text, 'numeric(24,8)' )",
            capture,
        )
        self.assertIn(
            "pg_catalog.pg_input_is_valid( "
            "safe_financial_score_text, 'numeric(18,8)' )",
            capture,
        )
        self.assertRegex(
            capture,
            r"safe_target_price\s*:=\s*case\s+when.*?"
            r"pg_catalog\.pg_input_is_valid\(.*?"
            r"then\s+case\s+when\s+safe_target_text::numeric\(24,8\)\s*"
            r">\s*0",
        )
        backfill = normalized(
            self.sql.split(
                "WITH backfill_source AS",
                1,
            )[1].split(
                "CREATE TABLE public.n6_ai_position_strategy_episode",
                1,
            )[0]
        )
        for canonical_name in (
            "buy_target_price",
            "score",
            "up_sell_reference_period",
            "clear_sell_ref_period",
        ):
            self.assertRegex(
                backfill,
                r"coalesce\(\s*projection\.display_payload_json\s*"
                r"->'condition_projection_context'->'fields'\s*"
                rf"->>'{canonical_name}',\s*"
                r"projection\.display_payload_json"
                rf"->>'{canonical_name}'",
            )
        self.assertEqual(backfill.count("pg_catalog.pg_input_is_valid"), 2)
        self.assertEqual(
            backfill.count(
                "pg_catalog.pg_input_is_valid( "
                "backfill_target_text, 'numeric(24,8)' )"
            ),
            1,
        )
        self.assertIn(
            "pg_catalog.pg_input_is_valid( "
            "backfill_financial_score_text, 'numeric(18,8)' )",
            backfill,
        )
        self.assertIn(
            "backfill_target_price > 0",
            backfill,
        )
        self.assertIn(
            "backfill_financial_score",
            backfill,
        )
        self.assertNotIn("cross join lateral", backfill)
        self.assertIn(
            "update public.n6_ai_shared_signal_projection shared",
            backfill,
        )
        self.assertNotIn("from public.", capture)
        self.assertIn("update public.n6_ai_shared_signal_projection", capture)

    def test_sell_period_capture_and_backfill_fail_closed_on_alias_conflict(
        self,
    ) -> None:
        capture = normalized(
            function_block(
                self.sql,
                "n6_ai_shared_strategy_fields_capture_v1",
            )
        )
        for token in (
            "safe_up_sell_period",
            "safe_clear_sell_period",
            "safe_up_sell_period is distinct from safe_clear_sell_period",
        ):
            self.assertIn(token, capture)
        backfill = normalized(
            self.sql.split(
                "WITH backfill_source AS",
                1,
            )[1].split(
                "CREATE TABLE public.n6_ai_position_strategy_episode",
                1,
            )[0]
        )
        self.assertIn(
            "backfill_up_sell_period is distinct from "
            "backfill_clear_sell_period",
            backfill,
        )

    def test_context_uses_only_approved_n6_views_and_latest_membership(self) -> None:
        context = normalized(
            function_block(self.sql, "n6_ai_strategy_context_load_v1")
        )
        for token in (
            "security definer",
            "set search_path = pg_catalog",
            "session_user <> 'n6_ai_agent'",
            "public.n6_ai_agent_context_load_v2",
            "public.n6_ai_shared_signal_projection",
            "public.v_n6_index_membership_fact",
            "public.v_n6_board_membership_fact",
            "membership.trade_date ~ '^[0-9]{8}$'",
            "membership.trade_date <= pg_catalog.to_char( "
            "p_for_trade_date, 'yyyymmdd' )",
            "order by membership.trade_date desc",
            "row_number() over",
            "original_condition_key ~ '^buy_hint(?::|$)'",
            "original_condition_key ~ '^sell_hint(?::|$)'",
            "condition_key ~ '^buy_hint(?::|$)'",
            "condition_key ~ '^sell_hint(?::|$)'",
            "reference_target_price",
            "target_quality_status",
            "up_sell_reference_period",
            "financial_score_raw",
            "snapshot.source_signal_projection_ids_json",
            "snapshot.workset_hash",
            "'base_snapshot_workset_hash', snapshot_workset_hash",
        ):
            self.assertIn(token, context)
        self.assertNotIn(
            "membership.trade_date <= p_for_trade_date",
            context,
        )
        self.assertNotRegex(
            context,
            r"signal_type\s*~\s*'\^(?:buy|sell)_hint",
        )
        self.assertEqual(
            context.count("join public.user_projection_run"),
            3,
        )
        self.assertEqual(
            context.count("projection_run.source_layer = 'n5_action'"),
            3,
        )
        self.assertEqual(
            context.count("projection_run.status = 'passed'"),
            3,
        )
        self.assertEqual(
            context.count(
                "projection_run.quality_summary_json "
                "->>'b_track_signal_projection' = 'passed'"
            ),
            3,
        )
        self.assertNotIn(
            "projection_run.status in ('passed', 'ready')",
            context,
        )
        self.assertEqual(
            context.count(
                "and not ( coalesce( "
                "hint.original_condition_key "
                "~ '^sell_hint(?::|$)', false ) or coalesce( "
                "hint.condition_key "
                "~ '^sell_hint(?::|$)', false ) )"
            ),
            2,
        )
        self.assertEqual(
            context.count(
                "and not ( coalesce( "
                "hint.original_condition_key "
                "~ '^buy_hint(?::|$)', false ) or coalesce( "
                "hint.condition_key "
                "~ '^buy_hint(?::|$)', false ) )"
            ),
            2,
        )
        self.assertEqual(
            context.count(
                "membership.created_at desc nulls last, "
                "membership.source_version desc nulls last"
            ),
            2,
        )
        self.assertEqual(
            context.count(
                "snapshot_source_signal_ids "
                "@> pg_catalog.jsonb_build_array( "
                "signal.source_signal_projection_id )"
            ),
            1,
        )
        self.assertEqual(
            context.count(
                "snapshot_source_signal_ids "
                "@> pg_catalog.jsonb_build_array( "
                "hint.source_signal_projection_id )"
            ),
            2,
        )
        self.assertEqual(
            context.count(
                "distinct pg_catalog.jsonb_build_object( "
                "'source_signal_projection_id', "
                "hint.source_signal_projection_id, "
                "'identity_key', hint.identity_key, "
                "'direction', hint.direction ) "
                "order by pg_catalog.jsonb_build_object( "
                "'source_signal_projection_id', "
                "hint.source_signal_projection_id, "
                "'identity_key', hint.identity_key, "
                "'direction', hint.direction )"
            ),
            2,
        )
        self.assertEqual(
            context.count(
                "distinct pg_catalog.jsonb_build_object( "
                "'identity_key', membership.index_identity_key, "
                "'trade_date', membership.trade_date, "
                "'source_version', membership.source_version ) "
                "order by pg_catalog.jsonb_build_object( "
                "'identity_key', membership.index_identity_key, "
                "'trade_date', membership.trade_date, "
                "'source_version', membership.source_version )"
            ),
            1,
        )
        self.assertEqual(
            context.count(
                "distinct pg_catalog.jsonb_build_object( "
                "'identity_key', membership.board_identity_key, "
                "'trade_date', membership.trade_date, "
                "'source_version', membership.source_version ) "
                "order by pg_catalog.jsonb_build_object( "
                "'identity_key', membership.board_identity_key, "
                "'trade_date', membership.trade_date, "
                "'source_version', membership.source_version )"
            ),
            1,
        )

    def test_membership_lineage_is_valid_total_ordered_and_unambiguous(
        self,
    ) -> None:
        context = normalized(
            function_block(self.sql, "n6_ai_strategy_context_load_v1")
        )

        def assert_membership_contract(candidate: str) -> None:
            normalized_candidate = normalized(candidate)
            self.assertEqual(
                normalized_candidate.count(
                    "membership.stock_identity_key "
                    "~ '^stock:(sh|sz):[0-9]{6}$'"
                ),
                2,
            )
            self.assertEqual(
                normalized_candidate.count(
                    "membership.index_identity_key "
                    "~ '^index:(sh|sz):[0-9]{6}$'"
                ),
                1,
            )
            self.assertEqual(
                normalized_candidate.count(
                    "membership.board_identity_key is not null "
                    "and pg_catalog.btrim("
                    "membership.board_identity_key) <> ''"
                ),
                1,
            )
            self.assertEqual(
                normalized_candidate.count(
                    "membership.created_at is not null"
                ),
                2,
            )
            self.assertEqual(
                normalized_candidate.count(
                    "membership.source_version is not null "
                    "and pg_catalog.btrim(membership.source_version) <> ''"
                ),
                2,
            )
            self.assertEqual(
                normalized_candidate.count(
                    "order by membership.trade_date desc nulls last, "
                    "membership.created_at desc nulls last, "
                    "membership.source_version desc nulls last"
                ),
                2,
            )
            self.assertEqual(
                normalized_candidate.count(
                    "pg_catalog.count(*) over ( partition by "
                    "membership.stock_identity_key, "
                ),
                2,
            )
            self.assertIn(
                "membership.index_identity_key, membership.trade_date, "
                "membership.created_at, membership.source_version ) "
                "as membership_tie_count",
                normalized_candidate,
            )
            self.assertIn(
                "membership.board_identity_key, membership.trade_date, "
                "membership.created_at, membership.source_version ) "
                "as membership_tie_count",
                normalized_candidate,
            )
            self.assertEqual(
                normalized_candidate.count(
                    "membership_rank = 1 and membership_tie_count = 1"
                ),
                2,
            )

        assert_membership_contract(context)

        mutation_tokens = (
            "membership.stock_identity_key "
            "~ '^stock:(SH|SZ):[0-9]{6}$'",
            "membership.index_identity_key "
            "~ '^index:(SH|SZ):[0-9]{6}$'",
            "membership.board_identity_key IS NOT NULL",
            "membership.created_at IS NOT NULL",
            "membership.source_version IS NOT NULL",
            "NULLS LAST",
            "pg_catalog.count(*) OVER",
            "membership_tie_count = 1",
        )
        for token in mutation_tokens:
            with self.subTest(removed_membership_guard=token):
                mutated = context.replace(normalized(token), "", 1)
                self.assertNotEqual(mutated, context)
                with self.assertRaises(AssertionError):
                    assert_membership_contract(mutated)

    def test_strategy_workset_hash_blocks_same_snapshot_replay_drift(
        self,
    ) -> None:
        context = normalized(
            function_block(self.sql, "n6_ai_strategy_context_load_v1")
        )
        evaluator = normalized(
            function_block(
                self.sql,
                "n6_ai_strategy_shadow_evaluate",
            )
        )
        self.assertRegex(
            context,
            r"strategy_workset_hash\s*:=\s*pg_catalog\.encode\s*\(\s*"
            r"pg_catalog\.sha256\s*\(\s*pg_catalog\.convert_to\s*\(\s*"
            r"pg_catalog\.jsonb_build_object\s*\(\s*"
            r"'base_snapshot_workset_hash'\s*,\s*snapshot_workset_hash\s*,\s*"
            r"'strategy_candidates'\s*,\s*strategy_candidates\s*\)"
            r"\s*::text\s*,\s*'utf8'\s*\)\s*\)\s*,\s*'hex'\s*\)",
        )
        self.assertIn(
            "'base_snapshot_workset_hash', snapshot_workset_hash",
            context,
        )
        self.assertIn(
            "'strategy_workset_hash', strategy_workset_hash",
            context,
        )
        self.assertNotIn(
            "'strategy_workset_hash', snapshot_workset_hash",
            context,
        )
        self.assertIn(
            "snapshot.workset_hash = "
            "strategy_context->>'base_snapshot_workset_hash'",
            evaluator,
        )
        self.assertNotIn(
            "snapshot.workset_hash = "
            "strategy_context->>'strategy_workset_hash'",
            evaluator,
        )

        account_lock = evaluator.index("for update of account")
        replay_guard = evaluator.index(
            "if exists ( select 1 from "
            "public.n6_ai_candidate_rank_audit prior_audit"
        )
        anchor_insert = evaluator.index(
            "insert into public.n6_ai_candidate_rank_audit"
        )
        first_episode_dml = evaluator.index("with closed_position as")
        self.assertLess(account_lock, replay_guard)
        self.assertLess(replay_guard, anchor_insert)
        self.assertLess(anchor_insert, first_episode_dml)
        replay_return = evaluator[replay_guard:anchor_insert]
        for token in (
            "prior_audit.ai_context_snapshot_id = context_snapshot_id",
            "coalesce( prior_audit.audit_payload_json"
            "->>'strategy_workset_hash', '' ) is distinct from "
            "strategy_context->>'strategy_workset_hash'",
            "'reason', 'strategy_context_replay_drift'",
            "'candidate_rank_audit_count', 0",
            "'strategy_action_audit_count', 0",
            "'completed_strategy_episode_count', 0",
            "'proposal_created', false",
            "'order_created', false",
            "'trade_created', false",
            "'position_mutated', false",
            "'cash_mutated', false",
            "'execution_authorized', false",
        ):
            self.assertIn(token, replay_return)
        self.assertNotIn("nullif(", replay_return)

        anchor_block = evaluator[
            anchor_insert:first_episode_dml
        ]
        for token in (
            "'source', 'strategy_workset_anchor'",
            "'strategy_workset_hash', "
            "strategy_context->>'strategy_workset_hash'",
            "null, null, null, 0, 'missing'",
            "on conflict ( ai_context_snapshot_id, "
            "source_signal_projection_id ) do nothing",
        ):
            self.assertIn(token, anchor_block)
        self.assertNotIn("candidate_count :=", anchor_block)

        candidate_table = normalized(
            self.sql.split(
                "CREATE TABLE public.n6_ai_candidate_rank_audit",
                1,
            )[1].split(
                "REVOKE ALL ON TABLE public.n6_ai_position_strategy_episode",
                1,
            )[0]
        )
        self.assertRegex(
            candidate_table,
            r"unique\s+nulls\s+not\s+distinct\s*\(\s*"
            r"ai_context_snapshot_id\s*,\s*"
            r"source_signal_projection_id\s*\)",
        )
        self.assertIn(
            "source_signal_projection_id is null "
            "and identity_key is null",
            candidate_table,
        )
        self.assertIn(
            "source_signal_projection_id is not null "
            "and identity_key is not null "
            "and identity_key ~ '^stock:(sh|sz):[0-9]{6}$'",
            candidate_table,
        )

    def test_empty_first_run_anchor_blocks_changed_candidate_replay(
        self,
    ) -> None:
        evaluator = normalized(
            function_block(
                self.sql,
                "n6_ai_strategy_shadow_evaluate",
            )
        )
        pre_episode_dml = evaluator.split(
            "with closed_position as",
            1,
        )[0]
        anchor_enabled = (
            "insert into public.n6_ai_candidate_rank_audit"
            in pre_episode_dml
            and "'source', 'strategy_workset_anchor'"
            in pre_episode_dml
        )

        def evaluate(
            audit_rows: list[dict[str, object]],
            strategy_hash: str,
            candidate_ids: list[int],
        ) -> dict[str, object]:
            if any(
                (row.get("strategy_workset_hash") or "")
                != strategy_hash
                for row in audit_rows
            ):
                return {
                    "reason": "strategy_context_replay_drift",
                    "audit_rows": list(audit_rows),
                    "proposal_created": False,
                    "order_created": False,
                    "trade_created": False,
                    "position_mutated": False,
                    "cash_mutated": False,
                    "execution_authorized": False,
                }

            next_rows = list(audit_rows)
            if (
                anchor_enabled
                and not any(
                    row["source_id"] is None for row in next_rows
                )
            ):
                next_rows.append(
                    {
                        "source_id": None,
                        "strategy_workset_hash": strategy_hash,
                    }
                )
            next_rows.extend(
                {
                    "source_id": candidate_id,
                    "strategy_workset_hash": strategy_hash,
                }
                for candidate_id in candidate_ids
            )
            return {"reason": None, "audit_rows": next_rows}

        empty_hash = "a" * 64
        changed_hash = "b" * 64
        first_run = evaluate([], empty_hash, [])
        self.assertIsNone(first_run["reason"])
        self.assertEqual(
            first_run["audit_rows"],
            [
                {
                    "source_id": None,
                    "strategy_workset_hash": empty_hash,
                }
            ],
        )

        changed_replay = evaluate(
            first_run["audit_rows"],
            changed_hash,
            [101],
        )
        self.assertEqual(
            changed_replay["reason"],
            "strategy_context_replay_drift",
        )
        self.assertEqual(
            changed_replay["audit_rows"],
            first_run["audit_rows"],
        )
        for flag in (
            "proposal_created",
            "order_created",
            "trade_created",
            "position_mutated",
            "cash_mutated",
            "execution_authorized",
        ):
            self.assertFalse(changed_replay[flag])

    def test_candidate_anchor_check_rejects_null_and_sentinel_drift(
        self,
    ) -> None:
        candidate_table = normalized(
            self.sql.split(
                "CREATE TABLE public.n6_ai_candidate_rank_audit",
                1,
            )[1].split(
                "REVOKE ALL ON TABLE public.n6_ai_position_strategy_episode",
                1,
            )[0]
        )
        classification_start = candidate_table.index(
            "source_signal_projection_id is null"
        )
        classification_end = candidate_table.index(
            "check ( (financial_score_raw is null",
            classification_start,
        )
        classification = candidate_table[
            classification_start:classification_end
        ]

        def sql_equal(left: object, right: object) -> bool | None:
            if left is None or right is None:
                return None
            return left == right

        def sql_regex(value: object, pattern: str) -> bool | None:
            if value is None:
                return None
            return re.fullmatch(pattern, str(value)) is not None

        def sql_and(values: list[bool | None]) -> bool | None:
            if False in values:
                return False
            if None in values:
                return None
            return True

        def sql_or(values: list[bool | None]) -> bool | None:
            if True in values:
                return True
            if None in values:
                return None
            return False

        def enabled(token: str, value: bool | None) -> bool:
            return value if token in classification else True

        def check_accepts(row: dict[str, object]) -> bool:
            payload = row["audit_payload"]
            assert isinstance(payload, dict)
            anchor = sql_and(
                [
                    row["source_id"] is None,
                    row["identity_key"] is None,
                    sql_equal(
                        payload.get("source"),
                        "strategy_workset_anchor",
                    ),
                    sql_regex(
                        payload.get("strategy_workset_hash"),
                        r"[0-9a-f]{64}",
                    ),
                    enabled(
                        "financial_score_raw is null",
                        row["financial_score_raw"] is None,
                    ),
                    enabled(
                        "financial_rank_score = 0",
                        sql_equal(row["financial_rank_score"], 0),
                    ),
                    enabled(
                        "score_status = 'missing'",
                        sql_equal(row["score_status"], "missing"),
                    ),
                    enabled(
                        "index_hint_evidence_refs = '[]'::jsonb",
                        sql_equal(row["index_hint_evidence_refs"], []),
                    ),
                    enabled(
                        "board_hint_evidence_refs = '[]'::jsonb",
                        sql_equal(row["board_hint_evidence_refs"], []),
                    ),
                    enabled(
                        "index_membership_refs = '[]'::jsonb",
                        sql_equal(row["index_membership_refs"], []),
                    ),
                    enabled(
                        "board_membership_refs = '[]'::jsonb",
                        sql_equal(row["board_membership_refs"], []),
                    ),
                    enabled(
                        "index_hint_adjustment = 0",
                        sql_equal(row["index_hint_adjustment"], 0),
                    ),
                    enabled(
                        "board_hint_adjustment = 0",
                        sql_equal(row["board_hint_adjustment"], 0),
                    ),
                    enabled(
                        "index_hint_conflict_zeroed = false",
                        sql_equal(
                            row["index_hint_conflict_zeroed"],
                            False,
                        ),
                    ),
                    enabled(
                        "board_hint_conflict_zeroed = false",
                        sql_equal(
                            row["board_hint_conflict_zeroed"],
                            False,
                        ),
                    ),
                    enabled(
                        "candidate_qualified = false",
                        sql_equal(row["candidate_qualified"], False),
                    ),
                ]
            )
            candidate = sql_and(
                [
                    row["source_id"] is not None,
                    enabled(
                        "identity_key is not null",
                        row["identity_key"] is not None,
                    ),
                    sql_regex(
                        row["identity_key"],
                        r"stock:(SH|SZ):[0-9]{6}",
                    ),
                    sql_equal(
                        payload.get("source"),
                        "approved_n6_strategy_context",
                    ),
                ]
            )
            classification_result = sql_or([anchor, candidate])
            if ") is true" in classification:
                classification_result = classification_result is True
            return classification_result is not False

        valid_anchor: dict[str, object] = {
            "source_id": None,
            "identity_key": None,
            "financial_score_raw": None,
            "financial_rank_score": 0,
            "score_status": "missing",
            "index_hint_evidence_refs": [],
            "board_hint_evidence_refs": [],
            "index_membership_refs": [],
            "board_membership_refs": [],
            "index_hint_adjustment": 0,
            "board_hint_adjustment": 0,
            "index_hint_conflict_zeroed": False,
            "board_hint_conflict_zeroed": False,
            "candidate_qualified": False,
            "audit_payload": {
                "source": "strategy_workset_anchor",
                "strategy_workset_hash": "a" * 64,
            },
        }
        self.assertTrue(check_accepts(valid_anchor))

        def changed(
            row: dict[str, object],
            field: str,
            value: object,
        ) -> dict[str, object]:
            result = dict(row)
            if field.startswith("audit_payload."):
                payload = dict(result["audit_payload"])
                payload[field.split(".", 1)[1]] = value
                result["audit_payload"] = payload
            else:
                result[field] = value
            return result

        invalid_anchor_mutations = (
            ("audit_payload.source", None),
            ("audit_payload.strategy_workset_hash", None),
            ("financial_score_raw", 1),
            ("financial_rank_score", 1),
            ("score_status", "available"),
            ("index_hint_evidence_refs", [{"id": 1}]),
            ("board_hint_evidence_refs", [{"id": 1}]),
            ("index_membership_refs", [{"id": 1}]),
            ("board_membership_refs", [{"id": 1}]),
            ("index_hint_adjustment", 1),
            ("board_hint_adjustment", -1),
            ("index_hint_conflict_zeroed", True),
            ("board_hint_conflict_zeroed", True),
            ("candidate_qualified", True),
        )
        for field, value in invalid_anchor_mutations:
            with self.subTest(anchor_mutation=field):
                self.assertFalse(
                    check_accepts(changed(valid_anchor, field, value))
                )

        valid_candidate = changed(
            changed(
                valid_anchor,
                "source_id",
                101,
            ),
            "identity_key",
            "stock:SH:600000",
        )
        valid_candidate = changed(
            valid_candidate,
            "audit_payload.source",
            "approved_n6_strategy_context",
        )
        self.assertTrue(check_accepts(valid_candidate))
        self.assertFalse(
            check_accepts(
                changed(valid_candidate, "identity_key", None)
            )
        )
        self.assertIn(") is true", classification)
        self.assertIn("identity_key is not null", classification)

    def test_hint_v0_formula_and_evidence_are_audited(self) -> None:
        for token in (
            "index_hint_adjustment",
            "board_hint_adjustment",
            "hint_adjustment",
            "decision_rank_score",
            "index_hint_conflict_zeroed",
            "board_hint_conflict_zeroed",
            "index_hint_evidence_refs",
            "board_hint_evidence_refs",
            "index_membership_refs",
            "board_membership_refs",
            "financial_rank_score",
            "score_status",
            "index_hint_adjustment + board_hint_adjustment",
            "between -2 and 2",
        ):
            self.assertIn(token, self.norm)
        context = normalized(
            function_block(self.sql, "n6_ai_strategy_context_load_v1")
        )
        self.assertRegex(
            context,
            r"order by\s*\(\s*financial_rank_score\s*"
            r"\+\s*index_hint_adjustment\s*"
            r"\+\s*board_hint_adjustment\s*\)\s*desc\s*,\s*"
            r"identity_key\s*,\s*source_signal_projection_id",
        )

    def test_shadow_evaluator_has_server_quantity_and_priority_guards(self) -> None:
        evaluator = normalized(
            function_block(
                self.sql,
                "n6_ai_strategy_shadow_evaluate",
            )
        )
        for token in (
            "session_user <> 'n6_ai_agent'",
            "shadow",
            "p_run_bucket",
            "n6_ai_strategy_context_load_v1",
            "56082554c4f1099c9fa265d80f0233fde7459d2748be4c85f69fc198bddfc9e7",
            "n6_ai_investor_strategy_policy_v1",
            "n6_ai_knowledge_bundle_v3",
            "95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b",
            "execution_authorized",
            "public.n6_virtual_position_lot",
            "remaining_quantity > 0",
            "available_trade_date <= p_for_trade_date",
            "lot_status in ('available', 'locked_t1')",
            "server_sellable_quantity < 100",
            "period_clear_priority",
            "pending_clear",
            "pending_clear_continue",
            "source_signal_projection_id",
            "primary_trigger_period",
            "up_sell_reference_period",
            "source_adapter = 'mootdx.std'",
            "quote.fetched_at >= quote.quote_minute",
            "( quote.quote_minute at time zone 'asia/shanghai' )::time",
            "( quote.fetched_at at time zone 'asia/shanghai' )::time",
            "get diagnostics inserted_count = row_count",
            "on conflict do nothing",
            "signal.strategy_context_version = "
            "'n6_ai_investor_strategy_policy_v1'",
            "signal.reference_target_price = "
            "position_row.locked_target_price",
            "target_source_reference_price",
            "target_source_signal_id > 0",
            "positive_episode_lot_quantity",
            "invalid_positive_episode_lot_count",
            "sellable_lot_state_hash",
            "lot.virtual_account_id <> authority.virtual_account_id",
            "shadow_strategy_position_lot_invariant_failed",
            "shadow_strategy_episode_mismatch",
            "from public.common_trade_calendar calendar",
            "calendar.trade_date = pg_catalog.to_char( "
            "p_for_trade_date, 'yyyymmdd' )",
            "calendar.is_open = true",
            "'status', 'not_open_trade_date'",
            "'context_knowledge_bundle_sha256', "
            "live_context_bundle_hash",
            "'strategy_workset_hash', "
            "strategy_context->>'strategy_workset_hash'",
            "join public.n6_strategy strategy",
            "strategy.strategy_id = snapshot.strategy_id",
            "strategy.principal_id = snapshot.principal_id",
            "strategy.status = 'active'",
            "snapshot.workset_hash = "
            "strategy_context->>'base_snapshot_workset_hash'",
            "for update of account",
        ):
            self.assertIn(token, evaluator)
        self.assertEqual(
            evaluator.count("join public.user_projection_run"),
            3,
        )
        self.assertEqual(
            evaluator.count("projection_run.source_layer = 'n5_action'"),
            3,
        )
        self.assertEqual(
            evaluator.count("projection_run.status = 'passed'"),
            3,
        )
        self.assertEqual(
            evaluator.count(
                "projection_run.quality_summary_json "
                "->>'b_track_signal_projection' = 'passed'"
            ),
            3,
        )
        self.assertNotIn(
            "projection_run.status in ('passed', 'ready')",
            evaluator,
        )
        self.assertIn(
            "'qualification_reason', case when "
            "qualification.pending_clear_blocked then "
            "'pending_clear_same_account_identity' else 'qualified' end",
            evaluator,
        )
        self.assertIn(
            "not qualification.pending_clear_blocked",
            evaluator,
        )
        self.assertEqual(
            evaluator.count("pending_clear_completed_at ="),
            1,
        )
        self.assertLess(
            evaluator.index("with closed_position as"),
            evaluator.index("for candidate in"),
        )
        self.assertLess(
            evaluator.index(
                "get diagnostics completed_episode_count = row_count"
            ),
            evaluator.index("for candidate in"),
        )
        self.assertLess(
            evaluator.index("for position_row in"),
            evaluator.index("for candidate in"),
        )
        self.assertLess(
            evaluator.index("set pending_clear = true"),
            evaluator.index("for candidate in"),
        )
        candidate_block = evaluator.split(
            "for candidate in", 1
        )[1].split("end loop", 1)[0]
        self.assertNotIn(
            "episode.strategy_id = authority.strategy_id",
            candidate_block,
        )
        completion_block = evaluator.split(
            "with closed_position as", 1
        )[1].split("for position_row in", 1)[0]
        self.assertNotIn(
            "episode.strategy_id = authority.strategy_id",
            completion_block,
        )
        self.assertIn(
            "authority.source_signal_projection_ids_json "
            "@> pg_catalog.jsonb_build_array( "
            "signal.source_signal_projection_id )",
            candidate_block,
        )
        self.assertNotIn("target_source := null", evaluator)
        self.assertNotIn("sell_source := null", evaluator)
        self.assertNotIn("quote_row := null", evaluator)
        self.assertRegex(
            evaluator,
            r"if\s+position_row\.target_price_source_signal_projection_id\s*"
            r">\s*0\s+then\s+select",
        )
        self.assertLess(
            evaluator.index("shadow_strategy_position_lot_invariant_failed"),
            evaluator.index("insert into public.n6_ai_strategy_action"),
        )
        self.assertLess(
            evaluator.index("'status', 'not_open_trade_date'"),
            evaluator.index(
                "strategy_context := "
                "public.n6_ai_strategy_context_load_v1"
            ),
        )
        for token in (
            "episode_row.ai_user_id is distinct from authority.ai_user_id",
            "episode_row.principal_id is distinct from authority.principal_id",
            "episode_row.principal_type is distinct from 'ai_user'",
            "episode_row.virtual_account_id is distinct from "
            "authority.virtual_account_id",
            "episode_row.virtual_position_id is distinct from "
            "position_row.virtual_position_id",
            "episode_row.holding_episode_no is distinct from "
            "position_row.holding_episode_no",
            "episode_row.episode_status is distinct from 'open'",
            "'action_family', case",
            "then 'clear'",
            "'sellable_lot_state_hash', sellable_lot_state_hash",
            "'for_trade_date', case when action_type = 'target_reduce' "
            "then p_for_trade_date else null end",
        ):
            self.assertIn(token, evaluator)
        self.assertNotIn(
            "episode_row.strategy_id is distinct from authority.strategy_id",
            evaluator,
        )
        self.assertIn(
            "episode_row.strategy_id, authority.virtual_account_id",
            evaluator,
        )
        self.assertNotIn(
            "'for_trade_date', p_for_trade_date, 'action_family'",
            evaluator,
        )
        self.assertRegex(
            evaluator,
            r"jsonb_agg\s*\(\s*pg_catalog\.jsonb_build_array\s*\("
            r".*?lot\.virtual_position_lot_id.*?"
            r"order by lot\.virtual_position_lot_id",
        )
        self.assertRegex(
            evaluator,
            r"local_strategy_time\s+between\s+time\s+'09:30'\s+and\s+"
            r"time\s+'11:30'.*local_strategy_time\s+between\s+"
            r"time\s+'13:00'\s+and\s+time\s+'15:00'",
        )
        self.assertRegex(
            evaluator,
            r"pg_catalog\.floor\s*\(\s*server_sellable_quantity\s*/\s*"
            r"3\s*/\s*100\s*\)\s*\*\s*100",
        )
        for forbidden_target in (
            "public.n6_virtual_trade_proposal",
            "public.n6_virtual_order",
            "public.n6_virtual_trade",
            "public.n6_virtual_position_event",
            "public.n6_virtual_cash_ledger",
            "public.n6_virtual_cash_snapshot",
        ):
            self.assertNotRegex(
                evaluator,
                rf"\b(?:insert into|update|delete from)\s+"
                rf"{re.escape(forbidden_target)}\b",
            )

    def test_shadow_evaluator_freezes_period_clear_before_t1_wait(self) -> None:
        evaluator = normalized(
            function_block(
                self.sql,
                "n6_ai_strategy_shadow_evaluate",
            )
        )
        signal_lookup = evaluator.index(
            "select signal.source_signal_projection_id "
            "into sell_source_signal_id"
        )
        pending_update = evaluator.index(
            "set pending_clear = true"
        )
        t1_wait = evaluator.index(
            "if server_sellable_quantity <= 0 then continue"
        )
        self.assertLess(signal_lookup, t1_wait)
        self.assertLess(pending_update, t1_wait)

    def test_shadow_evaluator_completes_pending_clear_only_after_closed_position(
        self,
    ) -> None:
        evaluator = normalized(
            function_block(
                self.sql,
                "n6_ai_strategy_shadow_evaluate",
            )
        )
        completion_update = evaluator.index(
            "set pending_clear = false, "
            "episode_status = 'closed', "
            "pending_clear_completed_at = pg_catalog.clock_timestamp()"
        )
        position_loop = evaluator.index("for position_row in")
        self.assertLess(completion_update, position_loop)
        completion = evaluator.split(
            "with closed_position as", 1
        )[1].split("for position_row in", 1)[0]
        required_tokens = (
            "closed_position as",
            "position.position_status = 'closed_virtual'",
            "position.quantity = 0",
            "position.available_quantity = 0",
            "position.locked_quantity = 0",
            "position.quality_status = 'passed'",
            "for share of position",
            "episode.pending_clear = true",
            "episode.pending_clear_completed_at is null",
            "episode.episode_status = 'open'",
            "episode.ai_user_id = authority.ai_user_id",
            "episode.principal_id = authority.principal_id",
            "episode.principal_type = 'ai_user'",
            "episode.virtual_account_id = "
            "closed_position.virtual_account_id",
            "episode.virtual_position_id = "
            "closed_position.virtual_position_id",
            "episode.identity_key = closed_position.identity_key",
            "episode.holding_episode_no = "
            "closed_position.holding_episode_no",
            "and exists ( select 1 from "
            "public.n6_virtual_position_lot lot",
            "and not exists ( select 1 from "
            "public.n6_virtual_position_lot lot",
            "lot.virtual_account_id is distinct from "
            "closed_position.virtual_account_id",
            "lot.principal_id is distinct from authority.principal_id",
            "lot.principal_type is distinct from 'ai_user'",
            "lot.identity_key is distinct from "
            "closed_position.identity_key",
            "lot.remaining_quantity <> 0",
            "lot.lot_status <> 'closed'",
            "get diagnostics completed_episode_count = row_count",
        )

        def assert_completion_contract(candidate: str) -> None:
            for token in required_tokens:
                self.assertIn(token, candidate)

        assert_completion_contract(
            "closed_position as " + completion
        )
        for token in required_tokens:
            with self.subTest(removed_token=token):
                mutated = (
                    "closed_position as " + completion
                ).replace(token, "", 1)
                with self.assertRaises(AssertionError):
                    assert_completion_contract(mutated)
        self.assertIn(
            "'completed_strategy_episode_count', "
            "completed_episode_count",
            evaluator,
        )
        self.assertNotIn(
            "episode.strategy_id = authority.strategy_id",
            completion,
        )
        self.assertNotIn("episode.policy_version =", completion)
        self.assertNotIn("episode.policy_hash =", completion)

    def test_period_clear_and_action_evidence_bind_frozen_snapshot(self):
        evaluator = normalized(
            function_block(
                self.sql,
                "n6_ai_strategy_shadow_evaluate",
            )
        )
        sell_lookup = evaluator.split(
            "sell_source_signal_id := null", 1
        )[1].split("period_clear_priority :=", 1)[0]
        self.assertIn(
            "authority.source_signal_projection_ids_json "
            "@> pg_catalog.jsonb_build_array( "
            "signal.source_signal_projection_id )",
            sell_lookup,
        )
        action_values = evaluator.split(
            "insert into public.n6_ai_strategy_action", 1
        )[1].split("on conflict do nothing", 1)[0]
        self.assertIn(
            "case when action_type = 'period_clear' "
            "then sell_source_signal_id "
            "when action_type = 'pending_clear_continue' "
            "then episode_row.pending_clear_source_signal_projection_id "
            "else null end",
            action_values,
        )
        self.assertIn(
            "'strategy_workset_hash', "
            "strategy_context->>'strategy_workset_hash'",
            evaluator.split("return pg_catalog.jsonb_build_object", 1)[1],
        )

    def test_shadow_evaluator_binds_current_server_five_minute_bucket(
        self,
    ) -> None:
        evaluator = normalized(
            function_block(
                self.sql,
                "n6_ai_strategy_shadow_evaluate",
            )
        )
        self.assertIn("current_strategy_run_bucket", evaluator)
        self.assertIn(
            "p_run_bucket is distinct from current_strategy_run_bucket",
            evaluator,
        )

    def test_proposal_extension_is_nullable_and_source_constrained(self) -> None:
        for token in (
            "add column strategy_action_id bigint",
            "references public.n6_ai_strategy_action",
            "ai_target_reduce",
            "ai_period_clear",
            "ai_pending_clear",
            "n6_virtual_trade_proposal_059_strategy_action_ck",
        ):
            self.assertIn(token, self.norm)
        self.assertRegex(
            self.norm,
            r"source_type\s+in\s*\(\s*'ai_target_reduce'\s*,\s*"
            r"'ai_period_clear'\s*,\s*'ai_pending_clear'\s*\)",
        )

    def test_dormant_executor_functions_fail_closed(self) -> None:
        for name in (
            "n6_ai_strategy_proposal_create_confirm_v1",
            "n6_ai_executor_strategy_action_apply_v1",
        ):
            block = normalized(function_block(self.sql, name))
            self.assertIn("security definer", block)
            self.assertIn("set search_path = pg_catalog", block)
            self.assertIn("session_user <> 'n6_virtual_executor'", block)
            self.assertIn(
                "execution_activated constant boolean := false",
                block,
            )
            self.assertIn("strategy_execution_not_activated", block)

    def test_execute_grants_are_exact_and_public_web_have_none(self) -> None:
        for signature in AI_FUNCTIONS:
            self.assertIn(
                f"grant execute on function public.{signature} "
                "to n6_ai_agent;",
                self.compact,
            )
        self.assertNotIn(
            "grant execute on function public."
            "n6_ai_strategy_context_load_v1(text,date,integer,text) "
            "to n6_ai_agent;",
            self.compact,
        )
        for signature in EXECUTOR_FUNCTIONS:
            self.assertIn(
                f"grant execute on function public.{signature} "
                "to n6_virtual_executor;",
                self.compact,
            )
        self.assertNotRegex(
            self.compact,
            r"grant execute on function public\."
            r"n6_ai_strategy_proposal_create_confirm_v1\(jsonb\) "
            r"to n6_ai_agent",
        )
        self.assertNotRegex(
            self.compact,
            r"grant (?:select|insert|update|delete|references|trigger|usage)"
            r".* to n6_ai_agent",
        )
        for role in ("public", "n6_btrack_web"):
            self.assertRegex(
                self.compact,
                rf"revoke all on function public\."
                rf"n6_ai_strategy_shadow_evaluate\(date,text,text\).*from "
                rf"(?:[^;]*,\s*)?{role}(?:\s*,[^;]*)?;",
            )
        for table in NEW_TABLES:
            self.assertIn(
                f"revoke all on table public.{table} from public,"
                "n6_ai_agent,n6_btrack_web,n6_virtual_executor;",
                self.compact,
            )
            self.assertIn(
                f"revoke all on sequence public.{table}_"
                f"{'strategy_episode_id' if table.endswith('episode') else 'strategy_action_id' if table.endswith('action') else 'candidate_rank_audit_id'}"
                "_seq from public,n6_ai_agent,n6_btrack_web,"
                "n6_virtual_executor;",
                self.compact,
            )

    def test_postflight_acl_contract_is_exact_and_fail_closed(self) -> None:
        postflight = normalized(
            self.sql.split("DO $postflight$", 1)[1].split(
                "$postflight$;", 1
            )[0]
        )
        function_matrix = (
            (
                "public.n6_ai_strategy_context_load_v1"
                "(text,date,integer,text)",
                "none",
            ),
            (
                "public.n6_ai_strategy_shadow_evaluate(date,text,text)",
                "n6_ai_agent",
            ),
            (
                "public.n6_ai_strategy_proposal_create_confirm_v1(jsonb)",
                "n6_virtual_executor",
            ),
            (
                "public.n6_ai_executor_strategy_action_apply_v1"
                "(bigint,text)",
                "n6_virtual_executor",
            ),
            (
                "public.n6_ai_shared_strategy_fields_capture_v1()",
                "none",
            ),
            (
                "public."
                "n6_ai_strategy_episode_locked_fields_immutable_v1()",
                "none",
            ),
        )
        role_names = (
            "n6_ai_agent",
            "n6_btrack_web",
            "n6_virtual_executor",
        )
        sequence_names = tuple(
            f"{table}_"
            f"{'strategy_episode_id' if table.endswith('episode') else 'strategy_action_id' if table.endswith('action') else 'candidate_rank_audit_id'}"
            "_seq"
            for table in NEW_TABLES
        )
        table_privileges = (
            "'select', 'insert', 'update', 'delete', 'truncate', "
            "'references', 'trigger'"
        )
        sequence_privileges = "'usage', 'select', 'update'"
        function_acl_allowlist = (
            "and function_acl.grantee <> function_row.proowner and ( "
            "allowed_role_oid is null or function_acl.grantee is distinct "
            "from allowed_role_oid or function_acl.privilege_type <> "
            "'execute' or function_acl.is_grantable = true )"
        )
        table_acl_allowlist = (
            "where relation.oid = relation_oid "
            "and table_acl.grantee <> relation.relowner;"
        )
        sequence_acl_allowlist = (
            "where relation.oid = relation_oid "
            "and sequence_acl.grantee <> relation.relowner;"
        )

        def assert_postflight_acl_contract(candidate: str) -> None:
            for signature, allowed_role in function_matrix:
                self.assertIn(signature, candidate)
                self.assertEqual(candidate.count(signature), 2)
                self.assertIn(
                    f"('{signature}'::text, '{allowed_role}'::text)",
                    candidate,
                )
            for role_name in role_names:
                self.assertIn(f"('{role_name}'::text)", candidate)
                self.assertEqual(
                    candidate.count(f"('{role_name}'::text)"),
                    3,
                )
            for table_name in NEW_TABLES:
                self.assertIn(
                    f"('public.{table_name}'::text)", candidate
                )
            for sequence_name in sequence_names:
                self.assertIn(
                    f"('public.{sequence_name}'::text)", candidate
                )
            for token in (
                "pg_catalog.aclexplode(",
                "pg_catalog.acldefault('f', function_row.proowner)",
                "public_acl.grantee = 0",
                "public_acl.privilege_type = 'execute'",
                "direct_acl.grantee = role_oid",
                "direct_acl.privilege_type = 'execute'",
                "direct_acl.is_grantable = true",
                "unexpected_acl_count integer",
                "function_acl.grantee <> function_row.proowner",
                "function_acl.grantee is distinct from allowed_role_oid",
                "function_acl.privilege_type <> 'execute'",
                "function_acl.is_grantable = true",
                "pg_catalog.has_function_privilege(",
                "direct_execute_count <> 1",
                "direct_grantable_count <> 0",
                "direct_execute_count <> 0",
                "059_postflight_function_acl_matrix_drift",
                "relation_kind is distinct from 'r'",
                "pg_catalog.acldefault('r', relation.relowner)",
                "table_acl.grantee <> relation.relowner",
                "pg_catalog.has_table_privilege(",
                "059_postflight_table_acl_drift",
                "relation_kind is distinct from 's'",
                "pg_catalog.acldefault('s', relation.relowner)",
                "sequence_acl.grantee <> relation.relowner",
                "pg_catalog.has_sequence_privilege(",
                "059_postflight_sequence_acl_drift",
            ):
                self.assertIn(token, candidate)
            self.assertEqual(candidate.count("pg_catalog.aclexplode("), 8)
            self.assertEqual(
                candidate.count(
                    "pg_catalog.acldefault('f', function_row.proowner)"
                ),
                4,
            )
            self.assertEqual(
                candidate.count(
                    "pg_catalog.acldefault('r', relation.relowner)"
                ),
                2,
            )
            self.assertEqual(
                candidate.count(
                    "pg_catalog.acldefault('s', relation.relowner)"
                ),
                2,
            )
            self.assertEqual(
                candidate.count("pg_catalog.has_function_privilege("),
                2,
            )
            self.assertEqual(
                candidate.count("public_acl.grantee = 0"),
                3,
            )
            self.assertEqual(candidate.count(table_privileges), 2)
            self.assertEqual(candidate.count(sequence_privileges), 2)
            self.assertEqual(candidate.count(function_acl_allowlist), 1)
            self.assertEqual(candidate.count(table_acl_allowlist), 1)
            self.assertEqual(
                candidate.count(sequence_acl_allowlist),
                1,
            )
            self.assertEqual(
                candidate.count(
                    "if public_privilege_count <> 0 then"
                ),
                3,
            )
            self.assertEqual(
                candidate.count(
                    "if not pg_catalog.has_function_privilege("
                ),
                1,
            )
            self.assertEqual(
                candidate.count(
                    "elsif pg_catalog.has_function_privilege("
                ),
                1,
            )
            self.assertEqual(
                candidate.count("if pg_catalog.has_table_privilege("),
                1,
            )
            self.assertEqual(
                candidate.count(
                    "if pg_catalog.has_sequence_privilege("
                ),
                1,
            )
            self.assertEqual(
                candidate.count("if unexpected_acl_count <> 0 then"),
                3,
            )

        assert_postflight_acl_contract(postflight)

        removable_tokens = tuple(
            signature for signature, _ in function_matrix
        ) + tuple(
            f"('{role_name}'::text)" for role_name in role_names
        ) + tuple(
            f"('public.{table_name}'::text)" for table_name in NEW_TABLES
        ) + tuple(
            f"('public.{sequence_name}'::text)"
            for sequence_name in sequence_names
        )
        for token in removable_tokens:
            with self.subTest(removed=token):
                mutated = postflight.replace(token, "", 1)
                self.assertNotEqual(mutated, postflight)
                with self.assertRaises(AssertionError):
                    assert_postflight_acl_contract(mutated)

        for signature, allowed_role in function_matrix:
            matrix_entry = (
                f"('{signature}'::text, '{allowed_role}'::text)"
            )
            with self.subTest(removed_function_grant=signature):
                mutated = postflight.replace(matrix_entry, "", 1)
                self.assertNotEqual(mutated, postflight)
                with self.assertRaises(AssertionError):
                    assert_postflight_acl_contract(mutated)
            replacement_role = (
                "n6_btrack_web"
                if allowed_role == "n6_ai_agent"
                else "n6_ai_agent"
            )
            with self.subTest(wrong_function_grant=signature):
                mutated = postflight.replace(
                    matrix_entry,
                    f"('{signature}'::text, "
                    f"'{replacement_role}'::text)",
                    1,
                )
                self.assertNotEqual(mutated, postflight)
                with self.assertRaises(AssertionError):
                    assert_postflight_acl_contract(mutated)

        for privilege_name in (
            "select",
            "insert",
            "update",
            "delete",
            "truncate",
            "references",
            "trigger",
        ):
            with self.subTest(removed_table_privilege=privilege_name):
                mutated_privileges = table_privileges.replace(
                    f"'{privilege_name}'", "'bogus'", 1
                )
                mutated = postflight.replace(
                    table_privileges, mutated_privileges, 1
                )
                self.assertNotEqual(mutated, postflight)
                with self.assertRaises(AssertionError):
                    assert_postflight_acl_contract(mutated)
        for privilege_name in ("usage", "select", "update"):
            with self.subTest(removed_sequence_privilege=privilege_name):
                mutated_privileges = sequence_privileges.replace(
                    f"'{privilege_name}'", "'bogus'", 1
                )
                mutated = postflight.replace(
                    sequence_privileges, mutated_privileges, 1
                )
                self.assertNotEqual(mutated, postflight)
                with self.assertRaises(AssertionError):
                    assert_postflight_acl_contract(mutated)

        for branch in (
            "if public_privilege_count <> 0 then",
            "if not pg_catalog.has_function_privilege(",
            "elsif pg_catalog.has_function_privilege(",
            "if pg_catalog.has_table_privilege(",
            "if pg_catalog.has_sequence_privilege(",
            "if unexpected_acl_count <> 0 then",
        ):
            with self.subTest(removed_result_consumer=branch):
                mutated = postflight.replace(branch, "if false then", 1)
                self.assertNotEqual(mutated, postflight)
                with self.assertRaises(AssertionError):
                    assert_postflight_acl_contract(mutated)

        unexpected_grantee_mutations = (
            (
                "and function_acl.grantee <> function_row.proowner",
                "and function_acl.grantee <> function_row.proowner "
                "and function_acl.grantee <> 424242",
            ),
            (
                "and table_acl.grantee <> relation.relowner",
                "and table_acl.grantee <> relation.relowner "
                "and table_acl.grantee <> 424242",
            ),
            (
                "and sequence_acl.grantee <> relation.relowner",
                "and sequence_acl.grantee <> relation.relowner "
                "and sequence_acl.grantee <> 424242",
            ),
        )
        for old, replacement in unexpected_grantee_mutations:
            with self.subTest(injected_unknown_grantee=old):
                mutated = postflight.replace(old, replacement, 1)
                self.assertNotEqual(mutated, postflight)
                with self.assertRaises(AssertionError):
                    assert_postflight_acl_contract(mutated)

        mutations = (
            (
                "('public.n6_ai_strategy_shadow_evaluate"
                "(date,text,text)'::text, 'n6_ai_agent'::text)",
                "('public.n6_ai_strategy_shadow_evaluate"
                "(date,text,text)'::text, 'n6_btrack_web'::text)",
            ),
            (
                "('public.n6_ai_strategy_context_load_v1"
                "(text,date,integer,text)'::text, 'none'::text)",
                "('public.n6_ai_strategy_context_load_v1"
                "(text,date,integer,text)'::text, "
                "'n6_ai_agent'::text)",
            ),
            ("public_acl.grantee = 0", "public_acl.grantee <> 0"),
            (
                "pg_catalog.has_function_privilege(",
                "pg_catalog.has_table_privilege(",
            ),
            (
                "pg_catalog.aclexplode(",
                "pg_catalog.aclcontains(",
            ),
            (
                "pg_catalog.acldefault('s', relation.relowner)",
                "pg_catalog.acldefault('r', relation.relowner)",
            ),
            (
                "direct_acl.is_grantable = true",
                "direct_acl.is_grantable = false",
            ),
            (
                "function_acl.grantee is distinct from allowed_role_oid",
                "function_acl.grantee = allowed_role_oid",
            ),
            (
                "function_acl.grantee <> function_row.proowner",
                "function_acl.grantee = function_row.proowner",
            ),
            (
                "table_acl.grantee <> relation.relowner",
                "table_acl.grantee = relation.relowner",
            ),
            (
                "sequence_acl.grantee <> relation.relowner",
                "sequence_acl.grantee = relation.relowner",
            ),
            (
                "pg_catalog.has_table_privilege(",
                "pg_catalog.has_sequence_privilege(",
            ),
            (
                "pg_catalog.has_sequence_privilege(",
                "pg_catalog.has_table_privilege(",
            ),
        )
        for old, replacement in mutations:
            with self.subTest(mutation=old):
                mutated = postflight.replace(old, replacement, 1)
                self.assertNotEqual(mutated, postflight)
                with self.assertRaises(AssertionError):
                    assert_postflight_acl_contract(mutated)

    def test_dml_allowlist_and_forbidden_sources(self) -> None:
        targets = {
            target.lower()
            for target in re.findall(
                r"(?im)^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
                r"(?:public\.)?([a-z][a-z0-9_]*)",
                self.sql,
            )
        }
        self.assertLessEqual(
            targets,
            {
                "n6_ai_position_strategy_episode",
                "n6_ai_strategy_action",
                "n6_ai_candidate_rank_audit",
                "n6_ai_shared_signal_projection",
            },
        )
        for forbidden in (
            "stock_condition_basis",
            "index_condition_basis",
            "board_condition_basis",
            "condition_pool",
            "minute_target_scope",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_checkpoint",
            "n3_",
            "n4_",
            "execute immediate",
        ):
            self.assertNotIn(forbidden, self.norm)
        self.assertNotRegex(
            self.norm,
            r"(?:from|join|update|insert into|delete from)\s+"
            r"(?:public\.)?n[1-5]_[a-z0-9_]+",
        )

    def test_rollback_is_fail_closed_and_preserves_history(self) -> None:
        self.assertTrue(self.rollback_code_norm.startswith("begin;"))
        self.assertTrue(self.rollback_code_norm.endswith("commit;"))
        for table in (
            "public.n6_ai_position_strategy_episode",
            "public.n6_ai_strategy_action",
            "public.n6_ai_candidate_rank_audit",
            "public.n6_virtual_trade_proposal",
            "public.n6_virtual_order",
            "public.n6_virtual_trade",
        ):
            self.assertIn(f"lock table {table}", self.rollback_norm)
        for blocker in (
            "059_rollback_blocked_by_strategy_history",
            "059_rollback_blocked_by_strategy_proposal",
            "059_rollback_blocked_by_strategy_order_or_trade",
            "059_rollback_blocked_by_processing_action",
            "059_rollback_blocked_by_pending_clear",
        ):
            self.assertIn(blocker, self.rollback_norm)
        self.assertNotRegex(self.rollback_norm, r"\bdelete\s+from\b")
        self.assertNotRegex(self.rollback_norm, r"\btruncate\b")
        for table in reversed(NEW_TABLES):
            self.assertIn(f"drop table public.{table}", self.rollback_norm)
        self.assertIn(
            "add constraint n6_virtual_trade_proposal_055_actor_ck",
            self.rollback_norm,
        )
        self.assertIn(
            "add constraint n6_virtual_trade_proposal_055_source_type_ck",
            self.rollback_norm,
        )

    def test_contract_freezes_policy_choices_and_inactive_runtime(self) -> None:
        for token in (
            "implementation_status=implemented_not_migrated",
            "runtime_status=inactive",
            "shadow_runtime_authorized=false",
            "autonomous_trading_authorized=false",
            "real_trading_authorized=false",
            "highest_live_migration=058",
            "candidate_migration=059",
            "period_clear_priority",
            "latest approved membership <= for_trade_date",
            "floor(server_sellable_quantity / 100) * 100",
            "remaining 1..99",
            "T+1",
            "300",
            "N3N6Q",
            "no N1-N5 direct access",
            "no proposal/order/trade/position/cash DML in Shadow",
            "separate future activation gate",
            "context_loader_bundle_sha256="
            "1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc",
            "promoted_knowledge_bundle_sha256="
            "95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b",
            "context_knowledge_bundle_sha256",
            "condition_projection_context.fields",
        ):
            self.assertIn(token, self.contract)


if __name__ == "__main__":
    unittest.main()
