"""N3-C3 MinuteBarClosed outbox run-once executor.

The executor is scoped to C3 outbox creation from C2 closed 30m summaries. It
does not modify closed summary rows, minute bars, realtime projection facts,
snapshots, inbox/checkpoint rows, downstream runtime, or worker state.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities
from ashare_v3.events.repository import EventRepository
from ashare_v3.events.models import EventEnvelope
from ashare_v3.market.minute_bar_closed_outbox_plan import (
    ASSET_KINDS,
    DEFAULT_JSON_REPORT_PATH as DEFAULT_C3_DRY_RUN_JSON_PATH,
    EVENT_TYPE,
    build_c3_run_id,
    build_duplicate_summary,
    build_minute_bar_closed_candidate,
    fetch_runtime_context,
)
from ashare_v3.market.previous_day_preload_execute import json_safe, utc_now_iso, write_json, write_text


DEFAULT_C3_CONTRACT_JSON_PATH = "docs/N3_C3_minute_bar_closed_execute_contract.json"
DEFAULT_C3_PREFLIGHT_JSON_PATH = "docs/N3_C3_minute_bar_closed_execute_preflight.json"
DEFAULT_C3_JSON_REPORT_PATH = "docs/N3_C3_minute_bar_closed_execute_report.json"
DEFAULT_C3_MD_REPORT_PATH = "docs/N3_C3_MINUTEBARCLOSED_EXECUTE_REPORT.md"
DEFAULT_C3_ROLLBACK_SQL_PATH = "sql/N3_C3_minute_bar_closed_outbox_rollback.sql"

C3_METRIC_SCOPE = "minute_bar_closed_outbox"
C3_QUALITY_SCHEMA_VERSION = "n3.minute_bar_closed_outbox.v1"
C3_QUALITY_LAYER_SCOPE = "market_data_run"
ALLOWED_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "common_event_outbox",
)
FORBIDDEN_WRITE_TABLES = (
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
)


class MinuteBarClosedOutboxExecuteError(RuntimeError):
    """Raised when N3-C3 execute violates its reviewed contract."""


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_minute_bar_closed_outbox_execute(
    *,
    dsn: str,
    contract_path: str = DEFAULT_C3_CONTRACT_JSON_PATH,
    preflight_path: str = DEFAULT_C3_PREFLIGHT_JSON_PATH,
    dry_run_path: str = DEFAULT_C3_DRY_RUN_JSON_PATH,
    json_report_path: str = DEFAULT_C3_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_C3_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_C3_ROLLBACK_SQL_PATH,
    c3_run_id: str | None = None,
    for_trade_date: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    contract = read_json(contract_path)
    preflight = read_json(preflight_path)
    dry_run = read_json(dry_run_path)
    ensure_c3_execute_contract(
        contract,
        preflight,
        dry_run,
        execute=execute,
        user_confirmed=user_confirmed,
        c3_run_id=c3_run_id,
        for_trade_date=for_trade_date,
    )
    resolved_run_id = str(contract["c3_run_id"])
    c2_run_id = str(contract["c2_run_id"])
    dates = contract["dates"]
    source_runs = contract["source_runs"]

    pre_execute = capture_c3_execute_snapshot(
        dsn,
        c3_run_id=resolved_run_id,
        source_subscription_run_id=str(source_runs["source_subscription_run_id"]),
        c2_run_id=c2_run_id,
    )
    ensure_clean_c3_target(pre_execute["target_audit"], resolved_run_id)
    ensure_source_runs_passed(pre_execute, contract)

    if progress_callback:
        progress_callback("N3-C3 building MinuteBarClosed v2 events")
    runtime = fetch_runtime_context(
        dsn=dsn,
        c2_run_id=c2_run_id,
        c3_run_id=resolved_run_id,
        source_subscription_run_id=str(source_runs["source_subscription_run_id"]),
        for_trade_date=str(dates["for_trade_date"]),
    )
    events, blockers, excluded = build_events_for_execute(
        summary_rows_by_asset=runtime["summary_rows_by_asset"],
        enrichment_context=runtime["enrichment_context"],
        c3_run_id=resolved_run_id,
    )
    event_summary = summarize_c3_events(events, blockers, excluded)
    validate_event_summary_against_contract(event_summary, contract, dry_run)
    quality_items = build_c3_execute_quality_items(
        contract=contract,
        event_summary=event_summary,
        target_audit=pre_execute["target_audit"],
    )
    quality_counts = count_quality_severities(quality_items)
    if quality_counts["P0"]:
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: P0 quality blockers present before write")

    started_at = utc_now_iso()
    if progress_callback:
        progress_callback(f"N3-C3 writing {len(events)} MinuteBarClosed outbox rows")
    write_c3_execute_transaction(
        dsn=dsn,
        contract=contract,
        events=events,
        quality_items=quality_items,
        status="passed",
        started_at=started_at,
        contract_path=contract_path,
        preflight_path=preflight_path,
        dry_run_path=dry_run_path,
    )
    post_execute = capture_c3_execute_snapshot(
        dsn,
        c3_run_id=resolved_run_id,
        source_subscription_run_id=str(source_runs["source_subscription_run_id"]),
        c2_run_id=c2_run_id,
    )
    rollback_sql = build_c3_rollback_sql(resolved_run_id)
    write_text(rollback_sql_path, rollback_sql)
    report = {
        "stage": "N3-C3",
        "layer_role": "N3_market_data",
        "execution_mode": "minute_bar_closed_outbox_run_once_execute",
        "result": "EXECUTED",
        "c3_run_id": resolved_run_id,
        "c2_run_id": c2_run_id,
        "source_condition_run_id": source_runs["source_condition_run_id"],
        "source_subscription_run_id": source_runs["source_subscription_run_id"],
        "for_trade_date": dates["for_trade_date"],
        "source_trade_date": dates["source_trade_date"],
        "prev_trade_date": dates["prev_trade_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "paths": {
            "contract_path": contract_path,
            "preflight_path": preflight_path,
            "dry_run_path": dry_run_path,
            "rollback_sql_path": rollback_sql_path,
        },
        "write_result": {
            "outbox_rows_written": len(events),
            "quality_rows_written": len(quality_items),
            "run_rows_written": 1,
            "event_type_counts": event_summary["event_count_by_type"],
            "outbox_rows_by_event_type": event_summary["event_count_by_type"],
            "status": "pending",
            "delivered_or_delivering": 0,
        },
        "event_summary": event_summary,
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "pre_execute": pre_execute,
        "post_execute": post_execute,
        "rollback": {
            "rollback_safe": rollback_safe_from_snapshot(post_execute),
            "rollback_sql_path": rollback_sql_path,
        },
        "side_effects": {
            "writes_performed": True,
            "event_outbox_written": True,
            "quality_written": True,
            "market_data_fact_written": False,
            "outbox_consumed": False,
            "inbox_or_checkpoint_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "next_allowed_step": "N3-C3 execute post-review",
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_c3_execute_report(report))
    return report


def ensure_c3_execute_contract(
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    *,
    execute: bool,
    user_confirmed: bool,
    c3_run_id: str | None,
    for_trade_date: str | None,
) -> None:
    if not execute:
        raise MinuteBarClosedOutboxExecuteError("N3-C3 MinuteBarClosed execute requires explicit --execute")
    if not user_confirmed:
        raise MinuteBarClosedOutboxExecuteError("N3-C3 MinuteBarClosed execute requires explicit --user-confirmed")
    if contract.get("stage") != "N3-C3-MinuteBarClosed-outbox-execute-contract":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: contract stage mismatch")
    if contract.get("layer_role") != "N3_market_data":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: contract layer_role mismatch")
    if contract.get("execution_mode") != "minute_bar_closed_outbox_run_once_execute":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: execution_mode mismatch")
    if not contract.get("runner_exists") or contract.get("runner_readiness") != "ready":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: runner readiness is not ready")
    if preflight.get("stage") != "N3-C3-MinuteBarClosed-outbox-execute-preflight":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: preflight stage mismatch")
    if preflight.get("result") != "PREFLIGHT_PASS":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: preflight did not pass")
    if preflight.get("runner_readiness") != "ready":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: preflight runner readiness is not ready")
    if dry_run.get("result") != "DRY_RUN_PASS":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: dry-run did not pass")
    if c3_run_id and c3_run_id != str(contract.get("c3_run_id") or ""):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: CLI c3_run_id does not match contract")
    if preflight.get("c3_run_id") != contract.get("c3_run_id") or dry_run.get("c3_run_id") != contract.get("c3_run_id"):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: c3_run_id mismatch")
    dates = contract.get("dates") or {}
    contract_for_trade_date = str(dates.get("for_trade_date") or "")
    if for_trade_date and for_trade_date != contract_for_trade_date:
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: CLI for_trade_date does not match contract")
    if str(dates.get("source_trade_date") or "") != contract_for_trade_date:
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: source_trade_date must equal for_trade_date for C3 run metadata")
    if str(dates.get("prev_trade_date") or "") != contract_for_trade_date:
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: prev_trade_date must equal for_trade_date for C3 run metadata")
    previous_day = contract.get("previous_day_provenance") or {}
    if str(previous_day.get("previous_day_minute_date") or "") == "":
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: previous_day_provenance.previous_day_minute_date is required")
    if not contract.get("writes_outbox") or not (preflight.get("contract_summary") or {}).get("writes_outbox"):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: contract must have writes_outbox=true")
    if contract.get("consumes_outbox") or (preflight.get("contract_summary") or {}).get("consumes_outbox"):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: C3 must not consume outbox")
    if int(((dry_run.get("quality") or {}).get("p0_count") or 0)):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: dry-run has P0 blockers")
    if int(((dry_run.get("payload_validation_summary") or {}).get("blocked_count") or 0)):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: dry-run payload blockers exist")
    if int(((dry_run.get("duplicate_summary") or {}).get("duplicate_candidate_count") or 0)):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: dry-run duplicate candidates exist")


def ensure_clean_c3_target(target_audit: Mapping[str, Any], c3_run_id: str) -> None:
    if target_audit.get("run_exists"):
        raise MinuteBarClosedOutboxExecuteError(f"N3-C3 blocked: c3_run_id already exists: {c3_run_id}")
    for key in ("quality_rows_for_c3_run", "outbox_rows_for_c3_run", "inbox_rows_for_c3_run", "checkpoint_rows_for_c3_run"):
        count = int(target_audit.get(key) or 0)
        if count:
            if "outbox" in key:
                noun = "outbox"
            elif "inbox" in key:
                noun = "inbox"
            elif "checkpoint" in key:
                noun = "checkpoint"
            else:
                noun = "quality"
            raise MinuteBarClosedOutboxExecuteError(f"N3-C3 blocked: {noun} baseline is nonzero for {c3_run_id}")


def ensure_source_runs_passed(snapshot: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    rows = snapshot.get("source_run_rows") or {}
    for run_id in (contract["source_runs"]["source_subscription_run_id"], contract["source_runs"]["c2_run_id"]):
        row = rows.get(run_id)
        if row is None or row.get("status") != "passed":
            raise MinuteBarClosedOutboxExecuteError(f"N3-C3 blocked: source run is not passed: {run_id}")


def build_events_for_execute(
    *,
    summary_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    enrichment_context: Mapping[str, Any],
    c3_run_id: str,
) -> tuple[list[EventEnvelope], list[dict[str, Any]], dict[str, int]]:
    events: list[EventEnvelope] = []
    blockers: list[dict[str, Any]] = []
    excluded = {"missing": 0, "partial": 0, "failed": 0, "total": 0}
    for asset_kind in ASSET_KINDS:
        for summary in summary_rows_by_asset.get(asset_kind, []):
            status = str(summary.get("closed_status") or "")
            if status != "closed":
                if status in excluded:
                    excluded[status] += 1
                    excluded["total"] += 1
                continue
            candidate = build_minute_bar_closed_candidate(
                summary=summary,
                enrichment_context=enrichment_context,
                c3_run_id=c3_run_id,
            )
            if candidate.event is not None:
                events.append(candidate.event)
            if candidate.blocker is not None:
                blockers.append(candidate.blocker)
    return events, blockers, excluded


def summarize_c3_events(
    events: Sequence[EventEnvelope],
    blockers: Sequence[Mapping[str, Any]],
    excluded: Mapping[str, int],
) -> dict[str, Any]:
    duplicate = build_duplicate_summary(events)
    by_asset = Counter(event.asset_kind for event in events)
    by_type = Counter(event.event_type for event in events)
    status = Counter(event.payload_json.get("closed_status") for event in events)
    return {
        "event_count": len(events),
        "event_count_by_asset": {asset_kind: int(by_asset.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}
        | {"total": len(events)},
        "event_count_by_type": dict(by_type),
        "closed_status": dict(status),
        "excluded_by_status": dict(excluded),
        "payload_blocker_count": len(blockers),
        "payload_blockers_by_code": dict(Counter(str(item.get("blocker_code") or "") for item in blockers)),
        "payload_blocker_samples": list(blockers[:20]),
        "duplicate_candidate_count": int(duplicate["duplicate_candidate_count"]),
        "duplicate_key_count": int(duplicate["duplicate_key_count"]),
        "duplicate_keys_sample": duplicate["duplicate_keys_sample"],
    }


def validate_event_summary_against_contract(
    event_summary: Mapping[str, Any],
    contract: Mapping[str, Any],
    dry_run: Mapping[str, Any],
) -> None:
    expected = contract.get("expected_outbox_rows") or {}
    actual_by_asset = event_summary.get("event_count_by_asset") or {}
    for key in (*ASSET_KINDS, "total"):
        if int(actual_by_asset.get(key) or 0) != int(expected.get(key) or 0):
            raise MinuteBarClosedOutboxExecuteError(f"N3-C3 blocked: event count mismatch for {key}")
    dry_candidate = (dry_run.get("candidate_summary") or {}).get("candidate_count_by_asset") or {}
    if int(dry_candidate.get("total") or 0) != int(event_summary.get("event_count") or 0):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: event count differs from dry-run")
    expected_excluded = contract.get("expected_excluded_summary_count") or {}
    actual_excluded = event_summary.get("excluded_by_status") or {}
    for key in ("missing", "partial", "failed", "total"):
        if int(actual_excluded.get(key) or 0) != int(expected_excluded.get(key) or 0):
            raise MinuteBarClosedOutboxExecuteError(f"N3-C3 blocked: excluded count mismatch for {key}")
    if int(event_summary.get("payload_blocker_count") or 0):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: payload blockers exist")
    if int(event_summary.get("duplicate_candidate_count") or 0):
        raise MinuteBarClosedOutboxExecuteError("N3-C3 blocked: duplicate dedup keys exist")


def build_c3_execute_quality_items(
    *,
    contract: Mapping[str, Any],
    event_summary: Mapping[str, Any],
    target_audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    c3_run_id = str(contract["c3_run_id"])
    items: list[dict[str, Any]] = []
    details = {
        "metric_scope": C3_METRIC_SCOPE,
        "c3_run_id": c3_run_id,
        "c2_run_id": contract.get("c2_run_id"),
        "asset_kind": "common",
        "projection_schema_version": C3_QUALITY_SCHEMA_VERSION,
        "previous_day_provenance": contract.get("previous_day_provenance"),
    }
    if target_audit.get("run_exists") or any(
        int(target_audit.get(key) or 0)
        for key in ("quality_rows_for_c3_run", "outbox_rows_for_c3_run", "inbox_rows_for_c3_run", "checkpoint_rows_for_c3_run")
    ):
        items.append(
            quality_row(
                data_domain="common",
                table_name="common_event_outbox",
                gate_code="n3_c3_execute_baseline_zero",
                gate_name="C3 target baseline is zero before execute",
                severity="P0",
                status="failed",
                expected="all scoped rows zero",
                actual=json.dumps(target_audit, ensure_ascii=True, sort_keys=True),
                details=details,
            )
        )
    expected_total = int((contract.get("expected_outbox_rows") or {}).get("total") or 0)
    actual_total = int(event_summary.get("event_count") or 0)
    if actual_total != expected_total:
        items.append(
            quality_row(
                data_domain="common",
                table_name="common_event_outbox",
                gate_code="n3_c3_execute_outbox_rows_match_contract",
                gate_name="MinuteBarClosed outbox rows match contract",
                severity="P0",
                status="failed",
                expected=str(expected_total),
                actual=str(actual_total),
                details=details,
            )
        )
    if int(event_summary.get("payload_blocker_count") or 0):
        items.append(
            quality_row(
                data_domain="common",
                table_name="common_event_outbox",
                gate_code="n3_c3_execute_payload_blockers_zero",
                gate_name="MinuteBarClosed v2 payloads all validate",
                severity="P0",
                status="failed",
                expected="0",
                actual=str(event_summary.get("payload_blocker_count")),
                details=details,
            )
        )
    if int(event_summary.get("duplicate_candidate_count") or 0):
        items.append(
            quality_row(
                data_domain="common",
                table_name="common_event_outbox",
                gate_code="n3_c3_execute_duplicate_dedup_zero",
                gate_name="MinuteBarClosed v2 dedup keys are unique",
                severity="P0",
                status="failed",
                expected="0",
                actual=str(event_summary.get("duplicate_candidate_count")),
                details=details,
            )
        )
    missing = int((event_summary.get("excluded_by_status") or {}).get("missing") or 0)
    if missing:
        items.append(
            quality_row(
                data_domain="stock",
                table_name="stock_closed_30m_summary",
                gate_code="n3_c3_execute_bj_920xxx_missing_excluded",
                gate_name="BJ 920xxx missing summaries are excluded from MinuteBarClosed",
                severity="P1",
                status="warning",
                expected="0 missing excluded",
                actual=str(missing),
                details={**details, "asset_kind": "stock"},
            )
        )
    if not items:
        items.append(
            quality_row(
                data_domain="common",
                table_name="common_event_outbox",
                gate_code="n3_c3_execute_ready",
                gate_name="C3 MinuteBarClosed execute quality passed",
                severity="P2",
                status="passed",
                expected="ready",
                actual="ready",
                details=details,
            )
        )
    return items


def quality_row(
    *,
    data_domain: str,
    table_name: str,
    gate_code: str,
    gate_name: str,
    severity: str,
    status: str,
    expected: str | None,
    actual: str | None,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "data_domain": data_domain,
        "layer_scope": C3_QUALITY_LAYER_SCOPE,
        "table_name": table_name,
        "gate_code": gate_code,
        "gate_name": gate_name,
        "severity": severity,
        "status": status,
        "expected_value": expected,
        "actual_value": actual,
        "identity_key": None,
        "details": dict(details),
    }


def capture_c3_execute_snapshot(
    dsn: str,
    *,
    c3_run_id: str,
    source_subscription_run_id: str,
    c2_run_id: str,
) -> dict[str, Any]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        run_ids = [source_subscription_run_id, c2_run_id, c3_run_id]
        cur.execute(
            """
            SELECT run_id, status, source_condition_run_id, for_trade_date,
                   source_trade_date, prev_trade_date, market_data_pulled,
                   market_data_fact_written, p0_count, p1_count, p2_count,
                   source_scope_row_count, candidate_row_count,
                   subscription_row_count, subscription_object_count, dedup_ratio
            FROM common_market_data_run
            WHERE run_id = ANY(%s)
            """,
            (run_ids,),
        )
        source_run_rows = {row["run_id"]: normalize_row(row) for row in cur.fetchall()}
        target_audit = {
            "run_exists": c3_run_id in source_run_rows,
            "quality_rows_for_c3_run": count_rows_by_run(cur, "common_market_data_quality_item", c3_run_id),
            "outbox_rows_for_c3_run": count_outbox_rows(cur, c3_run_id),
            "inbox_rows_for_c3_run": count_inbox_rows(cur, c3_run_id),
            "checkpoint_rows_for_c3_run": count_checkpoint_rows(cur, c3_run_id),
        }
        cur.execute(
            "SELECT status, count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s GROUP BY status",
            (c3_run_id,),
        )
        outbox_status = {str(row["status"]): int(row["row_count"]) for row in cur.fetchall()}
    return {
        "source_run_rows": source_run_rows,
        "target_audit": target_audit,
        "outbox_status_for_c3_run": outbox_status,
    }


def write_c3_execute_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    events: Sequence[EventEnvelope],
    quality_items: Sequence[Mapping[str, Any]],
    status: str,
    started_at: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
) -> None:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                insert_c3_run(
                    cur,
                    contract=contract,
                    status="running",
                    started_at=started_at,
                    contract_path=contract_path,
                    preflight_path=preflight_path,
                    dry_run_path=dry_run_path,
                )
                repo = EventRepository(cur)
                for event in events:
                    repo.insert_outbox(event)
                insert_c3_quality_items(cur, contract=contract, quality_items=quality_items)
                counts = count_quality_severities(list(quality_items))
                cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status = %s,
                        p0_count = %s,
                        p1_count = %s,
                        p2_count = %s,
                        market_data_pulled = false,
                        market_data_fact_written = false,
                        downstream_layers_touched = false,
                        worker_started = false,
                        finished_at = now(),
                        updated_at = now()
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        counts["P0"],
                        counts["P1"],
                        counts["P2"],
                        contract["c3_run_id"],
                    ),
                )


def insert_c3_run(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    status: str,
    started_at: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
) -> None:
    source_run = fetch_run_for_insert(cur, str(contract["source_runs"]["source_subscription_run_id"]))
    expected = contract["expected_outbox_rows"]
    dates = contract["dates"]
    cur.execute(
        """
        INSERT INTO common_market_data_run (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          prev_trade_date, mode, status, p0_count, p1_count, p2_count,
          source_scope_row_count, candidate_row_count, subscription_row_count,
          subscription_object_count, dedup_ratio, generated_by,
          market_data_pulled, market_data_fact_written,
          downstream_layers_touched, worker_started, started_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, 'execute', %s, 0, 0, 0,
                %s, %s, %s, %s, %s, 'N3-C3-minute-bar-closed-outbox-execute',
                false, false, false, false, %s, %s)
        """,
        (
            contract["c3_run_id"],
            contract["source_runs"]["source_condition_run_id"],
            dates["for_trade_date"],
            dates["source_trade_date"],
            dates["prev_trade_date"],
            status,
            int(source_run.get("source_scope_row_count") or 0),
            int(expected.get("total") or 0),
            int(expected.get("total") or 0),
            int(source_run.get("subscription_object_count") or 0),
            source_run.get("dedup_ratio"),
            started_at,
            Jsonb(
                json_safe(
                    {
                        "stage": "N3-C3",
                        "metric_scope": C3_METRIC_SCOPE,
                        "c3_run_id": contract["c3_run_id"],
                        "c2_run_id": contract["c2_run_id"],
                        "contract_path": contract_path,
                        "preflight_path": preflight_path,
                        "dry_run_path": dry_run_path,
                        "previous_day_provenance": contract.get("previous_day_provenance"),
                        "writes_outbox": True,
                        "consumes_outbox": False,
                        "run_once_only": True,
                        "replay_storm_guard": contract.get("replay_storm_guard"),
                    }
                )
            ),
        ),
    )


def fetch_run_for_insert(cur: Any, run_id: str) -> Mapping[str, Any]:
    cur.execute(
        """
        SELECT source_scope_row_count, candidate_row_count, subscription_row_count,
               subscription_object_count, dedup_ratio
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise MinuteBarClosedOutboxExecuteError(f"N3-C3 blocked: source subscription run missing: {run_id}")
    return row


def insert_c3_quality_items(cur: Any, *, contract: Mapping[str, Any], quality_items: Sequence[Mapping[str, Any]]) -> int:
    if not quality_items:
        return 0
    dates = contract["dates"]
    columns = (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "data_domain",
        "layer_scope",
        "table_name",
        "gate_code",
        "gate_name",
        "severity",
        "status",
        "expected_value",
        "actual_value",
        "identity_key",
        "details",
    )
    values = []
    for item in quality_items:
        values.append(
            (
                contract["c3_run_id"],
                contract["source_runs"]["source_condition_run_id"],
                dates["for_trade_date"],
                dates["source_trade_date"],
                item["data_domain"],
                item["layer_scope"],
                item.get("table_name"),
                item["gate_code"],
                item["gate_name"],
                item["severity"],
                item["status"],
                item.get("expected_value"),
                item.get("actual_value"),
                item.get("identity_key"),
                Jsonb(json_safe(item.get("details") or {})),
            )
        )
    placeholders = ", ".join(["%s"] * len(columns))
    cur.executemany(
        f"""
        INSERT INTO common_market_data_quality_item ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        values,
    )
    return len(values)


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


def rollback_safe_from_snapshot(snapshot: Mapping[str, Any]) -> bool:
    audit = snapshot.get("target_audit") or {}
    status = snapshot.get("outbox_status_for_c3_run") or {}
    return (
        int(audit.get("inbox_rows_for_c3_run") or 0) == 0
        and int(audit.get("checkpoint_rows_for_c3_run") or 0) == 0
        and int(status.get("delivering") or 0) == 0
        and int(status.get("delivered") or 0) == 0
    )


def build_c3_rollback_sql(c3_run_id: str) -> str:
    escaped = c3_run_id.replace("'", "''")
    return f"""-- N3-C3 MinuteBarClosed outbox rollback.
-- Scope: {escaped}
-- Safe only before downstream replay/consumption. Does not touch C2 summaries,
-- C2 delta minute rows, B1/B2/N4/N5 runtime, or user/action/trigger tables.

DO $$
DECLARE
  v_c3_run_id TEXT := '{escaped}';
  v_delivered_count BIGINT;
  v_inbox_count BIGINT;
  v_checkpoint_count BIGINT;
BEGIN
  SELECT count(*) INTO v_delivered_count
  FROM common_event_outbox
  WHERE source_run_id = v_c3_run_id
    AND status IN ('delivering', 'delivered');

  IF v_delivered_count > 0 THEN
    RAISE EXCEPTION 'N3-C3 rollback blocked: delivered/delivering outbox rows exist for %', v_c3_run_id;
  END IF;

  SELECT count(*) INTO v_inbox_count
  FROM common_event_inbox
  WHERE source_run_id = v_c3_run_id;

  IF v_inbox_count > 0 THEN
    RAISE EXCEPTION 'N3-C3 rollback blocked: inbox rows exist for %', v_c3_run_id;
  END IF;

  SELECT count(*) INTO v_checkpoint_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_c3_run_id || '%';

  IF v_checkpoint_count > 0 THEN
    RAISE EXCEPTION 'N3-C3 rollback blocked: checkpoint references exist for %', v_c3_run_id;
  END IF;

  DELETE FROM common_event_outbox WHERE source_run_id = '{escaped}';
  DELETE FROM common_market_data_quality_item WHERE run_id = '{escaped}';
  DELETE FROM common_market_data_run WHERE run_id = '{escaped}';
END $$;
"""


def normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output


def format_c3_execute_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    write = report.get("write_result") or {}
    event_summary = report.get("event_summary") or {}
    side = report.get("side_effects") or {}
    lines = [
        "# N3-C3 MinuteBarClosed Outbox Execute Report",
        "",
        "## Summary",
        "",
        f"- result: `{report.get('result')}`",
        f"- layer_role: `{report.get('layer_role')}`",
        f"- c3_run_id: `{report.get('c3_run_id')}`",
        f"- c2_run_id: `{report.get('c2_run_id')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- outbox_rows_written: `{write.get('outbox_rows_written')}`",
        f"- event_type_counts: `{write.get('event_type_counts')}`",
        f"- excluded_by_status: `{event_summary.get('excluded_by_status')}`",
        f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
        f"- rollback_safe: `{(report.get('rollback') or {}).get('rollback_safe')}`",
        "",
        "## Boundary",
        "",
        f"- event_outbox_written: `{side.get('event_outbox_written')}`",
        f"- outbox_consumed: `{side.get('outbox_consumed')}`",
        f"- inbox_or_checkpoint_written: `{side.get('inbox_or_checkpoint_written')}`",
        f"- downstream_layers_touched: `{side.get('downstream_layers_touched')}`",
        f"- worker_started: `{side.get('worker_started')}`",
        "",
    ]
    return "\n".join(lines)
