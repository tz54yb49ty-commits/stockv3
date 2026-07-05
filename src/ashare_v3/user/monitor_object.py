"""Core B-track monitor object model.

This module is deliberately pure: it has no database driver, web route, UI, or
trading dependency. Persistence adapters can map these fields to storage later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Literal


AssetType = Literal["stock", "index", "board"]
MonitorStatus = Literal["active", "expired"]
ExpiredReason = Literal["date_mismatch", "removed", "manual"] | None
SourceType = Literal["direct", "index", "board"]
ParentType = Literal["index", "board"] | None


@dataclass(frozen=True)
class MonitorObjectColumn:
    name: str
    required: bool = True


MONITOR_OBJECT_SCHEMA: tuple[MonitorObjectColumn, ...] = (
    MonitorObjectColumn("id"),
    MonitorObjectColumn("user_id"),
    MonitorObjectColumn("asset_type"),
    MonitorObjectColumn("identity_key"),
    MonitorObjectColumn("display_name"),
    MonitorObjectColumn("for_trade_date"),
    MonitorObjectColumn("source_trade_date"),
    MonitorObjectColumn("status"),
    MonitorObjectColumn("expired_reason", required=False),
    MonitorObjectColumn("source_type"),
    MonitorObjectColumn("source_id", required=False),
    MonitorObjectColumn("source_name", required=False),
    MonitorObjectColumn("parent_type", required=False),
    MonitorObjectColumn("parent_identity_key", required=False),
    MonitorObjectColumn("membership_origin"),
    MonitorObjectColumn("created_at"),
    MonitorObjectColumn("updated_at"),
)


MONITOR_OBJECT_CREATE_TABLE_SQL = """
CREATE TABLE monitor_object (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('stock', 'index', 'board')),
    identity_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    for_trade_date TEXT NOT NULL,
    source_trade_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'expired')),
    expired_reason TEXT CHECK (expired_reason IS NULL OR expired_reason IN ('date_mismatch', 'removed', 'manual')),
    source_type TEXT NOT NULL CHECK (source_type IN ('direct', 'index', 'board')),
    source_id TEXT,
    source_name TEXT,
    parent_type TEXT CHECK (parent_type IS NULL OR parent_type IN ('index', 'board')),
    parent_identity_key TEXT,
    membership_origin BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
)
""".strip()


@dataclass(frozen=True)
class MonitorObject:
    id: int
    user_id: int
    asset_type: AssetType
    identity_key: str
    display_name: str
    for_trade_date: str
    source_trade_date: str
    status: MonitorStatus
    expired_reason: ExpiredReason
    source_type: SourceType
    source_id: str | None
    source_name: str | None
    parent_type: ParentType
    parent_identity_key: str | None
    membership_origin: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_text(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name}_required")
    return text


def _validate_asset_type(asset_type: str) -> AssetType:
    if asset_type not in {"stock", "index", "board"}:
        raise ValueError("invalid_asset_type")
    return asset_type  # type: ignore[return-value]


def create_direct_monitor_object(
    *,
    id: int,
    user_id: int,
    asset_type: str,
    identity_key: str,
    display_name: str,
    for_trade_date: str,
    source_trade_date: str,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> MonitorObject:
    timestamp = created_at or updated_at or _timestamp()
    return MonitorObject(
        id=int(id),
        user_id=int(user_id),
        asset_type=_validate_asset_type(asset_type),
        identity_key=_require_text(identity_key, "identity_key"),
        display_name=_require_text(display_name, "display_name"),
        for_trade_date=_require_text(for_trade_date, "for_trade_date"),
        source_trade_date=_require_text(source_trade_date, "source_trade_date"),
        status="active",
        expired_reason=None,
        source_type="direct",
        source_id=None,
        source_name=None,
        parent_type=None,
        parent_identity_key=None,
        membership_origin=False,
        created_at=timestamp,
        updated_at=updated_at or timestamp,
    )


def _create_drill_down_monitor_object(
    *,
    id: int,
    user_id: int,
    asset_type: str,
    identity_key: str,
    display_name: str,
    for_trade_date: str,
    source_trade_date: str,
    source_type: SourceType,
    source_id: str,
    source_name: str,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> MonitorObject:
    if source_type not in {"index", "board"}:
        raise ValueError("invalid_source_type")
    timestamp = created_at or updated_at or _timestamp()
    parent_type: ParentType = source_type
    return MonitorObject(
        id=int(id),
        user_id=int(user_id),
        asset_type=_validate_asset_type(asset_type),
        identity_key=_require_text(identity_key, "identity_key"),
        display_name=_require_text(display_name, "display_name"),
        for_trade_date=_require_text(for_trade_date, "for_trade_date"),
        source_trade_date=_require_text(source_trade_date, "source_trade_date"),
        status="active",
        expired_reason=None,
        source_type=source_type,
        source_id=_require_text(source_id, "source_id"),
        source_name=_require_text(source_name, "source_name"),
        parent_type=parent_type,
        parent_identity_key=_require_text(source_id, "source_id"),
        membership_origin=True,
        created_at=timestamp,
        updated_at=updated_at or timestamp,
    )


def create_index_drill_down_monitor_object(
    *,
    id: int,
    user_id: int,
    asset_type: str,
    identity_key: str,
    display_name: str,
    for_trade_date: str,
    source_trade_date: str,
    source_id: str,
    source_name: str,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> MonitorObject:
    return _create_drill_down_monitor_object(
        id=id,
        user_id=user_id,
        asset_type=asset_type,
        identity_key=identity_key,
        display_name=display_name,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        source_type="index",
        source_id=source_id,
        source_name=source_name,
        created_at=created_at,
        updated_at=updated_at,
    )


def create_board_drill_down_monitor_object(
    *,
    id: int,
    user_id: int,
    asset_type: str,
    identity_key: str,
    display_name: str,
    for_trade_date: str,
    source_trade_date: str,
    source_id: str,
    source_name: str,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> MonitorObject:
    return _create_drill_down_monitor_object(
        id=id,
        user_id=user_id,
        asset_type=asset_type,
        identity_key=identity_key,
        display_name=display_name,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        source_type="board",
        source_id=source_id,
        source_name=source_name,
        created_at=created_at,
        updated_at=updated_at,
    )


def update_monitor_status_by_trade_date(
    monitors: Iterable[MonitorObject],
    filter_trade_date: str,
) -> list[MonitorObject]:
    current_trade_date = _require_text(filter_trade_date, "filter_trade_date")
    updated: list[MonitorObject] = []
    for monitor in monitors:
        if monitor.status == "active" and monitor.for_trade_date != current_trade_date:
            updated.append(
                replace(
                    monitor,
                    status="expired",
                    expired_reason="date_mismatch",
                    updated_at=_timestamp(),
                )
            )
        else:
            updated.append(monitor)
    return updated


def get_user_monitor_objects(
    monitors: Iterable[MonitorObject],
    *,
    user_id: int,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {"active": [], "expired": []}
    for monitor in monitors:
        if monitor.user_id != int(user_id):
            continue
        grouped[monitor.status].append(monitor.to_dict())
    return grouped
