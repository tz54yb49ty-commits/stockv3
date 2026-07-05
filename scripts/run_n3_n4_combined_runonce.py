#!/usr/bin/env python3
"""Plan a bounded N3/N4 combined run-once without implementing business logic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ORDINARY_PREVIOUS_RUN_REQUIRES = (
    "trigger_provisional_ordinary_",
    "__realtime_action_confirmation_metric_",
    "__asset_all__",
    "current_period_avg_v1",
    "__atomic_rule_v1_period_rollover_guard_v1",
)

HINT_PREVIOUS_RUN_REQUIRES = (
    "trigger_provisional_b2_",
    "__realtime_hint_projection_metric_",
    "__asset_index_board__",
    "__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1",
)

HINT_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"

FORBIDDEN_COMMAND_TOKENS = (
    " n5",
    " n6",
    "outbox_consume",
    "consume_outbox",
    "checkpoint_update",
    "worker",
    "launchctl",
    "bootstrap",
    "bootout",
)


class CombinedRunonceBlocked(RuntimeError):
    """Raised when the combined run-once orchestrator must stop before child execution."""


def build_combined_runonce_plan(
    *,
    for_trade_date: str,
    ordinary_previous_trigger_run_id: str,
    hint_previous_trigger_run_id: str,
    n4_context_run_id: str,
    subscription_run_id: str,
    execute: bool = False,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    _validate_trade_date(for_trade_date)
    _validate_required("ordinary_previous_trigger_run_id", ordinary_previous_trigger_run_id)
    _validate_required("hint_previous_trigger_run_id", hint_previous_trigger_run_id)
    _validate_required("n4_context_run_id", n4_context_run_id)
    _validate_required("subscription_run_id", subscription_run_id)
    _validate_ordinary_previous_run_id(ordinary_previous_trigger_run_id)
    _validate_hint_previous_run_id(hint_previous_trigger_run_id)
    _validate_context_and_subscription(for_trade_date, n4_context_run_id, subscription_run_id)
    if execute and not user_confirmed:
        raise CombinedRunonceBlocked("combined run-once execute blocked: missing --user-confirmed")

    child_steps = _build_child_steps(
        for_trade_date=for_trade_date,
        ordinary_previous_trigger_run_id=ordinary_previous_trigger_run_id,
        hint_previous_trigger_run_id=hint_previous_trigger_run_id,
        n4_context_run_id=n4_context_run_id,
        subscription_run_id=subscription_run_id,
    )
    _assert_no_forbidden_commands(child_steps)
    child_runner_audit = _build_child_runner_audit(child_steps)
    missing_runners = [item for item in child_runner_audit if item["status"] == "missing_child_runner"]
    if execute and missing_runners:
        missing_ids = ", ".join(item["step_id"] for item in missing_runners)
        raise CombinedRunonceBlocked(f"combined run-once execute blocked: missing child runners: {missing_ids}")

    return {
        "result": "PLAN_ONLY_PASS" if not execute else "EXECUTE_BLOCKED_UNTIL_CHILD_RUNNERS_READY",
        "mode": "plan_only" if not execute else "execute_requested",
        "for_trade_date": for_trade_date,
        "terminal_step": "combined_closeout",
        "baseline_policy": {
            "ordinary_previous_trigger_run_id": ordinary_previous_trigger_run_id,
            "hint_previous_trigger_run_id": hint_previous_trigger_run_id,
            "source_selection": "exact_run_id_only",
            "wildcard_selection_allowed": False,
        },
        "orchestrator_contract": {
            "layer_role": "runtime_control",
            "implements_business_logic": False,
            "writes_business_tables": False,
            "consumes_outbox": False,
            "updates_inbox_or_checkpoint": False,
            "starts_worker": False,
            "executes_rollback": False,
            "schema_change": False,
        },
        "n5_freeze_policy": {
            "n5_frozen": True,
            "n5_preflight_allowed": False,
            "n5_execute_allowed": False,
            "n4_outbox_policy": "pending_only_no_consume",
        },
        "target_absence_required_before_each_execute": True,
        "child_steps": child_steps,
        "child_runner_audit": child_runner_audit,
        "missing_child_runner_count": len(missing_runners),
        "report_contract": {
            "local_report_only": True,
            "expected_fields": [
                "child_step_list",
                "actual_proof_minutes",
                "generated_target_run_ids",
                "baseline_run_ids",
                "rollback_artifact_paths",
                "outbox_counts",
                "n5_freeze_proof",
                "forbidden_side_effect_proof",
            ],
        },
    }


def _build_child_steps(
    *,
    for_trade_date: str,
    ordinary_previous_trigger_run_id: str,
    hint_previous_trigger_run_id: str,
    n4_context_run_id: str,
    subscription_run_id: str,
) -> list[dict[str, Any]]:
    ordinary_hhmm = "<ordinary_hhmm>"
    hint_hhmm = "<hint_hhmm>"
    source_condition_run_id = _source_condition_run_id(subscription_run_id)
    n3p_source_run_id = f"n3p_mixed_realtime_source_payload_{for_trade_date}_until_{ordinary_hhmm}_v1"
    n3p_metric_run_id = (
        f"realtime_action_confirmation_metric_{for_trade_date}_until_{ordinary_hhmm}"
        f"__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__"
        f"{subscription_run_id}"
    )
    n3_hint_run_id = (
        f"realtime_hint_projection_metric_{for_trade_date}_until_{hint_hhmm}"
        f"__asset_index_board__{HINT_PROOF_KIND}__{subscription_run_id}"
    )
    n4_ordinary_run_id = (
        f"trigger_provisional_ordinary_{for_trade_date}_until_{ordinary_hhmm}__"
        f"{n3p_metric_run_id}__atomic_rule_v1_period_rollover_guard_v1"
    )
    n4_hint_run_id = f"trigger_provisional_b2_{for_trade_date}_until_{hint_hhmm}__{n3_hint_run_id}__atomic_rule_v1"

    return [
        _step(
            "n3p_current_source_fetch",
            "N3_market_data",
            runner_path="scripts/run_n3p_current_source_fetch_once.py",
            argv=_n3_child_contract_argv(
                runner_path="scripts/run_n3p_current_source_fetch_once.py",
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                subscription_run_id=subscription_run_id,
                source_condition_run_id=source_condition_run_id,
                target_run_id=n3p_source_run_id,
                json_report_path=f"tmp/N3P_{for_trade_date}_{ordinary_hhmm}_source_fetch_report.json",
                execute=True,
            ),
            target_run_id=n3p_source_run_id,
            notes=["bounded N3_market_data wrapper; runtime_control only plans argv"],
        ),
        _step(
            "n3p_trigger_proof_preflight",
            "N3_market_data",
            runner_path="scripts/run_n3p_trigger_proof_preflight_once.py",
            argv=_n3_child_contract_argv(
                runner_path="scripts/run_n3p_trigger_proof_preflight_once.py",
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                subscription_run_id=subscription_run_id,
                source_condition_run_id=source_condition_run_id,
                source_run_id=n3p_source_run_id,
                target_run_id=n3p_metric_run_id,
                contract_path=f"tmp/N3P_{for_trade_date}_{ordinary_hhmm}_trigger_proof_contract.json",
                preflight_path=f"tmp/N3P_{for_trade_date}_{ordinary_hhmm}_trigger_proof_preflight.json",
                source_payload_path=f"docs/intraday_live_current/{for_trade_date}/N3P_mixed_realtime_{ordinary_hhmm}_source_fetch_payload.json",
                json_report_path=f"tmp/N3P_{for_trade_date}_{ordinary_hhmm}_trigger_proof_preflight_report.json",
                execute=False,
            ),
            source_run_id=n3p_source_run_id,
            target_run_id=n3p_metric_run_id,
            notes=["bounded N3_market_data wrapper; runtime_control only plans argv"],
        ),
        _step(
            "n3p_trigger_proof_execute",
            "N3_market_data",
            runner_path="scripts/run_v3_realtime_virtual_metric_writer_once.py",
            argv=[
                "python3",
                "scripts/run_v3_realtime_virtual_metric_writer_once.py",
                "--contract-path",
                f"tmp/N3P_{for_trade_date}_{ordinary_hhmm}_trigger_proof_contract.json",
                "--source-payload-path",
                f"docs/intraday_live_current/{for_trade_date}/N3P_mixed_realtime_{ordinary_hhmm}_source_fetch_payload.json",
                "--output-path",
                f"tmp/N3P_{for_trade_date}_{ordinary_hhmm}_trigger_proof_execute_report.json",
                "--execute",
                "--user-confirmed",
            ],
            source_run_id=n3p_source_run_id,
            target_run_id=n3p_metric_run_id,
            rollback_sql_path=f"sql/N3P_{for_trade_date}_{ordinary_hhmm}_trigger_proof_rollback.sql",
        ),
        _step(
            "n3_hint_source_fetch",
            "N3_market_data",
            runner_path="scripts/run_n3_hint_index_board_1m_source_fetch_once.py",
            argv=_n3_child_contract_argv(
                runner_path="scripts/run_n3_hint_index_board_1m_source_fetch_once.py",
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                subscription_run_id=subscription_run_id,
                source_condition_run_id=source_condition_run_id,
                target_run_id=f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{hint_hhmm}_v1",
                hint_proof_kind=HINT_PROOF_KIND,
                json_report_path=f"docs/intraday_live_current/{for_trade_date}/N3_hint_index_board_1m_{hint_hhmm}_midday_bridge_frequency8_fetch_report.json",
                execute=True,
            ),
            target_run_id=f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{hint_hhmm}_v1",
            notes=["bounded N3_market_data wrapper; runtime_control only plans argv"],
        ),
        _step(
            "n3_hint_proof_preflight",
            "N3_market_data",
            runner_path="scripts/run_n3_hint_index_board_1m_proof_preflight_once.py",
            argv=_n3_child_contract_argv(
                runner_path="scripts/run_n3_hint_index_board_1m_proof_preflight_once.py",
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                subscription_run_id=subscription_run_id,
                source_condition_run_id=source_condition_run_id,
                source_run_id=f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{hint_hhmm}_v1",
                target_run_id=n3_hint_run_id,
                source_artifact_path=f"docs/intraday_live_current/{for_trade_date}/N3_hint_index_board_1m_{hint_hhmm}_midday_bridge_frequency8_payload.json",
                hint_proof_kind=HINT_PROOF_KIND,
                json_report_path=f"tmp/N3_hint_index_board_1m_{for_trade_date}_{hint_hhmm}_midday_bridge_v1_preflight_report.json",
                execute=False,
            ),
            source_run_id=f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{hint_hhmm}_v1",
            target_run_id=n3_hint_run_id,
            notes=["bounded N3_market_data wrapper; runtime_control only plans argv"],
        ),
        _step(
            "n3_hint_proof_execute",
            "N3_market_data",
            runner_path="scripts/run_n3_hint_index_board_1m_proof_execute_once.py",
            argv=_n3_child_contract_argv(
                runner_path="scripts/run_n3_hint_index_board_1m_proof_execute_once.py",
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                subscription_run_id=subscription_run_id,
                source_condition_run_id=source_condition_run_id,
                source_run_id=f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{hint_hhmm}_v1",
                target_run_id=n3_hint_run_id,
                source_artifact_path=f"docs/intraday_live_current/{for_trade_date}/N3_hint_index_board_1m_{hint_hhmm}_midday_bridge_frequency8_payload.json",
                hint_proof_kind=HINT_PROOF_KIND,
                json_report_path=f"tmp/N3_hint_index_board_1m_{for_trade_date}_{hint_hhmm}_midday_bridge_v1_execute_report.json",
                execute=True,
            ),
            source_run_id=f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{hint_hhmm}_v1",
            target_run_id=n3_hint_run_id,
            rollback_sql_path=f"sql/N3_hint_index_board_1m_{for_trade_date}_{hint_hhmm}_rollback.sql",
            notes=["bounded N3_market_data wrapper; runtime_control only plans argv"],
        ),
        _step(
            "n4_ordinary_matcher_preflight",
            "N4_trigger",
            runner_path="scripts/run_n4_provisional_ordinary_execute_once.py",
            argv=_n4_ordinary_argv(
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                source_condition_run_id=source_condition_run_id,
                n3p_metric_run_id=n3p_metric_run_id,
                n4_ordinary_run_id=n4_ordinary_run_id,
                execute=False,
            ),
            source_run_id=n3p_metric_run_id,
            target_run_id=n4_ordinary_run_id,
            previous_baseline_run_id=ordinary_previous_trigger_run_id,
        ),
        _step(
            "n4_ordinary_matcher_execute",
            "N4_trigger",
            runner_path="scripts/run_n4_provisional_ordinary_execute_once.py",
            argv=_n4_ordinary_argv(
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                source_condition_run_id=source_condition_run_id,
                n3p_metric_run_id=n3p_metric_run_id,
                n4_ordinary_run_id=n4_ordinary_run_id,
                execute=True,
            ),
            source_run_id=n3p_metric_run_id,
            target_run_id=n4_ordinary_run_id,
            previous_baseline_run_id=ordinary_previous_trigger_run_id,
            rollback_sql_path=f"sql/N4_{for_trade_date}_{ordinary_hhmm}_ordinary_period_rollover_guard_v1_rollback.sql",
        ),
        _step(
            "n4_hint_matcher_preflight",
            "N4_trigger",
            runner_path="scripts/run_n4_provisional_projection_execute_once.py",
            argv=_n4_hint_argv(
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                source_condition_run_id=source_condition_run_id,
                n3_hint_run_id=n3_hint_run_id,
                n4_hint_run_id=n4_hint_run_id,
                execute=False,
            ),
            source_run_id=n3_hint_run_id,
            target_run_id=n4_hint_run_id,
            previous_baseline_run_id=hint_previous_trigger_run_id,
        ),
        _step(
            "n4_hint_matcher_execute",
            "N4_trigger",
            runner_path="scripts/run_n4_provisional_projection_execute_once.py",
            argv=_n4_hint_argv(
                for_trade_date=for_trade_date,
                n4_context_run_id=n4_context_run_id,
                source_condition_run_id=source_condition_run_id,
                n3_hint_run_id=n3_hint_run_id,
                n4_hint_run_id=n4_hint_run_id,
                execute=True,
            ),
            source_run_id=n3_hint_run_id,
            target_run_id=n4_hint_run_id,
            previous_baseline_run_id=hint_previous_trigger_run_id,
            rollback_sql_path=f"sql/N4_{for_trade_date}_{hint_hhmm}_hint_v2_rollback.sql",
        ),
        _step(
            "combined_closeout",
            "runtime_control",
            runner_path="internal:combined_closeout",
            notes=["read-only closeout: verify passed targets, pending outbox only, rollback SQL, N5 freeze, no worker"],
        ),
    ]


def _step(
    step_id: str,
    layer_role: str,
    *,
    runner_path: str | None,
    argv: list[str] | None = None,
    source_run_id: str | None = None,
    target_run_id: str | None = None,
    previous_baseline_run_id: str | None = None,
    rollback_sql_path: str | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    target_absence_check_required = bool(target_run_id and argv and "--execute" in argv)
    return {
        "step_id": step_id,
        "layer_role": layer_role,
        "runner_path": runner_path,
        "argv": argv or [],
        "source_run_id": source_run_id,
        "target_run_id": target_run_id,
        "previous_baseline_run_id": previous_baseline_run_id,
        "rollback_sql_path": rollback_sql_path,
        "target_absence_check_required": target_absence_check_required,
        "notes": notes or [],
    }


def _n3_child_contract_argv(
    *,
    runner_path: str,
    for_trade_date: str,
    n4_context_run_id: str,
    subscription_run_id: str,
    source_condition_run_id: str,
    target_run_id: str,
    json_report_path: str,
    source_run_id: str = "",
    source_payload_path: str = "",
    source_artifact_path: str = "",
    contract_path: str = "",
    preflight_path: str = "",
    hint_proof_kind: str = "",
    execute: bool,
) -> list[str]:
    argv = [
        "python3",
        runner_path,
        "--for-trade-date",
        for_trade_date,
        "--n4-context-run-id",
        n4_context_run_id,
        "--subscription-run-id",
        subscription_run_id,
        "--source-condition-run-id",
        source_condition_run_id,
        "--target-run-id",
        target_run_id,
        "--json-report-path",
        json_report_path,
    ]
    optional_pairs = [
        ("--source-run-id", source_run_id),
        ("--source-payload-path", source_payload_path),
        ("--source-artifact-path", source_artifact_path),
        ("--contract-path", contract_path),
        ("--preflight-path", preflight_path),
        ("--hint-proof-kind", hint_proof_kind),
    ]
    for flag, value in optional_pairs:
        if value:
            argv.extend([flag, value])
    if execute:
        argv.extend(["--execute", "--user-confirmed"])
    return argv


def _n4_ordinary_argv(
    *,
    for_trade_date: str,
    n4_context_run_id: str,
    source_condition_run_id: str,
    n3p_metric_run_id: str,
    n4_ordinary_run_id: str,
    execute: bool,
) -> list[str]:
    argv = [
        "python3",
        "scripts/run_n4_provisional_ordinary_execute_once.py",
        "--trigger-context-run-id",
        n4_context_run_id,
        "--source-metric-run-id",
        n3p_metric_run_id,
        "--trigger-run-id",
        n4_ordinary_run_id,
        "--for-trade-date",
        for_trade_date,
        "--source-condition-run-id",
        source_condition_run_id,
        "--json-report-path",
        f"tmp/N4_{for_trade_date}_<ordinary_hhmm>_ordinary_period_rollover_guard_v1_execute_report.json",
        "--rollback-sql-path",
        f"sql/N4_{for_trade_date}_<ordinary_hhmm>_ordinary_period_rollover_guard_v1_rollback.sql",
    ]
    if execute:
        argv.extend(["--execute", "--user-confirmed"])
    return argv


def _n4_hint_argv(
    *,
    for_trade_date: str,
    n4_context_run_id: str,
    source_condition_run_id: str,
    n3_hint_run_id: str,
    n4_hint_run_id: str,
    execute: bool,
) -> list[str]:
    argv = [
        "python3",
        "scripts/run_n4_provisional_projection_execute_once.py",
        "--trigger-context-run-id",
        n4_context_run_id,
        "--projection-run-id",
        n4_hint_run_id,
        "--source-projection-run-id",
        n3_hint_run_id,
        "--trigger-run-id",
        n4_hint_run_id,
        "--for-trade-date",
        for_trade_date,
        "--source-condition-run-id",
        source_condition_run_id,
        "--json-report-path",
        f"tmp/N4_{for_trade_date}_<hint_hhmm>_hint_v2_execute_report.json",
        "--rollback-sql-path",
        f"sql/N4_{for_trade_date}_<hint_hhmm>_hint_v2_rollback.sql",
    ]
    if execute:
        argv.extend(["--execute", "--user-confirmed"])
    return argv


def _build_child_runner_audit(child_steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    audit: list[dict[str, str]] = []
    for step in child_steps:
        runner_path = step.get("runner_path")
        if isinstance(runner_path, str) and runner_path.startswith("internal:"):
            status = "available_internal"
        elif not runner_path:
            status = "missing_child_runner"
        elif Path(str(runner_path)).exists():
            status = "available"
        else:
            status = "missing_child_runner"
        audit.append({"step_id": str(step["step_id"]), "runner_path": str(runner_path or ""), "status": status})
    return audit


def _assert_no_forbidden_commands(child_steps: list[dict[str, Any]]) -> None:
    command_blob = "\n".join(" ".join(str(part) for part in step.get("argv", [])) for step in child_steps).lower()
    for token in FORBIDDEN_COMMAND_TOKENS:
        if token in command_blob:
            raise CombinedRunonceBlocked(f"forbidden child command token detected: {token.strip()}")


def _validate_trade_date(value: str) -> None:
    if not (str(value).isdigit() and len(str(value)) == 8):
        raise CombinedRunonceBlocked("for_trade_date must be YYYYMMDD")


def _validate_required(name: str, value: str) -> None:
    if not str(value or "").strip():
        raise CombinedRunonceBlocked(f"{name} is required")


def _validate_ordinary_previous_run_id(run_id: str) -> None:
    for required in ORDINARY_PREVIOUS_RUN_REQUIRES:
        if required not in run_id:
            raise CombinedRunonceBlocked("ordinary previous baseline is not exact period_rollover_guard_v1 ordinary target")


def _validate_hint_previous_run_id(run_id: str) -> None:
    for required in HINT_PREVIOUS_RUN_REQUIRES:
        if required not in run_id:
            raise CombinedRunonceBlocked("HINT previous baseline must be exact corrected midday_bridge_v1 HINT target")


def _validate_context_and_subscription(for_trade_date: str, n4_context_run_id: str, subscription_run_id: str) -> None:
    if f"trigger_context_snapshot_{for_trade_date}_" not in n4_context_run_id:
        raise CombinedRunonceBlocked("n4_context_run_id trade_date mismatch")
    if f"market_data_subscription_{for_trade_date}_" not in subscription_run_id:
        raise CombinedRunonceBlocked("subscription_run_id trade_date mismatch")


def _source_condition_run_id(subscription_run_id: str) -> str:
    marker = "market_data_subscription_"
    if not subscription_run_id.startswith(marker):
        raise CombinedRunonceBlocked("invalid subscription_run_id")
    rest = subscription_run_id[len(marker) :]
    parts = rest.split("_", 1)
    if len(parts) != 2 or not parts[1].startswith("condition_layer_"):
        raise CombinedRunonceBlocked("subscription_run_id missing condition layer suffix")
    return parts[1]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a bounded N3/N4 combined run-once.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--ordinary-previous-trigger-run-id", required=True)
    parser.add_argument("--hint-previous-trigger-run-id", required=True)
    parser.add_argument("--n4-context-run-id", required=True)
    parser.add_argument("--subscription-run-id", required=True)
    parser.add_argument("--report-path")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        plan = build_combined_runonce_plan(
            for_trade_date=args.for_trade_date,
            ordinary_previous_trigger_run_id=args.ordinary_previous_trigger_run_id,
            hint_previous_trigger_run_id=args.hint_previous_trigger_run_id,
            n4_context_run_id=args.n4_context_run_id,
            subscription_run_id=args.subscription_run_id,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    except CombinedRunonceBlocked as exc:
        payload = {"result": "BLOCKED", "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    if args.report_path:
        Path(args.report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_path).write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
    else:
        print(f"result={plan['result']} terminal_step={plan['terminal_step']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
