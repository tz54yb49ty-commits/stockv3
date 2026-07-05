"""N3-C3 MinuteBarClosed outbox dry-run planner.

The planner reads C2 closed 30m summary facts and builds validated
MinuteBarClosed v2 event candidates. It never writes N3 facts, quality rows,
outbox rows, inbox rows, checkpoints, or downstream runtime state.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.events.models import EventContractError, EventEnvelope
from ashare_v3.market.closed_30m_replay_plan import ASSET_KINDS, IDENTITY_COLUMNS, SUMMARY_TABLES
from ashare_v3.market.event_factory import minute_bar_closed_event
from ashare_v3.market.preload_plan import normalize_db_row


DEFAULT_DESIGN_PATH = "docs/N3_C3_minute_bar_closed_dry_run_design.json"
DEFAULT_V2_CONTRACT_PATH = "docs/N3_C3_minute_bar_closed_v2_event_contract.json"
DEFAULT_C2_EXECUTE_REPORT_PATH = "docs/N3_C2_closed_30m_replay_execute_report.json"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/N3_C3_MINUTEBARCLOSED_OUTBOX_DRY_RUN_REPORT.md"
DEFAULT_JSON_REPORT_PATH = "docs/N3_C3_minute_bar_closed_outbox_dry_run_report.json"

EVENT_TYPE = "MinuteBarClosed"
EVENT_SCHEMA_VERSION = "v2"
REQUIRED_DATA_KIND = "minute_bar_1m"
C3_SOURCE_ADAPTER = "N3Closed30mSummaryAdapter"
ALLOWED_FUTURE_EXECUTE_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "common_event_outbox",
]
FORBIDDEN_WRITE_TABLES = [
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
    "condition tables",
    "trigger/action/user/voice/mobile/sim/position tables",
    "N4/N5/N6",
    "worker",
    "old system",
]


@dataclass(frozen=True)
class MinuteBarClosedCandidate:
    event: EventEnvelope | None
    summary: Mapping[str, Any]
    blocker: dict[str, Any] | None = None


def build_c3_run_id(*, c2_run_id: str, for_trade_date: str) -> str:
    return f"minute_bar_closed_outbox_{for_trade_date}__{c2_run_id}"


def build_write_scope_contract() -> dict[str, Any]:
    return {
        "allowed_future_execute_write_tables": list(ALLOWED_FUTURE_EXECUTE_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "future_execute_writes_outbox": True,
        "dry_run_writes_outbox": False,
        "dry_run_writes_run_or_quality": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "downstream_layers_touched": False,
        "worker_started": False,
        "n4_n5_replay_requires_explicit_c3_run_id_allowlist": True,
    }


def build_trace_enrichment_context(
    *,
    subscription_rows: Sequence[Mapping[str, Any]],
    pull_plan_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    subscriptions_by_id: dict[int, dict[str, Any]] = {}
    subscriptions_by_identity: dict[str, dict[str, Any]] = {}
    for row in subscription_rows:
        normalized = dict(row)
        subscription_id = normalized.get("subscription_id")
        if subscription_id is not None:
            subscriptions_by_id[int(subscription_id)] = normalized
        identity_key = str(normalized.get("identity_key") or "")
        asset_kind = str(normalized.get("asset_kind") or "")
        if asset_kind and identity_key:
            subscriptions_by_identity[f"{asset_kind}|{identity_key}"] = normalized

    pull_plan_by_asset: dict[str, dict[str, Any]] = {}
    for row in pull_plan_rows:
        normalized = dict(row)
        asset_kind = str(normalized.get("asset_kind") or "")
        if asset_kind:
            pull_plan_by_asset[asset_kind] = normalized

    return {
        "subscriptions_by_id": subscriptions_by_id,
        "subscriptions_by_identity": subscriptions_by_identity,
        "pull_plan_by_asset": pull_plan_by_asset,
    }


def build_minute_bar_closed_candidate(
    *,
    summary: Mapping[str, Any],
    enrichment_context: Mapping[str, Any],
    c3_run_id: str,
) -> MinuteBarClosedCandidate:
    if str(summary.get("closed_status") or "") != "closed":
        return MinuteBarClosedCandidate(
            event=None,
            summary=summary,
            blocker=blocker(summary, "not_closed_summary", "Only closed summaries can emit MinuteBarClosed"),
        )

    asset_kind = str(summary.get("asset_kind") or "")
    identity_key = str(summary.get("identity_key") or summary.get(f"{asset_kind}_identity_key") or "")
    subscription_id = extract_subscription_id(summary)
    if subscription_id is None:
        return MinuteBarClosedCandidate(
            event=None,
            summary=summary,
            blocker=blocker(summary, "missing_subscription_id", "summary trace missing subscription_id"),
        )

    subscriptions_by_id = enrichment_context.get("subscriptions_by_id") or {}
    subscription = subscriptions_by_id.get(int(subscription_id))
    if subscription is None:
        subscription = (enrichment_context.get("subscriptions_by_identity") or {}).get(f"{asset_kind}|{identity_key}")
    if subscription is None:
        return MinuteBarClosedCandidate(
            event=None,
            summary=summary,
            blocker=blocker(summary, "missing_subscription_trace", "subscription trace could not be resolved"),
        )
    if str(subscription.get("identity_key") or "") != identity_key:
        return MinuteBarClosedCandidate(
            event=None,
            summary=summary,
            blocker=blocker(summary, "subscription_identity_mismatch", "subscription identity does not match summary"),
        )

    pull_plan = (enrichment_context.get("pull_plan_by_asset") or {}).get(asset_kind)
    pull_plan_id = pull_plan.get("pull_plan_id") if pull_plan else None
    if not pull_plan_id:
        return MinuteBarClosedCandidate(
            event=None,
            summary=summary,
            blocker=blocker(summary, "missing_pull_plan_id", "pull_plan_id could not be resolved"),
        )

    source_minute_refs = extract_source_minute_refs(summary)
    if not source_minute_refs:
        return MinuteBarClosedCandidate(
            event=None,
            summary=summary,
            blocker=blocker(summary, "missing_source_minute_refs", "source_minute_refs is required for v2"),
        )

    summary_id = summary.get("summary_id")
    if summary_id is None:
        return MinuteBarClosedCandidate(
            event=None,
            summary=summary,
            blocker=blocker(summary, "missing_summary_id", "summary_id is required for v2 dedup"),
        )

    payload = {
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "closed_30m_summary_id": summary_id,
        "summary_id": summary_id,
        "source_minute_bar_ids": list(summary.get("source_minute_bar_ids") or []),
        "source_minute_refs": source_minute_refs,
        "c2_run_id": summary.get("run_id"),
        "source_condition_run_id": summary.get("source_condition_run_id"),
        "source_subscription_run_id": summary.get("source_subscription_run_id"),
        "source_today_minute_run_ids": list(summary.get("source_today_minute_run_ids") or []),
        "bucket_id": summary.get("bucket_id"),
        "bucket_start": stringify_value(summary.get("bucket_start")),
        "bucket_end": stringify_value(summary.get("bucket_end")),
        "closed_status": summary.get("closed_status"),
        "replay_diff_json": summary.get("replay_diff_json") or {},
        "quality_status": summary.get("quality_status") or "passed",
        "subscription_id": subscription_id,
        "pull_plan_id": int(pull_plan_id),
        "run_id": c3_run_id,
        "source_adapter": C3_SOURCE_ADAPTER,
        "source_pull_plan_adapter": pull_plan.get("adapter_name") if pull_plan else None,
        "data_quality_status": summary.get("quality_status") or "passed",
    }
    try:
        event = minute_bar_closed_event(
            asset_kind=asset_kind,
            identity_key=identity_key,
            trade_date=str(summary.get("trade_date") or summary.get("for_trade_date") or ""),
            minute_bar_time=stringify_value(summary.get("bucket_end")) or str(summary.get("bucket_id") or ""),
            event_time=coerce_datetime(summary.get("bucket_end")),
            source_run_id=c3_run_id,
            source_adapter=C3_SOURCE_ADAPTER,
            payload=payload,
            event_schema_version=EVENT_SCHEMA_VERSION,
            c2_run_id=str(summary.get("run_id") or ""),
            summary_id=summary_id,
            bucket_id=str(summary.get("bucket_id") or ""),
        )
    except (EventContractError, ValueError) as exc:
        return MinuteBarClosedCandidate(
            event=None,
            summary=summary,
            blocker=blocker(summary, "payload_validation_failed", str(exc)),
        )

    return MinuteBarClosedCandidate(event=event, summary=summary)


def build_minute_bar_closed_dry_run_report(
    *,
    c2_run_id: str,
    c3_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    for_trade_date: str,
    summary_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    enrichment_context: Mapping[str, Any],
    target_audit: Mapping[str, Any],
    expected_counts: Mapping[str, int],
    expected_excluded: Mapping[str, int],
    source_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows_by_asset = {asset_kind: list(summary_rows_by_asset.get(asset_kind) or []) for asset_kind in ASSET_KINDS}
    status_counts_by_asset = {
        asset_kind: dict(Counter(str(row.get("closed_status") or "") for row in rows))
        for asset_kind, rows in rows_by_asset.items()
    }
    closed_rows_by_asset = {
        asset_kind: [row for row in rows if str(row.get("closed_status") or "") == "closed"]
        for asset_kind, rows in rows_by_asset.items()
    }
    candidate_source_count_by_asset = {asset_kind: len(rows) for asset_kind, rows in closed_rows_by_asset.items()}
    candidate_source_count_by_asset["total"] = sum(candidate_source_count_by_asset.values())
    excluded_by_status = {
        status: sum(
            count
            for counts in status_counts_by_asset.values()
            for key, count in counts.items()
            if key == status
        )
        for status in ("missing", "partial", "failed")
    }
    excluded_by_status["total"] = sum(excluded_by_status.values())
    bj_excluded = sum(
        1
        for rows in rows_by_asset.values()
        for row in rows
        if str(row.get("closed_status") or "") in {"missing", "partial", "failed"} and is_bj_920xxx(row)
    )

    candidates: list[MinuteBarClosedCandidate] = []
    for asset_kind in ASSET_KINDS:
        for row in closed_rows_by_asset[asset_kind]:
            candidates.append(
                build_minute_bar_closed_candidate(
                    summary=row,
                    enrichment_context=enrichment_context,
                    c3_run_id=c3_run_id,
                )
            )
    events = [candidate.event for candidate in candidates if candidate.event is not None]
    blockers = [candidate.blocker for candidate in candidates if candidate.blocker is not None]
    event_count_by_asset = Counter(event.asset_kind for event in events)
    generated_count_by_asset = {asset_kind: int(event_count_by_asset.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}
    generated_count_by_asset["total"] = sum(generated_count_by_asset.values())
    duplicate_summary = build_duplicate_summary(events)
    quality_items = build_quality_items(
        c2_run_id=c2_run_id,
        c3_run_id=c3_run_id,
        expected_counts=expected_counts,
        actual_counts=candidate_source_count_by_asset,
        expected_excluded=expected_excluded,
        actual_excluded=excluded_by_status,
        target_audit=target_audit,
        blockers=blockers,
        duplicate_summary=duplicate_summary,
        source_evidence=source_evidence or {},
    )
    severity_counts = count_quality_severities(quality_items)
    blocked = severity_counts["P0"] > 0
    return {
        "stage": "N3-C3",
        "layer_role": "N3_market_data",
        "execution_mode": "minute_bar_closed_outbox_dry_run",
        "result": "DRY_RUN_BLOCKED" if blocked else "DRY_RUN_PASS",
        "blocked": blocked,
        "c2_run_id": c2_run_id,
        "c3_run_id": c3_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "for_trade_date": for_trade_date,
        "event_contract": {
            "event_type": EVENT_TYPE,
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "minute_bar_id_required": False,
            "source_adapter": C3_SOURCE_ADAPTER,
        },
        "candidate_summary": {
            "candidate_source_count_by_asset": candidate_source_count_by_asset,
            "candidate_count_by_asset": generated_count_by_asset,
            "excluded_by_status": excluded_by_status,
            "status_counts_by_asset": status_counts_by_asset,
            "bj_920xxx_excluded_summary_rows": bj_excluded,
        },
        "payload_validation_summary": {
            "validated_count": len(events),
            "blocked_count": len(blockers),
            "blockers_by_code": dict(Counter(str(item.get("blocker_code")) for item in blockers)),
            "blocker_samples": blockers[:20],
            "event_samples": [event_sample(event) for event in events[:5]],
        },
        "trace_enrichment_summary": {
            "subscription_trace_count": len(enrichment_context.get("subscriptions_by_id") or {}),
            "pull_plan_trace_count": len(enrichment_context.get("pull_plan_by_asset") or {}),
            "missing_trace_blockers": [item for item in blockers if str(item.get("blocker_code") or "").startswith("missing_")][:20],
            "pull_plan_id_required": True,
            "placeholder_pull_plan_id_allowed": False,
        },
        "duplicate_summary": duplicate_summary,
        "write_scope_contract": build_write_scope_contract(),
        "target_audit": dict(target_audit),
        "source_evidence": dict(source_evidence or {}),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "quality_written": False,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "inbox_or_checkpoint_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "replay_storm_guard": {
            "c3_consumes_outbox": False,
            "worker_auto_consume_c3_source_run_id_allowed": False,
            "n4_n5_replay_requires_explicit_c3_run_id_allowlist": True,
            "n4_n5_replay_contract_required": True,
        },
        "next_allowed_step": "N3-C3 dry-run review" if not blocked else "fix C3 dry-run P0 blockers",
    }


def build_minute_bar_closed_outbox_dry_run(
    *,
    dsn: str,
    design_path: str = DEFAULT_DESIGN_PATH,
    v2_contract_path: str = DEFAULT_V2_CONTRACT_PATH,
    c2_execute_report_path: str = DEFAULT_C2_EXECUTE_REPORT_PATH,
) -> dict[str, Any]:
    design = load_json_file(design_path)
    v2_contract = load_json_file(v2_contract_path)
    c2_report = load_json_file(c2_execute_report_path)
    lineage = design.get("source_lineage") or {}
    c2_run_id = str(lineage.get("c2_run_id") or c2_report.get("c2_run_id") or "")
    source_condition_run_id = str(lineage.get("source_condition_run_id") or c2_report.get("source_condition_run_id") or "")
    source_subscription_run_id = str(lineage.get("source_subscription_run_id") or c2_report.get("source_subscription_run_id") or "")
    for_trade_date = str(lineage.get("for_trade_date") or c2_report.get("for_trade_date") or "")
    c3_run_id = build_c3_run_id(c2_run_id=c2_run_id, for_trade_date=for_trade_date)
    runtime = fetch_runtime_context(
        dsn=dsn,
        c2_run_id=c2_run_id,
        c3_run_id=c3_run_id,
        source_subscription_run_id=source_subscription_run_id,
        for_trade_date=for_trade_date,
    )
    expected_counts = (design.get("candidate_count") or {}).get("expected_minute_bar_closed_candidates") or {}
    expected_excluded = (design.get("candidate_count") or {}).get("expected_excluded_summary_count") or {}
    return build_minute_bar_closed_dry_run_report(
        c2_run_id=c2_run_id,
        c3_run_id=c3_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        for_trade_date=for_trade_date,
        summary_rows_by_asset=runtime["summary_rows_by_asset"],
        enrichment_context=runtime["enrichment_context"],
        target_audit=runtime["target_audit"],
        expected_counts=expected_counts,
        expected_excluded=expected_excluded,
        source_evidence={
            "design_path": design_path,
            "v2_contract_path": v2_contract_path,
            "c2_execute_report_path": c2_execute_report_path,
            "v2_contract_result": v2_contract.get("result"),
            "c2_execute_result": c2_report.get("result"),
        },
    )


def fetch_runtime_context(
    *,
    dsn: str,
    c2_run_id: str,
    c3_run_id: str,
    source_subscription_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        summary_rows_by_asset = {
            asset_kind: fetch_summary_rows(cur, asset_kind=asset_kind, c2_run_id=c2_run_id)
            for asset_kind in ASSET_KINDS
        }
        subscriptions = fetch_subscription_rows(cur, source_subscription_run_id, for_trade_date)
        pull_plans = fetch_pull_plan_rows(cur, source_subscription_run_id, for_trade_date)
        target_audit = fetch_target_audit(cur, c3_run_id)
    return {
        "summary_rows_by_asset": summary_rows_by_asset,
        "enrichment_context": build_trace_enrichment_context(
            subscription_rows=subscriptions,
            pull_plan_rows=pull_plans,
        ),
        "target_audit": target_audit,
    }


def fetch_summary_rows(cur: Any, *, asset_kind: str, c2_run_id: str) -> list[dict[str, Any]]:
    table_name = SUMMARY_TABLES[asset_kind]
    identity_column = IDENTITY_COLUMNS[asset_kind]
    cur.execute(
        f"""
        SELECT summary_id, run_id, source_condition_run_id, source_subscription_run_id,
               source_today_minute_run_ids, for_trade_date, trade_date, asset_kind,
               {identity_column} AS identity_key, exchange, code, display_code, name,
               bucket_id, bucket_start, bucket_end, closed_status, quality_status,
               source_minute_bar_ids, replay_diff_json, raw_json
        FROM {table_name}
        WHERE run_id = %s
        ORDER BY {identity_column}, bucket_id, summary_id
        """,
        (c2_run_id,),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def fetch_subscription_rows(cur: Any, run_id: str, for_trade_date: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT subscription_id, run_id, asset_kind, identity_key, exchange, code,
               display_code, name, required_data_kind, data_trade_date, status
        FROM common_market_data_subscription
        WHERE run_id = %s
          AND for_trade_date = %s
          AND required_data_kind = 'minute_bar_1m'
        ORDER BY asset_kind, identity_key, subscription_id
        """,
        (run_id, for_trade_date),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def fetch_pull_plan_rows(cur: Any, run_id: str, for_trade_date: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT pull_plan_id, run_id, asset_kind, required_data_kind, data_trade_date,
               for_trade_date, adapter_name, plan_status
        FROM common_market_data_pull_plan
        WHERE run_id = %s
          AND for_trade_date = %s
          AND data_trade_date = %s
          AND required_data_kind = 'minute_bar_1m'
        ORDER BY asset_kind, pull_plan_id
        """,
        (run_id, for_trade_date, for_trade_date),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def fetch_target_audit(cur: Any, c3_run_id: str) -> dict[str, Any]:
    return {
        "run_exists": market_data_run_exists(cur, c3_run_id),
        "quality_rows_for_c3_run": count_rows_by_run(cur, "common_market_data_quality_item", c3_run_id),
        "outbox_rows_for_c3_run": count_outbox_rows(cur, c3_run_id),
        "inbox_rows_for_c3_run": count_inbox_rows(cur, c3_run_id),
        "checkpoint_rows_for_c3_run": count_checkpoint_rows(cur, c3_run_id),
    }


def market_data_run_exists(cur: Any, run_id: str) -> bool:
    cur.execute("SELECT 1 FROM common_market_data_run WHERE run_id = %s LIMIT 1", (run_id,))
    return cur.fetchone() is not None


def count_rows_by_run(cur: Any, table_name: str, run_id: str) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def count_outbox_rows(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def count_inbox_rows(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def count_checkpoint_rows(cur: Any, run_id: str) -> int:
    cur.execute(
        "SELECT count(*)::bigint AS row_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::TEXT LIKE %s",
        (f"%{run_id}%",),
    )
    return int(cur.fetchone()["row_count"])


def build_duplicate_summary(events: Sequence[EventEnvelope]) -> dict[str, Any]:
    counts = Counter(event.dedup_key for event in events)
    duplicates = {key: count for key, count in counts.items() if count > 1}
    return {
        "duplicate_candidate_count": sum(count - 1 for count in duplicates.values()),
        "duplicate_key_count": len(duplicates),
        "duplicate_keys_sample": [
            {"dedup_key": key, "count": count}
            for key, count in list(duplicates.items())[:20]
        ],
    }


def build_quality_items(
    *,
    c2_run_id: str,
    c3_run_id: str,
    expected_counts: Mapping[str, int],
    actual_counts: Mapping[str, int],
    expected_excluded: Mapping[str, int],
    actual_excluded: Mapping[str, int],
    target_audit: Mapping[str, Any],
    blockers: Sequence[Mapping[str, Any]],
    duplicate_summary: Mapping[str, Any],
    source_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not c2_run_id:
        items.append(quality_item("P0", "failed", "n3_c3_c2_run_id_present", "C2 run id is present"))
    if not c3_run_id:
        items.append(quality_item("P0", "failed", "n3_c3_c3_run_id_present", "C3 run id is present"))
    if target_audit.get("run_exists"):
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c3_run_id_not_reused",
                "C3 run id must not already exist",
                expected="absent",
                actual="present",
            )
        )
    for key in ("quality_rows_for_c3_run", "outbox_rows_for_c3_run", "inbox_rows_for_c3_run", "checkpoint_rows_for_c3_run"):
        if int(target_audit.get(key) or 0):
            items.append(
                quality_item(
                    "P0",
                    "failed",
                    f"n3_c3_{key}_zero",
                    f"{key} must be zero before C3 execute",
                    expected="0",
                    actual=str(target_audit.get(key)),
                )
            )
    for asset_kind in (*ASSET_KINDS, "total"):
        expected = int(expected_counts.get(asset_kind) or 0)
        actual = int(actual_counts.get(asset_kind) or 0)
        if expected != actual:
            items.append(
                quality_item(
                    "P0",
                    "failed",
                    f"n3_c3_candidate_count_{asset_kind}_matches_design",
                    f"C3 candidate count for {asset_kind} matches design",
                    expected=str(expected),
                    actual=str(actual),
                )
            )
    for status in ("missing", "partial", "failed", "total"):
        expected = int(expected_excluded.get(status) or 0)
        actual = int(actual_excluded.get(status) or 0)
        if expected != actual:
            items.append(
                quality_item(
                    "P0",
                    "failed",
                    f"n3_c3_excluded_{status}_matches_design",
                    f"C3 excluded {status} count matches design",
                    expected=str(expected),
                    actual=str(actual),
                )
            )
    if blockers:
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c3_trace_or_payload_blockers_zero",
                "All closed summaries resolve trace and validate payload",
                expected="0 blockers",
                actual=str(len(blockers)),
            )
        )
    duplicate_count = int(duplicate_summary.get("duplicate_candidate_count") or 0)
    if duplicate_count:
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c3_duplicate_dedup_key_zero",
                "MinuteBarClosed v2 dedup keys are unique",
                expected="0",
                actual=str(duplicate_count),
            )
        )
    if int(actual_excluded.get("missing") or 0):
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c3_missing_summaries_excluded",
                "Missing summaries are excluded from MinuteBarClosed generation",
                expected="0 missing excluded",
                actual=str(actual_excluded.get("missing")),
            )
        )
    if not source_evidence.get("v2_contract_result", "DESIGN_PASS"):
        items.append(
            quality_item(
                "P2",
                "passed",
                "n3_c3_v2_contract_loaded",
                "C3 v2 event contract evidence loaded",
            )
        )
    if not items:
        items.append(
            quality_item(
                "P2",
                "passed",
                "n3_c3_dry_run_ready",
                "C3 MinuteBarClosed dry-run is ready for review",
                expected="ready",
                actual="ready",
            )
        )
    return items


def extract_subscription_id(summary: Mapping[str, Any]) -> int | None:
    raw_json = summary.get("raw_json") or {}
    value = summary.get("subscription_id") or raw_json.get("subscription_id")
    if value is None:
        return None
    return int(value)


def extract_source_minute_refs(summary: Mapping[str, Any]) -> list[Any]:
    replay_diff_json = summary.get("replay_diff_json") or {}
    raw_json = summary.get("raw_json") or {}
    refs = replay_diff_json.get("source_minute_refs") or raw_json.get("resolved_minute_trace") or []
    return list(refs)


def blocker(summary: Mapping[str, Any], code: str, reason: str) -> dict[str, Any]:
    asset_kind = str(summary.get("asset_kind") or "")
    return {
        "blocker_code": code,
        "reason": reason,
        "summary_id": summary.get("summary_id"),
        "asset_kind": asset_kind,
        "identity_key": summary.get("identity_key") or summary.get(f"{asset_kind}_identity_key"),
        "bucket_id": summary.get("bucket_id"),
    }


def is_bj_920xxx(row: Mapping[str, Any]) -> bool:
    identity_key = str(row.get("identity_key") or row.get("stock_identity_key") or "")
    exchange = str(row.get("exchange") or "")
    code = str(row.get("code") or "")
    return exchange == "BJ" or code.startswith("920") or identity_key.startswith("stock:BJ:920")


def coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def stringify_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def event_sample(event: EventEnvelope) -> dict[str, Any]:
    payload = event.payload_json
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "asset_kind": event.asset_kind,
        "identity_key": event.identity_key,
        "dedup_key": event.dedup_key,
        "summary_id": payload.get("summary_id"),
        "bucket_id": payload.get("bucket_id"),
        "pull_plan_id": payload.get("pull_plan_id"),
        "source_minute_refs_count": len(payload.get("source_minute_refs") or []),
    }


def load_json_file(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_report_files(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    markdown = Path(markdown_path)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(format_markdown_report(report), encoding="utf-8")
    json_report = Path(json_path)
    json_report.parent.mkdir(parents=True, exist_ok=True)
    json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def format_summary(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    candidate = report.get("candidate_summary") or {}
    payload = report.get("payload_validation_summary") or {}
    duplicate = report.get("duplicate_summary") or {}
    return "\n".join(
        [
            "MinuteBarClosed outbox dry-run",
            f"  result={report.get('result')}",
            f"  c2_run_id={report.get('c2_run_id')}",
            f"  c3_run_id={report.get('c3_run_id')}",
            f"  candidates={candidate.get('candidate_count_by_asset')}",
            f"  excluded={candidate.get('excluded_by_status')}",
            f"  payload_validated={payload.get('validated_count')} blockers={payload.get('blocked_count')}",
            f"  duplicate_candidate_count={duplicate.get('duplicate_candidate_count')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
            "  writes_performed=false event_outbox_written=false outbox_consumed=false worker_started=false",
        ]
    )


def format_markdown_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    candidate = report.get("candidate_summary") or {}
    payload = report.get("payload_validation_summary") or {}
    trace = report.get("trace_enrichment_summary") or {}
    duplicate = report.get("duplicate_summary") or {}
    scope = report.get("write_scope_contract") or {}
    lines = [
        "# N3-C3 MinuteBarClosed Outbox Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- result: `{report.get('result')}`",
        f"- layer_role: `{report.get('layer_role')}`",
        f"- c2_run_id: `{report.get('c2_run_id')}`",
        f"- c3_run_id: `{report.get('c3_run_id')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- candidate_count_by_asset: `{candidate.get('candidate_count_by_asset')}`",
        f"- excluded_by_status: `{candidate.get('excluded_by_status')}`",
        f"- bj_920xxx_excluded_summary_rows: `{candidate.get('bj_920xxx_excluded_summary_rows')}`",
        f"- payload_validated_count: `{payload.get('validated_count')}`",
        f"- trace_blocked_count: `{payload.get('blocked_count')}`",
        f"- duplicate_candidate_count: `{duplicate.get('duplicate_candidate_count')}`",
        f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
        "",
        "## Boundary",
        "",
        "- writes_performed: `false`",
        "- quality_written: `false`",
        "- event_outbox_written: `false`",
        "- outbox_consumed: `false`",
        "- inbox_or_checkpoint_written: `false`",
        "- downstream_layers_touched: `false`",
        "- worker_started: `false`",
        "",
        "## Trace Enrichment",
        "",
        f"- subscription_trace_count: `{trace.get('subscription_trace_count')}`",
        f"- pull_plan_trace_count: `{trace.get('pull_plan_trace_count')}`",
        "- missing trace rows block event generation; placeholder `pull_plan_id` is forbidden.",
        "",
        "## Future Write Scope",
        "",
        "Allowed future execute writes:",
        "",
        "```text",
        "\n".join(scope.get("allowed_future_execute_write_tables") or []),
        "```",
        "",
        "Forbidden:",
        "",
        "```text",
        "\n".join(scope.get("forbidden_write_tables") or []),
        "```",
        "",
        "## Replay Guard",
        "",
        "- C3 dry-run does not consume outbox.",
        "- C3 future execute only writes pending outbox rows after explicit gate.",
        "- N4/N5 replay requires explicit C3 run_id allowlist and owning-layer contracts.",
        "",
        "## Next Step",
        "",
        f"- next_allowed_step: `{report.get('next_allowed_step')}`",
        "- C3 execute remains forbidden until a separate execute contract, preflight, rollback review, and explicit user confirmation.",
        "",
    ]
    return "\n".join(lines)
