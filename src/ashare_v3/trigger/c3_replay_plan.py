"""N4 C3 MinuteBarClosed replay dry-run planner.

The planner compares an explicitly allowlisted N3-C3 MinuteBarClosed stream
with the current N4 projection matcher result. It is intentionally read-only:
it does not consume C3 outbox rows, write inbox/checkpoint records, write
trigger facts, emit N4 outbox events, or enter N5/N6.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item
from ashare_v3.events.ids import stable_hash
from ashare_v3.trigger.canonical_signal import (
    CANONICAL_SIGNAL_TYPES,
    canonical_payload_errors,
    canonicalize_trigger_candidate,
)
from ashare_v3.trigger.context_preflight import ASSET_KINDS, TARGET_CONTEXT_TABLES, normalize_text_array
from ashare_v3.trigger.projection_matcher import (
    DEFAULT_CONTEXT_RUN_ID,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_SYNTHETIC_DENYLIST,
    TRIGGER_PERIOD,
    fetch_context_rows,
    projection_30m_type_for_candidate,
    projection_matches_signal,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect


DEFAULT_ALLOWED_C3_RUN_ID = (
    "minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
DEFAULT_SOURCE_C2_RUN_ID = (
    "closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
DEFAULT_C2B_RUN_ID = (
    "closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID = "trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249"
DEFAULT_N5_ACTION_EXECUTE_RUN_ID = (
    "action_consumer_current_real_execute_20260525_"
    "trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249"
)
DEFAULT_REPLAY_RUN_ID = "trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b"
DEFAULT_CONSUMER_NAME = "n4_c3_minute_bar_closed_replay_consumer_v1"
DEFAULT_JSON_REPORT_PATH = "docs/N4_C3_replay_dry_run_report.json"
DEFAULT_MD_REPORT_PATH = "docs/N4_C3_REPLAY_DRY_RUN_REPORT.md"

SOURCE_LAYER = "N3_market_data"
SOURCE_EVENT_TYPE = "MinuteBarClosed"
SOURCE_EVENT_SCHEMA_VERSION = "v2"
TRIGGER_SOURCE_EVENT_TYPE = "MinuteBarClosed"
REPLAY_SIGNAL_TYPES = ("B_BUY_30M_VOL", "BUY_HINT", "S_SELL_30M_SHRINK", "SELL_HINT")
CANONICAL_REPLAY_SIGNAL_TYPES = ("B_BUY", "BUY_HINT", "S_SELL", "SELL_HINT")
REPLAY_CLASSIFICATIONS = ("would_match", "would_clear", "would_change", "unchanged", "missing", "not_ready")
USABLE_CLOSED_QUALITY_STATUSES = {"passed", "warning"}
SUMMARY_TABLE_CONFIG = {
    "stock": ("stock_closed_30m_summary", "stock_identity_key"),
    "index": ("index_closed_30m_summary", "index_identity_key"),
    "board": ("board_closed_30m_summary", "board_identity_key"),
}
ENRICHMENT_TABLE_CONFIG = {
    "stock": "stock_closed_30m_signal_enrichment",
    "index": "index_closed_30m_signal_enrichment",
    "board": "board_closed_30m_signal_enrichment",
}
ROW_COUNT_GUARD_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
    "common_action_event",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
)


class C3ReplayPlanError(RuntimeError):
    """Raised when a C3 replay dry-run input contract is invalid."""


def build_replay_run_id(c3_run_id: str, *, for_trade_date: str = "20260525") -> str:
    """Build the replay run id for an explicitly supplied C3 run id."""

    if c3_run_id == DEFAULT_ALLOWED_C3_RUN_ID and for_trade_date == "20260525":
        return DEFAULT_REPLAY_RUN_ID
    suffix = hashlib.sha1(c3_run_id.encode("utf-8")).hexdigest()[:12]
    return f"trigger_replay_from_c3_minute_bar_closed_{for_trade_date}__c3_{suffix}"


def run_c3_replay_dry_run(
    *,
    dsn: str,
    allowed_c3_run_id: str = DEFAULT_ALLOWED_C3_RUN_ID,
    c2b_run_id: str = DEFAULT_C2B_RUN_ID,
    replay_run_id: str | None = None,
    trigger_context_run_id: str = DEFAULT_CONTEXT_RUN_ID,
    projection_execute_run_id: str = DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
    json_report_path: str = DEFAULT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_MD_REPORT_PATH,
    sample_limit: int = 80,
) -> dict[str, Any]:
    resolved_replay_run_id = replay_run_id or build_replay_run_id(allowed_c3_run_id)
    before_counts = capture_row_counts(dsn)
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_c3_replay_dry_run",
        source_run_id=resolved_replay_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        trigger_context_rows, trigger_context_run = fetch_context_rows(dsn, trigger_context_run_id)
        projection_trigger_run = fetch_trigger_run(cur, projection_execute_run_id)
        c3_outbox_rows = fetch_c3_outbox_rows(cur, allowed_c3_run_id)
        closed_summary_rows = fetch_closed_summary_rows(cur, c3_outbox_rows)
        closed_signal_enrichment_rows = fetch_closed_signal_enrichment_rows(cur, c2b_run_id, c3_outbox_rows)
        projection_match_rows = fetch_projection_match_rows(cur, projection_execute_run_id)
        trace_only_projection_counts = fetch_projection_trace_only_counts(cur, DEFAULT_PROJECTION_RUN_ID)
    after_counts = capture_row_counts(dsn)

    report = build_c3_replay_dry_run_report_from_rows(
        allowed_c3_run_id=allowed_c3_run_id,
        c2b_run_id=c2b_run_id,
        replay_run_id=resolved_replay_run_id,
        trigger_context_run=trigger_context_run,
        projection_trigger_run=projection_trigger_run,
        context_rows=trigger_context_rows,
        c3_outbox_rows=c3_outbox_rows,
        closed_summary_rows=closed_summary_rows,
        closed_signal_enrichment_rows=closed_signal_enrichment_rows,
        projection_match_rows=projection_match_rows,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        sample_limit=sample_limit,
        trace_only_projection_summary=trace_only_projection_counts,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_c3_replay_report(report))
    return report


def filter_c3_input_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    allowed_c3_run_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        normalized = normalize_outbox_row(row)
        reject_reason = c3_reject_reason(normalized, allowed_c3_run_id=allowed_c3_run_id)
        if reject_reason:
            normalized["reject_reason"] = reject_reason
            rejected.append(normalized)
        else:
            allowed.append(normalized)
    allowed.sort(key=c3_sort_key)
    rejected.sort(key=c3_sort_key)
    return allowed, rejected


def c3_reject_reason(row: Mapping[str, Any], *, allowed_c3_run_id: str) -> str | None:
    if str(row.get("source_layer") or "") != SOURCE_LAYER:
        return "source_layer_not_n3"
    if str(row.get("event_type") or "") != SOURCE_EVENT_TYPE:
        return "event_type_not_minute_bar_closed"
    if str(row.get("source_run_id") or "") != allowed_c3_run_id:
        return "source_run_id_not_allowlisted"
    if str(row.get("status") or "") != "pending":
        return "status_not_pending"
    if str(row.get("event_schema_version") or "") != SOURCE_EVENT_SCHEMA_VERSION:
        return "event_schema_version_not_v2"
    return None


def signal_type_for_context(row: Mapping[str, Any]) -> str | None:
    direction = str(row.get("direction") or "")
    condition_key = str(row.get("condition_key") or "")
    allowed = set(normalize_text_array(row.get("allowed_signal_types")))
    if direction == "buy" and condition_key == "BUY_HINT" and "BUY_HINT" in allowed:
        return "BUY_HINT"
    if direction == "sell" and condition_key == "SELL_HINT" and "SELL_HINT" in allowed:
        return "SELL_HINT"
    if direction == "buy" and "B_BUY_30M_VOL" in allowed:
        return "B_BUY_30M_VOL"
    if direction == "sell" and "S_SELL_30M_SHRINK" in allowed:
        return "S_SELL_30M_SHRINK"
    return None


def build_c3_replay_dry_run_report_from_rows(
    *,
    allowed_c3_run_id: str,
    replay_run_id: str,
    c2b_run_id: str = DEFAULT_C2B_RUN_ID,
    trigger_context_run: Mapping[str, Any],
    projection_trigger_run: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    c3_outbox_rows: Sequence[Mapping[str, Any]],
    closed_summary_rows: Sequence[Mapping[str, Any]],
    closed_signal_enrichment_rows: Sequence[Mapping[str, Any]] = (),
    projection_match_rows: Sequence[Mapping[str, Any]],
    before_row_counts: Mapping[str, Mapping[str, Any]] | None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None,
    synthetic_denylist: Sequence[str] = DEFAULT_SYNTHETIC_DENYLIST,
    sample_limit: int = 80,
    trace_only_projection_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    accepted_c3_rows, rejected_c3_rows = filter_c3_input_rows(c3_outbox_rows, allowed_c3_run_id=allowed_c3_run_id)
    context_candidates = build_replay_context_candidates(
        context_rows=context_rows,
        trigger_context_run_id=str(trigger_context_run.get("run_id") or DEFAULT_CONTEXT_RUN_ID),
    )
    evaluations = build_replay_evaluations(
        context_candidates=context_candidates,
        c3_outbox_rows=accepted_c3_rows,
        closed_summary_rows=closed_summary_rows,
        closed_signal_enrichment_rows=closed_signal_enrichment_rows,
        projection_match_rows=projection_match_rows,
        projection_trigger_run_id=str(projection_trigger_run.get("run_id") or DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID),
    )
    classification_summary = summarize_by_classification(evaluations)
    replay_diff_summary = summarize_replay_diff(evaluations)
    signal_summary = summarize_by_signal(evaluations)
    asset_summary = summarize_by_asset(evaluations)
    reason_summary = count_by(evaluations, "reason")
    closed_signal_summary = summarize_closed_signal_status(evaluations, closed_signal_enrichment_rows)
    boundary_confirmation = build_boundary_confirmation()
    quality_items = build_replay_quality_items(
        allowed_c3_run_id=allowed_c3_run_id,
        replay_run_id=replay_run_id,
        trigger_context_run=trigger_context_run,
        projection_trigger_run=projection_trigger_run,
        context_candidates=context_candidates,
        accepted_c3_rows=accepted_c3_rows,
        rejected_c3_rows=rejected_c3_rows,
        evaluations=evaluations,
        before_row_counts=before_row_counts,
        after_row_counts=after_row_counts,
        synthetic_denylist=synthetic_denylist,
    )
    quality_counts = count_quality_severities(quality_items)
    return {
        "stage": "N4-C3-MinuteBarClosed-replay-dry-run-runner",
        "result": "DRY_RUN_PASS" if quality_counts["P0"] == 0 else "DRY_RUN_BLOCKED",
        "layer_role": "N4_trigger",
        "mode": "c3_replay_dry_run",
        "replay_run_id": replay_run_id,
        "allowed_c3_run_id": allowed_c3_run_id,
        "c2b_run_id": c2b_run_id,
        "trigger_context_run_id": trigger_context_run.get("run_id") or DEFAULT_CONTEXT_RUN_ID,
        "source_condition_run_id": trigger_context_run.get("source_condition_run_id"),
        "source_subscription_run_id": derive_payload_field(accepted_c3_rows, "source_subscription_run_id")
        or DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
        "source_c2_run_id": derive_payload_field(accepted_c3_rows, "c2_run_id") or DEFAULT_SOURCE_C2_RUN_ID,
        "original_n4_projection_execute_run_id": projection_trigger_run.get("run_id")
        or DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
        "original_n5_action_execute_run_id": DEFAULT_N5_ACTION_EXECUTE_RUN_ID,
        "generated_at": utc_now_iso(),
        "consumer_name": DEFAULT_CONSUMER_NAME,
        "input_boundary": {
            "explicit_allowlist_required": True,
            "allowed_filter": {
                "source_layer": SOURCE_LAYER,
                "event_type": SOURCE_EVENT_TYPE,
                "source_run_id": allowed_c3_run_id,
                "status": "pending",
                "event_schema_version": SOURCE_EVENT_SCHEMA_VERSION,
            },
            "raw_c3_outbox_row_count": len(c3_outbox_rows),
            "accepted_c3_outbox_row_count": len(accepted_c3_rows),
            "rejected_c3_outbox_row_count": len(rejected_c3_rows),
            "rejected_reason_summary": count_by(rejected_c3_rows, "reject_reason"),
            "forbidden_consumption_inputs": [
                "B1 MarketSnapshotUpdated outbox",
                "B2 realtime projection facts",
                "old synthetic N4 outbox",
                "N5 outbox",
                "non-allowlisted C3 outbox",
                "raw minute tables",
                "external market adapters",
                "old system",
            ],
        },
        "comparison_materials": {
            "c3_minute_bar_closed_payloads": "read_only",
            "closed_30m_summary_rows": len(closed_summary_rows),
            "closed_signal_enrichment_rows": len(closed_signal_enrichment_rows),
            "current_trigger_context_snapshot_rows": len(context_rows),
            "replay_context_candidate_count": len(context_candidates),
            "original_projection_match_rows": len(projection_match_rows),
            "b2_projection_facts_usage": "trace_only",
            "b2_projection_trace_only_summary": dict(trace_only_projection_summary or {}),
        },
        "classification_summary": classification_summary,
        "replay_diff_summary": replay_diff_summary,
        "closed_signal_summary": closed_signal_summary,
        "signal_summary": signal_summary,
        "asset_summary": asset_summary,
        "reason_summary": reason_summary,
        "sample_diffs": evaluations[:sample_limit],
        "row_count_guard": {
            "before": before_row_counts or {},
            "after": after_row_counts or {},
            "unchanged": before_row_counts == after_row_counts,
        },
        "boundary_confirmation": boundary_confirmation,
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "P0/P1/P2": f"{quality_counts['P0']}/{quality_counts['P1']}/{quality_counts['P2']}",
        "rollback_strategy": {
            "this_dry_run": "No DB rollback required; delete generated dry-run report files if discarded.",
            "future_replay_execute": (
                "Rollback must delete only replay_run_id-scoped N4 replay inbox/checkpoint, trigger facts, "
                "quality rows, replay outbox if a future contract allows it, and common_trigger_run. It must not "
                "touch the original N4 projection passed run, N5 passed run, N3 C3 outbox, B1/B2/C2/C3 facts, "
                "or synthetic outbox."
            ),
        },
        "next_gate": {
            "allow_n4_c3_replay_dry_run_review": quality_counts["P0"] == 0,
            "allow_replay_runner_execute": False,
            "execute_blocker": "This stage is dry-run implementation only; replay execute/event schema needs a separate contract.",
        },
        "storm_guard": {
            "no_worker": True,
            "no_automatic_n5_replay": True,
            "explicit_c3_run_id_allowlist": True,
            "distinct_consumer_name": DEFAULT_CONSUMER_NAME,
            "no_standard_trigger_matched_outbox_emission": True,
        },
    }


def build_replay_context_candidates(
    *,
    context_rows: Sequence[Mapping[str, Any]],
    trigger_context_run_id: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in context_rows:
        if row.get("run_id") != trigger_context_run_id:
            continue
        legacy_signal_type = signal_type_for_context(row)
        if legacy_signal_type not in REPLAY_SIGNAL_TYPES:
            continue
        mapping = canonicalize_trigger_candidate(
            str(row.get("condition_key") or ""),
            candidate_signal_type=legacy_signal_type,
        )
        normalized = normalize_mapping(row)
        normalized["signal_type"] = mapping.signal_type
        normalized["action_mark"] = mapping.action_mark
        normalized["original_condition_key"] = mapping.original_condition_key
        normalized["legacy_signal_type"] = legacy_signal_type
        normalized["trigger_period"] = TRIGGER_PERIOD
        candidates.append(normalized)
    candidates.sort(key=lambda row: (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""), str(row.get("direction") or ""), str(row.get("condition_key") or "")))
    return candidates


def derive_payload_field(rows: Sequence[Mapping[str, Any]], field_name: str) -> Any:
    for row in rows:
        payload = extract_payload(row)
        value = payload.get(field_name)
        if value:
            return value
    return None


def build_replay_evaluations(
    *,
    context_candidates: Sequence[Mapping[str, Any]],
    c3_outbox_rows: Sequence[Mapping[str, Any]],
    closed_summary_rows: Sequence[Mapping[str, Any]],
    closed_signal_enrichment_rows: Sequence[Mapping[str, Any]],
    projection_match_rows: Sequence[Mapping[str, Any]],
    projection_trigger_run_id: str,
) -> list[dict[str, Any]]:
    c3_events_by_identity = index_c3_events(c3_outbox_rows)
    closed_summary_by_key = index_closed_summaries(closed_summary_rows)
    enrichment_by_key = index_closed_signal_enrichment(closed_signal_enrichment_rows)
    projection_by_grain = index_projection_matches(projection_match_rows, projection_trigger_run_id=projection_trigger_run_id)
    output: list[dict[str, Any]] = []
    for context in context_candidates:
        identity_key = str(context.get("identity_key") or "")
        asset_kind = str(context.get("asset_kind") or "")
        direction = str(context.get("direction") or "")
        signal_type = str(context.get("signal_type") or "")
        legacy_signal_type = str(context.get("legacy_signal_type") or signal_type)
        condition_key = str(context.get("condition_key") or "")
        buckets = collect_candidate_buckets(
            asset_kind=asset_kind,
            identity_key=identity_key,
            signal_type=legacy_signal_type,
            condition_key=condition_key,
            c3_events_by_identity=c3_events_by_identity,
            projection_by_grain=projection_by_grain,
        )
        if not buckets:
            buckets = [None]
        for bucket in buckets:
            c3_event = latest_c3_event_for_bucket(c3_events_by_identity, asset_kind, identity_key, bucket)
            summary = closed_summary_for_event(
                event=c3_event,
                bucket=bucket,
                asset_kind=asset_kind,
                identity_key=identity_key,
                closed_summary_by_key=closed_summary_by_key,
            )
            enrichment = enrichment_for_event(
                event=c3_event,
                bucket=bucket,
                asset_kind=asset_kind,
                identity_key=identity_key,
                enrichment_by_key=enrichment_by_key,
            )
            projection = projection_by_grain.get(
                (asset_kind, identity_key, direction, legacy_signal_type, condition_key, TRIGGER_PERIOD, bucket)
            )
            output.append(
                evaluate_replay_candidate(
                    context=context,
                    c3_event=c3_event,
                    closed_summary=summary,
                    closed_signal_enrichment=enrichment,
                    projection_match=projection,
                    normalized_bucket=bucket,
                )
            )
    output.sort(key=lambda row: (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""), str(row.get("signal_type") or ""), str(row.get("trigger_bucket") or "")))
    return output


def evaluate_replay_candidate(
    *,
    context: Mapping[str, Any],
    c3_event: Mapping[str, Any] | None,
    closed_summary: Mapping[str, Any] | None,
    closed_signal_enrichment: Mapping[str, Any] | None,
    projection_match: Mapping[str, Any] | None,
    normalized_bucket: str | None,
) -> dict[str, Any]:
    signal_type = str(context.get("signal_type") or "")
    legacy_signal_type = str(context.get("legacy_signal_type") or signal_type)
    projection_matched = projection_row_is_matched(projection_match)
    projection_signal_status = projection_signal_status_from_match(projection_match or {})
    projection_quality_status = str((projection_match or {}).get("data_quality_status") or "missing")

    if c3_event is None:
        return replay_eval(
            context=context,
            c3_event={},
            closed_summary={},
            closed_signal_enrichment={},
            projection_match=projection_match,
            trigger_bucket=normalized_bucket,
            classification="missing",
            diff_case="replay_blocked",
            reason="c3_event_missing",
            projection_matched=projection_matched,
            closed_matched=False,
            projection_signal_status=projection_signal_status,
            closed_signal_status="missing",
            projection_quality_status=projection_quality_status,
            closed_quality_status="missing",
        )

    if closed_summary is None:
        return replay_eval(
            context=context,
            c3_event=c3_event,
            closed_summary={},
            closed_signal_enrichment=closed_signal_enrichment or {},
            projection_match=projection_match,
            trigger_bucket=normalized_bucket,
            classification="missing",
            diff_case="replay_blocked",
            reason="closed_summary_missing",
            projection_matched=projection_matched,
            closed_matched=False,
            projection_signal_status=projection_signal_status,
            closed_signal_status="missing",
            projection_quality_status=projection_quality_status,
            closed_quality_status="missing",
        )

    closed_status = str(closed_summary.get("closed_status") or (c3_event.get("payload_json") or {}).get("closed_status") or "")
    enrichment = closed_signal_enrichment or {}
    closed_quality_status = str(
        enrichment.get("closed_signal_quality_status")
        or closed_summary.get("quality_status")
        or (c3_event.get("payload_json") or {}).get("quality_status")
        or "missing"
    )
    closed_signal_status = closed_signal_status_from_enrichment(enrichment) or closed_signal_status_from_summary(closed_summary)
    if closed_status != "closed":
        return replay_eval(
            context=context,
            c3_event=c3_event,
            closed_summary=closed_summary,
            closed_signal_enrichment=enrichment,
            projection_match=projection_match,
            trigger_bucket=normalized_bucket,
            classification="not_ready",
            diff_case="replay_blocked",
            reason="closed_status_not_closed",
            projection_matched=projection_matched,
            closed_matched=False,
            projection_signal_status=projection_signal_status,
            closed_signal_status=closed_signal_status or "missing",
            projection_quality_status=projection_quality_status,
            closed_quality_status=closed_quality_status,
        )
    if closed_quality_status not in USABLE_CLOSED_QUALITY_STATUSES:
        return replay_eval(
            context=context,
            c3_event=c3_event,
            closed_summary=closed_summary,
            closed_signal_enrichment=enrichment,
            projection_match=projection_match,
            trigger_bucket=normalized_bucket,
            classification="not_ready",
            diff_case="replay_blocked",
            reason="closed_quality_not_usable",
            projection_matched=projection_matched,
            closed_matched=False,
            projection_signal_status=projection_signal_status,
            closed_signal_status=closed_signal_status or "missing",
            projection_quality_status=projection_quality_status,
            closed_quality_status=closed_quality_status,
        )
    if not closed_signal_status:
        return replay_eval(
            context=context,
            c3_event=c3_event,
            closed_summary=closed_summary,
            closed_signal_enrichment=enrichment,
            projection_match=projection_match,
            trigger_bucket=normalized_bucket,
            classification="not_ready",
            diff_case="replay_blocked",
            reason="closed_signal_status_missing",
            projection_matched=projection_matched,
            closed_matched=False,
            projection_signal_status=projection_signal_status,
            closed_signal_status="missing",
            projection_quality_status=projection_quality_status,
            closed_quality_status=closed_quality_status,
        )

    closed_matched = projection_matches_signal(legacy_signal_type, closed_signal_status)
    if closed_matched and not projection_matched:
        classification = "would_match"
        diff_case = "projection_not_matched_but_closed_matched"
        reason = "projection_match_missing"
    elif projection_matched and not closed_matched:
        classification = "would_clear"
        diff_case = "projection_matched_but_closed_not_matched"
        reason = "projection_match_present_closed_not_matched"
    elif projection_matched and closed_matched:
        changed = projection_signal_status != closed_signal_status or not qualities_compatible(
            projection_quality_status, closed_quality_status
        )
        classification = "would_change" if changed else "unchanged"
        diff_case = "both_matched_but_quality_changed" if changed else "unchanged"
        reason = "quality_changed" if changed else "unchanged_confirmed"
    else:
        classification = "unchanged"
        diff_case = "unchanged"
        reason = "both_unmatched_confirmed"

    return replay_eval(
        context=context,
        c3_event=c3_event,
        closed_summary=closed_summary,
        closed_signal_enrichment=enrichment,
        projection_match=projection_match,
        trigger_bucket=normalized_bucket,
        classification=classification,
        diff_case=diff_case,
        reason=reason,
        projection_matched=projection_matched,
        closed_matched=closed_matched,
        projection_signal_status=projection_signal_status,
        closed_signal_status=closed_signal_status,
        projection_quality_status=projection_quality_status,
        closed_quality_status=closed_quality_status,
    )


def replay_eval(
    *,
    context: Mapping[str, Any],
    c3_event: Mapping[str, Any],
    closed_summary: Mapping[str, Any],
    closed_signal_enrichment: Mapping[str, Any],
    projection_match: Mapping[str, Any] | None,
    trigger_bucket: str | None,
    classification: str,
    diff_case: str,
    reason: str,
    projection_matched: bool,
    closed_matched: bool,
    projection_signal_status: str,
    closed_signal_status: str,
    projection_quality_status: str,
    closed_quality_status: str,
) -> dict[str, Any]:
    payload = c3_event.get("payload_json") if isinstance(c3_event, Mapping) else {}
    payload = payload if isinstance(payload, Mapping) else {}
    legacy_signal_type = str(context.get("legacy_signal_type") or context.get("signal_type") or "")
    projection_type = "none"
    if closed_matched:
        projection_type = projection_30m_type_for_candidate(legacy_signal_type, closed_signal_status)
    elif projection_matched:
        projection_type = projection_30m_type_for_candidate(legacy_signal_type, projection_signal_status)
    mapping = canonicalize_trigger_candidate(
        str(context.get("condition_key") or ""),
        candidate_signal_type=legacy_signal_type,
        projection_30m_type=projection_type,
    )
    plan_key = "|".join(
        [
            str(context.get("asset_kind") or ""),
            str(context.get("identity_key") or ""),
            str(context.get("direction") or ""),
            mapping.signal_type,
            mapping.action_mark,
            legacy_signal_type,
            str(context.get("condition_key") or ""),
            str(trigger_bucket or "bucket_missing"),
            classification,
            reason,
        ]
    )
    return {
        "plan_id": stable_hash(plan_key, length=32),
        "classification": classification,
        "diff_case": diff_case,
        "reason": reason,
        "asset_kind": context.get("asset_kind"),
        "identity_key": context.get("identity_key"),
        "direction": context.get("direction"),
        "signal_type": mapping.signal_type,
        "action_mark": mapping.action_mark,
        "condition_key": context.get("condition_key"),
        "original_condition_key": mapping.original_condition_key,
        "legacy_signal_type": legacy_signal_type,
        "match_basis": "closed_30m_replay",
        "trigger_period": TRIGGER_PERIOD,
        "trigger_bucket": trigger_bucket or "bucket_missing",
        "context_snapshot_id": context.get("trigger_context_id"),
        "context_run_id": context.get("run_id"),
        "source_condition_run_id": context.get("source_condition_run_id"),
        "source_condition_pool_id": context.get("source_condition_pool_id"),
        "source_condition_basis_id": context.get("source_condition_basis_id"),
        "source_market_subscription_id": context.get("source_market_subscription_id"),
        "context_hash": context.get("context_hash"),
        "projection_matched": projection_matched,
        "closed_matched": closed_matched,
        "projection_signal_status": projection_signal_status,
        "closed_signal_status": closed_signal_status,
        "projection_quality_status": projection_quality_status,
        "closed_quality_status": closed_quality_status,
        "source_c3_event_id": c3_event.get("event_id") if isinstance(c3_event, Mapping) else None,
        "source_c3_outbox_id": c3_event.get("outbox_id") if isinstance(c3_event, Mapping) else None,
        "closed_30m_summary_id": closed_summary.get("summary_id") or payload.get("summary_id") or payload.get("closed_30m_summary_id"),
        "closed_signal_enrichment_id": closed_signal_enrichment.get("enrichment_id"),
        "closed_signal_enrichment_run_id": closed_signal_enrichment.get("c2b_run_id"),
        "closed_bucket_id": closed_summary.get("bucket_id") or payload.get("bucket_id"),
        "projection_trigger_match_id": (projection_match or {}).get("trigger_match_id"),
        "projection_source_event_id": (projection_match or {}).get("source_event_id"),
        "projection_output_event_type": (projection_match or {}).get("output_event_type"),
        "value_trace": {
            "closed_open": closed_summary.get("open"),
            "closed_close": closed_summary.get("close"),
            "closed_amount": closed_summary.get("amount"),
            "closed_current_window_amount": closed_signal_enrichment.get("current_window_amount"),
            "closed_baseline_window_amount": closed_signal_enrichment.get("baseline_window_amount"),
            "closed_amount_ratio": closed_signal_enrichment.get("closed_amount_ratio"),
            "closed_price_direction_status": closed_signal_enrichment.get("closed_price_direction_status"),
            "projection_trigger_price": (projection_match or {}).get("trigger_price"),
        },
        "period_trigger_baseline_trace_present": bool(
            ((context.get("raw_json") or {}) if isinstance(context.get("raw_json"), Mapping) else {}).get(
                "period_trigger_baseline_json"
            )
        ),
        "trace_only_b2_projection_fact_used_for_classification": False,
    }


def collect_candidate_buckets(
    *,
    asset_kind: str,
    identity_key: str,
    signal_type: str,
    condition_key: str,
    c3_events_by_identity: Mapping[tuple[str, str], list[Mapping[str, Any]]],
    projection_by_grain: Mapping[tuple[str, str, str, str, str, str, str | None], Mapping[str, Any]],
) -> list[str | None]:
    buckets: set[str | None] = set()
    for row in c3_events_by_identity.get((asset_kind, identity_key), []):
        buckets.add(normalize_bucket_id(extract_payload(row).get("bucket_id"), trade_date=str(row.get("trade_date") or "")))
    for key in projection_by_grain:
        key_asset, key_identity, _direction, key_signal, key_condition, _period, bucket = key
        if key_asset == asset_kind and key_identity == identity_key and key_signal == signal_type and key_condition == condition_key:
            buckets.add(bucket)
    return sorted(buckets, key=lambda value: str(value or ""))


def index_c3_events(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    output: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        normalized = normalize_outbox_row(row)
        key = (str(normalized.get("asset_kind") or ""), str(normalized.get("identity_key") or ""))
        output.setdefault(key, []).append(normalized)
    for entries in output.values():
        entries.sort(key=c3_sort_key)
    return output


def index_closed_summaries(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[Any, ...], dict[str, Any]]:
    output: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        normalized = normalize_closed_summary_row(row)
        asset_kind = str(normalized.get("asset_kind") or "")
        identity_key = str(normalized.get("identity_key") or "")
        summary_id = normalized.get("summary_id")
        bucket_id = normalize_bucket_id(normalized.get("bucket_id"), trade_date=str(normalized.get("trade_date") or ""))
        if summary_id is not None:
            output[(asset_kind, "summary_id", str(summary_id))] = normalized
        if identity_key and bucket_id:
            output[(asset_kind, identity_key, bucket_id)] = normalized
    return output


def index_closed_signal_enrichment(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[Any, ...], dict[str, Any]]:
    output: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        normalized = normalize_closed_signal_enrichment_row(row)
        asset_kind = str(normalized.get("asset_kind") or "")
        identity_key = str(normalized.get("identity_key") or "")
        summary_id = normalized.get("current_summary_id")
        bucket_id = normalize_bucket_id(normalized.get("bucket_id"), trade_date=str(normalized.get("trade_date") or ""))
        if summary_id is not None:
            output[(asset_kind, "summary_id", str(summary_id))] = normalized
        if identity_key and bucket_id:
            output[(asset_kind, identity_key, bucket_id)] = normalized
    return output


def index_projection_matches(
    rows: Sequence[Mapping[str, Any]],
    *,
    projection_trigger_run_id: str,
) -> dict[tuple[str, str, str, str, str, str, str | None], dict[str, Any]]:
    output: dict[tuple[str, str, str, str, str, str, str | None], dict[str, Any]] = {}
    for row in rows:
        normalized = normalize_mapping(row)
        if normalized.get("run_id") != projection_trigger_run_id:
            continue
        signal_type = str(normalized.get("signal_type") or "")
        raw_json = normalized.get("raw_json") if isinstance(normalized.get("raw_json"), Mapping) else {}
        raw_plan = raw_json.get("plan") if isinstance(raw_json, Mapping) and isinstance(raw_json.get("plan"), Mapping) else {}
        legacy_signal_type = str(
            raw_plan.get("legacy_signal_type")
            or raw_json.get("legacy_signal_type")
            or normalized.get("legacy_signal_type")
            or signal_type
        )
        if legacy_signal_type not in REPLAY_SIGNAL_TYPES:
            continue
        bucket = normalize_bucket_id(
            normalized.get("trigger_bucket") or raw_json.get("projection_window_id"),
            trade_date=str(normalized.get("for_trade_date") or ""),
        )
        normalized["legacy_signal_type"] = legacy_signal_type
        normalized["canonical_signal_type"] = signal_type
        key = (
            str(normalized.get("asset_kind") or ""),
            str(normalized.get("identity_key") or ""),
            str(normalized.get("direction") or ""),
            legacy_signal_type,
            str(normalized.get("condition_key") or ""),
            str(normalized.get("trigger_period") or TRIGGER_PERIOD),
            bucket,
        )
        output.setdefault(key, normalized)
    return output


def latest_c3_event_for_bucket(
    c3_events_by_identity: Mapping[tuple[str, str], list[Mapping[str, Any]]],
    asset_kind: str,
    identity_key: str,
    bucket: str | None,
) -> Mapping[str, Any] | None:
    events = c3_events_by_identity.get((asset_kind, identity_key), [])
    if bucket is None:
        return events[-1] if events else None
    for row in reversed(events):
        payload = extract_payload(row)
        row_bucket = normalize_bucket_id(payload.get("bucket_id"), trade_date=str(row.get("trade_date") or ""))
        if row_bucket == bucket:
            return row
    return None


def closed_summary_for_event(
    *,
    event: Mapping[str, Any] | None,
    bucket: str | None,
    asset_kind: str,
    identity_key: str,
    closed_summary_by_key: Mapping[tuple[Any, ...], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if event is None:
        return None
    payload = extract_payload(event)
    summary_id = payload.get("closed_30m_summary_id") or payload.get("summary_id")
    if summary_id is not None:
        summary = closed_summary_by_key.get((asset_kind, "summary_id", str(summary_id)))
        if summary:
            return summary
    if bucket is not None:
        return closed_summary_by_key.get((asset_kind, identity_key, bucket))
    return None


def enrichment_for_event(
    *,
    event: Mapping[str, Any] | None,
    bucket: str | None,
    asset_kind: str,
    identity_key: str,
    enrichment_by_key: Mapping[tuple[Any, ...], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if event is None:
        return None
    payload = extract_payload(event)
    summary_id = payload.get("closed_30m_summary_id") or payload.get("summary_id")
    if summary_id is not None:
        enrichment = enrichment_by_key.get((asset_kind, "summary_id", str(summary_id)))
        if enrichment:
            return enrichment
    if bucket is not None:
        return enrichment_by_key.get((asset_kind, identity_key, bucket))
    return None


def normalize_bucket_id(value: Any, *, trade_date: str = "20260525") -> str | None:
    text = str(value or "")
    if not text:
        return None
    if text.startswith(f"{trade_date}_"):
        return text
    parts = text.split("_")
    if len(parts) == 2 and all(part.isdigit() and len(part) == 4 for part in parts):
        start, end = parts
        start_hour = int(start[:2])
        start_minute = int(start[2:])
        if start_minute > 0:
            start_minute -= 1
        start_key = f"{start_hour:02d}{start_minute:02d}"
        return f"{trade_date}_{start_key}_{end}"
    return text


def closed_signal_status_from_summary(summary: Mapping[str, Any]) -> str | None:
    raw = summary.get("raw_json") if isinstance(summary.get("raw_json"), Mapping) else {}
    for key in (
        "closed_market_shape_status",
        "market_shape_status",
        "closed_signal_status",
        "projection_signal_status",
    ):
        value = summary.get(key) or raw.get(key)
        if value:
            return str(value)
    return None


def closed_signal_status_from_enrichment(enrichment: Mapping[str, Any]) -> str | None:
    value = enrichment.get("closed_signal_status") or enrichment.get("closed_market_shape_status")
    if value and str(value) != "unknown":
        return str(value)
    return None


def projection_signal_status_from_match(row: Mapping[str, Any]) -> str:
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), Mapping) else {}
    raw_plan = raw.get("plan") if isinstance(raw, Mapping) and isinstance(raw.get("plan"), Mapping) else {}
    projection_trace = raw.get("projection_trace") if isinstance(raw, Mapping) and isinstance(raw.get("projection_trace"), Mapping) else {}
    return str(
        row.get("projection_signal_status")
        or raw_plan.get("projection_signal_status")
        or raw.get("projection_signal_status")
        or projection_trace.get("raw_json_projection_signal_status")
        or "missing"
    )


def projection_row_is_matched(row: Mapping[str, Any] | None) -> bool:
    return bool(row) and str(row.get("output_event_type") or "") == "TriggerMatched"


def qualities_compatible(projection_quality_status: str, closed_quality_status: str) -> bool:
    return projection_quality_status == "passed" and closed_quality_status == "passed"


def normalize_outbox_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["payload_json"] = parse_jsonish(output.get("payload_json") or {})
    output["status"] = output.get("status") or "pending"
    output["event_schema_version"] = output.get("event_schema_version") or SOURCE_EVENT_SCHEMA_VERSION
    return output


def normalize_closed_summary_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["raw_json"] = parse_jsonish(output.get("raw_json") or {})
    output["replay_diff_json"] = parse_jsonish(output.get("replay_diff_json") or {})
    if "identity_key" not in output or not output.get("identity_key"):
        asset_kind = str(output.get("asset_kind") or "")
        identity_column = f"{asset_kind}_identity_key"
        output["identity_key"] = output.get(identity_column)
    return output


def normalize_closed_signal_enrichment_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["closed_signal_basis_json"] = parse_jsonish(output.get("closed_signal_basis_json") or {})
    output["baseline_trace_json"] = parse_jsonish(output.get("baseline_trace_json") or {})
    output["raw_json"] = parse_jsonish(output.get("raw_json") or {})
    return output


def extract_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json") or {}
    return parse_jsonish(payload) if not isinstance(payload, Mapping) else dict(payload)


def parse_jsonish(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def c3_sort_key(row: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (
        str(row.get("partition_key") or row.get("identity_key") or ""),
        normalize_event_time_for_sort(row.get("event_time")),
        int(row.get("outbox_id") or 0),
        str(row.get("event_id") or ""),
    )


def normalize_event_time_for_sort(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def summarize_by_classification(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_count": len(evaluations),
        "by_classification": count_by(evaluations, "classification"),
    }


def summarize_replay_diff(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("diff_case") or "") for row in evaluations)
    return {
        "projection_matched_but_closed_not_matched": counts.get("projection_matched_but_closed_not_matched", 0),
        "projection_not_matched_but_closed_matched": counts.get("projection_not_matched_but_closed_matched", 0),
        "both_matched_but_quality_changed": counts.get("both_matched_but_quality_changed", 0),
        "unchanged": counts.get("unchanged", 0),
        "replay_blocked": counts.get("replay_blocked", 0),
    }


def summarize_by_signal(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "by_signal_type": count_by(evaluations, "signal_type"),
        "by_signal_type_and_classification": count_by_pair(evaluations, "signal_type", "classification"),
        "by_action_mark": count_by(evaluations, "action_mark"),
        "by_action_mark_and_classification": count_by_pair(evaluations, "action_mark", "classification"),
        "by_legacy_signal_type": count_by(evaluations, "legacy_signal_type"),
        "canonical_scope": list(CANONICAL_REPLAY_SIGNAL_TYPES),
        "legacy_condition_signal_scope": list(REPLAY_SIGNAL_TYPES),
    }


def summarize_by_asset(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "by_asset_kind": count_by(evaluations, "asset_kind"),
        "by_asset_kind_and_classification": count_by_pair(evaluations, "asset_kind", "classification"),
    }


def summarize_closed_signal_status(
    evaluations: Sequence[Mapping[str, Any]],
    closed_signal_enrichment_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    missing_count = sum(1 for row in evaluations if row.get("reason") == "closed_signal_status_missing")
    return {
        "closed_signal_status_missing_count": missing_count,
        "closed_signal_status_distribution": count_by(evaluations, "closed_signal_status"),
        "closed_signal_quality_distribution": count_by(evaluations, "closed_quality_status"),
        "enrichment_row_count": len(closed_signal_enrichment_rows),
        "enrichment_signal_distribution": count_by(closed_signal_enrichment_rows, "closed_signal_status"),
        "enrichment_quality_distribution": count_by(closed_signal_enrichment_rows, "closed_signal_quality_status"),
    }


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def count_by_pair(rows: Sequence[Mapping[str, Any]], key_a: str, key_b: str) -> dict[str, int]:
    counter = Counter(f"{row.get(key_a) or ''}:{row.get(key_b) or ''}" for row in rows)
    return dict(sorted(counter.items()))


def build_boundary_confirmation() -> dict[str, bool]:
    return {
        "database_written": False,
        "c3_outbox_consumed": False,
        "common_event_inbox_written": False,
        "checkpoint_written": False,
        "trigger_match_written": False,
        "trigger_state_written": False,
        "n4_outbox_written": False,
        "n5_n6_touched": False,
        "worker_started": False,
        "market_data_pulled": False,
        "old_system_touched": False,
        "standard_trigger_matched_outbox_emitted": False,
    }


def build_replay_quality_items(
    *,
    allowed_c3_run_id: str,
    replay_run_id: str,
    trigger_context_run: Mapping[str, Any],
    projection_trigger_run: Mapping[str, Any],
    context_candidates: Sequence[Mapping[str, Any]],
    accepted_c3_rows: Sequence[Mapping[str, Any]],
    rejected_c3_rows: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    before_row_counts: Mapping[str, Mapping[str, Any]] | None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None,
    synthetic_denylist: Sequence[str],
) -> list[dict[str, Any]]:
    row_counts_unchanged = before_row_counts == after_row_counts
    trigger_run_id = str(trigger_context_run.get("run_id") or "")
    projection_run_id = str(projection_trigger_run.get("run_id") or "")
    invalid_signals = sorted(
        {str(row.get("signal_type") or "") for row in evaluations if row.get("signal_type") not in CANONICAL_SIGNAL_TYPES}
    )
    invalid_payloads = [row for row in evaluations if canonical_payload_errors(row)]
    not_ready_count = sum(1 for row in evaluations if row.get("classification") == "not_ready")
    missing_count = sum(1 for row in evaluations if row.get("classification") == "missing")
    return [
        quality_item(
            "P0",
            "passed" if allowed_c3_run_id == DEFAULT_ALLOWED_C3_RUN_ID else "failed",
            "n4_c3_replay_allowlisted_run_id",
            "C3 replay dry-run must use the explicitly allowlisted C3 run id",
            expected=DEFAULT_ALLOWED_C3_RUN_ID,
            actual=allowed_c3_run_id,
        ),
        quality_item(
            "P0",
            "passed" if replay_run_id and replay_run_id != trigger_run_id and replay_run_id != projection_run_id else "failed",
            "n4_c3_replay_run_id_distinct",
            "Replay run id must be distinct from context and original projection execute run ids",
            expected="distinct replay run id",
            actual=replay_run_id,
        ),
        quality_item(
            "P0",
            "passed" if trigger_run_id == DEFAULT_CONTEXT_RUN_ID and trigger_context_run.get("status") == "passed" else "failed",
            "n4_c3_replay_context_run_ready",
            "C3 replay dry-run must bind the current passed N4 trigger context run",
            expected=DEFAULT_CONTEXT_RUN_ID,
            actual=f"{trigger_run_id}:{trigger_context_run.get('status')}",
        ),
        quality_item(
            "P0",
            "passed" if trigger_run_id not in set(synthetic_denylist) else "failed",
            "n4_c3_replay_context_not_synthetic",
            "C3 replay dry-run must exclude old synthetic context runs",
            expected="not synthetic denylisted",
            actual=trigger_run_id,
        ),
        quality_item(
            "P0",
            "passed" if projection_run_id == DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID and projection_trigger_run.get("status") == "passed" else "failed",
            "n4_c3_replay_projection_result_ready",
            "C3 replay dry-run must compare against the current passed N4 projection matcher execute run",
            expected=DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
            actual=f"{projection_run_id}:{projection_trigger_run.get('status')}",
        ),
        quality_item(
            "P0",
            "passed" if accepted_c3_rows else "failed",
            "n4_c3_replay_c3_input_available",
            "C3 replay dry-run must have allowlisted pending MinuteBarClosed input rows",
            expected=">0",
            actual=str(len(accepted_c3_rows)),
        ),
        quality_item(
            "P0",
            "passed" if not rejected_c3_rows else "failed",
            "n4_c3_replay_no_forbidden_c3_inputs",
            "C3 replay dry-run input set must not include non-allowlisted or forbidden event rows",
            expected="0 rejected rows",
            actual=str(len(rejected_c3_rows)),
        ),
        quality_item(
            "P0",
            "passed" if context_candidates else "failed",
            "n4_c3_replay_context_candidates_available",
            "C3 replay dry-run must derive replay candidates from local N4 context",
            expected=">0",
            actual=str(len(context_candidates)),
        ),
        quality_item(
            "P0",
            "passed" if not invalid_signals else "failed",
            "n4_c3_replay_signal_scope_only_four",
            "C3 replay dry-run output must expose only the four canonical runtime signal types",
            expected="B_BUY,BUY_HINT,S_SELL,SELL_HINT",
            actual=",".join(invalid_signals),
        ),
        quality_item(
            "P0",
            "passed" if not invalid_payloads else "failed",
            "n4_c3_replay_canonical_payload_alignment",
            "Replay dry-run payloads must expose canonical signal_type/action_mark and preserve original_condition_key",
            expected="canonical_payload_errors=0",
            actual=str(len(invalid_payloads)),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n4_c3_replay_no_database_writes",
            "C3 replay dry-run must not change guarded DB row counts",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item("P0", "passed", "n4_c3_replay_no_n4_outbox", "C3 replay dry-run does not emit N4 outbox events"),
        quality_item("P0", "passed", "n4_c3_replay_no_n5_n6", "C3 replay dry-run does not enter N5/N6"),
        quality_item("P0", "passed", "n4_c3_replay_no_worker", "C3 replay dry-run is run-once planning only; no worker is started"),
        quality_item(
            "P1",
            "warning" if not_ready_count else "passed",
            "n4_c3_replay_not_ready_visible",
            "Rows with C3 input but missing unusable closed signal/status remain visible as not_ready",
            expected="visible if present",
            actual=str(not_ready_count),
        ),
        quality_item(
            "P1",
            "warning" if missing_count else "passed",
            "n4_c3_replay_missing_visible",
            "Rows missing comparable C3 event or closed summary trace remain visible as missing",
            expected="visible if present",
            actual=str(missing_count),
        ),
    ]


def fetch_trigger_run(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, source_market_data_run_id,
               for_trade_date, source_trade_date, prev_trade_date,
               mode, status, context_snapshot_row_count,
               trigger_state_row_count, trigger_match_row_count, trigger_event_outbox_count,
               raw_json
        FROM common_trigger_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    return normalize_mapping(cur.fetchone() or {})


def fetch_c3_outbox_rows(cur: psycopg.Cursor[dict[str, Any]], allowed_c3_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT outbox_id, event_id, event_type, event_schema_version, trade_date,
               asset_kind, identity_key, event_time, source_layer, source_run_id,
               dedup_key, partition_key, payload_json, status, created_at, updated_at
        FROM common_event_outbox
        WHERE source_layer = %s
          AND event_type = %s
          AND source_run_id = %s
          AND status = 'pending'
        ORDER BY partition_key, event_time, outbox_id, event_id
        """,
        (SOURCE_LAYER, SOURCE_EVENT_TYPE, allowed_c3_run_id),
    )
    return [normalize_outbox_row(row) for row in cur.fetchall()]


def fetch_closed_summary_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    c3_outbox_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    summary_ids_by_asset: dict[str, set[int]] = {asset_kind: set() for asset_kind in ASSET_KINDS}
    for row in c3_outbox_rows:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind not in summary_ids_by_asset:
            continue
        payload = extract_payload(row)
        summary_id = payload.get("closed_30m_summary_id") or payload.get("summary_id")
        if summary_id is None:
            continue
        try:
            summary_ids_by_asset[asset_kind].add(int(summary_id))
        except (TypeError, ValueError):
            continue

    rows: list[dict[str, Any]] = []
    for asset_kind, summary_ids in summary_ids_by_asset.items():
        if not summary_ids:
            continue
        table_name, identity_column = SUMMARY_TABLE_CONFIG[asset_kind]
        cur.execute(
            f"""
            SELECT summary_id, run_id, source_condition_run_id, source_subscription_run_id,
                   for_trade_date, trade_date, asset_kind, {identity_column} AS identity_key,
                   bucket_id, bucket_start, bucket_end, closed_status, quality_status,
                   open, high, low, close, amount, replay_diff_json, raw_json
            FROM {table_name}
            WHERE summary_id = ANY(%s)
            ORDER BY {identity_column}, bucket_id, summary_id
            """,
            (list(summary_ids),),
        )
        rows.extend(normalize_closed_summary_row(row) for row in cur.fetchall())
    return rows


def fetch_closed_signal_enrichment_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    c2b_run_id: str,
    c3_outbox_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    summary_ids_by_asset: dict[str, set[int]] = {asset_kind: set() for asset_kind in ASSET_KINDS}
    for row in c3_outbox_rows:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind not in summary_ids_by_asset:
            continue
        payload = extract_payload(row)
        summary_id = payload.get("closed_30m_summary_id") or payload.get("summary_id")
        if summary_id is None:
            continue
        try:
            summary_ids_by_asset[asset_kind].add(int(summary_id))
        except (TypeError, ValueError):
            continue

    rows: list[dict[str, Any]] = []
    for asset_kind, summary_ids in summary_ids_by_asset.items():
        if not summary_ids:
            continue
        table_name = ENRICHMENT_TABLE_CONFIG[asset_kind]
        cur.execute(
            f"""
            SELECT enrichment_id, c2b_run_id, c2_run_id, current_summary_id,
                   source_condition_run_id, source_subscription_run_id,
                   source_previous_day_minute_run_id, for_trade_date, trade_date,
                   asset_kind, identity_key, exchange, code, display_code, name,
                   bucket_id, bucket_start, bucket_end,
                   current_window_amount, baseline_window_amount, closed_amount_ratio,
                   closed_price_change_pct, closed_price_direction_status,
                   closed_market_shape_status, closed_signal_status,
                   closed_signal_quality_status, closed_signal_basis_json,
                   baseline_trace_json, calculation_config_hash, raw_json
            FROM {table_name}
            WHERE c2b_run_id = %s
              AND current_summary_id = ANY(%s)
            ORDER BY identity_key, bucket_id, current_summary_id
            """,
            (c2b_run_id, list(summary_ids)),
        )
        rows.extend(normalize_closed_signal_enrichment_row(row) for row in cur.fetchall())
    return rows


def fetch_projection_match_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    projection_execute_run_id: str,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT trigger_match_id, run_id, source_event_id, source_event_type,
               source_condition_run_id, source_condition_pool_id, source_condition_basis_id,
               source_market_subscription_id, for_trade_date, asset_kind, identity_key,
               direction, signal_type, condition_key, trigger_price, trigger_time,
               trigger_period, trigger_bucket, data_quality_status,
               output_event_type, output_event_id, dedup_key, context_hash, raw_json
        FROM common_trigger_match
        WHERE run_id = %s
          AND signal_type = ANY(%s)
        ORDER BY asset_kind, identity_key, direction, signal_type, condition_key, trigger_bucket, trigger_match_id
        """,
        (projection_execute_run_id, list(dict.fromkeys((*REPLAY_SIGNAL_TYPES, *CANONICAL_REPLAY_SIGNAL_TYPES)))),
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def fetch_projection_trace_only_counts(cur: psycopg.Cursor[dict[str, Any]], projection_run_id: str) -> dict[str, Any]:
    counts: dict[str, Any] = {"projection_run_id": projection_run_id, "trace_only": True, "by_asset_kind": {}}
    for asset_kind in ASSET_KINDS:
        table_name = f"{asset_kind}_realtime_projection_metric"
        cur.execute("SELECT to_regclass(%s) AS table_oid", (f"public.{table_name}",))
        exists = cur.fetchone()["table_oid"] is not None
        if not exists:
            counts["by_asset_kind"][asset_kind] = {"exists": False, "row_count": None}
            continue
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE projection_run_id = %s", (projection_run_id,))
        counts["by_asset_kind"][asset_kind] = {"exists": True, "row_count": int(cur.fetchone()["row_count"])}
    return counts


def capture_row_counts(dsn: str) -> dict[str, dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_c3_replay_capture_row_counts",
        source_run_id="c3_replay_row_count_guard",
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        output: dict[str, dict[str, Any]] = {}
        for table_name in ROW_COUNT_GUARD_TABLES:
            cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
            exists = cur.fetchone()["regclass"] is not None
            if not exists:
                output[table_name] = {"exists": False, "row_count": None, "status": "missing"}
                continue
            cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
            output[table_name] = {
                "exists": True,
                "row_count": int(cur.fetchone()["row_count"]),
                "status": "present",
            }
        return output


def format_c3_replay_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    classification = report["classification_summary"]
    diff = report["replay_diff_summary"]
    signal_summary = report["signal_summary"]
    closed_signal = report.get("closed_signal_summary") or {}
    return "\n".join(
        [
            "# N4 C3 MinuteBarClosed Replay Dry-Run Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- layer_role: `{report.get('layer_role')}`",
            f"- replay_run_id: `{report.get('replay_run_id')}`",
            f"- allowed_c3_run_id: `{report.get('allowed_c3_run_id')}`",
            f"- c2b_run_id: `{report.get('c2b_run_id')}`",
            f"- trigger_context_run_id: `{report.get('trigger_context_run_id')}`",
            f"- original_n4_projection_execute_run_id: `{report.get('original_n4_projection_execute_run_id')}`",
            f"- generated_at: `{report.get('generated_at')}`",
            "",
            "## Input Boundary",
            "",
            f"- accepted C3 rows: `{report['input_boundary'].get('accepted_c3_outbox_row_count')}`",
            f"- rejected C3 rows: `{report['input_boundary'].get('rejected_c3_outbox_row_count')}`",
            "- forbidden inputs: B1 outbox, B2 projection facts as consumption input, old synthetic N4 outbox, N5 outbox, non-allowlisted C3 outbox, raw minute tables, external adapters, old system",
            "",
            "## Classification Summary",
            "",
            f"- candidate_count: `{classification.get('candidate_count')}`",
            f"- by_classification: `{classification.get('by_classification')}`",
            "",
            "## Replay Diff Summary",
            "",
            f"- projection_matched_but_closed_not_matched: `{diff.get('projection_matched_but_closed_not_matched')}`",
            f"- projection_not_matched_but_closed_matched: `{diff.get('projection_not_matched_but_closed_matched')}`",
            f"- both_matched_but_quality_changed: `{diff.get('both_matched_but_quality_changed')}`",
            f"- unchanged: `{diff.get('unchanged')}`",
            f"- replay_blocked: `{diff.get('replay_blocked')}`",
            "",
            "## Closed Signal Summary",
            "",
            f"- closed_signal_status_missing_count: `{closed_signal.get('closed_signal_status_missing_count')}`",
            f"- closed_signal_status_distribution: `{closed_signal.get('closed_signal_status_distribution')}`",
            f"- enrichment_row_count: `{closed_signal.get('enrichment_row_count')}`",
            "",
            "## Signal Summary",
            "",
            f"- by_signal_type: `{signal_summary.get('by_signal_type')}`",
            f"- by_action_mark: `{signal_summary.get('by_action_mark')}`",
            f"- by_legacy_signal_type: `{signal_summary.get('by_legacy_signal_type')}`",
            f"- by_signal_type_and_classification: `{signal_summary.get('by_signal_type_and_classification')}`",
            f"- by_action_mark_and_classification: `{signal_summary.get('by_action_mark_and_classification')}`",
            "",
            "## Boundary Confirmation",
            "",
            f"- database_written: `{report['boundary_confirmation'].get('database_written')}`",
            f"- c3_outbox_consumed: `{report['boundary_confirmation'].get('c3_outbox_consumed')}`",
            f"- common_event_inbox_written: `{report['boundary_confirmation'].get('common_event_inbox_written')}`",
            f"- checkpoint_written: `{report['boundary_confirmation'].get('checkpoint_written')}`",
            f"- trigger_match_written: `{report['boundary_confirmation'].get('trigger_match_written')}`",
            f"- trigger_state_written: `{report['boundary_confirmation'].get('trigger_state_written')}`",
            f"- n4_outbox_written: `{report['boundary_confirmation'].get('n4_outbox_written')}`",
            f"- n5_n6_touched: `{report['boundary_confirmation'].get('n5_n6_touched')}`",
            f"- worker_started: `{report['boundary_confirmation'].get('worker_started')}`",
            "",
            "## Quality",
            "",
            f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
            f"- quality_items: `{len(quality.get('items') or [])}`",
            "",
            "## Next Gate",
            "",
            f"- allow_n4_c3_replay_dry_run_review: `{report['next_gate'].get('allow_n4_c3_replay_dry_run_review')}`",
            "- replay execute remains blocked until a separate replay execute/event contract is approved.",
        ]
    )


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: str, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
