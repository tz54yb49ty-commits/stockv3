"""Read-only N3-B1 board snapshot readiness probe.

The probe checks whether TDX 881xxx board snapshot data has advanced to the
requested trade date before a B1 fact-only retry is considered. It reads only
N3 subscription control rows and writes only the requested JSON artifact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import socket
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.market.realtime_snapshot_execute import (
    ASIA_SHANGHAI,
    BoardMarketDataAdapter,
    first_present,
    frame_to_records,
    parse_datetime_like,
    parse_tdx_record_datetime,
)


DEFAULT_BOARD_SNAPSHOT_PROBE_JSON_PATH = "docs/N3_B1_board_snapshot_probe_20260528.json"
BOARD_SUBSCRIPTION_COUNT_SQL = """
SELECT count(*)::bigint AS row_count
FROM common_market_data_subscription
WHERE run_id = %s
  AND asset_kind = 'board'
  AND required_data_kind = 'realtime_daily_snapshot'
"""
BOARD_SUBSCRIPTION_SQL = """
SELECT subscription_id, run_id, source_condition_run_id, for_trade_date,
       source_trade_date, prev_trade_date, asset_kind, identity_key, exchange,
       code, display_code, name, required_data_kind, data_trade_date, raw_json
FROM common_market_data_subscription
WHERE run_id = %s
  AND asset_kind = 'board'
  AND required_data_kind = 'realtime_daily_snapshot'
ORDER BY identity_key
"""


def run_board_snapshot_probe(
    *,
    dsn: str,
    run_id: str,
    limit: int = 10,
    timeout_seconds: int = 30,
    json_output_path: str = DEFAULT_BOARD_SNAPSHOT_PROBE_JSON_PATH,
    adapter: Any | None = None,
) -> dict[str, Any]:
    """Run a read-only board snapshot probe and write the JSON report."""

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_seconds)
    try:
        subscriptions, total_available, trade_date = fetch_board_realtime_snapshot_subscriptions(
            dsn=dsn,
            run_id=run_id,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
        report = build_board_snapshot_probe_report(
            run_id=run_id,
            trade_date=trade_date or "",
            subscriptions=subscriptions,
            adapter=adapter or BoardMarketDataAdapter(),
            limit=limit,
            timeout_seconds=timeout_seconds,
            total_available=total_available,
        )
        write_json(json_output_path, report)
        return report
    finally:
        socket.setdefaulttimeout(old_timeout)


def fetch_board_realtime_snapshot_subscriptions(
    *,
    dsn: str,
    run_id: str,
    limit: int,
    timeout_seconds: int,
) -> tuple[list[dict[str, Any]], int, str | None]:
    """Read board realtime snapshot subscriptions for the run.

    The connection is opened read-only and the query touches only
    ``common_market_data_subscription``.
    """

    if limit < 0:
        raise ValueError("--limit must be >= 0")
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=timeout_seconds,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(BOARD_SUBSCRIPTION_COUNT_SQL, (run_id,))
        total_available = int(cur.fetchone()["row_count"])
        sql = BOARD_SUBSCRIPTION_SQL
        params: tuple[Any, ...] = (run_id,)
        if limit > 0:
            sql += "\nLIMIT %s"
            params = (run_id, limit)
        cur.execute(sql, params)
        rows = [normalize_db_row(row) for row in cur.fetchall()]
    trade_dates = sorted({str(row.get("for_trade_date") or "") for row in rows if row.get("for_trade_date")})
    return rows, total_available, trade_dates[0] if len(trade_dates) == 1 else (trade_dates[0] if trade_dates else None)


def build_board_snapshot_probe_report(
    *,
    run_id: str,
    trade_date: str,
    subscriptions: Sequence[Mapping[str, Any]],
    adapter: Any,
    limit: int,
    timeout_seconds: int,
    total_available: int | None = None,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("--limit must be >= 0")
    selected = select_probe_subscriptions(subscriptions, limit=limit)
    samples = [probe_one_board_subscription(row, adapter=adapter, trade_date=trade_date) for row in selected]
    summary = summarize_probe_samples(samples, total_available=total_available if total_available is not None else len(subscriptions))
    probe_status = "BLOCKED" if not trade_date or not selected else ("READY_FOR_B1_RETRY" if summary["all_ready"] else "WAIT_MARKET_DATA")
    return {
        "stage": "N3-B1-board-snapshot-probe",
        "layer_role": "N3_market_data",
        "mode": "read_only_probe",
        "probe_status": probe_status,
        "generated_at": utc_now_iso(),
        "run_id": run_id,
        "trade_date": trade_date,
        "limit": limit,
        "timeout_seconds": timeout_seconds,
        "summary": summary,
        "samples": samples,
        "side_effects": {
            "database_written": False,
            "common_market_data_run_modified": False,
            "common_event_outbox_written": False,
            "common_event_inbox_written": False,
            "common_event_consumer_checkpoint_written": False,
            "b1_retry_executed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def select_probe_subscriptions(rows: Sequence[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    if limit < 0:
        raise ValueError("--limit must be >= 0")
    selected = list(rows) if limit == 0 else list(rows)[:limit]
    return [dict(row) for row in selected]


def probe_one_board_subscription(
    subscription: Mapping[str, Any],
    *,
    adapter: Any,
    trade_date: str,
) -> dict[str, Any]:
    identity_key = str(subscription.get("identity_key") or "")
    code = str(subscription.get("code") or "")
    base = {
        "identity_key": identity_key,
        "code": code,
        "adapter": str(getattr(adapter, "adapter_name", adapter.__class__.__name__)),
        "returned": False,
        "snapshot_trade_date": None,
        "tail_datetime": None,
        "reason": "not_checked",
    }
    try:
        snapshot = adapter.fetch_snapshot(dict(subscription), trade_date)
    except Exception as exc:  # noqa: BLE001 - probe must record source failures, not raise.
        base.update({"reason": "adapter_exception", "error": repr(exc)})
        return base

    if snapshot is None:
        tail_probe = fetch_board_tail_probe(adapter, subscription)
        if tail_probe is not None:
            tail_datetime = tail_probe.get("tail_datetime")
            snapshot_trade_date = trade_date_from_datetime(tail_datetime)
            base.update(
                {
                    "snapshot_trade_date": snapshot_trade_date,
                    "tail_datetime": isoformat_or_none(tail_datetime),
                    "reason": "stale_tail_datetime" if snapshot_trade_date and snapshot_trade_date != trade_date else "adapter_returned_none",
                }
            )
            return base
        base["reason"] = "adapter_returned_none"
        return base

    snapshot_time = first_present(snapshot, "snapshot_time", "snapshot_datetime", "datetime", "time")
    parsed = parse_datetime_like(snapshot_time)
    snapshot_trade_date = trade_date_from_datetime(parsed)
    base.update(
        {
            "returned": True,
            "snapshot_trade_date": snapshot_trade_date,
            "tail_datetime": isoformat_or_none(parsed),
            "reason": "ready" if snapshot_trade_date == trade_date else "stale_snapshot_trade_date",
        }
    )
    if parsed is None:
        base["reason"] = "missing_snapshot_time"
    return base


def fetch_board_tail_probe(adapter: Any, subscription: Mapping[str, Any]) -> dict[str, Any] | None:
    client = getattr(adapter, "_client", None)
    if client is None or not hasattr(client, "index"):
        return None
    code = str(subscription.get("code") or "")
    try:
        frame = client.index(symbol=code, frequency=9, start=0, offset=5)
        rows = frame_to_records(frame)
    except Exception:
        return None
    if not rows:
        return None
    tail = dict(rows[-1])
    return {"tail_datetime": parse_tdx_record_datetime(tail), "raw_tail": json_safe(tail)}


def summarize_probe_samples(samples: Sequence[Mapping[str, Any]], *, total_available: int) -> dict[str, Any]:
    ready_count = sum(1 for row in samples if row.get("reason") == "ready")
    stale_count = sum(1 for row in samples if str(row.get("reason") or "").startswith("stale_"))
    missing_count = sum(1 for row in samples if row.get("reason") in {"adapter_returned_none", "missing_snapshot_time"})
    error_count = sum(1 for row in samples if row.get("reason") == "adapter_exception")
    tail_datetimes = sorted(str(row.get("tail_datetime")) for row in samples if row.get("tail_datetime"))
    total_checked = len(samples)
    return {
        "total_available": int(total_available),
        "total_checked": total_checked,
        "ready_count": ready_count,
        "missing_count": missing_count,
        "stale_count": stale_count,
        "error_count": error_count,
        "all_ready": total_checked > 0 and ready_count == total_checked,
        "earliest_tail_datetime": tail_datetimes[0] if tail_datetimes else None,
        "latest_tail_datetime": tail_datetimes[-1] if tail_datetimes else None,
    }


def trade_date_from_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(ASIA_SHANGHAI).strftime("%Y%m%d")


def isoformat_or_none(value: datetime | None) -> str | None:
    return value.astimezone(ASIA_SHANGHAI).isoformat() if value is not None else None


def normalize_db_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): json_safe(value) for key, value in dict(row).items()}


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
