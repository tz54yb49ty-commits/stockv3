from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

from ashare_v3.user.human_virtual_account_provisioning import (
    BACKFILL_TARGETS,
    ProvisioningGateError,
    run_provisioning_once,
)


ROOT = Path(__file__).resolve().parents[1]


class _Context:
    def __init__(self, value: Any) -> None:
        self.value = value

    def __enter__(self) -> Any:
        return self.value

    def __exit__(self, *_: object) -> None:
        return None


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.last_sql = ""
        self.last_params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: Any = None) -> None:
        self.last_sql = " ".join(sql.split())
        self.last_params = tuple(params or ())
        self.calls.append((self.last_sql, self.last_params))

    def fetchone(self) -> dict[str, Any] | None:
        if "FROM public.n6_principal p" in self.last_sql:
            principal_id = int(self.last_params[0])
            return {
                "principal_id": principal_id,
                "principal_type": "human_user",
                "principal_status": "active",
                "user_id": principal_id - 1,
                "login_name": BACKFILL_TARGETS[principal_id],
                "role": "user",
                "user_status": "active",
                "account_count": 0,
                "mapping_count": 0,
                "ledger_count": 0,
                "snapshot_count": 0,
                "complete_chain_count": 0,
            }
        if "n6_provision_human_virtual_account" in self.last_sql:
            principal_id = int(self.last_params[0])
            return {"result": {"ok": True, "status": "created", "principal_id": principal_id}}
        return None


class _Connection:
    def __init__(self) -> None:
        self.cursor_value = _Cursor()

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def transaction(self) -> _Context:
        return _Context(self)

    def cursor(self) -> _Context:
        return _Context(self.cursor_value)


class ProvisioningContractTest(unittest.TestCase):
    def test_forward_sql_is_atomic_fixed_authority_and_has_no_trade_side_effects(self) -> None:
        sql = (ROOT / "sql/074_n6_human_virtual_account_provisioning.sql").read_text(encoding="utf-8")
        compact = re.sub(r"\s+", " ", sql)
        self.assertIn("SECURITY DEFINER", sql)
        self.assertIn("SET search_path = pg_catalog", sql)
        self.assertIn("REVOKE ALL ON FUNCTION public.n6_provision_human_virtual_account(bigint) FROM PUBLIC", compact)
        self.assertIn("GRANT EXECUTE ON FUNCTION public.n6_provision_human_virtual_account(bigint) TO n6_btrack_web", compact)
        self.assertIn("c_initial_cash constant numeric(24, 4) := 100000000.0000", sql)
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertGreaterEqual(sql.count("FOR UPDATE"), 2)
        self.assertLess(
            sql.index("INSERT INTO public.n6_virtual_account"),
            sql.index("INSERT INTO public.n6_virtual_cash_ledger"),
        )
        self.assertLess(
            sql.index("INSERT INTO public.n6_virtual_cash_ledger"),
            sql.index("INSERT INTO public.n6_virtual_cash_snapshot"),
        )
        self.assertLess(
            sql.index("INSERT INTO public.n6_virtual_cash_snapshot"),
            sql.index("INSERT INTO public.n6_principal_account"),
        )
        for table in (
            "n6_virtual_account",
            "n6_virtual_cash_ledger",
            "n6_virtual_cash_snapshot",
            "n6_principal_account",
        ):
            self.assertIn(f"INSERT INTO public.{table}", compact)
        self.assertIn("'status', 'noop'", sql)
        self.assertIn("partial or duplicate account chain blocked", sql)
        self.assertIn("account_mapping.virtual_account_id = v_account.virtual_account_id", sql)
        for table in (
            "n6_virtual_trade_proposal",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_position_lot",
            "common_event_outbox",
        ):
            self.assertNotIn(f"INSERT INTO public.{table}", compact)

    def test_rollback_blocks_downstream_and_recursive_event_references(self) -> None:
        sql = (ROOT / "sql/074_n6_human_virtual_account_provisioning_rollback.sql").read_text(encoding="utf-8")
        compact = re.sub(r"\s+", " ", sql)
        self.assertIn("074 rollback BLOCKED by downstream references for account", sql)
        self.assertIn("jsonb_path_exists", sql)
        self.assertIn("n6_ai_strategy_action", sql)
        self.assertIn("n6_virtual_cash_ledger ledger\n           WHERE ledger.virtual_account_id", sql)
        self.assertIn("n6_virtual_cash_snapshot snapshot\n           WHERE snapshot.virtual_account_id", sql)
        recursive_path = "$.**.virtual_account_id ? (@ == $account_id || @ == $account_id_text)"
        self.assertEqual(sql.count(recursive_path), 4)
        self.assertEqual(sql.count("'account_id_text', account_row.virtual_account_id::text"), 4)
        for relation, json_column in (
            ("common_event_ledger", "payload_json"),
            ("common_event_outbox", "payload_json"),
            ("common_event_inbox", "payload_json"),
            ("common_event_inbox", "raw_json"),
        ):
            self.assertRegex(
                compact,
                rf"SELECT 1 FROM public\.{relation} row_value .*?row_value\.{json_column}, "
                rf"'\$\.\*\*\.virtual_account_id \? \(@ == \$account_id \|\| @ == \$account_id_text\)'",
            )
        self.assertIn("UPDATE public.n6_virtual_account", sql)
        self.assertLess(sql.index("DELETE FROM public.n6_virtual_cash_snapshot"), sql.index("DELETE FROM public.n6_virtual_account"))
        self.assertLess(sql.index("DROP FUNCTION public.n6_provision_human_virtual_account"), sql.index("COMMIT;"))

    def test_dry_run_is_read_only_and_does_not_call_provisioning_function(self) -> None:
        connection = _Connection()
        report = run_provisioning_once(service="test", connect=lambda **_: connection)
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual([row["decision"] for row in report["targets"]], ["create", "create"])
        sql_calls = [sql for sql, _ in connection.cursor_value.calls]
        self.assertIn("SET TRANSACTION READ ONLY", sql_calls)
        self.assertFalse(any(sql.startswith("SELECT public.n6_provision") for sql in sql_calls))

    def test_execute_requires_exact_allowlist_and_explicit_authorization(self) -> None:
        with self.assertRaisesRegex(ProvisioningGateError, "execute_not_authorized"):
            run_provisioning_once(
                service="test",
                execute=True,
                execute_authorized=True,
                connect=lambda **_: self.fail("connection must not open"),
            )
        with self.assertRaisesRegex(ProvisioningGateError, "invalid_principal_allowlist"):
            run_provisioning_once(
                service="test",
                principal_ids=[],
                execute=True,
                execute_authorized=True,
                connect=lambda **_: self.fail("connection must not open"),
            )
        with self.assertRaisesRegex(ProvisioningGateError, "execute_not_authorized"):
            run_provisioning_once(
                service="test",
                principal_ids=[8],
                execute=True,
                execute_authorized=True,
                connect=lambda **_: self.fail("connection must not open"),
            )
        connection = _Connection()
        report = run_provisioning_once(
            service="test",
            principal_ids=[9, 8],
            execute=True,
            execute_authorized=True,
            connect=lambda **_: connection,
        )
        self.assertEqual(report["mode"], "execute")
        self.assertEqual([row["principal_id"] for row in report["results"]], [8, 9])
        calls = [sql for sql, _ in connection.cursor_value.calls if sql.startswith("SELECT public.n6_provision")]
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
