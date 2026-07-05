"""Execute runner support for N1 condition source activation 20260602.

The implementation reuses the verified 20260529 activation mechanics while
binding every contract, manifest, source version, and commit marker to the
20260602 condition-source activation scope.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from ashare_v3.ingestion import condition_source_activation_20260529_execute as template

_base = template.template.base


TRADE_DATE = "20260602"
BATCH_ID = "condition_source_activation_20260602_v1"
TDX_ROOT = Path("/Volumes/MacRaid/tdxdata/tdx")
SOURCE_VERSIONS = {
    "stock_daily_basic": "stock_daily_basic_20260602_v1",
    "stock_financial": "stock_financial_20260602_v1",
    "index_membership": "index_membership_20260602_v1",
    "board_membership": "board_membership_20260602_v1",
}
ACTIVE_SCOPES = {
    "stock_daily_basic": "20260602",
    "stock_financial": "20260602",
    "index_membership": "TDX:20260602",
    "board_membership": "TDX:20260602",
}
DATA_DOMAINS = {
    "stock_daily_basic": "stock",
    "stock_financial": "stock",
    "index_membership": "index",
    "board_membership": "board",
}
EXPECTED_REFERENCE_ROWS = {
    "stock_daily_basic": 5507,
    "stock_financial": 5507,
    "index_membership": 12841,
    "board_membership": 56960,
}
RECENT_ACTIVE_REFERENCE_ROWS = {
    "board_membership": 56960,
}
OFFICIAL_NO_TRADE_IDENTITIES = (
    "stock:BJ:920305",
    "stock:SH:600193",
    "stock:SH:600608",
    "stock:SH:605081",
    "stock:SH:688121",
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
)
OFFICIAL_NO_TRADE_TS_CODES = {
    "stock:BJ:920305": "920305.BJ",
    "stock:SH:600193": "600193.SH",
    "stock:SH:600608": "600608.SH",
    "stock:SH:605081": "605081.SH",
    "stock:SH:688121": "688121.SH",
    "stock:SZ:000004": "000004.SZ",
    "stock:SZ:000638": "000638.SZ",
    "stock:SZ:000668": "000668.SZ",
    "stock:SZ:000736": "000736.SZ",
    "stock:SZ:001331": "001331.SZ",
    "stock:SZ:002200": "002200.SZ",
    "stock:SZ:002731": "002731.SZ",
    "stock:SZ:002808": "002808.SZ",
    "stock:SZ:002898": "002898.SZ",
    "stock:SZ:002969": "002969.SZ",
    "stock:SZ:300029": "300029.SZ",
    "stock:SZ:300175": "300175.SZ",
    "stock:SZ:300685": "300685.SZ",
}
STALE_IDENTITY_MANIFEST = (
    {
        "identity_key": "stock:SZ:300114",
        "ts_code": "300114.SZ",
        "superseded_by_identity_key": "stock:SZ:302132",
        "action": "manifest_only_do_not_modify_identity",
        "severity": "P1",
    },
)
ALLOWED_FUTURE_WRITE_TABLES = template.ALLOWED_FUTURE_WRITE_TABLES
DEFAULT_PATHS = {
    "dry_run_json": Path("docs/N1_condition_source_20260602_activation_dry_run_report.json"),
    "dry_run_md": Path("docs/N1_CONDITION_SOURCE_20260602_ACTIVATION_DRY_RUN_REPORT.md"),
    "contract_json": Path("docs/N1_condition_source_20260602_activation_execute_contract.json"),
    "contract_md": Path("docs/N1_CONDITION_SOURCE_20260602_ACTIVATION_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_condition_source_20260602_activation_execute_preflight.json"),
    "preflight_md": Path("docs/N1_CONDITION_SOURCE_20260602_ACTIVATION_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_condition_source_20260602_activation_rollback.sql"),
}

ConditionSourceActivation20260602Blocked = template.ConditionSourceActivation20260529Blocked


@contextmanager
def patched_template() -> Iterator[None]:
    overrides = {
        "TRADE_DATE": TRADE_DATE,
        "BATCH_ID": BATCH_ID,
        "TDX_ROOT": TDX_ROOT,
        "SOURCE_VERSIONS": SOURCE_VERSIONS,
        "ACTIVE_SCOPES": ACTIVE_SCOPES,
        "DATA_DOMAINS": DATA_DOMAINS,
        "EXPECTED_REFERENCE_ROWS": EXPECTED_REFERENCE_ROWS,
        "RECENT_ACTIVE_REFERENCE_ROWS": RECENT_ACTIVE_REFERENCE_ROWS,
        "OFFICIAL_NO_TRADE_IDENTITIES": OFFICIAL_NO_TRADE_IDENTITIES,
        "OFFICIAL_NO_TRADE_TS_CODES": OFFICIAL_NO_TRADE_TS_CODES,
        "STALE_IDENTITY_MANIFEST": STALE_IDENTITY_MANIFEST,
        "DEFAULT_PATHS": DEFAULT_PATHS,
    }
    previous = {name: getattr(template, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(template, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(template, name, value)


def _replace_20260529_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("20260529", "20260602")
    if isinstance(value, list):
        return [_replace_20260529_text(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace_20260529_text(item) for item in value)
    if isinstance(value, dict):
        return {key: _replace_20260529_text(item) for key, item in value.items()}
    return value


def _fix_report_text(report: Mapping[str, Any]) -> dict[str, Any]:
    fixed = dict(report)
    fixed["stage"] = str(fixed.get("stage") or "").replace("20260529", "20260602")
    if "execute_command_template" in fixed:
        fixed["execute_command_template"] = str(fixed["execute_command_template"]).replace("20260529", "20260602")
    if "quality_items" in fixed:
        fixed["quality_items"] = _replace_20260529_text(fixed["quality_items"])
    return _base.normalize_jsonable(fixed)


def now_iso() -> str:
    return template.now_iso()


def official_no_trade_manifest() -> list[dict[str, Any]]:
    with patched_template():
        return template.official_no_trade_manifest()


def sample_pass_snapshot() -> dict[str, Any]:
    with patched_template():
        snapshot = template.sample_pass_snapshot()
    snapshot["trade_date"] = TRADE_DATE
    snapshot["source_batch_id"] = BATCH_ID
    snapshot["upstream_daily"] = {
        "stock_daily": {"active_source_version": "stock_daily_20260602_v1", "row_count": 5507},
        "index_daily": {"active_source_version": "index_daily_20260602_v1", "row_count": 83},
        "board_daily": {"active_source_version": "board_daily_20260602_v1", "row_count": 428},
    }
    snapshot["stock_scope"] = {
        **(snapshot.get("stock_scope") or {}),
        "active_stock_identity_rows": 5526,
        "official_daily_stock_rows": 5507,
        "condition_stock_rows": 5507,
        "condition_source_gap_manifest_rows": len(official_no_trade_manifest()),
        "condition_source_gap_manifest": official_no_trade_manifest(),
        "official_no_trade_manifest": official_no_trade_manifest(),
        "stale_identity_manifest": list(STALE_IDENTITY_MANIFEST),
    }
    snapshot["membership_tdx"]["board_membership"].update(
        {
            "raw_rows": 56970,
            "filtered_rows": 56960,
            "missing_board_identity": 0,
            "missing_stock_identity": 7,
            "unmapped_raw_count": 10,
            "unmapped_unique_identity_count": 7,
            "duplicate_rows": 0,
        }
    )
    snapshot["current_target_fact_rows"] = {
        "stock_daily_basic": 0,
        "stock_financial": 0,
        "index_membership": 0,
        "board_membership": 0,
    }
    snapshot["target_source_version_conflicts"] = dict(snapshot["current_target_fact_rows"])
    snapshot["active_target_source_versions"] = []
    snapshot["contract_batch_exists"] = False
    return _base.normalize_jsonable(snapshot)


def build_snapshot_from_db(
    *,
    dsn: str,
    trade_date: str = TRADE_DATE,
    tdx_root: str | Path = TDX_ROOT,
) -> dict[str, Any]:
    with patched_template():
        return template.build_snapshot_from_db(dsn=dsn, trade_date=trade_date, tdx_root=tdx_root)


def build_expected_rows(snapshot: Mapping[str, Any]) -> dict[str, int]:
    with patched_template():
        return template.build_expected_rows(snapshot)


def build_quality_items(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    with patched_template():
        return _replace_20260529_text(template.build_quality_items(snapshot))


def summarize_quality(items: list[Mapping[str, Any]]) -> dict[str, int]:
    return template.summarize_quality(items)


def build_blockers(quality_items: list[Mapping[str, Any]]) -> list[str]:
    return template.build_blockers(quality_items)


def build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    with patched_template():
        report = template.build_execute_preflight_report(
            snapshot,
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
            postgres_commit_enabled=postgres_commit_enabled,
        )
    return _fix_report_text(report)


def build_dry_run_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    with patched_template():
        report = template.build_dry_run_report(snapshot)
    return _fix_report_text(report)


def build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    with patched_template():
        contract = template.build_execute_contract(snapshot)
    return _fix_report_text(contract)


class DefaultConditionSourceActivation20260602SourceBuilder:
    def __init__(self, *, tdx_root: str | Path = TDX_ROOT, tushare_token: str | None = None) -> None:
        self._builder = template.DefaultConditionSourceActivation20260529SourceBuilder(
            tdx_root=tdx_root,
            tushare_token=tushare_token,
        )

    def build_source_bundle(self, *, dsn: str, trade_date: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        with patched_template():
            return _base.normalize_jsonable(
                self._builder.build_source_bundle(dsn=dsn, trade_date=trade_date, snapshot=snapshot)
            )


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    template.validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )


def validate_source_bundle(*, bundle: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    with patched_template():
        report = template.validate_source_bundle(bundle=bundle, snapshot=snapshot)
    return _fix_report_text(report)


def validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    postgres_commit_enabled: bool,
) -> None:
    with patched_template():
        template.validate_commit_preconditions(
            snapshot=snapshot,
            validation_report=validation_report,
            postgres_commit_enabled=postgres_commit_enabled,
        )


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    with patched_template():
        plan = template.build_commit_plan(bundle=bundle, validation_report=validation_report, baseline=baseline)
    for row in plan.get("active_source_version_rows") or []:
        row["activated_by"] = "n1_condition_source_activation_20260602_execute_runner"
    plan["manifests"] = {
        **(plan.get("manifests") or {}),
        "official_no_trade_manifest": official_no_trade_manifest(),
        "stale_identity_manifest": list(STALE_IDENTITY_MANIFEST),
    }
    return _base.normalize_jsonable(plan)


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    unexpected_tables = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_FUTURE_WRITE_TABLES))
    if unexpected_tables:
        raise ConditionSourceActivation20260602Blocked(f"unexpected write tables: {unexpected_tables}")
    cur = conn.cursor()
    try:
        insert_ingest_batch(cur, commit_plan)
        _base.insert_stock_daily_basic_rows(cur, (commit_plan.get("rows") or {}).get("stock_daily_basic") or [])
        _base.insert_stock_financial_rows(cur, (commit_plan.get("rows") or {}).get("stock_financial") or [])
        _base.insert_index_membership_rows(cur, (commit_plan.get("rows") or {}).get("index_membership") or [])
        _base.insert_board_membership_rows(cur, (commit_plan.get("rows") or {}).get("board_membership") or [])
        _base.insert_quality_rows(cur, commit_plan.get("quality_rows") or [])
        _base.insert_active_source_version_rows(cur, commit_plan.get("active_source_version_rows") or [])
        update_ingest_batch_passed(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return _base.normalize_jsonable(
        {
            "committed": True,
            "batch_id": commit_plan.get("batch_id"),
            "written_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "row_counts": commit_plan.get("row_counts") or {},
            "rollback_safe": True,
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
        }
    )


def update_ingest_batch_passed(cur: Any) -> None:
    cur.execute(
        """
        UPDATE common_ingest_batch
        SET status = 'passed',
            finished_at = now()
        WHERE batch_id = %s
        """,
        (BATCH_ID,),
    )


def insert_ingest_batch(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_path, source_params, raw_hash, row_count, error_count,
          quality_gate_summary, error_summary, rollback_strategy, status, started_at
        )
        VALUES (
          %(batch_id)s, %(trade_date)s, 'common', 'condition_source_activation',
          'n1.condition_source_activation.20260602.v1', %(source_version)s,
          NULL, %(source_params)s, NULL, %(row_count)s, 0,
          %(quality_gate_summary)s, NULL, %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": BATCH_ID,
            "trade_date": TRADE_DATE,
            "source_version": BATCH_ID,
            "source_params": _base.jsonb_payload(
                {"source_versions": SOURCE_VERSIONS, "active_scopes": ACTIVE_SCOPES},
                context="common_ingest_batch.source_params",
            ),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total") or 0),
            "quality_gate_summary": _base.jsonb_payload(
                {
                    "expected_rows": commit_plan.get("row_counts") or {},
                    "official_no_trade_manifest_rows": len(official_no_trade_manifest()),
                    "stale_identity_manifest_rows": len(STALE_IDENTITY_MANIFEST),
                    "board_unmapped_raw_count": (commit_plan.get("manifests") or {}).get("board_unmapped_raw_count"),
                },
                context="common_ingest_batch.quality_gate_summary",
            ),
            "rollback_strategy": str(DEFAULT_PATHS["rollback_sql"]),
        },
    )


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    with patched_template():
        template.write_preflight_files(_fix_report_text(report), json_path=json_path, markdown_path=markdown_path)


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    with patched_template():
        template.write_contract_files(_fix_report_text(contract), json_path=json_path, markdown_path=markdown_path)


def write_dry_run_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    with patched_template():
        template.write_dry_run_files(_fix_report_text(report), json_path=json_path, markdown_path=markdown_path)


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    with patched_template():
        return template.render_preflight_markdown(_fix_report_text(report)).replace("20260529", "20260602")


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    with patched_template():
        return template.render_contract_markdown(_fix_report_text(contract)).replace("20260529", "20260602")


def render_dry_run_markdown(report: Mapping[str, Any]) -> str:
    with patched_template():
        return template.render_dry_run_markdown(_fix_report_text(report)).replace("20260529", "20260602")
