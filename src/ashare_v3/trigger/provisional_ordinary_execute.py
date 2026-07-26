"""N4P ordinary TriggerMatched execute contract.

This module persists N4P ordinary dry-run plans produced from N3P trigger
proof metrics. It is isolated from the legacy projection matcher execute route
and only writes N4 trigger facts plus outbox when explicitly called by a
confirmed runner.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.events.ids import build_stable_event_id, join_dedup_parts
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    EventEnvelope,
    N4_SOURCE_LAYER,
    utc_now,
    validate_event_envelope,
)
from ashare_v3.trigger.provisional_ordinary_matcher import (
    HINT_CONDITION_KEYS,
    ORDINARY_CONDITION_SIGNAL_TYPES,
    SAME_DAY_FORMAL_EVIDENCE_SOURCE,
    SOURCE_METRIC_KIND,
    assert_same_day_period_escalation_output_contract,
    build_provisional_ordinary_matcher_plans,
)
from ashare_v3.trigger.provisional_projection_execute import to_jsonable
from ashare_v3.trigger.provisional_trigger_lifecycle import (
    TRIGGER_MATCHED_EVENT_TYPE,
    TRIGGER_STATE_CHANGED_EVENT_TYPE,
    build_lifecycle_output_plans,
    lifecycle_state_key,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect, audited_n4_trigger_connect


N4P_ORDINARY_ALLOWED_WRITE_TABLES = frozenset(
    {
        "common_trigger_run",
        "common_trigger_quality_item",
        "common_trigger_state",
        "common_trigger_match",
        "common_event_outbox",
    }
)
N4P_ORDINARY_FORBIDDEN_WRITE_TABLES = frozenset(
    {
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "common_action_run",
        "common_action_event",
        "stock_action_fact",
        "index_action_fact",
        "board_action_fact",
        "user_signal_projection",
        "user_card_projection",
        "user_notification_queue",
        "n6_virtual_account",
        "n6_virtual_order",
        "n6_virtual_trade",
        "n6_virtual_position",
        "sim_projection",
        "real_trade_order",
        "voice_delivery",
        "mobile_push",
    }
)
N4P_ORDINARY_ROLLBACK_DOWNSTREAM_GUARD_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_action_run",
    "common_action_event",
    "common_action_quality_item",
    "common_action_tracking_state",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_signal_card_projection",
    "user_signal_projection_event",
    "user_notification_queue",
    "user_card_projection",
    "user_voice_delivery",
    "user_device_ack",
    "sim_projection",
    "sim_account",
    "sim_order",
    "sim_trade",
    "sim_position",
    "n6_virtual_account",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_position",
    "real_trade_order",
    "voice_delivery",
    "mobile_push",
)
ORDINARY_TRIGGER_EVENT_TYPE = TRIGGER_MATCHED_EVENT_TYPE
ORDINARY_STATE_CHANGED_EVENT_TYPE = TRIGGER_STATE_CHANGED_EVENT_TYPE
ORDINARY_SOURCE_EVENT_TYPE = "MarketSnapshotUpdated"
ORDINARY_SOURCE_METRIC_EVENT_TYPE = "N3PRealtimeActionMetric"
N3P_TRIGGER_PROOF_KIND = "n3p_formal_amount_chain"
N3P_TRIGGER_PROOF_ROLE = "trigger_proof"
N3P_TRIGGER_PROOF_OWNER = "N3"
N3P_TRIGGER_PROOF_CONSUMER = "N4"
DEFAULT_GENERATED_BY = "n4p_provisional_ordinary_execute_v1"
PERIOD_PRIORITY = ("Y", "Q", "M", "W", "D")
VALID_TRIGGER_PERIODS = frozenset((*PERIOD_PRIORITY, "30m"))
ATOMIC_RULE_SUFFIX_RE = re.compile(r"^atomic_rule_v\d+$")
N4_RULE_SUFFIX_PERIOD_ROLLOVER_GUARD_V1 = "period_rollover_guard_v1"
ALLOWED_N4_RULE_SUFFIXES = frozenset({N4_RULE_SUFFIX_PERIOD_ROLLOVER_GUARD_V1})
RULE_SUFFIX_RE = re.compile(r"^(?P<atomic_rule_suffix>atomic_rule_v\d+)(?:_(?P<n4_rule_suffix>period_rollover_guard_v1))?$")
DEFAULT_SOURCE_VARIANT = "default"
AMOUNT_CHAIN_V2_SOURCE_VARIANT = "live_current_1m_amount_chain_v2"
AMOUNT_CHAIN_V2_LIFECYCLE_V2_SOURCE_VARIANT = "live_current_1m_amount_chain_v2_lifecycle_v2"
AMOUNT_CHAIN_V2_CORRECTED_REPLAY_SOURCE_VARIANT = "live_current_1m_amount_chain_v2_corrected_replay"
AMOUNT_CHAIN_V2_UNIFIED_PAYLOAD_V1_SOURCE_VARIANT = "live_current_1m_amount_chain_v2_unified_payload_v1"
AMOUNT_CHAIN_V2_ASSET_UNIT_FIX_V1_SOURCE_VARIANT = "live_current_1m_amount_chain_v2_asset_unit_fix_v1"
B1_SOURCE_RETURNED_SNAPSHOT_AMOUNT_CHAIN_V2_ASSET_UNIT_FIX_V1_SOURCE_VARIANT = (
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1"
)
B1_SOURCE_RETURNED_SNAPSHOT_CURRENT_PERIOD_AVG_V1_SOURCE_VARIANT = (
    "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
)
NO_PREVIOUS_BASELINE_MODE = "no_previous_baseline"
ALLOWED_SOURCE_VARIANTS = frozenset(
    {
        DEFAULT_SOURCE_VARIANT,
        AMOUNT_CHAIN_V2_SOURCE_VARIANT,
        AMOUNT_CHAIN_V2_LIFECYCLE_V2_SOURCE_VARIANT,
        AMOUNT_CHAIN_V2_CORRECTED_REPLAY_SOURCE_VARIANT,
        AMOUNT_CHAIN_V2_UNIFIED_PAYLOAD_V1_SOURCE_VARIANT,
        AMOUNT_CHAIN_V2_ASSET_UNIT_FIX_V1_SOURCE_VARIANT,
        B1_SOURCE_RETURNED_SNAPSHOT_AMOUNT_CHAIN_V2_ASSET_UNIT_FIX_V1_SOURCE_VARIANT,
        B1_SOURCE_RETURNED_SNAPSHOT_CURRENT_PERIOD_AVG_V1_SOURCE_VARIANT,
    }
)
RUN_ID_RE = re.compile(
    r"^trigger_provisional_ordinary_"
    r"(?P<for_trade_date>\d{8})_until_(?P<until_hhmm>\d{4})"
    r"__realtime_action_confirmation_metric_"
    r"(?P=for_trade_date)_until_(?P=until_hhmm)"
    r"(?:__(?P<asset_scope>asset_(?:all|stock|index|board)))?"
    r"(?P<source_variant_suffix>(?:__(?:live_current_1m_amount_chain_v2|live_current_1m_amount_chain_v2_lifecycle_v2|live_current_1m_amount_chain_v2_corrected_replay|live_current_1m_amount_chain_v2_unified_payload_v1|live_current_1m_amount_chain_v2_asset_unit_fix_v1|b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1|b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1))?)"
    r"(?:__(?P<rule_suffix>atomic_rule_v\d+(?:_period_rollover_guard_v1)?))?$"
)


class N4POrdinaryExecuteBlocked(RuntimeError):
    """Raised when N4P ordinary execute must fail closed."""


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000.0, 3)


def build_n4p_ordinary_trigger_run_id(
    *,
    for_trade_date: str,
    until_hhmm: str,
    asset_scope: str = "asset_all",
    source_variant: str = DEFAULT_SOURCE_VARIANT,
    source_metric_run_id: str = "",
    rule_suffix: str = "",
    n4_rule_suffix: str = "",
) -> str:
    if len(for_trade_date) != 8 or not for_trade_date.isdigit():
        raise N4POrdinaryExecuteBlocked(f"invalid for_trade_date: {for_trade_date}")
    if len(until_hhmm) != 4 or not until_hhmm.isdigit():
        raise N4POrdinaryExecuteBlocked(f"invalid until_hhmm: {until_hhmm}")
    if asset_scope not in {"asset_all", "asset_stock", "asset_index", "asset_board"}:
        raise N4POrdinaryExecuteBlocked(f"invalid asset_scope: {asset_scope}")
    if source_metric_run_id:
        source_variant = source_variant_from_metric_run_id(source_metric_run_id, default=source_variant)
    if source_variant not in ALLOWED_SOURCE_VARIANTS:
        raise N4POrdinaryExecuteBlocked(f"invalid source_variant: {source_variant}")
    if source_variant != DEFAULT_SOURCE_VARIANT and not rule_suffix:
        raise N4POrdinaryExecuteBlocked(f"rule_suffix is required for source_variant: {source_variant}")
    if rule_suffix and not ATOMIC_RULE_SUFFIX_RE.match(rule_suffix):
        raise N4POrdinaryExecuteBlocked(f"invalid rule_suffix: {rule_suffix}")
    if n4_rule_suffix and n4_rule_suffix not in ALLOWED_N4_RULE_SUFFIXES:
        raise N4POrdinaryExecuteBlocked(f"invalid n4_rule_suffix: {n4_rule_suffix}")
    if n4_rule_suffix and rule_suffix != "atomic_rule_v1":
        raise N4POrdinaryExecuteBlocked(f"invalid rule_suffix for n4_rule_suffix {n4_rule_suffix}: {rule_suffix}")
    if source_variant != DEFAULT_SOURCE_VARIANT and rule_suffix != "atomic_rule_v1":
        raise N4POrdinaryExecuteBlocked(f"invalid rule_suffix for source_variant {source_variant}: {rule_suffix}")
    full_rule_suffix = f"{rule_suffix}_{n4_rule_suffix}" if n4_rule_suffix else rule_suffix
    return (
        f"trigger_provisional_ordinary_{for_trade_date}_until_{until_hhmm}"
        f"__realtime_action_confirmation_metric_{for_trade_date}_until_{until_hhmm}"
        f"__{asset_scope}"
        f"{f'__{source_variant}' if source_variant != DEFAULT_SOURCE_VARIANT else ''}"
        f"{f'__{full_rule_suffix}' if full_rule_suffix else ''}"
    )


def parse_n4p_ordinary_trigger_run_id(run_id: str) -> dict[str, str]:
    matched = RUN_ID_RE.match(str(run_id or ""))
    if not matched:
        raise N4POrdinaryExecuteBlocked(f"invalid N4P ordinary trigger_run_id: {run_id}")
    source_variant_suffix = str(matched.group("source_variant_suffix") or "")
    source_variant = source_variant_suffix.removeprefix("__") if source_variant_suffix else DEFAULT_SOURCE_VARIANT
    if source_variant not in ALLOWED_SOURCE_VARIANTS:
        raise N4POrdinaryExecuteBlocked(f"invalid N4P ordinary trigger_run_id: {run_id}")
    rule_suffix = matched.group("rule_suffix") or ""
    rule_suffix_parts = parse_n4p_ordinary_rule_suffix(rule_suffix)
    atomic_rule_suffix = rule_suffix_parts["atomic_rule_suffix"]
    n4_rule_suffix = rule_suffix_parts["n4_rule_suffix"]
    asset_scope = matched.group("asset_scope") or "legacy"
    if source_variant != DEFAULT_SOURCE_VARIANT and asset_scope == "legacy":
        raise N4POrdinaryExecuteBlocked(f"invalid N4P ordinary trigger_run_id: {run_id}")
    if source_variant != DEFAULT_SOURCE_VARIANT and not rule_suffix:
        raise N4POrdinaryExecuteBlocked(f"invalid N4P ordinary trigger_run_id: {run_id}")
    if source_variant != DEFAULT_SOURCE_VARIANT and atomic_rule_suffix != "atomic_rule_v1":
        raise N4POrdinaryExecuteBlocked(f"invalid N4P ordinary trigger_run_id: {run_id}")
    return {
        "run_id": run_id,
        "for_trade_date": matched.group("for_trade_date"),
        "until_hhmm": matched.group("until_hhmm"),
        "source_metric_prefix": SOURCE_METRIC_KIND,
        "source_metric_date": matched.group("for_trade_date"),
        "source_metric_until_hhmm": matched.group("until_hhmm"),
        "asset_scope": asset_scope,
        "source_variant": source_variant,
        "rule_suffix": rule_suffix,
        "atomic_rule_suffix": atomic_rule_suffix,
        "n4_rule_suffix": n4_rule_suffix,
        "mode": "provisional_ordinary",
        "source_metric_kind": SOURCE_METRIC_KIND,
    }


def parse_n4p_ordinary_rule_suffix(rule_suffix: str) -> dict[str, str]:
    if not rule_suffix:
        return {"atomic_rule_suffix": "", "n4_rule_suffix": ""}
    matched = RULE_SUFFIX_RE.match(str(rule_suffix))
    if not matched:
        raise N4POrdinaryExecuteBlocked(f"invalid N4P ordinary rule_suffix: {rule_suffix}")
    atomic_rule_suffix = str(matched.group("atomic_rule_suffix") or "")
    n4_rule_suffix = str(matched.group("n4_rule_suffix") or "")
    if n4_rule_suffix and n4_rule_suffix not in ALLOWED_N4_RULE_SUFFIXES:
        raise N4POrdinaryExecuteBlocked(f"invalid N4P ordinary rule_suffix: {rule_suffix}")
    if n4_rule_suffix and atomic_rule_suffix != "atomic_rule_v1":
        raise N4POrdinaryExecuteBlocked(f"invalid N4P ordinary rule_suffix: {rule_suffix}")
    return {"atomic_rule_suffix": atomic_rule_suffix, "n4_rule_suffix": n4_rule_suffix}


def source_variant_from_metric_run_id(source_metric_run_id: str, *, default: str) -> str:
    metric_run_id = str(source_metric_run_id or "")
    if metric_run_id.startswith("realtime_projection_metric_"):
        raise N4POrdinaryExecuteBlocked(f"unsupported ordinary source_metric_run_id: {source_metric_run_id}")
    if not metric_run_id.startswith(f"{SOURCE_METRIC_KIND}_"):
        raise N4POrdinaryExecuteBlocked(f"unsupported ordinary source_metric_run_id: {source_metric_run_id}")
    for variant in sorted(ALLOWED_SOURCE_VARIANTS - {DEFAULT_SOURCE_VARIANT}, key=len, reverse=True):
        if f"__{variant}__" in metric_run_id:
            return variant
    if "amount_chain_" in metric_run_id:
        raise N4POrdinaryExecuteBlocked(f"unsupported source_metric_run_id variant: {source_metric_run_id}")
    return default


def ordered_ordinary_triggered_periods(plan: Mapping[str, Any]) -> list[str]:
    raw_periods = plan.get("triggered_periods") or plan.get("all_trigger_periods") or []
    if not raw_periods and plan.get("trigger_period"):
        raw_periods = [plan.get("trigger_period")]
    available = {str(period) for period in raw_periods if str(period or "") in PERIOD_PRIORITY}
    return [period for period in PERIOD_PRIORITY if period in available]


def ordinary_trigger_period_for_plan(plan: Mapping[str, Any], *, triggered_periods: Sequence[str]) -> str:
    if triggered_periods:
        return str(triggered_periods[0])
    if str(plan.get("output_event_type") or "") == ORDINARY_STATE_CHANGED_EVENT_TYPE:
        previous_period = first_valid_trigger_period(
            [
                plan.get("previous_primary_trigger_period"),
                plan.get("previous_trigger_period"),
                plan.get("previous_triggered_periods"),
                plan.get("previous_all_trigger_periods"),
            ]
        )
        if previous_period:
            return previous_period
        condition_period = first_valid_trigger_period(periods_from_condition_key(str(plan.get("condition_key") or "")))
        if condition_period:
            return condition_period
        raise N4POrdinaryExecuteBlocked(
            "valid trigger_period is required for ordinary TriggerStateChanged: "
            f"condition_key={plan.get('condition_key')}"
        )
    period = valid_trigger_period(plan.get("trigger_period"))
    if period:
        return period
    raise N4POrdinaryExecuteBlocked(
        "valid trigger_period is required for ordinary TriggerMatched: "
        f"condition_key={plan.get('condition_key')}"
    )


def valid_trigger_period(value: Any) -> str | None:
    text = str(value or "")
    return text if text in VALID_TRIGGER_PERIODS else None


def first_valid_trigger_period(values: Any) -> str | None:
    if values is None or values == "":
        return None
    if isinstance(values, (str, bytes)):
        return valid_trigger_period(values)
    if isinstance(values, Sequence):
        for value in values:
            period = valid_trigger_period(value)
            if period:
                return period
    return valid_trigger_period(values)


def periods_from_condition_key(condition_key: str) -> list[str]:
    if ":" not in condition_key:
        return []
    raw_periods = condition_key.split(":", 1)[1].split(",")
    available = {period.strip() for period in raw_periods if period.strip() in PERIOD_PRIORITY}
    return [period for period in PERIOD_PRIORITY if period in available]


def ordinary_trigger_price_for_period(plan: Mapping[str, Any], trigger_period: str) -> Any:
    rule_proof = plan.get("rule_proof")
    rule_proof = rule_proof if isinstance(rule_proof, Mapping) else {}
    for detail_key in ("triggered_period_details", "period_evaluation_details"):
        details = rule_proof.get(detail_key)
        if not isinstance(details, Sequence) or isinstance(details, (str, bytes)):
            continue
        for detail in details:
            if not isinstance(detail, Mapping):
                continue
            if str(detail.get("period") or "") == trigger_period:
                return detail.get("current_price_or_close")
    return plan.get("trigger_price")


def pre_enrich_ordinary_lifecycle_plan(plan: Mapping[str, Any], *, for_trade_date: str) -> dict[str, Any]:
    current = dict(plan)
    current["for_trade_date"] = for_trade_date
    current["projection_30m_flag"] = bool(current.get("projection_30m_flag") or False)
    current["projection_30m_type"] = str(current.get("projection_30m_type") or "none")
    current["trigger_mark_candidate"] = str(current.get("trigger_mark_candidate") or "none")

    is_matched = (
        str(current.get("plan_status") or "") == "matched"
        or str(current.get("output_event_type") or "") == ORDINARY_TRIGGER_EVENT_TYPE
        or str(current.get("current_status") or "") == "matched"
    )
    if is_matched:
        _assert_ordinary_lifecycle_plan(current)
        triggered_periods = ordered_ordinary_triggered_periods(current)
        trigger_period = ordinary_trigger_period_for_plan(current, triggered_periods=triggered_periods)
        if not triggered_periods:
            triggered_periods = [trigger_period]
        trigger_price = ordinary_trigger_price_for_period(current, trigger_period)
        same_day_plan = _is_same_day_period_escalation_plan(current)
        current.update(
            {
                "current_status": "matched",
                "trigger_live": True,
                "trigger_period": trigger_period,
                "primary_trigger_period": (
                    current.get("primary_trigger_period")
                    if same_day_plan
                    else current.get("primary_trigger_period") or trigger_period
                ),
                "triggered_periods": triggered_periods,
                "all_trigger_periods": (
                    list(current.get("all_trigger_periods"))
                    if same_day_plan
                    else list(current.get("all_trigger_periods") or triggered_periods)
                ),
                "trigger_price": trigger_price,
            }
        )
    elif str(current.get("current_status") or "") in {"inactive", "pending_market_data"}:
        current["trigger_live"] = False
    return current


def assert_n4p_ordinary_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise N4POrdinaryExecuteBlocked("N4P ordinary execute blocked: missing " + ", ".join(missing))


def build_provisional_ordinary_execute_plan(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    source_metric_run: Mapping[str, Any],
    trigger_context_run_id: str,
    source_metric_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    dry_run_plans: Sequence[Mapping[str, Any]],
    context_snapshot_row_count: int,
    target_counts: Mapping[str, int],
    previous_trigger_states: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    parsed_run_id = parse_n4p_ordinary_trigger_run_id(trigger_run_id)
    if parsed_run_id["for_trade_date"] != for_trade_date:
        raise N4POrdinaryExecuteBlocked(
            f"trigger_run_id trade date mismatch: {parsed_run_id['for_trade_date']} != {for_trade_date}"
        )
    _require_passed_run(trigger_context_run, expected_run_id=trigger_context_run_id, run_kind="trigger_context_run")
    _require_passed_run(source_metric_run, expected_run_id=source_metric_run_id, run_kind="source_metric_run")
    _assert_target_absent(target_counts)

    normalized_dry_run_plans = [
        pre_enrich_ordinary_lifecycle_plan(plan, for_trade_date=for_trade_date)
        for plan in dry_run_plans
    ]
    lifecycle_plans = build_lifecycle_output_plans(
        normalized_dry_run_plans,
        previous_states=previous_trigger_states,
    )
    matched_plans = _dedupe_lifecycle_plans(lifecycle_plans, event_type=ORDINARY_TRIGGER_EVENT_TYPE)
    state_changed_plans = _dedupe_lifecycle_plans(lifecycle_plans, event_type=ORDINARY_STATE_CHANGED_EVENT_TYPE)
    now = utc_now()
    state_rows: list[dict[str, Any]] = []
    match_rows: list[dict[str, Any]] = []
    outbox_rows: list[dict[str, Any]] = []
    enriched_plans: list[dict[str, Any]] = []
    for plan in [*matched_plans, *state_changed_plans]:
        enriched = enrich_ordinary_plan(
            plan,
            trigger_run_id=trigger_run_id,
            trigger_context_run_id=trigger_context_run_id,
            source_metric_run_id=source_metric_run_id,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=for_trade_date,
        )
        state_row = build_ordinary_trigger_state_row(
            trigger_run_id=trigger_run_id,
            trigger_context_run=trigger_context_run,
            plan=enriched,
            created_at=now,
        )
        envelope = build_ordinary_trigger_matched_envelope(
            trigger_run_id=trigger_run_id,
            trigger_context_run=trigger_context_run,
            plan=enriched,
            output_event_id=str(enriched["output_event_id"]),
            trigger_state_id=None,
            trigger_match_id=None,
            created_at=now,
        )
        enriched_plans.append(enriched)
        state_rows.append(state_row)
        if enriched.get("output_event_type") == ORDINARY_TRIGGER_EVENT_TYPE:
            match_row = build_ordinary_trigger_match_row(
                trigger_run_id=trigger_run_id,
                trigger_context_run=trigger_context_run,
                plan=enriched,
                output_event_id=str(enriched["output_event_id"]),
                created_at=now,
            )
            match_rows.append(match_row)
        outbox_rows.append(envelope.as_record())

    run_row = build_ordinary_trigger_run_row(
        trigger_run_id=trigger_run_id,
        trigger_context_run=trigger_context_run,
        source_metric_run=source_metric_run,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        trigger_context_run_id=trigger_context_run_id,
        source_metric_run_id=source_metric_run_id,
        context_snapshot_row_count=context_snapshot_row_count,
        candidate_count=len(dry_run_plans),
        matched_count=len(matched_plans),
        state_count=len(state_rows),
        match_count=len(match_rows),
        outbox_count=len(outbox_rows),
        created_at=now,
    )
    writes = {
        "common_trigger_run": [run_row],
        "common_trigger_quality_item": build_ordinary_quality_items(
            trigger_run_id=trigger_run_id,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=for_trade_date,
            source_trade_date=str(trigger_context_run.get("source_trade_date") or ""),
            dry_run_plans=normalized_dry_run_plans,
            matched_count=len(matched_plans),
            created_at=now,
        ),
        "common_trigger_state": state_rows,
        "common_trigger_match": match_rows,
        "common_event_outbox": outbox_rows,
    }
    return {
        "result": "EXECUTE_PLAN_READY",
        "status": "passed",
        "layer_role": "N4_trigger",
        "trigger_run_id": trigger_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "source_metric_kind": SOURCE_METRIC_KIND,
        "source_metric_run_id": source_metric_run_id,
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "candidate_count": len(normalized_dry_run_plans),
        "matched_count": len(matched_plans),
        "state_changed_count": len(state_changed_plans),
        "noop_count": len(normalized_dry_run_plans) - len(lifecycle_plans),
        "summary": summarize_ordinary_execute_plans(enriched_plans, candidate_count=len(normalized_dry_run_plans)),
        "writes": writes,
        "write_counts": {table_name: len(rows) for table_name, rows in writes.items()},
        "allowed_write_tables": sorted(N4P_ORDINARY_ALLOWED_WRITE_TABLES),
        "forbidden_write_counts": {table_name: 0 for table_name in sorted(N4P_ORDINARY_FORBIDDEN_WRITE_TABLES)},
        "event_model": {
            "output_event_types": sorted({str(plan.get("output_event_type")) for plan in [*matched_plans, *state_changed_plans]}),
            "writes_pending_market_data": False,
            "writes_state_changed": bool(state_changed_plans),
            "consumes_source_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "enters_n5": bool(matched_plans),
        },
        "side_effect_guard": {
            "db_written": True,
            "trigger_run_written": bool(writes["common_trigger_run"]),
            "trigger_state_written": bool(writes["common_trigger_state"]),
            "trigger_match_written": bool(writes["common_trigger_match"]),
            "outbox_written": bool(writes["common_event_outbox"]),
            "inbox_written": False,
            "checkpoint_written": False,
            "n5_executed": False,
            "n6_written": False,
            "sim_trade_virtual_written": False,
            "worker_started": False,
        },
        "dry_run_plans": [to_jsonable(dict(plan)) for plan in normalized_dry_run_plans],
    }


def enrich_ordinary_plan(
    plan: Mapping[str, Any],
    *,
    trigger_run_id: str,
    trigger_context_run_id: str,
    source_metric_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    _assert_ordinary_lifecycle_plan(plan)
    output_event_type = str(plan.get("output_event_type") or "")
    selected_metric_id = _required_text(plan.get("selected_metric_id"), "selected_metric_id")
    source_event_id = f"N3P:{source_metric_run_id}:{selected_metric_id}"
    dedup_key = build_ordinary_dedup_key(
        trigger_run_id=trigger_run_id,
        source_event_id=source_event_id,
        plan=plan,
        event_type=output_event_type,
    )
    output_event_id = build_stable_event_id(
        source_layer=N4_SOURCE_LAYER,
        event_type=output_event_type,
        source_run_id=trigger_run_id,
        dedup_key=dedup_key,
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
    )
    triggered_periods = ordered_ordinary_triggered_periods(plan)
    trigger_period = ordinary_trigger_period_for_plan(plan, triggered_periods=triggered_periods)
    if not triggered_periods and str(plan.get("output_event_type") or "") == ORDINARY_STATE_CHANGED_EVENT_TYPE:
        triggered_periods = [trigger_period]
    trigger_price = ordinary_trigger_price_for_period(plan, trigger_period)
    same_day_plan = _is_same_day_period_escalation_plan(plan)
    current_status = str(plan.get("current_status") or "matched")
    if current_status == "matched":
        trigger_live = True
    elif current_status in {"inactive", "pending_market_data"}:
        trigger_live = False
    else:
        trigger_live = bool(plan.get("trigger_live"))
    enriched = {
        **dict(plan),
        "run_id": trigger_run_id,
        "source_event_id": source_event_id,
        "source_event_type": ORDINARY_SOURCE_EVENT_TYPE,
        "source_metric_event_type": ORDINARY_SOURCE_METRIC_EVENT_TYPE,
        "trigger_context_run_id": trigger_context_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_metric_kind": SOURCE_METRIC_KIND,
        "source_metric_run_id": source_metric_run_id,
        "metric_role": N3P_TRIGGER_PROOF_ROLE,
        "proof_owner": N3P_TRIGGER_PROOF_OWNER,
        "proof_consumer": N3P_TRIGGER_PROOF_CONSUMER,
        "not_n5_final_proof": True,
        "source_trigger_proof_kind": N3P_TRIGGER_PROOF_KIND,
        "source_trigger_proof_run_id": source_metric_run_id,
        "source_trigger_proof_metric_id": plan.get("selected_metric_id"),
        "source_trigger_proof_time": plan.get("selected_metric_time"),
        "for_trade_date": for_trade_date,
        "direction": direction_for_plan(plan),
        "trigger_period": trigger_period,
        "triggered_periods": triggered_periods,
        "trigger_price": trigger_price,
        "primary_trigger_period": (
            plan.get("primary_trigger_period")
            if same_day_plan
            else plan.get("primary_trigger_period") or trigger_period
        ),
        "all_trigger_periods": (
            list(plan.get("all_trigger_periods"))
            if same_day_plan
            else list(plan.get("all_trigger_periods") or triggered_periods)
        ),
        "trigger_bucket": f"n3p:{plan.get('selected_metric_time') or selected_metric_id}",
        "source_outcome_event_type": output_event_type,
        "source_outcome_event_id": output_event_id,
        "output_event_id": output_event_id,
        "dedup_key": dedup_key,
        "data_quality_status": "passed",
        "match_basis": "n3p_trigger_proof_metric",
        "trigger_live": trigger_live,
        "current_status": current_status,
    }
    return enriched


def build_ordinary_dedup_key(
    *,
    trigger_run_id: str,
    source_event_id: str,
    plan: Mapping[str, Any],
    event_type: str = ORDINARY_TRIGGER_EVENT_TYPE,
) -> str:
    return join_dedup_parts(
        N4_SOURCE_LAYER,
        event_type,
        trigger_run_id,
        source_event_id,
        plan.get("asset_kind"),
        plan.get("identity_key"),
        direction_for_plan(plan),
        plan.get("signal_type"),
        plan.get("condition_key"),
        plan.get("trigger_type"),
        plan.get("selected_metric_time"),
        plan.get("source_metric_run_id"),
        plan.get("selected_metric_id"),
        plan.get("candidate_trigger_identity_key"),
    )


def build_ordinary_trigger_run_row(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    source_metric_run: Mapping[str, Any],
    for_trade_date: str,
    source_condition_run_id: str,
    trigger_context_run_id: str,
    source_metric_run_id: str,
    context_snapshot_row_count: int,
    candidate_count: int,
    matched_count: int,
    state_count: int,
    match_count: int,
    outbox_count: int,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": trigger_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_market_data_run_id": source_metric_run_id,
        "for_trade_date": for_trade_date,
        "source_trade_date": trigger_context_run.get("source_trade_date"),
        "prev_trade_date": trigger_context_run.get("prev_trade_date"),
        "mode": "execute",
        "status": "passed",
        "context_snapshot_row_count": int(context_snapshot_row_count),
        "candidate_count": candidate_count,
        "matched_count": matched_count,
        "trigger_state_row_count": state_count,
        "trigger_match_row_count": match_count,
        "trigger_event_outbox_count": outbox_count,
        "generated_by": DEFAULT_GENERATED_BY,
        "market_data_pulled": False,
        "action_layer_touched": False,
        "user_layer_touched": False,
        "voice_touched": False,
        "sim_touched": False,
        "real_trade_touched": False,
        "worker_started": False,
        "raw_json": {
            "provisional": True,
            "mode_detail": "n4p_ordinary_realtime_action_execute",
            "trigger_context_run_id": trigger_context_run_id,
            "source_metric_kind": SOURCE_METRIC_KIND,
            "source_metric_run_id": source_metric_run_id,
            "source_n3p_live_target_run_id": source_metric_run_id,
            "metric_role": N3P_TRIGGER_PROOF_ROLE,
            "proof_owner": N3P_TRIGGER_PROOF_OWNER,
            "proof_consumer": N3P_TRIGGER_PROOF_CONSUMER,
            "not_n5_final_proof": True,
            "source_trigger_proof_kind": N3P_TRIGGER_PROOF_KIND,
            "source_trigger_proof_run_id": source_metric_run_id,
            "source_metric_run_status": source_metric_run.get("status"),
            "event_model": "TriggerMatched_or_TriggerStateChanged_lifecycle",
            "writes_inbox_or_checkpoint": False,
            "enters_n5": bool(matched_count),
        },
        "started_at": created_at,
        "finished_at": created_at,
    }


def build_ordinary_quality_items(
    *,
    trigger_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    dry_run_plans: Sequence[Mapping[str, Any]],
    matched_count: int,
    created_at: datetime,
) -> list[dict[str, Any]]:
    return [
        {
            "run_id": trigger_run_id,
            "source_condition_run_id": source_condition_run_id,
            "for_trade_date": for_trade_date,
            "source_trade_date": source_trade_date,
            "data_domain": "common",
            "layer_scope": "trigger_run",
            "table_name": "common_trigger_run/common_trigger_state/common_trigger_match/common_event_outbox",
            "gate_code": "n4p_ordinary_execute_summary",
            "gate_name": "N4P ordinary execute summary",
            "severity": "P2",
            "status": "passed",
            "expected_value": "TriggerMatched or TriggerStateChanged lifecycle ordinary provisional execute",
            "actual_value": f"matched={matched_count}",
            "identity_key": None,
            "details": {
                "provisional": True,
                "source_metric_kind": SOURCE_METRIC_KIND,
                "metric_role": N3P_TRIGGER_PROOF_ROLE,
                "proof_owner": N3P_TRIGGER_PROOF_OWNER,
                "proof_consumer": N3P_TRIGGER_PROOF_CONSUMER,
                "not_n5_final_proof": True,
                "source_trigger_proof_kind": N3P_TRIGGER_PROOF_KIND,
                "candidate_count": len(dry_run_plans),
                "matched_count": matched_count,
                "allowed_output_event_types": [ORDINARY_TRIGGER_EVENT_TYPE, ORDINARY_STATE_CHANGED_EVENT_TYPE],
                "writes_inbox_or_checkpoint": False,
                "enters_n5": bool(matched_count),
            },
            "created_at": created_at,
        }
    ]


def build_ordinary_trigger_state_row(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": trigger_run_id,
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "for_trade_date": str(plan.get("for_trade_date") or trigger_context_run.get("for_trade_date") or ""),
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "direction": plan.get("direction"),
        "signal_type": plan.get("signal_type"),
        "condition_key": plan.get("condition_key"),
        "trigger_period": plan.get("trigger_period"),
        "trigger_bucket": plan.get("trigger_bucket"),
        "current_status": plan.get("current_status") or "matched",
        "last_source_event_id": plan.get("source_event_id"),
        "data_quality_status": "passed",
        "context_hash": None,
        "match_count": 1 if plan.get("current_status") != "inactive" else 0,
        "first_matched_at": parse_event_time(plan.get("selected_metric_time")) if plan.get("current_status") != "inactive" else None,
        "last_matched_at": parse_event_time(plan.get("selected_metric_time")) if plan.get("current_status") != "inactive" else None,
        "cleared_at": parse_event_time(plan.get("selected_metric_time")) if plan.get("current_status") == "inactive" else None,
        "dedup_key": plan.get("dedup_key"),
        "raw_json": build_ordinary_raw_json(plan),
        "created_at": created_at,
        "updated_at": created_at,
    }


def build_ordinary_trigger_match_row(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    output_event_id: str,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": trigger_run_id,
        "source_event_id": plan.get("source_event_id"),
        "source_event_type": plan.get("source_event_type"),
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "for_trade_date": str(plan.get("for_trade_date") or trigger_context_run.get("for_trade_date") or ""),
        "direction": plan.get("direction"),
        "signal_type": plan.get("signal_type"),
        "condition_key": plan.get("condition_key"),
        "trigger_period": plan.get("trigger_period"),
        "trigger_bucket": plan.get("trigger_bucket"),
        "trigger_price": plan.get("trigger_price"),
        "trigger_time": parse_event_time(plan.get("selected_metric_time")),
        "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
        "output_event_id": output_event_id,
        "output_event_type": ORDINARY_TRIGGER_EVENT_TYPE,
        "dedup_key": plan.get("dedup_key"),
        "data_quality_status": "passed",
        "source_condition_pool_id": None,
        "source_condition_basis_id": None,
        "source_market_subscription_id": None,
        "context_hash": None,
        "raw_json": build_ordinary_raw_json(plan),
        "created_at": created_at,
    }


def build_ordinary_trigger_matched_envelope(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    output_event_id: str,
    trigger_state_id: int | None,
    trigger_match_id: int | None,
    created_at: datetime | None = None,
) -> EventEnvelope:
    event_type = str(plan.get("output_event_type") or ORDINARY_TRIGGER_EVENT_TYPE)
    enters_n5 = event_type == ORDINARY_TRIGGER_EVENT_TYPE
    trigger_live = bool(plan.get("trigger_live")) if event_type == ORDINARY_STATE_CHANGED_EVENT_TYPE else True
    current_status = str(plan.get("current_status") or ("matched" if trigger_live else "inactive"))
    original_condition_key = plan.get("original_condition_key") or plan.get("condition_key")
    payload = to_jsonable(
        {
            "event_type": event_type,
            "run_id": trigger_run_id,
            "source_event_id": plan.get("source_event_id"),
            "source_event_type": plan.get("source_event_type"),
            "identity_key": plan.get("identity_key"),
            "asset_kind": plan.get("asset_kind"),
            "display_name": plan.get("display_name"),
            "condition_projection_context": to_jsonable(
                plan.get("condition_projection_context")
                if plan.get("condition_projection_context") is not None
                else {}
            ),
            "condition_projection_context_status": plan.get("condition_projection_context_status") or "not_ready",
            "condition_projection_context_trace": to_jsonable(
                plan.get("condition_projection_context_trace") or {}
            ),
            "direction": plan.get("direction"),
            "condition_key": plan.get("condition_key"),
            "original_condition_key": original_condition_key,
            "signal_type": plan.get("signal_type"),
            "trigger_type": plan.get("trigger_type"),
            "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
            "projection_30m_flag": bool(plan.get("projection_30m_flag") or False),
            "projection_30m_type": plan.get("projection_30m_type") or "none",
            "trigger_period": plan.get("trigger_period"),
            "triggered_periods": plan.get("triggered_periods") or [],
            "prerequisite_periods": plan.get("prerequisite_periods") or [],
            "period_escalation_trace": to_jsonable(plan.get("period_escalation_trace") or {}),
            "ordinary_period_escalation_policy_version": plan.get(
                "ordinary_period_escalation_policy_version"
            ),
            "ordinary_period_escalation_policy_hash": plan.get(
                "ordinary_period_escalation_policy_hash"
            ),
            "trigger_price": plan.get("trigger_price"),
            "trigger_time": plan.get("selected_metric_time"),
            "trigger_bucket": plan.get("trigger_bucket"),
            "match_basis": "n3p_trigger_proof_metric",
            "data_quality_status": "passed",
            "provisional": True,
            "source_metric_kind": SOURCE_METRIC_KIND,
            "source_metric_event_type": plan.get("source_metric_event_type"),
            "source_metric_run_id": plan.get("source_metric_run_id"),
            "source_n3p_live_target_run_id": plan.get("source_metric_run_id"),
            "selected_metric_id": plan.get("selected_metric_id"),
            "selected_metric_time": plan.get("selected_metric_time"),
            "metric_role": plan.get("metric_role") or N3P_TRIGGER_PROOF_ROLE,
            "proof_owner": plan.get("proof_owner") or N3P_TRIGGER_PROOF_OWNER,
            "proof_consumer": plan.get("proof_consumer") or N3P_TRIGGER_PROOF_CONSUMER,
            "not_n5_final_proof": bool(plan.get("not_n5_final_proof") if "not_n5_final_proof" in plan else True),
            "source_trigger_proof_kind": plan.get("source_trigger_proof_kind") or N3P_TRIGGER_PROOF_KIND,
            "source_trigger_proof_run_id": plan.get("source_trigger_proof_run_id") or plan.get("source_metric_run_id"),
            "source_trigger_proof_metric_id": plan.get("source_trigger_proof_metric_id") or plan.get("selected_metric_id"),
            "source_trigger_proof_time": plan.get("source_trigger_proof_time") or plan.get("selected_metric_time"),
            "metric_time_label": plan.get("metric_time_label"),
            "metric_minute_label": plan.get("metric_minute_label"),
            "is_closed_1m": bool(plan.get("is_closed_1m")),
            "source_mode": plan.get("source_mode"),
            "c1_dependency": plan.get("c1_dependency"),
            "trigger_live": trigger_live,
            "current_status": current_status,
            "previous_status": plan.get("previous_status"),
            "previous_trigger_live": plan.get("previous_trigger_live"),
            "primary_trigger_period": plan.get("primary_trigger_period"),
            "previous_primary_trigger_period": plan.get("previous_primary_trigger_period"),
            "all_trigger_periods": plan.get("all_trigger_periods") or [],
            "previous_all_trigger_periods": plan.get("previous_all_trigger_periods") or [],
            "previous_projection_30m_flag": plan.get("previous_projection_30m_flag"),
            "previous_projection_30m_type": plan.get("previous_projection_30m_type"),
            "previous_trigger_mark_candidate": plan.get("previous_trigger_mark_candidate"),
            "state_change_reason": plan.get("state_change_reason"),
            "source_outcome_event_type": plan.get("source_outcome_event_type"),
            "source_outcome_event_id": plan.get("source_outcome_event_id"),
            "lifecycle_state_key": plan.get("lifecycle_state_key"),
            "lifecycle_state_key_version": plan.get("lifecycle_state_key_version"),
            "trigger_context_run_id": plan.get("trigger_context_run_id"),
            "source_condition_run_id": plan.get("source_condition_run_id"),
            "trigger_state_id": trigger_state_id,
            "trigger_match_id": trigger_match_id,
            "candidate_trigger_identity_key": plan.get("candidate_trigger_identity_key"),
            "n5_entry_allowed": enters_n5,
            "rule_eval_result": to_jsonable(plan.get("rule_eval_result") or {}),
            "rule_proof": to_jsonable(plan.get("rule_proof") or {}),
            "trace": to_jsonable(plan.get("trace") or {}),
            "n4_boundary": {
                "provisional_ordinary": True,
                "market_data_pulled": False,
                "source_outbox_consumed": False,
                "writes_inbox_or_checkpoint": False,
                "downstream_layers_touched": False,
                "worker_started": False,
                "enters_n5": enters_n5,
            },
        }
    )
    envelope = EventEnvelope(
        event_id=output_event_id,
        event_type=event_type,
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        trade_date=str(plan.get("for_trade_date") or trigger_context_run.get("for_trade_date") or ""),
        asset_kind=str(plan.get("asset_kind") or ""),
        identity_key=str(plan.get("identity_key") or ""),
        event_time=parse_event_time(plan.get("selected_metric_time")),
        source_layer=N4_SOURCE_LAYER,
        source_run_id=trigger_run_id,
        dedup_key=str(plan.get("dedup_key") or ""),
        partition_key=str(plan.get("identity_key") or ""),
        payload_json=payload,
        created_at=created_at or utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def build_ordinary_raw_json(plan: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str(plan.get("output_event_type") or "")
    return to_jsonable(
        {
            "event_type": plan.get("output_event_type"),
            "provisional": True,
            "asset_kind": plan.get("asset_kind"),
            "identity_key": plan.get("identity_key"),
            "condition_projection_context": to_jsonable(
                plan.get("condition_projection_context")
                if plan.get("condition_projection_context") is not None
                else {}
            ),
            "condition_projection_context_status": plan.get("condition_projection_context_status") or "not_ready",
            "condition_projection_context_trace": to_jsonable(
                plan.get("condition_projection_context_trace") or {}
            ),
            "source_metric_kind": SOURCE_METRIC_KIND,
            "source_metric_event_type": plan.get("source_metric_event_type"),
            "source_metric_run_id": plan.get("source_metric_run_id"),
            "source_n3p_live_target_run_id": plan.get("source_metric_run_id"),
            "selected_metric_id": plan.get("selected_metric_id"),
            "selected_metric_time": plan.get("selected_metric_time"),
            "metric_role": plan.get("metric_role") or N3P_TRIGGER_PROOF_ROLE,
            "proof_owner": plan.get("proof_owner") or N3P_TRIGGER_PROOF_OWNER,
            "proof_consumer": plan.get("proof_consumer") or N3P_TRIGGER_PROOF_CONSUMER,
            "not_n5_final_proof": bool(plan.get("not_n5_final_proof") if "not_n5_final_proof" in plan else True),
            "source_trigger_proof_kind": plan.get("source_trigger_proof_kind") or N3P_TRIGGER_PROOF_KIND,
            "source_trigger_proof_run_id": plan.get("source_trigger_proof_run_id") or plan.get("source_metric_run_id"),
            "source_trigger_proof_metric_id": plan.get("source_trigger_proof_metric_id") or plan.get("selected_metric_id"),
            "source_trigger_proof_time": plan.get("source_trigger_proof_time") or plan.get("selected_metric_time"),
            "metric_time_label": plan.get("metric_time_label"),
            "metric_minute_label": plan.get("metric_minute_label"),
            "is_closed_1m": bool(plan.get("is_closed_1m")),
            "source_mode": plan.get("source_mode"),
            "c1_dependency": plan.get("c1_dependency"),
            "condition_key": plan.get("condition_key"),
            "original_condition_key": plan.get("original_condition_key") or plan.get("condition_key"),
            "signal_type": plan.get("signal_type"),
            "trigger_type": plan.get("trigger_type"),
            "trigger_period": plan.get("trigger_period"),
            "triggered_periods": plan.get("triggered_periods") or [],
            "all_trigger_periods": plan.get("all_trigger_periods") or [],
            "primary_trigger_period": plan.get("primary_trigger_period"),
            "prerequisite_periods": plan.get("prerequisite_periods") or [],
            "period_escalation_trace": to_jsonable(plan.get("period_escalation_trace") or {}),
            "ordinary_period_escalation_policy_version": plan.get(
                "ordinary_period_escalation_policy_version"
            ),
            "ordinary_period_escalation_policy_hash": plan.get(
                "ordinary_period_escalation_policy_hash"
            ),
            "trigger_price": plan.get("trigger_price"),
            "trigger_time": plan.get("selected_metric_time"),
            "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
            "source_condition_run_id": plan.get("source_condition_run_id"),
            "trigger_context_run_id": plan.get("trigger_context_run_id"),
            "projection_30m_flag": bool(plan.get("projection_30m_flag") or False),
            "projection_30m_type": plan.get("projection_30m_type") or "none",
            "candidate_trigger_identity_key": plan.get("candidate_trigger_identity_key"),
            "output_event_type": plan.get("output_event_type"),
            "source_outcome_event_id": plan.get("output_event_id"),
            "current_status": plan.get("current_status"),
            "trigger_live": plan.get("trigger_live"),
            "lifecycle_state_key": plan.get("lifecycle_state_key"),
            "lifecycle_state_key_version": plan.get("lifecycle_state_key_version"),
            "lifecycle_output_reason": plan.get("lifecycle_output_reason"),
            "n5_entry_allowed": event_type == ORDINARY_TRIGGER_EVENT_TYPE,
            "rule_eval_result": to_jsonable(plan.get("rule_eval_result") or {}),
            "rule_proof": to_jsonable(plan.get("rule_proof") or {}),
            "trace": to_jsonable(plan.get("trace") or {}),
            "plan": to_jsonable(dict(plan)),
        }
    )


def execute_provisional_ordinary_transaction(*, dsn: str, execute_plan: Mapping[str, Any]) -> dict[str, int]:
    trigger_run_id = str(execute_plan.get("trigger_run_id") or "")
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4p_provisional_ordinary_execute",
        source_run_id=trigger_run_id,
        readonly_expected=False,
        bypass_classification="explicit_bypass_n4p_ordinary_execute",
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            insert_ordinary_trigger_run(cur, execute_plan["writes"]["common_trigger_run"][0])
            insert_ordinary_quality_items(cur, execute_plan["writes"]["common_trigger_quality_item"])
            state_id_by_dedup_key: dict[str, int] = {}
            for row in execute_plan["writes"]["common_trigger_state"]:
                dedup_key = str(row["dedup_key"])
                state_id_by_dedup_key[dedup_key] = insert_ordinary_trigger_state(cur, row)
            match_count = 0
            outbox_count = 0
            matched_dedup_keys: set[str] = set()
            for match_row in execute_plan["writes"]["common_trigger_match"]:
                dedup_key = str(match_row["dedup_key"])
                matched_dedup_keys.add(dedup_key)
                state_id = state_id_by_dedup_key[dedup_key]
                match_id = insert_ordinary_trigger_match(cur, match_row, trigger_state_id=state_id)
                update_ordinary_state_last_match(cur, trigger_state_id=state_id, trigger_match_id=match_id)
                event_plan = _matched_plan_by_dedup_key(execute_plan, dedup_key)
                envelope = build_ordinary_trigger_matched_envelope(
                    trigger_run_id=trigger_run_id,
                    trigger_context_run=execute_plan["writes"]["common_trigger_run"][0],
                    plan=event_plan,
                    output_event_id=str(match_row["output_event_id"]),
                    trigger_state_id=state_id,
                    trigger_match_id=match_id,
                )
                insert_ordinary_outbox_envelope(cur, envelope)
                match_count += 1
                outbox_count += 1
            for state_row in execute_plan["writes"]["common_trigger_state"]:
                dedup_key = str(state_row["dedup_key"])
                if dedup_key in matched_dedup_keys:
                    continue
                state_id = state_id_by_dedup_key[dedup_key]
                event_plan = _state_plan_by_dedup_key(execute_plan, dedup_key)
                envelope = build_ordinary_trigger_matched_envelope(
                    trigger_run_id=trigger_run_id,
                    trigger_context_run=execute_plan["writes"]["common_trigger_run"][0],
                    plan=event_plan,
                    output_event_id=str(event_plan["output_event_id"]),
                    trigger_state_id=state_id,
                    trigger_match_id=None,
                )
                insert_ordinary_outbox_envelope(cur, envelope)
                outbox_count += 1
            conn.commit()
    return {
        "common_trigger_run": 1,
        "common_trigger_quality_item": len(execute_plan["writes"]["common_trigger_quality_item"]),
        "common_trigger_state": len(execute_plan["writes"]["common_trigger_state"]),
        "common_trigger_match": match_count,
        "common_event_outbox": outbox_count,
    }


def run_provisional_ordinary_once(
    *,
    dsn: str,
    trigger_context_run_id: str,
    source_metric_run_id: str,
    trigger_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    previous_trigger_run_id: str | None = None,
    baseline_mode: str | None = None,
    execute: bool,
    user_confirmed: bool,
    json_report_path: str | Path | None = None,
    markdown_report_path: str | Path | None = None,
    rollback_sql_path: str | Path | None = None,
) -> dict[str, Any]:
    total_started_at = perf_counter()
    phase_timing_ms: dict[str, float] = {}
    if execute:
        assert_n4p_ordinary_execute_confirmed(execute=execute, user_confirmed=user_confirmed)
    normalized_baseline_mode = normalize_previous_baseline_mode(baseline_mode)

    phase_started_at = perf_counter()
    context_rows, trigger_context_run = fetch_ordinary_trigger_context_rows(dsn, trigger_context_run_id)
    phase_timing_ms["fetch_context_ms"] = _elapsed_ms(phase_started_at)

    phase_started_at = perf_counter()
    metric_rows, source_metric_run = fetch_ordinary_source_metric_rows(dsn, source_metric_run_id)
    phase_timing_ms["fetch_metric_ms"] = _elapsed_ms(phase_started_at)

    phase_started_at = perf_counter()
    dry_run_plans = build_provisional_ordinary_matcher_plans(
        trigger_context_run_id=trigger_context_run_id,
        source_metric_run_id=source_metric_run_id,
        context_rows=context_rows,
        metric_rows=metric_rows,
    )
    phase_timing_ms["build_matcher_plans_ms"] = _elapsed_ms(phase_started_at)

    phase_started_at = perf_counter()
    target_counts = fetch_target_counts(dsn, trigger_run_id)
    phase_timing_ms["fetch_target_counts_ms"] = _elapsed_ms(phase_started_at)

    phase_started_at = perf_counter()
    previous_trigger_states = fetch_previous_ordinary_trigger_states(
        dsn,
        trigger_run_id=trigger_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        previous_trigger_run_id=previous_trigger_run_id,
        baseline_mode=normalized_baseline_mode,
    )
    phase_timing_ms["fetch_previous_states_ms"] = _elapsed_ms(phase_started_at)

    phase_started_at = perf_counter()
    execute_plan = build_provisional_ordinary_execute_plan(
        trigger_run_id=trigger_run_id,
        trigger_context_run=trigger_context_run,
        source_metric_run=source_metric_run,
        trigger_context_run_id=trigger_context_run_id,
        source_metric_run_id=source_metric_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        dry_run_plans=dry_run_plans,
        context_snapshot_row_count=len(context_rows),
        target_counts=target_counts,
        previous_trigger_states=previous_trigger_states,
    )
    phase_timing_ms["build_execute_plan_ms"] = _elapsed_ms(phase_started_at)
    write_counts: dict[str, int] | None = None
    result = "PREFLIGHT_PASS"
    phase_timing_ms["execute_transaction_ms"] = 0.0
    if execute:
        phase_started_at = perf_counter()
        write_counts = execute_provisional_ordinary_transaction(dsn=dsn, execute_plan=execute_plan)
        phase_timing_ms["execute_transaction_ms"] = _elapsed_ms(phase_started_at)
        result = "EXECUTED"
    phase_timing_ms["write_artifacts_ms"] = 0.0
    phase_timing_ms["total_ms"] = _elapsed_ms(total_started_at)
    report = {
        "result": result,
        "trigger_run_id": trigger_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "source_metric_kind": SOURCE_METRIC_KIND,
        "source_metric_run_id": source_metric_run_id,
        "previous_trigger_run_id": previous_trigger_run_id or "",
        "baseline_mode": normalized_baseline_mode,
        "for_trade_date": for_trade_date,
        "execute": execute,
        "summary": execute_plan.get("summary"),
        "write_counts": write_counts or execute_plan.get("write_counts"),
        "event_model": execute_plan.get("event_model"),
        "side_effect_guard": execute_plan.get("side_effect_guard"),
        "forbidden_write_counts": execute_plan.get("forbidden_write_counts"),
        "phase_timing_ms": phase_timing_ms,
    }
    phase_started_at = perf_counter()
    write_ordinary_execute_artifacts(
        report=report,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        rollback_sql_path=rollback_sql_path,
    )
    phase_timing_ms["write_artifacts_ms"] = _elapsed_ms(phase_started_at)
    phase_timing_ms["total_ms"] = _elapsed_ms(total_started_at)
    if json_report_path is not None or markdown_report_path is not None:
        write_ordinary_execute_artifacts(
            report=report,
            json_report_path=json_report_path,
            markdown_report_path=markdown_report_path,
            rollback_sql_path=None,
        )
    if rollback_sql_path is not None:
        report["rollback_sql_path"] = str(rollback_sql_path)
    return report


def fetch_ordinary_trigger_context_rows(
    dsn: str,
    trigger_context_run_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4p_ordinary_context_fetch",
        source_run_id=trigger_context_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM common_trigger_run WHERE run_id = %s", (trigger_context_run_id,))
        trigger_context_run = cur.fetchone()
        if not trigger_context_run:
            raise N4POrdinaryExecuteBlocked(f"trigger_context_run missing: {trigger_context_run_id}")
        rows: list[dict[str, Any]] = []
        for asset_kind, table_name in (
            ("stock", "stock_trigger_context_snapshot"),
            ("index", "index_trigger_context_snapshot"),
            ("board", "board_trigger_context_snapshot"),
        ):
            cur.execute(f"SELECT *, %s AS asset_kind FROM {table_name} WHERE run_id = %s", (asset_kind, trigger_context_run_id))
            rows.extend(dict(row) for row in cur.fetchall())
        return rows, dict(trigger_context_run)


def fetch_ordinary_source_metric_rows(
    dsn: str,
    source_metric_run_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4p_ordinary_source_metric_fetch",
        source_run_id=source_metric_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM common_market_data_run WHERE run_id = %s", (source_metric_run_id,))
        source_metric_run = cur.fetchone()
        if not source_metric_run:
            raise N4POrdinaryExecuteBlocked(f"source_metric_run missing: {source_metric_run_id}")
        rows: list[dict[str, Any]] = []
        for asset_kind, table_name in (
            ("stock", "stock_action_confirmation_projection_metric"),
            ("index", "index_action_confirmation_projection_metric"),
            ("board", "board_action_confirmation_projection_metric"),
        ):
            cur.execute(
                f"SELECT *, %s AS asset_kind FROM {table_name} WHERE projection_run_id = %s",
                (asset_kind, source_metric_run_id),
            )
            rows.extend(dict(row) for row in cur.fetchall())
        return rows, dict(source_metric_run)


def fetch_previous_ordinary_trigger_states(
    dsn: str,
    *,
    trigger_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    previous_trigger_run_id: str | None = None,
    baseline_mode: str | None = None,
) -> list[dict[str, Any]]:
    normalized_baseline_mode = normalize_previous_baseline_mode(baseline_mode)
    if previous_trigger_run_id is None and normalized_baseline_mode == NO_PREVIOUS_BASELINE_MODE:
        return []
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4p_ordinary_previous_state_fetch",
        source_run_id=trigger_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        if previous_trigger_run_id:
            previous_rows = fetch_latest_ordinary_state_snapshot_rows_through_previous_target(
                cur,
                trigger_run_id=trigger_run_id,
                for_trade_date=for_trade_date,
                source_condition_run_id=source_condition_run_id,
                previous_trigger_run_id=previous_trigger_run_id,
            )
            if previous_rows:
                selected = select_previous_ordinary_trigger_states(
                    previous_rows,
                    previous_trigger_run_id=previous_trigger_run_id,
                    baseline_mode=normalized_baseline_mode,
                )
                if selected:
                    return selected
            exact_rows = fetch_exact_previous_ordinary_trigger_state_rows(
                cur,
                for_trade_date=for_trade_date,
                source_condition_run_id=source_condition_run_id,
                previous_trigger_run_id=previous_trigger_run_id,
            )
            return select_previous_ordinary_trigger_states(
                exact_rows,
                previous_trigger_run_id=previous_trigger_run_id,
                baseline_mode=normalized_baseline_mode,
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM common_trigger_state
                WHERE for_trade_date = %s
                  AND source_condition_run_id = %s
                  AND run_id <> %s
                """,
                (for_trade_date, source_condition_run_id, trigger_run_id),
            )
        return select_previous_ordinary_trigger_states(
            [dict(row) for row in cur.fetchall()],
            previous_trigger_run_id=previous_trigger_run_id,
            baseline_mode=normalized_baseline_mode,
        )


def fetch_latest_ordinary_state_snapshot_rows_through_previous_target(
    cur: Any,
    *,
    trigger_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    previous_trigger_run_id: str,
) -> list[dict[str, Any]]:
    try:
        previous_parsed = parse_n4p_ordinary_trigger_run_id(previous_trigger_run_id)
    except N4POrdinaryExecuteBlocked:
        return []
    cutoff_hhmm = str(previous_parsed["until_hhmm"])
    cutoff_trade_date = str(previous_parsed["for_trade_date"])
    cur.execute(
        """
        WITH previous_candidate_states AS (
          SELECT
            s.*,
            substring(s.run_id from 'trigger_provisional_ordinary_([0-9]{8})_until_') AS run_trade_date,
            substring(s.run_id from 'until_([0-9]{4})') AS run_until_hhmm,
            CASE
              WHEN COALESCE(NULLIF(s.raw_json->>'trigger_type', ''), NULLIF(s.raw_json #>> '{plan,trigger_type}', ''), s.condition_key) IN ('BUY_HINT', 'SELL_HINT', 'BUY:FULL', 'SELL:FULL')
                THEN COALESCE(NULLIF(s.raw_json->>'trigger_type', ''), NULLIF(s.raw_json #>> '{plan,trigger_type}', ''), s.condition_key)
              WHEN COALESCE(NULLIF(s.raw_json->>'trigger_type', ''), NULLIF(s.raw_json #>> '{plan,trigger_type}', ''), s.condition_key) = 'BUY'
                OR COALESCE(NULLIF(s.raw_json->>'trigger_type', ''), NULLIF(s.raw_json #>> '{plan,trigger_type}', ''), s.condition_key) LIKE 'BUY:%%'
                THEN 'BUY'
              WHEN COALESCE(NULLIF(s.raw_json->>'trigger_type', ''), NULLIF(s.raw_json #>> '{plan,trigger_type}', ''), s.condition_key) = 'SELL'
                OR COALESCE(NULLIF(s.raw_json->>'trigger_type', ''), NULLIF(s.raw_json #>> '{plan,trigger_type}', ''), s.condition_key) LIKE 'SELL:%%'
                THEN 'SELL'
              ELSE COALESCE(NULLIF(s.raw_json->>'trigger_type', ''), NULLIF(s.raw_json #>> '{plan,trigger_type}', ''), s.condition_key)
            END AS lifecycle_trigger_type
          FROM common_trigger_state s
          JOIN common_trigger_run r ON r.run_id = s.run_id
          WHERE s.for_trade_date = %s
            AND s.source_condition_run_id = %s
            AND s.run_id <> %s
            AND s.run_id LIKE %s
            AND r.status = 'passed'
            AND substring(s.run_id from 'trigger_provisional_ordinary_([0-9]{8})_until_') = %s
            AND substring(s.run_id from 'until_([0-9]{4})') <= %s
        ),
        ranked_previous_states AS (
          SELECT
            previous_candidate_states.*,
            row_number() over (
              PARTITION BY for_trade_date, asset_kind, identity_key, signal_type, condition_key, lifecycle_trigger_type
              ORDER BY run_until_hhmm DESC, run_id DESC
            ) AS lifecycle_rank
          FROM previous_candidate_states
        )
        SELECT *
        FROM ranked_previous_states
        WHERE lifecycle_rank = 1
        ORDER BY run_until_hhmm, run_id
        """,
        (
            for_trade_date,
            source_condition_run_id,
            trigger_run_id,
            "trigger_provisional_ordinary_%",
            cutoff_trade_date,
            cutoff_hhmm,
        ),
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_exact_previous_ordinary_trigger_state_rows(
    cur: Any,
    *,
    for_trade_date: str,
    source_condition_run_id: str,
    previous_trigger_run_id: str,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM common_trigger_state
        WHERE for_trade_date = %s
          AND source_condition_run_id = %s
          AND run_id = %s
        """,
        (for_trade_date, source_condition_run_id, previous_trigger_run_id),
    )
    return [dict(row) for row in cur.fetchall()]


def normalize_previous_baseline_mode(baseline_mode: str | None = None) -> str:
    text = str(baseline_mode or "").strip()
    if not text:
        return ""
    if text == NO_PREVIOUS_BASELINE_MODE:
        return text
    raise N4POrdinaryExecuteBlocked(f"unsupported previous baseline mode: {text}")


def select_previous_ordinary_trigger_states(
    rows: Sequence[Mapping[str, Any]],
    *,
    previous_trigger_run_id: str | None = None,
    baseline_mode: str | None = None,
) -> list[dict[str, Any]]:
    normalized_baseline_mode = normalize_previous_baseline_mode(baseline_mode)
    selected_rows = [dict(row) for row in rows]
    if previous_trigger_run_id:
        snapshot_rows = select_latest_ordinary_state_snapshot_through_previous_target(
            selected_rows,
            previous_trigger_run_id=previous_trigger_run_id,
        )
        if snapshot_rows:
            return snapshot_rows
        exact_rows = [row for row in selected_rows if str(row.get("run_id") or "") == previous_trigger_run_id]
        if not exact_rows:
            raise N4POrdinaryExecuteBlocked(f"previous_trigger_run_id has no trigger states: {previous_trigger_run_id}")
        return exact_rows
    if normalized_baseline_mode == NO_PREVIOUS_BASELINE_MODE:
        return []

    previous_run_ids = sorted({str(row.get("run_id") or "") for row in selected_rows if str(row.get("run_id") or "")})
    if len(previous_run_ids) > 1:
        raise N4POrdinaryExecuteBlocked(
            "ambiguous previous ordinary trigger baseline: "
            + ", ".join(previous_run_ids)
            + "; provide previous_trigger_run_id"
        )
    return selected_rows


def select_latest_ordinary_state_snapshot_through_previous_target(
    rows: Sequence[Mapping[str, Any]],
    *,
    previous_trigger_run_id: str,
) -> list[dict[str, Any]]:
    try:
        previous_parsed = parse_n4p_ordinary_trigger_run_id(previous_trigger_run_id)
    except N4POrdinaryExecuteBlocked:
        return []
    cutoff_hhmm = str(previous_parsed["until_hhmm"])
    cutoff_trade_date = str(previous_parsed["for_trade_date"])
    latest_by_key: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for raw_row in rows:
        row = dict(raw_row)
        run_id = str(row.get("run_id") or "")
        try:
            parsed = parse_n4p_ordinary_trigger_run_id(run_id)
        except N4POrdinaryExecuteBlocked:
            continue
        if str(parsed["for_trade_date"]) != cutoff_trade_date:
            continue
        until_hhmm = str(parsed["until_hhmm"])
        if until_hhmm > cutoff_hhmm:
            continue
        key = lifecycle_state_key(row)
        existing = latest_by_key.get(key)
        candidate_key = (until_hhmm, run_id)
        if existing is None or candidate_key > (existing[0], existing[1]):
            latest_by_key[key] = (until_hhmm, run_id, row)
    return [item[2] for item in sorted(latest_by_key.values(), key=lambda item: (item[0], item[1]))]


def insert_ordinary_trigger_run(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_trigger_run (
          run_id, source_condition_run_id, source_market_data_run_id,
          for_trade_date, source_trade_date, prev_trade_date, mode, status,
          context_snapshot_row_count, trigger_state_row_count,
          trigger_match_row_count, trigger_event_outbox_count, generated_by,
          market_data_pulled, action_layer_touched, user_layer_touched,
          voice_touched, sim_touched, real_trade_touched, worker_started,
          raw_json, started_at, finished_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(source_market_data_run_id)s,
          %(for_trade_date)s, %(source_trade_date)s, %(prev_trade_date)s, %(mode)s, %(status)s,
          %(context_snapshot_row_count)s, %(trigger_state_row_count)s,
          %(trigger_match_row_count)s, %(trigger_event_outbox_count)s, %(generated_by)s,
          %(market_data_pulled)s, %(action_layer_touched)s, %(user_layer_touched)s,
          %(voice_touched)s, %(sim_touched)s, %(real_trade_touched)s, %(worker_started)s,
          %(raw_json)s, %(started_at)s, %(finished_at)s
        )
        """,
        {**dict(row), "raw_json": Jsonb(to_jsonable(row.get("raw_json") or {}))},
    )


def insert_ordinary_quality_items(cur: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO common_trigger_quality_item (
              run_id, source_condition_run_id, for_trade_date, source_trade_date,
              data_domain, layer_scope, table_name, gate_code, gate_name, severity,
              status, expected_value, actual_value, identity_key, details, created_at
            )
            VALUES (
              %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s, %(source_trade_date)s,
              %(data_domain)s, %(layer_scope)s, %(table_name)s, %(gate_code)s, %(gate_name)s, %(severity)s,
              %(status)s, %(expected_value)s, %(actual_value)s, %(identity_key)s, %(details)s, %(created_at)s
            )
            """,
            {**dict(row), "details": Jsonb(to_jsonable(row.get("details") or {}))},
        )


def insert_ordinary_trigger_state(cur: Any, row: Mapping[str, Any]) -> int:
    cur.execute(
        """
        INSERT INTO common_trigger_state (
          run_id, source_condition_run_id, for_trade_date,
          asset_kind, identity_key, direction, signal_type, condition_key,
          trigger_period, trigger_bucket, current_status, last_source_event_id,
          data_quality_status, context_hash, match_count, first_matched_at,
          last_matched_at, cleared_at, raw_json, created_at, updated_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s,
          %(asset_kind)s, %(identity_key)s, %(direction)s, %(signal_type)s, %(condition_key)s,
          %(trigger_period)s, %(trigger_bucket)s, %(current_status)s, %(last_source_event_id)s,
          %(data_quality_status)s, %(context_hash)s, %(match_count)s, %(first_matched_at)s,
          %(last_matched_at)s, %(cleared_at)s, %(raw_json)s, %(created_at)s, %(updated_at)s
        )
        RETURNING trigger_state_id
        """,
        {**dict(row), "raw_json": Jsonb(to_jsonable(row.get("raw_json") or {}))},
    )
    fetched = cur.fetchone()
    if isinstance(fetched, Mapping):
        return int(fetched["trigger_state_id"])
    return int(fetched[0])


def insert_ordinary_trigger_match(cur: Any, row: Mapping[str, Any], *, trigger_state_id: int) -> int:
    cur.execute(
        """
        INSERT INTO common_trigger_match (
          run_id, trigger_state_id, source_event_id, source_event_type,
          source_condition_run_id, source_condition_pool_id, source_condition_basis_id,
          source_market_subscription_id, for_trade_date, asset_kind, identity_key,
          direction, signal_type, condition_key, trigger_price, trigger_mark_candidate,
          trigger_time, trigger_period, trigger_bucket,
          output_event_id, output_event_type, data_quality_status,
          dedup_key, context_hash, raw_json, created_at
        )
        VALUES (
          %(run_id)s, %(trigger_state_id)s, %(source_event_id)s, %(source_event_type)s,
          %(source_condition_run_id)s, %(source_condition_pool_id)s, %(source_condition_basis_id)s,
          %(source_market_subscription_id)s, %(for_trade_date)s, %(asset_kind)s, %(identity_key)s,
          %(direction)s, %(signal_type)s, %(condition_key)s, %(trigger_price)s, %(trigger_mark_candidate)s,
          %(trigger_time)s, %(trigger_period)s, %(trigger_bucket)s,
          %(output_event_id)s, %(output_event_type)s, %(data_quality_status)s,
          %(dedup_key)s, %(context_hash)s, %(raw_json)s, %(created_at)s
        )
        RETURNING trigger_match_id
        """,
        {
            **dict(row),
            "trigger_state_id": trigger_state_id,
            "raw_json": Jsonb(to_jsonable(row.get("raw_json") or {})),
        },
    )
    fetched = cur.fetchone()
    if isinstance(fetched, Mapping):
        return int(fetched["trigger_match_id"])
    return int(fetched[0])


def update_ordinary_state_last_match(cur: Any, *, trigger_state_id: int, trigger_match_id: int) -> None:
    cur.execute(
        """
        UPDATE common_trigger_state
        SET last_trigger_match_id = %s, updated_at = now()
        WHERE trigger_state_id = %s
        """,
        (trigger_match_id, trigger_state_id),
    )


def insert_ordinary_outbox_envelope(cur: Any, envelope: EventEnvelope) -> str:
    record = envelope.as_record()
    columns = (
        "event_id",
        "event_type",
        "event_schema_version",
        "trade_date",
        "asset_kind",
        "identity_key",
        "event_time",
        "source_layer",
        "source_run_id",
        "dedup_key",
        "partition_key",
        "payload_json",
        "created_at",
    )
    placeholders = ", ".join(["%s"] * len(columns))
    cur.execute(
        f"""
        INSERT INTO common_event_outbox ({", ".join(columns)})
        VALUES ({placeholders})
        RETURNING event_id
        """,
        [Jsonb(to_jsonable(record[column])) if column == "payload_json" else record[column] for column in columns],
    )
    fetched = cur.fetchone()
    if isinstance(fetched, Mapping):
        return str(fetched["event_id"])
    return str(fetched[0])


def fetch_target_counts(dsn: str, trigger_run_id: str) -> dict[str, int]:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4p_ordinary_execute_target_absence",
        source_run_id=trigger_run_id,
        readonly_expected=True,
        bypass_classification="readonly_n4p_ordinary_target_absence",
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        counts: dict[str, int] = {}
        for table_name in ("common_trigger_run", "common_trigger_state", "common_trigger_match"):
            cur.execute(f"SELECT count(*) AS row_count FROM {table_name} WHERE run_id = %s", (trigger_run_id,))
            counts[table_name] = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*) AS row_count
            FROM common_event_outbox
            WHERE source_layer = %s AND source_run_id = %s
            """,
            (N4_SOURCE_LAYER, trigger_run_id),
        )
        counts["common_event_outbox"] = int(cur.fetchone()["row_count"])
        cur.execute("SELECT count(*) AS row_count FROM common_event_inbox WHERE source_run_id = %s", (trigger_run_id,))
        counts["common_event_inbox"] = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*) AS row_count
            FROM common_event_consumer_checkpoint
            WHERE source_layer = %s AND checkpoint_payload::text LIKE %s
            """,
            (N4_SOURCE_LAYER, f"%{trigger_run_id}%"),
        )
        counts["checkpoint_refs"] = int(cur.fetchone()["row_count"])
        return counts


def build_ordinary_rollback_sql(trigger_run_id: str) -> str:
    escaped = trigger_run_id.replace("'", "''")
    downstream_guard_tables = ",\n      ".join(
        f"'{table_name}'" for table_name in N4P_ORDINARY_ROLLBACK_DOWNSTREAM_GUARD_TABLES
    )
    return f"""-- N4P ordinary rollback for {escaped}
DO $$
DECLARE
  v_run_id text := '{escaped}';
  v_ref_table text;
  v_ref_count bigint;
BEGIN
  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_event_outbox AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 '
      || 'AND NOT (t.source_layer = ''N4_trigger'' AND t.source_run_id = $2)'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_event_outbox refs exist for %', v_run_id;
    END IF;
    EXECUTE
      'SELECT count(*) FROM common_event_outbox AS t '
      || 'WHERE t.source_layer = ''N4_trigger'' '
      || 'AND t.source_run_id = $1 '
      || 'AND t.status IN (''delivered'', ''delivering'')'
      INTO v_ref_count
      USING v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: scoped outbox already delivered/delivering for %', v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_match') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_trigger_match AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 AND t.run_id <> $2'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_trigger_match refs exist for %', v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_state') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_trigger_state AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 AND t.run_id <> $2'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_trigger_state refs exist for %', v_run_id;
    END IF;
  END IF;

  FOR v_ref_table IN SELECT unnest(ARRAY[
      {downstream_guard_tables}
  ])
  LOOP
    IF to_regclass('public.' || v_ref_table) IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM %I AS t WHERE to_jsonb(t)::text LIKE $1',
        v_ref_table
      )
      INTO v_ref_count
      USING '%' || v_run_id || '%';
      IF v_ref_count > 0 THEN
        RAISE EXCEPTION 'rollback blocked: downstream refs exist in % for %', v_ref_table, v_run_id;
      END IF;
    END IF;
  END LOOP;

  DELETE FROM common_event_outbox
  WHERE source_layer = 'N4_trigger' AND source_run_id = v_run_id;
  DELETE FROM common_trigger_match WHERE run_id = v_run_id;
  DELETE FROM common_trigger_state WHERE run_id = v_run_id;
  DELETE FROM common_trigger_quality_item WHERE run_id = v_run_id;
  DELETE FROM common_trigger_run WHERE run_id = v_run_id;
END $$;
"""


def write_ordinary_execute_artifacts(
    *,
    report: Mapping[str, Any],
    json_report_path: str | Path | None = None,
    markdown_report_path: str | Path | None = None,
    rollback_sql_path: str | Path | None = None,
) -> None:
    import json

    if json_report_path is not None:
        Path(json_report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_report_path).write_text(json.dumps(to_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if markdown_report_path is not None:
        Path(markdown_report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(markdown_report_path).write_text(render_ordinary_execute_markdown(report), encoding="utf-8")
    if rollback_sql_path is not None:
        Path(rollback_sql_path).parent.mkdir(parents=True, exist_ok=True)
        Path(rollback_sql_path).write_text(build_ordinary_rollback_sql(str(report.get("trigger_run_id") or "")), encoding="utf-8")


def render_ordinary_execute_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    phase_timing = report.get("phase_timing_ms") or {}
    return "\n".join(
        [
            "# N4P Ordinary Execute Report",
            "",
            f"- result: {report.get('result')}",
            f"- trigger_run_id: {report.get('trigger_run_id')}",
            f"- source_metric_run_id: {report.get('source_metric_run_id')}",
            f"- candidate_count: {summary.get('candidate_count')}",
            f"- matched_count: {summary.get('matched_count')}",
            f"- writes_inbox_or_checkpoint: {(report.get('event_model') or {}).get('writes_inbox_or_checkpoint')}",
            f"- enters_n5: {(report.get('event_model') or {}).get('enters_n5')}",
            f"- phase_timing_ms: {to_jsonable(phase_timing)}",
            "",
        ]
    )


def summarize_ordinary_execute_plans(plans: Sequence[Mapping[str, Any]], *, candidate_count: int) -> dict[str, Any]:
    matched = [plan for plan in plans if plan.get("output_event_type") == ORDINARY_TRIGGER_EVENT_TYPE]
    state_changed = [plan for plan in plans if plan.get("output_event_type") == ORDINARY_STATE_CHANGED_EVENT_TYPE]
    return {
        "candidate_count": candidate_count,
        "matched_count": len(matched),
        "state_changed_count": len(state_changed),
        "noop_count": candidate_count - len(plans),
        "matched_by_asset_kind": dict(Counter(str(plan.get("asset_kind") or "") for plan in matched)),
        "matched_by_signal_type": dict(Counter(str(plan.get("signal_type") or "") for plan in matched)),
        "matched_by_trigger_type": dict(Counter(str(plan.get("trigger_type") or "") for plan in matched)),
        "matched_by_trigger_mark_candidate": dict(Counter(str(plan.get("trigger_mark_candidate") or "") for plan in matched)),
        "output_event_types": dict(Counter(str(plan.get("output_event_type") or "") for plan in plans)),
        "unclosed_metric_count": sum(1 for plan in plans if plan.get("is_closed_1m") is False),
    }


def direction_for_plan(plan: Mapping[str, Any]) -> str:
    signal_type = str(plan.get("signal_type") or "")
    condition_key = str(plan.get("condition_key") or "")
    trigger_type = str(plan.get("trigger_type") or "")
    direction = str(plan.get("direction") or "")
    if direction not in {"buy", "sell"}:
        raise N4POrdinaryExecuteBlocked("ordinary execute requires explicit buy/sell direction")
    expected_signal_type = "B_BUY" if direction == "buy" else "S_SELL"
    expected_prefix = "BUY" if direction == "buy" else "SELL"
    if signal_type != expected_signal_type:
        raise N4POrdinaryExecuteBlocked(
            f"ordinary execute direction/signal_type mismatch: {direction}/{signal_type}"
        )
    if not condition_key.startswith(expected_prefix) or not trigger_type.startswith(expected_prefix):
        raise N4POrdinaryExecuteBlocked(
            "ordinary execute direction/condition/trigger_type mismatch: "
            f"{direction}/{condition_key}/{trigger_type}"
        )
    return direction


def parse_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return utc_now()
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _dedupe_lifecycle_plans(dry_run_plans: Sequence[Mapping[str, Any]], *, event_type: str) -> list[Mapping[str, Any]]:
    deduped: dict[str, Mapping[str, Any]] = {}
    for plan in dry_run_plans:
        if plan.get("output_event_type") != event_type:
            continue
        _assert_ordinary_lifecycle_plan(plan)
        key = str(plan.get("candidate_trigger_identity_key") or "")
        if not key:
            raise N4POrdinaryExecuteBlocked("candidate_trigger_identity_key is required")
        deduped.setdefault(key, plan)
    return list(deduped.values())


def _assert_ordinary_lifecycle_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("output_event_type") not in {ORDINARY_TRIGGER_EVENT_TYPE, ORDINARY_STATE_CHANGED_EVENT_TYPE}:
        raise N4POrdinaryExecuteBlocked(f"unsupported N4P ordinary output_event_type: {plan.get('output_event_type')}")
    condition_key = str(plan.get("condition_key") or "")
    trigger_type = str(plan.get("trigger_type") or "")
    if condition_key in HINT_CONDITION_KEYS or trigger_type in HINT_CONDITION_KEYS:
        raise N4POrdinaryExecuteBlocked(f"ordinary execute received hint condition: {condition_key or trigger_type}")
    if not ordinary_trigger_type_allowed(trigger_type):
        raise N4POrdinaryExecuteBlocked(f"unsupported ordinary trigger_type: {trigger_type}")
    if plan.get("source_metric_kind") != SOURCE_METRIC_KIND:
        raise N4POrdinaryExecuteBlocked(f"unsupported source_metric_kind: {plan.get('source_metric_kind')}")
    direction_for_plan(plan)
    try:
        assert_same_day_period_escalation_output_contract(plan)
    except ValueError as exc:
        raise N4POrdinaryExecuteBlocked(str(exc)) from exc


def _is_same_day_period_escalation_plan(plan: Mapping[str, Any]) -> bool:
    trace = plan.get("period_escalation_trace")
    trace = trace if isinstance(trace, Mapping) else {}
    if trace.get("same_day_formal_evidence") is True:
        return True
    period_traces = trace.get("periods")
    if isinstance(period_traces, Mapping) and any(
        isinstance(period_trace, Mapping)
        and period_trace.get("evidence_source") == SAME_DAY_FORMAL_EVIDENCE_SOURCE
        for period_trace in period_traces.values()
    ):
        return True
    rule_proof = plan.get("rule_proof")
    rule_proof = rule_proof if isinstance(rule_proof, Mapping) else {}
    details = rule_proof.get("triggered_period_details")
    return isinstance(details, list) and any(
        isinstance(detail, Mapping)
        and isinstance(detail.get("period_escalation_trace"), Mapping)
        and detail["period_escalation_trace"].get("evidence_source")
        == SAME_DAY_FORMAL_EVIDENCE_SOURCE
        for detail in details
    )


def ordinary_trigger_type_allowed(trigger_type: str) -> bool:
    if trigger_type in ORDINARY_CONDITION_SIGNAL_TYPES:
        return True
    if trigger_type.startswith("BUY:") or trigger_type.startswith("SELL:"):
        suffix = trigger_type.split(":", 1)[1]
        periods = [period.strip() for period in suffix.split(",") if period.strip()]
        return bool(periods) and all(period in PERIOD_PRIORITY for period in periods)
    return False


def _assert_target_absent(target_counts: Mapping[str, int]) -> None:
    expected_keys = (
        "common_trigger_run",
        "common_trigger_state",
        "common_trigger_match",
        "common_event_outbox",
        "common_event_inbox",
        "checkpoint_refs",
    )
    existing = {name: int(target_counts.get(name) or 0) for name in expected_keys if int(target_counts.get(name) or 0) > 0}
    if existing:
        raise N4POrdinaryExecuteBlocked(f"BLOCKED_TARGET_NOT_EMPTY: {existing}")


def _require_passed_run(run: Mapping[str, Any], *, expected_run_id: str, run_kind: str) -> None:
    run_id = str(run.get("run_id") or run.get("projection_run_id") or "")
    status = str(run.get("status") or "")
    if run_id != expected_run_id:
        raise N4POrdinaryExecuteBlocked(f"{run_kind} lineage mismatch: {run_id} != {expected_run_id}")
    if status != "passed":
        raise N4POrdinaryExecuteBlocked(f"{run_kind} status must be passed: {status}")


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise N4POrdinaryExecuteBlocked(f"{field_name} is required")
    return text


def _matched_plan_by_dedup_key(execute_plan: Mapping[str, Any], dedup_key: str) -> Mapping[str, Any]:
    for row in execute_plan["writes"]["common_trigger_match"]:
        if str(row.get("dedup_key") or "") == dedup_key:
            return dict(row.get("raw_json", {}).get("plan") or {})
    raise N4POrdinaryExecuteBlocked(f"matched plan missing for dedup_key={dedup_key}")


def _state_plan_by_dedup_key(execute_plan: Mapping[str, Any], dedup_key: str) -> Mapping[str, Any]:
    for row in execute_plan["writes"]["common_trigger_state"]:
        if str(row.get("dedup_key") or "") == dedup_key:
            return dict(row.get("raw_json", {}).get("plan") or {})
    raise N4POrdinaryExecuteBlocked(f"state plan missing for dedup_key={dedup_key}")
