"""Row-level N2 context enrichment materialization helpers.

This module is deliberately pure: it plans payload rows and rollback text for
an N2-owned materialization gate, but it never connects to or writes a
database. The execute gate, if later approved, must use a separate command.
"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Mapping, Sequence

from ashare_v3.condition.context_enrichment import PERIODS, stable_hash


MATERIALIZATION_SPEC_VERSION = "N2-context-enrichment-row-materialization-v1"
MATERIALIZATION_POLICY = {
    "policy_name": "n2_context_enrichment_row_level_for_n4_v4",
    "source": "N2_condition",
    "source_context": "minute_target_scope",
    "target_consumer": "N4_trigger",
    "n4_can_recompute_context": False,
    "write_mode": "append_only_run_id_scoped",
    "overwrite_allowed": False,
}
MATERIALIZATION_POLICY_HASH = stable_hash(MATERIALIZATION_POLICY)

MATERIALIZATION_TABLES = (
    "common_condition_context_enrichment_run",
    "stock_condition_context_enrichment",
    "index_condition_context_enrichment",
    "board_condition_context_enrichment",
)
EXECUTE_SCRIPT = "scripts/run_n2_context_enrichment_materialization_execute.py"


def materialization_table_plan() -> dict[str, Any]:
    return {
        "current_gate_write_tables": [],
        "future_execute_write_tables": list(MATERIALIZATION_TABLES),
        "table_ownership": "N2_condition",
        "write_mode": "append_only_run_id_scoped",
        "forbidden_write_scopes": [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "N3_market_data",
            "N4_trigger",
            "N5_action",
            "N6_user",
            "worker",
        ],
    }


def build_execute_command_candidate(*, payload_path: str, contract_path: str) -> str:
    return (
        "PYTHONPATH=src:scripts python3 "
        f"{EXECUTE_SCRIPT} "
        f"--payload-path {payload_path} "
        f"--contract-path {contract_path} "
        "--execute "
        "--user-confirmed"
    )


def validate_execute_flags(*, execute: bool, user_confirmed: bool) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    if not execute:
        blocked_reasons.append("missing_execute_flag")
    if not user_confirmed:
        blocked_reasons.append("missing_user_confirmed_flag")
    return {
        "gate_result": "PASS" if not blocked_reasons else "BLOCKED",
        "blocked_reasons": blocked_reasons,
        "writes_allowed": not blocked_reasons,
    }


def build_materialization_payload_rows(
    rows_by_domain: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    source_condition_run_id: str,
    target_run_id: str,
    for_trade_date: str,
    spec_version: str = MATERIALIZATION_SPEC_VERSION,
    policy_hash: str = MATERIALIZATION_POLICY_HASH,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {"stock": [], "index": [], "board": []}
    for asset_kind in ("stock", "index", "board"):
        rows = rows_by_domain.get(asset_kind) or []
        for row in rows:
            output[asset_kind].append(
                build_materialization_payload_row(
                    row,
                    asset_kind=asset_kind,
                    source_condition_run_id=source_condition_run_id,
                    target_run_id=target_run_id,
                    for_trade_date=for_trade_date,
                    spec_version=spec_version,
                    policy_hash=policy_hash,
                )
            )
    return output


def build_materialization_payload_row(
    row: Mapping[str, Any],
    *,
    asset_kind: str,
    source_condition_run_id: str,
    target_run_id: str,
    for_trade_date: str,
    spec_version: str,
    policy_hash: str,
) -> dict[str, Any]:
    baseline = deepcopy(row.get("period_trigger_baseline_json") or {})
    payload_json = {
        "spec_version": spec_version,
        "source_layer": "N2_condition",
        "target_consumer": "N4_trigger",
        "n4_can_recompute_context": False,
        "context_enrichment_version": row.get("context_enrichment_version")
        or ((baseline.get("context_enrichment") or {}).get("context_enrichment_version") if isinstance(baseline, Mapping) else None),
        "context_enrichment_hash": row.get("context_enrichment_hash"),
        "period_trigger_baseline_json": baseline,
        "trigger_amount_chain_baseline_json": deepcopy(row.get("trigger_amount_chain_baseline_json") or {}),
        "trigger_amount_chain_formula_hash": row.get("trigger_amount_chain_formula_hash"),
        "FULL_prerequisite_trace_json": deepcopy(row.get("FULL_prerequisite_trace_json") or {}),
        "FULL_prerequisite_quality_status": row.get("FULL_prerequisite_quality_status"),
        "HINT_prerequisite_trace_json": deepcopy(row.get("HINT_prerequisite_trace_json") or {}),
        "HINT_prerequisite_quality_status": row.get("HINT_prerequisite_quality_status"),
    }
    row_key = stable_hash(
        {
            "target_run_id": target_run_id,
            "asset_kind": asset_kind,
            "identity_key": row.get("identity_key"),
            "condition_key": row.get("condition_key"),
            "source_scope_id": row.get("source_row_id"),
            "context_enrichment_hash": row.get("context_enrichment_hash"),
        }
    )
    return {
        "materialization_run_id": target_run_id,
        "spec_version": spec_version,
        "policy_hash": policy_hash,
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "source_trade_date": row.get("source_trade_date"),
        "asset_kind": asset_kind,
        "identity_key": row.get("identity_key"),
        "condition_key": row.get("condition_key"),
        "direction": row.get("direction"),
        "allowed_signal_types": list(row.get("allowed_signal_types") or []),
        "source_scope_table": row.get("context_source_table"),
        "source_scope_id": row.get("source_row_id"),
        "context_enrichment_hash": row.get("context_enrichment_hash"),
        "context_materialization_row_key": row_key,
        "payload_json": payload_json,
    }


def summarize_materialization_payload_rows(
    payload_rows_by_domain: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    expected_context_rows: int,
) -> dict[str, Any]:
    all_rows = [row for rows in payload_rows_by_domain.values() for row in rows]
    rows = {domain: len(payload_rows_by_domain.get(domain) or []) for domain in ("stock", "index", "board")}
    rows["total"] = len(all_rows)
    return {
        "rows": rows,
        "context_enrichment_hash_rows": sum(1 for row in all_rows if row.get("context_enrichment_hash")),
        "previous_transition_rows": sum(1 for row in all_rows if _all_periods_have(row, "previous_transition")),
        "trigger_previous_entity_bound_rows": sum(
            1
            for row in all_rows
            if _all_periods_have(row, "trigger_previous_entity_high")
            and _all_periods_have(row, "trigger_previous_entity_low")
        ),
        "trigger_previous_amount_baseline_rows": sum(
            1 for row in all_rows if _all_periods_have(row, "trigger_previous_amount_baseline")
        ),
        "previous_entity_bound_rows": sum(
            1
            for row in all_rows
            if _all_periods_have(row, "previous_entity_high") and _all_periods_have(row, "previous_entity_low")
        ),
        "previous_amount_baseline_rows": sum(1 for row in all_rows if _all_periods_have(row, "previous_amount_baseline")),
        "period_baseline_ready_distribution": _period_baseline_ready_distribution(all_rows),
        "FULL_trace_rows": sum(1 for row in all_rows if _payload(row).get("FULL_prerequisite_trace_json")),
        "HINT_trace_rows": sum(1 for row in all_rows if _payload(row).get("HINT_prerequisite_trace_json")),
        "expected_context_rows": expected_context_rows,
        "context_row_mismatch": 0 if not expected_context_rows or rows["total"] == expected_context_rows else 1,
    }


def build_materialization_rollback_sql(target_run_id: str, write_tables: Sequence[str] | None = None) -> str:
    tables = list(write_tables or MATERIALIZATION_TABLES)
    delete_tables = [table for table in tables if table != "common_condition_context_enrichment_run"]
    delete_tables.append("common_condition_context_enrichment_run")
    delete_lines = "\n".join(
        f"  DELETE FROM {table} WHERE {materialization_run_column(table)} = v_run_id;" for table in delete_tables
    )
    return f"""-- N2 context enrichment row-level materialization rollback.
-- Scope: only rows for {target_run_id}.
-- Hard-fails before DELETE if event infra or downstream N3/N4/N5/N6 refs exist.
DO $$
DECLARE
  v_run_id text := '{target_run_id}';
  v_ref_count bigint := 0;
BEGIN
  SELECT
      COALESCE((SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_consumer_checkpoint WHERE last_event_id LIKE '%' || v_run_id || '%' OR checkpoint_payload::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v_run_id OR run_id = v_run_id), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v_run_id OR run_id = v_run_id), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_state WHERE source_condition_run_id = v_run_id OR run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_match WHERE source_condition_run_id = v_run_id OR run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v_run_id OR run_id = v_run_id), 0)
    + COALESCE((SELECT count(*) FROM common_action_event WHERE source_condition_run_id = v_run_id OR run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR trace_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_projection_run WHERE source_display_condition_run_id = v_run_id OR quality_summary_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_signal_projection WHERE source_condition_display_run_id = v_run_id OR source_payload_json::text LIKE '%' || v_run_id || '%' OR display_payload_json::text LIKE '%' || v_run_id || '%' OR trace_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_signal_card WHERE card_payload_json::text LIKE '%' || v_run_id || '%' OR trace_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_notification_queue WHERE notification_payload_json::text LIKE '%' || v_run_id || '%' OR trace_json::text LIKE '%' || v_run_id || '%'), 0)
  INTO v_ref_count;

  IF v_ref_count > 0 THEN
    RAISE EXCEPTION 'rollback blocked: context materialization % has event/downstream refs: %', v_run_id, v_ref_count;
  END IF;

  IF EXISTS (SELECT 1 FROM common_condition_context_enrichment_run WHERE run_id = v_run_id AND COALESCE((raw_json->>'downstream_layers_touched')::boolean, false)) THEN
    RAISE EXCEPTION 'rollback blocked: context materialization % has downstream_layers_touched=true', v_run_id;
  END IF;

  IF EXISTS (SELECT 1 FROM common_condition_context_enrichment_run WHERE run_id = v_run_id AND COALESCE((raw_json->>'worker_started')::boolean, false)) THEN
    RAISE EXCEPTION 'rollback blocked: context materialization % has worker_started=true', v_run_id;
  END IF;

{delete_lines}
END $$;
"""


def materialization_run_column(table: str) -> str:
    if table == "common_condition_context_enrichment_run":
        return "run_id"
    return "materialization_run_id"


def _payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("payload_json")
    return payload if isinstance(payload, Mapping) else {}


def _periods(row: Mapping[str, Any]) -> Mapping[str, Any]:
    baseline = _payload(row).get("period_trigger_baseline_json")
    if not isinstance(baseline, Mapping):
        return {}
    periods = baseline.get("periods")
    return periods if isinstance(periods, Mapping) else {}


def _all_periods_have(row: Mapping[str, Any], field: str) -> bool:
    periods = _periods(row)
    for period in PERIODS:
        entry = periods.get(period)
        if not isinstance(entry, Mapping) or entry.get(field) in (None, ""):
            return False
    return True


def _period_baseline_ready_distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    distribution = {"all_ready": 0, "partial_or_not_ready": 0}
    for row in rows:
        periods = _periods(row)
        if all(isinstance(periods.get(period), Mapping) and bool(periods[period].get("period_baseline_ready")) for period in PERIODS):
            distribution["all_ready"] += 1
        else:
            distribution["partial_or_not_ready"] += 1
    return distribution


def write_payload_jsonl(path: str, payload_rows_by_domain: Mapping[str, Sequence[Mapping[str, Any]]]) -> int:
    count = 0
    with open(path, "w", encoding="utf-8") as handle:
        for domain in ("stock", "index", "board"):
            for row in payload_rows_by_domain.get(domain) or []:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
                count += 1
    return count
