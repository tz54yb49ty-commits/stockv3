from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

from tests.test_n6_ai_qualified_extrema_function_fix_schema import (
    FUNCTIONS as EXTREMA_FUNCTIONS,
    FUNCTION_HEADER,
    function_block,
    function_body,
    normalized,
    top_level_function_blocks,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "sql/061_n6_ai_shadow_decision_risk_state_and_qualified_extrema_fix.sql"
)
ROLLBACK = (
    ROOT
    / "sql/061_n6_ai_shadow_decision_risk_state_and_qualified_extrema_fix_rollback.sql"
)
SOURCE_055 = ROOT / "sql/055_n6_ai_agent_v1_schema.sql"
SOURCE_058 = ROOT / "sql/058_n6_ai_context_memory_hash_contract.sql"
SOURCE_060 = ROOT / "sql/060_n6_ai_qualified_extrema_function_fix.sql"
ROLLBACK_060 = ROOT / "sql/060_n6_ai_qualified_extrema_function_fix_rollback.sql"

DECISION_NAME = "n6_ai_agent_shadow_decision_record"
DECISION_SIGNATURE = "n6_ai_agent_shadow_decision_record(jsonb)"
DECISION_SOURCE_SHA = (
    "8bd6ed7e55ebd3f84178089e64684a66b3b2cbbf03b4f3a8115b997479b953cb"
)
DECISION_FIXED_SHA = (
    "32b5e4c480f89f4bda964e71ccc910150fe0fb8f489ad4f5c89315fa3be72951"
)
FUNCTION_NAMES = set(EXTREMA_FUNCTIONS) | {DECISION_NAME}
EXPECTED_ALLOWED_ROLES = {
    "n6_ai_agent_daily_summary_record(jsonb)": "n6_ai_agent",
    "n6_ai_agent_context_load(text,date,integer)": None,
    "n6_ai_agent_proposal_create_confirm(jsonb)": "n6_ai_agent",
    "n6_ai_executor_risk_recheck(bigint,text)": "n6_virtual_executor",
    "n6_ai_strategy_shadow_evaluate(date,text,text)": "n6_ai_agent",
    "n6_ai_agent_shadow_decision_record(jsonb)": "n6_ai_agent",
}

OLD_LOOKUP = """  SELECT decision.ai_decision_id,
         decision.server_risk_allowed,
         decision.server_risk_reason
    INTO target_decision_id, target_risk_allowed, target_risk_reason
  FROM public.n6_ai_decision decision
  WHERE decision.idempotency_key = target_idempotency_key;
  IF target_decision_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'already_recorded',
      'decision_id', target_decision_id,
      'server_risk_allowed', target_risk_allowed,
      'server_risk_reason', target_risk_reason
    );
  END IF;"""

FIXED_LOOKUP = """  SELECT decision.ai_decision_id,
         decision.server_risk_allowed,
         decision.server_risk_reason
    INTO existing_decision_id, existing_server_risk_allowed,
         existing_server_risk_reason
  FROM public.n6_ai_decision decision
  WHERE decision.idempotency_key = target_idempotency_key;
  IF existing_decision_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true,
      'status', 'already_recorded',
      'decision_id', existing_decision_id,
      'server_risk_allowed', existing_server_risk_allowed,
      'server_risk_reason', existing_server_risk_reason
    );
  END IF;"""


def expected_fixed_decision_block(source_055: str) -> str:
    source = function_block(source_055, DECISION_NAME)
    if hashlib.sha256(function_body(source).encode()).hexdigest() != (
        DECISION_SOURCE_SHA
    ):
        raise AssertionError("decision authority body hash mismatch")
    declaration = "  target_decision_id bigint;\n"
    if source.count(declaration) != 1 or source.count(OLD_LOOKUP) != 1:
        raise AssertionError("decision authority patch points missing or polluted")
    fixed = source.replace(
        declaration,
        declaration
        + "  existing_decision_id bigint;\n"
        + "  existing_server_risk_allowed boolean;\n"
        + "  existing_server_risk_reason text;\n",
        1,
    ).replace(OLD_LOOKUP, FIXED_LOOKUP, 1)
    if hashlib.sha256(function_body(fixed).encode()).hexdigest() != (
        DECISION_FIXED_SHA
    ):
        raise AssertionError("fixed decision body hash mismatch")
    return fixed


def section(sql: str, tag: str) -> str:
    start_marker = "DO $" + tag + "$"
    end_marker = "$" + tag + "$;"
    start = sql.find(start_marker)
    end = sql.find(end_marker, start)
    if start < 0 or end < 0:
        raise AssertionError(f"missing {tag}")
    return sql[start : end + len(end_marker)]


def without_function_bodies(sql: str) -> str:
    result = sql
    for name in FUNCTION_NAMES:
        blocks = top_level_function_blocks(result, name)
        if len(blocks) != 1:
            raise AssertionError(
                f"expected one top-level definition for {name}, found {len(blocks)}"
            )
        result = result.replace(
            blocks[0],
            f"CREATE OR REPLACE FUNCTION public.{name};",
            1,
        )
    return result


def validate_058_context_load_acl_authority(source_058: str) -> None:
    old_revoke = re.findall(
        r"REVOKE\s+EXECUTE\s+ON\s+FUNCTION\s+"
        r"public\.n6_ai_agent_context_load\s*\(\s*"
        r"text\s*,\s*date\s*,\s*integer\s*\)\s+"
        r"FROM\s+n6_ai_agent\s*;",
        source_058,
        flags=re.IGNORECASE,
    )
    v2_grant = re.findall(
        r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+"
        r"public\.n6_ai_agent_context_load_v2\s*\(\s*"
        r"text\s*,\s*date\s*,\s*integer\s*,\s*text\s*\)\s+"
        r"TO\s+n6_ai_agent\s*;",
        source_058,
        flags=re.IGNORECASE,
    )
    old_grant = re.findall(
        r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+"
        r"public\.n6_ai_agent_context_load\s*\(\s*"
        r"text\s*,\s*date\s*,\s*integer\s*\)\s+"
        r"TO\s+n6_ai_agent\s*;",
        source_058,
        flags=re.IGNORECASE,
    )
    if len(old_revoke) != 1 or len(v2_grant) != 1 or old_grant:
        raise AssertionError("058 context_load ACL authority mismatch")


def validate_gate_acl_expectations(section_text: str) -> None:
    for signature, allowed_role in EXPECTED_ALLOWED_ROLES.items():
        matches = [
            line
            for line in section_text.splitlines()
            if f"('{signature}'" in line
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"ACL expectation signature mismatch: {signature}"
            )
        expected_value = (
            "NULL::text"
            if allowed_role is None
            else f"'{allowed_role}'"
        )
        if not re.search(
            rf",\s*{re.escape(expected_value)}\)\s*,?\s*$",
            matches[0],
        ):
            raise AssertionError(f"ACL expectation drift: {signature}")


def validate_attributes(section_text: str) -> None:
    for token in (
        "owner_name = 'ashare_v3_user'",
        "language_name = 'plpgsql'",
        "function_proc.prosecdef",
        "not function_proc.proisstrict",
        "not function_proc.proleakproof",
        "function_proc.provolatile = 'v'",
        "function_proc.proparallel = 'u'",
        "search_path=pg_catalog",
        "function_proc.proacl",
        "pg_catalog.aclexplode(",
        "pg_catalog.acldefault(",
        "function_acl.privilege_type = 'execute'",
        "not function_acl.is_grantable",
        "allowed_role_oid := null;",
        "if expected.allowed_role is not null then",
        "expected.allowed_role is null",
        "and allowed_role_oid is null",
        "expected.allowed_role is not null",
        "and allowed_role_oid is not null",
        "function_acl.grantee = function_proc.owner_oid",
    ):
        if token not in section_text.lower():
            raise AssertionError(f"missing function attribute/ACL lock: {token}")
    if section_text.lower().count("allowed_role_oid := null;") != 1:
        raise AssertionError("allowed role OID must reset once per gate loop")
    if "function_acl.grantee in (" in section_text.lower():
        raise AssertionError("nullable allowed role uses unsafe IN predicate")
    validate_gate_acl_expectations(section_text)


def validate_contract(
    migration: str,
    rollback: str,
    source_055: str,
    source_058: str,
    source_060: str,
    rollback_060: str,
) -> None:
    validate_058_context_load_acl_authority(source_058)
    for label, sql in (("migration", migration), ("rollback", rollback)):
        sql_norm = normalized(sql)
        if not sql_norm.startswith("begin;") or not sql_norm.endswith("commit;"):
            raise AssertionError(f"{label} transaction boundary missing")
        preflight_end = sql.lower().find("$preflight$;")
        first_ddl = sql.lower().find("create or replace function public.")
        if preflight_end < 0 or first_ddl < 0 or preflight_end >= first_ddl:
            raise AssertionError(f"{label} preflight must precede DDL")
        names = [
            match.group("name").lower()
            for match in FUNCTION_HEADER.finditer(sql)
        ]
        if set(names) != FUNCTION_NAMES or len(names) != 6:
            raise AssertionError(f"{label} must replace exact six functions")
        for name in FUNCTION_NAMES:
            if len(top_level_function_blocks(sql, name)) != 1:
                raise AssertionError(
                    f"{label} expected one definition for {name}"
                )

    for name, data in EXTREMA_FUNCTIONS.items():
        forward = function_block(migration, name)
        reviewed = function_block(source_060, name)
        restored = function_block(rollback, name)
        reviewed_rollback = function_block(rollback_060, name)
        if forward != reviewed:
            raise AssertionError(f"060 fixed body drift: {name}")
        if restored != reviewed_rollback:
            raise AssertionError(f"060 rollback body drift: {name}")
        if hashlib.sha256(function_body(forward).encode()).hexdigest() != (
            data["fixed_sha"]
        ):
            raise AssertionError(f"extrema fixed SHA mismatch: {name}")
        if hashlib.sha256(function_body(restored).encode()).hexdigest() != (
            data["old_sha"]
        ):
            raise AssertionError(f"extrema rollback SHA mismatch: {name}")

    decision_source = function_block(source_055, DECISION_NAME)
    decision_fixed = expected_fixed_decision_block(source_055)
    if function_block(migration, DECISION_NAME) != decision_fixed:
        raise AssertionError("decision fix exceeds isolated patch")
    if function_block(rollback, DECISION_NAME) != decision_source:
        raise AssertionError("decision rollback differs from byte authority")

    migration_decision = function_block(migration, DECISION_NAME)
    for declaration in (
        "existing_decision_id bigint;",
        "existing_server_risk_allowed boolean;",
        "existing_server_risk_reason text;",
    ):
        if migration_decision.count(declaration) != 1:
            raise AssertionError(f"missing isolated variable: {declaration}")
    lookup_start = migration_decision.index(
        "  SELECT decision.ai_decision_id,"
    )
    lookup_end = migration_decision.index(
        "\n\n  INSERT INTO public.n6_ai_decision_run",
        lookup_start,
    )
    lookup = migration_decision[lookup_start:lookup_end]
    if FIXED_LOOKUP not in lookup:
        raise AssertionError("duplicate lookup does not use isolated variables")
    if (
        "target_risk_allowed" in lookup
        or "target_risk_reason" in lookup
        or "target_decision_id" in lookup
    ):
        raise AssertionError("duplicate lookup overwrites computed target state")
    hold_assignment = migration_decision.index(
        "    target_risk_allowed := true;"
    )
    if hold_assignment >= lookup_start:
        raise AssertionError("hold risk state must be computed before lookup")
    for token in (
        "'decision_id', existing_decision_id",
        "'server_risk_allowed', existing_server_risk_allowed",
        "'server_risk_reason', existing_server_risk_reason",
    ):
        if token not in lookup:
            raise AssertionError(f"duplicate return drift: {token}")

    if "pg_catalog.greatest(" in migration:
        raise AssertionError("qualified greatest remains in migration")
    if "pg_catalog.least(" in migration:
        raise AssertionError("qualified least remains in migration")

    migration_preflight = section(migration, "preflight")
    rollback_preflight = section(rollback, "preflight")
    migration_postflight = section(migration, "postflight")
    rollback_postflight = section(rollback, "postflight")
    for gate in (
        migration_preflight,
        rollback_preflight,
        migration_postflight,
        rollback_postflight,
    ):
        validate_attributes(gate)

    for token in (
        "061_partial_or_source_mismatch",
        "061_already_applied",
        "source_count <> 6",
        "fixed_count = 6",
        "fixed_count <> 0",
    ):
        if token not in migration_preflight:
            raise AssertionError(f"missing migration classification: {token}")
    if "061_rollback_requires_fixed_state" not in rollback_preflight:
        raise AssertionError("rollback does not require exact fixed state")

    expected_pairs = [
        (
            data["signature"],
            data["old_sha"],
            data["fixed_sha"],
        )
        for data in EXTREMA_FUNCTIONS.values()
    ] + [
        (DECISION_SIGNATURE, DECISION_SOURCE_SHA, DECISION_FIXED_SHA)
    ]
    for signature, old_sha, fixed_sha in expected_pairs:
        if (
            signature not in migration_preflight
            or old_sha not in migration_preflight
            or fixed_sha not in migration_preflight
        ):
            raise AssertionError(f"migration SHA lock missing: {signature}")
        if (
            signature not in rollback_preflight
            or fixed_sha not in rollback_preflight
        ):
            raise AssertionError(f"rollback fixed lock missing: {signature}")
        if old_sha in rollback_preflight:
            raise AssertionError(
                f"rollback preflight accepts non-fixed state: {signature}"
            )
        if (
            signature not in migration_postflight
            or fixed_sha not in migration_postflight
        ):
            raise AssertionError(f"migration postflight missing: {signature}")
        if (
            signature not in rollback_postflight
            or old_sha not in rollback_postflight
        ):
            raise AssertionError(f"rollback postflight missing: {signature}")

    for label, sql in (("migration", migration), ("rollback", rollback)):
        top_level = without_function_bodies(sql)
        if re.search(
            r"(?i)\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b",
            top_level,
        ):
            raise AssertionError(f"{label} top-level business DML forbidden")
        if re.search(
            r"(?i)\b(?:GRANT|REVOKE|ALTER|DROP|"
            r"CREATE\s+(?:TABLE|INDEX|TRIGGER|ROLE|SCHEMA|SEQUENCE))\b",
            top_level,
        ):
            raise AssertionError(f"{label} forbidden DDL/ACL mutation")
        if re.search(r"(?is)\bEXECUTE\s+(?:format\s*\(|[^;]+)", top_level):
            raise AssertionError(f"{label} dynamic SQL forbidden")


class N6AiShadowDecisionRiskStateAndQualifiedExtremaFixTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        paths = (
            MIGRATION,
            ROLLBACK,
            SOURCE_055,
            SOURCE_058,
            SOURCE_060,
            ROLLBACK_060,
        )
        missing = [
            str(path.relative_to(ROOT)) for path in paths if not path.is_file()
        ]
        if missing:
            raise AssertionError(f"061 authority/artifacts missing: {missing}")
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")
        cls.source_055 = SOURCE_055.read_text(encoding="utf-8")
        cls.source_058 = SOURCE_058.read_text(encoding="utf-8")
        cls.source_060 = SOURCE_060.read_text(encoding="utf-8")
        cls.rollback_060 = ROLLBACK_060.read_text(encoding="utf-8")

    def validate(
        self,
        migration: str | None = None,
        rollback: str | None = None,
        source_055: str | None = None,
        source_058: str | None = None,
        source_060: str | None = None,
        rollback_060: str | None = None,
    ) -> None:
        validate_contract(
            self.migration if migration is None else migration,
            self.rollback if rollback is None else rollback,
            self.source_055 if source_055 is None else source_055,
            self.source_058 if source_058 is None else source_058,
            self.source_060 if source_060 is None else source_060,
            self.rollback_060 if rollback_060 is None else rollback_060,
        )

    def test_exact_six_atomic_function_replacements(self) -> None:
        self.validate()

    def test_hold_state_survives_no_row_and_duplicate_returns_existing(self) -> None:
        decision = function_block(self.migration, DECISION_NAME)
        self.assertIn("target_risk_allowed := true;", decision)
        self.assertIn(FIXED_LOOKUP, decision)
        self.assertNotIn(OLD_LOOKUP, decision)
        lookup = decision[
            decision.index("  SELECT decision.ai_decision_id,") :
            decision.index(
                "\n\n  INSERT INTO public.n6_ai_decision_run"
            )
        ]
        self.assertNotIn("target_risk_allowed", lookup)
        self.assertNotIn("target_risk_reason", lookup)

    def test_function_properties_acl_and_byte_authorities(self) -> None:
        validate_058_context_load_acl_authority(self.source_058)
        for name in EXTREMA_FUNCTIONS:
            self.assertEqual(
                function_block(self.migration, name),
                function_block(self.source_060, name),
            )
            self.assertEqual(
                function_block(self.rollback, name),
                function_block(self.rollback_060, name),
            )
        self.assertEqual(
            function_block(self.rollback, DECISION_NAME),
            function_block(self.source_055, DECISION_NAME),
        )

    def test_058_acl_authority_and_acl_pollution_fail_closed(self) -> None:
        revoke = (
            "REVOKE EXECUTE ON FUNCTION "
            "public.n6_ai_agent_context_load(\n"
            "  text,date,integer\n"
            ") FROM n6_ai_agent;"
        )
        with self.assertRaisesRegex(
            AssertionError, "058 context_load ACL authority mismatch"
        ):
            self.validate(
                source_058=self.source_058.replace(revoke, "", 1)
            )

        migration_preflight = section(self.migration, "preflight")
        context_line = next(
            line
            for line in migration_preflight.splitlines()
            if f"('n6_ai_agent_context_load(text,date,integer)'" in line
        )
        with self.assertRaisesRegex(
            AssertionError, "ACL expectation drift"
        ):
            self.validate(
                migration=self.migration.replace(
                    context_line,
                    context_line.replace(
                        "NULL::text", "'n6_ai_agent'", 1
                    ),
                    1,
                )
            )

        daily_line = next(
            line
            for line in migration_preflight.splitlines()
            if f"('n6_ai_agent_daily_summary_record(jsonb)'" in line
        )
        with self.assertRaisesRegex(
            AssertionError, "ACL expectation drift"
        ):
            self.validate(
                migration=self.migration.replace(
                    daily_line,
                    daily_line.replace(
                        "'n6_ai_agent')", "NULL::text)", 1
                    ),
                    1,
                )
            )

        risk_line = next(
            line
            for line in migration_preflight.splitlines()
            if f"('n6_ai_executor_risk_recheck(bigint,text)'" in line
        )
        with self.assertRaisesRegex(
            AssertionError, "ACL expectation drift"
        ):
            self.validate(
                migration=self.migration.replace(
                    risk_line,
                    risk_line.replace(
                        "'n6_virtual_executor'",
                        "'n6_ai_agent'",
                        1,
                    ),
                    1,
                )
            )

    def test_no_qualified_special_expression_or_top_level_business_dml(
        self,
    ) -> None:
        self.assertNotIn("pg_catalog.greatest(", self.migration)
        self.assertNotIn("pg_catalog.least(", self.migration)
        for sql in (self.migration, self.rollback):
            top_level = without_function_bodies(sql)
            self.assertIsNone(
                re.search(
                    r"(?i)\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b",
                    top_level,
                )
            )

    def test_missing_and_polluted_authority_fail_closed(self) -> None:
        authority = function_block(self.source_055, DECISION_NAME)
        with self.assertRaisesRegex(AssertionError, "found 0"):
            self.validate(
                source_055=self.source_055.replace(authority, "", 1)
            )
        polluted = authority.replace(
            "  target_decision_id bigint;",
            "  target_decision_id bigint; ",
            1,
        )
        with self.assertRaisesRegex(
            AssertionError, "decision authority body hash mismatch"
        ):
            self.validate(
                source_055=self.source_055.replace(
                    authority, polluted, 1
                )
            )

    def test_function_and_decision_mutations_fail_closed(self) -> None:
        extrema_name = "n6_ai_agent_context_load"
        extrema = function_block(self.migration, extrema_name)
        with self.assertRaises(AssertionError):
            self.validate(
                migration=self.migration.replace(extrema, "", 1)
            )
        with self.assertRaisesRegex(AssertionError, "060 fixed body drift"):
            self.validate(
                migration=self.migration.replace(
                    extrema,
                    extrema.replace(
                        "RETURN pg_catalog.jsonb_build_object(",
                        "RETURN  pg_catalog.jsonb_build_object(",
                        1,
                    ),
                    1,
                )
            )
        with self.assertRaisesRegex(
            AssertionError, "decision fix exceeds isolated patch"
        ):
            self.validate(
                migration=self.migration.replace(
                    "INTO existing_decision_id, "
                    "existing_server_risk_allowed,",
                    "INTO existing_decision_id, target_risk_allowed,",
                    1,
                )
            )

    def test_gate_hash_attribute_transaction_and_dml_mutations_fail_closed(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            AssertionError, "migration SHA lock missing"
        ):
            self.validate(
                migration=self.migration.replace(
                    DECISION_SOURCE_SHA, "0" * 64, 1
                )
            )
        with self.assertRaisesRegex(
            AssertionError, "missing function attribute/ACL lock"
        ):
            self.validate(
                migration=self.migration.replace(
                    "function_proc.proparallel = 'u'",
                    "function_proc.proparallel = 's'",
                    1,
                )
            )
        with self.assertRaisesRegex(
            AssertionError, "missing function attribute/ACL lock"
        ):
            self.validate(
                migration=self.migration.replace(
                    "    allowed_role_oid := NULL;\n",
                    "",
                    1,
                )
            )
        with self.assertRaisesRegex(
            AssertionError, "transaction boundary missing"
        ):
            self.validate(migration=self.migration.replace("BEGIN;", "", 1))
        with self.assertRaisesRegex(
            AssertionError, "top-level business DML forbidden"
        ):
            self.validate(
                migration=self.migration.replace(
                    "\nCOMMIT;",
                    "\nDELETE FROM public.n6_ai_decision;\nCOMMIT;",
                    1,
                )
            )


if __name__ == "__main__":
    unittest.main()
