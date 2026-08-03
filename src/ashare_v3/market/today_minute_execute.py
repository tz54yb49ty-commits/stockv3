"""N3-C1 today 1 minute bar run-once executor.

This module is intentionally limited to N3 market-data responsibilities:
validate a passed N3-C0 dry-run plan, fetch today's already closed 1m bars
through a bounded run-once adapter, and write only stock/index/board minute
facts plus run/quality metadata. It does not write common_event_outbox, consume
events, start workers, or enter downstream layers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
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
from ashare_v3.market.minute_label_normalization import (
    MinuteLabelNormalizationError,
    normalize_c1_physical_intraday_1m_labels,
)
from ashare_v3.market.mootdx_batch_attempt import (
    MootdxBatchAttemptOutcome,
    MootdxBatchObjectTracker,
    MootdxEndpointTransportError,
    build_mootdx_minute_semantic_probe,
    is_endpoint_transport_exception,
    run_mootdx_batch_attempt,
    with_batch_attempt_provenance,
)
from ashare_v3.market.preload_plan import MINUTE_FACT_TABLES, normalize_db_row
from ashare_v3.market.previous_day_preload_execute import (
    bulk_upsert_minute_bars,
    first_present,
    json_safe,
    normalize_minute_bar_records,
    utc_now_iso,
    write_json,
    write_text,
)
from ashare_v3.market.subscription_plan import ADAPTER_NAMES, ASSET_KINDS
from ashare_v3.market.today_minute_plan import (
    DEFAULT_N3_C0_JSON_REPORT_PATH,
    REQUIRED_DATA_KIND,
    build_expected_bar_times,
    build_today_minute_rollback_sql,
    build_today_minute_subscription_report,
    ensure_shanghai_timezone,
    today_minute_subscriptions,
)
from ashare_v3.market.repositories import ASSET_FACT_TABLES
from ashare_v3.mootdx_client import EndpointSelection, MootdxEndpointManager


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_N3_C1_PRE_BACKUP_PATH = "docs/N3_C1_today_minute_bar_1m_execute_backup_before.json"
DEFAULT_N3_C1_POST_BACKUP_PATH = "docs/N3_C1_today_minute_bar_1m_execute_backup_after.json"
DEFAULT_N3_C1_JSON_REPORT_PATH = "docs/N3_C1_today_minute_bar_1m_execute_report.json"
DEFAULT_N3_C1_MD_REPORT_PATH = "docs/N3_C1_TODAY_MINUTE_BAR_1M_EXECUTE_REPORT.md"
DEFAULT_N3_C1_ROLLBACK_SQL_PATH = "sql/N3_C1_today_minute_bar_1m_rollback.sql"
SOURCE_NO_TRADE_QUALITY_VISIBLE_STATUS = "source_no_trade_quality_visible"
MOOTDX_INTRADAY_SOURCE_LUNCH_CLOSE_TIME = (13, 0)
CANONICAL_MORNING_CLOSE_TIME = (11, 30)

ALLOWED_C1_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
)
FORBIDDEN_C1_WRITE_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
)


class TodayMinuteExecuteError(RuntimeError):
    """Raised when N3-C1 execute violates its run-once contract."""


DEFAULT_INTRADAY_QUALITY_VISIBLE_NO_TRADE_PROOFS: dict[tuple[str, str], dict[str, Any]] = {
    ("20260622", "stock:SZ:002217"): {
        "status": "source_no_trade",
        "reason": "source_suspended",
        "source": "operator_confirmed_mootdx_intraday_no_trade",
        "trade_date": "20260622",
        "identity_key": "stock:SZ:002217",
        "writes_fake_bar": False,
    }
}


class MootdxTodayMinuteAdapter:
    """Fetch today 1 minute bars with Mootdx quote APIs.

    The adapter is lazy and is only instantiated by the execute path. Unit
    tests inject a fake client, so implementation tests never call external
    market-data APIs.
    """

    source_version = "mootdx.bars.today_minute.frequency8.offset800"
    external_source = "mootdx"

    def __init__(
        self,
        *,
        client: Any | None = None,
        market: str = "std",
        frequency: int = 8,
        start: int = 0,
        offset: int = 800,
        intraday_trade_date: str | None = None,
        quality_visible_no_trade_proofs: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
    ) -> None:
        self.frequency = frequency
        self.start = start
        self.offset = offset
        self.intraday_trade_date = intraday_trade_date
        proof_source = (
            DEFAULT_INTRADAY_QUALITY_VISIBLE_NO_TRADE_PROOFS
            if quality_visible_no_trade_proofs is None
            else quality_visible_no_trade_proofs
        )
        self.quality_visible_no_trade_proofs = {
            key: dict(value)
            for key, value in proof_source.items()
        }
        self._client = client
        if self._client is None:
            raise TodayMinuteExecuteError(
                "MootdxTodayMinuteAdapter requires a manager-selected pinned client"
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
            raise TodayMinuteExecuteError(f"unsupported asset_kind: {asset_kind}")
        rows = normalize_minute_bar_records(frame, trade_date=trade_date)
        return normalize_mootdx_intraday_minute_labels(
            rows,
            trade_date=trade_date,
            intraday_trade_date=self._resolved_intraday_trade_date(),
        )

    def _resolved_intraday_trade_date(self) -> str:
        return self.intraday_trade_date or datetime.now(tz=ASIA_SHANGHAI).strftime("%Y%m%d")

    def quality_visible_no_trade_proof(
        self,
        *,
        subscription: Mapping[str, Any],
        trade_date: str,
        actual_rows: Sequence[Mapping[str, Any]],
        expected_bar_count: int,
        latest_closed_minute: datetime,
    ) -> dict[str, Any] | None:
        if str(subscription.get("asset_kind") or "") != "stock":
            return None
        if len(actual_rows) >= expected_bar_count:
            return None
        proof = self.quality_visible_no_trade_proofs.get((trade_date, str(subscription.get("identity_key") or "")))
        if not proof:
            return None
        return {
            **dict(proof),
            "trade_date": trade_date,
            "identity_key": str(subscription.get("identity_key") or ""),
            "actual_bar_count": len(actual_rows),
            "expected_bar_count": expected_bar_count,
            "latest_closed_minute": latest_closed_minute.isoformat(),
        }


def normalize_mootdx_intraday_minute_labels(
    rows: Sequence[Mapping[str, Any]],
    *,
    trade_date: str,
    intraday_trade_date: str,
) -> list[dict[str, Any]]:
    """Validate C1 physical 1m labels without legacy lunch bridge rewriting."""

    try:
        return normalize_c1_physical_intraday_1m_labels(
            rows,
            trade_date=trade_date,
            intraday_trade_date=intraday_trade_date,
            source_adapter="mootdx",
        )
    except MinuteLabelNormalizationError as exc:
        raise TodayMinuteExecuteError(f"N3-C1 blocked: {exc}") from exc


def _bar_time_matches(row: Mapping[str, Any], hour: int, minute: int) -> bool:
    bar_time = ensure_shanghai_timezone(row["bar_time"])
    return bar_time.hour == hour and bar_time.minute == minute


def run_today_minute_bar_1m_execute(
    *,
    dsn: str,
    c0_plan_path: str = DEFAULT_N3_C0_JSON_REPORT_PATH,
    pre_backup_path: str = DEFAULT_N3_C1_PRE_BACKUP_PATH,
    post_backup_path: str = DEFAULT_N3_C1_POST_BACKUP_PATH,
    json_report_path: str = DEFAULT_N3_C1_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N3_C1_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_N3_C1_ROLLBACK_SQL_PATH,
    for_trade_date: str | None = None,
    today_minute_run_id: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    adapter: Any | None = None,
    endpoint_manager: MootdxEndpointManager | None = None,
    endpoint_probe: Callable[..., Mapping[str, Any]] | None = None,
    endpoint_client_factory: Callable[[EndpointSelection], Any] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> dict[str, Any]:
    """Execute one bounded N3-C1 today minute catch-up run."""

    plan = read_json(c0_plan_path)
    ensure_executable_plan(
        plan,
        execute=execute,
        user_confirmed=user_confirmed,
        for_trade_date=for_trade_date,
        today_minute_run_id=today_minute_run_id,
    )
    resolved_run_id = str(plan["today_minute_run_id"])
    source_run_id = str(plan["source_market_data_run_id"])
    started_at = utc_now_iso()

    pre_backup = capture_today_minute_execute_backup(
        dsn,
        phase="before_n3_c1",
        today_minute_run_id=resolved_run_id,
        source_run_id=source_run_id,
        for_trade_date=str(plan["for_trade_date"]),
    )
    ensure_clean_today_minute_target(pre_backup, resolved_run_id)
    write_json(pre_backup_path, pre_backup)

    subscription_report = build_today_minute_subscription_report(dsn=dsn, market_data_run_id=source_run_id)
    subscriptions = today_minute_subscriptions(subscription_report)
    ensure_subscription_counts_match_plan(subscriptions, plan)

    source_run_row = fetch_market_data_run_row_by_id(dsn, source_run_id)
    outcome: MootdxBatchAttemptOutcome[Any] | None = None
    atomic_committed = False
    if adapter is None:
        prepared, outcome = prepare_mootdx_today_minute_batch(
            plan=plan,
            subscriptions=subscriptions,
            manager=endpoint_manager or MootdxEndpointManager.from_toml(),
            probe=endpoint_probe
            or build_mootdx_minute_semantic_probe(
                subscriptions=subscriptions,
                trade_date=str(plan["for_trade_date"]),
                adapter_factory=lambda client: MootdxTodayMinuteAdapter(
                    client=client,
                    intraday_trade_date=str(plan["for_trade_date"]),
                ),
            ),
            client_factory=endpoint_client_factory,
        )
        object_results, data_snapshot, post_checks, quality_items = commit_today_minute_attempt_transaction(
            dsn=dsn,
            plan=plan,
            source_run_row=source_run_row,
            started_at=started_at,
            c0_plan_path=c0_plan_path,
            prepared=prepared,
            failed_results=failed_today_minute_batch_results(plan, subscriptions, outcome),
            outcome=outcome,
            pre_backup=pre_backup,
        )
        atomic_committed = True
    else:
        insert_today_minute_run(
            dsn,
            plan=plan,
            source_run_row=source_run_row,
            started_at=started_at,
            c0_plan_path=c0_plan_path,
        )
        object_results = execute_subscription_today_minutes(
            dsn=dsn,
            plan=plan,
            subscriptions=subscriptions,
            adapter=adapter,
            progress_callback=progress_callback,
            progress_every=progress_every,
        )

    if not atomic_committed:
        data_snapshot = capture_today_minute_execute_backup(
            dsn,
            phase="after_n3_c1_data_before_quality",
            today_minute_run_id=resolved_run_id,
            source_run_id=source_run_id,
            for_trade_date=str(plan["for_trade_date"]),
        )
        post_checks = build_post_execute_checks(
            plan=plan,
            pre_backup=pre_backup,
            data_snapshot=data_snapshot,
            object_results=object_results,
        )
        quality_items = build_post_execute_quality_items(
            plan=plan,
            post_checks=post_checks,
            object_results=object_results,
        )
    quality_counts = count_quality_severities(quality_items)
    if not atomic_committed:
        write_today_minute_quality_and_finalize_run(
            dsn,
            plan=plan,
            quality_items=quality_items,
            object_results=object_results,
            status="passed" if quality_counts["P0"] == 0 else "failed",
            batch_attempt=outcome.to_provenance() if outcome is not None else None,
        )

    post_backup = capture_today_minute_execute_backup(
        dsn,
        phase="after_n3_c1",
        today_minute_run_id=resolved_run_id,
        source_run_id=source_run_id,
        for_trade_date=str(plan["for_trade_date"]),
    )
    write_json(post_backup_path, post_backup)
    write_text(rollback_sql_path, build_today_minute_rollback_sql(resolved_run_id))

    report = {
        "stage": "N3-C1",
        "layer_role": "N3_market_data",
        "execution_mode": "today_minute_bar_1m_run_once_execute",
        "source_run_id": source_run_id,
        "today_minute_run_id": resolved_run_id,
        "source_condition_run_id": plan["source_condition_run_id"],
        "for_trade_date": plan["for_trade_date"],
        "source_trade_date": plan["source_trade_date"],
        "prev_trade_date": plan["prev_trade_date"],
        "latest_closed_minute": plan["latest_closed_minute"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "c0_plan_path": c0_plan_path,
        "pre_backup_path": pre_backup_path,
        "post_backup_path": post_backup_path,
        "rollback_sql_path": rollback_sql_path,
        "expected_asset_counts": build_expected_asset_counts(plan),
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
            "target_today_minute_run_row_counts": pre_backup["target_today_minute_run_row_counts"],
            "outbox_rows_for_run": pre_backup["outbox_rows_for_run"],
            "inbox_rows_for_run": pre_backup["inbox_rows_for_run"],
        },
        "post_execute": {
            "active_snapshot_hash": stable_json_hash(post_backup["active_snapshot"]),
            "target_today_minute_run_row_counts": post_backup["target_today_minute_run_row_counts"],
            "outbox_rows_for_run": post_backup["outbox_rows_for_run"],
            "inbox_rows_for_run": post_backup["inbox_rows_for_run"],
            "today_minute_run_row": post_backup["today_minute_run_row"],
        },
        "side_effects": {
            "writes_performed": True,
            "migration_executed": False,
            "market_data_pulled": True,
            "minute_bar_written": any(int(item.get("minute_rows_written") or 0) > 0 for item in object_results),
            "event_outbox_written": False,
            "outbox_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_today_minute_execute_report(report))
    return report


def prepare_mootdx_today_minute_batch(
    *,
    plan: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    manager: MootdxEndpointManager,
    probe: Callable[..., Mapping[str, Any]],
    client_factory: Callable[[EndpointSelection], Any] | None = None,
) -> tuple[list[dict[str, Any]], MootdxBatchAttemptOutcome[Any]]:
    outcome = run_mootdx_batch_attempt(
        manager=manager,
        batch_id=str(plan["today_minute_run_id"]),
        probe=probe,
        client_factory=client_factory,
        required_checks=("minute_scope_sentinels",),
        fetch_batch=lambda client, selection: _prepare_today_minute_attempt(
            plan=plan,
            subscriptions=subscriptions,
            adapter=MootdxTodayMinuteAdapter(client=client),
            object_tracker=MootdxBatchObjectTracker(manager, selection),
        ),
    )
    prepared = list(outcome.result or [])
    for item in prepared:
        item["mootdx_batch_attempt"] = outcome.to_provenance()
        item["minute_records"] = [
            with_batch_attempt_provenance(record, outcome)
            for record in item["minute_records"]
        ]
    return prepared, outcome


def _prepare_today_minute_attempt(
    *,
    plan: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    adapter: Any,
    object_tracker: MootdxBatchObjectTracker,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for subscription in subscriptions:
        try:
            normalized_rows = adapter.fetch_minute_bars(subscription, str(plan["for_trade_date"]))
        except Exception as exc:  # noqa: BLE001 - preserve local program and contract errors.
            if is_endpoint_transport_exception(exc):
                raise MootdxEndpointTransportError(str(exc)) from exc
            raise
        filtered_rows = filter_closed_today_minute_rows(
            normalized_rows,
            trade_date=str(plan["for_trade_date"]),
            latest_closed_minute=parse_latest_closed_minute(plan),
        )
        minute_records = build_today_minute_fact_records(
            plan=plan,
            subscription=subscription,
            normalized_rows=filtered_rows,
            adapter_name=adapter_name_for_subscription(plan, subscription),
            adapter=adapter,
        )
        expected_count = int(plan.get("expected_bar_count_per_object") or 0)
        object_result = object_tracker.record(
            identity_key=str(subscription.get("identity_key") or ""),
            value=minute_records,
            empty=len(minute_records) == 0,
        )
        passed = object_result.status == "passed" and len(minute_records) == expected_count
        prepared.append(
            {
                "subscription": dict(subscription),
                "minute_records": minute_records if passed else [],
                "status": "passed" if passed else "failed",
                "expected_bar_count": expected_count,
                "actual_bar_count": len(minute_records),
                "error_message": (
                    None
                    if passed
                    else f"object minute rows incomplete: expected={expected_count} actual={len(minute_records)}"
                ),
            }
        )
    return prepared


def write_prepared_today_minute_batch(
    *,
    dsn: str,
    prepared: Sequence[Mapping[str, Any]],
    connection_factory: Callable[[str], Any] | None = None,
    run_context: tuple[Mapping[str, Any], Mapping[str, Any], str, str] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    connect = connection_factory or (
        lambda value: audited_n3_market_execute_connect(value, connect_timeout=10, row_factory=dict_row)
    )
    with connect(dsn) as conn:
        with conn.transaction():
            if run_context is not None:
                plan, source_run_row, started_at, c0_plan_path = run_context
                with conn.cursor() as cur:
                    _insert_today_minute_run(
                        cur,
                        plan=plan,
                        source_run_row=source_run_row,
                        started_at=started_at,
                        c0_plan_path=c0_plan_path,
                        batch_attempt=prepared[0].get("mootdx_batch_attempt") if prepared else None,
                    )
            results.extend(_write_prepared_today_minute_batch_on_connection(conn, prepared))
    return results


def _write_prepared_today_minute_batch_on_connection(
    conn: Any,
    prepared: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in prepared:
        subscription = dict(item["subscription"])
        minute_records = list(item["minute_records"])
        provenance = (
            {"mootdx_batch_attempt": item["mootdx_batch_attempt"]}
            if item.get("mootdx_batch_attempt")
            else None
        )
        if item.get("status", "passed") != "passed":
            results.append(
                build_object_result(
                    subscription=subscription,
                    status="failed",
                    quality_status="failed",
                    expected_bar_count=int(item["expected_bar_count"]),
                    actual_bar_count=int(item["actual_bar_count"]),
                    minute_rows_written=0,
                    error_message=str(item["error_message"]),
                    quality_visible=provenance,
                )
            )
            continue
        with conn.cursor() as cur:
            written = bulk_upsert_minute_bars(cur, str(subscription["asset_kind"]), minute_records)
        results.append(
            build_object_result(
                subscription=subscription,
                status="passed",
                quality_status="passed",
                expected_bar_count=len(minute_records),
                actual_bar_count=len(minute_records),
                minute_rows_written=written,
                error_message=None,
                quality_visible=provenance,
            )
        )
    return results


def commit_today_minute_attempt_transaction(
    *,
    dsn: str,
    plan: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    c0_plan_path: str,
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
                _insert_today_minute_run(
                    cur,
                    plan=plan,
                    source_run_row=source_run_row,
                    started_at=started_at,
                    c0_plan_path=c0_plan_path,
                    batch_attempt=provenance,
                )
            object_results = (
                _write_prepared_today_minute_batch_on_connection(conn, prepared)
                if outcome.status == "passed"
                else [dict(row) for row in failed_results]
            )
            with conn.cursor() as cur:
                data_snapshot = dict(
                    data_snapshot_builder(cur)
                    if data_snapshot_builder is not None
                    else _capture_today_minute_execute_backup_with_cursor(
                        cur,
                        phase="after_n3_c1_data_before_quality",
                        today_minute_run_id=str(plan["today_minute_run_id"]),
                        source_run_id=str(plan["source_market_data_run_id"]),
                        for_trade_date=str(plan["for_trade_date"]),
                    )
                )
                post_checks = build_post_execute_checks(
                    plan=plan,
                    pre_backup=pre_backup,
                    data_snapshot=data_snapshot,
                    object_results=object_results,
                )
                quality_items = build_post_execute_quality_items(
                    plan=plan,
                    post_checks=post_checks,
                    object_results=object_results,
                )
                quality_counts = count_quality_severities(quality_items)
                (finalizer or _finalize_today_minute_run_with_cursor)(
                    cur,
                    plan=plan,
                    quality_items=quality_items,
                    object_results=object_results,
                    status="passed" if quality_counts["P0"] == 0 else "failed",
                    batch_attempt=provenance,
                )
    return object_results, data_snapshot, post_checks, quality_items


def failed_today_minute_batch_results(
    plan: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    outcome: MootdxBatchAttemptOutcome[Any],
) -> list[dict[str, Any]]:
    expected_count = int(plan.get("expected_bar_count_per_object") or 0)
    return [
        build_object_result(
            subscription=subscription,
            status="failed",
            quality_status="failed",
            expected_bar_count=expected_count,
            actual_bar_count=0,
            minute_rows_written=0,
            error_message="atomic Mootdx today-minute batch failed; all attempt rows discarded",
            quality_visible={"mootdx_batch_attempt": outcome.to_provenance()},
        )
        for subscription in subscriptions
    ]


def ensure_executable_plan(
    plan: Mapping[str, Any],
    *,
    execute: bool,
    user_confirmed: bool,
    for_trade_date: str | None,
    today_minute_run_id: str | None,
) -> None:
    if not execute:
        raise TodayMinuteExecuteError("N3-C1 execute requires explicit --execute")
    if not user_confirmed:
        raise TodayMinuteExecuteError("N3-C1 execute requires explicit --user-confirmed")
    if plan.get("stage") != "N3-C0":
        raise TodayMinuteExecuteError("N3-C1 blocked: C0 plan stage is not N3-C0")
    if plan.get("layer_role") != "N3_market_data":
        raise TodayMinuteExecuteError("N3-C1 blocked: C0 plan layer_role is not N3_market_data")
    if bool(plan.get("blocked")) or int((plan.get("quality") or {}).get("p0_count") or 0) > 0:
        raise TodayMinuteExecuteError("N3-C1 blocked: C0 plan has P0 blockers")
    if bool(plan.get("event_outbox_write_required_in_execute")):
        raise TodayMinuteExecuteError("N3-C1 blocked: C0 plan unexpectedly requires outbox writes")
    if plan.get("generated_event_types_for_execute") not in ([], None):
        raise TodayMinuteExecuteError("N3-C1 blocked: C0 plan has generated event types")
    if bool((plan.get("execute_contract") or {}).get("writes_outbox")):
        raise TodayMinuteExecuteError("N3-C1 blocked: execute contract must keep writes_outbox=false")
    if plan.get("latest_closed_minute"):
        try:
            expected_bar_count = int(plan.get("expected_bar_count_per_object"))
        except (TypeError, ValueError):
            expected_bar_count = 0
        if expected_bar_count <= 0:
            raise TodayMinuteExecuteError(
                "N3-C1 blocked: expected_bar_count_per_object missing or invalid in C0 plan"
            )
    if for_trade_date and for_trade_date != str(plan.get("for_trade_date") or ""):
        raise TodayMinuteExecuteError("N3-C1 blocked: CLI for_trade_date does not match C0 plan")
    if today_minute_run_id and today_minute_run_id != str(plan.get("today_minute_run_id") or ""):
        raise TodayMinuteExecuteError("N3-C1 blocked: CLI today_minute_run_id does not match C0 plan")


def ensure_clean_today_minute_target(backup: Mapping[str, Any], today_minute_run_id: str) -> None:
    if bool(backup.get("today_minute_run_exists")):
        raise TodayMinuteExecuteError(f"N3-C1 blocked: today minute run already exists: {today_minute_run_id}")
    dirty = {
        table_name: count
        for table_name, count in (backup.get("target_today_minute_run_row_counts") or {}).items()
        if int(count or 0) != 0
    }
    if dirty:
        raise TodayMinuteExecuteError(f"N3-C1 blocked: today minute target rows already exist: {dirty}")
    if int(backup.get("outbox_rows_for_run") or 0) != 0:
        raise TodayMinuteExecuteError("N3-C1 blocked: today_minute_run_id already has outbox rows")
    if int(backup.get("inbox_rows_for_run") or 0) != 0:
        raise TodayMinuteExecuteError("N3-C1 blocked: today_minute_run_id already has inbox rows")


def ensure_subscription_counts_match_plan(
    subscriptions: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> None:
    counts = Counter(str(row.get("asset_kind") or "") for row in subscriptions)
    expected = plan.get("today_minute_object_count_by_asset_kind") or {}
    mismatches = []
    for asset_kind in ASSET_KINDS:
        expected_count = int(expected.get(asset_kind) or 0)
        actual_count = int(counts.get(asset_kind) or 0)
        if actual_count != expected_count:
            mismatches.append(f"{asset_kind}: expected={expected_count} actual={actual_count}")
    if mismatches:
        raise TodayMinuteExecuteError(
            "N3-C1 blocked: subscription counts do not match C0 plan: " + "; ".join(mismatches)
        )


def execute_subscription_today_minutes(
    *,
    dsn: str,
    plan: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    adapter: Any,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total = len(subscriptions)
    for index, subscription in enumerate(subscriptions, start=1):
        if progress_callback and (index == 1 or index == total or index % max(progress_every, 1) == 0):
            progress_callback(
                f"N3-C1 today minute progress {index}/{total} "
                f"{subscription.get('asset_kind')} {subscription.get('identity_key')}"
            )
        results.append(
            execute_one_subscription_today_minute(
                dsn=dsn,
                plan=plan,
                subscription=subscription,
                adapter=adapter,
            )
        )
    return results


def execute_one_subscription_today_minute(
    *,
    dsn: str,
    plan: Mapping[str, Any],
    subscription: Mapping[str, Any],
    adapter: Any,
) -> dict[str, Any]:
    expected_count = int(plan.get("expected_bar_count_per_object") or 0)
    adapter_name = adapter_name_for_subscription(plan, subscription)
    try:
        normalized_rows = adapter.fetch_minute_bars(subscription, str(plan["for_trade_date"]))
        filtered_rows = filter_closed_today_minute_rows(
            normalized_rows,
            trade_date=str(plan["for_trade_date"]),
            latest_closed_minute=parse_latest_closed_minute(plan),
        )
        minute_records = build_today_minute_fact_records(
            plan=plan,
            subscription=subscription,
            normalized_rows=filtered_rows,
            adapter_name=adapter_name,
            adapter=adapter,
        )
        with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    written = bulk_upsert_minute_bars(cur, str(subscription["asset_kind"]), minute_records)
        quality_visible_no_trade_proof = quality_visible_no_trade_proof_for_subscription(
            adapter=adapter,
            subscription=subscription,
            plan=plan,
            actual_rows=filtered_rows,
            expected_bar_count=expected_count,
        )
        status, quality_status = classify_today_minute_object_status(
            actual_count=len(minute_records),
            expected_count=expected_count,
            error_message=None,
            quality_visible_no_trade_proof=quality_visible_no_trade_proof,
        )
        return build_object_result(
            subscription=subscription,
            status=status,
            quality_status=quality_status,
            expected_bar_count=expected_count,
            actual_bar_count=len(minute_records),
            minute_rows_written=written,
            error_message=None,
            quality_visible=quality_visible_no_trade_proof,
        )
    except Exception as exc:  # noqa: BLE001 - adapter or write failures become quality evidence.
        error_message = f"{type(exc).__name__}: {exc}"
        return build_object_result(
            subscription=subscription,
            status="failed",
            quality_status="failed",
            expected_bar_count=expected_count,
            actual_bar_count=0,
            minute_rows_written=0,
            error_message=error_message,
        )


def filter_closed_today_minute_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    trade_date: str,
    latest_closed_minute: datetime,
) -> list[dict[str, Any]]:
    expected_times = set(build_expected_bar_times(trade_date=trade_date, latest_closed_minute=latest_closed_minute))
    output = []
    for row in rows:
        bar_time = ensure_shanghai_timezone(row["bar_time"])
        if bar_time in expected_times:
            item = dict(row)
            item["bar_time"] = bar_time
            output.append(item)
    output.sort(key=lambda item: item["bar_time"])
    return output


def build_today_minute_fact_records(
    *,
    plan: Mapping[str, Any],
    subscription: Mapping[str, Any],
    normalized_rows: Sequence[Mapping[str, Any]],
    adapter_name: str,
    adapter: Any,
) -> list[dict[str, Any]]:
    source_run_id = str(plan["source_market_data_run_id"])
    today_minute_run_id = str(plan["today_minute_run_id"])
    records: list[dict[str, Any]] = []
    for row in normalized_rows:
        raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), Mapping) else dict(row)
        records.append(
            {
                "run_id": today_minute_run_id,
                "subscription_id": subscription.get("subscription_id"),
                "source_condition_run_id": plan["source_condition_run_id"],
                "for_trade_date": plan["for_trade_date"],
                "trade_date": plan["for_trade_date"],
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
                "is_previous_day_preload": False,
                "source_scope_ids": subscription.get("source_scope_ids") or [],
                "source_condition_pool_ids": subscription.get("source_condition_pool_ids") or [],
                "raw_json": {
                    "source_run_id": source_run_id,
                    "today_minute_run_id": today_minute_run_id,
                    "required_data_kind": REQUIRED_DATA_KIND,
                    "latest_closed_minute": plan.get("latest_closed_minute"),
                    "external_source": getattr(adapter, "external_source", "unknown"),
                    "source_adapter": adapter_name,
                    "source_version": getattr(adapter, "source_version", "unknown"),
                    "writes_outbox": False,
                    "raw_payload": json_safe(raw_payload),
                },
            }
        )
    return records


def adapter_name_for_subscription(plan: Mapping[str, Any], subscription: Mapping[str, Any]) -> str:
    asset_kind = str(subscription.get("asset_kind") or "")
    for row in source_adapter_rows(plan):
        if row.get("asset_kind") == asset_kind:
            return str(row.get("adapter_name") or ADAPTER_NAMES[asset_kind])
    return ADAPTER_NAMES[asset_kind]


def source_adapter_rows(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    section = plan.get("source_adapter_plan") or {}
    if isinstance(section, Mapping):
        rows = section.get("rows") or section.get("sample_rows") or []
        return [dict(row) for row in rows]
    if isinstance(section, Sequence) and not isinstance(section, (str, bytes, bytearray)):
        return [dict(row) for row in section]
    return []


def parse_latest_closed_minute(plan: Mapping[str, Any]) -> datetime:
    raw_value = str(plan.get("latest_closed_minute") or "")
    if not raw_value:
        raise TodayMinuteExecuteError("N3-C1 blocked: latest_closed_minute missing from C0 plan")
    return ensure_shanghai_timezone(datetime.fromisoformat(raw_value.replace("Z", "+00:00")))


def status_for_count(*, actual_count: int, expected_count: int, error_message: str | None) -> str:
    if error_message:
        return "failed"
    if actual_count == expected_count:
        return "passed"
    if actual_count == 0:
        return "missing"
    return "partial"


def classify_today_minute_object_status(
    *,
    actual_count: int,
    expected_count: int,
    error_message: str | None,
    quality_visible_no_trade_proof: Mapping[str, Any] | None,
) -> tuple[str, str]:
    status = status_for_count(actual_count=actual_count, expected_count=expected_count, error_message=error_message)
    if status in {"partial", "missing"} and quality_visible_no_trade_proof:
        return SOURCE_NO_TRADE_QUALITY_VISIBLE_STATUS, SOURCE_NO_TRADE_QUALITY_VISIBLE_STATUS
    return status, status


def quality_visible_no_trade_proof_for_subscription(
    *,
    adapter: Any,
    subscription: Mapping[str, Any],
    plan: Mapping[str, Any],
    actual_rows: Sequence[Mapping[str, Any]],
    expected_bar_count: int,
) -> dict[str, Any] | None:
    proof_method = getattr(adapter, "quality_visible_no_trade_proof", None)
    if not callable(proof_method):
        return None
    proof = proof_method(
        subscription=subscription,
        trade_date=str(plan["for_trade_date"]),
        actual_rows=actual_rows,
        expected_bar_count=expected_bar_count,
        latest_closed_minute=parse_latest_closed_minute(plan),
    )
    return dict(proof) if isinstance(proof, Mapping) else None


def build_object_result(
    *,
    subscription: Mapping[str, Any],
    status: str,
    quality_status: str,
    expected_bar_count: int,
    actual_bar_count: int,
    minute_rows_written: int,
    error_message: str | None,
    quality_visible: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "asset_kind": subscription.get("asset_kind"),
        "identity_key": subscription.get("identity_key"),
        "subscription_id": subscription.get("subscription_id"),
        "status": status,
        "quality_status": quality_status,
        "expected_bar_count": expected_bar_count,
        "actual_bar_count": actual_bar_count,
        "missing_bar_count": max(expected_bar_count - actual_bar_count, 0),
        "minute_rows_written": minute_rows_written,
        "error_message": error_message,
    }
    if quality_visible:
        result["quality_visible"] = dict(quality_visible)
    return result


def insert_today_minute_run(
    dsn: str,
    *,
    plan: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    c0_plan_path: str,
    batch_attempt: Mapping[str, Any] | None = None,
) -> None:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _insert_today_minute_run(
                    cur,
                    plan=plan,
                    source_run_row=source_run_row,
                    started_at=started_at,
                    c0_plan_path=c0_plan_path,
                    batch_attempt=batch_attempt,
                )


def _insert_today_minute_run(
    cur: Any,
    *,
    plan: Mapping[str, Any],
    source_run_row: Mapping[str, Any],
    started_at: str,
    c0_plan_path: str,
    batch_attempt: Mapping[str, Any] | None,
) -> None:
    counts = plan.get("today_minute_object_count_by_asset_kind") or {}
    subscription_count = sum(int(counts.get(asset_kind) or 0) for asset_kind in ASSET_KINDS)
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
                %s, %s, %s, %s, %s, 'N3-C1-today-minute-execute',
                false, false, false, false, %s, %s)
        """,
        (
            plan["today_minute_run_id"],
            plan["source_condition_run_id"],
            plan["for_trade_date"],
            plan["source_trade_date"],
            plan["prev_trade_date"],
            int(source_run_row.get("source_scope_row_count") or 0),
            int(source_run_row.get("candidate_row_count") or 0),
            subscription_count,
            subscription_count,
            source_run_row.get("dedup_ratio"),
            started_at,
            Jsonb(
                {
                    "stage": "N3-C1",
                    "source_run_id": plan["source_market_data_run_id"],
                    "today_minute_run_id": plan["today_minute_run_id"],
                    "c0_plan_path": c0_plan_path,
                    "writes_outbox": False,
                    "run_once_only": True,
                    "mootdx_batch_attempt": dict(batch_attempt) if batch_attempt else None,
                }
            ),
        ),
    )


def fetch_market_data_run_row_by_id(dsn: str, run_id: str) -> dict[str, Any]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        row = fetch_market_data_run_row(cur, run_id)
    if row is None:
        raise TodayMinuteExecuteError(f"N3-C1 blocked: source market_data_run missing: {run_id}")
    return row


def write_today_minute_quality_and_finalize_run(
    dsn: str,
    *,
    plan: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
    object_results: Sequence[Mapping[str, Any]],
    status: str,
    batch_attempt: Mapping[str, Any] | None = None,
) -> None:
    quality_counts = count_quality_severities(quality_items)
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _finalize_today_minute_run_with_cursor(
                    cur,
                    plan=plan,
                    quality_items=quality_items,
                    object_results=object_results,
                    status=status,
                    batch_attempt=batch_attempt,
                )


def _finalize_today_minute_run_with_cursor(
    cur: Any,
    *,
    plan: Mapping[str, Any],
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
    insert_quality_items(cur, plan=plan, quality_items=traced_quality_items)
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
                                "stage": "N3-C1",
                                "source_run_id": plan["source_market_data_run_id"],
                                "today_minute_run_id": plan["today_minute_run_id"],
                                "writes_outbox": False,
                                "write_result": summarize_write_result(object_results, quality_items),
                                "actual_asset_counts": summarize_actual_asset_counts(object_results),
                                "mootdx_batch_attempt": dict(batch_attempt) if batch_attempt else None,
                            }
                        ),
                        plan["today_minute_run_id"],
                    ),
    )


def insert_quality_items(
    cur: Any,
    *,
    plan: Mapping[str, Any],
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
                plan["today_minute_run_id"],
                plan["source_condition_run_id"],
                plan["for_trade_date"],
                plan["source_trade_date"],
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


def capture_today_minute_execute_backup(
    dsn: str,
    *,
    phase: str,
    today_minute_run_id: str,
    source_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return _capture_today_minute_execute_backup_with_cursor(
            cur,
            phase=phase,
            today_minute_run_id=today_minute_run_id,
            source_run_id=source_run_id,
            for_trade_date=for_trade_date,
        )


def _capture_today_minute_execute_backup_with_cursor(
    cur: Any,
    *,
    phase: str,
    today_minute_run_id: str,
    source_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "captured_at": utc_now_iso(),
        "source_run_id": source_run_id,
        "today_minute_run_id": today_minute_run_id,
        "for_trade_date": for_trade_date,
        "active_snapshot": fetch_n1_n2_active_snapshot(cur),
        "today_minute_run_exists": market_data_run_exists(cur, today_minute_run_id),
        "today_minute_run_row": fetch_market_data_run_row(cur, today_minute_run_id),
        "source_run_row": fetch_market_data_run_row(cur, source_run_id),
        "target_today_minute_run_row_counts": fetch_today_minute_run_row_counts(cur, today_minute_run_id),
        "target_today_minute_run_row_counts_by_asset": fetch_today_minute_run_counts_by_asset(
            cur,
            today_minute_run_id,
            for_trade_date,
        ),
        "duplicate_minute_key_count_by_asset": fetch_duplicate_minute_key_counts(
            cur,
            today_minute_run_id,
            for_trade_date,
        ),
        "physical_isolation_violation_count_by_asset": fetch_physical_isolation_violation_counts(
            cur,
            today_minute_run_id,
        ),
        "outbox_rows_for_run": fetch_outbox_count(cur, today_minute_run_id),
        "inbox_rows_for_run": fetch_inbox_count(cur, today_minute_run_id),
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


def fetch_today_minute_run_row_counts(cur: Any, run_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in (*MINUTE_FACT_TABLES.values(), "common_market_data_quality_item", "common_market_data_run"):
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE run_id = %s", (run_id,))
        counts[table_name] = int(cur.fetchone()["row_count"])
    return counts


def fetch_today_minute_run_counts_by_asset(cur: Any, run_id: str, trade_date: str) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for asset_kind in ASSET_KINDS:
        minute_table, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["minute"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count,
                   count(DISTINCT {identity_column})::bigint AS object_count
            FROM {minute_table}
            WHERE run_id = %s AND trade_date = %s AND is_previous_day_preload = false
            """,
            (run_id, trade_date),
        )
        row = cur.fetchone()
        output[asset_kind] = {
            "minute_row_count": int(row["row_count"]),
            "minute_object_count": int(row["object_count"]),
        }
    return output


def fetch_duplicate_minute_key_counts(cur: Any, run_id: str, trade_date: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        minute_table, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["minute"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS duplicate_group_count
            FROM (
              SELECT run_id, trade_date, {identity_column}, bar_time, source_adapter, count(*) AS row_count
              FROM {minute_table}
              WHERE run_id = %s AND trade_date = %s AND is_previous_day_preload = false
              GROUP BY run_id, trade_date, {identity_column}, bar_time, source_adapter
              HAVING count(*) > 1
            ) duplicates
            """,
            (run_id, trade_date),
        )
        output[asset_kind] = int(cur.fetchone()["duplicate_group_count"])
    return output


def fetch_physical_isolation_violation_counts(cur: Any, run_id: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        minute_table, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["minute"]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS violation_count
            FROM {minute_table}
            WHERE run_id = %s AND {identity_column} NOT LIKE %s
            """,
            (run_id, f"{asset_kind}:%"),
        )
        output[asset_kind] = int(cur.fetchone()["violation_count"])
    return output


def fetch_outbox_count(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def fetch_inbox_count(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def build_post_execute_checks(
    *,
    plan: Mapping[str, Any],
    pre_backup: Mapping[str, Any],
    data_snapshot: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_rows = {asset: int((plan.get("expected_minute_rows_by_asset_kind") or {}).get(asset) or 0) for asset in ASSET_KINDS}
    actual_rows = {
        asset: int((data_snapshot.get("target_today_minute_run_row_counts_by_asset") or {}).get(asset, {}).get("minute_row_count") or 0)
        for asset in ASSET_KINDS
    }
    expected_objects = {asset: int((plan.get("today_minute_object_count_by_asset_kind") or {}).get(asset) or 0) for asset in ASSET_KINDS}
    actual_objects = {
        asset: int((data_snapshot.get("target_today_minute_run_row_counts_by_asset") or {}).get(asset, {}).get("minute_object_count") or 0)
        for asset in ASSET_KINDS
    }
    duplicate_counts = data_snapshot.get("duplicate_minute_key_count_by_asset") or {}
    isolation_counts = data_snapshot.get("physical_isolation_violation_count_by_asset") or {}
    issue_counts = Counter(str(row.get("status") or "") for row in object_results)
    return {
        "n3_c1_expected_objects_by_asset": expected_objects,
        "n3_c1_actual_objects_by_asset": actual_objects,
        "n3_c1_expected_minute_rows_by_asset": expected_rows,
        "n3_c1_actual_minute_rows_by_asset": actual_rows,
        "n3_c1_minute_rows_not_exceed_expected": all(actual_rows[asset] <= expected_rows[asset] for asset in ASSET_KINDS),
        "n3_c1_total_minute_rows_present": sum(actual_rows.values()) > 0 or sum(expected_rows.values()) == 0,
        "n3_c1_duplicate_minute_key_zero": all(int(count or 0) == 0 for count in duplicate_counts.values()),
        "n3_c1_duplicate_minute_key_count_by_asset": dict(duplicate_counts),
        "n3_c1_physical_table_isolation": all(int(count or 0) == 0 for count in isolation_counts.values()),
        "n3_c1_physical_isolation_violation_count_by_asset": dict(isolation_counts),
        "n3_c1_outbox_rows_zero": int(pre_backup.get("outbox_rows_for_run") or 0) == 0
        and int(data_snapshot.get("outbox_rows_for_run") or 0) == 0,
        "n3_c1_inbox_rows_zero": int(pre_backup.get("inbox_rows_for_run") or 0) == 0
        and int(data_snapshot.get("inbox_rows_for_run") or 0) == 0,
        "n3_c1_n1_n2_active_snapshot_unchanged": stable_json_hash(pre_backup["active_snapshot"]) == stable_json_hash(data_snapshot["active_snapshot"]),
        "n3_c1_object_status_counts": dict(issue_counts),
        "n3_c1_partial_or_missing_objects": sum(issue_counts.get(key, 0) for key in ("partial", "missing", "failed")),
        "n3_c1_quality_visible_no_trade_objects": int(issue_counts.get(SOURCE_NO_TRADE_QUALITY_VISIBLE_STATUS) or 0),
    }


def build_post_execute_quality_items(
    *,
    plan: Mapping[str, Any],
    post_checks: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    issue_results = [row for row in object_results if row.get("status") in {"partial", "missing", "failed"}]
    failed_results = [row for row in object_results if row.get("status") == "failed"]
    quality_visible_no_trade_results = [
        row for row in object_results if row.get("status") == SOURCE_NO_TRADE_QUALITY_VISIBLE_STATUS
    ]
    items = [
        quality_item(
            "P0",
            "passed" if post_checks["n3_c1_minute_rows_not_exceed_expected"] else "failed",
            "n3_c1_minute_rows_not_exceed_expected",
            "today minute rows must not exceed C0 expected closed-minute rows",
            expected=json.dumps(post_checks["n3_c1_expected_minute_rows_by_asset"], ensure_ascii=False, sort_keys=True),
            actual=json.dumps(post_checks["n3_c1_actual_minute_rows_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_c1_total_minute_rows_present"] else "failed",
            "n3_c1_total_minute_rows_present",
            "today minute execute must write at least one row when rows were expected",
            expected=">0 when expected rows > 0",
            actual=str(sum(int(value) for value in post_checks["n3_c1_actual_minute_rows_by_asset"].values())),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_c1_duplicate_minute_key_zero"] else "failed",
            "n3_c1_duplicate_minute_key_zero",
            "duplicate minute key count must be zero in each physical table",
            expected="0",
            actual=json.dumps(post_checks["n3_c1_duplicate_minute_key_count_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_c1_physical_table_isolation"] else "failed",
            "n3_c1_physical_table_isolation",
            "identity_key prefix must match the physical minute table family",
            expected="0",
            actual=json.dumps(post_checks["n3_c1_physical_isolation_violation_count_by_asset"], ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_c1_outbox_rows_zero"] else "failed",
            "n3_c1_outbox_rows_zero",
            "N3-C1 writes_outbox=false; common_event_outbox must not receive rows for this run_id",
            expected="0",
            actual="0" if post_checks["n3_c1_outbox_rows_zero"] else "non-zero",
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_c1_inbox_rows_zero"] else "failed",
            "n3_c1_inbox_rows_zero",
            "N3-C1 does not consume outbox; common_event_inbox must not receive rows for this run_id",
            expected="0",
            actual="0" if post_checks["n3_c1_inbox_rows_zero"] else "non-zero",
        ),
        quality_item(
            "P0",
            "passed" if post_checks["n3_c1_n1_n2_active_snapshot_unchanged"] else "failed",
            "n3_c1_n1_n2_active_snapshot_unchanged",
            "N3-C1 must not modify N1/N2 active lineage",
            expected="unchanged",
            actual="unchanged" if post_checks["n3_c1_n1_n2_active_snapshot_unchanged"] else "changed",
        ),
    ]
    if issue_results:
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c1_partial_or_missing_objects",
                "ordinary partial/missing/failed today minute objects block C1 completeness",
                expected="0 issue objects",
                actual=str(len(issue_results)),
                details={
                    "issue_count": len(issue_results),
                    "sample": [summarize_object_result(row) for row in issue_results[:20]],
                    "failed_count": len(failed_results),
                },
            )
        )
    if quality_visible_no_trade_results:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c1_quality_visible_no_trade_objects",
                "source-confirmed no-trade/suspended today minute objects remain quality-visible without fake bars",
                expected="explicit source no-trade proof for every excluded object",
                actual=str(len(quality_visible_no_trade_results)),
                details={
                    "issue_count": len(quality_visible_no_trade_results),
                    "sample": [summarize_object_result(row) for row in quality_visible_no_trade_results[:20]],
                    "policy": "do_not_fabricate_minute_bars",
                },
            )
        )
    if not issue_results and not quality_visible_no_trade_results:
        items.append(
            quality_item(
                "P2",
                "passed",
                "n3_c1_today_minute_execute_clean",
                "today minute execute finished without partial/missing/failed objects",
                expected="no issue objects",
                actual="no issue objects",
            )
        )
    if int((plan.get("quality") or {}).get("p1_count") or 0) > 0:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c1_inherited_c0_p1",
                "C1 inherited non-blocking warnings from C0 dry-run",
                expected="p1_count=0",
                actual=f"p1_count={(plan.get('quality') or {}).get('p1_count')}",
            )
        )
    return items


def summarize_object_result(row: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "asset_kind": row.get("asset_kind"),
        "identity_key": row.get("identity_key"),
        "status": row.get("status"),
        "expected_bar_count": row.get("expected_bar_count"),
        "actual_bar_count": row.get("actual_bar_count"),
        "missing_bar_count": row.get("missing_bar_count"),
        "error_message": row.get("error_message"),
    }
    if row.get("quality_visible"):
        summary["quality_visible"] = row.get("quality_visible")
    return summary


def summarize_actual_asset_counts(object_results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {
        asset_kind: {"object_count": 0, "minute_rows_written": 0, "issue_object_count": 0, "quality_visible_object_count": 0}
        for asset_kind in ASSET_KINDS
    }
    for row in object_results:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind not in output:
            continue
        output[asset_kind]["object_count"] += 1
        output[asset_kind]["minute_rows_written"] += int(row.get("minute_rows_written") or 0)
        if row.get("status") in {"partial", "missing", "failed"}:
            output[asset_kind]["issue_object_count"] += 1
        if row.get("status") == SOURCE_NO_TRADE_QUALITY_VISIBLE_STATUS:
            output[asset_kind]["quality_visible_object_count"] += 1
    return output


def summarize_write_result(
    object_results: Sequence[Mapping[str, Any]],
    quality_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "objects_processed": len(object_results),
        "objects_passed": sum(1 for row in object_results if row.get("status") == "passed"),
        "objects_partial": sum(1 for row in object_results if row.get("status") == "partial"),
        "objects_missing": sum(1 for row in object_results if row.get("status") == "missing"),
        "objects_failed": sum(1 for row in object_results if row.get("status") == "failed"),
        "objects_quality_visible_no_trade": sum(
            1 for row in object_results if row.get("status") == SOURCE_NO_TRADE_QUALITY_VISIBLE_STATUS
        ),
        "minute_rows_written": sum(int(row.get("minute_rows_written") or 0) for row in object_results),
        "quality_item_rows_written": len(quality_items),
        "event_outbox_rows_written": 0,
    }


def build_expected_asset_counts(plan: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    object_counts = plan.get("today_minute_object_count_by_asset_kind") or {}
    row_counts = plan.get("expected_minute_rows_by_asset_kind") or {}
    return {
        asset_kind: {
            "object_count": int(object_counts.get(asset_kind) or 0),
            "subscription_count": int(object_counts.get(asset_kind) or 0),
            "expected_minute_rows": int(row_counts.get(asset_kind) or 0),
        }
        for asset_kind in ASSET_KINDS
    }


def read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def format_today_minute_execute_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    write = report.get("write_result") or {}
    side_effects = report.get("side_effects") or {}
    rows_by_asset = (report.get("post_checks") or {}).get("n3_c1_actual_minute_rows_by_asset") or {}
    return "\n".join(
        [
            "# N3-C1 today_minute_bar_1m execute report",
            "",
            "## Result",
            "",
            f"- status: {'EXECUTED' if int(quality.get('p0_count') or 0) == 0 else 'FAILED'}",
            f"- today_minute_run_id: `{report.get('today_minute_run_id')}`",
            f"- source_run_id: `{report.get('source_run_id')}`",
            f"- for_trade_date: `{report.get('for_trade_date')}`",
            f"- latest_closed_minute: `{report.get('latest_closed_minute')}`",
            f"- P0/P1/P2: {quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
            "",
            "## Writes",
            "",
            f"- minute_rows_written: {write.get('minute_rows_written')}",
            f"- stock/index/board rows: {json.dumps(rows_by_asset, ensure_ascii=False, sort_keys=True)}",
            f"- quality_item_rows_written: {write.get('quality_item_rows_written')}",
            f"- event_outbox_rows_written: {write.get('event_outbox_rows_written')}",
            "",
            "## Boundaries",
            "",
            f"- market_data_pulled: {side_effects.get('market_data_pulled')}",
            f"- minute_bar_written: {side_effects.get('minute_bar_written')}",
            f"- event_outbox_written: {side_effects.get('event_outbox_written')}",
            f"- outbox_consumed: {side_effects.get('outbox_consumed')}",
            f"- downstream_layers_touched: {side_effects.get('downstream_layers_touched')}",
            f"- worker_started: {side_effects.get('worker_started')}",
            "",
            "## Rollback",
            "",
            f"- rollback_sql_path: `{report.get('rollback_sql_path')}`",
            "",
        ]
    )
