"""N4 action-confirmation metric business execute runner.

The runner is deliberately run-once and double-confirmation guarded. It writes
only N4 trigger facts/outbox and never consumes N3 outbox, writes inbox or
checkpoint rows, starts workers, pulls market data, or enters N5/N6.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities
from ashare_v3.events.ids import build_n4_trigger_state_changed_dedup_key, build_stable_event_id
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    EventEnvelope,
    N4_SOURCE_LAYER,
    utc_now,
    validate_event_envelope,
)
from ashare_v3.trigger.action_confirmation_metric_matcher import (
    DEFAULT_EXECUTE_CONTRACT_JSON_PATH,
    DEFAULT_EXECUTE_FINAL_PREFLIGHT_JSON_PATH,
    DEFAULT_EXECUTE_ROLLBACK_SQL_PATH,
    DEFAULT_EXECUTE_RUN_ID,
    DEFAULT_FOR_TRADE_DATE,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_SOURCE_CONDITION_RUN_ID,
    DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
    DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
    DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    action_confirmation_metric_plan_replay_mode,
    build_action_confirmation_metric_business_execute_contract,
    build_action_confirmation_metric_execute_final_preflight,
    build_action_confirmation_metric_execute_rollback_sql,
    build_action_confirmation_metric_preflight_report,
    capture_action_confirmation_metric_execute_baseline,
    fetch_action_confirmation_metric_rows,
    fetch_context_rows,
    iter_action_confirmation_metric_plans_for_metric_grain,
    write_json,
    write_text,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_trigger_connect
from ashare_v3.trigger.standard_trigger_execute import (
    assert_no_existing_execute_outputs,
    build_execute_dedup_key,
    insert_execute_match,
    insert_execute_quality_items,
    insert_outbox_envelope,
    jsonb,
    schema_data_quality_status,
    update_execute_state_last_match,
    upsert_execute_state,
)


DEFAULT_EXECUTE_REPORT_JSON_PATH = "docs/N4_action_confirmation_metric_business_execute_report.json"
DEFAULT_EXECUTE_REPORT_MARKDOWN_PATH = "docs/N4_ACTION_CONFIRMATION_METRIC_BUSINESS_EXECUTE_REPORT.md"


class ActionConfirmationMetricExecuteError(RuntimeError):
    """Raised when N4 action-confirmation metric execute is blocked."""


def load_json(path: str | Path) -> dict[str, Any]:
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def assert_action_confirmation_metric_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise ActionConfirmationMetricExecuteError(
            "N4 action-confirmation metric execute blocked: missing " + ", ".join(missing)
        )


def run_action_confirmation_metric_once(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    execute_run_id: str = DEFAULT_EXECUTE_RUN_ID,
    trigger_context_run_id: str = DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    projection_run_id: str = DEFAULT_PROJECTION_RUN_ID,
    source_condition_run_id: str = DEFAULT_SOURCE_CONDITION_RUN_ID,
    source_subscription_run_id: str = DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
    source_snapshot_run_id: str = DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
    for_trade_date: str = DEFAULT_FOR_TRADE_DATE,
    dry_run_json_path: str = DEFAULT_JSON_REPORT_PATH,
    dry_run_preflight_json_path: str = DEFAULT_PREFLIGHT_JSON_PATH,
    contract_json_path: str = DEFAULT_EXECUTE_CONTRACT_JSON_PATH,
    final_preflight_json_path: str = DEFAULT_EXECUTE_FINAL_PREFLIGHT_JSON_PATH,
    rollback_sql_path: str = DEFAULT_EXECUTE_ROLLBACK_SQL_PATH,
    execute_report_json_path: str = DEFAULT_EXECUTE_REPORT_JSON_PATH,
    execute_report_markdown_path: str = DEFAULT_EXECUTE_REPORT_MARKDOWN_PATH,
) -> dict[str, Any]:
    assert_action_confirmation_metric_execute_confirmed(execute=execute, user_confirmed=user_confirmed)
    dry_run_report = load_json(dry_run_json_path)
    dry_run_preflight = load_json(dry_run_preflight_json_path)
    contract = build_action_confirmation_metric_business_execute_contract(
        dry_run_report,
        dry_run_preflight,
        execute_run_id=execute_run_id,
        rollback_sql_path=rollback_sql_path,
        business_execute_runner_ready=True,
        business_execute_runner="scripts/run_trigger_action_confirmation_metric_once.py",
    )
    write_text(rollback_sql_path, build_action_confirmation_metric_execute_rollback_sql(execute_run_id))
    baseline = capture_action_confirmation_metric_execute_baseline(dsn, execute_run_id)
    final_preflight = build_action_confirmation_metric_execute_final_preflight(
        dry_run_report,
        dry_run_preflight,
        contract,
        baseline_summary=baseline,
        rollback_sql_exists=Path(rollback_sql_path).exists(),
    )
    write_json(contract_json_path, contract)
    write_json(final_preflight_json_path, final_preflight)
    if final_preflight.get("result") != "PREFLIGHT_PASS":
        raise ActionConfirmationMetricExecuteError(
            f"N4 action-confirmation metric execute blocked: {final_preflight.get('blockers')}"
    )

    context_rows, trigger_context_run = fetch_context_rows(dsn, trigger_context_run_id)
    metric_rows = fetch_action_confirmation_metric_rows(
        dsn,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
    )
    replay_mode = action_confirmation_metric_plan_replay_mode(metric_rows)
    planned_candidate_count = int((dry_run_report.get("summary") or {}).get("candidate_count") or 0)
    plans = iter_action_confirmation_metric_plans_for_metric_grain(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
        context_rows=context_rows,
        metric_rows=metric_rows,
    )
    quality_items = list(final_preflight.get("quality_items") or [])
    write_counts = execute_action_confirmation_metric_transaction(
        dsn=dsn,
        execute_run_id=execute_run_id,
        trigger_context_run=trigger_context_run,
        projection_run={
            "projection_run_id": projection_run_id,
            "source_snapshot_run_id": source_snapshot_run_id,
            "source_subscription_run_id": source_subscription_run_id,
        },
        plan_count=planned_candidate_count,
        plans=plans,
        quality_items=quality_items,
    )
    report = {
        "result": "EXECUTED",
        "layer_role": "N4_trigger",
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": source_snapshot_run_id,
        "for_trade_date": for_trade_date,
        "replay_mode": replay_mode,
        "write_counts": write_counts,
        "quality": {
            "p0_count": int((final_preflight.get("quality") or {}).get("p0_count") or 0),
            "p1_count": int((final_preflight.get("quality") or {}).get("p1_count") or 0),
            "p2_count": int((final_preflight.get("quality") or {}).get("p2_count") or 0),
        },
        "side_effects": {
            "writes_n4_trigger_facts": True,
            "writes_outbox": True,
            "consumes_n3_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "n5_n6_touched": False,
            "worker_started": False,
            "market_data_pulled": False,
            "real_trade_touched": False,
        },
    }
    write_json(execute_report_json_path, report)
    write_text(execute_report_markdown_path, format_action_confirmation_metric_execute_report(report))
    return report


def execute_action_confirmation_metric_transaction(
    *,
    dsn: str,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    projection_run: Mapping[str, Any],
    plan_count: int,
    plans: Iterable[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_action_confirmation_metric_execute_transaction",
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
                trigger_context_run=trigger_context_run,
                projection_run=projection_run,
                plan_count=plan_count,
                quality_items=quality_items,
            )
            quality_count = insert_execute_quality_items(
                cur,
                execute_run_id=execute_run_id,
                source_condition_run_id=str(trigger_context_run.get("source_condition_run_id") or ""),
                for_trade_date=str(trigger_context_run.get("for_trade_date") or ""),
                source_trade_date=str(trigger_context_run.get("source_trade_date") or ""),
                items=quality_items,
            )
            write_counts = write_action_confirmation_metric_outcomes_with_cursor(
                cur,
                execute_run_id=execute_run_id,
                trigger_context_run=trigger_context_run,
                plans=plans,
            )
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
                (
                    write_counts["common_trigger_state"],
                    write_counts["common_trigger_match"],
                    write_counts["common_event_outbox"],
                    execute_run_id,
                ),
            )
        conn.commit()
    return {
        "common_trigger_run": 1,
        "common_trigger_quality_item": quality_count,
        **write_counts,
    }


def insert_action_confirmation_metric_trigger_run(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    projection_run: Mapping[str, Any],
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
          %(source_condition_row_count)s, %(context_snapshot_row_count)s,
          0, 0, 0, 'trigger_action_confirmation_metric_execute_v1',
          false, false, false, false, false, false, false, %(raw_json)s,
          now(), now()
        )
        """,
        {
            "run_id": execute_run_id,
            "source_condition_run_id": trigger_context_run.get("source_condition_run_id"),
            "source_market_data_run_id": projection_run.get("projection_run_id"),
            "for_trade_date": trigger_context_run.get("for_trade_date"),
            "source_trade_date": trigger_context_run.get("source_trade_date"),
            "prev_trade_date": trigger_context_run.get("prev_trade_date") or trigger_context_run.get("source_trade_date"),
            "p0_count": severity["P0"],
            "p1_count": severity["P1"],
            "p2_count": severity["P2"],
            "source_condition_row_count": int(trigger_context_run.get("context_snapshot_row_count") or plan_count),
            "context_snapshot_row_count": int(trigger_context_run.get("context_snapshot_row_count") or 0),
            "raw_json": jsonb(
                {
                    "trigger_context_run_id": trigger_context_run.get("run_id"),
                    "projection_run_id": projection_run.get("projection_run_id"),
                    "source_snapshot_run_id": projection_run.get("source_snapshot_run_id"),
                    "source_subscription_run_id": projection_run.get("source_subscription_run_id"),
                    "canonical_runtime_spec": "docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md",
                    "action_confirmation_rule_spec": "docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md",
                    "writes_outbox": True,
                    "consumes_n3_outbox": False,
                    "writes_inbox_or_checkpoint": False,
                }
            ),
        },
    )


def write_action_confirmation_metric_outcomes_with_cursor(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plans: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    allowed_event_types = {"TriggerMatched", "TriggerStateChanged"}
    lifecycle_state_keys: set[tuple[str, str, str, str, str, str]] = set()
    match_count = 0
    outbox_count = 0
    matched_event_count = 0
    pending_event_count = 0
    state_changed_event_count = 0
    for plan in plans:
        output_event_type = str(plan.get("output_event_type") or "")
        if output_event_type not in allowed_event_types:
            continue
        state_id = upsert_execute_state(cur, execute_run_id=execute_run_id, trigger_context_run=trigger_context_run, plan=plan)
        lifecycle_state_keys.add(
            (
                str(plan.get("asset_kind") or ""),
                str(plan.get("identity_key") or ""),
                str(plan.get("direction") or ""),
                str(plan.get("signal_type") or ""),
                str(plan.get("condition_key") or ""),
                str(trigger_context_run.get("for_trade_date") or ""),
            )
        )
        dedup_key = build_execute_dedup_key(execute_run_id=execute_run_id, plan=plan)
        output_event_id = build_stable_event_id(
            source_layer=N4_SOURCE_LAYER,
            event_type=output_event_type,
            source_run_id=execute_run_id,
            dedup_key=dedup_key,
            event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        )
        match_id: int | None = None
        if output_event_type == "TriggerMatched" and bool(plan.get("writes_common_trigger_match", True)):
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
            match_count += 1
        envelope = build_action_confirmation_metric_execute_event_envelope(
            execute_run_id=execute_run_id,
            trigger_context_run=trigger_context_run,
            plan=plan,
            trigger_state_id=state_id,
            trigger_match_id=match_id,
            output_event_id=output_event_id,
            dedup_key=dedup_key,
        )
        insert_outbox_envelope(cur, envelope)
        outbox_count += 1
        if output_event_type == "TriggerMatched":
            matched_event_count += 1
        elif output_event_type == "TriggerStateChanged":
            state_changed_event_count += 1
    return {
        "common_trigger_state": len(lifecycle_state_keys),
        "common_trigger_match": match_count,
        "common_event_outbox": outbox_count,
        "TriggerMatched": matched_event_count,
        "TriggerPendingMarketData": pending_event_count,
        "TriggerStateChanged": state_changed_event_count,
    }


def build_action_confirmation_metric_execute_event_envelope(
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    trigger_state_id: int,
    trigger_match_id: int | None,
    output_event_id: str,
    dedup_key: str,
) -> EventEnvelope:
    payload = {
        "run_id": execute_run_id,
        "source_event_id": plan.get("source_event_id"),
        "source_event_type": plan.get("source_event_type"),
        "source_action_confirmation_metric_id": plan.get("source_action_confirmation_metric_id"),
        "source_projection_run_id": plan.get("source_projection_run_id"),
        "projection_schema_version": plan.get("projection_schema_version"),
        "source_snapshot_run_id": plan.get("source_snapshot_run_id"),
        "source_snapshot_event_id": plan.get("source_snapshot_event_id"),
        "source_today_minute_run_id": plan.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": plan.get("source_previous_day_minute_run_id"),
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
        "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
        "match_basis": plan.get("match_basis"),
        "trigger_price": plan.get("trigger_price"),
        "trigger_price_source": plan.get("trigger_price_source"),
        "trigger_period": plan.get("trigger_period"),
        "trigger_bucket": plan.get("trigger_bucket"),
        "trigger_live": plan.get("trigger_live"),
        "previous_trigger_live": plan.get("previous_trigger_live"),
        "current_status": plan.get("current_status"),
        "previous_status": plan.get("previous_status"),
        "primary_trigger_period": plan.get("primary_trigger_period"),
        "previous_primary_trigger_period": plan.get("previous_primary_trigger_period"),
        "triggered_periods": plan.get("triggered_periods") or [],
        "triggered_period_details": plan.get("triggered_period_details")
        or plan.get("formal_triggered_period_details")
        or [],
        "formal_trigger_period_proof_status": plan.get("formal_trigger_period_proof_status"),
        "all_trigger_periods": plan.get("all_trigger_periods"),
        "previous_all_trigger_periods": plan.get("previous_all_trigger_periods") or [],
        "projection_30m_flag": plan.get("projection_30m_flag"),
        "projection_30m_type": plan.get("projection_30m_type"),
        "previous_projection_30m_flag": plan.get("previous_projection_30m_flag"),
        "previous_projection_30m_type": plan.get("previous_projection_30m_type"),
        "previous_trigger_mark_candidate": plan.get("previous_trigger_mark_candidate"),
        "state_change_reason": plan.get("state_change_reason"),
        "source_outcome_event_type": plan.get("source_outcome_event_type"),
        "source_outcome_event_id": plan.get("source_outcome_event_id"),
        "writes_common_trigger_match": bool(plan.get("writes_common_trigger_match", plan.get("output_event_type") == "TriggerMatched")),
        "is_n5_action_entry": bool(plan.get("is_n5_action_entry", plan.get("output_event_type") == "TriggerMatched")),
        "data_quality_status": plan.get("data_quality_status"),
        "db_data_quality_status": schema_data_quality_status(plan.get("data_quality_status")),
        "metric_quality_status": plan.get("metric_quality_status"),
        "metric_ready": plan.get("metric_ready"),
        "not_ready_reason": plan.get("not_ready_reason"),
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "source_condition_pool_id": plan.get("source_condition_pool_id"),
        "source_condition_basis_id": plan.get("source_condition_basis_id"),
        "source_minute_target_scope_id": plan.get("source_minute_target_scope_id"),
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "context_hash": plan.get("context_hash"),
        "metric_trace": plan.get("metric_trace") or {},
        "period_trigger_baseline_trace": plan.get("period_trigger_baseline_trace") or {},
        "n4_boundary": {
            "market_data_pulled": False,
            "n3_outbox_consumed": False,
            "writes_inbox_or_checkpoint": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "final_action_mark_decided": False,
        },
    }
    envelope = EventEnvelope(
        event_id=output_event_id,
        event_type=str(plan.get("output_event_type")),
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        trade_date=str(trigger_context_run.get("for_trade_date")),
        asset_kind=str(plan.get("asset_kind")),
        identity_key=str(plan.get("identity_key")),
        event_time=parse_action_confirmation_metric_event_time(plan),
        source_layer=N4_SOURCE_LAYER,
        source_run_id=execute_run_id,
        dedup_key=dedup_key,
        partition_key=str(plan.get("identity_key")),
        payload_json=payload,
        created_at=utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def build_action_confirmation_metric_state_changed_event_envelope(
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    source_outcome_event_id: str,
    source_outcome_event_type: str,
) -> EventEnvelope:
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
        event_type="TriggerStateChanged",
        source_run_id=execute_run_id,
        dedup_key=dedup_key,
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
    )
    payload = {
        "run_id": execute_run_id,
        "source_event_id": source_outcome_event_id,
        "source_event_type": source_outcome_event_type,
        "source_action_confirmation_metric_id": plan.get("source_action_confirmation_metric_id"),
        "source_projection_run_id": plan.get("source_projection_run_id"),
        "projection_schema_version": plan.get("projection_schema_version"),
        "source_snapshot_run_id": plan.get("source_snapshot_run_id"),
        "source_snapshot_event_id": plan.get("source_snapshot_event_id"),
        "source_today_minute_run_id": plan.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": plan.get("source_previous_day_minute_run_id"),
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
        "source_outcome_event_type": source_outcome_event_type,
        "source_outcome_event_id": source_outcome_event_id,
        "writes_common_trigger_match": False,
        "is_n5_action_entry": False,
        "data_quality_status": plan.get("data_quality_status"),
        "db_data_quality_status": schema_data_quality_status(plan.get("data_quality_status")),
        "metric_quality_status": plan.get("metric_quality_status"),
        "metric_ready": plan.get("metric_ready"),
        "not_ready_reason": plan.get("not_ready_reason"),
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "source_condition_pool_id": plan.get("source_condition_pool_id"),
        "source_condition_basis_id": plan.get("source_condition_basis_id"),
        "source_minute_target_scope_id": plan.get("source_minute_target_scope_id"),
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "context_hash": plan.get("context_hash"),
        "metric_trace": plan.get("metric_trace") or {},
        "period_trigger_baseline_trace": plan.get("period_trigger_baseline_trace") or {},
        "n4_boundary": {
            "market_data_pulled": False,
            "n3_outbox_consumed": False,
            "writes_inbox_or_checkpoint": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "final_action_mark_decided": False,
        },
    }
    envelope = EventEnvelope(
        event_id=output_event_id,
        event_type="TriggerStateChanged",
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        trade_date=str(trigger_context_run.get("for_trade_date")),
        asset_kind=str(plan.get("asset_kind")),
        identity_key=str(plan.get("identity_key")),
        event_time=parse_action_confirmation_metric_event_time(plan),
        source_layer=N4_SOURCE_LAYER,
        source_run_id=execute_run_id,
        dedup_key=dedup_key,
        partition_key=str(plan.get("identity_key")),
        payload_json=payload,
        created_at=utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def parse_action_confirmation_metric_event_time(plan: Mapping[str, Any]) -> datetime:
    trace = plan.get("metric_trace") or {}
    raw = None
    if isinstance(trace, Mapping):
        raw = trace.get("metric_time") or trace.get("current_price_time")
    if raw:
        try:
            return datetime.fromisoformat(str(raw).replace(" ", "T"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def format_action_confirmation_metric_execute_report(report: Mapping[str, Any]) -> str:
    counts = report.get("write_counts") or {}
    quality = report.get("quality") or {}
    return "\n".join(
        [
            "# N4 Action-Confirmation Metric Business Execute Report",
            "",
            f"- result: {report.get('result')}",
            f"- execute_run_id: {report.get('execute_run_id')}",
            f"- projection_run_id: {report.get('projection_run_id')}",
            f"- trigger_context_run_id: {report.get('trigger_context_run_id')}",
            f"- common_trigger_run: {counts.get('common_trigger_run', 0)}",
            f"- common_trigger_quality_item: {counts.get('common_trigger_quality_item', 0)}",
            f"- common_trigger_state: {counts.get('common_trigger_state', 0)}",
            f"- common_trigger_match: {counts.get('common_trigger_match', 0)}",
            f"- common_event_outbox: {counts.get('common_event_outbox', 0)}",
            f"- P0/P1/P2: {quality.get('p0_count', 0)}/{quality.get('p1_count', 0)}/{quality.get('p2_count', 0)}",
            "",
        ]
    )
