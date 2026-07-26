from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from ashare_v3.user.ai_investor_strategy_policy_v1 import (
    KNOWLEDGE_BUNDLE_SHA256,
    KNOWLEDGE_BUNDLE_VERSION,
    POLICY_DOCUMENT_SHA256,
    POLICY_VERSION,
    StrategyPolicyError,
    buy_blocked_by_pending_clear,
    clear_sell_quantity,
    evaluate_pending_clear,
    evaluate_position_strategy,
    hint_channel_adjustment,
    rank_shadow_buy_candidates,
    server_sellable_quantity,
    target_reduce_quantity,
    target_reduction_boundary,
    target_quote_reaches_locked_price,
)


TRADE_DATE = date(2026, 7, 20)
DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")
EVALUATION_TIME = datetime(
    2026, 7, 20, 10, 2, 30, tzinfo=DISPLAY_TIMEZONE
)
POLICY_SHA = (
    "56082554c4f1099c9fa265d80f0233fde7459d2748be4c85f69fc198bddfc9e7"
)


def policy_identity() -> dict[str, str]:
    return {
        "policy_version": POLICY_VERSION,
        "policy_document_sha256": POLICY_DOCUMENT_SHA256,
        "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
        "knowledge_bundle_sha256": KNOWLEDGE_BUNDLE_SHA256,
    }


def membership(
    context_identity_key: str,
    *,
    stock_identity_key: str = "stock:SH:600000",
    asset_kind: str = "index",
    **overrides,
):
    row = {
        "asset_kind": asset_kind,
        "context_identity_key": context_identity_key,
        "stock_identity_key": stock_identity_key,
        "for_trade_date": "20260720",
        "status": "active",
        "quality_status": "passed",
        "source": "approved_n6_membership",
        "membership_ref": f"membership:{context_identity_key}",
        "created_at": "2026-07-20T09:00:00+08:00",
        "source_version": "v1",
    }
    row.update(overrides)
    return row


def hint(
    identity_key: str,
    direction: str,
    *,
    asset_kind: str = "index",
    **overrides,
):
    row = {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "for_trade_date": "20260720",
        "status": "active",
        "quality_status": "passed",
        "source": "approved_n6_context",
        "evidence_ref": f"hint:{identity_key}:{direction}",
        "condition_key": (
            "BUY_HINT:D" if direction == "buy" else "SELL_HINT:D"
        ),
        "original_condition_key": (
            "BUY_HINT" if direction == "buy" else "SELL_HINT"
        ),
        "signal_type": "B_BUY" if direction == "buy" else "S_SELL",
    }
    row.update(overrides)
    return row


def quote(**overrides):
    row = {
        "source": "n3n6q",
        "identity_key": "stock:SH:600000",
        "for_trade_date": "20260720",
        "current_price": "12.50",
        "quality_status": "passed",
        "is_fresh": True,
        "session_status": "trading",
        "quote_minute": "2026-07-20T10:02:00+08:00",
        "fetched_at": "2026-07-20T10:02:10+08:00",
    }
    row.update(overrides)
    return row


def candidate(
    identity_key: str,
    financial_score_raw,
    **overrides,
):
    row = {
        "identity_key": identity_key,
        "financial_score_raw": financial_score_raw,
        "for_trade_date": "20260720",
        "source_layer": "N5_action",
        "direction": "buy",
        "status": "active",
        "quality_status": "passed",
        "ai_eligible": True,
        "source_signal_projection_id": 101,
    }
    row.update(overrides)
    return row


def position(**overrides):
    row = {
        "ai_user_id": 1,
        "strategy_id": 4,
        "virtual_account_id": 7,
        "virtual_position_id": 11,
        "principal_id": 2,
        "principal_type": "ai_user",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "holding_episode_no": 3,
        "episode_status": "open",
        "quantity": 500,
        "available_quantity": 500,
        "locked_quantity": 0,
        "position_status": "open_virtual",
        "quality_status": "passed",
        "locked_target_price": "12.00",
        "target_price_status": "frozen",
        "locked_target_quality_status": "passed",
        "locked_target_source_signal_projection_id": 101,
        "up_sell_reference_period": "M",
        "up_reference_period": "Q",
        "pending_clear": False,
        "policy_version": POLICY_VERSION,
        "policy_hash": POLICY_DOCUMENT_SHA256,
    }
    row.update(overrides)
    return row


def lot(
    lot_id: int,
    quantity: int,
    available_trade_date: str,
    *,
    lot_status: str = "locked_t1",
    **overrides,
):
    row = {
        "virtual_position_lot_id": lot_id,
        "virtual_account_id": 7,
        "virtual_position_id": 11,
        "principal_id": 2,
        "principal_type": "ai_user",
        "identity_key": "stock:SH:600000",
        "holding_episode_no": 3,
        "remaining_quantity": quantity,
        "available_trade_date": available_trade_date,
        "lot_status": lot_status,
    }
    row.update(overrides)
    return row


def sell_message(**overrides):
    row = {
        "source_layer": "N5_action",
        "identity_key": "stock:SH:600000",
        "direction": "sell",
        "for_trade_date": "20260720",
        "status": "active",
        "quality_status": "passed",
        "primary_trigger_period": "M",
        "source_signal_projection_id": 91,
    }
    row.update(overrides)
    return row


class PolicyAuthorityTest(unittest.TestCase):
    def test_policy_document_matches_frozen_authority_hash(self):
        policy_path = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "N6_AI_INVESTOR_STRATEGY_POLICY_V1_DRAFT.md"
        )
        self.assertTrue(policy_path.is_file())
        self.assertEqual(
            hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            POLICY_DOCUMENT_SHA256,
        )


class QuantityPolicyTest(unittest.TestCase):
    def test_target_reduction_examples_and_odd_lots(self):
        self.assertEqual(
            {
                quantity: target_reduce_quantity(quantity)
                for quantity in (100, 200, 300, 600, 1000)
            },
            {100: 100, 200: 100, 300: 100, 600: 200, 1000: 300},
        )
        for quantity in range(1, 100):
            self.assertEqual(target_reduce_quantity(quantity), quantity)
        self.assertEqual(target_reduce_quantity(0), 0)

    def test_clear_quantity_uses_whole_lots_except_odd_lot_remainder(self):
        self.assertEqual(clear_sell_quantity(0), 0)
        for quantity in range(1, 100):
            self.assertEqual(clear_sell_quantity(quantity), quantity)
        self.assertEqual(clear_sell_quantity(199), 100)
        self.assertEqual(clear_sell_quantity(600), 600)

    def test_quantity_rejects_negative_boolean_and_fractional_values(self):
        for invalid in (-1, True, Decimal("100.5")):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    StrategyPolicyError, "invalid_quantity"
                ):
                    target_reduce_quantity(invalid)


class HintPolicyTest(unittest.TestCase):
    def test_each_hint_channel_is_capped_and_conflicts_zero(self):
        index_key = "index:SH:000300"
        links = [membership(index_key)]
        self.assertEqual(
            hint_channel_adjustment(
                asset_kind="index",
                stock_identity_key="stock:SH:600000",
                for_trade_date=TRADE_DATE,
                hints=[hint(index_key, "buy"), hint(index_key, "buy")],
                memberships=links,
            )["adjustment"],
            1,
        )
        self.assertEqual(
            hint_channel_adjustment(
                asset_kind="index",
                stock_identity_key="stock:SH:600000",
                for_trade_date=TRADE_DATE,
                hints=[hint(index_key, "sell")],
                memberships=links,
            )["adjustment"],
            -1,
        )
        conflict = hint_channel_adjustment(
            asset_kind="index",
            stock_identity_key="stock:SH:600000",
            for_trade_date=TRADE_DATE,
            hints=[hint(index_key, "buy"), hint(index_key, "sell")],
            memberships=links,
        )
        self.assertEqual(conflict["adjustment"], 0)
        self.assertIs(conflict["conflict_zeroed"], True)
        self.assertEqual(
            hint_channel_adjustment(
                asset_kind="index",
                stock_identity_key="stock:SH:600000",
                for_trade_date=TRADE_DATE,
                hints=[],
                memberships=links,
            )["adjustment"],
            0,
        )

    def test_hint_requires_all_membership_date_status_quality_and_source_gates(self):
        index_key = "index:SH:000300"
        good_hint = hint(index_key, "buy")
        good_membership = membership(index_key)
        mutations = (
            ([good_hint], [membership(index_key, status="removed")]),
            ([good_hint], [membership(index_key, quality_status="failed")]),
            ([good_hint], [membership(index_key, source="unapproved")]),
            ([hint(index_key, "buy", status="removed")], [good_membership]),
            (
                [hint(index_key, "buy", quality_status="failed")],
                [good_membership],
            ),
            (
                [hint(index_key, "buy", for_trade_date="20260717")],
                [good_membership],
            ),
            ([hint(index_key, "buy", source="unapproved")], [good_membership]),
        )
        for hints, memberships in mutations:
            with self.subTest(hints=hints, memberships=memberships):
                audit = hint_channel_adjustment(
                    asset_kind="index",
                    stock_identity_key="stock:SH:600000",
                    for_trade_date=TRADE_DATE,
                    hints=hints,
                    memberships=memberships,
                )
                self.assertEqual(audit["adjustment"], 0)
                self.assertEqual(audit["evidence_refs"], ())

    def test_ordinary_or_direction_mismatched_context_is_not_hint(self):
        index_key = "index:SH:000300"
        links = [membership(index_key)]
        rejected = (
            hint(
                index_key,
                "buy",
                condition_key="BUY:D",
                original_condition_key="BUY",
                signal_type="B_BUY",
            ),
            hint(
                index_key,
                "buy",
                condition_key="SELL_HINT:D",
                original_condition_key="SELL_HINT",
                signal_type="B_BUY",
            ),
        )
        for row in rejected:
            with self.subTest(row=row):
                audit = hint_channel_adjustment(
                    asset_kind="index",
                    stock_identity_key="stock:SH:600000",
                    for_trade_date=TRADE_DATE,
                    hints=[row],
                    memberships=links,
                )
                self.assertEqual(audit["adjustment"], 0)
                self.assertEqual(audit["evidence_refs"], ())

    def test_latest_approved_membership_at_or_before_trade_date_governs(self):
        index_key = "index:SH:000300"
        current_hint = [hint(index_key, "buy")]
        older = membership(index_key, for_trade_date="20260719")
        accepted = hint_channel_adjustment(
            asset_kind="index",
            stock_identity_key="stock:SH:600000",
            for_trade_date=TRADE_DATE,
            hints=current_hint,
            memberships=[older],
        )
        self.assertEqual(accepted["adjustment"], 1)
        self.assertEqual(accepted["membership_refs"], (older["membership_ref"],))

        future_only = hint_channel_adjustment(
            asset_kind="index",
            stock_identity_key="stock:SH:600000",
            for_trade_date=TRADE_DATE,
            hints=current_hint,
            memberships=[
                membership(index_key, for_trade_date="20260721")
            ],
        )
        self.assertEqual(future_only["adjustment"], 0)

        newest_removed = membership(
            index_key,
            for_trade_date="20260719",
            status="removed",
            membership_ref="membership:newest-removed",
        )
        governed = hint_channel_adjustment(
            asset_kind="index",
            stock_identity_key="stock:SH:600000",
            for_trade_date=TRADE_DATE,
            hints=current_hint,
            memberships=[
                membership(
                    index_key,
                    for_trade_date="20260718",
                    membership_ref="membership:older-active",
                ),
                newest_removed,
            ],
        )
        self.assertEqual(governed["adjustment"], 0)
        self.assertEqual(governed["membership_refs"], ())

    def test_membership_same_date_uses_created_at_then_source_version(self):
        index_key = "index:SH:000300"
        current_hint = [hint(index_key, "buy")]
        older_active = membership(
            index_key,
            created_at="2026-07-20T09:00:00+08:00",
            source_version="v9",
            membership_ref="membership:older-active",
        )
        newer_removed = membership(
            index_key,
            created_at="2026-07-20T09:01:00+08:00",
            source_version="v1",
            status="removed",
            membership_ref="membership:newer-removed",
        )
        governed = hint_channel_adjustment(
            asset_kind="index",
            stock_identity_key="stock:SH:600000",
            for_trade_date=TRADE_DATE,
            hints=current_hint,
            memberships=[older_active, newer_removed],
        )
        self.assertEqual(governed["adjustment"], 0)
        self.assertEqual(governed["membership_refs"], ())

        same_time_v2 = membership(
            index_key,
            created_at="2026-07-20T09:01:00+08:00",
            source_version="v2",
            membership_ref="membership:v2-active",
        )
        accepted = hint_channel_adjustment(
            asset_kind="index",
            stock_identity_key="stock:SH:600000",
            for_trade_date=TRADE_DATE,
            hints=current_hint,
            memberships=[
                same_time_v2,
                older_active,
                newer_removed,
            ],
        )
        self.assertEqual(accepted["adjustment"], 1)
        self.assertEqual(
            accepted["membership_refs"],
            ("membership:v2-active",),
        )

    def test_shadow_ranking_preserves_null_and_is_input_order_independent(self):
        hints = [
            hint("index:SH:000300", "buy"),
            hint(
                "board:TDX:881001",
                "buy",
                asset_kind="board",
            ),
        ]
        memberships = [
            membership("index:SH:000300"),
            membership(
                "board:TDX:881001",
                asset_kind="board",
            ),
        ]
        candidates = [
            candidate("stock:SH:600001", "2", source_signal_projection_id=102),
            candidate("stock:SH:600000", None, source_signal_projection_id=103),
            candidate("stock:SZ:000001", "2", source_signal_projection_id=104),
        ]
        first = rank_shadow_buy_candidates(
            candidates,
            hints=hints,
            memberships=memberships,
            for_trade_date=TRADE_DATE,
            **policy_identity(),
        )
        second = rank_shadow_buy_candidates(
            list(reversed(candidates)),
            hints=list(reversed(hints)),
            memberships=list(reversed(memberships)),
            for_trade_date=TRADE_DATE,
            **policy_identity(),
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [row["identity_key"] for row in first],
            [
                "stock:SH:600000",
                "stock:SH:600001",
                "stock:SZ:000001",
            ],
        )
        missing = first[0]
        self.assertIsNone(missing["financial_score_raw"])
        self.assertEqual(missing["financial_rank_score"], "0")
        self.assertEqual(missing["score_status"], "missing")
        self.assertEqual(missing["hint_adjustment"], 2)
        self.assertEqual(missing["decision_rank_score"], "2")
        self.assertEqual(missing["mode"], "shadow_only")
        self.assertIs(missing["execution_authorized"], False)
        present = next(
            row for row in first if row["financial_score_raw"] is not None
        )
        self.assertEqual(present["score_status"], "available")
        self.assertEqual(
            missing["knowledge_bundle_version"],
            "N6_AI_KNOWLEDGE_BUNDLE_V3",
        )
        self.assertEqual(
            missing["knowledge_bundle_sha256"],
            "95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b",
        )

    def test_shadow_ranking_duplicate_identity_uses_source_id_tie_break(self):
        candidates = [
            candidate(
                "stock:SH:600000",
                "2",
                source_signal_projection_id=102,
            ),
            candidate(
                "stock:SH:600000",
                "2",
                source_signal_projection_id=101,
            ),
        ]
        first = rank_shadow_buy_candidates(
            candidates,
            hints=[],
            memberships=[],
            for_trade_date=TRADE_DATE,
            **policy_identity(),
        )
        second = rank_shadow_buy_candidates(
            list(reversed(candidates)),
            hints=[],
            memberships=[],
            for_trade_date=TRADE_DATE,
            **policy_identity(),
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [row["source_signal_projection_id"] for row in first],
            [101, 102],
        )

    def test_ranking_rejects_any_candidate_not_already_qualified_by_n5(self):
        base = candidate("stock:SH:600000", "1")
        mutations = (
            {"for_trade_date": "20260717"},
            {"source_layer": "N4_trigger"},
            {"direction": "sell"},
            {"status": "removed"},
            {"quality_status": "failed"},
            {"ai_eligible": False},
            {"source_signal_projection_id": 0},
            {"source_signal_projection_id": True},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(
                    StrategyPolicyError, "candidate_not_qualified"
                ):
                    rank_shadow_buy_candidates(
                        [{**base, **mutation}],
                        hints=[],
                        memberships=[],
                        for_trade_date=TRADE_DATE,
                        **policy_identity(),
                    )

    def test_policy_or_document_hash_mismatch_fails_closed(self):
        qualified = candidate("stock:SH:600000", "1")
        for identity in (
            {
                "policy_version": "wrong",
                "policy_document_sha256": POLICY_SHA,
                "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
                "knowledge_bundle_sha256": KNOWLEDGE_BUNDLE_SHA256,
            },
            {
                "policy_version": POLICY_VERSION,
                "policy_document_sha256": "0" * 64,
                "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
                "knowledge_bundle_sha256": KNOWLEDGE_BUNDLE_SHA256,
            },
            {
                "policy_version": POLICY_VERSION,
                "policy_document_sha256": POLICY_SHA,
                "knowledge_bundle_version": "N6_AI_KNOWLEDGE_BUNDLE_V2",
                "knowledge_bundle_sha256": KNOWLEDGE_BUNDLE_SHA256,
            },
            {
                "policy_version": POLICY_VERSION,
                "policy_document_sha256": POLICY_SHA,
                "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
                "knowledge_bundle_sha256": "0" * 64,
            },
        ):
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(
                    StrategyPolicyError, "policy_identity_mismatch"
                ):
                    rank_shadow_buy_candidates(
                        [qualified],
                        hints=[],
                        memberships=[],
                        for_trade_date=TRADE_DATE,
                        **identity,
                    )


class PositionPolicyTest(unittest.TestCase):
    def test_target_quote_requires_n3n6q_identity_date_quality_freshness_session(self):
        self.assertIs(
            target_quote_reaches_locked_price(
                quote(),
                identity_key="stock:SH:600000",
                for_trade_date=TRADE_DATE,
                locked_target_price="12",
                evaluation_time=EVALUATION_TIME,
            ),
            True,
        )
        rejected = (
            quote(source="other"),
            quote(identity_key="stock:SZ:000001"),
            quote(identity_key="board:TDX:881001"),
            quote(for_trade_date="20260717"),
            quote(current_price="NaN"),
            quote(current_price="0"),
            quote(quality_status="failed"),
            quote(is_fresh=False),
            quote(session_status="closed"),
            quote(quote_minute="2026-07-20T09:59:00+08:00"),
            quote(quote_minute="2026-07-20T10:03:00+08:00"),
            quote(
                quote_minute="2026-07-20T10:02:00+08:00",
                fetched_at="2026-07-20T10:01:59+08:00",
            ),
            quote(fetched_at="2026-07-20T10:03:00+08:00"),
            quote(quote_minute="2026-07-20T10:02:00"),
            quote(fetched_at="2026-07-20T10:02:10"),
        )
        for row in rejected:
            with self.subTest(row=row):
                self.assertIs(
                    target_quote_reaches_locked_price(
                        row,
                        identity_key="stock:SH:600000",
                        for_trade_date=TRADE_DATE,
                        locked_target_price="12",
                        evaluation_time=EVALUATION_TIME,
                    ),
                    False,
                )

    def test_target_quote_rejects_lunch_after_close_and_cross_date(self):
        rejected = (
            (
                quote(
                    quote_minute="2026-07-20T11:59:00+08:00",
                    fetched_at="2026-07-20T11:59:10+08:00",
                ),
                datetime(
                    2026, 7, 20, 12, 0, tzinfo=DISPLAY_TIMEZONE
                ),
            ),
            (
                quote(
                    quote_minute="2026-07-20T15:00:00+08:00",
                    fetched_at="2026-07-20T15:00:10+08:00",
                ),
                datetime(
                    2026, 7, 20, 15, 1, tzinfo=DISPLAY_TIMEZONE
                ),
            ),
            (
                quote(
                    quote_minute="2026-07-20T23:59:00+08:00",
                    fetched_at="2026-07-20T23:59:10+08:00",
                ),
                datetime(
                    2026, 7, 21, 0, 0, tzinfo=DISPLAY_TIMEZONE
                ),
            ),
        )
        for row, evaluation_time in rejected:
            with self.subTest(evaluation_time=evaluation_time):
                self.assertIs(
                    target_quote_reaches_locked_price(
                        row,
                        identity_key="stock:SH:600000",
                        for_trade_date=TRADE_DATE,
                        locked_target_price="12",
                        evaluation_time=evaluation_time,
                    ),
                    False,
                )

    def test_target_reduction_boundary_is_account_position_episode_and_price(self):
        self.assertEqual(
            target_reduction_boundary(position()),
            (7, 11, 3, "12"),
        )
        changed = position(holding_episode_no=4)
        self.assertNotEqual(
            target_reduction_boundary(position()),
            target_reduction_boundary(changed),
        )

    def test_target_reduce_requires_frozen_passed_positive_source(self):
        mutations = (
            {"target_price_status": "candidate"},
            {"locked_target_quality_status": "failed"},
            {"locked_target_source_signal_projection_id": None},
            {"locked_target_source_signal_projection_id": 0},
            {"locked_target_source_signal_projection_id": True},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = evaluate_position_strategy(
                    position(quantity=100, **mutation),
                    lots=[lot(1, 100, "20260720", lot_status="available")],
                    target_quote=quote(current_price="12.50"),
                    sell_message=None,
                    for_trade_date=TRADE_DATE,
                    evaluation_time=EVALUATION_TIME,
                    executed_target_boundaries=set(),
                    **policy_identity(),
                )
                self.assertEqual(result["action_type"], "none")
                self.assertEqual(result["quantity"], 0)

    def test_period_match_uses_up_sell_reference_period_not_up_reference_period(self):
        mature = [lot(1, 300, "20260720", lot_status="available")]
        result = evaluate_position_strategy(
            position(
                quantity=300,
                up_sell_reference_period="M",
                up_reference_period="Q",
            ),
            lots=mature,
            target_quote=quote(current_price="10"),
            sell_message=sell_message(primary_trigger_period="M"),
            for_trade_date=TRADE_DATE,
            evaluation_time=EVALUATION_TIME,
            executed_target_boundaries=set(),
            **policy_identity(),
        )
        self.assertEqual(result["action_type"], "period_clear")
        mismatch = evaluate_position_strategy(
            position(
                quantity=300,
                up_sell_reference_period="M",
                up_reference_period="Q",
            ),
            lots=mature,
            target_quote=quote(current_price="10"),
            sell_message=sell_message(primary_trigger_period="Q"),
            for_trade_date=TRADE_DATE,
            evaluation_time=EVALUATION_TIME,
            executed_target_boundaries=set(),
            **policy_identity(),
        )
        self.assertEqual(mismatch["action_type"], "none")

    def test_sellable_quantity_aggregates_only_same_mature_open_episode_lots(self):
        lots = [
            lot(1, 100, "20260719", lot_status="available"),
            lot(2, 200, "20260720"),
            lot(3, 300, "20260721"),
            lot(4, 0, "20260719", lot_status="closed"),
            lot(5, 500, "20260719", virtual_account_id=8),
            lot(6, 600, "20260719", holding_episode_no=4),
        ]
        self.assertEqual(
            server_sellable_quantity(
                lots,
                virtual_account_id=7,
                virtual_position_id=11,
                holding_episode_no=3,
                for_trade_date=TRADE_DATE,
            ),
            300,
        )

    def test_unknown_positive_lot_status_and_position_lot_drift_fail_closed(self):
        with self.assertRaisesRegex(
            StrategyPolicyError, "unknown_positive_lot_status"
        ):
            server_sellable_quantity(
                [lot(1, 100, "20260720", lot_status="mystery")],
                virtual_account_id=7,
                virtual_position_id=11,
                holding_episode_no=3,
                for_trade_date=TRADE_DATE,
            )
        for inconsistent in (
            (
                position(pending_clear=True, quantity=0),
                [lot(1, 100, "20260720")],
            ),
            (
                position(pending_clear=True, quantity=100),
                [lot(1, 0, "20260720", lot_status="closed")],
            ),
        ):
            with self.subTest(inconsistent=inconsistent):
                with self.assertRaisesRegex(
                    StrategyPolicyError, "position_lot_quantity_mismatch"
                ):
                    evaluate_pending_clear(
                        inconsistent[0],
                        lots=inconsistent[1],
                        for_trade_date=TRADE_DATE,
                        **policy_identity(),
                    )

    def test_pending_clear_continues_when_lots_mature_and_completes_at_zero(self):
        waiting = evaluate_pending_clear(
            position(pending_clear=True, quantity=300),
            lots=[lot(1, 300, "20260721")],
            for_trade_date=TRADE_DATE,
            **policy_identity(),
        )
        self.assertEqual(waiting["action_type"], "pending_clear_wait_t1")
        self.assertIs(waiting["pending_clear"], True)
        continued = evaluate_pending_clear(
            position(pending_clear=True, quantity=300),
            lots=[lot(1, 300, "20260720")],
            for_trade_date=TRADE_DATE,
            **policy_identity(),
        )
        self.assertEqual(continued["action_type"], "pending_clear_continue")
        self.assertEqual(continued["quantity"], 300)
        self.assertIs(continued["pending_clear"], True)
        completed = evaluate_pending_clear(
            position(
                pending_clear=True,
                quantity=0,
                available_quantity=0,
                locked_quantity=0,
                position_status="closed_virtual",
            ),
            lots=[lot(1, 0, "20260720", lot_status="closed")],
            for_trade_date=TRADE_DATE,
            **policy_identity(),
        )
        self.assertEqual(completed["action_type"], "pending_clear_completed")
        self.assertIs(completed["pending_clear"], False)
        for result in (waiting, continued, completed):
            self.assertEqual(result["mode"], "shadow_only")
            self.assertIs(result["execution_authorized"], False)

    def test_pending_clear_completion_requires_closed_position_and_lot_proof(
        self,
    ):
        for candidate_position, candidate_lots in (
            (
                position(
                    pending_clear=True,
                    quantity=0,
                    available_quantity=0,
                    locked_quantity=0,
                    position_status="closed_virtual",
                ),
                [],
            ),
            (
                position(
                    pending_clear=True,
                    quantity=0,
                    available_quantity=0,
                    locked_quantity=0,
                    position_status="open_virtual",
                ),
                [lot(1, 0, "20260720", lot_status="closed")],
            ),
        ):
            with self.subTest(
                status=candidate_position["position_status"],
                lot_count=len(candidate_lots),
            ):
                with self.assertRaises(StrategyPolicyError):
                    evaluate_pending_clear(
                        candidate_position,
                        lots=candidate_lots,
                        for_trade_date=TRADE_DATE,
                        **policy_identity(),
                    )

    def test_pending_clear_requires_active_flag_and_ai_stock_identity(self):
        invalid_positions = (
            position(pending_clear=False),
            position(pending_clear=None),
            position(pending_clear=True, principal_type="human_user"),
            position(pending_clear=True, asset_kind="index"),
            position(pending_clear=True, identity_key="stock:BJ:430001"),
            position(pending_clear=True, principal_id=0),
            position(pending_clear=True, ai_user_id=0),
            position(pending_clear=True, strategy_id=0),
            position(pending_clear=True, policy_version="wrong"),
            position(pending_clear=True, policy_hash="0" * 64),
        )
        for candidate_position in invalid_positions:
            with self.subTest(position=candidate_position):
                with self.assertRaises(StrategyPolicyError):
                    evaluate_pending_clear(
                        candidate_position,
                        lots=[lot(1, 500, "20260720")],
                        for_trade_date=TRADE_DATE,
                        **policy_identity(),
                    )

    def test_pending_clear_rejects_same_episode_lot_identity_drift(self):
        for overrides in (
            {"virtual_account_id": 8},
            {"principal_id": 3},
            {"principal_type": "human_user"},
            {"identity_key": "stock:SH:600001"},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(
                    StrategyPolicyError,
                    "position_lot_identity_mismatch",
                ):
                    evaluate_pending_clear(
                        position(pending_clear=True),
                        lots=[lot(1, 500, "20260720", **overrides)],
                        for_trade_date=TRADE_DATE,
                        **policy_identity(),
                    )

        result = evaluate_pending_clear(
            position(pending_clear=True),
            lots=[
                lot(1, 500, "20260720"),
                lot(2, 99, "20260720", virtual_position_id=99),
            ],
            for_trade_date=TRADE_DATE,
            **policy_identity(),
        )
        self.assertEqual(result["action_type"], "pending_clear_continue")

    def test_pending_clear_requires_positive_unique_lot_ids(self):
        invalid_lot_sets = (
            [
                lot(1, 250, "20260720"),
                lot(1, 250, "20260720"),
            ],
            [lot(0, 500, "20260720")],
            [lot(None, 500, "20260720")],
        )
        for candidate_lots in invalid_lot_sets:
            with self.subTest(lots=candidate_lots):
                with self.assertRaises(StrategyPolicyError):
                    evaluate_pending_clear(
                        position(pending_clear=True),
                        lots=candidate_lots,
                        for_trade_date=TRADE_DATE,
                        **policy_identity(),
                    )

    def test_pending_clear_blocks_only_same_account_and_identity_buy(self):
        positions = [position(pending_clear=True)]
        self.assertIs(
            buy_blocked_by_pending_clear(
                virtual_account_id=7,
                identity_key="stock:SH:600000",
                positions=positions,
            ),
            True,
        )
        self.assertIs(
            buy_blocked_by_pending_clear(
                virtual_account_id=8,
                identity_key="stock:SH:600000",
                positions=positions,
            ),
            False,
        )
        self.assertIs(
            buy_blocked_by_pending_clear(
                virtual_account_id=7,
                identity_key="stock:SH:600000",
                positions=[position(pending_clear=False)],
            ),
            False,
        )
        self.assertIs(
            buy_blocked_by_pending_clear(
                virtual_account_id=7,
                identity_key="stock:SH:600000",
                positions=[
                    position(
                        pending_clear=False,
                        episode_status="closed",
                        quantity=0,
                        available_quantity=0,
                    )
                ],
            ),
            False,
        )
        self.assertIs(
            buy_blocked_by_pending_clear(
                virtual_account_id=7,
                identity_key="stock:SH:600000",
                positions=[
                    position(pending_clear=False),
                    position(
                        virtual_position_id=12,
                        holding_episode_no=4,
                        pending_clear=True,
                    ),
                ],
            ),
            True,
        )
        for invalid_position in (
            position(pending_clear=True, principal_type="human_user"),
            position(pending_clear=True, asset_kind="index"),
            position(pending_clear=True, episode_status="closed"),
            position(pending_clear="true"),
            position(pending_clear=1),
            position(pending_clear=None),
            {
                key: value
                for key, value in position(pending_clear=True).items()
                if key != "pending_clear"
            },
        ):
            with self.subTest(position=invalid_position):
                with self.assertRaises(StrategyPolicyError):
                    buy_blocked_by_pending_clear(
                        virtual_account_id=7,
                        identity_key="stock:SH:600000",
                        positions=[invalid_position],
                    )
        for account_id, identity_key in (
            (0, "stock:SH:600000"),
            (7, "stock:BJ:430001"),
        ):
            with self.subTest(
                account_id=account_id,
                identity_key=identity_key,
            ):
                with self.assertRaises(StrategyPolicyError):
                    buy_blocked_by_pending_clear(
                        virtual_account_id=account_id,
                        identity_key=identity_key,
                        positions=[],
                    )
        self.assertIs(
            buy_blocked_by_pending_clear(
                virtual_account_id=7,
                identity_key="stock:SH:600000",
                positions=[
                    position(
                        pending_clear=True,
                        quantity=0,
                        available_quantity=0,
                        locked_quantity=0,
                    )
                ],
            ),
            True,
        )
        self.assertIs(
            buy_blocked_by_pending_clear(
                virtual_account_id=7,
                identity_key="stock:SH:600001",
                positions=positions,
            ),
            False,
        )

    def test_unified_strategy_continues_pending_clear_before_other_actions(self):
        result = evaluate_position_strategy(
            position(pending_clear=True, quantity=300),
            lots=[lot(1, 300, "20260720")],
            target_quote=quote(current_price="99"),
            sell_message=sell_message(primary_trigger_period="M"),
            for_trade_date=TRADE_DATE,
            evaluation_time=EVALUATION_TIME,
            executed_target_boundaries=set(),
            **policy_identity(),
        )
        self.assertEqual(result["action_type"], "pending_clear_continue")
        self.assertEqual(result["quantity"], 300)
        self.assertNotIn("target_reduction_suppressed", result)

    def test_clear_sell_reference_alias_must_match_canonical_period(self):
        with self.assertRaisesRegex(
            StrategyPolicyError, "clear_sell_ref_period_mismatch"
        ):
            evaluate_position_strategy(
                position(
                    quantity=300,
                    up_sell_reference_period="M",
                    clear_sell_ref_period="Q",
                ),
                lots=[lot(1, 300, "20260720")],
                target_quote=quote(),
                sell_message=sell_message(),
                for_trade_date=TRADE_DATE,
                evaluation_time=EVALUATION_TIME,
                executed_target_boundaries=set(),
                **policy_identity(),
            )

    def test_period_clear_has_priority_and_suppresses_target_reduction_in_audit(self):
        result = evaluate_position_strategy(
            position(quantity=600),
            lots=[lot(1, 600, "20260720")],
            target_quote=quote(current_price="12.50"),
            sell_message=sell_message(primary_trigger_period="M"),
            for_trade_date=TRADE_DATE,
            evaluation_time=EVALUATION_TIME,
            executed_target_boundaries=set(),
            **policy_identity(),
        )
        self.assertEqual(result["action_type"], "period_clear")
        self.assertEqual(result["quantity"], 600)
        self.assertIs(result["target_reduction_suppressed"], True)
        self.assertEqual(
            result["target_reduction_suppressed_reason"],
            "period_clear_priority",
        )
        self.assertEqual(result["mode"], "shadow_only")
        self.assertIs(result["execution_authorized"], False)

    def test_target_reduction_is_idempotent_and_never_execution_authorized(self):
        boundary = target_reduction_boundary(position())
        first = evaluate_position_strategy(
            position(quantity=600),
            lots=[lot(1, 600, "20260720")],
            target_quote=quote(current_price="12.50"),
            sell_message=None,
            for_trade_date=TRADE_DATE,
            evaluation_time=EVALUATION_TIME,
            executed_target_boundaries=set(),
            **policy_identity(),
        )
        self.assertEqual(first["action_type"], "target_reduce")
        self.assertEqual(first["quantity"], 200)
        replay = evaluate_position_strategy(
            position(quantity=600),
            lots=[lot(1, 600, "20260720")],
            target_quote=quote(current_price="12.50"),
            sell_message=None,
            for_trade_date=TRADE_DATE,
            evaluation_time=EVALUATION_TIME,
            executed_target_boundaries={boundary},
            **policy_identity(),
        )
        self.assertEqual(replay["action_type"], "none")
        self.assertEqual(replay["reason"], "target_reduction_already_recorded")
        for result in (first, replay):
            self.assertEqual(result["mode"], "shadow_only")
            self.assertIs(result["execution_authorized"], False)


if __name__ == "__main__":
    unittest.main()
