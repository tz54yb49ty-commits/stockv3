#!/usr/bin/env python3
"""Bounded N6 B-track signal projection poller.

Consumes canonical N5 action outbox events into N6 user projection tables. The
poller is intentionally one-shot and launchd-friendly; it never updates N5
outbox status, sends notifications, writes sim/trade rows, or starts workers.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
try:
    import fcntl
except ImportError:  # pragma: no cover - native Windows
    fcntl = None
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Sequence
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

try:
    from ashare_v3.runtime.intraday_worker_lineage import (
        DEFAULT_LINEAGE_CONFIG_PATH,
        LineageConfigError,
        load_intraday_worker_lineage_config,
    )
except ImportError:  # pragma: no cover - native Windows always passes --for-trade-date
    DEFAULT_LINEAGE_CONFIG_PATH = ""

    class LineageConfigError(RuntimeError):
        pass

    def load_intraday_worker_lineage_config(path: Any) -> dict[str, Any]:
        raise LineageConfigError("lineage_config_unavailable_on_native_windows")

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
    IndustryMembershipRow,
    N5_PROJECTION_MESSAGE_CONTRACT_HASH,
    N5_PROJECTION_MESSAGE_CONTRACT_VERSION,
    ProjectionEvent,
    ProjectionInputSnapshot,
    REQUIRED_ENVELOPE_FIELDS,
    evaluate_projection_message_contract,
    freeze_stock_industry_context,
    is_projection_message_contract_event,
    source_trade_date_for_event,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except Exception:  # pragma: no cover - import fallback for package contexts
    DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3")


ASIA_SHANGHAI = timezone(timedelta(hours=8))
CONSUMER_NAME = "n6_b_track_signal_projection_poller_v1"
SINGLETON_LOCK_PATH = "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/locks/n6_b_track_signal_projection_poller.lock"
SINGLETON_LOCK_CONTRACT_VERSION = "N6-poller-os-singleton-lock-v1"
SINGLETON_LOCK_UID = 501
SINGLETON_LOCK_GID = 20
ADVISORY_LOCK_CONTRACT_VERSION = "N6-poller-advisory-lock-v1"
ADVISORY_LOCK_KEY_MATERIAL = "N6-poller-advisory-lock-v1:n6_b_track_signal_projection_poller_v1"
ADVISORY_LOCK_KEY_MATERIAL_SHA256 = "8c393b78cccccfc1cdc8d4f598a928bae8e447ac91d52bc90b386b4424f2d316"
ADVISORY_LOCK_KEY = -8342571444709044287
ADVISORY_LOCK_SQL = "SELECT pg_try_advisory_xact_lock(%s::bigint) AS acquired"
CAS_AUTHORITY_MODES = ("internal_one_shot", "external_bounded_canary")
MAX_INTERNAL_BATCH_SIZE = 100
CHECKPOINT_PARTITION_KEY = "N5_action"
CHECKPOINT_SOURCE_LAYER = "N5_action"
HISTORICAL_BACKFILL_CONFIRM_TOKEN = "N6_B_TRACK_SIGNAL_HISTORICAL_BACKFILL_CONFIRMED"
DEFAULT_JSON_REPORT_PATH = "tmp/N6_b_track_signal_projection_poller_launchd_report.json"
DEFAULT_HISTORY_PATH = "tmp/N6_b_track_signal_projection_poller_history.jsonl"
DEFAULT_HISTORICAL_BACKFILL_REPORT_PATH = "tmp/N6_b_track_signal_historical_backfill_report.json"
DEFAULT_HISTORICAL_BACKFILL_HISTORY_PATH = "tmp/N6_b_track_signal_historical_backfill_history.jsonl"
TRADING_WINDOW_START = time(9, 25)
TRADING_WINDOW_END = time(15, 0)
HISTORY_CAP_LINES = 500
PROJECTION_MESSAGE_MARKER_FIELDS = (
    "projection_message_contract_version",
    "projection_message_contract_hash",
    "projection_message_status",
    "projection_message_not_ready_reasons",
)


@dataclass
class CommitResult:
    committed: bool
    user_projection_run: int
    user_signal_projection: int
    user_signal_card: int
    common_event_inbox: int
    common_event_consumer_checkpoint: int


class PollerBlockedError(RuntimeError):
    """Typed fail-closed boundary raised before a transaction can commit."""


class SingletonLockHeldError(RuntimeError):
    """The reviewed singleton is currently owned by another process."""


class SingletonLockContractError(RuntimeError):
    """The reviewed singleton path or metadata contract is invalid."""


@dataclass
class SingletonLockHandle:
    fd: int
    parent_fd: int
    path: Path
    metadata: dict[str, Any]

    def release(self) -> None:
        if self.fd < 0:
            return
        self.metadata["status"] = "released"
        self.metadata["released_at"] = datetime.now(ASIA_SHANGHAI).isoformat()
        _write_lock_metadata(self.fd, self.metadata)
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)
        os.close(self.parent_fd)
        self.fd = -1
        self.parent_fd = -1


@contextmanager
def acquire_singleton_lock(
    lock_path: str | Path,
    *,
    expected_path: str | Path = SINGLETON_LOCK_PATH,
    expected_uid: int = SINGLETON_LOCK_UID,
    expected_gid: int = SINGLETON_LOCK_GID,
    release_id: str = "",
    source_commit: str = "",
):
    handle = _acquire_singleton_lock(
        lock_path,
        expected_path=expected_path,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        release_id=release_id,
        source_commit=source_commit,
    )
    try:
        yield handle
    finally:
        handle.release()


def _acquire_singleton_lock(
    lock_path: str | Path,
    *,
    expected_path: str | Path,
    expected_uid: int,
    expected_gid: int,
    release_id: str,
    source_commit: str,
) -> SingletonLockHandle:
    if fcntl is None:
        raise SingletonLockContractError("posix_singleton_lock_unavailable")
    path = Path(lock_path)
    expected = Path(expected_path)
    if not path.is_absolute() or str(path) != str(expected) or path.name != expected.name:
        raise SingletonLockContractError("singleton_lock_contract_invalid")
    parent = path.parent
    try:
        parent_lstat = parent.lstat()
    except OSError as exc:
        raise SingletonLockContractError("singleton_lock_contract_invalid") from exc
    if (
        stat.S_ISLNK(parent_lstat.st_mode)
        or not stat.S_ISDIR(parent_lstat.st_mode)
        or parent.resolve(strict=True) != parent
        or stat.S_IMODE(parent_lstat.st_mode) != 0o700
        or parent_lstat.st_uid != expected_uid
        or parent_lstat.st_gid != expected_gid
    ):
        raise SingletonLockContractError("singleton_lock_contract_invalid")
    parent_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        parent_fd = os.open(parent, parent_flags)
    except OSError as exc:
        raise SingletonLockContractError("singleton_lock_contract_invalid") from exc
    fd = -1
    try:
        opened_parent = os.fstat(parent_fd)
        if (
            not stat.S_ISDIR(opened_parent.st_mode)
            or stat.S_IMODE(opened_parent.st_mode) != 0o700
            or opened_parent.st_uid != expected_uid
            or opened_parent.st_gid != expected_gid
            or (opened_parent.st_dev, opened_parent.st_ino) != (parent_lstat.st_dev, parent_lstat.st_ino)
        ):
            raise SingletonLockContractError("singleton_lock_contract_invalid")
        try:
            existing = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise SingletonLockContractError("singleton_lock_contract_invalid") from exc
        if existing is not None and (
            not stat.S_ISREG(existing.st_mode)
            or existing.st_nlink != 1
            or stat.S_IMODE(existing.st_mode) != 0o600
            or existing.st_uid != expected_uid
            or existing.st_gid != expected_gid
        ):
            raise SingletonLockContractError("singleton_lock_contract_invalid")
        try:
            fd = os.open(
                path.name,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise SingletonLockContractError("singleton_lock_contract_invalid") from exc
        _validate_lock_inode(fd, parent_fd, path.name, expected_uid=expected_uid, expected_gid=expected_gid)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SingletonLockHeldError("singleton_lock_held") from exc
        _validate_lock_inode(fd, parent_fd, path.name, expected_uid=expected_uid, expected_gid=expected_gid)
        metadata = {
            "contract_version": SINGLETON_LOCK_CONTRACT_VERSION,
            "release_id": release_id,
            "source_commit": source_commit,
            "consumer_name": CONSUMER_NAME,
            "invocation_id": str(uuid.uuid4()),
            "owner_pid": os.getpid(),
            "owner_ppid": os.getppid(),
            "process_start_identity": f"pid={os.getpid()};module_started_at={PROCESS_STARTED_AT}",
            "executable_realpath": str(Path(sys.executable).resolve()),
            "executable_sha256": _file_sha256(Path(sys.executable)),
            "argv_secret_free": True,
            "argv_sha256": _canonical_sha256(_secret_free_argv(sys.argv)),
            "acquired_at": datetime.now(ASIA_SHANGHAI).isoformat(),
            "status": "acquired",
        }
        _write_lock_metadata(fd, metadata)
        return SingletonLockHandle(fd=fd, parent_fd=parent_fd, path=path, metadata=metadata)
    except Exception:
        if fd >= 0:
            os.close(fd)
        os.close(parent_fd)
        raise


def _validate_lock_inode(fd: int, parent_fd: int, name: str, *, expected_uid: int, expected_gid: int) -> None:
    opened = os.fstat(fd)
    linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(linked.st_mode)
        or opened.st_nlink != 1
        or linked.st_nlink != 1
        or stat.S_IMODE(opened.st_mode) != 0o600
        or opened.st_uid != expected_uid
        or opened.st_gid != expected_gid
        or (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino)
    ):
        raise SingletonLockContractError("singleton_lock_contract_invalid")


def _write_lock_metadata(fd: int, metadata: Mapping[str, Any]) -> None:
    payload = _canonical_json_bytes(metadata) + b"\n"
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise SingletonLockContractError("singleton_lock_contract_invalid")
        view = view[written:]
    os.fsync(fd)


PROCESS_STARTED_AT = datetime.now(ASIA_SHANGHAI).isoformat()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _secret_free_argv(argv: Sequence[str]) -> list[str]:
    sanitized: list[str] = []
    redact_next = False
    for value in argv:
        if redact_next:
            sanitized.append("<redacted-dsn>")
            redact_next = False
        elif value == "--dsn":
            sanitized.append(value)
            redact_next = True
        elif value.startswith("--dsn="):
            sanitized.append("--dsn=<redacted-dsn>")
        else:
            sanitized.append(value)
    return sanitized


def _timestamp_cas_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _string_cas_value(value: Any) -> str | None:
    return None if value is None else str(value)


def _select_checkpoint_cas(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    consumer_name: str,
    for_update: bool,
) -> dict[str, Any]:
    query = """
        SELECT consumer_name,
               partition_key,
               source_layer,
               last_event_time,
               last_outbox_id,
               last_event_id,
               checkpoint_payload,
               updated_at
          FROM common_event_consumer_checkpoint
         WHERE consumer_name = %s
           AND partition_key = %s
           AND source_layer = %s
    """
    if for_update:
        query += " FOR UPDATE"
    cur.execute(query, (consumer_name, CHECKPOINT_PARTITION_KEY, CHECKPOINT_SOURCE_LAYER))
    row = cur.fetchone()
    if not row:
        return {
            "checkpoint_exists": False,
            "consumer_name": None,
            "partition_key": None,
            "source_layer": None,
            "last_event_time": None,
            "last_outbox_id": None,
            "last_event_id": None,
            "checkpoint_payload_sha256": None,
            "updated_at": None,
        }
    payload = row.get("checkpoint_payload")
    if not isinstance(payload, Mapping) or set(payload) != {"event_count", "projection_policy"}:
        raise PollerBlockedError("checkpoint_cas_mismatch")
    return {
        "checkpoint_exists": True,
        "consumer_name": _string_cas_value(row.get("consumer_name")),
        "partition_key": _string_cas_value(row.get("partition_key")),
        "source_layer": _string_cas_value(row.get("source_layer")),
        "last_event_time": _timestamp_cas_value(row.get("last_event_time")),
        "last_outbox_id": int(row["last_outbox_id"]) if row.get("last_outbox_id") is not None else None,
        "last_event_id": _string_cas_value(row.get("last_event_id")),
        "checkpoint_payload_sha256": _canonical_sha256(dict(payload)),
        "updated_at": _timestamp_cas_value(row.get("updated_at")),
    }


def _select_unconsumed_n5_action_events(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    trade_date: str,
    consumer_name: str,
    limit: int,
) -> list[dict[str, Any]]:
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
               CASE
                 WHEN payload_json ? 'projection_message_contract_version'
                   THEN payload_json->>'asset_code'
                 ELSE COALESCE(payload_json->>'code', split_part(identity_key, ':', 3))
               END AS code,
               CASE
                 WHEN payload_json ? 'projection_message_contract_version'
                   THEN payload_json->>'asset_name'
                 ELSE payload_json->>'name'
               END AS name,
               CASE
                 WHEN payload_json ? 'projection_message_contract_version'
                   THEN CASE payload_json->>'direction'
                     WHEN 'buy' THEN payload_json->'condition_projection_context'->'fields'->>'buy_target_price'
                     WHEN 'sell' THEN payload_json->'condition_projection_context'->'fields'->>'sell_target_price'
                     ELSE NULL
                   END
                 ELSE COALESCE(payload_json->>'target_price', payload_json->>'action_target_price')
               END AS target_price,
               payload_json->>'current_price' AS current_price,
               CASE
                 WHEN payload_json ? 'projection_message_contract_version'
                   THEN CASE payload_json->>'direction'
                     WHEN 'buy' THEN payload_json->'condition_projection_context'->'fields'->>'buy_expected_return_pct'
                     WHEN 'sell' THEN payload_json->'condition_projection_context'->'fields'->>'sell_expected_return_pct'
                     ELSE NULL
                   END
                 ELSE COALESCE(payload_json->>'expected_return_pct', payload_json->>'action_expected_return_pct')
               END AS expected_return_pct,
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


def _selected_event_cas_object(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = []
    for event in sorted(
        events,
        key=lambda row: (_timestamp_cas_value(row.get("event_time")) or "", int(row.get("outbox_id") or 0), str(row.get("event_id") or "")),
    ):
        payload = event.get("payload_json")
        if not isinstance(payload, Mapping):
            raise PollerBlockedError("selected_event_cas_mismatch")
        items.append(
            {
                "outbox_id": int(event["outbox_id"]) if event.get("outbox_id") is not None else None,
                "event_id": _string_cas_value(event.get("event_id")),
                "event_time": _timestamp_cas_value(event.get("event_time")),
                "event_type": _string_cas_value(event.get("event_type")),
                "event_schema_version": _string_cas_value(event.get("event_schema_version")),
                "trade_date": _string_cas_value(event.get("trade_date")),
                "asset_kind": _string_cas_value(event.get("asset_kind")),
                "identity_key": _string_cas_value(event.get("identity_key")),
                "source_layer": _string_cas_value(event.get("source_layer")),
                "source_run_id": _string_cas_value(event.get("source_run_id")),
                "dedup_key": _string_cas_value(event.get("dedup_key")),
                "partition_key": _string_cas_value(event.get("partition_key")),
                "status": _string_cas_value(event.get("status")),
                "payload_json_sha256": _canonical_sha256(dict(payload)),
            }
        )
    return {"event_count": len(items), "events": items}


def _cas_snapshot(checkpoint: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checkpoint_object = dict(checkpoint)
    selected_event_object = _selected_event_cas_object(events)
    return {
        "checkpoint": checkpoint_object,
        "checkpoint_cas_sha256": _canonical_sha256(checkpoint_object),
        "selected_event": selected_event_object,
        "selected_event_cas_sha256": _canonical_sha256(selected_event_object),
        "selected_event_count": len(events),
        "events": [dict(event) for event in events],
    }


class PostgresBTrackProjectionRepository:
    def __init__(self, dsn: str, *, windows_projection_contract: bool = False) -> None:
        self.dsn = dsn
        self.windows_projection_contract = windows_projection_contract

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
            return _select_unconsumed_n5_action_events(
                cur,
                trade_date=trade_date,
                consumer_name=consumer_name,
                limit=limit,
            )

    def capture_cas_snapshot(self, *, trade_date: str, consumer_name: str, limit: int) -> dict[str, Any]:
        with psycopg.connect(
            self.dsn,
            row_factory=dict_row,
            connect_timeout=10,
            options="-c default_transaction_read_only=on -c default_transaction_isolation=repeatable\\ read",
        ) as conn, conn.cursor() as cur:
            checkpoint = _select_checkpoint_cas(cur, consumer_name=consumer_name, for_update=False)
            events = _select_unconsumed_n5_action_events(
                cur,
                trade_date=trade_date,
                consumer_name=consumer_name,
                limit=limit,
            )
        return _cas_snapshot(checkpoint, events)

    def commit_projection_events(
        self,
        *,
        trade_date: str,
        max_events: int,
        projection_run_id: str,
        consumer_name: str,
        expected_checkpoint_cas_sha256: str,
        expected_selected_event_cas_sha256: str,
        expected_selected_event_count: int,
    ) -> dict[str, Any]:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=10) as conn:
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                        cur.execute(ADVISORY_LOCK_SQL, (ADVISORY_LOCK_KEY,))
                        advisory_row = cur.fetchone()
                        if not advisory_row or not bool(advisory_row["acquired"]):
                            raise PollerBlockedError("postgresql_advisory_lock_not_acquired")
                        checkpoint = _select_checkpoint_cas(cur, consumer_name=consumer_name, for_update=True)
                        transaction_rows = _select_unconsumed_n5_action_events(
                            cur,
                            trade_date=trade_date,
                            consumer_name=consumer_name,
                            limit=max_events,
                        )
                        transaction_snapshot = _cas_snapshot(checkpoint, transaction_rows)
                        if transaction_snapshot["checkpoint_cas_sha256"] != expected_checkpoint_cas_sha256:
                            raise PollerBlockedError("checkpoint_cas_mismatch")
                        if (
                            transaction_snapshot["selected_event_cas_sha256"] != expected_selected_event_cas_sha256
                            or transaction_snapshot["selected_event_count"] != expected_selected_event_count
                        ):
                            raise PollerBlockedError("selected_event_cas_mismatch")
                        blockers = _validate_events(transaction_rows, expected_trade_date=trade_date)
                        if blockers:
                            raise PollerBlockedError(blockers[0])
                        prepared = _partition_projection_message_events(transaction_rows)
                        projection_events = [
                            _projection_event_from_row(row) for row in prepared["projectable_events"]
                        ]
                        projection_events = freeze_stock_industry_context(
                            projection_events,
                            _select_reviewed_industry_rows(cur, projection_events),
                        )
                        skipped_projection_events = [
                            (_projection_event_from_row(item["event"]), list(item["reasons"]))
                            for item in prepared["skipped_events"]
                        ]
                        selected_events = sorted(
                            projection_events + [event for event, _ in skipped_projection_events],
                            key=lambda event: (str(event.event_time), event.outbox_id, event.event_id),
                        )
                        skipped_reasons_by_event_id = {
                            event.event_id: reasons for event, reasons in skipped_projection_events
                        }
                        source_run_id = _source_action_run_id_for(projection_events)
                        if not selected_events:
                            return {
                                "committed": False,
                                "user_projection_run": 0,
                                "user_signal_projection": 0,
                                "user_signal_card": 0,
                                "common_event_inbox": 0,
                                "common_event_consumer_checkpoint": 0,
                                "skipped_projection_message": 0,
                                "selected_events": [],
                                "skipped_events": [],
                            }
                        snapshot = None
                        if projection_events:
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
                                quality_summary={
                                    "b_track_signal_projection": "passed",
                                    "skipped_projection_message_count": len(skipped_projection_events),
                                },
                            )
                            insert_projection_run(cur, run_row)
                        projection_count = 0
                        card_count = 0
                        inbox_count = 0
                        for event in selected_events:
                            skip_reasons = skipped_reasons_by_event_id.get(event.event_id)
                            if skip_reasons is not None:
                                _insert_inbox(cur, event, consumer_name, skip_reasons=skip_reasons)
                                inbox_count += 1
                                continue
                            assert snapshot is not None
                            if self.windows_projection_contract:
                                projected, cards = _project_windows_event_for_scoped_users(
                                    cur,
                                    event,
                                    projection_run_id=projection_run_id,
                                )
                                projection_count += projected
                                card_count += cards
                            else:
                                projection_row = build_projection_row(event, projection_run_id, snapshot)
                                _enforce_n6_display_payload_contract(
                                    projection_row,
                                    event,
                                    payload_key="display_payload_json",
                                )
                                projection_id = insert_signal_projection(cur, projection_row)
                                card_row = build_card_row(event, projection_run_id, snapshot)
                                _enforce_n6_display_payload_contract(
                                    card_row,
                                    event,
                                    payload_key="card_payload_json",
                                )
                                card_row["user_signal_projection_id"] = projection_id
                                insert_signal_card(cur, card_row)
                                projection_count += 1
                                card_count += 1
                            _insert_inbox(cur, event, consumer_name)
                            inbox_count += 1
                        if projection_events:
                            cur.execute(
                                """
                                UPDATE user_projection_run
                                SET output_projection_count = %s,
                                    updated_at = now()
                                WHERE user_projection_run_id = %s
                                """,
                                (projection_count, projection_run_id),
                            )
                        _upsert_checkpoint(
                            cur,
                            selected_events,
                            consumer_name,
                        )
            except PollerBlockedError:
                conn.rollback()
                raise
        return {
            "committed": True,
            "user_projection_run": 1 if projection_events else 0,
            "user_signal_projection": projection_count,
            "user_signal_card": card_count,
            "common_event_inbox": inbox_count,
            "common_event_consumer_checkpoint": 1 if selected_events else 0,
            "skipped_projection_message": len(skipped_projection_events),
            "selected_events": transaction_rows,
            "skipped_events": prepared["skipped_events"],
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
    max_events: int = MAX_INTERNAL_BATCH_SIZE,
    cas_authority_mode: str = "internal_one_shot",
    expected_checkpoint_cas_sha256: str | None = None,
    expected_selected_event_cas_sha256: str | None = None,
    expected_selected_event_count: int | None = None,
    json_report_path: str | Path = DEFAULT_JSON_REPORT_PATH,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    write_reports: bool = False,
) -> dict[str, Any]:
    cas_blocker = _validate_cas_authority(
        consumer_name=consumer_name,
        cas_authority_mode=cas_authority_mode,
        max_events=max_events,
        expected_checkpoint_cas_sha256=expected_checkpoint_cas_sha256,
        expected_selected_event_cas_sha256=expected_selected_event_cas_sha256,
        expected_selected_event_count=expected_selected_event_count,
    )
    if cas_blocker:
        return _stdout_only_lock_result("BLOCKED", cas_blocker)
    started_at = _now(now).isoformat()
    report = _base_report(started_at=started_at, for_trade_date=for_trade_date, consumer_name=consumer_name)
    report["cas_authority"] = {
        "mode": cas_authority_mode,
        "expected_checkpoint_cas_sha256": expected_checkpoint_cas_sha256,
        "expected_selected_event_cas_sha256": expected_selected_event_cas_sha256,
        "expected_selected_event_count": expected_selected_event_count,
    }
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

    try:
        prewrite_snapshot = dict(
            repo.capture_cas_snapshot(
                trade_date=effective_trade_date,
                consumer_name=consumer_name,
                limit=max_events,
            )
        )
    except PollerBlockedError as exc:
        return _finalize(
            report,
            "BLOCKED",
            reason=str(exc),
            blockers=[str(exc)],
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    events = list(prewrite_snapshot["events"])
    report["cas_authority"].update(
        {
            "prewrite_checkpoint_cas_sha256": prewrite_snapshot["checkpoint_cas_sha256"],
            "prewrite_selected_event_cas_sha256": prewrite_snapshot["selected_event_cas_sha256"],
            "prewrite_selected_event_count": prewrite_snapshot["selected_event_count"],
        }
    )
    if cas_authority_mode == "external_bounded_canary" and (
        prewrite_snapshot["checkpoint_cas_sha256"] != expected_checkpoint_cas_sha256
        or prewrite_snapshot["selected_event_cas_sha256"] != expected_selected_event_cas_sha256
        or prewrite_snapshot["selected_event_count"] != expected_selected_event_count
    ):
        blocker = (
            "checkpoint_cas_mismatch"
            if prewrite_snapshot["checkpoint_cas_sha256"] != expected_checkpoint_cas_sha256
            else "selected_event_cas_mismatch"
        )
        return _finalize(
            report,
            "BLOCKED",
            reason=blocker,
            blockers=[blocker],
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
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
    if not events and (not execute or not user_confirmed):
        return _finalize(
            report,
            "NOOP",
            reason="no_unconsumed_n5_action_events",
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    prepared = _partition_projection_message_events(events)
    projectable_events = prepared["projectable_events"]
    skipped_events = prepared["skipped_events"]
    report["projectable_event_count"] = len(projectable_events)
    report["projectable_event_ids"] = [str(event.get("event_id") or "") for event in projectable_events]
    report["projection_message_audit"] = {
        "skipped_event_count": len(skipped_events),
        "items": [
            {
                "event_id": str(item["event"].get("event_id") or ""),
                "outbox_id": int(item["event"].get("outbox_id") or 0),
                "reasons": list(item["reasons"]),
            }
            for item in skipped_events
        ],
    }
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
    try:
        write_result = dict(
            repo.commit_projection_events(
                trade_date=effective_trade_date,
                max_events=max_events,
                projection_run_id=projection_run_id,
                consumer_name=consumer_name,
                expected_checkpoint_cas_sha256=prewrite_snapshot["checkpoint_cas_sha256"],
                expected_selected_event_cas_sha256=prewrite_snapshot["selected_event_cas_sha256"],
                expected_selected_event_count=prewrite_snapshot["selected_event_count"],
            )
        )
    except PollerBlockedError as exc:
        return _finalize(
            report,
            "BLOCKED",
            reason=str(exc),
            blockers=[str(exc)],
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
        )
    write_result.pop("selected_events", None)
    write_result.pop("skipped_events", None)
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
    if not events:
        return _finalize(
            report,
            "NOOP",
            reason="no_unconsumed_n5_action_events",
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
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
    if consumer_name != CONSUMER_NAME or max_events_per_date < 1:
        return _finalize(
            report,
            "BLOCKED",
            reason="invalid_cas_authority",
            blockers=["invalid_cas_authority"],
            write_reports=write_reports,
            json_report_path=json_report_path,
            history_path=history_path,
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
        prewrite_snapshot = dict(
            repo.capture_cas_snapshot(
                trade_date=trade_date,
                consumer_name=consumer_name,
                limit=max_events_per_date,
            )
        )
        events = list(prewrite_snapshot["events"])
        blockers = _validate_events(events, expected_trade_date=trade_date)
        prepared = _partition_projection_message_events(events) if not blockers else {
            "projectable_events": [],
            "skipped_events": [],
        }
        projectable_events = prepared["projectable_events"]
        skipped_events = prepared["skipped_events"]
        item: dict[str, Any] = {
            "trade_date": trade_date,
            "selected_event_count": len(events),
            "selected_event_ids": [str(event.get("event_id") or "") for event in events[:20]],
            "projectable_event_count": len(projectable_events),
            "skipped_projection_message_count": len(skipped_events),
            "projection_message_audit": [
                {
                    "event_id": str(skipped["event"].get("event_id") or ""),
                    "outbox_id": int(skipped["event"].get("outbox_id") or 0),
                    "reasons": list(skipped["reasons"]),
                }
                for skipped in skipped_events
            ],
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
            try:
                write_result = dict(
                    repo.commit_projection_events(
                        trade_date=trade_date,
                        max_events=max_events_per_date,
                        projection_run_id=projection_run_id,
                        consumer_name=consumer_name,
                        expected_checkpoint_cas_sha256=prewrite_snapshot["checkpoint_cas_sha256"],
                        expected_selected_event_cas_sha256=prewrite_snapshot["selected_event_cas_sha256"],
                        expected_selected_event_count=prewrite_snapshot["selected_event_count"],
                    )
                )
            except PollerBlockedError as exc:
                item["blockers"] = [str(exc)]
                report["per_trade_date"].append(item)
                return _finalize(
                    report,
                    "BLOCKED",
                    reason=str(exc),
                    blockers=[f"{trade_date}:{exc}"],
                    write_reports=write_reports,
                    json_report_path=json_report_path,
                    history_path=history_path,
                )
            write_result.pop("selected_events", None)
            write_result.pop("skipped_events", None)
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


def _partition_projection_message_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    projectable_events: list[Mapping[str, Any]] = []
    skipped_events: list[dict[str, Any]] = []
    for event in events:
        reasons = _projection_message_skip_reasons(event)
        if reasons:
            skipped_events.append({"event": event, "reasons": reasons})
        else:
            projectable_events.append(event)
    return {
        "projectable_events": projectable_events,
        "skipped_events": skipped_events,
    }


def _projection_message_skip_reasons(event: Mapping[str, Any]) -> list[str]:
    payload = event.get("payload_json")
    if not isinstance(payload, Mapping):
        return ["projection_message_payload_not_object"]
    reasons = [
        f"projection_message_marker_missing:{field}"
        for field in PROJECTION_MESSAGE_MARKER_FIELDS
        if field not in payload
    ]
    if payload.get("projection_message_contract_version") != N5_PROJECTION_MESSAGE_CONTRACT_VERSION:
        reasons.append("projection_message_contract_version_mismatch")
    if payload.get("projection_message_contract_hash") != N5_PROJECTION_MESSAGE_CONTRACT_HASH:
        reasons.append("projection_message_contract_hash_mismatch")
    if payload.get("projection_message_status") != "ready":
        reasons.append("projection_message_status_not_ready")
    if reasons:
        if not str(payload.get("asset_name") or "").strip():
            reasons.append("projection_message_asset_name_missing")
        return sorted(set(reasons))
    evaluation = evaluate_projection_message_contract(_projection_event_from_row(event))
    return list(evaluation["reasons"]) if not evaluation["projectable"] else []


def _projection_event_from_row(row: Mapping[str, Any]) -> ProjectionEvent:
    payload = row.get("payload_json")
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload = dict(payload or {})
    target_price = row.get("target_price")
    expected_return_pct = row.get("expected_return_pct")
    if "projection_message_contract_version" in payload:
        context = payload.get("condition_projection_context")
        fields = context.get("fields") if isinstance(context, Mapping) else None
        fields = fields if isinstance(fields, Mapping) else {}
        direction = str(payload.get("direction") or "")
        if direction == "buy":
            target_price = fields.get("buy_target_price")
            expected_return_pct = fields.get("buy_expected_return_pct")
        elif direction == "sell":
            target_price = fields.get("sell_target_price")
            expected_return_pct = fields.get("sell_expected_return_pct")
        else:
            target_price = None
            expected_return_pct = None
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
        payload_json=payload,
        source_display_table=row.get("source_display_table"),
        display_basis_id=row.get("display_basis_id"),
        display_run_id=row.get("display_run_id"),
        code=row.get("code"),
        name=row.get("name"),
        target_price=target_price,
        expected_return_pct=expected_return_pct,
        board_code=row.get("board_code"),
        board_name=row.get("board_name"),
        current_price=row.get("current_price"),
    )


def _source_action_run_id_for(events: Sequence[ProjectionEvent]) -> str:
    source_run_ids = [event.source_run_id for event in events if event.source_run_id]
    if not source_run_ids:
        return "n6_b_track_signal_projection_no_source_run"
    return source_run_ids[0] if len(set(source_run_ids)) == 1 else "n6_b_track_signal_projection_mixed_n5_runs"


def _select_reviewed_industry_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    events: Sequence[ProjectionEvent],
) -> list[IndustryMembershipRow]:
    stock_identity_keys = sorted(
        {
            event.identity_key
            for event in events
            if event.asset_kind == "stock" and is_projection_message_contract_event(event)
        }
    )
    source_trade_dates = sorted(
        {
            source_trade_date
            for event in events
            if event.asset_kind == "stock" and is_projection_message_contract_event(event)
            if (source_trade_date := source_trade_date_for_event(event))
        }
    )
    if not stock_identity_keys or not source_trade_dates:
        return []
    cur.execute(
        """
        SELECT DISTINCT trade_date,
                        stock_identity_key,
                        board_identity_key,
                        board_code,
                        board_name
          FROM v_n6_board_membership_fact
         WHERE stock_identity_key = ANY(%s)
           AND trade_date = ANY(%s)
           AND board_type = 'tdx_industry'
         ORDER BY stock_identity_key,
                  trade_date,
                  board_identity_key,
                  board_code,
                  board_name
        """,
        (stock_identity_keys, source_trade_dates),
    )
    return [IndustryMembershipRow(**dict(row)) for row in cur.fetchall()]


def _enforce_n6_display_payload_contract(
    row: dict[str, Any],
    event: ProjectionEvent,
    *,
    payload_key: str,
) -> None:
    display_payload = dict(row.get(payload_key) or {})
    if event.event_type == "ActionEligible":
        display_payload["action_price"] = None
        display_payload["action_pct"] = None
        display_payload["action_pct_status"] = None
    if event.asset_kind != "stock":
        display_payload.pop("score", None)
        display_payload.pop("pe_core", None)
    row[payload_key] = display_payload


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


WINDOWS_MONITOR_TABLE_BY_ASSET = {
    "stock": "user_monitor_stock",
    "index": "user_monitor_index",
    "board": "user_monitor_board",
}
WINDOWS_N6_CONSUMER_NAME = "windows_n6_action_projection_v1"


def windows_card_mutation_for_event(event_type: str) -> str:
    if event_type == "ActionEligible":
        return "create"
    if event_type in {"ActionExecuted", "ActionBlocked", "ActionSkipped"}:
        return "update"
    return "none"


def _fetch_windows_scoped_users(
    cur: psycopg.Cursor[dict[str, Any]],
    event: ProjectionEvent,
) -> list[dict[str, Any]]:
    monitor_table = WINDOWS_MONITOR_TABLE_BY_ASSET[event.asset_kind]
    direction = str(event.payload_json.get("direction") or "").lower()
    condition_key = str(event.payload_json.get("condition_key") or "")
    cur.execute(
        f"""
        WITH scoped AS (
          SELECT principal_id, principal_type, user_id
          FROM user_realtime_monitor_scope
          WHERE asset_kind = %s
            AND identity_key = %s
            AND status = 'active'
          UNION
          SELECT principal_id, principal_type, user_id
          FROM {monitor_table}
          WHERE identity_key = %s
            AND direction = %s
            AND status = 'active'
            AND quality_status = 'reviewed'
            AND (valid_for_trade_date IS NULL OR valid_for_trade_date = %s)
            AND (condition_key IS NULL OR condition_key = '' OR condition_key = %s)
        )
        SELECT DISTINCT s.principal_id,
               s.principal_type,
               s.user_id,
               u.login_name,
               u.role,
               u.status,
               p.user_filter_profile_id,
               p.profile_name,
               p.is_default,
               p.status AS profile_status
        FROM scoped s
        JOIN user_account u
          ON u.user_id = s.user_id
         AND u.status = 'active'
        LEFT JOIN LATERAL (
          SELECT user_filter_profile_id, profile_name, is_default, status
          FROM user_filter_profile
          WHERE user_id = s.user_id
            AND is_default = true
            AND status = 'active'
          ORDER BY user_filter_profile_id
          LIMIT 1
        ) p ON true
        ORDER BY s.user_id, s.principal_id, s.principal_type
        """,
        (
            event.asset_kind,
            event.identity_key,
            event.identity_key,
            direction,
            event.trade_date,
            condition_key,
        ),
    )
    return [dict(row) for row in cur.fetchall()]


def _windows_user_snapshot(
    event: ProjectionEvent,
    projection_run_id: str,
    scoped_user: Mapping[str, Any],
) -> ProjectionExecuteSnapshot:
    profile = None
    if scoped_user.get("user_filter_profile_id") is not None:
        profile = FilterProfile(
            user_filter_profile_id=int(scoped_user["user_filter_profile_id"]),
            user_id=int(scoped_user["user_id"]),
            profile_name=str(scoped_user.get("profile_name") or ""),
            is_default=bool(scoped_user.get("is_default")),
            status=str(scoped_user.get("profile_status") or "active"),
        )
    return ProjectionExecuteSnapshot(
        input_snapshot=ProjectionInputSnapshot(
            table_counts={},
            admin=AdminUser(
                user_id=int(scoped_user["user_id"]),
                login_name=str(scoped_user.get("login_name") or ""),
                role=str(scoped_user.get("role") or "user"),
                status=str(scoped_user.get("status") or "active"),
            ),
            default_profile=profile,
            n5_outbox_counts={},
            display_basis_counts={},
            events=[event],
        ),
        projection_run_id=projection_run_id,
        scoped_counts={},
        linked_counts={},
    )


def _project_windows_event_for_scoped_users(
    cur: psycopg.Cursor[dict[str, Any]],
    event: ProjectionEvent,
    *,
    projection_run_id: str,
) -> tuple[int, int]:
    projection_count = 0
    card_count = 0
    mutation = windows_card_mutation_for_event(event.event_type)
    episode_entry_event_id = str(event.payload_json.get("episode_entry_event_id") or "")
    for scoped_user in _fetch_windows_scoped_users(cur, event):
        snapshot = _windows_user_snapshot(event, projection_run_id, scoped_user)
        projection_row = build_projection_row(event, projection_run_id, snapshot)
        projection_row["display_payload_json"].update({
            "principal_id": int(scoped_user["principal_id"]),
            "principal_type": str(scoped_user["principal_type"]),
            "episode_entry_event_id": episode_entry_event_id,
            "projection_idempotency_key": f"{event.outbox_id}:{event.event_id}:{scoped_user['user_id']}",
            "windows_projection_contract": "windows_n6_action_projection_v1",
        })
        _enforce_n6_display_payload_contract(projection_row, event, payload_key="display_payload_json")
        projection_id = insert_signal_projection(cur, projection_row)
        projection_count += 1
        if mutation == "create":
            card_row = build_card_row(event, projection_run_id, snapshot)
            card_row["card_payload_json"].update({
                "principal_id": int(scoped_user["principal_id"]),
                "principal_type": str(scoped_user["principal_type"]),
                "episode_entry_event_id": episode_entry_event_id,
                "windows_projection_contract": "windows_n6_action_projection_v1",
            })
            _enforce_n6_display_payload_contract(card_row, event, payload_key="card_payload_json")
            card_row["user_signal_projection_id"] = projection_id
            insert_signal_card(cur, card_row)
            card_count += 1
        elif mutation == "update":
            card_count += _update_windows_episode_card(cur, event, snapshot, episode_entry_event_id)
    return projection_count, card_count


def _update_windows_episode_card(
    cur: psycopg.Cursor[dict[str, Any]],
    event: ProjectionEvent,
    snapshot: ProjectionExecuteSnapshot,
    episode_entry_event_id: str,
) -> int:
    if not episode_entry_event_id:
        return 0
    card = build_card_row(event, snapshot.projection_run_id, snapshot)
    card["card_payload_json"]["episode_entry_event_id"] = episode_entry_event_id
    cur.execute(
        """
        UPDATE user_signal_card c
        SET card_status = %(card_status)s,
            display_priority = %(display_priority)s,
            title = %(title)s,
            summary = %(summary)s,
            current_price = %(current_price)s,
            source_event_id = %(source_event_id)s,
            source_action_event_id = %(source_action_event_id)s,
            source_action_event_type = %(source_action_event_type)s,
            action_state = %(action_state)s,
            action_mark = %(action_mark)s,
            trace_json = %(trace_json)s,
            projection_policy = %(projection_policy)s,
            card_payload_json = %(card_payload_json)s,
            updated_at = now()
        FROM user_signal_projection p
        WHERE c.user_signal_projection_id = p.user_signal_projection_id
          AND c.user_id = %(user_id)s
          AND p.source_action_event_type = 'ActionEligible'
          AND p.asset_kind = %(asset_kind)s
          AND p.identity_key = %(identity_key)s
          AND p.direction = %(direction)s
          AND p.source_payload_json #>> '{payload_json,episode_entry_event_id}' = %(episode_entry_event_id)s
        """,
        {
            **card,
            "card_payload_json": Jsonb(card["card_payload_json"]),
            "trace_json": Jsonb(card.get("trace_json") or {}),
            "episode_entry_event_id": episode_entry_event_id,
        },
    )
    return max(int(cur.rowcount or 0), 0)


def _insert_inbox(
    cur: psycopg.Cursor[dict[str, Any]],
    event: ProjectionEvent,
    consumer_name: str,
    *,
    skip_reasons: Sequence[str] | None = None,
) -> None:
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
        RETURNING inbox_id
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
            Jsonb(
                {
                    "n6_projection": "b_track_signal_projection",
                    "projection_status": "skipped_fail_closed" if skip_reasons else "projected",
                    "projection_skip_reasons": list(skip_reasons or []),
                    "outbox_status_updated": False,
                }
            ),
        ),
    )
    if not cur.fetchone():
        raise PollerBlockedError("inbox_idempotency_conflict")


def _upsert_checkpoint(
    cur: psycopg.Cursor[dict[str, Any]],
    events: Sequence[ProjectionEvent],
    consumer_name: str,
) -> None:
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
            Jsonb(
                {
                    "event_count": len(events),
                    "projection_policy": "n6_b_track_signal_projection",
                }
            ),
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


def _validate_cas_authority(
    *,
    consumer_name: str,
    cas_authority_mode: str,
    max_events: int,
    expected_checkpoint_cas_sha256: str | None,
    expected_selected_event_cas_sha256: str | None,
    expected_selected_event_count: int | None,
) -> str:
    if consumer_name != CONSUMER_NAME or cas_authority_mode not in CAS_AUTHORITY_MODES:
        return "invalid_cas_authority"
    provided = (
        expected_checkpoint_cas_sha256,
        expected_selected_event_cas_sha256,
        expected_selected_event_count,
    )
    if cas_authority_mode == "internal_one_shot":
        if not 1 <= max_events <= MAX_INTERNAL_BATCH_SIZE:
            return "invalid_cas_authority"
        return "invalid_internal_cas_authority" if any(value is not None for value in provided) else ""
    if max_events != 1:
        return "invalid_cas_authority"
    if any(value is None for value in provided):
        return "external_bounded_canary_cas_authority_missing"
    if not _is_sha256(expected_checkpoint_cas_sha256) or not _is_sha256(expected_selected_event_cas_sha256):
        return "external_bounded_canary_cas_authority_invalid"
    if expected_selected_event_count not in (0, 1):
        return "external_bounded_canary_cas_authority_invalid"
    return ""


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


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
    parser.add_argument("--max-events", type=int, default=MAX_INTERNAL_BATCH_SIZE)
    parser.add_argument("--singleton-lock-path", required=True)
    parser.add_argument("--cas-authority-mode", choices=CAS_AUTHORITY_MODES, default="internal_one_shot")
    parser.add_argument("--expected-checkpoint-cas-sha256")
    parser.add_argument("--expected-selected-event-cas-sha256")
    parser.add_argument("--expected-selected-event-count", type=int)
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
    release_id, source_commit = _runtime_release_identity()
    cas_blocker = "" if args.historical_backfill else _validate_cas_authority(
        consumer_name=args.consumer_name,
        cas_authority_mode=args.cas_authority_mode,
        max_events=args.max_events,
        expected_checkpoint_cas_sha256=args.expected_checkpoint_cas_sha256,
        expected_selected_event_cas_sha256=args.expected_selected_event_cas_sha256,
        expected_selected_event_count=args.expected_selected_event_count,
    )
    if cas_blocker:
        report = _stdout_only_lock_result("BLOCKED", cas_blocker)
    else:
        try:
            with acquire_singleton_lock(
                args.singleton_lock_path,
                release_id=release_id,
                source_commit=source_commit,
            ):
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
                        cas_authority_mode=args.cas_authority_mode,
                        expected_checkpoint_cas_sha256=args.expected_checkpoint_cas_sha256,
                        expected_selected_event_cas_sha256=args.expected_selected_event_cas_sha256,
                        expected_selected_event_count=args.expected_selected_event_count,
                        json_report_path=args.json_report_path,
                        history_path=args.history_path,
                        write_reports=True,
                    )
        except SingletonLockHeldError:
            report = _stdout_only_lock_result("NOOP", "singleton_lock_held")
        except SingletonLockContractError:
            report = _stdout_only_lock_result("BLOCKED", "singleton_lock_contract_invalid")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(
            f"result={report['result']} reason={report.get('reason', '')} "
            f"selected_event_count={report.get('selected_event_count', 0)}"
        )
    return 0 if report["result"] in {"EXECUTE_PASS", "NOOP", "PREFLIGHT_PASS"} else 2


def _runtime_release_identity() -> tuple[str, str]:
    release_id = Path(__file__).resolve().parents[1].name
    source_commit = release_id.rsplit("__", 1)[-1] if "__" in release_id else ""
    if not (len(source_commit) == 40 and all(char in "0123456789abcdef" for char in source_commit)):
        source_commit = ""
    return release_id, source_commit


def _stdout_only_lock_result(result: str, reason: str) -> dict[str, Any]:
    now = datetime.now(ASIA_SHANGHAI).isoformat()
    return {
        "stage": "N6_B_TRACK_SIGNAL_PROJECTION_POLLER_ONCE",
        "result": result,
        "reason": reason,
        "blockers": [reason] if result == "BLOCKED" else [],
        "started_at": now,
        "finished_at": now,
        "selected_event_count": 0,
        "side_effects": _base_report(started_at=now, for_trade_date=None, consumer_name=CONSUMER_NAME)["side_effects"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
