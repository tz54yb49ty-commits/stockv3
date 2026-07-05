"""Guarded scoped stock_identity repair for 920206.BJ on 20260608."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from ashare_v3.ingestion import stock_identity_refresh_20260529_execute as template


TRADE_DATE = "20260608"
BATCH_ID = "stock_identity_refresh_20260608_920206_v1"
SOURCE_VERSION = "stock_identity_20260608_v1"
PREVIOUS_SOURCE_VERSION = "stock_identity_20260605_v1"
PREVIOUS_SOURCE_BATCH_ID = "stock_identity_refresh_20260605_920211_v1"
ACTIVE_SCOPE_KEY = "A_STOCK:20260608"
EXPECTED_TS_CODE = "920206.BJ"
EXPECTED_IDENTITY_KEY = "stock:BJ:920206"
EXPECTED_IDENTITY = {
    "stock_identity_key": EXPECTED_IDENTITY_KEY,
    "ts_code": EXPECTED_TS_CODE,
    "code": "920206",
    "exchange": "BJ",
    "name": "彩客科技",
    "area": "河北",
    "industry": "染料涂料",
    "market": "北交所",
    "listed_date": TRADE_DATE,
    "status": "active",
}
DEFAULT_PATHS = {
    "contract_json": Path("docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_EXECUTE_CONTRACT.json"),
    "contract_md": Path("docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_EXECUTE_PREFLIGHT.json"),
    "preflight_md": Path("docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_20260608_stock_identity_920206_repair_rollback.sql"),
}
IMPLEMENTATION_REPORT_JSON = Path("docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_RUNNER_IMPLEMENTATION.json")
IMPLEMENTATION_REPORT_MD = Path("docs/N1_20260608_STOCK_IDENTITY_920206_REPAIR_RUNNER_IMPLEMENTATION.md")
ALLOWED_FUTURE_WRITE_TABLES = template.ALLOWED_FUTURE_WRITE_TABLES
FORBIDDEN_WRITE_TABLES = template.FORBIDDEN_WRITE_TABLES


class StockIdentity920206Repair20260608Blocked(RuntimeError):
    """Raised when the 20260608 920206 identity repair gate is blocked."""


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


def _convert_blocker(exc: Exception) -> StockIdentity920206Repair20260608Blocked:
    return StockIdentity920206Repair20260608Blocked(str(exc))


def _replace_text(value: Any) -> Any:
    if isinstance(value, str):
        text = value
        replacements = {
            "20260529": "20260608",
            "920218": "920206",
            "新天力": "彩客科技",
            "浙江": "河北",
            "塑料": "染料涂料",
            "stock_identity_refresh_20260529_v1": BATCH_ID,
            "stock_identity_20260529_v1": SOURCE_VERSION,
            "stock_identity_20260527_v1": PREVIOUS_SOURCE_VERSION,
            "A_STOCK:20260529": ACTIVE_SCOPE_KEY,
            "run_stock_identity_refresh_20260529_once.py": "run_n1_20260608_stock_identity_920206_repair_once.py",
            "n1_stock_identity_refresh_20260529_execute_runner": "n1_stock_identity_920206_repair_20260608_execute_runner",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    if isinstance(value, list):
        return [_replace_text(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace_text(item) for item in value)
    if isinstance(value, dict):
        return {key: _replace_text(item) for key, item in value.items()}
    return value


def _fix_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(_replace_text(dict(report)), ensure_ascii=False, default=str))


class DefaultStockIdentity920206Repair20260608SourceAdapter(template.DefaultStockIdentityRefresh20260529SourceAdapter):
    """Tushare proof adapter for the 920206.BJ identity row."""


def validate_target_request(*, trade_date: str, identity_key: str, ts_code: str) -> None:
    if trade_date != TRADE_DATE:
        raise StockIdentity920206Repair20260608Blocked(f"this runner is fixed to trade_date={TRADE_DATE}")
    if identity_key != EXPECTED_IDENTITY_KEY:
        raise StockIdentity920206Repair20260608Blocked(f"identity_key must be {EXPECTED_IDENTITY_KEY}")
    if ts_code != EXPECTED_TS_CODE:
        raise StockIdentity920206Repair20260608Blocked(f"ts_code must be {EXPECTED_TS_CODE}")


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> None:
    missing: list[str] = []
    if not execute_requested:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if not source_fetch_enabled:
        missing.append("--source-fetch-enabled")
    if not postgres_commit_enabled:
        missing.append("--postgres-commit-enabled")
    if missing:
        raise StockIdentity920206Repair20260608Blocked(f"missing required execute flag(s): {', '.join(missing)}")


def sample_pass_snapshot() -> dict[str, Any]:
    with patched_template():
        snapshot = _fix_report(template.sample_pass_snapshot())
    snapshot["latest_previous_active_source_version"] = PREVIOUS_SOURCE_VERSION
    snapshot["latest_previous_active_source_batch_id"] = PREVIOUS_SOURCE_BATCH_ID
    snapshot["existing_active_scope_key_count"] = 0
    return snapshot


def build_snapshot_from_db(*, dsn: str, trade_date: str = TRADE_DATE) -> dict[str, Any]:
    with patched_template():
        try:
            return _fix_report(template.build_snapshot_from_db(dsn=dsn, trade_date=trade_date))
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc


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
            plan = template.build_commit_plan(rows=rows, validation_report=validation_report, baseline=baseline)
        except template.StockIdentityRefresh20260529Blocked as exc:
            raise _convert_blocker(exc) from exc
    fixed = _fix_report(plan)
    fixed["active_source_version"]["activated_by"] = "n1_stock_identity_920206_repair_20260608_execute_runner"
    fixed["batch"]["source_params"]["previous_source_version"] = fixed["previous_source_version"]
    return fixed


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        source_fetch_enabled=source_fetch_enabled,
        postgres_commit_enabled=postgres_commit_enabled,
    )
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
    fixed["execute_flags"] = [
        "--execute",
        "--user-confirmed",
        "--source-fetch-enabled",
        "--postgres-commit-enabled",
    ]
    fixed["runner_readiness"] = "ready_for_final_gate"
    fixed["final_execute_gate_allowed"] = True
    return fixed


def build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    source_report: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    source_fetch_enabled: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    with patched_template():
        report = template.build_execute_preflight_report(
            snapshot,
            source_report=source_report,
            execute_requested=execute_requested,
            user_confirmed=user_confirmed,
        )
    fixed = _fix_report(report)
    fixed["runner_readiness"] = "ready_for_final_gate"
    fixed["final_execute_gate_allowed"] = fixed.get("result") == "PREFLIGHT_PASS"
    fixed["execute_flags"] = [
        "--execute",
        "--user-confirmed",
        "--source-fetch-enabled",
        "--postgres-commit-enabled",
    ]
    fixed["execute_command_candidate"] = (
        "PYTHONPATH=src python3 scripts/run_n1_20260608_stock_identity_920206_repair_once.py "
        "--trade-date 20260608 --identity-key stock:BJ:920206 --ts-code 920206.BJ "
        "--execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled"
    )
    if execute_requested:
        try:
            validate_execute_request(
                execute_requested=execute_requested,
                user_confirmed=user_confirmed,
                source_fetch_enabled=source_fetch_enabled,
                postgres_commit_enabled=postgres_commit_enabled,
            )
        except StockIdentity920206Repair20260608Blocked as exc:
            blockers = list(fixed.get("blockers") or [])
            blockers.append(str(exc))
            fixed["blockers"] = blockers
            fixed["result"] = "PREFLIGHT_BLOCKED"
            fixed["final_execute_gate_allowed"] = False
    return fixed


def blocked_source_report(message: str) -> dict[str, Any]:
    with patched_template():
        return _fix_report(template.blocked_source_report(message))


def build_implementation_report() -> dict[str, Any]:
    return {
        "gate": "N1_20260608_STOCK_IDENTITY_920206_REPAIR_RUNNER_IMPLEMENTATION_GATE",
        "layer_role": "N1_ingestion",
        "result": "IMPLEMENTATION_PASS",
        "runner_readiness": "ready_for_final_gate",
        "final_execute_gate_allowed": True,
        "execute_authorized": False,
        "trade_date": TRADE_DATE,
        "target": {
            "identity_key": EXPECTED_IDENTITY_KEY,
            "ts_code": EXPECTED_TS_CODE,
            "source_batch_id": BATCH_ID,
            "source_version": SOURCE_VERSION,
            "active_scope_key": ACTIVE_SCOPE_KEY,
        },
        "guard_summary": {
            "default_execute": False,
            "required_execute_flags": [
                "--execute",
                "--user-confirmed",
                "--source-fetch-enabled",
                "--postgres-commit-enabled",
            ],
            "wrong_trade_date_blocks": True,
            "wrong_identity_key_or_ts_code_blocks": True,
            "p0_blocks_execute": True,
            "rollback_unsafe_blocks": True,
        },
        "allowed_write_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "rollback_sql": str(DEFAULT_PATHS["rollback_sql"]),
        "forbidden_scope_proof": {
            "writes_performed": False,
            "postgres_written": False,
            "rollback_executed": False,
            "daily_facts_written": False,
            "condition_source_written": False,
            "n2_n3_n4_n5_n6_entered": False,
            "outbox_inbox_checkpoint_updated": False,
            "worker_started": False,
            "realtime_quote_pulled": False,
            "old_system_touched": False,
            "trade_or_sim_touched": False,
        },
        "next_gate": "N1_20260608_STOCK_IDENTITY_920206_REPAIR_EXECUTE_FINAL_GATE_REVIEW",
    }


def render_implementation_markdown(report: Mapping[str, Any]) -> str:
    return f"""# N1 20260608 Stock Identity 920206 Repair Runner Implementation

Result: `{report["result"]}`

- layer_role: `{report["layer_role"]}`
- runner_readiness: `{report["runner_readiness"]}`
- final_execute_gate_allowed: `{report["final_execute_gate_allowed"]}`
- execute_authorized: `{report["execute_authorized"]}`

## Guard Summary

```json
{json.dumps(report["guard_summary"], ensure_ascii=False, indent=2)}
```

## Allowed Write Tables

```json
{json.dumps(report["allowed_write_tables"], ensure_ascii=False, indent=2)}
```

## Forbidden Scope Proof

```json
{json.dumps(report["forbidden_scope_proof"], ensure_ascii=False, indent=2)}
```

## Next Gate

`{report["next_gate"]}`
"""


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
    write_markdown(markdown_path, "N1 20260608 Stock Identity 920206 Repair Execute Contract", contract)


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    write_json(json_path, report)
    write_markdown(markdown_path, "N1 20260608 Stock Identity 920206 Repair Execute Preflight", report)


def write_implementation_files(
    report: Mapping[str, Any] | None = None,
    *,
    json_path: str | Path = IMPLEMENTATION_REPORT_JSON,
    markdown_path: str | Path = IMPLEMENTATION_REPORT_MD,
) -> dict[str, Any]:
    payload = dict(report or build_implementation_report())
    write_json(json_path, payload)
    Path(markdown_path).write_text(render_implementation_markdown(payload), encoding="utf-8")
    return payload
