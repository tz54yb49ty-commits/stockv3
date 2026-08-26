"""Scoped N3 historical closed-minute source expansion runner.

This runner is intentionally narrower than the full-day replay backfill helper:
it consumes a reviewed payload containing the exact missing v4 objects and can
write only the target expansion run's N3 minute facts, run row, and quality
items.  It never writes event infrastructure and never enters N4/N5/N6.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.market.mootdx_batch_attempt import (
    MootdxBatchAttemptOutcome,
    MootdxBatchObjectTracker,
    MootdxEndpointTransportError,
    build_mootdx_minute_semantic_probe,
    is_endpoint_transport_exception,
    run_mootdx_batch_attempt,
)
from ashare_v3.market.previous_day_preload_execute import (
    bulk_upsert_minute_bars,
    utc_now_iso,
    write_json,
    write_text,
)
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from ashare_v3.market.today_minute_execute import MootdxTodayMinuteAdapter
from ashare_v3.mootdx_client import EndpointSelection, MootdxEndpointManager

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_PAYLOAD_PATH = "docs/V3_20260616_n3_historical_closed_minute_source_expansion_for_v4_metric_payload.json"
DEFAULT_REPORT_PATH = "docs/V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION_EXECUTE_REPORT.json"
DEFAULT_REPORT_MD_PATH = "docs/V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION_EXECUTE_REPORT.md"

ASSET_KINDS = ("stock", "index", "board")
EXPECTED_MISSING_BY_ASSET = {"stock": 415, "index": 13, "board": 39}
EXPECTED_ROWS_BY_ASSET = {"stock": 75115, "index": 2353, "board": 7059}
SOURCE_ADAPTER = "mootdx_scoped_historical_closed_minute_expansion"
SOURCE_VERSION = "mootdx.bars.scoped_historical_closed_minute.frequency8.offset800"


class HistoricalClosedMinuteSourceExpansionBlocked(RuntimeError):
    """Raised when scoped source expansion violates its reviewed contract."""


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require_execute_flags(*, execute: bool, user_confirmed: bool) -> None:
    """Allow plan-only by default and require both flags for execute."""

    if execute and not user_confirmed:
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            "historical closed-minute source expansion blocked: missing --user-confirmed"
        )
    if user_confirmed and not execute:
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            "historical closed-minute source expansion blocked: missing --execute"
        )


def validate_payload(payload: Mapping[str, Any]) -> None:
    for required_key in ("target_expansion_run_id", "source_condition_run_id", "source_trade_date", "for_trade_date"):
        if not payload.get(required_key):
            raise HistoricalClosedMinuteSourceExpansionBlocked(
                f"historical closed-minute source expansion blocked: missing payload field {required_key}"
            )
    source_policy = payload.get("source_policy") or {}
    if source_policy.get("stale_v1_b1_c1_reuse_allowed") is not False:
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            "historical closed-minute source expansion blocked: stale v1 B1/C1 reuse is not forbidden"
        )
    if source_policy.get("fake_realtime_snapshot_allowed") is not False:
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            "historical closed-minute source expansion blocked: fake realtime snapshot is not forbidden"
        )
    candidates = payload.get("missing_candidates") or []
    expected_candidates_by_asset, expected_rows_by_asset = _expected_scope_from_payload(payload)
    actual_candidates_by_asset = Counter(str(candidate.get("asset_kind")) for candidate in candidates)
    actual_rows_by_asset = Counter()
    for candidate in candidates:
        asset_kind = str(candidate.get("asset_kind"))
        actual_rows_by_asset[asset_kind] += int(candidate.get("expected_minute_rows") or 0)
    actual_candidates = {asset: int(actual_candidates_by_asset.get(asset, 0)) for asset in ASSET_KINDS}
    actual_rows = {asset: int(actual_rows_by_asset.get(asset, 0)) for asset in ASSET_KINDS}
    if actual_candidates != expected_candidates_by_asset:
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            f"historical closed-minute source expansion blocked: unexpected missing scope {actual_candidates}"
        )
    if actual_rows != expected_rows_by_asset:
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            f"historical closed-minute source expansion blocked: unexpected planned rows {actual_rows}"
        )
    for candidate in candidates:
        if str(candidate.get("target_expansion_run_id") or "") != str(payload.get("target_expansion_run_id") or ""):
            raise HistoricalClosedMinuteSourceExpansionBlocked(
                "historical closed-minute source expansion blocked: candidate target run mismatch"
            )
        if candidate.get("source_today_minute_run_id"):
            raise HistoricalClosedMinuteSourceExpansionBlocked(
                "historical closed-minute source expansion blocked: candidate already carries today minute lineage"
            )


def _expected_scope_from_payload(payload: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    planned = payload.get("planned_write_scope") or {}
    planned_by_asset = planned.get("planned_rows_by_asset")
    if isinstance(planned_by_asset, Mapping):
        candidates = {
            asset: int((planned_by_asset.get(asset) or {}).get("previous_day_missing_objects") or 0)
            + int((planned_by_asset.get(asset) or {}).get("current_closed_minute_missing_objects") or 0)
            for asset in ASSET_KINDS
        }
        rows = {
            asset: int((planned_by_asset.get(asset) or {}).get("combined_planned_rows") or 0)
            for asset in ASSET_KINDS
        }
        return candidates, rows
    missing = payload.get("missing_scope", {}).get("by_asset", {})
    candidates = {asset: int((missing.get(asset) or {}).get("missing_objects") or 0) for asset in ASSET_KINDS}
    rows = {
        "stock": int(planned.get("stock_minute_rows") or 0),
        "index": int(planned.get("index_minute_rows") or 0),
        "board": int(planned.get("board_minute_rows") or 0),
    }
    return candidates, rows


def _planned_total_rows(payload: Mapping[str, Any]) -> int:
    planned = payload.get("planned_write_scope") or {}
    if planned.get("total_minute_rows") is not None:
        return int(planned.get("total_minute_rows") or 0)
    planned_by_asset = planned.get("planned_rows_by_asset")
    if isinstance(planned_by_asset, Mapping):
        return sum(int((planned_by_asset.get(asset) or {}).get("combined_planned_rows") or 0) for asset in ASSET_KINDS)
    return sum(
        int(planned.get(key) or 0)
        for key in ("stock_minute_rows", "index_minute_rows", "board_minute_rows")
    )


def _parse_bar_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("+08:00") or text.endswith("+00:00"):
        return datetime.fromisoformat(text)
    if "T" in text:
        return datetime.fromisoformat(text)
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def _candidate_fetch_key(candidate: Mapping[str, Any]) -> str:
    return "|".join(
        (
            str(candidate.get("identity_key") or ""),
            str(candidate.get("required_data_kind") or ""),
            str(candidate.get("data_trade_date") or ""),
            str(candidate.get("candidate_sequence") or ""),
        )
    )


def _candidate_latest_minute(candidate: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    return str(candidate.get("latest_closed_minute") or payload.get("latest_closed_minute") or "")


def _filter_until_latest(rows: Sequence[Mapping[str, Any]], latest_closed_minute: str) -> list[dict[str, Any]]:
    latest = _parse_bar_time(latest_closed_minute)
    output: list[dict[str, Any]] = []
    for row in rows:
        bar_time = _parse_bar_time(row["bar_time"])
        comparable = bar_time
        if latest.tzinfo is not None and comparable.tzinfo is None:
            comparable = comparable.replace(tzinfo=latest.tzinfo)
        if comparable <= latest:
            item = dict(row)
            item["bar_time"] = bar_time
            output.append(item)
    output.sort(key=lambda item: _parse_bar_time(item["bar_time"]))
    return output


def build_minute_records_for_candidates(
    *,
    payload: Mapping[str, Any],
    adapter_rows_by_identity: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Build DB-ready minute rows from reviewed candidates and adapter rows."""

    expansion_run_id = str(payload["target_expansion_run_id"])
    source_condition_run_id = str(payload["source_condition_run_id"])
    for_trade_date = str(payload["for_trade_date"])
    records_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    object_results: list[dict[str, Any]] = []
    for candidate in payload.get("missing_candidates") or []:
        identity = str(candidate["identity_key"])
        asset_kind = str(candidate["asset_kind"])
        expected_count = int(candidate.get("expected_minute_rows") or payload.get("bar_count_per_object_until_latest_closed_minute") or 0)
        fetch_key = _candidate_fetch_key(candidate)
        source_rows = _filter_until_latest(
            adapter_rows_by_identity.get(fetch_key) or adapter_rows_by_identity.get(identity) or [],
            _candidate_latest_minute(candidate, payload),
        )
        status = "passed" if len(source_rows) == expected_count else "missing"
        object_results.append(
            {
                "candidate_sequence": candidate.get("candidate_sequence"),
                "asset_kind": asset_kind,
                "identity_key": identity,
                "required_data_kind": candidate.get("required_data_kind"),
                "data_trade_date": candidate.get("data_trade_date"),
                "expected_minute_rows": expected_count,
                "actual_minute_rows": len(source_rows),
                "status": status,
                "source_policy": "scoped_historical_closed_minute_backfill",
            }
        )
        for row in source_rows:
            records_by_asset.setdefault(asset_kind, []).append(
                {
                    "run_id": expansion_run_id,
                    "subscription_id": candidate.get("source_subscription_id"),
                    "source_condition_run_id": source_condition_run_id,
                    "for_trade_date": for_trade_date,
                    "trade_date": str(candidate.get("data_trade_date") or for_trade_date),
                    "bar_time": row.get("bar_time"),
                    "identity_key": identity,
                    "exchange": candidate.get("exchange"),
                    "code": candidate.get("code"),
                    "display_code": candidate.get("display_code") or candidate.get("code"),
                    "name": candidate.get("name") or identity,
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                    "source_adapter": SOURCE_ADAPTER,
                    "source_version": SOURCE_VERSION,
                    "quality_status": "passed",
                    "is_previous_day_preload": bool(candidate.get("is_previous_day_preload")),
                    "source_scope_ids": candidate.get("source_scope_ids") or [],
                    "source_condition_pool_ids": candidate.get("source_condition_pool_ids") or [],
                    "raw_json": {
                        "source_policy": "scoped_historical_closed_minute_backfill",
                        "payload_candidate_sequence": candidate.get("candidate_sequence"),
                        "required_data_kind": candidate.get("required_data_kind"),
                        "data_trade_date": candidate.get("data_trade_date"),
                        "is_previous_day_preload": bool(candidate.get("is_previous_day_preload")),
                        "target_expansion_run_id": expansion_run_id,
                        "source_subscription_run_id": candidate.get("source_subscription_run_id"),
                        "source_previous_day_minute_run_id": candidate.get("source_previous_day_minute_run_id"),
                        "source_trace": candidate.get("source_trace"),
                        "raw_payload": row.get("raw_payload"),
                        "mootdx_batch_attempt": row.get("mootdx_batch_attempt"),
                        "attempt_id": row.get("attempt_id"),
                        "endpoint_id": row.get("endpoint_id"),
                        "endpoint_host": row.get("endpoint_host"),
                        "endpoint_port": row.get("endpoint_port"),
                        "old_system_read": False,
                        "stale_v1_b1_c1_reused": False,
                        "fake_realtime_snapshot": False,
                    },
                }
            )
    return records_by_asset, object_results


def build_adapter_rows(
    *,
    payload: Mapping[str, Any],
    adapter: Any,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    candidates = list(payload.get("missing_candidates") or [])
    rows_by_identity: dict[str, list[dict[str, Any]]] = {}
    fetch_results: list[dict[str, Any]] = []
    total = len(candidates)
    for index, candidate in enumerate(candidates, start=1):
        identity = str(candidate["identity_key"])
        trade_date = str(candidate.get("data_trade_date") or payload.get("data_trade_date") or payload.get("for_trade_date"))
        if progress_callback and (index == 1 or index == total or index % max(progress_every, 1) == 0):
            progress_callback(f"historical closed-minute source expansion fetch {index}/{total} {identity}")
        try:
            fetched = adapter.fetch_minute_bars(candidate, trade_date)
            rows_by_identity[_candidate_fetch_key(candidate)] = list(fetched)
            fetch_results.append(
                {
                    "asset_kind": candidate.get("asset_kind"),
                    "identity_key": identity,
                    "required_data_kind": candidate.get("required_data_kind"),
                    "data_trade_date": trade_date,
                    "status": "fetched",
                    "row_count": len(fetched),
                    "source": SOURCE_ADAPTER,
                }
            )
        except Exception as exc:  # noqa: BLE001 - pre-write blocker evidence.
            fetch_results.append(
                {
                    "asset_kind": candidate.get("asset_kind"),
                    "identity_key": identity,
                    "required_data_kind": candidate.get("required_data_kind"),
                    "data_trade_date": trade_date,
                    "status": "failed",
                    "row_count": 0,
                    "source": SOURCE_ADAPTER,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return rows_by_identity, fetch_results


def prepare_mootdx_historical_batch(
    *,
    payload: Mapping[str, Any],
    manager: MootdxEndpointManager,
    probe: Callable[..., Mapping[str, Any]],
    client_factory: Callable[[EndpointSelection], Any] | None = None,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    MootdxBatchAttemptOutcome[Any],
]:
    outcome = run_mootdx_batch_attempt(
        manager=manager,
        batch_id=str(payload["target_expansion_run_id"]),
        probe=probe,
        client_factory=client_factory,
        required_checks=("minute_scope_sentinels",),
        fetch_batch=lambda client, selection: _prepare_complete_historical_attempt(
            payload=payload,
            adapter=MootdxTodayMinuteAdapter(client=client),
            object_tracker=MootdxBatchObjectTracker(manager, selection),
        ),
    )
    if outcome.status != "passed":
        return {}, [], outcome
    rows_by_identity, fetch_results = outcome.result
    provenance = outcome.to_provenance()
    winning = next(
        (
            dict(attempt)
            for attempt in provenance.get("attempts") or []
            if attempt.get("attempt_id") == provenance.get("winning_attempt_id")
        ),
        {},
    )
    for rows in rows_by_identity.values():
        for row in rows:
            row["mootdx_batch_attempt"] = provenance
            row["attempt_id"] = winning.get("attempt_id")
            row["endpoint_id"] = winning.get("endpoint_id")
            row["endpoint_host"] = winning.get("endpoint_host")
            row["endpoint_port"] = winning.get("endpoint_port")
    return rows_by_identity, fetch_results, outcome


def _prepare_complete_historical_attempt(
    *,
    payload: Mapping[str, Any],
    adapter: Any,
    object_tracker: MootdxBatchObjectTracker,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    rows_by_identity: dict[str, list[dict[str, Any]]] = {}
    fetch_results: list[dict[str, Any]] = []
    for candidate in payload.get("missing_candidates") or []:
        trade_date = str(candidate.get("data_trade_date") or payload.get("for_trade_date") or "")
        try:
            fetched_value = adapter.fetch_minute_bars(candidate, trade_date)
        except Exception as exc:  # noqa: BLE001 - preserve local program and contract errors.
            if is_endpoint_transport_exception(exc):
                raise MootdxEndpointTransportError(str(exc)) from exc
            raise
        fetched = list(fetched_value)
        rows_by_identity[_candidate_fetch_key(candidate)] = fetched
        rows = _filter_until_latest(
            fetched,
            _candidate_latest_minute(candidate, payload),
        )
        expected = int(
            candidate.get("expected_minute_rows")
            or payload.get("bar_count_per_object_until_latest_closed_minute")
            or 0
        )
        object_result = object_tracker.record(
            identity_key=_candidate_fetch_key(candidate),
            value=rows,
            empty=len(rows) == 0,
        )
        fetch_results.append(
            {
                "asset_kind": candidate.get("asset_kind"),
                "identity_key": candidate.get("identity_key"),
                "required_data_kind": candidate.get("required_data_kind"),
                "data_trade_date": trade_date,
                "status": (
                    "fetched"
                    if len(rows) == expected
                    else "missing"
                    if object_result.status == "empty_required_object"
                    else "partial"
                ),
                "row_count": len(rows),
                "expected_row_count": expected,
                "source": SOURCE_ADAPTER,
            }
        )
    return rows_by_identity, fetch_results


def build_historical_minute_semantic_probe(
    payload: Mapping[str, Any],
) -> Callable[..., Mapping[str, Any]]:
    candidates = list(payload.get("missing_candidates") or [])
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for candidate in candidates:
        trade_date = str(candidate.get("data_trade_date") or payload.get("for_trade_date") or "")
        grouped.setdefault(trade_date, []).append(candidate)
    probes = [
        build_mootdx_minute_semantic_probe(
            subscriptions=rows,
            trade_date=trade_date,
            adapter_factory=lambda client: MootdxTodayMinuteAdapter(client=client),
        )
        for trade_date, rows in sorted(grouped.items())
    ]

    def probe(endpoint: Any, make_client: Callable[[str], Any]) -> Mapping[str, Any]:
        results = [item(endpoint, make_client) for item in probes]
        return {
            "checks": {
                "minute_scope_sentinels": bool(results)
                and all(bool((result.get("checks") or {}).get("minute_scope_sentinels")) for result in results)
            },
            "target_trade_dates": sorted(grouped),
        }

    return probe


def _count_target_rows(cur: Any, run_id: str) -> dict[str, Any]:
    table_counts: dict[str, int] = {}
    for table in (
        "common_market_data_run",
        "common_market_data_quality_item",
        "stock_minute_bar_1m",
        "index_minute_bar_1m",
        "board_minute_bar_1m",
    ):
        cur.execute(f"SELECT count(*)::bigint AS c FROM {table} WHERE run_id = %s", (run_id,))
        table_counts[table] = int(cur.fetchone()["c"])
    cur.execute(
        """
        SELECT count(*)::bigint AS c
        FROM common_event_outbox
        WHERE source_run_id = %s OR payload_json::text LIKE %s
        """,
        (run_id, f"%{run_id}%"),
    )
    outbox = int(cur.fetchone()["c"])
    cur.execute(
        """
        SELECT count(*)::bigint AS c
        FROM common_event_inbox
        WHERE source_run_id = %s OR payload_json::text LIKE %s OR raw_json::text LIKE %s
        """,
        (run_id, f"%{run_id}%", f"%{run_id}%"),
    )
    inbox = int(cur.fetchone()["c"])
    cur.execute(
        """
        SELECT count(*)::bigint AS c
        FROM common_event_consumer_checkpoint
        WHERE checkpoint_payload::text LIKE %s
        """,
        (f"%{run_id}%",),
    )
    checkpoint = int(cur.fetchone()["c"])
    return {"table_counts": table_counts, "event_refs": {"outbox": outbox, "inbox": inbox, "checkpoint": checkpoint}}


def capture_target_counts(*, dsn: str, run_id: str) -> dict[str, Any]:
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            return _count_target_rows(cur, run_id)


def _quality_visible_missing_policy(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    policy = payload.get("quality_visible_missing_policy") or {}
    return policy if isinstance(policy, Mapping) else {}


def _quality_visible_missing_allowed(payload: Mapping[str, Any]) -> bool:
    policy = _quality_visible_missing_policy(payload)
    return bool(
        policy.get("enabled")
        and policy.get("allow_partial_complete_object_write")
        and policy.get("missing_objects_are_quality_visible_blockers")
        and policy.get("do_not_write_incomplete_minute_facts")
    )


def filter_records_to_passed_candidates(
    records_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    object_results: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    passed_sequences = {
        int(item["candidate_sequence"])
        for item in object_results
        if item.get("status") == "passed" and item.get("candidate_sequence") is not None
    }
    output: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    for asset_kind in ASSET_KINDS:
        for row in records_by_asset.get(asset_kind) or []:
            raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), Mapping) else {}
            sequence = raw_json.get("payload_candidate_sequence")
            if sequence is not None and int(sequence) in passed_sequences:
                output.setdefault(asset_kind, []).append(dict(row))
    return output


def _quality_items(payload: Mapping[str, Any], object_results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    expansion_run_id = str(payload["target_expansion_run_id"])
    counts = Counter(str(item.get("status")) for item in object_results)
    failed = [dict(item) for item in object_results if item.get("status") != "passed"]
    quality_visible_allowed = bool(failed) and _quality_visible_missing_allowed(payload)
    status = "warning" if quality_visible_allowed else ("failed" if failed else "passed")
    severity = "P1" if quality_visible_allowed else ("P0" if failed else "P1")
    items = [
        {
            "run_id": expansion_run_id,
            "source_condition_run_id": payload["source_condition_run_id"],
            "for_trade_date": payload["for_trade_date"],
            "source_trade_date": payload["source_trade_date"],
            "data_domain": "common",
            "layer_scope": "market_data_run",
            "table_name": None,
            "gate_code": "v3_20260616_historical_closed_minute_source_expansion_object_coverage",
            "gate_name": "V3 20260616 historical closed-minute source expansion object coverage",
            "severity": severity,
            "status": status,
            "expected_value": "all scoped missing source candidates have their reviewed expected minute row count",
            "actual_value": json.dumps(dict(counts), ensure_ascii=False, sort_keys=True),
            "identity_key": None,
            "details": {
                "object_status_counts": dict(counts),
                "failed_sample": failed[:30],
                "quality_visible_missing_policy": dict(_quality_visible_missing_policy(payload)),
                "stale_v1_b1_c1_reused": False,
                "fake_realtime_snapshot": False,
            },
        },
        {
            "run_id": expansion_run_id,
            "source_condition_run_id": payload["source_condition_run_id"],
            "for_trade_date": payload["for_trade_date"],
            "source_trade_date": payload["source_trade_date"],
            "data_domain": "common",
            "layer_scope": "market_data_run",
            "table_name": None,
            "gate_code": "v3_20260616_historical_closed_minute_source_expansion_source_policy",
            "gate_name": "V3 20260616 historical closed-minute source expansion source policy",
            "severity": "P1",
            "status": "passed",
            "expected_value": "approved N3 adapter only; no old system; no stale v1 B1/C1",
            "actual_value": SOURCE_ADAPTER,
            "identity_key": None,
            "details": {
                "source_adapter": SOURCE_ADAPTER,
                "source_version": SOURCE_VERSION,
                "old_system_read": False,
                "writes_outbox": False,
            },
        },
    ]
    if quality_visible_allowed:
        items.append(
            {
                "run_id": expansion_run_id,
                "source_condition_run_id": payload["source_condition_run_id"],
                "for_trade_date": payload["for_trade_date"],
                "source_trade_date": payload["source_trade_date"],
                "data_domain": "common",
                "layer_scope": "market_data_run",
                "table_name": None,
                "gate_code": "v3_20260617_source_expansion_quality_visible_missing_objects",
                "gate_name": "V3 20260617 source expansion quality-visible missing objects",
                "severity": "P1",
                "status": "warning",
                "expected_value": "missing objects are visible and incomplete minute facts are not written",
                "actual_value": json.dumps(dict(counts), ensure_ascii=False, sort_keys=True),
                "identity_key": None,
                "details": {
                    "failed_sample": failed[:30],
                    "do_not_write_incomplete_minute_facts": True,
                    "quality_visible_missing_policy": dict(_quality_visible_missing_policy(payload)),
                },
            }
        )
    batch_attempt = payload.get("mootdx_batch_attempt")
    if isinstance(batch_attempt, Mapping):
        for item in items:
            item["details"] = {
                **dict(item.get("details") or {}),
                "mootdx_batch_attempt": dict(batch_attempt),
            }
    return items


def _insert_quality_items(cur: Any, quality_items: Sequence[Mapping[str, Any]]) -> None:
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
    cur.executemany(
        f"""
        INSERT INTO common_market_data_quality_item ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        [
            tuple(Jsonb(item[column]) if column == "details" else item.get(column) for column in columns)
            for item in quality_items
        ],
    )


def _p_counts(quality_items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item.get("severity")) for item in quality_items if item.get("status") != "passed")
    return {"P0": counts.get("P0", 0), "P1": counts.get("P1", 0), "P2": counts.get("P2", 0)}


def write_expansion_to_db(
    *,
    dsn: str,
    payload: Mapping[str, Any],
    records_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    object_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expansion_run_id = str(payload["target_expansion_run_id"])
    pre_counts = capture_target_counts(dsn=dsn, run_id=expansion_run_id)
    dirty = {key: value for key, value in pre_counts["table_counts"].items() if int(value or 0) != 0}
    if dirty or any(int(v or 0) != 0 for v in pre_counts["event_refs"].values()):
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            f"historical closed-minute source expansion blocked: target run not clean {pre_counts}"
        )
    quality_items = _quality_items(payload, object_results)
    p_counts = _p_counts(quality_items)
    if p_counts["P0"]:
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            "historical closed-minute source expansion blocked: object coverage has P0 failures before DB write"
        )
    total_rows = sum(len(rows) for rows in records_by_asset.values())
    object_count = len({str(item.get("identity_key")) for item in object_results if item.get("status") == "passed"})
    with audited_n3_market_execute_connect(
        dsn,
        stage_id="v3_20260616_historical_closed_minute_source_expansion",
        source_run_id=expansion_run_id,
        row_factory=dict_row,
    ) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
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
                            %s, %s, %s, %s, 1.0, 'V3-historical-closed-minute-source-expansion',
                            true, false, false, false, now(), %s)
                    """,
                    (
                        expansion_run_id,
                        payload["source_condition_run_id"],
                        payload["for_trade_date"],
                        payload["source_trade_date"],
                        payload["source_trade_date"],
                        object_count,
                        object_count,
                        object_count,
                        object_count,
                        Jsonb(
                            {
                                "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
                                "records_planned": total_rows,
                                "writes_outbox": False,
                                "old_system_read": False,
                                "stale_v1_b1_c1_reused": False,
                                "mootdx_batch_attempt": (
                                    dict(payload["mootdx_batch_attempt"])
                                    if isinstance(payload.get("mootdx_batch_attempt"), Mapping)
                                    else None
                                ),
                            }
                        ),
                    ),
                )
                for asset_kind in ASSET_KINDS:
                    rows = list(records_by_asset.get(asset_kind) or [])
                    for offset in range(0, len(rows), 5000):
                        bulk_upsert_minute_bars(cur, asset_kind, rows[offset : offset + 5000])
                _insert_quality_items(cur, quality_items)
                cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status = 'passed',
                        p0_count = %s,
                        p1_count = %s,
                        p2_count = %s,
                        market_data_fact_written = true,
                        downstream_layers_touched = false,
                        worker_started = false,
                        finished_at = now(),
                        updated_at = now(),
                        raw_json = raw_json || %s
                    WHERE run_id = %s
                    """,
                    (
                        p_counts["P0"],
                        p_counts["P1"],
                        p_counts["P2"],
                        Jsonb(
                            {
                                "object_results_summary": {
                                    "total": len(object_results),
                                    "status_counts": dict(Counter(str(item.get("status")) for item in object_results)),
                                }
                            }
                        ),
                        expansion_run_id,
                    ),
                )
    post_counts = capture_target_counts(dsn=dsn, run_id=expansion_run_id)
    return {
        "pre_counts": pre_counts,
        "post_counts": post_counts,
        "quality_item_count": len(quality_items),
        "p_counts": p_counts,
        "records_planned": total_rows,
    }


def write_failed_historical_attempt_to_db(
    *,
    dsn: str,
    payload: Mapping[str, Any],
    outcome: MootdxBatchAttemptOutcome[Any],
) -> dict[str, Any]:
    expansion_run_id = str(payload["target_expansion_run_id"])
    pre_counts = capture_target_counts(dsn=dsn, run_id=expansion_run_id)
    dirty = {key: value for key, value in pre_counts["table_counts"].items() if int(value or 0) != 0}
    if dirty or any(int(value or 0) != 0 for value in pre_counts["event_refs"].values()):
        raise HistoricalClosedMinuteSourceExpansionBlocked(
            f"historical closed-minute source expansion blocked: target run not clean {pre_counts}"
        )
    provenance = outcome.to_provenance()
    candidate_count = len(payload.get("missing_candidates") or [])
    quality_items = [
        {
            "run_id": expansion_run_id,
            "source_condition_run_id": payload["source_condition_run_id"],
            "for_trade_date": payload["for_trade_date"],
            "source_trade_date": payload["source_trade_date"],
            "data_domain": "common",
            "layer_scope": "market_data_run",
            "table_name": None,
            "gate_code": "v3_20260616_historical_closed_minute_endpoint_attempt",
            "gate_name": "V3 20260616 historical closed-minute endpoint attempt",
            "severity": "P0",
            "status": "failed",
            "expected_value": "one complete endpoint attempt passes before any fact write",
            "actual_value": str(outcome.status),
            "identity_key": None,
            "details": {
                "mootdx_batch_attempt": provenance,
                "success_fact_written": False,
                "success_event_written": False,
            },
        }
    ]
    with audited_n3_market_execute_connect(
        dsn,
        stage_id="v3_20260616_historical_closed_minute_source_expansion",
        source_run_id=expansion_run_id,
        row_factory=dict_row,
    ) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO common_market_data_run (
                      run_id, source_condition_run_id, for_trade_date, source_trade_date,
                      prev_trade_date, mode, status, p0_count, p1_count, p2_count,
                      source_scope_row_count, candidate_row_count, subscription_row_count,
                      subscription_object_count, dedup_ratio, generated_by,
                      market_data_pulled, market_data_fact_written,
                      downstream_layers_touched, worker_started,
                      started_at, finished_at, raw_json
                    )
                    VALUES (%s, %s, %s, %s, %s, 'execute', 'failed', 1, 0, 0,
                            %s, %s, %s, %s, 1.0, 'V3-historical-closed-minute-source-expansion',
                            true, false, false, false, now(), now(), %s)
                    """,
                    (
                        expansion_run_id,
                        payload["source_condition_run_id"],
                        payload["for_trade_date"],
                        payload["source_trade_date"],
                        payload["source_trade_date"],
                        candidate_count,
                        candidate_count,
                        candidate_count,
                        candidate_count,
                        Jsonb(
                            {
                                "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
                                "blocked_reason": "atomic_mootdx_batch_failed_before_fact_write",
                                "writes_outbox": False,
                                "mootdx_batch_attempt": provenance,
                            }
                        ),
                    ),
                )
                _insert_quality_items(cur, quality_items)
    post_counts = capture_target_counts(dsn=dsn, run_id=expansion_run_id)
    return {
        "pre_counts": pre_counts,
        "post_counts": post_counts,
        "quality_item_count": 1,
        "p_counts": {"P0": 1, "P1": 0, "P2": 0},
    }


def format_report_markdown(report: Mapping[str, Any]) -> str:
    return (
        "# V3 20260616 N3 Historical Closed-Minute Source Expansion Report\n\n"
        f"- result: `{report.get('result')}`\n"
        f"- expansion_run_id: `{report.get('target_expansion_run_id')}`\n"
        f"- mode: `{report.get('mode')}`\n"
        f"- records_planned: `{report.get('records_planned')}`\n"
        f"- P0/P1/P2: `{report.get('P0_P1_P2')}`\n"
        f"- database_written: `{report.get('database_written')}`\n"
        f"- forbidden_scope: `{report.get('forbidden_scope')}`\n"
    )


def run_historical_closed_minute_source_expansion(
    *,
    dsn: str = DEFAULT_DSN,
    payload_path: str | Path = DEFAULT_PAYLOAD_PATH,
    json_report_path: str | Path = DEFAULT_REPORT_PATH,
    markdown_report_path: str | Path = DEFAULT_REPORT_MD_PATH,
    execute: bool = False,
    user_confirmed: bool = False,
    adapter: Any | None = None,
    endpoint_manager: MootdxEndpointManager | None = None,
    endpoint_probe: Callable[..., Mapping[str, Any]] | None = None,
    endpoint_client_factory: Callable[[EndpointSelection], Any] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> dict[str, Any]:
    require_execute_flags(execute=execute, user_confirmed=user_confirmed)
    payload = load_json(payload_path)
    validate_payload(payload)
    expansion_run_id = str(payload["target_expansion_run_id"])
    forbidden_scope = {
        "writes_outbox": False,
        "outbox_inbox_checkpoint_consumed_or_updated": False,
        "n4_executed": False,
        "n5_executed": False,
        "n6_executed": False,
        "worker_started": False,
        "old_system_read": False,
        "voice_mobile_sim_position_order_trade_touched": False,
    }
    if not execute:
        report = {
            "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
            "result": "PLAN_ONLY",
            "mode": "plan_only",
            "target_expansion_run_id": expansion_run_id,
            "payload_path": str(payload_path),
            "records_planned": _planned_total_rows(payload),
            "missing_objects": len(payload.get("missing_candidates") or []),
            "database_written": False,
            "adapter_called": False,
            "P0_P1_P2": {"P0": 0, "P1": 0, "P2": 0},
            "forbidden_scope": forbidden_scope,
        }
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_report_markdown(report))
        return report

    started_at = utc_now_iso()
    candidates_missing_control_rows = [
        {
            "asset_kind": candidate.get("asset_kind"),
            "identity_key": candidate.get("identity_key"),
            "required_data_kind": candidate.get("required_data_kind"),
            "data_trade_date": candidate.get("data_trade_date"),
        }
        for candidate in payload.get("missing_candidates") or []
        if candidate.get("subscription_control_row_present") is False
    ]
    if candidates_missing_control_rows:
        report = {
            "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
            "result": "BLOCKED",
            "blocked_reason": "subscription_control_rows_missing_before_adapter_fetch",
            "target_expansion_run_id": expansion_run_id,
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "blocking_candidate_sample": candidates_missing_control_rows[:30],
            "database_written": False,
            "adapter_called": False,
            "forbidden_scope": forbidden_scope,
        }
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_report_markdown(report))
        return report
    batch_outcome: MootdxBatchAttemptOutcome[Any] | None = None
    if adapter is None:
        adapter_rows, fetch_results, batch_outcome = prepare_mootdx_historical_batch(
            payload=payload,
            manager=endpoint_manager or MootdxEndpointManager.from_toml(),
            probe=endpoint_probe or build_historical_minute_semantic_probe(payload),
            client_factory=endpoint_client_factory,
        )
    else:
        adapter_rows, fetch_results = build_adapter_rows(
            payload=payload,
            adapter=adapter,
            progress_callback=progress_callback,
            progress_every=progress_every,
        )
    if batch_outcome is not None and batch_outcome.status != "passed":
        failure_write = write_failed_historical_attempt_to_db(
            dsn=dsn,
            payload=payload,
            outcome=batch_outcome,
        )
        report = {
            "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
            "result": "BLOCKED",
            "blocked_reason": "atomic_mootdx_batch_failed_before_db_write",
            "data_quality_status": "missing",
            "target_expansion_run_id": expansion_run_id,
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "mootdx_batch_attempt": batch_outcome.to_provenance(),
            "database_written": True,
            "failure_run_and_quality_written": True,
            "quality_item_count": failure_write["quality_item_count"],
            "P0_P1_P2": failure_write["p_counts"],
            "pre_counts": failure_write["pre_counts"],
            "post_counts": failure_write["post_counts"],
            "success_fact_written": False,
            "success_event_written": False,
            "forbidden_scope": forbidden_scope,
        }
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_report_markdown(report))
        return report
    if batch_outcome is not None:
        payload = {
            **dict(payload),
            "mootdx_batch_attempt": batch_outcome.to_provenance(),
        }
    failed_fetches = [item for item in fetch_results if item.get("status") == "failed"]
    if failed_fetches:
        report = {
            "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
            "result": "BLOCKED",
            "blocked_reason": "adapter_fetch_failed_before_db_write",
            "target_expansion_run_id": expansion_run_id,
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "fetch_status_counts": dict(Counter(str(item.get("status")) for item in fetch_results)),
            "blocking_fetch_sample": failed_fetches[:30],
            "database_written": False,
            "forbidden_scope": forbidden_scope,
        }
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_report_markdown(report))
        return report
    records_by_asset, object_results = build_minute_records_for_candidates(
        payload=payload,
        adapter_rows_by_identity=adapter_rows,
    )
    blocking_objects = [item for item in object_results if item.get("status") != "passed"]
    if blocking_objects:
        if _quality_visible_missing_allowed(payload):
            records_by_asset = filter_records_to_passed_candidates(records_by_asset, object_results)
        else:
            report = {
                "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
                "result": "BLOCKED",
                "blocked_reason": "object_minute_rows_incomplete_before_db_write",
                "target_expansion_run_id": expansion_run_id,
                "started_at": started_at,
                "finished_at": utc_now_iso(),
                "object_status_counts": dict(Counter(str(item.get("status")) for item in object_results)),
                "blocking_object_sample": blocking_objects[:30],
                "database_written": False,
                "forbidden_scope": forbidden_scope,
            }
            write_json(json_report_path, report)
            write_text(markdown_report_path, format_report_markdown(report))
            return report
    write_result = write_expansion_to_db(
        dsn=dsn,
        payload=payload,
        records_by_asset=records_by_asset,
        object_results=object_results,
    )
    report = {
        "stage": "V3_20260616_N3_HISTORICAL_CLOSED_MINUTE_SOURCE_EXPANSION",
        "result": "EXECUTE_PASS",
        "mode": "execute",
        "target_expansion_run_id": expansion_run_id,
        "payload_path": str(payload_path),
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "records_planned": write_result["records_planned"],
        "P0_P1_P2": write_result["p_counts"],
        "pre_counts": write_result["pre_counts"],
        "post_counts": write_result["post_counts"],
        "quality_item_count": write_result["quality_item_count"],
        "object_status_counts": dict(Counter(str(item.get("status")) for item in object_results)),
        "database_written": True,
        "forbidden_scope": forbidden_scope,
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_report_markdown(report))
    return report
