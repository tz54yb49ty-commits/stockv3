import hashlib
import json
import os
from datetime import date
from pathlib import Path
import stat
import tempfile
import unittest

from ashare_v3.ingestion.runtime_hot_cleanup import (
    DELETE_LOCK_TIMEOUT_MS,
    DELETE_STATEMENT_TIMEOUT_MS,
    INBOX_ID_BATCH_SIZE,
    build_runtime_hot_cleanup_plan_v2,
    discover_calendar_retained_trade_dates,
    discover_database_trade_dates,
    execute_runtime_hot_cleanup_database_v2,
    execute_frozen_inbox_units,
    freeze_inbox_delete_units,
    runtime_hot_cleanup_v2_specs,
)
from scripts.run_runtime_hot_keep5_cleanup_once import (
    KEEP5_CONFIRM_TOKEN,
    discover_local_artifact_files,
    execute_verified_local_allowlist,
    load_verified_local_archive_allowlist,
    run_runtime_hot_keep5_cleanup_once,
)


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)


class _CalendarConnection:
    def __init__(self, dates):
        self.dates = dates
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((str(sql), tuple(params or ())))
        return _Rows([(item,) for item in self.dates])


class _DateDomainConnection(_CalendarConnection):
    def execute(self, sql, params=None):
        self.calls.append((str(sql), tuple(params or ())))
        return _Rows([("20260812",)]) if "from stock_action_fact" in str(sql).lower() else _Rows([])


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _DeleteCursor:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _InboxConnection:
    def __init__(self, *, ids=None, error=None):
        self.ids = ids or []
        self.error = error
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def transaction(self):
        return _Transaction()

    def execute(self, sql, params=None):
        text = str(sql).lower()
        values = tuple(params or ())
        self.calls.append((text, values))
        if text.startswith("select i.inbox_id"):
            return _Rows([(item,) for item in self.ids])
        if text.startswith("set local"):
            return _DeleteCursor(0)
        if text.startswith("delete from common_event_inbox"):
            if self.error is not None:
                raise self.error
            return _DeleteCursor(len(values[0]))
        raise AssertionError(text)


def _manifest_for(source: Path, archive: Path, trade_date: str) -> dict:
    source_stat = source.stat()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return {
        "source_path": str(source),
        "trade_date": trade_date,
        "artifact_family": "runtime_date_directory",
        "source_device": source_stat.st_dev,
        "source_inode": source_stat.st_ino,
        "source_mode": stat.S_IMODE(source_stat.st_mode),
        "source_mtime_ns": source_stat.st_mtime_ns,
        "source_logical_bytes": source_stat.st_size,
        "source_allocated_bytes": source_stat.st_blocks * 512,
        "source_sha256": digest,
        "archive_path": str(archive),
        "archive_sha256": digest,
        "reference_classification": "runtime_artifact",
        "restore_proof_id": "restore-proof-1",
    }


def _write_verified_local_archive_evidence(
    *,
    root: Path,
    entry: dict,
    archive: Path,
    retained_trade_dates: list[str],
) -> dict[str, Path]:
    manifest = root / "manifest.jsonl"
    manifest_raw = (json.dumps(entry, sort_keys=True) + "\n").encode()
    manifest.write_bytes(manifest_raw)
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    allowlist = root / "exact_cleanup_allowlist.jsonl"
    allowlist_entry = {
        **entry,
        "manifest_sha256": manifest_sha256,
        "retained_date_overlap": 0,
        "active_current_lineage_overlap": 0,
        "source_identity_stable": True,
        "archive_fully_verified": True,
    }
    allowlist_raw = (json.dumps(allowlist_entry, sort_keys=True) + "\n").encode()
    allowlist.write_bytes(allowlist_raw)
    restore_proof = root / "restore_proof.json"
    restore_proof.write_text(json.dumps({
        "schema_version": "LocalArtifactIsolationRestoreProof.v1",
        "batch_id": "batch-1",
        "result": "RESTORE_PROOF_PASS",
        "families": {
            entry["artifact_family"]: {"restore_proof_id": entry["restore_proof_id"]},
        },
    }), encoding="utf-8")
    summary = root / "summary.json"
    summary.write_text(json.dumps({
        "schema_version": "LocalArtifactArchiveSummary.v1",
        "batch_id": "batch-1",
        "result": "ARCHIVED_VERIFIED",
        "ready_for_runtime_exact_reclaim": True,
        "manifest_path": str(manifest),
        "manifest_sha256": manifest_sha256,
        "allowlist_path": str(allowlist),
        "allowlist_sha256": hashlib.sha256(allowlist_raw).hexdigest(),
        "restore_proof_path": str(restore_proof),
        "restore_proof_sha256": hashlib.sha256(restore_proof.read_bytes()).hexdigest(),
        "entry_count": 1,
        "source_logical_bytes_total": entry["source_logical_bytes"],
        "source_allocated_bytes_total": entry["source_allocated_bytes"],
        "archive_logical_bytes_total": archive.stat().st_size,
        "source_archive_hash_equality_count": 1,
        "retained_trade_dates": retained_trade_dates,
        "restore_proof_result": "RESTORE_PROOF_PASS",
    }), encoding="utf-8")
    return {
        "manifest": manifest,
        "summary": summary,
        "allowlist": allowlist,
        "restore_proof": restore_proof,
    }


def _write_empty_verified_local_archive_evidence(
    *,
    root: Path,
    retained_trade_dates: list[str],
) -> dict[str, Path]:
    manifest = root / "manifest.jsonl"
    manifest.write_bytes(b"")
    allowlist = root / "exact_cleanup_allowlist.jsonl"
    allowlist.write_bytes(b"")
    restore_proof = root / "restore_proof.json"
    restore_proof.write_text(json.dumps({
        "schema_version": "LocalArtifactIsolationRestoreProof.v1",
        "batch_id": "batch-1",
        "result": "RESTORE_PROOF_PASS",
        "families": {},
    }), encoding="utf-8")
    summary = root / "summary.json"
    summary.write_text(json.dumps({
        "schema_version": "LocalArtifactArchiveSummary.v1",
        "batch_id": "batch-1",
        "result": "ARCHIVED_VERIFIED",
        "ready_for_runtime_exact_reclaim": True,
        "manifest_path": str(manifest),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "allowlist_path": str(allowlist),
        "allowlist_sha256": hashlib.sha256(allowlist.read_bytes()).hexdigest(),
        "restore_proof_path": str(restore_proof),
        "restore_proof_sha256": hashlib.sha256(restore_proof.read_bytes()).hexdigest(),
        "entry_count": 0,
        "source_logical_bytes_total": 0,
        "source_allocated_bytes_total": 0,
        "archive_logical_bytes_total": 0,
        "source_archive_hash_equality_count": 0,
        "retained_trade_dates": retained_trade_dates,
        "restore_proof_result": "RESTORE_PROOF_PASS",
    }), encoding="utf-8")
    return {
        "manifest": manifest,
        "summary": summary,
        "allowlist": allowlist,
        "restore_proof": restore_proof,
    }


def _write_current_pointer(
    *,
    archive_root: Path,
    evidence: dict[str, Path],
    retained_trade_dates: list[str],
    cleanup_date: str,
    entry_count: int,
) -> Path:
    pointer = archive_root / "current_verified_batch.json"
    payload = {
        "schema_version": "LocalArtifactArchiveCurrentPointer.v1",
        "for_cleanup_date": cleanup_date,
        "batch_id": "batch-1",
        "retained_trade_dates": retained_trade_dates,
        "entry_count": entry_count,
        "result": "ARCHIVED_VERIFIED",
        "restore_proof_result": "RESTORE_PROOF_PASS",
    }
    for field, path in evidence.items():
        payload[field] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    pointer.write_text(json.dumps(payload), encoding="utf-8")
    return pointer


class RuntimeHotCleanupV2Test(unittest.TestCase):
    def test_calendar_retains_current_plus_previous_five_completed_dates(self):
        conn = _CalendarConnection(["20260820", "20260819", "20260818", "20260817", "20260814"])
        retained = discover_calendar_retained_trade_dates(
            current_trade_date="20260821", connection_factory=lambda _dsn: conn
        )
        self.assertEqual(
            retained,
            ["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"],
        )
        self.assertIn("common_trade_calendar", conn.calls[0][0])
        self.assertIn("trade_date < %s", conn.calls[0][0])

    def test_db_and_local_dates_are_independent_and_retained_dates_are_excluded(self):
        plan = build_runtime_hot_cleanup_plan_v2(
            current_trade_date="20260821",
            retained_trade_dates=["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"],
            database_trade_dates=["20260812", "20260814", "20260821"],
            local_files=[
                {"source_path": "/tmp/a", "trade_date": "20260811", "artifact_family": "runtime_date_directory"},
                {"source_path": "/tmp/b", "trade_date": "20260820", "artifact_family": "runtime_date_directory"},
            ],
            inbox_delete_units=[],
            table_counter=lambda _spec, _trade_date: 0,
        )
        self.assertEqual(plan.database_cleanup_trade_dates, ("20260812",))
        self.assertEqual(plan.local_cleanup_trade_dates, ("20260811",))
        self.assertEqual(
            plan.as_dict()["blocked_by_layer"],
            [{"scope": "n6_user_projection", "layer_role": "N6_user"}],
        )
        tables = {spec.table for spec in runtime_hot_cleanup_v2_specs()}
        self.assertNotIn("user_projection_run", tables)
        self.assertFalse(any("action_confirmation_projection_metric" in table for table in tables))
        self.assertFalse(any("previous_day_minute_cumulative" in table for table in tables))

    def test_future_database_date_is_protected_and_never_reaches_deleter(self):
        counter_dates: list[str] = []
        delete_calls: list[str] = []
        plan = build_runtime_hot_cleanup_plan_v2(
            current_trade_date="20260823",
            retained_trade_dates=["20260817", "20260818", "20260819", "20260820", "20260821", "20260823"],
            database_trade_dates=["20260817", "20260824"],
            local_files=[],
            inbox_delete_units=[],
            table_counter=lambda _spec, trade_date: counter_dates.append(trade_date) or 0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = execute_runtime_hot_cleanup_database_v2(
                plan=plan,
                progress_journal_path=Path(tmp) / "progress.jsonl",
                table_deleter=lambda _spec, trade_date: delete_calls.append(trade_date) or 0,
            )
        self.assertEqual(plan.database_protected_future_trade_dates, ("20260824",))
        self.assertEqual(plan.database_cleanup_trade_dates, ())
        self.assertEqual(counter_dates, [])
        self.assertEqual(delete_calls, [])
        self.assertEqual(result["committed_unit_count"], 0)

    def test_database_date_discovery_finds_fact_date_missing_from_driver_tables(self):
        conn = _DateDomainConnection([])
        dates = discover_database_trade_dates(connection_factory=lambda _dsn: conn)
        self.assertEqual(dates, ["20260812"])
        sql_text = "\n".join(sql for sql, _params in conn.calls).lower()
        self.assertIn("from stock_action_fact", sql_text)
        self.assertNotIn("stock_previous_day_minute_cumulative", sql_text)
        self.assertNotIn("action_confirmation_projection_metric", sql_text)

    def test_inbox_ids_are_frozen_in_50_50_n_units(self):
        ids = list(range(1, 124))
        conn = _InboxConnection(ids=ids)
        units = freeze_inbox_delete_units(
            cleanup_trade_dates=["20260812"], connection_factory=lambda _dsn: conn
        )
        n3_units = [unit for unit in units if unit["layer"] == "n4"]
        self.assertEqual(INBOX_ID_BATCH_SIZE, 50)
        self.assertEqual([unit["planned_rows"] for unit in n3_units], [50, 50, 23])
        self.assertEqual(n3_units[0]["inbox_ids"], ids[:50])

    def test_each_inbox_unit_commits_to_durable_journal_and_timeout_never_retries(self):
        units = [
            {"unit_id": "u1", "trade_date": "20260812", "layer": "n4", "table": "common_event_inbox", "inbox_ids": list(range(1, 51)), "planned_rows": 50},
            {"unit_id": "u2", "trade_date": "20260812", "layer": "n4", "table": "common_event_inbox", "inbox_ids": list(range(51, 101)), "planned_rows": 50},
            {"unit_id": "u3", "trade_date": "20260812", "layer": "n4", "table": "common_event_inbox", "inbox_ids": [101], "planned_rows": 1},
        ]
        connections = [_InboxConnection(), _InboxConnection(error=TimeoutError("statement timeout"))]
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "progress.jsonl"
            result = execute_frozen_inbox_units(
                units=units,
                progress_journal_path=journal,
                connection_factory=lambda _dsn: connections.pop(0),
            )
            journal_rows = [json.loads(line) for line in journal.read_text().splitlines()]
        self.assertEqual(result["result"], "BLOCKED_DATABASE_DELETE_TIMEOUT")
        self.assertEqual(result["retry_attempts"], 0)
        self.assertEqual(result["attempted_units"], 2)
        self.assertEqual(result["committed_unit_count"], 1)
        self.assertFalse(result["rollback_claimed"])
        self.assertEqual([row["unit_id"] for row in journal_rows], ["u1"])
        first_calls = connections  # all supplied connections were consumed exactly once
        self.assertEqual(first_calls, [])
        self.assertEqual(DELETE_LOCK_TIMEOUT_MS, 1_000)
        self.assertEqual(DELETE_STATEMENT_TIMEOUT_MS, 30_000)

    def test_archive_manifest_exact_allowlist_and_active_path_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docs/runtime/20260812/n3_daily/payload.json"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"payload")
            archive_root = root / "archive"
            archive = archive_root / "20260812/payload.json"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(source.read_bytes())
            discovered = discover_local_artifact_files(project_root=root, current_date=date(2026, 8, 21))
            source = source.resolve()
            archive = archive.resolve()
            entry = _manifest_for(source, archive, "20260812")
            evidence = _write_verified_local_archive_evidence(
                root=root,
                entry=entry,
                archive=archive,
                retained_trade_dates=["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"],
            )
            entries, blockers = load_verified_local_archive_allowlist(
                manifest_path=evidence["manifest"],
                batch_summary_path=evidence["summary"],
                allowlist_path=evidence["allowlist"],
                restore_proof_path=evidence["restore_proof"],
                discovered_cleanup_files=discovered,
                retained_trade_dates=["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"],
                archive_root=archive_root,
            )
            self.assertEqual(blockers, [])
            blocked = execute_verified_local_allowlist(entries=entries, active_paths=[source])
            self.assertEqual(blocked["result"], "BLOCKED_LOCAL_ARCHIVE_VERIFIED_RECLAIM")
            self.assertTrue(source.exists())
            passed = execute_verified_local_allowlist(entries=entries)
            self.assertEqual(passed["result"], "LOCAL_ARCHIVE_VERIFIED_RECLAIM_PASS")
            self.assertFalse(source.exists())

    def test_current_pointer_local_only_reclaims_exact_file_without_database_calls(self):
        retained = ["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docs/runtime/20260811/n4_daily/payload.json"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"local-proof")
            archive_root = root / "archive"
            batch_root = archive_root / "batch=batch-1"
            archive = batch_root / "files/payload.json"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(source.read_bytes())
            entry = _manifest_for(source.resolve(), archive.resolve(), "20260811")
            evidence = _write_verified_local_archive_evidence(
                root=batch_root,
                entry=entry,
                archive=archive,
                retained_trade_dates=retained,
            )
            pointer = _write_current_pointer(
                archive_root=archive_root,
                evidence=evidence,
                retained_trade_dates=retained,
                cleanup_date="20260821",
                entry_count=1,
            )
            delete_calls: list[str] = []
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=root / "reports",
                local_artifact_project_root=root,
                local_artifact_current_date=date(2026, 8, 21),
                local_archive_current_pointer_path=pointer,
                local_archive_root=archive_root,
                local_only=True,
                trade_dates=retained,
                table_deleter=lambda spec, _trade_date: delete_calls.append(spec.table) or 0,
                runtime_writer_process_detector=lambda: [],
                execute=True,
                confirm_token=KEEP5_CONFIRM_TOKEN,
            )
        self.assertEqual(report["result"], "RUNTIME_HOT_CLEANUP_V2_EXECUTE_PASS")
        self.assertEqual(report["database_cleanup"]["result"], "DATABASE_CLEANUP_NOT_RUN_LOCAL_ONLY")
        self.assertEqual(report["database_cleanup_mode"], "disabled_by_layer_policy")
        self.assertEqual(report["local_archive_pointer"]["batch_id"], "batch-1")
        self.assertEqual(delete_calls, [])
        self.assertFalse(source.exists())
        self.assertEqual(report["deleted_active_lineage_count"], 0)

    def test_empty_verified_current_pointer_local_only_passes(self):
        retained = ["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_root = root / "archive"
            batch_root = archive_root / "batch=batch-1"
            batch_root.mkdir(parents=True)
            evidence = _write_empty_verified_local_archive_evidence(
                root=batch_root,
                retained_trade_dates=retained,
            )
            pointer = _write_current_pointer(
                archive_root=archive_root,
                evidence=evidence,
                retained_trade_dates=retained,
                cleanup_date="20260821",
                entry_count=0,
            )
            delete_calls: list[str] = []
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=root / "reports",
                local_artifact_project_root=root,
                local_artifact_current_date=date(2026, 8, 21),
                local_archive_current_pointer_path=pointer,
                local_archive_root=archive_root,
                local_only=True,
                trade_dates=retained,
                table_deleter=lambda spec, _trade_date: delete_calls.append(spec.table) or 0,
                runtime_writer_process_detector=lambda: [],
                execute=True,
                confirm_token=KEEP5_CONFIRM_TOKEN,
            )
        self.assertEqual(report["result"], "RUNTIME_HOT_CLEANUP_V2_EXECUTE_PASS")
        self.assertEqual(report["local_file_cleanup"]["removed_paths"], [])
        self.assertEqual(report["local_archive_pointer"]["entry_count"], 0)
        self.assertEqual(delete_calls, [])

    def test_pointer_date_sha_symlink_and_partial_allowlist_fail_closed(self):
        retained = ["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"]
        for drift in ("stale_date", "sha", "path_escape", "symlink", "partial_allowlist"):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "docs/runtime/20260811/n4_daily/payload.json"
                source.parent.mkdir(parents=True)
                source.write_bytes(b"must-remain")
                archive_root = root / "archive"
                batch_root = archive_root / "batch=batch-1"
                batch_root.mkdir(parents=True)
                evidence = _write_empty_verified_local_archive_evidence(
                    root=batch_root,
                    retained_trade_dates=retained,
                )
                pointer = _write_current_pointer(
                    archive_root=archive_root,
                    evidence=evidence,
                    retained_trade_dates=retained,
                    cleanup_date="20260821",
                    entry_count=0,
                )
                payload = json.loads(pointer.read_text(encoding="utf-8"))
                if drift == "stale_date":
                    payload["for_cleanup_date"] = "20260820"
                    pointer.write_text(json.dumps(payload), encoding="utf-8")
                elif drift == "sha":
                    payload["manifest"]["sha256"] = "0" * 64
                    pointer.write_text(json.dumps(payload), encoding="utf-8")
                elif drift == "path_escape":
                    outside = root / "outside-manifest.jsonl"
                    outside.write_bytes(evidence["manifest"].read_bytes())
                    payload["manifest"] = {
                        "path": str(outside),
                        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    }
                    pointer.write_text(json.dumps(payload), encoding="utf-8")
                elif drift == "symlink":
                    target = archive_root / "pointer-target.json"
                    target.write_text(json.dumps(payload), encoding="utf-8")
                    pointer.unlink()
                    pointer.symlink_to(target)
                report = run_runtime_hot_keep5_cleanup_once(
                    report_dir=root / "reports",
                    local_artifact_project_root=root,
                    local_artifact_current_date=date(2026, 8, 21),
                    local_archive_current_pointer_path=pointer,
                    local_archive_root=archive_root,
                    local_only=True,
                    trade_dates=retained,
                    runtime_writer_process_detector=lambda: [],
                    execute=True,
                    confirm_token=KEEP5_CONFIRM_TOKEN,
                )
                self.assertEqual(report["result"], "RUNTIME_HOT_CLEANUP_V2_EXECUTE_BLOCKED")
                self.assertTrue(source.exists())
                self.assertFalse(report["cleanup_executed"])
                self.assertFalse(any(report["side_effects"].values()))

    def test_current_pointer_and_legacy_evidence_cannot_be_mixed(self):
        retained = ["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_root = root / "archive"
            batch_root = archive_root / "batch=batch-1"
            batch_root.mkdir(parents=True)
            evidence = _write_empty_verified_local_archive_evidence(
                root=batch_root,
                retained_trade_dates=retained,
            )
            pointer = _write_current_pointer(
                archive_root=archive_root,
                evidence=evidence,
                retained_trade_dates=retained,
                cleanup_date="20260821",
                entry_count=0,
            )
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=root / "reports",
                local_artifact_project_root=root,
                local_artifact_current_date=date(2026, 8, 21),
                local_archive_current_pointer_path=pointer,
                local_archive_manifest_path=evidence["manifest"],
                local_archive_root=archive_root,
                local_only=True,
                trade_dates=retained,
                runtime_writer_process_detector=lambda: [],
                execute=True,
                confirm_token=KEEP5_CONFIRM_TOKEN,
            )
        self.assertEqual(report["result"], "RUNTIME_HOT_CLEANUP_V2_EXECUTE_BLOCKED")
        self.assertEqual(report["local_archive_blockers"], ["local_archive_input_mode_conflict"])
        self.assertFalse(report["cleanup_executed"])
        self.assertFalse(any(report["side_effects"].values()))

    def test_direct_delete_mode_is_rejected_without_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=Path(tmp) / "reports", direct_delete_no_archive=True, execute=True
            )
        self.assertEqual(report["result"], "BLOCKED_DIRECT_DELETE_NO_ARCHIVE_REJECTED")
        self.assertEqual(report["archive_mode"], "verified-archive-required")
        self.assertFalse(report["cleanup_executed"])
        self.assertFalse(any(report["side_effects"].values()))

    def test_database_timeout_does_not_block_archive_verified_local_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docs/runtime/20260811/n4_daily/payload.json"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"local-proof")
            archive_root = root / "archive"
            archive = archive_root / "20260811/payload.json"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(source.read_bytes())
            source = source.resolve()
            archive = archive.resolve()
            entry = _manifest_for(source, archive, "20260811")
            evidence = _write_verified_local_archive_evidence(
                root=root,
                entry=entry,
                archive=archive,
                retained_trade_dates=["20260814", "20260817", "20260818", "20260819", "20260820", "20260821"],
            )
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=root / "reports",
                local_artifact_project_root=root,
                local_artifact_current_date=date(2026, 8, 21),
                local_archive_manifest_path=evidence["manifest"],
                local_archive_batch_summary_path=evidence["summary"],
                local_archive_allowlist_path=evidence["allowlist"],
                local_archive_restore_proof_path=evidence["restore_proof"],
                local_archive_root=archive_root,
                trade_dates=["20260812", "20260814", "20260817", "20260818", "20260819", "20260820", "20260821"],
                table_counter=lambda _spec, _trade_date: 1,
                table_deleter=lambda _spec, _trade_date: (_ for _ in ()).throw(TimeoutError("statement timeout")),
                runtime_writer_process_detector=lambda: [],
                execute=True,
                confirm_token=KEEP5_CONFIRM_TOKEN,
            )
        self.assertEqual(report["result"], "RUNTIME_HOT_CLEANUP_V2_EXECUTE_PARTIAL")
        self.assertEqual(report["database_cleanup"]["result"], "BLOCKED_DATABASE_DELETE_TIMEOUT")
        self.assertEqual(report["database_cleanup"]["retry_attempts"], 0)
        self.assertEqual(report["local_file_cleanup"]["result"], "LOCAL_ARCHIVE_VERIFIED_RECLAIM_PASS")
        self.assertFalse(source.exists())
        self.assertFalse(report["rollback_claimed"])

    def test_plan_only_blocks_when_verified_archive_evidence_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "docs/runtime/20260812/n3_daily/payload.json"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"payload")
            delete_calls: list[str] = []
            report = run_runtime_hot_keep5_cleanup_once(
                report_dir=root / "reports",
                local_artifact_project_root=root,
                local_artifact_current_date=date(2026, 8, 21),
                trade_dates=["20260812", "20260814", "20260817", "20260818", "20260819", "20260820", "20260821"],
                table_counter=lambda _spec, _trade_date: 0,
                table_deleter=lambda spec, _trade_date: delete_calls.append(spec.table) or 0,
                runtime_writer_process_detector=lambda: [],
                execute=True,
            )

        self.assertEqual(report["result"], "RUNTIME_HOT_CLEANUP_V2_EXECUTE_BLOCKED")
        self.assertIn("verified_local_archive_evidence_required", report["local_archive_blockers"])
        self.assertFalse(report["cleanup_executed"])
        self.assertEqual(delete_calls, [])
        self.assertFalse(any(report["side_effects"].values()))


if __name__ == "__main__":
    unittest.main()
