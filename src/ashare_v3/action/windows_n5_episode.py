"""Pure Windows N5 in-memory episode and closed-minute confirmation planner.

The planner consumes canonical N4 lifecycle events and N3 standardized
closed-minute metrics.  It neither pulls market data nor writes a database,
outbox, inbox, checkpoint, N6 projection, sim state, or trade instruction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, time
from decimal import Decimal
from threading import RLock
from types import MappingProxyType
from typing import Any

from ashare_v3.action.event_factory import build_n5_action_event
from ashare_v3.events.models import EventEnvelope, N4_SOURCE_LAYER, N5_SOURCE_LAYER
from ashare_v3.market.windows_n3_action_metric import ActionConfirmationMetric


ACTION_POLICY_VERSION = "windows_n5_closed_minute_confirmation_v1"
SOURCE_RULE_POLICY_VERSION = "windows_n4_state_transition_v1"
VALID_CONDITION_KEYS = {"BUY:STATE_V1", "SELL:STATE_V1"}
VALID_SIGNAL_TYPES = {"B_BUY", "S_SELL"}
VALID_ASSET_KINDS = {"stock", "index", "board"}
TriggerGrain = tuple[str, str, str, str, str, str]


@dataclass(frozen=True, slots=True)
class EpisodeKey:
    trade_date: str
    asset_kind: str
    identity_key: str
    direction: str
    signal_type: str
    condition_key: str
    episode_entry_event_id: str


@dataclass(frozen=True, slots=True)
class N5ActionEpisode:
    key: EpisodeKey
    entry_trigger_event: Mapping[str, Any]
    current_source_event: Mapping[str, Any]
    action_state: str
    confirmation_status: str
    trigger_live: bool
    eligible_event_id: str | None
    executed_event_id: str | None
    last_checked_minute_index: int | None
    last_checked_minute_label: str | None
    latest_metric_proof: Mapping[str, Any] | None
    tracking_until: datetime
    source_n4_version: int

    def __post_init__(self) -> None:
        if self.action_state not in {"eligible", "executed"}:
            raise ValueError(f"unsupported active action_state: {self.action_state}")
        if self.confirmation_status not in {"pending", "passed"}:
            raise ValueError(
                f"unsupported active confirmation_status: {self.confirmation_status}"
            )
        object.__setattr__(
            self,
            "entry_trigger_event",
            MappingProxyType(dict(self.entry_trigger_event)),
        )
        object.__setattr__(
            self,
            "current_source_event",
            MappingProxyType(dict(self.current_source_event)),
        )
        if self.latest_metric_proof is not None:
            object.__setattr__(
                self,
                "latest_metric_proof",
                MappingProxyType(dict(self.latest_metric_proof)),
            )


@dataclass(frozen=True, slots=True)
class ConfirmationDecision:
    metric_ready: bool
    all_passed: bool
    checks: Mapping[str, bool | None]
    action_mark: str | None
    action_mark_reason: str | None
    pending_reason: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", MappingProxyType(dict(self.checks)))


@dataclass(frozen=True, slots=True)
class N5EpisodeSnapshot:
    action_run_id: str
    asset_kind: str
    version: int
    generated_at: datetime | None
    active: Mapping[EpisodeKey, N5ActionEpisode]
    processed_trigger_event_count: int
    closed_episode_count: int
    trigger_watermark_count: int
    closed_episode_watermark_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "active", MappingProxyType(dict(self.active)))


@dataclass(frozen=True, slots=True)
class N5PlanBatch:
    snapshot: N5EpisodeSnapshot
    events: tuple[EventEnvelope, ...]


class WindowsN5EpisodePlanner:
    """Atomic planner for one independent stock/index/board channel."""

    def __init__(self, *, asset_kind: str, action_run_id: str) -> None:
        if asset_kind not in VALID_ASSET_KINDS:
            raise ValueError(f"unsupported asset_kind: {asset_kind}")
        if not action_run_id:
            raise ValueError("action_run_id is required")
        self.asset_kind = asset_kind
        self.action_run_id = action_run_id
        self._lock = RLock()
        self._active: dict[EpisodeKey, N5ActionEpisode] = {}
        self._trigger_watermarks: dict[
            TriggerGrain, tuple[int, str]
        ] = {}
        self._closed_episode_watermarks: dict[
            TriggerGrain, str
        ] = {}
        self._processed_trigger_event_count = 0
        self._closed_episode_count = 0
        self._version = 0
        self._generated_at: datetime | None = None

    def read(self) -> N5EpisodeSnapshot:
        with self._lock:
            return self._snapshot()

    def consume_trigger_event(self, event: EventEnvelope) -> N5PlanBatch:
        with self._lock:
            return self._consume_trigger_event(event, emit=True)

    def consume_metric(
        self,
        metric: ActionConfirmationMetric,
    ) -> N5PlanBatch:
        with self._lock:
            if metric.asset_kind != self.asset_kind:
                raise ValueError("N3 metric asset_kind mismatch")
            matching = [
                (key, episode)
                for key, episode in self._active.items()
                if key.trade_date == metric.trade_date
                and key.identity_key == metric.identity_key
                and episode.action_state == "eligible"
            ]
            output: list[EventEnvelope] = []
            changed = False
            for key, episode in matching:
                if (
                    episode.last_checked_minute_index is not None
                    and metric.expected_minute_index
                    <= episode.last_checked_minute_index
                ):
                    continue
                if not metric.metric_ready:
                    continue
                decision = evaluate_confirmation(episode.key.direction, metric)
                if decision.all_passed:
                    action_event = self._build_action_executed(
                        episode,
                        metric,
                        decision,
                    )
                    self._active[key] = replace(
                        episode,
                        action_state="executed",
                        confirmation_status="passed",
                        executed_event_id=action_event.event_id,
                        last_checked_minute_index=metric.expected_minute_index,
                        last_checked_minute_label=metric.metric_minute_label,
                        latest_metric_proof=_metric_proof(metric),
                    )
                    output.append(action_event)
                    changed = True
                    continue
                if _metric_reaches_close(metric):
                    skipped = self._build_action_skipped(
                        episode,
                        event_time=metric.metric_time or episode.tracking_until,
                        reason="window_expired",
                    )
                    del self._active[key]
                    self._mark_episode_closed(key)
                    output.append(skipped)
                    changed = True
                    continue
                self._active[key] = replace(
                    episode,
                    last_checked_minute_index=metric.expected_minute_index,
                    last_checked_minute_label=metric.metric_minute_label,
                    latest_metric_proof=_metric_proof(metric),
                )
                changed = True
            if changed:
                self._advance_version(metric.metric_time)
            return N5PlanBatch(self._snapshot(), tuple(output))

    def expire(self, observed_at: datetime) -> N5PlanBatch:
        with self._lock:
            output: list[EventEnvelope] = []
            for key, episode in tuple(self._active.items()):
                if (
                    episode.action_state == "eligible"
                    and observed_at >= episode.tracking_until
                ):
                    output.append(
                        self._build_action_skipped(
                            episode,
                            event_time=observed_at,
                            reason="window_expired",
                        )
                    )
                    del self._active[key]
                    self._mark_episode_closed(key)
            if output:
                self._advance_version(observed_at)
            return N5PlanBatch(self._snapshot(), tuple(output))

    def restore_from_outbox(
        self,
        events: Sequence[EventEnvelope],
    ) -> N5EpisodeSnapshot:
        """Fold ordered same-day N4/N5 outbox events without emitting messages."""

        with self._lock:
            if (
                self._active
                or self._trigger_watermarks
                or self._closed_episode_watermarks
                or self._version
            ):
                raise RuntimeError("restore requires a new empty planner")
            for event in events:
                if event.asset_kind != self.asset_kind:
                    continue
                if event.source_layer == N4_SOURCE_LAYER:
                    self._consume_trigger_event(event, emit=False)
                    continue
                if event.source_layer == N5_SOURCE_LAYER:
                    self._restore_action_event(event)
            return self._snapshot()

    def _consume_trigger_event(
        self,
        event: EventEnvelope,
        *,
        emit: bool,
    ) -> N5PlanBatch:
        _validate_trigger_event(event, self.asset_kind)
        payload = dict(event.payload_json)
        grain = _trigger_grain(event, payload)
        source_version = _integer(payload.get("n4_state_version"))
        watermark = self._trigger_watermarks.get(grain)
        if watermark is not None and source_version <= watermark[0]:
            return N5PlanBatch(self._snapshot(), ())
        self._trigger_watermarks[grain] = (
            source_version,
            event.event_id,
        )
        output: list[EventEnvelope] = []
        self._processed_trigger_event_count += 1
        if str(payload.get("data_quality_status") or "") != "ready":
            self._advance_version(event.event_time)
            return N5PlanBatch(self._snapshot(), ())

        if event.event_type == "TriggerMatched":
            if not _matched_event_is_live(payload):
                self._advance_version(event.event_time)
                return N5PlanBatch(self._snapshot(), ())
            entry_id = event.event_id
            if self._closed_episode_watermarks.get(grain) == entry_id:
                self._advance_version(event.event_time)
                return N5PlanBatch(self._snapshot(), ())
            key = _episode_key(event, entry_id)
            if key not in self._active:
                event_snapshot = _event_snapshot(event)
                episode = N5ActionEpisode(
                    key=key,
                    entry_trigger_event=event_snapshot,
                    current_source_event=event_snapshot,
                    action_state="eligible",
                    confirmation_status="pending",
                    trigger_live=True,
                    eligible_event_id=None,
                    executed_event_id=None,
                    last_checked_minute_index=None,
                    last_checked_minute_label=None,
                    latest_metric_proof=None,
                    tracking_until=_tracking_until(event),
                    source_n4_version=_integer(payload.get("n4_state_version")),
                )
                if emit:
                    eligible = self._build_action_eligible(episode)
                    episode = replace(
                        episode,
                        eligible_event_id=eligible.event_id,
                    )
                    output.append(eligible)
                self._active[key] = episode
            self._advance_version(event.event_time)
            return N5PlanBatch(self._snapshot(), tuple(output))

        entry_id = str(payload.get("episode_entry_event_id") or "")
        found = self._find_by_entry_id(entry_id)
        if found is None:
            self._advance_version(event.event_time)
            return N5PlanBatch(self._snapshot(), ())
        key, episode = found
        if bool(payload.get("trigger_live")):
            self._active[key] = replace(
                episode,
                current_source_event=_event_snapshot(event),
                trigger_live=True,
                source_n4_version=_integer(payload.get("n4_state_version")),
            )
        else:
            if emit and episode.action_state == "eligible":
                output.append(
                    self._build_action_skipped(
                        episode,
                        event_time=event.event_time,
                        reason="trigger_live_false",
                        current_source_event=event,
                    )
                )
            del self._active[key]
            self._mark_episode_closed(key)
        self._advance_version(event.event_time)
        return N5PlanBatch(self._snapshot(), tuple(output))

    def _restore_action_event(self, event: EventEnvelope) -> None:
        payload = dict(event.payload_json)
        entry_id = str(payload.get("episode_entry_event_id") or "")
        found = self._find_by_entry_id(entry_id)
        if event.event_type == "ActionEligible" and found is not None:
            key, episode = found
            self._active[key] = replace(
                episode,
                eligible_event_id=event.event_id,
            )
        elif event.event_type == "ActionExecuted" and found is not None:
            market_proof = payload.get("final_market_proof")
            key, episode = found
            self._active[key] = replace(
                episode,
                action_state="executed",
                confirmation_status="passed",
                executed_event_id=event.event_id,
                last_checked_minute_index=_optional_integer(
                    payload.get("metric_minute_index")
                ),
                last_checked_minute_label=payload.get("metric_minute_label"),
                latest_metric_proof=(
                    dict(market_proof)
                    if isinstance(market_proof, Mapping)
                    else None
                ),
            )
        elif event.event_type == "ActionSkipped" and found is not None:
            key, _episode = found
            del self._active[key]
            self._mark_episode_closed(key)
        self._advance_version(event.event_time)

    def _build_action_eligible(
        self,
        episode: N5ActionEpisode,
    ) -> EventEnvelope:
        return self._build_action_event(
            episode=episode,
            event_type="ActionEligible",
            source_event=episode.entry_trigger_event,
            event_time=_event_time(episode.entry_trigger_event),
            action_state="eligible",
            confirmation_status="pending",
            action_mark=None,
            reason="trigger_matched",
            metric=None,
            decision=None,
        )

    def _build_action_executed(
        self,
        episode: N5ActionEpisode,
        metric: ActionConfirmationMetric,
        decision: ConfirmationDecision,
    ) -> EventEnvelope:
        return self._build_action_event(
            episode=episode,
            event_type="ActionExecuted",
            source_event=episode.current_source_event,
            event_time=metric.metric_time or _event_time(
                episode.current_source_event
            ),
            action_state="executed",
            confirmation_status="passed",
            action_mark=decision.action_mark,
            reason=decision.action_mark_reason or "all_confirmations_passed",
            metric=metric,
            decision=decision,
        )

    def _build_action_skipped(
        self,
        episode: N5ActionEpisode,
        *,
        event_time: datetime,
        reason: str,
        current_source_event: EventEnvelope | None = None,
    ) -> EventEnvelope:
        source = (
            _event_snapshot(current_source_event)
            if current_source_event is not None
            else episode.current_source_event
        )
        return self._build_action_event(
            episode=episode,
            event_type="ActionSkipped",
            source_event=source,
            event_time=event_time,
            action_state="expired",
            confirmation_status="expired",
            action_mark=None,
            reason=reason,
            metric=None,
            decision=None,
        )

    def _build_action_event(
        self,
        *,
        episode: N5ActionEpisode,
        event_type: str,
        source_event: Mapping[str, Any],
        event_time: datetime,
        action_state: str,
        confirmation_status: str,
        action_mark: str | None,
        reason: str,
        metric: ActionConfirmationMetric | None,
        decision: ConfirmationDecision | None,
    ) -> EventEnvelope:
        entry_payload = dict(episode.entry_trigger_event["payload_json"])
        current_payload = dict(source_event["payload_json"])
        formal_periods = tuple(
            str(value)
            for value in current_payload.get("all_trigger_periods", ())
        )
        primary_period = current_payload.get("primary_trigger_period")
        trigger_period = str(current_payload.get("trigger_period") or "")
        payload: dict[str, Any] = {
            "rule_policy_version": SOURCE_RULE_POLICY_VERSION,
            "episode_entry_event_id": episode.key.episode_entry_event_id,
            "action_entry_trigger_matched_ref": dict(
                episode.entry_trigger_event
            ),
            "current_active_source_ref": dict(source_event),
            "source_n4_payload": current_payload,
            "trigger_price": current_payload.get("trigger_price"),
            "trigger_kind": "trigger",
            "triggered_periods": list(formal_periods),
            "all_trigger_periods": list(formal_periods),
            "primary_trigger_period": primary_period,
            "period_trigger_baseline_trace": {
                "source_condition_run_id": current_payload.get(
                    "source_condition_run_id"
                ),
                "rule_policy_version": SOURCE_RULE_POLICY_VERSION,
            },
            "baseline_source": "windows_n4_memory",
            "metric_minute_index": (
                metric.expected_minute_index if metric is not None else None
            ),
            "metric_minute_label": (
                metric.metric_minute_label if metric is not None else None
            ),
            "action_price": (
                metric.current_price if metric is not None else None
            ),
            "confirmation_checks": (
                dict(decision.checks) if decision is not None else {}
            ),
            "action_mark_reason": (
                decision.action_mark_reason if decision is not None else None
            ),
            "final_market_proof": (
                _metric_proof(metric) if metric is not None else None
            ),
        }
        source_trigger_event_id = str(source_event["event_id"])
        return build_n5_action_event(
            event_type=event_type,
            asset_kind=episode.key.asset_kind,
            identity_key=episode.key.identity_key,
            trade_date=episode.key.trade_date,
            event_time=event_time,
            action_run_id=self.action_run_id,
            source_trigger_event_id=source_trigger_event_id,
            source_trigger_run_id=str(source_event["source_run_id"]),
            source_trigger_state_id=current_payload.get("n4_state_version"),
            source_trigger_match_id=episode.key.episode_entry_event_id,
            source_condition_run_id=str(
                current_payload.get("source_condition_run_id")
                or entry_payload.get("source_condition_run_id")
                or "not_available"
            ),
            direction=episode.key.direction,
            signal_type=episode.key.signal_type,
            condition_key=episode.key.condition_key,
            original_condition_key=episode.key.condition_key,
            trigger_period=trigger_period,
            data_quality_status=str(
                current_payload.get("data_quality_status") or "ready"
            ),
            action_mark=action_mark,
            action_state=action_state,
            confirmation_status=confirmation_status,
            action_policy=ACTION_POLICY_VERSION,
            eligibility_reason=reason if event_type == "ActionEligible" else None,
            skipped_reason=reason if event_type == "ActionSkipped" else None,
            trace_json={
                "entry_event_id": episode.key.episode_entry_event_id,
                "current_source_event_id": source_trigger_event_id,
                "source_n4_version": _integer(
                    current_payload.get("n4_state_version")
                ) or episode.source_n4_version,
            },
            action_type=(
                "buy_candidate"
                if episode.key.direction == "buy"
                else "sell_candidate"
            ),
            lane="policy_pending",
            source_market_trace={
                "source": "windows_n3_action_metric"
                if metric is not None
                else "windows_n4_memory",
                "metric_policy_version": (
                    metric.metric_policy_version if metric is not None else None
                ),
            },
            payload=payload,
        )

    def _find_by_entry_id(
        self,
        entry_id: str,
    ) -> tuple[EpisodeKey, N5ActionEpisode] | None:
        if not entry_id:
            return None
        return next(
            (
                (key, episode)
                for key, episode in self._active.items()
                if key.episode_entry_event_id == entry_id
            ),
            None,
        )

    def _mark_episode_closed(self, key: EpisodeKey) -> None:
        grain = _trigger_grain_from_key(key)
        if (
            self._closed_episode_watermarks.get(grain)
            != key.episode_entry_event_id
        ):
            self._closed_episode_count += 1
        self._closed_episode_watermarks[grain] = key.episode_entry_event_id

    def _advance_version(self, generated_at: datetime | None) -> None:
        self._version += 1
        self._generated_at = generated_at

    def _snapshot(self) -> N5EpisodeSnapshot:
        return N5EpisodeSnapshot(
            action_run_id=self.action_run_id,
            asset_kind=self.asset_kind,
            version=self._version,
            generated_at=self._generated_at,
            active=self._active,
            processed_trigger_event_count=self._processed_trigger_event_count,
            closed_episode_count=self._closed_episode_count,
            trigger_watermark_count=len(self._trigger_watermarks),
            closed_episode_watermark_count=len(
                self._closed_episode_watermarks
            ),
        )


def evaluate_confirmation(
    direction: str,
    metric: ActionConfirmationMetric,
) -> ConfirmationDecision:
    if direction not in {"buy", "sell"}:
        raise ValueError(f"unsupported direction: {direction}")
    if not metric.metric_ready:
        return ConfirmationDecision(
            metric_ready=False,
            all_passed=False,
            checks={
                "120m_price": None,
                "30m_price": None,
                "5m_price": None,
                "5m_amount": None,
                "1m_price": None,
                "1m_amount": None,
            },
            action_mark=None,
            action_mark_reason=None,
            pending_reason=metric.error_summary or "metric_not_ready",
        )

    greater = direction == "buy"
    price = metric.current_price
    checks = {
        "120m_price": _strict_compare(
            price,
            metric.previous_120m_body_high
            if greater
            else metric.previous_120m_body_low,
            greater=greater,
        ),
        "30m_price": _strict_compare(
            price,
            metric.previous_30m_body_high
            if greater
            else metric.previous_30m_body_low,
            greater=greater,
        ),
        "5m_price": _strict_compare(
            price,
            metric.previous_5m_body_high
            if greater
            else metric.previous_5m_body_low,
            greater=greater,
        ),
        "5m_amount": (
            True
            if metric.first_5m_amount_default_pass
            else _strict_compare(
                metric.current_5m_virtual_amount,
                metric.previous_5m_full_amount,
                greater=greater,
            )
        ),
        "1m_price": _strict_compare(
            price,
            metric.previous_1m_body_high
            if greater
            else metric.previous_1m_body_low,
            greater=greater,
        ),
        "1m_amount": (
            True
            if metric.first_1m_amount_default_pass
            else _strict_compare(
                metric.current_1m_amount,
                metric.previous_1m_amount,
                greater=greater,
            )
        ),
    }
    all_passed = all(value is True for value in checks.values())
    action_mark = None
    mark_reason = None
    if all_passed:
        same_window = metric.previous_day_same_window_amount
        if same_window is None:
            action_mark = "normal"
            mark_reason = "previous_day_same_window_amount_missing"
        elif (
            direction == "buy"
            and metric.current_30m_virtual_amount is not None
            and metric.current_30m_virtual_amount > same_window
        ):
            action_mark = "30m_volume"
            mark_reason = "buy_30m_virtual_amount_stronger"
        elif (
            direction == "sell"
            and metric.current_30m_virtual_amount is not None
            and metric.current_30m_virtual_amount < same_window
        ):
            action_mark = "30m_shrink"
            mark_reason = "sell_30m_virtual_amount_weaker"
        else:
            action_mark = "normal"
            mark_reason = "same_window_30m_amount_condition_not_met"
    return ConfirmationDecision(
        metric_ready=True,
        all_passed=all_passed,
        checks=checks,
        action_mark=action_mark,
        action_mark_reason=mark_reason,
        pending_reason=None if all_passed else "confirmation_not_passed",
    )


def _validate_trigger_event(event: EventEnvelope, asset_kind: str) -> None:
    if event.source_layer != N4_SOURCE_LAYER:
        raise ValueError("N5 accepts only N4 trigger events")
    if event.event_type not in {"TriggerMatched", "TriggerStateChanged"}:
        raise ValueError(f"unsupported N4 event_type: {event.event_type}")
    if event.asset_kind != asset_kind:
        raise ValueError("N4 event asset_kind mismatch")
    payload = event.payload_json
    if str(payload.get("rule_policy_version") or "") != SOURCE_RULE_POLICY_VERSION:
        raise ValueError("unsupported N4 rule_policy_version")
    if str(payload.get("condition_key") or "") not in VALID_CONDITION_KEYS:
        raise ValueError("unsupported Windows state condition_key")
    signal_type = str(payload.get("signal_type") or "")
    direction = str(payload.get("direction") or "")
    if signal_type not in VALID_SIGNAL_TYPES:
        raise ValueError("unsupported runtime signal_type")
    if (signal_type == "B_BUY") != (direction == "buy"):
        raise ValueError("direction and signal_type mismatch")


def _matched_event_is_live(payload: Mapping[str, Any]) -> bool:
    return (
        bool(payload.get("trigger_live"))
        and str(payload.get("current_status") or "") == "matched"
        and str(payload.get("data_quality_status") or "") == "ready"
    )


def _episode_key(event: EventEnvelope, entry_id: str) -> EpisodeKey:
    payload = event.payload_json
    return EpisodeKey(
        trade_date=event.trade_date,
        asset_kind=event.asset_kind,
        identity_key=event.identity_key,
        direction=str(payload.get("direction") or ""),
        signal_type=str(payload.get("signal_type") or ""),
        condition_key=str(payload.get("condition_key") or ""),
        episode_entry_event_id=entry_id,
    )


def _trigger_grain(
    event: EventEnvelope,
    payload: Mapping[str, Any],
) -> TriggerGrain:
    return (
        event.trade_date,
        event.asset_kind,
        event.identity_key,
        str(payload.get("direction") or ""),
        str(payload.get("signal_type") or ""),
        str(payload.get("condition_key") or ""),
    )


def _trigger_grain_from_key(key: EpisodeKey) -> TriggerGrain:
    return (
        key.trade_date,
        key.asset_kind,
        key.identity_key,
        key.direction,
        key.signal_type,
        key.condition_key,
    )


def _tracking_until(event: EventEnvelope) -> datetime:
    base = datetime.strptime(event.trade_date, "%Y%m%d")
    return base.replace(
        hour=15,
        minute=0,
        tzinfo=event.event_time.tzinfo,
    )


def _event_snapshot(event: EventEnvelope) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "event_time": event.event_time,
        "source_run_id": event.source_run_id,
        "payload_json": dict(event.payload_json),
    }


def _event_time(snapshot: Mapping[str, Any]) -> datetime:
    value = snapshot.get("event_time")
    if not isinstance(value, datetime):
        raise ValueError("event snapshot missing event_time")
    return value


def _metric_proof(metric: ActionConfirmationMetric) -> dict[str, Any]:
    return {
        "source_basis": "N3T_C1_CLOSED",
        "metric_role": "action_confirmation",
        "proof_consumer": "N5",
        "not_n5_final_proof": False,
        "trade_date": metric.trade_date,
        "metric_policy_version": metric.metric_policy_version,
        "boundary_policy_version": metric.boundary_policy_version,
        "virtual_amount_policy_version": metric.virtual_amount_policy_version,
        "provider": metric.provider,
        "metric_time": metric.metric_time,
        "metric_minute_label": metric.metric_minute_label,
        "metric_minute_index": metric.expected_minute_index,
        "observed_minute_index": metric.observed_minute_index,
        "metric_quality_status": metric.metric_quality_status,
        "current_price": metric.current_price,
        "current_1m_close": metric.current_price,
        "previous_120m_body_high": metric.previous_120m_body_high,
        "previous_120m_body_low": metric.previous_120m_body_low,
        "previous_30m_body_high": metric.previous_30m_body_high,
        "previous_30m_body_low": metric.previous_30m_body_low,
        "previous_5m_body_high": metric.previous_5m_body_high,
        "previous_5m_body_low": metric.previous_5m_body_low,
        "previous_1m_body_high": metric.previous_1m_body_high,
        "previous_1m_body_low": metric.previous_1m_body_low,
        "current_5m_virtual_amount": metric.current_5m_virtual_amount,
        "previous_5m_full_amount": metric.previous_5m_full_amount,
        "current_1m_amount": metric.current_1m_amount,
        "previous_1m_amount": metric.previous_1m_amount,
        "current_30m_virtual_amount": metric.current_30m_virtual_amount,
        "previous_day_same_window_amount": (
            metric.previous_day_same_window_amount
        ),
        "previous_30m_full_amount": metric.previous_30m_full_amount,
        "is_first_1m_of_day": metric.is_first_1m_of_day,
        "is_first_5m_of_day": metric.is_first_5m_of_day,
        "first_1m_amount_default_pass": metric.first_1m_amount_default_pass,
        "first_5m_amount_default_pass": metric.first_5m_amount_default_pass,
        "previous_1m_period_source": metric.previous_1m_period_source,
        "previous_5m_period_source": metric.previous_5m_period_source,
        "previous_30m_period_source": metric.previous_30m_period_source,
        "previous_120m_period_source": metric.previous_120m_period_source,
        "amount_unit": metric.amount_unit,
    }


def _strict_compare(
    left: Decimal | None,
    right: Decimal | None,
    *,
    greater: bool,
) -> bool | None:
    if left is None or right is None:
        return None
    return left > right if greater else left < right


def _metric_reaches_close(metric: ActionConfirmationMetric) -> bool:
    if metric.expected_minute_index >= 240:
        return True
    if metric.metric_time is None:
        return False
    return metric.metric_time.time() >= time(15, 0)


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_integer(value: Any) -> int | None:
    if value is None:
        return None
    return _integer(value)
