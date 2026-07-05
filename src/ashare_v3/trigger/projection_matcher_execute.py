"""N4 real projection matcher run-once execute runner.

This module implements the N4-side contract for consuming the current N3-B1
MarketSnapshotUpdated outbox rows together with N3-B2 projection facts. The
public execute entrypoint requires both --execute and --user-confirmed. Helper
plan builders are pure so contract tests can verify idempotency and boundaries
without touching PostgreSQL.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item
from ashare_v3.events.ids import build_stable_event_id, join_dedup_parts
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    EventEnvelope,
    N4_SOURCE_LAYER,
    utc_now,
    validate_event_envelope,
)
from ashare_v3.events.outbox import OUTBOX_COLUMNS
from ashare_v3.trigger.projection_matcher import (
    DEFAULT_CONTEXT_RUN_ID,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_SYNTHETIC_DENYLIST,
    ROW_COUNT_GUARD_TABLES,
    build_projection_matcher_plans,
    fetch_context_rows,
    fetch_projection_rows,
    is_formal_snapshot_fallback_match,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect, audited_n4_trigger_connect
from ashare_v3.trigger.rule_v4_matcher import (
    condition_signal_type_for_condition_key,
    projection_30m_flags,
)
from ashare_v3.trigger.v4_enforcement import V4EnforcementBlocked, assert_v4_trigger_matched_plan


DEFAULT_SNAPSHOT_RUN_ID = (
    "realtime_daily_snapshot_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
DEFAULT_EXECUTE_RUN_ID = "trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249"
DEFAULT_CONSUMER_NAME = "n4_projection_matcher_consumer_v1"
DEFAULT_JSON_REPORT_PATH = "docs/N4_PROJECTION_MATCHER_EXECUTE_PREFLIGHT_REPORT.json"
DEFAULT_MD_REPORT_PATH = "docs/N4_PROJECTION_MATCHER_EXECUTE_PREFLIGHT_REPORT.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N4_projection_matcher_rollback.sql"
CONTRACT_JSON_PATH = "docs/N4_projection_matcher_execute_contract.json"
CONTRACT_MD_PATH = "docs/N4_PROJECTION_MATCHER_EXECUTE_CONTRACT.md"

SOURCE_LAYER = "N3_market_data"
SOURCE_EVENT_TYPE = "MarketSnapshotUpdated"
EXECUTION_MODE = "run_once"
ALLOWED_OUTPUT_EVENT_TYPES = ("TriggerMatched", "TriggerPendingMarketData")
FORBIDDEN_OUTPUT_EVENT_TYPES = ("TriggerSuppressed", "TriggerNotReady", "TriggerCleared")
SCHEMA_DATA_QUALITY_STATUS = {
    "passed": "passed",
    "partial": "partial",
    "missing": "missing",
    "delayed": "delayed",
    "failed": "failed",
    "not_ready": "missing",
    "blocked": "missing",
    "warning": "partial",
}
N4_EXECUTE_GUARD_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_trigger_run",
    "common_trigger_state",
    "common_trigger_match",
    "common_trigger_quality_item",
    "common_event_outbox",
)
FORMAL_TRIGGER_PERIODS = {"Y", "Q", "M", "W", "D"}
CURRENT_V4_CORRECTED_FORBIDDEN_EXECUTE_RUN_IDS = frozenset(
    {
        "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
    }
)
LEGACY_PROJECTION_MATCHER_ROUTE_METADATA = {
    "route_name": "legacy_outbox_consuming_projection_matcher_execute",
    "source_module": "src/ashare_v3/trigger/projection_matcher_execute.py",
    "script": "scripts/run_trigger_projection_matcher_once.py",
    "deprecated": True,
    "deprecation_reason": (
        "Consumes N3 outbox and writes N4 inbox/checkpoint/state/match/outbox in one route; "
        "current v4 corrected and matched-only 20260605 flow must use dedicated runners."
    ),
    "allowed_scope": "historical_compatibility_or_explicit_projection_matcher_gate_only",
    "allowed_for_current_v4_corrected_flow": False,
    "allowed_for_20260605_n4_execute_gate": False,
    "n5_entry_source_for_current_chain": False,
    "forbidden_execute_run_ids": sorted(CURRENT_V4_CORRECTED_FORBIDDEN_EXECUTE_RUN_IDS),
    "current_v4_corrected_runners": [
        "scripts/run_n4_20260605_v4_corrected_execute_once.py",
        "scripts/run_n4_20260605_matched_only_execute_once.py",
    ],
}


def normalize_action_mark(plan: Mapping[str, Any]) -> str:
    """Resolve the N4 trigger_mark_candidate from current or legacy plan fields."""
    for key in ("action_mark", "trigger_mark_candidate"):
        value = str(plan.get(key) or "").strip()
        if value:
            return value
    return "normal"


def projection_metadata_for_trigger_mark(trigger_mark_candidate: str) -> tuple[bool, str]:
    if trigger_mark_candidate == "30m_volume":
        return True, "volume_up"
    if trigger_mark_candidate == "30m_shrink":
        return True, "shrink_down"
    return False, "none"


def projection_metadata_for_plan(plan: Mapping[str, Any], trigger_mark_candidate: str) -> tuple[bool, str]:
    projection_30m_type = str(plan.get("projection_30m_type") or "")
    if projection_30m_type in {"volume_up", "shrink_down"}:
        return True, projection_30m_type
    return projection_metadata_for_trigger_mark(trigger_mark_candidate)


def normalize_formal_trigger_period(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text in FORMAL_TRIGGER_PERIODS else None


def normalize_trigger_period_for_plan(plan: Mapping[str, Any]) -> str | None:
    text = str(plan.get("trigger_period") or "").strip()
    if (
        text == "30m"
        and plan.get("trigger_kind") == "hint"
        and plan.get("condition_key") in {"BUY_HINT", "SELL_HINT"}
    ):
        return "30m"
    if text in FORMAL_TRIGGER_PERIODS:
        return text
    if (
        plan.get("output_event_type") == "TriggerPendingMarketData"
        and str(plan.get("projection_period") or "").strip() == "30m"
    ):
        return "30m"
    return None


def normalize_formal_periods(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                return [text] if text in FORMAL_TRIGGER_PERIODS else []
            return normalize_formal_periods(parsed)
        return [part.strip() for part in text.split(",") if part.strip() in FORMAL_TRIGGER_PERIODS]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip() in FORMAL_TRIGGER_PERIODS]
    text = str(value).strip()
    return [text] if text in FORMAL_TRIGGER_PERIODS else []


class ProjectionMatcherExecuteError(RuntimeError):
    """Raised when the N4 projection matcher execute gate is blocked."""


def assert_legacy_projection_route_allowed(*, execute_run_id: str) -> None:
    """Fence the deprecated route away from current v4 corrected execute gates."""

    if execute_run_id in CURRENT_V4_CORRECTED_FORBIDDEN_EXECUTE_RUN_IDS:
        raise ProjectionMatcherExecuteError(
            "N4 projection matcher execute blocked: deprecated legacy projection matcher route "
            f"is not allowed for current v4 corrected execute_run_id={execute_run_id}"
        )


def assert_execute_confirmed(
    *,
    execute: bool,
    user_confirmed: bool,
    execute_run_id: str,
    trigger_context_run_id: str,
    projection_run_id: str,
    snapshot_run_id: str,
) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    for field_name, value in (
        ("execute_run_id", execute_run_id),
        ("trigger_context_run_id", trigger_context_run_id),
        ("projection_run_id", projection_run_id),
        ("snapshot_run_id", snapshot_run_id),
    ):
        if not str(value or "").strip():
            missing.append(field_name)
    if missing:
        raise ProjectionMatcherExecuteError(
            "N4 projection matcher execute blocked: missing explicit confirmation/input "
            + ", ".join(missing)
        )
    assert_legacy_projection_route_allowed(execute_run_id=execute_run_id)


def build_execute_contract(
    *,
    consumer_name: str = DEFAULT_CONSUMER_NAME,
    trigger_context_run_id: str = DEFAULT_CONTEXT_RUN_ID,
    projection_run_id: str = DEFAULT_PROJECTION_RUN_ID,
    snapshot_run_id: str = DEFAULT_SNAPSHOT_RUN_ID,
) -> dict[str, Any]:
    return {
        "stage": "N4 projection matcher run-once execute",
        "layer_role": "N4_trigger",
        "route_selection": dict(LEGACY_PROJECTION_MATCHER_ROUTE_METADATA),
        "execution_mode": EXECUTION_MODE,
        "consumer_name": consumer_name,
        "requires_execute_flag": True,
        "requires_user_confirmed_flag": True,
        "source_layer": SOURCE_LAYER,
        "input_event_types": [SOURCE_EVENT_TYPE],
        "input_filter": {
            "source_run_id": snapshot_run_id,
            "status": "pending",
            "source_layer": SOURCE_LAYER,
            "event_type": SOURCE_EVENT_TYPE,
        },
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "synthetic_denylist": list(DEFAULT_SYNTHETIC_DENYLIST),
        "planned_event_types": list(ALLOWED_OUTPUT_EVENT_TYPES),
        "not_planned_event_types": list(FORBIDDEN_OUTPUT_EVENT_TYPES),
        "canonical_payload_fields": [
            "signal_type",
            "trigger_price",
            "trigger_kind",
            "triggered_periods",
            "all_trigger_periods",
            "primary_trigger_period",
            "n5_entry_allowed",
            "projection_period",
            "projection_30m_type",
            "trigger_mark_candidate",
            "condition_key",
            "original_condition_key",
            "match_basis",
        ],
        "canonical_signal_types": ["B_BUY", "S_SELL"],
        "canonical_trigger_mark_candidates": ["normal", "30m_volume", "30m_shrink"],
        "allowed_write_tables": [
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_run",
            "common_trigger_state",
            "common_trigger_match",
            "common_trigger_quality_item",
            "common_event_outbox",
        ],
        "forbidden_write_domains": [
            "N2 condition tables",
            "N3 snapshot/projection facts",
            "N5/N6/action/user/voice/sim/position",
            "old synthetic outbox",
        ],
        "idempotency": {
            "inbox": "consumer_name + event_id and consumer source dedup key",
            "trigger_match": "run_id + source_event_id + trigger grain",
            "outbox": "source_layer + event_type + source_run_id + dedup_key + event_schema_version",
            "checkpoint": "only advances by source outbox_id per partition",
        },
        "side_effects": {
            "worker_started": False,
            "n5_n6_touched": False,
            "market_data_pulled": False,
            "n3_outbox_status_updated": False,
            "old_synthetic_outbox_touched": False,
        },
    }


def build_projection_matcher_execute_plan(
    *,
    execute_run_id: str,
    trigger_context_run_id: str,
    projection_run_id: str,
    snapshot_run_id: str,
    trigger_run: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    source_outbox_rows: Sequence[Mapping[str, Any]],
    existing_inbox_keys: Mapping[str, set[str]],
    existing_checkpoints: Mapping[str, Mapping[str, Any]],
    synthetic_denylist: Sequence[str] = DEFAULT_SYNTHETIC_DENYLIST,
    consumer_name: str = DEFAULT_CONSUMER_NAME,
) -> dict[str, Any]:
    if trigger_context_run_id in set(synthetic_denylist):
        raise ProjectionMatcherExecuteError(
            f"N4 projection matcher execute blocked: context run is synthetic denylisted: {trigger_context_run_id}"
        )
    if str(trigger_run.get("run_id") or "") != trigger_context_run_id:
        raise ProjectionMatcherExecuteError(
            f"N4 projection matcher execute blocked: trigger_run mismatch: {trigger_run.get('run_id')}"
        )
    if str(trigger_run.get("status") or "") != "passed":
        raise ProjectionMatcherExecuteError("N4 projection matcher execute blocked: trigger context run is not passed")

    normalized_source_rows = [normalize_outbox_row(row) for row in source_outbox_rows]
    source_event_plan = build_source_event_plan(
        rows=normalized_source_rows,
        consumer_name=consumer_name,
        snapshot_run_id=snapshot_run_id,
        existing_inbox_keys=existing_inbox_keys,
        existing_checkpoints=existing_checkpoints,
        synthetic_denylist=synthetic_denylist,
    )
    accepted_event_ids = {
        str(row.get("event_id") or "")
        for row in source_event_plan
        if row.get("consumer_status") == "planned_process"
    }
    source_row_by_event_id = {
        str(row.get("event_id") or ""): row
        for row in normalized_source_rows
    }
    inbox_write_plan = [
        build_inbox_write_plan_row(
            event_plan=row,
            execute_run_id=execute_run_id,
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
        )
        for row in source_event_plan
        if row.get("consumer_status") == "planned_process"
    ]
    checkpoint_write_plan = build_checkpoint_write_plan_for_accepted_events(
        execute_run_id=execute_run_id,
        source_event_plan=source_event_plan,
        existing_checkpoints=existing_checkpoints,
    )
    trigger_output_plan, output_dedup_skipped = build_trigger_output_plan(
        execute_run_id=execute_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        snapshot_run_id=snapshot_run_id,
        trigger_run=trigger_run,
        evaluations=evaluations,
        accepted_event_ids=accepted_event_ids,
        source_row_by_event_id=source_row_by_event_id,
        existing_output_dedup_keys=existing_inbox_keys.get("output_dedup_keys", set()),
        existing_outbox_event_ids=existing_inbox_keys.get("outbox_event_ids", set()),
    )
    summary = summarize_execute_plan(
        trigger_context_run_id=trigger_context_run_id,
        synthetic_denylist=synthetic_denylist,
        source_event_plan=source_event_plan,
        trigger_output_plan=trigger_output_plan,
        inbox_write_plan=inbox_write_plan,
        checkpoint_write_plan=checkpoint_write_plan,
        output_dedup_skipped=output_dedup_skipped,
    )
    return {
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "snapshot_run_id": snapshot_run_id,
        "consumer_name": consumer_name,
        "source_event_plan": source_event_plan,
        "inbox_write_plan": inbox_write_plan,
        "checkpoint_write_plan": checkpoint_write_plan,
        "trigger_output_plan": trigger_output_plan,
        "summary": summary,
        "side_effects": {
            "will_execute_sql": True,
            "n3_outbox_status_updated": False,
            "old_synthetic_outbox_touched": False,
            "worker_started": False,
            "n5_n6_touched": False,
        },
    }


def build_source_event_plan(
    *,
    rows: Sequence[Mapping[str, Any]],
    consumer_name: str,
    snapshot_run_id: str,
    existing_inbox_keys: Mapping[str, set[str]],
    existing_checkpoints: Mapping[str, Mapping[str, Any]],
    synthetic_denylist: Sequence[str],
) -> list[dict[str, Any]]:
    seen_event_ids: set[str] = set()
    seen_consumer_dedup_keys: set[str] = set()
    plans: list[dict[str, Any]] = []
    for row in sorted(rows, key=source_sort_key):
        event_id = str(row.get("event_id") or "")
        partition_key = str(row.get("partition_key") or row.get("identity_key") or "")
        consumer_dedup_key = build_source_consumer_dedup_key(row)
        skip_reasons: list[str] = []
        if str(row.get("source_layer") or "") != SOURCE_LAYER:
            skip_reasons.append("unsupported_source_layer")
        if str(row.get("event_type") or "") != SOURCE_EVENT_TYPE:
            skip_reasons.append("unsupported_event_type")
        if str(row.get("source_layer") or "") == SOURCE_LAYER and str(row.get("source_run_id") or "") != snapshot_run_id:
            skip_reasons.append("non_current_snapshot_run")
        if str(row.get("status") or "") != "pending":
            skip_reasons.append("source_event_not_pending")
        if not event_id:
            skip_reasons.append("missing_event_id")
        if not partition_key:
            skip_reasons.append("missing_partition_key")
        if event_id in existing_inbox_keys.get("event_ids", set()):
            skip_reasons.append("existing_inbox_event_id")
        if consumer_dedup_key in existing_inbox_keys.get("consumer_dedup_keys", set()):
            skip_reasons.append("existing_inbox_dedup_key")
        if event_id in seen_event_ids:
            skip_reasons.append("duplicate_event_id_in_batch")
        if consumer_dedup_key in seen_consumer_dedup_keys:
            skip_reasons.append("duplicate_dedup_key_in_batch")
        if is_at_or_before_checkpoint(row, existing_checkpoints.get(partition_key)):
            skip_reasons.append("at_or_before_existing_watermark")

        status = "planned_process" if not skip_reasons else "skipped"
        if status == "planned_process":
            seen_event_ids.add(event_id)
            seen_consumer_dedup_keys.add(consumer_dedup_key)
        plans.append(
            {
                "consumer_name": consumer_name,
                "consumer_status": status,
                "skip_reasons": skip_reasons,
                "source_outbox_id": row.get("outbox_id"),
                "event_id": event_id,
                "event_type": row.get("event_type"),
                "event_schema_version": row.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION,
                "source_layer": row.get("source_layer"),
                "source_run_id": row.get("source_run_id"),
                "dedup_key": row.get("dedup_key"),
                "consumer_dedup_key": consumer_dedup_key,
                "partition_key": partition_key,
                "event_time": row.get("event_time"),
                "asset_kind": row.get("asset_kind"),
                "identity_key": row.get("identity_key"),
                "would_insert_common_event_inbox": status == "planned_process",
                "would_update_consumer_checkpoint": False,
                "would_update_n3_outbox_status": False,
                "source_outbox_row": dict(row),
                "synthetic_denylist_enforced": bool(synthetic_denylist),
            }
        )
    return plans


def build_trigger_output_plan(
    *,
    execute_run_id: str,
    trigger_context_run_id: str,
    projection_run_id: str,
    snapshot_run_id: str,
    trigger_run: Mapping[str, Any],
    evaluations: Sequence[Mapping[str, Any]],
    accepted_event_ids: set[str],
    source_row_by_event_id: Mapping[str, Mapping[str, Any]],
    existing_output_dedup_keys: set[str],
    existing_outbox_event_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen_dedup_keys: set[str] = set()
    output_plan: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for evaluation in evaluations:
        if evaluation.get("plan_status") not in {"matched", "pending"}:
            continue
        event_type = str(evaluation.get("output_event_type") or "")
        if event_type not in ALLOWED_OUTPUT_EVENT_TYPES:
            skipped.append({"plan": dict(evaluation), "skip_reason": "unsupported_output_event_type"})
            continue
        source_event_id = str(evaluation.get("source_event_id") or "")
        if source_event_id not in accepted_event_ids:
            continue
        source_row = source_row_by_event_id.get(source_event_id) or {}
        trigger_mark_candidate = normalize_action_mark(evaluation)
        normalized_evaluation = {**dict(evaluation), "trigger_mark_candidate": trigger_mark_candidate}
        normalized_evaluation.pop("action_mark", None)
        dedup_key = build_output_dedup_key(
            event_type=event_type,
            trade_date=str(trigger_run.get("for_trade_date") or source_row.get("trade_date") or ""),
            plan=normalized_evaluation,
        )
        output_event_id = build_stable_event_id(
            source_layer=N4_SOURCE_LAYER,
            event_type=event_type,
            source_run_id=execute_run_id,
            dedup_key=dedup_key,
            event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        )
        if dedup_key in existing_output_dedup_keys or output_event_id in existing_outbox_event_ids or dedup_key in seen_dedup_keys:
            skipped.append({"plan": dict(evaluation), "skip_reason": "duplicate_output_dedup_key", "dedup_key": dedup_key})
            continue
        seen_dedup_keys.add(dedup_key)
        plan = {
            **normalized_evaluation,
            "run_id": execute_run_id,
            "trigger_context_run_id": trigger_context_run_id,
            "projection_run_id": projection_run_id,
            "source_snapshot_run_id": snapshot_run_id,
            "source_outbox_id": source_row.get("outbox_id"),
            "source_event_time": source_row.get("event_time"),
            "event_time": (
                source_row.get("event_time")
                or normalized_evaluation.get("event_time")
                or normalized_evaluation.get("trigger_time")
            ),
            "source_event_payload": source_row.get("payload_json") or {},
            "output_event_id": output_event_id,
            "output_dedup_key": dedup_key,
            "data_quality_status": normalize_trigger_data_quality_status(evaluation.get("data_quality_status")),
            "would_write_trigger_state": True,
            "would_write_trigger_match": event_type == "TriggerMatched",
            "would_write_n4_outbox": True,
        }
        if event_type == "TriggerMatched":
            try:
                assert_v4_trigger_matched_plan(plan)
            except V4EnforcementBlocked as exc:
                raise ProjectionMatcherExecuteError(
                    f"N4 projection matcher v4 enforcement blocked TriggerMatched before writes: {exc}"
                ) from exc
        output_plan.append(plan)
    return output_plan, skipped


def build_checkpoint_write_plan_for_accepted_events(
    *,
    execute_run_id: str,
    source_event_plan: Sequence[Mapping[str, Any]],
    existing_checkpoints: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    accepted_by_partition: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for plan in source_event_plan:
        if plan.get("consumer_status") == "planned_process":
            accepted_by_partition[str(plan.get("partition_key") or "")].append(plan)
    checkpoint_rows: list[dict[str, Any]] = []
    for partition_key, plans in sorted(accepted_by_partition.items()):
        last_plan = sorted(plans, key=source_plan_sort_key)[-1]
        checkpoint = build_checkpoint_write_plan(last_plan, existing_checkpoints.get(partition_key))
        checkpoint["execute_run_id"] = execute_run_id
        checkpoint["accepted_event_count"] = len(plans)
        checkpoint_rows.append(checkpoint)
    return checkpoint_rows


def build_checkpoint_write_plan(
    event_plan: Mapping[str, Any],
    existing_checkpoint: Mapping[str, Any] | None,
) -> dict[str, Any]:
    would_advance = not is_event_plan_at_or_before_checkpoint(event_plan, existing_checkpoint)
    return {
        "consumer_name": event_plan.get("consumer_name") or DEFAULT_CONSUMER_NAME,
        "partition_key": event_plan.get("partition_key"),
        "source_layer": SOURCE_LAYER,
        "last_event_id": event_plan.get("event_id"),
        "last_event_time": event_plan.get("event_time"),
        "last_outbox_id": event_plan.get("source_outbox_id"),
        "checkpoint_payload": {
            "stage": "N4_projection_matcher_execute",
            "execution_mode": EXECUTION_MODE,
            "watermark_policy": "partition_key + event_time + outbox_id + event_id",
        },
        "would_insert_or_update_common_event_consumer_checkpoint": would_advance,
        "skip_reason": None if would_advance else "checkpoint_not_advanced",
    }


def build_inbox_write_plan_row(
    *,
    event_plan: Mapping[str, Any],
    execute_run_id: str,
    trigger_context_run_id: str,
    projection_run_id: str,
) -> dict[str, Any]:
    return {
        "consumer_name": event_plan.get("consumer_name") or DEFAULT_CONSUMER_NAME,
        "event_id": event_plan.get("event_id"),
        "event_type": event_plan.get("event_type"),
        "event_schema_version": event_plan.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION,
        "source_layer": event_plan.get("source_layer"),
        "source_run_id": event_plan.get("source_run_id"),
        "dedup_key": event_plan.get("dedup_key"),
        "partition_key": event_plan.get("partition_key"),
        "payload_json": (event_plan.get("source_outbox_row") or {}).get("payload_json") or {},
        "status": "processed",
        "raw_json": {
            "processing_result": "processed",
            "execute_run_id": execute_run_id,
            "trigger_context_run_id": trigger_context_run_id,
            "projection_run_id": projection_run_id,
            "source_outbox_id": event_plan.get("source_outbox_id"),
        },
        "would_insert_common_event_inbox": True,
    }


def summarize_execute_plan(
    *,
    trigger_context_run_id: str,
    synthetic_denylist: Sequence[str],
    source_event_plan: Sequence[Mapping[str, Any]],
    trigger_output_plan: Sequence[Mapping[str, Any]],
    inbox_write_plan: Sequence[Mapping[str, Any]],
    checkpoint_write_plan: Sequence[Mapping[str, Any]],
    output_dedup_skipped: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    accepted = [row for row in source_event_plan if row.get("consumer_status") == "planned_process"]
    skipped = [row for row in source_event_plan if row.get("consumer_status") == "skipped"]
    matched = [row for row in trigger_output_plan if row.get("output_event_type") == "TriggerMatched"]
    pending = [row for row in trigger_output_plan if row.get("output_event_type") == "TriggerPendingMarketData"]
    return {
        "source_event_read_count": len(source_event_plan),
        "accepted_source_event_count": len(accepted),
        "skipped_source_event_count": len(skipped),
        "skipped_source_event_reasons": count_skip_reasons(skipped),
        "inbox_write_plan_count": len(inbox_write_plan),
        "checkpoint_write_plan_count": sum(
            1
            for row in checkpoint_write_plan
            if row.get("would_insert_or_update_common_event_consumer_checkpoint")
        ),
        "trigger_output_plan_count": len(trigger_output_plan),
        "matched_output_count": len(matched),
        "pending_output_count": len(pending),
        "output_dedup_skipped_count": len(output_dedup_skipped),
        "matched_by_signal_type": count_by(matched, "signal_type"),
        "pending_by_signal_type": count_by(pending, "signal_type"),
        "matched_by_trigger_mark_candidate": count_by(matched, "trigger_mark_candidate"),
        "pending_by_trigger_mark_candidate": count_by(pending, "trigger_mark_candidate"),
        "matched_by_legacy_signal_type": count_by(matched, "legacy_signal_type"),
        "pending_by_legacy_signal_type": count_by(pending, "legacy_signal_type"),
        "board_not_ready_pending_count": sum(
            1 for row in pending if row.get("asset_kind") == "board" and is_projection_not_ready(row)
        ),
        "bj_920xxx_not_ready_pending_count": sum(
            1
            for row in pending
            if str(row.get("identity_key") or "").startswith("stock:BJ:920") and is_projection_not_ready(row)
        ),
        "board_bj_not_ready_matched_count": sum(
            1
            for row in matched
            if (row.get("asset_kind") == "board" or str(row.get("identity_key") or "").startswith("stock:BJ:920"))
            and is_projection_not_ready(row)
            and not is_formal_snapshot_fallback_match(row)
        ),
        "formal_snapshot_fallback_board_bj_matched_count": sum(
            1
            for row in matched
            if (row.get("asset_kind") == "board" or str(row.get("identity_key") or "").startswith("stock:BJ:920"))
            and is_projection_not_ready(row)
            and is_formal_snapshot_fallback_match(row)
        ),
        "planned_event_types": sorted({str(row.get("output_event_type") or "") for row in trigger_output_plan}),
        "synthetic_denylist_enforced": True,
        "current_context_is_denylisted": trigger_context_run_id in set(synthetic_denylist),
        "n3_outbox_status_update_count": 0,
        "worker_started": False,
    }


def is_projection_not_ready(row: Mapping[str, Any]) -> bool:
    classification = str(row.get("not_ready_classification") or "").strip().lower()
    if classification and classification not in {"none", "null", "ready"}:
        return True
    if str(row.get("projection_status") or "") == "not_ready":
        return True
    if str(row.get("projection_quality_status") or "") == "blocked":
        return True
    if str(row.get("trace_status") or "") == "blocked":
        return True
    return False


def run_projection_matcher_execute_preflight(
    *,
    dsn: str,
    execute_run_id: str = DEFAULT_EXECUTE_RUN_ID,
    trigger_context_run_id: str = DEFAULT_CONTEXT_RUN_ID,
    projection_run_id: str = DEFAULT_PROJECTION_RUN_ID,
    snapshot_run_id: str = DEFAULT_SNAPSHOT_RUN_ID,
    consumer_name: str = DEFAULT_CONSUMER_NAME,
    json_report_path: str = DEFAULT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
    dry_run_report_path: str | None = None,
    sample_limit: int = 80,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    assert_legacy_projection_route_allowed(execute_run_id=execute_run_id)
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_projection_matcher_execute_preflight",
        source_run_id=execute_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        before_counts = fetch_row_counts(cur, N4_EXECUTE_GUARD_TABLES)
        context_rows, trigger_run = fetch_context_rows(dsn, trigger_context_run_id)
        projection_rows = fetch_projection_rows(dsn, projection_run_id)
        source_outbox_rows = fetch_current_snapshot_outbox_rows(cur, snapshot_run_id)
        existing_inbox_keys = fetch_existing_inbox_keys(cur, consumer_name, execute_run_id)
        existing_checkpoints = fetch_existing_checkpoints(cur, consumer_name)
        after_counts = fetch_row_counts(cur, N4_EXECUTE_GUARD_TABLES)

    evaluations = build_projection_matcher_plans(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        context_rows=context_rows,
        projection_rows=projection_rows,
        synthetic_denylist=DEFAULT_SYNTHETIC_DENYLIST,
    )
    execute_plan = build_projection_matcher_execute_plan(
        execute_run_id=execute_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        snapshot_run_id=snapshot_run_id,
        trigger_run=trigger_run,
        evaluations=evaluations,
        source_outbox_rows=source_outbox_rows,
        existing_inbox_keys=existing_inbox_keys,
        existing_checkpoints=existing_checkpoints,
        synthetic_denylist=DEFAULT_SYNTHETIC_DENYLIST,
        consumer_name=consumer_name,
    )
    rollback_sql = build_projection_matcher_rollback_sql(execute_run_id, consumer_name)
    dry_run_alignment = load_dry_run_alignment(dry_run_report_path)
    quality_items = build_preflight_quality_items(
        execute_plan=execute_plan,
        dry_run_alignment=dry_run_alignment,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
    )
    quality_counts = count_quality_severities(quality_items)
    report = {
        "stage": "N4-projection-matcher-execute-preflight",
        "result": "PREFLIGHT_PASS" if quality_counts["P0"] == 0 else "PREFLIGHT_BLOCKED",
        "layer_role": "N4_trigger",
        "mode": "real_projection_matcher_run_once_execute_preflight",
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "snapshot_run_id": snapshot_run_id,
        "consumer_name": consumer_name,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "execute_contract": build_execute_contract(
            consumer_name=consumer_name,
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
            snapshot_run_id=snapshot_run_id,
        ),
        "dry_run_alignment": dry_run_alignment,
        "execute_plan_summary": execute_plan["summary"],
        "source_event_plan": execute_plan["source_event_plan"],
        "trigger_output_plan": execute_plan["trigger_output_plan"],
        "inbox_write_plan": execute_plan["inbox_write_plan"],
        "checkpoint_write_plan": execute_plan["checkpoint_write_plan"],
        "sample_source_event_plan": execute_plan["source_event_plan"][:sample_limit],
        "sample_trigger_output_plan": execute_plan["trigger_output_plan"][:sample_limit],
        "sample_inbox_write_plan": execute_plan["inbox_write_plan"][:sample_limit],
        "sample_checkpoint_write_plan": execute_plan["checkpoint_write_plan"][:sample_limit],
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "before_row_counts": before_counts,
        "after_row_counts": after_counts,
        "rollback_sql_path": rollback_sql_path,
        "rollback_sql": rollback_sql,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "writes_performed": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "trigger_state_written": False,
            "trigger_match_written": False,
            "event_outbox_written": False,
            "n3_outbox_status_updated": False,
            "market_data_pulled": False,
            "worker_started": False,
            "downstream_layers_touched": False,
        },
        "next_gate": {
            "allow_real_execute_user_confirmation": quality_counts["P0"] == 0,
            "execute_requires": ["--execute", "--user-confirmed"],
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_preflight_report(report))
    write_text(rollback_sql_path, rollback_sql)
    return report


def run_projection_matcher_once(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    execute_run_id: str = DEFAULT_EXECUTE_RUN_ID,
    trigger_context_run_id: str = DEFAULT_CONTEXT_RUN_ID,
    projection_run_id: str = DEFAULT_PROJECTION_RUN_ID,
    snapshot_run_id: str = DEFAULT_SNAPSHOT_RUN_ID,
    consumer_name: str = DEFAULT_CONSUMER_NAME,
    json_report_path: str = DEFAULT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
    dry_run_report_path: str | None = None,
    sample_limit: int = 80,
) -> dict[str, Any]:
    assert_execute_confirmed(
        execute=execute,
        user_confirmed=user_confirmed,
        execute_run_id=execute_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        snapshot_run_id=snapshot_run_id,
    )
    preflight = run_projection_matcher_execute_preflight(
        dsn=dsn,
        execute_run_id=execute_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        snapshot_run_id=snapshot_run_id,
        consumer_name=consumer_name,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        rollback_sql_path=rollback_sql_path,
        dry_run_report_path=dry_run_report_path,
        sample_limit=sample_limit,
    )
    if int(preflight["quality"]["p0_count"]) > 0:
        raise ProjectionMatcherExecuteError("N4 projection matcher execute blocked: preflight has P0 findings")

    inserted_counts = execute_projection_matcher_transaction(dsn=dsn, preflight=preflight)
    preflight["result"] = "EXECUTED"
    preflight["inserted_counts"] = inserted_counts
    preflight["side_effects"].update(
        {
            "will_execute_sql": True,
            "writes_performed": True,
            "common_event_inbox_written": True,
            "checkpoint_written": True,
            "trigger_state_written": True,
            "trigger_match_written": True,
            "event_outbox_written": True,
        }
    )
    write_json(json_report_path, preflight)
    write_text(markdown_report_path, format_preflight_report(preflight))
    return preflight


def execute_projection_matcher_transaction(*, dsn: str, preflight: Mapping[str, Any]) -> dict[str, int]:
    execute_run_id = str(preflight["execute_run_id"])
    trigger_context_run_id = str(preflight["trigger_context_run_id"])
    projection_run_id = str(preflight["projection_run_id"])
    snapshot_run_id = str(preflight["snapshot_run_id"])
    consumer_name = str(preflight["consumer_name"])
    plan_summary = dict(preflight["execute_plan_summary"])
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_projection_matcher_execute_transaction",
        source_run_id=execute_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            context_run = fetch_trigger_run_for_update(cur, trigger_context_run_id)
            upsert_execute_trigger_run(
                cur,
                execute_run_id=execute_run_id,
                context_run=context_run,
                projection_run_id=projection_run_id,
                snapshot_run_id=snapshot_run_id,
                plan_summary=plan_summary,
            )
            quality_count = insert_quality_items(
                cur,
                execute_run_id=execute_run_id,
                context_run=context_run,
                items=preflight["quality"]["items"],
            )
            inbox_count = insert_inbox_records(
                cur,
                rows=preflight["inbox_write_plan"],
                consumer_name=consumer_name,
            )
            state_match_outbox_counts = execute_trigger_output_rows(
                cur,
                execute_run_id=execute_run_id,
                context_run=context_run,
                rows=preflight["trigger_output_plan"],
            )
            checkpoint_count = upsert_checkpoints(cur, rows=preflight["checkpoint_write_plan"], consumer_name=consumer_name)
            update_execute_trigger_run_finished(
                cur,
                execute_run_id=execute_run_id,
                p0_count=int(preflight["quality"]["p0_count"]),
                p1_count=int(preflight["quality"]["p1_count"]),
                p2_count=int(preflight["quality"]["p2_count"]),
                trigger_state_count=state_match_outbox_counts["common_trigger_state"],
                trigger_match_count=state_match_outbox_counts["common_trigger_match"],
                outbox_count=state_match_outbox_counts["common_event_outbox"],
            )
        conn.commit()
    return {
        "common_event_inbox": inbox_count,
        "common_event_consumer_checkpoint": checkpoint_count,
        "common_trigger_quality_item": quality_count,
        **state_match_outbox_counts,
    }


def build_output_dedup_key(*, event_type: str, trade_date: str, plan: Mapping[str, Any]) -> str:
    dedup_trigger_period = str(plan.get("trigger_period") or plan.get("projection_period") or "none")
    return join_dedup_parts(
        "N4_trigger",
        event_type,
        str(plan.get("source_event_id") or ""),
        str(plan.get("source_event_type") or SOURCE_EVENT_TYPE),
        str(plan.get("asset_kind") or ""),
        str(plan.get("identity_key") or ""),
        trade_date,
        "direction",
        str(plan.get("direction") or ""),
        "signal_type",
        str(plan.get("signal_type") or ""),
        "action_mark",
        normalize_action_mark(plan),
        "condition_key",
        str(plan.get("condition_key") or ""),
        "original_condition_key",
        str(plan.get("original_condition_key") or plan.get("condition_key") or ""),
        "trigger_period",
        dedup_trigger_period,
        "trigger_bucket",
        str(plan.get("trigger_bucket") or ""),
    )


def build_projection_matcher_rollback_sql(execute_run_id: str, consumer_name: str = DEFAULT_CONSUMER_NAME) -> str:
    return f"""-- N4 projection matcher execute rollback.
-- Scope: N4 execute run only. Run only after confirming N4 outbox rows for
-- this execute_run_id have not been delivered to N5 and no downstream layer
-- has consumed them. This rollback intentionally keeps all N3 facts and the
-- original N3 outbox rows intact.

BEGIN;

DO $$
BEGIN
  RAISE EXCEPTION 'N4 projection matcher rollback is guarded. Review delivered outbox, inbox/checkpoint, N5/N6, notification, sim, position, and trade refs before enabling scoped deletes for {execute_run_id}.';
END $$;

-- Safety preview.
SELECT event_type, status, count(*) AS row_count
FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = '{execute_run_id}'
GROUP BY event_type, status
ORDER BY event_type, status;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = '{execute_run_id}';

DELETE FROM common_trigger_match
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_state
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_quality_item
WHERE run_id = '{execute_run_id}';

DELETE FROM common_event_inbox
WHERE consumer_name = '{consumer_name}'
  AND raw_json ->> 'execute_run_id' = '{execute_run_id}';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = '{consumer_name}'
  AND source_layer = 'N3_market_data'
  AND checkpoint_payload ->> 'execute_run_id' = '{execute_run_id}';

DELETE FROM common_trigger_run
WHERE run_id = '{execute_run_id}';

COMMIT;
"""


def normalize_outbox_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["payload_json"] = output.get("payload_json") or {}
    output["status"] = output.get("status") or "pending"
    output["event_schema_version"] = output.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION
    return output


def normalize_trigger_data_quality_status(value: Any) -> str:
    text = str(value or "missing")
    return SCHEMA_DATA_QUALITY_STATUS.get(text, "missing")


def build_source_consumer_dedup_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("source_layer") or ""),
            str(row.get("event_type") or ""),
            str(row.get("source_run_id") or ""),
            str(row.get("dedup_key") or ""),
            str(row.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION),
        ]
    )


def source_sort_key(row: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(row.get("partition_key") or row.get("identity_key") or ""),
        normalize_event_time_for_sort(row.get("event_time")),
        int(row.get("outbox_id") or 0),
        str(row.get("event_id") or ""),
    )


def source_plan_sort_key(row: Mapping[str, Any]) -> tuple[str, int, str]:
    return (
        normalize_event_time_for_sort(row.get("event_time")),
        int(row.get("source_outbox_id") or 0),
        str(row.get("event_id") or ""),
    )


def normalize_event_time_for_sort(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def is_at_or_before_checkpoint(row: Mapping[str, Any], checkpoint: Mapping[str, Any] | None) -> bool:
    if not checkpoint:
        return False
    last_outbox_id = checkpoint.get("last_outbox_id")
    row_outbox_id = row.get("outbox_id")
    if last_outbox_id is not None and row_outbox_id is not None:
        try:
            return int(row_outbox_id) <= int(last_outbox_id)
        except (TypeError, ValueError):
            return False
    return False


def is_event_plan_at_or_before_checkpoint(
    event_plan: Mapping[str, Any],
    checkpoint: Mapping[str, Any] | None,
) -> bool:
    if not checkpoint:
        return False
    last_outbox_id = checkpoint.get("last_outbox_id")
    source_outbox_id = event_plan.get("source_outbox_id")
    if last_outbox_id is not None and source_outbox_id is not None:
        try:
            return int(source_outbox_id) <= int(last_outbox_id)
        except (TypeError, ValueError):
            return False
    return False


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def count_skip_reasons(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for reason in row.get("skip_reasons") or []:
            counter[str(reason)] += 1
    return dict(sorted(counter.items()))


def fetch_current_snapshot_outbox_rows(cur: psycopg.Cursor[dict[str, Any]], snapshot_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT outbox_id, event_id, event_type, event_schema_version, trade_date,
               asset_kind, identity_key, event_time, source_layer, source_run_id,
               dedup_key, partition_key, payload_json, status, created_at, updated_at
        FROM common_event_outbox
        WHERE source_layer = %s
          AND event_type = %s
          AND source_run_id = %s
          AND status = 'pending'
        ORDER BY partition_key, event_time, outbox_id, event_id
        """,
        (SOURCE_LAYER, SOURCE_EVENT_TYPE, snapshot_run_id),
    )
    return [normalize_outbox_row(row) for row in cur.fetchall()]


def fetch_existing_inbox_keys(
    cur: psycopg.Cursor[dict[str, Any]],
    consumer_name: str,
    execute_run_id: str,
) -> dict[str, set[str]]:
    event_ids: set[str] = set()
    consumer_dedup_keys: set[str] = set()
    output_dedup_keys: set[str] = set()
    outbox_event_ids: set[str] = set()
    cur.execute(
        """
        SELECT event_id, source_layer, event_type, source_run_id, dedup_key, event_schema_version
        FROM common_event_inbox
        WHERE consumer_name = %s
        """,
        (consumer_name,),
    )
    for row in cur.fetchall():
        normalized = normalize_mapping(row)
        event_ids.add(str(normalized.get("event_id") or ""))
        consumer_dedup_keys.add(build_source_consumer_dedup_key(normalized))
    cur.execute(
        """
        SELECT event_id, event_type, source_run_id, dedup_key, event_schema_version
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
        """,
        (execute_run_id,),
    )
    for row in cur.fetchall():
        normalized = normalize_mapping(row)
        outbox_event_ids.add(str(normalized.get("event_id") or ""))
        output_dedup_keys.add(str(normalized.get("dedup_key") or ""))
    return {
        "event_ids": event_ids,
        "consumer_dedup_keys": consumer_dedup_keys,
        "output_dedup_keys": output_dedup_keys,
        "outbox_event_ids": outbox_event_ids,
    }


def fetch_existing_checkpoints(cur: psycopg.Cursor[dict[str, Any]], consumer_name: str) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT consumer_name, partition_key, source_layer, last_event_id,
               last_event_time, last_outbox_id, checkpoint_payload, updated_at
        FROM common_event_consumer_checkpoint
        WHERE consumer_name = %s
          AND source_layer = %s
        """,
        (consumer_name, SOURCE_LAYER),
    )
    return {str(row["partition_key"]): normalize_mapping(row) for row in cur.fetchall()}


def fetch_row_counts(cur: psycopg.Cursor[dict[str, Any]], table_names: Sequence[str]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for table_name in table_names:
        cur.execute("SELECT to_regclass(%s) AS table_oid", (table_name,))
        exists = cur.fetchone()["table_oid"] is not None
        if not exists:
            counts[table_name] = {"exists": False, "row_count": None, "status": "missing"}
            continue
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
        counts[table_name] = {"exists": True, "row_count": int(cur.fetchone()["row_count"]), "status": "present"}
    return counts


def load_dry_run_alignment(dry_run_report_path: str | None) -> dict[str, Any]:
    if not dry_run_report_path:
        return {"source": None, "result": None, "p0_count": None}

    report_path = Path(dry_run_report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = dict(report.get("summary") or {})
    reviewed_counts = dict(report.get("reviewed_expected_counts") or {})
    quality = dict(report.get("quality") or {})
    return {
        "source": str(report_path),
        "result": report.get("result"),
        "p0_count": int(quality.get("p0_count") or 0),
        "expected_matched_count": int(
            summary.get("matched_count")
            if summary.get("matched_count") is not None
            else reviewed_counts.get("TriggerMatched")
            or 0
        ),
        "expected_pending_count": int(
            summary.get("pending_count")
            if summary.get("pending_count") is not None
            else reviewed_counts.get("TriggerPendingMarketData")
            or 0
        ),
    }


def build_preflight_quality_items(
    *,
    execute_plan: Mapping[str, Any],
    dry_run_alignment: Mapping[str, Any] | None = None,
    before_row_counts: Mapping[str, Mapping[str, Any]],
    after_row_counts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    summary = execute_plan["summary"]
    dry_run_alignment = dry_run_alignment or {}
    expected_matched_count = int(
        dry_run_alignment.get("expected_matched_count")
        if dry_run_alignment.get("expected_matched_count") is not None
        else summary.get("matched_output_count")
        or 0
    )
    expected_pending_count = int(
        dry_run_alignment.get("expected_pending_count")
        if dry_run_alignment.get("expected_pending_count") is not None
        else summary.get("pending_output_count")
        or 0
    )
    row_counts_unchanged = before_row_counts == after_row_counts
    items: list[dict[str, Any]] = []
    if dry_run_alignment.get("source"):
        dry_run_result = str(dry_run_alignment.get("result") or "")
        dry_run_p0 = int(dry_run_alignment.get("p0_count") or 0)
        items.append(
            quality_item(
                "P0",
                "passed" if dry_run_result == "DRY_RUN_PASS" and dry_run_p0 == 0 else "failed",
                "n4_projection_execute_dry_run_alignment_passed",
                "N4 projection execute preflight must align to a passed refreshed dry-run artifact",
                expected="DRY_RUN_PASS/P0=0",
                actual=f"{dry_run_result}/P0={dry_run_p0}",
            )
        )
    items.extend(
        [
        quality_item(
            "P0",
            "passed" if int(summary.get("accepted_source_event_count") or 0) > 0 else "failed",
            "n4_projection_execute_current_b1_events_available",
            "N4 projection execute must have current B1 MarketSnapshotUpdated events to process",
            expected=">0",
            actual=str(summary.get("accepted_source_event_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("matched_output_count") or 0) == expected_matched_count else "failed",
            "n4_projection_execute_matched_count_matches_dry_run",
            "N4 projection execute planned TriggerMatched count must match refreshed dry-run",
            expected=str(expected_matched_count),
            actual=str(summary.get("matched_output_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("pending_output_count") or 0) == expected_pending_count else "failed",
            "n4_projection_execute_pending_count_matches_dry_run",
            "N4 projection execute planned TriggerPendingMarketData count must match refreshed dry-run",
            expected=str(expected_pending_count),
            actual=str(summary.get("pending_output_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("board_bj_not_ready_matched_count") or 0) == 0 else "failed",
            "n4_projection_execute_board_bj_not_ready_no_match",
            "board and BJ not_ready projection rows must not become TriggerMatched",
            expected="0",
            actual=str(summary.get("board_bj_not_ready_matched_count") or 0),
        ),
        quality_item(
            "P0",
            "passed"
            if set(summary.get("planned_event_types") or [])
            and set(summary.get("planned_event_types") or []).issubset(set(ALLOWED_OUTPUT_EVENT_TYPES))
            else "failed",
            "n4_projection_execute_only_allowed_output_events",
            "N4 projection execute must plan only allowed canonical output event types",
            expected="subset of TriggerMatched,TriggerPendingMarketData",
            actual=",".join(summary.get("planned_event_types") or []),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("n3_outbox_status_update_count") or 0) == 0 else "failed",
            "n4_projection_execute_no_n3_outbox_status_update",
            "N4 projection execute must not update upstream N3 outbox status",
            expected="0",
            actual=str(summary.get("n3_outbox_status_update_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n4_projection_execute_preflight_read_only",
            "N4 projection execute preflight must not change DB row counts",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item("P0", "passed", "n4_projection_execute_no_worker", "N4 projection execute is run-once only"),
        quality_item("P0", "passed", "n4_projection_execute_no_downstream", "N4 projection execute does not enter N5/N6"),
        ]
    )
    return items


def fetch_trigger_run_for_update(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, source_market_data_run_id,
               for_trade_date, source_trade_date, prev_trade_date, status,
               context_snapshot_row_count
        FROM common_trigger_run
        WHERE run_id = %s
        FOR SHARE
        """,
        (run_id,),
    )
    row = normalize_mapping(cur.fetchone() or {})
    if not row:
        raise ProjectionMatcherExecuteError(f"N4 projection matcher execute blocked: context run not found: {run_id}")
    return row


def upsert_execute_trigger_run(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    context_run: Mapping[str, Any],
    projection_run_id: str,
    snapshot_run_id: str,
    plan_summary: Mapping[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO common_trigger_run (
          run_id, source_condition_run_id, source_market_data_run_id,
          for_trade_date, source_trade_date, prev_trade_date,
          mode, status, context_snapshot_row_count, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'execute', 'running', %s, %s)
        ON CONFLICT (run_id) DO UPDATE SET
          status = 'running',
          raw_json = EXCLUDED.raw_json,
          updated_at = now()
        """,
        (
            execute_run_id,
            context_run["source_condition_run_id"],
            context_run.get("source_market_data_run_id"),
            context_run["for_trade_date"],
            context_run["source_trade_date"],
            context_run["prev_trade_date"],
            int(context_run.get("context_snapshot_row_count") or 0),
            Jsonb(
                to_jsonable({
                    "stage": "N4_projection_matcher_execute",
                    "trigger_context_run_id": context_run["run_id"],
                    "projection_run_id": projection_run_id,
                    "snapshot_run_id": snapshot_run_id,
                    "plan_summary": dict(plan_summary),
                })
            ),
        ),
    )


def insert_quality_items(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    context_run: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
) -> int:
    if not items:
        return 0
    rows = []
    for item in items:
        gate_code = str(item.get("gate_code") or "")
        rows.append(
            (
                execute_run_id,
                context_run["source_condition_run_id"],
                context_run["for_trade_date"],
                context_run["source_trade_date"],
                "common",
                "event_contract" if "event" in gate_code else "trigger_run",
                "common_event_inbox/common_event_consumer_checkpoint/common_trigger_match/common_event_outbox",
                gate_code,
                str(item.get("gate_name") or gate_code),
                str(item.get("severity") or "P0"),
                str(item.get("status") or "passed"),
                item.get("expected_value"),
                item.get("actual_value"),
                None,
                Jsonb(to_jsonable(item.get("details") or {})),
            )
        )
    cur.executemany(
        """
        INSERT INTO common_trigger_quality_item (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          data_domain, layer_scope, table_name, gate_code, gate_name, severity,
          status, expected_value, actual_value, identity_key, details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return len(rows)


def build_unified_trigger_payload_fields(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return payload-only unified trigger signal fields for outbox/raw_json."""

    condition_key = str(plan.get("condition_key") or "")
    direction = str(plan.get("direction") or "")
    trigger_kind = str(plan.get("trigger_kind") or ("hint" if condition_key in {"BUY_HINT", "SELL_HINT"} else "trigger"))
    signal_type = str(plan.get("signal_type") or ("S_SELL" if direction == "sell" else "B_BUY"))
    condition_signal_type = str(
        plan.get("condition_signal_type")
        or condition_signal_type_for_condition_key(
            condition_key,
            direction=direction,
            condition_family="hint" if trigger_kind == "hint" else "ordinary",
        )
    )
    projection_30m_flag, projection_30m_type = projection_metadata_for_plan(
        plan,
        str(plan.get("trigger_mark_candidate") or plan.get("action_mark") or "normal"),
    )
    volume_flag, shrink_flag = projection_30m_flags(
        plan.get("projection_30m_type") or projection_30m_type,
        projection_30m_flag=bool(plan.get("projection_30m_flag") if plan.get("projection_30m_flag") is not None else projection_30m_flag),
    )
    requested_periods = normalize_formal_periods(plan.get("requested_periods"))
    if not requested_periods and trigger_kind != "hint":
        requested_periods = requested_periods_for_condition_key(condition_key)
    triggered_details = plan.get("triggered_period_details")
    if triggered_details is None:
        if trigger_kind == "hint" or plan.get("output_event_type") != "TriggerMatched":
            triggered_details = []
        else:
            triggered_details = [
                {
                    "period": period,
                    "classification": "triggered",
                    "trigger_price": plan.get("trigger_price"),
                    "baseline_source": plan.get("baseline_source") or "trigger_baseline",
                }
                for period in normalize_formal_periods(plan.get("triggered_periods"))
            ]

    return {
        "signal_type": signal_type,
        "runtime_signal_type": plan.get("runtime_signal_type") or signal_type,
        "direction": direction,
        "condition_signal_type": condition_signal_type,
        "condition_key": condition_key,
        "original_condition_key": plan.get("original_condition_key") or condition_key,
        "trigger_kind": trigger_kind,
        "trigger_mark_candidate": plan.get("trigger_mark_candidate") or plan.get("action_mark") or "normal",
        "requested_periods": requested_periods,
        "triggered_periods": normalize_formal_periods(plan.get("triggered_periods")),
        "all_trigger_periods": normalize_formal_periods(plan.get("all_trigger_periods")),
        "primary_trigger_period": normalize_formal_trigger_period(plan.get("primary_trigger_period")),
        "triggered_period_details": to_jsonable(triggered_details),
        "trigger_period": normalize_trigger_period_for_plan(plan),
        "trigger_price": plan.get("trigger_price"),
        "trigger_time": plan.get("trigger_time") or plan.get("source_event_time"),
        "event_time": plan.get("event_time") or plan.get("trigger_time") or plan.get("source_event_time"),
        "price_source": plan.get("price_source") or (
            "n3_realtime_projection" if plan.get("match_basis") == "intraday_projection" else "n3_realtime_snapshot"
        ),
        "match_basis": plan.get("match_basis"),
        "baseline_source": plan.get("baseline_source") or "trigger_baseline",
        "projection_30m_required": bool(
            plan.get("projection_30m_required")
            if plan.get("projection_30m_required") is not None
            else trigger_kind == "hint"
        ),
        "projection_30m_flag": bool(plan.get("projection_30m_flag") if plan.get("projection_30m_flag") is not None else projection_30m_flag),
        "projection_30m_type": plan.get("projection_30m_type") or projection_30m_type,
        "projection_period": plan.get("projection_period") or ("30m" if projection_30m_flag else None),
        "projection_30m_volume_up_flag": bool(
            plan.get("projection_30m_volume_up_flag")
            if plan.get("projection_30m_volume_up_flag") is not None
            else volume_flag
        ),
        "projection_30m_shrink_down_flag": bool(
            plan.get("projection_30m_shrink_down_flag")
            if plan.get("projection_30m_shrink_down_flag") is not None
            else shrink_flag
        ),
        "trigger_live": bool(plan.get("trigger_live")) if plan.get("trigger_live") is not None else plan.get("output_event_type") == "TriggerMatched",
        "current_status": plan.get("current_status") or (
            "matched" if plan.get("output_event_type") == "TriggerMatched" else "pending_market_data"
        ),
        "n5_entry_allowed": bool(plan.get("n5_entry_allowed")),
        "data_quality_status": plan.get("data_quality_status"),
    }


def requested_periods_for_condition_key(condition_key: str) -> list[str]:
    if condition_key in {"BUY_HINT", "SELL_HINT"}:
        return []
    if condition_key in {"BUY:FULL", "SELL:FULL"}:
        return ["D"]
    if ":" in condition_key:
        requested = [
            part.strip()
            for part in condition_key.split(":", 1)[1].split(",")
            if part.strip() in FORMAL_TRIGGER_PERIODS
        ]
        if requested:
            return [period for period in ("Y", "Q", "M", "W", "D") if period in set(requested)]
    return ["D"]


def raw_json_with_unified_payload(stage: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    plan_trace = dict(plan)
    plan_trace.pop("action_mark", None)
    return {
        "stage": stage,
        **build_unified_trigger_payload_fields(plan),
        "plan": plan_trace,
    }


def insert_inbox_records(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    rows: Sequence[Mapping[str, Any]],
    consumer_name: str,
) -> int:
    if not rows:
        return 0
    values = [
        (
            consumer_name,
            row["event_id"],
            row["event_type"],
            row.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION,
            row["source_layer"],
            row["source_run_id"],
            row["dedup_key"],
            row["partition_key"],
            Jsonb(to_jsonable(row.get("payload_json") or {})),
            "processed",
            1,
            Jsonb(to_jsonable(row.get("raw_json") or {})),
        )
        for row in rows
    ]
    cur.executemany(
        """
        INSERT INTO common_event_inbox (
          consumer_name, event_id, event_type, event_schema_version,
          source_layer, source_run_id, dedup_key, partition_key,
          payload_json, status, attempt_count, processed_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
        ON CONFLICT (consumer_name, event_id) DO NOTHING
        """,
        values,
    )
    return len(rows)


def execute_trigger_output_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    context_run: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    state_ids: set[int] = set()
    match_count = 0
    outbox_count = 0
    for plan in rows:
        event_time = parse_event_time(plan.get("source_event_time"))
        current_status = "matched" if plan.get("output_event_type") == "TriggerMatched" else "pending_market_data"
        if plan.get("output_event_type") == "TriggerMatched":
            try:
                assert_v4_trigger_matched_plan(plan)
            except V4EnforcementBlocked as exc:
                raise ProjectionMatcherExecuteError(
                    f"N4 projection matcher v4 enforcement blocked TriggerMatched before writes: {exc}"
                ) from exc
        state_id = upsert_trigger_state(
            cur,
            execute_run_id=execute_run_id,
            context_run=context_run,
            plan=plan,
            event_time=event_time,
            current_status=current_status,
        )
        match_id: int | None = None
        if plan.get("output_event_type") == "TriggerMatched":
            match_id = insert_trigger_match(
                cur,
                execute_run_id=execute_run_id,
                context_run=context_run,
                plan=plan,
                trigger_state_id=state_id,
                trigger_time=event_time,
            )
            update_state_last_match(cur, trigger_state_id=state_id, trigger_match_id=match_id)
        envelope = build_output_event_envelope(
            execute_run_id=execute_run_id,
            context_run=context_run,
            plan=plan,
            event_time=event_time,
            trigger_state_id=state_id,
            trigger_match_id=match_id,
        )
        insert_outbox_envelope(cur, envelope)
        state_ids.add(state_id)
        if match_id is not None:
            match_count += 1
        outbox_count += 1
    return {
        "common_trigger_state": len(state_ids),
        "common_trigger_match": match_count,
        "common_event_outbox": outbox_count,
    }


def upsert_trigger_state(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    event_time: datetime,
    current_status: str,
) -> int:
    matched = current_status == "matched"
    trigger_mark_candidate = normalize_action_mark(plan)
    projection_30m_flag, projection_30m_type = projection_metadata_for_plan(plan, trigger_mark_candidate)
    primary_trigger_period = normalize_formal_trigger_period(plan.get("primary_trigger_period"))
    all_trigger_periods = normalize_formal_periods(plan.get("all_trigger_periods"))
    trigger_period = normalize_trigger_period_for_plan(plan)
    cur.execute(
        """
        INSERT INTO common_trigger_state (
          run_id, source_condition_run_id, for_trade_date, asset_kind,
          identity_key, direction, signal_type, condition_key, trigger_period,
          trigger_bucket, current_status, last_source_event_id,
          data_quality_status, context_hash, match_count, first_matched_at,
          last_matched_at, trigger_live, trigger_mark_candidate,
          primary_trigger_period, all_trigger_periods, projection_30m_flag,
          projection_30m_type, raw_json, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (
          run_id, for_trade_date, asset_kind, identity_key, direction,
          signal_type, condition_key, trigger_period, trigger_bucket
        )
        DO UPDATE SET
          current_status = EXCLUDED.current_status,
          last_source_event_id = EXCLUDED.last_source_event_id,
          data_quality_status = EXCLUDED.data_quality_status,
          context_hash = EXCLUDED.context_hash,
          match_count = CASE
            WHEN EXCLUDED.current_status = 'matched' THEN GREATEST(common_trigger_state.match_count, 1)
            ELSE common_trigger_state.match_count
          END,
          first_matched_at = COALESCE(common_trigger_state.first_matched_at, EXCLUDED.first_matched_at),
          last_matched_at = COALESCE(EXCLUDED.last_matched_at, common_trigger_state.last_matched_at),
          trigger_live = EXCLUDED.trigger_live,
          trigger_mark_candidate = EXCLUDED.trigger_mark_candidate,
          primary_trigger_period = EXCLUDED.primary_trigger_period,
          all_trigger_periods = EXCLUDED.all_trigger_periods,
          projection_30m_flag = EXCLUDED.projection_30m_flag,
          projection_30m_type = EXCLUDED.projection_30m_type,
          raw_json = EXCLUDED.raw_json,
          updated_at = now()
        RETURNING trigger_state_id
        """,
        (
            execute_run_id,
            plan.get("source_condition_run_id") or context_run["source_condition_run_id"],
            context_run["for_trade_date"],
            plan["asset_kind"],
            plan["identity_key"],
            plan["direction"],
            plan["signal_type"],
            plan["condition_key"],
            trigger_period,
            plan["trigger_bucket"],
            current_status,
            plan["source_event_id"],
            plan["data_quality_status"],
            plan.get("context_hash"),
            1 if matched else 0,
            event_time if matched else None,
            event_time if matched else None,
            matched,
            trigger_mark_candidate,
            primary_trigger_period,
            Jsonb(to_jsonable(all_trigger_periods)),
            projection_30m_flag,
            projection_30m_type,
            Jsonb(to_jsonable(raw_json_with_unified_payload("N4_projection_matcher_execute", plan))),
        ),
    )
    return int(cur.fetchone()["trigger_state_id"])


def insert_trigger_match(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    trigger_state_id: int,
    trigger_time: datetime,
) -> int:
    trigger_mark_candidate = normalize_action_mark(plan)
    trigger_period = normalize_trigger_period_for_plan(plan)
    match_trigger_time = parse_event_time(plan.get("trigger_time") or trigger_time)
    cur.execute(
        """
        INSERT INTO common_trigger_match (
          run_id, trigger_state_id, source_event_id, source_event_type,
          source_condition_run_id, source_condition_pool_id,
          source_condition_basis_id, source_market_subscription_id,
          for_trade_date, asset_kind, identity_key, direction, signal_type,
          condition_key, trigger_price, trigger_time, trigger_period, trigger_bucket,
          data_quality_status, output_event_type, output_event_id, dedup_key,
          context_hash, trigger_mark_candidate, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (
          run_id, source_event_id, asset_kind, identity_key, direction,
          signal_type, condition_key, trigger_period, trigger_bucket
        )
        DO UPDATE SET
          trigger_state_id = EXCLUDED.trigger_state_id,
          trigger_price = EXCLUDED.trigger_price,
          trigger_time = EXCLUDED.trigger_time,
          output_event_id = EXCLUDED.output_event_id,
          dedup_key = EXCLUDED.dedup_key,
          data_quality_status = EXCLUDED.data_quality_status,
          trigger_mark_candidate = EXCLUDED.trigger_mark_candidate,
          raw_json = EXCLUDED.raw_json
        RETURNING trigger_match_id
        """,
        (
            execute_run_id,
            trigger_state_id,
            plan["source_event_id"],
            plan["source_event_type"],
            plan.get("source_condition_run_id") or context_run["source_condition_run_id"],
            plan.get("source_condition_pool_id"),
            plan.get("source_condition_basis_id"),
            plan.get("source_market_subscription_id"),
            context_run["for_trade_date"],
            plan["asset_kind"],
            plan["identity_key"],
            plan["direction"],
            plan["signal_type"],
            plan["condition_key"],
            plan.get("trigger_price"),
            match_trigger_time,
            trigger_period,
            plan["trigger_bucket"],
            plan["data_quality_status"],
            plan["output_event_type"],
            plan["output_event_id"],
            plan["output_dedup_key"],
            plan.get("context_hash"),
            trigger_mark_candidate,
            Jsonb(to_jsonable(raw_json_with_unified_payload("N4_projection_matcher_execute", plan))),
        ),
    )
    return int(cur.fetchone()["trigger_match_id"])


def update_state_last_match(cur: psycopg.Cursor[dict[str, Any]], *, trigger_state_id: int, trigger_match_id: int) -> None:
    cur.execute(
        """
        UPDATE common_trigger_state
        SET last_trigger_match_id = %s,
            updated_at = now()
        WHERE trigger_state_id = %s
        """,
        (trigger_match_id, trigger_state_id),
    )


def build_output_event_envelope(
    *,
    execute_run_id: str,
    context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    event_time: datetime,
    trigger_state_id: int,
    trigger_match_id: int | None,
) -> EventEnvelope:
    payload = build_output_event_payload(
        execute_run_id=execute_run_id,
        plan=plan,
        trigger_state_id=trigger_state_id,
        trigger_match_id=trigger_match_id,
    )
    envelope = EventEnvelope(
        event_id=str(plan["output_event_id"]),
        event_type=str(plan["output_event_type"]),
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        trade_date=str(context_run["for_trade_date"]),
        asset_kind=str(plan["asset_kind"]),
        identity_key=str(plan["identity_key"]),
        event_time=event_time,
        source_layer=N4_SOURCE_LAYER,
        source_run_id=execute_run_id,
        dedup_key=str(plan["output_dedup_key"]),
        partition_key=str(plan["identity_key"]),
        payload_json=payload,
        created_at=utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def build_output_event_payload(
    *,
    execute_run_id: str,
    plan: Mapping[str, Any],
    trigger_state_id: int,
    trigger_match_id: int | None,
) -> dict[str, Any]:
    trigger_mark_candidate = plan.get("trigger_mark_candidate") or plan.get("action_mark") or "normal"
    projection_30m_flag, projection_30m_type = projection_metadata_for_plan(plan, str(trigger_mark_candidate))
    payload = {
        "run_id": execute_run_id,
        "source_event_id": plan["source_event_id"],
        "source_event_type": plan["source_event_type"],
        "source_snapshot_run_id": plan.get("source_snapshot_run_id"),
        "projection_run_id": plan.get("projection_run_id"),
        "trigger_context_run_id": plan.get("trigger_context_run_id"),
        "context_snapshot_id": plan.get("context_snapshot_id"),
        "trigger_state_id": trigger_state_id,
        "trigger_match_id": trigger_match_id,
        "identity_key": plan["identity_key"],
        "asset_kind": plan["asset_kind"],
        "direction": plan["direction"],
        "condition_key": plan["condition_key"],
        "original_condition_key": plan.get("original_condition_key") or plan.get("condition_key"),
        "signal_type": plan["signal_type"],
        "trigger_price": plan.get("trigger_price"),
        "trigger_time": plan.get("trigger_time") or plan.get("source_event_time"),
        "trigger_kind": plan.get("trigger_kind"),
        "trigger_live": bool(plan.get("trigger_live")) if plan.get("trigger_live") is not None else plan.get("output_event_type") == "TriggerMatched",
        "current_status": plan.get("current_status") or (
            "matched" if plan.get("output_event_type") == "TriggerMatched" else "pending_market_data"
        ),
        "n5_entry_allowed": bool(plan.get("n5_entry_allowed")),
        "triggered_periods": normalize_formal_periods(plan.get("triggered_periods")),
        "all_trigger_periods": normalize_formal_periods(plan.get("all_trigger_periods")),
        "primary_trigger_period": normalize_formal_trigger_period(plan.get("primary_trigger_period")),
        "projection_period": plan.get("projection_period") or ("30m" if projection_30m_flag else None),
        "projection_30m_flag": projection_30m_flag,
        "projection_30m_type": projection_30m_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "legacy_signal_type": plan.get("legacy_signal_type"),
        "match_basis": plan.get("match_basis"),
        "trigger_period": normalize_trigger_period_for_plan(plan),
        "trigger_bucket": plan["trigger_bucket"],
        "data_quality_status": plan["data_quality_status"],
        "projection_signal_status": plan.get("projection_signal_status"),
        "projection_status": plan.get("projection_status"),
        "projection_quality_status": plan.get("projection_quality_status"),
        "trace_status": plan.get("trace_status"),
        "projection_trace": plan.get("projection_trace") or {},
        "period_trigger_baseline_trace": plan.get("period_trigger_baseline_trace") or {},
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "source_condition_pool_id": plan.get("source_condition_pool_id"),
        "source_condition_basis_id": plan.get("source_condition_basis_id"),
        "source_minute_target_scope_id": plan.get("source_minute_target_scope_id"),
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "context_hash": plan.get("context_hash"),
        "n4_boundary": {
            "market_data_pulled": False,
            "raw_projection_computed_by_n4": False,
            "downstream_layers_touched": False,
        },
    }
    payload.update(build_unified_trigger_payload_fields(plan))
    payload.pop("action_mark", None)
    return payload


def insert_outbox_envelope(cur: psycopg.Cursor[dict[str, Any]], envelope: EventEnvelope) -> str:
    record = envelope.as_record()
    columns = ", ".join(OUTBOX_COLUMNS)
    placeholders = ", ".join(["%s"] * len(OUTBOX_COLUMNS))
    values = [Jsonb(to_jsonable(record[column])) if column == "payload_json" else record[column] for column in OUTBOX_COLUMNS]
    cur.execute(
        f"""
        INSERT INTO common_event_outbox ({columns})
        VALUES ({placeholders})
        ON CONFLICT (event_id) DO UPDATE SET
          payload_json = EXCLUDED.payload_json,
          event_time = EXCLUDED.event_time,
          partition_key = EXCLUDED.partition_key,
          updated_at = now()
        RETURNING event_id
        """,
        values,
    )
    return str(cur.fetchone()["event_id"])


def upsert_checkpoints(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    rows: Sequence[Mapping[str, Any]],
    consumer_name: str,
) -> int:
    writable = [row for row in rows if row.get("would_insert_or_update_common_event_consumer_checkpoint")]
    if not writable:
        return 0
    values = [
        (
            consumer_name,
            row["partition_key"],
            SOURCE_LAYER,
            row["last_event_id"],
            parse_event_time(row.get("last_event_time")),
            row["last_outbox_id"],
            Jsonb(to_jsonable({**(row.get("checkpoint_payload") or {}), "execute_run_id": row.get("execute_run_id")})),
        )
        for row in writable
    ]
    cur.executemany(
        """
        INSERT INTO common_event_consumer_checkpoint (
          consumer_name, partition_key, source_layer, last_event_id,
          last_event_time, last_outbox_id, checkpoint_payload, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (consumer_name, partition_key, source_layer)
        DO UPDATE SET
          last_event_id = EXCLUDED.last_event_id,
          last_event_time = EXCLUDED.last_event_time,
          last_outbox_id = EXCLUDED.last_outbox_id,
          checkpoint_payload = EXCLUDED.checkpoint_payload,
          updated_at = now()
        WHERE common_event_consumer_checkpoint.last_outbox_id IS NULL
           OR EXCLUDED.last_outbox_id > common_event_consumer_checkpoint.last_outbox_id
        """,
        values,
    )
    return len(writable)


def update_execute_trigger_run_finished(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    p0_count: int,
    p1_count: int,
    p2_count: int,
    trigger_state_count: int,
    trigger_match_count: int,
    outbox_count: int,
) -> None:
    cur.execute(
        """
        UPDATE common_trigger_run
        SET status = %s,
            p0_count = %s,
            p1_count = %s,
            p2_count = %s,
            trigger_state_row_count = %s,
            trigger_match_row_count = %s,
            trigger_event_outbox_count = %s,
            finished_at = now(),
            updated_at = now()
        WHERE run_id = %s
        """,
        (
            "passed" if p0_count == 0 else "blocked",
            p0_count,
            p1_count,
            p2_count,
            trigger_state_count,
            trigger_match_count,
            outbox_count,
            execute_run_id,
        ),
    )


def parse_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "")
    if text:
        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def write_json(path: str, data: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_preflight_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    summary = report["execute_plan_summary"]
    return "\n".join(
        [
            "# N4 Projection Matcher Execute Preflight Report",
            "",
            "## Summary",
            "",
            f"- result: {report['result']}",
            f"- layer_role: {report['layer_role']}",
            f"- execute_run_id: {report['execute_run_id']}",
            f"- trigger_context_run_id: {report['trigger_context_run_id']}",
            f"- projection_run_id: {report['projection_run_id']}",
            f"- snapshot_run_id: {report['snapshot_run_id']}",
            f"- accepted_source_event_count: {summary['accepted_source_event_count']}",
            f"- matched_output_count: {summary['matched_output_count']}",
            f"- pending_output_count: {summary['pending_output_count']}",
            f"- inbox_write_plan_count: {summary['inbox_write_plan_count']}",
            f"- checkpoint_write_plan_count: {summary['checkpoint_write_plan_count']}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            "",
            "## Boundary",
            "",
            "- preflight writes_performed=false",
            "- execute requires --execute and --user-confirmed",
            "- N3 outbox status update is not planned",
            "- N5/N6/action/user/voice/sim/real trade are forbidden",
            "",
            "## Rollback",
            "",
            f"- rollback_sql_path: {report['rollback_sql_path']}",
        ]
    ) + "\n"
