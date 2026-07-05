"""N1 official daily fact ingestion dry-run planning.

This module only builds read-only reports for N1 official daily fact coverage.
It does not call external market data sources, execute SQL writes, write
PostgreSQL facts, write Parquet, update active source versions, consume outbox
events, or enter downstream layers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import json
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
ASSET_KINDS = ("stock", "index", "board")
CONTRACT_BATCH_ID = "official_daily_ingest_20260525_v1"
CONTRACT_SOURCE_VERSION = CONTRACT_BATCH_ID
SOURCE_VERSIONS = {
    "stock": "stock_daily_20260525_v1",
    "index": "index_daily_20260525_v1",
    "board": "board_daily_20260525_v1",
}
FIXED_9_INDEX_IDENTITIES = (
    "index:SH:000905",
    "index:SZ:399303",
    "index:SH:000001",
    "index:SH:000852",
    "index:SZ:399001",
    "index:SZ:399006",
    "index:SH:000300",
    "index:SH:000016",
    "index:SH:000688",
)
DAILY_TABLES = {
    "stock": "stock_daily_bar_fact",
    "index": "index_daily_bar_fact",
    "board": "board_daily_bar_fact",
}
IDENTITY_COLUMNS = {
    "stock": "stock_identity_key",
    "index": "index_identity_key",
    "board": "board_identity_key",
}
ACTIVE_DATA_TYPES = {
    "stock": "stock_daily",
    "index": "index_daily",
    "board": "board_daily",
}
SOURCE_FETCH_PLAN = {
    "stock": {
        "target_table": "stock_daily_bar_fact",
        "source": "Tushare daily + adj_factor proof",
        "actual_fetch": False,
        "proof": "official_daily_proof=true only when daily and adj_factor both exist",
    },
    "index": {
        "target_table": "index_daily_bar_fact",
        "source": "TDX/Mootdx preferred; Tushare index_daily fallback",
        "actual_fetch": False,
        "required_fixed_9": list(FIXED_9_INDEX_IDENTITIES),
    },
    "board": {
        "target_table": "board_daily_bar_fact",
        "source": "TDX/Mootdx industry board daily",
        "actual_fetch": False,
        "required_code_shape": "^881[0-9]{3}$",
    },
}
ALLOWED_FUTURE_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
)
FORBIDDEN_SCOPE = (
    "N3 EOD snapshot tables",
    "C3 outbox",
    "condition tables",
    "trigger/action/user/voice/mobile/sim/position tables",
    "Parquet in initial execute contract",
    "worker",
    "old system",
    "real trading",
)
DEFAULT_EOD_REPORT_JSON = "docs/N3_EOD_snapshot_refresh_dry_run_report.json"
DEFAULT_JSON_REPORT_PATH = "docs/N1_official_daily_20260525_ingestion_dry_run_report.json"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/N1_OFFICIAL_DAILY_20260525_INGESTION_DRY_RUN_REPORT.md"


def build_official_daily_ingestion_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    trade_date = str(snapshot.get("for_trade_date") or "20260525")
    expected_scope = normalize_expected_scope(snapshot.get("expected_scope") or {})
    expected_counts = count_expected_scope(expected_scope)
    current_rows = normalize_counts(snapshot.get("current_fact_rows") or {})
    current_objects = normalize_counts(snapshot.get("current_fact_object_counts") or {})
    available_counts = {asset: current_objects.get(asset, 0) for asset in ASSET_KINDS}
    available_counts["total"] = sum(available_counts.values())
    missing_by_asset = build_missing_counts(expected_counts, available_counts)
    missing_samples = build_missing_samples(expected_scope, snapshot.get("current_fact_identity_keys") or {})

    quality_items = build_quality_items(
        trade_date=trade_date,
        expected_scope=expected_scope,
        missing_by_asset=missing_by_asset,
        duplicate_identity_rows=normalize_counts(snapshot.get("duplicate_identity_rows") or {}),
        same_code_contamination=normalize_counts(snapshot.get("same_code_contamination") or {}),
        active_source_versions=normalize_rows(snapshot.get("active_source_versions_for_trade_date") or []),
        target_source_version_conflicts=normalize_counts(snapshot.get("target_source_version_conflicts") or {}),
        contract_batch_exists=bool(snapshot.get("contract_batch_exists")),
    )
    quality_counts = count_quality(quality_items)
    result = "DRY_RUN_BLOCKED" if quality_counts["P0"] else "DRY_RUN_PASS"

    report = {
        "stage": "N1 official daily fact ingestion dry-run",
        "layer_role": "N1_ingestion",
        "result": result,
        "blocked": bool(quality_counts["P0"]),
        "for_trade_date": trade_date,
        "contract_batch_id": CONTRACT_BATCH_ID,
        "contract_source_version": CONTRACT_SOURCE_VERSION,
        "source_versions": dict(SOURCE_VERSIONS),
        "expected_eod_coverage_objects": expected_counts,
        "available_official_daily_before_execute": available_counts,
        "current_n1_fact": {
            asset: {
                "table": DAILY_TABLES[asset],
                "row_count": current_rows.get(asset, 0),
                "object_count": current_objects.get(asset, 0),
                "source_versions_for_trade_date": list((snapshot.get("source_versions_for_trade_date") or {}).get(asset, [])),
            }
            for asset in ASSET_KINDS
        },
        "missing_official_daily": {
            "missing_by_asset": missing_by_asset,
            "missing_identity_samples": missing_samples,
        },
        "source_fetch_plan": build_source_fetch_plan(expected_counts),
        "expected_fetched_rows": {
            "mode": "plan_only_no_external_fetch",
            "actual_fetched_rows": None,
            "minimum_eod_coverage_rows": expected_counts,
            "canonical_daily_scope": "may exceed EOD expected objects; EOD coverage subset must be complete",
        },
        "conflict_summary": {
            "contract_batch_exists": bool(snapshot.get("contract_batch_exists")),
            "target_source_version_conflicts": normalize_counts(snapshot.get("target_source_version_conflicts") or {}),
            "active_source_versions_for_trade_date": normalize_rows(snapshot.get("active_source_versions_for_trade_date") or []),
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "future_write_scope": {
            "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "future_execute_writes_postgres": True,
            "future_execute_updates_active_source_version": True,
            "future_execute_writes_parquet": False,
            "writes_outbox": False,
            "consumes_c3_outbox": False,
            "enters_n3_n4_n5_n6": False,
        },
        "contract_alignment": {
            "batch_id": CONTRACT_BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "writes_postgres": False,
            "writes_parquet": False,
            "updates_active_source_version": False,
            "enters_n3_n4_n5_n6": False,
        },
        "forbidden_scope": list(FORBIDDEN_SCOPE),
        "execute_contract": {
            "execute_runner_required": True,
            "this_cli_can_execute": False,
            "execute_requires": ["--execute", "--user-confirmed"],
            "block_on_existing_source_version": True,
            "block_on_existing_active_source_version": True,
            "postgres_only_initial_execute": True,
        },
        "eod_handoff": {
            "read_active_source_version_first": True,
            "read_by_trade_date_source_version_identity_key": True,
            "forbid_max_trade_date": True,
            "forbid_runtime_snapshot_substitution": True,
        },
        "side_effects": {
            "read_only_database_checks": bool(snapshot.get("read_only_database_checks", False)),
            "will_call_external_sources": False,
            "writes_postgres": False,
            "writes_parquet": False,
            "updates_active_source_version": False,
            "writes_outbox": False,
            "consumes_c3_outbox": False,
            "enters_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
        "generated_at": now_iso(),
    }
    return normalize_jsonable(report)


def build_snapshot_from_db(*, dsn: str, for_trade_date: str, eod_report_path: str | Path = DEFAULT_EOD_REPORT_JSON) -> dict[str, Any]:
    eod_report = load_json(eod_report_path)
    expected_rows = normalize_counts(eod_report.get("expected_eod_snapshot_rows") or {})
    subscription_run_id = str((eod_report.get("lineage_allowlist") or {}).get("source_subscription_run_id") or "")
    if not subscription_run_id:
        raise ValueError("source_subscription_run_id is required from EOD dry-run report")

    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            expected_scope = fetch_expected_scope(cur, for_trade_date=for_trade_date, subscription_run_id=subscription_run_id)
            if sum(len(rows) for rows in expected_scope.values()) == 0:
                expected_scope = fallback_expected_scope_from_counts(expected_rows)
            current_rows, current_objects, current_keys, source_versions = fetch_current_fact_state(cur, for_trade_date=for_trade_date)
            snapshot = {
                "for_trade_date": for_trade_date,
                "expected_scope": expected_scope,
                "current_fact_identity_keys": current_keys,
                "current_fact_rows": current_rows,
                "current_fact_object_counts": current_objects,
                "source_versions_for_trade_date": source_versions,
                "active_source_versions_for_trade_date": fetch_active_source_versions_for_trade_date(cur, for_trade_date=for_trade_date),
                "target_source_version_conflicts": fetch_target_source_version_conflicts(cur, for_trade_date=for_trade_date),
                "contract_batch_exists": fetch_contract_batch_exists(cur),
                "duplicate_identity_rows": fetch_duplicate_identity_rows(cur, for_trade_date=for_trade_date),
                "same_code_contamination": fetch_same_code_contamination(cur, for_trade_date=for_trade_date),
                "read_only_database_checks": True,
            }
    return snapshot


def fetch_expected_scope(cur: Any, *, for_trade_date: str, subscription_run_id: str) -> dict[str, list[dict[str, Any]]]:
    cur.execute(
        """
        SELECT asset_kind, identity_key, exchange, code, name
        FROM common_market_data_subscription
        WHERE for_trade_date = %s
          AND run_id = %s
          AND required_data_kind = 'realtime_daily_snapshot'
        GROUP BY asset_kind, identity_key, exchange, code, name
        ORDER BY asset_kind, identity_key
        """,
        (for_trade_date, subscription_run_id),
    )
    scope = {asset: [] for asset in ASSET_KINDS}
    for row in cur.fetchall():
        asset = str(row["asset_kind"])
        if asset in scope:
            scope[asset].append(
                {
                    "identity_key": str(row["identity_key"]),
                    "exchange": row.get("exchange"),
                    "code": row.get("code"),
                    "name": row.get("name"),
                }
            )
    return scope


def fetch_current_fact_state(cur: Any, *, for_trade_date: str) -> tuple[dict[str, int], dict[str, int], dict[str, set[str]], dict[str, list[str]]]:
    rows: dict[str, int] = {}
    objects: dict[str, int] = {}
    keys: dict[str, set[str]] = {}
    source_versions: dict[str, list[str]] = {}
    for asset in ASSET_KINDS:
        table = DAILY_TABLES[asset]
        identity_col = IDENTITY_COLUMNS[asset]
        predicate = "trade_date = %s"
        if asset == "stock":
            predicate += " AND official_daily_proof IS TRUE"
        cur.execute(
            f"SELECT COUNT(*)::int AS row_count, COUNT(DISTINCT {identity_col})::int AS object_count FROM {table} WHERE {predicate}",
            (for_trade_date,),
        )
        row = cur.fetchone()
        rows[asset] = int(row["row_count"])
        objects[asset] = int(row["object_count"])
        cur.execute(f"SELECT DISTINCT {identity_col} AS identity_key FROM {table} WHERE {predicate}", (for_trade_date,))
        keys[asset] = {str(item["identity_key"]) for item in cur.fetchall()}
        cur.execute(f"SELECT DISTINCT source_version FROM {table} WHERE trade_date = %s ORDER BY source_version", (for_trade_date,))
        source_versions[asset] = [str(item["source_version"]) for item in cur.fetchall()]
    return rows, objects, keys, source_versions


def fetch_active_source_versions_for_trade_date(cur: Any, *, for_trade_date: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT data_domain, data_type, scope_key, source_version, source_batch_id,
               previous_source_version, activated_at, activated_by
        FROM common_active_source_version
        WHERE scope_key = %s
          AND (
            (data_domain = 'stock' AND data_type = 'stock_daily')
            OR (data_domain = 'index' AND data_type = 'index_daily')
            OR (data_domain = 'board' AND data_type = 'board_daily')
          )
        ORDER BY data_domain, data_type
        """,
        (for_trade_date,),
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_target_source_version_conflicts(cur: Any, *, for_trade_date: str) -> dict[str, int]:
    conflicts: dict[str, int] = {}
    for asset in ASSET_KINDS:
        table = DAILY_TABLES[asset]
        source_version = SOURCE_VERSIONS[asset]
        cur.execute(
            f"SELECT COUNT(*)::int AS c FROM {table} WHERE trade_date = %s AND source_version = %s",
            (for_trade_date, source_version),
        )
        conflicts[asset] = int(cur.fetchone()["c"])
    return conflicts


def fetch_contract_batch_exists(cur: Any) -> bool:
    cur.execute("SELECT EXISTS (SELECT 1 FROM common_ingest_batch WHERE batch_id = %s) AS exists", (CONTRACT_BATCH_ID,))
    return bool(cur.fetchone()["exists"])


def fetch_duplicate_identity_rows(cur: Any, *, for_trade_date: str) -> dict[str, int]:
    duplicates: dict[str, int] = {}
    for asset in ASSET_KINDS:
        table = DAILY_TABLES[asset]
        identity_col = IDENTITY_COLUMNS[asset]
        cur.execute(
            f"""
            SELECT COUNT(*)::int AS c
            FROM (
              SELECT {identity_col}, trade_date, source_version
              FROM {table}
              WHERE trade_date = %s
              GROUP BY {identity_col}, trade_date, source_version
              HAVING COUNT(*) > 1
            ) d
            """,
            (for_trade_date,),
        )
        duplicates[asset] = int(cur.fetchone()["c"])
    return duplicates


def fetch_same_code_contamination(cur: Any, *, for_trade_date: str) -> dict[str, int]:
    checks = {
        "stock": "stock_identity_key NOT LIKE 'stock:%%' OR code LIKE '88%%'",
        "index": "index_identity_key NOT LIKE 'index:%%'",
        "board": "board_identity_key NOT LIKE 'board:TDX:%%' OR board_code NOT LIKE '881%%'",
    }
    result: dict[str, int] = {}
    for asset, predicate in checks.items():
        table = DAILY_TABLES[asset]
        cur.execute(f"SELECT COUNT(*)::int AS c FROM {table} WHERE trade_date = %s AND ({predicate})", (for_trade_date,))
        result[asset] = int(cur.fetchone()["c"])
    return result


def build_quality_items(
    *,
    trade_date: str,
    expected_scope: Mapping[str, Sequence[Mapping[str, Any]]],
    missing_by_asset: Mapping[str, int],
    duplicate_identity_rows: Mapping[str, int],
    same_code_contamination: Mapping[str, int],
    active_source_versions: Sequence[Mapping[str, Any]],
    target_source_version_conflicts: Mapping[str, int],
    contract_batch_exists: bool,
) -> list[dict[str, Any]]:
    fixed_present = {row.get("identity_key") for row in expected_scope.get("index", [])}
    fixed_missing = sorted(set(FIXED_9_INDEX_IDENTITIES) - {str(value) for value in fixed_present if value})
    board_bad = [
        str(row.get("identity_key") or row.get("code") or "")
        for row in expected_scope.get("board", [])
        if not is_881_board(row)
    ]
    stock_bad = [
        str(row.get("identity_key") or row.get("code") or "")
        for row in expected_scope.get("stock", [])
        if str(row.get("code") or "").startswith("88") or not str(row.get("identity_key") or "").startswith("stock:")
    ]
    source_conflict_total = sum(int(target_source_version_conflicts.get(asset, 0)) for asset in ASSET_KINDS)
    duplicate_total = sum(int(duplicate_identity_rows.get(asset, 0)) for asset in ASSET_KINDS)
    contamination_total = sum(int(same_code_contamination.get(asset, 0)) for asset in ASSET_KINDS)

    return [
        quality_item("contract_batch_absent", not contract_batch_exists, "batch absent", str(contract_batch_exists), {"batch_id": CONTRACT_BATCH_ID}),
        quality_item(
            "existing_source_version_conflict",
            source_conflict_total == 0,
            "0",
            str(source_conflict_total),
            {"by_asset": {asset: int(target_source_version_conflicts.get(asset, 0)) for asset in ASSET_KINDS}},
        ),
        quality_item(
            "existing_active_source_version_conflict",
            len(active_source_versions) == 0,
            "0 active rows for 20260525 stock/index/board daily",
            str(len(active_source_versions)),
            {"active_source_versions": normalize_rows(active_source_versions)},
        ),
        quality_item("fixed_9_index_scope_coverage", not fixed_missing, "9/9", str(9 - len(fixed_missing)), {"missing": fixed_missing}),
        quality_item("board_881_scope_coverage", not board_bad, "0 non-881 board identities", str(len(board_bad)), {"bad": board_bad[:50]}),
        quality_item("stock_expected_scope_code_shape", not stock_bad, "0 stock 88xxxx or non-stock identities", str(len(stock_bad)), {"bad": stock_bad[:50]}),
        quality_item(
            "duplicate_identity_key",
            duplicate_total == 0,
            "0",
            str(duplicate_total),
            {"by_asset": {asset: int(duplicate_identity_rows.get(asset, 0)) for asset in ASSET_KINDS}},
        ),
        quality_item(
            "same_code_contamination",
            contamination_total == 0,
            "0",
            str(contamination_total),
            {"by_asset": {asset: int(same_code_contamination.get(asset, 0)) for asset in ASSET_KINDS}},
        ),
        quality_item("dry_run_no_write_scope", True, "no writes", "no writes"),
        quality_item("forbidden_source_usage", True, "0 forbidden source reads", "0"),
        quality_item(
            "missing_official_daily_before_execute",
            int(missing_by_asset.get("total", 0)) == 0,
            "0",
            str(int(missing_by_asset.get("total", 0))),
            {"by_asset": dict(missing_by_asset)},
            severity="P1",
            warning_when_false=True,
        ),
        quality_item("source_fetch_not_executed_by_design", False, "external source fetch not run in dry-run", "plan-only", severity="P1", warning_when_false=True),
        quality_item("parquet_write_deferred", False, "PostgreSQL-only first execute contract", "Parquet skipped by design", severity="P2", warning_when_false=True),
    ]


def quality_item(
    gate_name: str,
    passed: bool,
    expected: str,
    actual: str,
    details: Mapping[str, Any] | None = None,
    *,
    severity: str = "P0",
    warning_when_false: bool = False,
) -> dict[str, Any]:
    status = "passed" if passed else ("warning" if warning_when_false else "failed")
    return {
        "gate_name": gate_name,
        "severity": severity,
        "status": status,
        "expected_value": expected,
        "actual_value": actual,
        "details": normalize_jsonable(dict(details or {})),
    }


def build_source_fetch_plan(expected_counts: Mapping[str, int]) -> dict[str, Any]:
    plan = json.loads(json.dumps(SOURCE_FETCH_PLAN, ensure_ascii=False))
    for asset in ASSET_KINDS:
        plan[asset]["minimum_eod_coverage"] = int(expected_counts.get(asset, 0))
    return plan


def build_missing_counts(expected_counts: Mapping[str, int], available_counts: Mapping[str, int]) -> dict[str, int]:
    result = {
        asset: max(int(expected_counts.get(asset, 0)) - int(available_counts.get(asset, 0)), 0)
        for asset in ASSET_KINDS
    }
    result["total"] = sum(result.values())
    return result


def build_missing_samples(
    expected_scope: Mapping[str, Sequence[Mapping[str, Any]]],
    current_fact_identity_keys: Mapping[str, Any],
    *,
    limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    samples: dict[str, list[dict[str, Any]]] = {}
    for asset in ASSET_KINDS:
        current = {str(value) for value in current_fact_identity_keys.get(asset, set())}
        missing: list[dict[str, Any]] = []
        for row in expected_scope.get(asset, []):
            identity_key = str(row.get("identity_key") or "")
            if identity_key and identity_key not in current:
                missing.append(
                    {
                        "identity_key": identity_key,
                        "exchange": row.get("exchange"),
                        "code": row.get("code"),
                        "name": row.get("name"),
                    }
                )
            if len(missing) >= limit:
                break
        samples[asset] = missing
    return samples


def render_markdown_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    missing = (report.get("missing_official_daily") or {}).get("missing_by_asset") or {}
    return "\n".join(
        [
            "# N1 Official Daily 20260525 Ingestion Dry-Run Report",
            "",
            "## Summary",
            "",
            f"- result: `{report.get('result')}`",
            f"- layer_role: `{report.get('layer_role')}`",
            f"- for_trade_date: `{report.get('for_trade_date')}`",
            f"- contract_batch_id: `{report.get('contract_batch_id')}`",
            f"- stock source_version: `{(report.get('source_versions') or {}).get('stock')}`",
            f"- index source_version: `{(report.get('source_versions') or {}).get('index')}`",
            f"- board source_version: `{(report.get('source_versions') or {}).get('board')}`",
            f"- expected_eod_coverage_objects: `{report.get('expected_eod_coverage_objects')}`",
            f"- available_official_daily_before_execute: `{report.get('available_official_daily_before_execute')}`",
            f"- missing_official_daily: `{missing}`",
            f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
            "",
            "## Source Fetch Plan",
            "",
            "- stock: `Tushare daily + adj_factor proof`",
            "- index: `TDX/Mootdx preferred; Tushare index_daily fallback`",
            "- board: `TDX/Mootdx industry board daily`",
            "- actual_fetch: `False`",
            "",
            "## Boundary",
            "",
            f"- writes_postgres: `{(report.get('side_effects') or {}).get('writes_postgres')}`",
            f"- writes_parquet: `{(report.get('side_effects') or {}).get('writes_parquet')}`",
            f"- updates_active_source_version: `{(report.get('side_effects') or {}).get('updates_active_source_version')}`",
            f"- enters_n3_n4_n5_n6: `{(report.get('side_effects') or {}).get('enters_n3_n4_n5_n6')}`",
            f"- worker_started: `{(report.get('side_effects') or {}).get('worker_started')}`",
            "",
            "## Decision",
            "",
            "This runner is plan-only. Future ingestion still requires a separate N1 execute runner and explicit execute gate.",
            "",
        ]
    )


def write_report_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n")
    markdown_target.write_text(render_markdown_report(report))


def normalize_expected_scope(value: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    scope: dict[str, list[dict[str, Any]]] = {}
    for asset in ASSET_KINDS:
        rows = value.get(asset) or []
        scope[asset] = [dict(row) for row in rows]
    return scope


def count_expected_scope(expected_scope: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, int]:
    counts = {asset: len(expected_scope.get(asset, [])) for asset in ASSET_KINDS}
    counts["total"] = sum(counts.values())
    return counts


def normalize_counts(value: Mapping[str, Any]) -> dict[str, int]:
    counts = {asset: int(value.get(asset, 0) or 0) for asset in ASSET_KINDS}
    if "total" in value:
        counts["total"] = int(value.get("total") or 0)
    return counts


def normalize_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_jsonable(dict(row)) for row in rows]


def count_quality(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter({"P0": 0, "P1": 0, "P2": 0})
    for item in items:
        if item.get("status") != "passed":
            counts[str(item.get("severity") or "P2")] += 1
    return {key: int(counts[key]) for key in ("P0", "P1", "P2")}


def is_881_board(row: Mapping[str, Any]) -> bool:
    identity_key = str(row.get("identity_key") or "")
    code = str(row.get("code") or "")
    return identity_key.startswith("board:TDX:881") and re.fullmatch(r"881[0-9]{3}", code) is not None


def fallback_expected_scope_from_counts(expected_rows: Mapping[str, int]) -> dict[str, list[dict[str, Any]]]:
    scope: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    for asset in ASSET_KINDS:
        for index in range(int(expected_rows.get(asset, 0))):
            scope[asset].append({"identity_key": f"{asset}:UNKNOWN:{index:06d}", "exchange": None, "code": f"{index:06d}", "name": None})
    return scope


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(normalize_jsonable(item) for item in value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).isoformat()
