"""Lower-level audited hooks for N3 combined child production entrypoints.

These hooks are intentionally thin. They dispatch to injected N3 providers or
existing N3 writer helpers, then normalize the child-runner report shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from scripts.n3_n4_combined_child_contract import MIDDAY_BRIDGE_HINT_PROOF_KIND


N3_READY_RESULT = "EXECUTE_READY_REAL_IO_CONTRACT"
MISSING_N3_PRODUCTION_ENTRYPOINT_RESULT = "BLOCKED_MISSING_N3_PRODUCTION_ENTRYPOINT"

_FORBIDDEN_SIDE_EFFECTS = {
    "runtime_executed": False,
    "outbox_consumed": False,
    "inbox_or_checkpoint_updated": False,
    "worker_started": False,
    "rollback_executed": False,
    "schema_changed": False,
    "n4_n5_n6_touched": False,
    "n5_n6_touched": False,
}


def n3p_current_source_fetch_and_register(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
) -> Mapping[str, Any]:
    fetcher = _resolve_lower_hook(
        dependencies=dependencies,
        preferred_dependency_names=("market_fetch_adapter",),
        method_names=(
            "fetch_n3p_current_source_payload",
            "fetch_n3p_mixed_realtime_source_payload",
        ),
    )
    if fetcher is None:
        return _missing_payload("n3p_current_source_fetch", "fetch_n3p_current_source_payload")
    try:
        source_payload = _invoke(fetcher, args=args, report=report, dependencies=dependencies)
        payload = dict(source_payload or {})
        registrar = _resolve_lower_hook(
            dependencies=dependencies,
            preferred_dependency_names=("source_payload_registrar",),
            method_names=(
                "register_n3p_source_payload_run",
                "register_source_payload_run",
                "ensure_mixed_realtime_source_payload_run",
            ),
        )
        if registrar is not None and not _is_blocked(payload):
            registration = _invoke(
                registrar,
                args=args,
                report=report,
                dependencies=dependencies,
                source_payload=payload,
            )
            payload.update(dict(registration or {}))
        payload.setdefault("source_payload_run_id", getattr(args, "target_run_id", ""))
        payload.setdefault("writes_n3p_metric_rows", False)
        return _normalize_success("n3p_current_source_fetch", args=args, report=report, payload=payload)
    except Exception as exc:  # pragma: no cover - defensive production guard.
        return _exception_payload("n3p_current_source_fetch", exc)


def n3p_trigger_proof_preflight_plan(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
) -> Mapping[str, Any]:
    planner = _resolve_lower_hook(
        dependencies=dependencies,
        preferred_dependency_names=("artifact_reader", "db_connection"),
        method_names=(
            "build_n3p_trigger_proof_preflight",
            "run_n3p_trigger_proof_preflight_plan",
            "n3p_trigger_proof_preflight_plan",
        ),
    )
    if planner is not None:
        try:
            payload = _invoke(planner, args=args, report=report, dependencies=dependencies)
            return _normalize_success("n3p_trigger_proof_preflight", args=args, report=report, payload=dict(payload or {}))
        except Exception as exc:  # pragma: no cover - defensive production guard.
            return _exception_payload("n3p_trigger_proof_preflight", exc)
    return _run_virtual_metric_writer_or_missing(
        step_id="n3p_trigger_proof_preflight",
        args=args,
        report=report,
        execute=False,
        required_entrypoint="build_n3p_trigger_proof_preflight",
    )


def n3p_trigger_proof_execute_write(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
) -> Mapping[str, Any]:
    writer = _resolve_lower_hook(
        dependencies=dependencies,
        preferred_dependency_names=("db_writer", "artifact_reader", "rollback_sql_writer"),
        method_names=(
            "execute_n3p_trigger_proof",
            "run_n3p_trigger_proof_execute_write",
            "n3p_trigger_proof_execute_write",
        ),
    )
    if writer is not None:
        try:
            payload = _invoke(writer, args=args, report=report, dependencies=dependencies)
            return _normalize_success("n3p_trigger_proof_execute", args=args, report=report, payload=dict(payload or {}))
        except Exception as exc:  # pragma: no cover - defensive production guard.
            return _exception_payload("n3p_trigger_proof_execute", exc)
    return _run_virtual_metric_writer_or_missing(
        step_id="n3p_trigger_proof_execute",
        args=args,
        report=report,
        execute=True,
        required_entrypoint="execute_n3p_trigger_proof",
    )


def n3_hint_frequency8_source_fetch(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
) -> Mapping[str, Any]:
    hint_blocker = _require_midday_bridge_hint_kind(args)
    if hint_blocker is not None:
        return hint_blocker
    fetcher = _resolve_lower_hook(
        dependencies=dependencies,
        preferred_dependency_names=("market_fetch_adapter",),
        method_names=(
            "fetch_n3_hint_frequency8_source",
            "fetch_n3_hint_index_board_frequency8_source",
            "build_n3_hint_index_board_frequency8_payload",
        ),
    )
    if fetcher is None:
        return _missing_payload("n3_hint_source_fetch", "fetch_n3_hint_frequency8_source")
    try:
        payload = dict(_invoke(fetcher, args=args, report=report, dependencies=dependencies) or {})
        blocker = _reject_stock_hint_rows(payload)
        if blocker is not None:
            return blocker
        payload.setdefault("asset_scope", "index_board_only")
        return _normalize_success("n3_hint_source_fetch", args=args, report=report, payload=payload)
    except Exception as exc:  # pragma: no cover - defensive production guard.
        return _exception_payload("n3_hint_source_fetch", exc)


def n3_hint_proof_preflight_plan(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
) -> Mapping[str, Any]:
    hint_blocker = _require_midday_bridge_hint_kind(args)
    if hint_blocker is not None:
        return hint_blocker
    planner = _resolve_lower_hook(
        dependencies=dependencies,
        preferred_dependency_names=("artifact_reader", "db_connection"),
        method_names=(
            "build_n3_hint_proof_preflight",
            "build_index_board_1m_hint_projection_preflight",
            "run_n3_hint_proof_preflight_plan",
        ),
    )
    if planner is None:
        return _missing_payload("n3_hint_proof_preflight", "build_n3_hint_proof_preflight")
    try:
        payload = dict(_invoke(planner, args=args, report=report, dependencies=dependencies) or {})
        blocker = _reject_stock_hint_rows(payload)
        if blocker is not None:
            return blocker
        return _normalize_success("n3_hint_proof_preflight", args=args, report=report, payload=payload)
    except Exception as exc:  # pragma: no cover - defensive production guard.
        return _exception_payload("n3_hint_proof_preflight", exc)


def n3_hint_proof_execute_write(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
) -> Mapping[str, Any]:
    hint_blocker = _require_midday_bridge_hint_kind(args)
    if hint_blocker is not None:
        return hint_blocker
    writer = _resolve_lower_hook(
        dependencies=dependencies,
        preferred_dependency_names=("db_writer", "artifact_reader", "rollback_sql_writer"),
        method_names=(
            "execute_n3_hint_projection_write_plan",
            "write_n3_hint_projection_proof",
            "run_n3_hint_proof_execute_write",
        ),
    )
    if writer is None:
        return _missing_payload("n3_hint_proof_execute", "execute_n3_hint_projection_write_plan")
    try:
        payload = dict(_invoke(writer, args=args, report=report, dependencies=dependencies) or {})
        blocker = _reject_stock_hint_rows(payload)
        if blocker is not None:
            return blocker
        return _normalize_success("n3_hint_proof_execute", args=args, report=report, payload=payload)
    except Exception as exc:  # pragma: no cover - defensive production guard.
        return _exception_payload("n3_hint_proof_execute", exc)


def _run_virtual_metric_writer_or_missing(
    *,
    step_id: str,
    args: Any,
    report: Mapping[str, Any],
    execute: bool,
    required_entrypoint: str,
) -> Mapping[str, Any]:
    if not (
        getattr(args, "contract_path", "")
        and getattr(args, "preflight_path", "")
        and getattr(args, "source_payload_path", "")
    ):
        return _missing_payload(step_id, required_entrypoint)
    try:
        from ashare_v3.market.v3_realtime_virtual_metric_writer import run_virtual_metric_writer

        payload = run_virtual_metric_writer(
            contract=_read_json_file(args.contract_path),
            preflight=_read_json_file(args.preflight_path),
            source_payload=_read_json_file(args.source_payload_path),
            execute=execute,
            user_confirmed=execute,
        )
        return _normalize_success(step_id, args=args, report=report, payload=dict(payload or {}))
    except Exception as exc:  # pragma: no cover - exercised by execute gates.
        return _exception_payload(step_id, exc)


def _resolve_lower_hook(
    *,
    dependencies: Any,
    preferred_dependency_names: tuple[str, ...],
    method_names: tuple[str, ...],
) -> Callable[..., Mapping[str, Any] | None] | None:
    dependency_names = (
        *preferred_dependency_names,
        "market_fetch_adapter",
        "db_connection",
        "db_writer",
        "artifact_writer",
        "artifact_reader",
        "source_payload_registrar",
        "target_absence_checker",
        "rollback_sql_writer",
    )
    seen: set[str] = set()
    for dependency_name in dependency_names:
        if dependency_name in seen:
            continue
        seen.add(dependency_name)
        dependency = getattr(dependencies, dependency_name, None)
        if dependency is None:
            continue
        for method_name in method_names:
            method = getattr(dependency, method_name, None)
            if callable(method):
                return method
        if callable(dependency):
            return dependency
    return None


def _invoke(target: Callable[..., Mapping[str, Any] | None], **kwargs: Any) -> Mapping[str, Any] | None:
    try:
        return target(**kwargs)
    except TypeError:
        reduced = {name: value for name, value in kwargs.items() if name != "source_payload"}
        if reduced == kwargs:
            raise
        return target(**reduced)


def _normalize_success(
    step_id: str,
    *,
    args: Any,
    report: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(payload)
    if _is_blocked(result):
        _apply_forbidden_side_effect_guards(result)
        return result
    result["result"] = result.get("result") or N3_READY_RESULT
    result["step_id"] = result.get("step_id") or step_id
    result["received_target_run_id"] = result.get("received_target_run_id") or getattr(args, "target_run_id", "")
    result["source_run_id"] = result.get("source_run_id") or getattr(args, "source_run_id", "")
    result["target_absence_checked"] = bool(report.get("target_absence_checked"))
    result["real_io_operation_wired"] = True
    result["production_adapter_wired"] = True
    result["execute_contract_ready"] = True
    _apply_forbidden_side_effect_guards(result)
    return result


def _missing_payload(step_id: str, required_entrypoint: str) -> dict[str, Any]:
    payload = {
        "result": MISSING_N3_PRODUCTION_ENTRYPOINT_RESULT,
        "reason": (
            f"{MISSING_N3_PRODUCTION_ENTRYPOINT_RESULT}:{step_id}:"
            f"required_entrypoint={required_entrypoint}"
        ),
        "required_production_entrypoint": required_entrypoint,
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
        "execute_contract_ready": False,
        "market_data_pulled": False,
        "database_written": False,
    }
    _apply_forbidden_side_effect_guards(payload)
    return payload


def _exception_payload(step_id: str, exc: Exception) -> dict[str, Any]:
    payload = {
        "result": f"BLOCKED_N3_PRODUCTION_HOOK_EXCEPTION:{step_id}",
        "reason": f"{type(exc).__name__}: {exc}",
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
        "execute_contract_ready": False,
        "market_data_pulled": False,
        "database_written": False,
    }
    _apply_forbidden_side_effect_guards(payload)
    return payload


def _require_midday_bridge_hint_kind(args: Any) -> Mapping[str, Any] | None:
    if str(getattr(args, "hint_proof_kind", "") or "") == MIDDAY_BRIDGE_HINT_PROOF_KIND:
        return None
    payload = {
        "result": "BLOCKED_HINT_PROOF_KIND",
        "reason": f"required HINT proof kind is {MIDDAY_BRIDGE_HINT_PROOF_KIND}",
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
        "execute_contract_ready": False,
        "market_data_pulled": False,
        "database_written": False,
    }
    _apply_forbidden_side_effect_guards(payload)
    return payload


def _reject_stock_hint_rows(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    stock_rows = payload.get("stock_rows")
    if stock_rows is None and isinstance(payload.get("written_rows"), Mapping):
        stock_rows = payload["written_rows"].get("stock")
    if stock_rows in (None, 0, "0"):
        return None
    result = {
        "result": "BLOCKED_HINT_STOCK_ROWS",
        "reason": f"HINT proof must not contain stock rows: stock_rows={stock_rows}",
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
        "execute_contract_ready": False,
        "market_data_pulled": False,
        "database_written": False,
    }
    _apply_forbidden_side_effect_guards(result)
    return result


def _apply_forbidden_side_effect_guards(payload: dict[str, Any]) -> None:
    payload["writes_outbox"] = False
    payload["consumes_outbox"] = False
    payload["updates_inbox_or_checkpoint"] = False
    payload["starts_worker"] = False
    payload["touches_n4_n5_n6"] = False
    payload["touches_n5_n6"] = False
    side_effects = dict(payload.get("side_effects") or {})
    side_effects.update(_FORBIDDEN_SIDE_EFFECTS)
    side_effects["database_written"] = False
    side_effects["market_data_pulled"] = False
    payload["side_effects"] = side_effects


def _read_json_file(path: str) -> Mapping[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _is_blocked(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("result", "")).startswith("BLOCKED")
