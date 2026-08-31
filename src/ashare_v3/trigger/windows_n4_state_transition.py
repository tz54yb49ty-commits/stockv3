"""Pure Windows N4 state-transition planner.

The planner consumes immutable Windows N4 memory snapshots and produces
TriggerMatched/TriggerStateChanged envelopes.  It does not persist events,
read the database, fetch market data, or start downstream action work.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from threading import RLock
from types import MappingProxyType

from ashare_v3.events.models import (
    EventEnvelope,
    N4_SOURCE_LAYER,
    validate_event_envelope,
)
from ashare_v3.trigger.event_factory import build_n4_trigger_event
from ashare_v3.trigger.windows_n4_memory import (
    BoardRuntimeState,
    IndexRuntimeState,
    RuntimeStateSnapshot,
    StockRuntimeState,
)


RULE_POLICY_VERSION = "windows_n4_daily_transition_v2"
BUY_CONDITION_KEY = "BUY:D_STATE_V2"
SELL_CONDITION_KEY = "SELL:D_STATE_V2"
LEGACY_RULE_POLICY_VERSION = "windows_n4_state_transition_v1"
LEGACY_BUY_CONDITION_KEY = "BUY:STATE_V1"
LEGACY_SELL_CONDITION_KEY = "SELL:STATE_V1"
SUPPORTED_RULE_POLICY_VERSIONS = {
    LEGACY_RULE_POLICY_VERSION,
    RULE_POLICY_VERSION,
}
FORMAL_PERIOD_PRIORITY = ("Y", "Q", "M", "W", "D")
VALID_30M_GRADES = {"volume_up", "shrink_down", "none", "unknown"}
RuntimeState = StockRuntimeState | IndexRuntimeState | BoardRuntimeState
RuleValue = bool | None


@dataclass(frozen=True, slots=True)
class DirectionTriggerState:
    """Current lifecycle state for one object and one direction."""

    direction: str
    signal_type: str
    condition_key: str
    trigger_live: bool
    current_status: str
    rule_flags: Mapping[str, RuleValue]
    activation_sources: tuple[str, ...]
    formal_triggered_periods: tuple[str, ...]
    primary_trigger_period: str | None
    trigger_period: str | None
    projection_30m_type: str
    trigger_mark_candidate: str
    episode_number: int
    episode_entry_event_id: str | None
    last_event_id: str | None
    source_n4_version: int

    def __post_init__(self) -> None:
        if self.direction not in {"buy", "sell"}:
            raise ValueError(f"unsupported direction: {self.direction}")
        if self.signal_type not in {"B_BUY", "S_SELL"}:
            raise ValueError(f"unsupported signal_type: {self.signal_type}")
        if self.current_status not in {"inactive", "matched"}:
            raise ValueError(f"unsupported current_status: {self.current_status}")
        if self.trigger_live != (self.current_status == "matched"):
            raise ValueError("trigger_live must agree with current_status")
        if self.projection_30m_type not in VALID_30M_GRADES:
            raise ValueError(f"unsupported 30m projection: {self.projection_30m_type}")
        object.__setattr__(self, "rule_flags", MappingProxyType(dict(self.rule_flags)))


@dataclass(frozen=True, slots=True)
class ObjectTriggerState:
    """Buy/sell lifecycle state attached to one N4 runtime object."""

    asset_kind: str
    identity_key: str
    exchange: str
    code: str
    name: str
    source_n4_version: int
    buy: DirectionTriggerState
    sell: DirectionTriggerState


@dataclass(frozen=True, slots=True)
class TriggerStateSnapshot:
    source_condition_run_id: str
    source_trade_date: str
    for_trade_date: str
    asset_kind: str
    source_n4_version: int
    generated_at: datetime
    states: Mapping[str, ObjectTriggerState]

    def __post_init__(self) -> None:
        object.__setattr__(self, "states", MappingProxyType(dict(self.states)))


@dataclass(frozen=True, slots=True)
class TriggerPlanBatch:
    snapshot: TriggerStateSnapshot
    events: tuple[EventEnvelope, ...]


@dataclass(frozen=True, slots=True)
class _DirectionEvaluation:
    determinate: bool
    trigger_live: bool
    rule_flags: Mapping[str, RuleValue]
    activation_sources: tuple[str, ...]
    formal_triggered_periods: tuple[str, ...]
    primary_trigger_period: str | None
    trigger_period: str | None
    projection_30m_type: str
    trigger_mark_candidate: str


class OutOfOrderN4Snapshot(ValueError):
    """Raised when a planner receives an older N4 snapshot."""


class WindowsN4StateTransitionPlanner:
    """Atomic, bounded planner for one stock/index/board channel."""

    def __init__(self, *, asset_kind: str, trigger_run_id: str) -> None:
        if asset_kind not in {"stock", "index", "board"}:
            raise ValueError(f"unsupported asset_kind: {asset_kind}")
        if not trigger_run_id:
            raise ValueError("trigger_run_id is required")
        self.asset_kind = asset_kind
        self.trigger_run_id = trigger_run_id
        self._lock = RLock()
        self._snapshot: TriggerStateSnapshot | None = None

    def read(self) -> TriggerStateSnapshot:
        with self._lock:
            if self._snapshot is None:
                raise RuntimeError("no N4 snapshot has been consumed")
            return self._snapshot

    def fork(self) -> WindowsN4StateTransitionPlanner:
        """Return an isolated candidate with the same immutable state."""

        with self._lock:
            candidate = WindowsN4StateTransitionPlanner(
                asset_kind=self.asset_kind,
                trigger_run_id=self.trigger_run_id,
            )
            candidate._snapshot = self._snapshot
            return candidate

    def restore_from_outbox(
        self,
        events: Sequence[EventEnvelope],
    ) -> TriggerStateSnapshot:
        """Fold one trading day's immutable N4 Outbox events into memory."""

        with self._lock:
            restored = _restore_trigger_state_snapshot(
                events,
                asset_kind=self.asset_kind,
            )
            if self._snapshot is not None:
                if self._snapshot != restored:
                    raise ValueError(
                        "planner already holds different lifecycle state"
                    )
                return self._snapshot
            self._snapshot = restored
            return restored

    def consume(
        self,
        runtime_snapshot: RuntimeStateSnapshot[RuntimeState],
    ) -> TriggerPlanBatch:
        with self._lock:
            return self._consume_locked(runtime_snapshot)

    def _consume_locked(
        self,
        runtime_snapshot: RuntimeStateSnapshot[RuntimeState],
    ) -> TriggerPlanBatch:
        previous_snapshot = self._snapshot
        if previous_snapshot is not None:
            self._validate_lineage(runtime_snapshot, previous_snapshot)
            if runtime_snapshot.version < previous_snapshot.source_n4_version:
                raise OutOfOrderN4Snapshot(
                    f"{self.asset_kind} N4 version moved backwards: "
                    f"{runtime_snapshot.version} < {previous_snapshot.source_n4_version}"
                )
            if runtime_snapshot.version == previous_snapshot.source_n4_version:
                return TriggerPlanBatch(snapshot=previous_snapshot, events=())

        next_states: dict[str, ObjectTriggerState] = {}
        events: list[EventEnvelope] = []
        previous_states = previous_snapshot.states if previous_snapshot is not None else {}
        for identity_key, runtime_state in runtime_snapshot.states.items():
            if runtime_state.asset_kind != self.asset_kind:
                raise ValueError(f"N4 asset mismatch for {identity_key}")
            if runtime_state.identity_key != identity_key:
                raise ValueError(f"N4 identity mismatch for {identity_key}")
            previous = previous_states.get(identity_key) or _initial_object_state(runtime_state)
            next_object, object_events = self._plan_object(
                runtime_state,
                previous,
                runtime_snapshot,
            )
            next_states[identity_key] = next_object
            events.extend(object_events)

        next_snapshot = TriggerStateSnapshot(
            source_condition_run_id=runtime_snapshot.source_condition_run_id,
            source_trade_date=runtime_snapshot.source_trade_date,
            for_trade_date=runtime_snapshot.for_trade_date,
            asset_kind=self.asset_kind,
            source_n4_version=runtime_snapshot.version,
            generated_at=runtime_snapshot.generated_at,
            states=next_states,
        )
        self._snapshot = next_snapshot
        return TriggerPlanBatch(snapshot=next_snapshot, events=tuple(events))

    def _validate_lineage(
        self,
        runtime_snapshot: RuntimeStateSnapshot[RuntimeState],
        previous: TriggerStateSnapshot,
    ) -> None:
        if (
            runtime_snapshot.source_condition_run_id != previous.source_condition_run_id
            or runtime_snapshot.source_trade_date != previous.source_trade_date
            or runtime_snapshot.for_trade_date != previous.for_trade_date
        ):
            raise ValueError("N4 snapshot lineage changed inside one planner")

    def _plan_object(
        self,
        runtime_state: RuntimeState,
        previous: ObjectTriggerState,
        runtime_snapshot: RuntimeStateSnapshot[RuntimeState],
    ) -> tuple[ObjectTriggerState, tuple[EventEnvelope, ...]]:
        if not _has_usable_evidence(runtime_state):
            return (
                replace(
                    previous,
                    source_n4_version=runtime_snapshot.version,
                    buy=replace(
                        previous.buy,
                        source_n4_version=runtime_snapshot.version,
                    ),
                    sell=replace(
                        previous.sell,
                        source_n4_version=runtime_snapshot.version,
                    ),
                ),
                (),
            )

        flags = _evaluate_daily_rules(runtime_state)
        buy_evaluation = _evaluate_direction("buy", flags)
        sell_evaluation = _evaluate_direction("sell", flags)
        buy_state, buy_event = self._advance_direction(
            runtime_state,
            previous.buy,
            buy_evaluation,
            runtime_snapshot,
        )
        sell_state, sell_event = self._advance_direction(
            runtime_state,
            previous.sell,
            sell_evaluation,
            runtime_snapshot,
        )
        next_object = ObjectTriggerState(
            asset_kind=runtime_state.asset_kind,
            identity_key=runtime_state.identity_key,
            exchange=runtime_state.exchange,
            code=runtime_state.code,
            name=runtime_state.name,
            source_n4_version=runtime_snapshot.version,
            buy=buy_state,
            sell=sell_state,
        )
        return next_object, tuple(
            event for event in (buy_event, sell_event) if event is not None
        )

    def _advance_direction(
        self,
        runtime_state: RuntimeState,
        previous: DirectionTriggerState,
        evaluation: _DirectionEvaluation,
        runtime_snapshot: RuntimeStateSnapshot[RuntimeState],
    ) -> tuple[DirectionTriggerState, EventEnvelope | None]:
        if not evaluation.determinate and not evaluation.trigger_live:
            return replace(
                previous,
                source_n4_version=runtime_snapshot.version,
            ), None

        desired = DirectionTriggerState(
            direction=previous.direction,
            signal_type=previous.signal_type,
            condition_key=previous.condition_key,
            trigger_live=evaluation.trigger_live,
            current_status="matched" if evaluation.trigger_live else "inactive",
            rule_flags=evaluation.rule_flags,
            activation_sources=evaluation.activation_sources,
            formal_triggered_periods=evaluation.formal_triggered_periods,
            primary_trigger_period=evaluation.primary_trigger_period,
            trigger_period=evaluation.trigger_period,
            projection_30m_type=evaluation.projection_30m_type,
            trigger_mark_candidate=evaluation.trigger_mark_candidate,
            episode_number=previous.episode_number,
            episode_entry_event_id=previous.episode_entry_event_id,
            last_event_id=previous.last_event_id,
            source_n4_version=runtime_snapshot.version,
        )

        if evaluation.trigger_live and not previous.trigger_live:
            desired = replace(
                desired,
                episode_number=previous.episode_number + 1,
            )
            event = self._build_event(
                event_type="TriggerMatched",
                runtime_state=runtime_state,
                previous=previous,
                current=desired,
                runtime_snapshot=runtime_snapshot,
            )
            desired = replace(
                desired,
                episode_entry_event_id=event.event_id,
                last_event_id=event.event_id,
            )
            event = self._build_event(
                event_type="TriggerMatched",
                runtime_state=runtime_state,
                previous=previous,
                current=desired,
                runtime_snapshot=runtime_snapshot,
            )
            return desired, event

        if evaluation.trigger_live and previous.trigger_live:
            return desired, None

        if not evaluation.trigger_live and previous.trigger_live:
            event = self._build_event(
                event_type="TriggerStateChanged",
                runtime_state=runtime_state,
                previous=previous,
                current=desired,
                runtime_snapshot=runtime_snapshot,
            )
            return replace(desired, last_event_id=event.event_id), event

        return desired, None

    def _build_event(
        self,
        *,
        event_type: str,
        runtime_state: RuntimeState,
        previous: DirectionTriggerState,
        current: DirectionTriggerState,
        runtime_snapshot: RuntimeStateSnapshot[RuntimeState],
    ) -> EventEnvelope:
        event_time = runtime_state.observed_at or runtime_state.source_time
        if event_time is None:
            raise ValueError("usable N4 state must have an effective event time")
        source_event_id = (
            f"n4-memory:{runtime_state.asset_kind}:{runtime_state.identity_key}:"
            f"{runtime_snapshot.version}"
        )
        trigger_bucket = f"episode:{current.episode_number}"
        match_basis = (
            f"{RULE_POLICY_VERSION}:"
            f"{','.join(current.activation_sources) or 'inactive'}"
        )
        projection_flag = current.projection_30m_type in {
            "volume_up",
            "shrink_down",
        }
        previous_projection_flag = previous.projection_30m_type in {
            "volume_up",
            "shrink_down",
        }
        payload = {
            "rule_policy_version": RULE_POLICY_VERSION,
            "source_condition_run_id": runtime_state.source_condition_run_id,
            "source_trade_date": runtime_state.source_trade_date,
            "for_trade_date": runtime_state.for_trade_date,
            "code": runtime_state.code,
            "name": runtime_state.name,
            "n4_state_version": runtime_snapshot.version,
            "source_n3_version": runtime_state.source_n3_version,
            "source_transitions": dict(runtime_state.source_transitions),
            "source_amounts": _decimal_mapping_payload(
                runtime_state.source_amounts
            ),
            "comparison_amounts": _decimal_mapping_payload(
                runtime_state.comparison_amounts
            ),
            "realtime_transitions": dict(runtime_state.realtime_transitions),
            "realtime_virtual_amounts": _decimal_mapping_payload(
                runtime_state.realtime_virtual_amounts
            ),
            "current_price": _decimal_payload(runtime_state.current_price),
            "cumulative_amount": _decimal_payload(
                runtime_state.cumulative_amount
            ),
            "provider": runtime_state.provider,
            "live_status": runtime_state.live_status,
            "fresh": runtime_state.fresh,
            "effective_time": event_time.isoformat(),
            "data_quality_status": "ready",
            "source_w_average_amount": (
                str(runtime_state.comparison_amounts["W"])
                if runtime_state.comparison_amounts.get("W") is not None
                else None
            ),
            "rule_flags": dict(current.rule_flags),
            "activation_sources": list(current.activation_sources),
            "formal_triggered_periods": list(current.formal_triggered_periods),
            "triggered_periods": list(current.formal_triggered_periods),
            "all_trigger_periods": list(current.formal_triggered_periods),
            "primary_trigger_period": current.primary_trigger_period,
            "projection_30m_flag": projection_flag,
            "projection_30m_type": current.projection_30m_type,
            "trigger_live": current.trigger_live,
            "current_status": current.current_status,
            "episode_number": current.episode_number,
            "episode_entry_event_id": current.episode_entry_event_id,
        }
        if event_type == "TriggerStateChanged":
            payload.update(
                {
                    "previous_trigger_live": previous.trigger_live,
                    "previous_status": previous.current_status,
                    "previous_primary_trigger_period": previous.primary_trigger_period,
                    "previous_all_trigger_periods": list(
                        previous.formal_triggered_periods
                    ),
                    "previous_projection_30m_flag": previous_projection_flag,
                    "previous_projection_30m_type": previous.projection_30m_type,
                    "previous_trigger_mark_candidate": (
                        previous.trigger_mark_candidate
                    ),
                    "state_change_reason": "matched_to_inactive",
                    "source_outcome_event_type": "N4RuntimeStateVersion",
                    "source_outcome_event_id": source_event_id,
                }
            )
        return build_n4_trigger_event(
            event_type=event_type,
            asset_kind=runtime_state.asset_kind,
            identity_key=runtime_state.identity_key,
            trade_date=runtime_state.for_trade_date,
            event_time=event_time,
            trigger_run_id=self.trigger_run_id,
            source_event_id=source_event_id,
            direction=current.direction,
            signal_type=current.signal_type,
            condition_key=current.condition_key,
            trigger_mark_candidate=current.trigger_mark_candidate,
            trigger_period=(
                current.trigger_period
                or previous.trigger_period
                or ""
            ),
            trigger_bucket=trigger_bucket,
            match_basis=match_basis,
            data_quality_status="ready",
            payload=payload,
            created_at=runtime_snapshot.generated_at,
        )


def _restore_trigger_state_snapshot(
    events: Sequence[EventEnvelope],
    *,
    asset_kind: str,
) -> TriggerStateSnapshot:
    if not events:
        raise ValueError("restore events must not be empty")

    unique: dict[str, EventEnvelope] = {}
    for event in events:
        validate_event_envelope(event)
        _validate_restore_event(event, asset_kind)
        previous = unique.get(event.event_id)
        if previous is not None and previous.as_record() != event.as_record():
            raise ValueError(f"conflicting duplicate event_id: {event.event_id}")
        unique[event.event_id] = event

    ordered = sorted(
        unique.values(),
        key=lambda event: (
            _restore_int(event.payload_json, "n4_state_version"),
            event.event_time,
            event.event_id,
        ),
    )
    first = ordered[0].payload_json
    lineage = tuple(
        _restore_str(first, key)
        for key in (
            "source_condition_run_id",
            "source_trade_date",
            "for_trade_date",
        )
    )
    policy_version = _restore_str(first, "rule_policy_version")
    states: dict[str, ObjectTriggerState] = {}
    seen_versions: set[tuple[str, str, int]] = set()

    for event in ordered:
        payload = event.payload_json
        current_lineage = tuple(
            _restore_str(payload, key)
            for key in (
                "source_condition_run_id",
                "source_trade_date",
                "for_trade_date",
            )
        )
        if current_lineage != lineage:
            raise ValueError("restore events contain mixed N2 lineage or dates")
        if _restore_str(payload, "rule_policy_version") != policy_version:
            raise ValueError("restore events contain mixed rule policies")
        version = _restore_int(payload, "n4_state_version")
        direction = _restore_str(payload, "direction")
        version_key = (event.identity_key, direction, version)
        if version_key in seen_versions:
            raise ValueError(
                "multiple N4 lifecycle events share one direction and version"
            )
        seen_versions.add(version_key)

        previous_object = states.get(event.identity_key)
        if previous_object is None:
            previous_object = _initial_restored_object(event)
        previous_direction = (
            previous_object.buy if direction == "buy" else previous_object.sell
        )
        current_direction = _restore_direction_state(
            event,
            previous_direction,
            version,
        )
        states[event.identity_key] = replace(
            previous_object,
            source_n4_version=max(
                previous_object.source_n4_version,
                version,
            ),
            buy=(
                current_direction
                if direction == "buy"
                else previous_object.buy
            ),
            sell=(
                current_direction
                if direction == "sell"
                else previous_object.sell
            ),
        )

    return TriggerStateSnapshot(
        source_condition_run_id=lineage[0],
        source_trade_date=lineage[1],
        for_trade_date=lineage[2],
        asset_kind=asset_kind,
        source_n4_version=max(
            _restore_int(event.payload_json, "n4_state_version")
            for event in ordered
        ),
        generated_at=max(event.created_at for event in ordered),
        states=states,
    )


def _validate_restore_event(
    event: EventEnvelope,
    asset_kind: str,
) -> None:
    payload = event.payload_json
    if (
        event.source_layer != N4_SOURCE_LAYER
        or event.event_type not in {"TriggerMatched", "TriggerStateChanged"}
        or event.asset_kind != asset_kind
    ):
        raise ValueError("event is not restorable by this N4 channel")
    if _restore_str(payload, "run_id") != event.source_run_id:
        raise ValueError("restore payload run_id does not match event")
    if (
        _restore_str(payload, "rule_policy_version")
        not in SUPPORTED_RULE_POLICY_VERSIONS
    ):
        raise ValueError("restore event rule policy is not supported")
    if _restore_str(payload, "for_trade_date") != event.trade_date:
        raise ValueError("restore event trade_date does not match payload")


def _initial_restored_object(event: EventEnvelope) -> ObjectTriggerState:
    payload = event.payload_json
    parts = event.identity_key.split(":")
    if len(parts) != 3 or parts[0] != event.asset_kind:
        raise ValueError(f"invalid restore identity_key: {event.identity_key}")
    code = _restore_str(payload, "code")
    if code != parts[2]:
        raise ValueError("restore payload code does not match identity_key")
    return ObjectTriggerState(
        asset_kind=event.asset_kind,
        identity_key=event.identity_key,
        exchange=parts[1],
        code=code,
        name=_restore_str(payload, "name"),
        source_n4_version=0,
        buy=_initial_direction_state("buy"),
        sell=_initial_direction_state("sell"),
    )


def _restore_direction_state(
    event: EventEnvelope,
    previous: DirectionTriggerState,
    version: int,
) -> DirectionTriggerState:
    payload = event.payload_json
    direction = _restore_str(payload, "direction")
    policy_version = _restore_str(payload, "rule_policy_version")
    expected_signal = "B_BUY" if direction == "buy" else "S_SELL"
    expected_condition = _condition_key_for_policy(
        policy_version,
        direction,
    )
    if (
        direction != previous.direction
        or _restore_str(payload, "signal_type") != expected_signal
        or _restore_str(payload, "condition_key") != expected_condition
    ):
        raise ValueError("restore event direction grain is inconsistent")

    trigger_live = payload.get("trigger_live")
    if type(trigger_live) is not bool:
        raise ValueError("restore trigger_live must be boolean")
    status = _restore_str(payload, "current_status")
    if status != ("matched" if trigger_live else "inactive"):
        raise ValueError("restore trigger_live and current_status disagree")
    episode = _restore_int(payload, "episode_number")
    entry_event_id = _restore_str(payload, "episode_entry_event_id")

    if event.event_type == "TriggerMatched":
        if previous.trigger_live or not trigger_live:
            raise ValueError("TriggerMatched cannot reopen a live episode")
        if episode != previous.episode_number + 1:
            raise ValueError("TriggerMatched episode_number is not monotonic")
        if entry_event_id != event.event_id:
            raise ValueError(
                "TriggerMatched episode_entry_event_id must equal event_id"
            )
    elif (
        not previous.trigger_live
        or episode != previous.episode_number
        or entry_event_id != previous.episode_entry_event_id
    ):
        raise ValueError(
            "TriggerStateChanged must retain the current live episode"
        )

    if (
        policy_version == RULE_POLICY_VERSION
        and event.event_type == "TriggerStateChanged"
        and trigger_live
    ):
        raise ValueError("V2 TriggerStateChanged must be inactive")
    flags = payload.get("rule_flags")
    if not isinstance(flags, Mapping) or set(flags) != {"A", "B", "C", "D30"}:
        raise ValueError("restore event has invalid rule_flags")
    activation_sources = _restore_sequence(payload, "activation_sources")
    formal_periods = _restore_sequence(
        payload,
        "formal_triggered_periods",
    )
    primary = payload.get("primary_trigger_period")
    if primary is not None and primary not in FORMAL_PERIOD_PRIORITY:
        raise ValueError("restore primary_trigger_period is invalid")
    projection = _restore_str(payload, "projection_30m_type")
    if projection not in VALID_30M_GRADES:
        raise ValueError("restore projection_30m_type is invalid")
    if policy_version == RULE_POLICY_VERSION:
        if flags["B"] is not False or flags["D30"] is not False:
            raise ValueError("V2 30m rule flags must be false")
        expected_periods = ("D",) if trigger_live else ()
        if (
            activation_sources != expected_periods
            or formal_periods != expected_periods
            or primary != ("D" if trigger_live else None)
            or projection != "none"
        ):
            raise ValueError("V2 trigger period contract is invalid")

    return DirectionTriggerState(
        direction=direction,
        signal_type=expected_signal,
        condition_key=expected_condition,
        trigger_live=trigger_live,
        current_status=status,
        rule_flags=dict(flags),
        activation_sources=activation_sources,
        formal_triggered_periods=formal_periods,
        primary_trigger_period=primary,
        trigger_period=(
            _restore_str(payload, "trigger_period")
            if trigger_live
            else None
        ),
        projection_30m_type=projection,
        trigger_mark_candidate=_restore_str(
            payload,
            "trigger_mark_candidate",
        ),
        episode_number=episode,
        episode_entry_event_id=entry_event_id,
        last_event_id=event.event_id,
        source_n4_version=version,
    )


def _restore_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"restore payload requires {key}")
    return value


def _restore_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 1:
        raise ValueError(f"restore payload requires positive integer {key}")
    return value


def _restore_sequence(
    payload: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item
        for item in value
    ):
        raise ValueError(f"restore payload requires string sequence {key}")
    return tuple(value)


def _condition_key_for_policy(
    policy_version: str,
    direction: str,
) -> str:
    if policy_version == RULE_POLICY_VERSION:
        return (
            BUY_CONDITION_KEY
            if direction == "buy"
            else SELL_CONDITION_KEY
        )
    if policy_version == LEGACY_RULE_POLICY_VERSION:
        return (
            LEGACY_BUY_CONDITION_KEY
            if direction == "buy"
            else LEGACY_SELL_CONDITION_KEY
        )
    raise ValueError("restore event rule policy is not supported")


def _initial_object_state(runtime_state: RuntimeState) -> ObjectTriggerState:
    return ObjectTriggerState(
        asset_kind=runtime_state.asset_kind,
        identity_key=runtime_state.identity_key,
        exchange=runtime_state.exchange,
        code=runtime_state.code,
        name=runtime_state.name,
        source_n4_version=0,
        buy=_initial_direction_state("buy"),
        sell=_initial_direction_state("sell"),
    )


def _initial_direction_state(direction: str) -> DirectionTriggerState:
    is_buy = direction == "buy"
    return DirectionTriggerState(
        direction=direction,
        signal_type="B_BUY" if is_buy else "S_SELL",
        condition_key=BUY_CONDITION_KEY if is_buy else SELL_CONDITION_KEY,
        trigger_live=False,
        current_status="inactive",
        rule_flags={"A": False, "B": False, "C": False, "D30": False},
        activation_sources=(),
        formal_triggered_periods=(),
        primary_trigger_period=None,
        trigger_period=None,
        projection_30m_type="none",
        trigger_mark_candidate="normal",
        episode_number=0,
        episode_entry_event_id=None,
        last_event_id=None,
        source_n4_version=0,
    )


def _has_usable_evidence(state: RuntimeState) -> bool:
    return (
        state.fresh
        and state.live_status == "available"
        and state.current_price is not None
        and (state.observed_at is not None or state.source_time is not None)
    )


def _evaluate_daily_rules(state: RuntimeState) -> Mapping[str, RuleValue]:
    source_d = state.source_transitions.get("D")
    live_d = state.realtime_transitions.get("D")
    source_w = state.comparison_amounts.get("W")
    live_w = state.realtime_virtual_amounts.get("W")
    return MappingProxyType(
        {
            "A": _tri_and(
                _known_not_equal(source_d, "volume_up"),
                _known_equal(live_d, "volume_up"),
                _decimal_compare(live_w, source_w, greater=True),
            ),
            "B": False,
            "C": _tri_and(
                _known_not_equal(source_d, "low_volume_down"),
                _known_equal(live_d, "low_volume_down"),
                _decimal_compare(live_w, source_w, greater=False),
            ),
            "D30": False,
        }
    )


def _evaluate_direction(
    direction: str,
    flags: Mapping[str, RuleValue],
) -> _DirectionEvaluation:
    result = flags["A" if direction == "buy" else "C"]
    trigger_live = result is True
    periods = ("D",) if trigger_live else ()
    return _DirectionEvaluation(
        determinate=result is not None,
        trigger_live=trigger_live,
        rule_flags=flags,
        activation_sources=periods,
        formal_triggered_periods=periods,
        primary_trigger_period="D" if trigger_live else None,
        trigger_period="D" if trigger_live else None,
        projection_30m_type="none",
        trigger_mark_candidate="normal",
    )


def _known_equal(value: object, expected: str) -> RuleValue:
    if value in (None, "unknown"):
        return None
    return str(value) == expected


def _known_not_equal(value: object, expected: str) -> RuleValue:
    equal = _known_equal(value, expected)
    return None if equal is None else not equal


def _decimal_payload(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal_mapping_payload(
    values: Mapping[str, Decimal | None],
) -> dict[str, str | None]:
    return {
        period: _decimal_payload(value)
        for period, value in values.items()
    }


def _decimal_compare(
    current: Decimal | None,
    baseline: Decimal | None,
    *,
    greater: bool,
) -> RuleValue:
    if current is None or baseline is None:
        return None
    return current > baseline if greater else current < baseline


def _tri_and(*values: RuleValue) -> RuleValue:
    if any(value is None for value in values):
        return None
    return all(values)
