#!/usr/bin/env python3
"""Run-once N4 trigger rule spec v4 execute runner.

Default invocation is intentionally blocked unless both --execute and
--user-confirmed are provided. The runner recomputes the approved v4 full-lineage
plan from standard N2/N3 enrichment inputs before writing matched-only N4 facts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.trigger.local_trigger_dry_run import fetch_context_rows, fetch_snapshot_rows
from ashare_v3.trigger.rule_v4_execute import (
    V4TriggerExecuteBlocked,
    assert_v4_execute_confirmed,
    build_v4_execute_write_plan,
    build_v4_quality_items,
    execute_v4_matched_only_transaction,
)
from ashare_v3.trigger.synthetic_dry_run import write_json
from check_condition_source_ready import DEFAULT_DSN
from plan_n4_trigger_rule_v4_full_lineage_dry_run import (
    DEFAULT_CONTEXT_RUN_ID,
    DEFAULT_DIFF_JSON,
    DEFAULT_N2_CONTEXT_ENRICHMENT_REPORT,
    DEFAULT_N2_CONTEXT_MATERIALIZATION_RUN_ID,
    DEFAULT_N3_PROJECTION_ENRICHMENT_REPORT,
    DEFAULT_N3_PROJECTION_RUN_ID,
    DEFAULT_SNAPSHOT_RUN_ID,
    run_full_lineage_dry_run,
)


DEFAULT_EXECUTE_RUN_ID = "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1"
DEFAULT_CONTRACT_PATH = "docs/N4_TRIGGER_RULE_SPEC_v4_execute_contract_draft.json"
DEFAULT_PREFLIGHT_PATH = "docs/N4_TRIGGER_RULE_SPEC_v4_execute_preflight_draft.json"
DEFAULT_DRY_RUN_REPORT_PATH = "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N4_TRIGGER_RULE_SPEC_v4_execute_rollback_draft.sql"
DEFAULT_EXECUTE_REPORT_PATH = "docs/N4_TRIGGER_RULE_SPEC_v4_execute_report.json"


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        assert_v4_execute_confirmed(execute=args.execute, user_confirmed=args.user_confirmed)
        report = run_execute(args)
    except V4TriggerExecuteBlocked as exc:
        report = {
            "result": "BLOCKED",
            "layer_role": "N4_trigger",
            "execute_run_id": args.execute_run_id,
            "writes_performed": False,
            "blocked_reason": str(exc),
            "boundary_proof": {
                "db_write": False,
                "outbox_consumed": False,
                "inbox_checkpoint_written": False,
                "n5_n6_entered": False,
                "worker_started": False,
            },
        }
        if args.report_json_path:
            write_json(Path(args.report_json_path), report)
        print_report(report, as_json=args.json)
        return 2

    if args.report_json_path:
        write_json(Path(args.report_json_path), report)
    print_report(report, as_json=args.json)
    return 0 if report.get("result") == "EXECUTE_PASS" else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="N4 trigger rule spec v4 matched-only execute runner.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_EXECUTE_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_CONTEXT_RUN_ID)
    parser.add_argument("--snapshot-run-id", default=DEFAULT_SNAPSHOT_RUN_ID)
    parser.add_argument("--condition-context-materialization-run-id", default=DEFAULT_N2_CONTEXT_MATERIALIZATION_RUN_ID)
    parser.add_argument("--projection-run-id", default=DEFAULT_N3_PROJECTION_RUN_ID)
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--readiness-path", "--preflight-path", dest="readiness_path", default=DEFAULT_PREFLIGHT_PATH)
    parser.add_argument(
        "--dry-run-report-path",
        "--dry-run-json-path",
        dest="dry_run_report_path",
        default=DEFAULT_DRY_RUN_REPORT_PATH,
    )
    parser.add_argument("--diff-json-path", default=DEFAULT_DIFF_JSON)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--report-json-path", default=None)
    parser.add_argument("--n2-context-enrichment-report-path", default=DEFAULT_N2_CONTEXT_ENRICHMENT_REPORT)
    parser.add_argument("--n3-projection-enrichment-report-path", default=DEFAULT_N3_PROJECTION_ENRICHMENT_REPORT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def run_execute(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_json(args.contract_path)
    preflight = load_json(args.readiness_path)
    assert_artifacts_ready(contract=contract, preflight=preflight, args=args)

    dry_run_report, _diff = run_full_lineage_dry_run(
        dsn=args.dsn,
        trigger_context_run_id=args.trigger_context_run_id,
        snapshot_run_id=args.snapshot_run_id,
        condition_context_materialization_run_id=args.condition_context_materialization_run_id,
        projection_run_id=args.projection_run_id,
        sample_limit=100000,
        n2_context_enrichment_report_path=args.n2_context_enrichment_report_path,
        n3_projection_enrichment_report_path=args.n3_projection_enrichment_report_path,
    )
    plans = list(dry_run_report.get("sample_v4_plans") or [])
    write_plan = build_v4_execute_write_plan(
        plans,
        execute_run_id=args.execute_run_id,
        trigger_context_run_id=args.trigger_context_run_id,
        snapshot_run_id=args.snapshot_run_id,
    )
    assert_write_plan_matches_contract(write_plan=write_plan, contract=contract, preflight=preflight)
    quality_items = build_v4_quality_items(write_plan)
    if any(item.get("severity") == "P0" and item.get("status") == "failed" for item in quality_items):
        raise V4TriggerExecuteBlocked("N4 v4 execute blocked by quality items before writes")

    trigger_context_run, _context_rows = fetch_context_rows(args.dsn, args.trigger_context_run_id)
    snapshot_run, _snapshot_rows = fetch_snapshot_rows(args.dsn, args.snapshot_run_id)
    write_counts = execute_v4_matched_only_transaction(
        dsn=args.dsn,
        execute_run_id=args.execute_run_id,
        trigger_context_run=trigger_context_run,
        snapshot_run=snapshot_run,
        write_plan=write_plan,
        quality_items=quality_items,
    )
    return {
        "result": "EXECUTE_PASS",
        "layer_role": "N4_trigger",
        "execute_run_id": args.execute_run_id,
        "trigger_context_run_id": args.trigger_context_run_id,
        "snapshot_run_id": args.snapshot_run_id,
        "write_counts": write_counts,
        "outcome_persistence_strategy": write_plan["outcome_persistence_strategy"],
        "suppressed_counts": write_plan["suppressed_counts"],
        "invalid_n5_entry_count": write_plan["invalid_n5_entry_count"],
        "full_blocked_count": write_plan["full_blocked_count"],
        "bj_quality_blocked_count": write_plan["bj_quality_blocked_count"],
        "rollback_sql_path": args.rollback_sql_path,
        "boundary_proof": {
            "n3_outbox_consumed": False,
            "inbox_checkpoint_written": False,
            "n5_n6_entered": False,
            "worker_started": False,
            "market_data_pulled": False,
            "real_trade_touched": False,
        },
    }


def assert_artifacts_ready(*, contract: dict[str, Any], preflight: dict[str, Any], args: argparse.Namespace) -> None:
    blockers: list[str] = []
    if contract.get("result") != "CONTRACT_PASS":
        blockers.append(f"contract result={contract.get('result')}")
    if preflight.get("result") != "PREFLIGHT_PASS":
        blockers.append(f"preflight result={preflight.get('result')}")
    if contract.get("execute_run_id") != args.execute_run_id:
        blockers.append("contract execute_run_id mismatch")
    if preflight.get("execute_run_id") != args.execute_run_id:
        blockers.append("preflight execute_run_id mismatch")
    if contract.get("trigger_context_run_id") != args.trigger_context_run_id:
        blockers.append("contract trigger_context_run_id mismatch")
    if contract.get("snapshot_run_id") != args.snapshot_run_id:
        blockers.append("contract snapshot_run_id mismatch")
    if int((preflight.get("quality") or {}).get("p0_count") or 0) != 0:
        blockers.append("preflight P0 is not zero")
    if not (preflight.get("runner_readiness") or {}).get("ready"):
        blockers.append("runner_readiness.ready is not true")
    if blockers:
        raise V4TriggerExecuteBlocked("N4 v4 execute blocked by artifacts: " + "; ".join(blockers))


def assert_write_plan_matches_contract(
    *,
    write_plan: dict[str, Any],
    contract: dict[str, Any],
    preflight: dict[str, Any],
) -> None:
    expected = contract.get("expected_writes") or preflight.get("expected_future_writes") or {}
    actual = write_plan["write_counts"]
    blockers = []
    if int(actual.get("TriggerMatched") or 0) != int(expected.get("TriggerMatched") or 0):
        blockers.append("TriggerMatched expected write count mismatch")
    if int(actual.get("TriggerPendingMarketData") or 0) != int(expected.get("TriggerPendingMarketData") or 0):
        blockers.append("TriggerPendingMarketData expected write count mismatch")
    if int(actual.get("TriggerStateChanged") or 0) != int(expected.get("TriggerStateChanged") or 0):
        blockers.append("TriggerStateChanged expected write count mismatch")
    if int(write_plan.get("invalid_n5_entry_count") or 0) != 0:
        blockers.append("invalid N5 entry count is not zero")
    if blockers:
        raise V4TriggerExecuteBlocked("N4 v4 execute blocked by write-plan mismatch: " + "; ".join(blockers))


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def print_report(report: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    print(
        "\n".join(
            [
                "N4 trigger rule spec v4 execute runner",
                f"  result={report.get('result')}",
                f"  execute_run_id={report.get('execute_run_id')}",
                f"  write_counts={report.get('write_counts')}",
                f"  blocked_reason={report.get('blocked_reason')}",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
