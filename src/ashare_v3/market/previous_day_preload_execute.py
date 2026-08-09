"""N3-A1 previous-day minute preload executor.

This module is intentionally limited to N3 market-data responsibilities:
fetch previous-day 1 minute bars for already persisted subscriptions, write
stock/index/board minute facts, write preload status, and write N3 quality
items. It does not write common_event_outbox, start workers, or enter
trigger/action/user layers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.migration_execute import fetch_n1_n2_active_snapshot, stable_json_hash
from ashare_v3.market.mootdx_batch_attempt import (
    MootdxBatchAttemptOutcome,
    MootdxBatchObjectTracker,
    MootdxEndpointTransportError,
    build_mootdx_minute_semantic_probe,
    is_endpoint_transport_exception,
    run_mootdx_batch_attempt,
    with_batch_attempt_provenance,
)
from ashare_v3.market.preload_execute_contract import DEFAULT_A1_CONTRACT_JSON_PATH, read_json
from ashare_v3.market.preload_plan import (
    EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
    MINUTE_FACT_TABLES,
    PRELOAD_STATUS_TABLES,
    build_persisted_subscription_report,
    previous_day_subscriptions,
)
from ashare_v3.market.repositories import ASSET_FACT_TABLES, PreloadStatusRepository
from ashare_v3.market.subscription_plan import ADAPTER_NAMES, ASSET_KINDS
from ashare_v3.mootdx_client import EndpointSelection, MootdxEndpointManager


DEFAULT_N3_A1_PRE_BACKUP_PATH = "docs/N3_A1_previous_day_minute_preload_execute_backup_before.json"
DEFAULT_N3_A1_POST_BACKUP_PATH = "docs/N3_A1_previous_day_minute_preload_execute_backup_after.json"
DEFAULT_N3_A1_JSON_REPORT_PATH = "docs/N3_A1_previous_day_minute_preload_execute_report.json"
DEFAULT_N3_A1_MD_REPORT_PATH = "docs/N3_A1_PREVIOUS_DAY_MINUTE_PRELOAD_EXECUTE_REPORT.md"

ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
N3_A1_FACT_AND_STATUS_TABLES = (
    *MINUTE_FACT_TABLES.values(),
    *PRELOAD_STATUS_TABLES.values(),
)
N3_A1_FORBIDDEN_TABLES = ("common_event_outbox",)


class PreviousDayMinutePreloadExecuteError(RuntimeError):
    """Raised when N3-A1 execute violates its contract."""


class MootdxPreviousDayMinuteAdapter:
    """Fetch previous-day 1 minute bars with Mootdx online quote APIs."""

    source_version = "mootdx.bars.frequency8.offset800"
    external_source = "mootdx"

    def __init__(
        self,
        *,
        client: Any | None = None,
        market: str = "std",
        frequency: int = 8,
        start: int = 0,
        offset: int = 800,
    ) -> None:
        self.frequency = frequency
        self.start = start
        self.offset = offset
        self._client = client
        if self._client is None:
            raise PreviousDayMinutePreloadExecuteError(
                "MootdxPreviousDayMinuteAdapter requires a manager-selected pinned client"
            )

    def fetch_minute_bars(self, subscription: Mapping[str, Any], trade_date: str) -> list[dict[str, Any]]:
        asset_kind = str(subscription.get("asset_kind") or "")
        code = str(subscription.get("code") or "")
        if asset_kind == "stock":
            frame = self._client.bars(
                symbol=code,
                frequency=self.frequency,
                start=self.start,
                offset=self.offset,
            )
        elif asset_kind in {"index", "board"}:
            frame = self._client.index_bars(
                symbol=code,
                frequency=self.frequency,
                start=self.start,
                offset=self.offset,
            )
        else:
            raise PreviousDayMinutePreloadExecuteError(f"unsupported asset_kind: {asset_kind}")
        return normalize_minute_bar_records(frame, trade_date=trade_date)


def run_previous_day_minute_preload_execute(
    *,
    dsn: str,
    contract_path: str = DEFAULT_A1_CONTRACT_JSON_PATH,
    pre_backup_path: str = DEFAULT_N3_A1_PRE_BACKUP_PATH,
    post_backup_path: str = DEFAULT_N3_A1_POST_BACKUP_PATH,
    json_report_path: str = DEFAULT_N3_A1_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N3_A1_MD_REPORT_PATH,
    adapter: Any | None = None,
    endpoint_manager: MootdxEndpointManager | None = None,
    endpoint_probe: Callable[..., Mapping[str, Any]] | None = None,
    endpoint_client_factory: Callable[[EndpointSelection], Any] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
    execute: bool = False,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    """Execute N3-A1 using a reviewed contract and write the execute report."""

    ensure_execute_authorized(execute=execute, user_confirmed=user_confirmed)
    contract = read_json(contract_path)
    ensure_executable_contract(contract)
    source_run_id = str(contract["source_run_id"])
    preload_run_id = str(contract["preload_run_id"])
    previous_day_minute_date = str(contract["previous_day_minute_date"])
    started_at = utc_now_iso()

    pre_backup = capture_preload_execute_backup(
        dsn,
        phase="before_n3_a1",
        preload_run_id=preload_run_id,
        source_run_id=source_run_id,
        previous_day_minute_date=previous_day_minute_date,
    )
    ensure_clean_preload_target(pre_backup, preload_run_id)
    write_json(pre_backup_path, pre_backup)

    subscription_report = build_persisted_subscription_report(dsn=dsn, market_data_run_id=source_run_id)
    subscriptions = previous_day_subscriptions(subscription_report)
    ensure_subscription_counts_match_contract(subscriptions, contract)

    source_run_row = fetch_source_market_data_run(dsn, source_run_id)
    outcome: MootdxBatchAttemptOutcome[Any] | None = None
    atomic_committed = False
    if adapter is None:
        prepared, outcome = prepare_mootdx_previous_day_batch(
            contract=contract,
            subscriptions=subscriptions,
            manager=endpoint_manager or MootdxEndpointManager.from_toml(),
            probe=endpoint_probe
            or build_mootdx_minute_semantic_probe(
                subscriptions=subscriptions,
                trade_date=previous_day_minute_date,
                adapter_factory=lambda client: MootdxPreviousDayMinuteAdapter(client=client),
            ),
            client_factory=endpoint_client_factory,
        )
        object_results, data_snapshot, post_checks, quality_items = commit_previous_day_attempt_transaction(
            dsn=dsn,
            contract=contract,
            source_run_row=source_run_row,
            started_at=started_at,
            prepared=prepared,
            failed_results=failed_previous_day_batch_results(contract, subscriptions, outcome),
            outcome=outcome,
            pre_backup=pre_backup,
        )
        atomic_committed = True
    else:
        insert_preload_run(
            dsn,
            contract=contract,
            source_run_row=source_run_row,
            started_at=started_at,
        )
        object_results = execute_subscription_preloads(
            dsn=dsn,
            contract=contract,
            subscriptions=subscriptions,
            adapter=adapter,
            progress_callback=progress_callback,
            progress_every=progress_every,
        )

    if not atomic_committed:
        data_snapshot = capture_preload_execute_backup(
            dsn,
            phase="after_n3_a1_data_before_quality",
            preload_run_id=preload_run_id,
            source_run_id=source_run_id,
            previous_day_minute_date=previous_day_minute_date,
        )
        post_checks = build_post_execute_checks(
            contract=contract,
            pre_backup=pre_backup,
            data_snapshot=data_snapshot,
            object_results=object_results,
        )
        quality_items = build_post_execute_quality_items(
            contract=contract,
            post_checks=post_checks,
            object_results=object_results,
        )
    quality_counts = count_quality_severities(quality_items)
    if not atomic_committed:
        write_preload_quality_and_finalize_run(
            dsn,
            contract=contract,
            quality_items=quality_items,
            object_results=object_results,
            status="passed" if quality_counts["P0"] == 0 else "failed",
            batch_attempt=outcome.to_provenance() if outcome is not None else None,
        )

    post_backup = capture_preload_execute_backup(
        dsn,
        phase="after_n3_a1",
        preload_run_id=preload_run_id,
        source_run_id=source_run_id,
        previous_day_minute_date=previous_day_minute_date,
    )
    write_json(post_backup_path, post_backup)

    report = {
        "stage": "N3-A1",
        "layer_role": "N3_market_data",
        "execution_mode": "previous_day_minute_preload_execute",
        "source_run_id": source_run_id,
        "preload_run_id": preload_run_id,
        "source_condition_run_id": contract["source_condition_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "source_trade_date": contract["source_trade_date"],
        "previous_day_minute_date": previous_day_minute_date,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "contract_path": contract_path,
        "pre_backup_path": pre_backup_path,
        "post_backup_path": post_backup_path,
        "expected_asset_counts": contract["expected_asset_counts"],
        "actual_asset_counts": summarize_actual_asset_counts(object_results),
        "write_result": summarize_write_result(object_results, quality_items),
        "post_checks": post_checks,
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "pre_execute": {
            "active_snapshot_hash": stable_json_hash(pre_backup["active_snapshot"]),
            "target_preload_run_row_counts": pre_backup["target_preload_run_row_counts"],
            "common_event_outbox_row_count": pre_backup["common_event_outbox_row_count"],
        },
        "post_execute": {
            "active_snapshot_hash": stable_json_hash(post_backup["active_snapshot"]),
            "target_preload_run_row_counts": post_backup["target_preload_run_row_counts"],
            "common_event_outbox_row_count": post_backup["common_event_outbox_row_count"],
            "preload_run_row": post_backup["preload_run_row"],
        },
        "side_effects": {
            "writes_performed": True,
            "migration_executed": False,
            "market_data_pulled": True,
            "market_data_fact_written": any(int(item.get("minute_rows_written") or 0) > 0 for item in object_results),
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_previous_day_minute_execute_report(report))
    return report


def prepare_mootdx_previous_day_batch(
    *,
    contract: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    manager: MootdxEndpointManager,
    probe: Callable[..., Mapping[str, Any]],
    client_factory: Callable[[EndpointSelection], Any] | None = None,
) -> tuple[list[dict[str, Any]], MootdxBatchAttemptOutcome[Any]]:
    outcome = run_mootdx_batch_attempt(
        manager=manager,
        batch_id=str(contract["preload_run_id"]),
        probe=probe,
        client_factory=client_factory,
        required_checks=("minute_scope_sentinels",),
        fetch_batch=lambda client, selection: _prepare_previous_day_attempt(
            contract=contract,
            subscriptions=subscriptions,
            adapter=MootdxPreviousDayMinuteAdapter(client=client),
            object_tracker=MootdxBatchObjectTracker(manager, selection),
        ),
    )
    prepared = list(outcome.result or [])
    for item in prepared:
        item["minute_records"] = [
            with_batch_attempt_provenance(record, outcome)
            for record in item["minute_records"]
        ]
        item["status_record"] = with_batch_attempt_provenance(item["status_record"], outcome)
    return prepared, outcome


def _prepare_previous_day_attempt(
    *,
    contract: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    adapter: Any,
    object_tracker: MootdxBatchObjectTracker,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    expected_count = int(contract.get("expected_bar_count_per_object") or EXPECTED_A_SHARE_MINUTE_BAR_COUNT)
    for subscription in subscriptions:
        try:
            rows = adapter.fetch_minute_bars(subscription, str(contract["previous_day_minute_date"]))
        except Exception as exc:  # noqa: BLE001 - preserve local program and contract errors.
            if is_endpoint_transport_exception(exc):
                raise MootdxEndpointTransportError(str(exc)) from exc
            raise
        minute_records = build_minute_fact_records(
            contract=contract,
            subscription=subscription,
            normalized_rows=rows,
            adapter_name=adapter_name_for_subscription(contract, subscription),
            adapter=adapter,
        )
        object_tracker.record(
            identity_key=str(subscription.get("identity_key") or ""),
            value=minute_records,
            empty=len(minute_records) == 0,
        )
        passed = len(minute_records) == expected_count
        error_message = (
            None
            if passed
            else f"object minute rows incomplete: expected={expected_count} actual={len(minute_records)}"
        )
        status_record = build_preload_status_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name_for_subscription(contract, subscription),
            adapter=adapter,
            minute_records=minute_records,
            expected_count=expected_count,
            error_message=error_message,
        )
        prepared.append(
            {
                "subscription": dict(subscription),
                "minute_records": minute_records if passed else [],
                "status_record": status_record,
            }
        )
    return prepared


def write_prepared_previous_day_batch(
    *,
    dsn: str,
    prepared: Sequence[Mapping[str, Any]],
    connection_factory: Callable[[str], Any] | None = None,
    run_context: tuple[Mapping[str, Any], Mapping[str, Any], str] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    connect = connection_factory or (
        lambda value: audited_n3_market_execute_connect(value, connect_timeout=10, row_factory=dict_row)
    )
    with connect(dsn) as conn:
        with conn.transaction():
            if run_context is not None:
                contract, source_run_row, started_at = run_context
                first_status = dict(prepared[0]["status_record"]) if prepared else {}
                first_raw = first_status.get("raw_json")
                first_raw = first_raw if isinstance(first_raw, Mapping) else getattr(first_raw, "obj", {})
                with conn.cursor() as cur:
                    _insert_preload_run(
                        cur,
                        contract=contract,
                        source_run_row=source_run_row,
                        started_at=started_at,
                        batch_attempt=(
                            first_raw.get("mootdx_batch_attempt")
                            if isinstance(first_raw, Mapping)
                            else None
                        ),
                    )
            results.extend(_write_prepared_previous_day_batch_on_connection(conn, prepared))
    return results


def _write_prepared_previous_day_batch_on_connection(
    conn: Any,
    prepared: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in prepared:
        subscription = dict(item["subscription"])
        minute_records = list(item["minute_records"])
        status_record = dict(item["status_record"])
        with conn.cursor() as cur:
            written = (
                bulk_upsert_minute_bars(cur, str(subscription["asset_kind"]), minute_records)
                if minute_records
                else 0
            )
            PreloadStatusRepository(cur).upsert_preload_status(status_record)
        raw_json = status_record.get("raw_json")
        raw_json = raw_json if isinstance(raw_json, Mapping) else getattr(raw_json, "obj", {})
        results.append(
            {
                "asset_kind": subscription.get("asset_kind"),
                "identity_key": subscription.get("identity_key"),
                "subscription_id": subscription.get("subscription_id"),
                "status": status_record["status"],
                "quality_status": status_record["quality_status"],
                "expected_bar_count": status_record["expected_bar_count"],
                "actual_bar_count": status_record["actual_bar_count"],
                "missing_bar_count": status_record["missing_bar_count"],
                "minute_rows_written": written,
                "error_message": status_record["error_message"],
                "mootdx_batch_attempt": (
                    raw_json.get("mootdx_batch_attempt")
                    if isinstance(raw_json, Mapping)
                    else None
                ),
            }
        )
    return results


def commit_previous_day_attempt_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    prepared: Sequence[Mapping[str, Any]],
    failed_results: Sequence[Mapping[str, Any]],
    outcome: MootdxBatchAttemptOutcome[Any],
    pre_backup: Mapping[str, Any],
    connection_factory: Callable[[str], Any] | None = None,
    data_snapshot_builder: Callable[[Any], Mapping[str, Any]] | None = None,
    finalizer: Callable[..., None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    connect = connection_factory or (
        lambda value: audited_n3_market_execute_connect(value, connect_timeout=10, row_factory=dict_row)
    )
    provenance = outcome.to_provenance()
    with connect(dsn) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _insert_preload_run(
                    cur,
                    contract=contract,
                    source_run_row=source_run_row,
                    started_at=started_at,
                    batch_attempt=provenance,
                )
            object_results = (
                _write_prepared_previous_day_batch_on_connection(conn, prepared)
                if outcome.status == "passed"
                else [dict(row) for row in failed_results]
            )
            with conn.cursor() as cur:
                data_snapshot = dict(
                    data_snapshot_builder(cur)
                    if data_snapshot_builder is not None
                    else _capture_preload_execute_backup_with_cursor(
                        cur,
                        phase="after_n3_a1_data_before_quality",
                        preload_run_id=str(contract["preload_run_id"]),
                        source_run_id=str(contract["source_run_id"]),
                        previous_day_minute_date=str(contract["previous_day_minute_date"]),
                    )
                )
                post_checks = build_post_execute_checks(
                    contract=contract,
                    pre_backup=pre_backup,
                    data_snapshot=data_snapshot,
                    object_results=object_results,
                )
                quality_items = build_post_execute_quality_items(
                    contract=contract,
                    post_checks=post_checks,
                    object_results=object_results,
                )
                quality_counts = count_quality_severities(quality_items)
                (finalizer or _finalize_preload_run_with_cursor)(
                    cur,
                    contract=contract,
                    quality_items=quality_items,
                    object_results=object_results,
                    status="passed" if quality_counts["P0"] == 0 else "failed",
                    batch_attempt=provenance,
                )
    return object_results, data_snapshot, post_checks, quality_items


def failed_previous_day_batch_results(
    contract: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    outcome: MootdxBatchAttemptOutcome[Any],
) -> list[dict[str, Any]]:
    expected_count = int(contract.get("expected_bar_count_per_object") or EXPECTED_A_SHARE_MINUTE_BAR_COUNT)
    return [
        {
            "asset_kind": subscription.get("asset_kind"),
            "identity_key": subscription.get("identity_key"),
            "subscription_id": subscription.get("subscription_id"),
            "status": "failed",
            "quality_status": "failed",
            "expected_bar_count": expected_count,
            "actual_bar_count": 0,
            "missing_bar_count": expected_count,
            "minute_rows_written": 0,
            "error_message": "atomic Mootdx previous-day batch failed; all attempt rows discarded",
            "mootdx_batch_attempt": outcome.to_provenance(),
        }
        for subscription in subscriptions
    ]


def ensure_execute_authorized(*, execute: bool, user_confirmed: bool) -> None:
    if not execute:
        raise PreviousDayMinutePreloadExecuteError("N3-A1 previous-day minute execute requires explicit --execute")
    if not user_confirmed:
        raise PreviousDayMinutePreloadExecuteError("N3-A1 previous-day minute execute requires explicit --user-confirmed")


def ensure_executable_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("stage") != "N3-A1-preflight":
        raise PreviousDayMinutePreloadExecuteError("N3-A1 blocked: contract stage is not N3-A1-preflight")
    if contract.get("layer_role") != "N3_market_data":
        raise PreviousDayMinutePreloadExecuteError("N3-A1 blocked: contract layer_role is not N3_market_data")
    if int((contract.get("quality") or {}).get("p0_count") or 0) > 0:
        raise PreviousDayMinutePreloadExecuteError("N3-A1 blocked: execute contract has P0 findings")
    if bool(contract.get("writes_outbox")) or bool(contract.get("writes_event_outbox")):
        raise PreviousDayMinutePreloadExecuteError("N3-A1 blocked: execute contract must keep writes_outbox=false")
    expected_date = str(contract.get("previous_day_minute_date") or "")
    if not (len(expected_date) == 8 and expected_date.isdigit()):
        raise PreviousDayMinutePreloadExecuteError("N3-A1 blocked: previous_day_minute_date must be YYYYMMDD")
    for table_group in (contract.get("target_tables") or {}).values():
        for table_name in table_group.values():
            if isinstance(table_name, str) and ("_runtime" in table_name or table_name == "common_event_outbox"):
                raise PreviousDayMinutePreloadExecuteError(f"N3-A1 blocked: forbidden target table {table_name}")


def ensure_clean_preload_target(backup: Mapping[str, Any], preload_run_id: str) -> None:
    if bool(backup.get("preload_run_exists")):
        raise PreviousDayMinutePreloadExecuteError(f"N3-A1 blocked: preload run already exists: {preload_run_id}")
    dirty = {
        table_name: count
        for table_name, count in (backup.get("target_preload_run_row_counts") or {}).items()
        if int(count or 0) != 0
    }
    if dirty:
        raise PreviousDayMinutePreloadExecuteError(f"N3-A1 blocked: preload target rows already exist: {dirty}")
    dirty_event_refs = {
        table_name: count
        for table_name, count in scoped_event_ref_counts(backup).items()
        if int(count or 0) != 0
    }
    if dirty_event_refs:
        raise PreviousDayMinutePreloadExecuteError(
            f"N3-A1 blocked: scoped event refs already exist for {preload_run_id}: {dirty_event_refs}"
        )


def ensure_subscription_counts_match_contract(
    subscriptions: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> None:
    counts = Counter(str(row.get("asset_kind") or "") for row in subscriptions)
    expected = contract.get("expected_asset_counts") or {}
    mismatches = []
    for asset_kind in ASSET_KINDS:
        expected_count = int((expected.get(asset_kind) or {}).get("subscription_count") or 0)
        actual_count = int(counts.get(asset_kind) or 0)
        if actual_count != expected_count:
            mismatches.append(f"{asset_kind}: expected={expected_count} actual={actual_count}")
    if mismatches:
        raise PreviousDayMinutePreloadExecuteError(
            "N3-A1 blocked: subscription counts do not match contract: " + "; ".join(mismatches)
        )


def execute_subscription_preloads(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    adapter: Any,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total = len(subscriptions)
    for index, subscription in enumerate(subscriptions, start=1):
        if progress_callback and (index == 1 or index == total or index % max(progress_every, 1) == 0):
            progress_callback(f"N3-A1 preload progress {index}/{total} {subscription.get('asset_kind')} {subscription.get('identity_key')}")
        result = execute_one_subscription_preload(
            dsn=dsn,
            contract=contract,
            subscription=subscription,
            adapter=adapter,
        )
        results.append(result)
    return results


def execute_one_subscription_preload(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    subscription: Mapping[str, Any],
    adapter: Any,
) -> dict[str, Any]:
    expected_count = int(contract.get("expected_bar_count_per_object") or EXPECTED_A_SHARE_MINUTE_BAR_COUNT)
    previous_day_minute_date = str(contract["previous_day_minute_date"])
    adapter_name = adapter_name_for_subscription(contract, subscription)
    try:
        normalized_rows = adapter.fetch_minute_bars(subscription, previous_day_minute_date)
        minute_records = build_minute_fact_records(
            contract=contract,
            subscription=subscription,
            normalized_rows=normalized_rows,
            adapter_name=adapter_name,
            adapter=adapter,
        )
        status_record = build_preload_status_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            minute_records=minute_records,
            expected_count=expected_count,
            error_message=None,
        )
        with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    written = bulk_upsert_minute_bars(cur, str(subscription["asset_kind"]), minute_records)
                    PreloadStatusRepository(cur).upsert_preload_status(status_record)
        return {
            "asset_kind": subscription.get("asset_kind"),
            "identity_key": subscription.get("identity_key"),
            "subscription_id": subscription.get("subscription_id"),
            "status": status_record["status"],
            "quality_status": status_record["quality_status"],
            "expected_bar_count": expected_count,
            "actual_bar_count": len(minute_records),
            "missing_bar_count": max(expected_count - len(minute_records), 0),
            "minute_rows_written": written,
            "error_message": None,
        }
    except Exception as exc:  # noqa: BLE001 - adapter failures become quality evidence.
        error_message = f"{type(exc).__name__}: {exc}"
        status_record = build_preload_status_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            minute_records=[],
            expected_count=expected_count,
            error_message=error_message,
        )
        with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    PreloadStatusRepository(cur).upsert_preload_status(status_record)
        return {
            "asset_kind": subscription.get("asset_kind"),
            "identity_key": subscription.get("identity_key"),
            "subscription_id": subscription.get("subscription_id"),
            "status": "failed",
            "quality_status": "failed",
            "expected_bar_count": expected_count,
            "actual_bar_count": 0,
            "missing_bar_count": expected_count,
            "minute_rows_written": 0,
            "error_message": error_message,
        }


def adapter_name_for_subscription(contract: Mapping[str, Any], subscription: Mapping[str, Any]) -> str:
    asset_kind = str(subscription.get("asset_kind") or "")
    for row in contract.get("source_adapter_plan") or []:
        if row.get("asset_kind") == asset_kind:
            return str(row.get("adapter_name") or ADAPTER_NAMES[asset_kind])
    return ADAPTER_NAMES[asset_kind]


def build_minute_fact_records(
    *,
    contract: Mapping[str, Any],
    subscription: Mapping[str, Any],
    normalized_rows: Sequence[Mapping[str, Any]],
    adapter_name: str,
    adapter: Any,
) -> list[dict[str, Any]]:
    source_run_id = str(contract["source_run_id"])
    preload_run_id = str(contract["preload_run_id"])
    records: list[dict[str, Any]] = []
    for row in normalized_rows:
        raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), Mapping) else dict(row)
        records.append(
            {
                "run_id": preload_run_id,
                "subscription_id": subscription.get("subscription_id"),
                "source_condition_run_id": contract["source_condition_run_id"],
                "for_trade_date": contract["for_trade_date"],
                "trade_date": contract["previous_day_minute_date"],
                "bar_time": row["bar_time"],
                "identity_key": subscription["identity_key"],
                "exchange": subscription["exchange"],
                "code": subscription["code"],
                "display_code": subscription.get("display_code"),
                "name": subscription.get("name"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
                "source_adapter": adapter_name,
                "source_version": getattr(adapter, "source_version", "unknown"),
                "quality_status": "passed",
                "is_previous_day_preload": True,
                "source_scope_ids": subscription.get("source_scope_ids") or [],
                "source_condition_pool_ids": subscription.get("source_condition_pool_ids") or [],
                "raw_json": {
                    "source_run_id": source_run_id,
                    "preload_run_id": preload_run_id,
                    "required_data_kind": "previous_day_minute_bar_1m",
                    "external_source": getattr(adapter, "external_source", "unknown"),
                    "source_adapter": adapter_name,
                    "source_version": getattr(adapter, "source_version", "unknown"),
                    "raw_payload": json_safe(raw_payload),
                },
            }
        )
    return records


def build_preload_status_record(
    *,
    contract: Mapping[str, Any],
    subscription: Mapping[str, Any],
    adapter_name: str,
    adapter: Any,
    minute_records: Sequence[Mapping[str, Any]],
    expected_count: int,
    error_message: str | None,
) -> dict[str, Any]:
    actual_count = len(minute_records)
    if error_message:
        status = "failed"
        quality_status = "failed"
    elif actual_count == expected_count:
        status = "passed"
        quality_status = "passed"
    elif actual_count == 0:
        status = "missing"
        quality_status = "missing"
    else:
        status = "partial"
        quality_status = "partial"
    first_bar_time = minute_records[0]["bar_time"] if minute_records else None
    last_bar_time = minute_records[-1]["bar_time"] if minute_records else None
    return {
        "asset_kind": subscription["asset_kind"],
        "run_id": contract["preload_run_id"],
        "subscription_id": subscription.get("subscription_id"),
        "source_condition_run_id": contract["source_condition_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "trade_date": contract["previous_day_minute_date"],
        "identity_key": subscription["identity_key"],
        "exchange": subscription["exchange"],
        "code": subscription["code"],
        "display_code": subscription.get("display_code"),
        "name": subscription.get("name"),
        "expected_bar_count": expected_count,
        "actual_bar_count": actual_count,
        "missing_bar_count": max(expected_count - actual_count, 0),
        "first_bar_time": first_bar_time,
        "last_bar_time": last_bar_time,
        "status": status,
        "quality_status": quality_status,
        "source_adapter": adapter_name,
        "error_message": error_message,
        "source_scope_ids": subscription.get("source_scope_ids") or [],
        "source_condition_pool_ids": subscription.get("source_condition_pool_ids") or [],
        "raw_json": Jsonb(
            {
                "source_run_id": contract["source_run_id"],
                "preload_run_id": contract["preload_run_id"],
                "required_data_kind": "previous_day_minute_bar_1m",
                "external_source": getattr(adapter, "external_source", "unknown"),
                "source_adapter": adapter_name,
                "source_version": getattr(adapter, "source_version", "unknown"),
            }
        ),
    }


def bulk_upsert_minute_bars(cur: Any, asset_kind: str, records: Sequence[Mapping[str, Any]]) -> int:
    if not records:
        return 0
    table_name, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["minute"]
    columns = (
        "run_id",
        "subscription_id",
        "source_condition_run_id",
        "for_trade_date",
        "trade_date",
        "bar_time",
        identity_column,
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
        "source_adapter",
        "source_version",
        "quality_status",
        "is_previous_day_preload",
        "source_scope_ids",
        "source_condition_pool_ids",
        "raw_json",
    )
    values = [
        tuple(
            Jsonb(record[column]) if column == "raw_json" else record.get("identity_key") if column == identity_column else record.get(column)
            for column in columns
        )
        for record in records
    ]
    update_columns = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "source_version",
        "quality_status",
        "is_previous_day_preload",
        "source_scope_ids",
        "source_condition_pool_ids",
        "raw_json",
    )
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
    cur.executemany(
        f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        ON CONFLICT (run_id, trade_date, {identity_column}, bar_time, source_adapter)
        DO UPDATE SET {assignments}
        """,
        values,
    )
    return len(values)


def normalize_minute_bar_records(frame: Any, *, trade_date: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in frame_to_records(frame):
        bar_time = parse_bar_time(record)
        if bar_time.strftime("%Y%m%d") != trade_date:
            continue
        rows.append(
            {
                "bar_time": bar_time,
                "open": first_present(record, "open"),
                "high": first_present(record, "high"),
                "low": first_present(record, "low"),
                "close": first_present(record, "close", "price"),
                "volume": first_present(record, "volume", "vol"),
                "amount": first_present(record, "amount"),
                "raw_payload": dict(record),
            }
        )
    rows.sort(key=lambda item: item["bar_time"])
    return rows


def frame_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        try:
            records = frame.to_dict(orient="records")
        except TypeError:
            records = frame.to_dict("records")
        return [dict(record) for record in records]
    if isinstance(frame, Mapping):
        return [dict(frame)]
    if isinstance(frame, Sequence) and not isinstance(frame, (str, bytes, bytearray)):
        return [dict(record) for record in frame]
    raise PreviousDayMinutePreloadExecuteError(f"unsupported minute frame type: {type(frame).__name__}")


def parse_bar_time(record: Mapping[str, Any]) -> datetime:
    value = first_present(record, "datetime", "date_time", "bar_time", "time")
    if value is not None:
        parsed = parse_datetime_like(value)
        if parsed is not None:
            return parsed
    if all(record.get(key) is not None for key in ("year", "month", "day", "hour", "minute")):
        return datetime(
            int(record["year"]),
            int(record["month"]),
            int(record["day"]),
            int(record["hour"]),
            int(record["minute"]),
            tzinfo=ASIA_SHANGHAI,
        )
    date_value = first_present(record, "date")
    minute_value = first_present(record, "minute", "time")
    if date_value is not None and minute_value is not None:
        parsed = parse_datetime_like(f"{date_value} {minute_value}")
        if parsed is not None:
            return parsed
    raise PreviousDayMinutePreloadExecuteError("minute bar record missing parseable bar_time")


def parse_datetime_like(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return ensure_shanghai_timezone(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=ASIA_SHANGHAI)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("/", "-")
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y%m%d",
    ):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.replace(tzinfo=ASIA_SHANGHAI)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return ensure_shanghai_timezone(parsed)


def ensure_shanghai_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ASIA_SHANGHAI)
    return value.astimezone(ASIA_SHANGHAI)


def first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return None


def insert_preload_run(
    dsn: str,
    *,
    contract: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    batch_attempt: Mapping[str, Any] | None = None,
) -> None:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _insert_preload_run(
                    cur,
                    contract=contract,
                    source_run_row=source_run_row,
                    started_at=started_at,
                    batch_attempt=batch_attempt,
                )


def _insert_preload_run(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    batch_attempt: Mapping[str, Any] | None,
) -> None:
    expected_counts = contract.get("expected_asset_counts") or {}
    subscription_count = sum(
        int((expected_counts.get(asset) or {}).get("subscription_count") or 0)
        for asset in ASSET_KINDS
    )
    object_count = sum(
        int((expected_counts.get(asset) or {}).get("object_count") or 0)
        for asset in ASSET_KINDS
    )
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
        VALUES (%s, %s, %s, %s, %s, 'execute', 'running', 0, 0, 0,
                %s, %s, %s, %s, %s, 'market_data_layer',
                false, false, false, false, %s, %s)
        """,
        (
            contract["preload_run_id"],
            contract["source_condition_run_id"],
            contract["for_trade_date"],
            contract["source_trade_date"],
            contract["previous_day_minute_date"],
            int(source_run_row.get("source_scope_row_count") or 0),
            int(source_run_row.get("candidate_row_count") or 0),
            subscription_count,
            object_count,
            source_run_row.get("dedup_ratio"),
            started_at,
            Jsonb(
                {
                    "stage": "N3-A1",
                    "source_run_id": contract["source_run_id"],
                    "preload_run_id": contract["preload_run_id"],
                    "contract_path": DEFAULT_A1_CONTRACT_JSON_PATH,
                    "writes_outbox": False,
                    "mootdx_batch_attempt": dict(batch_attempt) if batch_attempt else None,
                }
            ),
        ),
    )


def fetch_source_market_data_run(dsn: str, source_run_id: str) -> dict[str, Any]:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_scope_row_count, candidate_row_count, subscription_row_count,
                   subscription_object_count, dedup_ratio
            FROM common_market_data_run
            WHERE run_id = %s
            """,
            (source_run_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise PreviousDayMinutePreloadExecuteError(f"N3-A1 blocked: source market_data_run missing: {source_run_id}")
    return dict(row)


def write_preload_quality_and_finalize_run(
    dsn: str,
    *,
    contract: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
    object_results: Sequence[Mapping[str, Any]],
    status: str,
    batch_attempt: Mapping[str, Any] | None = None,
) -> None:
    quality_counts = count_quality_severities(quality_items)
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _finalize_preload_run_with_cursor(
                    cur,
                    contract=contract,
                    quality_items=quality_items,
                    object_results=object_results,
                    status=status,
                    batch_attempt=batch_attempt,
                )


def _finalize_preload_run_with_cursor(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
    object_results: Sequence[Mapping[str, Any]],
    status: str,
    batch_attempt: Mapping[str, Any] | None,
) -> None:
    quality_counts = count_quality_severities(quality_items)
    traced_quality_items = [
        {
            **dict(item),
            "details": {
                **dict(item.get("details") or {}),
                "mootdx_batch_attempt": dict(batch_attempt) if batch_attempt else None,
            },
        }
        for item in quality_items
    ]
    insert_quality_items(cur, contract=contract, quality_items=traced_quality_items)
    cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status = %s,
                        p0_count = %s,
                        p1_count = %s,
                        p2_count = %s,
                        market_data_pulled = true,
                        market_data_fact_written = %s,
                        downstream_layers_touched = false,
                        worker_started = false,
                        finished_at = now(),
                        updated_at = now(),
                        raw_json = %s
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        quality_counts["P0"],
                        quality_counts["P1"],
                        quality_counts["P2"],
                        any(int(row.get("minute_rows_written") or 0) > 0 for row in object_results),
                        Jsonb(
                            {
                                "stage": "N3-A1",
                                "source_run_id": contract["source_run_id"],
                                "preload_run_id": contract["preload_run_id"],
                                "writes_outbox": False,
                                "write_result": summarize_write_result(object_results, quality_items),
                                "actual_asset_counts": summarize_actual_asset_counts(object_results),
                                "mootdx_batch_attempt": dict(batch_attempt) if batch_attempt else None,
                            }
                        ),
                        contract["preload_run_id"],
                    ),
    )


def insert_quality_items(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
) -> int:
    if not quality_items:
        return 0
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
    rows = []
    for item in quality_items:
        rows.append(
            (
                contract["preload_run_id"],
                contract["source_condition_run_id"],
                contract["for_trade_date"],
                contract["source_trade_date"],
                item.get("data_domain") or "common",
                "market_data_run",
                item.get("table_name"),
                item.get("gate_code"),
                item.get("gate_name"),
                item.get("severity"),
                item.get("status"),
                item.get("expected_value"),
                item.get("actual_value"),
                item.get("identity_key"),
                Jsonb(item.get("details") or {}),
            )
        )
    cur.executemany(
        f"""
        INSERT INTO common_market_data_quality_item ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        rows,
    )
    return len(rows)


def capture_preload_execute_backup(
    dsn: str,
    *,
    phase: str,
    preload_run_id: str,
    source_run_id: str,
    previous_day_minute_date: str,
) -> dict[str, Any]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return _capture_preload_execute_backup_with_cursor(
            cur,
            phase=phase,
            preload_run_id=preload_run_id,
            source_run_id=source_run_id,
            previous_day_minute_date=previous_day_minute_date,
        )


def _capture_preload_execute_backup_with_cursor(
    cur: Any,
    *,
    phase: str,
    preload_run_id: str,
    source_run_id: str,
    previous_day_minute_date: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "captured_at": utc_now_iso(),
        "source_run_id": source_run_id,
        "preload_run_id": preload_run_id,
        "previous_day_minute_date": previous_day_minute_date,
        "active_snapshot": fetch_n1_n2_active_snapshot(cur),
        "preload_run_exists": market_data_run_exists(cur, preload_run_id),
        "preload_run_row": fetch_market_data_run_row(cur, preload_run_id),
        "source_run_row": fetch_market_data_run_row(cur, source_run_id),
        "target_table_row_counts": fetch_table_row_counts(cur, N3_A1_FACT_AND_STATUS_TABLES),
        "target_preload_run_row_counts": fetch_preload_run_row_counts(cur, preload_run_id),
        "target_preload_run_row_counts_by_asset": fetch_preload_run_counts_by_asset(
            cur, preload_run_id, previous_day_minute_date
        ),
        "duplicate_minute_key_count_by_asset": fetch_duplicate_minute_key_counts(
            cur, preload_run_id, previous_day_minute_date
        ),
        "physical_isolation_violation_count_by_asset": fetch_physical_isolation_violation_counts(
            cur, preload_run_id
        ),
        "common_event_outbox_row_count": fetch_table_count(cur, "common_event_outbox"),
        "common_event_inbox_row_count": fetch_table_count(cur, "common_event_inbox"),
        "common_event_consumer_checkpoint_row_count": fetch_table_count(
            cur, "common_event_consumer_checkpoint"
        ),
        "scoped_event_ref_counts": fetch_scoped_event_ref_counts(cur, preload_run_id),
    }


def market_data_run_exists(cur: Any, run_id: str) -> bool:
    cur.execute("SELECT 1 FROM common_market_data_run WHERE run_id = %s LIMIT 1", (run_id,))
    return cur.fetchone() is not None


def fetch_market_data_run_row(cur: Any, run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
               prev_trade_date, mode, status, p0_count, p1_count, p2_count,
               source_scope_row_count, candidate_row_count, subscription_row_count,
               subscription_object_count, dedup_ratio, market_data_pulled,
               market_data_fact_written, downstream_layers_touched, worker_started
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    return normalize_db_row(row) if row else None


def fetch_table_count(cur: Any, table_name: str) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
    return int(cur.fetchone()["row_count"])


def fetch_table_row_counts(cur: Any, table_names: Sequence[str]) -> dict[str, int]:
    return {table_name: fetch_table_count(cur, table_name) for table_name in table_names}


def fetch_scoped_event_ref_counts(cur: Any, preload_run_id: str) -> dict[str, int]:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s", (preload_run_id,))
    outbox_count = int(cur.fetchone()["row_count"])
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id = %s", (preload_run_id,))
    inbox_count = int(cur.fetchone()["row_count"])
    cur.execute(
        "SELECT count(*)::bigint AS row_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::TEXT LIKE %s",
        (f"%{preload_run_id}%",),
    )
    checkpoint_count = int(cur.fetchone()["row_count"])
    return {
        "common_event_outbox": outbox_count,
        "common_event_inbox": inbox_count,
        "common_event_consumer_checkpoint": checkpoint_count,
    }


def fetch_preload_run_row_counts(cur: Any, preload_run_id: str) -> dict[str, int]:
    counts = {}
    for table_name in (*N3_A1_FACT_AND_STATUS_TABLES, "common_market_data_quality_item", "common_market_data_run"):
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE run_id = %s", (preload_run_id,))
        counts[table_name] = int(cur.fetchone()["row_count"])
    return counts


def fetch_preload_run_counts_by_asset(cur: Any, preload_run_id: str, trade_date: str) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for asset_kind in ASSET_KINDS:
        minute_table, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["minute"]
        status_table, _, _ = ASSET_FACT_TABLES[asset_kind]["preload_status"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count,
                   count(DISTINCT {identity_column})::bigint AS object_count
            FROM {minute_table}
            WHERE run_id = %s AND trade_date = %s AND is_previous_day_preload = true
            """,
            (preload_run_id, trade_date),
        )
        minute = cur.fetchone()
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count,
                   count(DISTINCT {identity_column})::bigint AS object_count,
                   count(*) FILTER (WHERE status = 'passed')::bigint AS passed_count,
                   count(*) FILTER (WHERE status IN ('partial', 'missing', 'failed'))::bigint AS issue_count
            FROM {status_table}
            WHERE run_id = %s AND trade_date = %s
            """,
            (preload_run_id, trade_date),
        )
        status = cur.fetchone()
        output[asset_kind] = {
            "minute_row_count": int(minute["row_count"]),
            "minute_object_count": int(minute["object_count"]),
            "preload_status_row_count": int(status["row_count"]),
            "preload_status_object_count": int(status["object_count"]),
            "preload_passed_count": int(status["passed_count"]),
            "preload_issue_count": int(status["issue_count"]),
        }
    return output


def fetch_duplicate_minute_key_counts(cur: Any, preload_run_id: str, trade_date: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        minute_table, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["minute"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS duplicate_group_count
            FROM (
              SELECT run_id, trade_date, {identity_column}, bar_time, source_adapter, count(*) AS row_count
              FROM {minute_table}
              WHERE run_id = %s AND trade_date = %s
              GROUP BY run_id, trade_date, {identity_column}, bar_time, source_adapter
              HAVING count(*) > 1
            ) duplicates
            """,
            (preload_run_id, trade_date),
        )
        output[asset_kind] = int(cur.fetchone()["duplicate_group_count"])
    return output


def fetch_physical_isolation_violation_counts(cur: Any, preload_run_id: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        minute_table, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["minute"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS violation_count
            FROM {minute_table}
            WHERE run_id = %s AND {identity_column} NOT LIKE %s
            """,
            (preload_run_id, f"{asset_kind}:%"),
        )
        output[asset_kind] = int(cur.fetchone()["violation_count"])
    return output


def build_post_execute_checks(
    *,
    contract: Mapping[str, Any],
    pre_backup: Mapping[str, Any],
    data_snapshot: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_counts = contract.get("expected_asset_counts") or {}
    counts_by_asset = data_snapshot.get("target_preload_run_row_counts_by_asset") or {}
    actual_status_counts = {
        asset_kind: int((counts_by_asset.get(asset_kind) or {}).get("preload_status_object_count") or 0)
        for asset_kind in ASSET_KINDS
    }
    expected_status_counts = {
        asset_kind: int((expected_counts.get(asset_kind) or {}).get("object_count") or 0)
        for asset_kind in ASSET_KINDS
    }
    actual_rows = {
        asset_kind: int((counts_by_asset.get(asset_kind) or {}).get("minute_row_count") or 0)
        for asset_kind in ASSET_KINDS
    }
    expected_rows = {
        asset_kind: int((expected_counts.get(asset_kind) or {}).get("expected_minute_bar_rows") or 0)
        for asset_kind in ASSET_KINDS
    }
    duplicate_counts = data_snapshot.get("duplicate_minute_key_count_by_asset") or {}
    isolation_counts = data_snapshot.get("physical_isolation_violation_count_by_asset") or {}
    issue_counts = Counter(str(row.get("status") or "") for row in object_results)
    pre_scoped_event_refs = scoped_event_ref_counts(pre_backup)
    post_scoped_event_refs = scoped_event_ref_counts(data_snapshot)
    global_event_counts_before = global_event_counts(pre_backup)
    global_event_counts_after = global_event_counts(data_snapshot)
    return {
        "n3_a1_asset_object_count_matches_a0": actual_status_counts == expected_status_counts,
        "n3_a1_expected_status_counts": expected_status_counts,
        "n3_a1_actual_status_counts": actual_status_counts,
        "n3_a1_minute_rows_reasonable": all(0 <= actual_rows[asset_kind] <= expected_rows[asset_kind] for asset_kind in ASSET_KINDS),
        "n3_a1_total_minute_rows_present": sum(actual_rows.values()) > 0 or sum(expected_rows.values()) == 0,
        "n3_a1_expected_minute_rows_by_asset": expected_rows,
        "n3_a1_actual_minute_rows_by_asset": actual_rows,
        "n3_a1_duplicate_minute_key_zero": all(int(count or 0) == 0 for count in duplicate_counts.values()),
        "n3_a1_duplicate_minute_key_count_by_asset": dict(duplicate_counts),
        "n3_a1_missing_object_not_silent": sum(issue_counts.get(key, 0) for key in ("partial", "missing", "failed")) == int(
            sum((counts_by_asset.get(asset_kind) or {}).get("preload_issue_count") or 0 for asset_kind in ASSET_KINDS)
        ),
        "n3_a1_object_status_counts": dict(issue_counts),
        "n3_a1_physical_table_isolation": all(int(count or 0) == 0 for count in isolation_counts.values()),
        "n3_a1_physical_isolation_violation_count_by_asset": dict(isolation_counts),
        "n3_a1_scoped_event_refs_zero": all(int(count or 0) == 0 for count in [*pre_scoped_event_refs.values(), *post_scoped_event_refs.values()]),
        "n3_a1_scoped_event_ref_counts_before": pre_scoped_event_refs,
        "n3_a1_scoped_event_ref_counts_after": post_scoped_event_refs,
        "n3_a1_global_event_counts_unchanged": global_event_counts_before == global_event_counts_after,
        "n3_a1_global_event_counts_before": global_event_counts_before,
        "n3_a1_global_event_counts_after": global_event_counts_after,
        "n3_a1_n1_n2_active_snapshot_unchanged": stable_json_hash(pre_backup["active_snapshot"]) == stable_json_hash(data_snapshot["active_snapshot"]),
    }


def scoped_event_ref_counts(snapshot: Mapping[str, Any]) -> dict[str, int]:
    refs = snapshot.get("scoped_event_ref_counts")
    if isinstance(refs, Mapping):
        return {
            "common_event_outbox": int(refs.get("common_event_outbox") or 0),
            "common_event_inbox": int(refs.get("common_event_inbox") or 0),
            "common_event_consumer_checkpoint": int(refs.get("common_event_consumer_checkpoint") or 0),
        }
    return {
        "common_event_outbox": int(snapshot.get("common_event_outbox_scoped_row_count") or 0),
        "common_event_inbox": int(snapshot.get("common_event_inbox_scoped_row_count") or 0),
        "common_event_consumer_checkpoint": int(snapshot.get("common_event_consumer_checkpoint_scoped_row_count") or 0),
    }


def global_event_counts(snapshot: Mapping[str, Any]) -> dict[str, int]:
    return {
        "common_event_outbox": int(snapshot.get("common_event_outbox_row_count") or 0),
        "common_event_inbox": int(snapshot.get("common_event_inbox_row_count") or 0),
        "common_event_consumer_checkpoint": int(snapshot.get("common_event_consumer_checkpoint_row_count") or 0),
    }


def build_post_execute_quality_items(
    *,
    contract: Mapping[str, Any],
    post_checks: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    issue_results = [row for row in object_results if row.get("status") in {"partial", "missing", "failed"}]
    failed_results = [row for row in object_results if row.get("status") == "failed"]
    contract_p1 = int((contract.get("quality") or {}).get("p1_count") or 0)
    items = [
        quality_item(
            "P0",
            "passed" if post_checks["n3_a1_asset_object_count_matches_a0"] else "failed",
            "n3_a1_asset_object_count_matches_a0",
            "stock/index/board preload_status object_count must match A0",
            expected=json.dumps(post_checks["n3_a1_expected_status_counts"], ensure_ascii=False, sort_keys=True),
            actual=json.dumps(post_checks["n3_a1_actual_status_counts"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_a1_minute_rows_reasonable"] else "failed",
            "n3_a1_minute_rows_reasonable",
            "actual minute rows must be between zero and expected A-share minute rows",
            expected=json.dumps(post_checks["n3_a1_expected_minute_rows_by_asset"], ensure_ascii=False, sort_keys=True),
            actual=json.dumps(post_checks["n3_a1_actual_minute_rows_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_a1_total_minute_rows_present"] else "failed",
            "n3_a1_total_minute_rows_present",
            "a trading-day previous minute preload must write at least one minute row unless no rows were expected",
            expected=">0 when expected rows > 0",
            actual=str(sum(int(value) for value in post_checks["n3_a1_actual_minute_rows_by_asset"].values())),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_a1_duplicate_minute_key_zero"] else "failed",
            "n3_a1_duplicate_minute_key_zero",
            "duplicate minute key count must be zero in each physical table",
            expected="0",
            actual=json.dumps(post_checks["n3_a1_duplicate_minute_key_count_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_a1_missing_object_not_silent"] else "failed",
            "n3_a1_missing_object_not_silent",
            "missing or partial objects must have preload_status evidence",
            expected="issue object count equals issue preload_status count",
            actual=json.dumps(post_checks["n3_a1_object_status_counts"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_a1_physical_table_isolation"] else "failed",
            "n3_a1_physical_table_isolation",
            "identity_key prefix must match the physical minute table family",
            expected="0",
            actual=json.dumps(post_checks["n3_a1_physical_isolation_violation_count_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks.get("n3_a1_scoped_event_refs_zero", post_checks.get("n3_a1_outbox_rows_zero")) else "failed",
            "n3_a1_scoped_event_refs_zero",
            "N3-A1 writes_outbox=false and must not create scoped outbox/inbox/checkpoint refs",
            expected="scoped outbox/inbox/checkpoint refs = 0",
            actual=json.dumps(
                {
                    "before": post_checks.get("n3_a1_scoped_event_ref_counts_before", {}),
                    "after": post_checks.get("n3_a1_scoped_event_ref_counts_after", {}),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_a1_n1_n2_active_snapshot_unchanged"] else "failed",
            "n3_a1_n1_n2_active_snapshot_unchanged",
            "N3-A1 must not change N1/N2 active run state",
            expected="unchanged",
            actual="unchanged" if post_checks["n3_a1_n1_n2_active_snapshot_unchanged"] else "changed",
        ),
        quality_item(
            "P1",
            "warning" if contract_p1 > 0 else "passed",
            "n3_a1_contract_p1_carried",
            "N3-A1 carries non-blocking P1 items from the reviewed execute contract",
            expected="0",
            actual=str(contract_p1),
        ),
        quality_item(
            "P1",
            "warning" if not post_checks.get("n3_a1_global_event_counts_unchanged", True) else "passed",
            "n3_a1_global_event_counts_changed_scoped_safe",
            "Global event-table counts may change due unrelated pending work; A1 only requires scoped refs to stay zero",
            expected=json.dumps(post_checks.get("n3_a1_global_event_counts_before", {}), ensure_ascii=False, sort_keys=True),
            actual=json.dumps(post_checks.get("n3_a1_global_event_counts_after", {}), ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P1",
            "warning" if issue_results else "passed",
            "n3_a1_missing_or_partial_objects_recorded",
            "missing/partial/failed objects are allowed only when status evidence is recorded",
            expected="0",
            actual=str(len(issue_results)),
            details={"samples": [summarize_object_result(row) for row in issue_results[:20]]},
        ),
        quality_item(
            "P1",
            "warning" if failed_results else "passed",
            "n3_a1_adapter_failures_recorded",
            "adapter failures must be recorded as preload_status and quality evidence",
            expected="0",
            actual=str(len(failed_results)),
            details={"samples": [summarize_object_result(row) for row in failed_results[:20]]},
        ),
    ]
    for item in items:
        item.setdefault("details", {})
        item["details"] = {
            **(item.get("details") or {}),
            "source_run_id": contract["source_run_id"],
            "preload_run_id": contract["preload_run_id"],
        }
    return items


def summarize_object_result(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "asset_kind": row.get("asset_kind"),
        "identity_key": row.get("identity_key"),
        "subscription_id": row.get("subscription_id"),
        "status": row.get("status"),
        "actual_bar_count": row.get("actual_bar_count"),
        "error_message": row.get("error_message"),
    }


def summarize_actual_asset_counts(object_results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for asset_kind in ASSET_KINDS:
        rows = [row for row in object_results if row.get("asset_kind") == asset_kind]
        output[asset_kind] = {
            "object_count": len(rows),
            "minute_rows_written": sum(int(row.get("minute_rows_written") or 0) for row in rows),
            "passed_count": sum(1 for row in rows if row.get("status") == "passed"),
            "partial_count": sum(1 for row in rows if row.get("status") == "partial"),
            "missing_count": sum(1 for row in rows if row.get("status") == "missing"),
            "failed_count": sum(1 for row in rows if row.get("status") == "failed"),
        }
    return output


def summarize_write_result(
    object_results: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "objects_processed": len(object_results),
        "minute_rows_written": sum(int(row.get("minute_rows_written") or 0) for row in object_results),
        "preload_status_rows_written": len(object_results),
        "quality_item_rows_written": len(quality_items),
        "event_outbox_rows_written": 0,
    }


def format_previous_day_minute_execute_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    lines = [
        "# N3-A1 Previous-Day Minute Preload Execute Report",
        "",
        "## Summary",
        "",
        f"- stage: `{report['stage']}`",
        f"- layer_role: `{report['layer_role']}`",
        f"- source_run_id: `{report['source_run_id']}`",
        f"- preload_run_id: `{report['preload_run_id']}`",
        f"- previous_day_minute_date: `{report['previous_day_minute_date']}`",
        f"- objects_processed: `{write['objects_processed']}`",
        f"- minute_rows_written: `{write['minute_rows_written']}`",
        f"- preload_status_rows_written: `{write['preload_status_rows_written']}`",
        f"- quality_item_rows_written: `{write['quality_item_rows_written']}`",
        f"- event_outbox_rows_written: `{write['event_outbox_rows_written']}`",
        f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
        "",
        "## Asset Counts",
        "",
    ]
    for asset_kind, counts in (report.get("actual_asset_counts") or {}).items():
        lines.append(
            f"- {asset_kind}: objects=`{counts['object_count']}` minute_rows=`{counts['minute_rows_written']}` "
            f"passed=`{counts['passed_count']}` partial=`{counts['partial_count']}` "
            f"missing=`{counts['missing_count']}` failed=`{counts['failed_count']}`"
        )
    lines.extend(
        [
            "",
            "## Post Checks",
            "",
        ]
    )
    for key, value in (report.get("post_checks") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
        ]
    )
    for key, value in (report.get("side_effects") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Rollback",
            "",
            "- rollback_sql_path: `sql/N3_A1_previous_day_minute_rollback.sql`",
            "- rollback key: `source_run_id + preload_run_id`",
            "- common_event_outbox is not touched by N3-A1 rollback.",
            "",
        ]
    )
    return "\n".join(lines)


def normalize_db_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: normalize_db_value(value) for key, value in dict(row).items()}


def normalize_db_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
