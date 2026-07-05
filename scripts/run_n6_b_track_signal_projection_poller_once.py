#!/usr/bin/env python3
"""Bounded N6 B-track signal projection poller.

Consumes canonical N5 action outbox events into N6 user projection tables. The
poller is intentionally one-shot and launchd-friendly; it never updates N5
outbox status, sends notifications, writes sim/trade rows, or starts workers.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.runtime.intraday_worker_lineage import (
    DEFAULT_LINEAGE_CONFIG_PATH,
    LineageConfigError,
    load_intraday_worker_lineage_config,
)
from ashare_v3.user.projection_execute import (
    ProjectionExecuteSnapshot,
    build_card_row,
    build_projection_row,
    build_projection_run_row,
    insert_projection_run,
    insert_signal_card,
    insert_signal_projection,
)
from ashare_v3.user.projection_plan import (
    AdminUser,
    CANONICAL_EVENT_TYPES,
    CANONICAL_REQUIRED_PAYLOAD_FIELDS,
    FilterProfile,
    ProjectionEvent,
    ProjectionInputSnapshot,
    REQUIRED_ENVELOPE_FIELDS,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except Exception:  # pragma: no cover - import fallback for package contexts
    DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3")


ASIA_SHANGHAI = timezone(timedelta(hours=8))
CONSUMER_NAME = "n6_b_track_signal_projection_poller_v1"
HISTORICAL_BACKFILL_CONFIRM_TOKEN = "N6_B_TRACK_SIGNAL_HISTORICAL_BACKFILL_CONFIRMED"
DEFAULT_JSON_REPORT_PATH = "tmp/N6_b_track_signal_projection_poller_launchd_report.json"
DEFAULT_HISTORY_PATH = "tmp/N6_b_track_signal_projection_poller_history.jsonl"
DEFAULT_HISTORICAL_BACKFILL_REPORT_PATH = "tmp/N6_b_track_signal_historical_backfill_report.json"
DEFAULT_HISTORICAL_BACKFILL_HISTORY_PATH = "tmp/N6_b_track_signal_historical_backfill_history.jsonl"
TRADING_WINDOW_START = time(9, 25)
TRADING_WINDOW_END = time(15, 0)
HISTORY_CAP_LINES = 500


@dataclass
class CommitResult:
    committed: bool
    user_projection_run: int
    user_signal_projection: int
    user_signal_card: int
    common_event_inbox: int
    common_event_consumer_checkpoint: int


class PostgresBTrackProjectionRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def is_open_trade_date(self, trade_date: str) -> bool:
        with psycopg.connect(
            self.dsn,
            row_factory=dict_row,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(bool_or(is_open), false) AS is_open
                FROM common_trade_calendar
                WHERE trade_date = %s
                """,
                (trade_date,),
            )
            row = cur.fetchone()
        return bool(row and row["is_open"])

    def fetch_unconsumed_n5_action_events(self, *, trade_date: str, consumer_name: str, limit: int) -> list[dict[str, Any]]:
        with psycopg.connect(
            self.dsn,
            row_factory=dict_row,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        ) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT outbox_id,
                       event_id,
                       event_type,
                       event_schema_version,
                       trade_date,
                       asset_kind,
                       identity_key,
                       event_time,
                       source_layer,
                       source_run_id,
                       dedup_key,
                       partition_key,
                       status,
                       payload_json,
                       NULL::text AS source_display_table,
                       NULL::integer AS display_basis_id,
                       payload_json->>'source_condition_run_id' AS display_run_id,
                       COALESCE(payload_json->>'code', split_part(identity_key, ':', 3)) AS code,
                       payload_json->>'name' AS name,
                       COALESCE(payload_json->>'target_price', payload_json->>'action_target_price') AS target_price,
                       payload_json->>'current_price' AS current_price,
                       COALESCE(payload_json->>'expected_return_pct', payload_json->>'action_expected_return_pct') AS expected_return_pct,
                       COALESCE(payload_json->>'board_code', payload_json->'trace_json'->>'board_code') AS board_code,
                       COALESCE(payload_json->>'board_name', payload_json->'trace_json'->>'board_name') AS board_name
                  FROM common_event_outbox o
                 WHERE source_layer = 'N5_action'
                   AND trade_date = %s
                   AND event_type = ANY(%s)
                   AND status = 'pending'
                   AND NOT EXISTS (
                     SELECT 1
                     FROM common_event_inbox i
                     WHERE i.consumer_name = %s
                       AND i.event_id = o.event_id
                   )
                 ORDER BY event_time, outbox_id, event_id
                 LIMIT %s
                """,
                (trade_date, list(CANONICAL_EVENT_TYPES), consumer_name, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def commit_projection_events(
        self,
        *,
        events: Sequence[dict[str, Any]],
        projection_run_id: str,
        consumer_name: str,
    ) -> dict[str, Any]:
        projection_events = [_projection_event_from_row(row) for row in events]
        source_run_id = _source_action_run_id_for(projection_events)
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=10) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    admin = _fetch_admin(cur)
                    default_profile = _fetch_default_profile(cur, admin.user_id if admin else None)
                    snapshot = ProjectionExecuteSnapshot(
                        input_snapshot=ProjectionInputSnapshot(
                            table_counts={},
                            admin=admin,
                            default_profile=default_profile,
                            n5_outbox_counts={},
                            display_basis_counts={},
                            events=list(projection_events),
                        ),
                        projection_run_id=projection_run_id,
                        scoped_counts={},
                        linked_counts={},
                    )
                    run_row = build_projection_run_row(
                        projection_events,
                        {"event_summary": {"by_event_type": dict(Counter(event.event_type for event in projection_events))}},
                        projection_run_id=projection_run_id,
                        source_action_run_id=source_run_id,
                        quality_summary={"b_track_signal_projection": "passed"},
                    )
                    insert_projection_run(cur, run_row)
                    projection_count = 0
                    card_count = 0
                    inbox_count = 0
                    for event in projection_events:
                        projection_row = build_projection_row(event, projection_run_id, snapshot)
                        projection_id = insert_signal_projection(cur, projection_row)
                        card_row = build_card_row(event, projection_run_id, snapshot)
                        card_row["user_signal_projection_id"] = projection_id
                        insert_signal_card(cur, card_row)
                        _insert_inbox(cur, event, consumer_name)
                        projection_count += 1
                        card_count += 1
                        inbox_count += 1
                    _upsert_checkpoint(cur, projection_events, consumer_name)
        return {
            "committed": True,
            "user_projection_run": 1,
            "user_signal_projection": projection_count,
            "user_signal_card": card_count,
            "common_event_inbox": inbox_count,
            "common_event_consumer_checkpoint": 1 if projection_events else 0,
        }


def run_b_track_signal_projection_poller(
    *,
    repository: Any | None = None,
    dsn: str = DEFAULT_DSN,
    for_trade_date: str | None = None,
    lineage_config: str | Path = DEFAULT_LINEAGE_CONFIG_PATH,
    now: datetime | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    consumer_name: str = CONSUMER_NAME,
    max_events: int = 100,
    json_report_path: str | Path = DEFAULT_JSON_REPORT_PATH,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    write_reports: bool = False,
) -> dict[str, Any]:
    started_at = _now(now).isoformat()
    report = _base_report(started_at=started_at, for_trade_date=for_trade_date, consumer_name=consumer_name)
    try:
        effective_trade_date = for_trade_date or _load_for_trade_date(lineage_config)
    except LineageConfigError as exc:
        return _finalize(report, "BLOCKED", blockers=[str(exc)], write_reports=write_reports, json_report_path=json_report_path, history_path=history_path)
    report["for_trade_date"] = effective_trade_date

    current_time = _now(now).timetz().replace(tzinfo=None)
    if current_time < TRADING_WINDOW_START or current_time > TRADING_WINDOW_END:
        return _finalize(
            report,
            "NOOP",
            reason="outside_trading_window",
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )

    repo = repository or PostgresBTrackProjectionRepository(dsn)
    if not repo.is_open_trade_date(effective_trade_date):
        return _finalize(
            report,
            "NOOP",
            reason="trade_date_not_open",
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )

    events = list(repo.fetch_unconsumed_n5_action_events(trade_date=effective_trade_date, consumer_name=consumer_name, limit=max_events))
    report["selected_event_count"] = len(events)
    report["selected_event_ids"] = [str(event.get("event_id") or "") for event in events]
    blockers = _validate_events(events, expected_trade_date=effective_trade_date)
    if blockers:
        return _finalize(
            report,
            "BLOCKED",
            blockers=blockers,
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    if not events:
        return _finalize(
            report,
            "NOOP",
            reason="no_unconsumed_n5_action_events",
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    if not execute or not user_confirmed:
        return _finalize(
            report,
            "BLOCKED",
            blockers=["execute_requires_user_confirmed_bounded_poller"],
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )

    projection_run_id = _projection_run_id(effective_trade_date, events, _now(now))
    write_result = dict(repo.commit_projection_events(events=events, projection_run_id=projection_run_id, consumer_name=consumer_name))
    report["projection_run_id"] = projection_run_id
    report["write_result"] = write_result
    report["side_effects"].update(
        {
            "writes_database": bool(write_result.get("committed")),
            "writes_user_signal_projection": int(write_result.get("user_signal_projection") or 0) > 0,
            "writes_user_signal_card": int(write_result.get("user_signal_card") or 0) > 0,
            "writes_common_event_inbox": int(write_result.get("common_event_inbox") or 0) > 0,
            "writes_common_event_consumer_checkpoint": int(write_result.get("common_event_consumer_checkpoint") or 0) > 0,
        }
    )
    return _finalize(
        report,
        "EXECUTE_PASS",
        write_reports=write_reports,
        json_report_path=json_report_path,
        history_path=history_path,
    )


def run_b_track_signal_historical_backfill(
    *,
    repository: Any | None = None,
    dsn: str = DEFAULT_DSN,
    trade_dates: Sequence[str],
    execute: bool = False,
    confirm_token: str = "",
    consumer_name: str = CONSUMER_NAME,
    max_events_per_date: int = 10000,
    json_report_path: str | Path = DEFAULT_HISTORICAL_BACKFILL_REPORT_PATH,
    history_path: str | Path = DEFAULT_HISTORICAL_BACKFILL_HISTORY_PATH,
    write_reports: bool = False,
) -> dict[str, Any]:
    started_at = datetime.now(ASIA_SHANGHAI).isoformat()
    report = _base_report(started_at=started_at, for_trade_date=None, consumer_name=consumer_name)
    report.update(
        {
            "stage": "N6_B_TRACK_SIGNAL_HISTORICAL_BACKFILL",
            "mode": "historical_backfill",
            "trade_dates": list(trade_dates),
            "per_trade_date": [],
            "total_selected_event_count": 0,
        }
    )
    if execute and confirm_token != HISTORICAL_BACKFILL_CONFIRM_TOKEN:
        return _finalize(
            report,
            "BLOCKED",
            blockers=["invalid_historical_backfill_confirm_token"],
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    normalized_dates = [_normalize_trade_date(value) for value in trade_dates]
    bad_dates = [value for value in normalized_dates if not value]
    if bad_dates or not normalized_dates:
        return _finalize(
            report,
            "BLOCKED",
            blockers=["invalid_or_missing_backfill_trade_date"],
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    repo = repository or PostgresBTrackProjectionRepository(dsn)
    total_selected = 0
    total_write_counts = Counter()
    for trade_date in normalized_dates:
        events = list(
            repo.fetch_unconsumed_n5_action_events(
                trade_date=trade_date,
                consumer_name=consumer_name,
                limit=max_events_per_date,
            )
        )
        blockers = _validate_events(events, expected_trade_date=trade_date)
        item: dict[str, Any] = {
            "trade_date": trade_date,
            "selected_event_count": len(events),
            "selected_event_ids": [str(event.get("event_id") or "") for event in events[:20]],
            "blockers": blockers,
            "write_result": {},
        }
        total_selected += len(events)
        if blockers:
            report["per_trade_date"].append(item)
            return _finalize(
                report,
                "BLOCKED",
                blockers=[f"{trade_date}:{blocker}" for blocker in blockers],
                write_reports=write_reports,
                json_report_path=json_report_path,
                history_path=history_path,
            )
        if events and execute:
            projection_run_id = _projection_run_id(trade_date, events, datetime.now(ASIA_SHANGHAI))
            write_result = dict(
                repo.commit_projection_events(
                    events=events,
                    projection_run_id=projection_run_id,
                    consumer_name=consumer_name,
                )
            )
            item["projection_run_id"] = projection_run_id
            item["write_result"] = write_result
            for key, value in write_result.items():
                if isinstance(value, int):
                    total_write_counts[key] += int(value)
        report["per_trade_date"].append(item)
    report["total_selected_event_count"] = total_selected
    report["write_result"] = dict(total_write_counts)
    if total_selected == 0:
        return _finalize(
            report,
            "NOOP",
            reason="no_historical_n5_action_events_to_backfill",
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    if not execute:
        return _finalize(
            report,
            "PREFLIGHT_PASS",
            reason="historical_backfill_candidates_ready",
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    report["side_effects"].update(
        {
            "writes_database": bool(total_write_counts),
            "writes_user_signal_projection": total_write_counts.get("user_signal_projection", 0) > 0,
            "writes_user_signal_card": total_write_counts.get("user_signal_card", 0) > 0,
            "writes_common_event_inbox": total_write_counts.get("common_event_inbox", 0) > 0,
            "writes_common_event_consumer_checkpoint": total_write_counts.get("common_event_consumer_checkpoint", 0) > 0,
        }
    )
    return _finalize(
        report,
        "EXECUTE_PASS",
        write_reports=write_reports,
        json_report_path=json_report_path,
        history_path=history_path,
    )


def _base_report(*, started_at: str, for_trade_date: str | None, consumer_name: str) -> dict[str, Any]:
    return {
        "stage": "N6_B_TRACK_SIGNAL_PROJECTION_POLLER_ONCE",
        "result": "UNKNOWN",
        "started_at": started_at,
        "finished_at": "",
        "duration_ms": 0.0,
        "for_trade_date": for_trade_date or "",
        "consumer_name": consumer_name,
        "allowed_event_types": list(CANONICAL_EVENT_TYPES),
        "selected_event_count": 0,
        "selected_event_ids": [],
        "blockers": [],
        "reason": "",
        "side_effects": {
            "writes_database": False,
            "writes_user_signal_projection": False,
            "writes_user_signal_card": False,
            "writes_common_event_inbox": False,
            "writes_common_event_consumer_checkpoint": False,
            "updates_n5_outbox_status": False,
            "n5_outbox_consumed": False,
            "voice_mobile_push": False,
            "sim_trade": False,
            "real_trade": False,
            "worker_started": False,
        },
    }


def _finalize(
    report: dict[str, Any],
    result: str,
    *,
    reason: str = "",
    blockers: Sequence[str] | None = None,
    write_reports: bool,
    json_report_path: str | Path,
    history_path: str | Path,
) -> dict[str, Any]:
    finished = datetime.now(ASIA_SHANGHAI)
    started = datetime.fromisoformat(report["started_at"])
    report["result"] = result
    report["reason"] = reason
    report["blockers"] = list(blockers or [])
    report["finished_at"] = finished.isoformat()
    report["duration_ms"] = round(max(0.0, (finished - started).total_seconds() * 1000), 3)
    if write_reports:
        _write_json(Path(json_report_path), report)
        _append_history(Path(history_path), report)
    return report


def _validate_events(events: Sequence[Mapping[str, Any]], *, expected_trade_date: str) -> list[str]:
    blockers: list[str] = []
    for event in events:
        for field in REQUIRED_ENVELOPE_FIELDS:
            if event.get(field) in (None, ""):
                blockers.append(f"required_envelope_field_missing:{field}")
        if event.get("source_layer") != "N5_action":
            blockers.append(f"invalid_source_layer:{event.get('source_layer')}")
        if event.get("event_type") not in CANONICAL_EVENT_TYPES:
            blockers.append(f"invalid_event_type:{event.get('event_type')}")
        if str(event.get("trade_date") or "") != expected_trade_date:
            blockers.append(f"trade_date_mismatch:{event.get('event_id')}")
        payload = event.get("payload_json")
        if not isinstance(payload, Mapping):
            blockers.append("payload_json_not_object")
            continue
        for field in CANONICAL_REQUIRED_PAYLOAD_FIELDS:
            if payload.get(field) in (None, ""):
                blockers.append(f"required_payload_field_missing:{field}")
    return sorted(set(blockers))


def _projection_event_from_row(row: Mapping[str, Any]) -> ProjectionEvent:
    payload = row.get("payload_json")
    if isinstance(payload, str):
        payload = json.loads(payload)
    return ProjectionEvent(
        outbox_id=int(row.get("outbox_id") or 0),
        event_id=str(row.get("event_id") or ""),
        event_type=str(row.get("event_type") or ""),
        event_schema_version=str(row.get("event_schema_version") or ""),
        trade_date=str(row.get("trade_date") or ""),
        asset_kind=str(row.get("asset_kind") or ""),
        identity_key=str(row.get("identity_key") or ""),
        event_time=row.get("event_time"),
        source_layer=str(row.get("source_layer") or ""),
        source_run_id=str(row.get("source_run_id") or ""),
        dedup_key=str(row.get("dedup_key") or ""),
        partition_key=str(row.get("partition_key") or ""),
        status=str(row.get("status") or ""),
        payload_json=dict(payload or {}),
        source_display_table=row.get("source_display_table"),
        display_basis_id=row.get("display_basis_id"),
        display_run_id=row.get("display_run_id"),
        code=row.get("code"),
        name=row.get("name"),
        target_price=row.get("target_price"),
        expected_return_pct=row.get("expected_return_pct"),
        board_code=row.get("board_code"),
        board_name=row.get("board_name"),
        current_price=row.get("current_price"),
    )


def _source_action_run_id_for(events: Sequence[ProjectionEvent]) -> str:
    source_run_ids = [event.source_run_id for event in events if event.source_run_id]
    if not source_run_ids:
        return "n6_b_track_signal_projection_no_source_run"
    return source_run_ids[0] if len(set(source_run_ids)) == 1 else "n6_b_track_signal_projection_mixed_n5_runs"


def _fetch_admin(cur: psycopg.Cursor[dict[str, Any]]) -> AdminUser | None:
    cur.execute(
        """
        SELECT user_id, login_name, role, status
        FROM user_account
        WHERE login_name = 'admin'
        ORDER BY user_id
        LIMIT 1
        """
    )
    row = cur.fetchone()
    return AdminUser(**dict(row)) if row else None


def _fetch_default_profile(cur: psycopg.Cursor[dict[str, Any]], admin_user_id: int | None) -> FilterProfile | None:
    if admin_user_id is None:
        return None
    cur.execute(
        """
        SELECT user_filter_profile_id, user_id, profile_name, is_default, status
        FROM user_filter_profile
        WHERE user_id = %s
          AND is_default = true
          AND status = 'active'
        ORDER BY user_filter_profile_id
        LIMIT 1
        """,
        (admin_user_id,),
    )
    row = cur.fetchone()
    return FilterProfile(**dict(row)) if row else None


def _insert_inbox(cur: psycopg.Cursor[dict[str, Any]], event: ProjectionEvent, consumer_name: str) -> None:
    cur.execute(
        """
        INSERT INTO common_event_inbox (
            consumer_name,
            event_id,
            event_type,
            event_schema_version,
            source_layer,
            source_run_id,
            dedup_key,
            partition_key,
            payload_json,
            status,
            processed_at,
            raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'processed', now(), %s)
        ON CONFLICT (consumer_name, event_id) DO NOTHING
        """,
        (
            consumer_name,
            event.event_id,
            event.event_type,
            event.event_schema_version,
            event.source_layer,
            event.source_run_id,
            event.dedup_key,
            event.partition_key,
            Jsonb(event.payload_json),
            Jsonb({"n6_projection": "b_track_signal_projection", "outbox_status_updated": False}),
        ),
    )


def _upsert_checkpoint(cur: psycopg.Cursor[dict[str, Any]], events: Sequence[ProjectionEvent], consumer_name: str) -> None:
    if not events:
        return
    last_event = sorted(events, key=lambda event: (str(event.event_time), event.outbox_id, event.event_id))[-1]
    cur.execute(
        """
        INSERT INTO common_event_consumer_checkpoint (
            consumer_name,
            partition_key,
            source_layer,
            last_event_id,
            last_event_time,
            last_outbox_id,
            checkpoint_payload,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (consumer_name, partition_key, source_layer) DO UPDATE
        SET last_event_id = EXCLUDED.last_event_id,
            last_event_time = EXCLUDED.last_event_time,
            last_outbox_id = EXCLUDED.last_outbox_id,
            checkpoint_payload = EXCLUDED.checkpoint_payload,
            updated_at = now()
        """,
        (
            consumer_name,
            "N5_action",
            "N5_action",
            last_event.event_id,
            last_event.event_time,
            last_event.outbox_id,
            Jsonb({"event_count": len(events), "projection_policy": "n6_b_track_signal_projection"}),
        ),
    )


def _projection_run_id(for_trade_date: str, events: Sequence[Mapping[str, Any]], now: datetime) -> str:
    digest = hashlib.sha256("|".join(str(event.get("event_id") or "") for event in events).encode("utf-8")).hexdigest()[:12]
    return f"n6_b_track_signal_projection_{for_trade_date}_{now.strftime('%H%M%S')}_{digest}"


def _load_for_trade_date(lineage_config: str | Path) -> str:
    payload = load_intraday_worker_lineage_config(lineage_config)
    return str(payload["for_trade_date"])


def _normalize_trade_date(value: Any) -> str:
    text = str(value or "").strip()
    return text if len(text) == 8 and text.isdigit() else ""


def _now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(ASIA_SHANGHAI)
    return now.astimezone(ASIA_SHANGHAI) if now.tzinfo else now.replace(tzinfo=ASIA_SHANGHAI)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _append_history(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    path.write_text("\n".join(lines[-HISTORY_CAP_LINES:]) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--for-trade-date")
    parser.add_argument("--lineage-config", default=DEFAULT_LINEAGE_CONFIG_PATH)
    parser.add_argument("--consumer-name", default=CONSUMER_NAME)
    parser.add_argument("--max-events", type=int, default=100)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--history-path", default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--historical-backfill", action="store_true")
    parser.add_argument("--backfill-trade-date", action="append", default=[])
    parser.add_argument("--confirm-token", default="")
    parser.add_argument("--historical-json-report-path", default=DEFAULT_HISTORICAL_BACKFILL_REPORT_PATH)
    parser.add_argument("--historical-history-path", default=DEFAULT_HISTORICAL_BACKFILL_HISTORY_PATH)
    parser.add_argument("--max-events-per-date", type=int, default=10000)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.historical_backfill:
        report = run_b_track_signal_historical_backfill(
            dsn=args.dsn,
            trade_dates=args.backfill_trade_date,
            execute=args.execute,
            confirm_token=args.confirm_token,
            consumer_name=args.consumer_name,
            max_events_per_date=args.max_events_per_date,
            json_report_path=args.historical_json_report_path,
            history_path=args.historical_history_path,
            write_reports=True,
        )
    else:
        report = run_b_track_signal_projection_poller(
            dsn=args.dsn,
            for_trade_date=args.for_trade_date,
            lineage_config=args.lineage_config,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            consumer_name=args.consumer_name,
            max_events=args.max_events,
            json_report_path=args.json_report_path,
            history_path=args.history_path,
            write_reports=True,
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(f"result={report['result']} selected_event_count={report.get('selected_event_count', 0)}")
    return 0 if report["result"] in {"EXECUTE_PASS", "NOOP", "PREFLIGHT_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
