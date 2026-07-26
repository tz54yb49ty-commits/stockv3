"""Static contract tests for N6 migration 065A."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD = (
    ROOT / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql"
).read_text(encoding="utf-8")
ROLLBACK = (
    ROOT
    / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix_rollback.sql"
).read_text(encoding="utf-8")


class N6065AConfirmedManualBuyClaimScopeFixTest(unittest.TestCase):
    def test_forward_is_narrow_and_preserves_expiry_default(self) -> None:
        for required in (
            "p.expires_at > pg_catalog.now()",
            "expires_at>pg_catalog.now()",
            "principal_type IN ('admin','human_user')",
            "p.principal_type IN ('admin', 'human_user')",
            "source_type='signal'",
            "p.source_type = 'signal'",
            "proposal_side='buy'",
            "p.proposal_side = 'buy'",
            "actor_ai_user_id IS NULL",
            "source_ai_decision_id IS NULL",
            "n6_btrack_manual_signal_buy_current_scope",
        ):
            self.assertIn(required, FORWARD)
        self.assertNotIn(
            "UPDATE public.n6_virtual_trade_proposal SET", FORWARD
        )

    def test_forward_and_rollback_pin_exact_function_hashes(self) -> None:
        for source_sha in (
            "fc3bed9cb3f66dfe722e8869062100d62843542bc77828ccc8c581b0e37f00f0",
            "77db38fea32888e5ec4c81698858409171ed319c0fb292aa12dd5b4f0c7c9c2e",
            "a7c2b375cbea5546a699829a3605d0a83c5a92df3e32279bec876320ce968f20",
            "45c8405c9d0d5d9daa4812234c5113fb9a4544430975578f54699e21c10e2eaa",
        ):
            self.assertIn(source_sha, FORWARD + ROLLBACK)
        self.assertIn("SECURITY DEFINER", FORWARD)
        self.assertIn("SET search_path=pg_catalog", FORWARD)
        self.assertIn("TO n6_virtual_executor", FORWARD)
        self.assertIn("TO n6_virtual_executor", ROLLBACK)

    def test_rollback_restores_expiry_only_predicates(self) -> None:
        self.assertIn(
            "proposal_status='confirmed' AND expires_at>pg_catalog.now()",
            ROLLBACK,
        )
        self.assertIn(
            "p.proposal_status = 'confirmed'\n"
            "      AND p.expires_at > pg_catalog.now()",
            ROLLBACK,
        )


if __name__ == "__main__":
    unittest.main()
