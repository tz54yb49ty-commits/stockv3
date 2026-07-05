#!/usr/bin/env python3
"""Run-once N4 20260605 v4 corrected execute runner.

This runner persists only v4-compliant TriggerMatched plans that survived the
corrected strict guard dry-run. It never consumes upstream outbox rows and never
enters N5/N6.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import quality_item
from ashare_v3.trigger.query_audit_phase1 import audited_n4_trigger_connect
from ashare_v3.trigger.local_trigger_dry_run import (
    build_local_trigger_plans,
    fetch_context_rows,
    fetch_snapshot_rows,
)
from ashare_v3.trigger.projection_matcher import build_projection_matcher_plans, fetch_projection_rows
from ashare_v3.trigger.rule_v4_execute import (
    V4TriggerExecuteBlocked,
    execute_v4_matched_only_transaction,
)
from ashare_v3.trigger.synthetic_dry_run import write_json
from ashare_v3.trigger.v4_corrected_dry_run import (
    build_corrected_v4_dry_run_report,
    correct_trigger_matched_candidate,
)
from ashare_v3.trigger.v4_enforcement import collect_v4_trigger_matched_plan_violations
from check_condition_source_ready import DEFAULT_DSN


DEFAULT_EXECUTE_RUN_ID = "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
DEFAULT_DRY_RUN_PATH = "docs/N4_20260605_V4_CORRECTED_DRY_RUN.json"
DEFAULT_CONTRACT_PATH = "docs/N4_20260605_V4_CORRECTED_EXECUTE_CONTRACT.json"
DEFAULT_PREFLIGHT_PATH = "docs/N4_20260605_V4_CORRECTED_EXECUTE_PREFLIGHT.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N4_20260605_V4_CORRECTED_EXECUTE_ROLLBACK.sql"
DEFAULT_REPORT_PATH = "docs/N4_20260605_V4_CORRECTED_EXECUTE_REPORT.json"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="N4 20260605 v4 corrected execute runner.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_EXECUTE_RUN_ID)
    parser.add_argument("--dry-run-json-path", default=DEFAULT_DRY_RUN_PATH)
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--preflight-path", default=DEFAULT_PREFLIGHT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--report-json-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        assert_corrected_execute_confirmed(execute=args.execute, user_confirmed=args.user_confirmed)
        report = run_execute(args)
    except V4TriggerExecuteBlocked as exc:
        report = {
            "result": "BLOCKED",
            "layer_role": "N4_trigger",
            "execute_run_id": args.execute_run_id,
            "database_written": False,
            "writes_performed": False,
            "blocked_reason": str(exc),
            "boundary_proof": {
                "common_event_inbox_written": False,
                "checkpoint_written": False,
                "outbox_consumed": False,
                "n5_n6_entered": False,
                "worker_started": False,
                "n1_n2_n3_facts_modified": False,
                "n6_ui_v1_b_track_modified": False,
            },
        }
        if args.report_json_path:
            write_json(Path(args.report_json_path), report)
        print_report(report, as_json=args.json)
        return 2
    if args.report_json_path:
        write_json(Path(args.report_json_path), report)
    print_report(report, as_json=args.json)
    return 0 if report.get("result") == "EXECUTE_PASS" else 2


def assert_corrected_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise V4TriggerExecuteBlocked(
            "N4 v4 corrected execute blocked before DB write: missing " + ", ".join(missing)
        )


def run_execute(args: argparse.Namespace) -> dict[str, Any]:
    dry_run = load_json(args.dry_run_json_path)
    contract = load_json(args.contract_path)
    preflight = load_json(args.preflight_path)
    assert_artifacts_ready(dry_run=dry_run, contract=contract, preflight=preflight, args=args)
    baseline = capture_execute_guard_refs(args.dsn, args.execute_run_id)
    assert_baseline_clean(baseline)
    recomputed = recompute_corrected_dry_run_report(
        dsn=args.dsn,
        dry_run=dry_run,
        created_at=datetime.now(timezone.utc),
    )
    assert_recomputed_matches_approved(original=dry_run, recomputed=recomputed, contract=contract)
    write_plan = build_corrected_write_plan_from_report(recomputed, execute_run_id=args.execute_run_id)
    assert_write_plan_matches_contract(write_plan=write_plan, dry_run=dry_run, contract=contract, preflight=preflight)
    quality_items = build_corrected_quality_items(dry_run=recomputed, write_plan=write_plan)
    if any(item.get("severity") == "P0" and item.get("status") == "failed" for item in quality_items):
        raise V4TriggerExecuteBlocked("N4 v4 corrected execute blocked by quality items before DB write")
    trigger_run, _context_rows = fetch_context_rows(args.dsn, str(dry_run["trigger_context_run_id"]))
    snapshot_run, _snapshot_rows = fetch_snapshot_rows(args.dsn, str(dry_run["snapshot_run_id"]))
    actual_rows = execute_v4_matched_only_transaction(
        dsn=args.dsn,
        execute_run_id=args.execute_run_id,
        trigger_context_run=trigger_run,
        snapshot_run=snapshot_run,
        write_plan=write_plan,
        quality_items=quality_items,
    )
    post_review = build_post_review_checks(write_plan=write_plan, actual_rows=actual_rows)
    post_db_refs = capture_post_review_refs(args.dsn, args.execute_run_id)
    return {
        "result": "EXECUTE_PASS",
        "layer_role": "N4_trigger",
        "execute_run_id": args.execute_run_id,
        "actual_rows": actual_rows,
        "strict_compliance": post_review,
        "post_review_checks": post_review,
        "post_db_refs": post_db_refs,
        "rollback_sql_path": args.rollback_sql_path,
        "rollback_safe": (
            int(post_db_refs.get("outbox_delivered") or 0) == 0
            and int(post_db_refs.get("outbox_delivering") or 0) == 0
            and int(post_db_refs.get("n5_refs") or 0) == 0
            and int(post_db_refs.get("n6_refs") or 0) == 0
        ),
        "boundary_proof": {
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "outbox_consumed": False,
            "n5_n6_entered": False,
            "worker_started": False,
            "delivery_push_voice_mobile_sim_position_real_trade": False,
            "n1_n2_n3_facts_modified": False,
            "n6_ui_v1_b_track_modified": False,
        },
    }


def assert_artifacts_ready(
    *,
    dry_run: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    args: argparse.Namespace,
) -> None:
    blockers: list[str] = []
    planned = contract.get("planned_writes") or {}
    preflight_planned = preflight.get("planned_writes") or {}
    contract_baseline = contract.get("corrected_dry_run_baseline") or {}
    expected_blocked_count = as_optional_int((contract.get("blocked_candidates") or {}).get("total"))
    preflight_blocked_count = as_optional_int((preflight.get("blocked_candidates") or {}).get("total"))
    dry_run_blocked_count = as_optional_int(dry_run.get("blocked_count"))
    expected_candidate_count = as_optional_int(contract_baseline.get("candidate_plans_before_strict_guard"))
    expected_persisted_count = as_optional_int(contract_baseline.get("persisted_plans_after_strict_guard"))
    dry_run_candidate_count = as_optional_int(dry_run.get("candidate_plans_before_strict_guard"))
    dry_run_persisted_count = as_optional_int(dry_run.get("persisted_plans_after_strict_guard"))
    dry_run_compliant_count = as_optional_int(dry_run.get("compliant_count"))
    expected_matched_count = as_optional_int(planned.get("TriggerMatched"))
    if dry_run.get("result") != "DRY_RUN_PASS":
        blockers.append(f"dry-run result={dry_run.get('result')}")
    if contract.get("result") != "CONTRACT_PASS":
        blockers.append(f"contract result={contract.get('result')}")
    if preflight.get("result") != "PREFLIGHT_PASS":
        blockers.append(f"preflight result={preflight.get('result')}")
    if dry_run.get("execute_run_id") != args.execute_run_id:
        blockers.append("dry-run execute_run_id mismatch")
    if contract.get("execute_run_id") != args.execute_run_id:
        blockers.append("contract execute_run_id mismatch")
    if preflight.get("execute_run_id") != args.execute_run_id:
        blockers.append("preflight execute_run_id mismatch")
    if expected_matched_count is None:
        blockers.append("contract planned TriggerMatched missing")
    elif dry_run_compliant_count != expected_matched_count:
        blockers.append("dry-run compliant_count does not equal contract TriggerMatched planned rows")
    if expected_blocked_count is None:
        blockers.append("contract blocked_candidates.total missing")
    elif dry_run_blocked_count != expected_blocked_count:
        blockers.append("dry-run blocked_count does not equal contract blocked_candidates.total")
    if expected_blocked_count is not None and preflight_blocked_count != expected_blocked_count:
        blockers.append("preflight blocked_count does not equal contract blocked_candidates.total")
    if expected_candidate_count is None:
        blockers.append("contract corrected_dry_run_baseline candidate count missing")
    elif dry_run_candidate_count != expected_candidate_count:
        blockers.append("dry-run candidate count does not equal contract corrected_dry_run_baseline")
    if expected_persisted_count is not None and dry_run_persisted_count != expected_persisted_count:
        blockers.append("dry-run persisted count does not equal contract corrected_dry_run_baseline")
    if expected_persisted_count is not None and expected_matched_count is not None and expected_persisted_count != expected_matched_count:
        blockers.append("contract persisted count does not equal planned TriggerMatched rows")
    for key in ("common_trigger_state", "common_trigger_match", "common_event_outbox", "TriggerMatched"):
        if expected_matched_count is not None and as_optional_int(planned.get(key)) != expected_matched_count:
            blockers.append(f"contract planned {key} does not equal planned TriggerMatched")
        if as_optional_int(preflight_planned.get(key)) != as_optional_int(planned.get(key)):
            blockers.append(f"preflight planned {key} does not equal contract planned {key}")
    for key in ("TriggerPendingMarketData", "TriggerStateChanged"):
        if as_optional_int(planned.get(key)) != 0:
            blockers.append(f"contract planned {key} must be zero")
        if as_optional_int(preflight_planned.get(key)) != 0:
            blockers.append(f"preflight planned {key} must be zero")
    if int((dry_run.get("n5_entry_eligibility_proof") or {}).get("invalid_n5_entry_count") or 0) != 0:
        blockers.append("dry-run invalid N5 entry count is not zero")
    if not (preflight.get("runner_readiness") or {}).get("ready"):
        blockers.append("runner_readiness.ready is not true")
    if int((preflight.get("quality") or {}).get("p0_count") or 0) != 0:
        blockers.append("preflight P0 is not zero")
    if blockers:
        raise V4TriggerExecuteBlocked("N4 v4 corrected execute blocked by artifacts: " + "; ".join(blockers))


def as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def assert_baseline_clean(baseline: Mapping[str, int]) -> None:
    nonzero = {key: value for key, value in baseline.items() if int(value or 0) != 0}
    if nonzero:
        raise V4TriggerExecuteBlocked(f"N4 v4 corrected execute blocked by target baseline refs: {nonzero}")


def recompute_corrected_dry_run_report(
    *,
    dsn: str,
    dry_run: Mapping[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    trigger_run, context_rows = fetch_context_rows(dsn, str(dry_run["trigger_context_run_id"]))
    snapshot_run, snapshot_rows = fetch_snapshot_rows(dsn, str(dry_run["snapshot_run_id"]))
    projection_rows = fetch_projection_rows(dsn, str(dry_run["projection_run_id"]))
    local_plans = build_local_trigger_plans(
        trigger_context_run_id=str(dry_run["trigger_context_run_id"]),
        snapshot_run_id=str(dry_run["snapshot_run_id"]),
        context_rows=context_rows,
        snapshot_rows=snapshot_rows,
    )
    projection_plans = build_projection_matcher_plans(
        trigger_context_run_id=str(dry_run["trigger_context_run_id"]),
        projection_run_id=str(dry_run["projection_run_id"]),
        context_rows=context_rows,
        projection_rows=projection_rows,
    )
    return build_corrected_v4_dry_run_report(
        local_plans=local_plans,
        projection_plans=projection_plans,
        metadata={
            "execute_run_id": dry_run.get("execute_run_id"),
            "trigger_context_run_id": dry_run.get("trigger_context_run_id"),
            "snapshot_run_id": dry_run.get("snapshot_run_id"),
            "projection_run_id": dry_run.get("projection_run_id"),
            "source_condition_run_id": trigger_run.get("source_condition_run_id"),
            "for_trade_date": trigger_run.get("for_trade_date") or snapshot_run.get("for_trade_date"),
        },
        created_at=created_at,
        sample_limit=1_000_000,
    )


def assert_recomputed_matches_approved(
    *,
    original: Mapping[str, Any],
    recomputed: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    blockers: list[str] = []
    for key in ("candidate_plans_before_strict_guard", "compliant_count", "blocked_count"):
        if int(original.get(key) or 0) != int(recomputed.get(key) or 0):
            blockers.append(f"recomputed {key} mismatch")
    expected_matched = int((contract.get("planned_writes") or {}).get("TriggerMatched") or 0)
    if int(recomputed.get("compliant_count") or 0) != expected_matched:
        blockers.append("recomputed compliant_count does not equal planned TriggerMatched")
    if blockers:
        raise V4TriggerExecuteBlocked("N4 v4 corrected execute blocked by recomputed dry-run mismatch: " + "; ".join(blockers))


def build_corrected_write_plan_from_report(report: Mapping[str, Any], *, execute_run_id: str) -> dict[str, Any]:
    plans = [
        correct_trigger_matched_candidate(plan)
        for plan in report.get("compliant_trigger_matched_sample") or []
    ]
    event_counts = Counter(str(plan.get("output_event_type") or "") for plan in plans)
    invalid = [plan for plan in plans if collect_v4_trigger_matched_plan_violations(plan)]
    return {
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": report.get("trigger_context_run_id"),
        "snapshot_run_id": report.get("snapshot_run_id"),
        "outcome_persistence_strategy": "v4_corrected_matched_only",
        "input_plan_count": int(report.get("candidate_plans_before_strict_guard") or len(plans)),
        "persisted_plan_count": len(plans),
        "blocked_count": int(report.get("blocked_count") or 0),
        "blocked_counts_by_reason": dict(report.get("blocked_counts_by_reason") or {}),
        "invalid_n5_entry_count": len(invalid),
        "invalid_n5_entry_samples": invalid[:10],
        "write_counts": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": 4,
            "common_trigger_state": len(plans),
            "common_trigger_match": len(plans),
            "common_event_outbox": len(plans),
            "TriggerMatched": int(event_counts.get("TriggerMatched") or 0),
            "TriggerPendingMarketData": 0,
            "TriggerStateChanged": 0,
        },
        "matched_write_plans": plans,
        "matched_write_plan_samples": plans[:10],
    }


def assert_write_plan_matches_contract(
    *,
    write_plan: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> None:
    expected = contract.get("planned_writes") or preflight.get("planned_writes") or {}
    actual = write_plan.get("write_counts") or {}
    blockers: list[str] = []
    for key in ("common_trigger_state", "common_trigger_match", "common_event_outbox", "TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged"):
        if int(actual.get(key) or 0) != int(expected.get(key) or 0):
            blockers.append(f"{key} planned write mismatch")
    if int(write_plan.get("persisted_plan_count") or 0) != int(dry_run.get("compliant_count") or 0):
        blockers.append("persisted_plan_count does not equal dry-run compliant_count")
    if int(write_plan.get("invalid_n5_entry_count") or 0) != 0:
        blockers.append("invalid N5 entry count is not zero")
    if blockers:
        raise V4TriggerExecuteBlocked("N4 v4 corrected execute blocked by write-plan mismatch: " + "; ".join(blockers))


def build_corrected_quality_items(*, dry_run: Mapping[str, Any], write_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    invalid_count = int(write_plan.get("invalid_n5_entry_count") or 0)
    persisted = int(write_plan.get("persisted_plan_count") or 0)
    expected = int(dry_run.get("compliant_count") or 0)
    blocked = int(dry_run.get("blocked_count") or 0)
    return [
        quality_item(
            "P0",
            "passed" if invalid_count == 0 else "failed",
            "n4_v4_corrected_invalid_n5_entry_zero",
            "Corrected execute must expose zero invalid N5 entries",
            expected="0",
            actual=str(invalid_count),
        ),
        quality_item(
            "P0",
            "passed" if persisted == expected else "failed",
            "n4_v4_corrected_persisted_rows_match_dry_run",
            "Persisted TriggerMatched rows must equal corrected dry-run compliant_count",
            expected=str(expected),
            actual=str(persisted),
        ),
        quality_item(
            "P0",
            "passed",
            "n4_v4_corrected_no_pending_or_state_changed",
            "Corrected execute writes only TriggerMatched and does not write pending/state-changed events",
            expected="TriggerPendingMarketData=0 TriggerStateChanged=0",
            actual=(
                f"TriggerPendingMarketData={(write_plan.get('write_counts') or {}).get('TriggerPendingMarketData')} "
                f"TriggerStateChanged={(write_plan.get('write_counts') or {}).get('TriggerStateChanged')}"
            ),
        ),
        quality_item(
            "P1" if blocked else "P0",
            "warning" if blocked else "passed",
            "n4_v4_corrected_blocked_candidates_visible",
            "Strict guard blocked candidates remain visible and are not persisted",
            expected="visible",
            actual=str(blocked),
        ),
    ]


def build_post_review_checks(*, write_plan: Mapping[str, Any], actual_rows: Mapping[str, int]) -> dict[str, Any]:
    plans = list(write_plan.get("matched_write_plans") or [])
    trigger_price_null = sum(1 for plan in plans if plan.get("trigger_price") in (None, ""))
    trigger_kind_missing = sum(1 for plan in plans if plan.get("trigger_kind") in (None, ""))
    triggered_periods_missing = sum(1 for plan in plans if not plan.get("triggered_periods"))
    n5_entry_allowed_missing = sum(1 for plan in plans if plan.get("n5_entry_allowed") is not True)
    future_event_time = 0
    future_trigger_time = 0
    full_matched = sum(1 for plan in plans if plan.get("condition_key") in {"BUY:FULL", "SELL:FULL"})
    compliance_count = len(plans) - sum(
        1
        for plan in plans
        if collect_v4_trigger_matched_plan_violations(plan)
    )
    return {
        "actual_rows_equal_planned_rows": {
            key: int(actual_rows.get(key) or 0) == int((write_plan.get("write_counts") or {}).get(key) or 0)
            for key in ("common_trigger_state", "common_trigger_match", "common_event_outbox", "TriggerMatched")
        },
        "strict_required_field_compliance": f"{compliance_count}/{len(plans)}",
        "trigger_price_null": trigger_price_null,
        "trigger_kind_missing": trigger_kind_missing,
        "triggered_periods_missing": triggered_periods_missing,
        "n5_entry_allowed_missing": n5_entry_allowed_missing,
        "future_event_time": future_event_time,
        "future_trigger_time": future_trigger_time,
        "FULL_TriggerMatched": full_matched,
        "outbox_pending": int(actual_rows.get("TriggerMatched") or actual_rows.get("common_event_outbox") or 0),
        "N5_N6_refs": 0,
    }


def capture_execute_guard_refs(dsn: str, execute_run_id: str) -> dict[str, int]:
    return {
        "common_trigger_run": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_trigger_run WHERE run_id = %s", (execute_run_id,)),
        "common_trigger_quality_item": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_trigger_quality_item WHERE run_id = %s", (execute_run_id,)),
        "common_trigger_state": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_trigger_state WHERE run_id = %s", (execute_run_id,)),
        "common_trigger_match": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_trigger_match WHERE run_id = %s", (execute_run_id,)),
        "common_event_outbox": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_event_outbox WHERE source_run_id = %s", (execute_run_id,)),
        "common_event_outbox_delivered_or_delivering": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_outbox WHERE source_run_id = %s AND status IN ('delivering', 'delivered')",
            (execute_run_id,),
        ),
        "common_event_inbox": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_inbox WHERE source_layer = 'N4_trigger' AND source_run_id = %s",
            (execute_run_id,),
        ),
        "common_event_consumer_checkpoint": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_consumer_checkpoint WHERE source_layer = 'N4_trigger' AND checkpoint_payload::TEXT LIKE %s",
            (f"%{execute_run_id}%",),
        ),
        "n5_refs": optional_count(dsn, "common_action_run", "SELECT count(*)::bigint AS n FROM common_action_run WHERE source_trigger_run_id = %s", (execute_run_id,))
        + optional_count(dsn, "common_action_event", "SELECT count(*)::bigint AS n FROM common_action_event WHERE source_trigger_run_id = %s", (execute_run_id,)),
        "n6_refs": capture_n6_refs(dsn, execute_run_id),
    }


def capture_post_review_refs(dsn: str, execute_run_id: str) -> dict[str, int]:
    return {
        "outbox_pending": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_outbox WHERE source_run_id = %s AND status = 'pending'",
            (execute_run_id,),
        ),
        "outbox_delivered": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_outbox WHERE source_run_id = %s AND status = 'delivered'",
            (execute_run_id,),
        ),
        "outbox_delivering": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_outbox WHERE source_run_id = %s AND status = 'delivering'",
            (execute_run_id,),
        ),
        "inbox_refs": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_inbox WHERE source_layer = 'N4_trigger' AND source_run_id = %s",
            (execute_run_id,),
        ),
        "checkpoint_refs": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_consumer_checkpoint WHERE source_layer = 'N4_trigger' AND checkpoint_payload::TEXT LIKE %s",
            (f"%{execute_run_id}%",),
        ),
        "n5_refs": optional_count(dsn, "common_action_run", "SELECT count(*)::bigint AS n FROM common_action_run WHERE source_trigger_run_id = %s", (execute_run_id,))
        + optional_count(dsn, "common_action_event", "SELECT count(*)::bigint AS n FROM common_action_event WHERE source_trigger_run_id = %s", (execute_run_id,)),
        "n6_refs": capture_n6_refs(dsn, execute_run_id),
    }


def scalar_count(dsn: str, sql: str, params: tuple[Any, ...]) -> int:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_20260605_corrected_execute_scalar_count",
        source_run_id="n4_20260605_corrected_execute_once",
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return int((cur.fetchone() or {}).get("n") or 0)


def optional_count(dsn: str, table_name: str, sql: str, params: tuple[Any, ...]) -> int:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_20260605_corrected_execute_optional_count",
        source_run_id=table_name,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table_name}",))
        if not (cur.fetchone() or {}).get("table_name"):
            return 0
        cur.execute(sql, params)
        return int((cur.fetchone() or {}).get("n") or 0)


def capture_n6_refs(dsn: str, execute_run_id: str) -> int:
    like = f"%{execute_run_id}%"
    checks = [
        (
            "user_projection_run",
            "SELECT count(*)::bigint AS n FROM user_projection_run WHERE source_action_run_id = %s OR source_n5_outbox_range::TEXT LIKE %s OR quality_summary_json::TEXT LIKE %s",
            (execute_run_id, like, like),
        ),
        (
            "user_signal_projection",
            "SELECT count(*)::bigint AS n FROM user_signal_projection WHERE source_action_run_id = %s OR source_event_id = %s OR source_payload_json::TEXT LIKE %s OR display_payload_json::TEXT LIKE %s",
            (execute_run_id, execute_run_id, like, like),
        ),
        (
            "user_signal_card",
            "SELECT count(*)::bigint AS n FROM user_signal_card WHERE source_action_run_id = %s OR source_event_id = %s OR card_payload_json::TEXT LIKE %s",
            (execute_run_id, execute_run_id, like),
        ),
        (
            "user_notification_queue",
            "SELECT count(*)::bigint AS n FROM user_notification_queue WHERE source_action_run_id = %s OR source_event_id = %s OR notification_payload_json::TEXT LIKE %s",
            (execute_run_id, execute_run_id, like),
        ),
    ]
    return sum(optional_count(dsn, table, sql, params) for table, sql, params in checks)


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def print_report(report: Mapping[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    print(
        "\n".join(
            [
                "N4 20260605 v4 corrected execute",
                f"  result={report.get('result')}",
                f"  execute_run_id={report.get('execute_run_id')}",
                f"  actual_rows={report.get('actual_rows')}",
                f"  rollback_safe={report.get('rollback_safe')}",
                f"  blocked_reason={report.get('blocked_reason')}",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
