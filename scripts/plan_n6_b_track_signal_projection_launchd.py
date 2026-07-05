#!/usr/bin/env python3
"""Build plan-only LaunchAgent plist for the N6 B-track signal poller."""

from __future__ import annotations

import argparse
import json
import plistlib
import sys
from pathlib import Path
from typing import Any


LABEL = "com.ashare-v3.n6.b-track-signal-poller"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LINEAGE_CONFIG_PATH = "docs/runtime/current_intraday_worker_lineage.json"
DEFAULT_REPORT_PATH = "tmp/N6_b_track_signal_projection_poller_launchd_report.json"
DEFAULT_HISTORY_PATH = "tmp/N6_b_track_signal_projection_poller_history.jsonl"


def build_launchd_plan(
    *,
    project_root: Path = PROJECT_ROOT,
    python_executable: str = sys.executable,
) -> dict[str, Any]:
    root = Path(project_root)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [
            python_executable,
            "scripts/run_n6_b_track_signal_projection_poller_once.py",
            "--lineage-config",
            DEFAULT_LINEAGE_CONFIG_PATH,
            "--execute",
            "--user-confirmed",
            "--json-report-path",
            DEFAULT_REPORT_PATH,
            "--history-path",
            DEFAULT_HISTORY_PATH,
        ],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "src:scripts:.",
        },
        "RunAtLoad": False,
        "KeepAlive": False,
        "StartInterval": 3,
        "StandardOutPath": str(root / "tmp/com.ashare-v3.n6.b-track-signal-poller.out.log"),
        "StandardErrorPath": str(root / "tmp/com.ashare-v3.n6.b-track-signal-poller.err.log"),
    }
    _assert_plist_safe(plist)
    return {
        "stage": "N6_B_TRACK_SIGNAL_PROJECTION_LAUNCHD_PLAN",
        "result": "PLAN_ONLY_PASS",
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
    project_root: Path = PROJECT_ROOT,
    python_executable: str = sys.executable,
) -> dict[str, Any]:
    report = build_launchd_plan(project_root=project_root, python_executable=python_executable)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in report["launchd_plist_keys"]:
        path = output_dir / f"{report[key]['label']}.plist"
        with path.open("wb") as fh:
            plistlib.dump(report[key]["plist"], fh, sort_keys=True)
        report[key]["plist_path"] = str(path)
    return report


def _assert_plist_safe(plist: dict[str, Any]) -> None:
    args = [str(arg) for arg in plist.get("ProgramArguments", [])]
    joined = " ".join(args).lower()
    forbidden = ("run_n3", "run_n4", "run_n5", "archive", "cleanup", "launchctl", "rollback", ";", "&&", "|")
    found = [token for token in forbidden if token in joined]
    if found:
        raise ValueError(f"unsafe ProgramArguments token(s): {found}")
    if plist.get("RunAtLoad") is not False:
        raise ValueError("RunAtLoad must be false")
    if plist.get("KeepAlive") is not False:
        raise ValueError("KeepAlive must be false")
    if int(plist.get("StartInterval") or 0) != 3:
        raise ValueError("StartInterval must be 3")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tmp/runtime_keep5_launchd_plan")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = write_launchd_plan(
        output_dir=Path(args.output_dir),
        project_root=Path(args.project_root),
        python_executable=args.python_executable,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"PLAN_ONLY_PASS label={LABEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
