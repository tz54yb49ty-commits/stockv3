"""N3-A0 previous-day minute preload dry-run planner.

This module consumes the persisted N3-6 subscription and pull-plan control
rows and prepares the previous-day minute preload plan. It does not call
market-data adapters, write market-data facts, emit event outbox rows, execute
migrations, or touch downstream layers.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.schema_migration_review import REQUIRED_MARKET_CONTROL_TABLES
from ashare_v3.market.subscription_plan import (
    ADAPTER_NAMES,
    ASSET_KINDS,
    rows_section,
)


DEFAULT_MARKET_FACT_SCHEMA_PATH = "sql/007_market_data_fact_schema.sql"
EXPECTED_A_SHARE_MINUTE_BAR_COUNT = 240

MINUTE_FACT_TABLES = {
    "stock": "stock_minute_bar_1m",
    "index": "index_minute_bar_1m",
    "board": "board_minute_bar_1m",
}
PRELOAD_STATUS_TABLES = {
    "stock": "stock_previous_day_minute_preload_status",
    "index": "index_previous_day_minute_preload_status",
    "board": "board_previous_day_minute_preload_status",
}
REALTIME_SNAPSHOT_TABLES = {
    "stock": "stock_realtime_daily_snapshot",
    "index": "index_realtime_daily_snapshot",
    "board": "board_realtime_daily_snapshot",
}
REQUIRED_N3A_EXECUTE_TABLES = (
    *REQUIRED_MARKET_CONTROL_TABLES,
    *MINUTE_FACT_TABLES.values(),
    *PRELOAD_STATUS_TABLES.values(),
)
FULL_MARKET_FACT_TABLES = (
    *REALTIME_SNAPSHOT_TABLES.values(),
    *MINUTE_FACT_TABLES.values(),
    *PRELOAD_STATUS_TABLES.values(),
)


def build_previous_day_minute_preload_plan_dry_run(
    *,
    dsn: str,
    run_id: str | None = None,
    market_data_run_id: str | None = None,
    source_trade_date: str | None = None,
    for_trade_date: str | None = None,
    expected_previous_day_minute_date: str | None = None,
    include_rows: bool = True,
) -> dict[str, Any]:
    """Build a dry-run plan for N3-A previous-day minute preload."""

    resolved_run_id = market_data_run_id or run_id
    if not resolved_run_id:
        raise ValueError("market_data_run_id is required for N3-A0 persisted subscription dry-run")

    subscription_report = build_persisted_subscription_report(
        dsn=dsn,
        market_data_run_id=resolved_run_id,
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
    )
    if subscription_report.get("blocked"):
        return build_n3_subscription_blocked_report(subscription_report)

    expected_date = expected_previous_day_minute_date or str(subscription_report.get("prev_trade_date") or "")

    subscriptions = previous_day_subscriptions(subscription_report)
    preload_rows = build_preload_status_plan_rows(
        subscriptions=subscriptions,
        expected_bar_count=EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
    )
    pull_batches = build_preload_pull_batches(
        subscription_report=subscription_report,
        subscriptions=subscriptions,
        persisted_pull_plans=subscription_report.get("market_data_pull_plan", {}).get("rows", []),
        expected_bar_count=EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
    )
    quality_items = build_preload_quality_items(
        subscription_report=subscription_report,
        subscriptions=subscriptions,
        pull_batches=pull_batches,
        expected_previous_day_minute_date=expected_date,
    )
    severity_counts = count_quality_severities(quality_items)
    previous_day_object_keys = {(row["asset_kind"], row["identity_key"]) for row in subscriptions}
    asset_counts = dict(sorted(Counter(row["asset_kind"] for row in subscriptions).items()))
    estimated_rows_by_asset = {
        asset_kind: asset_counts.get(asset_kind, 0) * EXPECTED_A_SHARE_MINUTE_BAR_COUNT
        for asset_kind in ASSET_KINDS
    }
    estimated_write_tables_by_asset = {
        asset_kind: {
            "minute_fact_table": MINUTE_FACT_TABLES[asset_kind],
            "preload_status_table": PRELOAD_STATUS_TABLES[asset_kind],
        }
        for asset_kind in ASSET_KINDS
    }

    return {
        "stage": "N3-A0",
        "plan_mode": "previous_day_minute_preload_dry_run",
        "mode": "dry_run",
        "market_data_run_id": subscription_report.get("market_data_run_id"),
        "source_condition_run_id": subscription_report.get("source_condition_run_id"),
        "source_trade_date": subscription_report.get("source_trade_date"),
        "for_trade_date": subscription_report.get("for_trade_date"),
        "prev_trade_date": subscription_report.get("prev_trade_date"),
        "data_trade_date": subscription_report.get("prev_trade_date"),
        "expected_previous_day_minute_date": expected_date,
        "source_subscription_plan": {
            "market_data_run_id": subscription_report.get("market_data_run_id"),
            "source_scope_row_count": subscription_report.get("source_scope_row_count"),
            "candidate_row_count": subscription_report.get("candidate_row_count"),
            "subscription_row_count": subscription_report.get("subscription_row_count"),
            "subscription_object_count": subscription_report.get("subscription_object_count"),
            "required_data_kind_counts": subscription_report.get("required_data_kind_counts"),
            "dedup_ratio": subscription_report.get("dedup_ratio"),
            "p0_count": subscription_report.get("quality", {}).get("p0_count"),
            "passed": subscription_report.get("passed"),
        },
        "previous_day_minute_subscription_count": len(subscriptions),
        "previous_day_minute_object_count": len(previous_day_object_keys),
        "previous_day_minute_object_count_by_asset_kind": asset_counts_by_asset(asset_counts),
        "expected_minute_bar_count_per_object": EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
        "estimated_minute_bar_row_count": len(previous_day_object_keys) * EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
        "estimated_minute_bar_row_count_by_asset_kind": estimated_rows_by_asset,
        "preload_pull_plan_row_count": len(pull_batches),
        "previous_day_minute_date_counts": dict(sorted(Counter(str(row.get("data_trade_date") or "") for row in subscriptions).items())),
        "source_adapter_plan": rows_section(pull_batches, include_rows=include_rows),
        "estimated_write_tables": sorted(
            {
                table_name
                for tables in estimated_write_tables_by_asset.values()
                for table_name in tables.values()
            }
        ),
        "estimated_write_tables_by_asset_kind": estimated_write_tables_by_asset,
        "event_outbox_write_planned": False,
        "generated_event_types": [],
        "preload_status_plan": rows_section(preload_rows, include_rows=include_rows),
        "preload_pull_plan": rows_section(pull_batches, include_rows=include_rows),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blocked": severity_counts["P0"] > 0,
        "execute_ready": severity_counts["P0"] == 0,
        "n2_scope_error": False,
        "n2_handoff_prompt": None,
        "n3_subscription_error": False,
        "schema_path": DEFAULT_MARKET_FACT_SCHEMA_PATH,
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


def build_persisted_subscription_report(
    *,
    dsn: str,
    market_data_run_id: str,
    source_trade_date: str | None = None,
    for_trade_date: str | None = None,
) -> dict[str, Any]:
    """Read the persisted N3-6 subscription run and rows in read-only mode."""

    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        run_row = fetch_market_data_run(cur, market_data_run_id)
        if run_row is None:
            return build_missing_subscription_run_report(market_data_run_id)
        if source_trade_date and run_row.get("source_trade_date") != source_trade_date:
            return build_subscription_run_filter_blocked_report(run_row, "source_trade_date", source_trade_date)
        if for_trade_date and run_row.get("for_trade_date") != for_trade_date:
            return build_subscription_run_filter_blocked_report(run_row, "for_trade_date", for_trade_date)
        subscription_rows = fetch_subscription_rows(cur, market_data_run_id)
        pull_plan_rows = fetch_previous_day_pull_plan_rows(cur, market_data_run_id)
        quality_rows = fetch_market_data_quality_rows(cur, market_data_run_id)

    previous_rows = [
        row for row in subscription_rows if row.get("required_data_kind") == "previous_day_minute_bar_1m"
    ]
    required_kind_counts = dict(sorted(Counter(str(row.get("required_data_kind") or "") for row in subscription_rows).items()))
    previous_object_keys = {(row["asset_kind"], row["identity_key"]) for row in previous_rows}
    source_quality_items = build_persisted_subscription_quality_items(
        run_row=run_row,
        subscription_rows=subscription_rows,
        previous_rows=previous_rows,
        pull_plan_rows=pull_plan_rows,
        source_quality_rows=quality_rows,
    )
    severity_counts = count_quality_severities(source_quality_items)
    return {
        "stage": "N3-6",
        "plan_mode": "market_data_subscription_persisted",
        "mode": run_row.get("mode"),
        "market_data_run_id": market_data_run_id,
        "source_condition_run_id": run_row.get("source_condition_run_id"),
        "source_trade_date": run_row.get("source_trade_date"),
        "for_trade_date": run_row.get("for_trade_date"),
        "prev_trade_date": run_row.get("prev_trade_date"),
        "source_scope_row_count": run_row.get("source_scope_row_count"),
        "candidate_row_count": run_row.get("candidate_row_count"),
        "subscription_row_count": run_row.get("subscription_row_count"),
        "subscription_object_count": run_row.get("subscription_object_count"),
        "required_data_kind_counts": required_kind_counts,
        "dedup_ratio": run_row.get("dedup_ratio"),
        "market_data_subscription_dedup": rows_section(subscription_rows, include_rows=True),
        "market_data_pull_plan": rows_section(pull_plan_rows, include_rows=True),
        "previous_day_minute_subscription_count": len(previous_rows),
        "previous_day_minute_object_count": len(previous_object_keys),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": source_quality_items,
        },
        "blocked": severity_counts["P0"] > 0,
        "passed": severity_counts["P0"] == 0,
    }


def fetch_market_data_run(cur: psycopg.Cursor[dict[str, Any]], market_data_run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
               prev_trade_date, mode, status, p0_count, p1_count, p2_count,
               source_scope_row_count, candidate_row_count, subscription_row_count,
               subscription_object_count, dedup_ratio, market_data_pulled,
               market_data_fact_written, downstream_layers_touched, worker_started
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (market_data_run_id,),
    )
    row = cur.fetchone()
    return normalize_db_row(row) if row else None


def fetch_subscription_rows(cur: psycopg.Cursor[dict[str, Any]], market_data_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT subscription_id, run_id, source_condition_run_id, for_trade_date,
               source_trade_date, prev_trade_date, asset_kind, identity_key,
               exchange, code, display_code, name, required_data_kind,
               data_trade_date, source_scope_row_count, source_scope_tables,
               source_scope_ids, source_condition_pool_ids, condition_keys,
               directions, allowed_signal_types, priority, status, selected_reason,
               raw_json
        FROM common_market_data_subscription
        WHERE run_id = %s
        ORDER BY asset_kind, required_data_kind, identity_key, subscription_id
        """,
        (market_data_run_id,),
    )
    return [normalize_subscription_row(row) for row in cur.fetchall()]


def fetch_previous_day_pull_plan_rows(cur: psycopg.Cursor[dict[str, Any]], market_data_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT pull_plan_id, run_id, source_condition_run_id, for_trade_date,
               source_trade_date, prev_trade_date, asset_kind, required_data_kind,
               data_trade_date, adapter_name, subscription_count, object_count,
               subscription_ids_sample, subscription_refs_sample, identity_keys_sample,
               plan_status, execute_allowed, selected_reason, raw_json
        FROM common_market_data_pull_plan
        WHERE run_id = %s
          AND required_data_kind = 'previous_day_minute_bar_1m'
        ORDER BY asset_kind, data_trade_date, pull_plan_id
        """,
        (market_data_run_id,),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def fetch_market_data_quality_rows(cur: psycopg.Cursor[dict[str, Any]], market_data_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT severity, status, gate_code, gate_name, expected_value,
               actual_value, details
        FROM common_market_data_quality_item
        WHERE run_id = %s
        ORDER BY quality_item_id
        """,
        (market_data_run_id,),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def normalize_subscription_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_db_row(row)
    raw_json = output.get("raw_json") if isinstance(output.get("raw_json"), Mapping) else {}
    output["subscription_ref"] = raw_json.get("subscription_ref") or f"subscription:{output.get('subscription_id')}"
    output["source_scope_refs"] = raw_json.get("source_scope_refs") or []
    output["data_trade_dates"] = raw_json.get("data_trade_dates") or [output.get("data_trade_date")]
    return output


def normalize_db_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: normalize_db_value(value) for key, value in dict(row).items()}


def normalize_db_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def fetch_table_status(cur: psycopg.Cursor[dict[str, Any]], table_names: Sequence[str]) -> dict[str, bool]:
    status: dict[str, bool] = {}
    for table_name in table_names:
        cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
        status[table_name] = cur.fetchone()["regclass"] is not None
    return status


def previous_day_subscriptions(subscription_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = (subscription_report.get("market_data_subscription_dedup") or {}).get("rows") or []
    return [
        dict(row)
        for row in rows
        if row.get("required_data_kind") == "previous_day_minute_bar_1m"
    ]


def build_preload_status_plan_rows(
    *,
    subscriptions: Sequence[Mapping[str, Any]],
    expected_bar_count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, subscription in enumerate(subscriptions, start=1):
        asset_kind = str(subscription.get("asset_kind"))
        rows.append(
            {
                "preload_status_ref": f"dry_run:preload_status:{index}",
                "subscription_ref": subscription.get("subscription_ref"),
                "run_id": subscription.get("run_id"),
                "source_condition_run_id": subscription.get("source_condition_run_id"),
                "for_trade_date": subscription.get("for_trade_date"),
                "trade_date": subscription.get("data_trade_date"),
                "asset_kind": asset_kind,
                "target_table": PRELOAD_STATUS_TABLES[asset_kind],
                "minute_fact_table": MINUTE_FACT_TABLES[asset_kind],
                "identity_key": subscription.get("identity_key"),
                "exchange": subscription.get("exchange"),
                "code": subscription.get("code"),
                "display_code": subscription.get("display_code"),
                "name": subscription.get("name"),
                "source_adapter": ADAPTER_NAMES[asset_kind],
                "expected_bar_count": expected_bar_count,
                "planned_status": "planned",
                "source_scope_ids": subscription.get("source_scope_ids") or [],
                "source_condition_pool_ids": subscription.get("source_condition_pool_ids") or [],
                "condition_keys": subscription.get("condition_keys") or [],
                "directions": subscription.get("directions") or [],
                "selected_reason": "dry-run preload status row for previous_day_minute_bar_1m subscription",
            }
        )
    return rows


def build_preload_pull_batches(
    *,
    subscription_report: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    persisted_pull_plans: Sequence[Mapping[str, Any]] | None = None,
    expected_bar_count: int,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for subscription in subscriptions:
        groups[(str(subscription.get("asset_kind")), str(subscription.get("data_trade_date")))].append(subscription)

    pull_plan_by_key = {
        (str(row.get("asset_kind")), str(row.get("data_trade_date"))): row
        for row in (persisted_pull_plans or [])
    }
    rows: list[dict[str, Any]] = []
    for (asset_kind, trade_date), group in sorted(groups.items()):
        identity_keys = [row.get("identity_key") for row in group]
        persisted_pull_plan = pull_plan_by_key.get((asset_kind, trade_date), {})
        rows.append(
            {
                "preload_pull_plan_ref": f"dry_run:previous_day_pull:{len(rows) + 1}",
                "source_pull_plan_id": persisted_pull_plan.get("pull_plan_id"),
                "market_data_run_id": subscription_report.get("market_data_run_id"),
                "source_condition_run_id": subscription_report.get("source_condition_run_id"),
                "for_trade_date": subscription_report.get("for_trade_date"),
                "trade_date": trade_date,
                "previous_day_minute_date": trade_date,
                "asset_kind": asset_kind,
                "required_data_kind": "previous_day_minute_bar_1m",
                "adapter_name": persisted_pull_plan.get("adapter_name") or ADAPTER_NAMES[asset_kind],
                "subscription_count": len(group),
                "object_count": len(set(identity_keys)),
                "target_minute_fact_table": MINUTE_FACT_TABLES[asset_kind],
                "target_preload_status_table": PRELOAD_STATUS_TABLES[asset_kind],
                "estimated_write_tables": [
                    MINUTE_FACT_TABLES[asset_kind],
                    PRELOAD_STATUS_TABLES[asset_kind],
                ],
                "expected_bar_count_per_object": expected_bar_count,
                "expected_minute_bar_rows": len(set(identity_keys)) * expected_bar_count,
                "estimated_bar_row_count": len(set(identity_keys)) * expected_bar_count,
                "source_adapter_plan": {
                    "adapter_name": persisted_pull_plan.get("adapter_name") or ADAPTER_NAMES[asset_kind],
                    "adapter_call_planned": False,
                    "dry_run_only": True,
                },
                "persisted_pull_plan": {
                    "pull_plan_id": persisted_pull_plan.get("pull_plan_id"),
                    "subscription_count": persisted_pull_plan.get("subscription_count"),
                    "object_count": persisted_pull_plan.get("object_count"),
                    "execute_allowed": persisted_pull_plan.get("execute_allowed"),
                    "plan_status": persisted_pull_plan.get("plan_status"),
                },
                "identity_keys_sample": identity_keys[:20],
                "execute_allowed": False,
                "selected_reason": "N3-A0 dry-run only; adapter calls and writes require later execute",
            }
        )
    return rows


def build_preload_quality_items(
    *,
    subscription_report: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_batches: Sequence[Mapping[str, Any]],
    expected_previous_day_minute_date: str,
) -> list[dict[str, Any]]:
    subscription_quality = subscription_report.get("quality") or {}
    subscription_p0 = int(subscription_quality.get("p0_count") or 0)
    subscription_p1 = int(subscription_quality.get("p1_count") or 0)
    subscription_p2 = int(subscription_quality.get("p2_count") or 0)
    prev_trade_date = str(subscription_report.get("prev_trade_date") or "")
    wrong_trade_dates = [
        row.get("subscription_ref") or row.get("identity_key")
        for row in subscriptions
        if str(row.get("data_trade_date") or "") != expected_previous_day_minute_date
    ]
    pull_plan_wrong_trade_dates = [
        row.get("source_pull_plan_id") or row.get("asset_kind")
        for row in pull_batches
        if str(row.get("previous_day_minute_date") or "") != expected_previous_day_minute_date
    ]
    expected_asset_kinds = {asset_kind for asset_kind in ASSET_KINDS if any(row.get("asset_kind") == asset_kind for row in subscriptions)}
    pull_plan_asset_kinds = {str(row.get("asset_kind")) for row in pull_batches}
    missing_asset_pull_plans = sorted(expected_asset_kinds - pull_plan_asset_kinds)
    count_mismatches = []
    for row in pull_batches:
        persisted = row.get("persisted_pull_plan") if isinstance(row.get("persisted_pull_plan"), Mapping) else {}
        if persisted and (
            int(persisted.get("subscription_count") or -1) != int(row.get("subscription_count") or 0)
            or int(persisted.get("object_count") or -1) != int(row.get("object_count") or 0)
        ):
            count_mismatches.append(row.get("asset_kind"))
    execute_allowed_plans = [
        row.get("source_pull_plan_id") or row.get("asset_kind")
        for row in pull_batches
        if (row.get("persisted_pull_plan") or {}).get("execute_allowed") is not False
    ]
    missing_trace = [
        row.get("subscription_ref") or row.get("identity_key")
        for row in subscriptions
        if not row.get("source_scope_ids") or not row.get("source_condition_pool_ids")
    ]
    estimated_tables = [
        table
        for row in pull_batches
        for table in row.get("estimated_write_tables", [])
    ]
    runtime_identifier_hits = sorted({table for table in estimated_tables if table.endswith("_runtime") or "_runtime" in table})
    event_outbox_hits = sorted({table for table in estimated_tables if table == "common_event_outbox"})
    user_event_hits: list[str] = []
    physical_separation_errors = []
    for row in pull_batches:
        asset_kind = str(row.get("asset_kind"))
        expected_minute_prefix = f"{asset_kind}_"
        if not str(row.get("target_minute_fact_table") or "").startswith(expected_minute_prefix):
            physical_separation_errors.append(str(row.get("target_minute_fact_table")))
        if not str(row.get("target_preload_status_table") or "").startswith(expected_minute_prefix):
            physical_separation_errors.append(str(row.get("target_preload_status_table")))
    items = [
        quality_item(
            "P0",
            "passed" if subscription_report.get("passed") and subscription_p0 == 0 else "failed",
            "n3_6_subscription_run_clean",
            "N3-A0 requires a clean persisted N3-6 subscription run",
            expected="N3-6 subscription run passed and P0=0",
            actual=f"passed={subscription_report.get('passed')} p0={subscription_p0}",
        ),
        quality_item(
            "P1",
            "warning" if subscription_p1 > 0 else "passed",
            "n3_6_subscription_run_p1_carried",
            "N3-A0 carries non-blocking P1 items from the N3-6 subscription run",
            expected="0",
            actual=str(subscription_p1),
        ),
        quality_item(
            "P2",
            "warning" if subscription_p2 > 0 else "passed",
            "n3_6_subscription_run_p2_carried",
            "N3-A0 carries non-blocking P2 items from the N3-6 subscription run",
            expected="0",
            actual=str(subscription_p2),
        ),
        quality_item(
            "P0",
            "passed" if subscriptions else "failed",
            "previous_day_minute_subscriptions_present",
            "N3-A0 requires previous_day_minute_bar_1m subscriptions",
            expected=">0",
            actual=str(len(subscriptions)),
        ),
        quality_item(
            "P0",
            "passed" if not wrong_trade_dates else "failed",
            "previous_day_subscription_trade_date_matches_expected",
            "previous-day minute subscriptions must target the expected previous-day minute date",
            expected=expected_previous_day_minute_date,
            actual="matched" if not wrong_trade_dates else ",".join(str(item) for item in wrong_trade_dates[:20]),
        ),
        quality_item(
            "P0",
            "passed" if expected_previous_day_minute_date == prev_trade_date else "failed",
            "expected_previous_day_minute_date_matches_prev_trade_date",
            "N3-A0 expected previous-day minute date must match N3-6 prev_trade_date",
            expected=prev_trade_date,
            actual=expected_previous_day_minute_date,
        ),
        quality_item(
            "P0",
            "passed" if not pull_plan_wrong_trade_dates else "failed",
            "previous_day_pull_plan_trade_date_matches_expected",
            "previous-day minute pull plans must target the expected previous-day minute date",
            expected=expected_previous_day_minute_date,
            actual="matched" if not pull_plan_wrong_trade_dates else ",".join(str(item) for item in pull_plan_wrong_trade_dates[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not missing_trace else "failed",
            "previous_day_subscription_trace_present",
            "subscriptions must preserve source_scope_ids and source_condition_pool_ids",
            expected="trace arrays present",
            actual="present" if not missing_trace else ",".join(str(item) for item in missing_trace[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not missing_asset_pull_plans else "failed",
            "previous_day_pull_plan_asset_coverage",
            "N3-A0 requires a previous-day pull plan for each asset kind present in subscriptions",
            expected="pull plan for each asset kind in subscriptions",
            actual="covered" if not missing_asset_pull_plans else ",".join(missing_asset_pull_plans),
        ),
        quality_item(
            "P0",
            "passed" if not count_mismatches else "failed",
            "previous_day_pull_plan_counts_match_subscriptions",
            "persisted pull_plan counts must match the corresponding subscription rows",
            expected="counts match",
            actual="matched" if not count_mismatches else ",".join(str(item) for item in count_mismatches),
        ),
        quality_item(
            "P0",
            "passed" if not execute_allowed_plans else "failed",
            "previous_day_pull_plan_execute_not_allowed",
            "N3-A0 dry-run must not mark persisted pull plans executable",
            expected="execute_allowed=false",
            actual="false" if not execute_allowed_plans else ",".join(str(item) for item in execute_allowed_plans[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not physical_separation_errors else "failed",
            "previous_day_estimated_tables_physically_separated",
            "N3-A0 estimated write tables must be physically separated by stock/index/board",
            expected="stock/index/board target table prefixes",
            actual="separated" if not physical_separation_errors else ",".join(physical_separation_errors),
        ),
        quality_item(
            "P0",
            "passed" if not runtime_identifier_hits else "failed",
            "n3a_no_runtime_table_names",
            "N3-A0 plan must not use *_runtime table names",
            expected="no *_runtime identifiers",
            actual="none" if not runtime_identifier_hits else ",".join(runtime_identifier_hits),
        ),
        quality_item(
            "P0",
            "passed" if not event_outbox_hits else "failed",
            "n3a_no_event_outbox_write_plan",
            "N3-A0 dry-run must not plan common_event_outbox writes",
            expected="common_event_outbox absent",
            actual="absent" if not event_outbox_hits else ",".join(event_outbox_hits),
        ),
        quality_item(
            "P0",
            "passed" if not user_event_hits else "failed",
            "n3a_no_user_event_names",
            "N3-A0 dry-run must not generate User* event names",
            expected="no User* events",
            actual="none" if not user_event_hits else ",".join(user_event_hits),
        ),
        quality_item(
            "P0",
            "passed",
            "n3a_dry_run_no_adapter_call",
            "N3-A0 dry-run does not call external market-data adapters",
        ),
        quality_item(
            "P0",
            "passed",
            "n3a_dry_run_no_database_write",
            "N3-A0 dry-run does not write market-data rows or execute migrations",
        ),
        quality_item(
            "P0",
            "passed",
            "n3a_dry_run_no_event_outbox_write",
            "N3-A0 dry-run does not write common_event_outbox",
        ),
        quality_item(
            "P0",
            "passed",
            "n3a_dry_run_no_downstream_layers",
            "N3-A0 dry-run does not enter trigger/action/mobile/voice/sim",
        ),
    ]
    return items


def asset_counts_by_asset(asset_counts: Mapping[str, int]) -> dict[str, int]:
    return {asset_kind: int(asset_counts.get(asset_kind, 0)) for asset_kind in ASSET_KINDS}


def build_persisted_subscription_quality_items(
    *,
    run_row: Mapping[str, Any],
    subscription_rows: Sequence[Mapping[str, Any]],
    previous_rows: Sequence[Mapping[str, Any]],
    pull_plan_rows: Sequence[Mapping[str, Any]],
    source_quality_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    _ = source_quality_rows
    p0_count = int(run_row.get("p0_count") or 0)
    p1_count = int(run_row.get("p1_count") or 0)
    p2_count = int(run_row.get("p2_count") or 0)
    items = [
        quality_item(
            "P0",
            "passed" if run_row.get("mode") == "execute" else "failed",
            "n3_6_market_data_run_mode_execute",
            "N3-A0 must read a persisted N3-6 execute run",
            expected="execute",
            actual=str(run_row.get("mode")),
        ),
        quality_item(
            "P0",
            "passed" if run_row.get("status") == "passed" else "failed",
            "n3_6_market_data_run_status_passed",
            "N3-A0 requires the persisted N3-6 run status to be passed",
            expected="passed",
            actual=str(run_row.get("status")),
        ),
        quality_item(
            "P0",
            "passed" if p0_count == 0 else "failed",
            "n3_6_market_data_run_p0_zero",
            "N3-A0 requires the persisted N3-6 run P0 count to be zero",
            expected="0",
            actual=str(p0_count),
        ),
        quality_item(
            "P1",
            "warning" if p1_count > 0 else "passed",
            "n3_6_market_data_run_p1_carried",
            "N3-A0 carries non-blocking P1 items from persisted N3-6 run",
            expected="0",
            actual=str(p1_count),
        ),
        quality_item(
            "P2",
            "warning" if p2_count > 0 else "passed",
            "n3_6_market_data_run_p2_carried",
            "N3-A0 carries non-blocking P2 items from persisted N3-6 run",
            expected="0",
            actual=str(p2_count),
        ),
        quality_item(
            "P0",
            "passed" if not run_row.get("market_data_pulled") else "failed",
            "n3_6_market_data_not_pulled",
            "N3-A0 starts from subscription metadata, before any market data pull",
            expected="market_data_pulled=false",
            actual=str(run_row.get("market_data_pulled")).lower(),
        ),
        quality_item(
            "P0",
            "passed" if not run_row.get("market_data_fact_written") else "failed",
            "n3_6_market_data_fact_not_written",
            "N3-A0 starts before market-data fact writes",
            expected="market_data_fact_written=false",
            actual=str(run_row.get("market_data_fact_written")).lower(),
        ),
        quality_item(
            "P0",
            "passed" if not run_row.get("downstream_layers_touched") and not run_row.get("worker_started") else "failed",
            "n3_6_no_downstream_or_worker",
            "N3-A0 requires N3-6 not to have touched downstream layers or workers",
            expected="downstream_layers_touched=false worker_started=false",
            actual=(
                f"downstream_layers_touched={str(run_row.get('downstream_layers_touched')).lower()} "
                f"worker_started={str(run_row.get('worker_started')).lower()}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if subscription_rows else "failed",
            "n3_6_subscription_rows_present",
            "N3-A0 requires persisted market_data_subscription rows",
            expected=">0",
            actual=str(len(subscription_rows)),
        ),
        quality_item(
            "P0",
            "passed" if previous_rows else "failed",
            "n3_6_previous_day_subscription_rows_present",
            "N3-A0 requires persisted previous_day_minute_bar_1m subscription rows",
            expected=">0",
            actual=str(len(previous_rows)),
        ),
        quality_item(
            "P0",
            "passed" if pull_plan_rows else "failed",
            "n3_6_previous_day_pull_plan_rows_present",
            "N3-A0 requires persisted previous_day_minute_bar_1m pull_plan rows",
            expected=">0",
            actual=str(len(pull_plan_rows)),
        ),
    ]
    return items


def build_missing_subscription_run_report(market_data_run_id: str) -> dict[str, Any]:
    items = [
        quality_item(
            "P0",
            "failed",
            "n3_6_market_data_run_exists",
            "N3-A0 requires the persisted N3-6 market_data_subscription run",
            expected=market_data_run_id,
            actual="missing",
        )
    ]
    severity_counts = count_quality_severities(items)
    return {
        "stage": "N3-6",
        "plan_mode": "market_data_subscription_persisted",
        "mode": None,
        "market_data_run_id": market_data_run_id,
        "source_condition_run_id": None,
        "source_trade_date": None,
        "for_trade_date": None,
        "prev_trade_date": None,
        "source_scope_row_count": 0,
        "candidate_row_count": 0,
        "subscription_row_count": 0,
        "subscription_object_count": 0,
        "required_data_kind_counts": {},
        "dedup_ratio": None,
        "market_data_subscription_dedup": rows_section([], include_rows=True),
        "market_data_pull_plan": rows_section([], include_rows=True),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": items,
        },
        "blocked": True,
        "passed": False,
    }


def build_subscription_run_filter_blocked_report(
    run_row: Mapping[str, Any],
    field_name: str,
    expected_value: str,
) -> dict[str, Any]:
    items = [
        quality_item(
            "P0",
            "failed",
            f"n3_6_market_data_run_{field_name}_matches_filter",
            "N3-A0 persisted run does not match the requested filter",
            expected=expected_value,
            actual=str(run_row.get(field_name)),
        )
    ]
    severity_counts = count_quality_severities(items)
    return {
        "stage": "N3-6",
        "plan_mode": "market_data_subscription_persisted",
        "mode": run_row.get("mode"),
        "market_data_run_id": run_row.get("run_id"),
        "source_condition_run_id": run_row.get("source_condition_run_id"),
        "source_trade_date": run_row.get("source_trade_date"),
        "for_trade_date": run_row.get("for_trade_date"),
        "prev_trade_date": run_row.get("prev_trade_date"),
        "source_scope_row_count": run_row.get("source_scope_row_count"),
        "candidate_row_count": run_row.get("candidate_row_count"),
        "subscription_row_count": run_row.get("subscription_row_count"),
        "subscription_object_count": run_row.get("subscription_object_count"),
        "required_data_kind_counts": {},
        "dedup_ratio": run_row.get("dedup_ratio"),
        "market_data_subscription_dedup": rows_section([], include_rows=True),
        "market_data_pull_plan": rows_section([], include_rows=True),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": items,
        },
        "blocked": True,
        "passed": False,
    }


def build_n3_subscription_blocked_report(subscription_report: Mapping[str, Any]) -> dict[str, Any]:
    quality_items = [
        quality_item(
            "P0",
            "failed",
            "n3_subscription_contract_failed",
            "N3-A0 stopped because persisted N3-6 subscription run is not usable",
            expected="persisted N3-6 subscription run P0=0",
            actual=f"P0={(subscription_report.get('quality') or {}).get('p0_count')}",
        )
    ]
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": "N3-A0",
        "plan_mode": "previous_day_minute_preload_dry_run",
        "mode": "dry_run",
        "market_data_run_id": subscription_report.get("market_data_run_id"),
        "source_condition_run_id": subscription_report.get("source_condition_run_id"),
        "source_trade_date": subscription_report.get("source_trade_date"),
        "for_trade_date": subscription_report.get("for_trade_date"),
        "prev_trade_date": subscription_report.get("prev_trade_date"),
        "source_subscription_plan": {
            "passed": subscription_report.get("passed"),
            "blocked": subscription_report.get("blocked"),
            "p0_count": (subscription_report.get("quality") or {}).get("p0_count"),
            "blocking_items": [
                item
                for item in (subscription_report.get("quality") or {}).get("items", [])
                if item.get("status") == "failed"
            ],
        },
        "previous_day_minute_subscription_count": 0,
        "previous_day_minute_object_count": 0,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blocked": True,
        "execute_ready": False,
        "n2_scope_error": False,
        "n2_handoff_prompt": None,
        "n3_subscription_error": True,
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


def build_n2_blocked_report(subscription_report: Mapping[str, Any]) -> dict[str, Any]:
    prompt = format_n2_handoff_prompt(subscription_report)
    quality_items = [
        quality_item(
            "P0",
            "failed",
            "n2_scope_contract_failed",
            "N3-A0 stopped because N3-0 subscription planning found N2 scope contract blockers",
            expected="N3-0 subscription plan P0=0",
            actual=f"P0={(subscription_report.get('quality') or {}).get('p0_count')}",
            details={"n2_handoff_prompt": prompt},
        )
    ]
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": "N3-A0",
        "plan_mode": "previous_day_minute_preload_dry_run",
        "mode": "dry_run",
        "source_condition_run_id": subscription_report.get("source_condition_run_id"),
        "source_trade_date": subscription_report.get("source_trade_date"),
        "for_trade_date": subscription_report.get("for_trade_date"),
        "prev_trade_date": subscription_report.get("prev_trade_date"),
        "source_subscription_plan": {
            "passed": subscription_report.get("passed"),
            "blocked": subscription_report.get("blocked"),
            "p0_count": (subscription_report.get("quality") or {}).get("p0_count"),
            "blocking_items": [
                item
                for item in (subscription_report.get("quality") or {}).get("items", [])
                if item.get("status") == "failed"
            ],
        },
        "previous_day_minute_subscription_count": 0,
        "previous_day_minute_object_count": 0,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blocked": True,
        "execute_ready": False,
        "n2_scope_error": True,
        "n2_handoff_prompt": prompt,
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


def format_n2_handoff_prompt(subscription_report: Mapping[str, Any]) -> str:
    failed_items = [
        item
        for item in (subscription_report.get("quality") or {}).get("items", [])
        if item.get("status") == "failed"
    ]
    evidence = "; ".join(
        f"{item.get('gate_code')}: expected={item.get('expected_value')} actual={item.get('actual_value')}"
        for item in failed_items[:10]
    )
    return "\n".join(
        [
            "blocked_by_layer=N2_condition",
            "source_layer=N3_market_data",
            f"source_condition_run_id={subscription_report.get('source_condition_run_id')}",
            f"for_trade_date={subscription_report.get('for_trade_date')}",
            f"证据：{evidence or 'N3-0 subscription plan P0 failed.'}",
            "建议下一步：请在 N2 会话修复 active condition run / minute_target_scope 合同，使 scope 全部来自 condition_pool、previous_day_minute_date=prev_trade_date、trace 字段完整，然后重新交给 N3。",
            "禁止本层继续做：N3 不修改 condition_basis / condition_pool / minute_target_scope，不重新计算条件，不绕过 scope 拉行情。",
        ]
    )


def format_previous_day_minute_preload_summary(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    return "\n".join(
        [
            "previous-day minute preload dry-run",
            f"  market_data_run_id={report.get('market_data_run_id')}",
            f"  source_condition_run_id={report.get('source_condition_run_id')}",
            f"  source_trade_date={report.get('source_trade_date')}",
            f"  for_trade_date={report.get('for_trade_date')}",
            f"  prev_trade_date={report.get('prev_trade_date')}",
            f"  expected_previous_day_minute_date={report.get('expected_previous_day_minute_date')}",
            f"  previous_day_minute_date_counts={report.get('previous_day_minute_date_counts')}",
            f"  previous_day_minute_subscription_count={report.get('previous_day_minute_subscription_count')}",
            f"  previous_day_minute_object_count={report.get('previous_day_minute_object_count')}",
            f"  object_count_by_asset={report.get('previous_day_minute_object_count_by_asset_kind')}",
            f"  estimated_minute_bar_row_count={report.get('estimated_minute_bar_row_count')}",
            f"  preload_pull_plan_row_count={report.get('preload_pull_plan_row_count')}",
            f"  estimated_write_tables={report.get('estimated_write_tables')}",
            f"  event_outbox_write_planned={report.get('event_outbox_write_planned')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
            f"  blocked={report.get('blocked')} execute_ready={report.get('execute_ready')} n2_scope_error={report.get('n2_scope_error')} n3_subscription_error={report.get('n3_subscription_error')}",
            "  read_only_database_checks=true will_execute_sql=false migration_executed=false",
            "  market_data_pulled=false market_data_fact_written=false event_outbox_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


def format_previous_day_minute_preload_markdown(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    side_effects = report.get("side_effects") or {}
    source_plan = report.get("source_subscription_plan") or {}
    lines = [
        "# N3-A0 Previous-Day Minute Preload Dry-Run",
        "",
        "## Result",
        "",
        f"- market_data_run_id: `{report.get('market_data_run_id')}`",
        f"- source_condition_run_id: `{report.get('source_condition_run_id')}`",
        f"- source_trade_date: `{report.get('source_trade_date')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- prev_trade_date / data_trade_date: `{report.get('prev_trade_date')}`",
        f"- expected_previous_day_minute_date: `{report.get('expected_previous_day_minute_date')}`",
        f"- blocked: `{report.get('blocked')}`",
        f"- execute_ready: `{report.get('execute_ready')}`",
        f"- n2_scope_error: `{report.get('n2_scope_error')}`",
        f"- n3_subscription_error: `{report.get('n3_subscription_error')}`",
        f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
        "",
        "## Subscription Input",
        "",
        f"- persisted N3-6 passed: `{source_plan.get('passed')}`",
        f"- market_data_run_id: `{source_plan.get('market_data_run_id')}`",
        f"- source_scope_row_count: `{source_plan.get('source_scope_row_count')}`",
        f"- candidate_row_count: `{source_plan.get('candidate_row_count')}`",
        f"- subscription_row_count: `{source_plan.get('subscription_row_count')}`",
        f"- subscription_object_count: `{source_plan.get('subscription_object_count')}`",
        f"- required_data_kind_counts: `{source_plan.get('required_data_kind_counts')}`",
        f"- dedup_ratio: `{source_plan.get('dedup_ratio')}`",
        "",
        "## Preload Plan",
        "",
        f"- previous_day_minute_subscription_count: `{report.get('previous_day_minute_subscription_count')}`",
        f"- previous_day_minute_object_count: `{report.get('previous_day_minute_object_count')}`",
        f"- previous_day_minute_object_count_by_asset_kind: `{report.get('previous_day_minute_object_count_by_asset_kind')}`",
        f"- previous_day_minute_date_counts: `{report.get('previous_day_minute_date_counts')}`",
        f"- expected_minute_bar_count_per_object: `{report.get('expected_minute_bar_count_per_object')}`",
        f"- estimated_minute_bar_row_count: `{report.get('estimated_minute_bar_row_count')}`",
        f"- estimated_minute_bar_row_count_by_asset_kind: `{report.get('estimated_minute_bar_row_count_by_asset_kind')}`",
        f"- preload_pull_plan_row_count: `{report.get('preload_pull_plan_row_count')}`",
        "",
        "## Source Adapter Plan",
        "",
    ]
    for row in (report.get("source_adapter_plan") or {}).get("sample_rows", []):
        lines.append(
            f"- {row.get('asset_kind')}: adapter=`{row.get('adapter_name')}` "
            f"subscriptions=`{row.get('subscription_count')}` objects=`{row.get('object_count')}` "
            f"previous_day_minute_date=`{row.get('previous_day_minute_date')}` "
            f"expected_minute_bar_rows=`{row.get('expected_minute_bar_rows')}`"
        )
    lines.extend(
        [
            "",
            "## Estimated Write Tables",
            "",
            f"- schema_path: `{report.get('schema_path')}`",
            f"- estimated_write_tables: `{report.get('estimated_write_tables')}`",
            f"- estimated_write_tables_by_asset_kind: `{report.get('estimated_write_tables_by_asset_kind')}`",
            f"- event_outbox_write_planned: `{report.get('event_outbox_write_planned')}`",
            f"- generated_event_types: `{report.get('generated_event_types')}`",
        ]
    )
    lines.extend(
        [
        "",
        "## Quality Items",
        "",
        ]
    )
    for item in quality.get("items", []):
        lines.append(
            f"- {item.get('severity')} {item.get('status')} {item.get('gate_code')}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- old_system_touched: `{side_effects.get('old_system_touched')}`",
            f"- migration_executed: `{side_effects.get('migration_executed')}`",
            f"- writes_performed: `{side_effects.get('writes_performed')}`",
            f"- market_data_pulled: `{side_effects.get('market_data_pulled')}`",
            f"- market_data_fact_written: `{side_effects.get('market_data_fact_written')}`",
            f"- event_outbox_written: `{side_effects.get('event_outbox_written')}`",
            f"- downstream_layers_touched: `{side_effects.get('downstream_layers_touched')}`",
            f"- worker_started: `{side_effects.get('worker_started')}`",
            "",
            "## Rollback",
            "",
            "No database rows were written in N3-A0. Rollback is deleting this report and the newly added dry-run code/report files.",
            "",
        ]
    )
    if report.get("n2_handoff_prompt"):
        lines.extend(["## N2 Handoff Prompt", "", "```text", str(report["n2_handoff_prompt"]), "```", ""])
    return "\n".join(lines)


def read_schema_text(path: str = DEFAULT_MARKET_FACT_SCHEMA_PATH) -> str:
    return Path(path).read_text(encoding="utf-8")
