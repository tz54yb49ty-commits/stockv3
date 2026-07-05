"""N3-B0 realtime daily snapshot run-once dry-run planner.

This module reads persisted N3 subscription/pull-plan control rows and the
N3-A1 previous-day preload status. It does not call market data adapters,
write snapshot facts, write common_event_outbox, or start workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.preload_plan import (
    REALTIME_SNAPSHOT_TABLES,
    build_persisted_subscription_report,
    normalize_db_row,
)
from ashare_v3.market.subscription_plan import ADAPTER_NAMES, ASSET_KINDS, rows_section


DEFAULT_N3_B0_MARKDOWN_REPORT_PATH = "docs/N3_B0_REALTIME_DAILY_SNAPSHOT_DRY_RUN_REPORT.md"
DEFAULT_N3_B0_JSON_REPORT_PATH = "docs/N3_B0_realtime_daily_snapshot_dry_run.json"
REQUIRED_DATA_KIND = "realtime_daily_snapshot"
SNAPSHOT_EVENT_TYPES = (
    "MarketSnapshotUpdated",
    "MarketDataDelayed",
    "MarketDataMissing",
    "MarketDisplaySnapshotUpdated",
)


def build_realtime_daily_snapshot_dry_run(
    *,
    dsn: str,
    market_data_run_id: str,
    previous_day_preload_run_id: str | None = None,
    include_rows: bool = True,
    writes_outbox: bool = True,
) -> dict[str, Any]:
    subscription_report = build_realtime_subscription_report(
        dsn=dsn,
        market_data_run_id=market_data_run_id,
    )
    preload_audit = build_previous_day_preload_audit(
        dsn=dsn,
        preload_run_id=previous_day_preload_run_id,
    )
    subscriptions = realtime_snapshot_subscriptions(subscription_report)
    pull_batches = build_realtime_snapshot_pull_batches(
        subscription_report=subscription_report,
        subscriptions=subscriptions,
        persisted_pull_plans=(subscription_report.get("realtime_snapshot_pull_plan") or {}).get("rows") or [],
        writes_outbox=writes_outbox,
    )
    quality_items = build_realtime_snapshot_quality_items(
        subscription_report=subscription_report,
        subscriptions=subscriptions,
        pull_batches=pull_batches,
        preload_audit=preload_audit,
    )
    severity_counts = count_quality_severities(quality_items)
    object_keys = {(row["asset_kind"], row["identity_key"]) for row in subscriptions}
    object_counts_by_asset = asset_counts_by_asset(Counter(row["asset_kind"] for row in subscriptions))
    expected_snapshot_rows_by_asset = {asset_kind: object_counts_by_asset[asset_kind] for asset_kind in ASSET_KINDS}
    estimated_write_tables_by_asset = {
        asset_kind: {"snapshot_fact_table": REALTIME_SNAPSHOT_TABLES[asset_kind]}
        for asset_kind in ASSET_KINDS
    }
    return {
        "stage": "N3-B0",
        "layer_role": "N3_market_data",
        "plan_mode": "realtime_daily_snapshot_run_once_dry_run",
        "mode": "dry_run",
        "market_data_run_id": market_data_run_id,
        "source_condition_run_id": subscription_report.get("source_condition_run_id"),
        "source_trade_date": subscription_report.get("source_trade_date"),
        "for_trade_date": subscription_report.get("for_trade_date"),
        "prev_trade_date": subscription_report.get("prev_trade_date"),
        "required_data_kind": REQUIRED_DATA_KIND,
        "snapshot_subscription_count": len(subscriptions),
        "snapshot_object_count": len(object_keys),
        "snapshot_object_count_by_asset_kind": object_counts_by_asset,
        "expected_snapshot_rows": len(object_keys),
        "expected_snapshot_rows_by_asset_kind": expected_snapshot_rows_by_asset,
        "source_subscription_plan": {
            "market_data_run_id": subscription_report.get("market_data_run_id"),
            "source_scope_row_count": subscription_report.get("source_scope_row_count"),
            "candidate_row_count": subscription_report.get("candidate_row_count"),
            "subscription_row_count": subscription_report.get("subscription_row_count"),
            "subscription_object_count": subscription_report.get("subscription_object_count"),
            "required_data_kind_counts": subscription_report.get("required_data_kind_counts"),
            "dedup_ratio": subscription_report.get("dedup_ratio"),
            "p0_count": (subscription_report.get("quality") or {}).get("p0_count"),
            "passed": subscription_report.get("passed"),
        },
        "previous_day_preload_audit": preload_audit,
        "source_adapter_plan": rows_section(pull_batches, include_rows=include_rows),
        "estimated_write_tables": sorted(
            table_name
            for tables in estimated_write_tables_by_asset.values()
            for table_name in tables.values()
        ),
        "estimated_write_tables_by_asset_kind": estimated_write_tables_by_asset,
        "expected_event_contract": build_snapshot_execute_event_contract(writes_outbox=writes_outbox),
        "market_display_event_contract": build_market_display_event_contract(writes_outbox=writes_outbox),
        "writes_outbox": bool(writes_outbox),
        "event_outbox_write_planned_in_dry_run": False,
        "event_outbox_write_required_in_execute": bool(writes_outbox),
        "generated_event_types_for_execute": list(SNAPSHOT_EVENT_TYPES) if writes_outbox else [],
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blocked": severity_counts["P0"] > 0,
        "execute_ready_for_preflight": severity_counts["P0"] == 0,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "realtime_snapshot_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def build_realtime_subscription_report(*, dsn: str, market_data_run_id: str) -> dict[str, Any]:
    report = build_persisted_subscription_report(dsn=dsn, market_data_run_id=market_data_run_id)
    if report.get("blocked"):
        return report
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        pull_plan_rows = fetch_realtime_pull_plan_rows(cur, market_data_run_id)
    report["realtime_snapshot_pull_plan"] = rows_section(pull_plan_rows, include_rows=True)
    return report


def fetch_realtime_pull_plan_rows(cur: psycopg.Cursor[dict[str, Any]], market_data_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT pull_plan_id, run_id, source_condition_run_id, for_trade_date,
               source_trade_date, prev_trade_date, asset_kind, required_data_kind,
               data_trade_date, adapter_name, subscription_count, object_count,
               subscription_ids_sample, subscription_refs_sample, identity_keys_sample,
               plan_status, execute_allowed, selected_reason, raw_json
        FROM common_market_data_pull_plan
        WHERE run_id = %s
          AND required_data_kind = 'realtime_daily_snapshot'
        ORDER BY asset_kind, data_trade_date, pull_plan_id
        """,
        (market_data_run_id,),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def realtime_snapshot_subscriptions(subscription_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = (subscription_report.get("market_data_subscription_dedup") or {}).get("rows") or []
    return [dict(row) for row in rows if row.get("required_data_kind") == REQUIRED_DATA_KIND]


def build_realtime_snapshot_pull_batches(
    *,
    subscription_report: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    persisted_pull_plans: Sequence[Mapping[str, Any]],
    writes_outbox: bool = True,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for subscription in subscriptions:
        key = (str(subscription.get("asset_kind")), str(subscription.get("data_trade_date")))
        groups.setdefault(key, []).append(subscription)
    pull_plan_by_key = {
        (str(row.get("asset_kind")), str(row.get("data_trade_date"))): row
        for row in persisted_pull_plans
    }
    rows: list[dict[str, Any]] = []
    for (asset_kind, trade_date), group in sorted(groups.items()):
        identity_keys = [row.get("identity_key") for row in group]
        persisted = pull_plan_by_key.get((asset_kind, trade_date), {})
        rows.append(
            {
                "snapshot_pull_plan_ref": f"dry_run:realtime_snapshot_pull:{len(rows) + 1}",
                "source_pull_plan_id": persisted.get("pull_plan_id"),
                "market_data_run_id": subscription_report.get("market_data_run_id"),
                "source_condition_run_id": subscription_report.get("source_condition_run_id"),
                "for_trade_date": subscription_report.get("for_trade_date"),
                "trade_date": trade_date,
                "asset_kind": asset_kind,
                "required_data_kind": REQUIRED_DATA_KIND,
                "adapter_name": persisted.get("adapter_name") or ADAPTER_NAMES[asset_kind],
                "subscription_count": len(group),
                "object_count": len(set(identity_keys)),
                "expected_snapshot_rows": len(set(identity_keys)),
                "target_snapshot_table": REALTIME_SNAPSHOT_TABLES[asset_kind],
                "estimated_write_tables": [REALTIME_SNAPSHOT_TABLES[asset_kind]],
                "execute_contract": {
                    "write_snapshot_fact": True,
                    "write_market_snapshot_updated_outbox_same_transaction": bool(writes_outbox),
                    "writes_outbox": bool(writes_outbox),
                    "dry_run_only": True,
                    "adapter_call_planned_in_dry_run": False,
                },
                "persisted_pull_plan": {
                    "pull_plan_id": persisted.get("pull_plan_id"),
                    "subscription_count": persisted.get("subscription_count"),
                    "object_count": persisted.get("object_count"),
                    "execute_allowed": persisted.get("execute_allowed"),
                    "plan_status": persisted.get("plan_status"),
                },
                "identity_keys_sample": identity_keys[:20],
                "execute_allowed": False,
                "selected_reason": "N3-B0 dry-run only; realtime snapshot adapter calls and writes require N3-B1",
            }
        )
    return rows


def build_previous_day_preload_audit(*, dsn: str, preload_run_id: str | None) -> dict[str, Any]:
    if not preload_run_id:
        return {
            "preload_run_id": None,
            "run_present": False,
            "status": None,
            "p0_count": 0,
            "p1_count": 0,
            "p2_count": 0,
            "status_counts_by_asset_kind": asset_status_counts_template(),
            "missing_object_count": 0,
            "missing_samples": [],
        }
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, status, p0_count, p1_count, p2_count,
                   market_data_pulled, market_data_fact_written,
                   downstream_layers_touched, worker_started
            FROM common_market_data_run
            WHERE run_id = %s
            """,
            (preload_run_id,),
        )
        run_row = cur.fetchone()
        if run_row is None:
            return {
                "preload_run_id": preload_run_id,
                "run_present": False,
                "status": None,
                "p0_count": 0,
                "p1_count": 0,
                "p2_count": 0,
                "status_counts_by_asset_kind": asset_status_counts_template(),
                "missing_object_count": 0,
                "missing_samples": [],
            }
        run = normalize_db_row(run_row)
        status_counts: dict[str, dict[str, int]] = {}
        missing_samples: list[dict[str, Any]] = []
        for asset_kind in ASSET_KINDS:
            table_name = f"{asset_kind}_previous_day_minute_preload_status"
            identity_column = f"{asset_kind}_identity_key"
            cur.execute(
                f"""
                SELECT status, count(*)::bigint AS row_count
                FROM {table_name}
                WHERE run_id = %s
                GROUP BY status
                ORDER BY status
                """,
                (preload_run_id,),
            )
            counts = {str(row["status"]): int(row["row_count"]) for row in cur.fetchall()}
            status_counts[asset_kind] = {
                "passed": counts.get("passed", 0),
                "partial": counts.get("partial", 0),
                "missing": counts.get("missing", 0),
                "failed": counts.get("failed", 0),
                "total": sum(counts.values()),
            }
            cur.execute(
                f"""
                SELECT {identity_column} AS identity_key, code, display_code, name,
                       actual_bar_count, missing_bar_count, status
                FROM {table_name}
                WHERE run_id = %s
                  AND status <> 'passed'
                ORDER BY {identity_column}
                LIMIT 20
                """,
                (preload_run_id,),
            )
            missing_samples.extend(normalize_db_row(row) | {"asset_kind": asset_kind} for row in cur.fetchall())
    return {
        "preload_run_id": preload_run_id,
        "run_present": True,
        "status": run.get("status"),
        "p0_count": int(run.get("p0_count") or 0),
        "p1_count": int(run.get("p1_count") or 0),
        "p2_count": int(run.get("p2_count") or 0),
        "market_data_pulled": bool(run.get("market_data_pulled")),
        "market_data_fact_written": bool(run.get("market_data_fact_written")),
        "downstream_layers_touched": bool(run.get("downstream_layers_touched")),
        "worker_started": bool(run.get("worker_started")),
        "status_counts_by_asset_kind": status_counts,
        "missing_object_count": sum(counts["missing"] + counts["partial"] + counts["failed"] for counts in status_counts.values()),
        "missing_samples": missing_samples,
    }


def build_realtime_snapshot_quality_items(
    *,
    subscription_report: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_batches: Sequence[Mapping[str, Any]],
    preload_audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    subscription_p0 = int((subscription_report.get("quality") or {}).get("p0_count") or 0)
    subscription_p1 = int((subscription_report.get("quality") or {}).get("p1_count") or 0)
    expected_asset_kinds = {asset_kind for asset_kind in ASSET_KINDS if any(row.get("asset_kind") == asset_kind for row in subscriptions)}
    pull_plan_asset_kinds = {str(row.get("asset_kind")) for row in pull_batches}
    missing_asset_pull_plans = sorted(
        (expected_asset_kinds - pull_plan_asset_kinds)
        | {
            str(row.get("asset_kind"))
            for row in pull_batches
            if not row.get("source_pull_plan_id")
        }
    )
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
        if not row.get("subscription_id") or not row.get("source_scope_ids") or not row.get("source_condition_pool_ids")
    ]
    estimated_tables = [table for row in pull_batches for table in row.get("estimated_write_tables", [])]
    physical_errors = [
        row.get("target_snapshot_table")
        for row in pull_batches
        if not str(row.get("target_snapshot_table") or "").startswith(f"{row.get('asset_kind')}_")
    ]
    runtime_hits = sorted({table for table in estimated_tables if "_runtime" in str(table)})
    user_event_hits = sorted(event_type for event_type in SNAPSHOT_EVENT_TYPES if event_type.startswith("User"))
    unsupported_event_hits = sorted(
        set(SNAPSHOT_EVENT_TYPES)
        - {"MarketSnapshotUpdated", "MarketDataDelayed", "MarketDataMissing", "MarketDisplaySnapshotUpdated"}
    )
    preload_p0 = int(preload_audit.get("p0_count") or 0)
    preload_missing = int(preload_audit.get("missing_object_count") or 0)
    items = [
        quality_item(
            "P0",
            "passed" if subscription_report.get("passed") and subscription_p0 == 0 else "failed",
            "n3_b0_subscription_run_clean",
            "N3-B0 requires a clean persisted N3-6 subscription run",
            expected="N3-6 subscription run passed and P0=0",
            actual=f"passed={subscription_report.get('passed')} p0={subscription_p0}",
        ),
        quality_item(
            "P1",
            "warning" if subscription_p1 > 0 else "passed",
            "n3_b0_subscription_run_p1_carried",
            "N3-B0 carries non-blocking P1 items from the N3-6 subscription run",
            expected="0",
            actual=str(subscription_p1),
        ),
        quality_item(
            "P0",
            "passed" if subscriptions else "failed",
            "realtime_snapshot_subscriptions_present",
            "N3-B0 requires realtime_daily_snapshot subscriptions",
            expected=">0",
            actual=str(len(subscriptions)),
        ),
        quality_item(
            "P0",
            "passed" if not missing_trace else "failed",
            "realtime_snapshot_subscription_trace_present",
            "snapshot subscriptions must preserve subscription_id, source_scope_ids, and source_condition_pool_ids",
            expected="trace present",
            actual="present" if not missing_trace else ",".join(str(item) for item in missing_trace[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not missing_asset_pull_plans else "failed",
            "realtime_snapshot_pull_plan_asset_coverage",
            "N3-B0 requires a realtime snapshot pull plan for each asset kind present in subscriptions",
            expected="pull plan for each asset kind in subscriptions",
            actual="covered" if not missing_asset_pull_plans else ",".join(missing_asset_pull_plans),
        ),
        quality_item(
            "P0",
            "passed" if not count_mismatches else "failed",
            "realtime_snapshot_pull_plan_counts_match_subscriptions",
            "persisted realtime pull_plan counts must match subscription rows",
            expected="counts match",
            actual="matched" if not count_mismatches else ",".join(str(item) for item in count_mismatches),
        ),
        quality_item(
            "P0",
            "passed" if not execute_allowed_plans else "failed",
            "realtime_snapshot_pull_plan_execute_not_allowed_in_b0",
            "N3-B0 dry-run must not mark persisted pull plans executable",
            expected="execute_allowed=false",
            actual="false" if not execute_allowed_plans else ",".join(str(item) for item in execute_allowed_plans[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not physical_errors else "failed",
            "realtime_snapshot_estimated_tables_physically_separated",
            "N3-B0 estimated write tables must be physically separated by stock/index/board",
            expected="stock/index/board target table prefixes",
            actual="separated" if not physical_errors else ",".join(str(item) for item in physical_errors),
        ),
        quality_item(
            "P0",
            "passed" if not runtime_hits else "failed",
            "n3_b0_no_runtime_table_names",
            "N3-B0 must not use *_runtime formal table names",
            expected="no *_runtime target table",
            actual="none" if not runtime_hits else ",".join(runtime_hits),
        ),
        quality_item(
            "P0",
            "passed" if not user_event_hits and not unsupported_event_hits else "failed",
            "n3_b0_event_contract_allowed_n3_events",
            "N3-B0 execute contract must use allowed N3 events and no User* names",
            expected="MarketSnapshotUpdated/MarketDataDelayed/MarketDataMissing/MarketDisplaySnapshotUpdated",
            actual="allowed" if not user_event_hits and not unsupported_event_hits else ",".join(user_event_hits + unsupported_event_hits),
        ),
        quality_item(
            "P0",
            "passed" if preload_p0 == 0 else "failed",
            "n3_b0_preload_p0_zero",
            "N3-B0 can carry preload P1/P2, but should not proceed if N3-A1 has P0",
            expected="0",
            actual=str(preload_p0),
        ),
        quality_item(
            "P1",
            "warning" if preload_missing > 0 else "passed",
            "n3_b0_preload_missing_carried_non_blocking",
            "N3-A1 previous-day missing objects are carried as non-blocking context for realtime snapshot dry-run",
            expected="0",
            actual=str(preload_missing),
            details={"samples": preload_audit.get("missing_samples") or []},
        ),
        quality_item(
            "P0",
            "passed",
            "n3_b0_no_market_pull_or_write",
            "N3-B0 must not pull market data or write snapshot/outbox/facts",
            expected="read-only dry-run",
            actual="read-only dry-run",
        ),
    ]
    return items


def build_snapshot_execute_event_contract(*, writes_outbox: bool = True) -> dict[str, Any]:
    if not writes_outbox:
        return {
            "stage": "N3-B1-preflight/B1",
            "fact_tables": REALTIME_SNAPSHOT_TABLES,
            "writes_outbox": False,
            "transaction_contract": [
                "BEGIN",
                "UPSERT stock/index/board_realtime_daily_snapshot",
                "COMMIT",
            ],
            "disabled_outbox_events": list(SNAPSHOT_EVENT_TYPES),
            "market_snapshot_updated": {
                "event_type": "MarketSnapshotUpdated",
                "generated": False,
                "reason": "current B1 contract sets writes_outbox=false",
            },
            "quality_events": [],
            "b0_side_effects": {
                "market_data_pulled": False,
                "snapshot_written": False,
                "event_outbox_written": False,
            },
        }
    return {
        "stage": "N3-B1-preflight/B1",
        "fact_tables": REALTIME_SNAPSHOT_TABLES,
        "writes_outbox": True,
        "transaction_contract": [
            "BEGIN",
            "UPSERT stock/index/board_realtime_daily_snapshot",
            "INSERT common_event_outbox MarketSnapshotUpdated",
            "COMMIT",
        ],
        "market_snapshot_updated": {
            "event_type": "MarketSnapshotUpdated",
            "payload_required_fields": [
                "subscription_id",
                "pull_plan_id",
                "run_id",
                "source_adapter",
                "data_quality_status",
                "snapshot_id",
            ],
            "dedup_key": "asset_kind + identity_key + trade_date + snapshot_time + source_adapter",
            "partition_key": "identity_key",
            "drives": "N4 trigger primary input",
        },
        "quality_events": [
            {
                "event_type": "MarketDataDelayed",
                "fact_source": "common_market_data_quality_item / pull status",
                "payload_required_fields": [
                    "subscription_id",
                    "pull_plan_id",
                    "run_id",
                    "source_adapter",
                    "data_quality_status",
                    "quality_item_id",
                ],
            },
            {
                "event_type": "MarketDataMissing",
                "fact_source": "common_market_data_quality_item / pull status",
                "payload_required_fields": [
                    "subscription_id",
                    "pull_plan_id",
                    "run_id",
                    "source_adapter",
                    "data_quality_status",
                    "quality_item_id",
                ],
            },
        ],
        "b0_side_effects": {
            "market_data_pulled": False,
            "snapshot_written": False,
            "event_outbox_written": False,
        },
    }


def build_market_display_event_contract(*, writes_outbox: bool = True) -> dict[str, Any]:
    return {
        "event_type": "MarketDisplaySnapshotUpdated",
        "generated": bool(writes_outbox),
        "not_user_event": True,
        "trigger_policy": "low-frequency display material only",
        "voice_policy": "does_not_trigger_voice",
        "downstream": "N6 may consume into user_market_projection later",
        "payload_required_fields": [
            "subscription_id",
            "pull_plan_id",
            "run_id",
            "source_adapter",
            "data_quality_status",
            "snapshot_id",
        ]
        if writes_outbox
        else [],
        "b0_side_effects": {
            "event_outbox_written": False,
            "downstream_layers_touched": False,
        },
    }


def asset_counts_by_asset(counter: Counter[str]) -> dict[str, int]:
    return {asset_kind: int(counter.get(asset_kind, 0)) for asset_kind in ASSET_KINDS}


def asset_status_counts_template() -> dict[str, dict[str, int]]:
    return {
        asset_kind: {"passed": 0, "partial": 0, "missing": 0, "failed": 0, "total": 0}
        for asset_kind in ASSET_KINDS
    }


def format_realtime_daily_snapshot_summary(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    return "\n".join(
        [
            "realtime daily snapshot dry-run",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  market_data_run_id={report['market_data_run_id']}",
            f"  source_condition_run_id={report['source_condition_run_id']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  snapshot_subscription_count={report['snapshot_subscription_count']}",
            f"  snapshot_object_count={report['snapshot_object_count']}",
            f"  object_count_by_asset={report['snapshot_object_count_by_asset_kind']}",
            f"  expected_snapshot_rows={report['expected_snapshot_rows']}",
            f"  source_adapter_plan_rows={report['source_adapter_plan']['row_count']}",
            f"  estimated_write_tables={report['estimated_write_tables']}",
            f"  writes_outbox={str(report.get('writes_outbox')).lower()}",
            f"  execute_events={report['generated_event_types_for_execute']}",
            f"  preload_missing_carried={report['previous_day_preload_audit']['missing_object_count']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            f"  blocked={report['blocked']} execute_ready_for_preflight={report['execute_ready_for_preflight']}",
            "  market_data_pulled=false realtime_snapshot_written=false event_outbox_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


def format_realtime_daily_snapshot_markdown(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        "# N3-B0 Realtime Daily Snapshot Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- stage: `{report['stage']}`",
        f"- layer_role: `{report['layer_role']}`",
        f"- market_data_run_id: `{report['market_data_run_id']}`",
        f"- source_condition_run_id: `{report['source_condition_run_id']}`",
        f"- for_trade_date: `{report['for_trade_date']}`",
        f"- snapshot_subscription_count: `{report['snapshot_subscription_count']}`",
        f"- snapshot_object_count: `{report['snapshot_object_count']}`",
        f"- expected_snapshot_rows: `{report['expected_snapshot_rows']}`",
        f"- writes_outbox: `{str(report.get('writes_outbox')).lower()}`",
        f"- event_outbox_write_planned_in_dry_run: `{report['event_outbox_write_planned_in_dry_run']}`",
        f"- event_outbox_write_required_in_execute: `{report['event_outbox_write_required_in_execute']}`",
        f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
        "",
        "## Object Counts",
        "",
    ]
    for asset_kind, count in report["snapshot_object_count_by_asset_kind"].items():
        lines.append(f"- {asset_kind}: `{count}`")
    lines.extend(["", "## Adapter Plan", ""])
    for row in (report["source_adapter_plan"] or {}).get("rows") or []:
        lines.append(
            f"- {row['asset_kind']}: adapter=`{row['adapter_name']}` "
            f"objects=`{row['object_count']}` expected_snapshot_rows=`{row['expected_snapshot_rows']}` "
            f"target=`{row['target_snapshot_table']}`"
        )
    lines.extend(["", "## Event Contract", ""])
    for event_type in report["generated_event_types_for_execute"]:
        lines.append(f"- `{event_type}`")
    lines.extend(["", "## Previous-Day Preload Context", ""])
    audit = report["previous_day_preload_audit"]
    lines.append(f"- preload_run_id: `{audit.get('preload_run_id')}`")
    lines.append(f"- status: `{audit.get('status')}`")
    lines.append(f"- missing_object_count: `{audit.get('missing_object_count')}`")
    if audit.get("missing_samples"):
        sample_text = ", ".join(str(row.get("identity_key")) for row in audit["missing_samples"][:20])
        lines.append(f"- missing_samples: `{sample_text}`")
    lines.extend(["", "## Quality", ""])
    for item in quality["items"]:
        lines.append(
            f"- {item['severity']} {item['status']} {item['gate_code']}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(["", "## Boundary", ""])
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def write_report_files(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    write_text(markdown_path, format_realtime_daily_snapshot_markdown(report))
    write_text(json_path, json.dumps(json_safe(report), ensure_ascii=False, indent=2, default=str) + "\n")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
