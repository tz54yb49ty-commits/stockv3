"""N3 HINT index/board frequency=8 source provider seam.

The combined N3 child runner uses this provider for HINT source fetch. It is
dependency-injected so tests and patch gates can prove the contract without
pulling market data or writing DB.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
from typing import Any, Callable

from scripts.n3_n4_combined_child_contract import MIDDAY_BRIDGE_HINT_PROOF_KIND


N3_READY_RESULT = "EXECUTE_READY_REAL_IO_CONTRACT"
HINT_SOURCE_SCOPE_BLOCKER = "BLOCKED_N3_HINT_SOURCE_SCOPE_NOT_READY"
HINT_SOURCE_FETCHER_BLOCKER = "BLOCKED_N3_HINT_SOURCE_MARKET_FETCHER"
HINT_SOURCE_ARTIFACT_BLOCKER = "BLOCKED_N3_HINT_SOURCE_ARTIFACT_WRITER"
HINT_SOURCE_PAYLOAD_BLOCKER = "BLOCKED_N3_HINT_SOURCE_PAYLOAD_INVALID"
HINT_SOURCE_PROOF_KIND_BLOCKER = "BLOCKED_HINT_PROOF_KIND"
HINT_PROOF_PREFLIGHT_BLOCKER = "BLOCKED_N3_HINT_PROOF_PREFLIGHT"
HINT_PROOF_PREFLIGHT_ARTIFACT_MATERIALIZATION_BLOCKER = "BLOCKED_N3_HINT_PREFLIGHT_ARTIFACT_MATERIALIZATION"
HINT_PROOF_PREFLIGHT_ARTIFACT_CONTRACT_BLOCKER = "BLOCKED_HINT_CONTRACT_CONTENT_MISMATCH"
HINT_PROOF_EXECUTE_BLOCKER = "BLOCKED_N3_HINT_PROOF_EXECUTE"

HINT_SOURCE_MODE = "index_board_frequency8_1m"
HINT_SOURCE_SCOPE_POLICY = "n4_context_hint_index_board_frequency8_v1"
HINT_SOURCE_HASH_POLICY = "payload_hash_canonical_file_sha256_trace"
N3_OUTBOX_EVENT_TYPES = (
    "MarketSnapshotUpdated",
    "MinuteBarClosed",
    "MinuteBarCorrected",
    "MarketDataDelayed",
    "MarketDataMissing",
    "MarketDisplaySnapshotUpdated",
)
_DEFAULT_HINT_ARTIFACT_WRITER = object()

_FORBIDDEN_SIDE_EFFECTS = {
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


class N3HintFrequency8SourceProvider:
    def __init__(self, *, backend: Any | None = None) -> None:
        self.backend = backend if backend is not None else N3HintFrequency8SourceBackend()

    def fetch_n3_hint_frequency8_source(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        if str(getattr(args, "hint_proof_kind", "") or "") != MIDDAY_BRIDGE_HINT_PROOF_KIND:
            return _blocked(
                HINT_SOURCE_PROOF_KIND_BLOCKER,
                f"required HINT proof kind is {MIDDAY_BRIDGE_HINT_PROOF_KIND}",
            )
        scope_loader = getattr(self.backend, "load_n3_hint_frequency8_scope", None)
        market_fetcher = getattr(self.backend, "fetch_n3_hint_frequency8_market_rows", None)
        artifact_writer = getattr(self.backend, "write_n3_hint_frequency8_artifacts", None)
        if not callable(scope_loader):
            return _blocked(HINT_SOURCE_SCOPE_BLOCKER, "scope loader dependency is required for HINT source fetch")
        if not callable(market_fetcher):
            return _blocked(HINT_SOURCE_FETCHER_BLOCKER, "market fetch dependency is required for HINT source fetch")
        if not callable(artifact_writer):
            return _blocked(HINT_SOURCE_ARTIFACT_BLOCKER, "artifact writer dependency is required for HINT source fetch")

        scope = dict(scope_loader(args=args, report=report, dependencies=dependencies) or {})
        if _is_blocked(scope):
            return scope
        scope_blocker = validate_n3_hint_frequency8_scope(scope)
        if scope_blocker is not None:
            return scope_blocker

        fetched = dict(market_fetcher(args=args, report=report, dependencies=dependencies, scope=scope) or {})
        if _is_blocked(fetched):
            return fetched
        payload = _build_source_payload(args=args, scope=scope, fetched=fetched)
        validation = validate_n3_hint_frequency8_payload(payload)
        if not validation["valid"]:
            return _blocked(
                HINT_SOURCE_PAYLOAD_BLOCKER,
                ",".join(validation["blocked_reasons"]),
                blocked_reasons=validation["blocked_reasons"],
                normalization_trace=payload.get("normalization_trace") or {},
                artifact_written=False,
            )

        artifact = dict(
            artifact_writer(
                args=args,
                report=report,
                dependencies=dependencies,
                payload=payload,
                fetch_report=_fetch_report_from_payload(scope=scope, payload=payload),
            )
            or {}
        )
        if _is_blocked(artifact):
            return artifact
        expected_hash = compute_n3_hint_frequency8_source_payload_hash(payload)
        observed_hash = str(artifact.get("payload_hash") or "")
        if observed_hash and observed_hash != expected_hash:
            return _blocked(
                HINT_SOURCE_PAYLOAD_BLOCKER,
                "payload_hash_mismatch",
                blocked_reasons=["payload_hash_mismatch"],
                expected_payload_hash=expected_hash,
                observed_payload_hash=observed_hash,
                artifact_written=False,
            )

        result = dict(payload)
        result.update(
            {
                "result": N3_READY_RESULT,
                "payload_hash": observed_hash or expected_hash,
                "source_payload_hash": observed_hash or expected_hash,
                "source_artifact_path": str(artifact.get("payload_path") or artifact.get("source_artifact_path") or ""),
                "source_report_path": str(artifact.get("report_path") or artifact.get("source_report_path") or ""),
                "file_sha256": str(artifact.get("file_sha256") or ""),
                "source_artifact_file_sha256": str(artifact.get("file_sha256") or artifact.get("source_artifact_file_sha256") or ""),
                "artifact_written": bool(artifact.get("artifact_written", True)),
                "market_data_pulled": True,
                "database_written": False,
                "execute_contract_ready": True,
            }
        )
        _apply_forbidden_side_effect_guards(result)
        return result


class N3HintProofPreflightProvider:
    def __init__(self, *, backend: Any | None = None) -> None:
        self.backend = backend if backend is not None else N3HintProofPreflightBackend()

    def build_n3_hint_proof_preflight(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        builder = getattr(self.backend, "build_n3_hint_proof_preflight", None)
        if not callable(builder):
            return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, "proof preflight backend dependency is required")
        payload = dict(builder(args=args, report=report, dependencies=dependencies) or {})
        if _is_blocked(payload):
            payload.setdefault("database_written", False)
            payload.setdefault("market_data_pulled", False)
        else:
            payload.setdefault("result", N3_READY_RESULT)
            payload.setdefault("proof_kind", MIDDAY_BRIDGE_HINT_PROOF_KIND)
            payload.setdefault("database_written", False)
            payload.setdefault("market_data_pulled", False)
            payload.setdefault("writes_outbox", False)
            payload.setdefault("stock_rows", 0)
            materialization = _materialize_n3_hint_proof_preflight_artifacts(args=args, payload=payload)
            if _is_blocked(materialization):
                payload = dict(materialization)
            else:
                payload.update(materialization)
                payload.pop("writer_contract", None)
                payload.pop("writer_preflight", None)
        _apply_forbidden_side_effect_guards(payload)
        return payload


def _materialize_n3_hint_proof_preflight_artifacts(*, args: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Write HINT proof contract/preflight artifacts for wrapper plan-only handoff."""

    has_contract = "writer_contract" in payload
    has_preflight = "writer_preflight" in payload
    if not has_contract and not has_preflight:
        return {}
    contract = payload.get("writer_contract")
    preflight = payload.get("writer_preflight")
    if not isinstance(contract, Mapping) or not isinstance(preflight, Mapping):
        return _blocked(
            HINT_PROOF_PREFLIGHT_ARTIFACT_CONTRACT_BLOCKER,
            "writer_contract_and_writer_preflight_required",
            target_run_id=payload.get("target_run_id"),
            source_artifact_path=payload.get("source_artifact_path"),
        )
    return _write_hint_proof_preflight_artifacts(
        contract_path=str(getattr(args, "contract_path", "") or ""),
        preflight_path=str(getattr(args, "preflight_path", "") or ""),
        contract=contract,
        preflight=preflight,
        target_run_id=str(payload.get("target_run_id") or ""),
        source_artifact_path=str(payload.get("source_artifact_path") or getattr(args, "source_artifact_path", "") or ""),
        proof_kind=str(payload.get("proof_kind") or MIDDAY_BRIDGE_HINT_PROOF_KIND),
        require_paths=True,
    )


def _write_hint_proof_preflight_artifacts(
    *,
    contract_path: str,
    preflight_path: str,
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    target_run_id: str,
    source_artifact_path: str,
    proof_kind: str,
    require_paths: bool,
) -> dict[str, Any]:
    missing_paths = [
        name
        for name, value in (("contract_path", contract_path), ("preflight_path", preflight_path))
        if not value
    ]
    if missing_paths:
        if not require_paths and len(missing_paths) == 2:
            return {}
        return _blocked(
            HINT_PROOF_PREFLIGHT_ARTIFACT_MATERIALIZATION_BLOCKER,
            f"missing_artifact_path:{','.join(missing_paths)}",
            target_run_id=target_run_id,
            source_artifact_path=source_artifact_path,
        )

    contract_doc = dict(contract)
    preflight_doc = dict(preflight)
    for document in (contract_doc, preflight_doc):
        document.setdefault("target_run_id", target_run_id)
        document.setdefault("source_artifact_path", source_artifact_path)
        document.setdefault("proof_kind", proof_kind)
        document.setdefault("writes_outbox", False)
        document.setdefault("database_written", False)
        document.setdefault("market_data_pulled", False)
        document.setdefault("stock_rows", 0)
    try:
        _write_json_if_requested(contract_path, contract_doc)
        _write_json_if_requested(preflight_path, preflight_doc)
    except Exception as exc:
        return _blocked(
            HINT_PROOF_PREFLIGHT_ARTIFACT_MATERIALIZATION_BLOCKER,
            f"artifact_write_failed:{type(exc).__name__}:{exc}",
            target_run_id=target_run_id,
            source_artifact_path=source_artifact_path,
        )

    return {
        "preflight_artifacts_materialized": True,
        "contract_path": contract_path,
        "preflight_path": preflight_path,
        "contract_artifact_path": contract_path,
        "preflight_artifact_path": preflight_path,
        "artifact_written": True,
        "database_written": False,
        "market_data_pulled": False,
        "writes_outbox": False,
    }


class N3HintProofExecuteProvider:
    def __init__(self, *, backend: Any | None = None) -> None:
        self.backend = backend if backend is not None else N3HintProofExecuteBackend()

    def execute_n3_hint_projection_write_plan(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        executor = getattr(self.backend, "execute_n3_hint_projection_write_plan", None)
        if not callable(executor):
            return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "proof execute backend dependency is required")
        return executor(args=args, report=report, dependencies=dependencies)


class N3HintProofExecuteBackend:
    """Execute an already-materialized N3 HINT proof write plan.

    This backend does not fetch market data or rebuild proof rows. It validates
    exact contract/preflight artifacts, writes scoped rollback SQL, then persists
    only the index/board HINT proof target rows described by the write plan.
    """

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        config: Mapping[str, Any] | None = None,
        target_snapshot_loader: Any = None,
        rollback_sql_path: str | None = None,
    ) -> None:
        self.env = os.environ if env is None else env
        self.config = dict(config or {})
        self.target_snapshot_loader = target_snapshot_loader
        self.rollback_sql_path = rollback_sql_path

    def execute_n3_hint_projection_write_plan(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        del report
        if str(getattr(args, "hint_proof_kind", "") or "") != MIDDAY_BRIDGE_HINT_PROOF_KIND:
            return _blocked(
                HINT_SOURCE_PROOF_KIND_BLOCKER,
                f"required HINT proof kind is {MIDDAY_BRIDGE_HINT_PROOF_KIND}",
            )
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        try:
            contract_path = str(getattr(args, "contract_path", "") or "")
            preflight_path = str(getattr(args, "preflight_path", "") or "")
            if not contract_path or not preflight_path:
                return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "missing_contract_or_preflight_path")
            contract = _read_json_path(contract_path)
            preflight = _read_json_path(preflight_path)
            target_run_id = str(getattr(args, "target_run_id", "") or "")
            if not target_run_id:
                return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "missing_target_run_id")

            from ashare_v3.market.hint_1m_projection_persistence import (
                HintProjectionPersistenceError,
                build_hint_projection_rollback_sql,
                ensure_clean_hint_projection_target,
                parse_hint_projection_run_id,
            )

            parsed_target = parse_hint_projection_run_id(target_run_id)
            if parsed_target["proof_kind"] != MIDDAY_BRIDGE_HINT_PROOF_KIND:
                return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "unsupported_hint_proof_kind")
            blocker = _validate_hint_execute_artifacts(
                args=args,
                target_run_id=target_run_id,
                parsed_target=parsed_target,
                contract=contract,
                preflight=preflight,
            )
            if blocker is not None:
                return blocker

            write_plan = dict(contract.get("write_plan") or {})
            blocker = _validate_hint_execute_write_plan(write_plan=write_plan, preflight=preflight, target_run_id=target_run_id)
            if blocker is not None:
                return blocker

            target_snapshot = self._load_target_snapshot(
                args=args,
                dependencies=dependencies,
                config=config,
                target_run_id=target_run_id,
            )
            if _is_blocked(target_snapshot):
                return target_snapshot
            try:
                ensure_clean_hint_projection_target(target_snapshot, target_run_id)
            except HintProjectionPersistenceError as exc:
                return _blocked(HINT_PROOF_EXECUTE_BLOCKER, str(exc), target_absence_snapshot=dict(target_snapshot))

            rollback_sql = str(contract.get("rollback_sql") or build_hint_projection_rollback_sql(target_run_id))
            rollback_sql_path = self.rollback_sql_path or str(
                getattr(args, "rollback_sql_path", "") or _default_hint_execute_rollback_path(parsed_target)
            )
            Path(rollback_sql_path).parent.mkdir(parents=True, exist_ok=True)
            Path(rollback_sql_path).write_text(rollback_sql, encoding="utf-8")

            write_result = _persist_hint_projection_write_plan_to_db(
                config=config,
                target_run_id=target_run_id,
                write_plan=write_plan,
            )
            result = {
                "result": N3_READY_RESULT,
                "target_run_id": target_run_id,
                "actual_until_hhmm": preflight.get("actual_until_hhmm") or contract.get("actual_until_hhmm"),
                "proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
                "rows_written": dict(write_result.get("rows_written") or {}),
                "total_rows_written": int(write_result.get("total_rows_written") or 0),
                "quality_rows_written": int(write_result.get("quality_rows_written") or 0),
                "market_data_run_rows_written": int(write_result.get("market_data_run_rows_written") or 0),
                "metric_ready": dict(write_plan.get("metric_ready") or {}),
                "rows_by_asset": dict(write_plan.get("rows_by_asset") or {}),
                "projection_type_distribution": dict(write_plan.get("projection_type_distribution") or {}),
                "stock_rows": 0,
                "allowed_write_tables": list(write_plan.get("allowed_write_tables") or []),
                "rollback_sql_path": rollback_sql_path,
                "rollback_ready": True,
                "target_absence_snapshot": dict(target_snapshot),
                "source_artifact_payload_hash": contract.get("source_artifact_payload_hash") or preflight.get("source_artifact_payload_hash"),
                "source_artifact_file_sha256": contract.get("source_artifact_file_sha256") or preflight.get("source_artifact_file_sha256"),
                "database_written": True,
                "market_data_pulled": False,
                "artifact_written": True,
                "execute_contract_ready": True,
                "writes_outbox": False,
            }
            _apply_forbidden_side_effect_guards(result)
            _write_json_if_requested(str(getattr(args, "json_report_path", "") or ""), result)
            return result
        except Exception as exc:  # pragma: no cover - defensive production guard.
            return _blocked(HINT_PROOF_EXECUTE_BLOCKER, f"{type(exc).__name__}:{exc}")

    def _resolve_config(self) -> Mapping[str, Any]:
        if self.config:
            return self.config
        return N3HintFrequency8SourceBackend(env=self.env)._resolve_config()

    def _load_target_snapshot(
        self,
        *,
        args: Any,
        dependencies: Any,
        config: Mapping[str, Any],
        target_run_id: str,
    ) -> Mapping[str, Any]:
        loader = _component_callable(self.target_snapshot_loader, "load_n3_hint_target_snapshot") or _dependency_method(
            dependencies,
            "target_absence_checker",
            "load_n3_hint_target_snapshot",
        )
        if loader is not None:
            return _call_with_supported_kwargs(
                loader,
                args=args,
                dependencies=dependencies,
                config=config,
                target_run_id=target_run_id,
            )
        return load_n3_hint_target_snapshot_from_db(args=args, dependencies=dependencies, config=config, target_run_id=target_run_id)


class N3HintProofPreflightBackend:
    """Read-only/materialization backend for N3 HINT proof preflight.

    The backend reads an already-written HINT frequency=8 source artifact and
    materializes local contract/preflight artifacts. It does not fetch market
    data, write DB rows, or touch downstream layers.
    """

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        config: Mapping[str, Any] | None = None,
        scope_loader: Any = None,
        previous_day_rows_loader: Any = None,
        target_snapshot_loader: Any = None,
    ) -> None:
        self.env = os.environ if env is None else env
        self.config = dict(config or {})
        self.scope_loader = scope_loader
        self.previous_day_rows_loader = previous_day_rows_loader
        self.target_snapshot_loader = target_snapshot_loader

    def build_n3_hint_proof_preflight(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        del report
        if str(getattr(args, "hint_proof_kind", "") or "") != MIDDAY_BRIDGE_HINT_PROOF_KIND:
            return _blocked(
                HINT_SOURCE_PROOF_KIND_BLOCKER,
                f"required HINT proof kind is {MIDDAY_BRIDGE_HINT_PROOF_KIND}",
            )
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        try:
            payload_path = str(getattr(args, "source_artifact_path", "") or getattr(args, "source_payload_path", "") or "")
            if not payload_path:
                return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, "missing_source_artifact_path")
            source_payload = _read_json_path(payload_path)
            payload_hash = compute_n3_hint_frequency8_source_payload_hash(source_payload)
            embedded_hash = str(source_payload.get("payload_hash") or source_payload.get("source_payload_hash") or "")
            if embedded_hash and embedded_hash != payload_hash:
                return _blocked(
                    HINT_PROOF_PREFLIGHT_BLOCKER,
                    "source_payload_hash_mismatch",
                    expected_payload_hash=embedded_hash,
                    observed_payload_hash=payload_hash,
                )
            source_file_sha256 = hashlib.sha256(Path(payload_path).read_bytes()).hexdigest()
            source_blocker = _validate_hint_proof_source_payload(source_payload)
            if source_blocker is not None:
                return source_blocker

            actual_until_hhmm = str(source_payload.get("actual_until_hhmm") or _hhmm_from_time(str(source_payload.get("proof_input_time") or "")))
            subscription_run_id = str(getattr(args, "subscription_run_id", "") or source_payload.get("subscription_run_id") or "")
            if not actual_until_hhmm or not subscription_run_id:
                return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, "missing_actual_until_hhmm_or_subscription_run_id")

            from ashare_v3.market.hint_1m_projection_persistence import (
                HintProjectionPersistenceError,
                build_hint_projection_rollback_sql,
                build_hint_projection_run_id,
                build_hint_projection_write_plan,
                ensure_clean_hint_projection_target,
                parse_hint_projection_run_id,
            )

            target_run_id = build_hint_projection_run_id(
                trade_date=str(getattr(args, "for_trade_date", "") or source_payload.get("for_trade_date") or ""),
                until_hhmm=actual_until_hhmm,
                source_subscription_run_id=subscription_run_id,
                proof_kind=MIDDAY_BRIDGE_HINT_PROOF_KIND,
            )
            parsed_target = parse_hint_projection_run_id(target_run_id)
            received_target_run_id = str(getattr(args, "target_run_id", "") or source_payload.get("target_run_id") or "")
            source_payload_target_run_id = str(source_payload.get("target_run_id") or "")
            target_snapshot = self._load_target_snapshot(
                args=args,
                dependencies=dependencies,
                config=config,
                target_run_id=target_run_id,
            )
            if _is_blocked(target_snapshot):
                return target_snapshot
            try:
                ensure_clean_hint_projection_target(target_snapshot, target_run_id)
            except HintProjectionPersistenceError as exc:
                return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, str(exc), target_absence_snapshot=dict(target_snapshot))

            scope = self._load_scope(args=args, dependencies=dependencies, config=config)
            if _is_blocked(scope):
                return scope
            scope_blocker = validate_n3_hint_frequency8_scope(scope)
            if scope_blocker is not None:
                return scope_blocker

            previous_reference = self._load_previous_day_rows(
                args=args,
                dependencies=dependencies,
                config=config,
                scope=scope,
                target_run_id=target_run_id,
            )
            if _is_blocked(previous_reference):
                return previous_reference
            previous_rows = _rows(previous_reference, "previous_day_1m_rows")
            proof_rows = _build_hint_proof_rows_from_payload(
                source_payload=source_payload,
                scope=scope,
                previous_day_1m_rows=previous_rows,
                projection_run_id=target_run_id,
                previous_trade_date=parsed_target["source_trade_date"],
            )
            if not proof_rows:
                return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, "proof_rows_empty")

            source_condition_run_id = str(getattr(args, "source_condition_run_id", "") or "")
            if not source_condition_run_id:
                source_condition_run_id = (
                    f"condition_layer_{parsed_target['source_trade_date']}_source_{parsed_target['source_trade_date']}"
                    f"_for_{parsed_target['trade_date']}_v1"
                )
            source_previous_day_minute_run_id = str(
                previous_reference.get("source_previous_day_minute_run_id")
                or _derive_previous_day_minute_run_id(parsed_target=parsed_target)
            )
            write_plan = build_hint_projection_write_plan(
                projection_run_id=target_run_id,
                proof_rows=proof_rows,
                source_condition_run_id=source_condition_run_id,
                source_subscription_run_id=subscription_run_id,
                source_artifact_path=payload_path,
                source_artifact_sha256=payload_hash,
                source_artifact_payload_hash=payload_hash,
                source_artifact_file_sha256=source_file_sha256,
                source_previous_day_minute_run_id=source_previous_day_minute_run_id,
                source_context_run_id=str(getattr(args, "n4_context_run_id", "") or source_payload.get("n4_context_run_id") or ""),
            )
            rollback_sql = build_hint_projection_rollback_sql(target_run_id)
            metric_fact_rows_total = sum(int(value or 0) for value in (write_plan.get("rows_by_asset") or {}).values())
            projection_distribution = dict(write_plan.get("projection_type_distribution") or {})
            retargeted_from_stale_input = bool(
                (received_target_run_id and received_target_run_id != target_run_id)
                or (source_payload_target_run_id and source_payload_target_run_id != target_run_id)
            )
            contract = {
                "result": N3_READY_RESULT,
                "target_run_id": target_run_id,
                "received_target_run_id": received_target_run_id,
                "source_payload_target_run_id": source_payload_target_run_id,
                "retargeted_from_stale_input": retargeted_from_stale_input,
                "for_trade_date": parsed_target["trade_date"],
                "source_trade_date": parsed_target["source_trade_date"],
                "actual_until_hhmm": actual_until_hhmm,
                "proof_input_time": source_payload.get("proof_input_time"),
                "proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
                "source_artifact_path": payload_path,
                "source_artifact_payload_hash": payload_hash,
                "source_artifact_file_sha256": source_file_sha256,
                "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
                "source_context_run_id": str(getattr(args, "n4_context_run_id", "") or source_payload.get("n4_context_run_id") or ""),
                "source_condition_run_id": source_condition_run_id,
                "proof_rows": proof_rows,
                "write_plan": write_plan,
                "rollback_sql": rollback_sql,
                "writes_outbox": False,
                "database_written": False,
                "market_data_pulled": False,
            }
            preflight = {
                "result": N3_READY_RESULT,
                "target_run_id": target_run_id,
                "received_target_run_id": received_target_run_id,
                "source_payload_target_run_id": source_payload_target_run_id,
                "retargeted_from_stale_input": retargeted_from_stale_input,
                "actual_until_hhmm": actual_until_hhmm,
                "source_artifact_payload_hash": payload_hash,
                "source_artifact_file_sha256": source_file_sha256,
                "target_absence_snapshot": dict(target_snapshot),
                "proof_rows_input_total": len(proof_rows),
                "proof_rows_total": metric_fact_rows_total,
                "metric_fact_exclusion_count": int(write_plan.get("metric_fact_exclusion_count") or 0),
                "metric_fact_exclusion_reason_counts": dict(write_plan.get("metric_fact_exclusion_reason_counts") or {}),
                "rows_by_asset": dict(write_plan.get("rows_by_asset") or {}),
                "metric_ready": dict(write_plan.get("metric_ready") or {}),
                "projection_type_distribution": projection_distribution,
                "stock_rows": 0,
                "rollback_ready": True,
                "execute_contract_ready": True,
                "writes_outbox": False,
                "database_written": False,
                "market_data_pulled": False,
            }
            materialization = _write_hint_proof_preflight_artifacts(
                contract_path=str(getattr(args, "contract_path", "") or ""),
                preflight_path=str(getattr(args, "preflight_path", "") or ""),
                contract=contract,
                preflight=preflight,
                target_run_id=target_run_id,
                source_artifact_path=payload_path,
                proof_kind=MIDDAY_BRIDGE_HINT_PROOF_KIND,
                require_paths=False,
            )
            if _is_blocked(materialization):
                return materialization

            result = {
                **preflight,
                **materialization,
                "proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
                "source_artifact_path": payload_path,
                "contract_path": str(materialization.get("contract_path") or getattr(args, "contract_path", "") or ""),
                "preflight_path": str(materialization.get("preflight_path") or getattr(args, "preflight_path", "") or ""),
                "allowed_write_tables": list(write_plan.get("allowed_write_tables") or []),
                "common_event_outbox": 0,
                "artifact_written": bool(materialization.get("artifact_written")),
            }
            _apply_forbidden_side_effect_guards(result)
            return result
        except Exception as exc:  # pragma: no cover - defensive production guard.
            return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, f"{type(exc).__name__}:{exc}")

    def _resolve_config(self) -> Mapping[str, Any]:
        if self.config:
            return self.config
        return N3HintFrequency8SourceBackend(env=self.env)._resolve_config()

    def _load_scope(self, *, args: Any, dependencies: Any, config: Mapping[str, Any]) -> Mapping[str, Any]:
        loader = _component_callable(self.scope_loader, "load_n3_hint_frequency8_scope") or _dependency_method(
            dependencies,
            "db_connection",
            "load_n3_hint_frequency8_scope",
        )
        if loader is not None:
            return _call_with_supported_kwargs(loader, args=args, report={}, dependencies=dependencies, config=config)
        return load_n3_hint_frequency8_scope_from_db(args=args, report={}, dependencies=dependencies, config=config)

    def _load_previous_day_rows(
        self,
        *,
        args: Any,
        dependencies: Any,
        config: Mapping[str, Any],
        scope: Mapping[str, Any],
        target_run_id: str,
    ) -> Mapping[str, Any]:
        loader = _component_callable(self.previous_day_rows_loader, "load_n3_hint_previous_day_reference_rows") or _dependency_method(
            dependencies,
            "db_connection",
            "load_n3_hint_previous_day_reference_rows",
        )
        if loader is not None:
            return _call_with_supported_kwargs(
                loader,
                args=args,
                dependencies=dependencies,
                config=config,
                scope=scope,
                target_run_id=target_run_id,
            )
        return load_n3_hint_previous_day_reference_rows_from_db(
            args=args,
            dependencies=dependencies,
            config=config,
            scope=scope,
            target_run_id=target_run_id,
        )

    def _load_target_snapshot(
        self,
        *,
        args: Any,
        dependencies: Any,
        config: Mapping[str, Any],
        target_run_id: str,
    ) -> Mapping[str, Any]:
        loader = _component_callable(self.target_snapshot_loader, "load_n3_hint_target_snapshot") or _dependency_method(
            dependencies,
            "target_absence_checker",
            "load_n3_hint_target_snapshot",
        )
        if loader is not None:
            return _call_with_supported_kwargs(
                loader,
                args=args,
                dependencies=dependencies,
                config=config,
                target_run_id=target_run_id,
            )
        return load_n3_hint_target_snapshot_from_db(args=args, dependencies=dependencies, config=config, target_run_id=target_run_id)


class N3HintFrequency8SourceBackend:
    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        config: Mapping[str, Any] | None = None,
        scope_loader: Any = None,
        market_fetcher: Any = None,
        artifact_writer: Any = _DEFAULT_HINT_ARTIFACT_WRITER,
    ) -> None:
        self.env = os.environ if env is None else env
        self.config = dict(config or {})
        self.scope_loader = scope_loader
        self.market_fetcher = market_fetcher
        self.artifact_writer = (
            N3HintFrequency8SourceArtifactWriter()
            if artifact_writer is _DEFAULT_HINT_ARTIFACT_WRITER
            else artifact_writer
        )

    def load_n3_hint_frequency8_scope(self, *, args: Any, report: Mapping[str, Any], dependencies: Any) -> Mapping[str, Any]:
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        loader = _component_callable(self.scope_loader, "load_n3_hint_frequency8_scope") or _dependency_method(
            dependencies,
            "db_connection",
            "load_n3_hint_frequency8_scope",
        )
        if loader is None:
            return load_n3_hint_frequency8_scope_from_db(
                args=args,
                report=report,
                dependencies=dependencies,
                config=config,
            )
        return _call_with_supported_kwargs(
            loader,
            args=args,
            report=report,
            dependencies=dependencies,
            config=config,
        )

    def fetch_n3_hint_frequency8_market_rows(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        scope: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        fetcher = _component_callable(self.market_fetcher, "fetch_n3_hint_frequency8_market_rows") or _dependency_method(
            dependencies,
            "market_fetch_adapter",
            "fetch_n3_hint_frequency8_market_rows",
        )
        if fetcher is not None:
            return _call_with_supported_kwargs(
                fetcher,
                args=args,
                report=report,
                dependencies=dependencies,
                scope=scope,
                config=config,
            )
        adapter = self.market_fetcher or getattr(dependencies, "market_fetch_adapter", None)
        if adapter is None:
            return _blocked(HINT_SOURCE_FETCHER_BLOCKER, "market fetch dependency is required for HINT source fetch")
        return fetch_n3_hint_frequency8_market_rows_from_adapter(
            args=args,
            scope=scope,
            adapter=adapter,
        )

    def write_n3_hint_frequency8_artifacts(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        payload: Mapping[str, Any],
        fetch_report: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        config = self._resolve_config()
        if _is_blocked(config):
            return config
        writer = _component_callable(self.artifact_writer, "write_n3_hint_frequency8_artifacts") or _dependency_method(
            dependencies,
            "artifact_writer",
            "write_n3_hint_frequency8_artifacts",
        )
        if writer is None:
            return _blocked(HINT_SOURCE_ARTIFACT_BLOCKER, "artifact writer dependency is required for HINT source fetch")
        return _call_with_supported_kwargs(
            writer,
            args=args,
            report=report,
            dependencies=dependencies,
            payload=payload,
            fetch_report=fetch_report,
            config=config,
        )

    def _resolve_config(self) -> Mapping[str, Any]:
        if self.config:
            return self.config
        database_url = (
            self.env.get("ASHARE_V3_POSTGRES_DSN")
            or self.env.get("DATABASE_URL")
            or self.env.get("PG_DSN")
            or self.env.get("POSTGRES_DSN")
        )
        if database_url:
            return {"database_url": database_url}
        if self.env.get("PGHOST") and self.env.get("PGDATABASE"):
            return {
                "pg_host": self.env.get("PGHOST"),
                "pg_database": self.env.get("PGDATABASE"),
                "pg_user": self.env.get("PGUSER"),
                "pg_port": self.env.get("PGPORT"),
            }
        default_dsn = _project_default_dsn()
        if default_dsn:
            return {"database_url": default_dsn}
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, "database config is required for HINT source scope loading")


class N3HintFrequency8MarketFetchAdapter:
    """Lazy low-level market adapter for HINT index/board frequency=8 source.

    Construction must not import or call mootdx. The client is resolved only
    when an authorized execute path invokes a fetch method.
    """

    def __init__(self, *, client_factory: Callable[[], Any] | None = None) -> None:
        self._client_factory = client_factory or _default_mootdx_client
        self._client: Any = None

    def fetch_index_board_1m_rows(
        self,
        *,
        obj: Mapping[str, Any] | None = None,
        symbol: str | None = None,
        frequency: int = 8,
        start: int = 0,
        offset: int = 800,
        market: int | None = None,
        **_kwargs: Any,
    ) -> Any:
        return self.index_bars(
            symbol=str(symbol or (obj or {}).get("code") or ""),
            frequency=frequency,
            start=start,
            offset=offset,
            market=market,
        )

    def fetch_stock_quotes(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("stock quote fetch is forbidden for HINT frequency=8 source")

    def index_bars(
        self,
        *,
        symbol: str,
        frequency: int = 8,
        start: int = 0,
        offset: int = 800,
        market: int | None = None,
        **kwargs: Any,
    ) -> Any:
        if not symbol:
            raise RuntimeError("index/board symbol is required")
        client = self._resolve_client()
        method = getattr(client, "index_bars", None) or getattr(client, "index", None)
        if not callable(method):
            raise RuntimeError("mootdx client does not expose index_bars()/index()")
        return _call_with_supported_kwargs(
            method,
            symbol=symbol,
            frequency=frequency,
            start=start,
            offset=offset,
            market=market,
            **kwargs,
        )

    def _resolve_client(self) -> Any:
        if self._client is None:
            client = self._client_factory()
            if client is None:
                raise RuntimeError("mootdx client factory unavailable")
            self._client = client
        return self._client


class N3HintFrequency8SourceArtifactWriter:
    def __init__(self, *, output_root: str | os.PathLike[str] | None = None) -> None:
        self.output_root = str(output_root) if output_root is not None else "docs/intraday_live_current"

    def write_n3_hint_frequency8_artifacts(
        self,
        *,
        args: Any,
        report: Mapping[str, Any],
        dependencies: Any,
        payload: Mapping[str, Any],
        fetch_report: Mapping[str, Any],
        config: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        del args, report, dependencies
        config = config or {}
        for_trade_date = str(payload.get("for_trade_date") or "")
        actual_until_hhmm = str(payload.get("actual_until_hhmm") or "")
        if not for_trade_date or not actual_until_hhmm:
            return _blocked(HINT_SOURCE_ARTIFACT_BLOCKER, "for_trade_date and actual_until_hhmm are required")
        output_root = str(config.get("artifact_output_root") or self.output_root)
        output_dir = Path(output_root) / for_trade_date
        payload_path = output_dir / f"N3_hint_index_board_1m_{actual_until_hhmm}_midday_bridge_frequency8_payload.json"
        report_path = output_dir / f"N3_hint_index_board_1m_{actual_until_hhmm}_midday_bridge_frequency8_fetch_report.json"

        payload_to_write = dict(payload)
        payload_hash = compute_n3_hint_frequency8_source_payload_hash(payload_to_write)
        payload_to_write["payload_hash"] = payload_hash
        payload_to_write["source_payload_hash"] = payload_hash
        payload_to_write["source_artifact_hash_policy"] = HINT_SOURCE_HASH_POLICY
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            payload_bytes = _canonical_json_bytes(payload_to_write)
            payload_path.write_bytes(payload_bytes)
            file_sha256 = hashlib.sha256(payload_bytes).hexdigest()
            report_to_write = {
                **dict(fetch_report),
                "result": N3_READY_RESULT,
                "payload_hash": payload_hash,
                "payload_path": str(payload_path),
                "report_path": str(report_path),
                "file_sha256": file_sha256,
                "artifact_written": True,
                "database_written": False,
                "writes_outbox": False,
                "consumes_outbox": False,
                "updates_inbox_or_checkpoint": False,
                "starts_worker": False,
                "touches_n4_n5_n6": False,
            }
            report_path.write_bytes(_canonical_json_bytes(report_to_write))
        except OSError as exc:
            return _blocked(HINT_SOURCE_ARTIFACT_BLOCKER, f"artifact_write_failed:{type(exc).__name__}:{exc}")
        return {
            "payload_path": str(payload_path),
            "report_path": str(report_path),
            "payload_hash": payload_hash,
            "source_payload_hash": payload_hash,
            "file_sha256": file_sha256,
            "source_artifact_file_sha256": file_sha256,
            "artifact_written": True,
            "database_written": False,
            "writes_outbox": False,
        }


def fetch_n3_hint_frequency8_market_rows_from_adapter(
    *,
    args: Any,
    scope: Mapping[str, Any],
    adapter: Any,
) -> Mapping[str, Any]:
    if not callable(getattr(adapter, "fetch_index_board_1m_rows", None)):
        return _blocked(HINT_SOURCE_FETCHER_BLOCKER, "market fetch dependency is required for HINT source fetch")
    for_trade_date = str(getattr(args, "for_trade_date", "") or scope.get("for_trade_date") or "")
    rows: list[dict[str, Any]] = []
    fetch_errors: list[str] = []
    for obj in [*_rows(scope, "index_1m_objects"), *_rows(scope, "board_1m_objects")]:
        try:
            raw_records = _records_from_frame(
                _call_with_supported_kwargs(
                    adapter.fetch_index_board_1m_rows,
                    obj=obj,
                    symbol=str(obj.get("code") or ""),
                    frequency=8,
                    start=0,
                    offset=800,
                    market=_market_code_for_object(obj),
                )
            )
        except Exception as exc:
            fetch_errors.append(f"{obj.get('identity_key')}:{type(exc).__name__}:{exc}")
            continue
        for raw in raw_records:
            row = _normalize_index_board_row(raw=raw, obj=obj, for_trade_date=for_trade_date)
            if row is not None:
                rows.append(row)
    if fetch_errors:
        return _blocked(
            HINT_SOURCE_FETCHER_BLOCKER,
            ",".join(fetch_errors),
            fetch_errors=fetch_errors,
            market_data_pulled=True,
        )
    proof_input_time = _derive_proof_input_time(rows)
    return {
        "proof_input_time": proof_input_time,
        "actual_until_hhmm": _hhmm_from_time(proof_input_time),
        "index_board_1m_rows": rows,
        "market_data_pulled": True,
        "database_written": False,
    }


def load_n3_hint_frequency8_scope_from_db(
    *,
    args: Any,
    report: Mapping[str, Any],
    dependencies: Any,
    config: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Load HINT frequency=8 source scope from passed N4 context only."""

    del report, dependencies
    for_trade_date = str(getattr(args, "for_trade_date", "") or "")
    n4_context_run_id = str(getattr(args, "n4_context_run_id", "") or "")
    missing = [
        name
        for name, value in (
            ("for_trade_date", for_trade_date),
            ("n4_context_run_id", n4_context_run_id),
        )
        if not value
    ]
    if missing:
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, f"missing_scope_input:{','.join(missing)}")
    try:
        with _connect_db(config) as conn:
            conn.execute("BEGIN READ ONLY")
            try:
                return _load_n3_hint_frequency8_scope_with_connection(
                    conn=conn,
                    for_trade_date=for_trade_date,
                    n4_context_run_id=n4_context_run_id,
                )
            finally:
                conn.execute("ROLLBACK")
    except Exception as exc:
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, f"scope_loader_exception:{type(exc).__name__}:{exc}")


def load_n3_hint_target_snapshot_from_db(
    *,
    args: Any,
    dependencies: Any,
    config: Mapping[str, Any],
    target_run_id: str,
) -> Mapping[str, Any]:
    del args, dependencies
    try:
        with _connect_db(config) as conn:
            conn.execute("BEGIN READ ONLY")
            try:
                return _load_n3_hint_target_snapshot_with_connection(conn=conn, target_run_id=target_run_id)
            finally:
                conn.execute("ROLLBACK")
    except Exception as exc:
        return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, f"target_snapshot_exception:{type(exc).__name__}:{exc}")


def load_n3_hint_previous_day_reference_rows_from_db(
    *,
    args: Any,
    dependencies: Any,
    config: Mapping[str, Any],
    scope: Mapping[str, Any],
    target_run_id: str,
) -> Mapping[str, Any]:
    del args, dependencies
    try:
        with _connect_db(config) as conn:
            conn.execute("BEGIN READ ONLY")
            try:
                return _load_n3_hint_previous_day_reference_rows_with_connection(
                    conn=conn,
                    scope=scope,
                    target_run_id=target_run_id,
                )
            finally:
                conn.execute("ROLLBACK")
    except Exception as exc:
        return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, f"previous_day_reference_exception:{type(exc).__name__}:{exc}")


def _validate_hint_execute_artifacts(
    *,
    args: Any,
    target_run_id: str,
    parsed_target: Mapping[str, str],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    for name, artifact in (("contract", contract), ("preflight", preflight)):
        if artifact.get("result") != N3_READY_RESULT:
            return _blocked(HINT_PROOF_EXECUTE_BLOCKER, f"{name}_not_execute_ready")
        if str(artifact.get("target_run_id") or "") != target_run_id:
            return _blocked(HINT_PROOF_EXECUTE_BLOCKER, f"{name}_target_run_id_mismatch")
    actual_hhmm = str(preflight.get("actual_until_hhmm") or contract.get("actual_until_hhmm") or "")
    if actual_hhmm != parsed_target["until_hhmm"]:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "actual_hhmm_target_mismatch")
    if str(getattr(args, "for_trade_date", "") or "") and str(getattr(args, "for_trade_date")) != parsed_target["trade_date"]:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "for_trade_date_target_mismatch")
    contract_hash = str(contract.get("source_artifact_payload_hash") or "")
    preflight_hash = str(preflight.get("source_artifact_payload_hash") or "")
    if contract_hash and preflight_hash and contract_hash != preflight_hash:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "source_payload_hash_mismatch")
    if contract.get("writes_outbox") or preflight.get("writes_outbox"):
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "artifact_writes_outbox_forbidden")
    return None


def _validate_hint_execute_write_plan(
    *,
    write_plan: Mapping[str, Any],
    preflight: Mapping[str, Any],
    target_run_id: str,
) -> Mapping[str, Any] | None:
    if not write_plan:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "write_plan_missing")
    if str(write_plan.get("projection_run_id") or "") != target_run_id:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "write_plan_target_run_id_mismatch")
    if str(write_plan.get("proof_kind") or "") != MIDDAY_BRIDGE_HINT_PROOF_KIND:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "write_plan_proof_kind_mismatch")
    if int(write_plan.get("stock_rows") or 0) != 0:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "stock_rows_forbidden")
    metric_rows = write_plan.get("metric_rows") or {}
    if not isinstance(metric_rows, Mapping):
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "metric_rows_missing")
    if metric_rows.get("stock"):
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "stock_rows_forbidden")
    if write_plan.get("writes_outbox") or write_plan.get("consumes_outbox") or write_plan.get("touches_n4_n5_n6"):
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "writes_outbox_or_downstream_forbidden")
    allowed_tables = set(write_plan.get("allowed_write_tables") or [])
    expected_allowed = {
        "common_market_data_run",
        "common_market_data_quality_item",
        "index_realtime_hint_projection_metric",
        "board_realtime_hint_projection_metric",
    }
    if allowed_tables != expected_allowed:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "allowed_write_tables_mismatch")
    rows_by_asset = {
        "index": len(_records_from_frame(metric_rows.get("index") or [])),
        "board": len(_records_from_frame(metric_rows.get("board") or [])),
    }
    rows_by_asset = {asset: count for asset, count in rows_by_asset.items() if count}
    if rows_by_asset != dict(write_plan.get("rows_by_asset") or {}):
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "write_plan_rows_by_asset_mismatch")
    total_rows = sum(rows_by_asset.values())
    if int(preflight.get("proof_rows_total") or total_rows) != total_rows:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "preflight_total_rows_mismatch")
    if dict(preflight.get("rows_by_asset") or rows_by_asset) != rows_by_asset:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "preflight_rows_by_asset_mismatch")
    ready_count = sum(
        1
        for rows in (metric_rows.get("index") or [], metric_rows.get("board") or [])
        for row in _records_from_frame(rows)
        if bool(row.get("metric_ready"))
    )
    not_ready_count = total_rows - ready_count
    metric_ready = {"ready": ready_count, "not_ready": not_ready_count}
    if dict(write_plan.get("metric_ready") or {}) != metric_ready:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "write_plan_metric_ready_mismatch")
    if dict(preflight.get("metric_ready") or metric_ready) != metric_ready:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "preflight_metric_ready_mismatch")
    distribution = Counter(
        str(row.get("projection_30m_type") or "")
        for rows in (metric_rows.get("index") or [], metric_rows.get("board") or [])
        for row in _records_from_frame(rows)
    )
    distribution_dict = dict(distribution)
    if dict(write_plan.get("projection_type_distribution") or {}) != distribution_dict:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "write_plan_projection_distribution_mismatch")
    if dict(preflight.get("projection_type_distribution") or distribution_dict) != distribution_dict:
        return _blocked(HINT_PROOF_EXECUTE_BLOCKER, "preflight_projection_distribution_mismatch")
    return None


def _default_hint_execute_rollback_path(parsed_target: Mapping[str, str]) -> str:
    suffix = "midday_bridge_v1" if parsed_target.get("proof_kind") == MIDDAY_BRIDGE_HINT_PROOF_KIND else "v1"
    return f"sql/N3_hint_index_board_1m_{parsed_target['trade_date']}_{parsed_target['until_hhmm']}_{suffix}_rollback.sql"


def _persist_hint_projection_write_plan_to_db(
    *,
    config: Mapping[str, Any],
    target_run_id: str,
    write_plan: Mapping[str, Any],
) -> Mapping[str, Any]:
    with _connect_db(config) as conn:
        conn.execute("BEGIN")
        try:
            _insert_hint_market_data_run(conn, write_plan)
            quality_rows = _insert_hint_quality_items(conn, write_plan)
            rows_written = {
                "index": _insert_hint_metric_rows(conn, "index", _records_from_frame((write_plan.get("metric_rows") or {}).get("index") or [])),
                "board": _insert_hint_metric_rows(conn, "board", _records_from_frame((write_plan.get("metric_rows") or {}).get("board") or [])),
                "stock": 0,
            }
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    total_rows = int(rows_written["index"]) + int(rows_written["board"])
    return {
        "target_run_id": target_run_id,
        "market_data_run_rows_written": 1,
        "quality_rows_written": quality_rows,
        "rows_written": rows_written,
        "total_rows_written": total_rows,
    }


def _insert_hint_market_data_run(conn: Any, write_plan: Mapping[str, Any]) -> None:
    row = dict(write_plan.get("common_market_data_run") or {})
    run_id = str(row.get("run_id") or write_plan.get("projection_run_id") or "")
    rows_total = sum(int(value or 0) for value in (write_plan.get("rows_by_asset") or {}).values())
    quality_items = _records_from_frame(write_plan.get("quality_items") or [])
    p_counts = Counter(str(item.get("severity") or "") for item in quality_items)
    now = _now_shanghai_iso()
    raw_json = dict(row.get("raw_json") or {})
    raw_json.update(
        {
            "allowed_write_tables": list(write_plan.get("allowed_write_tables") or []),
            "rows_by_asset": dict(write_plan.get("rows_by_asset") or {}),
            "projection_type_distribution": dict(write_plan.get("projection_type_distribution") or {}),
            "writes_outbox": False,
        }
    )
    conn.execute(
        """
        INSERT INTO common_market_data_run (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          prev_trade_date, mode, status, p0_count, p1_count, p2_count,
          source_scope_row_count, candidate_row_count, subscription_row_count,
          subscription_object_count, dedup_ratio, generated_by,
          market_data_pulled, market_data_fact_written,
          downstream_layers_touched, worker_started, started_at, finished_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, NULL, %s,
                false, true, false, false, %s, %s, %s)
        """,
        (
            run_id,
            row.get("source_condition_run_id"),
            row.get("for_trade_date"),
            row.get("source_trade_date"),
            row.get("prev_trade_date") or row.get("source_trade_date"),
            row.get("mode") or "execute",
            row.get("status") or "passed",
            int(p_counts.get("P0") or 0),
            int(p_counts.get("P1") or 0),
            int(p_counts.get("P2") or 0),
            rows_total,
            rows_total,
            rows_total,
            rows_total,
            "V3-n3-hint-projection-proof-execute-provider",
            now,
            now,
            _jsonb(raw_json),
        ),
    )


def _insert_hint_quality_items(conn: Any, write_plan: Mapping[str, Any]) -> int:
    count = 0
    for item in _records_from_frame(write_plan.get("quality_items") or []):
        conn.execute(
            """
            INSERT INTO common_market_data_quality_item (
              run_id, source_condition_run_id, for_trade_date, source_trade_date,
              data_domain, layer_scope, table_name, gate_code, gate_name,
              severity, status, expected_value, actual_value, details
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item.get("run_id"),
                item.get("source_condition_run_id"),
                item.get("for_trade_date"),
                item.get("source_trade_date"),
                item.get("data_domain"),
                item.get("layer_scope"),
                item.get("table_name"),
                item.get("gate_code"),
                item.get("gate_name"),
                item.get("severity"),
                item.get("status"),
                item.get("expected_value"),
                item.get("actual_value"),
                _jsonb(item.get("details") or {}),
            ),
        )
        count += 1
    return count


def _insert_hint_metric_rows(conn: Any, asset_kind: str, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    if asset_kind not in {"index", "board"}:
        raise RuntimeError("stock HINT metric rows are forbidden")
    table_name = f"{asset_kind}_realtime_hint_projection_metric"
    columns = [
        "projection_run_id",
        "trade_date",
        "metric_minute_label",
        "asset_kind",
        "identity_key",
        "code",
        "name",
        "direction",
        "condition_key",
        "original_condition_key",
        "source_condition_pool_id",
        "source_minute_target_scope_id",
        "source_subscription_run_id",
        "source_artifact_path",
        "source_artifact_sha256",
        "source_previous_day_minute_run_id",
        "source_context_run_id",
        "proof_kind",
        "source_mode",
        "metric_role",
        "proof_owner",
        "proof_consumer",
        "not_n5_final_proof",
        "current_window_start",
        "current_window_end",
        "previous_completed_window_start",
        "previous_completed_window_end",
        "current_window_elapsed_count",
        "full_window_count",
        "current_30m_price",
        "current_30m_elapsed_amount",
        "previous_day_same_elapsed_30m_amount",
        "previous_day_full_30m_amount",
        "current_30m_virtual_amount",
        "reference_30m_amount",
        "reference_30m_entity_high",
        "reference_30m_entity_low",
        "projection_30m_type",
        "projection_30m_flag",
        "metric_ready",
        "blocked_reasons",
        "raw_json",
        "trace_json",
    ]
    sql = f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
    """
    for row in rows:
        if str(row.get("asset_kind") or "") != asset_kind:
            raise RuntimeError("asset_kind/table mismatch for HINT metric row")
        params = []
        for column in columns:
            value = row.get(column)
            if column in {"raw_json", "trace_json"}:
                value = _jsonb(value or {})
            params.append(value)
        conn.execute(sql, tuple(params))
    return len(rows)


def _jsonb(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except Exception:  # pragma: no cover - tests can run without psycopg.
        return value
    return Jsonb(value)


def _now_shanghai_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _load_n3_hint_frequency8_scope_with_connection(
    *,
    conn: Any,
    for_trade_date: str,
    n4_context_run_id: str,
) -> Mapping[str, Any]:
    if not n4_context_run_id:
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, "missing_scope_input:n4_context_run_id")
    status = _run_status(conn, "common_trigger_run", n4_context_run_id)
    if status != "passed":
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, f"n4_context_status={status or 'missing'}")

    context_rows = {
        "stock": _hint_context_rows(conn, "stock_trigger_context_snapshot", n4_context_run_id),
        "index": _hint_context_rows(conn, "index_trigger_context_snapshot", n4_context_run_id),
        "board": _hint_context_rows(conn, "board_trigger_context_snapshot", n4_context_run_id),
    }
    bad_dates = [
        f"{asset}:{row.get('identity_key')}:{row.get('for_trade_date')}"
        for asset, rows in context_rows.items()
        for row in rows
        if row.get("for_trade_date") and str(row.get("for_trade_date")) != for_trade_date
    ]
    if bad_dates:
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, f"for_trade_date_mismatch:{bad_dates[0]}")
    bad_quality = [
        f"{asset}:{row.get('identity_key')}:{row.get('quality_status')}"
        for asset, rows in context_rows.items()
        for row in rows
        if str(row.get("quality_status") or "passed") != "passed"
    ]
    if bad_quality:
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, f"context_quality_not_passed:{bad_quality[0]}")

    stock_hint_rows = [row for row in context_rows["stock"] if _is_hint_context_row(row)]
    index_hint_rows = [row for row in context_rows["index"] if _is_hint_context_row(row)]
    board_hint_rows = [row for row in context_rows["board"] if _is_hint_context_row(row)]
    index_objects_or_blocked = _dedupe_hint_context_objects(index_hint_rows, asset_kind="index")
    if isinstance(index_objects_or_blocked, Mapping) and _is_blocked(index_objects_or_blocked):
        return index_objects_or_blocked
    board_objects_or_blocked = _dedupe_hint_context_objects(board_hint_rows, asset_kind="board")
    if isinstance(board_objects_or_blocked, Mapping) and _is_blocked(board_objects_or_blocked):
        return board_objects_or_blocked

    index_objects = list(index_objects_or_blocked)
    board_objects = list(board_objects_or_blocked)
    scope = {
        "for_trade_date": for_trade_date,
        "n4_context_run_id": n4_context_run_id,
        "n4_context_status": "passed",
        "source_scope_policy": HINT_SOURCE_SCOPE_POLICY,
        "stock_1m_objects": [],
        "stock_quote_objects": [],
        "stock_minute_bar_objects": [],
        "index_1m_objects": index_objects,
        "board_1m_objects": board_objects,
        "stock_hint_row_count": len(stock_hint_rows),
        "index_hint_row_count": len(index_hint_rows),
        "board_hint_row_count": len(board_hint_rows),
        "stock_hint_excluded_count": len(stock_hint_rows),
        "stock_excluded_count": len(stock_hint_rows),
        "stock_minute_bar_scope_count": 0,
        "stock_object_count": 0,
        "index_object_count": len(index_objects),
        "board_object_count": len(board_objects),
        "index_board_1m_count": len(index_objects) + len(board_objects),
        "context_row_counts": {asset: len(rows) for asset, rows in context_rows.items()},
        "dedupe_counts": {"index": len(index_objects), "board": len(board_objects)},
        "database_written": False,
        "market_data_pulled": False,
        "writes_outbox": False,
    }
    blocker = validate_n3_hint_frequency8_scope(scope)
    if blocker is not None:
        return blocker
    return scope


def _load_n3_hint_target_snapshot_with_connection(*, conn: Any, target_run_id: str) -> Mapping[str, Any]:
    return {
        "run_exists": _count_sql(conn, "SELECT count(*) FROM common_market_data_run WHERE run_id=%s", (target_run_id,)),
        "quality_rows": _count_sql(
            conn,
            "SELECT count(*) FROM common_market_data_quality_item WHERE run_id=%s",
            (target_run_id,),
        ),
        "index_rows": _count_sql(conn, "SELECT count(*) FROM index_realtime_hint_projection_metric WHERE projection_run_id=%s", (target_run_id,)),
        "board_rows": _count_sql(conn, "SELECT count(*) FROM board_realtime_hint_projection_metric WHERE projection_run_id=%s", (target_run_id,)),
        "outbox_refs": _count_sql(
            conn,
            "SELECT count(*) FROM common_event_outbox WHERE source_layer=%s AND event_type = ANY(%s) AND source_run_id=%s",
            ("N3_market_data", list(N3_OUTBOX_EVENT_TYPES), target_run_id),
        ),
        "inbox_refs": _count_event_inbox_refs_for_source_run(conn, target_run_id),
        "checkpoint_refs": _count_event_checkpoint_refs_for_source_run(conn, target_run_id),
        "n4_refs": _count_optional_column_refs(
            conn,
            ("common_trigger_run", "common_trigger_state", "common_trigger_match"),
            ("run_id", "source_run_id", "trigger_run_id", "projection_run_id", "source_projection_run_id"),
            target_run_id,
        ),
        "n5_refs": _count_optional_column_refs(
            conn,
            ("common_action_run", "common_action_event"),
            ("run_id", "source_run_id", "trigger_run_id", "action_run_id", "projection_run_id"),
            target_run_id,
        ),
        "n6_refs": _count_optional_column_refs(
            conn,
            ("user_projection_run", "user_signal_projection", "user_signal_card"),
            ("run_id", "source_run_id", "trigger_run_id", "action_run_id", "projection_run_id"),
            target_run_id,
        ),
    }


def _count_event_inbox_refs_for_source_run(conn: Any, target_run_id: str) -> int:
    return _count_sql(
        conn,
        """
        SELECT count(*)
        FROM common_event_inbox inbox
        WHERE EXISTS (
          SELECT 1
          FROM common_event_outbox outbox
          WHERE outbox.source_layer=%s
            AND outbox.event_type = ANY(%s)
            AND outbox.source_run_id=%s
            AND inbox.source_layer = outbox.source_layer
            AND inbox.event_id = outbox.event_id
        )
        """,
        ("N3_market_data", list(N3_OUTBOX_EVENT_TYPES), target_run_id),
    )


def _count_event_checkpoint_refs_for_source_run(conn: Any, target_run_id: str) -> int:
    return _count_sql(
        conn,
        """
        SELECT count(*)
        FROM common_event_consumer_checkpoint checkpoint
        WHERE EXISTS (
          SELECT 1
          FROM common_event_outbox outbox
          WHERE outbox.source_layer=%s
            AND outbox.event_type = ANY(%s)
            AND outbox.source_run_id=%s
            AND (
              (checkpoint.last_outbox_id IS NOT NULL AND checkpoint.last_outbox_id = outbox.outbox_id)
              OR (checkpoint.last_event_id IS NOT NULL AND checkpoint.last_event_id = outbox.event_id)
            )
        )
        """,
        ("N3_market_data", list(N3_OUTBOX_EVENT_TYPES), target_run_id),
    )


def _load_n3_hint_previous_day_reference_rows_with_connection(
    *,
    conn: Any,
    scope: Mapping[str, Any],
    target_run_id: str,
) -> Mapping[str, Any]:
    from ashare_v3.market.hint_1m_projection_persistence import parse_hint_projection_run_id

    parsed = parse_hint_projection_run_id(target_run_id)
    source_previous_day_minute_run_id = _derive_previous_day_minute_run_id(parsed_target=parsed)
    rows: list[dict[str, Any]] = []
    entity_reference_row_count = 0
    merged_entity_reference_row_count = 0
    for asset_kind, cumulative_table_name, minute_table_name, identity_column, objects_key in (
        (
            "index",
            "index_previous_day_minute_cumulative",
            "index_minute_bar_1m",
            "index_identity_key",
            "index_1m_objects",
        ),
        (
            "board",
            "board_previous_day_minute_cumulative",
            "board_minute_bar_1m",
            "board_identity_key",
            "board_1m_objects",
        ),
    ):
        identities = [str(obj.get("identity_key") or "") for obj in _rows(scope, objects_key)]
        identities = [identity for identity in identities if identity]
        if not identities:
            continue
        cumulative_rows = _fetchall(
            conn,
            f"""
            SELECT
              asset_kind,
              identity_key,
              source_trade_date,
              canonical_minute_label,
              cumulative_amount_yuan,
              code,
              exchange,
              elapsed_index
            FROM {cumulative_table_name}
            WHERE source_previous_day_minute_run_id=%s
              AND for_trade_date=%s
              AND source_trade_date=%s
              AND identity_key = ANY(%s)
            ORDER BY identity_key, elapsed_index
            """,
            (
                source_previous_day_minute_run_id,
                parsed["trade_date"],
                parsed["source_trade_date"],
                identities,
            ),
        )
        reference_rows = _cumulative_rows_to_1m_reference_rows(cumulative_rows, expected_asset_kind=asset_kind)
        entity_reference_rows = _fetch_previous_day_last_30m_entity_reference_rows(
            conn=conn,
            asset_kind=asset_kind,
            table_name=minute_table_name,
            identity_column=identity_column,
            for_trade_date=parsed["trade_date"],
            previous_trade_date=parsed["source_trade_date"],
            identities=identities,
        )
        entity_reference_row_count += len(entity_reference_rows)
        merged_entity_reference_row_count += _merge_previous_day_last_30m_entity_reference_rows(
            reference_rows,
            entity_reference_rows,
        )
        rows.extend(reference_rows)
    if not rows:
        return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, "previous_day_reference_rows_missing")
    return {
        "previous_day_1m_rows": rows,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "previous_day_reference_rows": len(rows),
        "previous_day_entity_reference_rows": entity_reference_row_count,
        "previous_day_entity_reference_rows_merged": merged_entity_reference_row_count,
    }


def validate_n3_hint_frequency8_scope(scope: Mapping[str, Any]) -> Mapping[str, Any] | None:
    failed = [
        f"{key}={scope.get(key)}"
        for key, expected in (("n4_context_status", "passed"),)
        if key in scope and str(scope.get(key)) != expected
    ]
    if failed:
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, ",".join(failed))
    if _rows(scope, "stock_quote_objects", "stock_1m_objects", "stock_minute_bar_objects"):
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, "stock_hint_source_scope_forbidden")
    index_objects = _rows(scope, "index_1m_objects")
    board_objects = _rows(scope, "board_1m_objects")
    if not index_objects and not board_objects:
        return _blocked(HINT_SOURCE_SCOPE_BLOCKER, "hint_index_board_scope_empty")
    return None


def validate_n3_hint_frequency8_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = _rows(payload, "index_board_1m_rows")
    proof_input_time = str(payload.get("proof_input_time") or "")
    proof_dt = _parse_dt(proof_input_time)
    blocked: list[str] = []
    normalization_trace = payload.get("normalization_trace") or {}
    if isinstance(normalization_trace, Mapping) and int(normalization_trace.get("duplicate_conflict_count") or 0) > 0:
        blocked.append("duplicate_object_minute_conflict")
    seen: set[tuple[str, str]] = set()
    observed_object_keys: set[tuple[str, str]] = set()
    expected_object_keys = _expected_payload_object_keys(payload)
    required = ("open", "high", "low", "close", "amount")
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind not in {"index", "board"}:
            blocked.append("non_index_board_row")
        identity_key = str(row.get("identity_key") or "")
        if asset_kind and identity_key:
            observed_object_keys.add((asset_kind, identity_key))
        if any(row.get(field) in (None, "") for field in required):
            blocked.append("required_fields_missing")
        if _row_has_fake_marker(row):
            blocked.append("fake_source_marker")
        label = _row_minute_label(row)
        if label == "11:30":
            blocked.append("canonical_1130_forbidden")
        row_dt = _parse_dt(str(row.get("bar_time") or row.get("datetime") or ""))
        if proof_dt is not None and row_dt is not None and row_dt > proof_dt:
            blocked.append("row_after_proof_input_time")
        key = (str(row.get("identity_key") or ""), label)
        if key in seen:
            blocked.append("duplicate_object_minute")
        seen.add(key)
        if _row_trade_date(row, row_dt=row_dt) != str(payload.get("for_trade_date") or ""):
            blocked.append("source_trade_date_mismatch")
    if not rows:
        blocked.append("hint_source_rows_missing")
    if expected_object_keys:
        if expected_object_keys - observed_object_keys:
            blocked.append("missing_scoped_object")
        if observed_object_keys - expected_object_keys:
            blocked.append("unexpected_scoped_object")
    return {"valid": not blocked, "blocked_reasons": list(dict.fromkeys(blocked))}


def compute_n3_hint_frequency8_source_payload_hash(payload: Mapping[str, Any]) -> str:
    payload_for_hash = {
        "proof_input_time": payload.get("proof_input_time"),
        "actual_until_hhmm": payload.get("actual_until_hhmm"),
        "index_board_1m_rows": payload.get("index_board_1m_rows") or [],
        "hint_proof_kind": payload.get("hint_proof_kind"),
    }
    return hashlib.sha256(
        json.dumps(payload_for_hash, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _build_source_payload(*, args: Any, scope: Mapping[str, Any], fetched: Mapping[str, Any]) -> dict[str, Any]:
    for_trade_date = str(getattr(args, "for_trade_date", "") or scope.get("for_trade_date") or "")
    raw_rows = [dict(row) for row in _rows(fetched, "index_board_1m_rows", "index_1m_rows", "board_1m_rows")]
    normalized = normalize_hint_frequency8_source_rows_before_validation(
        raw_rows,
        for_trade_date=for_trade_date,
        proof_input_time=str(fetched.get("proof_input_time") or ""),
    )
    rows = [dict(row) for row in normalized["normalized_rows"]]
    derived_proof_input_time = _derive_proof_input_time(rows)
    proof_input_time = _select_hint_proof_input_time(
        raw_proof_input_time=str(fetched.get("proof_input_time") or ""),
        derived_proof_input_time=derived_proof_input_time,
        for_trade_date=for_trade_date,
    )
    actual_until_hhmm = _hhmm_from_time(proof_input_time)
    index_rows = [row for row in rows if str(row.get("asset_kind") or "") == "index"]
    board_rows = [row for row in rows if str(row.get("asset_kind") or "") == "board"]
    stock_excluded = int(scope.get("stock_hint_excluded_count") or scope.get("stock_excluded_count") or 0)
    return {
        "proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
        "hint_proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
        "source_mode": HINT_SOURCE_MODE,
        "asset_scope": "index_board_only",
        "metric_role": "hint_trigger_proof_source",
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "not_n5_final_proof": True,
        "for_trade_date": for_trade_date,
        "target_run_id": str(getattr(args, "target_run_id", "") or ""),
        "n4_context_run_id": str(getattr(args, "n4_context_run_id", "") or scope.get("n4_context_run_id") or ""),
        "subscription_run_id": str(getattr(args, "subscription_run_id", "") or scope.get("subscription_run_id") or ""),
        "proof_input_time": proof_input_time,
        "actual_until_hhmm": actual_until_hhmm,
        "index_board_1m_rows": rows,
        "source_payload_counts": {"index_rows": len(index_rows), "board_rows": len(board_rows), "stock_rows": 0},
        "source_object_counts": {
            "index": int(scope.get("index_object_count") or len(_rows(scope, "index_1m_objects"))),
            "board": int(scope.get("board_object_count") or len(_rows(scope, "board_1m_objects"))),
            "stock_excluded": stock_excluded,
        },
        "stock_rows": 0,
        "stock_excluded_count": stock_excluded,
        "source_scope_policy": str(scope.get("source_scope_policy") or HINT_SOURCE_SCOPE_POLICY),
        "source_scope_identity_keys": {
            "index": sorted(str(obj.get("identity_key") or "") for obj in _rows(scope, "index_1m_objects")),
            "board": sorted(str(obj.get("identity_key") or "") for obj in _rows(scope, "board_1m_objects")),
        },
        "midday_bridge_policy": "hint_1300_as_1130_close_v1",
        "normalization_trace": normalized["normalization_trace"],
        "database_written": False,
        "writes_outbox": False,
    }


def _fetch_report_from_payload(*, scope: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "proof_input_time": payload.get("proof_input_time"),
        "actual_until_hhmm": payload.get("actual_until_hhmm"),
        "proof_kind": payload.get("proof_kind"),
        "source_mode": payload.get("source_mode"),
        "source_payload_counts": payload.get("source_payload_counts"),
        "source_object_counts": payload.get("source_object_counts"),
        "stock_excluded_count": payload.get("stock_excluded_count"),
        "normalization_trace": payload.get("normalization_trace"),
        "source_scope_policy": scope.get("source_scope_policy") or HINT_SOURCE_SCOPE_POLICY,
        "validation_result": {"valid": True, "blocked_reasons": []},
        "market_data_pulled": True,
        "database_written": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "updates_inbox_or_checkpoint": False,
        "starts_worker": False,
        "touches_n4_n5_n6": False,
    }


def normalize_hint_frequency8_source_rows_before_validation(
    rows: Sequence[Mapping[str, Any]],
    *,
    for_trade_date: str,
    proof_input_time: str | None = None,
) -> dict[str, Any]:
    """Filter HINT frequency=8 rows to the proof date before validation.

    The low-level adapter can return several trade dates in one offset window.
    This normalizer only removes rows that are outside the requested trade date
    and collapses exact duplicate object-minute rows. Current-day raw/canonical
    11:30 rows are intentionally preserved so the existing HINT validation path
    still fails closed unless the midday bridge policy explicitly handles them.
    """

    del proof_input_time
    normalized_trade_date = _normalize_trade_date(for_trade_date)
    trace: dict[str, Any] = {
        "raw_row_count": 0,
        "normalized_row_count": 0,
        "rows_dropped_date_mismatch": 0,
        "rows_dropped_1130": 0,
        "duplicate_rows_collapsed": 0,
        "duplicate_conflict_count": 0,
        "dates_seen": [],
        "source_trade_date_set": [],
        "for_trade_date": normalized_trade_date,
        "duplicate_conflict_samples": [],
    }
    dates_seen: set[str] = set()
    source_trade_dates: set[str] = set()
    rows_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    signatures_by_key: dict[tuple[str, str, str], tuple[tuple[str, Any], ...]] = {}

    for raw_row in rows:
        trace["raw_row_count"] += 1
        row = dict(raw_row)
        row_dt = _parse_dt(str(row.get("bar_time") or row.get("datetime") or ""))
        row_trade_date = _row_trade_date(row, row_dt=row_dt)
        if row_trade_date:
            dates_seen.add(row_trade_date)
            source_trade_dates.add(row_trade_date)
        if row_trade_date != normalized_trade_date:
            trace["rows_dropped_date_mismatch"] += 1
            continue

        label = _row_minute_label(row)
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""), label)
        signature = _hint_frequency8_duplicate_signature(row)
        existing_signature = signatures_by_key.get(key)
        if existing_signature is not None:
            if existing_signature == signature:
                trace["duplicate_rows_collapsed"] += 1
                continue
            trace["duplicate_conflict_count"] += 1
            samples = trace["duplicate_conflict_samples"]
            if isinstance(samples, list) and len(samples) < 5:
                samples.append({"asset_kind": key[0], "identity_key": key[1], "minute_label": key[2]})
            continue
        rows_by_key[key] = row
        signatures_by_key[key] = signature

    normalized_rows = list(rows_by_key.values())
    trace["normalized_row_count"] = len(normalized_rows)
    trace["dates_seen"] = sorted(dates_seen)
    trace["source_trade_date_set"] = sorted(source_trade_dates)
    return {"normalized_rows": normalized_rows, "normalization_trace": trace, "blockers": []}


def _expected_payload_object_keys(payload: Mapping[str, Any]) -> set[tuple[str, str]]:
    raw_scope = payload.get("source_scope_identity_keys") or {}
    if not isinstance(raw_scope, Mapping):
        return set()
    expected: set[tuple[str, str]] = set()
    for asset_kind in ("index", "board"):
        value = raw_scope.get(asset_kind) or []
        if isinstance(value, str):
            identities = [value]
        elif isinstance(value, Sequence):
            identities = value
        else:
            identities = []
        expected.update((asset_kind, str(identity)) for identity in identities if str(identity or ""))
    return expected


def _normalize_index_board_row(*, raw: Mapping[str, Any], obj: Mapping[str, Any], for_trade_date: str) -> dict[str, Any] | None:
    row_dt = _market_datetime_from_value(raw.get("bar_time") or raw.get("datetime") or raw.get("time"), for_trade_date=for_trade_date)
    if row_dt is None:
        return None
    bar_time = _format_shanghai_iso(row_dt)
    return {
        "asset_kind": str(obj.get("asset_kind") or ""),
        "identity_key": str(obj.get("identity_key") or ""),
        "exchange": str(obj.get("exchange") or ""),
        "code": str(obj.get("code") or raw.get("code") or ""),
        "name": str(obj.get("name") or raw.get("name") or ""),
        "bar_time": bar_time,
        "datetime": bar_time,
        "minute_label": row_dt.strftime("%H:%M"),
        "open": _first_present(raw, "open"),
        "high": _first_present(raw, "high"),
        "low": _first_present(raw, "low"),
        "close": _first_present(raw, "close", "price"),
        "amount": _first_present(raw, "amount", "turnover"),
        "volume": _first_present(raw, "volume", "vol"),
        "source_adapter_method": "index",
        "source_frequency": 8,
        "source_marker": str(raw.get("source_marker") or "mootdx_index_frequency_8"),
        "trade_date": row_dt.strftime("%Y%m%d"),
        "source_trade_date": row_dt.strftime("%Y%m%d"),
        "raw_payload": dict(raw),
    }


def _run_status(conn: Any, table_name: str, run_id: str) -> str:
    if table_name != "common_trigger_run":
        raise ValueError(f"unsupported run status table: {table_name}")
    row = _fetchone(conn, "SELECT status FROM common_trigger_run WHERE run_id=%s", (run_id,))
    if not row:
        return ""
    return str(row[0] if not isinstance(row, Mapping) else row.get("status") or "")


def _hint_context_rows(conn: Any, table_name: str, n4_context_run_id: str) -> list[dict[str, Any]]:
    allowed_tables = {
        "stock_trigger_context_snapshot",
        "index_trigger_context_snapshot",
        "board_trigger_context_snapshot",
    }
    if table_name not in allowed_tables:
        raise ValueError(f"unsupported context table: {table_name}")
    rows = _fetchall(
        conn,
        f"""
        SELECT
          trigger_context_id,
          asset_kind,
          identity_key,
          exchange,
          code,
          display_code,
          name,
          direction,
          condition_key,
          allowed_signal_types,
          is_hint_scope,
          quality_status,
          for_trade_date,
          source_condition_pool_id,
          source_minute_target_scope_id
        FROM {table_name}
        WHERE run_id=%s
        ORDER BY identity_key, trigger_context_id
        """,
        (n4_context_run_id,),
    )
    return [_hint_context_row_dict(row) for row in rows]


def _hint_context_row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return {
            "trigger_context_id": row.get("trigger_context_id"),
            "asset_kind": row.get("asset_kind"),
            "identity_key": row.get("identity_key"),
            "exchange": row.get("exchange"),
            "code": row.get("code"),
            "display_code": row.get("display_code"),
            "name": row.get("name"),
            "direction": row.get("direction"),
            "condition_key": row.get("condition_key"),
            "allowed_signal_types": row.get("allowed_signal_types"),
            "is_hint_scope": bool(row.get("is_hint_scope")),
            "quality_status": row.get("quality_status"),
            "for_trade_date": row.get("for_trade_date"),
            "source_condition_pool_id": row.get("source_condition_pool_id"),
            "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        }
    return {
        "trigger_context_id": row[0],
        "asset_kind": row[1],
        "identity_key": row[2],
        "exchange": row[3],
        "code": row[4],
        "display_code": row[5],
        "name": row[6],
        "direction": row[7],
        "condition_key": row[8],
        "allowed_signal_types": row[9],
        "is_hint_scope": bool(row[10]),
        "quality_status": row[11],
        "for_trade_date": row[12],
        "source_condition_pool_id": row[13],
        "source_minute_target_scope_id": row[14],
    }


def _is_hint_context_row(row: Mapping[str, Any]) -> bool:
    condition_key = str(row.get("condition_key") or "")
    if condition_key in {"BUY_HINT", "SELL_HINT"}:
        return True
    allowed_signal_types = row.get("allowed_signal_types")
    if isinstance(allowed_signal_types, str):
        allowed = {allowed_signal_types}
    elif isinstance(allowed_signal_types, Sequence):
        allowed = {str(value) for value in allowed_signal_types}
    else:
        allowed = set()
    return bool(row.get("is_hint_scope")) and bool(allowed.intersection({"BUY_HINT", "SELL_HINT"}))


def _dedupe_hint_context_objects(rows: Sequence[Mapping[str, Any]], *, asset_kind: str) -> list[dict[str, Any]] | Mapping[str, Any]:
    objects_by_identity: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity_key = str(row.get("identity_key") or "")
        if not identity_key:
            return _blocked(HINT_SOURCE_SCOPE_BLOCKER, f"missing_identity_key:{asset_kind}")
        candidate = {
            "asset_kind": asset_kind,
            "identity_key": identity_key,
            "exchange": str(row.get("exchange") or ""),
            "code": str(row.get("code") or ""),
            "display_code": str(row.get("display_code") or row.get("code") or ""),
            "name": str(row.get("name") or ""),
            "direction": str(row.get("direction") or ""),
            "condition_key": str(row.get("condition_key") or ""),
            "original_condition_key": str(row.get("original_condition_key") or row.get("condition_key") or ""),
            "source_condition_pool_id": row.get("source_condition_pool_id"),
            "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        }
        existing = objects_by_identity.get(identity_key)
        if existing is not None and any(existing.get(field) != candidate.get(field) for field in candidate):
            return _blocked(HINT_SOURCE_SCOPE_BLOCKER, f"duplicate_identity_ambiguity:{asset_kind}:{identity_key}")
        objects_by_identity[identity_key] = candidate
    return [objects_by_identity[key] for key in sorted(objects_by_identity)]


def _validate_hint_proof_source_payload(source_payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if str(source_payload.get("hint_proof_kind") or source_payload.get("proof_kind") or "") != MIDDAY_BRIDGE_HINT_PROOF_KIND:
        return _blocked(HINT_SOURCE_PROOF_KIND_BLOCKER, f"required HINT proof kind is {MIDDAY_BRIDGE_HINT_PROOF_KIND}")
    if str(source_payload.get("asset_scope") or "") != "index_board_only":
        return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, "asset_scope_must_be_index_board_only")
    if int(source_payload.get("stock_rows") or 0) != 0:
        return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, "stock_rows_forbidden")
    for row in _rows(source_payload, "index_board_1m_rows"):
        if str(row.get("asset_kind") or "") not in {"index", "board"}:
            return _blocked(HINT_PROOF_PREFLIGHT_BLOCKER, "non_index_board_source_row")
    validation = validate_n3_hint_frequency8_payload(source_payload)
    if not validation["valid"]:
        return _blocked(
            HINT_PROOF_PREFLIGHT_BLOCKER,
            ",".join(validation["blocked_reasons"]),
            blocked_reasons=validation["blocked_reasons"],
        )
    return None


def _build_hint_proof_rows_from_payload(
    *,
    source_payload: Mapping[str, Any],
    scope: Mapping[str, Any],
    previous_day_1m_rows: Sequence[Mapping[str, Any]],
    projection_run_id: str,
    previous_trade_date: str,
) -> list[dict[str, Any]]:
    from ashare_v3.market.hint_1m_projection_proof import build_index_board_1m_hint_projection_proof

    proof_input_time = str(source_payload.get("proof_input_time") or "")
    current_rows = _rows(source_payload, "index_board_1m_rows")
    proof_rows: list[dict[str, Any]] = []
    for ordinal, obj in enumerate([*_rows(scope, "index_1m_objects"), *_rows(scope, "board_1m_objects")], start=1):
        row = build_index_board_1m_hint_projection_proof(
            asset_kind=str(obj.get("asset_kind") or ""),
            identity_key=str(obj.get("identity_key") or ""),
            for_trade_date=str(source_payload.get("for_trade_date") or ""),
            previous_trade_date=previous_trade_date,
            proof_input_time=proof_input_time,
            current_day_1m_rows=current_rows,
            previous_day_1m_rows=previous_day_1m_rows,
            projection_run_id=projection_run_id,
            projection_id=ordinal,
        )
        row.update(
            {
                "code": obj.get("code"),
                "name": obj.get("name"),
                "direction": obj.get("direction") or _direction_from_condition_key(str(obj.get("condition_key") or "")),
                "condition_key": obj.get("condition_key") or "BUY_HINT",
                "original_condition_key": obj.get("original_condition_key") or obj.get("condition_key") or "BUY_HINT",
                "source_condition_pool_id": obj.get("source_condition_pool_id"),
                "source_minute_target_scope_id": obj.get("source_minute_target_scope_id"),
                "midday_bridge_policy": "hint_1300_as_1130_close_v1",
                "projection_run_proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
            }
        )
        proof_rows.append(row)
    return proof_rows


def _direction_from_condition_key(condition_key: str) -> str:
    return "sell" if condition_key == "SELL_HINT" else "buy"


def _derive_previous_day_minute_run_id(*, parsed_target: Mapping[str, str]) -> str:
    return (
        f"previous_day_minute_preload_{parsed_target['source_trade_date']}_for_{parsed_target['trade_date']}"
        f"__{parsed_target['source_subscription_run_id']}"
    )


def _cumulative_rows_to_1m_reference_rows(rows: Sequence[Any], *, expected_asset_kind: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous_cumulative_by_identity: dict[str, float] = {}
    for raw in rows:
        row = raw if isinstance(raw, Mapping) else {
            "asset_kind": raw[0],
            "identity_key": raw[1],
            "source_trade_date": raw[2],
            "canonical_minute_label": raw[3],
            "cumulative_amount_yuan": raw[4],
            "code": raw[5],
            "exchange": raw[6],
            "elapsed_index": raw[7],
        }
        asset_kind = str(row.get("asset_kind") or expected_asset_kind)
        identity_key = str(row.get("identity_key") or "")
        cumulative = float(row.get("cumulative_amount_yuan") or 0)
        previous = previous_cumulative_by_identity.get(identity_key, 0.0)
        previous_cumulative_by_identity[identity_key] = cumulative
        label = str(row.get("canonical_minute_label") or "")
        logical_label = "11:30" if label == "13:00" else label
        output.append(
            {
                "asset_kind": asset_kind,
                "identity_key": identity_key,
                "trade_date": str(row.get("source_trade_date") or ""),
                "canonical_minute_label": logical_label,
                "minute_label": logical_label,
                "amount": max(cumulative - previous, 0.0),
                "code": row.get("code"),
                "exchange": row.get("exchange"),
                "source_marker": "a1_previous_day_cumulative_alias",
                "raw_cumulative_minute_label": label,
            }
        )
    return output


def _fetch_previous_day_last_30m_entity_reference_rows(
    *,
    conn: Any,
    asset_kind: str,
    table_name: str,
    identity_column: str,
    for_trade_date: str,
    previous_trade_date: str,
    identities: Sequence[str],
) -> list[Any]:
    return _fetchall(
        conn,
        f"""
        SELECT
          '{asset_kind}' AS asset_kind,
          {identity_column} AS identity_key,
          trade_date,
          to_char(bar_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI') AS minute_label,
          open,
          close,
          code,
          exchange
        FROM {table_name}
        WHERE for_trade_date=%s
          AND trade_date=%s
          AND is_previous_day_preload IS TRUE
          AND quality_status='passed'
          AND {identity_column} = ANY(%s)
          AND to_char(bar_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI') = ANY(%s)
        ORDER BY {identity_column}, bar_time
        """,
        (
            for_trade_date,
            previous_trade_date,
            list(identities),
            ["14:31", "15:00"],
        ),
    )


def _merge_previous_day_last_30m_entity_reference_rows(
    reference_rows: list[dict[str, Any]],
    entity_rows: Sequence[Any],
) -> int:
    entity_by_key: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}
    for raw in entity_rows:
        row = raw if isinstance(raw, Mapping) else {
            "asset_kind": raw[0],
            "identity_key": raw[1],
            "trade_date": raw[2],
            "minute_label": raw[3],
            "open": raw[4],
            "close": raw[5],
            "code": raw[6],
            "exchange": raw[7],
        }
        key = (
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
            str(row.get("trade_date") or ""),
            str(row.get("minute_label") or ""),
        )
        entity_by_key[key] = row

    merged_count = 0
    for row in reference_rows:
        key = (
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
            str(row.get("trade_date") or ""),
            str(row.get("minute_label") or row.get("canonical_minute_label") or ""),
        )
        entity = entity_by_key.get(key)
        if entity is None:
            continue
        for field in ("open", "close"):
            if entity.get(field) is not None:
                row[field] = entity.get(field)
        row["entity_reference_source"] = "previous_day_minute_bar_1m"
        merged_count += 1
    return merged_count


def _count_sql(conn: Any, sql: str, params: Sequence[Any] = ()) -> int:
    row = _fetchone(conn, sql, params)
    if not row:
        return 0
    value = row[0] if not isinstance(row, Mapping) else next(iter(row.values()))
    return int(value or 0)


def _count_optional_column_refs(
    conn: Any,
    table_names: Sequence[str],
    column_names: Sequence[str],
    target_run_id: str,
) -> int:
    total = 0
    for table_name in table_names:
        exists = _fetchone(conn, "SELECT to_regclass(%s)", (table_name,))
        regclass = exists[0] if exists and not isinstance(exists, Mapping) else (exists or {}).get("to_regclass") if exists else None
        if not regclass:
            continue
        present_columns = _fetchall(
            conn,
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s AND column_name = ANY(%s)
            """,
            (table_name, list(column_names)),
        )
        columns = [
            str(row[0] if not isinstance(row, Mapping) else row.get("column_name"))
            for row in present_columns
            if str(row[0] if not isinstance(row, Mapping) else row.get("column_name"))
        ]
        if not columns:
            continue
        where_clause = " OR ".join(f"{column}=%s" for column in columns)
        total += _count_sql(conn, f"SELECT count(*) FROM {table_name} WHERE {where_clause}", tuple(target_run_id for _ in columns))
    return total


def _read_json_path(path: str) -> Mapping[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json_if_requested(path: str, payload: Mapping[str, Any]) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_canonical_json_bytes(payload))


def _component_callable(component: Any, method_name: str) -> Callable[..., Any] | None:
    if component is None:
        return None
    if callable(component):
        return component
    method = getattr(component, method_name, None)
    return method if callable(method) else None


def _dependency_method(dependencies: Any, dependency_name: str, method_name: str) -> Callable[..., Any] | None:
    dependency = getattr(dependencies, dependency_name, None)
    if dependency is None:
        return None
    method = getattr(dependency, method_name, None)
    return method if callable(method) else None


def _project_default_dsn() -> str:
    try:
        from scripts.check_condition_source_ready import DEFAULT_DSN
    except ImportError:
        try:
            from check_condition_source_ready import DEFAULT_DSN
        except ImportError:
            return ""
    return str(DEFAULT_DSN or "")


def _default_mootdx_client() -> Any:
    try:
        from mootdx.quotes import Quotes
    except Exception:  # pragma: no cover - optional runtime dependency.
        return None
    try:
        return Quotes.factory(market="std")
    except Exception:  # pragma: no cover - optional runtime dependency.
        return None


def _connect_db(config: Mapping[str, Any]) -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - environment dependency
        raise RuntimeError("psycopg is required for HINT source scope DB loading") from exc

    database_url = str(config.get("database_url") or "")
    if database_url:
        return psycopg.connect(database_url)
    pg_database = str(config.get("pg_database") or "")
    if not pg_database:
        raise ValueError("database_url or pg_database is required for HINT source scope DB loading")
    kwargs: dict[str, Any] = {"dbname": pg_database}
    if config.get("pg_host"):
        kwargs["host"] = str(config["pg_host"])
    if config.get("pg_user"):
        kwargs["user"] = str(config["pg_user"])
    if config.get("pg_port"):
        kwargs["port"] = str(config["pg_port"])
    return psycopg.connect(**kwargs)


def _fetchone(conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
    cursor = conn.execute(sql, params)
    return cursor.fetchone()


def _fetchall(conn: Any, sql: str, params: Sequence[Any] = ()) -> list[Any]:
    cursor = conn.execute(sql, params)
    return list(cursor.fetchall())


def _call_with_supported_kwargs(callback: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback(**kwargs)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return callback(**kwargs)
    supported = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return callback(**supported)


def _records_from_frame(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict("records")
        except TypeError:
            records = to_dict()
        return [dict(row) for row in records if isinstance(row, Mapping)] if isinstance(records, Sequence) else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _rows(payload: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        rows.extend(_records_from_frame(value))
    return rows


def _derive_proof_input_time(rows: Sequence[Mapping[str, Any]]) -> str:
    candidates = [_parse_dt(str(row.get("bar_time") or row.get("datetime") or "")) for row in rows]
    candidates = [value for value in candidates if value is not None]
    return _format_shanghai_iso(max(candidates)) if candidates else ""


def _select_hint_proof_input_time(
    *,
    raw_proof_input_time: str,
    derived_proof_input_time: str,
    for_trade_date: str,
) -> str:
    raw_dt = _parse_dt(raw_proof_input_time)
    derived_dt = _parse_dt(derived_proof_input_time)
    normalized_trade_date = _normalize_trade_date(for_trade_date)
    if raw_dt is None:
        return derived_proof_input_time
    raw_dt = _ensure_shanghai_tz(raw_dt)
    if normalized_trade_date and raw_dt.strftime("%Y%m%d") != normalized_trade_date:
        return derived_proof_input_time
    if derived_dt is not None and raw_dt > _ensure_shanghai_tz(derived_dt):
        return derived_proof_input_time
    return _format_shanghai_iso(raw_dt)


def _market_datetime_from_value(value: Any, *, for_trade_date: str) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _ensure_shanghai_tz(value)
    text = str(value)
    date_match = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", text)
    time_match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?", text)
    if not time_match:
        return None
    if date_match:
        year, month, day = (int(part) for part in date_match.groups())
    else:
        trade_date = _normalize_trade_date(for_trade_date)
        if len(trade_date) != 8:
            return None
        year, month, day = int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:8])
    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    second = int(time_match.group(3) or 0)
    micro_text = (time_match.group(4) or "").ljust(6, "0")
    return datetime(year, month, day, hour, minute, second, int(micro_text or 0), tzinfo=timezone(timedelta(hours=8)))


def _parse_dt(value: str) -> datetime | None:
    text = str(value or "")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _market_datetime_from_value(text, for_trade_date="")


def _ensure_shanghai_tz(value: datetime) -> datetime:
    shanghai = timezone(timedelta(hours=8))
    return value.replace(tzinfo=shanghai) if value.tzinfo is None else value.astimezone(shanghai)


def _format_shanghai_iso(value: datetime) -> str:
    return _ensure_shanghai_tz(value).isoformat()


def _first_present(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _hhmm_from_time(value: str) -> str:
    match = re.search(r"(\d{2}):(\d{2})", str(value or ""))
    return f"{match.group(1)}{match.group(2)}" if match else ""


def _row_minute_label(row: Mapping[str, Any]) -> str:
    raw = str(row.get("bar_time") or row.get("datetime") or row.get("minute_label") or row.get("time") or "")
    match = re.search(r"(\d{2}):(\d{2})", raw)
    return f"{match.group(1)}:{match.group(2)}" if match else raw[-5:]


def _row_trade_date(row: Mapping[str, Any], *, row_dt: datetime | None) -> str:
    explicit = row.get("trade_date") or row.get("source_trade_date")
    if explicit:
        return _normalize_trade_date(str(explicit))
    if row_dt is not None:
        return row_dt.strftime("%Y%m%d")
    return ""


def _row_has_fake_marker(row: Mapping[str, Any]) -> bool:
    marker_text = " ".join(
        str(row.get(key) or "").lower()
        for key in ("source_marker", "source_time_marker", "source_quality", "marker")
    )
    return any(token in marker_text for token in ("fake", "synthetic", "fabricated"))


def _hint_frequency8_duplicate_signature(row: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    fields = (
        "asset_kind",
        "identity_key",
        "exchange",
        "code",
        "name",
        "bar_time",
        "datetime",
        "minute_label",
        "open",
        "high",
        "low",
        "close",
        "amount",
        "volume",
        "source_marker",
        "trade_date",
        "source_trade_date",
    )
    return tuple((field, _json_stable_value(row.get(field))) for field in fields)


def _json_stable_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _market_code_for_object(obj: Mapping[str, Any]) -> int | None:
    exchange = str(obj.get("exchange") or "")
    if exchange == "SH":
        return 1
    if exchange == "SZ":
        return 0
    return None


def _normalize_trade_date(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))[:8]


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode("utf-8")


def _is_blocked(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("result", "")).startswith("BLOCKED")


def _blocked(result: str, reason: str, **extra: Any) -> dict[str, Any]:
    normalized_reason = reason if reason.startswith(result) else f"{result}:{reason}"
    payload = {
        "result": result,
        "reason": normalized_reason,
        "execute_contract_ready": False,
        "real_io_operation_wired": True,
        "production_adapter_wired": True,
        "market_data_pulled": False,
        "database_written": False,
        "artifact_written": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "updates_inbox_or_checkpoint": False,
        "starts_worker": False,
        "touches_n4_n5_n6": False,
        "touches_n5_n6": False,
    }
    payload.update(extra)
    _apply_forbidden_side_effect_guards(payload)
    return payload


def _apply_forbidden_side_effect_guards(payload: dict[str, Any]) -> None:
    payload["writes_outbox"] = False
    payload["consumes_outbox"] = False
    payload["updates_inbox_or_checkpoint"] = False
    payload["starts_worker"] = False
    payload["touches_n4_n5_n6"] = False
    payload["touches_n5_n6"] = False
    side_effects = dict(payload.get("side_effects") or {})
    side_effects.update(_FORBIDDEN_SIDE_EFFECTS)
    payload["side_effects"] = side_effects
