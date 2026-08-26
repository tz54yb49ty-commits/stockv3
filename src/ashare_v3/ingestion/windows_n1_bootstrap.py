"""Fail-closed orchestration for the Windows N1 zero-database bootstrap."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .windows_n1_sources import three_year_start


N1_BOOTSTRAP_STAGES = (
    "schema",
    "scope",
    "identity_membership",
    "daily_bars",
    "eltdx_finance",
    "daily_basic",
    "activate_n1_sources",
    "n1_data_ready",
)
FORBIDDEN_STAGES = ("trade_calendar", "calendar_repair", "n2", "n3", "n4", "n5", "n6")


@dataclass(frozen=True)
class WindowsN1BootstrapConfig:
    artifact_root: Path
    end_date: str
    start_date: str
    tq_url: str = "http://127.0.0.1:17709"

    @classmethod
    def for_today(cls, *, artifact_root: Path, today: date) -> "WindowsN1BootstrapConfig":
        return cls(artifact_root=artifact_root, start_date=three_year_start(today), end_date=today.strftime("%Y%m%d"))


@dataclass
class BootstrapResult:
    run_id: str
    completed_stages: list[str] = field(default_factory=list)
    security_failures: list[dict[str, Any]] = field(default_factory=list)
    finance_gate_passed: bool = False
    n1_data_ready: bool = False


def write_security_failure(
    *, artifact_root: Path, run_id: str, symbol: str, stage: str, error: BaseException
) -> Path:
    safe_symbol = "".join(char if char.isalnum() or char in "._-" else "_" for char in symbol)
    run_dir = artifact_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{stage}__{safe_symbol}.json"
    path.write_text(json.dumps({
        "schema_version": "WindowsN1SecurityFailure.v1",
        "run_id": run_id,
        "stage": stage,
        "symbol": symbol,
        "error_type": type(error).__name__,
        "error": str(error),
        "other_security_rows_rolled_back": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_security_items(
    *, items: Sequence[str], stage: str, run_id: str, artifact_root: Path,
    worker: Callable[[str], None], result: BootstrapResult,
) -> None:
    for symbol in items:
        try:
            worker(symbol)
        except Exception as error:  # single-security isolation is intentional
            artifact = write_security_failure(
                artifact_root=artifact_root, run_id=run_id, symbol=symbol, stage=stage, error=error,
            )
            result.security_failures.append({"symbol": symbol, "stage": stage, "artifact": str(artifact)})


def execute_bootstrap(
    *, config: WindowsN1BootstrapConfig,
    stage_handlers: Mapping[str, Callable[[BootstrapResult], None]],
) -> BootstrapResult:
    unknown = set(stage_handlers) - set(N1_BOOTSTRAP_STAGES)
    if unknown:
        raise RuntimeError(f"non-N1 or unknown bootstrap stages rejected: {sorted(unknown)}")
    run_id = "windows_n1_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = BootstrapResult(run_id=run_id)
    for stage in N1_BOOTSTRAP_STAGES:
        handler = stage_handlers.get(stage)
        if handler is None:
            raise RuntimeError(f"missing fail-closed stage handler: {stage}")
        handler(result)
        result.completed_stages.append(stage)
        if stage == "eltdx_finance" and not result.finance_gate_passed:
            raise RuntimeError("eltdx finance gate failed; no fallback source allowed")
    result.n1_data_ready = result.completed_stages == list(N1_BOOTSTRAP_STAGES)
    return result
