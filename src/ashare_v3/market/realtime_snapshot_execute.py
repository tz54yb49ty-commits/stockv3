"""N3-B1 realtime daily snapshot run-once executor.

This module is intentionally limited to N3 market-data responsibilities:
validate a reviewed B1 contract/readiness gate, fetch one realtime snapshot
batch through an injected adapter, and write stock/index/board snapshot facts.
The 20260527 B1 contract is explicitly fact-only and writes no outbox rows.
It does not start workers and does not enter trigger/action/user layers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import importlib
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.ingestion.tushare_env import load_tushare_token
from ashare_v3.market.fact_writer import write_market_quality_with_event, write_market_snapshot_with_event
from ashare_v3.market.mootdx_batch_attempt import (
    MootdxBatchAttemptOutcome,
    MootdxBatchObjectTracker,
    MootdxEndpointSemanticValidationError,
    MootdxEndpointTransportError,
    is_endpoint_transport_exception,
    run_mootdx_batch_attempt,
    with_batch_attempt_provenance,
)
from ashare_v3.market.migration_execute import fetch_n1_n2_active_snapshot, stable_json_hash
from ashare_v3.market.n3_source_time_policy import (
    N3SourceTimePolicyError,
    SOURCE_RETURNED_TIME_POLICY,
    map_source_time_to_trade_window,
    source_marker_from_mapping,
)
from ashare_v3.market.preload_plan import REALTIME_SNAPSHOT_TABLES, normalize_db_row
from ashare_v3.market.previous_day_preload_execute import first_present, frame_to_records
from ashare_v3.market.realtime_snapshot_execute_contract import DEFAULT_B1_CONTRACT_JSON_PATH
from ashare_v3.market.realtime_snapshot_execute_readiness import DEFAULT_B1_READINESS_JSON_PATH
from ashare_v3.market.realtime_snapshot_plan import REQUIRED_DATA_KIND, build_realtime_subscription_report, realtime_snapshot_subscriptions
from ashare_v3.market.repositories import ASSET_FACT_TABLES, QualityRepository, SnapshotRepository
from ashare_v3.market.subscription_plan import ADAPTER_NAMES, ASSET_KINDS
from ashare_v3.mootdx_client import EndpointSelection, MootdxEndpointManager
from ashare_v3.quote_transport import (
    quote_transport_scope_blocker,
    resolve_quote_transport_name,
)


DEFAULT_N3_B1_PRE_BACKUP_PATH = "docs/N3_B1_realtime_daily_snapshot_execute_backup_before.json"
DEFAULT_N3_B1_POST_BACKUP_PATH = "docs/N3_B1_realtime_daily_snapshot_execute_backup_after.json"
DEFAULT_N3_B1_JSON_REPORT_PATH = "docs/N3_B1_realtime_daily_snapshot_execute_report.json"
DEFAULT_N3_B1_MD_REPORT_PATH = "docs/N3_B1_REALTIME_DAILY_SNAPSHOT_EXECUTE_REPORT.md"
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_SOURCE_TIME_FUTURE_TOLERANCE_SECONDS = 120

ALLOWED_B1_FACT_ONLY_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
)
ALLOWED_B1_WRITE_TABLES = (
    *ALLOWED_B1_FACT_ONLY_WRITE_TABLES,
    "common_event_outbox",
)
FORBIDDEN_B1_WRITE_TABLE_MARKERS = (
    "minute_bar_1m",
    "trigger",
    "action",
    "user",
    "voice",
    "sim",
    "position",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)


class RealtimeSnapshotExecuteError(RuntimeError):
    """Raised when N3-B1 execute violates its run-once contract."""


class MootdxRealtimeSnapshotAdapter:
    """Fetch realtime snapshot rows with Mootdx quote APIs.

    The adapter is lazy and is only instantiated by the execute path. Unit
    tests inject a fake adapter, so implementation tests never call external
    market-data APIs.
    """

    source_version = "mootdx.quotes.realtime_snapshot.v1"
    external_source = "mootdx"

    def __init__(self, *, client: Any | None = None, market: str = "std") -> None:
        self._client = client
        if self._client is None:
            raise RealtimeSnapshotExecuteError(
                "MootdxRealtimeSnapshotAdapter requires a manager-selected pinned client"
            )

    def fetch_snapshot(self, subscription: Mapping[str, Any], trade_date: str) -> dict[str, Any] | None:
        del trade_date
        code = str(subscription.get("code") or "")
        frame = self._client.quotes(symbol=code)
        rows = normalize_snapshot_records(frame)
        return rows[0] if rows else None


class BoardMarketDataAdapter:
    """Fetch TDX 881xxx board snapshots through the index-like TDX path."""

    source_version = "mootdx.quotes.board_index_snapshot.v1"
    external_source = "mootdx"
    source_path = "std.index"
    adapter_name = "BoardMarketDataAdapter"

    def __init__(self, *, client: Any | None = None, market: str = "std") -> None:
        self._client = client
        if self._client is None:
            raise RealtimeSnapshotExecuteError(
                "BoardMarketDataAdapter requires a manager-selected pinned client"
            )

    def fetch_snapshot(self, subscription: Mapping[str, Any], trade_date: str) -> dict[str, Any] | None:
        code = str(subscription.get("code") or "")
        frame = self._client.index(symbol=code, frequency=9, start=0, offset=5)
        rows = frame_to_records(frame)
        if not rows:
            return None

        tail = dict(rows[-1])
        snapshot_time = parse_tdx_record_datetime(tail)
        if snapshot_time is None or snapshot_time.astimezone(ASIA_SHANGHAI).strftime("%Y%m%d") != trade_date:
            return None

        previous = dict(rows[-2]) if len(rows) >= 2 else {}
        close_value = first_present(tail, "close", "price")
        observed_at = utc_now().astimezone(ASIA_SHANGHAI).isoformat()
        return {
            "open": first_present(tail, "open"),
            "high": first_present(tail, "high"),
            "low": first_present(tail, "low"),
            "close": close_value,
            "current_price": close_value,
            "pre_close": first_present(previous, "close", "price"),
            "volume": first_present(tail, "volume", "vol"),
            "amount": first_present(tail, "amount"),
            "raw_snapshot_time_label": snapshot_time.astimezone(ASIA_SHANGHAI).isoformat(),
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": observed_at,
            "fetched_at": observed_at,
            "adapter_name": self.adapter_name,
            "source_path": self.source_path,
            "source_version": self.source_version,
            "external_source": self.external_source,
            "raw_payload": tail,
        }


class IndexMarketDataAdapter:
    """Fetch SH/SZ index snapshots through Mootdx's index path.

    The generic quote path accepts naked codes and can route duplicate index
    codes to stocks. This adapter keeps index subscriptions on the index API
    and leaves the TDX period label as trace instead of trusted event time.
    """

    source_version = "mootdx.quotes.index_snapshot.v1"
    external_source = "mootdx"
    source_path = "std.index"
    adapter_name = "IndexMarketDataAdapter"

    def __init__(self, *, client: Any | None = None, market: str = "std") -> None:
        self._client = client
        if self._client is None:
            raise RealtimeSnapshotExecuteError(
                "IndexMarketDataAdapter requires a manager-selected pinned client"
            )

    def fetch_snapshot(self, subscription: Mapping[str, Any], trade_date: str) -> dict[str, Any] | None:
        code = str(subscription.get("code") or "")
        frame = self._client.index(symbol=code, frequency=9, start=0, offset=5)
        rows = frame_to_records(frame)
        if not rows:
            return None

        tail = dict(rows[-1])
        snapshot_time = parse_tdx_record_datetime(tail)
        if snapshot_time is None or snapshot_time.astimezone(ASIA_SHANGHAI).strftime("%Y%m%d") != trade_date:
            return None

        previous = dict(rows[-2]) if len(rows) >= 2 else {}
        close_value = first_present(tail, "close", "price")
        observed_at = utc_now().astimezone(ASIA_SHANGHAI).isoformat()
        exchange = str(subscription.get("exchange") or "").upper()
        raw_market = exchange_to_tdx_market(exchange)
        raw_payload = {
            **tail,
            "market": raw_market,
            "code": code,
            "asset_kind": "index",
            "identity_key": subscription.get("identity_key"),
        }
        return {
            "open": first_present(tail, "open"),
            "high": first_present(tail, "high"),
            "low": first_present(tail, "low"),
            "close": close_value,
            "current_price": close_value,
            "pre_close": first_present(previous, "close", "price"),
            "volume": first_present(tail, "volume", "vol"),
            "amount": first_present(tail, "amount"),
            "raw_snapshot_time_label": snapshot_time.astimezone(ASIA_SHANGHAI).isoformat(),
            "raw_snapshot_time_semantics": "tdx_index_frequency_9_period_label",
            "source_time_trust_level": "untrusted_period_label",
            "observed_at": observed_at,
            "fetched_at": observed_at,
            "market": raw_market,
            "code": code,
            "asset_kind": "index",
            "raw_route_market": raw_market,
            "raw_route_code": code,
            "raw_route_asset_kind": "index",
            "adapter_name": self.adapter_name,
            "source_path": self.source_path,
            "source_version": self.source_version,
            "external_source": self.external_source,
            "raw_payload": raw_payload,
        }


class TushareBjIndexSnapshotAdapter:
    """Fetch BJ index snapshots from Tushare index_daily as a fact-only fallback."""

    source_version = "tushare.index_daily.bj_snapshot_fallback.v1"
    external_source = "tushare"
    source_path = "tushare.index_daily"
    adapter_name = "TushareBjIndexSnapshotAdapter"

    def __init__(self, *, client: Any | None = None, token: str | None = None) -> None:
        self._client = client
        self._token = token or load_tushare_token()

    def fetch_snapshot(self, subscription: Mapping[str, Any], trade_date: str) -> dict[str, Any] | None:
        code = str(subscription.get("code") or "")
        ts_code = str(subscription.get("display_code") or "")
        if not ts_code or "." not in ts_code:
            ts_code = f"{code}.BJ"
        rows = self._query_index_daily(ts_code=ts_code, trade_date=trade_date)
        if rows:
            row = dict(rows[0])
            if str(row.get("trade_date") or "") == trade_date:
                return self._snapshot_from_index_daily_row(row, source_path=self.source_path)

        prev_trade_date = str(subscription.get("prev_trade_date") or "")
        if prev_trade_date:
            previous_rows = self._query_index_daily(ts_code=ts_code, trade_date=prev_trade_date)
            if previous_rows:
                previous = dict(previous_rows[0])
                if str(previous.get("trade_date") or "") == prev_trade_date:
                    return self._bootstrap_from_previous_close(previous, for_trade_date=trade_date)
        return None

    def _query_index_daily(self, *, ts_code: str, trade_date: str) -> list[dict[str, Any]]:
        frame = self._client_or_raise().index_daily(
            ts_code=ts_code,
            start_date=trade_date,
            end_date=trade_date,
            fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount",
        )
        return [dict(row) for row in frame_to_records(frame)]

    def _snapshot_from_index_daily_row(self, row: Mapping[str, Any], *, source_path: str) -> dict[str, Any]:
        close_value = first_present(row, "close")
        return {
            "open": first_present(row, "open"),
            "high": first_present(row, "high"),
            "low": first_present(row, "low"),
            "close": close_value,
            "current_price": close_value,
            "pre_close": first_present(row, "pre_close"),
            "volume": first_present(row, "vol", "volume"),
            "amount": first_present(row, "amount"),
            "snapshot_time": None,
            "adapter_name": self.adapter_name,
            "source_path": self.source_path,
            "source_version": self.source_version,
            "external_source": self.external_source,
            "raw_payload": row,
        }

    def _bootstrap_from_previous_close(self, previous: Mapping[str, Any], *, for_trade_date: str) -> dict[str, Any] | None:
        close_value = first_present(previous, "close")
        if close_value is None:
            return None
        raw_payload = {
            **dict(previous),
            "previous_trade_date_bootstrap": True,
            "source_trade_date": str(previous.get("trade_date") or ""),
            "for_trade_date": for_trade_date,
        }
        return {
            "open": close_value,
            "high": close_value,
            "low": close_value,
            "close": close_value,
            "current_price": close_value,
            "pre_close": close_value,
            "volume": 0,
            "amount": 0,
            "snapshot_time": None,
            "adapter_name": self.adapter_name,
            "source_path": "tushare.index_daily.previous_trade_date_bootstrap",
            "source_version": self.source_version,
            "external_source": self.external_source,
            "raw_payload": raw_payload,
        }

    def _client_or_raise(self) -> Any:
        if self._client is None:
            if not self._token:
                raise RealtimeSnapshotExecuteError("TUSHARE_TOKEN is required for BJ index realtime snapshot fallback")
            tushare = importlib.import_module("tushare")
            self._client = tushare.pro_api(self._token)
        return self._client


class AssetRoutingRealtimeSnapshotAdapter:
    """Route asset families to source-specific adapters."""

    source_version = "mootdx.quotes.asset_routing_snapshot.v1"
    external_source = "mootdx"

    def __init__(
        self,
        *,
        default_adapter: Any | None = None,
        index_adapter: Any | None = None,
        board_adapter: Any | None = None,
        bj_index_adapter: Any | None = None,
    ) -> None:
        if default_adapter is None or index_adapter is None or board_adapter is None:
            raise RealtimeSnapshotExecuteError(
                "AssetRoutingRealtimeSnapshotAdapter requires pinned stock/index/board adapters"
            )
        self.default_adapter = default_adapter
        self.index_adapter = index_adapter
        self.board_adapter = board_adapter
        self.bj_index_adapter = bj_index_adapter or TushareBjIndexSnapshotAdapter()

    def fetch_snapshot(self, subscription: Mapping[str, Any], trade_date: str) -> dict[str, Any] | None:
        return self.adapter_for_subscription(subscription).fetch_snapshot(subscription, trade_date)

    def adapter_for_subscription(self, subscription: Mapping[str, Any]) -> Any:
        route = _snapshot_provider_route(subscription)
        if route == "mootdx_board":
            return self.board_adapter
        if route == "tushare_bj_index":
            return self.bj_index_adapter
        if route == "mootdx_index":
            return self.index_adapter
        return self.default_adapter


def run_realtime_daily_snapshot_execute(
    *,
    dsn: str,
    contract_path: str = DEFAULT_B1_CONTRACT_JSON_PATH,
    readiness_path: str = DEFAULT_B1_READINESS_JSON_PATH,
    pre_backup_path: str = DEFAULT_N3_B1_PRE_BACKUP_PATH,
    post_backup_path: str = DEFAULT_N3_B1_POST_BACKUP_PATH,
    json_report_path: str = DEFAULT_N3_B1_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N3_B1_MD_REPORT_PATH,
    for_trade_date: str | None = None,
    snapshot_run_id: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    no_outbox: bool = False,
    allow_outbox: bool = False,
    pre_open_source_policy: bool = False,
    adapter: Any | None = None,
    endpoint_manager: MootdxEndpointManager | None = None,
    endpoint_probe: Callable[..., Mapping[str, Any]] | None = None,
    endpoint_client_factory: Callable[[EndpointSelection], Any] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> dict[str, Any]:
    """Execute a single N3-B1 realtime snapshot run from reviewed artifacts."""

    contract = read_json(contract_path)
    readiness = read_json(readiness_path)
    ensure_executable_contract(
        contract,
        readiness,
        execute=execute,
        user_confirmed=user_confirmed,
        no_outbox=no_outbox,
        allow_outbox=allow_outbox,
        pre_open_source_policy=pre_open_source_policy,
        for_trade_date=for_trade_date,
        snapshot_run_id=snapshot_run_id,
    )
    resolved_snapshot_run_id = str(contract["snapshot_run_id"])
    source_run_id = str(contract["source_run_id"])
    started_at = utc_now_iso()

    pre_backup = capture_snapshot_execute_backup(
        dsn,
        phase="before_n3_b1",
        snapshot_run_id=resolved_snapshot_run_id,
        source_run_id=source_run_id,
        for_trade_date=str(contract["for_trade_date"]),
    )
    ensure_clean_snapshot_target(pre_backup, resolved_snapshot_run_id)
    write_json(pre_backup_path, pre_backup)

    subscription_report = build_realtime_subscription_report(dsn=dsn, market_data_run_id=source_run_id)
    subscriptions = realtime_snapshot_subscriptions(subscription_report)
    ensure_subscription_counts_match_contract(subscriptions, contract)

    source_run_row = fetch_market_data_run_row_by_id(dsn, source_run_id)
    resolved_adapter = adapter
    prepared_snapshots: list[dict[str, Any]] | None = None
    endpoint_outcome: MootdxBatchAttemptOutcome[Any] | None = None
    if resolved_adapter is None:
        prepared_snapshots, endpoint_outcome = prepare_mootdx_snapshot_batch(
            contract=contract,
            subscriptions=subscriptions,
            manager=endpoint_manager or MootdxEndpointManager.from_toml(),
            probe=endpoint_probe or build_default_mootdx_endpoint_probe(subscriptions),
            client_factory=endpoint_client_factory,
            snapshot_time=parse_datetime_like(started_at) or utc_now(),
            progress_callback=progress_callback,
            progress_every=progress_every,
        )
    elif bool(contract.get("writes_outbox")):
        prepared_snapshots = prepare_subscription_snapshots(
            contract=contract,
            subscriptions=subscriptions,
            adapter=resolved_adapter,
            snapshot_time=parse_datetime_like(started_at) or utc_now(),
            progress_callback=progress_callback,
            progress_every=progress_every,
        )
    if prepared_snapshots is not None and bool(contract.get("writes_outbox")):
        precheck = build_run_level_atomic_source_time_precheck(
            contract=contract,
            prepared_snapshots=prepared_snapshots,
        )
        if not precheck["passed"] and not (
            endpoint_outcome is not None and endpoint_outcome.status == "failed"
        ):
            object_results = no_write_object_results(prepared_snapshots)
            quality_items = build_run_level_atomic_precheck_quality_items(
                contract=contract,
                precheck=precheck,
            )
            report = build_run_level_atomic_precheck_blocked_report(
                contract=contract,
                contract_path=contract_path,
                readiness_path=readiness_path,
                pre_backup_path=pre_backup_path,
                post_backup_path=post_backup_path,
                pre_backup=pre_backup,
                object_results=object_results,
                quality_items=quality_items,
                precheck=precheck,
                started_at=started_at,
            )
            write_json(post_backup_path, pre_backup)
            write_json(json_report_path, report)
            write_text(markdown_report_path, format_realtime_snapshot_execute_report(report))
            return report

    endpoint_failure_committed = False
    atomic_committed = False
    if endpoint_outcome is not None and endpoint_outcome.status == "failed":
        object_results = write_failed_snapshot_attempt_transaction(
            dsn=dsn,
            contract=contract,
            source_run_row=source_run_row,
            started_at=started_at,
            prepared_snapshots=prepared_snapshots or [],
            outcome=endpoint_outcome,
        )
        endpoint_failure_committed = True
    elif endpoint_outcome is not None and endpoint_outcome.status == "passed":
        object_results, data_snapshot, post_checks, quality_items = commit_snapshot_attempt_transaction(
            dsn=dsn,
            contract=contract,
            source_run_row=source_run_row,
            started_at=started_at,
            prepared_snapshots=prepared_snapshots or [],
            outcome=endpoint_outcome,
        )
        atomic_committed = True

    if not endpoint_failure_committed and not atomic_committed:
        insert_snapshot_run(
            dsn,
            contract=contract,
            source_run_row=source_run_row,
            started_at=started_at,
            batch_attempt=endpoint_outcome.to_provenance() if endpoint_outcome is not None else None,
        )

    if not endpoint_failure_committed and not atomic_committed and prepared_snapshots is not None:
        object_results = write_prepared_subscription_snapshots(
            dsn=dsn,
            contract=contract,
            prepared_snapshots=prepared_snapshots,
        )
    elif not endpoint_failure_committed and not atomic_committed:
        object_results = execute_subscription_snapshots(
            dsn=dsn,
            contract=contract,
            subscriptions=subscriptions,
            adapter=resolved_adapter,
            progress_callback=progress_callback,
            progress_every=progress_every,
        )

    if not atomic_committed:
        data_snapshot = capture_snapshot_execute_backup(
            dsn,
            phase="after_n3_b1_data_before_quality",
            snapshot_run_id=resolved_snapshot_run_id,
            source_run_id=source_run_id,
            for_trade_date=str(contract["for_trade_date"]),
        )
        post_checks = build_post_execute_checks(
            contract=contract,
            data_snapshot=data_snapshot,
            object_results=object_results,
        )
        quality_items = build_post_execute_quality_items(
            contract=contract,
            post_checks=post_checks,
            object_results=object_results,
        )
    quality_counts = count_quality_severities(quality_items)
    if not endpoint_failure_committed and not atomic_committed:
        write_snapshot_quality_and_finalize_run(
            dsn,
            contract=contract,
            quality_items=quality_items,
            object_results=object_results,
            status="passed" if quality_counts["P0"] == 0 else "failed",
            batch_attempt=endpoint_outcome.to_provenance() if endpoint_outcome is not None else None,
        )

    post_backup = capture_snapshot_execute_backup(
        dsn,
        phase="after_n3_b1",
        snapshot_run_id=resolved_snapshot_run_id,
        source_run_id=source_run_id,
        for_trade_date=str(contract["for_trade_date"]),
    )
    write_json(post_backup_path, post_backup)

    report = {
        "stage": "N3-B1",
        "result": "EXECUTE_PASS",
        "layer_role": "N3_market_data",
        "execution_mode": "realtime_daily_snapshot_run_once_execute",
        "source_run_id": source_run_id,
        "snapshot_run_id": resolved_snapshot_run_id,
        "source_condition_run_id": contract["source_condition_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "source_trade_date": contract["source_trade_date"],
        "prev_trade_date": contract["prev_trade_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "contract_path": contract_path,
        "readiness_path": readiness_path,
        "pre_backup_path": pre_backup_path,
        "post_backup_path": post_backup_path,
        "expected_asset_counts": contract["expected_asset_counts"],
        "writes_outbox": bool(contract.get("writes_outbox")),
        "generated_outbox_events": []
        if not bool(contract.get("writes_outbox"))
        else (contract.get("event_contract") or {}).get("generated_outbox_events_in_b1_default", []),
        "allowed_write_tables": list(ALLOWED_B1_FACT_ONLY_WRITE_TABLES)
        if not bool(contract.get("writes_outbox"))
        else list(ALLOWED_B1_WRITE_TABLES),
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
            "target_snapshot_run_row_counts": pre_backup["target_snapshot_run_row_counts"],
            "snapshot_outbox_row_count": pre_backup["snapshot_outbox_row_count"],
            "downstream_inbox_row_count": pre_backup["downstream_inbox_row_count"],
            "checkpoint_ref_count": pre_backup["checkpoint_ref_count"],
        },
        "post_execute": {
            "active_snapshot_hash": stable_json_hash(post_backup["active_snapshot"]),
            "target_snapshot_run_row_counts": post_backup["target_snapshot_run_row_counts"],
            "snapshot_outbox_row_count": post_backup["snapshot_outbox_row_count"],
            "downstream_inbox_row_count": post_backup["downstream_inbox_row_count"],
            "checkpoint_ref_count": post_backup["checkpoint_ref_count"],
            "snapshot_run_row": post_backup["snapshot_run_row"],
        },
        "side_effects": {
            "writes_performed": True,
            "migration_executed": False,
            "market_data_pulled": True,
            "realtime_snapshot_written": any(int(item.get("snapshot_rows_written") or 0) > 0 for item in object_results),
            "event_outbox_written": any(int(item.get("outbox_rows_written") or 0) > 0 for item in object_results),
            "minute_bar_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_realtime_snapshot_execute_report(report))
    return report


def prepare_mootdx_snapshot_batch(
    *,
    contract: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    manager: MootdxEndpointManager,
    probe: Callable[..., Mapping[str, Any]],
    client_factory: Callable[[EndpointSelection], Any] | None = None,
    transport: str | None = None,
    snapshot_time: datetime,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> tuple[list[dict[str, Any]], MootdxBatchAttemptOutcome[Any]]:
    resolved_transport = resolve_quote_transport_name(transport)
    capability_blocker = quote_transport_scope_blocker(
        resolved_transport,
        subscriptions,
    )
    if capability_blocker is not None:
        raise RealtimeSnapshotExecuteError(
            f"{capability_blocker['blocker']}:"
            + ",".join(capability_blocker["unsupported_identity_keys"])
        )
    outcome = run_mootdx_batch_attempt(
        manager=manager,
        batch_id=str(contract["snapshot_run_id"]),
        probe=probe,
        client_factory=client_factory,
        transport=resolved_transport,
        fetch_batch=lambda client, selection: _prepare_complete_snapshot_attempt(
            contract=contract,
            subscriptions=subscriptions,
            client=client,
            snapshot_time=snapshot_time,
            progress_callback=progress_callback,
            progress_every=progress_every,
            object_tracker=MootdxBatchObjectTracker(manager, selection),
        ),
    )
    if outcome.status == "passed":
        prepared = list(outcome.result or [])
    else:
        prepared = prepare_subscription_snapshots(
            contract=contract,
            subscriptions=subscriptions,
            adapter=_FailedMootdxSnapshotBatchAdapter(),
            snapshot_time=snapshot_time,
        )
    return [_trace_prepared_snapshot(row, outcome) for row in prepared], outcome


def _prepare_complete_snapshot_attempt(
    *,
    contract: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    client: Any,
    snapshot_time: datetime,
    progress_callback: Callable[[str], None] | None,
    progress_every: int,
    object_tracker: MootdxBatchObjectTracker,
) -> list[dict[str, Any]]:
    adapter = AssetRoutingRealtimeSnapshotAdapter(
        default_adapter=MootdxRealtimeSnapshotAdapter(client=client),
        index_adapter=IndexMarketDataAdapter(client=client),
        board_adapter=BoardMarketDataAdapter(client=client),
    )
    prepared: list[dict[str, Any]] = []
    for subscription in subscriptions:
        item = prepare_one_subscription_snapshot(
            contract=contract,
            subscription=subscription,
            adapter=adapter,
            snapshot_time=snapshot_time,
        )
        fetch_status = item.get("_attempt_fetch_status")
        if fetch_status == "transport_error":
            raise MootdxEndpointTransportError(
                str((item.get("object_result") or {}).get("error_message"))
            )
        object_tracker.record(
            identity_key=str(subscription.get("identity_key") or ""),
            value=item,
            empty=fetch_status == "empty_required_object",
        )
        prepared.append(item)
    empty_objects = [row for row in prepared if row.get("_attempt_fetch_status") == "empty_required_object"]
    blocking = [
        row
        for row in prepared
        if row.get("write_kind") != "snapshot"
        and row.get("_attempt_fetch_status") != "empty_required_object"
    ]
    if blocking:
        raise MootdxEndpointSemanticValidationError(
            f"atomic Mootdx snapshot attempt incomplete: {len(blocking)} subscription(s)"
        )
    if empty_objects:
        return prepared
    precheck = build_run_level_atomic_source_time_precheck(
        contract=contract,
        prepared_snapshots=prepared,
    )
    if not precheck["passed"]:
        raise MootdxEndpointSemanticValidationError(
            f"atomic Mootdx snapshot source-time precheck failed: {len(precheck['blockers'])} blocker(s)"
        )
    return prepared


def build_default_mootdx_endpoint_probe(
    subscriptions: Sequence[Mapping[str, Any]],
) -> Callable[[Any, Callable[[str], Any]], Mapping[str, Any]]:
    mootdx_subscriptions = [row for row in subscriptions if _uses_mootdx_snapshot_route(row)]
    sentinels = {
        asset_kind: sorted(
            (row for row in mootdx_subscriptions if str(row.get("asset_kind") or "") == asset_kind),
            key=lambda row: str(row.get("identity_key") or ""),
        )[0]
        for asset_kind in ASSET_KINDS
        if any(str(row.get("asset_kind") or "") == asset_kind for row in mootdx_subscriptions)
    }

    def probe(endpoint: Any, make_client: Callable[[str], Any]) -> Mapping[str, Any]:
        del endpoint
        client = make_client("std")
        quote_rows = normalize_snapshot_records(client.quotes(symbol="600000"))
        quote_ok = bool(
            quote_rows
            and snapshot_has_effective_quote(quote_rows[0])
            and _probe_row_identity_matches(quote_rows[0], expected_code="600000")
        )
        daily_rows = frame_to_records(client.bars(symbol="600000", frequency=9, start=0, offset=3))
        daily_ok = _daily_probe_rows_valid(daily_rows, expected_code="600000", minimum_rows=3)
        index_rows = frame_to_records(client.index_bars(symbol="000001", frequency=9, start=0, offset=3))
        index_ok = _daily_probe_rows_valid(index_rows, expected_code="000001", minimum_rows=1)
        sentinel_ok = all(_snapshot_sentinel_valid(client, row) for row in sentinels.values())
        return {
            "checks": {
                "stock_quote": quote_ok,
                "stock_daily_bars": daily_ok,
                "index_daily_bars": index_ok,
                "scope_sentinels": sentinel_ok,
            }
        }

    return probe


def _uses_mootdx_snapshot_route(subscription: Mapping[str, Any]) -> bool:
    return _snapshot_provider_route(subscription).startswith("mootdx_")


def _snapshot_provider_route(subscription: Mapping[str, Any]) -> str:
    asset_kind = str(subscription.get("asset_kind") or "")
    exchange = str(subscription.get("exchange") or "").upper()
    if asset_kind == "board" and exchange == "TDX":
        return "mootdx_board"
    if asset_kind == "index" and exchange == "BJ":
        return "tushare_bj_index"
    if asset_kind == "index":
        return "mootdx_index"
    return "mootdx_default"


def _probe_row_identity_matches(row: Mapping[str, Any], *, expected_code: str) -> bool:
    raw_code = first_present(row, "code", "symbol")
    raw_payload = row.get("raw_payload")
    if raw_code is None and isinstance(raw_payload, Mapping):
        raw_code = first_present(raw_payload, "code", "symbol")
    return raw_code is not None and normalize_route_code(raw_code) == normalize_route_code(expected_code)


def _daily_probe_rows_valid(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_code: str,
    minimum_rows: int,
) -> bool:
    if len(rows) < minimum_rows:
        return False
    if any(not _probe_row_identity_matches(row, expected_code=expected_code) for row in rows):
        return False
    labels = [str(first_present(row, "datetime", "date", "trade_date") or "") for row in rows]
    return (
        all(labels)
        and (labels == sorted(labels) or labels == sorted(labels, reverse=True))
        and len(set(labels)) == len(labels)
    )


def _snapshot_sentinel_valid(client: Any, subscription: Mapping[str, Any]) -> bool:
    asset_kind = str(subscription.get("asset_kind") or "")
    code = str(subscription.get("code") or "")
    if asset_kind == "stock":
        rows = normalize_snapshot_records(client.quotes(symbol=code))
    else:
        rows = frame_to_records(client.index(symbol=code, frequency=9, start=0, offset=1))
    if not rows or not snapshot_has_effective_quote(rows[-1]):
        return False
    return _probe_row_identity_matches(rows[-1], expected_code=code)


def default_mootdx_endpoint_probe(endpoint: Any, make_client: Callable[[str], Any]) -> Mapping[str, Any]:
    """Compatibility alias that fails closed without batch sentinel authority."""

    del endpoint
    del make_client
    return {
        "checks": {
            "stock_quote": False,
            "stock_daily_bars": False,
            "index_daily_bars": False,
            "scope_sentinels": False,
        }
    }


def _trace_prepared_snapshot(
    prepared: Mapping[str, Any],
    outcome: MootdxBatchAttemptOutcome[Any],
) -> dict[str, Any]:
    copied = dict(prepared)
    record_key = "snapshot_record" if copied.get("write_kind") == "snapshot" else "quality_record"
    record = copied.get(record_key)
    if isinstance(record, Mapping):
        copied[record_key] = with_batch_attempt_provenance(record, outcome)
    return copied


class _FailedMootdxSnapshotBatchAdapter:
    source_version = "mootdx.endpoint_batch.failed"
    external_source = "mootdx"

    def fetch_snapshot(self, subscription: Mapping[str, Any], trade_date: str) -> None:
        del subscription, trade_date
        raise MootdxEndpointTransportError(
            "atomic Mootdx snapshot batch failed; all attempt rows discarded"
        )


def ensure_execute_authorized(*, execute: bool, user_confirmed: bool) -> None:
    if not execute:
        raise RealtimeSnapshotExecuteError("N3-B1 execute requires explicit --execute")
    if not user_confirmed:
        raise RealtimeSnapshotExecuteError("N3-B1 execute requires explicit --user-confirmed")


def ensure_executable_contract(
    contract: Mapping[str, Any],
    readiness: Mapping[str, Any],
    *,
    execute: bool,
    user_confirmed: bool,
    no_outbox: bool = False,
    allow_outbox: bool = False,
    pre_open_source_policy: bool = False,
    for_trade_date: str | None,
    snapshot_run_id: str | None,
) -> None:
    ensure_execute_authorized(execute=execute, user_confirmed=user_confirmed)
    if contract.get("stage") != "N3-B1-preflight":
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: contract stage is not N3-B1-preflight")
    if contract.get("layer_role") != "N3_market_data":
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: contract layer_role is not N3_market_data")
    if int((contract.get("quality") or {}).get("p0_count") or 0) > 0:
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: execute contract has P0 findings")
    contract_writes_outbox = bool(contract.get("writes_outbox"))
    if contract_writes_outbox:
        if no_outbox:
            raise RealtimeSnapshotExecuteError("N3-B1 blocked: --no-outbox conflicts with a writes_outbox=true contract")
        if not allow_outbox:
            raise RealtimeSnapshotExecuteError("N3-B1 writes_outbox=true execute requires explicit --writes-outbox=true")
    else:
        if allow_outbox:
            raise RealtimeSnapshotExecuteError("N3-B1 blocked: --writes-outbox=true requires a writes_outbox=true contract")
        if not no_outbox:
            raise RealtimeSnapshotExecuteError("N3-B1 fact-only execute requires explicit --no-outbox")
    source_time_policy = contract.get("source_time_policy") or {}
    if source_time_policy.get("mode") == "pre_open_fact_only" and not pre_open_source_policy:
        raise RealtimeSnapshotExecuteError("N3-B1 pre-open execute requires explicit --pre-open-source-policy")
    if pre_open_source_policy and source_time_policy.get("mode") != "pre_open_fact_only":
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: --pre-open-source-policy requires a pre_open_fact_only contract")
    if readiness.get("stage") != "N3-B1-readiness-gate":
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: readiness stage is not N3-B1-readiness-gate")
    if readiness.get("ready") is not True or int((readiness.get("quality") or {}).get("p0_count") or 0) > 0:
        raise RealtimeSnapshotExecuteError(
            f"N3-B1 blocked: readiness is not ready ({readiness.get('blocked_reason')})"
        )
    if contract.get("source_run_id") != readiness.get("source_run_id"):
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: source_run_id mismatch between contract and readiness")
    if contract.get("snapshot_run_id") != readiness.get("snapshot_run_id"):
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: snapshot_run_id mismatch between contract and readiness")
    if for_trade_date and for_trade_date != str(contract.get("for_trade_date") or ""):
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: CLI for_trade_date does not match contract")
    if snapshot_run_id and snapshot_run_id != str(contract.get("snapshot_run_id") or ""):
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: CLI snapshot_run_id does not match contract")


def ensure_clean_snapshot_target(backup: Mapping[str, Any], snapshot_run_id: str) -> None:
    if bool(backup.get("snapshot_run_exists")):
        raise RealtimeSnapshotExecuteError(f"N3-B1 blocked: snapshot run already exists: {snapshot_run_id}")
    dirty = {
        table_name: count
        for table_name, count in (backup.get("target_snapshot_run_row_counts") or {}).items()
        if table_name != "for_trade_date_marker" and int(count or 0) != 0
    }
    if dirty:
        raise RealtimeSnapshotExecuteError(f"N3-B1 blocked: snapshot target rows already exist: {dirty}")
    if int(backup.get("snapshot_outbox_row_count") or 0) != 0:
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: snapshot_run_id already has outbox rows")
    if int(backup.get("downstream_inbox_row_count") or 0) != 0:
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: snapshot_run_id already has downstream inbox rows")
    if int(backup.get("checkpoint_ref_count") or 0) != 0:
        raise RealtimeSnapshotExecuteError("N3-B1 blocked: snapshot_run_id already has checkpoint refs")


def prepare_subscription_snapshots(
    *,
    contract: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    adapter: Any,
    snapshot_time: datetime,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> list[dict[str, Any]]:
    """Fetch and validate all snapshots without writing any DB rows."""

    results: list[dict[str, Any]] = []
    total = len(subscriptions)
    for index, subscription in enumerate(subscriptions, start=1):
        if progress_callback and (index == 1 or index == total or index % max(progress_every, 1) == 0):
            progress_callback(
                f"N3-B1 realtime snapshot source-time precheck {index}/{total} "
                f"{subscription.get('asset_kind')} {subscription.get('identity_key')}"
            )
        results.append(
            prepare_one_subscription_snapshot(
                contract=contract,
                subscription=subscription,
                adapter=adapter,
                snapshot_time=snapshot_time,
            )
        )
    return results


def prepare_one_subscription_snapshot(
    *,
    contract: Mapping[str, Any],
    subscription: Mapping[str, Any],
    adapter: Any,
    snapshot_time: datetime,
) -> dict[str, Any]:
    adapter_name = adapter_name_for_subscription(contract, subscription)
    writes_outbox = bool(contract.get("writes_outbox"))
    try:
        raw_snapshot = adapter.fetch_snapshot(subscription, str(contract["for_trade_date"]))
    except Exception as exc:  # noqa: BLE001 - transport failures become quality evidence.
        if not is_endpoint_transport_exception(exc):
            raise
        error_message = f"{type(exc).__name__}: {exc}"
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=snapshot_time,
            status="warning",
            quality_status="failed",
            gate_code="n3_b1_realtime_snapshot_delayed",
            gate_name="realtime snapshot adapter failed or delayed",
            severity="P1",
            expected_value="fresh snapshot row",
            actual_value=error_message,
            error_message=error_message,
        )
        return {
            "_attempt_fetch_status": "transport_error",
            "write_kind": "quality",
            "quality_record": quality_record,
            "snapshot_record": None,
            "object_result": build_object_result(
                subscription=subscription,
                status="failed",
                quality_status="failed",
                event_type=None,
                snapshot_rows_written=0,
                quality_item_rows_written=1,
                outbox_rows_written=0,
                error_message=error_message,
            ),
        }

    if raw_snapshot is None:
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=snapshot_time,
            status="warning",
            quality_status="missing",
            gate_code="n3_b1_realtime_snapshot_missing",
            gate_name="realtime snapshot missing from source adapter",
            severity="P1",
            expected_value="snapshot row",
            actual_value="missing",
            error_message=None,
        )
        return {
            "_attempt_fetch_status": "empty_required_object",
            "write_kind": "quality",
            "quality_record": quality_record,
            "snapshot_record": None,
            "object_result": build_object_result(
                subscription=subscription,
                status="missing",
                quality_status="missing",
                event_type=None,
                snapshot_rows_written=0,
                quality_item_rows_written=1,
                outbox_rows_written=0,
                error_message=None,
            ),
        }

    identity_route_evidence = build_snapshot_identity_route_evidence(
        subscription=subscription,
        raw_snapshot=raw_snapshot,
    )
    if identity_route_evidence["identity_route_status"] == "identity_route_mismatch":
        error_message = str(
            identity_route_evidence.get("identity_route_status_reason")
            or "raw quote route does not match subscription identity"
        )
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=snapshot_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_identity_route_mismatch",
            gate_name="raw quote identity route must match subscription identity",
            severity="P0",
            expected_value=str(identity_route_evidence.get("expected_route")),
            actual_value=str(identity_route_evidence.get("actual_route")),
            error_message=error_message,
        )
        return {
            "write_kind": "quality",
            "quality_record": quality_record,
            "snapshot_record": None,
            "object_result": build_object_result(
                subscription=subscription,
                status="failed",
                quality_status="failed",
                event_type=None,
                snapshot_rows_written=0,
                quality_item_rows_written=1,
                outbox_rows_written=0,
                error_message=error_message,
                identity_route_evidence=identity_route_evidence,
            ),
        }

    source_time_evidence = build_snapshot_source_time_evidence(
        contract=contract,
        raw_snapshot=raw_snapshot,
        default_time=snapshot_time,
        asset_kind=str(subscription.get("asset_kind") or ""),
    )
    if source_time_evidence["source_time_status"] == "source_time_date_mismatch":
        error_message = str(source_time_evidence.get("source_time_status_reason") or "source time date mismatch")
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=snapshot_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_source_time_date_mismatch",
            gate_name="source timestamp must not point to another trade date",
            severity="P0",
            expected_value=str(contract["for_trade_date"]),
            actual_value=str(source_time_evidence.get("source_snapshot_trade_date")),
            error_message=error_message,
        )
        return {
            "write_kind": "quality",
            "quality_record": quality_record,
            "snapshot_record": None,
            "object_result": build_object_result(
                subscription=subscription,
                status="failed",
                quality_status="failed",
                event_type=None,
                snapshot_rows_written=0,
                quality_item_rows_written=1,
                outbox_rows_written=0,
                error_message=error_message,
                source_time_evidence=source_time_evidence,
            ),
        }
    if source_time_evidence["source_time_status"] == "source_time_untrusted_label":
        error_message = str(source_time_evidence.get("source_time_status_reason") or "source time is an untrusted label")
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=snapshot_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_source_time_untrusted_label",
            gate_name="raw snapshot time label must not be used as realtime event time",
            severity="P0",
            expected_value="trusted realtime source_time or reviewed observed_at normalization policy",
            actual_value=str(source_time_evidence.get("raw_snapshot_time_label")),
            error_message=error_message,
        )
        return {
            "write_kind": "quality",
            "quality_record": quality_record,
            "snapshot_record": None,
            "object_result": build_object_result(
                subscription=subscription,
                status="failed",
                quality_status="failed",
                event_type=None,
                snapshot_rows_written=0,
                quality_item_rows_written=1,
                outbox_rows_written=0,
                error_message=error_message,
                source_time_evidence=source_time_evidence,
            ),
        }
    if source_time_evidence["source_time_status"] == "source_time_future":
        error_message = str(source_time_evidence.get("source_time_status_reason") or "source time is in the future")
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=snapshot_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_source_time_future",
            gate_name="source timestamp must not be later than execution time plus tolerance",
            severity="P0",
            expected_value=str(source_time_evidence.get("source_time_future_max_allowed") or "execution time + tolerance"),
            actual_value=str(source_time_evidence.get("source_snapshot_time")),
            error_message=error_message,
        )
        return {
            "write_kind": "quality",
            "quality_record": quality_record,
            "snapshot_record": None,
            "object_result": build_object_result(
                subscription=subscription,
                status="failed",
                quality_status="failed",
                event_type=None,
                snapshot_rows_written=0,
                quality_item_rows_written=1,
                outbox_rows_written=0,
                error_message=error_message,
                source_time_evidence=source_time_evidence,
            ),
        }
    if source_returned_time_status_blocks(source_time_evidence):
        error_message = str(source_time_evidence.get("source_time_status_reason") or "source-returned time invalid")
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=snapshot_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_source_returned_time_invalid",
            gate_name="source-returned timestamp must be valid before realtime snapshot write",
            severity="P0",
            expected_value="source_time_confirmed, source_time_label_normalized, or source_time_observed_at_fallback",
            actual_value=str(source_time_evidence.get("source_time_status")),
            error_message=error_message,
        )
        return {
            "write_kind": "quality",
            "quality_record": quality_record,
            "snapshot_record": None,
            "object_result": build_object_result(
                subscription=subscription,
                status="failed",
                quality_status="failed",
                event_type=None,
                snapshot_rows_written=0,
                quality_item_rows_written=1,
                outbox_rows_written=0,
                error_message=error_message,
                source_time_evidence=source_time_evidence,
            ),
        }

    snapshot_record = build_snapshot_record(
        contract=contract,
        subscription=subscription,
        adapter_name=adapter_name,
        adapter=adapter,
        raw_snapshot=raw_snapshot,
        snapshot_time=source_time_evidence["resolved_snapshot_time"],
        source_time_evidence=source_time_evidence,
        identity_route_evidence=identity_route_evidence,
    )
    return {
        "write_kind": "snapshot",
        "quality_record": None,
        "snapshot_record": snapshot_record,
        "object_result": build_object_result(
            subscription=subscription,
            status="passed",
            quality_status="passed",
            event_type="MarketSnapshotUpdated" if writes_outbox else None,
            snapshot_rows_written=1,
            quality_item_rows_written=0,
            outbox_rows_written=1 if writes_outbox else 0,
            error_message=None,
            source_time_evidence=source_time_evidence,
            identity_route_evidence=identity_route_evidence,
        ),
    }


def build_run_level_atomic_source_time_precheck(
    *,
    contract: Mapping[str, Any],
    prepared_snapshots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    blockers = []
    for prepared in prepared_snapshots:
        result = prepared.get("object_result") or {}
        if result.get("status") != "passed":
            blockers.append(summarize_object_result(result))
    future_source_time_count = sum(
        1
        for prepared in prepared_snapshots
        if ((prepared.get("object_result") or {}).get("source_time_status") == "source_time_future")
    )
    source_time_date_mismatch_count = sum(
        1
        for prepared in prepared_snapshots
        if ((prepared.get("object_result") or {}).get("source_time_status") == "source_time_date_mismatch")
    )
    untrusted_source_time_label_count = sum(
        1
        for prepared in prepared_snapshots
        if ((prepared.get("object_result") or {}).get("source_time_status") == "source_time_untrusted_label")
    )
    identity_route_mismatch_count = sum(
        1
        for prepared in prepared_snapshots
        if ((prepared.get("object_result") or {}).get("identity_route_status") == "identity_route_mismatch")
    )
    issue_count = len(blockers)
    return {
        "enabled": bool(contract.get("writes_outbox")),
        "passed": issue_count == 0,
        "handling": "P0_BLOCK_NO_DB_WRITE_NO_OUTBOX",
        "precheck_before_run_row": True,
        "objects_checked": len(prepared_snapshots),
        "p0_aggregate_blocker_count": issue_count,
        "future_source_time_count": future_source_time_count,
        "source_time_date_mismatch_count": source_time_date_mismatch_count,
        "untrusted_source_time_label_count": untrusted_source_time_label_count,
        "identity_route_mismatch_count": identity_route_mismatch_count,
        "blockers": blockers[:50],
    }


def build_run_level_atomic_precheck_quality_items(
    *,
    contract: Mapping[str, Any],
    precheck: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items = [
        quality_item(
            "P0",
            "failed",
            "n3_b1_run_level_atomic_source_time_precheck",
            "standard outbox B1 must validate all object source-time evidence before any DB write",
            expected="0 source-time or aggregate object blockers before write phase",
            actual=str(precheck.get("p0_aggregate_blocker_count") or 0),
            details={
                "source_run_id": contract["source_run_id"],
                "snapshot_run_id": contract["snapshot_run_id"],
                "handling": precheck.get("handling"),
                "future_source_time_count": precheck.get("future_source_time_count"),
                "source_time_date_mismatch_count": precheck.get("source_time_date_mismatch_count"),
                "untrusted_source_time_label_count": precheck.get("untrusted_source_time_label_count"),
                "identity_route_mismatch_count": precheck.get("identity_route_mismatch_count"),
                "samples": precheck.get("blockers") or [],
            },
        )
    ]
    contract_p1 = int((contract.get("quality") or {}).get("p1_count") or 0)
    if contract_p1:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_b1_contract_p1_carried",
                "N3-B1 carries non-blocking P1 items from the reviewed execute contract",
                expected="0",
                actual=str(contract_p1),
                details={
                    "source_run_id": contract["source_run_id"],
                    "snapshot_run_id": contract["snapshot_run_id"],
                },
            )
        )
    return items


def no_write_object_results(prepared_snapshots: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for prepared in prepared_snapshots:
        result = dict(prepared.get("object_result") or {})
        result["event_type"] = None
        result["snapshot_rows_written"] = 0
        result["quality_item_rows_written"] = 0
        result["outbox_rows_written"] = 0
        result["run_level_write_blocked"] = True
        output.append(result)
    return output


def build_run_level_atomic_precheck_blocked_report(
    *,
    contract: Mapping[str, Any],
    contract_path: str,
    readiness_path: str,
    pre_backup_path: str,
    post_backup_path: str,
    pre_backup: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
    precheck: Mapping[str, Any],
    started_at: str,
) -> dict[str, Any]:
    quality_counts = count_quality_severities(list(quality_items))
    return {
        "stage": "N3-B1",
        "result": "BLOCKED",
        "blocked_reason": "run_level_atomic_source_time_precheck_failed",
        "layer_role": "N3_market_data",
        "execution_mode": "realtime_daily_snapshot_run_once_execute",
        "source_run_id": contract["source_run_id"],
        "snapshot_run_id": contract["snapshot_run_id"],
        "source_condition_run_id": contract["source_condition_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "source_trade_date": contract["source_trade_date"],
        "prev_trade_date": contract["prev_trade_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "contract_path": contract_path,
        "readiness_path": readiness_path,
        "pre_backup_path": pre_backup_path,
        "post_backup_path": post_backup_path,
        "expected_asset_counts": contract["expected_asset_counts"],
        "writes_outbox": bool(contract.get("writes_outbox")),
        "generated_outbox_events": [],
        "allowed_write_tables": list(ALLOWED_B1_WRITE_TABLES),
        "atomic_source_time_precheck": dict(precheck),
        "actual_asset_counts": summarize_actual_asset_counts(object_results),
        "write_result": {
            "objects_processed": len(object_results),
            "snapshot_rows_written": 0,
            "quality_item_rows_written": 0,
            "event_outbox_rows_written": 0,
            "status_counts": dict(Counter(str(row.get("status") or "") for row in object_results)),
        },
        "post_checks": {
            "n3_b1_run_level_atomic_source_time_precheck": False,
            "n3_b1_no_partial_write": True,
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": list(quality_items),
        },
        "pre_execute": {
            "active_snapshot_hash": stable_json_hash(pre_backup["active_snapshot"]),
            "target_snapshot_run_row_counts": pre_backup["target_snapshot_run_row_counts"],
            "snapshot_outbox_row_count": pre_backup["snapshot_outbox_row_count"],
            "downstream_inbox_row_count": pre_backup["downstream_inbox_row_count"],
            "checkpoint_ref_count": pre_backup["checkpoint_ref_count"],
        },
        "post_execute": {
            "active_snapshot_hash": stable_json_hash(pre_backup["active_snapshot"]),
            "target_snapshot_run_row_counts": pre_backup["target_snapshot_run_row_counts"],
            "snapshot_outbox_row_count": pre_backup["snapshot_outbox_row_count"],
            "downstream_inbox_row_count": pre_backup["downstream_inbox_row_count"],
            "checkpoint_ref_count": pre_backup["checkpoint_ref_count"],
            "snapshot_run_row": pre_backup.get("snapshot_run_row"),
        },
        "side_effects": {
            "writes_performed": False,
            "migration_executed": False,
            "market_data_pulled": True,
            "realtime_snapshot_written": False,
            "event_outbox_written": False,
            "minute_bar_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def write_prepared_subscription_snapshots(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    prepared_snapshots: Sequence[Mapping[str, Any]],
    connection_factory: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    results = []
    connect = connection_factory or open_connection
    with connect(dsn) as conn:
        with conn.transaction():
            results.extend(
                _write_prepared_subscription_snapshots_on_connection(
                    conn,
                    contract=contract,
                    prepared_snapshots=prepared_snapshots,
                )
            )
    return results


def _write_prepared_subscription_snapshots_on_connection(
    conn: Any,
    *,
    contract: Mapping[str, Any],
    prepared_snapshots: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    writes_outbox = bool(contract.get("writes_outbox"))
    for prepared in prepared_snapshots:
        if prepared.get("write_kind") == "snapshot":
            snapshot_record = prepared.get("snapshot_record")
            if not isinstance(snapshot_record, Mapping):
                raise RealtimeSnapshotExecuteError("N3-B1 blocked: prepared snapshot record missing")
            if writes_outbox:
                write_market_snapshot_with_event(conn, snapshot_record)
            else:
                write_market_snapshot_fact_only(conn, snapshot_record)
        else:
            quality_record = prepared.get("quality_record")
            if not isinstance(quality_record, Mapping):
                raise RealtimeSnapshotExecuteError("N3-B1 blocked: prepared quality record missing")
            if writes_outbox:
                write_market_quality_with_event(conn, quality_record, event_type="MarketDataDelayed")
            else:
                write_market_quality_fact_only(conn, quality_record)
        result = dict(prepared.get("object_result") or {})
        if prepared.get("write_kind") != "snapshot" and writes_outbox:
            result.update(event_type="MarketDataDelayed", outbox_rows_written=1)
        results.append(result)
    return results


def execute_subscription_snapshots(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    adapter: Any,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
    connection_factory: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total = len(subscriptions)
    for index, subscription in enumerate(subscriptions, start=1):
        if progress_callback and (index == 1 or index == total or index % max(progress_every, 1) == 0):
            progress_callback(
                f"N3-B1 realtime snapshot progress {index}/{total} "
                f"{subscription.get('asset_kind')} {subscription.get('identity_key')}"
            )
        results.append(
            execute_one_subscription_snapshot(
                dsn=dsn,
                contract=contract,
                subscription=subscription,
                adapter=adapter,
                connection_factory=connection_factory,
            )
        )
    return results


def execute_one_subscription_snapshot(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    subscription: Mapping[str, Any],
    adapter: Any,
    connection_factory: Callable[[str], Any] | None = None,
    snapshot_time: datetime | None = None,
) -> dict[str, Any]:
    adapter_name = adapter_name_for_subscription(contract, subscription)
    event_time = snapshot_time or utc_now()
    connect = connection_factory or open_connection
    writes_outbox = bool(contract.get("writes_outbox"))
    try:
        raw_snapshot = adapter.fetch_snapshot(subscription, str(contract["for_trade_date"]))
    except Exception as exc:  # noqa: BLE001 - adapter failures become quality evidence.
        error_message = f"{type(exc).__name__}: {exc}"
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=event_time,
            status="warning",
            quality_status="failed",
            gate_code="n3_b1_realtime_snapshot_delayed",
            gate_name="realtime snapshot adapter failed or delayed",
            severity="P1",
            expected_value="fresh snapshot row",
            actual_value=error_message,
            error_message=error_message,
        )
        with connect(dsn) as conn:
            write_market_quality_fact_only(conn, quality_record)
        return build_object_result(
            subscription=subscription,
            status="failed",
            quality_status="failed",
            event_type=None,
            snapshot_rows_written=0,
            quality_item_rows_written=1,
            outbox_rows_written=0,
            error_message=error_message,
        )

    if raw_snapshot is None:
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=event_time,
            status="warning",
            quality_status="missing",
            gate_code="n3_b1_realtime_snapshot_missing",
            gate_name="realtime snapshot missing from source adapter",
            severity="P1",
            expected_value="snapshot row",
            actual_value="missing",
            error_message=None,
        )
        with connect(dsn) as conn:
            write_market_quality_fact_only(conn, quality_record)
        return build_object_result(
            subscription=subscription,
            status="missing",
            quality_status="missing",
            event_type=None,
            snapshot_rows_written=0,
            quality_item_rows_written=1,
            outbox_rows_written=0,
            error_message=None,
        )

    identity_route_evidence = build_snapshot_identity_route_evidence(
        subscription=subscription,
        raw_snapshot=raw_snapshot,
    )
    if identity_route_evidence["identity_route_status"] == "identity_route_mismatch":
        error_message = str(
            identity_route_evidence.get("identity_route_status_reason")
            or "raw quote route does not match subscription identity"
        )
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=event_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_identity_route_mismatch",
            gate_name="raw quote identity route must match subscription identity",
            severity="P0",
            expected_value=str(identity_route_evidence.get("expected_route")),
            actual_value=str(identity_route_evidence.get("actual_route")),
            error_message=error_message,
        )
        with connect(dsn) as conn:
            write_market_quality_fact_only(conn, quality_record)
        return build_object_result(
            subscription=subscription,
            status="failed",
            quality_status="failed",
            event_type=None,
            snapshot_rows_written=0,
            quality_item_rows_written=1,
            outbox_rows_written=0,
            error_message=error_message,
            identity_route_evidence=identity_route_evidence,
        )

    source_time_evidence = build_snapshot_source_time_evidence(
        contract=contract,
        raw_snapshot=raw_snapshot,
        default_time=event_time,
        asset_kind=str(subscription.get("asset_kind") or ""),
    )
    if source_time_evidence["source_time_status"] == "source_time_date_mismatch":
        error_message = str(source_time_evidence.get("source_time_status_reason") or "source time date mismatch")
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=event_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_source_time_date_mismatch",
            gate_name="source timestamp must not point to another trade date",
            severity="P0",
            expected_value=str(contract["for_trade_date"]),
            actual_value=str(source_time_evidence.get("source_snapshot_trade_date")),
            error_message=error_message,
        )
        with connect(dsn) as conn:
            write_market_quality_fact_only(conn, quality_record)
        return build_object_result(
            subscription=subscription,
            status="failed",
            quality_status="failed",
            event_type=None,
            snapshot_rows_written=0,
            quality_item_rows_written=1,
            outbox_rows_written=0,
            error_message=error_message,
            source_time_evidence=source_time_evidence,
        )
    if source_time_evidence["source_time_status"] == "source_time_untrusted_label":
        error_message = str(source_time_evidence.get("source_time_status_reason") or "source time is an untrusted label")
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=event_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_source_time_untrusted_label",
            gate_name="raw snapshot time label must not be used as realtime event time",
            severity="P0",
            expected_value="trusted realtime source_time or reviewed observed_at normalization policy",
            actual_value=str(source_time_evidence.get("raw_snapshot_time_label")),
            error_message=error_message,
        )
        with connect(dsn) as conn:
            write_market_quality_fact_only(conn, quality_record)
        return build_object_result(
            subscription=subscription,
            status="failed",
            quality_status="failed",
            event_type=None,
            snapshot_rows_written=0,
            quality_item_rows_written=1,
            outbox_rows_written=0,
            error_message=error_message,
            source_time_evidence=source_time_evidence,
        )
    if source_time_evidence["source_time_status"] == "source_time_future":
        error_message = str(source_time_evidence.get("source_time_status_reason") or "source time is in the future")
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=event_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_source_time_future",
            gate_name="source timestamp must not be later than execution time plus tolerance",
            severity="P0",
            expected_value=str(source_time_evidence.get("source_time_future_max_allowed") or "execution time + tolerance"),
            actual_value=str(source_time_evidence.get("source_snapshot_time")),
            error_message=error_message,
        )
        with connect(dsn) as conn:
            write_market_quality_fact_only(conn, quality_record)
        return build_object_result(
            subscription=subscription,
            status="failed",
            quality_status="failed",
            event_type=None,
            snapshot_rows_written=0,
            quality_item_rows_written=1,
            outbox_rows_written=0,
            error_message=error_message,
            source_time_evidence=source_time_evidence,
        )
    if source_returned_time_status_blocks(source_time_evidence):
        error_message = str(source_time_evidence.get("source_time_status_reason") or "source-returned time invalid")
        quality_record = build_snapshot_quality_record(
            contract=contract,
            subscription=subscription,
            adapter_name=adapter_name,
            adapter=adapter,
            event_time=event_time,
            status="failed",
            quality_status="failed",
            gate_code="n3_b1_source_returned_time_invalid",
            gate_name="source-returned timestamp must be valid before realtime snapshot write",
            severity="P0",
            expected_value="source_time_confirmed, source_time_label_normalized, or source_time_observed_at_fallback",
            actual_value=str(source_time_evidence.get("source_time_status")),
            error_message=error_message,
        )
        with connect(dsn) as conn:
            write_market_quality_fact_only(conn, quality_record)
        return build_object_result(
            subscription=subscription,
            status="failed",
            quality_status="failed",
            event_type=None,
            snapshot_rows_written=0,
            quality_item_rows_written=1,
            outbox_rows_written=0,
            error_message=error_message,
            source_time_evidence=source_time_evidence,
        )

    snapshot_record = build_snapshot_record(
        contract=contract,
        subscription=subscription,
        adapter_name=adapter_name,
        adapter=adapter,
        raw_snapshot=raw_snapshot,
        snapshot_time=source_time_evidence["resolved_snapshot_time"],
        source_time_evidence=source_time_evidence,
        identity_route_evidence=identity_route_evidence,
    )
    with connect(dsn) as conn:
        if writes_outbox:
            write_market_snapshot_with_event(conn, snapshot_record)
        else:
            write_market_snapshot_fact_only(conn, snapshot_record)
    return build_object_result(
        subscription=subscription,
        status="passed",
        quality_status="passed",
        event_type="MarketSnapshotUpdated" if writes_outbox else None,
        snapshot_rows_written=1,
        quality_item_rows_written=0,
        outbox_rows_written=1 if writes_outbox else 0,
        error_message=None,
        source_time_evidence=source_time_evidence,
        identity_route_evidence=identity_route_evidence,
    )


def write_market_snapshot_fact_only(conn: Any, snapshot_record: Mapping[str, Any]) -> dict[str, Any]:
    with conn.transaction():
        with conn.cursor() as cursor:
            snapshot_id = SnapshotRepository(cursor).upsert_snapshot(snapshot_record)
            return {"snapshot_id": snapshot_id}


def write_market_quality_fact_only(conn: Any, quality_record: Mapping[str, Any]) -> dict[str, Any]:
    with conn.transaction():
        with conn.cursor() as cursor:
            quality_item_id = QualityRepository(cursor).insert_quality_item(quality_record)
            return {"quality_item_id": quality_item_id}


def build_snapshot_record(
    *,
    contract: Mapping[str, Any],
    subscription: Mapping[str, Any],
    adapter_name: str,
    adapter: Any,
    raw_snapshot: Mapping[str, Any],
    snapshot_time: datetime,
    source_time_evidence: Mapping[str, Any] | None = None,
    identity_route_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_run_id = str(contract["source_run_id"])
    snapshot_run_id = str(contract["snapshot_run_id"])
    source_version = first_present(raw_snapshot, "source_version") or getattr(adapter, "source_version", "unknown")
    external_source = first_present(raw_snapshot, "external_source") or getattr(adapter, "external_source", "unknown")
    source_path = first_present(raw_snapshot, "source_path")
    source_evidence = dict(source_time_evidence or build_snapshot_source_time_evidence(
        contract=contract,
        raw_snapshot=raw_snapshot,
        default_time=snapshot_time,
        asset_kind=str(subscription.get("asset_kind") or ""),
    ))
    route_evidence = dict(
        identity_route_evidence
        or build_snapshot_identity_route_evidence(subscription=subscription, raw_snapshot=raw_snapshot)
    )
    snapshot_quality_status = "partial" if source_evidence.get("source_time_warning") else "passed"
    return {
        "asset_kind": subscription["asset_kind"],
        "run_id": snapshot_run_id,
        "subscription_id": subscription.get("subscription_id"),
        "pull_plan_id": pull_plan_id_for_subscription(contract, subscription),
        "source_condition_run_id": contract["source_condition_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "trade_date": contract["for_trade_date"],
        "snapshot_time": snapshot_time,
        "identity_key": subscription["identity_key"],
        "exchange": subscription["exchange"],
        "code": subscription["code"],
        "display_code": subscription.get("display_code"),
        "name": subscription.get("name"),
        "open": first_present(raw_snapshot, "open"),
        "high": first_present(raw_snapshot, "high"),
        "low": first_present(raw_snapshot, "low"),
        "close": first_present(raw_snapshot, "close", "price", "current_price"),
        "current_price": first_present(raw_snapshot, "current_price", "price", "close"),
        "pre_close": first_present(raw_snapshot, "pre_close", "last_close", "yesterday_close"),
        "volume": first_present(raw_snapshot, "volume", "vol"),
        "amount": first_present(raw_snapshot, "amount"),
        "source_adapter": adapter_name,
        "source_version": source_version,
        "quality_status": snapshot_quality_status,
        "data_quality_status": snapshot_quality_status,
        "source_scope_ids": subscription.get("source_scope_ids") or [],
        "source_condition_pool_ids": subscription.get("source_condition_pool_ids") or [],
        "raw_json": Jsonb(
            {
                "source_run_id": source_run_id,
                "snapshot_run_id": snapshot_run_id,
                "required_data_kind": REQUIRED_DATA_KIND,
                "external_source": external_source,
                "source_adapter": adapter_name,
                "adapter_name": adapter_name,
                "source_path": source_path,
                "source_version": source_version,
                "identity_route_status": route_evidence.get("identity_route_status"),
                "identity_route_guard_enabled": bool(route_evidence.get("identity_route_guard_enabled")),
                "identity_route_status_reason": route_evidence.get("identity_route_status_reason"),
                "expected_route": json_safe(route_evidence.get("expected_route")),
                "actual_route": json_safe(route_evidence.get("actual_route")),
                "raw_route_market": json_safe(route_evidence.get("raw_market")),
                "raw_route_exchange": route_evidence.get("raw_exchange"),
                "raw_route_code": route_evidence.get("raw_code"),
                "raw_route_asset_kind": route_evidence.get("raw_asset_kind"),
                "source_time_status": source_evidence.get("source_time_status"),
                "source_time_policy": source_evidence.get("source_time_policy"),
                "source_time_missing_or_preopen": bool(source_evidence.get("source_time_missing_or_preopen")),
                "source_time_future": bool(source_evidence.get("source_time_future")),
                "source_time_untrusted_label": bool(source_evidence.get("source_time_untrusted_label")),
                "source_time_label_normalized": bool(source_evidence.get("source_time_label_normalized")),
                "source_time_observed_at_fallback": bool(source_evidence.get("source_time_observed_at_fallback")),
                "source_time_future_guard_enabled": bool(source_evidence.get("source_time_future_guard_enabled")),
                "source_time_future_tolerance_seconds": source_evidence.get("source_time_future_tolerance_seconds"),
                "source_time_future_delta_seconds": source_evidence.get("source_time_future_delta_seconds"),
                "source_time_future_max_allowed": source_evidence.get("source_time_future_max_allowed"),
                "snapshot_time_policy": source_evidence.get("snapshot_time_policy"),
                "source_snapshot_time": source_evidence.get("source_snapshot_time"),
                "source_snapshot_trade_date": source_evidence.get("source_snapshot_trade_date"),
                "source_trade_window_start": source_evidence.get("source_trade_window_start"),
                "source_trade_window_end": source_evidence.get("source_trade_window_end"),
                "raw_snapshot_time_label": source_evidence.get("raw_snapshot_time_label"),
                "raw_snapshot_time_semantics": source_evidence.get("raw_snapshot_time_semantics"),
                "source_time_trust_level": source_evidence.get("source_time_trust_level"),
                "untrusted_source_time_label_handling": source_evidence.get("untrusted_source_time_label_handling"),
                "observed_at": source_evidence.get("observed_at"),
                "fetched_at": source_evidence.get("fetched_at"),
                "trusted_source_timestamp_present": source_evidence.get("trusted_source_timestamp_present"),
                "stock_missing_source_time_policy": source_evidence.get("stock_missing_source_time_policy"),
                "stock_source_time_fallback_reason": source_evidence.get("stock_source_time_fallback_reason"),
                "effective_quote_present": bool(source_evidence.get("effective_quote_present")),
                "source_time_status_reason": source_evidence.get("source_time_status_reason"),
                "raw_payload": json_safe(dict(raw_snapshot)),
            }
        ),
    }


def build_snapshot_source_time_evidence(
    *,
    contract: Mapping[str, Any],
    raw_snapshot: Mapping[str, Any],
    default_time: datetime,
    asset_kind: str | None = None,
) -> dict[str, Any]:
    source_time_policy = contract.get("source_time_policy") or {}
    policy_mode = str(source_time_policy.get("mode") or "strict_live")
    future_guard_enabled = bool(source_time_policy.get("source_time_future_guard_enabled", True))
    future_tolerance_seconds = source_time_future_tolerance_seconds(source_time_policy)
    raw_snapshot_time_label = extract_snapshot_raw_time_label(raw_snapshot)
    raw_snapshot_time_semantics = first_present(raw_snapshot, "raw_snapshot_time_semantics")
    source_time_trust_level = first_present(raw_snapshot, "source_time_trust_level")
    source_time_untrusted_label = snapshot_source_time_is_untrusted_label(raw_snapshot)
    label_handling = str(
        source_time_policy.get("board_source_time_label_handling")
        or source_time_policy.get("untrusted_source_time_label_handling")
        or "P0_BLOCK_NO_OUTBOX"
    )
    normalize_untrusted_label = source_time_label_normalization_allowed(
        policy_mode=policy_mode,
        label_handling=label_handling,
        asset_kind=asset_kind,
        source_time_trust_level=source_time_trust_level,
        raw_snapshot_time_semantics=raw_snapshot_time_semantics,
    )
    observed_at = extract_snapshot_observed_at(raw_snapshot, default_time)
    fetched_at = extract_snapshot_fetched_at(raw_snapshot, observed_at)
    source_time = observed_at if source_time_untrusted_label and normalize_untrusted_label else None
    if not source_time_untrusted_label:
        source_time = extract_snapshot_source_time(raw_snapshot)
    expected_trade_date = str(contract.get("for_trade_date") or "")
    effective_quote_present = snapshot_has_effective_quote(raw_snapshot)
    trusted_source_timestamp_present = bool(source_time and not source_time_untrusted_label)
    source_marker = str(source_marker_from_mapping(raw_snapshot) or "").strip().lower()
    source_marker_is_fake = source_marker in {"fake", "synthetic", "fabricated"}
    stock_observed_at_fallback = False
    stock_source_time_fallback_reason: str | None = None
    stock_missing_source_time_policy = source_time_policy.get("stock_missing_source_time_policy")
    if stock_observed_at_fallback_allowed(
        policy_mode=policy_mode,
        asset_kind=asset_kind,
        source_time=source_time,
        source_time_untrusted_label=source_time_untrusted_label,
        source_time_policy=source_time_policy,
        effective_quote_present=effective_quote_present,
        source_marker_is_fake=source_marker_is_fake,
    ):
        source_time = observed_at
        stock_observed_at_fallback = True
        stock_source_time_fallback_reason = "missing_trusted_source_timestamp"
    resolved_snapshot_time = source_time or default_time
    source_trade_date = source_time.astimezone(ASIA_SHANGHAI).strftime("%Y%m%d") if source_time else None
    comparison_time = ensure_aware_datetime(default_time)
    future_max_allowed = comparison_time + timedelta(seconds=future_tolerance_seconds)
    future_delta_seconds = (
        (source_time.astimezone(timezone.utc) - comparison_time.astimezone(timezone.utc)).total_seconds()
        if source_time
        else None
    )
    source_returned_window: dict[str, Any] | None = None
    source_returned_error: str | None = None
    if policy_mode == SOURCE_RETURNED_TIME_POLICY:
        try:
            if source_marker_is_fake:
                raise N3SourceTimePolicyError("fake_source_time_forbidden")
            if source_time is None:
                raise N3SourceTimePolicyError("missing_source_time")
            source_returned_window = map_source_time_to_trade_window(
                source_time=source_time,
                for_trade_date=expected_trade_date,
            )
        except N3SourceTimePolicyError as exc:
            source_returned_error = str(exc)

    if source_time_untrusted_label and not normalize_untrusted_label:
        status = "source_time_untrusted_label"
        warning = False
        reason = "raw snapshot time is a period label and is not a trusted realtime update timestamp"
    elif policy_mode == SOURCE_RETURNED_TIME_POLICY and source_returned_error:
        status = source_returned_error
        warning = False
        reason = "source-returned timestamp failed N3 source-time policy"
        if status == "source_time_date_mismatch":
            reason = "source timestamp points to a different trade date"
        elif status == "fake_source_time_forbidden":
            reason = "fake/synthetic/fabricated source row is forbidden"
    elif stock_observed_at_fallback:
        status = "source_time_observed_at_fallback"
        warning = True
        reason = "stock quotes() has no trusted source timestamp; observed_at/fetched_at used by reviewed policy"
    elif source_time_untrusted_label and normalize_untrusted_label:
        status = "source_time_label_normalized"
        warning = True
        reason = "raw snapshot time label normalized to observed_at by explicit reviewed policy"
    elif source_time and source_trade_date != expected_trade_date:
        status = "source_time_date_mismatch"
        warning = False
        reason = "source timestamp points to a different trade date"
    elif policy_mode == SOURCE_RETURNED_TIME_POLICY and source_time and source_trade_date == expected_trade_date:
        status = "source_time_confirmed"
        warning = False
        reason = "source-returned timestamp matches for_trade_date"
    elif (
        source_time
        and source_trade_date == expected_trade_date
        and future_guard_enabled
        and source_time.astimezone(timezone.utc) > future_max_allowed.astimezone(timezone.utc)
    ):
        status = "source_time_future"
        warning = False
        reason = (
            "source timestamp is later than execution/current time plus "
            f"{future_tolerance_seconds}s tolerance"
        )
    elif source_time and source_trade_date == expected_trade_date:
        status = "source_time_confirmed"
        warning = False
        reason = "source timestamp matches for_trade_date"
    elif policy_mode == "pre_open_fact_only":
        status = "source_time_missing_or_preopen"
        warning = True
        reason = "source timestamp missing or pre-open zero quote; execution time is used as snapshot_time"
    else:
        status = "source_time_missing"
        warning = False
        reason = "source timestamp missing"

    return {
        "source_time_policy_mode": policy_mode,
        "source_time_status": status,
        "source_time_warning": warning,
        "source_time_missing_or_preopen": status == "source_time_missing_or_preopen",
        "source_time_future": status == "source_time_future",
        "source_time_untrusted_label": status == "source_time_untrusted_label",
        "source_time_label_normalized": status == "source_time_label_normalized",
        "source_time_observed_at_fallback": status == "source_time_observed_at_fallback",
        "source_time_future_guard_enabled": future_guard_enabled,
        "source_time_future_tolerance_seconds": future_tolerance_seconds,
        "source_time_future_delta_seconds": future_delta_seconds,
        "source_time_future_max_allowed": future_max_allowed.astimezone(ASIA_SHANGHAI).isoformat(),
        "source_time_status_reason": reason,
        "source_time_policy": SOURCE_RETURNED_TIME_POLICY if policy_mode == SOURCE_RETURNED_TIME_POLICY else policy_mode,
        "source_snapshot_time": source_time.astimezone(ASIA_SHANGHAI).isoformat() if source_time else None,
        "source_snapshot_trade_date": source_trade_date,
        "source_trade_window_start": source_returned_window["window_start"].isoformat()
        if source_returned_window
        else None,
        "source_trade_window_end": source_returned_window["window_end"].isoformat()
        if source_returned_window
        else None,
        "raw_snapshot_time_label": raw_snapshot_time_label.astimezone(ASIA_SHANGHAI).isoformat()
        if raw_snapshot_time_label
        else None,
        "raw_snapshot_time_semantics": raw_snapshot_time_semantics,
        "source_time_trust_level": source_time_trust_level,
        "untrusted_source_time_label_handling": label_handling,
        "index_board_period_label_policy": source_time_policy.get("index_board_period_label_policy"),
        "index_board_only_normalization": bool(source_time_policy.get("index_board_only_normalization")),
        "trusted_source_timestamp_present": trusted_source_timestamp_present,
        "stock_missing_source_time_policy": stock_missing_source_time_policy,
        "stock_observed_at_fallback": bool(source_time_policy.get("stock_observed_at_fallback")),
        "stock_trusted_source_timestamp_required": bool(
            source_time_policy.get("stock_trusted_source_timestamp_required", True)
        ),
        "stock_source_time_fallback_reason": stock_source_time_fallback_reason,
        "observed_at": observed_at.astimezone(ASIA_SHANGHAI).isoformat(),
        "fetched_at": fetched_at.astimezone(ASIA_SHANGHAI).isoformat(),
        "resolved_snapshot_time": resolved_snapshot_time,
        "snapshot_time_policy": snapshot_time_policy_for_source_status(status, bool(source_time)),
        "effective_quote_present": effective_quote_present,
    }


def source_time_label_normalization_allowed(
    *,
    policy_mode: str,
    label_handling: str,
    asset_kind: str | None,
    source_time_trust_level: Any,
    raw_snapshot_time_semantics: Any,
) -> bool:
    if label_handling != "NORMALIZE_TO_OBSERVED_AT":
        return False
    if policy_mode != SOURCE_RETURNED_TIME_POLICY:
        return True
    if str(asset_kind or "") not in {"index", "board"}:
        return False
    return (
        str(source_time_trust_level or "") == "untrusted_period_label"
        and str(raw_snapshot_time_semantics or "") == "tdx_index_frequency_9_period_label"
    )


def source_returned_time_status_blocks(source_time_evidence: Mapping[str, Any]) -> bool:
    if source_time_evidence.get("source_time_policy_mode") != SOURCE_RETURNED_TIME_POLICY:
        return False
    return str(source_time_evidence.get("source_time_status") or "") not in {
        "source_time_confirmed",
        "source_time_label_normalized",
        "source_time_observed_at_fallback",
    }


def source_time_future_tolerance_seconds(source_time_policy: Mapping[str, Any]) -> int:
    value = source_time_policy.get("future_tolerance_seconds", DEFAULT_SOURCE_TIME_FUTURE_TOLERANCE_SECONDS)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return DEFAULT_SOURCE_TIME_FUTURE_TOLERANCE_SECONDS


def snapshot_time_policy_for_source_status(status: str, has_source_time: bool) -> str:
    if status == "source_time_label_normalized":
        return "observed_at_when_raw_source_time_is_label"
    if status == "source_time_observed_at_fallback":
        return "observed_at_when_stock_quote_has_no_source_time"
    if status == "source_time_untrusted_label":
        return "blocked_raw_source_time_label"
    return "source_time" if has_source_time else "execution_time_when_source_time_missing"


def stock_observed_at_fallback_allowed(
    *,
    policy_mode: str,
    asset_kind: str | None,
    source_time: datetime | None,
    source_time_untrusted_label: bool,
    source_time_policy: Mapping[str, Any],
    effective_quote_present: bool,
    source_marker_is_fake: bool,
) -> bool:
    if policy_mode != SOURCE_RETURNED_TIME_POLICY:
        return False
    if str(asset_kind or "") != "stock":
        return False
    if source_time is not None or source_time_untrusted_label:
        return False
    if not effective_quote_present:
        return False
    if source_marker_is_fake:
        return False
    return (
        bool(source_time_policy.get("stock_observed_at_fallback"))
        and source_time_policy.get("stock_missing_source_time_policy")
        == "observed_at_fallback_when_effective_quote_present"
    )


def build_snapshot_identity_route_evidence(
    *,
    subscription: Mapping[str, Any],
    raw_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    raw_payload = raw_snapshot.get("raw_payload") if isinstance(raw_snapshot.get("raw_payload"), Mapping) else {}
    expected_asset_kind = str(subscription.get("asset_kind") or "")
    expected_exchange = str(subscription.get("exchange") or "").upper()
    expected_code = normalize_route_code(subscription.get("code"))
    raw_market = first_present(raw_snapshot, "market", "tdx_market", "mootdx_market", "raw_route_market")
    if raw_market is None and raw_payload:
        raw_market = first_present(raw_payload, "market", "tdx_market", "mootdx_market", "raw_route_market")
    raw_code = normalize_route_code(first_present(raw_snapshot, "code", "symbol", "ts_code", "raw_route_code"))
    if raw_code is None and raw_payload:
        raw_code = normalize_route_code(first_present(raw_payload, "code", "symbol", "ts_code", "raw_route_code"))
    raw_asset_kind = normalize_route_asset_kind(
        first_present(raw_snapshot, "asset_kind", "asset_type", "security_type", "raw_route_asset_kind")
    )
    if raw_asset_kind is None and raw_payload:
        raw_asset_kind = normalize_route_asset_kind(
            first_present(raw_payload, "asset_kind", "asset_type", "security_type", "raw_route_asset_kind")
        )
    raw_exchange = tdx_market_to_exchange(raw_market)
    expected_market = exchange_to_tdx_market(expected_exchange)
    reasons: list[str] = []

    if raw_code and expected_code and raw_code != expected_code:
        reasons.append(f"raw code {raw_code} != expected code {expected_code}")
    if expected_asset_kind in {"stock", "index"} and raw_market is not None and expected_market is not None:
        if normalize_route_market(raw_market) != expected_market:
            reasons.append(f"raw market {raw_market} maps to {raw_exchange} != expected {expected_exchange}")
    if raw_asset_kind and expected_asset_kind and raw_asset_kind != expected_asset_kind:
        reasons.append(f"raw asset_kind {raw_asset_kind} != expected {expected_asset_kind}")

    status = "identity_route_mismatch" if reasons else "identity_route_confirmed"
    return {
        "identity_route_guard_enabled": True,
        "identity_route_status": status,
        "identity_route_status_reason": "; ".join(reasons) if reasons else "raw quote route matches subscription identity",
        "expected_route": {
            "asset_kind": expected_asset_kind,
            "exchange": expected_exchange,
            "code": expected_code,
            "tdx_market": expected_market,
            "identity_key": subscription.get("identity_key"),
        },
        "actual_route": {
            "asset_kind": raw_asset_kind,
            "exchange": raw_exchange,
            "code": raw_code,
            "tdx_market": normalize_route_market(raw_market),
            "raw_market": raw_market,
        },
        "raw_market": raw_market,
        "raw_exchange": raw_exchange,
        "raw_code": raw_code,
        "raw_asset_kind": raw_asset_kind,
    }


def normalize_route_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    if "." in text:
        text = text.split(".", 1)[0]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def normalize_route_market(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def exchange_to_tdx_market(exchange: str) -> int | None:
    return {"SZ": 0, "SH": 1}.get(exchange.upper())


def tdx_market_to_exchange(value: Any) -> str | None:
    market = normalize_route_market(value)
    return {0: "SZ", 1: "SH"}.get(market)


def normalize_route_asset_kind(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    aliases = {
        "stock": "stock",
        "equity": "stock",
        "a_stock": "stock",
        "index": "index",
        "idx": "index",
        "board": "board",
        "sector": "board",
    }
    return aliases.get(text)


def ensure_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ASIA_SHANGHAI)
    return value


def snapshot_source_time_is_untrusted_label(raw_snapshot: Mapping[str, Any]) -> bool:
    trust_level = str(first_present(raw_snapshot, "source_time_trust_level") or "")
    semantics = str(first_present(raw_snapshot, "raw_snapshot_time_semantics") or "")
    return trust_level in {"untrusted_period_label", "period_label"} or semantics.endswith("_period_label")


def extract_snapshot_raw_time_label(raw_snapshot: Mapping[str, Any]) -> datetime | None:
    parsed = parse_datetime_like(first_present(raw_snapshot, "raw_snapshot_time_label", "raw_snapshot_time"))
    if parsed is not None:
        return parsed
    raw_payload = raw_snapshot.get("raw_payload") if isinstance(raw_snapshot.get("raw_payload"), Mapping) else {}
    return parse_tdx_record_datetime(raw_payload) if raw_payload else None


def extract_snapshot_observed_at(raw_snapshot: Mapping[str, Any], default_time: datetime) -> datetime:
    parsed = parse_datetime_like(first_present(raw_snapshot, "observed_at", "fetched_at"))
    return parsed or ensure_aware_datetime(default_time)


def extract_snapshot_fetched_at(raw_snapshot: Mapping[str, Any], observed_at: datetime) -> datetime:
    parsed = parse_datetime_like(first_present(raw_snapshot, "fetched_at", "observed_at"))
    return parsed or observed_at


def extract_snapshot_source_time(raw_snapshot: Mapping[str, Any]) -> datetime | None:
    parsed = parse_datetime_like(first_present(raw_snapshot, "snapshot_time", "snapshot_datetime", "datetime"))
    if parsed is not None:
        return parsed
    raw_payload = raw_snapshot.get("raw_payload") if isinstance(raw_snapshot.get("raw_payload"), Mapping) else {}
    parsed = parse_datetime_like(first_present(raw_payload, "snapshot_time", "snapshot_datetime", "datetime", "time"))
    if parsed is not None:
        return parsed
    return parse_tdx_record_datetime(raw_payload) if raw_payload else None


def snapshot_has_effective_quote(raw_snapshot: Mapping[str, Any]) -> bool:
    raw_payload = raw_snapshot.get("raw_payload") if isinstance(raw_snapshot.get("raw_payload"), Mapping) else {}
    values = [
        first_present(raw_snapshot, "current_price", "price", "close"),
        first_present(raw_snapshot, "open"),
        first_present(raw_snapshot, "high"),
        first_present(raw_snapshot, "low"),
        first_present(raw_snapshot, "volume", "vol"),
        first_present(raw_snapshot, "amount"),
        first_present(raw_payload, "price", "open", "high", "low", "volume", "vol", "amount"),
    ]
    return any(is_positive_number(value) for value in values)


def is_positive_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def build_snapshot_quality_record(
    *,
    contract: Mapping[str, Any],
    subscription: Mapping[str, Any],
    adapter_name: str,
    adapter: Any,
    event_time: datetime,
    status: str,
    quality_status: str,
    gate_code: str,
    gate_name: str,
    severity: str,
    expected_value: str,
    actual_value: str,
    error_message: str | None,
) -> dict[str, Any]:
    snapshot_run_id = str(contract["snapshot_run_id"])
    return {
        "run_id": snapshot_run_id,
        "subscription_id": subscription.get("subscription_id"),
        "pull_plan_id": pull_plan_id_for_subscription(contract, subscription),
        "source_condition_run_id": contract["source_condition_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "source_trade_date": contract["source_trade_date"],
        "data_domain": subscription["asset_kind"],
        "asset_kind": subscription["asset_kind"],
        "identity_key": subscription["identity_key"],
        "layer_scope": "market_data_run",
        "table_name": REALTIME_SNAPSHOT_TABLES[str(subscription["asset_kind"])],
        "gate_code": gate_code,
        "gate_name": gate_name,
        "severity": severity,
        "status": status,
        "expected_value": expected_value,
        "actual_value": actual_value,
        "details": Jsonb(
            {
                "source_run_id": contract["source_run_id"],
                "snapshot_run_id": snapshot_run_id,
                "subscription_id": subscription.get("subscription_id"),
                "identity_key": subscription.get("identity_key"),
                "error_message": error_message,
                "external_source": getattr(adapter, "external_source", "unknown"),
            }
        ),
        "event_time": event_time,
        "required_data_kind": REQUIRED_DATA_KIND,
        "status_kind": quality_status,
        "source_adapter": adapter_name,
        "quality_status": quality_status,
        "data_quality_status": quality_status,
    }


def adapter_name_for_subscription(contract: Mapping[str, Any], subscription: Mapping[str, Any]) -> str:
    asset_kind = str(subscription.get("asset_kind") or "")
    for row in contract.get("source_adapter_plan") or []:
        if row.get("asset_kind") == asset_kind:
            return str(row.get("adapter_name") or ADAPTER_NAMES[asset_kind])
    return ADAPTER_NAMES[asset_kind]


def pull_plan_id_for_subscription(contract: Mapping[str, Any], subscription: Mapping[str, Any]) -> Any:
    asset_kind = str(subscription.get("asset_kind") or "")
    for row in contract.get("source_adapter_plan") or []:
        if row.get("asset_kind") == asset_kind:
            return row.get("source_pull_plan_id")
    return None


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
        raise RealtimeSnapshotExecuteError(
            "N3-B1 blocked: subscription counts do not match contract: " + "; ".join(mismatches)
        )


def open_connection(dsn: str) -> Any:
    return audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row)


def fetch_market_data_run_row_by_id(dsn: str, run_id: str) -> dict[str, Any]:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        row = fetch_market_data_run_row(cur, run_id)
    if row is None:
        raise RealtimeSnapshotExecuteError(f"N3-B1 blocked: market_data_run missing: {run_id}")
    return row


def insert_snapshot_run(
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
                _insert_snapshot_run_with_cursor(
                    cur,
                    contract=contract,
                    source_run_row=source_run_row,
                    started_at=started_at,
                    batch_attempt=batch_attempt,
                )


def _insert_snapshot_run_with_cursor(
    cur: Any,
    *,
    contract: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    batch_attempt: Mapping[str, Any] | None,
) -> None:
    expected_counts = contract.get("expected_asset_counts") or {}
    subscription_count = sum(int((expected_counts.get(asset) or {}).get("subscription_count") or 0) for asset in ASSET_KINDS)
    object_count = sum(int((expected_counts.get(asset) or {}).get("object_count") or 0) for asset in ASSET_KINDS)
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
                            %s, %s, %s, %s, %s, 'N3-B1-realtime-snapshot-execute',
                            false, false, false, false, %s, %s)
                    """,
                    (
                        contract["snapshot_run_id"],
                        contract["source_condition_run_id"],
                        contract["for_trade_date"],
                        contract["source_trade_date"],
                        contract["prev_trade_date"],
                        int(source_run_row.get("source_scope_row_count") or 0),
                        int(source_run_row.get("candidate_row_count") or 0),
                        subscription_count,
                        object_count,
                        source_run_row.get("dedup_ratio"),
                        started_at,
                        Jsonb(
                            {
                                "stage": "N3-B1",
                                "source_run_id": contract["source_run_id"],
                                "snapshot_run_id": contract["snapshot_run_id"],
                                "writes_outbox": bool(contract.get("writes_outbox")),
                                "mootdx_batch_attempt": dict(batch_attempt) if batch_attempt else None,
                            }
                        ),
                    ),
    )


def write_failed_snapshot_attempt_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    prepared_snapshots: Sequence[Mapping[str, Any]],
    outcome: MootdxBatchAttemptOutcome[Any],
    connection_factory: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    connect = connection_factory or open_connection
    provenance = outcome.to_provenance()
    with connect(dsn) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _insert_snapshot_run_with_cursor(
                    cur,
                    contract=contract,
                    source_run_row=source_run_row,
                    started_at=started_at,
                    batch_attempt=provenance,
                )
            results: list[dict[str, Any]] = []
            for prepared in prepared_snapshots:
                quality_record = prepared.get("quality_record")
                if not isinstance(quality_record, Mapping):
                    raise RealtimeSnapshotExecuteError("endpoint failure quality record missing")
                if bool(contract.get("writes_outbox")):
                    write_market_quality_with_event(
                        conn,
                        quality_record,
                        event_type="MarketDataDelayed",
                    )
                else:
                    write_market_quality_fact_only(conn, quality_record)
                result = dict(prepared.get("object_result") or {})
                if bool(contract.get("writes_outbox")):
                    result.update(event_type="MarketDataDelayed", outbox_rows_written=1)
                results.append(result)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status = 'failed',
                        p0_count = 0,
                        p1_count = %s,
                        p2_count = 0,
                        market_data_pulled = true,
                        market_data_fact_written = false,
                        downstream_layers_touched = false,
                        worker_started = false,
                        finished_at = now(),
                        updated_at = now(),
                        raw_json = %s
                    WHERE run_id = %s
                    """,
                    (
                        len(results),
                        Jsonb({
                            "stage": "N3-B1",
                            "source_run_id": contract["source_run_id"],
                            "snapshot_run_id": contract["snapshot_run_id"],
                            "writes_outbox": bool(contract.get("writes_outbox")),
                            "mootdx_batch_attempt": provenance,
                            "endpoint_failure": True,
                            "success_event_rows_written": 0,
                        }),
                        contract["snapshot_run_id"],
                    ),
                )
    return results


def commit_snapshot_attempt_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    prepared_snapshots: Sequence[Mapping[str, Any]],
    outcome: MootdxBatchAttemptOutcome[Any],
    connection_factory: Callable[[str], Any] | None = None,
    data_snapshot_builder: Callable[[Any], Mapping[str, Any]] | None = None,
    finalizer: Callable[..., None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    connect = connection_factory or open_connection
    provenance = outcome.to_provenance()
    with connect(dsn) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _insert_snapshot_run_with_cursor(
                    cur,
                    contract=contract,
                    source_run_row=source_run_row,
                    started_at=started_at,
                    batch_attempt=provenance,
                )
            object_results = _write_prepared_subscription_snapshots_on_connection(
                conn,
                contract=contract,
                prepared_snapshots=prepared_snapshots,
            )
            with conn.cursor() as cur:
                data_snapshot = dict(
                    data_snapshot_builder(cur)
                    if data_snapshot_builder is not None
                    else _capture_snapshot_execute_backup_with_cursor(
                        cur,
                        phase="after_n3_b1_data_before_quality",
                        snapshot_run_id=str(contract["snapshot_run_id"]),
                        source_run_id=str(contract["source_run_id"]),
                        for_trade_date=str(contract["for_trade_date"]),
                    )
                )
                post_checks = build_post_execute_checks(
                    contract=contract,
                    data_snapshot=data_snapshot,
                    object_results=object_results,
                )
                quality_items = build_post_execute_quality_items(
                    contract=contract,
                    post_checks=post_checks,
                    object_results=object_results,
                )
                quality_counts = count_quality_severities(quality_items)
                (finalizer or _finalize_snapshot_run_with_cursor)(
                    cur,
                    contract=contract,
                    quality_items=quality_items,
                    object_results=object_results,
                    status="passed" if quality_counts["P0"] == 0 else "failed",
                    batch_attempt=provenance,
                )
    return object_results, data_snapshot, post_checks, quality_items


def write_snapshot_quality_and_finalize_run(
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
                _finalize_snapshot_run_with_cursor(
                    cur,
                    contract=contract,
                    quality_items=quality_items,
                    object_results=object_results,
                    status=status,
                    batch_attempt=batch_attempt,
                )


def _finalize_snapshot_run_with_cursor(
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
                        any(int(row.get("snapshot_rows_written") or 0) > 0 for row in object_results),
                        Jsonb(
                            {
                                "stage": "N3-B1",
                                "source_run_id": contract["source_run_id"],
                                "snapshot_run_id": contract["snapshot_run_id"],
                                "writes_outbox": bool(contract.get("writes_outbox")),
                                "write_result": summarize_write_result(object_results, quality_items),
                                "actual_asset_counts": summarize_actual_asset_counts(object_results),
                                "mootdx_batch_attempt": dict(batch_attempt) if batch_attempt else None,
                            }
                        ),
                        contract["snapshot_run_id"],
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
                contract["snapshot_run_id"],
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


def capture_snapshot_execute_backup(
    dsn: str,
    *,
    phase: str,
    snapshot_run_id: str,
    source_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return _capture_snapshot_execute_backup_with_cursor(
            cur,
            phase=phase,
            snapshot_run_id=snapshot_run_id,
            source_run_id=source_run_id,
            for_trade_date=for_trade_date,
        )


def _capture_snapshot_execute_backup_with_cursor(
    cur: Any,
    *,
    phase: str,
    snapshot_run_id: str,
    source_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "captured_at": utc_now_iso(),
        "source_run_id": source_run_id,
        "snapshot_run_id": snapshot_run_id,
        "for_trade_date": for_trade_date,
        "active_snapshot": fetch_n1_n2_active_snapshot(cur),
        "snapshot_run_exists": market_data_run_exists(cur, snapshot_run_id),
        "snapshot_run_row": fetch_market_data_run_row(cur, snapshot_run_id),
        "source_run_row": fetch_market_data_run_row(cur, source_run_id),
        "target_table_row_counts": fetch_table_row_counts(cur, REALTIME_SNAPSHOT_TABLES.values()),
        "target_snapshot_run_row_counts": fetch_snapshot_run_row_counts(cur, snapshot_run_id, for_trade_date),
        "target_snapshot_run_counts_by_asset": fetch_snapshot_run_counts_by_asset(cur, snapshot_run_id, for_trade_date),
        "duplicate_snapshot_key_count_by_asset": fetch_duplicate_snapshot_key_counts(cur, snapshot_run_id, for_trade_date),
        "physical_isolation_violation_count_by_asset": fetch_physical_isolation_violation_counts(cur, snapshot_run_id),
        "snapshot_outbox_row_count": fetch_snapshot_outbox_count(cur, snapshot_run_id),
        "snapshot_outbox_counts_by_type": fetch_snapshot_outbox_counts_by_type(cur, snapshot_run_id),
        "downstream_inbox_row_count": fetch_downstream_inbox_count(cur, snapshot_run_id),
        "checkpoint_ref_count": fetch_checkpoint_ref_count(cur, snapshot_run_id),
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


def fetch_snapshot_run_row_counts(cur: Any, snapshot_run_id: str, for_trade_date: str) -> dict[str, int]:
    counts = {}
    for table_name in (*REALTIME_SNAPSHOT_TABLES.values(), "common_market_data_quality_item", "common_market_data_run"):
        cur.execute(
            f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE run_id = %s",
            (snapshot_run_id,),
        )
        counts[table_name] = int(cur.fetchone()["row_count"])
    counts["common_event_outbox"] = fetch_snapshot_outbox_count(cur, snapshot_run_id)
    counts["for_trade_date_marker"] = 1 if for_trade_date else 0
    return counts


def fetch_snapshot_run_counts_by_asset(cur: Any, snapshot_run_id: str, for_trade_date: str) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for asset_kind in ASSET_KINDS:
        table_name, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["snapshot"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count,
                   count(DISTINCT {identity_column})::bigint AS object_count
            FROM {table_name}
            WHERE run_id = %s AND for_trade_date = %s
            """,
            (snapshot_run_id, for_trade_date),
        )
        row = cur.fetchone()
        output[asset_kind] = {
            "snapshot_row_count": int(row["row_count"]),
            "snapshot_object_count": int(row["object_count"]),
        }
    return output


def fetch_duplicate_snapshot_key_counts(cur: Any, snapshot_run_id: str, for_trade_date: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        table_name, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["snapshot"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS duplicate_group_count
            FROM (
              SELECT run_id, trade_date, {identity_column}, snapshot_time, source_adapter, count(*) AS row_count
              FROM {table_name}
              WHERE run_id = %s AND for_trade_date = %s
              GROUP BY run_id, trade_date, {identity_column}, snapshot_time, source_adapter
              HAVING count(*) > 1
            ) duplicates
            """,
            (snapshot_run_id, for_trade_date),
        )
        output[asset_kind] = int(cur.fetchone()["duplicate_group_count"])
    return output


def fetch_physical_isolation_violation_counts(cur: Any, snapshot_run_id: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        table_name, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["snapshot"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS violation_count
            FROM {table_name}
            WHERE run_id = %s AND {identity_column} NOT LIKE %s
            """,
            (snapshot_run_id, f"{asset_kind}:%"),
        )
        output[asset_kind] = int(cur.fetchone()["violation_count"])
    return output


def fetch_snapshot_outbox_count(cur: Any, snapshot_run_id: str) -> int:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_event_outbox
        WHERE source_layer = 'N3_market_data'
          AND source_run_id = %s
        """,
        (snapshot_run_id,),
    )
    return int(cur.fetchone()["row_count"])


def fetch_snapshot_outbox_counts_by_type(cur: Any, snapshot_run_id: str) -> dict[str, int]:
    cur.execute(
        """
        SELECT event_type, count(*)::bigint AS row_count
        FROM common_event_outbox
        WHERE source_layer = 'N3_market_data'
          AND source_run_id = %s
        GROUP BY event_type
        ORDER BY event_type
        """,
        (snapshot_run_id,),
    )
    return {str(row["event_type"]): int(row["row_count"]) for row in cur.fetchall()}


def fetch_downstream_inbox_count(cur: Any, snapshot_run_id: str) -> int:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_event_inbox
        WHERE source_layer = 'N3_market_data'
          AND source_run_id = %s
        """,
        (snapshot_run_id,),
    )
    return int(cur.fetchone()["row_count"])


def fetch_checkpoint_ref_count(cur: Any, snapshot_run_id: str) -> int:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_event_consumer_checkpoint
        WHERE checkpoint_payload::TEXT LIKE %s
        """,
        (f"%{snapshot_run_id}%",),
    )
    return int(cur.fetchone()["row_count"])


def build_post_execute_checks(
    *,
    contract: Mapping[str, Any],
    data_snapshot: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_counts = contract.get("expected_asset_counts") or {}
    counts_by_asset = data_snapshot.get("target_snapshot_run_counts_by_asset") or {}
    actual_counts = {
        asset_kind: int((counts_by_asset.get(asset_kind) or {}).get("snapshot_object_count") or 0)
        for asset_kind in ASSET_KINDS
    }
    expected_object_counts = {
        asset_kind: int((expected_counts.get(asset_kind) or {}).get("object_count") or 0)
        for asset_kind in ASSET_KINDS
    }
    actual_rows = {
        asset_kind: int((counts_by_asset.get(asset_kind) or {}).get("snapshot_row_count") or 0)
        for asset_kind in ASSET_KINDS
    }
    successful_count = sum(1 for row in object_results if row.get("status") == "passed")
    writes_outbox = bool(contract.get("writes_outbox"))
    outbox_counts = data_snapshot.get("snapshot_outbox_counts_by_type") or {}
    scoped_outbox_count = int(data_snapshot.get("snapshot_outbox_row_count") or 0)
    scoped_inbox_count = int(data_snapshot.get("downstream_inbox_row_count") or 0)
    scoped_checkpoint_count = int(data_snapshot.get("checkpoint_ref_count") or 0)
    duplicate_counts = data_snapshot.get("duplicate_snapshot_key_count_by_asset") or {}
    isolation_counts = data_snapshot.get("physical_isolation_violation_count_by_asset") or {}
    return {
        "n3_b1_snapshot_object_count_matches_b0": actual_counts == expected_object_counts,
        "n3_b1_expected_snapshot_object_counts": expected_object_counts,
        "n3_b1_actual_snapshot_object_counts": actual_counts,
        "n3_b1_snapshot_rows_reasonable": all(0 <= actual_rows[asset_kind] <= expected_object_counts[asset_kind] for asset_kind in ASSET_KINDS),
        "n3_b1_actual_snapshot_rows_by_asset": actual_rows,
        "n3_b1_market_snapshot_outbox_matches_successful_facts": (
            int(outbox_counts.get("MarketSnapshotUpdated") or 0) == successful_count if writes_outbox else True
        ),
        "n3_b1_no_non_snapshot_outbox_events": (
            set(outbox_counts).issubset({"MarketSnapshotUpdated"}) if writes_outbox else True
        ),
        "n3_b1_writes_outbox_false": (not writes_outbox and scoped_outbox_count == 0) or writes_outbox,
        "n3_b1_outbox_counts_by_type": dict(outbox_counts),
        "n3_b1_scoped_event_refs_zero": scoped_outbox_count == 0 and scoped_inbox_count == 0 and scoped_checkpoint_count == 0,
        "n3_b1_scoped_event_refs": {
            "common_event_outbox": scoped_outbox_count,
            "common_event_inbox": scoped_inbox_count,
            "common_event_consumer_checkpoint": scoped_checkpoint_count,
        },
        "n3_b1_duplicate_snapshot_key_zero": all(int(count or 0) == 0 for count in duplicate_counts.values()),
        "n3_b1_duplicate_snapshot_key_count_by_asset": dict(duplicate_counts),
        "n3_b1_physical_table_isolation": all(int(count or 0) == 0 for count in isolation_counts.values()),
        "n3_b1_physical_isolation_violation_count_by_asset": dict(isolation_counts),
        "n3_b1_no_downstream_consumption_before_rollback": scoped_inbox_count == 0 and scoped_checkpoint_count == 0,
    }


def build_post_execute_quality_items(
    *,
    contract: Mapping[str, Any],
    post_checks: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    issue_results = [row for row in object_results if row.get("status") in {"missing", "failed"}]
    source_time_warning_results = [row for row in object_results if row.get("source_time_warning")]
    source_time_mismatch_results = [
        row for row in object_results if row.get("source_time_status") == "source_time_date_mismatch"
    ]
    contract_p1 = int((contract.get("quality") or {}).get("p1_count") or 0)
    writes_outbox = bool(contract.get("writes_outbox"))
    items = [
        quality_item(
            "P0",
            "passed" if post_checks["n3_b1_snapshot_object_count_matches_b0"] else "failed",
            "n3_b1_snapshot_object_count_matches_b0",
            "stock/index/board snapshot object_count must match B0 expected asset counts",
            expected=json.dumps(post_checks["n3_b1_expected_snapshot_object_counts"], ensure_ascii=False, sort_keys=True),
            actual=json.dumps(post_checks["n3_b1_actual_snapshot_object_counts"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_b1_snapshot_rows_reasonable"] else "failed",
            "n3_b1_snapshot_rows_reasonable",
            "actual snapshot rows must be between zero and expected snapshot rows",
            expected="0 <= actual <= expected",
            actual=json.dumps(post_checks["n3_b1_actual_snapshot_rows_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        *(
            [
                quality_item(
                    "P0",
                    "passed" if post_checks["n3_b1_market_snapshot_outbox_matches_successful_facts"] else "failed",
                    "n3_b1_market_snapshot_outbox_matches_successful_facts",
                    "successful snapshot fact writes must have same-transaction MarketSnapshotUpdated outbox rows",
                    expected="one MarketSnapshotUpdated per passed object",
                    actual=json.dumps(post_checks["n3_b1_outbox_counts_by_type"], ensure_ascii=False, sort_keys=True),
                ),
                quality_item(
                    "P0",
                    "passed" if post_checks["n3_b1_no_non_snapshot_outbox_events"] else "failed",
                    "n3_b1_no_non_snapshot_outbox_events",
                    "standard B1 outbox execute must not emit non-snapshot outbox events",
                    expected="only MarketSnapshotUpdated outbox rows",
                    actual=json.dumps(post_checks["n3_b1_outbox_counts_by_type"], ensure_ascii=False, sort_keys=True),
                ),
            ]
            if writes_outbox
            else [
                quality_item(
                    "P0",
                    "passed" if post_checks["n3_b1_writes_outbox_false"] else "failed",
                    "n3_b1_writes_outbox_false",
                    "fact-only B1 must not write common_event_outbox",
                    expected="0 scoped outbox rows",
                    actual=json.dumps(post_checks["n3_b1_scoped_event_refs"], ensure_ascii=False, sort_keys=True),
                ),
                quality_item(
                    "P0",
                    "passed" if post_checks["n3_b1_scoped_event_refs_zero"] else "failed",
                    "n3_b1_scoped_event_refs_zero",
                    "fact-only B1 must leave outbox/inbox/checkpoint scoped refs at zero",
                    expected="0 scoped event refs",
                    actual=json.dumps(post_checks["n3_b1_scoped_event_refs"], ensure_ascii=False, sort_keys=True),
                ),
            ]
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_b1_duplicate_snapshot_key_zero"] else "failed",
            "n3_b1_duplicate_snapshot_key_zero",
            "duplicate snapshot key count must be zero in each physical table",
            expected="0",
            actual=json.dumps(post_checks["n3_b1_duplicate_snapshot_key_count_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_b1_physical_table_isolation"] else "failed",
            "n3_b1_physical_table_isolation",
            "identity_key prefix must match the physical snapshot table family",
            expected="0",
            actual=json.dumps(post_checks["n3_b1_physical_isolation_violation_count_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_b1_no_downstream_consumption_before_rollback"] else "failed",
            "n3_b1_no_downstream_consumption_before_rollback",
            "rollback is only safe before outbox rows are delivered or consumed downstream",
            expected="0 downstream inbox rows",
            actual="0" if post_checks["n3_b1_no_downstream_consumption_before_rollback"] else "non-zero",
        ),
        quality_item(
            "P1",
            "warning" if contract_p1 > 0 else "passed",
            "n3_b1_contract_p1_carried",
            "N3-B1 carries non-blocking P1 items from the reviewed execute contract",
            expected="0",
            actual=str(contract_p1),
        ),
        quality_item(
            "P0" if writes_outbox else "P1",
            "failed" if writes_outbox and issue_results else ("warning" if issue_results else "passed"),
            "n3_b1_missing_or_delayed_objects_recorded",
            "source issue objects must not pass silently; standard outbox runs fail instead of emitting non-snapshot events",
            expected="0",
            actual=str(len(issue_results)),
            details={"samples": [summarize_object_result(row) for row in issue_results[:20]]},
        ),
        quality_item(
            "P0",
            "failed" if source_time_mismatch_results else "passed",
            "n3_b1_source_time_date_mismatch_zero",
            "explicit source timestamp must not point to a different trade date",
            expected="0",
            actual=str(len(source_time_mismatch_results)),
            details={"samples": [summarize_object_result(row) for row in source_time_mismatch_results[:20]]},
        ),
        quality_item(
            "P1",
            "warning" if source_time_warning_results else "passed",
            "n3_b1_pre_open_source_time_not_confirmed",
            "pre-open fact-only snapshots with missing source time or zero quote must be recorded as non-live source-time warnings",
            expected="0",
            actual=str(len(source_time_warning_results)),
            details={
                "source_time_status_counts": dict(
                    Counter(str(row.get("source_time_status") or "") for row in source_time_warning_results)
                ),
                "samples": [summarize_object_result(row) for row in source_time_warning_results[:20]],
            },
        ),
    ]
    for item in items:
        item.setdefault("details", {})
        item["details"] = {
            **(item.get("details") or {}),
            "source_run_id": contract["source_run_id"],
            "snapshot_run_id": contract["snapshot_run_id"],
        }
    return items


def build_object_result(
    *,
    subscription: Mapping[str, Any],
    status: str,
    quality_status: str,
    event_type: str | None,
    snapshot_rows_written: int,
    quality_item_rows_written: int,
    outbox_rows_written: int,
    error_message: str | None,
    source_time_evidence: Mapping[str, Any] | None = None,
    identity_route_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_evidence = dict(source_time_evidence or {})
    route_evidence = dict(identity_route_evidence or {})
    return {
        "asset_kind": subscription.get("asset_kind"),
        "identity_key": subscription.get("identity_key"),
        "subscription_id": subscription.get("subscription_id"),
        "status": status,
        "quality_status": quality_status,
        "identity_route_status": route_evidence.get("identity_route_status"),
        "identity_route_guard_enabled": bool(route_evidence.get("identity_route_guard_enabled")),
        "identity_route_status_reason": route_evidence.get("identity_route_status_reason"),
        "raw_route_market": route_evidence.get("raw_market"),
        "raw_route_exchange": route_evidence.get("raw_exchange"),
        "raw_route_code": route_evidence.get("raw_code"),
        "raw_route_asset_kind": route_evidence.get("raw_asset_kind"),
        "source_time_status": source_evidence.get("source_time_status"),
        "source_time_missing_or_preopen": bool(source_evidence.get("source_time_missing_or_preopen")),
        "source_time_future": bool(source_evidence.get("source_time_future")),
        "source_time_untrusted_label": bool(source_evidence.get("source_time_untrusted_label")),
        "source_time_label_normalized": bool(source_evidence.get("source_time_label_normalized")),
        "source_time_warning": bool(source_evidence.get("source_time_warning")),
        "source_snapshot_trade_date": source_evidence.get("source_snapshot_trade_date"),
        "raw_snapshot_time_label": source_evidence.get("raw_snapshot_time_label"),
        "raw_snapshot_time_semantics": source_evidence.get("raw_snapshot_time_semantics"),
        "source_time_trust_level": source_evidence.get("source_time_trust_level"),
        "observed_at": source_evidence.get("observed_at"),
        "fetched_at": source_evidence.get("fetched_at"),
        "effective_quote_present": source_evidence.get("effective_quote_present"),
        "event_type": event_type,
        "snapshot_rows_written": snapshot_rows_written,
        "quality_item_rows_written": quality_item_rows_written,
        "outbox_rows_written": outbox_rows_written,
        "error_message": error_message,
    }


def summarize_object_result(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "asset_kind": row.get("asset_kind"),
        "identity_key": row.get("identity_key"),
        "subscription_id": row.get("subscription_id"),
        "status": row.get("status"),
        "identity_route_status": row.get("identity_route_status"),
        "identity_route_status_reason": row.get("identity_route_status_reason"),
        "raw_route_market": row.get("raw_route_market"),
        "raw_route_exchange": row.get("raw_route_exchange"),
        "raw_route_code": row.get("raw_route_code"),
        "source_time_status": row.get("source_time_status"),
        "event_type": row.get("event_type"),
        "error_message": row.get("error_message"),
    }


def summarize_actual_asset_counts(object_results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for asset_kind in ASSET_KINDS:
        rows = [row for row in object_results if row.get("asset_kind") == asset_kind]
        output[asset_kind] = {
            "object_count": len(rows),
            "passed": sum(1 for row in rows if row.get("status") == "passed"),
            "missing": sum(1 for row in rows if row.get("status") == "missing"),
            "failed": sum(1 for row in rows if row.get("status") == "failed"),
            "snapshot_rows_written": sum(int(row.get("snapshot_rows_written") or 0) for row in rows),
            "quality_item_rows_written": sum(int(row.get("quality_item_rows_written") or 0) for row in rows),
            "outbox_rows_written": sum(int(row.get("outbox_rows_written") or 0) for row in rows),
        }
    return output


def summarize_write_result(
    object_results: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "objects_processed": len(object_results),
        "snapshot_rows_written": sum(int(row.get("snapshot_rows_written") or 0) for row in object_results),
        "quality_item_rows_written": sum(int(row.get("quality_item_rows_written") or 0) for row in object_results)
        + len(quality_items),
        "event_outbox_rows_written": sum(int(row.get("outbox_rows_written") or 0) for row in object_results),
        "status_counts": dict(Counter(str(row.get("status") or "") for row in object_results)),
    }


def normalize_snapshot_records(frame: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in frame_to_records(frame):
        rows.append(
            {
                "open": first_present(record, "open"),
                "high": first_present(record, "high"),
                "low": first_present(record, "low"),
                "close": first_present(record, "close", "price"),
                "current_price": first_present(record, "current_price", "price", "close"),
                "pre_close": first_present(record, "pre_close", "last_close", "yesterday_close"),
                "volume": first_present(record, "volume", "vol"),
                "amount": first_present(record, "amount"),
                "raw_payload": dict(record),
            }
        )
    return rows


def resolve_snapshot_time(raw_snapshot: Mapping[str, Any], default_time: datetime) -> datetime:
    value = first_present(raw_snapshot, "snapshot_time", "snapshot_datetime", "datetime")
    parsed = parse_datetime_like(value)
    return parsed or default_time


def parse_tdx_record_datetime(record: Mapping[str, Any]) -> datetime | None:
    parsed = parse_datetime_like(first_present(record, "datetime", "snapshot_time", "time"))
    if parsed is not None:
        return parsed

    year = first_present(record, "year")
    month = first_present(record, "month")
    day = first_present(record, "day")
    if year is None or month is None or day is None:
        return None
    hour = first_present(record, "hour") or 15
    minute = first_present(record, "minute") or 0
    try:
        return datetime(int(year), int(month), int(day), int(hour), int(minute), tzinfo=ASIA_SHANGHAI)
    except (TypeError, ValueError):
        return None


def parse_datetime_like(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ASIA_SHANGHAI)
    return parsed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_safe(value), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, Jsonb):
        return json_safe(value.obj)
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def format_realtime_snapshot_execute_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    write = report["write_result"]
    lines = [
        "# N3-B1 Realtime Daily Snapshot Execute Report",
        "",
        "## Summary",
        "",
        f"- stage: `{report['stage']}`",
        f"- layer_role: `{report['layer_role']}`",
        f"- source_run_id: `{report['source_run_id']}`",
        f"- snapshot_run_id: `{report['snapshot_run_id']}`",
        f"- for_trade_date: `{report['for_trade_date']}`",
        f"- objects_processed: `{write['objects_processed']}`",
        f"- snapshot_rows_written: `{write['snapshot_rows_written']}`",
        f"- quality_item_rows_written: `{write['quality_item_rows_written']}`",
        f"- event_outbox_rows_written: `{write['event_outbox_rows_written']}`",
        f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
        "",
        "## Boundary",
        "",
    ]
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.append("")
    return "\n".join(lines)
