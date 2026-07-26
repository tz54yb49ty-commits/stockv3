from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/056_n6_ai_agent_v1_identity_account_seed.sql"
ROLLBACK = ROOT / "sql/056_n6_ai_agent_v1_identity_account_seed_rollback.sql"


class N6AiAgentIdentitySeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_seed_is_ai_only_and_paper_only(self) -> None:
        self.assertIn("u.user_id = 1", self.migration)
        self.assertIn("u.role = 'admin'", self.migration)
        self.assertIn("u.status = 'active'", self.migration)
        self.assertIn("'ai_user'", self.migration)
        self.assertIn("'sandbox_only'", self.migration)
        self.assertIn("'paper_only', true", self.migration)
        self.assertIn("'real_trade_enabled', false", self.migration)
        self.assertIn("100000000.0000", self.migration)
        self.assertNotIn("INSERT INTO public.n6_virtual_order", self.migration)
        self.assertNotIn("INSERT INTO public.n6_virtual_trade", self.migration)
        self.assertNotIn("INSERT INTO public.n6_virtual_position", self.migration)

    def test_seed_freezes_conservative_policy(self) -> None:
        for fragment in (
            "'buy_budget_cny', 300000",
            "'max_identity_exposure_cny', 600000",
            "'max_gross_exposure_pct', 10",
            "'max_daily_new_buys', 10",
            "'autonomous_canary_daily_buys', 1",
            "'drawdown_pause_pct', 5",
        ):
            self.assertIn(fragment, self.migration)

    def test_seed_is_transactional_and_idempotent(self) -> None:
        self.assertTrue(self.migration.startswith("-- N6 AI Agent"))
        self.assertEqual(self.migration.count("\nBEGIN;\n"), 1)
        self.assertEqual(self.migration.count("\nCOMMIT;\n"), 1)
        self.assertIn("marker_principal_count = 1 AND complete_count = 1", self.migration)
        self.assertIn("partial or drifted seed state rejected", self.migration)

    def test_exact_seed_return_requires_global_ai_uniqueness(self) -> None:
        for counter in (
            "active_ai_principal_count",
            "active_ai_user_count",
            "active_ai_strategy_count",
            "active_ai_account_count",
        ):
            self.assertIn(counter, self.migration)
            self.assertLess(
                self.migration.index(f"INTO {counter}"),
                self.migration.index(
                    "IF marker_principal_count = 1 AND complete_count = 1"
                ),
            )
        uniqueness_check = self.migration.index(
            "IF active_ai_principal_count <> 1"
        )
        exact_seed_return = self.migration.index(
            "IF marker_principal_count = 1 AND complete_count = 1"
        )
        return_statement = self.migration.index(
            "    RETURN;",
            exact_seed_return,
        )
        self.assertLess(exact_seed_return, uniqueness_check)
        self.assertLess(uniqueness_check, return_statement)
        self.assertIn(
            "056 exact seed is not the unique active AI",
            self.migration,
        )

    def test_rollback_preserves_business_history(self) -> None:
        for relation in (
            "n6_virtual_trade_proposal",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_position_event",
            "n6_virtual_position_lot",
            "n6_virtual_pnl_snapshot",
            "n6_virtual_quote_run",
            "n6_ai_context_snapshot",
            "n6_ai_decision_run",
            "n6_ai_decision",
            "n6_ai_daily_summary",
            "n6_ai_strategy_evaluation",
        ):
            self.assertIn(f"SELECT 1 FROM public.{relation}", self.rollback)
        self.assertIn("rollback blocked by preserved AI business history", self.rollback)
        self.assertNotIn("DELETE FROM public.n6_virtual_trade_proposal", self.rollback)
        self.assertNotIn("DELETE FROM public.n6_virtual_order", self.rollback)
        self.assertNotIn("DELETE FROM public.n6_virtual_trade\n", self.rollback)
        self.assertNotIn("DELETE FROM public.n6_virtual_position\n", self.rollback)

    def test_rollback_explicitly_blocks_seed_adjacent_history(self) -> None:
        expected_blockers = {
            "principal_mapping_count": (
                "public.n6_principal_account",
                "extra or missing principal-account mappings",
            ),
            "principal_strategy_count": (
                "public.n6_strategy",
                "extra or missing target-principal strategies",
            ),
            "principal_account_count": (
                "public.n6_virtual_account",
                "extra or missing target-principal accounts",
            ),
            "account_ledger_count": (
                "public.n6_virtual_cash_ledger",
                "extra or missing cash ledger history",
            ),
            "account_snapshot_count": (
                "public.n6_virtual_cash_snapshot",
                "extra or missing cash snapshot history",
            ),
        }
        first_delete = self.rollback.index(
            "DELETE FROM public.n6_principal_account"
        )
        for counter, (relation, message) in expected_blockers.items():
            self.assertIn(f"INTO {counter}", self.rollback)
            self.assertIn(f"FROM {relation}", self.rollback)
            self.assertIn(message, self.rollback)
            self.assertLess(self.rollback.index(f"INTO {counter}"), first_delete)

    def test_seed_does_not_touch_upstream_or_real_trade(self) -> None:
        combined = (self.migration + self.rollback).lower()
        for forbidden in (
            "condition_basis",
            "condition_pool",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_checkpoint",
        ):
            self.assertIsNone(
                re.search(
                    rf"\b(?:insert\s+into|update|delete\s+from)\s+"
                    rf"(?:public\.)?{re.escape(forbidden)}\b",
                    combined,
                )
            )


if __name__ == "__main__":
    unittest.main()
