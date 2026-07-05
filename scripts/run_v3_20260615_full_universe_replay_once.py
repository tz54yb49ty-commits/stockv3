#!/usr/bin/env python3
"""Runtime-control plan shim for 20260615 full-universe replay.

This file intentionally does not execute N3, N4, N5, or N6.  The previous
version bundled a direct N3->N6 replay pipeline, which violates the v3 layer
contract.  It now only emits a layer-separated plan and blocks any attempt to
run the multi-layer pipeline from one process.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


RUNTIME_CONTROL_PLAN_ONLY = True
ORCHESTRATION_MODE = "runtime_control_plan_only"
CROSS_LAYER_EXECUTION_ALLOWED = False
DEFAULT_REPORT_JSON = "docs/V3_20260615_FULL_UNIVERSE_REPLAY_LAYER_SEPARATION_PLAN.json"
DEFAULT_REPORT_MD = "docs/V3_20260615_FULL_UNIVERSE_REPLAY_LAYER_SEPARATION_PLAN.md"
ASIA_SHANGHAI_OFFSET = "+08:00"


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def normalize_midday_source_labels(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize source 11:30 labels to V3's 13:00 bridge label.

    V3 does not fabricate a missing 11:30 minute row.  If a source adapter
    labels the lunch close as 11:30, the runtime bridge represents it as the
    13:00 comparison anchor so 13:01 compares to 13:00.
    """

    normalized: list[dict[str, Any]] = []
    for row in rows:
        output = dict(row)
        bar_time = output.get("bar_time")
        if isinstance(bar_time, str):
            dt = datetime.fromisoformat(bar_time)
        elif isinstance(bar_time, datetime):
            dt = bar_time
        else:
            normalized.append(output)
            continue
        if dt.hour == 11 and dt.minute == 30:
            output["bar_time"] = dt.replace(hour=13, minute=0)
            raw_payload = dict(output.get("raw_payload") or {})
            raw_payload.setdefault("source_label_time", "11:30")
            raw_payload["v3_normalized_label_time"] = "13:00"
            raw_payload["midday_bridge_policy"] = "source_1130_label_normalized_to_v3_1300"
            output["raw_payload"] = raw_payload
        normalized.append(output)
    normalized.sort(key=lambda item: item.get("bar_time") or datetime.min)
    return normalized


def classify_full_universe_fetch_results(fetch_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    tolerated_keys = {"index:BJ:899050", "index:BJ:899601"}
    tolerated: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    for row in fetch_results:
        identity = str(row.get("identity_key") or "")
        status = str(row.get("status") or "")
        row_count = int(row.get("row_count") or 0)
        if status == "missing" or row_count <= 0:
            if identity in tolerated_keys:
                tolerated.append(dict(row))
            else:
                blocking.append(dict(row))
    return {
        "tolerated_missing": tolerated,
        "blocking_fetches": blocking,
        "tolerated_missing_policy": "quality_visible_no_fabricated_minute_rows",
    }


def build_layer_separated_plan(*, for_trade_date: str = "20260615", mode: str = "attachment_rule_canonical_policy_fix") -> dict[str, Any]:
    return {
        "result": "PLAN_ONLY",
        "orchestration_mode": ORCHESTRATION_MODE,
        "cross_layer_execution_allowed": CROSS_LAYER_EXECUTION_ALLOWED,
        "for_trade_date": for_trade_date,
        "mode": mode,
        "layer_separated_steps": [
            {
                "layer_role": "N3_market_data",
                "gate": f"V3_{for_trade_date}_N3_FULL_UNIVERSE_METRIC_CONTRACT_PREFLIGHT_GATE",
                "allowed_scope": "N3 data and action-confirmation metric contracts only",
            },
            {
                "layer_role": "N4_trigger",
                "gate": f"V3_{for_trade_date}_N4_ATTACHMENT_RULE_ALIGNED_REPLAY_CONTRACT_PREFLIGHT_GATE",
                "allowed_scope": "N4 trigger replay only after N3 post-review",
            },
            {
                "layer_role": "N5_action",
                "gate": f"V3_{for_trade_date}_N5_ATTACHMENT_RULE_ALIGNED_REPLAY_CONTRACT_PREFLIGHT_GATE",
                "allowed_scope": "N5 action replay only after N4 post-review",
            },
            {
                "layer_role": "N6_user",
                "gate": f"V3_{for_trade_date}_N6_PROJECTION_AFTER_N5_ATTACHMENT_RULE_REPLAY_CONTRACT_PREFLIGHT_GATE",
                "allowed_scope": "N6 projection only after N5 post-review",
            },
        ],
        "forbidden_scope": {
            "n3_execute_from_this_script": True,
            "n4_execute_from_this_script": True,
            "n5_execute_from_this_script": True,
            "n6_execute_from_this_script": True,
            "database_write_from_this_script": True,
            "outbox_consume_or_update_from_this_script": True,
            "scheduler_or_worker_start_from_this_script": True,
        },
    }


def format_plan(plan: Mapping[str, Any]) -> str:
    lines = [
        "# V3 20260615 Full-Universe Replay Layer Separation Plan",
        "",
        f"- result: `{plan.get('result')}`",
        f"- orchestration_mode: `{plan.get('orchestration_mode')}`",
        f"- cross_layer_execution_allowed: `{plan.get('cross_layer_execution_allowed')}`",
        "",
        "## Layer Steps",
    ]
    for step in plan.get("layer_separated_steps") or []:
        lines.append(f"- `{step['layer_role']}` -> `{step['gate']}`")
    lines.extend(
        [
            "",
            "This compatibility shim deliberately refuses to execute a combined N3->N6 pipeline.",
            "Invoke each gate in its own layer_role session with its own contract, preflight, rollback, and post-review.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--for-trade-date", default="20260615")
    parser.add_argument("--mode", default="attachment_rule_canonical_policy_fix")
    parser.add_argument("--json-report-path", default=DEFAULT_REPORT_JSON)
    parser.add_argument("--markdown-report-path", default=DEFAULT_REPORT_MD)
    parser.add_argument("--execute", action="store_true", help="Always blocked by this runtime-control shim.")
    parser.add_argument("--user-confirmed", action="store_true")
    args = parser.parse_args(argv)

    plan = build_layer_separated_plan(for_trade_date=args.for_trade_date, mode=args.mode)
    if args.execute:
        plan["result"] = "BLOCKED"
        plan["blocker"] = "cross_layer_full_universe_replay_removed_use_layer_gates"
    write_json(args.json_report_path, plan)
    write_text(args.markdown_report_path, format_plan(plan))
    print(json.dumps({"result": plan["result"], "report": args.json_report_path}, ensure_ascii=False))
    return 2 if args.execute else 0


if __name__ == "__main__":
    raise SystemExit(main())
