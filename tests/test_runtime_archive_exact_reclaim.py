from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.run_runtime_archive_exact_reclaim_once import (
    EXPECTED_BRANCH,
    EXPECTED_IMPLEMENTATION_PATHS,
    EXPECTED_START_HEAD,
    ReclaimBlocked,
    SHA256_RE,
    execute_batches,
    file_identity,
    git_freeze,
    ordered_batches,
    progress_summary,
)


def make_row(root: Path, family: str, trade_date: str, name: str) -> dict[str, object]:
    source = root / "source" / family / trade_date / name
    archive = root / "archive" / family / trade_date / name
    source.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    payload = f"{family}:{trade_date}:{name}".encode()
    source.write_bytes(payload)
    archive.write_bytes(payload)
    observed = source.lstat()
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "source_path": str(source),
        "archive_path": str(archive),
        "artifact_family": family,
        "trade_date": trade_date,
        "source_device": observed.st_dev,
        "source_inode": observed.st_ino,
        "source_mode": f"{observed.st_mode & 0o7777:04o}",
        "source_mtime_ns": observed.st_mtime_ns,
        "source_logical_bytes": observed.st_size,
        "source_allocated_bytes": observed.st_blocks * 512,
        "source_sha256": digest,
        "archive_sha256": digest,
    }


class RuntimeArchiveExactReclaimTest(unittest.TestCase):
    def test_git_freeze_accepts_40_lower_hex_commit(self) -> None:
        expected_head = "a" * 40
        responses = [
            SimpleNamespace(returncode=0, stdout=f"{EXPECTED_BRANCH}\n"),
            SimpleNamespace(returncode=0, stdout=f"{expected_head}\n"),
            SimpleNamespace(returncode=0, stdout=f"{EXPECTED_START_HEAD}\n"),
            SimpleNamespace(returncode=0, stdout="\n".join(EXPECTED_IMPLEMENTATION_PATHS) + "\n"),
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=""),
        ]
        with patch(
            "scripts.run_runtime_archive_exact_reclaim_once.run_checked",
            side_effect=responses,
        ):
            self.assertEqual(git_freeze(expected_head)["head"], expected_head)

    def test_git_freeze_rejects_non_40_lower_hex_commit(self) -> None:
        for invalid in ("a" * 39, "a" * 41, "g" * 40):
            with self.subTest(invalid=invalid):
                with patch(
                    "scripts.run_runtime_archive_exact_reclaim_once.run_checked"
                ) as run_checked:
                    with self.assertRaisesRegex(ReclaimBlocked, "expected_head_invalid"):
                        git_freeze(invalid)
                    run_checked.assert_not_called()

    def test_sha256_validator_remains_64_lower_hex(self) -> None:
        self.assertIsNotNone(SHA256_RE.fullmatch("a" * 64))
        for invalid in ("a" * 40, "a" * 63, "a" * 65, "g" * 64):
            with self.subTest(invalid=invalid):
                self.assertIsNone(SHA256_RE.fullmatch(invalid))

    def test_order_is_family_then_oldest_date_then_stable_path(self) -> None:
        rows = [
            {"artifact_family": "post_close_fastlane", "trade_date": "20260101", "source_path": "z"},
            {"artifact_family": "intraday_live_current", "trade_date": "20260102", "source_path": "b"},
            {"artifact_family": "n3p_trigger_proof_contract", "trade_date": "20260103", "source_path": "a"},
            {"artifact_family": "intraday_live_current", "trade_date": "20260101", "source_path": "c"},
            {"artifact_family": "intraday_live_current", "trade_date": "20260101", "source_path": "a"},
        ]
        batches = ordered_batches(rows)
        self.assertEqual([(family, date) for family, date, _ in batches], [
            ("n3p_trigger_proof_contract", "20260103"),
            ("intraday_live_current", "20260101"),
            ("intraday_live_current", "20260102"),
            ("post_close_fastlane", "20260101"),
        ])
        self.assertEqual([row["source_path"] for row in batches[1][2]], ["a", "c"])

    def test_identity_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = make_row(root, "n3p_trigger_proof_contract", "20260101", "a.json")
            source = Path(row["source_path"])
            target = source.with_name("target.json")
            source.rename(target)
            source.symlink_to(target)
            with self.assertRaisesRegex(ReclaimBlocked, "file_not_regular_or_symlink"):
                file_identity(source, expected=row, archive=False)

    def test_execute_unlinks_exact_files_and_fsyncs_progress_per_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                make_row(root, "intraday_live_current", "20260102", "b.json"),
                make_row(root, "n3p_trigger_proof_contract", "20260101", "a.json"),
            ]
            progress = root / "progress.jsonl"
            progress.touch()
            free_values = iter((100, 100, 100, 100))

            def df_reader() -> dict[str, object]:
                return {"available_bytes": next(free_values), "raw": "df"}

            outcome = execute_batches(rows, progress_path=progress, df_reader=df_reader)
            self.assertEqual(outcome["result"], "BLOCKED_FOR_SEPARATE_SNAPSHOT_FALLBACK")
            self.assertEqual(outcome["unlink_count"], 2)
            self.assertEqual(outcome["remaining_count"], 0)
            self.assertFalse(any(Path(row["source_path"]).exists() for row in rows))
            self.assertTrue(all(Path(row["archive_path"]).exists() for row in rows))
            events = [json.loads(line) for line in progress.read_text().splitlines()]
            self.assertEqual([event["event"] for event in events], [
                "unlink_committed", "date_batch_committed",
                "unlink_committed", "date_batch_committed",
            ])
            self.assertEqual([event.get("artifact_family") for event in events if event["event"] == "unlink_committed"], [
                "n3p_trigger_proof_contract", "intraday_live_current",
            ])

    def test_pre_unlink_archive_drift_stops_without_unlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = make_row(root, "n3p_trigger_proof_contract", "20260101", "a.json")
            Path(row["archive_path"]).write_text("drift", encoding="utf-8")
            progress = root / "progress.jsonl"
            progress.touch()
            with self.assertRaisesRegex(ReclaimBlocked, "archive_"):
                execute_batches([row], progress_path=progress, df_reader=lambda: {"available_bytes": 0, "raw": "df"})
            self.assertTrue(Path(row["source_path"]).exists())
            self.assertEqual(progress.read_text(), "")

    def test_progress_summary_preserves_partial_commit_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            progress = Path(tmp) / "progress.jsonl"
            progress.write_text(
                json.dumps({"event": "unlink_committed", "manifest_allocated_bytes": 4096}) + "\n"
                + json.dumps({"event": "date_batch_committed"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(progress_summary(progress), {
                "unlink_count": 1,
                "manifest_allocated_bytes_unlinked": 4096,
            })


if __name__ == "__main__":
    unittest.main()
