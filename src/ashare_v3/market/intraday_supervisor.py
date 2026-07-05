"""N3 B1/C1/B2 intraday bounded supervisor.

The supervisor is a thin run-once orchestrator for N3 market-data stages. It
detects the latest closed minute, derives deterministic run ids, and invokes
existing guarded B1/C1/B2 runners in order. It does not implement market-data
business logic, write trigger/action/user data, consume outbox rows, or start a
long-running worker.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from ashare_v3.market.previous_day_preload_execute import write_json, write_text
from ashare_v3.market.today_minute_plan import calculate_latest_closed_minute


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_SUPERVISOR_JSON_REPORT_PATH = "docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_REPORT.json"
DEFAULT_SUPERVISOR_MD_REPORT_PATH = "docs/N3_INTRADAY_B1_C1_B2_SUPERVISOR_REPORT.md"
AUCTION_PLAN_ONLY_START = time(9, 15)
AUCTION_EXECUTE_START = time(9, 20)
FIRST_CLOSED_MINUTE_AVAILABLE_AT = time(9, 32)

FORBIDDEN_COMMAND_MARKERS = (
    "run_n4",
    "run_n5",
    "run_n6",
    "trigger",
    "action_consumer",
    "action",
    "worker",
    "voice",
    "mobile",
    "sim",
    "position",
    "pnl",
    "order_execute",
    "real_trade",
    "proposal",
    "outbox_consume",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "checkpoint",
    "stock_monitor_isolated",
    "monitor.db",
    "LaunchAgent",
)

PATH_VALUE_OPTIONS = frozenset(
    {
        "--c0-plan-path",
        "--contract-path",
        "--docs-root",
        "--dry-run-path",
        "--json-report-path",
        "--markdown-report-path",
        "--output-path",
        "--post-backup-path",
        "--pre-backup-path",
        "--preflight-path",
        "--readiness-path",
        "--rollback-sql-path",
        "--sql-root",
    }
)

ALLOWED_N3_CHILD_SCRIPT_BASENAMES = frozenset(
    {
        "run_realtime_daily_snapshot_once.py",
        "run_today_minute_bar_1m_once.py",
        "run_realtime_projection_metric_once.py",
    }
)

FORBIDDEN_SCRIPT_PATH_MARKERS = (
    "stock_monitor_isolated",
    "monitor.db",
    "LaunchAgent",
)


@dataclass(frozen=True)
class IntradaySupervisorPaths:
    """Artifact path collection for one latest-closed-minute pass."""

    b1_contract_path: str
    b1_readiness_path: str
    b1_json_report_path: str
    b1_markdown_report_path: str
    b1_pre_backup_path: str
    b1_post_backup_path: str
    b1_rollback_sql_path: str
    c0_plan_path: str
    c1_json_report_path: str
    c1_markdown_report_path: str
    c1_pre_backup_path: str
    c1_post_backup_path: str
    c1_rollback_sql_path: str
    b2_contract_path: str
    b2_preflight_path: str
    b2_dry_run_path: str
    b2_json_report_path: str
    b2_markdown_report_path: str
    b2_rollback_sql_path: str


def build_intraday_supervisor_plan(
    *,
    for_trade_date: str,
    subscription_run_id: str,
    preload_run_id: str,
    passed_run_ids: Iterable[str],
    as_of: datetime | None = None,
    python_executable: str = sys.executable,
    docs_root: str | Path = "docs",
    sql_root: str | Path = "sql",
) -> dict[str, Any]:
    """Build a bounded B1/C1/B2 supervisor plan without executing commands."""

    resolved_as_of = ensure_shanghai_timezone(as_of or datetime.now(tz=ASIA_SHANGHAI))
    local_date = resolved_as_of.strftime("%Y%m%d")
    if local_date != for_trade_date:
        return base_report(
            for_trade_date=for_trade_date,
            subscription_run_id=subscription_run_id,
            preload_run_id=preload_run_id,
            as_of=resolved_as_of,
            status="blocked",
            reason="current_date_mismatch",
            child_steps=[],
        )

    latest_closed_minute = calculate_latest_closed_minute(as_of=resolved_as_of, trade_date=for_trade_date)
    if latest_closed_minute is None:
        minute_time = resolved_as_of.time().replace(second=0, microsecond=0)
        if AUCTION_PLAN_ONLY_START <= minute_time < AUCTION_EXECUTE_START:
            return base_report(
                for_trade_date=for_trade_date,
                subscription_run_id=subscription_run_id,
                preload_run_id=preload_run_id,
                as_of=resolved_as_of,
                status="noop",
                reason="auction_preopen_plan_only",
                child_steps=[],
                stage_order_policy="B1_B2_PREWARM_ONLY",
                projection_input_mode="auction_or_snapshot_only",
                effective_hhmm=AUCTION_EXECUTE_START.strftime("%H%M"),
                prewarm_hhmm=AUCTION_EXECUTE_START.strftime("%H%M"),
            )
        if AUCTION_EXECUTE_START <= minute_time < FIRST_CLOSED_MINUTE_AVAILABLE_AT:
            effective_hhmm = resolved_as_of.strftime("%H%M")
            run_ids = build_stage_run_ids(
                for_trade_date=for_trade_date,
                latest_closed_minute_hhmm=effective_hhmm,
                subscription_run_id=subscription_run_id,
                stage_run_mode="auction",
            )
            passed = set(passed_run_ids)
            if run_ids["B2"] in passed:
                return base_report(
                    for_trade_date=for_trade_date,
                    subscription_run_id=subscription_run_id,
                    preload_run_id=preload_run_id,
                    as_of=resolved_as_of,
                    status="noop",
                    reason="auction_snapshot_projection_already_processed",
                    child_steps=[],
                    stage_order_policy="B1_B2_BEFORE_FIRST_CLOSED_MINUTE",
                    projection_input_mode="auction_or_snapshot_only",
                    effective_hhmm=effective_hhmm,
                    skipped_child_steps=[c1_no_closed_minute_skip()],
                )
            paths = build_intraday_supervisor_paths(
                for_trade_date=for_trade_date,
                latest_closed_minute_hhmm=effective_hhmm,
                docs_root=docs_root,
                sql_root=sql_root,
                stage_run_mode="auction",
            )
            child_steps = build_child_steps(
                for_trade_date=for_trade_date,
                subscription_run_id=subscription_run_id,
                preload_run_id=preload_run_id,
                run_ids=run_ids,
                paths=paths,
                python_executable=python_executable,
                passed_run_ids=passed,
                include_c1=False,
                projection_input_mode="auction_or_snapshot_only",
            )
            return base_report(
                for_trade_date=for_trade_date,
                subscription_run_id=subscription_run_id,
                preload_run_id=preload_run_id,
                as_of=resolved_as_of,
                status="ready" if child_steps else "noop",
                reason="auction_snapshot_projection_ready" if child_steps else "auction_stage_runs_already_passed",
                child_steps=child_steps,
                stage_order_policy="B1_B2_BEFORE_FIRST_CLOSED_MINUTE",
                projection_input_mode="auction_or_snapshot_only",
                effective_hhmm=effective_hhmm,
                skipped_child_steps=[c1_no_closed_minute_skip()],
            )
        return base_report(
            for_trade_date=for_trade_date,
            subscription_run_id=subscription_run_id,
            preload_run_id=preload_run_id,
            as_of=resolved_as_of,
            status="noop",
            reason="no_closed_minute_available",
            child_steps=[],
        )

    latest_hhmm = latest_closed_minute.strftime("%H%M")
    run_ids = build_stage_run_ids(
        for_trade_date=for_trade_date,
        latest_closed_minute_hhmm=latest_hhmm,
        subscription_run_id=subscription_run_id,
    )
    passed = set(passed_run_ids)
    if run_ids["B2"] in passed:
        return base_report(
            for_trade_date=for_trade_date,
            subscription_run_id=subscription_run_id,
            preload_run_id=preload_run_id,
            as_of=resolved_as_of,
            status="noop",
            reason="latest_closed_minute_already_processed",
            child_steps=[],
            latest_closed_minute=latest_closed_minute,
        )

    paths = build_intraday_supervisor_paths(
        for_trade_date=for_trade_date,
        latest_closed_minute_hhmm=latest_hhmm,
        docs_root=docs_root,
        sql_root=sql_root,
    )
    child_steps = build_child_steps(
        for_trade_date=for_trade_date,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        run_ids=run_ids,
        paths=paths,
        python_executable=python_executable,
        passed_run_ids=passed,
        include_c1=True,
        projection_input_mode="closed_minute",
    )
    return base_report(
        for_trade_date=for_trade_date,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        as_of=resolved_as_of,
        status="ready" if child_steps else "noop",
        reason="new_closed_minute_detected" if child_steps else "stage_runs_already_passed",
        child_steps=child_steps,
        latest_closed_minute=latest_closed_minute,
        stage_order_policy="B1_C1_B2_AFTER_CLOSED_MINUTE",
        projection_input_mode="closed_minute",
        effective_hhmm=latest_hhmm,
    )


def run_intraday_supervisor_plan(
    plan: Mapping[str, Any],
    *,
    command_runner: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Run child commands from a supervisor plan and stop after first failure."""

    report = dict(plan)
    if report.get("status") != "ready":
        report["child_step_results"] = []
        report["executed_child_command_count"] = 0
        return report

    runner = command_runner or default_command_runner
    results: list[dict[str, Any]] = []
    for step in report.get("child_steps", []):
        command = list(step["command"])
        validate_child_command(command)
        completed = runner(command)
        result = {
            "stage": step["stage"],
            "step_id": step["step_id"],
            "run_id": step["run_id"],
            "returncode": int(getattr(completed, "returncode", 1)),
            "stdout": str(getattr(completed, "stdout", ""))[:4000],
            "stderr": str(getattr(completed, "stderr", ""))[:4000],
            "report_path": step.get("json_report_path"),
        }
        results.append(result)
        if result["returncode"] != 0:
            report["status"] = "blocked"
            report["reason"] = "child_step_failed"
            report["failed_stage"] = step["stage"]
            report["failed_step_id"] = step["step_id"]
            break
    else:
        report["status"] = "passed"
        report["reason"] = "all_child_steps_passed"
        report["failed_stage"] = None
        report["failed_step_id"] = None

    report["child_step_results"] = results
    report["executed_child_command_count"] = len(results)
    return report


def fetch_passed_market_data_run_ids(*, dsn: str, for_trade_date: str, run_id_prefixes: Sequence[str]) -> set[str]:
    """Fetch already-passed N3 run ids used as the supervisor watermark."""

    if not run_id_prefixes:
        return set()
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        predicates = " OR ".join(["run_id LIKE %s" for _ in run_id_prefixes])
        cur.execute(
            f"""
            SELECT run_id
            FROM common_market_data_run
            WHERE for_trade_date = %s
              AND status = 'passed'
              AND ({predicates})
            """,
            (for_trade_date, *[f"{prefix}%" for prefix in run_id_prefixes]),
        )
        return {str(row["run_id"]) for row in cur.fetchall()}


def build_stage_run_ids(
    *,
    for_trade_date: str,
    latest_closed_minute_hhmm: str,
    subscription_run_id: str,
    stage_run_mode: str = "closed_minute",
) -> dict[str, str]:
    label = build_stage_run_label(latest_closed_minute_hhmm, stage_run_mode=stage_run_mode)
    b1_run_id = f"realtime_daily_snapshot_{for_trade_date}_{label}__{subscription_run_id}"
    c1_run_id = f"today_minute_bar_1m_{for_trade_date}_{label}__{subscription_run_id}"
    b2_run_id = f"realtime_projection_metric_{for_trade_date}_{label}__{b1_run_id}"
    return {"B1": b1_run_id, "C1": c1_run_id, "B2": b2_run_id}


def build_stage_run_label(latest_closed_minute_hhmm: str, *, stage_run_mode: str = "closed_minute") -> str:
    if stage_run_mode == "closed_minute":
        return f"until_{latest_closed_minute_hhmm}"
    if stage_run_mode == "auction":
        return f"auction_{latest_closed_minute_hhmm}"
    raise ValueError(f"unsupported_intraday_stage_run_mode:{stage_run_mode}")


def build_intraday_supervisor_paths(
    *,
    for_trade_date: str,
    latest_closed_minute_hhmm: str,
    docs_root: str | Path,
    sql_root: str | Path,
    stage_run_mode: str = "closed_minute",
) -> IntradaySupervisorPaths:
    docs = Path(docs_root)
    sql = Path(sql_root)
    suffix = f"{for_trade_date}_{build_stage_run_label(latest_closed_minute_hhmm, stage_run_mode=stage_run_mode)}"
    return IntradaySupervisorPaths(
        b1_contract_path=str(docs / f"N3_B1_realtime_snapshot_{suffix}_execute_contract.json"),
        b1_readiness_path=str(docs / f"N3_B1_realtime_snapshot_{suffix}_execute_readiness.json"),
        b1_json_report_path=str(docs / f"N3_B1_realtime_snapshot_{suffix}_execute_report.json"),
        b1_markdown_report_path=str(docs / f"N3_B1_REALTIME_SNAPSHOT_{suffix}_EXECUTE_REPORT.md"),
        b1_pre_backup_path=str(docs / f"N3_B1_realtime_snapshot_{suffix}_backup_before.json"),
        b1_post_backup_path=str(docs / f"N3_B1_realtime_snapshot_{suffix}_backup_after.json"),
        b1_rollback_sql_path=str(sql / f"N3_B1_realtime_snapshot_{suffix}_rollback.sql"),
        c0_plan_path=str(docs / f"N3_C0_today_minute_bar_1m_{suffix}_dry_run.json"),
        c1_json_report_path=str(docs / f"N3_C1_today_minute_bar_1m_{suffix}_execute_report.json"),
        c1_markdown_report_path=str(docs / f"N3_C1_TODAY_MINUTE_BAR_1M_{suffix}_EXECUTE_REPORT.md"),
        c1_pre_backup_path=str(docs / f"N3_C1_today_minute_bar_1m_{suffix}_backup_before.json"),
        c1_post_backup_path=str(docs / f"N3_C1_today_minute_bar_1m_{suffix}_backup_after.json"),
        c1_rollback_sql_path=str(sql / f"N3_C1_today_minute_bar_1m_{suffix}_rollback.sql"),
        b2_contract_path=str(docs / f"N3_B2_realtime_projection_{suffix}_execute_contract.json"),
        b2_preflight_path=str(docs / f"N3_B2_realtime_projection_{suffix}_execute_preflight.json"),
        b2_dry_run_path=str(docs / f"N3_B2_realtime_projection_{suffix}_dry_run.json"),
        b2_json_report_path=str(docs / f"N3_B2_realtime_projection_{suffix}_execute_report.json"),
        b2_markdown_report_path=str(docs / f"N3_B2_REALTIME_PROJECTION_{suffix}_EXECUTE_REPORT.md"),
        b2_rollback_sql_path=str(sql / f"N3_B2_realtime_projection_{suffix}_rollback.sql"),
    )


def build_child_steps(
    *,
    for_trade_date: str,
    subscription_run_id: str,
    preload_run_id: str,
    run_ids: Mapping[str, str],
    paths: IntradaySupervisorPaths,
    python_executable: str,
    passed_run_ids: set[str],
    include_c1: bool = True,
    projection_input_mode: str = "closed_minute",
) -> list[dict[str, Any]]:
    b1_step = {
        "stage": "B1",
        "step_id": "b1_realtime_snapshot",
        "run_id": run_ids["B1"],
        "json_report_path": paths.b1_json_report_path,
        "rollback_sql_path": paths.b1_rollback_sql_path,
        "projection_input_mode": projection_input_mode,
        "command": [
            python_executable,
            "scripts/run_realtime_daily_snapshot_once.py",
            "--contract-path",
            paths.b1_contract_path,
            "--readiness-path",
            paths.b1_readiness_path,
            "--pre-backup-path",
            paths.b1_pre_backup_path,
            "--post-backup-path",
            paths.b1_post_backup_path,
            "--json-report-path",
            paths.b1_json_report_path,
            "--markdown-report-path",
            paths.b1_markdown_report_path,
            "--for-trade-date",
            for_trade_date,
            "--snapshot-run-id",
            run_ids["B1"],
            "--no-outbox",
            "--execute",
            "--user-confirmed",
            "--json",
        ],
    }
    c1_step = {
        "stage": "C1",
        "step_id": "c1_today_minute",
        "run_id": run_ids["C1"],
        "json_report_path": paths.c1_json_report_path,
        "rollback_sql_path": paths.c1_rollback_sql_path,
        "projection_input_mode": projection_input_mode,
        "command": [
            python_executable,
            "scripts/run_today_minute_bar_1m_once.py",
            "--c0-plan-path",
            paths.c0_plan_path,
            "--pre-backup-path",
            paths.c1_pre_backup_path,
            "--post-backup-path",
            paths.c1_post_backup_path,
            "--json-report-path",
            paths.c1_json_report_path,
            "--markdown-report-path",
            paths.c1_markdown_report_path,
            "--rollback-sql-path",
            paths.c1_rollback_sql_path,
            "--for-trade-date",
            for_trade_date,
            "--today-minute-run-id",
            run_ids["C1"],
            "--execute",
            "--user-confirmed",
            "--json",
        ],
    }
    b2_step = {
        "stage": "B2",
        "step_id": "b2_realtime_projection",
        "run_id": run_ids["B2"],
        "json_report_path": paths.b2_json_report_path,
        "rollback_sql_path": paths.b2_rollback_sql_path,
        "projection_input_mode": projection_input_mode,
        "command": [
            python_executable,
            "scripts/run_realtime_projection_metric_once.py",
            "--contract-path",
            paths.b2_contract_path,
            "--preflight-path",
            paths.b2_preflight_path,
            "--dry-run-path",
            paths.b2_dry_run_path,
            "--json-report-path",
            paths.b2_json_report_path,
            "--markdown-report-path",
            paths.b2_markdown_report_path,
            "--rollback-sql-path",
            paths.b2_rollback_sql_path,
            "--projection-run-id",
            run_ids["B2"],
            "--for-trade-date",
            for_trade_date,
            "--execute",
            "--user-confirmed",
            "--json",
        ],
        "source_runs": {
            "subscription_run_id": subscription_run_id,
            "preload_run_id": preload_run_id,
            "snapshot_run_id": run_ids["B1"],
            "today_minute_run_id": run_ids["C1"] if include_c1 else None,
        },
    }
    steps = [b1_step]
    if include_c1:
        steps.append(c1_step)
    steps.append(b2_step)
    return [step for step in steps if step["run_id"] not in passed_run_ids]


def c1_no_closed_minute_skip() -> dict[str, str]:
    return {
        "stage": "C1",
        "step_id": "c1_today_minute",
        "reason": "no_closed_minute_available",
    }


def validate_child_command(command: Sequence[str]) -> None:
    if not isinstance(command, list):
        raise ValueError("n3_intraday_supervisor_command_must_be_list")
    if len(command) < 2:
        raise ValueError("n3_intraday_supervisor_child_script_missing")
    script_token = str(command[1])
    for marker in FORBIDDEN_SCRIPT_PATH_MARKERS:
        if marker in script_token or marker.lower() in script_token.lower():
            raise ValueError(f"n3_intraday_supervisor_forbidden_command_marker:{marker}")
    script_basename = Path(script_token).name
    marker = _find_forbidden_command_marker(script_basename)
    if marker is not None:
        raise ValueError(f"n3_intraday_supervisor_forbidden_command_marker:{marker}")
    if script_basename not in ALLOWED_N3_CHILD_SCRIPT_BASENAMES:
        raise ValueError(f"n3_intraday_supervisor_unapproved_child_script:{script_basename}")
    for token in _semantic_command_tokens_for_guard(command):
        marker = _find_forbidden_command_marker(token)
        if marker is not None:
            raise ValueError(f"n3_intraday_supervisor_forbidden_command_marker:{marker}")
    if "--execute" not in command or "--user-confirmed" not in command:
        raise ValueError("n3_intraday_supervisor_execute_child_missing_confirmation_flags")


def _semantic_command_tokens_for_guard(command: Sequence[str]) -> list[str]:
    tokens: list[str] = []
    skip_next = False
    for raw_token in command[2:]:
        token = str(raw_token)
        if skip_next:
            skip_next = False
            continue
        if token in PATH_VALUE_OPTIONS:
            tokens.append(token)
            skip_next = True
            continue
        path_option = _split_path_option_token(token)
        if path_option is not None:
            tokens.append(path_option)
            continue
        tokens.append(token)
    return tokens


def _split_path_option_token(token: str) -> str | None:
    for option in PATH_VALUE_OPTIONS:
        if token.startswith(f"{option}="):
            return option
    return None


def _find_forbidden_command_marker(token: str) -> str | None:
    lowered = token.lower()
    for marker in FORBIDDEN_COMMAND_MARKERS:
        if marker in token or marker.lower() in lowered:
            return marker
    return None


def default_command_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def base_report(
    *,
    for_trade_date: str,
    subscription_run_id: str,
    preload_run_id: str,
    as_of: datetime,
    status: str,
    reason: str,
    child_steps: list[dict[str, Any]],
    latest_closed_minute: datetime | None = None,
    stage_order_policy: str = "",
    projection_input_mode: str = "",
    effective_hhmm: str | None = None,
    prewarm_hhmm: str | None = None,
    skipped_child_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "stage": "N3-intraday-B1-C1-B2-supervisor",
        "layer_role": "N3_market_data",
        "for_trade_date": for_trade_date,
        "subscription_run_id": subscription_run_id,
        "preload_run_id": preload_run_id,
        "as_of": as_of.isoformat(),
        "latest_closed_minute": latest_closed_minute.isoformat() if latest_closed_minute else None,
        "latest_closed_minute_hhmm": latest_closed_minute.strftime("%H%M") if latest_closed_minute else None,
        "effective_hhmm": effective_hhmm,
        "prewarm_hhmm": prewarm_hhmm,
        "stage_order_policy": stage_order_policy,
        "projection_input_mode": projection_input_mode,
        "skipped_child_steps": skipped_child_steps or [],
        "status": status,
        "reason": reason,
        "child_steps": child_steps,
        "side_effects": {
            "supervisor_writes_database": False,
            "starts_worker": False,
            "outbox_consumed_or_updated": False,
            "n4_n5_n6_entered": False,
            "old_system_touched": False,
            "trade_sim_position_pnl_touched": False,
        },
    }


def ensure_shanghai_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ASIA_SHANGHAI)
    return value.astimezone(ASIA_SHANGHAI)


def render_supervisor_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# N3 Intraday B1/C1/B2 Supervisor Report",
        "",
        f"- status: `{report.get('status')}`",
        f"- reason: `{report.get('reason')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- latest_closed_minute: `{report.get('latest_closed_minute')}`",
        f"- executed_child_command_count: `{report.get('executed_child_command_count', 0)}`",
        "",
        "## Child Steps",
    ]
    for step in report.get("child_steps", []):
        lines.append(f"- `{step.get('stage')}` run_id=`{step.get('run_id')}` report=`{step.get('json_report_path')}`")
    lines.extend(
        [
            "",
            "## Forbidden Scope",
            "",
            "- no worker",
            "- no outbox/inbox/checkpoint consume or update",
            "- no N4/N5/N6",
            "- no delivery/push/voice/mobile",
            "- no proposal/order/trade/sim/position/PnL/real trade",
        ]
    )
    return "\n".join(lines) + "\n"


def write_supervisor_report(report: Mapping[str, Any], *, json_report_path: str | Path, markdown_report_path: str | Path) -> None:
    write_json(json_report_path, dict(report))
    write_text(markdown_report_path, render_supervisor_markdown(report))


def load_intraday_supervisor_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
