from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ashare_v3.user.virtual_executor import (
    CLAIM_NEXT_SQL,
    CLAIM_SQL,
    FUNCTION_SQL,
    VirtualExecutorRequest,
    execute_proposal,
)
from scripts.run_n6_virtual_executor_once import (
    build_parser,
    main,
    run_from_args,
    validate_executor_environment,
)


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "sql/046_n6_btrack_virtual_executor_apply.sql").read_text()
ROLLBACK = (ROOT / "sql/046_n6_btrack_virtual_executor_apply_rollback.sql").read_text()
CONTRACT = json.loads(
    (ROOT / "docs/N6_B_TRACK_PRODUCT_V3_VIRTUAL_EXECUTOR_046_CONTRACT.json").read_text()
)
SQL_048 = (
    ROOT / "sql/048_n6_btrack_proposal_scope_and_executor_claim_next.sql"
).read_text()
ROLLBACK_048 = (
    ROOT / "sql/048_n6_btrack_proposal_scope_and_executor_claim_next_rollback.sql"
).read_text()
CONTRACT_048 = json.loads(
    (
        ROOT
        / "docs/N6_B_TRACK_PRODUCT_V3_PROPOSAL_SCOPE_AND_EXECUTOR_CLAIM_NEXT_048_CONTRACT.json"
    ).read_text()
)
SQL_057 = (ROOT / "sql/057_n6_ai_agent_execution_compat.sql").read_text()
SQL_063 = (ROOT / "sql/063_n6_btrack_manual_actionable_buy.sql").read_text()
ROLLBACK_063 = (
    ROOT / "sql/063_n6_btrack_manual_actionable_buy_rollback.sql"
).read_text()
CONTRACT_063 = json.loads(
    (
        ROOT
        / "docs/N6_B_TRACK_PRODUCT_V3_MANUAL_ACTIONABLE_BUY_063_CONTRACT.json"
    ).read_text()
)
SQL_064 = (
    ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql"
).read_text()
ROLLBACK_064 = (
    ROOT / "sql/064_n6_btrack_trade_date_all_day_buy_rollback.sql"
).read_text()
CONTRACT_064 = json.loads(
    (
        ROOT
        / "docs/N6_B_TRACK_PRODUCT_V3_TRADE_DATE_ALL_DAY_BUY_064_CONTRACT.json"
    ).read_text()
)


def _parenthesized(text: str, open_index: int) -> tuple[str, int]:
    depth = 0
    quote = None
    for index in range(open_index, len(text)):
        char = text[index]
        if quote:
            if char == quote and text[index - 1] != "\\":
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:index], index + 1
    raise AssertionError("unclosed_parenthesis")


def _function_definition(sql: str, name: str) -> str:
    marker = f"CREATE OR REPLACE FUNCTION public.{name}"
    start = sql.index(marker)
    end = sql.index("$function$;", start) + len("$function$;")
    return sql[start:end]


def _function_body(sql: str, name: str) -> str:
    definition = _function_definition(sql, name)
    start = definition.index("AS $function$") + len("AS $function$")
    end = definition.index("$function$;", start)
    return definition[start:end]


def _dollar_assignment(sql: str, variable: str, tag: str) -> str:
    marker = f"{variable} := ${tag}$"
    start = sql.index(marker) + len(marker)
    end = sql.index(f"${tag}$;", start)
    return sql[start:end]


def _replace_exact(
    source: str,
    sql: str,
    old_tag: str,
    new_tag: str,
    expected_count: int,
) -> str:
    old = _dollar_assignment(sql, "old_text", old_tag)
    new = _dollar_assignment(sql, "new_text", new_tag)
    actual_count = source.count(old)
    if actual_count != expected_count:
        raise AssertionError(
            f"{old_tag} count {actual_count}, expected {expected_count}"
        )
    return source.replace(old, new)


def _top_level_csv(text: str) -> list[str]:
    items = []
    start = 0
    depth = 0
    quote = None
    for index, char in enumerate(text):
        if quote:
            if char == quote and text[index - 1] != "\\":
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(text[start:index].strip())
            start = index + 1
    items.append(text[start:].strip())
    return items


class FakeCursor:
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params) -> None:
        self.connection.calls.append(("execute", sql, params))
        self.connection.execute_count += 1
        if self.connection.fail_on_execute == self.connection.execute_count:
            raise RuntimeError("atomic_failure")

    def fetchone(self):
        return (self.connection.payloads.pop(0),)


class FakeConnection:
    def __init__(self, payloads=None, fail_on_execute=None) -> None:
        self.payloads = list(payloads or [
            {"ok": True, "status": "processing", "proposal_id": 7},
            {"ok": True, "status": "executed"},
        ])
        self.fail_on_execute = fail_on_execute
        self.calls = []
        self.execute_count = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.calls.append(("commit",))

    def rollback(self):
        self.calls.append(("rollback",))

    def close(self):
        self.closed = True


class VirtualExecutor046Test(unittest.TestCase):
    def test_python_calls_only_function_and_commits(self) -> None:
        conn = FakeConnection()
        result = execute_proposal(conn, VirtualExecutorRequest(7, "run-7"))
        self.assertEqual(result["status"], "executed")
        self.assertEqual(conn.calls[0], ("execute", CLAIM_SQL, (7, "run-7")))
        self.assertEqual(conn.calls[1], ("execute", FUNCTION_SQL, (7, "run-7")))
        self.assertEqual(conn.calls[-1], ("commit",))
        for function_call in (CLAIM_SQL, FUNCTION_SQL):
            self.assertNotIn("INSERT", function_call.upper())
            self.assertNotIn("UPDATE", function_call.upper())

    def test_default_claim_next_calls_apply_in_same_outer_transaction(self) -> None:
        conn = FakeConnection()
        result = execute_proposal(conn, VirtualExecutorRequest(None, "run-next"))
        self.assertEqual(result["status"], "executed")
        self.assertEqual(
            conn.calls[0], ("execute", CLAIM_NEXT_SQL, ("run-next",))
        )
        self.assertEqual(
            conn.calls[1], ("execute", FUNCTION_SQL, (7, "run-next"))
        )
        self.assertEqual(conn.calls[-1], ("commit",))

    def test_python_rolls_back_claim_when_apply_crashes(self) -> None:
        conn = FakeConnection(fail_on_execute=2)
        with self.assertRaisesRegex(RuntimeError, "atomic_failure"):
            execute_proposal(conn, VirtualExecutorRequest(7, "run-7"))
        self.assertEqual(conn.calls[-1], ("rollback",))
        self.assertFalse(any(call[0] == "commit" for call in conn.calls))

    def test_python_rolls_back_claim_when_apply_rejects(self) -> None:
        conn = FakeConnection(payloads=[
            {"ok": True, "status": "processing", "proposal_id": 7},
            {"ok": False, "status": "quote_not_ready"},
        ])
        result = execute_proposal(conn, VirtualExecutorRequest(7, "run-7"))
        self.assertEqual(result["status"], "quote_not_ready")
        self.assertEqual(conn.calls[-1], ("rollback",))

    def test_no_claimable_proposal_rolls_back_without_apply(self) -> None:
        conn = FakeConnection(
            payloads=[{"ok": False, "status": "no_claimable_proposal"}]
        )
        result = execute_proposal(conn, VirtualExecutorRequest(None, "run-next"))
        self.assertEqual(result["status"], "no_claimable_proposal")
        self.assertEqual(conn.execute_count, 1)
        self.assertEqual(conn.calls[-1], ("rollback",))
        self.assertFalse(any(call[0] == "commit" for call in conn.calls))

    def test_not_claimed_fails_closed_without_apply(self) -> None:
        conn = FakeConnection(payloads=[{"ok": False, "status": "not_claimed"}])
        result = execute_proposal(conn, VirtualExecutorRequest(7, "run-7"))
        self.assertEqual(result["status"], "not_claimed")
        self.assertEqual(conn.execute_count, 1)
        self.assertEqual(conn.calls[-1], ("rollback",))

    def test_runner_without_execute_is_zero_connection_zero_dml(self) -> None:
        calls = []
        args = argparse.Namespace(
            dsn=None, proposal_id=7, executor_run_id="run-7", execute=False
        )
        payload = run_from_args(args, connect=lambda *a, **k: calls.append((a, k)))
        self.assertEqual(payload["status"], "read_only_preflight")
        self.assertFalse(payload["claim_called"])
        self.assertFalse(payload["dml"])
        self.assertEqual(calls, [])

    def test_runner_parser_rejects_dsn_argument(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                [
                    "--proposal-id",
                    "7",
                    "--executor-run-id",
                    "run-7",
                    "--dsn",
                    "postgresql://secret@invalid/db",
                ]
            )

    def test_runner_parser_defaults_to_claim_next(self) -> None:
        args = build_parser().parse_args(
            ["--executor-run-id", "scheduled-run"]
        )
        self.assertIsNone(args.proposal_id)
        self.assertFalse(args.execute)

    def test_runner_treats_no_claimable_proposal_as_successful_noop(self) -> None:
        with patch(
            "scripts.run_n6_virtual_executor_once.build_parser"
        ) as parser_factory, patch(
            "scripts.run_n6_virtual_executor_once.run_from_args",
            return_value={"ok": False, "status": "no_claimable_proposal"},
        ):
            parser_factory.return_value.parse_args.return_value = argparse.Namespace()
            self.assertEqual(main(), 0)

    def test_runner_keeps_real_executor_failure_nonzero(self) -> None:
        with patch(
            "scripts.run_n6_virtual_executor_once.build_parser"
        ) as parser_factory, patch(
            "scripts.run_n6_virtual_executor_once.run_from_args",
            return_value={"ok": False, "status": "quote_not_ready"},
        ):
            parser_factory.return_value.parse_args.return_value = argparse.Namespace()
            self.assertEqual(main(), 2)

    def test_execute_uses_exact_restricted_service_without_reading_files(self) -> None:
        connection = FakeConnection()
        connect_calls = []

        def connect(*args, **kwargs):
            connect_calls.append((args, kwargs))
            return connection

        args = argparse.Namespace(
            proposal_id=7, executor_run_id="run-7", execute=True
        )
        environ = {
            "PGSERVICE": "n6_virtual_executor",
            "PGSERVICEFILE": "/Library/Application Support/Ashare/pg_service.conf",
            "PGPASSFILE": "/Library/Application Support/Ashare/n6_virtual_executor.pgpass",
        }
        with patch.dict("os.environ", environ, clear=True), patch(
            "builtins.open"
        ) as file_open:
            result = run_from_args(args, connect=connect)
        self.assertEqual(result["status"], "executed")
        self.assertEqual(connect_calls[0][0], ("service=n6_virtual_executor",))
        self.assertFalse(connect_calls[0][1]["autocommit"])
        file_open.assert_not_called()
        self.assertTrue(connection.closed)

    def test_execute_rejects_service_password_dsn_and_pg_overrides(self) -> None:
        accepted_paths = {
            "PGSERVICEFILE": "/nonsecret/pg_service.conf",
            "PGPASSFILE": "/nonsecret/n6_virtual_executor.pgpass",
        }
        rejected = (
            {},
            {"PGSERVICE": ""},
            {"PGSERVICE": " n6_virtual_executor"},
            {"PGSERVICE": "N6_VIRTUAL_EXECUTOR"},
            {"PGSERVICE": "n6_btrack_web"},
            {"PGSERVICE": "n6_virtual_executor", **accepted_paths, "PGPASSWORD": "secret"},
            {"PGSERVICE": "n6_virtual_executor", **accepted_paths, "DATABASE_URL": "postgresql://invalid"},
            {"PGSERVICE": "n6_virtual_executor", **accepted_paths, "ASHARE_V3_POSTGRES_DSN": "invalid"},
            {"PGSERVICE": "n6_virtual_executor", **accepted_paths, "POSTGRES_PASSWORD": "secret"},
            {"PGSERVICE": "n6_virtual_executor", **accepted_paths, "PGUSER": "owner"},
            {"PGSERVICE": "n6_virtual_executor", "PGSERVICEFILE": "relative", "PGPASSFILE": "/valid"},
            {"PGSERVICE": "n6_virtual_executor", "PGSERVICEFILE": "/valid", "PGPASSFILE": ""},
        )
        for environ in rejected:
            with self.subTest(keys=sorted(environ)):
                with self.assertRaises(ValueError):
                    validate_executor_environment(environ)

    def test_048_claim_next_fifo_skip_locked_expiry_and_acl(self) -> None:
        self.assertIn(
            "CREATE OR REPLACE FUNCTION public.n6_executor_claim_next_proposal",
            SQL_048,
        )
        self.assertIn(
            "ORDER BY p.confirmed_at ASC NULLS LAST, p.created_at ASC, p.proposal_id ASC",
            SQL_048,
        )
        self.assertIn("FOR UPDATE SKIP LOCKED", SQL_048)
        self.assertIn("LIMIT 1", SQL_048)
        self.assertIn("p.proposal_status = 'confirmed'", SQL_048)
        self.assertIn("p.expires_at > pg_catalog.now()", SQL_048)
        self.assertIn("'no_claimable_proposal'", SQL_048)
        self.assertNotIn("proposal_status = 'expired'", SQL_048)
        self.assertIn(
            "REVOKE ALL ON FUNCTION public.n6_executor_claim_next_proposal(text) FROM PUBLIC;",
            SQL_048,
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.n6_executor_claim_next_proposal(text) TO n6_virtual_executor;",
            SQL_048,
        )

    def test_048_contract_and_rollback_are_function_only(self) -> None:
        claim = CONTRACT_048["claim_next"]
        self.assertEqual(claim["locking"], "FOR UPDATE SKIP LOCKED")
        self.assertEqual(claim["maximum_rows"], 1)
        self.assertFalse(claim["expired_claimed"])
        self.assertEqual(
            CONTRACT_048["runner"]["outer_transaction"],
            ["claim", "046_apply", "commit"],
        )
        self.assertIn(
            "DROP FUNCTION IF EXISTS public.n6_executor_claim_next_proposal(text)",
            ROLLBACK_048,
        )
        for forbidden in (
            "CREATE TABLE",
            "CREATE INDEX",
            "CREATE ROLE",
            "CREATE TRIGGER",
            "DELETE FROM",
            "TRUNCATE",
        ):
            self.assertNotIn(forbidden, SQL_048.upper())

    def test_contract_freezes_restricted_service_wiring(self) -> None:
        credentials = CONTRACT["runtime_credentials"]
        self.assertEqual(credentials["required_pgservice"], "n6_virtual_executor")
        self.assertEqual(
            credentials["connection_string"], "service=n6_virtual_executor"
        )
        self.assertFalse(credentials["dsn_argument_allowed"])
        self.assertFalse(credentials["argv_secret_allowed"])
        self.assertFalse(credentials["pgpassword_allowed"])
        self.assertFalse(credentials["credential_file_contents_read_by_runner"])

    def test_contract_proves_claim_apply_atomicity_and_no_processing_residue(self) -> None:
        runner = CONTRACT["runner"]
        self.assertEqual(
            runner["execute_outer_transaction"],
            ["042_claim", "046_apply_and_processing_to_executed", "commit"],
        )
        self.assertTrue(runner["apply_rejection_rolls_back_claim"])
        self.assertTrue(runner["not_claimed_returns_without_apply"])
        self.assertTrue(runner["exception_or_process_failure_before_commit_rolls_back_claim"])
        self.assertFalse(runner["processing_residue_from_current_invocation"])

    def test_trade_insert_has_exact_30_column_value_mapping(self) -> None:
        marker = "INSERT INTO public.n6_virtual_trade"
        start = SQL.index(marker)
        columns_text, after_columns = _parenthesized(SQL, SQL.index("(", start))
        values_marker = SQL.index("VALUES", after_columns)
        values_text, _ = _parenthesized(SQL, SQL.index("(", values_marker))
        columns = _top_level_csv(columns_text)
        values = _top_level_csv(values_text)
        self.assertEqual(len(columns), 30)
        self.assertEqual(len(values), 30)
        self.assertEqual(
            list(zip(columns[18:22], values[18:22])),
            [
                ("trade_status", "'filled_virtual'"),
                ("trade_time", "pg_catalog.clock_timestamp()"),
                ("source_lineage_json", "lineage"),
                ("run_id", "p_executor_run_id"),
            ],
        )

    def test_order_insert_maps_source_signal_projection_foreign_key(self) -> None:
        marker = "INSERT INTO public.n6_virtual_order"
        start = SQL.index(marker)
        columns_text, after_columns = _parenthesized(SQL, SQL.index("(", start))
        values_marker = SQL.index("VALUES", after_columns)
        values_text, _ = _parenthesized(SQL, SQL.index("(", values_marker))
        columns = _top_level_csv(columns_text)
        values = _top_level_csv(values_text)
        self.assertEqual(len(columns), len(values))
        mapping = dict(zip(columns, values))
        self.assertEqual(
            mapping["source_signal_projection_id"],
            "proposal.source_signal_projection_id",
        )
        self.assertEqual(
            CONTRACT["order_projection_lineage"]["manual_position_behavior"],
            "null",
        )

    def test_buy_policy_uses_300k_and_100_share_lots(self) -> None:
        self.assertIn(
            "LEAST(300000::numeric, cash_before.available_cash) / fill_price / 100",
            SQL,
        )
        self.assertIn("* 100", SQL)
        self.assertIn("cash_before.available_cash < gross_amount", SQL)
        self.assertIn("IF fill_quantity < 100 THEN", SQL)
        self.assertIn("'budget_below_one_lot'", SQL)
        self.assertEqual(CONTRACT["policy"]["buy_budget_cny"], 300000)
        self.assertEqual(CONTRACT["policy"]["buy_round_lot"], 100)
        self.assertEqual(
            CONTRACT["policy"]["cash_below_budget_behavior"],
            "scale_down_to_round_lot",
        )
        self.assertEqual(
            CONTRACT["policy"]["cash_below_one_lot_behavior"], "fail_closed"
        )
        self.assertIn("'target_price_not_ready'", SQL)
        self.assertIn("proposal.locked_target_price, 'frozen'", SQL)
        self.assertIn("ELSE position_before.locked_target_price", SQL)
        self.assertEqual(
            CONTRACT["policy"]["same_episode_add_target"], "preserve_existing"
        )
        self.assertIn(
            "proposal.source_signal_projection_id, 'provisional_first_day'",
            SQL,
        )
        for field in (
            "stop_loss_price",
            "stop_loss_source_quote_snapshot_id",
            "stop_loss_frozen_at",
            "stop_loss_effective_trade_date",
            "stop_loss_policy_version",
            "stop_loss_policy_hash",
        ):
            field_clause = SQL.split(f"{field} = CASE", 1)[1].split("END,", 1)[0]
            self.assertIn("THEN NULL", field_clause)
            self.assertIn(f"ELSE position_before.{field}", field_clause)
        self.assertEqual(
            CONTRACT["policy"]["same_episode_add_stop_loss"], "preserve_existing"
        )

    def test_quote_authority_is_n6_only_and_fail_closed(self) -> None:
        for token in (
            "public.n6_virtual_quote_snapshot",
            "quote.quality_status <> 'passed'",
            "quote.quality_reason <> 'ok'",
            "quote.exchange NOT IN ('SH', 'SZ')",
            "interval '2 minutes'",
            "quote.current_price::text IN ('NaN', 'Infinity', '-Infinity')",
        ):
            self.assertIn(token, SQL)
        for polluted_client_field in (
            "p_price",
            "p_quantity",
            "p_account",
            "p_position",
            "p_trade_date",
            "p_principal",
        ):
            self.assertNotIn(polluted_client_field, SQL)

    def test_sell_locks_and_allocates_all_t1_lots_fifo(self) -> None:
        self.assertIn("available_trade_date <= trade_date_date", SQL)
        self.assertIn("ORDER BY available_trade_date, virtual_position_lot_id", SQL)
        self.assertIn("remaining_to_sell", SQL)
        self.assertIn("proposal.source_virtual_position_id IS DISTINCT FROM", SQL)
        self.assertIn("'t1_quantity_not_sellable'", SQL)

    def test_sell_requires_exact_nonnull_holding_episode_before_writes(self) -> None:
        episode_check = SQL.index("proposal.holding_episode_no IS NULL")
        first_business_write = SQL.index("INSERT INTO public.n6_virtual_order")
        self.assertLess(episode_check, first_business_write)
        self.assertIn(
            "proposal.holding_episode_no <> position_before.holding_episode_no",
            SQL,
        )
        self.assertIn("'holding_episode_mismatch'", SQL)
        self.assertEqual(
            CONTRACT["policy"]["sell_holding_episode"],
            "required_exact_current_position_episode",
        )

    def test_source_principal_and_account_pollution_fail_closed(self) -> None:
        self.assertIn("proposal.source_type = 'stop_loss'", SQL)
        self.assertIn("account.principal_id <> proposal.principal_id", SQL)
        self.assertIn("position_before.principal_id <> proposal.principal_id", SQL)
        self.assertIn("proposal.proposal_status <> 'processing'", SQL)
        self.assertIn("proposal.executor_run_id IS DISTINCT FROM p_executor_run_id", SQL)
        self.assertIn("proposal.expires_at <= pg_catalog.clock_timestamp()", SQL)

    def test_trade_session_calendar_lot_and_cash_authority_fail_closed(self) -> None:
        for token in (
            "trade_date_date <> (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date",
            "time '09:30' AND time '11:30'",
            "time '13:00' AND time '15:00'",
            "FROM public.common_trade_calendar",
            "trade_date = trade_date_integer::text AND is_open = true",
            "old_available_lot_quantity + old_locked_lot_quantity",
            "SET lot_status = 'available'",
            "active_cash_snapshot_count",
            "active_cash_snapshot_count <> 1",
            "active_cash_snapshot_id <> cash_before.cash_snapshot_id",
            "'cash_authority_conflict'",
        ):
            self.assertIn(token, SQL)
        self.assertNotIn("trade_date = trade_date_integer AND", SQL)
        self.assertNotIn("trade_date > trade_date_integer AND", SQL)

    def test_sell_position_event_uses_removed_cost_basis_not_proceeds(self) -> None:
        self.assertIn(
            "fill_quantity * position_before.average_cost, 4",
            SQL,
        )
        self.assertIn("position_cost_delta,", SQL)
        self.assertNotIn(
            "CASE WHEN proposal.proposal_side = 'buy' THEN gross_amount ELSE -gross_amount END",
            SQL,
        )
        self.assertEqual(
            CONTRACT["policy"]["sell_position_event_cost_delta"],
            "negative_removed_average_cost_basis",
        )

    def test_idempotency_concurrency_and_atomic_chain(self) -> None:
        self.assertIn("FOR UPDATE", SQL)
        self.assertIn("proposal.proposal_status = 'executed'", SQL)
        self.assertIn("'idempotent', true", SQL)
        self.assertIn("source_proposal_id", SQL)
        order = [
            "INSERT INTO public.n6_virtual_order",
            "INSERT INTO public.n6_virtual_trade",
            "INSERT INTO public.n6_virtual_cash_ledger",
            "INSERT INTO public.n6_virtual_cash_snapshot",
            "INSERT INTO public.n6_virtual_position_event",
            "UPDATE public.n6_virtual_trade_proposal",
        ]
        positions = [SQL.index(token) for token in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("EXCEPTION WHEN", SQL)

    def test_position_event_pointer_is_exact_and_failure_rolls_back_chain(self) -> None:
        event_insert = SQL.index("INSERT INTO public.n6_virtual_position_event")
        pointer_update = SQL.index("SET source_position_event_id = new_position_event_id")
        proposal_finish = SQL.index("SET proposal_status = 'executed'")
        self.assertLess(event_insert, pointer_update)
        self.assertLess(pointer_update, proposal_finish)
        self.assertIn(
            "GET DIAGNOSTICS position_pointer_update_count = ROW_COUNT",
            SQL,
        )
        self.assertIn("IF position_pointer_update_count <> 1 THEN", SQL)
        self.assertIn("RAISE EXCEPTION '046 position event pointer update count", SQL)
        self.assertEqual(
            CONTRACT["position_event_pointer"]["mismatch_behavior"],
            "raise_and_rollback_full_transaction",
        )

    def test_rollback_only_removes_046_interface(self) -> None:
        self.assertIn("DROP FUNCTION IF EXISTS public.n6_executor_apply_claimed_proposal", ROLLBACK)
        for forbidden in ("DELETE FROM", "TRUNCATE", "DROP TABLE", "041_", "042_", "043_", "044_", "045_"):
            self.assertNotIn(forbidden, ROLLBACK.upper())


class ManualActionableBuy063ExecutorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.executor = _function_definition(
            SQL_063, "n6_executor_apply_claimed_proposal"
        )
        cls.executor_057 = _function_definition(
            SQL_057, "n6_executor_apply_claimed_proposal"
        )

    def test_063_executor_delta_from_057_is_exact(self) -> None:
        delta = "".join(
            difflib.unified_diff(
                self.executor_057.splitlines(keepends=True),
                self.executor.splitlines(keepends=True),
                fromfile="057",
                tofile="063",
            )
        )
        self.assertEqual(
            hashlib.sha256(delta.encode()).hexdigest(),
            "a2c4ad832df3bee11455526a940f7cd3745558c2ee9b9e7b90b3c450075312dd",
        )
        self.assertEqual(len(delta.splitlines()), 161)

    def test_targetless_new_position_keeps_lineage_and_writes_not_ready(self) -> None:
        normalization = (
            "IF proposal.locked_target_price IS NULL\n"
            "     OR proposal.locked_target_price::text IN (\n"
            "       'NaN', 'Infinity', '-Infinity'\n"
            "     )\n"
            "     OR proposal.locked_target_price <= 0 THEN\n"
            "    proposal.locked_target_price := NULL;\n"
            "  END IF;"
        )
        self.assertEqual(self.executor.count(normalization), 1)
        self.assertIn(
            "AND proposal.source_signal_projection_id IS NULL THEN",
            self.executor,
        )
        self.assertIn(
            "'signal_projection_lineage_not_ready'",
            self.executor,
        )
        self.assertNotIn("'target_price_not_ready'", self.executor)

        marker = "INSERT INTO public.n6_virtual_position"
        start = self.executor.index(marker)
        columns_text, after_columns = _parenthesized(
            self.executor, self.executor.index("(", start)
        )
        values_marker = self.executor.index("VALUES", after_columns)
        values_text, _ = _parenthesized(
            self.executor, self.executor.index("(", values_marker)
        )
        mapping = dict(
            zip(_top_level_csv(columns_text), _top_level_csv(values_text))
        )
        self.assertEqual(
            mapping["locked_target_price"],
            "proposal.locked_target_price",
        )
        self.assertIn("THEN 'frozen'", mapping["target_price_status"])
        self.assertIn("ELSE 'not_ready'", mapping["target_price_status"])
        self.assertIn(
            "THEN proposal.source_signal_projection_id",
            mapping["target_price_source_signal_projection_id"],
        )
        self.assertIn(
            "ELSE NULL",
            mapping["target_price_source_signal_projection_id"],
        )

        missing = CONTRACT_063["executor"]["new_or_reopened_position"][
            "missing_target"
        ]
        self.assertIsNone(missing["locked_target_price"])
        self.assertEqual(missing["target_price_status"], "not_ready")
        self.assertIsNone(
            missing["target_price_source_signal_projection_id"]
        )
        self.assertEqual(
            CONTRACT_063["executor"]["target_normalization"][
                "missing_nonpositive_or_nonfinite"
            ],
            "normalize_to_null_before_position_write",
        )
        self.assertTrue(
            CONTRACT_063["executor"]["target_normalization"][
                "applies_to_web_ai_and_existing_proposals"
            ]
        )

    def test_positive_target_new_position_is_frozen_without_fabrication(self) -> None:
        positive = CONTRACT_063["executor"]["new_or_reopened_position"][
            "positive_target"
        ]
        self.assertEqual(
            positive["locked_target_price"],
            "proposal.locked_target_price",
        )
        self.assertEqual(positive["target_price_status"], "frozen")
        self.assertEqual(
            positive["target_price_source_signal_projection_id"],
            "proposal.source_signal_projection_id",
        )
        self.assertFalse(
            CONTRACT_063["proposal_create"]["buy_target_policy"][
                "trigger_or_action_price_used_as_target"
            ]
        )
        target_write = self.executor[
            self.executor.index("first_open_trade_date, locked_target_price"):
            self.executor.index(
                ") RETURNING virtual_position_id INTO position_id"
            )
        ]
        self.assertNotIn("fill_price", target_write)
        self.assertNotIn("signal_reference_price", target_write)

    def test_same_episode_add_preserves_target_and_reopen_reselects_state(self) -> None:
        update = self.executor.split(
            "UPDATE public.n6_virtual_position\n    SET position_status", 1
        )[1].split("    WHERE virtual_position_id = position_id;", 1)[0]
        for field in (
            "locked_target_price",
            "target_price_status",
            "target_price_source_signal_projection_id",
        ):
            clause = update.split(f"{field} = CASE", 1)[1].split(
                "\n        END,", 1
            )[0]
            self.assertIn(
                "position_before.position_status = 'closed_virtual'",
                clause,
            )
            self.assertIn("position_before.quantity = 0", clause)
            self.assertIn(f"ELSE position_before.{field}", clause)
        self.assertIn("ELSE 'not_ready'", update)
        self.assertEqual(
            CONTRACT_063["executor"]["same_episode_add"][
                "target_price_status"
            ],
            "preserve_existing",
        )

    def test_063_preserves_budget_quote_t1_and_atomic_write_chain(self) -> None:
        for invariant in (
            "LEAST(300000::numeric, cash_before.available_cash) / fill_price / 100",
            "IF fill_quantity < 100 THEN",
            "quote.quality_status <> 'passed'",
            "interval '2 minutes'",
            "available_trade_date",
            "ORDER BY available_trade_date, virtual_position_lot_id",
            "FOR UPDATE",
            "source_position_event_id = new_position_event_id",
        ):
            self.assertIn(invariant, self.executor_057)
            self.assertIn(invariant, self.executor)
        write_order = [
            "INSERT INTO public.n6_virtual_order",
            "INSERT INTO public.n6_virtual_trade",
            "INSERT INTO public.n6_virtual_cash_ledger",
            "INSERT INTO public.n6_virtual_cash_snapshot",
            "INSERT INTO public.n6_virtual_position_event",
        ]
        positions = [self.executor.index(token) for token in write_order]
        positions.append(
            self.executor.rindex("UPDATE public.n6_virtual_trade_proposal")
        )
        self.assertEqual(positions, sorted(positions))

    def test_063_sell_branch_is_identical_to_057(self) -> None:
        start_marker = (
            "  ELSE\n"
            "    IF position_before.virtual_position_id IS NULL"
        )
        end_marker = "  lineage :="
        sell_057 = self.executor_057[
            self.executor_057.index(start_marker):
            self.executor_057.index(end_marker, self.executor_057.index(start_marker))
        ]
        sell_063 = self.executor[
            self.executor.index(start_marker):
            self.executor.index(end_marker, self.executor.index(start_marker))
        ]
        self.assertEqual(sell_063, sell_057)

    def test_063_policy_lineage_and_rollback_are_exact(self) -> None:
        policy = "n6_btrack_manual_actionable_buy_063_v1"
        self.assertEqual(CONTRACT_063["executor"]["policy_version"], policy)
        self.assertEqual(CONTRACT_063["executor"]["policy_hash"], policy)
        self.assertIn(f"'policy_version', '{policy}'", self.executor)
        self.assertGreaterEqual(self.executor.count(f"'{policy}'"), 10)
        self.assertNotIn(
            "'n6_btrack_virtual_executor_046_v1'",
            self.executor,
        )
        self.assertIn("'n6_virtual_executor_046'", self.executor)
        self.assertNotIn("'n6_virtual_executor_063'", self.executor)
        self.assertEqual(
            CONTRACT_063["executor"]["cash_ledger_source_event_type"],
            "n6_virtual_executor_046_preserved",
        )
        self.assertEqual(
            CONTRACT_063["executor"]["policy_scope"],
            "all_outcomes_written_by_the_063_executor_function",
        )
        restored = _function_definition(
            ROLLBACK_063, "n6_executor_apply_claimed_proposal"
        )
        self.assertEqual(restored, self.executor_057)
        self.assertIn("'n6_btrack_virtual_executor_046_v1'", restored)


class TradeDateAllDayBuy064ExecutorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sql_042 = (
            ROOT / "sql/042_n6_b_track_db_role_policy_schema.sql"
        ).read_text()
        cls.proposal_063 = _function_body(
            SQL_063, "n6_btrack_proposal_create"
        )
        cls.confirm_042 = _function_body(
            sql_042, "n6_btrack_proposal_confirm"
        )
        cls.proposal_list_042 = _function_body(
            sql_042, "n6_btrack_proposal_list"
        )
        cls.transition_guard_042 = _function_body(
            sql_042, "n6_btrack_proposal_transition_guard"
        )
        cls.executor_063 = _function_body(
            SQL_063, "n6_executor_apply_claimed_proposal"
        )

        proposal_list = _replace_exact(
            cls.proposal_list_042,
            SQL_064,
            "proposal_list_status_042",
            "proposal_list_status_064",
            1,
        )
        cls.proposal_list_064 = _replace_exact(
            proposal_list,
            SQL_064,
            "proposal_list_json_042",
            "proposal_list_json_064",
            1,
        )
        cls.transition_guard_064 = _replace_exact(
            cls.transition_guard_042,
            SQL_064,
            "proposal_guard_web_042",
            "proposal_guard_web_064",
            1,
        )

        proposal = cls.proposal_063
        for old_tag, new_tag, expected_count in (
            ("proposal_session_063", "proposal_session_064", 1),
            ("proposal_scope_guard_063", "proposal_scope_guard_064", 1),
            (
                "proposal_reference_guard_063",
                "proposal_reference_guard_064",
                1,
            ),
            ("proposal_insert_063", "proposal_insert_064", 1),
            ("proposal_lineage_063", "proposal_lineage_064", 1),
            ("proposal_return_063", "proposal_return_064", 1),
        ):
            proposal = _replace_exact(
                proposal,
                SQL_064,
                old_tag,
                new_tag,
                expected_count,
            )
        proposal = _replace_exact(
            proposal,
            SQL_064,
            "proposal_retry_anchor_064",
            "proposal_retry_064",
            1,
        )
        cls.proposal_064 = proposal

        confirm = cls.confirm_042
        for old_tag, new_tag in (
            ("confirm_declare_042", "confirm_declare_064"),
            ("confirm_revalidation_042", "confirm_revalidation_064"),
        ):
            confirm = _replace_exact(
                confirm, SQL_064, old_tag, new_tag, 1
            )
        cls.confirm_064 = confirm

        executor = cls.executor_063
        for old_tag, new_tag, expected_count in (
            ("executor_declare_063", "executor_declare_064", 1),
            ("executor_account_063", "executor_account_064", 1),
            ("executor_quote_063", "executor_quote_064", 1),
            ("executor_lineage_063", "executor_lineage_064", 1),
            (
                "executor_fill_policy_063",
                "executor_fill_policy_064",
                1,
            ),
            (
                "executor_trade_fill_policy_063",
                "executor_trade_fill_policy_064",
                1,
            ),
            (
                "executor_row_quote_id_063",
                "executor_row_quote_id_064",
                2,
            ),
            (
                "executor_return_quote_id_063",
                "executor_return_quote_id_064",
                1,
            ),
        ):
            executor = _replace_exact(
                executor,
                SQL_064,
                old_tag,
                new_tag,
                expected_count,
            )
        cls.executor_064 = executor.replace(
            "n6_btrack_manual_actionable_buy_063_v1",
            "n6_btrack_trade_date_all_day_buy_064_v1",
        )

    def test_064_forward_transform_is_exact_and_dynamic_signatures_keep_argument_names(
        self,
    ) -> None:
        self.assertEqual(
            hashlib.sha256(self.proposal_064.encode()).hexdigest(),
            "56e9979559eaec73bab459cd5fb6b3affa897067f7e40d08787e81701c90a47d",
        )
        self.assertEqual(
            hashlib.sha256(self.confirm_064.encode()).hexdigest(),
            "696ad75b2874710d30ecdd3e9ebf2ac7354d9b3698e31e698dbcc51a06d3bee4",
        )
        self.assertEqual(
            hashlib.sha256(self.executor_064.encode()).hexdigest(),
            "beb59b8a4a19fa1c1d0d0508d0c83fe726774581a1e2966442ce5cecd91b5e9c",
        )
        self.assertEqual(
            hashlib.sha256(
                self.proposal_list_064.encode()
            ).hexdigest(),
            "1d87e9f33b17c5fc88d45c63e40a6dbcf0641b78425dd8cea3be0f6078ae4ee2",
        )
        self.assertEqual(
            hashlib.sha256(
                self.transition_guard_064.encode()
            ).hexdigest(),
            "c93231dd1bd456c34c954769016442d7e7fb04f0c040a18ca3a346b6e9745a9c",
        )
        for signature in (
            "p_session_token_hash text,p_source_type text,p_source_id bigint",
            "p_session_token_hash text,p_proposal_id bigint,p_idempotency_key text",
            "p_proposal_id bigint,p_executor_run_id text",
        ):
            self.assertIn(signature, SQL_064)
            self.assertIn(signature, ROLLBACK_064)
        self.assertNotIn(
            "CREATE OR REPLACE FUNCTION "
            "public.n6_btrack_proposal_create(text,text,bigint) ",
            SQL_064,
        )

    def test_064_private_scope_helper_revalidates_projection_scope_and_has_no_direct_acl(
        self,
    ) -> None:
        marker = (
            "CREATE FUNCTION "
            "public.n6_btrack_manual_signal_buy_current_scope"
        )
        start = SQL_064.index(marker)
        end = SQL_064.index("$function$;", start) + len("$function$;")
        helper = SQL_064[start:end]
        for invariant in (
            "SECURITY DEFINER",
            "SET search_path = pg_catalog",
            "p_principal_type NOT IN ('admin', 'human_user')",
            "p_for_trade_date IS DISTINCT FROM current_trade_date",
            "calendar.is_open = true",
            "projection_run.status IN ('passed', 'ready')",
            "projection.direction = 'buy'",
            "= 'eligible'",
            "= 'executed'",
            "p_signal_reference_kind = 'trigger_price'",
            "p_signal_reference_kind = 'action_price'",
            "source.current_reference_price =",
            "principal.owner_user_id = p_user_id",
            "account.virtual_account_status = 'active'",
            "position.position_status = 'open_virtual'",
            "monitor.quality_status = 'reviewed'",
            "realtime_scope.source_type = 'single_row'",
            "RETURN matching_source_count = 1",
        ):
            self.assertIn(invariant, helper)
        self.assertIn(
            "REVOKE ALL ON FUNCTION\n"
            "  public.n6_btrack_manual_signal_buy_current_scope",
            SQL_064,
        )
        self.assertNotRegex(
            SQL_064,
            r"GRANT EXECUTE ON FUNCTION\s+"
            r"public\.n6_btrack_manual_signal_buy_current_scope",
        )
        self.assertEqual(
            CONTRACT_064["server_revalidation"]["private_helper"][
                "direct_execute_roles"
            ],
            [],
        )

    def test_064_create_and_pending_confirm_are_all_day_but_idempotent_replay_is_stable(
        self,
    ) -> None:
        manual_exception = self.proposal_064.index(
            "IF p_source_type = 'signal'\n"
            "     AND v_side = 'buy'"
        )
        conditional_session = self.proposal_064.index(
            "IF NOT (\n"
            "    p_source_type = 'signal'\n"
            "    AND v_side = 'buy'"
        )
        proposal_insert = self.proposal_064.index(
            "INSERT INTO public.n6_virtual_trade_proposal"
        )
        self.assertLess(manual_exception, conditional_session)
        self.assertLess(conditional_session, proposal_insert)
        self.assertIn(
            "NOT public.n6_btrack_manual_signal_buy_current_scope",
            self.proposal_064,
        )
        self.assertIn(
            "shanghai_local_time BETWEEN time '09:30:00' "
            "AND time '11:30:00'",
            self.proposal_064,
        )
        self.assertIn(
            "shanghai_local_time BETWEEN time '13:00:00' "
            "AND time '15:00:00'",
            self.proposal_064,
        )

        pending_revalidation = self.confirm_064.index(
            "IF row_value.proposal_status IN ('pending', 'confirmed')"
        )
        idempotent_success = self.confirm_064.index(
            "IF row_value.proposal_status='confirmed' "
            "AND row_value.confirm_idempotency_key=p_idempotency_key"
        )
        self.assertLess(pending_revalidation, idempotent_success)
        for invariant in (
            "confirmation_generation_token",
            "pg_catalog.split_part(p_idempotency_key, ':', 1) <> 'n6v3'",
            "proposal_generation_mismatch",
            "proposal_trade_date_not_current",
            "current_open_trade_date_required",
            "signal_reference_price_invalid",
            "n6_btrack_manual_signal_buy_current_scope",
        ):
            self.assertIn(invariant, self.confirm_064)
        self.assertTrue(
            CONTRACT_064["proposal_and_confirmation"][
                "idempotent_confirmation_preserved"
            ]
        )

    def test_064_list_reports_time_expired_pending_and_confirmed_as_effective_expired(
        self,
    ) -> None:
        for invariant in (
            "p.proposal_status IN ('pending', 'confirmed')",
            "p.expires_at <= pg_catalog.now()",
            "THEN 'expired'",
            "ELSE p.proposal_status",
            "END AS proposal_status",
        ):
            self.assertIn(invariant, self.proposal_list_064)
        self.assertNotIn(
            "END AS proposal_status",
            self.proposal_list_042,
        )

        def effective_status(
            raw_status: str,
            *,
            timed_out: bool,
        ) -> str:
            if raw_status in {"pending", "confirmed"} and timed_out:
                return "expired"
            return raw_status

        for raw_status, timed_out, expected in (
            ("pending", True, "expired"),
            ("confirmed", True, "expired"),
            ("confirmed", False, "confirmed"),
            ("processing", True, "processing"),
            ("executed", True, "executed"),
        ):
            with self.subTest(
                raw_status=raw_status,
                timed_out=timed_out,
            ):
                self.assertEqual(
                    effective_status(
                        raw_status,
                        timed_out=timed_out,
                    ),
                    expected,
                )

    def test_064_rearms_only_the_same_unfilled_expired_manual_signal_row(
        self,
    ) -> None:
        retry = _dollar_assignment(
            SQL_064,
            "new_text",
            "proposal_retry_064",
        )
        retry_update = retry.split(
            "  INSERT INTO public.n6_virtual_trade_proposal (",
            1,
        )[0]
        current_scope_guard = self.proposal_064.index(
            "NOT public.n6_btrack_manual_signal_buy_current_scope"
        )
        retry_anchor = self.proposal_064.index(
            "-- n6_064_manual_signal_retry_rearm"
        )
        self.assertLess(current_scope_guard, retry_anchor)
        for invariant in (
            "existing_proposal.source_type = 'signal'",
            "existing_proposal.source_signal_projection_id = v_projection_id",
            "FOR UPDATE",
            "result_row.proposal_side IS DISTINCT FROM 'buy'",
            "result_row.actor_ai_user_id IS NOT NULL",
            "result_row.source_ai_decision_id IS NOT NULL",
            "result_row.strategy_action_id IS NOT NULL",
            "result_row.proposal_status IN ('processing', 'executed')",
            "result_row.proposal_status IN (\n"
            "             'expired', 'failed', 'rejected'",
            "result_row.proposal_status IN ('pending', 'confirmed')",
            "result_row.expires_at <=\n"
            "                 pg_catalog.clock_timestamp()",
            "existing_order.source_proposal_id =\n"
            "                 result_row.proposal_id",
            "existing_trade.source_proposal_id =\n"
            "                 result_row.proposal_id",
            "SET holding_episode_no = v_episode",
            "proposal_status = 'pending'",
            "expires_at =\n"
            "            pg_catalog.clock_timestamp() + interval '60 seconds'",
            "confirmed_at = NULL",
            "confirm_idempotency_key = NULL",
            "executor_run_id = NULL",
            "failure_reason = NULL",
            "WHERE proposal_id = result_row.proposal_id",
            "'manual_retry_audit'",
            "'confirmation_generation_token'",
            "pg_catalog.gen_random_uuid()::text",
            "'previous_proposal_status'",
            "'previous_expires_at'",
            "'previous_confirmed_at'",
            "'retried_at'",
            "'rearmed', true",
            "'proposal_id', result_row.proposal_id",
        ):
            self.assertIn(invariant, retry_update)
        self.assertNotIn(
            "INSERT INTO public.n6_virtual_trade_proposal",
            retry_update,
        )

    def test_064_retry_transition_guard_is_manual_current_signal_and_zero_fill_only(
        self,
    ) -> None:
        retry_guard = self.transition_guard_064.split(
            "-- n6_064_manual_signal_retry_transition",
            1,
        )[1].split(
            "    ELSE\n"
            "      RAISE EXCEPTION 'web proposal transition rejected",
            1,
        )[0]
        for invariant in (
            "ELSIF COALESCE((",
            "), false) THEN\n      NULL;",
            "OLD.source_type = 'signal'",
            "NEW.source_type = 'signal'",
            "OLD.principal_type IN ('admin', 'human_user')",
            "OLD.actor_ai_user_id IS NULL",
            "OLD.source_ai_decision_id IS NULL",
            "OLD.strategy_action_id IS NULL",
            "OLD.proposal_side = 'buy'",
            "NEW.proposal_side = 'buy'",
            "NEW.source_signal_projection_id =\n"
            "          OLD.source_signal_projection_id",
            "OLD.proposal_status IN ('expired', 'failed', 'rejected')",
            "OLD.proposal_status IN ('pending', 'confirmed')",
            "OLD.expires_at <= pg_catalog.clock_timestamp()",
            "NEW.proposal_status = 'pending'",
            "OLD.executed_virtual_order_id IS NULL",
            "NEW.executed_virtual_order_id IS NULL",
            "OLD.executed_virtual_trade_id IS NULL",
            "NEW.executed_virtual_trade_id IS NULL",
            "NEW.executor_run_id IS NULL",
            "NEW.failure_reason IS NULL",
            "NEW.source_lineage_json->>'manual_buy_policy_version' =",
            "'n6_btrack_trade_date_all_day_buy_064_v1'",
            "NEW.source_lineage_json\n"
            "            ->>'confirmation_generation_token' IS NOT NULL",
            "IS DISTINCT FROM\n"
            "          OLD.source_lineage_json\n"
            "            ->>'confirmation_generation_token'",
            "NEW.source_lineage_json->>'for_trade_date' =",
            "AT TIME ZONE 'Asia/Shanghai'",
            "public.n6_btrack_manual_signal_buy_current_scope(",
            "NEW.source_signal_projection_id",
            "NEW.signal_reference_kind",
            "NEW.signal_reference_price",
            "existing_order.source_proposal_id = OLD.proposal_id",
            "existing_trade.source_proposal_id = OLD.proposal_id",
        ):
            self.assertIn(invariant, retry_guard)
        for forbidden_status in ("processing", "executed"):
            self.assertNotIn(
                f"OLD.proposal_status = '{forbidden_status}'",
                retry_guard,
            )

    def test_064_confirmed_expiry_rejection_precedes_same_key_idempotency(
        self,
    ) -> None:
        expiry_rejection = self.confirm_064.index(
            "-- n6_064_confirm_expiry_precedes_idempotency"
        )
        idempotent_success = self.confirm_064.index(
            "IF row_value.proposal_status='confirmed' "
            "AND row_value.confirm_idempotency_key=p_idempotency_key"
        )
        self.assertLess(expiry_rejection, idempotent_success)
        expiry_branch = self.confirm_064[
            expiry_rejection:idempotent_success
        ]
        for invariant in (
            "row_value.proposal_status = 'confirmed'",
            "row_value.expires_at <= pg_catalog.clock_timestamp()",
            "'status', 'expired'",
            "'error', 'proposal_expired'",
        ):
            self.assertIn(invariant, expiry_branch)

    def test_064_confirmation_generation_blocks_old_rearmed_request(self) -> None:
        for source in (
            self.proposal_list_064,
            self.proposal_064,
            self.confirm_064,
            self.transition_guard_064,
        ):
            self.assertIn("confirmation_generation_token", source)
        self.assertIn(
            "pg_catalog.gen_random_uuid()::text",
            self.proposal_064,
        )
        generation_rejection = self.confirm_064.index(
            "'error', 'proposal_generation_mismatch'"
        )
        idempotent_success = self.confirm_064.index(
            "IF row_value.proposal_status='confirmed' "
            "AND row_value.confirm_idempotency_key=p_idempotency_key"
        )
        self.assertLess(generation_rejection, idempotent_success)
        self.assertEqual(
            CONTRACT_064["proposal_and_confirmation"][
                "confirmation_generation"
            ]["old_or_missing_generation"],
            "fail_closed_proposal_generation_mismatch",
        )

        def may_confirm(stored_generation: str, request_key: str) -> bool:
            parts = request_key.split(":", 2)
            return (
                len(parts) == 3
                and parts[0] == "n6v3"
                and parts[1] == stored_generation
                and bool(parts[2])
            )

        old_key = "n6v3:generation-n:old-confirm"
        self.assertTrue(may_confirm("generation-n", old_key))
        self.assertFalse(may_confirm("generation-n-plus-1", old_key))
        self.assertFalse(
            may_confirm("generation-n-plus-1", "legacy-random-key")
        )

    def test_064_price_priority_and_time_boundaries_are_explicit(self) -> None:
        fresh = self.executor_064.index(
            "fill_price_source := 'quote_current_price'"
        )
        same_day = self.executor_064.index(
            "'same_day_last_quote_current_price'"
        )
        reference = self.executor_064.index(
            "fill_price_source := 'signal_reference_price'"
        )
        self.assertLess(fresh, same_day)
        self.assertLess(same_day, reference)
        for invariant in (
            "interval '2 minutes'",
            "candidate.exchange =\n"
            "          pg_catalog.split_part(proposal.identity_key, ':', 2)",
            "candidate.fetched_at >= candidate.quote_minute",
            "current_local_time > time '11:30'",
            "current_local_time < time '13:00'",
            "current_local_time > time '15:00'",
            "fill_quote_snapshot_id := NULL",
            "fill_price_field := proposal.signal_reference_kind",
            "'preopen_no_same_day_quote'",
            "'outside_session_no_usable_same_day_quote'",
        ):
            self.assertIn(invariant, self.executor_064)

        def selected_source(
            minute: int, fresh_quote: bool, same_day_quote: bool
        ) -> str:
            if fresh_quote:
                return "quote_current_price"
            lunch_or_postclose = 690 < minute < 780 or minute > 900
            if lunch_or_postclose and same_day_quote:
                return "same_day_last_quote_current_price"
            return "signal_reference_price"

        cases = (
            (0, False, False, "signal_reference_price"),
            (569, False, False, "signal_reference_price"),
            (570, True, False, "quote_current_price"),
            (690, True, False, "quote_current_price"),
            (720, False, True, "same_day_last_quote_current_price"),
            (780, True, True, "quote_current_price"),
            (900, True, True, "quote_current_price"),
            (901, False, True, "same_day_last_quote_current_price"),
            (1439, False, True, "same_day_last_quote_current_price"),
        )
        for minute, has_fresh, has_last, expected in cases:
            with self.subTest(minute=minute):
                self.assertEqual(
                    selected_source(minute, has_fresh, has_last),
                    expected,
                )

    def test_064_non_manual_paths_keep_session_and_fresh_quote_fail_closed(
        self,
    ) -> None:
        non_manual = self.executor_064[
            self.executor_064.index(
                "  ELSE\n"
                "    SELECT * INTO quote\n"
                "    FROM public.n6_virtual_quote_snapshot"
            ):
            self.executor_064.index(
                "  IF cash_before.trade_date > trade_date_integer"
            )
        ]
        for invariant in (
            "'quote_not_ready'",
            "interval '2 minutes'",
            "quote.quality_status <> 'passed'",
            "quote.quality_reason <> 'ok'",
            "quote.current_price::text IN",
            "'trade_session_not_ready'",
            "time '09:30'",
            "time '11:30'",
            "time '13:00'",
            "time '15:00'",
            "fill_policy_id := 'n6_046_latest_quote_fill_v1'",
        ):
            self.assertIn(invariant, non_manual)
        self.assertNotIn(
            "signal_reference_price::numeric(24,6)", non_manual
        )
        self.assertEqual(
            CONTRACT_064["fill_price_policy"][
                "non_manual_buy_behavior"
            ],
            "preserve_063_regular_session_and_fresh_quote_fail_closed",
        )

    def test_064_preserves_targetless_target_budget_cash_t1_and_atomic_chain(
        self,
    ) -> None:
        for invariant in (
            "proposal.locked_target_price := NULL",
            "ELSE 'not_ready'",
            "ELSE position_before.target_price_status",
            "LEAST(300000::numeric, cash_before.available_cash) "
            "/ fill_price / 100",
            "IF fill_quantity < 100 THEN",
            "available_trade_date",
            "'locked_t1'",
            "FOR UPDATE",
            "source_position_event_id = new_position_event_id",
        ):
            self.assertIn(invariant, self.executor_063)
            self.assertIn(invariant, self.executor_064)
        write_order = [
            "INSERT INTO public.n6_virtual_order",
            "INSERT INTO public.n6_virtual_trade",
            "INSERT INTO public.n6_virtual_cash_ledger",
            "INSERT INTO public.n6_virtual_cash_snapshot",
            "INSERT INTO public.n6_virtual_position_event",
            "UPDATE public.n6_virtual_trade_proposal",
        ]
        positions = [
            self.executor_064.rindex(token) for token in write_order
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(
            CONTRACT_064["position_policy"][
                "new_or_reopened_without_positive_target"
            ]["target_price_status"],
            "not_ready",
        )

    def test_064_lineage_and_null_quote_reference_fill_are_auditable(
        self,
    ) -> None:
        for field in (
            "'fill_quote_snapshot_id', fill_quote_snapshot_id",
            "'fill_price_source', fill_price_source",
            "'fill_price_field', fill_price_field",
            "'fill_fallback_reason', fill_fallback_reason",
            "'fill_policy_version', fill_policy_id",
            "'for_trade_date', trade_date_integer::text",
        ):
            self.assertIn(field, self.executor_064)
        self.assertIn(
            "'policy_version', "
            "'n6_btrack_trade_date_all_day_buy_064_v1'",
            self.executor_064,
        )
        self.assertEqual(
            self.executor_064.count(
                "proposal.signal_reference_kind, "
                "proposal.signal_reference_price,\n"
                "    fill_quote_snapshot_id"
            ),
            2,
        )

    def test_064_rollback_exactly_restores_063_042_and_preserves_history(
        self,
    ) -> None:
        proposal_list = _replace_exact(
            self.proposal_list_064,
            ROLLBACK_064,
            "proposal_list_json_064",
            "proposal_list_json_042",
            1,
        )
        proposal_list = _replace_exact(
            proposal_list,
            ROLLBACK_064,
            "proposal_list_status_064",
            "proposal_list_status_042",
            1,
        )
        self.assertEqual(proposal_list, self.proposal_list_042)

        transition_guard = _replace_exact(
            self.transition_guard_064,
            ROLLBACK_064,
            "proposal_guard_web_064",
            "proposal_guard_web_042",
            1,
        )
        self.assertEqual(
            transition_guard,
            self.transition_guard_042,
        )

        proposal = self.proposal_064
        retry_start = proposal.index(
            "  -- n6_064_manual_signal_retry_rearm\n"
        )
        retry_anchor = proposal.index(
            "  INSERT INTO public.n6_virtual_trade_proposal (\n",
            retry_start,
        )
        proposal = proposal[:retry_start] + proposal[retry_anchor:]
        for rollback_invariant in (
            "old_text := '  -- n6_064_manual_signal_retry_rearm'",
            "retry_start := pg_catalog.strpos(source_text, old_text)",
            "retry_anchor := pg_catalog.strpos(",
            "pg_catalog.substr(source_text, 1, retry_start - 1)",
            "pg_catalog.substr(source_text, retry_anchor)",
        ):
            self.assertIn(rollback_invariant, ROLLBACK_064)
        for old_tag, new_tag in (
            ("proposal_return_064", "proposal_return_063"),
            ("proposal_lineage_064", "proposal_lineage_063"),
            ("proposal_insert_064", "proposal_insert_063"),
            ("proposal_scope_guard_064", "proposal_scope_guard_063"),
            ("proposal_target_guard_064", "proposal_target_guard_063"),
            ("proposal_session_064", "proposal_session_063"),
        ):
            proposal = _replace_exact(
                proposal, ROLLBACK_064, old_tag, new_tag, 1
            )
        self.assertEqual(proposal, self.proposal_063)

        confirm = self.confirm_064
        for old_tag, new_tag in (
            ("confirm_revalidation_064", "confirm_revalidation_042"),
            ("confirm_declare_064", "confirm_declare_042"),
        ):
            confirm = _replace_exact(
                confirm, ROLLBACK_064, old_tag, new_tag, 1
            )
        self.assertEqual(confirm, self.confirm_042)

        executor = self.executor_064
        for old_tag, new_tag, expected_count in (
            ("executor_lineage_064", "executor_lineage_063", 1),
            (
                "executor_fill_policy_064",
                "executor_fill_policy_063",
                1,
            ),
            (
                "executor_trade_fill_policy_064",
                "executor_trade_fill_policy_063",
                1,
            ),
            ("executor_quote_064", "executor_quote_063", 1),
            ("executor_account_064", "executor_account_063", 1),
            ("executor_declare_064", "executor_declare_063", 1),
            (
                "executor_row_quote_id_064",
                "executor_row_quote_id_063",
                2,
            ),
            (
                "executor_return_quote_id_064",
                "executor_return_quote_id_063",
                1,
            ),
        ):
            executor = _replace_exact(
                executor,
                ROLLBACK_064,
                old_tag,
                new_tag,
                expected_count,
            )
        executor = executor.replace(
            "n6_btrack_trade_date_all_day_buy_064_v1",
            "n6_btrack_manual_actionable_buy_063_v1",
        )
        self.assertEqual(executor, self.executor_063)
        self.assertIn(
            "DROP FUNCTION "
            "public.n6_btrack_manual_signal_buy_current_scope",
            ROLLBACK_064,
        )
        for forbidden in (
            "DELETE FROM",
            "TRUNCATE",
            "DROP TABLE",
        ):
            self.assertNotIn(forbidden, ROLLBACK_064.upper())
        rollback_contract = CONTRACT_064["rollback"]
        self.assertEqual(
            rollback_contract[
                "restore_exact_063_executor_sha256"
            ],
            hashlib.sha256(self.executor_063.encode()).hexdigest(),
        )
        self.assertTrue(
            rollback_contract[
                "preserve_historical_proposals_orders_trades_cash_lots_positions_and_events"
            ]
        )

    def test_064_contract_keeps_runtime_and_broker_closed_in_this_gate(
        self,
    ) -> None:
        runtime = CONTRACT_064["runtime"]
        for key in (
            "active_database_write_performed",
            "active_migration_executed_in_this_gate",
            "release_built_or_switched_in_this_gate",
            "proposal_or_confirm_sent_in_this_gate",
            "executor_started_in_this_gate",
            "broker_or_real_order_touched_in_this_gate",
        ):
            with self.subTest(key=key):
                self.assertFalse(runtime[key])
        for key in (
            "active_database_read_only_preflight_performed",
            "isolated_postgresql_16_migration_roundtrip_passed",
            "isolated_postgresql_16_business_acceptance_passed",
        ):
            with self.subTest(key=key):
                self.assertTrue(runtime[key])
        self.assertFalse(
            CONTRACT_064["preserved_boundaries"][
                "mootdx_change_is_direct_root_cause"
            ]
        )
        self.assertFalse(
            CONTRACT_064["preserved_boundaries"][
                "quote_writer_schedule_changed"
            ]
        )


class VirtualStopLossRunner049Test(unittest.TestCase):
    def test_default_is_zero_connection_and_zero_dml(self) -> None:
        from scripts.run_n6_virtual_stop_loss_once import run_from_args

        calls = []
        result = run_from_args(
            argparse.Namespace(executor_run_id="stop-49", execute=False, dsn=None),
            connect=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
        self.assertEqual(result["status"], "read_only_preflight")
        self.assertFalse(result["db_connected"])
        self.assertFalse(result["dml"])
        self.assertEqual(calls, [])

    def test_execute_calls_freeze_and_evaluate_once_in_one_transaction(self) -> None:
        from scripts.run_n6_virtual_stop_loss_once import run_from_args

        connection = FakeConnection(payloads=[
            {"ok": True, "status": "frozen"},
            {"ok": True, "status": "confirmed"},
        ])
        args = argparse.Namespace(executor_run_id="stop-49", execute=True, dsn=None)
        environment = {
            "PGSERVICE": "n6_virtual_executor",
            "PGSERVICEFILE": "/restricted/pg_service.conf",
            "PGPASSFILE": "/restricted/pgpass",
        }
        with patch.dict("os.environ", environment, clear=True):
            result = run_from_args(args, connect=lambda *a, **k: connection)
        self.assertEqual(result["status"], "completed")
        executes = [call for call in connection.calls if call[0] == "execute"]
        self.assertEqual(len(executes), 2)
        self.assertIn("n6_executor_freeze_next_stop_loss", executes[0][1])
        self.assertIn("n6_executor_evaluate_next_stop_loss", executes[1][1])
        self.assertEqual(connection.calls[-1], ("commit",))
        self.assertTrue(connection.closed)

    def test_exception_rolls_back_and_restricted_credentials_are_exact(self) -> None:
        from scripts.run_n6_virtual_stop_loss_once import (
            run_from_args,
            validate_executor_environment,
        )

        with self.assertRaises(ValueError):
            validate_executor_environment({"PGSERVICE": "wrong"})
        with self.assertRaises(ValueError):
            validate_executor_environment({
                "PGSERVICE": "n6_virtual_executor", "PGPASSWORD": "secret"
            })
        connection = FakeConnection(fail_on_execute=2)
        args = argparse.Namespace(executor_run_id="stop-49", execute=True, dsn=None)
        with patch.dict("os.environ", {"PGSERVICE": "n6_virtual_executor"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "atomic_failure"):
                run_from_args(args, connect=lambda *a, **k: connection)
        self.assertIn(("rollback",), connection.calls)
        self.assertFalse(any(call[0] == "commit" for call in connection.calls))

    def test_049_apply_terminal_vs_retry_classification_and_zero_account_writes(self) -> None:
        sql = (ROOT / "sql/049_n6_virtual_stop_loss_freeze_evaluate_execute.sql").read_text()
        self.assertIn("proposal.source_type = 'stop_loss'", sql)
        self.assertIn("proposal.source_virtual_position_id IS DISTINCT FROM", sql)
        self.assertIn("proposal_status = 'failed'", sql)
        self.assertIn("'account_writes', 0", sql)
        self.assertIn("'stop_loss_quote_recovered'", sql)
        self.assertIn("'stop_loss_t1_lot_not_sellable'", sql)
        self.assertIn("proposal.source_type = 'stop_loss' AND quote.fetched_at < quote.quote_minute", sql)
        stop_terminal = sql.index("IF proposal.source_type = 'stop_loss' THEN", sql.index("INTO old_available_lot_quantity"))
        generic_mismatch = sql.index("IF proposal.source_type <> 'stop_loss'\n     AND position_before.position_status", stop_terminal)
        first_account_insert = sql.index("INSERT INTO public.n6_virtual_order")
        self.assertLess(stop_terminal, generic_mismatch)
        self.assertLess(generic_mismatch, first_account_insert)
        stop_block = sql[stop_terminal:generic_mismatch]
        self.assertIn("proposal.source_virtual_position_id IS DISTINCT FROM", stop_block)
        self.assertIn("old_available_lot_quantity <= 0", stop_block)
        self.assertIn("'account_writes', 0", stop_block)
        transient = sql.index("IF NOT FOUND\n     OR quote.quality_status")
        account_write = sql.index("INSERT INTO public.n6_virtual_order")
        self.assertLess(transient, account_write)


if __name__ == "__main__":
    unittest.main()
