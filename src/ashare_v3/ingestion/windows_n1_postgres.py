"""PostgreSQL persistence boundary for the Windows N1 bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


N1_WRITABLE_TABLES = frozenset({
    "common_ingest_batch", "common_quality_gate_result", "common_active_source_version",
    "stock_identity", "index_identity", "board_identity",
    "stock_daily_bar_fact", "index_daily_bar_fact", "board_daily_bar_fact",
    "index_membership_fact", "board_membership_fact",
    "stock_financial_metrics_fact", "stock_daily_basic",
})
FORBIDDEN_WRITE_TABLES = frozenset({"common_trade_calendar"})
REQUIRED_READY_DATA_TYPES = frozenset({
    "stock_identity", "index_identity", "board_identity",
    "index_membership_fact", "board_membership_fact",
    "stock_daily_bar_fact", "index_daily_bar_fact", "board_daily_bar_fact",
    "stock_financial_metrics_fact", "stock_daily_basic",
})


def stable_rows_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def jsonb_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def validate_write_target(table: str) -> None:
    if table in FORBIDDEN_WRITE_TABLES or table not in N1_WRITABLE_TABLES:
        raise RuntimeError(f"Windows N1 write target rejected: {table}")


def validate_schema_sql(sql_text: str) -> None:
    """Accept the frozen N1 schema only when it defines no downstream tables."""
    import re
    created = {
        match.group(1).lower()
        for match in re.finditer(r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?([a-z_][a-z0-9_]*)", sql_text, re.I)
    }
    allowed = N1_WRITABLE_TABLES | FORBIDDEN_WRITE_TABLES
    unexpected = created - allowed
    missing = allowed - created
    if unexpected or missing:
        raise RuntimeError(
            f"schema table allowlist mismatch: unexpected={sorted(unexpected)}, missing={sorted(missing)}"
        )


@dataclass
class WindowsN1PostgresRepository:
    connection: Any

    def verify_authority(self) -> None:
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute("SELECT current_database(), current_user")
                database, _user = cur.fetchone()
        if database != "ashare_v3":
            raise RuntimeError(f"database authority mismatch: {database}")

    def apply_schema(self, schema_path: Path) -> None:
        sql_text = schema_path.read_text(encoding="utf-8")
        validate_schema_sql(sql_text)
        self.verify_authority()
        with self.connection.cursor() as cur:
            cur.execute(sql_text)
        self.connection.commit()

    def _passed_batch_is_identical(
        self, cur: Any, *, batch_id: str, raw_hash: str, row_count: int,
    ) -> bool:
        cur.execute(
            "SELECT status,raw_hash,row_count FROM common_ingest_batch WHERE batch_id=%s",
            (batch_id,),
        )
        existing = cur.fetchone()
        if existing is None:
            return False
        if tuple(existing) == ("passed", raw_hash, row_count):
            return True
        raise RuntimeError(f"batch identity collision or incomplete prior batch: {batch_id}")

    def business_row_counts(self) -> dict[str, int]:
        counts = {}
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                for table in sorted(N1_WRITABLE_TABLES | FORBIDDEN_WRITE_TABLES):
                    cur.execute("SELECT to_regclass(%s)", (table,))
                    if cur.fetchone()[0] is None:
                        counts[table] = 0
                        continue
                    cur.execute(f'SELECT count(*) FROM "{table}"')
                    counts[table] = int(cur.fetchone()[0])
        return counts

    def downstream_row_counts(self) -> dict[str, int]:
        counts = {}
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    "SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"
                )
                for schema, table in cur.fetchall():
                    if schema == "public" and table in N1_WRITABLE_TABLES | FORBIDDEN_WRITE_TABLES:
                        continue
                    cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
                    counts[f"{schema}.{table}"] = int(cur.fetchone()[0])
        return counts

    def persist_batch(
        self, *, table: str, rows: Sequence[Mapping[str, Any]], conflict_columns: Sequence[str],
        batch_id: str, trade_date: str, data_domain: str, data_type: str,
        source_version: str, activation_scope_key: str | None = None,
    ) -> None:
        validate_write_target(table)
        if not rows:
            raise RuntimeError(f"empty batch rejected: {batch_id}")
        columns = tuple(rows[0])
        if any(tuple(row) != columns for row in rows):
            raise RuntimeError("row column order mismatch")
        from psycopg import sql
        from psycopg.types.json import Jsonb
        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(sql.Placeholder() for _ in columns),
            sql.SQL(",").join(map(sql.Identifier, conflict_columns)),
            sql.SQL(",").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
                for column in columns if column not in conflict_columns
            ),
        )
        values = []
        for row in rows:
            values.append(tuple(
                Jsonb(value, dumps=jsonb_dumps) if column == "raw_payload" else value
                for column, value in row.items()
            ))
        raw_hash = stable_rows_hash(rows)
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                if self._passed_batch_is_identical(
                    cur, batch_id=batch_id, raw_hash=raw_hash, row_count=len(rows)
                ):
                    return
                cur.execute(
                    "INSERT INTO common_ingest_batch (batch_id,trade_date,data_domain,data_type,source,source_version,raw_hash,row_count,status,started_at) VALUES (%s,%s,%s,%s,'TQ_ELTDX_WINDOWS',%s,%s,%s,'running',now())",
                    (batch_id, trade_date, data_domain, data_type, source_version, raw_hash, len(rows)),
                )
                cur.executemany(statement, values)
                cur.execute(
                    "INSERT INTO common_quality_gate_result (source_batch_id,source_version,data_domain,data_type,gate_name,severity,status,expected_value,actual_value,details) VALUES (%s,%s,%s,%s,'non_empty_identity_scoped_batch','P0','passed','>0',%s,%s)",
                    (batch_id, source_version, data_domain, data_type, str(len(rows)), Jsonb({"table": table})),
                )
                cur.execute("UPDATE common_ingest_batch SET status='passed',finished_at=now(),quality_gate_summary=%s WHERE batch_id=%s", (Jsonb({"P0": 0, "row_count": len(rows)}), batch_id))
                if activation_scope_key is not None:
                    cur.execute(
                        "INSERT INTO common_active_source_version (data_domain,data_type,scope_key,source_version,source_batch_id,activated_by) VALUES (%s,%s,%s,%s,%s,'windows_n1_bootstrap') ON CONFLICT (data_domain,data_type,scope_key) DO UPDATE SET previous_source_version=common_active_source_version.source_version,source_version=EXCLUDED.source_version,source_batch_id=EXCLUDED.source_batch_id,activated_at=now(),activated_by=EXCLUDED.activated_by",
                        (data_domain, data_type, activation_scope_key, source_version, batch_id),
                    )

    def activate_source(
        self, *, data_domain: str, data_type: str, scope_key: str,
        source_version: str, batch_id: str, row_count: int,
    ) -> None:
        validate_write_target("common_active_source_version")
        raw_hash = hashlib.sha256(batch_id.encode()).hexdigest()
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                if self._passed_batch_is_identical(
                    cur, batch_id=batch_id, raw_hash=raw_hash, row_count=row_count
                ):
                    return
                cur.execute(
                    "INSERT INTO common_ingest_batch (batch_id,trade_date,data_domain,data_type,source,source_version,raw_hash,row_count,status,started_at,finished_at,quality_gate_summary) VALUES (%s,%s,%s,%s,'TQ_ELTDX_WINDOWS',%s,%s,%s,'passed',now(),now(),%s)",
                    (batch_id, scope_key, data_domain, data_type, source_version, raw_hash, row_count, json.dumps({"P0": 0, "activation": True})),
                )
                cur.execute(
                    "INSERT INTO common_active_source_version (data_domain,data_type,scope_key,source_version,source_batch_id,activated_by) VALUES (%s,%s,%s,%s,%s,'windows_n1_bootstrap') ON CONFLICT (data_domain,data_type,scope_key) DO UPDATE SET previous_source_version=common_active_source_version.source_version,source_version=EXCLUDED.source_version,source_batch_id=EXCLUDED.source_batch_id,activated_at=now(),activated_by=EXCLUDED.activated_by",
                    (data_domain, data_type, scope_key, source_version, batch_id),
                )

    def assert_n1_data_ready(self, scope_key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute("SELECT data_type FROM common_active_source_version WHERE scope_key=%s", (scope_key,))
                active = {row[0] for row in cur.fetchall()}
                missing = REQUIRED_READY_DATA_TYPES - active
                if missing:
                    raise RuntimeError(f"missing active N1 sources: {sorted(missing)}")
                for table in sorted(REQUIRED_READY_DATA_TYPES):
                    validate_write_target(table)
                    cur.execute(f'SELECT count(*) FROM "{table}"')
                    counts[table] = int(cur.fetchone()[0])
                    if counts[table] == 0:
                        raise RuntimeError(f"empty N1 fact: {table}")
                cur.execute("SELECT count(*) FROM common_trade_calendar")
                if int(cur.fetchone()[0]) != 0:
                    raise RuntimeError("common_trade_calendar must remain empty in Windows N1")
        return counts
