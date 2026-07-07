"""Post-close N1 -> N2 -> N3-A1 -> N4 context readiness orchestration.

The module builds a single bounded post-close command chain. It deliberately
stops after static pre-open readiness guards and does not enter intraday N3P,
N4 matchers, N5, N6, workers, or event-consumer status updates.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from ashare_v3.runtime.intraday_worker_lineage import (
    write_intraday_worker_lineage_config_after_fastlane_pass,
)


ASIA_SHANGHAI = timezone(timedelta(hours=8))
LAUNCHD_LABEL = "com.asharev3.postclose.n1-n2-n3a1"


@dataclass(frozen=True)
class ChildCommand:
    step_id: str
    layer_role: str
    argv: list[str]
    report_paths: list[str]


@dataclass(frozen=True)
class DateContext:
    source_trade_date: str
    for_trade_date: str
    prev_trade_date: str
    fallback_next_trade_date: str


def _json_result(path: Path | str) -> str | None:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    result = payload.get("result")
    return str(result) if result is not None else None


def _recovery_artifact_passed(command: ChildCommand) -> bool:
    execute_pass_steps = {
        "calendar_repair",
        "n1_source_facts",
        "n1_stock_financial_canonical_metrics",
        "n2_condition",
        "n3_subscription",
        "n3_a1_preload",
        "n3_a1_cumulative_amount",
        "n4_trigger_context_snapshot",
        "n4_context_rollback_ready",
        "preopen_readiness_noop",
        "lineage_pollution_guard",
        "worker_launchd_guard",
    }
    if command.step_id in execute_pass_steps:
        return any(
            Path(report_path).suffix == ".json"
            and _json_result(report_path) in {"EXECUTE_PASS", "IDEMPOTENT_PASS", "PASS"}
            for report_path in command.report_paths
        )
    if command.step_id == "n3_a0_preload_dry_run":
        return any(Path(report_path).suffix == ".json" and _json_result(report_path) in {"DRY_RUN_PASS", "PASS"} for report_path in command.report_paths)
    if command.step_id == "n3_a1_contract":
        results = {
            Path(report_path).name: _json_result(report_path)
            for report_path in command.report_paths
            if Path(report_path).suffix == ".json"
        }
        return (
            results.get("46_n3_a1_preload_contract.json") in {"CONTRACT_PASS", "PASS"}
            and results.get("47_n3_a1_preload_preflight.json") in {"PREFLIGHT_PASS", "PASS"}
        )
    if command.step_id != "n1_stock_financial_canonical_source_bundle":
        return False
    for report_path in command.report_paths:
        path = Path(report_path)
        if path.name.endswith("_preflight.json") and _json_result(path) == "PREFLIGHT_PASS":
            return True
    return False


def _report_has_step(report: dict[str, Any] | None, step_id: str) -> bool:
    return any(str(step.get("step_id") or "") == step_id for step in (report or {}).get("sub_steps") or [])


def condition_run_id_for(source_trade_date: str, for_trade_date: str) -> str:
    return f"condition_layer_{source_trade_date}_source_{source_trade_date}_for_{for_trade_date}_v1"


def subscription_run_id_for(source_trade_date: str, for_trade_date: str) -> str:
    condition_run_id = condition_run_id_for(source_trade_date, for_trade_date)
    return f"market_data_subscription_{for_trade_date}_{condition_run_id}"


def preload_run_id_for(source_trade_date: str, for_trade_date: str) -> str:
    subscription_run_id = subscription_run_id_for(source_trade_date, for_trade_date)
    return f"previous_day_minute_preload_{source_trade_date}_for_{for_trade_date}__{subscription_run_id}"


def n4_context_run_id_for(source_trade_date: str, for_trade_date: str) -> str:
    condition_run_id = condition_run_id_for(source_trade_date, for_trade_date)
    return f"trigger_context_snapshot_{for_trade_date}_{condition_run_id}__atomic_rule_v1"


def build_oneshot_child_commands(
    *,
    source_trade_date: str,
    for_trade_date: str,
    prev_trade_date: str,
    next_trade_date: str,
    dsn: str,
    docs_root: Path | str,
    sql_root: Path | str,
    include_calendar_repair: bool = False,
    python_executable: str = "python3",
) -> list[ChildCommand]:
    """Return the fixed post-close command sequence."""

    docs_dir = Path(docs_root) / for_trade_date
    sql_dir = Path(sql_root)
    condition_run_id = condition_run_id_for(source_trade_date, for_trade_date)
    subscription_run_id = subscription_run_id_for(source_trade_date, for_trade_date)
    preload_run_id = preload_run_id_for(source_trade_date, for_trade_date)
    commands: list[ChildCommand] = []

    if include_calendar_repair:
        calendar_json = docs_dir / "10_calendar_repair_execute_report.json"
        calendar_md = docs_dir / "10_calendar_repair_execute_report.md"
        commands.append(
            ChildCommand(
                step_id="calendar_repair",
                layer_role="N1_ingestion",
                argv=[
                    python_executable,
                    "scripts/run_trade_calendar_patch_once.py",
                    "--trade-date",
                    for_trade_date,
                    "--expected-prev-trade-date",
                    source_trade_date,
                    "--fallback-next-trade-date",
                    next_trade_date,
                    "--source-batch-id",
                    f"n1_trade_calendar_repair_{for_trade_date}_v1",
                    "--source-version",
                    f"n1_trade_calendar_repair_{for_trade_date}_v1",
                    "--dsn",
                    dsn,
                    "--json-report-path",
                    str(calendar_json),
                    "--markdown-report-path",
                    str(calendar_md),
                    "--rollback-sql-path",
                    str(sql_dir / f"N1_{for_trade_date}_trade_calendar_repair_rollback.sql"),
                    "--execute",
                    "--user-confirmed",
                    "--postgres-commit-enabled",
                ],
                report_paths=[str(calendar_json), str(calendar_md)],
            )
        )

    n1_json = docs_dir / "20_n1_source_facts_execute_report.json"
    n1_md = docs_dir / "20_n1_source_facts_execute_report.md"
    commands.append(
        ChildCommand(
            step_id="n1_source_facts",
            layer_role="N1_ingestion",
            argv=[
                python_executable,
                "scripts/run_n1_source_facts_once.py",
                "--trade-date",
                source_trade_date,
                "--for-trade-date",
                for_trade_date,
                "--prev-trade-date",
                prev_trade_date,
                "--next-trade-date",
                for_trade_date,
                "--dsn",
                dsn,
                "--execute-report-json",
                str(n1_json),
                "--execute-report-md",
                str(n1_md),
                "--rollback-sql-path",
                str(sql_dir / f"N1_{source_trade_date}_source_facts_guarded_runner_rollback.sql"),
                "--execute",
                "--user-confirmed",
                "--source-fetch-enabled",
                "--postgres-commit-enabled",
            ],
            report_paths=[str(n1_json), str(n1_md)],
        )
    )

    previous_financial_snapshot = Path(docs_root) / source_trade_date / "21_n1_stock_financial_canonical_snapshot_v1.json"
    financial_bundle_cache = docs_dir / "21_n1_stock_financial_canonical_snapshot_v1.json"
    financial_tushare_probe_cache = docs_dir / "21_n1_stock_financial_canonical_tushare_probe_cache.json"
    financial_bundle_dry_run_json = docs_dir / "21_n1_stock_financial_canonical_source_bundle_dry_run.json"
    financial_bundle_dry_run_md = docs_dir / "21_n1_stock_financial_canonical_source_bundle_dry_run.md"
    financial_bundle_contract_json = docs_dir / "21_n1_stock_financial_canonical_source_bundle_contract.json"
    financial_bundle_contract_md = docs_dir / "21_n1_stock_financial_canonical_source_bundle_contract.md"
    financial_bundle_preflight_json = docs_dir / "21_n1_stock_financial_canonical_source_bundle_preflight.json"
    financial_bundle_preflight_md = docs_dir / "21_n1_stock_financial_canonical_source_bundle_preflight.md"
    commands.append(
        ChildCommand(
            step_id="n1_stock_financial_canonical_source_bundle",
            layer_role="N1_ingestion",
            argv=[
                python_executable,
                "scripts/plan_stock_financial_canonical_source_bundle_once.py",
                "--source-trade-date",
                source_trade_date,
                "--dsn",
                dsn,
                "--source-fetch-enabled",
                "--incremental",
                "--previous-snapshot-path",
                str(previous_financial_snapshot),
                "--snapshot-cache-path",
                str(financial_bundle_cache),
                "--resume-cache-path",
                str(financial_tushare_probe_cache),
                "--dry-run-json",
                str(financial_bundle_dry_run_json),
                "--dry-run-md",
                str(financial_bundle_dry_run_md),
                "--contract-json",
                str(financial_bundle_contract_json),
                "--contract-md",
                str(financial_bundle_contract_md),
                "--preflight-json",
                str(financial_bundle_preflight_json),
                "--preflight-md",
                str(financial_bundle_preflight_md),
            ],
            report_paths=[
                str(financial_bundle_cache),
                str(financial_tushare_probe_cache),
                str(financial_bundle_dry_run_json),
                str(financial_bundle_dry_run_md),
                str(financial_bundle_contract_json),
                str(financial_bundle_contract_md),
                str(financial_bundle_preflight_json),
                str(financial_bundle_preflight_md),
            ],
        )
    )

    financial_execute_json = docs_dir / "22_n1_stock_financial_canonical_execute_report.json"
    financial_execute_md = docs_dir / "22_n1_stock_financial_canonical_execute_report.md"
    financial_dry_run_json = docs_dir / "22_n1_stock_financial_canonical_dry_run.json"
    financial_dry_run_md = docs_dir / "22_n1_stock_financial_canonical_dry_run.md"
    financial_contract_json = docs_dir / "22_n1_stock_financial_canonical_contract.json"
    financial_contract_md = docs_dir / "22_n1_stock_financial_canonical_contract.md"
    financial_preflight_json = docs_dir / "22_n1_stock_financial_canonical_preflight.json"
    financial_preflight_md = docs_dir / "22_n1_stock_financial_canonical_preflight.md"
    financial_rollback_sql = sql_dir / f"N1_stock_financial_canonical_metrics_{source_trade_date}_rollback.sql"
    commands.append(
        ChildCommand(
            step_id="n1_stock_financial_canonical_metrics",
            layer_role="N1_ingestion",
            argv=[
                python_executable,
                "scripts/run_stock_financial_canonical_metrics_once.py",
                "--source-trade-date",
                source_trade_date,
                "--target-source-version",
                f"stock_financial_{source_trade_date}_v2",
                "--dsn",
                dsn,
                "--source-bundle-cache-path",
                str(financial_bundle_cache),
                "--dry-run-json",
                str(financial_dry_run_json),
                "--dry-run-md",
                str(financial_dry_run_md),
                "--contract-json",
                str(financial_contract_json),
                "--contract-md",
                str(financial_contract_md),
                "--preflight-json",
                str(financial_preflight_json),
                "--preflight-md",
                str(financial_preflight_md),
                "--json-report-path",
                str(financial_execute_json),
                "--markdown-report-path",
                str(financial_execute_md),
                "--rollback-sql-path",
                str(financial_rollback_sql),
                "--execute",
                "--user-confirmed",
                "--postgres-commit-enabled",
            ],
            report_paths=[
                str(financial_execute_json),
                str(financial_execute_md),
                str(financial_dry_run_json),
                str(financial_dry_run_md),
                str(financial_contract_json),
                str(financial_contract_md),
                str(financial_preflight_json),
                str(financial_preflight_md),
                str(financial_rollback_sql),
            ],
        )
    )

    n2_json = docs_dir / "30_n2_condition_execute_report.json"
    commands.append(
        ChildCommand(
            step_id="n2_condition",
            layer_role="N2_condition",
            argv=[
                python_executable,
                "scripts/run_condition_layer_execute.py",
                "--source-trade-date",
                source_trade_date,
                "--dsn",
                dsn,
                "--run-id",
                condition_run_id,
                "--report-path",
                str(n2_json),
                "--execute",
                "--user-confirmed",
                "--json",
            ],
            report_paths=[str(n2_json)],
        )
    )

    n3_json = docs_dir / "40_n3_subscription_execute_report.json"
    n3_md = docs_dir / "40_n3_subscription_execute_report.md"
    commands.append(
        ChildCommand(
            step_id="n3_subscription",
            layer_role="N3_market_data",
            argv=[
                python_executable,
                "scripts/run_market_data_subscription_execute.py",
                "--dsn",
                dsn,
                "--source-condition-run-id",
                condition_run_id,
                "--source-trade-date",
                source_trade_date,
                "--for-trade-date",
                for_trade_date,
                "--market-data-run-id",
                subscription_run_id,
                "--json-report-path",
                str(n3_json),
                "--markdown-report-path",
                str(n3_md),
                "--execute",
                "--user-confirmed",
                "--json",
            ],
            report_paths=[str(n3_json), str(n3_md)],
        )
    )

    a0_json = docs_dir / "45_n3_a0_previous_day_minute_preload_dry_run.json"
    a0_md = docs_dir / "45_n3_a0_previous_day_minute_preload_dry_run.md"
    commands.append(
        ChildCommand(
            step_id="n3_a0_preload_dry_run",
            layer_role="N3_market_data",
            argv=[
                python_executable,
                "scripts/plan_previous_day_minute_preload.py",
                "--dsn",
                dsn,
                "--run-id",
                subscription_run_id,
                "--source-trade-date",
                source_trade_date,
                "--for-trade-date",
                for_trade_date,
                "--expected-previous-day-minute-date",
                source_trade_date,
                "--report-path",
                str(a0_md),
                "--json-report-path",
                str(a0_json),
                "--json",
            ],
            report_paths=[str(a0_json), str(a0_md)],
        )
    )

    a1_contract_json = docs_dir / "46_n3_a1_preload_contract.json"
    a1_contract_md = docs_dir / "46_n3_a1_preload_contract.md"
    a1_preflight_json = docs_dir / "47_n3_a1_preload_preflight.json"
    a1_preflight_md = docs_dir / "47_n3_a1_preload_preflight.md"
    a1_rollback_sql = sql_dir / f"N3_A1_previous_day_minute_preload_{source_trade_date}_for_{for_trade_date}_rollback.sql"
    commands.append(
        ChildCommand(
            step_id="n3_a1_contract",
            layer_role="N3_market_data",
            argv=[
                python_executable,
                "scripts/plan_previous_day_minute_execute_contract.py",
                "--dsn",
                dsn,
                "--run-id",
                subscription_run_id,
                "--a0-report-path",
                str(a0_json),
                "--json-report-path",
                str(a1_contract_json),
                "--markdown-report-path",
                str(a1_contract_md),
                "--preflight-json-path",
                str(a1_preflight_json),
                "--preflight-markdown-path",
                str(a1_preflight_md),
                "--rollback-sql-path",
                str(a1_rollback_sql),
                "--preload-run-id",
                preload_run_id,
                "--json",
            ],
            report_paths=[
                str(a1_contract_json),
                str(a1_contract_md),
                str(a1_preflight_json),
                str(a1_preflight_md),
                str(a1_rollback_sql),
            ],
        )
    )

    a1_json = docs_dir / "50_n3_a1_preload_execute_report.json"
    a1_md = docs_dir / "50_n3_a1_preload_execute_report.md"
    commands.append(
        ChildCommand(
            step_id="n3_a1_preload",
            layer_role="N3_market_data",
            argv=[
                python_executable,
                "scripts/run_previous_day_minute_preload_execute.py",
                "--dsn",
                dsn,
                "--contract-path",
                str(a1_contract_json),
                "--source-subscription-run-id",
                subscription_run_id,
                "--preload-run-id",
                preload_run_id,
                "--data-trade-date",
                source_trade_date,
                "--json-report-path",
                str(a1_json),
                "--markdown-report-path",
                str(a1_md),
                "--execute",
                "--user-confirmed",
                "--historical-preload",
                "--json",
            ],
            report_paths=[str(a1_json), str(a1_md)],
        )
    )
    cumulative_json = docs_dir / "51_n3_a1_cumulative_amount_execute_report.json"
    cumulative_md = docs_dir / "51_n3_a1_cumulative_amount_execute_report.md"
    cumulative_rollback_sql = sql_dir / f"N3_A1_previous_day_minute_cumulative_{source_trade_date}_for_{for_trade_date}_rollback.sql"
    commands.append(
        ChildCommand(
            step_id="n3_a1_cumulative_amount",
            layer_role="N3_market_data",
            argv=[
                python_executable,
                "scripts/run_previous_day_cumulative_amount_execute.py",
                "--dsn",
                dsn,
                "--source-previous-day-minute-run-id",
                preload_run_id,
                "--for-trade-date",
                for_trade_date,
                "--source-trade-date",
                source_trade_date,
                "--json-report-path",
                str(cumulative_json),
                "--markdown-report-path",
                str(cumulative_md),
                "--rollback-sql-path",
                str(cumulative_rollback_sql),
                "--execute",
                "--user-confirmed",
                "--json",
            ],
            report_paths=[str(cumulative_json), str(cumulative_md), str(cumulative_rollback_sql)],
        )
    )
    n4_context_run_id = n4_context_run_id_for(source_trade_date, for_trade_date)
    n4_context_json = docs_dir / "52_n4_trigger_context_snapshot_execute_report.json"
    n4_context_md = docs_dir / "52_n4_trigger_context_snapshot_execute_report.md"
    n4_context_rollback_sql = sql_dir / f"N4_trigger_context_snapshot_{for_trade_date}_rollback.sql"
    commands.append(
        ChildCommand(
            step_id="n4_trigger_context_snapshot",
            layer_role="N4_trigger",
            argv=[
                python_executable,
                "scripts/run_trigger_context_snapshot_execute.py",
                "--dsn",
                dsn,
                "--condition-run-id",
                condition_run_id,
                "--for-trade-date",
                for_trade_date,
                "--json-report-path",
                str(n4_context_json),
                "--markdown-report-path",
                str(n4_context_md),
                "--rollback-sql-path",
                str(n4_context_rollback_sql),
                "--allow-existing-context-for-trade-date",
                "--execute",
                "--user-confirmed",
                "--json",
            ],
            report_paths=[str(n4_context_json), str(n4_context_md), str(n4_context_rollback_sql)],
        )
    )
    guard_specs = [
        ("n4_context_rollback_ready", "53_n4_context_rollback_ready_report", ["--rollback-sql-path", str(n4_context_rollback_sql)]),
        ("preopen_readiness_noop", "54_preopen_readiness_noop_report", []),
        ("lineage_pollution_guard", "55_lineage_pollution_guard_report", []),
        ("worker_launchd_guard", "56_worker_launchd_guard_report", []),
    ]
    for step_id, file_stem, extra_args in guard_specs:
        guard_json = docs_dir / f"{file_stem}.json"
        guard_md = docs_dir / f"{file_stem}.md"
        commands.append(
            ChildCommand(
                step_id=step_id,
                layer_role="runtime_control",
                argv=[
                    python_executable,
                    "scripts/review_post_close_preopen_guards.py",
                    "--check",
                    step_id,
                    "--dsn",
                    dsn,
                    "--for-trade-date",
                    for_trade_date,
                    "--source-trade-date",
                    source_trade_date,
                    "--condition-run-id",
                    condition_run_id,
                    "--subscription-run-id",
                    subscription_run_id,
                    "--preload-run-id",
                    preload_run_id,
                    "--n4-context-run-id",
                    n4_context_run_id,
                    *extra_args,
                    "--json-report-path",
                    str(guard_json),
                    "--markdown-report-path",
                    str(guard_md),
                    "--json",
                ],
                report_paths=[str(guard_json), str(guard_md)],
            )
        )
    return commands


def run_post_close_oneshot(
    *,
    source_trade_date: str,
    for_trade_date: str,
    prev_trade_date: str,
    next_trade_date: str,
    dsn: str,
    docs_root: Path | str,
    sql_root: Path | str,
    execute: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
    include_calendar_repair: bool | None = None,
    force_rerun_after_blocked: bool = False,
    enable_n5_n3t_readiness_rollover: bool = False,
    python_executable: str = "python3",
    command_runner: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Run the post-close chain or produce a blocked/noop report."""

    docs_dir = Path(docs_root) / for_trade_date
    docs_dir.mkdir(parents=True, exist_ok=True)
    status_path = docs_dir / "00_status.json"
    json_report_path = docs_dir / "01_oneshot_execute_report.json"
    md_report_path = docs_dir / "01_oneshot_execute_report.md"

    previous_status = _load_json(status_path)
    previous_report = _load_json(json_report_path)
    if (
        previous_status
        and previous_status.get("result") == "EXECUTE_PASS"
        and not force_rerun_after_blocked
        and _report_has_step(previous_report, "worker_launchd_guard")
    ):
        return {
            "result": "NOOP",
            "reason": "already_execute_pass",
            "source_trade_date": source_trade_date,
            "for_trade_date": for_trade_date,
            "status_path": str(status_path),
        }

    requested_calendar_repair = include_calendar_repair
    target_calendar_exists = False
    if include_calendar_repair is None or include_calendar_repair:
        target_calendar_exists = calendar_date_exists(dsn=dsn, trade_date=for_trade_date)
    if include_calendar_repair is None:
        include_calendar_repair = not target_calendar_exists
    elif include_calendar_repair and target_calendar_exists:
        include_calendar_repair = False

    report: dict[str, Any] = {
        "result": "RUNNING",
        "flow": "post_close_static_preopen_readiness_oneshot",
        "source_trade_date": source_trade_date,
        "for_trade_date": for_trade_date,
        "prev_trade_date": prev_trade_date,
        "fallback_next_trade_date": next_trade_date,
        "run_ids": {
            "condition_run_id": condition_run_id_for(source_trade_date, for_trade_date),
            "subscription_run_id": subscription_run_id_for(source_trade_date, for_trade_date),
            "preload_run_id": preload_run_id_for(source_trade_date, for_trade_date),
        },
        "confirmation": {
            "execute": execute,
            "user_confirmed": user_confirmed,
            "postgres_commit_enabled": postgres_commit_enabled,
        },
        "calendar_repair": {
            "requested": requested_calendar_repair,
            "target_calendar_exists": target_calendar_exists,
            "will_run": bool(include_calendar_repair),
        },
        "sub_steps": [],
        "sub_report_paths": [],
        "failed_step_id": None,
        "forbidden_scope_proof": forbidden_scope_proof(),
    }

    blockers = confirmation_blockers(
        execute=execute,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    if blockers:
        report["result"] = "BLOCKED"
        report["blockers"] = blockers
        _write_reports(report, status_path=status_path, json_report_path=json_report_path, md_report_path=md_report_path)
        _refresh_latest_after_status(Path(docs_root), docs_dir)
        return report

    commands = build_oneshot_child_commands(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        prev_trade_date=prev_trade_date,
        next_trade_date=next_trade_date,
        dsn=dsn,
        docs_root=docs_root,
        sql_root=sql_root,
        include_calendar_repair=bool(include_calendar_repair),
        python_executable=python_executable,
    )

    previous_successful_steps: set[str] = set()
    previous_pass_missing_terminal_readiness = (
        bool(previous_status)
        and previous_status.get("result") == "EXECUTE_PASS"
        and previous_report
        and previous_report.get("result") == "EXECUTE_PASS"
        and not _report_has_step(previous_report, "worker_launchd_guard")
    )
    if (
        (force_rerun_after_blocked and previous_report and previous_report.get("result") in {"PARTIAL_BLOCKED", "BLOCKED"})
        or previous_pass_missing_terminal_readiness
    ):
        previous_successful_steps = {
            str(step.get("step_id"))
            for step in previous_report.get("sub_steps") or []
            if int(step.get("returncode") or 0) == 0
        }
        previous_successful_steps.update(
            command.step_id for command in commands if _recovery_artifact_passed(command)
        )

    runner = command_runner or default_command_runner
    for command in commands:
        if command.step_id in previous_successful_steps:
            step_report = {
                "step_id": command.step_id,
                "layer_role": command.layer_role,
                "argv": command.argv,
                "returncode": 0,
                "stdout_tail": "",
                "stderr_tail": "",
                "report_paths": command.report_paths,
                "skipped": True,
                "skip_reason": "previous_step_succeeded",
            }
            report["sub_steps"].append(step_report)
            report["sub_report_paths"].extend(command.report_paths)
            continue
        completed = runner(command.argv)
        step_report = {
            "step_id": command.step_id,
            "layer_role": command.layer_role,
            "argv": command.argv,
            "returncode": int(getattr(completed, "returncode", 0) or 0),
            "stdout_tail": str(getattr(completed, "stdout", "") or "")[-4000:],
            "stderr_tail": str(getattr(completed, "stderr", "") or "")[-4000:],
            "report_paths": command.report_paths,
        }
        report["sub_steps"].append(step_report)
        report["sub_report_paths"].extend(command.report_paths)
        if step_report["returncode"] != 0:
            report["failed_step_id"] = command.step_id
            report["result"] = "PARTIAL_BLOCKED" if len(report["sub_steps"]) > 1 else "BLOCKED"
            report["blockers"] = [f"child_step_failed:{command.step_id}"]
            _write_reports(report, status_path=status_path, json_report_path=json_report_path, md_report_path=md_report_path)
            _refresh_latest_after_status(Path(docs_root), docs_dir)
            return report

    report["result"] = "EXECUTE_PASS"
    report["blockers"] = []
    if enable_n5_n3t_readiness_rollover:
        attach_n5_n3t_readiness_rollover(
            report,
            source_trade_date=source_trade_date,
            for_trade_date=for_trade_date,
            dsn=dsn,
            python_executable=python_executable,
            runner=runner,
        )
    _write_reports(report, status_path=status_path, json_report_path=json_report_path, md_report_path=md_report_path)
    _refresh_latest_after_status(Path(docs_root), docs_dir)
    lineage_config_path = write_intraday_worker_lineage_config_after_fastlane_pass(
        docs_root=Path(docs_root),
        docs_dir=docs_dir,
    )
    if lineage_config_path:
        report["intraday_worker_lineage_config_path"] = str(lineage_config_path)
        _write_reports(report, status_path=status_path, json_report_path=json_report_path, md_report_path=md_report_path)
    return report


def confirmation_blockers(*, execute: bool, user_confirmed: bool, postgres_commit_enabled: bool) -> list[str]:
    blockers: list[str] = []
    if not execute:
        blockers.append("missing_execute")
    if not user_confirmed:
        blockers.append("missing_user_confirmed")
    if not postgres_commit_enabled:
        blockers.append("missing_postgres_commit_enabled")
    return blockers


def forbidden_scope_proof() -> dict[str, bool]:
    return {
        "n3_b_c_b2_executed": False,
        "n4_n5_n6_entered": False,
        "outbox_inbox_checkpoint_consumed_or_updated": False,
        "worker_started": False,
        "delivery_push_voice_mobile": False,
        "sim_position_pnl_real_trade": False,
        "proposal_order_trade": False,
        "old_system_touched": False,
    }


def default_command_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": "src:scripts"}
    return subprocess.run(argv, check=False, text=True, capture_output=True, env=env)


def attach_n5_n3t_readiness_rollover(
    report: dict[str, Any],
    *,
    source_trade_date: str,
    for_trade_date: str,
    dsn: str,
    python_executable: str,
    runner: Callable[[list[str]], Any],
) -> None:
    output_dir = Path("tmp/N5_N3T_action_confirmation_fastlane_activation_config")
    rollover_source_trade_date = "".join(ch for ch in str(source_trade_date or "") if ch.isdigit())
    target_trade_date = "".join(ch for ch in str(for_trade_date or "") if ch.isdigit())
    base_activation_config = select_n5_n3t_readiness_rollover_base_activation_config(
        output_dir=output_dir,
        source_trade_date=rollover_source_trade_date,
    )
    current_exchange_time = (
        f"{rollover_source_trade_date[:4]}-{rollover_source_trade_date[4:6]}-{rollover_source_trade_date[6:]}T18:00:00+08:00"
        if len(rollover_source_trade_date) == 8
        else ""
    )
    argv = [
        python_executable,
        "scripts/plan_n5_n3t_fastlane_launchd.py",
        "--post-close-readiness-config-rollover",
        "--for-trade-date",
        rollover_source_trade_date or target_trade_date,
        "--dsn",
        dsn,
        "--base-activation-config",
        str(base_activation_config),
        "--output-dir",
        str(output_dir),
        "--current-exchange-time",
        current_exchange_time,
        "--json",
    ]
    completed = runner(argv)
    stdout_text = str(getattr(completed, "stdout", "") or "")
    stderr_text = str(getattr(completed, "stderr", "") or "")
    returncode = int(getattr(completed, "returncode", 0) or 0)
    parsed: dict[str, Any] = {}
    try:
        loaded = json.loads(stdout_text)
        if isinstance(loaded, dict):
            parsed = loaded
    except json.JSONDecodeError:
        parsed = {}

    review_summary = parsed.get("active_worker_policy_review")
    if not isinstance(review_summary, dict):
        review_summary = {}
    readiness = {
        "step_id": "n5_n3t_next_trade_day_readiness_rollover",
        "layer_role": "runtime_control",
        "argv": argv,
        "returncode": returncode,
        "stdout_tail": stdout_text[-4000:],
        "stderr_tail": stderr_text[-4000:],
        "result": str(parsed.get("result") or ("PASS" if returncode == 0 else "BLOCKED")),
        "next_trade_date": str(parsed.get("next_trade_date") or ""),
        "stable_activation_config_path": str(parsed.get("stable_activation_config_path") or ""),
        "dated_activation_config_path": str(parsed.get("dated_activation_config_path") or ""),
        "active_worker_policy_review_path": str(parsed.get("active_worker_policy_review_path") or ""),
        "review_result": str(review_summary.get("result") or ""),
        "report_path": str(parsed.get("report_path") or ""),
        "non_blocking_for_post_close_mainline": True,
    }
    report["n5_n3t_next_trade_day_readiness"] = readiness
    if returncode != 0:
        report["n5_n3t_readiness_blocker"] = "n5_n3t_next_trade_day_readiness_rollover_failed"


def select_n5_n3t_readiness_rollover_base_activation_config(
    *,
    output_dir: Path,
    source_trade_date: str,
) -> Path:
    safe_source_trade_date = "".join(ch for ch in str(source_trade_date or "") if ch.isdigit())
    stable_path = output_dir / "write_enabled_activation_config_current_runtime_deferred_v1.json"
    source_dated_path = output_dir / f"write_enabled_activation_config_{safe_source_trade_date}_runtime_deferred_v1.json"
    for candidate in (stable_path, source_dated_path):
        payload = _load_json(candidate)
        if (
            payload
            and payload.get("artifact_type") == "n5_n3t_fastlane_activation_config_v1"
            and str(payload.get("for_trade_date") or "") == safe_source_trade_date
        ):
            return candidate
    return source_dated_path


def build_launchd_plist(
    *,
    project_root: Path,
    python_executable: str,
    dsn: str,
    docs_root: str = "docs/post_close_fastlane",
    sql_root: str = "sql",
    stdout_path: str | None = None,
    stderr_path: str | None = None,
) -> str:
    stdout_path = stdout_path or str(project_root / "logs/post_close_fastlane/stdout.log")
    stderr_path = stderr_path or str(project_root / "logs/post_close_fastlane/stderr.log")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LAUNCHD_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python_executable}</string>
    <string>scripts/run_post_close_n1_n2_n3a1_oneshot.py</string>
    <string>--auto-dates-from-calendar</string>
    <string>--dsn</string>
    <string>{dsn}</string>
    <string>--docs-root</string>
    <string>{docs_root}</string>
    <string>--sql-root</string>
    <string>{sql_root}</string>
    <string>--execute</string>
    <string>--user-confirmed</string>
    <string>--postgres-commit-enabled</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{project_root}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>src:scripts</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>18</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>{stdout_path}</string>
  <key>StandardErrorPath</key>
  <string>{stderr_path}</string>
</dict>
</plist>
"""


def derive_date_context_from_calendar(*, dsn: str, today: date | None = None) -> DateContext:
    today = today or datetime.now(ASIA_SHANGHAI).date()
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - surfaced in CLI reports
        raise RuntimeError("psycopg is required for --auto-dates-from-calendar") from exc
    with psycopg.connect(dsn) as conn:
        conn.execute("BEGIN READ ONLY")
        row = conn.execute(
            """
            SELECT trade_date, prev_trade_date, next_trade_date
            FROM common_trade_calendar
            WHERE is_open = true AND trade_date <= %s
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (today.strftime("%Y%m%d"),),
        ).fetchone()
    if not row:
        raise RuntimeError("no_open_trade_calendar_row_found_for_auto_dates")
    source_trade_date, prev_trade_date, for_trade_date = [str(value) for value in row]
    if not for_trade_date or for_trade_date.lower() == "none":
        raise RuntimeError(f"source_trade_date_has_no_next_trade_date:{source_trade_date}")
    return DateContext(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        prev_trade_date=prev_trade_date,
        fallback_next_trade_date=next_weekday_yyyymmdd(for_trade_date),
    )


def calendar_date_exists(*, dsn: str, trade_date: str) -> bool:
    try:
        import psycopg
    except ModuleNotFoundError:
        return False
    with psycopg.connect(dsn) as conn:
        conn.execute("BEGIN READ ONLY")
        count = conn.execute(
            "SELECT count(*) FROM common_trade_calendar WHERE trade_date = %s",
            (trade_date,),
        ).fetchone()[0]
    return int(count or 0) > 0


def next_weekday_yyyymmdd(yyyymmdd: str) -> str:
    current = datetime.strptime(yyyymmdd, "%Y%m%d").date() + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current.strftime("%Y%m%d")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_reports(
    report: dict[str, Any],
    *,
    status_path: Path,
    json_report_path: Path,
    md_report_path: Path,
) -> None:
    status = {
        "result": report.get("result"),
        "source_trade_date": report.get("source_trade_date"),
        "for_trade_date": report.get("for_trade_date"),
        "failed_step_id": report.get("failed_step_id"),
        "updated_at": datetime.now(ASIA_SHANGHAI).isoformat(),
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    md_report_path.write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Post-Close N1-N2-N3A1 Cumulative One-Shot Report",
        "",
        f"- result: `{report.get('result')}`",
        f"- source_trade_date: `{report.get('source_trade_date')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- failed_step_id: `{report.get('failed_step_id')}`",
        "",
        "## Steps",
    ]
    for step in report.get("sub_steps", []):
        lines.append(f"- `{step.get('step_id')}` returncode=`{step.get('returncode')}`")
    lines.extend(["", "## Forbidden Scope", ""])
    for key, value in (report.get("forbidden_scope_proof") or {}).items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def _refresh_latest_symlink(docs_root: Path, docs_dir: Path) -> None:
    latest = docs_root / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(docs_dir.name)
    except OSError:
        pointer = docs_root / "latest.txt"
        pointer.write_text(docs_dir.name + "\n", encoding="utf-8")


def _refresh_latest_after_status(docs_root: Path, docs_dir: Path) -> bool:
    status = _load_json(docs_dir / "00_status.json")
    report = _load_json(docs_dir / "01_oneshot_execute_report.json")
    if not status or not report:
        return False
    if str(status.get("for_trade_date") or "") != docs_dir.name:
        return False
    if not status.get("result"):
        return False
    _refresh_latest_symlink(docs_root, docs_dir)
    return True
