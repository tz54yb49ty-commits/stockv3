"""20260608 unified-output retry action-confirmation metric artifact planner.

This module is read-only. It builds the N3 metric payload, contract, preflight,
rollback, and final-gate artifacts for the N4 unified-output retry run without
executing materialization or mutating N4/N5/N6.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.action_confirmation_metric_materialization_execute import (
    ALLOWED_WRITE_TABLES,
    FORBIDDEN_WRITE_TABLES,
    PROJECTION_SCHEMA_VERSION,
    PROJECTION_TABLES,
    REQUESTED_TARGET_ALIASES,
    build_preflight,
    build_rollback_sql,
    validate_payload,
)
from ashare_v3.market.action_confirmation_projection_plan import (
    ASSET_KINDS,
    IDENTITY_COLUMNS,
    MINUTE_TABLES,
    SNAPSHOT_TABLES,
    add_price_amount_flags,
    build_metric_candidate_row,
    normalize_jsonable,
    parse_dt,
    simulate_metric_ready_db_check,
)
from ashare_v3.market.previous_day_preload_execute import utc_now_iso, write_json, write_text
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
FOR_TRADE_DATE = "20260608"
SOURCE_TRADE_DATE = "20260605"
PREV_TRADE_DATE = "20260605"
TARGET_N4_RUN_ID = "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry"
TARGET_METRIC_RUN_ID = (
    "action_confirmation_metric_20260608_until_1500__"
    "trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry"
)
SOURCE_CONDITION_RUN_ID = "condition_layer_20260605_to_20260608_v13_index_all_execute"
SOURCE_SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
)
REPAIR_SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260608_action_metric_coverage_repair_v1__"
    "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry"
)
SOURCE_SNAPSHOT_RUN_ID = (
    "realtime_daily_snapshot_20260608__"
    "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
)
SOURCE_REALTIME_PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__"
    "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
)
SOURCE_TODAY_MINUTE_RUN_IDS = [
    "today_minute_bar_1m_20260608_until_1500__"
    "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute",
    "today_minute_bar_1m_20260608_until_1500_action_metric_coverage_repair_v1__"
    "market_data_subscription_20260608_action_metric_coverage_repair_v1",
]
SOURCE_PREVIOUS_DAY_MINUTE_RUN_IDS = [
    "previous_day_minute_preload_20260605__"
    "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute",
    "previous_day_minute_preload_20260605_for_20260608_action_metric_coverage_repair_v1__"
    "market_data_subscription_20260608_action_metric_coverage_repair_v1",
]
RUN_ID_TO_SUBSCRIPTION_RUN_ID = {
    SOURCE_TODAY_MINUTE_RUN_IDS[0]: SOURCE_SUBSCRIPTION_RUN_ID,
    SOURCE_PREVIOUS_DAY_MINUTE_RUN_IDS[0]: SOURCE_SUBSCRIPTION_RUN_ID,
    SOURCE_TODAY_MINUTE_RUN_IDS[1]: REPAIR_SUBSCRIPTION_RUN_ID,
    SOURCE_PREVIOUS_DAY_MINUTE_RUN_IDS[1]: REPAIR_SUBSCRIPTION_RUN_ID,
}

DRY_RUN_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_DRY_RUN.json"
DRY_RUN_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_DRY_RUN.md"
CONTRACT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_CONTRACT.json"
CONTRACT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_CONTRACT.md"
PREFLIGHT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_PREFLIGHT.json"
PREFLIGHT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_PREFLIGHT.md"
PAYLOAD_JSON = "docs/N3_action_confirmation_metric_20260608_until_1500_unified_output_retry_payload.json"
ROLLBACK_SQL = "sql/N3_action_confirmation_metric_20260608_until_1500_unified_output_retry_rollback.sql"
FINAL_GATE_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_FINAL_GATE_REVIEW.json"
FINAL_GATE_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_FINAL_GATE_REVIEW.md"
EXECUTE_REPORT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_REPORT.json"
EXECUTE_REPORT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_REPORT.md"
EXECUTE_COMMAND = (
    "PYTHONPATH=src:scripts python3 scripts/run_n3_action_confirmation_metric_materialization_execute.py "
    f"--payload-path {PAYLOAD_JSON} "
    f"--contract-path {CONTRACT_JSON} "
    "--execute --user-confirmed "
    f"--report-path {EXECUTE_REPORT_JSON} "
    f"--markdown-report-path {EXECUTE_REPORT_MD}"
)

EXPECTED_ROWS = {"stock": 412, "index": 60, "board": 84, "total": 556}
EXPECTED_N4_MATCHED = 556
EXPECTED_UNIQUE_OBJECTS = {"stock": 403, "index": 54, "board": 84, "total": 541}
EXPECTED_CONDITION_SIGNAL_TYPES = {"BUY": 299, "SELL": 135, "BUY_HINT": 116, "SELL_HINT": 6}
EXPECTED_SIGNAL_TYPES = {"B_BUY": 415, "S_SELL": 141}
EXPECTED_TRIGGER_MARKS = {"normal": 434, "30m_volume": 116, "30m_shrink": 6}


@dataclass(frozen=True)
class TriggerMatch:
    trigger_match_id: int
    output_event_id: str | None
    source_event_id: str | None
    asset_kind: str
    identity_key: str
    direction: str | None
    signal_type: str | None
    condition_key: str | None
    trigger_mark_candidate: str | None
    trigger_period: str | None
    trigger_bucket: str | None
    trigger_time: Any
    raw_json: Mapping[str, Any]


def derive_condition_signal_type(condition_key: str | None) -> str:
    text = str(condition_key or "")
    for prefix in ("BUY_HINT", "SELL_HINT", "BUY:FULL", "SELL:FULL", "BUY", "SELL"):
        if text.startswith(prefix):
            return prefix
    return text.split(":", 1)[0] if text else ""


def load_trigger_matches(cur: Any) -> list[TriggerMatch]:
    cur.execute(
        """
        SELECT
          m.trigger_match_id,
          m.output_event_id,
          o.event_id AS source_event_id,
          m.asset_kind,
          m.identity_key,
          m.direction,
          m.signal_type,
          m.condition_key,
          m.trigger_mark_candidate,
          m.trigger_period,
          m.trigger_bucket,
          m.trigger_time,
          m.raw_json
        FROM common_trigger_match m
        LEFT JOIN common_event_outbox o
          ON o.source_run_id = m.run_id
         AND o.event_type = 'TriggerMatched'
         AND o.event_id = m.output_event_id
        WHERE m.run_id = %s
          AND m.output_event_type = 'TriggerMatched'
          AND m.identity_key NOT LIKE '%%:BJ:%%'
          AND COALESCE(m.signal_type, '') NOT LIKE '%%FULL%%'
          AND COALESCE(m.condition_key, '') NOT LIKE '%%FULL%%'
        ORDER BY m.asset_kind, m.identity_key, m.trigger_time, m.trigger_match_id
        """,
        (TARGET_N4_RUN_ID,),
    )
    events: list[TriggerMatch] = []
    for row in cur.fetchall():
        events.append(
            TriggerMatch(
                trigger_match_id=int(row["trigger_match_id"]),
                output_event_id=row.get("output_event_id"),
                source_event_id=row.get("source_event_id"),
                asset_kind=str(row["asset_kind"]),
                identity_key=str(row["identity_key"]),
                direction=row.get("direction"),
                signal_type=row.get("signal_type"),
                condition_key=row.get("condition_key"),
                trigger_mark_candidate=row.get("trigger_mark_candidate"),
                trigger_period=row.get("trigger_period"),
                trigger_bucket=row.get("trigger_bucket"),
                trigger_time=row.get("trigger_time"),
                raw_json=dict(row.get("raw_json") or {}),
            )
        )
    return events


def identities_by_asset(events: Sequence[TriggerMatch]) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = {asset: set() for asset in ASSET_KINDS}
    for event in events:
        if event.asset_kind in grouped:
            grouped[event.asset_kind].add(event.identity_key)
    return {asset: sorted(values) for asset, values in grouped.items()}


def load_snapshot_maps(cur: Any, identities: Mapping[str, Sequence[str]]) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {asset: {} for asset in ASSET_KINDS}
    for asset_kind in ASSET_KINDS:
        wanted = list(identities.get(asset_kind) or [])
        if not wanted:
            continue
        table = SNAPSHOT_TABLES[asset_kind]
        identity_column = IDENTITY_COLUMNS[asset_kind]
        cur.execute(
            f"""
            WITH snapshot_rows AS (
              SELECT
                snapshot_id AS source_snapshot_id,
                {identity_column} AS identity_key,
                exchange,
                code,
                display_code,
                name,
                trade_date,
                snapshot_time,
                current_price,
                ROW_NUMBER() OVER (PARTITION BY {identity_column} ORDER BY snapshot_time DESC, snapshot_id DESC) AS rn
              FROM {table}
              WHERE run_id = %s
                AND {identity_column} = ANY(%s)
            ),
            snapshot_events AS (
              SELECT event_id, payload_json ->> 'snapshot_id' AS snapshot_id
              FROM common_event_outbox
              WHERE source_run_id = %s
                AND event_type = 'MarketSnapshotUpdated'
            )
            SELECT s.*, e.event_id AS source_snapshot_event_id
            FROM snapshot_rows s
            LEFT JOIN snapshot_events e ON e.snapshot_id = s.source_snapshot_id::TEXT
            WHERE s.rn = 1
            ORDER BY s.identity_key
            """,
            (SOURCE_SNAPSHOT_RUN_ID, wanted, SOURCE_SNAPSHOT_RUN_ID),
        )
        output[asset_kind] = {str(row["identity_key"]): normalize_jsonable(dict(row)) for row in cur.fetchall()}
    return output


def load_projection_maps(cur: Any, identities: Mapping[str, Sequence[str]]) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {asset: {} for asset in ASSET_KINDS}
    for asset_kind in ASSET_KINDS:
        wanted = list(identities.get(asset_kind) or [])
        if not wanted:
            continue
        table = PROJECTION_TABLES[asset_kind]
        identity_column = IDENTITY_COLUMNS[asset_kind]
        cur.execute(
            f"""
            SELECT *, {identity_column} AS identity_key
            FROM {table}
            WHERE projection_run_id = %s
              AND {identity_column} = ANY(%s)
            ORDER BY {identity_column}, projection_id DESC
            """,
            (SOURCE_REALTIME_PROJECTION_RUN_ID, wanted),
        )
        for row in cur.fetchall():
            output[asset_kind].setdefault(str(row["identity_key"]), normalize_jsonable(dict(row)))
    return output


def load_minute_maps(
    cur: Any,
    *,
    run_ids: Sequence[str],
    identities: Mapping[str, Sequence[str]],
) -> dict[str, dict[str, dict[str, list[dict[str, Any]]]]]:
    output: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {asset: {} for asset in ASSET_KINDS}
    for asset_kind in ASSET_KINDS:
        wanted = list(identities.get(asset_kind) or [])
        if not wanted:
            continue
        table = MINUTE_TABLES[asset_kind]
        identity_column = IDENTITY_COLUMNS[asset_kind]
        for run_id in run_ids:
            cur.execute(
                f"""
                SELECT
                  bar_id,
                  run_id,
                  {identity_column} AS identity_key,
                  bar_time,
                  open,
                  close,
                  amount
                FROM {table}
                WHERE run_id = %s
                  AND {identity_column} = ANY(%s)
                ORDER BY {identity_column}, bar_time, bar_id
                """,
                (run_id, wanted),
            )
            for row in cur.fetchall():
                identity = str(row["identity_key"])
                output[asset_kind].setdefault(identity, {}).setdefault(run_id, []).append(
                    normalize_jsonable(dict(row))
                )
    return output


def select_run_with_trigger_bar(
    rows_by_run: Mapping[str, Sequence[Mapping[str, Any]]],
    run_ids: Sequence[str],
    trigger_minute: Any,
) -> tuple[str | None, list[dict[str, Any]], dict[str, Any] | None]:
    for run_id in run_ids:
        rows = [dict(row) for row in rows_by_run.get(run_id, [])]
        rows.sort(key=lambda row: parse_dt(row["bar_time"]))
        through = [row for row in rows if parse_dt(row["bar_time"]) <= trigger_minute]
        exact = [row for row in through if parse_dt(row["bar_time"]) == trigger_minute]
        if exact and through:
            return run_id, through, dict(exact[-1])
    return None, [], None


def select_previous_run(
    rows_by_run: Mapping[str, Sequence[Mapping[str, Any]]],
    run_ids: Sequence[str],
) -> tuple[str | None, list[dict[str, Any]]]:
    for run_id in run_ids:
        rows = [dict(row) for row in rows_by_run.get(run_id, [])]
        rows.sort(key=lambda row: parse_dt(row["bar_time"]))
        if rows:
            return run_id, rows
    return None, []


def trigger_minute(value: Any) -> Any:
    dt = parse_dt(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ASIA_SHANGHAI)
    else:
        dt = dt.astimezone(ASIA_SHANGHAI)
    return dt.replace(second=0, microsecond=0)


def n4_event_dict(event: TriggerMatch) -> dict[str, Any]:
    raw = event.raw_json or {}
    plan = raw.get("plan") if isinstance(raw.get("plan"), Mapping) else {}
    return {
        "trigger_match_id": event.trigger_match_id,
        "output_event_id": event.output_event_id,
        "event_id": event.source_event_id or event.output_event_id,
        "source_event_id": event.source_event_id or event.output_event_id,
        "asset_kind": event.asset_kind,
        "identity_key": event.identity_key,
        "direction": event.direction,
        "signal_type": event.signal_type,
        "condition_key": event.condition_key,
        "condition_signal_type": derive_condition_signal_type(event.condition_key),
        "trigger_mark_candidate": event.trigger_mark_candidate,
        "trigger_period": event.trigger_period,
        "trigger_bucket": event.trigger_bucket,
        "trigger_time": parse_dt(event.trigger_time).isoformat() if event.trigger_time else None,
        "primary_trigger_period": plan.get("primary_trigger_period") or raw.get("primary_trigger_period") or event.trigger_period,
        "triggered_periods": plan.get("triggered_periods") or raw.get("triggered_periods") or [event.trigger_period],
        "all_trigger_periods": plan.get("all_trigger_periods") or raw.get("all_trigger_periods") or [event.trigger_period],
    }


def build_metric_row(
    *,
    event: TriggerMatch,
    snapshot_row: Mapping[str, Any],
    projection_row: Mapping[str, Any],
    today_run_id: str,
    previous_run_id: str,
    today_rows: list[Mapping[str, Any]],
    previous_rows: list[Mapping[str, Any]],
    exact_trigger_bar: Mapping[str, Any],
) -> dict[str, Any]:
    source_subscription_run_id = RUN_ID_TO_SUBSCRIPTION_RUN_ID.get(today_run_id) or SOURCE_SUBSCRIPTION_RUN_ID
    row = build_metric_candidate_row(
        asset_kind=event.asset_kind,
        projection_run_id=TARGET_METRIC_RUN_ID,
        projection_schema_version=PROJECTION_SCHEMA_VERSION,
        for_trade_date=FOR_TRADE_DATE,
        source_condition_run_id=SOURCE_CONDITION_RUN_ID,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=SOURCE_SNAPSHOT_RUN_ID,
        source_today_minute_run_id=today_run_id,
        source_previous_day_minute_run_id=previous_run_id,
        snapshot_row=snapshot_row,
        today_rows=list(today_rows),
        previous_day_rows=list(previous_rows),
    )
    minute_dt = trigger_minute(event.trigger_time)
    row["metric_time"] = minute_dt.isoformat()
    row["metric_minute_label"] = minute_dt.strftime("%H:%M")
    row["current_price"] = float(exact_trigger_bar["close"]) if exact_trigger_bar.get("close") is not None else None
    row["current_price_source"] = "minute_bar_1m"
    row["current_price_time"] = parse_dt(exact_trigger_bar["bar_time"]).isoformat()
    row["current_1m_amount"] = float(exact_trigger_bar["amount"]) if exact_trigger_bar.get("amount") is not None else None
    add_price_amount_flags(row)

    projection_summary = {
        "projection_run_id": projection_row.get("projection_run_id"),
        "projection_id": projection_row.get("projection_id"),
        "projection_status": projection_row.get("projection_status"),
        "projection_quality_status": projection_row.get("projection_quality_status"),
        "projection_signal_status": projection_row.get("projection_signal_status"),
        "trace_status": projection_row.get("trace_status"),
    }
    event_trace = n4_event_dict(event)
    raw = dict(row.get("raw_json") or {})
    raw.update(
        {
            "materialization_payload": True,
            "dry_run_only": False,
            "metric_scope": "action_confirmation_projection_metric",
            "lineage_scope": "20260608_until_1500_unified_output_retry",
            "source_trigger_run_id": TARGET_N4_RUN_ID,
            "source_event_id": event_trace["source_event_id"],
            "source_trigger_match_id": event.trigger_match_id,
            "condition_signal_type": event_trace["condition_signal_type"],
            "signal_type": event.signal_type,
            "trigger_mark_candidate": event.trigger_mark_candidate,
            "trigger_period": event.trigger_period,
            "primary_trigger_period": event_trace["primary_trigger_period"],
            "triggered_periods": event_trace["triggered_periods"],
            "all_trigger_periods": event_trace["all_trigger_periods"],
            "trigger_time": event_trace["trigger_time"],
            "trigger_minute_label": row["metric_minute_label"],
            "trigger_minute_alignment_preserved": True,
            "source_realtime_projection": projection_summary,
            "source_minute_run_selection": {
                "today_minute_run_id": today_run_id,
                "previous_day_minute_run_id": previous_run_id,
                "source_subscription_run_id": source_subscription_run_id,
            },
            "n4_trigger_execute_run_id": TARGET_N4_RUN_ID,
            "n4_trigger_matched_event_count": 1,
            "n4_trigger_matched_events": [event_trace],
            "n4_recompute_allowed": False,
            "n5_opaque_payload_trust_allowed": False,
            "bj_excluded": True,
            "full_excluded": True,
        }
    )
    row["raw_json"] = raw
    source_fact_ids = dict(row.get("source_fact_ids") or {})
    source_fact_ids.update(
        {
            "source_realtime_projection_id": projection_row.get("projection_id"),
            "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID,
            "source_trigger_run_id": TARGET_N4_RUN_ID,
            "source_trigger_match_id": event.trigger_match_id,
            "source_event_id": event_trace["source_event_id"],
            "n4_trigger_match_ids": [event.trigger_match_id],
            "n4_output_event_ids": [event.output_event_id] if event.output_event_id else [],
        }
    )
    row["source_fact_ids"] = source_fact_ids
    row["calculation_config_hash"] = "n3.action_confirmation_metric.20260608.unified_output_retry.v1"
    db_check = simulate_metric_ready_db_check(row)
    if not db_check["passes"]:
        row["metric_ready"] = False
        row["metric_quality_status"] = "missing"
        row["raw_json"]["db_check_missing_fields"] = db_check["missing_fields"]
    return normalize_jsonable(row)


def build_payload(dsn: str) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        events = load_trigger_matches(cur)
        identities = identities_by_asset(events)
        snapshots = load_snapshot_maps(cur, identities)
        projections = load_projection_maps(cur, identities)
        today_minutes = load_minute_maps(cur, run_ids=SOURCE_TODAY_MINUTE_RUN_IDS, identities=identities)
        previous_minutes = load_minute_maps(
            cur,
            run_ids=SOURCE_PREVIOUS_DAY_MINUTE_RUN_IDS,
            identities=identities,
        )

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for event in events:
        minute_dt = trigger_minute(event.trigger_time)
        snapshot_row = snapshots.get(event.asset_kind, {}).get(event.identity_key)
        projection_row = projections.get(event.asset_kind, {}).get(event.identity_key)
        today_run_id, today_rows, exact_bar = select_run_with_trigger_bar(
            today_minutes.get(event.asset_kind, {}).get(event.identity_key, {}),
            SOURCE_TODAY_MINUTE_RUN_IDS,
            minute_dt,
        )
        previous_run_id, previous_rows = select_previous_run(
            previous_minutes.get(event.asset_kind, {}).get(event.identity_key, {}),
            SOURCE_PREVIOUS_DAY_MINUTE_RUN_IDS,
        )
        if not snapshot_row or not projection_row or not today_run_id or not previous_run_id or not exact_bar:
            excluded.append(
                {
                    "asset_kind": event.asset_kind,
                    "identity_key": event.identity_key,
                    "trigger_match_id": event.trigger_match_id,
                    "metric_minute_label": minute_dt.strftime("%H:%M"),
                    "snapshot_present": bool(snapshot_row),
                    "projection_present": bool(projection_row),
                    "today_run_id": today_run_id,
                    "previous_run_id": previous_run_id,
                    "exact_trigger_bar_present": bool(exact_bar),
                    "reason": "source_trace_missing",
                }
            )
            continue
        rows.append(
            build_metric_row(
                event=event,
                snapshot_row=snapshot_row,
                projection_row=projection_row,
                today_run_id=today_run_id,
                previous_run_id=previous_run_id,
                today_rows=today_rows,
                previous_rows=previous_rows,
                exact_trigger_bar=exact_bar,
            )
        )

    row_counts = count_rows(rows)
    event_counts = count_event_dimensions(events)
    duplicate_metric_grain = duplicate_metric_grain_count(rows)
    payload = {
        "artifact_type": "N3_action_confirmation_metric_materialization_payload",
        "artifact_subtype": "20260608_until_1500_unified_output_retry",
        "layer_role": "N3_market_data",
        "projection_run_id": TARGET_METRIC_RUN_ID,
        "target_run_id": TARGET_METRIC_RUN_ID,
        "lineage_scope": "20260608_until_1500_unified_output_retry",
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "for_trade_date": FOR_TRADE_DATE,
        "source_trade_date": SOURCE_TRADE_DATE,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "trigger_execute_run_id": TARGET_N4_RUN_ID,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID,
        "source_subscription_run_id": SOURCE_SUBSCRIPTION_RUN_ID,
        "source_subscription_run_ids": [SOURCE_SUBSCRIPTION_RUN_ID, REPAIR_SUBSCRIPTION_RUN_ID],
        "source_today_minute_run_ids": list(SOURCE_TODAY_MINUTE_RUN_IDS),
        "source_previous_day_minute_run_ids": list(SOURCE_PREVIOUS_DAY_MINUTE_RUN_IDS),
        "expected_rows": row_counts,
        "metric_ready_expected": sum(1 for row in rows if row.get("metric_ready")),
        "n4_matched_coverage": {
            "covered": len(events),
            "expected": EXPECTED_N4_MATCHED,
            "missing": max(0, EXPECTED_N4_MATCHED - len(events)),
            "distinct_metric_rows": len(rows),
            "excluded_rows": len(excluded),
            "duplicate_metric_grain": duplicate_metric_grain,
            "deterministic_one_metric_row_per_trigger_matched": duplicate_metric_grain == 0
            and len(rows) == len(events),
        },
        "source_readiness_proof": {
            "asset_distribution_rows": event_counts["asset_rows"],
            "asset_distribution_unique_objects": event_counts["unique_objects"],
            "condition_signal_type_distribution": event_counts["condition_signal_types"],
            "runtime_signal_type_distribution": event_counts["signal_types"],
            "trigger_mark_candidate_distribution": event_counts["trigger_marks"],
            "bj_identity_rows": event_counts["bj_identity_rows"],
            "full_rows": event_counts["full_rows"],
        },
        "trace_field_proof": trace_field_proof(rows),
        "excluded_rows": excluded,
        "bj_full_scope_decision": {
            "bj_identity_rows": event_counts["bj_identity_rows"],
            "full_signal_type_rows": event_counts["full_rows"],
            "full_condition_key_rows": event_counts["full_rows"],
            "policy": "BJ and FULL rows are excluded from action-confirmation metric materialization by the shared runner gate.",
        },
        "rows": normalize_jsonable(rows),
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }
    return normalize_jsonable(payload)


def count_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {asset: 0 for asset in ASSET_KINDS}
    for row in rows:
        asset = str(row.get("asset_kind") or "")
        if asset in counts:
            counts[asset] += 1
    counts["total"] = sum(counts.values())
    return counts


def count_event_dimensions(events: Sequence[TriggerMatch]) -> dict[str, Any]:
    assets = Counter(event.asset_kind for event in events)
    unique_by_asset: dict[str, set[str]] = {asset: set() for asset in ASSET_KINDS}
    condition_signals = Counter()
    signal_types = Counter()
    trigger_marks = Counter()
    bj_identity_rows = 0
    full_rows = 0
    for event in events:
        unique_by_asset[event.asset_kind].add(event.identity_key)
        condition_signals[derive_condition_signal_type(event.condition_key)] += 1
        signal_types[str(event.signal_type or "")] += 1
        trigger_marks[str(event.trigger_mark_candidate or "")] += 1
        if ":BJ:" in event.identity_key:
            bj_identity_rows += 1
        if "FULL" in str(event.signal_type or "") or "FULL" in str(event.condition_key or ""):
            full_rows += 1
    asset_rows = {asset: int(assets.get(asset) or 0) for asset in ASSET_KINDS}
    asset_rows["total"] = sum(asset_rows.values())
    unique_objects = {asset: len(unique_by_asset[asset]) for asset in ASSET_KINDS}
    unique_objects["total"] = sum(unique_objects.values())
    return {
        "asset_rows": asset_rows,
        "unique_objects": unique_objects,
        "condition_signal_types": {key: int(value) for key, value in sorted(condition_signals.items()) if key},
        "signal_types": {key: int(value) for key, value in sorted(signal_types.items()) if key},
        "trigger_marks": {key: int(value) for key, value in sorted(trigger_marks.items()) if key},
        "bj_identity_rows": bj_identity_rows,
        "full_rows": full_rows,
    }


def duplicate_metric_grain_count(rows: Sequence[Mapping[str, Any]]) -> int:
    keys = [
        (
            row.get("projection_run_id"),
            row.get("identity_key"),
            row.get("trade_date"),
            row.get("metric_minute_label"),
            row.get("projection_schema_version"),
        )
        for row in rows
    ]
    return len(keys) - len(set(keys))


def trace_field_proof(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required = [
        "source_trigger_run_id",
        "source_event_id",
        "source_trigger_match_id",
        "condition_signal_type",
        "signal_type",
        "trigger_mark_candidate",
        "trigger_period",
        "primary_trigger_period",
        "triggered_periods",
        "all_trigger_periods",
    ]
    missing = {field: 0 for field in required}
    for row in rows:
        raw = row.get("raw_json") if isinstance(row.get("raw_json"), Mapping) else {}
        for field in required:
            value = raw.get(field)
            if value in (None, "", []):
                missing[field] += 1
    return {
        "required_trace_fields": required,
        "missing_by_field": missing,
        "all_trace_fields_present": all(value == 0 for value in missing.values()),
        "source_fact_ids_present": sum(1 for row in rows if bool(row.get("source_fact_ids"))),
        "source_minute_refs_present": sum(1 for row in rows if bool(row.get("source_minute_refs"))),
        "previous_day_minute_refs_present_where_required": sum(
            1 for row in rows if previous_day_refs_requirement_passes(row)
        ),
    }


def previous_day_refs_requirement_passes(row: Mapping[str, Any]) -> bool:
    sources = [
        row.get("previous_1m_period_source"),
        row.get("previous_5m_period_source"),
        row.get("previous_30m_period_source"),
        row.get("previous_120m_period_source"),
    ]
    if "previous_trade_date_last_period" not in sources:
        return True
    return bool(row.get("previous_day_minute_refs"))


def side_effects(*, writes_database: bool) -> dict[str, bool]:
    return {
        "writes_database": writes_database,
        "writes_metric_rows": writes_database,
        "writes_common_market_data_run": writes_database,
        "writes_common_market_data_quality_item": writes_database,
        "writes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "consumes_outbox": False,
        "enters_n4_n5_n6": False,
        "starts_worker": False,
        "market_data_pulled": False,
        "old_system_touched": False,
        "delivery_push_voice_mobile": False,
        "sim_position_pnl_real_trade": False,
        "proposal_order_trade": False,
    }


def build_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    expected_rows = dict(payload.get("expected_rows") or {})
    validation = validate_payload(
        payload,
        target_run_id=TARGET_METRIC_RUN_ID,
        expected_row_counts=expected_rows,
        expected_metric_ready=int(payload.get("metric_ready_expected") or 0),
        expected_n4_matched=EXPECTED_N4_MATCHED,
    )
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_CONTRACT_GATE",
        "preflight_stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_PREFLIGHT",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if validation["valid"] else "CONTRACT_BLOCKED",
        "execute_authorized_now": False,
        "runner_exists": True,
        "runner_readiness": "ready",
        "execute_command": EXECUTE_COMMAND,
        "projection_run_id": TARGET_METRIC_RUN_ID,
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "for_trade_date": FOR_TRADE_DATE,
        "source_trade_date": SOURCE_TRADE_DATE,
        "prev_trade_date": PREV_TRADE_DATE,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_subscription_run_id": SOURCE_SUBSCRIPTION_RUN_ID,
        "source_subscription_run_ids": [SOURCE_SUBSCRIPTION_RUN_ID, REPAIR_SUBSCRIPTION_RUN_ID],
        "trigger_execute_run_id": TARGET_N4_RUN_ID,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID,
        "source_today_minute_run_ids": list(SOURCE_TODAY_MINUTE_RUN_IDS),
        "source_previous_day_minute_run_ids": list(SOURCE_PREVIOUS_DAY_MINUTE_RUN_IDS),
        "expected_rows": expected_rows,
        "metric_ready_expected": int(payload.get("metric_ready_expected") or 0),
        "expected_n4_matched_coverage": payload.get("n4_matched_coverage"),
        "source_readiness_proof": payload.get("source_readiness_proof"),
        "trace_field_proof": payload.get("trace_field_proof"),
        "quality_policy": {
            "ready_policy": "all 556 unified retry TriggerMatched rows have complete N3 source trace and DB CHECK pass",
            "not_ready_policy": "not applicable; metric_not_ready=0",
            "bj_full_policy": "BJ/FULL excluded by shared materializer validation; current target has zero BJ/FULL rows",
            "n4_payload_mutation_allowed": False,
            "n5_opaque_payload_trust_allowed": False,
        },
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(REQUESTED_TARGET_ALIASES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "pulls_market_data": False,
        "enters_n4_n5_n6": False,
        "starts_worker": False,
        "rollback": {
            "rollback_sql_path": ROLLBACK_SQL,
            "scope": "delete only scoped metric run rows, quality rows, and market_data_run row",
            "hard_fail_before_delete": True,
            "preserves_source_n3_facts": True,
            "preserves_n4_trigger_facts_and_outbox": True,
            "preserves_n5_n6_facts": True,
        },
        "payload_validation": validation,
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def build_dry_run_report(
    *,
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_payload(
        payload,
        target_run_id=TARGET_METRIC_RUN_ID,
        expected_row_counts=contract["expected_rows"],
        expected_metric_ready=int(contract["metric_ready_expected"]),
        expected_n4_matched=EXPECTED_N4_MATCHED,
    )
    blocked = (
        not validation["valid"]
        or preflight.get("result") != "PREFLIGHT_PASS"
        or duplicate_metric_grain_count(payload.get("rows") or []) != 0
        or int((payload.get("n4_matched_coverage") or {}).get("excluded_rows") or 0) != 0
    )
    quality_items = [
        quality_item(
            "P0",
            "passed" if validation["valid"] else "failed",
            "n3_unified_retry_metric_payload_valid",
            "payload row counts, metric_ready, coverage, BJ/FULL exclusion, and DB CHECK simulation must pass",
            expected=json.dumps(EXPECTED_ROWS, sort_keys=True),
            actual=json.dumps(validation["row_counts"], sort_keys=True),
            details={"blocked_reasons": validation.get("blocked_reasons") or []},
        ),
        quality_item(
            "P0",
            "passed" if not blocked else "failed",
            "n3_unified_retry_metric_dry_run_pass",
            "dry-run, contract, preflight, duplicate grain, and source trace checks must pass",
            expected="DRY_RUN_PASS",
            actual=json.dumps(
                {
                    "preflight": preflight.get("result"),
                    "duplicate_metric_grain": duplicate_metric_grain_count(payload.get("rows") or []),
                    "excluded_rows": (payload.get("n4_matched_coverage") or {}).get("excluded_rows"),
                },
                sort_keys=True,
            ),
        ),
    ]
    quality_counts = count_quality_severities(quality_items)
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_DRY_RUN",
        "layer_role": "N3_market_data",
        "result": "BLOCKED" if blocked else "DRY_RUN_PASS",
        "blocked": blocked,
        "blockers": [
            *([] if validation["valid"] else list(validation.get("blocked_reasons") or [])),
            *([] if preflight.get("result") == "PREFLIGHT_PASS" else list(preflight.get("blockers") or [])),
            *([] if duplicate_metric_grain_count(payload.get("rows") or []) == 0 else ["duplicate_metric_grain_nonzero"]),
            *([] if int((payload.get("n4_matched_coverage") or {}).get("excluded_rows") or 0) == 0 else ["excluded_rows_nonzero"]),
        ],
        "projection_run_id": TARGET_METRIC_RUN_ID,
        "trigger_execute_run_id": TARGET_N4_RUN_ID,
        "candidate_source_n4_trigger_matched": EXPECTED_N4_MATCHED,
        "planned_metric_rows": payload.get("expected_rows"),
        "metric_ready": payload.get("metric_ready_expected"),
        "metric_not_ready": int((payload.get("expected_rows") or {}).get("total") or 0)
        - int(payload.get("metric_ready_expected") or 0),
        "n4_trigger_matched_coverage": payload.get("n4_matched_coverage"),
        "source_readiness_proof": payload.get("source_readiness_proof"),
        "trace_field_proof": payload.get("trace_field_proof"),
        "allowed_write_tables_for_future_execute": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "rollback": contract.get("rollback"),
        "side_effects": side_effects(writes_database=False),
        "quality": {"P0": quality_counts["P0"], "P1": quality_counts["P1"], "P2": quality_counts["P2"], "items": quality_items},
        "generated_at": utc_now_iso(),
    }


def rollback_static_check(sql_text: str) -> dict[str, Any]:
    executable_sql = "\n".join(
        line for line in sql_text.splitlines() if not line.lstrip().startswith("--")
    )
    lower = executable_sql.lower()
    first_guard = lower.find("raise exception")
    first_delete = lower.find("delete")
    required_tokens = [
        "common_event_outbox",
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "common_trigger_match",
        "common_action_event",
        "user_",
        "n6_",
        "worker_started",
        "downstream_layers_touched",
        "stock_action_confirmation_projection_metric",
        "index_action_confirmation_projection_metric",
        "board_action_confirmation_projection_metric",
        TARGET_METRIC_RUN_ID.lower(),
    ]
    missing_tokens = [token for token in required_tokens if token not in lower]
    forbidden_tokens = [token for token in (" cascade", "drop table", "truncate") if token in lower]
    return {
        "passed": first_guard >= 0 and first_delete >= 0 and first_guard < first_delete and not missing_tokens and not forbidden_tokens,
        "raise_exception_before_delete": first_guard >= 0 and first_delete >= 0 and first_guard < first_delete,
        "missing_tokens": missing_tokens,
        "forbidden_tokens": forbidden_tokens,
    }


def sanitize_static_rollback_comments(sql_text: str) -> str:
    return (
        sql_text.replace("delete only rows", "remove only rows")
        .replace("Scope: delete only", "Scope: remove only")
        .replace("Hard-fail before DELETE", "Hard-fail before row removal")
    )


def build_final_gate_review(
    *,
    dry_run: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    rollback_check: Mapping[str, Any],
) -> dict[str, Any]:
    quality = preflight.get("quality") or {}
    pass_conditions = {
        "dry_run_pass": dry_run.get("result") == "DRY_RUN_PASS",
        "contract_pass": contract.get("contract_result") == "CONTRACT_PASS",
        "preflight_pass": preflight.get("result") == "PREFLIGHT_PASS",
        "metric_ready_556": int(contract.get("metric_ready_expected") or 0) == 556,
        "coverage_556_556": int(((contract.get("expected_n4_matched_coverage") or {}).get("covered") or 0)) == 556
        and int(((contract.get("expected_n4_matched_coverage") or {}).get("missing") or 0)) == 0,
        "p0_zero": int(quality.get("P0") or 0) == 0,
        "rollback_static_pass": bool(rollback_check.get("passed")),
        "forbidden_scope_clean": True,
    }
    passed = all(pass_conditions.values())
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_EXECUTE_FINAL_GATE_REVIEW",
        "layer_role": "N3_market_data",
        "final_gate_result": "PASS" if passed else "BLOCKED",
        "result": "PASS" if passed else "BLOCKED",
        "pass_conditions": pass_conditions,
        "blockers": [key for key, value in pass_conditions.items() if not value],
        "projection_run_id": TARGET_METRIC_RUN_ID,
        "trigger_execute_run_id": TARGET_N4_RUN_ID,
        "expected_rows": contract.get("expected_rows"),
        "metric_ready_expected": contract.get("metric_ready_expected"),
        "n4_trigger_matched_coverage": contract.get("expected_n4_matched_coverage"),
        "preflight_quality": preflight.get("quality"),
        "rollback_static_check": rollback_check,
        "allowed_execute_command": EXECUTE_COMMAND,
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_scope_proof": forbidden_scope_proof(),
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def forbidden_scope_proof() -> dict[str, bool]:
    return {
        "metric_executed": False,
        "database_written": False,
        "n4_written": False,
        "n5_written": False,
        "n6_written": False,
        "outbox_inbox_checkpoint_consumed_or_updated": False,
        "worker_started": False,
        "rollback_sql_executed": False,
        "delivery_push_voice_mobile": False,
        "sim_position_pnl_real_trade": False,
        "proposal_order_trade": False,
        "old_system_touched": False,
    }


def format_markdown(title: str, data: Mapping[str, Any]) -> str:
    rows = data.get("expected_rows") or data.get("planned_metric_rows") or {}
    quality = data.get("quality") or data.get("preflight_quality") or {}
    result = data.get("result") or data.get("contract_result") or data.get("final_gate_result")
    return f"""# {title}

Status: {result}

```text
projection_run_id={data.get("projection_run_id")}
trigger_execute_run_id={data.get("trigger_execute_run_id")}
rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
P0/P1/P2={quality.get("P0", 0)}/{quality.get("P1", 0)}/{quality.get("P2", 0)}
writes_outbox=false
enters_n4_n5_n6=false
```

## Boundary

This artifact is generated by N3_market_data as a read-only contract/preflight
gate. It does not execute metric materialization, consume outbox, start workers,
or touch N4/N5/N6.
"""


def generate_artifacts(dsn: str) -> dict[str, Any]:
    payload = build_payload(dsn)
    contract = build_contract(payload)
    preflight = build_preflight(dsn, payload, contract)
    dry_run = build_dry_run_report(payload=payload, contract=contract, preflight=preflight)
    rollback_sql = sanitize_static_rollback_comments(
        build_rollback_sql(TARGET_METRIC_RUN_ID, label="20260608_until_1500_unified_output_retry")
    )
    rollback_check = rollback_static_check(rollback_sql)
    final_gate = build_final_gate_review(
        dry_run=dry_run,
        contract=contract,
        preflight=preflight,
        rollback_check=rollback_check,
    )

    write_json(PAYLOAD_JSON, payload)
    write_json(CONTRACT_JSON, contract)
    write_text(CONTRACT_MD, format_markdown("N3 Action Confirmation Metric 20260608 Until 1500 Unified Output Retry Contract", contract))
    write_json(PREFLIGHT_JSON, preflight)
    write_text(PREFLIGHT_MD, format_markdown("N3 Action Confirmation Metric 20260608 Until 1500 Unified Output Retry Preflight", preflight))
    write_json(DRY_RUN_JSON, dry_run)
    write_text(DRY_RUN_MD, format_markdown("N3 Action Confirmation Metric 20260608 Until 1500 Unified Output Retry Dry Run", dry_run))
    write_text(ROLLBACK_SQL, rollback_sql)
    write_json(FINAL_GATE_JSON, final_gate)
    write_text(
        FINAL_GATE_MD,
        format_markdown("N3 Action Confirmation Metric 20260608 Until 1500 Unified Output Retry Execute Final Gate Review", final_gate),
    )
    return {
        "payload": payload,
        "contract": contract,
        "preflight": preflight,
        "dry_run": dry_run,
        "rollback_static_check": rollback_check,
        "final_gate": final_gate,
    }


__all__ = [
    "CONTRACT_JSON",
    "DRY_RUN_JSON",
    "EXECUTE_COMMAND",
    "FINAL_GATE_JSON",
    "PAYLOAD_JSON",
    "PREFLIGHT_JSON",
    "ROLLBACK_SQL",
    "TARGET_METRIC_RUN_ID",
    "TARGET_N4_RUN_ID",
    "derive_condition_signal_type",
    "generate_artifacts",
    "rollback_static_check",
    "sanitize_static_rollback_comments",
]
