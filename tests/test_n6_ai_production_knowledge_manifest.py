from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from ashare_v3.user.ai_agent import (
    CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
    load_production_knowledge_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = (
    ROOT / "scripts/build_n6_ai_production_knowledge_manifest.py"
)
ALLOWLIST_PATH = (
    ROOT / "docs/N6_AI_PRODUCTION_FIELD_ALLOWLIST_V1.json"
)
MANIFEST_PATH = (
    ROOT
    / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
)
RESEARCH_MANIFEST_PATH = (
    ROOT / "docs/N6_AI_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
)


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_n6_ai_production_knowledge_manifest",
        BUILDER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("production_manifest_builder_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class N6AiProductionKnowledgeManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.allowlist = json.loads(
            ALLOWLIST_PATH.read_text(encoding="utf-8")
        )
        cls.manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8")
        )

    def test_allowlist_and_manifest_rebuild_exactly(self) -> None:
        self.assertEqual(
            self.builder.build_allowlist(ROOT), self.allowlist
        )
        self.assertEqual(
            self.builder.build_manifest(ROOT), self.manifest
        )
        without_hash = {
            key: value
            for key, value in self.manifest.items()
            if key not in {"bundle_sha256", "activation_contract"}
        }
        self.assertEqual(
            self.manifest["bundle_sha256"],
            self.builder.canonical_hash(without_hash),
        )

    def test_production_allowlist_excludes_all_opaque_json(self) -> None:
        fields = [
            (relation["relation_name"], field)
            for relation in self.allowlist["relations"]
            for field in relation["fields"]
        ]
        self.assertEqual(len(fields), 194)
        self.assertEqual(
            self.allowlist["excluded_opaque_json_field_count"], 6
        )
        self.assertEqual(
            set(self.allowlist["excluded_opaque_json_fields"]),
            {
                f"{relation}.{field}"
                for relation, field in self.builder.OPAQUE_JSON_FIELDS
            },
        )
        self.assertTrue(
            all(field["data_type"].upper() != "JSONB" for _, field in fields)
        )
        self.assertTrue(
            all(
                field["semantic_status"] != "needs_human_review"
                for _, field in fields
            )
        )

    def test_shadow_authority_is_explicit_and_autonomy_disabled(
        self,
    ) -> None:
        self.assertTrue(self.manifest["production_agent_usable"])
        self.assertFalse(self.manifest["autonomous_trading_usable"])
        self.assertEqual(
            self.manifest["highest_schema_migration"], "058"
        )
        self.assertEqual(
            self.manifest["planned_schema_migrations"], []
        )
        self.assertEqual(
            self.manifest["research_bundle_superseded_sha256"],
            self.builder.RESEARCH_BUNDLE_SHA256,
        )
        boundaries = self.manifest["runtime_boundaries"]
        self.assertTrue(boundaries["shadow_only"])
        self.assertTrue(
            boundaries["autonomous_feature_must_remain_disabled"]
        )
        self.assertTrue(boundaries["zero_human_private_data"])
        self.assertTrue(
            boundaries["zero_n1_n5_bare_table_access"]
        )
        self.assertEqual(
            self.manifest["bundle_sha256"],
            CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
        )
        self.assertEqual(
            sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
        )

    def test_runtime_loader_accepts_only_exact_regular_file(self) -> None:
        environment = {
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(MANIFEST_PATH),
            PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
            ),
        }
        loaded = load_production_knowledge_manifest(environment)
        self.assertEqual(
            loaded["bundle_sha256"],
            CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
        )
        for mutation in (
            {},
            {
                **environment,
                PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: "0" * 64,
            },
            {
                **environment,
                PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: "relative.json",
            },
        ):
            with self.assertRaises((OSError, ValueError)):
                load_production_knowledge_manifest(mutation)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tampered = root / "manifest.json"
            tampered.write_bytes(MANIFEST_PATH.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                load_production_knowledge_manifest(
                    {
                        **environment,
                        PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
                            tampered
                        ),
                    }
                )
            link = root / "manifest-link.json"
            os.symlink(MANIFEST_PATH, link)
            with self.assertRaises((OSError, ValueError)):
                load_production_knowledge_manifest(
                    {
                        **environment,
                        PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(link),
                    }
                )

    def test_activation_hashes_bind_exact_migration_chain(self) -> None:
        activation = self.manifest["activation_contract"]
        self.assertEqual(activation["migration"], "058")
        self.assertEqual(len(activation["migration_chain"]), 4)
        for item in activation["migration_chain"]:
            path = ROOT / item["path"]
            self.assertEqual(
                item["sha256"], sha256(path.read_bytes()).hexdigest()
            )
        self.assertEqual(
            activation["migration_file_sha256"],
            sha256(
                (
                    ROOT
                    / "sql/058_n6_ai_context_memory_hash_contract.sql"
                ).read_bytes()
            ).hexdigest(),
        )

    def test_research_manifest_remains_non_runtime_authority(self) -> None:
        research = json.loads(
            RESEARCH_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        self.assertFalse(research["production_agent_usable"])
        self.assertEqual(research["highest_migration"], "054")
        self.assertEqual(
            research["bundle_sha256"],
            self.builder.RESEARCH_BUNDLE_SHA256,
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
