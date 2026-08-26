"""One-time, interactive setup for the existing native Windows PostgreSQL service."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import subprocess
from typing import Any, Callable

from .windows_n1_postgres import (
    FORBIDDEN_WRITE_TABLES, N1_WRITABLE_TABLES, WindowsN1PostgresRepository,
)


HOST = "127.0.0.1"
PORT = 5432
DATABASE = "ashare_v3"
APP_ROLE = "ashare_v3_user"
ADMIN_DATABASE = "postgres"
PASSWORDLESS_APP_DSN = (
    "host=127.0.0.1 port=5432 dbname=ashare_v3 user=ashare_v3_user"
)


@dataclass(frozen=True)
class SetupResult:
    database: str
    role: str
    pgpass_path: Path
    business_row_counts: dict[str, int]


def assert_fresh_authority(admin_connection: Any) -> None:
    """Stop unless both database and role are absent; never repair partial state."""
    with admin_connection.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname=%s)", (DATABASE,))
        database_exists = bool(cur.fetchone()[0])
        cur.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=%s)", (APP_ROLE,))
        role_exists = bool(cur.fetchone()[0])
    if database_exists or role_exists:
        raise RuntimeError(
            "fresh authority required; refusing existing or partial state: "
            f"database_exists={database_exists}, role_exists={role_exists}"
        )


def pgpass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def merge_pgpass(existing: str, *, password: str) -> str:
    key = f"{HOST}:{PORT}:{DATABASE}:{APP_ROLE}:"
    retained = [line for line in existing.splitlines() if not line.startswith(key)]
    retained.append(key + pgpass_escape(password))
    return "\n".join(retained) + "\n"


def write_user_pgpass(
    *, password: str, environ: dict[str, str] | None = None,
    run_command: Callable[..., Any] = subprocess.run,
) -> Path:
    environment = os.environ if environ is None else environ
    if environment.get("USERNAME", "").lower() != "ashare-ops":
        raise RuntimeError("Windows setup must run as ashare-ops")
    appdata = environment.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is unavailable")
    path = Path(appdata) / "postgresql" / "pgpass.conf"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    temporary = path.with_name("pgpass.conf.windows_n1_tmp")
    temporary.write_text(merge_pgpass(existing, password=password), encoding="utf-8")
    try:
        run_command(
            ["icacls.exe", str(temporary), "/inheritance:r", "/grant:r", "ashare-ops:(R,W)", "SYSTEM:(F)"],
            check=True, capture_output=True, text=True,
        )
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def grant_minimum_n1_privileges(admin_connection: Any) -> None:
    from psycopg import sql
    writable = sorted(N1_WRITABLE_TABLES - {"common_ingest_batch", "common_quality_gate_result", "common_active_source_version"})
    # Metadata tables are also required by the runner, but the calendar is read-only.
    writable.extend(["common_ingest_batch", "common_quality_gate_result", "common_active_source_version"])
    all_tables = sorted(set(writable) | FORBIDDEN_WRITE_TABLES)
    with admin_connection.transaction():
        with admin_connection.cursor() as cur:
            cur.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(sql.Identifier(DATABASE), sql.Identifier(APP_ROLE)))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DATABASE), sql.Identifier(APP_ROLE)))
            cur.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
            cur.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(sql.Identifier(APP_ROLE)))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))
            cur.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(
                sql.SQL(",").join(sql.Identifier(name) for name in all_tables), sql.Identifier(APP_ROLE)
            ))
            cur.execute(sql.SQL("GRANT INSERT,UPDATE ON {} TO {}").format(
                sql.SQL(",").join(sql.Identifier(name) for name in writable), sql.Identifier(APP_ROLE)
            ))
            cur.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))
            cur.execute(sql.SQL("REVOKE DELETE,TRUNCATE,REFERENCES,TRIGGER ON ALL TABLES IN SCHEMA public FROM {}").format(sql.Identifier(APP_ROLE)))


def verify_app_authority(app_connection: Any) -> None:
    """Prove the application role has N1 DML only and cannot govern schema/data."""
    writable = N1_WRITABLE_TABLES
    all_tables = sorted(writable | FORBIDDEN_WRITE_TABLES)
    with app_connection.cursor() as cur:
        cur.execute(
            "SELECT current_database(),current_user,"
            "has_database_privilege(current_user,current_database(),'CONNECT'),"
            "has_database_privilege(current_user,current_database(),'CREATE'),"
            "has_schema_privilege(current_user,'public','USAGE'),"
            "has_schema_privilege(current_user,'public','CREATE')"
        )
        database, role, can_connect, can_create_database_objects, can_use_schema, can_create_schema_objects = cur.fetchone()
        if (database, role) != (DATABASE, APP_ROLE):
            raise RuntimeError("app authority identity mismatch")
        if not can_connect or not can_use_schema or can_create_database_objects or can_create_schema_objects:
            raise RuntimeError("app database/schema privileges exceed N1 authority")
        cur.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=current_user"
        )
        if any(map(bool, cur.fetchone())):
            raise RuntimeError("app role attributes exceed N1 authority")
        for table in all_tables:
            cur.execute(
                "SELECT has_table_privilege(current_user,%s,'SELECT'),"
                "has_table_privilege(current_user,%s,'INSERT'),"
                "has_table_privilege(current_user,%s,'UPDATE'),"
                "has_table_privilege(current_user,%s,'DELETE'),"
                "has_table_privilege(current_user,%s,'TRUNCATE'),"
                "has_table_privilege(current_user,%s,'REFERENCES'),"
                "has_table_privilege(current_user,%s,'TRIGGER')",
                (table, table, table, table, table, table, table),
            )
            select, insert, update, delete, truncate, references, trigger = map(bool, cur.fetchone())
            expected_write = table in writable
            if not select or insert != expected_write or update != expected_write:
                raise RuntimeError(f"app N1 table privilege mismatch: {table}")
            if delete or truncate or references or trigger:
                raise RuntimeError(f"forbidden app table privilege detected: {table}")


def setup_database(*, admin_password: str, schema_path: Path) -> SetupResult:
    """Create only the authorized empty N1 database/role on the existing service."""
    import psycopg
    from psycopg import sql
    app_password = secrets.token_urlsafe(48)
    admin_kwargs = {
        "host": HOST, "port": PORT, "dbname": ADMIN_DATABASE,
        "user": "postgres", "password": admin_password, "connect_timeout": 8,
    }
    with psycopg.connect(**admin_kwargs, autocommit=True) as admin:
        assert_fresh_authority(admin)
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(APP_ROLE), sql.Literal(app_password)))
            cur.execute(sql.SQL("CREATE DATABASE {} OWNER postgres").format(sql.Identifier(DATABASE)))
    database_kwargs = {**admin_kwargs, "dbname": DATABASE}
    with psycopg.connect(**database_kwargs) as database_connection:
        repository = WindowsN1PostgresRepository(database_connection)
        repository.apply_schema(schema_path)
        counts = repository.business_row_counts()
        if any(counts.values()):
            raise RuntimeError("new N1 schema is not empty")
        grant_minimum_n1_privileges(database_connection)
    pgpass_path = write_user_pgpass(password=app_password)
    # Password is intentionally omitted: this proves standard libpq pgpass discovery.
    with psycopg.connect(PASSWORDLESS_APP_DSN, connect_timeout=8) as app_connection:
        repository = WindowsN1PostgresRepository(app_connection)
        repository.verify_authority()
        verify_app_authority(app_connection)
        if any(repository.business_row_counts().values()):
            raise RuntimeError("app-role empty-database verification failed")
    return SetupResult(DATABASE, APP_ROLE, pgpass_path, counts)
