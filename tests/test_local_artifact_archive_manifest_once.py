from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.run_local_artifact_archive_manifest_once import (
    ArchiveBlocked,
    discover_candidates,
    execute_archive,
    execute_manifest_supersession,
)
from scripts.run_runtime_hot_keep5_cleanup_once import discover_local_artifact_files


RETAINED = ["20260821", "20260820", "20260819", "20260818", "20260817", "20260814"]
EVIDENCE_SHA = "a" * 64


class LocalArtifactArchiveManifestTest(unittest.TestCase):
    def make_source(self, root: Path) -> None:
        (root / "tmp").mkdir(parents=True)
        intraday = root / "tmp" / "N5_N3T_action_confirmation_fastlane_monitor" / "20260626"
        post_close = root / "docs" / "runtime" / "20260701" / "n3_post_close_fastlane"
        runtime = root / "docs" / "runtime" / "20260701" / "n3_daily"
        intraday.mkdir(parents=True)
        post_close.mkdir(parents=True)
        runtime.mkdir(parents=True)
        (root / "tmp" / "N3P_20260701_0931_trigger_proof_contract.json").write_text("n3p")
        (intraday / "N3P_live_report.md").write_text("intraday")
        (intraday / "N4_do_not_read.md").write_text("n4")
        (post_close / "20_n1_report.json").write_text("n1")
        (post_close / "40_n3_report.json").write_text("n3")
        (post_close / "52_n4_report.json").write_text("n4")
        (runtime / "payload.json").write_text("runtime")

    def test_discovery_is_exact_and_excludes_other_layers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            candidates, blockers, skipped = discover_candidates(source, set(RETAINED), "20260821")
            self.assertEqual(blockers, [])
            candidates, blockers, skipped = discover_candidates(source, set(RETAINED), "20260821")
            cleanup_inventory = discover_local_artifact_files(
                project_root=source, current_date=date(2026, 8, 21)
            )
            self.assertEqual(blockers, [])
            self.assertEqual(len(candidates), 7)
            self.assertEqual({item.family for item in candidates}, {
                "n3p_trigger_proof_contract", "intraday_live_current", "post_close_fastlane", "runtime_date_directory"
            })
            self.assertEqual(
                {(str(item.source_path), item.trade_date, item.family) for item in candidates},
                {
                    (item["source_path"], item["trade_date"], item["artifact_family"])
                    for item in cleanup_inventory if item["trade_date"] not in RETAINED
                },
            )
            self.assertEqual(sum(skipped.values()), 0)
            self.assertTrue(any("N4" in str(item.source_path) or "52_n4" in str(item.source_path) for item in candidates))

    def test_retained_files_are_not_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            retained = source / "tmp" / "N3P_20260820_0931_trigger_proof_contract.json"
            retained.write_text("retained")
            candidates, blockers, skipped = discover_candidates(source, set(RETAINED), "20260821")
            self.assertEqual(blockers, [])
            self.assertNotIn(retained, {item.source_path for item in candidates})
            self.assertEqual(skipped["n3p_trigger_proof_contract"], 1)

    def test_scope_drift_in_artifact_family_blocks_allowlist_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            archive = root / "archive"
            archive.mkdir()
            self.make_source(source)
            summary = execute_archive(
                source_root=source, archive_base=archive, batch_id="scope-drift",
                retained_dates=RETAINED, current_date="20260821", quiesce_evidence_sha256=EVIDENCE_SHA,
            )
            from scripts.run_runtime_hot_keep5_cleanup_once import load_verified_local_archive_allowlist

            discovered = [json.loads(line) for line in Path(summary["manifest_path"]).read_text().splitlines()]
            discovered[0]["artifact_family"] = "post_close_fastlane"
            _entries, blockers = load_verified_local_archive_allowlist(
                manifest_path=summary["manifest_path"], batch_summary_path=summary["summary_path"],
                allowlist_path=summary["allowlist_path"], restore_proof_path=summary["restore_proof_path"],
                discovered_cleanup_files=discovered, retained_trade_dates=RETAINED, archive_root=archive,
            )
            self.assertIn("local_archive_exact_allowlist_mismatch", blockers)

    def test_symlink_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            self.make_source(source)
            target = source / "target.json"
            target.write_text("target")
            (source / "tmp" / "N3P_20260702_0931_trigger_proof_contract.json").symlink_to(target)
            candidates, blockers, _ = discover_candidates(source, set(RETAINED), "20260821")
            self.assertEqual(candidates, [])
            self.assertTrue(any(value.startswith("runtime_cleanup_discovery_not_closed:") for value in blockers))

    def test_execute_copies_hashes_and_proves_restore_without_source_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            archive = root / "archive"
            archive.mkdir()
            self.make_source(source)
            source_hashes = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source.rglob("*") if path.is_file()
            }
            summary = execute_archive(
                source_root=source,
                archive_base=archive,
                batch_id="test-batch",
                retained_dates=RETAINED,
                current_date="20260821",
                quiesce_evidence_sha256=EVIDENCE_SHA,
            )
            self.assertEqual(summary["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(summary["restore_proof_result"], "RESTORE_PROOF_PASS")
            self.assertFalse(summary["cleanup_eligible"])
            self.assertTrue(summary["ready_for_runtime_exact_reclaim"])
            self.assertEqual(summary["source_mutation_count"], 0)
            self.assertEqual(summary["entry_count"], 7)
            self.assertEqual(source_hashes, {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source.rglob("*") if path.is_file()
            })
            manifest_lines = Path(summary["manifest_path"]).read_text().splitlines()
            self.assertEqual(len(manifest_lines), 7)
            for line in manifest_lines:
                entry = json.loads(line)
                self.assertEqual(entry["source_sha256"], entry["archive_sha256"])
                self.assertIn("source_logical_bytes", entry)
                self.assertIn("source_allocated_bytes", entry)
                self.assertNotIn("logical_bytes", entry)
                self.assertNotIn("allocated_bytes", entry)
                self.assertTrue(Path(entry["archive_path"]).is_file())
            proof = json.loads(Path(summary["restore_proof_path"]).read_text())
            self.assertEqual(proof["result"], "RESTORE_PROOF_PASS")
            self.assertTrue(all(value["status"] == "RESTORE_PROOF_PASS" for value in proof["families"].values()))

    def test_reused_batch_and_invalid_retained_set_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            archive = root / "archive"
            archive.mkdir()
            self.make_source(source)
            execute_archive(
                source_root=source, archive_base=archive, batch_id="once",
                retained_dates=RETAINED, current_date="20260821",
                quiesce_evidence_sha256=EVIDENCE_SHA,
            )
            with self.assertRaises(FileExistsError):
                execute_archive(
                    source_root=source, archive_base=archive, batch_id="once",
                    retained_dates=RETAINED, current_date="20260821",
                    quiesce_evidence_sha256=EVIDENCE_SHA,
                )
            with self.assertRaises(ArchiveBlocked):
                execute_archive(
                    source_root=source, archive_base=archive, batch_id="bad-retained",
                    retained_dates=RETAINED[:-1], current_date="20260821",
                    quiesce_evidence_sha256=EVIDENCE_SHA,
                )

    def test_manifest_supersession_uses_exact_kernel_fields_and_preserves_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            archive = root / "archive"
            archive.mkdir()
            self.make_source(source)
            old_summary = execute_archive(
                source_root=source, archive_base=archive, batch_id="payload-v1",
                retained_dates=RETAINED, current_date="20260821",
                quiesce_evidence_sha256=EVIDENCE_SHA,
            )
            old_manifest = Path(old_summary["manifest_path"])
            legacy_entries = []
            for line in old_manifest.read_text().splitlines():
                entry = json.loads(line)
                entry["logical_bytes"] = entry.pop("source_logical_bytes")
                entry["allocated_bytes"] = entry.pop("source_allocated_bytes")
                legacy_entries.append(entry)
            old_manifest.chmod(0o644)
            old_manifest.write_bytes(b"".join(
                (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode()
                for entry in legacy_entries
            ))
            old_manifest.chmod(0o444)
            old_manifest_sha = hashlib.sha256(old_manifest.read_bytes()).hexdigest()
            old_manifest_stat = old_manifest.stat()
            source_hashes = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source.rglob("*") if path.is_file()
            }
            evidence = root / "phase_evidence.json"
            evidence.write_text("{}\n")
            evidence_sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
            sidecar = root / "phase_evidence.json.sha256"
            sidecar.write_text(f"{evidence_sha}  phase_evidence.json\n")
            sidecar_sha = hashlib.sha256(sidecar.read_bytes()).hexdigest()

            summary = execute_manifest_supersession(
                source_root=source,
                archive_base=archive,
                batch_id="manifest-v2",
                archive_payload_batch_id="payload-v1",
                supersedes_batch_root=archive / "batch=payload-v1",
                supersedes_manifest_sha256=old_manifest_sha,
                retained_dates=RETAINED,
                current_date="20260821",
                quiesce_evidence_path=evidence,
                quiesce_evidence_sha256=evidence_sha,
                quiesce_sidecar_path=sidecar,
                quiesce_sidecar_sha256=sidecar_sha,
                expected_entry_count=7,
            )
            self.assertEqual(summary["result"], "ARCHIVED_VERIFIED")
            self.assertEqual(summary["archive_payload_batch_id"], "payload-v1")
            self.assertEqual(summary["supersedes_manifest_sha"], old_manifest_sha)
            self.assertEqual(summary["restore_proof_result"], "RESTORE_PROOF_PASS")
            self.assertEqual(summary["source_archive_hash_equality_count"], 7)
            self.assertEqual(summary["source_logical_bytes_total"], summary["archive_logical_bytes_total"])
            self.assertFalse(summary["cleanup_eligible"])
            self.assertEqual(summary["source_mutation_count"], 0)
            self.assertEqual(summary["archive_payload_batch_mutation_count"], 0)
            required_batch_fields = {
                "batch_id", "manifest_sha256", "entry_count", "source_logical_bytes_total",
                "source_allocated_bytes_total", "archive_logical_bytes_total",
                "source_archive_hash_equality_count", "retained_trade_dates", "restore_proof_result",
            }
            self.assertTrue(required_batch_fields <= summary.keys())
            entries = [json.loads(line) for line in Path(summary["manifest_path"]).read_text().splitlines()]
            self.assertEqual(len(entries), 7)
            self.assertTrue(all("source_logical_bytes" in entry and "source_allocated_bytes" in entry for entry in entries))
            self.assertTrue(all("logical_bytes" not in entry and "allocated_bytes" not in entry for entry in entries))
            self.assertEqual(old_manifest_sha, hashlib.sha256(old_manifest.read_bytes()).hexdigest())
            self.assertEqual(old_manifest_stat.st_mtime_ns, old_manifest.stat().st_mtime_ns)
            self.assertEqual(source_hashes, {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source.rglob("*") if path.is_file()
            })
            self.assertEqual(evidence_sha, hashlib.sha256(Path(summary["quiesce_evidence_copied_path"]).read_bytes()).hexdigest())
            self.assertEqual(sidecar_sha, hashlib.sha256(Path(summary["quiesce_evidence_sidecar_copied_path"]).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
