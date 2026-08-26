"""One-time, interactive setup for the existing native Windows PostgreSQL service."""

from __future__ import annotations

from dataclasses import dataclass
import json
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
OPERATOR_DIRECT = "ashare-ops"
OPERATOR_ELEVATED = "elevated-47894"
OPERATOR_MODES = (OPERATOR_DIRECT, OPERATOR_ELEVATED)
OPERATOR_NAME = r"TDX-STOCK\47894"
RUNTIME_NAME = r"TDX-STOCK\ashare-ops"
OPERATOR_RID = "1002"
RUNTIME_RID = "1006"
ELEVATED_RUNTIME_PGPASS = Path(
    r"C:\Users\ashare-ops.tdx-stock\AppData\Roaming\postgresql\pgpass.conf"
)


@dataclass(frozen=True)
class WindowsIdentityEvidence:
    name: str
    sid: str
    is_administrator: bool
    runtime_sid: str


@dataclass(frozen=True)
class SetupResult:
    database: str
    role: str
    pgpass_path: Path
    business_row_counts: dict[str, int]


@dataclass(frozen=True)
class RecoveryAuthorityEvidence:
    database_exists: bool
    database_owner: str | None
    database_size: int | None
    role_exists: bool
    role_login: bool
    role_superuser: bool
    role_createdb: bool
    role_createrole: bool
    role_replication: bool
    public_tables: tuple[str, ...]
    table_counts: dict[str, int]


@dataclass(frozen=True)
class RecoveryResult:
    database: str
    role: str
    pgpass_path: Path
    database_size: int
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


def read_windows_identity(
    run_command: Callable[..., Any] = subprocess.run,
) -> WindowsIdentityEvidence:
    script = (
        "$identity=[Security.Principal.WindowsIdentity]::GetCurrent();"
        "$principal=[Security.Principal.WindowsPrincipal]::new($identity);"
        "$runtime=[Security.Principal.NTAccount]::new('TDX-STOCK\\ashare-ops').Translate([Security.Principal.SecurityIdentifier]);"
        "[pscustomobject]@{name=$identity.Name;sid=$identity.User.Value;"
        "is_administrator=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);"
        "runtime_sid=$runtime.Value}|ConvertTo-Json -Compress"
    )
    completed = run_command(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, capture_output=True, text=True,
    )
    payload = json.loads(completed.stdout)
    return WindowsIdentityEvidence(
        name=str(payload["name"]), sid=str(payload["sid"]),
        is_administrator=bool(payload["is_administrator"]),
        runtime_sid=str(payload["runtime_sid"]),
    )


def validate_operator_identity(mode: str, identity: WindowsIdentityEvidence) -> None:
    if mode not in OPERATOR_MODES:
        raise RuntimeError(f"unsupported operator mode: {mode}")
    operator_prefix, separator, operator_rid = identity.sid.rpartition("-")
    runtime_prefix, runtime_separator, runtime_rid = identity.runtime_sid.rpartition("-")
    if not separator or not runtime_separator or operator_prefix != runtime_prefix:
        raise RuntimeError("Windows operator/runtime SID authority mismatch")
    if identity.runtime_sid != f"{operator_prefix}-{RUNTIME_RID}":
        raise RuntimeError("runtime ashare-ops SID mismatch")
    if mode == OPERATOR_DIRECT:
        if identity.name.lower() != RUNTIME_NAME.lower() or operator_rid != RUNTIME_RID:
            raise RuntimeError("direct setup requires exact TDX-STOCK\\ashare-ops identity")
    elif (
        identity.name.lower() != OPERATOR_NAME.lower()
        or operator_rid != OPERATOR_RID
        or not identity.is_administrator
    ):
        raise RuntimeError("elevated setup requires exact administrator TDX-STOCK\\47894 identity")


def pgpass_path_for_mode(
    mode: str, *, environment: dict[str, str], identity: WindowsIdentityEvidence,
) -> Path:
    validate_operator_identity(mode, identity)
    if mode == OPERATOR_ELEVATED:
        return ELEVATED_RUNTIME_PGPASS
    appdata = environment.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is unavailable")
    return Path(appdata) / "postgresql" / "pgpass.conf"


def verify_pgpass_acl(
    path: Path, *, runtime_sid: str,
    run_command: Callable[..., Any] = subprocess.run,
) -> None:
    script = (
        "$acl=Get-Acl -LiteralPath $args[0];"
        "$rules=@($acl.Access|ForEach-Object{[pscustomobject]@{"
        "sid=$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value;"
        "deny=($_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Deny);"
        "rights=[int]$_.FileSystemRights}});"
        "[pscustomobject]@{owner=$acl.Owner.Translate([Security.Principal.SecurityIdentifier]).Value;"
        "protected=$acl.AreAccessRulesProtected;rules=$rules}|ConvertTo-Json -Compress -Depth 4"
    )
    completed = run_command(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script, str(path)],
        check=True, capture_output=True, text=True,
    )
    payload = json.loads(completed.stdout)
    rules = payload.get("rules") or []
    if isinstance(rules, dict):
        rules = [rules]
    rule_sids = {str(rule["sid"]) for rule in rules if not bool(rule["deny"])}
    if payload.get("owner") != runtime_sid or not payload.get("protected"):
        raise RuntimeError("pgpass owner/inheritance ACL mismatch")
    if rule_sids != {runtime_sid, "S-1-5-18"} or any(bool(rule["deny"]) for rule in rules):
        raise RuntimeError("pgpass ACL contains non-runtime principal")
    rights_by_sid = {
        sid: 0 for sid in rule_sids
    }
    for rule in rules:
        if not bool(rule["deny"]):
            rights_by_sid[str(rule["sid"])] |= int(rule["rights"])
    if rights_by_sid[runtime_sid] & 0x3 != 0x3 or rights_by_sid["S-1-5-18"] != 2032127:
        raise RuntimeError("pgpass ACL rights are insufficient")


def write_user_pgpass(
    *, password: str, operator_mode: str = OPERATOR_DIRECT,
    identity: WindowsIdentityEvidence | None = None,
    environ: dict[str, str] | None = None,
    run_command: Callable[..., Any] = subprocess.run,
    acl_verifier: Callable[..., None] = verify_pgpass_acl,
) -> Path:
    environment = os.environ if environ is None else environ
    evidence = identity or read_windows_identity(run_command)
    path = pgpass_path_for_mode(operator_mode, environment=environment, identity=evidence)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    temporary = path.with_name(f"pgpass.conf.windows_n1_{secrets.token_hex(8)}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        handle.write(merge_pgpass(existing, password=password))
    try:
        run_command(
            ["icacls.exe", str(temporary), "/inheritance:r"],
            check=True, capture_output=True, text=True,
        )
        run_command(
            ["icacls.exe", str(temporary), "/grant:r", f"*{evidence.runtime_sid}:(R,W)", "*S-1-5-18:(F)"],
            check=True, capture_output=True, text=True,
        )
        run_command(
            ["icacls.exe", str(temporary), "/setowner", f"*{evidence.runtime_sid}"],
            check=True, capture_output=True, text=True,
        )
        acl_verifier(temporary, runtime_sid=evidence.runtime_sid, run_command=run_command)
        os.replace(temporary, path)
        acl_verifier(path, runtime_sid=evidence.runtime_sid, run_command=run_command)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def validate_recovery_authority(evidence: RecoveryAuthorityEvidence) -> None:
    expected_tables = N1_WRITABLE_TABLES | FORBIDDEN_WRITE_TABLES
    if not evidence.database_exists or evidence.database_owner != "postgres":
        raise RuntimeError("recovery requires existing postgres-owned ashare_v3")
    if evidence.database_size is None or evidence.database_size <= 0:
        raise RuntimeError("recovery database size evidence is invalid")
    if not evidence.role_exists or not evidence.role_login:
        raise RuntimeError("recovery requires existing LOGIN ashare_v3_user")
    if any((evidence.role_superuser, evidence.role_createdb, evidence.role_createrole, evidence.role_replication)):
        raise RuntimeError("recovery app role attributes exceed authority")
    if set(evidence.public_tables) != expected_tables or len(evidence.public_tables) != len(expected_tables):
        raise RuntimeError("recovery requires exact 14-table N1 canonical schema")
    if set(evidence.table_counts) != expected_tables:
        raise RuntimeError("recovery table count evidence is incomplete")
    nonempty = {table: count for table, count in evidence.table_counts.items() if count != 0}
    if nonempty:
        raise RuntimeError(f"recovery requires exact empty N1 database: {sorted(nonempty)}")
    if evidence.table_counts.get("common_trade_calendar") != 0:
        raise RuntimeError("recovery requires empty common_trade_calendar")


def inspect_recovery_authority(admin_connection: Any, database_connection: Any) -> RecoveryAuthorityEvidence:
    from psycopg import sql
    with admin_connection.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s),"
            "(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s),"
            "(SELECT pg_database_size(datname) FROM pg_database WHERE datname=%s)",
            (DATABASE, DATABASE, DATABASE),
        )
        database_exists, owner, database_size = cur.fetchone()
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s),"
            "COALESCE((SELECT rolcanlogin FROM pg_roles WHERE rolname=%s),false),"
            "COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname=%s),false),"
            "COALESCE((SELECT rolcreatedb FROM pg_roles WHERE rolname=%s),false),"
            "COALESCE((SELECT rolcreaterole FROM pg_roles WHERE rolname=%s),false),"
            "COALESCE((SELECT rolreplication FROM pg_roles WHERE rolname=%s),false)",
            (APP_ROLE,) * 6,
        )
        role_exists, login, superuser, createdb, createrole, replication = cur.fetchone()
    with database_connection.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        tables = tuple(row[0] for row in cur.fetchall())
        counts = {}
        for table in tables:
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
            counts[table] = int(cur.fetchone()[0])
    evidence = RecoveryAuthorityEvidence(
        bool(database_exists), str(owner) if owner is not None else None,
        int(database_size) if database_size is not None else None,
        bool(role_exists), bool(login), bool(superuser), bool(createdb),
        bool(createrole), bool(replication), tables, counts,
    )
    validate_recovery_authority(evidence)
    return evidence


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
            cur.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(sql.Identifier(APP_ROLE)))
            cur.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(
                sql.SQL(",").join(sql.Identifier(name) for name in all_tables), sql.Identifier(APP_ROLE)
            ))
            cur.execute(sql.SQL("GRANT INSERT,UPDATE ON {} TO {}").format(
                sql.SQL(",").join(sql.Identifier(name) for name in writable), sql.Identifier(APP_ROLE)
            ))
            cur.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}").format(sql.Identifier(APP_ROLE)))
            cur.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))


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


def setup_database(
    *, admin_password: str, schema_path: Path,
    operator_mode: str = OPERATOR_DIRECT,
    operator_identity: WindowsIdentityEvidence | None = None,
) -> SetupResult:
    """Create only the authorized empty N1 database/role on the existing service."""
    import psycopg
    from psycopg import sql
    identity = operator_identity or read_windows_identity()
    validate_operator_identity(operator_mode, identity)
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
    pgpass_path = write_user_pgpass(
        password=app_password, operator_mode=operator_mode, identity=identity,
    )
    app_connect = (
        {"host": HOST, "port": PORT, "dbname": DATABASE, "user": APP_ROLE,
         "password": app_password, "connect_timeout": 8}
        if operator_mode == OPERATOR_ELEVATED
        else {"conninfo": PASSWORDLESS_APP_DSN, "connect_timeout": 8}
    )
    # Elevated mode verifies with the generated password only in memory; it never
    # writes the administrator's own pgpass. Direct mode proves libpq discovery.
    with psycopg.connect(**app_connect) as app_connection:
        repository = WindowsN1PostgresRepository(app_connection)
        repository.verify_authority()
        verify_app_authority(app_connection)
        if any(repository.business_row_counts().values()):
            raise RuntimeError("app-role empty-database verification failed")
    return SetupResult(DATABASE, APP_ROLE, pgpass_path, counts)


def recover_empty_setup(
    *, admin_password: str,
    operator_identity: WindowsIdentityEvidence | None = None,
) -> RecoveryResult:
    """Recover credentials only for the exact, already-created empty N1 authority."""
    import psycopg
    from psycopg import sql
    identity = operator_identity or read_windows_identity()
    validate_operator_identity(OPERATOR_ELEVATED, identity)
    app_password = secrets.token_urlsafe(48)
    admin_kwargs = {
        "host": HOST, "port": PORT, "dbname": ADMIN_DATABASE,
        "user": "postgres", "password": admin_password, "connect_timeout": 8,
    }
    database_kwargs = {**admin_kwargs, "dbname": DATABASE}
    with psycopg.connect(**admin_kwargs, autocommit=True) as admin_connection:
        with psycopg.connect(**database_kwargs) as database_connection:
            evidence = inspect_recovery_authority(admin_connection, database_connection)
            grant_minimum_n1_privileges(database_connection)
        with admin_connection.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(APP_ROLE), sql.Literal(app_password)
                )
            )
    pgpass_path = write_user_pgpass(
        password=app_password, operator_mode=OPERATOR_ELEVATED, identity=identity,
    )
    with psycopg.connect(
        host=HOST, port=PORT, dbname=DATABASE, user=APP_ROLE,
        password=app_password, connect_timeout=8,
    ) as app_connection:
        repository = WindowsN1PostgresRepository(app_connection)
        repository.verify_authority()
        verify_app_authority(app_connection)
        counts = repository.business_row_counts()
        if set(counts) != N1_WRITABLE_TABLES | FORBIDDEN_WRITE_TABLES or any(counts.values()):
            raise RuntimeError("recovery app verification requires exact empty N1 authority")
    return RecoveryResult(
        DATABASE, APP_ROLE, pgpass_path, int(evidence.database_size), counts,
    )
