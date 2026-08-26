"""N3-C2 closed minute / closed 30m replay run-once executor.

The module implements the future C2 execute boundary, but importing or testing
it does not pull market data or write the runtime database. The public runner
requires explicit ``--execute`` and ``--user-confirmed`` gates before it can
write C2-scoped minute deltas, closed 30m summaries, quality rows, and a single
market-data run row. It never writes or consumes event outbox/inbox rows.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities
from ashare_v3.market.closed_30m_replay_plan import (
    ASIA_SHANGHAI,
    BUCKET_SPECS,
    FORBIDDEN_WRITE_TABLES,
    IDENTITY_COLUMNS,
    SUMMARY_TABLES,
    build_full_day_minute_labels,
    fetch_minute_subscriptions,
    fetch_target_audit,
)
from ashare_v3.market.mootdx_batch_attempt import (
    MootdxBatchAttemptOutcome,
    MootdxBatchObjectTracker,
    MootdxEndpointTransportError,
    build_mootdx_minute_semantic_probe,
    is_endpoint_transport_exception,
    run_mootdx_batch_attempt,
)
from ashare_v3.market.preload_plan import MINUTE_FACT_TABLES, normalize_db_row
from ashare_v3.market.previous_day_preload_execute import (
    json_safe,
    normalize_minute_bar_records,
    utc_now_iso,
    write_json,
    write_text,
)
from ashare_v3.market.subscription_plan import ASSET_KINDS
from ashare_v3.mootdx_client import EndpointSelection, MootdxEndpointManager


DEFAULT_C2_DRY_RUN_PLAN_PATH = "docs/N3_C2_closed_30m_dry_run_plan.json"
DEFAULT_C2_EXECUTE_CONTRACT_PATH = "docs/N3_C2_closed_30m_execute_contract.json"
DEFAULT_C2_DRY_RUN_REPORT_PATH = "docs/N3_C2_closed_30m_replay_dry_run_report.json"
DEFAULT_C2_JSON_REPORT_PATH = "docs/N3_C2_closed_30m_replay_execute_report.json"
DEFAULT_C2_MD_REPORT_PATH = "docs/N3_C2_CLOSED_30M_REPLAY_EXECUTE_REPORT.md"
DEFAULT_C2_ROLLBACK_SQL_PATH = "sql/N3_C2_closed_30m_business_rollback.sql"

CLOSED_30M_METRIC_SCOPE = "closed_30m_replay"
C2_QUALITY_LAYER_SCOPE = "market_data_run"
C2_QUALITY_SCHEMA_VERSION = "n3.closed_30m_replay.v1"
ALLOWED_QUALITY_DATA_DOMAINS = ("common", "stock", "index", "board")
C2_REPLAY_COMPARE_KEY = ["asset_kind", "identity_key", "trade_date", "bar_time"]
C2_REPLAY_TOLERANCE = {
    "price_abs": "0.000001",
    "amount_abs": "0.01",
    "volume_abs": "0.000001",
}
C2_REPLAY_DIFF_REQUIRED_FIELDS = (
    "c2_run_id",
    "baseline_run_id",
    "replay_source_adapter",
    "compare_key",
    "tolerance",
    "delta_kind",
    "c2_delta_bar_id",
    "source_error",
    "replay_row_hash",
    "baseline_row_hash",
    "diff_fields",
    "source_trade_date",
    "source_bar_time",
)

ALLOWED_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
)


class Closed30mReplayExecuteError(RuntimeError):
    """Raised when N3-C2 execute violates its reviewed contract."""


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


class MootdxClosed30mReplayAdapter:
    """Fetch full-day 1m replay bars with Mootdx TDX APIs.

    The routing is intentionally explicit: stock objects use ``bars`` while
    index and TDX board objects use ``index_bars``. The execute runner filters
    normalized rows to the requested trade date and official full-day labels.
    """

    source_adapter = "mootdx.std.closed_30m_replay.frequency8"
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
            raise Closed30mReplayExecuteError(
                "MootdxClosed30mReplayAdapter requires a manager-selected pinned client"
            )

    def fetch_full_day_minute_bars(self, subscription: Mapping[str, Any], trade_date: str) -> list[dict[str, Any]]:
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
            raise Closed30mReplayExecuteError(f"N3-C2 blocked: unsupported asset_kind for replay adapter: {asset_kind}")
        expected_labels = set(build_full_day_minute_labels())
        rows = normalize_minute_bar_records(frame, trade_date=trade_date)
        return [row for row in rows if minute_label(row.get("bar_time")) in expected_labels]


def ensure_c2_execute_contract(
    dry_run_plan: Mapping[str, Any],
    execute_contract: Mapping[str, Any],
    dry_run_report: Mapping[str, Any],
    *,
    execute: bool,
    user_confirmed: bool,
    c2_run_id: str | None,
    for_trade_date: str | None,
) -> None:
    """Validate the reviewed C2 artifacts and explicit execute gates."""

    if not execute:
        raise Closed30mReplayExecuteError("N3-C2 blocked: --execute is required")
    if not user_confirmed:
        raise Closed30mReplayExecuteError("N3-C2 blocked: --user-confirmed is required")

    expected_run_id = str(execute_contract.get("c2_run_id") or dry_run_report.get("c2_run_id") or "")
    if not expected_run_id or str(c2_run_id or "") != expected_run_id:
        raise Closed30mReplayExecuteError(
            f"N3-C2 blocked: c2_run_id mismatch, cli={c2_run_id} expected={expected_run_id}"
        )
    for artifact_name, artifact in (("dry-run plan", dry_run_plan), ("dry-run report", dry_run_report)):
        artifact_run_id = str(artifact.get("c2_run_id") or "")
        if artifact_run_id and artifact_run_id != expected_run_id:
            raise Closed30mReplayExecuteError(
                f"N3-C2 blocked: c2_run_id mismatch in {artifact_name}, artifact={artifact_run_id} expected={expected_run_id}"
            )

    expected_trade_date = str(execute_contract.get("for_trade_date") or dry_run_report.get("for_trade_date") or "")
    if not expected_trade_date or str(for_trade_date or "") != expected_trade_date:
        raise Closed30mReplayExecuteError(
            f"N3-C2 blocked: for_trade_date mismatch, cli={for_trade_date} expected={expected_trade_date}"
        )

    for artifact_name, artifact in (
        ("dry-run plan", dry_run_plan),
        ("execute contract", execute_contract),
        ("dry-run report", dry_run_report),
    ):
        if artifact.get("layer_role") != "N3_market_data":
            raise Closed30mReplayExecuteError(f"N3-C2 blocked: {artifact_name} layer_role must be N3_market_data")

    if dry_run_report.get("result") != "DRY_RUN_PASS" or bool(dry_run_report.get("blocked")):
        raise Closed30mReplayExecuteError("N3-C2 blocked: dry-run report is not DRY_RUN_PASS")
    quality = dry_run_report.get("quality") or {}
    if int(quality.get("p0_count") or 0) != 0:
        raise Closed30mReplayExecuteError("N3-C2 blocked: dry-run report still has P0 quality items")

    for source_name, source in (
        ("dry-run plan", dry_run_plan),
        ("execute contract", execute_contract),
    ):
        if bool(source.get("writes_outbox")):
            raise Closed30mReplayExecuteError(f"N3-C2 blocked: {source_name} must keep writes_outbox=false")

    write_scope = dry_run_plan.get("write_scope") or {}
    if bool(write_scope.get("writes_outbox")):
        raise Closed30mReplayExecuteError("N3-C2 blocked: dry-run write_scope must keep writes_outbox=false")
    if bool(execute_contract.get("starts_worker")):
        raise Closed30mReplayExecuteError("N3-C2 blocked: execute contract must not start worker")

    report_expected = ((dry_run_report.get("closed_30m_summary_plan") or {}).get("expected_summary_rows") or {}).get("total")
    contract_expected = expected_summary_rows_from_contract(execute_contract)["total"]
    if report_expected is not None and contract_expected is not None and int(report_expected) != int(contract_expected):
        raise Closed30mReplayExecuteError("N3-C2 blocked: expected summary rows differ between contract and dry-run")


def ensure_clean_c2_target(target_audit: Mapping[str, Any], c2_run_id: str) -> None:
    if bool(target_audit.get("run_exists")):
        raise Closed30mReplayExecuteError(f"N3-C2 blocked: c2_run_id already exists in common_market_data_run: {c2_run_id}")
    nested_checks = (
        ("minute", "minute_rows_for_c2_run"),
        ("summary", "summary_rows_for_c2_run"),
    )
    for label, key in nested_checks:
        rows_by_asset = target_audit.get(key) or {}
        for asset_kind in ASSET_KINDS:
            count = int((rows_by_asset or {}).get(asset_kind) or 0)
            if count:
                raise Closed30mReplayExecuteError(f"N3-C2 blocked: {label} rows already exist for {asset_kind}: {count}")
    scalar_checks = (
        ("quality", "quality_rows_for_c2_run"),
        ("outbox", "outbox_rows_for_c2_run"),
        ("inbox", "inbox_rows_for_c2_run"),
        ("checkpoint", "checkpoint_rows_for_c2_run"),
    )
    for label, key in scalar_checks:
        count = int(target_audit.get(key) or 0)
        if count:
            raise Closed30mReplayExecuteError(f"N3-C2 blocked: {label} rows already exist for c2_run_id {c2_run_id}: {count}")


def run_closed_30m_replay_execute(
    *,
    dsn: str,
    dry_run_plan_path: str = DEFAULT_C2_DRY_RUN_PLAN_PATH,
    execute_contract_path: str = DEFAULT_C2_EXECUTE_CONTRACT_PATH,
    dry_run_report_path: str = DEFAULT_C2_DRY_RUN_REPORT_PATH,
    json_report_path: str = DEFAULT_C2_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_C2_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_C2_ROLLBACK_SQL_PATH,
    c2_run_id: str | None = None,
    for_trade_date: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    adapter: Any | None = None,
    endpoint_manager: MootdxEndpointManager | None = None,
    endpoint_probe: Callable[..., Mapping[str, Any]] | None = None,
    endpoint_client_factory: Callable[[EndpointSelection], Any] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> dict[str, Any]:
    """Execute a single reviewed C2 replay pass, then exit."""

    dry_run_plan = read_json(dry_run_plan_path)
    execute_contract = read_json(execute_contract_path)
    dry_run_report = read_json(dry_run_report_path)
    ensure_c2_execute_contract(
        dry_run_plan,
        execute_contract,
        dry_run_report,
        execute=execute,
        user_confirmed=user_confirmed,
        c2_run_id=c2_run_id,
        for_trade_date=for_trade_date,
    )

    resolved_run_id = str(execute_contract["c2_run_id"])
    resolved_trade_date = str(execute_contract["for_trade_date"])
    source_condition_run_id = str(dry_run_report["source_condition_run_id"])
    source_subscription_run_id = str(dry_run_report["source_subscription_run_id"])
    today_minute_run_id = str(dry_run_report["today_minute_run_id"])
    started_at = utc_now_iso()

    pre_backup = capture_c2_execute_snapshot(dsn, c2_run_id=resolved_run_id)
    ensure_clean_c2_target(pre_backup["target_audit"], resolved_run_id)

    subscriptions = fetch_c2_subscriptions(dsn, source_subscription_run_id)
    all_delta_rows: dict[str, list[dict[str, Any]]] = {asset_kind: [] for asset_kind in ASSET_KINDS}
    all_summary_rows: dict[str, list[dict[str, Any]]] = {asset_kind: [] for asset_kind in ASSET_KINDS}
    object_results: list[dict[str, Any]] = []
    expected_labels = build_full_day_minute_labels()
    baseline_rows_by_identity: dict[str, list[dict[str, Any]]] = {}

    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn, conn.cursor() as cur:
        for subscription in subscriptions:
            asset_kind = str(subscription["asset_kind"])
            baseline_rows_by_identity[str(subscription["identity_key"])] = fetch_baseline_minute_rows(
                cur,
                asset_kind=asset_kind,
                today_minute_run_id=today_minute_run_id,
                identity_key=str(subscription["identity_key"]),
                trade_date=resolved_trade_date,
            )

    batch_outcome: MootdxBatchAttemptOutcome[Any] | None = None
    if adapter is None:
        replay_batch, batch_outcome = prepare_mootdx_c2_replay_batch(
            c2_run_id=resolved_run_id,
            trade_date=resolved_trade_date,
            subscriptions=subscriptions,
            manager=endpoint_manager or MootdxEndpointManager.from_toml(),
            probe=endpoint_probe
            or build_mootdx_minute_semantic_probe(
                subscriptions=subscriptions,
                trade_date=resolved_trade_date,
                adapter_factory=lambda client: MootdxClosed30mReplayAdapter(client=client),
                fetch_rows=lambda value, subscription, date: value.fetch_full_day_minute_bars(subscription, date),
            ),
            client_factory=endpoint_client_factory,
        )
    else:
        replay_batch = []
        for subscription in subscriptions:
            try:
                replay_rows = adapter.fetch_full_day_minute_bars(subscription, resolved_trade_date)
                fetch_error = None
            except Exception as exc:  # pragma: no cover - real adapter branch
                replay_rows = []
                fetch_error = str(exc)
            replay_batch.append(
                {
                    "subscription": dict(subscription),
                    "replay_rows": replay_rows,
                    "fetch_error": fetch_error,
                    "source_adapter": getattr(adapter, "source_adapter", "mootdx.std.closed_30m_replay.frequency8"),
                    "source_version": getattr(adapter, "source_version", "mootdx.bars.frequency8.offset800"),
                }
            )

    for index, item in enumerate(replay_batch, start=1):
        subscription = dict(item["subscription"])
        if progress_callback and (index == 1 or index % progress_every == 0 or index == len(subscriptions)):
            progress_callback(f"N3-C2 replaying {index}/{len(subscriptions)} {subscription['identity_key']}")
        asset_kind = str(subscription["asset_kind"])
        baseline_rows = baseline_rows_by_identity[str(subscription["identity_key"])]
        replay_rows = list(item["replay_rows"])
        fetch_error = item.get("fetch_error")
        delta_rows = build_replay_delta_records(
            c2_run_id=resolved_run_id,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=resolved_trade_date,
            subscription=subscription,
            baseline_rows=baseline_rows,
            replay_rows=replay_rows,
            expected_labels=expected_labels,
            source_adapter=str(item["source_adapter"]),
            source_version=str(item["source_version"]),
        )
        summary_rows = build_closed_30m_summary_records(
            c2_run_id=resolved_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_today_minute_run_ids=[today_minute_run_id],
            for_trade_date=resolved_trade_date,
            subscription=subscription,
            baseline_rows=baseline_rows,
            delta_rows=delta_rows,
            fetch_error=fetch_error,
        )
        all_delta_rows[asset_kind].extend(delta_rows)
        all_summary_rows[asset_kind].extend(summary_rows)
        object_results.append(
            {
                "asset_kind": asset_kind,
                "identity_key": subscription["identity_key"],
                "replay_rows": len(replay_rows),
                "delta_rows": len(delta_rows),
                "summary_rows": len(summary_rows),
                "fetch_error": fetch_error,
            }
        )
    if batch_outcome is not None and batch_outcome.status != "passed":
        object_results = [
            {
                "asset_kind": subscription["asset_kind"],
                "identity_key": subscription["identity_key"],
                "replay_rows": 0,
                "delta_rows": 0,
                "summary_rows": 0,
                "fetch_error": "atomic Mootdx C2 batch failed; all attempt rows discarded",
                "mootdx_batch_attempt": batch_outcome.to_provenance(),
            }
            for subscription in subscriptions
        ]

    row_summary = summarize_execute_rows(
        c2_run_id=resolved_run_id,
        minute_delta_rows={asset_kind: len(rows) for asset_kind, rows in all_delta_rows.items()},
        summary_rows={asset_kind: len(rows) for asset_kind, rows in all_summary_rows.items()},
        summary_status=Counter(row["closed_status"] for rows in all_summary_rows.values() for row in rows),
        quality_rows=0,
        outbox_rows_for_c2_run=0,
    )
    if batch_outcome is None or batch_outcome.status == "passed":
        validate_generated_summary_rows(row_summary, execute_contract)
    quality_items = build_c2_quality_items(
        c2_run_id=resolved_run_id,
        source_condition_run_id=source_condition_run_id,
        row_summary=row_summary,
    )
    quality_counts = count_quality_severities(quality_items)
    status = "passed" if quality_counts["P0"] == 0 else "failed"

    write_c2_execute_transaction(
        dsn=dsn,
        c2_run_id=resolved_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        today_minute_run_id=today_minute_run_id,
        for_trade_date=resolved_trade_date,
        started_at=started_at,
        status=status,
        quality_counts=quality_counts,
        delta_rows_by_asset=all_delta_rows,
        summary_rows_by_asset=all_summary_rows,
        quality_items=quality_items,
        dry_run_plan_path=dry_run_plan_path,
        execute_contract_path=execute_contract_path,
        dry_run_report_path=dry_run_report_path,
        batch_attempt=batch_outcome.to_provenance() if batch_outcome is not None else None,
    )

    post_backup = capture_c2_execute_snapshot(dsn, c2_run_id=resolved_run_id)
    rollback_scope = build_closed_30m_rollback_scope(resolved_run_id)
    row_summary = summarize_execute_rows(
        c2_run_id=resolved_run_id,
        minute_delta_rows={asset_kind: len(rows) for asset_kind, rows in all_delta_rows.items()},
        summary_rows={asset_kind: len(rows) for asset_kind, rows in all_summary_rows.items()},
        summary_status=Counter(row["closed_status"] for rows in all_summary_rows.values() for row in rows),
        quality_rows=len(quality_items),
        outbox_rows_for_c2_run=post_backup["target_audit"]["outbox_rows_for_c2_run"],
    )
    report = {
        "stage": "N3-C2",
        "layer_role": "N3_market_data",
        "execution_mode": "closed_minute_30m_replay_run_once_execute",
        "result": "EXECUTED" if quality_counts["P0"] == 0 else "FAILED",
        "c2_run_id": resolved_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "today_minute_run_id": today_minute_run_id,
        "for_trade_date": resolved_trade_date,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "paths": {
            "dry_run_plan_path": dry_run_plan_path,
            "execute_contract_path": execute_contract_path,
            "dry_run_report_path": dry_run_report_path,
            "rollback_sql_path": rollback_sql_path,
        },
        "write_result": row_summary,
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "pre_execute": pre_backup,
        "post_execute": post_backup,
        "object_results_sample": object_results[:20],
        "rollback": rollback_scope,
        "next_allowed_step": "N3-C2 execute post-review" if quality_counts["P0"] == 0 else "rollback or fix C2 P0 before review",
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, render_c2_execute_markdown(report))
    write_text(rollback_sql_path, build_c2_business_rollback_sql(resolved_run_id))
    return report


def prepare_mootdx_c2_replay_batch(
    *,
    c2_run_id: str,
    trade_date: str,
    subscriptions: Sequence[Mapping[str, Any]],
    manager: MootdxEndpointManager,
    probe: Callable[..., Mapping[str, Any]],
    client_factory: Callable[[EndpointSelection], Any] | None = None,
) -> tuple[list[dict[str, Any]], MootdxBatchAttemptOutcome[Any]]:
    outcome = run_mootdx_batch_attempt(
        manager=manager,
        batch_id=c2_run_id,
        probe=probe,
        client_factory=client_factory,
        required_checks=("minute_scope_sentinels",),
        fetch_batch=lambda client, selection: _prepare_complete_c2_replay_attempt(
            trade_date=trade_date,
            subscriptions=subscriptions,
            adapter=MootdxClosed30mReplayAdapter(client=client),
            object_tracker=MootdxBatchObjectTracker(manager, selection),
        ),
    )
    prepared = list(outcome.result or [])
    if outcome.status == "passed":
        provenance = outcome.to_provenance()
        winning = next(
            (
                dict(attempt)
                for attempt in provenance.get("attempts") or []
                if attempt.get("attempt_id") == provenance.get("winning_attempt_id")
            ),
            {},
        )
        for item in prepared:
            item["subscription"] = {
                **dict(item["subscription"]),
                "mootdx_batch_attempt": provenance,
            }
            item["source_adapter"] = str(item["source_adapter"])
            item["source_version"] = str(item["source_version"])
            for row in item["replay_rows"]:
                row["attempt_id"] = winning.get("attempt_id")
                row["endpoint_id"] = winning.get("endpoint_id")
                row["endpoint_host"] = winning.get("endpoint_host")
                row["endpoint_port"] = winning.get("endpoint_port")
    return prepared, outcome


def _prepare_complete_c2_replay_attempt(
    *,
    trade_date: str,
    subscriptions: Sequence[Mapping[str, Any]],
    adapter: MootdxClosed30mReplayAdapter,
    object_tracker: MootdxBatchObjectTracker,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for subscription in subscriptions:
        try:
            rows = adapter.fetch_full_day_minute_bars(subscription, trade_date)
        except Exception as exc:  # noqa: BLE001 - preserve local program and contract errors.
            if is_endpoint_transport_exception(exc):
                raise MootdxEndpointTransportError(str(exc)) from exc
            raise
        object_result = object_tracker.record(
            identity_key=str(subscription.get("identity_key") or ""),
            value=rows,
            empty=not rows,
        )
        prepared.append(
            {
                "subscription": dict(subscription),
                "replay_rows": rows,
                "fetch_error": None if object_result.status == "passed" else "empty_required_object",
                "source_adapter": adapter.source_adapter,
                "source_version": adapter.source_version,
            }
        )
    return prepared


def build_replay_delta_records(
    *,
    c2_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    subscription: Mapping[str, Any],
    baseline_rows: Sequence[Mapping[str, Any]],
    replay_rows: Sequence[Mapping[str, Any]],
    expected_labels: Sequence[str] | None = None,
    source_adapter: str,
    source_version: str | None,
) -> list[dict[str, Any]]:
    expected = list(expected_labels or build_full_day_minute_labels())
    baseline_by_label = rows_by_minute_label(baseline_rows)
    replay_by_label = rows_by_minute_label(replay_rows)
    delta_records: list[dict[str, Any]] = []
    for label in expected:
        replay_row = replay_by_label.get(label)
        if replay_row is None:
            continue
        baseline_row = baseline_by_label.get(label)
        if baseline_row is None:
            delta_kind = "baseline_missing"
        elif minute_values_differ(baseline_row, replay_row):
            delta_kind = "replay_diff"
        else:
            continue
        delta_records.append(
            build_minute_delta_record(
                c2_run_id=c2_run_id,
                source_condition_run_id=source_condition_run_id,
                for_trade_date=for_trade_date,
                subscription=subscription,
                replay_row=replay_row,
                baseline_row=baseline_row,
                minute_label_value=label,
                delta_kind=delta_kind,
                source_adapter=source_adapter,
                source_version=source_version,
            )
        )
    return delta_records


def build_minute_delta_record(
    *,
    c2_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    subscription: Mapping[str, Any],
    replay_row: Mapping[str, Any],
    baseline_row: Mapping[str, Any] | None,
    minute_label_value: str,
    delta_kind: str,
    source_adapter: str,
    source_version: str | None,
) -> dict[str, Any]:
    asset_kind = str(subscription["asset_kind"])
    identity_key = str(subscription["identity_key"])
    trade_date = str(replay_row.get("trade_date") or for_trade_date)
    bar_time = replay_row.get("bar_time") or timestamp_for_label(for_trade_date, minute_label_value)
    delta_key = deterministic_c2_delta_key(
        c2_run_id=c2_run_id,
        identity_key=identity_key,
        trade_date=trade_date,
        bar_time=bar_time,
    )
    replay_diff = build_replay_diff_json(
        c2_run_id=c2_run_id,
        baseline_row=baseline_row,
        replay_row=replay_row,
        delta_kind=delta_kind,
        replay_source_adapter=source_adapter,
        source_trade_date=trade_date,
        source_bar_time=bar_time,
        c2_delta_key=delta_key,
    )
    return {
        "run_id": c2_run_id,
        "subscription_id": subscription.get("subscription_id"),
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "trade_date": trade_date,
        "bar_time": bar_time,
        "minute_label": minute_label_value,
        f"{asset_kind}_identity_key": identity_key,
        "identity_key": identity_key,
        "exchange": subscription.get("exchange"),
        "code": subscription.get("code"),
        "display_code": subscription.get("display_code") or subscription.get("code"),
        "name": subscription.get("name"),
        "open": replay_row.get("open"),
        "high": replay_row.get("high"),
        "low": replay_row.get("low"),
        "close": replay_row.get("close"),
        "volume": replay_row.get("volume"),
        "amount": replay_row.get("amount"),
        "source_adapter": source_adapter,
        "source_version": source_version,
        "quality_status": "passed",
        "is_previous_day_preload": False,
        "source_scope_ids": list(subscription.get("source_scope_ids") or []),
        "source_condition_pool_ids": list(subscription.get("source_condition_pool_ids") or []),
        "raw_json": {
            "stage": "N3-C2",
            "metric_scope": CLOSED_30M_METRIC_SCOPE,
            "c2_run_id": c2_run_id,
            "c2_delta_key": delta_key,
            "delta_kind": delta_kind,
            "baseline_run_id": baseline_row.get("run_id") if baseline_row else None,
            "baseline_bar_id": baseline_row.get("bar_id") if baseline_row else None,
            "source_trade_date": trade_date,
            "source_bar_time": stringify_value(bar_time),
            "replay_source_adapter": source_adapter,
            "replay_diff_json": replay_diff,
            "writes_outbox": False,
            "mootdx_batch_attempt": subscription.get("mootdx_batch_attempt"),
        },
    }


def build_closed_30m_summary_records(
    *,
    c2_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_today_minute_run_ids: Sequence[str],
    for_trade_date: str,
    subscription: Mapping[str, Any],
    baseline_rows: Sequence[Mapping[str, Any]],
    delta_rows: Sequence[Mapping[str, Any]],
    fetch_error: str | None = None,
) -> list[dict[str, Any]]:
    effective_by_label = rows_by_minute_label(baseline_rows)
    effective_by_label.update(rows_by_minute_label(delta_rows))
    asset_kind = str(subscription["asset_kind"])
    identity_key = str(subscription["identity_key"])
    output: list[dict[str, Any]] = []
    for bucket_id, start_time, end_time in BUCKET_SPECS:
        labels = minute_labels_for_range(start_time, end_time)
        bucket_rows = [effective_by_label[label] for label in labels if label in effective_by_label]
        actual_count = len(bucket_rows)
        missing_count = len(labels) - actual_count
        if fetch_error:
            closed_status = "failed"
            quality_status = "failed"
        elif actual_count == 0:
            closed_status = "missing"
            quality_status = "missing"
        elif missing_count == 0:
            closed_status = "closed"
            quality_status = "passed"
        else:
            closed_status = "partial"
            quality_status = "partial"
        values = bucket_ohlcva(bucket_rows)
        source_ids = [
            int(row["bar_id"])
            for row in bucket_rows
            if row.get("bar_id") is not None and str(row.get("run_id") or "") != c2_run_id
        ]
        resolved_trace = [
            build_resolved_minute_trace(
                row,
                c2_run_id=c2_run_id,
                identity_key=identity_key,
            )
            for row in bucket_rows
        ]
        replay_diff = {
            "missing_labels": [label for label in labels if label not in effective_by_label],
            "delta_labels": [
                label
                for label in labels
                if label in effective_by_label and str((effective_by_label[label].get("raw_json") or {}).get("metric_scope") or "") == CLOSED_30M_METRIC_SCOPE
            ],
            "source_minute_refs": resolved_trace,
            "fetch_error": fetch_error,
        }
        output.append(
            {
                "run_id": c2_run_id,
                "source_condition_run_id": source_condition_run_id,
                "source_subscription_run_id": source_subscription_run_id,
                "source_today_minute_run_ids": list(source_today_minute_run_ids),
                "for_trade_date": for_trade_date,
                "trade_date": for_trade_date,
                "asset_kind": asset_kind,
                f"{asset_kind}_identity_key": identity_key,
                "identity_key": identity_key,
                "exchange": subscription.get("exchange"),
                "code": subscription.get("code"),
                "display_code": subscription.get("display_code") or subscription.get("code"),
                "name": subscription.get("name"),
                "bucket_id": bucket_id,
                "bucket_start": timestamp_for_label(for_trade_date, start_time.strftime("%H:%M")),
                "bucket_end": timestamp_for_label(for_trade_date, end_time.strftime("%H:%M")),
                "expected_minute_count": len(labels),
                "actual_minute_count": actual_count,
                "missing_minute_count": missing_count,
                "open": values["open"],
                "high": values["high"],
                "low": values["low"],
                "close": values["close"],
                "volume": values["volume"],
                "amount": values["amount"],
                "closed_status": closed_status,
                "quality_status": quality_status,
                "source_minute_bar_ids": source_ids,
                "replay_diff_json": replay_diff,
                "raw_json": {
                    "stage": "N3-C2",
                    "metric_scope": CLOSED_30M_METRIC_SCOPE,
                    "c2_run_id": c2_run_id,
                    "subscription_id": subscription.get("subscription_id"),
                    "resolved_minute_trace": resolved_trace,
                    "source_minute_trace_policy": "source_minute_bar_ids stores C1 persisted bar_ids; C2 delta minutes are represented by deterministic c2_delta_key until bar_id is assigned after insert.",
                    "writes_outbox": False,
                    "minute_bar_closed_event_deferred_to": "N3-C3",
                    "mootdx_batch_attempt": subscription.get("mootdx_batch_attempt"),
                },
            }
        )
    return output


def summarize_execute_rows(
    *,
    c2_run_id: str,
    minute_delta_rows: Mapping[str, int],
    summary_rows: Mapping[str, int],
    summary_status: Mapping[str, int] | Counter[str],
    quality_rows: int,
    outbox_rows_for_c2_run: int,
) -> dict[str, Any]:
    minute_by_asset = {asset_kind: int(minute_delta_rows.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}
    summary_by_asset = {asset_kind: int(summary_rows.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}
    return {
        "c2_run_id": c2_run_id,
        "minute_delta_rows": {**minute_by_asset, "total": sum(minute_by_asset.values())},
        "summary_rows": {**summary_by_asset, "total": sum(summary_by_asset.values())},
        "summary_status": {
            "closed": int(summary_status.get("closed") or 0),
            "partial": int(summary_status.get("partial") or 0),
            "missing": int(summary_status.get("missing") or 0),
            "failed": int(summary_status.get("failed") or 0),
        },
        "quality_rows": int(quality_rows),
        "outbox_rows_for_c2_run": int(outbox_rows_for_c2_run),
        "side_effects": {
            "writes_outbox": False,
            "consumes_outbox": False,
            "writes_inbox": False,
            "starts_worker": False,
            "enters_n4_n5_n6": False,
        },
    }


def expected_summary_rows_from_contract(contract: Mapping[str, Any]) -> dict[str, int]:
    expected = ((contract.get("closed_30m_summary_contract") or {}).get("expected_summary_rows") or {})
    if not expected:
        raise Closed30mReplayExecuteError(
            "N3-C2 blocked: closed_30m_summary_contract.expected_summary_rows is required"
        )
    return {asset_kind: int(expected.get(asset_kind) or 0) for asset_kind in (*ASSET_KINDS, "total")}


def validate_generated_summary_rows(row_summary: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    expected = expected_summary_rows_from_contract(contract)
    actual = row_summary.get("summary_rows") or {}
    mismatches = {
        asset_kind: {"expected": expected[asset_kind], "actual": int(actual.get(asset_kind) or 0)}
        for asset_kind in (*ASSET_KINDS, "total")
        if int(actual.get(asset_kind) or 0) != expected[asset_kind]
    }
    if mismatches:
        raise Closed30mReplayExecuteError(f"N3-C2 blocked: generated summary row count mismatch: {mismatches}")


def build_c2_quality_items(
    *,
    c2_run_id: str,
    source_condition_run_id: str,
    row_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    del source_condition_run_id
    minute_rows = row_summary.get("minute_delta_rows") or {}
    summary_rows = row_summary.get("summary_rows") or {}
    status = row_summary.get("summary_status") or {}
    items = [
        c2_quality_item(
            data_domain="common",
            table_name="common_market_data_run",
            gate_code="n3_c2_closed_30m_run_completed",
            gate_name="N3-C2 run-once completed without outbox",
            severity="P0",
            status="passed",
            expected_value="writes_outbox=0",
            actual_value=f"outbox_rows={row_summary.get('outbox_rows_for_c2_run', 0)}",
            c2_run_id=c2_run_id,
        ),
        c2_quality_item(
            data_domain="common",
            table_name="stock/index/board_closed_30m_summary",
            gate_code="n3_c2_closed_30m_summary_rows_written",
            gate_name="Closed 30m summary rows written",
            severity="P0",
            status="passed" if int(summary_rows.get("total") or 0) > 0 else "failed",
            expected_value="summary_rows>0",
            actual_value=str(summary_rows.get("total") or 0),
            c2_run_id=c2_run_id,
            details={"summary_status": dict(status)},
        ),
    ]
    for asset_kind in ASSET_KINDS:
        asset_summary_count = int(summary_rows.get(asset_kind) or 0)
        items.append(
            c2_quality_item(
                data_domain=asset_kind,
                table_name=SUMMARY_TABLES[asset_kind],
                gate_code=f"n3_c2_closed_30m_{asset_kind}_summary_visible",
                gate_name=f"{asset_kind} closed 30m summary visible",
                severity="P1" if asset_summary_count == 0 else "P2",
                status="warning" if asset_summary_count == 0 else "passed",
                expected_value="summary_rows>0",
                actual_value=str(asset_summary_count),
                c2_run_id=c2_run_id,
                details={"minute_delta_rows": int(minute_rows.get(asset_kind) or 0)},
            )
        )
    if int(row_summary.get("bj_920xxx_missing") or 0) or int(status.get("missing") or 0):
        items.append(
            c2_quality_item(
                data_domain="stock",
                table_name=SUMMARY_TABLES["stock"],
                gate_code="n3_c2_closed_30m_bj_920xxx_missing_visible",
                gate_name="BJ 920xxx missing objects are explicit",
                severity="P1",
                status="warning",
                expected_value="no fabricated minute rows",
                actual_value=str(row_summary.get("bj_920xxx_missing") or status.get("missing") or 0),
                c2_run_id=c2_run_id,
            )
        )
    return items


def c2_quality_item(
    *,
    data_domain: str,
    table_name: str,
    gate_code: str,
    gate_name: str,
    severity: str,
    status: str,
    expected_value: str,
    actual_value: str,
    c2_run_id: str,
    identity_key: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if data_domain not in ALLOWED_QUALITY_DATA_DOMAINS:
        raise Closed30mReplayExecuteError(f"N3-C2 blocked: illegal quality data_domain: {data_domain}")
    merged_details = dict(details or {})
    merged_details.setdefault("metric_scope", CLOSED_30M_METRIC_SCOPE)
    merged_details.setdefault("c2_run_id", c2_run_id)
    merged_details.setdefault("asset_kind", data_domain)
    merged_details.setdefault("projection_schema_version", C2_QUALITY_SCHEMA_VERSION)
    return {
        "data_domain": data_domain,
        "layer_scope": C2_QUALITY_LAYER_SCOPE,
        "table_name": table_name,
        "gate_code": gate_code,
        "gate_name": gate_name,
        "severity": severity,
        "status": status,
        "expected_value": expected_value,
        "actual_value": actual_value,
        "identity_key": identity_key,
        "details": merged_details,
    }


def build_closed_30m_rollback_scope(c2_run_id: str) -> dict[str, Any]:
    return {
        "c2_run_id": c2_run_id,
        "delete_tables": [
            "stock_closed_30m_summary",
            "index_closed_30m_summary",
            "board_closed_30m_summary",
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
            "common_market_data_quality_item",
            "common_market_data_run",
        ],
        "precheck_no_rows": [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ],
        "preserves_c1_b1_b2_n4_n5": True,
        "writes_outbox": False,
    }


def capture_c2_execute_snapshot(dsn: str, *, c2_run_id: str) -> dict[str, Any]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return {
            "captured_at": utc_now_iso(),
            "c2_run_id": c2_run_id,
            "target_audit": fetch_target_audit(cur, c2_run_id),
        }


def fetch_c2_subscriptions(dsn: str, source_subscription_run_id: str) -> list[dict[str, Any]]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return fetch_minute_subscriptions(cur, source_subscription_run_id)


def fetch_market_data_run_row(cur: Any, run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
               prev_trade_date, mode, status, p0_count, p1_count, p2_count,
               source_scope_row_count, candidate_row_count, subscription_row_count,
               subscription_object_count, dedup_ratio, raw_json
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    return normalize_db_row(row) if row else None


def fetch_baseline_minute_rows(
    cur: Any,
    *,
    asset_kind: str,
    today_minute_run_id: str,
    identity_key: str,
    trade_date: str,
) -> list[dict[str, Any]]:
    table_name = MINUTE_FACT_TABLES[asset_kind]
    identity_column = IDENTITY_COLUMNS[asset_kind]
    cur.execute(
        f"""
        SELECT bar_id, run_id, subscription_id, source_condition_run_id, for_trade_date,
               trade_date, bar_time, {identity_column} AS identity_key,
               exchange, code, display_code, name, open, high, low, close,
               volume, amount, source_adapter, source_version, quality_status,
               is_previous_day_preload, source_scope_ids, source_condition_pool_ids,
               raw_json
        FROM {table_name}
        WHERE run_id = %s
          AND trade_date = %s
          AND {identity_column} = %s
          AND is_previous_day_preload = false
        ORDER BY bar_time
        """,
        (today_minute_run_id, trade_date, identity_key),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def write_c2_execute_transaction(
    *,
    dsn: str,
    c2_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    today_minute_run_id: str,
    for_trade_date: str,
    started_at: str,
    status: str,
    quality_counts: Mapping[str, int],
    delta_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    summary_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    quality_items: Sequence[Mapping[str, Any]],
    dry_run_plan_path: str,
    execute_contract_path: str,
    dry_run_report_path: str,
    batch_attempt: Mapping[str, Any] | None = None,
) -> None:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                insert_c2_market_data_run(
                    cur,
                    c2_run_id=c2_run_id,
                    source_condition_run_id=source_condition_run_id,
                    source_subscription_run_id=source_subscription_run_id,
                    today_minute_run_id=today_minute_run_id,
                    for_trade_date=for_trade_date,
                    started_at=started_at,
                    status="running",
                    quality_counts={"P0": 0, "P1": 0, "P2": 0},
                    source_run_row=fetch_market_data_run_row(cur, source_subscription_run_id),
                    raw_json={
                        "stage": "N3-C2",
                        "writes_outbox": False,
                        "event_outbox_written": False,
                        "dry_run_plan_path": dry_run_plan_path,
                        "execute_contract_path": execute_contract_path,
                        "dry_run_report_path": dry_run_report_path,
                        "mootdx_batch_attempt": dict(batch_attempt) if batch_attempt else None,
                    },
                )
                for asset_kind, rows in delta_rows_by_asset.items():
                    insert_minute_delta_rows(cur, asset_kind=asset_kind, rows=rows)
                for asset_kind, rows in summary_rows_by_asset.items():
                    insert_closed_summary_rows(cur, asset_kind=asset_kind, rows=rows)
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
                insert_c2_quality_items(
                    cur,
                    c2_run_id=c2_run_id,
                    source_condition_run_id=source_condition_run_id,
                    for_trade_date=for_trade_date,
                    quality_items=traced_quality_items,
                )
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
                        updated_at = now()
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        int(quality_counts.get("P0") or 0),
                        int(quality_counts.get("P1") or 0),
                        int(quality_counts.get("P2") or 0),
                        any(delta_rows_by_asset.values()) or any(summary_rows_by_asset.values()),
                        c2_run_id,
                    ),
                )


def insert_c2_market_data_run(
    cur: Any,
    *,
    c2_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    today_minute_run_id: str,
    for_trade_date: str,
    started_at: str,
    status: str,
    quality_counts: Mapping[str, int],
    source_run_row: Mapping[str, Any] | None,
    raw_json: Mapping[str, Any],
) -> None:
    source_row = dict(source_run_row or {})
    cur.execute(
        """
        INSERT INTO common_market_data_run (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          prev_trade_date, mode, status, p0_count, p1_count, p2_count,
          source_scope_row_count, candidate_row_count, subscription_row_count,
          subscription_object_count, dedup_ratio, generated_by,
          market_data_pulled, market_data_fact_written, downstream_layers_touched,
          worker_started, started_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, 'execute', %s, %s, %s, %s,
                %s, %s, %s, %s, %s, 'N3-C2-closed-30m-replay-execute',
                false, false, false, false, %s, %s)
        """,
        (
            c2_run_id,
            source_condition_run_id,
            for_trade_date,
            str(source_row.get("source_trade_date") or source_row.get("prev_trade_date") or for_trade_date),
            str(source_row.get("prev_trade_date") or source_row.get("source_trade_date") or for_trade_date),
            status,
            int(quality_counts.get("P0") or 0),
            int(quality_counts.get("P1") or 0),
            int(quality_counts.get("P2") or 0),
            int(source_row.get("source_scope_row_count") or 0),
            int(source_row.get("candidate_row_count") or 0),
            int(source_row.get("subscription_row_count") or 0),
            int(source_row.get("subscription_object_count") or 0),
            source_row.get("dedup_ratio"),
            started_at,
            Jsonb(
                json_safe(
                    {
                        **dict(raw_json),
                        "source_subscription_run_id": source_subscription_run_id,
                        "source_today_minute_run_ids": [today_minute_run_id],
                    }
                )
            ),
        ),
    )


def insert_minute_delta_rows(cur: Any, *, asset_kind: str, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    table_name = MINUTE_FACT_TABLES[asset_kind]
    identity_column = IDENTITY_COLUMNS[asset_kind]
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
    values = []
    for row in rows:
        values.append(
            (
                row["run_id"],
                row.get("subscription_id"),
                row["source_condition_run_id"],
                row["for_trade_date"],
                row["trade_date"],
                row["bar_time"],
                row["identity_key"],
                row.get("exchange"),
                row.get("code"),
                row.get("display_code"),
                row.get("name"),
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("volume"),
                row.get("amount"),
                row.get("source_adapter"),
                row.get("source_version"),
                row.get("quality_status") or "passed",
                False,
                list(row.get("source_scope_ids") or []),
                list(row.get("source_condition_pool_ids") or []),
                Jsonb(json_safe(row.get("raw_json") or {})),
            )
        )
    cur.executemany(
        f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        values,
    )
    return len(values)


def insert_closed_summary_rows(cur: Any, *, asset_kind: str, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    table_name = SUMMARY_TABLES[asset_kind]
    identity_column = IDENTITY_COLUMNS[asset_kind]
    columns = (
        "run_id",
        "source_condition_run_id",
        "source_subscription_run_id",
        "source_today_minute_run_ids",
        "for_trade_date",
        "trade_date",
        "asset_kind",
        identity_column,
        "exchange",
        "code",
        "display_code",
        "name",
        "bucket_id",
        "bucket_start",
        "bucket_end",
        "expected_minute_count",
        "actual_minute_count",
        "missing_minute_count",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "closed_status",
        "quality_status",
        "source_minute_bar_ids",
        "replay_diff_json",
        "raw_json",
    )
    values = []
    for row in rows:
        values.append(
            (
                row["run_id"],
                row["source_condition_run_id"],
                row["source_subscription_run_id"],
                list(row["source_today_minute_run_ids"]),
                row["for_trade_date"],
                row["trade_date"],
                asset_kind,
                row["identity_key"],
                row.get("exchange"),
                row.get("code"),
                row.get("display_code"),
                row.get("name"),
                row["bucket_id"],
                row["bucket_start"],
                row["bucket_end"],
                row["expected_minute_count"],
                row["actual_minute_count"],
                row["missing_minute_count"],
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("volume"),
                row.get("amount"),
                row["closed_status"],
                row["quality_status"],
                list(row.get("source_minute_bar_ids") or []),
                Jsonb(json_safe(row.get("replay_diff_json") or {})),
                Jsonb(json_safe(row.get("raw_json") or {})),
            )
        )
    cur.executemany(
        f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        values,
    )
    return len(values)


def insert_c2_quality_items(
    cur: Any,
    *,
    c2_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
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
        data_domain = str(item.get("data_domain") or "common")
        if data_domain not in ALLOWED_QUALITY_DATA_DOMAINS:
            raise Closed30mReplayExecuteError(f"N3-C2 blocked: illegal quality data_domain: {data_domain}")
        layer_scope = str(item.get("layer_scope") or C2_QUALITY_LAYER_SCOPE)
        if layer_scope != C2_QUALITY_LAYER_SCOPE:
            raise Closed30mReplayExecuteError(f"N3-C2 blocked: illegal quality layer_scope: {layer_scope}")
        details = dict(item.get("details") or {})
        details.setdefault("metric_scope", CLOSED_30M_METRIC_SCOPE)
        details.setdefault("c2_run_id", c2_run_id)
        details.setdefault("projection_schema_version", C2_QUALITY_SCHEMA_VERSION)
        rows.append(
            (
                c2_run_id,
                source_condition_run_id,
                for_trade_date,
                for_trade_date,
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
        rows,
    )
    return len(rows)


def rows_by_minute_label(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        label = str(row.get("minute_label") or minute_label(row.get("bar_time")) or "")
        if label:
            output[label] = row
    return output


def minute_label(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(ASIA_SHANGHAI).strftime("%H:%M")
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(ASIA_SHANGHAI).strftime("%H:%M")
    except ValueError:
        pass
    if len(text) >= 5 and text[-5:-3].isdigit() and text[-2:].isdigit() and text[-3] == ":":
        return text[-5:]
    if len(text) >= 16 and text[11:16].replace(":", "").isdigit():
        return text[11:16]
    return None


def timestamp_for_label(trade_date: str, label: str) -> str:
    day = f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
    return f"{day} {label}:00+08:00"


def minute_labels_for_range(start_time: time, end_time: time) -> list[str]:
    start = start_time.hour * 60 + start_time.minute
    end = end_time.hour * 60 + end_time.minute
    return [f"{minute // 60:02d}:{minute % 60:02d}" for minute in range(start, end + 1)]


def minute_values_differ(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    for field in ("open", "high", "low", "close", "volume", "amount"):
        if decimal_or_none(left.get(field)) != decimal_or_none(right.get(field)):
            return True
    return False


def build_replay_diff_json(
    *,
    c2_run_id: str,
    baseline_row: Mapping[str, Any] | None,
    replay_row: Mapping[str, Any],
    delta_kind: str,
    replay_source_adapter: str,
    source_trade_date: str,
    source_bar_time: Any,
    c2_delta_key: str,
    source_error: str | None = None,
) -> dict[str, Any]:
    diff_fields: list[str] = []
    changed_values = {}
    for field in ("open", "high", "low", "close", "volume", "amount"):
        if baseline_row is None:
            if replay_row.get(field) is not None:
                diff_fields.append(field)
            continue
        left = decimal_or_none(baseline_row.get(field))
        right = decimal_or_none(replay_row.get(field))
        if left != right:
            diff_fields.append(field)
            changed_values[field] = {
                "baseline": str(left) if left is not None else None,
                "replay": str(right) if right is not None else None,
            }
    return {
        "c2_run_id": c2_run_id,
        "baseline_run_id": baseline_row.get("run_id") if baseline_row else None,
        "replay_source_adapter": replay_source_adapter,
        "compare_key": list(C2_REPLAY_COMPARE_KEY),
        "tolerance": dict(C2_REPLAY_TOLERANCE),
        "delta_kind": delta_kind,
        "baseline_bar_id": baseline_row.get("bar_id") if baseline_row else None,
        "c2_delta_bar_id": None,
        "c2_delta_key": c2_delta_key,
        "source_error": source_error,
        "replay_row_hash": stable_row_hash(replay_row),
        "baseline_row_hash": stable_row_hash(baseline_row) if baseline_row else None,
        "diff_fields": diff_fields,
        "changed_values": changed_values,
        "source_trade_date": source_trade_date,
        "source_bar_time": stringify_value(source_bar_time),
    }


def deterministic_c2_delta_key(
    *,
    c2_run_id: str,
    identity_key: str,
    trade_date: str,
    bar_time: Any,
) -> str:
    payload = {
        "c2_run_id": c2_run_id,
        "identity_key": identity_key,
        "trade_date": trade_date,
        "bar_time": stringify_value(bar_time),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"c2_delta:{digest}"


def stable_row_hash(row: Mapping[str, Any] | None) -> str | None:
    if row is None:
        return None
    payload = {
        "trade_date": row.get("trade_date"),
        "bar_time": stringify_value(row.get("bar_time")),
        "open": stringify_value(row.get("open")),
        "high": stringify_value(row.get("high")),
        "low": stringify_value(row.get("low")),
        "close": stringify_value(row.get("close")),
        "volume": stringify_value(row.get("volume")),
        "amount": stringify_value(row.get("amount")),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_resolved_minute_trace(
    row: Mapping[str, Any],
    *,
    c2_run_id: str,
    identity_key: str,
) -> dict[str, Any]:
    raw = row.get("raw_json") or {}
    is_c2_delta = str(row.get("run_id") or "") == c2_run_id or str(raw.get("metric_scope") or "") == CLOSED_30M_METRIC_SCOPE
    return {
        "source_kind": "C2_delta" if is_c2_delta else "C1_baseline",
        "run_id": row.get("run_id"),
        "bar_id": row.get("bar_id"),
        "c2_delta_key": raw.get("c2_delta_key") if is_c2_delta else None,
        "identity_key": row.get("identity_key") or identity_key,
        "trade_date": row.get("trade_date"),
        "bar_time": stringify_value(row.get("bar_time")),
        "minute_label": row.get("minute_label") or minute_label(row.get("bar_time")),
    }


def stringify_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def bucket_ohlcva(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"open": None, "high": None, "low": None, "close": None, "volume": None, "amount": None}
    sorted_rows = sorted(rows, key=lambda row: str(row.get("minute_label") or minute_label(row.get("bar_time")) or ""))
    highs = [decimal_or_none(row.get("high")) for row in sorted_rows if decimal_or_none(row.get("high")) is not None]
    lows = [decimal_or_none(row.get("low")) for row in sorted_rows if decimal_or_none(row.get("low")) is not None]
    volumes = [decimal_or_none(row.get("volume")) for row in sorted_rows if decimal_or_none(row.get("volume")) is not None]
    amounts = [decimal_or_none(row.get("amount")) for row in sorted_rows if decimal_or_none(row.get("amount")) is not None]
    return {
        "open": sorted_rows[0].get("open"),
        "high": max(highs) if highs else None,
        "low": min(lows) if lows else None,
        "close": sorted_rows[-1].get("close"),
        "volume": sum(volumes, Decimal("0")) if volumes else None,
        "amount": sum(amounts, Decimal("0")) if amounts else None,
    }


def render_c2_execute_markdown(report: Mapping[str, Any]) -> str:
    write = report.get("write_result") or {}
    quality = report.get("quality") or {}
    return "\n".join(
        [
            "# N3-C2 Closed 30m Replay Execute Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- c2_run_id: `{report.get('c2_run_id')}`",
            f"- for_trade_date: `{report.get('for_trade_date')}`",
            f"- minute_delta_rows: `{(write.get('minute_delta_rows') or {}).get('total')}`",
            f"- summary_rows: `{(write.get('summary_rows') or {}).get('total')}`",
            f"- summary_status: `{write.get('summary_status')}`",
            f"- quality P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
            f"- outbox_rows_for_c2_run: `{write.get('outbox_rows_for_c2_run')}`",
            f"- rollback_sql_path: `{(report.get('paths') or {}).get('rollback_sql_path')}`",
            "",
            "Boundary: no common_event_outbox write, no inbox/checkpoint consumption, no N4/N5/N6, no worker.",
        ]
    )


def build_c2_business_rollback_sql(c2_run_id: str) -> str:
    escaped = c2_run_id.replace("'", "''")
    return f"""-- N3-C2 closed minute / closed 30m business rollback.
-- Scope: {escaped}
DO $$
DECLARE
  v_c2_run_id TEXT := '{escaped}';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_run_id = v_c2_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2 rollback: common_event_outbox has % rows for %', v_count, v_c2_run_id;
  END IF;
  SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = v_c2_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2 rollback: common_event_inbox has % rows for %', v_count, v_c2_run_id;
  END IF;
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_c2_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing C2 rollback: common_event_consumer_checkpoint references % in % rows', v_c2_run_id, v_count;
  END IF;
END $$;

DELETE FROM stock_closed_30m_summary WHERE run_id = '{escaped}';
DELETE FROM index_closed_30m_summary WHERE run_id = '{escaped}';
DELETE FROM board_closed_30m_summary WHERE run_id = '{escaped}';

DELETE FROM stock_minute_bar_1m WHERE run_id = '{escaped}' AND is_previous_day_preload = false;
DELETE FROM index_minute_bar_1m WHERE run_id = '{escaped}' AND is_previous_day_preload = false;
DELETE FROM board_minute_bar_1m WHERE run_id = '{escaped}' AND is_previous_day_preload = false;

DELETE FROM common_market_data_quality_item WHERE run_id = '{escaped}';
DELETE FROM common_market_data_run WHERE run_id = '{escaped}';
"""
