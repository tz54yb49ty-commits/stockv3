#!/usr/bin/env python3
"""Run V3-only 20260612 N4 full-day trigger replay once.

This replay keeps the existing N4 action-confirmation matcher rules, but the
dry-run path is state-machine aware: it emits TriggerMatched only for new action
entries, TriggerPendingMarketData only when evidence is insufficient, and
TriggerStateChanged for material trigger-state changes such as deactivation or
period/projection changes.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market import v3_full_day_replay_plan as replay_plan
from ashare_v3.trigger.action_confirmation_metric_execute import (
    ActionConfirmationMetricExecuteError,
    assert_action_confirmation_metric_execute_confirmed,
    insert_action_confirmation_metric_trigger_run,
    insert_execute_quality_items,
    write_action_confirmation_metric_outcomes_with_cursor,
)
from ashare_v3.trigger.action_confirmation_metric_matcher import (
    build_action_confirmation_metric_execute_rollback_sql,
    build_action_confirmation_metric_preflight_report,
    capture_action_confirmation_metric_execute_baseline,
    evaluate_action_confirmation_metric_candidate,
    fetch_action_confirmation_metric_rows,
    fetch_context_rows,
    metric_candidate_signal_for_context,
    metrics_by_identity_time_series,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_trigger_connect
from ashare_v3.trigger.standard_trigger_execute import assert_no_existing_execute_outputs
from ashare_v3.trigger.worker_state_transition import build_transition_event_plans, trigger_state_key
from psycopg.rows import dict_row

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


DRY_RUN_JSON = "docs/V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_DRY_RUN.json"
DRY_RUN_MD = "docs/V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_DRY_RUN.md"
PREFLIGHT_JSON = "docs/V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_PREFLIGHT.json"
PREFLIGHT_MD = "docs/V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_PREFLIGHT.md"
CONTRACT_JSON = "docs/V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_CONTRACT.json"
CONTRACT_MD = "docs/V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_CONTRACT.md"
EXECUTE_JSON = "docs/V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_EXECUTE_REPORT.json"
EXECUTE_MD = "docs/V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_EXECUTE_REPORT.md"
ROLLBACK_SQL = "sql/V3_20260612_n4_full_day_trigger_replay_rollback.sql"
DEFAULT_N4_FULL_DAY_REPLAY_RUN_ID = "v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3"
DEFAULT_N5_FULL_DAY_REPLAY_CONSUMER_NAME = "v3_n5_action_replay_20260612_state_machine_consumer_v3"
READY_BUT_NOT_SATISFIED_REASONS = {
    "metric_ready_but_side_trigger_evidence_not_satisfied",
    "metric_ready_but_side_projection_not_satisfied",
    "metric_ready_but_formal_trigger_not_satisfied",
}
FORMAL_PERIOD_VALUES = {"Y", "Q", "M", "W", "D"}
KNOWN_POLLUTED_SAMPLE_IDENTITY_KEY = "stock:SZ:002056"
KNOWN_POLLUTED_SAMPLE_CONDITION_KEY = "BUY:M,W,D"


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def is_hint_plan(plan: Mapping[str, Any]) -> bool:
    condition_key = str(plan.get("condition_key") or "").upper()
    return condition_key in {"BUY_HINT", "SELL_HINT"} or str(plan.get("trigger_kind") or "") == "hint"


def list_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def formal_period_fields(plan: Mapping[str, Any]) -> list[str]:
    values = []
    values.extend(list_field(plan.get("triggered_periods")))
    values.extend(list_field(plan.get("all_trigger_periods")))
    values.extend(list_field(plan.get("primary_trigger_period")))
    return values


def iter_full_day_plans(
    *,
    context_rows: Sequence[Mapping[str, Any]],
    metric_lookup: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
) -> Iterable[dict[str, Any]]:
    """Yield full-day N4 transition plans.

    The matcher is still evaluated for every minute, but a persisted
    TriggerMatched is emitted only when a context transitions into matched.
    Sustained true minutes and material changes are represented by the
    state-machine output, not by repeated action-entry TriggerMatched events.
    """

    previous_states: dict[str, dict[str, Any]] = {}
    for row in context_rows:
        if row.get("run_id") != trigger_context_run_id:
            continue
        legacy_signal = metric_candidate_signal_for_context(row)
        if not legacy_signal:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        metrics = metric_lookup.get(key) or []
        if not metrics:
            plan = evaluate_action_confirmation_metric_candidate(
                row=row,
                metric=None,
                legacy_signal_type=legacy_signal,
                projection_run_id=projection_run_id,
                source_condition_run_id=source_condition_run_id,
                source_subscription_run_id=source_subscription_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
                for_trade_date=for_trade_date,
            )
            plan["replay_mode"] = "full_day_metric_time_series"
            yield from _state_machine_plans_for_metric_plan(
                plan,
                previous_states=previous_states,
                for_trade_date=for_trade_date,
            )
            continue
        for metric in metrics:
            plan = evaluate_action_confirmation_metric_candidate(
                row=row,
                metric=metric,
                legacy_signal_type=legacy_signal,
                projection_run_id=projection_run_id,
                source_condition_run_id=source_condition_run_id,
                source_subscription_run_id=source_subscription_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
                for_trade_date=for_trade_date,
            )
            plan["replay_mode"] = "full_day_metric_time_series"
            yield from _state_machine_plans_for_metric_plan(
                plan,
                previous_states=previous_states,
                for_trade_date=for_trade_date,
            )


def _state_machine_plans_for_metric_plan(
    plan: Mapping[str, Any],
    *,
    previous_states: dict[str, dict[str, Any]],
    for_trade_date: str,
) -> list[dict[str, Any]]:
    evaluation = _state_machine_evaluation(plan, for_trade_date=for_trade_date)
    state_key = str(evaluation["trigger_state_key"])
    previous_state = previous_states.get(state_key)
    if evaluation.get("output_event_type") == "TriggerMatched" and previous_state and previous_state.get("current_status") == "matched":
        evaluation["new_trigger_fact"] = False
    transition_plans = build_transition_event_plans(
        previous_state=previous_state,
        current_evaluation=evaluation,
        source_event_id=str(evaluation.get("source_event_id") or ""),
        trade_date=for_trade_date,
    )
    previous_states[state_key] = _state_snapshot(evaluation)
    output: list[dict[str, Any]] = []
    for item in transition_plans:
        normalized = dict(item)
        normalized["trigger_state_key"] = state_key
        normalized["replay_mode"] = plan.get("replay_mode") or "full_day_metric_time_series"
        event_type = str(normalized.get("output_event_type") or "")
        if event_type == "TriggerStateChanged":
            normalized["plan_status"] = "state_changed"
            normalized["state_transition"] = normalized.get("state_change_reason")
        elif event_type == "TriggerMatched":
            normalized["plan_status"] = "would_trigger"
            normalized["state_transition"] = "activated" if previous_state is None or previous_state.get("current_status") != "matched" else "matched_changed"
        elif event_type == "TriggerPendingMarketData":
            normalized["plan_status"] = "would_pending"
            normalized["state_transition"] = "pending_market_data"
        output.append(normalized)
    return output


def _state_machine_evaluation(plan: Mapping[str, Any], *, for_trade_date: str) -> dict[str, Any]:
    evaluation = dict(plan)
    evaluation["trade_date"] = for_trade_date
    evaluation["trigger_state_key"] = trigger_state_key(
        trade_date=for_trade_date,
        asset_kind=str(evaluation.get("asset_kind") or ""),
        identity_key=str(evaluation.get("identity_key") or ""),
        direction=str(evaluation.get("direction") or ""),
        signal_type=str(evaluation.get("signal_type") or ""),
        condition_key=str(evaluation.get("condition_key") or ""),
    )
    output_event_type = evaluation.get("output_event_type")
    if output_event_type == "TriggerMatched":
        evaluation["current_status"] = "matched"
        evaluation["trigger_live"] = True
        return evaluation
    if output_event_type == "TriggerPendingMarketData" and not _is_ready_but_not_satisfied(evaluation):
        evaluation["current_status"] = "pending_market_data"
        evaluation["trigger_live"] = False
        evaluation["n5_entry_allowed"] = False
        evaluation["new_trigger_fact"] = False
        return evaluation
    evaluation["output_event_type"] = None
    evaluation["current_status"] = "inactive"
    evaluation["trigger_live"] = False
    evaluation["n5_entry_allowed"] = False
    evaluation["new_trigger_fact"] = False
    evaluation["primary_trigger_period"] = None
    evaluation["all_trigger_periods"] = []
    evaluation["projection_30m_flag"] = False
    evaluation["projection_30m_type"] = "none"
    evaluation["trigger_mark_candidate"] = evaluation.get("trigger_mark_candidate") or "normal"
    return evaluation


def _is_ready_but_not_satisfied(plan: Mapping[str, Any]) -> bool:
    reason = str(plan.get("not_ready_reason") or "")
    return reason in READY_BUT_NOT_SATISFIED_REASONS or (
        str(plan.get("plan_status") or "") == "would_pending"
        and bool(plan.get("metric_ready"))
        and reason.startswith("metric_ready_but_")
    )


def _state_snapshot(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": evaluation.get("trade_date"),
        "asset_kind": evaluation.get("asset_kind"),
        "identity_key": evaluation.get("identity_key"),
        "direction": evaluation.get("direction"),
        "signal_type": evaluation.get("signal_type"),
        "condition_key": evaluation.get("condition_key"),
        "current_status": evaluation.get("current_status"),
        "trigger_live": bool(evaluation.get("trigger_live")),
        "primary_trigger_period": evaluation.get("primary_trigger_period"),
        "all_trigger_periods": list(evaluation.get("all_trigger_periods") or []),
        "projection_30m_flag": bool(evaluation.get("projection_30m_flag")),
        "projection_30m_type": evaluation.get("projection_30m_type") or "none",
        "trigger_mark_candidate": evaluation.get("trigger_mark_candidate") or "normal",
        "data_quality_status": evaluation.get("data_quality_status") or "passed",
        "source_trace_hash": evaluation.get("source_trace_hash"),
    }


def _counter_to_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(value) for key, value in sorted(counter.items()) if key}


def summarize_full_day_plans(plans: Iterable[Mapping[str, Any]], *, sample_limit: int = 40) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    counters: dict[str, Counter[str]] = {
        "by_asset_kind": Counter(),
        "would_trigger_by_asset_kind": Counter(),
        "would_pending_by_asset_kind": Counter(),
        "state_changed_by_asset_kind": Counter(),
        "by_signal_type": Counter(),
        "would_trigger_by_signal_type": Counter(),
        "would_pending_by_signal_type": Counter(),
        "state_changed_by_signal_type": Counter(),
        "by_trigger_mark_candidate": Counter(),
        "would_trigger_by_trigger_mark_candidate": Counter(),
        "would_pending_by_trigger_mark_candidate": Counter(),
        "state_changed_by_trigger_mark_candidate": Counter(),
        "by_output_event_type": Counter(),
        "by_not_ready_reason": Counter(),
        "by_state_change_reason": Counter(),
    }
    totals = Counter()
    state_keys: set[str] = set()
    samples = {
        "would_trigger_plans": [],
        "would_pending_plans": [],
        "state_changed_plans": [],
        "quality_only_plans": [],
        "no_op_samples": [],
    }
    for plan in plans:
        status = str(plan.get("plan_status") or "")
        event_type = str(plan.get("output_event_type") or "")
        asset_kind = str(plan.get("asset_kind") or "")
        signal_type = str(plan.get("signal_type") or "")
        trigger_mark = str(plan.get("trigger_mark_candidate") or "")
        not_ready = str(plan.get("not_ready_reason") or "")
        condition_key = str(plan.get("condition_key") or "")
        identity_key = str(plan.get("identity_key") or "")
        trigger_period = str(plan.get("trigger_period") or "")
        hint_plan = is_hint_plan(plan)
        formal_values = formal_period_fields(plan)
        totals["candidate_count"] += 1
        if not hint_plan and trigger_period == "30m":
            totals["ordinary_trigger_period_30m_count"] += 1
        if any(value == "30m" for value in formal_values):
            totals["formal_period_arrays_contains_30m_count"] += 1
        if not hint_plan and event_type == "TriggerMatched" and (trigger_period == "30m" or any(value == "30m" for value in formal_values)):
            totals["ordinary_formal_30m_contamination_count"] += 1
        if not hint_plan and event_type == "TriggerMatched" and not any(value in FORMAL_PERIOD_VALUES for value in list_field(plan.get("triggered_periods"))):
            totals["ordinary_formal_missing_proof_trigger_matched_count"] += 1
        if not hint_plan and not_ready == "formal_trigger_period_proof_missing":
            totals["ordinary_formal_missing_proof_pending_count"] += 1
        if hint_plan and event_type == "TriggerMatched" and trigger_period == "30m":
            totals["hint_30m_trigger_matched_count"] += 1
        if identity_key == KNOWN_POLLUTED_SAMPLE_IDENTITY_KEY and condition_key == KNOWN_POLLUTED_SAMPLE_CONDITION_KEY:
            totals["known_polluted_sample_candidate_count"] += 1
            if event_type == "TriggerMatched":
                totals["known_polluted_sample_trigger_matched_count"] += 1
                if trigger_period == "30m" or any(value == "30m" for value in formal_values):
                    totals["known_polluted_sample_30m_contamination_count"] += 1
                if not any(value in FORMAL_PERIOD_VALUES for value in list_field(plan.get("triggered_periods"))):
                    totals["known_polluted_sample_missing_formal_proof_trigger_matched_count"] += 1
            if not_ready == "formal_trigger_period_proof_missing":
                totals["known_polluted_sample_formal_missing_pending_count"] += 1
        if event_type:
            state_key = str(plan.get("trigger_state_key") or "")
            if state_key:
                state_keys.add(state_key)
        counters["by_asset_kind"][asset_kind] += 1
        counters["by_signal_type"][signal_type] += 1
        counters["by_trigger_mark_candidate"][trigger_mark] += 1
        if event_type:
            counters["by_output_event_type"][event_type] += 1
        if plan.get("state_change_reason"):
            counters["by_state_change_reason"][str(plan.get("state_change_reason"))] += 1
        if not_ready:
            counters["by_not_ready_reason"][not_ready] += 1
        if plan.get("metric_ready") is True:
            totals["metric_ready_candidate_count"] += 1
        if not_ready in {"metric_row_missing", "metric_not_ready"}:
            totals["metric_missing_or_not_ready_candidate_count"] += 1
        if status == "would_trigger":
            totals["would_trigger_count"] += 1
            counters["would_trigger_by_asset_kind"][asset_kind] += 1
            counters["would_trigger_by_signal_type"][signal_type] += 1
            counters["would_trigger_by_trigger_mark_candidate"][trigger_mark] += 1
            if len(samples["would_trigger_plans"]) < sample_limit:
                samples["would_trigger_plans"].append(dict(plan))
        elif status == "would_pending":
            totals["would_pending_count"] += 1
            counters["would_pending_by_asset_kind"][asset_kind] += 1
            counters["would_pending_by_signal_type"][signal_type] += 1
            counters["would_pending_by_trigger_mark_candidate"][trigger_mark] += 1
            if len(samples["would_pending_plans"]) < sample_limit:
                samples["would_pending_plans"].append(dict(plan))
        elif status == "state_changed":
            totals["state_changed_count"] += 1
            counters["state_changed_by_asset_kind"][asset_kind] += 1
            counters["state_changed_by_signal_type"][signal_type] += 1
            counters["state_changed_by_trigger_mark_candidate"][trigger_mark] += 1
            if len(samples["state_changed_plans"]) < sample_limit:
                samples["state_changed_plans"].append(dict(plan))
        elif status == "quality_only":
            totals["quality_only_count"] += 1
            if len(samples["quality_only_plans"]) < sample_limit:
                samples["quality_only_plans"].append(dict(plan))
        else:
            if len(samples["no_op_samples"]) < sample_limit:
                samples["no_op_samples"].append(dict(plan))
    summary = {key: int(value) for key, value in totals.items()}
    for key, counter in counters.items():
        summary[key] = _counter_to_dict(counter)
    summary.setdefault("would_trigger_count", 0)
    summary.setdefault("would_pending_count", 0)
    summary.setdefault("state_changed_count", 0)
    summary.setdefault("quality_only_count", 0)
    summary.setdefault("candidate_count", 0)
    summary.setdefault("ordinary_trigger_period_30m_count", 0)
    summary.setdefault("formal_period_arrays_contains_30m_count", 0)
    summary.setdefault("ordinary_formal_30m_contamination_count", 0)
    summary.setdefault("ordinary_formal_missing_proof_trigger_matched_count", 0)
    summary.setdefault("ordinary_formal_missing_proof_pending_count", 0)
    summary.setdefault("hint_30m_trigger_matched_count", 0)
    summary.setdefault("known_polluted_sample_candidate_count", 0)
    summary.setdefault("known_polluted_sample_trigger_matched_count", 0)
    summary.setdefault("known_polluted_sample_30m_contamination_count", 0)
    summary.setdefault("known_polluted_sample_missing_formal_proof_trigger_matched_count", 0)
    summary.setdefault("known_polluted_sample_formal_missing_pending_count", 0)
    summary["state_key_count"] = len(state_keys)
    summary["persisted_write_policy"] = (
        "state-machine replay dry-run; TriggerMatched is N5 entry only, "
        "TriggerPendingMarketData and TriggerStateChanged are non-entry events"
    )
    return summary, samples


def build_quality_items(*, trigger_run: Mapping[str, Any], context_rows: Sequence[Mapping[str, Any]], metric_rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        quality_item(
            "P0",
            "passed" if trigger_run.get("status") == "passed" else "failed",
            "v3_n4_full_day_context_run_passed",
            "N4 full-day replay must bind a passed localized context run",
            expected="passed",
            actual=str(trigger_run.get("status")),
        ),
        quality_item(
            "P0",
            "passed" if context_rows else "failed",
            "v3_n4_full_day_context_rows_available",
            "N4 full-day replay must have localized context rows",
            expected=">0",
            actual=str(len(context_rows)),
        ),
        quality_item(
            "P0",
            "passed" if metric_rows else "failed",
            "v3_n4_full_day_metric_rows_available",
            "N4 full-day replay must consume N3 full-day metric rows",
            expected=">0",
            actual=str(len(metric_rows)),
        ),
        quality_item(
            "P0",
            "passed",
            "v3_n4_full_day_no_raw_minute_read",
            "N4 replay consumes N3 metric facts and does not assemble raw minute indicators",
        ),
        quality_item(
            "P0",
            "passed",
            "v3_n4_full_day_no_n5_n6",
            "N4 replay does not enter N5/N6, voice, mobile, sim, position or trade",
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("ordinary_formal_30m_contamination_count") or 0) == 0 else "failed",
            "v3_n4_fixed_replay_ordinary_formal_30m_contamination_zero",
            "Ordinary BUY/SELL/FULL TriggerMatched must not use 30m as formal trigger period",
            expected="0",
            actual=str(summary.get("ordinary_formal_30m_contamination_count")),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("formal_period_arrays_contains_30m_count") or 0) == 0 else "failed",
            "v3_n4_fixed_replay_formal_period_arrays_30m_zero",
            "triggered_periods/all_trigger_periods/primary_trigger_period must not contain 30m",
            expected="0",
            actual=str(summary.get("formal_period_arrays_contains_30m_count")),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("ordinary_formal_missing_proof_trigger_matched_count") or 0) == 0 else "failed",
            "v3_n4_fixed_replay_ordinary_missing_formal_proof_matched_zero",
            "Ordinary formal candidates missing explicit N4 formal proof must not become TriggerMatched",
            expected="0",
            actual=str(summary.get("ordinary_formal_missing_proof_trigger_matched_count")),
        ),
        quality_item(
            "P0",
            "passed"
            if int(summary.get("known_polluted_sample_30m_contamination_count") or 0) == 0
            and int(summary.get("known_polluted_sample_missing_formal_proof_trigger_matched_count") or 0) == 0
            else "failed",
            "v3_n4_fixed_replay_known_polluted_sample_not_fabricated",
            "Known polluted stock:SZ:002056 BUY:M,W,D sample may match only with real formal proof, never by 30m marker or empty proof",
            expected="30m_contamination=0;missing_formal_proof_matched=0",
            actual=(
                f"trigger_matched={summary.get('known_polluted_sample_trigger_matched_count')};"
                f"30m_contamination={summary.get('known_polluted_sample_30m_contamination_count')};"
                f"missing_formal_proof_matched={summary.get('known_polluted_sample_missing_formal_proof_trigger_matched_count')}"
            ),
        ),
        quality_item(
            "P1",
            "warning" if int(summary.get("would_pending_count") or 0) else "passed",
            "v3_n4_full_day_non_matched_retained_in_dry_run",
            "Non-matched/pending candidate reasons are retained in dry-run and not persisted as N5 entry",
            expected="N5 entry only from TriggerMatched",
            actual=f"would_pending={summary.get('would_pending_count')}",
        ),
    ]


def build_report_and_artifacts(
    *,
    dsn: str,
    sample_limit: int,
    execute_run_id: str = DEFAULT_N4_FULL_DAY_REPLAY_RUN_ID,
    dry_run_json_path: str = DRY_RUN_JSON,
    dry_run_markdown_path: str = DRY_RUN_MD,
    contract_json_path: str = CONTRACT_JSON,
    contract_markdown_path: str = CONTRACT_MD,
    preflight_json_path: str = PREFLIGHT_JSON,
    preflight_markdown_path: str = PREFLIGHT_MD,
    rollback_sql_path: str = ROLLBACK_SQL,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[tuple[str, str], Sequence[Mapping[str, Any]]], Mapping[str, Any]]:
    trigger_context_run_id = replay_plan.TRIGGER_CONTEXT_RUN_ID
    projection_run_id = replay_plan.FULL_DAY_METRIC_RUN_ID
    source_condition_run_id = replay_plan.SOURCE_CONDITION_RUN_ID
    source_subscription_run_id = replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID
    source_snapshot_run_id = replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID
    for_trade_date = replay_plan.FOR_TRADE_DATE
    context_rows, trigger_run = fetch_context_rows(dsn, trigger_context_run_id)
    metric_rows = fetch_action_confirmation_metric_rows(
        dsn,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
    )
    metric_lookup = metrics_by_identity_time_series(metric_rows, projection_run_id=projection_run_id)
    summary, samples = summarize_full_day_plans(
        iter_full_day_plans(
            context_rows=context_rows,
            metric_lookup=metric_lookup,
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_snapshot_run_id=source_snapshot_run_id,
            for_trade_date=for_trade_date,
        ),
        sample_limit=sample_limit,
    )
    quality_items = build_quality_items(trigger_run=trigger_run, context_rows=context_rows, metric_rows=metric_rows, summary=summary)
    quality_counts = count_quality_severities(quality_items)
    report = {
        "stage": "V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_DRY_RUN",
        "result": "DRY_RUN_PASS" if quality_counts["P0"] == 0 else "DRY_RUN_BLOCKED",
        "layer_role": "N4_trigger",
        "trigger_context_run_id": trigger_context_run_id,
        "source_trigger_run_id": execute_run_id,
        "trigger_run_id": execute_run_id,
        "projection_run_id": projection_run_id,
        "metric_run_id": projection_run_id,
        "projection_schema_version": replay_plan.FULL_DAY_METRIC_SCHEMA_VERSION,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": source_snapshot_run_id,
        "for_trade_date": for_trade_date,
        "input_summary": {
            "context_rows": len(context_rows),
            "metric_rows": len(metric_rows),
            "metric_identities": len(metric_lookup),
        },
        "matcher_contract": {
            "uses_existing_n4_rules": True,
            "uses_state_machine_output": True,
            "state_key": "trade_date|asset_kind|identity_key|direction|signal_type|condition_key",
            "reads_only_n3_action_confirmation_metric_facts": True,
            "reads_raw_minute_tables": False,
            "writes_database": False,
            "n4_decides_final_action_mark": False,
            "n5_entry_event": "TriggerMatched",
            "ordinary_formal_30m_contamination_forbidden": True,
            "ordinary_formal_trigger_requires_explicit_period_proof": True,
            "hint_30m_projection_trigger_remains_legal": True,
        },
        "consumer_strategy": {
            "uses_dedicated_consumer": True,
            "dedicated_consumer_name": DEFAULT_N5_FULL_DAY_REPLAY_CONSUMER_NAME,
            "source_trigger_run_id": execute_run_id,
            "metric_run_id": projection_run_id,
            "purpose": "20260612 full-day N5 action replay against superseding N4 run",
        },
        "summary": summary,
        "plans": {
            "output_plan_count": int(summary.get("would_trigger_count") or 0)
            + int(summary.get("would_pending_count") or 0)
            + int(summary.get("state_changed_count") or 0),
            **samples,
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "dry_run_only": True,
            "database_written": False,
            "n5_n6_entered": False,
            "outbox_consumed": False,
            "worker_started": False,
            "voice_mobile_sim_trade_touched": False,
        },
    }
    preflight = build_action_confirmation_metric_preflight_report(report)
    baseline = capture_action_confirmation_metric_execute_baseline(dsn, execute_run_id)
    rollback_sql = build_action_confirmation_metric_execute_rollback_sql(execute_run_id)
    contract = {
        "stage": "V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_CONTRACT",
        "result": "CONTRACT_PASS" if report["result"] == "DRY_RUN_PASS" and baseline_zero(baseline) else "CONTRACT_BLOCKED",
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": source_snapshot_run_id,
        "for_trade_date": for_trade_date,
        "write_policy": "state-machine output: TriggerMatched action-entry; TriggerPendingMarketData/TriggerStateChanged non-entry",
        "strict_guards": {
            "ordinary_formal_30m_contamination": int(summary.get("ordinary_formal_30m_contamination_count") or 0),
            "formal_period_arrays_contains_30m": int(summary.get("formal_period_arrays_contains_30m_count") or 0),
            "ordinary_missing_formal_proof_trigger_matched": int(
                summary.get("ordinary_formal_missing_proof_trigger_matched_count") or 0
            ),
            "known_polluted_sample_trigger_matched": int(summary.get("known_polluted_sample_trigger_matched_count") or 0),
            "hint_30m_trigger_matched": int(summary.get("hint_30m_trigger_matched_count") or 0),
        },
        "expected_writes": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": "quality_items",
            "common_trigger_state": int(summary.get("state_key_count") or 0),
            "common_trigger_match": int(summary.get("would_trigger_count") or 0),
            "common_event_outbox": int(summary.get("would_trigger_count") or 0)
            + int(summary.get("would_pending_count") or 0)
            + int(summary.get("state_changed_count") or 0),
            "TriggerMatched": int(summary.get("would_trigger_count") or 0),
            "TriggerPendingMarketData": int(summary.get("would_pending_count") or 0),
            "TriggerStateChanged": int(summary.get("state_changed_count") or 0),
        },
        "baseline": baseline,
        "rollback_sql": rollback_sql_path,
        "forbidden_scope": {
            "consume_n3_outbox": False,
            "write_inbox_checkpoint": False,
            "enter_n5_n6": False,
            "voice_mobile_sim_trade": False,
        },
    }
    final_preflight = {
        "stage": "V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_PREFLIGHT",
        "result": "PREFLIGHT_PASS" if contract["result"] == "CONTRACT_PASS" else "PREFLIGHT_BLOCKED",
        "execute_authorized": False,
        "execute_run_id": execute_run_id,
        "blockers": [] if contract["result"] == "CONTRACT_PASS" else ["contract_or_baseline_blocked"],
        "planned_writes": contract["expected_writes"],
        "baseline": baseline,
        "quality": report["quality"],
        "rollback_sql": rollback_sql_path,
    }
    write_json(dry_run_json_path, report)
    write_text(dry_run_markdown_path, format_report(report))
    write_json(preflight_json_path, final_preflight)
    write_text(preflight_markdown_path, format_preflight(final_preflight))
    write_json(contract_json_path, contract)
    write_text(contract_markdown_path, format_contract(contract))
    write_text(rollback_sql_path, rollback_sql)
    return report, preflight, contract, final_preflight, context_rows, metric_lookup, trigger_run


def baseline_zero(baseline: Mapping[str, int]) -> bool:
    return all(int(value or 0) == 0 for value in baseline.values())


def execute_replay(
    *,
    dsn: str,
    execute_run_id: str = DEFAULT_N4_FULL_DAY_REPLAY_RUN_ID,
    context_rows: Sequence[Mapping[str, Any]],
    metric_lookup: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    trigger_run: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
    batch_size: int,
    progress_every: int,
) -> dict[str, int]:
    projection_run = {
        "projection_run_id": replay_plan.FULL_DAY_METRIC_RUN_ID,
        "source_snapshot_run_id": replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
        "source_subscription_run_id": replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
    }
    counts = Counter()
    with audited_n4_trigger_connect(
        dsn,
        stage_id="v3_20260612_n4_full_day_trigger_replay_execute",
        source_run_id=execute_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            assert_no_existing_execute_outputs(cur, execute_run_id)
            insert_action_confirmation_metric_trigger_run(
                cur,
                execute_run_id=execute_run_id,
                trigger_context_run=trigger_run,
                projection_run=projection_run,
                plan_count=int(sum(len(v) for v in metric_lookup.values())),
                quality_items=quality_items,
            )
            quality_count = insert_execute_quality_items(
                cur,
                execute_run_id=execute_run_id,
                source_condition_run_id=str(trigger_run.get("source_condition_run_id") or ""),
                for_trade_date=str(trigger_run.get("for_trade_date") or ""),
                source_trade_date=str(trigger_run.get("source_trade_date") or ""),
                items=quality_items,
            )
            counts["common_trigger_run"] = 1
            counts["common_trigger_quality_item"] = quality_count
            batch: list[dict[str, Any]] = []
            seen = 0
            for plan in iter_full_day_plans(
                context_rows=context_rows,
                metric_lookup=metric_lookup,
                trigger_context_run_id=replay_plan.TRIGGER_CONTEXT_RUN_ID,
                projection_run_id=replay_plan.FULL_DAY_METRIC_RUN_ID,
                source_condition_run_id=replay_plan.SOURCE_CONDITION_RUN_ID,
                source_subscription_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                source_snapshot_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                for_trade_date=replay_plan.FOR_TRADE_DATE,
            ):
                seen += 1
                if plan.get("output_event_type") not in {"TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged"}:
                    continue
                batch.append(plan)
                if len(batch) >= batch_size:
                    written = write_action_confirmation_metric_outcomes_with_cursor(
                        cur,
                        execute_run_id=execute_run_id,
                        trigger_context_run=trigger_run,
                        plans=batch,
                    )
                    counts.update(written)
                    batch.clear()
                if progress_every and seen % progress_every == 0:
                    print(f"n4 full-day replay scanned={seen} matched_written={counts['common_event_outbox']}", flush=True)
            if batch:
                written = write_action_confirmation_metric_outcomes_with_cursor(
                    cur,
                    execute_run_id=execute_run_id,
                    trigger_context_run=trigger_run,
                    plans=batch,
                )
                counts.update(written)
            cur.execute("SELECT count(*)::bigint AS row_count FROM common_trigger_state WHERE run_id = %s", (execute_run_id,))
            counts["common_trigger_state"] = int(cur.fetchone()["row_count"])
            cur.execute("SELECT count(*)::bigint AS row_count FROM common_trigger_match WHERE run_id = %s", (execute_run_id,))
            counts["common_trigger_match"] = int(cur.fetchone()["row_count"])
            cur.execute(
                """
                SELECT count(*)::bigint AS row_count
                FROM common_event_outbox
                WHERE source_layer = 'N4_trigger' AND source_run_id = %s
                """,
                (execute_run_id,),
            )
            counts["common_event_outbox"] = int(cur.fetchone()["row_count"])
            cur.execute(
                """
                UPDATE common_trigger_run
                SET status='passed',
                    trigger_state_row_count=%s,
                    trigger_match_row_count=%s,
                    trigger_event_outbox_count=%s,
                    finished_at=now(),
                    updated_at=now()
                WHERE run_id=%s
                """,
                (
                    counts["common_trigger_state"],
                    counts["common_trigger_match"],
                    counts["common_event_outbox"],
                    execute_run_id,
                ),
            )
        conn.commit()
    return dict(counts)


def format_report(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    return "\n".join(
        [
            "# V3 20260612 N4 Full-Day Trigger Replay Dry-Run",
            "",
            f"- result: `{report.get('result')}`",
            f"- projection_run_id: `{report.get('projection_run_id')}`",
            f"- candidate_count: `{summary.get('candidate_count')}`",
            f"- TriggerMatched: `{(summary.get('by_output_event_type') or {}).get('TriggerMatched', 0)}`",
            f"- TriggerPendingMarketData: `{(summary.get('by_output_event_type') or {}).get('TriggerPendingMarketData', 0)}`",
            f"- TriggerStateChanged: `{(summary.get('by_output_event_type') or {}).get('TriggerStateChanged', 0)}`",
            f"- state_change_reasons: `{summary.get('by_state_change_reason')}`",
            f"- ordinary formal 30m contamination: `{summary.get('ordinary_formal_30m_contamination_count', 0)}`",
            f"- formal period arrays contain 30m: `{summary.get('formal_period_arrays_contains_30m_count', 0)}`",
            f"- ordinary missing formal proof matched: `{summary.get('ordinary_formal_missing_proof_trigger_matched_count', 0)}`",
            f"- HINT 30m TriggerMatched: `{summary.get('hint_30m_trigger_matched_count', 0)}`",
            f"- known polluted sample matched: `{summary.get('known_polluted_sample_trigger_matched_count', 0)}`",
            f"- persisted write policy: `{summary.get('persisted_write_policy')}`",
        ]
    ) + "\n"


def format_contract(contract: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# V3 20260612 N4 Full-Day Trigger Replay Contract",
            "",
            f"- result: `{contract.get('result')}`",
            f"- execute_run_id: `{contract.get('execute_run_id')}`",
            f"- expected_writes: `{contract.get('expected_writes')}`",
            f"- write_policy: `{contract.get('write_policy')}`",
            f"- strict_guards: `{contract.get('strict_guards')}`",
        ]
    ) + "\n"


def format_preflight(preflight: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# V3 20260612 N4 Full-Day Trigger Replay Preflight",
            "",
            f"- result: `{preflight.get('result')}`",
            f"- blockers: `{preflight.get('blockers')}`",
            f"- planned_writes: `{preflight.get('planned_writes')}`",
        ]
    ) + "\n"


def format_execute_report(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# V3 20260612 N4 Full-Day Trigger Replay Execute Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- execute_run_id: `{report.get('execute_run_id')}`",
            f"- write_counts: `{report.get('write_counts')}`",
            "- consumes N3 outbox: `False`",
            "- enters N5/N6: `False`",
        ]
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_N4_FULL_DAY_REPLAY_RUN_ID)
    parser.add_argument("--dry-run-json-path", default=DRY_RUN_JSON)
    parser.add_argument("--dry-run-markdown-path", default=DRY_RUN_MD)
    parser.add_argument("--contract-json-path", default=CONTRACT_JSON)
    parser.add_argument("--contract-markdown-path", default=CONTRACT_MD)
    parser.add_argument("--preflight-json-path", default=PREFLIGHT_JSON)
    parser.add_argument("--preflight-markdown-path", default=PREFLIGHT_MD)
    parser.add_argument("--execute-json-path", default=EXECUTE_JSON)
    parser.add_argument("--execute-markdown-path", default=EXECUTE_MD)
    parser.add_argument("--rollback-sql-path", default=ROLLBACK_SQL)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--progress-every", type=int, default=100000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report, _dry_preflight, contract, final_preflight, context_rows, metric_lookup, trigger_run = build_report_and_artifacts(
        dsn=args.dsn,
        sample_limit=args.sample_limit,
        execute_run_id=args.execute_run_id,
        dry_run_json_path=args.dry_run_json_path,
        dry_run_markdown_path=args.dry_run_markdown_path,
        contract_json_path=args.contract_json_path,
        contract_markdown_path=args.contract_markdown_path,
        preflight_json_path=args.preflight_json_path,
        preflight_markdown_path=args.preflight_markdown_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    if not args.execute:
        output = final_preflight
    else:
        try:
            assert_action_confirmation_metric_execute_confirmed(execute=args.execute, user_confirmed=args.user_confirmed)
            if final_preflight.get("result") != "PREFLIGHT_PASS":
                raise ActionConfirmationMetricExecuteError(f"N4 full-day replay preflight blocked: {final_preflight.get('blockers')}")
            write_counts = execute_replay(
                dsn=args.dsn,
                execute_run_id=args.execute_run_id,
                context_rows=context_rows,
                metric_lookup=metric_lookup,
                trigger_run=trigger_run,
                quality_items=report["quality"]["items"],
                batch_size=args.batch_size,
                progress_every=args.progress_every,
            )
            output = {
                "stage": "V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_EXECUTE",
                "result": "EXECUTE_PASS",
                "execute_run_id": args.execute_run_id,
                "dry_run_summary": report["summary"],
                "contract": contract,
                "preflight": final_preflight,
                "write_counts": write_counts,
                "side_effects": {
                    "writes_n4_trigger_facts": True,
                    "writes_outbox": True,
                    "consumes_n3_outbox": False,
                    "writes_inbox_or_checkpoint": False,
                    "n5_n6_touched": False,
                    "worker_started": False,
                    "voice_mobile_sim_trade_touched": False,
                },
            }
            write_json(args.execute_json_path, output)
            write_text(args.execute_markdown_path, format_execute_report(output))
        except Exception as exc:  # keep a no-half-write report for final closeout
            output = {
                "stage": "V3_20260612_N4_FULL_DAY_TRIGGER_REPLAY_EXECUTE",
                "result": "BLOCKED",
                "execute_run_id": args.execute_run_id,
                "blocked_reason": f"{type(exc).__name__}: {exc}",
                "side_effects": {
                    "n5_n6_touched": False,
                    "voice_mobile_sim_trade_touched": False,
                },
            }
            write_json(args.execute_json_path, output)
            write_text(args.execute_markdown_path, format_execute_report(output))
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_execute_report(output) if output.get("result") in {"EXECUTE_PASS", "BLOCKED"} else format_preflight(output))
    return 0 if output.get("result") in {"PREFLIGHT_PASS", "EXECUTE_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
