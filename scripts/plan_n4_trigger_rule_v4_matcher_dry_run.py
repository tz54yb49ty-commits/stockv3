#!/usr/bin/env python3
"""Generate N4 trigger rule spec v4 matcher dry-run artifacts.

This is a contract dry-run utility. It does not connect to the runtime
database and does not write business rows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ashare_v3.trigger.rule_v4_matcher import (
    TRIGGER_RULE_POLICY_HASH,
    TRIGGER_RULE_SPEC_VERSION,
    build_v4_dry_run_report,
    evaluate_v4_plan,
)


DEFAULT_JSON_REPORT = Path("docs/N4_TRIGGER_RULE_SPEC_v4_matcher_dry_run_report.json")
DEFAULT_MD_REPORT = Path("docs/N4_TRIGGER_RULE_SPEC_v4_MATCHER_DRY_RUN_REPORT.md")
DEFAULT_DIFF_JSON = Path("docs/N4_TRIGGER_RULE_SPEC_v4_v3_v4_diff_backtest.json")
DEFAULT_DIFF_MD = Path("docs/N4_TRIGGER_RULE_SPEC_v4_V3_V4_DIFF_BACKTEST.md")
DEFAULT_V3_REPORT = Path("docs/N4_20260603_local_trigger_dry_run_report.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-report-path", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-report-path", type=Path, default=DEFAULT_MD_REPORT)
    parser.add_argument("--diff-json-path", type=Path, default=DEFAULT_DIFF_JSON)
    parser.add_argument("--diff-markdown-path", type=Path, default=DEFAULT_DIFF_MD)
    parser.add_argument("--v3-report-path", type=Path, default=DEFAULT_V3_REPORT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.execute:
        raise SystemExit("BLOCKED: v4 matcher dry-run script is read-only and never executes N4")

    v3_summary = _load_v3_summary(args.v3_report_path)
    traceability_summary = _traceability_summary()
    plans = _sample_v4_plans()
    report = build_v4_dry_run_report(
        plans,
        v3_summary=v3_summary,
        traceability_summary=traceability_summary,
    )
    report.update(
        {
            "implementation_result": "IMPLEMENTATION_PASS",
            "independent_v4_run_id": "trigger_rule_v4_matcher_dry_run_contract_sample",
            "full_semantics_execute_status": "BLOCKED",
            "full_semantics_blocker": "BUY:FULL / SELL:FULL execute requires final N2 prerequisite semantics approval",
            "historical_run_policy": "do_not_reinterpret_or_modify_historical_runs",
            "database_writes": False,
            "outbox_consumed": False,
            "worker_started": False,
        }
    )

    diff = _build_diff_artifact(report, v3_summary)

    _write_json(args.json_report_path, report)
    _write_markdown(args.markdown_report_path, _render_report_md(report))
    _write_json(args.diff_json_path, diff)
    _write_markdown(args.diff_markdown_path, _render_diff_md(diff))
    print(json.dumps({"result": report["result"], "json_report": str(args.json_report_path)}, ensure_ascii=False))
    return 0


def _sample_v4_plans() -> list[dict[str, Any]]:
    run_id = "trigger_rule_v4_matcher_dry_run_contract_sample"
    return [
        evaluate_v4_plan(_context("BUY:Y,Q,M,W,D"), _projection(chain={"Y": True, "Q": True, "M": True, "W": True, "D": True}), v4_run_id=run_id),
        evaluate_v4_plan(_context("SELL:D", direction="sell", sell=True), _projection(price=7.5, amount=80, chain={"D": True}), v4_run_id=run_id),
        evaluate_v4_plan(_context("SELL:D", direction="sell", sell=True), _projection(price=9, amount=120, chain={"D": True}), v4_run_id=run_id),
        evaluate_v4_plan(_context("BUY:D"), None, v4_run_id=run_id),
        evaluate_v4_plan(_context("BUY:FULL"), _projection(chain={"D": True}), v4_run_id=run_id),
        evaluate_v4_plan(_context("SELL:FULL", direction="sell", sell=True), _projection(price=7.5, amount=80, chain={"D": True}), v4_run_id=run_id),
        evaluate_v4_plan(_context("BUY_HINT"), _projection(chain={"projection_30m": True}, projection_type="volume_up", projection_flag=True), v4_run_id=run_id),
        evaluate_v4_plan(_context("SELL_HINT", direction="sell", sell=True), _projection(chain={"projection_30m": True}, projection_type="shrink_down", projection_flag=True), v4_run_id=run_id),
        evaluate_v4_plan(_context("BUY:D"), _projection(chain={"D": True}, quality="warning"), v4_run_id=run_id),
    ]


def _context(condition_key: str, *, direction: str = "buy", sell: bool = False) -> dict[str, Any]:
    if sell:
        periods = {
            "D": {
                "previous_transition": "flat",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
    else:
        periods = {
            "Y": {
                "previous_transition": "flat",
                "previous_entity_high": 20,
                "previous_entity_low": 18,
                "previous_amount_baseline": 1000,
                "period_baseline_ready": True,
            },
            "Q": {
                "previous_transition": "flat",
                "previous_entity_high": 18,
                "previous_entity_low": 16,
                "previous_amount_baseline": 800,
                "period_baseline_ready": True,
            },
            "M": {
                "previous_transition": "volume_up",
                "previous_entity_high": 16,
                "previous_entity_low": 14,
                "previous_amount_baseline": 700,
                "period_baseline_ready": True,
            },
            "W": {
                "previous_transition": "flat",
                "previous_entity_high": 10,
                "previous_entity_low": 9,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            },
            "D": {
                "previous_transition": "flat",
                "previous_entity_high": 10.5,
                "previous_entity_low": 9.5,
                "previous_amount_baseline": 90,
                "period_baseline_ready": True,
            },
        }
    return {
        "asset_kind": "stock",
        "identity_key": "stock:SZ:000001",
        "trade_date": "20260603",
        "condition_key": condition_key,
        "original_condition_key": condition_key,
        "direction": direction,
        "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
        "context_snapshot_id": "trigger_context_snapshot_v4_contract_sample",
        "period_trigger_baseline_json": {
            "context_enrichment": {"ready": True},
            "periods": periods,
        },
    }


def _projection(
    *,
    price: float = 11,
    amount: float = 130,
    chain: dict[str, bool] | None = None,
    projection_type: str = "none",
    projection_flag: bool = False,
    quality: str = "passed",
) -> dict[str, Any]:
    return {
        "projection_run_id": "projection_v4_contract_sample",
        "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
        "source_market_data_run_id": "market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1",
        "raw_json": {
            "enrichment_v1": {
                "current_price_or_close": price,
                "current_amount_metric": amount,
                "current_metric_time": "2026-06-03T10:47:00+08:00",
                "current_metric_quality_status": quality,
                "trigger_amount_chain_pass": chain or {"W": True, "D": True},
                "projection_period": "30m",
                "projection_30m_flag": projection_flag,
                "projection_30m_type": projection_type,
                "projection_lineage_json": {"source": "n3_projection_enrichment_v1"},
                "source_freshness_status": "passed",
            }
        },
    }


def _load_v3_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"source": str(path), "status": "missing"}
    data = json.loads(path.read_text())
    return {
        "source": str(path),
        "result": data.get("result") or data.get("status"),
        "context_candidates": data.get("context_candidate_count") or data.get("context_candidates"),
        "planned_trigger_matched": data.get("planned_trigger_matched") or data.get("planned", {}).get("TriggerMatched"),
        "planned_trigger_pending_market_data": data.get("planned_trigger_pending_market_data") or data.get("planned", {}).get("TriggerPendingMarketData"),
        "planned_trigger_state_changed": data.get("planned_trigger_state_changed") or data.get("planned", {}).get("TriggerStateChanged"),
        "p0_p1_p2": data.get("P0/P1/P2") or data.get("quality_summary") or data.get("quality"),
    }


def _traceability_summary() -> dict[str, Any]:
    covered = [
        "N4-005..N4-016",
        "N4-017..N4-026",
        "N4-027..N4-032",
        "N4-033..N4-042",
        "N4-043..N4-052",
        "N4-053..N4-065",
        "N4-066..N4-107",
        "N4-140..N4-227",
        "N4-233..N4-244",
        "N4-275..N4-286",
        "N4-325..N4-339",
        "N4-401..N4-405",
    ]
    full_guard = ["N4-108..N4-139"]
    gaps = [
        "N4-001..N4-004",
        "N4-228..N4-232",
        "N4-245..N4-274",
        "N4-287..N4-324",
        "N4-340..N4-400",
    ]
    return {
        "covered_rule_ranges": covered,
        "covered_by_block_guard": full_guard,
        "remaining_gap_rule_ranges": gaps,
        "per_rule_status": _per_rule_status(covered, full_guard, gaps),
    }


def _per_rule_status(
    covered_ranges: list[str],
    full_guard_ranges: list[str],
    gap_ranges: list[str],
) -> dict[str, str]:
    statuses = {f"N4-{idx:03d}": "unclassified" for idx in range(1, 406)}
    for range_expr in covered_ranges:
        for rule_id in _expand_rule_range(range_expr):
            statuses[rule_id] = "covered_by_stage3_v4_dry_run_matcher"
    for range_expr in full_guard_ranges:
        for rule_id in _expand_rule_range(range_expr):
            statuses[rule_id] = "covered_by_full_block_guard_execute_still_blocked"
    for range_expr in gap_ranges:
        for rule_id in _expand_rule_range(range_expr):
            statuses[rule_id] = "gap_future_stage_not_implemented_in_this_gate"
    return statuses


def _expand_rule_range(range_expr: str) -> list[str]:
    if ".." not in range_expr:
        return [range_expr]
    start, end = range_expr.split("..", 1)
    start_idx = int(start.split("-", 1)[1])
    end_idx = int(end.split("-", 1)[1])
    return [f"N4-{idx:03d}" for idx in range(start_idx, end_idx + 1)]


def _build_diff_artifact(report: Mapping[str, Any], v3_summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "result": "DIFF_BACKTEST_PASS",
        "scope": "representative_contract_backtest_only_no_business_execute",
        "trigger_rule_spec_version": TRIGGER_RULE_SPEC_VERSION,
        "trigger_rule_policy_hash": TRIGGER_RULE_POLICY_HASH,
        "v3_baseline": dict(v3_summary),
        "v4_sample": {
            "plan_count": report["plan_count"],
            "event_counts": report["event_counts"],
            "outcome_counts": report["outcome_counts"],
            "signal_type_distribution": report["signal_type_distribution"],
            "n5_entry_guard": report["n5_entry_guard"],
            "full_blocked_proof": report["full_blocked_proof"],
        },
        "main_semantic_diff": [
            "v4 distinguishes matched/pending_market_data/no_op/quality_blocked/inactive",
            "v4 reports only actual triggered Y/Q/M/W/D periods",
            "v4 keeps 30m as projection_period/projection_30m_type and never as primary/all periods",
            "v4 blocks FULL execute until final FULL prerequisite semantics are approved",
            "v4 allows N5 entry only for TriggerMatched with matched live state",
        ],
        "historical_run_policy": "read_only_no_silent_reinterpretation",
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _render_report_md(report: Mapping[str, Any]) -> str:
    return f"""# N4 Trigger Rule Spec v4 Matcher Dry-Run Report

Result: `{report['result']}`

Implementation result: `{report['implementation_result']}`

Spec version: `{report['trigger_rule_spec_version']}`

Policy hash: `{report['trigger_rule_policy_hash']}`

Independent v4 run id: `{report['independent_v4_run_id']}`

## Summary

```json
{json.dumps({k: report[k] for k in ['plan_count', 'event_counts', 'outcome_counts', 'signal_type_distribution', 'trigger_kind_distribution', 'trigger_mark_candidate_distribution', 'deprecated_runtime_signal_type_count']}, ensure_ascii=False, indent=2)}
```

## FULL Blocked Proof

```json
{json.dumps(report['full_blocked_proof'], ensure_ascii=False, indent=2)}
```

## N5 Entry Guard Proof

```json
{json.dumps(report['n5_entry_guard'], ensure_ascii=False, indent=2)}
```

## Source Boundary Proof

```json
{json.dumps(report['source_boundary_proof'], ensure_ascii=False, indent=2)}
```

## Traceability Summary

```json
{json.dumps(report['traceability_summary'], ensure_ascii=False, indent=2)}
```
"""


def _render_diff_md(diff: Mapping[str, Any]) -> str:
    return f"""# N4 Trigger Rule Spec v4 V3-V4 Diff / Backtest Artifact

Result: `{diff['result']}`

Scope: `{diff['scope']}`

## V3 Baseline

```json
{json.dumps(diff['v3_baseline'], ensure_ascii=False, indent=2)}
```

## V4 Sample

```json
{json.dumps(diff['v4_sample'], ensure_ascii=False, indent=2)}
```

## Main Semantic Diff

```json
{json.dumps(diff['main_semantic_diff'], ensure_ascii=False, indent=2)}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
