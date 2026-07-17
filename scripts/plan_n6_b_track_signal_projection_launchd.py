#!/usr/bin/env python3
"""Build a plan-only immutable LaunchAgent plist for N6 B-track projection."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
from pathlib import Path
from typing import Any


LABEL = "com.ashare-v3.n6.b-track-signal-projection-batch-v1"
CONSUMER_NAME = "n6_b_track_signal_projection_poller_v1"
BATCH_SIZE = 100
START_INTERVAL_SECONDS = 3
DEFAULT_LINEAGE_CONFIG_PATH = Path(
    "/Users/chuanfuchen/Documents/A股监控系统v3/docs/runtime/current_intraday_worker_lineage.json"
)
DEFAULT_STATE_ROOT = Path("/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track")
RELEASE_ID_PATTERN = re.compile(r"^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$")


def build_launchd_plan(
    *,
    release_path: Path,
    runtime_env_path: Path,
    lineage_config_path: Path = DEFAULT_LINEAGE_CONFIG_PATH,
    state_root: Path = DEFAULT_STATE_ROOT,
) -> dict[str, Any]:
    release = _absolute_path(release_path, "release_path")
    runtime_env = _absolute_path(runtime_env_path, "runtime_env_path")
    lineage = _absolute_path(lineage_config_path, "lineage_config_path")
    state = _absolute_path(state_root, "state_root")
    if not RELEASE_ID_PATTERN.fullmatch(release.name):
        raise ValueError("release_path must end with <YYYYMMDD_HHMMSS>__<40hex>")

    python_executable = runtime_env / "bin/python3.11"
    runner = release / "scripts/run_n6_b_track_signal_projection_poller_once.py"
    singleton = state / "locks/n6_b_track_signal_projection_poller.lock"
    report = state / "reports/N6_b_track_signal_projection_batch_v1_report.json"
    history = state / "history/N6_b_track_signal_projection_batch_v1_history.jsonl"
    logs = state / "logs"
    plist = {
        "Label": LABEL,
        "ProgramArguments": [
            str(python_executable),
            str(runner),
            "--lineage-config",
            str(lineage),
            "--consumer-name",
            CONSUMER_NAME,
            "--max-events",
            str(BATCH_SIZE),
            "--singleton-lock-path",
            str(singleton),
            "--cas-authority-mode",
            "internal_one_shot",
            "--execute",
            "--user-confirmed",
            "--json-report-path",
            str(report),
            "--history-path",
            str(history),
        ],
        "WorkingDirectory": str(state / "cwd"),
        "EnvironmentVariables": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": ":".join((str(release / "src"), str(release / "scripts"), str(release))),
        },
        "RunAtLoad": False,
        "KeepAlive": False,
        "StartInterval": START_INTERVAL_SECONDS,
        "StandardOutPath": str(logs / f"{LABEL}.out.log"),
        "StandardErrorPath": str(logs / f"{LABEL}.err.log"),
    }
    _assert_plist_safe(
        plist,
        release_path=release,
        runtime_env_path=runtime_env,
        lineage_config_path=lineage,
        state_root=state,
    )
    return {
        "stage": "N6_B_TRACK_SIGNAL_PROJECTION_BATCH_LAUNCHD_PLAN",
        "result": "PLAN_ONLY_PASS",
        "release_id": release.name,
        "launchd_plist_keys": ["n6_b_track_signal"],
        "n6_b_track_signal": {"label": LABEL, "plist": plist},
        "side_effects": {
            "launchd_mutated": False,
            "worker_started": False,
            "runtime_executed": False,
            "writes_database": False,
            "archive_executed": False,
            "cleanup_executed": False,
        },
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
    for key in report["launchd_plist_keys"]:
        path = output_dir / f"{report['release_id']}.{report[key]['label']}.plist"
        with path.open("wb") as fh:
            plistlib.dump(report[key]["plist"], fh, sort_keys=True)
        report[key]["plist_path"] = str(path)
    return report


def _absolute_path(value: Path, name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path


def _assert_plist_safe(
    plist: dict[str, Any],
    *,
    release_path: Path,
    runtime_env_path: Path,
    lineage_config_path: Path,
    state_root: Path,
) -> None:
    args = [str(arg) for arg in plist.get("ProgramArguments", [])]
    expected_args = [
        str(runtime_env_path / "bin/python3.11"),
        str(release_path / "scripts/run_n6_b_track_signal_projection_poller_once.py"),
        "--lineage-config",
        str(lineage_config_path),
        "--consumer-name",
        CONSUMER_NAME,
        "--max-events",
        str(BATCH_SIZE),
        "--singleton-lock-path",
        str(state_root / "locks/n6_b_track_signal_projection_poller.lock"),
        "--cas-authority-mode",
        "internal_one_shot",
        "--execute",
        "--user-confirmed",
        "--json-report-path",
        str(state_root / "reports/N6_b_track_signal_projection_batch_v1_report.json"),
        "--history-path",
        str(state_root / "history/N6_b_track_signal_projection_batch_v1_history.jsonl"),
    ]
    if args != expected_args:
        raise ValueError("ProgramArguments drift from reviewed N6 batch contract")
    if plist.get("Label") != LABEL:
        raise ValueError("unexpected LaunchAgent label")
    if plist.get("RunAtLoad") is not False or plist.get("KeepAlive") is not False:
        raise ValueError("N6 batch poller must remain a non-resident one-shot")
    if int(plist.get("StartInterval") or 0) != START_INTERVAL_SECONDS:
        raise ValueError("StartInterval must be 3")
    joined = " ".join(args).lower()
    forbidden = (
        "--dsn",
        "--for-trade-date",
        "--historical-backfill",
        "external_bounded_canary",
        "run_n3",
        "run_n4",
        "run_n5",
        "launchctl",
        "rollback",
        ";",
        "&&",
        "|",
    )
    found = [token for token in forbidden if token in joined]
    if found:
        raise ValueError(f"unsafe ProgramArguments token(s): {found}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tmp/n6_batch_launchd_plan")
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
        print(f"PLAN_ONLY_PASS label={LABEL} release_id={report['release_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
