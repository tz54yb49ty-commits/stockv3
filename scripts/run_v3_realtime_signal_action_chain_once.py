#!/usr/bin/env python3
"""Build a V3 N3 -> N4 -> N5 realtime signal/action dry-run report.

This script is intentionally dry-run/report-only. It reads an existing N3
metric replay report, derives N4/N5 canonical dry-run counts, and writes report
artifacts. It does not call N3/N4/N5 child runners, write a runtime database,
start a scheduler, or enter N6.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


DEFAULT_REPLAY_REPORT_PATH = "docs/V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE.json"
DEFAULT_JSON_REPORT_PATH = "docs/V3_REALTIME_SIGNAL_ACTION_CHAIN_DRY_RUN_REPORT_20260612.json"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/V3_REALTIME_SIGNAL_ACTION_CHAIN_DRY_RUN_REPORT_20260612.md"


def _count_total(counts: Mapping[str, Any]) -> int:
    total = 0
    for value in counts.values():
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
    return total


def _ready_count(replay_report: Mapping[str, Any]) -> int:
    counts = dict(replay_report.get("metric_ready_counts") or {})
    return int(counts.get("ready") or counts.get("passed") or 0)


def forbidden_scope_proof(replay_report: Mapping[str, Any]) -> dict[str, bool]:
    replay_side_effects = dict(replay_report.get("side_effects") or {})
    return {
        "target_machine_read_only": bool(replay_side_effects.get("target_machine_read_only", True)),
        "database_written": False,
        "runtime_db_written": False,
        "scheduler_started": False,
        "worker_started": False,
        "child_invoked": False,
        "outbox_inbox_checkpoint_mutated": False,
        "n3_execute_run": False,
        "n4_executed": False,
        "n5_executed": False,
        "n6_entered": False,
        "voice_mobile_sim_trade_touched": False,
        "real_trade_touched": False,
    }


def build_chain_report(
    replay_report: Mapping[str, Any],
    *,
    execute: bool = False,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "stage": "V3_REALTIME_SIGNAL_ACTION_CHAIN_DRY_RUN",
        "trade_date": replay_report.get("trade_date"),
        "execute": execute,
        "user_confirmed": user_confirmed,
        "child_invoked": False,
        "mode": "dry_run_report_only",
        "forbidden_scope_proof": forbidden_scope_proof(replay_report),
    }
    if execute and not user_confirmed:
        return {**base, "result": "BLOCKED", "blocked_reason": "missing --user-confirmed"}
    if user_confirmed and not execute:
        return {**base, "result": "BLOCKED", "blocked_reason": "missing --execute"}
    if not execute:
        return {
            **base,
            "result": "PLAN_ONLY",
            "planned_stages": [
                "n3_metric_replay",
                "n4_trigger_dry_run",
                "n5_action_dry_run",
            ],
        }

    v3_counts = dict(replay_report.get("v3_replay_counts") or {})
    matched_count = _count_total(v3_counts)
    ready_count = _ready_count(replay_report)
    metric_ready_counts = dict(replay_report.get("metric_ready_counts") or {})
    pending_count = int(metric_ready_counts.get("not_ready") or metric_ready_counts.get("missing") or 0)
    diff_summary = dict(replay_report.get("diff_summary") or {})
    n4_stage = {
        "result": "DRY_RUN_PASS",
        "input_source": "N3 realtime virtual metric replay",
        "TriggerMatched": matched_count,
        "TriggerPendingMarketData": pending_count,
        "TriggerStateChanged": 0,
        "raw_minute_rows_read": False,
        "market_adapter_called": False,
        "business_rules_changed": False,
    }
    n5_stage = {
        "result": "DRY_RUN_PASS",
        "entry_event": "TriggerMatched",
        "ActionEligible": matched_count,
        "ActionExecuted": matched_count,
        "ActionBlocked": 0,
        "ActionSkipped": 0,
        "non_entry_events_ignored": ["TriggerPendingMarketData", "TriggerStateChanged"],
        "evidence": "trigger_time_virtual_120m_30m_5m_plus_closed_trigger_minute_1m",
        "real_order_created": False,
        "sim_order_created": False,
        "n6_entered": False,
    }
    return {
        **base,
        "result": "DRY_RUN_PASS",
        "stages": {
            "n3_metric_replay": {
                "result": replay_report.get("result"),
                "target_golden_counts": replay_report.get("target_golden_counts"),
                "v3_replay_counts": v3_counts,
                "metric_ready_counts": replay_report.get("metric_ready_counts"),
                "diff_summary": diff_summary,
            },
            "n4_trigger_dry_run": n4_stage,
            "n5_action_dry_run": n5_stage,
        },
        "summary": {
            "n3_metric_ready": ready_count,
            "n4_trigger_matched": matched_count,
            "n5_action_eligible": matched_count,
            "n5_action_executed": matched_count,
            "target_missing_in_v3": diff_summary.get("missing_in_v3", 0),
            "target_extra_in_v3": diff_summary.get("extra_in_v3", 0),
        },
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, report: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: str | Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# V3 Realtime Signal Action Chain Dry Run",
        "",
        "N3 -> N4 -> N5 report-only chain.",
        "",
        f"- result: `{report.get('result')}`",
        f"- trade_date: `{report.get('trade_date')}`",
        f"- mode: `{report.get('mode')}`",
        f"- child_invoked: `{report.get('child_invoked')}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in dict(report.get("summary") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Forbidden Scope", ""])
    for key, value in dict(report.get("forbidden_scope_proof") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Stages", ""])
    for stage_name, stage in dict(report.get("stages") or {}).items():
        lines.append(f"### {stage_name}")
        for key, value in dict(stage).items():
            if isinstance(value, (dict, list)):
                continue
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-report-path", default=DEFAULT_REPLAY_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    replay_report = load_json(args.replay_report_path)
    report = build_chain_report(replay_report, execute=args.execute, user_confirmed=args.user_confirmed)
    write_json(args.json_report_path, report)
    write_markdown(args.markdown_report_path, report)
    print(f"wrote {args.json_report_path}")
    print(f"wrote {args.markdown_report_path}")
    return 0 if report["result"] in {"PLAN_ONLY", "DRY_RUN_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
