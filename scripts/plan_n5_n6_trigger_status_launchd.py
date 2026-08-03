#!/usr/bin/env python3
"""Build plan-only LaunchAgent plists for trigger-status convergence."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
from pathlib import Path
from typing import Any


N5_LABEL = "com.ashare-v3.n5.trigger-status-forward-v1"
N6_LABEL = "com.ashare-v3.n6.trigger-status-projection-v1"
N5_CONSUMER_NAME = "n5_trigger_status_forward_current_v1"
START_INTERVAL_SECONDS = 30
MAX_EVENTS = 5000
N5_MAX_RUNTIME_SECONDS = 20
DEFAULT_LINEAGE_CONFIG_PATH = Path(
    "/Users/chuanfuchen/Documents/A股监控系统v3/docs/runtime/"
    "current_intraday_worker_lineage.json"
)
DEFAULT_RELEASE_ROOT = Path(
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/trigger-status"
)
DEFAULT_STATE_ROOT = Path(
    "/Users/chuanfuchen/.local/state/ashare-v3/trigger-status"
)
RELEASE_ID_PATTERN = re.compile(r"^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$")


def build_launchd_plan(
    *,
    release_path: Path,
    runtime_env_path: Path,
    lineage_config_path: Path = DEFAULT_LINEAGE_CONFIG_PATH,
    state_root: Path = DEFAULT_STATE_ROOT,
) -> dict[str, Any]:
    release = _absolute(release_path, "release_path")
    runtime_env = _absolute(runtime_env_path, "runtime_env_path")
    lineage = _absolute(lineage_config_path, "lineage_config_path")
    state = _absolute(state_root, "state_root")
    if release.parent != DEFAULT_RELEASE_ROOT:
        raise ValueError("release_path must use fixed trigger-status release root")
    if not RELEASE_ID_PATTERN.fullmatch(release.name):
        raise ValueError("release_path must end with <YYYYMMDD_HHMMSS>__<40hex>")

    python = runtime_env / "bin/python3.11"
    common_env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": ":".join(
            (str(release / "src"), str(release / "scripts"), str(release))
        ),
    }
    logs = state / "logs"
    n5_args = [
        str(python),
        str(release / "scripts/run_n5_trigger_status_forward_current_once.py"),
        "--lineage-config",
        str(lineage),
        "--consumer-name",
        N5_CONSUMER_NAME,
        "--max-events",
        str(MAX_EVENTS),
        "--max-runtime-seconds",
        str(N5_MAX_RUNTIME_SECONDS),
        "--singleton-lock-path",
        str(state / "locks/n5_trigger_status_forward.lock"),
        "--execute",
        "--user-confirmed",
        "--json-report-path",
        str(state / "reports/n5_trigger_status_forward_current.json"),
        "--history-path",
        str(state / "history/n5_trigger_status_forward_current.jsonl"),
    ]
    n6_args = [
        str(python),
        str(release / "scripts/run_n6_trigger_status_projection_current_once.py"),
        "--lineage-config",
        str(lineage),
        "--limit",
        str(MAX_EVENTS),
        "--singleton-lock-path",
        str(state / "locks/n6_trigger_status_projection.lock"),
        "--execute",
        "--user-confirmed",
        "--json-report-path",
        str(state / "reports/n6_trigger_status_projection_current.json"),
        "--history-path",
        str(state / "history/n6_trigger_status_projection_current.jsonl"),
    ]
    plists = {
        "n5": _plist(N5_LABEL, n5_args, state, common_env, logs),
        "n6": _plist(N6_LABEL, n6_args, state, common_env, logs),
    }
    _assert_safe(plists, release, runtime_env, lineage, state)
    return {
        "policy_id": "n5_n6_trigger_status_scheduled_convergence_30s_v1",
        "stage": "N5_N6_TRIGGER_STATUS_LAUNCHD_PLAN",
        "result": "PLAN_ONLY_PASS",
        "release_id": release.name,
        "activation_order": ["n5", "n6"],
        "n5": {"label": N5_LABEL, "plist": plists["n5"]},
        "n6": {"label": N6_LABEL, "plist": plists["n6"]},
        "side_effects": {
            "release_materialized": False,
            "launchd_mutated": False,
            "worker_started": False,
            "database_written": False,
            "service_rebound": False,
        },
    }


def _plist(
    label: str,
    args: list[str],
    state_root: Path,
    environment: dict[str, str],
    logs: Path,
) -> dict[str, Any]:
    return {
        "Label": label,
        "ProgramArguments": args,
        "WorkingDirectory": str(state_root / "cwd"),
        "EnvironmentVariables": environment,
        "RunAtLoad": False,
        "KeepAlive": False,
        "StartInterval": START_INTERVAL_SECONDS,
        "StandardOutPath": str(logs / f"{label}.out.log"),
        "StandardErrorPath": str(logs / f"{label}.err.log"),
    }


def _assert_safe(
    plists: dict[str, dict[str, Any]],
    release: Path,
    runtime_env: Path,
    lineage: Path,
    state: Path,
) -> None:
    expected = build_expected_arguments(release, runtime_env, lineage, state)
    for key, label in (("n5", N5_LABEL), ("n6", N6_LABEL)):
        plist = plists[key]
        if plist.get("Label") != label:
            raise ValueError("unexpected trigger-status LaunchAgent label")
        if plist.get("ProgramArguments") != expected[key]:
            raise ValueError("trigger-status ProgramArguments drift")
        if plist.get("RunAtLoad") is not False or plist.get("KeepAlive") is not False:
            raise ValueError("trigger-status runners must remain non-resident one-shot")
        if plist.get("StartInterval") != START_INTERVAL_SECONDS:
            raise ValueError("trigger-status StartInterval must be 30")
        joined = " ".join(expected[key]).lower()
        forbidden = (
            "launchctl",
            "kickstart",
            "migration",
            "rollback",
            "run_n4",
            "run_n3",
            "run_n1",
            "run_n2",
            "trigger_pct",
            ";",
            "&&",
            "|",
        )
        found = [token for token in forbidden if token in joined]
        if found:
            raise ValueError(f"unsafe trigger-status ProgramArguments token(s): {found}")


def build_expected_arguments(
    release: Path,
    runtime_env: Path,
    lineage: Path,
    state: Path,
) -> dict[str, list[str]]:
    python = runtime_env / "bin/python3.11"
    return {
        "n5": [
            str(python),
            str(release / "scripts/run_n5_trigger_status_forward_current_once.py"),
            "--lineage-config",
            str(lineage),
            "--consumer-name",
            N5_CONSUMER_NAME,
            "--max-events",
            str(MAX_EVENTS),
            "--max-runtime-seconds",
            str(N5_MAX_RUNTIME_SECONDS),
            "--singleton-lock-path",
            str(state / "locks/n5_trigger_status_forward.lock"),
            "--execute",
            "--user-confirmed",
            "--json-report-path",
            str(state / "reports/n5_trigger_status_forward_current.json"),
            "--history-path",
            str(state / "history/n5_trigger_status_forward_current.jsonl"),
        ],
        "n6": [
            str(python),
            str(release / "scripts/run_n6_trigger_status_projection_current_once.py"),
            "--lineage-config",
            str(lineage),
            "--limit",
            str(MAX_EVENTS),
            "--singleton-lock-path",
            str(state / "locks/n6_trigger_status_projection.lock"),
            "--execute",
            "--user-confirmed",
            "--json-report-path",
            str(state / "reports/n6_trigger_status_projection_current.json"),
            "--history-path",
            str(state / "history/n6_trigger_status_projection_current.jsonl"),
        ],
    }


def write_launchd_plan(
    *,
    output_dir: Path,
    release_path: Path,
    runtime_env_path: Path,
    lineage_config_path: Path = DEFAULT_LINEAGE_CONFIG_PATH,
    state_root: Path = DEFAULT_STATE_ROOT,
) -> dict[str, Any]:
    report = build_launchd_plan(
        release_path=release_path,
        runtime_env_path=runtime_env_path,
        lineage_config_path=lineage_config_path,
        state_root=state_root,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in report["activation_order"]:
        path = output_dir / f"{report['release_id']}.{report[key]['label']}.plist"
        with path.open("wb") as fh:
            plistlib.dump(report[key]["plist"], fh, sort_keys=True)
        report[key]["plist_path"] = str(path)
    return report


def _absolute(value: Path, name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tmp/trigger_status_launchd_plan")
    parser.add_argument("--release-path", required=True)
    parser.add_argument("--runtime-env-path", required=True)
    parser.add_argument("--lineage-config-path", default=str(DEFAULT_LINEAGE_CONFIG_PATH))
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = write_launchd_plan(
        output_dir=Path(args.output_dir),
        release_path=Path(args.release_path),
        runtime_env_path=Path(args.runtime_env_path),
        lineage_config_path=Path(args.lineage_config_path),
        state_root=Path(args.state_root),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("PLAN_ONLY_PASS labels=" + ",".join(report[key]["label"] for key in report["activation_order"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
