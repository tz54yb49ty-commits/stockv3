"""N3-EOD snapshot refresh dry-run planner.

This module builds a settlement / official close confirmation dry-run report.
It only reads N3/N4/N1 evidence and never writes EOD facts, run rows, quality
rows, outbox/inbox/checkpoint rows, downstream runtime state, or starts workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
ASSET_KINDS = ("stock", "index", "board")
IDENTITY_COLUMNS = {
    "stock": "stock_identity_key",
    "index": "index_identity_key",
    "board": "board_identity_key",
}
SNAPSHOT_TABLES = {
    "stock": "stock_realtime_daily_snapshot",
    "index": "index_realtime_daily_snapshot",
    "board": "board_realtime_daily_snapshot",
}
CLOSED_SUMMARY_TABLES = {
    "stock": "stock_closed_30m_summary",
    "index": "index_closed_30m_summary",
    "board": "board_closed_30m_summary",
}
CLOSED_SIGNAL_TABLES = {
    "stock": "stock_closed_30m_signal_enrichment",
    "index": "index_closed_30m_signal_enrichment",
    "board": "board_closed_30m_signal_enrichment",
}
EOD_SNAPSHOT_TABLES = {
    "stock": "stock_eod_snapshot",
    "index": "index_eod_snapshot",
    "board": "board_eod_snapshot",
}
EOD_RECONCILIATION_TABLES = {
    "stock": "stock_eod_reconciliation_item",
    "index": "index_eod_reconciliation_item",
    "board": "board_eod_reconciliation_item",
}
OFFICIAL_DAILY_TABLES = {
    "stock": "stock_daily_bar_fact",
    "index": "index_daily_bar_fact",
    "board": "board_daily_bar_fact",
}
N4_AUDIT_TABLES = {
    "stock": "stock_trigger_replay_audit",
    "index": "index_trigger_replay_audit",
    "board": "board_trigger_replay_audit",
}

DEFAULT_CONTRACT_PATH = "docs/N3_EOD_snapshot_refresh_contract.json"
DEFAULT_DRY_RUN_PLAN_PATH = "docs/N3_EOD_snapshot_refresh_dry_run_plan.json"
DEFAULT_SCHEMA_READINESS_PATH = "docs/N3_EOD_snapshot_schema_readiness.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N3_EOD_snapshot_business_rollback.sql"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/N3_EOD_SNAPSHOT_REFRESH_DRY_RUN_REPORT.md"
DEFAULT_JSON_REPORT_PATH = "docs/N3_EOD_snapshot_refresh_dry_run_report.json"
DEFAULT_PREFLIGHT_MARKDOWN_PATH = "docs/N3_EOD_SNAPSHOT_REFRESH_EXECUTE_PREFLIGHT.md"
DEFAULT_PREFLIGHT_JSON_PATH = "docs/N3_EOD_snapshot_refresh_execute_preflight.json"

ALLOWED_FUTURE_EXECUTE_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_eod_snapshot",
    "index_eod_snapshot",
    "board_eod_snapshot",
    "stock_eod_reconciliation_item",
    "index_eod_reconciliation_item",
    "board_eod_reconciliation_item",
]
FORBIDDEN_WRITE_TABLES = [
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
    "stock_closed_30m_signal_enrichment",
    "index_closed_30m_signal_enrichment",
    "board_closed_30m_signal_enrichment",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "C3 outbox",
    "condition tables",
    "trigger/action/user/voice/mobile/sim/position tables",
    "N4/N5/N6",
    "worker",
    "old system",
]


def build_write_scope_contract() -> dict[str, Any]:
    return {
        "allowed_future_execute_write_tables": list(ALLOWED_FUTURE_EXECUTE_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_c3_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "updates_runtime_sources": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }


def build_eod_dry_run_report(
    *,
    eod_run_id: str,
    for_trade_date: str,
    lineage_allowlist: Mapping[str, Any],
    expected_eod_snapshot_rows: Mapping[str, int],
    source_summary: Mapping[str, Any],
    official_daily_status: Mapping[str, Any],
    target_audit: Mapping[str, Any],
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    quality_items = build_quality_items(
        expected_eod_snapshot_rows=expected_eod_snapshot_rows,
        source_summary=source_summary,
        official_daily_status=official_daily_status,
        target_audit=target_audit,
        rollback_sql_path=rollback_sql_path,
    )
    quality_counts = count_quality_severities(quality_items)
    blockers = build_blockers(quality_items, official_daily_status=official_daily_status, target_audit=target_audit)
    blocked = quality_counts["P0"] > 0
    official_available = bool(official_daily_status.get("available")) and int(official_daily_status.get("missing_fact_count") or 0) == 0
    execute_final_gate_allowed = not blocked and official_available
    execute_blocker = None
    if blocked:
        execute_blocker = "dry_run_p0_blocker"
    elif not official_available:
        execute_blocker = str(official_daily_status.get("missing_code") or "missing_official_daily_fact")

    expected_rows = normalize_counts(expected_eod_snapshot_rows)
    report = {
        "stage": "N3-EOD snapshot refresh dry-run",
        "layer_role": "N3_market_data",
        "result": "DRY_RUN_BLOCKED" if blocked else "DRY_RUN_PASS",
        "blocked": blocked,
        "blockers": blockers,
        "eod_run_id": eod_run_id,
        "for_trade_date": for_trade_date,
        "lineage_allowlist": dict(lineage_allowlist),
        "expected_eod_snapshot_rows": expected_rows,
        "preview_eod_snapshot_rows": dict(source_summary.get("b1_snapshot_rows") or expected_rows),
        "source_summary": normalize_jsonable(source_summary),
        "official_daily_status": normalize_jsonable(official_daily_status),
        "reconciliation_item_preview_counts": build_reconciliation_preview_counts(
            official_daily_status=official_daily_status,
            source_summary=source_summary,
        ),
        "stale_candidate_count": build_stale_candidate_count(source_summary=source_summary, official_daily_status=official_daily_status),
        "target_audit": normalize_jsonable(target_audit),
        "write_scope": build_write_scope_contract(),
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "execute_final_gate_allowed": execute_final_gate_allowed,
        "execute_blocker": execute_blocker,
        "rollback_sql_path": rollback_sql_path,
        "rollback_scope": {
            "business_rollback_scope": "eod_run_id only",
            "deletes": [
                "stock/index/board_eod_reconciliation_item",
                "stock/index/board_eod_snapshot",
                "common_market_data_quality_item",
                "common_market_data_run",
            ],
            "does_not_touch": ["B1", "B2", "C2", "C2B", "C3", "N4", "N5", "N6"],
            "guarded_by_outbox_inbox_checkpoint": True,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_database": False,
            "writes_eod_snapshot": False,
            "writes_reconciliation": False,
            "writes_run_or_quality": False,
            "writes_outbox": False,
            "consumes_c3_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "market_data_pulled": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "generated_at": now_iso(),
    }
    return report


def build_eod_execute_preflight_report(dry_run_report: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if bool(dry_run_report.get("blocked")):
        blockers.extend(str(code) for code in dry_run_report.get("blockers") or [])
    if not bool(dry_run_report.get("execute_final_gate_allowed")):
        blocker = str(dry_run_report.get("execute_blocker") or "execute_final_gate_not_allowed")
        if blocker not in blockers:
            blockers.append(blocker)

    result = "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS"
    return {
        "stage": "N3-EOD snapshot refresh execute preflight",
        "layer_role": "N3_market_data",
        "result": result,
        "blocked": bool(blockers),
        "blockers": blockers,
        "eod_run_id": dry_run_report.get("eod_run_id"),
        "for_trade_date": dry_run_report.get("for_trade_date"),
        "execute_final_gate_allowed": not blockers,
        "dry_run_result": dry_run_report.get("result"),
        "official_daily_status": dry_run_report.get("official_daily_status"),
        "target_audit": dry_run_report.get("target_audit"),
        "quality": dry_run_report.get("quality"),
        "write_scope": build_write_scope_contract(),
        "rollback_sql_path": dry_run_report.get("rollback_sql_path", DEFAULT_ROLLBACK_SQL_PATH),
        "side_effects": {
            "read_only_database_checks": True,
            "writes_database": False,
            "writes_outbox": False,
            "consumes_c3_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
        "generated_at": now_iso(),
    }


def build_eod_snapshot_refresh_dry_run(
    *,
    dsn: str,
    contract_path: str = DEFAULT_CONTRACT_PATH,
    dry_run_plan_path: str = DEFAULT_DRY_RUN_PLAN_PATH,
    schema_readiness_path: str = DEFAULT_SCHEMA_READINESS_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = read_json(contract_path)
    dry_run_plan = read_json(dry_run_plan_path)
    schema_readiness = read_json(schema_readiness_path)
    eod_run_id = str(contract["eod_run_id"])
    for_trade_date = str(contract["for_trade_date"])
    lineage = dict(contract.get("lineage_allowlist") or {})
    expected_rows = normalize_counts(contract.get("expected_eod_snapshot_rows") or dry_run_plan.get("expected_eod_snapshot_rows") or {})

    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        source_summary = fetch_source_summary(cur, lineage=lineage, expected_rows=expected_rows, for_trade_date=for_trade_date)
        official_daily_status = fetch_official_daily_status(cur, for_trade_date=for_trade_date, expected_rows=expected_rows)
        target_audit = fetch_target_audit(cur, eod_run_id=eod_run_id)
        target_audit["schema_readiness_result"] = schema_readiness.get("result")

    dry_run_report = build_eod_dry_run_report(
        eod_run_id=eod_run_id,
        for_trade_date=for_trade_date,
        lineage_allowlist=lineage,
        expected_eod_snapshot_rows=expected_rows,
        source_summary=source_summary,
        official_daily_status=official_daily_status,
        target_audit=target_audit,
        rollback_sql_path=rollback_sql_path,
    )
    preflight_report = build_eod_execute_preflight_report(dry_run_report)
    return dry_run_report, preflight_report


def fetch_source_summary(
    cur: Any,
    *,
    lineage: Mapping[str, Any],
    expected_rows: Mapping[str, int],
    for_trade_date: str,
) -> dict[str, Any]:
    source_runs = fetch_source_run_status(cur, lineage)
    b1_run_id = str(lineage.get("source_b1_snapshot_run_id") or "")
    c2_run_id = str(lineage.get("source_c2_run_id") or "")
    c2b_run_id = str(lineage.get("source_c2b_run_id") or "")
    c3_run_id = str(lineage.get("source_c3_run_id") or "")
    n4_audit_run_id = str(lineage.get("source_n4_replay_audit_run_id") or "")
    return {
        "source_runs": source_runs,
        "b1_snapshot_rows": fetch_snapshot_counts(cur, b1_run_id),
        "c2_summary_rows": fetch_c2_summary_counts(cur, c2_run_id),
        "c2b_enrichment_rows": fetch_c2b_counts(cur, c2b_run_id),
        "c3_outbox": fetch_c3_outbox_status(cur, c3_run_id),
        "n4_replay_audit": fetch_n4_replay_audit_counts(cur, n4_audit_run_id),
        "expected_source_rows": dict(expected_rows),
        "for_trade_date": for_trade_date,
    }


def fetch_source_run_status(cur: Any, lineage: Mapping[str, Any]) -> dict[str, Any]:
    market_run_keys = [
        "source_subscription_run_id",
        "source_b1_snapshot_run_id",
        "source_c2_run_id",
        "source_c2b_run_id",
        "source_c3_run_id",
    ]
    statuses: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    condition_run_id = str(lineage.get("source_condition_run_id") or "")
    if condition_run_id:
        row = fetch_one(cur, "common_condition_run", "run_id", condition_run_id)
        statuses["source_condition_run_id"] = {"run_id": condition_run_id, "status": row.get("status") if row else None, "exists": row is not None}
        if row is None or str(row.get("status")) != "passed":
            missing.append("source_condition_run_id")

    for key in market_run_keys:
        run_id = str(lineage.get(key) or "")
        if not run_id:
            missing.append(key)
            statuses[key] = {"run_id": run_id, "status": None, "exists": False}
            continue
        row = fetch_one(cur, "common_market_data_run", "run_id", run_id)
        statuses[key] = {"run_id": run_id, "status": row.get("status") if row else None, "exists": row is not None}
        if row is None or str(row.get("status")) != "passed":
            missing.append(key)

    n4_run_id = str(lineage.get("source_n4_replay_audit_run_id") or "")
    if n4_run_id:
        row = fetch_one(cur, "common_trigger_run", "run_id", n4_run_id)
        statuses["source_n4_replay_audit_run_id"] = {"run_id": n4_run_id, "status": row.get("status") if row else None, "exists": row is not None}
        if row is None or str(row.get("status")) != "passed":
            missing.append("source_n4_replay_audit_run_id")

    return {
        "passed": len(missing) == 0,
        "missing_or_not_passed": missing,
        "status_by_source": statuses,
    }


def fetch_snapshot_counts(cur: Any, run_id: str) -> dict[str, int]:
    counts = {asset: count_where(cur, SNAPSHOT_TABLES[asset], "run_id = %s", (run_id,)) for asset in ASSET_KINDS}
    counts["total"] = sum(counts.values())
    return counts


def fetch_c2_summary_counts(cur: Any, c2_run_id: str) -> dict[str, Any]:
    by_asset = {asset: count_where(cur, CLOSED_SUMMARY_TABLES[asset], "run_id = %s", (c2_run_id,)) for asset in ASSET_KINDS}
    status_counter: Counter[str] = Counter()
    for asset in ASSET_KINDS:
        if not table_exists(cur, CLOSED_SUMMARY_TABLES[asset]):
            continue
        cur.execute(
            f"SELECT closed_status, count(*)::int AS c FROM {CLOSED_SUMMARY_TABLES[asset]} WHERE run_id=%s GROUP BY closed_status",
            (c2_run_id,),
        )
        for row in cur.fetchall():
            status_counter[str(row["closed_status"] or "unknown")] += int(row["c"])
    return {
        "by_asset": {**by_asset, "total": sum(by_asset.values())},
        "total": sum(by_asset.values()),
        "closed": int(status_counter.get("closed", 0)),
        "partial": int(status_counter.get("partial", 0)),
        "missing": int(status_counter.get("missing", 0)),
        "failed": int(status_counter.get("failed", 0)),
        "status_distribution": dict(status_counter),
    }


def fetch_c2b_counts(cur: Any, c2b_run_id: str) -> dict[str, Any]:
    by_asset = {asset: count_where(cur, CLOSED_SIGNAL_TABLES[asset], "c2b_run_id = %s", (c2b_run_id,)) for asset in ASSET_KINDS}
    signal_counter: Counter[str] = Counter()
    quality_counter: Counter[str] = Counter()
    for asset in ASSET_KINDS:
        table = CLOSED_SIGNAL_TABLES[asset]
        if not table_exists(cur, table):
            continue
        cur.execute(
            f"""
            SELECT closed_signal_status, closed_signal_quality_status, count(*)::int AS c
            FROM {table}
            WHERE c2b_run_id=%s
            GROUP BY closed_signal_status, closed_signal_quality_status
            """,
            (c2b_run_id,),
        )
        for row in cur.fetchall():
            signal_counter[str(row["closed_signal_status"] or "unknown")] += int(row["c"])
            quality_counter[str(row["closed_signal_quality_status"] or "unknown")] += int(row["c"])
    return {
        "by_asset": {**by_asset, "total": sum(by_asset.values())},
        "total": sum(by_asset.values()),
        "computable": sum(count for status, count in quality_counter.items() if status == "passed"),
        "unknown": int(signal_counter.get("unknown", 0)),
        "missing": int(quality_counter.get("missing", 0)),
        "signal_distribution": dict(signal_counter),
        "quality_distribution": dict(quality_counter),
    }


def fetch_c3_outbox_status(cur: Any, c3_run_id: str) -> dict[str, int]:
    if not table_exists(cur, "common_event_outbox"):
        return {"total": 0}
    cur.execute(
        """
        SELECT status, count(*)::int AS c
        FROM common_event_outbox
        WHERE source_run_id=%s
        GROUP BY status
        """,
        (c3_run_id,),
    )
    counts = {str(row["status"] or "unknown"): int(row["c"]) for row in cur.fetchall()}
    counts["total"] = sum(counts.values())
    counts.setdefault("pending", 0)
    counts.setdefault("delivered", 0)
    counts.setdefault("delivering", 0)
    return counts


def fetch_n4_replay_audit_counts(cur: Any, replay_run_id: str) -> dict[str, Any]:
    by_asset = {asset: count_where(cur, N4_AUDIT_TABLES[asset], "replay_run_id = %s", (replay_run_id,)) for asset in ASSET_KINDS}
    classification_counter: Counter[str] = Counter()
    for asset in ASSET_KINDS:
        table = N4_AUDIT_TABLES[asset]
        if not table_exists(cur, table):
            continue
        cur.execute(
            f"SELECT replay_classification, count(*)::int AS c FROM {table} WHERE replay_run_id=%s GROUP BY replay_classification",
            (replay_run_id,),
        )
        for row in cur.fetchall():
            classification_counter[str(row["replay_classification"] or "unknown")] += int(row["c"])
    return {
        "by_asset": {**by_asset, "total": sum(by_asset.values())},
        "total": sum(by_asset.values()),
        "classification_distribution": dict(classification_counter),
        "missing": int(classification_counter.get("missing", 0)),
        "not_ready": int(classification_counter.get("not_ready", 0)),
    }


def fetch_official_daily_status(cur: Any, *, for_trade_date: str, expected_rows: Mapping[str, int]) -> dict[str, Any]:
    coverage: dict[str, int] = {}
    by_asset_missing: dict[str, int] = {}
    source_versions: dict[str, list[str]] = {}
    for asset in ASSET_KINDS:
        table = OFFICIAL_DAILY_TABLES[asset]
        identity_col = IDENTITY_COLUMNS[asset]
        expected = int(expected_rows.get(asset, 0))
        if not table_exists(cur, table):
            coverage[asset] = 0
            by_asset_missing[asset] = expected
            source_versions[asset] = []
            continue
        predicate = "trade_date = %s"
        params: tuple[Any, ...] = (for_trade_date,)
        if asset == "stock" and column_exists(cur, table, "official_daily_proof"):
            predicate += " AND official_daily_proof IS TRUE"
        cur.execute(f"SELECT count(DISTINCT {identity_col})::int AS c FROM {table} WHERE {predicate}", params)
        count = int(cur.fetchone()["c"])
        coverage[asset] = count
        by_asset_missing[asset] = max(expected - count, 0)
        cur.execute(f"SELECT DISTINCT source_version FROM {table} WHERE trade_date=%s AND source_version IS NOT NULL ORDER BY source_version", (for_trade_date,))
        source_versions[asset] = [str(row["source_version"]) for row in cur.fetchall()]
    coverage["total"] = sum(coverage.values())
    by_asset_missing["total"] = sum(by_asset_missing.values())
    active_rows = fetch_active_daily_source_versions(cur)
    available = by_asset_missing["total"] == 0 and coverage["total"] >= int(expected_rows.get("total", 0))
    return {
        "available": available,
        "missing_code": None if available else "missing_official_daily_fact",
        "missing_fact_count": by_asset_missing["total"],
        "missing_by_asset": by_asset_missing,
        "coverage": coverage,
        "expected": dict(expected_rows),
        "source_versions_for_trade_date": source_versions,
        "active_source_versions": active_rows,
    }


def fetch_active_daily_source_versions(cur: Any) -> list[dict[str, Any]]:
    if not table_exists(cur, "common_active_source_version"):
        return []
    cur.execute(
        """
        SELECT data_domain, data_type, scope_key, source_version, source_batch_id
        FROM common_active_source_version
        WHERE data_type IN ('stock_daily', 'index_daily', 'board_daily')
        ORDER BY data_domain, data_type, scope_key
        """
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_target_audit(cur: Any, *, eod_run_id: str) -> dict[str, Any]:
    snapshot_rows = {
        asset: count_where(cur, EOD_SNAPSHOT_TABLES[asset], "eod_run_id = %s", (eod_run_id,))
        for asset in ASSET_KINDS
    }
    reconciliation_rows = {
        asset: count_where(cur, EOD_RECONCILIATION_TABLES[asset], "eod_run_id = %s", (eod_run_id,))
        for asset in ASSET_KINDS
    }
    snapshot_rows["total"] = sum(snapshot_rows.values())
    reconciliation_rows["total"] = sum(reconciliation_rows.values())
    return {
        "schema_tables_exist": all(table_exists(cur, table) for table in [*EOD_SNAPSHOT_TABLES.values(), *EOD_RECONCILIATION_TABLES.values()]),
        "eod_run_exists": count_where(cur, "common_market_data_run", "run_id = %s", (eod_run_id,)) > 0,
        "target_rows_for_eod_run": snapshot_rows,
        "reconciliation_rows_for_eod_run": reconciliation_rows,
        "quality_rows_for_eod_run": count_where(cur, "common_market_data_quality_item", "run_id = %s", (eod_run_id,)),
        "outbox_rows_for_eod_run": count_where(cur, "common_event_outbox", "source_run_id = %s", (eod_run_id,)),
        "inbox_rows_for_eod_run": count_where(cur, "common_event_inbox", "source_run_id = %s", (eod_run_id,)),
        "checkpoint_rows_for_eod_run": count_where(
            cur,
            "common_event_consumer_checkpoint",
            "checkpoint_payload::text LIKE %s",
            (f"%{eod_run_id}%",),
        ),
    }


def build_quality_items(
    *,
    expected_eod_snapshot_rows: Mapping[str, int],
    source_summary: Mapping[str, Any],
    official_daily_status: Mapping[str, Any],
    target_audit: Mapping[str, Any],
    rollback_sql_path: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    schema_ok = bool(target_audit.get("schema_tables_exist"))
    items.append(quality_item("P0", "passed" if schema_ok else "failed", "n3_eod_schema_019_tables_exist", "019 EOD schema tables exist"))

    source_runs = source_summary.get("source_runs") or {}
    source_ok = bool(source_runs.get("passed"))
    items.append(
        quality_item(
            "P0",
            "passed" if source_ok else "failed",
            "n3_eod_source_runs_passed",
            "Allowlisted source runs are present and passed",
            details={"missing_or_not_passed": list(source_runs.get("missing_or_not_passed") or [])},
        )
    )

    b1_rows = normalize_counts(source_summary.get("b1_snapshot_rows") or {})
    expected_rows = normalize_counts(expected_eod_snapshot_rows)
    b1_ok = b1_rows.get("total") == expected_rows.get("total")
    items.append(
        quality_item(
            "P0",
            "passed" if b1_ok else "failed",
            "n3_eod_b1_snapshot_rows_match_expected",
            "B1 snapshot row count matches EOD expected object count",
            expected=str(expected_rows),
            actual=str(b1_rows),
        )
    )

    if bool(target_audit.get("eod_run_exists")):
        items.append(quality_item("P0", "failed", "eod_run_id_already_exists", "EOD run id must not exist before execute"))
    else:
        items.append(quality_item("P0", "passed", "eod_run_id_absent", "EOD run id absent before execute"))

    target_total = int((target_audit.get("target_rows_for_eod_run") or {}).get("total") or 0)
    rec_total = int((target_audit.get("reconciliation_rows_for_eod_run") or {}).get("total") or 0)
    rows_zero = target_total == 0 and rec_total == 0
    items.append(
        quality_item(
            "P0",
            "passed" if rows_zero else "failed",
            "target_rows_not_zero" if not rows_zero else "target_eod_rows_zero",
            "EOD target rows for eod_run_id are zero",
            actual=f"snapshot={target_total}; reconciliation={rec_total}",
        )
    )

    event_boundary_counts = {
        "quality": int(target_audit.get("quality_rows_for_eod_run") or 0),
        "outbox": int(target_audit.get("outbox_rows_for_eod_run") or 0),
        "inbox": int(target_audit.get("inbox_rows_for_eod_run") or 0),
        "checkpoint": int(target_audit.get("checkpoint_rows_for_eod_run") or 0),
    }
    event_boundary_ok = all(value == 0 for value in event_boundary_counts.values())
    items.append(
        quality_item(
            "P0",
            "passed" if event_boundary_ok else "failed",
            "event_boundary_rows_zero_for_eod_run_id",
            "Run/quality/outbox/inbox/checkpoint scoped EOD rows are zero",
            actual=str(event_boundary_counts),
        )
    )

    c3 = source_summary.get("c3_outbox") or {}
    c3_delivered = int(c3.get("delivered") or 0) + int(c3.get("delivering") or 0)
    items.append(
        quality_item(
            "P0",
            "passed" if c3_delivered == 0 else "failed",
            "c3_outbox_unconsumed",
            "C3 outbox remains unconsumed for EOD dry-run",
            actual=str(c3),
        )
    )

    official_missing = int(official_daily_status.get("missing_fact_count") or 0)
    official_available = bool(official_daily_status.get("available"))
    items.append(
        quality_item(
            "P1",
            "passed" if official_available else "warning",
            "missing_official_daily_fact",
            "N1 official daily fact coverage for EOD settlement",
            expected=str(expected_rows),
            actual=str(official_daily_status.get("coverage") or {}),
            details={"missing_fact_count": official_missing},
        )
    )

    c2_missing = int((source_summary.get("c2_summary_rows") or {}).get("missing") or 0)
    items.append(
        quality_item(
            "P1",
            "passed" if c2_missing == 0 else "warning",
            "n3_eod_c2_missing_summary_rows",
            "C2 missing summaries remain settlement evidence",
            actual=str(c2_missing),
        )
    )

    n4_missing = int((source_summary.get("n4_replay_audit") or {}).get("missing") or 0)
    items.append(
        quality_item(
            "P1",
            "passed" if n4_missing == 0 else "warning",
            "n3_eod_n4_replay_audit_missing_rows",
            "N4 C3 replay audit missing rows remain evidence",
            actual=str(n4_missing),
        )
    )

    rollback_exists = Path(rollback_sql_path).exists()
    items.append(
        quality_item(
            "P0",
            "passed" if rollback_exists else "failed",
            "n3_eod_business_rollback_sql_exists",
            "EOD business rollback SQL exists",
            actual=rollback_sql_path,
        )
    )
    return items


def build_blockers(
    quality_items: list[Mapping[str, Any]],
    *,
    official_daily_status: Mapping[str, Any],
    target_audit: Mapping[str, Any],
) -> list[str]:
    blockers = [
        str(item.get("gate_code"))
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") in {"failed", "warning"}
    ]
    if bool(target_audit.get("eod_run_exists")) and "eod_run_id_already_exists" not in blockers:
        blockers.append("eod_run_id_already_exists")
    target_total = int((target_audit.get("target_rows_for_eod_run") or {}).get("total") or 0)
    if target_total and "target_rows_not_zero" not in blockers:
        blockers.append("target_rows_not_zero")
    return blockers


def build_reconciliation_preview_counts(*, official_daily_status: Mapping[str, Any], source_summary: Mapping[str, Any]) -> dict[str, int]:
    return {
        "official_daily_missing": int(official_daily_status.get("missing_fact_count") or 0),
        "official_price_diff": 0,
        "official_volume_diff": 0,
        "official_amount_diff": 0,
        "b1_snapshot_diff": 0,
        "c2_closed_summary_missing": int((source_summary.get("c2_summary_rows") or {}).get("missing") or 0),
        "c2b_signal_enrichment_unknown": int((source_summary.get("c2b_enrichment_rows") or {}).get("unknown") or 0),
        "c3_outbox_status": 1,
        "n4_replay_audit_missing": int((source_summary.get("n4_replay_audit") or {}).get("missing") or 0),
        "stale_candidate": 0,
        "boundary_check": 1,
    }


def build_stale_candidate_count(*, source_summary: Mapping[str, Any], official_daily_status: Mapping[str, Any]) -> int:
    if not official_daily_status.get("available"):
        return 0
    return 0


def format_dry_run_markdown(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    expected = report.get("expected_eod_snapshot_rows") or {}
    official = report.get("official_daily_status") or {}
    source = report.get("source_summary") or {}
    c3 = source.get("c3_outbox") or {}
    lines = [
        "# N3-EOD Snapshot Refresh Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- result: `{report.get('result')}`",
        f"- blocked: `{report.get('blocked')}`",
        f"- eod_run_id: `{report.get('eod_run_id')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- expected_eod_snapshot_rows: `{expected}`",
        f"- official_daily_available: `{official.get('available')}`",
        f"- official_daily_missing_count: `{official.get('missing_fact_count')}`",
        f"- execute_final_gate_allowed: `{report.get('execute_final_gate_allowed')}`",
        f"- execute_blocker: `{report.get('execute_blocker')}`",
        f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
        "",
        "## Source Summary",
        "",
        f"- B1 snapshot rows: `{source.get('b1_snapshot_rows')}`",
        f"- C2 summary rows: `{source.get('c2_summary_rows')}`",
        f"- C2B enrichment rows: `{source.get('c2b_enrichment_rows')}`",
        f"- C3 outbox status: `{c3}`",
        f"- N4 replay audit: `{source.get('n4_replay_audit')}`",
        "",
        "## Reconciliation Preview",
        "",
        f"- counts: `{report.get('reconciliation_item_preview_counts')}`",
        f"- stale_candidate_count: `{report.get('stale_candidate_count')}`",
        "",
        "## Boundary",
        "",
        f"- writes_database: `{(report.get('side_effects') or {}).get('writes_database')}`",
        f"- writes_outbox: `{(report.get('side_effects') or {}).get('writes_outbox')}`",
        f"- consumes_c3_outbox: `{(report.get('side_effects') or {}).get('consumes_c3_outbox')}`",
        f"- downstream_layers_touched: `{(report.get('side_effects') or {}).get('downstream_layers_touched')}`",
        f"- worker_started: `{(report.get('side_effects') or {}).get('worker_started')}`",
        "",
        "## Decision",
        "",
        "EOD business execute remains blocked unless this report and execute preflight both allow the final gate.",
        "",
    ]
    return "\n".join(lines)


def format_preflight_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# N3-EOD Snapshot Refresh Execute Preflight",
        "",
        "## Summary",
        "",
        f"- result: `{report.get('result')}`",
        f"- blocked: `{report.get('blocked')}`",
        f"- blockers: `{report.get('blockers')}`",
        f"- eod_run_id: `{report.get('eod_run_id')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- execute_final_gate_allowed: `{report.get('execute_final_gate_allowed')}`",
        "",
        "## Boundary",
        "",
        f"- write_scope: `{report.get('write_scope')}`",
        f"- side_effects: `{report.get('side_effects')}`",
        "",
        "## Decision",
        "",
        "Execute requires an explicit final gate and remains blocked if listed blockers are non-empty.",
        "",
    ]
    return "\n".join(lines)


def write_report_files(
    dry_run_report: Mapping[str, Any],
    preflight_report: Mapping[str, Any],
    *,
    markdown_path: str = DEFAULT_MARKDOWN_REPORT_PATH,
    json_path: str = DEFAULT_JSON_REPORT_PATH,
    preflight_markdown_path: str = DEFAULT_PREFLIGHT_MARKDOWN_PATH,
    preflight_json_path: str = DEFAULT_PREFLIGHT_JSON_PATH,
) -> None:
    write_text(markdown_path, format_dry_run_markdown(dry_run_report))
    write_json(json_path, dry_run_report)
    write_text(preflight_markdown_path, format_preflight_markdown(preflight_report))
    write_json(preflight_json_path, preflight_report)


def format_summary(dry_run_report: Mapping[str, Any], preflight_report: Mapping[str, Any]) -> str:
    quality = dry_run_report.get("quality") or {}
    official = dry_run_report.get("official_daily_status") or {}
    expected = dry_run_report.get("expected_eod_snapshot_rows") or {}
    lines = [
        f"result={dry_run_report.get('result')}",
        f"preflight={preflight_report.get('result')}",
        f"eod_run_id={dry_run_report.get('eod_run_id')}",
        f"expected_rows={expected}",
        f"official_daily_available={official.get('available')}",
        f"official_daily_missing_count={official.get('missing_fact_count')}",
        f"P0/P1/P2={quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
        f"execute_final_gate_allowed={preflight_report.get('execute_final_gate_allowed')}",
        f"blockers={preflight_report.get('blockers')}",
    ]
    return "\n".join(lines)


def read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str, data: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def fetch_one(cur: Any, table: str, key_col: str, value: str) -> dict[str, Any] | None:
    if not table_exists(cur, table):
        return None
    cur.execute(f"SELECT * FROM {table} WHERE {key_col}=%s", (value,))
    row = cur.fetchone()
    return dict(row) if row else None


def count_where(cur: Any, table: str, predicate: str, params: tuple[Any, ...]) -> int:
    if not table_exists(cur, table):
        return 0
    cur.execute(f"SELECT count(*)::int AS c FROM {table} WHERE {predicate}", params)
    return int(cur.fetchone()["c"])


def table_exists(cur: Any, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS reg", (f"public.{table}",))
    return cur.fetchone()["reg"] is not None


def column_exists(cur: Any, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def normalize_counts(counts: Mapping[str, Any]) -> dict[str, int]:
    out = {asset: int(counts.get(asset) or 0) for asset in ASSET_KINDS}
    out["total"] = int(counts.get("total") or sum(out.values()))
    return out


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): normalize_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [normalize_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).isoformat()
