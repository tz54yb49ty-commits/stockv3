"""Real-execution configuration template validation.

This loader validates the N3.1 real-execution configuration template. It never
reads secret values, calls external APIs, reads local TDX files, connects
PostgreSQL, executes SQL, writes Parquet, or creates files under the data root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Mapping

from ashare_v3.ingestion.common import IngestionValidationError
from ashare_v3.ingestion.execution_preflight import REQUIRED_PREFLIGHT_CATEGORIES
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT


DEFAULT_REAL_EXECUTION_CONFIG = "configs/real_execution.example.toml"
EXPECTED_CONFIRMATION_ITEMS = (
    "scope.raw_ingestion_only",
    "stage.one_stage_at_a_time",
    "secret.tushare_token_env",
    "secret.postgres_dsn_env",
    "source.tushare_network",
    "source.mootdx_network",
    "source.tdx_local_txt_read",
    "database.postgresql_schema_and_write",
    "archive.data_root_write",
    "quality_gate.activation_blocking",
    "rollback.source_batch_restore",
    "safety.old_system_boundary",
    "safety.no_worker_or_service_start",
)


@dataclass(frozen=True)
class RealExecutionConfig:
    mode: str
    approved_stage: str
    allow_real_execution: bool
    operator_confirmation_id: str
    initial_backfill_config: str
    daily_incremental_config: str
    data_root: str
    tdx_root: str
    tushare_token_env: str
    postgres_dsn_env: str
    permissions: Mapping[str, bool]
    quality_gate: Mapping[str, bool]
    rollback: Mapping[str, Any]
    required_confirmation_items: tuple[str, ...]

    @property
    def ready_to_execute(self) -> bool:
        return self.allow_real_execution and self.approved_stage in {"initial_backfill", "daily_incremental"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "approved_stage": self.approved_stage,
            "allow_real_execution": self.allow_real_execution,
            "operator_confirmation_id": self.operator_confirmation_id,
            "ready_to_execute": self.ready_to_execute,
            "configs": {
                "initial_backfill_config": self.initial_backfill_config,
                "daily_incremental_config": self.daily_incremental_config,
            },
            "paths": {
                "data_root": self.data_root,
                "tdx_root": self.tdx_root,
            },
            "security": {
                "tushare_token_env": self.tushare_token_env,
                "postgres_dsn_env": self.postgres_dsn_env,
                "store_secret_in_config": False,
            },
            "permissions": dict(self.permissions),
            "quality_gate": dict(self.quality_gate),
            "rollback": dict(self.rollback),
            "preflight": {
                "required_confirmation_items": list(self.required_confirmation_items),
                "required_category_count": len(REQUIRED_PREFLIGHT_CATEGORIES),
            },
        }


def load_real_execution_config(path: str | Path = DEFAULT_REAL_EXECUTION_CONFIG) -> RealExecutionConfig:
    config_path = Path(path)
    with config_path.open("rb") as file_obj:
        data = tomllib.load(file_obj)
    return real_execution_config_from_mapping(data)


def real_execution_config_from_mapping(data: Mapping[str, Any]) -> RealExecutionConfig:
    real_execution = require_mapping(data.get("real_execution"), "real_execution")
    configs = require_mapping(data.get("configs"), "configs")
    paths = require_mapping(data.get("paths"), "paths")
    security = require_mapping(data.get("security"), "security")
    permissions = require_mapping(data.get("permissions"), "permissions")
    quality_gate = require_mapping(data.get("quality_gate"), "quality_gate")
    rollback = require_mapping(data.get("rollback"), "rollback")
    preflight = require_mapping(data.get("preflight"), "preflight")

    reject_embedded_secrets(security)
    normalized_permissions = validate_permissions(permissions)
    normalized_quality_gate = validate_quality_gate(quality_gate)
    normalized_rollback = validate_rollback(rollback)
    required_confirmation_items = validate_required_confirmation_items(preflight.get("required_confirmation_items"))

    mode = require_value(real_execution.get("mode"), "real_execution.mode")
    if mode != "preflight_only":
        raise IngestionValidationError("real_execution.mode must be preflight_only in N3.1 template")
    approved_stage = require_value(real_execution.get("approved_stage"), "real_execution.approved_stage")
    if approved_stage != "none":
        raise IngestionValidationError("real_execution.approved_stage must be none in N3.1 template")
    allow_real_execution = real_execution.get("allow_real_execution")
    if allow_real_execution is not False:
        raise IngestionValidationError("real_execution.allow_real_execution must be false in N3.1 template")

    return RealExecutionConfig(
        mode=mode,
        approved_stage=approved_stage,
        allow_real_execution=False,
        operator_confirmation_id=str(real_execution.get("operator_confirmation_id") or ""),
        initial_backfill_config=require_value(configs.get("initial_backfill_config"), "configs.initial_backfill_config"),
        daily_incremental_config=require_value(configs.get("daily_incremental_config"), "configs.daily_incremental_config"),
        data_root=require_value(paths.get("data_root", DEFAULT_DATA_ROOT), "paths.data_root"),
        tdx_root=require_value(paths.get("tdx_root"), "paths.tdx_root"),
        tushare_token_env=require_value(security.get("tushare_token_env"), "security.tushare_token_env"),
        postgres_dsn_env=require_value(security.get("postgres_dsn_env"), "security.postgres_dsn_env"),
        permissions=normalized_permissions,
        quality_gate=normalized_quality_gate,
        rollback=normalized_rollback,
        required_confirmation_items=required_confirmation_items,
    )


def validate_permissions(permissions: Mapping[str, Any]) -> dict[str, bool]:
    expected_flags = (
        "allow_network",
        "allow_tdx_file_read",
        "allow_database_write",
        "allow_data_file_write",
        "allow_worker_start",
        "allow_old_system_access",
    )
    normalized: dict[str, bool] = {}
    for flag in expected_flags:
        if permissions.get(flag) is not False:
            raise IngestionValidationError(f"permissions.{flag} must be false in N3.1 template")
        normalized[flag] = False
    return normalized


def validate_quality_gate(quality_gate: Mapping[str, Any]) -> dict[str, bool]:
    expected_true_flags = (
        "block_on_p0",
        "require_identity_key_coverage",
        "require_physical_table_split",
        "require_official_daily_proof",
        "require_stock_daily_basic_universe",
        "require_active_source_version_rollback",
    )
    normalized: dict[str, bool] = {}
    for flag in expected_true_flags:
        if quality_gate.get(flag) is not True:
            raise IngestionValidationError(f"quality_gate.{flag} must be true")
        normalized[flag] = True
    return normalized


def validate_rollback(rollback: Mapping[str, Any]) -> dict[str, Any]:
    expected_strategy = "delete_by_source_batch_id_then_restore_previous_active_source_version"
    if rollback.get("strategy") != expected_strategy:
        raise IngestionValidationError(f"rollback.strategy must be {expected_strategy}")
    expected_true_flags = (
        "require_source_batch_id_delete",
        "require_previous_active_source_version_restore",
        "require_manifest_rollback_plan",
        "require_failed_audit_retention",
    )
    normalized: dict[str, Any] = {"strategy": expected_strategy}
    for flag in expected_true_flags:
        if rollback.get(flag) is not True:
            raise IngestionValidationError(f"rollback.{flag} must be true")
        normalized[flag] = True
    return normalized


def validate_required_confirmation_items(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise IngestionValidationError("preflight.required_confirmation_items must be a string list")
    items = tuple(value)
    missing = sorted(set(EXPECTED_CONFIRMATION_ITEMS) - set(items))
    extra = sorted(set(items) - set(EXPECTED_CONFIRMATION_ITEMS))
    if missing or extra or len(items) != len(set(items)):
        raise IngestionValidationError(f"preflight.required_confirmation_items mismatch: missing={missing}, extra={extra}")
    return items


def reject_embedded_secrets(security: Mapping[str, Any]) -> None:
    bad_keys = [
        key
        for key in security
        if ("token" in key.lower() or "dsn" in key.lower()) and not key.endswith("_env")
    ]
    if bad_keys:
        raise IngestionValidationError(f"security secrets must be env var names only: {bad_keys}")
    if security.get("store_secret_in_config") is not False:
        raise IngestionValidationError("security.store_secret_in_config must be false")


def require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IngestionValidationError(f"{field_name} must be a table")
    return value


def require_value(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise IngestionValidationError(f"{field_name} is required")
    return text
