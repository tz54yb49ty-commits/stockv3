"""Per-minute N3 intraday B1/C1/B2 child artifact generation.

This module is deliberately side-effect-light: it builds deterministic artifact
paths and writes only reviewed dry-run/contract/preflight/rollback draft files
when explicitly asked. It never connects to the database, executes child
runners, consumes event infra, or starts workers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any

from ashare_v3.market.intraday_supervisor import build_intraday_supervisor_paths, build_stage_run_ids
from ashare_v3.market.today_minute_plan import ASIA_SHANGHAI, build_expected_bar_times


ASSET_KINDS = ("stock", "index", "board")
B2_CALCULATION_CONFIG = {
    "amount_projection_expand_threshold": "1.2",
    "amount_projection_shrink_threshold": "0.8",
    "calculation_config_hash": "c0e47d3beec744930c098fae1a083fc1da95f9752bb2efc01dc76b3ed4d92b1d",
    "calculation_method": "active_30m_bucket_projection_v1_strict_current_lineage",
    "completion_ratio_min_ready": "0.2",
    "price_flat_abs_pct_threshold": "0.001",
    "window_total_seconds": 1800,
}
B2_EXPECTED_DISTRIBUTION_POLICY = {
    "mode": "derive_from_projection_rows",
    "applies_to_artifact_generation_mode": "dynamic_intraday_child_artifact",
    "reason": (
        "Dynamic intraday child artifacts are generated before the same pass writes B1/C1 facts; "
        "the B2 execute runner derives the reviewed distribution from the projection rows it builds "
        "and keeps the resulting canonical counts in the execute report."
    ),
}
B2_FACT_ONLY_PROJECTION_TIME_POLICY = {
    "mode": "fact_only_defer_off_bucket_source_snapshot_time",
    "bucket_time_source": "source_snapshot_time",
    "off_bucket_source_snapshot_time_handling": "NOOP_PASS_NO_WRITE",
    "no_closed_data_forged": True,
    "maps_midday_to_trading_bucket": False,
    "applies_to_artifact_generation_mode": "dynamic_intraday_child_artifact",
    "reason": (
        "Fact-only intraday B2 must defer midday/off-bucket source snapshot_time instead of "
        "mapping observed_at to a trading bucket or forging closed minute data."
    ),
}
B2_FACT_ONLY_SNAPSHOT_TRACE_POLICY = {
    "allow_missing_snapshot_event_id": True,
    "required_trace_fields": ["snapshot_id", "subscription_id", "pull_plan_id", "source_adapter"],
}
B1_FACT_ONLY_SOURCE_TIME_POLICY = {
    "mode": "strict_live",
    "source_time_future_guard_enabled": True,
    "future_tolerance_seconds": 120,
    "future_source_time_handling": "P0_BLOCK_NO_OUTBOX",
    "untrusted_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
    "board_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
    "index_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
    "normalize_to_observed_at_enabled": True,
    "event_time_policy": "observed_at_for_untrusted_period_label",
    "fact_only_quality_policy": "quality_visible_source_time_label_normalized",
}
B1_FACT_ONLY_SOURCE_TIME_SEMANTICS_POLICY = {
    "reviewed_policy_enabled": True,
    "policy_owner_gate": "N3_20260612_B1_FACT_ONLY_SOURCE_TIME_SEMANTICS_POLICY_AND_FAILED_RUN_CLEANUP_GATE",
    "untrusted_period_label_handling": "NORMALIZE_TO_OBSERVED_AT",
    "raw_period_label_trace_required": True,
    "observed_at_required": True,
    "fetched_at_required": True,
    "quality_visible_status": "source_time_label_normalized",
    "future_source_time_handling": "P0_BLOCK_NO_OUTBOX",
    "writes_outbox": False,
}


class IntradayChildArtifactError(RuntimeError):
    """Base error for dynamic child artifact generation."""


class IntradayChildArtifactConflictError(IntradayChildArtifactError):
    """Raised when an existing generated artifact differs from the planned content."""


@dataclass(frozen=True)
class IntradayChildArtifactRequest:
    """Input contract for one for_trade_date + latest closed minute generation."""

    for_trade_date: str
    latest_closed_minute_hhmm: str
    subscription_run_id: str
    preload_run_id: str
    source_condition_run_id: str
    docs_root: str | Path = "docs"
    sql_root: str | Path = "sql"
    latest_closed_minute: str | None = None
    projection_input_mode: str = "closed_minute"
    subscription_summary: dict[str, Any] | None = None


def build_intraday_child_artifact_plan(request: IntradayChildArtifactRequest) -> dict[str, Any]:
    """Build a deterministic artifact-generation plan without writing files."""

    validate_request(request)
    stage_run_mode = "auction" if request.projection_input_mode == "auction_or_snapshot_only" else "closed_minute"
    stage_run_ids = build_stage_run_ids(
        for_trade_date=request.for_trade_date,
        latest_closed_minute_hhmm=request.latest_closed_minute_hhmm,
        subscription_run_id=request.subscription_run_id,
        stage_run_mode=stage_run_mode,
    )
    paths = build_intraday_supervisor_paths(
        for_trade_date=request.for_trade_date,
        latest_closed_minute_hhmm=request.latest_closed_minute_hhmm,
        docs_root=request.docs_root,
        sql_root=request.sql_root,
        stage_run_mode=stage_run_mode,
    )
    previous_day = derive_previous_day_minute_date(request)
    generated_artifacts = build_generated_artifact_paths(paths)
    subscription_summary = load_subscription_summary(request)
    payloads = build_artifact_payloads(
        request=request,
        stage_run_ids=stage_run_ids,
        generated_artifacts=generated_artifacts,
        previous_day_minute_date=previous_day,
        subscription_summary=subscription_summary,
    )
    return {
        "stage": "N3-intraday-B1-C1-B2-dynamic-child-artifact-generation",
        "layer_role": "N3_market_data",
        "result": "PLAN_ONLY",
        "for_trade_date": request.for_trade_date,
        "latest_closed_minute": request.latest_closed_minute,
        "latest_closed_minute_hhmm": request.latest_closed_minute_hhmm,
        "projection_input_mode": request.projection_input_mode,
        "subscription_run_id": request.subscription_run_id,
        "preload_run_id": request.preload_run_id,
        "source_condition_run_id": request.source_condition_run_id,
        "previous_day_minute_date": previous_day,
        "subscription_summary": subscription_summary,
        "stage_run_ids": stage_run_ids,
        "generated_artifacts": generated_artifacts,
        "artifact_payloads": payloads,
        "idempotency_policy": {
            "artifact_path_key": "for_trade_date + latest_closed_minute_hhmm",
            "existing_identical_artifacts": "unchanged",
            "existing_conflicting_artifacts": "BLOCKED",
            "allow_overwrite_requires_explicit_flag": True,
        },
        "side_effects": {
            "database_connected": False,
            "subprocess_executed": False,
            "supervisor_executed": False,
            "b1_c1_b2_executed": False,
            "outbox_inbox_checkpoint_consumed_or_updated": False,
            "n4_n5_n6_entered": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def write_intraday_child_artifacts(plan: dict[str, Any], *, allow_overwrite: bool = False) -> dict[str, Any]:
    """Write planned child artifacts after conflict checks."""

    writes = flatten_artifact_payloads(plan)
    conflicts = []
    written = 0
    unchanged = 0
    for path_text, content in writes:
        path = Path(path_text)
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing == content:
                unchanged += 1
                continue
            if not allow_overwrite:
                conflicts.append(path_text)
                continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written += 1
    if conflicts:
        raise IntradayChildArtifactConflictError(
            "N3 intraday child artifact generation blocked by existing conflicting artifacts: "
            + ", ".join(conflicts)
        )
    return {
        "status": "unchanged" if written == 0 else "written",
        "written_artifact_count": written,
        "unchanged_artifact_count": unchanged,
        "artifact_count": len(writes),
    }


def write_intraday_child_artifact_report(
    report: dict[str, Any],
    *,
    json_report_path: str | Path,
    markdown_report_path: str | Path,
) -> None:
    """Write generator execution report files."""

    write_json(json_report_path, report)
    write_text(markdown_report_path, render_intraday_child_artifact_markdown(report))


def validate_request(request: IntradayChildArtifactRequest) -> None:
    if not re.fullmatch(r"\d{8}", request.for_trade_date):
        raise IntradayChildArtifactError("for_trade_date must be YYYYMMDD")
    if not re.fullmatch(r"\d{4}", request.latest_closed_minute_hhmm):
        raise IntradayChildArtifactError("latest_closed_minute_hhmm must be HHMM")
    hour = int(request.latest_closed_minute_hhmm[:2])
    minute = int(request.latest_closed_minute_hhmm[2:])
    if hour > 23 or minute > 59:
        raise IntradayChildArtifactError("latest_closed_minute_hhmm is not a valid HHMM")
    if not request.subscription_run_id:
        raise IntradayChildArtifactError("subscription_run_id is required")
    if not request.preload_run_id:
        raise IntradayChildArtifactError("preload_run_id is required")
    if not request.source_condition_run_id:
        raise IntradayChildArtifactError("source_condition_run_id is required")
    if request.projection_input_mode not in {"closed_minute", "auction_or_snapshot_only"}:
        raise IntradayChildArtifactError("projection_input_mode must be closed_minute or auction_or_snapshot_only")


def derive_previous_day_minute_date(request: IntradayChildArtifactRequest) -> str:
    match = re.search(r"preload_(\d{8})_for_" + re.escape(request.for_trade_date), request.preload_run_id)
    return match.group(1) if match else ""


def expected_bar_count_for_request(request: IntradayChildArtifactRequest) -> int:
    if request.projection_input_mode == "auction_or_snapshot_only":
        return 0
    latest_closed_minute = parse_latest_closed_minute_for_request(request)
    return len(build_expected_bar_times(trade_date=request.for_trade_date, latest_closed_minute=latest_closed_minute))


def parse_latest_closed_minute_for_request(request: IntradayChildArtifactRequest) -> datetime:
    if request.latest_closed_minute:
        return datetime.fromisoformat(request.latest_closed_minute.replace("Z", "+00:00")).astimezone(ASIA_SHANGHAI)
    return datetime.strptime(
        f"{request.for_trade_date}{request.latest_closed_minute_hhmm}",
        "%Y%m%d%H%M",
    ).replace(tzinfo=ASIA_SHANGHAI)


def build_generated_artifact_paths(paths: Any) -> dict[str, dict[str, str]]:
    return {
        "B1": {
            "execute_contract_json": paths.b1_contract_path,
            "execute_contract_md": paths.b1_contract_path.removesuffix(".json") + ".md",
            "execute_readiness_json": paths.b1_readiness_path,
            "execute_readiness_md": paths.b1_readiness_path.removesuffix(".json") + ".md",
            "rollback_sql": paths.b1_rollback_sql_path,
            "json_report_path": paths.b1_json_report_path,
            "markdown_report_path": paths.b1_markdown_report_path,
            "pre_backup_path": paths.b1_pre_backup_path,
            "post_backup_path": paths.b1_post_backup_path,
        },
        "C1": {
            "c0_dry_run_json": paths.c0_plan_path,
            "c0_dry_run_md": paths.c0_plan_path.removesuffix(".json") + ".md",
            "rollback_sql": paths.c1_rollback_sql_path,
            "json_report_path": paths.c1_json_report_path,
            "markdown_report_path": paths.c1_markdown_report_path,
            "pre_backup_path": paths.c1_pre_backup_path,
            "post_backup_path": paths.c1_post_backup_path,
        },
        "B2": {
            "dry_run_json": paths.b2_dry_run_path,
            "dry_run_md": paths.b2_dry_run_path.removesuffix(".json") + ".md",
            "execute_contract_json": paths.b2_contract_path,
            "execute_contract_md": paths.b2_contract_path.removesuffix(".json") + ".md",
            "execute_preflight_json": paths.b2_preflight_path,
            "execute_preflight_md": paths.b2_preflight_path.removesuffix(".json") + ".md",
            "rollback_sql": paths.b2_rollback_sql_path,
            "json_report_path": paths.b2_json_report_path,
            "markdown_report_path": paths.b2_markdown_report_path,
        },
    }


def build_artifact_payloads(
    *,
    request: IntradayChildArtifactRequest,
    stage_run_ids: dict[str, str],
    generated_artifacts: dict[str, dict[str, str]],
    previous_day_minute_date: str,
    subscription_summary: dict[str, Any],
) -> dict[str, dict[str, str]]:
    b1_contract = build_b1_contract(request, stage_run_ids, generated_artifacts, previous_day_minute_date, subscription_summary)
    b1_readiness = build_b1_readiness(request, stage_run_ids, generated_artifacts, subscription_summary)
    c1_plan = build_c1_plan(
        request,
        stage_run_ids,
        generated_artifacts,
        previous_day_minute_date,
        subscription_summary,
    )
    b2_dry_run = build_b2_dry_run(request, stage_run_ids, subscription_summary)
    b2_contract = build_b2_contract(request, stage_run_ids, generated_artifacts, previous_day_minute_date, subscription_summary)
    b2_preflight = build_b2_preflight(request, stage_run_ids, generated_artifacts, subscription_summary)
    return {
        "B1": {
            "execute_contract_json": stable_json(b1_contract),
            "execute_contract_md": render_stage_markdown("B1 execute contract", b1_contract),
            "execute_readiness_json": stable_json(b1_readiness),
            "execute_readiness_md": render_stage_markdown("B1 execute readiness", b1_readiness),
            "rollback_sql": build_rollback_sql(stage="B1", run_id=stage_run_ids["B1"], source_run_id=request.subscription_run_id),
        },
        "C1": {
            "c0_dry_run_json": stable_json(c1_plan),
            "c0_dry_run_md": render_stage_markdown("C1 C0 dry-run", c1_plan),
            "rollback_sql": build_rollback_sql(stage="C1", run_id=stage_run_ids["C1"], source_run_id=request.subscription_run_id),
        },
        "B2": {
            "dry_run_json": stable_json(b2_dry_run),
            "dry_run_md": render_stage_markdown("B2 dry-run", b2_dry_run),
            "execute_contract_json": stable_json(b2_contract),
            "execute_contract_md": render_stage_markdown("B2 execute contract", b2_contract),
            "execute_preflight_json": stable_json(b2_preflight),
            "execute_preflight_md": render_stage_markdown("B2 execute preflight", b2_preflight),
            "rollback_sql": build_rollback_sql(stage="B2", run_id=stage_run_ids["B2"], source_run_id=request.subscription_run_id),
        },
    }


def build_b1_contract(
    request: IntradayChildArtifactRequest,
    stage_run_ids: dict[str, str],
    generated_artifacts: dict[str, dict[str, str]],
    previous_day_minute_date: str,
    subscription_summary: dict[str, Any],
) -> dict[str, Any]:
    expected_asset_counts = build_snapshot_expected_asset_counts(subscription_summary)
    return {
        "stage": "N3-B1-preflight",
        "layer_role": "N3_market_data",
        "execution_mode": "realtime_daily_snapshot_run_once_execute_contract",
        "artifact_generation_mode": "dynamic_intraday_child_artifact",
        "source_run_id": request.subscription_run_id,
        "market_data_run_id": request.subscription_run_id,
        "snapshot_run_id": stage_run_ids["B1"],
        "source_condition_run_id": request.source_condition_run_id,
        "for_trade_date": request.for_trade_date,
        "source_trade_date": previous_day_minute_date,
        "prev_trade_date": previous_day_minute_date,
        "required_data_kind": "realtime_daily_snapshot",
        "expected_asset_counts": expected_asset_counts,
        "expected_row_count": sum(int(row["expected_snapshot_rows"]) for row in expected_asset_counts.values()),
        "writes_outbox": False,
        "writes_event_outbox": False,
        "writes_market_snapshot_updated": False,
        "generated_outbox_events": [],
        "source_time_policy": dict(B1_FACT_ONLY_SOURCE_TIME_POLICY),
        "fact_only_source_time_semantics_policy": dict(B1_FACT_ONLY_SOURCE_TIME_SEMANTICS_POLICY),
        "rollback_sql_path": generated_artifacts["B1"]["rollback_sql"],
        "execute_runner_readiness": {
            "runner_exists": True,
            "runner_path": "scripts/run_realtime_daily_snapshot_once.py",
            "runner_requires_execute_flag": True,
            "runner_requires_user_confirmed_flag": True,
            "runner_requires_no_outbox_flag": True,
            "runner_accepts_rollback_sql_path_argument": False,
            "rollback_sql_path_exposed_in_supervisor_metadata": True,
            "execute_final_gate_allowed": False,
            "blocked_reason": "dynamic child artifacts require separate final gate before live child execute",
        },
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": [generator_quality_note()]},
        "side_effects": side_effects_false(),
    }


def build_b1_readiness(
    request: IntradayChildArtifactRequest,
    stage_run_ids: dict[str, str],
    generated_artifacts: dict[str, dict[str, str]],
    subscription_summary: dict[str, Any],
) -> dict[str, Any]:
    expected_asset_counts = build_snapshot_expected_asset_counts(subscription_summary)
    return {
        "stage": "N3-B1-readiness-gate",
        "layer_role": "N3_market_data",
        "mode": "dynamic_child_artifact_generation",
        "ready": True,
        "blocked": False,
        "blocked_reason": None,
        "for_trade_date": request.for_trade_date,
        "source_run_id": request.subscription_run_id,
        "market_data_run_id": request.subscription_run_id,
        "snapshot_run_id": stage_run_ids["B1"],
        "preload_run_id": request.preload_run_id,
        "expected_asset_counts": expected_asset_counts,
        "source_time_policy": dict(B1_FACT_ONLY_SOURCE_TIME_POLICY),
        "fact_only_source_time_semantics_policy": dict(B1_FACT_ONLY_SOURCE_TIME_SEMANTICS_POLICY),
        "rollback_sql_path": generated_artifacts["B1"]["rollback_sql"],
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": [generator_quality_note()]},
        "side_effects": side_effects_false(),
    }


def build_c1_plan(
    request: IntradayChildArtifactRequest,
    stage_run_ids: dict[str, str],
    generated_artifacts: dict[str, dict[str, str]],
    previous_day_minute_date: str,
    subscription_summary: dict[str, Any],
) -> dict[str, Any]:
    auction_mode = request.projection_input_mode == "auction_or_snapshot_only"
    minute_counts = build_minute_object_counts(subscription_summary)
    expected_bar_count_per_object = expected_bar_count_for_request(request)
    expected_minute_rows = {
        asset: int(count) * expected_bar_count_per_object
        for asset, count in minute_counts.items()
    }
    return {
        "stage": "N3-C0",
        "layer_role": "N3_market_data",
        "result": "SKIPPED" if auction_mode else "DRY_RUN_PASS",
        "blocked": False,
        "skip_reason": "no_closed_minute_available" if auction_mode else None,
        "execute_allowed": not auction_mode,
        "artifact_generation_mode": "dynamic_intraday_child_artifact",
        "for_trade_date": request.for_trade_date,
        "latest_closed_minute_hhmm": request.latest_closed_minute_hhmm,
        "projection_input_mode": request.projection_input_mode,
        "source_market_data_run_id": request.subscription_run_id,
        "source_run_id": request.subscription_run_id,
        "source_condition_run_id": request.source_condition_run_id,
        "source_trade_date": previous_day_minute_date,
        "prev_trade_date": previous_day_minute_date,
        "latest_closed_minute": request.latest_closed_minute,
        "today_minute_run_id": stage_run_ids["C1"],
        "required_data_kind": "minute_bar_1m",
        "today_minute_object_count_by_asset_kind": minute_counts,
        "expected_bar_count_per_object": expected_bar_count_per_object,
        "expected_minute_rows_by_asset_kind": expected_minute_rows,
        "event_outbox_write_required_in_execute": False,
        "generated_event_types_for_execute": [],
        "rollback_sql_path": generated_artifacts["C1"]["rollback_sql"],
        "execute_contract": {
            "stage": "N3-C1-preflight",
            "layer_role": "N3_market_data",
            "today_minute_run_id": stage_run_ids["C1"],
            "source_market_data_run_id": request.subscription_run_id,
            "source_run_id": request.subscription_run_id,
            "run_once_only": True,
            "requires_execute_flag": True,
            "requires_user_confirmed_flag": True,
            "writes_outbox": False,
            "generated_event_types": [],
            "execute_allowed": not auction_mode,
            "blocked_reason": "no_closed_minute_available" if auction_mode else None,
        },
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": [generator_quality_note()]},
        "side_effects": side_effects_false(),
    }


def build_b2_dry_run(
    request: IntradayChildArtifactRequest,
    stage_run_ids: dict[str, str],
    subscription_summary: dict[str, Any],
) -> dict[str, Any]:
    projection_rows = build_projection_expected_rows(subscription_summary)
    expected_distribution = build_b2_pending_expected_distribution()
    expected_distribution_policy = dict(B2_EXPECTED_DISTRIBUTION_POLICY)
    return {
        "stage": "N3-B2-realtime-projection-dry-run",
        "layer_role": "N3_market_data",
        "result": "DRY_RUN_PASS",
        "blocked": False,
        "blockers": [],
        "projection_run_id_candidate": stage_run_ids["B2"],
        "for_trade_date": request.for_trade_date,
        "projection_input_mode": request.projection_input_mode,
        "source_requirements": build_b2_source_requirements(request),
        "snapshot_only_execution_policy": build_b2_snapshot_only_execution_policy(request),
        "projection_time_policy": dict(B2_FACT_ONLY_PROJECTION_TIME_POLICY),
        "fact_only_snapshot_trace_policy": dict(B2_FACT_ONLY_SNAPSHOT_TRACE_POLICY),
        "expected_projection_rows": projection_rows,
        "expected_distribution": expected_distribution,
        "expected_distribution_policy": expected_distribution_policy,
        "ready_not_ready_distribution": {
            "ready": expected_distribution["ready_rows"],
            "not_ready": expected_distribution["not_ready_rows"],
            "distribution_source": expected_distribution_policy["mode"],
        },
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": [generator_quality_note()]},
        "side_effects": side_effects_false(),
    }


def build_b2_contract(
    request: IntradayChildArtifactRequest,
    stage_run_ids: dict[str, str],
    generated_artifacts: dict[str, dict[str, str]],
    previous_day_minute_date: str,
    subscription_summary: dict[str, Any],
) -> dict[str, Any]:
    projection_rows = build_projection_expected_rows(subscription_summary)
    expected_distribution = build_b2_pending_expected_distribution()
    expected_distribution_policy = dict(B2_EXPECTED_DISTRIBUTION_POLICY)
    return {
        "stage": "N3-B2-realtime-projection-execute-contract",
        "layer_role": "N3_market_data",
        "execution_mode": "realtime_projection_metric_run_once_execute",
        "artifact_generation_mode": "dynamic_intraday_child_artifact",
        "projection_run_id": stage_run_ids["B2"],
        "projection_input_mode": request.projection_input_mode,
        "source_runs": {
            "source_condition_run_id": request.source_condition_run_id,
            "subscription_run_id": request.subscription_run_id,
            "snapshot_run_id": stage_run_ids["B1"],
            "preload_run_id": request.preload_run_id,
            "today_minute_run_id": stage_run_ids["C1"] if request.projection_input_mode == "closed_minute" else None,
        },
        "source_requirements": build_b2_source_requirements(request),
        "snapshot_only_execution_policy": build_b2_snapshot_only_execution_policy(request),
        "calculation_config": dict(B2_CALCULATION_CONFIG),
        "projection_time_policy": dict(B2_FACT_ONLY_PROJECTION_TIME_POLICY),
        "fact_only_snapshot_trace_policy": dict(B2_FACT_ONLY_SNAPSHOT_TRACE_POLICY),
        "dates": {
            "for_trade_date": request.for_trade_date,
            "source_trade_date": previous_day_minute_date,
            "prev_trade_date": previous_day_minute_date,
        },
        "expected_projection_rows": projection_rows,
        "expected_distribution": expected_distribution,
        "expected_distribution_policy": expected_distribution_policy,
        "rollback_sql_path": generated_artifacts["B2"]["rollback_sql"],
        "writes_outbox": False,
        "updates_market_snapshot_payload": False,
        "consumes_outbox": False,
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": [generator_quality_note()]},
        "side_effects": side_effects_false(),
    }


def build_b2_preflight(
    request: IntradayChildArtifactRequest,
    stage_run_ids: dict[str, str],
    generated_artifacts: dict[str, dict[str, str]],
    subscription_summary: dict[str, Any],
) -> dict[str, Any]:
    projection_rows = build_projection_expected_rows(subscription_summary)
    expected_distribution = build_b2_pending_expected_distribution()
    expected_distribution_policy = dict(B2_EXPECTED_DISTRIBUTION_POLICY)
    auction_mode = request.projection_input_mode == "auction_or_snapshot_only"
    return {
        "stage": "N3-B2-realtime-projection-execute-preflight",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_PASS",
        "blocked": False,
        "blockers": [],
        "projection_run_id": stage_run_ids["B2"],
        "for_trade_date": request.for_trade_date,
        "projection_input_mode": request.projection_input_mode,
        "source_requirements": build_b2_source_requirements(request),
        "snapshot_only_execution_policy": build_b2_snapshot_only_execution_policy(request),
        "projection_time_policy": dict(B2_FACT_ONLY_PROJECTION_TIME_POLICY),
        "fact_only_snapshot_trace_policy": dict(B2_FACT_ONLY_SNAPSHOT_TRACE_POLICY),
        "rollback_sql_path": generated_artifacts["B2"]["rollback_sql"],
        "expected_distribution": expected_distribution,
        "expected_distribution_policy": expected_distribution_policy,
        "expected_projection_rows": projection_rows,
        "contract_summary": {
            "writes_outbox": False,
            "updates_market_snapshot_payload": False,
            "consumes_outbox": False,
        },
        "lineage_checks": [
            {"name": "source_condition_run_id_present", "passed": True, "value": request.source_condition_run_id},
            {"name": "subscription_run_id_present", "passed": True, "value": request.subscription_run_id},
            {"name": "preload_run_id_present", "passed": True, "value": request.preload_run_id},
            {
                "name": "today_minute_run_id_required" if not auction_mode else "today_minute_run_id_not_required",
                "passed": True,
                "value": request.projection_input_mode == "closed_minute",
            },
        ],
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": [generator_quality_note()]},
        "side_effects": side_effects_false(),
    }


def build_b2_pending_expected_distribution() -> dict[str, Any]:
    return {
        "ready_rows": None,
        "ready_by_asset": {},
        "not_ready_rows": None,
        "not_ready_by_asset": {},
        "projection_signal_status": {},
        "projection_quality_status": {},
        "trace_status": {},
        "board_not_ready": None,
        "bj_920xxx_not_ready": None,
        "distribution_status": "pending_execute_row_build",
    }


def build_b2_source_requirements(request: IntradayChildArtifactRequest) -> dict[str, Any]:
    requires_today_minute = request.projection_input_mode == "closed_minute"
    return {
        "requires_snapshot_run": True,
        "requires_previous_day_minute_run": True,
        "requires_today_minute_run": requires_today_minute,
        "closed_minute_forged": False,
        "auction_or_snapshot_only_allowed": request.projection_input_mode == "auction_or_snapshot_only",
    }


def build_b2_snapshot_only_execution_policy(request: IntradayChildArtifactRequest) -> dict[str, Any]:
    enabled = request.projection_input_mode == "auction_or_snapshot_only"
    return {
        "enabled": enabled,
        "noop_pass_no_write_allowed": enabled,
        "noop_reason": "auction_or_snapshot_only_waiting_for_metric_runner" if enabled else None,
        "is_auction_virtual": enabled,
        "period_source": "snapshot_only_no_closed_1m" if enabled else "closed_minute_1m",
        "quality_status": "pending_market_data" if enabled else "ready_for_closed_minute_projection",
        "trace_required_fields": [
            "snapshot_run_id",
            "subscription_run_id",
            "preload_run_id",
            "source_condition_run_id",
            "projection_input_mode",
        ],
        "closed_minute_forged": False,
        "minute_bar_closed_written": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "n4_n5_n6_entered": False,
    }


def b2_auction_runner_blocker() -> dict[str, str]:
    return {
        "code": "b2_auction_mode_runner_requires_today_minute_run",
        "message": "Current run_realtime_projection_metric_once.py / realtime_projection_execute.py still requires today_minute_run_id; auction_or_snapshot_only B2 artifacts are generated for review but blocked until a snapshot-only B2 runner path is implemented.",
        "owner_layer": "N3_market_data",
    }


def load_subscription_summary(request: IntradayChildArtifactRequest) -> dict[str, Any]:
    if request.subscription_summary is not None:
        return normalize_subscription_summary(
            request.subscription_summary,
            source_artifact_path=None,
            source="live_subscription_counts",
        )

    docs_root = Path(request.docs_root)
    candidates = [
        docs_root / f"N3_A1_{request.for_trade_date}_MARKET_DATA_SUBSCRIPTION_DRY_RUN.json",
        docs_root / f"N3_A1_{request.for_trade_date}_subscription_execute_report.json",
        docs_root / f"N3_A1_{request.for_trade_date}_SUBSCRIPTION_EXECUTE_REPORT.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        summary = data.get("dry_run_summary") if isinstance(data.get("dry_run_summary"), dict) else data
        snapshot_counts = normalize_asset_counts(summary.get("object_count_by_asset_kind") or {})
        minute_counts = normalize_asset_counts(summary.get("previous_day_minute_required_object_count_by_asset_kind") or {})
        if any(snapshot_counts.values()) or any(minute_counts.values()):
            return normalize_subscription_summary(
                {
                    "snapshot_object_count_by_asset_kind": snapshot_counts,
                    "today_minute_object_count_by_asset_kind": minute_counts,
                },
                source_artifact_path=str(path),
                source="subscription_artifact",
            )
    return {
        "source": "schema_only_zero_counts",
        "source_artifact_path": None,
        "snapshot_object_count_by_asset_kind": zero_counts(),
        "today_minute_object_count_by_asset_kind": zero_counts(),
    }


def normalize_subscription_summary(
    summary: dict[str, Any],
    *,
    source_artifact_path: str | None,
    source: str,
) -> dict[str, Any]:
    snapshot_counts = normalize_asset_counts(summary.get("snapshot_object_count_by_asset_kind") or {})
    minute_counts = normalize_asset_counts(
        summary.get("today_minute_object_count_by_asset_kind")
        or summary.get("previous_day_minute_required_object_count_by_asset_kind")
        or {}
    )
    output = {
        "source": str(summary.get("source") or source),
        "source_artifact_path": source_artifact_path,
        "snapshot_object_count_by_asset_kind": snapshot_counts,
        "today_minute_object_count_by_asset_kind": minute_counts,
    }
    if summary.get("source_run_id"):
        output["source_run_id"] = str(summary["source_run_id"])
    return output


def normalize_asset_counts(value: dict[str, Any]) -> dict[str, int]:
    return {asset: int(value.get(asset) or 0) for asset in ASSET_KINDS}


def build_snapshot_expected_asset_counts(subscription_summary: dict[str, Any]) -> dict[str, dict[str, int]]:
    counts = normalize_asset_counts(subscription_summary.get("snapshot_object_count_by_asset_kind") or {})
    return {
        asset: {
            "object_count": int(count),
            "subscription_count": int(count),
            "expected_snapshot_rows": int(count),
        }
        for asset, count in counts.items()
    }


def build_minute_object_counts(subscription_summary: dict[str, Any]) -> dict[str, int]:
    return normalize_asset_counts(subscription_summary.get("today_minute_object_count_by_asset_kind") or {})


def build_projection_expected_rows(subscription_summary: dict[str, Any]) -> dict[str, int]:
    counts = normalize_asset_counts(subscription_summary.get("snapshot_object_count_by_asset_kind") or {})
    counts["total"] = sum(counts.values())
    return counts


def build_rollback_sql(*, stage: str, run_id: str, source_run_id: str) -> str:
    stage_tables = {
        "B1": [
            "stock_realtime_daily_snapshot",
            "index_realtime_daily_snapshot",
            "board_realtime_daily_snapshot",
        ],
        "C1": [
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
        ],
        "B2": [
            "stock_realtime_projection_metric",
            "index_realtime_projection_metric",
            "board_realtime_projection_metric",
        ],
    }
    delete_column = {"B1": "run_id", "C1": "source_run_id", "B2": "projection_run_id"}[stage]
    downstream_tables = [
        "common_event_outbox",
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "stock_realtime_projection_metric",
        "index_realtime_projection_metric",
        "board_realtime_projection_metric",
        "common_trigger_state",
        "common_trigger_match",
        "common_action_confirmation",
        "common_action_event",
        "user_card_projection",
        "user_signal_projection",
        "user_signal_card",
        "user_notification_queue",
        "user_sim_order",
        "user_sim_trade",
        "user_sim_position",
        "n6_virtual_order",
        "n6_virtual_trade",
        "n6_virtual_position",
        "n6_virtual_position_event",
        "n6_virtual_pnl_snapshot",
    ]
    table_array = ", ".join(f"'{table}'" for table in downstream_tables)
    deletes = "\n".join(
        f"DELETE FROM {table} WHERE {delete_column} = '{run_id}';" for table in stage_tables[stage]
    )
    return f"""-- N3 intraday {stage} rollback for run_id={run_id}
-- Generated by dynamic child artifact generator.
-- Scope: only this {stage} run's scoped facts, quality rows, and run row.
DO $$
DECLARE
  v_run_id text := '{run_id}';
  v_source_run_id text := '{source_run_id}';
  v_table text;
  v_count bigint;
  v_has_source_run_id boolean;
  v_has_payload_json boolean;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id IN (v_run_id, v_source_run_id)
    AND (COALESCE(downstream_layers_touched, false) OR COALESCE(worker_started, false));
  IF v_count > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream_layers_touched or worker_started for %', v_run_id;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[{table_array}]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = v_table AND column_name = 'source_run_id'
      ) INTO v_has_source_run_id;
      IF v_has_source_run_id THEN
        EXECUTE format('SELECT count(*) FROM %I WHERE source_run_id IN ($1, $2)', v_table)
          INTO v_count USING v_run_id, v_source_run_id;
        IF v_count > 0 THEN
          RAISE EXCEPTION 'rollback blocked: downstream source_run_id refs in %. count=%', v_table, v_count;
        END IF;
      END IF;

      SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = v_table AND column_name = 'payload_json'
      ) INTO v_has_payload_json;
      IF v_has_payload_json THEN
        EXECUTE format('SELECT count(*) FROM %I WHERE payload_json::text LIKE $1', v_table)
          INTO v_count USING '%' || v_run_id || '%';
        IF v_count > 0 THEN
          RAISE EXCEPTION 'rollback blocked: downstream payload refs in %. count=%', v_table, v_count;
        END IF;
      END IF;
    END IF;
  END LOOP;
END $$;

{deletes}
DELETE FROM common_market_data_quality_item WHERE run_id = '{run_id}';
DELETE FROM common_market_data_run WHERE run_id = '{run_id}';
"""


def flatten_artifact_payloads(plan: dict[str, Any]) -> list[tuple[str, str]]:
    writes: list[tuple[str, str]] = []
    artifacts = plan["generated_artifacts"]
    payloads = plan["artifact_payloads"]
    for stage, stage_payloads in payloads.items():
        for key, content in stage_payloads.items():
            path = artifacts[stage][key]
            writes.append((path, content))
    return writes


def zero_counts(*, total: bool = False) -> dict[str, int]:
    counts = {asset_kind: 0 for asset_kind in ASSET_KINDS}
    if total:
        counts["total"] = 0
    return counts


def generator_quality_note() -> dict[str, Any]:
    return {
        "severity": "P1",
        "code": "dynamic_child_artifact_schema_only",
        "message": "Generated without DB access or market-data calls; final execute gate must refresh live source/baseline checks.",
    }


def side_effects_false() -> dict[str, bool]:
    return {
        "read_only_database_checks": False,
        "database_connected": False,
        "will_execute_sql": False,
        "writes_performed": False,
        "market_data_pulled": False,
        "event_outbox_written": False,
        "outbox_consumed_or_updated": False,
        "downstream_layers_touched": False,
        "worker_started": False,
        "old_system_touched": False,
    }


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_stage_markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        f"- stage: `{payload.get('stage')}`",
        f"- layer_role: `{payload.get('layer_role')}`",
        f"- generation_mode: `{payload.get('artifact_generation_mode', 'dynamic_intraday_child_artifact')}`",
        "- database_written: `false`",
        "- supervisor_executed: `false`",
        "- b1_c1_b2_executed: `false`",
        "- outbox_inbox_checkpoint_consumed_or_updated: `false`",
        "- n4_n5_n6_entered: `false`",
    ]
    return "\n".join(lines) + "\n"


def render_intraday_child_artifact_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# N3 Intraday B1/C1/B2 Dynamic Child Artifact Generation Report",
        "",
        f"- result: `{report.get('result')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- latest_closed_minute_hhmm: `{report.get('latest_closed_minute_hhmm')}`",
        f"- subscription_run_id: `{report.get('subscription_run_id')}`",
        f"- preload_run_id: `{report.get('preload_run_id')}`",
        "",
        "## Generated Artifacts",
    ]
    for stage, artifact_map in (report.get("generated_artifacts") or {}).items():
        lines.append(f"### {stage}")
        for name, path in artifact_map.items():
            lines.append(f"- `{name}`: `{path}`")
    lines.extend(
        [
            "",
            "## Forbidden Scope",
            "",
            "```text",
            "database_connected=false",
            "subprocess_executed=false",
            "supervisor_executed=false",
            "b1_c1_b2_executed=false",
            "outbox_inbox_checkpoint_consumed_or_updated=false",
            "n4_n5_n6_entered=false",
            "worker_started=false",
            "old_system_touched=false",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(stable_json(payload), encoding="utf-8")


def write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
