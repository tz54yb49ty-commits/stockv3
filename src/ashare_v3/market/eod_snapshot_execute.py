"""N3-EOD snapshot refresh run-once executor.

The executor materializes settlement / official close confirmation facts only
after explicit double confirmation. It does not write or consume event
outbox/inbox/checkpoint rows, does not update realtime snapshot/projection,
minute, closed summary, or C2B facts, and does not enter N4/N5/N6.
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
from ashare_v3.market.eod_snapshot_plan import (
    ASSET_KINDS,
    CLOSED_SIGNAL_TABLES,
    CLOSED_SUMMARY_TABLES,
    EOD_RECONCILIATION_TABLES,
    EOD_SNAPSHOT_TABLES,
    IDENTITY_COLUMNS,
    N4_AUDIT_TABLES,
    OFFICIAL_DAILY_TABLES,
    SNAPSHOT_TABLES,
    count_where,
    fetch_official_daily_status,
    fetch_source_summary,
    fetch_target_audit,
    normalize_counts,
    table_exists,
)
from ashare_v3.market.previous_day_preload_execute import json_safe, utc_now_iso, write_json, write_text


DEFAULT_EOD_CONTRACT_JSON_PATH = "docs/N3_EOD_snapshot_refresh_execute_contract.json"
DEFAULT_EOD_PREFLIGHT_JSON_PATH = "docs/N3_EOD_snapshot_refresh_execute_preflight.json"
DEFAULT_EOD_JSON_REPORT_PATH = "docs/N3_EOD_snapshot_refresh_execute_report.json"
DEFAULT_EOD_MD_REPORT_PATH = "docs/N3_EOD_SNAPSHOT_REFRESH_EXECUTE_REPORT.md"
DEFAULT_EOD_ROLLBACK_SQL_PATH = "sql/N3_EOD_snapshot_business_rollback.sql"

EOD_CONTRACT_STAGE = "N3-EOD-snapshot-refresh-execute-contract"
EOD_PREFLIGHT_STAGE = "N3-EOD-snapshot-refresh-execute-preflight"
EOD_METRIC_SCOPE = "eod_snapshot_refresh"
EOD_QUALITY_SCHEMA_VERSION = "n3.eod_snapshot_refresh.v1"
EOD_QUALITY_LAYER_SCOPE = "market_data_run"
ALLOWED_QUALITY_DATA_DOMAINS = ("common", "stock", "index", "board")

ALLOWED_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_eod_snapshot",
    "index_eod_snapshot",
    "board_eod_snapshot",
    "stock_eod_reconciliation_item",
    "index_eod_reconciliation_item",
    "board_eod_reconciliation_item",
)
FORBIDDEN_WRITE_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
    "stock_closed_30m_signal_enrichment",
    "index_closed_30m_signal_enrichment",
    "board_closed_30m_signal_enrichment",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "condition tables",
    "trigger tables",
    "action tables",
    "user tables",
    "voice/mobile/sim/position tables",
    "N4/N5/N6",
    "worker",
    "old system",
)


class EodSnapshotExecuteError(RuntimeError):
    """Raised when N3-EOD execute violates its reviewed contract."""


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_eod_snapshot_execute(
    *,
    dsn: str,
    contract_path: str = DEFAULT_EOD_CONTRACT_JSON_PATH,
    preflight_path: str = DEFAULT_EOD_PREFLIGHT_JSON_PATH,
    json_report_path: str = DEFAULT_EOD_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_EOD_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_EOD_ROLLBACK_SQL_PATH,
    eod_run_id: str | None = None,
    for_trade_date: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    contract = read_json(contract_path)
    preflight = read_json(preflight_path)
    ensure_eod_execute_contract(
        contract,
        preflight,
        execute=execute,
        user_confirmed=user_confirmed,
        eod_run_id=eod_run_id,
        for_trade_date=for_trade_date,
    )
    resolved_run_id = str(contract["eod_run_id"])

    pre_execute = capture_eod_execute_snapshot(dsn, contract=contract)
    ensure_clean_eod_target(pre_execute["target_audit"], resolved_run_id)
    ensure_official_daily_available(pre_execute["official_daily_status"])
    ensure_eod_source_runs_passed(pre_execute["source_summary"], contract)
    ensure_c3_outbox_unconsumed(pre_execute["source_summary"])

    if progress_callback:
        progress_callback("N3-EOD building settlement rows")
    snapshot_rows_by_asset = fetch_b1_snapshot_rows(dsn=dsn, contract=contract)
    official_rows_by_asset = fetch_official_daily_rows(dsn=dsn, contract=contract)
    snapshot_rows = build_eod_snapshot_rows(
        contract=contract,
        snapshot_rows=snapshot_rows_by_asset,
        official_rows=official_rows_by_asset,
    )
    row_summary = summarize_eod_snapshot_rows(snapshot_rows)
    reconciliation_rows = build_reconciliation_items(
        contract=contract,
        snapshot_rows=snapshot_rows,
        source_summary=pre_execute["source_summary"],
    )
    reconciliation_summary = summarize_reconciliation_items(reconciliation_rows)
    quality_items = build_eod_execute_quality_items(
        contract=contract,
        row_summary=row_summary,
        official_daily_status=pre_execute["official_daily_status"],
        target_audit=pre_execute["target_audit"],
        source_summary=pre_execute["source_summary"],
    )
    quality_counts = count_quality_severities(quality_items)
    if quality_counts["P0"]:
        raise EodSnapshotExecuteError("N3-EOD blocked: P0 quality blockers present before write")

    started_at = utc_now_iso()
    if progress_callback:
        progress_callback(f"N3-EOD writing {row_summary['total_rows']} snapshot rows")
    write_eod_execute_transaction(
        dsn=dsn,
        contract=contract,
        snapshot_rows=snapshot_rows,
        reconciliation_rows=reconciliation_rows,
        quality_items=quality_items,
        status="passed",
        started_at=started_at,
        contract_path=contract_path,
        preflight_path=preflight_path,
    )
    post_execute = capture_eod_execute_snapshot(dsn, contract=contract)
    rollback_sql = build_eod_rollback_sql(resolved_run_id)
    write_text(rollback_sql_path, rollback_sql)

    report = {
        "stage": "N3-EOD",
        "layer_role": "N3_market_data",
        "execution_mode": "eod_snapshot_refresh_run_once_execute",
        "result": "EXECUTED",
        "eod_run_id": resolved_run_id,
        "for_trade_date": contract["for_trade_date"],
        "lineage": contract["lineage"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "paths": {
            "contract_path": contract_path,
            "preflight_path": preflight_path,
            "rollback_sql_path": rollback_sql_path,
        },
        "write_result": {
            "snapshot_rows_written": row_summary["total_rows"],
            "snapshot_rows_by_asset": row_summary["rows_by_asset"] | {"total": row_summary["total_rows"]},
            "reconciliation_rows_written": reconciliation_summary["total_rows"],
            "reconciliation_rows_by_asset": reconciliation_summary["rows_by_asset"]
            | {"total": reconciliation_summary["total_rows"]},
            "quality_rows_written": len(quality_items),
            "run_rows_written": 1,
            "writes_outbox": False,
            "outbox_rows_written": 0,
        },
        "row_summary": row_summary,
        "reconciliation_summary": reconciliation_summary,
        "official_daily_status": pre_execute["official_daily_status"],
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
            "eod_snapshot_rows_written": True,
            "eod_reconciliation_rows_written": True,
            "quality_written": True,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "inbox_or_checkpoint_written": False,
            "realtime_snapshot_modified": False,
            "realtime_projection_modified": False,
            "minute_bar_modified": False,
            "closed_30m_summary_modified": False,
            "closed_signal_enrichment_modified": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "next_allowed_step": "N3-EOD execute post-review",
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_eod_execute_report(report))
    return report


def ensure_eod_execute_contract(
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    execute: bool,
    user_confirmed: bool,
    eod_run_id: str | None,
    for_trade_date: str | None,
) -> None:
    if not execute:
        raise EodSnapshotExecuteError("N3-EOD snapshot refresh execute requires explicit --execute")
    if not user_confirmed:
        raise EodSnapshotExecuteError("N3-EOD snapshot refresh execute requires explicit --user-confirmed")
    if str(contract.get("stage") or "") != EOD_CONTRACT_STAGE:
        raise EodSnapshotExecuteError("N3-EOD blocked: contract stage mismatch")
    if contract.get("layer_role") != "N3_market_data":
        raise EodSnapshotExecuteError("N3-EOD blocked: contract layer_role mismatch")
    if not contract.get("runner_exists") or contract.get("runner_readiness") != "ready":
        raise EodSnapshotExecuteError("N3-EOD blocked: runner readiness is not ready")
    if str(preflight.get("stage") or "") not in {EOD_PREFLIGHT_STAGE, "N3-EOD snapshot refresh execute preflight"}:
        raise EodSnapshotExecuteError("N3-EOD blocked: preflight stage mismatch")
    if preflight.get("result") != "PREFLIGHT_PASS":
        raise EodSnapshotExecuteError("N3-EOD blocked: preflight did not pass")
    if preflight.get("runner_readiness") not in {None, "ready"}:
        raise EodSnapshotExecuteError("N3-EOD blocked: preflight runner readiness is not ready")
    if not bool(preflight.get("execute_final_gate_allowed")):
        raise EodSnapshotExecuteError("N3-EOD blocked: execute final gate is not allowed by preflight")
    contract_run_id = str(contract.get("eod_run_id") or "")
    if eod_run_id and eod_run_id != contract_run_id:
        raise EodSnapshotExecuteError("N3-EOD blocked: CLI eod_run_id does not match contract")
    if preflight.get("eod_run_id") != contract_run_id:
        raise EodSnapshotExecuteError("N3-EOD blocked: preflight eod_run_id mismatch")
    contract_trade_date = str(contract.get("for_trade_date") or "")
    if for_trade_date and for_trade_date != contract_trade_date:
        raise EodSnapshotExecuteError("N3-EOD blocked: CLI for_trade_date does not match contract")
    if preflight.get("for_trade_date") != contract_trade_date:
        raise EodSnapshotExecuteError("N3-EOD blocked: preflight for_trade_date mismatch")
    if contract.get("writes_outbox") or contract.get("consumes_c3_outbox"):
        raise EodSnapshotExecuteError("N3-EOD blocked: writes_outbox and consumes_c3_outbox must be false")
    write_scope = preflight.get("write_scope") or {}
    if write_scope.get("writes_outbox") or write_scope.get("consumes_c3_outbox"):
        raise EodSnapshotExecuteError("N3-EOD blocked: preflight write scope violates outbox boundary")
    ensure_official_daily_available(preflight.get("official_daily_status") or {})
    ensure_c3_outbox_unconsumed(preflight.get("source_summary") or {})
    quality = preflight.get("quality") or {}
    if int(quality.get("p0_count") or 0):
        raise EodSnapshotExecuteError("N3-EOD blocked: preflight has P0 blockers")


def ensure_clean_eod_target(target_audit: Mapping[str, Any], eod_run_id: str) -> None:
    if target_audit.get("eod_run_exists"):
        raise EodSnapshotExecuteError(f"N3-EOD blocked: eod_run_id already exists: {eod_run_id}")
    target_rows = target_audit.get("target_rows_for_eod_run") or {}
    reconciliation_rows = target_audit.get("reconciliation_rows_for_eod_run") or {}
    if int(target_rows.get("total") or 0) or sum(int(target_rows.get(asset) or 0) for asset in ASSET_KINDS):
        raise EodSnapshotExecuteError(f"N3-EOD blocked: EOD target snapshot baseline is nonzero for {eod_run_id}")
    if int(reconciliation_rows.get("total") or 0) or sum(int(reconciliation_rows.get(asset) or 0) for asset in ASSET_KINDS):
        raise EodSnapshotExecuteError(f"N3-EOD blocked: EOD reconciliation baseline is nonzero for {eod_run_id}")
    for key in ("quality_rows_for_eod_run", "outbox_rows_for_eod_run", "inbox_rows_for_eod_run", "checkpoint_rows_for_eod_run"):
        count = int(target_audit.get(key) or 0)
        if count:
            noun = key.replace("_rows_for_eod_run", "").replace("_", " ")
            raise EodSnapshotExecuteError(f"N3-EOD blocked: {noun} baseline is nonzero for {eod_run_id}")


def ensure_official_daily_available(official_daily_status: Mapping[str, Any]) -> None:
    if not official_daily_status.get("available") or int(official_daily_status.get("missing_fact_count") or 0):
        raise EodSnapshotExecuteError("N3-EOD blocked: official daily coverage is incomplete")


def ensure_c3_outbox_unconsumed(source_summary: Mapping[str, Any]) -> None:
    c3 = source_summary.get("c3_outbox") or {}
    delivered = int(c3.get("delivered") or 0)
    delivering = int(c3.get("delivering") or 0)
    if delivered or delivering:
        raise EodSnapshotExecuteError("N3-EOD blocked: C3 outbox has delivered/delivering rows")


def ensure_eod_source_runs_passed(source_summary: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    source_runs = source_summary.get("source_runs") or {}
    if not source_runs.get("passed"):
        raise EodSnapshotExecuteError(
            f"N3-EOD blocked: source runs not passed: {source_runs.get('missing_or_not_passed')}"
        )
    lineage = contract.get("lineage") or {}
    for key in (
        "source_condition_run_id",
        "source_subscription_run_id",
        "source_b1_snapshot_run_id",
        "source_c2_run_id",
        "source_c2b_run_id",
        "source_c3_run_id",
        "source_n4_replay_audit_run_id",
    ):
        if not lineage.get(key):
            raise EodSnapshotExecuteError(f"N3-EOD blocked: missing lineage key {key}")


def build_eod_snapshot_rows(
    *,
    contract: Mapping[str, Any],
    snapshot_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    official_rows: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    lineage = contract["lineage"]
    official_by_asset = {
        asset: {str(row.get("identity_key") or row.get(IDENTITY_COLUMNS[asset]) or ""): dict(row) for row in official_rows.get(asset, [])}
        for asset in ASSET_KINDS
    }
    rows: list[dict[str, Any]] = []
    for asset in ASSET_KINDS:
        for snapshot in snapshot_rows.get(asset, []):
            identity_key = str(snapshot.get("identity_key") or snapshot.get(IDENTITY_COLUMNS[asset]) or "")
            official = official_by_asset[asset].get(identity_key)
            status = "official_confirmed" if official else "official_missing"
            quality = "passed" if official else "missing"
            source_batch = official.get("source_batch_id") if official else None
            open_value = (official or snapshot).get("open")
            high_value = (official or snapshot).get("high")
            low_value = (official or snapshot).get("low")
            close_value = (official or snapshot).get("close") or snapshot.get("current_price")
            volume_value = (official or snapshot).get("volume")
            amount_value = (official or snapshot).get("amount")
            code = str((official or snapshot).get("code") or snapshot.get("board_code") or "")
            display_code = (official or snapshot).get("display_code") or (official or snapshot).get("ts_code") or code
            name = (official or snapshot).get("name") or (official or snapshot).get("board_name")
            exchange = str(snapshot.get("exchange") or (official or {}).get("exchange") or ("TDX" if asset == "board" else ""))
            rows.append(
                {
                    "eod_run_id": contract["eod_run_id"],
                    "source_condition_run_id": lineage["source_condition_run_id"],
                    "source_subscription_run_id": lineage["source_subscription_run_id"],
                    "source_b1_snapshot_run_id": lineage["source_b1_snapshot_run_id"],
                    "source_c2_run_id": lineage["source_c2_run_id"],
                    "source_c2b_run_id": lineage["source_c2b_run_id"],
                    "source_c3_run_id": lineage["source_c3_run_id"],
                    "source_n4_replay_audit_run_id": lineage["source_n4_replay_audit_run_id"],
                    "official_daily_run_id": source_batch,
                    "trade_date": contract["for_trade_date"],
                    "asset_kind": asset,
                    "identity_key": identity_key,
                    "exchange": exchange,
                    "code": code,
                    "display_code": display_code,
                    "name": name,
                    "open": open_value,
                    "high": high_value,
                    "low": low_value,
                    "close": close_value,
                    "volume": volume_value,
                    "amount": amount_value,
                    "official_close_price": official.get("close") if official else None,
                    "official_volume": official.get("volume") if official else None,
                    "official_amount": official.get("amount") if official else None,
                    "eod_source_status": status,
                    "settlement_quality_status": quality,
                    "stale_candidate": False,
                    "raw_json": {
                        "metric_scope": EOD_METRIC_SCOPE,
                        "snapshot_id": snapshot.get("snapshot_id"),
                        "subscription_id": snapshot.get("subscription_id"),
                        "b1_snapshot": normalize_runtime_payload(snapshot),
                        "official_daily": normalize_runtime_payload(official or {}),
                        "official_source_version": official.get("source_version") if official else None,
                        "source_lineage": dict(lineage),
                    },
                }
            )
    return rows


def summarize_eod_snapshot_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_asset = Counter(str(row.get("asset_kind") or "") for row in rows)
    source_status = Counter(str(row.get("eod_source_status") or "") for row in rows)
    quality_status = Counter(str(row.get("settlement_quality_status") or "") for row in rows)
    stale_count = sum(1 for row in rows if bool(row.get("stale_candidate")))
    return {
        "total_rows": len(rows),
        "rows_by_asset": {asset: int(by_asset.get(asset) or 0) for asset in ASSET_KINDS},
        "source_status_distribution": dict(source_status),
        "settlement_quality_distribution": dict(quality_status),
        "stale_candidate_count": int(stale_count),
    }


def build_reconciliation_items(
    *,
    contract: Mapping[str, Any],
    snapshot_rows: Sequence[Mapping[str, Any]],
    source_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    lineage = contract["lineage"]
    rows: list[dict[str, Any]] = []
    for snapshot in snapshot_rows:
        rows.append(
            reconciliation_row(
                snapshot,
                source_run_id=str(snapshot.get("official_daily_run_id") or "official_daily_fact"),
                source_layer="N1_ingestion",
                source_fact_type="official_daily_fact",
                diff_type="official_daily_confirmed",
                diff_severity="info",
                quality_status="passed" if snapshot.get("official_daily_run_id") else "missing",
                expected={"official_daily_required": True},
                actual={"official_daily_run_id": snapshot.get("official_daily_run_id")},
                trace={"metric_scope": EOD_METRIC_SCOPE},
            )
        )

    representative_by_asset = first_snapshot_by_asset(snapshot_rows)
    c2_missing = int((source_summary.get("c2_summary_rows") or {}).get("missing") or 0)
    if c2_missing:
        rows.extend(
            aggregate_warning_rows(
                representative_by_asset,
                source_run_id=str(lineage["source_c2_run_id"]),
                source_layer="N3_market_data",
                source_fact_type="closed_30m_summary",
                diff_type="c2_closed_summary_missing",
                actual={"missing_summary_rows": c2_missing},
            )
        )
    n4_missing = int((source_summary.get("n4_replay_audit") or {}).get("missing") or 0)
    if n4_missing:
        rows.extend(
            aggregate_warning_rows(
                representative_by_asset,
                source_run_id=str(lineage["source_n4_replay_audit_run_id"]),
                source_layer="N4_trigger",
                source_fact_type="trigger_replay_audit",
                diff_type="n4_replay_audit_missing",
                actual={"missing_audit_rows": n4_missing},
            )
        )
    return rows


def reconciliation_row(
    snapshot: Mapping[str, Any],
    *,
    source_run_id: str,
    source_layer: str,
    source_fact_type: str,
    diff_type: str,
    diff_severity: str,
    quality_status: str,
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    trace: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "eod_run_id": snapshot["eod_run_id"],
        "eod_snapshot_id": snapshot.get("eod_snapshot_id"),
        "asset_kind": snapshot["asset_kind"],
        "identity_key": snapshot["identity_key"],
        "trade_date": snapshot["trade_date"],
        "source_run_id": source_run_id,
        "source_layer": source_layer,
        "source_fact_type": source_fact_type,
        "diff_type": diff_type,
        "diff_severity": diff_severity,
        "stale_candidate": False,
        "expected_value_json": dict(expected),
        "actual_value_json": dict(actual),
        "trace_json": {"metric_scope": EOD_METRIC_SCOPE, **dict(trace)},
        "quality_status": quality_status,
    }


def first_snapshot_by_asset(snapshot_rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in snapshot_rows:
        asset = str(row.get("asset_kind") or "")
        out.setdefault(asset, row)
    return out


def aggregate_warning_rows(
    representative_by_asset: Mapping[str, Mapping[str, Any]],
    *,
    source_run_id: str,
    source_layer: str,
    source_fact_type: str,
    diff_type: str,
    actual: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset in ASSET_KINDS:
        snapshot = representative_by_asset.get(asset)
        if snapshot is None:
            continue
        rows.append(
            reconciliation_row(
                snapshot,
                source_run_id=source_run_id,
                source_layer=source_layer,
                source_fact_type=source_fact_type,
                diff_type=diff_type,
                diff_severity="P1",
                quality_status="warning",
                expected={"missing_rows": 0},
                actual=actual,
                trace={"aggregate_warning": True, "asset_kind": asset},
            )
        )
    return rows


def summarize_reconciliation_items(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_asset = Counter(str(row.get("asset_kind") or "") for row in rows)
    by_diff = Counter(str(row.get("diff_type") or "") for row in rows)
    by_quality = Counter(str(row.get("quality_status") or "") for row in rows)
    stale_count = sum(1 for row in rows if bool(row.get("stale_candidate")))
    return {
        "total_rows": len(rows),
        "rows_by_asset": {asset: int(by_asset.get(asset) or 0) for asset in ASSET_KINDS},
        "diff_type_distribution": dict(by_diff),
        "quality_distribution": dict(by_quality),
        "stale_candidate_count": int(stale_count),
    }


def build_eod_execute_quality_items(
    *,
    contract: Mapping[str, Any],
    row_summary: Mapping[str, Any],
    official_daily_status: Mapping[str, Any],
    target_audit: Mapping[str, Any],
    source_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    eod_run_id = str(contract["eod_run_id"])
    expected = normalize_counts(contract.get("expected_eod_snapshot_rows") or {})
    actual = dict(row_summary.get("rows_by_asset") or {})
    actual["total"] = int(row_summary.get("total_rows") or 0)
    details = {
        "metric_scope": EOD_METRIC_SCOPE,
        "eod_run_id": eod_run_id,
        "source_subscription_run_id": (contract.get("lineage") or {}).get("source_subscription_run_id"),
        "event_schema_version": EOD_QUALITY_SCHEMA_VERSION,
    }
    items = [
        quality_row(
            data_domain="common",
            table_name="common_market_data_run",
            gate_code="n3_eod_execute_baseline_zero",
            gate_name="EOD target baseline is zero before execute",
            severity="P0",
            status="passed" if target_is_clean(target_audit) else "failed",
            expected="all scoped rows zero",
            actual=json.dumps(json_safe(target_audit), ensure_ascii=False, sort_keys=True),
            details=details,
        ),
        quality_row(
            data_domain="common",
            table_name="stock/index/board_eod_snapshot",
            gate_code="n3_eod_execute_snapshot_rows_match_contract",
            gate_name="EOD snapshot rows match contract counts",
            severity="P0",
            status="passed" if actual == expected else "failed",
            expected=json.dumps(expected, ensure_ascii=False, sort_keys=True),
            actual=json.dumps(actual, ensure_ascii=False, sort_keys=True),
            details=details,
        ),
        quality_row(
            data_domain="common",
            table_name="stock/index/board_daily_bar_fact",
            gate_code="n3_eod_execute_official_daily_coverage_complete",
            gate_name="Official daily coverage is complete for EOD settlement",
            severity="P0",
            status="passed"
            if official_daily_status.get("available") and int(official_daily_status.get("missing_fact_count") or 0) == 0
            else "failed",
            expected=json.dumps(expected, ensure_ascii=False, sort_keys=True),
            actual=json.dumps(official_daily_status.get("coverage") or {}, ensure_ascii=False, sort_keys=True),
            details={**details, "source_versions_for_trade_date": official_daily_status.get("source_versions_for_trade_date")},
        ),
    ]
    c2_missing = int((source_summary.get("c2_summary_rows") or {}).get("missing") or 0)
    if c2_missing:
        items.append(
            quality_row(
                data_domain="stock",
                table_name="stock/index/board_eod_reconciliation_item",
                gate_code="n3_eod_c2_missing_summary_rows_visible",
                gate_name="C2 missing summaries remain settlement evidence",
                severity="P1",
                status="warning",
                expected="0 missing C2 summaries",
                actual=str(c2_missing),
                details={**details, "source_c2_run_id": (contract.get("lineage") or {}).get("source_c2_run_id")},
            )
        )
    n4_missing = int((source_summary.get("n4_replay_audit") or {}).get("missing") or 0)
    if n4_missing:
        items.append(
            quality_row(
                data_domain="stock",
                table_name="stock/index/board_eod_reconciliation_item",
                gate_code="n3_eod_n4_replay_audit_missing_rows_visible",
                gate_name="N4 C3 replay audit missing rows remain settlement evidence",
                severity="P1",
                status="warning",
                expected="0 missing N4 replay audit rows",
                actual=str(n4_missing),
                details={**details, "source_n4_replay_audit_run_id": (contract.get("lineage") or {}).get("source_n4_replay_audit_run_id")},
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
        raise EodSnapshotExecuteError(f"N3-EOD blocked: illegal quality data_domain: {data_domain}")
    return {
        "data_domain": data_domain,
        "layer_scope": EOD_QUALITY_LAYER_SCOPE,
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


def target_is_clean(target_audit: Mapping[str, Any]) -> bool:
    target_rows = target_audit.get("target_rows_for_eod_run") or {}
    reconciliation_rows = target_audit.get("reconciliation_rows_for_eod_run") or {}
    return (
        not target_audit.get("eod_run_exists")
        and int(target_rows.get("total") or 0) == 0
        and int(reconciliation_rows.get("total") or 0) == 0
        and int(target_audit.get("quality_rows_for_eod_run") or 0) == 0
        and int(target_audit.get("outbox_rows_for_eod_run") or 0) == 0
        and int(target_audit.get("inbox_rows_for_eod_run") or 0) == 0
        and int(target_audit.get("checkpoint_rows_for_eod_run") or 0) == 0
    )


def capture_eod_execute_snapshot(dsn: str, *, contract: Mapping[str, Any]) -> dict[str, Any]:
    eod_run_id = str(contract["eod_run_id"])
    lineage = contract["lineage"]
    expected_rows = normalize_counts(contract.get("expected_eod_snapshot_rows") or {})
    for_trade_date = str(contract["for_trade_date"])
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        source_summary = fetch_source_summary(cur, lineage=lineage, expected_rows=expected_rows, for_trade_date=for_trade_date)
        official_daily_status = fetch_official_daily_status(cur, for_trade_date=for_trade_date, expected_rows=expected_rows)
        target_audit = fetch_target_audit(cur, eod_run_id=eod_run_id)
    return {
        "source_summary": source_summary,
        "official_daily_status": official_daily_status,
        "target_audit": target_audit,
    }


def fetch_b1_snapshot_rows(*, dsn: str, contract: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    lineage = contract["lineage"]
    run_id = str(lineage["source_b1_snapshot_run_id"])
    rows: dict[str, list[dict[str, Any]]] = {}
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for asset in ASSET_KINDS:
            table = SNAPSHOT_TABLES[asset]
            identity_col = IDENTITY_COLUMNS[asset]
            cur.execute(
                f"""
                SELECT snapshot_id, run_id, subscription_id, source_condition_run_id,
                       for_trade_date, trade_date, snapshot_time,
                       {identity_col} AS identity_key, exchange, code, display_code, name,
                       open, high, low, close, current_price, pre_close, volume, amount,
                       source_adapter, source_version, quality_status, raw_json
                FROM {table}
                WHERE run_id = %s AND trade_date = %s
                ORDER BY {identity_col}
                """,
                (run_id, contract["for_trade_date"]),
            )
            rows[asset] = [normalize_runtime_payload(row) for row in cur.fetchall()]
    return rows


def fetch_official_daily_rows(*, dsn: str, contract: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    for_trade_date = str(contract["for_trade_date"])
    rows: dict[str, list[dict[str, Any]]] = {}
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT stock_identity_key AS identity_key, trade_date, exchange, code, ts_code AS display_code,
                   name, open, high, low, close, volume, amount, source_version, source_batch_id
            FROM stock_daily_bar_fact
            WHERE trade_date = %s AND official_daily_proof IS TRUE
            ORDER BY stock_identity_key
            """,
            (for_trade_date,),
        )
        rows["stock"] = [normalize_runtime_payload(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT index_identity_key AS identity_key, trade_date, exchange, code, code AS display_code,
                   name, open, high, low, close, volume, amount, source_version, source_batch_id
            FROM index_daily_bar_fact
            WHERE trade_date = %s
            ORDER BY index_identity_key
            """,
            (for_trade_date,),
        )
        rows["index"] = [normalize_runtime_payload(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT board_identity_key AS identity_key, trade_date, 'TDX' AS exchange, board_code AS code,
                   board_code AS display_code, board_name AS name, open, high, low, close, volume, amount,
                   source_version, source_batch_id
            FROM board_daily_bar_fact
            WHERE trade_date = %s
            ORDER BY board_identity_key
            """,
            (for_trade_date,),
        )
        rows["board"] = [normalize_runtime_payload(row) for row in cur.fetchall()]
    return rows


def write_eod_execute_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    snapshot_rows: Sequence[Mapping[str, Any]],
    reconciliation_rows: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
    status: str,
    started_at: str,
    contract_path: str,
    preflight_path: str,
) -> None:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                insert_eod_run(
                    cur,
                    contract=contract,
                    status="running",
                    started_at=started_at,
                    contract_path=contract_path,
                    preflight_path=preflight_path,
                )
                snapshot_id_by_key = insert_eod_snapshot_rows(cur, snapshot_rows)
                hydrated_reconciliation = hydrate_reconciliation_snapshot_ids(
                    reconciliation_rows,
                    snapshot_id_by_key=snapshot_id_by_key,
                )
                insert_reconciliation_rows(cur, hydrated_reconciliation)
                insert_eod_quality_items(cur, contract=contract, quality_items=quality_items)
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
                    (status, counts["P0"], counts["P1"], counts["P2"], contract["eod_run_id"]),
                )


def insert_eod_run(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    status: str,
    started_at: str,
    contract_path: str,
    preflight_path: str,
) -> None:
    source_run = fetch_source_subscription_run(cur, str(contract["lineage"]["source_subscription_run_id"]))
    expected = contract["expected_eod_snapshot_rows"]
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
                %s, %s, %s, %s, %s, 'N3-EOD-snapshot-refresh-execute',
                false, false, false, false, %s, %s)
        """,
        (
            contract["eod_run_id"],
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
                        "stage": "N3-EOD",
                        "metric_scope": EOD_METRIC_SCOPE,
                        "eod_run_id": contract["eod_run_id"],
                        "lineage": contract["lineage"],
                        "contract_path": contract_path,
                        "preflight_path": preflight_path,
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
        raise EodSnapshotExecuteError(f"N3-EOD blocked: source subscription run missing: {run_id}")
    return row


def insert_eod_snapshot_rows(cur: Any, rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str], int]:
    snapshot_id_by_key: dict[tuple[str, str, str], int] = {}
    for asset in ASSET_KINDS:
        table = EOD_SNAPSHOT_TABLES[asset]
        asset_rows = [row for row in rows if row.get("asset_kind") == asset]
        if not asset_rows:
            continue
        columns = (
            "eod_run_id",
            "source_condition_run_id",
            "source_subscription_run_id",
            "source_b1_snapshot_run_id",
            "source_c2_run_id",
            "source_c2b_run_id",
            "source_c3_run_id",
            "source_n4_replay_audit_run_id",
            "official_daily_run_id",
            "trade_date",
            "asset_kind",
            "identity_key",
            "exchange",
            "code",
            "display_code",
            "name",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "official_close_price",
            "official_volume",
            "official_amount",
            "eod_source_status",
            "settlement_quality_status",
            "stale_candidate",
            "raw_json",
        )
        for row in asset_rows:
            values = tuple(Jsonb(json_safe(row[col])) if col == "raw_json" else row.get(col) for col in columns)
            cur.execute(
                f"""
                INSERT INTO {table} ({", ".join(columns)})
                VALUES ({", ".join(["%s"] * len(columns))})
                RETURNING eod_snapshot_id
                """,
                values,
            )
            snapshot_id = int(cur.fetchone()["eod_snapshot_id"])
            snapshot_id_by_key[(asset, str(row["identity_key"]), str(row["trade_date"]))] = snapshot_id
    return snapshot_id_by_key


def hydrate_reconciliation_snapshot_ids(
    rows: Sequence[Mapping[str, Any]],
    *,
    snapshot_id_by_key: Mapping[tuple[str, str, str], int],
) -> list[dict[str, Any]]:
    hydrated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        key = (str(row["asset_kind"]), str(row["identity_key"]), str(row["trade_date"]))
        item["eod_snapshot_id"] = snapshot_id_by_key.get(key)
        hydrated.append(item)
    return hydrated


def insert_reconciliation_rows(cur: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for asset in ASSET_KINDS:
        table = EOD_RECONCILIATION_TABLES[asset]
        asset_rows = [row for row in rows if row.get("asset_kind") == asset]
        if not asset_rows:
            continue
        columns = (
            "eod_run_id",
            "eod_snapshot_id",
            "asset_kind",
            "identity_key",
            "trade_date",
            "source_run_id",
            "source_layer",
            "source_fact_type",
            "diff_type",
            "diff_severity",
            "stale_candidate",
            "expected_value_json",
            "actual_value_json",
            "trace_json",
            "quality_status",
        )
        values = []
        for row in asset_rows:
            values.append(
                tuple(
                    Jsonb(json_safe(row[col]))
                    if col in {"expected_value_json", "actual_value_json", "trace_json"}
                    else row.get(col)
                    for col in columns
                )
            )
        cur.executemany(
            f"""
            INSERT INTO {table} ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
            """,
            values,
        )
        count += len(values)
    return count


def insert_eod_quality_items(cur: Any, *, contract: Mapping[str, Any], quality_items: Sequence[Mapping[str, Any]]) -> int:
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
            raise EodSnapshotExecuteError(f"N3-EOD blocked: illegal quality data_domain: {data_domain}")
        layer_scope = str(item.get("layer_scope") or EOD_QUALITY_LAYER_SCOPE)
        if layer_scope != EOD_QUALITY_LAYER_SCOPE:
            raise EodSnapshotExecuteError(f"N3-EOD blocked: illegal quality layer_scope: {layer_scope}")
        details = dict(item.get("details") or {})
        details.setdefault("metric_scope", EOD_METRIC_SCOPE)
        details.setdefault("eod_run_id", contract["eod_run_id"])
        details.setdefault("event_schema_version", EOD_QUALITY_SCHEMA_VERSION)
        values.append(
            (
                contract["eod_run_id"],
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


def build_eod_execute_preflight(
    *,
    dsn: str,
    contract_path: str = DEFAULT_EOD_CONTRACT_JSON_PATH,
    rollback_sql_path: str = DEFAULT_EOD_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    contract = read_json(contract_path)
    snapshot = capture_eod_execute_snapshot(dsn, contract=contract)
    blockers: list[str] = []
    try:
        ensure_clean_eod_target(snapshot["target_audit"], str(contract.get("eod_run_id") or ""))
    except EodSnapshotExecuteError as exc:
        blockers.append(str(exc))
    try:
        ensure_official_daily_available(snapshot["official_daily_status"])
    except EodSnapshotExecuteError as exc:
        blockers.append(str(exc))
    try:
        ensure_eod_source_runs_passed(snapshot["source_summary"], contract)
    except EodSnapshotExecuteError as exc:
        blockers.append(str(exc))
    try:
        ensure_c3_outbox_unconsumed(snapshot["source_summary"])
    except EodSnapshotExecuteError as exc:
        blockers.append(str(exc))
    if not Path(rollback_sql_path).exists():
        blockers.append("rollback_sql_missing")
    if not contract.get("runner_exists") or contract.get("runner_readiness") != "ready":
        blockers.append("runner_not_ready")
    if contract.get("writes_outbox") or contract.get("consumes_c3_outbox"):
        blockers.append("outbox_boundary_violation")

    result = "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS"
    return {
        "stage": EOD_PREFLIGHT_STAGE,
        "layer_role": "N3_market_data",
        "result": result,
        "blocked": bool(blockers),
        "blockers": blockers,
        "runner_exists": True,
        "runner_readiness": "ready",
        "execute_authorized": False,
        "eod_execute_allowed_now": False,
        "eod_execute_allowed_reason": "awaiting_final_gate_user_confirmation" if not blockers else "preflight_blocked",
        "eod_run_id": contract.get("eod_run_id"),
        "for_trade_date": contract.get("for_trade_date"),
        "execute_final_gate_allowed": not blockers,
        "lineage": contract.get("lineage"),
        "target_audit": snapshot["target_audit"],
        "source_summary": snapshot["source_summary"],
        "official_daily_status": snapshot["official_daily_status"],
        "expected_eod_snapshot_rows": contract.get("expected_eod_snapshot_rows"),
        "allowed_writes": list(ALLOWED_WRITE_TABLES),
        "forbidden_writes": list(FORBIDDEN_WRITE_TABLES),
        "write_scope": build_write_scope_contract(),
        "writes_outbox": False,
        "consumes_c3_outbox": False,
        "rollback_sql_path": rollback_sql_path,
        "side_effects": {
            "read_only_database_checks": True,
            "writes_database": False,
            "writes_outbox": False,
            "consumes_c3_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
        "next_allowed_step": "N3-EOD execute final gate" if not blockers else "fix N3-EOD preflight blockers",
    }


def build_write_scope_contract() -> dict[str, Any]:
    return {
        "allowed_execute_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_c3_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "updates_runtime_sources": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }


def build_eod_rollback_sql(eod_run_id: str) -> str:
    escaped = eod_run_id.replace("'", "''")
    return f"""-- N3-EOD snapshot refresh business rollback.
-- Scope: {escaped}
-- Deletes only EOD snapshot facts, reconciliation facts, quality rows, and run metadata.
-- Does not touch B1/B2/C2/C2B/C3/N4/N5 runtime, event outbox, inbox, checkpoint, minute bars, snapshots, projections, or downstream layers.

DO $$
DECLARE
  v_eod_run_id TEXT := '{escaped}';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_eod_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing EOD rollback: common_event_outbox has % rows for %', v_count, v_eod_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_eod_run_id;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing EOD rollback: common_event_inbox has % rows for %', v_count, v_eod_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_eod_run_id || '%';

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing EOD rollback: common_event_consumer_checkpoint references % in % rows', v_eod_run_id, v_count;
  END IF;
END $$;

DELETE FROM board_eod_reconciliation_item WHERE eod_run_id = '{escaped}';
DELETE FROM index_eod_reconciliation_item WHERE eod_run_id = '{escaped}';
DELETE FROM stock_eod_reconciliation_item WHERE eod_run_id = '{escaped}';
DELETE FROM board_eod_snapshot WHERE eod_run_id = '{escaped}';
DELETE FROM index_eod_snapshot WHERE eod_run_id = '{escaped}';
DELETE FROM stock_eod_snapshot WHERE eod_run_id = '{escaped}';
DELETE FROM common_market_data_quality_item WHERE run_id = '{escaped}';
DELETE FROM common_market_data_run WHERE run_id = '{escaped}';
"""


def rollback_safe_from_snapshot(snapshot: Mapping[str, Any]) -> bool:
    audit = snapshot.get("target_audit") or {}
    return (
        int(audit.get("outbox_rows_for_eod_run") or 0) == 0
        and int(audit.get("inbox_rows_for_eod_run") or 0) == 0
        and int(audit.get("checkpoint_rows_for_eod_run") or 0) == 0
    )


def write_eod_execute_preflight_files(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    write_json(json_path, report)
    write_text(markdown_path, format_eod_preflight_report(report))


def format_eod_preflight_report(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N3-EOD Snapshot Refresh Execute Preflight",
            "",
            f"- result: `{report.get('result')}`",
            f"- layer_role: `{report.get('layer_role')}`",
            f"- eod_run_id: `{report.get('eod_run_id')}`",
            f"- runner_readiness: `{report.get('runner_readiness')}`",
            f"- execute_authorized: `{report.get('execute_authorized')}`",
            f"- eod_execute_allowed_now: `{report.get('eod_execute_allowed_now')}`",
            f"- eod_execute_allowed_reason: `{report.get('eod_execute_allowed_reason')}`",
            f"- execute_final_gate_allowed: `{report.get('execute_final_gate_allowed')}`",
            f"- blockers: `{report.get('blockers')}`",
            f"- expected_eod_snapshot_rows: `{report.get('expected_eod_snapshot_rows')}`",
            f"- official_daily_status: `{report.get('official_daily_status')}`",
            f"- target_audit: `{report.get('target_audit')}`",
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


def format_eod_execute_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    write = report.get("write_result") or {}
    reconciliation = report.get("reconciliation_summary") or {}
    side = report.get("side_effects") or {}
    return "\n".join(
        [
            "# N3-EOD Snapshot Refresh Execute Report",
            "",
            "## Summary",
            "",
            f"- result: `{report.get('result')}`",
            f"- layer_role: `{report.get('layer_role')}`",
            f"- eod_run_id: `{report.get('eod_run_id')}`",
            f"- for_trade_date: `{report.get('for_trade_date')}`",
            f"- snapshot_rows_written: `{write.get('snapshot_rows_written')}`",
            f"- snapshot_rows_by_asset: `{write.get('snapshot_rows_by_asset')}`",
            f"- reconciliation_rows_written: `{write.get('reconciliation_rows_written')}`",
            f"- reconciliation_diff_distribution: `{reconciliation.get('diff_type_distribution')}`",
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


def normalize_runtime_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output
