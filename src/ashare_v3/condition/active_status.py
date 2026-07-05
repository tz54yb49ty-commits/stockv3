"""Condition run active-status policy helpers.

N2 uses ``passed_active`` as the canonical active pointer. Legacy ``passed``
rows remain readable so older runs stay auditable until they are superseded by a
new canonical active run.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


CANONICAL_ACTIVE_STATUS = "passed_active"
LEGACY_ACTIVE_STATUS = "passed"
ACTIVE_CONDITION_RUN_STATUSES = (CANONICAL_ACTIVE_STATUS, LEGACY_ACTIVE_STATUS)
CONDITION_RUN_STATUS_CHECK_NAME = "common_condition_run_status_check"
PASSED_ACTIVE_UNIQUE_INDEX_NAME = "ux_common_condition_run_one_passed_active"


def active_status_rank(status: object) -> int:
    if status == CANONICAL_ACTIVE_STATUS:
        return 0
    if status == LEGACY_ACTIVE_STATUS:
        return 1
    return 2


def active_status_order_sql(column_name: str = "status") -> str:
    return (
        f"CASE {column_name} "
        f"WHEN '{CANONICAL_ACTIVE_STATUS}' THEN 0 "
        f"WHEN '{LEGACY_ACTIVE_STATUS}' THEN 1 "
        "ELSE 2 END"
    )


def active_status_sql_list() -> str:
    return ", ".join(f"'{status}'" for status in ACTIVE_CONDITION_RUN_STATUSES)


def status_check_supports_passed_active(check_definition: object) -> bool:
    return CANONICAL_ACTIVE_STATUS in str(check_definition or "")


def summarize_active_runs(
    rows: Sequence[Mapping[str, Any]],
    *,
    overwrite: bool,
    table_exists: bool = True,
) -> dict[str, Any]:
    active_rows = [
        dict(row)
        for row in rows
        if row.get("status") in ACTIVE_CONDITION_RUN_STATUSES
    ]
    sorted_rows = [
        row
        for _, row in sorted(
            enumerate(active_rows),
            key=lambda item: (active_status_rank(item[1].get("status")), item[0]),
        )
    ]
    canonical_count = sum(1 for row in sorted_rows if row.get("status") == CANONICAL_ACTIVE_STATUS)
    legacy_count = sum(1 for row in sorted_rows if row.get("status") == LEGACY_ACTIVE_STATUS)
    active_exists = bool(sorted_rows)
    blocked_by_multiple_passed_active = canonical_count > 1
    return {
        "table_exists": table_exists,
        "active_exists": active_exists,
        "active_runs": sorted_rows,
        "active_run_count": len(sorted_rows),
        "canonical_active_status": CANONICAL_ACTIVE_STATUS,
        "legacy_active_status": LEGACY_ACTIVE_STATUS,
        "canonical_active_run_count": canonical_count,
        "legacy_active_run_count": legacy_count,
        "default_policy": "reject_if_active_exists",
        "overwrite": overwrite,
        "blocked_by_active_run": active_exists and not overwrite,
        "blocked_by_multiple_passed_active": blocked_by_multiple_passed_active,
        "read_only": True,
    }
