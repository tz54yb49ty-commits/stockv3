#!/usr/bin/env python3
"""Generate local launchd plan artifacts for N3/N4 intraday proof pollers."""

from __future__ import annotations

import argparse
import json
import plistlib
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


N3_LABEL = "com.ashare-v3.n3.intraday-proof-poller"
N3P_BRANCH_LABEL = "com.ashare-v3.n3.intraday-proof-poller.n3p"
HINT_BRANCH_LABEL = "com.ashare-v3.n3.intraday-proof-poller.hint"
N4_LABEL = "com.ashare-v3.n4.proof-discovery-poller"
N4_HINT_LABEL = "com.ashare-v3.n4.proof-discovery-poller.hint"
DSN_PLACEHOLDER = "__ASHARE_V3_POSTGRES_DSN__"
N3_INTERVAL_SECONDS = 15
N3P_BRANCH_INTERVAL_SECONDS = 60
HINT_BRANCH_INTERVAL_SECONDS = 180
N4_INTERVAL_SECONDS = 10
DEFAULT_PYTHON_EXECUTABLE = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
DEFAULT_LINEAGE_CONFIG_PATH = "docs/runtime/current_intraday_worker_lineage.json"


def build_launchd_plan(
    *,
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    trigger_context_run_id: str,
    working_directory: str,
    dsn: str = "",
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
    lineage_config_path: str = DEFAULT_LINEAGE_CONFIG_PATH,
    split_n3_branches: bool = False,
) -> dict[str, Any]:
    if split_n3_branches:
        n3p_plist = _build_n3_proof_poller_plist(
            label=N3P_BRANCH_LABEL,
            start_interval=N3P_BRANCH_INTERVAL_SECONDS,
            working_directory=working_directory,
            python_executable=python_executable,
            lineage_config_path=lineage_config_path,
            json_report_path="tmp/N3_intraday_proof_poller_n3p_launchd_report.json",
            branch_mode="n3p_only",
        )
        hint_plist = _build_n3_proof_poller_plist(
            label=HINT_BRANCH_LABEL,
            start_interval=HINT_BRANCH_INTERVAL_SECONDS,
            working_directory=working_directory,
            python_executable=python_executable,
            lineage_config_path=lineage_config_path,
            json_report_path="tmp/N3_intraday_proof_poller_hint_launchd_report.json",
            branch_mode="hint_only",
        )
    else:
        n3_plist = _build_n3_proof_poller_plist(
            label=N3_LABEL,
            start_interval=N3_INTERVAL_SECONDS,
            working_directory=working_directory,
            python_executable=python_executable,
            lineage_config_path=lineage_config_path,
            json_report_path="tmp/N3_intraday_proof_poller_launchd_report.json",
        )
    n4_mode = "ordinary" if split_n3_branches else None
    n4_plist = _build_n4_proof_discovery_plist(
        label=N4_LABEL,
        working_directory=working_directory,
        python_executable=python_executable,
        lineage_config_path=lineage_config_path,
        json_report_path="tmp/N4_intraday_proof_discovery_poller_launchd_report.json",
        mode=n4_mode,
    )
    _assert_plist_safe(n4_plist)
    if split_n3_branches:
        n4_hint_plist = _build_n4_proof_discovery_plist(
            label=N4_HINT_LABEL,
            working_directory=working_directory,
            python_executable=python_executable,
            lineage_config_path=lineage_config_path,
            json_report_path="tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json",
            mode="hint",
        )
        _assert_plist_safe(n4_hint_plist)
    report = {
        "gate": "N3_N4_INTRADAY_WORKER_LAUNCHD_PLAN_AND_HARDENING_PATCH_GATE",
        "result": "PLAN_ONLY_PASS",
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "lineage_config_path": lineage_config_path,
        "dsn_policy": {
            "n3_parent_environment_variable": "omitted_unless_real_dsn_is_installed",
            "n3_placeholder_env_allowed": False,
            "n4_parent_environment_variable": "ASHARE_V3_POSTGRES_DSN",
            "n4_plist_value": DSN_PLACEHOLDER,
            "n4_child_arg": "--dsn",
            "dsn_redacted": _redact_dsn(dsn),
            "report_uses_redacted_dsn": True,
        },
        "n4": {"label": N4_LABEL, "plist": n4_plist},
        "forbidden_operation_proof": {
            "database_written": False,
            "market_data_pulled": False,
            "runtime_executed": False,
            "outbox_consumed": False,
            "inbox_checkpoint_updated": False,
            "n5_n6_entered": False,
            "launchd_loaded_or_started": False,
            "rollback_executed": False,
            "schema_changed": False,
            "commit_created": False,
        },
    }
    if split_n3_branches:
        _assert_plist_safe(n3p_plist)
        _assert_plist_safe(hint_plist)
        report.update(
            {
                "gate": "N3_PROOF_POLLER_BRANCH_MODE_LAUNCHD_PLAN_GATE",
                "n3_branch_policy": {
                    "enabled": True,
                    "n3p_branch": "n3p_only",
                    "hint_branch": "hint_only",
                    "n3p_start_interval_seconds": N3P_BRANCH_INTERVAL_SECONDS,
                    "hint_start_interval_seconds": HINT_BRANCH_INTERVAL_SECONDS,
                },
                "launchd_plist_keys": ["n3p", "hint", "n4", "n4_hint"],
                "n3p": {"label": N3P_BRANCH_LABEL, "plist": n3p_plist},
                "hint": {"label": HINT_BRANCH_LABEL, "plist": hint_plist},
                "n4_hint": {"label": N4_HINT_LABEL, "plist": n4_hint_plist},
            }
        )
    else:
        _assert_plist_safe(n3_plist)
        report.update(
            {
                "n3_branch_policy": {"enabled": False},
                "launchd_plist_keys": ["n3", "n4"],
                "n3": {"label": N3_LABEL, "plist": n3_plist},
            }
        )
    return report


def write_launchd_plan(
    *,
    output_dir: Path,
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    trigger_context_run_id: str,
    working_directory: str,
    dsn: str = "",
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
    lineage_config_path: str = DEFAULT_LINEAGE_CONFIG_PATH,
    split_n3_branches: bool = False,
) -> dict[str, Any]:
    report = build_launchd_plan(
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        source_condition_run_id=source_condition_run_id,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        trigger_context_run_id=trigger_context_run_id,
        working_directory=working_directory,
        dsn=dsn,
        python_executable=python_executable,
        lineage_config_path=lineage_config_path,
        split_n3_branches=split_n3_branches,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in report["launchd_plist_keys"]:
        plist_path = output_dir / f"{report[key]['label']}.plist"
        with plist_path.open("wb") as fh:
            plistlib.dump(report[key]["plist"], fh, sort_keys=True)
        report[key]["plist_path"] = str(plist_path)
    report_path = output_dir / f"N3_N4_intraday_worker_launchd_plan_{for_trade_date}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _build_n3_proof_poller_plist(
    *,
    label: str,
    start_interval: int,
    working_directory: str,
    python_executable: str,
    lineage_config_path: str,
    json_report_path: str,
    branch_mode: str | None = None,
) -> dict[str, Any]:
    program_arguments = [
        python_executable,
        "scripts/run_n3_intraday_proof_poller_once.py",
        "--lineage-config",
        lineage_config_path,
        "--json-report-path",
        json_report_path,
        "--python-executable",
        python_executable,
    ]
    if branch_mode:
        program_arguments.extend(["--branch", branch_mode])
    program_arguments.extend(["--execute", "--user-confirmed"])
    return _build_plist(
        label=label,
        start_interval=start_interval,
        working_directory=working_directory,
        include_dsn_placeholder=False,
        program_arguments=program_arguments,
    )


def _build_n4_proof_discovery_plist(
    *,
    label: str,
    working_directory: str,
    python_executable: str,
    lineage_config_path: str,
    json_report_path: str,
    mode: str | None = None,
) -> dict[str, Any]:
    program_arguments = [
        python_executable,
        "scripts/run_n4_intraday_proof_discovery_poll_once.py",
        "--dsn",
        DSN_PLACEHOLDER,
        "--lineage-config",
        lineage_config_path,
        "--json-report-path",
        json_report_path,
        "--python-executable",
        python_executable,
        "--selection-mode",
        "realtime_latest_only",
    ]
    if mode:
        program_arguments.extend(["--mode", mode])
    program_arguments.extend(["--execute", "--user-confirmed"])
    return _build_plist(
        label=label,
        start_interval=N4_INTERVAL_SECONDS,
        working_directory=working_directory,
        program_arguments=program_arguments,
    )


def _build_plist(
    *,
    label: str,
    start_interval: int,
    working_directory: str,
    program_arguments: list[str],
    include_dsn_placeholder: bool = True,
) -> dict[str, Any]:
    environment_variables = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "src:scripts:.",
    }
    if include_dsn_placeholder:
        environment_variables["ASHARE_V3_POSTGRES_DSN"] = DSN_PLACEHOLDER
    return {
        "Label": label,
        "ProgramArguments": program_arguments,
        "WorkingDirectory": working_directory,
        "EnvironmentVariables": environment_variables,
        "StartInterval": start_interval,
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": f"{working_directory}/tmp/{label}.out.log",
        "StandardErrorPath": f"{working_directory}/tmp/{label}.err.log",
    }


def _assert_plist_safe(plist: dict[str, Any]) -> None:
    joined = " ".join(str(value) for value in plist.get("ProgramArguments", [])).lower()
    for token in (
        "run_n3_n4_n5_realtime_chain_once.py",
        "run_n5",
        "run_n6",
        "consume",
        "checkpoint",
        "rollback",
        "schema",
        "migration",
        "launchctl",
    ):
        if token in joined:
            raise ValueError(f"forbidden launchd ProgramArguments token: {token}")
    if plist.get("RunAtLoad") is not False or plist.get("KeepAlive") is not False:
        raise ValueError("launchd plan must keep RunAtLoad=false and KeepAlive=false")


def _redact_dsn(dsn: str) -> str:
    if not dsn:
        return ""
    try:
        parsed = urlsplit(dsn)
        if parsed.password:
            username = parsed.username or ""
            hostname = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            auth = f"{username}:***@{hostname}{port}" if username else f"***@{hostname}{port}"
            return urlunsplit((parsed.scheme, auth, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        pass
    redacted = re.sub(r":([^:@/\s]+)@", ":***@", dsn)
    return re.sub(r"(password=)[^\s]+", r"\1***", redacted, flags=re.IGNORECASE)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate local N3/N4 proof poller launchd plan artifacts.")
    parser.add_argument("--output-dir", default="tmp/N3_N4_intraday_worker_launchd_plan")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--source-trade-date", required=True)
    parser.add_argument("--source-condition-run-id", required=True)
    parser.add_argument("--subscription-run-id", required=True)
    parser.add_argument("--preload-run-id", required=True)
    parser.add_argument("--trigger-context-run-id", required=True)
    parser.add_argument("--working-directory", default=str(Path.cwd()))
    parser.add_argument("--dsn", default="")
    parser.add_argument("--python-executable", default=DEFAULT_PYTHON_EXECUTABLE)
    parser.add_argument("--lineage-config", default=DEFAULT_LINEAGE_CONFIG_PATH)
    parser.add_argument("--split-n3-branches", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = write_launchd_plan(
        output_dir=Path(args.output_dir),
        for_trade_date=args.for_trade_date,
        source_trade_date=args.source_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        subscription_run_id=args.subscription_run_id,
        preload_run_id=args.preload_run_id,
        trigger_context_run_id=args.trigger_context_run_id,
        working_directory=args.working_directory,
        dsn=args.dsn,
        python_executable=args.python_executable,
        lineage_config_path=args.lineage_config,
        split_n3_branches=args.split_n3_branches,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"result={report['result']} report_path={report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
