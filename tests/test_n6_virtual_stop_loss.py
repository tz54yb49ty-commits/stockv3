from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import unittest

from ashare_v3.user.virtual_stop_loss import (
    DISPLAY_TIMEZONE,
    adjacent_pair,
    finite_positive,
    first_ready_candidate,
    freeze_candidate,
    matured_lot_quantity,
    valid_runtime_quote,
)


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "sql/049_n6_virtual_stop_loss_freeze_evaluate_execute.sql").read_text()


def quote(minute: datetime, price="9.9", *, snapshot_id=1, fetched_at=None, **overrides):
    row = {
        "virtual_quote_snapshot_id": snapshot_id,
        "identity_key": "stock:SH:600000",
        "exchange": "SH",
        "quote_minute": minute,
        "fetched_at": fetched_at or minute,
        "current_price": price,
        "day_low": "9.8",
        "quality_status": "passed",
        "quality_reason": "ok",
    }
    row.update(overrides)
    return row


class VirtualStopLossPolicyTest(unittest.TestCase):
    def test_finite_positive_rejects_nonfinite_and_nonpositive(self):
        self.assertEqual(finite_positive("1.25"), Decimal("1.25"))
        for value in (None, True, 0, -1, "NaN", "Infinity", "-Infinity"):
            self.assertIsNone(finite_positive(value))

    def test_freeze_uses_last_provider_window_quote_and_allows_late_fetch(self):
        first_day = date(2026, 7, 17)
        rows = [
            quote(datetime(2026, 7, 17, 14, 55, tzinfo=DISPLAY_TIMEZONE), snapshot_id=1),
            quote(
                datetime(2026, 7, 17, 15, 5, tzinfo=DISPLAY_TIMEZONE),
                snapshot_id=2,
                fetched_at=datetime(2026, 7, 17, 15, 8, tzinfo=DISPLAY_TIMEZONE),
                day_low="9.5",
            ),
        ]
        self.assertEqual(
            freeze_candidate(rows, identity_key="stock:SH:600000", first_open_date=first_day),
            ("frozen", Decimal("9.5"), 2),
        )

    def test_freeze_missing_or_wrong_scope_is_retryable_not_ready(self):
        first_day = date(2026, 7, 17)
        wrong = quote(
            datetime(2026, 7, 17, 15, 0, tzinfo=DISPLAY_TIMEZONE),
            identity_key="stock:BJ:430001", exchange="BJ",
        )
        self.assertEqual(
            freeze_candidate([wrong], identity_key="stock:SH:600000", first_open_date=first_day)[0],
            "not_ready",
        )
        cross_day_fetch = quote(
            datetime(2026, 7, 17, 15, 0, tzinfo=DISPLAY_TIMEZONE),
            fetched_at=datetime(2026, 7, 18, 9, 0, tzinfo=DISPLAY_TIMEZONE),
        )
        self.assertEqual(
            freeze_candidate([cross_day_fetch], identity_key="stock:SH:600000",
                             first_open_date=first_day)[0],
            "not_ready",
        )
        self.assertIn(
            "(q.fetched_at AT TIME ZONE 'Asia/Shanghai')::date =\n        position_row.first_open_trade_date",
            SQL,
        )

    def test_runtime_quote_requires_dual_freshness_and_clock_order(self):
        now = datetime(2026, 7, 17, 10, 2, tzinfo=DISPLAY_TIMEZONE)
        minute = now - timedelta(minutes=1)
        self.assertTrue(valid_runtime_quote(quote(minute), identity_key="stock:SH:600000", now=now)[0])
        for bad in (
            quote(minute, fetched_at=minute - timedelta(seconds=1)),
            quote(now - timedelta(seconds=121)),
            quote(now + timedelta(seconds=1)),
            quote(minute, quality_status="not_ready", quality_reason="missing"),
            quote(minute, exchange="BJ"),
        ):
            self.assertFalse(valid_runtime_quote(bad, identity_key="stock:SH:600000", now=now)[0])

    def test_adjacent_breach_rejects_spike_gap_and_rebound(self):
        now = datetime(2026, 7, 17, 10, 2, tzinfo=DISPLAY_TIMEZONE)
        q1 = quote(now - timedelta(minutes=1), "10", snapshot_id=1)
        q2 = quote(now, "9.9", snapshot_id=2)
        self.assertEqual(adjacent_pair([q1, q2], identity_key=q1["identity_key"],
                                       stop_loss_price="10", now=now,
                                       relation="at_or_below"), (1, 2))
        self.assertIsNone(adjacent_pair([q1], identity_key=q1["identity_key"],
                                        stop_loss_price="10", now=now,
                                        relation="at_or_below"))
        self.assertIsNone(adjacent_pair([q1, quote(now, "10.1", snapshot_id=3)],
                                        identity_key=q1["identity_key"], stop_loss_price="10",
                                        now=now, relation="at_or_below"))
        self.assertIsNone(adjacent_pair([quote(now - timedelta(minutes=2), snapshot_id=4), q2],
                                        identity_key=q1["identity_key"], stop_loss_price="10",
                                        now=now, relation="at_or_below"))
        earlier_breach = [
            quote(now - timedelta(minutes=2), "9.8", snapshot_id=5),
            quote(now - timedelta(minutes=1), "9.9", snapshot_id=6),
            quote(now, "10.1", snapshot_id=7),
        ]
        self.assertIsNone(adjacent_pair(earlier_breach, identity_key=q1["identity_key"],
                                        stop_loss_price="10", now=now,
                                        relation="at_or_below"))
        same_minute_rebound = earlier_breach + [quote(now, "9.9", snapshot_id=8)]
        self.assertEqual(adjacent_pair(same_minute_rebound, identity_key=q1["identity_key"],
                                       stop_loss_price="10", now=now,
                                       relation="at_or_below"), (6, 8))

    def test_t1_lots_require_exact_scope_episode_and_maturity(self):
        scope = {"virtual_position_id": 7, "virtual_account_id": 8, "principal_id": 9,
                 "principal_type": "human_user", "identity_key": "stock:SH:600000",
                 "holding_episode_no": 2}
        base = {**scope, "remaining_quantity": "100", "available_trade_date": date(2026, 7, 17),
                "lot_status": "locked_t1"}
        lots = [base, {**base, "holding_episode_no": 1},
                {**base, "available_trade_date": date(2026, 7, 18)},
                {**base, "lot_status": "closed"}]
        self.assertEqual(matured_lot_quantity(lots, scope=scope,
                                               current_trade_date=date(2026, 7, 17)), Decimal("100"))

    def test_sql_locks_lots_before_aggregate_and_rearms_after_terminal_update(self):
        self.assertIn("WITH locked_lots AS (", SQL)
        self.assertIn("SELECT l.remaining_quantity", SQL)
        self.assertIn("FOR UPDATE\n  )\n  SELECT pg_catalog.sum", SQL)
        self.assertNotIn("terminal_proposal.created_at", SQL)
        self.assertIn("r1.quote_minute > terminal_proposal.updated_at", SQL)
        self.assertIn("ORDER BY p.updated_at DESC, p.proposal_id DESC", SQL)
        self.assertIn("ORDER BY last_terminal.updated_at DESC, last_terminal.proposal_id DESC", SQL)
        self.assertIn("r1.fetched_at >= r1.quote_minute", SQL)
        self.assertIn("r1.fetched_at <= r1.quote_minute + interval '120 seconds'", SQL)
        for required in (
            "(r1.quote_minute AT TIME ZONE 'Asia/Shanghai')::date = current_trade_date",
            "r1.quote_minute <= pg_catalog.clock_timestamp()",
            "r1.fetched_at <= pg_catalog.clock_timestamp()",
            "r2.quote_minute < first_quote.quote_minute",
        ):
            self.assertIn(required, SQL)

    def test_candidate_and_detail_terminal_scope_are_exact(self):
        scope = {
            "source_type": "stop_loss",
            "proposal_side": "sell",
            "principal_id": 9,
            "principal_type": "human_user",
            "virtual_account_id": 8,
            "identity_key": "stock:SH:600000",
            "source_virtual_position_id": 7,
            "holding_episode_no": 2,
        }
        current = {
            **scope, "proposal_id": 10, "proposal_status": "failed",
            "updated_at": datetime(2026, 7, 17, 10, 0, tzinfo=DISPLAY_TIMEZONE),
        }
        wrong_rows = []
        for field, value in (
            ("principal_id", 99),
            ("principal_type", "admin"),
            ("virtual_account_id", 88),
            ("identity_key", "stock:SZ:000001"),
            ("proposal_side", "buy"),
        ):
            wrong_rows.append({
                **current, field: value, "proposal_id": current["proposal_id"] + len(wrong_rows) + 1,
                "updated_at": current["updated_at"] + timedelta(minutes=len(wrong_rows) + 1),
            })

        def latest_exact_terminal(rows):
            terminal_statuses = {"expired", "rejected", "failed"}
            matched = [
                row for row in rows
                if all(row.get(key) == value for key, value in scope.items())
                and row.get("proposal_status") in terminal_statuses
            ]
            return max(matched, key=lambda row: (row["updated_at"], row["proposal_id"]))

        self.assertEqual(latest_exact_terminal([current, *wrong_rows])["proposal_id"], 10)

        candidate = SQL.split("AND (\n      NOT EXISTS (", 1)[1].split(
            "ORDER BY p.virtual_position_id", 1
        )[0]
        detail = SQL.split("SELECT p.* INTO terminal_proposal", 1)[1].split(
            "FOR UPDATE;", 1
        )[0]
        for alias in ("terminal", "last_terminal"):
            for predicate in (
                f"{alias}.source_type = 'stop_loss'",
                f"{alias}.proposal_side = 'sell'",
                f"{alias}.principal_id = p.principal_id",
                f"{alias}.principal_type = p.principal_type",
                f"{alias}.virtual_account_id = p.virtual_account_id",
                f"{alias}.identity_key = p.identity_key",
                f"{alias}.source_virtual_position_id = p.virtual_position_id",
                f"{alias}.holding_episode_no = p.holding_episode_no",
                f"{alias}.proposal_status IN ('expired', 'rejected', 'failed')",
            ):
                self.assertIn(predicate, candidate)
        self.assertIn(
            "ORDER BY last_terminal.updated_at DESC, last_terminal.proposal_id DESC",
            candidate,
        )
        for predicate in (
            "p.source_type = 'stop_loss'",
            "p.proposal_side = 'sell'",
            "p.principal_id = position_row.principal_id",
            "p.principal_type = position_row.principal_type",
            "p.virtual_account_id = position_row.virtual_account_id",
            "p.identity_key = position_row.identity_key",
            "p.source_virtual_position_id = position_row.virtual_position_id",
            "p.holding_episode_no = position_row.holding_episode_no",
            "p.proposal_status IN ('expired', 'rejected', 'failed')",
            "ORDER BY p.updated_at DESC, p.proposal_id DESC",
        ):
            self.assertIn(predicate, detail)

    def test_not_ready_position_does_not_starve_ready_freeze_or_evaluate(self):
        positions = [{"id": 1, "freeze_ready": False, "evaluate_ready": False},
                     {"id": 2, "freeze_ready": True, "evaluate_ready": True}]
        self.assertEqual(first_ready_candidate(positions, lambda p: p["freeze_ready"])["id"], 2)
        self.assertEqual(first_ready_candidate(positions, lambda p: p["evaluate_ready"])["id"], 2)
        freeze_select = SQL.split("SELECT p.* INTO position_row", 1)[1].split("FOR UPDATE SKIP LOCKED", 1)[0]
        evaluate_select = SQL.split("SELECT p.* INTO position_row", 2)[2].split("FOR UPDATE SKIP LOCKED", 1)[0]
        self.assertIn("EXISTS (\n      SELECT 1 FROM public.n6_virtual_quote_snapshot q", freeze_select)
        self.assertIn("EXISTS (\n      SELECT 1 FROM public.n6_virtual_position_lot l", evaluate_select)
        self.assertIn("AND EXISTS (\n      SELECT 1\n      FROM public.n6_virtual_quote_snapshot q2", evaluate_select)

    def test_sql_confirmed_proposal_and_episode_blocks_are_deterministic(self):
        self.assertIn("'confirmed',", SQL)
        self.assertIn("confirmed_at,", SQL)
        self.assertIn("confirm_idempotency_key", SQL)
        self.assertIn("position_row.virtual_position_id || ':' ||", SQL)
        self.assertIn("'pending', 'confirmed', 'processing', 'executed'", SQL)
        self.assertIn("ON CONFLICT DO NOTHING", SQL)


if __name__ == "__main__":
    unittest.main()
