#!/usr/bin/env python3
"""Run one bounded N3 C1/N3T action-confirmation fastlane shell.

This runner is intentionally artifact-first. It only inspects explicit N5 active
scope artifact files from the configured directory and returns a bounded
manifest. Market pull, DB writes, canonical C1 writes, and N3T table writes
remain separate explicit execute gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ashare_v3.runtime_control.n5_n3t_fastlane import (
    FASTLANE_LANE_ID,
    build_fastlane_source_run_namespace,
    classify_fastlane_session_phase,
    load_fastlane_activation_config,
    resolve_fastlane_runtime_session_context,
    resolve_fastlane_active_worker_decision,
    validate_fastlane_write_enabled_activation_authorization,
)
from ashare_v3.market.c1_scoped_artifact import (
    CURRENT_DAY_SOURCE_ROWS_TYPE,
    apply_source_close_label_policy_to_row,
    build_n3_c1_n3t_metric_context_source_artifact,
    build_n3_c1_scoped_artifact_plan,
    build_n3_c1_scoped_current_day_staging_artifact,
    build_n3_c1_scoped_current_day_pull_plan,
    source_close_label_for_physical_start_label,
)
from ashare_v3.market.n3t_action_confirmation_metric import build_n3t_scoped_metric_from_c1_artifact_plan
from ashare_v3.market.n3t_action_confirmation_metric import (
    N3T_TABLE_BY_ASSET_KIND,
    N3T_WRITER_INSERT_COLUMNS,
    build_n3t_action_confirmation_metric_row,
)

INPUT_ARTIFACT_TYPE = "n5_active_scope_snapshot_v1"
DEFAULT_FASTLANE_MAX_RUNTIME_SECONDS = 10.0


class FastlaneShellBlocked(RuntimeError):
    """Raised when the artifact-first runner cannot proceed safely."""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one artifact-first N3 C1/N3T fastlane shell.")
    parser.add_argument("--activation-config", default="")
    parser.add_argument("--fastlane-lane-id", default="")
    parser.add_argument("--active-scope-artifact-path", default="")
    parser.add_argument("--active-scope-artifact-dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--current-day-source-artifact-dir", default="")
    parser.add_argument("--current-day-source-provider", default="")
    parser.add_argument("--metric-context-source-artifact-dir", default="")
    parser.add_argument("--previous-day-context-artifact-dir", default="")
    parser.add_argument("--previous-day-context-provider", default="")
    parser.add_argument("--n3t-writer-adapter", default="")
    parser.add_argument("--max-runtime-seconds", type=float, default=0.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--scheduler-quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def run_n3_c1_n3t_action_confirmation_fastlane_once(
    argv: Sequence[str] | None = None,
    *,
    now_monotonic: Any = time.monotonic,
    scoped_executor: Callable[..., Mapping[str, Any]] | None = None,
    current_day_source_provider_adapter: Callable[..., Mapping[str, Any]] | None = None,
    metric_context_builder_adapter: Callable[..., Mapping[str, Any]] | None = None,
    previous_day_context_provider_adapter: Callable[..., Mapping[str, Any]] | None = None,
    n3t_writer_adapter: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    invocation_id = f"n3_c1_n3t_fastlane_invocation_{uuid.uuid4().hex}"
    started = now_monotonic()
    artifacts: list[dict[str, Any]] = []
    current_day_source_provider_result: dict[str, Any] | None = None
    metric_context_builder_result: dict[str, Any] | None = None
    try:
        _apply_activation_config(args)
        _validate_args(args)
        artifacts = _discover_requested_active_scope_artifacts(args)
        if args.execute:
            if not artifacts:
                raise FastlaneShellBlocked("active_scope_artifact_missing")
            current_exchange_time = str(getattr(args, "fastlane_current_exchange_time", "") or "").strip()
            if current_exchange_time:
                executable_artifacts, waiting_for_close_artifacts = _split_closed_active_scope_artifacts(
                    artifacts,
                    current_exchange_time=current_exchange_time,
                )
                if waiting_for_close_artifacts and not executable_artifacts:
                    raise FastlaneShellBlocked("target_minute_not_closed")
                artifacts = executable_artifacts
            _materialize_missing_scoped_pull_plans(
                active_scope_artifacts=artifacts,
                output_dir=Path(args.output_dir),
                observed_at=_runner_observed_at(args),
            )
            if current_day_source_provider_adapter is None:
                current_day_source_provider_adapter = _configured_current_day_source_provider_adapter(args)
            if current_day_source_provider_adapter is not None:
                current_day_source_provider_result = _run_current_day_source_provider_adapter(
                    args=args,
                    active_scope_artifacts=artifacts,
                    output_dir=Path(args.output_dir),
                    current_day_source_provider_adapter=current_day_source_provider_adapter,
                )
            _materialize_missing_scoped_current_day_staging_artifacts(
                args=args,
                active_scope_artifacts=artifacts,
                output_dir=Path(args.output_dir),
                observed_at=_runner_observed_at(args),
            )
        scoped_executor_plan = _build_scoped_executor_plan(
            active_scope_artifacts=artifacts,
            output_dir=Path(args.output_dir),
            plan_status="blocked" if args.execute else "planned",
            blocked_reason="scoped_c1_n3t_executor_required" if args.execute else None,
        )
        if args.execute and scoped_executor is None:
            if metric_context_builder_adapter is None:
                if previous_day_context_provider_adapter is None:
                    previous_day_context_provider_adapter = _configured_previous_day_context_provider_adapter(args)
                metric_context_builder_adapter = _configured_metric_context_builder_adapter(
                    args,
                    previous_day_context_provider_adapter=previous_day_context_provider_adapter,
                )
            if metric_context_builder_adapter is not None:
                metric_context_builder_result = _run_metric_context_builder_adapter(
                    args=args,
                    scoped_executor_plan=scoped_executor_plan,
                    metric_context_builder_adapter=metric_context_builder_adapter,
                )
                scoped_executor_plan = _build_scoped_executor_plan(
                    active_scope_artifacts=artifacts,
                    output_dir=Path(args.output_dir),
                    plan_status="blocked",
                    blocked_reason="scoped_c1_n3t_executor_required",
                )
        if args.execute:
            handoff_only = False
            if scoped_executor is not None:
                execute_result = dict(scoped_executor(args=args, active_scope_artifacts=artifacts) or {})
            else:
                n3t_writer_inputs = _n3t_writer_inputs_from_plan(scoped_executor_plan)
                if not n3t_writer_inputs:
                    if n3t_writer_adapter is None:
                        raise FastlaneShellBlocked("scoped_c1_n3t_executor_required")
                    raise FastlaneShellBlocked("n3t_writer_inputs_required")
                if n3t_writer_adapter is None:
                    n3t_writer_adapter = _configured_n3t_writer_adapter(args)
                if n3t_writer_adapter is None:
                    execute_result = _build_n3t_writer_handoff_result(n3t_writer_inputs=n3t_writer_inputs)
                    handoff_only = True
                else:
                    execute_result = dict(
                        n3t_writer_adapter(args=args, n3t_writer_inputs=n3t_writer_inputs) or {}
                    )
            _validate_execute_result(execute_result)
            return {
                "verdict": (
                    "N3_C1_N3T_FASTLANE_N3T_WRITER_HANDOFF_READY"
                    if handoff_only
                    else "N3_C1_N3T_FASTLANE_EXECUTE_PASS"
                ),
                "invocation_id": invocation_id,
                "fastlane_lane_id": args.fastlane_lane_id,
                "fastlane": {
                    "session_phase": getattr(args, "fastlane_session_phase", ""),
                    "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
                },
                "execute_requested": True,
                "writes_enabled": not handoff_only,
                "artifact_first_only": True,
                "active_scope_artifact_dir": args.active_scope_artifact_dir,
                "output_dir": args.output_dir,
                "active_scope_artifact_count": len(artifacts),
                "active_scope_artifacts": artifacts,
                "scoped_executor_plan": scoped_executor_plan,
                "current_day_source_provider_result": current_day_source_provider_result,
                "metric_context_builder_result": metric_context_builder_result,
                "execute_result": execute_result,
                "bounded": {
                    "max_runtime_seconds": float(args.max_runtime_seconds),
                    "elapsed_seconds": round(now_monotonic() - started, 6),
                },
                "boundary": _boundary(),
            }
        return {
            "verdict": "N3_C1_N3T_FASTLANE_SHELL_READY",
            "invocation_id": invocation_id,
            "fastlane_lane_id": args.fastlane_lane_id,
            "fastlane": {
                "session_phase": getattr(args, "fastlane_session_phase", ""),
                "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
            },
            "execute_requested": bool(args.execute),
            "writes_enabled": False,
            "artifact_first_only": True,
            "active_scope_artifact_dir": args.active_scope_artifact_dir,
            "output_dir": args.output_dir,
            "active_scope_artifact_count": len(artifacts),
            "active_scope_artifacts": artifacts,
            "scoped_executor_plan": scoped_executor_plan,
            "current_day_source_provider_result": current_day_source_provider_result,
            "metric_context_builder_result": metric_context_builder_result,
            "bounded": {
                "max_runtime_seconds": float(args.max_runtime_seconds),
                "elapsed_seconds": round(now_monotonic() - started, 6),
            },
            "boundary": _boundary(),
            "next_required_gate": "N3_C1_N3T_SCOPED_REALTIME_POLLER_EXECUTE_GATE",
        }
    except FastlaneShellBlocked as exc:
        verdict = "BLOCKED_N3_C1_N3T_FASTLANE_EXECUTE" if bool(args.execute) else "BLOCKED_N3_C1_N3T_FASTLANE_SHELL"
        return {
            "verdict": verdict,
            "blocked_reason": str(exc),
            "invocation_id": invocation_id,
            "execute_requested": bool(args.execute),
            "writes_enabled": False,
            "fastlane": {
                "session_phase": getattr(args, "fastlane_session_phase", ""),
                "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
            },
            "active_scope_artifact_count": len(artifacts),
            "scoped_executor_plan": _build_scoped_executor_plan(
                active_scope_artifacts=artifacts,
                output_dir=Path(str(getattr(args, "output_dir", "") or ".")),
                plan_status="blocked",
                blocked_reason=str(exc),
            ),
            "boundary": _boundary(),
        }


def _run_metric_context_builder_adapter(
    *,
    args: argparse.Namespace,
    scoped_executor_plan: Mapping[str, Any],
    metric_context_builder_adapter: Callable[..., Mapping[str, Any]],
) -> dict[str, Any] | None:
    candidates = [
        dict(artifact)
        for artifact in scoped_executor_plan.get("planned_artifacts") or []
        if (artifact.get("component_readiness") or {}).get("status") == "waiting_for_metric_context_artifact"
    ]
    if not candidates:
        return None
    result = dict(metric_context_builder_adapter(args=args, planned_artifacts=candidates) or {})
    _validate_metric_context_builder_result(result)
    return result


def _run_current_day_source_provider_adapter(
    *,
    args: argparse.Namespace,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    current_day_source_provider_adapter: Callable[..., Mapping[str, Any]],
) -> dict[str, Any] | None:
    source_dir_text = str(getattr(args, "current_day_source_artifact_dir", "") or "").strip()
    if not source_dir_text:
        raise FastlaneShellBlocked("current_day_source_artifact_dir_required")
    source_dir = Path(source_dir_text)
    source_dir.mkdir(parents=True, exist_ok=True)
    planned = _build_scoped_executor_plan(
        active_scope_artifacts=active_scope_artifacts,
        output_dir=output_dir,
        plan_status="planned",
        blocked_reason=None,
    )
    candidates: list[dict[str, Any]] = []
    for artifact in planned.get("planned_artifacts") or []:
        target_hhmm = str(artifact.get("target_hhmm") or "")
        source_run_hash = str(artifact.get("source_run_hash") or "")
        staging_path = Path(str(artifact.get("staging_artifact_path") or ""))
        if staging_path.exists():
            continue
        if _find_current_day_source_rows_artifact(
            source_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
        ):
            continue
        candidates.append(dict(artifact))
    if not candidates:
        return None
    result = dict(current_day_source_provider_adapter(args=args, planned_artifacts=candidates) or {})
    _validate_current_day_source_provider_result(result)
    return result


def _configured_metric_context_builder_adapter(
    args: argparse.Namespace,
    *,
    previous_day_context_provider_adapter: Callable[..., Mapping[str, Any]] | None = None,
) -> Callable[..., Mapping[str, Any]] | None:
    source_dir = str(getattr(args, "metric_context_source_artifact_dir", "") or "").strip()
    if not source_dir:
        return None

    def adapter(*, args: argparse.Namespace, planned_artifacts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return _build_metric_context_from_source_artifacts(
            args=args,
            planned_artifacts=planned_artifacts,
            source_dir=Path(source_dir),
            previous_day_context_provider_adapter=previous_day_context_provider_adapter,
        )

    return adapter


def _configured_previous_day_context_provider_adapter(
    args: argparse.Namespace,
) -> Callable[..., Mapping[str, Any]] | None:
    provider_name = str(getattr(args, "previous_day_context_provider", "") or "").strip()
    if not provider_name:
        return None
    if provider_name != "postgres_previous_day_raw_c1_context_v1":
        raise FastlaneShellBlocked("previous_day_context_provider_mismatch")

    def adapter(
        *,
        args: argparse.Namespace,
        planned_artifact: Mapping[str, Any],
        target_hhmm: str,
        previous_context_dir: Path,
    ) -> dict[str, Any]:
        return _build_previous_day_context_artifact_from_postgres(
            args=args,
            planned_artifact=planned_artifact,
            target_hhmm=target_hhmm,
            previous_context_dir=Path(previous_context_dir),
            provider_name=provider_name,
        )

    return adapter


def _configured_current_day_source_provider_adapter(
    args: argparse.Namespace,
) -> Callable[..., Mapping[str, Any]] | None:
    provider_name = str(getattr(args, "current_day_source_provider", "") or "").strip()
    if not provider_name:
        return None
    if provider_name != "mootdx_today_minute_adapter_v1":
        raise FastlaneShellBlocked("current_day_source_provider_mismatch")

    def adapter(*, args: argparse.Namespace, planned_artifacts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        from ashare_v3.market.today_minute_execute import MootdxTodayMinuteAdapter

        return _build_current_day_source_rows_with_market_adapter(
            args=args,
            planned_artifacts=planned_artifacts,
            market_adapter=MootdxTodayMinuteAdapter(),
            provider_name=provider_name,
        )

    return adapter


def _configured_n3t_writer_adapter(args: argparse.Namespace) -> Callable[..., Mapping[str, Any]] | None:
    adapter_name = str(getattr(args, "n3t_writer_adapter", "") or "").strip()
    if not adapter_name:
        return None
    if adapter_name != "postgres_n3t_action_confirmation_metric_writer_v1":
        raise FastlaneShellBlocked("n3t_writer_adapter_mismatch")

    def adapter(*, args: argparse.Namespace, n3t_writer_inputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return _write_n3t_metrics_to_postgres(args=args, n3t_writer_inputs=n3t_writer_inputs)

    return adapter


def _build_current_day_source_rows_with_market_adapter(
    *,
    args: argparse.Namespace,
    planned_artifacts: Sequence[Mapping[str, Any]],
    market_adapter: Any,
    provider_name: str,
) -> dict[str, Any]:
    source_dir_text = str(getattr(args, "current_day_source_artifact_dir", "") or "").strip()
    if not source_dir_text:
        raise FastlaneShellBlocked("current_day_source_artifact_dir_required")
    source_dir = Path(source_dir_text)
    source_dir.mkdir(parents=True, exist_ok=True)
    artifact_count = 0
    source_row_count = 0
    source_artifacts: list[dict[str, Any]] = []
    for planned in planned_artifacts:
        target_hhmm = str(planned.get("target_hhmm") or "")
        source_run_hash = str(planned.get("source_run_hash") or "")
        namespace_token = str(planned.get("namespace_token") or "")
        pull_plan = _read_optional_json_artifact(str(planned.get("pull_plan_path") or ""))
        if not pull_plan["exists"]:
            raise FastlaneShellBlocked("scoped_pull_plan_missing_for_source_provider")
        payload = dict(pull_plan.get("payload") or {})
        if payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
            raise FastlaneShellBlocked("scoped_pull_plan_contract_mismatch")
        if payload.get("plan_status") != "planned":
            raise FastlaneShellBlocked("scoped_pull_plan_not_planned")
        if payload.get("full_market_fallback_used") is True:
            raise FastlaneShellBlocked("full_market_fallback_forbidden")
        for_trade_date = str(payload.get("for_trade_date") or planned.get("for_trade_date") or "")
        if not namespace_token:
            namespace_token = f"{for_trade_date}_{target_hhmm}_{source_run_hash or 'unknown'}"
        rows: list[dict[str, Any]] = []
        for plan_row in payload.get("plan_rows") or []:
            subscription = _subscription_from_plan_row(plan_row)
            fetched_rows = market_adapter.fetch_minute_bars(subscription, for_trade_date)
            rows.extend(
                _current_day_source_rows_from_provider_rows(
                    provider_rows=list(fetched_rows or []),
                    plan_row=plan_row,
                    for_trade_date=for_trade_date,
                    provider_name=provider_name,
                )
            )
        artifact = {
            "artifact_type": CURRENT_DAY_SOURCE_ROWS_TYPE,
            "artifact_schema_version": "v1",
            "producer_layer": "N3_market_data",
            "for_trade_date": for_trade_date,
            "target_hhmm": target_hhmm,
            "target_minute_label": _hhmm_to_minute_label(target_hhmm),
            "source_run_hash": source_run_hash,
            "source_run_namespace": namespace_token,
            "source_provider": provider_name,
            "source_adapter": getattr(market_adapter, "external_source", provider_name),
            "source_version": getattr(market_adapter, "source_version", "unknown"),
            "scope_count": int(payload.get("scope_count") or 0),
            "closed_minute_row_count": len(rows),
            "closed_minute_rows": rows,
            "market_data_pulled": True,
            "database_written": False,
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "touches_n4_n5_n6_outbox": False,
            "updates_n4_outbox": False,
            "scans_n5_db": False,
            "touches_n6": False,
            "full_market_fallback_used": False,
        }
        path = source_dir / f"n3_c1_scoped_current_day_source_rows_v1_{namespace_token}.json"
        path.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifact_count += 1
        source_row_count += len(rows)
        source_artifacts.append(
            {
                "path": str(path),
                "target_hhmm": target_hhmm,
                "for_trade_date": for_trade_date,
                "artifact_type": CURRENT_DAY_SOURCE_ROWS_TYPE,
                "row_count": len(rows),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "adapter_type": "n3_c1_scoped_current_day_source_rows_provider_adapter_v1",
        "provider_name": provider_name,
        "artifact_written": artifact_count > 0,
        "artifact_count": artifact_count,
        "source_row_count": source_row_count,
        "source_artifacts": source_artifacts,
        "market_data_pulled": artifact_count > 0,
        "database_written": False,
        "runtime_execute": False,
        "writes_canonical_minute_bar_1m": False,
        "writes_n3_outbox": False,
        "writes_common_event_outbox": False,
        "touches_n4_n5_n6_outbox": False,
        "updates_n4_outbox": False,
        "scans_n5_db": False,
        "touches_n6": False,
        "full_market_fallback_used": False,
    }


def _build_metric_context_from_source_artifacts(
    *,
    args: argparse.Namespace,
    planned_artifacts: Sequence[Mapping[str, Any]],
    source_dir: Path,
    previous_day_context_provider_adapter: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not source_dir.exists() or not source_dir.is_dir():
        raise FastlaneShellBlocked("metric_context_source_artifact_dir_missing")
    artifact_count = 0
    source_artifacts: list[dict[str, Any]] = []
    previous_day_context_provider_results: list[dict[str, Any]] = []
    for planned in planned_artifacts:
        target_hhmm = str(planned.get("target_hhmm") or "")
        source_run_hash = str(planned.get("source_run_hash") or "")
        source = _find_metric_context_source_artifact(
            source_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
        )
        if not source:
            provider_result = _materialize_metric_context_source_artifact_from_previous_day_context(
                args=args,
                planned_artifact=planned,
                source_dir=source_dir,
                target_hhmm=target_hhmm,
                previous_day_context_provider_adapter=previous_day_context_provider_adapter,
            )
            if provider_result:
                previous_day_context_provider_results.append(provider_result)
            source = _find_metric_context_source_artifact(
                source_dir,
                target_hhmm=target_hhmm,
                source_run_hash=source_run_hash,
            )
        if not source:
            raise FastlaneShellBlocked("metric_context_source_artifact_missing")
        active_scope = _read_optional_json_artifact(str(planned.get("input_active_scope_artifact_path") or ""))
        if not active_scope["exists"]:
            raise FastlaneShellBlocked("active_scope_artifact_missing")
        metric_path = Path(str(planned.get("metric_context_artifact_path") or ""))
        if metric_path.exists():
            continue
        artifact = build_n3_c1_scoped_artifact_plan(
            active_scope["payload"],
            target_minute_label=_hhmm_to_minute_label(target_hhmm),
            observed_at=_runner_observed_at(args),
            source_artifact_path=str(active_scope.get("path") or ""),
            source_artifact_hash=str(active_scope.get("sha256") or ""),
            metric_context_rows=list((source.get("payload") or {}).get("metric_context_rows") or []),
        )
        if artifact.get("artifact_status") != "planned" or artifact.get("metric_context_status") != "ready":
            raise FastlaneShellBlocked(str(artifact.get("blocked_reason") or "metric_context_source_contract_mismatch"))
        metric_path.parent.mkdir(parents=True, exist_ok=True)
        metric_path.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifact_count += 1
        source_artifacts.append(
            {
                "path": source.get("path"),
                "sha256": source.get("sha256"),
                "target_hhmm": target_hhmm,
                "artifact_type": "n3_c1_n3t_metric_context_source_v1",
            }
        )
    return {
        "adapter_type": "n3_c1_n3t_metric_context_builder_adapter_v1",
        "artifact_written": artifact_count > 0,
        "artifact_count": artifact_count,
        "source_artifacts": source_artifacts,
        "previous_day_context_provider_results": previous_day_context_provider_results,
        "database_written": False,
        "market_data_pulled": False,
        "runtime_execute": False,
        "writes_canonical_minute_bar_1m": False,
        "writes_n3_outbox": False,
        "writes_common_event_outbox": False,
        "touches_n4_n5_n6_outbox": False,
        "updates_n4_outbox": False,
        "scans_n5_db": False,
        "touches_n6": False,
        "full_market_fallback_used": False,
    }


def _materialize_metric_context_source_artifact_from_previous_day_context(
    *,
    args: argparse.Namespace,
    planned_artifact: Mapping[str, Any],
    source_dir: Path,
    target_hhmm: str,
    previous_day_context_provider_adapter: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    previous_context_dir_text = str(getattr(args, "previous_day_context_artifact_dir", "") or "").strip()
    if not previous_context_dir_text:
        return None
    previous_context_dir = Path(previous_context_dir_text)
    previous_context = _find_previous_day_context_artifact(previous_context_dir, target_hhmm=target_hhmm)
    provider_result: dict[str, Any] | None = None
    if not previous_context and previous_day_context_provider_adapter is not None:
        previous_context_dir.mkdir(parents=True, exist_ok=True)
        provider_result = dict(
            previous_day_context_provider_adapter(
                args=args,
                planned_artifact=planned_artifact,
                target_hhmm=target_hhmm,
                previous_context_dir=previous_context_dir,
            )
            or {}
        )
        _validate_previous_day_context_provider_result(provider_result)
        previous_context = _find_previous_day_context_artifact(previous_context_dir, target_hhmm=target_hhmm)
    if not previous_context:
        return provider_result
    active_scope = _read_optional_json_artifact(str(planned_artifact.get("input_active_scope_artifact_path") or ""))
    staging = _read_optional_json_artifact(str(planned_artifact.get("staging_artifact_path") or ""))
    if not active_scope["exists"]:
        raise FastlaneShellBlocked("active_scope_artifact_missing")
    if not staging["exists"]:
        raise FastlaneShellBlocked("staging_artifact_missing_for_metric_context_source")
    artifact = build_n3_c1_n3t_metric_context_source_artifact(
        active_scope["payload"],
        staging_artifact=staging["payload"],
        previous_day_minute_rows=list((previous_context.get("payload") or {}).get("previous_day_minute_rows") or []),
        target_hhmm=target_hhmm,
        observed_at=_runner_observed_at(args),
        source_staging_artifact_path=str(staging.get("path") or ""),
        source_staging_artifact_hash=str(staging.get("sha256") or ""),
    )
    if artifact.get("artifact_status") != "planned" or artifact.get("metric_context_status") != "ready":
        raise FastlaneShellBlocked(str(artifact.get("blocked_reason") or "metric_context_source_context_mismatch"))
    namespace_token = str(planned_artifact.get("namespace_token") or "")
    source_run_hash = str(planned_artifact.get("source_run_hash") or "")
    artifact = dict(artifact)
    artifact["source_run_hash"] = source_run_hash
    artifact["source_run_namespace"] = namespace_token
    source_dir.mkdir(parents=True, exist_ok=True)
    for_trade_date = str(artifact.get("for_trade_date") or "unknown_trade_date")
    target = str(artifact.get("target_hhmm") or target_hhmm)
    token = namespace_token or f"{for_trade_date}_{target}_{source_run_hash or 'unknown'}"
    path = source_dir / f"n3_c1_n3t_metric_context_source_v1_{token}.json"
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return provider_result


def _find_metric_context_source_artifact(
    source_dir: Path,
    *,
    target_hhmm: str,
    source_run_hash: str = "",
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for path in sorted(source_dir.glob("*.json")):
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != "n3_c1_n3t_metric_context_source_v1":
            continue
        payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
        if payload_hhmm.replace(":", "") != target_hhmm:
            continue
        if source_run_hash:
            payload_hash = str(payload.get("source_run_hash") or "")
            if payload_hash and payload_hash != source_run_hash:
                continue
            if not payload_hash and source_run_hash not in path.name:
                continue
        matches.append(source)
    if len(matches) > 1:
        raise FastlaneShellBlocked("metric_context_source_artifact_ambiguous")
    return matches[0] if matches else None


def _find_current_day_source_rows_artifact(
    source_dir: Path,
    *,
    target_hhmm: str,
    source_run_hash: str = "",
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for path in sorted(source_dir.glob("*.json")):
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != CURRENT_DAY_SOURCE_ROWS_TYPE:
            continue
        payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
        if payload_hhmm.replace(":", "") != target_hhmm:
            continue
        if source_run_hash:
            payload_hash = str(payload.get("source_run_hash") or "")
            if payload_hash and payload_hash != source_run_hash:
                continue
            if not payload_hash and source_run_hash not in path.name:
                continue
        matches.append(source)
    if len(matches) > 1:
        raise FastlaneShellBlocked("current_day_source_artifact_ambiguous")
    return matches[0] if matches else None


def _find_previous_day_context_artifact(previous_context_dir: Path, *, target_hhmm: str) -> dict[str, Any] | None:
    if not previous_context_dir.exists() or not previous_context_dir.is_dir():
        return None
    matches: list[dict[str, Any]] = []
    for path in sorted(previous_context_dir.glob("*.json")):
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != "n3_c1_n3t_previous_day_context_v1":
            continue
        payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
        if payload_hhmm.replace(":", "") != target_hhmm:
            continue
        matches.append(source)
    if len(matches) > 1:
        raise FastlaneShellBlocked("previous_day_context_artifact_ambiguous")
    return matches[0] if matches else None


def _validate_metric_context_builder_result(result: Mapping[str, Any]) -> None:
    if result.get("adapter_type") != "n3_c1_n3t_metric_context_builder_adapter_v1":
        raise FastlaneShellBlocked("metric_context_builder_adapter_type_mismatch")
    forbidden_true_fields = (
        "database_written",
        "market_data_pulled",
        "runtime_execute",
        "writes_canonical_minute_bar_1m",
        "writes_n3_outbox",
        "writes_common_event_outbox",
        "touches_n4_n5_n6_outbox",
        "updates_n4_outbox",
        "scans_n5_db",
        "touches_n6",
        "full_market_fallback_used",
    )
    for field in forbidden_true_fields:
        if result.get(field) is True:
            raise FastlaneShellBlocked(f"metric_context_builder_{field}_forbidden")


def _validate_previous_day_context_provider_result(result: Mapping[str, Any]) -> None:
    if result.get("adapter_type") != "n3_c1_n3t_previous_day_context_provider_adapter_v1":
        raise FastlaneShellBlocked("previous_day_context_provider_adapter_type_mismatch")
    forbidden_true_fields = (
        "database_written",
        "market_data_pulled",
        "runtime_execute",
        "writes_canonical_minute_bar_1m",
        "writes_n3_outbox",
        "writes_common_event_outbox",
        "touches_n4_n5_n6_outbox",
        "updates_n4_outbox",
        "scans_n5_db",
        "touches_n6",
        "full_market_fallback_used",
    )
    for field in forbidden_true_fields:
        if result.get(field) is True:
            raise FastlaneShellBlocked(f"previous_day_context_provider_{field}_forbidden")


def _validate_current_day_source_provider_result(result: Mapping[str, Any]) -> None:
    if result.get("adapter_type") != "n3_c1_scoped_current_day_source_rows_provider_adapter_v1":
        raise FastlaneShellBlocked("current_day_source_provider_adapter_type_mismatch")
    forbidden_true_fields = (
        "database_written",
        "runtime_execute",
        "writes_canonical_minute_bar_1m",
        "writes_n3_outbox",
        "writes_common_event_outbox",
        "touches_n4_n5_n6_outbox",
        "updates_n4_outbox",
        "scans_n5_db",
        "touches_n6",
        "full_market_fallback_used",
    )
    for field in forbidden_true_fields:
        if result.get(field) is True:
            raise FastlaneShellBlocked(f"current_day_source_provider_{field}_forbidden")


def _build_previous_day_context_artifact_from_postgres(
    *,
    args: argparse.Namespace,
    planned_artifact: Mapping[str, Any],
    target_hhmm: str,
    previous_context_dir: Path,
    provider_name: str,
) -> dict[str, Any]:
    active_scope = _read_optional_json_artifact(str(planned_artifact.get("input_active_scope_artifact_path") or ""))
    staging = _read_optional_json_artifact(str(planned_artifact.get("staging_artifact_path") or ""))
    if not active_scope["exists"]:
        raise FastlaneShellBlocked("active_scope_artifact_missing_for_previous_day_context_provider")
    if not staging["exists"]:
        raise FastlaneShellBlocked("staging_artifact_missing_for_previous_day_context_provider")

    scope_payload = dict(active_scope.get("payload") or {})
    staging_payload = dict(staging.get("payload") or {})
    for_trade_date = str(scope_payload.get("for_trade_date") or staging_payload.get("for_trade_date") or "")
    if not re.fullmatch(r"\d{8}", for_trade_date):
        raise FastlaneShellBlocked("previous_day_context_for_trade_date_invalid")

    expected = _expected_previous_day_context_keys(staging_payload, for_trade_date=for_trade_date)
    if not expected:
        raise FastlaneShellBlocked("previous_day_context_expected_rows_empty")

    dsn = str(os.environ.get("ASHARE_V3_POSTGRES_DSN") or "").strip()
    if not dsn:
        raise FastlaneShellBlocked("previous_day_context_dsn_required")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - import environment issue
        raise FastlaneShellBlocked("previous_day_context_psycopg_required") from exc

    with psycopg.connect(
        dsn,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    ) as conn:
        with conn.cursor() as cur:
            previous_trade_date = _fetch_previous_trade_date(cur, for_trade_date)
            rows = _fetch_previous_day_context_rows(cur, expected, for_trade_date, previous_trade_date)

    previous_context_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "artifact_type": "n3_c1_n3t_previous_day_context_v1",
        "artifact_schema_version": "v1",
        "producer_layer": "N3_market_data",
        "provider_name": provider_name,
        "for_trade_date": for_trade_date,
        "previous_trade_date": previous_trade_date,
        "target_hhmm": target_hhmm,
        "target_minute_label": _hhmm_to_minute_label(target_hhmm),
        "scope_count": int(scope_payload.get("scope_count") or 0),
        "previous_day_minute_row_count": len(rows),
        "previous_day_minute_rows": rows,
        "database_read": True,
        "database_written": False,
        "market_data_pulled": False,
        "runtime_execute": False,
        "writes_canonical_minute_bar_1m": False,
        "writes_n3_outbox": False,
        "writes_common_event_outbox": False,
        "touches_n4_n5_n6_outbox": False,
        "updates_n4_outbox": False,
        "scans_n5_db": False,
        "touches_n6": False,
        "full_market_fallback_used": False,
    }
    path = previous_context_dir / f"n3_c1_n3t_previous_day_context_v1_{for_trade_date}_{target_hhmm}.json"
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "adapter_type": "n3_c1_n3t_previous_day_context_provider_adapter_v1",
        "provider_name": provider_name,
        "artifact_written": True,
        "artifact_count": 1,
        "previous_day_minute_row_count": len(rows),
        "previous_day_context_artifacts": [
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "target_hhmm": target_hhmm,
                "artifact_type": "n3_c1_n3t_previous_day_context_v1",
            }
        ],
        "database_read": True,
        "database_written": False,
        "market_data_pulled": False,
        "runtime_execute": False,
        "writes_canonical_minute_bar_1m": False,
        "writes_n3_outbox": False,
        "writes_common_event_outbox": False,
        "touches_n4_n5_n6_outbox": False,
        "updates_n4_outbox": False,
        "scans_n5_db": False,
        "touches_n6": False,
        "full_market_fallback_used": False,
    }


def _expected_previous_day_context_keys(
    staging_artifact: Mapping[str, Any],
    *,
    for_trade_date: str,
) -> dict[str, dict[tuple[str, str], set[str]]]:
    expected: dict[str, dict[tuple[str, str], set[str]]] = {}
    for row in staging_artifact.get("closed_minute_rows") or []:
        source = dict(row or {})
        if source.get("fake_or_synthetic_row") is True:
            raise FastlaneShellBlocked("previous_day_context_fake_row_forbidden")
        asset_kind = str(source.get("asset_kind") or "")
        identity_key = str(source.get("identity_key") or "")
        physical_label = _hhmm_to_minute_label(source.get("physical_c1_label") or "")
        if asset_kind not in {"stock", "index", "board"} or not identity_key.startswith(f"{asset_kind}:"):
            raise FastlaneShellBlocked("previous_day_context_staging_scope_mismatch")
        mapped = source_close_label_for_physical_start_label(for_trade_date, physical_label)
        if mapped.get("status") != "mapped":
            raise FastlaneShellBlocked("previous_day_context_source_label_not_mappable")
        raw_label = str(mapped.get("raw_source_label") or "")
        expected.setdefault(asset_kind, {}).setdefault((identity_key, physical_label), set()).add(raw_label)
    return expected


def _fetch_previous_trade_date(cur: Any, for_trade_date: str) -> str:
    cur.execute(
        """
        SELECT prev_trade_date
        FROM common_trade_calendar
        WHERE trade_date = %s
          AND is_open = true
        LIMIT 1
        """,
        (for_trade_date,),
    )
    row = cur.fetchone()
    previous_trade_date = str((row or {}).get("prev_trade_date") or "")
    if not re.fullmatch(r"\d{8}", previous_trade_date):
        raise FastlaneShellBlocked("previous_trade_date_missing")
    return previous_trade_date


def _fetch_previous_day_context_rows(
    cur: Any,
    expected: Mapping[str, Mapping[tuple[str, str], set[str]]],
    for_trade_date: str,
    previous_trade_date: str,
) -> list[dict[str, Any]]:
    table_by_asset = {
        "stock": ("stock_minute_bar_1m", "stock_identity_key"),
        "index": ("index_minute_bar_1m", "index_identity_key"),
        "board": ("board_minute_bar_1m", "board_identity_key"),
    }
    output: list[dict[str, Any]] = []
    missing: list[str] = []
    for asset_kind, identity_to_labels in expected.items():
        table_name, identity_column = table_by_asset[asset_kind]
        identity_keys = sorted({identity for identity, _physical in identity_to_labels})
        raw_labels = sorted({label for labels in identity_to_labels.values() for label in labels})
        if not identity_keys or not raw_labels:
            continue
        cur.execute(
            f"""
            WITH candidate AS (
                SELECT
                    bar_id,
                    {identity_column} AS identity_key,
                    to_char(bar_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI') AS raw_source_label,
                    open,
                    high,
                    low,
                    close,
                    amount,
                    created_at
                FROM {table_name}
                WHERE for_trade_date = %s
                  AND trade_date = %s
                  AND is_previous_day_preload IS TRUE
                  AND {identity_column} = ANY(%s)
                  AND to_char(bar_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI') = ANY(%s)
            )
            SELECT DISTINCT ON (identity_key, raw_source_label)
                bar_id,
                identity_key,
                raw_source_label,
                open,
                high,
                low,
                close,
                amount
            FROM candidate
            ORDER BY identity_key, raw_source_label, created_at DESC, bar_id DESC
            """,
            (for_trade_date, previous_trade_date, identity_keys, raw_labels),
        )
        rows_by_key = {
            (str(row["identity_key"]), str(row["raw_source_label"])): dict(row)
            for row in cur.fetchall()
        }
        for (identity_key, physical_label), labels in sorted(identity_to_labels.items()):
            for raw_label in sorted(labels):
                row = rows_by_key.get((identity_key, raw_label))
                if not row:
                    missing.append(f"{asset_kind}:{identity_key}:{physical_label}:{raw_label}")
                    continue
                output.append(
                    {
                        "asset_kind": asset_kind,
                        "identity_key": identity_key,
                        "physical_c1_label": physical_label,
                        "raw_source_label": raw_label,
                        "open": _json_number(row.get("open")),
                        "high": _json_number(row.get("high")),
                        "low": _json_number(row.get("low")),
                        "close": _json_number(row.get("close")),
                        "amount": _json_number(row.get("amount")),
                        "source_row_ref": f"{table_name}:{row.get('bar_id')}",
                        "fake_or_synthetic_row": False,
                    }
                )
    if missing:
        raise FastlaneShellBlocked("previous_day_context_rows_missing")
    output.sort(key=lambda row: (row["asset_kind"], row["identity_key"], row["physical_c1_label"]))
    return output


def _json_number(value: Any) -> float | int | None:
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _subscription_from_plan_row(plan_row: Mapping[str, Any]) -> dict[str, Any]:
    asset_kind = str(plan_row.get("asset_kind") or "")
    identity_key = str(plan_row.get("identity_key") or "")
    parts = identity_key.split(":")
    if len(parts) < 3 or parts[0] != asset_kind:
        raise FastlaneShellBlocked("scoped_pull_plan_identity_key_mismatch")
    exchange = parts[1]
    code = parts[2]
    return {
        "subscription_id": f"fastlane:{identity_key}",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": exchange,
        "code": code,
        "display_code": code,
        "name": str(plan_row.get("name") or ""),
        "required_data_kind": "minute_bar_1m",
    }


def _current_day_source_rows_from_provider_rows(
    *,
    provider_rows: Sequence[Mapping[str, Any]],
    plan_row: Mapping[str, Any],
    for_trade_date: str,
    provider_name: str,
) -> list[dict[str, Any]]:
    required_labels = {_hhmm_to_minute_label(label) for label in plan_row.get("required_physical_labels") or []}
    rows: list[dict[str, Any]] = []
    scope = {
        field: str(plan_row.get(field) or "")
        for field in (
            "for_trade_date",
            "asset_kind",
            "identity_key",
            "direction",
            "signal_type",
            "condition_key",
            "source_trigger_event_id",
            "source_trigger_run_id",
            "scope_status",
        )
    }
    for index, provider_row in enumerate(provider_rows):
        normalized = _normalize_provider_current_day_row(provider_row, for_trade_date=for_trade_date)
        physical_label = _hhmm_to_minute_label(normalized.get("physical_c1_label") or "")
        if physical_label not in required_labels:
            continue
        output = {
            **scope,
            "physical_c1_label": physical_label,
            "raw_source_label": _hhmm_to_minute_label(normalized.get("raw_source_label") or ""),
            "source_label_policy": normalized.get("source_label_policy")
            or "source_close_label_to_physical_start_label_v1",
            "source_label_semantics": normalized.get("source_label_semantics") or "close_label",
            "physical_label_semantics": normalized.get("physical_label_semantics") or "start_label",
            "fake_or_synthetic_row": bool(normalized.get("fake_or_synthetic_row")),
            "source_provider": provider_name,
            "source_row_ref": normalized.get("source_row_ref")
            or f"{provider_name}:{scope['identity_key']}:{physical_label}:{index}",
        }
        for key in ("open", "high", "low", "close", "volume", "amount"):
            if key in normalized:
                output[key] = normalized.get(key)
        rows.append(output)
    return rows


def _normalize_provider_current_day_row(row: Mapping[str, Any], *, for_trade_date: str) -> dict[str, Any]:
    source = dict(row or {})
    if source.get("physical_c1_label") and source.get("raw_source_label"):
        return source
    try:
        return apply_source_close_label_policy_to_row(source, for_trade_date=for_trade_date)
    except Exception as exc:  # noqa: BLE001 - provider rows become contract blockers downstream.
        raise FastlaneShellBlocked(f"current_day_source_provider_row_label_mismatch:{exc}") from exc


def _validate_execute_result(result: Mapping[str, Any]) -> None:
    if result.get("full_market_fallback_used") is True:
        raise FastlaneShellBlocked("full_market_fallback_forbidden")
    if result.get("writes_n3_outbox") is True:
        raise FastlaneShellBlocked("n3_outbox_write_forbidden")
    if result.get("touches_n4_n5_n6_outbox") is True:
        raise FastlaneShellBlocked("n4_n5_n6_outbox_touch_forbidden")
    if result.get("adapter_type") in {
        "n3t_action_confirmation_metric_writer_adapter_v1",
        "n3t_action_confirmation_metric_writer_handoff_v1",
    }:
        if result.get("source_basis") != "N3T_C1_CLOSED":
            raise FastlaneShellBlocked("n3t_writer_source_basis_mismatch")
        if result.get("metric_role") != "action_confirmation":
            raise FastlaneShellBlocked("n3t_writer_metric_role_mismatch")
        if result.get("proof_consumer") != "N5":
            raise FastlaneShellBlocked("n3t_writer_proof_consumer_mismatch")
        if result.get("not_n5_final_proof") is not False:
            raise FastlaneShellBlocked("n3t_writer_not_n5_final_proof_mismatch")
        if result.get("adapter_type") == "n3t_action_confirmation_metric_writer_handoff_v1":
            if result.get("write_executed") is True or result.get("db_write_executed") is True:
                raise FastlaneShellBlocked("n3t_writer_handoff_must_not_write_db")
            if result.get("writes_enabled") is True:
                raise FastlaneShellBlocked("n3t_writer_handoff_writes_enabled_forbidden")
        if result.get("writes_common_event_outbox") is True:
            raise FastlaneShellBlocked("n3t_writer_outbox_write_forbidden")
        if result.get("writes_canonical_minute_bar_1m") is True:
            raise FastlaneShellBlocked("n3t_writer_canonical_c1_write_forbidden")
        allowed_tables = {
            "stock_n3t_action_confirmation_metric",
            "index_n3t_action_confirmation_metric",
            "board_n3t_action_confirmation_metric",
        }
        target_table_counts = dict(result.get("target_table_counts") or {})
        if not target_table_counts or any(table not in allowed_tables for table in target_table_counts):
            raise FastlaneShellBlocked("n3t_writer_target_table_forbidden")


def _write_n3t_metrics_to_postgres(
    *,
    args: argparse.Namespace,
    n3t_writer_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    dsn = os.environ.get("ASHARE_V3_POSTGRES_DSN", "").strip()
    if not dsn:
        raise FastlaneShellBlocked("n3t_writer_dsn_env_required")
    rows_by_table = _n3t_insert_rows_by_table(args=args, n3t_writer_inputs=n3t_writer_inputs)
    target_table_counts = {table: len(rows) for table, rows in rows_by_table.items()}
    inserted_rows = 0
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    json_columns = {
        "source_closed_minute_bar_ids",
        "previous_day_minute_refs",
        "blocked_reasons",
        "trace_json",
        "raw_json",
    }
    allowed_tables = set(N3T_TABLE_BY_ASSET_KIND.values())
    columns = list(N3T_WRITER_INSERT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    conflict_sql = (
        "projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version"
    )
    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for table, rows in rows_by_table.items():
                if table not in allowed_tables:
                    raise FastlaneShellBlocked("n3t_writer_target_table_forbidden")
                sql = (
                    f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({conflict_sql}) DO NOTHING"
                )
                for row in rows:
                    values = [
                        Jsonb(row.get(column)) if column in json_columns else row.get(column)
                        for column in columns
                    ]
                    cur.execute(sql, values)
                    inserted_rows += int(cur.rowcount or 0)
    return {
        "adapter_type": "n3t_action_confirmation_metric_writer_adapter_v1",
        "write_executed": True,
        "db_write_executed": True,
        "writes_enabled": True,
        "source_basis": "N3T_C1_CLOSED",
        "metric_role": "action_confirmation",
        "proof_consumer": "N5",
        "not_n5_final_proof": False,
        "n3t_writer_input_count": len(n3t_writer_inputs),
        "metric_plan_row_count": sum(target_table_counts.values()),
        "inserted_rows": inserted_rows,
        "target_table_counts": target_table_counts,
        "writes_common_event_outbox": False,
        "writes_canonical_minute_bar_1m": False,
        "touches_n4_n5_n6_outbox": False,
        "full_market_fallback_used": False,
    }


def _n3t_insert_rows_by_table(
    *,
    args: argparse.Namespace,
    n3t_writer_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    allowed_tables = set(N3T_TABLE_BY_ASSET_KIND.values())
    as_of_time = _runner_observed_at(args)
    for item in n3t_writer_inputs:
        metric_context_path = str(item.get("metric_context_artifact_path") or "")
        source = _read_optional_json_artifact(metric_context_path)
        if not source["exists"]:
            raise FastlaneShellBlocked("n3t_writer_metric_context_artifact_missing")
        plan = build_n3t_scoped_metric_from_c1_artifact_plan(
            source["payload"],
            source_artifact_path=metric_context_path,
            source_artifact_hash=str(source.get("sha256") or ""),
        )
        if plan.get("plan_status") != "planned":
            raise FastlaneShellBlocked(str(plan.get("blocked_reason") or "n3t_writer_plan_not_planned"))
        projection_run_id = str(item.get("n3t_metric_run_id") or "")
        for metric in plan.get("metric_plan_rows") or []:
            table = str(metric.get("target_table") or "")
            if table not in allowed_tables:
                raise FastlaneShellBlocked("n3t_writer_target_table_forbidden")
            row = build_n3t_action_confirmation_metric_row(
                projection_run_id=projection_run_id,
                asset_kind=str(metric.get("asset_kind") or ""),
                identity_key=str(metric.get("identity_key") or ""),
                trade_date=str(metric.get("trade_date") or ""),
                metric_minute_label=str(metric.get("metric_minute_label") or ""),
                as_of_time=as_of_time,
                metric_values=dict(metric.get("metric_values") or {}),
                source_closed_minute_bar_ids=list(metric.get("source_closed_minute_bar_ids") or []),
                previous_day_minute_refs=list(metric.get("previous_day_minute_refs") or []),
                candidate_trace={
                    "source_artifact_path": metric_context_path,
                    "source_artifact_sha256": source.get("sha256"),
                    "source_trigger_run_id": metric.get("source_trigger_run_id"),
                    "condition_key": metric.get("condition_key"),
                },
            )
            if not row.get("metric_ready"):
                raise FastlaneShellBlocked("n3t_writer_metric_row_not_ready")
            rows_by_table.setdefault(table, []).append(row)
    if not rows_by_table:
        raise FastlaneShellBlocked("n3t_writer_rows_required")
    return rows_by_table


def _build_n3t_writer_handoff_result(*, n3t_writer_inputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    target_table_counts: dict[str, int] = {}
    metric_plan_row_count = 0
    metric_context_artifacts: list[dict[str, Any]] = []
    n3t_metric_run_ids: list[str] = []
    for item in n3t_writer_inputs:
        for table, count in dict(item.get("target_table_counts") or {}).items():
            target_table_counts[str(table)] = target_table_counts.get(str(table), 0) + int(count or 0)
        metric_plan_row_count += int(item.get("metric_plan_row_count") or 0)
        metric_context_artifacts.append(
            {
                "path": item.get("metric_context_artifact_path"),
                "sha256": item.get("metric_context_artifact_sha256"),
                "target_hhmm": item.get("target_hhmm"),
                "for_trade_date": item.get("for_trade_date"),
            }
        )
        n3t_metric_run_ids.append(str(item.get("n3t_metric_run_id") or ""))

    return {
        "adapter_type": "n3t_action_confirmation_metric_writer_handoff_v1",
        "handoff_only": True,
        "write_executed": False,
        "db_write_executed": False,
        "writes_enabled": False,
        "source_basis": "N3T_C1_CLOSED",
        "metric_role": "action_confirmation",
        "proof_consumer": "N5",
        "not_n5_final_proof": False,
        "n3t_writer_input_count": len(n3t_writer_inputs),
        "metric_plan_row_count": metric_plan_row_count,
        "target_table_counts": target_table_counts,
        "n3t_metric_run_ids": n3t_metric_run_ids,
        "metric_context_artifacts": metric_context_artifacts,
        "writes_common_event_outbox": False,
        "writes_canonical_minute_bar_1m": False,
        "touches_n4_n5_n6_outbox": False,
        "full_market_fallback_used": False,
        "next_required_gate": "N3T_FASTLANE_WRITER_ADAPTER_PATCH_GATE",
    }


def _validate_args(args: argparse.Namespace) -> None:
    if args.fastlane_lane_id != FASTLANE_LANE_ID:
        raise FastlaneShellBlocked("fastlane_lane_id_mismatch")
    if args.execute and not args.user_confirmed:
        raise FastlaneShellBlocked("execute_requires_user_confirmed")
    if float(args.max_runtime_seconds) <= 0:
        raise FastlaneShellBlocked("max_runtime_seconds_must_be_positive")
    if not str(args.active_scope_artifact_dir or "").strip() and not str(args.active_scope_artifact_path or "").strip():
        raise FastlaneShellBlocked("active_scope_artifact_dir_required")
    if not str(args.output_dir or "").strip():
        raise FastlaneShellBlocked("output_dir_required")


def _apply_activation_config(args: argparse.Namespace) -> None:
    config_path = str(getattr(args, "activation_config", "") or "").strip()
    if not config_path:
        return
    config = load_fastlane_activation_config(config_path)
    if bool(getattr(args, "execute", False)):
        try:
            validate_fastlane_write_enabled_activation_authorization(config)
        except ValueError as exc:
            raise FastlaneShellBlocked(str(exc)) from exc
    args.fastlane_lane_id = args.fastlane_lane_id or FASTLANE_LANE_ID
    args.active_scope_artifact_dir = args.active_scope_artifact_dir or str(
        config.get("n5_active_scope_artifact_dir") or ""
    )
    args.output_dir = args.output_dir or str(config.get("n3_c1_n3t_artifact_dir") or "")
    args.current_day_source_artifact_dir = str(
        getattr(args, "current_day_source_artifact_dir", "")
        or config.get("n3_c1_n3t_current_day_source_artifact_dir")
        or ""
    )
    args.current_day_source_provider = str(
        getattr(args, "current_day_source_provider", "")
        or config.get("n3_c1_n3t_current_day_source_provider")
        or ""
    )
    args.metric_context_source_artifact_dir = str(
        getattr(args, "metric_context_source_artifact_dir", "")
        or config.get("n3_c1_n3t_metric_context_source_artifact_dir")
        or ""
    )
    args.previous_day_context_artifact_dir = str(
        getattr(args, "previous_day_context_artifact_dir", "")
        or config.get("n3_c1_n3t_previous_day_context_artifact_dir")
        or ""
    )
    args.previous_day_context_provider = str(
        getattr(args, "previous_day_context_provider", "")
        or config.get("n3_c1_n3t_previous_day_context_provider")
        or ""
    )
    args.n3t_writer_adapter = str(
        getattr(args, "n3t_writer_adapter", "")
        or config.get("n3_c1_n3t_n3t_writer_adapter")
        or ""
    )
    if float(args.max_runtime_seconds or 0.0) <= 0:
        args.max_runtime_seconds = float(
            (config.get("max_runtime_seconds_by_lane") or {}).get("n3_c1_n3t_action_confirmation")
            or DEFAULT_FASTLANE_MAX_RUNTIME_SECONDS
        )
    _apply_fastlane_worker_phase_gate(args, config)


def _discover_requested_active_scope_artifacts(args: argparse.Namespace) -> list[dict[str, Any]]:
    path_text = str(getattr(args, "active_scope_artifact_path", "") or "").strip()
    if path_text:
        return _discover_single_active_scope_artifact(Path(path_text))
    return _discover_active_scope_artifacts(Path(args.active_scope_artifact_dir))


def _apply_fastlane_worker_phase_gate(args: argparse.Namespace, config: Mapping[str, Any]) -> None:
    session_context = config.get("session_context") or {}
    try:
        session_context = resolve_fastlane_runtime_session_context(config)
    except ValueError as exc:
        raise FastlaneShellBlocked(str(exc)) from exc
    if not isinstance(session_context, Mapping) or not session_context:
        return
    classification = classify_fastlane_session_phase(
        for_trade_date=str(config.get("for_trade_date") or ""),
        trigger_time=str(session_context.get("trigger_time") or session_context.get("current_exchange_time") or ""),
        current_exchange_time=str(session_context.get("current_exchange_time") or ""),
        trade_calendar_is_open=bool(session_context.get("trade_calendar_is_open")),
    )
    decision = resolve_fastlane_active_worker_decision(
        lane_key="n3_c1_n3t_action_confirmation",
        session_phase=str(classification["phase"]),
        formal_trigger_matched_available=bool(session_context.get("formal_trigger_matched_available")),
        closed_minute_available=bool(session_context.get("closed_minute_available")),
        matching_n3t_metric_available=bool(session_context.get("matching_n3t_metric_available")),
    )
    args.fastlane_session_phase = classification["phase"]
    args.fastlane_active_worker_decision = decision
    args.fastlane_current_exchange_time = str(session_context.get("current_exchange_time") or "")
    if not decision["writes_enabled_allowed"]:
        raise FastlaneShellBlocked(str(decision.get("blocked_reason") or decision.get("worker_mode") or "write_not_allowed"))


def _discover_active_scope_artifacts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if not path.is_dir():
        raise FastlaneShellBlocked("active_scope_artifact_dir_must_be_directory")
    artifacts: list[dict[str, Any]] = []
    for artifact_path in sorted(path.glob("*.json")):
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FastlaneShellBlocked(f"active_scope_artifact_json_invalid:{artifact_path}") from exc
        if payload.get("artifact_type") != INPUT_ARTIFACT_TYPE:
            continue
        artifacts.append(
            {
                "path": str(artifact_path),
                "artifact_type": INPUT_ARTIFACT_TYPE,
                "for_trade_date": str(payload.get("for_trade_date") or ""),
                "scope_count": int(payload.get("scope_count") or 0),
                "source_trigger_run_id": str(payload.get("source_trigger_run_id") or ""),
                "action_run_id": str(payload.get("action_run_id") or ""),
                "source_run_hash": str(payload.get("source_run_hash") or ""),
                "source_run_namespace": str(payload.get("source_run_namespace") or ""),
                "full_market_fallback_allowed": bool(payload.get("full_market_fallback_allowed")),
                "n3_scans_n5_internals": bool(payload.get("n3_scans_n5_internals")),
            }
        )
    return artifacts


def _discover_single_active_scope_artifact(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if not path.is_file():
        raise FastlaneShellBlocked("active_scope_artifact_path_must_be_file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FastlaneShellBlocked(f"active_scope_artifact_json_invalid:{path}") from exc
    if payload.get("artifact_type") != INPUT_ARTIFACT_TYPE:
        raise FastlaneShellBlocked("active_scope_artifact_type_mismatch")
    return [
        {
            "path": str(path),
            "artifact_type": INPUT_ARTIFACT_TYPE,
            "for_trade_date": str(payload.get("for_trade_date") or ""),
            "scope_count": int(payload.get("scope_count") or 0),
            "source_trigger_run_id": str(payload.get("source_trigger_run_id") or ""),
            "action_run_id": str(payload.get("action_run_id") or ""),
            "source_run_hash": str(payload.get("source_run_hash") or ""),
            "source_run_namespace": str(payload.get("source_run_namespace") or ""),
            "full_market_fallback_allowed": bool(payload.get("full_market_fallback_allowed")),
            "n3_scans_n5_internals": bool(payload.get("n3_scans_n5_internals")),
        }
    ]


def _materialize_missing_scoped_pull_plans(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    observed_at: Any,
) -> None:
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        target_hhmm = context["target_hhmm"]
        pull_plan_path = output_dir / f"n3_c1_scoped_current_day_pull_plan_v1_{context['namespace_token']}_fastlane.json"
        if pull_plan_path.exists():
            continue
        source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        if not source["exists"]:
            continue
        plan = build_n3_c1_scoped_current_day_pull_plan(
            source["payload"],
            target_minute_label=_hhmm_to_minute_label(target_hhmm),
            observed_at=observed_at,
            source_artifact_path=str(artifact.get("path") or ""),
            source_artifact_hash=str(source.get("sha256") or ""),
        )
        pull_plan_path.parent.mkdir(parents=True, exist_ok=True)
        pull_plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _split_closed_active_scope_artifacts(
    artifacts: Sequence[Mapping[str, Any]],
    *,
    current_exchange_time: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    executable: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    for artifact in artifacts:
        item = dict(artifact)
        context = _infer_scope_context(item)
        if _target_hhmm_closed(context["target_hhmm"], current_exchange_time=current_exchange_time):
            executable.append(item)
        else:
            item["blocked_reason"] = "target_minute_not_closed"
            item["current_exchange_time"] = str(current_exchange_time)
            item["target_hhmm"] = context["target_hhmm"]
            waiting.append(item)
    return executable, waiting


def _target_hhmm_closed(target_hhmm: str, *, current_exchange_time: str) -> bool:
    target = _hhmm_int(target_hhmm)
    current = _hhmm_int(current_exchange_time)
    if target <= 0 or current <= 0:
        return False
    required = target if target >= 1500 else _add_hhmm_minutes(target, 1)
    return current >= required


def _add_hhmm_minutes(hhmm: int, minutes: int) -> int:
    hour = hhmm // 100
    minute = hhmm % 100
    total = hour * 60 + minute + minutes
    return (total // 60) * 100 + (total % 60)


def _hhmm_int(value: Any) -> int:
    text = str(value or "").strip()
    if re.fullmatch(r"[0-2][0-9][0-5][0-9]", text):
        return int(text)
    try:
        return int(datetime.fromisoformat(text).strftime("%H%M"))
    except ValueError:
        pass
    match = re.search(r"(?:^|[^0-9])([0-2][0-9]):([0-5][0-9])", text)
    if not match:
        return 0
    return int(match.group(1) + match.group(2))


def _materialize_missing_scoped_current_day_staging_artifacts(
    *,
    args: argparse.Namespace,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    observed_at: Any,
) -> None:
    source_dir_text = str(getattr(args, "current_day_source_artifact_dir", "") or "").strip()
    if not source_dir_text:
        return
    source_dir = Path(source_dir_text)
    if not source_dir.exists() or not source_dir.is_dir():
        raise FastlaneShellBlocked("current_day_source_artifact_dir_missing")
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        target_hhmm = context["target_hhmm"]
        namespace_token = context["namespace_token"]
        source_run_hash = context["source_run_hash"]
        pull_plan_path = output_dir / f"n3_c1_scoped_current_day_pull_plan_v1_{namespace_token}_fastlane.json"
        staging_path = (
            output_dir
            / "current_day_staging"
            / f"n3_c1_scoped_current_day_staging_v1_{namespace_token}_fastlane.json"
        )
        if staging_path.exists():
            continue
        active_scope = _read_optional_json_artifact(str(artifact.get("path") or ""))
        pull_plan = _read_optional_json_artifact(str(pull_plan_path))
        source_rows = _find_current_day_source_rows_artifact(
            source_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
        )
        if not active_scope["exists"]:
            raise FastlaneShellBlocked("active_scope_artifact_missing")
        if not pull_plan["exists"]:
            raise FastlaneShellBlocked("scoped_pull_plan_missing_for_staging")
        if not source_rows:
            continue
        staging = build_n3_c1_scoped_current_day_staging_artifact(
            active_scope["payload"],
            pull_plan_artifact=pull_plan["payload"],
            source_rows_artifact=source_rows["payload"],
            target_hhmm=target_hhmm,
            observed_at=observed_at,
            source_pull_plan_path=str(pull_plan.get("path") or ""),
            source_pull_plan_hash=str(pull_plan.get("sha256") or ""),
            source_rows_artifact_path=str(source_rows.get("path") or ""),
            source_rows_artifact_hash=str(source_rows.get("sha256") or ""),
        )
        if staging.get("artifact_status") != "passed":
            raise FastlaneShellBlocked(str(staging.get("blocked_reason") or "current_day_staging_contract_mismatch"))
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        staging_path.write_text(
            json.dumps(staging, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _runner_observed_at(args: argparse.Namespace) -> str:
    configured = str(getattr(args, "fastlane_current_exchange_time", "") or "").strip()
    if configured:
        return configured
    return datetime.now().astimezone().isoformat()


def _build_scoped_executor_plan(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    plan_status: str,
    blocked_reason: str | None,
) -> dict[str, Any]:
    planned_artifacts: list[dict[str, Any]] = []
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        target_hhmm = context["target_hhmm"]
        for_trade_date = context["for_trade_date"]
        namespace_token = context["namespace_token"]
        source_run_hash = context["source_run_hash"]
        planned_artifact = {
            "input_active_scope_artifact_path": str(artifact.get("path") or ""),
            "scope_count": int(artifact.get("scope_count") or 0),
            "target_hhmm": target_hhmm,
            "for_trade_date": for_trade_date,
            "source_run_hash": source_run_hash,
            "namespace_token": namespace_token,
            "pull_plan_path": str(output_dir / f"n3_c1_scoped_current_day_pull_plan_v1_{namespace_token}_fastlane.json"),
            "staging_artifact_path": str(
                output_dir / "current_day_staging" / f"n3_c1_scoped_current_day_staging_v1_{namespace_token}_fastlane.json"
            ),
            "metric_context_artifact_path": str(
                output_dir
                / "metric_context"
                / f"n3_c1_scoped_closed_1m_artifact_v1_{namespace_token}_fastlane_raw_prevday_c1_amount_v1.json"
            ),
            "n3t_metric_run_id": (
                f"n3t_action_confirmation_metric_{for_trade_date}_until_{target_hhmm}__"
                f"fastlane_sr_{source_run_hash}_raw_prevday_c1_amount_v1"
            ),
            "required_executor_components": [
                "scoped_c1_pull_plan_builder",
                "scoped_c1_pull_staging_writer",
                "metric_context_artifact_builder",
                "n3t_action_confirmation_metric_writer",
            ],
        }
        planned_artifact["component_readiness"] = _local_component_readiness(planned_artifact)
        planned_artifacts.append(planned_artifact)
    return {
        "plan_type": "n3_c1_n3t_fastlane_scoped_executor_plan_v1",
        "plan_status": plan_status,
        "blocked_reason": blocked_reason,
        "planned_artifact_count": len(planned_artifacts),
        "planned_artifacts": planned_artifacts,
        "side_effects": {
            "writes_db": False,
            "pulls_market_data": False,
            "writes_canonical_minute_bar_1m": False,
            "writes_outbox": False,
            "updates_n4_outbox": False,
            "touches_n6": False,
        },
    }


def _local_component_readiness(planned_artifact: Mapping[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    pull_plan = _read_optional_json_artifact(planned_artifact["pull_plan_path"])
    staging = _read_optional_json_artifact(planned_artifact["staging_artifact_path"])
    metric = _read_optional_json_artifact(planned_artifact["metric_context_artifact_path"])
    n3t_writer_plan_summary: dict[str, Any] | None = None

    if not pull_plan["exists"]:
        status = "waiting_for_scoped_c1_plan"
    elif not staging["exists"]:
        status = "waiting_for_scoped_pull_staging"
    elif not metric["exists"]:
        status = "waiting_for_metric_context_artifact"
    else:
        status = "metric_context_ready_for_n3t_execute_gate"

    if pull_plan["exists"]:
        payload = pull_plan["payload"]
        if payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
            violations.append("pull_plan_artifact_type")
        if payload.get("plan_status") != "planned":
            violations.append("pull_plan_status")
        if payload.get("full_market_fallback_used") is True:
            violations.append("pull_plan_full_market_fallback")
    if staging["exists"]:
        payload = staging["payload"]
        if payload.get("artifact_type") != "n3_c1_scoped_current_day_staging_v1":
            violations.append("staging_artifact_type")
        if payload.get("artifact_status") != "passed":
            violations.append("staging_artifact_status")
        if payload.get("full_market_fallback_used") is True:
            violations.append("staging_full_market_fallback")
        for key in ("database_written", "writes_canonical_minute_bar_1m", "writes_n3_outbox"):
            if payload.get(key) is True:
                violations.append(f"staging_{key}")
    if metric["exists"]:
        payload = metric["payload"]
        if payload.get("artifact_type") != "n3_c1_scoped_closed_1m_artifact_v1":
            violations.append("metric_context_artifact_type")
        if payload.get("artifact_status") != "planned":
            violations.append("metric_context_artifact_status")
        if payload.get("metric_context_status") != "ready":
            violations.append("metric_context_status")
        for key in ("full_market_fallback_used", "database_written", "runtime_execute", "writes_n3_outbox"):
            if payload.get(key) is True:
                violations.append(f"metric_context_{key}")
        n3t_writer_plan_summary = _n3t_writer_plan_summary(
            metric_payload=payload,
            source_artifact_path=str(planned_artifact["metric_context_artifact_path"]),
            source_artifact_hash=str(metric.get("sha256") or ""),
        )
        if n3t_writer_plan_summary.get("plan_status") not in {"planned", "noop"}:
            violations.append(
                "n3t_writer_plan:"
                + str(n3t_writer_plan_summary.get("blocked_reason") or "contract_mismatch")
            )

    if violations:
        status = "blocked_local_component_contract_mismatch"

    target_hhmm = str(planned_artifact.get("target_hhmm") or "unknown")
    return {
        "status": status,
        "next_required_gate": _next_required_gate(status, target_hhmm),
        "violations": violations,
        "pull_plan_exists": pull_plan["exists"],
        "staging_artifact_exists": staging["exists"],
        "metric_context_artifact_exists": metric["exists"],
        "pull_plan_sha256": pull_plan.get("sha256"),
        "staging_artifact_sha256": staging.get("sha256"),
        "metric_context_artifact_sha256": metric.get("sha256"),
        "scope_count": int((metric["payload"] or staging["payload"] or pull_plan["payload"] or {}).get("scope_count") or 0),
        "closed_minute_row_count": int((staging["payload"] or {}).get("closed_minute_row_count") or 0),
        "metric_context_count": int((metric["payload"] or {}).get("metric_context_count") or 0),
        "n3t_writer_plan_summary": n3t_writer_plan_summary if metric["exists"] else None,
        "side_effects": {
            "writes_db": False,
            "pulls_market_data": False,
            "writes_canonical_minute_bar_1m": False,
            "writes_outbox": False,
            "updates_n4_outbox": False,
            "touches_n6": False,
        },
    }


def _n3t_writer_plan_summary(
    *,
    metric_payload: Mapping[str, Any],
    source_artifact_path: str,
    source_artifact_hash: str,
) -> dict[str, Any]:
    plan = build_n3t_scoped_metric_from_c1_artifact_plan(
        metric_payload,
        source_artifact_path=source_artifact_path,
        source_artifact_hash=source_artifact_hash,
    )
    table_counts: dict[str, int] = {}
    for row in plan.get("metric_plan_rows") or []:
        table = str(row.get("target_table") or "")
        table_counts[table] = table_counts.get(table, 0) + 1
    return {
        "plan_type": plan.get("plan_type"),
        "plan_status": plan.get("plan_status"),
        "blocked_reason": plan.get("blocked_reason"),
        "source_basis": plan.get("source_basis"),
        "metric_role": plan.get("metric_role"),
        "proof_consumer": plan.get("proof_consumer"),
        "not_n5_final_proof": plan.get("not_n5_final_proof"),
        "target_tables": list(plan.get("target_tables") or []),
        "target_table_counts": table_counts,
        "metric_plan_row_count": len(plan.get("metric_plan_rows") or []),
        "scope_count": int(plan.get("scope_count") or 0),
        "side_effects": dict(plan.get("side_effects") or {}),
    }


def _n3t_writer_inputs_from_plan(scoped_executor_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    for artifact in scoped_executor_plan.get("planned_artifacts") or []:
        readiness = dict(artifact.get("component_readiness") or {})
        writer_plan = dict(readiness.get("n3t_writer_plan_summary") or {})
        if readiness.get("status") != "metric_context_ready_for_n3t_execute_gate":
            continue
        if writer_plan.get("plan_status") != "planned":
            continue
        inputs.append(
            {
                "target_hhmm": artifact.get("target_hhmm"),
                "for_trade_date": artifact.get("for_trade_date"),
                "n3t_metric_run_id": artifact.get("n3t_metric_run_id"),
                "metric_context_artifact_path": artifact.get("metric_context_artifact_path"),
                "metric_context_artifact_sha256": readiness.get("metric_context_artifact_sha256"),
                "metric_plan_row_count": writer_plan.get("metric_plan_row_count"),
                "target_table_counts": dict(writer_plan.get("target_table_counts") or {}),
                "source_basis": writer_plan.get("source_basis"),
                "metric_role": writer_plan.get("metric_role"),
                "proof_consumer": writer_plan.get("proof_consumer"),
                "not_n5_final_proof": writer_plan.get("not_n5_final_proof"),
            }
        )
    return inputs


def _read_optional_json_artifact(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        return {"exists": False, "path": str(path), "payload": {}}
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise FastlaneShellBlocked(f"local_component_artifact_json_invalid:{path}") from exc
    return {
        "exists": True,
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "payload": payload,
    }


def _next_required_gate(status: str, target_hhmm: str) -> str:
    if status == "waiting_for_scoped_c1_plan":
        return f"N3_C1_N3T_FASTLANE_{target_hhmm}_SCOPED_C1_PLAN_GATE"
    if status == "waiting_for_scoped_pull_staging":
        return f"N3_C1_N3T_FASTLANE_{target_hhmm}_SCOPED_PULL_EXECUTE_GATE"
    if status == "waiting_for_metric_context_artifact":
        return f"N3_C1_N3T_FASTLANE_{target_hhmm}_METRIC_CONTEXT_ARTIFACT_GATE"
    if status == "metric_context_ready_for_n3t_execute_gate":
        return f"N3T_FASTLANE_{target_hhmm}_SCOPED_METRIC_EXECUTE_GATE"
    return f"N3_C1_N3T_FASTLANE_{target_hhmm}_LOCAL_COMPONENT_REVIEW_GATE"


def _infer_scope_context(artifact: Mapping[str, Any]) -> dict[str, str]:
    search_text = " ".join(
        str(artifact.get(key) or "")
        for key in ("path", "source_trigger_run_id", "action_run_id", "for_trade_date")
    )
    hhmm_match = re.search(r"until_([0-2][0-9][0-5][0-9])", search_text)
    if not hhmm_match:
        hhmm_match = re.search(r"_([0-2][0-9][0-5][0-9])(?:_|\\.)", search_text)
    date_match = re.search(r"(20[0-9]{6})", search_text)
    target_hhmm = hhmm_match.group(1) if hhmm_match else "unknown"
    for_trade_date = str(artifact.get("for_trade_date") or (date_match.group(1) if date_match else "unknown"))
    namespace = build_fastlane_source_run_namespace(
        for_trade_date=for_trade_date,
        source_trigger_run_id=str(artifact.get("source_trigger_run_id") or ""),
        action_run_id=str(artifact.get("action_run_id") or ""),
        target_hhmm=target_hhmm,
    )
    source_run_hash = str(artifact.get("source_run_hash") or namespace["source_run_hash"])
    namespace_token = str(artifact.get("source_run_namespace") or namespace["token"])
    return {
        "target_hhmm": namespace["target_hhmm"],
        "for_trade_date": namespace["for_trade_date"],
        "source_run_hash": source_run_hash,
        "namespace_token": namespace_token,
    }


def _normalize_fastlane_scope_target_hhmm(target_hhmm: str) -> str:
    target = _hhmm_int(target_hhmm)
    if 925 <= target < 930:
        return "0930"
    return target_hhmm


def _hhmm_to_minute_label(value: Any) -> str:
    text = str(value or "")
    if re.fullmatch(r"\d{4}", text):
        return f"{text[:2]}:{text[2:]}"
    return text


def _boundary() -> dict[str, bool]:
    return {
        "reads_only_explicit_n5_active_scope_artifacts": True,
        "scans_n5_db": False,
        "writes_db": False,
        "pulls_market_data": False,
        "writes_canonical_minute_bar_1m": False,
        "writes_n3_outbox": False,
        "touches_n4_n5_n6_outbox": False,
        "uses_a1_cumulative_authority": False,
        "uses_n3p_b1_b2_or_realtime_metric": False,
        "full_market_fallback": False,
        "launchd_loaded_or_started": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    scheduler_quiet = _scheduler_quiet_requested(argv)
    manifest = run_n3_c1_n3t_action_confirmation_fastlane_once(argv)
    if scheduler_quiet and _is_scheduler_phase_noop(manifest):
        return 0
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    return 2 if str(manifest.get("verdict") or "").startswith("BLOCKED") else 0


def _scheduler_quiet_requested(argv: Sequence[str] | None) -> bool:
    values = list(sys.argv[1:] if argv is None else argv)
    return "--scheduler-quiet" in values


def _is_scheduler_phase_noop(manifest: Mapping[str, Any]) -> bool:
    if not str(manifest.get("verdict") or "").startswith("BLOCKED"):
        return False
    if manifest.get("writes_enabled") is not False:
        return False
    reason = str(manifest.get("blocked_reason") or "")
    return reason in {
        "closed_day_or_non_trading",
        "pre_open_before_0925_no_write",
        "first_closed_minute_not_available",
        "closed_minute_not_available",
        "target_minute_not_closed",
        "matching_n3t_metric_missing",
        "fastlane write-enabled active plan requires session_context or session_context_policy",
        "fastlane write-enabled active plan requires session_context_policy.trade_calendar_is_open",
        "fastlane write-enabled active plan requires active_worker_policy_review_ref",
        "fastlane active_worker_policy_review_ref not ready",
        "fastlane active_worker_policy_review_ref for_trade_date mismatch",
        "active worker policy review not ready",
        "active worker policy review not ready: manual_gate_required",
        "active worker policy review not ready: blockers_or_waiting_reasons",
        "active worker policy review chain_backlog mismatch",
        "fastlane active_worker_policy_review_path not readable",
    }


def _scheduler_noop_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    fastlane = manifest.get("fastlane") if isinstance(manifest.get("fastlane"), Mapping) else {}
    return {
        "verdict": "FASTLANE_SCHEDULER_NOOP",
        "blocked_reason": str(manifest.get("blocked_reason") or ""),
        "session_phase": str(fastlane.get("session_phase") or ""),
        "scheduler_quiet": True,
        "writes_enabled": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
