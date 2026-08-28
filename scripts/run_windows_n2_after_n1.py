#!/usr/bin/env python3
"""Wait for Windows N1 completion and run the existing N2 execute entrypoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from ashare_v3.condition.windows_n2_after_n1 import (
    PostgresAfterN1Repository,
    run_windows_n2_after_n1,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
    from run_condition_layer_execute import load_condition_runner_policy
except ModuleNotFoundError:
    from scripts.check_condition_source_ready import DEFAULT_DSN
    from scripts.run_condition_layer_execute import load_condition_runner_policy


def execute_existing_n2(
    *, source_trade_date: str, dsn: str, policy_path: Path,
) -> dict[str, Any]:
    runner_path = Path(__file__).with_name("run_condition_layer_execute.py")
    env = dict(os.environ)
    env["ASHARE_V3_POSTGRES_DSN"] = dsn
    completed = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--source-trade-date",
            source_trade_date,
            "--policy",
            str(policy_path),
            "--execute",
            "--user-confirmed",
            "--operator",
            "windows_n2_after_n1",
            "--confirmation-note",
            "scheduled after N1 fastlane_complete",
            "--json",
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"N2 execute exited {completed.returncode}: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("N2 execute did not return JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("N2 execute JSON must be an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Windows N2 after the daily N1 completion marker.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument(
        "--policy",
        default="configs/n2_policy/default_policy_draft.json",
    )
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path
    policy_bundle = load_condition_runner_policy(policy_path)
    result = run_windows_n2_after_n1(
        repository=PostgresAfterN1Repository(args.dsn),
        policy_hash=policy_bundle.policy_hash,
        execute_n2=lambda source_trade_date: execute_existing_n2(
            source_trade_date=source_trade_date,
            dsn=args.dsn,
            policy_path=policy_path,
        ),
        poll_seconds=args.poll_seconds,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    if result.result in {"N2_AFTER_N1_PASS", "SKIPPED_NON_TRADING_DAY", "SKIPPED_IDENTICAL_PASSED_ACTIVE"}:
        return 0
    if result.result.startswith("BLOCKED_"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
