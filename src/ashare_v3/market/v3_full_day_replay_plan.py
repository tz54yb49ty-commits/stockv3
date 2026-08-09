"""V3-only full-day N3 data and metric readiness planning.

This module is intentionally read-only.  It audits V3 runtime coverage for a
trade date and produces contract/preflight artifacts for N3 backfill and
action-confirmation metric gates.  It never generates N4/N5 lineage, reads the
old target-machine database, or writes runtime facts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN

from ashare_v3.market.previous_day_preload_execute import bulk_upsert_minute_bars
from ashare_v3.market.action_confirmation_projection_execute import insert_action_confirmation_metric_rows
from ashare_v3.market.realtime_virtual_metric import (
    VIRTUAL_AMOUNT_POLICY_VERSION,
    _build_formal_amount_chain_fields as build_formal_amount_chain_fields,
    build_realtime_virtual_metric,
    convert_formal_source_amount_to_yuan,
    formal_amount_unit_rule_for_asset_kind,
)
from ashare_v3.market.v3_realtime_virtual_metric_writer import build_action_confirmation_metric_row


FOR_TRADE_DATE = "20260612"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260611_source_20260611_for_20260612_v1"
TRIGGER_CONTEXT_RUN_ID = "trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1"
LIMITED_METRIC_RUN_ID = (
    "action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__"
    "condition_layer_20260611_source_20260611_for_20260612_v1"
)
FULL_DAY_1M_BACKFILL_RUN_ID = "v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1"
FULL_DAY_PREVIOUS_1M_BACKFILL_RUN_ID = "v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1"
FULL_DAY_METRIC_RUN_ID = "v3_n3_action_confirmation_metric_20260612_full_day_replay_v1"
FULL_DAY_METRIC_SCHEMA_VERSION = "v3.realtime_virtual_metric.writer.contract.v1"
TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION = "n3.action_confirmation_metric.true_full_day_minute_series.v1"
FULL_DAY_PERIOD_TOTAL_UNITS = {"D": 1, "W": 5, "M": 20, "Q": 60, "Y": 240}
FULL_DAY_PREVIOUS_MINUTE_RUN_ID = FULL_DAY_PREVIOUS_1M_BACKFILL_RUN_ID

ASSET_CONFIG = {
    "stock": {
        "scope_table": "stock_minute_target_scope",
        "scope_identity_column": "stock_identity_key",
        "context_table": "stock_trigger_context_snapshot",
        "minute_table": "stock_minute_bar_1m",
        "minute_identity_column": "stock_identity_key",
        "metric_table": "stock_action_confirmation_projection_metric",
    },
    "index": {
        "scope_table": "index_minute_target_scope",
        "scope_identity_column": "index_identity_key",
        "context_table": "index_trigger_context_snapshot",
        "minute_table": "index_minute_bar_1m",
        "minute_identity_column": "index_identity_key",
        "metric_table": "index_action_confirmation_projection_metric",
    },
    "board": {
        "scope_table": "board_minute_target_scope",
        "scope_identity_column": "board_identity_key",
        "context_table": "board_trigger_context_snapshot",
        "minute_table": "board_minute_bar_1m",
        "minute_identity_column": "board_identity_key",
        "metric_table": "board_action_confirmation_projection_metric",
    },
}

ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
FULL_DAY_EXPECTED_1M_BAR_COUNT = 240
RETAINED_SOURCE_ADAPTER = "v3_retained_minute_bar_1m"
BACKFILL_SOURCE_ADAPTER = "mootdx_full_day_1m_backfill"
FULL_CONTEXT_FORMAL_ALLOWED_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_action_confirmation_projection_metric",
    "index_action_confirmation_projection_metric",
    "board_action_confirmation_projection_metric",
]
FULL_CONTEXT_FORMAL_REQUIRED_PROOF_FIELDS = [
    "formal_period_amount_proof",
    "formal_amount_chain_metrics",
    "D/W/M/Q/Y virtual amount proof fields",
    "n4_formal_trigger_period_proof_equivalent_envelope",
]


@dataclass(frozen=True)
class FullContextFormalMetricLineage:
    for_trade_date: str
    source_trade_date: str
    previous_trade_date: str
    source_condition_run_id: str
    source_subscription_run_id: str
    source_today_minute_run_id: str
    source_previous_day_minute_run_id: str
    trigger_context_run_id: str
    projection_run_id: str
    source_snapshot_run_id: str | None = None
    projection_schema_version: str = TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION

    @property
    def resolved_source_snapshot_run_id(self) -> str:
        return self.source_snapshot_run_id or self.source_today_minute_run_id

    def source_scope(self) -> dict[str, str]:
        return {
            "for_trade_date": self.for_trade_date,
            "source_trade_date": self.source_trade_date,
            "previous_trade_date": self.previous_trade_date,
            "source_condition_run_id": self.source_condition_run_id,
            "source_subscription_run_id": self.source_subscription_run_id,
            "source_snapshot_run_id": self.resolved_source_snapshot_run_id,
            "source_today_minute_run_id": self.source_today_minute_run_id,
            "source_previous_day_minute_run_id": self.source_previous_day_minute_run_id,
            "trigger_context_run_id": self.trigger_context_run_id,
        }


class FullDayBackfillBlocked(RuntimeError):
    """Raised when the V3 full-day 1m backfill gate is blocked."""


class FullDayMetricBlocked(RuntimeError):
    """Raised when the V3 full-day action-confirmation metric gate is blocked."""


def require_full_day_backfill_execute_flags(*, execute: bool, user_confirmed: bool) -> None:
    if not execute:
        raise FullDayBackfillBlocked("V3 full-day 1m backfill blocked: missing --execute")
    if not user_confirmed:
        raise FullDayBackfillBlocked("V3 full-day 1m backfill blocked: missing --user-confirmed")


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _asset_kind(identity_key: str) -> str:
    return str(identity_key).split(":", 1)[0]


def _identity_from_row(row: Mapping[str, Any]) -> str:
    return str(
        row.get("identity_key")
        or row.get("stock_identity_key")
        or row.get("index_identity_key")
        or row.get("board_identity_key")
        or ""
    )


def _identity_counter(rows: Sequence[Mapping[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        identity = _identity_from_row(row)
        if identity:
            counter[identity] += 1
    return counter


def _coverage_map(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = _identity_from_row(row)
        if not identity:
            continue
        row_count = int(row.get("row_count") or row.get("rows") or 0)
        rows_before_focus = int(row.get("rows_before_focus") or row.get("rows_before_focus_minute") or 0)
        existing = output.setdefault(
            identity,
            {
                "asset_kind": str(row.get("asset_kind") or _asset_kind(identity)),
                "identity_key": identity,
                "row_count": 0,
                "rows_before_focus": 0,
                "min_time": row.get("min_time") or row.get("min_bar_time") or row.get("min_label"),
                "max_time": row.get("max_time") or row.get("max_bar_time") or row.get("max_label"),
            },
        )
        existing["row_count"] += row_count
        existing["rows_before_focus"] += rows_before_focus
    return output


def count_by_asset(identity_keys: Sequence[str]) -> dict[str, int]:
    counts = Counter(_asset_kind(identity) for identity in identity_keys)
    return {asset: counts.get(asset, 0) for asset in ASSET_CONFIG}


def forbidden_scope_proof() -> dict[str, bool]:
    return {
        "old_system_read": False,
        "database_written": False,
        "outbox_inbox_checkpoint_consumed_or_updated": False,
        "n4_executed": False,
        "n5_executed": False,
        "n6_voice_mobile_sim_trade_touched": False,
        "scheduler_or_worker_started": False,
    }


def _normalize_bar_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=ASIA_SHANGHAI)
        return value.astimezone(ASIA_SHANGHAI)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ASIA_SHANGHAI)
    return parsed.astimezone(ASIA_SHANGHAI)


def _context_source_ids(row: Mapping[str, Any], key: str) -> list[int]:
    raw = row.get(key) or []
    if isinstance(raw, (list, tuple)):
        return [int(item) for item in raw if item is not None]
    if raw is None:
        return []
    return [int(raw)]


def _base_backfill_record(
    *,
    context_row: Mapping[str, Any],
    backfill_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    minute_trade_date: str,
    is_previous_day_preload: bool,
    bar_row: Mapping[str, Any],
    source_adapter: str,
    source_version: str,
    source_policy: str,
    raw_json_extra: Mapping[str, Any],
) -> dict[str, Any]:
    raw_payload = bar_row.get("raw_payload")
    raw_json = {
        "stage": "V3_20260612_N3_FULL_DAY_1M_BACKFILL",
        "source_policy": source_policy,
        "backfill_run_id": backfill_run_id,
        "writes_outbox": False,
        "minute_trade_date": minute_trade_date,
        "is_previous_day_preload": is_previous_day_preload,
        "raw_payload": raw_payload if isinstance(raw_payload, Mapping) else {},
        **dict(raw_json_extra),
    }
    return {
        "run_id": backfill_run_id,
        "subscription_id": context_row.get("source_market_subscription_id"),
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "trade_date": minute_trade_date,
        "bar_time": _normalize_bar_time(bar_row["bar_time"]),
        "identity_key": context_row["identity_key"],
        "exchange": context_row["exchange"],
        "code": context_row["code"],
        "display_code": context_row.get("display_code") or context_row.get("code"),
        "name": context_row.get("name") or context_row.get("identity_key"),
        "open": bar_row.get("open"),
        "high": bar_row.get("high"),
        "low": bar_row.get("low"),
        "close": bar_row.get("close"),
        "volume": bar_row.get("volume"),
        "amount": bar_row.get("amount"),
        "source_adapter": source_adapter,
        "source_version": source_version,
        "quality_status": "passed",
        "is_previous_day_preload": is_previous_day_preload,
        "source_scope_ids": _context_source_ids(context_row, "source_scope_ids"),
        "source_condition_pool_ids": _context_source_ids(context_row, "source_condition_pool_ids"),
        "raw_json": raw_json,
    }


def build_full_day_backfill_records_for_context(
    *,
    context_rows: Sequence[Mapping[str, Any]],
    retained_rows_by_identity: Mapping[str, Sequence[Mapping[str, Any]]],
    adapter_rows_by_identity: Mapping[str, Sequence[Mapping[str, Any]]],
    backfill_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    minute_trade_date: str | None = None,
    is_previous_day_preload: bool = False,
    transport_provenance: Mapping[str, Any] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Build scoped full-day 1m records without touching the database.

    Existing V3 minute rows are preferred when they already provide a complete
    full-day record for an identity.  Missing/partial identities must be supplied
    by the approved adapter rows.
    """

    minute_trade_date = minute_trade_date or for_trade_date
    transport_provenance = dict(transport_provenance or {})
    records_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_CONFIG}
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for context_row in context_rows:
        identity = str(context_row["identity_key"])
        if identity in seen:
            continue
        seen.add(identity)
        asset_kind = str(context_row["asset_kind"])
        retained = list(retained_rows_by_identity.get(identity) or [])
        adapter_rows = list(adapter_rows_by_identity.get(identity) or [])
        if len(retained) >= FULL_DAY_EXPECTED_1M_BAR_COUNT:
            source_rows = retained
            source_policy = "retained_v3_minute_fact"
            source_adapter = RETAINED_SOURCE_ADAPTER
            source_version = "v3.runtime.retained.20260612"
            extra = {
                "retained_from_run_id": retained[0].get("source_run_id"),
                "retained_row_count": len(retained),
            }
        else:
            source_rows = adapter_rows
            source_policy = "mootdx_full_day_backfill"
            source_adapter = BACKFILL_SOURCE_ADAPTER
            source_version = "mootdx.bars.full_day_1m.frequency8.offset800"
            extra = {
                "retained_row_count": len(retained),
                "adapter_row_count": len(adapter_rows),
            }
        built_rows = [
            _base_backfill_record(
                context_row=context_row,
                backfill_run_id=backfill_run_id,
                source_condition_run_id=source_condition_run_id,
                for_trade_date=for_trade_date,
                minute_trade_date=minute_trade_date,
                is_previous_day_preload=is_previous_day_preload,
                bar_row=row,
                source_adapter=source_adapter,
                source_version=source_version,
                source_policy=source_policy,
                raw_json_extra={
                    **extra,
                    "source_bar_id": row.get("source_bar_id"),
                    "source_run_id": row.get("source_run_id"),
                    **(transport_provenance if source_policy == "mootdx_full_day_backfill" else {}),
                },
            )
            for row in source_rows
        ]
        records_by_asset.setdefault(asset_kind, []).extend(built_rows)
        results.append(
            {
                "asset_kind": asset_kind,
                "identity_key": identity,
                "source_policy": source_policy,
                "retained_row_count": len(retained),
                "adapter_row_count": len(adapter_rows),
                "minute_rows_written": len(built_rows),
                "status": "passed" if len(built_rows) >= FULL_DAY_EXPECTED_1M_BAR_COUNT else "missing",
                "transport_provenance": (
                    transport_provenance if source_policy == "mootdx_full_day_backfill" else {}
                ),
            }
        )
    return records_by_asset, results


def fetch_full_day_backfill_context_rows(
    *,
    dsn: str = DEFAULT_DSN,
    trigger_context_run_id: str = TRIGGER_CONTEXT_RUN_ID,
    for_trade_date: str = FOR_TRADE_DATE,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            for asset_kind, cfg in ASSET_CONFIG.items():
                table_name = cfg["context_table"]
                cur.execute(
                    f"""
                    SELECT %s AS asset_kind,
                           identity_key,
                           exchange,
                           code,
                           max(display_code) AS display_code,
                           max(name) AS name,
                           min(source_market_subscription_id) AS source_market_subscription_id,
                           array_agg(DISTINCT source_minute_target_scope_id ORDER BY source_minute_target_scope_id) AS source_scope_ids,
                           array_agg(DISTINCT source_condition_pool_id ORDER BY source_condition_pool_id) AS source_condition_pool_ids
                    FROM {table_name}
                    WHERE run_id = %s AND for_trade_date = %s
                    GROUP BY identity_key, exchange, code
                    ORDER BY identity_key
                    """,
                    (asset_kind, trigger_context_run_id, for_trade_date),
                )
                rows.extend(dict(row) for row in cur.fetchall())
    return rows


def fetch_retained_today_minute_rows_by_identity(
    *,
    dsn: str = DEFAULT_DSN,
    for_trade_date: str = FOR_TRADE_DATE,
    minute_trade_date: str | None = None,
    is_previous_day_preload: bool = False,
    identities_by_asset: Mapping[str, Sequence[str]],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    minute_trade_date = minute_trade_date or for_trade_date
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            for asset_kind, identities in identities_by_asset.items():
                identity_list = list(dict.fromkeys(str(item) for item in identities))
                if not identity_list:
                    continue
                cfg = ASSET_CONFIG[asset_kind]
                table_name = cfg["minute_table"]
                identity_col = cfg["minute_identity_column"]
                cur.execute(
                    f"""
                    SELECT DISTINCT ON ({identity_col}, bar_time)
                           {identity_col} AS identity_key,
                           bar_id AS source_bar_id,
                           run_id AS source_run_id,
                           bar_time,
                           open, high, low, close, volume, amount,
                           source_adapter AS retained_source_adapter,
                           source_version AS retained_source_version,
                           quality_status,
                           raw_json AS raw_payload
                    FROM {table_name}
                    WHERE trade_date = %s
                      AND is_previous_day_preload = %s
                      AND {identity_col} = ANY(%s)
                    ORDER BY {identity_col}, bar_time,
                             CASE WHEN quality_status = 'passed' THEN 0 ELSE 1 END,
                             created_at DESC
                    """,
                    (minute_trade_date, is_previous_day_preload, identity_list),
                )
                for row in cur.fetchall():
                    item = dict(row)
                    output.setdefault(str(item["identity_key"]), []).append(item)
    for items in output.values():
        items.sort(key=lambda item: _normalize_bar_time(item["bar_time"]))
    return output


def capture_full_day_backfill_counts(
    *,
    dsn: str = DEFAULT_DSN,
    backfill_run_id: str = FULL_DAY_1M_BACKFILL_RUN_ID,
    for_trade_date: str = FOR_TRADE_DATE,
    minute_trade_date: str | None = None,
    is_previous_day_preload: bool = False,
) -> dict[str, Any]:
    minute_trade_date = minute_trade_date or for_trade_date
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            table_counts: dict[str, int] = {}
            for table_name in (
                "common_market_data_run",
                "common_market_data_quality_item",
                "stock_minute_bar_1m",
                "index_minute_bar_1m",
                "board_minute_bar_1m",
            ):
                cur.execute(f"SELECT count(*)::bigint AS c FROM {table_name} WHERE run_id = %s", (backfill_run_id,))
                table_counts[table_name] = int(cur.fetchone()["c"])
            by_asset: dict[str, dict[str, int]] = {}
            for asset_kind, cfg in ASSET_CONFIG.items():
                table_name = cfg["minute_table"]
                identity_col = cfg["minute_identity_column"]
                cur.execute(
                    f"""
                    SELECT count(*)::bigint AS row_count,
                           count(DISTINCT {identity_col})::bigint AS object_count
                    FROM {table_name}
                    WHERE run_id = %s AND trade_date = %s AND is_previous_day_preload = %s
                    """,
                    (backfill_run_id, minute_trade_date, is_previous_day_preload),
                )
                row = cur.fetchone()
                by_asset[asset_kind] = {
                    "row_count": int(row["row_count"]),
                    "object_count": int(row["object_count"]),
                }
            cur.execute(
                """
                SELECT count(*)::bigint AS c
                FROM common_event_outbox
                WHERE source_run_id = %s OR payload_json::text LIKE %s
                """,
                (backfill_run_id, f"%{backfill_run_id}%"),
            )
            outbox_refs = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*)::bigint AS c
                FROM common_event_inbox
                WHERE source_run_id = %s OR payload_json::text LIKE %s OR raw_json::text LIKE %s
                """,
                (backfill_run_id, f"%{backfill_run_id}%", f"%{backfill_run_id}%"),
            )
            inbox_refs = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*)::bigint AS c
                FROM common_event_consumer_checkpoint
                WHERE checkpoint_payload::text LIKE %s
                """,
                (f"%{backfill_run_id}%",),
            )
            checkpoint_refs = int(cur.fetchone()["c"])
    return {
        "table_counts": table_counts,
        "minute_counts_by_asset": by_asset,
        "event_refs": {
            "outbox": outbox_refs,
            "inbox": inbox_refs,
            "checkpoint": checkpoint_refs,
        },
    }


def _build_full_day_quality_items(
    *,
    backfill_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    object_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    counts = Counter(str(row.get("status")) for row in object_results)
    hard_failed = [row for row in object_results if row.get("status") not in {"passed", "missing"}]
    missing = [row for row in object_results if row.get("status") == "missing"]
    items = [
        {
            "run_id": backfill_run_id,
            "source_condition_run_id": source_condition_run_id,
            "for_trade_date": for_trade_date,
            "source_trade_date": source_trade_date,
            "data_domain": "common",
            "layer_scope": "market_data_run",
            "table_name": None,
            "gate_code": "v3_full_day_1m_backfill_object_coverage",
            "gate_name": "V3 full-day 1m backfill object coverage",
            "severity": "P0" if hard_failed else "P1",
            "status": "failed" if hard_failed else "warning" if missing else "passed",
            "expected_value": "all context objects have 240 1m rows",
            "actual_value": json.dumps(dict(counts), ensure_ascii=False, sort_keys=True),
            "identity_key": None,
            "details": {
                "object_status_counts": dict(counts),
                "hard_failed_sample": [dict(row) for row in hard_failed[:20]],
                "missing_source_sample": [dict(row) for row in missing[:20]],
                "missing_source_policy": "quality_visible; downstream N4 must emit TriggerPendingMarketData, never fabricate TriggerMatched",
            },
        }
    ]
    retained_count = sum(1 for row in object_results if row.get("source_policy") == "retained_v3_minute_fact")
    adapter_count = sum(1 for row in object_results if row.get("source_policy") == "mootdx_full_day_backfill")
    items.append(
        {
            "run_id": backfill_run_id,
            "source_condition_run_id": source_condition_run_id,
            "for_trade_date": for_trade_date,
            "source_trade_date": source_trade_date,
            "data_domain": "common",
            "layer_scope": "market_data_run",
            "table_name": None,
            "gate_code": "v3_full_day_1m_backfill_source_policy",
            "gate_name": "V3 full-day 1m retained plus adapter source policy",
            "severity": "P1",
            "status": "passed",
            "expected_value": "retained rows or approved adapter rows only",
            "actual_value": f"retained={retained_count};adapter={adapter_count}",
            "identity_key": None,
            "details": {
                "retained_object_count": retained_count,
                "adapter_object_count": adapter_count,
                "old_system_read": False,
            },
        }
    )
    return items


def _insert_full_day_quality_items(cur: Any, quality_items: Sequence[Mapping[str, Any]]) -> int:
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
    values = [
        tuple(Jsonb(item[column]) if column == "details" else item.get(column) for column in columns)
        for item in quality_items
    ]
    cur.executemany(
        f"""
        INSERT INTO common_market_data_quality_item ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        values,
    )
    return len(values)


def _p_counts(quality_items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item.get("severity")) for item in quality_items if item.get("status") != "passed")
    return {"P0": counts.get("P0", 0), "P1": counts.get("P1", 0), "P2": counts.get("P2", 0)}


def write_full_day_backfill_to_db(
    *,
    dsn: str,
    backfill_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    minute_trade_date: str | None = None,
    is_previous_day_preload: bool = False,
    source_trade_date: str,
    prev_trade_date: str,
    records_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    object_results: Sequence[Mapping[str, Any]],
    transport_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    minute_trade_date = minute_trade_date or for_trade_date
    transport_provenance = dict(transport_provenance or {})
    pre_counts = capture_full_day_backfill_counts(
        dsn=dsn,
        backfill_run_id=backfill_run_id,
        for_trade_date=for_trade_date,
        minute_trade_date=minute_trade_date,
        is_previous_day_preload=is_previous_day_preload,
    )
    dirty = {key: value for key, value in pre_counts["table_counts"].items() if int(value or 0) != 0}
    if dirty or any(int(v or 0) != 0 for v in pre_counts["event_refs"].values()):
        raise FullDayBackfillBlocked(f"V3 full-day 1m backfill blocked: target run not clean: {pre_counts}")
    quality_items = _build_full_day_quality_items(
        backfill_run_id=backfill_run_id,
        source_condition_run_id=source_condition_run_id,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        object_results=object_results,
    )
    p_counts = _p_counts(quality_items)
    if p_counts["P0"]:
        raise FullDayBackfillBlocked("V3 full-day 1m backfill blocked: object coverage has P0 failures")
    object_count = len({str(row.get("identity_key")) for row in object_results})
    total_rows = sum(len(rows) for rows in records_by_asset.values())
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
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
                            %s, %s, %s, %s, 1.0, 'V3-full-day-1m-backfill',
                            true, false, false, false, now(), %s)
                    """,
                    (
                        backfill_run_id,
                        source_condition_run_id,
                        for_trade_date,
                        source_trade_date,
                        prev_trade_date,
                        object_count,
                        object_count,
                        object_count,
                        object_count,
                        Jsonb(
                            {
                                "stage": "V3_20260612_N3_FULL_DAY_1M_BACKFILL",
                                "records_planned": total_rows,
                                "writes_outbox": False,
                                "old_system_read": False,
                                "transport_provenance": transport_provenance,
                            }
                        ),
                    ),
                )
                for asset_kind in ASSET_CONFIG:
                    rows = list(records_by_asset.get(asset_kind) or [])
                    for offset in range(0, len(rows), 5000):
                        bulk_upsert_minute_bars(cur, asset_kind, rows[offset : offset + 5000])
                _insert_full_day_quality_items(cur, quality_items)
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
                                    "status_counts": dict(Counter(str(row.get("status")) for row in object_results)),
                                    "source_policy_counts": dict(
                                        Counter(str(row.get("source_policy")) for row in object_results)
                                    ),
                                },
                                "transport_provenance": transport_provenance,
                            }
                        ),
                        backfill_run_id,
                    ),
                )
    post_counts = capture_full_day_backfill_counts(
        dsn=dsn,
        backfill_run_id=backfill_run_id,
        for_trade_date=for_trade_date,
        minute_trade_date=minute_trade_date,
        is_previous_day_preload=is_previous_day_preload,
    )
    return {
        "pre_counts": pre_counts,
        "post_counts": post_counts,
        "quality_items": quality_items,
        "p_counts": p_counts,
        "records_planned": total_rows,
    }


def format_full_day_backfill_execute_report(report: Mapping[str, Any]) -> str:
    post = report.get("post_counts") or {}
    lines = [
        "# V3 20260612 N3 Full-Day 1m Backfill Execute Report",
        "",
        f"- result: `{report.get('result')}`",
        f"- backfill_run_id: `{report.get('backfill_run_id')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- P0/P1/P2: `{report.get('P0_P1_P2')}`",
        f"- records planned: `{report.get('records_planned')}`",
        f"- minute counts by asset: `{post.get('minute_counts_by_asset')}`",
        f"- event refs: `{post.get('event_refs')}`",
        "",
        "## Boundary",
        "",
        "- writes_outbox: `false`",
        "- N4/N5/N6 executed: `false`",
        "- old system read: `false`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def require_full_day_metric_execute_flags(*, execute: bool, user_confirmed: bool) -> None:
    if not execute:
        raise FullDayMetricBlocked("V3 full-day action-confirmation metric blocked: missing --execute")
    if not user_confirmed:
        raise FullDayMetricBlocked("V3 full-day action-confirmation metric blocked: missing --user-confirmed")


def period_key_for_trade_date(trade_date: Any, period: str) -> str | None:
    try:
        value = datetime.strptime(str(trade_date), "%Y%m%d")
    except (TypeError, ValueError):
        return None
    if period == "W":
        iso_year, iso_week, _ = value.isocalendar()
        return f"{iso_year}W{iso_week:02d}"
    if period == "M":
        return value.strftime("%Y%m")
    if period == "Q":
        quarter = ((value.month - 1) // 3) + 1
        return f"{value.year}Q{quarter}"
    if period == "Y":
        return str(value.year)
    if period == "D":
        return value.strftime("%Y%m%d")
    return None


def period_seed_guard(
    *,
    period: str,
    item: Mapping[str, Any],
    source_trade_date: Any,
    for_trade_date: Any,
) -> dict[str, Any]:
    if period == "D":
        return {
            "period_key_source": "not_applicable_for_D",
            "source_period_key": period_key_for_trade_date(source_trade_date, period),
            "for_period_key": period_key_for_trade_date(for_trade_date, period),
            "baseline_period_key_current": item.get("period_key_current"),
            "period_seed_applied": False,
            "period_seed_reset_reason": "D_today_minute_sum_only",
            "period_key_guard_pass": True,
        }
    source_period_key = period_key_for_trade_date(source_trade_date, period)
    for_period_key = period_key_for_trade_date(for_trade_date, period)
    baseline_period_key_current = item.get("period_key_current")
    reset_reason = None
    if not source_period_key or not for_period_key:
        reset_reason = "period_key_unavailable"
    elif source_period_key != for_period_key:
        reset_reason = "source_period_key_mismatch_for_trade_date"
    elif baseline_period_key_current and str(baseline_period_key_current) != for_period_key:
        reset_reason = "baseline_period_key_mismatch_for_trade_date"
    return {
        "period_key_source": "source_trade_date_for_trade_date_guard",
        "source_period_key": source_period_key,
        "for_period_key": for_period_key,
        "baseline_period_key_current": baseline_period_key_current,
        "period_seed_applied": reset_reason is None,
        "period_seed_reset_reason": reset_reason,
        "period_key_guard_pass": reset_reason is None,
    }


def higher_period_context_from_trigger_context(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize N4 localized N2 period baselines for the N3 metric builder."""

    raw_json = row.get("raw_json") or {}
    baseline = {}
    if isinstance(raw_json, Mapping):
        baseline = dict(raw_json.get("period_trigger_baseline_json") or {})
    if not baseline and isinstance(row.get("period_trigger_baseline_json"), Mapping):
        baseline = dict(row.get("period_trigger_baseline_json") or {})
    periods = baseline.get("periods") if isinstance(baseline, Mapping) else {}
    periods = periods if isinstance(periods, Mapping) else {}
    output: dict[str, dict[str, Any]] = {}
    for period, total_units in FULL_DAY_PERIOD_TOTAL_UNITS.items():
        item = dict(periods.get(period) or {})
        guard = period_seed_guard(
            period=period,
            item=item,
            source_trade_date=row.get("source_trade_date"),
            for_trade_date=row.get("for_trade_date"),
        )
        current_open = item.get("current_open")
        if current_open is None:
            current_open = item.get("current_open_seed")
        previous_open = item.get("previous_open")
        previous_close = item.get("previous_close")
        previous_amount = item.get("previous_amount")
        if previous_amount is None:
            previous_amount = item.get("previous_amount_baseline") or item.get("previous_avg_amount")
        previous_avg_amount = item.get("previous_avg_amount")
        if previous_avg_amount is None:
            previous_avg_amount = item.get("classification_previous_amount_baseline")
        elapsed_units = item.get("elapsed_units")
        if elapsed_units is None:
            elapsed_units = item.get("current_trade_days_seed")
        seed_applied = bool(guard.get("period_seed_applied"))
        current_amount_seed = item.get("current_amount_seed") or 0
        current_amount_total_seed = item.get("current_amount_total_seed")
        current_trade_days_seed = item.get("current_trade_days_seed") or elapsed_units or 0
        if period != "D" and not seed_applied:
            current_amount_seed = 0
            current_amount_total_seed = 0
            current_trade_days_seed = 0
            elapsed_units = 0
        output[period] = {
            "baseline_source": "N2_period_trigger_baseline_json",
            "baseline_source_trade_date": item.get("baseline_source_trade_date")
            or item.get("baseline_source_trade_date")
            or item.get("baseline_source_trade_date")
            or item.get("baseline_source_trade_date")
            or item.get("baseline_source_trade_date")
            or row.get("source_trade_date"),
            "period_key_current": item.get("period_key_current"),
            "period_key_previous": item.get("period_key_previous"),
            "freshness_status": item.get("freshness_status"),
            "current_open": current_open,
            "previous_open": previous_open,
            "previous_close": previous_close,
            "previous_amount": previous_amount,
            "previous_avg_amount": previous_avg_amount,
            "current_amount_seed": current_amount_seed,
            "current_amount_total_seed": current_amount_total_seed,
            "current_trade_days_seed": current_trade_days_seed,
            "elapsed_units": elapsed_units or 0,
            "total_units": total_units,
            **guard,
        }
    return output


def fetch_full_day_metric_context_rows(
    *,
    dsn: str = DEFAULT_DSN,
    trigger_context_run_id: str = TRIGGER_CONTEXT_RUN_ID,
    for_trade_date: str = FOR_TRADE_DATE,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            for asset_kind, cfg in ASSET_CONFIG.items():
                table_name = cfg["context_table"]
                cur.execute(
                    f"""
                    SELECT DISTINCT ON (identity_key)
                           %s AS asset_kind,
                           trigger_context_id,
                           run_id,
                           source_condition_run_id,
                           source_condition_pool_id,
                           source_condition_basis_id,
                           source_minute_target_scope_id,
                           source_market_subscription_id,
                           for_trade_date,
                           source_trade_date,
                           prev_trade_date,
                           identity_key,
                           exchange,
                           code,
                           display_code,
                           name,
                           raw_json
                    FROM {table_name}
                    WHERE run_id = %s AND for_trade_date = %s
                    ORDER BY identity_key, trigger_context_id
                    """,
                    (asset_kind, trigger_context_run_id, for_trade_date),
                )
                rows.extend(dict(row) for row in cur.fetchall())
    return rows


def fetch_full_day_metric_minute_rows_by_identity(
    *,
    dsn: str = DEFAULT_DSN,
    asset_kind: str,
    identities: Sequence[str],
    today_run_id: str = FULL_DAY_1M_BACKFILL_RUN_ID,
    previous_run_id: str = FULL_DAY_PREVIOUS_MINUTE_RUN_ID,
    for_trade_date: str = FOR_TRADE_DATE,
    previous_trade_date: str = "20260611",
) -> dict[str, list[dict[str, Any]]]:
    cfg = ASSET_CONFIG[asset_kind]
    table_name = cfg["minute_table"]
    identity_col = cfg["minute_identity_column"]
    identity_list = list(dict.fromkeys(str(item) for item in identities))
    if not identity_list:
        return {}
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {identity_col} AS identity_key,
                       bar_id,
                       run_id,
                       trade_date,
                       bar_time,
                       code,
                       open, high, low, close, amount,
                       raw_json
                FROM {table_name}
                WHERE {identity_col} = ANY(%s)
                  AND (
                    (run_id = %s AND trade_date = %s AND is_previous_day_preload = false)
                    OR
                    (run_id = %s AND trade_date = %s AND is_previous_day_preload = true)
                  )
                ORDER BY {identity_col}, bar_time
                """,
                (identity_list, today_run_id, for_trade_date, previous_run_id, previous_trade_date),
            )
            output: dict[str, list[dict[str, Any]]] = {}
            for row in cur.fetchall():
                item = dict(row)
                output.setdefault(str(item["identity_key"]), []).append(item)
    return output


def _minute_record_for_metric(row: Mapping[str, Any]) -> dict[str, Any]:
    bar_time = _normalize_bar_time(row["bar_time"])
    return {
        "source_bar_id": row.get("bar_id"),
        "source_run_id": row.get("run_id"),
        "trade_date": row.get("trade_date"),
        "code": str(row.get("code") or ""),
        "datetime": bar_time.strftime("%Y-%m-%d %H:%M"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "amount": row.get("amount"),
    }


def _metric_observed_at(row: Mapping[str, Any]) -> str:
    bar_time = _normalize_bar_time(row["bar_time"])
    return (bar_time.replace(second=0, microsecond=0) + timedelta(minutes=1)).isoformat()


def build_full_day_metric_rows_for_identity(
    *,
    context_row: Mapping[str, Any],
    minute_rows: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    for_trade_date: str = FOR_TRADE_DATE,
    source_today_minute_run_id: str = FULL_DAY_1M_BACKFILL_RUN_ID,
    source_previous_day_minute_run_id: str = FULL_DAY_PREVIOUS_MINUTE_RUN_ID,
    source_snapshot_run_id: str | None = None,
) -> list[dict[str, Any]]:
    resolved_source_snapshot_run_id = source_snapshot_run_id or source_today_minute_run_id
    records = [_minute_record_for_metric(row) for row in minute_rows]
    for record in records:
        record["_dt"] = datetime.strptime(str(record["datetime"]), "%Y-%m-%d %H:%M")
        record["open"] = float(record.get("open") or 0.0)
        record["high"] = float(record.get("high") or 0.0)
        record["low"] = float(record.get("low") or 0.0)
        record["close"] = float(record.get("close") or 0.0)
        record["amount"] = float(record.get("amount") or 0.0)
    records.sort(key=lambda row: row["_dt"])
    current_rows = [
        row
        for row in minute_rows
        if str(row.get("trade_date")) == for_trade_date and str(row.get("run_id")) == source_today_minute_run_id
    ]
    current_rows.sort(key=lambda row: _normalize_bar_time(row["bar_time"]))
    asset_kind = str(context_row.get("asset_kind") or _asset_kind(str(context_row.get("identity_key") or "")))
    amount_unit_rule = formal_amount_unit_rule_for_asset_kind(asset_kind)
    period_context_row = dict(context_row)
    period_context_row.setdefault("for_trade_date", for_trade_date)
    higher_context = higher_period_context_from_trigger_context(period_context_row)
    previous_by_dt: dict[datetime, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if index:
            previous_by_dt[record["_dt"]] = records[index - 1]

    dates = sorted({row["_dt"].strftime("%Y%m%d") for row in records})
    previous_trade_date = next((date for date in reversed(dates) if date < for_trade_date), None)
    records_by_date: dict[str, list[dict[str, Any]]] = {}
    intraday_amount_by_dt: dict[datetime, float] = {}
    for record in records:
        records_by_date.setdefault(record["_dt"].strftime("%Y%m%d"), []).append(record)
    running_amount = 0.0
    for record in records_by_date.get(for_trade_date, []):
        running_amount += float(record["amount"])
        intraday_amount_by_dt[record["_dt"]] = running_amount

    def seg(dt: datetime, period: int) -> int | None:
        hm = dt.hour * 60 + dt.minute
        if 9 * 60 + 31 <= hm <= 11 * 60 + 30:
            minute_no = hm - (9 * 60 + 30)
        elif hm == 13 * 60:
            minute_no = 120
        elif 13 * 60 + 1 <= hm <= 15 * 60:
            minute_no = 120 + hm - 13 * 60
        else:
            return None
        if period == 1:
            return minute_no - 1
        if period in (5, 30):
            return (minute_no - 1) // period
        if period == 120:
            return 0 if minute_no <= 120 else 1
        raise ValueError(period)

    def first_segment(dt: datetime, period: int) -> bool:
        index = seg(dt, period)
        return index == 0

    def aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        ordered = sorted((dict(row) for row in rows), key=lambda row: row["_dt"])
        return {
            "open": float(ordered[0]["open"]),
            "close": float(ordered[-1]["close"]),
            "amount": sum(float(row["amount"]) for row in ordered),
            "body_high": max(float(ordered[0]["open"]), float(ordered[-1]["close"])),
            "body_low": min(float(ordered[0]["open"]), float(ordered[-1]["close"])),
            "source_minute_refs": [str(row["datetime"]) for row in ordered],
        }

    grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for record in records:
        date = record["_dt"].strftime("%Y%m%d")
        for period in (1, 5, 30, 120):
            index = seg(record["_dt"], period)
            if index is not None:
                grouped.setdefault((date, period, index), []).append(record)
    aggregates = {key: aggregate(value) for key, value in grouped.items()}

    def previous_segment(current_dt: datetime, period: int) -> tuple[dict[str, Any] | None, str]:
        current_index = seg(current_dt, period)
        if current_index is None:
            return None, "not_available"
        if current_index > 0:
            value = aggregates.get((for_trade_date, period, current_index - 1))
            return value, "same_trade_date_previous_period" if value else "not_available"
        if previous_trade_date is None:
            return None, "not_available"
        previous_indexes = [key[2] for key in aggregates if key[0] == previous_trade_date and key[1] == period]
        if not previous_indexes:
            return None, "not_available"
        value = aggregates.get((previous_trade_date, period, max(previous_indexes)))
        return value, "previous_trade_date_last_period" if value else "not_available"

    def current_segment_rows(current_dt: datetime, period: int) -> list[dict[str, Any]]:
        index = seg(current_dt, period)
        if index is None:
            return []
        return [
            dict(row)
            for row in grouped.get((for_trade_date, period, index), [])
            if row["_dt"] <= current_dt
        ]

    def current_virtual(current_dt: datetime, period: int) -> tuple[float | None, float, list[str], dict[str, Any]]:
        rows = current_segment_rows(current_dt, period)
        current_elapsed_amount = sum(float(row["amount"]) for row in rows)
        previous, _ = previous_segment(current_dt, period)
        previous_amount = float(previous["amount"]) if previous else 0.0
        index = seg(current_dt, period)
        previous_same_rows = (
            list(grouped.get((previous_trade_date, period, index), []))
            if previous_trade_date is not None and index is not None
            else []
        )
        elapsed_count = len(rows)
        previous_elapsed_rows = previous_same_rows[:elapsed_count]
        previous_elapsed_amount = sum(float(row["amount"]) for row in previous_elapsed_rows)
        previous_same_full_amount = sum(float(row["amount"]) for row in previous_same_rows)
        proof = {
            "status": "passed",
            "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
            "period_minutes": period,
            "current_elapsed_amount": current_elapsed_amount,
            "current_elapsed_count": elapsed_count,
            "previous_day_same_elapsed_amount": previous_elapsed_amount,
            "previous_day_same_full_amount": previous_same_full_amount,
            "previous_day_same_elapsed_refs": [str(row["datetime"]) for row in previous_elapsed_rows],
            "previous_day_same_full_refs": [str(row["datetime"]) for row in previous_same_rows],
        }
        failure_reason = None
        if not rows:
            failure_reason = "current_elapsed_amount_missing"
        elif previous_trade_date is None:
            failure_reason = "previous_trade_date_missing"
        elif not previous_same_rows:
            failure_reason = "previous_day_same_window_full_amount_missing"
        elif len(previous_same_rows) < elapsed_count:
            failure_reason = "previous_day_same_elapsed_window_incomplete"
        elif previous_elapsed_amount <= 0:
            failure_reason = "previous_day_same_elapsed_amount_non_positive"
        elif previous_same_full_amount <= 0:
            failure_reason = "previous_day_same_full_amount_non_positive"
        if failure_reason:
            proof["status"] = "failed"
            proof["reason"] = failure_reason
            return None, previous_amount, [str(row["datetime"]) for row in rows], proof

        virtual = current_elapsed_amount / previous_elapsed_amount * previous_same_full_amount
        proof["current_virtual_amount"] = virtual
        return virtual, previous_amount, [str(row["datetime"]) for row in rows], proof

    def previous_day_same_window(current_dt: datetime, period: int) -> tuple[float | None, list[str]]:
        if previous_trade_date is None:
            return None, []
        index = seg(current_dt, period)
        if index is None:
            return None, []
        rows = grouped.get((previous_trade_date, period, index), [])
        if not rows:
            return None, []
        return sum(float(row["amount"]) for row in rows), [str(row["datetime"]) for row in rows]

    def intraday_amount_through(current_dt: datetime) -> float:
        return float(intraday_amount_by_dt.get(current_dt) or 0.0)

    def higher_fields(current_price: float, amount: float) -> tuple[dict[str, Any], dict[str, str]]:
        fields: dict[str, Any] = {}
        sources: dict[str, str] = {}
        for period, item in higher_context.items():
            db_period = period.lower()
            current_open = item.get("current_open")
            previous_open = item.get("previous_open")
            previous_close = item.get("previous_close")
            previous_amount = item.get("previous_amount")
            elapsed_units = float(item.get("elapsed_units") or 0.0)
            total_units = float(item.get("total_units") or 0.0)
            current_amount_seed = convert_formal_source_amount_to_yuan(
                item.get("current_amount_seed") or 0.0,
                amount_unit_rule=amount_unit_rule,
            )
            if current_open is None:
                fields[f"current_{db_period}_body_high"] = None
                fields[f"current_{db_period}_body_low"] = None
            else:
                current_open_f = float(current_open)
                fields[f"current_{db_period}_body_high"] = max(current_open_f, current_price)
                fields[f"current_{db_period}_body_low"] = min(current_open_f, current_price)
            if previous_open is None or previous_close is None:
                fields[f"previous_{db_period}_body_high"] = None
                fields[f"previous_{db_period}_body_low"] = None
            else:
                previous_open_f = float(previous_open)
                previous_close_f = float(previous_close)
                fields[f"previous_{db_period}_body_high"] = max(previous_open_f, previous_close_f)
                fields[f"previous_{db_period}_body_low"] = min(previous_open_f, previous_close_f)
            if period == "D":
                fields[f"current_{db_period}_virtual_amount"] = amount
                sources[period] = "today_minute_sum_only"
            elif item.get("period_seed_applied") is False:
                fields[f"current_{db_period}_virtual_amount"] = amount
                sources[period] = "for_trade_date_new_period_today_only"
            elif elapsed_units > 0 and total_units > 0:
                fields[f"current_{db_period}_virtual_amount"] = (float(current_amount_seed or 0.0) + amount) / elapsed_units * total_units
                sources[period] = "n2_period_context_plus_intraday_1m"
            else:
                fields[f"current_{db_period}_virtual_amount"] = None
                sources[period] = "missing_n2_period_context"
            fields[f"previous_{db_period}_amount"] = convert_formal_source_amount_to_yuan(
                previous_amount,
                amount_unit_rule=amount_unit_rule,
            )
        return fields, sources

    def amount_buy(current: float | None, previous: float | None, first_period: bool) -> bool:
        return True if first_period else current is not None and previous is not None and current > previous

    def amount_sell(current: float | None, previous: float | None, first_period: bool) -> bool:
        return True if first_period else current is not None and previous is not None and current < previous

    def pass_flags(metric: Mapping[str, Any]) -> dict[str, dict[str, bool]]:
        price = float(metric.get("current_price") or 0.0)
        current_5m_amount = metric.get("current_5m_virtual_amount")
        previous_5m_amount = metric.get("previous_5m_full_amount")
        current_1m_amount = metric.get("current_1m_amount")
        previous_1m_amount = metric.get("previous_1m_amount")
        return {
            "B_BUY": {
                "buy_120m_price_pass": price > float(metric.get("previous_120m_body_high") or float("inf")),
                "buy_30m_price_pass": price > float(metric.get("previous_30m_body_high") or float("inf")),
                "buy_5m_price_pass": price > float(metric.get("previous_5m_body_high") or float("inf")),
                "buy_1m_price_pass": price > float(metric.get("previous_1m_body_high") or float("inf")),
                "buy_5m_amount_pass": amount_buy(current_5m_amount, previous_5m_amount, bool(metric.get("is_first_5m_of_day"))),
                "buy_1m_amount_pass": amount_buy(current_1m_amount, previous_1m_amount, bool(metric.get("is_first_1m_of_day"))),
            },
            "S_SELL": {
                "sell_120m_price_pass": price < float(metric.get("previous_120m_body_low") or float("-inf")),
                "sell_30m_price_pass": price < float(metric.get("previous_30m_body_low") or float("-inf")),
                "sell_5m_price_pass": price < float(metric.get("previous_5m_body_low") or float("-inf")),
                "sell_1m_price_pass": price < float(metric.get("previous_1m_body_low") or float("-inf")),
                "sell_5m_amount_pass": amount_sell(current_5m_amount, previous_5m_amount, bool(metric.get("is_first_5m_of_day"))),
                "sell_1m_amount_pass": amount_sell(current_1m_amount, previous_1m_amount, bool(metric.get("is_first_1m_of_day"))),
            },
        }

    output: list[dict[str, Any]] = []
    for current in current_rows:
        minute_label = _normalize_bar_time(current["bar_time"]).strftime("%Y-%m-%d %H:%M")
        current_record = _minute_record_for_metric(current)
        current_record["_dt"] = datetime.strptime(str(current_record["datetime"]), "%Y-%m-%d %H:%M")
        current_dt = current_record["_dt"]
        previous_1m = previous_by_dt.get(current_dt)
        previous_1m_source = (
            "same_trade_date_previous_period"
            if previous_1m and previous_1m["_dt"].strftime("%Y%m%d") == for_trade_date
            else "previous_trade_date_last_period"
            if previous_1m
            else "not_available"
        )
        previous_5m, previous_5m_source = previous_segment(current_dt, 5)
        previous_30m, previous_30m_source = previous_segment(current_dt, 30)
        previous_120m, previous_120m_source = previous_segment(current_dt, 120)
        current_5m_virtual, previous_5m_full, current_5m_refs, current_5m_virtual_proof = current_virtual(current_dt, 5)
        current_30m_virtual, previous_30m_full, current_30m_refs, current_30m_virtual_proof = current_virtual(current_dt, 30)
        current_120m_virtual, previous_120m_full, current_120m_refs, current_120m_virtual_proof = current_virtual(current_dt, 120)
        previous_day_same_amount, previous_day_same_refs = previous_day_same_window(current_dt, 30)
        blocked = [
            name
            for name, value in (
                ("previous_1m_not_found", previous_1m),
                ("previous_5m_not_found", previous_5m),
                ("previous_30m_not_found", previous_30m),
                ("previous_120m_not_found", previous_120m),
            )
            if value is None
        ]
        for period_name, proof in (
            ("5m", current_5m_virtual_proof),
            ("30m", current_30m_virtual_proof),
        ):
            if proof.get("status") != "passed":
                blocked.append(f"current_{period_name}_virtual_amount_policy_failed:{proof.get('reason') or 'unknown'}")
        current_price = float(current_record["close"])
        higher_values, higher_sources = higher_fields(current_price, intraday_amount_through(current_dt))
        formal_amount_chain_metrics, formal_amount_chain_proof = build_formal_amount_chain_fields(
            today_virt_amount=higher_values.get("current_d_virtual_amount"),
            higher_period_context=higher_context,
            asset_kind=asset_kind,
        )
        virtual_amount_policy = {
            "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
            "source_kind": "N3_standard_period_metric",
            "amount_unit": "yuan",
            "calibration_method": "previous_day_same_window_elapsed_ratio",
            "periods": {
                "5m": current_5m_virtual_proof,
                "30m": current_30m_virtual_proof,
                "120m": current_120m_virtual_proof,
            },
        }
        formal_period_amount_proof = {
            "source_kind": "N3_standard_period_metric",
            "amount_unit": "yuan",
            "source_amount_unit": formal_amount_chain_proof.get("source_amount_unit"),
            "proof_source_amount_unit": formal_amount_chain_proof.get("proof_source_amount_unit"),
            "proof_canonical_amount_unit": formal_amount_chain_proof.get("proof_canonical_amount_unit"),
            "unit_conversion_factor": formal_amount_chain_proof.get("unit_conversion_factor"),
            "proof_unit_conversion_factor": formal_amount_chain_proof.get("proof_unit_conversion_factor"),
            "unit_conversion_policy": formal_amount_chain_proof.get("unit_conversion_policy"),
            "proof_amount_unit_source": formal_amount_chain_proof.get("proof_amount_unit_source"),
            "amount_rule": formal_amount_chain_proof.get("amount_rule"),
            "amount_chain_metrics": dict(formal_amount_chain_metrics),
            "proof_version": "v3.n3.formal_period_amount_source.v1",
            "policy": "current_D_virtual_amount_plus_D/W/M/Q/Y_n2_period_average_chain",
            "current_d_amount_source": higher_sources.get("D"),
            "current_d_seed_applied": higher_sources.get("D") != "today_minute_sum_only",
            "period_with_today_seed_scope": "W/M/Q/Y_only",
            "snapshot_amount_promoted": False,
            "periods": {},
        }
        for period in FULL_DAY_PERIOD_TOTAL_UNITS:
            db_period = period.lower()
            amount_value = higher_values.get(f"current_{db_period}_virtual_amount")
            amount_source = higher_sources.get(period)
            amount_source_kind = (
                "N3_standard_period_metric"
                if amount_value is not None and amount_source != "missing_n2_period_context"
                else amount_source or "missing_n2_period_context"
            )
            formal_period_amount_proof["periods"][period] = {
                "period": period,
                "current_amount_source_kind": amount_source_kind,
                "current_amount_unit": "yuan" if amount_source_kind == "N3_standard_period_metric" else None,
                "current_amount_field": f"current_{db_period}_virtual_amount",
                "current_amount_yuan": amount_value,
                "n2_previous_amount_yuan": higher_values.get(f"previous_{db_period}_amount"),
                "source_amount_unit": formal_amount_chain_proof.get("source_amount_unit"),
                "proof_source_amount_unit": formal_amount_chain_proof.get("proof_source_amount_unit"),
                "proof_canonical_amount_unit": formal_amount_chain_proof.get("proof_canonical_amount_unit"),
                "unit_conversion_factor": formal_amount_chain_proof.get("unit_conversion_factor"),
                "proof_unit_conversion_factor": formal_amount_chain_proof.get("proof_unit_conversion_factor"),
                "unit_conversion_policy": formal_amount_chain_proof.get("unit_conversion_policy"),
                "proof_amount_unit_source": formal_amount_chain_proof.get("proof_amount_unit_source"),
                "current_body_high_field": f"current_{db_period}_body_high",
                "current_body_low_field": f"current_{db_period}_body_low",
                "period_source": amount_source,
                "source_field_trace": {
                    "current_amount_seed": "not_applied_for_D_current_amount"
                    if period == "D"
                    else "period_trigger_baseline_json.periods[*].current_amount_seed",
                    "elapsed_units": "period_trigger_baseline_json.periods[*].current_trade_days_seed/elapsed_units",
                    "total_units": "v3_full_day_replay_plan.FULL_DAY_PERIOD_TOTAL_UNITS",
                    "intraday_amount": "stock/index/board_minute_bar_1m.amount cumulative through metric_time",
                },
            }
            if period == "D":
                formal_period_amount_proof["periods"][period].update(
                    {
                        "current_d_amount_source": "today_minute_sum_only",
                        "current_d_seed_applied": False,
                        "period_with_today_seed_scope": "W/M/Q/Y_only",
                    }
                )
            if period in formal_amount_chain_proof.get("periods", {}):
                formal_period_amount_proof["periods"][period].update(
                    dict(formal_amount_chain_proof["periods"][period])
                )
            period_context = higher_context.get(period) or {}
            formal_period_amount_proof["periods"][period].update(
                {
                    "period_key_source": period_context.get("period_key_source"),
                    "source_period_key": period_context.get("source_period_key"),
                    "for_period_key": period_context.get("for_period_key"),
                    "baseline_period_key_current": period_context.get("baseline_period_key_current"),
                    "period_seed_applied": period_context.get("period_seed_applied"),
                    "period_seed_reset_reason": period_context.get("period_seed_reset_reason"),
                    "period_key_guard_pass": period_context.get("period_key_guard_pass"),
                }
            )
        current_5m_rows = current_segment_rows(current_dt, 5)
        current_30m_rows = current_segment_rows(current_dt, 30)
        current_120m_rows = current_segment_rows(current_dt, 120)
        previous_day_refs = sorted(
            {
                *[
                    str(ref)
                    for value, source in (
                        (previous_1m, previous_1m_source),
                        (previous_5m, previous_5m_source),
                        (previous_30m, previous_30m_source),
                        (previous_120m, previous_120m_source),
                    )
                    if source == "previous_trade_date_last_period" and value
                    for ref in (value.get("source_minute_refs") or [value.get("datetime")])
                    if ref
                ],
                *previous_day_same_refs,
            }
        )
        current_5m_agg = aggregate(current_5m_rows) or {}
        current_30m_agg = aggregate(current_30m_rows) or {}
        current_120m_agg = aggregate(current_120m_rows) or {}
        metric = {
            "code": str(context_row["code"]),
            "metric_time_label": minute_label,
            "metric_minute_label": minute_label,
            "snapshot_id": None,
            "event_id": None,
            "source_time": minute_label,
            "observed_at": _metric_observed_at(current),
            "session_kind": "regular",
            "period_source": {
                "1m": previous_1m_source,
                "5m": previous_5m_source,
                "30m": previous_30m_source,
                "120m": previous_120m_source,
                **higher_sources,
            },
            "is_closed_1m": True,
            "is_auction_virtual": False,
            "midday_bridge_policy": "13:00_label_equivalent_to_missing_11:30_bar"
            if current_dt.hour == 13 and current_dt.minute >= 1
            else None,
            "metric_ready": not blocked,
            "quality_status": "passed" if not blocked else "failed",
            "blocked_reasons": blocked,
            "current_price": current_price,
            "current_price_source": "n3_realtime_virtual_metric.current_1m.close",
            "current_price_time": minute_label,
            "current_1m_amount": float(current_record["amount"]),
            "previous_1m_amount": float(previous_1m["amount"]) if previous_1m else None,
            "current_1m_body_high": max(float(current_record["open"]), float(current_record["close"])),
            "current_1m_body_low": min(float(current_record["open"]), float(current_record["close"])),
            "previous_1m_body_high": max(float(previous_1m["open"]), float(previous_1m["close"])) if previous_1m else None,
            "previous_1m_body_low": min(float(previous_1m["open"]), float(previous_1m["close"])) if previous_1m else None,
            "current_5m_body_high": current_5m_agg.get("body_high"),
            "current_5m_body_low": current_5m_agg.get("body_low"),
            "previous_5m_body_high": previous_5m.get("body_high") if previous_5m else None,
            "previous_5m_body_low": previous_5m.get("body_low") if previous_5m else None,
            "current_30m_body_high": current_30m_agg.get("body_high"),
            "current_30m_body_low": current_30m_agg.get("body_low"),
            "previous_30m_body_high": previous_30m.get("body_high") if previous_30m else None,
            "previous_30m_body_low": previous_30m.get("body_low") if previous_30m else None,
            "current_120m_body_high": current_120m_agg.get("body_high"),
            "current_120m_body_low": current_120m_agg.get("body_low"),
            "previous_120m_body_high": previous_120m.get("body_high") if previous_120m else None,
            "previous_120m_body_low": previous_120m.get("body_low") if previous_120m else None,
            "current_5m_virtual_amount": current_5m_virtual,
            "previous_5m_full_amount": previous_5m.get("amount") if previous_5m else previous_5m_full,
            "current_30m_virtual_amount": current_30m_virtual,
            "previous_day_same_window_amount": previous_day_same_amount,
            "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
            "previous_30m_full_amount": previous_30m_full,
            "current_120m_virtual_amount": current_120m_virtual,
            "previous_120m_full_amount": previous_120m_full,
            "is_first_1m_of_day": first_segment(current_dt, 1),
            "is_first_5m_of_day": first_segment(current_dt, 5),
            "is_first_30m_of_day": first_segment(current_dt, 30),
            "is_first_120m_of_day": first_segment(current_dt, 120),
            "first_1m_amount_default_pass": first_segment(current_dt, 1),
            "first_5m_amount_default_pass": first_segment(current_dt, 5),
            "previous_1m_period_source": previous_1m_source,
            "previous_5m_period_source": previous_5m_source,
            "previous_30m_period_source": previous_30m_source,
            "previous_120m_period_source": previous_120m_source,
            "boundary_policy_version": "v3.realtime_virtual_metric.boundary.v1",
            "source_minute_refs": sorted(set([minute_label, *current_5m_refs, *current_30m_refs, *current_120m_refs])),
            "previous_day_minute_refs": previous_day_refs,
            "trace_json": {
                "builder": "ashare_v3.market.v3_full_day_replay_plan.fast_full_day_metric_builder",
                "higher_period_context_periods": sorted(higher_context.keys()),
                "virtual_amount_policy": virtual_amount_policy,
                "formal_amount_chain_metrics": dict(formal_amount_chain_metrics),
                "formal_period_amount_proof": formal_period_amount_proof,
            },
            "raw_json": {
                "source": "n3_realtime_virtual_metric_full_day_replay",
                "auction_policy": "closed_replay_0931_label",
                "midday_bridge_policy": "13:00_label_equivalent_to_missing_11:30_bar",
                "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
                "formal_amount_chain_metrics": dict(formal_amount_chain_metrics),
                "formal_period_amount_proof": formal_period_amount_proof,
            },
            **higher_values,
            **formal_amount_chain_metrics,
        }
        metric["deterministic_pass_flags"] = pass_flags(metric)
        candidate = {
            "asset_kind": context_row["asset_kind"],
            "identity_key": context_row["identity_key"],
            "exchange": context_row["exchange"],
            "code": context_row["code"],
            "display_code": context_row.get("display_code") or context_row.get("code"),
            "name": context_row.get("name") or context_row.get("identity_key"),
            "signal_type": "",
            "condition_key": "",
            "minute_label": minute_label,
            "observed_at": _metric_observed_at(current),
            "source_snapshot_run_id": resolved_source_snapshot_run_id,
            "source_today_minute_run_id": source_today_minute_run_id,
            "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
            "candidate_ref": f"full_day_metric:{context_row['identity_key']}:{minute_label}",
        }
        row = build_action_confirmation_metric_row(contract=contract, candidate=candidate, metric=metric)
        trace = dict(row.get("trace_json") or {})
        trace["full_day_replay"] = {
            "context_trigger_context_id": context_row.get("trigger_context_id"),
            "source_today_minute_run_id": source_today_minute_run_id,
            "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
            "metric_minute_bar_id": current.get("bar_id"),
            "uses_old_system": False,
        }
        row["trace_json"] = trace
        output.append(row)
    return output


def full_day_metric_contract(lineage: FullContextFormalMetricLineage | None = None) -> dict[str, Any]:
    if lineage is not None:
        return {
            "projection_run_id": lineage.projection_run_id,
            "projection_schema_version": lineage.projection_schema_version,
            "source_scope": lineage.source_scope(),
            "allowed_write_tables": list(FULL_CONTEXT_FORMAL_ALLOWED_WRITE_TABLES),
        }
    return {
        "projection_run_id": FULL_DAY_METRIC_RUN_ID,
        "projection_schema_version": FULL_DAY_METRIC_SCHEMA_VERSION,
        "source_scope": {
            "for_trade_date": FOR_TRADE_DATE,
            "source_trade_date": "20260611",
            "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
            "source_subscription_run_id": FULL_DAY_1M_BACKFILL_RUN_ID,
            "source_snapshot_run_id": FULL_DAY_1M_BACKFILL_RUN_ID,
            "source_today_minute_run_id": FULL_DAY_1M_BACKFILL_RUN_ID,
            "source_previous_day_minute_run_id": FULL_DAY_PREVIOUS_MINUTE_RUN_ID,
        },
        "allowed_write_tables": list(FULL_CONTEXT_FORMAL_ALLOWED_WRITE_TABLES),
    }


def capture_full_day_metric_counts(
    *,
    dsn: str = DEFAULT_DSN,
    projection_run_id: str = FULL_DAY_METRIC_RUN_ID,
) -> dict[str, int]:
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            counts: dict[str, int] = {}
            for table_name in (
                "common_market_data_run",
                "common_market_data_quality_item",
                "stock_action_confirmation_projection_metric",
                "index_action_confirmation_projection_metric",
                "board_action_confirmation_projection_metric",
                "common_event_outbox",
                "common_event_inbox",
            ):
                column = "run_id" if table_name in {"common_market_data_run", "common_market_data_quality_item"} else "projection_run_id"
                if table_name in {"common_event_outbox", "common_event_inbox"}:
                    cur.execute(
                        f"SELECT count(*)::bigint AS c FROM {table_name} WHERE source_run_id = %s OR payload_json::text LIKE %s",
                        (projection_run_id, f"%{projection_run_id}%"),
                    )
                else:
                    cur.execute(f"SELECT count(*)::bigint AS c FROM {table_name} WHERE {column} = %s", (projection_run_id,))
                counts[table_name] = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*)::bigint AS c
                FROM common_event_consumer_checkpoint
                WHERE checkpoint_payload::text LIKE %s
                """,
                (f"%{projection_run_id}%",),
            )
            counts["common_event_consumer_checkpoint"] = int(cur.fetchone()["c"])
    return counts


def _coverage_by_identity(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {_identity_from_row(row): row for row in rows if _identity_from_row(row)}


def _context_identity_counts(context_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("asset_kind") or _asset_kind(_identity_from_row(row))) for row in context_rows)
    return {asset: counts.get(asset, 0) for asset in ASSET_CONFIG}


def _validate_formal_metric_sample_rows(sample_metric_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    if not sample_metric_rows:
        return ["formal_proof_sample_missing"]
    missing: list[str] = []
    for row in sample_metric_rows:
        raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), Mapping) else {}
        trace_json = row.get("trace_json") if isinstance(row.get("trace_json"), Mapping) else {}
        formal_proof = raw_json.get("formal_period_amount_proof") or trace_json.get("formal_period_amount_proof")
        chain = raw_json.get("formal_amount_chain_metrics") or trace_json.get("formal_amount_chain_metrics")
        if not isinstance(formal_proof, Mapping):
            missing.append("formal_period_amount_proof")
        if not isinstance(chain, Mapping):
            missing.append("formal_amount_chain_metrics")
        periods = formal_proof.get("periods") if isinstance(formal_proof, Mapping) else {}
        if not isinstance(periods, Mapping) or any(period not in periods for period in FULL_DAY_PERIOD_TOTAL_UNITS):
            missing.append("D/W/M/Q/Y virtual amount proof fields")
        if row.get("projection_schema_version") != TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION:
            missing.append("true_full_day_minute_series_schema_version")
    return sorted(set(missing))


def build_full_context_formal_metric_plan_report(
    *,
    lineage: FullContextFormalMetricLineage,
    context_rows: Sequence[Mapping[str, Any]],
    today_coverage_rows: Sequence[Mapping[str, Any]],
    previous_coverage_rows: Sequence[Mapping[str, Any]],
    baseline_counts: Mapping[str, int],
    sample_metric_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    context_rows = [dict(row) for row in context_rows]
    if not context_rows:
        blockers.append("context_missing")

    if any(int(value or 0) != 0 for value in baseline_counts.values()):
        blockers.append("target_projection_run_id_already_exists")

    for row in context_rows:
        if str(row.get("run_id") or "") != lineage.trigger_context_run_id:
            blockers.append("context_lineage_mismatch")
            break
    for row in context_rows:
        if row.get("source_condition_run_id") and str(row.get("source_condition_run_id")) != lineage.source_condition_run_id:
            blockers.append("context_source_condition_run_id_mismatch")
            break
    for row in context_rows:
        if str(row.get("for_trade_date") or "") != lineage.for_trade_date:
            blockers.append("context_for_trade_date_mismatch")
            break

    context_identities = sorted({_identity_from_row(row) for row in context_rows if _identity_from_row(row)})
    today_by_identity = _coverage_by_identity(today_coverage_rows)
    previous_by_identity = _coverage_by_identity(previous_coverage_rows)
    today_bad = [
        identity
        for identity in context_identities
        if int(today_by_identity.get(identity, {}).get("row_count") or 0) != FULL_DAY_EXPECTED_1M_BAR_COUNT
    ]
    previous_bad = [
        identity
        for identity in context_identities
        if int(previous_by_identity.get(identity, {}).get("row_count") or 0) != FULL_DAY_EXPECTED_1M_BAR_COUNT
    ]
    if today_bad:
        blockers.append("today_minute_coverage_not_240")
    if previous_bad:
        blockers.append("previous_day_minute_coverage_not_240")

    formal_missing = _validate_formal_metric_sample_rows(sample_metric_rows or []) if sample_metric_rows is not None else []
    if formal_missing:
        blockers.append("formal_proof_fields_missing")

    context_counts = _context_identity_counts(context_rows)
    expected_rows = {asset: context_counts.get(asset, 0) * FULL_DAY_EXPECTED_1M_BAR_COUNT for asset in ASSET_CONFIG}
    expected_rows["total"] = sum(expected_rows.values())
    result = "PLAN_BLOCKED" if blockers else "PLAN_PASS"
    return {
        "stage": "N3 full-context formal action-confirmation metric plan",
        "layer_role": "N3_market_data",
        "result": result,
        "blocked": bool(blockers),
        "blockers": sorted(set(blockers)),
        "projection_run_id": lineage.projection_run_id,
        "projection_schema_version": lineage.projection_schema_version,
        "for_trade_date": lineage.for_trade_date,
        "source_scope": lineage.source_scope(),
        "context": {
            "row_count": len(context_rows),
            "identity_count": len(context_identities),
            "identities_by_asset": context_counts,
        },
        "expected_rows": expected_rows,
        "coverage": {
            "expected_minute_rows_per_identity": FULL_DAY_EXPECTED_1M_BAR_COUNT,
            "today_missing_or_incomplete_count": len(today_bad),
            "today_missing_or_incomplete_sample": today_bad[:20],
            "previous_day_missing_or_incomplete_count": len(previous_bad),
            "previous_day_missing_or_incomplete_sample": previous_bad[:20],
        },
        "formal_proof_fields": {
            "required": list(FULL_CONTEXT_FORMAL_REQUIRED_PROOF_FIELDS),
            "missing": formal_missing,
            "present": not formal_missing,
        },
        "baseline": dict(baseline_counts),
        "write_scope": {
            "future_execute_only": True,
            "allowed_future_execute_write_tables": list(FULL_CONTEXT_FORMAL_ALLOWED_WRITE_TABLES),
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "writes_n4_n5_n6": False,
            "writes_minute_facts": False,
        },
    }


def fetch_full_context_formal_metric_minute_coverage_rows(
    *,
    dsn: str = DEFAULT_DSN,
    lineage: FullContextFormalMetricLineage,
    context_rows: Sequence[Mapping[str, Any]],
    run_id: str,
    minute_trade_date: str,
    is_previous_day_preload: bool,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    identities_by_asset: dict[str, list[str]] = {asset: [] for asset in ASSET_CONFIG}
    for row in context_rows:
        identity = _identity_from_row(row)
        asset = str(row.get("asset_kind") or _asset_kind(identity))
        if identity and asset in identities_by_asset:
            identities_by_asset[asset].append(identity)
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            for asset, identities in identities_by_asset.items():
                identity_list = list(dict.fromkeys(identities))
                if not identity_list:
                    continue
                cfg = ASSET_CONFIG[asset]
                table_name = cfg["minute_table"]
                identity_col = cfg["minute_identity_column"]
                cur.execute(
                    f"""
                    SELECT %s AS asset_kind,
                           {identity_col} AS identity_key,
                           count(*)::bigint AS row_count,
                           min(bar_time) AS min_time,
                           max(bar_time) AS max_time
                    FROM {table_name}
                    WHERE {identity_col} = ANY(%s)
                      AND run_id = %s
                      AND trade_date = %s
                      AND is_previous_day_preload = %s
                    GROUP BY {identity_col}
                    """,
                    (asset, identity_list, run_id, minute_trade_date, is_previous_day_preload),
                )
                output.extend(dict(row) for row in cur.fetchall())
    return output


def _build_full_context_formal_metric_sample_rows(
    *,
    dsn: str,
    lineage: FullContextFormalMetricLineage,
    context_rows: Sequence[Mapping[str, Any]],
    sample_per_asset: int,
) -> list[dict[str, Any]]:
    contract = full_day_metric_contract(lineage)
    output: list[dict[str, Any]] = []
    for asset in ASSET_CONFIG:
        asset_contexts = [dict(row) for row in context_rows if str(row.get("asset_kind")) == asset]
        if not asset_contexts:
            continue
        sample_contexts = asset_contexts[: max(sample_per_asset, 0)]
        minute_rows = fetch_full_day_metric_minute_rows_by_identity(
            dsn=dsn,
            asset_kind=asset,
            identities=[str(row["identity_key"]) for row in sample_contexts],
            today_run_id=lineage.source_today_minute_run_id,
            previous_run_id=lineage.source_previous_day_minute_run_id,
            for_trade_date=lineage.for_trade_date,
            previous_trade_date=lineage.previous_trade_date,
        )
        for context in sample_contexts:
            rows = build_full_day_metric_rows_for_identity(
                context_row=context,
                minute_rows=minute_rows.get(str(context["identity_key"])) or [],
                contract=contract,
                for_trade_date=lineage.for_trade_date,
                source_today_minute_run_id=lineage.source_today_minute_run_id,
                source_previous_day_minute_run_id=lineage.source_previous_day_minute_run_id,
                source_snapshot_run_id=lineage.resolved_source_snapshot_run_id,
            )
            if rows:
                output.append(rows[-1])
    return output


def build_full_context_formal_metric_plan_from_db(
    *,
    dsn: str = DEFAULT_DSN,
    lineage: FullContextFormalMetricLineage,
    sample_per_asset: int = 1,
) -> dict[str, Any]:
    context_rows = fetch_full_day_metric_context_rows(
        dsn=dsn,
        trigger_context_run_id=lineage.trigger_context_run_id,
        for_trade_date=lineage.for_trade_date,
    )
    baseline = capture_full_day_metric_counts(dsn=dsn, projection_run_id=lineage.projection_run_id)
    today_coverage = fetch_full_context_formal_metric_minute_coverage_rows(
        dsn=dsn,
        lineage=lineage,
        context_rows=context_rows,
        run_id=lineage.source_today_minute_run_id,
        minute_trade_date=lineage.for_trade_date,
        is_previous_day_preload=False,
    )
    previous_coverage = fetch_full_context_formal_metric_minute_coverage_rows(
        dsn=dsn,
        lineage=lineage,
        context_rows=context_rows,
        run_id=lineage.source_previous_day_minute_run_id,
        minute_trade_date=lineage.previous_trade_date,
        is_previous_day_preload=True,
    )
    sample_rows = _build_full_context_formal_metric_sample_rows(
        dsn=dsn,
        lineage=lineage,
        context_rows=context_rows,
        sample_per_asset=sample_per_asset,
    )
    return build_full_context_formal_metric_plan_report(
        lineage=lineage,
        context_rows=context_rows,
        today_coverage_rows=today_coverage,
        previous_coverage_rows=previous_coverage,
        baseline_counts=baseline,
        sample_metric_rows=sample_rows,
    )


def build_full_day_coverage_audit_report(
    *,
    for_trade_date: str,
    source_condition_run_id: str,
    trigger_context_run_id: str,
    existing_metric_run_id: str,
    scope_rows: Sequence[Mapping[str, Any]],
    context_rows: Sequence[Mapping[str, Any]],
    minute_coverage_rows: Sequence[Mapping[str, Any]],
    metric_coverage_rows: Sequence[Mapping[str, Any]],
    focus_identity_key: str = "stock:SH:603259",
    focus_minute_label: str = "10:56",
    sample_limit: int = 20,
) -> dict[str, Any]:
    scope_counter = _identity_counter(scope_rows)
    context_counter = _identity_counter(context_rows)
    context_identities = sorted(context_counter)
    minute_coverage = _coverage_map(minute_coverage_rows)
    metric_coverage = _coverage_map(metric_coverage_rows)
    missing_minute = [identity for identity in context_identities if minute_coverage.get(identity, {}).get("row_count", 0) <= 0]
    missing_metric = [identity for identity in context_identities if metric_coverage.get(identity, {}).get("row_count", 0) <= 0]
    blockers: list[str] = []
    if missing_minute:
        blockers.append("n3_1m_source_missing_for_context_scope")
    if missing_metric:
        blockers.append("n3_metric_missing_for_context_scope")
    focus_minute = minute_coverage.get(focus_identity_key, {})
    focus_metric = metric_coverage.get(focus_identity_key, {})
    result = "BLOCKED" if blockers else "AUDIT_PASS"
    return {
        "stage": "V3_20260612_N3_FULL_DAY_1M_COVERAGE_AUDIT",
        "result": result,
        "blockers": blockers,
        "for_trade_date": for_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "existing_metric_run_id": existing_metric_run_id,
        "scope_proof": {
            "scope_row_count": len(scope_rows),
            "scope_object_count": len(scope_counter),
            "scope_objects_by_asset": count_by_asset(sorted(scope_counter)),
            "context_row_count": len(context_rows),
            "context_object_count": len(context_counter),
            "context_objects_by_asset": count_by_asset(context_identities),
        },
        "coverage_proof": {
            "minute_covered_object_count": sum(1 for row in minute_coverage.values() if row.get("row_count", 0) > 0),
            "metric_covered_object_count": sum(1 for row in metric_coverage.values() if row.get("row_count", 0) > 0),
            "missing_minute_object_count": len(missing_minute),
            "missing_metric_object_count": len(missing_metric),
            "missing_minute_by_asset": count_by_asset(missing_minute),
            "missing_metric_by_asset": count_by_asset(missing_metric),
            "missing_minute_sample": missing_minute[:sample_limit],
            "missing_metric_sample": missing_metric[:sample_limit],
        },
        "focus_object": {
            "identity_key": focus_identity_key,
            "focus_minute_label": focus_minute_label,
            "scope_rows": scope_counter.get(focus_identity_key, 0),
            "context_rows": context_counter.get(focus_identity_key, 0),
            "minute_rows": int(focus_minute.get("row_count") or 0),
            "metric_rows": int(focus_metric.get("row_count") or 0),
            "rows_before_focus_minute": int(focus_minute.get("rows_before_focus") or 0),
            "metric_rows_before_focus_minute": int(focus_metric.get("rows_before_focus") or 0),
        },
        "policy": {
            "v3_only": True,
            "target_machine_reference": "forbidden",
            "n4_n5_business_rules_changed": False,
            "old_runs_preserved_as_superseded_evidence": True,
        },
        "next_gate": {
            "allow_n3_1m_backfill_contract_preflight": bool(missing_minute),
            "allow_n3_full_day_metric_contract_preflight": not missing_minute,
            "allow_n4_replay_contract_preflight": not missing_minute and not missing_metric,
            "allow_n5_replay_contract_preflight": False,
            "execute_authorized": False,
        },
        "forbidden_scope_proof": forbidden_scope_proof(),
    }


def build_n3_full_day_backfill_contract_preflight(
    audit_report: Mapping[str, Any],
    *,
    backfill_run_id: str = FULL_DAY_1M_BACKFILL_RUN_ID,
    metric_run_id: str = FULL_DAY_METRIC_RUN_ID,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    missing_sample = list((audit_report.get("coverage_proof") or {}).get("missing_minute_sample") or [])
    missing_by_asset = dict((audit_report.get("coverage_proof") or {}).get("missing_minute_by_asset") or {})
    missing_total = int((audit_report.get("coverage_proof") or {}).get("missing_minute_object_count") or 0)
    contract = {
        "stage": "V3_20260612_N3_FULL_DAY_1M_BACKFILL_CONTRACT",
        "result": "CONTRACT_PASS",
        "for_trade_date": audit_report.get("for_trade_date"),
        "source_condition_run_id": audit_report.get("source_condition_run_id"),
        "trigger_context_run_id": audit_report.get("trigger_context_run_id"),
        "backfill_run_id": backfill_run_id,
        "future_metric_run_id": metric_run_id,
        "source_scope": {
            "scope_source": "V3 N2 minute_target_scope and N4 localized context only",
            "target_machine_reference": "forbidden",
            "missing_context_objects_total": missing_total,
            "missing_context_objects_by_asset": missing_by_asset,
            "missing_context_identity_sample": missing_sample,
        },
        "allowed_future_write_tables_after_user_confirmation": [
            "common_market_data_run",
            "common_market_data_quality_item",
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
        ],
        "forbidden_write_tables": [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_run",
            "common_action_run",
            "N6/user/voice/mobile/sim/position/order/trade",
        ],
        "minute_policy": {
            "auction_virtual_label": "09:31 may represent 09:20-09:30 auction realtime virtual 1m when source provides it",
            "midday_bridge": "13:00 bridges missing 11:30; 13:01 compares to 13:00; no fabricated 11:30 row",
        },
    }
    preflight = {
        "stage": "V3_20260612_N3_FULL_DAY_1M_BACKFILL_PREFLIGHT",
        "result": "PREFLIGHT_PASS",
        "P0_P1_P2": {"P0": 0, "P1": 0, "P2": 0},
        "contract_run_id": backfill_run_id,
        "execute_authorized": False,
        "requires_user_confirmation": True,
        "next_gate": "V3_20260612_N3_FULL_DAY_1M_BACKFILL_EXECUTE_FINAL_GATE_REVIEW",
        "forbidden_scope_proof": forbidden_scope_proof(),
    }
    rollback_sql = build_n3_full_day_backfill_rollback_sql(backfill_run_id)
    return contract, preflight, rollback_sql


def build_n3_full_day_backfill_rollback_sql(backfill_run_id: str = FULL_DAY_1M_BACKFILL_RUN_ID) -> str:
    return f"""-- V3 20260612 N3 full-day 1m backfill rollback
-- Scoped to run_id={backfill_run_id}
DO $$
DECLARE
  target_run_id text := '{backfill_run_id}';
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260612_full_day_1m_backfill_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_v3_20260612_full_day_1m_backfill_rollback=true before DELETE';
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_event_outbox
    WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_event_outbox refs exist for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_event_inbox
    WHERE source_run_id = target_run_id OR payload_json::text LIKE '%' || target_run_id || '%' OR raw_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_event_inbox refs exist for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_event_consumer_checkpoint
    WHERE checkpoint_payload::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_event_consumer_checkpoint refs exist for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_trigger_run
    WHERE source_market_data_run_id = target_run_id OR raw_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_trigger_run refs exist for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1 FROM common_action_run
    WHERE raw_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: common_action_run refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL AND EXISTS (
    SELECT 1 FROM user_signal_projection
    WHERE source_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: user_signal_projection refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL AND EXISTS (
    SELECT 1 FROM user_signal_card
    WHERE card_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: user_signal_card refs exist for %', target_run_id;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL AND EXISTS (
    SELECT 1 FROM user_notification_queue
    WHERE notification_payload_json::text LIKE '%' || target_run_id || '%' OR trace_json::text LIKE '%' || target_run_id || '%'
  ) THEN
    RAISE EXCEPTION 'hard-fail: user_notification_queue refs exist for %', target_run_id;
  END IF;
END $$;

DELETE FROM stock_minute_bar_1m WHERE run_id = '{backfill_run_id}';
DELETE FROM index_minute_bar_1m WHERE run_id = '{backfill_run_id}';
DELETE FROM board_minute_bar_1m WHERE run_id = '{backfill_run_id}';
DELETE FROM common_market_data_quality_item WHERE run_id = '{backfill_run_id}';
DELETE FROM common_market_data_run WHERE run_id = '{backfill_run_id}';
"""


def _focus_timestamp(for_trade_date: str, focus_minute_label: str) -> datetime:
    return datetime.strptime(f"{for_trade_date} {focus_minute_label}", "%Y%m%d %H:%M")


def fetch_full_day_coverage_inputs(
    *,
    dsn: str = DEFAULT_DSN,
    for_trade_date: str = FOR_TRADE_DATE,
    source_condition_run_id: str = SOURCE_CONDITION_RUN_ID,
    trigger_context_run_id: str = TRIGGER_CONTEXT_RUN_ID,
    projection_run_id: str = LIMITED_METRIC_RUN_ID,
    focus_minute_label: str = "10:56",
) -> dict[str, list[dict[str, Any]]]:
    focus_ts = _focus_timestamp(for_trade_date, focus_minute_label)
    inputs: dict[str, list[dict[str, Any]]] = {
        "scope_rows": [],
        "context_rows": [],
        "minute_coverage_rows": [],
        "metric_coverage_rows": [],
    }
    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            for asset_kind, cfg in ASSET_CONFIG.items():
                scope_table = cfg["scope_table"]
                scope_identity = cfg["scope_identity_column"]
                cur.execute(
                    f"""
                    SELECT %s AS asset_kind, {scope_identity} AS identity_key, run_id, for_trade_date,
                           direction, condition_key, minute_required
                    FROM {scope_table}
                    WHERE run_id = %s AND for_trade_date = %s
                    """,
                    (asset_kind, source_condition_run_id, for_trade_date),
                )
                inputs["scope_rows"].extend(dict(row) for row in cur.fetchall())

                context_table = cfg["context_table"]
                cur.execute(
                    f"""
                    SELECT asset_kind, identity_key, run_id, for_trade_date, direction, condition_key,
                           allowed_signal_types
                    FROM {context_table}
                    WHERE run_id = %s AND for_trade_date = %s
                    """,
                    (trigger_context_run_id, for_trade_date),
                )
                inputs["context_rows"].extend(dict(row) for row in cur.fetchall())

                minute_table = cfg["minute_table"]
                minute_identity = cfg["minute_identity_column"]
                cur.execute(
                    f"""
                    SELECT %s AS asset_kind, {minute_identity} AS identity_key,
                           COUNT(*)::int AS row_count,
                           SUM(CASE WHEN bar_time <= %s THEN 1 ELSE 0 END)::int AS rows_before_focus,
                           MIN(bar_time)::text AS min_time,
                           MAX(bar_time)::text AS max_time
                    FROM {minute_table}
                    WHERE trade_date = %s AND is_previous_day_preload = false
                    GROUP BY {minute_identity}
                    """,
                    (asset_kind, focus_ts, for_trade_date),
                )
                inputs["minute_coverage_rows"].extend(dict(row) for row in cur.fetchall())

                metric_table = cfg["metric_table"]
                cur.execute(
                    f"""
                    SELECT asset_kind, identity_key,
                           COUNT(*)::int AS row_count,
                           SUM(CASE WHEN metric_minute_label <= %s THEN 1 ELSE 0 END)::int AS rows_before_focus,
                           MIN(metric_minute_label)::text AS min_time,
                           MAX(metric_minute_label)::text AS max_time
                    FROM {metric_table}
                    WHERE projection_run_id = %s AND for_trade_date = %s
                    GROUP BY asset_kind, identity_key
                    """,
                    (focus_minute_label, projection_run_id, for_trade_date),
                )
                inputs["metric_coverage_rows"].extend(dict(row) for row in cur.fetchall())
    return inputs


def build_realtime_metric_coverage_guard_report(
    *,
    dsn: str = DEFAULT_DSN,
    for_trade_date: str,
    source_condition_run_id: str,
    trigger_context_run_id: str,
    projection_run_id: str,
    sample_limit: int = 20,
) -> dict[str, Any]:
    inputs = fetch_full_day_coverage_inputs(
        dsn=dsn,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        focus_minute_label="15:00",
    )
    audit = build_full_day_coverage_audit_report(
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        trigger_context_run_id=trigger_context_run_id,
        existing_metric_run_id=projection_run_id,
        scope_rows=inputs["scope_rows"],
        context_rows=inputs["context_rows"],
        minute_coverage_rows=inputs["minute_coverage_rows"],
        metric_coverage_rows=inputs["metric_coverage_rows"],
        focus_identity_key="stock:SH:603259",
        focus_minute_label="15:00",
        sample_limit=sample_limit,
    )
    if audit["blockers"]:
        return {
            "result": "BLOCKED",
            "blocked_reason": "n3_metric_coverage_missing_for_n4_context",
            "missing_identity_count": audit["coverage_proof"]["missing_metric_object_count"],
            "missing_identity_sample": audit["coverage_proof"]["missing_metric_sample"],
            "audit_stage": audit["stage"],
            "forbidden_scope_proof": audit["forbidden_scope_proof"],
        }
    return {
        "result": "PASS",
        "reason": "n3_metric_coverage_ready_for_n4_context",
        "covered_identity_count": audit["coverage_proof"]["metric_covered_object_count"],
        "forbidden_scope_proof": audit["forbidden_scope_proof"],
    }


def format_coverage_audit_markdown(report: Mapping[str, Any]) -> str:
    coverage = report.get("coverage_proof") or {}
    focus = report.get("focus_object") or {}
    lines = [
        "# V3 20260612 N3 Full-Day 1m Coverage Audit",
        "",
        f"- result: `{report.get('result')}`",
        f"- blockers: `{', '.join(report.get('blockers') or [])}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- source_condition_run_id: `{report.get('source_condition_run_id')}`",
        f"- trigger_context_run_id: `{report.get('trigger_context_run_id')}`",
        "",
        "## Coverage",
        "",
        f"- missing minute objects: `{coverage.get('missing_minute_object_count')}`",
        f"- missing metric objects: `{coverage.get('missing_metric_object_count')}`",
        f"- missing minute sample: `{coverage.get('missing_minute_sample')}`",
        f"- missing metric sample: `{coverage.get('missing_metric_sample')}`",
        "",
        "## 603259 Focus",
        "",
        f"- identity_key: `{focus.get('identity_key')}`",
        f"- focus minute: `{focus.get('focus_minute_label')}`",
        f"- scope/context rows: `{focus.get('scope_rows')}/{focus.get('context_rows')}`",
        f"- minute/metric rows: `{focus.get('minute_rows')}/{focus.get('metric_rows')}`",
        f"- rows before focus: `{focus.get('rows_before_focus_minute')}`",
        "",
        "## Boundary",
        "",
    ]
    for key, value in (report.get("forbidden_scope_proof") or {}).items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines).rstrip() + "\n"
