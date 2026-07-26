from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = (
    ROOT / "scripts/build_n6_ai_compact_field_dictionary.py"
)
FULL_PATH = ROOT / "docs/N6_AI_FIELD_DICTIONARY_V1.json"
COMPACT_PATH = (
    ROOT / "docs/N6_AI_FIELD_DICTIONARY_COMPACT_V1.json"
)
APPROVED_PATH = (
    ROOT / "docs/N6_AI_APPROVED_FIELD_DICTIONARY_V1.json"
)


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_n6_ai_compact_field_dictionary",
        BUILDER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("compact_builder_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class N6AiCompactFieldDictionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.full = json.loads(FULL_PATH.read_text(encoding="utf-8"))
        cls.compact = json.loads(
            COMPACT_PATH.read_text(encoding="utf-8")
        )
        cls.unpacked = cls.builder.unpack_compact(cls.compact)
        cls.approved = json.loads(
            APPROVED_PATH.read_text(encoding="utf-8")
        )
        cls.approved_unpacked = cls.builder.unpack_compact(
            cls.approved
        )

    def test_compact_rebuilds_byte_for_byte(self) -> None:
        rebuilt = self.builder.build_compact(
            self.full,
            full_file_sha256=sha256(
                FULL_PATH.read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(rebuilt, self.compact)

    def test_unpacked_projection_is_exact(self) -> None:
        expected = self.builder.semantic_projection(self.full)
        self.assertEqual(self.unpacked, expected)
        self.assertEqual(
            self.compact["semantic_projection_sha256"],
            self.builder.canonical_hash(expected),
        )

    def test_all_relations_and_fields_are_present(self) -> None:
        self.assertEqual(self.unpacked["relation_count"], 35)
        self.assertEqual(self.unpacked["field_count"], 1035)
        relation_columns = self.unpacked["relation_columns"]
        field_columns = self.unpacked["field_columns"]
        relations = self.unpacked["relations"]
        self.assertEqual(len(relations), 35)
        field_total = 0
        for relation_values, fields in relations:
            self.assertEqual(
                len(relation_values), len(relation_columns)
            )
            for field in fields:
                self.assertEqual(len(field), len(field_columns))
            field_total += len(fields)
        self.assertEqual(field_total, 1035)

    def test_unresolved_fields_remain_forbidden(self) -> None:
        field_columns = self.unpacked["field_columns"]
        semantic_index = field_columns.index("semantic_status")
        usage_index = field_columns.index("ai_usage")
        unresolved = 0
        approved_unresolved = 0
        for _, fields in self.unpacked["relations"]:
            for field in fields:
                if field[semantic_index] == "needs_human_review":
                    unresolved += 1
                    if field[usage_index] != "forbidden":
                        approved_unresolved += 1
        self.assertEqual(unresolved, 226)
        self.assertEqual(approved_unresolved, 0)
        self.assertEqual(
            self.unpacked["unresolved_approved_ai_field_count"],
            0,
        )

    def test_bridge_document_size_limit_is_respected(self) -> None:
        self.assertLessEqual(COMPACT_PATH.stat().st_size, 1_000_000)
        self.assertLessEqual(APPROVED_PATH.stat().st_size, 100_000)

    def test_approved_dictionary_is_exact_and_fetch_sized(self) -> None:
        rebuilt = self.builder.build_compact(
            self.full,
            full_file_sha256=sha256(
                FULL_PATH.read_bytes()
            ).hexdigest(),
            approved_only=True,
        )
        self.assertEqual(rebuilt, self.approved)
        expected = self.builder.approved_projection(self.full)
        self.assertEqual(self.approved_unpacked, expected)
        self.assertEqual(self.approved["scope"], "approved_ai_fields")
        self.assertEqual(self.approved_unpacked["field_count"], 200)
        self.assertEqual(
            self.approved_unpacked[
                "unresolved_approved_ai_field_count"
            ],
            0,
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
