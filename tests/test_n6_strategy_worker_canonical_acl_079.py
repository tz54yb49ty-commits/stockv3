import contextlib
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/079_n6_strategy_worker_canonical_signal_acl.sql"
ROLLBACK = (
    ROOT / "sql/079_n6_strategy_worker_canonical_signal_acl_rollback.sql"
)
SCHEMA_073 = ROOT / "sql/073_n6_strategy_center_schema.sql"
POSTGRES_BIN_CANDIDATES = (
    Path("/opt/homebrew/opt/postgresql@16/bin"),
    Path("/opt/homebrew/Cellar/postgresql@16/16.14/bin"),
    Path("/usr/local/opt/postgresql@16/bin"),
)


def _postgres_binary(name: str) -> str | None:
    executable = shutil.which(name)
    if executable is not None:
        return executable
    for directory in POSTGRES_BIN_CANDIDATES:
        candidate = directory / name
        if candidate.is_file():
            return str(candidate)
    return None


class _TemporaryPostgres:
    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="n6_079_postgres_"
        )
        self.root = Path(self._temporary_directory.name)
        self.data = self.root / "data"
        self.socket_dir = self.root / "socket"
        self.socket_dir.mkdir()
        self.port = self._unused_port()
        self.binaries = {
            name: _postgres_binary(name)
            for name in ("initdb", "pg_ctl", "createdb", "psql")
        }
        missing = [name for name, value in self.binaries.items() if value is None]
        if missing:
            self._temporary_directory.cleanup()
            raise unittest.SkipTest(
                "temporary PostgreSQL binaries unavailable: "
                + ", ".join(missing)
            )
        self.started = False

    @staticmethod
    def _unused_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    def _run(
        self,
        arguments: list[str],
        *,
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            arguments,
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
            stderr=subprocess.PIPE if capture_output else subprocess.DEVNULL,
        )

    def start(self) -> None:
        self._run(
            [
                self.binaries["initdb"],
                "-D",
                str(self.data),
                "--username=cluster_admin",
                "--auth=trust",
                "--no-locale",
                "--encoding=UTF8",
            ],
            capture_output=False,
        )
        self._run(
            [
                self.binaries["pg_ctl"],
                "-D",
                str(self.data),
                "-o",
                (
                    "-F -c listen_addresses= "
                    f"-k {self.socket_dir} -p {self.port}"
                ),
                "-w",
                "start",
            ],
            capture_output=False,
        )
        self.started = True
        self.sql(
            "CREATE ROLE ashare_v3_user LOGIN NOINHERIT;",
            database="postgres",
            user="cluster_admin",
        )
        self.sql(
            "CREATE ROLE n6_strategy_worker LOGIN NOINHERIT;",
            database="postgres",
            user="cluster_admin",
        )
        self._run(
            [
                self.binaries["createdb"],
                "-h",
                str(self.socket_dir),
                "-p",
                str(self.port),
                "-U",
                "cluster_admin",
                "-O",
                "ashare_v3_user",
                "ashare_v3",
            ]
        )
        self.sql(
            """
            CREATE TABLE stock_condition_display_basis (id bigint);
            CREATE TABLE index_condition_display_basis (id bigint);
            CREATE TABLE board_condition_display_basis (id bigint);
            CREATE VIEW v_n6_stock_condition_display_basis AS
              SELECT * FROM stock_condition_display_basis;
            CREATE VIEW v_n6_index_condition_display_basis AS
              SELECT * FROM index_condition_display_basis;
            CREATE VIEW v_n6_board_condition_display_basis AS
              SELECT * FROM board_condition_display_basis;
            GRANT SELECT ON v_n6_stock_condition_display_basis
              TO n6_strategy_worker;
            """
        )

    def sql(
        self,
        sql: str,
        *,
        database: str = "ashare_v3",
        user: str = "ashare_v3_user",
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            [
                self.binaries["psql"],
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                str(self.socket_dir),
                "-p",
                str(self.port),
                "-U",
                user,
                "-d",
                database,
                "-c",
                sql,
            ],
            check=check,
        )

    def file(
        self, path: Path, *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            [
                self.binaries["psql"],
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                str(self.socket_dir),
                "-p",
                str(self.port),
                "-U",
                "ashare_v3_user",
                "-d",
                "ashare_v3",
                "-f",
                str(path),
            ],
            check=check,
        )

    def scalar(self, sql: str) -> str:
        result = self._run(
            [
                self.binaries["psql"],
                "-X",
                "-A",
                "-t",
                "-h",
                str(self.socket_dir),
                "-p",
                str(self.port),
                "-U",
                "ashare_v3_user",
                "-d",
                "ashare_v3",
                "-c",
                sql,
            ]
        )
        return result.stdout.strip()

    def stop(self) -> None:
        if self.started:
            self._run(
                [
                    self.binaries["pg_ctl"],
                    "-D",
                    str(self.data),
                    "-m",
                    "immediate",
                    "-w",
                    "stop",
                ],
                capture_output=False,
            )
            self.started = False
        self._temporary_directory.cleanup()


@contextlib.contextmanager
def _temporary_postgres():
    postgres = _TemporaryPostgres()
    try:
        postgres.start()
        yield postgres
    finally:
        postgres.stop()


class N6StrategyWorkerCanonicalAcl079Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")
        cls.schema_073 = SCHEMA_073.read_text(encoding="utf-8")

    def test_worker_has_three_channel_read_contract(self) -> None:
        self.assertIn(
            "public.v_n6_stock_condition_display_basis", self.schema_073
        )
        grant = re.search(
            r"GRANT SELECT ON TABLE\s+(.*?)\s+TO n6_strategy_worker;",
            self.migration,
            re.DOTALL,
        )
        self.assertIsNotNone(grant)
        self.assertEqual(
            {
                value.strip()
                for value in grant.group(1).split(",")
            },
            {
                "public.v_n6_index_condition_display_basis",
                "public.v_n6_board_condition_display_basis",
            },
        )

    def test_acl_is_select_only_and_public_is_not_granted(self) -> None:
        grant_statements = re.findall(
            r"\bGRANT\s+.*?;", self.migration, re.DOTALL | re.IGNORECASE
        )
        self.assertEqual(len(grant_statements), 1)
        self.assertRegex(grant_statements[0], r"^GRANT SELECT ON TABLE")
        self.assertNotIn("PUBLIC", grant_statements[0])
        for forbidden in (
            "GRANT INSERT",
            "GRANT UPDATE",
            "GRANT DELETE",
            "GRANT ALL",
            "ALL PRIVILEGES",
            "GRANT USAGE ON SCHEMA",
            "GRANT SELECT ON ALL TABLES",
        ):
            self.assertNotIn(forbidden, self.migration.upper())

    def test_no_upstream_or_trading_table_grant(self) -> None:
        grant = re.findall(
            r"\bGRANT\s+.*?;", self.migration, re.DOTALL | re.IGNORECASE
        )[0]
        for forbidden in (
            "public.stock_condition_display_basis",
            "public.index_condition_display_basis",
            "public.board_condition_display_basis",
            "public.n6_virtual_trade_proposal",
            "public.n6_virtual_order",
            "public.n6_virtual_trade",
            "public.n6_virtual_position",
            "public.n6_virtual_cash",
            "public.common_action",
            "public.common_trigger",
        ):
            self.assertNotIn(forbidden, grant)

    def test_preflight_freezes_owner_view_security_and_dependencies(self) -> None:
        for required in (
            "CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'",
            "SESSION_USER IS DISTINCT FROM 'ashare_v3_user'",
            "view_row.relkind <> 'v'",
            "security_invoker=true",
            "information_schema.view_table_usage",
            "already applied or partial ACL conflict",
            "INSERT,UPDATE,DELETE",
            "acl.grantee = 0",
        ):
            self.assertIn(required, self.migration)

    def test_plpgsql_variables_do_not_shadow_sql_columns(self) -> None:
        declared_names = set(
            re.findall(
                r"^\s{2}([a-z][a-z0-9_]*)\s+(?:text|integer|record);$",
                self.migration,
                re.MULTILINE,
            )
        )
        qualified_column_names = set(
            re.findall(
                r"\b(?:acl|dependency|expected|namespace|relation)\."
                r"([a-z][a-z0-9_]*)",
                self.migration,
            )
        )
        self.assertTrue(declared_names)
        self.assertFalse(declared_names & qualified_column_names)
        self.assertNotRegex(
            self.migration, r"^\s{2}(?:view_name|base_name)\s+text;$"
        )
        self.assertIn(
            "dependency.view_name = target_view_name", self.migration
        )
        self.assertIn(
            "dependency.table_name = target_base_name", self.migration
        )

    def test_rollback_revokes_only_migration_grants(self) -> None:
        revoke_statements = re.findall(
            r"^REVOKE\s+.*?;",
            self.rollback,
            re.DOTALL | re.IGNORECASE | re.MULTILINE,
        )
        self.assertEqual(len(revoke_statements), 1)
        revoke = revoke_statements[0]
        self.assertIn("REVOKE SELECT ON TABLE", revoke)
        self.assertIn("v_n6_index_condition_display_basis", revoke)
        self.assertIn("v_n6_board_condition_display_basis", revoke)
        self.assertNotIn("v_n6_stock_condition_display_basis", revoke)
        self.assertNotRegex(
            self.rollback.upper(), r"\b(DROP|DELETE|TRUNCATE|UPDATE|INSERT)\b"
        )


class N6StrategyWorkerCanonicalAcl079PostgresTest(unittest.TestCase):
    ACL_SNAPSHOT_SQL = """
        SELECT concat_ws('|',
          has_table_privilege(
            'n6_strategy_worker',
            'public.v_n6_stock_condition_display_basis', 'SELECT'
          ),
          has_table_privilege(
            'n6_strategy_worker',
            'public.v_n6_index_condition_display_basis', 'SELECT'
          ),
          has_table_privilege(
            'n6_strategy_worker',
            'public.v_n6_board_condition_display_basis', 'SELECT'
          ),
          has_table_privilege(
            'n6_strategy_worker',
            'public.v_n6_stock_condition_display_basis',
            'INSERT,UPDATE,DELETE'
          ),
          has_table_privilege(
            'n6_strategy_worker',
            'public.v_n6_index_condition_display_basis',
            'INSERT,UPDATE,DELETE'
          ),
          has_table_privilege(
            'n6_strategy_worker',
            'public.v_n6_board_condition_display_basis',
            'INSERT,UPDATE,DELETE'
          ),
          has_table_privilege(
            'n6_strategy_worker',
            'public.stock_condition_display_basis',
            'SELECT,INSERT,UPDATE,DELETE'
          ),
          has_table_privilege(
            'n6_strategy_worker',
            'public.index_condition_display_basis',
            'SELECT,INSERT,UPDATE,DELETE'
          ),
          has_table_privilege(
            'n6_strategy_worker',
            'public.board_condition_display_basis',
            'SELECT,INSERT,UPDATE,DELETE'
          ),
          (
            SELECT count(*)
            FROM pg_catalog.pg_class relation
            JOIN pg_catalog.pg_namespace namespace
              ON namespace.oid = relation.relnamespace
            CROSS JOIN LATERAL pg_catalog.aclexplode(
              COALESCE(
                relation.relacl,
                pg_catalog.acldefault('r', relation.relowner)
              )
            ) acl
            WHERE namespace.nspname = 'public'
              AND relation.relname IN (
                'v_n6_stock_condition_display_basis',
                'v_n6_index_condition_display_basis',
                'v_n6_board_condition_display_basis'
              )
              AND acl.grantee = 0
          )
        );
    """

    def test_forward_commit_and_rollback_restore_acl_matrix(self) -> None:
        with _temporary_postgres() as postgres:
            self.assertEqual(
                postgres.scalar(self.ACL_SNAPSHOT_SQL),
                "t|f|f|f|f|f|f|f|f|0",
            )
            postgres.file(MIGRATION)
            self.assertEqual(
                postgres.scalar(self.ACL_SNAPSHOT_SQL),
                "t|t|t|f|f|f|f|f|f|0",
            )
            postgres.file(ROLLBACK)
            self.assertEqual(
                postgres.scalar(self.ACL_SNAPSHOT_SQL),
                "t|f|f|f|f|f|f|f|f|0",
            )

    def test_preflight_failure_leaves_both_target_grants_absent(self) -> None:
        with _temporary_postgres() as postgres:
            postgres.sql(
                """
                CREATE OR REPLACE VIEW v_n6_index_condition_display_basis AS
                  SELECT * FROM stock_condition_display_basis;
                """
            )
            result = postgres.file(MIGRATION, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "079 canonical view dependency drift", result.stderr
            )
            self.assertEqual(
                postgres.scalar(self.ACL_SNAPSHOT_SQL),
                "t|f|f|f|f|f|f|f|f|0",
            )


if __name__ == "__main__":
    unittest.main()
