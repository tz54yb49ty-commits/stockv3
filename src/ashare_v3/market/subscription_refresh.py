"""N3 market-data subscription refresh dry-run after an N2 rebase.

This module reads the new active condition run, rebuilds the N3-0
market_data_subscription / pull_plan dry-run, and compares it with existing
persisted N3 subscription runs. It does not persist N3 control rows, pull
market data, write market facts, write common_event_outbox, or start workers.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.subscription_execute import derive_execute_run_id
from ashare_v3.market.subscription_plan import (
    ACTIVE_CONDITION_RUN_STATUSES,
    ASSET_KINDS,
    build_market_data_subscription_plan_dry_run,
)


DEFAULT_REFRESH_MD_PATH = "docs/N3_AFTER_N2_R2_SUBSCRIPTION_REFRESH_DRY_RUN.md"
DEFAULT_REFRESH_JSON_PATH = "docs/N3_AFTER_N2_R2_subscription_refresh_dry_run.json"


def build_subscription_refresh_dry_run(
    *,
    dsn: str,
    new_condition_run_id: str,
    old_market_data_run_id: str | None = None,
    expected_scope_counts: Mapping[str, int] | None = None,
    expected_object_counts: Mapping[str, int] | None = None,
    include_rows: bool = False,
) -> dict[str, Any]:
    dry_run = build_market_data_subscription_plan_dry_run(
        dsn=dsn,
        run_id=new_condition_run_id,
        include_rows=include_rows,
    )
    db_state = fetch_subscription_refresh_db_state(
        dsn=dsn,
        new_condition_run_id=new_condition_run_id,
        for_trade_date=str(dry_run.get("for_trade_date") or ""),
        old_market_data_run_id=old_market_data_run_id,
    )
    return build_subscription_refresh_report_from_inputs(
        dry_run=dry_run,
        db_state=db_state,
        new_condition_run_id=new_condition_run_id,
        expected_scope_counts=expected_scope_counts or {"stock": 4236, "index": 18, "board": 258},
        expected_object_counts=expected_object_counts or {"stock": 2052, "index": 9, "board": 127},
    )


def fetch_subscription_refresh_db_state(
    *,
    dsn: str,
    new_condition_run_id: str,
    for_trade_date: str,
    old_market_data_run_id: str | None,
) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, status, source_trade_date, for_trade_date, prev_trade_date,
                   p0_count, p1_count, p2_count, finished_at, created_at
            FROM common_condition_run
            WHERE for_trade_date = %s
              AND status = ANY(%s)
            ORDER BY finished_at DESC NULLS LAST, created_at DESC, run_id DESC
            """,
            (for_trade_date, list(ACTIVE_CONDITION_RUN_STATUSES)),
        )
        active_passed_runs = [normalize_db_row(row) for row in cur.fetchall()]

        old_run: dict[str, Any] | None = None
        if old_market_data_run_id:
            old_run = fetch_market_data_run(cur, old_market_data_run_id)

        cur.execute(
            """
            SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
                   prev_trade_date, mode, status, p0_count, p1_count, p2_count,
                   source_scope_row_count, candidate_row_count, subscription_row_count,
                   subscription_object_count, market_data_pulled,
                   market_data_fact_written, downstream_layers_touched,
                   worker_started, created_at, updated_at
            FROM common_market_data_run
            WHERE for_trade_date = %s
              AND run_id LIKE 'market_data_subscription_%%'
            ORDER BY created_at DESC, run_id DESC
            """,
            (for_trade_date,),
        )
        existing_subscription_runs = [normalize_db_row(row) for row in cur.fetchall()]
        if old_run is None:
            old_run = first_stale_subscription_run(
                existing_subscription_runs,
                new_condition_run_id=new_condition_run_id,
            )

        control_counts = fetch_control_row_counts(cur, [row["run_id"] for row in existing_subscription_runs])
        fact_event_counts = fetch_fact_event_counts(cur)

    return {
        "active_passed_runs": active_passed_runs,
        "old_market_data_run": old_run,
        "existing_subscription_runs": existing_subscription_runs,
        "control_row_counts_by_run": control_counts,
        "fact_event_row_counts": fact_event_counts,
    }


def fetch_market_data_run(cur: Any, run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
               prev_trade_date, mode, status, p0_count, p1_count, p2_count,
               source_scope_row_count, candidate_row_count, subscription_row_count,
               subscription_object_count, market_data_pulled,
               market_data_fact_written, downstream_layers_touched,
               worker_started, created_at, updated_at
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    return normalize_db_row(row) if row is not None else None


def fetch_control_row_counts(cur: Any, run_ids: Sequence[str]) -> dict[str, dict[str, int]]:
    output = {
        run_id: {
            "common_market_data_subscription_candidate": 0,
            "common_market_data_subscription": 0,
            "common_market_data_pull_plan": 0,
        }
        for run_id in run_ids
    }
    if not run_ids:
        return output
    for table_name in output[next(iter(output))].keys():
        cur.execute(
            f"""
            SELECT run_id, count(*)::bigint AS row_count
            FROM {table_name}
            WHERE run_id = ANY(%s)
            GROUP BY run_id
            """,
            (list(run_ids),),
        )
        for row in cur.fetchall():
            output[str(row["run_id"])][table_name] = int(row["row_count"])
    return output


def fetch_fact_event_counts(cur: Any) -> dict[str, int]:
    table_names = (
        "stock_realtime_daily_snapshot",
        "index_realtime_daily_snapshot",
        "board_realtime_daily_snapshot",
        "stock_minute_bar_1m",
        "index_minute_bar_1m",
        "board_minute_bar_1m",
        "common_event_outbox",
    )
    output: dict[str, int] = {}
    for table_name in table_names:
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
        output[table_name] = int(cur.fetchone()["row_count"])
    return output


def first_stale_subscription_run(
    rows: Sequence[Mapping[str, Any]],
    *,
    new_condition_run_id: str,
) -> dict[str, Any] | None:
    for row in rows:
        if row.get("source_condition_run_id") != new_condition_run_id:
            return dict(row)
    return None


def build_subscription_refresh_report_from_inputs(
    *,
    dry_run: Mapping[str, Any],
    db_state: Mapping[str, Any],
    new_condition_run_id: str,
    expected_scope_counts: Mapping[str, int],
    expected_object_counts: Mapping[str, int],
) -> dict[str, Any]:
    suggested_execute_run_id = derive_execute_run_id(dry_run)
    old_run = db_state.get("old_market_data_run")
    old_run_is_stale = bool(old_run and old_run.get("source_condition_run_id") != new_condition_run_id)
    new_existing_runs = [
        dict(row)
        for row in db_state.get("existing_subscription_runs", [])
        if row.get("source_condition_run_id") == new_condition_run_id
    ]
    comparison = build_old_new_comparison(
        dry_run=dry_run,
        old_run=old_run if isinstance(old_run, Mapping) else None,
        old_control_counts=(db_state.get("control_row_counts_by_run") or {}).get(str(old_run.get("run_id"))) if isinstance(old_run, Mapping) else None,
    )
    quality_items = list((dry_run.get("quality") or {}).get("items") or [])
    quality_items.extend(
        build_refresh_quality_items(
            dry_run=dry_run,
            db_state=db_state,
            new_condition_run_id=new_condition_run_id,
            expected_scope_counts=expected_scope_counts,
            expected_object_counts=expected_object_counts,
            old_run=old_run if isinstance(old_run, Mapping) else None,
            old_run_is_stale=old_run_is_stale,
            new_existing_runs=new_existing_runs,
        )
    )
    counts = count_quality_severities(quality_items)
    return {
        "stage": "N3-after-N2-R2-subscription-refresh-dry-run",
        "layer_role": "N3_market_data",
        "mode": "dry_run",
        "new_condition_run_id": new_condition_run_id,
        "source_condition_run_id": dry_run.get("source_condition_run_id"),
        "source_trade_date": dry_run.get("source_trade_date"),
        "for_trade_date": dry_run.get("for_trade_date"),
        "prev_trade_date": dry_run.get("prev_trade_date"),
        "dry_run_market_data_run_id": dry_run.get("market_data_run_id"),
        "suggested_execute_run_id": suggested_execute_run_id,
        "active_n2_check": {
            "expected_active_run_id": new_condition_run_id,
            "passed_run_count": len(db_state.get("active_passed_runs") or []),
            "passed_runs": db_state.get("active_passed_runs") or [],
            "is_new_active_run": len(db_state.get("active_passed_runs") or []) == 1
            and (db_state.get("active_passed_runs") or [{}])[0].get("run_id") == new_condition_run_id,
        },
        "expected_scope_counts": dict(expected_scope_counts),
        "actual_scope_counts": dry_run.get("source_scope_row_count_by_asset_kind"),
        "expected_object_counts": dict(expected_object_counts),
        "actual_object_counts": dry_run.get("object_count_by_asset_kind"),
        "subscription_generation": {
            "source_scope_row_count": dry_run.get("source_scope_row_count"),
            "subscription_candidate_count": dry_run.get("subscription_candidate_count"),
            "dedup_subscription_count": dry_run.get("dedup_subscription_count"),
            "subscription_object_count": dry_run.get("subscription_object_count"),
            "required_data_kind_counts": dry_run.get("required_data_kind_counts"),
            "market_data_pull_plan_row_count": dry_run.get("market_data_pull_plan_row_count"),
            "dedup_ratio": dry_run.get("dedup_ratio"),
            "passed": dry_run.get("passed"),
            "blocked": dry_run.get("blocked"),
        },
        "market_data_pull_plan": dry_run.get("market_data_pull_plan"),
        "market_data_subscription_candidate": dry_run.get("market_data_subscription_candidate"),
        "market_data_subscription_dedup": dry_run.get("market_data_subscription_dedup"),
        "old_n3_subscription_run": old_run,
        "old_n3_subscription_run_is_stale": old_run_is_stale,
        "existing_new_condition_subscription_runs": new_existing_runs,
        "old_vs_new_comparison": comparison,
        "fact_event_row_counts_read_only": db_state.get("fact_event_row_counts"),
        "quality": {
            "p0_count": counts["P0"],
            "p1_count": counts["P1"],
            "p2_count": counts["P2"],
            "items": quality_items,
        },
        "passed": counts["P0"] == 0,
        "blocked": counts["P0"] > 0,
        "decision": {
            "old_n3_run_can_continue_as_final_chain": False if old_run_is_stale else None,
            "requires_new_n3_subscription_execute_before_downstream": True,
            "execute_performed": False,
        },
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


def build_old_new_comparison(
    *,
    dry_run: Mapping[str, Any],
    old_run: Mapping[str, Any] | None,
    old_control_counts: Mapping[str, int] | None,
) -> dict[str, Any]:
    if old_run is None:
        return {"old_run_present": False}
    old_candidate = int(old_run.get("candidate_row_count") or (old_control_counts or {}).get("common_market_data_subscription_candidate") or 0)
    old_subscription = int(old_run.get("subscription_row_count") or (old_control_counts or {}).get("common_market_data_subscription") or 0)
    old_pull_plan = int((old_control_counts or {}).get("common_market_data_pull_plan") or 0)
    new_candidate = int(dry_run.get("subscription_candidate_count") or dry_run.get("candidate_row_count") or 0)
    new_subscription = int(dry_run.get("dedup_subscription_count") or dry_run.get("subscription_row_count") or 0)
    new_pull_plan = int(dry_run.get("market_data_pull_plan_row_count") or 0)
    return {
        "old_run_present": True,
        "old_run_id": old_run.get("run_id"),
        "old_source_condition_run_id": old_run.get("source_condition_run_id"),
        "new_source_condition_run_id": dry_run.get("source_condition_run_id"),
        "old_counts": {
            "source_scope_row_count": int(old_run.get("source_scope_row_count") or 0),
            "candidate_row_count": old_candidate,
            "subscription_row_count": old_subscription,
            "subscription_object_count": int(old_run.get("subscription_object_count") or 0),
            "pull_plan_row_count": old_pull_plan,
        },
        "new_counts": {
            "source_scope_row_count": int(dry_run.get("source_scope_row_count") or 0),
            "candidate_row_count": new_candidate,
            "subscription_row_count": new_subscription,
            "subscription_object_count": int(dry_run.get("subscription_object_count") or 0),
            "pull_plan_row_count": new_pull_plan,
        },
        "delta": {
            "source_scope_row_count": int(dry_run.get("source_scope_row_count") or 0) - int(old_run.get("source_scope_row_count") or 0),
            "candidate_row_count": new_candidate - old_candidate,
            "subscription_row_count": new_subscription - old_subscription,
            "subscription_object_count": int(dry_run.get("subscription_object_count") or 0)
            - int(old_run.get("subscription_object_count") or 0),
            "pull_plan_row_count": new_pull_plan - old_pull_plan,
        },
        "lineage_changed": old_run.get("source_condition_run_id") != dry_run.get("source_condition_run_id"),
    }


def build_refresh_quality_items(
    *,
    dry_run: Mapping[str, Any],
    db_state: Mapping[str, Any],
    new_condition_run_id: str,
    expected_scope_counts: Mapping[str, int],
    expected_object_counts: Mapping[str, int],
    old_run: Mapping[str, Any] | None,
    old_run_is_stale: bool,
    new_existing_runs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    active_passed_runs = db_state.get("active_passed_runs") or []
    actual_scope_counts = dry_run.get("source_scope_row_count_by_asset_kind") or {}
    actual_object_counts = dry_run.get("object_count_by_asset_kind") or {}
    scope_counts_match = all(int(actual_scope_counts.get(asset) or 0) == int(expected_scope_counts.get(asset) or 0) for asset in ASSET_KINDS)
    object_counts_match = all(int(actual_object_counts.get(asset) or 0) == int(expected_object_counts.get(asset) or 0) for asset in ASSET_KINDS)
    pull_plan_rows = int(dry_run.get("market_data_pull_plan_row_count") or 0)
    candidate_rows = int(dry_run.get("subscription_candidate_count") or dry_run.get("candidate_row_count") or 0)
    subscription_rows = int(dry_run.get("dedup_subscription_count") or dry_run.get("subscription_row_count") or 0)
    return [
        quality_item(
            "P0",
            "passed"
            if len(active_passed_runs) == 1 and active_passed_runs[0].get("run_id") == new_condition_run_id
            else "failed",
            "n3_after_n2_r2_active_condition_run_is_new",
            "N3 refresh must consume the single active passed N2-R2 condition run",
            expected=new_condition_run_id,
            actual=",".join(str(row.get("run_id")) for row in active_passed_runs) or "none",
        ),
        quality_item(
            "P0",
            "passed" if dry_run.get("source_condition_run_id") == new_condition_run_id else "failed",
            "n3_after_n2_r2_dry_run_source_run_matches_new",
            "subscription dry-run source_condition_run_id must be the N2-R2 active run",
            expected=new_condition_run_id,
            actual=str(dry_run.get("source_condition_run_id")),
        ),
        quality_item(
            "P0",
            "passed" if scope_counts_match else "failed",
            "n3_after_n2_r2_scope_row_counts_match_expected",
            "stock/index/board minute_target_scope row counts must match N2-R2 report",
            expected=str(dict(expected_scope_counts)),
            actual=str({asset: int(actual_scope_counts.get(asset) or 0) for asset in ASSET_KINDS}),
        ),
        quality_item(
            "P0",
            "passed" if object_counts_match else "failed",
            "n3_after_n2_r2_object_counts_match_expected",
            "stock/index/board object counts must match N2-R2 expected N3 scope",
            expected=str(dict(expected_object_counts)),
            actual=str({asset: int(actual_object_counts.get(asset) or 0) for asset in ASSET_KINDS}),
        ),
        quality_item(
            "P0",
            "passed" if candidate_rows > 0 and subscription_rows > 0 and pull_plan_rows > 0 else "failed",
            "n3_after_n2_r2_subscription_and_pull_plan_generated",
            "candidate/dedup subscription/pull_plan rows must be generated",
            expected="all row counts > 0",
            actual=f"candidate={candidate_rows} subscription={subscription_rows} pull_plan={pull_plan_rows}",
        ),
        quality_item(
            "P0",
            "passed" if int((dry_run.get("quality") or {}).get("p0_count") or 0) == 0 and dry_run.get("passed") else "failed",
            "n3_after_n2_r2_subscription_dry_run_p0_zero",
            "underlying N3-0 subscription dry-run must pass with P0=0",
            expected="P0=0 passed=true",
            actual=f"P0={(dry_run.get('quality') or {}).get('p0_count')} passed={dry_run.get('passed')}",
        ),
        quality_item(
            "P0",
            "passed"
            if not dry_run.get("market_data_pulled")
            and not dry_run.get("market_data_fact_written")
            and not dry_run.get("downstream_layers_touched")
            and not dry_run.get("worker_started")
            else "failed",
            "n3_after_n2_r2_no_market_fact_outbox_or_worker",
            "refresh dry-run must not pull market data, write facts/outbox, enter downstream, or start workers",
            expected="all side-effect flags false",
            actual=side_effect_actual(dry_run),
        ),
        quality_item(
            "P1",
            "warning" if old_run_is_stale else "passed",
            "n3_after_n2_r2_old_n3_subscription_run_stale",
            "existing old N3 subscription run is based on a superseded condition run and cannot remain the final chain",
            expected=f"source_condition_run_id={new_condition_run_id}",
            actual="missing" if old_run is None else str(old_run.get("source_condition_run_id")),
            details={"old_run_id": old_run.get("run_id")} if old_run is not None else None,
        ),
        quality_item(
            "P1",
            "warning" if not new_existing_runs else "passed",
            "n3_after_n2_r2_new_n3_execute_not_yet_persisted",
            "dry-run is clean, but a new N3-6 subscription execute is still required before downstream N3-A/B/C refresh",
            expected="new N3 control run persisted before final chain",
            actual="not persisted" if not new_existing_runs else ",".join(str(row.get("run_id")) for row in new_existing_runs),
        ),
    ]


def side_effect_actual(dry_run: Mapping[str, Any]) -> str:
    keys = ("market_data_pulled", "market_data_fact_written", "downstream_layers_touched", "worker_started")
    return ",".join(f"{key}={dry_run.get(key)}" for key in keys)


def format_subscription_refresh_markdown(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    generation = report["subscription_generation"]
    lines = [
        "# N3 After N2-R2 Subscription Refresh Dry-Run",
        "",
        "## Summary",
        "",
        f"- stage: `{report['stage']}`",
        f"- layer_role: `{report['layer_role']}`",
        f"- new_condition_run_id: `{report['new_condition_run_id']}`",
        f"- dry_run_market_data_run_id: `{report['dry_run_market_data_run_id']}`",
        f"- suggested_execute_run_id: `{report['suggested_execute_run_id']}`",
        f"- source_trade_date: `{report['source_trade_date']}`",
        f"- for_trade_date: `{report['for_trade_date']}`",
        f"- prev_trade_date: `{report['prev_trade_date']}`",
        f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
        f"- passed: `{str(report['passed']).lower()}`",
        "",
        "## Active N2 Check",
        "",
        f"- is_new_active_run: `{str(report['active_n2_check']['is_new_active_run']).lower()}`",
        f"- passed_run_count: `{report['active_n2_check']['passed_run_count']}`",
        "",
        "## Counts",
        "",
        f"- expected_scope_counts: `{report['expected_scope_counts']}`",
        f"- actual_scope_counts: `{report['actual_scope_counts']}`",
        f"- expected_object_counts: `{report['expected_object_counts']}`",
        f"- actual_object_counts: `{report['actual_object_counts']}`",
        f"- source_scope_row_count: `{generation['source_scope_row_count']}`",
        f"- subscription_candidate_count: `{generation['subscription_candidate_count']}`",
        f"- dedup_subscription_count: `{generation['dedup_subscription_count']}`",
        f"- subscription_object_count: `{generation['subscription_object_count']}`",
        f"- required_data_kind_counts: `{generation['required_data_kind_counts']}`",
        f"- market_data_pull_plan_row_count: `{generation['market_data_pull_plan_row_count']}`",
        f"- dedup_ratio: `{generation['dedup_ratio']}`",
        "",
        "## Old N3 Run",
        "",
    ]
    old_run = report.get("old_n3_subscription_run")
    if isinstance(old_run, Mapping):
        lines.extend(
            [
                f"- old_run_id: `{old_run.get('run_id')}`",
                f"- old_source_condition_run_id: `{old_run.get('source_condition_run_id')}`",
                f"- old_n3_subscription_run_is_stale: `{str(report['old_n3_subscription_run_is_stale']).lower()}`",
                f"- old_run_can_continue_as_final_chain: `{str(report['decision']['old_n3_run_can_continue_as_final_chain']).lower()}`",
            ]
        )
    else:
        lines.append("- old_run_id: `missing`")
    lines.extend(
        [
            "",
            "## Old Vs New Comparison",
            "",
            f"- comparison: `{report['old_vs_new_comparison']}`",
            "",
            "## Quality",
            "",
        ]
    )
    for item in quality["items"]:
        if item.get("status") in {"failed", "warning"} or str(item.get("gate_code", "")).startswith("n3_after_n2_r2"):
            lines.append(
                f"- {item['severity']} {item['status']} {item['gate_code']}: "
                f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
            )
    lines.extend(["", "## Boundary", ""])
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.append("")
    return "\n".join(lines)


def format_subscription_refresh_summary(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    generation = report["subscription_generation"]
    return "\n".join(
        [
            "N3 after N2-R2 subscription refresh dry-run",
            f"  stage={report['stage']}",
            f"  new_condition_run_id={report['new_condition_run_id']}",
            f"  active_is_new={report['active_n2_check']['is_new_active_run']}",
            f"  suggested_execute_run_id={report['suggested_execute_run_id']}",
            f"  actual_scope_counts={report['actual_scope_counts']}",
            f"  actual_object_counts={report['actual_object_counts']}",
            f"  candidate={generation['subscription_candidate_count']} subscription={generation['dedup_subscription_count']} pull_plan={generation['market_data_pull_plan_row_count']}",
            f"  required_data_kind_counts={generation['required_data_kind_counts']}",
            f"  old_n3_stale={report['old_n3_subscription_run_is_stale']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  market_data_pulled=false market_data_fact_written=false event_outbox_written=false downstream_layers_touched=false worker_started=false",
        ]
    )


def write_subscription_refresh_reports(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    write_text(markdown_path, format_subscription_refresh_markdown(report))
    write_text(json_path, json.dumps(json_safe(report), ensure_ascii=False, indent=2, default=str) + "\n")


def normalize_db_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): json_safe(value) for key, value in row.items()}


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


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
