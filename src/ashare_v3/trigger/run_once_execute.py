"""N4-5 synthetic trigger run-once executor.

This executor uses the N4-4 synthetic/sample N3 event plans to write only N4
trigger facts and N4 outbox events. It does not consume real N3 outbox rows,
pull market data, start workers, or write downstream rows.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg import sql as pg_sql
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
from ashare_v3.trigger.context_preflight import ASSET_KINDS, TARGET_CONTEXT_TABLES
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect, audited_n4_trigger_connect
from ashare_v3.trigger.synthetic_dry_run import (
    DEFAULT_N4_4_JSON_REPORT_PATH,
    DEFAULT_N4_4_MD_REPORT_PATH,
    DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    SYNTHETIC_EVENT_TYPES,
    build_dry_run_plans,
    build_synthetic_events,
    fetch_local_context_rows,
    run_synthetic_trigger_dry_run,
    summarize_plans,
)


DEFAULT_N4_5_JSON_REPORT_PATH = "docs/N4_5_trigger_run_once_execute_report.json"
DEFAULT_N4_5_MD_REPORT_PATH = "docs/N4_5_TRIGGER_RUN_ONCE_EXECUTE_REPORT.md"
DEFAULT_N4_5_ROLLBACK_SQL_PATH = "sql/N4_5_trigger_run_once_rollback.sql"

ALLOWED_N4_OUTPUT_EVENT_TYPES = ("TriggerMatched", "TriggerPendingMarketData")
EXECUTED_N4_OUTPUT_EVENT_TYPES = ("TriggerMatched", "TriggerPendingMarketData")
REQUIRED_TRIGGER_MATCHED_PAYLOAD_KEYS = (
    "run_id",
    "source_event_id",
    "source_event_type",
    "context_snapshot_id",
    "trigger_match_id",
    "identity_key",
    "asset_kind",
    "direction",
    "condition_key",
    "signal_type",
    "trigger_mark_candidate",
    "trigger_period",
    "data_quality_status",
)
N4_5_QUALITY_PREFIX = "n4_5_"
N4_COUNT_TABLES = (
    "common_trigger_run",
    "common_trigger_state",
    "common_trigger_match",
    "common_trigger_quality_item",
    "common_event_outbox",
    *TARGET_CONTEXT_TABLES.values(),
)
N3_FACT_GUARD_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "common_market_data_subscription",
    "common_market_data_pull_plan",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_previous_day_minute_preload_status",
    "index_previous_day_minute_preload_status",
    "board_previous_day_minute_preload_status",
)


def run_trigger_run_once_execute(
    *,
    dsn: str,
    trigger_context_run_id: str = DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    json_report_path: str = DEFAULT_N4_5_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N4_5_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_N4_5_ROLLBACK_SQL_PATH,
    dry_run_json_report_path: str = DEFAULT_N4_4_JSON_REPORT_PATH,
    dry_run_markdown_report_path: str = DEFAULT_N4_4_MD_REPORT_PATH,
    sample_limit: int = 80,
    stage: str = "N4-5",
) -> dict[str, Any]:
    started_at = utc_now_iso()
    dry_run_report = run_synthetic_trigger_dry_run(
        dsn=dsn,
        trigger_context_run_id=trigger_context_run_id,
        json_report_path=dry_run_json_report_path,
        markdown_report_path=dry_run_markdown_report_path,
        sample_limit=sample_limit,
    )
    if int(dry_run_report["quality"]["p0_count"]) > 0:
        raise RuntimeError("N4-5 blocked: N4-4 dry-run precheck has P0 findings")

    context_rows, trigger_run = fetch_local_context_rows(dsn, trigger_context_run_id)
    synthetic_events = build_synthetic_events(str(trigger_run.get("for_trade_date") or ""))
    plans = build_dry_run_plans(context_rows=context_rows, synthetic_events=synthetic_events)
    plan_summary = summarize_plans(plans)
    rollback_sql = build_trigger_run_once_rollback_sql(trigger_context_run_id)
    write_text(rollback_sql_path, rollback_sql)

    source_condition_run_id = str(trigger_run.get("source_condition_run_id") or "")
    before_snapshot = capture_run_once_snapshot(
        dsn,
        phase="before_n4_5",
        condition_run_id=source_condition_run_id,
        trigger_run_id=trigger_context_run_id,
    )
    pre_quality_items = build_pre_execute_quality_items(
        trigger_context_run_id=trigger_context_run_id,
        trigger_run=trigger_run,
        dry_run_report=dry_run_report,
        plans=plans,
        synthetic_events=synthetic_events,
    )
    pre_severity_counts = count_quality_severities(pre_quality_items)
    if pre_severity_counts["P0"] > 0:
        raise RuntimeError("N4-5 blocked: execute prechecks have P0 findings")

    inserted_counts = execute_run_once_transaction(
        dsn=dsn,
        trigger_run=trigger_run,
        plans=plans,
        synthetic_events=synthetic_events,
        quality_items=pre_quality_items,
    )
    after_write_snapshot = capture_run_once_snapshot(
        dsn,
        phase="after_n4_5_write",
        condition_run_id=source_condition_run_id,
        trigger_run_id=trigger_context_run_id,
    )
    output_summary = fetch_output_summary(dsn, trigger_context_run_id)
    post_checks_for_quality = build_post_execute_checks(
        dry_run_report=dry_run_report,
        before_snapshot=before_snapshot,
        after_snapshot=after_write_snapshot,
        inserted_counts=inserted_counts,
        output_summary=output_summary,
        expected_quality_delta=None,
    )
    post_quality_items = build_post_quality_items(post_checks_for_quality)
    inserted_counts["common_trigger_quality_item"] += append_quality_items(
        dsn=dsn,
        trigger_run=trigger_run,
        items=post_quality_items,
    )

    after_snapshot = capture_run_once_snapshot(
        dsn,
        phase="after_n4_5",
        condition_run_id=source_condition_run_id,
        trigger_run_id=trigger_context_run_id,
    )
    output_summary = fetch_output_summary(dsn, trigger_context_run_id)
    post_checks = build_post_execute_checks(
        dry_run_report=dry_run_report,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        inserted_counts=inserted_counts,
        output_summary=output_summary,
        expected_quality_delta=inserted_counts["common_trigger_quality_item"],
    )
    all_quality_items = [*pre_quality_items, *post_quality_items]
    final_severity_counts = count_quality_severities(all_quality_items)

    report = {
        "stage": stage,
        "layer_role": "N4_trigger",
        "execution_mode": "synthetic_sample_n3_event_trigger_run_once_execute",
        "run_id": trigger_context_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": trigger_run.get("for_trade_date"),
        "source_trade_date": trigger_run.get("source_trade_date"),
        "prev_trade_date": trigger_run.get("prev_trade_date"),
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "rollback_sql_path": rollback_sql_path,
        "dry_run_precheck_report": summarize_dry_run_report(dry_run_report),
        "synthetic_events": synthetic_events,
        "plan_summary": plan_summary,
        "before_row_counts": before_snapshot["row_counts"],
        "after_row_counts": after_snapshot["row_counts"],
        "before_snapshot": before_snapshot,
        "after_snapshot": after_snapshot,
        "inserted_counts": inserted_counts,
        "output_summary": output_summary,
        "post_checks": post_checks,
        "quality": {
            "p0_count": final_severity_counts["P0"],
            "p1_count": final_severity_counts["P1"],
            "p2_count": final_severity_counts["P2"],
            "items": all_quality_items,
        },
        "rollback_sql": rollback_sql,
        "side_effects": {
            "will_execute_sql": True,
            "writes_performed": True,
            "trigger_state_written": True,
            "trigger_match_written": True,
            "trigger_quality_item_written": True,
            "event_outbox_written": True,
            "trigger_context_snapshot_written": False,
            "trigger_run_updated": False,
            "market_data_pulled": False,
            "real_n3_event_consumed": False,
            "real_common_event_outbox_consumed": False,
            "downstream_layers_touched": False,
            "action_user_voice_sim_written": False,
            "worker_started": False,
            "old_system_touched": False,
            "external_n2_runtime_path_accessed": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_trigger_run_once_execute_report(report))
    return report


def execute_run_once_transaction(
    *,
    dsn: str,
    trigger_run: Mapping[str, Any],
    plans: Sequence[Mapping[str, Any]],
    synthetic_events: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    run_id = str(trigger_run["run_id"])
    event_lookup = {str(event["event_type"]): event for event in synthetic_events}
    state_keys = {state_key(plan) for plan in plans}
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_run_once_execute_transaction",
        source_run_id=run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            assert_trigger_run_ready(cur, run_id)
            assert_no_existing_n4_5_outputs(cur, run_id)
            quality_count = insert_quality_items(cur, trigger_run=trigger_run, items=quality_items)
            for plan in plans:
                execute_plan(cur, trigger_run=trigger_run, plan=plan, event=event_lookup[str(plan["source_event_type"])])
        conn.commit()
    return {
        "common_trigger_state": len(state_keys),
        "common_trigger_match": len(plans),
        "common_event_outbox": len(plans),
        "common_trigger_quality_item": quality_count,
    }


def execute_plan(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    trigger_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    run_id = str(trigger_run["run_id"])
    event_time = parse_synthetic_event_time(str(event["event_time"]))
    current_status = "matched" if plan["output_event_type"] == "TriggerMatched" else "pending_market_data"
    state_id = upsert_trigger_state(
        cur,
        trigger_run=trigger_run,
        plan=plan,
        event_time=event_time,
        current_status=current_status,
    )
    dedup_key = build_run_once_dedup_key(
        event_type=str(plan["output_event_type"]),
        trade_date=str(trigger_run["for_trade_date"]),
        plan=plan,
    )
    output_event_id = build_stable_event_id(
        source_layer=N4_SOURCE_LAYER,
        event_type=str(plan["output_event_type"]),
        source_run_id=run_id,
        dedup_key=dedup_key,
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
    )
    match_id = insert_trigger_match(
        cur,
        trigger_run=trigger_run,
        plan=plan,
        trigger_state_id=state_id,
        trigger_time=event_time,
        output_event_id=output_event_id,
        dedup_key=dedup_key,
        event=event,
    )
    update_state_last_match(cur, trigger_state_id=state_id, trigger_match_id=match_id)
    envelope = build_output_event_envelope(
        trigger_run=trigger_run,
        plan=plan,
        event=event,
        event_time=event_time,
        output_event_id=output_event_id,
        dedup_key=dedup_key,
        trigger_state_id=state_id,
        trigger_match_id=match_id,
    )
    insert_outbox_envelope(cur, envelope)


def upsert_trigger_state(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    trigger_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    event_time: datetime,
    current_status: str,
) -> int:
    matched = current_status == "matched"
    cur.execute(
        """
        INSERT INTO common_trigger_state (
          run_id, source_condition_run_id, for_trade_date, asset_kind,
          identity_key, direction, signal_type, condition_key, trigger_period,
          trigger_bucket, current_status, last_source_event_id,
          data_quality_status, context_hash, match_count, first_matched_at,
          last_matched_at, raw_json, updated_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s,
          %(asset_kind)s, %(identity_key)s, %(direction)s, %(signal_type)s,
          %(condition_key)s, %(trigger_period)s, %(trigger_bucket)s,
          %(current_status)s, %(last_source_event_id)s, %(data_quality_status)s,
          %(context_hash)s, %(match_count)s, %(first_matched_at)s,
          %(last_matched_at)s, %(raw_json)s, now()
        )
        ON CONFLICT (
          run_id, for_trade_date, asset_kind, identity_key, direction,
          signal_type, condition_key, trigger_period, trigger_bucket
        )
        DO UPDATE SET
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
            "run_id": trigger_run["run_id"],
            "source_condition_run_id": plan["source_condition_run_id"],
            "for_trade_date": trigger_run["for_trade_date"],
            "asset_kind": plan["asset_kind"],
            "identity_key": plan["identity_key"],
            "direction": plan["direction"],
            "signal_type": plan["signal_type"],
            "condition_key": plan["condition_key"],
            "trigger_period": plan["trigger_period"],
            "trigger_bucket": plan["trigger_bucket"],
            "current_status": current_status,
            "last_source_event_id": plan["source_event_id"],
            "data_quality_status": plan["data_quality_status"],
            "context_hash": plan.get("context_hash"),
            "match_count": 1 if matched else 0,
            "first_matched_at": event_time if matched else None,
            "last_matched_at": event_time if matched else None,
            "raw_json": Jsonb({"stage": "N4-5", "plan": dict(plan)}),
        },
    )
    return int(cur.fetchone()["trigger_state_id"])


def insert_trigger_match(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    trigger_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    trigger_state_id: int,
    trigger_time: datetime,
    output_event_id: str,
    dedup_key: str,
    event: Mapping[str, Any],
) -> int:
    cur.execute(
        """
        INSERT INTO common_trigger_match (
          run_id, trigger_state_id, source_event_id, source_event_type,
          source_condition_run_id, source_condition_pool_id,
          source_condition_basis_id, source_market_subscription_id,
          for_trade_date, asset_kind, identity_key, direction, signal_type,
          condition_key, trigger_time, trigger_period, trigger_bucket,
          data_quality_status, output_event_type, output_event_id, dedup_key,
          context_hash, raw_json
        )
        VALUES (
          %(run_id)s, %(trigger_state_id)s, %(source_event_id)s,
          %(source_event_type)s, %(source_condition_run_id)s,
          %(source_condition_pool_id)s, %(source_condition_basis_id)s,
          %(source_market_subscription_id)s, %(for_trade_date)s,
          %(asset_kind)s, %(identity_key)s, %(direction)s, %(signal_type)s,
          %(condition_key)s, %(trigger_time)s, %(trigger_period)s,
          %(trigger_bucket)s, %(data_quality_status)s, %(output_event_type)s,
          %(output_event_id)s, %(dedup_key)s, %(context_hash)s, %(raw_json)s
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
          raw_json = EXCLUDED.raw_json
        RETURNING trigger_match_id
        """,
        {
            "run_id": trigger_run["run_id"],
            "trigger_state_id": trigger_state_id,
            "source_event_id": plan["source_event_id"],
            "source_event_type": plan["source_event_type"],
            "source_condition_run_id": plan["source_condition_run_id"],
            "source_condition_pool_id": plan.get("source_condition_pool_id"),
            "source_condition_basis_id": plan.get("source_condition_basis_id"),
            "source_market_subscription_id": plan.get("source_market_subscription_id"),
            "for_trade_date": trigger_run["for_trade_date"],
            "asset_kind": plan["asset_kind"],
            "identity_key": plan["identity_key"],
            "direction": plan["direction"],
            "signal_type": plan["signal_type"],
            "condition_key": plan["condition_key"],
            "trigger_time": trigger_time,
            "trigger_period": plan["trigger_period"],
            "trigger_bucket": plan["trigger_bucket"],
            "data_quality_status": plan["data_quality_status"],
            "output_event_type": plan["output_event_type"],
            "output_event_id": output_event_id,
            "dedup_key": dedup_key,
            "context_hash": plan.get("context_hash"),
            "raw_json": Jsonb({"stage": "N4-5", "plan": dict(plan), "synthetic_event": dict(event)}),
        },
    )
    return int(cur.fetchone()["trigger_match_id"])


def update_state_last_match(
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


def build_output_event_envelope(
    *,
    trigger_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    event: Mapping[str, Any],
    event_time: datetime,
    output_event_id: str,
    dedup_key: str,
    trigger_state_id: int,
    trigger_match_id: int,
) -> EventEnvelope:
    payload = build_output_event_payload(
        trigger_run=trigger_run,
        plan=plan,
        event=event,
        trigger_state_id=trigger_state_id,
        trigger_match_id=trigger_match_id,
    )
    envelope = EventEnvelope(
        event_id=output_event_id,
        event_type=str(plan["output_event_type"]),
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        trade_date=str(trigger_run["for_trade_date"]),
        asset_kind=str(plan["asset_kind"]),
        identity_key=str(plan["identity_key"]),
        event_time=event_time,
        source_layer=N4_SOURCE_LAYER,
        source_run_id=str(trigger_run["run_id"]),
        dedup_key=dedup_key,
        partition_key=str(plan["identity_key"]),
        payload_json=payload,
        created_at=utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def build_output_event_payload(
    *,
    trigger_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    event: Mapping[str, Any],
    trigger_state_id: int,
    trigger_match_id: int,
) -> dict[str, Any]:
    return {
        "run_id": trigger_run["run_id"],
        "source_event_id": plan["source_event_id"],
        "source_event_type": plan["source_event_type"],
        "context_snapshot_id": plan.get("context_snapshot_id"),
        "trigger_state_id": trigger_state_id,
        "trigger_match_id": trigger_match_id,
        "identity_key": plan["identity_key"],
        "asset_kind": plan["asset_kind"],
        "direction": plan["direction"],
        "condition_key": plan["condition_key"],
        "signal_type": plan["signal_type"],
        "trigger_mark_candidate": plan["trigger_mark_candidate"],
        "trigger_period": plan["trigger_period"],
        "trigger_bucket": plan["trigger_bucket"],
        "data_quality_status": plan["data_quality_status"],
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "source_condition_pool_id": plan.get("source_condition_pool_id"),
        "source_condition_basis_id": plan.get("source_condition_basis_id"),
        "source_minute_target_scope_id": plan.get("source_minute_target_scope_id"),
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "context_hash": plan.get("context_hash"),
        "period_trigger_baseline_trace": plan.get("period_trigger_baseline_trace") or {},
        "synthetic_sample_event": True,
        "synthetic_event_type": event.get("event_type"),
        "synthetic_event_id": event.get("event_id"),
        "n4_boundary": {
            "market_data_pulled": False,
            "real_n3_event_consumed": False,
            "downstream_layers_touched": False,
        },
    }


def insert_outbox_envelope(cur: psycopg.Cursor[dict[str, Any]], envelope: EventEnvelope) -> str:
    record = envelope.as_record()
    values = [
        Jsonb(record[column]) if column == "payload_json" else record[column]
        for column in OUTBOX_COLUMNS
    ]
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


def build_run_once_dedup_key(
    *,
    event_type: str,
    trade_date: str,
    plan: Mapping[str, Any],
) -> str:
    return join_dedup_parts(
        "N4_trigger",
        event_type,
        str(plan["source_event_id"]),
        str(plan["source_event_type"]),
        str(plan["asset_kind"]),
        str(plan["identity_key"]),
        trade_date,
        "direction",
        str(plan["direction"]),
        "signal_type",
        str(plan["signal_type"]),
        "trigger_mark_candidate",
        str(plan.get("trigger_mark_candidate") or "normal"),
        "condition_key",
        str(plan["condition_key"]),
        "trigger_period",
        str(plan["trigger_period"]),
        "trigger_bucket",
        str(plan["trigger_bucket"]),
    )


def assert_trigger_run_ready(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> None:
    cur.execute(
        """
        SELECT run_id, status, mode, context_snapshot_row_count, source_condition_run_id
        FROM common_trigger_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = normalize_mapping(cur.fetchone() or {})
    if not row:
        raise RuntimeError(f"N4-5 blocked: trigger context run not found: {run_id}")
    if row.get("status") != "passed" or int(row.get("context_snapshot_row_count") or 0) <= 0:
        raise RuntimeError(f"N4-5 blocked: trigger context run is not passed and populated: {row}")


def assert_no_existing_n4_5_outputs(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> None:
    counts = fetch_existing_n4_5_counts(cur, run_id)
    nonzero = {key: value for key, value in counts.items() if value > 0}
    if nonzero:
        raise RuntimeError(f"N4-5 blocked: existing trigger outputs require explicit rollback/overwrite: {nonzero}")


def fetch_existing_n4_5_counts(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, int]:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_trigger_state WHERE run_id = %s", (run_id,))
    state_count = int(cur.fetchone()["row_count"])
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_trigger_match WHERE run_id = %s", (run_id,))
    match_count = int(cur.fetchone()["row_count"])
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
        """,
        (run_id,),
    )
    outbox_count = int(cur.fetchone()["row_count"])
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_trigger_quality_item
        WHERE run_id = %s
          AND gate_code LIKE %s
        """,
        (run_id, f"{N4_5_QUALITY_PREFIX}%"),
    )
    quality_count = int(cur.fetchone()["row_count"])
    return {
        "common_trigger_state": state_count,
        "common_trigger_match": match_count,
        "common_event_outbox": outbox_count,
        "common_trigger_quality_item": quality_count,
    }


def insert_quality_items(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    trigger_run: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
) -> int:
    if not items:
        return 0
    rows = []
    for item in items:
        gate_code = str(item.get("gate_code") or "")
        rows.append(
            (
                trigger_run["run_id"],
                trigger_run["source_condition_run_id"],
                trigger_run["for_trade_date"],
                trigger_run["source_trade_date"],
                "common",
                infer_quality_scope(gate_code),
                infer_quality_table(gate_code),
                gate_code,
                str(item.get("gate_name") or gate_code),
                str(item.get("severity") or "P0"),
                str(item.get("status") or "passed"),
                item.get("expected_value"),
                item.get("actual_value"),
                None,
                Jsonb(item.get("details") or {}),
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


def append_quality_items(
    *,
    dsn: str,
    trigger_run: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
) -> int:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_run_once_append_quality_items",
        source_run_id=str(trigger_run.get("run_id") or "n4_run_once"),
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            inserted = insert_quality_items(cur, trigger_run=trigger_run, items=items)
        conn.commit()
    return inserted


def build_pre_execute_quality_items(
    *,
    trigger_context_run_id: str,
    trigger_run: Mapping[str, Any],
    dry_run_report: Mapping[str, Any],
    plans: Sequence[Mapping[str, Any]],
    synthetic_events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    summary = summarize_plans(plans)
    event_types = {str(event.get("event_type") or "") for event in synthetic_events}
    output_event_types = {str(plan.get("output_event_type") or "") for plan in plans}
    pending_source_event_types = {
        str(plan.get("source_event_type") or "")
        for plan in plans
        if plan.get("output_event_type") == "TriggerPendingMarketData"
    }
    return [
        quality_item(
            "P0",
            "passed" if trigger_run.get("run_id") == trigger_context_run_id and trigger_run.get("status") == "passed" else "failed",
            "n4_5_trigger_context_run_ready",
            "N4-5 must execute against the passed local trigger context run",
            expected=trigger_context_run_id,
            actual=str(trigger_run.get("run_id")),
        ),
        quality_item(
            "P0",
            "passed" if int(dry_run_report["quality"]["p0_count"]) == 0 else "failed",
            "n4_5_dry_run_precheck_p0_zero",
            "N4-5 must rerun N4-4 dry-run with P0=0 before execute",
            expected="0",
            actual=str(dry_run_report["quality"]["p0_count"]),
        ),
        quality_item(
            "P0",
            "passed" if len(plans) == int(dry_run_report["candidate_count"]) else "failed",
            "n4_5_plan_count_matches_dry_run",
            "N4-5 execute plans must match N4-4 dry-run candidate count",
            expected=str(dry_run_report["candidate_count"]),
            actual=str(len(plans)),
        ),
        quality_item(
            "P0",
            "passed" if summary["matched_count"] == int(dry_run_report["matched_count"]) else "failed",
            "n4_5_matched_count_matches_dry_run",
            "N4-5 matched count must match N4-4 dry-run",
            expected=str(dry_run_report["matched_count"]),
            actual=str(summary["matched_count"]),
        ),
        quality_item(
            "P0",
            "passed" if summary["pending_count"] == int(dry_run_report["pending_count"]) else "failed",
            "n4_5_pending_count_matches_dry_run",
            "N4-5 pending count must match N4-4 dry-run",
            expected=str(dry_run_report["pending_count"]),
            actual=str(summary["pending_count"]),
        ),
        quality_item(
            "P0",
            "passed" if event_types == set(SYNTHETIC_EVENT_TYPES) else "failed",
            "n4_5_uses_synthetic_event_types",
            "N4-5 must use synthetic/sample N3 events only",
            expected=",".join(SYNTHETIC_EVENT_TYPES),
            actual=",".join(sorted(event_types)),
        ),
        quality_item(
            "P0",
            "passed" if output_event_types <= set(EXECUTED_N4_OUTPUT_EVENT_TYPES) else "failed",
            "n4_5_output_event_types_allowed",
            "N4-5 must only plan allowed N4 output event types for this run",
            expected=",".join(EXECUTED_N4_OUTPUT_EVENT_TYPES),
            actual=",".join(sorted(output_event_types)),
        ),
        quality_item(
            "P0",
            "passed" if pending_source_event_types == {"MarketDataDelayed", "MarketDataMissing"} else "failed",
            "n4_5_pending_only_from_quality_events",
            "N4-5 pending outputs must come only from market-data quality events",
            expected="MarketDataDelayed,MarketDataMissing",
            actual=",".join(sorted(pending_source_event_types)),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("buy_hint_matched_count") or 0) > 0 and int(summary.get("sell_hint_matched_count") or 0) > 0 else "failed",
            "n4_5_buy_hint_sell_hint_formal_candidates",
            "BUY_HINT and SELL_HINT condition_key traces must enter N4 matched trigger candidates",
            expected="BUY_HINT>0 SELL_HINT>0",
            actual=f"BUY_HINT={summary.get('buy_hint_matched_count', 0)} SELL_HINT={summary.get('sell_hint_matched_count', 0)}",
        ),
        quality_item(
            "P0",
            "passed" if int(dry_run_report.get("period_trigger_baseline_trace_count") or 0) == len(plans) else "failed",
            "n4_5_period_trigger_baseline_trace_available",
            "N4-5 must preserve period_trigger_baseline_trace from accepted dry-run plans",
            expected=str(len(plans)),
            actual=str(dry_run_report.get("period_trigger_baseline_trace_count")),
        ),
        quality_item("P0", "passed", "n4_5_no_market_data_pull", "N4-5 does not pull market data"),
        quality_item("P0", "passed", "n4_5_no_real_n3_outbox_consumption", "N4-5 does not consume real N3 outbox events"),
        quality_item("P0", "passed", "n4_5_no_worker_or_downstream", "N4-5 does not start workers or enter downstream layers"),
    ]


def build_post_quality_items(post_checks: Mapping[str, bool]) -> list[dict[str, Any]]:
    return [
        quality_item(
            "P0",
            "passed" if passed else "failed",
            f"n4_5_{check_name}",
            f"N4-5 post execute check: {check_name}",
            expected="true",
            actual=str(passed).lower(),
        )
        for check_name, passed in post_checks.items()
    ]


def build_post_execute_checks(
    *,
    dry_run_report: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    inserted_counts: Mapping[str, int],
    output_summary: Mapping[str, Any],
    expected_quality_delta: int | None,
) -> dict[str, bool]:
    before_counts = before_snapshot["row_counts"]
    after_counts = after_snapshot["row_counts"]
    state_delta = row_count_delta(before_counts, after_counts, "common_trigger_state")
    match_delta = row_count_delta(before_counts, after_counts, "common_trigger_match")
    outbox_delta = row_count_delta(before_counts, after_counts, "common_event_outbox")
    checks = {
        "trigger_state_delta_matches_plan": state_delta == int(inserted_counts["common_trigger_state"]),
        "trigger_match_delta_matches_plan": match_delta == int(inserted_counts["common_trigger_match"]),
        "event_outbox_delta_matches_plan": outbox_delta == int(inserted_counts["common_event_outbox"]),
        "matched_count_matches_dry_run": int(output_summary["matched_count"]) == int(dry_run_report["matched_count"]),
        "pending_count_matches_dry_run": int(output_summary["pending_count"]) == int(dry_run_report["pending_count"]),
        "period_trigger_baseline_trace_preserved": int(output_summary["period_trigger_baseline_trace_count"])
        == int(dry_run_report.get("period_trigger_baseline_trace_count") or 0),
        "buy_hint_and_sell_hint_written": int(output_summary["buy_hint_matched_count"]) > 0
        and int(output_summary["sell_hint_matched_count"]) > 0,
        "outbox_event_types_allowed": not output_summary["disallowed_outbox_event_types"],
        "outbox_payload_contract_passed": int(output_summary["payload_contract_violation_count"]) == 0,
        "n2_active_run_unchanged": before_snapshot["condition_run_snapshot"] == after_snapshot["condition_run_snapshot"],
        "n3_fact_rows_unchanged": before_snapshot["n3_fact_row_counts"] == after_snapshot["n3_fact_row_counts"],
        "n3_outbox_rows_unchanged": before_snapshot["n3_outbox_row_count"] == after_snapshot["n3_outbox_row_count"],
        "downstream_rows_unchanged": before_snapshot["downstream_row_counts"] == after_snapshot["downstream_row_counts"],
        "trigger_run_not_updated": before_counts["common_trigger_run"] == after_counts["common_trigger_run"],
    }
    if expected_quality_delta is not None:
        checks["quality_item_delta_matches_plan"] = (
            row_count_delta(before_counts, after_counts, "common_trigger_quality_item") == expected_quality_delta
        )
    return checks


def capture_run_once_snapshot(
    dsn: str,
    *,
    phase: str,
    condition_run_id: str,
    trigger_run_id: str,
) -> dict[str, Any]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id=f"n4_run_once_capture_{phase}",
        source_run_id=trigger_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return {
            "phase": phase,
            "captured_at": utc_now_iso(),
            "row_counts": fetch_row_counts(cur, N4_COUNT_TABLES),
            "n3_fact_row_counts": fetch_row_counts(cur, N3_FACT_GUARD_TABLES),
            "n3_outbox_row_count": fetch_outbox_count_by_source(cur, "N3_market_data"),
            "n4_outbox_row_count_for_run": fetch_outbox_count_for_run(cur, trigger_run_id),
            "condition_run_snapshot": fetch_condition_run_snapshot(cur, condition_run_id),
            "downstream_row_counts": fetch_downstream_row_counts(cur),
        }


def fetch_output_summary(dsn: str, run_id: str) -> dict[str, Any]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_run_once_fetch_output_summary",
        source_run_id=run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        match_rows = fetch_trigger_match_rows(cur, run_id)
        cur.execute(
            """
            SELECT event_type, payload_json
            FROM common_event_outbox
            WHERE source_layer = 'N4_trigger'
              AND source_run_id = %s
            """,
            (run_id,),
        )
        outbox_rows = [normalize_mapping(row) for row in cur.fetchall()]
    matched_rows = [row for row in match_rows if row.get("output_event_type") == "TriggerMatched"]
    pending_rows = [row for row in match_rows if row.get("output_event_type") == "TriggerPendingMarketData"]
    payload_violations = find_payload_contract_violations(outbox_rows)
    outbox_event_types = sorted({str(row.get("event_type") or "") for row in outbox_rows})
    return {
        "state_count": count_distinct_state_keys(match_rows),
        "match_count": len(match_rows),
        "outbox_count": len(outbox_rows),
        "matched_count": len(matched_rows),
        "pending_count": len(pending_rows),
        "match_by_output_event_type": count_by(match_rows, "output_event_type"),
        "outbox_by_event_type": dict(sorted(Counter(str(row.get("event_type") or "") for row in outbox_rows).items())),
        "match_by_signal_type": count_by(match_rows, "signal_type"),
        "matched_by_signal_type": count_by(matched_rows, "signal_type"),
        "pending_by_signal_type": count_by(pending_rows, "signal_type"),
        "match_by_source_event_type": count_by(match_rows, "source_event_type"),
        "match_by_asset_kind": count_by(match_rows, "asset_kind"),
        "match_by_direction": count_by(match_rows, "direction"),
        "trigger_period_distribution": count_by(match_rows, "trigger_period"),
        "buy_hint_matched_count": sum(1 for row in matched_rows if row.get("condition_key") == "BUY_HINT"),
        "sell_hint_matched_count": sum(1 for row in matched_rows if row.get("condition_key") == "SELL_HINT"),
        "buy_hint_trigger_match_count": sum(1 for row in match_rows if row.get("condition_key") == "BUY_HINT"),
        "sell_hint_trigger_match_count": sum(1 for row in match_rows if row.get("condition_key") == "SELL_HINT"),
        "outbox_event_types": outbox_event_types,
        "disallowed_outbox_event_types": list_disallowed_outbox_event_types(outbox_event_types),
        "payload_contract_violation_count": len(payload_violations),
        "payload_contract_violations_sample": payload_violations[:20],
        "period_trigger_baseline_trace_count": sum(
            1
            for row in outbox_rows
            if (row.get("payload_json") or {}).get("period_trigger_baseline_trace", {}).get("present")
        ),
    }


def fetch_trigger_match_rows(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT run_id, trigger_state_id, source_event_id, source_event_type,
               source_condition_run_id, source_condition_pool_id,
               source_condition_basis_id, source_market_subscription_id,
               for_trade_date, asset_kind, identity_key, direction, signal_type,
               condition_key, trigger_period, trigger_bucket,
               data_quality_status, output_event_type, output_event_id,
               dedup_key, context_hash
        FROM common_trigger_match
        WHERE run_id = %s
        ORDER BY trigger_match_id
        """,
        (run_id,),
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def find_payload_contract_violations(outbox_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    violations = []
    for row in outbox_rows:
        if row.get("event_type") != "TriggerMatched":
            continue
        payload = row.get("payload_json") or {}
        missing = [
            key
            for key in REQUIRED_TRIGGER_MATCHED_PAYLOAD_KEYS
            if payload.get(key) is None or payload.get(key) == ""
        ]
        if missing:
            violations.append({"event_type": row.get("event_type"), "missing_keys": missing})
    return violations


def list_disallowed_outbox_event_types(event_types: Sequence[str]) -> list[str]:
    return sorted(set(event_types) - set(ALLOWED_N4_OUTPUT_EVENT_TYPES))


def fetch_row_counts(cur: psycopg.Cursor[dict[str, Any]], table_names: Sequence[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for table_name in table_names:
        if not table_exists(cur, table_name):
            output[table_name] = {"exists": False, "row_count": None, "status": "missing"}
            continue
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
        output[table_name] = {"exists": True, "row_count": int(cur.fetchone()["row_count"]), "status": "present"}
    return output


def table_exists(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
    return cur.fetchone()["regclass"] is not None


def fetch_outbox_count_by_source(cur: psycopg.Cursor[dict[str, Any]], source_layer: str) -> int | None:
    if not table_exists(cur, "common_event_outbox"):
        return None
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_event_outbox
        WHERE source_layer = %s
        """,
        (source_layer,),
    )
    return int(cur.fetchone()["row_count"])


def fetch_outbox_count_for_run(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> int | None:
    if not table_exists(cur, "common_event_outbox"):
        return None
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
        """,
        (run_id,),
    )
    return int(cur.fetchone()["row_count"])


def fetch_condition_run_snapshot(cur: psycopg.Cursor[dict[str, Any]], condition_run_id: str) -> dict[str, Any]:
    if not condition_run_id or not table_exists(cur, "common_condition_run"):
        return {}
    cur.execute(
        """
        SELECT run_id, status, source_trade_date, for_trade_date, prev_trade_date,
               p0_count, p1_count, p2_count, source_versions, raw_json, finished_at, updated_at
        FROM common_condition_run
        WHERE run_id = %s
        """,
        (condition_run_id,),
    )
    row = cur.fetchone()
    return normalize_mapping(row) if row else {}


def fetch_downstream_row_counts(cur: psycopg.Cursor[dict[str, Any]]) -> dict[str, int]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name ~ '^(common_)?(action|user|voice|sim|position)_'
        ORDER BY table_name
        """
    )
    table_names = [str(row["table_name"]) for row in cur.fetchall()]
    output: dict[str, int] = {}
    for table_name in table_names:
        cur.execute(
            pg_sql.SQL("SELECT count(*)::bigint AS row_count FROM {}").format(
                pg_sql.Identifier("public", table_name)
            )
        )
        output[table_name] = int(cur.fetchone()["row_count"])
    return output


def row_count_delta(
    before_counts: Mapping[str, Mapping[str, Any]],
    after_counts: Mapping[str, Mapping[str, Any]],
    table_name: str,
) -> int:
    before = int(before_counts[table_name]["row_count"] or 0)
    after = int(after_counts[table_name]["row_count"] or 0)
    return after - before


def state_key(plan: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(plan.get("asset_kind") or ""),
        str(plan.get("identity_key") or ""),
        str(plan.get("direction") or ""),
        str(plan.get("signal_type") or ""),
        str(plan.get("condition_key") or ""),
        str(plan.get("trigger_period") or ""),
        str(plan.get("trigger_bucket") or ""),
    )


def count_distinct_state_keys(rows: Sequence[Mapping[str, Any]]) -> int:
    return len({state_key(row) for row in rows})


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def infer_quality_scope(gate_code: str) -> str:
    if "state" in gate_code:
        return "trigger_state"
    if "match" in gate_code:
        return "trigger_match"
    if "event" in gate_code or "outbox" in gate_code or "payload" in gate_code:
        return "event_contract"
    if "run" in gate_code:
        return "trigger_run"
    return "trigger_run"


def infer_quality_table(gate_code: str) -> str | None:
    if "state" in gate_code:
        return "common_trigger_state"
    if "match" in gate_code:
        return "common_trigger_match"
    if "event" in gate_code or "outbox" in gate_code:
        return "common_event_outbox"
    if "run" in gate_code:
        return "common_trigger_run"
    return None


def parse_synthetic_event_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%dT%H:%M:%S%z")


def summarize_dry_run_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": report.get("stage"),
        "trigger_context_run_id": report.get("trigger_context_run_id"),
        "candidate_count": report.get("candidate_count"),
        "matched_count": report.get("matched_count"),
        "pending_count": report.get("pending_count"),
        "buy_hint_matched_count": report.get("summary", {}).get("buy_hint_matched_count"),
        "sell_hint_matched_count": report.get("summary", {}).get("sell_hint_matched_count"),
        "period_trigger_baseline_trace_count": report.get("period_trigger_baseline_trace_count"),
        "p0_count": report.get("quality", {}).get("p0_count"),
        "p1_count": report.get("quality", {}).get("p1_count"),
        "p2_count": report.get("quality", {}).get("p2_count"),
    }


def build_trigger_run_once_rollback_sql(run_id: str) -> str:
    return "\n".join(
        [
            "-- A-share monitor v3 N4-5 trigger run-once rollback.",
            "-- Execute only before downstream layers consume this N4 outbox.",
            "-- This rollback deletes only N4-5 state/match/quality/outbox rows for one run_id.",
            "",
            "BEGIN;",
            "",
            "DELETE FROM common_event_outbox",
            "WHERE source_layer = 'N4_trigger'",
            f"  AND source_run_id = '{run_id}';",
            "",
            f"DELETE FROM common_trigger_match WHERE run_id = '{run_id}';",
            f"DELETE FROM common_trigger_state WHERE run_id = '{run_id}';",
            "DELETE FROM common_trigger_quality_item",
            f"WHERE run_id = '{run_id}'",
            f"  AND gate_code LIKE '{N4_5_QUALITY_PREFIX}%';",
            "",
            "COMMIT;",
            "",
            "-- Boundary:",
            "-- - Does not touch common_trigger_run or trigger_context_snapshot rows.",
            "-- - Does not touch common_condition_run or condition tables.",
            "-- - Does not touch common_market_data_* or market data fact tables.",
            "-- - Does not touch downstream layer tables.",
            "",
        ]
    )


def format_trigger_run_once_execute_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    output = report["output_summary"]
    lines = [
        f"# {report['stage']} Trigger Run-Once Execute Report",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- run_id: {report['run_id']}",
        f"- source_condition_run_id: {report['source_condition_run_id']}",
        f"- for_trade_date: {report['for_trade_date']}",
        f"- rollback_sql_path: {report['rollback_sql_path']}",
        f"- started_at: {report['started_at']}",
        f"- finished_at: {report['finished_at']}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Dry-Run Match",
        "",
        f"- dry_run_candidate_count: {report['dry_run_precheck_report']['candidate_count']}",
        f"- dry_run_matched_count: {report['dry_run_precheck_report']['matched_count']}",
        f"- dry_run_pending_count: {report['dry_run_precheck_report']['pending_count']}",
        f"- dry_run_period_trigger_baseline_trace_count: {report['dry_run_precheck_report'].get('period_trigger_baseline_trace_count')}",
        f"- executed_matched_count: {output['matched_count']}",
        f"- executed_pending_count: {output['pending_count']}",
        f"- executed_period_trigger_baseline_trace_count: {output.get('period_trigger_baseline_trace_count')}",
        "",
        "## Write Counts",
        "",
    ]
    for table_name, count in report["inserted_counts"].items():
        lines.append(f"- {table_name}: {count}")
    lines.extend(
        [
            "",
            "## Output Summary",
            "",
            f"- match_by_output_event_type: {output['match_by_output_event_type']}",
            f"- outbox_by_event_type: {output['outbox_by_event_type']}",
            f"- matched_by_signal_type: {output['matched_by_signal_type']}",
            f"- pending_by_signal_type: {output['pending_by_signal_type']}",
            f"- trigger_period_distribution: {output['trigger_period_distribution']}",
            f"- buy_hint_matched_count: {output['buy_hint_matched_count']}",
            f"- sell_hint_matched_count: {output['sell_hint_matched_count']}",
            f"- period_trigger_baseline_trace_count: {output.get('period_trigger_baseline_trace_count')}",
            f"- payload_contract_violation_count: {output['payload_contract_violation_count']}",
            f"- disallowed_outbox_event_types: {output['disallowed_outbox_event_types']}",
            "",
            "## Before / After Row Counts",
            "",
        ]
    )
    for table_name in ("common_trigger_state", "common_trigger_match", "common_trigger_quality_item", "common_event_outbox"):
        before = report["before_row_counts"].get(table_name, {}).get("row_count")
        after = report["after_row_counts"].get(table_name, {}).get("row_count")
        lines.append(f"- {table_name}: before={before} after={after}")
    lines.extend(["", "## Post Checks", ""])
    for check_name, passed in report["post_checks"].items():
        lines.append(f"- {check_name}: {str(passed).lower()}")
    lines.extend(["", "## Boundary Confirmation", ""])
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.extend(
        [
            "",
            "## Rollback",
            "",
            f"Rollback SQL: {report['rollback_sql_path']}",
            "",
            "Use it only before downstream consumption. It deletes this run_id's N4-5 common_event_outbox, "
            "common_trigger_match, common_trigger_state, and n4_5_* quality rows.",
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
