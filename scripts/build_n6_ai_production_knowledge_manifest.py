from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


BUNDLE_VERSION = "N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_V1"
AUTHORITY_SOURCE_COMMIT = (
    "8fef361aa053eb93bb6b00bf43df6b73c32debbe"
)
AUTHORITY_SOURCE_TREE = (
    "4f78768e27cf733e99d35065293b4efe1bff2057"
)
RESEARCH_BUNDLE_SHA256 = (
    "69db95dd106bc5ffbee501ebe3144a3005bb8b55012377a29779816169e7b0fc"
)
APPROVED_USAGES = frozenset(
    {"decision", "context_only", "display_only"}
)
OPAQUE_JSON_FIELDS = frozenset(
    {
        (
            "v_n6_stock_condition_display_basis",
            "period_trigger_baseline_json",
        ),
        (
            "v_n6_stock_condition_display_basis",
            "target_price_trace_json",
        ),
        (
            "v_n6_index_condition_display_basis",
            "period_trigger_baseline_json",
        ),
        (
            "v_n6_index_condition_display_basis",
            "target_price_trace_json",
        ),
        (
            "v_n6_board_condition_display_basis",
            "period_trigger_baseline_json",
        ),
        (
            "v_n6_board_condition_display_basis",
            "target_price_trace_json",
        ),
    }
)
MIGRATIONS = (
    "sql/055_n6_ai_agent_v1_schema.sql",
    "sql/056_n6_ai_agent_v1_identity_account_seed.sql",
    "sql/057_n6_ai_agent_execution_compat.sql",
    "sql/058_n6_ai_context_memory_hash_contract.sql",
)
DOCUMENTS = (
    "docs/N6_AI_AGENT_V1_CONTRACT.json",
    "docs/N6_AI_AGENT_V1_SYSTEM_GUIDE.md",
    "docs/N6_PROJECTION_CONTRACT.md",
    "docs/N3N6Q_FOR_N6_VIRTUAL_ACCOUNT_QUOTE_CONTRACT.md",
    "docs/N6_MULTI_USER_AND_AI_ARCHITECTURE_v1.md",
    "docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md",
    "docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md",
    "docs/N5_CANONICAL_ACTION_FLOW_v0.1.md",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_hash(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _validate_git_identity(commit: str, tree: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("authority_source_commit_invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise ValueError("authority_source_tree_invalid")


def build_allowlist(root: Path) -> dict[str, Any]:
    dictionary_path = root / "docs/N6_AI_FIELD_DICTIONARY_V1.json"
    dictionary = json.loads(dictionary_path.read_text(encoding="utf-8"))
    if (
        dictionary.get("relation_count") != 35
        or dictionary.get("field_count") != 1035
        or dictionary.get("approved_ai_field_count") != 200
        or dictionary.get("unresolved_approved_ai_field_count") != 0
    ):
        raise ValueError("source_dictionary_contract_mismatch")

    relations: list[dict[str, Any]] = []
    excluded: set[tuple[str, str]] = set()
    field_count = 0
    for relation in dictionary["relations"]:
        relation_name = relation["relation_name"]
        fields = []
        for field in relation["fields"]:
            if field["ai_usage"] not in APPROVED_USAGES:
                continue
            key = (relation_name, field["canonical_name"])
            if field["data_type"].upper() == "JSONB":
                excluded.add(key)
                continue
            if field["semantic_status"] == "needs_human_review":
                raise ValueError(
                    "production_field_semantics_unresolved:"
                    f"{relation_name}.{field['canonical_name']}"
                )
            fields.append(
                {
                    "canonical_name": field["canonical_name"],
                    "chinese_name": field["chinese_name"],
                    "data_type": field["data_type"],
                    "unit": field["unit"],
                    "enums": field["enums"],
                    "null_meaning": field["null_meaning"],
                    "business_meaning": field["business_meaning"],
                    "data_grain": field["data_grain"],
                    "date_freshness_semantics": field[
                        "date_freshness_semantics"
                    ],
                    "quality_prerequisites": field[
                        "quality_prerequisites"
                    ],
                    "ai_usage": field["ai_usage"],
                    "forbidden_interpretation": field[
                        "forbidden_interpretation"
                    ],
                    "lineage": field["lineage"],
                    "semantic_status": field["semantic_status"],
                }
            )
        if fields:
            fields.sort(key=lambda item: item["canonical_name"])
            relations.append(
                {
                    "relation_name": relation_name,
                    "relation_kind": relation["relation_kind"],
                    "data_grain": relation["data_grain"],
                    "field_count": len(fields),
                    "fields": fields,
                }
            )
            field_count += len(fields)

    if excluded != OPAQUE_JSON_FIELDS:
        formatted = ",".join(
            f"{relation}.{field}"
            for relation, field in sorted(excluded)
        )
        raise ValueError(
            "opaque_json_exclusion_contract_mismatch:" + formatted
        )
    if field_count != 194:
        raise ValueError("production_field_count_mismatch")
    relations.sort(key=lambda item: item["relation_name"])
    payload: dict[str, Any] = {
        "allowlist_version": "N6_AI_PRODUCTION_FIELD_ALLOWLIST_V1",
        "authority_source_commit": AUTHORITY_SOURCE_COMMIT,
        "source_dictionary_file_sha256": file_hash(dictionary_path),
        "source_dictionary_payload_sha256": dictionary[
            "dictionary_payload_sha256"
        ],
        "production_field_count": field_count,
        "excluded_opaque_json_field_count": len(excluded),
        "excluded_opaque_json_fields": [
            f"{relation}.{field}"
            for relation, field in sorted(excluded)
        ],
        "unresolved_production_field_count": 0,
        "relations": relations,
    }
    payload["allowlist_payload_sha256"] = canonical_hash(payload)
    return payload


def build_manifest(
    root: Path,
    *,
    authority_source_commit: str = AUTHORITY_SOURCE_COMMIT,
    authority_source_tree: str = AUTHORITY_SOURCE_TREE,
) -> dict[str, Any]:
    _validate_git_identity(authority_source_commit, authority_source_tree)
    allowlist_path = (
        root / "docs/N6_AI_PRODUCTION_FIELD_ALLOWLIST_V1.json"
    )
    expected_allowlist = build_allowlist(root)
    actual_allowlist = json.loads(
        allowlist_path.read_text(encoding="utf-8")
    )
    if actual_allowlist != expected_allowlist:
        raise ValueError("production_field_allowlist_drift")

    research_path = (
        root / "docs/N6_AI_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
    )
    research = json.loads(research_path.read_text(encoding="utf-8"))
    if (
        research.get("bundle_sha256") != RESEARCH_BUNDLE_SHA256
        or research.get("production_agent_usable") is not False
    ):
        raise ValueError("research_bundle_authority_drift")

    dictionary = json.loads(
        (
            root / "docs/N6_AI_FIELD_DICTIONARY_V1.json"
        ).read_text(encoding="utf-8")
    )
    documents = [
        {"path": relative_path, "sha256": file_hash(root / relative_path)}
        for relative_path in DOCUMENTS
    ]
    knowledge_payload: dict[str, Any] = {
        "bundle_version": BUNDLE_VERSION,
        "authority_source_commit": authority_source_commit,
        "authority_source_tree": authority_source_tree,
        "highest_schema_migration": "058",
        "planned_schema_migrations": [],
        "status": "shadow_runtime_approved_after_catalog_activation",
        "production_agent_usable": True,
        "autonomous_trading_usable": False,
        "production_field_count": expected_allowlist[
            "production_field_count"
        ],
        "unresolved_production_field_count": 0,
        "production_field_allowlist_sha256": file_hash(allowlist_path),
        "production_field_allowlist_payload_sha256": expected_allowlist[
            "allowlist_payload_sha256"
        ],
        "research_bundle_superseded_sha256": RESEARCH_BUNDLE_SHA256,
        "allowed_sources_sha256": canonical_hash(
            dictionary["allowed_sources"]
        ),
        "forbidden_sources_sha256": canonical_hash(
            dictionary["forbidden_sources"]
        ),
        "documents": documents,
        "runtime_boundaries": {
            "shadow_only": True,
            "autonomous_feature_must_remain_disabled": True,
            "zero_human_private_data": True,
            "zero_n1_n5_bare_table_access": True,
            "zero_repository_or_obsidian_runtime_access": True,
            "model_cannot_submit_price_quantity_account_or_date": True,
            "fresh_n3n6q_quote_owned_by_executor": True,
        },
    }
    bundle_sha256 = canonical_hash(knowledge_payload)
    if not _SHA256_RE.fullmatch(bundle_sha256):
        raise ValueError("production_bundle_hash_invalid")
    return {
        **knowledge_payload,
        "bundle_sha256": bundle_sha256,
        "activation_contract": {
            "migration": "058",
            "migration_file_sha256": file_hash(root / MIGRATIONS[-1]),
            "migration_chain": [
                {
                    "migration": Path(relative_path).name.split("_", 1)[0],
                    "path": relative_path,
                    "sha256": file_hash(root / relative_path),
                }
                for relative_path in MIGRATIONS
            ],
            "required_db_role": "n6_ai_agent",
            "required_function": (
                "public.n6_ai_agent_context_load_v2"
                "(text,date,integer,text)"
            ),
            "required_external_manifest_file_sha256": True,
            "required_scram_service": "n6_ai_agent",
            "ai_identity_seed_required": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--allowlist-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    allowlist = build_allowlist(root)
    args.allowlist_output.write_text(
        json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = build_manifest(root)
    args.manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
