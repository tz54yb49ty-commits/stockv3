"""N4-3 trigger context snapshot executor.

This module localizes the active N2 condition context into N4 trigger context
snapshot tables. It does not consume N3 events, write trigger_state/match rows,
write common_event_outbox rows, pull market data, start workers, or enter N5/N6.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item
from ashare_v3.trigger.context_preflight import (
    ASSET_KINDS,
    ATOMIC_RULE_SPEC_PATH,
    ATOMIC_RULE_VERSION,
    CONTEXT_CONTRACT_VERSION,
    TARGET_CONTEXT_TABLES,
    build_atomic_context_run_id,
    build_trigger_context_preflight_dry_run,
    period_trigger_baseline_json_missing_count,
    required_period_not_ready_rows_count,
    normalize_text_array,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_context_refresh_connect
from ashare_v3.trigger.schema_review import REQUIRED_TRIGGER_TABLES, build_trigger_schema_migration_review


DEFAULT_N4_3_JSON_REPORT_PATH = "docs/N4_3_trigger_context_snapshot_execute_report.json"
DEFAULT_N4_3_MD_REPORT_PATH = "docs/N4_3_TRIGGER_CONTEXT_SNAPSHOT_EXECUTE_REPORT.md"
DEFAULT_N4_3_ROLLBACK_SQL_PATH = "sql/N4_3_trigger_context_snapshot_rollback.sql"

EXPECTED_CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260524014029_execute"

N4_CONTEXT_TABLES = tuple(TARGET_CONTEXT_TABLES[asset_kind] for asset_kind in ASSET_KINDS)
N4_WRITABLE_CONTEXT_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    *N4_CONTEXT_TABLES,
)
N4_FORBIDDEN_WRITE_TABLES = (
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
)
N3_GUARD_TABLES = (
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
    "common_event_outbox",
)

N4_CONTEXT_SIGNAL_ORDER = (
    "B_BUY",
    "S_SELL",
    "BUY_HINT",
    "SELL_HINT",
)
DEPRECATED_CONTEXT_SIGNAL_LABELS = {"B_BUY_30M_VOL", "S_SELL_30M_SHRINK"}
N2_TO_N4_CONTEXT_ALLOWED_SIGNAL_TYPES = {
    "BUY": ("B_BUY",),
    "BUY:FULL": ("B_BUY",),
    "SELL": ("S_SELL",),
    "SELL:FULL": ("S_SELL",),
    "B_BUY": ("B_BUY",),
    "B_BUY_30M_VOL": ("B_BUY",),
    "S_SELL": ("S_SELL",),
    "S_SELL_30M_SHRINK": ("S_SELL",),
    "BUY_HINT": ("BUY_HINT",),
    "SELL_HINT": ("SELL_HINT",),
}

CONTEXT_INSERT_COLUMNS = (
    "run_id",
    "source_condition_run_id",
    "source_condition_pool_id",
    "source_condition_basis_id",
    "source_minute_target_scope_id",
    "source_market_subscription_id",
    "for_trade_date",
    "source_trade_date",
    "prev_trade_date",
    "asset_kind",
    "identity_key",
    "exchange",
    "code",
    "display_code",
    "name",
    "lane",
    "monitor_type",
    "direction",
    "condition_key",
    "condition_periods",
    "allowed_signal_types",
    "is_hint_scope",
    "prev_up_str",
    "prev_dn_str",
    "period_transition_y",
    "period_transition_q",
    "period_transition_m",
    "period_transition_w",
    "period_transition_d",
    "amount_y",
    "amount_q",
    "amount_m",
    "amount_w",
    "amount_d",
    "previous_amount_y",
    "previous_amount_q",
    "previous_amount_m",
    "previous_amount_w",
    "previous_amount_d",
    "main_up_anchor",
    "up_reference_period",
    "up_amplitude",
    "buy_target_price",
    "main_down_anchor",
    "down_reference_period",
    "down_amplitude",
    "sell_target_price",
    "clear_sell_ref_period",
    "previous_day_minute_date",
    "daily_snapshot_required",
    "minute_required",
    "previous_day_minute_required",
    "previous_day_minute_quality_required",
    "policy_hash",
    "context_hash",
    "quality_status",
    "raw_json",
)


def run_trigger_context_snapshot_execute(
    *,
    dsn: str,
    condition_run_id: str = EXPECTED_CONDITION_RUN_ID,
    market_data_run_id: str | None = None,
    market_subscription_run_id: str | None = None,
    for_trade_date: str | None = "20260525",
    json_report_path: str = DEFAULT_N4_3_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N4_3_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_N4_3_ROLLBACK_SQL_PATH,
    allow_existing_context_for_trade_date: bool = False,
    expected_condition_run_id: str | None = None,
    stage: str = "N4-3",
    execution_mode: str = "trigger_context_snapshot_execute",
) -> dict[str, Any]:
    started_at = utc_now_iso()
    expected_condition_run_id = expected_condition_run_id or condition_run_id
    schema_review = build_trigger_schema_migration_review(dsn=dsn)
    if int(schema_review["quality"]["p0_count"]) > 0 or schema_review["target_tables_missing"]:
        raise RuntimeError(f"{stage} blocked: N4 schema is not ready")

    market_data_run_summary = {}
    if market_data_run_id:
        market_data_run_summary = fetch_market_data_run_summary(dsn, market_data_run_id)
    subscription_trace_run_id = market_subscription_run_id or market_data_run_id
    market_subscription_run_summary = {}
    if market_subscription_run_id and market_subscription_run_id != market_data_run_id:
        market_subscription_run_summary = fetch_market_data_run_summary(dsn, market_subscription_run_id)

    preflight = build_trigger_context_preflight_dry_run(
        dsn=dsn,
        run_id=condition_run_id,
        for_trade_date=for_trade_date,
        include_rows=True,
    )
    if int(preflight["quality"]["p0_count"]) > 0 or not bool(preflight["passed"]):
        raise RuntimeError(f"{stage} blocked: context preflight has P0 findings")
    if str(preflight.get("source_condition_run_id") or "") != condition_run_id:
        raise RuntimeError(f"{stage} blocked: active condition run does not match requested run_id")

    context_rows = list(preflight["trigger_context_snapshot_dry_run_plan"]["rows"])
    market_trace_summary = {}
    if subscription_trace_run_id:
        context_rows, market_trace_summary = attach_market_subscription_trace(
            dsn=dsn,
            market_data_run_id=subscription_trace_run_id,
            context_rows=context_rows,
        )
    run_id = build_trigger_context_run_id(preflight)
    rollback_sql = build_trigger_context_rollback_sql(run_id)
    write_text(rollback_sql_path, rollback_sql)

    before_snapshot = capture_execution_snapshot(dsn, phase="before_n4_3", condition_run_id=condition_run_id)
    existing_target_summary = fetch_context_summary(dsn, run_id)
    existing_trigger_run = dict(existing_target_summary.get("trigger_run") or {})
    if (
        existing_trigger_run.get("status") == "passed"
        and int(existing_trigger_run.get("context_snapshot_row_count") or 0) > 0
        and int(existing_target_summary.get("row_count") or 0) == int(existing_trigger_run.get("context_snapshot_row_count") or 0)
    ):
        report = {
            "result": "IDEMPOTENT_PASS",
            "stage": stage,
            "layer_role": "N4_trigger",
            "execution_mode": execution_mode,
            "run_id": run_id,
            "source_condition_run_id": condition_run_id,
            "source_market_data_run_id": market_data_run_id,
            "market_subscription_run_id": market_subscription_run_id,
            "for_trade_date": preflight["for_trade_date"],
            "source_trade_date": preflight["source_trade_date"],
            "prev_trade_date": preflight["prev_trade_date"],
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "json_report_path": json_report_path,
            "markdown_report_path": markdown_report_path,
            "rollback_sql_path": rollback_sql_path,
            "preflight_report": summarize_preflight(preflight),
            "market_data_run_summary": market_data_run_summary,
            "market_subscription_run_summary": market_subscription_run_summary,
            "market_subscription_trace_summary": market_trace_summary,
            "existing_n4_lineage_report": fetch_existing_n4_lineage_report(dsn, current_condition_run_id=condition_run_id),
            "allow_existing_context_for_trade_date": allow_existing_context_for_trade_date,
            "common_event_outbox_baseline_count": before_snapshot["row_counts"]["common_event_outbox"]["row_count"],
            "schema_review_summary": summarize_schema_review(schema_review),
            "before_row_counts": before_snapshot["row_counts"],
            "after_row_counts": before_snapshot["row_counts"],
            "inserted_counts": {
                "common_trigger_run": 0,
                "common_trigger_quality_item": 0,
                "stock_trigger_context_snapshot": 0,
                "index_trigger_context_snapshot": 0,
                "board_trigger_context_snapshot": 0,
                "common_trigger_state": 0,
                "common_trigger_match": 0,
                "common_event_outbox": 0,
                "context_snapshot_total": 0,
            },
            "post_context_summary": existing_target_summary,
            "post_checks": {
                "idempotent_existing_context_run_passed": True,
                "trigger_state_not_written": True,
                "trigger_match_not_written": True,
                "event_outbox_not_written": True,
            },
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
            "rollback_sql": rollback_sql,
            "side_effects": {
                "will_execute_sql": False,
                "migration_executed": False,
                "writes_performed": False,
                "trigger_context_snapshot_written": False,
                "trigger_run_written": False,
                "trigger_quality_item_written": False,
                "trigger_state_written": False,
                "trigger_match_written": False,
                "event_outbox_written": False,
                "market_data_pulled": False,
                "n3_event_consumed": False,
                "downstream_layers_touched": False,
                "worker_started": False,
                "old_system_touched": False,
                "external_n2_runtime_path_accessed": False,
            },
        }
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_trigger_context_execute_report(report))
        return report

    existing_n4_lineage_report = fetch_existing_n4_lineage_report(dsn, current_condition_run_id=condition_run_id)
    existing_active = fetch_existing_active_context_runs(dsn, for_trade_date=str(preflight["for_trade_date"]))
    if existing_active and not allow_existing_context_for_trade_date:
        raise RuntimeError(f"{stage} blocked: active trigger context already exists for trade date: {existing_active}")

    quality_items = build_execute_quality_items(
        preflight=preflight,
        context_rows=context_rows,
        expected_condition_run_id=expected_condition_run_id,
        market_data_run_id=market_data_run_id,
        market_data_run_summary=market_data_run_summary,
        market_subscription_run_id=market_subscription_run_id,
        market_subscription_run_summary=market_subscription_run_summary,
        market_trace_summary=market_trace_summary,
    )
    severity_counts = count_quality_severities(quality_items)
    if severity_counts["P0"] > 0:
        raise RuntimeError(f"{stage} blocked: execute prechecks have P0 findings")

    inserted_counts = execute_context_transaction(
        dsn=dsn,
        run_id=run_id,
        preflight=preflight,
        context_rows=context_rows,
        quality_items=quality_items,
        severity_counts=severity_counts,
        market_data_run_id=market_data_run_id,
        market_subscription_run_id=market_subscription_run_id,
        allow_existing_context_for_trade_date=allow_existing_context_for_trade_date,
    )
    after_write_snapshot = capture_execution_snapshot(dsn, phase="after_n4_3_context_write", condition_run_id=condition_run_id)
    post_context_summary = fetch_context_summary(dsn, run_id)
    initial_post_checks = build_post_execute_checks(
        preflight=preflight,
        before_snapshot=before_snapshot,
        after_snapshot=after_write_snapshot,
        inserted_counts=inserted_counts,
        post_context_summary=post_context_summary,
        run_id=run_id,
        condition_run_id=condition_run_id,
        market_data_run_id=market_data_run_id,
        check_quality_item_delta=False,
    )
    post_quality_items = build_post_quality_items(initial_post_checks)
    appended_quality_count = append_quality_items(
        dsn=dsn,
        run_id=run_id,
        preflight=preflight,
        items=post_quality_items,
    )
    inserted_counts["common_trigger_quality_item"] += appended_quality_count
    after_snapshot = capture_execution_snapshot(dsn, phase="after_n4_3", condition_run_id=condition_run_id)
    post_context_summary = fetch_context_summary(dsn, run_id)
    post_checks = build_post_execute_checks(
        preflight=preflight,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        inserted_counts=inserted_counts,
        post_context_summary=post_context_summary,
        run_id=run_id,
        condition_run_id=condition_run_id,
        market_data_run_id=market_data_run_id,
        check_quality_item_delta=True,
    )
    post_quality_items = build_post_quality_items(post_checks)
    all_quality_items = [*quality_items, *post_quality_items]
    final_severity_counts = count_quality_severities(all_quality_items)
    refresh_run_quality_counts(dsn, run_id, final_severity_counts, len(all_quality_items))

    report = {
        "stage": stage,
        "layer_role": "N4_trigger",
        "execution_mode": execution_mode,
        "run_id": run_id,
        "source_condition_run_id": condition_run_id,
        "source_market_data_run_id": market_data_run_id,
        "market_subscription_run_id": market_subscription_run_id,
        "for_trade_date": preflight["for_trade_date"],
        "source_trade_date": preflight["source_trade_date"],
        "prev_trade_date": preflight["prev_trade_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "rollback_sql_path": rollback_sql_path,
        "preflight_report": summarize_preflight(preflight),
        "market_data_run_summary": market_data_run_summary,
        "market_subscription_run_summary": market_subscription_run_summary,
        "market_subscription_trace_summary": market_trace_summary,
        "existing_n4_lineage_report": existing_n4_lineage_report,
        "allow_existing_context_for_trade_date": allow_existing_context_for_trade_date,
        "common_event_outbox_baseline_count": before_snapshot["row_counts"]["common_event_outbox"]["row_count"],
        "schema_review_summary": summarize_schema_review(schema_review),
        "before_row_counts": before_snapshot["row_counts"],
        "after_row_counts": after_snapshot["row_counts"],
        "inserted_counts": inserted_counts,
        "post_context_summary": post_context_summary,
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
            "migration_executed": False,
            "writes_performed": True,
            "trigger_context_snapshot_written": True,
            "trigger_run_written": True,
            "trigger_quality_item_written": True,
            "trigger_state_written": False,
            "trigger_match_written": False,
            "event_outbox_written": False,
            "market_data_pulled": False,
            "n3_event_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
            "external_n2_runtime_path_accessed": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_trigger_context_execute_report(report))
    return report


def build_trigger_context_run_id(preflight: Mapping[str, Any]) -> str:
    return build_atomic_context_run_id(
        for_trade_date=str(preflight["for_trade_date"]),
        condition_run_id=str(preflight["source_condition_run_id"]),
    )


def canonical_context_allowed_signal_types(
    allowed_signal_types: Any,
    *,
    direction: str,
    condition_key: str,
) -> list[str]:
    """Map N2 canonical condition semantics into N4 context candidate labels."""

    expanded: list[str] = []
    for signal_type in normalize_text_array(allowed_signal_types):
        expanded.extend(N2_TO_N4_CONTEXT_ALLOWED_SIGNAL_TYPES.get(signal_type, ()))
    if not expanded:
        key = str(condition_key or "")
        if key.startswith("BUY:"):
            expanded.append("B_BUY")
        elif key.startswith("SELL:"):
            expanded.append("S_SELL")
        elif key == "BUY_HINT":
            expanded.append("BUY_HINT")
        elif key == "SELL_HINT":
            expanded.append("SELL_HINT")

    direction_key = str(direction or "").lower()
    if direction_key == "buy":
        expanded = [value for value in expanded if value in {"B_BUY", "BUY_HINT"}]
    elif direction_key == "sell":
        expanded = [value for value in expanded if value in {"S_SELL", "SELL_HINT"}]

    expanded_set = set(expanded)
    return [value for value in N4_CONTEXT_SIGNAL_ORDER if value in expanded_set]


def execute_context_transaction(
    *,
    dsn: str,
    run_id: str,
    preflight: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
    severity_counts: Mapping[str, int],
    market_data_run_id: str | None = None,
    market_subscription_run_id: str | None = None,
    allow_existing_context_for_trade_date: bool = False,
) -> dict[str, int]:
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id="n4_context_execute_transaction",
        source_run_id=run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            assert_no_existing_context(
                cur,
                for_trade_date=str(preflight["for_trade_date"]),
                run_id=run_id,
                allow_existing_context_for_trade_date=allow_existing_context_for_trade_date,
            )
            insert_trigger_run(
                cur,
                run_id=run_id,
                preflight=preflight,
                severity_counts=severity_counts,
                context_row_count=len(context_rows),
                market_data_run_id=market_data_run_id,
                market_subscription_run_id=market_subscription_run_id,
            )
            inserted_context_counts = insert_context_rows(cur, run_id=run_id, rows=context_rows)
            inserted_quality_count = insert_quality_items(cur, run_id=run_id, preflight=preflight, items=quality_items)
            cur.execute(
                """
                UPDATE common_trigger_run
                SET status = 'passed',
                    context_snapshot_row_count = %s,
                    p0_count = %s,
                    p1_count = %s,
                    p2_count = %s,
                    finished_at = now(),
                    updated_at = now()
                WHERE run_id = %s
                """,
                (
                    len(context_rows),
                    int(severity_counts["P0"]),
                    int(severity_counts["P1"]),
                    int(severity_counts["P2"]),
                    run_id,
                ),
            )
        conn.commit()
    return {
        "common_trigger_run": 1,
        "common_trigger_quality_item": inserted_quality_count,
        **inserted_context_counts,
        "common_trigger_state": 0,
        "common_trigger_match": 0,
        "common_event_outbox": 0,
        "context_snapshot_total": sum(inserted_context_counts.values()),
    }


def assert_no_existing_context(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    for_trade_date: str,
    run_id: str,
    allow_existing_context_for_trade_date: bool = False,
) -> None:
    cur.execute("SELECT 1 FROM common_trigger_run WHERE run_id = %s LIMIT 1", (run_id,))
    if cur.fetchone() is not None:
        raise RuntimeError(f"trigger context run already exists: {run_id}")
    target_context_counts: dict[str, int] = {}
    for table_name in N4_CONTEXT_TABLES:
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE run_id = %s", (run_id,))
        target_context_counts[table_name] = int(cur.fetchone()["row_count"])
    target_nonzero = {table: count for table, count in target_context_counts.items() if count > 0}
    if target_nonzero:
        raise RuntimeError(f"context snapshot rows already exist for run_id {run_id}: {target_nonzero}")
    if allow_existing_context_for_trade_date:
        return

    cur.execute(
        """
        SELECT run_id, status, mode, context_snapshot_row_count
        FROM common_trigger_run
        WHERE for_trade_date = %s
          AND mode = 'execute'
          AND status IN ('planned', 'running', 'passed')
          AND context_snapshot_row_count > 0
        ORDER BY created_at DESC
        """,
        (for_trade_date,),
    )
    rows = [dict(row) for row in cur.fetchall()]
    if rows:
        raise RuntimeError(f"active trigger context already exists for {for_trade_date}: {rows}")

    context_counts: dict[str, int] = {}
    for table_name in N4_CONTEXT_TABLES:
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE for_trade_date = %s", (for_trade_date,))
        context_counts[table_name] = int(cur.fetchone()["row_count"])
    nonzero = {table: count for table, count in context_counts.items() if count > 0}
    if nonzero:
        raise RuntimeError(f"context snapshot rows already exist for {for_trade_date}: {nonzero}")


def insert_trigger_run(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    run_id: str,
    preflight: Mapping[str, Any],
    severity_counts: Mapping[str, int],
    context_row_count: int,
    market_data_run_id: str | None = None,
    market_subscription_run_id: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO common_trigger_run (
          run_id, source_condition_run_id, source_market_data_run_id, for_trade_date, source_trade_date,
          prev_trade_date, mode, status, p0_count, p1_count, p2_count,
          source_condition_row_count, context_snapshot_row_count,
          trigger_state_row_count, trigger_match_row_count, trigger_event_outbox_count,
          generated_by, raw_json, started_at, updated_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(source_market_data_run_id)s, %(for_trade_date)s, %(source_trade_date)s,
          %(prev_trade_date)s, 'execute', 'running', %(p0_count)s, %(p1_count)s, %(p2_count)s,
          %(source_condition_row_count)s, %(context_snapshot_row_count)s,
          0, 0, 0, 'n4_context_snapshot_execute', %(raw_json)s, now(), now()
        )
        """,
        {
            "run_id": run_id,
            "source_condition_run_id": preflight["source_condition_run_id"],
            "source_market_data_run_id": market_data_run_id,
            "for_trade_date": preflight["for_trade_date"],
            "source_trade_date": preflight["source_trade_date"],
            "prev_trade_date": preflight["prev_trade_date"],
            "p0_count": int(severity_counts["P0"]),
            "p1_count": int(severity_counts["P1"]),
            "p2_count": int(severity_counts["P2"]),
            "source_condition_row_count": int(preflight["candidate_context_row_count"]),
            "context_snapshot_row_count": context_row_count,
            "raw_json": Jsonb(
                {
                    "stage": "N4-3",
                    "rule_spec_path": ATOMIC_RULE_SPEC_PATH,
                    "rule_spec_version": ATOMIC_RULE_VERSION,
                    "context_contract_version": CONTEXT_CONTRACT_VERSION,
                    "preflight_summary": summarize_preflight(preflight),
                    "source_market_data_run_id": market_data_run_id,
                    "market_subscription_run_id": market_subscription_run_id,
                    "writes_outbox": False,
                    "downstream_layers_touched": False,
                    "worker_started": False,
                    "boundary": {
                        "n3_event_consumed": False,
                        "writes_outbox": False,
                        "event_outbox_written": False,
                        "trigger_state_written": False,
                        "trigger_match_written": False,
                        "downstream_layers_touched": False,
                        "worker_started": False,
                    },
                }
            ),
        },
    )


def insert_context_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    run_id: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        asset_rows = [row for row in rows if row.get("asset_kind") == asset_kind]
        if not asset_rows:
            counts[TARGET_CONTEXT_TABLES[asset_kind]] = 0
            continue
        table_name = TARGET_CONTEXT_TABLES[asset_kind]
        identity_column = f"{asset_kind}_identity_key"
        columns = list(CONTEXT_INSERT_COLUMNS)
        columns.insert(columns.index("exchange"), identity_column)
        sql = f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
        """
        values = [context_insert_values(run_id, row, columns, identity_column) for row in asset_rows]
        cur.executemany(sql, values)
        counts[table_name] = len(values)
    return counts


def context_insert_values(
    run_id: str,
    row: Mapping[str, Any],
    columns: Sequence[str],
    identity_column: str,
) -> tuple[Any, ...]:
    values: list[Any] = []
    for column in columns:
        if column == "run_id":
            values.append(run_id)
        elif column == identity_column:
            values.append(row.get("identity_key"))
        elif column == "condition_periods":
            values.append(normalize_text_array(row.get("condition_periods")))
        elif column == "allowed_signal_types":
            values.append(
                canonical_context_allowed_signal_types(
                    row.get("allowed_signal_types"),
                    direction=str(row.get("direction") or ""),
                    condition_key=str(row.get("condition_key") or ""),
                )
            )
        elif column == "quality_status":
            values.append("passed")
        elif column == "raw_json":
            values.append(Jsonb(build_context_raw_json(row)))
        else:
            values.append(row.get(column))
    return tuple(values)


def build_context_raw_json(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "source_scope_table",
        "source_pool_table",
        "source_basis_table",
        "scope_source",
        "scope_status",
        "active_target",
        "pool_quality_status",
        "basis_quality_status",
        "amount_quality_status",
        "period_trigger_baseline_json",
        "context_enrichment_materialization_run_id",
        "context_enrichment_version",
        "context_enrichment_hash",
        "trigger_amount_chain_baseline_json",
        "trigger_amount_chain_formula_hash",
        "full_prerequisite_trace_json",
        "full_prerequisite_quality_status",
        "hint_prerequisite_trace_json",
        "hint_prerequisite_quality_status",
        "period_baseline_ready_json",
        "minute_scope_reason",
        "policy_name",
        "selected_reason",
    )
    raw = {key: normalize_json_value(row.get(key)) for key in keys}
    source_allowed_signal_types = normalize_text_array(row.get("allowed_signal_types"))
    raw["source_allowed_signal_types"] = normalize_json_value(source_allowed_signal_types)
    raw["n4_context_allowed_signal_types"] = normalize_json_value(
        canonical_context_allowed_signal_types(
            source_allowed_signal_types,
            direction=str(row.get("direction") or ""),
            condition_key=str(row.get("condition_key") or ""),
        )
    )
    legacy_labels = [value for value in source_allowed_signal_types if value in DEPRECATED_CONTEXT_SIGNAL_LABELS]
    if legacy_labels:
        raw["legacy_compat_trace"] = {
            "deprecated_context_signal_labels": legacy_labels,
            "active_allowed_label": False,
            "replacement_active_labels": raw["n4_context_allowed_signal_types"],
        }
    return raw


def insert_quality_items(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    run_id: str,
    preflight: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
) -> int:
    rows = []
    for item in items:
        gate_code = str(item.get("gate_code") or "")
        rows.append(
            (
                run_id,
                preflight["source_condition_run_id"],
                preflight["for_trade_date"],
                preflight["source_trade_date"],
                infer_quality_domain(gate_code),
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
    run_id: str,
    preflight: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
) -> int:
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id="n4_context_append_quality_items",
        source_run_id=run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            inserted = insert_quality_items(cur, run_id=run_id, preflight=preflight, items=items)
        conn.commit()
    return inserted


def build_execute_quality_items(
    *,
    preflight: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    expected_condition_run_id: str = EXPECTED_CONDITION_RUN_ID,
    market_data_run_id: str | None = None,
    market_data_run_summary: Mapping[str, Any] | None = None,
    market_subscription_run_id: str | None = None,
    market_subscription_run_summary: Mapping[str, Any] | None = None,
    market_trace_summary: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    items = list(preflight["quality"]["items"])
    market_summary = market_data_run_summary or {}
    subscription_summary = market_subscription_run_summary or {}
    trace_summary = market_trace_summary or {}
    items.extend(
        [
            quality_item(
                "P0",
                "passed" if preflight.get("source_condition_run_id") == expected_condition_run_id else "failed",
                "n4_3_expected_condition_run_confirmed",
                "N4-3 must localize the explicitly confirmed active condition run",
                expected=expected_condition_run_id,
                actual=str(preflight.get("source_condition_run_id")),
            ),
            quality_item(
                "P0",
                "passed" if len(context_rows) == int(preflight["candidate_context_row_count"]) else "failed",
                "n4_3_preflight_rows_loaded",
                "N4-3 execute must load all preflight candidate rows",
                expected=str(preflight["candidate_context_row_count"]),
                actual=str(len(context_rows)),
            ),
            quality_item("P0", "passed", "n4_3_no_market_data_pull", "N4-3 does not pull market data"),
            quality_item("P0", "passed", "n4_3_no_n3_event_consumption", "N4-3 does not consume N3 events"),
            quality_item("P0", "passed", "n4_3_no_worker_or_downstream", "N4-3 does not start workers or enter N5/N6"),
            quality_item("P0", "passed", "n4_3_no_outbox_write", "N4-3 does not write TriggerMatched/Cleared/Pending outbox events"),
        ]
    )
    if market_data_run_id:
        items.extend(
            [
                quality_item(
                    "P0",
                    "passed" if market_summary.get("run_id") == market_data_run_id else "failed",
                    "n4_3_market_data_run_found",
                    "N4 context rebuild must trace the requested N3 market_data_run",
                    expected=market_data_run_id,
                    actual=str(market_summary.get("run_id")),
                ),
                quality_item(
                    "P0",
                    "passed" if market_summary.get("status") == "passed" else "failed",
                    "n4_3_market_data_run_status_passed",
                    "N3 market_data_run must be passed before N4 context localization",
                    expected="passed",
                    actual=str(market_summary.get("status")),
                ),
                quality_item(
                    "P0",
                    "passed" if market_summary.get("source_condition_run_id") == preflight.get("source_condition_run_id") else "failed",
                    "n4_3_market_data_run_source_condition_matches",
                    "N3 market_data_run source_condition_run_id must match the N4 source condition run",
                    expected=str(preflight.get("source_condition_run_id")),
                    actual=str(market_summary.get("source_condition_run_id")),
                ),
                quality_item(
                    "P0",
                    "passed" if int(trace_summary.get("untraced_context_row_count") or 0) == 0 else "failed",
                    "n4_3_market_subscription_trace_complete",
                    "N4 context rows must be traceable to the N3 realtime_daily_snapshot subscription run",
                    expected="0 untraced context rows",
                    actual=str(trace_summary.get("untraced_context_row_count")),
                    details={"untraced_sample": trace_summary.get("untraced_sample") or []},
                ),
            ]
        )
    if market_subscription_run_id and market_subscription_run_id != market_data_run_id:
        items.extend(
            [
                quality_item(
                    "P0",
                    "passed" if subscription_summary.get("run_id") == market_subscription_run_id else "failed",
                    "n4_3_market_subscription_run_found",
                    "N4 context rows must trace the requested N3 subscription run",
                    expected=market_subscription_run_id,
                    actual=str(subscription_summary.get("run_id")),
                ),
                quality_item(
                    "P0",
                    "passed" if subscription_summary.get("status") == "passed" else "failed",
                    "n4_3_market_subscription_run_status_passed",
                    "N3 subscription run must be passed before N4 context localization",
                    expected="passed",
                    actual=str(subscription_summary.get("status")),
                ),
                quality_item(
                    "P0",
                    "passed" if subscription_summary.get("source_condition_run_id") == preflight.get("source_condition_run_id") else "failed",
                    "n4_3_market_subscription_source_condition_matches",
                    "N3 subscription run source_condition_run_id must match the N4 source condition run",
                    expected=str(preflight.get("source_condition_run_id")),
                    actual=str(subscription_summary.get("source_condition_run_id")),
                ),
            ]
        )
    return items


def build_post_quality_items(post_checks: Mapping[str, bool]) -> list[dict[str, Any]]:
    return [
        quality_item(
            "P0",
            "passed" if passed else "failed",
            f"n4_3_{check_name}",
            f"N4-3 post execute check: {check_name}",
            expected="true",
            actual=str(passed).lower(),
        )
        for check_name, passed in post_checks.items()
    ]


def refresh_run_quality_counts(
    dsn: str,
    run_id: str,
    severity_counts: Mapping[str, int],
    quality_item_count: int,
) -> None:
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id="n4_context_refresh_quality_counts",
        source_run_id=run_id,
        readonly_expected=False,
        connect_timeout=10,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE common_trigger_run
                SET p0_count = %s,
                    p1_count = %s,
                    p2_count = %s,
                    updated_at = now(),
                    raw_json = coalesce(raw_json, '{}'::jsonb) || %s::jsonb
                WHERE run_id = %s
                """,
                (
                    int(severity_counts["P0"]),
                    int(severity_counts["P1"]),
                    int(severity_counts["P2"]),
                    json.dumps({"quality_item_count": quality_item_count}, ensure_ascii=False),
                    run_id,
                ),
            )
        conn.commit()


def capture_execution_snapshot(
    dsn: str,
    *,
    phase: str,
    condition_run_id: str,
) -> dict[str, Any]:
    table_names = tuple(dict.fromkeys((*REQUIRED_TRIGGER_TABLES, *N3_GUARD_TABLES, "common_condition_run")))
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id=f"n4_context_capture_{phase}",
        source_run_id=condition_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return {
            "phase": phase,
            "captured_at": utc_now_iso(),
            "row_counts": fetch_row_counts(cur, table_names),
            "condition_run_snapshot": fetch_condition_run_snapshot(cur, condition_run_id),
        }


def fetch_existing_active_context_runs(dsn: str, *, for_trade_date: str) -> list[dict[str, Any]]:
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id="n4_context_fetch_existing_active_runs",
        source_run_id=for_trade_date,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, status, mode, for_trade_date, source_condition_run_id, context_snapshot_row_count
            FROM common_trigger_run
            WHERE for_trade_date = %s
              AND mode = 'execute'
              AND status IN ('planned', 'running', 'passed')
              AND context_snapshot_row_count > 0
            ORDER BY created_at DESC
            """,
            (for_trade_date,),
        )
        return rows_to_json(cur.fetchall())


def fetch_market_data_run_summary(dsn: str, market_data_run_id: str) -> dict[str, Any]:
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id="n4_context_fetch_market_data_run_summary",
        source_run_id=market_data_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, status, mode, source_condition_run_id, for_trade_date,
                   source_trade_date, prev_trade_date, p0_count, p1_count, p2_count,
                   source_scope_row_count, candidate_row_count, subscription_row_count,
                   subscription_object_count, market_data_pulled, market_data_fact_written,
                   downstream_layers_touched, worker_started, finished_at, updated_at
            FROM common_market_data_run
            WHERE run_id = %s
            """,
            (market_data_run_id,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        summary = normalize_mapping(row)
        cur.execute(
            """
            SELECT required_data_kind, count(*)::bigint AS row_count,
                   count(DISTINCT identity_key)::bigint AS object_count
            FROM common_market_data_subscription
            WHERE run_id = %s
            GROUP BY required_data_kind
            ORDER BY required_data_kind
            """,
            (market_data_run_id,),
        )
        summary["subscription_counts_by_required_data_kind"] = rows_to_json(cur.fetchall())
        return summary


def attach_market_subscription_trace(
    *,
    dsn: str,
    market_data_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    subscriptions = fetch_market_subscriptions(dsn, market_data_run_id)
    return attach_market_subscription_trace_to_rows(
        context_rows=context_rows,
        subscriptions=subscriptions,
        market_data_run_id=market_data_run_id,
    )


def fetch_market_subscriptions(dsn: str, market_data_run_id: str) -> list[dict[str, Any]]:
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id="n4_context_fetch_market_subscriptions",
        source_run_id=market_data_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT subscription_id, run_id, source_condition_run_id, for_trade_date,
                   asset_kind, identity_key, required_data_kind, status,
                   source_scope_ids, source_condition_pool_ids, condition_keys,
                   directions, allowed_signal_types
            FROM common_market_data_subscription
            WHERE run_id = %s
            ORDER BY asset_kind, identity_key, required_data_kind, subscription_id
            """,
            (market_data_run_id,),
        )
        return [normalize_mapping(row) for row in cur.fetchall()]


def attach_market_subscription_trace_to_rows(
    *,
    context_rows: Sequence[Mapping[str, Any]],
    subscriptions: Sequence[Mapping[str, Any]],
    market_data_run_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    primary_subscription_by_object: dict[tuple[str, str], dict[str, Any]] = {}
    priority = {"realtime_daily_snapshot": 0, "minute_bar_1m": 1, "previous_day_minute_bar_1m": 2}
    for subscription in subscriptions:
        key = (str(subscription.get("asset_kind") or ""), str(subscription.get("identity_key") or ""))
        current = primary_subscription_by_object.get(key)
        if current is None or priority.get(str(subscription.get("required_data_kind") or ""), 99) < priority.get(
            str(current.get("required_data_kind") or ""), 99
        ):
            primary_subscription_by_object[key] = dict(subscription)

    output: list[dict[str, Any]] = []
    untraced_sample: list[dict[str, Any]] = []
    traced_count = 0
    for row in context_rows:
        normalized = normalize_mapping(row)
        key = (str(normalized.get("asset_kind") or ""), str(normalized.get("identity_key") or ""))
        subscription = primary_subscription_by_object.get(key)
        if subscription:
            normalized["source_market_subscription_id"] = int(subscription["subscription_id"])
            traced_count += 1
        else:
            normalized["source_market_subscription_id"] = None
            if len(untraced_sample) < 20:
                untraced_sample.append(
                    {
                        "asset_kind": normalized.get("asset_kind"),
                        "identity_key": normalized.get("identity_key"),
                        "condition_key": normalized.get("condition_key"),
                    }
                )
        output.append(normalized)

    required_data_kind_counts = dict(
        sorted(Counter(str(item.get("required_data_kind") or "") for item in subscriptions).items())
    )
    return output, {
        "market_data_run_id": market_data_run_id,
        "context_row_count": len(context_rows),
        "traced_context_row_count": traced_count,
        "untraced_context_row_count": len(context_rows) - traced_count,
        "subscription_row_count": len(subscriptions),
        "subscription_object_count": len(primary_subscription_by_object),
        "subscription_required_data_kind_counts": required_data_kind_counts,
        "primary_required_data_kind": "realtime_daily_snapshot",
        "untraced_sample": untraced_sample,
    }


def fetch_existing_n4_lineage_report(
    dsn: str,
    *,
    current_condition_run_id: str,
) -> dict[str, Any]:
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id="n4_context_fetch_existing_n4_lineage_report",
        source_run_id=current_condition_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, source_condition_run_id, source_market_data_run_id,
                   for_trade_date, mode, status, context_snapshot_row_count,
                   trigger_state_row_count, trigger_match_row_count,
                   trigger_event_outbox_count, created_at, updated_at
            FROM common_trigger_run
            ORDER BY created_at DESC
            """
        )
        runs = rows_to_json(cur.fetchall())
        cur.execute(
            """
            SELECT source_run_id, event_type, count(*)::bigint AS row_count
            FROM common_event_outbox
            WHERE source_layer = 'N4_trigger'
            GROUP BY source_run_id, event_type
            ORDER BY source_run_id, event_type
            """
        )
        outbox_by_run = rows_to_json(cur.fetchall())
    old_runs = [row for row in runs if row.get("source_condition_run_id") != current_condition_run_id]
    return {
        "current_condition_run_id": current_condition_run_id,
        "existing_trigger_runs": runs,
        "old_trigger_runs": old_runs,
        "old_trigger_run_count": len(old_runs),
        "n4_outbox_by_source_run": outbox_by_run,
    }


def fetch_row_counts(cur: psycopg.Cursor[dict[str, Any]], table_names: Sequence[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for table_name in table_names:
        if not table_exists(cur, table_name):
            output[table_name] = {"exists": False, "row_count": None, "status": "missing"}
            continue
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
        row = cur.fetchone()
        output[table_name] = {"exists": True, "row_count": int(row["row_count"]), "status": "present"}
    return output


def fetch_condition_run_snapshot(cur: psycopg.Cursor[dict[str, Any]], condition_run_id: str) -> dict[str, Any]:
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


def table_exists(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
    return cur.fetchone()["regclass"] is not None


def fetch_context_summary(dsn: str, run_id: str) -> dict[str, Any]:
    with audited_n4_context_refresh_connect(
        dsn,
        stage_id="n4_context_fetch_context_summary",
        source_run_id=run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        rows: list[dict[str, Any]] = []
        for asset_kind in ASSET_KINDS:
            table_name = TARGET_CONTEXT_TABLES[asset_kind]
            cur.execute(
                f"""
                SELECT asset_kind, identity_key, direction, condition_key,
                       condition_periods, allowed_signal_types,
                       source_condition_run_id, source_trade_date,
                       source_market_subscription_id, raw_json
                FROM {table_name}
                WHERE run_id = %s
                """,
                (run_id,),
            )
            rows.extend(normalize_mapping(row) for row in cur.fetchall())
        cur.execute(
            """
            SELECT run_id, status, source_condition_run_id, source_market_data_run_id, for_trade_date,
                   context_snapshot_row_count, trigger_state_row_count,
                   trigger_match_row_count, trigger_event_outbox_count
            FROM common_trigger_run
            WHERE run_id = %s
            """,
            (run_id,),
        )
        trigger_run = normalize_mapping(cur.fetchone() or {})
        summary = summarize_context_rows(rows)
        summary["trigger_run"] = trigger_run
        return summary


def summarize_context_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows_with_baseline = context_rows_with_baseline(rows)
    return {
        "row_count": len(rows),
        "row_count_by_asset_kind": {
            asset_kind: sum(1 for row in rows if row.get("asset_kind") == asset_kind)
            for asset_kind in ASSET_KINDS
        },
        "object_count_by_asset_kind": object_count_by_asset_kind(rows),
        "direction_distribution": dict(sorted(Counter(str(row.get("direction") or "") for row in rows).items())),
        "condition_key_counts": dict(sorted(Counter(str(row.get("condition_key") or "") for row in rows).items())),
        "buy_hint_row_count": sum(1 for row in rows if row.get("condition_key") == "BUY_HINT"),
        "sell_hint_row_count": sum(1 for row in rows if row.get("condition_key") == "SELL_HINT"),
        "source_condition_run_ids": sorted({str(row.get("source_condition_run_id") or "") for row in rows}),
        "source_market_subscription_id_nonnull_count": sum(
            1 for row in rows if row.get("source_market_subscription_id") is not None
        ),
        "source_market_subscription_id_null_count": sum(
            1 for row in rows if row.get("source_market_subscription_id") is None
        ),
        "period_trigger_baseline_json_missing": period_trigger_baseline_json_missing_count(rows_with_baseline),
        "required_period_not_ready_rows": required_period_not_ready_rows_count(rows_with_baseline),
    }


def context_rows_with_baseline(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        raw_json = item.get("raw_json") or {}
        if isinstance(raw_json, Mapping):
            item["period_trigger_baseline_json"] = raw_json.get("period_trigger_baseline_json") or {}
        else:
            item["period_trigger_baseline_json"] = {}
        enriched.append(item)
    return enriched


def object_count_by_asset_kind(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    grouped: dict[str, set[str]] = {asset_kind: set() for asset_kind in ASSET_KINDS}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        identity_key = str(row.get("identity_key") or "")
        if asset_kind in grouped and identity_key:
            grouped[asset_kind].add(identity_key)
    return {asset_kind: len(grouped[asset_kind]) for asset_kind in ASSET_KINDS}


def build_post_execute_checks(
    *,
    preflight: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    inserted_counts: Mapping[str, int],
    post_context_summary: Mapping[str, Any],
    run_id: str,
    condition_run_id: str,
    market_data_run_id: str | None = None,
    check_quality_item_delta: bool = True,
) -> dict[str, bool]:
    before_counts = before_snapshot["row_counts"]
    after_counts = after_snapshot["row_counts"]
    expected_by_asset = preflight["condition_row_count_by_asset_kind"]
    context_rows_match = int(post_context_summary["row_count"]) == int(preflight["candidate_context_row_count"])
    context_by_asset_match = post_context_summary["row_count_by_asset_kind"] == expected_by_asset
    direction_match = post_context_summary["direction_distribution"] == preflight["direction_distribution"]
    condition_key_match = post_context_summary["condition_key_counts"] == preflight["condition_key_counts"]
    hint_match = (
        int(post_context_summary["buy_hint_row_count"]) == int(preflight["buy_hint_row_count"])
        and int(post_context_summary["sell_hint_row_count"]) == int(preflight["sell_hint_row_count"])
    )
    allowed_n4_deltas = {
        "common_trigger_run": 1,
        "stock_trigger_context_snapshot": int(expected_by_asset["stock"]),
        "index_trigger_context_snapshot": int(expected_by_asset["index"]),
        "board_trigger_context_snapshot": int(expected_by_asset["board"]),
    }
    if check_quality_item_delta:
        allowed_n4_deltas["common_trigger_quality_item"] = int(inserted_counts["common_trigger_quality_item"])
    allowed_n4_delta_match = all(
        row_count_delta(before_counts, after_counts, table_name) == delta
        for table_name, delta in allowed_n4_deltas.items()
    )
    forbidden_unchanged = all(
        row_count_delta(before_counts, after_counts, table_name) == 0
        for table_name in N4_FORBIDDEN_WRITE_TABLES
    )
    n3_unchanged = all(
        before_counts.get(table_name) == after_counts.get(table_name)
        for table_name in N3_GUARD_TABLES
    )
    checks = {
        "run_id_written": after_counts["common_trigger_run"]["row_count"] == before_counts["common_trigger_run"]["row_count"] + 1,
        "context_snapshot_row_count_matches_preflight": context_rows_match,
        "context_snapshot_asset_distribution_matches_preflight": context_by_asset_match,
        "context_snapshot_direction_distribution_matches_preflight": direction_match,
        "context_snapshot_condition_key_distribution_matches_preflight": condition_key_match,
        "buy_hint_and_sell_hint_present": hint_match,
        "source_condition_run_id_traceable": post_context_summary["source_condition_run_ids"] == [condition_run_id],
        "period_trigger_baseline_json_localized": int(post_context_summary.get("period_trigger_baseline_json_missing") or 0) == 0,
        "required_period_not_ready_rows_zero": int(post_context_summary.get("required_period_not_ready_rows") or 0) == 0,
        "inserted_count_matches_allowed_n4_delta": allowed_n4_delta_match,
        "trigger_state_match_outbox_unchanged": forbidden_unchanged,
        "n2_active_run_unchanged": before_snapshot["condition_run_snapshot"] == after_snapshot["condition_run_snapshot"],
        "n3_facts_and_outbox_unchanged": n3_unchanged,
        "trigger_run_status_passed": trigger_run_status_passed(post_context_summary, run_id),
    }
    if market_data_run_id:
        trigger_run = post_context_summary.get("trigger_run") or {}
        checks["source_market_data_run_id_traceable"] = trigger_run.get("source_market_data_run_id") == market_data_run_id
        checks["source_market_subscription_trace_complete"] = (
            int(post_context_summary.get("source_market_subscription_id_nonnull_count") or 0)
            == int(preflight["candidate_context_row_count"])
            and int(post_context_summary.get("source_market_subscription_id_null_count") or 0) == 0
        )
    return checks


def trigger_run_status_passed(post_context_summary: Mapping[str, Any], run_id: str) -> bool:
    trigger_run = post_context_summary.get("trigger_run") or {}
    return bool(
        trigger_run.get("run_id") == run_id
        and trigger_run.get("status") == "passed"
        and int(trigger_run.get("trigger_state_row_count") or 0) == 0
        and int(trigger_run.get("trigger_match_row_count") or 0) == 0
        and int(trigger_run.get("trigger_event_outbox_count") or 0) == 0
    )


def row_count_delta(
    before_counts: Mapping[str, Mapping[str, Any]],
    after_counts: Mapping[str, Mapping[str, Any]],
    table_name: str,
) -> int:
    before = int(before_counts[table_name]["row_count"] or 0)
    after = int(after_counts[table_name]["row_count"] or 0)
    return after - before


def summarize_preflight(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_condition_run_id": preflight.get("source_condition_run_id"),
        "for_trade_date": preflight.get("for_trade_date"),
        "source_trade_date": preflight.get("source_trade_date"),
        "prev_trade_date": preflight.get("prev_trade_date"),
        "candidate_context_row_count": preflight.get("candidate_context_row_count"),
        "condition_row_count_by_asset_kind": preflight.get("condition_row_count_by_asset_kind"),
        "object_count_by_asset_kind": preflight.get("object_count_by_asset_kind"),
        "direction_distribution": preflight.get("direction_distribution"),
        "condition_key_counts": preflight.get("condition_key_counts"),
        "buy_hint_row_count": preflight.get("buy_hint_row_count"),
        "sell_hint_row_count": preflight.get("sell_hint_row_count"),
        "p0_count": preflight.get("quality", {}).get("p0_count"),
        "p1_count": preflight.get("quality", {}).get("p1_count"),
        "p2_count": preflight.get("quality", {}).get("p2_count"),
    }


def summarize_schema_review(schema_review: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target_tables_missing": schema_review["target_tables_missing"],
        "missing_dependency_tables": schema_review["missing_dependency_tables"],
        "missing_columns_count": len(schema_review["missing_columns"]),
        "type_mismatch_count": len(schema_review["type_mismatch"]),
        "missing_unique_constraints_count": len(schema_review["missing_unique_constraints"]),
        "p0_count": schema_review["quality"]["p0_count"],
        "p1_count": schema_review["quality"]["p1_count"],
        "p2_count": schema_review["quality"]["p2_count"],
    }


def infer_quality_domain(gate_code: str) -> str:
    if gate_code.startswith("stock_"):
        return "stock"
    if gate_code.startswith("index_"):
        return "index"
    if gate_code.startswith("board_"):
        return "board"
    return "common"


def infer_quality_scope(gate_code: str) -> str:
    if "event_contract" in gate_code:
        return "event_contract"
    if "state" in gate_code:
        return "trigger_state"
    if "match" in gate_code:
        return "trigger_match"
    if "run" in gate_code:
        return "trigger_run"
    return "trigger_context_snapshot"


def infer_quality_table(gate_code: str) -> str | None:
    if gate_code.startswith("stock_"):
        return "stock_trigger_context_snapshot"
    if gate_code.startswith("index_"):
        return "index_trigger_context_snapshot"
    if gate_code.startswith("board_"):
        return "board_trigger_context_snapshot"
    if "outbox" in gate_code:
        return "common_event_outbox"
    if "run" in gate_code:
        return "common_trigger_run"
    return None


def build_trigger_context_rollback_sql(run_id: str) -> str:
    return "\n".join(
        [
            "-- A-share monitor v3 N4 trigger context rollback.",
            "-- Execute only after confirming this N4 context run has not been consumed downstream.",
            "-- This rollback deletes only N4 trigger context/run/quality rows for one run_id.",
            "-- Optional N6/user tables are checked with to_regclass so the rollback is portable.",
            "",
            "BEGIN;",
            "",
            "DO $$",
            "DECLARE",
            f"  v_run_id TEXT := '{run_id}';",
            "  v_allowed TEXT := current_setting('ashare_v3.allow_n4_context_rollback_run_id', true);",
            "  v_count BIGINT;",
            "BEGIN",
            "  IF v_allowed IS DISTINCT FROM v_run_id THEN",
            "    RAISE EXCEPTION 'N4 context rollback hard-fail: set ashare_v3.allow_n4_context_rollback_run_id=% before mutation', v_run_id;",
            "  END IF;",
            "",
            "  SELECT count(*) INTO v_count",
            "  FROM common_event_outbox",
            "  WHERE source_layer = 'N4_trigger'",
            "    AND source_run_id = v_run_id",
            "    AND status IN ('delivered', 'delivering');",
            "  IF v_count <> 0 THEN",
            "    RAISE EXCEPTION 'Refusing N4 context rollback: scoped outbox already delivered/delivering has % rows for %', v_count, v_run_id;",
            "  END IF;",
            "",
            "  SELECT count(*) INTO v_count",
            "  FROM common_event_outbox",
            "  WHERE (source_layer = 'N4_trigger' AND source_run_id = v_run_id)",
            "     OR payload_json::TEXT LIKE '%' || v_run_id || '%';",
            "  IF v_count <> 0 THEN",
            "    RAISE EXCEPTION 'Refusing N4 context rollback: outbox has % rows for %', v_count, v_run_id;",
            "  END IF;",
            "",
            "  SELECT count(*) INTO v_count",
            "  FROM common_event_inbox",
            "  WHERE source_run_id = v_run_id",
            "     OR raw_json::TEXT LIKE '%' || v_run_id || '%'",
            "     OR payload_json::TEXT LIKE '%' || v_run_id || '%';",
            "  IF v_count <> 0 THEN",
            "    RAISE EXCEPTION 'Refusing N4 context rollback: inbox has % rows for %', v_count, v_run_id;",
            "  END IF;",
            "",
            "  SELECT count(*) INTO v_count",
            "  FROM common_event_consumer_checkpoint",
            "  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%'",
            "     OR last_event_id LIKE '%' || v_run_id || '%';",
            "  IF v_count <> 0 THEN",
            "    RAISE EXCEPTION 'Refusing N4 context rollback: checkpoint has % rows for %', v_count, v_run_id;",
            "  END IF;",
            "",
            "  SELECT count(*) INTO v_count",
            "  FROM common_trigger_match",
            "  WHERE run_id = v_run_id",
            "     OR raw_json::TEXT LIKE '%' || v_run_id || '%';",
            "  IF v_count <> 0 THEN",
            "    RAISE EXCEPTION 'Refusing N4 context rollback: trigger_match has % rows for %', v_count, v_run_id;",
            "  END IF;",
            "",
            "  SELECT count(*) INTO v_count",
            "  FROM common_trigger_state",
            "  WHERE run_id = v_run_id",
            "     OR raw_json::TEXT LIKE '%' || v_run_id || '%';",
            "  IF v_count <> 0 THEN",
            "    RAISE EXCEPTION 'Refusing N4 context rollback: trigger_state has % rows for %', v_count, v_run_id;",
            "  END IF;",
            "",
            "  SELECT count(*) INTO v_count",
            "  FROM common_action_run",
            "  WHERE source_trigger_run_id = v_run_id",
            "     OR raw_json::TEXT LIKE '%' || v_run_id || '%';",
            "  IF v_count <> 0 THEN",
            "    RAISE EXCEPTION 'Refusing N4 context rollback: N5 action_run has % rows for %', v_count, v_run_id;",
            "  END IF;",
            "",
            "  SELECT count(*) INTO v_count",
            "  FROM common_action_event",
            "  WHERE source_trigger_run_id = v_run_id",
            "     OR payload_json::TEXT LIKE '%' || v_run_id || '%'",
            "     OR trace_json::TEXT LIKE '%' || v_run_id || '%';",
            "  IF v_count <> 0 THEN",
            "    RAISE EXCEPTION 'Refusing N4 context rollback: N5 action_event has % rows for %', v_count, v_run_id;",
            "  END IF;",
            "",
            "  IF to_regclass('public.user_projection_run') IS NOT NULL THEN",
            "    EXECUTE $SQL$",
            "      SELECT count(*)",
            "      FROM user_projection_run",
            "      WHERE to_jsonb(user_projection_run)::TEXT LIKE '%' || $1 || '%'",
            "    $SQL$ INTO v_count USING v_run_id;",
            "    IF v_count <> 0 THEN",
            "      RAISE EXCEPTION 'Refusing N4 context rollback: user_projection_run has % rows for %', v_count, v_run_id;",
            "    END IF;",
            "  END IF;",
            "",
            "  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN",
            "    EXECUTE $SQL$",
            "      SELECT count(*)",
            "      FROM user_signal_projection",
            "      WHERE to_jsonb(user_signal_projection)::TEXT LIKE '%' || $1 || '%'",
            "    $SQL$ INTO v_count USING v_run_id;",
            "    IF v_count <> 0 THEN",
            "      RAISE EXCEPTION 'Refusing N4 context rollback: user_signal_projection has % rows for %', v_count, v_run_id;",
            "    END IF;",
            "  END IF;",
            "",
            "  IF to_regclass('public.user_signal_card') IS NOT NULL THEN",
            "    EXECUTE $SQL$",
            "      SELECT count(*)",
            "      FROM user_signal_card",
            "      WHERE to_jsonb(user_signal_card)::TEXT LIKE '%' || $1 || '%'",
            "    $SQL$ INTO v_count USING v_run_id;",
            "    IF v_count <> 0 THEN",
            "      RAISE EXCEPTION 'Refusing N4 context rollback: user_signal_card has % rows for %', v_count, v_run_id;",
            "    END IF;",
            "  END IF;",
            "",
            "  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN",
            "    EXECUTE $SQL$",
            "      SELECT count(*)",
            "      FROM user_notification_queue",
            "      WHERE to_jsonb(user_notification_queue)::TEXT LIKE '%' || $1 || '%'",
            "    $SQL$ INTO v_count USING v_run_id;",
            "    IF v_count <> 0 THEN",
            "      RAISE EXCEPTION 'Refusing N4 context rollback: user_notification_queue has % rows for %', v_count, v_run_id;",
            "    END IF;",
            "  END IF;",
            "",
            "  IF to_regclass('public.user_sim_order') IS NOT NULL THEN",
            "    EXECUTE $SQL$",
            "      SELECT count(*)",
            "      FROM user_sim_order",
            "      WHERE to_jsonb(user_sim_order)::TEXT LIKE '%' || $1 || '%'",
            "    $SQL$ INTO v_count USING v_run_id;",
            "    IF v_count <> 0 THEN",
            "      RAISE EXCEPTION 'Refusing N4 context rollback: user_sim_order has % rows for %', v_count, v_run_id;",
            "    END IF;",
            "  END IF;",
            "",
            "  IF to_regclass('public.user_sim_position') IS NOT NULL THEN",
            "    EXECUTE $SQL$",
            "      SELECT count(*)",
            "      FROM user_sim_position",
            "      WHERE to_jsonb(user_sim_position)::TEXT LIKE '%' || $1 || '%'",
            "    $SQL$ INTO v_count USING v_run_id;",
            "    IF v_count <> 0 THEN",
            "      RAISE EXCEPTION 'Refusing N4 context rollback: user_sim_position has % rows for %', v_count, v_run_id;",
            "    END IF;",
            "  END IF;",
            "",
            "  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN",
            "    EXECUTE $SQL$",
            "      SELECT count(*)",
            "      FROM user_sim_trade",
            "      WHERE to_jsonb(user_sim_trade)::TEXT LIKE '%' || $1 || '%'",
            "    $SQL$ INTO v_count USING v_run_id;",
            "    IF v_count <> 0 THEN",
            "      RAISE EXCEPTION 'Refusing N4 context rollback: user_sim_trade has % rows for %', v_count, v_run_id;",
            "    END IF;",
            "  END IF;",
            "END $$;",
            "",
            f"DELETE FROM common_trigger_quality_item WHERE run_id = '{run_id}';",
            f"DELETE FROM stock_trigger_context_snapshot WHERE run_id = '{run_id}';",
            f"DELETE FROM index_trigger_context_snapshot WHERE run_id = '{run_id}';",
            f"DELETE FROM board_trigger_context_snapshot WHERE run_id = '{run_id}';",
            f"DELETE FROM common_trigger_run WHERE run_id = '{run_id}';",
            "",
            "COMMIT;",
            "",
            "-- Boundary:",
            "-- - Does not touch common_condition_run or condition tables.",
            "-- - Does not touch common_market_data_* or market data fact tables.",
            "-- - Does not touch common_event_outbox.",
            "-- - Does not touch trigger_state / trigger_match because N4-3 never writes them.",
            "-- - Does not touch action/user/voice/mobile/sim/position tables.",
            "",
        ]
    )


def format_trigger_context_execute_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        f"# {report['stage']} Trigger Context Snapshot Execute Report",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- run_id: {report['run_id']}",
        f"- source_condition_run_id: {report['source_condition_run_id']}",
        f"- source_market_data_run_id: {report.get('source_market_data_run_id')}",
        f"- for_trade_date: {report['for_trade_date']}",
        f"- source_trade_date: {report['source_trade_date']}",
        f"- rollback_sql_path: {report['rollback_sql_path']}",
        f"- started_at: {report['started_at']}",
        f"- finished_at: {report['finished_at']}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Write Counts",
        "",
    ]
    for table_name, count in report["inserted_counts"].items():
        lines.append(f"- {table_name}: {count}")
    lines.extend(
        [
            "",
            "## Before / After Row Counts",
            "",
        ]
    )
    for table_name in (*N4_WRITABLE_CONTEXT_TABLES, *N4_FORBIDDEN_WRITE_TABLES):
        before = report["before_row_counts"].get(table_name, {}).get("row_count")
        after = report["after_row_counts"].get(table_name, {}).get("row_count")
        lines.append(f"- {table_name}: before={before} after={after}")
    lines.extend(
        [
            "",
            "## Post Checks",
            "",
        ]
    )
    for check_name, passed in report["post_checks"].items():
        lines.append(f"- {check_name}: {str(passed).lower()}")
    lines.extend(
        [
            "",
            "## Context Summary",
            "",
            f"- row_count: {report['post_context_summary']['row_count']}",
            f"- row_count_by_asset_kind: {report['post_context_summary']['row_count_by_asset_kind']}",
            f"- direction_distribution: {report['post_context_summary']['direction_distribution']}",
            f"- buy_hint_row_count: {report['post_context_summary']['buy_hint_row_count']}",
            f"- sell_hint_row_count: {report['post_context_summary']['sell_hint_row_count']}",
            f"- period_trigger_baseline_json_missing: {report['post_context_summary'].get('period_trigger_baseline_json_missing')}",
            f"- required_period_not_ready_rows: {report['post_context_summary'].get('required_period_not_ready_rows')}",
            f"- source_market_subscription_id_nonnull_count: {report['post_context_summary'].get('source_market_subscription_id_nonnull_count')}",
            f"- source_market_subscription_id_null_count: {report['post_context_summary'].get('source_market_subscription_id_null_count')}",
            "",
            "## Upstream Trace",
            "",
            f"- market_data_run_status: {report.get('market_data_run_summary', {}).get('status')}",
            f"- market_data_run_source_condition_run_id: {report.get('market_data_run_summary', {}).get('source_condition_run_id')}",
            f"- market_subscription_trace_summary: {report.get('market_subscription_trace_summary')}",
            "",
            "## Existing N4 Lineage",
            "",
            f"- old_trigger_run_count: {report.get('existing_n4_lineage_report', {}).get('old_trigger_run_count')}",
            f"- common_event_outbox_baseline_count: {report.get('common_event_outbox_baseline_count')}",
            "",
            "## Boundary Confirmation",
            "",
        ]
    )
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.extend(
        [
            "",
            "## Rollback",
            "",
            f"Rollback SQL: {report['rollback_sql_path']}",
            "",
            "Use it only before N4-4/N4-5 consumes this context run. It deletes only this run_id from "
            "common_trigger_quality_item, stock/index/board_trigger_context_snapshot, and common_trigger_run.",
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


def rows_to_json(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{key: normalize_json_value(value) for key, value in dict(row).items()} for row in rows]


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
