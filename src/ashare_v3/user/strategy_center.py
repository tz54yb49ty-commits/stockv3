from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
from itertools import product
from typing import Any, Iterable, Mapping, Sequence

from ashare_v3.user.projection_plan import source_trade_date_for_event


PACKAGE_1 = "package_1"
PACKAGE_2 = "package_2"
ALLOWED_PACKAGES = (PACKAGE_1, PACKAGE_2)
STRATEGY_VERSION_V1 = "N6_STRATEGY_CENTER_V1"
STRATEGY_VERSION_V2 = "N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2"
SUPPORTED_STRATEGY_VERSIONS = (STRATEGY_VERSION_V1, STRATEGY_VERSION_V2)
ALLOWED_BOARD_TYPES = ("tdx_industry", "tdx_concept", "tdx_region")
ALLOWED_SCOPE_SOURCES = ("monitor", "realtime_scope", "virtual_position")
DISPLAY_ACTION_STATES = ("eligible", "executed")
ALLOWED_DIRECTIONS = ("buy", "sell")
MEMBERSHIP_INDEX_IDENTITIES = (
    "index:SH:000016",
    "index:SH:000300",
    "index:SH:000688",
    "index:SH:000852",
    "index:SH:000905",
    "index:SZ:399006",
    "index:SZ:399303",
)
MARKET_HEAT_INDEX_IDENTITIES = (
    "index:SH:000001",
    "index:SZ:399001",
)

_SHANGHAI_TIMEZONE = timezone(timedelta(hours=8))
_MORNING_OPEN = time(9, 30)
_MORNING_CLOSE = time(11, 30)
_AFTERNOON_OPEN = time(13, 0)
_AFTERNOON_CLOSE = time(15, 0)
_MORNING_SESSION_SECONDS = 2 * 60 * 60
_TRADE_DATE_SESSION_SECONDS = 4 * 60 * 60
_QUALIFIED_SPAN_SECONDS = 30 * 60
_WEAK_SPAN_SECONDS = 60 * 60
_MARKET_HEAT_RANK = {
    "MARKET_HEAT_SUPPORTIVE": 0,
    "MARKET_HEAT_NEUTRAL": 1,
    "MARKET_HEAT_MIXED": 2,
    "MARKET_HEAT_ADVERSE": 3,
}

_V1_EVALUATOR_POLICY = {
    "version": "n6_strategy_center_matcher_v1",
    "strategy_version": STRATEGY_VERSION_V1,
    "display_only": True,
    "trade_date_scope": "whole_trade_date",
    "direction_match_required": False,
    "package_1": {
        "index_any_executed_required": True,
        "board_any_executed_required": True,
    },
    "package_2": {
        "index_any_executed_required": False,
        "board_any_executed_required": True,
    },
    "allowed_board_types": list(ALLOWED_BOARD_TYPES),
}

_V2_EVALUATOR_POLICY = {
    "version": "n6_strategy_center_matcher_v2",
    "strategy_version": STRATEGY_VERSION_V2,
    "display_only": True,
    "shadow_only": True,
    "trade_date_scope": "same_a_share_trade_date",
    "cross_trade_date_allowed": False,
    "direction_match_required": True,
    "time_basis": "a_share_trading_minutes",
    "time_precision": "trading_seconds",
    "valid_sessions": [
        "09:30:00-11:30:00",
        "13:00:00-15:00:00",
    ],
    "exclude_midday_break": True,
    "coherence_levels": {
        "STRONG": "0-15",
        "MEDIUM": "16-30",
        "WEAK": "31-60",
        "EXPIRED": ">60",
    },
    "qualified_levels": ["STRONG", "MEDIUM"],
    "weak_policy": "display_only_not_qualified",
    "candidate_stale_after_trading_minutes": 30,
    "event_selection": "first_confirmation_then_minimum_span",
    "confirmation_time": "latest_required_event_time",
    "lookahead_allowed": False,
    "event_time_authority": "n5_standard_event_time_only",
    "invalid_or_midday_event_time_policy": "fail_closed",
    "freshness_statuses": ["fresh", "stale"],
    "observation_reasons": ["weak_span", "stale_after_confirmation"],
    "observation_retention": "same_trade_date_close",
    "stale_policy": "observation_until_trade_date_close",
    "event_lineage_frozen": True,
    "arrival_order_authority": "user_signal_projection_id_monotonic",
    "frozen_episode_authority": (
        "persisted_match_or_observation_projection"
    ),
    "successive_episode_trigger": (
        "new_qualification_parent_projection_only"
    ),
    "cross_surface_uniqueness": "one_coherence_episode_one_surface",
    "mixed_package_level_policy": (
        "qualified_if_any_package_qualified_weak_evidence_retained"
    ),
    "heat_evidence_frozen_per_episode": True,
    "stock_state_upgrade_creates_episode": False,
    "eligible_to_executed_policy": (
        "same_coherence_episode_state_update_without_parent_reselection"
    ),
    "new_parent_evidence_policy": "new_coherence_episode_without_overwrite",
    "signal_dto_policy": "canonical_signals_dto_byte_equivalent",
    "strategy_fields_surface": "top_level_confluence",
    "sse_surface_kinds": ["qualified_match", "observation"],
    "package_1": {
        "index_any_executed_required": True,
        "board_any_executed_required": True,
    },
    "package_2": {
        "index_any_executed_required": False,
        "board_any_executed_required": True,
    },
    "allowed_board_types": list(ALLOWED_BOARD_TYPES),
    "membership_indices": list(MEMBERSHIP_INDEX_IDENTITIES),
    "market_heat_indices": list(MARKET_HEAT_INDEX_IDENTITIES),
    "market_heat_creates_candidate": False,
    "market_heat_freshness_window_trading_minutes": 30,
    "market_heat_event_selection": "latest_not_after_confirmation",
    "market_heat_states": [
        "MARKET_HEAT_SUPPORTIVE",
        "MARKET_HEAT_ADVERSE",
        "MARKET_HEAT_MIXED",
        "MARKET_HEAT_NEUTRAL",
    ],
    "market_heat_rank_order": [
        "MARKET_HEAT_SUPPORTIVE",
        "MARKET_HEAT_NEUTRAL",
        "MARKET_HEAT_MIXED",
        "MARKET_HEAT_ADVERSE",
    ],
    "version_migration": (
        "v1_grandfathered_v2_per_user_pending_atomic_switch"
    ),
    "proposal_authorized": False,
    "order_authorized": False,
    "trade_authorized": False,
    "position_or_cash_mutation_authorized": False,
    "autonomous_trading_authorized": False,
    "real_trading_authorized": False,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _approved_package_policy_payload(package_key: str) -> dict[str, Any]:
    package_rules = {
        PACKAGE_1: {
            "requires": [
                "stock_signal",
                "member_board_signal",
                "at_least_one_member_index_signal",
            ],
            "same_direction_required": True,
            "maximum_qualified_span": 30,
            "maximum_qualified_span_seconds": 1800,
        },
        PACKAGE_2: {
            "requires": ["stock_signal", "member_board_signal"],
            "same_direction_required": True,
            "maximum_qualified_span": 30,
            "maximum_qualified_span_seconds": 1800,
        },
    }
    if package_key not in package_rules:
        raise ValueError("unknown approved package key")
    return {
        "package_id": "N6_SC_TEMPORAL_CONFLUENCE_V2_CANDIDATE_20260723",
        "strategy_version": "N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
        "proposed_policy": "n6_strategy_center_matcher_v2",
        "package_key": package_key,
        "package_version": "v2",
        "rules": {
            "direction_match_required": True,
            "time_basis": "a_share_trading_minutes",
            "time_precision": "trading_seconds",
            "valid_sessions": [
                "09:30:00-11:30:00",
                "13:00:00-15:00:00",
            ],
            "exclude_midday_break": True,
            "cross_trade_date_allowed": False,
            "coherence_levels": {
                "STRONG": "0-15",
                "MEDIUM": "16-30",
                "WEAK": "31-60",
                "EXPIRED": ">60",
            },
            "qualified_levels": ["STRONG", "MEDIUM"],
            "weak_policy": "display_only_not_qualified",
            "candidate_stale_after_trading_minutes": 30,
            "event_selection": "first_confirmation_then_minimum_span",
            "confirmation_time": "latest_required_event_time",
            "lookahead_allowed": False,
            "event_time_authority": "n5_standard_event_time_only",
            "invalid_or_midday_event_time_policy": "fail_closed",
            "freshness_statuses": ["fresh", "stale"],
            "observation_reasons": [
                "weak_span",
                "stale_after_confirmation",
            ],
            "observation_retention": "same_trade_date_close",
            "stale_policy": "observation_until_trade_date_close",
            "event_lineage_frozen": True,
            "arrival_order_authority": (
                "user_signal_projection_id_monotonic"
            ),
            "frozen_episode_authority": (
                "persisted_match_or_observation_projection"
            ),
            "successive_episode_trigger": (
                "new_qualification_parent_projection_only"
            ),
            "cross_surface_uniqueness": (
                "one_coherence_episode_one_surface"
            ),
            "mixed_package_level_policy": (
                "qualified_if_any_package_qualified_weak_evidence_retained"
            ),
            "heat_evidence_frozen_per_episode": True,
            "stock_state_upgrade_creates_episode": False,
            "eligible_to_executed_policy": (
                "same_coherence_episode_state_update_without_parent_reselection"
            ),
            "new_parent_evidence_policy": (
                "new_coherence_episode_without_overwrite"
            ),
            "signal_dto_policy": "canonical_signals_dto_byte_equivalent",
            "strategy_fields_surface": "top_level_confluence",
            "sse_surface_kinds": ["qualified_match", "observation"],
        },
        "market_heat_indices": list(MARKET_HEAT_INDEX_IDENTITIES),
        "market_heat_policy": {
            "membership_required": False,
            "creates_candidate": False,
            "freshness_window_trading_minutes": 30,
            "event_selection": "latest_not_after_confirmation",
            "affects": ["heat_label", "candidate_ranking"],
            "states": [
                "MARKET_HEAT_SUPPORTIVE",
                "MARKET_HEAT_ADVERSE",
                "MARKET_HEAT_MIXED",
                "MARKET_HEAT_NEUTRAL",
            ],
            "rank_order": [
                "MARKET_HEAT_SUPPORTIVE",
                "MARKET_HEAT_NEUTRAL",
                "MARKET_HEAT_MIXED",
                "MARKET_HEAT_ADVERSE",
            ],
        },
        "membership_indices": list(MEMBERSHIP_INDEX_IDENTITIES),
        f"{package_key}_rule": package_rules[package_key],
        "risk_boundaries": {
            "display_only": True,
            "shadow_only": True,
            "proposal_authorized": False,
            "order_authorized": False,
            "trade_authorized": False,
            "position_or_cash_mutation_authorized": False,
            "autonomous_trading_authorized": False,
            "real_trading_authorized": False,
            "missing_lineage_or_time_policy": "fail_closed",
            "scheduler_scope": "single_principal_user_revision_per_tick",
            "version_migration": (
                "v1_grandfathered_v2_per_user_pending_atomic_switch"
            ),
        },
    }


APPROVED_PACKAGE_POLICY_PAYLOADS = {
    package_key: _approved_package_policy_payload(package_key)
    for package_key in ALLOWED_PACKAGES
}
APPROVED_PACKAGE_POLICY_HASHES = {
    package_key: _sha256(payload)
    for package_key, payload in APPROVED_PACKAGE_POLICY_PAYLOADS.items()
}


V1_EVALUATOR_POLICY_HASH = _sha256(_V1_EVALUATOR_POLICY)
V2_EVALUATOR_POLICY_HASH = _sha256(_V2_EVALUATOR_POLICY)
# Backward-compatible name for callers that explicitly consume the V2 module.
EVALUATOR_POLICY_HASH = V2_EVALUATOR_POLICY_HASH


V1_PACKAGE_POLICY_PAYLOADS = {
    PACKAGE_1: {
        "stock_states": ["eligible", "executed"],
        "trade_date_scope": "whole_trade_date",
        "direction_match_required": False,
        "index_any_executed_required": True,
        "board_any_executed_required": True,
        "allowed_board_types": list(ALLOWED_BOARD_TYPES),
        "display_only": True,
    },
    PACKAGE_2: {
        "stock_states": ["eligible", "executed"],
        "trade_date_scope": "whole_trade_date",
        "direction_match_required": False,
        "index_any_executed_required": False,
        "board_any_executed_required": True,
        "allowed_board_types": list(ALLOWED_BOARD_TYPES),
        "display_only": True,
    },
}
# 073 hashes PostgreSQL's canonical jsonb text, not compact application JSON.
V1_PACKAGE_POLICY_HASHES = {
    PACKAGE_1: "abd3d8239d44fe4ef040e162521fa82de880d9b9949c6b78b9649f080e8b3cd5",
    PACKAGE_2: "e891b1f8dcc1490989bcf891d5ce5c21d7a6a8520aca160b1dce7ce2172e8951",
}
APPROVED_PACKAGE_POLICY_PAYLOADS_BY_VERSION = {
    (package_key, "v1"): V1_PACKAGE_POLICY_PAYLOADS[package_key]
    for package_key in ALLOWED_PACKAGES
} | {
    (package_key, "v2"): APPROVED_PACKAGE_POLICY_PAYLOADS[package_key]
    for package_key in ALLOWED_PACKAGES
}
APPROVED_PACKAGE_POLICY_HASHES_BY_VERSION = {
    (package_key, "v1"): V1_PACKAGE_POLICY_HASHES[package_key]
    for package_key in ALLOWED_PACKAGES
} | {
    (package_key, "v2"): APPROVED_PACKAGE_POLICY_HASHES[package_key]
    for package_key in ALLOWED_PACKAGES
}


@dataclass(frozen=True)
class ScopeRow:
    trade_date: str
    stock_identity_key: str
    scope_source: str


@dataclass(frozen=True)
class MembershipRow:
    trade_date: str
    stock_identity_key: str
    parent_asset_kind: str
    parent_identity_key: str
    parent_code: str
    parent_name: str
    source_version: str
    source_batch_id: str = ""
    created_at: str = ""
    board_type: str = ""


@dataclass(frozen=True)
class MembershipSnapshotAuthority:
    stock_identity_key: str
    action_episode_key: str
    membership_kind: str
    requested_source_trade_date: str
    selected_membership_trade_date: str
    source_version: str
    source_batch_id: str
    provenance_status: str
    quality_status: str


@dataclass(frozen=True)
class ParentExecutedEvent:
    trade_date: str
    asset_kind: str
    identity_key: str
    code: str
    name: str
    event_id: str
    event_type: str
    action_state: str
    event_time: str
    source_run_id: str
    event_schema_version: str
    direction: str = ""
    user_signal_projection_id: int = 0


@dataclass(frozen=True)
class StockSignalEvent:
    user_signal_projection_id: int
    trade_date: str
    identity_key: str
    code: str
    name: str
    event_id: str
    event_type: str
    action_state: str
    event_time: str
    action_episode_key: str
    source_run_id: str
    event_schema_version: str
    signal: Mapping[str, Any]

    @property
    def payload_json(self) -> Mapping[str, Any]:
        return self.signal


@dataclass(frozen=True)
class StrategyMatch:
    trade_date: str
    stock_identity_key: str
    action_episode_key: str
    coherence_episode_key: str
    action_state: str
    source_signal_projection_id: int
    source_event_ids: tuple[str, ...]
    matched_packages: tuple[str, ...]
    scope_sources: tuple[str, ...]
    indices: tuple[Mapping[str, Any], ...]
    matched_boards: tuple[Mapping[str, Any], ...]
    signal: Mapping[str, Any]
    confluence: Mapping[str, Any]
    state_timeline: tuple[Mapping[str, Any], ...]
    mapping_quality: str
    requested_source_trade_date: str
    membership_source_trade_date: str
    membership_provenance: tuple[Mapping[str, Any], ...]
    evaluator_policy_hash: str
    projection_hash: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "surface_kind": "qualified_match",
            "trade_date": self.trade_date,
            "stock_identity_key": self.stock_identity_key,
            "action_episode_key": self.action_episode_key,
            "coherence_episode_key": self.coherence_episode_key,
            "action_state": self.action_state,
            "source_signal_projection_id": self.source_signal_projection_id,
            "source_event_ids": list(self.source_event_ids),
            "matched_packages": list(self.matched_packages),
            "scope_sources": list(self.scope_sources),
            "indices": [dict(item) for item in self.indices],
            "matched_boards": [dict(item) for item in self.matched_boards],
            "signal": dict(self.signal),
            "confluence": dict(self.confluence),
            "state_timeline": [dict(item) for item in self.state_timeline],
            "mapping_quality": self.mapping_quality,
            "requested_source_trade_date": self.requested_source_trade_date,
            "membership_source_trade_date": self.membership_source_trade_date,
            "membership_provenance": [
                dict(item) for item in self.membership_provenance
            ],
            "evaluator_policy_hash": self.evaluator_policy_hash,
            "projection_hash": self.projection_hash,
        }


@dataclass(frozen=True)
class StrategyObservation:
    trade_date: str
    stock_identity_key: str
    action_episode_key: str
    coherence_episode_key: str
    action_state: str
    source_signal_projection_id: int
    source_event_ids: tuple[str, ...]
    observed_packages: tuple[str, ...]
    scope_sources: tuple[str, ...]
    indices: tuple[Mapping[str, Any], ...]
    observed_boards: tuple[Mapping[str, Any], ...]
    signal: Mapping[str, Any]
    confluence: Mapping[str, Any]
    state_timeline: tuple[Mapping[str, Any], ...]
    mapping_quality: str
    requested_source_trade_date: str
    membership_source_trade_date: str
    membership_provenance: tuple[Mapping[str, Any], ...]
    evaluator_policy_hash: str
    observation_reason: str
    observation_hash: str

    @classmethod
    def from_candidate(
        cls,
        candidate: StrategyMatch,
        *,
        observation_reason: str,
    ) -> "StrategyObservation":
        if observation_reason not in {
            "weak_span",
            "stale_after_confirmation",
        }:
            raise ValueError("unknown strategy observation reason")
        level = candidate.confluence.get("coherence_level")
        if observation_reason == "weak_span" and level != "WEAK":
            raise ValueError("weak observation requires WEAK confluence")
        if (
            observation_reason == "stale_after_confirmation"
            and candidate.confluence.get("freshness_status") != "stale"
        ):
            raise ValueError("stale observation requires stale confluence")
        observation_payload = {
            **candidate.as_payload(),
            "surface_kind": "observation",
            "observed_packages": list(candidate.matched_packages),
            "observation_reason": observation_reason,
        }
        observation_payload.pop("matched_packages", None)
        observation_payload.pop("projection_hash", None)
        return cls(
            trade_date=candidate.trade_date,
            stock_identity_key=candidate.stock_identity_key,
            action_episode_key=candidate.action_episode_key,
            coherence_episode_key=candidate.coherence_episode_key,
            action_state=candidate.action_state,
            source_signal_projection_id=candidate.source_signal_projection_id,
            source_event_ids=candidate.source_event_ids,
            observed_packages=candidate.matched_packages,
            scope_sources=candidate.scope_sources,
            indices=candidate.indices,
            observed_boards=candidate.matched_boards,
            signal=candidate.signal,
            confluence=candidate.confluence,
            state_timeline=candidate.state_timeline,
            mapping_quality=candidate.mapping_quality,
            requested_source_trade_date=candidate.requested_source_trade_date,
            membership_source_trade_date=candidate.membership_source_trade_date,
            membership_provenance=candidate.membership_provenance,
            evaluator_policy_hash=candidate.evaluator_policy_hash,
            observation_reason=observation_reason,
            observation_hash=_sha256(observation_payload),
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "surface_kind": "observation",
            "trade_date": self.trade_date,
            "stock_identity_key": self.stock_identity_key,
            "action_episode_key": self.action_episode_key,
            "coherence_episode_key": self.coherence_episode_key,
            "action_state": self.action_state,
            "source_signal_projection_id": self.source_signal_projection_id,
            "source_event_ids": list(self.source_event_ids),
            "observed_packages": list(self.observed_packages),
            "scope_sources": list(self.scope_sources),
            "indices": [dict(item) for item in self.indices],
            "observed_boards": [dict(item) for item in self.observed_boards],
            "signal": dict(self.signal),
            "confluence": dict(self.confluence),
            "state_timeline": [dict(item) for item in self.state_timeline],
            "mapping_quality": self.mapping_quality,
            "requested_source_trade_date": self.requested_source_trade_date,
            "membership_source_trade_date": self.membership_source_trade_date,
            "membership_provenance": [
                dict(item) for item in self.membership_provenance
            ],
            "evaluator_policy_hash": self.evaluator_policy_hash,
            "observation_reason": self.observation_reason,
            "observation_level": self.confluence.get("coherence_level"),
            "qualified_strategy_match": False,
            "observation_hash": self.observation_hash,
        }


@dataclass(frozen=True)
class StrategyEvaluationResult:
    matches: tuple[StrategyMatch, ...]
    observations: tuple[StrategyObservation, ...]


def _nonempty(value: object) -> bool:
    return bool(str(value or "").strip())


def _event_clock(
    event_time: str, trade_date: str
) -> tuple[datetime, int] | None:
    """Return Shanghai-local time and its continuous A-share trading-second."""

    try:
        parsed = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    local = parsed.astimezone(_SHANGHAI_TIMEZONE)
    if local.strftime("%Y%m%d") != trade_date:
        return None
    clock = local.timetz().replace(tzinfo=None)
    if _MORNING_OPEN <= clock <= _MORNING_CLOSE:
        opened = local.replace(hour=9, minute=30, second=0, microsecond=0)
        coordinate = int((local - opened).total_seconds())
    elif _AFTERNOON_OPEN <= clock <= _AFTERNOON_CLOSE:
        opened = local.replace(hour=13, minute=0, second=0, microsecond=0)
        coordinate = _MORNING_SESSION_SECONDS + int(
            (local - opened).total_seconds()
        )
    else:
        return None
    return local, coordinate


def _evaluation_clock(
    evaluation_time: str, trade_date: str
) -> tuple[datetime, int] | None:
    """Map any aware same-date evaluation instant onto the trading clock."""

    try:
        parsed = datetime.fromisoformat(
            str(evaluation_time).replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    local = parsed.astimezone(_SHANGHAI_TIMEZONE)
    if local.strftime("%Y%m%d") != trade_date:
        return None
    clock = local.timetz().replace(tzinfo=None)
    morning_open = local.replace(hour=9, minute=30, second=0, microsecond=0)
    if clock < _MORNING_OPEN:
        return local, int((local - morning_open).total_seconds())
    if clock <= _MORNING_CLOSE:
        return local, int((local - morning_open).total_seconds())
    if clock < _AFTERNOON_OPEN:
        return local, _MORNING_SESSION_SECONDS
    if clock <= _AFTERNOON_CLOSE:
        afternoon_open = local.replace(
            hour=13, minute=0, second=0, microsecond=0
        )
        return local, _MORNING_SESSION_SECONDS + int(
            (local - afternoon_open).total_seconds()
        )
    return local, _TRADE_DATE_SESSION_SECONDS


def _stock_direction(event: StockSignalEvent) -> str:
    return str(event.signal.get("direction") or "").strip().lower()


def _coherence_level(span_seconds: int) -> str:
    if span_seconds <= 15 * 60:
        return "STRONG"
    if span_seconds <= _QUALIFIED_SPAN_SECONDS:
        return "MEDIUM"
    if span_seconds <= _WEAK_SPAN_SECONDS:
        return "WEAK"
    return "EXPIRED"


def _trading_minutes(span_seconds: int) -> int | float:
    minutes = span_seconds / 60
    return int(minutes) if minutes.is_integer() else round(minutes, 6)


def _stale_at(
    event_time: str, trade_date: str
) -> tuple[str | None, int, bool]:
    local, confirmation_coordinate = _event_clock(event_time, trade_date)
    stale_coordinate = confirmation_coordinate + _QUALIFIED_SPAN_SECONDS
    if stale_coordinate > _TRADE_DATE_SESSION_SECONDS:
        return None, stale_coordinate, False
    if stale_coordinate <= _MORNING_SESSION_SECONDS:
        session_open = local.replace(hour=9, minute=30, second=0, microsecond=0)
        stale_datetime = session_open + timedelta(seconds=stale_coordinate)
    else:
        session_open = local.replace(hour=13, minute=0, second=0, microsecond=0)
        stale_datetime = session_open + timedelta(
            seconds=stale_coordinate - _MORNING_SESSION_SECONDS
        )
    return stale_datetime.isoformat(), stale_coordinate, True


def _valid_identity(asset_kind: str, identity_key: str) -> bool:
    return _nonempty(identity_key) and identity_key.startswith(f"{asset_kind}:")


def _valid_stock_signal(event: StockSignalEvent, trade_date: str) -> bool:
    return (
        event.trade_date == trade_date
        and event.action_state in DISPLAY_ACTION_STATES
        and event.event_type in ("ActionEligible", "ActionExecuted")
        and event.event_type == f"Action{event.action_state.title()}"
        and event.user_signal_projection_id > 0
        and _valid_identity("stock", event.identity_key)
        and _stock_direction(event) in ALLOWED_DIRECTIONS
        and _event_clock(event.event_time, trade_date) is not None
        and all(
            _nonempty(value)
            for value in (
                event.code,
                event.name,
                event.event_id,
                event.event_time,
                event.action_episode_key,
                event.source_run_id,
                event.event_schema_version,
            )
        )
        and bool(event.signal)
    )


def _valid_parent_event(event: ParentExecutedEvent, trade_date: str) -> bool:
    return (
        event.trade_date == trade_date
        and event.asset_kind in ("index", "board")
        and _valid_identity(event.asset_kind, event.identity_key)
        and event.event_type == "ActionExecuted"
        and event.action_state == "executed"
        and event.direction in ALLOWED_DIRECTIONS
        and event.user_signal_projection_id > 0
        and _event_clock(event.event_time, trade_date) is not None
        and all(
            _nonempty(value)
            for value in (
                event.code,
                event.name,
                event.event_id,
                event.event_time,
                event.source_run_id,
                event.event_schema_version,
            )
        )
    )


def _valid_membership(row: MembershipRow, trade_date: str) -> bool:
    if (
        row.trade_date != trade_date
        or not _valid_identity("stock", row.stock_identity_key)
        or row.parent_asset_kind not in ("index", "board")
        or not _valid_identity(row.parent_asset_kind, row.parent_identity_key)
        or not all(
            _nonempty(value)
            for value in (
                row.parent_code,
                row.parent_name,
                row.source_version,
                row.source_batch_id,
            )
        )
    ):
        return False
    if row.parent_asset_kind == "board":
        return row.board_type in ALLOWED_BOARD_TYPES
    return not row.board_type


def _latest_memberships(
    rows: Iterable[MembershipRow],
    *,
    trade_date: str,
    stock_identity_key: str,
    parent_asset_kind: str,
) -> tuple[list[MembershipRow], bool]:
    candidates = [
        row
        for row in rows
        if row.trade_date == trade_date
        and row.stock_identity_key == stock_identity_key
        and row.parent_asset_kind == parent_asset_kind
    ]
    invalid_present = any(not _valid_membership(row, trade_date) for row in candidates)
    latest: dict[tuple[str, str], MembershipRow] = {}
    for row in candidates:
        if not _valid_membership(row, trade_date):
            continue
        key = (row.board_type, row.parent_identity_key)
        current = latest.get(key)
        rank = (row.created_at, row.source_version, row.source_batch_id)
        current_rank = (
            (current.created_at, current.source_version, current.source_batch_id)
            if current is not None
            else ("", "", "")
        )
        if current is None or rank > current_rank:
            latest[key] = row
    return (
        sorted(
            latest.values(),
            key=lambda row: (
                row.board_type,
                row.parent_identity_key,
                row.parent_code,
                row.parent_name,
            ),
        ),
        invalid_present,
    )


def _matching_parent_events(
    membership: MembershipRow,
    parent_events: Sequence[ParentExecutedEvent],
    trade_date: str,
) -> list[ParentExecutedEvent]:
    return sorted(
        {
            event.event_id: event
            for event in parent_events
            if _valid_parent_event(event, trade_date)
            and event.asset_kind == membership.parent_asset_kind
            and event.identity_key == membership.parent_identity_key
            and event.code == membership.parent_code
            and event.name == membership.parent_name
        }.values(),
        key=lambda event: (event.event_time, event.event_id),
    )


def _scope_by_stock(
    scope_rows: Iterable[ScopeRow], trade_date: str
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, set[str]] = {}
    for row in scope_rows:
        if (
            row.trade_date == trade_date
            and _valid_identity("stock", row.stock_identity_key)
            and row.scope_source in ALLOWED_SCOPE_SOURCES
        ):
            grouped.setdefault(row.stock_identity_key, set()).add(row.scope_source)
    return {
        identity_key: tuple(
            source for source in ALLOWED_SCOPE_SOURCES if source in sources
        )
        for identity_key, sources in grouped.items()
    }


def _event_fingerprint(event: StockSignalEvent) -> str:
    return _sha256(
        {
            "projection_id": event.user_signal_projection_id,
            "trade_date": event.trade_date,
            "identity_key": event.identity_key,
            "code": event.code,
            "name": event.name,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "action_state": event.action_state,
            "event_time": event.event_time,
            "episode": event.action_episode_key,
            "source_run_id": event.source_run_id,
            "schema": event.event_schema_version,
            "signal": dict(event.signal),
        }
    )


def _parent_event_fingerprint(event: ParentExecutedEvent) -> str:
    return _sha256(
        {
            "trade_date": event.trade_date,
            "asset_kind": event.asset_kind,
            "identity_key": event.identity_key,
            "code": event.code,
            "name": event.name,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "action_state": event.action_state,
            "event_time": event.event_time,
            "source_run_id": event.source_run_id,
            "event_schema_version": event.event_schema_version,
            "direction": event.direction,
            "user_signal_projection_id": event.user_signal_projection_id,
        }
    )


def _unconflicted_parent_events(
    events: Sequence[ParentExecutedEvent], trade_date: str
) -> tuple[ParentExecutedEvent, ...]:
    fingerprints: dict[str, str] = {}
    valid_by_id: dict[str, ParentExecutedEvent] = {}
    conflicted_ids: set[str] = set()
    for event in events:
        if event.trade_date != trade_date or not _nonempty(event.event_id):
            continue
        fingerprint = _parent_event_fingerprint(event)
        previous = fingerprints.get(event.event_id)
        if previous is not None and previous != fingerprint:
            conflicted_ids.add(event.event_id)
        fingerprints[event.event_id] = fingerprint
        if _valid_parent_event(event, trade_date):
            valid_by_id[event.event_id] = event
    return tuple(
        valid_by_id[event_id]
        for event_id in sorted(valid_by_id)
        if event_id not in conflicted_ids
    )


@dataclass(frozen=True)
class _ConfluenceSelection:
    package: str
    stock_event: StockSignalEvent
    board_row: MembershipRow
    board_event: ParentExecutedEvent
    index_row: MembershipRow | None
    index_event: ParentExecutedEvent | None
    span_seconds: int
    confirmation_time: str
    confirmation_coordinate: int
    projection_arrival_watermark: int
    parent_projection_arrival_watermark: int


def _same_direction_evidence(
    membership: MembershipRow,
    parent_events: Sequence[ParentExecutedEvent],
    *,
    trade_date: str,
    direction: str,
    evaluation_datetime: datetime | None,
    maximum_coordinate: int | None = None,
    maximum_projection_arrival_watermark: int | None = None,
) -> tuple[ParentExecutedEvent, ...]:
    return tuple(
        event
        for event in _matching_parent_events(membership, parent_events, trade_date)
        if event.direction == direction
        and (
            evaluation_datetime is None
            or _event_clock(event.event_time, trade_date)[0] <= evaluation_datetime
        )
        and (
            maximum_coordinate is None
            or _event_clock(event.event_time, trade_date)[1]
            <= maximum_coordinate
        )
        and (
            maximum_projection_arrival_watermark is None
            or event.user_signal_projection_id
            <= maximum_projection_arrival_watermark
        )
    )


def _selection_key(selection: _ConfluenceSelection) -> tuple[object, ...]:
    index_identity = (
        selection.index_row.parent_identity_key
        if selection.index_row is not None
        else ""
    )
    index_event_id = (
        selection.index_event.event_id if selection.index_event is not None else ""
    )
    return (
        selection.projection_arrival_watermark,
        selection.span_seconds,
        selection.confirmation_coordinate,
        selection.stock_event.event_time,
        selection.stock_event.event_id,
        selection.board_row.parent_identity_key,
        selection.board_event.event_time,
        selection.board_event.event_id,
        index_identity,
        selection.index_event.event_time if selection.index_event else "",
        index_event_id,
        selection.package,
    )


def _make_selection(
    *,
    package: str,
    stock_event: StockSignalEvent,
    board_row: MembershipRow,
    board_event: ParentExecutedEvent,
    index_row: MembershipRow | None = None,
    index_event: ParentExecutedEvent | None = None,
) -> _ConfluenceSelection:
    required_events: tuple[StockSignalEvent | ParentExecutedEvent, ...] = tuple(
        event
        for event in (stock_event, board_event, index_event)
        if event is not None
    )
    clocks = [
        _event_clock(event.event_time, stock_event.trade_date)
        for event in required_events
    ]
    coordinates = [clock[1] for clock in clocks if clock is not None]
    latest_event = max(
        required_events,
        key=lambda event: (
            _event_clock(event.event_time, stock_event.trade_date)[1],
            event.event_time,
            event.event_id,
        ),
    )
    return _ConfluenceSelection(
        package=package,
        stock_event=stock_event,
        board_row=board_row,
        board_event=board_event,
        index_row=index_row,
        index_event=index_event,
        span_seconds=max(coordinates) - min(coordinates),
        confirmation_time=latest_event.event_time,
        confirmation_coordinate=max(coordinates),
        projection_arrival_watermark=max(
            event.user_signal_projection_id for event in required_events
        ),
        parent_projection_arrival_watermark=max(
            event.user_signal_projection_id
            for event in (board_event, index_event)
            if event is not None
        ),
    )


def _best_package_selection(
    *,
    package: str,
    stock_events: Sequence[StockSignalEvent],
    board_evidence: Sequence[tuple[MembershipRow, ParentExecutedEvent]],
    index_evidence: Sequence[tuple[MembershipRow, ParentExecutedEvent]],
    maximum_span_seconds: int = _QUALIFIED_SPAN_SECONDS,
    minimum_parent_arrival_watermark: int = 0,
) -> _ConfluenceSelection | None:
    if package == PACKAGE_1:
        combinations = (
            _make_selection(
                package=package,
                stock_event=stock_event,
                board_row=board_item[0],
                board_event=board_item[1],
                index_row=index_item[0],
                index_event=index_item[1],
            )
            for stock_event, board_item, index_item in product(
                stock_events,
                board_evidence,
                index_evidence,
            )
        )
    else:
        combinations = (
            _make_selection(
                package=package,
                stock_event=stock_event,
                board_row=board_row,
                board_event=board_event,
            )
            for stock_event, (board_row, board_event) in product(
                stock_events,
                board_evidence,
            )
        )
    eligible = []
    for selection in combinations:
        if (
            selection.span_seconds > maximum_span_seconds
            or selection.parent_projection_arrival_watermark
            <= minimum_parent_arrival_watermark
        ):
            continue
        eligible.append(selection)
    return min(eligible, key=_selection_key) if eligible else None


def _market_heat(
    *,
    parent_events: Sequence[ParentExecutedEvent],
    trade_date: str,
    stock_direction: str,
    confirmation_coordinate: int,
    maximum_projection_arrival_watermark: int,
) -> tuple[str, tuple[Mapping[str, Any], ...]]:
    evidence: list[Mapping[str, Any]] = []
    relations: list[str | None] = []
    for identity_key in MARKET_HEAT_INDEX_IDENTITIES:
        eligible = [
            event
            for event in parent_events
            if event.asset_kind == "index"
            and event.identity_key == identity_key
            and _event_clock(event.event_time, trade_date)[1]
            <= confirmation_coordinate
            and confirmation_coordinate
            - _event_clock(event.event_time, trade_date)[1]
            <= _QUALIFIED_SPAN_SECONDS
            and event.user_signal_projection_id
            <= maximum_projection_arrival_watermark
        ]
        if not eligible:
            relations.append(None)
            continue
        selected = max(
            eligible,
            key=lambda event: (
                _event_clock(event.event_time, trade_date)[1],
                event.event_time,
                event.event_id,
            ),
        )
        relation = "same" if selected.direction == stock_direction else "opposite"
        relations.append(relation)
        evidence.append(
            {
                "identity_key": selected.identity_key,
                "event_id": selected.event_id,
                "event_time": selected.event_time,
                "direction": selected.direction,
                "relation_to_candidate": relation,
            }
        )
    if relations == ["same", "same"]:
        state = "MARKET_HEAT_SUPPORTIVE"
    elif relations == ["opposite", "opposite"]:
        state = "MARKET_HEAT_ADVERSE"
    elif relations == [None, None]:
        state = "MARKET_HEAT_NEUTRAL"
    else:
        state = "MARKET_HEAT_MIXED"
    return state, tuple(evidence)


def _evaluate_strategy_center(
    *,
    trade_date: str,
    selected_package_keys: Sequence[str],
    stock_signals: Sequence[StockSignalEvent],
    scope_rows: Sequence[ScopeRow],
    index_memberships: Sequence[MembershipRow],
    board_memberships: Sequence[MembershipRow],
    parent_executed_events: Sequence[ParentExecutedEvent],
    membership_authorities: Sequence[MembershipSnapshotAuthority] | None = None,
    evaluation_time: str | None = None,
    maximum_span_seconds: int = _QUALIFIED_SPAN_SECONDS,
    minimum_parent_arrival_watermarks: Mapping[tuple[str, str], int]
    | None = None,
) -> tuple[StrategyMatch, ...]:
    selected = tuple(
        package for package in ALLOWED_PACKAGES if package in selected_package_keys
    )
    if not selected or len(set(selected_package_keys)) != len(selected_package_keys):
        raise ValueError("selected_package_keys must contain one or two unique packages")
    if any(package not in ALLOWED_PACKAGES for package in selected_package_keys):
        raise ValueError("selected_package_keys contains an unknown package")
    if not _nonempty(trade_date):
        raise ValueError("trade_date is required")

    evaluation_datetime: datetime | None = None
    evaluation_coordinate: int | None = None
    if evaluation_time is not None:
        evaluation_clock = _evaluation_clock(evaluation_time, trade_date)
        if evaluation_clock is None:
            raise ValueError(
                "evaluation_time must be an aware timestamp on trade_date"
            )
        evaluation_datetime, evaluation_coordinate = evaluation_clock

    scopes = _scope_by_stock(scope_rows, trade_date)
    authoritative_parent_events = _unconflicted_parent_events(
        parent_executed_events, trade_date
    )
    grouped_signals: dict[tuple[str, str], dict[str, StockSignalEvent]] = {}
    conflicted_groups: set[tuple[str, str]] = set()
    group_directions: dict[tuple[str, str], str] = {}
    fingerprints: dict[tuple[str, str, str], str] = {}
    for event in stock_signals:
        if not _valid_stock_signal(event, trade_date):
            continue
        event_datetime = _event_clock(event.event_time, trade_date)[0]
        if evaluation_datetime is not None and event_datetime > evaluation_datetime:
            continue
        if event.identity_key not in scopes:
            continue
        group_key = (event.identity_key, event.action_episode_key)
        direction = _stock_direction(event)
        previous_direction = group_directions.get(group_key)
        if previous_direction is not None and previous_direction != direction:
            conflicted_groups.add(group_key)
            continue
        group_directions[group_key] = direction
        fingerprint_key = (*group_key, event.event_id)
        fingerprint = _event_fingerprint(event)
        previous = fingerprints.get(fingerprint_key)
        if previous is not None and previous != fingerprint:
            conflicted_groups.add(group_key)
            continue
        fingerprints[fingerprint_key] = fingerprint
        grouped_signals.setdefault(group_key, {})[event.event_id] = event

    results: list[StrategyMatch] = []
    for group_key in sorted(grouped_signals):
        if group_key in conflicted_groups:
            continue
        stock_identity_key, episode_key = group_key
        events = list(grouped_signals[group_key].values())
        requested_dates = {
            source_trade_date_for_event(event) for event in events
        }
        requested_source_trade_date = ""
        membership_provenance: tuple[Mapping[str, Any], ...] = ()
        selected_dates: dict[str, str] = {}
        authority_by_kind: dict[str, MembershipSnapshotAuthority] = {}
        if membership_authorities is None:
            continue
        if len(requested_dates) != 1 or None in requested_dates:
            continue
        requested_source_trade_date = str(next(iter(requested_dates)))
        authorities = [
            authority
            for authority in membership_authorities
            if authority.stock_identity_key == stock_identity_key
            and authority.action_episode_key == episode_key
            and authority.requested_source_trade_date
            == requested_source_trade_date
        ]
        authority_by_kind = {
            authority.membership_kind: authority for authority in authorities
        }
        if (
            set(authority_by_kind) != {"index", "board"}
            or len(authorities) != 2
            or any(
                authority.quality_status != "passed"
                or authority.provenance_status != "authoritative_as_of"
                or not _nonempty(authority.selected_membership_trade_date)
                or not _nonempty(authority.source_version)
                or not _nonempty(authority.source_batch_id)
                for authority in authorities
            )
        ):
            continue
        selected_dates = {
            kind: authority.selected_membership_trade_date
            for kind, authority in authority_by_kind.items()
        }
        membership_provenance = tuple(
            {
                "requested_source_trade_date": authority.requested_source_trade_date,
                "selected_membership_trade_date": authority.selected_membership_trade_date,
                "source_version": authority.source_version,
                "source_batch_id": authority.source_batch_id,
                "membership_kind": authority.membership_kind,
                "provenance_status": authority.provenance_status,
                "quality_status": authority.quality_status,
            }
            for authority in sorted(
                authorities, key=lambda item: item.membership_kind
            )
        )

        index_rows, invalid_index = _latest_memberships(
            index_memberships,
            trade_date=selected_dates["index"],
            stock_identity_key=stock_identity_key,
            parent_asset_kind="index",
        )
        board_rows, invalid_board = _latest_memberships(
            board_memberships,
            trade_date=selected_dates["board"],
            stock_identity_key=stock_identity_key,
            parent_asset_kind="board",
        )
        if invalid_index or invalid_board:
            continue

        index_rows = [
            row
            for row in index_rows
            if row.parent_identity_key in MEMBERSHIP_INDEX_IDENTITIES
        ]
        if any(
            row.source_version != authority_by_kind["index"].source_version
            or row.source_batch_id
            != authority_by_kind["index"].source_batch_id
            for row in index_rows
        ) or any(
            row.source_version != authority_by_kind["board"].source_version
            or row.source_batch_id
            != authority_by_kind["board"].source_batch_id
            for row in board_rows
        ):
            continue
        direction = group_directions[group_key]
        minimum_parent_arrival_watermark = int(
            (minimum_parent_arrival_watermarks or {}).get(group_key, 0)
        )
        board_evidence = [
            (row, event)
            for row in board_rows
            for event in _same_direction_evidence(
                row,
                authoritative_parent_events,
                trade_date=trade_date,
                direction=direction,
                evaluation_datetime=evaluation_datetime,
            )
        ]
        index_evidence = [
            (row, event)
            for row in index_rows
            for event in _same_direction_evidence(
                row,
                authoritative_parent_events,
                trade_date=trade_date,
                direction=direction,
                evaluation_datetime=evaluation_datetime,
            )
        ]
        selections = tuple(
            selection
            for package in selected
            for selection in (
                _best_package_selection(
                    package=package,
                    stock_events=events,
                    board_evidence=board_evidence,
                    index_evidence=index_evidence,
                    maximum_span_seconds=maximum_span_seconds,
                    minimum_parent_arrival_watermark=(
                        minimum_parent_arrival_watermark
                    ),
                ),
            )
            if selection is not None
        )
        if not selections:
            continue

        earliest_confirmation_coordinate = min(
            selection.confirmation_coordinate for selection in selections
        )
        selections = tuple(
            selection
            for selection in selections
            if selection.confirmation_coordinate
            == earliest_confirmation_coordinate
        )
        matched_packages = [selection.package for selection in selections]
        primary_selection = min(selections, key=_selection_key)
        frozen_confirmation = max(
            selections,
            key=lambda selection: (
                selection.confirmation_coordinate,
                selection.confirmation_time,
                selection.package,
            ),
        )
        frozen_stock_evidence = {
            selection.stock_event.event_id: selection.stock_event
            for selection in selections
        }
        current = max(
            events,
            key=lambda event: (
                event.action_state == "executed",
                _event_clock(event.event_time, trade_date)[1],
                event.event_time,
                event.event_id,
                event.user_signal_projection_id,
            ),
        )
        timeline = tuple(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "action_state": event.action_state,
                "event_time": event.event_time,
                "source_signal_projection_id": event.user_signal_projection_id,
            }
            for event in sorted(
                events,
                key=lambda item: (item.event_time, item.event_id),
            )
        )
        market_heat_state, market_heat_evidence = _market_heat(
            parent_events=authoritative_parent_events,
            trade_date=trade_date,
            stock_direction=direction,
            confirmation_coordinate=frozen_confirmation.confirmation_coordinate,
            maximum_projection_arrival_watermark=max(
                selection.projection_arrival_watermark
                for selection in selections
            ),
        )

        evidence_event_ids: set[str] = {event.event_id for event in events}
        for selection in selections:
            evidence_event_ids.add(selection.board_event.event_id)
            if selection.index_event is not None:
                evidence_event_ids.add(selection.index_event.event_id)
        evidence_event_ids.update(
            str(item["event_id"]) for item in market_heat_evidence
        )

        selected_index_events: dict[str, set[str]] = {}
        selected_board_events: dict[str, set[str]] = {}
        for selection in selections:
            selected_board_events.setdefault(
                selection.board_row.parent_identity_key, set()
            ).add(selection.board_event.event_id)
            if selection.index_row is not None and selection.index_event is not None:
                selected_index_events.setdefault(
                    selection.index_row.parent_identity_key, set()
                ).add(selection.index_event.event_id)

        indices: list[dict[str, Any]] = []
        for row in index_rows:
            evidence = _same_direction_evidence(
                row,
                authoritative_parent_events,
                trade_date=trade_date,
                direction=direction,
                evaluation_datetime=evaluation_datetime,
                maximum_coordinate=frozen_confirmation.confirmation_coordinate,
                maximum_projection_arrival_watermark=max(
                    selection.projection_arrival_watermark
                    for selection in selections
                ),
            )
            indices.append(
                {
                    "identity_key": row.parent_identity_key,
                    "code": row.parent_code,
                    "name": row.parent_name,
                    "executed_today": bool(evidence),
                    "executed_event_ids": [event.event_id for event in evidence],
                    "selected_for_confluence": (
                        row.parent_identity_key in selected_index_events
                    ),
                    "selected_event_ids": sorted(
                        selected_index_events.get(row.parent_identity_key, set())
                    ),
                    "membership_source_version": row.source_version,
                    "membership_source_batch_id": row.source_batch_id,
                    "membership_kind": "index",
                    "requested_source_trade_date": requested_source_trade_date,
                    "selected_membership_trade_date": selected_dates["index"],
                    "membership_provenance_status": (
                        authority_by_kind["index"].provenance_status
                    ),
                    "membership_quality_status": (
                        authority_by_kind["index"].quality_status
                    ),
                }
            )

        matched_boards: list[dict[str, Any]] = []
        for row in board_rows:
            selected_event_ids = selected_board_events.get(row.parent_identity_key)
            if not selected_event_ids:
                continue
            matched_boards.append(
                {
                    "identity_key": row.parent_identity_key,
                    "code": row.parent_code,
                    "name": row.parent_name,
                    "board_type": row.board_type,
                    "executed_event_ids": sorted(selected_event_ids),
                    "membership_source_version": row.source_version,
                    "membership_source_batch_id": row.source_batch_id,
                    "membership_kind": "board",
                    "requested_source_trade_date": requested_source_trade_date,
                    "selected_membership_trade_date": selected_dates["board"],
                    "membership_provenance_status": (
                        authority_by_kind["board"].provenance_status
                    ),
                    "membership_quality_status": (
                        authority_by_kind["board"].quality_status
                    ),
                }
            )

        if not index_rows:
            mapping_quality = "missing_index"
        else:
            mapping_quality = "passed"

        membership_source_trade_date = max(selected_dates.values())

        package_evidence = [
            {
                "package": selection.package,
                "coherence_level": _coherence_level(selection.span_seconds),
                "coherence_span_trading_minutes": _trading_minutes(
                    selection.span_seconds
                ),
                "confirmation_time": selection.confirmation_time,
                "stock_event_id": selection.stock_event.event_id,
                "stock_event_time": selection.stock_event.event_time,
                "board_identity_key": selection.board_row.parent_identity_key,
                "board_event_id": selection.board_event.event_id,
                "board_event_time": selection.board_event.event_time,
                "board_projection_arrival_watermark": (
                    selection.board_event.user_signal_projection_id
                ),
                "index_identity_key": (
                    selection.index_row.parent_identity_key
                    if selection.index_row is not None
                    else None
                ),
                "index_event_id": (
                    selection.index_event.event_id
                    if selection.index_event is not None
                    else None
                ),
                "index_event_time": (
                    selection.index_event.event_time
                    if selection.index_event is not None
                    else None
                ),
                "index_projection_arrival_watermark": (
                    selection.index_event.user_signal_projection_id
                    if selection.index_event is not None
                    else None
                ),
                "projection_arrival_watermark": (
                    selection.projection_arrival_watermark
                ),
                "parent_projection_arrival_watermark": (
                    selection.parent_projection_arrival_watermark
                ),
            }
            for selection in selections
        ]
        stale_at, stale_coordinate, stale_at_same_trade_date = _stale_at(
            frozen_confirmation.confirmation_time,
            trade_date,
        )
        confluence_audit = {
            "strategy_version": STRATEGY_VERSION_V2,
            "evaluator_policy_version": _V2_EVALUATOR_POLICY["version"],
            "evaluator_policy_hash": V2_EVALUATOR_POLICY_HASH,
            "display_only": True,
            "shadow_only": True,
            "direction": direction,
            "time_basis": "a_share_trading_minutes",
            "exclude_midday_break": True,
            "event_selection": "first_confirmation_then_minimum_span",
            "lookahead_allowed": False,
            "cross_trade_date_allowed": False,
            "coherence_level": _coherence_level(
                primary_selection.span_seconds
            ),
            "coherence_span_trading_minutes": _trading_minutes(
                primary_selection.span_seconds
            ),
            "confirmation_time": frozen_confirmation.confirmation_time,
            "confirmation_trading_second_coordinate": (
                frozen_confirmation.confirmation_coordinate
            ),
            "candidate_stale_after_trading_minutes": 30,
            "stale_at": stale_at,
            "stale_at_trading_second_coordinate": stale_coordinate,
            "stale_at_same_trade_date": stale_at_same_trade_date,
            "weak_policy": "display_only_not_qualified",
            "package_evidence": package_evidence,
            "market_heat_state": market_heat_state,
            "market_heat_rank": _MARKET_HEAT_RANK[market_heat_state],
            "market_heat_evidence": [dict(item) for item in market_heat_evidence],
            "market_heat_creates_candidate": False,
            "projection_arrival_watermark": max(
                selection.projection_arrival_watermark
                for selection in selections
            ),
            "parent_projection_arrival_watermark": max(
                selection.parent_projection_arrival_watermark
                for selection in selections
            ),
            "stock_confluence_event_ids": sorted(frozen_stock_evidence),
            "membership_index_allowlist": list(MEMBERSHIP_INDEX_IDENTITIES),
            "requested_source_trade_date": requested_source_trade_date,
            "membership_source_trade_date": membership_source_trade_date,
            "membership_provenance": [
                dict(item) for item in membership_provenance
            ],
            "proposal_authorized": False,
            "order_authorized": False,
            "trade_authorized": False,
            "position_or_cash_mutation_authorized": False,
            "autonomous_trading_authorized": False,
            "real_trading_authorized": False,
        }
        evaluation_age_seconds = (
            max(0, evaluation_coordinate - frozen_confirmation.confirmation_coordinate)
            if evaluation_coordinate is not None
            else 0
        )
        coherence_level = str(confluence_audit["coherence_level"])
        freshness_status = (
            "stale"
            if coherence_level in {"STRONG", "MEDIUM"}
            and evaluation_age_seconds > _QUALIFIED_SPAN_SECONDS
            else "fresh"
        )
        confluence_audit.update(
            {
                "freshness_status": freshness_status,
                "qualification_status": (
                    "qualified"
                    if coherence_level in {"STRONG", "MEDIUM"}
                    and freshness_status == "fresh"
                    else "observation"
                ),
            }
        )
        coherence_episode_key = "coherence:" + _sha256(
            {
                "strategy_version": STRATEGY_VERSION_V2,
                "trade_date": trade_date,
                "stock_identity_key": stock_identity_key,
                "action_episode_key": episode_key,
                "direction": direction,
                "confirmation_coordinate": (
                    frozen_confirmation.confirmation_coordinate
                ),
                "package_evidence": package_evidence,
            }
        )[:32]
        signal_payload = dict(current.signal)

        payload_without_hash = {
            "trade_date": trade_date,
            "stock_identity_key": stock_identity_key,
            "action_episode_key": episode_key,
            "coherence_episode_key": coherence_episode_key,
            "action_state": current.action_state,
            "source_signal_projection_id": current.user_signal_projection_id,
            "source_event_ids": sorted(evidence_event_ids),
            "matched_packages": matched_packages,
            "scope_sources": list(scopes[stock_identity_key]),
            "indices": indices,
            "matched_boards": matched_boards,
            "signal": signal_payload,
            "confluence": confluence_audit,
            "state_timeline": list(timeline),
            "mapping_quality": mapping_quality,
            "requested_source_trade_date": requested_source_trade_date,
            "membership_source_trade_date": membership_source_trade_date,
            "membership_provenance": list(membership_provenance),
            "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
        }
        results.append(
            StrategyMatch(
                trade_date=trade_date,
                stock_identity_key=stock_identity_key,
                action_episode_key=episode_key,
                coherence_episode_key=coherence_episode_key,
                action_state=current.action_state,
                source_signal_projection_id=current.user_signal_projection_id,
                source_event_ids=tuple(sorted(evidence_event_ids)),
                matched_packages=tuple(matched_packages),
                scope_sources=scopes[stock_identity_key],
                indices=tuple(indices),
                matched_boards=tuple(matched_boards),
                signal=signal_payload,
                confluence=confluence_audit,
                state_timeline=timeline,
                mapping_quality=mapping_quality,
                requested_source_trade_date=requested_source_trade_date,
                membership_source_trade_date=membership_source_trade_date,
                membership_provenance=membership_provenance,
                evaluator_policy_hash=EVALUATOR_POLICY_HASH,
                projection_hash=_sha256(payload_without_hash),
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda match: (
                _MARKET_HEAT_RANK[
                    match.confluence["market_heat_state"]
                ],
                match.stock_identity_key,
                match.action_episode_key,
                match.projection_hash,
            ),
        )
    )


def _match_hash_payload(match: StrategyMatch) -> dict[str, Any]:
    payload = match.as_payload()
    payload.pop("surface_kind", None)
    payload.pop("projection_hash", None)
    return payload


def _merge_same_confirmation_candidates(
    candidates: Sequence[StrategyMatch],
) -> tuple[StrategyMatch, ...]:
    grouped: dict[tuple[object, ...], list[StrategyMatch]] = {}
    for candidate in candidates:
        grouped.setdefault(
            (
                candidate.trade_date,
                candidate.stock_identity_key,
                candidate.action_episode_key,
                candidate.confluence.get("direction"),
                candidate.confluence.get(
                    "confirmation_trading_second_coordinate"
                ),
                candidate.confluence.get(
                    "projection_arrival_watermark"
                ),
            ),
            [],
        ).append(candidate)

    merged: list[StrategyMatch] = []
    for group_key in sorted(grouped, key=lambda value: tuple(map(str, value))):
        items = grouped[group_key]
        base = min(
            items,
            key=lambda item: (
                float(item.confluence["coherence_span_trading_minutes"]),
                item.projection_hash,
            ),
        )
        all_packages = tuple(
            package
            for package in ALLOWED_PACKAGES
            if any(package in item.matched_packages for item in items)
        )
        package_evidence_by_package = {
            str(evidence["package"]): dict(evidence)
            for item in items
            for evidence in item.confluence.get("package_evidence", [])
        }
        package_evidence = [
            package_evidence_by_package[package]
            for package in all_packages
            if package in package_evidence_by_package
        ]
        qualified_packages = tuple(
            package
            for package in all_packages
            if package_evidence_by_package[package]["coherence_level"]
            in {"STRONG", "MEDIUM"}
        )
        surface_packages = qualified_packages or all_packages
        surface_evidence = [
            package_evidence_by_package[package]
            for package in surface_packages
        ]
        surface_span_minutes = min(
            float(evidence["coherence_span_trading_minutes"])
            for evidence in surface_evidence
        )
        surface_span_seconds = round(surface_span_minutes * 60)
        confluence = {
            **dict(base.confluence),
            "coherence_level": _coherence_level(surface_span_seconds),
            "coherence_span_trading_minutes": _trading_minutes(
                surface_span_seconds
            ),
            "package_evidence": package_evidence,
            "qualified_packages": list(qualified_packages),
            "observation_packages": [
                package
                for package in all_packages
                if package not in qualified_packages
            ],
        }
        confluence["freshness_status"] = (
            "stale"
            if confluence["coherence_level"] in {"STRONG", "MEDIUM"}
            and any(
                item.confluence.get("freshness_status") == "stale"
                for item in items
            )
            else "fresh"
        )
        confluence["qualification_status"] = (
            "qualified"
            if confluence["coherence_level"] in {"STRONG", "MEDIUM"}
            and confluence["freshness_status"] == "fresh"
            else "observation"
        )
        confluence["projection_arrival_watermark"] = max(
            int(item.confluence["projection_arrival_watermark"])
            for item in items
        )
        confluence["parent_projection_arrival_watermark"] = max(
            int(item.confluence["parent_projection_arrival_watermark"])
            for item in items
        )
        coherence_episode_key = "coherence:" + _sha256(
            {
                "strategy_version": STRATEGY_VERSION_V2,
                "trade_date": base.trade_date,
                "stock_identity_key": base.stock_identity_key,
                "action_episode_key": base.action_episode_key,
                "direction": confluence["direction"],
                "confirmation_coordinate": confluence[
                    "confirmation_trading_second_coordinate"
                ],
                "package_evidence": package_evidence,
            }
        )[:32]
        index_by_identity: dict[str, dict[str, Any]] = {}
        for item in items:
            for index in item.indices:
                identity_key = str(index["identity_key"])
                current = index_by_identity.setdefault(identity_key, dict(index))
                current["executed_today"] = bool(
                    current.get("executed_today") or index.get("executed_today")
                )
                current["selected_for_confluence"] = bool(
                    current.get("selected_for_confluence")
                    or index.get("selected_for_confluence")
                )
                for field in ("executed_event_ids", "selected_event_ids"):
                    current[field] = sorted(
                        {
                            *(current.get(field) or []),
                            *(index.get(field) or []),
                        }
                    )
        board_by_identity: dict[str, dict[str, Any]] = {}
        for item in items:
            for board in item.matched_boards:
                identity_key = str(board["identity_key"])
                current = board_by_identity.setdefault(identity_key, dict(board))
                current["executed_event_ids"] = sorted(
                    {
                        *(current.get("executed_event_ids") or []),
                        *(board.get("executed_event_ids") or []),
                    }
                )
        provisional = replace(
            base,
            coherence_episode_key=coherence_episode_key,
            source_event_ids=tuple(
                sorted(
                    {
                        event_id
                        for item in items
                        for event_id in item.source_event_ids
                    }
                )
            ),
            matched_packages=surface_packages,
            indices=tuple(
                index_by_identity[key] for key in sorted(index_by_identity)
            ),
            matched_boards=tuple(
                board_by_identity[key] for key in sorted(board_by_identity)
            ),
            confluence=confluence,
            projection_hash="",
        )
        merged.append(
            replace(
                provisional,
                projection_hash=_sha256(_match_hash_payload(provisional)),
            )
        )
    merged_rows = tuple(
        sorted(
            merged,
            key=lambda match: (
                _MARKET_HEAT_RANK[match.confluence["market_heat_state"]],
                match.stock_identity_key,
                match.action_episode_key,
                int(
                    match.confluence[
                        "confirmation_trading_second_coordinate"
                    ]
                ),
                match.coherence_episode_key,
            ),
        )
    )
    next_watermark_by_group: dict[tuple[str, str], int] = {}
    for match in merged_rows:
        group_key = (match.stock_identity_key, match.action_episode_key)
        watermark = int(
            match.confluence["projection_arrival_watermark"]
        )
        current = next_watermark_by_group.get(group_key)
        if current is None or watermark < current:
            next_watermark_by_group[group_key] = watermark
    return tuple(
        match
        for match in merged_rows
        if int(match.confluence["projection_arrival_watermark"])
        == next_watermark_by_group[
            (match.stock_identity_key, match.action_episode_key)
        ]
    )


def _evaluate_v2_package_confirmations(
    *,
    maximum_span_seconds: int,
    trade_date: str,
    selected_package_keys: Sequence[str],
    stock_signals: Sequence[StockSignalEvent],
    scope_rows: Sequence[ScopeRow],
    index_memberships: Sequence[MembershipRow],
    board_memberships: Sequence[MembershipRow],
    parent_executed_events: Sequence[ParentExecutedEvent],
    membership_authorities: Sequence[MembershipSnapshotAuthority] | None,
    evaluation_time: str | None,
    minimum_parent_arrival_watermarks: Mapping[tuple[str, str], int]
    | None = None,
) -> tuple[StrategyMatch, ...]:
    selected = tuple(
        package for package in ALLOWED_PACKAGES if package in selected_package_keys
    )
    if not selected or len(set(selected_package_keys)) != len(selected_package_keys):
        raise ValueError("selected_package_keys must contain one or two unique packages")
    if any(package not in ALLOWED_PACKAGES for package in selected_package_keys):
        raise ValueError("selected_package_keys contains an unknown package")
    candidates = tuple(
        candidate
        for package in selected
        for candidate in _evaluate_strategy_center(
            trade_date=trade_date,
            selected_package_keys=(package,),
            stock_signals=stock_signals,
            scope_rows=scope_rows,
            index_memberships=index_memberships,
            board_memberships=board_memberships,
            parent_executed_events=parent_executed_events,
            membership_authorities=membership_authorities,
            evaluation_time=evaluation_time,
            maximum_span_seconds=maximum_span_seconds,
            minimum_parent_arrival_watermarks=(
                minimum_parent_arrival_watermarks
            ),
        )
    )
    return _merge_same_confirmation_candidates(candidates)


def _candidate_from_observation(
    observation: StrategyObservation,
) -> StrategyMatch:
    provisional = StrategyMatch(
        trade_date=observation.trade_date,
        stock_identity_key=observation.stock_identity_key,
        action_episode_key=observation.action_episode_key,
        coherence_episode_key=observation.coherence_episode_key,
        action_state=observation.action_state,
        source_signal_projection_id=observation.source_signal_projection_id,
        source_event_ids=observation.source_event_ids,
        matched_packages=observation.observed_packages,
        scope_sources=observation.scope_sources,
        indices=observation.indices,
        matched_boards=observation.observed_boards,
        signal=observation.signal,
        confluence=observation.confluence,
        state_timeline=observation.state_timeline,
        mapping_quality=observation.mapping_quality,
        requested_source_trade_date=observation.requested_source_trade_date,
        membership_source_trade_date=(
            observation.membership_source_trade_date
        ),
        membership_provenance=observation.membership_provenance,
        evaluator_policy_hash=observation.evaluator_policy_hash,
        projection_hash="",
    )
    return replace(
        provisional,
        projection_hash=_sha256(_match_hash_payload(provisional)),
    )


def _refresh_frozen_candidate(
    candidate: StrategyMatch,
    *,
    trade_date: str,
    stock_signals: Sequence[StockSignalEvent],
    scope_sources: tuple[str, ...],
    evaluation_coordinate: int | None,
    evaluation_datetime: datetime | None,
) -> StrategyMatch | None:
    if (
        candidate.trade_date != trade_date
        or candidate.confluence.get("strategy_version")
        != STRATEGY_VERSION_V2
        or candidate.evaluator_policy_hash != V2_EVALUATOR_POLICY_HASH
        or candidate.confluence.get("evaluator_policy_hash")
        != V2_EVALUATOR_POLICY_HASH
        or not candidate.coherence_episode_key
    ):
        raise ValueError("frozen_coherence_episode_authority_invalid")
    if not scope_sources:
        return None
    direction = str(candidate.confluence.get("direction") or "")
    parent_watermark = candidate.confluence.get(
        "parent_projection_arrival_watermark"
    )
    if (
        direction not in ALLOWED_DIRECTIONS
        or isinstance(parent_watermark, bool)
        or not isinstance(parent_watermark, int)
        or parent_watermark <= 0
    ):
        raise ValueError("frozen_coherence_episode_authority_invalid")

    events_by_id: dict[str, StockSignalEvent] = {}
    fingerprints: dict[str, str] = {}
    for event in stock_signals:
        if (
            event.identity_key != candidate.stock_identity_key
            or event.action_episode_key != candidate.action_episode_key
            or not _valid_stock_signal(event, trade_date)
            or _stock_direction(event) != direction
        ):
            continue
        event_datetime = _event_clock(event.event_time, trade_date)[0]
        if (
            evaluation_datetime is not None
            and event_datetime > evaluation_datetime
        ):
            continue
        fingerprint = _event_fingerprint(event)
        previous = fingerprints.get(event.event_id)
        if previous is not None and previous != fingerprint:
            raise ValueError("frozen_stock_episode_authority_conflict")
        fingerprints[event.event_id] = fingerprint
        events_by_id[event.event_id] = event
    if not events_by_id:
        return None

    current_events = tuple(events_by_id.values())
    current = max(
        current_events,
        key=lambda event: (
            event.action_state == "executed",
            _event_clock(event.event_time, trade_date)[1],
            event.event_time,
            event.event_id,
            event.user_signal_projection_id,
        ),
    )
    retain_frozen_executed = (
        candidate.action_state == "executed"
        and current.action_state != "executed"
    )
    timeline_by_id = {
        str(item["event_id"]): dict(item)
        for item in candidate.state_timeline
        if _nonempty(item.get("event_id"))
    }
    timeline_by_id.update(
        {
            event.event_id: {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "action_state": event.action_state,
                "event_time": event.event_time,
                "source_signal_projection_id": (
                    event.user_signal_projection_id
                ),
            }
            for event in current_events
        }
    )
    timeline = tuple(
        sorted(
            timeline_by_id.values(),
            key=lambda item: (
                str(item.get("event_time") or ""),
                str(item.get("event_id") or ""),
            ),
        )
    )

    confluence = dict(candidate.confluence)
    confirmation_coordinate = int(
        confluence["confirmation_trading_second_coordinate"]
    )
    evaluation_age_seconds = (
        max(0, evaluation_coordinate - confirmation_coordinate)
        if evaluation_coordinate is not None
        else 0
    )
    coherence_level = str(confluence["coherence_level"])
    freshness_status = (
        "stale"
        if (
            confluence.get("freshness_status") == "stale"
            or (
                coherence_level in {"STRONG", "MEDIUM"}
                and evaluation_age_seconds > _QUALIFIED_SPAN_SECONDS
            )
        )
        else "fresh"
    )
    confluence.update(
        {
            "freshness_status": freshness_status,
            "qualification_status": (
                "qualified"
                if coherence_level in {"STRONG", "MEDIUM"}
                and freshness_status == "fresh"
                else "observation"
            ),
        }
    )
    chosen_signal = (
        dict(candidate.signal)
        if retain_frozen_executed
        else dict(current.signal)
    )
    chosen_action_state = (
        candidate.action_state
        if retain_frozen_executed
        else current.action_state
    )
    chosen_projection_id = (
        candidate.source_signal_projection_id
        if retain_frozen_executed
        else current.user_signal_projection_id
    )
    provisional = replace(
        candidate,
        action_state=chosen_action_state,
        source_signal_projection_id=chosen_projection_id,
        source_event_ids=tuple(
            sorted(
                {
                    *candidate.source_event_ids,
                    *(event.event_id for event in current_events),
                }
            )
        ),
        scope_sources=scope_sources,
        signal=chosen_signal,
        confluence=confluence,
        state_timeline=timeline,
        projection_hash="",
    )
    return replace(
        provisional,
        projection_hash=_sha256(_match_hash_payload(provisional)),
    )


def _evaluate_v2_surfaces(
    *,
    trade_date: str,
    selected_package_keys: Sequence[str],
    stock_signals: Sequence[StockSignalEvent],
    scope_rows: Sequence[ScopeRow],
    index_memberships: Sequence[MembershipRow],
    board_memberships: Sequence[MembershipRow],
    parent_executed_events: Sequence[ParentExecutedEvent],
    membership_authorities: Sequence[MembershipSnapshotAuthority] | None,
    evaluation_time: str | None,
    frozen_matches: Sequence[StrategyMatch] = (),
    frozen_observations: Sequence[StrategyObservation] = (),
) -> StrategyEvaluationResult:
    evaluation_datetime: datetime | None = None
    evaluation_coordinate: int | None = None
    if evaluation_time is not None:
        evaluation_clock = _evaluation_clock(evaluation_time, trade_date)
        if evaluation_clock is None:
            raise ValueError(
                "evaluation_time must be an aware timestamp on trade_date"
            )
        evaluation_datetime, evaluation_coordinate = evaluation_clock
    scopes = _scope_by_stock(scope_rows, trade_date)

    frozen_candidates = [
        *frozen_matches,
        *(
            _candidate_from_observation(observation)
            for observation in frozen_observations
        ),
    ]
    frozen_keys: set[tuple[str, str, str]] = set()
    refreshed: list[StrategyMatch] = []
    parent_watermarks: dict[tuple[str, str], int] = {}
    for frozen in frozen_candidates:
        key = (
            frozen.stock_identity_key,
            frozen.action_episode_key,
            frozen.coherence_episode_key,
        )
        if key in frozen_keys:
            raise ValueError("frozen_coherence_surface_overlap")
        frozen_keys.add(key)
        group_key = (frozen.stock_identity_key, frozen.action_episode_key)
        refreshed_candidate = _refresh_frozen_candidate(
            frozen,
            trade_date=trade_date,
            stock_signals=stock_signals,
            scope_sources=scopes.get(frozen.stock_identity_key, ()),
            evaluation_coordinate=evaluation_coordinate,
            evaluation_datetime=evaluation_datetime,
        )
        if refreshed_candidate is None:
            continue
        refreshed.append(refreshed_candidate)
        parent_watermarks[group_key] = max(
            parent_watermarks.get(group_key, 0),
            int(
                refreshed_candidate.confluence[
                    "parent_projection_arrival_watermark"
                ]
            ),
        )

    new_candidates: list[StrategyMatch] = []
    maximum_iterations = max(1, len(parent_executed_events) + 1)
    for _ in range(maximum_iterations):
        batch = _evaluate_v2_package_confirmations(
            maximum_span_seconds=_WEAK_SPAN_SECONDS,
            trade_date=trade_date,
            selected_package_keys=selected_package_keys,
            stock_signals=stock_signals,
            scope_rows=scope_rows,
            index_memberships=index_memberships,
            board_memberships=board_memberships,
            parent_executed_events=parent_executed_events,
            membership_authorities=membership_authorities,
            evaluation_time=evaluation_time,
            minimum_parent_arrival_watermarks=parent_watermarks,
        )
        if not batch:
            break
        progressed = False
        prior_watermarks = dict(parent_watermarks)
        batch_watermarks = dict(parent_watermarks)
        for candidate in batch:
            key = (
                candidate.stock_identity_key,
                candidate.action_episode_key,
                candidate.coherence_episode_key,
            )
            group_key = (
                candidate.stock_identity_key,
                candidate.action_episode_key,
            )
            next_watermark = int(
                candidate.confluence[
                    "parent_projection_arrival_watermark"
                ]
            )
            if next_watermark <= prior_watermarks.get(group_key, 0):
                continue
            batch_watermarks[group_key] = max(
                batch_watermarks.get(group_key, 0),
                next_watermark,
            )
            if key not in frozen_keys:
                frozen_keys.add(key)
                new_candidates.append(candidate)
            progressed = True
        parent_watermarks = batch_watermarks
        if not progressed:
            break

    candidates = tuple((*refreshed, *new_candidates))
    matches: list[StrategyMatch] = []
    observations: list[StrategyObservation] = []
    surface_keys: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (
            candidate.stock_identity_key,
            candidate.action_episode_key,
            candidate.coherence_episode_key,
        )
        if key in surface_keys:
            raise ValueError("coherence_episode_surface_overlap")
        surface_keys.add(key)
        level = candidate.confluence.get("coherence_level")
        freshness = candidate.confluence.get("freshness_status")
        if level in {"STRONG", "MEDIUM"} and freshness == "fresh":
            matches.append(candidate)
        elif level == "WEAK":
            observations.append(
                StrategyObservation.from_candidate(
                    candidate, observation_reason="weak_span"
                )
            )
        elif level in {"STRONG", "MEDIUM"} and freshness == "stale":
            observations.append(
                StrategyObservation.from_candidate(
                    candidate,
                    observation_reason="stale_after_confirmation",
                )
            )
    return StrategyEvaluationResult(
        matches=tuple(matches),
        observations=tuple(observations),
    )


def evaluate_strategy_center(
    *,
    trade_date: str,
    selected_package_keys: Sequence[str],
    stock_signals: Sequence[StockSignalEvent],
    scope_rows: Sequence[ScopeRow],
    index_memberships: Sequence[MembershipRow],
    board_memberships: Sequence[MembershipRow],
    parent_executed_events: Sequence[ParentExecutedEvent],
    membership_authorities: Sequence[MembershipSnapshotAuthority] | None = None,
    evaluation_time: str | None = None,
    frozen_matches: Sequence[StrategyMatch] = (),
    frozen_observations: Sequence[StrategyObservation] = (),
) -> tuple[StrategyMatch, ...]:
    """Return qualified STRONG/MEDIUM matches only."""

    return _evaluate_v2_surfaces(
        trade_date=trade_date,
        selected_package_keys=selected_package_keys,
        stock_signals=stock_signals,
        scope_rows=scope_rows,
        index_memberships=index_memberships,
        board_memberships=board_memberships,
        parent_executed_events=parent_executed_events,
        membership_authorities=membership_authorities,
        evaluation_time=evaluation_time,
        frozen_matches=frozen_matches,
        frozen_observations=frozen_observations,
    ).matches


def evaluate_strategy_center_observations(
    *,
    trade_date: str,
    selected_package_keys: Sequence[str],
    stock_signals: Sequence[StockSignalEvent],
    scope_rows: Sequence[ScopeRow],
    index_memberships: Sequence[MembershipRow],
    board_memberships: Sequence[MembershipRow],
    parent_executed_events: Sequence[ParentExecutedEvent],
    membership_authorities: Sequence[MembershipSnapshotAuthority] | None = None,
    evaluation_time: str | None = None,
    frozen_matches: Sequence[StrategyMatch] = (),
    frozen_observations: Sequence[StrategyObservation] = (),
) -> tuple[StrategyObservation, ...]:
    """Return WEAK and stale display-only observations through trade close."""

    return _evaluate_v2_surfaces(
        trade_date=trade_date,
        selected_package_keys=selected_package_keys,
        stock_signals=stock_signals,
        scope_rows=scope_rows,
        index_memberships=index_memberships,
        board_memberships=board_memberships,
        parent_executed_events=parent_executed_events,
        membership_authorities=membership_authorities,
        evaluation_time=evaluation_time,
        frozen_matches=frozen_matches,
        frozen_observations=frozen_observations,
    ).observations


def _valid_stock_signal_v1(event: StockSignalEvent, trade_date: str) -> bool:
    return (
        event.trade_date == trade_date
        and event.action_state in DISPLAY_ACTION_STATES
        and event.event_type == f"Action{event.action_state.title()}"
        and event.user_signal_projection_id > 0
        and _valid_identity("stock", event.identity_key)
        and all(
            _nonempty(value)
            for value in (
                event.code,
                event.name,
                event.event_id,
                event.event_time,
                event.action_episode_key,
                event.source_run_id,
                event.event_schema_version,
            )
        )
        and bool(event.signal)
    )


def _valid_parent_event_v1(
    event: ParentExecutedEvent, trade_date: str
) -> bool:
    return (
        event.trade_date == trade_date
        and event.asset_kind in ("index", "board")
        and _valid_identity(event.asset_kind, event.identity_key)
        and event.event_type == "ActionExecuted"
        and event.action_state == "executed"
        and all(
            _nonempty(value)
            for value in (
                event.code,
                event.name,
                event.event_id,
                event.event_time,
                event.source_run_id,
                event.event_schema_version,
            )
        )
    )


def _unconflicted_parent_events_v1(
    events: Sequence[ParentExecutedEvent], trade_date: str
) -> tuple[ParentExecutedEvent, ...]:
    fingerprints: dict[str, str] = {}
    valid: dict[str, ParentExecutedEvent] = {}
    conflicts: set[str] = set()
    for event in events:
        if event.trade_date != trade_date or not _nonempty(event.event_id):
            continue
        fingerprint = _parent_event_fingerprint(event)
        previous = fingerprints.get(event.event_id)
        if previous is not None and previous != fingerprint:
            conflicts.add(event.event_id)
        fingerprints[event.event_id] = fingerprint
        if _valid_parent_event_v1(event, trade_date):
            valid[event.event_id] = event
    return tuple(
        valid[event_id]
        for event_id in sorted(valid)
        if event_id not in conflicts
    )


def _matching_parent_events_v1(
    membership: MembershipRow,
    parent_events: Sequence[ParentExecutedEvent],
    trade_date: str,
) -> tuple[ParentExecutedEvent, ...]:
    return tuple(
        sorted(
            (
                event
                for event in parent_events
                if _valid_parent_event_v1(event, trade_date)
                and event.asset_kind == membership.parent_asset_kind
                and event.identity_key == membership.parent_identity_key
                and event.code == membership.parent_code
                and event.name == membership.parent_name
            ),
            key=lambda event: (event.event_time, event.event_id),
        )
    )


def _evaluate_strategy_center_v1(
    *,
    trade_date: str,
    selected_package_keys: Sequence[str],
    stock_signals: Sequence[StockSignalEvent],
    scope_rows: Sequence[ScopeRow],
    index_memberships: Sequence[MembershipRow],
    board_memberships: Sequence[MembershipRow],
    parent_executed_events: Sequence[ParentExecutedEvent],
    membership_authorities: Sequence[MembershipSnapshotAuthority] | None,
) -> StrategyEvaluationResult:
    selected = tuple(
        package for package in ALLOWED_PACKAGES if package in selected_package_keys
    )
    if not selected or len(set(selected_package_keys)) != len(selected_package_keys):
        raise ValueError("selected_package_keys must contain one or two unique packages")
    if any(package not in ALLOWED_PACKAGES for package in selected_package_keys):
        raise ValueError("selected_package_keys contains an unknown package")
    scopes = _scope_by_stock(scope_rows, trade_date)
    parent_events = _unconflicted_parent_events_v1(
        parent_executed_events, trade_date
    )
    grouped: dict[tuple[str, str], dict[str, StockSignalEvent]] = {}
    fingerprints: dict[tuple[str, str, str], str] = {}
    conflicts: set[tuple[str, str]] = set()
    for event in stock_signals:
        if not _valid_stock_signal_v1(event, trade_date):
            continue
        if event.identity_key not in scopes:
            continue
        group_key = (event.identity_key, event.action_episode_key)
        fingerprint_key = (*group_key, event.event_id)
        fingerprint = _event_fingerprint(event)
        previous = fingerprints.get(fingerprint_key)
        if previous is not None and previous != fingerprint:
            conflicts.add(group_key)
            continue
        fingerprints[fingerprint_key] = fingerprint
        grouped.setdefault(group_key, {})[event.event_id] = event

    matches: list[StrategyMatch] = []
    for group_key in sorted(grouped):
        if group_key in conflicts or membership_authorities is None:
            continue
        stock_identity_key, action_episode_key = group_key
        events = tuple(grouped[group_key].values())
        requested_dates = {source_trade_date_for_event(event) for event in events}
        if len(requested_dates) != 1 or None in requested_dates:
            continue
        requested_source_trade_date = str(next(iter(requested_dates)))
        authorities = tuple(
            authority
            for authority in membership_authorities
            if authority.stock_identity_key == stock_identity_key
            and authority.action_episode_key == action_episode_key
            and authority.requested_source_trade_date == requested_source_trade_date
        )
        authority_by_kind = {
            authority.membership_kind: authority for authority in authorities
        }
        if (
            len(authorities) != 2
            or set(authority_by_kind) != {"index", "board"}
            or any(
                authority.quality_status != "passed"
                or authority.provenance_status != "authoritative_as_of"
                or not _nonempty(authority.selected_membership_trade_date)
                for authority in authorities
            )
        ):
            continue
        selected_dates = {
            kind: authority.selected_membership_trade_date
            for kind, authority in authority_by_kind.items()
        }
        index_rows, invalid_index = _latest_memberships(
            index_memberships,
            trade_date=selected_dates["index"],
            stock_identity_key=stock_identity_key,
            parent_asset_kind="index",
        )
        board_rows, invalid_board = _latest_memberships(
            board_memberships,
            trade_date=selected_dates["board"],
            stock_identity_key=stock_identity_key,
            parent_asset_kind="board",
        )
        current = max(
            events,
            key=lambda event: (
                event.action_state == "executed",
                event.event_time,
                event.event_id,
                event.user_signal_projection_id,
            ),
        )
        timeline = tuple(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "action_state": event.action_state,
                "event_time": event.event_time,
                "source_signal_projection_id": event.user_signal_projection_id,
            }
            for event in sorted(events, key=lambda item: (item.event_time, item.event_id))
        )
        evidence_event_ids = {event.event_id for event in events}
        indices: list[dict[str, Any]] = []
        any_index_executed = False
        for row in index_rows:
            evidence = _matching_parent_events_v1(row, parent_events, trade_date)
            any_index_executed = any_index_executed or bool(evidence)
            evidence_event_ids.update(event.event_id for event in evidence)
            indices.append(
                {
                    "identity_key": row.parent_identity_key,
                    "code": row.parent_code,
                    "name": row.parent_name,
                    "executed_today": bool(evidence),
                    "executed_event_ids": [event.event_id for event in evidence],
                    "membership_source_version": row.source_version,
                    "membership_source_batch_id": row.source_batch_id,
                    "membership_kind": "index",
                    "requested_source_trade_date": requested_source_trade_date,
                    "selected_membership_trade_date": selected_dates["index"],
                    "membership_provenance_status": authority_by_kind[
                        "index"
                    ].provenance_status,
                    "membership_quality_status": authority_by_kind[
                        "index"
                    ].quality_status,
                }
            )
        matched_boards: list[dict[str, Any]] = []
        for row in board_rows:
            evidence = _matching_parent_events_v1(row, parent_events, trade_date)
            if not evidence:
                continue
            evidence_event_ids.update(event.event_id for event in evidence)
            matched_boards.append(
                {
                    "identity_key": row.parent_identity_key,
                    "code": row.parent_code,
                    "name": row.parent_name,
                    "board_type": row.board_type,
                    "executed_event_ids": [event.event_id for event in evidence],
                    "membership_source_version": row.source_version,
                    "membership_source_batch_id": row.source_batch_id,
                    "membership_kind": "board",
                    "requested_source_trade_date": requested_source_trade_date,
                    "selected_membership_trade_date": selected_dates["board"],
                    "membership_provenance_status": authority_by_kind[
                        "board"
                    ].provenance_status,
                    "membership_quality_status": authority_by_kind[
                        "board"
                    ].quality_status,
                }
            )
        matched_packages: list[str] = []
        if PACKAGE_1 in selected and any_index_executed and matched_boards:
            matched_packages.append(PACKAGE_1)
        if PACKAGE_2 in selected and matched_boards:
            matched_packages.append(PACKAGE_2)
        if not matched_packages:
            continue
        confirmation_candidates = [
            event.event_time
            for event in (*events, *parent_events)
            if event.event_id in evidence_event_ids
            and _nonempty(event.event_time)
        ]
        if not confirmation_candidates:
            continue
        confirmation_time = max(confirmation_candidates)
        package_evidence = tuple(
            {
                "package": package,
                "evidence_event_ids": sorted(evidence_event_ids),
            }
            for package in matched_packages
        )
        coherence_episode_key = "legacy:" + _sha256(
            {
                "trade_date": trade_date,
                "stock_identity_key": stock_identity_key,
                "action_episode_key": action_episode_key,
                "strategy_version": STRATEGY_VERSION_V1,
            }
        )[:32]
        confluence = {
            "strategy_version": STRATEGY_VERSION_V1,
            "evaluator_policy_version": _V1_EVALUATOR_POLICY["version"],
            "evaluator_policy_hash": V1_EVALUATOR_POLICY_HASH,
            "display_only": True,
            "direction_match_required": False,
            "direction": (
                _stock_direction(current)
                if _stock_direction(current) in ALLOWED_DIRECTIONS
                else None
            ),
            "time_basis": "whole_trade_date",
            "coherence_level": "LEGACY_WHOLE_TRADE_DATE",
            "freshness_status": "legacy",
            "qualification_status": "qualified",
            "confirmation_time": confirmation_time,
            "package_evidence": list(package_evidence),
            "market_heat_state": "MARKET_HEAT_NEUTRAL",
            "market_heat_rank": _MARKET_HEAT_RANK["MARKET_HEAT_NEUTRAL"],
            "market_heat_evidence": [],
            "market_heat_creates_candidate": False,
        }
        membership_provenance = tuple(
            {
                "requested_source_trade_date": authority.requested_source_trade_date,
                "selected_membership_trade_date": authority.selected_membership_trade_date,
                "source_version": authority.source_version,
                "source_batch_id": authority.source_batch_id,
                "membership_kind": authority.membership_kind,
                "provenance_status": authority.provenance_status,
                "quality_status": authority.quality_status,
            }
            for authority in sorted(authorities, key=lambda item: item.membership_kind)
        )
        mapping_quality = (
            "missing_index"
            if not index_rows
            else ("degraded" if invalid_index or invalid_board else "passed")
        )
        body = {
            "trade_date": trade_date,
            "stock_identity_key": stock_identity_key,
            "action_episode_key": action_episode_key,
            "coherence_episode_key": coherence_episode_key,
            "action_state": current.action_state,
            "source_signal_projection_id": current.user_signal_projection_id,
            "source_event_ids": sorted(evidence_event_ids),
            "matched_packages": matched_packages,
            "scope_sources": list(scopes[stock_identity_key]),
            "indices": indices,
            "matched_boards": matched_boards,
            "signal": dict(current.signal),
            "confluence": confluence,
            "state_timeline": list(timeline),
            "mapping_quality": mapping_quality,
            "requested_source_trade_date": requested_source_trade_date,
            "membership_source_trade_date": max(selected_dates.values()),
            "membership_provenance": list(membership_provenance),
            "evaluator_policy_hash": V1_EVALUATOR_POLICY_HASH,
        }
        matches.append(
            StrategyMatch(
                trade_date=trade_date,
                stock_identity_key=stock_identity_key,
                action_episode_key=action_episode_key,
                coherence_episode_key=coherence_episode_key,
                action_state=current.action_state,
                source_signal_projection_id=current.user_signal_projection_id,
                source_event_ids=tuple(sorted(evidence_event_ids)),
                matched_packages=tuple(matched_packages),
                scope_sources=scopes[stock_identity_key],
                indices=tuple(indices),
                matched_boards=tuple(matched_boards),
                signal=dict(current.signal),
                confluence=confluence,
                state_timeline=timeline,
                mapping_quality=mapping_quality,
                requested_source_trade_date=requested_source_trade_date,
                membership_source_trade_date=max(selected_dates.values()),
                membership_provenance=membership_provenance,
                evaluator_policy_hash=V1_EVALUATOR_POLICY_HASH,
                projection_hash=_sha256(body),
            )
        )
    return StrategyEvaluationResult(matches=tuple(matches), observations=())


def evaluate_strategy_center_versioned(
    *,
    strategy_version: str,
    trade_date: str,
    selected_package_keys: Sequence[str],
    stock_signals: Sequence[StockSignalEvent],
    scope_rows: Sequence[ScopeRow],
    index_memberships: Sequence[MembershipRow],
    board_memberships: Sequence[MembershipRow],
    parent_executed_events: Sequence[ParentExecutedEvent],
    membership_authorities: Sequence[MembershipSnapshotAuthority] | None = None,
    evaluation_time: str | None = None,
    frozen_matches: Sequence[StrategyMatch] = (),
    frozen_observations: Sequence[StrategyObservation] = (),
) -> StrategyEvaluationResult:
    """Dispatch one frozen selection revision to its exact strategy version."""

    if strategy_version == STRATEGY_VERSION_V1:
        return _evaluate_strategy_center_v1(
            trade_date=trade_date,
            selected_package_keys=selected_package_keys,
            stock_signals=stock_signals,
            scope_rows=scope_rows,
            index_memberships=index_memberships,
            board_memberships=board_memberships,
            parent_executed_events=parent_executed_events,
            membership_authorities=membership_authorities,
        )
    if strategy_version != STRATEGY_VERSION_V2:
        raise ValueError("unsupported strategy version")
    return _evaluate_v2_surfaces(
        trade_date=trade_date,
        selected_package_keys=selected_package_keys,
        stock_signals=stock_signals,
        scope_rows=scope_rows,
        index_memberships=index_memberships,
        board_memberships=board_memberships,
        parent_executed_events=parent_executed_events,
        membership_authorities=membership_authorities,
        evaluation_time=evaluation_time,
        frozen_matches=frozen_matches,
        frozen_observations=frozen_observations,
    )
