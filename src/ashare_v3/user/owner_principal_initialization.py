"""N6 Phase 2 owner/principal initialization runner.

The runner is intentionally narrow and double-gated. It can only seed the two
Track B owner roots approved by the Phase 2 contract: admin principal and system
principal. It never creates accounts, AI users, watchlists, strategies,
sessions, projection rows, delivery rows, sim rows, positions, or real trades.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


SEED_RUN_ID = "n6_phase2_owner_principal_initialization_20260605_v1"
POLICY_VERSION = "n6_phase2_owner_principal_seed_policy_v1"
POLICY_HASH = "8334cb658002542819d0c970138b0bb3b8f5d8dadb414777408fcbd6aac6a8c4"
CONTRACT_PATH = "docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json"
ROLLBACK_SQL_PATH = "sql/N6_phase2_owner_principal_seed_rollback.sql"
SOURCE_ARTIFACT = "docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT.md"
CREATED_BY_GATE = "N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT_GATE"
TRACK_B_TABLES = (
    "n6_principal",
    "n6_ai_user",
    "n6_principal_account",
    "n6_watchlist_ownership",
    "n6_strategy",
)
READONLY_VIEWS = (
    "v_n6_stock_condition_display_basis",
    "v_n6_index_condition_display_basis",
    "v_n6_board_condition_display_basis",
    "v_n6_index_membership_fact",
    "v_n6_board_membership_fact",
)
PLANNED_ROWS = {
    "n6_principal": 2,
    "n6_principal_account": 0,
    "n6_ai_user": 0,
    "n6_watchlist_ownership": 0,
    "n6_strategy": 0,
}


@dataclass
class AdminUserSummary:
    user_id: int
    login_name: str
    role: str
    status: str


@dataclass
class OwnerPrincipalPreflightSnapshot:
    table_exists: dict[str, bool]
    view_exists: dict[str, bool]
    table_counts: dict[str, int | None]
    seed_scoped_counts: dict[str, int]
    admin_users: list[AdminUserSummary]
    readonly_role_exists: bool
    readonly_role_view_grants: list[dict[str, str]]
    readonly_role_base_table_grants: list[dict[str, str]]
    view_trigger_count: int
    duplicate_admin_principal_count: int
    duplicate_system_principal_count: int
    active_ai_without_profile_count: int
    outbox_ref_count: int
    side_effect_ref_count: int


class OwnerPrincipalInitializationRepository(Protocol):
    def fetch_preflight_snapshot(self, seed_run_id: str) -> OwnerPrincipalPreflightSnapshot:
        ...

    def insert_seed_principals(self, *, seed_run_id: str, admin_user_id: int) -> dict[str, object]:
        ...


class PostgresOwnerPrincipalInitializationRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def fetch_preflight_snapshot(self, seed_run_id: str) -> OwnerPrincipalPreflightSnapshot:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            return self._fetch_snapshot(cur, seed_run_id)

    def insert_seed_principals(self, *, seed_run_id: str, admin_user_id: int) -> dict[str, object]:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                snapshot = self._fetch_snapshot(cur, seed_run_id)
                preflight = build_preflight(snapshot, seed_run_id=seed_run_id)
                if preflight["blockers"]:
                    raise RuntimeError("owner/principal seed blocked by refreshed preflight")

                admin_row = self._insert_principal(
                    cur,
                    principal_type="admin",
                    owner_user_id=admin_user_id,
                    principal_status="active",
                    principal_label="Initial Admin Principal",
                    seed_key="phase2_admin_principal__user_account_admin",
                    seed_run_id=seed_run_id,
                )
                system_row = self._insert_principal(
                    cur,
                    principal_type="system",
                    owner_user_id=None,
                    principal_status="system_reserved",
                    principal_label="N6 System Principal",
                    seed_key="phase2_system_principal__n6_system",
                    seed_run_id=seed_run_id,
                )

        return {
            "n6_principal_rows_inserted": 2,
            "n6_ai_user_rows_inserted": 0,
            "n6_principal_account_rows_inserted": 0,
            "n6_watchlist_ownership_rows_inserted": 0,
            "n6_strategy_rows_inserted": 0,
            "inserted_principals": [admin_row, system_row],
        }

    def _fetch_snapshot(self, cur: psycopg.Cursor[dict[str, Any]], seed_run_id: str) -> OwnerPrincipalPreflightSnapshot:
        table_exists = {table: self._object_exists(cur, table) for table in TRACK_B_TABLES}
        view_exists = {view: self._object_exists(cur, view) for view in READONLY_VIEWS}
        table_counts = {table: self._count_table(cur, table) if table_exists[table] else None for table in TRACK_B_TABLES}
        admin_users = self._fetch_admin_users(cur)
        admin_user_id = admin_users[0].user_id if len(admin_users) == 1 else None
        return OwnerPrincipalPreflightSnapshot(
            table_exists=table_exists,
            view_exists=view_exists,
            table_counts=table_counts,
            seed_scoped_counts=self._fetch_seed_scoped_counts(cur, seed_run_id),
            admin_users=admin_users,
            readonly_role_exists=self._role_exists(cur, "n6_ui_readonly_role"),
            readonly_role_view_grants=self._fetch_role_grants(cur, READONLY_VIEWS),
            readonly_role_base_table_grants=self._fetch_role_grants(cur, TRACK_B_TABLES),
            view_trigger_count=self._count_view_triggers(cur),
            duplicate_admin_principal_count=self._count_admin_principal(cur, admin_user_id),
            duplicate_system_principal_count=self._count_system_principal(cur),
            active_ai_without_profile_count=self._count_active_ai_without_profile(cur),
            outbox_ref_count=0,
            side_effect_ref_count=0,
        )

    def _object_exists(self, cur: psycopg.Cursor[dict[str, Any]], object_name: str) -> bool:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{object_name}",))
        return bool(cur.fetchone()["exists"])

    def _count_table(self, cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> int:
        cur.execute(f"SELECT count(*)::int AS count FROM {table_name}")
        return int(cur.fetchone()["count"])

    def _fetch_seed_scoped_counts(self, cur: psycopg.Cursor[dict[str, Any]], seed_run_id: str) -> dict[str, int]:
        specs = {
            "n6_principal": ("principal_policy_json",),
            "n6_ai_user": ("readable_scope_policy",),
            "n6_principal_account": ("account_policy_json",),
            "n6_watchlist_ownership": ("ownership_policy_json",),
            "n6_strategy": ("strategy_payload_json",),
        }
        counts: dict[str, int] = {}
        for table, (json_col,) in specs.items():
            if not self._object_exists(cur, table):
                counts[table] = 0
                continue
            cur.execute(
                f"SELECT count(*)::int AS count FROM {table} WHERE {json_col}->>'seed_run_id' = %s",
                (seed_run_id,),
            )
            counts[table] = int(cur.fetchone()["count"])
        return counts

    def _fetch_admin_users(self, cur: psycopg.Cursor[dict[str, Any]]) -> list[AdminUserSummary]:
        cur.execute(
            """
            SELECT user_id, login_name, role, status
            FROM user_account
            WHERE login_name = 'admin'
            ORDER BY user_id
            """
        )
        return [AdminUserSummary(**dict(row)) for row in cur.fetchall()]

    def _role_exists(self, cur: psycopg.Cursor[dict[str, Any]], role_name: str) -> bool:
        cur.execute("SELECT to_regrole(%s) IS NOT NULL AS exists", (role_name,))
        return bool(cur.fetchone()["exists"])

    def _fetch_role_grants(self, cur: psycopg.Cursor[dict[str, Any]], names: tuple[str, ...]) -> list[dict[str, str]]:
        cur.execute(
            """
            SELECT table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE table_schema = 'public'
              AND grantee = 'n6_ui_readonly_role'
              AND table_name = ANY(%s)
            ORDER BY table_name, privilege_type
            """,
            (list(names),),
        )
        return [dict(row) for row in cur.fetchall()]

    def _count_view_triggers(self, cur: psycopg.Cursor[dict[str, Any]]) -> int:
        if not all(self._object_exists(cur, view) for view in READONLY_VIEWS):
            return 0
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM pg_trigger
            WHERE tgrelid IN (
              'v_n6_stock_condition_display_basis'::regclass,
              'v_n6_index_condition_display_basis'::regclass,
              'v_n6_board_condition_display_basis'::regclass,
              'v_n6_index_membership_fact'::regclass,
              'v_n6_board_membership_fact'::regclass
            )
              AND NOT tgisinternal
            """
        )
        return int(cur.fetchone()["count"])

    def _count_admin_principal(self, cur: psycopg.Cursor[dict[str, Any]], admin_user_id: int | None) -> int:
        if admin_user_id is None or not self._object_exists(cur, "n6_principal"):
            return 0
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM n6_principal
            WHERE principal_type = 'admin'
              AND owner_user_id = %s
            """,
            (admin_user_id,),
        )
        return int(cur.fetchone()["count"])

    def _count_system_principal(self, cur: psycopg.Cursor[dict[str, Any]]) -> int:
        if not self._object_exists(cur, "n6_principal"):
            return 0
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM n6_principal
            WHERE principal_type = 'system'
            """
        )
        return int(cur.fetchone()["count"])

    def _count_active_ai_without_profile(self, cur: psycopg.Cursor[dict[str, Any]]) -> int:
        if not self._object_exists(cur, "n6_principal") or not self._object_exists(cur, "n6_ai_user"):
            return 0
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM n6_principal p
            LEFT JOIN n6_ai_user ai ON ai.principal_id = p.principal_id
            WHERE p.principal_type = 'ai_user'
              AND p.principal_status = 'active'
              AND ai.principal_id IS NULL
            """
        )
        return int(cur.fetchone()["count"])

    def _insert_principal(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        *,
        principal_type: str,
        owner_user_id: int | None,
        principal_status: str,
        principal_label: str,
        seed_key: str,
        seed_run_id: str,
    ) -> dict[str, Any]:
        policy = {
            "seed_run_id": seed_run_id,
            "seed_key": seed_key,
            "policy_version": POLICY_VERSION,
            "policy_hash": POLICY_HASH,
            "source_artifact": SOURCE_ARTIFACT,
            "created_by_gate": CREATED_BY_GATE,
        }
        cur.execute(
            """
            INSERT INTO n6_principal (
              principal_type,
              owner_user_id,
              principal_status,
              principal_label,
              principal_policy_json
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING principal_id, principal_type, owner_user_id, principal_status
            """,
            (principal_type, owner_user_id, principal_status, principal_label, Jsonb(policy)),
        )
        return dict(cur.fetchone())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize N6 Track B owner/principal seed rows once.")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Defaults to caller-provided project default.")
    parser.add_argument("--seed-run-id", default=SEED_RUN_ID)
    parser.add_argument("--contract-path", default=CONTRACT_PATH)
    parser.add_argument("--execute", action="store_true", help="Required for the future write path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required with --execute.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def run_owner_principal_initialization(
    *,
    repository: OwnerPrincipalInitializationRepository | None = None,
    dsn: str | None = None,
    seed_run_id: str = SEED_RUN_ID,
    execute: bool = False,
    user_confirmed: bool = False,
    contract_path: str = CONTRACT_PATH,
    rollback_sql_path: str = ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    base_report = {
        "seed_run_id": seed_run_id,
        "started_at": started_at,
        "planned_rows": dict(PLANNED_ROWS),
        "allowed_write_tables": ["n6_principal"],
        "forbidden_write_tables": [
            "n6_principal_account",
            "n6_ai_user",
            "n6_watchlist_ownership",
            "n6_strategy",
            "user_account",
            "user_session",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ],
        "rollback_sql_path": rollback_sql_path,
        "database_written": False,
    }

    if not execute:
        return blocked_report(base_report, ["missing_execute_flag"])
    if not user_confirmed:
        return blocked_report(base_report, ["missing_user_confirmed_flag"])

    artifact_blockers = validate_contract_artifact(contract_path, seed_run_id)
    if artifact_blockers:
        return blocked_report(base_report, artifact_blockers)

    if repository is None:
        if not dsn:
            return blocked_report(base_report, ["missing_dsn"])
        repository = PostgresOwnerPrincipalInitializationRepository(dsn)

    snapshot = repository.fetch_preflight_snapshot(seed_run_id)
    preflight = build_preflight(snapshot, seed_run_id=seed_run_id)
    if preflight["blockers"]:
        report = blocked_report(base_report, preflight["blockers"])
        report["preflight"] = preflight
        return report

    admin_user_id = preflight["admin_user"]["user_id"]
    write_result = repository.insert_seed_principals(seed_run_id=seed_run_id, admin_user_id=admin_user_id)
    return {
        **base_report,
        "result": "EXECUTED",
        "preflight_result": "PREFLIGHT_PASS",
        "preflight": preflight,
        "write_result": write_result,
        "database_written": True,
        "outbox_consumed_or_updated": False,
        "worker_started": False,
        "delivery_push_voice_mobile_sim_position_real_trade": False,
        "finished_at": utc_now_iso(),
    }


def build_preflight(snapshot: OwnerPrincipalPreflightSnapshot, *, seed_run_id: str) -> dict[str, Any]:
    blockers: list[str] = []
    missing_tables = [table for table, exists in snapshot.table_exists.items() if not exists]
    missing_views = [view for view, exists in snapshot.view_exists.items() if not exists]
    if missing_tables:
        blockers.append("missing_036_tables")
    if missing_views:
        blockers.append("missing_036_views")
    if not snapshot.readonly_role_exists:
        blockers.append("readonly_role_missing")

    view_grants = {(row["table_name"], row["privilege_type"]) for row in snapshot.readonly_role_view_grants}
    expected_view_grants = {(view, "SELECT") for view in READONLY_VIEWS}
    if view_grants != expected_view_grants:
        blockers.append("readonly_role_view_grants_not_select_only")
    if snapshot.readonly_role_base_table_grants:
        blockers.append("readonly_role_has_base_table_grants")
    if snapshot.view_trigger_count != 0:
        blockers.append("view_trigger_count_nonzero")

    active_admins = [
        user
        for user in snapshot.admin_users
        if user.login_name == "admin" and user.role == "admin" and user.status == "active"
    ]
    if len(active_admins) != 1 or len(snapshot.admin_users) != 1:
        blockers.append("active_admin_user_not_exactly_one")

    if any(count != 0 for count in snapshot.seed_scoped_counts.values()):
        blockers.append("seed_scoped_baseline_nonzero")
    if snapshot.duplicate_admin_principal_count != 0:
        blockers.append("duplicate_admin_principal")
    if snapshot.duplicate_system_principal_count != 0:
        blockers.append("duplicate_system_principal")
    if snapshot.active_ai_without_profile_count != 0:
        blockers.append("active_ai_without_profile")
    if snapshot.outbox_ref_count != 0:
        blockers.append("outbox_refs_nonzero")
    if snapshot.side_effect_ref_count != 0:
        blockers.append("side_effect_refs_nonzero")

    return {
        "result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "seed_run_id": seed_run_id,
        "blockers": blockers,
        "table_exists": dict(snapshot.table_exists),
        "view_exists": dict(snapshot.view_exists),
        "table_counts": dict(snapshot.table_counts),
        "seed_scoped_counts": dict(snapshot.seed_scoped_counts),
        "admin_user": asdict(active_admins[0]) if len(active_admins) == 1 and len(snapshot.admin_users) == 1 else None,
        "readonly_role_exists": snapshot.readonly_role_exists,
        "readonly_role_view_grants": list(snapshot.readonly_role_view_grants),
        "readonly_role_base_table_grants": list(snapshot.readonly_role_base_table_grants),
        "view_trigger_count": snapshot.view_trigger_count,
        "duplicate_admin_principal_count": snapshot.duplicate_admin_principal_count,
        "duplicate_system_principal_count": snapshot.duplicate_system_principal_count,
        "active_ai_without_profile_count": snapshot.active_ai_without_profile_count,
        "outbox_ref_count": snapshot.outbox_ref_count,
        "side_effect_ref_count": snapshot.side_effect_ref_count,
        "planned_rows": dict(PLANNED_ROWS),
    }


def validate_contract_artifact(contract_path: str, seed_run_id: str) -> list[str]:
    path = Path(contract_path)
    if not path.exists():
        return ["missing_contract_json"]
    try:
        artifact = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ["invalid_contract_json"]
    blockers: list[str] = []
    if artifact.get("result") != "CONTRACT_PASS":
        blockers.append("contract_status_not_pass")
    if artifact.get("seed_run_id") != seed_run_id:
        blockers.append("contract_seed_run_id_mismatch")
    if artifact.get("planned_rows") != PLANNED_ROWS:
        blockers.append("contract_planned_rows_mismatch")
    return blockers


def blocked_report(base_report: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    return {
        **dict(base_report),
        "result": "BLOCKED",
        "blockers": blockers,
        "preflight_result": "BLOCKED",
        "write_result": None,
        "finished_at": utc_now_iso(),
    }


def format_summary(report: Mapping[str, Any]) -> str:
    if report.get("result") == "EXECUTED":
        write_result = report.get("write_result") or {}
        return (
            "result=EXECUTED\n"
            f"seed_run_id={report.get('seed_run_id')}\n"
            f"n6_principal_rows_inserted={write_result.get('n6_principal_rows_inserted')}\n"
            "forbidden_rows_inserted=0\n"
            f"rollback_sql_path={report.get('rollback_sql_path')}"
        )
    return (
        f"result={report.get('result')}\n"
        f"seed_run_id={report.get('seed_run_id')}\n"
        f"blockers={','.join(report.get('blockers') or [])}\n"
        f"rollback_sql_path={report.get('rollback_sql_path')}"
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
