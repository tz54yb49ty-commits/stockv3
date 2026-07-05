"""N5 provisional ActionExecuted write path.

This module is isolated from the formal N5 execute transaction. It consumes
ActionExecuted dry-run plans and maps them to N5 action facts/events/outbox
without writing inbox, checkpoints, tracking state, user projection, or any
trade/sim/virtual-account state.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from psycopg.rows import dict_row

from ashare_v3.action.event_factory import build_n5_action_event
from ashare_v3.action.provisional_action_eligible import (
    ACTION_FACT_TABLE_BY_ASSET_KIND,
    insert_action_fact,
    insert_action_run,
    insert_common_action_event,
    insert_common_event_outbox,
    insert_quality_items,
)
from ashare_v3.action.provisional_action_executed_dry_run import (
    ACTION_EXECUTED_PLAN,
    PROVISIONAL_EXECUTED_MODE,
    build_provisional_action_executed_dry_run_report,
)
from ashare_v3.action.query_audit_phase2 import audited_n5_action_connect, audited_n5_readonly_plan_connect
from ashare_v3.events.ids import join_dedup_parts
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    FORMAL_TRIGGER_PERIODS,
    N5_SOURCE_LAYER,
    utc_now,
)


ACTION_EXECUTED_EVENT_TYPE = "ActionExecuted"
PROVISIONAL_ACTIONEXECUTED_POLICY = "n5_provisional_intraday_closed_minute"
PROVISIONAL_ACTIONEXECUTED_GENERATED_BY = "n5_provisional_actionexecuted_v1"
N3P_NOT_ACTION_CONFIRMATION_PROOF_BLOCKER = "BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF"
N5_ACTION_CONFIRMATION_METRIC_V2_KIND = "n5_action_confirmation_metric_v2"
RUN_ID_PATTERN = re.compile(
    r"^action_provisional_executed_(?P<for_trade_date>\d{8})until(?P<until_hhmm>\d{4})__intraday_closed_minute$"
)
SKIPPED_DUPLICATE_ACTION_EXECUTED = "SKIPPED_DUPLICATE_ACTION_EXECUTED"

N5P_ACTIONEXECUTED_ALLOWED_WRITE_TABLES = frozenset(
    {
        "common_action_run",
        "common_action_quality_item",
        "stock_action_fact",
        "index_action_fact",
        "board_action_fact",
        "common_action_event",
        "common_event_outbox",
    }
)
N5P_ACTIONEXECUTED_FORBIDDEN_WRITE_TABLES = frozenset(
    {
        "common_event_inbox",
        "common_event_consumer_checkpoint",
    }
)


class N5PActionExecutedBlocked(RuntimeError):
    """Raised when N5P ActionExecuted must fail closed."""


def assert_provisional_actionexecuted_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise N5PActionExecutedBlocked(
            "N5 provisional ActionExecuted execute blocked: missing " + ", ".join(missing)
        )


def build_n5p_actionexecuted_run_id(*, for_trade_date: str, until_hhmm: str) -> str:
    _validate_trade_date(for_trade_date)
    _validate_hhmm(until_hhmm)
    return f"action_provisional_executed_{for_trade_date}until{until_hhmm}__intraday_closed_minute"


def parse_n5p_actionexecuted_run_id(run_id: str) -> dict[str, str]:
    match = RUN_ID_PATTERN.match(str(run_id or ""))
    if not match:
        raise N5PActionExecutedBlocked(f"invalid N5P ActionExecuted run_id: {run_id}")
    for_trade_date = match.group("for_trade_date")
    until_hhmm = match.group("until_hhmm")
    _validate_trade_date(for_trade_date)
    _validate_hhmm(until_hhmm)
    return {
        "run_id": run_id,
        "for_trade_date": for_trade_date,
        "until_hhmm": until_hhmm,
        "mode": "provisional_executed",
        "confirmation_mode": PROVISIONAL_EXECUTED_MODE,
    }


def build_provisional_actionexecuted_once_report(
    *,
    source_eligible_action_run: Mapping[str, Any],
    source_eligible_action_run_id: str,
    action_run_id: str,
    for_trade_date: str,
    latest_closed_minute_label: Any,
    source_actioneligible_rows: Sequence[Mapping[str, Any]],
    confirmation_metric_rows: Sequence[Mapping[str, Any]],
    confirmation_projection_rows: Sequence[Mapping[str, Any]],
    target_counts: Mapping[str, int],
    execute: bool,
    user_confirmed: bool,
    rollback_sql_path: str | Path | None = None,
    include_execute_plan: bool = False,
) -> dict[str, Any]:
    if execute:
        assert_provisional_actionexecuted_execute_confirmed(execute=execute, user_confirmed=user_confirmed)
    _require_passed_source_action_run(
        source_eligible_action_run,
        source_eligible_action_run_id=source_eligible_action_run_id,
    )
    dry_run_report = build_provisional_action_executed_dry_run_report(
        actioneligible_rows=source_actioneligible_rows,
        confirmation_metric_rows=confirmation_metric_rows,
        confirmation_projection_rows=confirmation_projection_rows,
        for_trade_date=for_trade_date,
        latest_closed_minute=latest_closed_minute_label,
    )
    execute_plan = build_provisional_action_executed_write_plan(
        action_run_id=action_run_id,
        for_trade_date=for_trade_date,
        dry_run_plans=dry_run_report["action_executed_plans"],
        target_counts=target_counts,
    )
    decision_counts = dict(Counter({str(key): int(value) for key, value in (dry_run_report.get("decision_counts") or {}).items()}))
    report = {
        "result": "PREFLIGHT_PASS",
        "final_status": "passed",
        "layer_role": "N5_action",
        "mode": "provisional_actionexecuted",
        "source_eligible_action_run_id": source_eligible_action_run_id,
        "action_run_id": action_run_id,
        "for_trade_date": for_trade_date,
        "latest_closed_minute_label": isoformat_or_none(latest_closed_minute_label),
        "execute": execute,
        "source_actioneligible_count": len(source_actioneligible_rows),
        "confirmation_metric_row_count": len(confirmation_metric_rows),
        "confirmation_projection_row_count": len(confirmation_projection_rows),
        "dry_run_counts": decision_counts,
        "action_executed_plan_count": dry_run_report.get("action_executed_plan_count"),
        "write_plan_counts": execute_plan.get("write_counts"),
        "actual_write_counts": None,
        "event_counts": execute_plan.get("event_counts"),
        "target_absence": {
            "passed": True,
            "counts": {str(key): int(value) for key, value in target_counts.items()},
        },
        "side_effect_guard": execute_plan.get("side_effect_guard"),
        "forbidden_write_counts": execute_plan.get("forbidden_write_counts"),
        "allowed_write_tables": execute_plan.get("allowed_write_tables"),
        "rollback_sql_path": str(rollback_sql_path) if rollback_sql_path is not None else None,
    }
    if include_execute_plan:
        report["_execute_plan"] = execute_plan
    return report


def run_provisional_actionexecuted_once(
    *,
    dsn: str,
    source_eligible_action_run_id: str,
    action_run_id: str,
    for_trade_date: str,
    latest_closed_minute_label: Any,
    execute: bool,
    user_confirmed: bool,
    json_report_path: str | Path | None = None,
    markdown_report_path: str | Path | None = None,
    rollback_sql_path: str | Path | None = None,
) -> dict[str, Any]:
    if execute:
        assert_provisional_actionexecuted_execute_confirmed(execute=execute, user_confirmed=user_confirmed)
    source_rows, source_run = fetch_source_actioneligible_rows(dsn, source_eligible_action_run_id)
    confirmation_metric_rows = fetch_confirmation_metric_rows(dsn, for_trade_date)
    confirmation_projection_rows = fetch_confirmation_projection_rows(dsn, for_trade_date)
    target_counts = fetch_target_counts_from_dsn(dsn, action_run_id)
    report = build_provisional_actionexecuted_once_report(
        source_eligible_action_run=source_run,
        source_eligible_action_run_id=source_eligible_action_run_id,
        action_run_id=action_run_id,
        for_trade_date=for_trade_date,
        latest_closed_minute_label=latest_closed_minute_label,
        source_actioneligible_rows=source_rows,
        confirmation_metric_rows=confirmation_metric_rows,
        confirmation_projection_rows=confirmation_projection_rows,
        target_counts=target_counts,
        execute=execute,
        user_confirmed=user_confirmed,
        rollback_sql_path=rollback_sql_path,
        include_execute_plan=True,
    )
    execute_plan = report.pop("_execute_plan")
    if execute:
        with audited_n5_action_connect(
            dsn,
            stage_id="n5_provisional_actionexecuted_execute",
            source_run_id=action_run_id,
            connect_timeout=10,
            row_factory=dict_row,
        ) as conn:
            report["actual_write_counts"] = execute_provisional_action_executed_transaction(
                connection=conn,
                execute_plan=execute_plan,
            )
        report["result"] = "EXECUTED"
    if rollback_sql_path is not None:
        write_text(rollback_sql_path, build_provisional_actionexecuted_rollback_sql(action_run_id))
        report["rollback_sql_path"] = str(rollback_sql_path)
    if json_report_path is not None:
        write_json(json_report_path, report)
    if markdown_report_path is not None:
        write_text(markdown_report_path, render_actionexecuted_report_markdown(report))
    return report


def build_provisional_action_executed_write_plan(
    *,
    action_run_id: str,
    for_trade_date: str,
    dry_run_plans: Sequence[Mapping[str, Any]],
    target_counts: Mapping[str, int],
) -> dict[str, Any]:
    parsed_run_id = parse_n5p_actionexecuted_run_id(action_run_id)
    if parsed_run_id["for_trade_date"] != for_trade_date:
        raise N5PActionExecutedBlocked("action_run_id for_trade_date mismatch")
    _assert_target_absent(target_counts)

    now = utc_now()
    input_plans = [dict(plan) for plan in dry_run_plans]
    candidates: list[dict[str, Any]] = []
    skipped_decisions: Counter[str] = Counter()
    seen_canonical_keys: set[str] = set()
    for plan in input_plans:
        if str(plan.get("decision") or "") != ACTION_EXECUTED_PLAN:
            skipped_decisions[str(plan.get("decision") or "UNKNOWN_DECISION")] += 1
            continue
        payload = plan.get("payload") if isinstance(plan.get("payload"), Mapping) else {}
        canonical_key = str(payload.get("canonical_action_identity_key") or plan.get("canonical_action_identity_key") or "")
        if canonical_key in seen_canonical_keys:
            skipped_decisions[SKIPPED_DUPLICATE_ACTION_EXECUTED] += 1
            continue
        seen_canonical_keys.add(canonical_key)
        candidates.append(
            build_actionexecuted_candidate(
                plan=plan,
                action_run_id=action_run_id,
                for_trade_date=for_trade_date,
            )
        )

    action_fact_rows = {
        "stock_action_fact": [],
        "index_action_fact": [],
        "board_action_fact": [],
    }
    common_action_event_rows: list[dict[str, Any]] = []
    outbox_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        table_name = str(candidate["target_action_fact_table"])
        fact_row = build_action_fact_row(candidate, created_at=now)
        action_fact_rows[table_name].append(fact_row)
        common_action_event_rows.append(
            build_common_action_event_row(candidate, source_action_fact_id=None, created_at=now)
        )
        outbox_rows.append(build_action_outbox_record(candidate, source_action_fact_id=None, created_at=now))

    action_confirmation_mode = summarize_action_confirmation_mode(candidates)
    writes = {
        "common_action_run": [
            build_action_run_row(
                action_run_id=action_run_id,
                for_trade_date=for_trade_date,
                source_trigger_run_id=single_or_placeholder(
                    [candidate.get("source_trigger_run_id") for candidate in candidates],
                    placeholder="derived_from_actionexecuted_plan_payload",
                ),
                source_condition_run_id=single_or_placeholder(
                    [candidate.get("source_condition_run_id") for candidate in candidates],
                    placeholder=None,
                ),
                action_confirmation_mode=action_confirmation_mode,
                input_plan_count=len(input_plans),
                action_executed_count=len(candidates),
                created_at=now,
            )
        ],
        "common_action_quality_item": [
            build_quality_item(
                action_run_id=action_run_id,
                for_trade_date=for_trade_date,
                source_trigger_run_id=single_or_placeholder(
                    [candidate.get("source_trigger_run_id") for candidate in candidates],
                    placeholder="derived_from_actionexecuted_plan_payload",
                ),
                action_confirmation_mode=action_confirmation_mode,
                input_plan_count=len(input_plans),
                action_executed_count=len(candidates),
                skipped_decision_counts=skipped_decisions,
                created_at=now,
            )
        ],
        **action_fact_rows,
        "common_action_event": common_action_event_rows,
        "common_event_outbox": outbox_rows,
    }
    event_counts = dict(Counter(row["event_type"] for row in outbox_rows))
    return {
        "result": "EXECUTE_PLAN_READY",
        "status": "passed",
        "layer_role": "N5_action",
        "mode": "provisional_actionexecuted",
        "action_confirmation_mode": action_confirmation_mode,
        "action_run_id": action_run_id,
        "for_trade_date": for_trade_date,
        "until_hhmm": parsed_run_id["until_hhmm"],
        "input_plan_count": len(input_plans),
        "action_executed_count": len(candidates),
        "skipped_decision_counts": dict(skipped_decisions),
        "event_counts": event_counts,
        "candidates": candidates,
        "writes": writes,
        "write_counts": {table_name: len(rows) for table_name, rows in writes.items()},
        "allowed_write_tables": sorted(N5P_ACTIONEXECUTED_ALLOWED_WRITE_TABLES),
        "forbidden_write_counts": {table_name: 0 for table_name in sorted(N5P_ACTIONEXECUTED_FORBIDDEN_WRITE_TABLES)},
        "side_effect_guard": build_side_effect_guard(bool(candidates)),
    }


def build_actionexecuted_candidate(
    *,
    plan: Mapping[str, Any],
    action_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    payload = plan.get("payload") if isinstance(plan.get("payload"), Mapping) else {}
    source_payload = source_actioneligible_payload(payload)
    asset_kind = str(payload.get("asset_kind") or "")
    if asset_kind not in ACTION_FACT_TABLE_BY_ASSET_KIND:
        raise N5PActionExecutedBlocked(f"unsupported asset_kind for ActionExecuted: {asset_kind}")
    identity_key = str(payload.get("identity_key") or "")
    signal_type = str(payload.get("signal_type") or "")
    action_type = normalize_business_action_type(payload.get("action_type"), signal_type=signal_type)
    fact_action_type = action_fact_type_for_business_action(action_type)
    condition_key = str(payload.get("condition_key") or "")
    original_condition_key = str(source_payload.get("original_condition_key") or source_payload.get("condition_key") or condition_key)
    action_mark = str(payload.get("action_mark") or "")
    if action_mark not in {"normal", "30m_volume", "30m_shrink"}:
        raise N5PActionExecutedBlocked("ActionExecuted payload missing canonical action_mark")
    canonical_key = str(payload.get("canonical_action_identity_key") or plan.get("canonical_action_identity_key") or "")
    action_confirmation_mode = str(payload.get("action_confirmation_mode") or PROVISIONAL_EXECUTED_MODE)
    if action_confirmation_mode != PROVISIONAL_EXECUTED_MODE:
        raise N5PActionExecutedBlocked("ActionExecuted requires closed N3P confirmation metric")
    if str(payload.get("source_fact_kind") or "") == "realtime_projection_metric":
        raise N5PActionExecutedBlocked("ActionExecuted cannot use B2 projection as final confirmation proof")
    if payload_is_n3p_trigger_proof(payload, source_payload):
        raise N5PActionExecutedBlocked(N3P_NOT_ACTION_CONFIRMATION_PROOF_BLOCKER)
    if str(payload.get("source_metric_kind") or "") != N5_ACTION_CONFIRMATION_METRIC_V2_KIND:
        raise N5PActionExecutedBlocked("ActionExecuted requires N5 action-confirmation metric v2 proof")
    confirmation_metric_run_id = str(payload.get("confirmation_metric_run_id") or "")
    confirmation_metric_id = str(payload.get("confirmation_metric_id") or "")
    if not confirmation_metric_run_id or not confirmation_metric_id:
        raise N5PActionExecutedBlocked("ActionExecuted requires confirmation_metric_run_id and confirmation_metric_id")
    is_closed_1m = bool_value(payload.get("is_closed_1m"))
    if not is_closed_1m:
        raise N5PActionExecutedBlocked("ActionExecuted requires closed N3P confirmation metric")
    selected_metric_time = str(payload.get("selected_metric_time") or payload.get("trigger_time") or "")
    action_key = build_actionexecuted_action_key(
        action_run_id=action_run_id,
        canonical_action_identity_key=canonical_key,
        source_eligible_event_id=str(payload.get("source_eligible_event_id") or ""),
        source_trigger_event_id=str(payload.get("source_trigger_event_id") or ""),
        confirmation_metric_run_id=confirmation_metric_run_id,
        confirmation_metric_id=confirmation_metric_id,
        action_type=action_type,
        identity_key=identity_key,
        condition_key=condition_key,
    )
    dedup_key = build_actionexecuted_dedup_key(action_key=action_key)
    period_info = build_period_passthrough(source_payload, condition_key=condition_key, trigger_type=str(payload.get("trigger_type") or ""))
    source_trigger_run_id = str(payload.get("source_trigger_run_id") or source_payload.get("source_trigger_run_id") or "")
    source_condition_run_id = str(
        source_payload.get("source_condition_run_id")
        or payload.get("source_condition_run_id")
        or "not_available_in_actioneligible_payload"
    )
    source_market_trace = build_source_market_trace(payload)
    trigger_time = source_payload.get("trigger_time") or selected_metric_time
    closed_minute_required = True
    closed_minute_verified = True
    minute_context_status = "closed"
    candidate = {
        "action_run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "source_trigger_event_id": str(payload.get("source_trigger_event_id") or ""),
        "source_trigger_event_type": "TriggerMatched",
        "event_schema_version": str(source_payload.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION),
        "source_trigger_match_id": source_payload.get("source_trigger_match_id") or source_payload.get("trigger_match_id") or "not_available",
        "source_trigger_state_id": source_payload.get("source_trigger_state_id") or source_payload.get("trigger_state_id") or "not_available",
        "source_condition_run_id": source_condition_run_id,
        "source_market_data_run_id": confirmation_metric_run_id
        or str(payload.get("source_metric_run_id") or payload.get("projection_run_id") or ""),
        "source_market_trace": source_market_trace,
        "for_trade_date": for_trade_date,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": str(source_payload.get("direction") or action_type),
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key,
        "trigger_period": period_info["trigger_period"],
        "trigger_time": trigger_time,
        "trigger_price": source_payload.get("trigger_price") or "0",
        "trigger_mark_candidate": payload.get("trigger_mark_candidate") or source_payload.get("trigger_mark_candidate"),
        "action_mark": action_mark,
        "action_state": "executed",
        "confirmation_status": "passed",
        "tracking_until": None,
        "last_checked_minute_label": payload.get("metric_minute_label"),
        "trace_json": build_trace_json(payload, action_key=action_key, dedup_key=dedup_key),
        "action_policy": PROVISIONAL_ACTIONEXECUTED_POLICY,
        "action_confirmation_mode": action_confirmation_mode,
        "is_closed_1m": is_closed_1m,
        "business_action_type": action_type,
        "fact_action_type": fact_action_type,
        "lane": str(source_payload.get("lane") or "provisional_intraday"),
        "decision_status": "executed",
        "data_quality_status": "passed",
        "closed_minute_required": closed_minute_required,
        "closed_minute_verified": closed_minute_verified,
        "minute_context_status": minute_context_status,
        "action_bucket": build_action_bucket(payload),
        "canonical_action_identity_key": canonical_key,
        "action_key": action_key,
        "dedup_key": dedup_key,
        "target_action_fact_table": ACTION_FACT_TABLE_BY_ASSET_KIND[asset_kind],
        "source_payload_json": build_source_payload_json(payload, period_info=period_info, action_key=action_key, dedup_key=dedup_key),
        "event_time": payload.get("confirmation_metric_time") or payload.get("selected_metric_time") or trigger_time,
        **period_info,
    }
    return candidate


def payload_is_n3p_trigger_proof(payload: Mapping[str, Any], source_payload: Mapping[str, Any]) -> bool:
    for item in (payload, source_payload):
        if str(item.get("metric_role") or "") == "trigger_proof":
            return True
        if bool_value(item.get("not_n5_final_proof")):
            return True
        if str(item.get("source_trigger_proof_kind") or ""):
            return True
        if str(item.get("source_metric_kind") or "") == "realtime_action_confirmation_metric":
            return True
    return False


def normalize_business_action_type(value: Any, *, signal_type: str) -> str:
    raw = str(value or "")
    if raw in {"buy", "buy_candidate"}:
        return "buy"
    if raw in {"sell", "sell_candidate"}:
        return "sell"
    return "sell" if signal_type == "S_SELL" else "buy"


def action_fact_type_for_business_action(action_type: str) -> str:
    return "sell_candidate" if action_type == "sell" else "buy_candidate"


def source_actioneligible_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    trace = payload.get("trace") if isinstance(payload.get("trace"), Mapping) else {}
    source_payload = trace.get("source_actioneligible_payload") if isinstance(trace.get("source_actioneligible_payload"), Mapping) else {}
    return dict(source_payload)


def summarize_action_confirmation_mode(candidates: Sequence[Mapping[str, Any]]) -> str:
    modes = {str(candidate.get("action_confirmation_mode") or PROVISIONAL_EXECUTED_MODE) for candidate in candidates}
    if not modes:
        return PROVISIONAL_EXECUTED_MODE
    if len(modes) == 1:
        return next(iter(modes))
    return "mixed"


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def build_action_run_row(
    *,
    action_run_id: str,
    for_trade_date: str,
    source_trigger_run_id: str,
    source_condition_run_id: str | None,
    action_confirmation_mode: str,
    input_plan_count: int,
    action_executed_count: int,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "mode": "execute",
        "status": "passed",
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "trigger_outbox_row_count": input_plan_count,
        "action_candidate_row_count": action_executed_count,
        "action_fact_row_count": action_executed_count,
        "action_event_outbox_count": action_executed_count,
        "position_event_row_count": 0,
        "generated_by": PROVISIONAL_ACTIONEXECUTED_GENERATED_BY,
        "market_data_pulled": False,
        "trigger_layer_mutated": False,
        "user_layer_touched": False,
        "voice_touched": False,
        "sim_touched": False,
        "real_trade_touched": False,
        "worker_started": False,
        "consumer_checkpoint_updated": False,
        "common_event_inbox_updated": False,
        "raw_json": {
            "provisional": True,
            "mode_detail": f"provisional_actionexecuted_{action_confirmation_mode}",
            "action_confirmation_mode": action_confirmation_mode,
            "writes_inbox_or_checkpoint": False,
            "auto_trade_triggered": False,
        },
        "started_at": created_at,
        "finished_at": created_at,
    }


def build_quality_item(
    *,
    action_run_id: str,
    for_trade_date: str,
    source_trigger_run_id: str,
    action_confirmation_mode: str,
    input_plan_count: int,
    action_executed_count: int,
    skipped_decision_counts: Mapping[str, int],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "for_trade_date": for_trade_date,
        "data_domain": "common",
        "layer_scope": "action_fact",
        "table_name": "common_action_event",
        "gate_code": "n5_provisional_actionexecuted_summary",
        "gate_name": "N5 provisional ActionExecuted summary",
        "severity": "P2",
        "status": "passed",
        "expected_value": "ACTION_EXECUTED_PLAN creates ActionExecuted only",
        "actual_value": f"executed={action_executed_count}",
        "identity_key": None,
        "details": {
            "provisional": True,
            "input_plan_count": input_plan_count,
            "action_executed_count": action_executed_count,
            "skipped_decision_counts": dict(skipped_decision_counts),
            "action_confirmation_mode": action_confirmation_mode,
        },
        "created_at": created_at,
    }


def build_action_fact_row(candidate: Mapping[str, Any], *, created_at: datetime) -> dict[str, Any]:
    return {
        "run_id": candidate["action_run_id"],
        "source_trigger_run_id": candidate["source_trigger_run_id"],
        "source_trigger_event_id": candidate["source_trigger_event_id"],
        "source_trigger_event_type": candidate["source_trigger_event_type"],
        "event_schema_version": candidate["event_schema_version"],
        "source_trigger_match_id": candidate.get("source_trigger_match_id"),
        "trigger_state_id": candidate.get("source_trigger_state_id"),
        "source_trigger_state_id": candidate.get("source_trigger_state_id"),
        "source_condition_run_id": candidate.get("source_condition_run_id"),
        "source_market_data_run_id": candidate.get("source_market_data_run_id"),
        "source_market_trace": candidate.get("source_market_trace") or {},
        "for_trade_date": candidate["for_trade_date"],
        "asset_kind": candidate["asset_kind"],
        "identity_key": candidate["identity_key"],
        "direction": candidate["direction"],
        "signal_type": candidate["signal_type"],
        "condition_key": candidate["condition_key"],
        "original_condition_key": candidate["original_condition_key"],
        "trigger_period": candidate["trigger_period"],
        "trigger_time": candidate.get("trigger_time"),
        "trigger_price": candidate.get("trigger_price"),
        "trigger_mark_candidate": candidate.get("trigger_mark_candidate"),
        "action_mark": candidate["action_mark"],
        "action_state": "executed",
        "confirmation_status": "passed",
        "tracking_until": None,
        "last_checked_minute_label": candidate.get("last_checked_minute_label"),
        "trace_json": candidate.get("trace_json") or {},
        "action_policy": PROVISIONAL_ACTIONEXECUTED_POLICY,
        "action_type": candidate["fact_action_type"],
        "lane": candidate["lane"],
        "decision_status": candidate.get("decision_status") or "executed",
        "data_quality_status": "passed",
        "closed_minute_required": candidate.get("closed_minute_required"),
        "closed_minute_verified": candidate.get("closed_minute_verified"),
        "minute_context_status": candidate.get("minute_context_status"),
        "action_bucket": candidate["action_bucket"],
        "action_key": candidate["action_key"],
        "dedup_key": candidate["dedup_key"],
        "source_payload_json": candidate["source_payload_json"],
        "raw_json": {
            "provisional": True,
            "plan": json_safe_value(dict(candidate)),
        },
        "created_at": created_at,
        "updated_at": created_at,
        "target_action_fact_table": candidate["target_action_fact_table"],
    }


def build_common_action_event_row(
    candidate: Mapping[str, Any],
    *,
    source_action_fact_id: int | None,
    created_at: datetime,
) -> dict[str, Any]:
    envelope = build_action_envelope(candidate, source_action_fact_id=source_action_fact_id, created_at=created_at)
    return {
        "event_id": envelope.event_id,
        "event_schema_version": envelope.event_schema_version,
        "run_id": candidate["action_run_id"],
        "source_trigger_run_id": candidate["source_trigger_run_id"],
        "source_trigger_event_id": candidate["source_trigger_event_id"],
        "source_trigger_match_id": candidate.get("source_trigger_match_id"),
        "source_trigger_state_id": candidate.get("source_trigger_state_id"),
        "source_condition_run_id": candidate.get("source_condition_run_id"),
        "source_market_data_run_id": candidate.get("source_market_data_run_id"),
        "source_market_trace": candidate.get("source_market_trace") or {},
        "source_action_fact_table": candidate["target_action_fact_table"],
        "source_action_fact_id": source_action_fact_id,
        "for_trade_date": candidate["for_trade_date"],
        "asset_kind": candidate["asset_kind"],
        "identity_key": candidate["identity_key"],
        "direction": candidate["direction"],
        "signal_type": candidate["signal_type"],
        "condition_key": candidate["condition_key"],
        "original_condition_key": candidate["original_condition_key"],
        "trigger_period": candidate["trigger_period"],
        "trigger_mark_candidate": candidate.get("trigger_mark_candidate"),
        "action_mark": candidate["action_mark"],
        "action_state": "executed",
        "confirmation_status": "passed",
        "tracking_until": None,
        "last_checked_minute_label": candidate.get("last_checked_minute_label"),
        "trace_json": candidate.get("trace_json") or {},
        "action_policy": PROVISIONAL_ACTIONEXECUTED_POLICY,
        "event_type": ACTION_EXECUTED_EVENT_TYPE,
        "action_type": candidate["fact_action_type"],
        "lane": candidate["lane"],
        "data_quality_status": "passed",
        "action_key": candidate["action_key"],
        "dedup_key": candidate["dedup_key"],
        "partition_key": candidate["identity_key"],
        "payload_json": envelope.payload_json,
        "created_at": created_at,
    }


def build_action_outbox_record(
    candidate: Mapping[str, Any],
    *,
    source_action_fact_id: int | None,
    created_at: datetime,
) -> dict[str, Any]:
    return build_action_envelope(candidate, source_action_fact_id=source_action_fact_id, created_at=created_at).as_record()


def build_action_envelope(
    candidate: Mapping[str, Any],
    *,
    source_action_fact_id: int | None,
    created_at: datetime,
):
    payload = {
        **dict(candidate["source_payload_json"]),
        "source_action_fact_table": candidate["target_action_fact_table"],
        "source_action_fact_id": source_action_fact_id,
    }
    return build_n5_action_event(
        event_type=ACTION_EXECUTED_EVENT_TYPE,
        asset_kind=str(candidate["asset_kind"]),
        identity_key=str(candidate["identity_key"]),
        trade_date=str(candidate["for_trade_date"]),
        event_time=parse_event_time(candidate.get("event_time") or candidate.get("trigger_time")),
        action_run_id=str(candidate["action_run_id"]),
        source_trigger_event_id=str(candidate["source_trigger_event_id"]),
        source_trigger_run_id=str(candidate["source_trigger_run_id"]),
        source_trigger_state_id=candidate.get("source_trigger_state_id"),
        source_trigger_match_id=candidate.get("source_trigger_match_id"),
        source_condition_run_id=str(candidate.get("source_condition_run_id") or ""),
        direction=str(candidate["direction"]),
        signal_type=str(candidate["signal_type"]),
        condition_key=str(candidate["condition_key"]),
        original_condition_key=str(candidate["original_condition_key"]),
        trigger_period=str(candidate["trigger_period"]),
        action_mark=str(candidate["action_mark"]),
        action_state="executed",
        confirmation_status="passed",
        action_policy=PROVISIONAL_ACTIONEXECUTED_POLICY,
        trace_json=candidate.get("trace_json") or {},
        action_type=str(candidate["business_action_type"]),
        lane=str(candidate["lane"]),
        data_quality_status="passed",
        source_market_data_run_id=str(candidate.get("source_market_data_run_id") or ""),
        source_market_trace=candidate.get("source_market_trace") or {},
        payload=payload,
        created_at=created_at,
    )


def execute_provisional_action_executed_transaction(*, connection: Any, execute_plan: Mapping[str, Any]) -> dict[str, int]:
    with connection.cursor() as cur:
        cur.execute("BEGIN")
        insert_action_run(cur, execute_plan["writes"]["common_action_run"][0])
        insert_quality_items(cur, execute_plan["writes"]["common_action_quality_item"])
        fact_count: Counter[str] = Counter()
        event_count = 0
        outbox_count = 0
        for candidate in execute_plan.get("candidates") or []:
            fact_row = build_action_fact_row(candidate, created_at=utc_now())
            action_fact_id = insert_action_fact(cur, fact_row)
            insert_common_action_event(
                cur,
                build_common_action_event_row(candidate, source_action_fact_id=action_fact_id, created_at=utc_now()),
            )
            insert_common_event_outbox(
                cur,
                build_action_outbox_record(candidate, source_action_fact_id=action_fact_id, created_at=utc_now()),
            )
            fact_count[str(candidate["target_action_fact_table"])] += 1
            event_count += 1
            outbox_count += 1
        connection.commit()
    return {
        "common_action_run": 1,
        "common_action_quality_item": len(execute_plan["writes"]["common_action_quality_item"]),
        "stock_action_fact": fact_count["stock_action_fact"],
        "index_action_fact": fact_count["index_action_fact"],
        "board_action_fact": fact_count["board_action_fact"],
        "common_action_event": event_count,
        "common_event_outbox": outbox_count,
    }


def fetch_target_counts(cur: Any, action_run_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in (
        "common_action_run",
        "common_action_quality_item",
        "stock_action_fact",
        "index_action_fact",
        "board_action_fact",
        "common_action_event",
    ):
        cur.execute(f"SELECT count(*) AS row_count FROM {table_name} WHERE run_id = %s", (action_run_id,))
        counts[table_name] = _row_count(cur.fetchone())
    cur.execute(
        """
        SELECT count(*) AS row_count
        FROM common_event_outbox
        WHERE source_layer = %s AND source_run_id = %s
        """,
        (N5_SOURCE_LAYER, action_run_id),
    )
    counts["common_event_outbox"] = _row_count(cur.fetchone())
    cur.execute(
        """
        SELECT count(*) AS row_count
        FROM common_event_inbox
        WHERE payload_json->>'run_id' = %s
           OR payload_json->>'action_run_id' = %s
           OR raw_json->>'run_id' = %s
           OR raw_json->>'action_run_id' = %s
        """,
        (action_run_id, action_run_id, action_run_id, action_run_id),
    )
    counts["common_event_inbox"] = _row_count(cur.fetchone())
    cur.execute(
        """
        SELECT count(*) AS row_count
        FROM common_event_consumer_checkpoint
        WHERE checkpoint_payload->>'run_id' = %s
           OR checkpoint_payload->>'action_run_id' = %s
        """,
        (action_run_id, action_run_id),
    )
    counts["common_event_consumer_checkpoint"] = _row_count(cur.fetchone())
    return counts


def fetch_target_counts_from_dsn(dsn: str, action_run_id: str) -> dict[str, int]:
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_provisional_actionexecuted_target_absence",
        source_run_id=action_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        return fetch_target_counts(cur, action_run_id)


def fetch_source_actioneligible_rows(dsn: str, source_eligible_action_run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_provisional_actionexecuted_source_fetch",
        source_run_id=source_eligible_action_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM common_action_run WHERE run_id = %s", (source_eligible_action_run_id,))
        source_run = cur.fetchone()
        if not source_run:
            raise N5PActionExecutedBlocked(f"source ActionEligible action run missing: {source_eligible_action_run_id}")
        _require_passed_source_action_run(source_run, source_eligible_action_run_id=source_eligible_action_run_id)
        cur.execute(
            """
            SELECT *
            FROM common_event_outbox
            WHERE source_layer = %s
              AND source_run_id = %s
              AND event_type = 'ActionEligible'
            ORDER BY event_time, event_id
            """,
            (N5_SOURCE_LAYER, source_eligible_action_run_id),
        )
        return [dict(row) for row in cur.fetchall()], dict(source_run)


def fetch_confirmation_metric_rows(dsn: str, for_trade_date: str) -> list[dict[str, Any]]:
    _validate_trade_date(for_trade_date)
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_provisional_actionexecuted_confirmation_metric_fetch",
        source_run_id=f"confirmation_metric:{for_trade_date}",
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        rows: list[dict[str, Any]] = []
        for asset_kind, table_name in (
            ("stock", "stock_action_confirmation_projection_metric"),
            ("index", "index_action_confirmation_projection_metric"),
            ("board", "board_action_confirmation_projection_metric"),
        ):
            cur.execute(
                f"""
                SELECT *, %s AS asset_kind
                FROM {table_name}
                WHERE for_trade_date = %s
                ORDER BY metric_time, action_confirmation_metric_id
                """,
                (asset_kind, for_trade_date),
            )
            rows.extend(dict(row) for row in cur.fetchall())
        return rows


def fetch_confirmation_projection_rows(dsn: str, for_trade_date: str) -> list[dict[str, Any]]:
    _validate_trade_date(for_trade_date)
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_provisional_actionexecuted_confirmation_projection_fetch",
        source_run_id=f"confirmation_projection:{for_trade_date}",
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        rows: list[dict[str, Any]] = []
        for asset_kind, table_name, identity_column in (
            ("stock", "stock_realtime_projection_metric", "stock_identity_key"),
            ("index", "index_realtime_projection_metric", "index_identity_key"),
            ("board", "board_realtime_projection_metric", "board_identity_key"),
        ):
            cur.execute(
                f"""
                SELECT *, {identity_column} AS identity_key, %s AS asset_kind
                FROM {table_name}
                WHERE for_trade_date = %s
                ORDER BY snapshot_time, projection_id
                """,
                (asset_kind, for_trade_date),
            )
            rows.extend(dict(row) for row in cur.fetchall())
        return rows


def _row_count(row: Any) -> int:
    if isinstance(row, Mapping):
        return int(row["row_count"])
    return int(row[0])


def build_actionexecuted_action_key(
    *,
    action_run_id: str,
    canonical_action_identity_key: str,
    source_eligible_event_id: str,
    source_trigger_event_id: str,
    confirmation_metric_run_id: str,
    confirmation_metric_id: str,
    action_type: str,
    identity_key: str,
    condition_key: str,
) -> str:
    return join_dedup_parts(
        "N5_action",
        "provisional_actionexecuted",
        "action_run_id",
        action_run_id,
        "canonical_action_identity_key",
        canonical_action_identity_key,
        "source_eligible_event_id",
        source_eligible_event_id,
        "source_trigger_event_id",
        source_trigger_event_id,
        "confirmation_metric_run_id",
        confirmation_metric_run_id,
        "confirmation_metric_id",
        confirmation_metric_id,
        "action_type",
        action_type,
        "identity_key",
        identity_key,
        "condition_key",
        condition_key,
    )


def build_actionexecuted_dedup_key(*, action_key: str) -> str:
    return join_dedup_parts("N5_action", ACTION_EXECUTED_EVENT_TYPE, "action_key", action_key)


def build_action_bucket(payload: Mapping[str, Any]) -> str:
    return join_dedup_parts(
        "provisional_actionexecuted",
        "confirmation_metric_run_id",
        payload.get("confirmation_metric_run_id"),
        "confirmation_metric_id",
        payload.get("confirmation_metric_id"),
    )


def build_source_market_trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": "N5P_ActionExecuted_confirmation_metric",
        "source_metric_kind": payload.get("source_metric_kind"),
        "source_metric_run_id": payload.get("source_metric_run_id"),
        "confirmation_metric_run_id": payload.get("confirmation_metric_run_id"),
        "confirmation_metric_id": payload.get("confirmation_metric_id"),
        "confirmation_metric_time": payload.get("confirmation_metric_time"),
        "selected_metric_id": payload.get("selected_metric_id"),
        "selected_metric_time": payload.get("selected_metric_time"),
        "metric_time_label": payload.get("metric_time_label"),
        "metric_minute_label": payload.get("metric_minute_label"),
        "is_closed_1m": payload.get("is_closed_1m"),
        "source_mode": payload.get("source_mode"),
        "c1_dependency": payload.get("c1_dependency"),
        "rule_proof": json_safe_value(payload.get("rule_proof") or {}),
    }


def build_trace_json(payload: Mapping[str, Any], *, action_key: str, dedup_key: str) -> dict[str, Any]:
    action_confirmation_mode = str(payload.get("action_confirmation_mode") or PROVISIONAL_EXECUTED_MODE)
    return {
        "provisional": True,
        "action_confirmation_mode": action_confirmation_mode,
        "source": "n5p_actionexecuted_write",
        "source_eligible_event_id": payload.get("source_eligible_event_id"),
        "source_trigger_event_id": payload.get("source_trigger_event_id"),
        "source_fact_kind": payload.get("source_fact_kind"),
        "source_metric_run_id": payload.get("source_metric_run_id"),
        "confirmation_metric_run_id": payload.get("confirmation_metric_run_id"),
        "selected_metric_id": payload.get("selected_metric_id"),
        "selected_metric_time": payload.get("selected_metric_time"),
        "confirmation_metric_id": payload.get("confirmation_metric_id"),
        "confirmation_metric_time": payload.get("confirmation_metric_time"),
        "projection_run_id": payload.get("projection_run_id"),
        "projection_id": payload.get("projection_id"),
        "confirmation_projection_run_id": payload.get("confirmation_projection_run_id"),
        "confirmation_projection_id": payload.get("confirmation_projection_id"),
        "confirmation_projection_time": payload.get("confirmation_projection_time"),
        "projection_30m_type": payload.get("projection_30m_type"),
        "trigger_mark_candidate": payload.get("trigger_mark_candidate"),
        "metric_minute_label": payload.get("metric_minute_label"),
        "is_closed_1m": bool_value(payload.get("is_closed_1m")),
        "source_mode": payload.get("source_mode"),
        "c1_dependency": payload.get("c1_dependency"),
        "canonical_action_identity_key": payload.get("canonical_action_identity_key"),
        "action_key": action_key,
        "dedup_key": dedup_key,
        "rule_proof": json_safe_value(payload.get("rule_proof") or {}),
        "trace": json_safe_value(payload.get("trace") or {}),
    }


def build_source_payload_json(
    payload: Mapping[str, Any],
    *,
    period_info: Mapping[str, Any],
    action_key: str,
    dedup_key: str,
) -> dict[str, Any]:
    baseline_source = "n3p_realtime_action_confirmation_metric"
    action_confirmation_mode = PROVISIONAL_EXECUTED_MODE
    is_closed_1m = bool_value(payload.get("is_closed_1m"))
    return json_safe_value(
        {
            **dict(payload),
            "event_type": ACTION_EXECUTED_EVENT_TYPE,
            "provisional": True,
            "action_confirmation_mode": action_confirmation_mode,
            "action_key": action_key,
            "dedup_key": dedup_key,
            "action_state": "executed",
            "confirmation_status": "passed",
            "is_closed_1m": is_closed_1m,
            "closed_minute_required": True,
            "closed_minute_verified": True,
            "minute_context_status": "closed",
            "trigger_price": source_actioneligible_payload(payload).get("trigger_price") or "0",
            "trigger_kind": period_info["trigger_kind"],
            "trigger_period": period_info["trigger_period"],
            "triggered_periods": period_info["triggered_periods"],
            "all_trigger_periods": period_info["all_trigger_periods"],
            "primary_trigger_period": period_info["primary_trigger_period"],
            "period_trigger_baseline_trace": period_info["period_trigger_baseline_trace"],
            "baseline_source": baseline_source,
        }
    )


def build_period_passthrough(
    source_payload: Mapping[str, Any],
    *,
    condition_key: str,
    trigger_type: str,
) -> dict[str, Any]:
    primary = first_formal_period(
        source_payload.get("primary_trigger_period"),
        source_payload.get("trigger_period"),
        condition_key_period(condition_key),
    )
    if not primary:
        primary = "D"
    if str(trigger_type or condition_key).endswith(":FULL"):
        triggered = list(FORMAL_TRIGGER_PERIODS)
    else:
        triggered = formal_period_values(source_payload.get("triggered_periods")) or [primary]
    all_periods = formal_period_values(source_payload.get("all_trigger_periods")) or list(triggered)
    period_trace = source_payload.get("period_trigger_baseline_trace")
    if not isinstance(period_trace, Mapping) or not period_trace:
        period_trace = {"source": "n5p_actionexecuted", "primary_trigger_period": primary}
    return {
        "trigger_kind": "trigger",
        "trigger_period": primary,
        "triggered_periods": triggered,
        "all_trigger_periods": all_periods,
        "primary_trigger_period": primary,
        "period_trigger_baseline_trace": dict(period_trace),
    }


def formal_period_values(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    output: list[str] = []
    for item in values:
        period = str(item or "").strip()
        if period in FORMAL_TRIGGER_PERIODS and period not in output:
            output.append(period)
    return output


def first_formal_period(*values: Any) -> str:
    for value in values:
        period = str(value or "").strip()
        if period in FORMAL_TRIGGER_PERIODS:
            return period
    return ""


def condition_key_period(condition_key: str) -> str:
    for token in reversed(str(condition_key or "").split(":")):
        if token in FORMAL_TRIGGER_PERIODS:
            return token
    return ""


def build_side_effect_guard(has_executed_rows: bool) -> dict[str, bool]:
    return {
        "action_run_written": True,
        "action_quality_written": True,
        "action_fact_written": has_executed_rows,
        "action_event_written": has_executed_rows,
        "outbox_written": has_executed_rows,
        "inbox_written": False,
        "checkpoint_written": False,
        "tracking_written": False,
        "n6_written": False,
        "sim_trade_virtual_written": False,
        "worker_started": False,
        "auto_trade_triggered": False,
    }


def single_or_placeholder(values: Sequence[Any], *, placeholder: Any) -> Any:
    normalized = sorted({str(value) for value in values if str(value or "")})
    if len(normalized) == 1:
        return normalized[0]
    if len(normalized) > 1:
        return ",".join(normalized)
    return placeholder


def _assert_target_absent(target_counts: Mapping[str, int]) -> None:
    existing = {name: int(count) for name, count in target_counts.items() if int(count) > 0}
    if existing:
        raise N5PActionExecutedBlocked(f"BLOCKED_TARGET_NOT_EMPTY: target exists for action_run_id: {existing}")


def _require_passed_source_action_run(run: Mapping[str, Any], *, source_eligible_action_run_id: str) -> None:
    run_id = str(run.get("run_id") or "")
    status = str(run.get("status") or "")
    if run_id != source_eligible_action_run_id:
        raise N5PActionExecutedBlocked(
            f"source ActionEligible run lineage mismatch: {run_id} != {source_eligible_action_run_id}"
        )
    if status != "passed":
        raise N5PActionExecutedBlocked(f"source ActionEligible run status must be passed: {status}")


def _validate_trade_date(value: str) -> None:
    if len(str(value or "")) != 8 or not str(value).isdigit():
        raise N5PActionExecutedBlocked("for_trade_date must be YYYYMMDD")


def _validate_hhmm(value: str) -> None:
    text = str(value or "")
    if len(text) != 4 or not text.isdigit():
        raise N5PActionExecutedBlocked("until_hhmm must be HHMM")
    hour = int(text[:2])
    minute = int(text[2:])
    if hour > 23 or minute > 59:
        raise N5PActionExecutedBlocked("until_hhmm is out of range")


def parse_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return utc_now()
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def isoformat_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_provisional_actionexecuted_rollback_sql(action_run_id: str) -> str:
    escaped = str(action_run_id).replace("'", "''")
    return f"""-- N5 provisional ActionExecuted rollback for {escaped}
DO $$
DECLARE
  v_run_id text := '{escaped}';
  v_downstream_refs bigint;
BEGIN
  SELECT
      (SELECT count(*) FROM common_event_inbox
       WHERE payload_json->>'run_id' = v_run_id
          OR payload_json->>'action_run_id' = v_run_id
          OR raw_json->>'run_id' = v_run_id
          OR raw_json->>'action_run_id' = v_run_id)
    + (SELECT count(*) FROM common_event_consumer_checkpoint
       WHERE checkpoint_payload->>'run_id' = v_run_id
          OR checkpoint_payload->>'action_run_id' = v_run_id)
  INTO v_downstream_refs;

  IF v_downstream_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream inbox/checkpoint refs exist for %', v_run_id;
  END IF;

  DELETE FROM common_event_outbox WHERE source_layer = 'N5_action' AND source_run_id = v_run_id;
  DELETE FROM common_action_event WHERE run_id = v_run_id;
  DELETE FROM stock_action_fact WHERE run_id = v_run_id;
  DELETE FROM index_action_fact WHERE run_id = v_run_id;
  DELETE FROM board_action_fact WHERE run_id = v_run_id;
  DELETE FROM common_action_quality_item WHERE run_id = v_run_id;
  DELETE FROM common_action_run WHERE run_id = v_run_id;
END $$;
"""


def render_actionexecuted_report_markdown(report: Mapping[str, Any]) -> str:
    dry_counts = report.get("dry_run_counts") or {}
    write_counts = report.get("actual_write_counts") or report.get("write_plan_counts") or {}
    return "\n".join(
        [
            "# N5 Provisional ActionExecuted Report",
            "",
            f"- result: {report.get('result')}",
            f"- source_eligible_action_run_id: {report.get('source_eligible_action_run_id')}",
            f"- action_run_id: {report.get('action_run_id')}",
            f"- action_executed_plan_count: {report.get('action_executed_plan_count')}",
            f"- ACTION_EXECUTED_PLAN: {dry_counts.get(ACTION_EXECUTED_PLAN, 0)}",
            f"- PENDING_NO_CLOSED_METRIC: {dry_counts.get('PENDING_NO_CLOSED_METRIC', 0)}",
            f"- NOT_EXECUTED_RULE_FAILED: {dry_counts.get('NOT_EXECUTED_RULE_FAILED', 0)}",
            f"- SKIPPED_INVALID_PAYLOAD: {dry_counts.get('SKIPPED_INVALID_PAYLOAD', 0)}",
            f"- common_action_event: {write_counts.get('common_action_event', 0)}",
            f"- common_event_outbox: {write_counts.get('common_event_outbox', 0)}",
            f"- inbox_written: {(report.get('side_effect_guard') or {}).get('inbox_written')}",
            f"- checkpoint_written: {(report.get('side_effect_guard') or {}).get('checkpoint_written')}",
            f"- rollback_sql_path: {report.get('rollback_sql_path')}",
            "",
        ]
    )


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(json_safe_value(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
