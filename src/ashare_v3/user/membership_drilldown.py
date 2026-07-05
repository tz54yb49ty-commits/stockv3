"""Read-only B-track membership drill-down helpers."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


MembershipRows = Iterable[Mapping[str, Any]]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def membership_stock_item(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stock_identity_key": _first_text(row, "stock_identity_key", "identity_key"),
        "display_name": _first_text(row, "display_name", "stock_name", "name"),
        "membership_date": _first_text(row, "membership_date", "membership_trade_date", "trade_date") or None,
        "weight": row.get("weight", row.get("membership_weight")),
    }


def get_index_membership_stocks(index_identity_key: str, rows: MembershipRows = ()) -> list[dict[str, Any]]:
    parent_key = _text(index_identity_key)
    return [
        membership_stock_item(row)
        for row in rows
        if _first_text(row, "index_identity_key", "parent_identity_key") == parent_key
    ]


def get_board_membership_stocks(board_identity_key: str, rows: MembershipRows = ()) -> list[dict[str, Any]]:
    parent_key = _text(board_identity_key)
    return [
        membership_stock_item(row)
        for row in rows
        if _first_text(row, "board_identity_key", "parent_identity_key") == parent_key
    ]


def resolve_membership(
    entity_type: str,
    identity_key: str,
    rows_by_entity: Mapping[str, MembershipRows] | None = None,
) -> list[dict[str, Any]]:
    rows_by_entity = rows_by_entity or {}
    normalized_type = _text(entity_type).lower()
    if normalized_type == "index":
        return get_index_membership_stocks(identity_key, rows_by_entity.get("index", ()))
    if normalized_type == "board":
        return get_board_membership_stocks(identity_key, rows_by_entity.get("board", ()))
    return []
