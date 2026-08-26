from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.run_local_artifact_archive_daily_once import (
    ArchiveBlocked,
    CURRENT_POINTER_NAME,
    next_cleanup_date,
    read_retained_trade_dates,
    run_local_artifact_archive_daily_once,
)


class _Cursor:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[str, ...] = ()

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[str, ...]) -> None:
        self.query = query
        self.params = params

    def fetchall(self) -> list[tuple[str]]:
        return self.rows


class _Connection:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self.cursor_value = _Cursor(rows)
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_value

    def close(self) -> None:
        self.closed = True


def _connection_factory(rows: list[tuple[str]], captured: dict[str, object]):
    def factory(dsn: str, **kwargs: object) -> _Connection:
        captured.update({"dsn": dsn, **kwargs})
        connection = _Connection(rows)
        captured["connection"] = connection
        return connection
    return factory


class LocalArtifactArchiveDailyTest(unittest.TestCase):
    def _make_source(self, root: Path) -> None:
        (root / "tmp").mkdir(parents=True)
        (root / "tmp" / "N3P_20260814_0931_trigger_proof_contract.json").write_text("n3p")

    def test_next_cleanup_date_uses_shanghai_calendar_day(self) -> None:
        now = datetime(2026, 8, 23, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(next_cleanup_date(now), "20260824")

    def test_calendar_read_is_read_only_and_keeps_cleanup_date(self) -> None:
        captured: dict[str, object] = {}
        result = read_retained_trade_dates(
            dsn="postgresql://example",
            for_cleanup_date="20260824",
            connection_factory=_connection_factory(
                [("20260821",), ("20260820",), ("20260819",), ("20260818",), ("20260817",)], captured
            ),
        )
        self.assertEqual(result, ["20260824", "20260817", "20260818", "20260819", "20260820", "20260821"])
        self.assertEqual(captured["options"], "-c default_transaction_read_only=on")
        connection = captured["connection"]
        assert isinstance(connection, _Connection)
        self.assertIn("trade_date < %s", connection.cursor_value.query)
        self.assertEqual(connection.cursor_value.params, ("20260824",))
        self.assertTrue(connection.closed)

    def test_verified_empty_or_nonempty_batch_publishes_exact_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, archive = root / "source", root / "archive"
            archive.mkdir()
            self._make_source(source)
            report = run_local_artifact_archive_daily_once(
                source_root=source,
                archive_base=archive,
                for_cleanup_date="20260824",
                execute=True,
                user_confirmed=True,
                writer_detector=lambda: [],
                connection_factory=_connection_factory(
                    [("20260821",), ("20260820",), ("20260819",), ("20260818",), ("20260817",)], {}
                ),
            )
            self.assertEqual(report["result"], "ARCHIVED_VERIFIED")
            pointer_path = archive / CURRENT_POINTER_NAME
            pointer = json.loads(pointer_path.read_text())
            self.assertEqual(pointer["schema_version"], "LocalArtifactArchiveCurrentPointer.v1")
            self.assertEqual(pointer["for_cleanup_date"], "20260824")
            self.assertEqual(pointer["entry_count"], 1)
            self.assertEqual(pointer["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(pointer["restore_proof_result"], "RESTORE_PROOF_PASS")
            for name in ("manifest", "summary", "allowlist", "restore_proof"):
                self.assertEqual(set(pointer[name]), {"path", "sha256"})
                evidence = Path(pointer[name]["path"])
                self.assertTrue(evidence.is_file())
                self.assertEqual(pointer[name]["sha256"], hashlib.sha256(evidence.read_bytes()).hexdigest())

    def test_verified_empty_batch_still_replaces_current_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, archive = root / "source", root / "archive"
            source.mkdir()
            archive.mkdir()
            old_pointer = archive / CURRENT_POINTER_NAME
            old_pointer.write_text('{"old":true}\n')
            report = run_local_artifact_archive_daily_once(
                source_root=source,
                archive_base=archive,
                for_cleanup_date="20260824",
                execute=True,
                user_confirmed=True,
                writer_detector=lambda: [],
                connection_factory=_connection_factory(
                    [("20260821",), ("20260820",), ("20260819",), ("20260818",), ("20260817",)], {}
                ),
            )
            self.assertEqual(report["result"], "ARCHIVED_VERIFIED")
            pointer = json.loads(old_pointer.read_text())
            self.assertEqual(pointer["entry_count"], 0)
            self.assertNotIn("old", pointer)

    def test_writer_failure_preserves_old_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, archive = root / "source", root / "archive"
            archive.mkdir()
            self._make_source(source)
            pointer_path = archive / CURRENT_POINTER_NAME
            pointer_path.write_text('{"old":true}\n')
            before = pointer_path.read_bytes()
            report = run_local_artifact_archive_daily_once(
                source_root=source,
                archive_base=archive,
                for_cleanup_date="20260824",
                execute=True,
                user_confirmed=True,
                writer_detector=lambda: [{"pid": 1}],
                connection_factory=lambda *_args, **_kwargs: self.fail("calendar must not be read"),
            )
            self.assertEqual(report["result"], "BLOCKED")
            self.assertEqual(pointer_path.read_bytes(), before)
            self.assertFalse((archive / "batch=local-artifact-archive-20260824").exists())

    def test_unsafe_archive_base_symlink_preserves_old_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, archive, archive_link = root / "source", root / "archive", root / "archive-link"
            source.mkdir()
            archive.mkdir()
            pointer_path = archive / CURRENT_POINTER_NAME
            pointer_path.write_text('{"old":true}\n')
            before = pointer_path.read_bytes()
            archive_link.symlink_to(archive, target_is_directory=True)
            archive_executor_called = False

            def archive_executor(**_kwargs: object) -> dict[str, object]:
                nonlocal archive_executor_called
                archive_executor_called = True
                return {}

            report = run_local_artifact_archive_daily_once(
                source_root=source,
                archive_base=archive_link,
                for_cleanup_date="20260824",
                execute=True,
                user_confirmed=True,
                writer_detector=lambda: [],
                connection_factory=_connection_factory(
                    [("20260821",), ("20260820",), ("20260819",), ("20260818",), ("20260817",)], {}
                ),
                archive_executor=archive_executor,
            )
            self.assertEqual(report["result"], "BLOCKED")
            self.assertIn("archive_base_missing_or_unsafe", report["blockers"])
            self.assertFalse(archive_executor_called)
            self.assertEqual(pointer_path.read_bytes(), before)

    def test_confirmation_is_required_before_any_archive_or_calendar_access(self) -> None:
        report = run_local_artifact_archive_daily_once(
            execute=False,
            user_confirmed=False,
            connection_factory=lambda *_args, **_kwargs: self.fail("calendar must not be read"),
            writer_detector=lambda: self.fail("writer detector must not run"),
        )
        self.assertEqual(report["result"], "BLOCKED_EXECUTE_CONFIRMATION_REQUIRED")
        self.assertEqual(report["source_mutation_count"], 0)
        self.assertEqual(report["database_writes"], 0)

    def test_source_identity_or_hash_drift_preserves_old_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, archive = root / "source", root / "archive"
            source.mkdir()
            archive.mkdir()
            pointer_path = archive / CURRENT_POINTER_NAME
            pointer_path.write_text('{"old":true}\n')
            before = pointer_path.read_bytes()
            report = run_local_artifact_archive_daily_once(
                source_root=source,
                archive_base=archive,
                for_cleanup_date="20260824",
                execute=True,
                user_confirmed=True,
                writer_detector=lambda: [],
                connection_factory=_connection_factory(
                    [("20260821",), ("20260820",), ("20260819",), ("20260818",), ("20260817",)], {}
                ),
                archive_executor=lambda **_kwargs: (_ for _ in ()).throw(
                    ArchiveBlocked("source_drift_after_copy:/source/tmp/N3P_20260814_0931_trigger_proof_contract.json")
                ),
            )
            self.assertEqual(report["result"], "BLOCKED")
            self.assertEqual(
                report["blockers"],
                ["source_drift_after_copy:/source/tmp/N3P_20260814_0931_trigger_proof_contract.json"],
            )
            self.assertEqual(pointer_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
