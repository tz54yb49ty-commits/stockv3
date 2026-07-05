"""Daily incremental raw-ingestion configuration loading for dry-run plans.

The loader only reads an explicit local TOML file and validates that it matches
the approved raw-ingestion daily dry-run scope. It never calls data sources,
reads local TDX files, opens a database connection, executes SQL, or writes
files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Mapping

from ashare_v3.ingestion.batch_orchestration import CORE_DAILY_TASK_SPECS, DailyIngestionOrchestrationPlan, build_daily_ingestion_orchestration_plan
from ashare_v3.ingestion.common import IngestionValidationError, require_yyyymmdd
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT


DEFAULT_DAILY_INCREMENTAL_CONFIG = "configs/daily_incremental.example.toml"


@dataclass(frozen=True)
class DailyIncrementalConfig:
    trade_date: str
    version: str
    data_root: str
    tdx_root: str
    tushare_token_env: str
    postgres_dsn_env: str
    sources: Mapping[str, Mapping[str, Any]]
    side_effects: Mapping[str, bool]

    def to_plan(self) -> DailyIngestionOrchestrationPlan:
        return build_daily_ingestion_orchestration_plan(
            trade_date=self.trade_date,
            version=self.version,
            data_root=self.data_root,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "version": self.version,
            "data_root": self.data_root,
            "tdx_root": self.tdx_root,
            "tushare_token_env": self.tushare_token_env,
            "postgres_dsn_env": self.postgres_dsn_env,
            "sources": {key: dict(value) for key, value in self.sources.items()},
            "side_effects": dict(self.side_effects),
        }


def load_daily_incremental_config(path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG) -> DailyIncrementalConfig:
    config_path = Path(path)
    with config_path.open("rb") as file_obj:
        data = tomllib.load(file_obj)
    return daily_incremental_config_from_mapping(data)


def daily_incremental_config_from_mapping(data: Mapping[str, Any]) -> DailyIncrementalConfig:
    daily = require_mapping(data.get("daily_incremental"), "daily_incremental")
    paths = require_mapping(data.get("paths"), "paths")
    security = require_mapping(data.get("security"), "security")
    side_effects = require_mapping(data.get("side_effects"), "side_effects")
    sources = require_mapping(data.get("sources"), "sources")

    reject_embedded_secrets(security)
    normalized_side_effects = validate_side_effects(side_effects)
    normalized_sources = validate_sources(sources)

    trade_date = require_yyyymmdd(str(daily.get("trade_date") or ""), "daily_incremental.trade_date")
    version = validate_version(str(daily.get("version") or "v1"))
    data_root = require_nonempty_string(paths.get("data_root", DEFAULT_DATA_ROOT), "paths.data_root")
    tdx_root = require_nonempty_string(paths.get("tdx_root"), "paths.tdx_root")
    tushare_token_env = require_nonempty_string(security.get("tushare_token_env"), "security.tushare_token_env")
    postgres_dsn_env = require_nonempty_string(security.get("postgres_dsn_env"), "security.postgres_dsn_env")

    return DailyIncrementalConfig(
        trade_date=trade_date,
        version=version,
        data_root=data_root,
        tdx_root=tdx_root,
        tushare_token_env=tushare_token_env,
        postgres_dsn_env=postgres_dsn_env,
        sources=normalized_sources,
        side_effects=normalized_side_effects,
    )


def build_daily_incremental_plan_from_config(path: str | Path = DEFAULT_DAILY_INCREMENTAL_CONFIG) -> DailyIngestionOrchestrationPlan:
    return load_daily_incremental_config(path).to_plan()


def validate_sources(sources: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected_specs = {spec.task_id: spec for spec in CORE_DAILY_TASK_SPECS}
    source_keys = set(sources)
    expected_keys = set(expected_specs)
    missing = sorted(expected_keys - source_keys)
    extra = sorted(source_keys - expected_keys)
    if missing or extra:
        raise IngestionValidationError(f"daily incremental sources mismatch: missing={missing}, extra={extra}")

    normalized: dict[str, Mapping[str, Any]] = {}
    for task_id, spec in expected_specs.items():
        source_config = require_mapping(sources[task_id], f"sources.{task_id}")
        expected_values = {
            "target_table": spec.table_name,
            "data_domain": spec.data_domain,
            "data_type": spec.data_type,
            "source": spec.source,
        }
        mismatches = {
            key: {"expected": expected_value, "actual": source_config.get(key)}
            for key, expected_value in expected_values.items()
            if source_config.get(key) != expected_value
        }
        if mismatches:
            raise IngestionValidationError(f"sources.{task_id} does not match approved daily plan: {mismatches}")
        normalized[task_id] = dict(source_config)
    return normalized


def validate_side_effects(side_effects: Mapping[str, Any]) -> dict[str, bool]:
    expected_flags = (
        "allow_network",
        "allow_tdx_file_read",
        "allow_database_write",
        "allow_data_file_write",
        "allow_worker_start",
    )
    normalized: dict[str, bool] = {}
    for flag in expected_flags:
        value = side_effects.get(flag)
        if value is not False:
            raise IngestionValidationError(f"side_effects.{flag} must be false in N2.15 dry-run config")
        normalized[flag] = False
    return normalized


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


def validate_version(version: str) -> str:
    text = str(version).strip()
    if not text.startswith("v") or len(text) < 2 or not text[1:].isdigit():
        raise IngestionValidationError(f"version must look like vN: {version!r}")
    return text


def require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IngestionValidationError(f"{field_name} must be a table")
    return value


def require_nonempty_string(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise IngestionValidationError(f"{field_name} is required")
    return text
