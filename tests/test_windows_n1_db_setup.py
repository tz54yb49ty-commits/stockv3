from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from ashare_v3.ingestion.windows_n1_db_setup import (
    ELEVATED_RUNTIME_PGPASS, OPERATOR_DIRECT, OPERATOR_ELEVATED,
    WindowsIdentityEvidence, assert_fresh_authority, merge_pgpass,
    pgpass_path_for_mode, validate_operator_identity, verify_pgpass_acl,
    write_user_pgpass,
)


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
            self.assertFalse(path.with_name("pgpass.conf.windows_n1_tmp").exists())
            self.assertIn("/inheritance:r", calls[0][0])
            self.assertIn(r"TDX-STOCK\ashare-ops:(R,W)", calls[0][0])

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


if __name__ == "__main__": unittest.main()
