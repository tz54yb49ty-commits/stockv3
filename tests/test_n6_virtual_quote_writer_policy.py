from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/051_n6_virtual_quote_writer_policy.sql"
ROLLBACK = ROOT / "sql/051_n6_virtual_quote_writer_policy_rollback.sql"
CONTRACT = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_QUOTE_WRITER_CONTRACT.json"
PERSISTENCE = ROOT / "src/ashare_v3/user/virtual_quote_persistence.py"
RUNNER = ROOT / "scripts/run_n6_virtual_quote_once.py"


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


class N6VirtualQuoteWriterPolicyTests(unittest.TestCase):
    def test_scope_is_active_account_position_union_live_buy_proposal(self) -> None:
        sql = normalized(MIGRATION)
        scope = sql.split(
            "create or replace function public.n6_quote_writer_scope", 1
        )[1].split(
            "create or replace function public.n6_quote_writer_pending_scope", 1
        )[0]
        self.assertEqual(
            scope.count("join public.n6_principal principal"), 1
        )
        self.assertRegex(
            scope,
            r"join public\.n6_principal principal on principal\.principal_id = a\.principal_id",
        )
        self.assertIn("principal.principal_status = 'active'", sql)
        self.assertIn("a.virtual_account_status = 'active'", sql)
        self.assertIn("a.principal_type in ('admin', 'human_user')", sql)
        self.assertIn("position.position_status = 'open_virtual'", sql)
        self.assertIn("position.quantity > 0", sql)
        self.assertIn("union select a.principal_id", sql)
        self.assertIn("proposal.proposal_side = 'buy'", sql)
        self.assertIn("proposal.proposal_status in ('pending', 'confirmed')", sql)
        self.assertIn(
            "proposal.expires_at > pg_catalog.clock_timestamp()", sql
        )

    def test_proposal_scope_rejects_sell_non_stock_terminal_and_source_drift(self) -> None:
        sql = normalized(MIGRATION)
        self.assertIn("proposal.asset_kind = 'stock'", sql)
        self.assertNotIn(
            "proposal.proposal_status in ('pending', 'confirmed', 'processing')",
            sql,
        )
        for terminal in ("rejected", "executed", "expired", "failed"):
            scope = sql.split(
                "create or replace function public.n6_quote_writer_scope", 1
            )[1].split(
                "create or replace function public.n6_quote_writer_save_run", 1
            )[0]
            self.assertNotIn(f"'{terminal}'", scope)
        self.assertIn(
            "proposal.virtual_account_id = a.virtual_account_id", sql
        )
        self.assertIn("proposal.principal_id = a.principal_id", sql)
        self.assertIn("proposal.principal_type = a.principal_type", sql)
        self.assertIn("proposal.user_id = a.owner_user_id", sql)
        self.assertIn(
            "source.user_signal_projection_id = proposal.source_signal_projection_id",
            sql,
        )
        self.assertIn("source.identity_key = proposal.identity_key", sql)
        self.assertIn("source.direction = proposal.proposal_side", sql)

    def test_minute_cap_and_not_ready_failure_contract_are_explicit(self) -> None:
        sql = normalized(MIGRATION)
        self.assertIn("public.n6_quote_writer_pending_scope", sql)
        self.assertIn(
            "existing.identity_key = scope.identity_key", sql
        )
        self.assertIn("existing.quote_minute = p_quote_minute", sql)
        self.assertIn(
            "on conflict (identity_key, quote_minute) do nothing", sql
        )
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["scheduler"]["cadence_seconds"], 5)
        self.assertTrue(contract["race_contract"]["normal_path_closed"])
        self.assertFalse(
            contract["race_contract"]["provider_failure_ttl_guarantee"]
        )
        self.assertEqual(
            contract["race_contract"]["same_minute_not_ready_retry"],
            "forbidden",
        )

    def test_role_is_function_only_and_provisioning_is_external(self) -> None:
        sql = normalized(MIGRATION)
        self.assertIn("required role missing: n6_quote_writer", sql)
        self.assertIn("direct relation privilege rejected", sql)
        self.assertIn("direct sequence privilege rejected", sql)
        self.assertIn(
            "grant execute on function public.n6_quote_writer_scope", sql
        )
        self.assertNotRegex(sql, r"\bcreate\s+role\b")
        self.assertNotRegex(sql, r"\balter\s+role\b")
        self.assertNotIn("password", sql)
        self.assertNotRegex(
            sql,
            r"grant\s+(select|insert|update|delete|usage\s+on\s+sequence)",
        )
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertIn(
            "NOINHERIT",
            contract["database_role"]["provisioning_role_attributes"],
        )

    def test_evidence_schema_is_reentrant_and_fails_closed_on_drift(self) -> None:
        sql = normalized(MIGRATION)
        self.assertIn(
            "create table if not exists public.n6_virtual_quote_run_identity", sql
        )
        self.assertIn(
            "create index if not exists idx_051_n6_virtual_quote_run_identity_snapshot", sql
        )
        for drift_guard in (
            "evidence table owner/kind drift",
            "evidence table column drift",
            "evidence table constraint drift",
            "evidence index drift",
            "pg_catalog.pg_get_constraintdef",
            "pg_catalog.pg_get_indexdef",
            "not con.condeferrable",
            "not con.condeferred",
            "con.convalidated",
            "constraints_exact is distinct from true",
            "constraint_count <> 7",
            "index_row.indisvalid",
            "index_row.indisready",
            "index_owner <> current_user",
            "index_kind <> 'i'",
        ):
            self.assertIn(drift_guard, sql)

    def test_catalog_char_columns_are_cast_before_text_concatenation(self) -> None:
        sql = normalized(MIGRATION)
        self.assertIn("a.attidentity::text", sql)
        self.assertNotRegex(sql, r"\|\|\s*a\.attidentity(?!\s*::text)")
        self.assertNotRegex(sql, r"\|\|\s*a\.attgenerated(?!\s*::text)")

    def test_save_function_validates_payload_and_authorized_scope(self) -> None:
        sql = normalized(MIGRATION)
        save = sql.split(
            "create or replace function public.n6_quote_writer_save_run", 1
        )[1]
        for required in (
            "jsonb_object_keys(batch_value)",
            "jsonb_object_keys(item_value)",
            "provider_intraday_time_without_trade_date",
            "batch_item_count <> (batch_value->>'item_count')::integer",
            "payload_count <> p_scoped_identity_count",
            "payload_passed_count <> p_passed_count",
            "payload_not_ready_count <> p_not_ready_count",
            "count(distinct item.value->>'identity_key')",
            "scope and batch identity sets differ",
            "public.n6_quote_writer_scope(p_quote_minute)",
            "allowed.principal_id = p_principal_id",
            "allowed.principal_type = p_principal_type",
            "existing quote snapshot conflicts with payload",
            "(batch->>'batch_id')::uuid",
            "invalid passed quote item",
            "invalid not-ready quote item",
            "at time zone 'asia/shanghai'",
            "public.common_trade_calendar",
            "pg_catalog.clock_timestamp() at time zone 'asia/shanghai'",
            "p_started_at >= p_quote_minute + interval '60 seconds'",
            "interval '75 seconds'",
        ):
            self.assertIn(required, save)

    def test_quote_writer_dml_is_quote_evidence_only(self) -> None:
        sql = normalized(MIGRATION)
        save = sql.split(
            "create or replace function public.n6_quote_writer_save_run", 1
        )[1]
        for allowed in (
            "insert into public.n6_virtual_quote_run",
            "insert into public.n6_virtual_quote_snapshot",
            "insert into public.n6_virtual_quote_run_identity",
            "update public.n6_virtual_quote_run",
        ):
            self.assertIn(allowed, save)
        for forbidden in (
            "insert into public.n6_virtual_trade_proposal",
            "update public.n6_virtual_trade_proposal",
            "insert into public.n6_virtual_order",
            "update public.n6_virtual_order",
            "insert into public.n6_virtual_trade",
            "update public.n6_virtual_trade",
            "insert into public.n6_virtual_position",
            "update public.n6_virtual_position",
            "insert into public.n6_virtual_cash",
            "update public.n6_virtual_cash",
            "user_monitor_",
            "user_signal_projection set",
        ):
            self.assertNotIn(forbidden, save)

    def test_rollback_preserves_all_quote_history(self) -> None:
        rollback = normalized(ROLLBACK)
        self.assertNotRegex(rollback, r"\b(delete|truncate)\b")
        self.assertNotIn("drop table", rollback)
        self.assertIn(
            "do not drop public.n6_virtual_quote_run_identity", rollback
        )

    def test_runtime_sources_have_no_account_dml_or_secret_literal(self) -> None:
        source = (
            PERSISTENCE.read_text(encoding="utf-8")
            + "\n"
            + RUNNER.read_text(encoding="utf-8")
        )
        lowered = source.lower()
        for target in (
            "n6_virtual_order",
            "n6_virtual_trade_proposal set",
            "n6_virtual_trade ",
            "n6_virtual_position set",
            "cash_ledger",
            "cash_snapshot",
        ):
            self.assertNotIn(target, lowered)
        self.assertNotRegex(
            source,
            re.compile(r"postgres(?:ql)?://[^\\s'\"]+@", re.IGNORECASE),
        )
        self.assertNotRegex(
            source,
            re.compile(r"(?:password|secret)\\s*=\\s*['\"][^'\"]+['\"]", re.IGNORECASE),
        )

    def test_contract_freezes_source_and_ui_retry_boundaries(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["layer_role"], "N6_user")
        self.assertEqual(contract["provider"]["authority"], "frozen_N3N6Q")
        self.assertEqual(contract["provider"]["fallbacks"], [])
        self.assertFalse(contract["runtime"]["database_connected_in_gate"])
        self.assertFalse(contract["runtime"]["scheduler_started_in_gate"])
        self.assertEqual(
            contract["race_contract"]["minimum_follow_up_ticks_before_expiry"],
            11,
        )
        self.assertEqual(
            contract["race_contract"]["provider_failure_ui"],
            "show_quote_not_ready_and_require_user_retry",
        )


if __name__ == "__main__":
    unittest.main()
