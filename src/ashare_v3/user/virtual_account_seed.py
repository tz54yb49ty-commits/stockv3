"""N6 Phase 3 virtual account seed runner.

The runner is intentionally narrow and double-gated. It can only create the
first admin virtual account and its initial cash ledger/snapshot rows approved
by the Phase 3 seed contract. It never creates human demo accounts, AI
accounts, orders, trades, positions, PnL rows, delivery rows, outbox rows,
workers, sim rows, or real trades.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


SEED_RUN_ID = "n6_phase3_virtual_account_seed_20260605_v1"
POLICY_VERSION = "n6_phase3_virtual_account_seed_policy_v1"
POLICY_HASH = "b85a7bc71353a5ccfe0479fa67f2b403e91eb3f2fa1a0ba89ebddfb6f5cd4377"
CONTRACT_PATH = "docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_execute_contract.json"
ROLLBACK_SQL_PATH = "sql/N6_phase3_virtual_account_seed_rollback.sql"
SOURCE_ARTIFACT = "docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_EXECUTE_CONTRACT.md"
CREATED_BY_GATE = "N6_PHASE3_VIRTUAL_ACCOUNT_SEED_EXECUTE_CONTRACT_GATE"
INITIAL_CASH = Decimal("1000000.0000")
TRADE_DATE = 20260605
ACCOUNT_NAME = "Admin Virtual Account"
LEDGER_TYPE = "initial_deposit"
VIRTUAL_ACCOUNT_STATUS = "active"
CASH_SNAPSHOT_STATUS = "active"
QUALITY_STATUS = "passed"

PHASE3_TABLES = (
    "n6_virtual_account",
    "n6_virtual_cash_ledger",
    "n6_virtual_cash_snapshot",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_position",
    "n6_virtual_position_event",
    "n6_virtual_pnl_snapshot",
)
READONLY_VIEWS = (
    "v_n6_stock_condition_display_basis",
    "v_n6_index_condition_display_basis",
    "v_n6_board_condition_display_basis",
    "v_n6_index_membership_fact",
    "v_n6_board_membership_fact",
)
N6_BASE_TABLES_FOR_READONLY_PROOF = (
    "n6_principal",
    "n6_ai_user",
    "n6_principal_account",
    "n6_watchlist_ownership",
    "n6_strategy",
)
PLANNED_ROWS = {
    "n6_virtual_account": 1,
    "n6_virtual_cash_ledger": 1,
    "n6_virtual_cash_snapshot": 1,
    "n6_virtual_order": 0,
    "n6_virtual_trade": 0,
    "n6_virtual_position": 0,
    "n6_virtual_position_event": 0,
    "n6_virtual_pnl_snapshot": 0,
}
ALLOWED_WRITE_TABLES = (
    "n6_virtual_account",
    "n6_virtual_cash_ledger",
    "n6_virtual_cash_snapshot",
)
FORBIDDEN_WRITE_TABLES = (
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_position",
    "n6_virtual_position_event",
    "n6_virtual_pnl_snapshot",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)


@dataclass
class AdminPrincipalSummary:
    principal_id: int
    principal_type: str
    principal_status: str
    owner_user_id: int
    login_name: str


@dataclass
class VirtualAccountSeedPreflightSnapshot:
    seed_run_id: str
    table_exists: dict[str, bool]
    table_counts: dict[str, int | None]
    seed_scoped_counts: dict[str, int]
    admin_principals: list[AdminPrincipalSummary]
    system_principal_count: int
    admin_active_virtual_account_count: int
    readonly_role_exists: bool
    readonly_role_view_select_only: bool
    readonly_role_base_table_grants: list[dict[str, str]]
    view_trigger_count: int
    outbox_ref_count: int
    worker_or_downstream_ref_count: int


class VirtualAccountSeedRepository(Protocol):
    def fetch_preflight_snapshot(self, seed_run_id: str) -> VirtualAccountSeedPreflightSnapshot:
        ...

    def commit_seed(
        self,
        *,
        seed_run_id: str,
        admin_principal_id: int,
        initial_cash: Decimal,
        trade_date: int,
    ) -> dict[str, object]:
        ...


class PostgresVirtualAccountSeedRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def fetch_preflight_snapshot(self, seed_run_id: str) -> VirtualAccountSeedPreflightSnapshot:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            return self._fetch_snapshot(cur, seed_run_id)

    def commit_seed(
        self,
        *,
        seed_run_id: str,
        admin_principal_id: int,
        initial_cash: Decimal,
        trade_date: int,
    ) -> dict[str, object]:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                snapshot = self._fetch_snapshot(cur, seed_run_id)
                preflight = build_preflight(snapshot, seed_run_id=seed_run_id)
                if preflight["blockers"]:
                    raise RuntimeError("virtual account seed blocked by refreshed preflight")

                account = self._insert_virtual_account(cur, seed_run_id, admin_principal_id, initial_cash)
                ledger = self._insert_initial_cash_ledger(cur, seed_run_id, account["virtual_account_id"], initial_cash, trade_date)
                cash_snapshot = self._insert_initial_cash_snapshot(
                    cur,
                    seed_run_id,
                    account["virtual_account_id"],
                    ledger["cash_ledger_id"],
                    initial_cash,
                    trade_date,
                )
                self._update_account_cash_snapshot_pointer(
                    cur,
                    account["virtual_account_id"],
                    cash_snapshot["cash_snapshot_id"],
                )

        return {
            "committed": True,
            "n6_virtual_account_rows_inserted": 1,
            "n6_virtual_cash_ledger_rows_inserted": 1,
            "n6_virtual_cash_snapshot_rows_inserted": 1,
            "n6_virtual_order_rows_inserted": 0,
            "n6_virtual_trade_rows_inserted": 0,
            "n6_virtual_position_rows_inserted": 0,
            "n6_virtual_position_event_rows_inserted": 0,
            "n6_virtual_pnl_snapshot_rows_inserted": 0,
            "virtual_account_id": account["virtual_account_id"],
            "cash_ledger_id": ledger["cash_ledger_id"],
            "cash_snapshot_id": cash_snapshot["cash_snapshot_id"],
            "current_cash_snapshot_id_updated": True,
        }

    def _fetch_snapshot(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        seed_run_id: str,
    ) -> VirtualAccountSeedPreflightSnapshot:
        table_exists = {table: self._object_exists(cur, table) for table in PHASE3_TABLES}
        table_counts = {table: self._count_table(cur, table) if table_exists[table] else None for table in PHASE3_TABLES}
        return VirtualAccountSeedPreflightSnapshot(
            seed_run_id=seed_run_id,
            table_exists=table_exists,
            table_counts=table_counts,
            seed_scoped_counts=self._seed_scoped_counts(cur, seed_run_id),
            admin_principals=self._fetch_admin_principals(cur),
            system_principal_count=self._count_system_principals(cur),
            admin_active_virtual_account_count=self._count_admin_active_virtual_accounts(cur),
            readonly_role_exists=self._role_exists(cur, "n6_ui_readonly_role"),
            readonly_role_view_select_only=self._readonly_view_grants_are_select_only(cur),
            readonly_role_base_table_grants=self._fetch_role_grants(cur, N6_BASE_TABLES_FOR_READONLY_PROOF),
            view_trigger_count=self._count_view_triggers(cur),
            outbox_ref_count=self._count_optional_runtime_refs(cur, seed_run_id),
            worker_or_downstream_ref_count=0,
        )

    def _object_exists(self, cur: psycopg.Cursor[dict[str, Any]], object_name: str) -> bool:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{object_name}",))
        return bool(cur.fetchone()["exists"])

    def _role_exists(self, cur: psycopg.Cursor[dict[str, Any]], role_name: str) -> bool:
        cur.execute("SELECT to_regrole(%s) IS NOT NULL AS exists", (role_name,))
        return bool(cur.fetchone()["exists"])

    def _count_table(self, cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> int:
        cur.execute(f"SELECT count(*)::int AS count FROM {table_name}")
        return int(cur.fetchone()["count"])

    def _seed_scoped_counts(self, cur: psycopg.Cursor[dict[str, Any]], seed_run_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in PHASE3_TABLES:
            if not self._object_exists(cur, table):
                counts[table] = 0
                continue
            cur.execute(
                f"""
                SELECT count(*)::int AS count
                FROM {table}
                WHERE run_id = %s OR rollback_scope = %s
                """,
                (seed_run_id, seed_run_id),
            )
            counts[table] = int(cur.fetchone()["count"])
        return counts

    def _fetch_admin_principals(self, cur: psycopg.Cursor[dict[str, Any]]) -> list[AdminPrincipalSummary]:
        if not self._object_exists(cur, "n6_principal"):
            return []
        cur.execute(
            """
            SELECT p.principal_id,
                   p.principal_type,
                   p.principal_status,
                   p.owner_user_id,
                   u.login_name
            FROM n6_principal p
            JOIN user_account u ON u.user_id = p.owner_user_id
            WHERE p.principal_type = 'admin'
              AND p.principal_status = 'active'
              AND u.login_name = 'admin'
              AND u.status = 'active'
            ORDER BY p.principal_id
            """
        )
        return [AdminPrincipalSummary(**dict(row)) for row in cur.fetchall()]

    def _count_system_principals(self, cur: psycopg.Cursor[dict[str, Any]]) -> int:
        if not self._object_exists(cur, "n6_principal"):
            return 0
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM n6_principal
            WHERE principal_type = 'system'
              AND principal_status = 'system_reserved'
            """
        )
        return int(cur.fetchone()["count"])

    def _count_admin_active_virtual_accounts(self, cur: psycopg.Cursor[dict[str, Any]]) -> int:
        if not self._object_exists(cur, "n6_virtual_account") or not self._object_exists(cur, "n6_principal"):
            return 0
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM n6_virtual_account va
            JOIN n6_principal p
              ON p.principal_id = va.principal_id
             AND p.principal_type = va.principal_type
            WHERE va.principal_type = 'admin'
              AND va.virtual_account_status = 'active'
              AND p.principal_status = 'active'
            """
        )
        return int(cur.fetchone()["count"])

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

    def _readonly_view_grants_are_select_only(self, cur: psycopg.Cursor[dict[str, Any]]) -> bool:
        grants = self._fetch_role_grants(cur, READONLY_VIEWS)
        return {(row["table_name"], row["privilege_type"]) for row in grants} == {(view, "SELECT") for view in READONLY_VIEWS}

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

    def _count_optional_runtime_refs(self, cur: psycopg.Cursor[dict[str, Any]], seed_run_id: str) -> int:
        total = 0
        for table in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"):
            if not self._object_exists(cur, table):
                continue
            columns = self._existing_columns(cur, table, ("source_run_id", "consumer_run_id", "run_id"))
            for column in columns:
                cur.execute(f"SELECT count(*)::int AS count FROM {table} WHERE {column} = %s", (seed_run_id,))
                total += int(cur.fetchone()["count"])
        return total

    def _existing_columns(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        table_name: str,
        candidates: tuple[str, ...],
    ) -> list[str]:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = ANY(%s)
            """,
            (table_name, list(candidates)),
        )
        return [row["column_name"] for row in cur.fetchall()]

    def _lineage_payload(self, seed_run_id: str, seed_key: str) -> dict[str, Any]:
        return {
            "seed_run_id": seed_run_id,
            "seed_key": seed_key,
            "policy_version": POLICY_VERSION,
            "policy_hash": POLICY_HASH,
            "rollback_scope": seed_run_id,
            "source_artifact": SOURCE_ARTIFACT,
            "created_by_gate": CREATED_BY_GATE,
            "initial_cash": str(INITIAL_CASH),
            "currency": "CNY",
        }

    def _insert_virtual_account(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        seed_run_id: str,
        admin_principal_id: int,
        initial_cash: Decimal,
    ) -> dict[str, Any]:
        cur.execute(
            """
            INSERT INTO n6_virtual_account (
              principal_id,
              principal_type,
              account_name,
              virtual_account_status,
              base_currency,
              initial_cash,
              current_cash_snapshot_id,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              source_lineage_json,
              quality_status
            )
            VALUES (%s, 'admin', %s, %s, 'CNY', %s, NULL, %s, %s, %s, %s, %s, %s)
            RETURNING virtual_account_id
            """,
            (
                admin_principal_id,
                ACCOUNT_NAME,
                VIRTUAL_ACCOUNT_STATUS,
                initial_cash,
                seed_run_id,
                POLICY_VERSION,
                POLICY_HASH,
                seed_run_id,
                Jsonb(self._lineage_payload(seed_run_id, "phase3_admin_virtual_account")),
                QUALITY_STATUS,
            ),
        )
        return dict(cur.fetchone())

    def _insert_initial_cash_ledger(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        seed_run_id: str,
        virtual_account_id: int,
        initial_cash: Decimal,
        trade_date: int,
    ) -> dict[str, Any]:
        cur.execute(
            """
            INSERT INTO n6_virtual_cash_ledger (
              virtual_account_id,
              ledger_type,
              amount,
              currency,
              trade_date,
              event_time,
              source_event_type,
              source_event_id,
              source_virtual_order_id,
              source_virtual_trade_id,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              source_lineage_json,
              quality_status
            )
            VALUES (%s, %s, %s, 'CNY', %s, now(), %s, %s, NULL, NULL, %s, %s, %s, %s, %s, %s)
            RETURNING cash_ledger_id
            """,
            (
                virtual_account_id,
                LEDGER_TYPE,
                initial_cash,
                trade_date,
                "phase3_virtual_account_seed",
                seed_run_id,
                seed_run_id,
                POLICY_VERSION,
                POLICY_HASH,
                seed_run_id,
                Jsonb(self._lineage_payload(seed_run_id, "phase3_admin_initial_cash_ledger")),
                QUALITY_STATUS,
            ),
        )
        return dict(cur.fetchone())

    def _insert_initial_cash_snapshot(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        seed_run_id: str,
        virtual_account_id: int,
        cash_ledger_id: int,
        initial_cash: Decimal,
        trade_date: int,
    ) -> dict[str, Any]:
        cur.execute(
            """
            INSERT INTO n6_virtual_cash_snapshot (
              virtual_account_id,
              snapshot_time,
              trade_date,
              available_cash,
              frozen_cash,
              total_cash,
              currency,
              source_ledger_max_id,
              snapshot_status,
              run_id,
              policy_version,
              policy_hash,
              rollback_scope,
              source_lineage_json,
              quality_status
            )
            VALUES (%s, now(), %s, %s, 0, %s, 'CNY', %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING cash_snapshot_id
            """,
            (
                virtual_account_id,
                trade_date,
                initial_cash,
                initial_cash,
                cash_ledger_id,
                CASH_SNAPSHOT_STATUS,
                seed_run_id,
                POLICY_VERSION,
                POLICY_HASH,
                seed_run_id,
                Jsonb(self._lineage_payload(seed_run_id, "phase3_admin_initial_cash_snapshot")),
                QUALITY_STATUS,
            ),
        )
        return dict(cur.fetchone())

    def _update_account_cash_snapshot_pointer(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        virtual_account_id: int,
        cash_snapshot_id: int,
    ) -> None:
        cur.execute(
            """
            UPDATE n6_virtual_account
            SET current_cash_snapshot_id = %s,
                updated_at = now()
            WHERE virtual_account_id = %s
            """,
            (cash_snapshot_id, virtual_account_id),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the first N6 Phase 3 admin virtual account once.")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Defaults to caller-provided project default.")
    parser.add_argument("--seed-run-id", default=SEED_RUN_ID)
    parser.add_argument("--contract-path", default=CONTRACT_PATH)
    parser.add_argument("--rollback-sql-path", default=ROLLBACK_SQL_PATH)
    parser.add_argument("--initial-cash", default=str(INITIAL_CASH))
    parser.add_argument("--trade-date", type=int, default=TRADE_DATE)
    parser.add_argument("--execute", action="store_true", help="Required for the future write path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required with --execute.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def run_virtual_account_seed(
    *,
    repository: VirtualAccountSeedRepository | None = None,
    dsn: str | None = None,
    seed_run_id: str = SEED_RUN_ID,
    execute: bool = False,
    user_confirmed: bool = False,
    contract_path: str = CONTRACT_PATH,
    rollback_sql_path: str = ROLLBACK_SQL_PATH,
    initial_cash: Decimal | str = INITIAL_CASH,
    trade_date: int = TRADE_DATE,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    initial_cash_decimal = Decimal(str(initial_cash))
    base_report = {
        "seed_run_id": seed_run_id,
        "started_at": started_at,
        "planned_rows": dict(PLANNED_ROWS),
        "seed_policy": {
            "policy_version": POLICY_VERSION,
            "policy_hash": POLICY_HASH,
            "principal": "admin",
            "initial_cash": str(initial_cash_decimal),
            "currency": "CNY",
            "ledger_type": LEDGER_TYPE,
            "virtual_account_status": VIRTUAL_ACCOUNT_STATUS,
            "cash_snapshot_status": CASH_SNAPSHOT_STATUS,
            "quality_status": QUALITY_STATUS,
        },
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
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
    if initial_cash_decimal != INITIAL_CASH:
        return blocked_report(base_report, ["initial_cash_policy_mismatch"])

    if repository is None:
        if not dsn:
            return blocked_report(base_report, ["missing_dsn"])
        repository = PostgresVirtualAccountSeedRepository(dsn)

    snapshot = repository.fetch_preflight_snapshot(seed_run_id)
    preflight = build_preflight(snapshot, seed_run_id=seed_run_id)
    if preflight["blockers"]:
        report = blocked_report(base_report, preflight["blockers"])
        report["preflight"] = preflight
        return report

    admin_principal_id = preflight["admin_principal"]["principal_id"]
    write_result = repository.commit_seed(
        seed_run_id=seed_run_id,
        admin_principal_id=admin_principal_id,
        initial_cash=initial_cash_decimal,
        trade_date=trade_date,
    )
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


def build_preflight(snapshot: VirtualAccountSeedPreflightSnapshot, *, seed_run_id: str) -> dict[str, Any]:
    blockers: list[str] = []
    missing_tables = [table for table, exists in snapshot.table_exists.items() if not exists]
    if missing_tables:
        blockers.append("phase3_schema_foundation_missing")
    if any(count not in (0, None) for count in snapshot.table_counts.values()):
        blockers.append("phase3_table_baseline_nonzero")
    if any(count != 0 for count in snapshot.seed_scoped_counts.values()):
        blockers.append("seed_scoped_baseline_nonzero")

    active_admins = [
        principal
        for principal in snapshot.admin_principals
        if principal.principal_type == "admin"
        and principal.principal_status == "active"
        and principal.login_name == "admin"
    ]
    if len(active_admins) != 1:
        blockers.append("admin_principal_not_exactly_one")
    if snapshot.system_principal_count != 1:
        blockers.append("system_principal_not_exactly_one")
    if snapshot.admin_active_virtual_account_count != 0:
        blockers.append("admin_active_virtual_account_exists")

    if not snapshot.readonly_role_exists:
        blockers.append("readonly_role_missing")
    if not snapshot.readonly_role_view_select_only:
        blockers.append("readonly_role_view_grants_not_select_only")
    if snapshot.readonly_role_base_table_grants:
        blockers.append("readonly_role_has_base_table_grants")
    if snapshot.view_trigger_count != 0:
        blockers.append("view_trigger_count_nonzero")
    if snapshot.outbox_ref_count != 0:
        blockers.append("outbox_refs_nonzero")
    if snapshot.worker_or_downstream_ref_count != 0:
        blockers.append("worker_or_downstream_refs_nonzero")

    return {
        "result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "seed_run_id": seed_run_id,
        "blockers": blockers,
        "table_exists": dict(snapshot.table_exists),
        "table_counts": dict(snapshot.table_counts),
        "seed_scoped_counts": dict(snapshot.seed_scoped_counts),
        "admin_principal": asdict(active_admins[0]) if len(active_admins) == 1 else None,
        "system_principal_count": snapshot.system_principal_count,
        "admin_active_virtual_account_count": snapshot.admin_active_virtual_account_count,
        "readonly_role_exists": snapshot.readonly_role_exists,
        "readonly_role_view_select_only": snapshot.readonly_role_view_select_only,
        "readonly_role_base_table_grants": list(snapshot.readonly_role_base_table_grants),
        "view_trigger_count": snapshot.view_trigger_count,
        "outbox_ref_count": snapshot.outbox_ref_count,
        "worker_or_downstream_ref_count": snapshot.worker_or_downstream_ref_count,
        "planned_rows": dict(PLANNED_ROWS),
    }


def validate_contract_artifact(contract_path: str, seed_run_id: str) -> list[str]:
    path = Path(contract_path)
    if not path.exists():
        return ["missing_contract_json"]
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["invalid_contract_json"]
    blockers: list[str] = []
    if artifact.get("result") != "CONTRACT_PASS":
        blockers.append("contract_status_not_pass")
    if artifact.get("seed_run_id") != seed_run_id:
        blockers.append("contract_seed_run_id_mismatch")
    if artifact.get("planned_rows") != PLANNED_ROWS:
        blockers.append("contract_planned_rows_mismatch")
    policy = artifact.get("seed_policy") or {}
    if policy and policy.get("policy_hash") != POLICY_HASH:
        blockers.append("contract_policy_hash_mismatch")
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
            f"n6_virtual_account_rows_inserted={write_result.get('n6_virtual_account_rows_inserted')}\n"
            f"n6_virtual_cash_ledger_rows_inserted={write_result.get('n6_virtual_cash_ledger_rows_inserted')}\n"
            f"n6_virtual_cash_snapshot_rows_inserted={write_result.get('n6_virtual_cash_snapshot_rows_inserted')}\n"
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
