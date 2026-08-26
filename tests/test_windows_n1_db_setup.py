from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import inspect
import unittest

from ashare_v3.ingestion.windows_n1_db_setup import (
    ELEVATED_RUNTIME_PGPASS, OPERATOR_DIRECT, OPERATOR_ELEVATED,
    RecoveryAuthorityEvidence, WindowsIdentityEvidence, assert_fresh_authority, merge_pgpass,
    grant_minimum_n1_privileges, pgpass_path_for_mode, validate_operator_identity, verify_pgpass_acl,
    validate_recovery_authority, write_user_pgpass,
)
from ashare_v3.ingestion.windows_n1_postgres import FORBIDDEN_WRITE_TABLES, N1_WRITABLE_TABLES


class FakeCursor:
    def __init__(self, values): self.values = iter(values)
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, statement, params): pass
    def fetchone(self): return (next(self.values),)


class FakeConnection:
    def __init__(self, values): self.values = values
    def cursor(self): return FakeCursor(self.values)


class WindowsN1DatabaseSetupTest(unittest.TestCase):
    runtime_sid = "S-1-5-21-111-222-333-1006"
    direct_identity = WindowsIdentityEvidence(
        name=r"TDX-STOCK\ashare-ops", sid=runtime_sid,
        is_administrator=False, runtime_sid=runtime_sid,
    )
    elevated_identity = WindowsIdentityEvidence(
        name=r"TDX-STOCK\47894", sid="S-1-5-21-111-222-333-1002",
        is_administrator=True, runtime_sid=runtime_sid,
    )

    def test_fresh_authority_requires_database_and_role_absent(self):
        assert_fresh_authority(FakeConnection([False, False]))
        for state in ([True, False], [False, True], [True, True]):
            with self.assertRaisesRegex(RuntimeError, "refusing existing or partial state"):
                assert_fresh_authority(FakeConnection(state))

    def test_pgpass_merge_preserves_other_entries_and_replaces_target(self):
        existing = "host:5432:other:user:keep\n127.0.0.1:5432:ashare_v3:ashare_v3_user:old\n"
        merged = merge_pgpass(existing, password=r"new:secret\value")
        self.assertIn("host:5432:other:user:keep", merged)
        self.assertNotIn(":old", merged)
        self.assertIn(r"new\:secret\\value", merged)

    def test_pgpass_temp_write_and_acl_command_never_expose_password(self):
        calls = []
        with TemporaryDirectory() as directory:
            path = write_user_pgpass(
                password="not-printed-secret",
                identity=self.direct_identity,
                environ={"APPDATA": directory},
                run_command=lambda args, **kwargs: calls.append((args, kwargs)),
                acl_verifier=lambda *args, **kwargs: None,
            )
            self.assertEqual(path, Path(directory) / "postgresql" / "pgpass.conf")
            self.assertIn("not-printed-secret", path.read_text(encoding="utf-8"))
            self.assertNotIn("not-printed-secret", repr(calls))
            self.assertEqual(list(path.parent.glob("pgpass.conf.windows_n1_*.tmp")), [])
            self.assertIn("/inheritance:r", calls[0][0])
            self.assertIn(f"*{self.runtime_sid}:(R,W)", calls[1][0])
            self.assertEqual(calls[2][0][-1], f"*{self.runtime_sid}")

    def test_operator_modes_require_exact_windows_identity_and_sids(self):
        validate_operator_identity(OPERATOR_DIRECT, self.direct_identity)
        validate_operator_identity(OPERATOR_ELEVATED, self.elevated_identity)
        self.assertEqual(
            pgpass_path_for_mode(
                OPERATOR_ELEVATED, environment={}, identity=self.elevated_identity
            ),
            ELEVATED_RUNTIME_PGPASS,
        )
        with self.assertRaisesRegex(RuntimeError, "administrator"):
            validate_operator_identity(
                OPERATOR_ELEVATED,
                WindowsIdentityEvidence(
                    name=r"TDX-STOCK\47894", sid="S-1-5-21-111-222-333-1002",
                    is_administrator=False, runtime_sid=self.runtime_sid,
                ),
            )
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
            validate_operator_identity("unknown", self.direct_identity)

    def test_elevated_write_targets_runtime_profile_not_operator_profile(self):
        calls = []
        with TemporaryDirectory() as directory:
            # Replace the frozen Windows path only for this filesystem fake.
            import ashare_v3.ingestion.windows_n1_db_setup as module
            original = module.ELEVATED_RUNTIME_PGPASS
            module.ELEVATED_RUNTIME_PGPASS = Path(directory) / "runtime" / "pgpass.conf"
            try:
                path = write_user_pgpass(
                    password="memory-only-app-secret", operator_mode=OPERATOR_ELEVATED,
                    identity=self.elevated_identity, environ={"APPDATA": "operator-profile"},
                    run_command=lambda args, **kwargs: calls.append((args, kwargs)),
                    acl_verifier=lambda *args, **kwargs: None,
                )
            finally:
                module.ELEVATED_RUNTIME_PGPASS = original
            self.assertEqual(path, Path(directory) / "runtime" / "pgpass.conf")
            self.assertNotIn("operator-profile", str(path))
            self.assertNotIn("memory-only-app-secret", repr(calls))

    def test_acl_proof_allows_only_runtime_and_system(self):
        payload = (
            '{"owner":"' + self.runtime_sid + '","protected":true,"rules":['
            '{"sid":"' + self.runtime_sid + '","deny":false,"rights":131487},'
            '{"sid":"S-1-5-18","deny":false,"rights":2032127}]}'
        )
        verify_pgpass_acl(
            Path("pgpass.conf"), runtime_sid=self.runtime_sid,
            run_command=lambda *args, **kwargs: SimpleNamespace(stdout=payload),
        )

    def recovery_evidence(self, **overrides):
        tables = tuple(sorted(N1_WRITABLE_TABLES | FORBIDDEN_WRITE_TABLES))
        values = {
            "database_exists": True, "database_owner": "postgres",
            "database_size": 9116695, "role_exists": True, "role_login": True,
            "role_superuser": False, "role_createdb": False,
            "role_createrole": False, "role_replication": False,
            "public_tables": tables, "table_counts": {table: 0 for table in tables},
        }
        values.update(overrides)
        return RecoveryAuthorityEvidence(**values)

    def test_recovery_requires_exact_existing_empty_authority(self):
        validate_recovery_authority(self.recovery_evidence())
        invalid = (
            {"database_exists": False}, {"database_owner": "ashare_v3_user"},
            {"role_exists": False}, {"role_login": False},
            {"role_superuser": True},
            {"public_tables": tuple(sorted(N1_WRITABLE_TABLES))},
            {"table_counts": {**self.recovery_evidence().table_counts, "stock_identity": 1}},
        )
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(RuntimeError):
                validate_recovery_authority(self.recovery_evidence(**override))

    def test_permission_refreeze_revokes_tables_and_sequences_before_grant(self):
        source = inspect.getsource(grant_minimum_n1_privileges)
        self.assertLess(source.index("REVOKE ALL ON ALL TABLES"), source.index("GRANT SELECT ON"))
        self.assertLess(source.index("REVOKE ALL ON ALL SEQUENCES"), source.index("GRANT USAGE,SELECT ON ALL SEQUENCES"))

    def test_acl_failure_cleans_unique_temp_and_preserves_existing_pgpass(self):
        with TemporaryDirectory() as directory:
            import ashare_v3.ingestion.windows_n1_db_setup as module
            original = module.ELEVATED_RUNTIME_PGPASS
            target = Path(directory) / "runtime" / "pgpass.conf"
            target.parent.mkdir(parents=True)
            target.write_text("old-entry\n", encoding="utf-8")
            module.ELEVATED_RUNTIME_PGPASS = target
            try:
                with self.assertRaisesRegex(RuntimeError, "acl failed"):
                    write_user_pgpass(
                        password="new-memory-secret", operator_mode=OPERATOR_ELEVATED,
                        identity=self.elevated_identity, environ={},
                        run_command=lambda *args, **kwargs: None,
                        acl_verifier=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("acl failed")),
                    )
            finally:
                module.ELEVATED_RUNTIME_PGPASS = original
            self.assertEqual(target.read_text(encoding="utf-8"), "old-entry\n")
            self.assertEqual(list(target.parent.glob("pgpass.conf.windows_n1_*.tmp")), [])


if __name__ == "__main__": unittest.main()
