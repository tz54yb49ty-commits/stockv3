#!/usr/bin/env python3
"""Install the post-close N1-N2-N3A1 one-shot LaunchAgent."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.runtime.post_close_fastlane import LAUNCHD_LABEL, build_launchd_plist  # noqa: E402


DEFAULT_DSN = os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--launch-agents-dir", default=str(Path.home() / "Library/LaunchAgents"))
    parser.add_argument("--load", action="store_true", help="Bootstrap the LaunchAgent after writing the plist.")
    parser.add_argument("--unload-first", action="store_true", help="Bootout existing label before bootstrap.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root)
    launch_agents_dir = Path(args.launch_agents_dir)
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "logs/post_close_fastlane").mkdir(parents=True, exist_ok=True)

    plist_text = build_launchd_plist(
        project_root=project_root,
        python_executable=args.python_executable,
        dsn=args.dsn,
    )
    target = launch_agents_dir / f"{LAUNCHD_LABEL}.plist"
    target.write_text(plist_text, encoding="utf-8")

    repo_copy = project_root / "launchd" / f"{LAUNCHD_LABEL}.plist"
    if repo_copy.exists():
        shutil.copyfile(target, repo_copy)

    if args.load:
        domain = f"gui/{os.getuid()}"
        if args.unload_first:
            subprocess.run(["launchctl", "bootout", domain, str(target)], check=False)
        completed = subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=False)
        if completed.returncode != 0:
            return completed.returncode
    print(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
