"""N3-C2B closed signal enrichment run-once executor.

The executor writes the reviewed C2B enrichment facts only after explicit
double confirmation. It does not write or consume event outbox/inbox rows, does
not update C2 summaries/minute bars/snapshots/projections, and does not enter
N4/N5/N6.
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
from ashare_v3.market.closed_signal_enrichment_plan import (
    ASSET_KINDS,
    CALCULATION_CONFIG_HASH,
    ENRICHMENT_TABLES,
    calculate_enrichment_candidate,
    fetch_runtime_context,
    json_safe,
)
from ashare_v3.market.previous_day_preload_execute import utc_now_iso, write_json, write_text


DEFAULT_C2B_CONTRACT_JSON_PATH = "docs/N3_C2B_closed_signal_enrichment_execute_contract.json"
DEFAULT_C2B_PREFLIGHT_JSON_PATH = "docs/N3_C2B_closed_signal_enrichment_execute_preflight.json"
DEFAULT_C2B_DRY_RUN_JSON_PATH = "docs/N3_C2B_closed_signal_enrichment_dry_run_report.json"
DEFAULT_C2B_JSON_REPORT_PATH = "docs/N3_C2B_closed_signal_enrichment_execute_report.json"
DEFAULT_C2B_MD_REPORT_PATH = "docs/N3_C2B_CLOSED_SIGNAL_ENRICHMENT_EXECUTE_REPORT.md"
DEFAULT_C2B_ROLLBACK_SQL_PATH = "sql/N3_C2B_closed_signal_enrichment_business_rollback.sql"

C2B_CONTRACT_STAGE = "N3-C2B-closed-signal-enrichment-execute-contract"
C2B_PREFLIGHT_STAGE = "N3-C2B-closed-signal-enrichment-execute-preflight"
C2B_METRIC_SCOPE = "closed_signal_enrichment"
C2B_QUALITY_SCHEMA_VERSION = "n3.closed_signal_enrichment.v1"
C2B_QUALITY_LAYER_SCOPE = "market_data_run"
ALLOWED_QUALITY_DATA_DOMAINS = ("common", "stock", "index", "board")
ALLOWED_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_closed_30m_signal_enrichment",
    "index_closed_30m_signal_enrichment",
    "board_closed_30m_signal_enrichment",
)
FORBIDDEN_WRITE_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
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
    "condition tables",
    "trigger tables",
    "action tables",
    "user tables",
    "voice/mobile/sim/position tables",
    "N4/N5/N6",
    "worker",
    "old system",
)


class ClosedSignalEnrichmentExecuteError(RuntimeError):
    """Raised when C2B execute violates its reviewed contract."""


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_closed_signal_enrichment_execute(
    *,
    dsn: str,
    contract_path: str = DEFAULT_C2B_CONTRACT_JSON_PATH,
    preflight_path: str = DEFAULT_C2B_PREFLIGHT_JSON_PATH,
    dry_run_path: str = DEFAULT_C2B_DRY_RUN_JSON_PATH,
    json_report_path: str = DEFAULT_C2B_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_C2B_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_C2B_ROLLBACK_SQL_PATH,
    c2b_run_id: str | None = None,
    for_trade_date: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    contract = read_json(contract_path)
    preflight = read_json(preflight_path)
    dry_run = read_json(dry_run_path)
    ensure_c2b_execute_contract(
        contract,
        preflight,
        dry_run,
        execute=execute,
        user_confirmed=user_confirmed,
        c2b_run_id=c2b_run_id,
        for_trade_date=for_trade_date,
    )
    resolved_run_id = str(contract["c2b_run_id"])
    lineage = contract["lineage"]

    pre_execute = capture_c2b_execute_snapshot(dsn, contract=contract)
    ensure_clean_c2b_target(pre_execute["target_audit"], resolved_run_id)
    ensure_c2b_source_runs_passed(pre_execute, contract)

    if progress_callback:
        progress_callback("N3-C2B building closed signal enrichment rows")
    rows = build_enrichment_rows_for_execute(dsn=dsn, contract=contract)
    row_summary = summarize_enrichment_rows(rows)
    validate_rows_against_dry_run(row_summary, dry_run)
    validate_rows_against_contract(row_summary, contract)
    quality_items = build_c2b_execute_quality_items(
        contract=contract,
        row_summary=row_summary,
        target_audit=pre_execute["target_audit"],
    )
    quality_counts = count_quality_severities(quality_items)
    if quality_counts["P0"]:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: P0 quality blockers present before write")

    started_at = utc_now_iso()
    if progress_callback:
        progress_callback(f"N3-C2B writing {row_summary['total_rows']} enrichment rows")
    write_c2b_execute_transaction(
        dsn=dsn,
        contract=contract,
        rows=rows,
        quality_items=quality_items,
        status="passed",
        started_at=started_at,
        contract_path=contract_path,
        preflight_path=preflight_path,
        dry_run_path=dry_run_path,
    )
    post_execute = capture_c2b_execute_snapshot(dsn, contract=contract)
    rollback_sql = build_c2b_rollback_sql(resolved_run_id)
    write_text(rollback_sql_path, rollback_sql)

    report = {
        "stage": "N3-C2B",
        "layer_role": "N3_market_data",
        "execution_mode": "closed_signal_enrichment_run_once_execute",
        "result": "EXECUTED",
        "c2b_run_id": resolved_run_id,
        "c2_run_id": lineage["c2_run_id"],
        "source_condition_run_id": lineage["source_condition_run_id"],
        "source_subscription_run_id": lineage["source_subscription_run_id"],
        "source_previous_day_minute_run_id": lineage["source_previous_day_minute_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "paths": {
            "contract_path": contract_path,
            "preflight_path": preflight_path,
            "dry_run_path": dry_run_path,
            "rollback_sql_path": rollback_sql_path,
        },
        "write_result": {
            "enrichment_rows_written": row_summary["total_rows"],
            "enrichment_rows_by_asset": row_summary["rows_by_asset"] | {"total": row_summary["total_rows"]},
            "quality_rows_written": len(quality_items),
            "run_rows_written": 1,
            "writes_outbox": False,
            "outbox_rows_written": 0,
        },
        "row_summary": row_summary,
        "n4_replay_unblock_estimate": dry_run.get("n4_replay_unblock_estimate"),
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
            "enrichment_rows_written": True,
            "quality_written": True,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "inbox_or_checkpoint_written": False,
            "closed_30m_summary_modified": False,
            "minute_bar_modified": False,
            "realtime_projection_modified": False,
            "realtime_snapshot_modified": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "next_allowed_step": "N3-C2B execute post-review",
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_c2b_execute_report(report))
    return report


def ensure_c2b_execute_contract(
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    *,
    execute: bool,
    user_confirmed: bool,
    c2b_run_id: str | None,
    for_trade_date: str | None,
) -> None:
    if not execute:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B closed signal enrichment execute requires explicit --execute")
    if not user_confirmed:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B closed signal enrichment execute requires explicit --user-confirmed")
    if str(contract.get("stage") or "") != C2B_CONTRACT_STAGE:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: contract stage mismatch")
    if contract.get("layer_role") != "N3_market_data":
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: contract layer_role mismatch")
    if not contract.get("runner_exists") or contract.get("runner_readiness") != "ready":
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: runner readiness is not ready")
    if str(preflight.get("stage") or "") != C2B_PREFLIGHT_STAGE:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: preflight stage mismatch")
    if preflight.get("result") != "PREFLIGHT_PASS":
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: preflight did not pass")
    if preflight.get("runner_readiness") != "ready":
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: preflight runner readiness is not ready")
    if dry_run.get("result") != "DRY_RUN_PASS":
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: dry-run did not pass")
    contract_run_id = str(contract.get("c2b_run_id") or "")
    if c2b_run_id and c2b_run_id != contract_run_id:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: CLI c2b_run_id does not match contract")
    if preflight.get("c2b_run_id") != contract_run_id or dry_run.get("c2b_run_id") != contract_run_id:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: c2b_run_id mismatch")
    contract_trade_date = str(contract.get("for_trade_date") or "")
    if for_trade_date and for_trade_date != contract_trade_date:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: CLI for_trade_date does not match contract")
    if dry_run.get("for_trade_date") != contract_trade_date:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: dry-run for_trade_date mismatch")
    if contract.get("writes_outbox") or preflight.get("writes_outbox"):
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: writes_outbox must be false")
    if contract.get("consumes_c3_outbox") or preflight.get("consumes_c3_outbox"):
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: C2B must not consume C3 outbox")
    if int(((dry_run.get("quality") or {}).get("p0_count") or 0)):
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: dry-run has P0 blockers")


def ensure_clean_c2b_target(target_audit: Mapping[str, Any], c2b_run_id: str) -> None:
    if target_audit.get("run_exists"):
        raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: c2b_run_id already exists: {c2b_run_id}")
    counts = target_audit.get("enrichment_rows_for_c2b_run") or {}
    if sum(int(counts.get(asset_kind) or 0) for asset_kind in ASSET_KINDS):
        raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: enrichment baseline is nonzero for {c2b_run_id}")
    for key in ("quality_rows_for_c2b_run", "outbox_rows_for_c2b_run", "inbox_rows_for_c2b_run", "checkpoint_rows_for_c2b_run"):
        count = int(target_audit.get(key) or 0)
        if count:
            noun = key.replace("_rows_for_c2b_run", "").replace("quality", "quality").replace("checkpoint", "checkpoint")
            raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: {noun} baseline is nonzero for {c2b_run_id}")


def ensure_c2b_source_runs_passed(snapshot: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    condition_rows = snapshot.get("source_condition_rows") or {}
    market_rows = snapshot.get("source_market_run_rows") or {}
    lineage = contract["lineage"]
    condition_id = str(lineage["source_condition_run_id"])
    condition_row = condition_rows.get(condition_id)
    if condition_row is None or condition_row.get("status") != "passed":
        raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: source condition run is not passed: {condition_id}")
    for key in ("source_subscription_run_id", "c2_run_id", "source_previous_day_minute_run_id"):
        run_id = str(lineage[key])
        row = market_rows.get(run_id)
        if row is None or row.get("status") != "passed":
            raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: source market run is not passed: {run_id}")


def build_enrichment_rows_for_execute(*, dsn: str, contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    lineage = contract["lineage"]
    runtime = fetch_runtime_context(
        dsn=dsn,
        c2b_run_id=str(contract["c2b_run_id"]),
        c2_run_id=str(lineage["c2_run_id"]),
        source_previous_day_minute_run_id=str(lineage["source_previous_day_minute_run_id"]),
        previous_day_minute_date=str(lineage["previous_day_minute_date"]),
    )
    rows: list[dict[str, Any]] = []
    for asset_kind in ASSET_KINDS:
        baselines = runtime["baseline_buckets_by_asset"].get(asset_kind, {})
        for summary in runtime["summary_rows_by_asset"].get(asset_kind, []):
            identity_key = str(summary.get("identity_key") or "")
            bucket_id = str(summary.get("bucket_id") or "")
            rows.append(
                calculate_enrichment_candidate(
                    summary,
                    baselines.get((identity_key, bucket_id)),
                    c2b_run_id=str(contract["c2b_run_id"]),
                    source_previous_day_minute_run_id=str(lineage["source_previous_day_minute_run_id"]),
                    previous_day_minute_date=str(lineage["previous_day_minute_date"]),
                )
            )
    return rows


def summarize_enrichment_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_asset = Counter(str(row.get("asset_kind") or "") for row in rows)
    signal = Counter(str(row.get("closed_signal_status") or "") for row in rows)
    quality = Counter(str(row.get("closed_signal_quality_status") or "") for row in rows)
    price_direction = Counter(str(row.get("closed_price_direction_status") or "") for row in rows)
    unknown_rows = int(signal.get("unknown") or 0)
    missing_rows = int(quality.get("missing") or 0)
    baseline_missing_rows = sum(
        1
        for row in rows
        if "baseline_status" in (row.get("closed_signal_basis_json") or {})
        and (row.get("closed_signal_basis_json") or {}).get("baseline_status") != "passed"
    )
    computable_rows = sum(
        1
        for row in rows
        if str(row.get("closed_signal_status") or "") != "unknown"
        and str(row.get("closed_signal_quality_status") or "") == "passed"
    )
    return {
        "total_rows": len(rows),
        "rows_by_asset": {asset_kind: int(by_asset.get(asset_kind) or 0) for asset_kind in ASSET_KINDS},
        "signal_distribution": dict(signal),
        "quality_distribution": dict(quality),
        "price_direction_distribution": dict(price_direction),
        "computable_rows": int(computable_rows),
        "unknown_rows": unknown_rows,
        "missing_rows": missing_rows,
        "baseline_missing_rows": int(baseline_missing_rows),
    }


def validate_rows_against_dry_run(row_summary: Mapping[str, Any], dry_run: Mapping[str, Any]) -> None:
    dry_counts = dry_run.get("current_summary_rows") or dry_run.get("expected_rows") or {}
    actual_counts = dict(row_summary.get("rows_by_asset") or {})
    actual_counts["total"] = int(row_summary.get("total_rows") or 0)
    for key in (*ASSET_KINDS, "total"):
        if int(actual_counts.get(key) or 0) != int(dry_counts.get(key) or 0):
            raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: row count mismatch for {key}")
    expected_signal = dict(dry_run.get("signal_distribution") or {})
    if dict(row_summary.get("signal_distribution") or {}) != expected_signal:
        raise ClosedSignalEnrichmentExecuteError("N3-C2B blocked: signal distribution differs from dry-run")
    for key in ("computable_rows", "unknown_rows", "missing_rows", "baseline_missing_rows"):
        if key in dry_run and int(row_summary.get(key) or 0) != int(dry_run.get(key) or 0):
            raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: {key} differs from dry-run")


def validate_rows_against_contract(row_summary: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    expected = contract.get("expected_enrichment_rows") or {}
    actual = dict(row_summary.get("rows_by_asset") or {})
    actual["total"] = int(row_summary.get("total_rows") or 0)
    for key in (*ASSET_KINDS, "total"):
        if int(actual.get(key) or 0) != int(expected.get(key) or 0):
            raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: enrichment row count mismatch for {key}")


def build_c2b_execute_quality_items(
    *,
    contract: Mapping[str, Any],
    row_summary: Mapping[str, Any],
    target_audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    c2b_run_id = str(contract["c2b_run_id"])
    expected = contract.get("expected_enrichment_rows") or {}
    actual_counts = dict(row_summary.get("rows_by_asset") or {})
    actual_counts["total"] = int(row_summary.get("total_rows") or 0)
    details = {
        "metric_scope": C2B_METRIC_SCOPE,
        "c2b_run_id": c2b_run_id,
        "c2_run_id": (contract.get("lineage") or {}).get("c2_run_id"),
        "source_previous_day_minute_run_id": (contract.get("lineage") or {}).get("source_previous_day_minute_run_id"),
        "asset_kind": "common",
        "projection_schema_version": C2B_QUALITY_SCHEMA_VERSION,
    }
    items: list[dict[str, Any]] = [
        quality_row(
            data_domain="common",
            table_name="common_market_data_run",
            gate_code="n3_c2b_execute_baseline_zero",
            gate_name="C2B target baseline is zero before execute",
            severity="P0",
            status="passed",
            expected="all scoped rows zero",
            actual=json.dumps(json_safe(target_audit), ensure_ascii=False, sort_keys=True),
            details=details,
        ),
        quality_row(
            data_domain="common",
            table_name="stock/index/board_closed_30m_signal_enrichment",
            gate_code="n3_c2b_execute_rows_match_contract",
            gate_name="C2B enrichment rows match contract counts",
            severity="P0",
            status="passed" if actual_counts == expected else "failed",
            expected=json.dumps(expected, ensure_ascii=False, sort_keys=True),
            actual=json.dumps(actual_counts, ensure_ascii=False, sort_keys=True),
            details=details,
        ),
        quality_row(
            data_domain="common",
            table_name="stock/index/board_closed_30m_signal_enrichment",
            gate_code="n3_c2b_execute_signal_distribution_reviewed",
            gate_name="C2B signal distribution is reviewed and explicit",
            severity="P2",
            status="passed",
            expected="reviewed distribution",
            actual=json.dumps(row_summary.get("signal_distribution") or {}, ensure_ascii=False, sort_keys=True),
            details=details,
        ),
    ]
    if target_audit.get("run_exists") or sum(
        int((target_audit.get("enrichment_rows_for_c2b_run") or {}).get(asset_kind) or 0) for asset_kind in ASSET_KINDS
    ) or any(
        int(target_audit.get(key) or 0)
        for key in ("quality_rows_for_c2b_run", "outbox_rows_for_c2b_run", "inbox_rows_for_c2b_run", "checkpoint_rows_for_c2b_run")
    ):
        items.append(
            quality_row(
                data_domain="common",
                table_name="stock/index/board_closed_30m_signal_enrichment",
                gate_code="n3_c2b_execute_target_nonzero_blocker",
                gate_name="C2B scoped target rows must be zero before execute",
                severity="P0",
                status="failed",
                expected="all scoped rows zero",
                actual=json.dumps(json_safe(target_audit), ensure_ascii=False, sort_keys=True),
                details=details,
            )
        )
    if int(row_summary.get("unknown_rows") or 0):
        items.append(
            quality_row(
                data_domain="stock",
                table_name="stock_closed_30m_signal_enrichment",
                gate_code="n3_c2b_unknown_signal_rows_visible",
                gate_name="unknown closed signal rows remain explicit",
                severity="P1",
                status="warning",
                expected="0 unknown rows",
                actual=str(row_summary.get("unknown_rows")),
                details={**details, "asset_kind": "stock"},
            )
        )
    if int(row_summary.get("missing_rows") or 0):
        items.append(
            quality_row(
                data_domain="stock",
                table_name="stock_closed_30m_signal_enrichment",
                gate_code="n3_c2b_missing_current_rows_visible",
                gate_name="missing current summary rows remain explicit",
                severity="P1",
                status="warning",
                expected="0 missing rows",
                actual=str(row_summary.get("missing_rows")),
                details={**details, "asset_kind": "stock"},
            )
        )
    if int(row_summary.get("baseline_missing_rows") or 0):
        items.append(
            quality_row(
                data_domain="stock",
                table_name="stock_closed_30m_signal_enrichment",
                gate_code="n3_c2b_baseline_missing_rows_visible",
                gate_name="baseline missing/zero rows remain unknown and must not be inferred by N4",
                severity="P1",
                status="warning",
                expected="0 baseline missing rows",
                actual=str(row_summary.get("baseline_missing_rows")),
                details={**details, "asset_kind": "stock"},
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
    if data_domain not in ALLOWED_QUALITY_DATA_DOMAINS:
        raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: illegal quality data_domain: {data_domain}")
    return {
        "data_domain": data_domain,
        "layer_scope": C2B_QUALITY_LAYER_SCOPE,
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


def build_c2b_execute_preflight(
    *,
    dsn: str,
    contract_path: str = DEFAULT_C2B_CONTRACT_JSON_PATH,
    dry_run_path: str = DEFAULT_C2B_DRY_RUN_JSON_PATH,
    rollback_sql_path: str = DEFAULT_C2B_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    contract = read_json(contract_path)
    dry_run = read_json(dry_run_path)
    snapshot = capture_c2b_execute_snapshot(dsn, contract=contract)
    blockers: list[str] = []
    if dry_run.get("result") != "DRY_RUN_PASS":
        blockers.append("dry_run_not_passed")
    try:
        ensure_clean_c2b_target(snapshot["target_audit"], str(contract.get("c2b_run_id") or ""))
    except ClosedSignalEnrichmentExecuteError as exc:
        blockers.append(str(exc))
    try:
        ensure_c2b_source_runs_passed(snapshot, contract)
    except ClosedSignalEnrichmentExecuteError as exc:
        blockers.append(str(exc))
    if not Path(rollback_sql_path).exists():
        blockers.append("rollback_sql_missing")
    if not contract.get("runner_exists") or contract.get("runner_readiness") != "ready":
        blockers.append("runner_not_ready")
    if contract.get("writes_outbox") or contract.get("consumes_c3_outbox"):
        blockers.append("outbox_boundary_violation")

    result = "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS"
    return {
        "stage": C2B_PREFLIGHT_STAGE,
        "layer_role": "N3_market_data",
        "result": result,
        "blocked": bool(blockers),
        "blockers": blockers,
        "runner_exists": True,
        "runner_readiness": "ready",
        "execute_authorized": False,
        "c2b_execute_allowed_now": False,
        "c2b_execute_allowed_reason": "awaiting_final_gate_user_confirmation" if not blockers else "preflight_blocked",
        "c2b_run_id": contract.get("c2b_run_id"),
        "for_trade_date": contract.get("for_trade_date"),
        "lineage": contract.get("lineage"),
        "baseline_guard": snapshot["target_audit"],
        "source_condition_rows": snapshot.get("source_condition_rows"),
        "source_market_run_rows": snapshot.get("source_market_run_rows"),
        "c3_outbox_status": snapshot.get("c3_outbox_status"),
        "expected_enrichment_rows": contract.get("expected_enrichment_rows"),
        "dry_run_rows": dry_run.get("current_summary_rows"),
        "expected_distribution": {
            "computable_rows": dry_run.get("computable_rows"),
            "unknown_rows": dry_run.get("unknown_rows"),
            "missing_rows": dry_run.get("missing_rows"),
            "baseline_missing_rows": dry_run.get("baseline_missing_rows"),
            "signal_distribution": dry_run.get("signal_distribution"),
        },
        "n4_replay_unblock_estimate": dry_run.get("n4_replay_unblock_estimate"),
        "allowed_writes": list(ALLOWED_WRITE_TABLES),
        "forbidden_writes": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_c3_outbox": False,
        "rollback_sql_path": rollback_sql_path,
        "side_effects": {
            "read_only_database_checks": True,
            "writes_performed": False,
            "enrichment_rows_written": False,
            "quality_written": False,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "inbox_or_checkpoint_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "next_allowed_step": "C2B execute final gate" if not blockers else "fix C2B preflight blockers",
    }


def capture_c2b_execute_snapshot(dsn: str, *, contract: Mapping[str, Any]) -> dict[str, Any]:
    c2b_run_id = str(contract["c2b_run_id"])
    lineage = contract["lineage"]
    market_run_ids = [
        str(lineage["source_subscription_run_id"]),
        str(lineage["c2_run_id"]),
        str(lineage["source_previous_day_minute_run_id"]),
        c2b_run_id,
    ]
    c3_run_id = str(lineage.get("c3_run_id") or "")
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
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
            (market_run_ids,),
        )
        market_rows = {row["run_id"]: normalize_row(row) for row in cur.fetchall()}
        cur.execute(
            "SELECT run_id, status FROM common_condition_run WHERE run_id = %s",
            (str(lineage["source_condition_run_id"]),),
        )
        condition_rows = {row["run_id"]: normalize_row(row) for row in cur.fetchall()}
        target_audit = fetch_target_audit(cur, c2b_run_id)
        cur.execute(
            "SELECT status, count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s GROUP BY status",
            (c3_run_id,),
        )
        c3_outbox_status = {str(row["status"]): int(row["row_count"]) for row in cur.fetchall()}
    return {
        "source_market_run_rows": market_rows,
        "source_condition_rows": condition_rows,
        "target_audit": target_audit,
        "c3_outbox_status": c3_outbox_status,
    }


def fetch_target_audit(cur: Any, c2b_run_id: str) -> dict[str, Any]:
    enrichment_counts = {}
    for asset_kind in ASSET_KINDS:
        table = ENRICHMENT_TABLES[asset_kind]
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table} WHERE c2b_run_id = %s", (c2b_run_id,))
        enrichment_counts[asset_kind] = int(cur.fetchone()["row_count"])
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_market_data_run WHERE run_id = %s", (c2b_run_id,))
    run_exists = int(cur.fetchone()["row_count"]) > 0
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_market_data_quality_item WHERE run_id = %s", (c2b_run_id,))
    quality_rows = int(cur.fetchone()["row_count"])
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s", (c2b_run_id,))
    outbox_rows = int(cur.fetchone()["row_count"])
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id = %s", (c2b_run_id,))
    inbox_rows = int(cur.fetchone()["row_count"])
    cur.execute(
        "SELECT count(*)::bigint AS row_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::TEXT LIKE %s",
        (f"%{c2b_run_id}%",),
    )
    checkpoint_rows = int(cur.fetchone()["row_count"])
    return {
        "run_exists": run_exists,
        "enrichment_rows_for_c2b_run": enrichment_counts,
        "quality_rows_for_c2b_run": quality_rows,
        "outbox_rows_for_c2b_run": outbox_rows,
        "inbox_rows_for_c2b_run": inbox_rows,
        "checkpoint_rows_for_c2b_run": checkpoint_rows,
    }


def write_c2b_execute_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
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
                insert_c2b_run(
                    cur,
                    contract=contract,
                    status="running",
                    started_at=started_at,
                    contract_path=contract_path,
                    preflight_path=preflight_path,
                    dry_run_path=dry_run_path,
                )
                insert_enrichment_rows(cur, rows)
                insert_c2b_quality_items(cur, contract=contract, quality_items=quality_items)
                counts = count_quality_severities(list(quality_items))
                cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status = %s,
                        p0_count = %s,
                        p1_count = %s,
                        p2_count = %s,
                        market_data_pulled = false,
                        market_data_fact_written = true,
                        downstream_layers_touched = false,
                        worker_started = false,
                        finished_at = now(),
                        updated_at = now()
                    WHERE run_id = %s
                    """,
                    (status, counts["P0"], counts["P1"], counts["P2"], contract["c2b_run_id"]),
                )


def insert_c2b_run(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    status: str,
    started_at: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
) -> None:
    source_run = fetch_source_subscription_run(cur, str(contract["lineage"]["source_subscription_run_id"]))
    expected = contract["expected_enrichment_rows"]
    metadata = contract.get("run_metadata") or {}
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
                %s, %s, %s, %s, %s, 'N3-C2B-closed-signal-enrichment-execute',
                false, false, false, false, %s, %s)
        """,
        (
            contract["c2b_run_id"],
            contract["lineage"]["source_condition_run_id"],
            contract["for_trade_date"],
            metadata.get("source_trade_date"),
            metadata.get("prev_trade_date"),
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
                        "stage": "N3-C2B",
                        "metric_scope": C2B_METRIC_SCOPE,
                        "c2b_run_id": contract["c2b_run_id"],
                        "lineage": contract["lineage"],
                        "contract_path": contract_path,
                        "preflight_path": preflight_path,
                        "dry_run_path": dry_run_path,
                        "calculation_config_hash": CALCULATION_CONFIG_HASH,
                        "writes_outbox": False,
                        "consumes_c3_outbox": False,
                        "run_once_only": True,
                    }
                )
            ),
        ),
    )


def fetch_source_subscription_run(cur: Any, run_id: str) -> Mapping[str, Any]:
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
        raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: source subscription run missing: {run_id}")
    return row


def insert_enrichment_rows(cur: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for asset_kind in ASSET_KINDS:
        table_name = ENRICHMENT_TABLES[asset_kind]
        asset_rows = [row for row in rows if row.get("asset_kind") == asset_kind]
        if not asset_rows:
            continue
        columns = (
            "c2b_run_id",
            "c2_run_id",
            "current_summary_id",
            "source_condition_run_id",
            "source_subscription_run_id",
            "source_previous_day_minute_run_id",
            "for_trade_date",
            "trade_date",
            "asset_kind",
            "identity_key",
            "exchange",
            "code",
            "display_code",
            "name",
            "bucket_id",
            "bucket_start",
            "bucket_end",
            "current_window_amount",
            "baseline_window_amount",
            "closed_amount_ratio",
            "closed_price_change_pct",
            "closed_price_direction_status",
            "closed_market_shape_status",
            "closed_signal_status",
            "closed_signal_quality_status",
            "closed_signal_basis_json",
            "baseline_trace_json",
            "calculation_config_hash",
            "raw_json",
        )
        values = [
            (
                row["c2b_run_id"],
                row["c2_run_id"],
                row["current_summary_id"],
                row["source_condition_run_id"],
                row["source_subscription_run_id"],
                row["source_previous_day_minute_run_id"],
                row["for_trade_date"],
                row["trade_date"],
                row["asset_kind"],
                row["identity_key"],
                row["exchange"],
                row["code"],
                row.get("display_code"),
                row.get("name"),
                row["bucket_id"],
                row["bucket_start"],
                row["bucket_end"],
                row.get("current_window_amount"),
                row.get("baseline_window_amount"),
                row.get("closed_amount_ratio"),
                row.get("closed_price_change_pct"),
                row["closed_price_direction_status"],
                row["closed_market_shape_status"],
                row["closed_signal_status"],
                row["closed_signal_quality_status"],
                Jsonb(json_safe(row["closed_signal_basis_json"])),
                Jsonb(json_safe(row["baseline_trace_json"])),
                row["calculation_config_hash"],
                Jsonb(json_safe(row.get("raw_json") or {})),
            )
            for row in asset_rows
        ]
        cur.executemany(
            f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
            """,
            values,
        )
        count += len(values)
    return count


def insert_c2b_quality_items(cur: Any, *, contract: Mapping[str, Any], quality_items: Sequence[Mapping[str, Any]]) -> int:
    if not quality_items:
        return 0
    metadata = contract.get("run_metadata") or {}
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
        data_domain = str(item.get("data_domain") or "common")
        if data_domain not in ALLOWED_QUALITY_DATA_DOMAINS:
            raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: illegal quality data_domain: {data_domain}")
        layer_scope = str(item.get("layer_scope") or C2B_QUALITY_LAYER_SCOPE)
        if layer_scope != C2B_QUALITY_LAYER_SCOPE:
            raise ClosedSignalEnrichmentExecuteError(f"N3-C2B blocked: illegal quality layer_scope: {layer_scope}")
        details = dict(item.get("details") or {})
        details.setdefault("metric_scope", C2B_METRIC_SCOPE)
        details.setdefault("c2b_run_id", contract["c2b_run_id"])
        details.setdefault("projection_schema_version", C2B_QUALITY_SCHEMA_VERSION)
        values.append(
            (
                contract["c2b_run_id"],
                contract["lineage"]["source_condition_run_id"],
                contract["for_trade_date"],
                metadata.get("source_trade_date"),
                data_domain,
                layer_scope,
                item.get("table_name"),
                item.get("gate_code"),
                item.get("gate_name"),
                item.get("severity"),
                item.get("status"),
                item.get("expected_value"),
                item.get("actual_value"),
                item.get("identity_key"),
                Jsonb(json_safe(details)),
            )
        )
    cur.executemany(
        f"""
        INSERT INTO common_market_data_quality_item ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        values,
    )
    return len(values)


def build_c2b_rollback_sql(c2b_run_id: str) -> str:
    escaped = c2b_run_id.replace("'", "''")
    return f"""-- N3-C2B closed signal enrichment business rollback.
-- Scope: {escaped}
-- Deletes only C2B enrichment facts, quality rows, and run metadata.
-- Does not touch C2 summary, C2 delta minute rows, C3 outbox, B1/B2/N4/N5 runtime, or downstream layers.

DO $$
DECLARE
  v_c2b_run_id TEXT := '{escaped}';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_c2b_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2B rollback: common_event_outbox has % rows for %', v_count, v_c2b_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_c2b_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2B rollback: common_event_inbox has % rows for %', v_count, v_c2b_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_c2b_run_id || '%';

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2B rollback: common_event_consumer_checkpoint references % in % rows', v_c2b_run_id, v_count;
  END IF;
END $$;

DELETE FROM board_closed_30m_signal_enrichment WHERE c2b_run_id = '{escaped}';
DELETE FROM index_closed_30m_signal_enrichment WHERE c2b_run_id = '{escaped}';
DELETE FROM stock_closed_30m_signal_enrichment WHERE c2b_run_id = '{escaped}';
DELETE FROM common_market_data_quality_item WHERE run_id = '{escaped}';
DELETE FROM common_market_data_run WHERE run_id = '{escaped}';
"""


def rollback_safe_from_snapshot(snapshot: Mapping[str, Any]) -> bool:
    audit = snapshot.get("target_audit") or {}
    return (
        int(audit.get("outbox_rows_for_c2b_run") or 0) == 0
        and int(audit.get("inbox_rows_for_c2b_run") or 0) == 0
        and int(audit.get("checkpoint_rows_for_c2b_run") or 0) == 0
    )


def write_c2b_execute_preflight_files(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    write_json(json_path, report)
    write_text(markdown_path, format_c2b_preflight_report(report))


def format_c2b_preflight_report(report: Mapping[str, Any]) -> str:
    expected = report.get("expected_enrichment_rows") or {}
    distribution = (report.get("expected_distribution") or {}).get("signal_distribution") or {}
    return "\n".join(
        [
            "# N3-C2B Closed Signal Enrichment Execute Preflight",
            "",
            f"- result: `{report.get('result')}`",
            f"- layer_role: `{report.get('layer_role')}`",
            f"- c2b_run_id: `{report.get('c2b_run_id')}`",
            f"- runner_readiness: `{report.get('runner_readiness')}`",
            f"- execute_authorized: `{report.get('execute_authorized')}`",
            f"- c2b_execute_allowed_now: `{report.get('c2b_execute_allowed_now')}`",
            f"- c2b_execute_allowed_reason: `{report.get('c2b_execute_allowed_reason')}`",
            f"- blockers: `{report.get('blockers')}`",
            f"- expected_enrichment_rows: `{expected}`",
            f"- signal_distribution: `{distribution}`",
            f"- baseline_guard: `{report.get('baseline_guard')}`",
            f"- c3_outbox_status: `{report.get('c3_outbox_status')}`",
            f"- writes_outbox: `{report.get('writes_outbox')}`",
            f"- consumes_c3_outbox: `{report.get('consumes_c3_outbox')}`",
            f"- rollback_sql_path: `{report.get('rollback_sql_path')}`",
            "",
            "## Boundary",
            "",
            f"- allowed_writes: `{report.get('allowed_writes')}`",
            f"- forbidden_writes: `{report.get('forbidden_writes')}`",
            f"- side_effects: `{report.get('side_effects')}`",
            "",
        ]
    )


def format_c2b_execute_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    write = report.get("write_result") or {}
    summary = report.get("row_summary") or {}
    side = report.get("side_effects") or {}
    return "\n".join(
        [
            "# N3-C2B Closed Signal Enrichment Execute Report",
            "",
            "## Summary",
            "",
            f"- result: `{report.get('result')}`",
            f"- layer_role: `{report.get('layer_role')}`",
            f"- c2b_run_id: `{report.get('c2b_run_id')}`",
            f"- c2_run_id: `{report.get('c2_run_id')}`",
            f"- for_trade_date: `{report.get('for_trade_date')}`",
            f"- enrichment_rows_written: `{write.get('enrichment_rows_written')}`",
            f"- enrichment_rows_by_asset: `{write.get('enrichment_rows_by_asset')}`",
            f"- signal_distribution: `{summary.get('signal_distribution')}`",
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
    )


def normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output
