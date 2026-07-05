"""Fast Lane boundary validation helpers.

The helpers are pure checks: they do not connect to a database, execute
commands, mutate event ledgers, or start workers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence


class FastLaneValidationError(ValueError):
    """Raised when a Fast Lane boundary or safety check fails."""


DESTRUCTIVE_SQL_TOKENS = ("DELETE", "UPDATE", "DROP", "TRUNCATE")
OLD_SYSTEM_MARKERS = (
    "/Users/chuanfuchen/stock_monitor_isolated",
    "/Users/chenchuanfu/stock_monitor_isolated",
    "stock_monitor_isolated",
    "monitor.db",
    "LaunchAgent",
    "8866",
    "8868",
    "8869",
    "8871",
)


def command_text(command: Sequence[str] | str | None) -> str:
    if command is None:
        return ""
    if isinstance(command, str):
        return command
    return " ".join(str(part) for part in command)


def assert_no_cross_layer_execute(
    *,
    wrapper_layer_role: str,
    child_step_layer_role: str,
    child_command: Sequence[str] | str,
    is_execute_step: bool,
) -> bool:
    if is_execute_step and wrapper_layer_role != child_step_layer_role:
        raise FastLaneValidationError(
            f"cross_layer_execute_blocked: wrapper={wrapper_layer_role} child={child_step_layer_role} "
            f"command={command_text(child_command)}"
        )
    return True


def assert_execute_command_confirmed(
    child_command: Sequence[str] | str,
    *,
    is_execute_step: bool,
) -> bool:
    if not is_execute_step:
        return True
    command = list(child_command.split()) if isinstance(child_command, str) else list(child_command)
    missing = []
    if "--execute" not in command:
        missing.append("missing_execute")
    if "--user-confirmed" not in command:
        missing.append("missing_user_confirmed")
    if missing:
        raise FastLaneValidationError(
            "execute_command_confirmation_blocked: " + ",".join(missing)
        )
    return True


def assert_postgres_commit_enabled_when_required(
    child_command: Sequence[str] | str,
    *,
    is_execute_step: bool,
    requires_postgres_commit_enabled: bool,
) -> bool:
    if not is_execute_step or not requires_postgres_commit_enabled:
        return True
    command = list(child_command.split()) if isinstance(child_command, str) else list(child_command)
    if "--postgres-commit-enabled" not in command:
        raise FastLaneValidationError("n1_postgres_commit_guard_blocked: missing_postgres_commit_enabled")
    return True


def assert_p0_zero(quality_summary: Mapping[str, object] | None) -> bool:
    p0 = _int_value(quality_summary or {}, "P0")
    if p0 > 0:
        raise FastLaneValidationError(f"p0_nonzero: P0={p0}")
    return True


def assert_rollback_static_safe(
    rollback_sql_path: str | Path,
    *,
    expected_scope: Iterable[str] = (),
) -> bool:
    path = Path(rollback_sql_path)
    if not path.exists():
        raise FastLaneValidationError(f"rollback_missing: {path}")
    text = path.read_text(encoding="utf-8")
    upper = text.upper()
    first_destructive = _first_index(upper, DESTRUCTIVE_SQL_TOKENS)
    if first_destructive < 0:
        raise FastLaneValidationError(f"rollback_has_no_destructive_statement: {path}")
    guard_index = upper.find("RAISE EXCEPTION")
    if guard_index < 0 or guard_index > first_destructive:
        raise FastLaneValidationError(f"rollback_guard_not_before_destructive_statement: {path}")
    if "CASCADE" in upper or "DROP TABLE" in upper or "TRUNCATE TABLE" in upper:
        raise FastLaneValidationError(f"rollback_forbidden_destructive_scope: {path}")
    scope_terms = tuple(expected_scope)
    if scope_terms and not any(term in text for term in scope_terms):
        raise FastLaneValidationError(f"rollback_expected_scope_missing: {path}")
    return True


def assert_expected_actual_rows_match(
    expected_rows: Mapping[str, object] | None,
    actual_rows: Mapping[str, object] | None,
) -> bool:
    expected = dict(expected_rows or {})
    actual = dict(actual_rows or {})
    if expected != actual:
        raise FastLaneValidationError(f"expected_actual_rows_mismatch: expected={expected} actual={actual}")
    return True


def assert_no_unexpected_event_delta(
    before_event_counts: Mapping[str, object] | None,
    after_event_counts: Mapping[str, object] | None,
    allowed_event_delta: Mapping[str, object] | None,
) -> bool:
    before = {key: _to_int(value) for key, value in (before_event_counts or {}).items()}
    after = {key: _to_int(value) for key, value in (after_event_counts or {}).items()}
    allowed = {key: _to_int(value) for key, value in (allowed_event_delta or {}).items()}
    for key in sorted(set(before) | set(after) | set(allowed)):
        delta = after.get(key, 0) - before.get(key, 0)
        if delta != allowed.get(key, 0):
            raise FastLaneValidationError(
                f"unexpected_event_delta: {key} delta={delta} allowed={allowed.get(key, 0)}"
            )
    return True


def assert_downstream_refs_zero(downstream_ref_counts: Mapping[str, object] | None) -> bool:
    refs = dict(downstream_ref_counts or {})
    nonzero = {key: value for key, value in _flatten_mapping(refs).items() if _to_int(value) != 0}
    if nonzero:
        raise FastLaneValidationError(f"downstream_refs_nonzero: {nonzero}")
    return True


def assert_no_old_system_touch(
    *,
    command: Sequence[str] | str | None,
    path_scan: Iterable[str] | None,
    service_scan: Iterable[str] | None,
) -> bool:
    haystack = "\n".join(
        [command_text(command), *(str(item) for item in (path_scan or ())), *(str(item) for item in (service_scan or ()))]
    )
    for marker in OLD_SYSTEM_MARKERS:
        if marker in haystack:
            raise FastLaneValidationError(f"old_system_touch_blocked: {marker}")
    return True


def assert_forbidden_scope_false(side_effect_flags: Mapping[str, object] | None) -> bool:
    flags = dict(side_effect_flags or {})
    forbidden_true = {
        key: value for key, value in _flatten_mapping(flags).items() if isinstance(value, bool) and value is True
    }
    if forbidden_true:
        raise FastLaneValidationError(f"forbidden_scope_true: {forbidden_true}")
    return True


def _first_index(text: str, tokens: Iterable[str]) -> int:
    indices = [text.find(token) for token in tokens if text.find(token) >= 0]
    return min(indices) if indices else -1


def _int_value(mapping: Mapping[str, object], key: str) -> int:
    return _to_int(mapping.get(key, 0))


def _to_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise FastLaneValidationError(f"non_integer_count: {value!r}") from None


def _flatten_mapping(mapping: Mapping[str, object], *, prefix: str = "") -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in mapping.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flattened.update(_flatten_mapping(value, prefix=full_key))
        else:
            flattened[full_key] = value
    return flattened
