"""Canonical N4 signal/trigger-mark mapping.

This module is intentionally pure and side-effect free. It translates N2/N4
condition semantics into the canonical runtime payload fields required by
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


CANONICAL_SIGNAL_TYPES = ("B_BUY", "S_SELL")
CANONICAL_TRIGGER_MARK_CANDIDATES = ("normal", "30m_volume", "30m_shrink")
CANONICAL_ACTION_MARKS = CANONICAL_TRIGGER_MARK_CANDIDATES
PROJECTION_30M_TYPES = ("none", "volume_up", "shrink_down")


class CanonicalSignalMappingError(ValueError):
    """Raised when condition semantics cannot be mapped canonically."""


@dataclass(frozen=True)
class CanonicalSignalMapping:
    original_condition_key: str
    signal_type: str
    trigger_mark_candidate: str

    @property
    def action_mark(self) -> str:
        """Compatibility alias for legacy call sites; N4 payloads use trigger_mark_candidate."""

        return self.trigger_mark_candidate

    def as_payload_fields(self) -> dict[str, str]:
        return {
            "original_condition_key": self.original_condition_key,
            "signal_type": self.signal_type,
            "trigger_mark_candidate": self.trigger_mark_candidate,
        }


DIRECT_CONDITION_MAPPINGS: dict[str, tuple[str, str]] = {
    "B_BUY": ("B_BUY", "normal"),
    "S_SELL": ("S_SELL", "normal"),
    "B_BUY_30M_VOL": ("B_BUY", "30m_volume"),
    "S_SELL_30M_SHRINK": ("S_SELL", "30m_shrink"),
}


def canonicalize_condition_key(
    condition_key: str,
    *,
    projection_30m_type: str | None = None,
) -> CanonicalSignalMapping:
    original_condition_key = normalize_condition_key(condition_key)
    projection_type = normalize_projection_30m_type(projection_30m_type)

    if original_condition_key in DIRECT_CONDITION_MAPPINGS:
        signal_type, trigger_mark_candidate = DIRECT_CONDITION_MAPPINGS[original_condition_key]
        return CanonicalSignalMapping(
            original_condition_key=original_condition_key,
            signal_type=signal_type,
            trigger_mark_candidate=trigger_mark_candidate,
        )

    if original_condition_key == "BUY_HINT":
        if projection_type == "shrink_down":
            raise CanonicalSignalMappingError("BUY_HINT cannot map to trigger_mark_candidate=30m_shrink")
        return CanonicalSignalMapping(
            original_condition_key=original_condition_key,
            signal_type="B_BUY",
            trigger_mark_candidate="30m_volume" if projection_type == "volume_up" else "normal",
        )

    if original_condition_key == "SELL_HINT":
        if projection_type == "volume_up":
            raise CanonicalSignalMappingError("SELL_HINT cannot map to trigger_mark_candidate=30m_volume")
        return CanonicalSignalMapping(
            original_condition_key=original_condition_key,
            signal_type="S_SELL",
            trigger_mark_candidate="30m_shrink" if projection_type == "shrink_down" else "normal",
        )

    if original_condition_key.startswith("BUY:"):
        return CanonicalSignalMapping(
            original_condition_key=original_condition_key,
            signal_type="B_BUY",
            trigger_mark_candidate="30m_volume" if projection_type == "volume_up" else "normal",
        )

    if original_condition_key.startswith("SELL:"):
        return CanonicalSignalMapping(
            original_condition_key=original_condition_key,
            signal_type="S_SELL",
            trigger_mark_candidate="30m_shrink" if projection_type == "shrink_down" else "normal",
        )

    raise CanonicalSignalMappingError(f"unsupported canonical condition_key: {original_condition_key}")


def canonicalize_condition_row(
    row: Mapping[str, object],
    *,
    candidate_signal_type: str | None = None,
    projection_30m_type: str | None = None,
) -> dict[str, object]:
    mapping = canonicalize_trigger_candidate(
        str(row.get("condition_key") or ""),
        candidate_signal_type=candidate_signal_type,
        projection_30m_type=projection_30m_type,
    )
    return {
        **dict(row),
        **mapping.as_payload_fields(),
    }


def canonicalize_trigger_candidate(
    condition_key: str,
    *,
    candidate_signal_type: str | None = None,
    projection_30m_type: str | None = None,
) -> CanonicalSignalMapping:
    """Map N4 trigger candidate semantics while preserving the N2 condition key.

    N2 condition keys such as BUY:D or SELL:Y,D are audit/condition semantics,
    not runtime signal types. N4 may derive a candidate semantic from
    allowed_signal_types, then canonicalize that candidate into runtime
    signal_type + trigger_mark_candidate while keeping the original condition_key for
    traceability.
    """

    original_condition_key = normalize_condition_key(condition_key)
    candidate_key = normalize_condition_key(candidate_signal_type or condition_key)
    candidate_mapping = canonicalize_condition_key(
        candidate_key,
        projection_30m_type=projection_30m_type,
    )
    return CanonicalSignalMapping(
        original_condition_key=original_condition_key,
        signal_type=candidate_mapping.signal_type,
        trigger_mark_candidate=candidate_mapping.trigger_mark_candidate,
    )


def canonical_payload_errors(payload: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    if str(payload.get("signal_type") or "") not in CANONICAL_SIGNAL_TYPES:
        errors.append("invalid_signal_type")
    trigger_mark_candidate = payload.get("trigger_mark_candidate")
    if trigger_mark_candidate is None and "action_mark" in payload:
        trigger_mark_candidate = payload.get("action_mark")
    if str(trigger_mark_candidate or "") not in CANONICAL_TRIGGER_MARK_CANDIDATES:
        errors.append("invalid_trigger_mark_candidate")
    if not str(payload.get("original_condition_key") or "").strip():
        errors.append("missing_original_condition_key")
    return errors


def normalize_condition_key(condition_key: str) -> str:
    normalized = str(condition_key or "").strip().upper()
    if not normalized:
        raise CanonicalSignalMappingError("condition_key is required")
    return normalized


def normalize_projection_30m_type(projection_30m_type: str | None) -> str:
    if projection_30m_type is None:
        return "none"
    normalized = str(projection_30m_type).strip().lower()
    if normalized in {"", "null"}:
        return "none"
    if normalized not in PROJECTION_30M_TYPES:
        raise CanonicalSignalMappingError(f"unsupported projection_30m_type: {projection_30m_type}")
    return normalized
