"""Guarded N6 virtual-account bootstrap 047 one-shot.

Planning is local-only.  The database is not contacted unless both execute
gates are present, the fixed libpq owner service is selected, and no
password/DSN environment variable is exposed to the process.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

import psycopg
from psycopg.rows import dict_row


RUN_ID = "n6_btrack_virtual_account_bootstrap_047_v1"
POLICY_VERSION = "n6_btrack_virtual_account_bootstrap_047_policy_v1"
POLICY_HASH = "62dddda28c79963ee67e204bc2c8e3dd21dce79411b36d90cce93c696a28c63b"
INITIAL_CASH = "100000000.0000"
OWNER_SERVICE = "ashare_v3_owner"
EXPECTED_OWNER_ROLE = "ashare_v3_user"
EXPECTED_DATABASE = "ashare_v3"
MIGRATION_PATH = Path("sql/047_n6_virtual_account_bootstrap.sql")
ROLLBACK_PATH = Path("sql/047_n6_virtual_account_bootstrap_rollback.sql")
CONTRACT_PATH = Path(
    "docs/N6_B_TRACK_PRODUCT_V3_MULTI_USER_VIRTUAL_ACCOUNT_BOOTSTRAP_047_CONTRACT.json"
)
TARGET_PRINCIPALS = (
    {"principal_id": 1, "principal_type": "admin", "mode": "audit_top_up"},
    {"principal_id": 3, "principal_type": "human_user", "mode": "create"},
    {"principal_id": 4, "principal_type": "human_user", "mode": "create"},
    {"principal_id": 5, "principal_type": "human_user", "mode": "create"},
    {"principal_id": 6, "principal_type": "human_user", "mode": "create"},
)
ALLOWED_DML_TABLES = (
    "n6_virtual_account",
    "n6_virtual_cash_ledger",
    "n6_virtual_cash_snapshot",
)
FORBIDDEN_DML_TABLES = (
    "user_monitor_stock",
    "user_monitor_index",
    "user_monitor_board",
    "user_realtime_monitor_scope",
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "n6_virtual_quote_run",
    "n6_virtual_quote_snapshot",
    "n6_virtual_trade_proposal",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_position",
    "n6_virtual_position_lot",
    "n6_virtual_position_event",
    "n6_virtual_pnl_snapshot",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)
FORBIDDEN_SECRET_ENV = (
    "PGPASSWORD",
    "ASHARE_V3_POSTGRES_DSN",
    "DATABASE_URL",
    "PG_DSN",
    "POSTGRES_DSN",
    "ASHARE_V3_N6_BTRACK_DSN",
    "ASHARE_V3_N6_BTRACK_PASSWORD",
)


class BootstrapRepository(Protocol):
    def execute_migration(self, sql: str) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ExecutionEnvironment:
    service: str
    service_file_valid: bool
    passfile_valid: bool
    forbidden_secret_keys: tuple[str, ...]


class PostgresBootstrapRepository:
    """Owner-only migration repository using a fixed libpq service."""

    def __init__(
        self,
        *,
        connect: Callable[..., Any] = psycopg.connect,
        service: str = OWNER_SERVICE,
        expected_owner_role: str = EXPECTED_OWNER_ROLE,
    ) -> None:
        self._connect = connect
        self._service = service
        self._expected_owner_role = expected_owner_role

    def execute_migration(self, sql: str) -> dict[str, Any]:
        with self._connect(
            f"service={self._service}",
            connect_timeout=10,
            row_factory=dict_row,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_database() AS database_name,
                           current_user AS current_role,
                           session_user AS session_role,
                           pg_get_userbyid(datdba) AS database_owner
                    FROM pg_database
                    WHERE datname = current_database()
                    """
                )
                authority = dict(cur.fetchone())
                expected = self._expected_owner_role
                if (
                    authority["database_name"] != EXPECTED_DATABASE
                    or authority["current_role"] != expected
                    or authority["session_role"] != expected
                    or authority["database_owner"] != expected
                ):
                    raise RuntimeError("047_owner_migration_identity_rejected")
                cur.execute(sql)
            conn.commit()
        return {
            "executed": True,
            "owner_identity_verified": True,
            "migration_path": str(MIGRATION_PATH),
        }


def _safe_absolute_path(value: str) -> bool:
    return bool(
        value
        and "\x00" not in value
        and "\r" not in value
        and "\n" not in value
        and Path(value).is_absolute()
    )


def inspect_execution_environment(env: Mapping[str, str]) -> ExecutionEnvironment:
    service_file = str(env.get("PGSERVICEFILE") or "")
    passfile = str(env.get("PGPASSFILE") or "")
    return ExecutionEnvironment(
        service=str(env.get("PGSERVICE") or ""),
        service_file_valid=_safe_absolute_path(service_file),
        passfile_valid=_safe_absolute_path(passfile),
        forbidden_secret_keys=tuple(
            sorted(key for key in FORBIDDEN_SECRET_ENV if str(env.get(key) or ""))
        ),
    )


def environment_blockers(env: Mapping[str, str]) -> list[str]:
    snapshot = inspect_execution_environment(env)
    blockers: list[str] = []
    if snapshot.service != OWNER_SERVICE:
        blockers.append("owner_service_not_exact")
    if not snapshot.service_file_valid:
        blockers.append("pgservicefile_invalid")
    if not snapshot.passfile_valid:
        blockers.append("pgpassfile_invalid")
    if snapshot.forbidden_secret_keys:
        blockers.append("forbidden_password_or_dsn_environment")
    return blockers


def validate_contract(path: Path = CONTRACT_PATH) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, ["contract_unreadable"]
    if payload.get("contract_version") != RUN_ID:
        blockers.append("contract_version_mismatch")
    if payload.get("policy_version") != POLICY_VERSION:
        blockers.append("contract_policy_version_mismatch")
    if payload.get("policy_hash") != POLICY_HASH:
        blockers.append("contract_policy_hash_mismatch")
    if payload.get("initial_cash") != INITIAL_CASH:
        blockers.append("contract_initial_cash_mismatch")
    if payload.get("target_principals") != list(TARGET_PRINCIPALS):
        blockers.append("contract_target_principals_mismatch")
    if payload.get("allowed_dml_tables") != list(ALLOWED_DML_TABLES):
        blockers.append("contract_allowed_dml_mismatch")
    return payload, blockers


def build_plan(
    *,
    contract_path: Path = CONTRACT_PATH,
    migration_path: Path = MIGRATION_PATH,
    rollback_path: Path = ROLLBACK_PATH,
) -> dict[str, Any]:
    contract, blockers = validate_contract(contract_path)
    for label, path in (
        ("migration", migration_path),
        ("rollback", rollback_path),
    ):
        if not path.is_file():
            blockers.append(f"{label}_sql_missing")
    return {
        "result": "PLAN_READY" if not blockers else "BLOCKED",
        "mode": "read_only_local_plan",
        "execute_authorized": False,
        "execute_runtime_preflight_status":
            "future_runtime_control_credential_gate_required",
        "database_connected": False,
        "database_written": False,
        "run_id": RUN_ID,
        "policy_version": POLICY_VERSION,
        "policy_hash": POLICY_HASH,
        "initial_cash": INITIAL_CASH,
        "target_principals": list(TARGET_PRINCIPALS),
        "allowed_dml_tables": list(ALLOWED_DML_TABLES),
        "forbidden_dml_tables": list(FORBIDDEN_DML_TABLES),
        "migration_path": str(migration_path),
        "rollback_path": str(rollback_path),
        "contract_path": str(contract_path),
        "contract_status": contract.get("status"),
        "execute_requires": [
            "--execute",
            "--user-confirmed",
            f"PGSERVICE={OWNER_SERVICE}",
            "PGSERVICEFILE",
            "PGPASSFILE",
            f"database={EXPECTED_DATABASE}",
            f"database_owner={EXPECTED_OWNER_ROLE}",
        ],
        "blockers": blockers,
    }


def run_bootstrap(
    *,
    execute: bool = False,
    user_confirmed: bool = False,
    env: Mapping[str, str] | None = None,
    repository: BootstrapRepository | None = None,
    contract_path: Path = CONTRACT_PATH,
    migration_path: Path = MIGRATION_PATH,
    rollback_path: Path = ROLLBACK_PATH,
) -> dict[str, Any]:
    plan = build_plan(
        contract_path=contract_path,
        migration_path=migration_path,
        rollback_path=rollback_path,
    )
    if not execute:
        return plan

    blockers = list(plan["blockers"])
    if not user_confirmed:
        blockers.append("missing_user_confirmed")
    runtime_env = os.environ if env is None else env
    blockers.extend(environment_blockers(runtime_env))
    if blockers:
        return {
            **plan,
            "result": "BLOCKED",
            "mode": "execute_blocked_before_connection",
            "blockers": list(dict.fromkeys(blockers)),
        }

    sql = migration_path.read_text(encoding="utf-8")
    repo = repository or PostgresBootstrapRepository()
    write_result = repo.execute_migration(sql)
    return {
        **plan,
        "result": "EXECUTED",
        "mode": "owner_migration_execute",
        "execute_authorized": True,
        "execute_runtime_preflight_status": "verified_in_execute_connection",
        "database_connected": True,
        "database_written": True,
        "blockers": [],
        "write_result": write_result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute guarded N6 virtual-account bootstrap 047."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--contract-path", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--migration-path", type=Path, default=MIGRATION_PATH)
    parser.add_argument("--rollback-path", type=Path, default=ROLLBACK_PATH)
    parser.add_argument("--json", action="store_true")
    return parser


def format_summary(report: Mapping[str, Any]) -> str:
    return "\n".join(
        (
            f"result={report.get('result')}",
            f"mode={report.get('mode')}",
            f"database_connected={str(bool(report.get('database_connected'))).lower()}",
            f"database_written={str(bool(report.get('database_written'))).lower()}",
            f"run_id={report.get('run_id')}",
            f"blockers={','.join(report.get('blockers') or []) or 'none'}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_bootstrap(
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        contract_path=args.contract_path,
        migration_path=args.migration_path,
        rollback_path=args.rollback_path,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_summary(report))
    return 0 if report["result"] in {"PLAN_READY", "EXECUTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
