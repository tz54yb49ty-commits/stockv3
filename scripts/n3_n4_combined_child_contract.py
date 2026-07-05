"""Thin child-runner contract helpers for N3/N4 combined run-once planning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


MIDDAY_BRIDGE_HINT_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"
DEFAULT_LAYER_RUNNER = object()
N3_READY_RESULT = "EXECUTE_READY_REAL_IO_CONTRACT"
MISSING_N3_REAL_RUNNER_RESULT = "BLOCKED_MISSING_N3_REAL_RUNNER"

LayerRunner = Callable[..., Mapping[str, Any] | None]
TargetAbsenceChecker = Callable[..., Mapping[str, Any] | None]


def build_child_arg_parser(*, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--n4-context-run-id", required=True)
    parser.add_argument("--subscription-run-id", required=True)
    parser.add_argument("--source-run-id", default="")
    parser.add_argument("--target-run-id", required=True)
    parser.add_argument("--source-condition-run-id", default="")
    parser.add_argument("--source-payload-path", default="")
    parser.add_argument("--source-artifact-path", default="")
    parser.add_argument("--contract-path", default="")
    parser.add_argument("--preflight-path", default="")
    parser.add_argument("--hint-proof-kind", default="")
    parser.add_argument("--json-report-path", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def run_child_contract(
    *,
    argv: Sequence[str] | None,
    step_id: str,
    layer_role: str,
    description: str,
    execute_contract_ready: bool = False,
    layer_runner: LayerRunner | None = None,
    layer_runner_name: str = "",
    audited_layer_capability: str = "",
    target_absence_checker: TargetAbsenceChecker | None = None,
    required_hint_proof_kind: str | None = None,
    output_contract: Mapping[str, Any] | None = None,
    run_layer_runner_in_plan_only: bool = False,
) -> int:
    parser = build_child_arg_parser(description=description)
    args = parser.parse_args(argv)
    report = build_child_contract_report(
        args=args,
        step_id=step_id,
        layer_role=layer_role,
        execute_contract_ready=execute_contract_ready or layer_runner is not None,
        layer_runner=layer_runner,
        layer_runner_name=layer_runner_name,
        audited_layer_capability=audited_layer_capability,
        target_absence_checker=target_absence_checker,
        required_hint_proof_kind=required_hint_proof_kind,
        output_contract=output_contract or {},
        run_layer_runner_in_plan_only=run_layer_runner_in_plan_only,
    )
    if args.json_report_path:
        path = Path(args.json_report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"result={report['result']} step_id={step_id}")
    return 2 if str(report["result"]).startswith("BLOCKED") else 0


def build_child_contract_report(
    *,
    args: argparse.Namespace,
    step_id: str,
    layer_role: str,
    execute_contract_ready: bool,
    layer_runner: LayerRunner | None,
    layer_runner_name: str,
    audited_layer_capability: str,
    target_absence_checker: TargetAbsenceChecker | None,
    required_hint_proof_kind: str | None,
    output_contract: Mapping[str, Any],
    run_layer_runner_in_plan_only: bool = False,
) -> dict[str, Any]:
    result = "PLAN_ONLY_PASS"
    reason = ""
    mode = "plan_only"
    hint_proof_kind = args.hint_proof_kind or (required_hint_proof_kind or "")
    if required_hint_proof_kind and args.hint_proof_kind and args.hint_proof_kind != required_hint_proof_kind:
        result = "BLOCKED_HINT_PROOF_KIND"
        reason = f"required HINT proof kind is {required_hint_proof_kind}"
    elif args.execute and not args.user_confirmed:
        result = "BLOCKED"
        reason = "missing --user-confirmed"
        mode = "execute_requested"
    elif (args.execute or run_layer_runner_in_plan_only) and layer_runner is None:
        result = MISSING_N3_REAL_RUNNER_RESULT
        reason = f"{MISSING_N3_REAL_RUNNER_RESULT}:{step_id}"
        mode = "execute_requested" if args.execute else "plan_only"
    target_absence_required = bool(args.target_run_id)
    report: dict[str, Any] = {
        "result": result,
        "reason": reason,
        "mode": mode,
        "step_id": step_id,
        "layer_role": layer_role,
        "for_trade_date": args.for_trade_date,
        "source_run_id": args.source_run_id,
        "target_run_id": args.target_run_id,
        "n4_context_run_id": args.n4_context_run_id,
        "subscription_run_id": args.subscription_run_id,
        "source_condition_run_id": args.source_condition_run_id,
        "source_payload_path": args.source_payload_path,
        "source_artifact_path": args.source_artifact_path,
        "contract_path": args.contract_path,
        "preflight_path": args.preflight_path,
        "hint_proof_kind": hint_proof_kind,
        "execute_requested": bool(args.execute),
        "user_confirmed": bool(args.user_confirmed),
        "execute_contract_ready": execute_contract_ready,
        "layer_runner_status": "wired" if layer_runner is not None else "missing",
        "layer_runner_name": layer_runner_name,
        "audited_layer_capability": audited_layer_capability,
        "output_contract": dict(output_contract),
        "target_absence_check_required": target_absence_required,
        "target_absence_checked": False,
    }
    _apply_forbidden_side_effect_guards(report)
    should_run_layer_runner = args.execute or run_layer_runner_in_plan_only
    if result.startswith("BLOCKED") or not should_run_layer_runner:
        return report

    report["mode"] = "execute_requested" if args.execute else "plan_only"
    absence = _run_target_absence_checker(
        args=args,
        report=report,
        target_absence_checker=target_absence_checker,
    )
    report.update(absence)
    if str(report.get("result", "")).startswith("BLOCKED"):
        _apply_forbidden_side_effect_guards(report)
        return report

    runner_payload = layer_runner(args=args, report=report) if layer_runner is not None else None
    if runner_payload:
        report.update(dict(runner_payload))
    if report.get("result") == "PLAN_ONLY_PASS":
        report["result"] = N3_READY_RESULT
    report["result"] = report.get("result") or N3_READY_RESULT
    _apply_forbidden_side_effect_guards(report)
    return report


def dry_run_target_absence_checker(*, args: argparse.Namespace, report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target_absence_check_status": "dry_run_contract_only",
        "target_absence_check_mode": "no_db_patch_gate",
        "target_run_id": args.target_run_id,
    }


def _run_target_absence_checker(
    *,
    args: argparse.Namespace,
    report: Mapping[str, Any],
    target_absence_checker: TargetAbsenceChecker | None,
) -> dict[str, Any]:
    checker = target_absence_checker or dry_run_target_absence_checker
    payload = checker(args=args, report=report) or {}
    result = dict(payload)
    if "status" in result and "target_absence_check_status" not in result:
        result["target_absence_check_status"] = result["status"]
    result.setdefault("target_absence_check_status", "dry_run_contract_only")
    result["target_absence_checked"] = True
    return result


def _apply_forbidden_side_effect_guards(report: dict[str, Any]) -> None:
    report["writes_outbox"] = False
    report["consumes_outbox"] = False
    report["updates_inbox_or_checkpoint"] = False
    report["starts_worker"] = False
    report["touches_n4_n5_n6"] = False
    report["touches_n5_n6"] = False
    report["side_effects"] = {
        "database_written": False,
        "market_data_pulled": False,
        "runtime_executed": False,
        "outbox_consumed": False,
        "inbox_or_checkpoint_updated": False,
        "worker_started": False,
        "rollback_executed": False,
        "schema_changed": False,
        "n4_n5_n6_touched": False,
        "n5_n6_touched": False,
    }
