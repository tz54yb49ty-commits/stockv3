from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/060_n6_ai_qualified_extrema_function_fix.sql"
ROLLBACK = (
    ROOT / "sql/060_n6_ai_qualified_extrema_function_fix_rollback.sql"
)
SOURCE_055 = ROOT / "sql/055_n6_ai_agent_v1_schema.sql"
SOURCE_059 = ROOT / "sql/059_n6_ai_investor_strategy_policy_v1.sql"

FUNCTIONS = {
    "n6_ai_agent_daily_summary_record": {
        "signature": "n6_ai_agent_daily_summary_record(jsonb)",
        "source": SOURCE_055,
        "old_sha": (
            "c8e0928d3afb20535792a82b20270d32d66d466a85d0d112"
            "aefc64fa8f573a5e"
        ),
        "fixed_sha": (
            "235b3913734fda03a3d55822d58f785ae3dad36002c38f473"
            "bfeaad6636f0042"
        ),
        "greatest": 3,
        "least": 0,
    },
    "n6_ai_agent_context_load": {
        "signature": "n6_ai_agent_context_load(text,date,integer)",
        "source": SOURCE_055,
        "old_sha": (
            "bbcd60822e8d18e6731ac0f46e68d2dd545dea08a172f286"
            "55eead4e1444fa84"
        ),
        "fixed_sha": (
            "4dae0563b34df9e066c2c91feb6f3a096a09ea2573a31f2cf"
            "30c71bfe0704993"
        ),
        "greatest": 3,
        "least": 0,
    },
    "n6_ai_agent_proposal_create_confirm": {
        "signature": "n6_ai_agent_proposal_create_confirm(jsonb)",
        "source": SOURCE_055,
        "old_sha": (
            "2bde0f7d24cd88bc2851fb162b8499730560e8959c8f814d"
            "6625a97fe9db063b"
        ),
        "fixed_sha": (
            "aa3806a66ed5fa08b3c497e42cfb0142c61759b796891cf81"
            "d7c041024de05f2"
        ),
        "greatest": 3,
        "least": 0,
    },
    "n6_ai_executor_risk_recheck": {
        "signature": "n6_ai_executor_risk_recheck(bigint,text)",
        "source": SOURCE_055,
        "old_sha": (
            "51faf7163dd35ead8f290c7a0ec17849f56dd0906339b8de4"
            "b7f1c5c932e834c"
        ),
        "fixed_sha": (
            "f42d6750d192321f851626428589fdc342355410b7e1c50a3"
            "3855642661bbf75"
        ),
        "greatest": 3,
        "least": 0,
    },
    "n6_ai_strategy_shadow_evaluate": {
        "signature": "n6_ai_strategy_shadow_evaluate(date,text,text)",
        "source": SOURCE_059,
        "old_sha": (
            "a7cd3200d0c4a226c9ea03fc14e62a03f86877f768d991911"
            "eafc8b7a13c2cb2"
        ),
        "fixed_sha": (
            "fcd1ada453c672c8a2caa5caa4857b15f7d162f2ed5780cda"
            "27c7cd41ad6b474"
        ),
        "greatest": 1,
        "least": 1,
    },
}

FUNCTION_HEADER = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\."
    r"(?P<name>[a-z0-9_]+)\s*\(",
    flags=re.IGNORECASE,
)


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def top_level_function_blocks(sql: str, name: str) -> list[str]:
    headers: list[tuple[int, re.Match[str]]] = []
    position = 0
    state = "normal"
    block_depth = 0
    dollar_delimiter = ""
    while position < len(sql):
        if state == "dollar":
            if sql.startswith(dollar_delimiter, position):
                position += len(dollar_delimiter)
                state = "normal"
            else:
                position += 1
            continue
        if state == "single_quote":
            if sql.startswith("''", position):
                position += 2
            elif sql[position] == "'":
                position += 1
                state = "normal"
            else:
                position += 1
            continue
        if state == "double_quote":
            if sql.startswith('""', position):
                position += 2
            elif sql[position] == '"':
                position += 1
                state = "normal"
            else:
                position += 1
            continue
        if state == "block_comment":
            if sql.startswith("/*", position):
                block_depth += 1
                position += 2
            elif sql.startswith("*/", position):
                block_depth -= 1
                position += 2
                if block_depth == 0:
                    state = "normal"
            else:
                position += 1
            continue

        if position == 0 or sql[position - 1] == "\n":
            statement_start = position
            while (
                statement_start < len(sql)
                and sql[statement_start] in (" ", "\t")
            ):
                statement_start += 1
            header = FUNCTION_HEADER.match(sql, statement_start)
            if header is not None and header.group("name").lower() == name.lower():
                headers.append((position, header))
        if sql.startswith("--", position):
            newline = sql.find("\n", position)
            position = len(sql) if newline < 0 else newline + 1
        elif sql.startswith("/*", position):
            state = "block_comment"
            block_depth = 1
            position += 2
        elif sql[position] == "'":
            state = "single_quote"
            position += 1
        elif sql[position] == '"':
            state = "double_quote"
            position += 1
        elif sql[position] == "$":
            delimiter = re.match(
                r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$",
                sql[position:],
            )
            if delimiter is None:
                position += 1
            else:
                dollar_delimiter = delimiter.group(0)
                state = "dollar"
                position += len(dollar_delimiter)
        else:
            position += 1

    blocks: list[str] = []
    for start, header in headers:
        declaration_tail = sql[header.end():]
        opening = re.search(
            r"(?im)^[ \t]*AS[ \t]+"
            r"(?P<delimiter>\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$)[ \t]*$",
            declaration_tail,
        )
        if opening is None:
            raise AssertionError(f"missing function body delimiter: {name}")
        delimiter = opening.group("delimiter")
        body_start = header.end() + opening.end()
        closing = re.search(
            rf"(?m)^[ \t]*{re.escape(delimiter)};[ \t]*$",
            sql[body_start:],
        )
        if closing is None:
            raise AssertionError(f"unterminated function block: {name}")
        blocks.append(sql[start:body_start + closing.end()])
    return blocks


def function_block(sql: str, name: str) -> str:
    blocks = top_level_function_blocks(sql, name)
    if len(blocks) != 1:
        raise AssertionError(
            f"expected one top-level definition for {name}, found {len(blocks)}"
        )
    return blocks[0]


def function_body(block: str) -> str:
    opening = re.search(
        r"\bAS\s+(?P<delimiter>\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$)",
        block,
        flags=re.IGNORECASE,
    )
    if opening is None:
        raise AssertionError("missing function body delimiter")
    delimiter = opening.group("delimiter")
    closing = block.rfind(delimiter)
    if closing <= opening.end():
        raise AssertionError("unterminated function body")
    return block[opening.end():closing]


def sql_without_function_bodies(value: str) -> str:
    output = value
    for name in FUNCTIONS:
        for block in top_level_function_blocks(output, name):
            output = output.replace(block, "CREATE OR REPLACE FUNCTION;")
    return output


def validate_authority_sources(source_055: str, source_059: str) -> None:
    for name, data in FUNCTIONS.items():
        candidate = source_055 if data["source"] == SOURCE_055 else source_059
        block = function_block(candidate, name)
        body_sha = hashlib.sha256(
            function_body(block).encode("utf-8")
        ).hexdigest()
        if body_sha != data["old_sha"]:
            raise AssertionError(
                f"authoritative old body hash mismatch: {name}"
            )


def validate_contract(migration: str, rollback: str) -> None:
    migration_norm = normalized(migration)
    rollback_norm = normalized(rollback)
    if not migration_norm.startswith("begin;") or not migration_norm.endswith(
        "commit;"
    ):
        raise AssertionError("forward transaction boundary missing")
    if not rollback_norm.startswith("begin;") or not rollback_norm.endswith(
        "commit;"
    ):
        raise AssertionError("rollback transaction boundary missing")

    first_ddl = migration.lower().find("create or replace function public.")
    preflight_end = migration.lower().find("$preflight$;")
    if first_ddl < 0 or preflight_end < 0 or preflight_end >= first_ddl:
        raise AssertionError("preflight must complete before first public DDL")
    rollback_first_ddl = rollback.lower().find(
        "create or replace function public."
    )
    rollback_preflight_end = rollback.lower().find("$preflight$;")
    if (
        rollback_first_ddl < 0
        or rollback_preflight_end < 0
        or rollback_preflight_end >= rollback_first_ddl
    ):
        raise AssertionError("rollback preflight must precede first DDL")

    for text, expected_state, expected_hash_key in (
        (migration, "source", "old_sha"),
        (rollback, "fixed", "fixed_sha"),
    ):
        preflight = text.lower().split("do $preflight$", 1)[1].split(
            "$preflight$;", 1
        )[0]
        for token in (
            "session_user <> 'ashare_v3_user'",
            "current_user <> 'ashare_v3_user'",
            "ashare_v3_user",
            "plpgsql",
            "prosecdef",
            "not function_proc.proisstrict",
            "not function_proc.proleakproof",
            "function_proc.provolatile = 'v'",
            "function_proc.proparallel = 'u'",
            "search_path=pg_catalog",
            "060_already_applied",
            "060_partial_or_source_mismatch",
        ):
            if token not in preflight:
                raise AssertionError(f"missing preflight attribute/branch: {token}")
        if expected_state not in preflight:
            raise AssertionError(f"missing {expected_state} classification")
        for data in FUNCTIONS.values():
            if data["signature"] not in preflight:
                raise AssertionError(
                    f"missing preflight signature: {data['signature']}"
                )
            if data[expected_hash_key] not in preflight:
                raise AssertionError(
                    f"missing preflight hash: {data[expected_hash_key]}"
                )

    for name, data in FUNCTIONS.items():
        source_sql = data["source"].read_text(encoding="utf-8")
        source_block = function_block(source_sql, name)
        forward_block = function_block(migration, name)
        rollback_block = function_block(rollback, name)
        restored_forward = forward_block.replace(
            "GREATEST(", "pg_catalog.greatest("
        ).replace("LEAST(", "pg_catalog.least(")
        if restored_forward != source_block:
            raise AssertionError(f"forward body drift beyond extrema tokens: {name}")
        if rollback_block != source_block:
            raise AssertionError(f"rollback body differs from authority: {name}")

        source_body = function_body(source_block)
        forward_body = function_body(forward_block)
        rollback_body = function_body(rollback_block)
        if hashlib.sha256(source_body.encode()).hexdigest() != data["old_sha"]:
            raise AssertionError(f"authoritative old body hash mismatch: {name}")
        if hashlib.sha256(forward_body.encode()).hexdigest() != data["fixed_sha"]:
            raise AssertionError(f"fixed body hash mismatch: {name}")
        if hashlib.sha256(rollback_body.encode()).hexdigest() != data["old_sha"]:
            raise AssertionError(f"rollback body hash mismatch: {name}")
        if source_body.count("pg_catalog.greatest(") != data["greatest"]:
            raise AssertionError(f"source greatest count mismatch: {name}")
        if source_body.count("pg_catalog.least(") != data["least"]:
            raise AssertionError(f"source least count mismatch: {name}")
        if "pg_catalog.greatest(" in forward_body:
            raise AssertionError(f"qualified greatest remains: {name}")
        if "pg_catalog.least(" in forward_body:
            raise AssertionError(f"qualified least remains: {name}")
        if forward_body.count("GREATEST(") != data["greatest"]:
            raise AssertionError(f"fixed GREATEST count mismatch: {name}")
        if forward_body.count("LEAST(") != data["least"]:
            raise AssertionError(f"fixed LEAST count mismatch: {name}")

    if migration.count("pg_catalog.greatest(") != 0:
        raise AssertionError("qualified greatest remains in forward migration")
    if migration.count("pg_catalog.least(") != 0:
        raise AssertionError("qualified least remains in forward migration")
    if sum(data["greatest"] for data in FUNCTIONS.values()) != 13:
        raise AssertionError("frozen greatest count changed")
    if sum(data["least"] for data in FUNCTIONS.values()) != 1:
        raise AssertionError("frozen least count changed")

    for text, hash_key in ((migration, "fixed_sha"), (rollback, "old_sha")):
        postflight = text.lower().split("do $postflight$", 1)[1].split(
            "$postflight$;", 1
        )[0]
        for token in (
            "ashare_v3_user",
            "plpgsql",
            "prosecdef",
            "not function_proc.proisstrict",
            "not function_proc.proleakproof",
            "function_proc.provolatile = 'v'",
            "function_proc.proparallel = 'u'",
            "search_path=pg_catalog",
            "060_postflight_mismatch",
        ):
            if token not in postflight:
                raise AssertionError(f"missing postflight attribute: {token}")
        for data in FUNCTIONS.values():
            if data["signature"] not in postflight:
                raise AssertionError(
                    f"missing postflight signature: {data['signature']}"
                )
            if data[hash_key] not in postflight:
                raise AssertionError(
                    f"missing postflight hash: {data[hash_key]}"
                )

    for text in (migration, rollback):
        top_level = sql_without_function_bodies(text)
        if re.search(r"(?is)\bEXECUTE\s+(?:format\s*\(|[^;]+)", top_level):
            raise AssertionError("dynamic SQL is forbidden")
        if re.search(
            r"(?i)\b(?:GRANT|REVOKE|ALTER|CREATE\s+(?:TABLE|INDEX|TRIGGER|"
            r"ROLE|SCHEMA|SEQUENCE)|DROP)\b",
            top_level,
        ):
            raise AssertionError("forbidden top-level DDL")
        if re.search(
            r"(?i)\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b",
            top_level,
        ):
            raise AssertionError("top-level business DML is forbidden")
        if re.search(r"(?i)\bexecution_activated\b\s*(?:=|:)\s*true", text):
            raise AssertionError("execution activation is forbidden")
        if re.search(
            r"(?i)\b(?:stock|index|board|common)_(?:daily|raw|condition|"
            r"trigger|action|minute)_",
            top_level,
        ):
            raise AssertionError("N1-N5 raw source expansion is forbidden")


class N6AiQualifiedExtremaFunctionFixSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        missing = [
            str(path.relative_to(ROOT))
            for path in (MIGRATION, ROLLBACK, SOURCE_055, SOURCE_059)
            if not path.is_file()
        ]
        if missing:
            raise AssertionError(f"060 implementation artifacts missing: {missing}")
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_exact_five_authoritative_function_replacements(self) -> None:
        validate_contract(self.migration, self.rollback)
        self.assertEqual(
            set(
                match.group("name").lower()
                for match in FUNCTION_HEADER.finditer(self.migration)
            ),
            set(FUNCTIONS),
        )
        self.assertEqual(
            set(
                match.group("name").lower()
                for match in FUNCTION_HEADER.finditer(self.rollback)
            ),
            set(FUNCTIONS),
        )

    def test_missing_function_and_extra_body_change_fail_closed(self) -> None:
        name = "n6_ai_agent_context_load"
        block = function_block(self.migration, name)
        with self.assertRaisesRegex(AssertionError, "found 0"):
            validate_contract(self.migration.replace(block, ""), self.rollback)
        with self.assertRaisesRegex(AssertionError, "drift beyond extrema"):
            validate_contract(
                self.migration.replace(
                    "RETURN pg_catalog.jsonb_build_object(",
                    "RETURN pg_catalog.jsonb_build_object( ",
                    1,
                ),
                self.rollback,
            )

    def test_missing_or_polluted_authority_fails_closed(self) -> None:
        source_055 = SOURCE_055.read_text(encoding="utf-8")
        source_059 = SOURCE_059.read_text(encoding="utf-8")
        name = "n6_ai_agent_context_load"
        authority_block = function_block(source_055, name)

        with self.assertRaisesRegex(AssertionError, "found 0"):
            validate_authority_sources(
                source_055.replace(authority_block, "", 1),
                source_059,
            )

        polluted_block = authority_block.replace(
            "pg_catalog.greatest(",
            "GREATEST(",
            1,
        )
        with self.assertRaisesRegex(
            AssertionError,
            "authoritative old body hash mismatch",
        ):
            validate_authority_sources(
                source_055.replace(
                    authority_block,
                    polluted_block,
                    1,
                ),
                source_059,
            )

    def test_incorrect_hash_and_missing_preflight_attribute_fail_closed(
        self,
    ) -> None:
        old_hash = FUNCTIONS["n6_ai_agent_context_load"]["old_sha"]
        with self.assertRaisesRegex(AssertionError, "missing preflight hash"):
            validate_contract(
                self.migration.replace(old_hash, "0" * 64),
                self.rollback,
            )
        with self.assertRaisesRegex(AssertionError, "missing preflight attribute"):
            validate_contract(
                self.migration.replace(
                    "function_proc.proparallel = 'u'",
                    "function_proc.proparallel = 's'",
                    1,
                ),
                self.rollback,
            )

    def test_dynamic_sql_and_forbidden_top_level_dml_ddl_fail_closed(
        self,
    ) -> None:
        commit_marker = "\nCOMMIT;"
        mutations = (
            "DO $$ BEGIN EXECUTE 'SELECT 1'; END $$;",
            "INSERT INTO public.n6_ai_decision DEFAULT VALUES;",
            "ALTER FUNCTION public.n6_ai_agent_context_load(text,date,integer) "
            "OWNER TO ashare_v3_user;",
            "GRANT EXECUTE ON FUNCTION "
            "public.n6_ai_agent_context_load(text,date,integer) TO PUBLIC;",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = self.migration.replace(
                    commit_marker,
                    f"\n{mutation}{commit_marker}",
                )
                with self.assertRaises(AssertionError):
                    validate_contract(candidate, self.rollback)


if __name__ == "__main__":
    unittest.main()
