#!/usr/bin/env python3
"""Build plan-only LaunchAgent plist for daily hot keep-5 cleanup."""

from __future__ import annotations

import argparse
import json
import plistlib
import sys
from pathlib import Path
from typing import Any

from ashare_v3.ingestion.runtime_archive import DEFAULT_RUNTIME_ARCHIVE_ROOT
from ashare_v3.ingestion.runtime_archive_execute import DEFAULT_DSN


CLEANUP_LABEL = "com.ashare-v3.runtime-hot-cleanup-keep5-daily"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_runtime_archive_cleanup_launchd_plan(
    *,
    project_root: Path = PROJECT_ROOT,
    python_executable: str = sys.executable,
    dsn: str = DEFAULT_DSN,
    archive_root: str = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    local_archive_current_pointer_path: str | None = None,
    local_archive_root: str = "/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts",
) -> dict[str, Any]:
    root = Path(project_root)
    logs = root / "logs/runtime_archive_cleanup"
    pointer_path = _require_absolute_evidence_path(
        "local_archive_current_pointer_path", local_archive_current_pointer_path
    )
    cleanup_plist = _build_plist(
        label=CLEANUP_LABEL,
        project_root=root,
        python_executable=python_executable,
        script="scripts/run_runtime_hot_keep5_cleanup_once.py",
        args=[
            "--dsn",
            dsn,
            "--archive-root",
            archive_root,
            "--execute",
            "--local-archive-current-pointer-path",
            pointer_path,
            "--local-archive-root",
            local_archive_root,
            "--local-only",
        ],
        hour=1,
        minute=0,
        stdout=logs / "cleanup_stdout.log",
        stderr=logs / "cleanup_stderr.log",
    )
    return {
        "schema": "RuntimeHotCleanupPlan.v2",
        "stage": "V3_RUNTIME_HOT_KEEP5_ARCHIVE_GATED_DAILY_LAUNCHD_PLAN",
        "local_cleanup_policy": "verified-archive-required",
        "launchd_plist_keys": ["cleanup"],
        "cleanup": {"label": CLEANUP_LABEL, "plist": cleanup_plist},
        "side_effects": {
            "launchd_mutated": False,
            "worker_started": False,
            "writes_database": False,
            "archive_executed": False,
            "cleanup_executed": False,
        },
    }


def _require_absolute_evidence_path(name: str, value: str | None) -> str:
    if not value:
        raise ValueError(f"{name} is required for verified-archive-required cleanup")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must be an absolute normalized path")
    return str(path)


def _build_plist(
    *,
    label: str,
    project_root: Path,
    python_executable: str,
    script: str,
    args: list[str],
    hour: int,
    minute: int,
    stdout: Path,
    stderr: Path,
) -> dict[str, Any]:
    return {
        "Label": label,
        "ProgramArguments": [python_executable, script, *args],
        "WorkingDirectory": str(project_root),
        "EnvironmentVariables": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "src:scripts:.",
        },
        "RunAtLoad": False,
        "KeepAlive": False,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(stdout),
        "StandardErrorPath": str(stderr),
    }


def materialize_plists(
    *,
    output_dir: Path,
    project_root: Path = PROJECT_ROOT,
    python_executable: str = sys.executable,
    dsn: str = DEFAULT_DSN,
    archive_root: str = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    local_archive_current_pointer_path: str | None = None,
    local_archive_root: str = "/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts",
) -> dict[str, Any]:
    report = build_runtime_archive_cleanup_launchd_plan(
        project_root=project_root,
        python_executable=python_executable,
        dsn=dsn,
        archive_root=archive_root,
        local_archive_current_pointer_path=local_archive_current_pointer_path,
        local_archive_root=local_archive_root,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in report["launchd_plist_keys"]:
        path = output_dir / f"{report[key]['label']}.plist"
        with path.open("wb") as fh:
            plistlib.dump(report[key]["plist"], fh, sort_keys=True)
        report[key]["plist_path"] = str(path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="launchd")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--archive-root", default=DEFAULT_RUNTIME_ARCHIVE_ROOT)
    parser.add_argument("--local-archive-current-pointer-path", required=True)
    parser.add_argument(
        "--local-archive-root",
        default="/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = materialize_plists(
        output_dir=Path(args.output_dir),
        project_root=Path(args.project_root),
        python_executable=args.python_executable,
        dsn=args.dsn,
        archive_root=args.archive_root,
        local_archive_current_pointer_path=args.local_archive_current_pointer_path,
        local_archive_root=args.local_archive_root,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) if args.json else "\n".join(report[key]["plist_path"] for key in report["launchd_plist_keys"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
