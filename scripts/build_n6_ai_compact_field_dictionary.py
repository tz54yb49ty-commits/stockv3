from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


COMPACT_VERSION = "N6_AI_COMPACT_FIELD_DICTIONARY_V1"


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


def _assert_no_negative_integer(value: Any) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        if value < 0:
            raise ValueError("negative_integer_not_packable")
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_negative_integer(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_negative_integer(item)


def _collect_strings(value: Any, result: set[str]) -> None:
    if isinstance(value, str):
        result.add(value)
    elif isinstance(value, list):
        for item in value:
            _collect_strings(item, result)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, result)


def _pack(value: Any, indexes: dict[str, int]) -> Any:
    if isinstance(value, str):
        return -(indexes[value] + 1)
    if isinstance(value, list):
        return [_pack(item, indexes) for item in value]
    if isinstance(value, dict):
        return {
            key: _pack(item, indexes)
            for key, item in sorted(value.items())
        }
    return value


def _unpack(value: Any, strings: list[str]) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int) and value < 0:
        return strings[-value - 1]
    if isinstance(value, list):
        return [_unpack(item, strings) for item in value]
    if isinstance(value, dict):
        return {
            key: _unpack(item, strings)
            for key, item in value.items()
        }
    return value


def semantic_projection(full: dict[str, Any]) -> dict[str, Any]:
    relations = full["relations"]
    relation_columns = sorted(
        set().union(
            *(
                set(relation) - {"fields"}
                for relation in relations
            )
        )
    )
    field_columns = sorted(
        set().union(
            *(
                set(field)
                for relation in relations
                for field in relation["fields"]
            )
        )
    )
    return {
        "dictionary_version": full["dictionary_version"],
        "source_commit": full["source_commit"],
        "highest_active_migration": full["highest_active_migration"],
        "planned_migration": full["planned_migration"],
        "status": full["status"],
        "production_agent_usable": full[
            "production_agent_usable"
        ],
        "relation_count": full["relation_count"],
        "field_count": full["field_count"],
        "reviewed_field_count": full["reviewed_field_count"],
        "unresolved_field_count": full["unresolved_field_count"],
        "approved_ai_field_count": full["approved_ai_field_count"],
        "unresolved_approved_ai_field_count": full[
            "unresolved_approved_ai_field_count"
        ],
        "approved_ai_field_semantics_complete": full[
            "approved_ai_field_semantics_complete"
        ],
        "allowed_sources": full["allowed_sources"],
        "forbidden_sources": full["forbidden_sources"],
        "hard_semantic_distinctions": full[
            "hard_semantic_distinctions"
        ],
        "relation_columns": relation_columns,
        "field_columns": field_columns,
        "relations": [
            [
                [relation.get(column) for column in relation_columns],
                [
                    [field.get(column) for column in field_columns]
                    for field in relation["fields"]
                ],
            ]
            for relation in relations
        ],
    }


def approved_projection(full: dict[str, Any]) -> dict[str, Any]:
    allowed = {"decision", "context_only", "display_only"}
    approved = dict(full)
    approved["relations"] = []
    for relation in full["relations"]:
        fields = [
            field
            for field in relation["fields"]
            if field["ai_usage"] in allowed
        ]
        if not fields:
            continue
        item = dict(relation)
        item["fields"] = fields
        item["field_count"] = len(fields)
        approved["relations"].append(item)
    approved["relation_count"] = len(approved["relations"])
    approved["field_count"] = sum(
        len(relation["fields"])
        for relation in approved["relations"]
    )
    approved["reviewed_field_count"] = approved["field_count"]
    approved["unresolved_field_count"] = 0
    return semantic_projection(approved)


def build_compact(
    full: dict[str, Any],
    *,
    full_file_sha256: str,
    approved_only: bool = False,
) -> dict[str, Any]:
    if full.get("unresolved_approved_ai_field_count") != 0:
        raise ValueError("approved_field_semantics_unresolved")
    if full.get("production_agent_usable") is not False:
        raise ValueError("full_dictionary_must_remain_research_only")
    projection = (
        approved_projection(full)
        if approved_only
        else semantic_projection(full)
    )
    _assert_no_negative_integer(projection)
    strings: set[str] = set()
    _collect_strings(projection, strings)
    string_table = sorted(strings)
    indexes = {
        value: index for index, value in enumerate(string_table)
    }
    payload: dict[str, Any] = {
        "compact_version": COMPACT_VERSION,
        "full_dictionary_file_sha256": full_file_sha256,
        "full_dictionary_payload_sha256": full[
            "dictionary_payload_sha256"
        ],
        "semantic_projection_sha256": canonical_hash(projection),
        "string_table": string_table,
        "packed": _pack(projection, indexes),
    }
    if approved_only:
        payload["scope"] = "approved_ai_fields"
    payload["compact_payload_sha256"] = canonical_hash(payload)
    return payload


def unpack_compact(compact: dict[str, Any]) -> dict[str, Any]:
    without_hash = {
        key: value
        for key, value in compact.items()
        if key != "compact_payload_sha256"
    }
    if canonical_hash(without_hash) != compact.get(
        "compact_payload_sha256"
    ):
        raise ValueError("compact_payload_hash_mismatch")
    strings = compact.get("string_table")
    if (
        not isinstance(strings, list)
        or strings != sorted(set(strings))
        or any(not isinstance(item, str) for item in strings)
    ):
        raise ValueError("compact_string_table_invalid")
    projection = _unpack(compact["packed"], strings)
    if canonical_hash(projection) != compact.get(
        "semantic_projection_sha256"
    ):
        raise ValueError("semantic_projection_hash_mismatch")
    return projection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approved-only", action="store_true")
    args = parser.parse_args()
    full = json.loads(args.input.read_text(encoding="utf-8"))
    payload = build_compact(
        full,
        full_file_sha256=file_hash(args.input),
        approved_only=args.approved_only,
    )
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
