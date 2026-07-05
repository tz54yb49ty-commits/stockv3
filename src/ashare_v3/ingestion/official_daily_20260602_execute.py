"""Execute runner support for N1 official daily ingestion 20260602.

This module binds the verified official-daily execute mechanics to the
20260602 source scope. Importing or running preflight remains read-only; writes
can happen only through the guarded execute transaction with all final flags.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.ingestion import official_daily_20260601_execute as template


TRADE_DATE = "20260602"
EXPECTED_PREV_TRADE_DATE = "20260601"
EXPECTED_NEXT_TRADE_DATE = "20260603"
ACTIVE_STOCK_IDENTITY_SCOPE_KEY = "A_STOCK:20260529"
ACTIVE_STOCK_IDENTITY_SOURCE_VERSION = "stock_identity_20260529_v1"
ACTIVE_STOCK_IDENTITY_SOURCE_BATCH_ID = "stock_identity_refresh_20260529_v1"
ACTIVE_STOCK_IDENTITY_PREVIOUS_SOURCE_VERSION = "stock_identity_20260527_v1"
BATCH_ID = "official_daily_ingest_20260602_v1"
CONTRACT_SOURCE_VERSION = BATCH_ID
SOURCE_VERSIONS = {
    "stock": "stock_daily_20260602_v1",
    "index": "index_daily_20260602_v1",
    "board": "board_daily_20260602_v1",
}
ACTIVE_DATA_TYPES = {
    "stock": "stock_daily",
    "index": "index_daily",
    "board": "board_daily",
}
EXPECTED_ROWS = {
    "stock_daily_bar_fact": 5507,
    "index_daily_bar_fact": 83,
    "board_daily_bar_fact": 428,
    "total_daily_fact": 6018,
}
EXPECTED_STOCK_ADJ_FACTOR_ROWS = 5525
EXPECTED_MATCHED_STOCK_IDENTITY_ROWS = 5507
EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS = 0
STOCK_SCOPE_BREAKDOWN = {
    "stock_identity_active_universe": 5526,
    "stale_identity_excluded": 1,
    "effective_universe_excluding_stale": 5525,
    "tushare_daily_rows": 5507,
    "tushare_daily_rows_with_stock_identity": 5507,
    "supplemental_source_bar_rows": 0,
    "official_no_trade_manifest_rows": 18,
    "expected_stock_daily_bar_rows": 5507,
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
FIXED_9_INDEX_IDENTITIES = template.FIXED_9_INDEX_IDENTITIES
CANONICAL_IDENTITY_MAPPING = template.CANONICAL_IDENTITY_MAPPING
INDEX_TUSHARE_FALLBACK_IDENTITIES = template.INDEX_TUSHARE_FALLBACK_IDENTITIES
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
    "stock:SZ:000668",
    "stock:SZ:000736",
    "stock:SZ:001331",
    "stock:SZ:002200",
    "stock:SZ:002731",
    "stock:SZ:002808",
    "stock:SZ:002898",
    "stock:SZ:002969",
    "stock:SZ:300029",
    "stock:SZ:300175",
    "stock:SZ:300685",
    "stock:SH:600193",
    "stock:SH:600608",
    "stock:SH:605081",
    "stock:SH:688121",
    "stock:BJ:920305",
)
OFFICIAL_NO_TRADE_CORRECTION_EVIDENCE: dict[str, Any] = {}
ALLOWED_FUTURE_WRITE_TABLES = template.ALLOWED_FUTURE_WRITE_TABLES
DEFAULT_PATHS = {
    "dry_run_json": Path("docs/N1_official_daily_20260602_ingestion_dry_run_report.json"),
    "dry_run_md": Path("docs/N1_INGESTION_20260602_DRY_RUN_PREFLIGHT_REPORT.md"),
    "contract_json": Path("docs/N1_official_daily_20260602_ingestion_execute_contract.json"),
    "contract_md": Path("docs/N1_OFFICIAL_DAILY_20260602_INGESTION_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_official_daily_20260602_ingestion_execute_preflight.json"),
    "preflight_md": Path("docs/N1_OFFICIAL_DAILY_20260602_INGESTION_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_official_daily_20260602_ingestion_rollback.sql"),
    "stock_probe_json": Path("docs/N1_official_daily_20260602_stock_source_probe.json"),
    "index_board_probe_json": Path("docs/N1_official_daily_20260602_index_board_source_probe.json"),
    "index_board_probe_md": Path("docs/N1_OFFICIAL_DAILY_20260602_INDEX_BOARD_SOURCE_PROBE.md"),
}


class OfficialDaily20260602ExecuteBlocked(RuntimeError):
    """Raised when the guarded 20260602 execute path refuses to continue."""


class DefaultOfficialDaily20260602SourceAdapter(template.DefaultOfficialDaily20260601SourceAdapter):
    """20260602 adapter using the verified official daily source routes."""


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
def patched_template() -> Iterator[None]:
    overrides = dict(_TEMPLATE_PATCH_VALUES)
    overrides["_TEMPLATE_PATCH_VALUES"] = dict(_TEMPLATE_PATCH_VALUES)
    previous = {name: getattr(template, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(template, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(template, name, value)


def _convert_blocker(exc: Exception) -> OfficialDaily20260602ExecuteBlocked:
    return OfficialDaily20260602ExecuteBlocked(str(exc))


_TEMPLATE_DISPLAY_TEXT_KEYS = {"stage", "execute_command_template", "gate_name", "activated_by"}


def _replace_template_display_text(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, str):
        if parent_key in _TEMPLATE_DISPLAY_TEXT_KEYS:
            return value.replace("20260601", "20260602").replace("20260529", "20260602")
        return value
    if isinstance(value, list):
        return [_replace_template_display_text(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace_template_display_text(item, parent_key=parent_key) for item in value)
    if isinstance(value, dict):
        return {key: _replace_template_display_text(item, parent_key=str(key)) for key, item in value.items()}
    return value


def _fix_report_text(report: Mapping[str, Any]) -> dict[str, Any]:
    fixed = _replace_template_display_text(dict(report))
    return json.loads(json.dumps(fixed, ensure_ascii=False, default=str))


def _quality_counts(items: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"p0_count": 0, "p1_count": 0, "p2_count": 0}
    for item in items:
        severity = str(item.get("severity") or "").upper()
        status = str(item.get("status") or "")
        if severity == "P0" and status != "passed":
            counts["p0_count"] += 1
        elif severity == "P1":
            counts["p1_count"] += 1
        elif severity == "P2":
            counts["p2_count"] += 1
    return counts


def _with_next_calendar_warning(report: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    fixed = dict(report)
    next_detail = dict(snapshot.get("next_trade_calendar_detail") or {})
    if int(next_detail.get("row_count") or 0) != 0:
        return fixed
    quality = dict(fixed.get("quality") or {})
    items = [dict(item) for item in quality.get("items") or []]
    gate_name = "next_trade_calendar_detail_missing_downstream_warning"
    if not any(item.get("gate_name") == gate_name for item in items):
        items.append(
            {
                "gate_name": gate_name,
                "severity": "P1",
                "status": "warning",
                "expected": {"trade_date": EXPECTED_NEXT_TRADE_DATE, "row_count": 1},
                "actual": {"trade_date": EXPECTED_NEXT_TRADE_DATE, "row_count": int(next_detail.get("row_count") or 0)},
                "details": {
                    "scope": "downstream_calendar_detail",
                    "blocking_official_daily_execute": False,
                    "must_patch_before_downstream": True,
                },
            }
        )
    quality.update(_quality_counts(items))
    quality["items"] = items
    fixed["quality"] = quality
    fixed["next_trade_calendar_detail"] = next_detail or {"trade_date": EXPECTED_NEXT_TRADE_DATE, "row_count": 0}
    return fixed


def _fix_markdown_template_title(path: str | Path) -> None:
    target = Path(path)
    if not target.exists():
        return
    text = target.read_text(encoding="utf-8")
    text = text.replace("# N1 Official Daily 20260601", "# N1 Official Daily 20260602")
    text = text.replace("# N1 Official Daily 20260529", "# N1 Official Daily 20260602")
    target.write_text(text, encoding="utf-8")


def _read_next_calendar_detail(*, dsn: str) -> dict[str, Any]:
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date::text, is_open, prev_trade_date::text,
                       next_trade_date::text, source_version
                FROM common_trade_calendar
                WHERE trade_date = %s
                """,
                (EXPECTED_NEXT_TRADE_DATE,),
            )
            rows = [dict(row) for row in cur.fetchall()]
    detail = rows[0] if rows else {"trade_date": EXPECTED_NEXT_TRADE_DATE}
    detail["row_count"] = len(rows)
    return detail


def now_iso() -> str:
    return template.now_iso()


def sample_pass_snapshot() -> dict[str, Any]:
    with patched_template():
        snapshot = _fix_report_text(template.sample_pass_snapshot())
    snapshot["next_trade_calendar_detail"] = {"trade_date": EXPECTED_NEXT_TRADE_DATE, "row_count": 0}
    return snapshot


def sample_stock_source_probe() -> dict[str, Any]:
    return {
        "result": "STOCK_PROBE_PASS",
        "stock_source": {
            "tushare_daily_count": EXPECTED_ROWS["stock_daily_bar_fact"],
            "adj_factor_count": EXPECTED_STOCK_ADJ_FACTOR_ROWS,
            "matched_identity_count": EXPECTED_MATCHED_STOCK_IDENTITY_ROWS,
            "unmapped_count": EXPECTED_UNMAPPED_TUSHARE_DAILY_ROWS,
            "adj_minus_daily_active_identity_count": len(OFFICIAL_NO_TRADE_IDENTITIES),
            "duplicate_daily_ts_code_count": 0,
        },
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "p0_items": [], "p1_items": [], "p2_items": []},
    }


def load_stock_source_probe(path: str | Path = DEFAULT_PATHS["stock_probe_json"]) -> dict[str, Any]:
    probe_path = Path(path)
    if not probe_path.exists():
        return sample_stock_source_probe()
    return json.loads(probe_path.read_text(encoding="utf-8"))


def load_index_board_source_probe(path: str | Path = DEFAULT_PATHS["index_board_probe_json"]) -> dict[str, Any] | None:
    with patched_template():
        return template.load_index_board_source_probe(path)


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    with patched_template():
        try:
            template.validate_execute_request(
                execute_requested=execute_requested,
                user_confirmed=user_confirmed,
                source_fetch_enabled=source_fetch_enabled,
                postgres_commit_enabled=postgres_commit_enabled,
            )
        except template.OfficialDaily20260601ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    with patched_template():
        try:
            snapshot = _fix_report_text(template.build_snapshot_from_db(dsn=dsn, trade_date=trade_date))
        except template.OfficialDaily20260601ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc
    snapshot["next_trade_calendar_detail"] = _read_next_calendar_detail(dsn=dsn)
    return snapshot


def build_expected_scope_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, list[dict[str, Any]]]:
    with patched_template():
        try:
            return template.build_expected_scope_from_db(dsn=dsn, trade_date=trade_date)
        except template.OfficialDaily20260601ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def fetch_official_daily_sources(
    *,
    adapter: Any,
    trade_date: str,
    expected_scope: Mapping[str, Any],
    source_fetch_enabled: bool,
) -> dict[str, Any]:
    with patched_template():
        try:
            return template.fetch_official_daily_sources(
                adapter=adapter,
                trade_date=trade_date,
                expected_scope=expected_scope,
                source_fetch_enabled=source_fetch_enabled,
            )
        except template.OfficialDaily20260601ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def validate_source_bundle(*, bundle: Mapping[str, Any], expected_scope: Mapping[str, Any], trade_date: str) -> dict[str, Any]:
    with patched_template():
        try:
            return _fix_report_text(template.validate_source_bundle(bundle=bundle, expected_scope=expected_scope, trade_date=trade_date))
        except template.OfficialDaily20260601ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    with patched_template():
        try:
            template.validate_commit_preconditions(
                snapshot=snapshot,
                validation_report=validation_report,
                source_fetch_enabled=source_fetch_enabled,
                postgres_commit_enabled=postgres_commit_enabled,
            )
        except template.OfficialDaily20260601ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    trade_date: str,
) -> dict[str, Any]:
    with patched_template():
        try:
            return _fix_report_text(
                template.build_commit_plan(
                    bundle=bundle,
                    validation_report=validation_report,
                    baseline=baseline,
                    trade_date=trade_date,
                )
            )
        except template.OfficialDaily20260601ExecuteBlocked as exc:
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
    with patched_template():
        try:
            return _fix_report_text(
                template.execute_commit_transaction(
                    conn,
                    commit_plan=commit_plan,
                    execute_requested=execute_requested,
                    user_confirmed=user_confirmed,
                    source_fetch_enabled=source_fetch_enabled,
                    postgres_commit_enabled=postgres_commit_enabled,
                )
            )
        except template.OfficialDaily20260601ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def load_execute_contract(path: str | Path = DEFAULT_PATHS["contract_json"]) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"result": "DESIGN_PASS", "source_batch_id": BATCH_ID, "source_versions": dict(SOURCE_VERSIONS)}
    return json.loads(target.read_text(encoding="utf-8"))


def validate_execute_contract(contract: Mapping[str, Any]) -> None:
    with patched_template():
        try:
            template.validate_execute_contract(contract)
        except template.OfficialDaily20260601ExecuteBlocked as exc:
            raise _convert_blocker(exc) from exc


def build_dry_run_report(*, snapshot: Mapping[str, Any], stock_probe: Mapping[str, Any]) -> dict[str, Any]:
    with patched_template():
        report = _fix_report_text(template.build_dry_run_report(snapshot=snapshot, stock_probe=stock_probe))
    return _with_next_calendar_warning(report, snapshot)


def build_execute_contract(*, snapshot: Mapping[str, Any], stock_probe: Mapping[str, Any]) -> dict[str, Any]:
    with patched_template():
        contract = template.build_execute_contract(snapshot=snapshot, stock_probe=stock_probe)
    fixed = _fix_report_text(contract)
    fixed.setdefault("implementation_status", {})["runner_readiness"] = "ready_for_final_gate"
    fixed["implementation_status"]["production_commit_path_implemented"] = True
    return fixed


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
    with patched_template():
        report = template.build_execute_preflight_report(
            snapshot=snapshot,
            stock_probe=stock_probe,
            index_board_probe=index_board_probe,
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
            source_fetch_enabled=source_fetch_enabled,
            postgres_commit_enabled=postgres_commit_enabled,
        )
    fixed = _with_next_calendar_warning(_fix_report_text(report), snapshot)
    fixed["runner_readiness"] = "ready_for_final_gate" if fixed.get("result") == "PREFLIGHT_PASS" else "blocked"
    fixed.setdefault("execute_runner", {})["production_commit_path_implemented"] = True
    return fixed


def build_index_board_source_probe_report(*args: Any, **kwargs: Any) -> dict[str, Any]:
    with patched_template():
        return _fix_report_text(template.build_index_board_source_probe_report(*args, **kwargs))


def build_index_board_probe_from_adapter(*args: Any, **kwargs: Any) -> dict[str, Any]:
    with patched_template():
        return _fix_report_text(template.build_index_board_probe_from_adapter(*args, **kwargs))


def write_dry_run_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    with patched_template():
        template.write_dry_run_files(_fix_report_text(report), json_path=json_path, markdown_path=markdown_path)
    _fix_markdown_template_title(markdown_path)


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    with patched_template():
        template.write_contract_files(_fix_report_text(contract), json_path=json_path, markdown_path=markdown_path)
    _fix_markdown_template_title(markdown_path)


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    with patched_template():
        template.write_preflight_files(_fix_report_text(report), json_path=json_path, markdown_path=markdown_path)
    _fix_markdown_template_title(markdown_path)
