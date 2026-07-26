from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/062_n6_ai_shadow_observation_run_audit.sql"
ROLLBACK = (
    ROOT / "sql/062_n6_ai_shadow_observation_run_audit_rollback.sql"
)
SOURCE_055 = ROOT / "sql/055_n6_ai_agent_v1_schema.sql"
SOURCE_061 = (
    ROOT
    / "sql/061_n6_ai_shadow_decision_risk_state_and_qualified_extrema_fix.sql"
)

TABLE = "public.n6_ai_shadow_observation_run_audit"
SEQUENCE = "public.n6_ai_shadow_observation_run_audit_audit_id_seq"
RECORD_FUNCTION = "n6_ai_shadow_observation_run_audit_record"
GUARD_FUNCTION = "n6_ai_shadow_observation_run_audit_append_only_guard"


def normalized(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower()).strip()


def table_block(sql: str) -> str:
    match = re.search(
        rf"(?is)\bCREATE\s+TABLE\s+{re.escape(TABLE)}\s*\("
        r"(?P<body>.*?)\n\);\s*\n",
        sql,
    )
    if match is None:
        raise AssertionError("062 audit table definition missing")
    return match.group("body")


def function_block(sql: str, name: str) -> str:
    match = re.search(
        rf"(?ims)^CREATE\s+OR\s+REPLACE\s+FUNCTION\s+"
        rf"(?:\n)?public\.{re.escape(name)}\s*\("
        r".*?^\$function\$;",
        sql,
    )
    if match is None:
        raise AssertionError(f"062 function definition missing: {name}")
    return match.group(0)


def assert_record_authority_contract(block: str) -> None:
    norm = normalized(block)
    required = (
        "session_user <> 'n6_ai_agent'",
        "current_user <> 'ashare_v3_user'",
        "from public.n6_ai_user ai",
        "join public.n6_principal principal",
        "principal.principal_type = 'ai_user'",
        "principal.principal_status = 'active'",
        "principal.owner_user_id is null",
        "ai.status in ('sandbox_only', 'active')",
        "actor.authority_count <> 1",
    )
    missing = [token for token in required if token not in norm]
    if missing:
        raise AssertionError(f"missing fail-closed authority tokens: {missing}")
    if "current_setting(" in norm or "set_config(" in norm:
        raise AssertionError("client GUC authority path is forbidden")


def assert_decision_run_reference_resolution(block: str) -> None:
    norm = normalized(block)
    resolver_start = norm.find(
        "if target_decision_id is null "
        "and target_decision_run_id is not null then"
    )
    state_start = norm.find(
        "if target_observation_run_id !~", resolver_start
    )
    insert_start = norm.find(
        "insert into public.n6_ai_shadow_observation_run_audit",
        state_start,
    )
    if min(resolver_start, state_start, insert_start) < 0:
        raise AssertionError("decision reference resolver ordering missing")
    if not resolver_start < state_start < insert_start:
        raise AssertionError("decision reference resolver ordering invalid")
    resolver = norm[resolver_start:state_start]
    required = (
        "resolved_decision_count <> 1",
        "resolved_decision_run_id is null",
        "target_decision_run_id is not null "
        "and target_decision_run_id is distinct from "
        "resolved_decision_run_id",
        "target_decision_run_id := resolved_decision_run_id",
        "where decision.ai_decision_id = target_decision_id",
    )
    missing = [token for token in required if token not in resolver]
    if missing:
        raise AssertionError(
            f"decision reference resolver fail-closed token missing: {missing}"
        )
    relations = set(
        re.findall(r"\b(?:from|join)\s+(public\.[a-z0-9_]+)", resolver)
    )
    if relations != {
        "public.n6_ai_decision",
        "public.n6_ai_decision_run",
    }:
        raise AssertionError(
            f"decision reference resolver relation pollution: {relations}"
        )
    if (
        "join public.n6_ai_decision_run decision_run "
        "on decision_run.ai_decision_run_id = "
        "decision.ai_decision_run_id"
        not in resolver
    ):
        raise AssertionError("decision reference resolver association missing")
    if "execute " in resolver or "format(" in resolver:
        raise AssertionError("dynamic SQL is forbidden in decision resolver")
    for token in (
        "(target_decision_run_id is null) <> "
        "(target_decision_id is null)",
        "decision.ai_decision_run_id = target_decision_run_id",
    ):
        if token not in norm:
            raise AssertionError(
                f"final decision reference validation missing: {token}"
            )


NO_NEW_INPUT_SQL_EXPECTATIONS = (
    (
        "decision_call_attempted",
        "decision_call_attempted = false",
        "target_decision_call_attempted is distinct from false",
    ),
    (
        "structure_valid",
        "structure_valid is null",
        "target_structure_valid is not null",
    ),
    (
        "context_snapshot_id",
        "context_snapshot_id is null",
        "target_context_snapshot_id is not null",
    ),
    (
        "decision_run_id",
        "decision_run_id is null",
        "target_decision_run_id is not null",
    ),
    (
        "decision_id",
        "decision_id is null",
        "target_decision_id is not null",
    ),
    (
        "server_risk_allowed",
        "server_risk_allowed is null",
        "target_server_risk_allowed is not null",
    ),
    (
        "server_risk_reason",
        "server_risk_reason is null",
        "target_server_risk_reason is not null",
    ),
    (
        "proposal_created",
        "proposal_created = false",
        "target_proposal_created is distinct from false",
    ),
    (
        "proposal_created_count",
        "proposal_created_count = 0",
        "target_proposal_created_count <> 0",
    ),
    (
        "order_created_count",
        "order_created_count = 0",
        "target_order_created_count <> 0",
    ),
    (
        "trade_created_count",
        "trade_created_count = 0",
        "target_trade_created_count <> 0",
    ),
    (
        "position_mutation_count",
        "position_mutation_count = 0",
        "target_position_mutation_count <> 0",
    ),
    (
        "lot_mutation_count",
        "lot_mutation_count = 0",
        "target_lot_mutation_count <> 0",
    ),
    (
        "cash_mutation_count",
        "cash_mutation_count = 0",
        "target_cash_mutation_count <> 0",
    ),
)


def no_new_input_sql_segments(sql: str) -> tuple[str, str]:
    table_start = sql.index(
        "CONSTRAINT n6_ai_shadow_observation_062_no_new_input_ck"
    )
    table_end = sql.index(
        "CONSTRAINT n6_ai_shadow_observation_062_side_effect_ck",
        table_start,
    )
    record = function_block(sql, RECORD_FUNCTION)
    function_start = record.index(
        "target_one_shot_status = 'no_new_input'"
    )
    function_end = record.index(
        "OR target_proposal_created_count < 0",
        function_start,
    )
    return (
        normalized(sql[table_start:table_end]),
        normalized(record[function_start:function_end]),
    )


def assert_no_new_input_sql_contract(
    table_segment: str, function_segment: str
) -> None:
    if "one_shot_status <> 'no_new_input'" not in table_segment:
        raise AssertionError("table no_new_input status gate missing")
    if "target_one_shot_status = 'no_new_input'" not in function_segment:
        raise AssertionError("function no_new_input status gate missing")
    for field, table_clause, function_clause in (
        NO_NEW_INPUT_SQL_EXPECTATIONS
    ):
        if table_clause not in table_segment:
            raise AssertionError(f"table no_new_input field missing: {field}")
        if function_clause not in function_segment:
            raise AssertionError(
                f"function no_new_input field missing: {field}"
            )


def no_new_input_matrix_accepts(row: dict[str, object]) -> bool:
    if row["one_shot_status"] != "no_new_input":
        return True
    return (
        row["decision_call_attempted"] is False
        and row["structure_valid"] is None
        and row["context_snapshot_id"] is None
        and row["decision_run_id"] is None
        and row["decision_id"] is None
        and row["server_risk_allowed"] is None
        and row["server_risk_reason"] is None
        and row["proposal_created"] is False
        and row["proposal_created_count"] == 0
        and row["order_created_count"] == 0
        and row["trade_created_count"] == 0
        and row["position_mutation_count"] == 0
        and row["lot_mutation_count"] == 0
        and row["cash_mutation_count"] == 0
    )


def valid_no_new_input_row() -> dict[str, object]:
    return {
        "one_shot_status": "no_new_input",
        "decision_call_attempted": False,
        "structure_valid": None,
        "context_snapshot_id": None,
        "decision_run_id": None,
        "decision_id": None,
        "server_risk_allowed": None,
        "server_risk_reason": None,
        "proposal_created": False,
        "proposal_created_count": 0,
        "order_created_count": 0,
        "trade_created_count": 0,
        "position_mutation_count": 0,
        "lot_mutation_count": 0,
        "cash_mutation_count": 0,
    }


class N6AiShadowObservationRunAuditSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        paths = (MIGRATION, ROLLBACK, SOURCE_055, SOURCE_061)
        missing = [
            str(path.relative_to(ROOT)) for path in paths if not path.is_file()
        ]
        if missing:
            raise AssertionError(f"062 authority/artifacts missing: {missing}")
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")
        cls.source_055 = SOURCE_055.read_text(encoding="utf-8")
        cls.source_061 = SOURCE_061.read_text(encoding="utf-8")
        cls.migration_norm = normalized(cls.migration)
        cls.rollback_norm = normalized(cls.rollback)
        cls.table = table_block(cls.migration)
        cls.table_norm = normalized(cls.table)
        cls.record_function = function_block(
            cls.migration, RECORD_FUNCTION
        )
        cls.guard_function = function_block(cls.migration, GUARD_FUNCTION)
        (
            cls.no_new_input_table_segment,
            cls.no_new_input_function_segment,
        ) = no_new_input_sql_segments(cls.migration)

    def test_single_transaction_and_offline_boundary(self) -> None:
        self.assertEqual(self.migration_norm.count("begin;"), 1)
        self.assertEqual(self.migration_norm.count("commit;"), 1)
        self.assertTrue(self.migration_norm.startswith("-- n6 ai shadow"))
        for forbidden in (
            "create role ",
            "alter role ",
            "create database ",
            "dblink",
            "postgres_fdw",
            "launchagent",
            "startinterval",
        ):
            self.assertNotIn(forbidden, self.migration_norm)

    def test_every_dollar_block_has_outer_end_terminator(self) -> None:
        for label, sql in (
            ("migration", self.migration),
            ("rollback", self.rollback),
        ):
            open_tags = re.findall(
                r"^DO\s+(\$[a-z_]+\$)|^AS\s+(\$function\$)",
                sql,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            expected_blocks = sum(1 for pair in open_tags if any(pair))
            terminated_blocks = len(
                re.findall(
                    r"^END;\s*\n(\$[a-z_]+\$);",
                    sql,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
            )
            self.assertEqual(
                terminated_blocks,
                expected_blocks,
                f"{label} has unterminated outer PL/pgSQL block",
            )

    def test_preflight_rejects_already_partial_and_unknown_state(self) -> None:
        for token in (
            "062_already_applied",
            "062_partial_state_rejected",
            "062_unknown_state_rejected",
            "target_object_count = 8",
            "target_object_count <> 0",
            "unknown_object_count <> 0",
        ):
            self.assertIn(token, self.migration_norm)

    def test_preflight_requires_published_055_through_061_authority(
        self,
    ) -> None:
        for token in (
            "public.n6_btrack_resolve_authority(text)",
            "public.n6_ai_agent_shadow_decision_record(jsonb)",
            "062_requires_live_055_through_061",
            "062_source_061_authority_mismatch",
            "32b5e4c480f89f4bda964e71ccc910150fe0fb8f489ad4f5c89315fa3be72951",
        ):
            self.assertIn(token, self.migration_norm)

    def test_audit_relation_and_identity_are_declared_once(self) -> None:
        self.assertEqual(
            len(
                re.findall(
                    rf"(?im)^CREATE\s+TABLE\s+{re.escape(TABLE)}\b",
                    self.migration,
                )
            ),
            1,
        )
        self.assertIn(
            "audit_id bigint generated always as identity primary key",
            self.table_norm,
        )
        self.assertIn(SEQUENCE, self.migration_norm)
        self.assertIn("owner to ashare_v3_user", self.migration_norm)

    def test_frozen_audit_columns_exist(self) -> None:
        required_columns = (
            "observation_run_id",
            "dedup_key",
            "trade_date",
            "ai_user_id",
            "principal_id",
            "provider",
            "model",
            "system_fingerprint",
            "one_shot_status",
            "identity_probe_succeeded",
            "decision_call_attempted",
            "structure_valid",
            "context_snapshot_id",
            "decision_run_id",
            "decision_id",
            "server_risk_allowed",
            "server_risk_reason",
            "proposal_created",
            "proposal_created_count",
            "order_created_count",
            "trade_created_count",
            "position_mutation_count",
            "lot_mutation_count",
            "cash_mutation_count",
            "input_token_count",
            "output_token_count",
            "total_token_count",
            "cache_hit_token_count",
            "cache_miss_token_count",
            "latency_ms",
            "started_at",
            "finished_at",
            "created_at",
        )
        for column in required_columns:
            self.assertRegex(
                self.table,
                rf"(?im)^\s*{re.escape(column)}\s+",
            )

    def test_sensitive_content_columns_are_absent(self) -> None:
        declared_columns = set(
            re.findall(
                r"(?im)^\s{2}([a-z][a-z0-9_]*)\s+"
                r"(?:bigint|text|date|boolean|timestamptz)",
                self.table,
            )
        )
        forbidden = {
            "prompt",
            "prompt_text",
            "content",
            "raw_content",
            "reasoning",
            "reasoning_content",
            "credential",
            "api_key",
            "session",
            "session_id",
            "session_token",
            "session_token_hash",
            "human_user_id",
            "owner_user_id",
            "human_private_data",
        }
        self.assertTrue(forbidden.isdisjoint(declared_columns))

    def test_probe_and_attempt_constraint_matrix_is_fail_closed(self) -> None:
        for token in (
            "identity_probe_succeeded = true",
            "decision_call_attempted = false",
            "structure_valid is null",
            "decision_call_attempted = true",
            "structure_valid is not null",
            "structure_valid is distinct from false",
        ):
            self.assertIn(token, self.table_norm)

    def test_no_new_input_positive_matrix(self) -> None:
        self.assertTrue(no_new_input_matrix_accepts(valid_no_new_input_row()))
        assert_no_new_input_sql_contract(
            self.no_new_input_table_segment,
            self.no_new_input_function_segment,
        )

    def test_no_new_input_each_polluted_field_is_rejected(self) -> None:
        pollution_cases = (
            ("decision_call_attempted", True),
            ("structure_valid", True),
            ("context_snapshot_id", 1),
            ("decision_run_id", 1),
            ("decision_id", 1),
            ("server_risk_allowed", True),
            ("server_risk_reason", "risk_allowed"),
            ("proposal_created", True),
            ("proposal_created_count", 1),
            ("order_created_count", 1),
            ("trade_created_count", 1),
            ("position_mutation_count", 1),
            ("lot_mutation_count", 1),
            ("cash_mutation_count", 1),
        )
        for field, polluted_value in pollution_cases:
            with self.subTest(field=field):
                row = valid_no_new_input_row()
                row[field] = polluted_value
                self.assertFalse(no_new_input_matrix_accepts(row))

    def test_no_new_input_sql_surfaces_are_mutation_locked(self) -> None:
        for field, table_clause, function_clause in (
            NO_NEW_INPUT_SQL_EXPECTATIONS
        ):
            with self.subTest(surface="table", field=field):
                polluted_table = self.no_new_input_table_segment.replace(
                    table_clause, "true", 1
                )
                with self.assertRaisesRegex(
                    AssertionError,
                    rf"table no_new_input field missing: {field}",
                ):
                    assert_no_new_input_sql_contract(
                        polluted_table,
                        self.no_new_input_function_segment,
                    )
            with self.subTest(surface="function", field=field):
                polluted_function = (
                    self.no_new_input_function_segment.replace(
                        function_clause, "false", 1
                    )
                )
                with self.assertRaisesRegex(
                    AssertionError,
                    rf"function no_new_input field missing: {field}",
                ):
                    assert_no_new_input_sql_contract(
                        self.no_new_input_table_segment,
                        polluted_function,
                    )

    def test_non_no_new_input_is_not_forced_to_zero(self) -> None:
        row = valid_no_new_input_row()
        row.update(
            {
                "one_shot_status": "shadow_decision_recorded",
                "decision_call_attempted": True,
                "structure_valid": True,
                "context_snapshot_id": 1,
                "decision_run_id": 1,
                "decision_id": 1,
                "server_risk_allowed": True,
                "server_risk_reason": "risk_allowed",
                "proposal_created": True,
                "proposal_created_count": 1,
                "order_created_count": 1,
                "trade_created_count": 1,
                "position_mutation_count": 1,
                "lot_mutation_count": 1,
                "cash_mutation_count": 1,
            }
        )
        self.assertTrue(no_new_input_matrix_accepts(row))

    def test_invalid_structure_cannot_reference_decision_or_risk(self) -> None:
        constraint = re.search(
            r"(?is)CONSTRAINT\s+"
            r"n6_ai_shadow_observation_062_invalid_structure_ck\s+"
            r"CHECK\s*\((.*?)\n\s*\),",
            self.migration,
        )
        self.assertIsNotNone(constraint)
        body = normalized(constraint.group(1))
        for token in (
            "decision_run_id is null",
            "decision_id is null",
            "server_risk_allowed is null",
            "server_risk_reason is null",
        ):
            self.assertIn(token, body)

    def test_decision_reference_requires_context_and_server_risk(self) -> None:
        for token in (
            "(decision_run_id is null) = (decision_id is null)",
            "decision_call_attempted = true",
            "structure_valid = true",
            "context_snapshot_id is not null",
            "server_risk_allowed is not null",
            "server_risk_reason is not null",
        ):
            self.assertIn(token, self.table_norm)

    def test_side_effect_counts_are_observable_not_silently_zeroed(
        self,
    ) -> None:
        side_effect_start = self.migration.index(
            "CONSTRAINT n6_ai_shadow_observation_062_side_effect_ck"
        )
        side_effect_end = self.migration.index(
            "CONSTRAINT n6_ai_shadow_observation_062_usage_ck",
            side_effect_start,
        )
        side_effect_constraint = normalized(
            self.migration[side_effect_start:side_effect_end]
        )
        for column in (
            "proposal_created_count",
            "order_created_count",
            "trade_created_count",
            "position_mutation_count",
            "lot_mutation_count",
            "cash_mutation_count",
        ):
            self.assertIn(f"{column} >= 0", side_effect_constraint)
            self.assertNotRegex(
                side_effect_constraint,
                rf"\b{re.escape(column)}\s*=\s*0\b",
            )
        self.assertIn(
            "proposal_created = (proposal_created_count > 0)",
            side_effect_constraint,
        )

    def test_provider_fingerprint_usage_cache_and_latency_are_bounded(
        self,
    ) -> None:
        for token in (
            "provider = 'deepseek'",
            "model = 'deepseek-v4-pro'",
            "n6_ai_shadow_observation_062_fingerprint_ck",
            "n6_ai_shadow_observation_062_usage_ck",
            "input_token_count >= 0",
            "output_token_count >= 0",
            "cache_hit_token_count >= 0",
            "cache_miss_token_count >= 0",
            "latency_ms >= 0",
        ):
            self.assertIn(token, self.table_norm)

    def test_only_one_function_is_granted_as_agent_record_entry(self) -> None:
        grant_targets = re.findall(
            r"(?is)\bGRANT\s+EXECUTE\s+ON\s+FUNCTION\s+"
            r"public\.([a-z0-9_]+)\s*\([^;]*?\)\s+"
            r"TO\s+n6_ai_agent\s*;",
            self.migration,
        )
        self.assertEqual(grant_targets, [RECORD_FUNCTION])
        self.assertNotIn(GUARD_FUNCTION, grant_targets)

    def test_record_entry_has_positive_authority_contract(self) -> None:
        assert_record_authority_contract(self.record_function)

    def test_session_user_pollution_mutation_fails_authority_validator(
        self,
    ) -> None:
        polluted = self.record_function.replace(
            "SESSION_USER <> 'n6_ai_agent'",
            "SESSION_USER <> current_setting('app.claimed_role')",
            1,
        )
        with self.assertRaisesRegex(
            AssertionError, "missing fail-closed authority"
        ):
            assert_record_authority_contract(polluted)

    def test_client_guc_pollution_mutation_fails_authority_validator(
        self,
    ) -> None:
        polluted = self.record_function.replace(
            "actor.authority_count <> 1",
            "actor.authority_count <> 1 "
            "OR current_setting('app.ai_user_id', true) IS NULL",
            1,
        )
        with self.assertRaisesRegex(AssertionError, "client GUC"):
            assert_record_authority_contract(polluted)

    def test_missing_authority_mutation_fails_authority_validator(
        self,
    ) -> None:
        missing = self.record_function.replace(
            "actor.authority_count <> 1", "false", 1
        )
        with self.assertRaisesRegex(
            AssertionError, "missing fail-closed authority"
        ):
            assert_record_authority_contract(missing)

    def test_payload_allowlist_and_sensitive_denylist_are_server_side(
        self,
    ) -> None:
        norm = normalized(self.record_function)
        self.assertIn("jsonb_object_keys(p_payload)", norm)
        self.assertIn("p_payload ?& array[", norm)
        self.assertIn("p_payload ?| array[", norm)
        for forbidden_key in (
            "'prompt'",
            "'content'",
            "'reasoning_content'",
            "'credential'",
            "'api_key'",
            "'session_token_hash'",
            "'human_user_id'",
            "'human_private_data'",
        ):
            self.assertIn(forbidden_key, norm)

    def test_time_inputs_and_hash_are_guc_independent(self) -> None:
        norm = normalized(self.record_function)
        self.assertIn("observation_audit_time_format_rejected", norm)
        self.assertIn(
            "coalesce(p_payload->>'trade_date', '') !~ "
            "'^[0-9]{4}-[0-9]{2}-[0-9]{2}$'",
            norm,
        )
        self.assertIn("'started_at_epoch'", norm)
        self.assertIn("'finished_at_epoch'", norm)
        self.assertIn("extract(epoch from target_started_at)", norm)
        self.assertIn(
            "extract(epoch from target_finished_at)",
            norm,
        )
        self.assertNotIn("pg_catalog.extract(", norm)

    def test_reference_validation_uses_server_authority(self) -> None:
        norm = normalized(self.record_function)
        for token in (
            "from public.n6_ai_context_snapshot context_snapshot",
            "from public.n6_ai_decision decision",
            "join public.n6_ai_decision_run decision_run",
            "decision.ai_user_id = actor.ai_user_id",
            "decision.principal_id = actor.principal_id",
            "decision.server_risk_allowed = target_server_risk_allowed",
            "decision.server_risk_reason = target_server_risk_reason",
        ):
            self.assertIn(token, norm)

    def test_decision_run_reference_is_resolved_server_side(self) -> None:
        assert_decision_run_reference_resolution(self.record_function)

    def test_decision_reference_resolver_mutations_fail_closed(self) -> None:
        mutations = (
            (
                "missing_resolver",
                "target_decision_run_id := resolved_decision_run_id;",
                "NULL;",
            ),
            (
                "wrong_relation",
                "JOIN public.n6_ai_decision_run decision_run",
                "JOIN public.n6_ai_context_snapshot decision_run",
            ),
            (
                "non_unique_or_missing_allowed",
                "resolved_decision_count <> 1",
                "resolved_decision_count = 0",
            ),
            (
                "explicit_mismatch_allowed",
                "target_decision_run_id IS DISTINCT FROM\n"
                "               resolved_decision_run_id",
                "target_decision_run_id = resolved_decision_run_id",
            ),
            (
                "only_run_id_allowed",
                "IF target_decision_id IS NULL\n"
                "     AND target_decision_run_id IS NOT NULL THEN",
                "IF target_decision_id IS NOT NULL\n"
                "     AND target_decision_run_id IS NOT NULL THEN",
            ),
            (
                "final_pair_bypassed",
                "(target_decision_run_id IS NULL) <>\n"
                "          (target_decision_id IS NULL)",
                "false",
            ),
            (
                "final_association_bypassed",
                "decision.ai_decision_run_id = target_decision_run_id",
                "true",
            ),
        )
        for name, source, replacement in mutations:
            with self.subTest(name=name):
                self.assertIn(source, self.record_function)
                polluted = self.record_function.replace(
                    source, replacement, 1
                )
                with self.assertRaises(AssertionError):
                    assert_decision_run_reference_resolution(polluted)

    def test_dedup_is_insert_only_and_conflicts_fail_closed(self) -> None:
        norm = normalized(self.record_function)
        for token in (
            "on conflict (dedup_key) do nothing",
            "observation_audit_already_recorded",
            "observation_audit_dedup_conflict",
            "existing_payload_hash = target_payload_hash",
        ):
            self.assertIn(token, norm)
        self.assertNotRegex(
            norm,
            rf"\bupdate\s+{re.escape(TABLE)}\b",
        )

    def test_append_only_guards_update_delete_and_truncate(self) -> None:
        norm = self.migration_norm
        self.assertIn("062_append_only_audit_history", norm)
        self.assertIn(
            "before update or delete on "
            "public.n6_ai_shadow_observation_run_audit",
            norm,
        )
        self.assertIn(
            "before truncate on "
            "public.n6_ai_shadow_observation_run_audit",
            norm,
        )
        self.assertIn("trigger_row.tgtype = 27", norm)
        self.assertIn("trigger_row.tgtype = 34", norm)

    def test_security_definer_search_path_and_owners_are_fixed(self) -> None:
        for block in (self.record_function, self.guard_function):
            norm = normalized(block)
            self.assertIn("language plpgsql", norm)
            self.assertIn("security definer", norm)
            self.assertIn("set search_path = pg_catalog", norm)
        self.assertEqual(
            self.migration_norm.count(
                "owner to ashare_v3_user"
            ),
            4,
        )

    def test_table_and_sequence_have_zero_restricted_role_privileges(
        self,
    ) -> None:
        norm = self.migration_norm
        self.assertIn(f"revoke all on table {TABLE}", norm)
        self.assertIn(f"revoke all on sequence {SEQUENCE}", norm)
        self.assertNotRegex(
            norm,
            r"\bgrant\s+[^;]*\bon\s+(?:table|sequence)\b",
        )
        for token in (
            "pg_catalog.has_table_privilege(",
            "pg_catalog.has_sequence_privilege(",
            "pg_catalog.aclexplode(",
            "pg_catalog.acldefault(",
        ):
            self.assertIn(token, norm)

    def test_function_acl_is_public_closed_agent_only(self) -> None:
        norm = self.migration_norm
        self.assertIn(
            "from public, n6_ai_agent, n6_btrack_web, "
            "n6_virtual_executor",
            norm,
        )
        self.assertIn(
            "grant execute on function "
            "public.n6_ai_shadow_observation_run_audit_record(jsonb) "
            "to n6_ai_agent",
            norm,
        )
        self.assertIn("pg_catalog.has_function_privilege(", norm)
        self.assertIn("direct_execute_count <> 1", norm)
        self.assertIn("direct_grantable_count <> 0", norm)
        self.assertIn(
            "function_acl.grantee = function_row.proowner",
            norm,
        )
        self.assertIn("allowed_role_oid is not null", norm)
        self.assertIn("062_postflight_function_acl_mismatch", norm)
        self.assertIn("062_postflight_function_grant_mismatch", norm)

    def test_migration_dml_is_confined_to_new_audit_relation(self) -> None:
        insert_targets = {
            target.lower()
            for target in re.findall(
                r"(?i)\bINSERT\s+INTO\s+"
                r"(public\.[a-z_][a-z0-9_]*)",
                self.migration,
            )
        }
        self.assertEqual(insert_targets, {TABLE})
        for pattern in (
            r"(?i)\bUPDATE\s+public\.",
            r"(?i)\bDELETE\s+FROM\s+public\.",
            r"(?i)\bTRUNCATE\s+TABLE\s+public\.",
        ):
            self.assertIsNone(re.search(pattern, self.migration))

    def test_rollback_checks_history_before_any_destructive_statement(
        self,
    ) -> None:
        history_gate = self.rollback_norm.index(
            "062_rollback_blocked_by_audit_history"
        )
        first_drop = self.rollback_norm.index("drop trigger")
        self.assertLess(history_gate, first_drop)
        self.assertIn(
            "lock table public.n6_ai_shadow_observation_run_audit "
            "in access exclusive mode",
            self.rollback_norm,
        )

    def test_nonempty_rollback_is_fail_closed_and_never_deletes_history(
        self,
    ) -> None:
        self.assertIn(
            "if exists ( select 1 from "
            "public.n6_ai_shadow_observation_run_audit )",
            self.rollback_norm,
        )
        self.assertIn(
            "062_rollback_blocked_by_audit_history",
            self.rollback_norm,
        )
        for forbidden in (
            f"delete from {TABLE}",
            f"truncate table {TABLE}",
            f"update {TABLE}",
        ):
            self.assertNotIn(forbidden, self.rollback_norm)

    def test_empty_rollback_removes_only_062_objects(self) -> None:
        for token in (
            "revoke execute on function "
            "public.n6_ai_shadow_observation_run_audit_record(jsonb)",
            "drop trigger "
            "trg_062_n6_ai_shadow_observation_append_only_truncate",
            "drop trigger "
            "trg_062_n6_ai_shadow_observation_append_only_row",
            "drop function "
            "public.n6_ai_shadow_observation_run_audit_record(jsonb)",
            "drop function "
            "public.n6_ai_shadow_observation_run_audit_append_only_guard()",
            "drop index public.idx_062_n6_ai_shadow_observation_window",
            "drop index public.idx_062_n6_ai_shadow_observation_dedup",
            f"drop table {TABLE}",
        ):
            self.assertIn(token, self.rollback_norm)
        self.assertIn(
            "drops its owned generated always identity sequence",
            self.rollback_norm,
        )

    def test_rollback_requires_and_reproves_061_source(self) -> None:
        for token in (
            "062_rollback_source_061_mismatch",
            "062_rollback_postflight_source_061_mismatch",
            "32b5e4c480f89f4bda964e71ccc910150fe0fb8f489ad4f5c89315fa3be72951",
        ):
            self.assertIn(token, self.rollback_norm)

    def test_no_055_through_061_object_is_modified(self) -> None:
        combined = f"{self.migration}\n{self.rollback}"
        forbidden_patterns = (
            r"(?is)\bALTER\s+TABLE\s+public\."
            r"(?:n6_ai_user|n6_principal|n6_ai_context_snapshot|"
            r"n6_ai_decision_run|n6_ai_decision)\b",
            r"(?is)\bDROP\s+TABLE\s+public\."
            r"(?:n6_ai_user|n6_principal|n6_ai_context_snapshot|"
            r"n6_ai_decision_run|n6_ai_decision)\b",
            r"(?is)\bCREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\."
            r"(?:n6_btrack_resolve_authority|"
            r"n6_ai_agent_shadow_decision_record)\b",
            r"(?is)\bREVOKE\b[^;]*\bON\s+FUNCTION\s+public\."
            r"(?:n6_btrack_resolve_authority|"
            r"n6_ai_agent_shadow_decision_record)\b",
            r"(?is)\bGRANT\b[^;]*\bON\s+FUNCTION\s+public\."
            r"(?:n6_btrack_resolve_authority|"
            r"n6_ai_agent_shadow_decision_record)\b",
        )
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, combined))

    def test_test_suite_is_static_and_never_connects_to_database(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8").lower()
        for forbidden in (
            "import " + "psycopg",
            "import " + "psycopg2",
            "import " + "sqlalchemy",
            "subprocess" + ".",
            "socket" + ".",
            "create_" + "connection(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
