"""Audited N3 child runner adapters for combined run-once wrappers.

The wrappers own contract checks and target absence ordering. Real N3 I/O is
injected through operation/dependency seams so patch tests can prove the call
path without touching network or database state.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from scripts.n3_n4_combined_child_contract import MIDDAY_BRIDGE_HINT_PROOF_KIND


N3_READY_RESULT = "EXECUTE_READY_REAL_IO_CONTRACT"
MISSING_N3_REAL_RUNNER_RESULT = "BLOCKED_MISSING_N3_REAL_RUNNER"
MISSING_N3_REAL_IO_RESULT = "BLOCKED_MISSING_N3_REAL_IO"
MISSING_N3_PRODUCTION_ENTRYPOINT_RESULT = "BLOCKED_MISSING_N3_PRODUCTION_ENTRYPOINT"

N3_REAL_RUNNER_STEP_IDS = (
    "n3p_current_source_fetch",
    "n3p_trigger_proof_preflight",
    "n3_hint_source_fetch",
    "n3_hint_proof_preflight",
    "n3_hint_proof_execute",
)
N3_HINT_SOURCE_FETCH_BACKEND_BLOCKER = "BLOCKED_N3_HINT_SOURCE_FETCH_BACKEND"

_STEP_TO_OPERATION_ATTRS = {
    "n3p_current_source_fetch": ("fetch_n3p_current_source", "n3p_current_source_fetch"),
    "n3p_trigger_proof_preflight": ("preflight_n3p_trigger_proof", "n3p_trigger_proof_preflight"),
    "n3_hint_source_fetch": ("fetch_n3_hint_source", "n3_hint_source_fetch"),
    "n3_hint_proof_preflight": ("preflight_n3_hint_proof", "n3_hint_proof_preflight"),
    "n3_hint_proof_execute": ("execute_n3_hint_proof", "n3_hint_proof_execute"),
}

RunnerOperation = Callable[..., Mapping[str, Any] | None]


@dataclass(frozen=True)
class N3RealRunnerOperations:
    fetch_n3p_current_source: RunnerOperation | None = None
    preflight_n3p_trigger_proof: RunnerOperation | None = None
    fetch_n3_hint_source: RunnerOperation | None = None
    preflight_n3_hint_proof: RunnerOperation | None = None
    execute_n3_hint_proof: RunnerOperation | None = None
    # Compatibility aliases for older tests/callers; new code should use the
    # verb-based operation names above.
    n3p_current_source_fetch: RunnerOperation | None = None
    n3p_trigger_proof_preflight: RunnerOperation | None = None
    n3_hint_source_fetch: RunnerOperation | None = None
    n3_hint_proof_preflight: RunnerOperation | None = None
    n3_hint_proof_execute: RunnerOperation | None = None


@dataclass(frozen=True)
class N3RealIODependencies:
    market_fetch_adapter: Any = None
    db_connection: Any = None
    db_writer: Any = None
    artifact_writer: Any = None
    artifact_reader: Any = None
    source_payload_registrar: Any = None
    target_absence_checker: Any = None
    rollback_sql_writer: Any = None


class N3ProductionRealIOAdapter:
    """Default production adapter for audited N3 child wrappers.

    Each method delegates to a module-level production entrypoint. The entrypoint
    may still fail closed if the reusable N3 implementation it needs is absent.
    """

    def __init__(
        self,
        *,
        n3p_source_fetch_backend: Any = None,
        n3p_trigger_proof_preflight_backend: Any = None,
        hint_source_fetch_backend: Any = None,
        hint_proof_preflight_backend: Any = None,
        hint_proof_execute_backend: Any = None,
    ) -> None:
        from scripts.n3_hint_frequency8_source_provider import (
            N3HintFrequency8MarketFetchAdapter,
            N3HintProofExecuteBackend,
            N3HintProofExecuteProvider,
            N3HintProofPreflightBackend,
            N3HintProofPreflightProvider,
            N3HintFrequency8SourceBackend,
            N3HintFrequency8SourceProvider,
        )
        from scripts.n3p_current_source_fetch_provider import (
            N3PCurrentMarketFetchAdapter,
            N3PCurrentSourceFetchBackend,
            N3PCurrentSourceFetchProvider,
            N3PTriggerProofPreflightBackend,
            N3PTriggerProofPreflightProvider,
        )

        backend = (
            n3p_source_fetch_backend
            if n3p_source_fetch_backend is not None
            else N3PCurrentSourceFetchBackend(market_fetcher=N3PCurrentMarketFetchAdapter())
        )
        self._n3p_source_fetch_provider = N3PCurrentSourceFetchProvider(backend=backend)
        self._n3_hint_source_fetch_provider = N3HintFrequency8SourceProvider(
            backend=(
                hint_source_fetch_backend
                if hint_source_fetch_backend is not None
                else N3HintFrequency8SourceBackend(market_fetcher=N3HintFrequency8MarketFetchAdapter())
            )
        )
        self._n3_hint_proof_preflight_provider = N3HintProofPreflightProvider(
            backend=(
                hint_proof_preflight_backend
                if hint_proof_preflight_backend is not None
                else N3HintProofPreflightBackend()
            )
        )
        self._n3_hint_proof_execute_provider = N3HintProofExecuteProvider(
            backend=(
                hint_proof_execute_backend
                if hint_proof_execute_backend is not None
                else N3HintProofExecuteBackend()
            )
        )
        preflight_backend = (
            n3p_trigger_proof_preflight_backend
            if n3p_trigger_proof_preflight_backend is not None
            else backend
            if callable(getattr(backend, "build_n3p_trigger_proof_preflight", None))
            else N3PTriggerProofPreflightBackend()
        )
        self._n3p_trigger_proof_preflight_provider = N3PTriggerProofPreflightProvider(backend=preflight_backend)

    def fetch_n3p_current_source(self, *, args: argparse.Namespace, report: Mapping[str, Any], dependencies: N3RealIODependencies) -> Mapping[str, Any]:
        return run_n3p_current_source_fetch(args=args, report=report, dependencies=dependencies)

    def fetch_n3p_current_source_payload(self, *, args: argparse.Namespace, report: Mapping[str, Any], dependencies: N3RealIODependencies) -> Mapping[str, Any]:
        return self._n3p_source_fetch_provider.fetch_n3p_current_source_payload(args=args, report=report, dependencies=dependencies)

    def register_n3p_source_payload_run(self, *, args: argparse.Namespace, report: Mapping[str, Any], dependencies: N3RealIODependencies, source_payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._n3p_source_fetch_provider.register_n3p_source_payload_run(args=args, report=report, dependencies=dependencies, source_payload=source_payload)

    def preflight_n3p_trigger_proof(self, *, args: argparse.Namespace, report: Mapping[str, Any], dependencies: N3RealIODependencies) -> Mapping[str, Any]:
        return run_n3p_trigger_proof_preflight(args=args, report=report, dependencies=dependencies)

    def build_n3p_trigger_proof_preflight(self, *, args: argparse.Namespace, report: Mapping[str, Any], dependencies: N3RealIODependencies) -> Mapping[str, Any]:
        return self._n3p_trigger_proof_preflight_provider.build_n3p_trigger_proof_preflight(args=args, report=report, dependencies=dependencies)

    def fetch_n3_hint_source(self, *, args: argparse.Namespace, report: Mapping[str, Any], dependencies: N3RealIODependencies) -> Mapping[str, Any]:
        return run_n3_hint_source_fetch(args=args, report=report, dependencies=dependencies)

    def fetch_n3_hint_frequency8_source(
        self,
        *,
        args: argparse.Namespace,
        report: Mapping[str, Any],
        dependencies: N3RealIODependencies,
    ) -> Mapping[str, Any]:
        return self._n3_hint_source_fetch_provider.fetch_n3_hint_frequency8_source(
            args=args,
            report=report,
            dependencies=dependencies,
        )

    def preflight_n3_hint_proof(self, *, args: argparse.Namespace, report: Mapping[str, Any], dependencies: N3RealIODependencies) -> Mapping[str, Any]:
        return run_n3_hint_proof_preflight(args=args, report=report, dependencies=dependencies)

    def build_n3_hint_proof_preflight(
        self,
        *,
        args: argparse.Namespace,
        report: Mapping[str, Any],
        dependencies: N3RealIODependencies,
    ) -> Mapping[str, Any]:
        return self._n3_hint_proof_preflight_provider.build_n3_hint_proof_preflight(
            args=args,
            report=report,
            dependencies=dependencies,
        )

    def execute_n3_hint_proof(self, *, args: argparse.Namespace, report: Mapping[str, Any], dependencies: N3RealIODependencies) -> Mapping[str, Any]:
        return run_n3_hint_proof_execute(args=args, report=report, dependencies=dependencies)

    def execute_n3_hint_projection_write_plan(
        self,
        *,
        args: argparse.Namespace,
        report: Mapping[str, Any],
        dependencies: N3RealIODependencies,
    ) -> Mapping[str, Any]:
        return self._n3_hint_proof_execute_provider.execute_n3_hint_projection_write_plan(
            args=args,
            report=report,
            dependencies=dependencies,
        )


def run_n3p_current_source_fetch(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    from scripts.n3_combined_child_production_hooks import n3p_current_source_fetch_and_register

    return n3p_current_source_fetch_and_register(args=args, report=report, dependencies=dependencies)


def run_n3p_trigger_proof_preflight(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    from scripts.n3_combined_child_production_hooks import n3p_trigger_proof_preflight_plan

    return n3p_trigger_proof_preflight_plan(args=args, report=report, dependencies=dependencies)


def run_n3p_trigger_proof_execute(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    from scripts.n3_combined_child_production_hooks import n3p_trigger_proof_execute_write

    return n3p_trigger_proof_execute_write(args=args, report=report, dependencies=dependencies)


def run_n3_hint_source_fetch(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    from scripts.n3_combined_child_production_hooks import n3_hint_frequency8_source_fetch

    return n3_hint_frequency8_source_fetch(args=args, report=report, dependencies=dependencies)


def run_n3_hint_proof_preflight(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    from scripts.n3_combined_child_production_hooks import n3_hint_proof_preflight_plan

    return n3_hint_proof_preflight_plan(args=args, report=report, dependencies=dependencies)


def run_n3_hint_proof_execute(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    from scripts.n3_combined_child_production_hooks import n3_hint_proof_execute_write

    return n3_hint_proof_execute_write(args=args, report=report, dependencies=dependencies)


def build_default_n3_real_runner_operations() -> N3RealRunnerOperations:
    return N3RealRunnerOperations(
        fetch_n3p_current_source=_production_n3p_current_source_fetch,
        preflight_n3p_trigger_proof=_production_n3p_trigger_proof_preflight,
        fetch_n3_hint_source=_production_n3_hint_source_fetch,
        preflight_n3_hint_proof=_production_n3_hint_proof_preflight,
        execute_n3_hint_proof=_production_n3_hint_proof_execute,
    )


def build_n3_real_layer_runner(
    step_id: str,
    *,
    operations: N3RealRunnerOperations | None = None,
    dependencies: N3RealIODependencies | None = None,
) -> RunnerOperation | None:
    operation_attrs = _STEP_TO_OPERATION_ATTRS.get(step_id)
    if operation_attrs is None:
        return None
    resolved_operations = operations if operations is not None else DEFAULT_N3_REAL_RUNNER_OPERATIONS
    resolved_dependencies = dependencies if dependencies is not None else DEFAULT_N3_REAL_IO_DEPENDENCIES
    operation = _resolve_operation(resolved_operations, operation_attrs)

    def _runner(*, args: argparse.Namespace, report: Mapping[str, Any]) -> dict[str, Any]:
        if operation is None:
            return _missing_real_io_payload(step_id=step_id, args=args, report=report)
        raw_payload = operation(args=args, report=report, dependencies=resolved_dependencies) or {}
        return _normalize_real_runner_payload(
            step_id=step_id,
            args=args,
            report=report,
            dependencies=resolved_dependencies,
            raw_payload=raw_payload,
        )

    return _runner


def _resolve_operation(
    operations: N3RealRunnerOperations,
    operation_attrs: tuple[str, ...],
) -> RunnerOperation | None:
    for attr in operation_attrs:
        operation = getattr(operations, attr)
        if operation is not None:
            return operation
    return None


def _missing_runner_payload(
    *,
    step_id: str,
    args: argparse.Namespace,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "result": MISSING_N3_REAL_RUNNER_RESULT,
        "reason": f"{MISSING_N3_REAL_RUNNER_RESULT}:{step_id}",
        "layer_runner_called": True,
        "layer_runner_step_id": step_id,
        "layer_runner_name": f"{step_id}_real_runner",
        "real_runner_wired": False,
        "execute_contract_ready": False,
        "target_absence_checked": bool(report.get("target_absence_checked")),
        "received_target_run_id": args.target_run_id,
    }
    _apply_real_runner_safety_fields(payload)
    return payload


def _missing_real_io_payload(
    *,
    step_id: str,
    args: argparse.Namespace,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "result": MISSING_N3_REAL_IO_RESULT,
        "reason": f"{MISSING_N3_REAL_IO_RESULT}:{step_id}",
        "layer_runner_called": True,
        "layer_runner_step_id": step_id,
        "layer_runner_name": f"{step_id}_real_runner",
        "real_runner_wired": True,
        "real_io_operation_wired": False,
        "execute_contract_ready": False,
        "target_absence_checked": bool(report.get("target_absence_checked")),
        "received_target_run_id": args.target_run_id,
    }
    _apply_real_runner_safety_fields(payload)
    return payload


def _normalize_real_runner_payload(
    *,
    step_id: str,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
    raw_payload: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(raw_payload)
    if not str(payload.get("result", "")).startswith("BLOCKED"):
        payload["result"] = payload.get("result") or N3_READY_RESULT
        payload["real_io_operation_wired"] = True
        payload["execute_contract_ready"] = True
    payload["real_runner_wired"] = True
    payload["layer_runner_called"] = True
    payload["layer_runner_step_id"] = step_id
    payload["layer_runner_name"] = payload.get("layer_runner_name") or f"{step_id}_real_runner"
    payload["target_absence_checked"] = bool(report.get("target_absence_checked"))
    payload["received_target_run_id"] = payload.get("received_target_run_id") or args.target_run_id
    payload["real_io_dependencies_injected"] = _present_dependency_names(dependencies)
    _apply_real_runner_safety_fields(payload)
    return payload


def _present_dependency_names(dependencies: N3RealIODependencies) -> list[str]:
    return [
        name
        for name in (
            "market_fetch_adapter",
            "db_connection",
            "db_writer",
            "artifact_writer",
            "artifact_reader",
            "source_payload_registrar",
            "target_absence_checker",
            "rollback_sql_writer",
        )
        if getattr(dependencies, name) is not None
    ]


def _production_n3p_current_source_fetch(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    return _call_production_dependency(
        step_id="n3p_current_source_fetch",
        args=args,
        report=report,
        dependencies=dependencies,
        preferred_dependency_names=("market_fetch_adapter",),
        method_names=("fetch_n3p_current_source", "n3p_current_source_fetch"),
    )


def _production_n3p_trigger_proof_preflight(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    return _call_production_dependency(
        step_id="n3p_trigger_proof_preflight",
        args=args,
        report=report,
        dependencies=dependencies,
        preferred_dependency_names=("artifact_reader", "db_connection"),
        method_names=("preflight_n3p_trigger_proof", "n3p_trigger_proof_preflight"),
    )


def _production_n3_hint_source_fetch(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    hint_blocker = _require_midday_bridge_hint_kind(args)
    if hint_blocker:
        return hint_blocker
    return _call_production_dependency(
        step_id="n3_hint_source_fetch",
        args=args,
        report=report,
        dependencies=dependencies,
        preferred_dependency_names=("market_fetch_adapter",),
        method_names=("fetch_n3_hint_source", "n3_hint_source_fetch"),
    )


def _production_n3_hint_proof_preflight(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    hint_blocker = _require_midday_bridge_hint_kind(args)
    if hint_blocker:
        return hint_blocker
    return _call_production_dependency(
        step_id="n3_hint_proof_preflight",
        args=args,
        report=report,
        dependencies=dependencies,
        preferred_dependency_names=("artifact_reader", "db_connection"),
        method_names=("preflight_n3_hint_proof", "n3_hint_proof_preflight"),
    )


def _production_n3_hint_proof_execute(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> Mapping[str, Any]:
    hint_blocker = _require_midday_bridge_hint_kind(args)
    if hint_blocker:
        return hint_blocker
    return _call_production_dependency(
        step_id="n3_hint_proof_execute",
        args=args,
        report=report,
        dependencies=dependencies,
        preferred_dependency_names=("db_writer",),
        method_names=("execute_n3_hint_proof", "n3_hint_proof_execute"),
    )


def _require_midday_bridge_hint_kind(args: argparse.Namespace) -> Mapping[str, Any] | None:
    if str(getattr(args, "hint_proof_kind", "") or "") == MIDDAY_BRIDGE_HINT_PROOF_KIND:
        return None
    return {
        "result": "BLOCKED_HINT_PROOF_KIND",
        "reason": f"required HINT proof kind is {MIDDAY_BRIDGE_HINT_PROOF_KIND}",
        "real_io_operation_wired": True,
        "execute_contract_ready": False,
    }


def _call_production_dependency(
    *,
    step_id: str,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
    preferred_dependency_names: tuple[str, ...],
    method_names: tuple[str, ...],
) -> Mapping[str, Any]:
    target = _resolve_production_dependency(
        dependencies=dependencies,
        preferred_dependency_names=preferred_dependency_names,
        method_names=method_names,
    )
    if target is None:
        return _missing_real_io_dependency_payload(
            step_id=step_id,
            preferred_dependency_names=preferred_dependency_names,
            method_names=method_names,
        )
    return target(args=args, report=report, dependencies=dependencies) or {}


def _call_required_production_hook(
    *,
    step_id: str,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
    preferred_dependency_names: tuple[str, ...],
    method_names: tuple[str, ...],
    required_entrypoint: str,
) -> Mapping[str, Any]:
    payload = _call_optional_production_hook(
        args=args,
        report=report,
        dependencies=dependencies,
        preferred_dependency_names=preferred_dependency_names,
        method_names=method_names,
    )
    if payload is not None:
        return payload
    return _missing_n3_production_entrypoint_payload(
        step_id=step_id,
        required_entrypoint=required_entrypoint,
    )


def _call_optional_production_hook(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
    preferred_dependency_names: tuple[str, ...],
    method_names: tuple[str, ...],
) -> Mapping[str, Any] | None:
    target = _resolve_production_dependency(
        dependencies=dependencies,
        preferred_dependency_names=preferred_dependency_names,
        method_names=method_names,
    )
    if target is None:
        return None
    return target(args=args, report=report, dependencies=dependencies) or {}


def _resolve_production_dependency(
    *,
    dependencies: N3RealIODependencies,
    preferred_dependency_names: tuple[str, ...],
    method_names: tuple[str, ...],
) -> RunnerOperation | None:
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
        dependency = getattr(dependencies, dependency_name)
        if dependency is None:
            continue
        for method_name in method_names:
            method = getattr(dependency, method_name, None)
            if callable(method):
                return method
        if callable(dependency):
            return dependency
    return None


def _read_json_file(path: str) -> Mapping[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _missing_real_io_dependency_payload(
    *,
    step_id: str,
    preferred_dependency_names: tuple[str, ...],
    method_names: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "result": MISSING_N3_REAL_IO_RESULT,
        "reason": (
            f"{MISSING_N3_REAL_IO_RESULT}:{step_id}:"
            f"missing_dependency={','.join(preferred_dependency_names)}:"
            f"method={','.join(method_names)}"
        ),
        "real_io_operation_wired": True,
        "execute_contract_ready": False,
        "missing_real_io_dependency": list(preferred_dependency_names),
        "missing_real_io_method": list(method_names),
        "market_data_pulled": False,
        "database_written": False,
    }


def _blocked_n3_hint_source_fetch_backend(
    reason_detail: str,
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    dependencies: N3RealIODependencies,
) -> dict[str, Any]:
    del dependencies
    payload = {
        "result": N3_HINT_SOURCE_FETCH_BACKEND_BLOCKER,
        "reason": f"{N3_HINT_SOURCE_FETCH_BACKEND_BLOCKER}:{reason_detail}",
        "step_id": report.get("step_id") or "n3_hint_source_fetch",
        "received_target_run_id": getattr(args, "target_run_id", ""),
        "hint_proof_kind": getattr(args, "hint_proof_kind", ""),
        "asset_scope": "index_board_only",
        "stock_rows": 0,
        "market_data_pulled": False,
        "database_written": False,
        "artifact_written": False,
        "source_payload_registered": False,
        "execute_contract_ready": False,
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
    }
    _apply_real_runner_safety_fields(payload)
    return payload


def _production_entrypoint_exception_payload(step_id: str, exc: Exception) -> dict[str, Any]:
    return {
        "result": f"BLOCKED_N3_PRODUCTION_ENTRYPOINT_EXCEPTION:{step_id}",
        "reason": f"{type(exc).__name__}: {exc}",
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
        "execute_contract_ready": False,
        "market_data_pulled": False,
        "database_written": False,
    }


def _missing_n3_production_entrypoint_payload(
    *,
    step_id: str,
    required_entrypoint: str,
) -> dict[str, Any]:
    return {
        "result": MISSING_N3_PRODUCTION_ENTRYPOINT_RESULT,
        "reason": (
            f"{MISSING_N3_PRODUCTION_ENTRYPOINT_RESULT}:{step_id}:"
            f"required_entrypoint={required_entrypoint}"
        ),
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
        "execute_contract_ready": False,
        "required_production_entrypoint": required_entrypoint,
        "market_data_pulled": False,
        "database_written": False,
    }


def _apply_real_runner_safety_fields(payload: dict[str, Any]) -> None:
    payload["writes_outbox"] = False
    payload["consumes_outbox"] = False
    payload["updates_inbox_or_checkpoint"] = False
    payload["starts_worker"] = False
    payload["touches_n4_n5_n6"] = False
    payload["touches_n5_n6"] = False
    payload["side_effects"] = {
        "database_written": False,
        "market_data_pulled": False,
        "runtime_executed": False,
        "outbox_consumed": False,
        "inbox_or_checkpoint_updated": False,
        "worker_started": False,
        "rollback_executed": False,
        "schema_changed": False,
        "n4_n5_n6_touched": False,
        "n5_n6_touched": False,
    }


DEFAULT_N3_REAL_RUNNER_OPERATIONS = build_default_n3_real_runner_operations()
DEFAULT_N3_PRODUCTION_REAL_IO_ADAPTER = N3ProductionRealIOAdapter()
DEFAULT_N3_REAL_IO_DEPENDENCIES = N3RealIODependencies(
    market_fetch_adapter=DEFAULT_N3_PRODUCTION_REAL_IO_ADAPTER,
    db_connection=DEFAULT_N3_PRODUCTION_REAL_IO_ADAPTER,
    db_writer=DEFAULT_N3_PRODUCTION_REAL_IO_ADAPTER,
    artifact_writer=DEFAULT_N3_PRODUCTION_REAL_IO_ADAPTER,
    artifact_reader=DEFAULT_N3_PRODUCTION_REAL_IO_ADAPTER,
    source_payload_registrar=DEFAULT_N3_PRODUCTION_REAL_IO_ADAPTER,
    rollback_sql_writer=DEFAULT_N3_PRODUCTION_REAL_IO_ADAPTER,
)
