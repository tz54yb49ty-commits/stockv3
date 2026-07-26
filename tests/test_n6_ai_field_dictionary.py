from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DICTIONARY_PATH = ROOT / "docs" / "N6_AI_FIELD_DICTIONARY_V1.json"
BUILDER_PATH = ROOT / "scripts" / "build_n6_ai_field_dictionary.py"
SCHEMA_PATH = ROOT / "sql" / "055_n6_ai_agent_v1_schema.sql"


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_n6_ai_field_dictionary", BUILDER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("builder_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class N6AiFieldDictionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.payload = json.loads(
            DICTIONARY_PATH.read_text(encoding="utf-8")
        )

    def test_dictionary_hash_and_counts_are_self_consistent(self) -> None:
        without_hash = {
            key: value
            for key, value in self.payload.items()
            if key != "dictionary_payload_sha256"
        }
        self.assertEqual(
            self.payload["dictionary_payload_sha256"],
            self.builder.canonical_hash(without_hash),
        )
        relations = self.payload["relations"]
        fields = [
            field
            for relation in relations
            for field in relation["fields"]
        ]
        self.assertEqual(self.payload["relation_count"], len(relations))
        self.assertEqual(self.payload["field_count"], len(fields))
        self.assertEqual(
            self.payload["unresolved_field_count"],
            len(self.payload["unresolved_fields"]),
        )
        self.assertEqual(
            self.payload["reviewed_field_count"]
            + self.payload["unresolved_field_count"],
            self.payload["field_count"],
        )
        approved = [
            field
            for field in fields
            if field["ai_usage"]
            in {"decision", "context_only", "display_only"}
        ]
        self.assertEqual(
            self.payload["approved_ai_field_count"], len(approved)
        )
        self.assertEqual(
            self.payload["unresolved_approved_ai_field_count"], 0
        )
        self.assertEqual(
            self.payload["unresolved_approved_ai_fields"], []
        )
        self.assertTrue(
            self.payload["approved_ai_field_semantics_complete"]
        )

    def test_dictionary_rebuilds_from_frozen_catalog_and_schema(self) -> None:
        catalog = {
            "database": self.payload["database"],
            "relations": self.payload["source_catalog_snapshot"],
        }
        rebuilt = self.builder.build_dictionary(
            catalog,
            SCHEMA_PATH.read_text(encoding="utf-8"),
        )
        self.assertEqual(rebuilt, self.payload)

    def test_relation_and_field_contract_is_complete(self) -> None:
        relation_names = {
            relation["relation_name"]
            for relation in self.payload["relations"]
        }
        self.assertEqual(
            relation_names, set(self.builder.RELATION_POLICY)
        )
        required = {
            "canonical_name",
            "chinese_name",
            "source_relation",
            "data_type",
            "unit",
            "enums",
            "null_meaning",
            "business_meaning",
            "data_grain",
            "date_freshness_semantics",
            "owner_layer",
            "formula_or_passthrough_source",
            "quality_prerequisites",
            "allowed_consumers",
            "ai_usage",
            "forbidden_interpretation",
            "lineage",
            "schema_state",
            "source_commit",
            "dictionary_version",
            "semantic_status",
        }
        for relation in self.payload["relations"]:
            self.assertEqual(
                relation["field_count"], len(relation["fields"])
            )
            self.assertFalse(relation["direct_ai_role_access"])
            names = [
                field["canonical_name"]
                for field in relation["fields"]
            ]
            self.assertEqual(len(names), len(set(names)))
            for field in relation["fields"]:
                self.assertTrue(required <= set(field))
                if field["semantic_status"] == "needs_human_review":
                    self.assertEqual(field["ai_usage"], "forbidden")

    def test_important_semantics_are_reviewed_and_fail_closed(self) -> None:
        by_name = {}
        for relation in self.payload["relations"]:
            for field in relation["fields"]:
                by_name.setdefault(field["canonical_name"], []).append(
                    field
                )
        for name in (
            "for_trade_date",
            "source_trade_date",
            "prev_trade_date",
            "level_up_score",
            "score",
            "pe_core",
            "buy_target_price",
            "trigger_price",
            "action_price",
            "filled_price",
            "quality_status",
            "available_cash",
            "available_quantity",
        ):
            self.assertIn(name, by_name)
            self.assertTrue(
                all(
                    field["semantic_status"].startswith("reviewed")
                    for field in by_name[name]
                )
            )
        self.assertIn(
            "not a buy signal",
            by_name["level_up_score"][0][
                "forbidden_interpretation"
            ],
        )
        self.assertIn(
            "fresh passed N3N6Q quote",
            by_name["action_price"][0][
                "forbidden_interpretation"
            ],
        )

    def test_private_relations_and_raw_json_are_never_agent_input(
        self,
    ) -> None:
        for relation in self.payload["relations"]:
            if relation["category"] in {
                "human_projection",
                "human_private_scope",
            }:
                self.assertTrue(
                    all(
                        field["ai_usage"] == "forbidden"
                        for field in relation["fields"]
                    )
                )
            for field in relation["fields"]:
                if (
                    field["canonical_name"].endswith("_json")
                    and field["semantic_status"] != "reviewed"
                ):
                    self.assertEqual(field["ai_usage"], "forbidden")

    def test_planned_proposal_actor_nullability_matches_055(self) -> None:
        proposal = next(
            relation
            for relation in self.payload["relations"]
            if relation["relation_name"]
            == "n6_virtual_trade_proposal"
        )
        by_name = {
            field["canonical_name"]: field
            for field in proposal["fields"]
        }
        self.assertFalse(by_name["user_id"]["not_null"])
        self.assertEqual(
            by_name["user_id"]["schema_state"],
            "planned_055_not_migrated",
        )
        self.assertFalse(by_name["actor_ai_user_id"]["not_null"])
        self.assertFalse(
            by_name["source_ai_decision_id"]["not_null"]
        )

    def test_relation_policy_caps_field_level_usage(self) -> None:
        by_relation = {
            relation["relation_name"]: relation
            for relation in self.payload["relations"]
        }
        for relation_name in (
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
            "v_n6_index_membership_fact",
            "v_n6_board_membership_fact",
        ):
            self.assertNotIn(
                "decision",
                {
                    field["ai_usage"]
                    for field in by_relation[relation_name]["fields"]
                },
            )
        quote = by_relation["v_n6_virtual_quote_latest"]
        quote_usage = {
            field["canonical_name"]: field["ai_usage"]
            for field in quote["fields"]
        }
        self.assertEqual(quote_usage["current_price"], "decision")
        self.assertEqual(quote_usage["quality_status"], "decision")
        self.assertEqual(quote_usage["fetched_at"], "decision")

    def test_planned_055_table_inventory_matches_migration(self) -> None:
        planned = self.builder.planned_relations(
            SCHEMA_PATH.read_text(encoding="utf-8")
        )
        expected = {
            item["relation_name"]: {
                column["name"] for column in item["columns"]
            }
            for item in planned
        }
        actual = {
            relation["relation_name"]: {
                field["canonical_name"]
                for field in relation["fields"]
            }
            for relation in self.payload["relations"]
            if relation["schema_state"] == "planned_055_not_migrated"
        }
        self.assertEqual(actual, expected)

    def test_source_contract_forbids_cross_layer_and_private_reads(
        self,
    ) -> None:
        forbidden = " ".join(self.payload["forbidden_sources"])
        for marker in (
            "human user sessions",
            "human-private",
            "N1-N5 raw",
            "common_event_outbox",
            "raw K",
            "arbitrary SQL",
            "model credentials",
            "hidden reasoning",
        ):
            self.assertIn(marker, forbidden)
        self.assertFalse(self.payload["production_agent_usable"])
        self.assertGreater(self.payload["unresolved_field_count"], 0)

    def test_builder_has_no_database_or_network_connector(self) -> None:
        source = BUILDER_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "psycopg",
            "PGSERVICE",
            "socket",
            "requests",
            "httpx",
            "urllib",
            "subprocess",
        ):
            self.assertNotIn(forbidden, source)
        self.assertEqual(
            sha256(SCHEMA_PATH.read_bytes()).hexdigest(),
            "ad13f8d0a1db3a91b01dd154e69f74abf1cee5458572f2210343f5d3c07d34a8",
        )


if __name__ == "__main__":
    unittest.main()
