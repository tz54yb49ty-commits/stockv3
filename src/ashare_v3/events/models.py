"""Common event envelope models and N3 contract validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


N3_SOURCE_LAYER = "N3_market_data"
N4_SOURCE_LAYER = "N4_trigger"
N5_SOURCE_LAYER = "N5_action"
DEFAULT_EVENT_SCHEMA_VERSION = "v1"
N3_EVENT_TYPES = (
    "MarketSnapshotUpdated",
    "MinuteBarClosed",
    "MinuteBarCorrected",
    "MarketDataDelayed",
    "MarketDataMissing",
    "MarketDisplaySnapshotUpdated",
)
N4_EVENT_TYPES = (
    "TriggerStateChanged",
    "TriggerMatched",
    "TriggerPendingMarketData",
)
N4_LEGACY_EVENT_TYPES = ("TriggerCleared", "TriggerLiveChanged")
N5_EVENT_TYPES = (
    "ActionEligible",
    "ActionBlocked",
    "ActionExecuted",
    "ActionSkipped",
)
N5_LEGACY_EVENT_TYPES = tuple(f"{prefix}Event" for prefix in ("Action", "Hint", "Risk", "Position"))
ASSET_KINDS = ("stock", "index", "board", "common")

N3_COMMON_PAYLOAD_KEYS = (
    "subscription_id",
    "pull_plan_id",
    "run_id",
    "source_adapter",
    "data_quality_status",
)
N3_EVENT_TRACE_KEYS = {
    "MarketSnapshotUpdated": ("snapshot_id",),
    "MarketDisplaySnapshotUpdated": ("snapshot_id",),
    "MinuteBarClosed": ("minute_bar_id",),
    "MinuteBarCorrected": ("minute_bar_id",),
    "MarketDataDelayed": ("quality_item_id",),
    "MarketDataMissing": ("quality_item_id",),
}
N3_MINUTE_BAR_CLOSED_V2_PAYLOAD_KEYS = (
    "source_minute_bar_ids",
    "source_minute_refs",
    "c2_run_id",
    "source_condition_run_id",
    "source_subscription_run_id",
    "source_today_minute_run_ids",
    "bucket_id",
    "bucket_start",
    "bucket_end",
    "closed_status",
    "replay_diff_json",
    "quality_status",
)
N4_COMMON_PAYLOAD_KEYS = (
    "run_id",
    "source_event_id",
    "identity_key",
    "asset_kind",
    "direction",
    "condition_key",
    "signal_type",
    "trigger_mark_candidate",
    "trigger_period",
    "match_basis",
    "data_quality_status",
)
N4_TRIGGER_STATE_CHANGED_PAYLOAD_KEYS = (
    "trigger_live",
    "previous_trigger_live",
    "current_status",
    "previous_status",
    "primary_trigger_period",
    "previous_primary_trigger_period",
    "all_trigger_periods",
    "previous_all_trigger_periods",
    "projection_30m_flag",
    "projection_30m_type",
    "previous_projection_30m_flag",
    "previous_projection_30m_type",
    "previous_trigger_mark_candidate",
    "state_change_reason",
    "source_outcome_event_type",
    "source_outcome_event_id",
)
N5_COMMON_PAYLOAD_KEYS = (
    "run_id",
    "source_trigger_event_id",
    "source_trigger_run_id",
    "source_trigger_state_id",
    "source_trigger_match_id",
    "source_condition_run_id",
    "action_key",
    "dedup_key",
    "identity_key",
    "asset_kind",
    "direction",
    "signal_type",
    "condition_key",
    "original_condition_key",
    "trigger_period",
    "action_state",
    "confirmation_status",
    "action_policy",
    "trace_json",
    "data_quality_status",
    "event_schema_version",
)
N5_TRIGGER_FACT_PASSTHROUGH_PAYLOAD_KEYS = (
    "n4_trigger_event_id",
    "trigger_price",
    "trigger_period",
    "triggered_periods",
    "all_trigger_periods",
    "primary_trigger_period",
    "trigger_kind",
    "period_trigger_baseline_trace",
    "baseline_source",
)
N4_DIRECTIONS = ("buy", "sell")
N5_ACTION_TYPES = (
    "buy_candidate",
    "sell_candidate",
    "clear_candidate",
    "pending_market_data",
    "risk_candidate",
)
N5_LANES = ("stock_trade", "stock_alert", "market_alert", "hint", "policy_pending")
N5_RUNTIME_SIGNAL_TYPES = ("B_BUY", "S_SELL")
N5_ACTION_MARKS = ("normal", "30m_volume", "30m_shrink")
N5_ACTION_STATES = ("eligible", "blocked", "executed", "skipped", "expired")
N5_CONFIRMATION_STATUSES = ("pending", "passed", "failed", "expired")
FORMAL_TRIGGER_PERIODS = ("Y", "Q", "M", "W", "D")
HINT_CONDITION_KEYS = ("BUY_HINT", "SELL_HINT")
WINDOWS_STATE_CONDITION_KEYS = ("BUY:STATE_V1", "SELL:STATE_V1")
WINDOWS_STATE_RULE_POLICY_VERSION = (
    "windows_n4_state_transition_v1"
)


class EventContractError(ValueError):
    """Raised when an event violates the v3 event contract."""


@dataclass(frozen=True)
class EventEnvelope:
    """Stable cross-layer event envelope.

    The envelope is pure data. It does not write to the database and does not
    commit transactions; repositories decide how to persist it.
    """

    event_id: str
    event_type: str
    event_schema_version: str
    trade_date: str
    asset_kind: str
    identity_key: str
    event_time: datetime
    source_layer: str
    source_run_id: str
    dedup_key: str
    partition_key: str
    payload_json: Mapping[str, Any]
    created_at: datetime

    def as_record(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_schema_version": self.event_schema_version,
            "trade_date": self.trade_date,
            "asset_kind": self.asset_kind,
            "identity_key": self.identity_key,
            "event_time": self.event_time,
            "source_layer": self.source_layer,
            "source_run_id": self.source_run_id,
            "dedup_key": self.dedup_key,
            "partition_key": self.partition_key,
            "payload_json": dict(self.payload_json),
            "created_at": self.created_at,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_n3_event_type(event_type: str) -> None:
    if event_type.startswith("User"):
        raise EventContractError("N3 event names must not use User* prefixes")
    if event_type not in N3_EVENT_TYPES:
        raise EventContractError(f"unsupported N3 event_type: {event_type}")


def validate_n4_event_type(event_type: str) -> None:
    if event_type.startswith("User"):
        raise EventContractError("N4 event names must not use User* prefixes")
    if event_type not in N4_EVENT_TYPES:
        raise EventContractError(f"unsupported N4 event_type: {event_type}")


def validate_n5_event_type(event_type: str) -> None:
    if event_type.startswith(("User", "Voice", "Sim")):
        raise EventContractError("N5 event names must not use User*, Voice*, or Sim* prefixes")
    if event_type not in N5_EVENT_TYPES:
        raise EventContractError(f"unsupported N5 event_type: {event_type}")


def validate_yyyymmdd(value: str, field_name: str) -> None:
    if len(value) != 8 or not value.isdigit():
        raise EventContractError(f"{field_name} must be YYYYMMDD")


def _payload_has_value(payload: Mapping[str, Any], key: str) -> bool:
    if key not in payload:
        return False
    value = payload[key]
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _payload_has_key_value_or_empty_collection(payload: Mapping[str, Any], key: str) -> bool:
    return key in payload and payload[key] is not None


def validate_minute_bar_closed_payload(event_schema_version: str, payload: Mapping[str, Any]) -> None:
    if event_schema_version != "v2":
        if not _payload_has_value(payload, "minute_bar_id"):
            raise EventContractError("N3 payload for MinuteBarClosed must include minute_bar_id")
        return

    if not (
        _payload_has_value(payload, "closed_30m_summary_id")
        or _payload_has_value(payload, "summary_id")
    ):
        raise EventContractError(
            "N3 MinuteBarClosed v2 payload must include closed_30m_summary_id or summary_id"
        )

    missing = [
        key
        for key in N3_MINUTE_BAR_CLOSED_V2_PAYLOAD_KEYS
        if not _payload_has_key_value_or_empty_collection(payload, key)
    ]
    if missing:
        raise EventContractError(
            f"N3 MinuteBarClosed v2 payload missing required summary trace fields: {', '.join(missing)}"
        )
    if not payload.get("source_minute_refs"):
        raise EventContractError("N3 MinuteBarClosed v2 payload requires non-empty source_minute_refs")


def validate_payload_trace_fields(
    event_type: str,
    payload: Mapping[str, Any],
    event_schema_version: str = DEFAULT_EVENT_SCHEMA_VERSION,
) -> None:
    missing = [key for key in N3_COMMON_PAYLOAD_KEYS if not payload.get(key)]
    if missing:
        raise EventContractError(f"N3 payload missing required trace fields: {', '.join(missing)}")

    if event_type == "MinuteBarClosed":
        validate_minute_bar_closed_payload(event_schema_version, payload)
        return

    trace_keys = N3_EVENT_TRACE_KEYS[event_type]
    if not any(payload.get(key) for key in trace_keys):
        raise EventContractError(
            f"N3 payload for {event_type} must include one of: {', '.join(trace_keys)}"
        )


def validate_n4_payload_fields(envelope: EventEnvelope) -> None:
    payload = envelope.payload_json
    missing = [
        key
        for key in N4_COMMON_PAYLOAD_KEYS
        if (key not in payload if key == "trigger_period" else not payload.get(key))
    ]
    if missing:
        raise EventContractError(f"N4 payload missing required fields: {', '.join(missing)}")

    asset_kind = str(payload.get("asset_kind") or "")
    identity_key = str(payload.get("identity_key") or "")
    direction = str(payload.get("direction") or "")
    condition_key = str(payload.get("condition_key") or "")
    signal_type = str(payload.get("signal_type") or "")
    if asset_kind != envelope.asset_kind:
        raise EventContractError("N4 payload asset_kind must match event envelope")
    if identity_key != envelope.identity_key:
        raise EventContractError("N4 payload identity_key must match event envelope")
    if direction not in N4_DIRECTIONS:
        raise EventContractError(f"unsupported N4 trigger direction: {direction}")
    if signal_type not in {"B_BUY", "S_SELL"}:
        raise EventContractError(f"unsupported N4 runtime signal_type: {signal_type}")
    if condition_key == "BUY_HINT" and direction != "buy":
        raise EventContractError("BUY_HINT must keep direction=buy in N4 payload")
    if condition_key == "SELL_HINT" and direction != "sell":
        raise EventContractError("SELL_HINT must keep direction=sell in N4 payload")
    if envelope.event_type == "TriggerStateChanged":
        missing_state = [
            key
            for key in N4_TRIGGER_STATE_CHANGED_PAYLOAD_KEYS
            if key not in payload
        ]
        if missing_state:
            raise EventContractError(
                f"TriggerStateChanged payload missing required fields: {', '.join(missing_state)}"
            )


def validate_n5_payload_fields(envelope: EventEnvelope) -> None:
    payload = envelope.payload_json
    missing = [key for key in N5_COMMON_PAYLOAD_KEYS if not _payload_has_value(payload, key)]
    if missing:
        raise EventContractError(f"N5 payload missing required fields: {', '.join(missing)}")
    if envelope.event_type in {"ActionEligible", "ActionBlocked", "ActionExecuted"}:
        validate_n5_trigger_fact_passthrough_payload(payload)

    asset_kind = str(payload.get("asset_kind") or "")
    identity_key = str(payload.get("identity_key") or "")
    direction = str(payload.get("direction") or "")
    signal_type = str(payload.get("signal_type") or "")
    condition_key = str(payload.get("condition_key") or "")
    original_condition_key = str(payload.get("original_condition_key") or "")
    action_state = str(payload.get("action_state") or "")
    confirmation_status = str(payload.get("confirmation_status") or "")
    action_mark = payload.get("action_mark")
    if asset_kind != envelope.asset_kind:
        raise EventContractError("N5 payload asset_kind must match event envelope")
    if identity_key != envelope.identity_key:
        raise EventContractError("N5 payload identity_key must match event envelope")
    if direction not in N4_DIRECTIONS:
        raise EventContractError(f"unsupported N5 action direction: {direction}")
    if condition_key == "BUY_HINT" and direction != "buy":
        raise EventContractError("BUY_HINT must keep direction=buy in N5 payload")
    if condition_key == "SELL_HINT" and direction != "sell":
        raise EventContractError("SELL_HINT must keep direction=sell in N5 payload")
    if original_condition_key == "BUY_HINT" and direction != "buy":
        raise EventContractError("BUY_HINT original_condition_key must keep direction=buy in N5 payload")
    if original_condition_key == "SELL_HINT" and direction != "sell":
        raise EventContractError("SELL_HINT original_condition_key must keep direction=sell in N5 payload")
    if signal_type not in N5_RUNTIME_SIGNAL_TYPES:
        raise EventContractError(f"unsupported N5 runtime signal_type: {signal_type}")
    if signal_type == "B_BUY" and direction != "buy":
        raise EventContractError("B_BUY must keep direction=buy in N5 payload")
    if signal_type == "S_SELL" and direction != "sell":
        raise EventContractError("S_SELL must keep direction=sell in N5 payload")
    if action_state not in N5_ACTION_STATES:
        raise EventContractError(f"unsupported N5 action_state: {action_state}")
    if confirmation_status not in N5_CONFIRMATION_STATUSES:
        raise EventContractError(f"unsupported N5 confirmation_status: {confirmation_status}")
    if "action_mark" not in payload:
        raise EventContractError("N5 payload missing required action_mark key")
    if action_mark is not None and str(action_mark) not in N5_ACTION_MARKS:
        raise EventContractError(f"unsupported N5 action_mark: {action_mark}")
    if envelope.event_type == "ActionEligible" and action_state != "eligible":
        raise EventContractError("ActionEligible payload must use action_state=eligible")
    if envelope.event_type == "ActionBlocked" and action_state != "blocked":
        raise EventContractError("ActionBlocked payload must use action_state=blocked")
    if envelope.event_type == "ActionExecuted":
        if action_state != "executed":
            raise EventContractError("ActionExecuted payload must use action_state=executed")
        if str(action_mark or "") not in N5_ACTION_MARKS:
            raise EventContractError("ActionExecuted payload must include final canonical action_mark")
    if envelope.event_type == "ActionSkipped" and action_state not in {"skipped", "expired"}:
        raise EventContractError("ActionSkipped payload must use action_state=skipped or expired")
    if not (payload.get("source_market_data_run_id") or payload.get("source_market_trace")):
        raise EventContractError(
            "N5 payload must include source_market_data_run_id or source_market_trace"
        )


def validate_n5_trigger_fact_passthrough_payload(payload: Mapping[str, Any]) -> None:
    trigger_kind = str(payload.get("trigger_kind") or "")
    condition_key = str(payload.get("condition_key") or payload.get("original_condition_key") or "")
    original_condition_key = str(payload.get("original_condition_key") or condition_key)
    is_hint = trigger_kind == "hint" and condition_key in HINT_CONDITION_KEYS and original_condition_key in HINT_CONDITION_KEYS
    is_windows_state_v1 = (
        trigger_kind == "trigger"
        and condition_key in WINDOWS_STATE_CONDITION_KEYS
        and original_condition_key == condition_key
        and str(payload.get("rule_policy_version") or "")
        == WINDOWS_STATE_RULE_POLICY_VERSION
    )
    period_keys = {"triggered_periods", "all_trigger_periods", "primary_trigger_period"}
    missing = [
        key
        for key in N5_TRIGGER_FACT_PASSTHROUGH_PAYLOAD_KEYS
        if key not in period_keys
        and not (is_windows_state_v1 and key == "trigger_price")
        and not _payload_has_value(payload, key)
    ]
    for key in period_keys:
        if key not in payload:
            missing.append(key)
    period_trace = payload.get("period_trigger_baseline_trace")
    if not isinstance(period_trace, Mapping) or not period_trace:
        missing.append("period_trigger_baseline_trace")
    if missing:
        unique_missing = sorted(set(missing))
        raise EventContractError(
            "N5 trigger fact passthrough payload missing required fields: "
            + ", ".join(unique_missing)
        )

    trigger_period = str(payload.get("trigger_period") or "").strip()
    triggered_periods = _trigger_period_values(payload.get("triggered_periods"))
    all_trigger_periods = _trigger_period_values(payload.get("all_trigger_periods"))
    primary_trigger_period = str(payload.get("primary_trigger_period") or "").strip()
    formal_sets = triggered_periods + all_trigger_periods + ([primary_trigger_period] if primary_trigger_period else [])
    if "30m" in formal_sets:
        raise EventContractError(
            "N5 trigger fact passthrough payload must not include 30m in "
            "triggered_periods/all_trigger_periods/primary_trigger_period"
        )
    invalid_formal = [period for period in formal_sets if period not in FORMAL_TRIGGER_PERIODS]
    if invalid_formal:
        raise EventContractError(
            "N5 trigger fact passthrough payload has invalid formal trigger periods: "
            + ", ".join(sorted(set(invalid_formal)))
        )
    if is_hint:
        if trigger_period != "30m":
            raise EventContractError("N5 hint trigger fact passthrough requires trigger_period=30m")
        if triggered_periods or all_trigger_periods or primary_trigger_period:
            raise EventContractError("N5 hint trigger fact passthrough requires empty formal trigger periods")
        return
    if trigger_kind == "trigger":
        if trigger_period == "30m":
            if not is_windows_state_v1:
                raise EventContractError(
                    "N5 ordinary trigger fact passthrough must not use trigger_period=30m"
                )
            if triggered_periods or all_trigger_periods or primary_trigger_period:
                raise EventContractError(
                    "N5 Windows STATE_V1 30m fallback requires empty formal trigger periods"
                )
            return
        if trigger_period not in FORMAL_TRIGGER_PERIODS:
            raise EventContractError("N5 ordinary trigger fact passthrough requires trigger_period Y/Q/M/W/D")
        if not triggered_periods or not all_trigger_periods or not primary_trigger_period:
            raise EventContractError(
                "N5 ordinary trigger fact passthrough requires non-empty formal trigger periods"
            )
        return
    raise EventContractError("N5 trigger fact passthrough payload has invalid trigger_kind")


def _trigger_period_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                import json

                parsed = json.loads(text)
            except (TypeError, ValueError):
                return [text]
            return _trigger_period_values(parsed)
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def validate_event_envelope(envelope: EventEnvelope) -> None:
    if not envelope.event_id:
        raise EventContractError("event_id is required")
    if not envelope.dedup_key:
        raise EventContractError("dedup_key is required")
    if not envelope.partition_key:
        raise EventContractError("partition_key is required")
    if envelope.asset_kind not in ASSET_KINDS:
        raise EventContractError(f"unsupported asset_kind: {envelope.asset_kind}")
    validate_yyyymmdd(envelope.trade_date, "trade_date")
    if envelope.source_layer == N3_SOURCE_LAYER:
        validate_n3_event_type(envelope.event_type)
        validate_payload_trace_fields(
            envelope.event_type,
            envelope.payload_json,
            envelope.event_schema_version,
        )
    if envelope.source_layer == N4_SOURCE_LAYER:
        validate_n4_event_type(envelope.event_type)
        validate_n4_payload_fields(envelope)
    if envelope.source_layer == N5_SOURCE_LAYER:
        validate_n5_event_type(envelope.event_type)
        validate_n5_payload_fields(envelope)
