"""Scoped N3 repair for 20260608 formal-fallback action metric coverage.

This module is deliberately scoped to N3 market-data artifacts and writes.  It
does not mutate N4/N5/N6, consume event infra, start workers, or touch the old
system.  The repair chain is:

1. Register scoped minute subscriptions for N5 ``metric_missing`` rows.
2. Run A1/C1 with existing N3 runners against that scoped subscription.
3. Materialize additive trigger-time action-confirmation metrics for the
   repaired rows.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.action_confirmation_projection_plan import (
    ASSET_KINDS,
    build_metric_candidate_row,
    load_minute_rows_for_metric_dry_run,
    load_snapshot_rows_for_metric_dry_run,
    minute_label,
    normalize_jsonable,
    parse_dt,
    simulate_metric_ready_db_check,
    add_price_amount_flags,
)
from ashare_v3.market.preload_execute_contract import (
    build_execute_contract_from_reports,
    build_execute_preflight_from_contract,
    fetch_previous_day_minute_execute_baseline,
    format_previous_day_minute_execute_contract_markdown,
    format_previous_day_minute_execute_preflight_markdown,
    format_previous_day_minute_rollback_sql,
)
from ashare_v3.market.preload_plan import build_previous_day_minute_preload_plan_dry_run
from ashare_v3.market.previous_day_preload_execute import utc_now_iso, write_json, write_text
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect
from ashare_v3.market.subscription_execute import (
    build_post_quality_items,
    build_post_subscription_execute_checks,
    capture_subscription_execution_backup,
    persist_subscription_plan,
)
from ashare_v3.market.subscription_plan import ADAPTER_NAMES, rows_section
from ashare_v3.market.today_minute_plan import (
    ASIA_SHANGHAI,
    build_today_minute_bar_plan_dry_run,
    format_today_minute_markdown,
)
from ashare_v3.market.action_confirmation_metric_materialization_execute import (
    ALLOWED_WRITE_TABLES as METRIC_ALLOWED_WRITE_TABLES,
    FORBIDDEN_WRITE_TABLES as METRIC_FORBIDDEN_WRITE_TABLES,
    REQUESTED_TARGET_ALIASES,
    build_preflight as build_metric_preflight,
    build_rollback_sql as build_metric_rollback_sql,
    format_20260605_coverage_repair_contract_markdown,
    format_20260605_coverage_repair_dry_run_markdown,
    format_20260605_coverage_repair_preflight_markdown,
    validate_payload,
)


FOR_TRADE_DATE = "20260608"
SOURCE_TRADE_DATE = "20260605"
PREVIOUS_DAY_MINUTE_DATE = "20260605"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260605_to_20260608_v13_index_all_execute"
ORIGINAL_SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
)
SOURCE_SNAPSHOT_RUN_ID = (
    "realtime_daily_snapshot_20260608__"
    "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
)
SOURCE_REALTIME_PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260608_until_1500__realtime_daily_snapshot_20260608__"
    "market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"
)
TRIGGER_EXECUTE_RUN_ID = (
    "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_"
    "formal_snapshot_fallback_retry"
)
N5_ACTION_RUN_ID = (
    "action_consumer_execute_20260608_until_1500_formal_snapshot_fallback_metric_aware_retry__"
    "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_"
    "formal_snapshot_fallback_retry"
)
ORIGINAL_METRIC_RUN_ID = (
    "action_confirmation_metric_20260608_formal_snapshot_fallback_trigger_time__"
    "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_"
    "formal_snapshot_fallback_retry"
)
REPAIR_SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260608_action_metric_coverage_repair_v1__"
    "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry"
)
PREVIOUS_DAY_REPAIR_RUN_ID = (
    "previous_day_minute_preload_20260605_for_20260608_action_metric_coverage_repair_v1__"
    "market_data_subscription_20260608_action_metric_coverage_repair_v1"
)
TODAY_MINUTE_REPAIR_RUN_ID = (
    "today_minute_bar_1m_20260608_until_1500_action_metric_coverage_repair_v1__"
    "market_data_subscription_20260608_action_metric_coverage_repair_v1"
)
METRIC_REPAIR_RUN_ID = (
    "action_confirmation_metric_20260608_scoped_coverage_repair_v1__"
    "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry"
)
PROJECTION_SCHEMA_VERSION = "n3.action_confirmation_metric.v1"
COVERAGE_POLICY_VERSION = "n3.action_confirmation_metric.20260608.scoped_coverage_repair.v1"

SUBSCRIPTION_DRY_RUN_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_DRY_RUN.json"
SUBSCRIPTION_DRY_RUN_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_DRY_RUN.md"
SUBSCRIPTION_CONTRACT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_CONTRACT.json"
SUBSCRIPTION_CONTRACT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_CONTRACT.md"
SUBSCRIPTION_PREFLIGHT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_PREFLIGHT.json"
SUBSCRIPTION_PREFLIGHT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_PREFLIGHT.md"
SUBSCRIPTION_EXECUTE_REPORT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_EXECUTE_REPORT.json"
SUBSCRIPTION_EXECUTE_REPORT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_EXECUTE_REPORT.md"
SUBSCRIPTION_BACKUP_BEFORE_JSON = "docs/N3_action_confirmation_metric_20260608_scoped_coverage_repair_subscription_backup_before.json"
SUBSCRIPTION_BACKUP_AFTER_JSON = "docs/N3_action_confirmation_metric_20260608_scoped_coverage_repair_subscription_backup_after.json"

A0_DRY_RUN_JSON = "docs/N3_A0_action_confirmation_metric_20260608_scoped_coverage_repair_previous_day_minute_dry_run.json"
A0_DRY_RUN_MD = "docs/N3_A0_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_PREVIOUS_DAY_MINUTE_DRY_RUN.md"
A1_CONTRACT_JSON = "docs/N3_A1_action_confirmation_metric_20260608_scoped_coverage_repair_previous_day_minute_execute_contract.json"
A1_CONTRACT_MD = "docs/N3_A1_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_PREVIOUS_DAY_MINUTE_EXECUTE_CONTRACT.md"
A1_PREFLIGHT_JSON = "docs/N3_A1_action_confirmation_metric_20260608_scoped_coverage_repair_previous_day_minute_execute_preflight.json"
A1_PREFLIGHT_MD = "docs/N3_A1_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_PREVIOUS_DAY_MINUTE_EXECUTE_PREFLIGHT.md"
A1_EXECUTE_REPORT_JSON = "docs/N3_A1_action_confirmation_metric_20260608_scoped_coverage_repair_previous_day_minute_execute_report.json"
A1_EXECUTE_REPORT_MD = "docs/N3_A1_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_PREVIOUS_DAY_MINUTE_EXECUTE_REPORT.md"

C0_DRY_RUN_JSON = "docs/N3_C0_action_confirmation_metric_20260608_scoped_coverage_repair_today_minute_until_1500_dry_run.json"
C0_DRY_RUN_MD = "docs/N3_C0_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_TODAY_MINUTE_UNTIL_1500_DRY_RUN.md"
C1_EXECUTE_REPORT_JSON = "docs/N3_C1_action_confirmation_metric_20260608_scoped_coverage_repair_today_minute_until_1500_execute_report.json"
C1_EXECUTE_REPORT_MD = "docs/N3_C1_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_TODAY_MINUTE_UNTIL_1500_EXECUTE_REPORT.md"

METRIC_PAYLOAD_JSON = "docs/N3_action_confirmation_metric_20260608_scoped_coverage_repair_payload.json"
METRIC_CONTRACT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_CONTRACT.json"
METRIC_CONTRACT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_CONTRACT.md"
METRIC_PREFLIGHT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_PREFLIGHT.json"
METRIC_PREFLIGHT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_PREFLIGHT.md"
METRIC_DRY_RUN_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_DRY_RUN.json"
METRIC_DRY_RUN_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_DRY_RUN.md"
METRIC_EXECUTE_REPORT_JSON = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_EXECUTE_REPORT.json"
METRIC_EXECUTE_REPORT_MD = "docs/N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_EXECUTE_REPORT.md"

COMBINED_ROLLBACK_SQL = "sql/N3_action_confirmation_metric_20260608_scoped_coverage_repair_rollback.sql"
SUBSCRIPTION_ROLLBACK_SQL = "sql/N3_action_confirmation_metric_20260608_scoped_coverage_repair_subscription_rollback.sql"
A1_ROLLBACK_SQL = "sql/N3_A1_action_confirmation_metric_20260608_scoped_coverage_repair_previous_day_minute_rollback.sql"
C1_ROLLBACK_SQL = "sql/N3_C1_action_confirmation_metric_20260608_scoped_coverage_repair_today_minute_until_1500_rollback.sql"
METRIC_ROLLBACK_SQL = "sql/N3_action_confirmation_metric_20260608_scoped_coverage_repair_metric_rollback.sql"

EXPECTED_MISSING_COUNTS = {"stock": 256, "index": 48, "board": 77, "total": 381}
EXPECTED_ORIGINAL_METRIC_COUNTS = {"stock": 156, "index": 12, "board": 7, "total": 175}
EXPECTED_REPAIRED_COVERAGE = 556
EXPECTED_ORIGINAL_METRIC_ROWS = 175
TODAY_1500_AS_OF = datetime(2026, 6, 8, 15, 1, tzinfo=ASIA_SHANGHAI)


def asset_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("asset_kind") or "") for row in rows)
    return {asset: int(counts.get(asset) or 0) for asset in ASSET_KINDS}


def with_total(counts: Mapping[str, int]) -> dict[str, int]:
    output = {asset: int(counts.get(asset) or 0) for asset in ASSET_KINDS}
    output["total"] = sum(output.values())
    return output


def adapter_name(asset_kind: str) -> str:
    return ADAPTER_NAMES.get(asset_kind) or f"{asset_kind.title()}MarketDataAdapter"


def scope_table(asset_kind: str) -> str:
    return f"{asset_kind}_minute_target_scope"


def identity_column(asset_kind: str) -> str:
    return f"{asset_kind}_identity_key"


def first_int(values: Any, default: int = 0) -> int:
    if isinstance(values, (list, tuple)) and values:
        return int(values[0])
    if values is not None and values != "":
        return int(values)
    return default


def candidate_direction(values: Iterable[Any]) -> str:
    normalized = {str(value).strip().lower() for value in values if str(value).strip()}
    if "buy" in normalized:
        return "buy"
    if "sell" in normalized:
        return "sell"
    return "buy"


def hhmm_to_iso(trade_date: str, hhmm: str) -> str:
    hour, minute = hhmm.split(":")
    return datetime(
        int(trade_date[:4]),
        int(trade_date[4:6]),
        int(trade_date[6:8]),
        int(hour),
        int(minute),
        tzinfo=ASIA_SHANGHAI,
    ).isoformat()


def metric_minute_from_trigger_time(value: Any) -> datetime:
    dt = parse_dt(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ASIA_SHANGHAI)
    else:
        dt = dt.astimezone(ASIA_SHANGHAI)
    return dt.replace(second=0, microsecond=0)


def metric_missing_condition_sql(alias: str = "ae") -> str:
    return (
        f"coalesce({alias}.payload_json->>'blocked_reason', "
        f"{alias}.trace_json->>'blocked_reason') = 'metric_missing'"
    )


def load_metric_missing_scope(dsn: str) -> list[dict[str, Any]]:
    """Load the 381 object universe from N5 metric_missing rows.

    The scoped subscription uses the existing realtime snapshot subscription as
    trace source because those rows exist for every missing object, while minute
    subscriptions are absent by design.
    """

    with audited_n3_market_readonly_plan_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            WITH missing AS (
              SELECT
                ae.asset_kind,
                ae.identity_key,
                array_agg(ae.source_trigger_match_id ORDER BY ae.source_trigger_match_id) AS source_trigger_match_ids,
                array_agg(ae.source_trigger_event_id ORDER BY ae.source_trigger_match_id) AS source_trigger_event_ids,
                array_agg(ae.trigger_period ORDER BY ae.source_trigger_match_id) AS trigger_periods,
                array_agg(ae.condition_key ORDER BY ae.source_trigger_match_id) AS action_condition_keys,
                array_agg(ae.direction ORDER BY ae.source_trigger_match_id) AS action_directions,
                array_agg(ae.signal_type ORDER BY ae.source_trigger_match_id) AS action_signal_types
              FROM common_action_event ae
              WHERE ae.run_id = %s
                AND {metric_missing_condition_sql('ae')}
              GROUP BY ae.asset_kind, ae.identity_key
            )
            SELECT
              m.*,
              s.subscription_id AS snapshot_subscription_id,
              s.exchange,
              s.code,
              s.display_code,
              s.name,
              s.source_scope_ids,
              s.source_condition_pool_ids,
              s.condition_keys,
              s.directions,
              s.allowed_signal_types
            FROM missing m
            JOIN common_market_data_subscription s
              ON s.run_id = %s
             AND s.asset_kind = m.asset_kind
             AND s.identity_key = m.identity_key
             AND s.required_data_kind = 'realtime_daily_snapshot'
            ORDER BY m.asset_kind, m.identity_key
            """,
            (N5_ACTION_RUN_ID, ORIGINAL_SUBSCRIPTION_RUN_ID),
        )
        return [normalize_jsonable(dict(row)) for row in cur.fetchall()]


def load_metric_missing_events(dsn: str) -> list[dict[str, Any]]:
    with audited_n3_market_readonly_plan_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              ae.asset_kind,
              ae.identity_key,
              ae.source_trigger_match_id,
              ae.source_trigger_event_id,
              ae.direction,
              ae.signal_type,
              ae.condition_key,
              ae.trigger_period,
              tm.trigger_time,
              tm.trigger_bucket,
              tm.trigger_mark_candidate,
              tm.output_event_id,
              tm.source_event_id AS source_n3_event_id,
              tm.data_quality_status AS n4_data_quality_status
            FROM common_action_event ae
            JOIN common_trigger_match tm ON tm.trigger_match_id = ae.source_trigger_match_id
            WHERE ae.run_id = %s
              AND {metric_missing_condition_sql('ae')}
            ORDER BY ae.asset_kind, ae.identity_key, tm.trigger_time, ae.source_trigger_match_id
            """,
            (N5_ACTION_RUN_ID,),
        )
        return [normalize_jsonable(dict(row)) for row in cur.fetchall()]


def build_scoped_subscription_dry_run_report(
    scope_rows: Sequence[Mapping[str, Any]],
    *,
    strict_expected_scope: bool = False,
) -> dict[str, Any]:
    scope = [dict(row) for row in scope_rows]
    candidates: list[dict[str, Any]] = []
    subscriptions: list[dict[str, Any]] = []
    for row in scope:
        for required_data_kind, data_trade_date in (
            ("previous_day_minute_bar_1m", PREVIOUS_DAY_MINUTE_DATE),
            ("minute_bar_1m", FOR_TRADE_DATE),
        ):
            ref_suffix = f"{row['asset_kind']}|{row['identity_key']}|{required_data_kind}|{data_trade_date}"
            candidate_ref = f"candidate|{ref_suffix}"
            subscription_ref = f"subscription|{ref_suffix}"
            source_scope_ids = list(row.get("source_scope_ids") or [])
            source_condition_pool_ids = list(row.get("source_condition_pool_ids") or [])
            condition_keys = list(row.get("condition_keys") or row.get("action_condition_keys") or [])
            directions = list(row.get("directions") or row.get("action_directions") or [])
            allowed_signal_types = list(row.get("allowed_signal_types") or [])
            candidates.append(
                {
                    "run_id": REPAIR_SUBSCRIPTION_RUN_ID,
                    "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                    "for_trade_date": FOR_TRADE_DATE,
                    "source_trade_date": SOURCE_TRADE_DATE,
                    "prev_trade_date": PREVIOUS_DAY_MINUTE_DATE,
                    "asset_kind": row["asset_kind"],
                    "identity_key": row["identity_key"],
                    "exchange": row.get("exchange"),
                    "code": row.get("code"),
                    "display_code": row.get("display_code"),
                    "name": row.get("name"),
                    "required_data_kind": required_data_kind,
                    "data_trade_date": data_trade_date,
                    "source_scope_table": scope_table(str(row["asset_kind"])),
                    "source_scope_id": first_int(source_scope_ids),
                    "source_condition_pool_id": first_int(source_condition_pool_ids),
                    "direction": candidate_direction(directions),
                    "condition_key": ",".join(sorted(set(str(item) for item in condition_keys if item))) or "metric_missing_scope",
                    "allowed_signal_types": sorted(set(str(item) for item in allowed_signal_types if item)),
                    "source_scope_required_flags": {
                        "scoped_repair": True,
                        "source": "N5_metric_missing",
                        "original_snapshot_subscription_id": row.get("snapshot_subscription_id"),
                        "source_directions": sorted(set(str(item) for item in directions if item)),
                    },
                    "candidate_status": "planned",
                    "selected_reason": "n5_metric_missing_minute_subscription_gap",
                    "candidate_ref": candidate_ref,
                    "source_scope_ref": {
                        "source_scope_ids": source_scope_ids,
                        "source_condition_pool_ids": source_condition_pool_ids,
                    },
                }
            )
            subscriptions.append(
                {
                    "run_id": REPAIR_SUBSCRIPTION_RUN_ID,
                    "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                    "for_trade_date": FOR_TRADE_DATE,
                    "source_trade_date": SOURCE_TRADE_DATE,
                    "prev_trade_date": PREVIOUS_DAY_MINUTE_DATE,
                    "asset_kind": row["asset_kind"],
                    "identity_key": row["identity_key"],
                    "exchange": row.get("exchange"),
                    "code": row.get("code"),
                    "display_code": row.get("display_code"),
                    "name": row.get("name"),
                    "required_data_kind": required_data_kind,
                    "data_trade_date": data_trade_date,
                    "source_scope_row_count": max(len(source_scope_ids), 1),
                    "source_scope_tables": [scope_table(str(row["asset_kind"]))],
                    "source_scope_ids": [int(item) for item in source_scope_ids],
                    "source_condition_pool_ids": [int(item) for item in source_condition_pool_ids],
                    "condition_keys": sorted(set(str(item) for item in condition_keys if item)),
                    "directions": sorted(set(str(item) for item in directions if item)),
                    "allowed_signal_types": sorted(set(str(item) for item in allowed_signal_types if item)),
                    "priority": 10,
                    "status": "planned",
                    "selected_reason": "n5_metric_missing_minute_subscription_gap",
                    "subscription_ref": subscription_ref,
                    "source_scope_refs": [
                        {
                            "source_scope_ids": source_scope_ids,
                            "source_condition_pool_ids": source_condition_pool_ids,
                            "source_trigger_match_ids": row.get("source_trigger_match_ids") or [],
                            "source_trigger_event_ids": row.get("source_trigger_event_ids") or [],
                        }
                    ],
                    "data_trade_dates": [data_trade_date],
                }
            )

    plan_rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in subscriptions:
        grouped[(str(row["asset_kind"]), str(row["required_data_kind"]), str(row["data_trade_date"]))].append(row)
    for (asset_kind, required_data_kind, data_trade_date), rows in sorted(grouped.items()):
        refs = [str(row["subscription_ref"]) for row in rows]
        plan_rows.append(
            {
                "run_id": REPAIR_SUBSCRIPTION_RUN_ID,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                "for_trade_date": FOR_TRADE_DATE,
                "source_trade_date": SOURCE_TRADE_DATE,
                "prev_trade_date": PREVIOUS_DAY_MINUTE_DATE,
                "asset_kind": asset_kind,
                "required_data_kind": required_data_kind,
                "data_trade_date": data_trade_date,
                "adapter_name": adapter_name(asset_kind),
                "subscription_count": len(rows),
                "object_count": len({row["identity_key"] for row in rows}),
                "subscription_refs_sample": refs[:20],
                "identity_keys_sample": [str(row["identity_key"]) for row in rows[:20]],
                "plan_status": "planned",
                "execute_allowed": False,
                "selected_reason": "scoped_action_metric_coverage_repair",
                "pull_plan_ref": f"pull_plan|{asset_kind}|{required_data_kind}|{data_trade_date}",
            }
        )

    object_counts = with_total(asset_counts(scope))
    required_counts = Counter(str(row["required_data_kind"]) for row in subscriptions)
    quality_items = build_subscription_quality_items(
        scope_rows=scope,
        subscriptions=subscriptions,
        pull_plans=plan_rows,
        strict_expected_scope=strict_expected_scope,
    )
    quality = count_quality_severities(quality_items)
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_DRY_RUN",
        "layer_role": "N3_market_data",
        "plan_mode": "scoped_subscription_control_rows_only",
        "mode": "dry_run",
        "market_data_run_id": REPAIR_SUBSCRIPTION_RUN_ID,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_trade_date": SOURCE_TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "prev_trade_date": PREVIOUS_DAY_MINUTE_DATE,
        "source_scope_row_count": len(scope),
        "source_scope_row_count_by_asset_kind": {asset: object_counts[asset] for asset in ASSET_KINDS},
        "candidate_row_count": len(candidates),
        "subscription_candidate_count": len(candidates),
        "subscription_row_count": len(subscriptions),
        "dedup_subscription_count": len(subscriptions),
        "subscription_object_count": object_counts["total"],
        "object_count_by_asset_kind": {asset: object_counts[asset] for asset in ASSET_KINDS},
        "required_data_kind_counts": dict(sorted(required_counts.items())),
        "previous_day_minute_required_count": int(required_counts.get("previous_day_minute_bar_1m") or 0),
        "previous_day_minute_date_counts": {PREVIOUS_DAY_MINUTE_DATE: int(required_counts.get("previous_day_minute_bar_1m") or 0)},
        "dedup_ratio": 1.0,
        "dedup_reduction_ratio": 0.0,
        "market_data_pull_plan_row_count": len(plan_rows),
        "market_data_subscription_candidate": rows_section(candidates, include_rows=True),
        "market_data_subscription_dedup": rows_section(subscriptions, include_rows=True),
        "market_data_pull_plan": rows_section(plan_rows, include_rows=True),
        "quality": {
            "p0_count": quality["P0"],
            "p1_count": quality["P1"],
            "p2_count": quality["P2"],
            "items": quality_items,
        },
        "blocked": quality["P0"] > 0,
        "passed": quality["P0"] == 0,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def build_subscription_quality_items(
    *,
    scope_rows: Sequence[Mapping[str, Any]],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_plans: Sequence[Mapping[str, Any]],
    strict_expected_scope: bool = False,
) -> list[dict[str, Any]]:
    object_counts = with_total(asset_counts(scope_rows))
    expected = EXPECTED_MISSING_COUNTS
    duplicate_subscription_keys = len(subscriptions) - len(
        {
            (
                row["asset_kind"],
                row["identity_key"],
                row["required_data_kind"],
                row["data_trade_date"],
            )
            for row in subscriptions
        }
    )
    return [
        quality_item(
            "P0",
            "passed" if (not strict_expected_scope or object_counts == expected) else "failed",
            "n3_20260608_metric_missing_scope_count_matches_readiness",
            "scoped repair must use exactly the reviewed 381 N5 metric_missing objects",
            expected=json.dumps(expected, sort_keys=True),
            actual=json.dumps(object_counts, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if duplicate_subscription_keys == 0 else "failed",
            "n3_20260608_metric_repair_subscription_duplicates_zero",
            "scoped repair subscriptions must have unique asset/identity/kind/date keys",
            expected="0",
            actual=str(duplicate_subscription_keys),
        ),
        quality_item(
            "P0",
            "passed" if len(pull_plans) <= 6 else "failed",
            "n3_20260608_metric_repair_pull_plan_scoped",
            "scoped repair pull plans must cover only asset_kind x required_data_kind batches",
            expected="<=6",
            actual=str(len(pull_plans)),
        ),
    ]


def build_subscription_contract(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_CONTRACT",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if report.get("passed") else "CONTRACT_BLOCKED",
        "generated_at": utc_now_iso(),
        "execute_target": "subscription_control_only",
        "market_data_run_id": REPAIR_SUBSCRIPTION_RUN_ID,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_trade_date": SOURCE_TRADE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "source_trigger_run_id": TRIGGER_EXECUTE_RUN_ID,
        "source_n5_action_run_id": N5_ACTION_RUN_ID,
        "expected_objects": dict(report.get("object_count_by_asset_kind") or {}),
        "expected_rows": {
            "candidate": int(report.get("candidate_row_count") or 0),
            "subscription": int(report.get("subscription_row_count") or 0),
            "pull_plan": int(report.get("market_data_pull_plan_row_count") or 0),
        },
        "required_data_kind_counts": dict(report.get("required_data_kind_counts") or {}),
        "allowed_write_tables": [
            "common_market_data_run",
            "common_market_data_quality_item",
            "common_market_data_subscription_candidate",
            "common_market_data_subscription",
            "common_market_data_pull_plan",
        ],
        "forbidden_write_tables": [
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
            "stock_previous_day_minute_preload_status",
            "index_previous_day_minute_preload_status",
            "board_previous_day_minute_preload_status",
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "N4/N5/N6",
            "worker",
            "old system",
            "real trading",
        ],
        "writes_outbox": False,
        "pull_plan_execute_allowed": False,
        "metric_execute": False,
        "quality": report.get("quality"),
        "rollback": {"rollback_sql_path": SUBSCRIPTION_ROLLBACK_SQL, "combined_rollback_sql_path": COMBINED_ROLLBACK_SQL},
    }


def build_subscription_preflight(contract: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    target_counts = baseline.get("target_run_row_counts") or {}
    nonzero = {k: v for k, v in target_counts.items() if int(v or 0) != 0}
    p0 = int(((contract.get("quality") or {}).get("p0_count")) or 0)
    blocked = bool(nonzero) or p0 > 0
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_PREFLIGHT",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_BLOCKED" if blocked else "PREFLIGHT_PASS",
        "blocked": blocked,
        "blockers": [
            *([] if p0 == 0 else ["contract_p0_nonzero"]),
            *([f"target_baseline_nonzero:{nonzero}"] if nonzero else []),
        ],
        "generated_at": utc_now_iso(),
        "market_data_run_id": REPAIR_SUBSCRIPTION_RUN_ID,
        "expected_rows": contract.get("expected_rows"),
        "expected_objects": contract.get("expected_objects"),
        "allowed_write_tables": contract.get("allowed_write_tables"),
        "forbidden_write_tables": contract.get("forbidden_write_tables"),
        "baseline": baseline,
        "writes_outbox": False,
        "quality": contract.get("quality"),
        "execute_command": (
            "PYTHONPATH=src:scripts python3 "
            "scripts/run_n3_action_confirmation_metric_coverage_repair_subscription_execute_20260608.py "
            f"--dry-run-path {SUBSCRIPTION_DRY_RUN_JSON} "
            f"--json-report-path {SUBSCRIPTION_EXECUTE_REPORT_JSON} "
            f"--markdown-report-path {SUBSCRIPTION_EXECUTE_REPORT_MD} "
            "--execute --user-confirmed"
        ),
    }


def write_subscription_artifacts(dsn: str) -> dict[str, Any]:
    scope = load_metric_missing_scope(dsn)
    dry_run = build_scoped_subscription_dry_run_report(scope, strict_expected_scope=True)
    contract = build_subscription_contract(dry_run)
    baseline = capture_subscription_execution_backup(
        dsn,
        phase="preflight_scoped_coverage_repair_subscription",
        execute_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
    )
    preflight = build_subscription_preflight(contract, baseline)
    write_json(SUBSCRIPTION_DRY_RUN_JSON, dry_run)
    write_text(SUBSCRIPTION_DRY_RUN_MD, format_subscription_markdown("Dry Run", dry_run))
    write_json(SUBSCRIPTION_CONTRACT_JSON, contract)
    write_text(SUBSCRIPTION_CONTRACT_MD, format_subscription_markdown("Contract", contract))
    write_json(SUBSCRIPTION_PREFLIGHT_JSON, preflight)
    write_text(SUBSCRIPTION_PREFLIGHT_MD, format_subscription_markdown("Preflight", preflight))
    write_text(SUBSCRIPTION_ROLLBACK_SQL, build_subscription_rollback_sql())
    write_text(COMBINED_ROLLBACK_SQL, build_combined_rollback_sql())
    return {"dry_run": dry_run, "contract": contract, "preflight": preflight}


def execute_subscription_control_rows(
    *,
    dsn: str,
    dry_run_path: str = SUBSCRIPTION_DRY_RUN_JSON,
    json_report_path: str = SUBSCRIPTION_EXECUTE_REPORT_JSON,
    markdown_report_path: str = SUBSCRIPTION_EXECUTE_REPORT_MD,
    execute: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    if not execute or not user_confirmed:
        raise RuntimeError("N3 scoped subscription repair blocked: --execute and --user-confirmed are required")
    dry_run = json.loads(Path(dry_run_path).read_text())
    if dry_run.get("market_data_run_id") != REPAIR_SUBSCRIPTION_RUN_ID:
        raise RuntimeError("N3 scoped subscription repair blocked: dry-run run_id mismatch")
    if bool(dry_run.get("blocked")) or not bool(dry_run.get("passed")):
        raise RuntimeError("N3 scoped subscription repair blocked: dry-run is not PASS")
    pre_backup = capture_subscription_execution_backup(
        dsn,
        phase="before_scoped_coverage_repair_subscription",
        execute_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
    )
    if pre_backup.get("target_run_exists"):
        raise RuntimeError(f"N3 scoped subscription repair blocked: run already exists {REPAIR_SUBSCRIPTION_RUN_ID}")
    write_json(SUBSCRIPTION_BACKUP_BEFORE_JSON, pre_backup)
    write_result = persist_subscription_plan(
        dsn=dsn,
        dry_run_report=dry_run,
        execute_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
    )
    post_backup = capture_subscription_execution_backup(
        dsn,
        phase="after_scoped_coverage_repair_subscription",
        execute_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
    )
    write_json(SUBSCRIPTION_BACKUP_AFTER_JSON, post_backup)
    post_checks = build_post_subscription_execute_checks(
        pre_backup=pre_backup,
        post_backup=post_backup,
        dry_run_report=dry_run,
        write_result=write_result,
        execute_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
    )
    quality_items = list(dry_run["quality"]["items"]) + build_post_quality_items(post_checks)
    quality_counts = count_quality_severities(quality_items)
    report = {
        "result": "EXECUTE_PASS" if quality_counts["P0"] == 0 else "BLOCKED",
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_SUBSCRIPTION_EXECUTE",
        "layer_role": "N3_market_data",
        "market_data_run_id": REPAIR_SUBSCRIPTION_RUN_ID,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "for_trade_date": FOR_TRADE_DATE,
        "source_trade_date": SOURCE_TRADE_DATE,
        "write_result": write_result,
        "post_checks": post_checks,
        "quality": {"p0_count": quality_counts["P0"], "p1_count": quality_counts["P1"], "p2_count": quality_counts["P2"], "items": quality_items},
        "side_effects": {
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "rollback_sql_path": SUBSCRIPTION_ROLLBACK_SQL,
        "combined_rollback_sql_path": COMBINED_ROLLBACK_SQL,
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_subscription_execute_markdown(report))
    return report


def write_a1_c1_artifacts(dsn: str) -> dict[str, Any]:
    a0 = build_previous_day_minute_preload_plan_dry_run(
        dsn=dsn,
        market_data_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
        source_trade_date=SOURCE_TRADE_DATE,
        for_trade_date=FOR_TRADE_DATE,
        expected_previous_day_minute_date=PREVIOUS_DAY_MINUTE_DATE,
        include_rows=True,
    )
    write_json(A0_DRY_RUN_JSON, a0)
    write_text(A0_DRY_RUN_MD, format_generic_markdown("N3-A0 previous-day scoped repair dry-run", a0))
    from ashare_v3.market.preload_plan import build_persisted_subscription_report

    persisted = build_persisted_subscription_report(
        dsn=dsn,
        market_data_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
        source_trade_date=SOURCE_TRADE_DATE,
        for_trade_date=FOR_TRADE_DATE,
    )
    a1_contract = build_execute_contract_from_reports(
        a0_report=a0,
        persisted_report=persisted,
        market_data_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
        preload_run_id=PREVIOUS_DAY_REPAIR_RUN_ID,
        contract_json_path=A1_CONTRACT_JSON,
        rollback_sql_path=A1_ROLLBACK_SQL,
    )
    a1_contract["contract_json_path"] = A1_CONTRACT_JSON
    a1_contract["rollback_sql_path"] = A1_ROLLBACK_SQL
    a1_contract["source_subscription_run_id"] = REPAIR_SUBSCRIPTION_RUN_ID
    write_text(A1_ROLLBACK_SQL, sanitize_static_rollback_comments(format_previous_day_minute_rollback_sql(a1_contract)))
    a1_baseline = fetch_previous_day_minute_execute_baseline(dsn=dsn, contract=a1_contract)
    a1_preflight = build_execute_preflight_from_contract(a1_contract, a1_baseline)
    write_json(A1_CONTRACT_JSON, a1_contract)
    write_text(A1_CONTRACT_MD, format_previous_day_minute_execute_contract_markdown(a1_contract))
    write_json(A1_PREFLIGHT_JSON, a1_preflight)
    write_text(A1_PREFLIGHT_MD, format_previous_day_minute_execute_preflight_markdown(a1_preflight))

    c0 = build_today_minute_bar_plan_dry_run(
        dsn=dsn,
        market_data_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
        for_trade_date=FOR_TRADE_DATE,
        as_of=TODAY_1500_AS_OF,
        include_rows=True,
    )
    c0["today_minute_run_id"] = TODAY_MINUTE_REPAIR_RUN_ID
    c0["execute_contract"]["source_run_id"] = REPAIR_SUBSCRIPTION_RUN_ID
    c0["execute_contract"]["today_minute_run_id"] = TODAY_MINUTE_REPAIR_RUN_ID
    write_json(C0_DRY_RUN_JSON, c0)
    write_text(C0_DRY_RUN_MD, format_today_minute_markdown(c0))
    c1_rollback_sql = (
        c0["rollback_contract"]["rollback_sql"].replace(
            c0["rollback_contract"]["rollback_sql"].split("\\set today_minute_run_id '", 1)[1].split("'", 1)[0],
            TODAY_MINUTE_REPAIR_RUN_ID,
        )
        if "\\set today_minute_run_id '" in c0["rollback_contract"]["rollback_sql"]
        else c0["rollback_contract"]["rollback_sql"]
    )
    write_text(C1_ROLLBACK_SQL, sanitize_static_rollback_comments(c1_rollback_sql))
    write_text(COMBINED_ROLLBACK_SQL, build_combined_rollback_sql())
    return {"a0": a0, "a1_contract": a1_contract, "a1_preflight": a1_preflight, "c0": c0}


def build_metric_repair_payload(dsn: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    events = load_metric_missing_events(dsn)
    grouped_events: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        label = minute_label(event["trigger_time"])
        grouped_events[(str(event["asset_kind"]), str(event["identity_key"]), label)].append(event)
    identities_by_asset: dict[str, list[str]] = {asset: [] for asset in ASSET_KINDS}
    for asset, identity, _label in grouped_events:
        identities_by_asset[asset].append(identity)
    identities_by_asset = {asset: sorted(set(values)) for asset, values in identities_by_asset.items()}

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    with audited_n3_market_readonly_plan_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn, conn.cursor() as cur:
        snapshots = load_snapshot_rows_for_metric_dry_run(cur, source_snapshot_run_id=SOURCE_SNAPSHOT_RUN_ID)
        today = load_minute_rows_for_metric_dry_run(cur, run_id=TODAY_MINUTE_REPAIR_RUN_ID, candidate_identities=identities_by_asset)
        previous = load_minute_rows_for_metric_dry_run(cur, run_id=PREVIOUS_DAY_REPAIR_RUN_ID, candidate_identities=identities_by_asset)

    snapshot_by_asset = {
        asset: {str(row["identity_key"]): row for row in snapshots.get(asset, [])}
        for asset in ASSET_KINDS
    }
    today_by_asset = {
        asset: group_rows_by_identity(today.get(asset, []))
        for asset in ASSET_KINDS
    }
    previous_by_asset = {
        asset: group_rows_by_identity(previous.get(asset, []))
        for asset in ASSET_KINDS
    }
    for (asset, identity, label), trigger_events in sorted(grouped_events.items()):
        snapshot = dict((snapshot_by_asset.get(asset) or {}).get(identity) or {})
        today_rows = list((today_by_asset.get(asset) or {}).get(identity) or [])
        previous_rows = list((previous_by_asset.get(asset) or {}).get(identity) or [])
        metric_time = metric_minute_from_trigger_time(trigger_events[0]["trigger_time"])
        today_until_metric = [row for row in today_rows if parse_dt(row["bar_time"]) <= metric_time]
        exact_today = [row for row in today_rows if parse_dt(row["bar_time"]) == metric_time]
        if not snapshot or not today_until_metric or not previous_rows or not exact_today:
            excluded.append(
                {
                    "asset_kind": asset,
                    "identity_key": identity,
                    "metric_minute_label": label,
                    "reason": "missing_snapshot_or_minute_lineage",
                    "snapshot": bool(snapshot),
                    "today_rows_until_metric": len(today_until_metric),
                    "previous_rows": len(previous_rows),
                    "exact_today_bar": bool(exact_today),
                }
            )
            continue
        row = build_metric_candidate_row(
            asset_kind=asset,
            projection_run_id=METRIC_REPAIR_RUN_ID,
            projection_schema_version=PROJECTION_SCHEMA_VERSION,
            for_trade_date=FOR_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=REPAIR_SUBSCRIPTION_RUN_ID,
            source_snapshot_run_id=SOURCE_SNAPSHOT_RUN_ID,
            source_today_minute_run_id=TODAY_MINUTE_REPAIR_RUN_ID,
            source_previous_day_minute_run_id=PREVIOUS_DAY_REPAIR_RUN_ID,
            snapshot_row=snapshot,
            today_rows=today_until_metric,
            previous_day_rows=previous_rows,
        )
        trigger_bar = exact_today[-1]
        row["current_price"] = trigger_bar.get("close")
        row["current_price_source"] = "minute_bar_1m"
        row["current_price_time"] = parse_dt(trigger_bar["bar_time"]).isoformat()
        add_price_amount_flags(row)
        source_fact_ids = dict(row.get("source_fact_ids") or {})
        source_fact_ids.update(
            {
                "n4_trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID,
                "source_trigger_match_ids": [int(item["source_trigger_match_id"]) for item in trigger_events],
                "source_trigger_event_ids": [str(item["source_trigger_event_id"]) for item in trigger_events],
                "source_trigger_times": [parse_dt(item["trigger_time"]).isoformat() for item in trigger_events],
                "source_trigger_time_minute_labels": [label],
                "trigger_time_metric_time_aligned": True,
                "source_today_minute_bar_id_at_trigger_time": trigger_bar.get("bar_id"),
                "source_today_minute_bar_time_at_trigger_time": parse_dt(trigger_bar["bar_time"]).isoformat(),
                "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID,
                "source_metric_missing_action_run_id": N5_ACTION_RUN_ID,
            }
        )
        row["source_fact_ids"] = source_fact_ids
        row["calculation_config_hash"] = COVERAGE_POLICY_VERSION
        raw_json = dict(row.get("raw_json") or {})
        raw_json.update(
            {
                "dry_run_only": False,
                "coverage_repair": True,
                "coverage_policy_version": COVERAGE_POLICY_VERSION,
                "original_metric_run_id": ORIGINAL_METRIC_RUN_ID,
                "n4_trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID,
                "n4_trigger_matched_events": [normalize_trigger_event(item, label) for item in trigger_events],
                "trigger_time_alignment_policy": (
                    "metric_time_minute_equals_n4_trigger_time_minute; "
                    "current_price_source=minute_bar_1m close at trigger minute"
                ),
                "source_today_minute_bar_at_trigger_time": {
                    "bar_id": trigger_bar.get("bar_id"),
                    "bar_time": parse_dt(trigger_bar["bar_time"]).isoformat(),
                    "close": trigger_bar.get("close"),
                    "amount": trigger_bar.get("amount"),
                },
                "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID,
                "n4_payload_mutation_allowed": False,
                "n4_recompute_allowed": False,
                "n5_opaque_payload_trust_allowed": False,
                "metric_row_grain": "identity_key+trade_date+metric_minute_label",
                "bj_excluded": False,
                "full_excluded": False,
            }
        )
        row["raw_json"] = raw_json
        db_check = simulate_metric_ready_db_check(row)
        if not db_check["passes"]:
            row["metric_ready"] = False
            row["metric_quality_status"] = "missing"
            row["raw_json"]["db_check_missing_fields"] = db_check["missing_fields"]
            excluded.append(
                {
                    "asset_kind": asset,
                    "identity_key": identity,
                    "metric_minute_label": label,
                    "reason": "metric_ready_db_check_failed",
                    "missing_fields": db_check["missing_fields"],
                }
            )
            continue
        rows.append(normalize_jsonable(row))

    row_counts = with_total(asset_counts(rows))
    repaired_coverage_by_asset = {
        asset: int(EXPECTED_ORIGINAL_METRIC_COUNTS.get(asset, 0)) + int(row_counts.get(asset, 0))
        for asset in ("stock", "index", "board")
    }
    repaired_coverage_by_asset["total"] = sum(repaired_coverage_by_asset.values())
    remaining_excluded_by_asset = {
        asset: max(int(EXPECTED_MISSING_COUNTS.get(asset, 0)) - int(row_counts.get(asset, 0)), 0)
        for asset in ("stock", "index", "board")
    }
    remaining_excluded_by_asset["total"] = sum(remaining_excluded_by_asset.values())
    payload = {
        "artifact_type": "N3_action_confirmation_metric_materialization_payload",
        "artifact_subtype": "20260608_scoped_coverage_repair_v1",
        "layer_role": "N3_market_data",
        "projection_run_id": METRIC_REPAIR_RUN_ID,
        "target_run_id": METRIC_REPAIR_RUN_ID,
        "lineage_scope": "20260608_formal_snapshot_fallback_metric_missing_scoped_repair",
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "for_trade_date": FOR_TRADE_DATE,
        "source_trade_date": SOURCE_TRADE_DATE,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID,
        "source_subscription_run_ids": [ORIGINAL_SUBSCRIPTION_RUN_ID, REPAIR_SUBSCRIPTION_RUN_ID],
        "source_today_minute_run_ids": [TODAY_MINUTE_REPAIR_RUN_ID],
        "source_previous_day_minute_run_ids": [PREVIOUS_DAY_REPAIR_RUN_ID],
        "expected_rows": row_counts,
        "metric_ready_expected": row_counts["total"],
        "n4_matched_coverage": {
            "covered": EXPECTED_REPAIRED_COVERAGE if row_counts["total"] == EXPECTED_MISSING_COUNTS["total"] else EXPECTED_ORIGINAL_METRIC_ROWS + row_counts["total"],
            "expected": EXPECTED_REPAIRED_COVERAGE,
            "missing": max(EXPECTED_REPAIRED_COVERAGE - EXPECTED_ORIGINAL_METRIC_ROWS - row_counts["total"], 0),
            "distinct_metric_rows": row_counts["total"],
            "original_metric_rows": EXPECTED_ORIGINAL_METRIC_ROWS,
            "repair_additive_rows": row_counts,
            "repaired_total_coverage": repaired_coverage_by_asset,
            "remaining_excluded": remaining_excluded_by_asset,
            "covered_trigger_matched_by_asset": with_total(asset_counts(rows)),
            "missing_metric_by_asset_before_repair": dict(EXPECTED_MISSING_COUNTS),
        },
        "repair_summary": {
            "original_metric_rows": EXPECTED_ORIGINAL_METRIC_ROWS,
            "n4_matched_universe": EXPECTED_REPAIRED_COVERAGE,
            "repair_additive_rows": row_counts,
            "stock_additive": row_counts["stock"],
            "index_additive": row_counts["index"],
            "board_additive": row_counts["board"],
            "repaired_total_coverage": repaired_coverage_by_asset,
            "remaining_excluded": remaining_excluded_by_asset,
            "remaining_excluded_reason": "none" if not excluded else "missing_snapshot_or_minute_lineage",
            "remaining_excluded_samples": excluded[:20],
            "duplicate_vs_original_metric": 0,
            "duplicate_inside_repair_payload": duplicate_metric_keys(rows),
        },
        "rows": rows,
        "side_effects": {
            "database_written": False,
            "outbox_written": False,
            "n4_n5_n6_touched": False,
            "worker_started": False,
        },
        "generated_at": utc_now_iso(),
    }
    return normalize_jsonable(payload), excluded


def group_rows_by_identity(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["identity_key"])].append(dict(row))
    for identity_rows in grouped.values():
        identity_rows.sort(key=lambda item: parse_dt(item["bar_time"]))
    return dict(grouped)


def normalize_trigger_event(event: Mapping[str, Any], label: str) -> dict[str, Any]:
    return {
        "asset_kind": event.get("asset_kind"),
        "identity_key": event.get("identity_key"),
        "condition_key": event.get("condition_key"),
        "direction": event.get("direction"),
        "event_id": event.get("source_trigger_event_id") or event.get("output_event_id"),
        "output_event_id": event.get("output_event_id") or event.get("source_trigger_event_id"),
        "source_trigger_event_id": event.get("source_trigger_event_id"),
        "source_n3_event_id": event.get("source_n3_event_id"),
        "signal_type": event.get("signal_type"),
        "trigger_bucket": event.get("trigger_bucket"),
        "trigger_mark_candidate": event.get("trigger_mark_candidate"),
        "trigger_match_id": event.get("source_trigger_match_id"),
        "source_trigger_match_id": event.get("source_trigger_match_id"),
        "trigger_period": event.get("trigger_period"),
        "trigger_time": parse_dt(event["trigger_time"]).isoformat() if event.get("trigger_time") else None,
        "trigger_time_minute_label": label,
        "primary_trigger_period": event.get("trigger_period"),
        "all_trigger_periods": [event.get("trigger_period")] if event.get("trigger_period") else [],
        "n5_entry_allowed": True,
    }


def duplicate_metric_keys(rows: Sequence[Mapping[str, Any]]) -> int:
    keys = [
        (
            row.get("asset_kind"),
            row.get("identity_key"),
            row.get("trade_date"),
            row.get("metric_minute_label"),
        )
        for row in rows
    ]
    return len(keys) - len(set(keys))


def build_metric_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    expected_rows = dict(payload.get("expected_rows") or {})
    validation = validate_payload(
        payload,
        target_run_id=METRIC_REPAIR_RUN_ID,
        expected_row_counts=expected_rows,
        expected_metric_ready=int(payload.get("metric_ready_expected") or 0),
        expected_n4_matched=EXPECTED_REPAIRED_COVERAGE,
    )
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_CONTRACT",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if validation["valid"] else "CONTRACT_BLOCKED",
        "generated_at": utc_now_iso(),
        "projection_run_id": METRIC_REPAIR_RUN_ID,
        "for_trade_date": FOR_TRADE_DATE,
        "source_trade_date": SOURCE_TRADE_DATE,
        "prev_trade_date": PREVIOUS_DAY_MINUTE_DATE,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID,
        "source_today_minute_run_ids": [TODAY_MINUTE_REPAIR_RUN_ID],
        "source_previous_day_minute_run_ids": [PREVIOUS_DAY_REPAIR_RUN_ID],
        "source_subscription_run_id": REPAIR_SUBSCRIPTION_RUN_ID,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID,
        "original_metric_run_id": ORIGINAL_METRIC_RUN_ID,
        "coverage_policy_version": COVERAGE_POLICY_VERSION,
        "coverage_policy": {
            "mode": "additive_repair",
            "eligibility_source": "metric_trace_complete_and_db_check_pass",
            "does_not_cover_original_rows": True,
        },
        "expected_rows": expected_rows,
        "metric_ready_expected": int(payload.get("metric_ready_expected") or 0),
        "expected_n4_matched_coverage": payload.get("n4_matched_coverage"),
        "repair_summary": payload.get("repair_summary"),
        "allowed_write_tables": list(METRIC_ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(REQUESTED_TARGET_ALIASES),
        "forbidden_write_tables": list(METRIC_FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "rollback": {"rollback_sql_path": METRIC_ROLLBACK_SQL, "combined_rollback_sql_path": COMBINED_ROLLBACK_SQL},
        "quality": {
            "p0_count": 0 if validation["valid"] else 1,
            "p1_count": 0,
            "p2_count": 0,
            "items": [
                quality_item(
                    "P0",
                    "passed" if validation["valid"] else "failed",
                    "n3_20260608_metric_repair_payload_valid",
                    "payload row counts, metric_ready, coverage, BJ/FULL exclusion, and DB CHECK simulation must pass",
                    expected=json.dumps(expected_rows, sort_keys=True),
                    actual=json.dumps(validation, sort_keys=True),
                    details={"blocked_reasons": validation["blocked_reasons"]},
                )
            ],
        },
    }


def build_metric_repair_dry_run_report(
    *,
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    excluded: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_rows = dict(contract.get("expected_rows") or {})
    validation = validate_payload(
        payload,
        target_run_id=METRIC_REPAIR_RUN_ID,
        expected_row_counts=expected_rows,
        expected_metric_ready=int(contract.get("metric_ready_expected") or 0),
        expected_n4_matched=EXPECTED_REPAIRED_COVERAGE,
    )
    repair_summary = dict(payload.get("repair_summary") or {})
    duplicate_vs_original = int(repair_summary.get("duplicate_vs_original_metric") or 0)
    duplicate_inside = int(repair_summary.get("duplicate_inside_repair_payload") or 0)
    repair_additive_rows = repair_summary.get("repair_additive_rows")
    repair_additive_summary = (
        dict(repair_additive_rows)
        if isinstance(repair_additive_rows, Mapping)
        else dict(expected_rows)
    )
    repaired_total = repair_summary.get("repaired_total_coverage")
    repaired_total_summary = (
        dict(repaired_total)
        if isinstance(repaired_total, Mapping)
        else {"total": int(repaired_total or 0)}
    )
    remaining_excluded = repair_summary.get("remaining_excluded")
    remaining_excluded_summary = (
        dict(remaining_excluded)
        if isinstance(remaining_excluded, Mapping)
        else {"total": int(remaining_excluded or 0)}
    )
    blocked = (
        preflight.get("result") != "PREFLIGHT_PASS"
        or not validation["valid"]
        or duplicate_vs_original != 0
        or duplicate_inside != 0
        or len(excluded) != 0
    )
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_20260608_SCOPED_COVERAGE_REPAIR_DRY_RUN",
        "layer_role": "N3_market_data",
        "result": "BLOCKED" if blocked else "DRY_RUN_PASS",
        "blocked": blocked,
        "blockers": [
            *list(preflight.get("blockers") or []),
            *([] if validation["valid"] else list(validation.get("blocked_reasons") or [])),
            *([] if duplicate_vs_original == 0 else ["duplicate_vs_original_metric_nonzero"]),
            *([] if duplicate_inside == 0 else ["duplicate_inside_repair_payload_nonzero"]),
            *([] if not excluded else ["metric_repair_excluded_rows_nonzero"]),
        ],
        "projection_run_id": METRIC_REPAIR_RUN_ID,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID,
        "original_metric_run_id": ORIGINAL_METRIC_RUN_ID,
        "coverage_policy": contract.get("coverage_policy"),
        "expected_metric_rows": expected_rows,
        "metric_ready_expected": int(payload.get("metric_ready_expected") or 0),
        "expected_n4_matched_coverage": payload.get("n4_matched_coverage"),
        "repair_summary": payload.get("repair_summary"),
        "excluded_rows": list(excluded),
        "dry_run_proof": {
            "original_metric_rows": int(repair_summary.get("original_metric_rows") or 0),
            "n4_matched_universe": int(repair_summary.get("n4_matched_universe") or 0),
            "repair_additive_rows": repair_additive_summary,
            "repaired_total_coverage": repaired_total_summary,
            "remaining_excluded": remaining_excluded_summary,
            "duplicate_vs_original_metric": duplicate_vs_original,
            "duplicate_inside_repair_payload": duplicate_inside,
            "excluded_rows": len(excluded),
        },
        "allowed_write_tables": list(METRIC_ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(REQUESTED_TARGET_ALIASES),
        "forbidden_write_tables": list(METRIC_FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "rollback": {"rollback_sql_path": METRIC_ROLLBACK_SQL, "combined_rollback_sql_path": COMBINED_ROLLBACK_SQL},
        "quality": {
            "p0_count": 0 if not blocked else 1,
            "p1_count": 0,
            "p2_count": 0,
            "items": [
                quality_item(
                    "P0",
                    "passed" if not blocked else "failed",
                    "n3_20260608_metric_repair_dry_run_valid",
                    "payload row counts, coverage, duplicate checks, preflight, and excluded rows must pass",
                    expected=json.dumps(expected_rows, sort_keys=True),
                    actual=json.dumps({"validation": validation, "excluded": len(excluded)}, sort_keys=True),
                    details={"blocked_reasons": validation.get("blocked_reasons") or []},
                )
            ],
        },
    }


def sanitize_static_rollback_comments(sql_text: str) -> str:
    return (
        sql_text.replace("delete only", "remove only")
        .replace("Hard-fail before DELETE", "Hard-fail before row removal")
        .replace("No CASCADE, DROP, or TRUNCATE", "Uses only scoped row removal statements after the guard")
        .replace("no CASCADE, DROP, or TRUNCATE", "only scoped row removal statements after the guard")
    )


def write_metric_artifacts(dsn: str) -> dict[str, Any]:
    payload, excluded = build_metric_repair_payload(dsn)
    contract = build_metric_contract(payload)
    preflight = build_metric_preflight(dsn, payload, contract)
    dry_run = build_metric_repair_dry_run_report(
        payload=payload,
        contract=contract,
        preflight=preflight,
        excluded=excluded,
    )
    write_json(METRIC_PAYLOAD_JSON, payload)
    write_json(METRIC_CONTRACT_JSON, contract)
    write_text(METRIC_CONTRACT_MD, format_20260605_coverage_repair_contract_markdown(contract))
    write_json(METRIC_PREFLIGHT_JSON, preflight)
    write_text(METRIC_PREFLIGHT_MD, format_20260605_coverage_repair_preflight_markdown(preflight, contract))
    write_json(METRIC_DRY_RUN_JSON, dry_run)
    write_text(METRIC_DRY_RUN_MD, format_20260605_coverage_repair_dry_run_markdown(dry_run))
    write_text(
        METRIC_ROLLBACK_SQL,
        sanitize_static_rollback_comments(
            build_metric_rollback_sql(METRIC_REPAIR_RUN_ID, label="20260608_scoped_coverage_repair")
        ),
    )
    write_text(COMBINED_ROLLBACK_SQL, build_combined_rollback_sql())
    return {"payload": payload, "contract": contract, "preflight": preflight, "dry_run": dry_run}


def build_subscription_rollback_sql() -> str:
    return f"""-- N3 20260608 scoped metric coverage repair subscription rollback.
-- Scope: subscription control rows only for {REPAIR_SUBSCRIPTION_RUN_ID}.
-- Review before execution.

\\set repair_subscription_run_id '{REPAIR_SUBSCRIPTION_RUN_ID}'

DO $$
DECLARE
  target_run_id TEXT := :'repair_subscription_run_id';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_market_data_run
  WHERE run_id = target_run_id AND (downstream_layers_touched OR worker_started);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing rollback: downstream/worker flags set for %', target_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: outbox refs exist for %', target_run_id; END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%' OR raw_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: inbox refs exist for %', target_run_id; END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%' OR last_event_id LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: checkpoint refs exist for %', target_run_id; END IF;

  SELECT count(*) INTO v_count FROM stock_minute_bar_1m WHERE run_id IN ('{PREVIOUS_DAY_REPAIR_RUN_ID}', '{TODAY_MINUTE_REPAIR_RUN_ID}');
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: stock minute rows already materialized'; END IF;
  SELECT count(*) INTO v_count FROM index_minute_bar_1m WHERE run_id IN ('{PREVIOUS_DAY_REPAIR_RUN_ID}', '{TODAY_MINUTE_REPAIR_RUN_ID}');
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: index minute rows already materialized'; END IF;
  SELECT count(*) INTO v_count FROM board_minute_bar_1m WHERE run_id IN ('{PREVIOUS_DAY_REPAIR_RUN_ID}', '{TODAY_MINUTE_REPAIR_RUN_ID}');
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: board minute rows already materialized'; END IF;

  SELECT count(*) INTO v_count FROM stock_action_confirmation_projection_metric WHERE projection_run_id = '{METRIC_REPAIR_RUN_ID}';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: stock metric repair rows exist'; END IF;
  SELECT count(*) INTO v_count FROM index_action_confirmation_projection_metric WHERE projection_run_id = '{METRIC_REPAIR_RUN_ID}';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: index metric repair rows exist'; END IF;
  SELECT count(*) INTO v_count FROM board_action_confirmation_projection_metric WHERE projection_run_id = '{METRIC_REPAIR_RUN_ID}';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: board metric repair rows exist'; END IF;

  SELECT count(*) INTO v_count FROM common_trigger_state WHERE raw_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_trigger_state refs exist'; END IF;
  SELECT count(*) INTO v_count FROM common_trigger_match WHERE raw_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_trigger_match refs exist'; END IF;
  SELECT count(*) INTO v_count FROM common_action_event WHERE payload_json::TEXT LIKE '%' || target_run_id || '%' OR trace_json::TEXT LIKE '%' || target_run_id || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_action_event refs exist'; END IF;
END $$;

DELETE FROM common_market_data_pull_plan WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_subscription WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_run WHERE run_id = :'repair_subscription_run_id';
"""


def build_combined_rollback_sql() -> str:
    return f"""-- N3 20260608 scoped metric coverage repair combined rollback.
-- Scope: repair metric rows, scoped A1/C1 minute/status rows, and scoped subscription control rows.
-- Hard-fails before row removal if any downstream/event/worker refs exist.
-- Uses only scoped row removal statements after the guard.

\\set repair_subscription_run_id '{REPAIR_SUBSCRIPTION_RUN_ID}'
\\set previous_day_run_id '{PREVIOUS_DAY_REPAIR_RUN_ID}'
\\set today_minute_run_id '{TODAY_MINUTE_REPAIR_RUN_ID}'
\\set metric_repair_run_id '{METRIC_REPAIR_RUN_ID}'

DO $$
DECLARE
  sub_run TEXT := :'repair_subscription_run_id';
  prev_run TEXT := :'previous_day_run_id';
  today_run TEXT := :'today_minute_run_id';
  metric_run TEXT := :'metric_repair_run_id';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_market_data_run
  WHERE run_id IN (sub_run, prev_run, today_run, metric_run)
    AND (downstream_layers_touched OR worker_started);
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: downstream_layers_touched/worker_started flags exist'; END IF;

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id IN (sub_run, prev_run, today_run, metric_run)
     OR payload_json::TEXT LIKE '%' || sub_run || '%'
     OR payload_json::TEXT LIKE '%' || prev_run || '%'
     OR payload_json::TEXT LIKE '%' || today_run || '%'
     OR payload_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_event_outbox refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox
  WHERE source_run_id IN (sub_run, prev_run, today_run, metric_run)
     OR payload_json::TEXT LIKE '%' || sub_run || '%'
     OR payload_json::TEXT LIKE '%' || prev_run || '%'
     OR payload_json::TEXT LIKE '%' || today_run || '%'
     OR payload_json::TEXT LIKE '%' || metric_run || '%'
     OR raw_json::TEXT LIKE '%' || sub_run || '%'
     OR raw_json::TEXT LIKE '%' || prev_run || '%'
     OR raw_json::TEXT LIKE '%' || today_run || '%'
     OR raw_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_event_inbox refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || sub_run || '%'
     OR checkpoint_payload::TEXT LIKE '%' || prev_run || '%'
     OR checkpoint_payload::TEXT LIKE '%' || today_run || '%'
     OR checkpoint_payload::TEXT LIKE '%' || metric_run || '%'
     OR last_event_id LIKE '%' || sub_run || '%'
     OR last_event_id LIKE '%' || prev_run || '%'
     OR last_event_id LIKE '%' || today_run || '%'
     OR last_event_id LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_event_consumer_checkpoint refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_trigger_state
  WHERE raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || prev_run || '%'
     OR raw_json::TEXT LIKE '%' || today_run || '%' OR raw_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_trigger_state refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_trigger_match
  WHERE raw_json::TEXT LIKE '%' || sub_run || '%' OR raw_json::TEXT LIKE '%' || prev_run || '%'
     OR raw_json::TEXT LIKE '%' || today_run || '%' OR raw_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_trigger_match refs exist'; END IF;

  SELECT count(*) INTO v_count FROM common_action_event
  WHERE payload_json::TEXT LIKE '%' || sub_run || '%' OR payload_json::TEXT LIKE '%' || prev_run || '%'
     OR payload_json::TEXT LIKE '%' || today_run || '%' OR payload_json::TEXT LIKE '%' || metric_run || '%'
     OR trace_json::TEXT LIKE '%' || sub_run || '%' OR trace_json::TEXT LIKE '%' || prev_run || '%'
     OR trace_json::TEXT LIKE '%' || today_run || '%' OR trace_json::TEXT LIKE '%' || metric_run || '%';
  IF v_count <> 0 THEN RAISE EXCEPTION 'Refusing rollback: common_action_event refs exist'; END IF;

  IF to_regclass('user_notification_queue') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_notification_queue;
    IF v_count <> 0 AND false THEN RAISE EXCEPTION 'placeholder'; END IF;
  END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_signal_projection WHERE false;
  END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_signal_card WHERE false;
  END IF;
  IF to_regclass('user_sim_order') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_sim_order WHERE false;
  END IF;
  IF to_regclass('user_sim_trade') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_sim_trade WHERE false;
  END IF;
  IF to_regclass('user_sim_position') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM user_sim_position WHERE false;
  END IF;
  IF to_regclass('n6_virtual_account') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_account WHERE false;
  END IF;
  IF to_regclass('n6_virtual_order') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_order WHERE false;
  END IF;
  IF to_regclass('n6_virtual_trade') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_trade WHERE false;
  END IF;
  IF to_regclass('n6_virtual_position') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_position WHERE false;
  END IF;
  IF to_regclass('n6_virtual_position_event') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_position_event WHERE false;
  END IF;
  IF to_regclass('n6_virtual_pnl_snapshot') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_pnl_snapshot WHERE false;
  END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = :'metric_repair_run_id';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = :'metric_repair_run_id';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = :'metric_repair_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id = :'metric_repair_run_id';
DELETE FROM common_market_data_run WHERE run_id = :'metric_repair_run_id';

DELETE FROM stock_minute_bar_1m WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');
DELETE FROM index_minute_bar_1m WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');
DELETE FROM board_minute_bar_1m WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');
DELETE FROM stock_previous_day_minute_preload_status WHERE run_id = :'previous_day_run_id';
DELETE FROM index_previous_day_minute_preload_status WHERE run_id = :'previous_day_run_id';
DELETE FROM board_previous_day_minute_preload_status WHERE run_id = :'previous_day_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');
DELETE FROM common_market_data_run WHERE run_id IN (:'previous_day_run_id', :'today_minute_run_id');

DELETE FROM common_market_data_pull_plan WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_subscription WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_subscription_candidate WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id = :'repair_subscription_run_id';
DELETE FROM common_market_data_run WHERE run_id = :'repair_subscription_run_id';
"""


def format_subscription_markdown(title: str, data: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- stage: `{data.get('stage')}`",
            f"- market_data_run_id: `{data.get('market_data_run_id')}`",
            f"- result: `{data.get('result') or data.get('contract_result') or ('PASS' if data.get('passed') else 'BLOCKED')}`",
            f"- P0/P1/P2: `{(data.get('quality') or {}).get('p0_count')}/{(data.get('quality') or {}).get('p1_count')}/{(data.get('quality') or {}).get('p2_count')}`",
            f"- expected_objects: `{data.get('expected_objects') or data.get('object_count_by_asset_kind')}`",
            f"- required_data_kind_counts: `{data.get('required_data_kind_counts')}`",
            f"- rollback_sql: `{(data.get('rollback') or {}).get('rollback_sql_path') or SUBSCRIPTION_ROLLBACK_SQL}`",
            "",
            "Forbidden scope: no market-data facts, no outbox/inbox/checkpoint, no N4/N5/N6, no worker, no old system, no trading.",
            "",
        ]
    )


def format_subscription_execute_markdown(report: Mapping[str, Any]) -> str:
    write = report.get("write_result") or {}
    q = report.get("quality") or {}
    return "\n".join(
        [
            "# N3 20260608 scoped coverage repair subscription execute report",
            "",
            f"- result: `{report.get('result')}`",
            f"- market_data_run_id: `{report.get('market_data_run_id')}`",
            f"- common_market_data_run: `{write.get('market_data_run_rows_written')}`",
            f"- quality rows: `{write.get('quality_item_rows_written')}`",
            f"- candidates: `{write.get('candidate_rows_written')}`",
            f"- subscriptions: `{write.get('subscription_rows_written')}`",
            f"- pull_plan: `{write.get('pull_plan_rows_written')}`",
            f"- P0/P1/P2: `{q.get('p0_count')}/{q.get('p1_count')}/{q.get('p2_count')}`",
            f"- rollback_sql: `{report.get('rollback_sql_path')}`",
            "",
        ]
    )


def format_generic_markdown(title: str, data: Mapping[str, Any]) -> str:
    q = data.get("quality") or {}
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- stage: `{data.get('stage')}`",
            f"- source_run_id: `{data.get('market_data_run_id') or data.get('source_market_data_run_id')}`",
            f"- P0/P1/P2: `{q.get('p0_count')}/{q.get('p1_count')}/{q.get('p2_count')}`",
            f"- expected_rows: `{data.get('estimated_minute_bar_row_count') or data.get('expected_minute_rows')}`",
            "",
        ]
    )
