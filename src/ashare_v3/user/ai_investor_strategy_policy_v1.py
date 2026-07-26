"""Deterministic Shadow-only policy helpers for the N6 AI investor.

This module is deliberately pure: it performs no database, network, clock, or
filesystem access.  Callers must provide already-approved N6 context and an
explicit trade date.  Every action-like result is audit-only and never grants
execution authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo


POLICY_VERSION = "n6_ai_investor_strategy_policy_v1"
POLICY_DOCUMENT_SHA256 = (
    "56082554c4f1099c9fa265d80f0233fde7459d2748be4c85f69fc198bddfc9e7"
)
KNOWLEDGE_BUNDLE_VERSION = "N6_AI_KNOWLEDGE_BUNDLE_V3"
KNOWLEDGE_BUNDLE_SHA256 = (
    "95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b"
)
SHADOW_MODE = "shadow_only"
DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")

_STOCK_PREFIXES = ("stock:SH:", "stock:SZ:")
_SELLABLE_LOT_STATUSES = frozenset({"locked_t1", "available"})
_APPROVED_HINT_SOURCE = "approved_n6_context"
_APPROVED_MEMBERSHIP_SOURCE = "approved_n6_membership"


class StrategyPolicyError(ValueError):
    """The supplied context does not satisfy the frozen policy contract."""


def validate_policy_identity(
    *,
    policy_version: str,
    policy_document_sha256: str,
    knowledge_bundle_version: str,
    knowledge_bundle_sha256: str,
) -> None:
    if (
        policy_version != POLICY_VERSION
        or policy_document_sha256 != POLICY_DOCUMENT_SHA256
        or knowledge_bundle_version != KNOWLEDGE_BUNDLE_VERSION
        or knowledge_bundle_sha256 != KNOWLEDGE_BUNDLE_SHA256
    ):
        raise StrategyPolicyError("policy_identity_mismatch")


def target_reduce_quantity(server_sellable_quantity: Any) -> int:
    """Return the one-third target reduction, respecting A-share lots."""

    quantity = _whole_non_negative_quantity(server_sellable_quantity)
    if quantity < 100:
        return quantity
    base_quantity = (quantity // 300) * 100
    return min(quantity, max(100, base_quantity))


def clear_sell_quantity(server_sellable_quantity: Any) -> int:
    """Return all sellable whole lots, or an entire odd-lot remainder."""

    quantity = _whole_non_negative_quantity(server_sellable_quantity)
    if quantity < 100:
        return quantity
    return (quantity // 100) * 100


def hint_channel_adjustment(
    *,
    asset_kind: str,
    stock_identity_key: str,
    for_trade_date: date,
    hints: Sequence[Mapping[str, Any]],
    memberships: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Calculate one capped HINT channel from approved N6 evidence."""

    if asset_kind not in {"index", "board"}:
        raise StrategyPolicyError("invalid_hint_asset_kind")
    if not _is_stock_identity(stock_identity_key):
        raise StrategyPolicyError("invalid_stock_identity")
    trade_date_text = _trade_date_text(for_trade_date)

    membership_candidates: dict[
        str,
        list[tuple[date, datetime, str, Mapping[str, Any]]],
    ] = {}
    for row in memberships:
        if (
            row.get("asset_kind") == asset_kind
            and row.get("stock_identity_key") == stock_identity_key
            and row.get("source") == _APPROVED_MEMBERSHIP_SOURCE
        ):
            context_identity = row.get("context_identity_key")
            try:
                membership_date = _parse_date(row.get("for_trade_date"))
                membership_created_at = _aware_datetime(
                    row.get("created_at"),
                    "invalid_membership_created_at",
                )
            except StrategyPolicyError:
                continue
            source_version = row.get("source_version")
            if (
                isinstance(context_identity, str)
                and membership_date <= for_trade_date
                and isinstance(source_version, str)
                and bool(source_version)
            ):
                membership_candidates.setdefault(context_identity, []).append(
                    (
                        membership_date,
                        membership_created_at,
                        source_version,
                        row,
                    )
                )

    approved_contexts: dict[str, tuple[str, ...]] = {}
    for context_identity, candidates in membership_candidates.items():
        latest_key = max(item[:3] for item in candidates)
        latest_rows = [
            row for row_date, created_at, source_version, row in candidates
            if (row_date, created_at, source_version) == latest_key
        ]
        if (
            len(latest_rows) == 1
            and latest_rows[0].get("status") == "active"
            and latest_rows[0].get("quality_status") == "passed"
            and isinstance(latest_rows[0].get("membership_ref"), str)
        ):
            approved_contexts[context_identity] = tuple(
                (str(latest_rows[0]["membership_ref"]),)
            )

    directions: set[str] = set()
    evidence_refs: set[str] = set()
    membership_refs: set[str] = set()
    for row in hints:
        context_identity = row.get("identity_key")
        direction = row.get("direction")
        if (
            row.get("asset_kind") == asset_kind
            and isinstance(context_identity, str)
            and context_identity in approved_contexts
            and direction in {"buy", "sell"}
            and row.get("for_trade_date") == trade_date_text
            and row.get("status") == "active"
            and row.get("quality_status") == "passed"
            and row.get("source") == _APPROVED_HINT_SOURCE
            and isinstance(row.get("evidence_ref"), str)
            and _hint_matches_direction(row, str(direction))
        ):
            directions.add(direction)
            evidence_refs.add(str(row["evidence_ref"]))
            membership_refs.update(approved_contexts[context_identity])

    conflict = directions == {"buy", "sell"}
    if conflict or not directions:
        adjustment = 0
    elif directions == {"buy"}:
        adjustment = 1
    else:
        adjustment = -1
    return _shadow_result(
        asset_kind=asset_kind,
        adjustment=adjustment,
        conflict_zeroed=conflict,
        evidence_refs=tuple(sorted(evidence_refs)),
        membership_refs=tuple(sorted(membership_refs)),
    )


def rank_shadow_buy_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    hints: Sequence[Mapping[str, Any]],
    memberships: Sequence[Mapping[str, Any]],
    for_trade_date: date,
    policy_version: str,
    policy_document_sha256: str,
    knowledge_bundle_version: str,
    knowledge_bundle_sha256: str,
) -> tuple[Mapping[str, Any], ...]:
    """Rank already-eligible candidates without granting buy authority."""

    validate_policy_identity(
        policy_version=policy_version,
        policy_document_sha256=policy_document_sha256,
        knowledge_bundle_version=knowledge_bundle_version,
        knowledge_bundle_sha256=knowledge_bundle_sha256,
    )
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        identity_key = candidate.get("identity_key")
        if not isinstance(identity_key, str) or not _is_stock_identity(
            identity_key
        ):
            raise StrategyPolicyError("invalid_stock_identity")
        if (
            candidate.get("for_trade_date")
            != _trade_date_text(for_trade_date)
            or candidate.get("source_layer") != "N5_action"
            or candidate.get("direction") != "buy"
            or candidate.get("status") != "active"
            or candidate.get("quality_status") != "passed"
            or candidate.get("ai_eligible") is not True
        ):
            raise StrategyPolicyError("candidate_not_qualified")
        try:
            source_signal_projection_id = _positive_identifier(
                candidate.get("source_signal_projection_id"),
                "candidate_not_qualified",
            )
        except StrategyPolicyError:
            raise StrategyPolicyError("candidate_not_qualified") from None
        raw_score = candidate.get("financial_score_raw")
        if raw_score is None:
            financial_score = Decimal(0)
            score_status = "missing"
        else:
            financial_score = _finite_decimal(
                raw_score, "invalid_financial_score"
            )
            score_status = "available"

        index_audit = hint_channel_adjustment(
            asset_kind="index",
            stock_identity_key=identity_key,
            for_trade_date=for_trade_date,
            hints=hints,
            memberships=memberships,
        )
        board_audit = hint_channel_adjustment(
            asset_kind="board",
            stock_identity_key=identity_key,
            for_trade_date=for_trade_date,
            hints=hints,
            memberships=memberships,
        )
        hint_adjustment = int(index_audit["adjustment"]) + int(
            board_audit["adjustment"]
        )
        if not -2 <= hint_adjustment <= 2:
            raise StrategyPolicyError("hint_adjustment_out_of_range")
        decision_score = financial_score + Decimal(hint_adjustment)
        ranked.append(
            {
                "identity_key": identity_key,
                "source_signal_projection_id": source_signal_projection_id,
                "financial_score_raw": raw_score,
                "financial_rank_score": _decimal_text(financial_score),
                "score_status": score_status,
                "index_hint_evidence_refs": index_audit["evidence_refs"],
                "board_hint_evidence_refs": board_audit["evidence_refs"],
                "index_membership_refs": index_audit["membership_refs"],
                "board_membership_refs": board_audit["membership_refs"],
                "index_hint_adjustment": index_audit["adjustment"],
                "board_hint_adjustment": board_audit["adjustment"],
                "index_hint_conflict_zeroed": index_audit[
                    "conflict_zeroed"
                ],
                "board_hint_conflict_zeroed": board_audit[
                    "conflict_zeroed"
                ],
                "hint_adjustment": hint_adjustment,
                "decision_rank_score": _decimal_text(decision_score),
                "policy_version": POLICY_VERSION,
                "policy_document_sha256": POLICY_DOCUMENT_SHA256,
                "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
                "knowledge_bundle_sha256": KNOWLEDGE_BUNDLE_SHA256,
                "mode": SHADOW_MODE,
                "execution_authorized": False,
                "_sort_score": decision_score,
            }
        )
    ranked.sort(
        key=lambda row: (
            -row["_sort_score"],
            row["identity_key"],
            row["source_signal_projection_id"],
        )
    )
    for row in ranked:
        del row["_sort_score"]
    return tuple(ranked)


def target_quote_reaches_locked_price(
    quote: Mapping[str, Any],
    *,
    identity_key: str,
    for_trade_date: date,
    locked_target_price: Any,
    evaluation_time: datetime,
) -> bool:
    """Fail closed unless an approved current-session N3N6Q quote qualifies."""

    if not _is_stock_identity(identity_key):
        return False
    if quote.get("source") != "n3n6q":
        return False
    if quote.get("identity_key") != identity_key:
        return False
    if quote.get("for_trade_date") != _trade_date_text(for_trade_date):
        return False
    if quote.get("quality_status") != "passed":
        return False
    if quote.get("is_fresh") is not True:
        return False
    if quote.get("session_status") != "trading":
        return False
    try:
        evaluated_at = _aware_datetime(
            evaluation_time, "invalid_evaluation_time"
        )
        quote_minute = _aware_datetime(
            quote.get("quote_minute"), "invalid_quote_minute"
        )
        fetched_at = _aware_datetime(
            quote.get("fetched_at"), "invalid_quote_fetched_at"
        )
        current_price = _finite_decimal(
            quote.get("current_price"), "invalid_quote_price"
        )
        target_price = _finite_decimal(
            locked_target_price, "invalid_locked_target_price"
        )
    except StrategyPolicyError:
        return False
    if not all(
        _in_trading_session(value, for_trade_date)
        for value in (evaluated_at, quote_minute, fetched_at)
    ):
        return False
    if (
        quote_minute > evaluated_at
        or fetched_at > evaluated_at
        or fetched_at < quote_minute
        or evaluated_at - quote_minute > timedelta(seconds=120)
        or evaluated_at - fetched_at > timedelta(seconds=120)
        or quote_minute.astimezone(DISPLAY_TIMEZONE).date()
        != _require_date(for_trade_date)
    ):
        return False
    return (
        current_price > 0
        and target_price > 0
        and current_price >= target_price
    )


def target_reduction_boundary(
    position: Mapping[str, Any],
) -> tuple[int, int, int, str]:
    """Return the frozen target-reduction idempotency boundary."""

    account_id = _positive_identifier(
        position.get("virtual_account_id"), "invalid_virtual_account_id"
    )
    position_id = _positive_identifier(
        position.get("virtual_position_id"), "invalid_virtual_position_id"
    )
    holding_episode_no = _positive_identifier(
        position.get("holding_episode_no"), "invalid_holding_episode_no"
    )
    locked_target_price = _finite_decimal(
        position.get("locked_target_price"), "invalid_locked_target_price"
    )
    if locked_target_price <= 0:
        raise StrategyPolicyError("invalid_locked_target_price")
    return (
        account_id,
        position_id,
        holding_episode_no,
        _decimal_text(locked_target_price),
    )


def server_sellable_quantity(
    lots: Sequence[Mapping[str, Any]],
    *,
    virtual_account_id: int,
    virtual_position_id: int,
    holding_episode_no: int,
    for_trade_date: date,
) -> int:
    """Aggregate only positive, same-episode lots that have matured."""

    trade_date = _require_date(for_trade_date)
    total = 0
    for row in lots:
        if (
            row.get("virtual_account_id") != virtual_account_id
            or row.get("virtual_position_id") != virtual_position_id
            or row.get("holding_episode_no") != holding_episode_no
        ):
            continue
        quantity = _whole_non_negative_quantity(
            row.get("remaining_quantity")
        )
        if quantity == 0:
            continue
        if row.get("lot_status") not in _SELLABLE_LOT_STATUSES:
            raise StrategyPolicyError("unknown_positive_lot_status")
        available_date = _parse_date(row.get("available_trade_date"))
        if available_date <= trade_date:
            total += quantity
    return total


def evaluate_pending_clear(
    position: Mapping[str, Any],
    *,
    lots: Sequence[Mapping[str, Any]],
    for_trade_date: date,
    policy_version: str,
    policy_document_sha256: str,
    knowledge_bundle_version: str,
    knowledge_bundle_sha256: str,
) -> Mapping[str, Any]:
    """Evaluate a pending-clear continuation using authoritative lot facts."""

    validate_policy_identity(
        policy_version=policy_version,
        policy_document_sha256=policy_document_sha256,
        knowledge_bundle_version=knowledge_bundle_version,
        knowledge_bundle_sha256=knowledge_bundle_sha256,
    )
    if (
        position.get("pending_clear") is not True
        or position.get("episode_status") != "open"
    ):
        raise StrategyPolicyError("pending_clear_episode_not_open")
    _validate_clear_period_alias(position)
    scoped_lots = _validate_position_lot_consistency(position, lots)
    if not scoped_lots:
        raise StrategyPolicyError("pending_clear_lot_proof_missing")
    total_quantity = sum(
        _whole_non_negative_quantity(row.get("remaining_quantity"))
        for row in scoped_lots
    )
    if total_quantity == 0:
        if (
            position.get("position_status") != "closed_virtual"
            or _whole_non_negative_quantity(
                position.get("available_quantity")
            )
            != 0
            or _whole_non_negative_quantity(
                position.get("locked_quantity")
            )
            != 0
            or position.get("quality_status") != "passed"
            or any(
                row.get("lot_status") != "closed"
                or _whole_non_negative_quantity(
                    row.get("remaining_quantity")
                )
                != 0
                for row in scoped_lots
            )
        ):
            raise StrategyPolicyError(
                "pending_clear_completion_not_proven"
            )
        return _shadow_result(
            action_type="pending_clear_completed",
            reason="holding_episode_quantity_zero",
            quantity=0,
            pending_clear=False,
        )
    if (
        position.get("position_status") != "open_virtual"
        or position.get("quality_status") != "passed"
    ):
        raise StrategyPolicyError("pending_clear_position_not_open")
    sellable = server_sellable_quantity(
        scoped_lots,
        virtual_account_id=int(position["virtual_account_id"]),
        virtual_position_id=int(position["virtual_position_id"]),
        holding_episode_no=int(position["holding_episode_no"]),
        for_trade_date=for_trade_date,
    )
    quantity = clear_sell_quantity(sellable)
    if quantity == 0:
        return _shadow_result(
            action_type="pending_clear_wait_t1",
            reason="no_mature_sellable_lot",
            quantity=0,
            pending_clear=True,
        )
    return _shadow_result(
        action_type="pending_clear_continue",
        reason="mature_lot_available",
        quantity=quantity,
        pending_clear=True,
    )


def buy_blocked_by_pending_clear(
    *,
    virtual_account_id: int,
    identity_key: str,
    positions: Sequence[Mapping[str, Any]],
) -> bool:
    """Block reopening the same account/identity until its episode is empty."""

    account_id = _positive_identifier(
        virtual_account_id, "invalid_virtual_account_id"
    )
    if not _is_stock_identity(identity_key):
        raise StrategyPolicyError("invalid_stock_identity")
    for row in positions:
        if (
            row.get("virtual_account_id") != account_id
            or row.get("identity_key") != identity_key
        ):
            continue
        _validated_position_identity(row)
        pending_clear = row.get("pending_clear")
        if pending_clear is not True and pending_clear is not False:
            raise StrategyPolicyError("invalid_pending_clear_status")
        episode_status = row.get("episode_status")
        if episode_status not in {"open", "closed"}:
            raise StrategyPolicyError("invalid_episode_status")
        if pending_clear is True:
            if episode_status != "open":
                raise StrategyPolicyError("pending_clear_episode_not_open")
            return True
    return False


def evaluate_position_strategy(
    position: Mapping[str, Any],
    *,
    lots: Sequence[Mapping[str, Any]],
    target_quote: Mapping[str, Any] | None,
    sell_message: Mapping[str, Any] | None,
    for_trade_date: date,
    evaluation_time: datetime,
    executed_target_boundaries: Set[tuple[int, int, int, str]],
    policy_version: str,
    policy_document_sha256: str,
    knowledge_bundle_version: str,
    knowledge_bundle_sha256: str,
) -> Mapping[str, Any]:
    """Evaluate one position, with period clear taking safe precedence."""

    validate_policy_identity(
        policy_version=policy_version,
        policy_document_sha256=policy_document_sha256,
        knowledge_bundle_version=knowledge_bundle_version,
        knowledge_bundle_sha256=knowledge_bundle_sha256,
    )
    _validate_clear_period_alias(position)
    scoped_lots = _validate_position_lot_consistency(position, lots)
    if position.get("pending_clear") is True:
        return evaluate_pending_clear(
            position,
            lots=scoped_lots,
            for_trade_date=for_trade_date,
            policy_version=policy_version,
            policy_document_sha256=policy_document_sha256,
            knowledge_bundle_version=knowledge_bundle_version,
            knowledge_bundle_sha256=knowledge_bundle_sha256,
        )
    if (
        position.get("position_status") != "open_virtual"
        or not _is_stock_identity(position.get("identity_key"))
    ):
        return _shadow_result(
            action_type="none",
            reason="position_not_eligible",
            quantity=0,
            pending_clear=bool(position.get("pending_clear")),
        )
    sellable = server_sellable_quantity(
        scoped_lots,
        virtual_account_id=int(position["virtual_account_id"]),
        virtual_position_id=int(position["virtual_position_id"]),
        holding_episode_no=int(position["holding_episode_no"]),
        for_trade_date=for_trade_date,
    )
    target_reached = (
        _target_context_ready(position)
        and bool(target_quote)
        and target_quote_reaches_locked_price(
            target_quote or {},
            identity_key=str(position["identity_key"]),
            for_trade_date=for_trade_date,
            locked_target_price=position.get("locked_target_price"),
            evaluation_time=evaluation_time,
        )
    )
    period_clear = _period_clear_matches(
        sell_message,
        position=position,
        for_trade_date=for_trade_date,
    )
    if period_clear:
        return _shadow_result(
            action_type="period_clear",
            reason="period_exact_match",
            quantity=clear_sell_quantity(sellable),
            pending_clear=True,
            target_reduction_suppressed=target_reached,
            target_reduction_suppressed_reason=(
                "period_clear_priority" if target_reached else None
            ),
        )

    if not target_reached:
        return _shadow_result(
            action_type="none",
            reason="no_strategy_trigger",
            quantity=0,
            pending_clear=bool(position.get("pending_clear")),
        )
    boundary = target_reduction_boundary(position)
    if boundary in executed_target_boundaries:
        return _shadow_result(
            action_type="none",
            reason="target_reduction_already_recorded",
            quantity=0,
            pending_clear=bool(position.get("pending_clear")),
            target_reduction_boundary=boundary,
        )
    return _shadow_result(
        action_type="target_reduce",
        reason="locked_target_reached",
        quantity=target_reduce_quantity(sellable),
        pending_clear=bool(position.get("pending_clear")),
        target_reduction_boundary=boundary,
    )


def _period_clear_matches(
    message: Mapping[str, Any] | None,
    *,
    position: Mapping[str, Any],
    for_trade_date: date,
) -> bool:
    if not message:
        return False
    return (
        message.get("source_layer") == "N5_action"
        and message.get("identity_key") == position.get("identity_key")
        and message.get("direction") == "sell"
        and message.get("for_trade_date") == _trade_date_text(for_trade_date)
        and message.get("status") == "active"
        and message.get("quality_status") == "passed"
        and isinstance(message.get("primary_trigger_period"), str)
        and message.get("primary_trigger_period")
        == position.get("up_sell_reference_period")
    )


def _scoped_lots(
    position: Mapping[str, Any],
    lots: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    (
        account_id,
        position_id,
        principal_id,
        identity_key,
        episode,
    ) = _validated_position_identity(position)
    scoped: list[Mapping[str, Any]] = []
    seen_lot_ids: set[int] = set()
    for row in lots:
        if (
            row.get("virtual_position_id") != position_id
            or row.get("holding_episode_no") != episode
        ):
            continue
        if (
            row.get("virtual_account_id") != account_id
            or row.get("principal_id") != principal_id
            or row.get("principal_type") != "ai_user"
            or row.get("identity_key") != identity_key
        ):
            raise StrategyPolicyError("position_lot_identity_mismatch")
        lot_id = _positive_identifier(
            row.get("virtual_position_lot_id"),
            "invalid_virtual_position_lot_id",
        )
        if lot_id in seen_lot_ids:
            raise StrategyPolicyError("duplicate_virtual_position_lot_id")
        seen_lot_ids.add(lot_id)
        quantity = _whole_non_negative_quantity(
            row.get("remaining_quantity")
        )
        if (
            quantity > 0
            and row.get("lot_status") not in _SELLABLE_LOT_STATUSES
        ):
            raise StrategyPolicyError("unknown_positive_lot_status")
        scoped.append(row)
    return tuple(scoped)


def _validated_position_identity(
    position: Mapping[str, Any],
) -> tuple[int, int, int, str, int]:
    _positive_identifier(position.get("ai_user_id"), "invalid_ai_user_id")
    _positive_identifier(position.get("strategy_id"), "invalid_strategy_id")
    account_id = _positive_identifier(
        position.get("virtual_account_id"), "invalid_virtual_account_id"
    )
    position_id = _positive_identifier(
        position.get("virtual_position_id"), "invalid_virtual_position_id"
    )
    principal_id = _positive_identifier(
        position.get("principal_id"), "invalid_principal_id"
    )
    episode = _positive_identifier(
        position.get("holding_episode_no"), "invalid_holding_episode_no"
    )
    identity_key = position.get("identity_key")
    if (
        position.get("principal_type") != "ai_user"
        or position.get("asset_kind") != "stock"
        or not isinstance(identity_key, str)
        or not _is_stock_identity(identity_key)
        or position.get("policy_version") != POLICY_VERSION
        or position.get("policy_hash") != POLICY_DOCUMENT_SHA256
    ):
        raise StrategyPolicyError("invalid_strategy_episode_identity")
    return account_id, position_id, principal_id, identity_key, episode


def _validate_position_lot_consistency(
    position: Mapping[str, Any],
    lots: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    scoped = _scoped_lots(position, lots)
    position_quantity = _whole_non_negative_quantity(
        position.get("quantity")
    )
    lot_quantity = sum(
        _whole_non_negative_quantity(row.get("remaining_quantity"))
        for row in scoped
    )
    if lot_quantity != position_quantity:
        raise StrategyPolicyError("position_lot_quantity_mismatch")
    return scoped


def _validate_clear_period_alias(position: Mapping[str, Any]) -> None:
    if (
        "clear_sell_ref_period" in position
        and position.get("clear_sell_ref_period")
        != position.get("up_sell_reference_period")
    ):
        raise StrategyPolicyError("clear_sell_ref_period_mismatch")


def _hint_matches_direction(
    row: Mapping[str, Any], direction: str
) -> bool:
    expected = "BUY_HINT" if direction == "buy" else "SELL_HINT"
    opposite = "SELL_HINT" if direction == "buy" else "BUY_HINT"
    keys = tuple(
        value
        for value in (
            row.get("condition_key"),
            row.get("original_condition_key"),
        )
        if isinstance(value, str)
    )

    def matches(value: str, prefix: str) -> bool:
        return value == prefix or value.startswith(f"{prefix}:")

    return any(matches(value, expected) for value in keys) and not any(
        matches(value, opposite) for value in keys
    )


def _target_context_ready(position: Mapping[str, Any]) -> bool:
    if (
        position.get("target_price_status") != "frozen"
        or position.get("locked_target_quality_status") != "passed"
    ):
        return False
    try:
        _positive_identifier(
            position.get("locked_target_source_signal_projection_id"),
            "invalid_locked_target_source_signal_projection_id",
        )
    except StrategyPolicyError:
        return False
    return True


def _shadow_result(**values: Any) -> Mapping[str, Any]:
    return {
        **values,
        "policy_version": POLICY_VERSION,
        "policy_document_sha256": POLICY_DOCUMENT_SHA256,
        "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
        "knowledge_bundle_sha256": KNOWLEDGE_BUNDLE_SHA256,
        "mode": SHADOW_MODE,
        "execution_authorized": False,
    }


def _whole_non_negative_quantity(value: Any) -> int:
    if isinstance(value, bool):
        raise StrategyPolicyError("invalid_quantity")
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise StrategyPolicyError("invalid_quantity") from None
    if (
        not quantity.is_finite()
        or quantity < 0
        or quantity != quantity.to_integral_value()
    ):
        raise StrategyPolicyError("invalid_quantity")
    return int(quantity)


def _positive_identifier(value: Any, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise StrategyPolicyError(reason)
    return value


def _finite_decimal(value: Any, reason: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise StrategyPolicyError(reason)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise StrategyPolicyError(reason) from None
    if not result.is_finite():
        raise StrategyPolicyError(reason)
    return result


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _is_stock_identity(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if not value.startswith(_STOCK_PREFIXES):
        return False
    code = value.rsplit(":", 1)[-1]
    return len(code) == 6 and code.isdigit()


def _require_date(value: Any) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise StrategyPolicyError("invalid_trade_date")
    return value


def _trade_date_text(value: Any) -> str:
    return _require_date(value).strftime("%Y%m%d")


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        raise StrategyPolicyError("invalid_available_trade_date")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise StrategyPolicyError("invalid_available_trade_date")
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise StrategyPolicyError("invalid_available_trade_date")


def _aware_datetime(value: Any, reason: str) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise StrategyPolicyError(reason) from None
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise StrategyPolicyError(reason)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StrategyPolicyError(reason)
    return parsed


def _in_trading_session(value: datetime, for_trade_date: date) -> bool:
    local_value = value.astimezone(DISPLAY_TIMEZONE)
    if local_value.date() != _require_date(for_trade_date):
        return False
    local_time = local_value.timetz().replace(tzinfo=None)
    return (
        time(9, 30) <= local_time <= time(11, 30)
        or time(13, 0) <= local_time <= time(15, 0)
    )
