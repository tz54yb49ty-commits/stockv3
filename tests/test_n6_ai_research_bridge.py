from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ashare_v3.user.ai_research_bridge as bridge_module
from ashare_v3.user.ai_research_bridge import (
    ReadOnlyResearchBridge,
    ResearchBridgeError,
    call_tool,
    serve_stdio,
    tool_definitions,
)


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def server_policy_061() -> dict[str, object]:
    return {
        "policy_version": "n6_ai_agent_conservative_risk_v1",
        "allowed": True,
        "reason": "passed",
        "buy_budget_cny": 300000,
        "max_identity_exposure_cny": 600000,
        "max_total_exposure_ratio": 0.10,
        "max_daily_new_buys": 10,
        "pause_drawdown_pct": 5,
        "computed_by": "n6_ai_agent_shadow_decision_record",
    }


def public_snapshot_with_server_policy() -> dict[str, object]:
    return {
        "public_scope": "shared_ai_virtual_account",
        "readonly": True,
        "decisions": [
            {
                "ai_decision_id": 61,
                "decision_type": "hold",
                "risk_assessment": {
                    "trigger": "signal",
                    "level": "low",
                    "summary": "server policy passed",
                    "server_policy": server_policy_061(),
                },
            }
        ],
    }


class N6AiResearchBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.git_root = root / "git"
        self.obsidian_root = root / "obsidian"
        self.notes_root = self.obsidian_root / "80-我的笔记"
        self.git_root.mkdir()
        self.notes_root.mkdir(parents=True)
        (self.obsidian_root / "40-AI投资员").mkdir()
        self.guide = self.git_root / "docs" / "guide.md"
        self.guide.parent.mkdir()
        self.guide.write_text(
            "# N6字段\nfor_trade_date 是当前交易日。", encoding="utf-8"
        )
        self.note = self.notes_root / "AI投资员" / "candidate.md"
        self.note.parent.mkdir()
        self.note.write_text("候选经验：只允许人工晋级。", encoding="utf-8")
        self.candidate_dir = (
            self.notes_root / "AI投资员" / "10-候选经验"
        )
        self.candidate_dir.mkdir()
        self.snapshot = (
            self.obsidian_root
            / "40-AI投资员"
            / "30-决策与日报"
            / "ai_public_snapshot.json"
        )
        self.snapshot.parent.mkdir()
        self.snapshot.write_text(
            json.dumps(
                {
                    "public_scope": "shared_ai_virtual_account",
                    "readonly": True,
                    "account": {"total_equity": 100_000_000},
                    "profile": {
                        "ai_user_id": "9",
                        "display_name": "AI模拟投资员",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.snapshot.chmod(0o600)
        self.manifest_path = (
            self.git_root
            / "docs"
            / "N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json"
        )
        self._write_manifest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _entry(
        self,
        *,
        document_id: str,
        root: str,
        relative_path: str,
        path: Path,
    ) -> dict[str, str]:
        return {
            "document_id": document_id,
            "root": root,
            "path": relative_path,
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "title": document_id,
            "kind": "semantic_memory",
        }

    def _write_manifest(
        self,
        *,
        documents: list[dict[str, str]] | None = None,
        snapshot: dict[str, str] | None | object = ...,
    ) -> None:
        payload: dict[str, object] = {
            "bundle_version": "n6-ai-knowledge-test-v1",
            "git_commit": "1" * 40,
            "git_tree": "2" * 40,
            "highest_migration": "057",
            "relation_signature_sha256": "3" * 64,
            "function_signature_sha256": "4" * 64,
            "field_dictionary_sha256": "5" * 64,
            "allowed_sources_sha256": "6" * 64,
            "forbidden_sources_sha256": "7" * 64,
            "reviewed_by": ["N6_user test reviewer"],
            "supersedes": None,
            "documents": documents
            if documents is not None
            else [
                self._entry(
                    document_id="n6-field-guide",
                    root="git",
                    relative_path="docs/guide.md",
                    path=self.guide,
                ),
                self._entry(
                    document_id="candidate-note",
                    root="notes",
                    relative_path="AI投资员/candidate.md",
                    path=self.note,
                ),
            ],
        }
        if snapshot is ...:
            payload["ai_public_snapshot"] = {
                "root": "obsidian",
                "path": (
                    "40-AI投资员/30-决策与日报/"
                    "ai_public_snapshot.json"
                ),
                "mode": "dynamic_owner_0600_v1",
            }
        elif snapshot is not None:
            payload["ai_public_snapshot"] = snapshot
        payload["bundle_sha256"] = canonical_hash(payload)
        self.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _bridge(self) -> ReadOnlyResearchBridge:
        return ReadOnlyResearchBridge(
            manifest_path=self.manifest_path,
            roots={
                "git": self.git_root,
                "obsidian": self.obsidian_root,
                "notes": self.notes_root,
            },
            expected_manifest_sha256=sha256(
                self.manifest_path.read_bytes()
            ).hexdigest(),
        )

    @staticmethod
    def _candidate_arguments(
        *,
        idempotency_key: str = "8" * 64,
        title: str = "候选规则",
    ) -> dict[str, object]:
        return {
            "title": title,
            "summary": "该经验仍需回放和人工审核。",
            "evidence_refs": [
                "bundle:document:n6-field-guide#for_trade_date"
            ],
            "counter_evidence": ["样本期不足十个交易日"],
            "candidate_rule": "仅进入候选区，不得自动晋级。",
            "idempotency_key": idempotency_key,
        }

    def test_exact_six_constrained_tools_search_fetch_and_snapshot(
        self,
    ) -> None:
        bridge = self._bridge()
        self.assertEqual(
            [item["name"] for item in tool_definitions()],
            [
                "knowledge_search",
                "knowledge_fetch",
                "ai_public_snapshot_get",
                "memory_candidate_append",
                "memory_candidate_list",
                "memory_candidate_get",
            ],
        )
        searched = call_tool(
            bridge,
            "knowledge_search",
            {"query": "for_trade_date", "limit": 5},
        )
        self.assertEqual(
            [item["document_id"] for item in searched["results"]],
            ["n6-field-guide"],
        )
        fetched = call_tool(
            bridge,
            "knowledge_fetch",
            {"document_id": "candidate-note"},
        )
        self.assertIn("人工晋级", fetched["content"])
        snapshot = call_tool(
            bridge, "ai_public_snapshot_get", {}
        )
        serialized = json.dumps(snapshot, ensure_ascii=False)
        self.assertTrue(snapshot["available"])
        self.assertNotIn("principal_id", serialized)
        self.assertNotIn("session_token_hash", serialized)
        self.assertNotIn("chain_of_thought", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("private_key_fingerprint", serialized)
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("database_dsn", serialized)
        self.assertEqual(snapshot["git_commit"], "1" * 40)
        self.assertEqual(snapshot["highest_migration"], "057")
        self.assertTrue(snapshot["memory_candidate_append_only"])

    def test_candidate_memory_append_list_get_and_idempotency(self) -> None:
        bridge = self._bridge()
        arguments = self._candidate_arguments()
        first = call_tool(
            bridge, "memory_candidate_append", arguments
        )
        self.assertTrue(first["created"])
        memory = first["memory"]
        memory_id = memory["memory_id"]
        self.assertEqual(memory["status"], "candidate_unreviewed")
        self.assertTrue(memory["knowledge_bundle_current"])
        self.assertEqual(
            memory["knowledge_bundle_sha256"],
            bridge.manifest_summary()["bundle_sha256"],
        )
        candidate_path = self.candidate_dir / f"{memory_id}.json"
        self.assertTrue(candidate_path.is_file())
        self.assertEqual(candidate_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            [
                path.name
                for path in self.candidate_dir.iterdir()
                if not path.name.startswith(".")
            ],
            [f"{memory_id}.json"],
        )

        second = call_tool(
            bridge, "memory_candidate_append", arguments
        )
        self.assertFalse(second["created"])
        self.assertEqual(second["memory"], memory)
        listed = call_tool(
            bridge, "memory_candidate_list", {"limit": 10}
        )
        self.assertEqual(listed["memories"], [memory])
        fetched = call_tool(
            bridge,
            "memory_candidate_get",
            {"memory_id": memory_id},
        )
        self.assertEqual(fetched["memory"], memory)

    def test_candidate_memory_idempotency_conflict_fails_closed(
        self,
    ) -> None:
        bridge = self._bridge()
        arguments = self._candidate_arguments()
        bridge.memory_candidate_append(**arguments)
        changed = self._candidate_arguments(title="不同候选规则")
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "memory_candidate_idempotency_conflict",
        ):
            bridge.memory_candidate_append(**changed)
        self.assertEqual(
            len(list(self.candidate_dir.glob("memory_*.json"))), 1
        )

    def test_candidate_memory_from_old_bundle_remains_readable(
        self,
    ) -> None:
        bridge = self._bridge()
        created = bridge.memory_candidate_append(
            **self._candidate_arguments()
        )
        memory_id = created["memory"]["memory_id"]
        payload = json.loads(
            self.manifest_path.read_text(encoding="utf-8")
        )
        payload["bundle_version"] = "n6-ai-knowledge-test-v2"
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
        current = self._bridge()
        fetched = current.memory_candidate_get(
            memory_id=memory_id
        )["memory"]
        self.assertFalse(fetched["knowledge_bundle_current"])
        self.assertEqual(
            current.memory_candidate_list(limit=1)["memories"],
            [fetched],
        )

    def test_candidate_memory_concurrent_same_request_creates_once(
        self,
    ) -> None:
        bridge = self._bridge()
        arguments = self._candidate_arguments(
            idempotency_key="9" * 64
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: bridge.memory_candidate_append(
                        **arguments
                    ),
                    range(2),
                )
            )
        self.assertEqual(
            sorted(result["created"] for result in results),
            [False, True],
        )
        self.assertEqual(
            results[0]["memory"], results[1]["memory"]
        )
        self.assertEqual(
            len(list(self.candidate_dir.glob("memory_*.json"))), 1
        )
        self.assertEqual(
            list(self.candidate_dir.glob(".pending-*")), []
        )

    def test_candidate_memory_rejects_secret_hidden_reasoning_and_paths(
        self,
    ) -> None:
        bridge = self._bridge()
        for field, value in (
            ("summary", "OPENAI_API_KEY=sk-proj-" + "A" * 40),
            ("summary", "保存 hidden reasoning"),
            ("candidate_rule", "复制 system_prompt"),
            ("summary", "access_token=must-not-persist"),
            ("summary", "refresh_token=must-not-persist"),
            ("summary", "credential=must-not-persist"),
            ("summary", "这里包含隐藏推理"),
            ("summary", "这里包含系统提示词"),
            ("summary", "系统\u200b提示词也不得绕过"),
            ("summary", "access.token=must-not-persist"),
            ("summary", "access  token=must-not-persist"),
            ("summary", "系统 提示词：内部规则"),
            ("summary", "隐藏 推理：逐步内容"),
            ("summary", "access💥token=must-not-persist"),
            ("summary", "系统\n提示词：内部规则"),
            ("summary", "隐藏\t推理：逐步内容"),
            ("summary", "access\u0301token=must-not-persist"),
        ):
            with self.subTest(field=field):
                arguments = self._candidate_arguments()
                arguments[field] = value
                with self.assertRaises(ResearchBridgeError):
                    call_tool(
                        bridge,
                        "memory_candidate_append",
                        arguments,
                    )
        with self.assertRaisesRegex(
            ResearchBridgeError, "tool_arguments_invalid"
        ):
            call_tool(
                bridge,
                "memory_candidate_append",
                {
                    **self._candidate_arguments(),
                    "path": "../../outside.json",
                },
            )
        self.assertEqual(list(self.candidate_dir.iterdir()), [])

    def test_candidate_memory_requires_real_manifest_evidence(self) -> None:
        bridge = self._bridge()
        for reference in (
            "bundle:document:missing-document",
            "../../outside.md",
            "decision:123",
        ):
            with self.subTest(reference=reference):
                arguments = self._candidate_arguments()
                arguments["evidence_refs"] = [reference]
                with self.assertRaisesRegex(
                    ResearchBridgeError,
                    "memory_candidate_evidence_ref_invalid",
                ):
                    bridge.memory_candidate_append(**arguments)
        self.assertEqual(list(self.candidate_dir.iterdir()), [])

    def test_candidate_memory_missing_or_unsafe_directory_fails_closed(
        self,
    ) -> None:
        bridge = self._bridge()
        self.candidate_dir.rmdir()
        outside = Path(self.temp.name) / "outside-candidates"
        outside.mkdir()
        self.candidate_dir.symlink_to(
            outside, target_is_directory=True
        )
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "memory_candidate_directory_unavailable",
        ):
            bridge.memory_candidate_append(
                **self._candidate_arguments()
            )
        self.assertEqual(list(outside.iterdir()), [])

    def test_candidate_memory_rejects_group_writable_directory(
        self,
    ) -> None:
        bridge = self._bridge()
        self.candidate_dir.chmod(0o777)
        try:
            with self.assertRaisesRegex(
                ResearchBridgeError,
                "memory_candidate_directory_unsafe",
            ):
                bridge.memory_candidate_append(
                    **self._candidate_arguments()
                )
        finally:
            self.candidate_dir.chmod(0o755)

    def test_candidate_memory_unsafe_child_does_not_leak_fds(
        self,
    ) -> None:
        bridge = self._bridge()
        before = len(os.listdir("/dev/fd"))
        self.candidate_dir.chmod(0o777)
        try:
            for _ in range(40):
                with self.assertRaisesRegex(
                    ResearchBridgeError,
                    "memory_candidate_directory_unsafe",
                ):
                    bridge.memory_candidate_list()
        finally:
            self.candidate_dir.chmod(0o755)
        after = len(os.listdir("/dev/fd"))
        self.assertLessEqual(after, before + 1)

    def test_candidate_memory_root_drift_has_stable_error(self) -> None:
        bridge = self._bridge()
        moved = self.obsidian_root / "moved-notes"
        self.notes_root.rename(moved)
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "memory_candidate_directory_unavailable",
        ):
            bridge.memory_candidate_list()

    def test_candidate_memory_file_symlink_and_unsafe_mode_fail_closed(
        self,
    ) -> None:
        bridge = self._bridge()
        arguments = self._candidate_arguments()
        memory_id = f"memory_{arguments['idempotency_key']}"
        outside = Path(self.temp.name) / "outside-candidate.json"
        outside.write_text("{}", encoding="utf-8")
        linked = self.candidate_dir / f"{memory_id}.json"
        linked.symlink_to(outside)
        with self.assertRaises(ResearchBridgeError):
            bridge.memory_candidate_append(**arguments)
        linked.unlink()
        stored = bridge.memory_candidate_append(**arguments)
        candidate_path = (
            self.candidate_dir
            / f"{stored['memory']['memory_id']}.json"
        )
        candidate_path.chmod(0o644)
        with self.assertRaisesRegex(
            ResearchBridgeError, "memory_candidate_file_unsafe"
        ):
            bridge.memory_candidate_get(
                memory_id=stored["memory"]["memory_id"]
            )

    def test_candidate_memory_list_is_bounded_and_quota_is_enforced(
        self,
    ) -> None:
        bridge = self._bridge()
        bridge.memory_candidate_append(
            **self._candidate_arguments(
                idempotency_key="a" * 64
            )
        )
        bridge.memory_candidate_append(
            **self._candidate_arguments(
                idempotency_key="b" * 64
            )
        )
        with patch.object(
            bridge,
            "_read_candidate",
            wraps=bridge._read_candidate,
        ) as reader:
            result = bridge.memory_candidate_list(limit=1)
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(len(result["memories"]), 1)
        self.assertEqual(result["candidate_count"], 2)
        self.assertTrue(result["truncated"])

        with patch.object(
            bridge_module, "MAX_CANDIDATE_FILES", 2
        ), self.assertRaisesRegex(
            ResearchBridgeError, "memory_candidate_quota_exceeded"
        ):
            bridge.memory_candidate_append(
                **self._candidate_arguments(
                    idempotency_key="c" * 64
                )
            )

    def test_candidate_memory_list_returns_latest_not_highest_hash(
        self,
    ) -> None:
        bridge = self._bridge()
        older = bridge.memory_candidate_append(
            **self._candidate_arguments(
                idempotency_key="f" * 64,
                title="较早候选",
            )
        )["memory"]
        os.utime(
            self.candidate_dir / f"{older['memory_id']}.json",
            ns=(1, 1),
        )
        newer = bridge.memory_candidate_append(
            **self._candidate_arguments(
                idempotency_key="0" * 64,
                title="较新候选",
            )
        )["memory"]
        self.assertNotEqual(older["memory_id"], newer["memory_id"])
        listed = bridge.memory_candidate_list(limit=1)
        self.assertEqual(
            listed["memories"][0]["memory_id"],
            newer["memory_id"],
        )

    def test_missing_snapshot_is_a_readonly_empty_state(self) -> None:
        self._write_manifest(snapshot=None)
        result = self._bridge().ai_public_snapshot_get()
        self.assertFalse(result["available"])
        self.assertIsNone(result["snapshot"])

    def test_dynamic_snapshot_can_appear_and_change_without_manifest_rebuild(
        self,
    ) -> None:
        self.snapshot.unlink()
        bridge = self._bridge()
        missing = bridge.ai_public_snapshot_get()
        self.assertFalse(missing["available"])
        self.assertIsNone(missing["snapshot"])

        first_payload = {
            "public_scope": "shared_ai_virtual_account",
            "readonly": True,
            "account": {"total_equity": 100_000_000},
        }
        self.snapshot.write_text(
            json.dumps(first_payload), encoding="utf-8"
        )
        self.snapshot.chmod(0o600)
        first = bridge.ai_public_snapshot_get()
        self.assertTrue(first["available"])
        self.assertEqual(first["snapshot"], first_payload)

        second_payload = {
            **first_payload,
            "account": {"total_equity": 100_123_456},
        }
        self.snapshot.write_text(
            json.dumps(second_payload), encoding="utf-8"
        )
        self.snapshot.chmod(0o600)
        second = bridge.ai_public_snapshot_get()
        self.assertTrue(second["available"])
        self.assertEqual(second["snapshot"], second_payload)
        self.assertNotEqual(
            first["snapshot_sha256"], second["snapshot_sha256"]
        )

    def test_dynamic_snapshot_requires_exact_manifest_descriptor(
        self,
    ) -> None:
        base = {
            "root": "obsidian",
            "path": (
                "40-AI投资员/30-决策与日报/"
                "ai_public_snapshot.json"
            ),
            "mode": "dynamic_owner_0600_v1",
        }
        cases = (
            {**base, "mode": "content_sha256_v1"},
            {**base, "sha256": "a" * 64},
            {**base, "root": "git"},
            {**base, "path": "40-AI投资员/snapshot.json"},
        )
        for descriptor in cases:
            with self.subTest(descriptor=descriptor):
                self._write_manifest(snapshot=descriptor)
                with self.assertRaisesRegex(
                    ResearchBridgeError,
                    "ai_public_snapshot_invalid",
                ):
                    self._bridge()
        self._write_manifest()

    def test_dynamic_snapshot_mode_symlink_and_fifo_fail_closed(
        self,
    ) -> None:
        bridge = self._bridge()
        with patch.object(
            bridge_module.os,
            "getuid",
            return_value=os.getuid() + 1,
        ):
            with self.assertRaisesRegex(
                ResearchBridgeError,
                "ai_public_snapshot_owner_mismatch",
            ):
                bridge.ai_public_snapshot_get()

        self.snapshot.chmod(0o644)
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "ai_public_snapshot_mode_mismatch",
        ):
            bridge.ai_public_snapshot_get()

        self.snapshot.unlink()
        outside = Path(self.temp.name) / "outside-snapshot.json"
        outside.write_text(
            json.dumps(
                {
                    "public_scope": "shared_ai_virtual_account",
                    "readonly": True,
                }
            ),
            encoding="utf-8",
        )
        outside.chmod(0o600)
        self.snapshot.symlink_to(outside)
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "ai_public_snapshot_symlink_or_file_type_not_allowed",
        ):
            bridge.ai_public_snapshot_get()

        self.snapshot.unlink()
        os.mkfifo(self.snapshot, 0o600)
        try:
            with self.assertRaisesRegex(
                ResearchBridgeError,
                "ai_public_snapshot_not_regular_file",
            ):
                bridge.ai_public_snapshot_get()
        finally:
            self.snapshot.unlink()

    def test_manifest_hash_and_document_hash_drift_fail_closed(self) -> None:
        expected_manifest_hash = sha256(
            self.manifest_path.read_bytes()
        ).hexdigest()
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        raw["bundle_version"] = "tampered"
        raw["bundle_sha256"] = canonical_hash(
            {
                key: value
                for key, value in raw.items()
                if key != "bundle_sha256"
            }
        )
        self.manifest_path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "knowledge_manifest_external_hash_mismatch",
        ):
            ReadOnlyResearchBridge(
                manifest_path=self.manifest_path,
                roots={
                    "git": self.git_root,
                    "obsidian": self.obsidian_root,
                    "notes": self.notes_root,
                },
                expected_manifest_sha256=expected_manifest_hash,
            )

        self._write_manifest()
        bridge = self._bridge()
        self.guide.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(
            ResearchBridgeError, "knowledge_document_hash_mismatch"
        ):
            bridge.knowledge_fetch(document_id="n6-field-guide")

    def test_manifest_requires_project_identity_and_component_hashes(
        self,
    ) -> None:
        for field in (
            "git_commit",
            "git_tree",
            "highest_migration",
            "relation_signature_sha256",
            "function_signature_sha256",
            "field_dictionary_sha256",
            "allowed_sources_sha256",
            "forbidden_sources_sha256",
            "reviewed_by",
            "supersedes",
        ):
            with self.subTest(field=field):
                payload = json.loads(
                    self.manifest_path.read_text(encoding="utf-8")
                )
                payload.pop(field)
                without_bundle_hash = {
                    key: value
                    for key, value in payload.items()
                    if key != "bundle_sha256"
                }
                payload["bundle_sha256"] = canonical_hash(
                    without_bundle_hash
                )
                self.manifest_path.write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                with self.assertRaises(ResearchBridgeError):
                    self._bridge()
                self._write_manifest()

    def test_path_traversal_hidden_secret_and_forbidden_suffix_are_rejected(
        self,
    ) -> None:
        cases = (
            "../outside.md",
            ".hidden/file.md",
            "docs/session-token.md",
            "docs/sessions/guide.md",
            "docs/credentials/guide.md",
            "docs/data.jsonl",
            "/tmp/absolute.md",
        )
        for relative_path in cases:
            with self.subTest(relative_path=relative_path):
                entry = self._entry(
                    document_id="bad-entry",
                    root="git",
                    relative_path="docs/guide.md",
                    path=self.guide,
                )
                entry["path"] = relative_path
                self._write_manifest(documents=[entry], snapshot=None)
                with self.assertRaises(ResearchBridgeError):
                    self._bridge()

    def test_existing_plural_secret_named_directories_are_rejected(
        self,
    ) -> None:
        for directory in ("sessions", "credentials", "tokens", "secrets"):
            with self.subTest(directory=directory):
                path = self.git_root / "docs" / directory / "guide.md"
                path.parent.mkdir(exist_ok=True)
                path.write_text("not readable", encoding="utf-8")
                entry = self._entry(
                    document_id="bad-entry",
                    root="git",
                    relative_path=f"docs/{directory}/guide.md",
                    path=path,
                )
                self._write_manifest(documents=[entry], snapshot=None)
                with self.assertRaisesRegex(
                    ResearchBridgeError, "knowledge_file_not_allowed"
                ):
                    self._bridge()

    def test_symlink_escape_is_rejected(self) -> None:
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        link = self.git_root / "docs" / "linked.md"
        link.symlink_to(outside)
        entry = self._entry(
            document_id="linked",
            root="git",
            relative_path="docs/linked.md",
            path=outside,
        )
        self._write_manifest(documents=[entry], snapshot=None)
        with self.assertRaisesRegex(
            ResearchBridgeError, "knowledge_symlink_not_allowed"
        ):
            self._bridge()

    def test_symlink_root_is_rejected(self) -> None:
        linked_root = Path(self.temp.name) / "linked-git"
        linked_root.symlink_to(self.git_root, target_is_directory=True)
        with self.assertRaisesRegex(
            ResearchBridgeError, "knowledge_root_symlink_not_allowed"
        ):
            ReadOnlyResearchBridge(
                manifest_path=linked_root
                / "docs"
                / "N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json",
                roots={
                    "git": linked_root,
                    "obsidian": self.obsidian_root,
                    "notes": self.notes_root,
                },
                expected_manifest_sha256=sha256(
                    self.manifest_path.read_bytes()
                ).hexdigest(),
            )

    def test_manifest_symlink_component_is_rejected(self) -> None:
        linked_docs = self.git_root / "linked-docs"
        linked_docs.symlink_to(
            self.git_root / "docs", target_is_directory=True
        )
        with self.assertRaisesRegex(
            ResearchBridgeError, "manifest_symlink_not_allowed"
        ):
            ReadOnlyResearchBridge(
                manifest_path=linked_docs
                / "N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json",
                roots={
                    "git": self.git_root,
                    "obsidian": self.obsidian_root,
                    "notes": self.notes_root,
                },
                expected_manifest_sha256=sha256(
                    self.manifest_path.read_bytes()
                ).hexdigest(),
            )

    def test_high_confidence_secret_material_is_rejected(self) -> None:
        self.guide.write_text(
            "OPENAI_API_KEY=sk-proj-"
            + "A" * 40,
            encoding="utf-8",
        )
        self._write_manifest(snapshot=None)
        bridge = self._bridge()
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "knowledge_document_contains_secret_material",
        ):
            bridge.knowledge_fetch(document_id="n6-field-guide")

    def test_public_snapshot_unknown_or_private_field_fails_closed(
        self,
    ) -> None:
        for field in (
            "session_id",
            "auth_token",
            "cookie",
            "user_id",
            "email",
            "phone",
            "human_account",
            "api_key",
            "database_dsn",
        ):
            with self.subTest(field=field):
                payload = {
                    "public_scope": "shared_ai_virtual_account",
                    "readonly": True,
                    field: "must-not-leak",
                }
                self.snapshot.write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                self._write_manifest()
                with self.assertRaisesRegex(
                    ResearchBridgeError,
                    "ai_public_snapshot_",
                ):
                    self._bridge().ai_public_snapshot_get()

    def test_public_snapshot_scalar_field_cannot_hide_nested_private_data(
        self,
    ) -> None:
        payload = {
            "public_scope": "shared_ai_virtual_account",
            "readonly": True,
            "account": {
                "account_name": {
                    "session_token": "must-not-leak",
                }
            },
        }
        self.snapshot.write_text(
            json.dumps(payload), encoding="utf-8"
        )
        self._write_manifest()
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "ai_public_snapshot_invalid_account_field_type",
        ):
            self._bridge().ai_public_snapshot_get()

    def test_public_snapshot_accepts_exact_061_server_policy(self) -> None:
        payload = public_snapshot_with_server_policy()
        self.snapshot.write_text(
            json.dumps(payload), encoding="utf-8"
        )
        self._write_manifest()

        result = self._bridge().ai_public_snapshot_get()

        self.assertTrue(result["available"])
        self.assertEqual(
            result["snapshot"]["decisions"][0]["risk_assessment"][
                "server_policy"
            ],
            server_policy_061(),
        )

    def test_public_snapshot_server_policy_rejects_schema_expansion(
        self,
    ) -> None:
        mutations = {
            "unknown": {"operator_note": "must-not-expand"},
            "private": {"session_token": "must-not-leak"},
        }
        for name, extra in mutations.items():
            with self.subTest(name=name):
                payload = public_snapshot_with_server_policy()
                policy = payload["decisions"][0]["risk_assessment"][
                    "server_policy"
                ]
                policy.update(extra)
                self.snapshot.write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                self._write_manifest()
                with self.assertRaisesRegex(
                    ResearchBridgeError,
                    "ai_public_snapshot_",
                ):
                    self._bridge().ai_public_snapshot_get()

    def test_public_snapshot_server_policy_requires_complete_scalar_types(
        self,
    ) -> None:
        wrong_values = {
            "allowed": "true",
            "buy_budget_cny": {"amount": 300000},
            "computed_by": ["runner"],
            "max_daily_new_buys": True,
            "max_identity_exposure_cny": "600000",
            "max_total_exposure_ratio": "0.10",
            "pause_drawdown_pct": None,
            "policy_version": 61,
            "reason": {"value": "passed"},
        }
        for field, wrong_value in wrong_values.items():
            with self.subTest(field=field):
                payload = public_snapshot_with_server_policy()
                policy = payload["decisions"][0]["risk_assessment"][
                    "server_policy"
                ]
                policy[field] = wrong_value
                self.snapshot.write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                self._write_manifest()
                with self.assertRaisesRegex(
                    ResearchBridgeError,
                    "ai_public_snapshot_",
                ):
                    self._bridge().ai_public_snapshot_get()

        payload = public_snapshot_with_server_policy()
        del payload["decisions"][0]["risk_assessment"]["server_policy"][
            "reason"
        ]
        self.snapshot.write_text(json.dumps(payload), encoding="utf-8")
        self._write_manifest()
        with self.assertRaisesRegex(
            ResearchBridgeError,
            "ai_public_snapshot_",
        ):
            self._bridge().ai_public_snapshot_get()

    def test_post_manifest_fifo_or_symlink_swap_fails_without_blocking(
        self,
    ) -> None:
        bridge = self._bridge()
        self.guide.unlink()
        os.mkfifo(self.guide)
        with self.assertRaises(ResearchBridgeError):
            bridge.knowledge_fetch(document_id="n6-field-guide")

        self.guide.unlink()
        outside = Path(self.temp.name) / "outside-after-init.md"
        outside.write_text("outside", encoding="utf-8")
        self.guide.symlink_to(outside)
        with self.assertRaisesRegex(
            ResearchBridgeError, "knowledge_symlink_not_allowed"
        ):
            bridge.knowledge_fetch(document_id="n6-field-guide")

    def test_unknown_tools_and_extra_arguments_fail_closed(self) -> None:
        bridge = self._bridge()
        search_result = call_tool(
            bridge,
            "knowledge_search",
            {
                "query": "N6",
                "_meta": {"codex_mcp_tool_call_id": "readonly-call"},
            },
        )
        self.assertGreaterEqual(len(search_result["results"]), 1)
        with self.assertRaisesRegex(ResearchBridgeError, "tool_not_found"):
            call_tool(bridge, "memory_candidate_promote", {})
        with self.assertRaisesRegex(
            ResearchBridgeError, "tool_arguments_invalid"
        ):
            call_tool(
                bridge,
                "knowledge_fetch",
                {"document_id": "n6-field-guide", "path": "../secret"},
            )
        with self.assertRaisesRegex(
            ResearchBridgeError, "tool_arguments_invalid"
        ):
            call_tool(
                bridge,
                "knowledge_search",
                {"query": "N6", "_meta": []},
            )
        with self.assertRaisesRegex(
            ResearchBridgeError, "knowledge_limit_invalid"
        ):
            bridge.knowledge_search(query="N6", limit=True)
        for name, arguments in (
            ("knowledge_search", {"query": 123}),
            ("knowledge_search", {"query": "N6", "limit": "8"}),
            ("knowledge_fetch", {"document_id": 123}),
        ):
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaisesRegex(
                    ResearchBridgeError, "tool_arguments_invalid"
                ):
                    call_tool(bridge, name, arguments)

    def test_search_has_a_total_document_read_budget(self) -> None:
        bridge = self._bridge()
        with patch.object(
            bridge_module, "MAX_SEARCH_TOTAL_BYTES", 10
        ), patch.object(
            bridge_module.os,
            "read",
            side_effect=AssertionError("document bytes read past budget"),
        ):
            with self.assertRaisesRegex(
                ResearchBridgeError,
                "knowledge_search_budget_exceeded",
            ):
                bridge.knowledge_search(query="N6")

    def test_stdio_protocol_lists_and_calls_only_reviewed_tools(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "knowledge_fetch",
                    "arguments": {
                        "document_id": "n6-field-guide",
                        "_meta": {
                            "codex_mcp_tool_call_id": "readonly-call"
                        },
                    },
                    "_meta": {
                        "progressToken": "codex-research-readonly"
                    },
                },
            },
        ]
        input_stream = BytesIO(
            b"".join(
                json.dumps(item).encode("utf-8") + b"\n"
                for item in requests
            )
        )
        output_stream = BytesIO()
        serve_stdio(
            self._bridge(),
            input_stream=input_stream,
            output_stream=output_stream,
        )
        responses = [
            json.loads(line)
            for line in output_stream.getvalue().splitlines()
        ]
        self.assertEqual([item["id"] for item in responses], [1, 2, 3])
        self.assertEqual(
            responses[0]["result"]["protocolVersion"], "2024-11-05"
        )
        self.assertEqual(
            [
                item["name"]
                for item in responses[1]["result"]["tools"]
            ],
            [
                "knowledge_search",
                "knowledge_fetch",
                "ai_public_snapshot_get",
                "memory_candidate_append",
                "memory_candidate_list",
                "memory_candidate_get",
            ],
        )
        self.assertIn(
            "for_trade_date",
            responses[2]["result"]["content"][0]["text"],
        )

    def test_stdio_accepts_only_object_mcp_request_metadata(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "knowledge_search",
                    "arguments": {"query": "N6"},
                    "_meta": [],
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "knowledge_search",
                    "arguments": {"query": "N6"},
                    "unexpected": {},
                },
            },
        ]
        output_stream = BytesIO()
        serve_stdio(
            self._bridge(),
            input_stream=BytesIO(
                b"".join(
                    json.dumps(item).encode("utf-8") + b"\n"
                    for item in requests
                )
            ),
            output_stream=output_stream,
        )
        responses = [
            json.loads(line)
            for line in output_stream.getvalue().splitlines()
        ]
        self.assertEqual(responses[0]["id"], 1)
        self.assertEqual(
            [response["error"]["message"] for response in responses[1:]],
            ["tool_arguments_invalid", "tool_arguments_invalid"],
        )

    def test_oversized_stdio_request_is_drained_before_next_request(
        self,
    ) -> None:
        oversized = b'{"jsonrpc":"2.0","id":1,"padding":"' + b"x" * 300
        requests = (
            oversized
            + b'"}\n'
            + json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "ping"}
            ).encode("utf-8")
            + b"\n"
        )
        output_stream = BytesIO()
        serve_stdio(
            self._bridge(),
            input_stream=BytesIO(requests),
            output_stream=output_stream,
            max_line_bytes=128,
        )
        responses = [
            json.loads(line)
            for line in output_stream.getvalue().splitlines()
        ]
        self.assertEqual(len(responses), 2)
        self.assertEqual(
            responses[0]["error"]["message"], "request_too_large"
        )
        self.assertEqual(responses[1]["id"], 2)
        self.assertEqual(responses[1]["result"], {})

    def test_stdio_requires_jsonrpc_id_and_initialize_lifecycle(self) -> None:
        requests = [
            {"jsonrpc": "1.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            {"jsonrpc": "2.0", "id": 5, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        ]
        output_stream = BytesIO()
        serve_stdio(
            self._bridge(),
            input_stream=BytesIO(
                b"".join(
                    json.dumps(item).encode("utf-8") + b"\n"
                    for item in requests
                )
            ),
            output_stream=output_stream,
        )
        responses = [
            json.loads(line)
            for line in output_stream.getvalue().splitlines()
        ]
        self.assertEqual(len(responses), 6)
        self.assertEqual(responses[0]["error"]["code"], -32600)
        self.assertEqual(
            responses[1]["error"]["message"], "not_initialized"
        )
        self.assertEqual(responses[2]["id"], 3)
        self.assertEqual(
            responses[3]["error"]["message"], "not_initialized"
        )
        self.assertIn("tools", responses[4]["result"])
        self.assertEqual(
            responses[5]["error"]["message"], "already_initialized"
        )

    def test_stdio_rejects_invalid_initialize_and_wire_argument_types(
        self,
    ) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "knowledge_search",
                    "arguments": {"query": 123},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "ai_public_snapshot_get",
                    "arguments": [],
                },
            },
        ]
        output_stream = BytesIO()
        serve_stdio(
            self._bridge(),
            input_stream=BytesIO(
                b"".join(
                    json.dumps(item).encode("utf-8") + b"\n"
                    for item in requests
                )
            ),
            output_stream=output_stream,
        )
        responses = [
            json.loads(line)
            for line in output_stream.getvalue().splitlines()
        ]
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertEqual(responses[1]["id"], 2)
        self.assertEqual(responses[2]["error"]["code"], -32602)
        self.assertEqual(responses[3]["error"]["code"], -32602)

    def test_stdio_distinguishes_protocol_and_tool_execution_errors(
        self,
    ) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "not_a_tool", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "knowledge_fetch",
                    "arguments": {"document_id": "missing"},
                },
            },
        ]
        output_stream = BytesIO()
        serve_stdio(
            self._bridge(),
            input_stream=BytesIO(
                b"".join(
                    json.dumps(item).encode("utf-8") + b"\n"
                    for item in requests
                )
            ),
            output_stream=output_stream,
        )
        responses = [
            json.loads(line)
            for line in output_stream.getvalue().splitlines()
        ]
        self.assertEqual(responses[1]["error"]["code"], -32602)
        self.assertNotIn("error", responses[2])
        self.assertTrue(responses[2]["result"]["isError"])
        self.assertIn(
            "knowledge_document_not_found",
            responses[2]["result"]["content"][0]["text"],
        )

    def test_source_has_no_network_database_subprocess_or_broad_write_api(
        self,
    ) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "ashare_v3"
            / "user"
            / "ai_research_bridge.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "import socket",
            "import subprocess",
            "import psycopg",
            "urllib",
            "requests",
            "httpx",
            "write_text(",
            "write_bytes(",
            "rename(",
            "replace(",
            "mkdir(",
        ):
            self.assertNotIn(forbidden, source)
        tree = ast.parse(source)
        builtin_open_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ]
        self.assertEqual(builtin_open_calls, [])
        self.assertIn(
            'nofollow = getattr(os, "O_NOFOLLOW", 0)', source
        )
        self.assertIn("dir_fd=current_fd", source)
        self.assertIn("src_dir_fd=directory_fd", source)
        self.assertIn("dst_dir_fd=directory_fd", source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("os.fchmod(file_fd, 0o600)", source)
        self.assertNotIn("memory_candidate_promote", source)
        self.assertIn("stat.S_ISREG", source)
        launcher = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "run_n6_ai_research_bridge.py"
        ).read_text(encoding="utf-8")
        self.assertIn("--expected-manifest-sha256", launcher)
        self.assertNotIn("--project-root", launcher)
        self.assertNotIn("--obsidian-root", launcher)
        self.assertNotIn('parser.add_argument(\\n        "--manifest"', launcher)


if __name__ == "__main__":
    unittest.main()
