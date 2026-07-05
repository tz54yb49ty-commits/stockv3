"""Active source version activation dry-run planning.

This module only builds activation and rollback SQL templates. It never opens a
database connection, executes SQL, or changes `common_active_source_version`.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.common import IngestionValidationError, QualityGateResult


SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
ALLOWED_ACTIVE_DATA_TYPES: dict[str, tuple[str, ...]] = {
    "common": ("trade_calendar",),
    "stock": ("stock_identity", "stock_daily", "stock_daily_basic", "stock_financial"),
    "index": ("index_identity", "index_daily", "index_membership"),
    "board": ("board_identity", "board_daily", "board_membership"),
}

ACTIVATION_SQL_TEMPLATE = """INSERT INTO common_active_source_version (data_domain, data_type, scope_key, source_version, source_batch_id, previous_source_version, activated_by) VALUES (:data_domain, :data_type, :scope_key, :source_version, :source_batch_id, :previous_source_version, :activated_by) ON CONFLICT (data_domain, data_type, scope_key) DO UPDATE SET previous_source_version = common_active_source_version.source_version, source_version = EXCLUDED.source_version, source_batch_id = EXCLUDED.source_batch_id, activated_at = now(), activated_by = EXCLUDED.activated_by;"""

ROLLBACK_TO_PREVIOUS_SQL_TEMPLATE = """UPDATE common_active_source_version SET source_version = :previous_source_version, source_batch_id = :previous_source_batch_id, previous_source_version = NULL, activated_at = now(), activated_by = :rollback_by WHERE data_domain = :data_domain AND data_type = :data_type AND scope_key = :scope_key AND source_version = :source_version AND source_batch_id = :source_batch_id;"""

ROLLBACK_DELETE_SQL_TEMPLATE = """DELETE FROM common_active_source_version WHERE data_domain = :data_domain AND data_type = :data_type AND scope_key = :scope_key AND source_version = :source_version AND source_batch_id = :source_batch_id;"""


@dataclass(frozen=True)
class ActiveSourceVersionPlan:
    data_domain: str
    data_type: str
    scope_key: str
    source_version: str
    source_batch_id: str
    previous_source_version: str | None
    previous_source_batch_id: str | None
    activated_by: str
    activation_sql_template: str
    rollback_sql_template: str
    quality_gates: tuple[QualityGateResult, ...]
    input_quality_gates: tuple[QualityGateResult, ...]
    will_connect_database: bool = False
    will_execute_sql: bool = False

    @property
    def activation_allowed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_domain": self.data_domain,
            "data_type": self.data_type,
            "scope_key": self.scope_key,
            "source_version": self.source_version,
            "source_batch_id": self.source_batch_id,
            "previous_source_version": self.previous_source_version,
            "previous_source_batch_id": self.previous_source_batch_id,
            "activated_by": self.activated_by,
            "activation_allowed": self.activation_allowed,
            "activation_sql_template": self.activation_sql_template,
            "rollback_sql_template": self.rollback_sql_template,
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "input_quality_gates": [quality_gate_to_dict(gate) for gate in self.input_quality_gates],
            "rollback": {
                "strategy": "restore_previous_source_version" if self.previous_source_version else "delete_current_active_source_version",
                "requires_previous_source_batch_id": bool(self.previous_source_version),
                "sql_template": self.rollback_sql_template,
            },
            "will_connect_database": self.will_connect_database,
            "will_execute_sql": self.will_execute_sql,
        }


def build_active_source_version_plan(
    *,
    data_domain: str,
    data_type: str,
    scope_key: str,
    source_version: str,
    source_batch_id: str,
    quality_gates: Sequence[QualityGateResult | Mapping[str, Any]],
    previous_source_version: str | None = None,
    previous_source_batch_id: str | None = None,
    activated_by: str = "ingestion",
) -> ActiveSourceVersionPlan:
    normalized_domain = normalize_safe_value(data_domain, "data_domain")
    normalized_type = normalize_safe_value(data_type, "data_type")
    normalized_scope = normalize_safe_value(scope_key, "scope_key")
    normalized_source_version = normalize_safe_value(source_version, "source_version")
    normalized_source_batch_id = normalize_safe_value(source_batch_id, "source_batch_id")
    normalized_previous_version = normalize_optional_safe_value(previous_source_version, "previous_source_version")
    normalized_previous_batch_id = normalize_optional_safe_value(previous_source_batch_id, "previous_source_batch_id")
    normalized_activated_by = normalize_safe_value(activated_by, "activated_by")
    normalized_quality_gates = tuple(normalize_quality_gate(gate) for gate in quality_gates)

    own_gates = tuple(
        build_activation_quality_gates(
            data_domain=normalized_domain,
            data_type=normalized_type,
            scope_key=normalized_scope,
            source_version=normalized_source_version,
            source_batch_id=normalized_source_batch_id,
            input_quality_gates=normalized_quality_gates,
            previous_source_version=normalized_previous_version,
            previous_source_batch_id=normalized_previous_batch_id,
        )
    )
    rollback_template = (
        ROLLBACK_TO_PREVIOUS_SQL_TEMPLATE
        if normalized_previous_version
        else ROLLBACK_DELETE_SQL_TEMPLATE
    )

    return ActiveSourceVersionPlan(
        data_domain=normalized_domain,
        data_type=normalized_type,
        scope_key=normalized_scope,
        source_version=normalized_source_version,
        source_batch_id=normalized_source_batch_id,
        previous_source_version=normalized_previous_version,
        previous_source_batch_id=normalized_previous_batch_id,
        activated_by=normalized_activated_by,
        activation_sql_template=ACTIVATION_SQL_TEMPLATE,
        rollback_sql_template=rollback_template,
        quality_gates=own_gates,
        input_quality_gates=normalized_quality_gates,
    )


def build_activation_quality_gates(
    *,
    data_domain: str,
    data_type: str,
    scope_key: str,
    source_version: str,
    source_batch_id: str,
    input_quality_gates: Sequence[QualityGateResult],
    previous_source_version: str | None,
    previous_source_batch_id: str | None,
) -> list[QualityGateResult]:
    allowed_types = ALLOWED_ACTIVE_DATA_TYPES.get(data_domain, ())
    failed_input_gates = [gate for gate in input_quality_gates if not gate.passed]
    return [
        QualityGateResult(
            gate_name="active_source_domain_type_allowed",
            status="passed" if data_type in allowed_types else "failed",
            expected_value=f"{data_domain}:{','.join(allowed_types)}",
            actual_value=f"{data_domain}:{data_type}",
            details={"allowed_data_types": list(allowed_types)},
        ),
        QualityGateResult(
            gate_name="active_source_metadata_present",
            status="passed" if all((data_domain, data_type, scope_key, source_version, source_batch_id)) else "failed",
            expected_value="data_domain/data_type/scope_key/source_version/source_batch_id",
            actual_value="present",
            details={},
        ),
        QualityGateResult(
            gate_name="active_source_input_quality_gates_non_empty",
            status="passed" if input_quality_gates else "failed",
            expected_value=">0",
            actual_value=str(len(input_quality_gates)),
            details={},
        ),
        QualityGateResult(
            gate_name="active_source_input_quality_gates_all_passed",
            status="passed" if input_quality_gates and not failed_input_gates else "failed",
            expected_value="all passed",
            actual_value=str(len(failed_input_gates)),
            details={"failed_gates": [quality_gate_to_dict(gate) for gate in failed_input_gates[:50]]},
        ),
        QualityGateResult(
            gate_name="active_source_previous_batch_available_for_rollback",
            status="passed" if not previous_source_version or bool(previous_source_batch_id) else "failed",
            expected_value="previous_source_batch_id when previous_source_version is set",
            actual_value=str(bool(previous_source_batch_id)),
            details={"previous_source_version": previous_source_version},
        ),
        QualityGateResult(
            gate_name="active_source_sql_templates_only",
            status="passed",
            expected_value="dry-run templates; no database execution",
            actual_value="will_execute_sql=false",
            details={},
        ),
    ]


def normalize_quality_gate(gate: QualityGateResult | Mapping[str, Any]) -> QualityGateResult:
    if isinstance(gate, QualityGateResult):
        return gate
    return QualityGateResult(
        gate_name=str(gate.get("gate_name") or "unnamed_quality_gate"),
        status=str(gate.get("status") or "failed"),
        severity=str(gate.get("severity") or "P0"),
        expected_value=optional_str(gate.get("expected_value")),
        actual_value=optional_str(gate.get("actual_value")),
        details=gate.get("details") if isinstance(gate.get("details"), Mapping) else {},
    )


def quality_gate_to_dict(gate: QualityGateResult) -> dict[str, Any]:
    return {
        "gate_name": gate.gate_name,
        "status": gate.status,
        "severity": gate.severity,
        "expected_value": gate.expected_value,
        "actual_value": gate.actual_value,
        "details": dict(gate.details or {}),
    }


def normalize_safe_value(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise IngestionValidationError(f"{field_name} is required")
    if not SAFE_VALUE_RE.match(text):
        raise IngestionValidationError(f"{field_name} is not safe for activation plan: {value!r}")
    return text


def normalize_optional_safe_value(value: str | None, field_name: str) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return normalize_safe_value(str(value), field_name)


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
