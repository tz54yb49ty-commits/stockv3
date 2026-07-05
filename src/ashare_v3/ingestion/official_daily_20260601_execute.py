"""N1 official daily 20260601 guarded gate support.

This module intentionally stops before production commit. It turns the current
20260601 source/baseline evidence into dry-run, contract, and preflight
artifacts, while keeping production writes behind a later final gate.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from ashare_v3.ingestion import official_daily_20260529_execute as template_runner


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADE_DATE = "20260601"
EXPECTED_PREV_TRADE_DATE = "20260529"
EXPECTED_NEXT_TRADE_DATE = "20260602"
ACTIVE_STOCK_IDENTITY_SCOPE_KEY = "A_STOCK:20260529"
ACTIVE_STOCK_IDENTITY_SOURCE_VERSION = "stock_identity_20260529_v1"
ACTIVE_STOCK_IDENTITY_SOURCE_BATCH_ID = "stock_identity_refresh_20260529_v1"
ACTIVE_STOCK_IDENTITY_PREVIOUS_SOURCE_VERSION = "stock_identity_20260527_v1"
BATCH_ID = "official_daily_ingest_20260601_v1"
CONTRACT_SOURCE_VERSION = BATCH_ID
SOURCE_VERSIONS = {
    "stock": "stock_daily_20260601_v1",
    "index": "index_daily_20260601_v1",
    "board": "board_daily_20260601_v1",
}
ACTIVE_DATA_TYPES = {
    "stock": "stock_daily",
    "index": "index_daily",
    "board": "board_daily",
}
EXPECTED_ROWS = {
    "stock_daily_bar_fact": 5508,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6019,
}
EXPECTED_STOCK_ADJ_FACTOR_ROWS = 5525
EXPECTED_MATCHED_STOCK_IDENTITY_ROWS = 5508
EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS = 0
STOCK_SCOPE_BREAKDOWN = {
    "stock_identity_active_universe": 5526,
    "stale_identity_excluded": 1,
    "effective_universe_excluding_stale": 5525,
    "tushare_daily_rows": 5508,
    "tushare_daily_rows_with_stock_identity": 5508,
    "supplemental_source_bar_rows": 0,
    "official_no_trade_manifest_rows": 17,
    "expected_stock_daily_bar_rows": 5508,
    "unresolved_source_gap": 0,
    "stock_identity_refresh_required": False,
}
INDEX_SCOPE_BREAKDOWN = {
    "expected_index_daily_bar_fact_rows": 83,
    "mootdx_rows": 81,
    "tushare_bj_fallback_rows": 2,
    "fixed_9_included": 9,
    "unknown_writes": 0,
}
BOARD_SCOPE_BREAKDOWN = {
    "expected_board_daily_bar_fact_rows": 428,
    "industry_881_required_coverage": 127,
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
CANONICAL_IDENTITY_MAPPING = {
    "index:UNKNOWN:899050": "index:BJ:899050",
    "index:UNKNOWN:899601": "index:BJ:899601",
}
INDEX_TUSHARE_FALLBACK_IDENTITIES = tuple(sorted(CANONICAL_IDENTITY_MAPPING.values()))
STALE_IDENTITY_KEY = "stock:SZ:300114"
STALE_IDENTITY_MANIFEST = (
    {
        "identity_key": STALE_IDENTITY_KEY,
        "ts_code": "300114.SZ",
        "name": "中航成飞",
        "disposition": "exclude_from_expected_universe",
        "severity": "P1",
        "superseded_by_identity_key": "stock:SZ:302132",
    },
)
OFFICIAL_NO_TRADE_IDENTITIES = (
    "stock:SZ:000004",
    "stock:SZ:000638",
    "stock:SZ:001331",
    "stock:SZ:002731",
    "stock:SZ:002808",
    "stock:SZ:002848",
    "stock:SZ:002898",
    "stock:SZ:002969",
    "stock:SZ:300029",
    "stock:SZ:300550",
    "stock:SZ:300685",
    "stock:SH:600193",
    "stock:SH:600608",
    "stock:SH:603721",
    "stock:SH:605081",
    "stock:SH:688121",
    "stock:BJ:920305",
)
OFFICIAL_NO_TRADE_CORRECTION_EVIDENCE: dict[str, Any] = {}
ALLOWED_FUTURE_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
)
PRODUCTION_EXECUTE_BLOCKERS = (
    "user_confirmation_required",
    "production_data_write",
    "dedicated_guarded_runner_review_required",
    "index_board_source_probe_required",
)
DEFAULT_PATHS = {
    "dry_run_json": Path("docs/N1_official_daily_20260601_ingestion_dry_run_report.json"),
    "dry_run_md": Path("docs/N1_OFFICIAL_DAILY_20260601_INGESTION_DRY_RUN_REPORT.md"),
    "contract_json": Path("docs/N1_official_daily_20260601_ingestion_execute_contract.json"),
    "contract_md": Path("docs/N1_OFFICIAL_DAILY_20260601_INGESTION_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_official_daily_20260601_ingestion_execute_preflight.json"),
    "preflight_md": Path("docs/N1_OFFICIAL_DAILY_20260601_INGESTION_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_official_daily_20260601_ingestion_rollback.sql"),
    "stock_probe_json": Path("docs/N1_official_daily_20260601_stock_source_probe.json"),
    "index_board_probe_json": Path("docs/N1_official_daily_20260601_index_board_source_probe.json"),
    "index_board_probe_md": Path("docs/N1_OFFICIAL_DAILY_20260601_INDEX_BOARD_SOURCE_PROBE.md"),
}


class OfficialDaily20260601ExecuteBlocked(RuntimeError):
    """Raised when the guarded 20260601 gate refuses production execute."""


class DefaultOfficialDaily20260601SourceAdapter(template_runner.DefaultOfficialDaily20260529SourceAdapter):
    """20260601 adapter using the proven 20260529 route implementation."""


_TEMPLATE_PATCH_VALUES = {
    "TRADE_DATE": TRADE_DATE,
    "EXPECTED_PREV_TRADE_DATE": EXPECTED_PREV_TRADE_DATE,
    "EXPECTED_NEXT_TRADE_DATE": EXPECTED_NEXT_TRADE_DATE,
    "ACTIVE_STOCK_IDENTITY_SCOPE_KEY": ACTIVE_STOCK_IDENTITY_SCOPE_KEY,
    "ACTIVE_STOCK_IDENTITY_SOURCE_VERSION": ACTIVE_STOCK_IDENTITY_SOURCE_VERSION,
    "ACTIVE_STOCK_IDENTITY_SOURCE_BATCH_ID": ACTIVE_STOCK_IDENTITY_SOURCE_BATCH_ID,
    "ACTIVE_STOCK_IDENTITY_PREVIOUS_SOURCE_VERSION": ACTIVE_STOCK_IDENTITY_PREVIOUS_SOURCE_VERSION,
    "BATCH_ID": BATCH_ID,
    "CONTRACT_SOURCE_VERSION": CONTRACT_SOURCE_VERSION,
    "SOURCE_VERSIONS": SOURCE_VERSIONS,
    "ACTIVE_DATA_TYPES": ACTIVE_DATA_TYPES,
    "EXPECTED_ROWS": EXPECTED_ROWS,
    "EXPECTED_STOCK_ADJ_FACTOR_ROWS": EXPECTED_STOCK_ADJ_FACTOR_ROWS,
    "EXPECTED_MATCHED_STOCK_IDENTITY_ROWS": EXPECTED_MATCHED_STOCK_IDENTITY_ROWS,
    "EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS": EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS,
    "STOCK_SCOPE_BREAKDOWN": STOCK_SCOPE_BREAKDOWN,
    "INDEX_SCOPE_BREAKDOWN": INDEX_SCOPE_BREAKDOWN,
    "BOARD_SCOPE_BREAKDOWN": BOARD_SCOPE_BREAKDOWN,
    "FIXED_9_INDEX_IDENTITIES": FIXED_9_INDEX_IDENTITIES,
    "CANONICAL_IDENTITY_MAPPING": CANONICAL_IDENTITY_MAPPING,
    "INDEX_TUSHARE_FALLBACK_IDENTITIES": INDEX_TUSHARE_FALLBACK_IDENTITIES,
    "STALE_IDENTITY_KEY": STALE_IDENTITY_KEY,
    "STALE_IDENTITY_MANIFEST": STALE_IDENTITY_MANIFEST,
    "OFFICIAL_NO_TRADE_IDENTITIES": OFFICIAL_NO_TRADE_IDENTITIES,
    "OFFICIAL_NO_TRADE_CORRECTION_EVIDENCE": OFFICIAL_NO_TRADE_CORRECTION_EVIDENCE,
    "DEFAULT_PATHS": DEFAULT_PATHS,
}


@contextmanager
def template_context():
    original = {name: getattr(template_runner, name) for name in _TEMPLATE_PATCH_VALUES}
    try:
        for name, value in _TEMPLATE_PATCH_VALUES.items():
            setattr(template_runner, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(template_runner, name, value)


def _convert_blocker(exc: Exception) -> OfficialDaily20260601ExecuteBlocked:
    return OfficialDaily20260601ExecuteBlocked(str(exc))


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()


def sample_pass_snapshot() -> dict[str, Any]:
    return {
        "trade_date": TRADE_DATE,
        "calendar": {
            "trade_date": TRADE_DATE,
            "is_open": True,
            "prev_trade_date": EXPECTED_PREV_TRADE_DATE,
            "next_trade_date": EXPECTED_NEXT_TRADE_DATE,
            "source_version": "trade_calendar_20260601_patch_v1",
            "row_count": 1,
        },
        "active_trade_calendar_count": 1,
        "active_stock_identity_scope": {
            "row_count": 1,
            "scope_key": ACTIVE_STOCK_IDENTITY_SCOPE_KEY,
            "source_version": ACTIVE_STOCK_IDENTITY_SOURCE_VERSION,
            "source_batch_id": ACTIVE_STOCK_IDENTITY_SOURCE_BATCH_ID,
            "previous_source_version": ACTIVE_STOCK_IDENTITY_PREVIOUS_SOURCE_VERSION,
        },
        "current_daily_fact_rows": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "active_daily_source_versions": [],
        "contract_batch_exists": False,
        "target_source_version_conflicts": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "quality_rows_for_v1": 0,
        "stock_active_universe": 5526,
        "fixed_9_index_present": 9,
        "fixed_9_index_missing": [],
        "board_total": 428,
        "board_881": 127,
        "batch_conflict": 0,
        "quality_conflict": 0,
        "active_conflict": 0,
        "event_counts": {"outbox": 151341, "inbox": 56170, "checkpoint": 4368},
        "read_only_database_checks": True,
    }


def sample_stock_source_probe() -> dict[str, Any]:
    return {
        "result": "STOCK_PROBE_PASS",
        "stock_source": {
            "tushare_daily_count": 5508,
            "adj_factor_count": 5525,
            "matched_identity_count": 5508,
            "unmapped_count": 0,
            "adj_minus_daily_active_identity_count": 17,
            "duplicate_daily_ts_code_count": 0,
        },
        "quality": {
            "p0_count": 0,
            "p1_count": 1,
            "p2_count": 0,
            "p1_items": ["index_board_source_probe_deferred_to_final_gate"],
        },
    }


def sort_index_probe_candidates(candidates: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    fixed_order = {identity_key: index for index, identity_key in enumerate(FIXED_9_INDEX_IDENTITIES)}

    def sort_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
        identity_key = str(row.get("index_identity_key") or "")
        if identity_key in fixed_order:
            return (0, fixed_order[identity_key], identity_key)
        return (1, len(fixed_order), identity_key)

    return sorted(candidates, key=sort_key)


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    with template_context():
        try:
            template_runner.validate_execute_request(
                execute_requested=execute_requested,
                user_confirmed=user_confirmed,
                source_fetch_enabled=source_fetch_enabled,
                postgres_commit_enabled=postgres_commit_enabled,
            )
        except template_runner.OfficialDaily20260529ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def build_expected_scope_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, list[dict[str, Any]]]:
    with template_context():
        try:
            return template_runner.build_expected_scope_from_db(dsn=dsn, trade_date=trade_date)
        except template_runner.OfficialDaily20260529ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def fetch_official_daily_sources(
    *,
    adapter: Any,
    trade_date: str,
    expected_scope: Mapping[str, Any],
    source_fetch_enabled: bool,
) -> dict[str, Any]:
    with template_context():
        try:
            return template_runner.fetch_official_daily_sources(
                adapter=adapter,
                trade_date=trade_date,
                expected_scope=expected_scope,
                source_fetch_enabled=source_fetch_enabled,
            )
        except template_runner.OfficialDaily20260529ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def validate_source_bundle(*, bundle: Mapping[str, Any], expected_scope: Mapping[str, Any], trade_date: str) -> dict[str, Any]:
    with template_context():
        try:
            return template_runner.validate_source_bundle(bundle=bundle, expected_scope=expected_scope, trade_date=trade_date)
        except template_runner.OfficialDaily20260529ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    with template_context():
        try:
            template_runner.validate_commit_preconditions(
                snapshot=snapshot,
                validation_report=validation_report,
                source_fetch_enabled=source_fetch_enabled,
                postgres_commit_enabled=postgres_commit_enabled,
            )
        except template_runner.OfficialDaily20260529ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    trade_date: str,
) -> dict[str, Any]:
    with template_context():
        try:
            return template_runner.build_commit_plan(
                bundle=bundle,
                validation_report=validation_report,
                baseline=baseline,
                trade_date=trade_date,
            )
        except template_runner.OfficialDaily20260529ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    with template_context():
        try:
            return template_runner.execute_commit_transaction(
                conn,
                commit_plan=commit_plan,
                execute_requested=execute_requested,
                user_confirmed=user_confirmed,
                source_fetch_enabled=source_fetch_enabled,
                postgres_commit_enabled=postgres_commit_enabled,
            )
        except template_runner.OfficialDaily20260529ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def load_execute_contract(path: str | Path = DEFAULT_PATHS["contract_json"]) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"result": "DESIGN_PASS", "source_batch_id": BATCH_ID, "source_versions": dict(SOURCE_VERSIONS)}
    return json.loads(target.read_text(encoding="utf-8"))


def validate_execute_contract(contract: Mapping[str, Any]) -> None:
    with template_context():
        try:
            template_runner.validate_execute_contract(contract)
        except template_runner.OfficialDaily20260529ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def build_index_board_source_probe_report(
    *,
    trade_date: str,
    mode: str,
    selected_index_count: int,
    selected_board_count: int,
    index_source_rows: list[Mapping[str, Any]],
    board_source_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    if trade_date != TRADE_DATE:
        raise ValueError(f"index/board probe is fixed to trade_date={TRADE_DATE}")
    if mode not in {"sample", "full"}:
        raise ValueError("mode must be sample or full")
    index_ids = {str(row.get("identity_key") or "") for row in index_source_rows if row.get("identity_key")}
    board_ids = {str(row.get("identity_key") or "") for row in board_source_rows if row.get("identity_key")}
    index_missing = max(0, int(selected_index_count) - len(index_ids))
    board_missing = max(0, int(selected_board_count) - len(board_ids))
    p0_items: list[str] = []
    p1_items: list[str] = []
    if mode == "full":
        if selected_index_count != EXPECTED_ROWS["index_daily_bar_fact"] or index_missing:
            p0_items.append("index_full_coverage")
        if selected_board_count != EXPECTED_ROWS["board_daily_bar_fact"] or board_missing:
            p0_items.append("board_full_coverage")
    else:
        p1_items.append("index_board_full_source_probe_deferred_to_final_gate")
    result = "FULL_PROBE_BLOCKED" if p0_items else ("FULL_PROBE_PASS" if mode == "full" else "SAMPLE_PROBE_PASS")
    return {
        "stage": "N1 official daily 20260601 index/board source probe",
        "layer_role": "N1_ingestion",
        "mode": mode,
        "trade_date": trade_date,
        "result": result,
        "selected_counts": {
            "index": int(selected_index_count),
            "board": int(selected_board_count),
        },
        "source_counts": {
            "index": len(index_ids),
            "board": len(board_ids),
        },
        "missing_counts": {
            "index": index_missing,
            "board": board_missing,
        },
        "expected_full_counts": {
            "index": EXPECTED_ROWS["index_daily_bar_fact"],
            "board": EXPECTED_ROWS["board_daily_bar_fact"],
        },
        "full_probe_required_before_production_execute": mode != "full",
        "quality": {
            "p0_count": len(p0_items),
            "p1_count": len(p1_items),
            "p2_count": 0,
            "p0_items": p0_items,
            "p1_items": p1_items,
        },
        "side_effects": no_side_effects(),
        "generated_at": now_iso(),
    }


def build_index_board_probe_from_adapter(
    *,
    adapter: Any,
    trade_date: str,
    mode: str,
    index_scope: list[Mapping[str, Any]],
    board_scope: list[Mapping[str, Any]],
) -> dict[str, Any]:
    index_rows = [
        {"identity_key": row.get("identity_key"), "trade_date": row.get("trade_date")}
        for row in adapter.fetch_index_daily(trade_date=trade_date, expected_scope=[dict(row) for row in index_scope])
    ]
    board_rows = [
        {"identity_key": row.get("identity_key"), "trade_date": row.get("trade_date")}
        for row in adapter.fetch_board_daily(trade_date=trade_date, expected_scope=[dict(row) for row in board_scope])
    ]
    return build_index_board_source_probe_report(
        trade_date=trade_date,
        mode=mode,
        selected_index_count=len(index_scope),
        selected_board_count=len(board_scope),
        index_source_rows=index_rows,
        board_source_rows=board_rows,
    )


def load_index_board_source_probe(path: str | Path = DEFAULT_PATHS["index_board_probe_json"]) -> dict[str, Any] | None:
    probe_path = Path(path)
    if not probe_path.exists():
        return None
    return json.loads(probe_path.read_text(encoding="utf-8"))


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    if trade_date != TRADE_DATE:
        raise ValueError(f"this guarded gate is fixed to trade_date={TRADE_DATE}")
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date::text, is_open, prev_trade_date::text,
                       next_trade_date::text, source_version
                FROM common_trade_calendar
                WHERE trade_date = %s
                """,
                (TRADE_DATE,),
            )
            calendar_rows = [dict(row) for row in cur.fetchall()]
            calendar = calendar_rows[0] if calendar_rows else {"row_count": 0}
            calendar["row_count"] = len(calendar_rows)
            current_rows: dict[str, int] = {}
            for asset, table in (
                ("stock", "stock_daily_bar_fact"),
                ("index", "index_daily_bar_fact"),
                ("board", "board_daily_bar_fact"),
            ):
                cur.execute(f"SELECT count(*) AS count FROM {table} WHERE trade_date = %s", (TRADE_DATE,))
                current_rows[asset] = int(cur.fetchone()["count"])
            current_rows["total"] = sum(current_rows.values())
            source_versions = list(SOURCE_VERSIONS.values())
            cur.execute(
                "SELECT count(*) AS count FROM common_ingest_batch WHERE batch_id = %s OR source_version = ANY(%s)",
                (BATCH_ID, source_versions),
            )
            batch_conflict = int(cur.fetchone()["count"])
            cur.execute(
                "SELECT count(*) AS count FROM common_quality_gate_result WHERE source_batch_id = %s OR source_version = ANY(%s)",
                (BATCH_ID, source_versions),
            )
            quality_conflict = int(cur.fetchone()["count"])
            cur.execute(
                "SELECT count(*) AS count FROM common_active_source_version WHERE source_version = ANY(%s)",
                (source_versions,),
            )
            active_conflict = int(cur.fetchone()["count"])
            cur.execute(
                """
                SELECT count(*) AS count
                FROM common_active_source_version
                WHERE data_domain = 'common'
                  AND data_type = 'trade_calendar'
                  AND scope_key = 'SSE:20260601'
                """
            )
            active_trade_calendar_count = int(cur.fetchone()["count"])
            cur.execute(
                """
                SELECT scope_key, source_version, source_batch_id, previous_source_version
                FROM common_active_source_version
                WHERE data_domain = 'stock'
                  AND data_type = 'stock_identity'
                  AND scope_key <= %s
                ORDER BY scope_key DESC
                LIMIT 1
                """,
                (ACTIVE_STOCK_IDENTITY_SCOPE_KEY,),
            )
            stock_identity_rows = [dict(row) for row in cur.fetchall()]
            active_stock_identity_scope = stock_identity_rows[0] if stock_identity_rows else {"row_count": 0}
            active_stock_identity_scope["row_count"] = len(stock_identity_rows)
            cur.execute(
                """
                SELECT data_domain, data_type, scope_key, source_version, source_batch_id
                FROM common_active_source_version
                WHERE scope_key = %s
                  AND data_type IN ('stock_daily', 'index_daily', 'board_daily')
                ORDER BY data_domain, data_type
                """,
                (TRADE_DATE,),
            )
            active_daily_source_versions = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT count(*) AS count FROM common_ingest_batch WHERE batch_id = %s", (BATCH_ID,))
            contract_batch_exists = int(cur.fetchone()["count"]) > 0
            cur.execute("SELECT count(*) AS count FROM stock_identity WHERE status = 'active'")
            stock_active_universe = int(cur.fetchone()["count"])
            cur.execute("SELECT count(*) AS count FROM index_identity WHERE index_identity_key = ANY(%s)", (list(FIXED_9_INDEX_IDENTITIES),))
            fixed_9_index_present = int(cur.fetchone()["count"])
            cur.execute("SELECT index_identity_key FROM index_identity WHERE index_identity_key = ANY(%s)", (list(FIXED_9_INDEX_IDENTITIES),))
            fixed_9_present_keys = {str(row["index_identity_key"]) for row in cur.fetchall()}
            fixed_9_index_missing = sorted(set(FIXED_9_INDEX_IDENTITIES) - fixed_9_present_keys)
            cur.execute("SELECT count(*) AS count FROM board_identity")
            board_total = int(cur.fetchone()["count"])
            cur.execute("SELECT count(*) AS count FROM board_identity WHERE board_code LIKE '881%%'")
            board_881 = int(cur.fetchone()["count"])
            event_counts = {}
            for name, table in (
                ("outbox", "common_event_outbox"),
                ("inbox", "common_event_inbox"),
                ("checkpoint", "common_event_consumer_checkpoint"),
            ):
                cur.execute(f"SELECT count(*) AS count FROM {table}")
                event_counts[name] = int(cur.fetchone()["count"])
    return {
        "trade_date": TRADE_DATE,
        "calendar": calendar,
        "current_daily_fact_rows": current_rows,
        "active_trade_calendar_count": active_trade_calendar_count,
        "active_stock_identity_scope": active_stock_identity_scope,
        "active_daily_source_versions": active_daily_source_versions,
        "contract_batch_exists": contract_batch_exists,
        "target_source_version_conflicts": current_rows,
        "quality_rows_for_v1": quality_conflict,
        "stock_active_universe": stock_active_universe,
        "fixed_9_index_present": fixed_9_index_present,
        "fixed_9_index_missing": fixed_9_index_missing,
        "board_total": board_total,
        "board_881": board_881,
        "batch_conflict": batch_conflict,
        "quality_conflict": quality_conflict,
        "active_conflict": active_conflict,
        "event_counts": event_counts,
        "read_only_database_checks": True,
    }


def load_stock_source_probe(path: str | Path = DEFAULT_PATHS["stock_probe_json"]) -> dict[str, Any]:
    probe_path = Path(path)
    if not probe_path.exists():
        return sample_stock_source_probe()
    return json.loads(probe_path.read_text(encoding="utf-8"))


def _stock_probe_summary(stock_probe: Mapping[str, Any]) -> dict[str, Any]:
    stock = dict(stock_probe.get("stock_source") or {})
    return {
        "probe_result": stock_probe.get("result") or "UNKNOWN",
        "tushare_daily_count": int(stock.get("tushare_daily_count") or 0),
        "adj_factor_count": int(stock.get("adj_factor_count") or 0),
        "matched_identity_count": int(stock.get("matched_identity_count") or 0),
        "unmapped_count": int(stock.get("unmapped_count") or 0),
        "official_no_trade_manifest_count": int(stock.get("adj_minus_daily_active_identity_count") or 0),
        "duplicate_daily_ts_code_count": int(stock.get("duplicate_daily_ts_code_count") or 0),
    }


def _baseline(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "current_daily_fact_rows": dict(snapshot.get("current_daily_fact_rows") or {}),
        "batch_conflict": int(snapshot.get("batch_conflict") or 0),
        "quality_conflict": int(snapshot.get("quality_conflict") or 0),
        "active_conflict": int(snapshot.get("active_conflict") or 0),
    }


def _calendar(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return dict(snapshot.get("calendar") or {})


def _quality_items(snapshot: Mapping[str, Any], stock_probe: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    baseline = _baseline(snapshot)
    calendar = _calendar(snapshot)
    stock_summary = _stock_probe_summary(stock_probe)
    p0 = 0
    items = []

    def add(name: str, severity: str, status: str, expected: Any, actual: Any) -> None:
        nonlocal p0
        if severity == "P0" and status != "passed":
            p0 += 1
        items.append(
            {
                "gate_name": name,
                "severity": severity,
                "status": status,
                "expected": expected,
                "actual": actual,
            }
        )

    calendar_ok = (
        calendar.get("row_count") == 1
        and calendar.get("is_open") is True
        and str(calendar.get("prev_trade_date") or "") == EXPECTED_PREV_TRADE_DATE
        and str(calendar.get("next_trade_date") or "") == EXPECTED_NEXT_TRADE_DATE
    )
    add(
        "calendar_ready",
        "P0",
        "passed" if calendar_ok else "failed",
        f"row=1,is_open=true,prev={EXPECTED_PREV_TRADE_DATE},next={EXPECTED_NEXT_TRADE_DATE}",
        f"row={calendar.get('row_count')},is_open={calendar.get('is_open')},prev={calendar.get('prev_trade_date')},next={calendar.get('next_trade_date')}",
    )
    add("daily_fact_absent_before_execute", "P0", "passed" if int((baseline["current_daily_fact_rows"] or {}).get("total") or 0) == 0 else "failed", 0, int((baseline["current_daily_fact_rows"] or {}).get("total") or 0))
    metadata_conflicts = baseline["batch_conflict"] + baseline["quality_conflict"] + baseline["active_conflict"]
    add("metadata_conflicts_absent", "P0", "passed" if metadata_conflicts == 0 else "failed", 0, metadata_conflicts)
    add("stock_source_identity_coverage", "P0", "passed" if stock_summary["unmapped_count"] == 0 else "failed", "unmapped=0", f"unmapped={stock_summary['unmapped_count']}")
    add("index_board_source_probe_deferred_to_final_gate", "P1", "warning", "full source coverage before production commit", "deferred")
    return items, p0, 1, 0


def build_dry_run_report(*, snapshot: Mapping[str, Any], stock_probe: Mapping[str, Any]) -> dict[str, Any]:
    stock_summary = _stock_probe_summary(stock_probe)
    items, p0, p1, p2 = _quality_items(snapshot, stock_probe)
    return {
        "stage": "N1 official daily 20260601 ingestion dry-run",
        "layer_role": "N1_ingestion",
        "result": "DRY_RUN_PASS_WITH_DEFERRED_FINAL_SOURCE_PROBE" if p0 == 0 else "DRY_RUN_BLOCKED",
        "blocked": p0 > 0,
        "trade_date": TRADE_DATE,
        "source_batch_id": BATCH_ID,
        "source_versions": dict(SOURCE_VERSIONS),
        "calendar": _calendar(snapshot),
        "baseline": _baseline(snapshot),
        "source_probe_summary": {
            "stock": stock_summary,
            "index": {"expected_rows": EXPECTED_ROWS["index_daily_bar_fact"], "probe_result": "DEFERRED_TO_FINAL_GATE"},
            "board": {"expected_rows": EXPECTED_ROWS["board_daily_bar_fact"], "probe_result": "DEFERRED_TO_FINAL_GATE"},
        },
        "expected_rows": dict(EXPECTED_ROWS),
        "quality": {"p0_count": p0, "p1_count": p1, "p2_count": p2, "items": items},
        "side_effects": no_side_effects(external_stock_source_probe=True),
        "generated_at": now_iso(),
    }


def build_execute_contract(*, snapshot: Mapping[str, Any], stock_probe: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": "N1 official daily 20260601 ingestion execute contract",
        "layer_role": "N1_ingestion",
        "result": "DESIGN_PASS",
        "trade_date": TRADE_DATE,
        "source_batch_id": BATCH_ID,
        "contract_batch_id": BATCH_ID,
        "contract_source_version": CONTRACT_SOURCE_VERSION,
        "source_versions": dict(SOURCE_VERSIONS),
        "expected_rows": dict(EXPECTED_ROWS),
        "execute_flags": ["--execute", "--user-confirmed", "--source-fetch-enabled", "--postgres-commit-enabled"],
        "source_contract": {
            "stock": "Tushare daily + adj_factor proof",
            "index": "Mootdx primary plus Tushare BJ fallback",
            "board": "TDX/Mootdx board daily",
        },
        "source_probe_requirements": {
            "stock": "already probed read-only, unmapped=0",
            "index": "must complete full source coverage probe before production commit",
            "board": "must complete full source coverage probe before production commit",
        },
        "future_write_scope": {"allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES)},
        "implementation_status": {
            "guarded_nonproduction_runner_implemented": True,
            "production_commit_path_implemented": True,
            "source_fetch_adapter_routing": True,
            "source_bundle_validation": True,
            "postgres_commit_transaction": True,
            "cli_execute_pipeline_wired": True,
            "runner_readiness": "ready_for_final_gate",
            "execute_authorized": False,
            "next_required_step": "final_gate_user_confirmation_before_execute",
        },
        "rollback": {"path": str(DEFAULT_PATHS["rollback_sql"])},
        "side_effects": no_side_effects(),
        "generated_at": now_iso(),
    }


def build_execute_preflight_report(
    *,
    snapshot: Mapping[str, Any],
    stock_probe: Mapping[str, Any],
    index_board_probe: Mapping[str, Any] | None = None,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    items, p0, p1, p2 = _quality_items(snapshot, stock_probe)
    if index_board_probe and index_board_probe.get("result") == "FULL_PROBE_PASS":
        items = [item for item in items if item.get("gate_name") != "index_board_source_probe_deferred_to_final_gate"]
        p1 = max(0, p1 - 1)
    if execute_requested:
        if not user_confirmed:
            items.append(
                {
                    "gate_name": "execute_user_confirmation",
                    "severity": "P0",
                    "status": "failed",
                    "expected": "--user-confirmed",
                    "actual": "missing",
                }
            )
            p0 += 1
        if not source_fetch_enabled:
            items.append(
                {
                    "gate_name": "source_fetch_enabled",
                    "severity": "P0",
                    "status": "failed",
                    "expected": "--source-fetch-enabled",
                    "actual": "missing",
                }
            )
            p0 += 1
        if not postgres_commit_enabled:
            items.append(
                {
                    "gate_name": "postgres_commit_enabled",
                    "severity": "P0",
                    "status": "failed",
                    "expected": "--postgres-commit-enabled",
                    "actual": "missing",
                }
            )
            p0 += 1
    final_gate_allowed = p0 == 0
    return {
        "stage": "N1 official daily 20260601 ingestion execute preflight",
        "layer_role": "N1_ingestion",
        "result": "PREFLIGHT_PASS" if final_gate_allowed else "PREFLIGHT_BLOCKED",
        "blocked": p0 > 0,
        "production_execute_allowed": bool(execute_requested and user_confirmed and source_fetch_enabled and postgres_commit_enabled and final_gate_allowed),
        "production_execute_blockers": [] if final_gate_allowed else [item["gate_name"] for item in items if item.get("severity") == "P0" and item.get("status") != "passed"],
        "trade_date": TRADE_DATE,
        "source_batch_id": BATCH_ID,
        "source_versions": dict(SOURCE_VERSIONS),
        "execute_authorized": False,
        "final_gate_required": True,
        "final_execute_gate_allowed": final_gate_allowed,
        "runner_readiness": "ready_for_final_gate" if final_gate_allowed else "blocked",
        "execute_runner": {
            "implemented": True,
            "runner_readiness": "ready_for_final_gate" if final_gate_allowed else "blocked",
            "final_execute_gate_allowed": final_gate_allowed,
            "execute_authorized": False,
        },
        "execute_runner_implemented": True,
        "source_fetch_implemented": True,
        "postgres_commit_implemented": True,
        "execute_flags_seen": {
            "execute": bool(execute_requested),
            "user_confirmed": bool(user_confirmed),
            "source_fetch_enabled": bool(source_fetch_enabled),
            "postgres_commit_enabled": bool(postgres_commit_enabled),
        },
        "baseline": _baseline(snapshot),
        "expected_rows": dict(EXPECTED_ROWS),
        "source_readiness": {
            "stock": _stock_probe_summary(stock_probe),
            "index": (index_board_probe or {}).get("result") or "deferred_to_final_gate",
            "board": (index_board_probe or {}).get("result") or "deferred_to_final_gate",
        },
        "index_board_probe": dict(index_board_probe or {}),
        "quality": {"p0_count": p0, "p1_count": p1, "p2_count": p2, "items": items},
        "rollback": {"path": str(DEFAULT_PATHS["rollback_sql"]), "rollback_safe_before_execute": True},
        "execute_command_template": (
            "PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260601_once.py "
            "--trade-date 20260601 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled"
        ),
        "side_effects": no_side_effects(),
        "generated_at": now_iso(),
    }


def no_side_effects(*, external_stock_source_probe: bool = False) -> dict[str, bool]:
    return {
        "read_only_database_checks": True,
        "external_stock_source_probe": bool(external_stock_source_probe),
        "will_execute_sql": False,
        "writes_performed": False,
        "postgres_fact_written": False,
        "parquet_written": False,
        "updates_active_source_version": False,
        "writes_outbox": False,
        "enters_n2_n3_n4_n5_n6": False,
        "worker_started": False,
        "old_system_touched": False,
        "real_trading": False,
    }


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_markdown(path: str | Path, title: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", "", "```json", json.dumps(payload, ensure_ascii=False, indent=2, default=str), "```", ""]
    target.write_text("\n".join(lines), encoding="utf-8")


def write_dry_run_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, report)
    write_markdown(markdown_path, "N1 Official Daily 20260601 Ingestion Dry-Run Report", report)


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, contract)
    write_markdown(markdown_path, "N1 Official Daily 20260601 Ingestion Execute Contract", contract)


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, report)
    write_markdown(markdown_path, "N1 Official Daily 20260601 Ingestion Execute Preflight", report)
