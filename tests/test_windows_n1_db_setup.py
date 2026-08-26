from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ashare_v3.ingestion.windows_n1_db_setup import (
    assert_fresh_authority, merge_pgpass, write_user_pgpass,
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
                environ={"USERNAME": "ashare-ops", "APPDATA": directory},
                run_command=lambda args, **kwargs: calls.append((args, kwargs)),
            )
            self.assertEqual(path, Path(directory) / "postgresql" / "pgpass.conf")
            self.assertIn("not-printed-secret", path.read_text(encoding="utf-8"))
            self.assertNotIn("not-printed-secret", repr(calls))
            self.assertFalse(path.with_name("pgpass.conf.windows_n1_tmp").exists())
            self.assertIn("/inheritance:r", calls[0][0])


if __name__ == "__main__": unittest.main()
