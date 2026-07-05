"""N6 initial admin bootstrap runner.

The runner is intentionally double-gated. Without both ``--execute`` and
``--user-confirmed`` it only performs/readies preflight checks and writes a
report artifact. It never accepts passwords via CLI arguments.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import sys
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


DEFAULT_LOGIN_NAME = "admin"
DEFAULT_DISPLAY_NAME = "Initial Admin"
DEFAULT_PROFILE_NAME = "MVP default"
DEFAULT_JSON_REPORT_PATH = "docs/N6_admin_bootstrap_preflight.json"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/N6_ADMIN_BOOTSTRAP_PREFLIGHT.md"
DSN_ENV = "ASHARE_V3_POSTGRES_DSN"
PASSWORD_ENV = "ASHARE_V3_N6_ADMIN_PASSWORD"
EXPECTED_N5_OUTBOX_COUNTS = {
    "ActionEvent:pending": 479,
    "HintEvent:pending": 9,
}
ALLOWED_PASSWORD_COLUMNS = {
    "password_hash",
    "password_hash_algo",
    "password_updated_at",
}
N6_TABLES = (
    "user_account",
    "user_session",
    "user_filter_profile",
    "user_watchlist",
    "user_watchlist_item",
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_signal_decision",
    "user_notification_queue",
    "user_sim_account",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
)
OTHER_N6_BUSINESS_TABLES = tuple(table for table in N6_TABLES if table not in {"user_account", "user_filter_profile"})


@dataclass
class AdminAccountSummary:
    user_id: int
    login_name: str
    role: str
    status: str


@dataclass
class PreflightSnapshot:
    table_counts: dict[str, int | None]
    admin_accounts: list[AdminAccountSummary]
    admin_default_profile_count: int
    n5_outbox_counts: dict[str, int]
    password_columns: list[str]
    plaintext_password_columns: list[str]


@dataclass(frozen=True)
class HashResult:
    password_hash: str
    password_hash_algo: str


class AdminBootstrapRepository(Protocol):
    def fetch_preflight_snapshot(self) -> PreflightSnapshot:
        ...

    def insert_admin_and_default_profile(
        self,
        *,
        password_hash: str,
        password_hash_algo: str,
    ) -> dict[str, object]:
        ...


class PostgresAdminBootstrapRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def fetch_preflight_snapshot(self) -> PreflightSnapshot:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            table_counts = {table: self._count_table(cur, table) for table in N6_TABLES}
            admin_accounts = self._fetch_admin_accounts(cur)
            admin_user_ids = [account.user_id for account in admin_accounts]
            admin_default_profile_count = self._count_admin_default_profiles(cur, admin_user_ids)
            password_columns = self._fetch_user_account_password_columns(cur)
            plaintext_password_columns = [column for column in password_columns if column not in ALLOWED_PASSWORD_COLUMNS]
            return PreflightSnapshot(
                table_counts=table_counts,
                admin_accounts=admin_accounts,
                admin_default_profile_count=admin_default_profile_count,
                n5_outbox_counts=self._fetch_n5_outbox_counts(cur),
                password_columns=password_columns,
                plaintext_password_columns=plaintext_password_columns,
            )

    def insert_admin_and_default_profile(
        self,
        *,
        password_hash: str,
        password_hash_algo: str,
    ) -> dict[str, object]:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    snapshot = self._fetch_preflight_snapshot_for_write(cur)
                    preflight = build_preflight_report(snapshot)
                    if preflight["p0_blockers"]:
                        raise RuntimeError("admin bootstrap write blocked by refreshed preflight")

                    cur.execute(
                        """
                        INSERT INTO user_account (
                          login_name,
                          display_name,
                          password_hash,
                          password_hash_algo,
                          role,
                          status,
                          user_policy_json
                        )
                        VALUES (
                          %s, %s, %s, %s, 'admin', 'active',
                          %s
                        )
                        RETURNING user_id
                        """,
                        (
                            DEFAULT_LOGIN_NAME,
                            DEFAULT_DISPLAY_NAME,
                            password_hash,
                            password_hash_algo,
                            Jsonb({"bootstrap": "n6_admin_bootstrap"}),
                        ),
                    )
                    user_id = cur.fetchone()["user_id"]
                    cur.execute(
                        """
                        INSERT INTO user_filter_profile (
                          user_id,
                          profile_name,
                          is_default,
                          enable_chase,
                          enable_ultra_short,
                          enable_short,
                          enable_mid,
                          enable_long,
                          strong_board_rule_json,
                          top_index_strategy_rule_json,
                          permission_scope,
                          status
                        )
                        VALUES (
                          %s, %s, true, true, true, true, true, true,
                          %s, %s, 'self', 'active'
                        )
                        """,
                        (
                            user_id,
                            DEFAULT_PROFILE_NAME,
                            Jsonb(
                                {
                                    "period_transition_y": "volume_up",
                                    "period_transition_q": "volume_up",
                                    "period_transition_m": "volume_up",
                                }
                            ),
                            Jsonb({}),
                        ),
                    )
        return {
            "user_account_rows_inserted": 1,
            "user_filter_profile_rows_inserted": 1,
            "user_session_rows_inserted": 0,
            "user_projection_rows_inserted": 0,
            "user_notification_rows_inserted": 0,
            "user_sim_rows_inserted": 0,
        }

    def _fetch_preflight_snapshot_for_write(self, cur: psycopg.Cursor[dict[str, Any]]) -> PreflightSnapshot:
        table_counts = {table: self._count_table(cur, table) for table in N6_TABLES}
        admin_accounts = self._fetch_admin_accounts(cur)
        admin_user_ids = [account.user_id for account in admin_accounts]
        password_columns = self._fetch_user_account_password_columns(cur)
        plaintext_password_columns = [column for column in password_columns if column not in ALLOWED_PASSWORD_COLUMNS]
        return PreflightSnapshot(
            table_counts=table_counts,
            admin_accounts=admin_accounts,
            admin_default_profile_count=self._count_admin_default_profiles(cur, admin_user_ids),
            n5_outbox_counts=self._fetch_n5_outbox_counts(cur),
            password_columns=password_columns,
            plaintext_password_columns=plaintext_password_columns,
        )

    def _table_exists(self, cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
        cur.execute("SELECT to_regclass(%s) AS reg", (f"public.{table_name}",))
        return cur.fetchone()["reg"] is not None

    def _count_table(self, cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> int | None:
        if not self._table_exists(cur, table_name):
            return None
        cur.execute(f"SELECT count(*)::int AS count FROM {table_name}")
        return cur.fetchone()["count"]

    def _fetch_admin_accounts(self, cur: psycopg.Cursor[dict[str, Any]]) -> list[AdminAccountSummary]:
        if not self._table_exists(cur, "user_account"):
            return []
        cur.execute(
            """
            SELECT user_id, login_name, role, status
            FROM user_account
            WHERE login_name = %s
            ORDER BY user_id
            """,
            (DEFAULT_LOGIN_NAME,),
        )
        return [AdminAccountSummary(**dict(row)) for row in cur.fetchall()]

    def _count_admin_default_profiles(self, cur: psycopg.Cursor[dict[str, Any]], admin_user_ids: list[int]) -> int:
        if not admin_user_ids or not self._table_exists(cur, "user_filter_profile"):
            return 0
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM user_filter_profile
            WHERE user_id = ANY(%s)
              AND profile_name = %s
              AND is_default = true
            """,
            (admin_user_ids, DEFAULT_PROFILE_NAME),
        )
        return cur.fetchone()["count"]

    def _fetch_user_account_password_columns(self, cur: psycopg.Cursor[dict[str, Any]]) -> list[str]:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'user_account'
              AND column_name ILIKE '%%password%%'
            ORDER BY ordinal_position
            """
        )
        return [row["column_name"] for row in cur.fetchall()]

    def _fetch_n5_outbox_counts(self, cur: psycopg.Cursor[dict[str, Any]]) -> dict[str, int]:
        if not self._table_exists(cur, "common_event_outbox"):
            return {}
        cur.execute(
            """
            SELECT event_type, status, count(*)::int AS count
            FROM common_event_outbox
            WHERE source_layer = 'N5_action'
              AND event_type IN ('ActionEvent', 'HintEvent', 'RiskEvent', 'PositionEvent')
            GROUP BY event_type, status
            ORDER BY event_type, status
            """
        )
        return {f"{row['event_type']}:{row['status']}": row["count"] for row in cur.fetchall()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap the initial N6 admin account.")
    parser.add_argument("--execute", action="store_true", help="Actually write one admin account and default profile.")
    parser.add_argument("--user-confirmed", action="store_true", help="Second human confirmation required for execute.")
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def run_admin_bootstrap(
    *,
    repository: AdminBootstrapRepository | None = None,
    dsn: str | None = None,
    execute: bool,
    user_confirmed: bool,
    password: str | None = None,
    password_source: str | None = None,
    hasher: Any | None = None,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    blockers: list[str] = []
    if repository is None:
        if not dsn:
            blockers.append("missing_dsn_env")
            return build_blocked_without_repository(
                blockers=blockers,
                execute=execute,
                user_confirmed=user_confirmed,
                started_at=started_at,
            )
        repository = PostgresAdminBootstrapRepository(dsn)

    snapshot = repository.fetch_preflight_snapshot()
    preflight = build_preflight_report(snapshot)
    blockers.extend(preflight["p0_blockers"])

    if not execute:
        blockers.append("missing_execute_flag")
    if not user_confirmed:
        blockers.append("missing_user_confirmed_flag")

    password_checked = False
    if execute and user_confirmed and not preflight["p0_blockers"]:
        password_checked = True
        password_blockers = validate_password(password)
        blockers.extend(password_blockers)

    base_report = {
        "stage": "N6-admin-bootstrap",
        "layer_role": "N6_user",
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "execute": execute,
        "user_confirmed": user_confirmed,
        "password_source": password_source or ("provided" if password else "missing"),
        "password_checked": password_checked,
        "password_value_logged": False,
        "password_hash_logged": False,
        "preflight": preflight,
        "blockers": sorted(set(blockers)),
        "allowed_write_scope": {
            "user_account": 1,
            "user_filter_profile": 1,
            "user_session": 0,
            "user_projection_rows": 0,
            "user_notification_rows": 0,
            "user_sim_rows": 0,
        },
        "forbidden_scope": forbidden_scope(),
        "n5_outbox_before": dict(snapshot.n5_outbox_counts),
        "n5_outbox_after": None,
        "n5_outbox_unchanged": None,
    }

    if blockers:
        return {
            **base_report,
            "result": "BLOCKED",
            "allow_execute_final_gate": False,
            "write_result": None,
            "hash_algo_used": None,
        }

    hash_result = (hasher or hash_password)(password or "")
    write_result = repository.insert_admin_and_default_profile(
        password_hash=hash_result.password_hash,
        password_hash_algo=hash_result.password_hash_algo,
    )
    after_snapshot = repository.fetch_preflight_snapshot()
    n5_outbox_unchanged = dict(snapshot.n5_outbox_counts) == dict(after_snapshot.n5_outbox_counts)
    post_write_blockers = validate_post_write_result(write_result, after_snapshot, snapshot.n5_outbox_counts)

    result = "EXECUTED" if not post_write_blockers else "FAILED"
    return {
        **base_report,
        "finished_at": utc_now_iso(),
        "result": result,
        "allow_execute_final_gate": result == "EXECUTED",
        "blockers": post_write_blockers,
        "write_result": write_result,
        "hash_algo_used": hash_result.password_hash_algo,
        "n5_outbox_after": dict(after_snapshot.n5_outbox_counts),
        "n5_outbox_unchanged": n5_outbox_unchanged,
        "post_write_table_counts": dict(after_snapshot.table_counts),
    }


def build_preflight_report(snapshot: PreflightSnapshot) -> dict[str, Any]:
    blockers: list[str] = []
    missing_tables = sorted(table for table, count in snapshot.table_counts.items() if count is None)
    if missing_tables:
        blockers.append("n6_schema_tables_missing")

    active_admins = [account for account in snapshot.admin_accounts if account.status == "active"]
    disabled_or_deleted_admins = [
        account for account in snapshot.admin_accounts if account.status in {"disabled", "deleted"}
    ]
    other_admin_statuses = [
        account for account in snapshot.admin_accounts if account.status not in {"active", "disabled", "deleted"}
    ]
    if active_admins:
        blockers.append("admin_active_exists")
    if disabled_or_deleted_admins:
        blockers.append("admin_disabled_or_deleted_exists")
    if other_admin_statuses:
        blockers.append("admin_unexpected_status_exists")

    if (snapshot.table_counts.get("user_account") or 0) > len(snapshot.admin_accounts):
        blockers.append("non_admin_user_account_exists")
    if (snapshot.table_counts.get("user_filter_profile") or 0) > 0:
        blockers.append("user_filter_profile_not_empty")
    if snapshot.admin_default_profile_count > 0:
        blockers.append("admin_default_filter_profile_exists")

    non_empty_other_tables = {
        table: count
        for table, count in snapshot.table_counts.items()
        if table in OTHER_N6_BUSINESS_TABLES and count not in (0, None)
    }
    if non_empty_other_tables:
        blockers.append("other_n6_business_tables_not_empty")

    if snapshot.n5_outbox_counts != EXPECTED_N5_OUTBOX_COUNTS:
        blockers.append("n5_outbox_count_mismatch")
    if snapshot.plaintext_password_columns:
        blockers.append("plaintext_password_column_detected")
    for required_column in ("password_hash", "password_hash_algo"):
        if required_column not in snapshot.password_columns:
            blockers.append(f"missing_{required_column}_column")

    return {
        "result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "p0_blockers": sorted(set(blockers)),
        "table_counts": dict(snapshot.table_counts),
        "missing_tables": missing_tables,
        "admin_accounts": [asdict(account) for account in snapshot.admin_accounts],
        "admin_default_profile_count": snapshot.admin_default_profile_count,
        "non_empty_other_n6_tables": non_empty_other_tables,
        "n5_outbox_counts": dict(snapshot.n5_outbox_counts),
        "n5_outbox_expected": dict(EXPECTED_N5_OUTBOX_COUNTS),
        "password_columns": list(snapshot.password_columns),
        "plaintext_password_columns": list(snapshot.plaintext_password_columns),
        "read_only": True,
    }


def build_blocked_without_repository(
    *,
    blockers: list[str],
    execute: bool,
    user_confirmed: bool,
    started_at: str,
) -> dict[str, Any]:
    if not execute:
        blockers.append("missing_execute_flag")
    if not user_confirmed:
        blockers.append("missing_user_confirmed_flag")
    return {
        "stage": "N6-admin-bootstrap",
        "layer_role": "N6_user",
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "result": "BLOCKED",
        "execute": execute,
        "user_confirmed": user_confirmed,
        "password_value_logged": False,
        "password_hash_logged": False,
        "preflight": {
            "result": "PREFLIGHT_BLOCKED",
            "p0_blockers": sorted(set(blockers)),
            "read_only": True,
        },
        "blockers": sorted(set(blockers)),
        "allow_execute_final_gate": False,
        "write_result": None,
        "hash_algo_used": None,
        "n5_outbox_before": None,
        "n5_outbox_after": None,
        "n5_outbox_unchanged": None,
        "allowed_write_scope": {
            "user_account": 1,
            "user_filter_profile": 1,
            "user_session": 0,
            "user_projection_rows": 0,
            "user_notification_rows": 0,
            "user_sim_rows": 0,
        },
        "forbidden_scope": forbidden_scope(),
    }


def validate_password(password: str | None) -> list[str]:
    if password is None:
        return ["missing_password_source"]
    if not password:
        return ["empty_password"]
    blockers: list[str] = []
    if len(password) < 6:
        blockers.append("password_too_short")
    if password.lower() == DEFAULT_LOGIN_NAME:
        blockers.append("password_equals_login_name")
    return blockers


def hash_password(password: str) -> HashResult:
    try:
        from argon2 import PasswordHasher
        from argon2.low_level import Type
    except ImportError:
        try:
            import bcrypt
        except ImportError as exc:
            raise RuntimeError("argon2id and bcrypt are unavailable") from exc
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
        return HashResult(password_hash=hashed, password_hash_algo="bcrypt")
    hasher = PasswordHasher(type=Type.ID)
    return HashResult(password_hash=hasher.hash(password), password_hash_algo="argon2id")


def validate_post_write_result(
    write_result: dict[str, object],
    after_snapshot: PreflightSnapshot,
    before_n5_outbox: dict[str, int],
) -> list[str]:
    blockers: list[str] = []
    expected_writes = {
        "user_account_rows_inserted": 1,
        "user_filter_profile_rows_inserted": 1,
        "user_session_rows_inserted": 0,
        "user_projection_rows_inserted": 0,
        "user_notification_rows_inserted": 0,
        "user_sim_rows_inserted": 0,
    }
    for key, expected in expected_writes.items():
        if write_result.get(key) != expected:
            blockers.append(f"unexpected_{key}")
    if after_snapshot.n5_outbox_counts != before_n5_outbox:
        blockers.append("n5_outbox_changed_after_write")
    for table in OTHER_N6_BUSINESS_TABLES:
        if (after_snapshot.table_counts.get(table) or 0) != 0:
            blockers.append(f"unexpected_{table}_rows_after_write")
    return sorted(set(blockers))


def forbidden_scope() -> dict[str, bool]:
    return {
        "write_user_session": False,
        "write_user_projection_run": False,
        "write_user_signal_projection": False,
        "write_user_signal_card": False,
        "write_user_signal_decision": False,
        "write_user_notification_queue": False,
        "write_user_watchlist": False,
        "write_user_watchlist_item": False,
        "write_user_sim_tables": False,
        "consume_n5_outbox": False,
        "update_n5_outbox_status": False,
        "write_n1_to_n5": False,
        "start_worker": False,
        "actual_push": False,
        "real_trade": False,
    }


def resolve_password_for_execute(*, execute: bool, user_confirmed: bool) -> tuple[str | None, str]:
    if not execute or not user_confirmed:
        return None, "not_requested"
    env_password = os.environ.get(PASSWORD_ENV)
    if env_password is not None:
        return env_password, f"env:{PASSWORD_ENV}"
    if sys.stdin.isatty():
        return getpass.getpass("N6 initial admin password: "), "interactive_getpass"
    return None, "missing"


def write_json(path: str, report: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def format_markdown_report(report: dict[str, Any]) -> str:
    preflight = report.get("preflight") or {}
    lines = [
        "# N6 Admin Bootstrap Preflight",
        "",
        "## Summary",
        "",
        f"- result: {report.get('result')}",
        f"- preflight_result: {preflight.get('result')}",
        f"- layer_role: {report.get('layer_role')}",
        f"- execute: {str(report.get('execute')).lower()}",
        f"- user_confirmed: {str(report.get('user_confirmed')).lower()}",
        f"- blockers: {report.get('blockers') or []}",
        f"- password_value_logged: {str(report.get('password_value_logged')).lower()}",
        f"- password_hash_logged: {str(report.get('password_hash_logged')).lower()}",
        "",
        "## Boundary",
        "",
        "- admin_initialized: false unless result is EXECUTED",
        "- user_session_written: false",
        "- N5 outbox consumed: false",
        "- user projection rows written: false",
        "- notification rows written: false",
        "- sim rows written: false",
        "- worker_started: false",
        "- actual_push: false",
        "- real_trade: false",
        "",
        "## Preflight",
        "",
        f"- p0_blockers: {preflight.get('p0_blockers') or []}",
        f"- table_counts: {preflight.get('table_counts') or {}}",
        f"- n5_outbox_counts: {preflight.get('n5_outbox_counts') or {}}",
        f"- password_columns: {preflight.get('password_columns') or []}",
        f"- plaintext_password_columns: {preflight.get('plaintext_password_columns') or []}",
        "",
        "## Next Gate",
        "",
        "This artifact does not authorize admin bootstrap execution. It may support a separate admin bootstrap final gate.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password, password_source = resolve_password_for_execute(
        execute=args.execute,
        user_confirmed=args.user_confirmed,
    )
    report = run_admin_bootstrap(
        dsn=os.environ.get(DSN_ENV),
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        password=password,
        password_source=password_source,
    )
    write_json(args.json_report_path, report)
    write_text(args.markdown_report_path, format_markdown_report(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_cli_summary(report))
    return 0 if report.get("result") == "EXECUTED" else 2


def format_cli_summary(report: dict[str, Any]) -> str:
    preflight = report.get("preflight") or {}
    return "\n".join(
        [
            "N6 admin bootstrap",
            f"  result={report.get('result')}",
            f"  preflight_result={preflight.get('result')}",
            f"  execute={report.get('execute')} user_confirmed={report.get('user_confirmed')}",
            f"  blockers={report.get('blockers')}",
            "  password_value_logged=false password_hash_logged=false",
            "  writes: user_account<=1 user_filter_profile<=1 user_session=0 projection=0 notification=0 sim=0",
            "  n5_outbox_consumed=false worker_started=false actual_push=false real_trade=false",
        ]
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
