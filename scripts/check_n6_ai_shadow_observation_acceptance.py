#!/usr/bin/env python3
"""Deterministic, read-only acceptance evaluation for migration 062."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
import json
import re
import sys
from typing import Any, Protocol, TextIO


CONTRACT_VERSION = "n6_ai_shadow_observation_acceptance_v1"
MIN_OPEN_TRADE_DATES = 10
MIN_DECISION_CALL_ATTEMPTS = 50
MIN_STRUCTURE_VALID_NUMERATOR = 99
MIN_STRUCTURE_VALID_DENOMINATOR = 100
READY_EXIT_CODE = 0
NOT_READY_EXIT_CODE = 2

ALLOWED_ONE_SHOT_STATUSES = frozenset(
    {
        "no_new_input",
        "decision_structure_invalid",
        "decision_record_rejected",
        "shadow_decision_recorded",
        "failed_closed",
    }
)
SIDE_EFFECT_FIELDS = {
    "proposal": "proposal_created_count",
    "order": "order_created_count",
    "trade": "trade_created_count",
    "position": "position_mutation_count",
    "lot": "lot_mutation_count",
    "cash": "cash_mutation_count",
}
_FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_DEDUP_RE = re.compile(r"^[0-9a-f]{64}$")


class AcceptanceRepository(Protocol):
    """Approved read boundary supplied by the embedding application."""

    def load_shadow_observation_acceptance_evidence(
        self,
    ) -> Mapping[str, Any]:
        ...


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_report(report: Mapping[str, Any]) -> str:
    """Return byte-stable JSON with no wall-clock fields."""

    return _canonical_json(report)


def _empty_report(gaps: Sequence[str]) -> dict[str, Any]:
    normalized_gaps = sorted(set(gaps))
    report = {
        "contract_version": CONTRACT_VERSION,
        "ready": False,
        "current_system_fingerprint": None,
        "window_started_at": None,
        "window_trade_dates": [],
        "open_trade_date_count": 0,
        "audit_row_count": 0,
        "total_audit_row_count": 0,
        "historical_audit_row_count": 0,
        "decision_call_attempt_count": 0,
        "structure_valid_count": 0,
        "structure_valid_rate": None,
        "accepted_decision_count": 0,
        "accepted_decision_missing_risk_count": 0,
        "invalid_structure_accepted_count": 0,
        "side_effects": {
            name: 0 for name in SIDE_EFFECT_FIELDS
        },
        "gaps": normalized_gaps,
        "evidence_sha256": sha256(
            _canonical_json(
                {
                    "contract_version": CONTRACT_VERSION,
                    "invalid": True,
                    "gaps": normalized_gaps,
                }
            ).encode("ascii")
        ).hexdigest(),
    }
    return report


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _parse_trade_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed.isoformat()


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _positive_int_or_none(value: Any) -> int | None | object:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return _INVALID
    return value


_INVALID = object()


def _normalize_open_trade_dates(
    raw: Any, gaps: list[str]
) -> list[str]:
    if (
        not isinstance(raw, Sequence)
        or isinstance(raw, (str, bytes, bytearray))
    ):
        gaps.append("open_trade_dates_invalid")
        return []
    parsed: list[str] = []
    for index, value in enumerate(raw):
        trade_date = _parse_trade_date(value)
        if trade_date is None:
            gaps.append(f"open_trade_date_{index}_invalid")
        else:
            parsed.append(trade_date)
    if parsed != sorted(parsed):
        gaps.append("open_trade_dates_not_sorted")
    if len(parsed) != len(set(parsed)):
        gaps.append("open_trade_dates_duplicate")
    return sorted(set(parsed))


def _normalize_row(
    raw: Any,
    index: int,
    open_dates: set[str],
    gaps: list[str],
) -> dict[str, Any] | None:
    prefix = f"audit_row_{index}"
    if not isinstance(raw, Mapping):
        gaps.append(f"{prefix}_invalid")
        return None

    audit_id = _positive_int_or_none(raw.get("audit_id"))
    dedup_key = raw.get("dedup_key")
    timestamp = _parse_timestamp(raw.get("started_at"))
    trade_date = _parse_trade_date(raw.get("trade_date"))
    fingerprint = raw.get("system_fingerprint")
    status = raw.get("one_shot_status")
    essential_valid = True
    if audit_id is _INVALID or audit_id is None:
        gaps.append(f"{prefix}_audit_id_invalid")
        essential_valid = False
    if not isinstance(dedup_key, str) or not _DEDUP_RE.fullmatch(
        dedup_key
    ):
        gaps.append(f"{prefix}_dedup_key_invalid")
        essential_valid = False
    if timestamp is None:
        gaps.append(f"{prefix}_started_at_invalid")
        essential_valid = False
    if trade_date is None:
        gaps.append(f"{prefix}_trade_date_invalid")
        essential_valid = False
    elif trade_date not in open_dates:
        gaps.append(f"{prefix}_trade_date_not_open")
    if not isinstance(fingerprint, str) or not _FINGERPRINT_RE.fullmatch(
        fingerprint
    ):
        gaps.append(f"{prefix}_system_fingerprint_invalid")
        essential_valid = False
    if status not in ALLOWED_ONE_SHOT_STATUSES:
        gaps.append(f"{prefix}_one_shot_status_unexplained")
        essential_valid = False
    if raw.get("identity_probe_succeeded") is not True:
        gaps.append(f"{prefix}_identity_probe_not_succeeded")

    attempted = raw.get("decision_call_attempted")
    structure_valid = raw.get("structure_valid")
    if not isinstance(attempted, bool):
        gaps.append(f"{prefix}_decision_call_attempted_invalid")
        essential_valid = False
        attempted = False
    if attempted:
        if not isinstance(structure_valid, bool):
            gaps.append(f"{prefix}_structure_valid_missing")
            structure_valid = False
    elif structure_valid is not None:
        gaps.append(f"{prefix}_structure_valid_without_attempt")
        structure_valid = None

    decision_id = _positive_int_or_none(raw.get("decision_id"))
    decision_run_id = _positive_int_or_none(raw.get("decision_run_id"))
    if decision_id is _INVALID:
        gaps.append(f"{prefix}_decision_id_invalid")
        decision_id = None
    if decision_run_id is _INVALID:
        gaps.append(f"{prefix}_decision_run_id_invalid")
        decision_run_id = None
    if (decision_id is None) != (decision_run_id is None):
        gaps.append(f"{prefix}_decision_reference_pair_invalid")

    risk_allowed = raw.get("server_risk_allowed")
    risk_reason = raw.get("server_risk_reason")
    if risk_allowed is not None and not isinstance(risk_allowed, bool):
        gaps.append(f"{prefix}_server_risk_allowed_invalid")
        risk_allowed = None
    if risk_reason is not None and (
        not isinstance(risk_reason, str)
        or not risk_reason
        or len(risk_reason) > 128
    ):
        gaps.append(f"{prefix}_server_risk_reason_invalid")
        risk_reason = None
    if (risk_allowed is None) != (risk_reason is None):
        gaps.append(f"{prefix}_server_risk_pair_invalid")

    proposal_created = raw.get("proposal_created")
    if not isinstance(proposal_created, bool):
        gaps.append(f"{prefix}_proposal_created_invalid")
        proposal_created = False
    side_effects: dict[str, int] = {}
    for name, field in SIDE_EFFECT_FIELDS.items():
        count = _nonnegative_int(raw.get(field))
        if count is None:
            gaps.append(f"{prefix}_{field}_invalid")
            count = 0
        side_effects[name] = count
    if proposal_created != (side_effects["proposal"] > 0):
        gaps.append(f"{prefix}_proposal_count_boolean_conflict")

    accepted = decision_id is not None
    if accepted and (
        attempted is not True or structure_valid is not True
    ):
        gaps.append(f"{prefix}_invalid_structure_accepted")

    if status == "no_new_input" and (
        attempted
        or structure_valid is not None
        or decision_id is not None
        or decision_run_id is not None
        or risk_allowed is not None
        or proposal_created
        or any(side_effects.values())
    ):
        gaps.append(f"{prefix}_no_new_input_matrix_invalid")
    elif status == "decision_structure_invalid" and (
        attempted is not True
        or structure_valid is not False
        or decision_id is not None
        or risk_allowed is not None
    ):
        gaps.append(f"{prefix}_invalid_structure_matrix_invalid")
    elif status == "decision_record_rejected" and (
        attempted is not True
        or structure_valid is not True
        or decision_id is not None
        or risk_allowed is not None
    ):
        gaps.append(f"{prefix}_decision_rejected_matrix_invalid")
    elif status == "shadow_decision_recorded" and (
        attempted is not True
        or structure_valid is not True
        or decision_id is None
        or decision_run_id is None
    ):
        gaps.append(f"{prefix}_recorded_decision_matrix_invalid")
    elif status == "failed_closed" and (
        decision_id is not None or risk_allowed is not None
    ):
        gaps.append(f"{prefix}_failed_closed_matrix_invalid")

    if not essential_valid:
        return None
    assert isinstance(audit_id, int)
    assert isinstance(dedup_key, str)
    assert timestamp is not None
    assert trade_date is not None
    assert isinstance(fingerprint, str)
    assert isinstance(status, str)
    return {
        "audit_id": audit_id,
        "dedup_key": dedup_key,
        "started_at": timestamp,
        "started_at_text": timestamp.isoformat(timespec="microseconds"),
        "trade_date": trade_date,
        "system_fingerprint": fingerprint,
        "one_shot_status": status,
        "decision_call_attempted": attempted,
        "structure_valid": structure_valid,
        "decision_id_present": accepted,
        "server_risk_allowed": risk_allowed,
        "server_risk_reason_present": risk_reason is not None,
        "side_effects": side_effects,
    }


def build_acceptance_report(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate only repository-supplied, already-authorized evidence."""

    if not isinstance(evidence, Mapping):
        return _empty_report(["acceptance_evidence_invalid"])

    gaps: list[str] = []
    if evidence.get("source_complete") is not True:
        gaps.append("evidence_source_incomplete")
    if evidence.get("source_order_proven") is not True:
        gaps.append("evidence_order_not_proven")
    open_trade_dates = _normalize_open_trade_dates(
        evidence.get("open_trade_dates"), gaps
    )
    open_date_set = set(open_trade_dates)

    raw_rows = evidence.get("audit_rows")
    if (
        not isinstance(raw_rows, Sequence)
        or isinstance(raw_rows, (str, bytes, bytearray))
    ):
        return _empty_report(gaps + ["audit_rows_invalid"])

    normalized_rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(raw_rows):
        normalized = _normalize_row(
            raw_row, index, open_date_set, gaps
        )
        if normalized is not None:
            normalized_rows.append(normalized)

    expected_count = _nonnegative_int(
        evidence.get("expected_enabled_one_shot_count")
    )
    if expected_count is None:
        gaps.append("expected_enabled_one_shot_count_invalid")
    elif expected_count != len(raw_rows):
        gaps.append("audit_row_count_mismatch")
    for field in (
        "authority_conflict_count",
        "unexplained_state_count",
    ):
        value = _nonnegative_int(evidence.get(field))
        if value is None:
            gaps.append(f"{field}_invalid")
        elif value:
            gaps.append(f"{field}_nonzero")

    audit_ids = [row["audit_id"] for row in normalized_rows]
    dedup_keys = [row["dedup_key"] for row in normalized_rows]
    if len(audit_ids) != len(set(audit_ids)):
        gaps.append("audit_id_duplicate")
    if len(dedup_keys) != len(set(dedup_keys)):
        gaps.append("dedup_key_duplicate")
    order_keys = [
        (row["started_at"], row["audit_id"])
        for row in normalized_rows
    ]
    if order_keys != sorted(order_keys) or len(order_keys) != len(
        set(order_keys)
    ):
        gaps.append("audit_rows_order_unproven")

    if not normalized_rows:
        return _empty_report(gaps + ["current_system_fingerprint_missing"])

    current_fingerprint = normalized_rows[-1][
        "system_fingerprint"
    ]
    window_start = len(normalized_rows) - 1
    while (
        window_start > 0
        and normalized_rows[window_start - 1][
            "system_fingerprint"
        ]
        == current_fingerprint
    ):
        window_start -= 1
    window = normalized_rows[window_start:]

    window_trade_dates = sorted(
        {row["trade_date"] for row in window}
    )
    decision_attempt_count = sum(
        row["decision_call_attempted"] is True for row in window
    )
    structure_valid_count = sum(
        row["decision_call_attempted"] is True
        and row["structure_valid"] is True
        for row in window
    )
    structure_valid_rate = (
        round(structure_valid_count / decision_attempt_count, 6)
        if decision_attempt_count
        else None
    )
    accepted_decisions = [
        row for row in window if row["decision_id_present"]
    ]
    missing_risk_count = sum(
        not isinstance(row["server_risk_allowed"], bool)
        for row in accepted_decisions
    )
    invalid_accepted_count = sum(
        row["decision_call_attempted"] is not True
        or row["structure_valid"] is not True
        for row in accepted_decisions
    )
    side_effects = {
        name: sum(row["side_effects"][name] for row in window)
        for name in SIDE_EFFECT_FIELDS
    }

    if len(window_trade_dates) < MIN_OPEN_TRADE_DATES:
        gaps.append("insufficient_open_trade_dates")
    if decision_attempt_count < MIN_DECISION_CALL_ATTEMPTS:
        gaps.append("insufficient_decision_call_attempts")
    if decision_attempt_count == 0:
        gaps.append("structure_valid_rate_unavailable")
    elif (
        structure_valid_count * MIN_STRUCTURE_VALID_DENOMINATOR
        < decision_attempt_count * MIN_STRUCTURE_VALID_NUMERATOR
    ):
        gaps.append("structure_valid_rate_below_threshold")
    if missing_risk_count:
        gaps.append("accepted_decision_missing_server_risk")
    if invalid_accepted_count:
        gaps.append("invalid_structure_accepted")
    for name, count in side_effects.items():
        if count:
            gaps.append(f"side_effect_nonzero:{name}")

    canonical_evidence = {
        "contract_version": CONTRACT_VERSION,
        "source_complete": evidence.get("source_complete") is True,
        "source_order_proven": (
            evidence.get("source_order_proven") is True
        ),
        "open_trade_dates": open_trade_dates,
        "expected_enabled_one_shot_count": expected_count,
        "authority_conflict_count": evidence.get(
            "authority_conflict_count"
        ),
        "unexplained_state_count": evidence.get(
            "unexplained_state_count"
        ),
        "rows": [
            {
                key: row[key]
                for key in (
                    "audit_id",
                    "dedup_key",
                    "started_at_text",
                    "trade_date",
                    "system_fingerprint",
                    "one_shot_status",
                    "decision_call_attempted",
                    "structure_valid",
                    "decision_id_present",
                    "server_risk_allowed",
                    "server_risk_reason_present",
                    "side_effects",
                )
            }
            for row in normalized_rows
        ],
        "gaps": sorted(set(gaps)),
    }
    report = {
        "contract_version": CONTRACT_VERSION,
        "ready": not gaps,
        "current_system_fingerprint": current_fingerprint,
        "window_started_at": window[0]["started_at_text"],
        "window_trade_dates": window_trade_dates,
        "open_trade_date_count": len(window_trade_dates),
        "audit_row_count": len(window),
        "total_audit_row_count": len(raw_rows),
        "historical_audit_row_count": window_start,
        "decision_call_attempt_count": decision_attempt_count,
        "structure_valid_count": structure_valid_count,
        "structure_valid_rate": structure_valid_rate,
        "accepted_decision_count": len(accepted_decisions),
        "accepted_decision_missing_risk_count": missing_risk_count,
        "invalid_structure_accepted_count": invalid_accepted_count,
        "side_effects": side_effects,
        "gaps": sorted(set(gaps)),
        "evidence_sha256": sha256(
            _canonical_json(canonical_evidence).encode("ascii")
        ).hexdigest(),
    }
    return report


def build_report_from_repository(
    repository: AcceptanceRepository | None,
) -> dict[str, Any]:
    if repository is None:
        return _empty_report(["acceptance_repository_not_configured"])
    try:
        evidence = (
            repository.load_shadow_observation_acceptance_evidence()
        )
    except Exception:
        return _empty_report(["acceptance_repository_read_failed"])
    return build_acceptance_report(evidence)


def main(
    repository: AcceptanceRepository | None = None,
    *,
    stdout: TextIO | None = None,
) -> int:
    report = build_report_from_repository(repository)
    target = sys.stdout if stdout is None else stdout
    target.write(serialize_report(report) + "\n")
    return READY_EXIT_CODE if report["ready"] else NOT_READY_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
