from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import unittest

from ashare_v3.user.virtual_account_v3 import (
    DEFAULT_VIRTUAL_ACCOUNT_INITIAL_CASH,
    DISPLAY_TIMEZONE,
    calculate_default_buy_quantity,
    evaluate_confirmed_proposal,
    freeze_first_day_stop_loss,
    two_adjacent_minute_stop_breach,
    valid_fresh_quote,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 17, 10, 2, tzinfo=DISPLAY_TIMEZONE)


def quote(
    minute: datetime,
    *,
    identity_key: str = "stock:SH:600000",
    price: str = "10",
    day_low: str = "9.5",
    quality_status: str = "passed",
    quality_reason: str = "ok",
    snapshot_id: int = 1,
) -> dict[str, object]:
    return {
        "virtual_quote_snapshot_id": snapshot_id,
        "identity_key": identity_key,
        "exchange": identity_key.split(":")[1],
        "current_price": price,
        "day_low": day_low,
        "quote_minute": minute,
        "fetched_at": minute + timedelta(seconds=15),
        "quality_status": quality_status,
        "quality_reason": quality_reason,
    }


class N6VirtualAccountV3Tests(unittest.TestCase):
    def test_default_buy_uses_300k_budget_and_100_share_lots(self) -> None:
        self.assertEqual(DEFAULT_VIRTUAL_ACCOUNT_INITIAL_CASH, Decimal("100000000"))
        self.assertEqual(
            calculate_default_buy_quantity(available_cash="100000000", current_price="10.23"),
            Decimal("29300"),
        )
        self.assertEqual(
            calculate_default_buy_quantity(available_cash="999", current_price="10"),
            Decimal("0"),
        )

    def test_quote_validation_fails_closed(self) -> None:
        good = quote(NOW - timedelta(minutes=1))
        self.assertEqual(valid_fresh_quote(good, identity_key="stock:SH:600000", now=NOW)[:2], (True, "ready"))
        for changed, requested_identity, expected in (
            ({"identity_key": "stock:SH:600001"}, "stock:SH:600000", "quote_identity_mismatch"),
            ({"identity_key": "stock:BJ:430001", "exchange": "BJ"}, "stock:BJ:430001", "quote_exchange_not_supported"),
            ({"quality_status": "not_ready"}, "stock:SH:600000", "quote_quality_not_passed"),
            ({"current_price": "NaN"}, "stock:SH:600000", "quote_price_invalid"),
            ({"fetched_at": NOW - timedelta(seconds=121)}, "stock:SH:600000", "quote_stale"),
        ):
            candidate = dict(good)
            candidate.update(changed)
            valid, reason, price = valid_fresh_quote(
                candidate,
                identity_key=requested_identity,
                now=NOW,
            )
            self.assertFalse(valid)
            self.assertEqual(reason, expected)
            self.assertIsNone(price)

    def test_confirmed_buy_and_sell_ignore_client_price_and_quantity(self) -> None:
        base = {
            "proposal_status": "confirmed",
            "expires_at": NOW + timedelta(seconds=30),
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
        }
        fresh = quote(NOW - timedelta(minutes=1), price="10")
        buy = evaluate_confirmed_proposal(
            {**base, "proposal_side": "buy", "client_price": "1", "client_quantity": "999999"},
            quote=fresh,
            available_cash="100000000",
            available_quantity="0",
            now=NOW,
        )
        self.assertTrue(buy.ready)
        self.assertEqual((buy.quantity, buy.fill_price), (Decimal("30000"), Decimal("10")))
        sell = evaluate_confirmed_proposal(
            {**base, "proposal_side": "sell"},
            quote=fresh,
            available_cash="0",
            available_quantity="1200",
            now=NOW,
        )
        self.assertTrue(sell.ready)
        self.assertEqual(sell.quantity, Decimal("1200"))

    def test_expired_or_t1_locked_proposal_is_not_executable(self) -> None:
        proposal = {
            "proposal_status": "confirmed",
            "expires_at": NOW + timedelta(seconds=30),
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "proposal_side": "sell",
        }
        locked = evaluate_confirmed_proposal(
            proposal,
            quote=quote(NOW - timedelta(minutes=1)),
            available_cash="0",
            available_quantity="0",
            now=NOW,
        )
        self.assertEqual((locked.ready, locked.reason), (False, "t1_available_quantity_not_sellable"))
        expired = evaluate_confirmed_proposal(
            {**proposal, "expires_at": NOW},
            quote=quote(NOW - timedelta(minutes=1)),
            available_cash="0",
            available_quantity="100",
            now=NOW,
        )
        self.assertEqual((expired.ready, expired.reason), (False, "proposal_expired"))

    def test_stop_loss_requires_same_identity_and_adjacent_minutes(self) -> None:
        first = quote(NOW - timedelta(minutes=2), price="9.5", snapshot_id=1)
        second = quote(NOW - timedelta(minutes=1), price="9.4", snapshot_id=2)
        self.assertTrue(two_adjacent_minute_stop_breach([first, second], stop_loss_price="9.6", now=NOW))
        gap = quote(NOW - timedelta(minutes=4), price="9.5", snapshot_id=3)
        self.assertFalse(two_adjacent_minute_stop_breach([gap, second], stop_loss_price="9.6", now=NOW))
        other = quote(
            NOW - timedelta(minutes=1),
            identity_key="stock:SZ:000001",
            price="9.4",
            snapshot_id=4,
        )
        self.assertFalse(two_adjacent_minute_stop_breach([first, other], stop_loss_price="9.6", now=NOW))

    def test_first_day_stop_freezes_last_valid_close_window_low(self) -> None:
        first = quote(datetime(2026, 7, 17, 14, 56, tzinfo=DISPLAY_TIMEZONE), day_low="9.6", snapshot_id=10)
        latest = quote(datetime(2026, 7, 17, 15, 1, tzinfo=DISPLAY_TIMEZONE), day_low="9.4", snapshot_id=11)
        self.assertEqual(
            freeze_first_day_stop_loss(
                [first, latest],
                identity_key="stock:SH:600000",
                first_open_trade_date="20260717",
            ),
            ("frozen", Decimal("9.4"), 11),
        )
        self.assertEqual(
            freeze_first_day_stop_loss(
                [quote(datetime(2026, 7, 17, 14, 54, tzinfo=DISPLAY_TIMEZONE))],
                identity_key="stock:SH:600000",
                first_open_trade_date="20260717",
            ),
            ("not_ready", None, None),
        )
        unsupported = quote(
            datetime(2026, 7, 17, 15, 1, tzinfo=DISPLAY_TIMEZONE),
            identity_key="stock:BJ:430001",
        )
        self.assertEqual(
            freeze_first_day_stop_loss(
                [unsupported],
                identity_key="stock:BJ:430001",
                first_open_trade_date="20260717",
            ),
            ("not_ready", None, None),
        )
        mismatched = quote(
            datetime(2026, 7, 17, 15, 2, tzinfo=DISPLAY_TIMEZONE),
            identity_key="stock:SZ:000001",
            day_low="1.0",
            snapshot_id=12,
        )
        self.assertEqual(
            freeze_first_day_stop_loss(
                [latest, mismatched],
                identity_key="stock:SH:600000",
                first_open_trade_date="20260717",
            ),
            ("not_ready", None, None),
        )

    def test_schema_is_additive_n6_only_and_rollback_preserves_history(self) -> None:
        schema = (ROOT / "sql/041_n6_b_track_product_v3_schema.sql").read_text()
        rollback = (ROOT / "sql/041_n6_b_track_product_v3_schema_rollback.sql").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS n6_virtual_trade_proposal", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS n6_virtual_position_lot", schema)
        self.assertNotIn("n6_btrack_web", schema)
        self.assertNotIn("n6_virtual_executor", schema)
        self.assertIn("idx_041_n6_virtual_trade_proposal_open", schema)
        self.assertNotIn("GRANT ", schema)
        self.assertNotIn("REVOKE ", schema)
        self.assertIn("041 grants no role privileges", rollback)
        self.assertNotIn("common_event_outbox", schema)
        self.assertNotIn("common_action", schema)
        self.assertNotIn("common_trigger", schema)
        self.assertNotIn("DELETE FROM", rollback)
        self.assertIn("position_v3_count", rollback)
        self.assertIn("rollback blocked", rollback)


if __name__ == "__main__":
    unittest.main()
