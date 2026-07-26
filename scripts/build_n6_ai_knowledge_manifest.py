from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


BUNDLE_VERSION = "N6_AI_KNOWLEDGE_BUNDLE_V5"
SUPERSEDED_BUNDLE_SHA256 = (
    "2b4d82a8f82c0930c22872c1e097910857378ab10bbf62840f838016bf89bfd9"
)
DOCUMENTS = (
    (
        "layered-architecture",
        "docs/V3_LAYERED_SYSTEM_ARCHITECTURE.md",
        "architecture",
    ),
    (
        "trigger-action-runtime",
        "docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md",
        "authority",
    ),
    (
        "n4-n5-state-flow",
        "docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md",
        "authority",
    ),
    (
        "n5-action-flow",
        "docs/N5_CANONICAL_ACTION_FLOW_v0.1.md",
        "authority",
    ),
    (
        "n6-projection-contract",
        "docs/N6_PROJECTION_CONTRACT.md",
        "authority",
    ),
    (
        "n3n6q-quote-contract",
        "docs/N3N6Q_FOR_N6_VIRTUAL_ACCOUNT_QUOTE_CONTRACT.md",
        "authority",
    ),
    (
        "n6-multi-user-ai-architecture",
        "docs/N6_MULTI_USER_AND_AI_ARCHITECTURE_v1.md",
        "architecture",
    ),
    (
        "n6-db-role-policy",
        "docs/N6_B_TRACK_PRODUCT_V3_DB_ROLE_POLICY_042_CONTRACT.md",
        "authority",
    ),
    (
        "n6-proposal-executor-contract",
        "docs/N6_B_TRACK_PRODUCT_V3_PROPOSAL_SCOPE_AND_EXECUTOR_CLAIM_NEXT_048_CONTRACT.md",
        "authority",
    ),
    (
        "n6-stop-loss-contract",
        "docs/N6_B_TRACK_PRODUCT_V3_VIRTUAL_STOP_LOSS_049_CONTRACT.md",
        "authority",
    ),
    (
        "ai-agent-contract",
        "docs/N6_AI_AGENT_V1_CONTRACT.json",
        "ai_contract",
    ),
    (
        "ai-agent-system-guide",
        "docs/N6_AI_AGENT_V1_SYSTEM_GUIDE.md",
        "ai_contract",
    ),
    (
        "ai-approved-field-dictionary",
        "docs/N6_AI_APPROVED_FIELD_DICTIONARY_V1.json",
        "field_dictionary",
    ),
    (
        "ai-production-knowledge-manifest",
        "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json",
        "production_contract",
    ),
    (
        "ai-runtime-activation-closeout",
        "docs/N6_AI_AGENT_V1_055_058_RUNTIME_ACTIVATION_CLOSEOUT.json",
        "runtime_evidence",
    ),
    (
        "n6-ai-investor-strategy-policy-v1-draft",
        "docs/N6_AI_INVESTOR_STRATEGY_POLICY_V1_DRAFT.md",
        "strategy_policy_draft",
    ),
    (
        "n6-ai-investor-strategy-policy-v1-shadow-candidate-20260721",
        (
            "docs/"
            "N6_AI_INVESTOR_STRATEGY_POLICY_V1_"
            "SHADOW_CANDIDATE_PACKAGE_20260721.json"
        ),
        "strategy_candidate_package",
    ),
    (
        "n6-ai-investor-strategy-policy-v1-shadow-canonical",
        (
            "docs/"
            "N6_AI_INVESTOR_STRATEGY_POLICY_V1_SHADOW_CANONICAL.md"
        ),
        "strategy_policy_shadow_canonical",
    ),
)
FUNCTION_PATTERN = re.compile(
    r"(?ms)^CREATE OR REPLACE FUNCTION public\.([a-z0-9_]+)"
    r"\s*\((.*?)\)\s*RETURNS\s+(.*?)(?=\nLANGUAGE\s)"
)


def canonical_hash(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def function_signatures(schema_text: str) -> list[dict[str, str]]:
    signatures = [
        {
            "name": match.group(1),
            "arguments": " ".join(match.group(2).split()),
            "returns": " ".join(match.group(3).split()),
        }
        for match in FUNCTION_PATTERN.finditer(schema_text)
    ]
    signatures.sort(key=lambda item: (item["name"], item["arguments"]))
    keys = [(item["name"], item["arguments"]) for item in signatures]
    if len(signatures) != 10 or len(keys) != len(set(keys)):
        raise ValueError("ai_function_signature_inventory_invalid")
    return signatures


def relation_signatures(
    dictionary: dict[str, Any],
) -> list[dict[str, Any]]:
    result = []
    for relation in dictionary["relations"]:
        result.append(
            {
                "relation_name": relation["relation_name"],
                "relation_kind": relation["relation_kind"],
                "schema_state": relation["schema_state"],
                "fields": [
                    {
                        "name": field["canonical_name"],
                        "data_type": field["data_type"],
                        "not_null": field["not_null"],
                        "ai_usage": field["ai_usage"],
                        "semantic_status": field["semantic_status"],
                    }
                    for field in relation["fields"]
                ],
            }
        )
    return sorted(result, key=lambda item: item["relation_name"])


def build_manifest(
    root: Path,
    *,
    git_commit: str,
    git_tree: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", git_commit):
        raise ValueError("git_commit_invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", git_tree):
        raise ValueError("git_tree_invalid")
    full_path = root / "docs/N6_AI_FIELD_DICTIONARY_V1.json"
    compact_path = (
        root / "docs/N6_AI_FIELD_DICTIONARY_COMPACT_V1.json"
    )
    approved_path = (
        root / "docs/N6_AI_APPROVED_FIELD_DICTIONARY_V1.json"
    )
    activation_path = (
        root
        / "docs/N6_AI_AGENT_V1_055_058_RUNTIME_ACTIVATION_CLOSEOUT.json"
    )
    production_manifest_path = (
        root
        / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
    )
    dictionary = json.loads(full_path.read_text(encoding="utf-8"))
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    production_manifest = json.loads(
        production_manifest_path.read_text(encoding="utf-8")
    )
    if dictionary.get("production_agent_usable") is not False:
        raise ValueError("field_dictionary_must_remain_research_only")
    if dictionary.get("unresolved_approved_ai_field_count") != 0:
        raise ValueError("approved_field_semantics_unresolved")
    if (
        approved.get("scope") != "approved_ai_fields"
        or approved.get("full_dictionary_file_sha256")
        != file_hash(full_path)
    ):
        raise ValueError("approved_dictionary_source_mismatch")
    if (
        activation.get("result") != "passed"
        or activation.get("interpretation", {}).get(
            "highest_live_schema_migration"
        )
        != "058"
        or activation.get("interpretation", {}).get(
            "shadow_or_autonomous_readiness_proven"
        )
        is not False
    ):
        raise ValueError("runtime_activation_evidence_invalid")
    if (
        production_manifest.get("highest_schema_migration") != "058"
        or production_manifest.get("production_agent_usable") is not True
        or production_manifest.get("autonomous_trading_usable")
        is not False
    ):
        raise ValueError("production_knowledge_manifest_invalid")
    schema_path = root / "sql/055_n6_ai_agent_v1_schema.sql"
    functions = function_signatures(
        schema_path.read_text(encoding="utf-8")
    )
    relations = relation_signatures(dictionary)
    documents = []
    for document_id, relative_path, kind in DOCUMENTS:
        path = root / relative_path
        if (
            not path.is_file()
            or Path(relative_path).parts[0] != "docs"
            or path.stat().st_size > 100_000
        ):
            raise ValueError(
                f"knowledge_document_not_fetch_safe:{relative_path}"
            )
        documents.append(
            {
                "document_id": document_id,
                "root": "git",
                "path": relative_path,
                "sha256": file_hash(path),
                "title": document_id,
                "kind": kind,
            }
        )
    payload: dict[str, Any] = {
        "bundle_version": BUNDLE_VERSION,
        "git_commit": git_commit,
        "git_tree": git_tree,
        "highest_migration": "058",
        "planned_migrations": [],
        "status": "research_runtime_evidence_bound",
        "production_agent_usable": False,
        "relation_signature_sha256": canonical_hash(relations),
        "function_signature_sha256": canonical_hash(functions),
        "field_dictionary_sha256": file_hash(approved_path),
        "full_field_dictionary_sha256": file_hash(full_path),
        "compact_all_fields_sha256": file_hash(compact_path),
        "execution_boundary_sha256": file_hash(root / "AGENTS.md"),
        "project_architecture_sha256": file_hash(
            root / "docs/Architecture.md"
        ),
        "planned_schema_055_sha256": file_hash(schema_path),
        "allowed_sources_sha256": canonical_hash(
            dictionary["allowed_sources"]
        ),
        "forbidden_sources_sha256": canonical_hash(
            dictionary["forbidden_sources"]
        ),
        "reviewed_by": [
            "N6_user exact-scope tests",
            "independent read-only boundary audit",
        ],
        "supersedes": SUPERSEDED_BUNDLE_SHA256,
        "runtime_activation_evidence_sha256": file_hash(
            activation_path
        ),
        "production_knowledge_manifest_sha256": file_hash(
            production_manifest_path
        ),
        "production_knowledge_bundle_sha256": production_manifest[
            "bundle_sha256"
        ],
        "ai_public_snapshot": {
            "root": "obsidian",
            "path": (
                "40-AI投资员/30-决策与日报/"
                "ai_public_snapshot.json"
            ),
            "mode": "dynamic_owner_0600_v1",
        },
        "documents": documents,
        "relation_signatures": relations,
        "function_signatures": functions,
        "runtime_requirements": {
            "external_manifest_sha256_required": True,
            "production_agent_must_not_read_repository": True,
            "production_agent_must_not_read_obsidian": True,
            "db_context_requires_058_hardened_function": True,
            "human_memory_promotion_required": True,
        },
    }
    payload["bundle_sha256"] = canonical_hash(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--git-tree", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_manifest(
        args.root.resolve(),
        git_commit=args.git_commit,
        git_tree=args.git_tree,
    )
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
