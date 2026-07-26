"""Static and boundary contract tests for N6 migration 066."""

from datetime import time
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD = (
    ROOT / "sql/066_n6_btrack_regular_session_manual_buy.sql"
).read_text(encoding="utf-8")
ROLLBACK = (
    ROOT / "sql/066_n6_btrack_regular_session_manual_buy_rollback.sql"
).read_text(encoding="utf-8")
BASE_064 = (
    ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql"
).read_text(encoding="utf-8")
BASE_065A = (
    ROOT / "sql/065a_n6_btrack_confirmed_manual_buy_claim_scope_fix.sql"
).read_text(encoding="utf-8")
CONTRACT = json.loads(
    (
        ROOT
        / "docs/N6_B_TRACK_REGULAR_SESSION_MANUAL_BUY_066_CONTRACT.json"
    ).read_text(encoding="utf-8")
)


def _dollar_block(sql: str, label: str) -> str:
    match = re.search(
        rf"\${re.escape(label)}\$(.*?)\${re.escape(label)}\$",
        sql,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing dollar block: {label}")
    return match.group(1)


def _regular_session_open(local_time: time) -> bool:
    return (
        time(9, 30) <= local_time <= time(11, 30)
        or time(13, 0) <= local_time <= time(15, 0)
    )


class N6066RegularSessionManualBuyTest(unittest.TestCase):
    def test_exact_session_boundaries(self) -> None:
        cases = {
            time(9, 29): False,
            time(9, 30): True,
            time(11, 30): True,
            time(11, 31): False,
            time(12, 59): False,
            time(13, 0): True,
            time(15, 0): True,
            time(15, 1): False,
            time(23, 59): False,
        }
        self.assertEqual(
            {
                local_time: _regular_session_open(local_time)
                for local_time in cases
            },
            cases,
        )
        self.assertIn("calendar.is_open = true", FORWARD)
        self.assertIn(
            "BETWEEN time '09:30:00' AND time '11:30:00'", FORWARD
        )
        self.assertIn(
            "BETWEEN time '13:00:00' AND time '15:00:00'", FORWARD
        )

    def test_create_confirm_claim_and_apply_share_one_gate(self) -> None:
        for label in (
            "create_session_066",
            "confirm_session_066",
            "claim_explicit_066",
            "claim_next_066",
            "apply_session_066",
        ):
            self.assertIn(
                "n6_btrack_regular_trade_session_open",
                _dollar_block(FORWARD, label),
                label,
            )
        self.assertIn("'error', 'outside_trading_session'", FORWARD)
        self.assertIn("'status', 'trade_session_not_ready'", FORWARD)

    def test_manual_buy_fill_requires_fresh_valid_quote(self) -> None:
        new_fill = _dollar_block(FORWARD, "manual_fill_066")
        old_fill = _dollar_block(FORWARD, "manual_fill_065b")
        self.assertIn("'status', 'quote_not_ready'", new_fill)
        self.assertIn("quote.current_price::numeric(24,6)", new_fill)
        self.assertIn("n6_066_fresh_quote_fill_v1", new_fill)
        for forbidden in (
            "same_day_last_quote_current_price",
            "n6_064_same_day_last_quote_fill_v1",
            "fill_price_source := 'signal_reference_price'",
            "n6_064_signal_reference_fill_v1",
        ):
            self.assertNotIn(forbidden, new_fill)
            self.assertIn(forbidden, old_fill)
        for required in (
            "candidate.quality_status = 'passed'",
            "candidate.quality_reason = 'ok'",
            "candidate.exchange =",
            "clock_timestamp() - interval '2 minutes'",
            "candidate.current_price > 0",
            "'NaN', 'Infinity', '-Infinity'",
        ):
            self.assertIn(required, BASE_064)

    def test_policy_scope_and_target_price_contract_are_preserved(self) -> None:
        self.assertIn(
            "n6_btrack_regular_session_manual_buy_066_v1", FORWARD
        )
        self.assertIn(
            "n6_btrack_current_date_batch_scope_fix_065_v1", ROLLBACK
        )
        self.assertIn(
            "n6_btrack_manual_signal_buy_current_scope", BASE_065A
        )
        self.assertEqual(
            CONTRACT["manual_signal_buy"]["action_states"],
            ["eligible", "executed"],
        )
        self.assertFalse(
            CONTRACT["manual_signal_buy"]["same_day_last_quote_fallback"]
        )
        self.assertFalse(
            CONTRACT["manual_signal_buy"][
                "signal_reference_price_fill_fallback"
            ]
        )
        self.assertIn(
            "missing target price opens with target_price_status=not_ready",
            CONTRACT["preserved_rules"],
        )

    def test_stop_loss_and_existing_business_rows_are_untouched(self) -> None:
        self.assertFalse(CONTRACT["stop_loss"]["changed"])
        self.assertEqual(
            CONTRACT["stop_loss"]["first_day_day_low_quote_window"],
            "14:55:00-15:05:00",
        )
        self.assertFalse(
            CONTRACT["existing_positions"]["historical_rows_rewritten"]
        )
        for sql in (FORWARD, ROLLBACK):
            self.assertNotIn(
                "INSERT INTO public.n6_virtual_trade_proposal", sql
            )
            self.assertNotIn("DELETE FROM public.n6_virtual_", sql)
            self.assertNotIn("TRUNCATE ", sql)
        self.assertNotIn("day_low", FORWARD)

    def test_forward_and_rollback_pin_hashes_owner_security_and_acl(self) -> None:
        forward_hashes = {
            "6c43e9c2426867d8d31d0827de83147893395ae923bb1b1bf83ea4b81654fd10",
            "2857c7437c45f0b280f60d0f577d835529185d0be6e24a67bbc9ab6ff51f9f06",
            "3ba1cc351e64e8ae6aebafdb33f577f4cc7bd2a97d46c31203893994503f75cf",
            "4768dbe91a2902fcfc372b72efcb736dd3bb073106c9fe0af45f5fcc6b9aa934",
            "d9cfbc4e07efce566e40fc642c60ef8ef5720aa2ca2aab942c3d0f4151c76366",
            "316ed7080aea0f343a7231b338a82f95fbec05755743bb46948583d9c93cac76",
        }
        rollback_hashes = {
            "56e9979559eaec73bab459cd5fb6b3affa897067f7e40d08787e81701c90a47d",
            "696ad75b2874710d30ecdd3e9ebf2ac7354d9b3698e31e698dbcc51a06d3bee4",
            "a7c2b375cbea5546a699829a3605d0a83c5a92df3e32279bec876320ce968f20",
            "45c8405c9d0d5d9daa4812234c5113fb9a4544430975578f54699e21c10e2eaa",
            "6e9a42f48d2dafa42c2b7a59de667f75c16acdd5b31b0e318c7fd84f73b3e98a",
        }
        for source_sha in forward_hashes:
            self.assertIn(source_sha, FORWARD + ROLLBACK)
        for source_sha in rollback_hashes:
            self.assertIn(source_sha, FORWARD + ROLLBACK)
        for sql in (FORWARD, ROLLBACK):
            self.assertIn("SECURITY DEFINER", sql)
            self.assertIn("SET search_path=pg_catalog", sql)
            self.assertIn("TO n6_btrack_web", sql)
            self.assertIn("TO n6_virtual_executor", sql)
            self.assertIn("postflight_acl_drift", sql)


if __name__ == "__main__":
    unittest.main()
