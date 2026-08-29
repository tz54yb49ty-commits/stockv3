#!/usr/bin/env python3
"""Run Windows N2, N3 post-close context, and N4 startup readiness in order."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from ashare_v3.market.windows_n3_previous_day_context import (
    PostgresPreviousDayContextLoader,
)
from ashare_v3.market.windows_n3_read_model import (
    N3ActiveReadModel,
    WindowsN3ReadOnlyRepository,
)
from ashare_v3.trigger.windows_n4_memory import build_windows_n4_runtime


N2_PASS_RESULTS = frozenset(
    {"N2_AFTER_N1_PASS", "SKIPPED_IDENTICAL_PASSED_ACTIVE"}
)
N3_PASS_RESULTS = frozenset(
    {
        "N3_PREVIOUS_DAY_CONTEXT_COMPLETE",
        "N3_PREVIOUS_DAY_CONTEXT_SKIPPED_COMPLETE",
    }
)


@dataclass(frozen=True, slots=True)
class N4Readiness:
    state_counts: Mapping[str, int]
    versions: Mapping[str, int]
    channel_statuses: Mapping[str, str]
    context_terminal_counts: Mapping[str, int]


def validate_n4_readiness(
    model: N3ActiveReadModel,
    context: Any,
    *,
    runtime_builder: Callable[[N3ActiveReadModel], Any] = build_windows_n4_runtime,
) -> N4Readiness:
    if (
        context.source_condition_run_id,
        context.source_trade_date,
        context.for_trade_date,
    ) != (model.run_id, model.source_trade_date, model.for_trade_date):
        raise RuntimeError("N3 context lineage does not match the active N2 run")

    expected = {
        "stock": len(model.stock),
        "index": len(model.index),
        "board": len(model.board),
    }
    terminal = {
        asset_kind: sum(int(value) for value in context.status_counts[asset_kind].values())
        for asset_kind in expected
    }
    if terminal != expected:
        raise RuntimeError(
            f"N3 context terminal counts do not match N2 objects: {terminal} != {expected}"
        )
    usable = {
        asset_kind: int(context.status_counts[asset_kind].get("ready", 0))
        + int(context.status_counts[asset_kind].get("partial", 0))
        for asset_kind in expected
    }
    unusable_channels = tuple(
        asset_kind
        for asset_kind, expected_count in expected.items()
        if expected_count > 0 and usable[asset_kind] == 0
    )
    if unusable_channels:
        raise RuntimeError(
            "N3 context has no usable rows for: " + ", ".join(unusable_channels)
        )

    runtime = runtime_builder(model)
    snapshots = {
        "stock": runtime.get_stock_states(),
        "index": runtime.get_index_states(),
        "board": runtime.get_board_states(),
    }
    state_counts = {key: len(value.states) for key, value in snapshots.items()}
    versions = {key: int(value.version) for key, value in snapshots.items()}
    statuses = {key: str(value.channel_status) for key, value in snapshots.items()}
    if state_counts != expected:
        raise RuntimeError(
            f"N4 warming state counts do not match N2 objects: {state_counts} != {expected}"
        )
    if any(value != 0 for value in versions.values()):
        raise RuntimeError(f"N4 readiness must start at version zero: {versions}")
    if any(value != "warming" for value in statuses.values()):
        raise RuntimeError(f"N4 readiness must be warming: {statuses}")
    return N4Readiness(state_counts, versions, statuses, terminal)


def run_postclose_fastlane(
    *,
    run_n2: Callable[[], Mapping[str, Any]],
    run_n3: Callable[[str], Mapping[str, Any]],
    load_model: Callable[[str], N3ActiveReadModel],
    load_context: Callable[[N3ActiveReadModel], Any],
    runtime_builder: Callable[[N3ActiveReadModel], Any] = build_windows_n4_runtime,
) -> dict[str, Any]:
    n2 = dict(run_n2())
    n2_result = str(n2.get("result") or "")
    if n2_result == "SKIPPED_NON_TRADING_DAY":
        return {
            "result": "WINDOWS_POSTCLOSE_FASTLANE_SKIPPED_NON_TRADING_DAY",
            "n2_result": n2_result,
            "source_trade_date": n2.get("source_trade_date"),
            "for_trade_date": None,
            "n4_database_write_count": 0,
            "trigger_event_count": 0,
        }
    if n2_result not in N2_PASS_RESULTS:
        raise RuntimeError(f"N2 post-close stage did not pass: {n2_result}")

    source_trade_date = str(n2.get("source_trade_date") or "")
    for_trade_date = str(n2.get("for_trade_date") or "")
    active_run_id = str(n2.get("active_run_id") or "")
    if not source_trade_date or not for_trade_date or not active_run_id:
        raise RuntimeError("N2 post-close result is missing lineage")

    n3 = dict(run_n3(for_trade_date))
    n3_result = str(n3.get("result") or "")
    if n3_result not in N3_PASS_RESULTS:
        raise RuntimeError(f"N3 previous-day context stage did not pass: {n3_result}")
    context_version = str(n3.get("context_version") or "")
    if not context_version:
        raise RuntimeError("N3 previous-day context result is missing context_version")

    model = load_model(for_trade_date)
    if (
        model.run_id,
        model.source_trade_date,
        model.for_trade_date,
    ) != (active_run_id, source_trade_date, for_trade_date):
        raise RuntimeError("active N2 lineage changed after the N3 stage")
    context = load_context(model)
    if str(context.context_version) != context_version:
        raise RuntimeError("loaded N3 context version does not match the N3 stage")
    readiness = validate_n4_readiness(
        model,
        context,
        runtime_builder=runtime_builder,
    )

    return {
        "result": "WINDOWS_POSTCLOSE_FASTLANE_PASS",
        "n1_completion_date": source_trade_date,
        "n2_result": n2_result,
        "n2_active_run_id": active_run_id,
        "source_trade_date": source_trade_date,
        "for_trade_date": for_trade_date,
        "n3_result": n3_result,
        "n3_context_run_id": str(n3.get("context_run_id") or context.context_run_id),
        "n3_context_version": context_version,
        "n3_expected_counts": dict(n3.get("expected_counts") or {}),
        "n3_terminal_counts": dict(n3.get("terminal_counts") or readiness.context_terminal_counts),
        "n3_status_counts": dict(n3.get("status_counts") or context.status_counts),
        "n4_readiness": asdict(readiness),
        "n4_database_write_count": 0,
        "trigger_event_count": 0,
    }


def _run_json_command(argv: Sequence[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        list(argv),
        cwd=str(cwd),
        env=dict(os.environ),
        text=True,
        capture_output=True,
        check=False,
    )
    text = completed.stdout.strip()
    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"child command returned invalid JSON: {' '.join(argv)}"
        ) from error
    if completed.returncode != 0:
        detail = payload or (completed.stderr or text).strip()
        raise RuntimeError(
            f"child command exited {completed.returncode}: {' '.join(argv)}: {detail}"
        )
    if not isinstance(payload, dict):
        raise RuntimeError("child command JSON must be an object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dsn",
        default=os.environ.get(
            "ASHARE_V3_DSN",
            os.environ.get(
                "ASHARE_V3_POSTGRES_DSN",
                "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3",
            ),
        ),
    )
    parser.add_argument("--policy", default="configs/n2_policy/default_policy_draft.json")
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument(
        "--context-version",
        default=os.environ.get("ASHARE_V3_N3_CONTEXT_VERSION", "v1"),
    )
    parser.add_argument("--tq-module-path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    n2_argv = [
        sys.executable,
        str(root / "scripts/run_windows_n2_after_n1.py"),
        "--dsn",
        args.dsn,
        "--policy",
        args.policy,
        "--poll-seconds",
        str(args.poll_seconds),
    ]

    def run_n3(for_trade_date: str) -> Mapping[str, Any]:
        argv = [
            sys.executable,
            str(root / "scripts/run_windows_n3_previous_day_context.py"),
            "--dsn",
            args.dsn,
            "--for-trade-date",
            for_trade_date,
            "--context-version",
            args.context_version,
        ]
        if args.tq_module_path:
            argv.extend(("--tq-module-path", args.tq_module_path))
        return _run_json_command(argv, cwd=root)

    try:
        payload = run_postclose_fastlane(
            run_n2=lambda: _run_json_command(n2_argv, cwd=root),
            run_n3=run_n3,
            load_model=WindowsN3ReadOnlyRepository(args.dsn).load_active,
            load_context=PostgresPreviousDayContextLoader(
                args.dsn,
                context_version=args.context_version,
            ).load,
        )
    except Exception as error:
        print(
            json.dumps(
                {
                    "result": "WINDOWS_POSTCLOSE_FASTLANE_FAILED",
                    "error": f"{type(error).__name__}:{error}",
                    "n4_database_write_count": 0,
                    "trigger_event_count": 0,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
