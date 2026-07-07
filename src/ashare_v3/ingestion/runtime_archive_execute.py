"""N1/archive run-once helpers for sealed N3-N6 runtime Parquet archive."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping

import pandas as pd
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq

from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.runtime_archive import (
    DEFAULT_RUNTIME_ARCHIVE_ROOT,
    make_runtime_archive_file_path,
    make_runtime_archive_manifest_path,
    make_runtime_archive_report_path,
    runtime_archive_side_effects,
)


DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"
DEFAULT_ARCHIVE_CHUNKSIZE = 100_000
PARTITIONED_EXPORT_TABLES = frozenset(
    {
        ("n3", "stock_minute_bar_1m"),
        ("n3", "stock_action_confirmation_projection_metric"),
        ("n4", "common_trigger_state"),
    }
)
SOURCE_LAYER_BY_RUNTIME_LAYER = {
    "n3": "N3_market_data",
    "n4": "N4_trigger",
    "n5": "N5_action",
}
EOD_RECONCILIATION_ITEM_TABLES = (
    ("stock_eod_reconciliation_item", "stock_eod_snapshot"),
    ("index_eod_reconciliation_item", "index_eod_snapshot"),
    ("board_eod_reconciliation_item", "board_eod_snapshot"),
)


@dataclass(frozen=True)
class RuntimeArchiveQuerySpec:
    layer: str
    table: str
    sql: str
    params: tuple[Any, ...]


def build_runtime_archive_query_specs(trade_date: str) -> tuple[RuntimeArchiveQuerySpec, ...]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    specs: list[RuntimeArchiveQuerySpec] = []
    specs.extend(eod_reconciliation_item_query_specs(normalized_trade_date))
    for layer, table, date_column in runtime_table_specs():
        specs.append(
            RuntimeArchiveQuerySpec(
                layer=layer,
                table=table,
                sql=f"select * from {table} where {date_column} = %s order by 1",
                params=(normalized_trade_date,),
            )
        )
    for layer, source_layer in SOURCE_LAYER_BY_RUNTIME_LAYER.items():
        specs.extend(event_infra_query_specs(layer, source_layer, normalized_trade_date))
    specs.extend(n6_query_specs(normalized_trade_date))
    return tuple(specs)


def eod_reconciliation_item_query_specs(trade_date: str) -> tuple[RuntimeArchiveQuerySpec, ...]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    return tuple(
        RuntimeArchiveQuerySpec(
            layer="n3",
            table=child_table,
            sql=(
                f"select child.* from {child_table} child "
                f"join {parent_table} parent on parent.eod_snapshot_id = child.eod_snapshot_id "
                "where parent.trade_date = %s order by child.eod_snapshot_id"
            ),
            params=(normalized_trade_date,),
        )
        for child_table, parent_table in EOD_RECONCILIATION_ITEM_TABLES
    )


def runtime_table_specs() -> tuple[tuple[str, str, str], ...]:
    return (
        ("n3", "common_market_data_run", "for_trade_date"),
        ("n3", "common_market_data_quality_item", "for_trade_date"),
        ("n3", "common_market_data_subscription_candidate", "for_trade_date"),
        ("n3", "common_market_data_subscription", "for_trade_date"),
        ("n3", "common_market_data_pull_plan", "for_trade_date"),
        ("n3", "stock_previous_day_minute_preload_status", "for_trade_date"),
        ("n3", "index_previous_day_minute_preload_status", "for_trade_date"),
        ("n3", "board_previous_day_minute_preload_status", "for_trade_date"),
        ("n3", "stock_realtime_daily_snapshot", "trade_date"),
        ("n3", "index_realtime_daily_snapshot", "trade_date"),
        ("n3", "board_realtime_daily_snapshot", "trade_date"),
        ("n3", "stock_projection_enrichment_v4_metric", "trade_date"),
        ("n3", "index_projection_enrichment_v4_metric", "trade_date"),
        ("n3", "board_projection_enrichment_v4_metric", "trade_date"),
        ("n3", "index_realtime_hint_projection_metric", "trade_date"),
        ("n3", "board_realtime_hint_projection_metric", "trade_date"),
        ("n3", "stock_eod_snapshot", "trade_date"),
        ("n3", "index_eod_snapshot", "trade_date"),
        ("n3", "board_eod_snapshot", "trade_date"),
        ("n3", "stock_minute_bar_1m", "trade_date"),
        ("n3", "index_minute_bar_1m", "trade_date"),
        ("n3", "board_minute_bar_1m", "trade_date"),
        ("n3", "stock_realtime_projection_metric", "trade_date"),
        ("n3", "index_realtime_projection_metric", "trade_date"),
        ("n3", "board_realtime_projection_metric", "trade_date"),
        ("n3", "stock_action_confirmation_projection_metric", "trade_date"),
        ("n3", "index_action_confirmation_projection_metric", "trade_date"),
        ("n3", "board_action_confirmation_projection_metric", "trade_date"),
        ("n3", "stock_closed_30m_summary", "trade_date"),
        ("n3", "stock_closed_30m_signal_enrichment", "trade_date"),
        ("n3", "index_closed_30m_summary", "trade_date"),
        ("n3", "index_closed_30m_signal_enrichment", "trade_date"),
        ("n3", "board_closed_30m_summary", "trade_date"),
        ("n3", "board_closed_30m_signal_enrichment", "trade_date"),
        ("n4", "common_trigger_run", "for_trade_date"),
        ("n4", "common_trigger_quality_item", "for_trade_date"),
        ("n4", "stock_trigger_context_snapshot", "for_trade_date"),
        ("n4", "index_trigger_context_snapshot", "for_trade_date"),
        ("n4", "board_trigger_context_snapshot", "for_trade_date"),
        ("n4", "common_trigger_state", "for_trade_date"),
        ("n4", "common_trigger_match", "for_trade_date"),
        ("n5", "common_action_run", "for_trade_date"),
        ("n5", "common_action_quality_item", "for_trade_date"),
        ("n5", "stock_action_fact", "for_trade_date"),
        ("n5", "index_action_fact", "for_trade_date"),
        ("n5", "board_action_fact", "for_trade_date"),
        ("n5", "common_action_event", "for_trade_date"),
    )


def event_infra_query_specs(layer: str, source_layer: str, trade_date: str) -> tuple[RuntimeArchiveQuerySpec, ...]:
    return (
        RuntimeArchiveQuerySpec(
            layer=layer,
            table="common_event_outbox",
            sql=(
                "select * from common_event_outbox "
                "where trade_date = %s and source_layer = %s order by outbox_id"
            ),
            params=(trade_date, source_layer),
        ),
        RuntimeArchiveQuerySpec(
            layer=layer,
            table="common_event_ledger",
            sql=(
                "select * from common_event_ledger "
                "where trade_date = %s and source_layer = %s order by event_id"
            ),
            params=(trade_date, source_layer),
        ),
        RuntimeArchiveQuerySpec(
            layer=layer,
            table="common_event_inbox",
            sql=(
                "select * from common_event_inbox i "
                "where i.source_layer = %s "
                "and exists (select 1 from common_event_outbox o "
                "where o.event_id = i.event_id and o.trade_date = %s and o.source_layer = %s) "
                "order by i.inbox_id"
            ),
            params=(source_layer, trade_date, source_layer),
        ),
        RuntimeArchiveQuerySpec(
            layer=layer,
            table="common_event_delivery_attempt",
            sql=(
                "select * from common_event_delivery_attempt d "
                "where exists (select 1 from common_event_outbox o "
                "where o.event_id = d.event_id and o.trade_date = %s and o.source_layer = %s) "
                "order by d.delivery_attempt_id"
            ),
            params=(trade_date, source_layer),
        ),
        RuntimeArchiveQuerySpec(
            layer=layer,
            table="common_event_consumer_checkpoint",
            sql=(
                "select * from common_event_consumer_checkpoint "
                "where source_layer = %s and last_event_time::date = to_date(%s, 'YYYYMMDD') "
                "order by consumer_name, partition_key"
            ),
            params=(source_layer, trade_date),
        ),
    )


def n6_query_specs(trade_date: str) -> tuple[RuntimeArchiveQuerySpec, ...]:
    action_run_filter = "select run_id from common_action_run where for_trade_date = %s"
    projection_run_filter = (
        "select user_projection_run_id from user_projection_run "
        f"where source_action_run_id in ({action_run_filter})"
    )
    return (
        RuntimeArchiveQuerySpec(
            layer="n6",
            table="user_projection_run",
            sql=(
                "select * from user_projection_run "
                f"where source_action_run_id in ({action_run_filter}) order by user_projection_run_id"
            ),
            params=(trade_date,),
        ),
        RuntimeArchiveQuerySpec(
            layer="n6",
            table="user_signal_projection",
            sql=(
                "select * from user_signal_projection "
                f"where user_projection_run_id in ({projection_run_filter}) order by user_signal_projection_id"
            ),
            params=(trade_date,),
        ),
        RuntimeArchiveQuerySpec(
            layer="n6",
            table="user_signal_card",
            sql=(
                "select * from user_signal_card "
                f"where user_projection_run_id in ({projection_run_filter}) order by user_signal_card_id"
            ),
            params=(trade_date,),
        ),
        RuntimeArchiveQuerySpec(
            layer="n6",
            table="user_notification_queue",
            sql=(
                "select * from user_notification_queue "
                f"where user_projection_run_id in ({projection_run_filter}) order by user_notification_queue_id"
            ),
            params=(trade_date,),
        ),
    )


def read_runtime_archive_frames(
    *,
    dsn: str,
    specs: tuple[RuntimeArchiveQuerySpec, ...],
) -> dict[tuple[str, str], pd.DataFrame]:
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    with psycopg.connect(dsn) as conn:
        for spec in specs:
            frames[(spec.layer, spec.table)] = pd.read_sql_query(spec.sql, conn, params=spec.params)
    return frames


def read_runtime_archive_frame(conn: Any, spec: RuntimeArchiveQuerySpec) -> pd.DataFrame:
    return pd.read_sql_query(spec.sql, conn, params=spec.params)


def read_runtime_archive_frame_chunks(
    conn: Any,
    spec: RuntimeArchiveQuerySpec,
    chunksize: int = DEFAULT_ARCHIVE_CHUNKSIZE,
) -> Any:
    return pd.read_sql_query(spec.sql, conn, params=spec.params, chunksize=int(chunksize))


def write_runtime_archive_frame(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    layer: str,
    table: str,
    frame: pd.DataFrame,
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    output_path = Path(
        make_runtime_archive_file_path(
            archive_root=str(archive_root),
            trade_date=normalized_trade_date,
            layer=layer,
            table=table,
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_frame = sanitize_frame_for_parquet(frame)
    parquet_frame.to_parquet(output_path, index=False)
    row_count = int(len(parquet_frame))
    verified_row_count = int(len(pd.read_parquet(output_path)))
    return {
        "layer": layer,
        "table": table,
        "row_count": row_count,
        "verified_row_count": verified_row_count,
        "checksum": f"sha256:{sha256(output_path.read_bytes()).hexdigest()}",
        "path": str(output_path),
        "format": "parquet",
    }


def write_runtime_archive_chunked_frame(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    layer: str,
    table: str,
    chunks: Any,
    timing: dict[str, Any],
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    if should_partition_table(layer=layer, table=table):
        return write_runtime_archive_partitioned_frame(
            trade_date=normalized_trade_date,
            archive_root=archive_root,
            layer=layer,
            table=table,
            chunks=chunks,
            timing=timing,
        )

    output_path = Path(
        make_runtime_archive_file_path(
            archive_root=str(archive_root),
            trade_date=normalized_trade_date,
            layer=layer,
            table=table,
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    row_count = 0
    chunk_count = 0
    writer: pq.ParquetWriter | None = None
    iterator = iter(chunks)
    timing["read_started_at"] = now_iso()
    read_duration_ms = 0.0
    write_duration_ms = 0.0
    write_started_at: str | None = None
    write_finished_at: str | None = None
    try:
        while True:
            read_start = perf_counter()
            try:
                frame = next(iterator)
            except StopIteration:
                break
            read_duration_ms += elapsed_ms(read_start)
            if frame is None:
                continue
            parquet_frame = sanitize_frame_for_parquet(frame)
            if write_started_at is None:
                write_started_at = now_iso()
            write_start = perf_counter()
            arrow_table = pa.Table.from_pandas(parquet_frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(output_path, arrow_table.schema)
            else:
                arrow_table = arrow_table.cast(writer.schema)
            writer.write_table(arrow_table)
            write_duration_ms += elapsed_ms(write_start)
            write_finished_at = now_iso()
            row_count += int(len(parquet_frame))
            chunk_count += 1
            del frame
            del parquet_frame
            del arrow_table
    finally:
        timing["read_finished_at"] = now_iso()
        timing["read_duration_ms"] = round(read_duration_ms, 3)
        if writer is not None:
            writer.close()

    if chunk_count == 0:
        if write_started_at is None:
            write_started_at = now_iso()
        write_start = perf_counter()
        pd.DataFrame().to_parquet(output_path, index=False)
        write_duration_ms += elapsed_ms(write_start)
        write_finished_at = now_iso()

    timing["write_started_at"] = write_started_at
    timing["write_finished_at"] = write_finished_at or now_iso()
    timing["write_duration_ms"] = round(write_duration_ms, 3)
    verified_row_count = int(pq.ParquetFile(output_path).metadata.num_rows)
    return {
        "layer": layer,
        "table": table,
        "row_count": row_count,
        "verified_row_count": verified_row_count,
        "checksum": f"sha256:{sha256(output_path.read_bytes()).hexdigest()}",
        "path": str(output_path),
        "format": "parquet",
        "chunk_count": chunk_count,
    }


def write_runtime_archive_partitioned_frame(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    layer: str,
    table: str,
    chunks: Any,
    timing: dict[str, Any],
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    output_dir = (
        Path(archive_root)
        / f"trade_date={normalized_trade_date}"
        / layer
        / table
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_part in output_dir.glob("part-*.parquet"):
        stale_part.unlink()

    row_count = 0
    verified_row_count = 0
    part_files: list[dict[str, Any]] = []
    iterator = iter(chunks)
    timing["read_started_at"] = now_iso()
    read_duration_ms = 0.0
    write_duration_ms = 0.0
    write_started_at: str | None = None
    write_finished_at: str | None = None
    part_index = 0

    while True:
        read_start = perf_counter()
        try:
            frame = next(iterator)
        except StopIteration:
            break
        read_duration_ms += elapsed_ms(read_start)
        if frame is None:
            continue
        parquet_frame = sanitize_frame_for_parquet(frame)
        part_path = output_dir / f"part-{part_index:05d}.parquet"
        if write_started_at is None:
            write_started_at = now_iso()
        write_start = perf_counter()
        parquet_frame.to_parquet(part_path, index=False)
        write_duration_ms += elapsed_ms(write_start)
        write_finished_at = now_iso()
        part_row_count = int(len(parquet_frame))
        part_verified_row_count = int(pq.ParquetFile(part_path).metadata.num_rows)
        part_checksum = f"sha256:{sha256(part_path.read_bytes()).hexdigest()}"
        part_files.append(
            {
                "part_index": part_index,
                "row_count": part_row_count,
                "verified_row_count": part_verified_row_count,
                "checksum": part_checksum,
                "path": str(part_path),
                "format": "parquet",
            }
        )
        row_count += part_row_count
        verified_row_count += part_verified_row_count
        part_index += 1
        del frame
        del parquet_frame

    timing["read_finished_at"] = now_iso()
    timing["read_duration_ms"] = round(read_duration_ms, 3)
    if write_started_at is None:
        write_started_at = now_iso()
        write_finished_at = write_started_at
    timing["write_started_at"] = write_started_at
    timing["write_finished_at"] = write_finished_at or now_iso()
    timing["write_duration_ms"] = round(write_duration_ms, 3)
    combined_checksum = combined_part_checksum(part_files)
    return {
        "layer": layer,
        "table": table,
        "row_count": row_count,
        "verified_row_count": verified_row_count,
        "checksum": combined_checksum,
        "path": str(output_dir),
        "format": "parquet_partitioned",
        "chunk_count": len(part_files),
        "part_files": part_files,
    }


def should_partition_table(*, layer: str, table: str) -> bool:
    return (layer, table) in PARTITIONED_EXPORT_TABLES


def combined_part_checksum(part_files: list[dict[str, Any]]) -> str:
    digest = sha256()
    for part in part_files:
        digest.update(str(part.get("checksum") or "").encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def write_runtime_archive_frames(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    frames: Mapping[tuple[str, str], pd.DataFrame],
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    files: list[dict[str, Any]] = []
    for (layer, table), frame in sorted(frames.items()):
        files.append(
            write_runtime_archive_frame(
                trade_date=normalized_trade_date,
                archive_root=archive_root,
                layer=layer,
                table=table,
                frame=frame,
            )
        )
    return write_runtime_archive_manifest(
        trade_date=normalized_trade_date,
        archive_root=archive_root,
        files=files,
    )


def write_runtime_archive_manifest(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    files: list[dict[str, Any]],
    result: str | None = None,
    table_timings: list[dict[str, Any]] | None = None,
    blocked_reason: str | None = None,
    current_table: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    root = Path(archive_root)
    manifest_path = Path(
        make_runtime_archive_manifest_path(archive_root=str(root), trade_date=normalized_trade_date)
    )
    report_path = Path(make_runtime_archive_report_path(archive_root=str(root), trade_date=normalized_trade_date))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    row_count_match = all(item["row_count"] == item["verified_row_count"] for item in files)
    manifest = {
        "manifest_version": "v3-runtime-archive.v1",
        "result": result or ("ARCHIVED_VERIFIED" if row_count_match else "BLOCKED"),
        "trade_date": normalized_trade_date,
        "archive_root": str(root),
        "file_count": len(files),
        "total_rows": sum(int(item["row_count"]) for item in files),
        "files": files,
        "table_timings": table_timings or [],
        "blocked_reason": blocked_reason,
        "current_table": current_table,
        "manifest_path": str(manifest_path),
        "report_path": str(report_path),
        "row_count_match": row_count_match,
        "checksum_algorithm": "sha256",
        "cleanup_eligible": False,
        "cleanup_blockers": ["manual_cleanup_required"],
        "side_effects": {
            **runtime_archive_side_effects(),
            "writes_archive_files": True,
            "archive_files_written": True,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    report_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    return manifest


def read_existing_verified_manifest(
    *,
    trade_date: str,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    required_table_keys: set[tuple[str, str]] | None = None,
) -> dict[str, Any] | None:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    manifest_path = Path(
        make_runtime_archive_manifest_path(
            archive_root=str(archive_root),
            trade_date=normalized_trade_date,
        )
    )
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if manifest.get("result") != "ARCHIVED_VERIFIED":
        return None
    if manifest.get("row_count_match") is not True:
        return None
    if manifest.get("checksum_algorithm") != "sha256":
        return None
    if manifest.get("cleanup_eligible") is not False:
        return None
    if required_table_keys:
        existing_table_keys = {
            (str(item.get("layer")), str(item.get("table")))
            for item in list(manifest.get("files") or [])
        }
        if not required_table_keys <= existing_table_keys:
            return None
    result = dict(manifest)
    result["result"] = "IDEMPOTENT_ARCHIVE_ALREADY_VERIFIED"
    result["reason"] = "existing_verified_manifest"
    result["manifest_path"] = str(manifest_path)
    result["side_effects"] = {
        **runtime_archive_side_effects(),
        "writes_archive_files": False,
        "archive_files_written": False,
    }
    result.setdefault("table_timings", [])
    return result


def sanitize_frame_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].map(json_safe_value)
    return result


def json_safe_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)
    if isinstance(value, Decimal):
        return str(value)
    return value


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def now_iso() -> str:
    return datetime.now().isoformat()


def elapsed_ms(start: float) -> float:
    return (perf_counter() - start) * 1000


def build_table_timing(spec: RuntimeArchiveQuerySpec) -> dict[str, Any]:
    return {
        "layer": spec.layer,
        "table": spec.table,
        "read_started_at": None,
        "read_finished_at": None,
        "read_duration_ms": 0.0,
        "write_started_at": None,
        "write_finished_at": None,
        "write_duration_ms": 0.0,
        "row_count": 0,
        "verified_row_count": 0,
        "status": "planned",
    }


def export_spec_from_frame(
    *,
    conn: Any,
    spec: RuntimeArchiveQuerySpec,
    trade_date: str,
    archive_root: str | Path,
    frame_reader: Callable[[Any, RuntimeArchiveQuerySpec], pd.DataFrame],
    frame_writer: Callable[..., dict[str, Any]],
    timing: dict[str, Any],
) -> dict[str, Any]:
    timing["read_started_at"] = now_iso()
    read_start = perf_counter()
    frame = frame_reader(conn, spec)
    timing["read_finished_at"] = now_iso()
    timing["read_duration_ms"] = round(elapsed_ms(read_start), 3)
    try:
        timing["write_started_at"] = now_iso()
        write_start = perf_counter()
        file_item = frame_writer(
            trade_date=trade_date,
            archive_root=archive_root,
            layer=spec.layer,
            table=spec.table,
            frame=frame,
        )
        timing["write_finished_at"] = now_iso()
        timing["write_duration_ms"] = round(elapsed_ms(write_start), 3)
        return file_item
    finally:
        del frame


def export_spec_from_chunks(
    *,
    conn: Any,
    spec: RuntimeArchiveQuerySpec,
    trade_date: str,
    archive_root: str | Path,
    chunksize: int,
    chunk_reader: Callable[[Any, RuntimeArchiveQuerySpec, int], Any],
    timing: dict[str, Any],
) -> dict[str, Any]:
    chunks = chunk_reader(conn, spec, int(chunksize))
    return write_runtime_archive_chunked_frame(
        trade_date=trade_date,
        archive_root=archive_root,
        layer=spec.layer,
        table=spec.table,
        chunks=chunks,
        timing=timing,
    )


def execute_runtime_archive(
    *,
    trade_date: str,
    dsn: str = DEFAULT_DSN,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    force_refresh_archive: bool = False,
    query_specs: tuple[RuntimeArchiveQuerySpec, ...] | None = None,
    connection_factory: Callable[[str], Any] = psycopg.connect,
    frame_reader: Callable[[Any, RuntimeArchiveQuerySpec], pd.DataFrame] | None = None,
    frame_writer: Callable[..., dict[str, Any]] | None = None,
    chunk_reader: Callable[[Any, RuntimeArchiveQuerySpec, int], Any] = read_runtime_archive_frame_chunks,
    chunksize: int = DEFAULT_ARCHIVE_CHUNKSIZE,
) -> dict[str, Any]:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    specs = query_specs if query_specs is not None else build_runtime_archive_query_specs(normalized_trade_date)
    if not force_refresh_archive:
        existing = read_existing_verified_manifest(
            trade_date=normalized_trade_date,
            archive_root=archive_root,
            required_table_keys={(spec.layer, spec.table) for spec in specs},
        )
        if existing is not None:
            return existing

    files: list[dict[str, Any]] = []
    table_timings: list[dict[str, Any]] = []
    with connection_factory(dsn) as conn:
        for spec in specs:
            timing = build_table_timing(spec)
            try:
                if frame_reader is not None or frame_writer is not None:
                    file_item = export_spec_from_frame(
                        conn=conn,
                        spec=spec,
                        trade_date=normalized_trade_date,
                        archive_root=archive_root,
                        frame_reader=frame_reader or read_runtime_archive_frame,
                        frame_writer=frame_writer or write_runtime_archive_frame,
                        timing=timing,
                    )
                else:
                    file_item = export_spec_from_chunks(
                        conn=conn,
                        spec=spec,
                        trade_date=normalized_trade_date,
                        archive_root=archive_root,
                        chunksize=chunksize,
                        chunk_reader=chunk_reader,
                        timing=timing,
                    )
                timing["row_count"] = int(file_item.get("row_count") or 0)
                timing["verified_row_count"] = int(file_item.get("verified_row_count") or 0)
                timing["status"] = (
                    "passed" if timing["row_count"] == timing["verified_row_count"] else "blocked"
                )
                files.append(file_item)
                table_timings.append(timing)
            except Exception as exc:
                timing["read_finished_at"] = timing.get("read_finished_at") or now_iso()
                timing["write_finished_at"] = timing.get("write_finished_at") or now_iso()
                timing["status"] = "blocked"
                timing["blocked_reason"] = f"{type(exc).__name__}: {exc}"
                table_timings.append(timing)
                return write_runtime_archive_manifest(
                    trade_date=normalized_trade_date,
                    archive_root=archive_root,
                    files=files,
                    result="BLOCKED",
                    table_timings=table_timings,
                    blocked_reason=timing["blocked_reason"],
                    current_table={"layer": spec.layer, "table": spec.table},
                )
    return write_runtime_archive_manifest(
        trade_date=normalized_trade_date,
        archive_root=archive_root,
        files=files,
        table_timings=table_timings,
    )
