"""Execute runner support for N1 stock_identity refresh on 20260605.

The scope is intentionally one stock: ``920211.BJ``. The module reuses the
verified 20260529 guarded identity refresh mechanics, with constants patched to
the 20260605 target. Import/preflight is safe; PostgreSQL writes require both
explicit execute flags in the run-once CLI.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from ashare_v3.ingestion import stock_identity_refresh_20260529_execute as template


TRADE_DATE = "20260605"
BATCH_ID = "stock_identity_refresh_20260605_920211_v1"
SOURCE_VERSION = "stock_identity_20260605_v1"
PREVIOUS_SOURCE_VERSION = "stock_identity_20260604_v1"
PREVIOUS_SOURCE_BATCH_ID = "stock_identity_20260604_v1"
ACTIVE_SCOPE_KEY = "A_STOCK:20260605"
EXPECTED_TS_CODE = "920211.BJ"
EXPECTED_IDENTITY_KEY = "stock:BJ:920211"
EXPECTED_IDENTITY = {
    "stock_identity_key": EXPECTED_IDENTITY_KEY,
    "ts_code": EXPECTED_TS_CODE,
    "code": "920211",
    "exchange": "BJ",
    "name": "",
    "area": "",
    "industry": "",
    "market": "",
    "listed_date": TRADE_DATE,
    "status": "active",
}
DEFAULT_PATHS = {
    "contract_json": Path("docs/N1_stock_identity_920211_20260605_refresh_execute_contract.json"),
    "contract_md": Path("docs/N1_STOCK_IDENTITY_920211_20260605_REFRESH_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_stock_identity_920211_20260605_refresh_execute_preflight.json"),
    "preflight_md": Path("docs/N1_STOCK_IDENTITY_920211_20260605_REFRESH_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_stock_identity_920211_20260605_refresh_rollback.sql"),
}
ALLOWED_FUTURE_WRITE_TABLES = template.ALLOWED_FUTURE_WRITE_TABLES
FORBIDDEN_WRITE_TABLES = template.FORBIDDEN_WRITE_TABLES


class StockIdentityRefresh20260605920211Blocked(RuntimeError):
    """Raised when the 20260605 920211 stock_identity refresh is blocked."""


_PATCH_VALUES = {
    "TRADE_DATE": TRADE_DATE,
    "BATCH_ID": BATCH_ID,
    "SOURCE_VERSION": SOURCE_VERSION,
    "PREVIOUS_SOURCE_VERSION": PREVIOUS_SOURCE_VERSION,
    "PREVIOUS_SOURCE_BATCH_ID": PREVIOUS_SOURCE_BATCH_ID,
    "ACTIVE_SCOPE_KEY": ACTIVE_SCOPE_KEY,
    "EXPECTED_TS_CODE": EXPECTED_TS_CODE,
    "EXPECTED_IDENTITY_KEY": EXPECTED_IDENTITY_KEY,
    "EXPECTED_IDENTITY": EXPECTED_IDENTITY,
    "DEFAULT_PATHS": DEFAULT_PATHS,
}


@contextmanager
def patched_template() -> Iterator[None]:
    previous = {name: getattr(template, name) for name in _PATCH_VALUES}
    try:
        for name, value in _PATCH_VALUES.items():
            setattr(template, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(template, name, value)


def _convert_blocker(exc: Exception) -> StockIdentityRefresh20260605920211Blocked:
    return StockIdentityRefresh20260605920211Blocked(str(exc))


def _replace_text(value: Any) -> Any:
    if isinstance(value, str):
        return (
            value.replace("20260529", "20260605")
            .replace("920218", "920211")
            .replace("新天力", "")
            .replace("run_stock_identity_refresh_20260605_once.py", "run_stock_identity_refresh_20260605_920211_once.py")
            .replace("run_stock_identity_refresh_20260529_once.py", "run_stock_identity_refresh_20260605_920211_once.py")
            .replace("n1_stock_identity_refresh_20260605_execute_runner", "n1_stock_identity_refresh_20260605_920211_execute_runner")
            .replace("n1_stock_identity_refresh_20260529_execute_runner", "n1_stock_identity_refresh_20260605_920211_execute_runner")
        )
    if isinstance(value, list):
        return [_replace_text(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace_text(item) for item in value)
    if isinstance(value, dict):
        return {key: _replace_text(item) for key, item in value.items()}
    return value


def _fix_report(report: Mapping[str, Any]) -> dict[str, Any]:
    fixed = _replace_text(dict(report))
    return json.loads(json.dumps(fixed, ensure_ascii=False, default=str))


class DefaultStockIdentityRefresh20260605920211SourceAdapter(template.DefaultStockIdentityRefresh20260529SourceAdapter):
    """Tushare proof adapter for the 920211.BJ identity row."""


def now_iso() -> str:
    return template.now_iso()


def sample_pass_snapshot() -> dict[str, Any]:
    with patched_template():
        return _fix_report(template.sample_pass_snapshot())


def validate_execute_request(*, execute_requested: bool, user_confirmed: bool) -> None:
    with patched_template():
        try:
            template.validate_execute_request(execute_requested=execute_requested, user_confirmed=user_confirmed)
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    with patched_template():
        try:
            return _fix_report(template.build_snapshot_from_db(dsn=dsn, trade_date=trade_date))
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


def frame_to_records(frame: Any) -> list[dict[str, Any]]:
    return template.frame_to_records(frame)


def validate_source_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    with patched_template():
        try:
            return _fix_report(template.validate_source_evidence(evidence))
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


def build_target_identity_rows(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    with patched_template():
        try:
            return _fix_report({"rows": template.build_target_identity_rows(evidence)})["rows"]
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


def validate_source_rows(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    with patched_template():
        try:
            return _fix_report(template.validate_source_rows(rows))
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


def validate_commit_preconditions(*, snapshot: Mapping[str, Any], validation_report: Mapping[str, Any]) -> None:
    with patched_template():
        try:
            template.validate_commit_preconditions(snapshot=snapshot, validation_report=validation_report)
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


def build_commit_plan(*, rows: list[Mapping[str, Any]], validation_report: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    with patched_template():
        try:
            return _fix_report(template.build_commit_plan(rows=rows, validation_report=validation_report, baseline=baseline))
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    with patched_template():
        try:
            return _fix_report(
                template.execute_commit_transaction(
                    conn,
                    commit_plan=commit_plan,
                    execute_requested=execute_requested,
                    user_confirmed=user_confirmed,
                )
            )
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


def build_execute_contract(snapshot: Mapping[str, Any], *, source_report: Mapping[str, Any]) -> dict[str, Any]:
    with patched_template():
        contract = template.build_execute_contract(snapshot, source_report=source_report)
    fixed = _fix_report(contract)
    source_rows = (((source_report or {}).get("source_evidence_summary") or {}).get("stock_basic") or [])
    if source_rows:
        raw = source_rows[0]
        fixed["new_identity_rows"] = [
            {
                "stock_identity_key": EXPECTED_IDENTITY_KEY,
                "ts_code": EXPECTED_TS_CODE,
                "code": "920211",
                "exchange": "BJ",
                "name": raw.get("name"),
                "area": raw.get("area"),
                "industry": raw.get("industry"),
                "market": raw.get("market"),
                "listed_date": raw.get("list_date"),
                "delisted_date": raw.get("delist_date"),
                "is_st": str(raw.get("name") or "").upper().startswith(("ST", "*ST")),
                "status": "active",
            }
        ]
    return fixed


def build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    source_report: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    with patched_template():
        return _fix_report(
            template.build_execute_preflight_report(
                snapshot,
                source_report=source_report,
                execute_requested=execute_requested,
                user_confirmed=user_confirmed,
            )
        )


def blocked_source_report(message: str) -> dict[str, Any]:
    with patched_template():
        return _fix_report(template.blocked_source_report(message))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    template.write_json(path, payload)


def write_markdown(path: str | Path, title: str, payload: Mapping[str, Any]) -> None:
    Path(path).write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                "```json",
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, contract)
    write_markdown(markdown_path, "N1 Stock Identity 920211 20260605 Refresh Execute Contract", contract)


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, report)
    write_markdown(markdown_path, "N1 Stock Identity 920211 20260605 Refresh Execute Preflight", report)
