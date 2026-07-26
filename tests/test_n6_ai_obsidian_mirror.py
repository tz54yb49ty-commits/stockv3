from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_n6_ai_obsidian_mirror import (
    MirrorError,
    apply_plan,
    build_plan,
)


class N6AiObsidianMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.project = root / "project"
        self.vault = root / "vault"
        (self.project / "docs").mkdir(parents=True)
        self.vault.mkdir()
        self.guide = self.project / "docs" / "guide.md"
        self.dictionary = (
            self.project
            / "docs"
            / "N6_AI_APPROVED_FIELD_DICTIONARY_V1.json"
        )
        self.guide.write_text("# N6 guide\n", encoding="utf-8")
        self.dictionary.write_text(
            '{"scope":"approved_ai_fields"}\n',
            encoding="utf-8",
        )
        self.manifest_path = (
            self.project
            / "docs"
            / "N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json"
        )
        self._write_manifest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_manifest(
        self,
        *,
        guide_path: str = "docs/guide.md",
    ) -> None:
        payload = {
            "bundle_version": "test-bundle-v1",
            "documents": [
                {
                    "document_id": "guide",
                    "root": "git",
                    "path": guide_path,
                    "sha256": sha256(
                        self.guide.read_bytes()
                    ).hexdigest(),
                },
                {
                    "document_id": "ai-approved-field-dictionary",
                    "root": "git",
                    "path": (
                        "docs/"
                        "N6_AI_APPROVED_FIELD_DICTIONARY_V1.json"
                    ),
                    "sha256": sha256(
                        self.dictionary.read_bytes()
                    ).hexdigest(),
                },
            ],
        }
        payload["bundle_sha256"] = canonical_hash(payload)
        self.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def _plan(self):
        return build_plan(
            project_root=self.project,
            vault_root=self.vault,
            expected_manifest_sha256=sha256(
                self.manifest_path.read_bytes()
            ).hexdigest(),
        )

    def test_dry_run_has_exact_generated_and_notes_boundaries(
        self,
    ) -> None:
        plan = self._plan()
        summary = plan.summary()
        self.assertEqual(summary["file_count"], 4)
        self.assertFalse(summary["notes_write_enabled"])
        self.assertFalse((self.vault / "40-AI投资员").exists())
        destinations = {
            item.destination.relative_to(plan.vault_root).as_posix()
            for item in plan.files
        }
        self.assertEqual(
            destinations,
            {
                "40-AI投资员/10-字段字典/"
                "N6_AI_APPROVED_FIELD_DICTIONARY_V1.json",
                "40-AI投资员/20-知识包/guide.md",
                "40-AI投资员/20-知识包/"
                "N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json",
                "40-AI投资员/30-决策与日报/README.md",
            },
        )

    def test_apply_is_idempotent_and_never_overwrites_notes(
        self,
    ) -> None:
        notes_file = (
            self.vault
            / "80-我的笔记"
            / "AI投资员"
            / "10-候选经验"
            / "mine.md"
        )
        notes_file.parent.mkdir(parents=True)
        notes_file.write_text("我的笔记", encoding="utf-8")
        before = notes_file.read_bytes()
        result = apply_plan(self._plan())
        self.assertTrue(result["applied"])
        apply_plan(self._plan())
        self.assertEqual(notes_file.read_bytes(), before)
        self.assertTrue(
            (
                self.vault
                / "80-我的笔记"
                / "AI投资员"
                / "20-人工审核"
            ).is_dir()
        )
        for item in self._plan().files:
            self.assertEqual(
                sha256(item.destination.read_bytes()).hexdigest(),
                item.sha256_hex,
            )
            self.assertEqual(
                stat_mode(item.destination), 0o444
            )

    def test_tampered_plan_cannot_write_notes(self) -> None:
        notes_file = (
            self.vault
            / "80-我的笔记"
            / "AI投资员"
            / "10-候选经验"
            / "mine.md"
        )
        notes_file.parent.mkdir(parents=True)
        notes_file.write_text("不可覆盖", encoding="utf-8")
        plan = self._plan()
        tampered_file = replace(
            plan.files[0], destination=notes_file.resolve()
        )
        tampered = replace(plan, files=(tampered_file,))
        with self.assertRaisesRegex(
            MirrorError, "mirror_destination_scope_invalid"
        ):
            apply_plan(tampered)
        self.assertEqual(
            notes_file.read_text(encoding="utf-8"), "不可覆盖"
        )

    def test_source_or_manifest_drift_fails_closed(self) -> None:
        plan = self._plan()
        self.guide.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(
            MirrorError, "mirror_source_drift"
        ):
            apply_plan(plan)
        self.assertFalse((self.vault / "40-AI投资员").exists())
        with self.assertRaisesRegex(
            MirrorError, "manifest_document_hash_mismatch"
        ):
            self._plan()

    def test_manifest_bundle_hash_and_document_ids_fail_closed(
        self,
    ) -> None:
        payload = json.loads(
            self.manifest_path.read_text(encoding="utf-8")
        )
        payload["bundle_sha256"] = "z" * 64
        self.manifest_path.write_text(
            json.dumps(payload), encoding="utf-8"
        )
        with self.assertRaisesRegex(MirrorError, "manifest_invalid"):
            self._plan()

        self._write_manifest()
        payload = json.loads(
            self.manifest_path.read_text(encoding="utf-8")
        )
        payload["documents"][1]["document_id"] = payload[
            "documents"
        ][0]["document_id"]
        payload["bundle_sha256"] = canonical_hash(
            {
                key: value
                for key, value in payload.items()
                if key != "bundle_sha256"
            }
        )
        self.manifest_path.write_text(
            json.dumps(payload), encoding="utf-8"
        )
        with self.assertRaisesRegex(
            MirrorError, "manifest_document_invalid"
        ):
            self._plan()

    def test_manifest_traversal_and_destination_symlink_fail_closed(
        self,
    ) -> None:
        self._write_manifest(guide_path="../outside.md")
        with self.assertRaisesRegex(
            MirrorError, "manifest_document_invalid"
        ):
            self._plan()
        self._write_manifest()
        plan = self._plan()
        target_dir = (
            self.vault / "40-AI投资员" / "20-知识包"
        )
        target_dir.mkdir(parents=True)
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        (target_dir / "guide.md").symlink_to(outside)
        with self.assertRaisesRegex(
            MirrorError, "mirror_destination_symlink_not_allowed"
        ):
            apply_plan(plan)
        self.assertEqual(
            outside.read_text(encoding="utf-8"), "outside"
        )

    def test_vault_and_generated_directories_must_be_owner_safe(
        self,
    ) -> None:
        self.vault.chmod(0o777)
        try:
            with self.assertRaisesRegex(
                MirrorError, "vault_root_unsafe"
            ):
                self._plan()
        finally:
            self.vault.chmod(0o755)

        plan = self._plan()
        unsafe = self.vault / "40-AI投资员"
        unsafe.mkdir()
        unsafe.chmod(0o777)
        try:
            with self.assertRaisesRegex(
                MirrorError, "mirror_directory_unsafe"
            ):
                apply_plan(plan)
        finally:
            unsafe.chmod(0o755)

    def test_source_has_no_database_network_or_notes_file_write(
        self,
    ) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "build_n6_ai_obsidian_mirror.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "import psycopg",
            "import socket",
            "import requests",
            "import urllib",
            "subprocess",
            "80-我的笔记/AI投资员/10-候选经验/",
            "80-我的笔记/AI投资员/20-人工审核/",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('"notes_write_enabled": False', source)

    def test_generated_mode_is_set_before_file_fsync(self) -> None:
        events: list[str] = []
        with patch(
            "scripts.build_n6_ai_obsidian_mirror.os.fchmod",
            side_effect=lambda _fd, _mode: events.append("fchmod"),
        ), patch(
            "scripts.build_n6_ai_obsidian_mirror.os.fsync",
            side_effect=lambda _fd: events.append("fsync"),
        ):
            apply_plan(self._plan())
        self.assertLess(
            events.index("fchmod"), events.index("fsync")
        )


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


if __name__ == "__main__":
    unittest.main()
