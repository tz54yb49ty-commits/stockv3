"""N3 previous-day full-context expansion subscription scope patch.

This module plans and executes previous_day_minute_bar_1m control rows for
full-context expansion. Execute creates the parent market_data_run and quality
items before child control rows. It does not pull market data, write market
facts, write event infrastructure, or enter downstream layers.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import (
    audited_n3_market_execute_connect,
    audited_n3_market_readonly_plan_connect,
)
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.full_context_expansion_subscription_plan import (
    BARS_PER_OBJECT,
    EXPECTED_CONTEXT_ROWS_BY_ASSET,
    EXPECTED_OBJECTS_BY_ASSET,
    EXPANSION_SUBSCRIPTION_RUN_ID,
    FOR_TRADE_DATE,
    SOURCE_CONDITION_RUN_ID,
    unique_preserve_order,
)
from ashare_v3.market.preload_plan import normalize_db_row
from ashare_v3.market.subscription_execute import (
    insert_quality_items,
    insert_pull_plans,
    insert_subscription_candidates,
    insert_subscriptions,
    utc_now_iso,
    write_json,
    write_text,
)
from ashare_v3.market.subscription_plan import ADAPTER_NAMES, ASSET_KINDS, rows_section


PREVIOUS_DAY_MINUTE_DATE = "20260602"
PREVIOUS_DAY_REQUIRED_DATA_KIND = "previous_day_minute_bar_1m"
SOURCE_REQUIRED_DATA_KIND = "minute_bar_1m"
EXPECTED_ROWS_BY_ASSET = {
    asset: count * BARS_PER_OBJECT for asset, count in EXPECTED_OBJECTS_BY_ASSET.items()
}

DEFAULT_DRY_RUN_JSON_PATH = (
    "docs/N3_previous_day_full_context_expansion_subscription_scope_20260603_dry_run_report.json"
)
DEFAULT_DRY_RUN_MD_PATH = (
    "docs/N3_PREVIOUS_DAY_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE_20260603_DRY_RUN_REPORT.md"
)
DEFAULT_EXECUTE_JSON_PATH = (
    "docs/N3_previous_day_full_context_expansion_subscription_scope_20260603_execute_report.json"
)
DEFAULT_EXECUTE_MD_PATH = (
    "docs/N3_PREVIOUS_DAY_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE_20260603_EXECUTE_REPORT.md"
)
DEFAULT_ROLLBACK_SQL_PATH = "sql/N3_previous_day_full_context_expansion_subscription_scope_20260603_rollback.sql"


def build_previous_day_full_context_expansion_scope_from_db(
    *,
    dsn: str,
    expansion_run_id: str = EXPANSION_SUBSCRIPTION_RUN_ID,
    include_rows: bool = True,
) -> dict[str, Any]:
    """Read existing expansion rows and build the additive previous-day scope plan."""

    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        target_db = fetch_target_db_proof(cur)
        run_row = fetch_market_data_run(cur, expansion_run_id)
        minute_candidates = fetch_subscription_candidates(cur, expansion_run_id, SOURCE_REQUIRED_DATA_KIND)
        existing_previous_day_counts = fetch_existing_previous_day_scope_counts(cur, expansion_run_id)
        baseline_refs = fetch_scope_ref_counts(cur, expansion_run_id)
        event_global_counts = fetch_event_global_counts(cur)

    candidates = derive_previous_day_expansion_candidates(
        expansion_run_id=expansion_run_id,
        minute_candidate_rows=minute_candidates,
        previous_day_minute_date=PREVIOUS_DAY_MINUTE_DATE,
    )
    subscriptions = deduplicate_previous_day_expansion_candidates(
        expansion_run_id=expansion_run_id,
        candidates=candidates,
    )
    pull_plan_rows = build_previous_day_expansion_pull_plan_rows(
        expansion_run_id=expansion_run_id,
        subscriptions=subscriptions,
    )
    quality_items = build_quality_items(
        run_row=run_row,
        minute_candidates=minute_candidates,
        candidates=candidates,
        subscriptions=subscriptions,
        pull_plan_rows=pull_plan_rows,
        existing_previous_day_counts=existing_previous_day_counts,
        baseline_refs=baseline_refs,
    )
    severity_counts = count_quality_severities(quality_items)
    object_counts = object_count_by_asset_kind(subscriptions)
    candidate_counts = dict(sorted(Counter(row["asset_kind"] for row in candidates).items()))
    expected_rows_by_asset = {asset: int(object_counts.get(asset, 0)) * BARS_PER_OBJECT for asset in ASSET_KINDS}
    report = {
        "stage": "N3_PREVIOUS_DAY_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE",
        "layer_role": "N3_market_data",
        "mode": "dry_run",
        "result": "SCOPE_DRY_RUN_PASS" if severity_counts["P0"] == 0 else "SCOPE_BLOCKED",
        "market_data_run_id": expansion_run_id,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_trade_date": PREVIOUS_DAY_MINUTE_DATE,
        "for_trade_date": FOR_TRADE_DATE,
        "prev_trade_date": PREVIOUS_DAY_MINUTE_DATE,
        "previous_day_minute_date": PREVIOUS_DAY_MINUTE_DATE,
        "target_db_proof": dict(target_db),
        "existing_run_status": normalize_mapping(run_row) if run_row else None,
        "source_minute_candidate_count": len(minute_candidates),
        "source_minute_candidate_count_by_asset_kind": dict(sorted(Counter(row["asset_kind"] for row in minute_candidates).items())),
        "candidate_row_count": len(candidates),
        "candidate_row_count_by_asset_kind": candidate_counts,
        "subscription_row_count": len(subscriptions),
        "subscription_object_count": len(subscriptions),
        "object_count_by_asset_kind": object_counts,
        "pull_plan_row_count": len(pull_plan_rows),
        "required_data_kind": PREVIOUS_DAY_REQUIRED_DATA_KIND,
        "expected_rows_by_asset_kind": expected_rows_by_asset,
        "expected_rows_total": sum(expected_rows_by_asset.values()),
        "existing_previous_day_scope_counts": existing_previous_day_counts,
        "scope_conflict": any(int(value) != 0 for value in existing_previous_day_counts.values()),
        "minute_bar_scope_conflict": False,
        "conflict_summary": {
            "existing_minute_bar_1m_rows_preserved": len(minute_candidates),
            "existing_previous_day_minute_bar_1m_rows": existing_previous_day_counts,
            "strategy": "append missing previous_day_minute_bar_1m rows only; do not overwrite existing minute_bar_1m scope",
        },
        "market_data_subscription_candidate": rows_section(candidates, include_rows=include_rows),
        "market_data_subscription_dedup": rows_section(subscriptions, include_rows=include_rows),
        "market_data_pull_plan": rows_section(pull_plan_rows, include_rows=include_rows),
        "source_adapter_readiness": {
            "adapter_route_ready": True,
            "adapter_plan_by_asset": {
                asset: {
                    "adapter_name": ADAPTER_NAMES[asset],
                    "object_count": int(object_counts.get(asset, 0)),
                    "expected_rows": int(expected_rows_by_asset.get(asset, 0)),
                }
                for asset in ASSET_KINDS
            },
            "bj_index_quality_blocked": {
                "identity_keys": ["index:BJ:899050", "index:BJ:899601"],
                "policy": "explicit_quality_blocked_no_silent_fallback",
            },
        },
        "event_infra_ref_counts": baseline_refs,
        "event_infra_global_counts_read_only": event_global_counts,
        "write_scope": {
            "allowed": [
                "common_market_data_run",
                "common_market_data_quality_item",
                "common_market_data_subscription_candidate",
                "common_market_data_subscription",
                "common_market_data_pull_plan",
            ],
            "forbidden": [
                "stock/index/board_minute_bar_1m",
                "stock/index/board_previous_day_minute_preload_status",
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "N4/N5/N6",
                "worker",
                "old_system",
                "real_trade",
            ],
        },
        "rollback_sql": DEFAULT_ROLLBACK_SQL_PATH,
        "rollback_hard_fail_guard": True,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blocked": severity_counts["P0"] > 0,
        "passed": severity_counts["P0"] == 0,
        "read_only_database_checks": True,
        "side_effects": {
            "business_data_written": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
    }
    return report


def build_previous_day_full_context_expansion_scope_from_plan_path(
    *,
    expansion_plan_path: str,
    for_trade_date: str,
    source_trade_date: str,
    previous_trade_date: str,
    expansion_run_id: str,
    previous_day_expansion_run_id: str,
    dsn: str | None = None,
    include_rows: bool = True,
) -> dict[str, Any]:
    """Build a read-only previous-day scope plan from a reviewed PR1 expansion artifact."""

    path = Path(expansion_plan_path)
    if path.exists():
        expansion_plan_report: Mapping[str, Any] | None = json.loads(path.read_text(encoding="utf-8"))
    else:
        expansion_plan_report = None
    baseline = empty_previous_day_expansion_baseline()
    if dsn:
        with audited_n3_market_readonly_plan_connect(
            dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            baseline = fetch_previous_day_expansion_baseline(cur, previous_day_expansion_run_id)
    return build_previous_day_full_context_expansion_scope_from_plan_report(
        expansion_plan_report=expansion_plan_report,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        previous_trade_date=previous_trade_date,
        expansion_run_id=expansion_run_id,
        previous_day_expansion_run_id=previous_day_expansion_run_id,
        baseline=baseline,
        include_rows=include_rows,
    )


def build_previous_day_full_context_expansion_scope_from_plan_report(
    *,
    expansion_plan_report: Mapping[str, Any] | None,
    for_trade_date: str,
    source_trade_date: str,
    previous_trade_date: str,
    expansion_run_id: str,
    previous_day_expansion_run_id: str,
    baseline: Mapping[str, int] | None = None,
    include_rows: bool = True,
) -> dict[str, Any]:
    """Build previous-day expansion scope from PR1 expansion plan rows without database writes."""

    baseline = dict(baseline or empty_previous_day_expansion_baseline())
    identity_rows = extract_expansion_identity_rows(expansion_plan_report)
    candidates = derive_previous_day_expansion_candidates(
        expansion_run_id=previous_day_expansion_run_id,
        minute_candidate_rows=identity_rows,
        previous_day_minute_date=previous_trade_date,
    )
    subscriptions = deduplicate_previous_day_expansion_candidates(
        expansion_run_id=previous_day_expansion_run_id,
        candidates=candidates,
        previous_day_minute_date=previous_trade_date,
    )
    pull_plan_rows = build_previous_day_expansion_pull_plan_rows(
        expansion_run_id=previous_day_expansion_run_id,
        subscriptions=subscriptions,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        previous_day_minute_date=previous_trade_date,
    )
    quality_items = build_plan_artifact_quality_items(
        expansion_plan_report=expansion_plan_report,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        previous_trade_date=previous_trade_date,
        expansion_run_id=expansion_run_id,
        identity_rows=identity_rows,
        candidates=candidates,
        subscriptions=subscriptions,
        pull_plan_rows=pull_plan_rows,
        baseline=baseline,
    )
    severity_counts = count_quality_severities(quality_items)
    blockers = [
        item["gate_code"]
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") != "passed"
    ]
    asset_counts = object_count_by_asset_kind(subscriptions)
    candidate_counts = dict(sorted(Counter(row["asset_kind"] for row in candidates).items()))
    expected_rows_by_asset = {asset: int(asset_counts.get(asset, 0)) * BARS_PER_OBJECT for asset in ASSET_KINDS}
    report = {
        "stage": "N3_PREVIOUS_DAY_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE",
        "layer_role": "N3_market_data",
        "mode": "dry_run",
        "plan_source": "pr1_full_context_expansion_plan_artifact",
        "result": "SCOPE_DRY_RUN_PASS" if severity_counts["P0"] == 0 else "SCOPE_BLOCKED",
        "market_data_run_id": previous_day_expansion_run_id,
        "source_expansion_run_id": expansion_run_id,
        "source_condition_run_id": str((expansion_plan_report or {}).get("source_condition_run_id") or ""),
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "prev_trade_date": previous_trade_date,
        "previous_day_minute_date": previous_trade_date,
        "expansion_identity_count": len({(row["asset_kind"], row["identity_key"]) for row in identity_rows}),
        "expansion_identity_count_by_asset_kind": object_count_by_asset_kind(identity_rows),
        "candidate_row_count": len(candidates),
        "candidate_row_count_by_asset_kind": candidate_counts,
        "subscription_row_count": len(subscriptions),
        "previous_day_subscription_rows_planned": len(subscriptions),
        "subscription_object_count": len(subscriptions),
        "asset_count_by_asset_kind": asset_counts,
        "pull_plan_row_count": len(pull_plan_rows),
        "pull_plan_rows_planned": len(pull_plan_rows),
        "required_data_kind": PREVIOUS_DAY_REQUIRED_DATA_KIND,
        "expected_rows_by_asset_kind": expected_rows_by_asset,
        "expected_rows_total": sum(expected_rows_by_asset.values()),
        "previous_day_expansion_baseline": dict(baseline),
        "market_data_subscription_candidate": rows_section(candidates, include_rows=include_rows),
        "market_data_subscription_dedup": rows_section(subscriptions, include_rows=include_rows),
        "market_data_pull_plan": rows_section(pull_plan_rows, include_rows=include_rows),
        "write_scope": {
            "future_execute_allowed_write_tables": [
                "common_market_data_run",
                "common_market_data_quality_item",
                "common_market_data_subscription_candidate",
                "common_market_data_subscription",
                "common_market_data_pull_plan",
            ],
            "forbidden": [
                "stock/index/board_minute_target_scope",
                "stock/index/board_minute_bar_1m",
                "stock/index/board_realtime_daily_snapshot",
                "stock/index/board_action_confirmation_projection_metric",
                "common_trigger_state/match/outbox",
                "N4/N5/N6",
                "worker",
                "real_trade",
            ],
        },
        "rollback_sql": (
            "sql/"
            f"N3_previous_day_full_context_expansion_subscription_scope_{previous_trade_date}_for_{for_trade_date}_rollback.sql"
        ),
        "rollback_sql_generated": False,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blockers": blockers,
        "blocked": severity_counts["P0"] > 0,
        "passed": severity_counts["P0"] == 0,
        "read_only_database_checks": True,
        "side_effects": {
            "business_data_written": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
    }
    return report


def extract_expansion_identity_rows(expansion_plan_report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not expansion_plan_report:
        return []
    section = expansion_plan_report.get("market_data_subscription_dedup") or {}
    if not bool(section.get("rows_included")):
        return []
    rows = section.get("rows") or []
    output: list[dict[str, Any]] = []
    for row in rows:
        normalized = normalize_db_row(row)
        if normalized.get("required_data_kind") != SOURCE_REQUIRED_DATA_KIND:
            continue
        output.extend(expand_subscription_identity_trace_rows(normalized))
    return output


def expand_subscription_identity_trace_rows(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    if row.get("source_scope_table") and row.get("source_scope_id"):
        return [dict(row)]
    tables = list(row.get("source_scope_tables") or [])
    ids = list(row.get("source_scope_ids") or [])
    refs = list(row.get("source_scope_refs") or [])
    pool_ids = list(row.get("source_condition_pool_ids") or [])
    condition_keys = list(row.get("condition_keys") or [])
    directions = list(row.get("directions") or [])
    allowed_signal_types = list(row.get("allowed_signal_types") or [])
    if not ids:
        ids = [0]
    output: list[dict[str, Any]] = []
    for idx, scope_id in enumerate(ids):
        table = value_at_or_first(tables, idx, default=f"{row['asset_kind']}_minute_target_scope")
        output.append(
            {
                **dict(row),
                "source_scope_table": table,
                "source_scope_id": int(scope_id),
                "source_scope_ref": value_at_or_first(refs, idx, default=f"{table}:{int(scope_id)}"),
                "source_condition_pool_id": int(value_at_or_first(pool_ids, idx, default=0) or 0),
                "direction": value_at_or_first(directions, idx, default=(directions[0] if directions else "")),
                "condition_key": value_at_or_first(condition_keys, idx, default=(condition_keys[0] if condition_keys else "")),
                "allowed_signal_types": allowed_signal_types,
                "source_scope_required_flags": {
                    **dict(row.get("source_scope_required_flags") or {}),
                    "minute_required": True,
                    "full_context_expansion": True,
                },
            }
        )
    return output


def value_at_or_first(values: Sequence[Any], index: int, *, default: Any = None) -> Any:
    if index < len(values):
        return values[index]
    if values:
        return values[0]
    return default


def derive_previous_day_expansion_candidates(
    *,
    expansion_run_id: str,
    minute_candidate_rows: Sequence[Mapping[str, Any]],
    previous_day_minute_date: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in minute_candidate_rows:
        flags = dict(row.get("source_scope_required_flags") or {})
        flags["minute_required"] = False
        flags["previous_day_minute_required"] = True
        flags["full_context_expansion"] = True
        flags["full_context_previous_day_expansion"] = True
        source_scope_ref = f"{row['source_scope_table']}:{int(row['source_scope_id'])}"
        candidates.append(
            {
                "candidate_ref": f"dry_run:previous_day_full_context_expansion_candidate:{len(candidates) + 1}",
                "run_id": expansion_run_id,
                "source_condition_run_id": row["source_condition_run_id"],
                "for_trade_date": row["for_trade_date"],
                "source_trade_date": row["source_trade_date"],
                "prev_trade_date": row["prev_trade_date"],
                "asset_kind": row["asset_kind"],
                "identity_key": row["identity_key"],
                "exchange": row["exchange"],
                "code": row["code"],
                "display_code": row.get("display_code"),
                "name": row.get("name"),
                "required_data_kind": PREVIOUS_DAY_REQUIRED_DATA_KIND,
                "data_trade_date": previous_day_minute_date,
                "source_scope_table": row["source_scope_table"],
                "source_scope_id": int(row["source_scope_id"]),
                "source_scope_ref": source_scope_ref,
                "source_condition_pool_id": int(row["source_condition_pool_id"]),
                "direction": row["direction"],
                "condition_key": row["condition_key"],
                "allowed_signal_types": list(row.get("allowed_signal_types") or []),
                "source_scope_required_flags": flags,
                "candidate_status": row.get("candidate_status") or "planned",
                "selected_reason": "full-context expansion: add previous-day minute scope for N4 v4 lineage",
            }
        )
    return candidates


def deduplicate_previous_day_expansion_candidates(
    *,
    expansion_run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    previous_day_minute_date: str = PREVIOUS_DAY_MINUTE_DATE,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in candidates:
        groups[
            (
                str(row["asset_kind"]),
                str(row["identity_key"]),
                str(row["required_data_kind"]),
                str(row["for_trade_date"]),
            )
        ].append(row)
    subscriptions: list[dict[str, Any]] = []
    for _, rows in sorted(groups.items()):
        first = rows[0]
        subscriptions.append(
            {
                "subscription_ref": f"dry_run:previous_day_full_context_expansion_subscription:{len(subscriptions) + 1}",
                "run_id": expansion_run_id,
                "source_condition_run_id": first["source_condition_run_id"],
                "for_trade_date": first["for_trade_date"],
                "source_trade_date": first["source_trade_date"],
                "prev_trade_date": first["prev_trade_date"],
                "asset_kind": first["asset_kind"],
                "identity_key": first["identity_key"],
                "exchange": first["exchange"],
                "code": first["code"],
                "display_code": first.get("display_code"),
                "name": first.get("name"),
                "required_data_kind": PREVIOUS_DAY_REQUIRED_DATA_KIND,
                "data_trade_date": previous_day_minute_date,
                "data_trade_dates": [previous_day_minute_date],
                "source_scope_row_count": len(rows),
                "source_scope_tables": unique_preserve_order(row["source_scope_table"] for row in rows),
                "source_scope_ids": unique_preserve_order(int(row["source_scope_id"]) for row in rows),
                "source_scope_refs": unique_preserve_order(row["source_scope_ref"] for row in rows),
                "source_condition_pool_ids": unique_preserve_order(int(row["source_condition_pool_id"]) for row in rows),
                "condition_keys": unique_preserve_order(row["condition_key"] for row in rows),
                "directions": unique_preserve_order(row["direction"] for row in rows),
                "allowed_signal_types": unique_preserve_order(
                    signal for row in rows for signal in (row.get("allowed_signal_types") or [])
                ),
                "priority": 111,
                "status": "planned",
                "selected_reason": "deduped full-context expansion previous-day minute subscription",
            }
        )
    return subscriptions


def build_previous_day_expansion_pull_plan_rows(
    *,
    expansion_run_id: str,
    subscriptions: Sequence[Mapping[str, Any]],
    for_trade_date: str = FOR_TRADE_DATE,
    source_trade_date: str = PREVIOUS_DAY_MINUTE_DATE,
    previous_day_minute_date: str = PREVIOUS_DAY_MINUTE_DATE,
    source_condition_run_id: str = SOURCE_CONDITION_RUN_ID,
) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in subscriptions:
        groups[str(row["asset_kind"])].append(row)
    rows: list[dict[str, Any]] = []
    for asset_kind in ASSET_KINDS:
        group = groups.get(asset_kind, [])
        if not group:
            continue
        rows.append(
            {
                "pull_plan_ref": f"dry_run:previous_day_full_context_expansion_pull_plan:{len(rows) + 1}",
                "run_id": expansion_run_id,
                "source_condition_run_id": source_condition_run_id,
                "for_trade_date": for_trade_date,
                "source_trade_date": source_trade_date,
                "prev_trade_date": previous_day_minute_date,
                "asset_kind": asset_kind,
                "required_data_kind": PREVIOUS_DAY_REQUIRED_DATA_KIND,
                "data_trade_date": previous_day_minute_date,
                "adapter_name": ADAPTER_NAMES[asset_kind],
                "subscription_count": len(group),
                "object_count": len({row["identity_key"] for row in group}),
                "subscription_refs_sample": [row["subscription_ref"] for row in group[:20]],
                "identity_keys_sample": [row["identity_key"] for row in group[:20]],
                "plan_status": "planned",
                "execute_allowed": False,
                "selected_reason": "full-context previous-day expansion control rows only; A1 execute remains separate",
            }
        )
    return rows


def run_previous_day_full_context_expansion_subscription_scope_execute(
    *,
    dsn: str,
    dry_run_path: str = DEFAULT_DRY_RUN_JSON_PATH,
    json_report_path: str = DEFAULT_EXECUTE_JSON_PATH,
    markdown_report_path: str = DEFAULT_EXECUTE_MD_PATH,
    execute: bool = False,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    if not execute:
        raise RuntimeError("N3 previous-day full-context expansion subscription scope blocked: missing --execute")
    if not user_confirmed:
        raise RuntimeError("N3 previous-day full-context expansion subscription scope blocked: missing --user-confirmed")

    dry_run_report = json.loads(Path(dry_run_path).read_text(encoding="utf-8"))
    ensure_executable_report(dry_run_report)
    run_id = str(dry_run_report["market_data_run_id"])
    pre_counts = capture_scope_counts(dsn, run_id)
    before_events = fetch_event_global_counts_with_dsn(dsn)
    started_at = utc_now_iso()
    write_result = persist_previous_day_scope_rows(
        dsn=dsn,
        report=dry_run_report,
        expansion_run_id=run_id,
    )
    post_counts = capture_scope_counts(dsn, run_id)
    after_events = fetch_event_global_counts_with_dsn(dsn)
    post_checks = {
        "market_data_run_row_added": post_counts["common_market_data_run"]
        - pre_counts["common_market_data_run"]
        == 1
        == int(write_result["market_data_run_rows_written"]),
        "quality_item_rows_added": post_counts["common_market_data_quality_item"]
        - pre_counts["common_market_data_quality_item"]
        == int(write_result["quality_item_rows_written"]),
        "previous_day_candidate_rows_added": post_counts["previous_day_candidate_rows"]
        - pre_counts["previous_day_candidate_rows"]
        == int(dry_run_report["candidate_row_count"])
        == int(write_result["candidate_rows_written"]),
        "previous_day_subscription_rows_added": post_counts["previous_day_subscription_rows"]
        - pre_counts["previous_day_subscription_rows"]
        == int(dry_run_report["subscription_row_count"])
        == int(write_result["subscription_rows_written"]),
        "previous_day_pull_plan_rows_added": post_counts["previous_day_pull_plan_rows"]
        - pre_counts["previous_day_pull_plan_rows"]
        == int(dry_run_report["pull_plan_row_count"])
        == int(write_result["pull_plan_rows_written"]),
        "event_outbox_delta_zero": after_events["common_event_outbox"] == before_events["common_event_outbox"],
        "event_inbox_delta_zero": after_events["common_event_inbox"] == before_events["common_event_inbox"],
        "event_checkpoint_delta_zero": after_events["common_event_consumer_checkpoint"]
        == before_events["common_event_consumer_checkpoint"],
    }
    quality_items = list(dry_run_report["quality"]["items"])
    for check, passed in post_checks.items():
        quality_items.append(
            quality_item(
                "P0",
                "passed" if passed else "failed",
                f"n3_previous_day_full_context_scope_postcheck_{check}",
                f"post execute check: {check}",
                expected="true",
                actual=str(bool(passed)).lower(),
            )
        )
    severity_counts = count_quality_severities(quality_items)
    report = {
        "stage": "N3_PREVIOUS_DAY_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE_EXECUTE",
        "layer_role": "N3_market_data",
        "result": "SCOPE_PASS" if severity_counts["P0"] == 0 else "BLOCKED",
        "market_data_run_id": run_id,
        "source_condition_run_id": dry_run_report["source_condition_run_id"],
        "for_trade_date": dry_run_report["for_trade_date"],
        "previous_day_minute_date": dry_run_report["previous_day_minute_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "dry_run_path": dry_run_path,
        "write_result": write_result,
        "pre_counts": pre_counts,
        "post_counts": post_counts,
        "post_checks": post_checks,
        "event_global_counts_before": before_events,
        "event_global_counts_after": after_events,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "writes_performed": True,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
        "rollback_sql": DEFAULT_ROLLBACK_SQL_PATH,
        "rollback_safe": severity_counts["P0"] == 0,
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_execute_markdown(report))
    return report


def ensure_executable_report(report: Mapping[str, Any]) -> None:
    if report.get("stage") != "N3_PREVIOUS_DAY_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE":
        raise RuntimeError("input report is not a previous-day full-context expansion subscription scope report")
    if bool(report.get("blocked")) or int(report["quality"]["p0_count"]) > 0:
        raise RuntimeError("previous-day full-context expansion subscription scope dry-run is blocked")
    for section_name in ("market_data_subscription_candidate", "market_data_subscription_dedup", "market_data_pull_plan"):
        section = report.get(section_name) or {}
        if not bool(section.get("rows_included")):
            raise RuntimeError(f"{section_name} rows are not included")
        if len(section.get("rows") or []) != int(section.get("row_count") or 0):
            raise RuntimeError(f"{section_name} row_count does not match included rows")


def persist_previous_day_scope_rows(
    *,
    dsn: str,
    report: Mapping[str, Any],
    expansion_run_id: str,
) -> dict[str, int]:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                counts = fetch_previous_day_expansion_baseline(cur, expansion_run_id)
                if any(int(value) != 0 for value in counts.values()):
                    raise RuntimeError(f"previous-day expansion scope already exists for {expansion_run_id}: {counts}")
                insert_previous_day_market_data_run(cur, report, expansion_run_id)
                quality_count = insert_quality_items(cur, report, expansion_run_id)
                candidate_count = insert_subscription_candidates(cur, report, expansion_run_id)
                subscription_ref_to_id = insert_subscriptions(cur, report, expansion_run_id)
                pull_plan_count = insert_pull_plans(cur, report, expansion_run_id, subscription_ref_to_id)
    return {
        "candidate_rows_written": candidate_count,
        "subscription_rows_written": len(subscription_ref_to_id),
        "pull_plan_rows_written": pull_plan_count,
        "market_data_run_rows_written": 1,
        "quality_item_rows_written": quality_count,
        "market_data_fact_rows_written": 0,
        "event_outbox_rows_written": 0,
    }


def insert_previous_day_market_data_run(cur: Any, report: Mapping[str, Any], execute_run_id: str) -> None:
    columns = (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "mode",
        "status",
        "p0_count",
        "p1_count",
        "p2_count",
        "source_scope_row_count",
        "candidate_row_count",
        "subscription_row_count",
        "subscription_object_count",
        "dedup_ratio",
        "generated_by",
        "market_data_pulled",
        "market_data_fact_written",
        "downstream_layers_touched",
        "worker_started",
        "finished_at",
        "raw_json",
    )
    quality = report["quality"]
    status = "passed" if int(quality["p0_count"]) == 0 else "blocked"
    source_scope_row_count = int(report.get("source_scope_row_count") or report["candidate_row_count"])
    subscription_object_count = int(
        report.get("subscription_object_count")
        or sum(int(value) for value in (report.get("asset_count_by_asset_kind") or {}).values())
    )
    candidate_count = int(report["candidate_row_count"])
    subscription_count = int(report["subscription_row_count"])
    dedup_ratio = report.get("dedup_ratio")
    if dedup_ratio is None and candidate_count:
        dedup_ratio = subscription_count / candidate_count
    values = (
        execute_run_id,
        report["source_condition_run_id"],
        report["for_trade_date"],
        report["source_trade_date"],
        report["prev_trade_date"],
        "execute",
        status,
        int(quality["p0_count"]),
        int(quality["p1_count"]),
        int(quality["p2_count"]),
        source_scope_row_count,
        candidate_count,
        subscription_count,
        subscription_object_count,
        dedup_ratio,
        "previous_day_full_context_expansion_scope_execute",
        False,
        False,
        False,
        False,
        datetime.now(timezone.utc),
        Jsonb(
            {
                "stage": report.get("stage"),
                "layer_role": report.get("layer_role"),
                "plan_source": report.get("plan_source"),
                "source_expansion_run_id": report.get("source_expansion_run_id"),
                "previous_day_minute_date": report.get("previous_day_minute_date"),
                "required_data_kind": report.get("required_data_kind"),
                "write_scope": report.get("write_scope"),
                "side_effects": {
                    "market_data_pulled": False,
                    "market_data_fact_written": False,
                    "event_outbox_written": False,
                    "downstream_layers_touched": False,
                    "worker_started": False,
                },
            }
        ),
    )
    cur.execute(
        f"""
        INSERT INTO common_market_data_run ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        values,
    )


def fetch_target_db_proof(cur: Any) -> dict[str, Any]:
    cur.execute("select current_database() as database, current_user as user, inet_server_addr()::text as host, inet_server_port() as port")
    return normalize_db_row(cur.fetchone())


def fetch_market_data_run(cur: Any, run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
               prev_trade_date, mode, status, p0_count, p1_count, p2_count,
               market_data_pulled, market_data_fact_written,
               downstream_layers_touched, worker_started
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    return normalize_db_row(row) if row else None


def fetch_subscription_candidates(cur: Any, run_id: str, required_data_kind: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
               prev_trade_date, asset_kind, identity_key, exchange, code,
               display_code, name, required_data_kind, data_trade_date,
               source_scope_table, source_scope_id, source_condition_pool_id,
               direction, condition_key, allowed_signal_types,
               source_scope_required_flags, candidate_status, selected_reason,
               raw_json
        FROM common_market_data_subscription_candidate
        WHERE run_id = %s
          AND required_data_kind = %s
        ORDER BY asset_kind, identity_key, source_scope_table, source_scope_id, candidate_id
        """,
        (run_id, required_data_kind),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def fetch_existing_previous_day_scope_counts(cur: Any, run_id: str) -> dict[str, int]:
    output: dict[str, int] = {}
    cur.execute(
        """
        SELECT count(*) AS rows
        FROM common_market_data_subscription_candidate
        WHERE run_id = %s
          AND required_data_kind = %s
        """,
        (run_id, PREVIOUS_DAY_REQUIRED_DATA_KIND),
    )
    output["candidate_rows"] = int(cur.fetchone()["rows"])
    cur.execute(
        """
        SELECT count(*) AS rows
        FROM common_market_data_subscription
        WHERE run_id = %s
          AND required_data_kind = %s
        """,
        (run_id, PREVIOUS_DAY_REQUIRED_DATA_KIND),
    )
    output["subscription_rows"] = int(cur.fetchone()["rows"])
    cur.execute(
        """
        SELECT count(*) AS rows
        FROM common_market_data_pull_plan
        WHERE run_id = %s
          AND required_data_kind = %s
        """,
        (run_id, PREVIOUS_DAY_REQUIRED_DATA_KIND),
    )
    output["pull_plan_rows"] = int(cur.fetchone()["rows"])
    return output


def fetch_scope_ref_counts(cur: Any, run_id: str) -> dict[str, int]:
    output: dict[str, int] = {}
    cur.execute("SELECT count(*) AS rows FROM common_event_outbox WHERE source_run_id=%s OR payload_json::TEXT LIKE %s", (run_id, f"%{run_id}%"))
    output["common_event_outbox_refs"] = int(cur.fetchone()["rows"])
    cur.execute(
        "SELECT count(*) AS rows FROM common_event_inbox WHERE source_run_id=%s OR payload_json::TEXT LIKE %s OR raw_json::TEXT LIKE %s",
        (run_id, f"%{run_id}%", f"%{run_id}%"),
    )
    output["common_event_inbox_refs"] = int(cur.fetchone()["rows"])
    cur.execute(
        "SELECT count(*) AS rows FROM common_event_consumer_checkpoint WHERE checkpoint_payload::TEXT LIKE %s OR last_event_id LIKE %s",
        (f"%{run_id}%", f"%{run_id}%"),
    )
    output["common_event_consumer_checkpoint_refs"] = int(cur.fetchone()["rows"])
    return output


def fetch_event_global_counts(cur: Any) -> dict[str, int]:
    output = {}
    for table in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"):
        cur.execute(f"SELECT count(*) AS rows FROM {table}")
        output[table] = int(cur.fetchone()["rows"])
    return output


def fetch_event_global_counts_with_dsn(dsn: str) -> dict[str, int]:
    with audited_n3_market_readonly_plan_connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        return fetch_event_global_counts(cur)


def capture_scope_counts(dsn: str, run_id: str) -> dict[str, int]:
    with audited_n3_market_readonly_plan_connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        existing = fetch_existing_previous_day_scope_counts(cur, run_id)
        baseline = fetch_previous_day_expansion_baseline(cur, run_id)
        refs = fetch_scope_ref_counts(cur, run_id)
    return {
        "common_market_data_run": baseline["common_market_data_run"],
        "common_market_data_quality_item": baseline["common_market_data_quality_item"],
        "previous_day_candidate_rows": existing["candidate_rows"],
        "previous_day_subscription_rows": existing["subscription_rows"],
        "previous_day_pull_plan_rows": existing["pull_plan_rows"],
        **refs,
    }


def empty_previous_day_expansion_baseline() -> dict[str, int]:
    return {
        "common_market_data_run": 0,
        "common_market_data_quality_item": 0,
        "common_market_data_subscription_candidate": 0,
        "common_market_data_subscription": 0,
        "common_market_data_pull_plan": 0,
        "common_event_outbox_refs": 0,
        "common_event_inbox_refs": 0,
        "common_event_consumer_checkpoint_refs": 0,
    }


def fetch_previous_day_expansion_baseline(cur: Any, run_id: str) -> dict[str, int]:
    baseline = empty_previous_day_expansion_baseline()
    for table_name in (
        "common_market_data_run",
        "common_market_data_quality_item",
        "common_market_data_subscription_candidate",
        "common_market_data_subscription",
        "common_market_data_pull_plan",
    ):
        cur.execute(f"SELECT count(*) AS rows FROM {table_name} WHERE run_id = %s", (run_id,))
        baseline[table_name] = int(cur.fetchone()["rows"])
    refs = fetch_scope_ref_counts(cur, run_id)
    baseline.update(refs)
    return baseline


def build_plan_artifact_quality_items(
    *,
    expansion_plan_report: Mapping[str, Any] | None,
    for_trade_date: str,
    source_trade_date: str,
    previous_trade_date: str,
    expansion_run_id: str,
    identity_rows: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_plan_rows: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, int],
) -> list[dict[str, Any]]:
    plan = expansion_plan_report or {}
    pull_plan_assets = {row["asset_kind"] for row in pull_plan_rows}
    subscription_assets = {row["asset_kind"] for row in subscriptions}
    items = [
        quality_item(
            "P0",
            "passed" if expansion_plan_report is not None else "failed",
            "n3_previous_day_full_context_expansion_plan_loaded",
            "PR1 full-context expansion plan artifact must be readable",
            expected="loaded",
            actual="loaded" if expansion_plan_report is not None else "missing",
        ),
        quality_item(
            "P0",
            "passed" if bool(plan.get("passed")) and not bool(plan.get("blocked")) else "failed",
            "n3_previous_day_full_context_expansion_plan_passed",
            "PR1 full-context expansion plan must be passed",
            expected="passed=true blocked=false",
            actual=f"passed={bool(plan.get('passed'))} blocked={bool(plan.get('blocked'))}",
        ),
        quality_item(
            "P0",
            "passed" if plan.get("market_data_run_id") == expansion_run_id else "failed",
            "n3_previous_day_full_context_expansion_run_id_matches_plan",
            "requested source expansion run id must match PR1 artifact",
            expected=expansion_run_id,
            actual=str(plan.get("market_data_run_id")),
        ),
        quality_item(
            "P0",
            "passed" if plan.get("for_trade_date") == for_trade_date else "failed",
            "n3_previous_day_full_context_for_trade_date_matches_plan",
            "requested for_trade_date must match PR1 artifact",
            expected=for_trade_date,
            actual=str(plan.get("for_trade_date")),
        ),
        quality_item(
            "P0",
            "passed" if plan.get("source_trade_date") == source_trade_date else "failed",
            "n3_previous_day_full_context_source_trade_date_matches_plan",
            "requested source_trade_date must match PR1 artifact",
            expected=source_trade_date,
            actual=str(plan.get("source_trade_date")),
        ),
        quality_item(
            "P0",
            "passed" if plan.get("prev_trade_date") == previous_trade_date else "failed",
            "n3_previous_day_full_context_previous_trade_date_matches_plan",
            "requested previous_trade_date must match PR1 artifact",
            expected=previous_trade_date,
            actual=str(plan.get("prev_trade_date")),
        ),
        quality_item(
            "P0",
            "passed" if len(identity_rows) > 0 else "failed",
            "n3_previous_day_full_context_expansion_identities_nonempty",
            "PR1 artifact must include expansion minute identities",
            expected=">0",
            actual=str(len(identity_rows)),
        ),
        quality_item(
            "P0",
            "passed" if len(candidates) > 0 and len(subscriptions) > 0 else "failed",
            "n3_previous_day_full_context_candidate_rows_nonzero",
            "previous-day candidate and subscription rows must be nonzero",
            expected=">0",
            actual=f"candidates={len(candidates)} subscriptions={len(subscriptions)}",
        ),
        quality_item(
            "P0",
            "passed" if not any(int(value) != 0 for value in baseline.values()) else "failed",
            "n3_previous_day_full_context_previous_day_expansion_baseline_zero",
            "previous-day expansion target run id must not already exist",
            expected="all zero",
            actual=json.dumps(dict(baseline), sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if subscription_assets == pull_plan_assets else "failed",
            "n3_previous_day_full_context_pull_plan_asset_coverage",
            "pull plan must cover every asset kind with planned previous-day subscriptions",
            expected=",".join(sorted(subscription_assets)),
            actual=",".join(sorted(pull_plan_assets)),
        ),
    ]
    return items


def build_quality_items(
    *,
    run_row: Mapping[str, Any] | None,
    minute_candidates: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_plan_rows: Sequence[Mapping[str, Any]],
    existing_previous_day_counts: Mapping[str, int],
    baseline_refs: Mapping[str, int],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.append(
        quality_item(
            "P0",
            "passed" if run_row and run_row.get("status") == "passed" else "failed",
            "n3_previous_day_full_context_expansion_subscription_run_ready",
            "expansion subscription run must already be passed",
            expected="passed",
            actual=str((run_row or {}).get("status")),
        )
    )
    candidate_counts = dict(sorted(Counter(row["asset_kind"] for row in candidates).items()))
    object_counts = object_count_by_asset_kind(subscriptions)
    pull_plan_assets = {row["asset_kind"] for row in pull_plan_rows}
    items.append(
        quality_item(
            "P0",
            "passed" if len(minute_candidates) == sum(EXPECTED_CONTEXT_ROWS_BY_ASSET.values()) else "failed",
            "n3_previous_day_full_context_source_minute_scope_matches_gap",
            "existing expansion minute candidates must match full-context gap rows",
            expected=json.dumps(EXPECTED_CONTEXT_ROWS_BY_ASSET, sort_keys=True),
            actual=json.dumps(dict(sorted(Counter(row["asset_kind"] for row in minute_candidates).items())), sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if candidate_counts == EXPECTED_CONTEXT_ROWS_BY_ASSET else "failed",
            "n3_previous_day_full_context_candidate_rows_match_gap",
            "derived previous-day candidates must match missing previous-day context rows",
            expected=json.dumps(EXPECTED_CONTEXT_ROWS_BY_ASSET, sort_keys=True),
            actual=json.dumps(candidate_counts, sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if object_counts == EXPECTED_OBJECTS_BY_ASSET else "failed",
            "n3_previous_day_full_context_objects_match_gap",
            "derived previous-day subscriptions must match missing previous-day context objects",
            expected=json.dumps(EXPECTED_OBJECTS_BY_ASSET, sort_keys=True),
            actual=json.dumps(object_counts, sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if pull_plan_assets == set(ASSET_KINDS) and len(pull_plan_rows) == 3 else "failed",
            "n3_previous_day_full_context_pull_plan_asset_coverage",
            "pull_plan must cover stock/index/board because all three have previous-day expansion objects",
            expected="stock,index,board",
            actual=",".join(sorted(pull_plan_assets)),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if not any(int(value) != 0 for value in existing_previous_day_counts.values()) else "failed",
            "n3_previous_day_full_context_scope_baseline_zero",
            "existing previous_day_minute_bar_1m candidate/subscription/pull_plan rows must be zero",
            expected="0/0/0",
            actual=json.dumps(dict(existing_previous_day_counts), sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if not any(int(value) != 0 for value in baseline_refs.values()) else "failed",
            "n3_previous_day_full_context_event_refs_zero",
            "scoped outbox/inbox/checkpoint refs must be zero",
            expected="0/0/0",
            actual=json.dumps(dict(baseline_refs), sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P1",
            "warning",
            "n3_previous_day_full_context_bj_index_quality_blocked_carried",
            "BJ index quality blockers remain explicit and must not silently fallback",
            expected="index:BJ:899050,index:BJ:899601 classified",
            actual="quality_blocked",
        )
    )
    return items


def build_previous_day_expansion_rollback_sql(run_id: str = EXPANSION_SUBSCRIPTION_RUN_ID) -> str:
    return f"""-- N3 previous-day full-context expansion subscription scope rollback.
-- Scope: only previous_day_minute_bar_1m control rows for {run_id}.
-- Hard-fails before DELETE if previous-day business rows, event infra, or downstream refs exist.

\\set ON_ERROR_STOP on
\\set run_id '{run_id}'
\\set required_data_kind 'previous_day_minute_bar_1m'

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := '{run_id}';
  v_count BIGINT;
  v_table TEXT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing previous-day full-context scope rollback: outbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%' OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing previous-day full-context scope rollback: inbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%' OR last_event_id LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing previous-day full-context scope rollback: checkpoint has % refs for %', v_count, v_run_id;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m',
    'stock_previous_day_minute_preload_status', 'index_previous_day_minute_preload_status', 'board_previous_day_minute_preload_status',
    'stock_action_confirmation_projection_metric', 'index_action_confirmation_projection_metric', 'board_action_confirmation_projection_metric',
    'common_trigger_run', 'common_trigger_state', 'common_trigger_match', 'common_trigger_quality_item',
    'common_action_run', 'common_action_event', 'common_action_quality_item',
    'user_signal_projection', 'user_signal_card', 'user_notification_queue'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE 'SELECT count(*) FROM public.' || quote_ident(v_table) || ' t WHERE to_jsonb(t)::TEXT LIKE $1'
        INTO v_count
        USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'Refusing previous-day full-context scope rollback: table % has % refs for %', v_table, v_count, v_run_id;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_market_data_pull_plan
WHERE run_id = :'run_id'
  AND required_data_kind = 'previous_day_minute_bar_1m';

DELETE FROM common_market_data_subscription
WHERE run_id = :'run_id'
  AND required_data_kind = 'previous_day_minute_bar_1m';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = :'run_id'
  AND required_data_kind = 'previous_day_minute_bar_1m';

COMMIT;
"""


def format_dry_run_markdown(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    return "\n".join(
        [
            "# N3 Previous-Day Full-Context Expansion Subscription Scope Dry-Run",
            "",
            "## Result",
            "",
            f"- result: `{report['result']}`",
            f"- market_data_run_id: `{report['market_data_run_id']}`",
            f"- previous_day_minute_date: `{report['previous_day_minute_date']}`",
            f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
            "",
            "## Planned Additive Rows",
            "",
            f"- candidate rows: `{report['candidate_row_count']}`",
            f"- subscription rows: `{report['subscription_row_count']}`",
            f"- pull_plan rows: `{report['pull_plan_row_count']}`",
            f"- expected rows: `{report['expected_rows_by_asset_kind']}`",
            "",
            "## Boundary",
            "",
            "- no market pull",
            "- no minute/snapshot/projection facts",
            "- no outbox/inbox/checkpoint writes",
            "- no N4/N5/N6",
            "- no worker",
            "",
            "## Rollback",
            "",
            f"- rollback_sql: `{report['rollback_sql']}`",
            "- hard-fail guard before first DELETE",
            "",
        ]
    )


def format_execute_markdown(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    return "\n".join(
        [
            "# N3 Previous-Day Full-Context Expansion Subscription Scope Execute Report",
            "",
            "## Result",
            "",
            f"- result: `{report['result']}`",
            f"- market_data_run_id: `{report['market_data_run_id']}`",
            f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
            "",
            "## Rows Written",
            "",
            f"- candidate rows: `{write['candidate_rows_written']}`",
            f"- subscription rows: `{write['subscription_rows_written']}`",
            f"- pull_plan rows: `{write['pull_plan_rows_written']}`",
            f"- market_data facts: `{write['market_data_fact_rows_written']}`",
            f"- outbox rows: `{write['event_outbox_rows_written']}`",
            "",
            "## Rollback",
            "",
            f"- rollback_sql: `{report['rollback_sql']}`",
            f"- rollback_safe: `{report['rollback_safe']}`",
            "",
        ]
    )


def normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return normalize_db_row(value) if value is not None else None


def object_count_by_asset_kind(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    output: dict[str, set[str]] = {asset: set() for asset in ASSET_KINDS}
    for row in rows:
        output.setdefault(str(row["asset_kind"]), set()).add(str(row["identity_key"]))
    return {asset: len(output.get(asset, set())) for asset in ASSET_KINDS}


def write_scope_artifacts(report: Mapping[str, Any]) -> None:
    write_json(DEFAULT_DRY_RUN_JSON_PATH, report)
    write_text(DEFAULT_DRY_RUN_MD_PATH, format_dry_run_markdown(report))
    Path(DEFAULT_ROLLBACK_SQL_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(DEFAULT_ROLLBACK_SQL_PATH).write_text(build_previous_day_expansion_rollback_sql(str(report["market_data_run_id"])), encoding="utf-8")
