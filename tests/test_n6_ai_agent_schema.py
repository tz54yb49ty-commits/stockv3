from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "sql" / "055_n6_ai_agent_v1_schema.sql"
ROLLBACK_PATH = ROOT / "sql" / "055_n6_ai_agent_v1_schema_rollback.sql"
CONTRACT_PATH = ROOT / "docs" / "N6_AI_AGENT_V1_CONTRACT.json"

TABLES = (
    "n6_ai_shared_signal_projection",
    "n6_ai_context_snapshot",
    "n6_ai_decision_run",
    "n6_ai_decision",
    "n6_ai_daily_summary",
    "n6_ai_strategy_evaluation",
)

FUNCTION_GRANTS = {
    "n6_ai_agent": (
        "n6_ai_agent_context_load(text,date,integer)",
        "n6_ai_agent_shadow_decision_record(jsonb)",
        "n6_ai_agent_proposal_create_confirm(jsonb)",
        "n6_ai_agent_daily_summary_record(jsonb)",
        "n6_ai_agent_strategy_evaluation_record(jsonb)",
        "n6_btrack_ai_public_snapshot(text,integer,integer,integer)",
    ),
    "n6_virtual_executor": (
        "n6_ai_executor_risk_recheck(bigint,text)",
    ),
    "n6_btrack_web": (
        "n6_btrack_ai_public_snapshot(text,integer,integer,integer)",
        "n6_btrack_ai_public_decision_detail(text,bigint)",
    ),
}


def normalized_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


FUNCTION_HEADER = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\."
    r"(?P<name>[a-z0-9_]+)\s*\(",
    flags=re.IGNORECASE,
)
TOP_LEVEL_DO_BLOCK = re.compile(
    r"^[ \t]*DO[ \t]+(?P<delimiter>\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$)"
    r"[ \t]*$\n(?P<body>.*?)"
    r"^[ \t]*(?P=delimiter);[ \t]*$",
    flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
PUBLIC_SESSION_GUARD = re.compile(
    r"\bIF\s+SESSION_USER\s*<>\s*'n6_btrack_web'\s+OR\b"
    r".*?\bTHEN\s+RETURN\s+NULL\s*;\s*END\s+IF\s*;",
    flags=re.IGNORECASE | re.DOTALL,
)
PUBLIC_AUTHORITY_ASSIGNMENT = re.compile(
    r"\bauthority\s*:=\s*public\.n6_btrack_resolve_authority\s*"
    r"\(\s*p_session_token_hash\s*\)\s*;",
    flags=re.IGNORECASE,
)
PUBLIC_AUTHORITY_GUARD = re.compile(
    r"\bIF\s+authority\s+IS\s+NULL\s+OR\s+"
    r"authority\s*->>\s*'principal_status'\s*<>\s*'active'\s+OR\s+"
    r"authority\s*->>\s*'principal_type'\s+NOT\s+IN\s*"
    r"\(\s*'admin'\s*,\s*'human_user'\s*\)\s+"
    r"THEN\s+RETURN\s+NULL\s*;\s*END\s+IF\s*;",
    flags=re.IGNORECASE | re.DOTALL,
)
PUBLIC_AI_PRINCIPAL_SCOPE = re.compile(
    r"\bprincipal\.principal_type\s*=\s*'ai_user'\s+AND\s+"
    r"principal\.principal_status\s*=\s*'active'",
    flags=re.IGNORECASE,
)


def top_level_function_blocks(sql: str, name: str) -> list[str]:
    """Return only dollar-quoted function bodies declared at SQL top level."""
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
            delimiter = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", sql[position:])
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
        end = body_start + closing.end()
        blocks.append(sql[start:end])
    return blocks


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


def sql_code_without_comments_or_dollar_strings(value: str) -> str:
    output: list[str] = []
    position = 0
    state = "normal"
    block_depth = 0
    dollar_delimiter = ""
    while position < len(value):
        if state == "single_quote":
            output.append(value[position])
            if value.startswith("''", position):
                output.append("'")
                position += 2
            elif value[position] == "'":
                position += 1
                state = "normal"
            else:
                position += 1
            continue
        if state == "double_quote":
            output.append(value[position])
            if value.startswith('""', position):
                output.append('"')
                position += 2
            elif value[position] == '"':
                position += 1
                state = "normal"
            else:
                position += 1
            continue
        if state == "dollar":
            if value.startswith(dollar_delimiter, position):
                output.extend(" " * len(dollar_delimiter))
                position += len(dollar_delimiter)
                state = "normal"
            else:
                output.append("\n" if value[position] == "\n" else " ")
                position += 1
            continue
        if state == "block_comment":
            if value.startswith("/*", position):
                output.extend("  ")
                block_depth += 1
                position += 2
            elif value.startswith("*/", position):
                output.extend("  ")
                block_depth -= 1
                position += 2
                if block_depth == 0:
                    state = "normal"
            else:
                output.append("\n" if value[position] == "\n" else " ")
                position += 1
            continue

        if value.startswith("--", position):
            newline = value.find("\n", position)
            if newline < 0:
                output.extend(" " * (len(value) - position))
                break
            output.extend(" " * (newline - position))
            output.append("\n")
            position = newline + 1
        elif value.startswith("/*", position):
            output.extend("  ")
            state = "block_comment"
            block_depth = 1
            position += 2
        elif value[position] == "'":
            output.append("'")
            state = "single_quote"
            position += 1
        elif value[position] == '"':
            output.append('"')
            state = "double_quote"
            position += 1
        elif value[position] == "$":
            delimiter = re.match(
                r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$",
                value[position:],
            )
            if delimiter is None:
                output.append(value[position])
                position += 1
            else:
                dollar_delimiter = delimiter.group(0)
                output.extend(" " * len(dollar_delimiter))
                position += len(dollar_delimiter)
                state = "dollar"
        else:
            output.append(value[position])
            position += 1
    return "".join(output)


def function_block(sql: str, name: str) -> str:
    blocks = top_level_function_blocks(sql, name)
    if not blocks:
        raise AssertionError(f"missing function block: {name}")
    if len(blocks) != 1:
        raise AssertionError(f"expected exactly one final function body: {name}")
    return blocks[0]


def assert_web_public_authority_contract(block: str) -> None:
    code = sql_code_without_comments_or_dollar_strings(function_body(block))
    if PUBLIC_SESSION_GUARD.search(code) is None:
        raise AssertionError("missing fail-closed public session guard")
    if PUBLIC_AUTHORITY_ASSIGNMENT.search(code) is None:
        raise AssertionError("missing fail-closed public authority resolver")
    if PUBLIC_AUTHORITY_GUARD.search(code) is None:
        raise AssertionError("missing fail-closed public authority guard")
    if PUBLIC_AI_PRINCIPAL_SCOPE.search(code) is None:
        raise AssertionError("missing fail-closed public AI principal scope")
    if re.search(r"\b(?:AND\s+FALSE|OR\s+TRUE)\b", code, flags=re.IGNORECASE):
        raise AssertionError("boolean constant weakens public authority")
    if re.search(
        r"\b(?:current_setting|set_config)\s*\(",
        code,
        flags=re.IGNORECASE,
    ):
        raise AssertionError("client principal GUC is not an authority source")


def assert_snapshot_public_authority_contract(block: str) -> None:
    code = sql_code_without_comments_or_dollar_strings(function_body(block))
    required_patterns = (
        (
            r"\bSESSION_USER\s+NOT\s+IN\s*"
            r"\(\s*'n6_btrack_web'\s*,\s*'n6_ai_agent'\s*\)",
            "missing exact public snapshot session roles",
        ),
        (
            r"\bIF\s+SESSION_USER\s*=\s*'n6_btrack_web'\s+THEN\b",
            "missing Web authority branch",
        ),
        (
            r"\bp_session_token_hash\s*!~\s*'\^\[0-9a-f\]\{64\}\$'",
            "missing Web session hash validation",
        ),
        (
            r"\bauthority\s*:=\s*"
            r"public\.n6_btrack_resolve_authority\s*"
            r"\(\s*p_session_token_hash\s*\)\s*;",
            "missing Web authority resolver",
        ),
        (
            r"\bIF\s+authority\s+IS\s+NULL\s+OR\s+"
            r"authority\s*->>\s*'principal_status'\s*<>\s*'active'\s+OR\s+"
            r"authority\s*->>\s*'principal_type'\s+NOT\s+IN\s*"
            r"\(\s*'admin'\s*,\s*'human_user'\s*\)",
            "missing active human Web authority guard",
        ),
        (
            r"\bELSIF\s+p_session_token_hash\s*<>\s*"
            r"pg_catalog\.repeat\s*\(\s*'0'\s*,\s*64\s*\)\s+THEN\b",
            "missing exact AI publisher sentinel guard",
        ),
        (
            r"\bprincipal\.principal_type\s*=\s*'ai_user'\s+AND\s+"
            r"principal\.principal_status\s*=\s*'active'",
            "missing active public AI principal scope",
        ),
    )
    for pattern, message in required_patterns:
        if re.search(pattern, code, flags=re.IGNORECASE | re.DOTALL) is None:
            raise AssertionError(message)
    if re.search(r"\b(?:AND\s+FALSE|OR\s+TRUE)\b", code, flags=re.IGNORECASE):
        raise AssertionError("boolean constant weakens public authority")
    if re.search(
        r"\b(?:current_setting|set_config)\s*\(",
        code,
        flags=re.IGNORECASE,
    ):
        raise AssertionError("client principal GUC is not an authority source")


class N6AiAgentSchemaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = SCHEMA_PATH.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK_PATH.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.schema_norm = normalized_sql(cls.schema)
        cls.rollback_norm = normalized_sql(cls.rollback)
        cls.schema_compact = re.sub(r"\s+", "", cls.schema.lower())
        cls.rollback_compact = re.sub(r"\s+", "", cls.rollback.lower())

    def test_transaction_and_exact_six_additive_tables(self) -> None:
        self.assertEqual(len(re.findall(r"(?im)^\s*BEGIN\s*;", self.schema)), 1)
        self.assertTrue(self.schema_norm.endswith("commit;"))
        for table in TABLES:
            self.assertRegex(
                self.schema,
                rf"CREATE TABLE(?: IF NOT EXISTS)? public\.{table}\b",
            )
        created = re.findall(
            r"CREATE TABLE(?: IF NOT EXISTS)?\s+public\.(n6_ai_[a-z0-9_]+)",
            self.schema,
            flags=re.IGNORECASE,
        )
        self.assertEqual(sorted(created), sorted(TABLES))
        self.assertNotRegex(
            self.schema,
            r"(?i)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:VIEW|MATERIALIZED\s+VIEW)\b",
        )

    def test_role_preflight_requires_hardened_three_roles_and_zero_direct_privilege(
        self,
    ) -> None:
        for role in ("n6_ai_agent", "n6_btrack_web", "n6_virtual_executor"):
            self.assertIn(f"('{role}'::text)", self.schema)
        for attribute in (
            "rolcanlogin",
            "rolinherit",
            "rolsuper",
            "rolcreatedb",
            "rolcreaterole",
            "rolreplication",
            "rolbypassrls",
        ):
            self.assertIn(attribute, self.schema)
        self.assertIn("has_table_privilege", self.schema)
        self.assertIn("has_sequence_privilege", self.schema)
        self.assertNotRegex(
            self.schema,
            r"(?is)\bGRANT\s+(?:SELECT|INSERT|UPDATE|DELETE|TRUNCATE|REFERENCES|"
            r"TRIGGER|USAGE\s+ON\s+SEQUENCE)\b.*?\bTO\s+"
            r"(?:n6_ai_agent|n6_btrack_web|n6_virtual_executor)\b",
        )

    def test_exact_nine_hardened_function_signatures(self) -> None:
        expected_names = ["n6_ai_shared_signal_projection_capture"]
        for signatures in FUNCTION_GRANTS.values():
            expected_names.extend(signature.split("(", 1)[0] for signature in signatures)
        created = set(re.findall(
            r"CREATE OR REPLACE FUNCTION\s+public\.([a-z0-9_]+)\s*\(",
            self.schema,
            flags=re.IGNORECASE,
        ))
        bootstrap = "n6_ai_agent_shadow_decision_record_bootstrap"
        if bootstrap in created:
            self.assertRegex(
                self.schema,
                rf"(?i)DROP\s+FUNCTION\s+public\.{bootstrap}\(jsonb\)\s*;",
            )
            created.remove(bootstrap)
        expected_name_set = set(expected_names)
        self.assertEqual(created, expected_name_set)
        for name in expected_name_set:
            block = function_block(self.schema, name)
            self.assertRegex(block, r"(?i)\bSECURITY DEFINER\b")
            self.assertRegex(
                block,
                r"(?i)\bSET\s+search_path\s*=\s*pg_catalog\b",
            )
            self.assertEqual(len(top_level_function_blocks(self.schema, name)), 1)
            with self.subTest(deleted_function=name):
                deleted = self.schema.replace(block, "", 1)
                with self.assertRaisesRegex(AssertionError, "missing function block"):
                    function_block(deleted, name)

        sample = (
            "CREATE OR REPLACE FUNCTION public.n6_test_function()\n"
            "RETURNS void\nLANGUAGE plpgsql\nAS $function$\n"
            "BEGIN\n  RETURN;\nEND\n$function$;"
        )
        self.assertEqual(function_block(sample, "n6_test_function"), sample)
        with self.assertRaisesRegex(AssertionError, "exactly one final function body"):
            function_block(f"{sample}\n{sample}", "n6_test_function")
        indented_sample = "\n".join(
            f"  {line}" for line in sample.splitlines()
        )
        self.assertEqual(
            function_block(indented_sample, "n6_test_function"),
            indented_sample,
        )
        tagged_sample = sample.replace("$function$", "$body$")
        self.assertEqual(
            function_block(tagged_sample, "n6_test_function"),
            tagged_sample,
        )
        with self.assertRaisesRegex(AssertionError, "exactly one final function body"):
            function_block(f"{sample}\n{indented_sample}", "n6_test_function")
        with self.assertRaisesRegex(AssertionError, "missing function block"):
            function_block("SELECT 1;", "n6_test_function")
        comment_fake = "\n".join(f"-- {line}" for line in sample.splitlines())
        with self.assertRaisesRegex(AssertionError, "missing function block"):
            function_block(comment_fake, "n6_test_function")
        string_fake = f"SELECT 'not a declaration\n{sample}\n';"
        with self.assertRaisesRegex(AssertionError, "missing function block"):
            function_block(string_fake, "n6_test_function")
        block_comment_fake = f"/* outer\n/* nested */\n{sample}\n*/"
        with self.assertRaisesRegex(AssertionError, "missing function block"):
            function_block(block_comment_fake, "n6_test_function")
        dollar_string_fake = f"DO $outer$\n{sample}\n$outer$;"
        with self.assertRaisesRegex(AssertionError, "missing function block"):
            function_block(dollar_string_fake, "n6_test_function")

    def test_every_top_level_plpgsql_block_has_outer_end_terminator(
        self,
    ) -> None:
        checked_function_blocks = 0
        function_names = {
            match.group("name").lower()
            for match in FUNCTION_HEADER.finditer(self.schema)
        }
        for name in function_names:
            for block in top_level_function_blocks(self.schema, name):
                if re.search(r"(?i)\bLANGUAGE\s+plpgsql\b", block) is None:
                    continue
                with self.subTest(function=name):
                    self.assertRegex(
                        function_body(block),
                        r"(?is)\bEND\s*;\s*$",
                    )
                checked_function_blocks += 1
        self.assertEqual(checked_function_blocks, 10)

        do_blocks = list(TOP_LEVEL_DO_BLOCK.finditer(self.schema))
        self.assertEqual(len(do_blocks), 3)
        for block in do_blocks:
            with self.subTest(do_block=block.group("delimiter")):
                self.assertRegex(block.group("body"), r"(?is)\bEND\s*;\s*$")

    def test_postcheck_loop_variable_is_explicitly_declared(self) -> None:
        postcheck = next(
            block
            for block in TOP_LEVEL_DO_BLOCK.finditer(self.schema)
            if block.group("delimiter") == "$postcheck$"
        )
        declaration = postcheck.group("body").split("BEGIN", 1)[0]
        self.assertRegex(
            declaration,
            r"(?im)^[ \t]*expected_role[ \t]+text[ \t]*;[ \t]*$",
        )

    def test_daily_buy_limit_cases_are_parenthesized_for_pg16(
        self,
    ) -> None:
        matches = re.findall(
            r"(?s)>=\s*\(CASE\s+WHEN\s+"
            r"autonomous_trade_(?:day_no|days)\s*<\s*3\s+"
            r"THEN\s+1\s+ELSE\s+10\s+END\)",
            self.schema,
        )
        self.assertEqual(len(matches), 3)
        self.assertNotRegex(
            self.schema,
            r"(?s)>=\s*CASE\s+WHEN\s+autonomous_trade_",
        )

    def test_public_revoke_and_exact_role_execute_matrix(self) -> None:
        for role, signatures in FUNCTION_GRANTS.items():
            for signature in signatures:
                self.assertIn(
                    f"revokeallonfunctionpublic.{signature.lower()}"
                    "frompublic;",
                    self.schema_compact,
                )
                self.assertIn(
                    f"grantexecuteonfunctionpublic.{signature.lower()}"
                    f"to{role};",
                    self.schema_compact,
                )
        grant_rows = re.findall(
            r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.([a-z0-9_]+\s*\([^;]+\))"
            r"\s+TO\s+(n6_ai_agent|n6_virtual_executor|n6_btrack_web)\s*;",
            self.schema,
            flags=re.IGNORECASE,
        )
        expected_rows = {
            (signature.replace(" ", "").lower(), role)
            for role, signatures in FUNCTION_GRANTS.items()
            for signature in signatures
        }
        actual_rows = {
            (signature.replace(" ", "").lower(), role.lower())
            for signature, role in grant_rows
        }
        self.assertEqual(actual_rows, expected_rows)

    def test_context_is_ai_owned_and_does_not_read_human_private_scope(self) -> None:
        context = function_block(self.schema, "n6_ai_agent_context_load").lower()
        for required in (
            "public.n6_ai_shared_signal_projection",
            "public.user_projection_run",
            "public.n6_virtual_account",
            "public.n6_virtual_cash_snapshot",
            "public.n6_virtual_position",
            "principal_type = 'ai_user'",
            "shared.shared_status = 'active'",
            "shared.asset_kind = 'index'",
            "shared.asset_kind = 'board'",
            "'market_context', market_context_payload.rows",
            "'context_only', true",
            "public.v_n6_virtual_quote_latest",
            "position_quote_not_ready",
        ):
            self.assertIn(required, context)
        for forbidden in (
            "user_session",
            "user_monitor_stock",
            "user_monitor_index",
            "user_monitor_board",
            "user_realtime_scope",
            "n2_",
            "n3_",
            "n4_",
            "n5_",
            "common_event_outbox",
            "public.user_signal_projection",
            "public.user_signal_card",
        ):
            self.assertNotIn(forbidden, context)
        self.assertRegex(context, r"p_max_signals\s*<\s*0")
        self.assertNotRegex(context, r"p_max_signals\s*<=\s*0")
        self.assertNotIn("projection_status in ('visible', 'blocked')", context)

    def test_shared_projection_has_an_explicit_sanitized_n6_producer(self) -> None:
        plan_source = (
            ROOT / "src" / "ashare_v3" / "user" / "projection_plan.py"
        ).read_text(encoding="utf-8")
        execute_source = (
            ROOT / "src" / "ashare_v3" / "user" / "projection_execute.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"permission_scope": "self"', plan_source)
        self.assertIn('"permission_scope": "self"', execute_source)
        self.assertNotIn('"permission_scope": "system"', plan_source)
        self.assertNotIn('"permission_scope": "system"', execute_source)
        capture = function_block(
            self.schema, "n6_ai_shared_signal_projection_capture"
        ).lower()
        self.assertIn("b_track_signal_projection", capture)
        self.assertIn("new.user_projection_run_id", capture)
        self.assertNotIn("new.user_id", capture)
        self.assertNotIn("new.user_filter_profile_id", capture)
        self.assertIn(
            "create trigger trg_055_n6_ai_shared_signal_projection_capture",
            self.schema_norm,
        )

    def test_quote_valuation_and_outstanding_budget_are_fail_closed(self) -> None:
        blocks = (
            function_block(self.schema, "n6_ai_agent_context_load")
            + function_block(self.schema, "n6_ai_agent_daily_summary_record")
            + function_block(
                self.schema, "n6_ai_agent_proposal_create_confirm"
            )
            + function_block(self.schema, "n6_ai_executor_risk_recheck")
            + function_block(self.schema, "n6_btrack_ai_public_snapshot")
        ).lower()
        self.assertNotIn("position.market_value", blocks)
        self.assertGreaterEqual(
            blocks.count("public.v_n6_virtual_quote_latest"), 5
        )
        self.assertIn("portfolio_quote_not_ready", blocks)
        self.assertIn("ai_portfolio_quote_not_ready", blocks)
        self.assertIn("daily_summary_quote_not_ready", blocks)
        proposal = function_block(
            self.schema, "n6_ai_agent_proposal_create_confirm"
        ).lower()
        executor = function_block(
            self.schema, "n6_ai_executor_risk_recheck"
        ).lower()
        for block in (proposal, executor):
            self.assertIn("outstanding_buy_reservation", block)
            self.assertIn("outstanding_identity_reservation", block)
            self.assertIn("current_drawdown", block)
            self.assertIn("300000", block)

    def test_model_and_proposal_cannot_supply_execution_authority(self) -> None:
        decision = function_block(
            self.schema, "n6_ai_agent_shadow_decision_record"
        ).lower()
        proposal = function_block(
            self.schema, "n6_ai_agent_proposal_create_confirm"
        ).lower()
        for forbidden_field in (
            "price",
            "quantity",
            "account",
            "trade_date",
            "principal",
            "user_id",
        ):
            self.assertIn(forbidden_field, decision)
            self.assertIn(forbidden_field, proposal)
        self.assertIn("signal_evidence_reference_required", decision)
        self.assertIn("position_evidence_reference_required", decision)
        self.assertIn("'shadow'", decision)
        self.assertNotRegex(
            decision,
            r"(?i)\bINSERT\s+INTO\s+public\.n6_virtual_trade_proposal\b",
        )
        self.assertIn("run_mode <> 'autonomous_canary'", proposal)
        self.assertIn("proposal_status", proposal)
        self.assertIn("'confirmed'", proposal)
        self.assertNotRegex(
            decision + proposal,
            r"(?i)\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+public\."
            r"n6_virtual_(?:order|trade|position|position_lot|cash_ledger|"
            r"cash_snapshot|quote_snapshot)\b",
        )

    def test_server_owns_hash_and_risk_provenance(self) -> None:
        decision = function_block(
            self.schema, "n6_ai_agent_shadow_decision_record"
        ).lower()
        proposal = function_block(
            self.schema, "n6_ai_agent_proposal_create_confirm"
        ).lower()
        executor = function_block(
            self.schema, "n6_ai_executor_risk_recheck"
        ).lower()
        self.assertIn(
            "p_payload->>'input_payload_hash' <> "
            "context_row.decision_input_hash",
            normalized_sql(decision),
        )
        self.assertIn("target_output_hash := pg_catalog.encode", decision)
        self.assertNotIn("'output_payload_hash'", decision.split("begin", 1)[1].split(
            "target_output_hash :=", 1
        )[0])
        self.assertIn("server_risk_allowed boolean not null", self.schema_norm)
        self.assertIn("server_risk_reason text not null", self.schema_norm)
        self.assertIn("'computed_by'", decision)
        self.assertIn("target_risk_assessment", decision)
        self.assertIn(
            "source.server_risk_allowed is distinct from true", proposal
        )
        self.assertIn(
            "decision_row.server_risk_allowed is distinct from true",
            executor,
        )

    def test_drawdown_pause_is_persisted_and_daily_summary_is_frozen(self) -> None:
        context = function_block(self.schema, "n6_ai_agent_context_load").lower()
        proposal = function_block(
            self.schema, "n6_ai_agent_proposal_create_confirm"
        ).lower()
        executor = function_block(
            self.schema, "n6_ai_executor_risk_recheck"
        ).lower()
        for block in (context, proposal, executor):
            self.assertIn("update public.n6_ai_user", block)
            self.assertIn("status = 'disabled'", block)
            self.assertIn("agent_drawdown_paused", block)
        summary = function_block(
            self.schema, "n6_ai_agent_daily_summary_record"
        ).lower()
        for required in (
            "daily_net_pnl",
            "previous_total_asset",
            "strategy_version",
            "strategy_hash",
            "knowledge_bundle_version",
            "knowledge_bundle_hash",
            "p_payload->'highlights'",
            "p_payload->'lessons'",
            "p_payload->'next_day_watch'",
        ):
            self.assertIn(required, summary)
        public = function_block(
            self.schema, "n6_btrack_ai_public_snapshot"
        ).lower()
        self.assertIn("'daily_net_pnl', row.daily_net_pnl", public)
        self.assertIn("'strategy_version', row.strategy_version", public)
        self.assertIn("'success_reasons'", public)

    def test_public_quote_mark_has_explicit_freshness_contract(self) -> None:
        public = function_block(
            self.schema, "n6_btrack_ai_public_snapshot"
        ).lower()
        for required in (
            "valuation_trade_date",
            "valuation_mode",
            "'fresh_120s'",
            "'midday_close'",
            "'daily_close'",
            "interval '120 seconds'",
            "time '11:28:00'",
            "time '14:55:00'",
            "time '15:05:00'",
        ):
            self.assertIn(required, public)

    def test_public_audit_survives_pause_and_uses_shared_display_names(
        self,
    ) -> None:
        public = function_block(
            self.schema, "n6_btrack_ai_public_snapshot"
        ).lower()
        detail = function_block(
            self.schema, "n6_btrack_ai_public_decision_detail"
        ).lower()
        for block in (public, detail):
            self.assertIn(
                "ai.status in ('sandbox_only', 'active', 'disabled')",
                block,
            )
            self.assertIn(
                "public.n6_ai_shared_signal_projection shared",
                block,
            )
        self.assertGreaterEqual(
            public.count(
                "public.n6_ai_shared_signal_projection shared"
            ),
            3,
        )
        self.assertIn("'display_name', row.display_name", public)
        self.assertIn(
            "'display_name', identity_name.display_name",
            detail,
        )
        self.assertIn("actor_count <> 1", detail)
        self.assertIn(
            "decision.ai_user_id = actor.ai_user_id",
            detail,
        )
        self.assertNotIn("latest_run.failure_reason", public)

    def test_ai_actor_and_lot_constraints_are_additive_and_fail_closed(self) -> None:
        for token in (
            "actor_ai_user_id",
            "source_ai_decision_id",
            "n6_virtual_trade_proposal_055_actor_ck",
            "n6_virtual_trade_proposal_055_source_type_ck",
            "n6_virtual_position_lot_055_principal_type_ck",
            "'ai_risk'",
            "'ai_user'",
        ):
            self.assertIn(token, self.schema)
        self.assertRegex(
            self.schema,
            r"(?is)ALTER\s+COLUMN\s+user_id\s+DROP\s+NOT\s+NULL",
        )
        self.assertIn("source_ai_decision_id", self.schema)

    def test_executor_recheck_exists_and_is_executor_only(self) -> None:
        block = function_block(self.schema, "n6_ai_executor_risk_recheck").lower()
        self.assertIn("session_user", block)
        self.assertIn("n6_virtual_executor", block)
        self.assertIn("source_ai_decision_id", block)
        self.assertIn("ai_user", block)
        self.assertNotRegex(
            block,
            r"(?i)\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+public\."
            r"n6_virtual_(?:order|trade|position|position_lot|cash_ledger|"
            r"cash_snapshot)\b",
        )

    def test_public_functions_require_btrack_authority_and_never_return_secrets(
        self,
    ) -> None:
        snapshot_block = function_block(
            self.schema, "n6_btrack_ai_public_snapshot"
        )
        detail_block = function_block(
            self.schema, "n6_btrack_ai_public_decision_detail"
        )
        assert_snapshot_public_authority_contract(snapshot_block)
        assert_web_public_authority_contract(detail_block)
        for block, contract in (
            (snapshot_block, assert_snapshot_public_authority_contract),
            (detail_block, assert_web_public_authority_contract),
        ):
            if contract is assert_snapshot_public_authority_contract:
                missing_session_guard = re.sub(
                    r"SESSION_USER\s+NOT\s+IN\s*"
                    r"\(\s*'n6_btrack_web'\s*,\s*'n6_ai_agent'\s*\)",
                    "false",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                )
            else:
                missing_session_guard = re.sub(
                    r"SESSION_USER\s*<>\s*'n6_btrack_web'",
                    "false",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                )
            mutations = {
                "missing_session_guard": missing_session_guard,
                "missing_resolver": re.sub(
                    r"authority\s*:=\s*"
                    r"public\.n6_btrack_resolve_authority\s*"
                    r"\(\s*p_session_token_hash\s*\)\s*;",
                    "authority := '{}'::jsonb;",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                ),
                "commented_resolver": re.sub(
                    r"authority\s*:=\s*"
                    r"public\.n6_btrack_resolve_authority\s*"
                    r"\(\s*p_session_token_hash\s*\)\s*;",
                    "authority := '{}'::jsonb; "
                    "-- public.n6_btrack_resolve_authority"
                    "(p_session_token_hash);",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                ),
                "null_and_false": re.sub(
                    r"IF\s+authority\s+IS\s+NULL",
                    "IF authority IS NULL AND false",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                ),
                "status_and_false": re.sub(
                    r"authority->>'principal_status'\s*<>\s*'active'",
                    "authority->>'principal_status' <> 'active' AND false",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                ),
                "type_and_false": re.sub(
                    r"authority->>'principal_type'\s+NOT\s+IN\s*"
                    r"\(\s*'admin'\s*,\s*'human_user'\s*\)",
                    "authority->>'principal_type' "
                    "NOT IN ('admin', 'human_user') AND false",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                ),
                "guard_or_true": re.sub(
                    r"THEN\s+RETURN\s+NULL\s*;\s*END\s+IF\s*;",
                    "OR true THEN RETURN NULL; END IF;",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                ),
                "missing_ai_principal_scope": re.sub(
                    r"principal\.principal_type\s*=\s*'ai_user'",
                    "principal.principal_type = 'human_user'",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                ),
            }
            if contract is assert_snapshot_public_authority_contract:
                mutations["missing_ai_publisher_sentinel"] = re.sub(
                    r"p_session_token_hash\s*<>\s*"
                    r"pg_catalog\.repeat\s*\(\s*'0'\s*,\s*64\s*\)",
                    "false",
                    block,
                    count=1,
                    flags=re.IGNORECASE,
                )
            for mutation_name, mutated in mutations.items():
                with self.subTest(public_authority_mutation=mutation_name):
                    with self.assertRaisesRegex(
                        AssertionError,
                        "authority|session guard|principal scope|"
                        "boolean constant|session roles|sentinel guard",
                    ):
                        contract(mutated)
            guc_mutations = (
                "PERFORM current_setting('app.principal_id');",
                "PERFORM current_setting ('app.principal_id');",
                "PERFORM current_setting/*client*/('app.principal_id');",
                "PERFORM set_config('app.principal_id', '1', false);",
            )
            for guc_statement in guc_mutations:
                with self.subTest(client_authority_pollution=guc_statement):
                    polluted = block.replace(
                        "BEGIN",
                        f"BEGIN\n  {guc_statement}",
                        1,
                    )
                    with self.assertRaisesRegex(AssertionError, "client principal GUC"):
                        contract(polluted)
        combined = snapshot_block.lower() + detail_block.lower()
        for forbidden in (
            "session_token_hash",
            "pgpass",
            "pgpassword",
            "model_credential",
            "raw_prompt",
            "chain_of_thought",
            "strategy_candidate_notes",
        ):
            if forbidden == "session_token_hash":
                # Parameter naming is allowed; selecting or returning session rows is not.
                self.assertNotIn("public.user_session", combined)
            else:
                self.assertNotIn(forbidden, combined)
        self.assertNotRegex(
            combined,
            r"(?i)\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b",
        )

    def test_rollback_is_history_protecting_and_restores_041_shape(self) -> None:
        self.assertEqual(
            len(re.findall(r"(?im)^\s*BEGIN\s*;", self.rollback)),
            1,
        )
        self.assertTrue(self.rollback_norm.endswith("commit;"))
        for table in TABLES:
            self.assertIn(f"lock table public.{table}", self.rollback_norm)
            self.assertIn(f"drop table public.{table}", self.rollback_norm)
        for relation in (
            "n6_ai_user",
            "n6_principal",
            "n6_strategy",
            "n6_principal_account",
            "n6_virtual_account",
            "n6_virtual_trade_proposal",
            "n6_virtual_position_lot",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_position_event",
            "n6_virtual_pnl_snapshot",
            "n6_virtual_cash_ledger",
            "n6_virtual_cash_snapshot",
            "n6_virtual_quote_run",
            "n6_virtual_quote_snapshot",
        ):
            self.assertIn(relation, self.rollback)
        self.assertNotRegex(
            self.rollback,
            r"(?i)\b(?:DELETE\s+FROM|TRUNCATE\s+(?:TABLE\s+)?)\b",
        )
        self.assertIn("ALTER COLUMN user_id SET NOT NULL", self.rollback)
        self.assertIn(
            "CHECK (principal_type IN ('admin', 'human_user'))",
            self.rollback,
        )
        self.assertIn(
            "CHECK (source_type IN ('signal', 'manual_position', 'stop_loss'))",
            self.rollback,
        )
        for role, signatures in FUNCTION_GRANTS.items():
            for signature in signatures:
                self.assertIn(
                    f"dropfunctionpublic.{signature.lower()};",
                    self.rollback_compact,
                )
        self.assertIn(
            "droptriggertrg_055_n6_ai_shared_signal_projection_capture"
            "onpublic.user_signal_projection;",
            self.rollback_compact,
        )
        self.assertIn(
            "dropfunctionpublic.n6_ai_shared_signal_projection_capture();",
            self.rollback_compact,
        )

    def test_rollback_drops_only_exactly_rebuildable_shared_projection(
        self,
    ) -> None:
        required = (
            "lock table public.user_projection_run",
            "with rebuildable_source as",
            "projection_run.source_layer = 'n5_action'",
            "projection_run.status = 'passed'",
            "projection_run.quality_summary_json "
            "->>'b_track_signal_projection' = 'passed'",
            "projection.projection_status = 'visible'",
            "shared.source_signal_projection_id",
            "shared.reason_fields_json is distinct from "
            "source.reason_fields_json",
            "shared.source_payload_hash is distinct from "
            "source.expected_payload_hash",
            "shared.shared_status <> 'active'",
            "055 rollback blocked: non-rebuildable shared projection rows=",
        )

        def assert_guard(sql: str) -> None:
            normalized = normalized_sql(sql)
            for fragment in required:
                self.assertIn(normalized_sql(fragment), normalized)

        assert_guard(self.rollback)
        for fragment in required:
            with self.subTest(missing_guard=fragment):
                mutated = self.rollback.replace(fragment, "", 1)
                if mutated == self.rollback:
                    mutated = normalized_sql(self.rollback).replace(
                        normalized_sql(fragment), "", 1
                    )
                with self.assertRaises(AssertionError):
                    assert_guard(mutated)

        self.assertNotRegex(
            self.rollback,
            r"(?i)\b(?:DELETE\s+FROM|TRUNCATE\s+(?:TABLE\s+)?)\b",
        )

    def test_canonical_json_matches_static_contract(self) -> None:
        self.assertEqual(self.contract["contract_version"], "n6_ai_agent_v1")
        self.assertEqual(self.contract["layer_role"], "N6_user")
        self.assertFalse(self.contract["real_trade_enabled"])
        self.assertFalse(self.contract["autonomous_trading_default_enabled"])
        self.assertEqual(sorted(self.contract["tables"]), sorted(TABLES))
        self.assertEqual(
            self.contract["role_contract"]["direct_public_relation_privileges"],
            [],
        )
        self.assertEqual(
            self.contract["role_contract"]["direct_public_sequence_privileges"],
            [],
        )
        self.assertEqual(self.contract["function_grants"]["public_execute"], [])
        self.assertTrue(
            self.contract["risk_policy"][
                "executor_recheck_required_before_account_dml"
            ]
        )
        self.assertTrue(
            self.contract["decision_integrity"][
                "output_hash_computed_by_security_definer"
            ]
        )
        self.assertTrue(
            self.contract["decision_integrity"][
                "server_risk_columns_are_authoritative"
            ]
        )
        self.assertTrue(
            self.contract["risk_policy"][
                "drawdown_pause_is_persisted_as_ai_user_disabled"
            ]
        )
        self.assertTrue(
            self.contract["daily_summary_contract"][
                "daily_net_pnl_is_previous_summary_delta"
            ]
        )
        self.assertEqual(
            self.contract["strategy_evolution"]["minimum_shadow_trading_days"],
            10,
        )
        self.assertTrue(
            self.contract["strategy_evolution"]["admin_promotion_required"]
        )
        self.assertFalse(self.contract["public_web_contract"]["write_controls"])
        self.assertTrue(
            self.contract["rollback"]["fail_closed_if_any_ai_fact_or_history_exists"]
        )
        self.assertFalse(
            self.contract["rollback"]["deletes_business_rows"]
        )
        self.assertTrue(
            self.contract["rollback"][
                "shared_projection_is_rebuildable_derived_data"
            ]
        )
        self.assertTrue(
            self.contract["rollback"][
                "shared_projection_drop_requires_exact_source_rebuildability"
            ]
        )
        self.assertTrue(
            self.contract["rollback"][
                "shared_projection_orphan_pollution_or_drift_blocks_rollback"
            ]
        )


if __name__ == "__main__":
    unittest.main()
