#!/usr/bin/env python3
"""Run one N4 replay bounded worker invocation.

This wrapper is orchestration only. Its active child path is the existing
run_trigger_action_confirmation_metric_once.py replay execute runner. It does
not start the N4 bounded poll worker, consume N3 outbox events, write N5/N6
facts, or perform rollback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ashare_v3.runtime.bounded_worker_control import (
    BoundedResult,
    SingletonLockHeld,
    acquire_global_chain_lock,
    atomic_write_json,
    build_invocation_id,
    build_phase1_realtime_chain_lock_path,
    build_run_id,
    check_stop_file,
    deadline_from_now,
    remaining_deadline_seconds,
    result_to_exit_code,
    run_child_with_timeout,
)


WORKER_NAME = "n4_replay_bounded_worker"
ACTIVE_PATH = "run_trigger_action_confirmation_metric_once.py"
ACTIVE_CHILD_SCRIPT = "scripts/run_trigger_action_confirmation_metric_once.py"
DEFERRED_WORKER_PATHS = (
    "src/ashare_v3/trigger/worker_consumer.py",
    "scripts/run_n4_worker_bounded_poll_once.py",
    "N3 outbox event consumer",
)
IMPLICIT_LINEAGE_VALUES = {"latest", "active", "fallback", "auto", "auto-resolve", "auto_resolve"}
TRIGGER_EVENT_TYPES = ("TriggerMatched", "TriggerStateChanged", "TriggerPendingMarketData")
HINT_CONDITION_KEYS = {"BUY_HINT", "SELL_HINT"}
DEFAULT_MAX_CANDIDATES = 10_000
DEFAULT_MAX_RUNTIME_SECONDS = 120.0
PRODUCTION_SCOPE_COVERAGE_PROVIDER = "n4_context_vs_n3_action_confirmation_metric_db"


class N4ReplayBlocked(RuntimeError):
    """Raised when wrapper preconditions fail before the replay child starts."""


@dataclass(frozen=True)
class ExplicitLineage:
    for_trade_date: str
    source_metric_run_id: str
    projection_run_id: str
    context_run_id: str
    source_condition_run_id: str
    source_subscription_run_id: str
    source_snapshot_run_id: str
    trigger_run_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "for_trade_date": self.for_trade_date,
            "source_metric_run_id": self.source_metric_run_id,
            "projection_run_id": self.projection_run_id,
            "context_run_id": self.context_run_id,
            "source_condition_run_id": self.source_condition_run_id,
            "source_subscription_run_id": self.source_subscription_run_id,
            "source_snapshot_run_id": self.source_snapshot_run_id,
            "trigger_run_id": self.trigger_run_id,
        }


@dataclass(frozen=True)
class N4BoundedContext:
    repo_root: Path
    lineage: ExplicitLineage
    invocation_id: str
    wrapper_run_id: str
    lock_path: Path
    deadline: datetime | None
    dsn: str
    status_json: Path
    manifest_json: Path
    rollback_sql_path: Path
    child_dry_run_json_path: Path
    child_dry_run_markdown_path: Path
    child_dry_run_preflight_json_path: Path
    child_dry_run_preflight_markdown_path: Path
    child_contract_json_path: Path
    child_contract_markdown_path: Path
    child_final_preflight_json_path: Path
    child_final_preflight_markdown_path: Path
    child_report_json_path: Path
    child_report_markdown_path: Path
    docs_root: Path
    sql_root: Path
    python_executable: str

    @property
    def input_run_ids(self) -> dict[str, str]:
        return {
            "source_metric_run_id": self.lineage.source_metric_run_id,
            "projection_run_id": self.lineage.projection_run_id,
            "context_run_id": self.lineage.context_run_id,
            "source_condition_run_id": self.lineage.source_condition_run_id,
            "source_subscription_run_id": self.lineage.source_subscription_run_id,
            "source_snapshot_run_id": self.lineage.source_snapshot_run_id,
        }

    @property
    def child_artifact_paths(self) -> dict[str, str]:
        return {
            "dry_run_json_path": str(self.child_dry_run_json_path),
            "dry_run_markdown_path": str(self.child_dry_run_markdown_path),
            "dry_run_preflight_json_path": str(self.child_dry_run_preflight_json_path),
            "dry_run_preflight_markdown_path": str(self.child_dry_run_preflight_markdown_path),
            "contract_json_path": str(self.child_contract_json_path),
            "contract_markdown_path": str(self.child_contract_markdown_path),
            "final_preflight_json_path": str(self.child_final_preflight_json_path),
            "final_preflight_markdown_path": str(self.child_final_preflight_markdown_path),
            "execute_report_json_path": str(self.child_report_json_path),
            "execute_report_markdown_path": str(self.child_report_markdown_path),
            "rollback_sql_path": str(self.rollback_sql_path),
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one N4 replay bounded worker invocation.")
    parser.add_argument("--for-trade-date")
    parser.add_argument("--source-metric-run-id")
    parser.add_argument("--projection-run-id")
    parser.add_argument("--context-run-id")
    parser.add_argument("--source-condition-run-id")
    parser.add_argument("--source-subscription-run-id")
    parser.add_argument("--source-snapshot-run-id")
    parser.add_argument("--trigger-run-id")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", ""))
    parser.add_argument("--status-json")
    parser.add_argument("--manifest-json")
    parser.add_argument("--rollback-sql-path")
    parser.add_argument("--stop-file", default="")
    parser.add_argument("--max-runtime-seconds", type=float, default=DEFAULT_MAX_RUNTIME_SECONDS)
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def build_explicit_lineage(args: argparse.Namespace) -> ExplicitLineage:
    lineage = ExplicitLineage(
        for_trade_date=_validate_trade_date(_required_arg(args, "for_trade_date")),
        source_metric_run_id=_validate_explicit_run_id("source_metric_run_id", _required_arg(args, "source_metric_run_id")),
        projection_run_id=_validate_explicit_run_id("projection_run_id", _required_arg(args, "projection_run_id")),
        context_run_id=_validate_explicit_run_id("context_run_id", _required_arg(args, "context_run_id")),
        source_condition_run_id=_validate_explicit_run_id(
            "source_condition_run_id", _required_arg(args, "source_condition_run_id")
        ),
        source_subscription_run_id=_validate_explicit_run_id(
            "source_subscription_run_id", _required_arg(args, "source_subscription_run_id")
        ),
        source_snapshot_run_id=_validate_explicit_run_id(
            "source_snapshot_run_id", _required_arg(args, "source_snapshot_run_id")
        ),
        trigger_run_id=_validate_explicit_run_id("trigger_run_id", _required_arg(args, "trigger_run_id")),
    )
    if lineage.source_metric_run_id != lineage.projection_run_id:
        raise N4ReplayBlocked("source_metric_run_id must equal projection_run_id")
    return lineage


def build_n4_bounded_context(
    lineage: ExplicitLineage,
    args: argparse.Namespace,
    *,
    repo_root: str | Path | None = None,
    now: datetime | None = None,
) -> N4BoundedContext:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    docs_root = _resolve_repo_path(root, _required_arg(args, "docs_root"))
    sql_root = _resolve_repo_path(root, _required_arg(args, "sql_root"))
    invocation_id = build_invocation_id()
    wrapper_run_id = build_run_id(WORKER_NAME, lineage.for_trade_date, invocation_id=invocation_id, now=now)
    rollback_sql_path = _resolve_repo_path(root, _required_arg(args, "rollback_sql_path"))
    child_stem = f"N4_REPLAY_BOUNDED_WORKER_{_safe_artifact_name(lineage.trigger_run_id)}"
    return N4BoundedContext(
        repo_root=root,
        lineage=lineage,
        invocation_id=invocation_id,
        wrapper_run_id=wrapper_run_id,
        lock_path=build_phase1_realtime_chain_lock_path(root, lineage.for_trade_date),
        deadline=deadline_from_now(args.max_runtime_seconds, now=now),
        dsn=str(args.dsn or ""),
        status_json=_resolve_repo_path(root, _required_arg(args, "status_json")),
        manifest_json=_resolve_repo_path(root, _required_arg(args, "manifest_json")),
        rollback_sql_path=rollback_sql_path,
        child_dry_run_json_path=docs_root / f"{child_stem}_child_dry_run.json",
        child_dry_run_markdown_path=docs_root / f"{child_stem}_child_dry_run.md",
        child_dry_run_preflight_json_path=docs_root / f"{child_stem}_child_dry_run_preflight.json",
        child_dry_run_preflight_markdown_path=docs_root / f"{child_stem}_child_dry_run_preflight.md",
        child_contract_json_path=docs_root / f"{child_stem}_child_execute_contract.json",
        child_contract_markdown_path=docs_root / f"{child_stem}_child_execute_contract.md",
        child_final_preflight_json_path=docs_root / f"{child_stem}_child_execute_final_preflight.json",
        child_final_preflight_markdown_path=docs_root / f"{child_stem}_child_execute_final_preflight.md",
        child_report_json_path=docs_root / f"{child_stem}_child_report.json",
        child_report_markdown_path=docs_root / f"{child_stem}_child_report.md",
        docs_root=docs_root,
        sql_root=sql_root,
        python_executable=str(args.python_executable or sys.executable),
    )


def build_replay_child_command(context: N4BoundedContext, args: argparse.Namespace) -> list[str]:
    assert_child_artifact_paths_explicit(context)
    child_script = context.repo_root / ACTIVE_CHILD_SCRIPT
    return [
        context.python_executable,
        str(child_script),
        "--dsn",
        context.dsn,
        "--execute-run-id",
        context.lineage.trigger_run_id,
        "--trigger-context-run-id",
        context.lineage.context_run_id,
        "--projection-run-id",
        context.lineage.projection_run_id,
        "--source-condition-run-id",
        context.lineage.source_condition_run_id,
        "--source-subscription-run-id",
        context.lineage.source_subscription_run_id,
        "--source-snapshot-run-id",
        context.lineage.source_snapshot_run_id,
        "--for-trade-date",
        context.lineage.for_trade_date,
        "--dry-run-json-path",
        str(context.child_dry_run_json_path),
        "--dry-run-preflight-json-path",
        str(context.child_dry_run_preflight_json_path),
        "--contract-json-path",
        str(context.child_contract_json_path),
        "--contract-markdown-path",
        str(context.child_contract_markdown_path),
        "--final-preflight-json-path",
        str(context.child_final_preflight_json_path),
        "--final-preflight-markdown-path",
        str(context.child_final_preflight_markdown_path),
        "--rollback-sql-path",
        str(context.rollback_sql_path),
        "--execute-report-json-path",
        str(context.child_report_json_path),
        "--execute-report-markdown-path",
        str(context.child_report_markdown_path),
        "--execute",
        "--user-confirmed",
        "--json",
    ]


def prepare_replay_child_artifacts(context: N4BoundedContext) -> dict[str, Any]:
    """Generate the child dry-run/contract artifacts under this wrapper's roots."""

    assert_child_artifact_paths_explicit(context)
    from ashare_v3.trigger.action_confirmation_metric_matcher import (
        build_action_confirmation_metric_business_execute_contract,
        build_action_confirmation_metric_execute_final_preflight,
        build_action_confirmation_metric_execute_rollback_sql,
        capture_action_confirmation_metric_execute_baseline,
        format_action_confirmation_metric_business_execute_contract,
        format_action_confirmation_metric_execute_final_preflight,
        run_action_confirmation_metric_dry_run,
        write_json,
        write_text,
    )

    dry_run_report, dry_run_preflight = run_action_confirmation_metric_dry_run(
        dsn=context.dsn,
        trigger_context_run_id=context.lineage.context_run_id,
        projection_run_id=context.lineage.projection_run_id,
        source_condition_run_id=context.lineage.source_condition_run_id,
        source_subscription_run_id=context.lineage.source_subscription_run_id,
        source_snapshot_run_id=context.lineage.source_snapshot_run_id,
        for_trade_date=context.lineage.for_trade_date,
        json_report_path=str(context.child_dry_run_json_path),
        markdown_report_path=str(context.child_dry_run_markdown_path),
        preflight_json_path=str(context.child_dry_run_preflight_json_path),
        preflight_markdown_path=str(context.child_dry_run_preflight_markdown_path),
    )
    write_text(
        str(context.rollback_sql_path),
        build_action_confirmation_metric_execute_rollback_sql(context.lineage.trigger_run_id),
    )
    contract = build_action_confirmation_metric_business_execute_contract(
        dry_run_report,
        dry_run_preflight,
        execute_run_id=context.lineage.trigger_run_id,
        rollback_sql_path=str(context.rollback_sql_path),
        business_execute_runner_ready=True,
        business_execute_runner=ACTIVE_CHILD_SCRIPT,
    )
    baseline = capture_action_confirmation_metric_execute_baseline(context.dsn, context.lineage.trigger_run_id)
    final_preflight = build_action_confirmation_metric_execute_final_preflight(
        dry_run_report,
        dry_run_preflight,
        contract,
        baseline_summary=baseline,
        rollback_sql_exists=context.rollback_sql_path.exists(),
    )
    write_json(str(context.child_contract_json_path), contract)
    write_text(
        str(context.child_contract_markdown_path),
        format_action_confirmation_metric_business_execute_contract(contract),
    )
    write_json(str(context.child_final_preflight_json_path), final_preflight)
    write_text(
        str(context.child_final_preflight_markdown_path),
        format_action_confirmation_metric_execute_final_preflight(final_preflight),
    )
    lineage_validation = validate_child_artifact_lineage(context)
    if final_preflight.get("result") != "PREFLIGHT_PASS":
        blockers = final_preflight.get("blockers") or []
        raise N4ReplayBlocked(f"child_final_preflight_blocked:{blockers}")
    return {
        "prepared": True,
        "dry_run_result": dry_run_report.get("result"),
        "dry_run_preflight_result": dry_run_preflight.get("result"),
        "contract_result": contract.get("result"),
        "final_preflight_result": final_preflight.get("result"),
        "lineage_validation": lineage_validation,
        "child_artifacts": context.child_artifact_paths,
    }


def assert_child_artifact_paths_explicit(context: N4BoundedContext) -> None:
    docs_paths = {
        "dry_run_json_path": context.child_dry_run_json_path,
        "dry_run_markdown_path": context.child_dry_run_markdown_path,
        "dry_run_preflight_json_path": context.child_dry_run_preflight_json_path,
        "dry_run_preflight_markdown_path": context.child_dry_run_preflight_markdown_path,
        "contract_json_path": context.child_contract_json_path,
        "contract_markdown_path": context.child_contract_markdown_path,
        "final_preflight_json_path": context.child_final_preflight_json_path,
        "final_preflight_markdown_path": context.child_final_preflight_markdown_path,
        "execute_report_json_path": context.child_report_json_path,
        "execute_report_markdown_path": context.child_report_markdown_path,
    }
    for label, path in docs_paths.items():
        if not _is_relative_to(path, context.docs_root):
            raise N4ReplayBlocked(f"child_artifact_path_not_under_docs_root:{label}")
        if _is_tracked_default_child_artifact_path(context, path):
            raise N4ReplayBlocked(f"default_docs_path_usage_blocked:{label}")
    if not _is_relative_to(context.rollback_sql_path, context.sql_root):
        raise N4ReplayBlocked("child_artifact_path_not_under_sql_root:rollback_sql_path")
    if _is_tracked_default_child_artifact_path(context, context.rollback_sql_path):
        raise N4ReplayBlocked("default_sql_path_usage_blocked:rollback_sql_path")


def validate_child_artifact_lineage(context: N4BoundedContext) -> dict[str, Any]:
    common_expected = {
        "trigger_context_run_id": context.lineage.context_run_id,
        "projection_run_id": context.lineage.projection_run_id,
        "source_condition_run_id": context.lineage.source_condition_run_id,
        "source_subscription_run_id": context.lineage.source_subscription_run_id,
        "source_snapshot_run_id": context.lineage.source_snapshot_run_id,
        "for_trade_date": context.lineage.for_trade_date,
    }
    artifacts: list[tuple[str, Path, dict[str, str]]] = [
        ("dry_run", context.child_dry_run_json_path, common_expected),
        ("dry_run_preflight", context.child_dry_run_preflight_json_path, common_expected),
        (
            "contract",
            context.child_contract_json_path,
            {"execute_run_id": context.lineage.trigger_run_id, **common_expected},
        ),
        (
            "final_preflight",
            context.child_final_preflight_json_path,
            {"execute_run_id": context.lineage.trigger_run_id, **common_expected},
        ),
    ]
    errors: list[str] = []
    for label, path, expected in artifacts:
        if not path.exists():
            errors.append(f"{label}_missing")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"{label}_invalid_json")
            continue
        for field, expected_value in expected.items():
            actual = str(payload.get(field) or "")
            if actual != expected_value:
                errors.append(f"{label}.{field}={actual}")
    if errors:
        raise N4ReplayBlocked("child_artifact_lineage_mismatch:" + ",".join(errors[:8]))
    return {
        "valid": True,
        "checked_artifacts": [label for label, _path, _expected in artifacts],
        "projection_run_id": context.lineage.projection_run_id,
        "trigger_run_id": context.lineage.trigger_run_id,
    }


def estimate_candidate_total(
    context: N4BoundedContext,
    candidate_estimator: Callable[[N4BoundedContext], Mapping[str, Any] | int] | None = None,
) -> dict[str, Any]:
    if candidate_estimator is not None:
        return _normalize_candidate_estimate(candidate_estimator(context))
    return _estimate_candidate_total_from_matcher(context)


def build_scope_coverage(
    context: N4BoundedContext | None,
    *,
    coverage_provider: Callable[[N4BoundedContext], Mapping[str, Any]] | None = None,
    expected_keys: Sequence[Mapping[str, Any]] | None = None,
    actual_keys: Sequence[Mapping[str, Any]] | None = None,
    legal_exclusion_keys: Sequence[Mapping[str, Any]] | None = None,
    sample_limit: int = 5,
) -> dict[str, Any]:
    if coverage_provider is not None:
        return dict(coverage_provider(context))  # type: ignore[arg-type]
    if expected_keys is None and actual_keys is None:
        if context is not None:
            return build_db_backed_scope_coverage(context, sample_limit=sample_limit)
        return {
            "provider": "not_wired",
            "coverage_complete": False,
            "stop_reason": "scope_coverage_provider_not_wired",
            "expected_count": None,
            "actual_count": None,
            "missing_count": None,
            "missing_by_condition_key": {},
            "production_note": (
                "PR-3 does not claim a production DB scope coverage provider without changing "
                "the execute module; callers must inject an authoritative provider."
            ),
        }

    expected = {_scope_key(row) for row in expected_keys or []}
    actual = {_scope_key(row) for row in actual_keys or []}
    legal_exclusion_proofs = {_scope_key(row) for row in legal_exclusion_keys or []}
    raw_missing = expected - actual
    legal_excluded_missing = raw_missing & legal_exclusion_proofs
    missing = sorted(raw_missing - legal_excluded_missing)
    legal_excluded_missing_sorted = sorted(legal_excluded_missing)

    missing_by_condition_key = _group_scope_keys_by_condition_key(missing, sample_limit=sample_limit)
    legal_exclusions_by_condition_key = _group_scope_keys_by_condition_key(
        legal_excluded_missing_sorted,
        sample_limit=sample_limit,
    )

    metric_capable_expected = expected - legal_excluded_missing
    expected_non_hint_count = sum(1 for key in metric_capable_expected if key[3] not in HINT_CONDITION_KEYS)
    actual_hint_only = bool(actual) and all(key[3] in HINT_CONDITION_KEYS for key in actual)
    coverage_complete = not missing and not (expected_non_hint_count and actual_hint_only)
    stop_reason = None if coverage_complete else "scope_coverage_incomplete"
    if expected_non_hint_count and actual_hint_only:
        stop_reason = "scope_coverage_incomplete_ordinary_expected_but_actual_hint_only"

    return {
        "provider": "injected_scope_key_sets",
        "coverage_complete": coverage_complete,
        "stop_reason": stop_reason,
        "expected_count": len(expected),
        "actual_count": len(actual),
        "raw_missing_count": len(raw_missing),
        "missing_count": len(missing),
        "missing_by_condition_key": missing_by_condition_key,
        "legal_quality_visible_exclusion_count": len(legal_excluded_missing),
        "legal_quality_visible_exclusions_by_condition_key": legal_exclusions_by_condition_key,
        "metric_capable_expected_count": len(metric_capable_expected),
        "metric_capable_missing_count": len(missing),
        "expected_non_hint_count": expected_non_hint_count,
        "actual_hint_only": actual_hint_only,
    }


def build_db_backed_scope_coverage(context: N4BoundedContext, *, sample_limit: int = 5) -> dict[str, Any]:
    from ashare_v3.trigger.action_confirmation_metric_matcher import (
        fetch_action_confirmation_metric_rows,
        fetch_projection_enrichment_v4_quality_visible_rows,
        metric_candidate_signal_for_context,
        metric_scope_matches_context_legacy_signal,
    )
    from ashare_v3.trigger.projection_matcher import fetch_context_rows

    context_rows, _trigger_run = fetch_context_rows(context.dsn, context.lineage.context_run_id)
    metric_rows = fetch_action_confirmation_metric_rows(
        context.dsn,
        projection_run_id=context.lineage.projection_run_id,
        source_condition_run_id=context.lineage.source_condition_run_id,
        source_subscription_run_id=context.lineage.source_subscription_run_id,
        source_snapshot_run_id=context.lineage.source_snapshot_run_id,
        for_trade_date=context.lineage.for_trade_date,
    )
    quality_visible_rows = fetch_projection_enrichment_v4_quality_visible_rows(
        context.dsn,
        projection_run_id=context.lineage.projection_run_id,
        source_trigger_context_run_id=context.lineage.context_run_id,
        for_trade_date=context.lineage.for_trade_date,
    )
    expected_keys = _expected_scope_keys_from_context(
        context_rows,
        trigger_context_run_id=context.lineage.context_run_id,
        candidate_signal_for_context=metric_candidate_signal_for_context,
    )
    actual_keys = _actual_scope_keys_from_metrics(
        context_rows,
        metric_rows,
        trigger_context_run_id=context.lineage.context_run_id,
        projection_run_id=context.lineage.projection_run_id,
        candidate_signal_for_context=metric_candidate_signal_for_context,
        metric_scope_matches_context_legacy_signal=metric_scope_matches_context_legacy_signal,
    )
    legal_exclusion_keys = _legal_quality_visible_exclusion_keys_from_projection_rows(
        quality_visible_rows,
        projection_run_id=context.lineage.projection_run_id,
        source_trigger_context_run_id=context.lineage.context_run_id,
    )
    coverage = build_scope_coverage(
        None,
        expected_keys=expected_keys,
        actual_keys=actual_keys,
        legal_exclusion_keys=legal_exclusion_keys,
        sample_limit=sample_limit,
    )
    coverage.update(
        {
            "provider": PRODUCTION_SCOPE_COVERAGE_PROVIDER,
            "production_provider_wired": True,
            "expected_source": "N4 localized trigger context via fetch_context_rows",
            "actual_source": "N3 action-confirmation projection metric via fetch_action_confirmation_metric_rows",
            "legal_exclusion_source": "N3 projection enrichment v4 quality-visible proof via fetch_projection_enrichment_v4_quality_visible_rows",
            "scope_grain": "asset_kind+identity_key+direction+condition_key",
            "context_row_count": len(context_rows),
            "metric_row_count": len(metric_rows),
            "quality_visible_projection_row_count": len(quality_visible_rows),
        }
    )
    return coverage


def assert_scope_coverage_complete(coverage: Mapping[str, Any]) -> None:
    if coverage.get("coverage_complete") is True:
        return
    reason = str(coverage.get("stop_reason") or "scope_coverage_incomplete")
    raise N4ReplayBlocked(reason)


def execute_replay_child(
    context: N4BoundedContext,
    args: argparse.Namespace,
    *,
    command_runner: Callable[[Sequence[str], float | None], Mapping[str, Any] | Any] | None = None,
) -> dict[str, Any]:
    stopped, stop_reason = check_stop_file(args.stop_file or None)
    if stopped:
        return {
            "result": BoundedResult.NOOP,
            "stop_reason": stop_reason,
            "child_invoked": False,
            "requires_post_check": False,
        }

    remaining = remaining_deadline_seconds(context.deadline)
    if remaining is not None and remaining <= 0:
        return {
            "result": BoundedResult.BLOCKED,
            "stop_reason": "deadline_before_replay",
            "child_invoked": False,
            "requires_post_check": False,
        }

    command = build_replay_child_command(context, args)
    runner = command_runner or _run_child_command
    child_result = _normalize_child_result(runner(command, remaining))
    child_result["argv"] = command
    child_result["child_invoked"] = True
    return child_result


def classify_replay_result(
    child_result: Mapping[str, Any],
    context: N4BoundedContext,
    *,
    post_check_provider: Callable[[N4BoundedContext], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if child_result.get("timed_out") or child_result.get("result") == BoundedResult.UNKNOWN_AFTER_TIMEOUT:
        post_check = post_check_trigger_run(context, post_check_provider=post_check_provider)
        return {
            "result": BoundedResult.UNKNOWN_AFTER_TIMEOUT,
            "stop_reason": "child_timeout",
            "requires_post_check": True,
            "post_check": post_check,
            "rollback_artifacts": {},
            "trigger_event_counts": _zero_event_counts(),
        }

    returncode = child_result.get("returncode")
    if returncode not in (0, None):
        post_check = post_check_trigger_run(context, post_check_provider=post_check_provider)
        return _classify_failed_or_ambiguous_child("child_exit_nonzero", post_check)

    report_result = _load_child_report(context.child_report_json_path, context.lineage.trigger_run_id)
    if report_result["error"]:
        post_check = post_check_trigger_run(context, post_check_provider=post_check_provider)
        return _classify_failed_or_ambiguous_child(str(report_result["error"]), post_check)

    rollback_result = _validate_rollback_sql(context.rollback_sql_path)
    if rollback_result["error"]:
        post_check = post_check_trigger_run(context, post_check_provider=post_check_provider)
        return _classify_failed_or_ambiguous_child(str(rollback_result["error"]), post_check)

    report = report_result["report"]
    return {
        "result": BoundedResult.PASS,
        "stop_reason": None,
        "requires_post_check": False,
        "post_check": {"state": "not_required"},
        "rollback_artifacts": rollback_result["rollback_artifacts"],
        "trigger_event_counts": _event_counts_from_report(report),
        "child_report_json_path": str(context.child_report_json_path),
    }


def post_check_trigger_run(
    context: N4BoundedContext,
    *,
    post_check_provider: Callable[[N4BoundedContext], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if post_check_provider is not None:
        return dict(post_check_provider(context))
    return _default_post_check_trigger_run(context)


def build_n4_manifest(
    context: N4BoundedContext,
    *,
    result: str,
    stop_reason: str | None,
    args: argparse.Namespace,
    candidate_estimate: Mapping[str, Any] | None = None,
    scope_coverage: Mapping[str, Any] | None = None,
    child_artifact_preparation: Mapping[str, Any] | None = None,
    child_result: Mapping[str, Any] | None = None,
    classification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    classification = dict(classification or {})
    trigger_event_counts = dict(classification.get("trigger_event_counts") or _zero_event_counts())
    child_invoked = bool((child_result or {}).get("child_invoked"))
    downstream_allowed = result == BoundedResult.PASS
    manifest = {
        "worker_name": WORKER_NAME,
        "json": bool(args.json),
        "result": result,
        "stop_reason": stop_reason,
        "exit_code": result_to_exit_code(result),
        "requires_post_check": bool(classification.get("requires_post_check", result in {BoundedResult.UNKNOWN_AFTER_TIMEOUT, BoundedResult.COMMIT_UNKNOWN})),
        "invocation_id": context.invocation_id,
        "wrapper_run_id": context.wrapper_run_id,
        "trigger_run_id": context.lineage.trigger_run_id,
        "trade_date": context.lineage.for_trade_date,
        "input_run_ids": context.input_run_ids,
        "explicit_lineage": context.lineage.to_dict(),
        "lineage_policy": {
            "all_lineage_explicit": True,
            "implicit_selectors_rejected": sorted(IMPLICIT_LINEAGE_VALUES),
            "source_metric_run_id_equals_projection_run_id": (
                context.lineage.source_metric_run_id == context.lineage.projection_run_id
            ),
        },
        "active_path": ACTIVE_PATH,
        "active_child_script": ACTIVE_CHILD_SCRIPT,
        "deferred_paths": list(DEFERRED_WORKER_PATHS),
        "candidate_total": _candidate_total_or_none(candidate_estimate),
        "candidate_estimate": dict(candidate_estimate or {}),
        "max_candidates": int(args.max_candidates),
        "scope_coverage": dict(scope_coverage or {}),
        "child_artifacts": context.child_artifact_paths,
        "child_artifact_preparation": dict(child_artifact_preparation or {}),
        "child_invoked": child_invoked,
        "child_result": dict(child_result or {}),
        "post_check": dict(classification.get("post_check") or {}),
        "trigger_event_counts": trigger_event_counts,
        "event_contract": {
            "TriggerMatched": "future N5 action confirmation entry",
            "TriggerStateChanged": "state broadcast only; does not write common_trigger_match",
            "TriggerPendingMarketData": "quality/state gate only; does not write common_trigger_match",
        },
        "rollback_artifacts": dict(classification.get("rollback_artifacts") or {}),
        "rollback_sql_path": str(context.rollback_sql_path),
        "status_json": str(context.status_json),
        "manifest_json": str(context.manifest_json),
        "lock_path": str(context.lock_path),
        "downstream_consumption_allowed": downstream_allowed,
        "n5_consumption_allowed": downstream_allowed,
        "side_effects": _no_cross_layer_side_effects(),
        "no_partial_contract": True,
        "no_silent_limit": True,
        "production_scope_coverage_provider_wired": bool((scope_coverage or {}).get("production_provider_wired")),
    }
    return manifest


def write_final_status(context: N4BoundedContext, manifest: Mapping[str, Any]) -> None:
    atomic_write_json(context.manifest_json, manifest)
    status = {
        key: manifest[key]
        for key in (
            "worker_name",
            "result",
            "stop_reason",
            "exit_code",
            "requires_post_check",
            "invocation_id",
            "wrapper_run_id",
            "trigger_run_id",
            "trade_date",
            "input_run_ids",
            "candidate_total",
            "child_invoked",
            "child_artifacts",
            "child_artifact_preparation",
            "child_result",
            "trigger_event_counts",
            "downstream_consumption_allowed",
            "n5_consumption_allowed",
            "side_effects",
        )
        if key in manifest
    }
    atomic_write_json(context.status_json, status)


def run_n4_replay_bounded_worker_once(
    argv: Sequence[str] | None = None,
    *,
    repo_root: str | Path | None = None,
    candidate_estimator: Callable[[N4BoundedContext], Mapping[str, Any] | int] | None = None,
    coverage_provider: Callable[[N4BoundedContext], Mapping[str, Any]] | None = None,
    command_runner: Callable[[Sequence[str], float | None], Mapping[str, Any] | Any] | None = None,
    child_artifact_preparer: Callable[[N4BoundedContext], Mapping[str, Any] | None] | None = None,
    post_check_provider: Callable[[N4BoundedContext], Mapping[str, Any]] | None = None,
    lock_acquirer: Callable[[str | Path], Any] = acquire_global_chain_lock,
    now: datetime | None = None,
) -> dict[str, Any]:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        lineage = build_explicit_lineage(args)
        context = build_n4_bounded_context(lineage, args, repo_root=repo_root, now=now)
    except (N4ReplayBlocked, ValueError) as exc:
        return _early_blocked_manifest(args, str(exc), repo_root=repo_root, now=now)

    if not args.execute:
        manifest = build_n4_manifest(
            context,
            result=BoundedResult.NOOP,
            stop_reason="plan_only",
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )
        write_final_status(context, manifest)
        return manifest

    try:
        with lock_acquirer(context.lock_path):
            manifest = _run_with_lock(
                context,
                args,
                candidate_estimator=candidate_estimator,
                coverage_provider=coverage_provider,
                command_runner=command_runner,
                child_artifact_preparer=child_artifact_preparer,
                post_check_provider=post_check_provider,
            )
            write_final_status(context, manifest)
            return manifest
    except SingletonLockHeld:
        manifest = build_n4_manifest(
            context,
            result=BoundedResult.NOOP,
            stop_reason="singleton_lock_held",
            args=args,
            candidate_estimate={},
            scope_coverage={},
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )
        write_final_status(context, manifest)
        return manifest


def main(argv: Sequence[str] | None = None) -> int:
    result = run_n4_replay_bounded_worker_once(argv)
    if result.get("json") is True:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "\n".join(
                [
                    "N4 replay bounded worker",
                    f"  result={result.get('result')}",
                    f"  stop_reason={result.get('stop_reason')}",
                    f"  trigger_run_id={result.get('trigger_run_id')}",
                    f"  child_invoked={result.get('child_invoked')}",
                    f"  n5_consumption_allowed={result.get('n5_consumption_allowed')}",
                ]
            )
        )
    return int(result.get("exit_code", result_to_exit_code(str(result.get("result") or BoundedResult.BLOCKED))))


def _run_with_lock(
    context: N4BoundedContext,
    args: argparse.Namespace,
    *,
    candidate_estimator: Callable[[N4BoundedContext], Mapping[str, Any] | int] | None,
    coverage_provider: Callable[[N4BoundedContext], Mapping[str, Any]] | None,
    command_runner: Callable[[Sequence[str], float | None], Mapping[str, Any] | Any] | None,
    child_artifact_preparer: Callable[[N4BoundedContext], Mapping[str, Any] | None] | None,
    post_check_provider: Callable[[N4BoundedContext], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    if not args.execute:
        return build_n4_manifest(
            context,
            result=BoundedResult.NOOP,
            stop_reason="plan_only",
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )
    if not args.user_confirmed:
        return build_n4_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason="execute_requires_user_confirmed",
            args=args,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )

    try:
        candidate_estimate = estimate_candidate_total(context, candidate_estimator=candidate_estimator)
    except Exception as exc:
        candidate_estimate = {
            "candidate_total": None,
            "source": "candidate_estimator_failed",
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    if _candidate_total_or_none(candidate_estimate) is None:
        return build_n4_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason="candidate_total_unavailable",
            args=args,
            candidate_estimate=candidate_estimate,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )
    if int(candidate_estimate["candidate_total"]) > int(args.max_candidates):
        return build_n4_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason="candidate_total_exceeds_max_candidates",
            args=args,
            candidate_estimate=candidate_estimate,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )

    try:
        scope_coverage = build_scope_coverage(context, coverage_provider=coverage_provider)
    except Exception as exc:
        scope_coverage = {
            "provider": "scope_coverage_provider_failed",
            "coverage_complete": False,
            "stop_reason": f"scope_coverage_provider_failed:{exc.__class__.__name__}",
            "missing_by_condition_key": {},
        }
    try:
        assert_scope_coverage_complete(scope_coverage)
    except N4ReplayBlocked as exc:
        return build_n4_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason=str(exc),
            args=args,
            candidate_estimate=candidate_estimate,
            scope_coverage=scope_coverage,
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )

    try:
        if child_artifact_preparer is not None:
            child_artifact_preparation = dict(child_artifact_preparer(context) or {})
            child_artifact_preparation["lineage_validation"] = validate_child_artifact_lineage(context)
            assert_child_artifact_paths_explicit(context)
        else:
            child_artifact_preparation = prepare_replay_child_artifacts(context)
    except N4ReplayBlocked as exc:
        return build_n4_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason=str(exc),
            args=args,
            candidate_estimate=candidate_estimate,
            scope_coverage=scope_coverage,
            child_artifact_preparation={"prepared": False, "error": str(exc)},
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )
    except Exception as exc:
        reason = f"child_artifact_preparation_failed:{exc.__class__.__name__}"
        return build_n4_manifest(
            context,
            result=BoundedResult.BLOCKED,
            stop_reason=reason,
            args=args,
            candidate_estimate=candidate_estimate,
            scope_coverage=scope_coverage,
            child_artifact_preparation={"prepared": False, "error": f"{exc.__class__.__name__}: {exc}"},
            child_result={"child_invoked": False},
            classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
        )

    child_result = execute_replay_child(context, args, command_runner=command_runner)
    if child_result.get("child_invoked") is not True:
        return build_n4_manifest(
            context,
            result=str(child_result["result"]),
            stop_reason=child_result.get("stop_reason"),
            args=args,
            candidate_estimate=candidate_estimate,
            scope_coverage=scope_coverage,
            child_artifact_preparation=child_artifact_preparation,
            child_result=child_result,
            classification={
                "requires_post_check": bool(child_result.get("requires_post_check", False)),
                "trigger_event_counts": _zero_event_counts(),
            },
        )

    classification = classify_replay_result(
        child_result,
        context,
        post_check_provider=post_check_provider,
    )
    return build_n4_manifest(
        context,
        result=str(classification["result"]),
        stop_reason=classification.get("stop_reason"),
        args=args,
        candidate_estimate=candidate_estimate,
        scope_coverage=scope_coverage,
        child_artifact_preparation=child_artifact_preparation,
        child_result=child_result,
        classification=classification,
    )


def _early_blocked_manifest(
    args: argparse.Namespace,
    stop_reason: str,
    *,
    repo_root: str | Path | None,
    now: datetime | None,
) -> dict[str, Any]:
    lineage = ExplicitLineage(
        for_trade_date=_maybe_trade_date(args.for_trade_date),
        source_metric_run_id=str(args.source_metric_run_id or ""),
        projection_run_id=str(args.projection_run_id or ""),
        context_run_id=str(args.context_run_id or ""),
        source_condition_run_id=str(args.source_condition_run_id or ""),
        source_subscription_run_id=str(args.source_subscription_run_id or ""),
        source_snapshot_run_id=str(args.source_snapshot_run_id or ""),
        trigger_run_id=str(args.trigger_run_id or ""),
    )
    safe_args = argparse.Namespace(**vars(args))
    if not safe_args.status_json:
        safe_args.status_json = "docs/N4_REPLAY_BOUNDED_WORKER_status.json"
    if not safe_args.manifest_json:
        safe_args.manifest_json = "docs/N4_REPLAY_BOUNDED_WORKER_manifest.json"
    if not safe_args.rollback_sql_path:
        safe_args.rollback_sql_path = "sql/N4_REPLAY_BOUNDED_WORKER_rollback.sql"
    context = build_n4_bounded_context(lineage, safe_args, repo_root=repo_root, now=now)
    manifest = build_n4_manifest(
        context,
        result=BoundedResult.BLOCKED,
        stop_reason=stop_reason,
        args=safe_args,
        child_result={"child_invoked": False},
        classification={"requires_post_check": False, "trigger_event_counts": _zero_event_counts()},
    )
    write_final_status(context, manifest)
    return manifest


def _estimate_candidate_total_from_matcher(context: N4BoundedContext) -> dict[str, Any]:
    from ashare_v3.trigger.action_confirmation_metric_matcher import (
        iter_action_confirmation_metric_plans_for_metric_grain,
        fetch_action_confirmation_metric_rows,
    )
    from ashare_v3.trigger.projection_matcher import fetch_context_rows

    context_rows, _trigger_run = fetch_context_rows(context.dsn, context.lineage.context_run_id)
    metric_rows = fetch_action_confirmation_metric_rows(
        context.dsn,
        projection_run_id=context.lineage.projection_run_id,
        source_condition_run_id=context.lineage.source_condition_run_id,
        source_subscription_run_id=context.lineage.source_subscription_run_id,
        source_snapshot_run_id=context.lineage.source_snapshot_run_id,
        for_trade_date=context.lineage.for_trade_date,
    )
    candidate_total = sum(
        1
        for _plan in iter_action_confirmation_metric_plans_for_metric_grain(
            trigger_context_run_id=context.lineage.context_run_id,
            projection_run_id=context.lineage.projection_run_id,
            source_condition_run_id=context.lineage.source_condition_run_id,
            source_subscription_run_id=context.lineage.source_subscription_run_id,
            source_snapshot_run_id=context.lineage.source_snapshot_run_id,
            for_trade_date=context.lineage.for_trade_date,
            context_rows=context_rows,
            metric_rows=metric_rows,
        )
    )
    return {
        "candidate_total": candidate_total,
        "source": "action_confirmation_metric_matcher_readonly_plan",
        "uses_limit": False,
        "uses_pagination": False,
    }


def _default_post_check_trigger_run(context: N4BoundedContext) -> dict[str, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - environment guard.
        return {"state": "unresolved", "reason": f"psycopg_unavailable:{exc.__class__.__name__}"}

    try:
        with psycopg.connect(
            context.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            run_row = _select_one(cur, "SELECT * FROM common_trigger_run WHERE run_id = %s", (context.lineage.trigger_run_id,))
            state_count = _count(cur, "common_trigger_state", "trigger_run_id", context.lineage.trigger_run_id)
            match_count = _count(cur, "common_trigger_match", "trigger_run_id", context.lineage.trigger_run_id)
            quality_count = _count(cur, "common_trigger_quality_item", "run_id", context.lineage.trigger_run_id)
            outbox_count = _count(cur, "common_event_outbox", "source_run_id", context.lineage.trigger_run_id)
            downstream_refs = _optional_downstream_refs(cur, context.lineage.trigger_run_id)
    except Exception as exc:  # pragma: no cover - live DB only.
        return {"state": "unresolved", "reason": f"post_check_query_failed:{exc.__class__.__name__}"}

    if run_row:
        expected_state = int(run_row.get("trigger_state_row_count") or 0)
        expected_match = int(run_row.get("trigger_match_row_count") or 0)
        expected_outbox = int(run_row.get("trigger_event_outbox_count") or 0)
        consistent = state_count == expected_state and match_count == expected_match and outbox_count == expected_outbox
        return {
            "state": "committed" if consistent and not downstream_refs else "unresolved",
            "run_status": run_row.get("status"),
            "state_count": state_count,
            "match_count": match_count,
            "quality_count": quality_count,
            "outbox_count": outbox_count,
            "downstream_refs": downstream_refs,
        }
    if not any((state_count, match_count, quality_count, outbox_count, downstream_refs)):
        return {
            "state": "rolled_back",
            "state_count": state_count,
            "match_count": match_count,
            "quality_count": quality_count,
            "outbox_count": outbox_count,
            "downstream_refs": downstream_refs,
        }
    return {
        "state": "unresolved",
        "state_count": state_count,
        "match_count": match_count,
        "quality_count": quality_count,
        "outbox_count": outbox_count,
        "downstream_refs": downstream_refs,
    }


def _classify_failed_or_ambiguous_child(stop_reason: str, post_check: Mapping[str, Any]) -> dict[str, Any]:
    state = str(post_check.get("state") or "unresolved")
    if state == "rolled_back":
        result = BoundedResult.CRASHED
        requires_post_check = False
    else:
        result = BoundedResult.COMMIT_UNKNOWN
        requires_post_check = True
    return {
        "result": result,
        "stop_reason": stop_reason,
        "requires_post_check": requires_post_check,
        "post_check": dict(post_check),
        "rollback_artifacts": {},
        "trigger_event_counts": _zero_event_counts(),
    }


def _load_child_report(path: Path, expected_trigger_run_id: str) -> dict[str, Any]:
    if not path.exists():
        return {"report": {}, "error": "child_report_missing"}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"report": {}, "error": "child_report_invalid_json"}
    report_run_id = str(report.get("trigger_run_id") or report.get("execute_run_id") or "")
    if report_run_id != expected_trigger_run_id:
        return {"report": report, "error": "child_report_trigger_run_id_mismatch"}
    return {"report": report, "error": None}


def _validate_rollback_sql(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"rollback_artifacts": {}, "error": "rollback_sql_missing"}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "rollback_artifacts": {
            "rollback_sql_path": str(path),
            "rollback_sql_sha256": digest,
        },
        "error": None,
    }


def _event_counts_from_report(report: Mapping[str, Any]) -> dict[str, int]:
    counts = report.get("write_counts") or report.get("planned_writes") or {}
    output: dict[str, int] = {}
    for event_type in TRIGGER_EVENT_TYPES:
        output[event_type] = int(counts.get(event_type) or 0)
    return output


def _zero_event_counts() -> dict[str, int]:
    return {event_type: 0 for event_type in TRIGGER_EVENT_TYPES}


def _run_child_command(command: Sequence[str], timeout_seconds: float | None) -> dict[str, Any]:
    return run_child_with_timeout(command, timeout_seconds)


def _normalize_child_result(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(result, Mapping):
        output = dict(result)
    else:
        output = {
            "result": getattr(result, "result", None),
            "returncode": getattr(result, "returncode", None),
            "timed_out": getattr(result, "timed_out", False),
            "elapsed_seconds": getattr(result, "elapsed_seconds", None),
            "stdout_tail": getattr(result, "stdout_tail", ""),
            "stderr_tail": getattr(result, "stderr_tail", ""),
        }
    if not output.get("result"):
        output["result"] = BoundedResult.PASS if output.get("returncode") == 0 else BoundedResult.CRASHED
    output.setdefault("requires_post_check", output["result"] in {BoundedResult.UNKNOWN_AFTER_TIMEOUT, BoundedResult.COMMIT_UNKNOWN})
    return output


def _normalize_candidate_estimate(value: Mapping[str, Any] | int) -> dict[str, Any]:
    if isinstance(value, Mapping):
        output = dict(value)
    else:
        output = {"candidate_total": int(value)}
    if "candidate_total" in output and output["candidate_total"] is not None:
        output["candidate_total"] = int(output["candidate_total"])
    output.setdefault("source", "injected")
    output.setdefault("uses_limit", False)
    output.setdefault("uses_pagination", False)
    return output


def _candidate_total_or_none(candidate_estimate: Mapping[str, Any] | None) -> int | None:
    if not candidate_estimate:
        return None
    value = candidate_estimate.get("candidate_total")
    if value is None:
        return None
    return int(value)


def _scope_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("asset_kind") or ""),
        str(row.get("identity_key") or ""),
        str(row.get("direction") or ""),
        str(row.get("condition_key") or ""),
    )


def _scope_key_dict(key: tuple[str, str, str, str]) -> dict[str, str]:
    return {
        "asset_kind": key[0],
        "identity_key": key[1],
        "direction": key[2],
        "condition_key": key[3],
    }


def _group_scope_keys_by_condition_key(
    keys: Sequence[tuple[str, str, str, str]],
    *,
    sample_limit: int,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for key in keys:
        condition_key = key[3]
        entry = grouped.setdefault(condition_key, {"count": 0, "samples": []})
        entry["count"] += 1
        if len(entry["samples"]) < sample_limit:
            entry["samples"].append(_scope_key_dict(key))
    return grouped


def _legal_quality_visible_exclusion_keys_from_projection_rows(
    projection_rows: Sequence[Mapping[str, Any]],
    *,
    projection_run_id: str,
    source_trigger_context_run_id: str,
) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    for row in projection_rows:
        if not _is_legal_quality_visible_projection_exclusion(
            row,
            projection_run_id=projection_run_id,
            source_trigger_context_run_id=source_trigger_context_run_id,
        ):
            continue
        key = _scope_key(row)
        if all(key):
            keys.append(_scope_key_dict(key))
    return keys


def _is_legal_quality_visible_projection_exclusion(
    row: Mapping[str, Any],
    *,
    projection_run_id: str,
    source_trigger_context_run_id: str,
) -> bool:
    return (
        str(row.get("projection_run_id") or "") == projection_run_id
        and str(row.get("source_trigger_context_run_id") or "") == source_trigger_context_run_id
        and row.get("quality_visible") is True
        and row.get("metric_ready") is False
        and str(row.get("metric_quality_status") or "") == "missing"
        and str(row.get("source_freshness_status") or "") == "source_minute_missing_quality_visible"
    )


def _expected_scope_keys_from_context(
    context_rows: Sequence[Mapping[str, Any]],
    *,
    trigger_context_run_id: str,
    candidate_signal_for_context: Callable[[Mapping[str, Any]], str | None],
) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    for row in context_rows:
        if str(row.get("run_id") or "") != trigger_context_run_id:
            continue
        if candidate_signal_for_context(row) is None:
            continue
        key = _scope_key(row)
        if all(key):
            keys.append(_scope_key_dict(key))
    return keys


def _actual_scope_keys_from_metrics(
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    candidate_signal_for_context: Callable[[Mapping[str, Any]], str | None],
    metric_scope_matches_context_legacy_signal: Callable[[Mapping[str, Any], str], bool],
) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    metrics_by_identity: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for metric in metric_rows:
        if str(metric.get("projection_run_id") or "") != projection_run_id:
            continue
        metric_key = (str(metric.get("asset_kind") or ""), str(metric.get("identity_key") or ""))
        if metric_key[0] and metric_key[1]:
            metrics_by_identity.setdefault(metric_key, []).append(metric)
        keys.extend(_declared_metric_scope_keys(metric))

    for row in context_rows:
        if str(row.get("run_id") or "") != trigger_context_run_id:
            continue
        legacy_signal = candidate_signal_for_context(row)
        if legacy_signal is None:
            continue
        row_key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        if not row_key[0] or not row_key[1]:
            continue
        for metric in metrics_by_identity.get(row_key, []):
            if metric_scope_matches_context_legacy_signal(metric, legacy_signal):
                keys.append(_scope_key_dict(_scope_key(row)))
                break
    return keys


def _declared_metric_scope_keys(metric: Mapping[str, Any]) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    metric_asset_kind = str(metric.get("asset_kind") or "")
    metric_identity_key = str(metric.get("identity_key") or "")
    for row in _metric_full_scope_condition_rows(metric):
        key = _metric_scope_key_from_mapping(row, asset_kind=metric_asset_kind, identity_key=metric_identity_key)
        if key is not None:
            keys.append(_scope_key_dict(key))
    for container in _metric_scope_containers(metric):
        key = _metric_scope_key_from_mapping(container, asset_kind=metric_asset_kind, identity_key=metric_identity_key)
        if key is not None:
            keys.append(_scope_key_dict(key))
    return keys


def _metric_scope_containers(metric: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    containers: list[Mapping[str, Any]] = [metric]
    for field in ("raw_json", "trace_json"):
        value = metric.get(field)
        if isinstance(value, Mapping):
            containers.append(value)
    return containers


def _metric_full_scope_condition_rows(metric: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for container in _metric_scope_containers(metric):
        value = container.get("full_scope_condition_rows")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            rows.extend(item for item in value if isinstance(item, Mapping))
    return rows


def _metric_scope_key_from_mapping(
    row: Mapping[str, Any],
    *,
    asset_kind: str,
    identity_key: str,
) -> tuple[str, str, str, str] | None:
    condition_key = str(
        row.get("condition_key")
        or row.get("original_condition_key")
        or row.get("canonical_condition_type")
        or ""
    ).upper()
    signal_type = str(row.get("signal_type") or row.get("runtime_signal_type") or "").upper()
    direction = _direction_for_scope(row.get("direction"), condition_key=condition_key, signal_type=signal_type)
    key_asset_kind = str(row.get("asset_kind") or asset_kind)
    key_identity_key = str(row.get("identity_key") or identity_key)
    if not condition_key or not direction or not key_asset_kind or not key_identity_key:
        return None
    return (key_asset_kind, key_identity_key, direction, condition_key)


def _direction_for_scope(value: Any, *, condition_key: str, signal_type: str) -> str | None:
    direction = str(value or "").lower()
    if direction in {"buy", "sell"}:
        return direction
    if condition_key.startswith("BUY"):
        return "buy"
    if condition_key.startswith("SELL"):
        return "sell"
    if signal_type in {"B_BUY", "B_BUY_30M_VOL", "BUY", "BUY:FULL", "BUY_HINT"}:
        return "buy"
    if signal_type in {"S_SELL", "S_SELL_30M_SHRINK", "SELL", "SELL:FULL", "SELL_HINT"}:
        return "sell"
    return None


def _required_arg(args: argparse.Namespace, name: str) -> str:
    value = getattr(args, name, None)
    if value is None or str(value) == "":
        raise N4ReplayBlocked(f"{name} is required")
    return str(value)


def _validate_trade_date(value: str) -> str:
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        value = value.replace("-", "")
    if len(value) != 8 or not value.isdigit():
        raise N4ReplayBlocked("for_trade_date must be YYYYMMDD")
    datetime.strptime(value, "%Y%m%d")
    return value


def _maybe_trade_date(value: Any) -> str:
    try:
        return _validate_trade_date(str(value or "19700101"))
    except Exception:
        return "19700101"


def _validate_explicit_run_id(name: str, value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise N4ReplayBlocked(f"{name} is required")
    if cleaned.lower() in IMPLICIT_LINEAGE_VALUES:
        raise N4ReplayBlocked(f"{name} uses implicit lineage selector: {cleaned}")
    return cleaned


def _resolve_repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _is_tracked_default_child_artifact_path(context: N4BoundedContext, path: Path) -> bool:
    default_paths = {
        context.repo_root / "docs/N4_action_confirmation_metric_dry_run_report.json",
        context.repo_root / "docs/N4_action_confirmation_metric_execute_preflight.json",
        context.repo_root / "docs/N4_action_confirmation_metric_business_execute_contract.json",
        context.repo_root / "docs/N4_ACTION_CONFIRMATION_METRIC_BUSINESS_EXECUTE_CONTRACT.md",
        context.repo_root / "docs/N4_action_confirmation_metric_business_execute_final_preflight.json",
        context.repo_root / "docs/N4_ACTION_CONFIRMATION_METRIC_BUSINESS_EXECUTE_FINAL_PREFLIGHT.md",
        context.repo_root / "docs/N4_action_confirmation_metric_business_execute_report.json",
        context.repo_root / "docs/N4_ACTION_CONFIRMATION_METRIC_BUSINESS_EXECUTE_REPORT.md",
        context.repo_root / "sql/N4_action_confirmation_metric_business_execute_rollback.sql",
    }
    resolved = path.resolve(strict=False)
    return any(resolved == default_path.resolve(strict=False) for default_path in default_paths)


def _safe_artifact_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:120]


def _no_cross_layer_side_effects() -> dict[str, bool]:
    return {
        "n5": False,
        "n6": False,
        "action": False,
        "trade": False,
        "sim": False,
        "voice": False,
        "mobile": False,
        "worker_started": False,
        "n3_outbox_consumed": False,
        "n3_inbox_written": False,
        "checkpoint_written": False,
    }


def _select_one(cursor: Any, sql: str, params: Sequence[Any]) -> Mapping[str, Any]:
    cursor.execute(sql, params)
    return cursor.fetchone() or {}


def _count(cursor: Any, table: str, run_column: str, run_id: str) -> int:
    cursor.execute(f"SELECT count(*) AS count FROM {table} WHERE {run_column} = %s", (run_id,))
    row = cursor.fetchone() or {}
    return int(row.get("count") or 0)


def _optional_downstream_refs(cursor: Any, trigger_run_id: str) -> dict[str, int]:
    refs: dict[str, int] = {}
    optional_tables = (
        ("common_action_confirmation", "source_trigger_run_id"),
        ("common_action_event", "source_trigger_run_id"),
        ("common_user_projection", "source_trigger_run_id"),
    )
    for table, column in optional_tables:
        try:
            refs[table] = _count(cursor, table, column, trigger_run_id)
        except Exception:
            refs[table] = 0
    return {table: count for table, count in refs.items() if count}


if __name__ == "__main__":
    raise SystemExit(main())
