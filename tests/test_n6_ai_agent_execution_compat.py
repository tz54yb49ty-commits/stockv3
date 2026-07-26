from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/057_n6_ai_agent_execution_compat.sql"
ROLLBACK = ROOT / "sql/057_n6_ai_agent_execution_compat_rollback.sql"
QUOTE_051 = ROOT / "sql/051_n6_virtual_quote_writer_policy.sql"
STOP_049 = ROOT / "sql/049_n6_virtual_stop_loss_freeze_evaluate_execute.sql"


def _function(sql: str, name: str) -> str:
    pattern = re.compile(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\("
        rf".*?\n\$function\$;",
        re.DOTALL,
    )
    match = pattern.search(sql)
    if match is None:
        raise AssertionError(f"missing function: {name}")
    return match.group(0)


class N6AiAgentExecutionCompatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")
        cls.quote_051 = QUOTE_051.read_text(encoding="utf-8")
        cls.stop_049 = STOP_049.read_text(encoding="utf-8")

    def test_exact_function_only_migration_boundary(self) -> None:
        self.assertTrue(self.migration.startswith("-- N6 AI Agent v1"))
        self.assertEqual(self.migration.count("\nBEGIN;"), 1)
        self.assertEqual(self.migration.count("\nCOMMIT;"), 1)
        self.assertEqual(
            re.findall(
                r"CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)\(",
                self.migration,
            ),
            [
                "n6_quote_writer_scope",
                "n6_quote_writer_save_run",
                "n6_executor_evaluate_next_stop_loss",
                "n6_executor_apply_claimed_proposal",
            ],
        )
        for forbidden in (
            "CREATE TABLE",
            "ALTER TABLE",
            "DROP TABLE",
            "CREATE ROLE",
            "ALTER ROLE",
            "CREATE TRIGGER",
            "DROP TRIGGER",
            "EXECUTE format(",
            "EXECUTE '",
        ):
            self.assertNotIn(forbidden, self.migration)

    def test_quote_scope_supports_active_ai_without_human_regression(self) -> None:
        scope = _function(self.migration, "n6_quote_writer_scope")
        self.assertIn("a.principal_type IN ('admin', 'human_user')", scope)
        self.assertIn("principal.owner_user_id IS NOT NULL", scope)
        self.assertIn("LEFT JOIN public.n6_ai_user ai", scope)
        self.assertIn("ai.status = 'active'", scope)
        self.assertIn("a.principal_type = 'ai_user'", scope)
        self.assertIn("principal.owner_user_id IS NULL", scope)
        self.assertIn("proposal.user_id IS NULL", scope)
        self.assertIn("proposal.actor_ai_user_id = a.ai_user_id", scope)
        self.assertIn("proposal.source_ai_decision_id IS NOT NULL", scope)
        self.assertIn("proposal.proposal_status IN ('pending', 'confirmed')", scope)
        self.assertIn(
            "proposal.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'",
            scope,
        )
        self.assertIn(
            "position.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'",
            scope,
        )

    def test_quote_save_accepts_ai_but_remains_scope_authorized(self) -> None:
        save = _function(self.migration, "n6_quote_writer_save_run")
        self.assertIn(
            "p_principal_type NOT IN ('admin', 'human_user', 'ai_user')",
            save,
        )
        self.assertIn(
            "FROM public.n6_quote_writer_scope(p_quote_minute) allowed",
            save,
        )
        self.assertIn("051 quote payload outside authorized scope", save)
        self.assertIn("item_value->>'exchange' = 'BJ'", save)
        self.assertIn("'unsupported_exchange'", save)
        self.assertIn("p_completed_at >= p_quote_minute + interval '75 seconds'", save)

    def test_stop_evaluator_resolves_exactly_one_human_or_ai_actor(self) -> None:
        stop = _function(self.migration, "n6_executor_evaluate_next_stop_loss")
        self.assertIn("principal.principal_type IN ('admin', 'human_user')", stop)
        self.assertIn("principal.principal_type = 'ai_user'", stop)
        self.assertIn("principal.owner_user_id IS NULL", stop)
        self.assertIn("ai.status = 'active'", stop)
        self.assertIn("actor_ai_user_id bigint;", stop)
        self.assertIn("position_row.principal_type = 'ai_user'", stop)
        self.assertIn("actor_ai_user_id, NULL, position_row.virtual_account_id", stop)
        self.assertIn("'principal_actor_not_ready'", stop)
        self.assertIn("'stop_loss', source_key", stop)
        self.assertIn("first_quote.current_price > position_row.stop_loss_price", stop)
        self.assertIn("confirm_quote.current_price > position_row.stop_loss_price", stop)
        self.assertIn("available_trade_date <= current_trade_date", stop)
        self.assertIn("confirm_quote.exchange NOT IN ('SH', 'SZ')", stop)

    def test_freeze_function_remains_generic_and_unreplaced(self) -> None:
        self.assertNotIn(
            "CREATE OR REPLACE FUNCTION public.n6_executor_freeze_next_stop_loss",
            self.migration,
        )
        freeze = _function(self.stop_049, "n6_executor_freeze_next_stop_loss")
        self.assertIn("FROM public.n6_virtual_position p", freeze)
        self.assertNotIn("owner_user_id IS NOT NULL", freeze)
        self.assertIn("p.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'", freeze)

    def test_executor_rechecks_ai_risk_before_account_fact_dml(self) -> None:
        executor = _function(
            self.migration, "n6_executor_apply_claimed_proposal"
        )
        risk_index = executor.index("public.n6_ai_executor_risk_recheck(")
        first_account_dml = min(
            executor.index("INSERT INTO public.n6_virtual_order"),
            executor.index("INSERT INTO public.n6_virtual_trade"),
            executor.index("INSERT INTO public.n6_virtual_cash_ledger"),
            executor.index("UPDATE public.n6_virtual_cash_snapshot"),
            executor.index("INSERT INTO public.n6_virtual_position"),
        )
        self.assertLess(risk_index, first_account_dml)
        self.assertIn("ai_risk_result->>'ok' <> 'true'", executor)
        self.assertIn("ai_risk_result->>'status' <> 'passed'", executor)
        self.assertIn("'ai_risk_recheck_failed_closed'", executor)
        self.assertIn("'account_writes', 0", executor)
        self.assertIn("proposal.source_type IN ('signal', 'ai_risk')", executor)
        self.assertIn(
            "proposal.source_type IN ('manual_position', 'stop_loss', 'ai_risk')",
            executor,
        )
        self.assertIn("proposal.source_type = 'stop_loss'", executor)
        self.assertIn("proposal.source_type = 'ai_risk'", executor)
        self.assertIn("proposal.user_id IS NOT NULL", executor)
        self.assertIn("proposal.actor_ai_user_id IS NULL", executor)
        self.assertIn("proposal.source_ai_decision_id IS NULL", executor)

    def test_executor_preserves_quote_t1_and_human_rules(self) -> None:
        executor = _function(
            self.migration, "n6_executor_apply_claimed_proposal"
        )
        self.assertIn("proposal.principal_type NOT IN ('admin', 'human_user')", executor)
        self.assertIn("proposal.source_type = 'ai_risk'", executor)
        self.assertIn("proposal.identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'", executor)
        self.assertIn("quote.exchange NOT IN ('SH', 'SZ')", executor)
        self.assertIn(
            "quote.quote_minute < pg_catalog.clock_timestamp() - interval '2 minutes'",
            executor,
        )
        self.assertIn("available_trade_date <= trade_date_date", executor)
        self.assertIn("fill_quantity < 100", executor)
        self.assertIn("LEAST(300000::numeric, cash_before.available_cash)", executor)
        self.assertIn("'a_share_t_plus_1_virtual_v1'", executor)
        self.assertIn("'n6_046_zero_fee_v1'", executor)

    def test_acl_keeps_account_writes_executor_only(self) -> None:
        for function_name, expected_role in (
            ("n6_quote_writer_scope(timestamptz)", "n6_quote_writer"),
            (
                "n6_quote_writer_save_run(\n"
                "  bigint,text,timestamptz,text,integer,integer,integer,\n"
                "  timestamptz,timestamptz,jsonb,jsonb\n"
                ")",
                "n6_quote_writer",
            ),
            (
                "n6_executor_evaluate_next_stop_loss(text)",
                "n6_virtual_executor",
            ),
            (
                "n6_executor_apply_claimed_proposal(bigint,text)",
                "n6_virtual_executor",
            ),
        ):
            grant_pattern = (
                rf"GRANT EXECUTE ON FUNCTION public\.{re.escape(function_name)}"
                rf"\s+TO {re.escape(expected_role)};"
            )
            self.assertRegex(self.migration, grant_pattern)
        self.assertNotRegex(
            self.migration,
            r"GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE|TRUNCATE|REFERENCES|TRIGGER)"
            r"\s+ON\s+(?:TABLE\s+)?public\.",
        )
        self.assertNotRegex(
            self.migration,
            r"GRANT\s+(?:USAGE|SELECT|UPDATE)\s+ON\s+SEQUENCE",
        )
        self.assertNotRegex(
            self.migration,
            r"GRANT EXECUTE ON FUNCTION public\.n6_executor_"
            r".*?\bTO n6_ai_agent\b",
        )

    def test_no_upstream_raw_source_or_real_trade_boundary(self) -> None:
        lowered = self.migration.lower()
        for forbidden in (
            "common_event_outbox",
            "condition_basis",
            "condition_pool",
            "minute_target_scope",
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "broker_session",
            "real_trade",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_rollback_restores_published_051_and_049_definitions(self) -> None:
        self.assertEqual(
            _function(self.rollback, "n6_quote_writer_scope"),
            _function(self.quote_051, "n6_quote_writer_scope"),
        )
        self.assertEqual(
            _function(self.rollback, "n6_quote_writer_save_run"),
            _function(self.quote_051, "n6_quote_writer_save_run"),
        )
        self.assertEqual(
            _function(self.rollback, "n6_executor_evaluate_next_stop_loss"),
            _function(self.stop_049, "n6_executor_evaluate_next_stop_loss"),
        )
        self.assertEqual(
            _function(self.rollback, "n6_executor_apply_claimed_proposal"),
            _function(self.stop_049, "n6_executor_apply_claimed_proposal"),
        )
        self.assertNotIn("DELETE FROM", self.rollback)
        self.assertNotIn("DROP TABLE", self.rollback)
        self.assertNotIn("DROP FUNCTION", self.rollback)
        self.assertIn("active AI proposal exists", self.rollback)
        self.assertIn("open AI position requires stop protection", self.rollback)


if __name__ == "__main__":
    unittest.main()
