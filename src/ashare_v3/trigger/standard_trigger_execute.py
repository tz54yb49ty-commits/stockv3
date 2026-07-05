"""N4 20260528 canonical standard trigger execute contract/preflight.

The preflight path is read-only: it refreshes execute contract artifacts from
the canonical local trigger dry-run report and checks target-run baselines.
The execute entrypoint is guarded by explicit flags and is not used by the
artifact refresh task.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.events.ids import build_n4_trigger_state_changed_dedup_key, build_stable_event_id, join_dedup_parts
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    EventEnvelope,
    N4_SOURCE_LAYER,
    utc_now,
    validate_event_envelope,
)
from ashare_v3.events.outbox import OUTBOX_COLUMNS
from ashare_v3.trigger.canonical_signal import CANONICAL_SIGNAL_TYPES, CANONICAL_TRIGGER_MARK_CANDIDATES
from ashare_v3.trigger.local_trigger_dry_run import (
    build_local_trigger_plans,
    build_trigger_state_change_plans,
    fetch_context_rows,
    fetch_snapshot_rows,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect, audited_n4_trigger_connect
from ashare_v3.trigger.synthetic_dry_run import write_json, write_text


DEFAULT_20260528_EXECUTE_RUN_ID = "trigger_execute_20260528_condition_layer_20260527_source_20260527_v2"
DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID = "trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v2"
DEFAULT_20260528_SNAPSHOT_RUN_ID = (
    "realtime_snapshot_20260528_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2"
)
DEFAULT_20260528_MARKET_SUBSCRIPTION_RUN_ID = "market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2"
DEFAULT_20260528_SOURCE_CONDITION_RUN_ID = "condition_layer_20260527_source_20260527_v2"
DEFAULT_20260528_DRY_RUN_JSON_PATH = "docs/N4_20260528_V2_canonical_local_trigger_dry_run_report.json"
DEFAULT_20260528_CONTRACT_JSON_PATH = "docs/N4_20260528_V2_canonical_trigger_execute_contract.json"
DEFAULT_20260528_CONTRACT_MD_PATH = "docs/N4_20260528_V2_CANONICAL_TRIGGER_EXECUTE_CONTRACT.md"
DEFAULT_20260528_PREFLIGHT_JSON_PATH = "docs/N4_20260528_V2_canonical_trigger_execute_preflight.json"
DEFAULT_20260528_PREFLIGHT_MD_PATH = "docs/N4_20260528_V2_CANONICAL_TRIGGER_EXECUTE_PREFLIGHT.md"
DEFAULT_20260528_ROLLBACK_SQL_PATH = "sql/N4_20260528_V2_canonical_trigger_execute_rollback.sql"

SOURCE_EVENT_TYPE = "MarketSnapshotUpdated"
ALLOWED_EVENT_TYPES = ("TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged")
STATE_CHANGE_EVENT_TYPE = "TriggerStateChanged"
DEPRECATED_RUNTIME_SIGNAL_TYPES = ("B_BUY_30M_VOL", "S_SELL_30M_SHRINK", "BUY_HINT", "SELL_HINT")
ALLOWED_WRITE_TABLES_AFTER_FINAL_CONFIRMATION = (
    "common_trigger_run",
    "common_trigger_quality_item",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
)
FORBIDDEN_WRITE_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "N2 condition tables",
    "N3 snapshot/projection/minute/subscription facts",
    "N5/N6/action/user/voice/mobile/sim/position/real-trade tables",
    "worker state",
)
SCHEMA_DATA_QUALITY_STATUS = {
    "passed": "passed",
    "partial": "partial",
    "missing": "missing",
    "delayed": "delayed",
    "failed": "failed",
    "not_ready": "missing",
    "pending": "missing",
    "blocked": "failed",
    "warning": "partial",
}


class StandardTriggerExecuteError(RuntimeError):
    """Raised when the standard trigger execute gate is blocked."""


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_safe(value: Any) -> Any:
    """Convert DB/Decimal/datetime values in trace payloads to JSON-safe data."""

    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def jsonb(value: Any) -> Jsonb:
    return Jsonb(json_safe(value))


def build_execute_contract_from_dry_run(
    dry_run_report: Mapping[str, Any],
    *,
    execute_run_id: str = DEFAULT_20260528_EXECUTE_RUN_ID,
    trigger_context_run_id: str | None = None,
    snapshot_run_id: str | None = None,
    market_subscription_run_id: str | None = None,
    dry_run_json_path: str | None = None,
    rollback_sql_path: str = DEFAULT_20260528_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    summary = dict(dry_run_report.get("summary") or {})
    trigger_context_run_id = trigger_context_run_id or str(
        dry_run_report.get("trigger_context_run_id") or DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID
    )
    snapshot_run_id = snapshot_run_id or str(dry_run_report.get("snapshot_run_id") or DEFAULT_20260528_SNAPSHOT_RUN_ID)
    market_subscription_run_id = (
        market_subscription_run_id
        if market_subscription_run_id is not None
        else str(dry_run_report.get("market_subscription_run_id") or "")
    )
    dry_run_json_path = dry_run_json_path or str(dry_run_report.get("json_report_path") or "")
    for_trade_date = str(dry_run_report.get("for_trade_date") or "")
    deprecated_signal_violations = deprecated_runtime_signal_type_paths(dry_run_report)
    sample_trace_missing_count = sample_original_condition_key_missing_count(dry_run_report)
    dry_run_quality = dict(dry_run_report.get("quality") or {})
    p0_count = int(dry_run_quality.get("p0_count") or 0)
    state_change_plan_count = int(
        summary.get("state_change_plan_count")
        or (summary.get("planned_output_event_types") or {}).get(STATE_CHANGE_EVENT_TYPE)
        or 0
    )
    outcome_count = int(summary.get("candidate_count") or dry_run_report.get("candidate_count") or 0)
    schema_compatibility_blocks_execute = False
    contract_pass = (
        dry_run_report.get("result") == "DRY_RUN_PASS"
        and p0_count == 0
        and not deprecated_signal_violations
        and sample_trace_missing_count == 0
        and state_change_plan_count > 0
        and not schema_compatibility_blocks_execute
    )
    return {
        "stage": f"N4-{for_trade_date or 'unknown'}-v2-standard-trigger-execute-contract",
        "result": "CONTRACT_PASS" if contract_pass else "CONTRACT_BLOCKED",
        "layer_role": "N4_trigger",
        "event_schema_version": "v2-canonical-trigger-action-runtime",
        "execution_mode": "fact_only_b1_snapshot_local_context_standard_trigger_execute",
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "snapshot_run_id": snapshot_run_id,
        "source_condition_run_id": str(dry_run_report.get("source_condition_run_id") or ""),
        "market_subscription_run_id": market_subscription_run_id,
        "source_market_data_run_id": str(dry_run_report.get("source_market_data_run_id") or snapshot_run_id),
        "for_trade_date": for_trade_date,
        "input_semantics": {
            "consumes_n3_outbox": False,
            "reads_b1_snapshot_facts": True,
            "reads_local_n4_context": True,
            "writes_inbox": False,
            "writes_checkpoint": False,
            "pulls_market_data": False,
        },
        "allowed_write_tables_after_final_confirmation": list(ALLOWED_WRITE_TABLES_AFTER_FINAL_CONFIRMATION),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "requires_execute_flag": True,
        "requires_user_confirmed_flag": True,
        "expected_writes": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": "execute_quality_rows_only",
            "common_trigger_state": outcome_count,
            "common_trigger_match": outcome_count,
            "common_event_outbox": outcome_count + state_change_plan_count,
            "TriggerMatched": int(summary.get("matched_plan_count") or dry_run_report.get("matched_plan_count") or 0),
            "TriggerPendingMarketData": int(summary.get("pending_plan_count") or dry_run_report.get("pending_plan_count") or 0),
            "TriggerStateChanged": state_change_plan_count,
        },
        "matched_by_signal_type": dict(summary.get("matched_by_signal_type") or {}),
        "pending_by_signal_type": dict(summary.get("pending_by_signal_type") or {}),
        "matched_by_trigger_mark_candidate": dict(summary.get("matched_by_trigger_mark_candidate") or {}),
        "pending_by_trigger_mark_candidate": dict(summary.get("pending_by_trigger_mark_candidate") or {}),
        "pending_by_legacy_condition_signal_type": dict(summary.get("pending_by_legacy_signal_type") or {}),
        "canonical_payload_contract": {
            "signal_type": list(CANONICAL_SIGNAL_TYPES),
            "trigger_mark_candidate": list(CANONICAL_TRIGGER_MARK_CANDIDATES),
            "required_runtime_fields": [
                "signal_type",
                "trigger_mark_candidate",
                "projection_30m_flag",
                "projection_30m_type",
            ],
            "required_trace_fields": ["condition_key", "original_condition_key", "legacy_signal_type"],
            "deprecated_signal_type_values_rejected_for_new_payloads": list(DEPRECATED_RUNTIME_SIGNAL_TYPES),
            "deprecated_signal_type_values_allowed_only_in_trace_fields": [
                "condition_key",
                "original_condition_key",
                "legacy_signal_type",
                "pending_by_legacy_condition_signal_type",
            ],
            "trigger_state_changed": {
                "writes_common_trigger_match": False,
                "required_fields": [
                    "trigger_live",
                    "previous_trigger_live",
                    "current_status",
                    "previous_status",
                    "primary_trigger_period",
                    "previous_primary_trigger_period",
                    "all_trigger_periods",
                    "previous_all_trigger_periods",
                    "state_change_reason",
                ],
            },
        },
        "signal_semantics": {
            "B_BUY+normal": "TriggerMatched allowed from passed B1 snapshot facts plus local context",
            "S_SELL+normal": "TriggerMatched allowed from passed B1 snapshot facts plus local context",
            "B_BUY+30m_volume": "TriggerPendingMarketData until N3 projection or closed confirmation exists; trace preserves B_BUY_30M_VOL as original_condition_key",
            "S_SELL+30m_shrink": "TriggerPendingMarketData until N3 projection or closed confirmation exists; trace preserves S_SELL_30M_SHRINK as original_condition_key",
            "BUY_HINT condition": "Trace-only condition_key mapped to signal_type=B_BUY and held pending until projection confirmation exists",
            "SELL_HINT condition": "Trace-only condition_key mapped to signal_type=S_SELL and held pending until projection confirmation exists",
        },
        "schema_compatibility": {
            "execute_blocked_until_schema_review": schema_compatibility_blocks_execute,
            "reason": "024 canonical trigger state compatibility migration passed; HINT condition_key can map to B_BUY/S_SELL while legacy rows remain compatible",
            "common_trigger_match_records_trigger_state_changed": False,
            "common_event_outbox_supports_trigger_state_changed": True,
            "common_trigger_state_canonical_columns_ready": True,
            "common_trigger_match_trigger_mark_candidate_ready": True,
        },
        "idempotency_gate": {
            "block_if_execute_run_exists": True,
            "block_if_outbox_exists": True,
            "block_if_trigger_match_or_state_exists": True,
            "block_if_inbox_or_checkpoint_refs_exist": True,
            "stable_event_id_required": True,
            "stable_dedup_key_required": True,
        },
        "rollback": {
            "rollback_sql_path": rollback_sql_path,
            "delete_scope": "execute_run_id only",
            "delete_tables": [
                "common_event_outbox",
                "common_trigger_match",
                "common_trigger_state",
                "common_trigger_quality_item",
                "common_trigger_run",
            ],
            "block_if_n5_consumed": True,
            "block_if_outbox_delivering_or_delivered": True,
            "does_not_touch_context_or_n3_or_n2_or_n5": True,
        },
        "runner_readiness": {
            "ready": True,
            "runner": "scripts/run_20260528_trigger_v2_execute_once.py",
            "preflight_runner_ready": True,
            "execute_runner_guarded_by_double_confirmation": True,
            "execute_final_gate_requires_user_confirmation": True,
            "execute_blocked_until_schema_compatibility_review": False,
            "supports_trigger_state_changed_outbox": True,
            "supports_024_state_columns": True,
            "supports_match_trigger_mark_candidate": True,
            "dry_run_alignment_source": dry_run_json_path,
        },
        "contract_checks": {
            "dry_run_result": dry_run_report.get("result"),
            "dry_run_p0_count": p0_count,
            "deprecated_runtime_signal_type_path_count": len(deprecated_signal_violations),
            "sample_original_condition_key_missing_count": sample_trace_missing_count,
            "canonical_payload_invalid_count": int(summary.get("canonical_payload_invalid_count") or 0),
        },
    }


def build_execute_preflight(
    *,
    dry_run_report: Mapping[str, Any],
    contract: Mapping[str, Any],
    baseline_summary: Mapping[str, int],
    dry_run_json_path: str = DEFAULT_20260528_DRY_RUN_JSON_PATH,
    rollback_sql_path: str = DEFAULT_20260528_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    quality_items = build_preflight_quality_items(
        dry_run_report=dry_run_report,
        contract=contract,
        baseline_summary=baseline_summary,
        rollback_sql_path=rollback_sql_path,
    )
    severity_counts = count_quality_severities(quality_items)
    blockers = [
        {
            "severity": item["severity"],
            "code": item["gate_code"],
            "message": item["gate_name"],
            "actual": item.get("actual_value"),
        }
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    dry_run_quality = dict(dry_run_report.get("quality") or {})
    dry_run_p1_gate_codes = dry_run_quality_gate_codes(dry_run_quality, severity="P1")
    expected_writes = dict(contract.get("expected_writes") or {})
    return {
        "stage": f"N4-{contract.get('for_trade_date') or 'unknown'}-v2-standard-trigger-execute-preflight",
        "result": "PREFLIGHT_PASS" if severity_counts["P0"] == 0 else "PREFLIGHT_BLOCKED",
        "layer_role": "N4_trigger",
        "event_schema_version": contract.get("event_schema_version"),
        "execute_run_id": contract.get("execute_run_id"),
        "trigger_context_run_id": contract.get("trigger_context_run_id"),
        "snapshot_run_id": contract.get("snapshot_run_id"),
        "source_condition_run_id": contract.get("source_condition_run_id"),
        "market_subscription_run_id": contract.get("market_subscription_run_id"),
        "for_trade_date": contract.get("for_trade_date"),
        "blockers": blockers,
        "dry_run_basis": {
            "report_path": dry_run_json_path,
            "result": dry_run_report.get("result"),
            "context_candidate_count": int(dry_run_report.get("context_candidate_count") or 0),
            "candidate_count": int(dry_run_report.get("candidate_count") or 0),
            "matched_plan_count": int(dry_run_report.get("matched_plan_count") or 0),
            "pending_plan_count": int(dry_run_report.get("pending_plan_count") or 0),
            "p0_count": int(dry_run_quality.get("p0_count") or 0),
            "p1_count": int(dry_run_quality.get("p1_count") or 0),
            "p2_count": int(dry_run_quality.get("p2_count") or 0),
            "p1_gate_codes": dry_run_p1_gate_codes,
        },
        "expected_future_writes": expected_writes,
        "matched_by_signal_type": dict(contract.get("matched_by_signal_type") or {}),
        "pending_by_signal_type": dict(contract.get("pending_by_signal_type") or {}),
        "matched_by_trigger_mark_candidate": dict(contract.get("matched_by_trigger_mark_candidate") or {}),
        "pending_by_trigger_mark_candidate": dict(contract.get("pending_by_trigger_mark_candidate") or {}),
        "pending_by_legacy_condition_signal_type": dict(contract.get("pending_by_legacy_condition_signal_type") or {}),
        "canonical_payload_contract": dict(contract.get("canonical_payload_contract") or {}),
        "baseline_summary": dict(baseline_summary),
        "upstream_input_refs": {
            "snapshot_run_outbox_allowed": int(baseline_summary.get("snapshot_run_outbox_allowed") or 0),
            "snapshot_run_outbox_disallowed": int(baseline_summary.get("snapshot_run_outbox_disallowed") or 0),
            "snapshot_run_inbox": int(baseline_summary.get("snapshot_run_inbox") or 0),
            "snapshot_run_checkpoint_refs": int(baseline_summary.get("snapshot_run_checkpoint_refs") or 0),
        },
        "target_output_baseline": {
            key: int(baseline_summary.get(key) or 0)
            for key in (
                "execute_run_common_trigger_run",
                "execute_run_quality",
                "execute_run_match",
                "execute_run_state",
                "execute_run_outbox",
                "execute_run_inbox",
                "execute_run_checkpoint_refs",
                "execute_run_outbox_delivered_or_delivering",
                "downstream_inbox_for_execute_run",
                "downstream_checkpoint_refs",
                "n5_action_run_refs",
            )
        },
        "idempotency_gate": {
            "clean_target_execute_run": target_baseline_is_clean(baseline_summary),
            "block_if_execute_run_exists": True,
            "block_if_outbox_exists": True,
            "block_if_trigger_match_or_state_exists": True,
            "block_if_inbox_or_checkpoint_refs_exist": True,
        },
        "rollback_safety": {
            "rollback_sql_path": rollback_sql_path,
            "rollback_safe_before_execute": target_baseline_is_clean(baseline_summary)
            and int(baseline_summary.get("execute_run_outbox_delivered_or_delivering") or 0) == 0,
            "rollback_safe_after_future_execute_only_if_unconsumed": True,
            "blocks_after_n5_consumption": True,
            "blocks_if_outbox_delivering_or_delivered": True,
            "does_not_touch_context_snapshot": True,
            "does_not_touch_n3_facts": True,
        },
        "side_effects": {
            "execute_performed": False,
            "writes_performed": False,
            "event_outbox_written": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "trigger_match_written": False,
            "trigger_state_written": False,
            "n5_n6_touched": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trade_touched": False,
        },
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "p1_gate_codes": [item["gate_code"] for item in quality_items if item["severity"] == "P1"],
        },
        "quality_items": quality_items,
        "runner_readiness": contract.get("runner_readiness"),
        "next_gate": {
            "allow_enter_n4_v2_execute_final_gate": severity_counts["P0"] == 0,
            "allow_enter_standard_trigger_execute_final_gate": severity_counts["P0"] == 0,
            "execute_authorized": False,
            "n5_remains_blocked": True,
            "required_before_final_gate": [
                "Explicit user confirmation for N4 v2 execute final gate",
                "Run scripts/run_20260528_trigger_v2_execute_once.py with --execute --user-confirmed",
                "Recheck target execute_run_id baseline remains zero immediately before execute",
                "Keep N5/N6 workers stopped and downstream consumption blocked",
            ],
        },
    }


def build_preflight_quality_items(
    *,
    dry_run_report: Mapping[str, Any],
    contract: Mapping[str, Any],
    baseline_summary: Mapping[str, int],
    rollback_sql_path: str,
) -> list[dict[str, Any]]:
    dry_run_quality = dict(dry_run_report.get("quality") or {})
    dry_run_summary = dict(dry_run_report.get("summary") or {})
    deprecated_signal_paths = deprecated_runtime_signal_type_paths(dry_run_report)
    sample_trace_missing_count = sample_original_condition_key_missing_count(dry_run_report)
    target_clean = target_baseline_is_clean(baseline_summary)
    upstream_input_compatible = (
        int(baseline_summary.get("snapshot_run_outbox_disallowed") or 0) == 0
        and int(baseline_summary.get("snapshot_run_inbox") or 0) == 0
        and int(baseline_summary.get("snapshot_run_checkpoint_refs") or 0) == 0
    )
    rollback_exists = Path(rollback_sql_path).exists()
    return [
        quality_item(
            "P0",
            "passed" if dry_run_report.get("result") == "DRY_RUN_PASS" else "failed",
            "n4_v2_execute_dry_run_passed",
            "N4 v2 execute preflight must be based on a passed canonical local dry-run",
            expected="DRY_RUN_PASS",
            actual=str(dry_run_report.get("result")),
        ),
        quality_item(
            "P0",
            "passed" if int(dry_run_quality.get("p0_count") or 0) == 0 else "failed",
            "n4_v2_execute_dry_run_p0_zero",
            "N4 v2 execute preflight requires dry-run P0=0",
            expected="0",
            actual=str(dry_run_quality.get("p0_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if contract.get("result") == "CONTRACT_PASS" else "failed",
            "n4_v2_execute_contract_passed",
            "N4 v2 execute contract must pass canonical alignment",
            expected="CONTRACT_PASS",
            actual=str(contract.get("result")),
        ),
        quality_item(
            "P0",
            "failed" if (contract.get("schema_compatibility") or {}).get("execute_blocked_until_schema_review") else "passed",
            "n4_v2_schema_compatibility_review_required",
            "N4 v2 execute remains blocked until trigger_state/match schema compatibility is reviewed",
            expected="schema compatibility reviewed",
            actual=json.dumps(contract.get("schema_compatibility") or {}, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if not deprecated_signal_paths else "failed",
            "n4_v2_deprecated_runtime_signal_type",
            "Canonical payload runtime signal_type must not contain deprecated 30m values",
            expected="no B_BUY_30M_VOL/S_SELL_30M_SHRINK in runtime signal_type fields",
            actual=json.dumps(deprecated_signal_paths[:10], ensure_ascii=False),
        ),
        quality_item(
            "P0",
            "passed" if sample_trace_missing_count == 0 else "failed",
            "n4_v2_original_condition_key_trace_present",
            "Canonical payload samples must preserve original_condition_key for trace/audit",
            expected="0 missing traces",
            actual=str(sample_trace_missing_count),
        ),
        quality_item(
            "P0",
            "passed" if int(dry_run_summary.get("canonical_payload_invalid_count") or 0) == 0 else "failed",
            "n4_v2_canonical_payload_invalid_count_zero",
            "Dry-run canonical payload invalid count must remain zero",
            expected="0",
            actual=str(dry_run_summary.get("canonical_payload_invalid_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if target_clean else "failed",
            "n4_v2_execute_target_baseline_zero",
            "Target execute_run_id must have no existing run/fact/outbox/inbox/checkpoint refs",
            expected="all target scoped refs=0",
            actual=json.dumps(baseline_summary, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if upstream_input_compatible else "failed",
            "n4_v2_execute_upstream_input_refs_compatible",
            "Allowlisted N3 MarketSnapshotUpdated pending outbox may exist, but upstream input must not be consumed/acked or contain non-allowlisted events",
            expected="snapshot_run_outbox_disallowed/snapshot_run_inbox/snapshot_run_checkpoint_refs=0",
            actual=json.dumps(
                {
                    "snapshot_run_outbox_allowed": int(baseline_summary.get("snapshot_run_outbox_allowed") or 0),
                    "snapshot_run_outbox_disallowed": int(baseline_summary.get("snapshot_run_outbox_disallowed") or 0),
                    "snapshot_run_inbox": int(baseline_summary.get("snapshot_run_inbox") or 0),
                    "snapshot_run_checkpoint_refs": int(baseline_summary.get("snapshot_run_checkpoint_refs") or 0),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        quality_item(
            "P0",
            "passed" if int(baseline_summary.get("execute_run_outbox_delivered_or_delivering") or 0) == 0 else "failed",
            "n4_v2_execute_outbox_not_delivered",
            "Rollback must be safe before execute; no delivered/delivering N4 outbox may exist",
            expected="0",
            actual=str(baseline_summary.get("execute_run_outbox_delivered_or_delivering") or 0),
        ),
        quality_item(
            "P0",
            "passed" if rollback_exists else "failed",
            "n4_v2_execute_rollback_sql_exists",
            "N4 v2 execute rollback SQL must exist before final gate",
            expected=rollback_sql_path,
            actual="exists" if rollback_exists else "missing",
        ),
        quality_item(
            "P0",
            "passed" if bool((contract.get("runner_readiness") or {}).get("ready")) else "failed",
            "n4_v2_execute_runner_ready",
            "N4 v2 execute runner must be present and guarded by double confirmation",
            expected="ready=true",
            actual=json.dumps(contract.get("runner_readiness") or {}, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P1",
            "warning" if int(dry_run_quality.get("p1_count") or 0) > 0 else "passed",
            "n4_v2_execute_dry_run_p1_carried",
            "N4 v2 execute preflight carries dry-run P1 warnings without blocking final gate",
            expected="visible",
            actual=str(dry_run_quality.get("p1_count") or 0),
        ),
        quality_item("P0", "passed", "n4_v2_execute_no_db_write_in_preflight", "Preflight refresh does not write database rows"),
        quality_item("P0", "passed", "n4_v2_execute_no_inbox_checkpoint", "Preflight refresh does not write inbox/checkpoint"),
        quality_item("P0", "passed", "n4_v2_execute_no_n5_n6", "N5/N6 remain blocked and untouched"),
        quality_item("P0", "passed", "n4_v2_execute_no_worker", "No worker or long-running service is started"),
    ]


def build_standard_trigger_execute_rollback_sql(execute_run_id: str) -> str:
    return f"""-- N4 canonical trigger execute rollback.
-- Scope: execute_run_id={execute_run_id}
-- Use only before downstream N5/N6 consumption. Does not touch N2/N3 facts or context snapshots.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := '{execute_run_id}';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: outbox delivered/delivering refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: downstream checkpoint refs = %', v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: N5 action run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: N5 action event refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_projection_run
      WHERE user_projection_run_id = $1
         OR source_action_run_id = $1
         OR source_n5_outbox_range::TEXT LIKE '%' || $1 || '%'
         OR quality_summary_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: N6 user_projection_run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_projection
      WHERE user_projection_run_id = $1
         OR source_action_run_id = $1
         OR source_event_id = $1
         OR source_payload_json::TEXT LIKE '%' || $1 || '%'
         OR display_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: N6 user_signal_projection refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_card
      WHERE user_projection_run_id = $1
         OR source_action_run_id = $1
         OR source_event_id = $1
         OR card_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: N6 user_signal_card refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_notification_queue
      WHERE user_projection_run_id = $1
         OR source_action_run_id = $1
         OR source_event_id = $1
         OR notification_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 canonical trigger execute rollback blocked: N6 user_notification_queue refs = %', v_count;
    END IF;
  END IF;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = '{execute_run_id}';

DELETE FROM common_trigger_match
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_state
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_quality_item
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_run
WHERE run_id = '{execute_run_id}';

COMMIT;
"""


def capture_execute_baseline(
    *,
    dsn: str,
    execute_run_id: str = DEFAULT_20260528_EXECUTE_RUN_ID,
    trigger_context_run_id: str = DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID,
    snapshot_run_id: str = DEFAULT_20260528_SNAPSHOT_RUN_ID,
) -> dict[str, int]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_standard_capture_execute_baseline",
        source_run_id=execute_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        baseline = {
            "execute_run_common_trigger_run": query_count(cur, "common_trigger_run", "run_id = %s", (execute_run_id,)),
            "execute_run_quality": query_count(cur, "common_trigger_quality_item", "run_id = %s", (execute_run_id,)),
            "execute_run_match": query_count(cur, "common_trigger_match", "run_id = %s", (execute_run_id,)),
            "execute_run_state": query_count(cur, "common_trigger_state", "run_id = %s", (execute_run_id,)),
            "execute_run_outbox": query_count(
                cur,
                "common_event_outbox",
                "source_layer = 'N4_trigger' AND source_run_id = %s",
                (execute_run_id,),
            ),
            "execute_run_inbox": query_count(cur, "common_event_inbox", "source_run_id = %s", (execute_run_id,)),
            "execute_run_checkpoint_refs": query_count(
                cur,
                "common_event_consumer_checkpoint",
                "source_layer = 'N4_trigger' AND checkpoint_payload::text LIKE %s",
                (f"%{execute_run_id}%",),
            ),
            "context_run_outbox": query_count(
                cur,
                "common_event_outbox",
                "source_layer = 'N4_trigger' AND source_run_id = %s",
                (trigger_context_run_id,),
            ),
            "context_run_match": query_count(cur, "common_trigger_match", "run_id = %s", (trigger_context_run_id,)),
            "context_run_state": query_count(cur, "common_trigger_state", "run_id = %s", (trigger_context_run_id,)),
            "snapshot_run_outbox": query_count(
                cur,
                "common_event_outbox",
                "source_layer = 'N3_market_data' AND source_run_id = %s",
                (snapshot_run_id,),
            ),
            "snapshot_run_outbox_allowed": query_count(
                cur,
                "common_event_outbox",
                "source_layer = 'N3_market_data' AND source_run_id = %s AND event_type = %s AND status = 'pending'",
                (snapshot_run_id, SOURCE_EVENT_TYPE),
            ),
            "snapshot_run_outbox_disallowed": query_count(
                cur,
                "common_event_outbox",
                """
                source_run_id = %s
                AND NOT (
                  source_layer = 'N3_market_data'
                  AND event_type = %s
                  AND status = 'pending'
                )
                """,
                (snapshot_run_id, SOURCE_EVENT_TYPE),
            ),
            "snapshot_run_inbox": query_count(cur, "common_event_inbox", "source_run_id = %s", (snapshot_run_id,)),
            "snapshot_run_checkpoint_refs": query_count(
                cur,
                "common_event_consumer_checkpoint",
                "source_layer = 'N3_market_data' AND checkpoint_payload::text LIKE %s",
                (f"%{snapshot_run_id}%",),
            ),
            "execute_run_outbox_delivered_or_delivering": query_count(
                cur,
                "common_event_outbox",
                "source_layer = 'N4_trigger' AND source_run_id = %s AND status IN ('delivering', 'delivered')",
                (execute_run_id,),
            ),
            "downstream_inbox_for_execute_run": query_count(
                cur,
                "common_event_inbox",
                "source_layer = 'N4_trigger' AND source_run_id = %s",
                (execute_run_id,),
            ),
            "downstream_checkpoint_refs": query_count(
                cur,
                "common_event_consumer_checkpoint",
                "source_layer = 'N4_trigger' AND checkpoint_payload::text LIKE %s",
                (f"%{execute_run_id}%",),
            ),
        }
        if table_exists(cur, "common_action_run"):
            baseline["n5_action_run_refs"] = query_count(
                cur,
                "common_action_run",
                "source_trigger_run_id = %s",
                (execute_run_id,),
            )
        else:
            baseline["n5_action_run_refs"] = 0
        return baseline


def run_standard_trigger_execute_preflight(
    *,
    dsn: str,
    execute_run_id: str = DEFAULT_20260528_EXECUTE_RUN_ID,
    trigger_context_run_id: str = DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID,
    snapshot_run_id: str = DEFAULT_20260528_SNAPSHOT_RUN_ID,
    market_subscription_run_id: str | None = None,
    dry_run_json_path: str = DEFAULT_20260528_DRY_RUN_JSON_PATH,
    contract_json_path: str = DEFAULT_20260528_CONTRACT_JSON_PATH,
    contract_markdown_path: str = DEFAULT_20260528_CONTRACT_MD_PATH,
    preflight_json_path: str = DEFAULT_20260528_PREFLIGHT_JSON_PATH,
    preflight_markdown_path: str = DEFAULT_20260528_PREFLIGHT_MD_PATH,
    rollback_sql_path: str = DEFAULT_20260528_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    dry_run_report = load_json(dry_run_json_path)
    write_text(rollback_sql_path, build_standard_trigger_execute_rollback_sql(execute_run_id))
    contract = build_execute_contract_from_dry_run(
        dry_run_report,
        execute_run_id=execute_run_id,
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
        market_subscription_run_id=market_subscription_run_id,
        dry_run_json_path=dry_run_json_path,
        rollback_sql_path=rollback_sql_path,
    )
    baseline = capture_execute_baseline(
        dsn=dsn,
        execute_run_id=execute_run_id,
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
    )
    preflight = build_execute_preflight(
        dry_run_report=dry_run_report,
        contract=contract,
        baseline_summary=baseline,
        dry_run_json_path=dry_run_json_path,
        rollback_sql_path=rollback_sql_path,
    )
    write_json(contract_json_path, contract)
    write_text(contract_markdown_path, format_execute_contract(contract))
    write_json(preflight_json_path, preflight)
    write_text(preflight_markdown_path, format_execute_preflight(preflight))
    return preflight


def assert_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise StandardTriggerExecuteError(
            "N4 v2 standard trigger execute blocked: missing " + ", ".join(missing)
        )


def run_standard_trigger_once(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    execute_run_id: str = DEFAULT_20260528_EXECUTE_RUN_ID,
    trigger_context_run_id: str = DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID,
    snapshot_run_id: str = DEFAULT_20260528_SNAPSHOT_RUN_ID,
    market_subscription_run_id: str | None = None,
    dry_run_json_path: str = DEFAULT_20260528_DRY_RUN_JSON_PATH,
    rollback_sql_path: str = DEFAULT_20260528_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    assert_execute_confirmed(execute=execute, user_confirmed=user_confirmed)
    dry_run_report = load_json(dry_run_json_path)
    contract = build_execute_contract_from_dry_run(
        dry_run_report,
        execute_run_id=execute_run_id,
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
        market_subscription_run_id=market_subscription_run_id,
        dry_run_json_path=dry_run_json_path,
        rollback_sql_path=rollback_sql_path,
    )
    baseline = capture_execute_baseline(
        dsn=dsn,
        execute_run_id=execute_run_id,
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
    )
    preflight = build_execute_preflight(
        dry_run_report=dry_run_report,
        contract=contract,
        baseline_summary=baseline,
        dry_run_json_path=dry_run_json_path,
        rollback_sql_path=rollback_sql_path,
    )
    if preflight["result"] != "PREFLIGHT_PASS":
        raise StandardTriggerExecuteError(f"N4 v2 standard trigger execute blocked: {preflight['blockers']}")

    trigger_run, context_rows = fetch_context_rows(dsn, trigger_context_run_id)
    snapshot_run, snapshot_rows = fetch_snapshot_rows(dsn, snapshot_run_id)
    plans = build_local_trigger_plans(
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
        context_rows=context_rows,
        snapshot_rows=snapshot_rows,
    )
    write_counts = execute_standard_trigger_transaction(
        dsn=dsn,
        execute_run_id=execute_run_id,
        trigger_context_run=trigger_run,
        snapshot_run=snapshot_run,
        plans=plans,
        quality_items=preflight["quality_items"],
    )
    return {
        "result": "EXECUTED",
        "layer_role": "N4_trigger",
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "snapshot_run_id": snapshot_run_id,
        "write_counts": write_counts,
    }


def execute_standard_trigger_transaction(
    *,
    dsn: str,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    snapshot_run: Mapping[str, Any],
    plans: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_standard_trigger_execute_transaction",
        source_run_id=execute_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            assert_no_existing_execute_outputs(cur, execute_run_id)
            insert_execute_trigger_run(
                cur,
                execute_run_id=execute_run_id,
                trigger_context_run=trigger_context_run,
                snapshot_run=snapshot_run,
                plan_count=len(plans),
                quality_items=quality_items,
            )
            quality_count = insert_execute_quality_items(
                cur,
                execute_run_id=execute_run_id,
                source_condition_run_id=str(trigger_context_run.get("source_condition_run_id") or DEFAULT_20260528_SOURCE_CONDITION_RUN_ID),
                for_trade_date=str(trigger_context_run.get("for_trade_date") or snapshot_run.get("for_trade_date") or ""),
                source_trade_date=str(trigger_context_run.get("source_trade_date") or snapshot_run.get("source_trade_date") or ""),
                items=quality_items,
            )
            state_count = 0
            match_count = 0
            outbox_count = 0
            outcome_event_ids_by_plan_id: dict[str, str] = {}
            for plan in plans:
                state_id = upsert_execute_state(cur, execute_run_id=execute_run_id, trigger_context_run=trigger_context_run, plan=plan)
                dedup_key = build_execute_dedup_key(execute_run_id=execute_run_id, plan=plan)
                output_event_id = build_stable_event_id(
                    source_layer=N4_SOURCE_LAYER,
                    event_type=str(plan["output_event_type"]),
                    source_run_id=execute_run_id,
                    dedup_key=dedup_key,
                    event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
                )
                match_id = insert_execute_match(
                    cur,
                    execute_run_id=execute_run_id,
                    trigger_context_run=trigger_context_run,
                    plan=plan,
                    trigger_state_id=state_id,
                    dedup_key=dedup_key,
                    output_event_id=output_event_id,
                )
                update_execute_state_last_match(cur, trigger_state_id=state_id, trigger_match_id=match_id)
                envelope = build_execute_event_envelope(
                    execute_run_id=execute_run_id,
                    trigger_context_run=trigger_context_run,
                    plan=plan,
                    trigger_state_id=state_id,
                    trigger_match_id=match_id,
                    output_event_id=output_event_id,
                    dedup_key=dedup_key,
                )
                insert_outbox_envelope(cur, envelope)
                outcome_event_ids_by_plan_id[str(plan.get("plan_id") or "")] = output_event_id
                state_count += 1
                match_count += 1
                outbox_count += 1
            for state_plan in build_trigger_state_change_plans(plans):
                source_outcome_event_id = outcome_event_ids_by_plan_id.get(str(state_plan.get("source_outcome_plan_id") or ""))
                envelope = build_execute_state_changed_event_envelope(
                    execute_run_id=execute_run_id,
                    trigger_context_run=trigger_context_run,
                    plan=state_plan,
                    source_outcome_event_id=source_outcome_event_id,
                )
                insert_outbox_envelope(cur, envelope)
                outbox_count += 1
            cur.execute(
                """
                UPDATE common_trigger_run
                SET status = 'passed',
                    trigger_state_row_count = %s,
                    trigger_match_row_count = %s,
                    trigger_event_outbox_count = %s,
                    finished_at = now(),
                    updated_at = now()
                WHERE run_id = %s
                """,
                (state_count, match_count, outbox_count, execute_run_id),
            )
        conn.commit()
    return {
        "common_trigger_run": 1,
        "common_trigger_quality_item": quality_count,
        "common_trigger_state": state_count,
        "common_trigger_match": match_count,
        "common_event_outbox": outbox_count,
    }


def insert_execute_trigger_run(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    snapshot_run: Mapping[str, Any],
    plan_count: int,
    quality_items: Sequence[Mapping[str, Any]],
) -> None:
    severity = count_quality_severities(quality_items)
    cur.execute(
        """
        INSERT INTO common_trigger_run (
          run_id, source_condition_run_id, source_market_data_run_id,
          for_trade_date, source_trade_date, prev_trade_date, mode, status,
          p0_count, p1_count, p2_count, source_condition_row_count,
          context_snapshot_row_count, trigger_state_row_count,
          trigger_match_row_count, trigger_event_outbox_count,
          generated_by, market_data_pulled, action_layer_touched,
          user_layer_touched, voice_touched, sim_touched, real_trade_touched,
          worker_started, raw_json, started_at, updated_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(source_market_data_run_id)s,
          %(for_trade_date)s, %(source_trade_date)s, %(prev_trade_date)s,
          'execute', 'running', %(p0_count)s, %(p1_count)s, %(p2_count)s,
          %(source_condition_row_count)s, 0, 0, 0, 0,
          'trigger_standard_execute_v2', false, false, false, false, false,
          false, false, %(raw_json)s, now(), now()
        )
        """,
        {
            "run_id": execute_run_id,
            "source_condition_run_id": trigger_context_run.get("source_condition_run_id"),
            "source_market_data_run_id": snapshot_run.get("run_id"),
            "for_trade_date": trigger_context_run.get("for_trade_date"),
            "source_trade_date": trigger_context_run.get("source_trade_date"),
            "prev_trade_date": trigger_context_run.get("prev_trade_date") or trigger_context_run.get("source_trade_date"),
            "p0_count": severity["P0"],
            "p1_count": severity["P1"],
            "p2_count": severity["P2"],
            "source_condition_row_count": int(trigger_context_run.get("context_snapshot_row_count") or plan_count),
            "raw_json": jsonb(
                {
                    "trigger_context_run_id": trigger_context_run.get("run_id"),
                    "snapshot_run_id": snapshot_run.get("run_id"),
                    "canonical_runtime_spec": "docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md",
                    "writes_outbox": True,
                    "consumes_n3_outbox": False,
                }
            ),
        },
    )


def insert_execute_quality_items(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    source_condition_run_id: str = DEFAULT_20260528_SOURCE_CONDITION_RUN_ID,
    for_trade_date: str = "",
    source_trade_date: str = "",
    items: Sequence[Mapping[str, Any]],
) -> int:
    rows = []
    for item in items:
        rows.append(
            (
                execute_run_id,
                source_condition_run_id,
                for_trade_date,
                source_trade_date,
                "common",
                "trigger_run",
                "common_trigger_run",
                str(item.get("gate_code") or ""),
                str(item.get("gate_name") or item.get("gate_code") or ""),
                str(item.get("severity") or "P0"),
                str(item.get("status") or "passed"),
                item.get("expected_value"),
                item.get("actual_value"),
                None,
                jsonb(item.get("details") or {}),
            )
        )
    if rows:
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


def upsert_execute_state(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> int:
    lifecycle_state_key_version = str(plan.get("lifecycle_state_key_version") or "")
    current_status = str(
        plan.get("current_status")
        or ("matched" if plan.get("output_event_type") == "TriggerMatched" else "pending_market_data")
    )
    matched = current_status == "matched"
    trigger_time = parse_event_time(plan)
    conflict_clause = """
        ON CONFLICT (
          run_id, for_trade_date, asset_kind, identity_key, direction,
          signal_type, condition_key
        )
        WHERE ((raw_json ->> 'lifecycle_state_key_version') = 'n4_lifecycle_state_key_v1')
    """ if lifecycle_state_key_version == "n4_lifecycle_state_key_v1" else """
        ON CONFLICT (
          run_id, for_trade_date, asset_kind, identity_key, direction,
          signal_type, condition_key, trigger_period, trigger_bucket
        )
    """
    cur.execute(
        f"""
        INSERT INTO common_trigger_state (
          run_id, source_condition_run_id, for_trade_date, asset_kind,
          identity_key, direction, signal_type, condition_key, trigger_period,
          trigger_bucket, trigger_live, trigger_mark_candidate,
          primary_trigger_period, all_trigger_periods, projection_30m_flag,
          projection_30m_type, current_status, last_source_event_id,
          data_quality_status, context_hash, match_count, first_matched_at,
          last_matched_at, raw_json, updated_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s,
          %(asset_kind)s, %(identity_key)s, %(direction)s, %(signal_type)s,
          %(condition_key)s, %(trigger_period)s, %(trigger_bucket)s,
          %(trigger_live)s, %(trigger_mark_candidate)s,
          %(primary_trigger_period)s, %(all_trigger_periods)s,
          %(projection_30m_flag)s, %(projection_30m_type)s,
          %(current_status)s, %(last_source_event_id)s, %(data_quality_status)s,
          %(context_hash)s, %(match_count)s, %(first_matched_at)s,
          %(last_matched_at)s, %(raw_json)s, now()
        )
        {conflict_clause}
        DO UPDATE SET
          trigger_live = EXCLUDED.trigger_live,
          trigger_mark_candidate = EXCLUDED.trigger_mark_candidate,
          primary_trigger_period = EXCLUDED.primary_trigger_period,
          all_trigger_periods = EXCLUDED.all_trigger_periods,
          projection_30m_flag = EXCLUDED.projection_30m_flag,
          projection_30m_type = EXCLUDED.projection_30m_type,
          current_status = EXCLUDED.current_status,
          last_source_event_id = EXCLUDED.last_source_event_id,
          data_quality_status = EXCLUDED.data_quality_status,
          context_hash = EXCLUDED.context_hash,
          match_count = common_trigger_state.match_count + EXCLUDED.match_count,
          first_matched_at = CASE
            WHEN EXCLUDED.current_status = 'matched'
              THEN COALESCE(common_trigger_state.first_matched_at, EXCLUDED.first_matched_at)
            ELSE common_trigger_state.first_matched_at
          END,
          last_matched_at = CASE
            WHEN EXCLUDED.current_status = 'matched' THEN EXCLUDED.last_matched_at
            ELSE common_trigger_state.last_matched_at
          END,
          raw_json = EXCLUDED.raw_json,
          updated_at = now()
        RETURNING trigger_state_id
        """,
        {
            "run_id": execute_run_id,
            "source_condition_run_id": trigger_context_run.get("source_condition_run_id"),
            "for_trade_date": trigger_context_run.get("for_trade_date"),
            "asset_kind": plan.get("asset_kind"),
            "identity_key": plan.get("identity_key"),
            "direction": plan.get("direction"),
            "signal_type": plan.get("signal_type"),
            "condition_key": plan.get("condition_key"),
            "trigger_period": plan.get("trigger_period"),
            "trigger_bucket": plan.get("trigger_bucket"),
            "trigger_live": bool(plan.get("trigger_live")),
            "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
            "primary_trigger_period": plan.get("primary_trigger_period"),
            "all_trigger_periods": jsonb(plan.get("all_trigger_periods") or []),
            "projection_30m_flag": bool(plan.get("projection_30m_flag")),
            "projection_30m_type": plan.get("projection_30m_type") or "none",
            "current_status": current_status,
            "last_source_event_id": plan.get("source_event_id"),
            "data_quality_status": schema_data_quality_status(plan.get("data_quality_status")),
            "context_hash": plan.get("context_hash"),
            "match_count": 1 if matched else 0,
            "first_matched_at": trigger_time if matched else None,
            "last_matched_at": trigger_time if matched else None,
            "raw_json": jsonb(
                {
                    "stage": "N4-20260528-v2-standard-trigger-execute",
                    "lifecycle_state_key_version": lifecycle_state_key_version or None,
                    "lifecycle_state_key": plan.get("lifecycle_state_key"),
                    "trigger_context_run_id": trigger_context_run.get("run_id"),
                    "canonical_plan": dict(plan),
                }
            ),
        },
    )
    return int(cur.fetchone()["trigger_state_id"])


def insert_execute_match(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    trigger_state_id: int,
    dedup_key: str,
    output_event_id: str,
) -> int:
    raw_json = build_trigger_match_raw_json(trigger_context_run=trigger_context_run, plan=plan)
    cur.execute(
        """
        INSERT INTO common_trigger_match (
          run_id, trigger_state_id, source_event_id, source_event_type,
          source_condition_run_id, source_condition_pool_id,
          source_condition_basis_id, source_market_subscription_id,
          for_trade_date, asset_kind, identity_key, direction, signal_type,
          condition_key, trigger_price, trigger_mark_candidate, trigger_time, trigger_period,
          trigger_bucket, data_quality_status, output_event_type,
          output_event_id, dedup_key, context_hash, raw_json
        )
        VALUES (
          %(run_id)s, %(trigger_state_id)s, %(source_event_id)s,
          %(source_event_type)s, %(source_condition_run_id)s,
          %(source_condition_pool_id)s, %(source_condition_basis_id)s,
          %(source_market_subscription_id)s, %(for_trade_date)s,
          %(asset_kind)s, %(identity_key)s, %(direction)s, %(signal_type)s,
          %(condition_key)s, %(trigger_price)s, %(trigger_mark_candidate)s, %(trigger_time)s,
          %(trigger_period)s, %(trigger_bucket)s, %(data_quality_status)s,
          %(output_event_type)s, %(output_event_id)s, %(dedup_key)s,
          %(context_hash)s, %(raw_json)s
        )
        ON CONFLICT (
          run_id, source_event_id, asset_kind, identity_key, direction,
          signal_type, condition_key, trigger_period, trigger_bucket
        )
        DO UPDATE SET
          trigger_state_id = EXCLUDED.trigger_state_id,
          output_event_id = EXCLUDED.output_event_id,
          dedup_key = EXCLUDED.dedup_key,
          data_quality_status = EXCLUDED.data_quality_status,
          trigger_mark_candidate = EXCLUDED.trigger_mark_candidate,
          raw_json = EXCLUDED.raw_json
        RETURNING trigger_match_id
        """,
        {
            "run_id": execute_run_id,
            "trigger_state_id": trigger_state_id,
            "source_event_id": plan.get("source_event_id"),
            "source_event_type": plan.get("source_event_type"),
            "source_condition_run_id": trigger_context_run.get("source_condition_run_id"),
            "source_condition_pool_id": plan.get("source_condition_pool_id"),
            "source_condition_basis_id": plan.get("source_condition_basis_id"),
            "source_market_subscription_id": plan.get("source_market_subscription_id"),
            "for_trade_date": trigger_context_run.get("for_trade_date"),
            "asset_kind": plan.get("asset_kind"),
            "identity_key": plan.get("identity_key"),
            "direction": plan.get("direction"),
            "signal_type": plan.get("signal_type"),
            "condition_key": plan.get("condition_key"),
            "trigger_price": plan.get("trigger_price"),
            "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
            "trigger_time": parse_event_time(plan),
            "trigger_period": plan.get("trigger_period"),
            "trigger_bucket": plan.get("trigger_bucket"),
            "data_quality_status": schema_data_quality_status(plan.get("data_quality_status")),
            "output_event_type": plan.get("output_event_type"),
            "output_event_id": output_event_id,
            "dedup_key": dedup_key,
            "context_hash": plan.get("context_hash"),
            "raw_json": jsonb(raw_json),
        },
    )
    return int(cur.fetchone()["trigger_match_id"])


def build_trigger_match_raw_json(
    *,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Build audit-friendly N4 match fact metadata.

    The event outbox payload remains the canonical cross-layer protocol. The
    match fact raw_json mirrors v4 required fields at the top level so audits
    and replay tools do not have to infer them from a nested canonical_plan.
    """

    return {
        "stage": "N4-20260528-v2-standard-trigger-execute",
        "trigger_context_run_id": trigger_context_run.get("run_id"),
        "trigger_price": plan.get("trigger_price"),
        "trigger_kind": plan.get("trigger_kind"),
        "triggered_periods": plan.get("triggered_periods") or [],
        "all_trigger_periods": plan.get("all_trigger_periods") or [],
        "primary_trigger_period": plan.get("primary_trigger_period"),
        "trigger_live": plan.get("trigger_live"),
        "current_status": plan.get("current_status"),
        "n5_entry_allowed": plan.get("n5_entry_allowed"),
        "match_basis": plan.get("match_basis"),
        "canonical_plan": dict(plan),
    }


def update_execute_state_last_match(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    trigger_state_id: int,
    trigger_match_id: int,
) -> None:
    cur.execute(
        """
        UPDATE common_trigger_state
        SET last_trigger_match_id = %s,
            updated_at = now()
        WHERE trigger_state_id = %s
        """,
        (trigger_match_id, trigger_state_id),
    )


def build_execute_event_envelope(
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    trigger_state_id: int,
    trigger_match_id: int,
    output_event_id: str,
    dedup_key: str,
) -> EventEnvelope:
    payload = {
        "run_id": execute_run_id,
        "source_event_id": plan.get("source_event_id"),
        "source_event_type": plan.get("source_event_type"),
        "source_snapshot_run_id": plan.get("source_snapshot_run_id"),
        "trigger_context_run_id": trigger_context_run.get("run_id"),
        "context_snapshot_id": plan.get("context_snapshot_id"),
        "trigger_state_id": trigger_state_id,
        "trigger_match_id": trigger_match_id,
        "identity_key": plan.get("identity_key"),
        "asset_kind": plan.get("asset_kind"),
        "direction": plan.get("direction"),
        "condition_key": plan.get("condition_key"),
        "original_condition_key": plan.get("original_condition_key"),
        "legacy_signal_type": plan.get("legacy_signal_type"),
        "signal_type": plan.get("signal_type"),
        "trigger_price": plan.get("trigger_price"),
        "trigger_time": parse_event_time(plan).isoformat(),
        "trigger_kind": plan.get("trigger_kind"),
        "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
        "match_basis": plan.get("match_basis"),
        "trigger_period": plan.get("trigger_period"),
        "trigger_bucket": plan.get("trigger_bucket"),
        "triggered_periods": plan.get("triggered_periods") or [],
        "trigger_live": plan.get("trigger_live"),
        "current_status": plan.get("current_status"),
        "n5_entry_allowed": plan.get("n5_entry_allowed"),
        "primary_trigger_period": plan.get("primary_trigger_period"),
        "all_trigger_periods": plan.get("all_trigger_periods"),
        "projection_period": plan.get("projection_period"),
        "projection_30m_flag": plan.get("projection_30m_flag"),
        "projection_30m_type": plan.get("projection_30m_type"),
        "data_quality_status": plan.get("data_quality_status"),
        "db_data_quality_status": schema_data_quality_status(plan.get("data_quality_status")),
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "source_condition_pool_id": plan.get("source_condition_pool_id"),
        "source_condition_basis_id": plan.get("source_condition_basis_id"),
        "source_minute_target_scope_id": plan.get("source_minute_target_scope_id"),
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "source_market_data_run_id": plan.get("source_market_data_run_id")
        or plan.get("source_snapshot_run_id")
        or plan.get("projection_run_id"),
        "context_hash": plan.get("context_hash"),
        "snapshot_trace": plan.get("snapshot_trace") or {},
        "projection_trace": plan.get("projection_trace") or {},
        "n3_trace": plan.get("n3_trace")
        or plan.get("projection_trace")
        or plan.get("snapshot_trace")
        or {},
        "period_trigger_baseline_trace": plan.get("period_trigger_baseline_trace") or {},
        "n4_boundary": {
            "market_data_pulled": False,
            "n3_outbox_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
    }
    envelope = EventEnvelope(
        event_id=output_event_id,
        event_type=str(plan.get("output_event_type")),
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        trade_date=str(trigger_context_run.get("for_trade_date")),
        asset_kind=str(plan.get("asset_kind")),
        identity_key=str(plan.get("identity_key")),
        event_time=parse_event_time(plan),
        source_layer=N4_SOURCE_LAYER,
        source_run_id=execute_run_id,
        dedup_key=dedup_key,
        partition_key=str(plan.get("identity_key")),
        payload_json=payload,
        created_at=utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def build_execute_state_changed_event_envelope(
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    source_outcome_event_id: str | None,
) -> EventEnvelope:
    source_outcome_event_id = source_outcome_event_id or str(plan.get("source_outcome_event_id") or "")
    dedup_key = build_n4_trigger_state_changed_dedup_key(
        asset_kind=str(plan.get("asset_kind")),
        identity_key=str(plan.get("identity_key")),
        trade_date=str(trigger_context_run.get("for_trade_date")),
        direction=str(plan.get("direction")),
        signal_type=str(plan.get("signal_type")),
        condition_key=str(plan.get("condition_key")),
        trigger_bucket=str(plan.get("trigger_bucket")),
        trigger_mark_candidate=str(plan.get("trigger_mark_candidate")),
        previous_status=plan.get("previous_status"),  # type: ignore[arg-type]
        current_status=str(plan.get("current_status")),
        previous_trigger_live=bool(plan.get("previous_trigger_live")),
        trigger_live=bool(plan.get("trigger_live")),
        previous_primary_trigger_period=plan.get("previous_primary_trigger_period"),  # type: ignore[arg-type]
        primary_trigger_period=plan.get("primary_trigger_period"),  # type: ignore[arg-type]
        previous_all_trigger_periods=plan.get("previous_all_trigger_periods"),
        all_trigger_periods=plan.get("all_trigger_periods"),
        state_change_reason=str(plan.get("state_change_reason")),
        source_outcome_event_id=source_outcome_event_id,
    )
    output_event_id = build_stable_event_id(
        source_layer=N4_SOURCE_LAYER,
        event_type=STATE_CHANGE_EVENT_TYPE,
        source_run_id=execute_run_id,
        dedup_key=dedup_key,
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
    )
    payload = {
        "run_id": execute_run_id,
        "source_event_id": source_outcome_event_id,
        "source_event_type": plan.get("source_outcome_event_type"),
        "source_snapshot_run_id": plan.get("source_snapshot_run_id"),
        "trigger_context_run_id": trigger_context_run.get("run_id"),
        "context_snapshot_id": plan.get("context_snapshot_id"),
        "identity_key": plan.get("identity_key"),
        "asset_kind": plan.get("asset_kind"),
        "direction": plan.get("direction"),
        "condition_key": plan.get("condition_key"),
        "original_condition_key": plan.get("original_condition_key"),
        "legacy_signal_type": plan.get("legacy_signal_type"),
        "signal_type": plan.get("signal_type"),
        "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
        "match_basis": plan.get("match_basis"),
        "trigger_period": plan.get("trigger_period"),
        "trigger_bucket": plan.get("trigger_bucket"),
        "trigger_live": bool(plan.get("trigger_live")),
        "previous_trigger_live": bool(plan.get("previous_trigger_live")),
        "current_status": plan.get("current_status"),
        "previous_status": plan.get("previous_status"),
        "primary_trigger_period": plan.get("primary_trigger_period"),
        "previous_primary_trigger_period": plan.get("previous_primary_trigger_period"),
        "all_trigger_periods": plan.get("all_trigger_periods") or [],
        "previous_all_trigger_periods": plan.get("previous_all_trigger_periods") or [],
        "projection_30m_flag": bool(plan.get("projection_30m_flag")),
        "projection_30m_type": plan.get("projection_30m_type") or "none",
        "previous_projection_30m_flag": bool(plan.get("previous_projection_30m_flag")),
        "previous_projection_30m_type": plan.get("previous_projection_30m_type") or "none",
        "previous_trigger_mark_candidate": plan.get("previous_trigger_mark_candidate"),
        "state_change_reason": plan.get("state_change_reason"),
        "source_outcome_event_type": plan.get("source_outcome_event_type"),
        "source_outcome_event_id": source_outcome_event_id,
        "data_quality_status": plan.get("data_quality_status"),
        "db_data_quality_status": schema_data_quality_status(plan.get("data_quality_status")),
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "source_condition_pool_id": plan.get("source_condition_pool_id"),
        "source_condition_basis_id": plan.get("source_condition_basis_id"),
        "source_minute_target_scope_id": plan.get("source_minute_target_scope_id"),
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "context_hash": plan.get("context_hash"),
        "snapshot_trace": plan.get("snapshot_trace") or {},
        "period_trigger_baseline_trace": plan.get("period_trigger_baseline_trace") or {},
        "writes_common_trigger_match": False,
        "n4_boundary": {
            "market_data_pulled": False,
            "n3_outbox_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
    }
    envelope = EventEnvelope(
        event_id=output_event_id,
        event_type=STATE_CHANGE_EVENT_TYPE,
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        trade_date=str(trigger_context_run.get("for_trade_date")),
        asset_kind=str(plan.get("asset_kind")),
        identity_key=str(plan.get("identity_key")),
        event_time=parse_event_time(plan),
        source_layer=N4_SOURCE_LAYER,
        source_run_id=execute_run_id,
        dedup_key=dedup_key,
        partition_key=str(plan.get("identity_key")),
        payload_json=payload,
        created_at=utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def insert_outbox_envelope(cur: psycopg.Cursor[dict[str, Any]], envelope: EventEnvelope) -> str:
    record = envelope.as_record()
    values = [jsonb(record[column]) if column == "payload_json" else record[column] for column in OUTBOX_COLUMNS]
    columns = ", ".join(OUTBOX_COLUMNS)
    placeholders = ", ".join(["%s"] * len(OUTBOX_COLUMNS))
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


def assert_no_existing_execute_outputs(cur: psycopg.Cursor[dict[str, Any]], execute_run_id: str) -> None:
    counts = {
        "common_trigger_run": query_count(cur, "common_trigger_run", "run_id = %s", (execute_run_id,)),
        "common_trigger_quality_item": query_count(cur, "common_trigger_quality_item", "run_id = %s", (execute_run_id,)),
        "common_trigger_match": query_count(cur, "common_trigger_match", "run_id = %s", (execute_run_id,)),
        "common_trigger_state": query_count(cur, "common_trigger_state", "run_id = %s", (execute_run_id,)),
        "common_event_outbox": query_count(
            cur,
            "common_event_outbox",
            "source_layer = 'N4_trigger' AND source_run_id = %s",
            (execute_run_id,),
        ),
        "common_event_inbox": query_count(cur, "common_event_inbox", "source_run_id = %s", (execute_run_id,)),
        "checkpoint_refs": query_count(
            cur,
            "common_event_consumer_checkpoint",
            "source_layer = 'N4_trigger' AND checkpoint_payload::text LIKE %s",
            (f"%{execute_run_id}%",),
        ),
    }
    nonzero = {key: value for key, value in counts.items() if int(value or 0) != 0}
    if nonzero:
        raise StandardTriggerExecuteError(f"N4 v2 standard trigger execute blocked: existing target refs {nonzero}")


def target_baseline_is_clean(baseline_summary: Mapping[str, int]) -> bool:
    target_keys = (
        "execute_run_common_trigger_run",
        "execute_run_quality",
        "execute_run_match",
        "execute_run_state",
        "execute_run_outbox",
        "execute_run_inbox",
        "execute_run_checkpoint_refs",
        "execute_run_outbox_delivered_or_delivering",
        "downstream_inbox_for_execute_run",
        "downstream_checkpoint_refs",
        "n5_action_run_refs",
    )
    return all(int(baseline_summary.get(key) or 0) == 0 for key in target_keys)


def deprecated_runtime_signal_type_paths(value: Any, *, path: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "signal_type" and isinstance(child, str) and child in DEPRECATED_RUNTIME_SIGNAL_TYPES:
                paths.append(child_path)
            else:
                paths.extend(deprecated_runtime_signal_type_paths(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(deprecated_runtime_signal_type_paths(child, path=f"{path}[{index}]"))
    return paths


def sample_original_condition_key_missing_count(dry_run_report: Mapping[str, Any]) -> int:
    count = 0
    for plan in dry_run_report.get("sample_plans") or []:
        if not isinstance(plan, Mapping):
            continue
        if plan.get("signal_type") and not str(plan.get("original_condition_key") or "").strip():
            count += 1
    return count


def dry_run_quality_gate_codes(quality: Mapping[str, Any], *, severity: str) -> list[str]:
    explicit = quality.get(f"{severity.lower()}_gate_codes")
    if explicit:
        return list(explicit)
    return [
        str(item.get("gate_code") or "")
        for item in quality.get("items") or []
        if isinstance(item, Mapping) and item.get("severity") == severity and str(item.get("gate_code") or "")
    ]


def query_count(
    cur: psycopg.Cursor[dict[str, Any]],
    table_name: str,
    where_clause: str,
    params: Sequence[Any],
) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE {where_clause}", tuple(params))
    return int(cur.fetchone()["row_count"])


def table_exists(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table_name}",))
    return bool(cur.fetchone()["table_name"])


def schema_data_quality_status(value: Any) -> str:
    return SCHEMA_DATA_QUALITY_STATUS.get(str(value or "").strip() or "missing", "missing")


def parse_event_time(plan: Mapping[str, Any]) -> datetime:
    trace = plan.get("snapshot_trace") or {}
    raw = plan.get("trigger_time") or plan.get("event_time")
    if raw is None and isinstance(trace, Mapping):
        raw = trace.get("snapshot_time")
    if raw:
        text = str(raw).replace(" ", "T")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def build_execute_dedup_key(*, execute_run_id: str, plan: Mapping[str, Any]) -> str:
    return join_dedup_parts(
        "N4_trigger",
        str(plan.get("output_event_type")),
        execute_run_id,
        str(plan.get("source_event_id")),
        str(plan.get("asset_kind")),
        str(plan.get("identity_key")),
        str(plan.get("direction")),
        str(plan.get("signal_type")),
        str(plan.get("trigger_mark_candidate")),
        str(plan.get("condition_key")),
        str(plan.get("original_condition_key")),
        str(plan.get("trigger_period")),
        str(plan.get("trigger_bucket")),
    )


def summarize_plans(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matched = [plan for plan in plans if plan.get("output_event_type") == "TriggerMatched"]
    pending = [plan for plan in plans if plan.get("output_event_type") == "TriggerPendingMarketData"]
    return {
        "candidate_count": len(plans),
        "matched_plan_count": len(matched),
        "pending_plan_count": len(pending),
        "matched_by_signal_type": dict(Counter(str(plan.get("signal_type")) for plan in matched)),
        "pending_by_signal_type": dict(Counter(str(plan.get("signal_type")) for plan in pending)),
        "matched_by_trigger_mark_candidate": dict(Counter(str(plan.get("trigger_mark_candidate")) for plan in matched)),
        "pending_by_trigger_mark_candidate": dict(Counter(str(plan.get("trigger_mark_candidate")) for plan in pending)),
    }


def format_execute_contract(contract: Mapping[str, Any]) -> str:
    expected = contract.get("expected_writes") or {}
    readiness = contract.get("runner_readiness") or {}
    trade_date = contract.get("for_trade_date") or "unknown"
    return "\n".join(
        [
            f"# N4 {trade_date} V2 Trigger Execute Contract",
            "",
            f"- result: `{contract.get('result')}`",
            f"- execute_run_id: `{contract.get('execute_run_id')}`",
            f"- context_run_id: `{contract.get('trigger_context_run_id')}`",
            f"- snapshot_run_id: `{contract.get('snapshot_run_id')}`",
            f"- event_schema_version: `{contract.get('event_schema_version')}`",
            f"- runner_ready: `{readiness.get('ready')}`",
            "",
            "## Expected Future Writes",
            "",
            f"- TriggerMatched: `{expected.get('TriggerMatched')}`",
            f"- TriggerPendingMarketData: `{expected.get('TriggerPendingMarketData')}`",
            f"- TriggerStateChanged: `{expected.get('TriggerStateChanged')}`",
            f"- common_trigger_state: `{expected.get('common_trigger_state')}`",
            f"- common_trigger_match: `{expected.get('common_trigger_match')}`",
            f"- common_event_outbox: `{expected.get('common_event_outbox')}`",
            "",
            "## Canonical Payload",
            "",
            "- runtime signal_type: `B_BUY`, `S_SELL`",
            "- trigger_mark_candidate: `normal`, `30m_volume`, `30m_shrink`",
            "- trace fields preserve `condition_key`, `original_condition_key`, `legacy_signal_type`",
            "- deprecated 30m and hint values are forbidden in runtime `signal_type`",
            "",
            "## Boundary",
            "",
            "- preflight refresh writes no database rows",
            "- final execute requires `--execute --user-confirmed`",
            "- N5/N6 remain blocked until N4 outbox execute is separately confirmed and passed",
        ]
    )


def format_execute_preflight(preflight: Mapping[str, Any]) -> str:
    quality = preflight.get("quality") or {}
    expected = preflight.get("expected_future_writes") or {}
    baseline = preflight.get("baseline_summary") or {}
    next_gate = preflight.get("next_gate") or {}
    trade_date = preflight.get("for_trade_date") or "unknown"
    lines = [
        f"# N4 {trade_date} V2 Trigger Execute Preflight",
        "",
        f"- result: `{preflight.get('result')}`",
        f"- execute_run_id: `{preflight.get('execute_run_id')}`",
        f"- context_run_id: `{preflight.get('trigger_context_run_id')}`",
        f"- snapshot_run_id: `{preflight.get('snapshot_run_id')}`",
        f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
        f"- allow_final_gate: `{next_gate.get('allow_enter_n4_v2_execute_final_gate')}`",
        "",
        "## Expected Writes After Final Confirmation",
        "",
        f"- TriggerMatched: `{expected.get('TriggerMatched')}`",
        f"- TriggerPendingMarketData: `{expected.get('TriggerPendingMarketData')}`",
        f"- common_event_outbox: `{expected.get('common_event_outbox')}`",
        "",
        "## Baseline",
        "",
    ]
    for key in sorted(baseline):
        lines.append(f"- {key}: `{baseline[key]}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- no database writes in this preflight",
            "- no N3 outbox consumption",
            "- no inbox/checkpoint writes",
            "- no N5/N6/worker/real trade",
        ]
    )
    return "\n".join(lines)
