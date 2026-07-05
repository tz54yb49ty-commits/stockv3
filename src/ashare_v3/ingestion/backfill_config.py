"""Initial backfill configuration loading for dry-run plans.

The loader only reads an explicit local TOML file and validates that it matches
the approved raw-ingestion dry-run scope. It never calls data sources, opens a
database connection, executes SQL, or writes files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Mapping

from ashare_v3.ingestion.backfill_plan import (
    MONTHLY_TASK_SPECS,
    RANGE_TASK_SPECS,
    SNAPSHOT_TASK_SPECS,
    InitialBackfillPlan,
    build_initial_backfill_plan,
    validate_version,
)
from ashare_v3.ingestion.common import IngestionValidationError, require_yyyymmdd
from ashare_v3.ingestion.parquet_archive import DEFAULT_DATA_ROOT


DEFAULT_INITIAL_BACKFILL_CONFIG = "configs/initial_backfill.example.toml"


@dataclass(frozen=True)
class InitialBackfillConfig:
    start_date: str
    end_date: str
    snapshot_date: str
    version: str
    data_root: str
    tdx_root: str
    tushare_token_env: str
    postgres_dsn_env: str
    sources: Mapping[str, Mapping[str, Any]]
    side_effects: Mapping[str, bool]

    def to_plan(self) -> InitialBackfillPlan:
        return build_initial_backfill_plan(
            start_date=self.start_date,
            end_date=self.end_date,
            snapshot_date=self.snapshot_date,
            version=self.version,
            data_root=self.data_root,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "snapshot_date": self.snapshot_date,
            "version": self.version,
            "data_root": self.data_root,
            "tdx_root": self.tdx_root,
            "tushare_token_env": self.tushare_token_env,
            "postgres_dsn_env": self.postgres_dsn_env,
            "sources": {key: dict(value) for key, value in self.sources.items()},
            "side_effects": dict(self.side_effects),
        }


def load_initial_backfill_config(path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG) -> InitialBackfillConfig:
    config_path = Path(path)
    with config_path.open("rb") as file_obj:
        data = tomllib.load(file_obj)
    return initial_backfill_config_from_mapping(data)


def initial_backfill_config_from_mapping(data: Mapping[str, Any]) -> InitialBackfillConfig:
    backfill = require_mapping(data.get("backfill"), "backfill")
    paths = require_mapping(data.get("paths"), "paths")
    security = require_mapping(data.get("security"), "security")
    side_effects = require_mapping(data.get("side_effects"), "side_effects")
    sources = require_mapping(data.get("sources"), "sources")

    reject_embedded_secrets(security)
    normalized_side_effects = validate_side_effects(side_effects)
    normalized_sources = validate_sources(sources)

    start_date = require_yyyymmdd(str(backfill.get("start_date") or ""), "backfill.start_date")
    end_date = require_yyyymmdd(str(backfill.get("end_date") or ""), "backfill.end_date")
    snapshot_date = require_yyyymmdd(str(backfill.get("snapshot_date") or end_date), "backfill.snapshot_date")
    version = validate_version(str(backfill.get("version") or "v1"))
    data_root = require_nonempty_string(paths.get("data_root", DEFAULT_DATA_ROOT), "paths.data_root")
    tdx_root = require_nonempty_string(paths.get("tdx_root"), "paths.tdx_root")
    tushare_token_env = require_nonempty_string(security.get("tushare_token_env"), "security.tushare_token_env")
    postgres_dsn_env = require_nonempty_string(security.get("postgres_dsn_env"), "security.postgres_dsn_env")

    return InitialBackfillConfig(
        start_date=start_date,
        end_date=end_date,
        snapshot_date=snapshot_date,
        version=version,
        data_root=data_root,
        tdx_root=tdx_root,
        tushare_token_env=tushare_token_env,
        postgres_dsn_env=postgres_dsn_env,
        sources=normalized_sources,
        side_effects=normalized_side_effects,
    )


def build_initial_backfill_plan_from_config(path: str | Path = DEFAULT_INITIAL_BACKFILL_CONFIG) -> InitialBackfillPlan:
    return load_initial_backfill_config(path).to_plan()


def validate_sources(sources: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected_specs = {
        spec.task_id: spec
        for spec in (*RANGE_TASK_SPECS, *SNAPSHOT_TASK_SPECS, *MONTHLY_TASK_SPECS)
    }
    source_keys = set(sources)
    expected_keys = set(expected_specs)
    missing = sorted(expected_keys - source_keys)
    extra = sorted(source_keys - expected_keys)
    if missing or extra:
        raise IngestionValidationError(f"initial backfill sources mismatch: missing={missing}, extra={extra}")

    normalized: dict[str, Mapping[str, Any]] = {}
    for task_id, spec in expected_specs.items():
        source_config = require_mapping(sources[task_id], f"sources.{task_id}")
        expected_values = {
            "target_table": spec.table_name,
            "data_domain": spec.data_domain,
            "data_type": spec.data_type,
            "source": spec.source,
            "slice_kind": spec.slice_kind,
        }
        mismatches = {
            key: {"expected": expected_value, "actual": source_config.get(key)}
            for key, expected_value in expected_values.items()
            if source_config.get(key) != expected_value
        }
        if mismatches:
            raise IngestionValidationError(f"sources.{task_id} does not match approved plan: {mismatches}")
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
            raise IngestionValidationError(f"side_effects.{flag} must be false in N2.12 dry-run config")
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


def require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IngestionValidationError(f"{field_name} must be a table")
    return value


def require_nonempty_string(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise IngestionValidationError(f"{field_name} is required")
    return text
