"""Static contract tests for N6 migration 065B."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD = (
    ROOT / "sql/065b_n6_btrack_confirmed_manual_buy_apply_scope_fix.sql"
).read_text(encoding="utf-8")
ROLLBACK = (
    ROOT
    / "sql/065b_n6_btrack_confirmed_manual_buy_apply_scope_fix_rollback.sql"
).read_text(encoding="utf-8")


class N6065BConfirmedManualBuyApplyScopeFixTest(unittest.TestCase):
    def test_apply_exception_is_current_scope_manual_buy_only(self) -> None:
        for required in (
            "proposal.expires_at <= pg_catalog.clock_timestamp()",
            "AND NOT (",
            "proposal.principal_type IN ('admin', 'human_user')",
            "proposal.actor_ai_user_id IS NULL",
            "proposal.source_ai_decision_id IS NULL",
            "proposal.source_type = 'signal'",
            "proposal.proposal_side = 'buy'",
            "n6_btrack_manual_signal_buy_current_scope",
        ):
            self.assertIn(required, FORWARD)
        self.assertNotIn(
            "UPDATE public.n6_virtual_trade_proposal SET", FORWARD
        )

    def test_exact_roundtrip_hashes_and_executor_only_acl(self) -> None:
        for source_sha in (
            "2229ac23d823d0f27a08ba7aae18ca682594bfc27515b7a3b10b2a5673023a17",
            "6e9a42f48d2dafa42c2b7a59de667f75c16acdd5b31b0e318c7fd84f73b3e98a",
        ):
            self.assertIn(source_sha, FORWARD + ROLLBACK)
        self.assertIn("TO n6_virtual_executor", FORWARD)
        self.assertIn("TO n6_virtual_executor", ROLLBACK)
        self.assertIn("SET search_path=pg_catalog", FORWARD)


if __name__ == "__main__":
    unittest.main()
