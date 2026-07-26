from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts/build_n6_ai_knowledge_manifest.py"
MANIFEST_PATH = ROOT / "docs/N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json"
STRATEGY_PATH = (
    ROOT / "docs/N6_AI_INVESTOR_STRATEGY_POLICY_V1_DRAFT.md"
)
STRATEGY_DOCUMENT_ID = (
    "n6-ai-investor-strategy-policy-v1-draft"
)
STRATEGY_SHA256 = (
    "56082554c4f1099c9fa265d80f0233fde7459d2748be4c85f69fc198bddfc9e7"
)
V3_RUNTIME_BUNDLE_SHA256 = (
    "95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b"
)
V4_BUNDLE_SHA256 = (
    "2b4d82a8f82c0930c22872c1e097910857378ab10bbf62840f838016bf89bfd9"
)
CANDIDATE_PATH = (
    ROOT
    / "docs"
    / "N6_AI_INVESTOR_STRATEGY_POLICY_V1_"
    "SHADOW_CANDIDATE_PACKAGE_20260721.json"
)
CANDIDATE_DOCUMENT_ID = (
    "n6-ai-investor-strategy-policy-v1-shadow-candidate-20260721"
)
CANDIDATE_SHA256 = (
    "284027a9db22dcd7adea23a38764576f2509e3a9b6aa3503f4d485d0ffeccd1b"
)
CANONICAL_PATH = (
    ROOT
    / "docs"
    / "N6_AI_INVESTOR_STRATEGY_POLICY_V1_SHADOW_CANONICAL.md"
)
CANONICAL_DOCUMENT_ID = (
    "n6-ai-investor-strategy-policy-v1-shadow-canonical"
)
CANONICAL_SHA256 = (
    "8010ee6a3c69a9f3472428766fb084c3cf969266d5b4ecec69dd79bfb7ddca1c"
)
PROMOTION_SOURCE_COMMIT = (
    "7c23d5113ca4377dd9836c88c39b8b78d27c6678"
)
PROMOTION_SOURCE_TREE = (
    "ba73089c9a99655622f47d63a1ba6e6342379ad3"
)
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_n6_ai_knowledge_manifest",
        BUILDER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("manifest_builder_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class N6AiKnowledgeManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.payload = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8")
        )

    def test_manifest_rebuilds_byte_for_byte(self) -> None:
        rebuilt = self.builder.build_manifest(
            ROOT,
            git_commit=self.payload["git_commit"],
            git_tree=self.payload["git_tree"],
        )
        self.assertEqual(rebuilt, self.payload)
        without_hash = {
            key: value
            for key, value in self.payload.items()
            if key != "bundle_sha256"
        }
        self.assertEqual(
            self.payload["bundle_sha256"],
            self.builder.canonical_hash(without_hash),
        )

    def test_documents_are_fetch_safe_and_hash_exact(self) -> None:
        entries = self.payload["documents"]
        expected = {
            document_id
            for document_id, _, _ in self.builder.DOCUMENTS
        }
        self.assertEqual(
            {entry["document_id"] for entry in entries},
            expected,
        )
        for entry in entries:
            path = ROOT / entry["path"]
            self.assertEqual(entry["root"], "git")
            self.assertEqual(Path(entry["path"]).parts[0], "docs")
            self.assertLessEqual(path.stat().st_size, 100_000)
            self.assertEqual(
                entry["sha256"],
                sha256(path.read_bytes()).hexdigest(),
            )

    def test_v5_promotes_shadow_governance_without_runtime_authority(
        self,
    ) -> None:
        self.assertEqual(
            self.payload["bundle_version"],
            "N6_AI_KNOWLEDGE_BUNDLE_V5",
        )
        self.assertEqual(
            self.payload["supersedes"],
            V4_BUNDLE_SHA256,
        )
        self.assertEqual(
            self.payload["git_commit"],
            PROMOTION_SOURCE_COMMIT,
        )
        self.assertEqual(
            self.payload["git_tree"],
            PROMOTION_SOURCE_TREE,
        )
        self.assertEqual(len(self.payload["documents"]), 18)
        strategy_entries = [
            entry
            for entry in self.payload["documents"]
            if entry["document_id"] == STRATEGY_DOCUMENT_ID
        ]
        self.assertEqual(
            strategy_entries,
            [
                {
                    "document_id": STRATEGY_DOCUMENT_ID,
                    "root": "git",
                    "path": (
                        "docs/"
                        "N6_AI_INVESTOR_STRATEGY_POLICY_V1_DRAFT.md"
                    ),
                    "sha256": STRATEGY_SHA256,
                    "title": STRATEGY_DOCUMENT_ID,
                    "kind": "strategy_policy_draft",
                }
            ],
        )
        self.assertEqual(
            sha256(STRATEGY_PATH.read_bytes()).hexdigest(),
            STRATEGY_SHA256,
        )
        strategy = STRATEGY_PATH.read_text(encoding="utf-8")
        for frozen_status in (
            "document_status=DRAFT",
            (
                "authority_status="
                "SESSION_CONFIRMED_NOT_YET_PROMOTED"
            ),
            "implementation_status=documented_not_active",
            "autonomous_trading_authorized=false",
            "real_trading_authorized=false",
            "unresolved_semantic_count=0",
        ):
            self.assertIn(frozen_status, strategy)

        promoted_entries = {
            entry["document_id"]: entry
            for entry in self.payload["documents"]
            if entry["document_id"]
            in {CANDIDATE_DOCUMENT_ID, CANONICAL_DOCUMENT_ID}
        }
        self.assertEqual(
            promoted_entries,
            {
                CANDIDATE_DOCUMENT_ID: {
                    "document_id": CANDIDATE_DOCUMENT_ID,
                    "root": "git",
                    "path": (
                        "docs/"
                        "N6_AI_INVESTOR_STRATEGY_POLICY_V1_"
                        "SHADOW_CANDIDATE_PACKAGE_20260721.json"
                    ),
                    "sha256": CANDIDATE_SHA256,
                    "title": CANDIDATE_DOCUMENT_ID,
                    "kind": "strategy_candidate_package",
                },
                CANONICAL_DOCUMENT_ID: {
                    "document_id": CANONICAL_DOCUMENT_ID,
                    "root": "git",
                    "path": (
                        "docs/"
                        "N6_AI_INVESTOR_STRATEGY_POLICY_V1_"
                        "SHADOW_CANONICAL.md"
                    ),
                    "sha256": CANONICAL_SHA256,
                    "title": CANONICAL_DOCUMENT_ID,
                    "kind": "strategy_policy_shadow_canonical",
                },
            },
        )
        self.assertEqual(
            sha256(CANDIDATE_PATH.read_bytes()).hexdigest(),
            CANDIDATE_SHA256,
        )
        self.assertEqual(
            sha256(CANONICAL_PATH.read_bytes()).hexdigest(),
            CANONICAL_SHA256,
        )
        candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(candidate["layer_role"], "N6_user")
        self.assertEqual(
            candidate["candidate_status"],
            "approved_for_shadow_only",
        )
        self.assertEqual(
            candidate["runtime_semantic_source_bundle"][
                "bundle_sha256"
            ],
            V3_RUNTIME_BUNDLE_SHA256,
        )
        self.assertEqual(
            candidate["research_promotion_bundle"][
                "bundle_version"
            ],
            "N6_AI_KNOWLEDGE_BUNDLE_V5",
        )
        for authority in (
            "autonomous_trading_authorized",
            "real_trading_authorized",
            "proposal_authorized",
            "order_authorized",
            "trade_authorized",
            "n1_n5_modification_authorized",
        ):
            self.assertFalse(candidate["risk_boundaries"][authority])
        canonical = CANONICAL_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "document_status=APPROVED_FOR_SHADOW_ONLY",
            canonical,
        )
        self.assertIn(
            "runtime_semantic_source_bundle=N6_AI_KNOWLEDGE_BUNDLE_V3",
            canonical,
        )
        self.assertIn(
            "research_promotion_bundle=N6_AI_KNOWLEDGE_BUNDLE_V5",
            canonical,
        )

    def test_real_bridge_loads_and_fetches_approved_dictionary(
        self,
    ) -> None:
        from ashare_v3.user.ai_research_bridge import (
            ReadOnlyResearchBridge,
        )

        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            obsidian = temp_root / "obsidian"
            notes = temp_root / "notes"
            obsidian.mkdir()
            notes.mkdir()
            bridge = ReadOnlyResearchBridge(
                manifest_path=MANIFEST_PATH,
                roots={
                    "git": ROOT,
                    "obsidian": obsidian,
                    "notes": notes,
                },
                expected_manifest_sha256=sha256(
                    MANIFEST_PATH.read_bytes()
                ).hexdigest(),
            )
            result = bridge.knowledge_fetch(
                document_id="ai-approved-field-dictionary"
            )
            self.assertEqual(
                result["sha256"],
                self.payload["field_dictionary_sha256"],
            )
            compact = json.loads(result["content"])
            self.assertEqual(compact["scope"], "approved_ai_fields")

    def test_relation_and_function_signatures_are_frozen(self) -> None:
        self.assertEqual(len(self.payload["relation_signatures"]), 35)
        self.assertEqual(len(self.payload["function_signatures"]), 10)
        self.assertEqual(
            self.payload["relation_signature_sha256"],
            self.builder.canonical_hash(
                self.payload["relation_signatures"]
            ),
        )
        self.assertEqual(
            self.payload["function_signature_sha256"],
            self.builder.canonical_hash(
                self.payload["function_signatures"]
            ),
        )

    def test_sources_and_non_readable_components_are_bound(self) -> None:
        full_path = ROOT / "docs/N6_AI_FIELD_DICTIONARY_V1.json"
        compact_path = (
            ROOT / "docs/N6_AI_FIELD_DICTIONARY_COMPACT_V1.json"
        )
        approved_path = (
            ROOT / "docs/N6_AI_APPROVED_FIELD_DICTIONARY_V1.json"
        )
        dictionary = json.loads(full_path.read_text(encoding="utf-8"))
        self.assertEqual(
            self.payload["field_dictionary_sha256"],
            sha256(approved_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.payload["full_field_dictionary_sha256"],
            sha256(full_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.payload["compact_all_fields_sha256"],
            sha256(compact_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.payload["allowed_sources_sha256"],
            self.builder.canonical_hash(dictionary["allowed_sources"]),
        )
        self.assertEqual(
            self.payload["forbidden_sources_sha256"],
            self.builder.canonical_hash(dictionary["forbidden_sources"]),
        )
        self.assertEqual(
            self.payload["execution_boundary_sha256"],
            sha256((ROOT / "AGENTS.md").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.payload["project_architecture_sha256"],
            sha256(
                (ROOT / "docs/Architecture.md").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            self.payload["planned_schema_055_sha256"],
            sha256(
                (
                    ROOT / "sql/055_n6_ai_agent_v1_schema.sql"
                ).read_bytes()
            ).hexdigest(),
        )

    def test_bundle_is_runtime_evidence_bound_but_not_production_authority(
        self,
    ) -> None:
        self.assertEqual(self.payload["highest_migration"], "058")
        self.assertEqual(self.payload["planned_migrations"], [])
        self.assertEqual(
            self.payload["status"],
            "research_runtime_evidence_bound",
        )
        self.assertFalse(self.payload["production_agent_usable"])
        self.assertEqual(
            self.payload["supersedes"],
            self.builder.SUPERSEDED_BUNDLE_SHA256,
        )
        requirements = self.payload["runtime_requirements"]
        self.assertTrue(
            requirements["external_manifest_sha256_required"]
        )
        self.assertTrue(
            requirements["db_context_requires_058_hardened_function"]
        )
        self.assertTrue(
            requirements["human_memory_promotion_required"]
        )
        self.assertEqual(
            self.payload["ai_public_snapshot"],
            {
                "root": "obsidian",
                "path": (
                    "40-AI投资员/30-决策与日报/"
                    "ai_public_snapshot.json"
                ),
                "mode": "dynamic_owner_0600_v1",
            },
        )

    def test_runtime_activation_and_production_manifests_are_bound(
        self,
    ) -> None:
        activation_path = (
            ROOT
            / "docs"
            / "N6_AI_AGENT_V1_055_058_RUNTIME_ACTIVATION_CLOSEOUT.json"
        )
        production_path = (
            ROOT
            / "docs"
            / "N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
        )
        activation = json.loads(
            activation_path.read_text(encoding="utf-8")
        )
        production = json.loads(
            production_path.read_text(encoding="utf-8")
        )
        self.assertEqual(activation["result"], "passed")
        self.assertEqual(
            activation["interpretation"][
                "highest_live_schema_migration"
            ],
            "058",
        )
        self.assertTrue(
            activation["interpretation"][
                "research_room_may_treat_055_058_as_live_at_closeout"
            ]
        )
        self.assertTrue(
            activation["interpretation"][
                "research_room_must_not_infer_current_live_state_after_closeout"
            ]
        )
        self.assertFalse(
            activation["interpretation"][
                "shadow_or_autonomous_readiness_proven"
            ]
        )
        self.assertEqual(
            self.payload["runtime_activation_evidence_sha256"],
            sha256(activation_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.payload["production_knowledge_manifest_sha256"],
            sha256(production_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.payload["production_knowledge_bundle_sha256"],
            production["bundle_sha256"],
        )

    def test_builder_has_no_db_network_or_runtime_capability(self) -> None:
        source = BUILDER_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "psycopg",
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "launchctl",
            "PGSERVICE",
            "PGPASSFILE",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
