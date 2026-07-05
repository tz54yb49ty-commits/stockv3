"""N6 local display cache sync runner.

The runner is intentionally narrow and double-gated. It can only copy reviewed
N2 display_basis rows and N1 membership rows into N6-owned display cache
tables, then activate the new cache_run_id after row-count and validation
checks pass. It never writes upstream source tables, event infrastructure,
N3/N4/N5 facts, N6 projections/cards, proposals, orders, trades, positions,
PnL, workers, or real trade state.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


CACHE_RUN_ID = "n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1"
CACHE_VERSION = "n6_display_cache_v1"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260604_source_20260604_v1"
SOURCE_TRADE_DATE = "20260604"
MAPPING_STRATEGY = "cartesian_fanout_v1"
CONTRACT_PATH = "docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_CONTRACT.json"
PREFLIGHT_PATH = "docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_PREFLIGHT.json"
ROLLBACK_SQL_PATH = "sql/N6_local_display_cache_sync_20260604_rollback.sql"

CACHE_TABLES = (
    "n6_display_cache_run",
    "n6_stock_display_cache",
    "n6_index_display_cache",
    "n6_board_display_cache",
    "n6_index_membership_display_cache",
    "n6_board_membership_display_cache",
)
CHILD_CACHE_TABLES = CACHE_TABLES[1:]
ALLOWED_SOURCE_TABLES = (
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
    "index_membership_fact",
    "board_membership_fact",
)
FORBIDDEN_SOURCE_TOKENS = (
    "condition_basis",
    "condition_pool",
    "minute_target_scope",
    "raw_k",
    "live market",
    "common_trigger",
    "common_action",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)
EXPECTED_SOURCE_COUNTS = {
    "stock_display_source": 1952,
    "index_display_source": 9,
    "board_display_source": 428,
    "index_membership_source": 12841,
    "board_membership_source": 56960,
}
EXPECTED_ROWS = {
    "n6_display_cache_run": 1,
    "n6_stock_display_cache": 8370,
    "n6_index_display_cache": 40,
    "n6_board_display_cache": 1824,
    "n6_index_membership_display_cache": 12841,
    "n6_board_membership_display_cache": 56960,
    "total_excluding_run": 80035,
    "total_including_run": 80036,
}
ALLOWED_WRITE_TABLES = CACHE_TABLES
FORBIDDEN_WRITE_TABLES = (
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
    "index_membership_fact",
    "board_membership_fact",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_notification_queue",
)


@dataclass
class LocalDisplayCachePreflightSnapshot:
    cache_run_id: str
    cache_version: str
    source_condition_run_id: str
    source_trade_date: str
    mapping_strategy: str
    latest_active_n2_run_id: str | None
    latest_active_n2_status: str | None
    source_counts: dict[str, int]
    target_table_exists: dict[str, bool]
    target_row_counts: dict[str, int]
    preview_row_counts: dict[str, int]
    cache_run_id_rows: int
    active_cache_same_version_rows: int
    active_cache_same_source_version_rows: int
    scoped_target_rows: int
    duplicate_fanout_key: int
    duplicate_row_hash: int
    missing_required: int
    invalid_board_type: int
    invalid_direction: int
    null_identity_key: int


class LocalDisplayCacheSyncRepository(Protocol):
    def fetch_preflight_snapshot(
        self,
        *,
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
    ) -> LocalDisplayCachePreflightSnapshot:
        ...

    def commit_sync(
        self,
        *,
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
        expected_rows: dict[str, int],
    ) -> dict[str, object]:
        ...


class PostgresLocalDisplayCacheSyncRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def fetch_preflight_snapshot(
        self,
        *,
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
    ) -> LocalDisplayCachePreflightSnapshot:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            return self._fetch_snapshot(
                cur,
                cache_run_id=cache_run_id,
                cache_version=cache_version,
                source_condition_run_id=source_condition_run_id,
                source_trade_date=source_trade_date,
                mapping_strategy=mapping_strategy,
            )

    def commit_sync(
        self,
        *,
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
        expected_rows: dict[str, int],
    ) -> dict[str, object]:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                snapshot = self._fetch_snapshot(
                    cur,
                    cache_run_id=cache_run_id,
                    cache_version=cache_version,
                    source_condition_run_id=source_condition_run_id,
                    source_trade_date=source_trade_date,
                    mapping_strategy=mapping_strategy,
                )
                preflight = build_preflight(snapshot)
                if preflight["blockers"]:
                    raise RuntimeError("local display cache sync blocked by refreshed preflight")

                inserted = self._insert_cache_rows(
                    cur,
                    cache_run_id=cache_run_id,
                    cache_version=cache_version,
                    source_condition_run_id=source_condition_run_id,
                    source_trade_date=source_trade_date,
                    mapping_strategy=mapping_strategy,
                    expected_rows=expected_rows,
                )

        return {
            "committed": True,
            "inserted_rows": inserted,
            "activated": True,
        }

    def _fetch_snapshot(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        *,
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
    ) -> LocalDisplayCachePreflightSnapshot:
        target_table_exists = {table: self._object_exists(cur, table) for table in CACHE_TABLES}
        target_row_counts = {
            table: self._count_table(cur, table) if target_table_exists[table] else -1
            for table in CACHE_TABLES
        }
        latest_active = self._latest_active_n2_run(cur)
        source_counts = self._source_counts(cur, source_condition_run_id, source_trade_date)
        preview = self._preview_validation(cur, cache_run_id, cache_version, source_condition_run_id, source_trade_date)
        idempotency = self._idempotency_counts(cur, cache_run_id, cache_version, source_condition_run_id)
        return LocalDisplayCachePreflightSnapshot(
            cache_run_id=cache_run_id,
            cache_version=cache_version,
            source_condition_run_id=source_condition_run_id,
            source_trade_date=source_trade_date,
            mapping_strategy=mapping_strategy,
            latest_active_n2_run_id=latest_active.get("run_id"),
            latest_active_n2_status=latest_active.get("status"),
            source_counts=source_counts,
            target_table_exists=target_table_exists,
            target_row_counts=target_row_counts,
            preview_row_counts={
                "n6_display_cache_run": 1,
                "n6_stock_display_cache": preview["stock_display_preview"],
                "n6_index_display_cache": preview["index_display_preview"],
                "n6_board_display_cache": preview["board_display_preview"],
                "n6_index_membership_display_cache": source_counts["index_membership_source"],
                "n6_board_membership_display_cache": source_counts["board_membership_source"],
                "total_excluding_run": (
                    preview["stock_display_preview"]
                    + preview["index_display_preview"]
                    + preview["board_display_preview"]
                    + source_counts["index_membership_source"]
                    + source_counts["board_membership_source"]
                ),
                "total_including_run": (
                    preview["stock_display_preview"]
                    + preview["index_display_preview"]
                    + preview["board_display_preview"]
                    + source_counts["index_membership_source"]
                    + source_counts["board_membership_source"]
                    + 1
                ),
            },
            cache_run_id_rows=idempotency["cache_run_id_rows"],
            active_cache_same_version_rows=idempotency["active_cache_same_version_rows"],
            active_cache_same_source_version_rows=idempotency["active_cache_same_source_version_rows"],
            scoped_target_rows=idempotency["scoped_target_rows"],
            duplicate_fanout_key=preview["duplicate_fanout_key"],
            duplicate_row_hash=preview["duplicate_row_hash"],
            missing_required=preview["missing_required"],
            invalid_board_type=preview["invalid_board_type"],
            invalid_direction=preview["invalid_direction"],
            null_identity_key=preview["null_identity_key"],
        )

    def _object_exists(self, cur: psycopg.Cursor[dict[str, Any]], object_name: str) -> bool:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{object_name}",))
        return bool(cur.fetchone()["exists"])

    def _count_table(self, cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> int:
        cur.execute(f"SELECT count(*)::int AS count FROM {table_name}")
        return int(cur.fetchone()["count"])

    def _latest_active_n2_run(self, cur: psycopg.Cursor[dict[str, Any]]) -> dict[str, Any]:
        cur.execute(
            """
            SELECT run_id, status
            FROM common_condition_run
            WHERE status = 'passed_active'
            ORDER BY source_trade_date DESC, updated_at DESC NULLS LAST, run_id DESC
            LIMIT 1
            """
        )
        return dict(cur.fetchone() or {})

    def _source_counts(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        source_condition_run_id: str,
        source_trade_date: str,
    ) -> dict[str, int]:
        cur.execute(
            """
            SELECT
              (SELECT count(*)::int FROM stock_condition_display_basis WHERE run_id = %(run_id)s) AS stock_display_source,
              (SELECT count(*)::int FROM index_condition_display_basis WHERE run_id = %(run_id)s) AS index_display_source,
              (SELECT count(*)::int FROM board_condition_display_basis WHERE run_id = %(run_id)s) AS board_display_source,
              (SELECT count(*)::int FROM index_membership_fact WHERE trade_date = %(trade_date)s) AS index_membership_source,
              (SELECT count(*)::int FROM board_membership_fact WHERE trade_date = %(trade_date)s) AS board_membership_source
            """,
            {"run_id": source_condition_run_id, "trade_date": source_trade_date},
        )
        return {key: int(value) for key, value in dict(cur.fetchone()).items()}

    def _idempotency_counts(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
    ) -> dict[str, int]:
        cur.execute(
            """
            SELECT
              (SELECT count(*)::int FROM n6_display_cache_run
                WHERE cache_run_id = %(cache_run_id)s) AS cache_run_id_rows,
              (SELECT count(*)::int FROM n6_display_cache_run
                WHERE cache_version = %(cache_version)s AND is_active) AS active_cache_same_version_rows,
              (SELECT count(*)::int FROM n6_display_cache_run
                WHERE cache_version = %(cache_version)s
                  AND source_condition_run_id = %(source_condition_run_id)s
                  AND is_active) AS active_cache_same_source_version_rows,
              (
                (SELECT count(*)::int FROM n6_stock_display_cache WHERE cache_run_id = %(cache_run_id)s AND cache_version = %(cache_version)s) +
                (SELECT count(*)::int FROM n6_index_display_cache WHERE cache_run_id = %(cache_run_id)s AND cache_version = %(cache_version)s) +
                (SELECT count(*)::int FROM n6_board_display_cache WHERE cache_run_id = %(cache_run_id)s AND cache_version = %(cache_version)s) +
                (SELECT count(*)::int FROM n6_index_membership_display_cache WHERE cache_run_id = %(cache_run_id)s AND cache_version = %(cache_version)s) +
                (SELECT count(*)::int FROM n6_board_membership_display_cache WHERE cache_run_id = %(cache_run_id)s AND cache_version = %(cache_version)s)
              ) AS scoped_target_rows
            """,
            {
                "cache_run_id": cache_run_id,
                "cache_version": cache_version,
                "source_condition_run_id": source_condition_run_id,
            },
        )
        return {key: int(value) for key, value in dict(cur.fetchone()).items()}

    def _preview_validation(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
    ) -> dict[str, int]:
        cur.execute(
            """
            WITH source_display AS (
              SELECT 'stock'::text AS asset_kind,
                     stock_condition_display_basis_id::bigint AS source_display_basis_id,
                     run_id,
                     source_trade_date,
                     stock_identity_key AS identity_key,
                     NULL::text AS board_type,
                     selected_directions,
                     selected_condition_keys,
                     selected_signal_types,
                     source_version,
                     updated_at
              FROM stock_condition_display_basis
              WHERE run_id = %(source_condition_run_id)s
              UNION ALL
              SELECT 'index',
                     index_condition_display_basis_id::bigint,
                     run_id,
                     source_trade_date,
                     index_identity_key,
                     NULL::text,
                     selected_directions,
                     selected_condition_keys,
                     selected_signal_types,
                     source_version,
                     updated_at
              FROM index_condition_display_basis
              WHERE run_id = %(source_condition_run_id)s
              UNION ALL
              SELECT 'board',
                     board_condition_display_basis_id::bigint,
                     run_id,
                     source_trade_date,
                     board_identity_key,
                     board_type,
                     selected_directions,
                     selected_condition_keys,
                     selected_signal_types,
                     source_version,
                     updated_at
              FROM board_condition_display_basis
              WHERE run_id = %(source_condition_run_id)s
            ), fanout AS (
              SELECT %(cache_run_id)s::text AS cache_run_id,
                     %(cache_version)s::text AS cache_version,
                     sd.*,
                     d.direction,
                     ck.condition_key,
                     md5(jsonb_build_object(
                       'cache_run_id', %(cache_run_id)s::text,
                       'cache_version', %(cache_version)s::text,
                       'source_condition_run_id', %(source_condition_run_id)s::text,
                       'source_trade_date', %(source_trade_date)s::text,
                       'asset_kind', sd.asset_kind,
                       'source_display_basis_id', sd.source_display_basis_id,
                       'identity_key', sd.identity_key,
                       'direction', d.direction,
                       'condition_key', ck.condition_key,
                       'selected_signal_types', to_jsonb(sd.selected_signal_types),
                       'source_version', sd.source_version,
                       'updated_at', sd.updated_at
                     )::text) AS row_hash
              FROM source_display sd
              CROSS JOIN LATERAL unnest(sd.selected_directions) AS d(direction)
              CROSS JOIN LATERAL unnest(sd.selected_condition_keys) AS ck(condition_key)
            ), membership_hashes AS (
              SELECT md5(jsonb_build_object(
                       'cache_run_id', %(cache_run_id)s::text,
                       'cache_version', %(cache_version)s::text,
                       'source_condition_run_id', %(source_condition_run_id)s::text,
                       'source_trade_date', %(source_trade_date)s::text,
                       'source_table', 'index_membership_fact',
                       'index_identity_key', index_identity_key,
                       'stock_identity_key', stock_identity_key,
                       'trade_date', trade_date,
                       'source_version', source_version,
                       'source_batch_id', source_batch_id
                     )::text) AS row_hash,
                     0::int AS invalid_board_type,
                     CASE WHEN index_identity_key IS NULL OR stock_identity_key IS NULL THEN 1 ELSE 0 END AS null_identity_key,
                     CASE WHEN index_identity_key IS NULL OR stock_identity_key IS NULL OR index_code IS NULL OR stock_code IS NULL THEN 1 ELSE 0 END AS missing_required
              FROM index_membership_fact
              WHERE trade_date = %(source_trade_date)s
              UNION ALL
              SELECT md5(jsonb_build_object(
                       'cache_run_id', %(cache_run_id)s::text,
                       'cache_version', %(cache_version)s::text,
                       'source_condition_run_id', %(source_condition_run_id)s::text,
                       'source_trade_date', %(source_trade_date)s::text,
                       'source_table', 'board_membership_fact',
                       'board_identity_key', board_identity_key,
                       'board_type', board_type,
                       'stock_identity_key', stock_identity_key,
                       'trade_date', trade_date,
                       'source_version', source_version,
                       'source_batch_id', source_batch_id
                     )::text),
                     CASE WHEN board_type IS NULL OR board_type = '' OR board_type NOT IN ('tdx_industry','tdx_concept','tdx_region') THEN 1 ELSE 0 END,
                     CASE WHEN board_identity_key IS NULL OR stock_identity_key IS NULL THEN 1 ELSE 0 END,
                     CASE WHEN board_identity_key IS NULL OR stock_identity_key IS NULL OR board_code IS NULL OR stock_code IS NULL OR board_type IS NULL THEN 1 ELSE 0 END
              FROM board_membership_fact
              WHERE trade_date = %(source_trade_date)s
            )
            SELECT
              count(*) FILTER (WHERE asset_kind = 'stock')::int AS stock_display_preview,
              count(*) FILTER (WHERE asset_kind = 'index')::int AS index_display_preview,
              count(*) FILTER (WHERE asset_kind = 'board')::int AS board_display_preview,
              (count(*) - count(DISTINCT (source_display_basis_id, direction, condition_key)))::int AS duplicate_fanout_key,
              (
                (SELECT count(*) FROM fanout) - (SELECT count(DISTINCT row_hash) FROM fanout) +
                (SELECT count(*) FROM membership_hashes) - (SELECT count(DISTINCT row_hash) FROM membership_hashes)
              )::int AS duplicate_row_hash,
              (
                count(*) FILTER (
                  WHERE source_display_basis_id IS NULL
                     OR run_id IS NULL
                     OR source_trade_date IS NULL
                     OR identity_key IS NULL OR identity_key = ''
                     OR direction IS NULL
                     OR condition_key IS NULL
                     OR row_hash IS NULL
                ) +
                (SELECT coalesce(sum(missing_required), 0) FROM membership_hashes)
              )::int AS missing_required,
              (
                count(*) FILTER (
                  WHERE asset_kind = 'board'
                    AND (board_type IS NULL OR board_type = '' OR board_type NOT IN ('tdx_industry','tdx_concept','tdx_region'))
                ) +
                (SELECT coalesce(sum(invalid_board_type), 0) FROM membership_hashes)
              )::int AS invalid_board_type,
              count(*) FILTER (WHERE direction NOT IN ('buy','sell'))::int AS invalid_direction,
              (
                count(*) FILTER (WHERE identity_key IS NULL OR identity_key = '') +
                (SELECT coalesce(sum(null_identity_key), 0) FROM membership_hashes)
              )::int AS null_identity_key
            FROM fanout
            """,
            {
                "cache_run_id": cache_run_id,
                "cache_version": cache_version,
                "source_condition_run_id": source_condition_run_id,
                "source_trade_date": source_trade_date,
            },
        )
        return {key: int(value) for key, value in dict(cur.fetchone()).items()}

    def _insert_cache_rows(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        *,
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
        expected_rows: dict[str, int],
    ) -> dict[str, int]:
        cur.execute(
            """
            INSERT INTO n6_display_cache_run (
              cache_run_id,
              source_condition_run_id,
              source_trade_date,
              cache_version,
              status,
              is_active,
              row_counts_json,
              validation_summary_json
            )
            VALUES (%s, %s, %s, %s, 'building', false, %s, %s)
            """,
            (
                cache_run_id,
                source_condition_run_id,
                source_trade_date,
                cache_version,
                Jsonb(expected_rows),
                Jsonb({"mapping_strategy": mapping_strategy}),
            ),
        )
        inserted = {"n6_display_cache_run": 1}
        inserted.update(self._insert_display_cache(cur, cache_run_id, cache_version, source_condition_run_id, source_trade_date, mapping_strategy))
        inserted.update(self._insert_membership_cache(cur, cache_run_id, cache_version, source_condition_run_id, source_trade_date))
        if inserted != {key: expected_rows[key] for key in CACHE_TABLES}:
            raise RuntimeError(f"local display cache inserted row mismatch: {inserted}")
        cur.execute(
            """
            UPDATE n6_display_cache_run
               SET status = 'passed',
                   is_active = true,
                   finished_at = now(),
                   updated_at = now(),
                   row_counts_json = %s,
                   validation_summary_json = %s
             WHERE cache_run_id = %s
               AND cache_version = %s
            """,
            (
                Jsonb(inserted),
                Jsonb(
                    {
                        "duplicate_fanout_key": 0,
                        "duplicate_row_hash": 0,
                        "missing_required": 0,
                        "invalid_board_type": 0,
                        "invalid_direction": 0,
                        "null_identity_key": 0,
                    }
                ),
                cache_run_id,
                cache_version,
            ),
        )
        return inserted

    def _insert_display_cache(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        counts["n6_stock_display_cache"] = self._insert_stock_display(
            cur, cache_run_id, cache_version, source_condition_run_id, source_trade_date, mapping_strategy
        )
        counts["n6_index_display_cache"] = self._insert_index_display(
            cur, cache_run_id, cache_version, source_condition_run_id, source_trade_date, mapping_strategy
        )
        counts["n6_board_display_cache"] = self._insert_board_display(
            cur, cache_run_id, cache_version, source_condition_run_id, source_trade_date, mapping_strategy
        )
        return counts

    def _insert_stock_display(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
    ) -> int:
        cur.execute(
            """
            INSERT INTO n6_stock_display_cache (
              cache_run_id, cache_version, source_condition_run_id, source_trade_date,
              source_table, source_version, row_hash, source_row_hash, source_identity_key,
              source_selected_directions_json, source_selected_condition_keys_json, expansion_strategy,
              asset_kind, identity_key, stock_identity_key, code, name, display_code, display_name,
              display_title, display_summary, condition_key, original_condition_key, direction,
              selected_signal_types_json, period_summary_json, year_overheat_level, quarter_overheat_level,
              month_overheat_level, week_overheat_level, day_overheat_level, target_price_context_json,
              label_json, explanation_json, quality_status, source_condition_display_basis_id,
              source_updated_at
            )
            SELECT %(cache_run_id)s, %(cache_version)s, %(source_condition_run_id)s, %(source_trade_date)s,
                   'stock_condition_display_basis', s.source_version,
                   md5(jsonb_build_object('cache_run_id', %(cache_run_id)s::text, 'source_id', s.stock_condition_display_basis_id, 'direction', d.direction, 'condition_key', ck.condition_key)::text),
                   md5(jsonb_build_object('source_table', 'stock_condition_display_basis', 'source_id', s.stock_condition_display_basis_id, 'run_id', s.run_id, 'identity_key', s.stock_identity_key, 'selected_directions', to_jsonb(s.selected_directions), 'selected_condition_keys', to_jsonb(s.selected_condition_keys))::text),
                   s.stock_identity_key, to_jsonb(s.selected_directions), to_jsonb(s.selected_condition_keys),
                   %(mapping_strategy)s, 'stock', s.stock_identity_key, s.stock_identity_key, s.code, s.name,
                   s.display_code, s.display_name, s.display_title, s.display_summary, ck.condition_key,
                   ck.condition_key, d.direction, to_jsonb(s.selected_signal_types), s.period_grade_summary_json,
                   s.period_grade_y, s.period_grade_q, s.period_grade_m, s.period_grade_w, s.period_grade_d,
                   s.target_price_summary_json, jsonb_build_object(), s.condition_summary_json,
                   s.quality_status, s.stock_condition_display_basis_id, s.updated_at
            FROM stock_condition_display_basis s
            CROSS JOIN LATERAL unnest(s.selected_directions) AS d(direction)
            CROSS JOIN LATERAL unnest(s.selected_condition_keys) AS ck(condition_key)
            WHERE s.run_id = %(source_condition_run_id)s
            """,
            {
                "cache_run_id": cache_run_id,
                "cache_version": cache_version,
                "source_condition_run_id": source_condition_run_id,
                "source_trade_date": source_trade_date,
                "mapping_strategy": mapping_strategy,
            },
        )
        return int(cur.rowcount or 0)

    def _insert_index_display(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
    ) -> int:
        cur.execute(
            """
            INSERT INTO n6_index_display_cache (
              cache_run_id, cache_version, source_condition_run_id, source_trade_date,
              source_table, source_version, row_hash, source_row_hash, source_identity_key,
              source_selected_directions_json, source_selected_condition_keys_json, expansion_strategy,
              asset_kind, identity_key, index_identity_key, code, name, display_code, display_name,
              display_title, display_summary, condition_key, original_condition_key, direction,
              selected_signal_types_json, period_summary_json, year_overheat_level, quarter_overheat_level,
              month_overheat_level, week_overheat_level, day_overheat_level, target_price_context_json,
              label_json, explanation_json, quality_status, source_condition_display_basis_id,
              source_updated_at
            )
            SELECT %(cache_run_id)s, %(cache_version)s, %(source_condition_run_id)s, %(source_trade_date)s,
                   'index_condition_display_basis', i.source_version,
                   md5(jsonb_build_object('cache_run_id', %(cache_run_id)s::text, 'source_id', i.index_condition_display_basis_id, 'direction', d.direction, 'condition_key', ck.condition_key)::text),
                   md5(jsonb_build_object('source_table', 'index_condition_display_basis', 'source_id', i.index_condition_display_basis_id, 'run_id', i.run_id, 'identity_key', i.index_identity_key, 'selected_directions', to_jsonb(i.selected_directions), 'selected_condition_keys', to_jsonb(i.selected_condition_keys))::text),
                   i.index_identity_key, to_jsonb(i.selected_directions), to_jsonb(i.selected_condition_keys),
                   %(mapping_strategy)s, 'index', i.index_identity_key, i.index_identity_key, i.code, i.name,
                   i.display_code, i.display_name, i.display_title, i.display_summary, ck.condition_key,
                   ck.condition_key, d.direction, to_jsonb(i.selected_signal_types), i.period_grade_summary_json,
                   i.period_grade_y, i.period_grade_q, i.period_grade_m, i.period_grade_w, i.period_grade_d,
                   i.target_price_summary_json, jsonb_build_object(), i.condition_summary_json,
                   i.quality_status, i.index_condition_display_basis_id, i.updated_at
            FROM index_condition_display_basis i
            CROSS JOIN LATERAL unnest(i.selected_directions) AS d(direction)
            CROSS JOIN LATERAL unnest(i.selected_condition_keys) AS ck(condition_key)
            WHERE i.run_id = %(source_condition_run_id)s
            """,
            {
                "cache_run_id": cache_run_id,
                "cache_version": cache_version,
                "source_condition_run_id": source_condition_run_id,
                "source_trade_date": source_trade_date,
                "mapping_strategy": mapping_strategy,
            },
        )
        return int(cur.rowcount or 0)

    def _insert_board_display(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
    ) -> int:
        cur.execute(
            """
            INSERT INTO n6_board_display_cache (
              cache_run_id, cache_version, source_condition_run_id, source_trade_date,
              source_table, source_version, row_hash, source_row_hash, source_identity_key,
              source_selected_directions_json, source_selected_condition_keys_json, expansion_strategy,
              asset_kind, identity_key, board_identity_key, board_type, code, name, display_code,
              display_name, display_title, display_summary, condition_key, original_condition_key,
              direction, selected_signal_types_json, period_summary_json, year_overheat_level,
              quarter_overheat_level, month_overheat_level, week_overheat_level, day_overheat_level,
              target_price_context_json, label_json, explanation_json, quality_status,
              source_condition_display_basis_id, source_updated_at
            )
            SELECT %(cache_run_id)s, %(cache_version)s, %(source_condition_run_id)s, %(source_trade_date)s,
                   'board_condition_display_basis', b.source_version,
                   md5(jsonb_build_object('cache_run_id', %(cache_run_id)s::text, 'source_id', b.board_condition_display_basis_id, 'direction', d.direction, 'condition_key', ck.condition_key)::text),
                   md5(jsonb_build_object('source_table', 'board_condition_display_basis', 'source_id', b.board_condition_display_basis_id, 'run_id', b.run_id, 'identity_key', b.board_identity_key, 'selected_directions', to_jsonb(b.selected_directions), 'selected_condition_keys', to_jsonb(b.selected_condition_keys))::text),
                   b.board_identity_key, to_jsonb(b.selected_directions), to_jsonb(b.selected_condition_keys),
                   %(mapping_strategy)s, 'board', b.board_identity_key, b.board_identity_key, b.board_type,
                   b.board_code, b.board_name, b.display_code, b.display_name, b.display_title,
                   b.display_summary, ck.condition_key, ck.condition_key, d.direction,
                   to_jsonb(b.selected_signal_types), b.period_grade_summary_json, b.period_grade_y,
                   b.period_grade_q, b.period_grade_m, b.period_grade_w, b.period_grade_d,
                   b.target_price_summary_json, jsonb_build_object(), b.condition_summary_json,
                   b.quality_status, b.board_condition_display_basis_id, b.updated_at
            FROM board_condition_display_basis b
            CROSS JOIN LATERAL unnest(b.selected_directions) AS d(direction)
            CROSS JOIN LATERAL unnest(b.selected_condition_keys) AS ck(condition_key)
            WHERE b.run_id = %(source_condition_run_id)s
            """,
            {
                "cache_run_id": cache_run_id,
                "cache_version": cache_version,
                "source_condition_run_id": source_condition_run_id,
                "source_trade_date": source_trade_date,
                "mapping_strategy": mapping_strategy,
            },
        )
        return int(cur.rowcount or 0)

    def _insert_membership_cache(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
    ) -> dict[str, int]:
        cur.execute(
            """
            INSERT INTO n6_index_membership_display_cache (
              cache_run_id, cache_version, source_condition_run_id, source_trade_date,
              source_table, source_version, source_batch_id, row_hash, membership_kind,
              parent_identity_key, parent_code, parent_name, index_identity_key, stock_identity_key,
              stock_code, stock_name, display_title, display_summary, label_json, explanation_json,
              quality_status, trade_date
            )
            SELECT %(cache_run_id)s, %(cache_version)s, %(source_condition_run_id)s, %(source_trade_date)s,
                   'index_membership_fact', im.source_version, im.source_batch_id,
                   md5(jsonb_build_object('cache_run_id', %(cache_run_id)s::text, 'index_identity_key', im.index_identity_key, 'stock_identity_key', im.stock_identity_key, 'trade_date', im.trade_date, 'source_version', im.source_version)::text),
                   'index', im.index_identity_key, im.index_code, im.index_name, im.index_identity_key,
                   im.stock_identity_key, im.stock_code, im.stock_name,
                   im.index_name || ' 成分股', im.stock_name, jsonb_build_object(), jsonb_build_object(),
                   'passed', im.trade_date
            FROM index_membership_fact im
            WHERE im.trade_date = %(source_trade_date)s
            """,
            {
                "cache_run_id": cache_run_id,
                "cache_version": cache_version,
                "source_condition_run_id": source_condition_run_id,
                "source_trade_date": source_trade_date,
            },
        )
        index_rows = int(cur.rowcount or 0)
        cur.execute(
            """
            INSERT INTO n6_board_membership_display_cache (
              cache_run_id, cache_version, source_condition_run_id, source_trade_date,
              source_table, source_version, source_batch_id, row_hash, membership_kind,
              parent_identity_key, parent_code, parent_name, board_identity_key, board_type,
              stock_identity_key, stock_code, stock_name, display_title, display_summary,
              label_json, explanation_json, quality_status, trade_date
            )
            SELECT %(cache_run_id)s, %(cache_version)s, %(source_condition_run_id)s, %(source_trade_date)s,
                   'board_membership_fact', bm.source_version, bm.source_batch_id,
                   md5(jsonb_build_object('cache_run_id', %(cache_run_id)s::text, 'board_identity_key', bm.board_identity_key, 'board_type', bm.board_type, 'stock_identity_key', bm.stock_identity_key, 'trade_date', bm.trade_date, 'source_version', bm.source_version)::text),
                   'board', bm.board_identity_key, bm.board_code, bm.board_name, bm.board_identity_key,
                   bm.board_type, bm.stock_identity_key, bm.stock_code, bm.stock_name,
                   bm.board_name || ' 成分股', bm.stock_name, jsonb_build_object(), jsonb_build_object(),
                   'passed', bm.trade_date
            FROM board_membership_fact bm
            WHERE bm.trade_date = %(source_trade_date)s
            """,
            {
                "cache_run_id": cache_run_id,
                "cache_version": cache_version,
                "source_condition_run_id": source_condition_run_id,
                "source_trade_date": source_trade_date,
            },
        )
        board_rows = int(cur.rowcount or 0)
        return {
            "n6_index_membership_display_cache": index_rows,
            "n6_board_membership_display_cache": board_rows,
        }


def validate_contract_artifact(path: str | None, cache_run_id: str) -> list[str]:
    if not path:
        return ["contract_path_missing"]
    try:
        artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["contract_artifact_missing"]
    except json.JSONDecodeError:
        return ["contract_json_invalid"]
    blockers: list[str] = []
    if artifact.get("result") != "CONTRACT_PASS":
        blockers.append("contract_not_passed")
    if artifact.get("cache_run_id") != cache_run_id:
        blockers.append("contract_cache_run_id_mismatch")
    if artifact.get("expected_rows") != EXPECTED_ROWS:
        blockers.append("contract_expected_rows_mismatch")
    if artifact.get("mapping_strategy") != MAPPING_STRATEGY:
        blockers.append("contract_mapping_strategy_mismatch")
    return blockers


def validate_preflight_artifact(path: str | None, cache_run_id: str) -> list[str]:
    if not path:
        return ["preflight_path_missing"]
    try:
        artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["preflight_artifact_missing"]
    except json.JSONDecodeError:
        return ["preflight_json_invalid"]
    blockers: list[str] = []
    if artifact.get("result") != "PREFLIGHT_PASS":
        blockers.append("preflight_not_passed")
    if artifact.get("cache_run_id") != cache_run_id:
        blockers.append("preflight_cache_run_id_mismatch")
    if artifact.get("preview_row_counts") != EXPECTED_ROWS:
        blockers.append("preflight_expected_rows_mismatch")
    summary = artifact.get("validation_summary") or {}
    if any(summary.get(key, 1) != 0 for key in ("duplicate_fanout_key", "duplicate_row_hash", "missing_required", "invalid_board_type", "invalid_direction", "null_identity_key")):
        blockers.append("preflight_validation_summary_not_clean")
    return blockers


def build_preflight(snapshot: LocalDisplayCachePreflightSnapshot) -> dict[str, object]:
    blockers: list[str] = []
    if snapshot.latest_active_n2_run_id != snapshot.source_condition_run_id or snapshot.latest_active_n2_status != "passed_active":
        blockers.append("latest_active_n2_run_mismatch")
    if snapshot.source_counts != EXPECTED_SOURCE_COUNTS:
        blockers.append("source_counts_mismatch")
    if snapshot.preview_row_counts != EXPECTED_ROWS:
        blockers.append("preview_row_counts_mismatch")
    if not all(snapshot.target_table_exists.values()):
        blockers.append("cache_table_missing")
    if any(value != 0 for value in snapshot.target_row_counts.values()):
        blockers.append("target_baseline_nonzero")
    if snapshot.cache_run_id_rows:
        blockers.append("cache_run_id_already_exists")
    if snapshot.scoped_target_rows:
        blockers.append("cache_run_id_scoped_rows_nonzero")
    if snapshot.active_cache_same_source_version_rows:
        blockers.append("active_cache_same_source_version_exists")
    if snapshot.active_cache_same_version_rows:
        blockers.append("active_cache_pointer_switch_requires_dedicated_gate")
    if snapshot.mapping_strategy != MAPPING_STRATEGY:
        blockers.append("mapping_strategy_mismatch")
    if any(
        value != 0
        for value in (
            snapshot.duplicate_fanout_key,
            snapshot.duplicate_row_hash,
            snapshot.missing_required,
            snapshot.invalid_board_type,
            snapshot.invalid_direction,
            snapshot.null_identity_key,
        )
    ):
        blockers.append("preview_validation_failed")
    return {
        "result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "blockers": blockers,
        "snapshot": asdict(snapshot),
    }


def run_local_display_cache_sync(
    *,
    dsn: str | None = None,
    repository: LocalDisplayCacheSyncRepository | None = None,
    cache_run_id: str = CACHE_RUN_ID,
    cache_version: str = CACHE_VERSION,
    source_condition_run_id: str = SOURCE_CONDITION_RUN_ID,
    source_trade_date: str = SOURCE_TRADE_DATE,
    mapping_strategy: str = MAPPING_STRATEGY,
    execute: bool = False,
    user_confirmed: bool = False,
    contract_path: str | None = CONTRACT_PATH,
    preflight_path: str | None = PREFLIGHT_PATH,
    rollback_sql_path: str = ROLLBACK_SQL_PATH,
) -> dict[str, object]:
    if not execute:
        return _blocked_report(cache_run_id, ["missing_execute_flag"])
    if not user_confirmed:
        return _blocked_report(cache_run_id, ["missing_user_confirmed_flag"])
    contract_blockers = validate_contract_artifact(contract_path, cache_run_id)
    preflight_blockers = validate_preflight_artifact(preflight_path, cache_run_id)
    if contract_blockers or preflight_blockers:
        return _blocked_report(cache_run_id, contract_blockers + preflight_blockers)
    repo = repository or PostgresLocalDisplayCacheSyncRepository(dsn or "")
    snapshot = repo.fetch_preflight_snapshot(
        cache_run_id=cache_run_id,
        cache_version=cache_version,
        source_condition_run_id=source_condition_run_id,
        source_trade_date=source_trade_date,
        mapping_strategy=mapping_strategy,
    )
    preflight = build_preflight(snapshot)
    if preflight["blockers"]:
        report = _blocked_report(cache_run_id, list(preflight["blockers"]))
        report["preflight"] = preflight
        return report
    write_result = repo.commit_sync(
        cache_run_id=cache_run_id,
        cache_version=cache_version,
        source_condition_run_id=source_condition_run_id,
        source_trade_date=source_trade_date,
        mapping_strategy=mapping_strategy,
        expected_rows=EXPECTED_ROWS,
    )
    return {
        "result": "EXECUTED",
        "cache_run_id": cache_run_id,
        "cache_version": cache_version,
        "source_condition_run_id": source_condition_run_id,
        "source_trade_date": source_trade_date,
        "mapping_strategy": mapping_strategy,
        "principal": "system-only",
        "preflight_result": "PREFLIGHT_PASS",
        "planned_rows": EXPECTED_ROWS,
        "write_result": write_result,
        "rollback_sql": rollback_sql_path,
        "database_written": True,
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "outbox_consumed_or_updated": False,
        "worker_started": False,
        "proposal_order_trade_position_pnl_real_trade": False,
    }


def _blocked_report(cache_run_id: str, blockers: list[str]) -> dict[str, object]:
    return {
        "result": "BLOCKED",
        "cache_run_id": cache_run_id,
        "blockers": blockers,
        "database_written": False,
        "outbox_consumed_or_updated": False,
        "worker_started": False,
        "proposal_order_trade_position_pnl_real_trade": False,
    }


def format_summary(report: Mapping[str, object]) -> str:
    lines = [
        f"result={report.get('result')}",
        f"cache_run_id={report.get('cache_run_id')}",
        f"database_written={report.get('database_written')}",
        f"outbox_consumed_or_updated={report.get('outbox_consumed_or_updated')}",
        f"worker_started={report.get('worker_started')}",
    ]
    if report.get("blockers"):
        lines.append(f"blockers={','.join(str(item) for item in report['blockers'])}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run N6 local display cache sync once after final gate.")
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--cache-run-id", default=CACHE_RUN_ID)
    parser.add_argument("--cache-version", default=CACHE_VERSION)
    parser.add_argument("--source-condition-run-id", default=SOURCE_CONDITION_RUN_ID)
    parser.add_argument("--source-trade-date", default=SOURCE_TRADE_DATE)
    parser.add_argument("--mapping-strategy", default=MAPPING_STRATEGY)
    parser.add_argument("--contract-path", default=CONTRACT_PATH)
    parser.add_argument("--preflight-path", default=PREFLIGHT_PATH)
    parser.add_argument("--rollback-sql-path", default=ROLLBACK_SQL_PATH)
    parser.add_argument("--json-report-path", default=None)
    parser.add_argument("--markdown-report-path", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser
