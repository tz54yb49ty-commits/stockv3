"""N5-1 N4 event consumer dry-run.

This module plans how an N5 consumer would read N4 standard events, order them
by partition, deduplicate them, and advance watermark/checkpoint state. It is
read-only: it never writes inbox/checkpoint rows, action facts, N5 outbox, user
projection, voice, sim, or trading rows.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.action.query_audit_phase2 import audited_n5_readonly_plan_connect
from ashare_v3.action.dry_run import (
    ALLOWED_N4_INPUT_EVENT_TYPES,
    build_action_candidates_from_outbox_rows,
    summarize_action_candidates,
)
from ashare_v3.action.preflight import (
    DEFAULT_TRIGGER_RUN_ID,
    ROW_COUNT_GUARD_TABLES,
    fetch_n4_outbox_rows,
    fetch_row_counts,
    fetch_trigger_run,
    normalize_outbox_row,
    summarize_outbox_rows,
    table_exists,
)
from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item


DEFAULT_N5_1_JSON_REPORT_PATH = "docs/N5_1_action_consumer_dry_run_report.json"
DEFAULT_N5_1_MD_REPORT_PATH = "docs/N5_1_ACTION_CONSUMER_DRY_RUN_REPORT.md"
DEFAULT_N5_1_CONSUMER_NAME = "n5_action_consumer_v1"
DEFAULT_N5_1_ACTION_RUN_ID = (
    "action_consumer_dry_run_20260525_trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029"
)
CONSUMER_SOURCE_LAYER = "N4_trigger"
CONSUMER_ORDERING = ("partition_key", "event_time", "outbox_id", "event_id")


def run_action_consumer_dry_run(
    *,
    dsn: str,
    trigger_run_id: str = DEFAULT_TRIGGER_RUN_ID,
    action_run_id: str = DEFAULT_N5_1_ACTION_RUN_ID,
    consumer_name: str = DEFAULT_N5_1_CONSUMER_NAME,
    json_report_path: str = DEFAULT_N5_1_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_1_MD_REPORT_PATH,
    sample_limit: int = 80,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_consumer_dry_run",
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
        after_counts = fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES)

    report = build_action_consumer_dry_run_report_from_rows(
        trigger_run_id=trigger_run_id,
        action_run_id=action_run_id,
        consumer_name=consumer_name,
        trigger_run=trigger_run,
        outbox_rows=outbox_rows,
        existing_inbox_keys=existing_inbox_keys,
        existing_checkpoints=existing_checkpoints,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        started_at=started_at,
        finished_at=utc_now_iso(),
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        sample_limit=sample_limit,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_action_consumer_dry_run_report(report))
    return report


def build_action_consumer_dry_run_report_from_rows(
    *,
    trigger_run_id: str,
    action_run_id: str,
    consumer_name: str,
    trigger_run: Mapping[str, Any] | None,
    outbox_rows: Sequence[Mapping[str, Any]],
    existing_inbox_keys: Mapping[str, set[str]] | None = None,
    existing_checkpoints: Mapping[str, Mapping[str, Any]] | None = None,
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    json_report_path: str = DEFAULT_N5_1_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_1_MD_REPORT_PATH,
    sample_limit: int = 80,
) -> dict[str, Any]:
    normalized_rows = [normalize_outbox_row(row) for row in outbox_rows]
    consumer_plan = build_consumer_plan(
        rows=normalized_rows,
        consumer_name=consumer_name,
        existing_inbox_keys=existing_inbox_keys or empty_inbox_keys(),
        existing_checkpoints=existing_checkpoints or {},
    )
    accepted_rows = [item["source_outbox_row"] for item in consumer_plan["event_plans"] if item["consumer_status"] == "planned_receive"]
    candidates = build_action_candidates_from_outbox_rows(accepted_rows, action_run_id=action_run_id)
    outbox_summary = summarize_outbox_rows(normalized_rows)
    candidate_summary = summarize_action_candidates(candidates)
    quality_items = build_quality_items(
        trigger_run_id=trigger_run_id,
        consumer_name=consumer_name,
        trigger_run=trigger_run or {},
        outbox_summary=outbox_summary,
        consumer_plan=consumer_plan,
        candidate_summary=candidate_summary,
        before_row_counts=before_row_counts or {},
        after_row_counts=after_row_counts or {},
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": "N5-1",
        "layer_role": "N5_action",
        "mode": "n4_event_consumption_dry_run",
        "execution_mode": "read_only_n4_outbox_consumer_plan",
        "action_run_id": action_run_id,
        "consumer_name": consumer_name,
        "source_trigger_run_id": trigger_run_id,
        "source_trigger_run": normalize_mapping(trigger_run or {}),
        "for_trade_date": (trigger_run or {}).get("for_trade_date") or infer_trade_date(normalized_rows),
        "started_at": started_at or utc_now_iso(),
        "finished_at": finished_at or utc_now_iso(),
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "consumer_contract": build_consumer_contract(consumer_name),
        "outbox_summary": outbox_summary,
        "consumer_plan_summary": summarize_consumer_plan(consumer_plan),
        "action_candidate_summary": candidate_summary,
        "checkpoint_write_plan": consumer_plan["checkpoint_write_plan"],
        "sample_event_plans": compact_event_plans(consumer_plan["event_plans"], sample_limit),
        "sample_action_candidates": candidates[:sample_limit],
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "before_row_counts": before_row_counts or {},
        "after_row_counts": after_row_counts or {},
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "writes_performed": False,
            "action_fact_written": False,
            "action_event_written": False,
            "position_event_written": False,
            "common_event_outbox_written": False,
            "common_event_inbox_updated": False,
            "consumer_checkpoint_updated": False,
            "n4_outbox_status_updated": False,
            "market_data_pulled": False,
            "real_n3_event_consumed": False,
            "real_n4_outbox_consumed": False,
            "trigger_layer_mutated": False,
            "user_layer_touched": False,
            "voice_touched": False,
            "sim_touched": False,
            "real_trade_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "passed": severity_counts["P0"] == 0,
    }


def build_consumer_contract(consumer_name: str) -> dict[str, Any]:
    return {
        "consumer_name": consumer_name,
        "source_layer": CONSUMER_SOURCE_LAYER,
        "input_event_types": list(ALLOWED_N4_INPUT_EVENT_TYPES),
        "ordering": list(CONSUMER_ORDERING),
        "partition_key": "identity_key from N4 event envelope",
        "dedup_keys": [
            "consumer_name + event_id",
            "consumer_name + source_layer + event_type + source_run_id + dedup_key + event_schema_version",
        ],
        "watermark": {
            "checkpoint_table": "common_event_consumer_checkpoint",
            "checkpoint_key": "consumer_name + partition_key + source_layer",
            "planned_fields": ["last_event_id", "last_event_time", "last_outbox_id", "checkpoint_payload"],
        },
        "ack_strategy": "write action/quality facts and N5 outbox in one future transaction, then advance checkpoint; N5-1 only plans this",
        "inbox_strategy": "future execute inserts common_event_inbox idempotently before/with action fact; N5-1 only plans this",
    }


def build_consumer_plan(
    *,
    rows: Sequence[Mapping[str, Any]],
    consumer_name: str,
    existing_inbox_keys: Mapping[str, set[str]],
    existing_checkpoints: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    sorted_rows = sorted((normalize_outbox_row(row) for row in rows), key=consumer_sort_key)
    seen_event_ids: set[str] = set()
    seen_consumer_dedup_keys: set[str] = set()
    event_plans: list[dict[str, Any]] = []
    accepted_by_partition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted_rows:
        plan = build_event_consumer_plan(
            row=row,
            consumer_name=consumer_name,
            existing_inbox_keys=existing_inbox_keys,
            existing_checkpoints=existing_checkpoints,
            seen_event_ids=seen_event_ids,
            seen_consumer_dedup_keys=seen_consumer_dedup_keys,
        )
        event_plans.append(plan)
        event_id = str(row.get("event_id") or "")
        consumer_dedup_key = build_consumer_dedup_key(row)
        if plan["consumer_status"] == "planned_receive":
            seen_event_ids.add(event_id)
            seen_consumer_dedup_keys.add(consumer_dedup_key)
            accepted_by_partition[str(row.get("partition_key") or row.get("identity_key") or "")].append(plan)

    last_plan_by_partition = {
        partition_key: plans[-1]
        for partition_key, plans in accepted_by_partition.items()
        if plans
    }
    for partition_key, plan in last_plan_by_partition.items():
        plan["would_advance_watermark"] = True
        plan["would_update_consumer_checkpoint"] = True

    checkpoint_write_plan = [
        build_checkpoint_plan_row(
            consumer_name=consumer_name,
            partition_key=partition_key,
            event_plan=event_plan,
            accepted_event_count=len(accepted_by_partition[partition_key]),
        )
        for partition_key, event_plan in sorted(last_plan_by_partition.items())
    ]
    return {
        "consumer_name": consumer_name,
        "source_layer": CONSUMER_SOURCE_LAYER,
        "ordering": list(CONSUMER_ORDERING),
        "event_plans": event_plans,
        "checkpoint_write_plan": checkpoint_write_plan,
    }


def build_event_consumer_plan(
    *,
    row: Mapping[str, Any],
    consumer_name: str,
    existing_inbox_keys: Mapping[str, set[str]],
    existing_checkpoints: Mapping[str, Mapping[str, Any]],
    seen_event_ids: set[str],
    seen_consumer_dedup_keys: set[str],
) -> dict[str, Any]:
    event_id = str(row.get("event_id") or "")
    event_type = str(row.get("event_type") or "")
    source_layer = str(row.get("source_layer") or "")
    partition_key = str(row.get("partition_key") or row.get("identity_key") or "")
    consumer_dedup_key = build_consumer_dedup_key(row)
    skip_reasons: list[str] = []
    if event_type not in ALLOWED_N4_INPUT_EVENT_TYPES:
        skip_reasons.append("unsupported_event_type")
    if source_layer != CONSUMER_SOURCE_LAYER:
        skip_reasons.append("unsupported_source_layer")
    if not event_id:
        skip_reasons.append("missing_event_id")
    if not partition_key:
        skip_reasons.append("missing_partition_key")
    if event_id in existing_inbox_keys.get("event_ids", set()):
        skip_reasons.append("existing_inbox_event_id")
    if consumer_dedup_key in existing_inbox_keys.get("consumer_dedup_keys", set()):
        skip_reasons.append("existing_inbox_dedup_key")
    if event_id in seen_event_ids:
        skip_reasons.append("duplicate_event_id_in_batch")
    if consumer_dedup_key in seen_consumer_dedup_keys:
        skip_reasons.append("duplicate_dedup_key_in_batch")
    if is_at_or_before_checkpoint(row, existing_checkpoints.get(partition_key)):
        skip_reasons.append("at_or_before_existing_watermark")

    consumer_status = "planned_receive" if not skip_reasons else "skipped"
    return {
        "consumer_name": consumer_name,
        "consumer_status": consumer_status,
        "skip_reasons": skip_reasons,
        "source_outbox_id": row.get("outbox_id"),
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": row.get("event_schema_version"),
        "source_layer": source_layer,
        "source_run_id": row.get("source_run_id"),
        "dedup_key": row.get("dedup_key"),
        "consumer_dedup_key": consumer_dedup_key,
        "partition_key": partition_key,
        "event_time": row.get("event_time"),
        "asset_kind": row.get("asset_kind"),
        "identity_key": row.get("identity_key"),
        "signal_type": (row.get("payload_json") or {}).get("signal_type"),
        "direction": (row.get("payload_json") or {}).get("direction"),
        "would_insert_common_event_inbox": consumer_status == "planned_receive",
        "would_update_common_event_inbox": False,
        "would_update_consumer_checkpoint": False,
        "would_advance_watermark": False,
        "would_write_action_fact": False,
        "would_consume_outbox": False,
        "source_outbox_row": dict(row),
    }


def build_checkpoint_plan_row(
    *,
    consumer_name: str,
    partition_key: str,
    event_plan: Mapping[str, Any],
    accepted_event_count: int,
) -> dict[str, Any]:
    return {
        "consumer_name": consumer_name,
        "partition_key": partition_key,
        "source_layer": CONSUMER_SOURCE_LAYER,
        "last_event_id": event_plan.get("event_id"),
        "last_event_time": event_plan.get("event_time"),
        "last_outbox_id": event_plan.get("source_outbox_id"),
        "accepted_event_count": accepted_event_count,
        "checkpoint_payload": {
            "dry_run": True,
            "stage": "N5-1",
            "watermark_policy": "partition_key + event_time + outbox_id + event_id",
        },
        "would_insert_or_update_common_event_consumer_checkpoint": True,
        "executed": False,
    }


def summarize_consumer_plan(consumer_plan: Mapping[str, Any]) -> dict[str, Any]:
    event_plans = list(consumer_plan["event_plans"])
    accepted = [plan for plan in event_plans if plan.get("consumer_status") == "planned_receive"]
    skipped = [plan for plan in event_plans if plan.get("consumer_status") == "skipped"]
    return {
        "consumer_name": consumer_plan["consumer_name"],
        "read_event_count": len(event_plans),
        "planned_receive_count": len(accepted),
        "skipped_count": len(skipped),
        "by_consumer_status": count_by(event_plans, "consumer_status"),
        "skip_reasons": count_skip_reasons(skipped),
        "by_event_type": count_by(event_plans, "event_type"),
        "accepted_by_event_type": count_by(accepted, "event_type"),
        "accepted_by_signal_type": count_by(accepted, "signal_type"),
        "accepted_by_asset_kind": count_by(accepted, "asset_kind"),
        "accepted_by_direction": count_by(accepted, "direction"),
        "partition_count": len({str(plan.get("partition_key") or "") for plan in event_plans}),
        "accepted_partition_count": len({str(plan.get("partition_key") or "") for plan in accepted}),
        "checkpoint_write_plan_count": len(consumer_plan["checkpoint_write_plan"]),
        "would_insert_inbox_count": sum(1 for plan in event_plans if plan.get("would_insert_common_event_inbox")),
        "would_update_checkpoint_count": sum(1 for plan in event_plans if plan.get("would_update_consumer_checkpoint")),
        "would_consume_outbox_count": sum(1 for plan in event_plans if plan.get("would_consume_outbox")),
        "ordering": list(consumer_plan["ordering"]),
        "watermark_policy": "last accepted event per partition",
        "buy_hint_accepted_count": sum(1 for plan in accepted if plan.get("signal_type") == "BUY_HINT"),
        "sell_hint_accepted_count": sum(1 for plan in accepted if plan.get("signal_type") == "SELL_HINT"),
        "pending_market_data_accepted_count": sum(1 for plan in accepted if plan.get("event_type") == "TriggerPendingMarketData"),
    }


def build_quality_items(
    *,
    trigger_run_id: str,
    consumer_name: str,
    trigger_run: Mapping[str, Any],
    outbox_summary: Mapping[str, Any],
    consumer_plan: Mapping[str, Any],
    candidate_summary: Mapping[str, Any],
    before_row_counts: Mapping[str, Mapping[str, Any]],
    after_row_counts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    consumer_summary = summarize_consumer_plan(consumer_plan)
    row_counts_unchanged = before_row_counts == after_row_counts
    inbox_checkpoint_unchanged = all(
        before_row_counts.get(table_name) == after_row_counts.get(table_name)
        for table_name in ("common_event_inbox", "common_event_consumer_checkpoint")
    )
    return [
        quality_item(
            "P0",
            "passed" if consumer_name else "failed",
            "n5_1_consumer_name_present",
            "N5-1 must declare a stable consumer_name",
            expected="non-empty",
            actual=consumer_name,
        ),
        quality_item(
            "P0",
            "passed" if trigger_run.get("run_id") == trigger_run_id else "failed",
            "n5_1_source_trigger_run_found",
            "N5-1 must read the requested N4 trigger run as upstream metadata",
            expected=trigger_run_id,
            actual=str(trigger_run.get("run_id") or ""),
        ),
        quality_item(
            "P0",
            "passed" if int(outbox_summary.get("outbox_row_count") or 0) > 0 else "failed",
            "n5_1_n4_outbox_available",
            "N5-1 must read N4 standard outbox rows",
            expected=">0",
            actual=str(outbox_summary.get("outbox_row_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if not outbox_summary.get("disallowed_event_types") else "failed",
            "n5_1_only_standard_n4_events",
            "N5-1 input must be TriggerMatched, TriggerPendingMarketData, or TriggerStateChanged",
            expected=",".join(ALLOWED_N4_INPUT_EVENT_TYPES),
            actual=",".join(outbox_summary.get("by_event_type", {}).keys()),
        ),
        quality_item(
            "P0",
            "passed"
            if int(consumer_summary.get("planned_receive_count") or 0)
            + int(consumer_summary.get("skipped_count") or 0)
            == int(consumer_summary.get("read_event_count") or 0)
            else "failed",
            "n5_1_consumer_plan_accounts_for_all_events",
            "N5-1 consumer plan must account for every read event",
            expected=str(consumer_summary.get("read_event_count") or 0),
            actual=str(int(consumer_summary.get("planned_receive_count") or 0) + int(consumer_summary.get("skipped_count") or 0)),
        ),
        quality_item(
            "P0",
            "passed"
            if int(consumer_summary.get("planned_receive_count") or 0)
            == int(candidate_summary.get("candidate_count") or 0)
            else "failed",
            "n5_1_accepted_events_map_to_candidates",
            "Every accepted N4 event must map to an N5 dry-run candidate or quality plan",
            expected=str(consumer_summary.get("planned_receive_count") or 0),
            actual=str(candidate_summary.get("candidate_count") or 0),
        ),
        quality_item(
            "P0",
            "passed"
            if int(consumer_summary.get("buy_hint_accepted_count") or 0) > 0
            and int(consumer_summary.get("sell_hint_accepted_count") or 0) > 0
            else "failed",
            "n5_1_buy_sell_hint_preserved",
            "BUY_HINT and SELL_HINT must survive consumer dry-run",
            expected="BUY_HINT>0 SELL_HINT>0",
            actual=(
                f"BUY_HINT={consumer_summary.get('buy_hint_accepted_count') or 0} "
                f"SELL_HINT={consumer_summary.get('sell_hint_accepted_count') or 0}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if int(candidate_summary.get("pending_generates_action_event_count") or 0) == 0 else "failed",
            "n5_1_pending_market_data_quality_plan_only",
            "TriggerPendingMarketData must only create quality plans in N5-1",
            expected="0 action events",
            actual=str(candidate_summary.get("pending_generates_action_event_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(candidate_summary.get("unclosed_minute_generates_action_event_count") or 0) == 0 else "failed",
            "n5_1_no_unclosed_minute_action_confirmation",
            "N5-1 must not confirm actions with unclosed minute context",
            expected="0",
            actual=str(candidate_summary.get("unclosed_minute_generates_action_event_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(consumer_summary.get("would_consume_outbox_count") or 0) == 0 else "failed",
            "n5_1_does_not_consume_outbox",
            "N5-1 must not update or consume N4 outbox rows",
            expected="0",
            actual=str(consumer_summary.get("would_consume_outbox_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n5_1_database_row_counts_unchanged",
            "N5-1 dry-run must keep guarded table row counts unchanged",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if inbox_checkpoint_unchanged else "failed",
            "n5_1_no_inbox_checkpoint_update",
            "N5-1 dry-run must not update common_event_inbox or consumer checkpoint",
            expected="unchanged",
            actual="unchanged" if inbox_checkpoint_unchanged else "changed",
        ),
        quality_item("P0", "passed", "n5_1_no_action_fact_write", "N5-1 does not write action facts"),
        quality_item("P0", "passed", "n5_1_no_market_data_pull", "N5-1 does not pull market data"),
        quality_item("P0", "passed", "n5_1_no_user_voice_sim_write", "N5-1 does not write user, voice, or sim outputs"),
        quality_item("P0", "passed", "n5_1_no_real_trade", "N5-1 does not call trading interfaces"),
        quality_item("P0", "passed", "n5_1_no_worker", "N5-1 does not start workers"),
        quality_item(
            "P2",
            "warning" if int(outbox_summary.get("synthetic_sample_event_count") or 0) > 0 else "passed",
            "n5_1_source_outbox_is_synthetic_sample",
            "Current N4 outbox is synthetic/sample run-once material for N5 development only",
            expected="development sample noted",
            actual=str(outbox_summary.get("synthetic_sample_event_count") or 0),
        ),
    ]


def fetch_existing_inbox_keys(cur: psycopg.Cursor[dict[str, Any]], consumer_name: str) -> dict[str, set[str]]:
    if not table_exists(cur, "common_event_inbox"):
        return empty_inbox_keys()
    cur.execute(
        """
        SELECT event_id, source_layer, event_type, source_run_id, dedup_key, event_schema_version
        FROM common_event_inbox
        WHERE consumer_name = %s
        """,
        (consumer_name,),
    )
    event_ids: set[str] = set()
    consumer_dedup_keys: set[str] = set()
    for row in cur.fetchall():
        normalized = normalize_mapping(row)
        event_ids.add(str(normalized.get("event_id") or ""))
        consumer_dedup_keys.add(build_consumer_dedup_key(normalized))
    return {"event_ids": event_ids, "consumer_dedup_keys": consumer_dedup_keys}


def fetch_existing_checkpoints(
    cur: psycopg.Cursor[dict[str, Any]],
    consumer_name: str,
) -> dict[str, dict[str, Any]]:
    if not table_exists(cur, "common_event_consumer_checkpoint"):
        return {}
    cur.execute(
        """
        SELECT consumer_name, partition_key, source_layer, last_event_id,
               last_event_time, last_outbox_id, checkpoint_payload, updated_at
        FROM common_event_consumer_checkpoint
        WHERE consumer_name = %s
          AND source_layer = %s
        """,
        (consumer_name, CONSUMER_SOURCE_LAYER),
    )
    return {
        str(row["partition_key"]): normalize_mapping(row)
        for row in cur.fetchall()
    }


def empty_inbox_keys() -> dict[str, set[str]]:
    return {"event_ids": set(), "consumer_dedup_keys": set()}


def build_consumer_dedup_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("source_layer") or ""),
            str(row.get("event_type") or ""),
            str(row.get("source_run_id") or ""),
            str(row.get("dedup_key") or ""),
            str(row.get("event_schema_version") or ""),
        ]
    )


def consumer_sort_key(row: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(row.get("partition_key") or row.get("identity_key") or ""),
        normalize_event_time_for_sort(row.get("event_time")),
        int(row.get("outbox_id") or 0),
        str(row.get("event_id") or ""),
    )


def normalize_event_time_for_sort(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def is_at_or_before_checkpoint(row: Mapping[str, Any], checkpoint: Mapping[str, Any] | None) -> bool:
    if not checkpoint:
        return False
    last_outbox_id = checkpoint.get("last_outbox_id")
    row_outbox_id = row.get("outbox_id")
    if last_outbox_id is not None and row_outbox_id is not None:
        try:
            return int(row_outbox_id) <= int(last_outbox_id)
        except (TypeError, ValueError):
            return False
    last_event_time = checkpoint.get("last_event_time")
    if last_event_time is None:
        return False
    return normalize_event_time_for_sort(row.get("event_time")) <= normalize_event_time_for_sort(last_event_time)


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def count_skip_reasons(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for reason in row.get("skip_reasons") or []:
            counter[str(reason)] += 1
    return dict(sorted(counter.items()))


def compact_event_plans(event_plans: Sequence[Mapping[str, Any]], sample_limit: int) -> list[dict[str, Any]]:
    keys = (
        "consumer_name",
        "consumer_status",
        "skip_reasons",
        "source_outbox_id",
        "event_id",
        "event_type",
        "partition_key",
        "event_time",
        "asset_kind",
        "identity_key",
        "signal_type",
        "direction",
        "would_insert_common_event_inbox",
        "would_update_consumer_checkpoint",
        "would_advance_watermark",
        "would_consume_outbox",
    )
    return [
        {key: plan.get(key) for key in keys}
        for plan in event_plans[:sample_limit]
    ]


def infer_trade_date(rows: Sequence[Mapping[str, Any]]) -> str | None:
    for row in rows:
        trade_date = row.get("trade_date")
        if trade_date:
            return str(trade_date)
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def format_action_consumer_dry_run_report(report: Mapping[str, Any]) -> str:
    outbox = report["outbox_summary"]
    consumer = report["consumer_plan_summary"]
    candidates = report["action_candidate_summary"]
    quality = report["quality"]
    side_effects = report["side_effects"]
    return "\n".join(
        [
            "# N5-1 Action Consumer Dry-Run Report",
            "",
            "## Summary",
            "",
            f"- stage: {report['stage']}",
            f"- layer_role: {report['layer_role']}",
            f"- consumer_name: {report['consumer_name']}",
            f"- source_trigger_run_id: {report['source_trigger_run_id']}",
            f"- action_run_id: {report['action_run_id']}",
            f"- for_trade_date: {report.get('for_trade_date')}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            "",
            "## Consumer Plan",
            "",
            f"- read_event_count: {consumer['read_event_count']}",
            f"- planned_receive_count: {consumer['planned_receive_count']}",
            f"- skipped_count: {consumer['skipped_count']}",
            f"- skip_reasons: {consumer['skip_reasons']}",
            f"- ordering: {consumer['ordering']}",
            f"- partition_count: {consumer['partition_count']}",
            f"- accepted_partition_count: {consumer['accepted_partition_count']}",
            f"- checkpoint_write_plan_count: {consumer['checkpoint_write_plan_count']}",
            f"- would_insert_inbox_count: {consumer['would_insert_inbox_count']}",
            f"- would_update_checkpoint_count: {consumer['would_update_checkpoint_count']}",
            f"- would_consume_outbox_count: {consumer['would_consume_outbox_count']}",
            "",
            "## N4 Event Distribution",
            "",
            f"- by_event_type: {outbox['by_event_type']}",
            f"- by_signal_type: {outbox['by_signal_type']}",
            f"- by_asset_kind: {outbox['by_asset_kind']}",
            f"- by_direction: {outbox['by_direction']}",
            f"- BUY_HINT matched/pending/total: {outbox['buy_hint_matched_count']}/{outbox['buy_hint_pending_count']}/{outbox['buy_hint_count']}",
            f"- SELL_HINT matched/pending/total: {outbox['sell_hint_matched_count']}/{outbox['sell_hint_pending_count']}/{outbox['sell_hint_count']}",
            "",
            "## Action Candidate Dry-Run",
            "",
            f"- candidate_count: {candidates['candidate_count']}",
            f"- action_candidate_count: {candidates['action_candidate_count']}",
            f"- quality_plan_count: {candidates['quality_plan_count']}",
            f"- planned_output_event_type: {candidates['by_planned_output_event_type']}",
            f"- pending_generates_action_event_count: {candidates['pending_generates_action_event_count']}",
            f"- BUY_HINT candidate count: {candidates['buy_hint_candidate_count']}",
            f"- SELL_HINT candidate count: {candidates['sell_hint_candidate_count']}",
            "",
            "## Boundary Confirmation",
            "",
            f"- writes_performed: {side_effects['writes_performed']}",
            f"- common_event_inbox_updated: {side_effects['common_event_inbox_updated']}",
            f"- consumer_checkpoint_updated: {side_effects['consumer_checkpoint_updated']}",
            f"- n4_outbox_status_updated: {side_effects['n4_outbox_status_updated']}",
            f"- action_fact_written: {side_effects['action_fact_written']}",
            f"- action_event_written: {side_effects['action_event_written']}",
            f"- market_data_pulled: {side_effects['market_data_pulled']}",
            f"- user_layer_touched: {side_effects['user_layer_touched']}",
            f"- voice_touched: {side_effects['voice_touched']}",
            f"- sim_touched: {side_effects['sim_touched']}",
            f"- real_trade_touched: {side_effects['real_trade_touched']}",
            f"- worker_started: {side_effects['worker_started']}",
            f"- old_system_touched: {side_effects['old_system_touched']}",
            "",
            "## Notes",
            "",
            "- This report plans N5 consumer behavior only; it does not execute inbox/checkpoint writes.",
            "- The current N4 outbox is synthetic/sample run-once material for N5 development validation.",
        ]
    )
