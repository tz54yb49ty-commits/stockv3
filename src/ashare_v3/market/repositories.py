"""N3 market fact repository drafts.

Repositories only build and execute SQL. They do not own transactions and do
not call market data adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ASSET_FACT_TABLES = {
    "stock": {
        "snapshot": ("stock_realtime_daily_snapshot", "stock_identity_key", "snapshot_id"),
        "minute": ("stock_minute_bar_1m", "stock_identity_key", "bar_id"),
        "preload_status": ("stock_previous_day_minute_preload_status", "stock_identity_key", "preload_status_id"),
    },
    "index": {
        "snapshot": ("index_realtime_daily_snapshot", "index_identity_key", "snapshot_id"),
        "minute": ("index_minute_bar_1m", "index_identity_key", "bar_id"),
        "preload_status": ("index_previous_day_minute_preload_status", "index_identity_key", "preload_status_id"),
    },
    "board": {
        "snapshot": ("board_realtime_daily_snapshot", "board_identity_key", "snapshot_id"),
        "minute": ("board_minute_bar_1m", "board_identity_key", "bar_id"),
        "preload_status": ("board_previous_day_minute_preload_status", "board_identity_key", "preload_status_id"),
    },
}


class MarketRepositoryError(ValueError):
    """Raised when a market repository input violates the N3 contract."""


def require_asset_kind(asset_kind: str) -> None:
    if asset_kind not in ASSET_FACT_TABLES:
        raise MarketRepositoryError(f"unsupported asset_kind: {asset_kind}")


def require_fields(record: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if record.get(field) is None]
    if missing:
        raise MarketRepositoryError(f"record missing required fields: {', '.join(missing)}")


def fetch_returned_id(cursor: Any, id_column: str) -> int:
    fetched = cursor.fetchone()
    if isinstance(fetched, dict):
        return int(fetched[id_column])
    if isinstance(fetched, tuple):
        return int(fetched[0])
    raise MarketRepositoryError(f"insert did not return {id_column}")


class SnapshotRepository:
    """Repository for stock/index/board realtime daily snapshot facts."""

    required_fields = (
        "asset_kind",
        "run_id",
        "subscription_id",
        "source_condition_run_id",
        "for_trade_date",
        "trade_date",
        "snapshot_time",
        "identity_key",
        "exchange",
        "code",
        "source_adapter",
        "quality_status",
    )

    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def upsert_snapshot(self, record: Mapping[str, Any]) -> int:
        require_fields(record, self.required_fields)
        asset_kind = str(record["asset_kind"])
        require_asset_kind(asset_kind)
        table_name, identity_column, id_column = ASSET_FACT_TABLES[asset_kind]["snapshot"]
        columns = (
            "run_id",
            "subscription_id",
            "source_condition_run_id",
            "for_trade_date",
            "trade_date",
            "snapshot_time",
            identity_column,
            "exchange",
            "code",
            "display_code",
            "name",
            "open",
            "high",
            "low",
            "close",
            "current_price",
            "pre_close",
            "volume",
            "amount",
            "source_adapter",
            "source_version",
            "quality_status",
            "source_scope_ids",
            "source_condition_pool_ids",
            "raw_json",
        )
        values = [
            record.get("run_id"),
            record.get("subscription_id"),
            record.get("source_condition_run_id"),
            record.get("for_trade_date"),
            record.get("trade_date"),
            record.get("snapshot_time"),
            record.get("identity_key"),
            record.get("exchange"),
            record.get("code"),
            record.get("display_code"),
            record.get("name"),
            record.get("open"),
            record.get("high"),
            record.get("low"),
            record.get("close"),
            record.get("current_price"),
            record.get("pre_close"),
            record.get("volume"),
            record.get("amount"),
            record.get("source_adapter"),
            record.get("source_version"),
            record.get("quality_status"),
            record.get("source_scope_ids", []),
            record.get("source_condition_pool_ids", []),
            record.get("raw_json"),
        ]
        placeholders = ", ".join(["%s"] * len(columns))
        update_columns = (
            "open",
            "high",
            "low",
            "close",
            "current_price",
            "pre_close",
            "volume",
            "amount",
            "source_version",
            "quality_status",
            "source_scope_ids",
            "source_condition_pool_ids",
            "raw_json",
        )
        assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
        self.cursor.execute(
            f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (run_id, trade_date, {identity_column}, snapshot_time, source_adapter)
            DO UPDATE SET {assignments}
            RETURNING {id_column}
            """,
            values,
        )
        return fetch_returned_id(self.cursor, id_column)


class MinuteBarRepository:
    """Repository for stock/index/board 1 minute bar facts."""

    required_fields = (
        "asset_kind",
        "run_id",
        "subscription_id",
        "source_condition_run_id",
        "for_trade_date",
        "trade_date",
        "bar_time",
        "identity_key",
        "exchange",
        "code",
        "source_adapter",
        "quality_status",
    )

    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def upsert_minute_bar(self, record: Mapping[str, Any]) -> int:
        require_fields(record, self.required_fields)
        asset_kind = str(record["asset_kind"])
        require_asset_kind(asset_kind)
        table_name, identity_column, id_column = ASSET_FACT_TABLES[asset_kind]["minute"]
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
            record.get("run_id"),
            record.get("subscription_id"),
            record.get("source_condition_run_id"),
            record.get("for_trade_date"),
            record.get("trade_date"),
            record.get("bar_time"),
            record.get("identity_key"),
            record.get("exchange"),
            record.get("code"),
            record.get("display_code"),
            record.get("name"),
            record.get("open"),
            record.get("high"),
            record.get("low"),
            record.get("close"),
            record.get("volume"),
            record.get("amount"),
            record.get("source_adapter"),
            record.get("source_version"),
            record.get("quality_status"),
            record.get("is_previous_day_preload", False),
            record.get("source_scope_ids", []),
            record.get("source_condition_pool_ids", []),
            record.get("raw_json"),
        ]
        placeholders = ", ".join(["%s"] * len(columns))
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
        self.cursor.execute(
            f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (run_id, trade_date, {identity_column}, bar_time, source_adapter)
            DO UPDATE SET {assignments}
            RETURNING {id_column}
            """,
            values,
        )
        return fetch_returned_id(self.cursor, id_column)


class PreloadStatusRepository:
    """Repository for stock/index/board previous-day minute preload status."""

    required_fields = (
        "asset_kind",
        "run_id",
        "subscription_id",
        "source_condition_run_id",
        "for_trade_date",
        "trade_date",
        "identity_key",
        "exchange",
        "code",
        "source_adapter",
        "status",
        "quality_status",
    )

    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def upsert_preload_status(self, record: Mapping[str, Any]) -> int:
        require_fields(record, self.required_fields)
        asset_kind = str(record["asset_kind"])
        require_asset_kind(asset_kind)
        table_name, identity_column, id_column = ASSET_FACT_TABLES[asset_kind]["preload_status"]
        columns = (
            "run_id",
            "subscription_id",
            "source_condition_run_id",
            "for_trade_date",
            "trade_date",
            identity_column,
            "exchange",
            "code",
            "display_code",
            "name",
            "expected_bar_count",
            "actual_bar_count",
            "missing_bar_count",
            "first_bar_time",
            "last_bar_time",
            "status",
            "quality_status",
            "source_adapter",
            "error_message",
            "source_scope_ids",
            "source_condition_pool_ids",
            "raw_json",
        )
        values = [
            record.get("identity_key") if column == identity_column else record.get(column)
            for column in columns
        ]
        placeholders = ", ".join(["%s"] * len(columns))
        update_columns = (
            "subscription_id",
            "display_code",
            "name",
            "expected_bar_count",
            "actual_bar_count",
            "missing_bar_count",
            "first_bar_time",
            "last_bar_time",
            "status",
            "quality_status",
            "error_message",
            "source_scope_ids",
            "source_condition_pool_ids",
            "raw_json",
            "updated_at",
        )
        assignments = ", ".join(
            "updated_at = now()" if column == "updated_at" else f"{column} = EXCLUDED.{column}"
            for column in update_columns
        )
        self.cursor.execute(
            f"""
            INSERT INTO {table_name} ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (run_id, trade_date, {identity_column}, source_adapter)
            DO UPDATE SET {assignments}
            RETURNING {id_column}
            """,
            values,
        )
        return fetch_returned_id(self.cursor, id_column)


class QualityRepository:
    """Repository for N3 market data quality/status facts."""

    required_fields = (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "data_domain",
        "layer_scope",
        "gate_code",
        "gate_name",
        "severity",
        "status",
    )

    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def insert_quality_item(self, record: Mapping[str, Any]) -> int:
        require_fields(record, self.required_fields)
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
        values = [record.get(column) for column in columns]
        placeholders = ", ".join(["%s"] * len(columns))
        self.cursor.execute(
            f"""
            INSERT INTO common_market_data_quality_item ({", ".join(columns)})
            VALUES ({placeholders})
            RETURNING quality_item_id
            """,
            values,
        )
        return fetch_returned_id(self.cursor, "quality_item_id")
