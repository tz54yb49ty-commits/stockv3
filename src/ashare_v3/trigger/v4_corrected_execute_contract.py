"""N4 20260605 v4 corrected execute contract/preflight planning.

The helpers here are pure builders. They do not open database connections,
consume outbox rows, or write trigger facts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


DEFAULT_EXECUTE_RUN_ID = "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
DEFAULT_CONTRACT_PATH = "docs/N4_20260605_V4_CORRECTED_EXECUTE_CONTRACT.json"
DEFAULT_PREFLIGHT_PATH = "docs/N4_20260605_V4_CORRECTED_EXECUTE_PREFLIGHT.json"
DEFAULT_DRY_RUN_PATH = "docs/N4_20260605_V4_CORRECTED_DRY_RUN.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N4_20260605_V4_CORRECTED_EXECUTE_ROLLBACK.sql"
DEFAULT_RUNNER_PATH = "scripts/run_n4_20260605_v4_corrected_execute_once.py"
QUALITY_ITEM_COUNT = 4

P0_GUARDS = (
    "trigger_price",
    "trigger_kind",
    "triggered_periods",
    "all_trigger_periods",
    "primary_trigger_period",
    "n5_entry_allowed",
    "event_time_not_future",
    "trigger_time_not_future",
    "full_semantic_contract_guard",
    "runtime_signal_type_B_BUY_or_S_SELL",
    "baseline_source_trigger_baseline",
)

ALLOWED_WRITE_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
)

FORBIDDEN_SCOPE = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "N1/N2/N3 facts",
    "N5/N6",
    "worker",
    "delivery/push/voice/mobile/sim/position/real trade",
    "N6_UI_v1/B-track",
)


def build_corrected_execute_contract(
    dry_run_report: Mapping[str, Any],
    *,
    contract_path: str = DEFAULT_CONTRACT_PATH,
    preflight_path: str = DEFAULT_PREFLIGHT_PATH,
    dry_run_path: str = DEFAULT_DRY_RUN_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
    runner_path: str = DEFAULT_RUNNER_PATH,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the corrected execute contract from a corrected dry-run report."""

    generated_at = generated_at or datetime.now(timezone.utc)
    stage = (
        "N4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_CONTRACT_GATE"
        if "REPAIRED_CONTEXT" in dry_run_path
        else "N4_20260605_V4_CORRECTED_EXECUTE_CONTRACT_GATE"
    )
    execute_run_id = str(dry_run_report.get("execute_run_id") or DEFAULT_EXECUTE_RUN_ID)
    compliant_count = int(dry_run_report.get("compliant_count") or dry_run_report.get("persisted_plans_after_strict_guard") or 0)
    blocked_count = int(dry_run_report.get("blocked_count") or 0)
    blocked_reasons = dict(dry_run_report.get("blocked_counts_by_reason") or {})
    p0_count = int((dry_run_report.get("quality") or {}).get("p0_count") or 0)
    can_preflight = bool(dry_run_report.get("execute_preflight_could_pass"))
    result = "CONTRACT_PASS" if dry_run_report.get("result") == "DRY_RUN_PASS" and p0_count == 0 and can_preflight else "BLOCKED"
    planned_writes = {
        "common_trigger_run": 1 if compliant_count else 0,
        "common_trigger_quality_item": QUALITY_ITEM_COUNT,
        "common_trigger_state": compliant_count,
        "common_trigger_match": compliant_count,
        "common_event_outbox": compliant_count,
        "TriggerMatched": compliant_count,
        "TriggerPendingMarketData": 0,
        "TriggerStateChanged": 0,
    }
    execute_command = build_execute_command(
        execute_run_id=execute_run_id,
        runner_path=runner_path,
        contract_path=contract_path,
        preflight_path=preflight_path,
        dry_run_path=dry_run_path,
        rollback_sql_path=rollback_sql_path,
    )
    matcher_proof = dry_run_report.get("matcher_proof") or {}
    baseline_source_dist = dict(matcher_proof.get("trace_baseline_source_distribution_for_compliant") or {})
    baseline_source_not_trigger = sum(
        int(value or 0)
        for key, value in baseline_source_dist.items()
        if key != "trigger_baseline"
    )
    return {
        "result": result,
        "layer_role": "N4_trigger",
        "stage": stage,
        "mode": "execute_contract",
        "generated_at": generated_at.isoformat(),
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": dry_run_report.get("trigger_context_run_id"),
        "snapshot_run_id": dry_run_report.get("snapshot_run_id"),
        "projection_run_id": dry_run_report.get("projection_run_id"),
        "source_condition_run_id": dry_run_report.get("source_condition_run_id"),
        "for_trade_date": dry_run_report.get("for_trade_date"),
        "dry_run_artifact_path": dry_run_path,
        "enforcement_contract_path": "docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_CONTRACT.json",
        "enforcement_preflight_path": "docs/N4_TRIGGER_RULE_V4_ENFORCEMENT_PREFLIGHT.json",
        "contract_path": contract_path,
        "preflight_path": preflight_path,
        "rollback_sql_path": rollback_sql_path,
        "runner_path": runner_path,
        "execute_command_candidate": execute_command,
        "corrected_dry_run_baseline": {
            "candidate_plans_before_strict_guard": int(dry_run_report.get("candidate_plans_before_strict_guard") or 0),
            "persisted_plans_after_strict_guard": compliant_count,
            "blocked_count": blocked_count,
            "p0_count": p0_count,
            "p1_count": int((dry_run_report.get("quality") or {}).get("p1_count") or 0),
            "p2_count": int((dry_run_report.get("quality") or {}).get("p2_count") or 0),
            "invalid_n5_entry_count": int((dry_run_report.get("n5_entry_eligibility_proof") or {}).get("invalid_n5_entry_count") or 0),
            "baseline_source_not_trigger_baseline": baseline_source_not_trigger,
            "baseline_source_distribution": baseline_source_dist,
        },
        "semantic_delta_vs_tainted_run": dry_run_report.get("semantic_delta_vs_tainted_run"),
        "matcher_proof": matcher_proof,
        "planned_writes": planned_writes,
        "blocked_candidates": {
            "total": blocked_count,
            "by_reason": blocked_reasons,
            "reason_counts_are_non_exclusive": True,
            "b2_projection_missing_required_fields": int(blocked_reasons.get("missing trigger_price") or 0),
            "b2_projection_missing_triggered_periods": int(blocked_reasons.get("missing triggered_periods") or 0),
            "full_semantic_blocked": int(blocked_reasons.get("FULL semantic blocked") or 0),
            "write_trigger_matched": False,
        },
        "p0_guards": list(P0_GUARDS),
        "n5_entry_contract": {
            "required": "TriggerMatched + B_BUY/S_SELL + current_status=matched + trigger_live=true + n5_entry_allowed=true",
            "required_payload_fields": [
                "n5_entry_allowed",
                "trigger_live",
                "current_status",
                "signal_type",
                "trigger_price",
                "trigger_kind",
                "triggered_periods",
                "all_trigger_periods",
                "primary_trigger_period",
                "match_basis",
            ],
            "invalid_n5_entry_count": int((dry_run_report.get("n5_entry_eligibility_proof") or {}).get("invalid_n5_entry_count") or 0),
        },
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_scope": list(FORBIDDEN_SCOPE),
        "post_review_checks": {
            "actual_rows_equal_planned_rows": True,
            "strict_required_field_compliance": f"{compliant_count}/{compliant_count}",
            "trigger_price_null": 0,
            "future_event_time": 0,
            "future_trigger_time": 0,
            "FULL_semantic_violations": 0,
            "trigger_kind_missing": 0,
            "triggered_periods_missing": 0,
            "n5_entry_allowed_missing": 0,
            "baseline_source_not_trigger_baseline": baseline_source_not_trigger,
            "outbox_pending": compliant_count,
            "outbox_delivered": 0,
            "outbox_delivering": 0,
            "N5_N6_refs": 0,
        },
        "execute_authorized": False,
        "notes": [
            "This gate does not execute and does not write database rows.",
            "Corrected execute requires a dedicated runner that consumes the corrected dry-run compliant plan set.",
            "ActionExecuted in downstream N5 is an action confirmation fact only; it is not an order, fill, sim, position, or real trade.",
        ],
    }


def build_corrected_execute_preflight(
    contract: Mapping[str, Any],
    *,
    baseline_refs: Mapping[str, int],
    runner_exists: bool,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build final preflight from a corrected execute contract and read-only baseline refs."""

    generated_at = generated_at or datetime.now(timezone.utc)
    baseline = {key: int(value or 0) for key, value in baseline_refs.items()}
    blockers: list[str] = []
    if contract.get("result") != "CONTRACT_PASS":
        blockers.append("contract_not_pass")
    if any(value != 0 for value in baseline.values()):
        blockers.append("target_baseline_nonzero")
    if not runner_exists:
        blockers.append("runner_missing")
    planned = dict(contract.get("planned_writes") or {})
    if int(planned.get("TriggerMatched") or 0) <= 0:
        blockers.append("no_persisted_trigger_matched")
    result = "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED"
    p0_count = 0 if not blockers else len(blockers)
    return {
        "result": result,
        "layer_role": "N4_trigger",
        "stage": contract.get("stage"),
        "mode": "execute_preflight",
        "generated_at": generated_at.isoformat(),
        "execute_run_id": contract.get("execute_run_id"),
        "contract_path": contract.get("contract_path"),
        "preflight_path": contract.get("preflight_path"),
        "rollback_sql_path": contract.get("rollback_sql_path"),
        "execute_command_candidate": contract.get("execute_command_candidate"),
        "execute_authorized": False,
        "runner_readiness": {
            "ready": runner_exists,
            "runner_path": contract.get("runner_path"),
            "reason": "ready" if runner_exists else "corrected execute runner is not implemented yet",
        },
        "baseline_refs": baseline,
        "planned_writes": planned,
        "blocked_candidates": contract.get("blocked_candidates"),
        "p0_guards": contract.get("p0_guards"),
        "post_review_checks": contract.get("post_review_checks"),
        "blockers": blockers,
        "quality": {
            "p0_count": p0_count,
            "p1_count": int((contract.get("corrected_dry_run_baseline") or {}).get("p1_count") or 0),
            "p2_count": 0,
            "items": [
                {
                    "severity": "P0",
                    "status": "passed" if contract.get("result") == "CONTRACT_PASS" else "failed",
                    "gate_code": "n4_v4_corrected_execute_contract_pass",
                    "gate_name": "Corrected execute contract must be CONTRACT_PASS",
                    "expected_value": "CONTRACT_PASS",
                    "actual_value": str(contract.get("result")),
                },
                {
                    "severity": "P0",
                    "status": "passed" if not any(value != 0 for value in baseline.values()) else "failed",
                    "gate_code": "n4_v4_corrected_execute_target_baseline_zero",
                    "gate_name": "Corrected execute scoped baseline must be zero",
                    "expected_value": "all zero",
                    "actual_value": str(baseline),
                },
                {
                    "severity": "P0",
                    "status": "passed" if runner_exists else "failed",
                    "gate_code": "n4_v4_corrected_execute_runner_ready",
                    "gate_name": "Dedicated corrected execute runner must exist before final gate",
                    "expected_value": "runner ready",
                    "actual_value": "ready" if runner_exists else "missing",
                },
            ],
        },
        "forbidden_scope": contract.get("forbidden_scope"),
        "next_gate": "runtime_control corrected execute final gate review" if result == "PREFLIGHT_PASS" else "N4 corrected execute runner implementation",
    }


def build_corrected_execute_rollback_sql(execute_run_id: str) -> str:
    """Return hard-fail rollback SQL scoped to the corrected execute run."""

    return f"""-- N4 v4 corrected execute rollback.
-- Scope: execute_run_id={execute_run_id}
-- Use only before downstream N5/N6 consumption. Does not touch upstream facts or context snapshots.

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
    RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: outbox delivered/delivering refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND checkpoint_payload::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: downstream checkpoint refs = %', v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N5 action run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N5 action event refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_projection_run
      WHERE source_action_run_id = $1
         OR source_n5_outbox_range::TEXT LIKE '%' || $1 || '%'
         OR quality_summary_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_projection_run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_projection
      WHERE source_action_run_id = $1
         OR source_event_id = $1
         OR source_payload_json::TEXT LIKE '%' || $1 || '%'
         OR display_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_signal_projection refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_card
      WHERE source_action_run_id = $1
         OR source_event_id = $1
         OR card_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_signal_card refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_notification_queue
      WHERE source_action_run_id = $1
         OR source_event_id = $1
         OR notification_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_notification_queue refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_order
      WHERE sim_run_id = $1
         OR order_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_sim_order refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_trade
      WHERE sim_run_id = $1
         OR trade_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_sim_trade refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_position
      WHERE sim_run_id = $1
         OR position_payload_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 corrected execute rollback blocked: N6 user_sim_position refs = %', v_count;
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


def build_execute_command(
    *,
    execute_run_id: str,
    runner_path: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
    rollback_sql_path: str,
) -> str:
    return "\n".join(
        [
            f"PYTHONPATH=src:scripts python3 {runner_path} \\",
            f"  --execute-run-id {execute_run_id} \\",
            f"  --dry-run-json-path {dry_run_path} \\",
            f"  --contract-path {contract_path} \\",
            f"  --preflight-path {preflight_path} \\",
            f"  --rollback-sql-path {rollback_sql_path} \\",
            "  --execute \\",
            "  --user-confirmed",
        ]
    )
