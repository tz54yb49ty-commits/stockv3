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
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import lru_cache
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
    FORBIDDEN_SOURCE_CLOSE_LABELS,
    OPEN_BOUNDARY_MISSING_SOURCE_REASON,
    SOURCE_CLOSE_LABEL_POLICY,
    apply_source_close_label_policy_to_row,
    build_n3_c1_n3t_metric_context_source_artifact,
    build_n3_c1_scoped_artifact_plan,
    build_n3_c1_scoped_current_day_staging_artifact,
    build_n3_c1_scoped_current_day_pull_plan,
    canonical_ashare_1m_labels,
    source_close_label_for_physical_start_label,
    source_close_label_to_physical_start_label,
)
from ashare_v3.market.n3t_action_confirmation_metric import build_n3t_scoped_metric_from_c1_artifact_plan
from ashare_v3.market.n3t_action_confirmation_metric import (
    N3T_TABLE_BY_ASSET_KIND,
    N3T_WRITER_INSERT_COLUMNS,
    build_n3t_action_confirmation_metric_row,
)

INPUT_ARTIFACT_TYPE = "n5_active_scope_snapshot_v1"
DEFAULT_FASTLANE_MAX_RUNTIME_SECONDS = 30.0
DEFAULT_POST_CLOSE_FINAL_A_PASS_MAX_CANDIDATES = 12
DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_MAX_CANDIDATES = 256
DEFAULT_ACTIVE_A_MINUTE_BATCH_MAX_MINUTES_PER_OBJECT = 10
DEFAULT_OBJECT_CURSOR_BATCH_MAX_MINUTES_PER_OBJECT = 16
DEFAULT_OBJECT_CURSOR_BATCH_MAX_PROOF_ROWS = 4096
DEFAULT_EXISTING_SOURCE_STAGING_MAX_CANDIDATES = 16
DEFAULT_EXISTING_STAGING_METRIC_CONTEXT_MAX_CANDIDATES = 2048
DEFAULT_SCOPED_PULL_PLAN_MAX_CANDIDATES = 16
DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_CONCURRENCY = 8
MAX_CURRENT_DAY_SOURCE_PROVIDER_CONCURRENCY = 8
POST_CLOSE_FINAL_A_CLOSE_GRACE_READY_HHMM = 1501
POST_CLOSE_FINAL_A_PHYSICAL_MINUTE_LABEL = "14:59"
POST_CLOSE_FINAL_A_C1_PULL_ATTEMPT_ARTIFACT_TYPE = (
    "n3_c1_n3t_post_close_final_a_c1_pull_attempt_v1"
)
ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE = "active_a_minute_batch_direct_provider"
OBJECT_CURSOR_BATCH_MODE = "active_a_object_cursor_in_memory_batch"
OBJECT_CURSOR_BATCH_ARTIFACT_TYPE = "n3_c1_n3t_object_cursor_batch_v1"
OBJECT_SCOPE_REF_FANOUT_PAYLOAD_POLICY = "n3_c1_n3t_compact_ref_v1"
OBJECT_SCOPE_REF_FANOUT_REF_FIELDS = (
    "for_trade_date",
    "state_key",
    "asset_kind",
    "identity_key",
    "direction",
    "signal_type",
    "condition_key",
    "source_trigger_event_id",
    "source_trigger_event_type",
    "source_trigger_run_id",
    "source_trigger_event_time",
    "latest_n4_event_id",
    "latest_n4_event_type",
    "latest_n4_event_time",
    "trigger_time",
    "first_confirmation_minute_label",
    "target_minute_label",
    "last_checked_minute_label",
    "next_unchecked_minute_label",
    "source_run_hash",
    "trigger_live",
    "current_status",
    "scope_status",
)
OBJECT_SCOPE_REF_FANOUT_HASHED_TRACE_FIELDS = (
    "source_n4_payload",
    "action_entry_trigger_matched_ref",
    "latest_trigger_state_changed_ref",
)
JSON_ARTIFACT_CACHE_MAX_ENTRIES = 512
_JSON_ARTIFACT_CACHE: OrderedDict[tuple[str, int, int], dict[str, Any]] = OrderedDict()


@lru_cache(maxsize=16)
def _canonical_ashare_1m_labels_cached(for_trade_date: str) -> tuple[str, ...]:
    return tuple(canonical_ashare_1m_labels(for_trade_date))


class FastlaneShellBlocked(RuntimeError):
    """Raised when the artifact-first runner cannot proceed safely."""


def _make_runtime_deadline_check(
    *,
    args: argparse.Namespace,
    started: float,
    now_monotonic: Any,
) -> Callable[[str], None]:
    def check(phase: str) -> None:
        max_seconds = float(getattr(args, "max_runtime_seconds", 0.0) or 0.0)
        if max_seconds <= 0:
            return
        elapsed = float(now_monotonic()) - float(started)
        if elapsed > max_seconds:
            raise FastlaneShellBlocked(f"max_runtime_seconds_exceeded:{phase}")

    return check


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one artifact-first N3 C1/N3T fastlane shell.")
    parser.add_argument("--activation-config", default="")
    parser.add_argument("--fastlane-lane-id", default="")
    parser.add_argument("--active-scope-artifact-path", default="")
    parser.add_argument("--active-scope-artifact-dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--current-exchange-time", dest="fastlane_current_exchange_time", default="")
    parser.add_argument("--current-day-source-artifact-dir", default="")
    parser.add_argument("--current-day-source-provider", default="")
    parser.add_argument("--current-day-source-provider-max-candidates-per-invocation", type=int, default=0)
    parser.add_argument("--current-day-source-provider-concurrency", type=int, default=0)
    parser.add_argument("--scoped-pull-plan-max-candidates-per-invocation", type=int, default=0)
    parser.add_argument("--existing-source-staging-max-candidates-per-invocation", type=int, default=0)
    parser.add_argument("--existing-staging-metric-context-max-candidates-per-invocation", type=int, default=0)
    parser.add_argument("--metric-context-source-artifact-dir", default="")
    parser.add_argument("--previous-day-context-artifact-dir", default="")
    parser.add_argument("--previous-day-context-provider", default="")
    parser.add_argument("--n3t-writer-adapter", default="")
    parser.add_argument("--max-runtime-seconds", type=float, default=0.0)
    parser.add_argument("--post-close-final-a-pass-max-candidates-per-invocation", type=int, default=0)
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
    metric_context_priority_summary: dict[str, Any] | None = None
    c1_active_a_minute_batch_summary: dict[str, Any] | None = None
    post_close_final_a_close_grace_pull: dict[str, Any] = {}
    n3t_writer_inputs: list[dict[str, Any]] = []
    n3t_writer_done_markers: list[dict[str, Any]] = []
    lane_results: dict[str, Any] = _initial_independent_lane_results()
    try:
        _apply_activation_config(args)
        _validate_args(args)
        deadline_check = _make_runtime_deadline_check(
            args=args,
            started=started,
            now_monotonic=now_monotonic,
        )
        deadline_check("validated")
        raw_active_scope_artifacts = _discover_requested_active_scope_artifacts(args, fanout=False)
        deadline_check("active_scope_discovered")
        if args.execute and _object_cursor_batch_hot_path_enabled(args):
            if not raw_active_scope_artifacts:
                raise FastlaneShellBlocked("active_scope_artifact_missing")
            if current_day_source_provider_adapter is None:
                current_day_source_provider_adapter = _configured_current_day_source_provider_adapter(args)
            if previous_day_context_provider_adapter is None:
                previous_day_context_provider_adapter = _configured_previous_day_context_provider_adapter(args)
            if n3t_writer_adapter is None:
                n3t_writer_adapter = _configured_n3t_writer_adapter(args)
            return _run_object_cursor_batch_hot_path(
                args=args,
                invocation_id=invocation_id,
                active_scope_artifacts=raw_active_scope_artifacts,
                current_day_source_provider_adapter=current_day_source_provider_adapter,
                previous_day_context_provider_adapter=previous_day_context_provider_adapter,
                n3t_writer_adapter=n3t_writer_adapter,
                deadline_check=deadline_check,
                started=started,
                now_monotonic=now_monotonic,
            )
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
            deadline_check("closed_minute_filter")
            if _is_post_close_final_a_pass(args):
                artifacts, chunk_summary = _select_post_close_final_a_pass_candidate_chunk(
                    active_scope_artifacts=artifacts,
                    output_dir=Path(args.output_dir),
                    max_candidates=_post_close_final_a_pass_max_candidates(args),
                )
                args.post_close_final_a_pass_chunk_summary = chunk_summary
            artifacts = _materialize_object_scope_ref_fanout_active_scope_artifacts(
                active_scope_artifacts=artifacts,
                output_dir=Path(args.output_dir),
            )
            base_active_scope_artifacts = list(artifacts)
            deadline_check("object_scope_ref_fanout_materialized")
            metric_source_dir_text = str(getattr(args, "metric_context_source_artifact_dir", "") or "").strip()
            previous_context_dir_text = str(getattr(args, "previous_day_context_artifact_dir", "") or "").strip()
            source_dir_text = str(getattr(args, "current_day_source_artifact_dir", "") or "").strip()
            closed_hhmm_for_active_a_minute_batch = _active_a_minute_batch_closed_hhmm(
                args,
                raw_active_scope_artifacts or base_active_scope_artifacts,
            )
            n3t_candidate_scope_artifacts = _active_scope_artifacts_with_current_object_persisted_ref_fanout(
                active_scope_artifacts=raw_active_scope_artifacts or base_active_scope_artifacts,
                output_dir=Path(args.output_dir),
                closed_hhmm=closed_hhmm_for_active_a_minute_batch,
            )
            metric_context_priority_artifacts: list[dict[str, Any]] = []
            metric_context_priority_summary: dict[str, Any] = {}
            metric_context_priority_artifacts, metric_context_priority_summary = (
                _select_existing_staging_metric_context_artifact_chunk(
                    active_scope_artifacts=n3t_candidate_scope_artifacts,
                    output_dir=Path(args.output_dir),
                    metric_context_source_dir=Path(metric_source_dir_text) if metric_source_dir_text else None,
                    previous_context_dir=Path(previous_context_dir_text) if previous_context_dir_text else None,
                    max_candidates=_existing_staging_metric_context_max_candidates(args),
                    allow_previous_day_context_missing=bool(
                        str(getattr(args, "previous_day_context_provider", "") or "").strip()
                    ),
                )
            )
            lane_results["n3t_lane"] = _lane_result_from_priority_summary(
                lane_name="n3t_lane",
                summary=metric_context_priority_summary,
                default_reason="n3t_lane_no_ready_staging",
                selected_artifacts=metric_context_priority_artifacts,
                observed_at=_runner_observed_at(args),
            )
            if metric_context_priority_artifacts:
                artifacts = metric_context_priority_artifacts
                args.prevctx_to_metric_context_chunk_summary = metric_context_priority_summary
            prioritized_staging_artifacts: list[dict[str, Any]] = []
            staging_priority_skip_reason = ""
            scoped_pull_plan_artifacts: list[dict[str, Any]] = []
            scoped_pull_plan_summary: dict[str, Any] = {}
            existing_source_staging_count = 0
            active_a_minute_batch_controls_c1 = False
            post_close_final_a_close_grace_pull = _post_close_final_a_c1_pull_gate(
                args,
                output_dir=Path(args.output_dir),
            )
            args.post_close_final_a_close_grace_pull = post_close_final_a_close_grace_pull
            post_close_c1_provider_disabled = bool(
                post_close_final_a_close_grace_pull.get("c1_selection_disabled")
            )
            if source_dir_text and not post_close_c1_provider_disabled:
                prioritized_staging_artifacts, c1_active_a_minute_batch_summary = (
                        _select_active_a_minute_batch_direct_provider_artifacts(
                        active_scope_artifacts=raw_active_scope_artifacts or base_active_scope_artifacts,
                        output_dir=Path(args.output_dir),
                        source_dir=Path(source_dir_text),
                        closed_hhmm=closed_hhmm_for_active_a_minute_batch,
                        max_candidates=_current_day_source_provider_max_candidates(args),
                    )
                )
                if _is_post_close_final_a_pass(args):
                    _apply_post_close_final_a_full_scope_coverage(
                        close_grace_pull=post_close_final_a_close_grace_pull,
                        c1_summary=c1_active_a_minute_batch_summary,
                    )
                    if not bool(post_close_final_a_close_grace_pull.get("external_pull_allowed")):
                        c1_active_a_minute_batch_summary["reason"] = (
                            str(post_close_final_a_close_grace_pull.get("reason") or "")
                            or "post_close_final_a_scope_exceeds_single_pull_limit"
                        )
                    c1_active_a_minute_batch_summary["post_close_final_a_close_grace_pull"] = dict(
                        post_close_final_a_close_grace_pull
                    )
                active_a_minute_batch_controls_c1 = _active_a_minute_batch_controls_c1(
                    active_scope_artifacts=base_active_scope_artifacts,
                    summary=c1_active_a_minute_batch_summary,
                )
                if active_a_minute_batch_controls_c1:
                    args.c1_active_a_minute_batch_summary = c1_active_a_minute_batch_summary
                if prioritized_staging_artifacts:
                    args.c1_active_a_minute_batch_summary = c1_active_a_minute_batch_summary
                    staging_priority_skip_reason = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
                elif _active_a_minute_batch_closed_minute_unavailable(
                    args=args,
                    summary=c1_active_a_minute_batch_summary,
                ):
                    args.c1_active_a_minute_batch_summary = c1_active_a_minute_batch_summary
                    lane_results["c1_lane"] = _lane_result_from_active_a_minute_batch_summary(
                        c1_active_a_minute_batch_summary,
                        selected_artifacts=[],
                        observed_at=_runner_observed_at(args),
                    )
                    return {
                        "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
                        "reason": "c1_active_a_minute_batch_closed_minute_unavailable",
                        "invocation_id": invocation_id,
                        "fastlane_lane_id": args.fastlane_lane_id,
                        "active_scope_artifact_count": len(base_active_scope_artifacts),
                        "artifact_paths": {
                            "active_scope_artifact_dir": args.active_scope_artifact_dir,
                            "output_dir": args.output_dir,
                        },
                        "counts": {
                            "active_scope_artifact_count": len(base_active_scope_artifacts),
                            "active_scope_artifact_row_count": sum(
                                int(item.get("scope_count") or 0) for item in base_active_scope_artifacts
                            ),
                        },
                        "lane_results": dict(lane_results),
                        "c1_active_a_minute_batch": dict(c1_active_a_minute_batch_summary or {}),
                        "boundary": _boundary(),
                        "bounded": {
                            "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
                            "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
                        },
                    }
                elif active_a_minute_batch_controls_c1:
                    staging_priority_skip_reason = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
                else:
                    prioritized_staging_artifacts = _select_existing_v2_source_stale_staging_rebuild_artifacts(
                    active_scope_artifacts=artifacts,
                    output_dir=Path(args.output_dir),
                    source_dir=Path(source_dir_text),
                    )
                    if prioritized_staging_artifacts:
                        staging_priority_skip_reason = "existing_v2_source_staging_rebuild_prioritized"
                    else:
                        prioritized_staging_artifacts = _select_existing_source_missing_staging_artifacts(
                            active_scope_artifacts=artifacts,
                            output_dir=Path(args.output_dir),
                            source_dir=Path(source_dir_text),
                            max_candidates=_existing_source_staging_max_candidates(args),
                        )
                        if prioritized_staging_artifacts:
                            staging_priority_skip_reason = "existing_source_missing_staging_interleave_prioritized"
                        else:
                            prioritized_staging_artifacts, scoped_pull_plan_summary = (
                                _select_object_minute_c1_lane_priority_artifacts(
                                    active_scope_artifacts=artifacts,
                                    output_dir=Path(args.output_dir),
                                    max_candidates=_scoped_pull_plan_max_candidates(args),
                                )
                            )
                            if prioritized_staging_artifacts:
                                args.scoped_pull_plan_chunk_summary = scoped_pull_plan_summary
                                staging_priority_skip_reason = "object_minute_c1_lane_prioritized"
                            else:
                                scoped_pull_plan_summary = {}
                                prioritized_staging_artifacts = _select_existing_pull_plan_missing_source_staging_artifacts(
                                    active_scope_artifacts=artifacts,
                                    output_dir=Path(args.output_dir),
                                    source_dir=Path(source_dir_text),
                                    max_candidates=_current_day_source_provider_max_candidates(args),
                                )
                                if prioritized_staging_artifacts:
                                    staging_priority_skip_reason = "pull_plan_missing_source_staging_backlog_prioritized"
            if source_dir_text and post_close_c1_provider_disabled and not metric_context_priority_artifacts:
                c1_active_a_minute_batch_summary = _post_close_c1_provider_disabled_summary(
                    active_scope_artifacts=base_active_scope_artifacts,
                    reason=str(
                        post_close_final_a_close_grace_pull.get("reason")
                        or "post_close_c1_provider_disabled"
                    ),
                    close_grace_pull=post_close_final_a_close_grace_pull,
                )
                args.c1_active_a_minute_batch_summary = c1_active_a_minute_batch_summary
                lane_results["c1_lane"] = _lane_result_from_active_a_minute_batch_summary(
                    c1_active_a_minute_batch_summary,
                    selected_artifacts=[],
                    observed_at=_runner_observed_at(args),
                )
                return {
                    "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
                    "reason": str(c1_active_a_minute_batch_summary["reason"]),
                    "invocation_id": invocation_id,
                    "fastlane_lane_id": args.fastlane_lane_id,
                    "active_scope_artifact_count": len(base_active_scope_artifacts),
                    "artifact_paths": {
                        "active_scope_artifact_dir": args.active_scope_artifact_dir,
                        "output_dir": args.output_dir,
                    },
                    "counts": {
                        "active_scope_artifact_count": len(base_active_scope_artifacts),
                        "active_scope_artifact_row_count": sum(
                            int(item.get("scope_count") or 0) for item in base_active_scope_artifacts
                        ),
                    },
                    "lane_results": dict(lane_results),
                    "c1_active_a_minute_batch": dict(c1_active_a_minute_batch_summary),
                    "post_close_final_a_close_grace_pull": dict(
                        post_close_final_a_close_grace_pull
                    ),
                    "boundary": _boundary(),
                    "bounded": {
                        "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
                        "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
                    },
                }
            if prioritized_staging_artifacts:
                artifacts = prioritized_staging_artifacts
            if not metric_context_priority_artifacts and not prioritized_staging_artifacts:
                ready_handoff_artifacts = [
                    dict(item)
                    for item in (c1_active_a_minute_batch_summary or {}).get("ready_handoff_artifacts", [])
                    if isinstance(item, Mapping)
                ]
                metric_context_selection_scope = (
                    _dedupe_active_scope_artifacts_by_namespace(ready_handoff_artifacts + n3t_candidate_scope_artifacts)
                    if ready_handoff_artifacts
                    else n3t_candidate_scope_artifacts
                )
                metric_context_priority_artifacts, metric_context_priority_summary = (
                    _select_existing_staging_metric_context_artifact_chunk(
                        active_scope_artifacts=metric_context_selection_scope,
                        output_dir=Path(args.output_dir),
                        metric_context_source_dir=Path(metric_source_dir_text) if metric_source_dir_text else None,
                        previous_context_dir=Path(previous_context_dir_text) if previous_context_dir_text else None,
                        max_candidates=_existing_staging_metric_context_max_candidates(args),
                        allow_previous_day_context_missing=bool(
                            str(getattr(args, "previous_day_context_provider", "") or "").strip()
                        ),
                    )
                )
                lane_results["n3t_lane"] = _lane_result_from_priority_summary(
                    lane_name="n3t_lane",
                    summary=metric_context_priority_summary,
                    default_reason="n3t_lane_no_ready_staging",
                    selected_artifacts=metric_context_priority_artifacts,
                    observed_at=_runner_observed_at(args),
                )
                if metric_context_priority_artifacts:
                    artifacts = metric_context_priority_artifacts
                    args.prevctx_to_metric_context_chunk_summary = metric_context_priority_summary
            if (
                not metric_context_priority_artifacts
                and not prioritized_staging_artifacts
                and active_a_minute_batch_controls_c1
            ):
                lane_results["c1_lane"] = _lane_result_from_active_a_minute_batch_summary(
                    c1_active_a_minute_batch_summary or {},
                    selected_artifacts=base_active_scope_artifacts,
                    observed_at=_runner_observed_at(args),
                )
                return {
                    "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
                    "reason": _active_a_minute_batch_waiting_reason(c1_active_a_minute_batch_summary or {}),
                    "invocation_id": invocation_id,
                    "fastlane_lane_id": args.fastlane_lane_id,
                    "active_scope_artifact_count": len(base_active_scope_artifacts),
                    "artifact_paths": {
                        "active_scope_artifact_dir": args.active_scope_artifact_dir,
                        "output_dir": args.output_dir,
                    },
                    "counts": {
                        "active_scope_artifact_count": len(base_active_scope_artifacts),
                        "active_scope_artifact_row_count": sum(
                            int(item.get("scope_count") or 0) for item in base_active_scope_artifacts
                        ),
                    },
                    "lane_results": dict(lane_results),
                    "c1_active_a_minute_batch": dict(c1_active_a_minute_batch_summary or {}),
                    "boundary": _boundary(),
                    "bounded": {
                        "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
                        "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
                    },
                }
            if not metric_context_priority_artifacts and not prioritized_staging_artifacts:
                scoped_pull_plan_artifacts, scoped_pull_plan_summary = _select_scoped_pull_plan_candidate_chunk(
                    active_scope_artifacts=artifacts,
                    output_dir=Path(args.output_dir),
                    max_candidates=_scoped_pull_plan_max_candidates(args),
                )
                if scoped_pull_plan_artifacts:
                    artifacts = scoped_pull_plan_artifacts
                    args.scoped_pull_plan_chunk_summary = scoped_pull_plan_summary
            if not metric_context_priority_artifacts or prioritized_staging_artifacts or active_a_minute_batch_controls_c1:
                lane_results["c1_lane"] = _lane_result_from_c1_selection(
                    prioritized_staging_artifacts=prioritized_staging_artifacts,
                    scoped_pull_plan_summary=scoped_pull_plan_summary,
                    skip_reason=staging_priority_skip_reason,
                    selected_artifacts=prioritized_staging_artifacts or scoped_pull_plan_artifacts,
                    observed_at=_runner_observed_at(args),
                )
                if staging_priority_skip_reason != ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE:
                    try:
                        _materialize_missing_scoped_pull_plans(
                            active_scope_artifacts=artifacts,
                            output_dir=Path(args.output_dir),
                            observed_at=_runner_observed_at(args),
                            deadline_check=deadline_check,
                        )
                    except FastlaneShellBlocked as exc:
                        scoped_pull_plan_summary = dict(getattr(args, "scoped_pull_plan_chunk_summary", {}) or {})
                        if _scoped_pull_plan_progress_timeout(exc, chunk_summary=scoped_pull_plan_summary):
                            manifest = _scoped_pull_plan_chunk_waiting_manifest(
                                args=args,
                                invocation_id=invocation_id,
                                artifacts=artifacts,
                                output_dir=Path(args.output_dir),
                                chunk_summary=scoped_pull_plan_summary,
                                started=started,
                                now_monotonic=now_monotonic,
                            )
                            manifest["lane_results"] = dict(lane_results)
                            return manifest
                        raise
                    deadline_check("scoped_pull_plan_materialized")
                if prioritized_staging_artifacts and staging_priority_skip_reason not in {
                    "object_minute_c1_lane_prioritized",
                    ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE,
                }:
                    existing_source_staging_count = _materialize_missing_scoped_current_day_staging_artifacts(
                        args=args,
                        active_scope_artifacts=prioritized_staging_artifacts,
                        output_dir=Path(args.output_dir),
                        observed_at=_runner_observed_at(args),
                        deadline_check=deadline_check,
                        require_source_dir_exists=False,
                    )
                if (
                    _is_post_close_final_a_pass(args)
                    and not bool(post_close_final_a_close_grace_pull.get("external_pull_allowed"))
                ):
                    current_day_source_provider_adapter = None
                elif current_day_source_provider_adapter is None:
                    current_day_source_provider_adapter = _configured_current_day_source_provider_adapter(args)
                direct_staging_count = 0
                if existing_source_staging_count > 0:
                    current_day_source_provider_result = _skipped_current_day_source_provider_result(
                        skip_reason=staging_priority_skip_reason,
                        staging_artifact_count=existing_source_staging_count,
                    )
                elif (
                    staging_priority_skip_reason == ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
                ):
                    if not prioritized_staging_artifacts:
                        current_day_source_provider_result = _skipped_current_day_source_provider_result(
                            skip_reason=ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE,
                            staging_artifact_count=0,
                            metric_context_candidate_count=len(metric_context_priority_artifacts),
                        )
                        current_day_source_provider_result["mode"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
                    elif current_day_source_provider_adapter is not None:
                        provider_fetch_artifacts = [
                            dict(item)
                            for item in (c1_active_a_minute_batch_summary or {}).get(
                                "provider_fetch_artifacts", []
                            )
                            if isinstance(item, Mapping)
                        ]
                        if _is_post_close_final_a_pass(args):
                            current_day_source_provider_result = (
                                _run_post_close_final_a_single_close_grace_provider_adapter(
                                    args=args,
                                    invocation_id=invocation_id,
                                    active_scope_artifacts=provider_fetch_artifacts or artifacts,
                                    output_dir=Path(args.output_dir),
                                    current_day_source_provider_adapter=current_day_source_provider_adapter,
                                    close_grace_pull=post_close_final_a_close_grace_pull,
                                )
                            )
                        else:
                            current_day_source_provider_result = (
                                _run_active_a_minute_batch_direct_provider_adapter(
                                    args=args,
                                    active_scope_artifacts=provider_fetch_artifacts or artifacts,
                                    output_dir=Path(args.output_dir),
                                    current_day_source_provider_adapter=current_day_source_provider_adapter,
                                )
                            )
                        provider_staging_count = _materialize_active_a_minute_batch_direct_staging_artifacts(
                            args=args,
                            active_scope_artifacts=artifacts,
                            output_dir=Path(args.output_dir),
                            observed_at=_runner_observed_at(args),
                            deadline_check=deadline_check,
                            source_artifacts=(
                                list((current_day_source_provider_result or {}).get("source_artifacts") or [])
                            ),
                        )
                        direct_staging_count += provider_staging_count
                    else:
                        direct_staging_count = _materialize_active_a_minute_batch_direct_staging_artifacts(
                            args=args,
                            active_scope_artifacts=artifacts,
                            output_dir=Path(args.output_dir),
                            observed_at=_runner_observed_at(args),
                            deadline_check=deadline_check,
                        )
                        current_day_source_provider_result = _skipped_current_day_source_provider_result(
                            skip_reason=ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE,
                            staging_artifact_count=direct_staging_count,
                        )
                        current_day_source_provider_result["mode"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
                    c1_active_a_minute_batch_summary = _merge_active_a_minute_batch_execution_summary(
                        c1_active_a_minute_batch_summary,
                        current_day_source_provider_result=current_day_source_provider_result,
                        staging_artifact_written_count=direct_staging_count,
                    )
                    if _is_post_close_final_a_pass(args):
                        c1_active_a_minute_batch_summary["post_close_final_a_close_grace_pull"] = dict(
                            post_close_final_a_close_grace_pull
                        )
                    if direct_staging_count > 0:
                        c1_active_a_minute_batch_summary["ready_handoff_artifacts"] = [
                            dict(item) for item in artifacts
                        ]
                    args.c1_active_a_minute_batch_summary = c1_active_a_minute_batch_summary
                elif current_day_source_provider_adapter is not None:
                    current_day_source_provider_result = _run_current_day_source_provider_adapter(
                        args=args,
                        active_scope_artifacts=artifacts,
                        output_dir=Path(args.output_dir),
                        current_day_source_provider_adapter=current_day_source_provider_adapter,
                        deadline_check=deadline_check,
                    )
                if not (
                    staging_priority_skip_reason == ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
                    and direct_staging_count > 0
                ):
                    try:
                        deadline_check("current_day_source_provider")
                    except FastlaneShellBlocked as exc:
                        if _current_day_source_provider_progress_timeout(
                            exc,
                            current_day_source_provider_result=current_day_source_provider_result,
                        ):
                            manifest = _current_day_source_provider_chunk_waiting_manifest(
                                args=args,
                                invocation_id=invocation_id,
                                artifacts=artifacts,
                                output_dir=Path(args.output_dir),
                                current_day_source_provider_result=current_day_source_provider_result or {},
                                started=started,
                                now_monotonic=now_monotonic,
                            )
                            manifest["lane_results"] = dict(lane_results)
                            return manifest
                        raise
                if existing_source_staging_count <= 0 and staging_priority_skip_reason != ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE:
                    _materialize_missing_scoped_current_day_staging_artifacts(
                        args=args,
                        active_scope_artifacts=artifacts,
                        output_dir=Path(args.output_dir),
                        observed_at=_runner_observed_at(args),
                        deadline_check=deadline_check,
                    )
                    deadline_check("current_day_staging_materialized")
                lane_results["c1_lane"] = _lane_result_after_c1_execution(
                    lane_results.get("c1_lane") or {},
                    existing_source_staging_count=existing_source_staging_count,
                    current_day_source_provider_result=current_day_source_provider_result,
                )
                if c1_active_a_minute_batch_summary:
                    lane_results["c1_lane"] = _lane_result_from_active_a_minute_batch_summary(
                        c1_active_a_minute_batch_summary,
                        selected_artifacts=artifacts,
                        observed_at=_runner_observed_at(args),
                    )
                    ready_handoff_artifacts = [
                        dict(item)
                        for item in (c1_active_a_minute_batch_summary or {}).get("ready_handoff_artifacts", [])
                        if isinstance(item, Mapping)
                    ]
                    if scoped_executor is None and int(
                        c1_active_a_minute_batch_summary.get("selected_candidate_count") or 0
                    ) > 0 and not ready_handoff_artifacts and not metric_context_priority_artifacts:
                        source_written = (
                            int(c1_active_a_minute_batch_summary.get("source_artifact_written_count") or 0) > 0
                        )
                        staging_written = (
                            int(c1_active_a_minute_batch_summary.get("staging_artifact_written_count") or 0) > 0
                        )
                        reason = (
                            "c1_active_a_minute_batch_ready_for_n3t_lane"
                            if source_written or staging_written
                            else "c1_active_a_minute_batch_chunk_incomplete"
                        )
                        return {
                            "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
                            "reason": reason,
                            "invocation_id": invocation_id,
                            "fastlane_lane_id": args.fastlane_lane_id,
                            "active_scope_artifact_count": len(artifacts),
                            "artifact_paths": {
                                "active_scope_artifact_dir": args.active_scope_artifact_dir,
                                "output_dir": args.output_dir,
                            },
                            "counts": {
                                "active_scope_artifact_count": len(artifacts),
                                "active_scope_artifact_row_count": sum(
                                    int(item.get("scope_count") or 0) for item in artifacts
                                ),
                            },
                            "lane_results": dict(lane_results),
                            "current_day_source_provider_result": current_day_source_provider_result,
                            "c1_active_a_minute_batch": dict(c1_active_a_minute_batch_summary),
                            "post_close_final_a_close_grace_pull": dict(
                                post_close_final_a_close_grace_pull
                            ),
                            "boundary": _boundary(),
                            "bounded": {
                                "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
                                "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
                            },
                        }
                metric_context_priority_artifacts, metric_context_priority_summary = (
                    _select_existing_staging_metric_context_artifact_chunk(
                        active_scope_artifacts=(
                            _dedupe_active_scope_artifacts_by_namespace(
                                ready_handoff_artifacts + n3t_candidate_scope_artifacts
                            )
                            if ready_handoff_artifacts
                            else n3t_candidate_scope_artifacts
                        ),
                        output_dir=Path(args.output_dir),
                        metric_context_source_dir=Path(metric_source_dir_text) if metric_source_dir_text else None,
                        previous_context_dir=Path(previous_context_dir_text) if previous_context_dir_text else None,
                        max_candidates=_existing_staging_metric_context_max_candidates(args),
                        allow_previous_day_context_missing=bool(
                            str(getattr(args, "previous_day_context_provider", "") or "").strip()
                        ),
                    )
                )
                if metric_context_priority_artifacts:
                    artifacts = metric_context_priority_artifacts
                    args.prevctx_to_metric_context_chunk_summary = metric_context_priority_summary
                    lane_results["n3t_lane"] = _lane_result_from_priority_summary(
                        lane_name="n3t_lane",
                        summary=metric_context_priority_summary,
                        default_reason="n3t_lane_no_ready_staging",
                        selected_artifacts=metric_context_priority_artifacts,
                        observed_at=_runner_observed_at(args),
                    )
            else:
                current_day_source_provider_result = _skipped_current_day_source_provider_result(
                    skip_reason="existing_staging_metric_context_interleave_prioritized",
                    metric_context_candidate_count=len(metric_context_priority_artifacts),
                )
        scoped_executor_plan = _build_scoped_executor_plan(
            active_scope_artifacts=artifacts,
            output_dir=Path(args.output_dir),
            plan_status="blocked" if args.execute else "planned",
            blocked_reason="scoped_c1_n3t_executor_required" if args.execute else None,
        )
        if not (args.execute and scoped_executor is None and metric_context_priority_artifacts):
            deadline_check("scoped_executor_plan_built")
        if args.execute and scoped_executor is None:
            if metric_context_priority_artifacts and _metric_context_priority_requires_builder(
                metric_context_priority_summary
            ):
                if metric_context_builder_adapter is None:
                    if previous_day_context_provider_adapter is None:
                        previous_day_context_provider_adapter = _configured_previous_day_context_provider_adapter(args)
                    metric_context_builder_adapter = _configured_metric_context_builder_adapter(
                        args,
                        previous_day_context_provider_adapter=previous_day_context_provider_adapter,
                    )
                metric_context_builder_result = _run_metric_context_builder_adapter(
                    args=args,
                    scoped_executor_plan=scoped_executor_plan,
                    metric_context_builder_adapter=metric_context_builder_adapter,
                )
                try:
                    deadline_check("metric_context_builder")
                except FastlaneShellBlocked as exc:
                    if _prevctx_to_metric_context_progress_timeout(
                        exc,
                        chunk_summary=metric_context_priority_summary,
                        metric_context_builder_result=metric_context_builder_result,
                    ):
                        partial_writer_flush = _flush_metric_context_chunk_to_n3t_writer(
                            args=args,
                            active_scope_artifacts=artifacts,
                            output_dir=Path(args.output_dir),
                            chunk_summary=metric_context_priority_summary or {},
                            n3t_writer_adapter=n3t_writer_adapter,
                        )
                        manifest = _prevctx_to_metric_context_chunk_waiting_manifest(
                            args=args,
                            invocation_id=invocation_id,
                            artifacts=artifacts,
                            output_dir=Path(args.output_dir),
                            chunk_summary=metric_context_priority_summary or {},
                            metric_context_builder_result=metric_context_builder_result or {},
                            started=started,
                            now_monotonic=now_monotonic,
                        )
                        manifest["lane_results"] = dict(lane_results)
                        if partial_writer_flush:
                            manifest["partial_n3t_writer_flush"] = partial_writer_flush
                            if partial_writer_flush.get("execute_result"):
                                manifest["execute_result"] = partial_writer_flush["execute_result"]
                            if partial_writer_flush.get("n3t_writer_done_markers"):
                                manifest["n3t_writer_done_markers"] = list(
                                    partial_writer_flush["n3t_writer_done_markers"]
                                )
                        return manifest
                    raise
                scoped_executor_plan = _build_scoped_executor_plan(
                    active_scope_artifacts=artifacts,
                    output_dir=Path(args.output_dir),
                    plan_status="blocked",
                    blocked_reason="scoped_c1_n3t_executor_required",
                )
                deadline_check("scoped_executor_plan_refreshed")
        if args.execute:
            handoff_only = False
            if scoped_executor is not None:
                deadline_check("before_scoped_executor")
                execute_result = dict(scoped_executor(args=args, active_scope_artifacts=artifacts) or {})
            else:
                n3t_writer_inputs = _n3t_writer_inputs_from_plan(scoped_executor_plan)
                if not n3t_writer_inputs:
                    deadline_check("n3t_writer_inputs_selected")
                    if _scoped_executor_plan_only_clean_noop(scoped_executor_plan) or (
                        metric_context_builder_result is not None
                        and not _scoped_executor_plan_has_contract_blocker(scoped_executor_plan)
                    ):
                        return {
                            "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
                            "reason": "waiting_for_valid_c1_n3t_candidate",
                            "invocation_id": invocation_id,
                            "fastlane_lane_id": args.fastlane_lane_id,
                            "fastlane": {
                                "session_phase": getattr(args, "fastlane_session_phase", ""),
                                "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
                            },
                            "execute_requested": True,
                            "writes_enabled": False,
                            "artifact_first_only": True,
                            "active_scope_artifact_dir": args.active_scope_artifact_dir,
                            "output_dir": args.output_dir,
                            "active_scope_artifact_count": len(artifacts),
                            "active_scope_artifacts": artifacts,
                            "lane_results": dict(lane_results),
                            "scoped_executor_plan": scoped_executor_plan,
                            "current_day_source_provider_result": current_day_source_provider_result,
                            "c1_active_a_minute_batch": dict(
                                c1_active_a_minute_batch_summary
                                or getattr(args, "c1_active_a_minute_batch_summary", {})
                                or {}
                            ),
                            "metric_context_builder_result": metric_context_builder_result,
                            "scoped_pull_plan_chunk": dict(
                                getattr(args, "scoped_pull_plan_chunk_summary", {}) or {}
                            ),
                            "bounded": {
                                "max_runtime_seconds": float(args.max_runtime_seconds),
                                "elapsed_seconds": round(now_monotonic() - started, 6),
                            },
                            "boundary": _boundary(),
                        }
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
            n3t_writer_done_markers = _write_n3t_writer_done_markers(
                output_dir=Path(args.output_dir),
                n3t_writer_inputs=n3t_writer_inputs,
                execute_result=execute_result,
                observed_at=_runner_observed_at(args),
            )
            if handoff_only and _metric_context_chunk_has_remaining(metric_context_priority_summary):
                manifest = _prevctx_to_metric_context_chunk_waiting_manifest(
                    args=args,
                    invocation_id=invocation_id,
                    artifacts=artifacts,
                    output_dir=Path(args.output_dir),
                    chunk_summary=metric_context_priority_summary or {},
                    metric_context_builder_result=metric_context_builder_result or {},
                    started=started,
                    now_monotonic=now_monotonic,
                )
                manifest["lane_results"] = dict(lane_results)
                manifest["scoped_executor_plan"] = scoped_executor_plan
                manifest["current_day_source_provider_result"] = current_day_source_provider_result
                manifest["c1_active_a_minute_batch"] = dict(
                    c1_active_a_minute_batch_summary
                    or getattr(args, "c1_active_a_minute_batch_summary", {})
                    or {}
                )
                manifest["execute_result"] = execute_result
                manifest["n3t_writer_done_markers"] = list(n3t_writer_done_markers)
                return manifest
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
                "lane_results": dict(lane_results),
                "scoped_executor_plan": scoped_executor_plan,
                "current_day_source_provider_result": current_day_source_provider_result,
                "c1_active_a_minute_batch": dict(
                    c1_active_a_minute_batch_summary
                    or getattr(args, "c1_active_a_minute_batch_summary", {})
                    or {}
                ),
                "metric_context_builder_result": metric_context_builder_result,
                "scoped_pull_plan_chunk": dict(getattr(args, "scoped_pull_plan_chunk_summary", {}) or {}),
                "execute_result": execute_result,
                "n3t_writer_done_markers": list(n3t_writer_done_markers),
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
            "lane_results": dict(lane_results),
            "scoped_executor_plan": scoped_executor_plan,
            "current_day_source_provider_result": current_day_source_provider_result,
            "c1_active_a_minute_batch": dict(
                c1_active_a_minute_batch_summary
                or getattr(args, "c1_active_a_minute_batch_summary", {})
                or {}
            ),
            "post_close_final_a_close_grace_pull": dict(
                post_close_final_a_close_grace_pull
                or getattr(args, "post_close_final_a_close_grace_pull", {})
                or {}
            ),
            "metric_context_builder_result": metric_context_builder_result,
            "scoped_pull_plan_chunk": dict(getattr(args, "scoped_pull_plan_chunk_summary", {}) or {}),
            "bounded": {
                "max_runtime_seconds": float(args.max_runtime_seconds),
                "elapsed_seconds": round(now_monotonic() - started, 6),
            },
            "boundary": _boundary(),
            "next_required_gate": "N3_C1_N3T_SCOPED_REALTIME_POLLER_EXECUTE_GATE",
        }
    except FastlaneShellBlocked as exc:
        if str(exc) == "post_close_final_a_pass_done":
            return {
                "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
                "reason": "post_close_final_a_pass_noop",
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
                "lane_results": dict(lane_results),
                "c1_active_a_minute_batch": dict(
                    c1_active_a_minute_batch_summary
                    or getattr(args, "c1_active_a_minute_batch_summary", {})
                    or {}
                ),
                "boundary": _boundary(),
            }
        if _is_post_close_final_a_pass(args) and str(exc).startswith("max_runtime_seconds_exceeded:"):
            chunk_summary = dict(getattr(args, "post_close_final_a_pass_chunk_summary", {}) or {})
            if chunk_summary:
                return _post_close_final_a_pass_chunk_waiting_manifest(
                    args=args,
                    invocation_id=invocation_id,
                    artifacts=artifacts,
                    output_dir=Path(str(getattr(args, "output_dir", "") or ".")),
                    chunk_summary=chunk_summary,
                    started=started,
                    now_monotonic=now_monotonic,
                )
        if str(exc).startswith("max_runtime_seconds_exceeded:"):
            c1_summary = dict(getattr(args, "c1_active_a_minute_batch_summary", {}) or {})
            if (
                c1_summary.get("mode") == ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
                and current_day_source_provider_result is not None
                and int(c1_summary.get("selected_candidate_count") or 0) > 0
            ):
                manifest = _current_day_source_provider_chunk_waiting_manifest(
                    args=args,
                    invocation_id=invocation_id,
                    artifacts=artifacts,
                    output_dir=Path(str(getattr(args, "output_dir", "") or ".")),
                    current_day_source_provider_result=current_day_source_provider_result or {},
                    started=started,
                    now_monotonic=now_monotonic,
                )
                manifest["lane_results"] = dict(lane_results)
                return manifest
            chunk_summary = dict(getattr(args, "prevctx_to_metric_context_chunk_summary", {}) or {})
            if _prevctx_to_metric_context_progress_timeout(
                exc,
                chunk_summary=chunk_summary,
                metric_context_builder_result=metric_context_builder_result,
            ):
                return _prevctx_to_metric_context_chunk_waiting_manifest(
                    args=args,
                    invocation_id=invocation_id,
                    artifacts=artifacts,
                    output_dir=Path(str(getattr(args, "output_dir", "") or ".")),
                    chunk_summary=chunk_summary,
                    metric_context_builder_result=metric_context_builder_result or {},
                    started=started,
                    now_monotonic=now_monotonic,
                )
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
            "lane_results": dict(lane_results),
            "current_day_source_provider_result": current_day_source_provider_result,
            "c1_active_a_minute_batch": dict(
                c1_active_a_minute_batch_summary
                or getattr(args, "c1_active_a_minute_batch_summary", {})
                or {}
            ),
            "post_close_final_a_close_grace_pull": dict(
                post_close_final_a_close_grace_pull
                or getattr(args, "post_close_final_a_close_grace_pull", {})
                or {}
            ),
            "metric_context_builder_result": metric_context_builder_result,
            "scoped_pull_plan_chunk": dict(getattr(args, "scoped_pull_plan_chunk_summary", {}) or {}),
            "scoped_executor_plan": _build_scoped_executor_plan(
                active_scope_artifacts=artifacts,
                output_dir=Path(str(getattr(args, "output_dir", "") or ".")),
                plan_status="blocked",
                blocked_reason=str(exc),
            ),
            "boundary": _boundary(),
        }


def _empty_lane_result(*, lane_name: str, reason: str) -> dict[str, Any]:
    return {
        "lane_name": lane_name,
        "selected_candidate_count": 0,
        "processed_candidate_count": 0,
        "skipped_candidate_count": 0,
        "failed_candidate_count": 0,
        "remaining_candidate_count": 0,
        "oldest_pending_trigger_time": "",
        "max_pending_age_seconds": 0,
        "reason": reason,
        "hard_blocker_count": 0,
    }


def _initial_independent_lane_results() -> dict[str, Any]:
    return {
        "n3t_lane": _empty_lane_result(
            lane_name="n3t_lane",
            reason="not_started",
        ),
        "c1_lane": _empty_lane_result(
            lane_name="c1_lane",
            reason="not_started",
        ),
    }


def _lane_result_from_priority_summary(
    *,
    lane_name: str,
    summary: Mapping[str, Any] | None,
    default_reason: str,
    selected_artifacts: Sequence[Mapping[str, Any]] = (),
    observed_at: str = "",
) -> dict[str, Any]:
    source = dict(summary or {})
    selected = int(source.get("selected_candidate_count") or 0)
    processed = int(source.get("processed_candidate_count") or selected)
    remaining = int(source.get("remaining_candidate_count") or 0)
    skipped = int(source.get("skipped_candidate_count") or remaining)
    reason = str(source.get("reason") or default_reason)
    if selected <= 0:
        processed = 0
        reason = default_reason
    result = {
        "lane_name": lane_name,
        "selected_candidate_count": selected,
        "processed_candidate_count": processed,
        "skipped_candidate_count": skipped,
        "failed_candidate_count": int(source.get("failed_candidate_count") or 0),
        "remaining_candidate_count": remaining,
        "reason": reason,
        "hard_blocker_count": 0,
    }
    result.update(_lane_pending_latency_fields(selected_artifacts, observed_at=observed_at))
    return result


def _lane_result_from_c1_selection(
    *,
    prioritized_staging_artifacts: Sequence[Mapping[str, Any]],
    scoped_pull_plan_summary: Mapping[str, Any] | None,
    skip_reason: str,
    selected_artifacts: Sequence[Mapping[str, Any]] = (),
    observed_at: str = "",
) -> dict[str, Any]:
    if prioritized_staging_artifacts:
        selected = len(prioritized_staging_artifacts)
        result = {
            "lane_name": "c1_lane",
            "selected_candidate_count": selected,
            "processed_candidate_count": 0,
            "skipped_candidate_count": 0,
            "failed_candidate_count": 0,
            "remaining_candidate_count": 0,
            "reason": skip_reason or "existing_source_staging_prioritized",
            "hard_blocker_count": 0,
        }
        result.update(_lane_pending_latency_fields(selected_artifacts, observed_at=observed_at))
        return result
    source = dict(scoped_pull_plan_summary or {})
    selected = int(source.get("selected_candidate_count") or 0)
    remaining = int(source.get("remaining_candidate_count") or 0)
    skipped = int(source.get("skipped_candidate_count") or remaining)
    result = {
        "lane_name": "c1_lane",
        "selected_candidate_count": selected,
        "processed_candidate_count": 0,
        "skipped_candidate_count": skipped,
        "failed_candidate_count": int(source.get("failed_candidate_count") or 0),
        "remaining_candidate_count": remaining,
        "reason": str(source.get("reason") or "c1_lane_no_candidate"),
        "hard_blocker_count": 0,
    }
    result.update(_lane_pending_latency_fields(selected_artifacts, observed_at=observed_at))
    return result


def _lane_pending_latency_fields(
    selected_artifacts: Sequence[Mapping[str, Any]],
    *,
    observed_at: str,
) -> dict[str, Any]:
    parsed: list[tuple[datetime, str]] = []
    for artifact in selected_artifacts:
        payload = _active_scope_payload_from_candidate(artifact)
        for ref in _iter_active_scope_ref_records(payload):
            for key in ("source_trigger_event_time", "trigger_time", "latest_n4_event_time", "event_time"):
                text = str(ref.get(key) or "").strip()
                if not text:
                    continue
                dt = _parse_iso_datetime_or_none(text)
                if dt is not None:
                    parsed.append((dt, text))
                    break
    if not parsed:
        return {"oldest_pending_trigger_time": "", "max_pending_age_seconds": 0}
    parsed.sort(key=lambda item: item[0])
    oldest_dt, oldest_text = parsed[0]
    observed_dt = _parse_iso_datetime_or_none(observed_at)
    if observed_dt is None:
        return {"oldest_pending_trigger_time": oldest_text, "max_pending_age_seconds": 0}
    if oldest_dt.tzinfo is None and observed_dt.tzinfo is not None:
        oldest_dt = oldest_dt.replace(tzinfo=observed_dt.tzinfo)
    if oldest_dt.tzinfo is not None and observed_dt.tzinfo is None:
        observed_dt = observed_dt.replace(tzinfo=oldest_dt.tzinfo)
    age_seconds = max(0, int((observed_dt - oldest_dt).total_seconds()))
    return {"oldest_pending_trigger_time": oldest_text, "max_pending_age_seconds": age_seconds}


def _active_scope_payload_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    path = str(candidate.get("path") or candidate.get("input_active_scope_artifact_path") or "").strip()
    if path:
        source = _read_optional_json_artifact(path)
        if source.get("exists"):
            return dict(source.get("payload") or {})
    return dict(candidate.get("payload") or candidate)


def _iter_active_scope_ref_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if isinstance(payload.get("active_tracking_refs"), list):
        refs.extend(dict(item) for item in payload.get("active_tracking_refs") or [] if isinstance(item, Mapping))
    for row in payload.get("scope_rows") or []:
        if not isinstance(row, Mapping):
            continue
        if isinstance(row.get("active_tracking_refs"), list):
            refs.extend(dict(item) for item in row.get("active_tracking_refs") or [] if isinstance(item, Mapping))
    if not refs:
        refs.append(dict(payload))
    return refs


def _parse_iso_datetime_or_none(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _wall_clock_observed_at() -> str:
    return datetime.now().astimezone().isoformat()


def _elapsed_ms(*, started_at: Any, completed_at: Any) -> int | None:
    started = _parse_iso_datetime_or_none(str(started_at or ""))
    completed = _parse_iso_datetime_or_none(str(completed_at or ""))
    if started is None or completed is None:
        return None
    return max(0, int(round((completed - started).total_seconds() * 1000)))


def _minute_closed_to_observed_ms(
    *,
    for_trade_date: str,
    target_hhmm: str,
    observed_at: str,
) -> int | None:
    observed = _parse_iso_datetime_or_none(observed_at)
    label = _hhmm_to_minute_label(target_hhmm)
    if observed is None or not re.fullmatch(r"\d{8}", str(for_trade_date or "")):
        return None
    if not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", label):
        return None
    minute_started = datetime.fromisoformat(
        f"{for_trade_date[:4]}-{for_trade_date[4:6]}-{for_trade_date[6:8]}T{label}:00+08:00"
    )
    minute_closed = minute_started + timedelta(minutes=1)
    return max(0, int(round((observed - minute_closed).total_seconds() * 1000)))


def _lane_result_after_c1_execution(
    lane_result: Mapping[str, Any],
    *,
    existing_source_staging_count: int,
    current_day_source_provider_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result = dict(lane_result or _empty_lane_result(lane_name="c1_lane", reason="c1_lane_no_candidate"))
    processed = int(existing_source_staging_count or 0)
    provider = dict(current_day_source_provider_result or {})
    processed += int(provider.get("artifact_count") or 0)
    failed = int(provider.get("failed_candidate_count") or 0)
    if provider.get("artifact_written") and processed <= 0:
        processed = 1
    selected = int(result.get("selected_candidate_count") or processed)
    result["selected_candidate_count"] = selected
    result["processed_candidate_count"] = processed
    result["failed_candidate_count"] = failed
    result["remaining_candidate_count"] = max(0, int(result.get("remaining_candidate_count") or 0))
    result["skipped_candidate_count"] = max(0, int(result.get("skipped_candidate_count") or 0))
    if processed > 0 and result.get("reason") in {"c1_lane_no_candidate", "scoped_pull_plan_candidate_chunk_ready"}:
        result["reason"] = "c1_lane_progressed"
    result.setdefault("lane_name", "c1_lane")
    result.setdefault("hard_blocker_count", 0)
    return result


def _lane_result_from_active_a_minute_batch_summary(
    summary: Mapping[str, Any],
    *,
    selected_artifacts: Sequence[Mapping[str, Any]] = (),
    observed_at: str = "",
) -> dict[str, Any]:
    source = dict(summary or {})
    selected = int(source.get("selected_object_count") or source.get("selected_candidate_count") or 0)
    processed = int(
        source.get("staging_artifact_written_count")
        or source.get("source_artifact_written_count")
        or source.get("processed_candidate_count")
        or 0
    )
    result = {
        "lane_name": "c1_lane",
        "mode": ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE,
        "selected_candidate_count": selected,
        "selected_object_count": selected,
        "selected_ref_count": int(source.get("selected_ref_count") or 0),
        "processed_candidate_count": processed,
        "skipped_candidate_count": int(source.get("skipped_existing_ready_count") or 0),
        "failed_candidate_count": int(source.get("failed_candidate_count") or 0),
        "remaining_candidate_count": int(source.get("remaining_candidate_count") or 0),
        "reason": str(source.get("reason") or ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE),
        "hard_blocker_count": 0,
    }
    result.update(_lane_pending_latency_fields(selected_artifacts, observed_at=observed_at))
    return result


def _active_a_minute_batch_controls_c1(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any] | None,
) -> bool:
    source = dict(summary or {})
    if source.get("mode") != ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE:
        return False
    return any(item.get("object_scope_ref_fanout") is True for item in active_scope_artifacts)


def _active_a_minute_batch_waiting_reason(summary: Mapping[str, Any]) -> str:
    source = dict(summary or {})
    if source.get("reason") == "active_a_minute_batch_closed_minute_unavailable":
        return "c1_active_a_minute_batch_closed_minute_unavailable"
    if (
        int(source.get("source_artifact_written_count") or 0) > 0
        or int(source.get("staging_artifact_written_count") or 0) > 0
        or int(source.get("skipped_existing_ready_count") or 0) > 0
    ):
        return "c1_active_a_minute_batch_ready_for_n3t_lane"
    return "c1_active_a_minute_batch_chunk_incomplete"


def _metric_context_chunk_has_remaining(summary: Mapping[str, Any] | None) -> bool:
    source = dict(summary or {})
    return int(source.get("remaining_candidate_count") or 0) > 0


def _current_day_source_provider_progress_timeout(
    exc: FastlaneShellBlocked,
    *,
    current_day_source_provider_result: Mapping[str, Any] | None,
) -> bool:
    if str(exc) != "max_runtime_seconds_exceeded:current_day_source_provider":
        return False
    result = dict(current_day_source_provider_result or {})
    return bool(result.get("artifact_written")) or int(result.get("artifact_count") or 0) > 0


def _current_day_source_provider_chunk_waiting_manifest(
    *,
    args: argparse.Namespace,
    invocation_id: str,
    artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    current_day_source_provider_result: Mapping[str, Any],
    started: float,
    now_monotonic: Any,
) -> dict[str, Any]:
    c1_active_summary = dict(getattr(args, "c1_active_a_minute_batch_summary", {}) or {})
    reason = (
        "c1_active_a_minute_batch_chunk_incomplete"
        if c1_active_summary.get("mode") == ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
        else "current_day_source_provider_chunk_incomplete"
    )
    return {
        "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
        "reason": reason,
        "invocation_id": invocation_id,
        "fastlane_lane_id": getattr(args, "fastlane_lane_id", ""),
        "fastlane": {
            "session_phase": getattr(args, "fastlane_session_phase", ""),
            "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
        },
        "execute_requested": bool(args.execute),
        "writes_enabled": False,
        "artifact_first_only": True,
        "active_scope_artifact_dir": getattr(args, "active_scope_artifact_dir", ""),
        "output_dir": getattr(args, "output_dir", ""),
        "active_scope_artifact_count": len(artifacts),
        "active_scope_artifacts": [dict(item) for item in artifacts],
        "current_day_source_provider_result": dict(current_day_source_provider_result),
        "c1_active_a_minute_batch": c1_active_summary,
        "scoped_executor_plan": _build_scoped_executor_plan(
            active_scope_artifacts=artifacts,
            output_dir=output_dir,
            plan_status="blocked",
            blocked_reason=reason,
        ),
        "bounded": {
            "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
            "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
        },
        "boundary": _boundary(),
    }


def _prevctx_to_metric_context_progress_timeout(
    exc: FastlaneShellBlocked,
    *,
    chunk_summary: Mapping[str, Any] | None,
    metric_context_builder_result: Mapping[str, Any] | None,
) -> bool:
    if not str(exc).startswith("max_runtime_seconds_exceeded:"):
        return False
    result = dict(metric_context_builder_result or {})
    if bool(result.get("artifact_written")) or int(result.get("artifact_count") or 0) > 0:
        return True
    summary = dict(chunk_summary or {})
    if summary.get("reason") != "prevctx_to_metric_context_chunk_incomplete":
        return False
    return False


def _prevctx_to_metric_context_chunk_waiting_manifest(
    *,
    args: argparse.Namespace,
    invocation_id: str,
    artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    chunk_summary: Mapping[str, Any],
    metric_context_builder_result: Mapping[str, Any],
    started: float,
    now_monotonic: Any,
) -> dict[str, Any]:
    return {
        "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
        "reason": "prevctx_to_metric_context_chunk_incomplete",
        "invocation_id": invocation_id,
        "fastlane_lane_id": getattr(args, "fastlane_lane_id", ""),
        "fastlane": {
            "session_phase": getattr(args, "fastlane_session_phase", ""),
            "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
        },
        "execute_requested": bool(args.execute),
        "writes_enabled": False,
        "artifact_first_only": True,
        "active_scope_artifact_dir": getattr(args, "active_scope_artifact_dir", ""),
        "output_dir": getattr(args, "output_dir", ""),
        "active_scope_artifact_count": len(artifacts),
        "active_scope_artifacts": [dict(item) for item in artifacts],
        "prevctx_to_metric_context_chunk": dict(chunk_summary),
        "metric_context_builder_result": dict(metric_context_builder_result),
        "scoped_executor_plan": _build_scoped_executor_plan(
            active_scope_artifacts=artifacts,
            output_dir=output_dir,
            plan_status="blocked",
            blocked_reason="prevctx_to_metric_context_chunk_incomplete",
        ),
        "bounded": {
            "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
            "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
        },
        "boundary": _boundary(),
    }


def _flush_metric_context_chunk_to_n3t_writer(
    *,
    args: argparse.Namespace,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    chunk_summary: Mapping[str, Any],
    n3t_writer_adapter: Callable[..., Mapping[str, Any]] | None,
) -> dict[str, Any]:
    selected_artifacts = _active_scope_artifacts_for_metric_context_chunk(
        active_scope_artifacts=active_scope_artifacts,
        chunk_summary=chunk_summary,
    )
    if not selected_artifacts:
        return {}
    scoped_executor_plan = _build_scoped_executor_plan(
        active_scope_artifacts=selected_artifacts,
        output_dir=output_dir,
        plan_status="planned",
        blocked_reason=None,
    )
    n3t_writer_inputs = _n3t_writer_inputs_from_plan(scoped_executor_plan)
    if not n3t_writer_inputs:
        return {
            "n3t_writer_input_count": 0,
            "selected_artifact_count": len(selected_artifacts),
            "reason": "n3t_writer_inputs_not_ready_after_metric_context_chunk",
        }
    adapter = n3t_writer_adapter
    handoff_only = False
    if adapter is None:
        adapter = _configured_n3t_writer_adapter(args)
    if adapter is None:
        execute_result = _build_n3t_writer_handoff_result(n3t_writer_inputs=n3t_writer_inputs)
        handoff_only = True
    else:
        execute_result = dict(adapter(args=args, n3t_writer_inputs=n3t_writer_inputs) or {})
    _validate_execute_result(execute_result)
    done_markers = _write_n3t_writer_done_markers(
        output_dir=output_dir,
        n3t_writer_inputs=n3t_writer_inputs,
        execute_result=execute_result,
        observed_at=_runner_observed_at(args),
    )
    return {
        "reason": "metric_context_chunk_flushed_to_n3t_writer",
        "handoff_only": handoff_only,
        "selected_artifact_count": len(selected_artifacts),
        "n3t_writer_input_count": len(n3t_writer_inputs),
        "execute_result": execute_result,
        "n3t_writer_done_markers": done_markers,
        "scoped_executor_plan": scoped_executor_plan,
    }


def _active_scope_artifacts_for_metric_context_chunk(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    chunk_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    selected_keys = {
        (
            str(item.get("target_hhmm") or ""),
            str(item.get("source_run_hash") or ""),
        )
        for item in chunk_summary.get("selected_source_runs") or []
        if isinstance(item, Mapping)
    }
    if not selected_keys:
        return []
    selected: list[dict[str, Any]] = []
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        key = (str(context.get("target_hhmm") or ""), str(context.get("source_run_hash") or ""))
        if key in selected_keys:
            selected.append(dict(artifact))
    return selected


def _scoped_pull_plan_progress_timeout(
    exc: FastlaneShellBlocked,
    *,
    chunk_summary: Mapping[str, Any] | None,
) -> bool:
    if str(exc) != "max_runtime_seconds_exceeded:scoped_pull_plan_candidate":
        return False
    summary = dict(chunk_summary or {})
    return summary.get("strategy") == "scoped_pull_plan_candidate_bounded_chunk_v1"


def _scoped_pull_plan_chunk_waiting_manifest(
    *,
    args: argparse.Namespace,
    invocation_id: str,
    artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    chunk_summary: Mapping[str, Any],
    started: float,
    now_monotonic: Any,
) -> dict[str, Any]:
    return {
        "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
        "reason": "scoped_pull_plan_candidate_chunk_incomplete",
        "invocation_id": invocation_id,
        "fastlane_lane_id": getattr(args, "fastlane_lane_id", ""),
        "fastlane": {
            "session_phase": getattr(args, "fastlane_session_phase", ""),
            "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
        },
        "execute_requested": bool(args.execute),
        "writes_enabled": False,
        "artifact_first_only": True,
        "active_scope_artifact_dir": getattr(args, "active_scope_artifact_dir", ""),
        "output_dir": getattr(args, "output_dir", ""),
        "active_scope_artifact_count": len(artifacts),
        "active_scope_artifacts": [dict(item) for item in artifacts],
        "scoped_pull_plan_chunk": dict(chunk_summary),
        "scoped_executor_plan": _build_scoped_executor_plan(
            active_scope_artifacts=artifacts,
            output_dir=output_dir,
            plan_status="blocked",
            blocked_reason="scoped_pull_plan_candidate_chunk_incomplete",
        ),
        "bounded": {
            "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
            "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
        },
        "boundary": _boundary(),
    }


def _skipped_current_day_source_provider_result(
    *,
    skip_reason: str,
    staging_artifact_count: int = 0,
    metric_context_candidate_count: int = 0,
) -> dict[str, Any]:
    return {
        "adapter_type": "n3_c1_scoped_current_day_source_rows_provider_adapter_v1",
        "artifact_written": False,
        "artifact_count": 0,
        "source_row_count": 0,
        "skipped": True,
        "skip_reason": skip_reason,
        "staging_artifact_count": int(staging_artifact_count),
        "metric_context_candidate_count": int(metric_context_candidate_count),
        "market_data_pulled": False,
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


def _post_close_final_a_pass_chunk_waiting_manifest(
    *,
    args: argparse.Namespace,
    invocation_id: str,
    artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    chunk_summary: Mapping[str, Any],
    started: float,
    now_monotonic: Any,
) -> dict[str, Any]:
    return {
        "verdict": "N3_C1_N3T_FASTLANE_READINESS_WAITING",
        "reason": "post_close_final_a_pass_chunk_incomplete",
        "invocation_id": invocation_id,
        "fastlane_lane_id": getattr(args, "fastlane_lane_id", ""),
        "fastlane": {
            "session_phase": getattr(args, "fastlane_session_phase", ""),
            "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
        },
        "execute_requested": bool(args.execute),
        "writes_enabled": False,
        "artifact_first_only": True,
        "active_scope_artifact_dir": getattr(args, "active_scope_artifact_dir", ""),
        "output_dir": getattr(args, "output_dir", ""),
        "active_scope_artifact_count": len(artifacts),
        "active_scope_artifacts": [dict(item) for item in artifacts],
        "post_close_final_a_pass_chunk": dict(chunk_summary),
        "scoped_executor_plan": _build_scoped_executor_plan(
            active_scope_artifacts=artifacts,
            output_dir=output_dir,
            plan_status="blocked",
            blocked_reason="post_close_final_a_pass_chunk_incomplete",
        ),
        "bounded": {
            "max_runtime_seconds": float(getattr(args, "max_runtime_seconds", 0.0) or 0.0),
            "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
        },
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
        if _planned_artifact_ready_for_metric_context_lane(artifact)
    ]
    if not candidates:
        return None
    result = dict(metric_context_builder_adapter(args=args, planned_artifacts=candidates) or {})
    _validate_metric_context_builder_result(result)
    return result


def _planned_artifact_ready_for_metric_context_lane(planned_artifact: Mapping[str, Any]) -> bool:
    readiness = dict(planned_artifact.get("component_readiness") or {})
    if readiness.get("status") == "waiting_for_metric_context_artifact":
        return True
    return (
        readiness.get("staging_artifact_exists") is True
        and readiness.get("metric_context_artifact_exists") is not True
        and readiness.get("staging_boundary_rebuild_required") is not True
        and readiness.get("current_day_boundary_rebuild_required") is not True
    )


def _run_current_day_source_provider_adapter(
    *,
    args: argparse.Namespace,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    current_day_source_provider_adapter: Callable[..., Mapping[str, Any]],
    deadline_check: Callable[[str], None] | None = None,
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
    planned_artifacts = list(planned.get("planned_artifacts") or [])
    max_candidates = _current_day_source_provider_max_candidates(args)
    candidates: list[dict[str, Any]] = []
    scanned_count = 0
    for artifact in planned_artifacts:
        scanned_count += 1
        target_hhmm = str(artifact.get("target_hhmm") or "")
        source_run_hash = str(artifact.get("source_run_hash") or "")
        staging_path = Path(str(artifact.get("staging_artifact_path") or ""))
        source_rows = _find_current_day_source_rows_artifact(
            source_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
            namespace_token=str(artifact.get("namespace_token") or ""),
        )
        needs_rebuild = _planned_artifact_needs_current_day_boundary_rebuild(
            artifact,
            source_dir=source_dir,
            existing_source_rows=source_rows,
        )
        if not _planned_artifact_has_executable_pull_plan(artifact):
            continue
        if staging_path.exists() and not needs_rebuild:
            continue
        if source_rows and not needs_rebuild:
            continue
        candidates.append(dict(artifact))
        if len(candidates) >= max_candidates:
            break
    if not candidates:
        return None
    if deadline_check is not None:
        deadline_check("before_current_day_source_provider_adapter")
    result = dict(current_day_source_provider_adapter(args=args, planned_artifacts=candidates) or {})
    selection_reasons = sorted(
        {
            str(artifact.get("c1_lane_selection_reason") or "")
            for artifact in active_scope_artifacts
            if str(artifact.get("c1_lane_selection_reason") or "")
        }
    )
    if selection_reasons:
        result["selection_reason"] = selection_reasons[0] if len(selection_reasons) == 1 else ",".join(selection_reasons)
    result["candidate_scan_bounded"] = True
    result["candidate_scan_limit"] = max_candidates
    result["candidate_scan_scanned_count"] = scanned_count
    result["candidate_count"] = len(candidates)
    result["remaining_candidate_count"] = max(0, len(planned_artifacts) - scanned_count)
    chunk_summary = dict(getattr(args, "scoped_pull_plan_chunk_summary", {}) or {})
    chunk_remaining = int(chunk_summary.get("remaining_candidate_count") or 0)
    if chunk_remaining > int(result["remaining_candidate_count"] or 0):
        result["remaining_candidate_count"] = chunk_remaining
    _validate_current_day_source_provider_result(result)
    return result


def _select_active_a_minute_batch_direct_provider_artifacts(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    source_dir: Path,
    closed_hhmm: str,
    max_candidates: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bounded_max = max(1, int(max_candidates or DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_MAX_CANDIDATES))
    if not re.fullmatch(r"[0-2][0-9][0-5][0-9]", str(closed_hhmm or "")):
        return [], {
            "mode": ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE,
            "strategy": "active_a_minute_batch_direct_provider_v1",
            "reason": "active_a_minute_batch_closed_minute_unavailable",
            "selected_candidate_count": 0,
            "selected_object_count": 0,
            "pending_object_count": 0,
            "remaining_object_count": 0,
            "selected_ref_count": 0,
            "closed_minute_label": "",
            "source_artifact_written_count": 0,
            "staging_artifact_written_count": 0,
            "skipped_existing_ready_count": 0,
            "failed_candidate_count": 0,
            "remaining_candidate_count": 0,
            "selected_source_runs": [],
        }
    candidate_artifacts = [dict(item) for item in active_scope_artifacts]
    records: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str, str]] = set()
    for sequence, artifact in enumerate(candidate_artifacts):
        closed_target_hhmm = str(closed_hhmm)
        source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        if not source["exists"]:
            continue
        source_payload = dict(source.get("payload") or {})
        for artifact_candidate, payload in _active_a_minute_batch_payload_candidates(
            artifact=artifact,
            payload=source_payload,
            closed_hhmm=closed_target_hhmm,
        ):
            target_hhmm = str(payload.get("target_hhmm") or artifact_candidate.get("target_hhmm") or closed_target_hhmm)
            if _hhmm_int(target_hhmm) <= 0 or _hhmm_int(target_hhmm) > _hhmm_int(closed_target_hhmm):
                continue
            if not _active_a_minute_batch_has_ready_ref(payload, closed_hhmm=target_hhmm):
                continue
            source_run_hash = _active_a_minute_batch_source_run_hash(payload, target_hhmm=target_hhmm)
            if not source_run_hash:
                continue
            for_trade_date = str(payload.get("for_trade_date") or artifact_candidate.get("for_trade_date") or "")
            namespace_token = f"{for_trade_date}_{target_hhmm}_{source_run_hash}"
            key = _active_a_minute_batch_object_key(payload, target_hhmm=target_hhmm)
            object_group_key = key[:4]
            if key in seen_keys:
                continue
            seen_keys.add(key)
            item = dict(artifact_candidate)
            item["c1_lane_mode"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
            item["c1_lane_selection_reason"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
            item["target_hhmm"] = target_hhmm
            item["source_run_hash"] = source_run_hash
            item["source_run_namespace"] = namespace_token
            records.append(
                {
                    "artifact": item,
                    "payload": payload,
                    "source_artifact_path": str(source.get("path") or artifact_candidate.get("path") or ""),
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "source_run_namespace": namespace_token,
                    "selected_ref_count": _active_a_minute_batch_ref_count(payload),
                    "object_group_key": object_group_key,
                    "sort_key": (
                        _hhmm_int(target_hhmm),
                        _active_a_minute_batch_object_key(payload, target_hhmm=target_hhmm),
                        sequence,
                    ),
                }
            )
    records.sort(key=lambda item: item["sort_key"])
    pending_records: list[dict[str, Any]] = []
    ready_records: list[dict[str, Any]] = []
    for record in records:
        target_hhmm = str(record.get("target_hhmm") or "")
        source_run_hash = str(record.get("source_run_hash") or "")
        source_run_namespace = str(record.get("source_run_namespace") or "")
        source_rows = _find_current_day_source_rows_artifact(
            source_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
            namespace_token=source_run_namespace,
            exact_only=True,
        )
        staging_path = (
            output_dir
            / "current_day_staging"
            / f"n3_c1_scoped_current_day_staging_v1_{source_run_namespace}_fastlane.json"
        )
        staging = _read_optional_json_artifact(str(staging_path))
        source_ready = bool(source_rows) and not _current_day_artifact_needs_boundary_rebuild(
            source_rows.get("payload") or {}
        )
        staging_ready = bool(staging["exists"]) and not _current_day_artifact_needs_boundary_rebuild(
            staging.get("payload") or {}
        )
        if staging_ready:
            ready_item = dict(record.get("artifact") or {})
            ready_item["c1_lane_mode"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
            ready_item["c1_lane_selection_reason"] = "active_a_minute_batch_existing_ready_handoff"
            ready_item["target_hhmm"] = target_hhmm
            ready_item["source_run_hash"] = source_run_hash
            ready_item["source_run_namespace"] = source_run_namespace
            ready_record = dict(record)
            ready_record["artifact"] = ready_item
            ready_records.append(ready_record)
            continue
        pending_records.append(record)

    pending_object_groups = {
        tuple(item.get("object_group_key") or ())
        for item in pending_records
    }
    selected_object_groups: set[tuple[str, str, str, str]] = set()
    for item in pending_records:
        selected_object_groups.add(tuple(item.get("object_group_key") or ()))
        if len(selected_object_groups) >= bounded_max:
            break
    limited_pending_records = _active_a_minute_batch_limit_records_per_object(pending_records)
    selected_records = [
        item
        for item in limited_pending_records
        if tuple(item.get("object_group_key") or ()) in selected_object_groups
    ]
    latest_provider_records_by_object: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}
    for item in pending_records:
        group_key = tuple(item.get("object_group_key") or ())
        if group_key not in selected_object_groups:
            continue
        latest_provider_records_by_object[group_key] = item
    ready_selected_records = _active_a_minute_batch_limit_records_per_object(ready_records)

    def _materialize_active_a_minute_record(record: Mapping[str, Any]) -> dict[str, Any]:
        artifact_item = dict(record.get("artifact") or {})
        target_hhmm = str(record.get("target_hhmm") or artifact_item.get("target_hhmm") or "")
        source_run_hash = str(record.get("source_run_hash") or artifact_item.get("source_run_hash") or "")
        source_run_namespace = str(record.get("source_run_namespace") or artifact_item.get("source_run_namespace") or "")
        artifact_item["path"] = _persist_active_a_minute_batch_closed_fanout_payload(
            payload=record.get("payload") or {},
            source_artifact_path=str(record.get("source_artifact_path") or artifact_item.get("path") or ""),
            output_dir=output_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
            source_run_namespace=source_run_namespace,
        )
        return artifact_item

    def _materialize_provider_fetch_record(record: Mapping[str, Any]) -> dict[str, Any]:
        artifact_item = _materialize_active_a_minute_record(record)
        target_hhmm = str(record.get("target_hhmm") or artifact_item.get("target_hhmm") or "")
        payload = dict(record.get("payload") or {})
        provider_source_run_hash = _active_a_minute_batch_provider_source_run_hash(
            payload,
            target_hhmm=target_hhmm,
        )
        for_trade_date = str(payload.get("for_trade_date") or artifact_item.get("for_trade_date") or "")
        artifact_item["ref_source_run_hash"] = str(artifact_item.get("source_run_hash") or "")
        artifact_item["ref_source_run_namespace"] = str(artifact_item.get("source_run_namespace") or "")
        artifact_item["source_run_hash"] = provider_source_run_hash
        artifact_item["source_run_namespace"] = (
            f"{for_trade_date}_{target_hhmm}_{provider_source_run_hash}"
        )
        return artifact_item

    selected = [_materialize_active_a_minute_record(item) for item in selected_records]
    provider_fetch_artifacts = [
        _materialize_provider_fetch_record(item)
        for item in latest_provider_records_by_object.values()
    ]
    ready_handoff_artifacts = [_materialize_active_a_minute_record(item) for item in ready_selected_records]
    remaining_count = max(0, len(pending_records) - len(selected_records))
    selected_hhmm = sorted({str(item.get("target_hhmm") or "") for item in selected_records})
    selected_ref_count = sum(
        int(item.get("selected_ref_count") or 0)
        for item in [*selected_records, *ready_selected_records]
    )
    summary = {
        "mode": ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE,
        "strategy": "active_a_minute_batch_direct_provider_v1",
        "reason": (
            "c1_active_a_minute_batch_chunk_incomplete"
            if remaining_count > 0
            else ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
        ),
        "selected_candidate_count": len(selected_records),
        "selected_object_count": len(selected_object_groups),
        "pending_object_count": len(pending_object_groups),
        "remaining_object_count": len(pending_object_groups - selected_object_groups),
        "selected_ref_count": selected_ref_count,
        "closed_minute_label": _hhmm_to_minute_label(selected_hhmm[0]) if len(selected_hhmm) == 1 else "multiple",
        "source_artifact_written_count": 0,
        "staging_artifact_written_count": 0,
        "skipped_existing_ready_count": len(ready_selected_records),
        "ready_handoff_artifacts": ready_handoff_artifacts,
        "provider_fetch_artifacts": provider_fetch_artifacts,
        "failed_candidate_count": 0,
        "remaining_candidate_count": remaining_count,
        "selected_source_runs": [
            {
                "target_hhmm": str(item.get("target_hhmm") or ""),
                "source_run_hash": str(item.get("source_run_hash") or ""),
                "source_run_namespace": str(item.get("source_run_namespace") or ""),
            }
            for item in selected_records
        ],
        "max_minutes_per_object": DEFAULT_ACTIVE_A_MINUTE_BATCH_MAX_MINUTES_PER_OBJECT,
    }
    return selected, summary


def _active_a_minute_batch_limit_records_per_object(
    records: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    counts: dict[tuple[str, str, str, str], int] = {}
    selected: list[Mapping[str, Any]] = []
    limit = max(1, DEFAULT_ACTIVE_A_MINUTE_BATCH_MAX_MINUTES_PER_OBJECT)
    for item in records:
        group_key = tuple(item.get("object_group_key") or ())
        current = counts.get(group_key, 0)
        if current >= limit:
            continue
        counts[group_key] = current + 1
        selected.append(item)
    return selected


def _active_a_minute_batch_payload_candidates(
    *,
    artifact: Mapping[str, Any],
    payload: Mapping[str, Any],
    closed_hhmm: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if artifact.get("object_scope_ref_fanout") is True or payload.get("object_scope_ref_fanout") is True:
        return [(dict(artifact), dict(payload))]
    closed_value = _hhmm_int(closed_hhmm)
    if closed_value <= 0:
        return []
    rows = [dict(row) for row in payload.get("scope_rows") or [] if isinstance(row, Mapping)]
    buckets: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for object_row in rows:
        if str(object_row.get("scope_status") or "active") != "active":
            continue
        for ref_source in object_row.get("active_tracking_refs") or []:
            if not isinstance(ref_source, Mapping):
                continue
            ref = dict(ref_source)
            ref_target = _target_hhmm_from_active_ref(ref)
            if not ref_target:
                continue
            ref_for_trade_date = str(
                ref.get("for_trade_date")
                or object_row.get("for_trade_date")
                or payload.get("for_trade_date")
                or artifact.get("for_trade_date")
                or ""
            )
            target_hhmms = _active_a_minute_batch_target_hhmms(
                for_trade_date=ref_for_trade_date,
                start_hhmm=ref_target,
                closed_hhmm=closed_hhmm,
            )
            if not target_hhmms:
                continue
            # One mootdx response already contains the full intraday series.
            # Materialize every closed cursor minute from that single response
            # so N3T can evaluate the backlog without repeating market pulls.
            direction = str(ref.get("direction") or object_row.get("direction") or "")
            if not direction:
                continue
            for target_hhmm in target_hhmms:
                key = (
                    ref_for_trade_date,
                    str(ref.get("asset_kind") or object_row.get("asset_kind") or ""),
                    str(ref.get("identity_key") or object_row.get("identity_key") or ""),
                    direction,
                    target_hhmm,
                )
                bucket = buckets.setdefault(key, {"object_row": object_row, "refs": [], "target_hhmm": target_hhmm})
                bucket["refs"].append(ref)
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for sequence, bucket in enumerate(buckets.values()):
        refs = sorted(
            (dict(ref) for ref in bucket["refs"]),
            key=lambda ref: (
                _hint_condition_priority(ref.get("condition_key")),
                str(ref.get("source_trigger_event_time") or ref.get("trigger_time") or ref.get("latest_n4_event_time") or ""),
                str(ref.get("condition_key") or ""),
                str(ref.get("state_key") or ""),
            ),
        )
        if not refs:
            continue
        target_hhmm = str(bucket.get("target_hhmm") or closed_hhmm)
        source_run_hash = _object_minute_source_run_hash(
            object_row=bucket["object_row"],
            active_refs=refs,
            target_hhmm=target_hhmm,
        )
        source_trigger_run_id = _joined_source_trigger_run_ids(refs) or str(payload.get("source_trigger_run_id") or "")
        for_trade_date = str(
            refs[0].get("for_trade_date")
            or bucket["object_row"].get("for_trade_date")
            or payload.get("for_trade_date")
            or artifact.get("for_trade_date")
            or ""
        )
        source_run_namespace = f"{for_trade_date}_{target_hhmm}_{source_run_hash}"
        narrowed_payload = _object_scope_ref_fanout_payload(
            payload=payload,
            object_row=bucket["object_row"],
            active_refs=refs,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
            source_run_namespace=source_run_namespace,
            source_trigger_run_id=source_trigger_run_id,
        )
        candidate = dict(artifact)
        candidate.update(
            {
                "for_trade_date": for_trade_date,
                "target_hhmm": target_hhmm,
                "source_trigger_run_id": source_trigger_run_id,
                "source_run_hash": source_run_hash,
                "source_run_namespace": source_run_namespace,
                "scope_count": 1,
                "active_tracking_ref_count": len(refs),
                "object_scope_ref_fanout": True,
                "source_trigger_event_id": _joined_source_trigger_event_ids(refs),
                "source_trigger_event_type": _joined_source_trigger_event_types(refs),
                "source_trigger_event_time": str(
                    refs[0].get("source_trigger_event_time")
                    or refs[0].get("latest_n4_event_time")
                    or refs[0].get("trigger_time")
                    or ""
                ),
                "sort_sequence": sequence,
            }
        )
        candidates.append((candidate, narrowed_payload))
    return candidates


def _object_cursor_batch_hot_path_enabled(args: argparse.Namespace) -> bool:
    if not bool(getattr(args, "scheduler_quiet", False)):
        return False
    if not bool(getattr(args, "execute", False)):
        return False
    return str(getattr(args, "fastlane_session_phase", "") or "") in {"trading", "lunch_break"}


def _object_cursor_batch_candidate_records(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    closed_hhmm: str,
    max_minutes_per_object: int = DEFAULT_OBJECT_CURSOR_BATCH_MAX_MINUTES_PER_OBJECT,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for sequence, artifact in enumerate(active_scope_artifacts):
        source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        if not source["exists"]:
            continue
        payload = dict(source.get("payload") or {})
        for candidate, narrowed_payload in _active_a_minute_batch_payload_candidates(
            artifact=artifact,
            payload=payload,
            closed_hhmm=closed_hhmm,
        ):
            target_hhmm = str(narrowed_payload.get("target_hhmm") or candidate.get("target_hhmm") or "")
            object_key = _active_a_minute_batch_object_key(narrowed_payload, target_hhmm=target_hhmm)[:4]
            if not all(object_key) or not re.fullmatch(r"[0-2][0-9][0-5][0-9]", target_hhmm):
                continue
            source_run_hash = _active_a_minute_batch_source_run_hash(
                narrowed_payload,
                target_hhmm=target_hhmm,
            )
            if not source_run_hash:
                continue
            for_trade_date = object_key[0]
            n3t_metric_run_id = (
                f"n3t_action_confirmation_metric_{for_trade_date}_until_{target_hhmm}__"
                f"fastlane_sr_{source_run_hash}_raw_prevday_c1_amount_v1"
            )
            groups.setdefault(object_key, []).append(
                {
                    "object_key": object_key,
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "source_run_namespace": f"{for_trade_date}_{target_hhmm}_{source_run_hash}",
                    "n3t_metric_run_id": n3t_metric_run_id,
                    "payload": narrowed_payload,
                    "source_active_scope_artifact_path": str(source.get("path") or artifact.get("path") or ""),
                    "source_active_scope_artifact_sha256": str(source.get("sha256") or ""),
                    "selected_ref_count": _active_a_minute_batch_ref_count(narrowed_payload),
                    "sort_sequence": sequence,
                }
            )

    bounded: list[dict[str, Any]] = []
    limit = max(1, int(max_minutes_per_object or DEFAULT_OBJECT_CURSOR_BATCH_MAX_MINUTES_PER_OBJECT))
    for object_key in sorted(groups):
        records_by_target: dict[str, dict[str, Any]] = {}
        for record in sorted(
            groups[object_key],
            key=lambda item: (_hhmm_int(item["target_hhmm"]), int(item.get("sort_sequence") or 0)),
        ):
            records_by_target.setdefault(str(record["target_hhmm"]), record)
        bounded.extend(list(records_by_target.values())[:limit])
    bounded.sort(key=lambda item: (_hhmm_int(item["target_hhmm"]), tuple(item["object_key"])))
    return bounded


def _object_cursor_batch_proof_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    object_key = tuple(record.get("object_key") or ())
    identity_key = str(object_key[2]) if len(object_key) >= 3 else ""
    return (
        str(record.get("n3t_metric_run_id") or ""),
        identity_key,
        _hhmm_to_minute_label(record.get("target_hhmm") or ""),
    )


def _select_pending_object_cursor_batch_records(
    *,
    records: Sequence[Mapping[str, Any]],
    existing_proof_keys: set[tuple[str, str, str]],
    max_objects: int = DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_MAX_CANDIDATES,
    max_proof_rows: int = DEFAULT_OBJECT_CURSOR_BATCH_MAX_PROOF_ROWS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    pending = [dict(record) for record in records if _object_cursor_batch_proof_key(record) not in existing_proof_keys]
    selected_object_keys: set[tuple[str, str, str, str]] = set()
    selected: list[dict[str, Any]] = []
    object_limit = max(1, int(max_objects or DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_MAX_CANDIDATES))
    proof_limit = max(1, int(max_proof_rows or DEFAULT_OBJECT_CURSOR_BATCH_MAX_PROOF_ROWS))
    for record in pending:
        object_key = tuple(record.get("object_key") or ())
        if object_key not in selected_object_keys and len(selected_object_keys) >= object_limit:
            continue
        if object_key not in selected_object_keys:
            selected_object_keys.add(object_key)
        selected.append(record)
        if len(selected) >= proof_limit:
            break
    return selected, {
        "candidate_count": len(records),
        "existing_proof_count": len(records) - len(pending),
        "pending_candidate_count": len(pending),
        "selected_object_count": len(selected_object_keys),
        "selected_candidate_count": len(selected),
        "remaining_candidate_count": max(0, len(pending) - len(selected)),
    }


def _load_existing_n3t_object_minute_proof_keys(
    *,
    records: Sequence[Mapping[str, Any]],
    dsn: str = "",
    connect_factory: Callable[..., Any] | None = None,
) -> set[tuple[str, str, str]]:
    if not records:
        return set()
    effective_dsn = str(dsn or os.environ.get("ASHARE_V3_POSTGRES_DSN") or "").strip()
    if not effective_dsn:
        raise FastlaneShellBlocked("object_cursor_batch_n3t_proof_read_dsn_required")
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for record in records:
        object_key = tuple(record.get("object_key") or ())
        if len(object_key) != 4:
            continue
        grouped.setdefault((str(object_key[0]), str(object_key[1])), []).append(record)
    if connect_factory is None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:  # pragma: no cover - import environment issue
            raise FastlaneShellBlocked("object_cursor_batch_psycopg_required") from exc
        connection_manager = psycopg.connect(
            effective_dsn,
            row_factory=dict_row,
            options="-c default_transaction_read_only=on",
            connect_timeout=10,
        )
    else:
        connection_manager = connect_factory(effective_dsn)
    existing: set[tuple[str, str, str]] = set()
    with connection_manager as connection:
        with connection.cursor() as cur:
            for (for_trade_date, asset_kind), group in sorted(grouped.items()):
                table = N3T_TABLE_BY_ASSET_KIND.get(asset_kind)
                if not table:
                    raise FastlaneShellBlocked("object_cursor_batch_asset_kind_mismatch")
                run_ids = sorted({str(item.get("n3t_metric_run_id") or "") for item in group})
                if not run_ids:
                    continue
                cur.execute(
                    f"""
                    SELECT projection_run_id, identity_key, metric_minute_label
                    FROM {table}
                    WHERE for_trade_date = %s
                      AND source_basis = 'N3T_C1_CLOSED'
                      AND metric_ready IS TRUE
                      AND projection_run_id = ANY(%s)
                    """,
                    (for_trade_date, run_ids),
                )
                for row in cur.fetchall():
                    existing.add(
                        (
                            str(row["projection_run_id"]),
                            str(row["identity_key"]),
                            str(row["metric_minute_label"]),
                        )
                    )
    return existing


def _object_cursor_batch_provider_plans(
    *,
    selected_records: Sequence[Mapping[str, Any]],
    observed_at: str,
) -> list[dict[str, Any]]:
    latest_by_object: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}
    for record in selected_records:
        object_key = tuple(record.get("object_key") or ())
        existing = latest_by_object.get(object_key)
        if existing is None or _hhmm_int(record.get("target_hhmm")) > _hhmm_int(existing.get("target_hhmm")):
            latest_by_object[object_key] = record
    plans: list[dict[str, Any]] = []
    for object_key, record in sorted(latest_by_object.items()):
        payload = dict(record.get("payload") or {})
        target_hhmm = str(record.get("target_hhmm") or "")
        pull_plan = build_n3_c1_scoped_current_day_pull_plan(
            payload,
            target_minute_label=_hhmm_to_minute_label(target_hhmm),
            observed_at=observed_at,
            source_artifact_path=str(record.get("source_active_scope_artifact_path") or ""),
            source_artifact_hash=str(record.get("source_active_scope_artifact_sha256") or ""),
        )
        if pull_plan.get("plan_status") != "planned" or pull_plan.get("full_market_fallback_used") is True:
            raise FastlaneShellBlocked(str(pull_plan.get("blocked_reason") or "object_cursor_batch_pull_plan_invalid"))
        provider_hash = _active_a_minute_batch_provider_source_run_hash(payload, target_hhmm=target_hhmm)
        plans.append(
            {
                "for_trade_date": object_key[0],
                "target_hhmm": target_hhmm,
                "source_run_hash": provider_hash,
                "namespace_token": f"{object_key[0]}_{target_hhmm}_{provider_hash}",
                "inline_pull_plan_payload": pull_plan,
                "object_batch_key": list(object_key),
            }
        )
    return plans


def _run_object_cursor_batch_hot_path(
    *,
    args: argparse.Namespace,
    invocation_id: str,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    current_day_source_provider_adapter: Callable[..., Mapping[str, Any]] | None,
    previous_day_context_provider_adapter: Callable[..., Mapping[str, Any]] | None,
    n3t_writer_adapter: Callable[..., Mapping[str, Any]] | None,
    deadline_check: Callable[[str], None],
    started: float,
    now_monotonic: Any,
) -> dict[str, Any]:
    observed_at = _runner_observed_at(args)
    closed_hhmm = _active_a_minute_batch_closed_hhmm(args, active_scope_artifacts)
    if not closed_hhmm:
        return _object_cursor_batch_manifest(
            args=args,
            invocation_id=invocation_id,
            active_scope_artifacts=active_scope_artifacts,
            selection_summary={},
            source_result={},
            previous_result={},
            writer_result={},
            batch_artifacts=[],
            failure_records=[],
            reason="object_cursor_batch_closed_minute_unavailable",
            started=started,
            now_monotonic=now_monotonic,
        )

    candidates = _object_cursor_batch_candidate_records(
        active_scope_artifacts=active_scope_artifacts,
        closed_hhmm=closed_hhmm,
    )
    deadline_check("object_cursor_batch_candidates_selected")
    existing_proof_keys = _load_existing_n3t_object_minute_proof_keys(records=candidates)
    selected, selection_summary = _select_pending_object_cursor_batch_records(
        records=candidates,
        existing_proof_keys=existing_proof_keys,
        max_objects=_current_day_source_provider_max_candidates(args),
        max_proof_rows=DEFAULT_OBJECT_CURSOR_BATCH_MAX_PROOF_ROWS,
    )
    selection_summary.update(
        {
            "closed_minute_label": _hhmm_to_minute_label(closed_hhmm),
            "max_objects": _current_day_source_provider_max_candidates(args),
            "max_minutes_per_object": DEFAULT_OBJECT_CURSOR_BATCH_MAX_MINUTES_PER_OBJECT,
            "max_proof_rows": DEFAULT_OBJECT_CURSOR_BATCH_MAX_PROOF_ROWS,
        }
    )
    if not selected:
        return _object_cursor_batch_manifest(
            args=args,
            invocation_id=invocation_id,
            active_scope_artifacts=active_scope_artifacts,
            selection_summary=selection_summary,
            source_result={},
            previous_result={},
            writer_result={},
            batch_artifacts=[],
            failure_records=[],
            reason="object_cursor_batch_no_pending_proof",
            started=started,
            now_monotonic=now_monotonic,
        )
    inline_source_adapter = getattr(current_day_source_provider_adapter, "inline_batch_adapter", None)
    if not callable(inline_source_adapter):
        raise FastlaneShellBlocked("object_cursor_batch_inline_source_provider_required")
    provider_plans = _object_cursor_batch_provider_plans(
        selected_records=selected,
        observed_at=observed_at,
    )
    source_result = dict(inline_source_adapter(args=args, planned_artifacts=provider_plans) or {})
    _validate_current_day_source_provider_result(source_result)
    source_by_object: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for source_artifact in source_result.get("source_artifacts") or []:
        if not isinstance(source_artifact, Mapping):
            continue
        payload = source_artifact.get("payload")
        if not isinstance(payload, Mapping):
            raise FastlaneShellBlocked("object_cursor_batch_inline_source_payload_required")
        object_key = tuple(source_artifact.get("object_batch_key") or ())
        if len(object_key) != 4:
            object_key = _active_a_minute_batch_source_payload_fetch_group_key(payload)
        if len(object_key) != 4 or not all(object_key):
            raise FastlaneShellBlocked("object_cursor_batch_source_scope_mismatch")
        source_by_object[object_key] = dict(source_artifact)

    records_by_object: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in selected:
        records_by_object.setdefault(tuple(record["object_key"]), []).append(dict(record))
    staging_records: list[dict[str, Any]] = []
    failure_records: list[dict[str, Any]] = []
    deadline_reached = False
    processed_object_keys: set[tuple[str, str, str, str]] = set()
    attempted_object_keys: set[tuple[str, str, str, str]] = set()
    for object_key, object_records in sorted(records_by_object.items()):
        attempted_object_keys.add(object_key)
        source_artifact = source_by_object.get(object_key)
        if not source_artifact:
            failure_records.append(
                _object_cursor_batch_failure(object_key, reason="current_day_source_provider_fetch_failed")
            )
        else:
            source_payload = dict(source_artifact.get("payload") or {})
            for record in sorted(object_records, key=lambda item: _hhmm_int(item["target_hhmm"])):
                try:
                    payload = dict(record.get("payload") or {})
                    target_hhmm = str(record.get("target_hhmm") or "")
                    pull_plan = build_n3_c1_scoped_current_day_pull_plan(
                        payload,
                        target_minute_label=_hhmm_to_minute_label(target_hhmm),
                        observed_at=observed_at,
                        source_artifact_path=str(record.get("source_active_scope_artifact_path") or ""),
                        source_artifact_hash=str(record.get("source_active_scope_artifact_sha256") or ""),
                    )
                    if pull_plan.get("plan_status") != "planned" or pull_plan.get("full_market_fallback_used") is True:
                        raise FastlaneShellBlocked(
                            str(pull_plan.get("blocked_reason") or "object_cursor_batch_pull_plan_invalid")
                        )
                    filtered_source = _source_rows_filtered_to_pull_plan(
                        source_payload,
                        pull_plan_payload=pull_plan,
                    )
                    staging = build_n3_c1_scoped_current_day_staging_artifact(
                        payload,
                        pull_plan_artifact=pull_plan,
                        source_rows_artifact=filtered_source,
                        target_hhmm=target_hhmm,
                        observed_at=observed_at,
                        source_pull_plan_path="inline://object_cursor_batch/pull_plan",
                        source_pull_plan_hash=_json_payload_sha256(pull_plan),
                        source_rows_artifact_path="inline://object_cursor_batch/current_day_source",
                        source_rows_artifact_hash=str(source_artifact.get("sha256") or ""),
                    )
                    if staging.get("artifact_status") != "passed":
                        raise FastlaneShellBlocked(
                            str(staging.get("blocked_reason") or "object_cursor_batch_staging_invalid")
                        )
                    staging_written_at = datetime.now().astimezone().isoformat()
                    staging.update(
                        {
                            "c1_lane_mode": OBJECT_CURSOR_BATCH_MODE,
                            "source_written_at": source_payload.get("source_written_at"),
                            "staging_written_at": staging_written_at,
                            "minute_closed_to_source_ms": source_payload.get("minute_closed_to_source_ms"),
                            "source_to_staging_ms": _elapsed_ms(
                                started_at=source_payload.get("source_written_at"),
                                completed_at=staging_written_at,
                            ),
                            "staging_to_proof_ms": None,
                            "proof_to_action_ms": None,
                        }
                    )
                    staging_records.append(
                        {
                            **record,
                            "staging_payload": staging,
                            "source_artifact": source_artifact,
                        }
                    )
                    processed_object_keys.add(object_key)
                except (FastlaneShellBlocked, ValueError) as exc:
                    failure_records.append(
                        _object_cursor_batch_failure(
                            object_key,
                            target_hhmm=str(record.get("target_hhmm") or ""),
                            reason=str(exc),
                        )
                    )
        try:
            deadline_check("object_cursor_batch_object_group")
        except FastlaneShellBlocked as exc:
            if not str(exc).startswith("max_runtime_seconds_exceeded:"):
                raise
            deadline_reached = True
            break

    if deadline_reached:
        unattempted_count = sum(
            len(object_records)
            for object_key, object_records in records_by_object.items()
            if object_key not in attempted_object_keys
        )
        selection_summary["remaining_candidate_count"] = (
            int(selection_summary.get("remaining_candidate_count") or 0) + unattempted_count
        )

    inline_previous_adapter = getattr(previous_day_context_provider_adapter, "inline_rows_batch_adapter", None)
    if staging_records and not callable(inline_previous_adapter):
        raise FastlaneShellBlocked("object_cursor_batch_inline_previous_day_provider_required")
    previous_result = (
        dict(
            inline_previous_adapter(
                args=args,
                staging_payloads=[item["staging_payload"] for item in staging_records],
            )
            or {}
        )
        if staging_records
        else {}
    )
    previous_rows = list(previous_result.get("previous_day_minute_rows") or [])
    previous_rows_by_object: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for previous_row in previous_rows:
        if not isinstance(previous_row, Mapping):
            continue
        previous_key = (
            str(previous_row.get("asset_kind") or ""),
            str(previous_row.get("identity_key") or ""),
        )
        if all(previous_key):
            previous_rows_by_object.setdefault(previous_key, []).append(dict(previous_row))
    missing_previous_objects = {
        tuple(item)
        for item in previous_result.get("missing_object_keys") or []
        if isinstance(item, (list, tuple)) and len(item) == 2
    }
    n3t_writer_inputs: list[dict[str, Any]] = []
    proof_records: list[dict[str, Any]] = []
    for record in staging_records:
        object_key = tuple(record["object_key"])
        target_hhmm = str(record.get("target_hhmm") or "")
        if (object_key[1], object_key[2]) in missing_previous_objects:
            failure_records.append(
                _object_cursor_batch_failure(
                    object_key,
                    target_hhmm=target_hhmm,
                    reason="previous_day_context_rows_missing",
                )
            )
            continue
        try:
            payload = dict(record.get("payload") or {})
            staging = dict(record.get("staging_payload") or {})
            metric_source = build_n3_c1_n3t_metric_context_source_artifact(
                payload,
                staging_artifact=staging,
                previous_day_minute_rows=previous_rows_by_object.get((object_key[1], object_key[2]), []),
                target_hhmm=target_hhmm,
                observed_at=observed_at,
                source_staging_artifact_path="inline://object_cursor_batch/current_day_staging",
                source_staging_artifact_hash=_json_payload_sha256(staging),
            )
            if metric_source.get("metric_context_status") != "ready":
                raise FastlaneShellBlocked(
                    str(metric_source.get("blocked_reason") or "metric_context_source_not_ready")
                )
            metric_payload = build_n3_c1_scoped_artifact_plan(
                payload,
                target_minute_label=_hhmm_to_minute_label(target_hhmm),
                observed_at=observed_at,
                source_artifact_path="inline://object_cursor_batch/metric_context_source",
                source_artifact_hash=_json_payload_sha256(metric_source),
                metric_context_rows=list(metric_source.get("metric_context_rows") or []),
            )
            if (
                metric_payload.get("artifact_status") != "planned"
                or metric_payload.get("metric_context_status") != "ready"
            ):
                raise FastlaneShellBlocked(
                    str(metric_payload.get("blocked_reason") or "metric_context_not_ready")
                )
            proof_written_at = datetime.now().astimezone().isoformat()
            metric_payload.update(
                {
                    "source_written_at": staging.get("source_written_at"),
                    "staging_written_at": staging.get("staging_written_at"),
                    "proof_written_at": proof_written_at,
                    "minute_closed_to_source_ms": staging.get("minute_closed_to_source_ms"),
                    "source_to_staging_ms": staging.get("source_to_staging_ms"),
                    "staging_to_proof_ms": _elapsed_ms(
                        started_at=staging.get("staging_written_at"),
                        completed_at=proof_written_at,
                    ),
                    "proof_to_action_ms": None,
                    "object_cursor_batch_inline": True,
                }
            )
            metric_hash = _json_payload_sha256(metric_payload)
            writer_input = {
                "target_hhmm": target_hhmm,
                "for_trade_date": object_key[0],
                "source_run_hash": record.get("source_run_hash"),
                "namespace_token": record.get("source_run_namespace"),
                "n3t_metric_run_id": record.get("n3t_metric_run_id"),
                "metric_context_artifact_path": "inline://object_cursor_batch/metric_context",
                "metric_context_artifact_sha256": metric_hash,
                "metric_context_payload": metric_payload,
                "source_basis": "N3T_C1_CLOSED",
                "metric_role": "action_confirmation",
                "proof_consumer": "N5",
                "not_n5_final_proof": False,
            }
            n3t_writer_inputs.append(writer_input)
            proof_records.append({**record, "metric_payload": metric_payload, "metric_hash": metric_hash})
        except (FastlaneShellBlocked, ValueError) as exc:
            failure_records.append(
                _object_cursor_batch_failure(
                    object_key,
                    target_hhmm=target_hhmm,
                    reason=str(exc),
                )
            )

    writer_result: dict[str, Any] = {}
    if n3t_writer_inputs:
        if n3t_writer_adapter is None:
            raise FastlaneShellBlocked("object_cursor_batch_n3t_writer_required")
        writer_result = dict(n3t_writer_adapter(args=args, n3t_writer_inputs=n3t_writer_inputs) or {})
        _validate_execute_result(writer_result)
    batch_artifacts = _write_object_cursor_batch_artifacts(
        output_dir=Path(args.output_dir),
        invocation_id=invocation_id,
        selected_records=selected,
        source_by_object=source_by_object,
        previous_rows=previous_rows,
        proof_records=proof_records,
        failure_records=failure_records,
        writer_result=writer_result,
        observed_at=observed_at,
    )
    reason = (
        "object_cursor_batch_chunk_incomplete"
        if deadline_reached or int(selection_summary.get("remaining_candidate_count") or 0) > 0
        else "object_cursor_batch_complete"
    )
    selection_summary["processed_object_count"] = len(processed_object_keys)
    selection_summary["processed_candidate_count"] = len(n3t_writer_inputs)
    selection_summary["failed_candidate_count"] = len(failure_records)
    return _object_cursor_batch_manifest(
        args=args,
        invocation_id=invocation_id,
        active_scope_artifacts=active_scope_artifacts,
        selection_summary=selection_summary,
        source_result=source_result,
        previous_result=previous_result,
        writer_result=writer_result,
        batch_artifacts=batch_artifacts,
        failure_records=failure_records,
        reason=reason,
        started=started,
        now_monotonic=now_monotonic,
    )


def _object_cursor_batch_failure(
    object_key: Sequence[str],
    *,
    reason: str,
    target_hhmm: str = "",
) -> dict[str, Any]:
    return {
        "for_trade_date": str(object_key[0]) if len(object_key) > 0 else "",
        "asset_kind": str(object_key[1]) if len(object_key) > 1 else "",
        "identity_key": str(object_key[2]) if len(object_key) > 2 else "",
        "direction": str(object_key[3]) if len(object_key) > 3 else "",
        "target_hhmm": str(target_hhmm or ""),
        "reason": str(reason or "object_cursor_batch_failed"),
    }


def _json_payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_atomic_compact_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(encoded, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _claim_atomic_compact_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(encoded):
            written = os.write(fd, encoded[offset:])
            if written <= 0:
                raise OSError("atomic compact JSON claim write failed")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_object_cursor_batch_artifacts(
    *,
    output_dir: Path,
    invocation_id: str,
    selected_records: Sequence[Mapping[str, Any]],
    source_by_object: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
    previous_rows: Sequence[Mapping[str, Any]],
    proof_records: Sequence[Mapping[str, Any]],
    failure_records: Sequence[Mapping[str, Any]],
    writer_result: Mapping[str, Any],
    observed_at: str,
) -> list[dict[str, Any]]:
    selected_by_object: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    proof_by_object: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    failures_by_object: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for record in selected_records:
        selected_by_object.setdefault(tuple(record.get("object_key") or ()), []).append(record)
    for record in proof_records:
        proof_by_object.setdefault(tuple(record.get("object_key") or ()), []).append(record)
    for failure in failure_records:
        key = (
            str(failure.get("for_trade_date") or ""),
            str(failure.get("asset_kind") or ""),
            str(failure.get("identity_key") or ""),
            str(failure.get("direction") or ""),
        )
        failures_by_object.setdefault(key, []).append(failure)

    written: list[dict[str, Any]] = []
    batch_dir = output_dir / "object_cursor_batch"
    for object_key, records in sorted(selected_by_object.items()):
        if len(object_key) != 4:
            continue
        source_artifact = dict(source_by_object.get(object_key) or {})
        source_payload = dict(source_artifact.get("payload") or {})
        object_previous_rows = [
            dict(row)
            for row in previous_rows
            if str(row.get("asset_kind") or "") == object_key[1]
            and str(row.get("identity_key") or "") == object_key[2]
        ]
        targets = sorted(
            {str(record.get("target_hhmm") or "") for record in records},
            key=_hhmm_int,
        )
        object_proofs = sorted(
            proof_by_object.get(object_key) or [],
            key=lambda item: _hhmm_int(item.get("target_hhmm")),
        )
        input_hash = _json_payload_sha256(
            {
                "object_key": list(object_key),
                "source_active_scope_artifact_sha256": sorted(
                    {str(record.get("source_active_scope_artifact_sha256") or "") for record in records}
                ),
                "target_hhmms": targets,
                "source_run_hashes": [str(record.get("source_run_hash") or "") for record in records],
            }
        )
        identity_hash = hashlib.sha256("|".join(object_key).encode("utf-8")).hexdigest()[:12]
        first_target = targets[0] if targets else "none"
        last_target = targets[-1] if targets else "none"
        path = (
            batch_dir
            / f"{OBJECT_CURSOR_BATCH_ARTIFACT_TYPE}_{object_key[0]}_{identity_hash}_{first_target}_{last_target}_{input_hash[:12]}.json"
        )
        payload = {
            "artifact_type": OBJECT_CURSOR_BATCH_ARTIFACT_TYPE,
            "artifact_schema_version": "v1",
            "producer_layer": "N3_market_data",
            "mode": OBJECT_CURSOR_BATCH_MODE,
            "invocation_id": invocation_id,
            "observed_at": observed_at,
            "for_trade_date": object_key[0],
            "asset_kind": object_key[1],
            "identity_key": object_key[2],
            "direction": object_key[3],
            "input_hash": input_hash,
            "target_minute_labels": [_hhmm_to_minute_label(value) for value in targets],
            "source_active_scope_artifact_paths": sorted(
                {str(record.get("source_active_scope_artifact_path") or "") for record in records}
            ),
            "current_day_source": {
                "source_run_hash": source_payload.get("source_run_hash"),
                "source_run_namespace": source_payload.get("source_run_namespace"),
                "source_provider": source_payload.get("source_provider"),
                "source_adapter": source_payload.get("source_adapter"),
                "source_version": source_payload.get("source_version"),
                "source_written_at": source_payload.get("source_written_at"),
                "closed_minute_row_count": int(source_payload.get("closed_minute_row_count") or 0),
                "closed_minute_rows": list(source_payload.get("closed_minute_rows") or []),
            },
            "previous_day_context": {
                "previous_day_minute_row_count": len(object_previous_rows),
                "previous_day_minute_rows": object_previous_rows,
            },
            "proofs": [
                {
                    "target_minute_label": _hhmm_to_minute_label(record.get("target_hhmm") or ""),
                    "n3t_metric_run_id": record.get("n3t_metric_run_id"),
                    "source_run_hash": record.get("source_run_hash"),
                    "metric_context_sha256": record.get("metric_hash"),
                    "metric_context_status": (record.get("metric_payload") or {}).get("metric_context_status"),
                }
                for record in object_proofs
            ],
            "failure_details": [dict(item) for item in failures_by_object.get(object_key) or []],
            "writer_result": {
                "write_executed": bool(writer_result.get("write_executed")),
                "inserted_rows": int(writer_result.get("inserted_rows") or 0),
                "target_table_counts": dict(writer_result.get("target_table_counts") or {}),
            },
            "boundary": {
                "database_read": True,
                "n3t_metric_db_written": bool(writer_result.get("db_write_executed")),
                "writes_canonical_minute_bar_1m": False,
                "writes_n3_outbox": False,
                "writes_n4_outbox": False,
                "writes_n5_outbox": False,
                "updates_n4_outbox": False,
                "scans_n5_db": False,
                "full_market_fallback_used": False,
                "touches_n6": False,
            },
        }
        _write_atomic_compact_json(path, payload)
        written.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "identity_key": object_key[2],
                "target_minute_count": len(targets),
                "proof_count": len(object_proofs),
            }
        )
    return written


def _object_cursor_batch_manifest(
    *,
    args: argparse.Namespace,
    invocation_id: str,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    selection_summary: Mapping[str, Any],
    source_result: Mapping[str, Any],
    previous_result: Mapping[str, Any],
    writer_result: Mapping[str, Any],
    batch_artifacts: Sequence[Mapping[str, Any]],
    failure_records: Sequence[Mapping[str, Any]],
    reason: str,
    started: float,
    now_monotonic: Any,
) -> dict[str, Any]:
    selected_objects = int(selection_summary.get("selected_object_count") or 0)
    selected_candidates = int(selection_summary.get("selected_candidate_count") or 0)
    processed_candidates = int(selection_summary.get("processed_candidate_count") or 0)
    remaining_candidates = int(selection_summary.get("remaining_candidate_count") or 0)
    failed_candidates = int(selection_summary.get("failed_candidate_count") or len(failure_records))
    write_executed = bool(writer_result.get("write_executed"))
    verdict = "N3_C1_N3T_FASTLANE_EXECUTE_PASS" if write_executed else "N3_C1_N3T_FASTLANE_READINESS_WAITING"
    lane_results = {
        "c1_lane": {
            "lane": "c1_lane",
            "mode": OBJECT_CURSOR_BATCH_MODE,
            "selected_candidate_count": selected_objects,
            "processed_candidate_count": int(source_result.get("inline_payload_count") or 0),
            "failed_candidate_count": int(source_result.get("failed_candidate_count") or 0),
            "skipped_candidate_count": int(selection_summary.get("existing_proof_count") or 0),
            "remaining_candidate_count": remaining_candidates,
            "reason": reason,
            "hard_blocker_count": 0,
        },
        "n3t_lane": {
            "lane": "n3t_lane",
            "mode": OBJECT_CURSOR_BATCH_MODE,
            "selected_candidate_count": selected_candidates,
            "processed_candidate_count": processed_candidates,
            "failed_candidate_count": failed_candidates,
            "skipped_candidate_count": int(selection_summary.get("existing_proof_count") or 0),
            "remaining_candidate_count": remaining_candidates,
            "reason": reason,
            "hard_blocker_count": 0,
        },
    }
    boundary = _boundary()
    boundary.update(
        {
            "writes_db": bool(writer_result.get("db_write_executed")),
            "writes_n3t_metric_db": bool(writer_result.get("db_write_executed")),
            "pulls_market_data": bool(source_result.get("market_data_pulled")),
            "writes_canonical_minute_bar_1m": False,
            "writes_n3_outbox": False,
            "touches_n4_n5_n6_outbox": False,
            "scans_n5_db": False,
            "full_market_fallback_used": False,
        }
    )
    return {
        "verdict": verdict,
        "reason": reason,
        "invocation_id": invocation_id,
        "fastlane_lane_id": args.fastlane_lane_id,
        "fastlane": {
            "session_phase": getattr(args, "fastlane_session_phase", ""),
            "active_worker_decision": getattr(args, "fastlane_active_worker_decision", {}),
        },
        "execute_requested": True,
        "writes_enabled": write_executed,
        "artifact_first_only": True,
        "active_scope_artifact_count": len(active_scope_artifacts),
        "lane_results": lane_results,
        "object_cursor_batch": {
            "artifact_type": OBJECT_CURSOR_BATCH_ARTIFACT_TYPE,
            "mode": OBJECT_CURSOR_BATCH_MODE,
            **dict(selection_summary),
            "batch_artifact_count": len(batch_artifacts),
            "batch_artifacts": [dict(item) for item in batch_artifacts],
            "failure_records": [dict(item) for item in failure_records],
            "provider_call_count": int(source_result.get("inline_payload_count") or 0),
            "previous_day_database_connection_count": int(previous_result.get("database_connection_count") or 0),
            "proof_row_count": int(writer_result.get("inserted_rows") or 0),
        },
        "current_day_source_provider_result": dict(source_result),
        "execute_result": dict(writer_result),
        "bounded": {
            "max_runtime_seconds": float(args.max_runtime_seconds),
            "elapsed_seconds": round(float(now_monotonic()) - float(started), 6),
        },
        "boundary": boundary,
    }


def _active_a_minute_batch_target_hhmms(
    *,
    for_trade_date: str,
    start_hhmm: str,
    closed_hhmm: str,
) -> list[str]:
    start_label = _hhmm_to_minute_label(start_hhmm)
    closed_label = _hhmm_to_minute_label(closed_hhmm)
    labels = _canonical_ashare_1m_labels_cached(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else ()
    if start_label in labels and closed_label in labels:
        start_index = labels.index(start_label)
        closed_index = labels.index(closed_label)
        if start_index > closed_index:
            return []
        return [label.replace(":", "") for label in labels[start_index : closed_index + 1]]
    start_value = _hhmm_int(start_hhmm)
    closed_value = _hhmm_int(closed_hhmm)
    if start_value <= 0 or closed_value <= 0 or start_value > closed_value:
        return []
    return [f"{start_value:04d}"]


def _persist_active_a_minute_batch_closed_fanout_payload(
    *,
    payload: Mapping[str, Any],
    source_artifact_path: str,
    output_dir: Path,
    target_hhmm: str,
    source_run_hash: str,
    source_run_namespace: str,
) -> str:
    fanout_dir = output_dir / "active_scope_ref_fanout"
    path = fanout_dir / f"n5_active_scope_snapshot_v1_{source_run_namespace}_ref_fanout.json"
    closed_payload = dict(payload)
    closed_payload.update(
        {
            "target_hhmm": target_hhmm,
            "target_minute_label": _hhmm_to_minute_label(target_hhmm),
            "source_run_hash": source_run_hash,
            "source_run_namespace": source_run_namespace,
            "object_scope_ref_fanout": True,
            "object_minute_scope": True,
            "object_minute_ref_dedupe_policy": "for_trade_date_asset_identity_direction_target_minute_v1",
            "source_object_scope_artifact_path": source_artifact_path,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_compact_json_artifact_atomic_if_stale(path, closed_payload)
    return str(path)


def _active_a_minute_batch_object_key(
    payload: Mapping[str, Any],
    *,
    target_hhmm: str,
) -> tuple[str, str, str, str, str]:
    rows = [row for row in payload.get("scope_rows") or [] if isinstance(row, Mapping)]
    row = rows[0] if rows else {}
    refs = [
        ref
        for scope_row in rows
        for ref in scope_row.get("active_tracking_refs") or []
        if isinstance(ref, Mapping)
    ]
    ref = refs[0] if refs else {}
    return (
        str(payload.get("for_trade_date") or row.get("for_trade_date") or ref.get("for_trade_date") or ""),
        str(row.get("asset_kind") or ref.get("asset_kind") or ""),
        str(row.get("identity_key") or ref.get("identity_key") or ""),
        str(ref.get("direction") or row.get("direction") or ""),
        str(target_hhmm),
    )


def _active_a_minute_batch_fetch_group_key_from_payload(
    payload: Mapping[str, Any],
    *,
    target_hhmm: str,
) -> tuple[str, str, str, str]:
    return _active_a_minute_batch_object_key(payload, target_hhmm=target_hhmm)[:4]


def _active_a_minute_batch_provider_source_run_hash(
    payload: Mapping[str, Any],
    *,
    target_hhmm: str,
) -> str:
    return _short_scope_hash(
        "active_a_minute_provider_source_v1",
        *_active_a_minute_batch_object_key(payload, target_hhmm=target_hhmm),
    )


def _active_a_minute_batch_fetch_group_key_for_planned(
    planned_artifact: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    target_hhmm = str(planned_artifact.get("target_hhmm") or "")
    active_scope = _read_optional_json_artifact(str(planned_artifact.get("input_active_scope_artifact_path") or ""))
    payload = active_scope.get("payload") or {}
    if isinstance(payload, Mapping):
        return _active_a_minute_batch_fetch_group_key_from_payload(payload, target_hhmm=target_hhmm)
    return (str(planned_artifact.get("for_trade_date") or ""), "", "", "")


def _active_a_minute_batch_fetch_target_sort_key(planned_artifact: Mapping[str, Any]) -> int:
    return _hhmm_int(str(planned_artifact.get("target_hhmm") or ""))


def _active_a_minute_batch_source_payload_fetch_group_key(
    source_payload: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    rows = [
        row
        for row in source_payload.get("closed_minute_rows") or source_payload.get("source_rows") or []
        if isinstance(row, Mapping)
    ]
    row = rows[0] if rows else {}
    return (
        str(source_payload.get("for_trade_date") or row.get("for_trade_date") or ""),
        str(row.get("asset_kind") or ""),
        str(row.get("identity_key") or ""),
        str(row.get("direction") or source_payload.get("direction") or ""),
    )


def _active_a_minute_batch_source_target_sort_key(source: Mapping[str, Any]) -> int:
    return _hhmm_int(str(source.get("_provider_target_hhmm") or ""))


def _active_a_minute_batch_closed_hhmm(
    args: argparse.Namespace,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
) -> str:
    current_exchange_time = str(getattr(args, "fastlane_current_exchange_time", "") or "").strip()
    current_hhmm = _hhmm_int(current_exchange_time)
    for_trade_date = ""
    for artifact in active_scope_artifacts:
        for_trade_date = str(artifact.get("for_trade_date") or "")
        if for_trade_date:
            break
    if not for_trade_date:
        for_trade_date = str(getattr(args, "for_trade_date", "") or "")
    labels = _canonical_ashare_1m_labels_cached(for_trade_date) if re.fullmatch(r"\d{8}", for_trade_date or "") else ()
    if current_hhmm <= 0:
        return ""
    last_closed = ""
    for label in labels:
        hhmm = _hhmm_int(label)
        if hhmm <= 0:
            continue
        required = hhmm if hhmm >= 1500 else _add_hhmm_minutes(hhmm, 1)
        if current_hhmm >= required:
            last_closed = f"{hhmm:04d}"
        else:
            break
    return last_closed


def _active_a_minute_batch_closed_minute_unavailable(
    *,
    args: argparse.Namespace,
    summary: Mapping[str, Any] | None,
) -> bool:
    source = dict(summary or {})
    if source.get("mode") != ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE:
        return False
    if source.get("reason") != "active_a_minute_batch_closed_minute_unavailable":
        return False
    return str(getattr(args, "fastlane_session_phase", "") or "") == "post_close"


def _post_close_final_a_c1_pull_attempt_marker_path(
    args: argparse.Namespace,
    *,
    output_dir: Path,
) -> Path:
    for_trade_date = str(getattr(args, "for_trade_date", "") or "").strip()
    if not re.fullmatch(r"\d{8}", for_trade_date):
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_trade_date_invalid")
    return (
        output_dir
        / "post_close_final_a"
        / f"{POST_CLOSE_FINAL_A_C1_PULL_ATTEMPT_ARTIFACT_TYPE}_{for_trade_date}.json"
    )


def _load_post_close_final_a_c1_pull_attempt_marker(
    path: Path,
    *,
    for_trade_date: str,
) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FastlaneShellBlocked(
            "post_close_final_a_c1_pull_attempt_marker_invalid"
        ) from exc
    if not isinstance(payload, Mapping):
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    result = dict(payload)
    if result.get("artifact_type") != POST_CLOSE_FINAL_A_C1_PULL_ATTEMPT_ARTIFACT_TYPE:
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    if str(result.get("for_trade_date") or "") != for_trade_date:
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    if result.get("status") not in {"started", "completed", "failed"}:
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    if result.get("target_physical_minute_label") != POST_CLOSE_FINAL_A_PHYSICAL_MINUTE_LABEL:
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    if result.get("raw_source_close_label") != "15:00":
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    if int(result.get("selected_provider_candidate_count") or 0) <= 0:
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    if not re.fullmatch(
        r"[0-9a-f]{64}",
        str(result.get("selected_provider_scope_sha256") or ""),
    ):
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    if int(result.get("full_scope_remaining_object_count") or 0) != 0:
        raise FastlaneShellBlocked("post_close_final_a_c1_pull_attempt_marker_invalid")
    return result


def _post_close_final_a_c1_pull_gate(
    args: argparse.Namespace,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    session_phase = str(getattr(args, "fastlane_session_phase", "") or "").strip()
    if session_phase != "post_close":
        return {
            "applicable": False,
            "reason": "not_post_close",
            "c1_selection_disabled": False,
            "external_pull_allowed": True,
        }
    decision = dict(getattr(args, "fastlane_active_worker_decision", {}) or {})
    if (
        not _is_post_close_final_a_pass(args)
        or decision.get("post_close_final_a_pass_allowed") is not True
        or decision.get("external_c1_pull_allowed_once") is not True
    ):
        return {
            "applicable": True,
            "reason": "post_close_c1_provider_disabled",
            "c1_selection_disabled": True,
            "external_pull_allowed": False,
        }
    current_exchange_time = str(
        getattr(args, "fastlane_current_exchange_time", "") or ""
    ).strip()
    current_hhmm = _hhmm_int(current_exchange_time)
    if current_hhmm < POST_CLOSE_FINAL_A_CLOSE_GRACE_READY_HHMM:
        return {
            "applicable": True,
            "reason": "post_close_final_a_close_grace_waiting",
            "c1_selection_disabled": True,
            "external_pull_allowed": False,
            "current_exchange_time": current_exchange_time,
            "close_grace_ready_hhmm": f"{POST_CLOSE_FINAL_A_CLOSE_GRACE_READY_HHMM:04d}",
            "target_physical_minute_label": POST_CLOSE_FINAL_A_PHYSICAL_MINUTE_LABEL,
            "raw_source_close_label": "15:00",
        }
    marker_path = _post_close_final_a_c1_pull_attempt_marker_path(
        args,
        output_dir=output_dir,
    )
    for_trade_date = str(getattr(args, "for_trade_date", "") or "")
    marker = _load_post_close_final_a_c1_pull_attempt_marker(
        marker_path,
        for_trade_date=for_trade_date,
    )
    if marker:
        return {
            "applicable": True,
            "reason": "post_close_final_a_close_grace_pull_already_attempted",
            "c1_selection_disabled": False,
            "external_pull_allowed": False,
            "current_exchange_time": current_exchange_time,
            "close_grace_ready_hhmm": f"{POST_CLOSE_FINAL_A_CLOSE_GRACE_READY_HHMM:04d}",
            "target_physical_minute_label": POST_CLOSE_FINAL_A_PHYSICAL_MINUTE_LABEL,
            "raw_source_close_label": "15:00",
            "attempt_marker_path": str(marker_path),
            "attempt_marker_status": str(marker.get("status") or ""),
            "attempt_marker_exists": True,
        }
    return {
        "applicable": True,
        "reason": "post_close_final_a_close_grace_pull_ready",
        "c1_selection_disabled": False,
        "external_pull_allowed": True,
        "current_exchange_time": current_exchange_time,
        "close_grace_ready_hhmm": f"{POST_CLOSE_FINAL_A_CLOSE_GRACE_READY_HHMM:04d}",
        "target_physical_minute_label": POST_CLOSE_FINAL_A_PHYSICAL_MINUTE_LABEL,
        "raw_source_close_label": "15:00",
        "attempt_marker_path": str(marker_path),
        "attempt_marker_status": "",
        "attempt_marker_exists": False,
    }


def _apply_post_close_final_a_full_scope_coverage(
    *,
    close_grace_pull: dict[str, Any],
    c1_summary: Mapping[str, Any],
) -> None:
    remaining_object_count = int(c1_summary.get("remaining_object_count") or 0)
    close_grace_pull.update(
        {
            "full_scope_pending_object_count": int(
                c1_summary.get("pending_object_count") or 0
            ),
            "full_scope_selected_object_count": int(
                c1_summary.get("selected_object_count") or 0
            ),
            "full_scope_remaining_object_count": remaining_object_count,
        }
    )
    if remaining_object_count > 0:
        close_grace_pull.update(
            {
                "reason": "post_close_final_a_scope_exceeds_single_pull_limit",
                "external_pull_allowed": False,
            }
        )


def _post_close_c1_provider_disabled_summary(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    reason: str = "post_close_c1_provider_disabled",
    close_grace_pull: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    active_ref_count = 0
    for artifact in active_scope_artifacts:
        payload = _active_scope_payload_from_candidate(artifact)
        active_ref_count += len(_iter_active_scope_ref_records(payload))
    return {
        "mode": ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE,
        "reason": reason,
        "selected_candidate_count": 0,
        "selected_object_count": 0,
        "selected_ref_count": active_ref_count,
        "processed_candidate_count": 0,
        "source_artifact_written_count": 0,
        "staging_artifact_written_count": 0,
        "skipped_existing_ready_count": 0,
        "failed_candidate_count": 0,
        "remaining_candidate_count": len(active_scope_artifacts),
        "post_close_final_a_close_grace_pull": dict(close_grace_pull or {}),
    }


def _active_a_minute_batch_source_run_hash(payload: Mapping[str, Any], *, target_hhmm: str) -> str:
    rows = [row for row in payload.get("scope_rows") or [] if isinstance(row, Mapping)]
    row = rows[0] if rows else {}
    refs = [
        dict(ref)
        for scope_row in rows
        for ref in scope_row.get("active_tracking_refs") or []
        if isinstance(ref, Mapping)
    ]
    if not refs:
        return ""
    object_row = dict(row)
    object_row.setdefault("for_trade_date", payload.get("for_trade_date"))
    object_row.setdefault("asset_kind", refs[0].get("asset_kind"))
    object_row.setdefault("identity_key", refs[0].get("identity_key"))
    return _object_minute_source_run_hash(
        object_row=object_row,
        active_refs=refs,
        target_hhmm=target_hhmm,
    )


def _active_a_minute_batch_has_ready_ref(payload: Mapping[str, Any], *, closed_hhmm: str) -> bool:
    closed_value = _hhmm_int(closed_hhmm)
    if closed_value <= 0:
        return False
    for ref in _iter_active_scope_ref_records(payload):
        ref_target = _target_hhmm_from_active_ref(ref)
        if not ref_target:
            continue
        if _hhmm_int(ref_target) <= closed_value:
            return True
    return False


def _active_a_minute_batch_ref_count(payload: Mapping[str, Any]) -> int:
    count = int(payload.get("active_tracking_ref_count") or 0)
    if count > 0:
        return count
    return len(_iter_active_scope_ref_records(payload))


def _build_inline_pull_plan_for_active_a_minute_batch(
    planned_artifact: Mapping[str, Any],
    *,
    observed_at: Any,
) -> dict[str, Any]:
    active_scope = _read_optional_json_artifact(str(planned_artifact.get("input_active_scope_artifact_path") or ""))
    if not active_scope["exists"]:
        raise FastlaneShellBlocked("active_scope_artifact_missing")
    target_hhmm = str(planned_artifact.get("target_hhmm") or "")
    plan = build_n3_c1_scoped_current_day_pull_plan(
        active_scope.get("payload") or {},
        target_minute_label=_hhmm_to_minute_label(target_hhmm),
        observed_at=observed_at,
        source_artifact_path=str(active_scope.get("path") or ""),
        source_artifact_hash=str(active_scope.get("sha256") or ""),
    )
    plan["plan_source"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
    plan["persistent_pull_plan_written"] = False
    return plan


def _run_active_a_minute_batch_direct_provider_adapter(
    *,
    args: argparse.Namespace,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    current_day_source_provider_adapter: Callable[..., Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not active_scope_artifacts:
        return None
    source_dir_text = str(getattr(args, "current_day_source_artifact_dir", "") or "").strip()
    if not source_dir_text:
        raise FastlaneShellBlocked("current_day_source_artifact_dir_required")
    source_dir = Path(source_dir_text)
    source_dir.mkdir(parents=True, exist_ok=True)
    scoped_plan = _build_scoped_executor_plan(
        active_scope_artifacts=active_scope_artifacts,
        output_dir=output_dir,
        plan_status="planned",
        blocked_reason=None,
        include_component_readiness=False,
    )
    planned_artifacts_by_fetch_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    reusable_source_artifacts: list[dict[str, Any]] = []
    observed_at = _runner_observed_at(args)
    for planned in scoped_plan.get("planned_artifacts") or []:
        item = dict(planned)
        item["c1_lane_mode"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
        item["c1_lane_selection_reason"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
        item["inline_pull_plan_payload"] = _build_inline_pull_plan_for_active_a_minute_batch(
            item,
            observed_at=observed_at,
        )
        fetch_key = _active_a_minute_batch_fetch_group_key_for_planned(item)
        existing = planned_artifacts_by_fetch_key.get(fetch_key)
        if existing is None or _active_a_minute_batch_fetch_target_sort_key(item) > _active_a_minute_batch_fetch_target_sort_key(existing):
            planned_artifacts_by_fetch_key[fetch_key] = item
    planned_artifacts: list[dict[str, Any]] = []
    for item in planned_artifacts_by_fetch_key.values():
        source_rows = _find_current_day_source_rows_artifact(
            source_dir,
            target_hhmm=str(item.get("target_hhmm") or ""),
            source_run_hash=str(item.get("source_run_hash") or ""),
            namespace_token=str(item.get("namespace_token") or ""),
        )
        if source_rows is None and item.get("ref_source_run_namespace"):
            source_rows = _find_current_day_source_rows_artifact(
                source_dir,
                target_hhmm=str(item.get("target_hhmm") or ""),
                source_run_hash=str(item.get("ref_source_run_hash") or ""),
                namespace_token=str(item.get("ref_source_run_namespace") or ""),
                exact_only=True,
            )
        if source_rows and not _current_day_artifact_needs_boundary_rebuild(source_rows.get("payload") or {}):
            source_payload = dict(source_rows.get("payload") or {})
            reusable_source_artifacts.append(
                {
                    "path": str(source_rows.get("path") or ""),
                    "target_hhmm": str(source_payload.get("target_hhmm") or item.get("target_hhmm") or ""),
                    "for_trade_date": str(source_payload.get("for_trade_date") or item.get("for_trade_date") or ""),
                    "artifact_type": CURRENT_DAY_SOURCE_ROWS_TYPE,
                    "source_run_hash": str(source_payload.get("source_run_hash") or item.get("source_run_hash") or ""),
                    "source_run_namespace": str(
                        source_payload.get("source_run_namespace") or item.get("namespace_token") or ""
                    ),
                    "row_count": int(source_payload.get("closed_minute_row_count") or 0),
                    "sha256": str(source_rows.get("sha256") or ""),
                    "fetch_group_key": list(
                        _active_a_minute_batch_fetch_group_key_for_planned(item)
                    ),
                }
            )
            continue
        planned_artifacts.append(item)
    planned_artifacts.sort(
        key=lambda item: (
            _active_a_minute_batch_fetch_target_sort_key(item),
            _active_a_minute_batch_fetch_group_key_for_planned(item),
        ),
    )
    summary = dict(getattr(args, "c1_active_a_minute_batch_summary", {}) or {})
    if not planned_artifacts:
        result = _skipped_current_day_source_provider_result(
            skip_reason=ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE,
            staging_artifact_count=0,
        )
        result["mode"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
        result["selection_reason"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
        result["selected_object_count"] = int(summary.get("selected_object_count") or 0)
        result["selected_ref_count"] = int(summary.get("selected_ref_count") or 0)
        result["closed_minute_label"] = str(summary.get("closed_minute_label") or "")
        result["candidate_scan_bounded"] = True
        result["candidate_scan_limit"] = _current_day_source_provider_max_candidates(args)
        result["candidate_scan_scanned_count"] = len(active_scope_artifacts)
        result["candidate_count"] = 0
        result["remaining_candidate_count"] = int(summary.get("remaining_candidate_count") or 0)
        result["source_artifacts"] = reusable_source_artifacts
        _validate_current_day_source_provider_result(result)
        return result
    result = dict(current_day_source_provider_adapter(args=args, planned_artifacts=planned_artifacts) or {})
    reported_source_artifacts = [
        dict(item)
        for item in result.get("source_artifacts") or []
        if isinstance(item, Mapping)
    ]
    fetch_group_key_by_namespace = {
        str(item.get("namespace_token") or ""): list(
            _active_a_minute_batch_fetch_group_key_for_planned(item)
        )
        for item in planned_artifacts
    }
    for source_artifact in reported_source_artifacts:
        namespace = str(source_artifact.get("source_run_namespace") or "")
        if namespace in fetch_group_key_by_namespace:
            source_artifact.setdefault("fetch_group_key", fetch_group_key_by_namespace[namespace])
    reported_paths = {str(item.get("path") or "") for item in reported_source_artifacts}
    for planned in planned_artifacts:
        source = _find_current_day_source_rows_artifact(
            source_dir,
            target_hhmm=str(planned.get("target_hhmm") or ""),
            source_run_hash=str(planned.get("source_run_hash") or ""),
            namespace_token=str(planned.get("namespace_token") or ""),
            exact_only=True,
        )
        if not source or str(source.get("path") or "") in reported_paths:
            continue
        payload = dict(source.get("payload") or {})
        reported_source_artifacts.append(
            {
                "path": str(source.get("path") or ""),
                "target_hhmm": str(payload.get("target_hhmm") or planned.get("target_hhmm") or ""),
                "for_trade_date": str(payload.get("for_trade_date") or planned.get("for_trade_date") or ""),
                "artifact_type": CURRENT_DAY_SOURCE_ROWS_TYPE,
                "source_run_hash": str(payload.get("source_run_hash") or planned.get("source_run_hash") or ""),
                "source_run_namespace": str(
                    payload.get("source_run_namespace") or planned.get("namespace_token") or ""
                ),
                "row_count": int(payload.get("closed_minute_row_count") or 0),
                "sha256": str(source.get("sha256") or ""),
                "fetch_group_key": list(
                    _active_a_minute_batch_fetch_group_key_for_planned(planned)
                ),
            }
        )
        reported_paths.add(str(source.get("path") or ""))
    result["selection_reason"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
    result["mode"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
    result["selected_object_count"] = int(summary.get("selected_object_count") or len(planned_artifacts))
    result["selected_ref_count"] = int(summary.get("selected_ref_count") or 0)
    result["closed_minute_label"] = str(summary.get("closed_minute_label") or "")
    result["candidate_scan_bounded"] = True
    result["candidate_scan_limit"] = _current_day_source_provider_max_candidates(args)
    result["candidate_scan_scanned_count"] = len(active_scope_artifacts)
    result["candidate_count"] = len(planned_artifacts)
    result["remaining_candidate_count"] = int(summary.get("remaining_candidate_count") or 0)
    result["source_artifacts"] = [
        *reusable_source_artifacts,
        *reported_source_artifacts,
    ]
    _validate_current_day_source_provider_result(result)
    return result


def _post_close_final_a_c1_pull_attempt_payload(
    *,
    args: argparse.Namespace,
    invocation_id: str,
    status: str,
    planned_artifacts: Sequence[Mapping[str, Any]],
    close_grace_pull: Mapping[str, Any] | None = None,
    provider_result: Mapping[str, Any] | None = None,
    error_type: str = "",
) -> dict[str, Any]:
    for_trade_date = str(getattr(args, "for_trade_date", "") or "")
    raw_source = source_close_label_for_physical_start_label(
        for_trade_date,
        POST_CLOSE_FINAL_A_PHYSICAL_MINUTE_LABEL,
    )
    result = dict(provider_result or {})
    grace = dict(close_grace_pull or {})
    provider_scope_rows = sorted(
        (
            {
                "for_trade_date": str(item.get("for_trade_date") or for_trade_date),
                "target_hhmm": str(item.get("target_hhmm") or ""),
                "source_run_hash": str(item.get("source_run_hash") or ""),
                "source_run_namespace": str(item.get("source_run_namespace") or ""),
            }
            for item in planned_artifacts
        ),
        key=lambda item: (
            item["for_trade_date"],
            item["target_hhmm"],
            item["source_run_namespace"],
            item["source_run_hash"],
        ),
    )
    return {
        "artifact_type": POST_CLOSE_FINAL_A_C1_PULL_ATTEMPT_ARTIFACT_TYPE,
        "artifact_schema_version": "v1",
        "producer_layer": "N3_market_data",
        "for_trade_date": for_trade_date,
        "status": status,
        "invocation_id": invocation_id,
        "current_exchange_time": str(
            getattr(args, "fastlane_current_exchange_time", "") or ""
        ),
        "target_physical_minute_label": POST_CLOSE_FINAL_A_PHYSICAL_MINUTE_LABEL,
        "raw_source_close_label": str(raw_source.get("raw_source_label") or ""),
        "selected_provider_candidate_count": len(planned_artifacts),
        "selected_provider_scope_sha256": _json_payload_sha256(
            {"provider_scope_rows": provider_scope_rows}
        ),
        "full_scope_pending_object_count": int(
            grace.get("full_scope_pending_object_count") or len(planned_artifacts)
        ),
        "full_scope_selected_object_count": int(
            grace.get("full_scope_selected_object_count") or len(planned_artifacts)
        ),
        "full_scope_remaining_object_count": int(
            grace.get("full_scope_remaining_object_count") or 0
        ),
        "source_artifact_written_count": int(result.get("artifact_count") or 0),
        "source_row_count": int(result.get("source_row_count") or 0),
        "failed_candidate_count": int(result.get("failed_candidate_count") or 0),
        "external_pull_attempted": True,
        "error_type": error_type,
        "database_written": False,
        "writes_canonical_minute_bar_1m": False,
        "writes_n3_outbox": False,
        "touches_n4_n5_n6_outbox": False,
        "updates_n4_outbox": False,
        "scans_n5_db": False,
        "full_market_fallback_used": False,
    }


def _run_post_close_final_a_single_close_grace_provider_adapter(
    *,
    args: argparse.Namespace,
    invocation_id: str,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    current_day_source_provider_adapter: Callable[..., Mapping[str, Any]],
    close_grace_pull: dict[str, Any],
) -> dict[str, Any] | None:
    if close_grace_pull.get("external_pull_allowed") is not True:
        raise FastlaneShellBlocked("post_close_final_a_close_grace_pull_not_allowed")
    marker_path = _post_close_final_a_c1_pull_attempt_marker_path(
        args,
        output_dir=output_dir,
    )
    invoked: dict[str, Any] = {
        "value": False,
        "planned_artifacts": [],
    }

    def guarded_provider(
        *,
        args: argparse.Namespace,
        planned_artifacts: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        try:
            _claim_atomic_compact_json(
                marker_path,
                _post_close_final_a_c1_pull_attempt_payload(
                    args=args,
                    invocation_id=invocation_id,
                    status="started",
                    planned_artifacts=planned_artifacts,
                    close_grace_pull=close_grace_pull,
                ),
            )
        except FileExistsError as exc:
            raise FastlaneShellBlocked(
                "post_close_final_a_close_grace_pull_already_attempted"
            ) from exc
        invoked["value"] = True
        invoked["planned_artifacts"] = [dict(item) for item in planned_artifacts]
        return current_day_source_provider_adapter(
            args=args,
            planned_artifacts=planned_artifacts,
        )

    try:
        result = _run_active_a_minute_batch_direct_provider_adapter(
            args=args,
            active_scope_artifacts=active_scope_artifacts,
            output_dir=output_dir,
            current_day_source_provider_adapter=guarded_provider,
        )
    except Exception as exc:
        if invoked["value"]:
            _write_atomic_compact_json(
                marker_path,
                _post_close_final_a_c1_pull_attempt_payload(
                    args=args,
                    invocation_id=invocation_id,
                    status="failed",
                    planned_artifacts=invoked["planned_artifacts"],
                    close_grace_pull=close_grace_pull,
                    error_type=type(exc).__name__,
                ),
            )
            close_grace_pull.update(
                {
                    "reason": "post_close_final_a_close_grace_pull_failed",
                    "external_pull_allowed": False,
                    "attempt_marker_exists": True,
                    "attempt_marker_status": "failed",
                    "attempt_marker_path": str(marker_path),
                }
            )
        raise
    if invoked["value"]:
        _write_atomic_compact_json(
            marker_path,
            _post_close_final_a_c1_pull_attempt_payload(
                args=args,
                invocation_id=invocation_id,
                status="completed",
                planned_artifacts=invoked["planned_artifacts"],
                close_grace_pull=close_grace_pull,
                provider_result=result,
            ),
        )
        close_grace_pull.update(
            {
                "reason": "post_close_final_a_close_grace_pull_completed",
                "external_pull_allowed": False,
                "attempt_marker_exists": True,
                "attempt_marker_status": "completed",
                "attempt_marker_path": str(marker_path),
            }
        )
    return result


def _materialize_active_a_minute_batch_direct_staging_artifacts(
    *,
    args: argparse.Namespace,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    observed_at: Any,
    deadline_check: Callable[[str], None] | None = None,
    source_artifacts: Sequence[Mapping[str, Any]] | None = None,
) -> int:
    source_dir_text = str(getattr(args, "current_day_source_artifact_dir", "") or "").strip()
    if not source_dir_text:
        return 0
    source_dir = Path(source_dir_text)
    if not source_dir.exists() or not source_dir.is_dir():
        raise FastlaneShellBlocked("current_day_source_artifact_dir_missing")
    materialized_count = 0
    scoped_plan = _build_scoped_executor_plan(
        active_scope_artifacts=active_scope_artifacts,
        output_dir=output_dir,
        plan_status="planned",
        blocked_reason=None,
        include_component_readiness=False,
    )
    provider_source_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    provider_sources_by_object_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for source_artifact in source_artifacts or []:
        path_text = str(source_artifact.get("path") or "").strip()
        if not path_text:
            continue
        source = _read_optional_json_artifact(path_text)
        if not source["exists"]:
            continue
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != CURRENT_DAY_SOURCE_ROWS_TYPE:
            raise FastlaneShellBlocked("current_day_source_artifact_contract_mismatch")
        target_hhmm = str(
            payload.get("target_hhmm")
            or source_artifact.get("target_hhmm")
            or payload.get("target_minute_label")
            or ""
        ).replace(":", "")
        source_run_hash = str(payload.get("source_run_hash") or source_artifact.get("source_run_hash") or "")
        key = (target_hhmm, source_run_hash)
        if key in provider_source_by_key and provider_source_by_key[key].get("path") != source.get("path"):
            raise FastlaneShellBlocked("current_day_source_artifact_ambiguous")
        provider_source_by_key[key] = source
        object_key = tuple(source_artifact.get("fetch_group_key") or ())
        if len(object_key) != 4:
            object_key = _active_a_minute_batch_source_payload_fetch_group_key(payload)
        if object_key:
            source_with_target = dict(source)
            source_with_target["_provider_target_hhmm"] = target_hhmm
            provider_sources_by_object_key.setdefault(object_key, []).append(source_with_target)
    for values in provider_sources_by_object_key.values():
        values.sort(key=_active_a_minute_batch_source_target_sort_key)
    for planned in scoped_plan.get("planned_artifacts") or []:
        active_scope = _read_optional_json_artifact(str(planned.get("input_active_scope_artifact_path") or ""))
        if not active_scope["exists"]:
            raise FastlaneShellBlocked("active_scope_artifact_missing")
        pull_plan_payload = _build_inline_pull_plan_for_active_a_minute_batch(planned, observed_at=observed_at)
        if pull_plan_payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
            raise FastlaneShellBlocked("scoped_pull_plan_contract_mismatch")
        if pull_plan_payload.get("full_market_fallback_used") is True:
            raise FastlaneShellBlocked("full_market_fallback_forbidden")
        if _is_clean_noop_pull_plan_payload(pull_plan_payload):
            continue
        if pull_plan_payload.get("plan_status") != "planned":
            raise FastlaneShellBlocked(str(pull_plan_payload.get("blocked_reason") or "scoped_pull_plan_not_planned"))
        target_hhmm = str(planned.get("target_hhmm") or "")
        source_run_hash = str(planned.get("source_run_hash") or "")
        source_rows = provider_source_by_key.get((target_hhmm, source_run_hash))
        if source_rows is None:
            object_key = _active_a_minute_batch_fetch_group_key_from_payload(
                active_scope.get("payload") or {},
                target_hhmm=target_hhmm,
            )
            for candidate_source in provider_sources_by_object_key.get(object_key, []):
                if _hhmm_int(str(candidate_source.get("_provider_target_hhmm") or "")) >= _hhmm_int(target_hhmm):
                    source_rows = candidate_source
                    break
        if source_rows is None:
            source_rows = _find_current_day_source_rows_artifact(
                source_dir,
                target_hhmm=target_hhmm,
                source_run_hash=source_run_hash,
                namespace_token=str(planned.get("namespace_token") or ""),
            )
        if not source_rows:
            continue
        source_rows_payload = source_rows["payload"]
        source_rows_payload = _source_rows_filtered_to_pull_plan(
            source_rows_payload,
            pull_plan_payload=pull_plan_payload,
        )
        staging = build_n3_c1_scoped_current_day_staging_artifact(
            active_scope["payload"],
            pull_plan_artifact=pull_plan_payload,
            source_rows_artifact=source_rows_payload,
            target_hhmm=str(planned.get("target_hhmm") or ""),
            observed_at=observed_at,
            source_pull_plan_path="",
            source_pull_plan_hash="",
            source_rows_artifact_path=str(source_rows.get("path") or ""),
            source_rows_artifact_hash=str(source_rows.get("sha256") or ""),
        )
        if staging.get("artifact_status") != "passed":
            raise FastlaneShellBlocked(str(staging.get("blocked_reason") or "current_day_staging_contract_mismatch"))
        staging_written_at = datetime.now().astimezone().isoformat()
        staging["c1_lane_mode"] = ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE
        staging["source_written_at"] = source_rows_payload.get("source_written_at")
        staging["staging_written_at"] = staging_written_at
        staging["minute_closed_to_source_ms"] = source_rows_payload.get("minute_closed_to_source_ms")
        staging["source_to_staging_ms"] = _elapsed_ms(
            started_at=source_rows_payload.get("source_written_at"),
            completed_at=staging_written_at,
        )
        staging["staging_to_proof_ms"] = None
        staging["proof_to_action_ms"] = None
        staging_path = Path(str(planned.get("staging_artifact_path") or ""))
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        staging_path.write_text(
            json.dumps(staging, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        materialized_count += 1
        if deadline_check is not None:
            deadline_check("active_a_minute_batch_staging_candidate")
    return materialized_count


def _merge_active_a_minute_batch_execution_summary(
    summary: Mapping[str, Any] | None,
    *,
    current_day_source_provider_result: Mapping[str, Any] | None,
    staging_artifact_written_count: int,
) -> dict[str, Any]:
    result = dict(summary or {})
    provider = dict(current_day_source_provider_result or {})
    result.setdefault("mode", ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE)
    result.setdefault("reason", ACTIVE_A_MINUTE_BATCH_DIRECT_PROVIDER_MODE)
    result["source_artifact_written_count"] = int(provider.get("artifact_count") or 0)
    result["staging_artifact_written_count"] = int(staging_artifact_written_count or 0)
    result["failed_candidate_count"] = int(provider.get("failed_candidate_count") or 0)
    result["remaining_candidate_count"] = int(
        provider.get("remaining_candidate_count") or result.get("remaining_candidate_count") or 0
    )
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

    def batch_adapter(
        *,
        args: argparse.Namespace,
        planned_artifacts: Sequence[Mapping[str, Any]],
        previous_context_dir: Path,
    ) -> dict[str, Any]:
        return _build_previous_day_context_artifacts_batch_from_postgres(
            args=args,
            planned_artifacts=planned_artifacts,
            previous_context_dir=Path(previous_context_dir),
            provider_name=provider_name,
        )

    def inline_rows_batch_adapter(
        *,
        args: argparse.Namespace,
        staging_payloads: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return _load_previous_day_context_rows_for_object_cursor_batch(
            args=args,
            staging_payloads=staging_payloads,
            provider_name=provider_name,
        )

    setattr(adapter, "batch_adapter", batch_adapter)
    setattr(adapter, "inline_rows_batch_adapter", inline_rows_batch_adapter)
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
            market_adapter_factory=MootdxTodayMinuteAdapter,
            provider_name=provider_name,
        )

    def inline_batch_adapter(
        *,
        args: argparse.Namespace,
        planned_artifacts: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        from ashare_v3.market.today_minute_execute import MootdxTodayMinuteAdapter

        return _build_current_day_source_rows_with_market_adapter(
            args=args,
            planned_artifacts=planned_artifacts,
            market_adapter_factory=MootdxTodayMinuteAdapter,
            provider_name=provider_name,
            persist_artifacts=False,
        )

    setattr(adapter, "inline_batch_adapter", inline_batch_adapter)
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
    market_adapter: Any | None = None,
    market_adapter_factory: Callable[[], Any] | None = None,
    provider_name: str,
    persist_artifacts: bool = True,
) -> dict[str, Any]:
    source_dir_text = str(getattr(args, "current_day_source_artifact_dir", "") or "").strip()
    if persist_artifacts and not source_dir_text:
        raise FastlaneShellBlocked("current_day_source_artifact_dir_required")
    if market_adapter is None and market_adapter_factory is None:
        raise FastlaneShellBlocked("current_day_source_provider_adapter_required")
    source_dir = Path(source_dir_text or ".")
    if persist_artifacts:
        source_dir.mkdir(parents=True, exist_ok=True)
    artifact_count = 0
    source_row_count = 0
    source_artifacts: list[dict[str, Any]] = []
    failed_candidates: list[dict[str, Any]] = []
    candidate_results: list[dict[str, Any]] = []
    provider_concurrency = min(_current_day_source_provider_concurrency(args), max(1, len(planned_artifacts)))
    worker_local = threading.local()
    adapter_count_lock = threading.Lock()
    provider_adapter_instance_count = 0

    def market_adapter_for_worker() -> Any:
        nonlocal provider_adapter_instance_count
        if market_adapter_factory is None:
            return market_adapter
        candidate_market_adapter = getattr(worker_local, "market_adapter", None)
        if candidate_market_adapter is None:
            candidate_market_adapter = market_adapter_factory()
            worker_local.market_adapter = candidate_market_adapter
            with adapter_count_lock:
                provider_adapter_instance_count += 1
        return candidate_market_adapter

    def process_planned_artifact(planned: Mapping[str, Any]) -> dict[str, Any]:
        target_hhmm = str(planned.get("target_hhmm") or "")
        source_run_hash = str(planned.get("source_run_hash") or "")
        namespace_token = str(planned.get("namespace_token") or "")
        inline_payload = planned.get("inline_pull_plan_payload")
        if isinstance(inline_payload, Mapping):
            payload = dict(inline_payload)
        else:
            pull_plan = _read_optional_json_artifact(str(planned.get("pull_plan_path") or ""))
            if not pull_plan["exists"]:
                raise FastlaneShellBlocked("scoped_pull_plan_missing_for_source_provider")
            payload = dict(pull_plan.get("payload") or {})
        if payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
            raise FastlaneShellBlocked("scoped_pull_plan_contract_mismatch")
        if _is_clean_noop_pull_plan_payload(payload):
            return {"status": "skipped", "reason": "clean_noop_pull_plan"}
        if payload.get("plan_status") != "planned":
            raise FastlaneShellBlocked("scoped_pull_plan_not_planned")
        if int(payload.get("scope_count") or 0) <= 0:
            return {"status": "skipped", "reason": "empty_pull_plan_scope"}
        if payload.get("full_market_fallback_used") is True:
            raise FastlaneShellBlocked("full_market_fallback_forbidden")
        for_trade_date = str(payload.get("for_trade_date") or planned.get("for_trade_date") or "")
        if not namespace_token:
            namespace_token = f"{for_trade_date}_{target_hhmm}_{source_run_hash or 'unknown'}"
        try:
            candidate_market_adapter = market_adapter_for_worker()
        except Exception as exc:  # noqa: BLE001 - isolate provider connection setup failures per candidate.
            return {
                "status": "failed",
                "candidate_result": {
                    "namespace_token": namespace_token,
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "status": "failed",
                    "reason": "current_day_source_provider_adapter_init_failed",
                    "error_type": type(exc).__name__,
                },
                "failed_candidate": {
                    "namespace_token": namespace_token,
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "failure_count": 1,
                    "reason": "current_day_source_provider_adapter_init_failed",
                    "error_type": type(exc).__name__,
                },
            }
        rows: list[dict[str, Any]] = []
        plan_failures: list[dict[str, Any]] = []
        for plan_row in payload.get("plan_rows") or []:
            subscription = _subscription_from_plan_row(plan_row)
            try:
                fetched_rows = candidate_market_adapter.fetch_minute_bars(subscription, for_trade_date)
            except Exception as exc:  # noqa: BLE001 - isolate one provider candidate from the batch.
                plan_failures.append(
                    {
                        "identity_key": subscription.get("identity_key"),
                        "asset_kind": subscription.get("asset_kind"),
                        "target_hhmm": target_hhmm,
                        "source_run_hash": source_run_hash,
                        "reason": "current_day_source_provider_fetch_failed",
                        "error_type": type(exc).__name__,
                    }
                )
                continue
            rows.extend(
                _current_day_source_rows_from_provider_rows(
                    provider_rows=list(fetched_rows or []),
                    plan_row=plan_row,
                    for_trade_date=for_trade_date,
                    provider_name=provider_name,
                )
            )
        if plan_failures:
            return {
                "status": "failed",
                "candidate_result": {
                    "namespace_token": namespace_token,
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "status": "failed",
                    "reason": "current_day_source_provider_fetch_failed",
                    "failure_count": len(plan_failures),
                },
                "failed_candidate": {
                    "namespace_token": namespace_token,
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "failure_count": len(plan_failures),
                    "failures": plan_failures,
                },
            }
        source_written_at = datetime.now().astimezone().isoformat()
        minute_closed_to_source_ms = _minute_closed_to_observed_ms(
            for_trade_date=for_trade_date,
            target_hhmm=target_hhmm,
            observed_at=source_written_at,
        )
        plan_rows = [row for row in payload.get("plan_rows") or [] if isinstance(row, Mapping)]
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
            "source_adapter": getattr(candidate_market_adapter, "external_source", provider_name),
            "source_version": getattr(candidate_market_adapter, "source_version", "unknown"),
            "direction": str((plan_rows[0] if plan_rows else {}).get("direction") or ""),
            "source_written_at": source_written_at,
            "minute_closed_to_source_ms": minute_closed_to_source_ms,
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
        artifact_sha256 = _json_payload_sha256(artifact)
        if persist_artifacts:
            path.write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            artifact_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        source_artifact = {
            "path": str(path) if persist_artifacts else f"inline://object_cursor_batch/{namespace_token}",
            "target_hhmm": target_hhmm,
            "for_trade_date": for_trade_date,
            "artifact_type": CURRENT_DAY_SOURCE_ROWS_TYPE,
            "source_run_hash": source_run_hash,
            "source_run_namespace": namespace_token,
            "row_count": len(rows),
            "sha256": artifact_sha256,
            "payload": artifact if not persist_artifacts else None,
            "object_batch_key": list(planned.get("object_batch_key") or []),
        }
        return {
            "status": "passed",
            "row_count": len(rows),
            "source_artifact": source_artifact,
            "candidate_result": {
                "namespace_token": namespace_token,
                "target_hhmm": target_hhmm,
                "source_run_hash": source_run_hash,
                "status": "passed",
                "row_count": len(rows),
                "artifact_path": str(path) if persist_artifacts else source_artifact["path"],
                "source_written_at": source_written_at,
                "minute_closed_to_source_ms": minute_closed_to_source_ms,
            },
        }

    if provider_concurrency <= 1 or len(planned_artifacts) <= 1:
        processed_results = [process_planned_artifact(planned) for planned in planned_artifacts]
    else:
        with ThreadPoolExecutor(max_workers=provider_concurrency) as executor:
            processed_results = list(executor.map(process_planned_artifact, planned_artifacts))

    for item in processed_results:
        status = str(item.get("status") or "")
        if status == "passed":
            artifact_count += 1
            source_row_count += int(item.get("row_count") or 0)
            source_artifacts.append(dict(item.get("source_artifact") or {}))
            candidate_results.append(dict(item.get("candidate_result") or {}))
            continue
        if status == "failed":
            failed_candidates.append(dict(item.get("failed_candidate") or {}))
            candidate_results.append(dict(item.get("candidate_result") or {}))
    return {
        "adapter_type": "n3_c1_scoped_current_day_source_rows_provider_adapter_v1",
        "provider_name": provider_name,
        "provider_concurrency": provider_concurrency,
        "provider_max_concurrency": MAX_CURRENT_DAY_SOURCE_PROVIDER_CONCURRENCY,
        "provider_adapter_instance_count": provider_adapter_instance_count,
        "concurrency_limited": provider_concurrency < len(planned_artifacts),
        "minute_closed_to_source_ms": max(
            (
                int(item["minute_closed_to_source_ms"])
                for item in candidate_results
                if item.get("minute_closed_to_source_ms") is not None
            ),
            default=None,
        ),
        "source_to_staging_ms": None,
        "staging_to_proof_ms": None,
        "proof_to_action_ms": None,
        "artifact_written": persist_artifacts and artifact_count > 0,
        "artifact_count": artifact_count if persist_artifacts else 0,
        "inline_payload_count": artifact_count if not persist_artifacts else 0,
        "source_row_count": source_row_count,
        "source_artifacts": source_artifacts,
        "candidate_results": candidate_results,
        "failed_candidate_count": len(failed_candidates),
        "failed_candidates": failed_candidates,
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


def _is_clean_noop_pull_plan_payload(payload: Mapping[str, Any]) -> bool:
    if payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
        return False
    if payload.get("full_market_fallback_used") is True:
        return False
    plan_status = str(payload.get("plan_status") or "")
    scope_count = int(payload.get("scope_count") or 0)
    return plan_status in {"noop", "planned"} and scope_count <= 0


def _planned_artifact_has_executable_pull_plan(planned_artifact: Mapping[str, Any]) -> bool:
    pull_plan = _read_optional_json_artifact(str(planned_artifact.get("pull_plan_path") or ""))
    if not pull_plan["exists"]:
        return False
    payload = pull_plan.get("payload") or {}
    if payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
        raise FastlaneShellBlocked("scoped_pull_plan_contract_mismatch")
    if payload.get("full_market_fallback_used") is True:
        raise FastlaneShellBlocked("full_market_fallback_forbidden")
    if _is_clean_noop_pull_plan_payload(payload):
        return False
    if payload.get("plan_status") != "planned":
        raise FastlaneShellBlocked("scoped_pull_plan_not_planned")
    return int(payload.get("scope_count") or 0) > 0


def _build_metric_context_from_source_artifacts(
    *,
    args: argparse.Namespace,
    planned_artifacts: Sequence[Mapping[str, Any]],
    source_dir: Path,
    previous_day_context_provider_adapter: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    _ensure_metric_context_source_artifact_dir(args, source_dir)
    artifact_count = 0
    source_artifacts: list[dict[str, Any]] = []
    skipped_candidates: list[dict[str, Any]] = []
    candidate_blockers: list[dict[str, Any]] = []
    previous_day_context_provider_results: list[dict[str, Any]] = []
    previous_day_context_batch_result: dict[str, Any] | None = None
    batch_blockers_by_candidate: dict[tuple[str, str, str], str] = {}
    batch_adapter = getattr(previous_day_context_provider_adapter, "batch_adapter", None)
    if callable(batch_adapter):
        previous_context_dir_text = str(
            getattr(args, "previous_day_context_artifact_dir", "") or ""
        ).strip()
        previous_context_dir = Path(previous_context_dir_text) if previous_context_dir_text else None
        batch_candidates: list[Mapping[str, Any]] = []
        for planned in planned_artifacts:
            target_hhmm = str(planned.get("target_hhmm") or "")
            source_run_hash = str(planned.get("source_run_hash") or "")
            source = _find_metric_context_source_artifact(
                source_dir,
                target_hhmm=target_hhmm,
                source_run_hash=source_run_hash,
                namespace_token=str(planned.get("namespace_token") or ""),
                exact_only=True,
                canonical_path_only=True,
            )
            if source:
                source_payload = source.get("payload") or {}
                if (
                    _metric_context_artifact_needs_open_boundary_previous_period_rebuild(source_payload)
                    or _metric_context_artifact_needs_rolling_window_rebuild(source_payload)
                ):
                    source = None
            if not source:
                staging = _read_optional_json_artifact(str(planned.get("staging_artifact_path") or ""))
                previous_context = (
                    _find_previous_day_context_artifact(
                        previous_context_dir,
                        target_hhmm=target_hhmm,
                        source_run_hash=source_run_hash,
                        namespace_token=str(planned.get("namespace_token") or ""),
                        staging_artifact=staging.get("payload") or {},
                        exact_only=True,
                        canonical_path_only=True,
                    )
                    if previous_context_dir is not None and staging.get("exists")
                    else None
                )
                if not previous_context:
                    batch_candidates.append(planned)
        if batch_candidates and previous_context_dir is not None:
            previous_day_context_batch_result = dict(
                batch_adapter(
                    args=args,
                    planned_artifacts=batch_candidates,
                    previous_context_dir=previous_context_dir,
                )
                or {}
            )
            _validate_previous_day_context_batch_provider_result(previous_day_context_batch_result)
            for provider_result in (
                previous_day_context_batch_result.get("previous_day_context_provider_results") or []
            ):
                result = dict(provider_result or {})
                _validate_previous_day_context_provider_result(result)
                previous_day_context_provider_results.append(result)
            for blocker in previous_day_context_batch_result.get("candidate_blockers") or []:
                blocked = dict(blocker or {})
                key = (
                    str(blocked.get("target_hhmm") or ""),
                    str(blocked.get("source_run_hash") or ""),
                    str(blocked.get("namespace_token") or ""),
                )
                batch_blockers_by_candidate[key] = str(
                    blocked.get("blocked_reason") or "previous_day_context_missing"
                )
    for planned in planned_artifacts:
        target_hhmm = str(planned.get("target_hhmm") or "")
        source_run_hash = str(planned.get("source_run_hash") or "")
        try:
            source = _find_metric_context_source_artifact(
                source_dir,
                target_hhmm=target_hhmm,
                source_run_hash=source_run_hash,
                namespace_token=str(planned.get("namespace_token") or ""),
                exact_only=True,
                canonical_path_only=True,
            )
            if source:
                source_payload = source.get("payload") or {}
                if _metric_context_artifact_needs_open_boundary_previous_period_rebuild(
                    source_payload
                ) or _metric_context_artifact_needs_rolling_window_rebuild(source_payload):
                    source = None
            if not source:
                candidate_key = (
                    target_hhmm,
                    source_run_hash,
                    str(planned.get("namespace_token") or ""),
                )
                if candidate_key in batch_blockers_by_candidate:
                    raise FastlaneShellBlocked(batch_blockers_by_candidate[candidate_key])
                provider_result = _materialize_metric_context_source_artifact_from_previous_day_context(
                    args=args,
                    planned_artifact=planned,
                    source_dir=source_dir,
                    target_hhmm=target_hhmm,
                    exact_previous_context_only=callable(batch_adapter),
                    previous_day_context_provider_adapter=(
                        None if callable(batch_adapter) else previous_day_context_provider_adapter
                    ),
                )
                if provider_result:
                    previous_day_context_provider_results.append(provider_result)
                source = _find_metric_context_source_artifact(
                    source_dir,
                    target_hhmm=target_hhmm,
                    source_run_hash=source_run_hash,
                    namespace_token=str(planned.get("namespace_token") or ""),
                    exact_only=True,
                    canonical_path_only=True,
                )
            if not source:
                raise FastlaneShellBlocked("metric_context_source_artifact_missing")
            active_scope = _read_optional_json_artifact(str(planned.get("input_active_scope_artifact_path") or ""))
            if not active_scope["exists"]:
                raise FastlaneShellBlocked("active_scope_artifact_missing")
            staging = _read_optional_json_artifact(str(planned.get("staging_artifact_path") or ""))
            staging_payload = dict(staging.get("payload") or {})
            metric_path = Path(str(planned.get("metric_context_artifact_path") or ""))
            existing_metric = _read_optional_json_artifact(str(metric_path)) if metric_path.exists() else {}
            metric_context_needs_rebuild = bool(
                existing_metric.get("exists")
                and (
                    _metric_context_artifact_needs_open_boundary_previous_period_rebuild(
                        existing_metric.get("payload") or {}
                    )
                    or _metric_context_artifact_needs_rolling_window_rebuild(
                        existing_metric.get("payload") or {}
                    )
                )
            )
            if metric_path.exists() and not metric_context_needs_rebuild:
                skipped_candidates.append(
                    _metric_context_candidate_record(
                        planned,
                        reason="metric_context_artifact_already_exists",
                    )
                )
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
                raise FastlaneShellBlocked(
                    str(artifact.get("blocked_reason") or "metric_context_source_contract_mismatch")
                )
            proof_artifact_written_at = datetime.now().astimezone().isoformat()
            artifact["source_written_at"] = staging_payload.get("source_written_at")
            artifact["staging_written_at"] = staging_payload.get("staging_written_at")
            artifact["proof_artifact_written_at"] = proof_artifact_written_at
            artifact["minute_closed_to_source_ms"] = staging_payload.get("minute_closed_to_source_ms")
            artifact["source_to_staging_ms"] = staging_payload.get("source_to_staging_ms")
            artifact["staging_to_proof_ms"] = _elapsed_ms(
                started_at=staging_payload.get("staging_written_at"),
                completed_at=proof_artifact_written_at,
            )
            artifact["proof_to_action_ms"] = None
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
                    "source_run_hash": source_run_hash,
                    "artifact_type": "n3_c1_n3t_metric_context_source_v1",
                }
            )
        except FastlaneShellBlocked as exc:
            reason = str(exc)
            if _is_hard_metric_context_builder_blocker(reason):
                raise
            candidate_blockers.append(_metric_context_candidate_record(planned, reason=reason))
            continue
    return {
        "adapter_type": "n3_c1_n3t_metric_context_builder_adapter_v1",
        "artifact_written": artifact_count > 0,
        "artifact_count": artifact_count,
        "source_artifacts": source_artifacts,
        "skipped_candidates": skipped_candidates,
        "candidate_blockers": candidate_blockers,
        "previous_day_context_provider_results": previous_day_context_provider_results,
        "previous_day_context_batch_result": previous_day_context_batch_result,
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


def _ensure_metric_context_source_artifact_dir(args: argparse.Namespace, source_dir: Path) -> None:
    if source_dir.exists():
        if not source_dir.is_dir():
            raise FastlaneShellBlocked("metric_context_source_artifact_dir_not_directory")
        return
    if not bool(getattr(args, "execute", False)):
        raise FastlaneShellBlocked("metric_context_source_artifact_dir_missing")
    output_dir_text = str(getattr(args, "output_dir", "") or "").strip()
    if not output_dir_text:
        raise FastlaneShellBlocked("output_dir_required")
    output_dir = Path(output_dir_text).resolve()
    resolved_source_dir = source_dir.resolve()
    if not _path_is_relative_to(resolved_source_dir, output_dir):
        raise FastlaneShellBlocked("metric_context_source_artifact_dir_missing")
    source_dir.mkdir(parents=True, exist_ok=True)


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _materialize_metric_context_source_artifact_from_previous_day_context(
    *,
    args: argparse.Namespace,
    planned_artifact: Mapping[str, Any],
    source_dir: Path,
    target_hhmm: str,
    exact_previous_context_only: bool = False,
    previous_day_context_provider_adapter: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    previous_context_dir_text = str(getattr(args, "previous_day_context_artifact_dir", "") or "").strip()
    if not previous_context_dir_text:
        raise FastlaneShellBlocked("previous_day_context_missing")
    previous_context_dir = Path(previous_context_dir_text)
    active_scope = _read_optional_json_artifact(str(planned_artifact.get("input_active_scope_artifact_path") or ""))
    staging = _read_optional_json_artifact(str(planned_artifact.get("staging_artifact_path") or ""))
    if not active_scope["exists"]:
        raise FastlaneShellBlocked("active_scope_artifact_missing")
    if not staging["exists"]:
        raise FastlaneShellBlocked("staging_artifact_missing_for_metric_context_source")
    source_run_hash = str(planned_artifact.get("source_run_hash") or "")
    previous_context = _find_previous_day_context_artifact(
        previous_context_dir,
        target_hhmm=target_hhmm,
        source_run_hash=source_run_hash,
        namespace_token=str(planned_artifact.get("namespace_token") or ""),
        staging_artifact=staging["payload"],
        exact_only=exact_previous_context_only,
        canonical_path_only=exact_previous_context_only,
    )
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
        previous_context = _find_previous_day_context_artifact(
            previous_context_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
            namespace_token=str(planned_artifact.get("namespace_token") or ""),
            staging_artifact=staging["payload"],
            exact_only=exact_previous_context_only,
            canonical_path_only=exact_previous_context_only,
        )
    if not previous_context:
        if not exact_previous_context_only and _has_previous_day_context_artifact_for_hhmm(
            previous_context_dir,
            target_hhmm=target_hhmm,
        ):
            raise FastlaneShellBlocked("previous_day_context_source_run_coverage_mismatch")
        if provider_result:
            return provider_result
        raise FastlaneShellBlocked("previous_day_context_missing")
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


def _metric_context_candidate_record(planned: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "target_hhmm": str(planned.get("target_hhmm") or ""),
        "for_trade_date": str(planned.get("for_trade_date") or ""),
        "source_run_hash": str(planned.get("source_run_hash") or ""),
        "namespace_token": str(planned.get("namespace_token") or ""),
        "input_active_scope_artifact_path": str(planned.get("input_active_scope_artifact_path") or ""),
        "staging_artifact_path": str(planned.get("staging_artifact_path") or ""),
        "metric_context_artifact_path": str(planned.get("metric_context_artifact_path") or ""),
        "blocked_reason": reason,
    }


def _is_hard_metric_context_builder_blocker(reason: str) -> bool:
    if "json_invalid" in reason:
        return True
    if "ambiguous" in reason:
        return True
    if "forbidden" in reason:
        return True
    return reason in {
        "metric_context_source_artifact_dir_missing",
        "metric_context_source_artifact_dir_not_directory",
        "output_dir_required",
    }


def _find_metric_context_source_artifact(
    source_dir: Path,
    *,
    target_hhmm: str,
    source_run_hash: str = "",
    namespace_token: str = "",
    exact_only: bool = False,
    canonical_path_only: bool = False,
) -> dict[str, Any] | None:
    if canonical_path_only and namespace_token:
        exact_path = source_dir / f"n3_c1_n3t_metric_context_source_v1_{namespace_token}.json"
        candidate_paths = [exact_path] if exact_path.exists() else []
    else:
        candidate_paths = _metric_context_source_candidate_paths(
            source_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
            namespace_token=namespace_token,
        )
    for path in candidate_paths:
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != "n3_c1_n3t_metric_context_source_v1":
            continue
        payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
        if payload_hhmm.replace(":", "") != target_hhmm:
            continue
        payload_hash = str(payload.get("source_run_hash") or "")
        if source_run_hash and payload_hash and payload_hash != source_run_hash:
            continue
        return source

    if exact_only or canonical_path_only:
        return None

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


def _metric_context_source_candidate_paths(
    source_dir: Path,
    *,
    target_hhmm: str,
    source_run_hash: str = "",
    namespace_token: str = "",
) -> list[Path]:
    paths: list[Path] = []
    if namespace_token:
        exact_path = source_dir / f"n3_c1_n3t_metric_context_source_v1_{namespace_token}.json"
        if exact_path.exists():
            return [exact_path]
    if source_run_hash:
        paths.extend(sorted(source_dir.glob(f"n3_c1_n3t_metric_context_source_v1_*_{target_hhmm}_{source_run_hash}.json")))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _build_metric_context_source_artifact_index(source_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return _build_hhmm_artifact_index(
        source_dir,
        artifact_type="n3_c1_n3t_metric_context_source_v1",
    )


def _find_metric_context_source_artifact_from_index(
    index: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    target_hhmm: str,
    source_run_hash: str = "",
) -> dict[str, Any] | None:
    matches = _matching_hhmm_hash_artifacts_from_index(
        index,
        target_hhmm=target_hhmm,
        source_run_hash=source_run_hash,
    )
    if len(matches) > 1:
        raise FastlaneShellBlocked("metric_context_source_artifact_ambiguous")
    return dict(matches[0]) if matches else None


def _find_current_day_source_rows_artifact(
    source_dir: Path,
    *,
    target_hhmm: str,
    source_run_hash: str = "",
    namespace_token: str = "",
    exact_only: bool = False,
) -> dict[str, Any] | None:
    if namespace_token:
        exact_path = source_dir / f"n3_c1_scoped_current_day_source_rows_v1_{namespace_token}.json"
        if exact_path.exists():
            source = _read_optional_json_artifact(str(exact_path))
            payload = source.get("payload") or {}
            if payload.get("artifact_type") != CURRENT_DAY_SOURCE_ROWS_TYPE:
                raise FastlaneShellBlocked("current_day_source_artifact_contract_mismatch")
            payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
            payload_hash = str(payload.get("source_run_hash") or "")
            if payload_hhmm.replace(":", "") != target_hhmm:
                raise FastlaneShellBlocked("current_day_source_artifact_target_mismatch")
            if source_run_hash and payload_hash and payload_hash != source_run_hash:
                raise FastlaneShellBlocked("current_day_source_artifact_source_run_mismatch")
            return source
        if exact_only:
            return None
    if source_run_hash:
        exact_matches: list[dict[str, Any]] = []
        for path in sorted(source_dir.glob(f"*_{target_hhmm}_{source_run_hash}.json")):
            source = _read_optional_json_artifact(str(path))
            payload = source.get("payload") or {}
            if payload.get("artifact_type") != CURRENT_DAY_SOURCE_ROWS_TYPE:
                continue
            payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
            if payload_hhmm.replace(":", "") != target_hhmm:
                continue
            payload_hash = str(payload.get("source_run_hash") or "")
            if payload_hash and payload_hash != source_run_hash:
                continue
            exact_matches.append(source)
        if len(exact_matches) > 1:
            raise FastlaneShellBlocked("current_day_source_artifact_ambiguous")
        if exact_matches:
            return exact_matches[0]
        return None
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


def _has_stale_morning_close_boundary_gap(payload: Mapping[str, Any]) -> bool:
    """Detect old artifacts that mapped lunch-boundary source labels to 11:29."""

    source = dict(payload or {})
    gaps = list(source.get("source_gap_physical_labels") or [])
    rows = (
        list(source.get("plan_rows") or [])
        + list(source.get("closed_minute_rows") or [])
        + list(source.get("source_rows") or [])
    )
    for row in source.get("plan_rows") or []:
        if isinstance(row, Mapping):
            gaps.extend(list(row.get("source_gap_physical_labels") or []))
    for gap in gaps:
        if not isinstance(gap, Mapping):
            continue
        if (
            str(gap.get("physical_c1_label") or "") == "11:29"
            and str(gap.get("missing_raw_source_label") or "") == "11:30"
        ):
            return True
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        physical_label = str(row.get("physical_c1_label") or "")
        raw_label = str(row.get("raw_source_label") or "")
        if physical_label == "11:29" and raw_label in {"11:30", "13:00"}:
            return True
    return False


def _uses_stale_source_label_policy(payload: Mapping[str, Any]) -> bool:
    source = dict(payload or {})
    policies = [str(source.get("source_label_policy") or "")]
    for row in (
        list(source.get("plan_rows") or [])
        + list(source.get("closed_minute_rows") or [])
        + list(source.get("source_rows") or [])
    ):
        if isinstance(row, Mapping):
            policies.append(str(row.get("source_label_policy") or ""))
    return any(policy and policy != SOURCE_CLOSE_LABEL_POLICY for policy in policies)


def _has_stale_raw_physical_label_mapping(payload: Mapping[str, Any]) -> bool:
    source = dict(payload or {})
    for_trade_date = str(source.get("for_trade_date") or "")
    for row in (
        list(source.get("plan_rows") or [])
        + list(source.get("closed_minute_rows") or [])
        + list(source.get("source_rows") or [])
    ):
        if not isinstance(row, Mapping):
            continue
        physical_label = _hhmm_to_minute_label(row.get("physical_c1_label") or "")
        raw_label = _hhmm_to_minute_label(row.get("raw_source_label") or "")
        if not physical_label or not raw_label:
            continue
        if (
            "09:31" <= raw_label <= "11:29"
            and physical_label != raw_label
            and not (physical_label == "09:30" and raw_label == "09:31")
        ):
            return True
        if raw_label not in {"11:30", "13:00"} and not ("13:01" <= raw_label <= "15:00"):
            continue
        mapped = source_close_label_to_physical_start_label(
            str(row.get("for_trade_date") or for_trade_date),
            raw_label,
        )
        if mapped.get("status") != "mapped":
            continue
        mapped_physical_label = _hhmm_to_minute_label(mapped.get("physical_c1_label") or "")
        if mapped_physical_label and mapped_physical_label != physical_label:
            return True
    return False


def _has_stale_open_boundary_pull_plan(payload: Mapping[str, Any]) -> bool:
    source = dict(payload or {})
    if source.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
        return False

    def has_required_open_label(item: Mapping[str, Any]) -> bool:
        physical_labels = [str(label) for label in item.get("required_physical_labels") or []]
        raw_labels = [str(label) for label in item.get("required_raw_source_labels") or []]
        return "09:30" in physical_labels or "09:30" in raw_labels

    def has_open_boundary_gap(item: Mapping[str, Any]) -> bool:
        for gap in item.get("source_gap_physical_labels") or []:
            if not isinstance(gap, Mapping):
                continue
            if (
                str(gap.get("physical_c1_label") or "") == "09:30"
                and str(gap.get("missing_raw_source_label") or "") == "09:30"
                and str(gap.get("reason") or "") == OPEN_BOUNDARY_MISSING_SOURCE_REASON
            ):
                return True
        return False

    items = [source] + [row for row in source.get("plan_rows") or [] if isinstance(row, Mapping)]
    return any(has_required_open_label(item) and not has_open_boundary_gap(item) for item in items)


def _current_day_artifact_needs_boundary_rebuild(payload: Mapping[str, Any]) -> bool:
    return (
        _has_stale_morning_close_boundary_gap(payload)
        or _has_stale_open_boundary_pull_plan(payload)
        or _uses_stale_source_label_policy(payload)
        or _has_stale_raw_physical_label_mapping(payload)
    )


def _metric_context_artifact_needs_open_boundary_previous_period_rebuild(payload: Mapping[str, Any]) -> bool:
    source = dict(payload or {})
    if source.get("artifact_type") not in {
        "n3_c1_scoped_closed_1m_artifact_v1",
        "n3_c1_n3t_metric_context_source_v1",
    }:
        return False
    for row in source.get("metric_context_rows") or []:
        if not isinstance(row, Mapping):
            continue
        metric_values = dict(row.get("metric_values") or {})
        if str(metric_values.get("previous_120m_period_source") or "") != "not_available":
            continue
        if bool(metric_values.get("is_first_120m_of_day")):
            continue
        if metric_values.get("previous_120m_body_high") in {None, ""}:
            continue
        if metric_values.get("previous_120m_body_low") in {None, ""}:
            continue
        if _metric_context_row_has_open_boundary_source_gap(row):
            return True
    return False


def _metric_context_artifact_needs_rolling_window_rebuild(payload: Mapping[str, Any]) -> bool:
    source = dict(payload or {})
    if source.get("artifact_type") not in {
        "n3_c1_scoped_closed_1m_artifact_v1",
        "n3_c1_n3t_metric_context_source_v1",
    }:
        return False
    for row in source.get("metric_context_rows") or []:
        if not isinstance(row, Mapping):
            continue
        metric_values = dict(row.get("metric_values") or {})
        current_5m_amount = _rolling_current_amount_from_context_row(row, for_trade_date=source.get("for_trade_date"), size=5)
        if current_5m_amount is not None:
            if _has_numeric_value(metric_values.get("current_5m_elapsed_amount")) and _numeric_delta(
                metric_values.get("current_5m_elapsed_amount"), current_5m_amount
            ) > 0.000001:
                return True
            if _has_numeric_value(metric_values.get("current_5m_amount")) and _numeric_delta(
                metric_values.get("current_5m_amount"), current_5m_amount
            ) > 0.000001:
                return True
        current_30m_amount = _rolling_current_amount_from_context_row(row, for_trade_date=source.get("for_trade_date"), size=30)
        if current_30m_amount is not None:
            if _has_numeric_value(metric_values.get("current_30m_closed_elapsed_amount")) and _numeric_delta(
                metric_values.get("current_30m_closed_elapsed_amount"), current_30m_amount
            ) > 0.000001:
                return True
    return False


def _rolling_current_amount_from_context_row(
    row: Mapping[str, Any],
    *,
    for_trade_date: Any,
    size: int,
) -> float | None:
    trade_date = str(for_trade_date or row.get("for_trade_date") or "")
    labels = _canonical_ashare_1m_labels_cached(trade_date) if re.fullmatch(r"\d{8}", trade_date) else ()
    if not labels or size <= 0:
        return None
    rows_by_label: dict[str, Mapping[str, Any]] = {}
    for item in row.get("closed_minute_rows") or []:
        if not isinstance(item, Mapping) or item.get("fake_or_synthetic_row") is True:
            continue
        label = _hhmm_to_minute_label(item.get("physical_c1_label") or item.get("minute_label") or item.get("raw_source_label") or "")
        if label in labels:
            rows_by_label.setdefault(label, item)
    if not rows_by_label:
        return None
    latest_label = max(rows_by_label, key=lambda label: labels.index(label))
    position = labels.index(latest_label) + 1
    start = max(0, position - size)
    expected_labels = list(labels[start:position])
    if expected_labels[:1] == ["09:30"] and "09:31" in expected_labels and "09:30" not in rows_by_label:
        expected_labels = [label for label in expected_labels if label != "09:30"]
    if len(expected_labels) < size:
        return None
    if any(label not in rows_by_label for label in expected_labels):
        return None
    return sum(_numeric_value(rows_by_label[label].get("amount")) for label in expected_labels)


def _numeric_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _has_numeric_value(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _numeric_delta(left: Any, right: float) -> float:
    try:
        return abs(float(left) - float(right))
    except (TypeError, ValueError):
        return float("inf")


def _metric_context_row_has_open_boundary_source_gap(row: Mapping[str, Any]) -> bool:
    labels: set[str] = set()
    for item in row.get("closed_minute_rows") or []:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("physical_c1_label") or item.get("minute_label") or item.get("raw_source_label") or "")
        if label:
            labels.add(_hhmm_to_minute_label(label))
    for item in row.get("source_closed_minute_bar_ids") or []:
        match = re.search(r"(?<!\\d)([0-2][0-9]:[0-5][0-9])(?!\\d)", str(item or ""))
        if match:
            labels.add(match.group(1))
    return "09:31" in labels and "09:30" not in labels


def _planned_artifact_needs_current_day_boundary_rebuild(
    artifact: Mapping[str, Any],
    *,
    source_dir: Path,
    existing_source_rows: Mapping[str, Any] | None = None,
) -> bool:
    for key in ("pull_plan_path", "staging_artifact_path"):
        source = _read_optional_json_artifact(str(artifact.get(key) or ""))
        if source["exists"] and _current_day_artifact_needs_boundary_rebuild(source.get("payload") or {}):
            return True
    source_rows = existing_source_rows
    if source_rows is None:
        source_rows = _find_current_day_source_rows_artifact(
            source_dir,
            target_hhmm=str(artifact.get("target_hhmm") or ""),
            source_run_hash=str(artifact.get("source_run_hash") or ""),
        )
    if source_rows and _current_day_artifact_needs_boundary_rebuild(source_rows.get("payload") or {}):
        return True
    return False


def _is_post_close_final_a_pass(args: argparse.Namespace) -> bool:
    decision = getattr(args, "fastlane_active_worker_decision", {}) or {}
    return (
        str(getattr(args, "fastlane_session_phase", "") or "") == "post_close"
        and str(decision.get("worker_mode") or "") == "post_close_final_a_pass"
    )


def _post_close_final_a_pass_max_candidates(args: argparse.Namespace) -> int:
    value = int(getattr(args, "post_close_final_a_pass_max_candidates_per_invocation", 0) or 0)
    return value if value > 0 else DEFAULT_POST_CLOSE_FINAL_A_PASS_MAX_CANDIDATES


def _current_day_source_provider_max_candidates(args: argparse.Namespace) -> int:
    value = int(getattr(args, "current_day_source_provider_max_candidates_per_invocation", 0) or 0)
    return value if value > 0 else DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_MAX_CANDIDATES


def _current_day_source_provider_concurrency(args: argparse.Namespace) -> int:
    value = int(getattr(args, "current_day_source_provider_concurrency", 0) or 0)
    if value <= 0:
        value = DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_CONCURRENCY
    return min(max(1, value), MAX_CURRENT_DAY_SOURCE_PROVIDER_CONCURRENCY)


def _scoped_pull_plan_max_candidates(args: argparse.Namespace) -> int:
    value = int(getattr(args, "scoped_pull_plan_max_candidates_per_invocation", 0) or 0)
    return value if value > 0 else DEFAULT_SCOPED_PULL_PLAN_MAX_CANDIDATES


def _existing_source_staging_max_candidates(args: argparse.Namespace) -> int:
    value = int(getattr(args, "existing_source_staging_max_candidates_per_invocation", 0) or 0)
    return value if value > 0 else DEFAULT_EXISTING_SOURCE_STAGING_MAX_CANDIDATES


def _existing_staging_metric_context_max_candidates(args: argparse.Namespace) -> int:
    value = int(getattr(args, "existing_staging_metric_context_max_candidates_per_invocation", 0) or 0)
    return value if value > 0 else DEFAULT_EXISTING_STAGING_METRIC_CONTEXT_MAX_CANDIDATES


def _select_post_close_final_a_pass_candidate_chunk(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    max_candidates: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a deterministic bounded chunk for post-close final A processing."""

    bounded_max = max(1, int(max_candidates or DEFAULT_POST_CLOSE_FINAL_A_PASS_MAX_CANDIDATES))
    local_plan = _build_scoped_executor_plan(
        active_scope_artifacts=active_scope_artifacts,
        output_dir=output_dir,
        plan_status="planned",
        blocked_reason=None,
    )
    readiness_by_namespace = {
        str(item.get("namespace_token") or ""): dict(item.get("component_readiness") or {})
        for item in local_plan.get("planned_artifacts") or []
    }
    records: list[dict[str, Any]] = []
    skipped_scope_count_zero = 0
    for sequence, artifact in enumerate(active_scope_artifacts):
        context = _infer_scope_context(artifact)
        payload_source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        payload = payload_source.get("payload") or {}
        scope_count = int(artifact.get("scope_count") or payload.get("scope_count") or 0)
        if scope_count <= 0:
            skipped_scope_count_zero += 1
            continue
        refs = list(_iter_active_scope_tracking_refs(payload))
        unprocessed_ref_count = sum(1 for ref in refs if not _active_scope_ref_has_evaluation_evidence(ref))
        if not refs:
            unprocessed_ref_count = scope_count
        readiness = readiness_by_namespace.get(context["namespace_token"], {})
        status = str(readiness.get("status") or "")
        missing_n3t_proof = status != "metric_context_ready_for_n3t_execute_gate"
        if unprocessed_ref_count > 0 and missing_n3t_proof:
            priority = 0
        elif unprocessed_ref_count > 0:
            priority = 1
        elif missing_n3t_proof:
            priority = 2
        else:
            priority = 3
        records.append(
            {
                "artifact": dict(artifact),
                "priority": priority,
                "sort_key": (
                    priority,
                    _active_scope_event_sort_key(payload, context=context),
                    context["target_hhmm"],
                    context["source_run_hash"],
                    sequence,
                ),
                "unprocessed_ref_count": unprocessed_ref_count,
                "missing_n3t_proof": missing_n3t_proof,
                "component_status": status,
            }
        )
    records.sort(key=lambda item: item["sort_key"])
    selected_records = records[:bounded_max]
    selected = [dict(item["artifact"]) for item in selected_records]
    remaining_count = max(0, len(records) - len(selected_records))
    skipped_count = skipped_scope_count_zero + remaining_count
    summary = {
        "strategy": "post_close_final_a_pass_a_first_bounded_chunk_v1",
        "reason": (
            "post_close_final_a_pass_chunk_incomplete"
            if remaining_count > 0
            else "post_close_final_a_pass_chunk_ready"
        ),
        "max_candidates_per_invocation": bounded_max,
        "total_candidate_count": len(records),
        "processed_candidate_count": len(selected_records),
        "skipped_candidate_count": skipped_count,
        "remaining_candidate_count": remaining_count,
        "scope_count_zero_skipped": skipped_scope_count_zero,
        "selected_source_runs": [
            {
                "source_run_hash": str(item["artifact"].get("source_run_hash") or ""),
                "source_run_namespace": str(item["artifact"].get("source_run_namespace") or ""),
                "unprocessed_ref_count": int(item["unprocessed_ref_count"]),
                "missing_n3t_proof": bool(item["missing_n3t_proof"]),
                "component_status": str(item["component_status"]),
            }
            for item in selected_records
        ],
    }
    return selected, summary


def _iter_active_scope_tracking_refs(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    refs: list[Mapping[str, Any]] = []
    for ref in payload.get("active_tracking_refs") or []:
        if isinstance(ref, Mapping):
            refs.append(ref)
    for row in payload.get("scope_rows") or []:
        if not isinstance(row, Mapping):
            continue
        row_refs = row.get("active_tracking_refs") or []
        if row_refs:
            for ref in row_refs:
                if isinstance(ref, Mapping):
                    refs.append(ref)
            continue
        if str(row.get("state_key") or row.get("source_trigger_run_id") or "").strip():
            refs.append(row)
    return refs


def _active_scope_ref_has_evaluation_evidence(ref: Mapping[str, Any]) -> bool:
    if str(ref.get("action_state") or "") in {"blocked", "executed", "skipped", "expired"}:
        return True
    if str(ref.get("confirmation_status") or "") in {"passed", "failed", "expired"}:
        return True
    raw_json = ref.get("raw_json") or {}
    if isinstance(raw_json, Mapping):
        for key in ("latest_metric_status", "metric_evaluation_key", "last_seen_metric_key"):
            if raw_json.get(key):
                return True
    for key in ("latest_metric_status", "metric_evaluation_key", "last_seen_metric_key"):
        if ref.get(key):
            return True
    return False


def _active_scope_event_sort_key(payload: Mapping[str, Any], *, context: Mapping[str, str]) -> str:
    candidates: list[str] = []
    for key in ("source_trigger_event_time", "trigger_time", "event_time"):
        value = str(payload.get(key) or "").strip()
        if value:
            candidates.append(value)
    for row in payload.get("scope_rows") or []:
        if not isinstance(row, Mapping):
            continue
        for key in ("source_trigger_event_time", "trigger_time", "event_time"):
            value = str(row.get(key) or "").strip()
            if value:
                candidates.append(value)
        for ref in row.get("active_tracking_refs") or []:
            if not isinstance(ref, Mapping):
                continue
            for key in ("source_trigger_event_time", "trigger_time", "event_time"):
                value = str(ref.get(key) or "").strip()
                if value:
                    candidates.append(value)
    if candidates:
        return min(candidates)
    target_hhmm = str(context.get("target_hhmm") or "")
    if re.fullmatch(r"[0-2][0-9][0-5][0-9]", target_hhmm):
        return f"{str(context.get('for_trade_date') or '')}T{target_hhmm[:2]}:{target_hhmm[2:]}:00"
    return target_hhmm


def _select_existing_v2_source_stale_staging_rebuild_artifacts(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    source_dir: Path,
) -> list[dict[str, Any]]:
    """Prioritize stale staging that can be rebuilt from already-correct source rows."""

    if not source_dir.exists() or not source_dir.is_dir():
        return []
    selected: list[dict[str, Any]] = []
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        staging_path = (
            output_dir
            / "current_day_staging"
            / f"n3_c1_scoped_current_day_staging_v1_{context['namespace_token']}_fastlane.json"
        )
        staging = _read_optional_json_artifact(str(staging_path))
        if not staging["exists"]:
            continue
        if not _current_day_artifact_needs_boundary_rebuild(staging.get("payload") or {}):
            continue
        try:
            source_rows = _find_current_day_source_rows_artifact(
                source_dir,
                target_hhmm=context["target_hhmm"],
                source_run_hash=context["source_run_hash"],
            )
        except FastlaneShellBlocked as exc:
            if str(exc) == "current_day_source_artifact_ambiguous":
                continue
            raise
        if not source_rows:
            continue
        if _current_day_artifact_needs_boundary_rebuild(source_rows.get("payload") or {}):
            continue
        selected.append(dict(artifact))
    return selected


def _select_existing_source_missing_staging_artifacts(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    source_dir: Path,
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Interleave local staging for candidates whose current-day source already exists."""

    if max_candidates <= 0:
        return []
    if not source_dir.exists() or not source_dir.is_dir():
        return []
    selected: list[dict[str, Any]] = []
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        try:
            source_rows = _find_current_day_source_rows_artifact(
                source_dir,
                target_hhmm=context["target_hhmm"],
                source_run_hash=context["source_run_hash"],
            )
        except FastlaneShellBlocked as exc:
            if str(exc) == "current_day_source_artifact_ambiguous":
                continue
            raise
        if not source_rows:
            continue
        if _current_day_artifact_needs_boundary_rebuild(source_rows.get("payload") or {}):
            continue
        staging_path = (
            output_dir
            / "current_day_staging"
            / f"n3_c1_scoped_current_day_staging_v1_{context['namespace_token']}_fastlane.json"
        )
        staging = _read_optional_json_artifact(str(staging_path))
        if staging["exists"] and not _current_day_artifact_needs_boundary_rebuild(staging.get("payload") or {}):
            continue
        selected.append(dict(artifact))
        if len(selected) >= max_candidates:
            break
    return selected


def _select_object_minute_c1_lane_priority_artifacts(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    max_candidates: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Prioritize latest object-minute A fanout before older pull-plan backlog."""

    selected, summary = _select_scoped_pull_plan_candidate_chunk(
        active_scope_artifacts=active_scope_artifacts,
        output_dir=output_dir,
        max_candidates=max_candidates,
        require_object_scope_ref_fanout=True,
    )
    result: list[dict[str, Any]] = []
    for artifact in selected:
        item = dict(artifact)
        item["c1_lane_selection_reason"] = "object_minute_c1_lane_prioritized"
        result.append(item)
    return result, summary


def _select_existing_pull_plan_missing_source_staging_artifacts(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    source_dir: Path,
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Prioritize older refs that already have a pull plan but still need source/staging."""

    if max_candidates <= 0:
        return []
    records: list[dict[str, Any]] = []
    candidate_artifacts = [dict(item) for item in active_scope_artifacts]
    for sequence, artifact in enumerate(candidate_artifacts):
        context = _infer_scope_context(artifact)
        namespace_token = context["namespace_token"]
        pull_plan_path = output_dir / f"n3_c1_scoped_current_day_pull_plan_v1_{namespace_token}_fastlane.json"
        staging_path = (
            output_dir
            / "current_day_staging"
            / f"n3_c1_scoped_current_day_staging_v1_{namespace_token}_fastlane.json"
        )
        pull_plan = _read_optional_json_artifact(str(pull_plan_path))
        if not pull_plan["exists"]:
            continue
        payload = dict(pull_plan.get("payload") or {})
        if payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
            raise FastlaneShellBlocked("scoped_pull_plan_contract_mismatch")
        if payload.get("full_market_fallback_used") is True:
            raise FastlaneShellBlocked("full_market_fallback_forbidden")
        if _is_clean_noop_pull_plan_payload(payload):
            continue
        if payload.get("plan_status") != "planned":
            raise FastlaneShellBlocked("scoped_pull_plan_not_planned")
        if int(payload.get("scope_count") or 0) <= 0:
            continue
        if _current_day_artifact_needs_boundary_rebuild(payload):
            continue
        staging = _read_optional_json_artifact(str(staging_path))
        if staging["exists"] and not _current_day_artifact_needs_boundary_rebuild(staging.get("payload") or {}):
            continue
        try:
            source_rows = _find_current_day_source_rows_artifact(
                source_dir,
                target_hhmm=context["target_hhmm"],
                source_run_hash=context["source_run_hash"],
            )
        except FastlaneShellBlocked as exc:
            if str(exc) == "current_day_source_artifact_ambiguous":
                continue
            raise
        if source_rows and not _current_day_artifact_needs_boundary_rebuild(source_rows.get("payload") or {}):
            continue
        records.append(
            {
                "artifact": dict(artifact),
                "sort_key": (
                    _active_scope_event_sort_key(
                        _read_optional_json_artifact(str(artifact.get("path") or "")).get("payload") or {},
                        context=context,
                    ),
                    context["target_hhmm"],
                    context["source_run_hash"],
                    sequence,
                ),
            }
        )
    records.sort(key=lambda item: item["sort_key"])
    selected: list[dict[str, Any]] = []
    for item in records[:max_candidates]:
        artifact = dict(item["artifact"])
        artifact["c1_lane_selection_reason"] = "pull_plan_missing_source_staging_backlog_prioritized"
        selected.append(artifact)
    return selected


def _select_existing_staging_metric_context_artifacts(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    metric_context_source_dir: Path | None,
    previous_context_dir: Path | None,
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Interleave metric-context building once staging and previous context are local."""

    selected, _summary = _select_existing_staging_metric_context_artifact_chunk(
        active_scope_artifacts=active_scope_artifacts,
        output_dir=output_dir,
        metric_context_source_dir=metric_context_source_dir,
        previous_context_dir=previous_context_dir,
        max_candidates=max_candidates,
    )
    return selected


def _active_scope_artifact_object_identity(artifact: Mapping[str, Any]) -> tuple[str, str, str]:
    payload: Mapping[str, Any] = artifact
    rows = payload.get("scope_rows")
    if rows is None and artifact.get("path"):
        source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        payload = source.get("payload") or {}
        rows = payload.get("scope_rows")
    if not isinstance(rows, list) or not rows:
        return "", "", ""
    row = dict(rows[0] or {})
    direction = str(row.get("direction") or "")
    refs = row.get("active_tracking_refs")
    if not direction and isinstance(refs, list) and refs:
        direction = str((refs[0] or {}).get("direction") or "")
    return (
        str(row.get("asset_kind") or ""),
        str(row.get("identity_key") or ""),
        direction,
    )


def _staging_artifact_matches_active_scope_object(
    artifact: Mapping[str, Any],
    staging_payload: Mapping[str, Any],
) -> bool:
    expected_asset_kind, expected_identity_key, expected_direction = _active_scope_artifact_object_identity(artifact)
    if not expected_asset_kind or not expected_identity_key:
        return True
    rows = (
        staging_payload.get("closed_minute_rows")
        or staging_payload.get("staging_rows")
        or staging_payload.get("rows")
        or []
    )
    if not isinstance(rows, list) or not rows:
        return True
    actual_keys = {
        (
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
            str(row.get("direction") or ""),
        )
        for row in rows
        if isinstance(row, Mapping)
    }
    actual_object_keys = {(asset_kind, identity_key) for asset_kind, identity_key, _direction in actual_keys}
    if (expected_asset_kind, expected_identity_key) not in actual_object_keys:
        return False
    if expected_direction and any(direction for _asset_kind, _identity_key, direction in actual_keys):
        return (expected_asset_kind, expected_identity_key, expected_direction) in actual_keys
    return True


def _select_existing_staging_metric_context_artifact_chunk(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    metric_context_source_dir: Path | None,
    previous_context_dir: Path | None,
    max_candidates: int,
    allow_previous_day_context_missing: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a bounded batch that can advance from staging/prevctx to metric context."""

    if max_candidates <= 0:
        return [], _prevctx_to_metric_context_chunk_summary(
            total_candidate_count=0,
            selected_records=[],
            max_candidates=max_candidates,
        )
    candidate_artifacts_all = [dict(item) for item in active_scope_artifacts]
    candidate_artifacts_all.sort(
        key=lambda item: (
            -_n3t_latest_trigger_time_sort_value(item),
            _n3t_candidate_path_readiness_rank(
                item,
                output_dir=output_dir,
                metric_context_source_dir=metric_context_source_dir,
                previous_context_dir=previous_context_dir,
            ),
            _earliest_target_hhmm_first_sort_key(_infer_scope_context(item)["target_hhmm"]),
            _infer_scope_context(item)["source_run_hash"],
        )
    )
    candidate_artifacts = candidate_artifacts_all[: max(0, max_candidates)]
    unscanned_candidate_count = max(0, len(candidate_artifacts_all) - len(candidate_artifacts))
    local_plan = _build_scoped_executor_plan(
        active_scope_artifacts=candidate_artifacts,
        output_dir=output_dir,
        plan_status="planned",
        blocked_reason=None,
        include_component_readiness=False,
    )
    metric_context_source_dir_ready = bool(
        metric_context_source_dir is not None and metric_context_source_dir.exists() and metric_context_source_dir.is_dir()
    )
    previous_context_dir_ready = bool(
        previous_context_dir is not None and previous_context_dir.exists() and previous_context_dir.is_dir()
    )
    records: list[dict[str, Any]] = []
    for sequence, (artifact, planned) in enumerate(
        zip(candidate_artifacts, local_plan.get("planned_artifacts") or [], strict=False)
    ):
        readiness = dict(planned.get("component_readiness") or {})
        target_hhmm = str(planned.get("target_hhmm") or "")
        target_sort_key = _earliest_target_hhmm_first_sort_key(target_hhmm)
        source_run_hash = str(planned.get("source_run_hash") or "")
        staging = _read_optional_json_artifact(str(planned.get("staging_artifact_path") or ""))
        if not staging["exists"]:
            continue
        staging_payload = dict(staging.get("payload") or {})
        if staging_payload.get("artifact_type") != "n3_c1_scoped_current_day_staging_v1":
            continue
        if staging_payload.get("artifact_status") != "passed":
            continue
        if not _staging_artifact_matches_active_scope_object(artifact, staging_payload):
            continue
        if _current_day_artifact_needs_boundary_rebuild(staging_payload):
            continue
        metric_path = Path(str(planned.get("metric_context_artifact_path") or ""))
        if metric_path.exists():
            metric_artifact = _read_optional_json_artifact(str(metric_path))
            if _metric_context_artifact_needs_open_boundary_previous_period_rebuild(
                metric_artifact.get("payload") or {}
            ):
                records.append(
                    {
                        "artifact": dict(artifact),
                        "target_hhmm": target_hhmm,
                        "source_run_hash": source_run_hash,
                        "component_status": str(readiness.get("status") or ""),
                        "selection_reason": "stale_metric_context_open_boundary_rebuild",
                        "selection_rank": 1,
                        "sort_key": (
                            -_n3t_latest_trigger_time_sort_value(artifact),
                            1,
                            target_sort_key,
                            source_run_hash,
                            sequence,
                        ),
                    }
                )
                continue
            if _metric_context_artifact_needs_rolling_window_rebuild(metric_artifact.get("payload") or {}):
                records.append(
                    {
                        "artifact": dict(artifact),
                        "target_hhmm": target_hhmm,
                        "source_run_hash": source_run_hash,
                        "component_status": str(readiness.get("status") or ""),
                        "selection_reason": "stale_metric_context_rolling_window_rebuild",
                        "selection_rank": 1,
                        "sort_key": (
                            -_n3t_latest_trigger_time_sort_value(artifact),
                            1,
                            target_sort_key,
                            source_run_hash,
                            sequence,
                        ),
                    }
                )
                continue
            if _n3t_writer_done_marker_path(output_dir=output_dir, planned_artifact=planned).exists():
                if _n3t_writer_done_marker_is_current(
                    output_dir=output_dir,
                    planned_artifact=planned,
                    metric_context_artifact=metric_artifact,
                ):
                    continue
                records.append(
                    {
                        "artifact": dict(artifact),
                        "target_hhmm": target_hhmm,
                        "source_run_hash": source_run_hash,
                        "component_status": str(readiness.get("status") or ""),
                        "selection_reason": "stale_n3t_writer_done_metric_context_hash_mismatch",
                        "selection_rank": -1,
                        "sort_key": (
                            -_n3t_latest_trigger_time_sort_value(artifact),
                            -1,
                            target_sort_key,
                            source_run_hash,
                            sequence,
                        ),
                    }
                )
                continue
            records.append(
                {
                    "artifact": dict(artifact),
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "component_status": str(readiness.get("status") or ""),
                    "selection_reason": "metric_context_exists",
                    "selection_rank": -1,
                    "sort_key": (
                        -_n3t_latest_trigger_time_sort_value(artifact),
                        -1,
                        target_sort_key,
                        source_run_hash,
                        sequence,
                    ),
                }
            )
            continue
        metric_source = (
            _find_metric_context_source_artifact(
                metric_context_source_dir,
                target_hhmm=target_hhmm,
                source_run_hash=source_run_hash,
                namespace_token=str(planned.get("namespace_token") or ""),
                exact_only=True,
                canonical_path_only=True,
            )
            if metric_context_source_dir_ready and metric_context_source_dir is not None
            else None
        )
        if metric_source:
            records.append(
                {
                    "artifact": dict(artifact),
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "component_status": str(readiness.get("status") or ""),
                    "selection_reason": "metric_context_source_exists",
                    "selection_rank": 0,
                    "sort_key": (
                        -_n3t_latest_trigger_time_sort_value(artifact),
                        0,
                        target_sort_key,
                        source_run_hash,
                        sequence,
                    ),
                }
            )
            continue

        selection_reason = "previous_day_context_missing"
        selection_rank = 3
        if previous_context_dir_ready and previous_context_dir is not None:
            if _find_previous_day_context_artifact(
                previous_context_dir,
                target_hhmm=target_hhmm,
                source_run_hash=source_run_hash,
                namespace_token=str(planned.get("namespace_token") or ""),
                staging_artifact=staging_payload,
                exact_only=True,
                canonical_path_only=allow_previous_day_context_missing,
            ):
                selection_reason = "previous_day_context_exists"
                selection_rank = 1
            elif not allow_previous_day_context_missing and _previous_day_context_exact_candidate_exists(
                previous_context_dir,
                target_hhmm=target_hhmm,
                source_run_hash=source_run_hash,
                namespace_token=str(planned.get("namespace_token") or ""),
            ):
                selection_reason = "previous_day_context_source_run_coverage_mismatch"
                selection_rank = 2
            elif not allow_previous_day_context_missing and _has_previous_day_context_artifact_for_hhmm(
                previous_context_dir, target_hhmm=target_hhmm
            ):
                selection_reason = "previous_day_context_source_run_coverage_mismatch"
                selection_rank = 2
        records.append(
                {
                    "artifact": dict(artifact),
                    "target_hhmm": target_hhmm,
                    "source_run_hash": source_run_hash,
                    "component_status": str(readiness.get("status") or ""),
                    "selection_reason": selection_reason,
                    "selection_rank": selection_rank,
                    "sort_key": (
                        -_n3t_latest_trigger_time_sort_value(artifact),
                        selection_rank,
                        target_sort_key,
                        source_run_hash,
                        sequence,
                    ),
                }
            )
    if not allow_previous_day_context_missing:
        if any(int(item.get("selection_rank") or 0) <= 1 for item in records):
            records = [item for item in records if int(item.get("selection_rank") or 0) <= 1]
        elif any(int(item.get("selection_rank") or 0) == 2 for item in records):
            records = [item for item in records if int(item.get("selection_rank") or 0) == 2]
    records.sort(key=lambda item: item["sort_key"])
    selected_records = records[: max(0, max_candidates)]
    if allow_previous_day_context_missing and max_candidates > 0:
        selected_ids = {id(item) for item in selected_records}
        deferred_records = [
            item
            for item in records
            if id(item) not in selected_ids and int(item.get("selection_rank") or 0) >= 2
        ]
        if deferred_records and not any(int(item.get("selection_rank") or 0) >= 2 for item in selected_records):
            selected_records = [*selected_records[: max(0, max_candidates - 1)], deferred_records[0]]
            selected_records.sort(key=lambda item: item["sort_key"])
    selected = [dict(item["artifact"]) for item in selected_records]
    summary = _prevctx_to_metric_context_chunk_summary(
        total_candidate_count=len(records),
        selected_records=selected_records,
        max_candidates=max_candidates,
    )
    if unscanned_candidate_count:
        summary["priority_candidate_count"] = int(summary.get("priority_candidate_count") or 0) + unscanned_candidate_count
        summary["skipped_candidate_count"] = int(summary.get("skipped_candidate_count") or 0) + unscanned_candidate_count
        summary["remaining_candidate_count"] = int(summary.get("remaining_candidate_count") or 0) + unscanned_candidate_count
        summary["reason"] = "prevctx_to_metric_context_chunk_incomplete"
        summary["candidate_scan_bounded"] = True
        summary["candidate_scan_limit"] = max(0, max_candidates)
    return selected, summary


def _n3t_latest_trigger_time_sort_value(artifact: Mapping[str, Any]) -> float:
    """Return the newest N4 trigger time for latest-trigger-first scheduling."""
    values: list[Any] = []
    for key in ("latest_n4_event_time", "source_trigger_event_time", "trigger_time"):
        values.append(artifact.get(key))
    for scope_row in artifact.get("scope_rows") or []:
        if not isinstance(scope_row, Mapping):
            continue
        for key in ("latest_n4_event_time", "source_trigger_event_time", "trigger_time"):
            values.append(scope_row.get(key))
        for ref in scope_row.get("active_tracking_refs") or []:
            if not isinstance(ref, Mapping):
                continue
            for key in ("latest_n4_event_time", "source_trigger_event_time", "trigger_time"):
                values.append(ref.get(key))
    timestamps: list[float] = []
    for value in values:
        parsed = _parse_iso_datetime_or_none(str(value or ""))
        if parsed is not None:
            timestamps.append(parsed.timestamp())
    return max(timestamps, default=0.0)


def _n3t_candidate_path_readiness_rank(
    artifact: Mapping[str, Any],
    *,
    output_dir: Path,
    metric_context_source_dir: Path | None,
    previous_context_dir: Path | None,
) -> int:
    context = _infer_scope_context(artifact)
    namespace_token = context["namespace_token"]
    target_hhmm = context["target_hhmm"]
    source_run_hash = context["source_run_hash"]
    staging_path = (
        output_dir
        / "current_day_staging"
        / f"n3_c1_scoped_current_day_staging_v1_{namespace_token}_fastlane.json"
    )
    if not staging_path.exists():
        return 9
    metric_path = (
        output_dir
        / "metric_context"
        / f"n3_c1_scoped_closed_1m_artifact_v1_{namespace_token}_fastlane_raw_prevday_c1_amount_v1.json"
    )
    if metric_path.exists():
        marker_path = output_dir / "n3t_writer_done" / f"n3t_writer_done_marker_v1_{namespace_token}.json"
        if marker_path.exists():
            return 8
        return -1
    if metric_context_source_dir is not None and metric_context_source_dir.exists() and metric_context_source_dir.is_dir():
        metric_source_path = (
            metric_context_source_dir
            / f"n3_c1_n3t_metric_context_source_v1_{namespace_token}.json"
        )
        if metric_source_path.exists():
            return 0
    if previous_context_dir is not None and previous_context_dir.exists() and previous_context_dir.is_dir():
        previous_context_path = (
            previous_context_dir
            / f"n3_c1_n3t_previous_day_context_v1_{namespace_token}.json"
        )
        if previous_context_path.exists():
            return 1
    return 3


def _earliest_target_hhmm_first_sort_key(target_hhmm: str) -> int:
    text = str(target_hhmm or "").replace(":", "").strip()
    if re.fullmatch(r"[0-2][0-9][0-5][0-9]", text):
        return int(text)
    return 0


def _prevctx_to_metric_context_chunk_summary(
    *,
    total_candidate_count: int,
    selected_records: Sequence[Mapping[str, Any]],
    max_candidates: int,
) -> dict[str, Any]:
    selected_count = len(selected_records)
    remaining_count = max(0, int(total_candidate_count) - selected_count)
    return {
        "strategy": "prevctx_to_metric_context_priority_bounded_chunk_v1",
        "reason": (
            "prevctx_to_metric_context_chunk_incomplete"
            if remaining_count > 0
            else "prevctx_to_metric_context_chunk_ready"
        ),
        "max_candidates_per_invocation": int(max_candidates),
        "priority_candidate_count": int(total_candidate_count),
        "selected_candidate_count": selected_count,
        "processed_candidate_count": selected_count,
        "skipped_candidate_count": remaining_count,
        "remaining_candidate_count": remaining_count,
        "selected_source_runs": [
            {
                "source_run_hash": str(item.get("source_run_hash") or ""),
                "target_hhmm": str(item.get("target_hhmm") or ""),
                "component_status": str(item.get("component_status") or ""),
                "selection_reason": str(item.get("selection_reason") or ""),
            }
            for item in selected_records
        ],
    }


def _metric_context_priority_requires_builder(chunk_summary: Mapping[str, Any] | None) -> bool:
    selected = list((chunk_summary or {}).get("selected_source_runs") or [])
    if not selected:
        return False
    writer_ready_reasons = {
        "metric_context_exists",
        "stale_n3t_writer_done_metric_context_hash_mismatch",
    }
    return any(str(item.get("selection_reason") or "") not in writer_ready_reasons for item in selected)


def _n3t_writer_done_marker_path(*, output_dir: Path, planned_artifact: Mapping[str, Any]) -> Path:
    namespace_token = str(planned_artifact.get("namespace_token") or "").strip()
    if not namespace_token:
        for_trade_date = str(planned_artifact.get("for_trade_date") or "unknown_trade_date")
        target_hhmm = str(planned_artifact.get("target_hhmm") or "unknown_hhmm")
        source_run_hash = str(planned_artifact.get("source_run_hash") or "unknown_source")
        namespace_token = f"{for_trade_date}_{target_hhmm}_{source_run_hash}"
    return output_dir / "n3t_writer_done" / f"n3t_writer_done_marker_v1_{namespace_token}.json"


def _n3t_writer_done_marker_is_current(
    *,
    output_dir: Path,
    planned_artifact: Mapping[str, Any],
    metric_context_artifact: Mapping[str, Any],
) -> bool:
    marker_path = _n3t_writer_done_marker_path(output_dir=output_dir, planned_artifact=planned_artifact)
    marker = _read_optional_json_artifact(str(marker_path))
    if not marker["exists"]:
        return False
    payload = dict(marker.get("payload") or {})
    marker_sha = str(payload.get("metric_context_artifact_sha256") or "").strip()
    metric_context_sha = str(metric_context_artifact.get("sha256") or "").strip()
    if marker_sha and metric_context_sha and marker_sha != metric_context_sha:
        return False
    return True


def _write_n3t_writer_done_markers(
    *,
    output_dir: Path,
    n3t_writer_inputs: Sequence[Mapping[str, Any]],
    execute_result: Mapping[str, Any],
    observed_at: str,
) -> list[dict[str, Any]]:
    if not n3t_writer_inputs:
        return []
    if execute_result.get("adapter_type") != "n3t_action_confirmation_metric_writer_adapter_v1":
        return []
    if execute_result.get("write_executed") is not True and execute_result.get("db_write_executed") is not True:
        return []
    marker_records: list[dict[str, Any]] = []
    for item in n3t_writer_inputs:
        marker_path = _n3t_writer_done_marker_path(output_dir=output_dir, planned_artifact=item)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "artifact_type": "n3t_writer_done_marker_v1",
            "artifact_schema_version": "v1",
            "producer_layer": "N3_market_data",
            "for_trade_date": str(item.get("for_trade_date") or ""),
            "target_hhmm": str(item.get("target_hhmm") or ""),
            "source_run_hash": str(item.get("source_run_hash") or ""),
            "source_run_namespace": str(item.get("namespace_token") or ""),
            "n3t_metric_run_id": str(item.get("n3t_metric_run_id") or ""),
            "metric_context_artifact_path": str(item.get("metric_context_artifact_path") or ""),
            "metric_context_artifact_sha256": str(item.get("metric_context_artifact_sha256") or ""),
            "writer_adapter_type": str(execute_result.get("adapter_type") or ""),
            "write_executed": bool(execute_result.get("write_executed")),
            "db_write_executed": bool(execute_result.get("db_write_executed")),
            "observed_at": observed_at,
            "database_written": False,
            "writes_common_event_outbox": False,
            "writes_canonical_minute_bar_1m": False,
            "touches_n4_n5_n6_outbox": False,
            "full_market_fallback_used": False,
        }
        marker_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        marker_records.append(
            {
                "path": str(marker_path),
                "sha256": hashlib.sha256(marker_path.read_bytes()).hexdigest(),
                "target_hhmm": payload["target_hhmm"],
                "source_run_hash": payload["source_run_hash"],
                "artifact_type": payload["artifact_type"],
            }
        )
    return marker_records


def _find_previous_day_context_artifact(
    previous_context_dir: Path,
    *,
    target_hhmm: str,
    source_run_hash: str = "",
    namespace_token: str = "",
    staging_artifact: Mapping[str, Any] | None = None,
    exact_only: bool = False,
    canonical_path_only: bool = False,
) -> dict[str, Any] | None:
    if not previous_context_dir.exists() or not previous_context_dir.is_dir():
        return None
    if namespace_token:
        exact_path = previous_context_dir / f"n3_c1_n3t_previous_day_context_v1_{namespace_token}.json"
        if exact_path.exists():
            source = _read_optional_json_artifact(str(exact_path))
            payload = source.get("payload") or {}
            if payload.get("artifact_type") != "n3_c1_n3t_previous_day_context_v1":
                raise FastlaneShellBlocked("previous_day_context_artifact_contract_mismatch")
            payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
            payload_hash = str(payload.get("source_run_hash") or "")
            if payload_hhmm.replace(":", "") != target_hhmm:
                raise FastlaneShellBlocked("previous_day_context_artifact_target_mismatch")
            if source_run_hash and payload_hash and payload_hash != source_run_hash:
                raise FastlaneShellBlocked("previous_day_context_artifact_source_run_mismatch")
            if _previous_day_context_covers_staging(payload, staging_artifact):
                return source
            return None
        if canonical_path_only:
            return None
    if source_run_hash:
        for path in sorted(
            previous_context_dir.glob(f"n3_c1_n3t_previous_day_context_v1_*_{target_hhmm}_{source_run_hash}.json")
        ):
            source = _read_optional_json_artifact(str(path))
            payload = source.get("payload") or {}
            if payload.get("artifact_type") != "n3_c1_n3t_previous_day_context_v1":
                continue
            payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
            if payload_hhmm.replace(":", "") != target_hhmm:
                continue
            payload_hash = str(payload.get("source_run_hash") or "")
            if payload_hash and payload_hash != source_run_hash:
                continue
            if _previous_day_context_covers_staging(payload, staging_artifact):
                return source

    if exact_only:
        return None

    scoped_matches: list[dict[str, Any]] = []
    legacy_matches: list[dict[str, Any]] = []
    for path in sorted(previous_context_dir.glob("*.json")):
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != "n3_c1_n3t_previous_day_context_v1":
            continue
        payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
        if payload_hhmm.replace(":", "") != target_hhmm:
            continue
        payload_hash = str(payload.get("source_run_hash") or "")
        path_has_hash = bool(source_run_hash and source_run_hash in path.name)
        if source_run_hash and (payload_hash or path_has_hash):
            if payload_hash and payload_hash != source_run_hash:
                continue
            if not payload_hash and not path_has_hash:
                continue
            if not _previous_day_context_covers_staging(payload, staging_artifact):
                continue
            scoped_matches.append(source)
            continue
        if _previous_day_context_covers_staging(payload, staging_artifact):
            legacy_matches.append(source)
    if len(scoped_matches) > 1 or (not scoped_matches and len(legacy_matches) > 1):
        raise FastlaneShellBlocked("previous_day_context_artifact_ambiguous")
    if scoped_matches:
        return scoped_matches[0]
    return legacy_matches[0] if legacy_matches else None


def _previous_day_context_exact_candidate_exists(
    previous_context_dir: Path,
    *,
    target_hhmm: str,
    source_run_hash: str = "",
    namespace_token: str = "",
) -> bool:
    if not source_run_hash or not previous_context_dir.exists() or not previous_context_dir.is_dir():
        return False
    if namespace_token:
        return (
            previous_context_dir
            / f"n3_c1_n3t_previous_day_context_v1_{namespace_token}.json"
        ).exists()
    return any(
        previous_context_dir.glob(f"n3_c1_n3t_previous_day_context_v1_*_{target_hhmm}_{source_run_hash}.json")
    )


def _build_previous_day_context_artifact_index(previous_context_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return _build_hhmm_artifact_index(
        previous_context_dir,
        artifact_type="n3_c1_n3t_previous_day_context_v1",
    )


def _find_previous_day_context_artifact_from_index(
    index: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    target_hhmm: str,
    source_run_hash: str = "",
    staging_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    scoped_matches: list[dict[str, Any]] = []
    legacy_matches: list[dict[str, Any]] = []
    for source in index.get(_normal_hhmm_key(target_hhmm), []):
        payload = source.get("payload") or {}
        payload_hash = str(payload.get("source_run_hash") or "")
        path_has_hash = bool(source_run_hash and source_run_hash in str(source.get("path") or ""))
        if source_run_hash and (payload_hash or path_has_hash):
            if payload_hash and payload_hash != source_run_hash:
                continue
            if not payload_hash and not path_has_hash:
                continue
            if not _previous_day_context_covers_staging(payload, staging_artifact):
                continue
            scoped_matches.append(dict(source))
            continue
        if _previous_day_context_covers_staging(payload, staging_artifact):
            legacy_matches.append(dict(source))
    if len(scoped_matches) > 1 or (not scoped_matches and len(legacy_matches) > 1):
        raise FastlaneShellBlocked("previous_day_context_artifact_ambiguous")
    if scoped_matches:
        return scoped_matches[0]
    return legacy_matches[0] if legacy_matches else None


def _has_previous_day_context_artifact_for_hhmm_from_index(
    index: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    target_hhmm: str,
) -> bool:
    return bool(index.get(_normal_hhmm_key(target_hhmm)))


def _has_previous_day_context_artifact_for_hhmm(previous_context_dir: Path, *, target_hhmm: str) -> bool:
    if not previous_context_dir.exists() or not previous_context_dir.is_dir():
        return False
    scoped_paths = sorted(previous_context_dir.glob(f"n3_c1_n3t_previous_day_context_v1_*_{target_hhmm}_*.json"))
    paths = scoped_paths if scoped_paths else sorted(previous_context_dir.glob("*.json"))
    for path in paths:
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != "n3_c1_n3t_previous_day_context_v1":
            continue
        payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
        if payload_hhmm.replace(":", "") == target_hhmm:
            return True
    return False


def _build_hhmm_artifact_index(source_dir: Path, *, artifact_type: str) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    if not source_dir.exists() or not source_dir.is_dir():
        return index
    for path in sorted(source_dir.glob("*.json")):
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != artifact_type:
            continue
        hhmm_key = _normal_hhmm_key(str(payload.get("target_hhmm") or payload.get("target_minute_label") or ""))
        if not hhmm_key:
            continue
        index.setdefault(hhmm_key, []).append(source)
    return index


def _matching_hhmm_hash_artifacts_from_index(
    index: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    target_hhmm: str,
    source_run_hash: str = "",
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for source in index.get(_normal_hhmm_key(target_hhmm), []):
        payload = source.get("payload") or {}
        if source_run_hash:
            payload_hash = str(payload.get("source_run_hash") or "")
            path_has_hash = source_run_hash in str(source.get("path") or "")
            if payload_hash and payload_hash != source_run_hash:
                continue
            if not payload_hash and not path_has_hash:
                continue
        matches.append(dict(source))
    return matches


def _normal_hhmm_key(value: str) -> str:
    return str(value or "").replace(":", "").strip()


def _has_previous_day_context_artifact_for_source_run(
    previous_context_dir: Path,
    *,
    target_hhmm: str,
    source_run_hash: str,
) -> bool:
    if not previous_context_dir.exists() or not previous_context_dir.is_dir():
        return False
    for path in sorted(previous_context_dir.glob("*.json")):
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != "n3_c1_n3t_previous_day_context_v1":
            continue
        payload_hhmm = str(payload.get("target_hhmm") or payload.get("target_minute_label") or "")
        if payload_hhmm.replace(":", "") != target_hhmm:
            continue
        payload_hash = str(payload.get("source_run_hash") or "")
        if source_run_hash and payload_hash:
            if payload_hash == source_run_hash:
                return True
            continue
        if source_run_hash and source_run_hash in path.name:
            return True
        if not source_run_hash:
            return True
    return False


def _previous_day_context_covers_staging(
    previous_context: Mapping[str, Any],
    staging_artifact: Mapping[str, Any] | None,
) -> bool:
    staging = dict(staging_artifact or {})
    if not staging:
        return True
    for_trade_date = str(staging.get("for_trade_date") or previous_context.get("for_trade_date") or "")
    expected = _expected_previous_day_context_keys(staging, for_trade_date=for_trade_date)
    if not expected:
        return False
    available: dict[str, dict[tuple[str, str], set[str]]] = {}
    for row in previous_context.get("previous_day_minute_rows") or []:
        source = dict(row or {})
        asset_kind = str(source.get("asset_kind") or "")
        identity_key = str(source.get("identity_key") or "")
        physical_label = _hhmm_to_minute_label(source.get("physical_c1_label") or "")
        raw_label = str(source.get("raw_source_label") or "")
        if not raw_label and physical_label and for_trade_date:
            raw_label = _previous_day_context_raw_label(
                for_trade_date=for_trade_date,
                physical_label=physical_label,
            )
        if asset_kind not in {"stock", "index", "board"} or not identity_key or not physical_label or not raw_label:
            continue
        available.setdefault(asset_kind, {}).setdefault((identity_key, physical_label), set()).add(raw_label)
    for asset_kind, identity_to_labels in expected.items():
        available_identity_to_labels = available.get(asset_kind) or {}
        for key, raw_labels in identity_to_labels.items():
            if not set(raw_labels).issubset(available_identity_to_labels.get(key) or set()):
                return False
    return True


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


def _validate_previous_day_context_batch_provider_result(result: Mapping[str, Any]) -> None:
    if result.get("adapter_type") != "n3_c1_n3t_previous_day_context_batch_provider_adapter_v1":
        raise FastlaneShellBlocked("previous_day_context_batch_provider_adapter_type_mismatch")
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
            raise FastlaneShellBlocked(f"previous_day_context_batch_provider_{field}_forbidden")


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


def _load_previous_day_context_rows_for_object_cursor_batch(
    *,
    args: argparse.Namespace,
    staging_payloads: Sequence[Mapping[str, Any]],
    provider_name: str,
    dsn: str = "",
    connect_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    expected: dict[str, dict[tuple[str, str], set[str]]] = {}
    trade_dates: set[str] = set()
    for staging in staging_payloads:
        for_trade_date = str(staging.get("for_trade_date") or "")
        if not re.fullmatch(r"\d{8}", for_trade_date):
            raise FastlaneShellBlocked("object_cursor_batch_previous_day_trade_date_invalid")
        trade_dates.add(for_trade_date)
        candidate_expected = _expected_previous_day_context_keys(staging, for_trade_date=for_trade_date)
        for asset_kind, identity_to_labels in candidate_expected.items():
            for identity_and_physical, raw_labels in identity_to_labels.items():
                expected.setdefault(asset_kind, {}).setdefault(identity_and_physical, set()).update(raw_labels)
    if len(trade_dates) != 1:
        raise FastlaneShellBlocked("object_cursor_batch_previous_day_trade_date_mismatch")
    if not expected:
        raise FastlaneShellBlocked("object_cursor_batch_previous_day_expected_rows_empty")
    effective_dsn = str(dsn or os.environ.get("ASHARE_V3_POSTGRES_DSN") or "").strip()
    if not effective_dsn:
        raise FastlaneShellBlocked("previous_day_context_dsn_required")
    if connect_factory is None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:  # pragma: no cover - import environment issue
            raise FastlaneShellBlocked("previous_day_context_psycopg_required") from exc
        connection_manager = psycopg.connect(
            effective_dsn,
            row_factory=dict_row,
            options="-c default_transaction_read_only=on",
            connect_timeout=10,
        )
    else:
        connection_manager = connect_factory(effective_dsn)
    for_trade_date = next(iter(trade_dates))
    with connection_manager as connection:
        with connection.cursor() as cur:
            previous_trade_date = _fetch_previous_trade_date(cur, for_trade_date)
            rows, missing = _fetch_previous_day_context_rows_with_missing(
                cur,
                expected,
                for_trade_date,
                previous_trade_date,
            )
    return {
        "adapter_type": "n3_c1_n3t_previous_day_context_inline_batch_provider_adapter_v1",
        "provider_name": provider_name,
        "for_trade_date": for_trade_date,
        "previous_trade_date": previous_trade_date,
        "previous_day_minute_row_count": len(rows),
        "previous_day_minute_rows": rows,
        "missing_row_keys": [list(item) for item in missing],
        "missing_object_keys": [
            list(item)
            for item in sorted({(asset_kind, identity_key) for asset_kind, identity_key, _physical, _raw in missing})
        ],
        "database_connection_count": 1,
        "database_read": True,
        "database_written": False,
        "market_data_pulled": False,
        "writes_canonical_minute_bar_1m": False,
        "writes_n3_outbox": False,
        "writes_common_event_outbox": False,
        "touches_n4_n5_n6_outbox": False,
        "updates_n4_outbox": False,
        "scans_n5_db": False,
        "touches_n6": False,
        "full_market_fallback_used": False,
    }


def _build_previous_day_context_artifacts_batch_from_postgres(
    *,
    args: argparse.Namespace,
    planned_artifacts: Sequence[Mapping[str, Any]],
    previous_context_dir: Path,
    provider_name: str,
    dsn: str = "",
    connect_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    candidates = [
        dict(planned)
        for planned in planned_artifacts
        if str(planned.get("target_hhmm") or "")
    ]
    result: dict[str, Any] = {
        "adapter_type": "n3_c1_n3t_previous_day_context_batch_provider_adapter_v1",
        "provider_name": provider_name,
        "artifact_written": False,
        "artifact_count": 0,
        "previous_day_context_provider_results": [],
        "candidate_blockers": [],
        "database_read": False,
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
    if not candidates:
        return result

    effective_dsn = str(dsn or os.environ.get("ASHARE_V3_POSTGRES_DSN") or "").strip()
    if not effective_dsn:
        result["candidate_blockers"] = [
            _metric_context_candidate_record(planned, reason="previous_day_context_dsn_required")
            for planned in candidates
        ]
        return result

    try:
        if connect_factory is None:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except Exception as exc:  # pragma: no cover - import environment issue
                raise FastlaneShellBlocked("previous_day_context_psycopg_required") from exc
            connection_manager = psycopg.connect(
                effective_dsn,
                row_factory=dict_row,
                options="-c default_transaction_read_only=on",
                connect_timeout=10,
            )
        else:
            connection_manager = connect_factory(effective_dsn)
        with connection_manager as connection:
            for planned in candidates:
                try:
                    provider_result = _build_previous_day_context_artifact_from_postgres(
                        args=args,
                        planned_artifact=planned,
                        target_hhmm=str(planned.get("target_hhmm") or ""),
                        previous_context_dir=previous_context_dir,
                        provider_name=provider_name,
                        connection=connection,
                    )
                    _validate_previous_day_context_provider_result(provider_result)
                    result["previous_day_context_provider_results"].append(provider_result)
                    result["artifact_count"] += int(provider_result.get("artifact_count") or 0)
                    result["artifact_written"] = result["artifact_count"] > 0
                except FastlaneShellBlocked as exc:
                    result["candidate_blockers"].append(
                        _metric_context_candidate_record(planned, reason=str(exc))
                    )
    except FastlaneShellBlocked as exc:
        result["candidate_blockers"] = [
            _metric_context_candidate_record(planned, reason=str(exc)) for planned in candidates
        ]
    result["database_read"] = bool(result["previous_day_context_provider_results"])
    return result


def _build_previous_day_context_artifact_from_postgres(
    *,
    args: argparse.Namespace,
    planned_artifact: Mapping[str, Any],
    target_hhmm: str,
    previous_context_dir: Path,
    provider_name: str,
    connection: Any | None = None,
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

    def fetch_rows(conn: Any) -> tuple[str, list[dict[str, Any]]]:
        with conn.cursor() as cur:
            previous_trade_date = _fetch_previous_trade_date(cur, for_trade_date)
            rows = _fetch_previous_day_context_rows(cur, expected, for_trade_date, previous_trade_date)
        return previous_trade_date, rows

    if connection is None:
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
        ) as owned_connection:
            previous_trade_date, rows = fetch_rows(owned_connection)
    else:
        previous_trade_date, rows = fetch_rows(connection)

    source_run_hash = str(planned_artifact.get("source_run_hash") or "")
    namespace_token = str(planned_artifact.get("namespace_token") or "")
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
        "source_run_hash": source_run_hash,
        "source_run_namespace": namespace_token,
        "scope_count": int(scope_payload.get("scope_count") or 0),
        "previous_day_minute_row_count": len(rows),
        "previous_day_minute_rows": rows,
        "source_active_scope_artifact_path": str(active_scope.get("path") or ""),
        "source_active_scope_artifact_hash": str(active_scope.get("sha256") or ""),
        "source_staging_artifact_path": str(staging.get("path") or ""),
        "source_staging_artifact_hash": str(staging.get("sha256") or ""),
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
    token = f"{for_trade_date}_{target_hhmm}_{source_run_hash}" if source_run_hash else f"{for_trade_date}_{target_hhmm}"
    path = previous_context_dir / f"n3_c1_n3t_previous_day_context_v1_{token}.json"
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
                "source_run_hash": source_run_hash,
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
    labels = _canonical_ashare_1m_labels_cached(for_trade_date) if re.fullmatch(r"\d{8}", for_trade_date or "") else ()
    labels_by_identity: dict[tuple[str, str], set[str]] = {}
    for row in staging_artifact.get("closed_minute_rows") or []:
        source = dict(row or {})
        if source.get("fake_or_synthetic_row") is True:
            raise FastlaneShellBlocked("previous_day_context_fake_row_forbidden")
        asset_kind = str(source.get("asset_kind") or "")
        identity_key = str(source.get("identity_key") or "")
        physical_label = _hhmm_to_minute_label(source.get("physical_c1_label") or "")
        if asset_kind not in {"stock", "index", "board"} or not identity_key.startswith(f"{asset_kind}:"):
            raise FastlaneShellBlocked("previous_day_context_staging_scope_mismatch")
        if physical_label not in labels:
            raise FastlaneShellBlocked("previous_day_context_staging_label_mismatch")
        labels_by_identity.setdefault((asset_kind, identity_key), set()).add(physical_label)

    for (asset_kind, identity_key), current_labels in sorted(labels_by_identity.items()):
        required_labels = _required_previous_day_metric_context_labels(
            labels=labels,
            current_labels=current_labels,
        )
        for physical_label in sorted(required_labels, key=lambda value: labels.index(value)):
            if physical_label == "09:30":
                continue
            raw_label = _previous_day_context_raw_label(
                for_trade_date=for_trade_date,
                physical_label=physical_label,
            )
            if not raw_label:
                continue
            expected.setdefault(asset_kind, {}).setdefault((identity_key, physical_label), set()).add(raw_label)
    return expected


def _required_previous_day_metric_context_labels(
    *,
    labels: Sequence[str],
    current_labels: set[str],
) -> set[str]:
    if not labels or not current_labels:
        return set()
    latest_label = max(current_labels, key=lambda value: labels.index(value))
    position = labels.index(latest_label) + 1
    open_boundary_gap = "09:30" not in current_labels and "09:31" in current_labels
    required: set[str] = set()

    for size in (1, 5, 30, 120):
        current_start = ((position - 1) // size) * size
        if current_start == 0:
            required.update(labels[-size:])
            continue
        if (
            current_start == 1
            and size == 1
            and labels[:2] == ["09:30", "09:31"]
            and open_boundary_gap
        ):
            required.update(labels[-size:])

    for size in (5, 30):
        current_start = ((position - 1) // size) * size
        same_window_labels = list(labels[current_start : current_start + size])
        if (
            same_window_labels[:1] == ["09:30"]
            and "09:31" in same_window_labels
            and open_boundary_gap
        ):
            same_window_labels = [label for label in same_window_labels if label != "09:30"]
        required.update(same_window_labels)
    return required


def _previous_day_context_raw_label(*, for_trade_date: str, physical_label: str) -> str:
    preload_label = _previous_day_preload_close_label_for_physical_label(physical_label)
    if preload_label:
        return preload_label
    try:
        mapped = source_close_label_for_physical_start_label(for_trade_date, physical_label)
    except Exception as exc:  # noqa: BLE001 - converted to a contract blocker upstream.
        raise FastlaneShellBlocked("previous_day_context_source_label_not_mappable") from exc
    if mapped.get("status") != "mapped":
        return ""
    return str(mapped.get("raw_source_label") or "")


def _previous_day_preload_close_label_for_physical_label(physical_label: str) -> str:
    label = _hhmm_to_minute_label(physical_label)
    if not label:
        return ""
    if label == "11:29":
        return "11:30"
    if "13:00" <= label <= "14:59":
        hour_text, minute_text = label.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text) + 1
        if minute >= 60:
            hour += 1
            minute = 0
        return f"{hour:02d}:{minute:02d}"
    return ""


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
    output, missing = _fetch_previous_day_context_rows_with_missing(
        cur,
        expected,
        for_trade_date,
        previous_trade_date,
    )
    if missing:
        raise FastlaneShellBlocked("previous_day_context_rows_missing")
    return output


def _fetch_previous_day_context_rows_with_missing(
    cur: Any,
    expected: Mapping[str, Mapping[tuple[str, str], set[str]]],
    for_trade_date: str,
    previous_trade_date: str,
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str, str]]]:
    table_by_asset = {
        "stock": ("stock_minute_bar_1m", "stock_identity_key"),
        "index": ("index_minute_bar_1m", "index_identity_key"),
        "board": ("board_minute_bar_1m", "board_identity_key"),
    }
    output: list[dict[str, Any]] = []
    missing: list[tuple[str, str, str, str]] = []
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
                    missing.append((asset_kind, identity_key, physical_label, raw_label))
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
    output.sort(key=lambda row: (row["asset_kind"], row["identity_key"], row["physical_c1_label"]))
    return output, missing


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
    required_raw_labels = {_hhmm_to_minute_label(label) for label in plan_row.get("required_raw_source_labels") or []}
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
        raw_label = _provider_row_raw_hhmm_label(provider_row)
        if raw_label in FORBIDDEN_SOURCE_CLOSE_LABELS:
            mapped = source_close_label_to_physical_start_label(for_trade_date, raw_label)
            if mapped.get("status") != "mapped" or mapped.get("physical_c1_label") not in required_labels:
                continue
        normalized = _normalize_provider_current_day_row(provider_row, for_trade_date=for_trade_date)
        physical_label = _hhmm_to_minute_label(normalized.get("physical_c1_label") or "")
        if physical_label not in required_labels:
            continue
        normalized_raw_label = _hhmm_to_minute_label(
            normalized.get("raw_source_label") or ""
        )
        if (
            physical_label == POST_CLOSE_FINAL_A_PHYSICAL_MINUTE_LABEL
            and "15:00" in required_raw_labels
            and normalized_raw_label != "15:00"
        ):
            continue
        output = {
            **scope,
            "physical_c1_label": physical_label,
            "raw_source_label": normalized_raw_label,
            "source_label_policy": normalized.get("source_label_policy") or SOURCE_CLOSE_LABEL_POLICY,
            "source_label_semantics": normalized.get("source_label_semantics") or "source_label",
            "physical_label_semantics": normalized.get("physical_label_semantics") or "physical_label",
            "fake_or_synthetic_row": bool(normalized.get("fake_or_synthetic_row")),
            "source_provider": provider_name,
            "source_row_ref": normalized.get("source_row_ref")
            or f"{provider_name}:{scope['identity_key']}:{physical_label}:{index}",
        }
        for key in ("open", "high", "low", "close", "volume", "amount"):
            if key in normalized:
                output[key] = normalized.get(key)
        rows.append(output)
    return _dedupe_current_day_provider_morning_close_rows(rows)


def _dedupe_current_day_provider_morning_close_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    lunch_boundary_keys = {
        _provider_morning_close_dedupe_key(row)
        for row in rows
        if _hhmm_to_minute_label(row.get("physical_c1_label") or "") == "13:00"
        and _hhmm_to_minute_label(row.get("raw_source_label") or "") in {"11:30", "13:00"}
    }
    final_close_keys = {
        _provider_morning_close_dedupe_key(row)
        for row in rows
        if _hhmm_to_minute_label(row.get("physical_c1_label") or "") == "14:59"
        and _hhmm_to_minute_label(row.get("raw_source_label") or "") in {"14:59", "15:00"}
    }
    if not lunch_boundary_keys and not final_close_keys:
        return [dict(row) for row in rows]
    deduped: list[dict[str, Any]] = []
    for row in rows:
        row_raw_label = _hhmm_to_minute_label(row.get("raw_source_label") or "")
        row_dedupe_key = _provider_morning_close_dedupe_key(row)
        has_raw_1300 = any(
            _hhmm_to_minute_label(candidate.get("physical_c1_label") or "") == "13:00"
            and _hhmm_to_minute_label(candidate.get("raw_source_label") or "") == "13:00"
            and _provider_morning_close_dedupe_key(candidate) == row_dedupe_key
            for candidate in rows
        )
        has_raw_1500 = any(
            _hhmm_to_minute_label(candidate.get("physical_c1_label") or "") == "14:59"
            and _hhmm_to_minute_label(candidate.get("raw_source_label") or "") == "15:00"
            and _provider_morning_close_dedupe_key(candidate) == row_dedupe_key
            for candidate in rows
        )
        if (
            _hhmm_to_minute_label(row.get("physical_c1_label") or "") == "13:00"
            and row_raw_label == "11:30"
            and row_dedupe_key in lunch_boundary_keys
            and has_raw_1300
        ):
            continue
        if (
            _hhmm_to_minute_label(row.get("physical_c1_label") or "") == "14:59"
            and row_raw_label == "14:59"
            and row_dedupe_key in final_close_keys
            and has_raw_1500
        ):
            continue
        deduped.append(dict(row))
    return deduped


def _provider_morning_close_dedupe_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row.get(field) or "")
        for field in (
            "for_trade_date",
            "asset_kind",
            "identity_key",
            "direction",
            "signal_type",
            "condition_key",
            "source_trigger_event_id",
            "source_trigger_run_id",
            "physical_c1_label",
        )
    )


def _provider_row_raw_hhmm_label(row: Mapping[str, Any]) -> str:
    for key in ("raw_source_label", "bar_time", "datetime", "timestamp", "time"):
        value = row.get(key)
        if value is None:
            continue
        text = str(value)
        if re.fullmatch(r"[0-2][0-9][0-5][0-9]", text):
            return _hhmm_to_minute_label(text)
        match = re.search(r"([0-2][0-9]):([0-5][0-9])", text)
        if match:
            return f"{match.group(1)}:{match.group(2)}"
    return ""


def _normalize_provider_current_day_row(row: Mapping[str, Any], *, for_trade_date: str) -> dict[str, Any]:
    source = dict(row or {})
    if source.get("physical_c1_label") and source.get("raw_source_label"):
        physical_label = _hhmm_to_minute_label(source.get("physical_c1_label"))
        raw_label = _hhmm_to_minute_label(source.get("raw_source_label"))
        mapped = source_close_label_to_physical_start_label(for_trade_date, raw_label)
        if mapped.get("status") != "mapped":
            raise FastlaneShellBlocked("current_day_source_provider_row_label_mismatch")
        mapped_physical_label = _hhmm_to_minute_label(mapped.get("physical_c1_label") or "")
        if mapped_physical_label != physical_label:
            if raw_label != physical_label:
                raise FastlaneShellBlocked("current_day_source_provider_row_label_mismatch")
            physical_label = mapped_physical_label
        source.update(
            {
                "physical_c1_label": physical_label,
                "raw_source_label": raw_label,
                "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
                "source_label_semantics": mapped.get("source_label_semantics") or "source_label",
                "physical_label_semantics": mapped.get("physical_label_semantics") or "physical_label",
            }
        )
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
    conflict_sql = _n3t_writer_conflict_clause(columns)
    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for table, rows in rows_by_table.items():
                if table not in allowed_tables:
                    raise FastlaneShellBlocked("n3t_writer_target_table_forbidden")
                sql = (
                    f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
                    f"{conflict_sql}"
                )
                values_batch = [
                    [
                        Jsonb(row.get(column)) if column in json_columns else row.get(column)
                        for column in columns
                    ]
                    for row in rows
                ]
                if values_batch:
                    cur.executemany(sql, values_batch)
                    inserted_rows += len(values_batch)
    result = {
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
    result.update(_n3t_writer_latency_summary(n3t_writer_inputs))
    return result


def _n3t_writer_latency_summary(
    n3t_writer_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, int | None]:
    values: dict[str, list[int]] = {
        "minute_closed_to_source_ms": [],
        "source_to_staging_ms": [],
        "staging_to_proof_ms": [],
    }
    for item in n3t_writer_inputs:
        source = _n3t_writer_metric_context_source(item)
        payload = source.get("payload") or {}
        for field in values:
            try:
                value = int(payload.get(field))
            except (TypeError, ValueError):
                continue
            if value >= 0:
                values[field].append(value)
    return {
        **{
            field: (max(field_values) if field_values else None)
            for field, field_values in values.items()
        },
        "proof_to_action_ms": None,
    }


def _n3t_writer_conflict_clause(columns: Sequence[str]) -> str:
    conflict_columns = (
        "projection_run_id",
        "identity_key",
        "trade_date",
        "metric_minute_label",
        "projection_schema_version",
    )
    conflict_sql = ", ".join(conflict_columns)
    update_columns = [str(column) for column in columns if str(column) not in set(conflict_columns)]
    update_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
    return f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"


def _n3t_writer_metric_context_source(item: Mapping[str, Any]) -> dict[str, Any]:
    metric_context_path = str(item.get("metric_context_artifact_path") or "")
    inline_payload = item.get("metric_context_payload")
    if isinstance(inline_payload, Mapping):
        payload = dict(inline_payload)
        expected_sha256 = str(item.get("metric_context_artifact_sha256") or "")
        actual_sha256 = _json_payload_sha256(payload)
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise FastlaneShellBlocked("n3t_writer_inline_metric_context_sha256_mismatch")
        return {
            "exists": True,
            "path": metric_context_path or "inline://object_cursor_batch/metric_context",
            "payload": payload,
            "sha256": actual_sha256,
            "inline": True,
        }
    return _read_optional_json_artifact(metric_context_path)


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
        source = _n3t_writer_metric_context_source(item)
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
                    "object_minute_scope": bool(metric.get("object_minute_scope")),
                    "object_minute_ref_count": int(metric.get("object_minute_ref_count") or 0),
                    "object_minute_ref_trace": list(metric.get("object_minute_ref_trace") or []),
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
    args.for_trade_date = str(config.get("for_trade_date") or "")
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
    metric_context_source_artifact_dir = str(
        getattr(args, "metric_context_source_artifact_dir", "")
        or config.get("n3_c1_n3t_metric_context_source_artifact_dir")
        or ""
    )
    if not metric_context_source_artifact_dir and str(args.output_dir or "").strip():
        metric_context_source_artifact_dir = str(Path(str(args.output_dir)) / "metric_context_source")
    args.metric_context_source_artifact_dir = metric_context_source_artifact_dir
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
    if int(getattr(args, "post_close_final_a_pass_max_candidates_per_invocation", 0) or 0) <= 0:
        args.post_close_final_a_pass_max_candidates_per_invocation = int(
            config.get("n3_c1_n3t_post_close_final_a_pass_max_candidates_per_invocation")
            or config.get("post_close_final_a_pass_max_candidates_per_invocation")
            or DEFAULT_POST_CLOSE_FINAL_A_PASS_MAX_CANDIDATES
        )
    if int(getattr(args, "current_day_source_provider_max_candidates_per_invocation", 0) or 0) <= 0:
        args.current_day_source_provider_max_candidates_per_invocation = int(
            config.get("n3_c1_n3t_current_day_source_provider_max_candidates_per_invocation")
            or config.get("current_day_source_provider_max_candidates_per_invocation")
            or DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_MAX_CANDIDATES
        )
    if int(getattr(args, "current_day_source_provider_concurrency", 0) or 0) <= 0:
        args.current_day_source_provider_concurrency = int(
            config.get("n3_c1_n3t_current_day_source_provider_concurrency")
            or config.get("current_day_source_provider_concurrency")
            or DEFAULT_CURRENT_DAY_SOURCE_PROVIDER_CONCURRENCY
        )
    if int(getattr(args, "scoped_pull_plan_max_candidates_per_invocation", 0) or 0) <= 0:
        args.scoped_pull_plan_max_candidates_per_invocation = int(
            config.get("n3_c1_n3t_scoped_pull_plan_max_candidates_per_invocation")
            or config.get("scoped_pull_plan_max_candidates_per_invocation")
            or DEFAULT_SCOPED_PULL_PLAN_MAX_CANDIDATES
        )
    if int(getattr(args, "existing_source_staging_max_candidates_per_invocation", 0) or 0) <= 0:
        args.existing_source_staging_max_candidates_per_invocation = int(
            config.get("n3_c1_n3t_existing_source_staging_max_candidates_per_invocation")
            or config.get("existing_source_staging_max_candidates_per_invocation")
            or DEFAULT_EXISTING_SOURCE_STAGING_MAX_CANDIDATES
        )
    if int(getattr(args, "existing_staging_metric_context_max_candidates_per_invocation", 0) or 0) <= 0:
        args.existing_staging_metric_context_max_candidates_per_invocation = int(
            config.get("n3_c1_n3t_existing_staging_metric_context_max_candidates_per_invocation")
            or config.get("existing_staging_metric_context_max_candidates_per_invocation")
            or DEFAULT_EXISTING_STAGING_METRIC_CONTEXT_MAX_CANDIDATES
        )
    _apply_fastlane_worker_phase_gate(args, config)


def _discover_requested_active_scope_artifacts(args: argparse.Namespace, *, fanout: bool = True) -> list[dict[str, Any]]:
    path_text = str(getattr(args, "active_scope_artifact_path", "") or "").strip()
    if path_text:
        return _discover_single_active_scope_artifact(Path(path_text), fanout=fanout)
    if bool(getattr(args, "scheduler_quiet", False)):
        latest_path = _latest_active_scope_artifact_path(Path(args.active_scope_artifact_dir))
        if latest_path is None:
            return []
        return _discover_single_active_scope_artifact(latest_path, fanout=fanout)
    return _discover_active_scope_artifacts(Path(args.active_scope_artifact_dir), fanout=fanout)


def _latest_active_scope_artifact_path(path: Path) -> Path | None:
    if not path.exists():
        return None
    if not path.is_dir():
        raise FastlaneShellBlocked("active_scope_artifact_dir_must_be_directory")
    candidates = [item for item in path.glob(f"{INPUT_ARTIFACT_TYPE}*.json") if item.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.stat().st_mtime_ns, item.name))


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
        for_trade_date_is_current_date=bool(
            session_context.get("for_trade_date_is_current_date", classification.get("current_date_matches_for_trade_date"))
        ),
        trade_calendar_is_open=bool(session_context.get("trade_calendar_is_open")),
        post_close_final_a_pass_available=bool(
            session_context.get("post_close_final_a_pass_available", classification["phase"] == "post_close")
        ),
        post_close_final_a_pass_done=bool(session_context.get("post_close_final_a_pass_done")),
    )
    args.fastlane_session_phase = classification["phase"]
    args.fastlane_active_worker_decision = decision
    args.fastlane_current_exchange_time = str(session_context.get("current_exchange_time") or "")
    if not decision["writes_enabled_allowed"]:
        raise FastlaneShellBlocked(str(decision.get("blocked_reason") or decision.get("worker_mode") or "write_not_allowed"))


def _discover_active_scope_artifacts(path: Path, *, fanout: bool = True) -> list[dict[str, Any]]:
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
        if fanout:
            artifacts.extend(_active_scope_artifact_candidates(artifact_path, payload))
        else:
            artifacts.append(_active_scope_artifact_base_candidate(artifact_path, payload))
    return artifacts


def _discover_single_active_scope_artifact(path: Path, *, fanout: bool = True) -> list[dict[str, Any]]:
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
    if not fanout:
        return [_active_scope_artifact_base_candidate(path, payload)]
    return _active_scope_artifact_candidates(path, payload)


def _active_scope_artifact_base_candidate(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "artifact_type": INPUT_ARTIFACT_TYPE,
        "for_trade_date": str(payload.get("for_trade_date") or ""),
        "scope_count": int(payload.get("scope_count") or 0),
        "source_trigger_run_id": str(payload.get("source_trigger_run_id") or ""),
        "action_run_id": str(payload.get("action_run_id") or ""),
        "target_hhmm": _target_hhmm_from_value(payload.get("target_hhmm") or payload.get("target_minute_label")),
        "source_run_hash": str(payload.get("source_run_hash") or ""),
        "source_run_namespace": str(payload.get("source_run_namespace") or ""),
        "full_market_fallback_allowed": bool(payload.get("full_market_fallback_allowed")),
        "n3_scans_n5_internals": bool(payload.get("n3_scans_n5_internals")),
        "object_scope_ref_fanout": bool(payload.get("object_scope_ref_fanout")),
    }


def _active_scope_artifact_candidates(path: Path, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    base = _active_scope_artifact_base_candidate(path, payload)
    if _active_scope_candidate_has_target(base):
        return [base]
    object_ref_candidates = _object_scope_ref_fanout_candidates(base, payload)
    return object_ref_candidates or [base]


def _active_scope_candidate_has_target(candidate: Mapping[str, Any]) -> bool:
    context = _infer_scope_context(candidate)
    return bool(re.fullmatch(r"[0-2][0-9][0-5][0-9]", context["target_hhmm"]))


def _object_scope_ref_fanout_candidates(
    base: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = list(payload.get("scope_rows") or [])
    if not rows:
        return []
    candidates: list[dict[str, Any]] = []
    buckets: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        object_row = dict(row or {})
        for ref_source in object_row.get("active_tracking_refs") or []:
            ref = dict(ref_source or {})
            target_hhmm = _target_hhmm_from_active_ref(ref)
            if not target_hhmm:
                continue
            key = (
                str(ref.get("for_trade_date") or object_row.get("for_trade_date") or base.get("for_trade_date") or ""),
                str(ref.get("asset_kind") or object_row.get("asset_kind") or ""),
                str(ref.get("identity_key") or object_row.get("identity_key") or ""),
                str(ref.get("direction") or ""),
                target_hhmm,
            )
            bucket = buckets.setdefault(
                key,
                {
                    "object_row": object_row,
                    "target_hhmm": target_hhmm,
                    "refs": [],
                },
            )
            bucket["refs"].append(ref)
    for sequence, bucket in enumerate(buckets.values()):
        refs = sorted(
            (dict(ref) for ref in bucket["refs"]),
            key=lambda ref: (
                _hint_condition_priority(ref.get("condition_key")),
                str(ref.get("source_trigger_event_time") or ref.get("trigger_time") or ref.get("latest_n4_event_time") or ""),
                str(ref.get("condition_key") or ""),
                str(ref.get("state_key") or ""),
            ),
        )
        if not refs:
            continue
        target_hhmm = str(bucket["target_hhmm"] or "")
        for_trade_date = str(base.get("for_trade_date") or payload.get("for_trade_date") or refs[0].get("for_trade_date") or "")
        source_run_hash = _object_minute_source_run_hash(
            object_row=bucket["object_row"],
            active_refs=refs,
            target_hhmm=target_hhmm,
        )
        source_trigger_run_id = _joined_source_trigger_run_ids(refs) or str(base.get("source_trigger_run_id") or "")
        source_run_namespace = f"{for_trade_date}_{target_hhmm}_{source_run_hash}"
        candidate = dict(base)
        narrowed_payload = _object_scope_ref_fanout_payload(
            payload=payload,
            object_row=bucket["object_row"],
            active_refs=refs,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
            source_run_namespace=source_run_namespace,
            source_trigger_run_id=source_trigger_run_id,
        )
        candidate.update(
            {
                "target_hhmm": target_hhmm,
                "source_trigger_run_id": source_trigger_run_id,
                "source_run_hash": source_run_hash,
                "source_run_namespace": source_run_namespace,
                "scope_count": 1,
                "active_tracking_ref_count": len(refs),
                "object_scope_ref_fanout": True,
                "_object_scope_ref_fanout_payload": narrowed_payload,
                "source_trigger_event_id": _joined_source_trigger_event_ids(refs),
                "source_trigger_event_type": _joined_source_trigger_event_types(refs),
                "source_trigger_event_time": str(
                    refs[0].get("source_trigger_event_time") or refs[0].get("latest_n4_event_time") or ""
                ),
                "sort_sequence": sequence,
            }
        )
        candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda item: (
            str(item.get("target_hhmm") or ""),
            str(item.get("source_run_hash") or ""),
            str(item.get("source_trigger_event_id") or ""),
        ),
    )


def _object_scope_ref_fanout_payload(
    *,
    payload: Mapping[str, Any],
    object_row: Mapping[str, Any],
    active_refs: Sequence[Mapping[str, Any]],
    target_hhmm: str,
    source_run_hash: str,
    source_run_namespace: str,
    source_trigger_run_id: str,
) -> dict[str, Any]:
    refs = [_compact_object_scope_ref(ref) for ref in active_refs]
    ref = refs[0] if refs else {}
    row = {
        "for_trade_date": str(
            ref.get("for_trade_date")
            or object_row.get("for_trade_date")
            or payload.get("for_trade_date")
            or ""
        ),
        "asset_kind": str(ref.get("asset_kind") or object_row.get("asset_kind") or ""),
        "identity_key": str(ref.get("identity_key") or object_row.get("identity_key") or ""),
        "scope_status": str(ref.get("scope_status") or object_row.get("scope_status") or "active"),
        "active_tracking_refs": refs,
        "attention_event_refs": [],
    }
    return {
        "artifact_type": INPUT_ARTIFACT_TYPE,
        "artifact_schema_version": str(payload.get("artifact_schema_version") or "v1"),
        "producer_layer": str(payload.get("producer_layer") or "N5_action"),
        "for_trade_date": row["for_trade_date"],
        "scope_granularity": "object",
        "scope_status": "active",
        "scope_count": 1,
        "active_tracking_ref_count": len(refs),
        "scope_rows": [row],
        "target_hhmm": target_hhmm,
        "target_minute_label": _hhmm_to_minute_label(target_hhmm),
        "source_run_hash": source_run_hash,
        "source_run_namespace": source_run_namespace,
        "source_trigger_run_id": source_trigger_run_id,
        "source_trigger_event_id": _joined_source_trigger_event_ids(refs),
        "source_trigger_event_type": _joined_source_trigger_event_types(refs),
        "source_trigger_event_time": str(
            ref.get("source_trigger_event_time") or ref.get("latest_n4_event_time") or ""
        ),
        "object_scope_ref_fanout": True,
        "object_minute_scope": True,
        "object_minute_ref_dedupe_policy": "for_trade_date_asset_identity_direction_target_minute_v1",
        "fanout_payload_policy": OBJECT_SCOPE_REF_FANOUT_PAYLOAD_POLICY,
        "full_market_fallback_allowed": False,
        "n3_scans_n5_internals": False,
        "db_write_allowed": False,
        "n4_outbox_status_update_allowed": False,
        "updates_n4_outbox": False,
    }


def _compact_object_scope_ref(ref_source: Mapping[str, Any]) -> dict[str, Any]:
    ref = dict(ref_source or {})
    compact = {field: ref.get(field) for field in OBJECT_SCOPE_REF_FANOUT_REF_FIELDS if field in ref}
    for field in OBJECT_SCOPE_REF_FANOUT_HASHED_TRACE_FIELDS:
        if field not in ref:
            continue
        compact[f"{field}_sha256"] = _canonical_json_value_sha256(ref.get(field))
    return compact


def _canonical_json_value_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _object_minute_source_run_hash(
    *,
    object_row: Mapping[str, Any],
    active_refs: Sequence[Mapping[str, Any]],
    target_hhmm: str,
) -> str:
    ref_parts = [
        "|".join(
            str(ref.get(key) or "")
            for key in (
                "source_run_hash",
                "state_key",
                "condition_key",
                "source_trigger_event_id",
                "source_trigger_event_time",
                "latest_n4_event_time",
                "next_unchecked_minute_label",
            )
        )
        for ref in active_refs
    ]
    return _short_scope_hash(
        str(object_row.get("for_trade_date") or ""),
        str(object_row.get("asset_kind") or ""),
        str(object_row.get("identity_key") or ""),
        str(active_refs[0].get("direction") if active_refs else ""),
        str(target_hhmm or ""),
        *sorted(ref_parts),
    )


def _joined_source_trigger_run_ids(active_refs: Sequence[Mapping[str, Any]]) -> str:
    values = sorted({str(ref.get("source_trigger_run_id") or "") for ref in active_refs if ref.get("source_trigger_run_id")})
    return ",".join(values)


def _joined_source_trigger_event_ids(active_refs: Sequence[Mapping[str, Any]]) -> str:
    values = sorted({str(ref.get("source_trigger_event_id") or "") for ref in active_refs if ref.get("source_trigger_event_id")})
    return ",".join(values)


def _joined_source_trigger_event_types(active_refs: Sequence[Mapping[str, Any]]) -> str:
    values = sorted({str(ref.get("source_trigger_event_type") or "") for ref in active_refs if ref.get("source_trigger_event_type")})
    return ",".join(values)


def _hint_condition_priority(condition_key: Any) -> int:
    text = str(condition_key or "").upper()
    return 1 if text.startswith("BUY_HINT") or text.startswith("SELL_HINT") else 0


def _materialize_object_scope_ref_fanout_active_scope_artifacts(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    materialized: list[dict[str, Any]] = []
    fanout_dir = output_dir / "active_scope_ref_fanout"
    fanout_dir.mkdir(parents=True, exist_ok=True)
    for artifact in active_scope_artifacts:
        item = dict(artifact)
        payload = item.pop("_object_scope_ref_fanout_payload", None)
        if not isinstance(payload, Mapping):
            materialized.append(item)
            continue
        namespace_token = _infer_scope_context(item)["namespace_token"]
        path = fanout_dir / f"n5_active_scope_snapshot_v1_{namespace_token}_ref_fanout.json"
        compact_payload = dict(payload)
        compact_payload["source_object_scope_artifact_path"] = str(artifact.get("path") or "")
        materialization_status = _write_compact_json_artifact_atomic_if_stale(path, compact_payload)
        item["path"] = str(path)
        item["source_object_scope_artifact_path"] = str(artifact.get("path") or "")
        item["fanout_materialization_status"] = materialization_status
        materialized.append(item)
    return materialized


def _write_compact_json_artifact_atomic_if_stale(path: Path, payload: Mapping[str, Any]) -> str:
    existed = path.exists()
    if existed and _compact_fanout_artifact_is_current(path):
        return "reused"
    encoded = (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(encoded, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return "compacted" if existed else "written"


def _compact_fanout_artifact_is_current(path: Path) -> bool:
    marker = (
        f'"fanout_payload_policy":"{OBJECT_SCOPE_REF_FANOUT_PAYLOAD_POLICY}"'
    ).encode("utf-8")
    try:
        with path.open("rb") as handle:
            return marker in handle.read(4096)
    except OSError:
        return False


def _active_scope_artifacts_with_persisted_ref_fanout(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        merged[context["namespace_token"]] = dict(artifact)

    fanout_dir = output_dir / "active_scope_ref_fanout"
    if not fanout_dir.exists() or not fanout_dir.is_dir():
        return list(merged.values())

    for path in sorted(fanout_dir.glob("n5_active_scope_snapshot_v1_*_ref_fanout.json")):
        source = _read_optional_json_artifact(str(path))
        payload = source.get("payload") or {}
        if payload.get("artifact_type") != INPUT_ARTIFACT_TYPE:
            continue
        for candidate in _active_scope_artifact_candidates(path, payload):
            if candidate.get("object_scope_ref_fanout") is not True:
                continue
            context = _infer_scope_context(candidate)
            merged.setdefault(context["namespace_token"], dict(candidate))
    return list(merged.values())


def _dedupe_active_scope_artifacts_by_namespace(
    active_scope_artifacts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        merged.setdefault(context["namespace_token"], dict(artifact))
    return list(merged.values())


def _active_scope_artifact_trade_date(artifact: Mapping[str, Any]) -> str:
    value = str(artifact.get("for_trade_date") or "")
    if value:
        return value
    path_text = str(artifact.get("path") or "")
    if not path_text:
        return ""
    source = _read_optional_json_artifact(path_text)
    payload = source.get("payload") or {}
    return str(payload.get("for_trade_date") or "")


def _active_scope_artifact_current_object_key(artifact: Mapping[str, Any]) -> tuple[str, str, str, str]:
    asset_kind, identity_key, direction = _active_scope_artifact_object_identity(artifact)
    return (_active_scope_artifact_trade_date(artifact), asset_kind, identity_key, direction)


def _active_scope_artifact_current_object_keys(artifact: Mapping[str, Any]) -> set[tuple[str, str, str, str]]:
    payload: Mapping[str, Any] = artifact
    if artifact.get("path"):
        source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        payload = source.get("payload") or artifact
    trade_date = str(payload.get("for_trade_date") or artifact.get("for_trade_date") or "")
    keys: set[tuple[str, str, str, str]] = set()
    for row_source in payload.get("scope_rows") or []:
        if not isinstance(row_source, Mapping):
            continue
        row = dict(row_source)
        asset_kind = str(row.get("asset_kind") or "")
        identity_key = str(row.get("identity_key") or "")
        row_trade_date = str(row.get("for_trade_date") or trade_date)
        refs = [ref for ref in row.get("active_tracking_refs") or [] if isinstance(ref, Mapping)]
        if refs:
            for ref in refs:
                direction = str(ref.get("direction") or row.get("direction") or "")
                if row_trade_date and asset_kind and identity_key and direction:
                    keys.add((row_trade_date, asset_kind, identity_key, direction))
            continue
        direction = str(row.get("direction") or "")
        if row_trade_date and asset_kind and identity_key and direction:
            keys.add((row_trade_date, asset_kind, identity_key, direction))
    return keys


def _active_scope_current_object_persisted_fanout_paths(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    closed_hhmm: str,
) -> list[Path]:
    if not re.fullmatch(r"[0-2][0-9][0-5][0-9]", str(closed_hhmm or "")):
        return []
    fanout_dir = output_dir / "active_scope_ref_fanout"
    staging_dir = output_dir / "current_day_staging"
    if not fanout_dir.exists() or not fanout_dir.is_dir():
        return []
    paths: set[Path] = set()
    for artifact in active_scope_artifacts:
        source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        if not source["exists"]:
            continue
        payload = dict(source.get("payload") or {})
        for artifact_candidate, candidate_payload in _active_a_minute_batch_payload_candidates(
            artifact=artifact,
            payload=payload,
            closed_hhmm=closed_hhmm,
        ):
            target_hhmm = str(
                candidate_payload.get("target_hhmm")
                or artifact_candidate.get("target_hhmm")
                or ""
            )
            source_run_hash = _active_a_minute_batch_source_run_hash(
                candidate_payload,
                target_hhmm=target_hhmm,
            )
            for_trade_date = str(
                candidate_payload.get("for_trade_date")
                or artifact_candidate.get("for_trade_date")
                or ""
            )
            if not (for_trade_date and target_hhmm and source_run_hash):
                continue
            namespace_token = f"{for_trade_date}_{target_hhmm}_{source_run_hash}"
            staging_path = staging_dir / f"n3_c1_scoped_current_day_staging_v1_{namespace_token}_fastlane.json"
            if not staging_path.exists():
                continue
            fanout_path = fanout_dir / f"n5_active_scope_snapshot_v1_{namespace_token}_ref_fanout.json"
            if fanout_path.exists():
                paths.add(fanout_path)
    return sorted(paths)


def _active_scope_artifacts_with_current_object_persisted_ref_fanout(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    closed_hhmm: str = "",
) -> list[dict[str, Any]]:
    current_object_keys: set[tuple[str, str, str, str]] = set()
    for artifact in active_scope_artifacts:
        current_object_keys.update(_active_scope_artifact_current_object_keys(artifact))
    if not current_object_keys:
        current_object_keys = {
            key
            for key in (_active_scope_artifact_current_object_key(item) for item in active_scope_artifacts)
            if key[0] and key[1] and key[2]
        }
    if not re.fullmatch(r"[0-2][0-9][0-5][0-9]", str(closed_hhmm or "")):
        candidates = _active_scope_artifacts_with_persisted_ref_fanout(
            active_scope_artifacts=active_scope_artifacts,
            output_dir=output_dir,
        )
    else:
        merged: dict[str, dict[str, Any]] = {}
        for artifact in active_scope_artifacts:
            context = _infer_scope_context(artifact)
            merged[context["namespace_token"]] = dict(artifact)
        for path in _active_scope_current_object_persisted_fanout_paths(
            active_scope_artifacts=active_scope_artifacts,
            output_dir=output_dir,
            closed_hhmm=closed_hhmm,
        ):
            source = _read_optional_json_artifact(str(path))
            payload = source.get("payload") or {}
            if payload.get("artifact_type") != INPUT_ARTIFACT_TYPE:
                continue
            for candidate in _active_scope_artifact_candidates(path, payload):
                if candidate.get("object_scope_ref_fanout") is not True:
                    continue
                key = _active_scope_artifact_current_object_key(candidate)
                if current_object_keys and key not in current_object_keys:
                    continue
                context = _infer_scope_context(candidate)
                merged.setdefault(context["namespace_token"], dict(candidate))
        candidates = list(merged.values())
    if not current_object_keys:
        return candidates
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        key = _active_scope_artifact_current_object_key(candidate)
        if key[0] and key[1] and key[2] and key in current_object_keys:
            filtered.append(dict(candidate))
    return filtered


def _target_hhmm_from_active_ref(ref: Mapping[str, Any]) -> str:
    for_trade_date = str(ref.get("for_trade_date") or "")
    first_hhmm = _target_hhmm_from_value(
        ref.get("first_confirmation_minute_label")
        or ref.get("source_trigger_event_time")
        or ref.get("trigger_time")
        or ref.get("latest_n4_event_time")
    )
    next_hhmm = _target_hhmm_from_value(ref.get("next_unchecked_minute_label"))
    if next_hhmm:
        return _max_canonical_hhmm(for_trade_date=for_trade_date, left=next_hhmm, right=first_hhmm)

    last_checked_hhmm = _target_hhmm_from_value(ref.get("last_checked_minute_label"))
    if last_checked_hhmm:
        computed_next = _next_canonical_hhmm(for_trade_date=for_trade_date, hhmm=last_checked_hhmm)
        if not computed_next:
            return ""
        return _max_canonical_hhmm(for_trade_date=for_trade_date, left=computed_next, right=first_hhmm)

    for key in (
        "first_confirmation_minute_label",
        "target_minute_label",
        "source_trigger_event_time",
        "trigger_time",
        "latest_n4_event_time",
    ):
        target_hhmm = _target_hhmm_from_value(ref.get(key))
        if target_hhmm:
            return target_hhmm
    return ""


def _max_canonical_hhmm(*, for_trade_date: str, left: str, right: str) -> str:
    if not right:
        return left
    if not left:
        return right
    labels = _canonical_ashare_1m_labels_cached(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else ()
    left_label = _hhmm_to_minute_label(left)
    right_label = _hhmm_to_minute_label(right)
    if left_label in labels and right_label in labels:
        return left if labels.index(left_label) >= labels.index(right_label) else right
    return left if int(left) >= int(right) else right


def _next_canonical_hhmm(*, for_trade_date: str, hhmm: str) -> str:
    labels = _canonical_ashare_1m_labels_cached(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else ()
    label = _hhmm_to_minute_label(hhmm)
    if label not in labels:
        return ""
    index = labels.index(label) + 1
    if index >= len(labels):
        return ""
    return labels[index].replace(":", "")


def _target_hhmm_from_value(value: Any) -> str:
    hhmm = _hhmm_int(value)
    return f"{hhmm:04d}" if hhmm > 0 else ""


def _fallback_ref_source_run_hash(ref: Mapping[str, Any]) -> str:
    text = "|".join(
        str(ref.get(key) or "")
        for key in (
            "source_trigger_event_id",
            "state_key",
            "asset_kind",
            "identity_key",
            "direction",
            "signal_type",
            "condition_key",
            "first_confirmation_minute_label",
        )
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _clean_fastlane_source_run_hash(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if any(
        token in lowered
        for token in (
            "realtime_action_confirmation_metric",
            "n3p",
            "b1_",
            "b2_",
        )
    ):
        return ""
    return text if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", text) else ""


def _clean_fastlane_source_run_hash_from_namespace(value: Any) -> str:
    text = str(value or "").strip()
    if any(
        token in text.lower()
        for token in (
            "realtime_action_confirmation_metric",
            "n3p",
            "b1_",
            "b2_",
        )
    ):
        return ""
    match = re.fullmatch(r"20[0-9]{6}_[0-2][0-9][0-5][0-9]_([A-Za-z0-9][A-Za-z0-9_-]{0,63})", text)
    return _clean_fastlane_source_run_hash(match.group(1)) if match else ""


def _fastlane_namespace_token(
    *,
    for_trade_date: str,
    target_hhmm: str,
    source_run_hash: str,
) -> str:
    return f"{for_trade_date}_{target_hhmm}_{source_run_hash}"


def _short_scope_hash(*parts: str) -> str:
    text = "|".join(str(part or "") for part in parts if str(part or ""))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12] if text else ""


def _fanout_pull_plan_matches_active_scope(
    pull_plan_payload: Mapping[str, Any],
    active_scope_payload: Mapping[str, Any],
) -> bool:
    plan_rows = [row for row in pull_plan_payload.get("plan_rows") or [] if isinstance(row, Mapping)]
    scope_rows = [row for row in active_scope_payload.get("scope_rows") or [] if isinstance(row, Mapping)]
    if int(pull_plan_payload.get("scope_count") or 0) != len(scope_rows):
        return False
    if len(plan_rows) != len(scope_rows):
        return False
    plan_keys = {_runner_object_scope_key(row) for row in plan_rows}
    scope_keys = {_runner_object_scope_key(row) for row in scope_rows}
    return plan_keys == scope_keys


def _select_scoped_pull_plan_candidate_chunk(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    max_candidates: int,
    require_object_scope_ref_fanout: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bounded_max = max(1, int(max_candidates or DEFAULT_SCOPED_PULL_PLAN_MAX_CANDIDATES))
    records: list[dict[str, Any]] = []
    candidate_artifacts = _active_scope_artifacts_with_persisted_ref_fanout(
        active_scope_artifacts=active_scope_artifacts,
        output_dir=output_dir,
    )
    for sequence, artifact in enumerate(candidate_artifacts):
        if require_object_scope_ref_fanout and artifact.get("object_scope_ref_fanout") is not True:
            continue
        context = _infer_scope_context(artifact)
        pull_plan_path = output_dir / f"n3_c1_scoped_current_day_pull_plan_v1_{context['namespace_token']}_fastlane.json"
        source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        if not source["exists"]:
            continue
        existing = _read_optional_json_artifact(str(pull_plan_path))
        needs_materialize = not existing["exists"]
        if existing["exists"]:
            existing_payload = existing.get("payload") or {}
            fanout_mismatch = bool(
                artifact.get("object_scope_ref_fanout") is True
                and not _fanout_pull_plan_matches_active_scope(existing_payload, source.get("payload") or {})
            )
            needs_materialize = fanout_mismatch or _current_day_artifact_needs_boundary_rebuild(existing_payload)
        if not needs_materialize:
            continue
        target_hhmm = context["target_hhmm"]
        records.append(
            {
                "artifact": dict(artifact),
                "target_hhmm": target_hhmm,
                "source_run_hash": context["source_run_hash"],
                "source_run_namespace": context["namespace_token"],
                "sort_key": (-_hhmm_int(target_hhmm), context["source_run_hash"], sequence),
            }
        )
    records.sort(key=lambda item: item["sort_key"])
    selected_records = records[:bounded_max]
    selected = [dict(item["artifact"]) for item in selected_records]
    remaining_count = max(0, len(records) - len(selected_records))
    summary = {
        "strategy": "scoped_pull_plan_candidate_bounded_chunk_v1",
        "reason": (
            "scoped_pull_plan_candidate_chunk_incomplete"
            if remaining_count > 0
            else "scoped_pull_plan_candidate_chunk_ready"
        ),
        "candidate_scan_bounded": True,
        "candidate_scan_limit": bounded_max,
        "total_candidate_count": len(records),
        "processed_candidate_count": len(selected_records),
        "skipped_candidate_count": remaining_count,
        "remaining_candidate_count": remaining_count,
        "selected_source_runs": [
            {
                "target_hhmm": str(item.get("target_hhmm") or ""),
                "source_run_hash": str(item.get("source_run_hash") or ""),
                "source_run_namespace": str(item.get("source_run_namespace") or ""),
            }
            for item in selected_records
        ],
    }
    return selected, summary


def _materialize_missing_scoped_pull_plans(
    *,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    observed_at: Any,
    deadline_check: Callable[[str], None] | None = None,
) -> None:
    for artifact in active_scope_artifacts:
        context = _infer_scope_context(artifact)
        target_hhmm = context["target_hhmm"]
        pull_plan_path = output_dir / f"n3_c1_scoped_current_day_pull_plan_v1_{context['namespace_token']}_fastlane.json"
        source = _read_optional_json_artifact(str(artifact.get("path") or ""))
        if not source["exists"]:
            if deadline_check is not None:
                deadline_check("scoped_pull_plan_candidate")
            continue
        if pull_plan_path.exists():
            existing = _read_optional_json_artifact(str(pull_plan_path))
            rebuild_for_fanout = bool(
                artifact.get("object_scope_ref_fanout") is True
                and existing["exists"]
                and not _fanout_pull_plan_matches_active_scope(existing.get("payload") or {}, source.get("payload") or {})
            )
            if (
                existing["exists"]
                and not rebuild_for_fanout
                and not _current_day_artifact_needs_boundary_rebuild(existing.get("payload") or {})
            ):
                if deadline_check is not None:
                    deadline_check("scoped_pull_plan_candidate")
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
        if deadline_check is not None:
            deadline_check("scoped_pull_plan_candidate")


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


def _runner_object_scope_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("for_trade_date") or ""),
        str(row.get("asset_kind") or ""),
        str(row.get("identity_key") or ""),
        str(row.get("scope_status") or ""),
    )


def _source_rows_filtered_to_pull_plan(
    source_rows_payload: Mapping[str, Any],
    *,
    pull_plan_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an in-memory source rows view scoped to the pull plan object rows."""

    plan_rows = list(pull_plan_payload.get("plan_rows") or [])
    if not plan_rows:
        return dict(source_rows_payload)
    expected_keys: set[tuple[tuple[str, str, str, str], str]] = set()
    for plan_row in plan_rows:
        object_key = _runner_object_scope_key(plan_row)
        for physical_label in plan_row.get("required_physical_labels") or []:
            expected_keys.add((object_key, _hhmm_to_minute_label(physical_label)))
    if not expected_keys:
        return dict(source_rows_payload)

    def row_matches(row: Mapping[str, Any]) -> bool:
        return (
            _runner_object_scope_key(row),
            _hhmm_to_minute_label(row.get("physical_c1_label")),
        ) in expected_keys

    output = dict(source_rows_payload)
    if "closed_minute_rows" in source_rows_payload:
        rows = [
            dict(row)
            for row in source_rows_payload.get("closed_minute_rows") or []
            if isinstance(row, Mapping) and row_matches(row)
        ]
        output["closed_minute_rows"] = rows
        output["closed_minute_row_count"] = len(rows)
    if "source_rows" in source_rows_payload:
        rows = [
            dict(row)
            for row in source_rows_payload.get("source_rows") or []
            if isinstance(row, Mapping) and row_matches(row)
        ]
        output["source_rows"] = rows
        output["source_row_count"] = len(rows)
    output["scope_count"] = int(pull_plan_payload.get("scope_count") or len(plan_rows))
    output["source_rows_filter_policy"] = "fanout_pull_plan_object_scope_subset_v1"
    return output


def _materialize_missing_scoped_current_day_staging_artifacts(
    *,
    args: argparse.Namespace,
    active_scope_artifacts: Sequence[Mapping[str, Any]],
    output_dir: Path,
    observed_at: Any,
    deadline_check: Callable[[str], None] | None = None,
    require_source_dir_exists: bool = True,
) -> int:
    source_dir_text = str(getattr(args, "current_day_source_artifact_dir", "") or "").strip()
    if not source_dir_text:
        return 0
    source_dir = Path(source_dir_text)
    if not source_dir.exists() or not source_dir.is_dir():
        if not require_source_dir_exists:
            return 0
        raise FastlaneShellBlocked("current_day_source_artifact_dir_missing")
    materialized_count = 0
    for artifact in active_scope_artifacts:
        if deadline_check is not None:
            deadline_check("current_day_staging_candidate")
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
        active_scope = _read_optional_json_artifact(str(artifact.get("path") or ""))
        pull_plan = _read_optional_json_artifact(str(pull_plan_path))
        staging = _read_optional_json_artifact(str(staging_path))
        if staging["exists"] and not _current_day_artifact_needs_boundary_rebuild(staging.get("payload") or {}):
            continue
        source_rows = _find_current_day_source_rows_artifact(
            source_dir,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
        )
        if source_rows and _current_day_artifact_needs_boundary_rebuild(source_rows.get("payload") or {}):
            continue
        if not active_scope["exists"]:
            raise FastlaneShellBlocked("active_scope_artifact_missing")
        if not pull_plan["exists"]:
            raise FastlaneShellBlocked("scoped_pull_plan_missing_for_staging")
        payload = pull_plan.get("payload") or {}
        if payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
            raise FastlaneShellBlocked("scoped_pull_plan_contract_mismatch")
        if payload.get("full_market_fallback_used") is True:
            raise FastlaneShellBlocked("full_market_fallback_forbidden")
        if _is_clean_noop_pull_plan_payload(payload):
            continue
        if payload.get("plan_status") != "planned":
            raise FastlaneShellBlocked("scoped_pull_plan_not_planned")
        if int(payload.get("scope_count") or 0) <= 0:
            continue
        if not source_rows:
            continue
        source_rows_payload = source_rows["payload"]
        if artifact.get("object_scope_ref_fanout") is True:
            source_rows_payload = _source_rows_filtered_to_pull_plan(
                source_rows_payload,
                pull_plan_payload=pull_plan["payload"],
            )
        staging = build_n3_c1_scoped_current_day_staging_artifact(
            active_scope["payload"],
            pull_plan_artifact=pull_plan["payload"],
            source_rows_artifact=source_rows_payload,
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
        materialized_count += 1
    return materialized_count


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
    include_component_readiness: bool = True,
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
            "ref_source_run_hash": str(artifact.get("ref_source_run_hash") or ""),
            "ref_source_run_namespace": str(artifact.get("ref_source_run_namespace") or ""),
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
        planned_artifact["component_readiness"] = (
            _local_component_readiness(planned_artifact)
            if include_component_readiness
            else {}
        )
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
    clean_noop_pull_plan = _is_clean_noop_pull_plan_payload(pull_plan["payload"] or {}) if pull_plan["exists"] else False
    pull_plan_needs_rebuild = bool(
        pull_plan["exists"] and _current_day_artifact_needs_boundary_rebuild(pull_plan.get("payload") or {})
    )
    staging_needs_rebuild = bool(
        staging["exists"] and _current_day_artifact_needs_boundary_rebuild(staging.get("payload") or {})
    )
    metric_context_open_boundary_rebuild_required = bool(
        metric["exists"]
        and _metric_context_artifact_needs_open_boundary_previous_period_rebuild(metric.get("payload") or {})
    )
    metric_context_rolling_window_rebuild_required = bool(
        metric["exists"] and _metric_context_artifact_needs_rolling_window_rebuild(metric.get("payload") or {})
    )
    metric_context_needs_rebuild = (
        metric_context_open_boundary_rebuild_required or metric_context_rolling_window_rebuild_required
    )
    current_day_boundary_rebuild_required = pull_plan_needs_rebuild or staging_needs_rebuild

    if clean_noop_pull_plan:
        status = "clean_noop_skipped"
    elif metric["exists"] and not metric_context_needs_rebuild:
        status = "metric_context_ready_for_n3t_execute_gate"
    elif metric_context_needs_rebuild and staging["exists"] and not staging_needs_rebuild:
        status = "waiting_for_metric_context_artifact"
    elif staging["exists"] and not staging_needs_rebuild:
        status = "waiting_for_metric_context_artifact"
    elif not pull_plan["exists"]:
        status = "waiting_for_scoped_c1_plan"
    elif pull_plan_needs_rebuild or staging_needs_rebuild or not staging["exists"]:
        status = "waiting_for_scoped_pull_staging"
    else:
        status = "metric_context_ready_for_n3t_execute_gate"

    if pull_plan["exists"]:
        payload = pull_plan["payload"]
        if payload.get("artifact_type") != "n3_c1_scoped_current_day_pull_plan_v1":
            violations.append("pull_plan_artifact_type")
        if payload.get("plan_status") != "planned" and not clean_noop_pull_plan:
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
        if not metric_context_needs_rebuild:
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
        "current_day_boundary_rebuild_required": current_day_boundary_rebuild_required,
        "pull_plan_boundary_rebuild_required": pull_plan_needs_rebuild,
        "staging_boundary_rebuild_required": staging_needs_rebuild,
        "metric_context_open_boundary_rebuild_required": metric_context_open_boundary_rebuild_required,
        "metric_context_rolling_window_rebuild_required": metric_context_rolling_window_rebuild_required,
        "metric_context_rebuild_required": metric_context_needs_rebuild,
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
                "source_run_hash": artifact.get("source_run_hash"),
                "namespace_token": artifact.get("namespace_token"),
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


def _scoped_executor_plan_only_clean_noop(scoped_executor_plan: Mapping[str, Any]) -> bool:
    artifacts = list(scoped_executor_plan.get("planned_artifacts") or [])
    if not artifacts:
        return False
    return all(
        (artifact.get("component_readiness") or {}).get("status") == "clean_noop_skipped"
        for artifact in artifacts
    )


def _scoped_executor_plan_has_contract_blocker(scoped_executor_plan: Mapping[str, Any]) -> bool:
    for artifact in scoped_executor_plan.get("planned_artifacts") or []:
        readiness = artifact.get("component_readiness") or {}
        if readiness.get("status") == "blocked_local_component_contract_mismatch":
            return True
        if readiness.get("violations"):
            return True
    return False


def _read_optional_json_artifact(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        return {"exists": False, "path": str(path), "payload": {}}
    stat_result = path.stat()
    cache_key = (str(path.resolve()), int(stat_result.st_mtime_ns), int(stat_result.st_size))
    cached = _JSON_ARTIFACT_CACHE.get(cache_key)
    if cached is not None:
        _JSON_ARTIFACT_CACHE.move_to_end(cache_key)
        return dict(cached)
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise FastlaneShellBlocked(f"local_component_artifact_json_invalid:{path}") from exc
    result = {
        "exists": True,
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "payload": payload,
    }
    _JSON_ARTIFACT_CACHE[cache_key] = dict(result)
    _JSON_ARTIFACT_CACHE.move_to_end(cache_key)
    while len(_JSON_ARTIFACT_CACHE) > JSON_ARTIFACT_CACHE_MAX_ENTRIES:
        _JSON_ARTIFACT_CACHE.popitem(last=False)
    return result


def _clear_json_artifact_cache_for_tests() -> None:
    _JSON_ARTIFACT_CACHE.clear()
    _canonical_ashare_1m_labels_cached.cache_clear()


def _next_required_gate(status: str, target_hhmm: str) -> str:
    if status == "clean_noop_skipped":
        return f"N3_C1_N3T_FASTLANE_{target_hhmm}_NOOP_SKIPPED"
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
        for key in (
            "target_hhmm",
            "target_minute_label",
            "path",
            "source_trigger_run_id",
            "source_run_namespace",
            "action_run_id",
            "for_trade_date",
        )
    )
    explicit_target_hhmm = _target_hhmm_from_value(
        artifact.get("target_hhmm") or artifact.get("target_minute_label")
    )
    hhmm_match = re.search(r"until_([0-2][0-9][0-5][0-9])", search_text)
    if not hhmm_match:
        hhmm_match = re.search(r"_([0-2][0-9][0-5][0-9])(?:_|\\.)", search_text)
    date_match = re.search(r"(20[0-9]{6})", search_text)
    target_hhmm = explicit_target_hhmm or (hhmm_match.group(1) if hhmm_match else "unknown")
    for_trade_date = str(artifact.get("for_trade_date") or (date_match.group(1) if date_match else "unknown"))
    namespace = build_fastlane_source_run_namespace(
        for_trade_date=for_trade_date,
        source_trigger_run_id=str(artifact.get("source_trigger_run_id") or ""),
        action_run_id=str(artifact.get("action_run_id") or ""),
        target_hhmm=target_hhmm,
    )
    source_run_hash = (
        _clean_fastlane_source_run_hash(artifact.get("source_run_hash"))
        or _clean_fastlane_source_run_hash_from_namespace(artifact.get("source_run_namespace"))
        or str(namespace["source_run_hash"])
    )
    namespace_token = str(artifact.get("source_run_namespace") or "")
    namespace_hash = _clean_fastlane_source_run_hash_from_namespace(namespace_token)
    if namespace_hash != source_run_hash:
        namespace_token = _fastlane_namespace_token(
            for_trade_date=str(namespace["for_trade_date"]),
            target_hhmm=str(namespace["target_hhmm"]),
            source_run_hash=source_run_hash,
        )
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
    if scheduler_quiet:
        print(json.dumps(_scheduler_compact_manifest(manifest), ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    return 2 if str(manifest.get("verdict") or "").startswith("BLOCKED") else 0


def _scheduler_quiet_requested(argv: Sequence[str] | None) -> bool:
    values = list(sys.argv[1:] if argv is None else argv)
    return "--scheduler-quiet" in values


def _scheduler_compact_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    fastlane = manifest.get("fastlane") if isinstance(manifest.get("fastlane"), Mapping) else {}
    compact: dict[str, Any] = {
        "verdict": str(manifest.get("verdict") or ""),
        "scheduler_quiet": True,
    }
    for key in (
        "blocked_reason",
        "reason",
        "for_trade_date",
        "writes_enabled",
        "artifact_writes_enabled",
        "active_scope_artifact_count",
    ):
        if key in manifest:
            compact[key] = _compact_scalar(manifest.get(key))
    for key in ("session_phase", "phase"):
        if key in fastlane:
            compact[key] = _compact_scalar(fastlane.get(key))
    lane_results = _scheduler_compact_lane_results(manifest)
    if lane_results:
        compact["lane_results"] = lane_results
    counts = _scheduler_compact_counts(manifest)
    if counts:
        compact["counts"] = counts
    artifact_paths = _scheduler_compact_artifact_paths(manifest)
    if artifact_paths:
        compact["artifact_paths"] = artifact_paths
    latency_ms = _scheduler_compact_latency_ms(manifest)
    if latency_ms:
        compact["latency_ms"] = latency_ms
    boundary = _compact_mapping_scalars(
        manifest.get("boundary"),
        {
            "pulls_market_data",
            "touches_n6",
            "updates_n4_outbox",
            "writes_canonical_minute_bar_1m",
            "writes_db",
            "writes_outbox",
        },
    )
    if boundary:
        compact["boundary"] = boundary
    return compact


def _scheduler_compact_latency_ms(manifest: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "minute_closed_to_source_ms",
        "source_to_staging_ms",
        "staging_to_proof_ms",
        "proof_to_action_ms",
    }
    result: dict[str, Any] = {}
    for key in ("current_day_source_provider_result", "execute_result"):
        value = manifest.get(key)
        if not isinstance(value, Mapping):
            continue
        for field in fields:
            if field in value and value.get(field) is not None:
                result[field] = _compact_scalar(value.get(field))
    return result


def _scheduler_compact_lane_results(manifest: Mapping[str, Any]) -> dict[str, Any]:
    lane_results = manifest.get("lane_results")
    if not isinstance(lane_results, Mapping):
        return {}
    compact: dict[str, Any] = {}
    allowed = {
        "lane_name",
        "reason",
        "selected_candidate_count",
        "processed_candidate_count",
        "skipped_candidate_count",
        "failed_candidate_count",
        "remaining_candidate_count",
        "priority_candidate_count",
        "hard_blocker_count",
        "candidate_scan_bounded",
        "candidate_scan_limit",
        "total_candidate_count",
        "oldest_pending_trigger_time",
        "max_pending_age_seconds",
    }
    for lane_name, lane_result in lane_results.items():
        lane_summary = _compact_mapping_scalars(lane_result, allowed)
        if lane_summary:
            compact[str(lane_name)] = lane_summary
    return compact


def _scheduler_compact_counts(manifest: Mapping[str, Any]) -> dict[str, Any]:
    counts = _compact_mapping_scalars(
        manifest,
        {
            "active_scope_artifact_count",
            "scope_count",
            "metric_context_count",
            "processed_candidate_count",
            "skipped_candidate_count",
            "remaining_candidate_count",
            "priority_candidate_count",
        },
    )
    list_count_keys = {
        "active_scope_artifacts": "active_scope_artifact_row_count",
        "artifacts": "artifact_row_count",
    }
    for key, output_key in list_count_keys.items():
        value = manifest.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            counts[output_key] = len(value)
    return counts


def _scheduler_compact_artifact_paths(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return _compact_mapping_scalars(
        manifest,
        {
            "active_scope_artifact_dir",
            "active_scope_artifact_path",
            "input_active_scope_artifact_path",
            "metric_context_artifact_path",
            "output_dir",
            "pull_plan_path",
            "staging_artifact_path",
        },
    )


def _compact_mapping_scalars(value: Any, allowed_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in sorted(allowed_keys):
        if key in value:
            result[key] = _compact_scalar(value.get(key))
    return result


def _compact_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _is_scheduler_phase_noop(manifest: Mapping[str, Any]) -> bool:
    if not str(manifest.get("verdict") or "").startswith("BLOCKED"):
        return False
    if manifest.get("writes_enabled") is not False:
        return False
    reason = str(manifest.get("blocked_reason") or "")
    return reason.startswith("fastlane active_worker_policy_review_ref_not_ready:") or reason in {
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
