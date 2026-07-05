"""Preflight confirmation checklist before any real raw-ingestion execution.

This module only turns the dry-run control report into a list of confirmations
that must be reviewed before real source reads, PostgreSQL writes, or Parquet
archive writes are allowed. It never calls external APIs, reads local TDX files,
connects PostgreSQL, executes SQL, writes Parquet, or creates files under the
data root.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.ingestion_dry_run_control import IngestionDryRunControlReport


REQUIRED_PREFLIGHT_CATEGORIES = ("scope", "stage", "secret", "source", "database", "archive", "quality_gate", "rollback", "safety")


@dataclass(frozen=True)
class PreflightConfirmationItem:
    item_id: str
    category: str
    description: str
    required_confirmation: str
    evidence: Mapping[str, Any]
    confirmed: bool = False
    severity: str = "P0"

    @property
    def status(self) -> str:
        return "confirmed" if self.confirmed else "pending_user_confirmation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "description": self.description,
            "required_confirmation": self.required_confirmation,
            "severity": self.severity,
            "status": self.status,
            "confirmed": self.confirmed,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ExecutionPreflightChecklist:
    dry_run_control_passed: bool
    initial_config_path: str
    daily_config_path: str
    confirmation_items: tuple[PreflightConfirmationItem, ...]
    quality_gates: tuple[QualityGateResult, ...]
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False

    @property
    def passed(self) -> bool:
        return self.dry_run_control_passed and all(gate.passed for gate in self.quality_gates)

    @property
    def ready_to_execute(self) -> bool:
        return self.dry_run_control_passed and all(item.confirmed for item in self.confirmation_items)

    @property
    def pending_item_ids(self) -> tuple[str, ...]:
        return tuple(item.item_id for item in self.confirmation_items if not item.confirmed)

    @property
    def category_counts(self) -> dict[str, int]:
        return dict(Counter(item.category for item in self.confirmation_items))

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run_control_passed": self.dry_run_control_passed,
            "initial_config_path": self.initial_config_path,
            "daily_config_path": self.daily_config_path,
            "passed": self.passed,
            "ready_to_execute": self.ready_to_execute,
            "pending_item_ids": list(self.pending_item_ids),
            "category_counts": self.category_counts,
            "confirmation_items": [item.to_dict() for item in self.confirmation_items],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
            },
        }


def build_execution_preflight_checklist(
    control_report: IngestionDryRunControlReport,
    confirmed_item_ids: Iterable[str] | None = None,
) -> ExecutionPreflightChecklist:
    confirmed = set(confirmed_item_ids or ())
    items = tuple(build_preflight_items(control_report, confirmed))
    gates = tuple(build_preflight_quality_gates(control_report, items))
    return ExecutionPreflightChecklist(
        dry_run_control_passed=control_report.passed,
        initial_config_path=control_report.initial_config_path,
        daily_config_path=control_report.daily_config_path,
        confirmation_items=items,
        quality_gates=gates,
    )


def build_preflight_items(
    control_report: IngestionDryRunControlReport,
    confirmed_item_ids: set[str],
) -> list[PreflightConfirmationItem]:
    item_specs = [
        (
            "scope.raw_ingestion_only",
            "scope",
            "Execution scope remains limited to the raw-ingestion layer.",
            "Confirm no condition, trigger, action, voice, sim, frontend, worker, or trading work is included.",
            {"allowed_domains": ["common", "stock", "index", "board"]},
        ),
        (
            "stage.one_stage_at_a_time",
            "stage",
            "Real execution must be approved one stage at a time.",
            "Confirm whether the next real stage is initial_backfill or daily_incremental before running it.",
            {
                "initial_batch_count": control_report.initial_backfill.batch_count,
                "daily_task_count": control_report.daily_incremental.task_count,
            },
        ),
        (
            "secret.tushare_token_env",
            "secret",
            "Tushare token must be provided outside the repository.",
            "Confirm TUSHARE_TOKEN is available via environment or local secret manager and is not written to files.",
            {"env_var": "TUSHARE_TOKEN", "store_secret_in_config": False},
        ),
        (
            "secret.postgres_dsn_env",
            "secret",
            "PostgreSQL DSN must be provided outside the repository.",
            "Confirm ASHARE_V3_POSTGRES_DSN is available via environment or local secret manager and is not written to files.",
            {"env_var": "ASHARE_V3_POSTGRES_DSN", "store_secret_in_config": False},
        ),
        (
            "source.tushare_network",
            "source",
            "External Tushare reads require explicit approval before real execution.",
            "Confirm network source reads are allowed for trade calendar, stock identity, index identity, stock daily, daily_basic, and fallback fields.",
            {"requires_network": True},
        ),
        (
            "source.mootdx_network",
            "source",
            "Mootdx/TDX quote and finance reads require explicit approval before real execution.",
            "Confirm Mootdx reads are allowed for index daily, board daily, and financial primary fields.",
            {"requires_network_or_tdx_client": True},
        ),
        (
            "source.tdx_local_txt_read",
            "source",
            "Local TDX txt reads require explicit approval before real execution.",
            "Confirm reading /Volumes/MacRaid/tdxdata/tdx is allowed for board identity and membership snapshots.",
            {"tdx_root": "/Volumes/MacRaid/tdxdata/tdx"},
        ),
        (
            "database.postgresql_schema_and_write",
            "database",
            "PostgreSQL write execution requires schema and DSN confirmation.",
            "Confirm PostgreSQL schema has been reviewed/applied separately and writes are allowed only after quality gates pass.",
            {"database": "PostgreSQL", "dsn_env_var": "ASHARE_V3_POSTGRES_DSN"},
        ),
        (
            "archive.data_root_write",
            "archive",
            "Parquet archive and manifest writes require data-root confirmation.",
            "Confirm writes under /Volumes/MacRaid/database are allowed and old system paths remain untouched.",
            {"data_root": "/Volumes/MacRaid/database"},
        ),
        (
            "quality_gate.activation_blocking",
            "quality_gate",
            "Quality gates must block active source_version activation.",
            "Confirm P0 quality gate failures stop activation and preserve failed audit evidence.",
            {"control_quality_gate_count": len(control_report.quality_gates)},
        ),
        (
            "rollback.source_batch_restore",
            "rollback",
            "Rollback must be confirmed before any write stage.",
            "Confirm rollback deletes by source_batch_id and restores previous active source_version.",
            {
                "initial_rollback_groups": control_report.initial_backfill.rollback_group_count,
                "daily_rollback_groups": control_report.daily_incremental.rollback_group_count,
            },
        ),
        (
            "safety.old_system_boundary",
            "safety",
            "Old system paths, databases, services, and LaunchAgents remain forbidden.",
            "Confirm no old system reads, writes, migrations, service starts, or LaunchAgent changes are included.",
            {"old_system_access": "forbidden"},
        ),
        (
            "safety.no_worker_or_service_start",
            "safety",
            "Real ingestion confirmation does not authorize worker or long-running service startup.",
            "Confirm any worker/service startup remains out of scope and requires a separate approval.",
            {"worker_start": "forbidden"},
        ),
    ]
    return [
        PreflightConfirmationItem(
            item_id=item_id,
            category=category,
            description=description,
            required_confirmation=required_confirmation,
            evidence=evidence,
            confirmed=item_id in confirmed_item_ids,
        )
        for item_id, category, description, required_confirmation, evidence in item_specs
    ]


def build_preflight_quality_gates(
    control_report: IngestionDryRunControlReport,
    items: tuple[PreflightConfirmationItem, ...],
) -> list[QualityGateResult]:
    categories = Counter(item.category for item in items)
    side_effect_violations = []
    if any(
        (
            control_report.will_call_external_sources,
            control_report.will_read_tdx_files,
            control_report.will_connect_database,
            control_report.will_execute_sql,
            control_report.will_write_data_files,
        )
    ):
        side_effect_violations.append("control_report")

    return [
        QualityGateResult(
            gate_name="preflight_control_report_passed",
            status="passed" if control_report.passed else "failed",
            expected_value="dry-run control report passed",
            actual_value=str(control_report.passed).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="preflight_items_present",
            status="passed" if items else "failed",
            expected_value=">0",
            actual_value=str(len(items)),
            details={},
        ),
        QualityGateResult(
            gate_name="preflight_required_categories_present",
            status="passed" if all(category in categories for category in REQUIRED_PREFLIGHT_CATEGORIES) else "failed",
            expected_value="/".join(REQUIRED_PREFLIGHT_CATEGORIES),
            actual_value=",".join(sorted(categories)),
            details={"category_counts": dict(categories)},
        ),
        QualityGateResult(
            gate_name="preflight_confirmation_state_explicit",
            status="passed" if all(item.status in {"confirmed", "pending_user_confirmation"} for item in items) else "failed",
            expected_value="confirmed or pending_user_confirmation",
            actual_value=str(len(items)),
            details={"pending_item_ids": [item.item_id for item in items if not item.confirmed]},
        ),
        QualityGateResult(
            gate_name="preflight_no_side_effects",
            status="passed" if not side_effect_violations else "failed",
            expected_value="no source calls, no TDX reads, no DB, no SQL, no data file writes",
            actual_value=str(len(side_effect_violations)),
            details={"violations": side_effect_violations},
        ),
    ]
