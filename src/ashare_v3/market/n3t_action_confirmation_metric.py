"""N3T closed-C1 action-confirmation metric contract helpers.

This module is a pure N3_market_data contract surface. It does not connect to
DB, read market data, write outbox rows, or run N3P/B1/B2 logic.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from ashare_v3.market.minute_label_normalization import (
    BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE,
    MinuteLabelNormalizationError,
    ashare_c1_minute_close_time,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
ASSET_KINDS = ("stock", "index", "board")
N3T_SOURCE_BASIS = "N3T_C1_CLOSED"
N3T_METRIC_ROLE = "action_confirmation"
N3T_PROOF_CONSUMER = "N5"
N3T_SCHEMA_VERSION = "n3t.action_confirmation_metric.v1"
N3T_SCOPED_C1_INPUT_ARTIFACT_TYPE = "n3_c1_scoped_closed_1m_artifact_v1"
N3T_SCOPED_METRIC_PLAN_TYPE = "n3t_scoped_metric_from_c1_artifact_plan_v1"
BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH = "BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH"
BLOCKED_N3T_EXECUTE_CONTEXT_INSUFFICIENT = "BLOCKED_N3T_EXECUTE_CONTEXT_INSUFFICIENT"
BLOCKED_FULL_MARKET_FALLBACK_RISK = "BLOCKED_FULL_MARKET_FALLBACK_RISK"
N3T_RUN_ID_RE = re.compile(r"^n3t_action_confirmation_metric_(?P<trade_date>\d{8})_until_(?P<hhmm>\d{4})__(?P<suffix>.+)$")
FORBIDDEN_LINEAGE_TOKENS = (
    "realtime_action_confirmation_metric",
    "n3p",
    "b1_",
    "b2_",
)
N3T_TABLE_BY_ASSET_KIND = {
    "stock": "stock_n3t_action_confirmation_metric",
    "index": "index_n3t_action_confirmation_metric",
    "board": "board_n3t_action_confirmation_metric",
}
N3T_CURRENT_DAY_MINUTE_TABLE_BY_ASSET_KIND = {
    "stock": "stock_minute_bar_1m",
    "index": "index_minute_bar_1m",
    "board": "board_minute_bar_1m",
}
N3T_PREVIOUS_DAY_CUMULATIVE_TABLE_BY_ASSET_KIND = {
    "stock": "stock_previous_day_minute_cumulative",
    "index": "index_previous_day_minute_cumulative",
    "board": "board_previous_day_minute_cumulative",
}
N3T_PREVIOUS_DAY_MINUTE_TABLE_BY_ASSET_KIND = {
    "stock": "stock_previous_day_minute_bar_1m",
    "index": "index_previous_day_minute_bar_1m",
    "board": "board_previous_day_minute_bar_1m",
}
N3T_FORBIDDEN_WRITER_INPUTS = (
    "N3P trigger proof rows",
    "B1 snapshot rows as proof",
    "B2 projection rows as proof",
    "legacy realtime_action_confirmation_metric as final action proof",
    "external market data adapters",
    "raw unclosed minute rows",
)
N3T_N5_COMPATIBILITY_ALIASES = {
    "current_30m_virtual_amount": "current_30m_closed_elapsed_amount",
    "current_5m_virtual_amount": "current_5m_amount",
    "previous_5m_full_amount": "previous_5m_amount",
}
N3T_NUMERIC_OUTPUT_FIELDS = (
    "current_price",
    "previous_120m_body_high",
    "previous_120m_body_low",
    "previous_30m_body_high",
    "previous_30m_body_low",
    "previous_5m_body_high",
    "previous_5m_body_low",
    "previous_1m_body_high",
    "previous_1m_body_low",
    "current_1m_amount",
    "previous_1m_amount",
    "current_5m_amount",
    "previous_5m_amount",
    "current_5m_virtual_amount",
    "previous_5m_full_amount",
    "current_30m_closed_elapsed_amount",
    "current_30m_virtual_amount",
    "previous_day_same_window_amount",
)
N3T_BOOLEAN_OUTPUT_FIELDS = (
    "is_first_1m_of_day",
    "is_first_5m_of_day",
    "first_1m_amount_default_pass",
    "first_5m_amount_default_pass",
)
N3T_OUTPUT_FIELDS = N3T_NUMERIC_OUTPUT_FIELDS + N3T_BOOLEAN_OUTPUT_FIELDS
N3T_WRITER_INSERT_BASE_COLUMNS = (
    "projection_run_id",
    "projection_schema_version",
    "for_trade_date",
    "trade_date",
    "asset_kind",
    "identity_key",
    "metric_time",
    "metric_minute_label",
    "source_basis",
    "metric_role",
    "proof_consumer",
    "not_n5_final_proof",
)
N3T_WRITER_INSERT_TRAIL_COLUMNS = (
    "source_closed_minute_bar_ids",
    "previous_day_minute_refs",
    "metric_ready",
    "metric_quality_status",
    "blocked_reasons",
    "trace_json",
    "raw_json",
)
N3T_WRITER_INSERT_COLUMNS = N3T_WRITER_INSERT_BASE_COLUMNS + N3T_OUTPUT_FIELDS + N3T_WRITER_INSERT_TRAIL_COLUMNS
N3T_READY_REQUIRED_FIELDS = (
    "current_price",
    "previous_120m_body_high",
    "previous_120m_body_low",
    "previous_30m_body_high",
    "previous_30m_body_low",
    "previous_5m_body_high",
    "previous_5m_body_low",
    "previous_1m_body_high",
    "previous_1m_body_low",
    "current_1m_amount",
    "current_5m_amount",
    "current_30m_closed_elapsed_amount",
)
N3T_SCOPED_C1_REQUIRED_SCOPE_GRAIN = (
    "for_trade_date",
    "asset_kind",
    "identity_key",
    "direction",
    "signal_type",
    "condition_key",
    "source_trigger_event_id",
    "source_trigger_run_id",
    "scope_status",
)
N3T_SCOPED_SIDE_EFFECT_FLAGS = (
    "database_written",
    "market_data_pulled",
    "writes_canonical_minute_bar_1m",
    "writes_n3_outbox",
    "consumes_n4_outbox",
    "updates_n4_outbox",
    "full_market_fallback_used",
    "runtime_execute",
)


class N3TMetricContractError(ValueError):
    """Raised when an N3T metric contract input is outside the allowed lineage."""


def build_n3t_metric_run_id(trade_date: str, until_hhmm: str, suffix: str) -> str:
    if not re.fullmatch(r"\d{8}", str(trade_date or "")):
        raise N3TMetricContractError("n3t_trade_date_must_be_yyyymmdd")
    hhmm = str(until_hhmm or "").replace(":", "")
    if not re.fullmatch(r"\d{4}", hhmm):
        raise N3TMetricContractError("n3t_until_hhmm_must_be_hhmm")
    suffix_text = str(suffix or "").strip("_ ")
    if not suffix_text:
        raise N3TMetricContractError("n3t_run_id_suffix_required")
    _reject_forbidden_lineage(suffix_text)
    return f"n3t_action_confirmation_metric_{trade_date}_until_{hhmm}__{suffix_text}"


def parse_n3t_metric_run_id(run_id: str) -> dict[str, str]:
    text = str(run_id or "")
    match = N3T_RUN_ID_RE.fullmatch(text)
    if not match:
        raise N3TMetricContractError("n3t_metric_run_id_required")
    _reject_forbidden_lineage(match.group("suffix"))
    return {
        "trade_date": match.group("trade_date"),
        "until_hhmm": match.group("hhmm"),
        "suffix": match.group("suffix"),
    }


def build_n3t_action_confirmation_metric_schema_contract() -> dict[str, Any]:
    return {
        "schema_version": N3T_SCHEMA_VERSION,
        "storage_option": "Option A",
        "table_by_asset_kind": dict(N3T_TABLE_BY_ASSET_KIND),
        "ddl_draft_by_asset_kind": {
            asset_kind: _build_table_ddl(asset_kind, table_name)
            for asset_kind, table_name in N3T_TABLE_BY_ASSET_KIND.items()
        },
        "lineage": {
            "source_basis": N3T_SOURCE_BASIS,
            "metric_role": N3T_METRIC_ROLE,
            "proof_consumer": N3T_PROOF_CONSUMER,
            "not_n5_final_proof": False,
            "run_id_prefix": "n3t_action_confirmation_metric_YYYYMMDD_until_HHMM__",
        },
        "output_fields": list(N3T_OUTPUT_FIELDS),
        "numeric_output_fields": list(N3T_NUMERIC_OUTPUT_FIELDS),
        "boolean_output_fields": list(N3T_BOOLEAN_OUTPUT_FIELDS),
        "n5_compatibility_aliases": dict(N3T_N5_COMPATIBILITY_ALIASES),
        "boundary": {
            "c1_definition": "closed_1m_bar_label_hhmm_covers_hhmm_to_hhmm_plus_1",
            "writes_n3_to_n4_outbox": False,
            "writes_n4_or_n5_or_n6": False,
            "uses_n3p_b1_b2_or_realtime_action_confirmation_metric": False,
            "pulls_market_data": False,
            "runtime_execute": False,
            "launchd": False,
        },
    }


def build_n3t_action_confirmation_metric_writer_draft_plan(
    *,
    projection_run_id: str,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    metric_minute_label: str,
    as_of_time: Any,
    metric_values: Mapping[str, Any] | None,
    source_closed_minute_bar_ids: Sequence[Any],
    previous_day_minute_refs: Sequence[Any],
    candidate_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = build_n3t_action_confirmation_metric_row(
        projection_run_id=projection_run_id,
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=trade_date,
        metric_minute_label=metric_minute_label,
        as_of_time=as_of_time,
        metric_values=metric_values,
        source_closed_minute_bar_ids=source_closed_minute_bar_ids,
        previous_day_minute_refs=previous_day_minute_refs,
        candidate_trace=candidate_trace,
    )
    for reason in (BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE, "BLOCKED_C1_MINUTE_NOT_CLOSED"):
        if reason in row["blocked_reasons"]:
            raise N3TMetricContractError(reason)

    target_table = N3T_TABLE_BY_ASSET_KIND[asset_kind]
    return {
        "writer_mode": "draft_only",
        "runtime_execute": False,
        "db_write_executed": False,
        "pulls_market_data": False,
        "source_basis": N3T_SOURCE_BASIS,
        "metric_role": N3T_METRIC_ROLE,
        "proof_consumer": N3T_PROOF_CONSUMER,
        "input_contract": {
            "allowed_input_tables": [
                N3T_CURRENT_DAY_MINUTE_TABLE_BY_ASSET_KIND[asset_kind],
                N3T_PREVIOUS_DAY_CUMULATIVE_TABLE_BY_ASSET_KIND[asset_kind],
            ],
            "minute_bar_table": N3T_CURRENT_DAY_MINUTE_TABLE_BY_ASSET_KIND[asset_kind],
            "current_day_minute_filter": {"is_previous_day_preload": False},
            "previous_day_raw_minute_filter": {"is_previous_day_preload": True},
            "same_window_cumulative_table": N3T_PREVIOUS_DAY_CUMULATIVE_TABLE_BY_ASSET_KIND[asset_kind],
            "logical_previous_day_minute_table": {
                "name": N3T_PREVIOUS_DAY_MINUTE_TABLE_BY_ASSET_KIND[asset_kind],
                "physical_table_required": False,
                "stored_in": N3T_CURRENT_DAY_MINUTE_TABLE_BY_ASSET_KIND[asset_kind],
                "selector": "is_previous_day_preload=true",
            },
            "allowed_input_context": [
                "closed C1 current-day rows from minute_bar_table where is_previous_day_preload=false",
                "previous-day raw C1 rows from minute_bar_table where is_previous_day_preload=true",
                "previous-day same-window cumulative context when already materialized",
            ],
            "requires_closed_c1": True,
            "required_source_basis": N3T_SOURCE_BASIS,
            "forbidden_inputs": list(N3T_FORBIDDEN_WRITER_INPUTS),
        },
        "write_contract": {
            "target_table": target_table,
            "allowed_write_tables": list(N3T_TABLE_BY_ASSET_KIND.values()),
            "writes_common_event_outbox": False,
            "writes_common_event_inbox": False,
            "writes_common_event_consumer_checkpoint": False,
            "writes_n3_to_n4_outbox": False,
            "writes_n4_n5_n6": False,
            "future_execute_requires_explicit_gate": True,
        },
        "insert_plan": {
            "operation": "INSERT_DRAFT_ONLY",
            "target_table": target_table,
            "columns": list(N3T_WRITER_INSERT_COLUMNS),
            "rows": [row],
        },
        "side_effects": {
            "db_write_executed": False,
            "runtime_execute": False,
            "launchd": False,
            "pulls_market_data": False,
            "writes_n3_to_n4_outbox": False,
            "writes_n4_or_n5_or_n6": False,
        },
    }


def build_n3t_scoped_metric_from_c1_artifact_plan(
    scoped_c1_artifact: Mapping[str, Any] | None,
    *,
    source_artifact_path: str | None = None,
    source_artifact_hash: str | None = None,
) -> dict[str, Any]:
    """Build a plan-only N3T metric contract from an explicit scoped C1 artifact."""

    artifact = dict(scoped_c1_artifact or {})
    for_trade_date = str(artifact.get("for_trade_date") or "")
    target_minute_label = str(artifact.get("target_minute_label") or "")
    base = _base_scoped_metric_plan(
        for_trade_date=for_trade_date,
        target_minute_label=target_minute_label,
        source_artifact_path=source_artifact_path,
        source_artifact_hash=source_artifact_hash,
    )

    boundary_reason = _scoped_c1_boundary_block_reason(artifact)
    if boundary_reason:
        return _blocked_scoped_metric_plan(base, boundary_reason)

    if not re.fullmatch(r"\d{8}", for_trade_date) or not re.fullmatch(r"\d{2}:\d{2}", target_minute_label):
        return _blocked_scoped_metric_plan(base, BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH)
    try:
        _minute_close_time(trade_date=for_trade_date, minute_label=target_minute_label)
    except N3TMetricContractError as exc:
        return _blocked_scoped_metric_plan(base, str(exc))

    artifact_status = str(artifact.get("artifact_status") or "")
    if artifact_status == "blocked":
        return _blocked_scoped_metric_plan(
            base,
            str(artifact.get("blocked_reason") or BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH),
        )

    scope_rows = list(artifact.get("scope_rows") or [])
    if artifact_status == "noop" or artifact.get("empty_scope_noop") is True or not scope_rows:
        base.update(
            {
                "plan_status": "noop",
                "empty_scope_noop": True,
                "metric_plan_rows": [],
                "scope_count": 0,
            }
        )
        return base

    if artifact_status != "planned":
        return _blocked_scoped_metric_plan(base, BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH)

    normalized_scope_rows: list[dict[str, str]] = []
    for row in scope_rows:
        normalized = _normalize_scoped_c1_scope_row(row)
        if not _valid_scoped_c1_scope_row(normalized, for_trade_date):
            return _blocked_scoped_metric_plan(base, BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH)
        normalized_scope_rows.append(normalized)

    metric_context_rows = list(artifact.get("metric_context_rows") or [])
    if artifact.get("metric_context_status") != "ready" or not metric_context_rows:
        return _blocked_scoped_metric_plan(base, BLOCKED_N3T_EXECUTE_CONTEXT_INSUFFICIENT)
    metric_context_by_key = _metric_context_by_scope_key(metric_context_rows, for_trade_date)
    if not metric_context_by_key:
        return _blocked_scoped_metric_plan(base, BLOCKED_N3T_EXECUTE_CONTEXT_INSUFFICIENT)

    metric_rows: list[dict[str, Any]] = []
    scope_keys: set[tuple[str, ...]] = set()
    for normalized in normalized_scope_rows:
        scope_key = _scoped_c1_scope_key(normalized)
        scope_keys.add(scope_key)
        context = metric_context_by_key.get(scope_key)
        if not context:
            return _blocked_scoped_metric_plan(base, BLOCKED_N3T_EXECUTE_CONTEXT_INSUFFICIENT)
        target_table = N3T_TABLE_BY_ASSET_KIND[normalized["asset_kind"]]
        metric_rows.append(
            {
                **normalized,
                "trade_date": for_trade_date,
                "metric_minute_label": target_minute_label,
                "target_table": target_table,
                "source_artifact_type": N3T_SCOPED_C1_INPUT_ARTIFACT_TYPE,
                "source_basis": N3T_SOURCE_BASIS,
                "metric_role": N3T_METRIC_ROLE,
                "proof_consumer": N3T_PROOF_CONSUMER,
                "not_n5_final_proof": False,
                "candidate_trace_authority": "trace_only_not_authoritative",
                "source_closed_minute_bar_ids": context["source_closed_minute_bar_ids"],
                "closed_minute_rows": context["closed_minute_rows"],
                "previous_day_minute_refs": context["previous_day_minute_refs"],
                "metric_values": context["metric_values"],
                "deterministic_derivation_inputs": context["deterministic_derivation_inputs"],
            }
        )
    if set(metric_context_by_key) != scope_keys:
        return _blocked_scoped_metric_plan(base, BLOCKED_N3T_EXECUTE_CONTEXT_INSUFFICIENT)

    metric_rows.sort(
        key=lambda row: (
            row["asset_kind"],
            row["identity_key"],
            row["direction"],
            row["signal_type"],
            row["condition_key"],
        )
    )
    base.update(
        {
            "plan_status": "planned",
            "scope_count": len(metric_rows),
            "metric_plan_rows": metric_rows,
            "empty_scope_noop": False,
        }
    )
    return base


def is_c1_minute_closed_for_action_confirmation(trade_date: str, minute_label: str, as_of_time: Any) -> bool:
    close_time = _minute_close_time(trade_date=trade_date, minute_label=minute_label)
    return _coerce_shanghai(as_of_time) >= close_time


def build_n3t_action_confirmation_metric_row(
    *,
    projection_run_id: str,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    metric_minute_label: str,
    as_of_time: Any,
    metric_values: Mapping[str, Any] | None,
    source_closed_minute_bar_ids: Sequence[Any],
    previous_day_minute_refs: Sequence[Any],
    candidate_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    parse_n3t_metric_run_id(projection_run_id)
    if asset_kind not in N3T_TABLE_BY_ASSET_KIND:
        raise N3TMetricContractError("n3t_asset_kind_must_be_stock_index_or_board")
    if not str(identity_key or "").startswith(f"{asset_kind}:"):
        raise N3TMetricContractError("n3t_identity_key_must_match_asset_kind")

    values = dict(metric_values or {})
    closed_refs = list(source_closed_minute_bar_ids or [])
    previous_refs = list(previous_day_minute_refs or [])
    blocked_reasons: list[str] = []
    metric_close_time: datetime | None = None

    try:
        metric_close_time = _minute_close_time(trade_date=trade_date, minute_label=metric_minute_label)
    except N3TMetricContractError as exc:
        blocked_reasons.append(str(exc))

    if not closed_refs:
        blocked_reasons.append("BLOCKED_N3T_CLOSED_C1_CONTEXT_REQUIRED")
    if not previous_refs:
        blocked_reasons.append("BLOCKED_N3T_PREVIOUS_DAY_CONTEXT_REQUIRED")
    if metric_close_time is not None and _coerce_shanghai(as_of_time) < metric_close_time:
        blocked_reasons.append("BLOCKED_C1_MINUTE_NOT_CLOSED")

    missing_fields = [field for field in N3T_READY_REQUIRED_FIELDS if values.get(field) is None]
    if missing_fields:
        blocked_reasons.append("BLOCKED_N3T_METRIC_FIELDS_INCOMPLETE")

    metric_ready = not blocked_reasons
    row = {
        "projection_run_id": projection_run_id,
        "projection_schema_version": N3T_SCHEMA_VERSION,
        "for_trade_date": trade_date,
        "trade_date": trade_date,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "metric_time": metric_close_time.isoformat() if metric_close_time is not None else "",
        "metric_minute_label": metric_minute_label,
        "source_basis": N3T_SOURCE_BASIS,
        "metric_role": N3T_METRIC_ROLE,
        "proof_consumer": N3T_PROOF_CONSUMER,
        "not_n5_final_proof": False,
        "metric_ready": metric_ready,
        "metric_quality_status": "passed" if metric_ready else "blocked",
        "blocked_reasons": blocked_reasons,
        "source_closed_minute_bar_ids": closed_refs,
        "source_minute_refs": closed_refs,
        "previous_day_minute_refs": previous_refs,
        "trace_json": {
            "source_basis": N3T_SOURCE_BASIS,
            "metric_role": N3T_METRIC_ROLE,
            "proof_consumer": N3T_PROOF_CONSUMER,
            "not_n5_final_proof": False,
            "candidate_trace": dict(candidate_trace or {}),
            "candidate_trace_authority": "trace_only_not_authoritative",
            "closed_minute_contract": "bar_label_HHMM_is_usable_after_HHMM_plus_1",
            "alias_relationships": dict(N3T_N5_COMPATIBILITY_ALIASES),
        },
        "raw_json": {
            "blocked_reasons": blocked_reasons,
            "source_closed_minute_bar_ids": closed_refs,
            "previous_day_minute_refs": previous_refs,
        },
    }
    for field in N3T_NUMERIC_OUTPUT_FIELDS:
        row[field] = values.get(field)
    for alias_field, canonical_field in N3T_N5_COMPATIBILITY_ALIASES.items():
        row[alias_field] = values.get(canonical_field)
    for field in N3T_BOOLEAN_OUTPUT_FIELDS:
        row[field] = _bool_value(values.get(field), default=False)
    return row


def _build_table_ddl(asset_kind: str, table_name: str) -> str:
    columns = "\n  ".join(_column_ddl(field) for field in N3T_OUTPUT_FIELDS)
    return f"""CREATE TABLE IF NOT EXISTS {table_name} (
  n3t_action_confirmation_metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL,
  projection_schema_version TEXT NOT NULL DEFAULT '{N3T_SCHEMA_VERSION}',
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT '{asset_kind}' CHECK (asset_kind = '{asset_kind}'),
  identity_key TEXT NOT NULL CHECK (identity_key LIKE '{asset_kind}:%'),
  metric_time TIMESTAMPTZ NOT NULL,
  metric_minute_label TEXT NOT NULL,
  source_basis TEXT NOT NULL DEFAULT '{N3T_SOURCE_BASIS}' CHECK (source_basis = '{N3T_SOURCE_BASIS}'),
  metric_role TEXT NOT NULL DEFAULT '{N3T_METRIC_ROLE}' CHECK (metric_role = '{N3T_METRIC_ROLE}'),
  proof_consumer TEXT NOT NULL DEFAULT '{N3T_PROOF_CONSUMER}' CHECK (proof_consumer = '{N3T_PROOF_CONSUMER}'),
  not_n5_final_proof BOOLEAN NOT NULL DEFAULT false CHECK (not_n5_final_proof = false),
  {columns}
  source_closed_minute_bar_ids JSONB NOT NULL DEFAULT '[]'::JSONB,
  previous_day_minute_refs JSONB NOT NULL DEFAULT '[]'::JSONB,
  metric_ready BOOLEAN NOT NULL DEFAULT false,
  metric_quality_status TEXT NOT NULL DEFAULT 'blocked',
  blocked_reasons JSONB NOT NULL DEFAULT '[]'::JSONB,
  trace_json JSONB NOT NULL DEFAULT '{{}}'::JSONB,
  raw_json JSONB NOT NULL DEFAULT '{{}}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version),
  CHECK (projection_run_id LIKE 'n3t_action_confirmation_metric_%'),
  CHECK (for_trade_date ~ '^[0-9]{{8}}$'),
  CHECK (trade_date ~ '^[0-9]{{8}}$'),
  CHECK (current_30m_virtual_amount IS NULL OR current_30m_closed_elapsed_amount IS NULL OR current_30m_virtual_amount = current_30m_closed_elapsed_amount),
  CHECK (current_5m_virtual_amount IS NULL OR current_5m_amount IS NULL OR current_5m_virtual_amount = current_5m_amount),
  CHECK (previous_5m_full_amount IS NULL OR previous_5m_amount IS NULL OR previous_5m_full_amount = previous_5m_amount),
  CHECK (metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked'))
);"""


def _column_ddl(field: str) -> str:
    if field in N3T_BOOLEAN_OUTPUT_FIELDS:
        return f"{field} BOOLEAN NOT NULL DEFAULT false,"
    return f"{field} NUMERIC,"


def _reject_forbidden_lineage(value: str) -> None:
    lowered = str(value or "").lower()
    if any(token in lowered for token in FORBIDDEN_LINEAGE_TOKENS):
        raise N3TMetricContractError("n3t_must_not_reuse_n3p_b1_b2_or_legacy_realtime_metric_lineage")


def _base_scoped_metric_plan(
    *,
    for_trade_date: str,
    target_minute_label: str,
    source_artifact_path: str | None,
    source_artifact_hash: str | None,
) -> dict[str, Any]:
    side_effects = _false_scoped_side_effects()
    return {
        "plan_type": N3T_SCOPED_METRIC_PLAN_TYPE,
        "plan_status": "blocked",
        "blocked_reason": None,
        "layer_role": "N3_market_data",
        "input_artifact_type": N3T_SCOPED_C1_INPUT_ARTIFACT_TYPE,
        "source_c1_artifact": {
            "path": source_artifact_path,
            "hash": source_artifact_hash,
            "artifact_type": N3T_SCOPED_C1_INPUT_ARTIFACT_TYPE,
        },
        "for_trade_date": str(for_trade_date or ""),
        "target_minute_label": str(target_minute_label or ""),
        "source_basis": N3T_SOURCE_BASIS,
        "metric_role": N3T_METRIC_ROLE,
        "proof_consumer": N3T_PROOF_CONSUMER,
        "not_n5_final_proof": False,
        "target_tables": list(N3T_TABLE_BY_ASSET_KIND.values()),
        "metric_plan_rows": [],
        "scope_count": 0,
        "empty_scope_noop": False,
        "full_market_fallback_allowed": False,
        "n3_scans_n5_internals": False,
        "lineage_policy": {
            "n3p_b1_b2_realtime_action_confirmation_metric": "trace_only_not_final_proof",
            "source_basis": N3T_SOURCE_BASIS,
            "metric_role": N3T_METRIC_ROLE,
            "proof_consumer": N3T_PROOF_CONSUMER,
            "not_n5_final_proof": False,
        },
        "write_contract": {
            "target_tables": list(N3T_TABLE_BY_ASSET_KIND.values()),
            "allowed_write_tables": list(N3T_TABLE_BY_ASSET_KIND.values()),
            "writes_common_event_outbox": False,
            "writes_common_event_inbox": False,
            "writes_common_event_consumer_checkpoint": False,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_to_n4_outbox": False,
            "writes_n4_n5": False,
            "future_execute_requires_explicit_gate": True,
        },
        "side_effects": side_effects,
        "boundary": {
            **side_effects,
            "runtime_control_artifact_path_hash_required": True,
            "n3_scans_n5_internals": False,
            "full_market_fallback_allowed": False,
            "n3p_b1_b2_realtime_action_confirmation_metric_final_proof_allowed": False,
            "blocks_only_action_executed": True,
            "blocks_action_eligible": False,
            "affects_n3_or_n4_worker_status": False,
        },
        **side_effects,
    }


def _blocked_scoped_metric_plan(base: Mapping[str, Any], reason: str) -> dict[str, Any]:
    plan = dict(base)
    plan.update(
        {
            "plan_status": "blocked",
            "blocked_reason": reason,
            "metric_plan_rows": [],
            "scope_count": 0,
            "empty_scope_noop": False,
            "full_market_fallback_allowed": False,
            "n3_scans_n5_internals": False,
        }
    )
    return plan


def _scoped_c1_boundary_block_reason(artifact: Mapping[str, Any]) -> str | None:
    if artifact.get("artifact_type") != N3T_SCOPED_C1_INPUT_ARTIFACT_TYPE:
        return BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH
    if artifact.get("full_market_fallback_allowed") is True or artifact.get("full_market_fallback_used") is True:
        return BLOCKED_FULL_MARKET_FALLBACK_RISK
    if artifact.get("n3_scans_n5_internals") is True:
        return BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH
    for flag in N3T_SCOPED_SIDE_EFFECT_FLAGS:
        if artifact.get(flag) is True:
            return BLOCKED_N3T_SCOPED_INPUT_CONTRACT_MISMATCH
    return None


def _normalize_scoped_c1_scope_row(row: Any) -> dict[str, str]:
    source = dict(row or {})
    return {field: str(source.get(field) or "") for field in N3T_SCOPED_C1_REQUIRED_SCOPE_GRAIN}


def _valid_scoped_c1_scope_row(row: Mapping[str, str], for_trade_date: str) -> bool:
    if any(not row.get(field) for field in N3T_SCOPED_C1_REQUIRED_SCOPE_GRAIN):
        return False
    if row["for_trade_date"] != for_trade_date:
        return False
    if row["asset_kind"] not in N3T_TABLE_BY_ASSET_KIND:
        return False
    if not row["identity_key"].startswith(f"{row['asset_kind']}:"):
        return False
    if row["scope_status"] != "active":
        return False
    return True


def _metric_context_by_scope_key(rows: Sequence[Any], for_trade_date: str) -> dict[tuple[str, ...], dict[str, Any]]:
    indexed: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        normalized = _normalize_metric_context_row(row)
        if not _valid_metric_context_row(normalized, for_trade_date):
            return {}
        key = _scoped_c1_scope_key(normalized)
        if key in indexed:
            return {}
        indexed[key] = normalized
    return indexed


def _normalize_metric_context_row(row: Any) -> dict[str, Any]:
    source = dict(row or {})
    return {
        **_normalize_scoped_c1_scope_row(source),
        "source_closed_minute_bar_ids": list(source.get("source_closed_minute_bar_ids") or []),
        "closed_minute_rows": list(source.get("closed_minute_rows") or []),
        "previous_day_minute_refs": list(source.get("previous_day_minute_refs") or []),
        "metric_values": dict(source.get("metric_values") or {}),
        "deterministic_derivation_inputs": dict(source.get("deterministic_derivation_inputs") or {}),
    }


def _valid_metric_context_row(row: Mapping[str, Any], for_trade_date: str) -> bool:
    scope = {field: str(row.get(field) or "") for field in N3T_SCOPED_C1_REQUIRED_SCOPE_GRAIN}
    if not _valid_scoped_c1_scope_row(scope, for_trade_date):
        return False
    if not (row.get("source_closed_minute_bar_ids") or row.get("closed_minute_rows")):
        return False
    if not row.get("previous_day_minute_refs"):
        return False
    metric_values = dict(row.get("metric_values") or {})
    return all(metric_values.get(field) is not None for field in N3T_READY_REQUIRED_FIELDS)


def _scoped_c1_scope_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(field) or "") for field in N3T_SCOPED_C1_REQUIRED_SCOPE_GRAIN)


def _false_scoped_side_effects() -> dict[str, bool]:
    return {flag: False for flag in N3T_SCOPED_SIDE_EFFECT_FLAGS}


def _minute_close_time(*, trade_date: str, minute_label: str) -> datetime:
    if not re.fullmatch(r"\d{8}", str(trade_date or "")):
        raise N3TMetricContractError("n3t_trade_date_must_be_yyyymmdd")
    try:
        return ashare_c1_minute_close_time(trade_date, minute_label)
    except MinuteLabelNormalizationError as exc:
        if BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE in str(exc):
            raise N3TMetricContractError(BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE) from exc
        raise N3TMetricContractError("n3t_metric_minute_label_must_be_hh_colon_mm") from exc


def _coerce_shanghai(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ASIA_SHANGHAI)
    return dt.astimezone(ASIA_SHANGHAI)


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n", ""}:
        return False
    return bool(value)
