"""N3-A1 previous-day cumulative amount materialization writer.

This writer is scoped to the N3 market-data layer. It materializes reviewed
A1 raw previous-day minute rows into stock/index/board cumulative tables only;
it does not write outbox/inbox/checkpoint rows or enter downstream layers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any

from psycopg.types.json import Jsonb

from ashare_v3.market.realtime_virtual_metric import (
    A1_CUMULATIVE_ASSET_KINDS,
    build_previous_day_cumulative_amount_rows,
    normalize_jsonable,
)


A1_CUMULATIVE_TABLES = {
    "stock": "stock_previous_day_minute_cumulative",
    "index": "index_previous_day_minute_cumulative",
    "board": "board_previous_day_minute_cumulative",
}

A1_CUMULATIVE_INSERT_COLUMNS = (
    "cumulative_id",
    "run_id",
    "source_previous_day_minute_run_id",
    "for_trade_date",
    "source_trade_date",
    "asset_kind",
    "identity_key",
    "code",
    "exchange",
    "canonical_minute_label",
    "canonical_bar_time",
    "raw_bar_time",
    "elapsed_index",
    "elapsed_count",
    "full_count",
    "cumulative_amount_yuan",
    "full_day_amount_yuan",
    "source_amount_unit",
    "canonical_amount_unit",
    "unit_conversion_factor",
    "normalization_policy",
    "raw_json",
    "trace_json",
    "created_at",
)

A1_CUMULATIVE_IDEMPOTENCY_HASH_COLUMNS = (
    "cumulative_id",
    "source_previous_day_minute_run_id",
    "for_trade_date",
    "source_trade_date",
    "asset_kind",
    "identity_key",
    "code",
    "exchange",
    "canonical_minute_label",
    "elapsed_index",
    "elapsed_count",
    "full_count",
    "cumulative_amount_yuan",
    "full_day_amount_yuan",
    "source_amount_unit",
    "canonical_amount_unit",
    "unit_conversion_factor",
    "normalization_policy",
)


class A1CumulativeAmountWriterBlocked(RuntimeError):
    """Raised when cumulative materialization must fail closed."""


def build_previous_day_cumulative_amount_write_plan(
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]],
    *,
    source_previous_day_minute_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    expected_object_counts_by_asset: Mapping[str, int] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build cumulative rows plus deterministic write/idempotency metadata."""

    materialized_at = created_at or datetime.now(timezone.utc).isoformat()
    build_result = build_previous_day_cumulative_amount_rows(
        rows_by_asset,
        source_previous_day_minute_run_id=source_previous_day_minute_run_id,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        created_at=materialized_at,
    )
    rows = {
        asset_kind: list((build_result.get("rows_by_asset") or {}).get(asset_kind) or [])
        for asset_kind in A1_CUMULATIVE_ASSET_KINDS
    }
    actual_object_counts = {
        asset_kind: len({str(row.get("identity_key") or "") for row in rows[asset_kind] if row.get("identity_key")})
        for asset_kind in A1_CUMULATIVE_ASSET_KINDS
    }
    errors = list(build_result.get("errors") or [])
    if expected_object_counts_by_asset is not None:
        for asset_kind in A1_CUMULATIVE_ASSET_KINDS:
            expected = int(expected_object_counts_by_asset.get(asset_kind) or 0)
            actual = int(actual_object_counts.get(asset_kind) or 0)
            if expected != actual:
                errors.append(
                    {
                        "asset_kind": asset_kind,
                        "reason": "expected_object_count_mismatch",
                        "expected": expected,
                        "actual": actual,
                    }
                )
    expected_row_hash_by_asset = {
        asset_kind: _stable_rows_hash(rows[asset_kind])
        for asset_kind in A1_CUMULATIVE_ASSET_KINDS
    }
    quality_summary = dict(build_result.get("quality_summary") or {})
    if errors:
        quality_summary["status"] = "failed"
        quality_summary["error_count"] = len(errors)
        quality_summary["blocked_reasons"] = sorted(
            {str(error.get("reason") or "") for error in errors if error.get("reason")}
        )
    return {
        "stage": "N3_A1_previous_day_cumulative_amount_write_plan",
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "status": quality_summary.get("status"),
        "rows_by_asset": rows,
        "expected_row_count_by_asset": {asset_kind: len(rows[asset_kind]) for asset_kind in A1_CUMULATIVE_ASSET_KINDS},
        "expected_object_count_by_asset": dict(expected_object_counts_by_asset or actual_object_counts),
        "actual_object_count_by_asset": actual_object_counts,
        "expected_row_hash_by_asset": expected_row_hash_by_asset,
        "quality_summary": quality_summary,
        "errors": errors,
        "side_effects": {
            "writes_db": False,
            "writes_cumulative_tables": False,
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "downstream_layers_touched": False,
        },
    }


def write_previous_day_cumulative_amount_rows(
    cur: Any,
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]],
    *,
    source_previous_day_minute_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    expected_object_counts_by_asset: Mapping[str, int] | None = None,
    existing_target_summary: Mapping[str, Mapping[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Materialize cumulative rows into physical cumulative tables.

    Existing non-empty targets are accepted only when every physical table has
    the exact expected count and deterministic hash. Any partial or mismatched
    target is treated as dirty and blocked.
    """

    plan = build_previous_day_cumulative_amount_write_plan(
        rows_by_asset,
        source_previous_day_minute_run_id=source_previous_day_minute_run_id,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        expected_object_counts_by_asset=expected_object_counts_by_asset,
        created_at=created_at,
    )
    if plan["status"] != "passed":
        reasons = ", ".join(sorted({str(error.get("reason") or "") for error in plan["errors"] if error.get("reason")}))
        raise A1CumulativeAmountWriterBlocked(
            "BLOCKED_A1_CUMULATIVE_SOURCE_INVALID"
            + (f": {reasons}" if reasons else "")
        )

    existing = dict(existing_target_summary or fetch_existing_cumulative_target_summary(cur, source_previous_day_minute_run_id))
    action = _classify_existing_target_state(plan, existing)
    if action == "dirty":
        raise A1CumulativeAmountWriterBlocked(
            "BLOCKED_A1_CUMULATIVE_TARGET_DIRTY: "
            f"source_previous_day_minute_run_id={source_previous_day_minute_run_id}"
        )
    if action == "idempotent_noop":
        return _write_report(plan, write_action=action, inserted_row_count_by_asset={asset_kind: 0 for asset_kind in A1_CUMULATIVE_ASSET_KINDS})

    inserted: dict[str, int] = {}
    for asset_kind in A1_CUMULATIVE_ASSET_KINDS:
        inserted[asset_kind] = insert_previous_day_cumulative_asset_rows(
            cur,
            asset_kind=asset_kind,
            rows=plan["rows_by_asset"][asset_kind],
        )
    return _write_report(plan, write_action="inserted", inserted_row_count_by_asset=inserted)


def insert_previous_day_cumulative_asset_rows(
    cur: Any,
    *,
    asset_kind: str,
    rows: Sequence[Mapping[str, Any]],
) -> int:
    if asset_kind not in A1_CUMULATIVE_TABLES:
        raise A1CumulativeAmountWriterBlocked(f"unsupported asset_kind: {asset_kind}")
    if not rows:
        return 0
    table_name = A1_CUMULATIVE_TABLES[asset_kind]
    values = [
        tuple(_db_value(column, row.get(column)) for column in A1_CUMULATIVE_INSERT_COLUMNS)
        for row in rows
    ]
    update_columns = (
        "canonical_bar_time",
        "raw_bar_time",
        "elapsed_index",
        "elapsed_count",
        "full_count",
        "cumulative_amount_yuan",
        "full_day_amount_yuan",
        "source_amount_unit",
        "canonical_amount_unit",
        "unit_conversion_factor",
        "normalization_policy",
        "raw_json",
        "trace_json",
    )
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
    cur.executemany(
        f"""
        INSERT INTO {table_name} ({", ".join(A1_CUMULATIVE_INSERT_COLUMNS)})
        VALUES ({", ".join(["%s"] * len(A1_CUMULATIVE_INSERT_COLUMNS))})
        ON CONFLICT (source_previous_day_minute_run_id, identity_key, canonical_minute_label)
        DO UPDATE SET {assignments}
        """,
        values,
    )
    return len(values)


def fetch_existing_cumulative_target_summary(
    cur: Any,
    source_previous_day_minute_run_id: str,
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for asset_kind, table_name in A1_CUMULATIVE_TABLES.items():
        cur.execute(
            f"""
            SELECT {", ".join(A1_CUMULATIVE_IDEMPOTENCY_HASH_COLUMNS)}
            FROM {table_name}
            WHERE source_previous_day_minute_run_id = %s
            ORDER BY identity_key, canonical_minute_label
            """,
            (source_previous_day_minute_run_id,),
        )
        fetched_rows = list(cur.fetchall()) if hasattr(cur, "fetchall") else []
        rows = [_mapping_from_cursor_row(row) for row in fetched_rows]
        summary[asset_kind] = {
            "row_count": len(rows),
            "row_hash": _stable_rows_hash(rows),
        }
    return summary


def build_previous_day_cumulative_amount_rollback_sql(source_previous_day_minute_run_id: str) -> str:
    escaped_run_id = source_previous_day_minute_run_id.replace("'", "''")
    deletes = "\n".join(
        f"  DELETE FROM {table_name} WHERE source_previous_day_minute_run_id = '{escaped_run_id}';"
        for table_name in A1_CUMULATIVE_TABLES.values()
    )
    return f"""-- Scoped rollback for N3-A1 previous-day cumulative amount materialization.
-- Execute only under an explicit rollback gate.
DO $$
DECLARE
  outbox_refs bigint;
  inbox_refs bigint;
  checkpoint_refs bigint;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = '{escaped_run_id}' OR payload_json::text LIKE '%{escaped_run_id}%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = '{escaped_run_id}' OR payload_json::text LIKE '%{escaped_run_id}%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%{escaped_run_id}%';

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0 THEN
    RAISE EXCEPTION 'blocked rollback for {escaped_run_id}: event refs exist';
  END IF;

{deletes}
END $$;
"""


def _classify_existing_target_state(plan: Mapping[str, Any], existing: Mapping[str, Mapping[str, Any]]) -> str:
    expected_counts = plan.get("expected_row_count_by_asset") or {}
    expected_hashes = plan.get("expected_row_hash_by_asset") or {}
    existing_counts = {
        asset_kind: int((existing.get(asset_kind) or {}).get("row_count") or 0)
        for asset_kind in A1_CUMULATIVE_ASSET_KINDS
    }
    if all(count == 0 for count in existing_counts.values()):
        return "insert"
    all_match = True
    for asset_kind in A1_CUMULATIVE_ASSET_KINDS:
        row_count = existing_counts[asset_kind]
        row_hash = str((existing.get(asset_kind) or {}).get("row_hash") or "")
        if row_count != int(expected_counts.get(asset_kind) or 0) or row_hash != str(expected_hashes.get(asset_kind) or ""):
            all_match = False
            break
    return "idempotent_noop" if all_match else "dirty"


def _write_report(
    plan: Mapping[str, Any],
    *,
    write_action: str,
    inserted_row_count_by_asset: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "stage": "N3_A1_previous_day_cumulative_amount_writer",
        "status": "passed",
        "write_action": write_action,
        "source_previous_day_minute_run_id": plan["source_previous_day_minute_run_id"],
        "for_trade_date": plan["for_trade_date"],
        "source_trade_date": plan["source_trade_date"],
        "expected_row_count_by_asset": dict(plan["expected_row_count_by_asset"]),
        "inserted_row_count_by_asset": dict(inserted_row_count_by_asset),
        "expected_row_hash_by_asset": dict(plan["expected_row_hash_by_asset"]),
        "quality_summary": dict(plan["quality_summary"]),
        "side_effects": {
            "writes_cumulative_tables": write_action == "inserted",
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "downstream_layers_touched": False,
        },
    }


def _db_value(column: str, value: Any) -> Any:
    if column in {"raw_json", "trace_json"}:
        return Jsonb(normalize_jsonable(value or {}))
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def _stable_rows_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    normalized = [
        {
            column: _hash_normalize(row.get(column))
            for column in A1_CUMULATIVE_IDEMPOTENCY_HASH_COLUMNS
        }
        for row in sorted(
            rows,
            key=lambda item: (
                str(item.get("identity_key") or ""),
                str(item.get("canonical_minute_label") or ""),
            ),
        )
    ]
    payload = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hash_normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, float):
        return round(value, 8)
    return normalize_jsonable(value)


def _mapping_from_cursor_row(row: Any) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        return row
    return {
        column: value
        for column, value in zip(A1_CUMULATIVE_IDEMPOTENCY_HASH_COLUMNS, row, strict=False)
    }
