"""N5-R4 execute preflight and contract review.

The preflight verifies the N5 execute contract from current N4-R4 outbox rows
without consuming outbox rows and without writing inbox/checkpoint, action
facts, action events, N5 outbox rows, user projection, voice, sim, mobile,
true-trade, worker, or old-system state.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.action.query_audit_phase2 import audited_n5_readonly_plan_connect
from ashare_v3.action.consumer_dry_run import (
    DEFAULT_N5_1_CONSUMER_NAME,
    fetch_existing_checkpoints,
    fetch_existing_inbox_keys,
)
from ashare_v3.action.dry_run import HINT_SIGNAL_TYPES
from ashare_v3.action.preflight import ROW_COUNT_GUARD_TABLES, fetch_n4_outbox_rows, fetch_row_counts, fetch_trigger_run
from ashare_v3.action.run_once_dry_run import (
    ACTION_FACT_TABLES,
    DEFAULT_N5_R4_ACTION_RUN_ID,
    DEFAULT_N5_R4_BASELINE_REPORT_PATH,
    DEFAULT_N5_R4_JSON_REPORT_PATH,
    DEFAULT_N5_R4_TRIGGER_RUN_ID,
    build_action_consumer_run_once_dry_run_report_from_rows,
    count_by,
    load_baseline_report,
    write_json,
    write_text,
)
from ashare_v3.condition.basis import count_quality_severities, quality_item


DEFAULT_N5_R4_EXECUTE_PREFLIGHT_JSON_REPORT_PATH = "docs/N5_R4_action_execute_preflight_report.json"
DEFAULT_N5_R4_EXECUTE_PREFLIGHT_MD_REPORT_PATH = "docs/N5_R4_ACTION_EXECUTE_PREFLIGHT_REPORT.md"
ORDINARY_ACTION_SIGNAL_TYPES = ("B_BUY", "S_SELL")
CANONICAL_ACTION_OUTPUT_EVENT_TYPES = ("ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped")


def run_action_execute_preflight(
    *,
    dsn: str,
    trigger_run_id: str = DEFAULT_N5_R4_TRIGGER_RUN_ID,
    action_run_id: str = DEFAULT_N5_R4_ACTION_RUN_ID,
    consumer_name: str = DEFAULT_N5_1_CONSUMER_NAME,
    n4_execute_report_path: str = DEFAULT_N5_R4_BASELINE_REPORT_PATH,
    n5_dry_run_report_path: str = DEFAULT_N5_R4_JSON_REPORT_PATH,
    json_report_path: str = DEFAULT_N5_R4_EXECUTE_PREFLIGHT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_R4_EXECUTE_PREFLIGHT_MD_REPORT_PATH,
    expected_read_event_count: int = 26652,
    sample_limit: int = 80,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_execute_preflight",
        source_run_id=action_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        before_counts = fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES)
        trigger_run = fetch_trigger_run(cur, trigger_run_id)
        outbox_rows = fetch_n4_outbox_rows(cur, trigger_run_id)
        existing_inbox_keys = fetch_existing_inbox_keys(cur, consumer_name)
        existing_checkpoints = fetch_existing_checkpoints(cur, consumer_name)
        action_fact_columns = fetch_action_fact_columns(cur)
        after_counts = fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES)

    fresh_plan = build_action_consumer_run_once_dry_run_report_from_rows(
        trigger_run_id=trigger_run_id,
        action_run_id=action_run_id,
        consumer_name=consumer_name,
        trigger_run=trigger_run,
        outbox_rows=outbox_rows,
        existing_inbox_keys=existing_inbox_keys,
        existing_checkpoints=existing_checkpoints,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        baseline_report=load_baseline_report(n4_execute_report_path),
        baseline_report_path=n4_execute_report_path,
        stage="N5-R4-execute-preflight-plan",
        expected_read_event_count=expected_read_event_count,
        require_period_trigger_baseline_trace=True,
        sample_limit=max(sample_limit, expected_read_event_count),
    )
    report = build_execute_preflight_report(
        trigger_run_id=trigger_run_id,
        action_run_id=action_run_id,
        consumer_name=consumer_name,
        fresh_plan=fresh_plan,
        persisted_dry_run_report=load_baseline_report(n5_dry_run_report_path),
        n4_execute_report_path=n4_execute_report_path,
        n5_dry_run_report_path=n5_dry_run_report_path,
        action_fact_columns=action_fact_columns,
        started_at=started_at,
        finished_at=utc_now_iso(),
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_execute_preflight_report(report))
    return report


def build_execute_preflight_report(
    *,
    trigger_run_id: str,
    action_run_id: str,
    consumer_name: str,
    fresh_plan: Mapping[str, Any],
    persisted_dry_run_report: Mapping[str, Any] | None,
    n4_execute_report_path: str,
    n5_dry_run_report_path: str,
    action_fact_columns: Mapping[str, Sequence[str]],
    started_at: str,
    finished_at: str,
    json_report_path: str,
    markdown_report_path: str,
) -> dict[str, Any]:
    action_write_plan = list(fresh_plan.get("sample_action_write_plan") or [])
    full_action_write_plan = list(fresh_plan.get("action_write_plan") or [])
    if full_action_write_plan:
        action_write_rows = full_action_write_plan
    else:
        action_write_rows = action_write_plan
    event_mapping = summarize_event_type_mapping(action_write_rows, fresh_plan.get("action_write_plan_summary") or {})
    trace_mapping = summarize_trace_mapping(action_write_rows, fresh_plan.get("action_write_plan_summary") or {}, action_fact_columns)
    idempotency_checkpoint_plan = build_idempotency_checkpoint_plan(fresh_plan)
    dry_run_report_comparison = compare_persisted_dry_run_report(fresh_plan, persisted_dry_run_report, n5_dry_run_report_path)
    quality_items = build_quality_items(
        fresh_plan=fresh_plan,
        event_mapping=event_mapping,
        trace_mapping=trace_mapping,
        idempotency_checkpoint_plan=idempotency_checkpoint_plan,
        dry_run_report_comparison=dry_run_report_comparison,
    )
    severity_counts = count_quality_severities(quality_items)
    allow_execute = severity_counts["P0"] == 0
    return {
        "stage": "N5-R4-execute-preflight",
        "layer_role": "N5_action",
        "mode": "execute_preflight_contract_review",
        "execution_mode": "read_only_n4_outbox_execute_contract_review",
        "source_trigger_run_id": trigger_run_id,
        "action_run_id": action_run_id,
        "consumer_name": consumer_name,
        "n4_execute_report_path": n4_execute_report_path,
        "n5_dry_run_report_path": n5_dry_run_report_path,
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "started_at": started_at,
        "finished_at": finished_at,
        "fresh_plan_summary": summarize_fresh_plan(fresh_plan),
        "event_type_mapping": event_mapping,
        "trace_mapping": trace_mapping,
        "idempotency_checkpoint_plan": idempotency_checkpoint_plan,
        "dry_run_report_comparison": dry_run_report_comparison,
        "before_row_counts": fresh_plan.get("before_row_counts") or {},
        "after_row_counts": fresh_plan.get("after_row_counts") or {},
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "allow_execute": allow_execute,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "writes_performed": False,
            "n4_outbox_consumed": False,
            "common_event_inbox_updated": False,
            "consumer_checkpoint_updated": False,
            "action_fact_written": False,
            "action_event_written": False,
            "n5_outbox_written": False,
            "n6_user_layer_touched": False,
            "voice_touched": False,
            "sim_touched": False,
            "mobile_touched": False,
            "real_trade_touched": False,
            "market_data_pulled": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "passed": allow_execute,
    }


def summarize_event_type_mapping(
    action_write_plan: Sequence[Mapping[str, Any]],
    action_write_plan_summary: Mapping[str, Any],
) -> dict[str, Any]:
    planned_rows = [row for row in action_write_plan if row.get("plan_status") == "planned_action_fact"]
    by_signal_and_event: dict[str, dict[str, int]] = {}
    violations: list[dict[str, Any]] = []
    for row in planned_rows:
        signal_type = str(row.get("signal_type") or "")
        event_type = str(row.get("planned_output_event_type") or "")
        by_signal_and_event.setdefault(signal_type, {})
        by_signal_and_event[signal_type][event_type] = by_signal_and_event[signal_type].get(event_type, 0) + 1
        expected_event_type = expected_output_event_type(row)
        if expected_event_type and event_type != expected_event_type:
            violations.append(compact_mapping_row(row, expected_event_type))
    return {
        "rules": {
            "TriggerMatched": "action_fact plan",
            "TriggerPendingMarketData": "quality only, no action fact and no N5 outbox event",
            "BUY_HINT": "condition trace only; runtime signal_type remains B_BUY",
            "SELL_HINT": "condition trace only; runtime signal_type remains S_SELL",
            "B_BUY": "canonical buy runtime signal",
            "S_SELL": "canonical sell runtime signal",
            "canonical_outputs": ", ".join(CANONICAL_ACTION_OUTPUT_EVENT_TYPES),
        },
        "by_signal_type_and_output_event_type": {
            signal_type: dict(sorted(counts.items()))
            for signal_type, counts in sorted(by_signal_and_event.items())
        },
        "hint_signal_action_fact_count": 0,
        "hint_condition_trace_action_fact_count": sum(
            1
            for row in planned_rows
            if row.get("condition_key") in HINT_SIGNAL_TYPES
            or row.get("original_condition_key") in HINT_SIGNAL_TYPES
        ),
        "ordinary_signal_action_fact_count": sum(
            1 for row in planned_rows if row.get("signal_type") in ORDINARY_ACTION_SIGNAL_TYPES
        ),
        "pending_action_fact_plan_count": int(action_write_plan_summary.get("pending_action_fact_plan_count") or 0),
        "mapping_violation_count": len(violations),
        "mapping_violations_sample": violations[:20],
    }


def summarize_trace_mapping(
    action_write_plan: Sequence[Mapping[str, Any]],
    action_write_plan_summary: Mapping[str, Any],
    action_fact_columns: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    planned_rows = [row for row in action_write_plan if row.get("plan_status") == "planned_action_fact"]
    with_trace = [
        row for row in planned_rows
        if has_period_trigger_baseline_trace(row.get("source_market_trace"))
    ]
    dedicated_columns = {
        table_name: [
            column
            for column in columns
            if column in {"period_trigger_baseline_trace", "period_trigger_baseline_json"}
        ]
        for table_name, columns in action_fact_columns.items()
    }
    source_market_trace_missing_tables = [
        table_name for table_name, columns in action_fact_columns.items() if "source_market_trace" not in columns
    ]
    return {
        "rule": "period_trigger_baseline_trace is carried inside source_market_trace JSONB; no dedicated action fact column",
        "target_field": "source_market_trace.period_trigger_baseline_trace",
        "planned_action_fact_count": int(action_write_plan_summary.get("planned_action_fact_count") or len(planned_rows)),
        "trace_present_in_action_fact_plan_count": len(with_trace),
        "trace_missing_in_action_fact_plan_count": len(planned_rows) - len(with_trace),
        "source_market_trace_missing_tables": source_market_trace_missing_tables,
        "dedicated_period_trace_columns": dedicated_columns,
        "dedicated_period_trace_column_count": sum(len(columns) for columns in dedicated_columns.values()),
    }


def build_idempotency_checkpoint_plan(fresh_plan: Mapping[str, Any]) -> dict[str, Any]:
    consumer = fresh_plan.get("consumer_plan_summary") or {}
    key_recheck = fresh_plan.get("candidate_key_stability_recheck") or {}
    return {
        "consumer_name": fresh_plan.get("consumer_name"),
        "ordering": (fresh_plan.get("consumer_contract") or {}).get("ordering"),
        "dedup_keys": (fresh_plan.get("consumer_contract") or {}).get("dedup_keys"),
        "checkpoint_key": "consumer_name + partition_key + source_layer",
        "checkpoint_write_plan_count": consumer.get("checkpoint_write_plan_count"),
        "would_insert_inbox_count": consumer.get("would_insert_inbox_count"),
        "would_update_checkpoint_count": consumer.get("would_update_checkpoint_count"),
        "would_consume_outbox_count": consumer.get("would_consume_outbox_count"),
        "action_key_stable_on_recompute": key_recheck.get("stable_on_recompute"),
        "duplicate_action_key_count": key_recheck.get("duplicate_action_key_count"),
        "duplicate_dedup_key_count": key_recheck.get("duplicate_dedup_key_count"),
        "executed": False,
    }


def compare_persisted_dry_run_report(
    fresh_plan: Mapping[str, Any],
    persisted_dry_run_report: Mapping[str, Any] | None,
    n5_dry_run_report_path: str,
) -> dict[str, Any]:
    if not persisted_dry_run_report:
        return {
            "dry_run_report_path": n5_dry_run_report_path,
            "available": False,
            "matches_fresh_plan": False,
        }
    fresh_output = (fresh_plan.get("output_event_plan_summary") or {}).get("by_event_type") or {}
    persisted_output = (persisted_dry_run_report.get("output_event_plan_summary") or {}).get("by_event_type") or {}
    fresh_action = fresh_plan.get("action_write_plan_summary") or {}
    persisted_action = persisted_dry_run_report.get("action_write_plan_summary") or {}
    return {
        "dry_run_report_path": n5_dry_run_report_path,
        "available": True,
        "same_source_run_id": persisted_dry_run_report.get("source_trigger_run_id") == fresh_plan.get("source_trigger_run_id"),
        "same_read_event_count": (persisted_dry_run_report.get("consumer_plan_summary") or {}).get("read_event_count")
        == (fresh_plan.get("consumer_plan_summary") or {}).get("read_event_count"),
        "same_output_event_plan": dict(persisted_output) == dict(fresh_output),
        "same_planned_action_fact_count": persisted_action.get("planned_action_fact_count")
        == fresh_action.get("planned_action_fact_count"),
        "fresh_output_event_plan": fresh_output,
        "persisted_output_event_plan": persisted_output,
        "matches_fresh_plan": (
            persisted_dry_run_report.get("source_trigger_run_id") == fresh_plan.get("source_trigger_run_id")
            and (persisted_dry_run_report.get("consumer_plan_summary") or {}).get("read_event_count")
            == (fresh_plan.get("consumer_plan_summary") or {}).get("read_event_count")
            and dict(persisted_output) == dict(fresh_output)
            and persisted_action.get("planned_action_fact_count") == fresh_action.get("planned_action_fact_count")
        ),
    }


def build_quality_items(
    *,
    fresh_plan: Mapping[str, Any],
    event_mapping: Mapping[str, Any],
    trace_mapping: Mapping[str, Any],
    idempotency_checkpoint_plan: Mapping[str, Any],
    dry_run_report_comparison: Mapping[str, Any],
) -> list[dict[str, Any]]:
    source_run = fresh_plan.get("source_run_id_summary") or {}
    consumer = fresh_plan.get("consumer_plan_summary") or {}
    outbox = fresh_plan.get("outbox_summary") or {}
    expected_read_event_count = fresh_plan.get("expected_read_event_count")
    row_counts_unchanged = fresh_plan.get("before_row_counts") == fresh_plan.get("after_row_counts")
    side_effects = fresh_plan.get("side_effects") or {}
    return [
        quality_item(
            "P0",
            "passed"
            if expected_read_event_count is None
            or int(consumer.get("read_event_count") or 0) == int(expected_read_event_count)
            else "failed",
            "n5_r4_execute_preflight_read_event_count",
            "N5-R4 execute preflight must read exactly the current N4-R4 outbox row count",
            expected=str(expected_read_event_count) if expected_read_event_count is not None else "not enforced",
            actual=str(consumer.get("read_event_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if source_run.get("only_expected_source_run_id") else "failed",
            "n5_r4_execute_preflight_only_current_source_run",
            "N5-R4 execute preflight must only read the current N4-R4 source_run_id",
            expected=str(source_run.get("expected_source_run_id") or ""),
            actual=json.dumps(source_run.get("by_source_run_id") or {}, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed"
            if expected_read_event_count is None
            or int(expected_read_event_count) != 26652
            or (
                int(outbox.get("matched_count") or 0) == 8884
                and int(outbox.get("pending_count") or 0) == 17768
            )
            else "failed",
            "n5_r4_execute_preflight_n4_event_counts",
            "N5-R4 execute preflight must preserve N4-R4 TriggerMatched/Pending counts",
            expected="TriggerMatched=8884 TriggerPendingMarketData=17768",
            actual=f"TriggerMatched={outbox.get('matched_count') or 0} TriggerPendingMarketData={outbox.get('pending_count') or 0}",
        ),
        quality_item(
            "P0",
            "passed" if int(event_mapping.get("pending_action_fact_plan_count") or 0) == 0 else "failed",
            "n5_r4_execute_preflight_pending_quality_only",
            "TriggerPendingMarketData must remain quality only and generate no action fact",
            expected="0",
            actual=str(event_mapping.get("pending_action_fact_plan_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(event_mapping.get("mapping_violation_count") or 0) == 0 else "failed",
            "n5_r4_execute_preflight_event_type_mapping",
            "N5 execute preflight must map planned actions only to canonical ActionEligible/ActionBlocked/ActionExecuted/ActionSkipped events",
            expected="0 mapping violations",
            actual=str(event_mapping.get("mapping_violation_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(trace_mapping.get("trace_missing_in_action_fact_plan_count") or 0) == 0 else "failed",
            "n5_r4_execute_preflight_period_trace_in_action_fact_trace",
            "period_trigger_baseline_trace must be carried into the action fact trace JSON plan",
            expected="0 missing traces",
            actual=str(trace_mapping.get("trace_missing_in_action_fact_plan_count") or 0),
        ),
        quality_item(
            "P0",
            "passed"
            if not trace_mapping.get("source_market_trace_missing_tables")
            and int(trace_mapping.get("dedicated_period_trace_column_count") or 0) == 0
            else "failed",
            "n5_r4_execute_preflight_trace_not_split_columns",
            "period_trigger_baseline_trace must not be split into dedicated action fact columns",
            expected="source_market_trace exists and dedicated period trace columns=0",
            actual=json.dumps(
                {
                    "missing_source_market_trace_tables": trace_mapping.get("source_market_trace_missing_tables") or [],
                    "dedicated_period_trace_columns": trace_mapping.get("dedicated_period_trace_columns") or {},
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        quality_item(
            "P0",
            "passed"
            if idempotency_checkpoint_plan.get("action_key_stable_on_recompute")
            and int(idempotency_checkpoint_plan.get("duplicate_action_key_count") or 0) == 0
            and int(idempotency_checkpoint_plan.get("duplicate_dedup_key_count") or 0) == 0
            else "failed",
            "n5_r4_execute_preflight_idempotency_keys",
            "N5-R4 execute plan must have stable action_key/dedup_key and no duplicate keys",
            expected="stable unique keys",
            actual=json.dumps(idempotency_checkpoint_plan, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n5_r4_execute_preflight_row_counts_unchanged",
            "N5-R4 execute preflight must not change guarded row counts",
            expected="unchanged",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if not any(side_effects.get(key) for key in side_effects if key != "read_only_database_checks") else "failed",
            "n5_r4_execute_preflight_no_side_effects",
            "N5-R4 execute preflight must not write, consume, pull market data, start workers, or enter N6",
            expected="no side effects",
            actual=json.dumps(side_effects, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P1",
            "passed" if dry_run_report_comparison.get("matches_fresh_plan") else "failed",
            "n5_r4_execute_preflight_dry_run_report_current",
            "Persisted N5-R4 dry-run report should match the fresh execute preflight plan",
            expected="matches_fresh_plan=true",
            actual=json.dumps(dry_run_report_comparison, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P2",
            "warning" if int(outbox.get("synthetic_sample_event_count") or 0) > 0 else "passed",
            "n5_r4_execute_preflight_source_outbox_is_synthetic_sample",
            "Current N4-R4 outbox is synthetic/sample material",
            expected="development sample noted",
            actual=str(outbox.get("synthetic_sample_event_count") or 0),
        ),
    ]


def summarize_fresh_plan(fresh_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_trigger_run_id": fresh_plan.get("source_trigger_run_id"),
        "source_run_id_summary": fresh_plan.get("source_run_id_summary"),
        "outbox_summary": fresh_plan.get("outbox_summary"),
        "consumer_plan_summary": fresh_plan.get("consumer_plan_summary"),
        "action_write_plan_summary": fresh_plan.get("action_write_plan_summary"),
        "output_event_plan_summary": fresh_plan.get("output_event_plan_summary"),
        "period_trigger_baseline_trace_summary": fresh_plan.get("period_trigger_baseline_trace_summary"),
        "baseline_comparison": fresh_plan.get("baseline_comparison"),
    }


def expected_output_event_type(row: Mapping[str, Any]) -> str | None:
    signal_type = str(row.get("signal_type") or "")
    if signal_type not in ORDINARY_ACTION_SIGNAL_TYPES:
        return None
    action_state = str(row.get("action_state") or "")
    if action_state == "executed":
        return "ActionExecuted"
    if action_state == "blocked":
        return "ActionBlocked"
    if action_state in {"skipped", "expired"}:
        return "ActionSkipped"
    if action_state == "eligible":
        return "ActionEligible"
    return None


def compact_mapping_row(row: Mapping[str, Any], expected_event_type: str) -> dict[str, Any]:
    return {
        "source_trigger_event_id": row.get("source_trigger_event_id"),
        "source_trigger_match_id": row.get("source_trigger_match_id"),
        "asset_kind": row.get("asset_kind"),
        "identity_key": row.get("identity_key"),
        "signal_type": row.get("signal_type"),
        "actual_event_type": row.get("planned_output_event_type"),
        "expected_event_type": expected_event_type,
    }


def has_period_trigger_baseline_trace(source_market_trace: Any) -> bool:
    if not isinstance(source_market_trace, Mapping):
        return False
    trace = source_market_trace.get("period_trigger_baseline_trace")
    return isinstance(trace, Mapping) and bool(trace)


def fetch_action_fact_columns(cur: Any) -> dict[str, list[str]]:
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
        """,
        (list(ACTION_FACT_TABLES),),
    )
    output = {table_name: [] for table_name in ACTION_FACT_TABLES}
    for row in cur.fetchall():
        output[str(row["table_name"])].append(str(row["column_name"]))
    return output


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_execute_preflight_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    fresh = report["fresh_plan_summary"]
    event_mapping = report["event_type_mapping"]
    trace_mapping = report["trace_mapping"]
    idempotency = report["idempotency_checkpoint_plan"]
    side_effects = report["side_effects"]
    outbox = fresh["outbox_summary"]
    return "\n".join(
        [
            "# N5-R4 Action Execute Preflight Report",
            "",
            "## Summary",
            "",
            f"- stage: {report['stage']}",
            f"- layer_role: {report['layer_role']}",
            f"- source_trigger_run_id: {report['source_trigger_run_id']}",
            f"- action_run_id: {report['action_run_id']}",
            f"- consumer_name: {report['consumer_name']}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            f"- allow_execute: {report['allow_execute']}",
            "",
            "## Source Outbox",
            "",
            f"- read_event_count: {(fresh['consumer_plan_summary'] or {}).get('read_event_count')}",
            f"- source_run_id_summary: {fresh['source_run_id_summary']}",
            f"- by_event_type: {outbox.get('by_event_type')}",
            f"- by_signal_type: {outbox.get('by_signal_type')}",
            f"- BUY_HINT matched/pending/total: {outbox.get('buy_hint_matched_count')}/{outbox.get('buy_hint_pending_count')}/{outbox.get('buy_hint_count')}",
            f"- SELL_HINT matched/pending/total: {outbox.get('sell_hint_matched_count')}/{outbox.get('sell_hint_pending_count')}/{outbox.get('sell_hint_count')}",
            "",
            "## Event Type Mapping",
            "",
            f"- rules: {event_mapping['rules']}",
            f"- by_signal_type_and_output_event_type: {event_mapping['by_signal_type_and_output_event_type']}",
            f"- hint_signal_action_fact_count: {event_mapping['hint_signal_action_fact_count']}",
            f"- ordinary_signal_action_fact_count: {event_mapping['ordinary_signal_action_fact_count']}",
            f"- pending_action_fact_plan_count: {event_mapping['pending_action_fact_plan_count']}",
            f"- mapping_violation_count: {event_mapping['mapping_violation_count']}",
            "",
            "## Trace Mapping",
            "",
            f"- rule: {trace_mapping['rule']}",
            f"- target_field: {trace_mapping['target_field']}",
            f"- planned_action_fact_count: {trace_mapping['planned_action_fact_count']}",
            f"- trace_present_in_action_fact_plan_count: {trace_mapping['trace_present_in_action_fact_plan_count']}",
            f"- trace_missing_in_action_fact_plan_count: {trace_mapping['trace_missing_in_action_fact_plan_count']}",
            f"- source_market_trace_missing_tables: {trace_mapping['source_market_trace_missing_tables']}",
            f"- dedicated_period_trace_columns: {trace_mapping['dedicated_period_trace_columns']}",
            "",
            "## Idempotency / Checkpoint Plan",
            "",
            f"- ordering: {idempotency['ordering']}",
            f"- dedup_keys: {idempotency['dedup_keys']}",
            f"- checkpoint_key: {idempotency['checkpoint_key']}",
            f"- checkpoint_write_plan_count: {idempotency['checkpoint_write_plan_count']}",
            f"- would_insert_inbox_count: {idempotency['would_insert_inbox_count']}",
            f"- would_update_checkpoint_count: {idempotency['would_update_checkpoint_count']}",
            f"- would_consume_outbox_count: {idempotency['would_consume_outbox_count']}",
            f"- action_key_stable_on_recompute: {idempotency['action_key_stable_on_recompute']}",
            f"- duplicate_action_key_count: {idempotency['duplicate_action_key_count']}",
            f"- duplicate_dedup_key_count: {idempotency['duplicate_dedup_key_count']}",
            f"- executed: {idempotency['executed']}",
            "",
            "## Row Count Guards",
            "",
            f"- before_row_counts: {report['before_row_counts']}",
            f"- after_row_counts: {report['after_row_counts']}",
            "",
            "## Boundary Confirmation",
            "",
            f"- writes_performed: {side_effects['writes_performed']}",
            f"- n4_outbox_consumed: {side_effects['n4_outbox_consumed']}",
            f"- common_event_inbox_updated: {side_effects['common_event_inbox_updated']}",
            f"- consumer_checkpoint_updated: {side_effects['consumer_checkpoint_updated']}",
            f"- action_fact_written: {side_effects['action_fact_written']}",
            f"- action_event_written: {side_effects['action_event_written']}",
            f"- n5_outbox_written: {side_effects['n5_outbox_written']}",
            f"- n6_user_layer_touched: {side_effects['n6_user_layer_touched']}",
            f"- voice_touched: {side_effects['voice_touched']}",
            f"- sim_touched: {side_effects['sim_touched']}",
            f"- mobile_touched: {side_effects['mobile_touched']}",
            f"- real_trade_touched: {side_effects['real_trade_touched']}",
            f"- market_data_pulled: {side_effects['market_data_pulled']}",
            f"- worker_started: {side_effects['worker_started']}",
            f"- old_system_touched: {side_effects['old_system_touched']}",
            "",
            "## Decision",
            "",
            f"- allow_execute: {report['allow_execute']}",
            "- This preflight did not execute database writes or consume outbox rows.",
        ]
    )
