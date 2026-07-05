"""N1 -> N3-A1 Fast Lane bundle contract helpers.

This module defines pure schema and validation orchestration for Fast Lane
bundle wrappers. It does not connect to a database or execute subprocesses.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ashare_v3.runtime.fastlane_validation import (
    FastLaneValidationError,
    assert_downstream_refs_zero,
    assert_execute_command_confirmed,
    assert_expected_actual_rows_match,
    assert_forbidden_scope_false,
    assert_no_cross_layer_execute,
    assert_no_old_system_touch,
    assert_no_unexpected_event_delta,
    assert_postgres_commit_enabled_when_required,
    assert_p0_zero,
)


PASS_STATUSES = frozenset({"pass", "passed", "prefight_pass", "preflight_pass", "contract_pass"})
N1_POSTGRES_COMMIT_REQUIRED_MARKERS = (
    "run_n1_source_facts_once.py",
    "run_n1_20260608_source_facts_once.py",
    "run_official_daily_ingestion_",
    "run_condition_source_activation_",
)


@dataclass(frozen=True)
class BundleSpec:
    bundle_kind: str
    layer_role: str
    report_json_name: str
    report_markdown_name: str
    next_gate: str
    forbidden_command_markers: tuple[str, ...]


BUNDLE_SPECS: dict[str, BundleSpec] = {
    "n1": BundleSpec(
        bundle_kind="n1",
        layer_role="N1_ingestion",
        report_json_name="02_n1_bundle_execute_report.json",
        report_markdown_name="02_n1_bundle_execute_report.md",
        next_gate="N2_CONDITION_FAST_LANE_BUNDLE_EXECUTE_GATE",
        forbidden_command_markers=(
            "run_condition",
            "condition_layer",
            "n2_",
            "market_data",
            "subscription",
            "previous_day_minute",
            "realtime",
            "trigger",
            "action",
            "n4_",
            "n5_",
            "n6_",
            "worker",
        ),
    ),
    "n2": BundleSpec(
        bundle_kind="n2",
        layer_role="N2_condition",
        report_json_name="03_n2_bundle_execute_report.json",
        report_markdown_name="03_n2_bundle_execute_report.md",
        next_gate="N3_MARKET_DATA_A1_FAST_LANE_BUNDLE_EXECUTE_GATE",
        forbidden_command_markers=(
            "market_data",
            "subscription",
            "preload",
            "pull",
            "realtime",
            "snapshot",
            "minute_bar",
            "n3_",
            "trigger",
            "action",
            "n4_",
            "n5_",
            "n6_",
            "worker",
        ),
    ),
    "n3_a1": BundleSpec(
        bundle_kind="n3_a1",
        layer_role="N3_market_data",
        report_json_name="04_n3_a1_bundle_execute_report.json",
        report_markdown_name="04_n3_a1_bundle_execute_report.md",
        next_gate="RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_CLOSEOUT_GATE",
        forbidden_command_markers=(
            "realtime_snapshot",
            "today_minute",
            "realtime_projection",
            "action_confirmation",
            "trigger",
            "action_consumer",
            "run_n4",
            "run_n5",
            "run_n6",
            "n4_",
            "n5_",
            "n6_",
            "worker",
        ),
    ),
}


@dataclass(frozen=True)
class SideEffectFlags:
    business_code_modified: bool = False
    database_written: bool = False
    n1_n2_n3_execute_performed: bool = False
    rollback_sql_executed: bool = False
    outbox_inbox_checkpoint_consumed_or_updated: bool = False
    worker_started: bool = False
    n3_b_or_n3_c_entered: bool = False
    n4_n5_n6_entered: bool = False
    realtime_market_data_pulled: bool = False
    delivery_push_voice_mobile_touched: bool = False
    sim_position_pnl_real_trade_touched: bool = False
    proposal_order_trade_touched: bool = False
    old_system_touched: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "business_code_modified": self.business_code_modified,
            "database_written": self.database_written,
            "n1_n2_n3_execute_performed": self.n1_n2_n3_execute_performed,
            "rollback_sql_executed": self.rollback_sql_executed,
            "outbox_inbox_checkpoint_consumed_or_updated": self.outbox_inbox_checkpoint_consumed_or_updated,
            "worker_started": self.worker_started,
            "n3_b_or_n3_c_entered": self.n3_b_or_n3_c_entered,
            "n4_n5_n6_entered": self.n4_n5_n6_entered,
            "realtime_market_data_pulled": self.realtime_market_data_pulled,
            "delivery_push_voice_mobile_touched": self.delivery_push_voice_mobile_touched,
            "sim_position_pnl_real_trade_touched": self.sim_position_pnl_real_trade_touched,
            "proposal_order_trade_touched": self.proposal_order_trade_touched,
            "old_system_touched": self.old_system_touched,
        }


ARTIFACT_FILE_NAMES = {
    "runtime_readiness_json": "01_runtime_readiness.json",
    "runtime_readiness_md": "01_runtime_readiness.md",
    "n1_bundle_report_json": "02_n1_bundle_execute_report.json",
    "n1_bundle_report_md": "02_n1_bundle_execute_report.md",
    "n2_bundle_report_json": "03_n2_bundle_execute_report.json",
    "n2_bundle_report_md": "03_n2_bundle_execute_report.md",
    "n3_a1_bundle_report_json": "04_n3_a1_bundle_execute_report.json",
    "n3_a1_bundle_report_md": "04_n3_a1_bundle_execute_report.md",
    "closeout_registration_json": "05_closeout_registration.json",
    "closeout_registration_md": "05_closeout_registration.md",
}

REQUIRED_REPORT_FIELDS = frozenset(
    {
        "bundle_run_id",
        "layer_role",
        "status",
        "sub_steps",
        "sub_report_paths",
        "quality_summary",
        "rollback_paths",
        "side_effect_flags",
        "blockers",
        "next_gate",
    }
)


def build_fastlane_artifact_paths(*, for_trade_date: str, docs_root: Path | str = Path("docs")) -> dict[str, Path]:
    base = Path(docs_root) / "fastlane" / for_trade_date
    return {key: base / file_name for key, file_name in ARTIFACT_FILE_NAMES.items()}


def validate_fastlane_artifact_schema(artifact_kind: str, data: Mapping[str, object]) -> bool:
    if artifact_kind in {"n1_bundle_report", "n2_bundle_report", "n3_a1_bundle_report"}:
        missing = REQUIRED_REPORT_FIELDS - set(data)
        if missing:
            raise ValueError(f"fastlane_schema_missing_fields: {artifact_kind} {sorted(missing)}")
        if not isinstance(data.get("sub_report_paths"), list):
            raise ValueError(f"fastlane_schema_sub_report_paths_not_list: {artifact_kind}")
        if not isinstance(data.get("side_effect_flags"), Mapping):
            raise ValueError(f"fastlane_schema_side_effect_flags_not_mapping: {artifact_kind}")
        return True
    raise ValueError(f"unknown_fastlane_artifact_kind: {artifact_kind}")


def run_bundle_from_step_dicts(
    *,
    bundle_kind: str,
    for_trade_date: str,
    step_dicts: Sequence[Mapping[str, object]],
    bundle_run_id: str | None = None,
    wrapper_execute: bool = True,
    wrapper_user_confirmed: bool = True,
) -> dict[str, Any]:
    spec = BUNDLE_SPECS[bundle_kind]
    blockers: list[str] = []
    evaluated_steps: list[dict[str, Any]] = []
    sub_report_paths: list[str] = []
    rollback_paths: list[str] = []
    quality_summary = {"P0": 0, "P1": 0, "P2": 0}
    side_effect_flags = SideEffectFlags().to_dict()

    if not step_dicts:
        blockers.append("no_child_steps")

    for raw_step in step_dicts:
        step = _normalize_step(raw_step)
        evaluated_steps.append(step)
        blockers.extend(step.get("pre_execution_blockers", []))
        sub_report_paths.extend(step["sub_report_paths"])
        if step.get("rollback_sql_path"):
            rollback_paths.append(str(step["rollback_sql_path"]))
        _merge_quality(quality_summary, step["quality_summary"])
        _merge_side_effect_flags(side_effect_flags, step["side_effect_flags"])

        step_blockers = _validate_step(
            spec=spec,
            step=step,
            wrapper_execute=wrapper_execute,
            wrapper_user_confirmed=wrapper_user_confirmed,
        )
        blockers.extend(step_blockers)
        if step_blockers or step["status"].lower() not in PASS_STATUSES:
            if step["status"].lower() not in PASS_STATUSES:
                blockers.append(f"sub_step_failed:{step['step_id']}:{step['status']}")
            break

    status = "blocked" if blockers else "passed"
    report: dict[str, Any] = {
        "bundle_run_id": bundle_run_id or f"{bundle_kind}_fastlane_bundle_{for_trade_date}",
        "bundle_kind": bundle_kind,
        "for_trade_date": for_trade_date,
        "layer_role": spec.layer_role,
        "status": status,
        "result": "PASS" if status == "passed" else "BLOCKED",
        "sub_steps": evaluated_steps,
        "sub_report_paths": sub_report_paths,
        "quality_summary": quality_summary,
        "rollback_paths": rollback_paths,
        "side_effect_flags": side_effect_flags,
        "blockers": blockers,
        "next_gate": spec.next_gate,
    }
    validate_fastlane_artifact_schema(f"{bundle_kind}_bundle_report", report)
    return report


def run_bundle_from_child_command_dicts(
    *,
    bundle_kind: str,
    for_trade_date: str,
    command_dicts: Sequence[Mapping[str, object]],
    bundle_run_id: str | None = None,
    wrapper_execute: bool = False,
    wrapper_user_confirmed: bool = False,
    orchestrate_child_commands: bool = False,
    timeout_seconds: int = 300,
    cwd: Path | str | None = None,
) -> dict[str, Any]:
    """Execute same-layer child commands and assemble a Fast Lane bundle report.

    This path is deliberately opt-in. It is the only path that invokes child
    processes; the existing child-step-json path remains pure report assembly.
    """
    spec = BUNDLE_SPECS[bundle_kind]
    executed_steps: list[dict[str, Any]] = []
    if not orchestrate_child_commands:
        planned = _normalize_step(command_dicts[0] if command_dicts else {"step_id": "no_child_commands"})
        planned["status"] = "blocked"
        planned["command_result"] = {"returncode": None, "stdout": "", "stderr": ""}
        report = run_bundle_from_step_dicts(
            bundle_kind=bundle_kind,
            for_trade_date=for_trade_date,
            step_dicts=[planned],
            bundle_run_id=bundle_run_id,
            wrapper_execute=wrapper_execute,
            wrapper_user_confirmed=wrapper_user_confirmed,
        )
        report["blockers"].insert(0, "wrapper_missing_orchestrate_child_commands")
        _attach_orchestration_summary(report, executed_child_command_count=0, explicit_opt_in=False)
        return report

    for raw_command in command_dicts:
        step = _normalize_step(raw_command)
        preflight_blockers = _validate_step(
            spec=spec,
            step=step,
            wrapper_execute=wrapper_execute,
            wrapper_user_confirmed=wrapper_user_confirmed,
        )
        if preflight_blockers:
            step["status"] = "blocked"
            step["command_result"] = {"returncode": None, "stdout": "", "stderr": ""}
            executed_steps.append(step)
            break

        try:
            command, command_env = _prepare_subprocess_command(step["command"])
        except FastLaneValidationError as exc:
            step["status"] = "blocked"
            step["command_result"] = {"returncode": None, "stdout": "", "stderr": ""}
            step["pre_execution_blockers"] = [str(exc)]
            executed_steps.append(step)
            break
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd) if cwd is not None else None,
                env={**os.environ, **command_env},
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            step["command_result"] = {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
            step["status"] = "passed" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            step["command_result"] = {
                "returncode": None,
                "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
                "timeout_seconds": timeout_seconds,
            }
            step["status"] = "failed"

        _merge_child_report_fields(step)
        executed_steps.append(step)
        if step["status"].lower() not in PASS_STATUSES:
            break

        interim = run_bundle_from_step_dicts(
            bundle_kind=bundle_kind,
            for_trade_date=for_trade_date,
            step_dicts=executed_steps,
            bundle_run_id=bundle_run_id,
            wrapper_execute=wrapper_execute,
            wrapper_user_confirmed=wrapper_user_confirmed,
        )
        if interim["blockers"]:
            break

    report = run_bundle_from_step_dicts(
        bundle_kind=bundle_kind,
        for_trade_date=for_trade_date,
        step_dicts=executed_steps,
        bundle_run_id=bundle_run_id,
        wrapper_execute=wrapper_execute,
        wrapper_user_confirmed=wrapper_user_confirmed,
    )
    _attach_orchestration_summary(
        report,
        executed_child_command_count=sum(
            1 for step in executed_steps if (step.get("command_result") or {}).get("returncode") is not None
        ),
        explicit_opt_in=True,
    )
    return report


def write_bundle_report_files(
    report: Mapping[str, object],
    *,
    json_report_path: Path | str,
    markdown_report_path: Path | str,
) -> None:
    json_path = Path(json_report_path)
    markdown_path = Path(markdown_report_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_bundle_report_markdown(report), encoding="utf-8")


def render_bundle_report_markdown(report: Mapping[str, object]) -> str:
    lines = [
        f"# Fast Lane Bundle Report: {report.get('bundle_kind', '')}",
        "",
        f"- status: `{report.get('status')}`",
        f"- bundle_run_id: `{report.get('bundle_run_id')}`",
        f"- layer_role: `{report.get('layer_role')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- next_gate: `{report.get('next_gate')}`",
        "",
        "## Sub Report Paths",
    ]
    for path in report.get("sub_report_paths", []):  # type: ignore[union-attr]
        lines.append(f"- `{path}`")
    lines.extend(["", "## Blockers"])
    blockers = list(report.get("blockers", []))  # type: ignore[arg-type]
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def load_json_file(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main_for_bundle(bundle_kind: str, argv: Sequence[str] | None = None) -> int:
    spec = BUNDLE_SPECS[bundle_kind]
    parser = argparse.ArgumentParser(description=f"Run {bundle_kind} Fast Lane bundle wrapper in guarded mode.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--bundle-run-id")
    parser.add_argument("--json-report-path")
    parser.add_argument("--markdown-report-path")
    parser.add_argument("--child-step-json", action="append", default=[])
    parser.add_argument("--child-command-json", action="append", default=[])
    parser.add_argument("--orchestrate-child-commands", action="store_true")
    parser.add_argument("--child-command-timeout-seconds", type=int, default=300)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    args = parser.parse_args(argv)

    if args.child_command_json and args.child_step_json:
        parser.error("--child-command-json cannot be combined with --child-step-json")
    if args.child_command_json:
        command_dicts = [json.loads(raw) for raw in args.child_command_json]
        report = run_bundle_from_child_command_dicts(
            bundle_kind=bundle_kind,
            for_trade_date=args.for_trade_date,
            command_dicts=command_dicts,
            bundle_run_id=args.bundle_run_id,
            wrapper_execute=args.execute,
            wrapper_user_confirmed=args.user_confirmed,
            orchestrate_child_commands=args.orchestrate_child_commands,
            timeout_seconds=args.child_command_timeout_seconds,
        )
    else:
        step_dicts = [json.loads(raw) for raw in args.child_step_json]
        report = run_bundle_from_step_dicts(
            bundle_kind=bundle_kind,
            for_trade_date=args.for_trade_date,
            step_dicts=step_dicts,
            bundle_run_id=args.bundle_run_id,
            wrapper_execute=args.execute,
            wrapper_user_confirmed=args.user_confirmed,
        )
    paths = build_fastlane_artifact_paths(for_trade_date=args.for_trade_date)
    json_path = Path(args.json_report_path) if args.json_report_path else paths[f"{bundle_kind}_bundle_report_json"]
    markdown_path = (
        Path(args.markdown_report_path) if args.markdown_report_path else paths[f"{bundle_kind}_bundle_report_md"]
    )
    write_bundle_report_files(report, json_report_path=json_path, markdown_report_path=markdown_path)
    return 0 if report["status"] == "passed" else 2


def _normalize_step(raw_step: Mapping[str, object]) -> dict[str, Any]:
    return {
        "step_id": str(raw_step.get("step_id", "")),
        "layer_role": str(raw_step.get("layer_role", "")),
        "command": _string_list(raw_step.get("command", [])),
        "is_execute_step": bool(raw_step.get("is_execute_step", False)),
        "status": str(raw_step.get("status", "not_run")),
        "sub_report_paths": _string_list(raw_step.get("sub_report_paths", [])),
        "quality_summary": _quality(raw_step.get("quality_summary")),
        "rollback_sql_path": str(raw_step.get("rollback_sql_path", "")),
        "expected_rows": dict(raw_step.get("expected_rows", {}) or {}),
        "actual_rows": dict(raw_step.get("actual_rows", {}) or {}),
        "event_counts_before": dict(raw_step.get("event_counts_before", {}) or {}),
        "event_counts_after": dict(raw_step.get("event_counts_after", {}) or {}),
        "allowed_event_delta": dict(raw_step.get("allowed_event_delta", {}) or {}),
        "downstream_refs": dict(raw_step.get("downstream_refs", {}) or {}),
        "side_effect_flags": dict(raw_step.get("side_effect_flags", {}) or {}),
        "path_scan": _string_list(raw_step.get("path_scan", [])),
        "service_scan": _string_list(raw_step.get("service_scan", [])),
        "requires_postgres_commit_enabled": bool(raw_step.get("requires_postgres_commit_enabled", False)),
        "command_result": dict(raw_step.get("command_result", {}) or {}),
        "pre_execution_blockers": _string_list(raw_step.get("pre_execution_blockers", [])),
    }


def _validate_step(
    *,
    spec: BundleSpec,
    step: Mapping[str, Any],
    wrapper_execute: bool,
    wrapper_user_confirmed: bool,
) -> list[str]:
    blockers: list[str] = []

    if step["layer_role"] != spec.layer_role:
        blockers.append(f"cross_layer_child_step:{step['step_id']}:{step['layer_role']}->{spec.layer_role}")
    try:
        assert_no_cross_layer_execute(
            wrapper_layer_role=spec.layer_role,
            child_step_layer_role=step["layer_role"],
            child_command=step["command"],
            is_execute_step=step["is_execute_step"],
        )
    except FastLaneValidationError as exc:
        blockers.append(str(exc))

    if step["is_execute_step"] and not wrapper_execute:
        blockers.append(f"wrapper_missing_execute:{step['step_id']}")
    if step["is_execute_step"] and not wrapper_user_confirmed:
        blockers.append(f"wrapper_missing_user_confirmed:{step['step_id']}")

    for check in (
        _check_execute_confirmation,
        _check_postgres_commit_flag,
        _check_forbidden_command,
        _check_quality,
        _check_expected_actual_rows,
        _check_event_delta,
        _check_downstream_refs,
        _check_side_effect_flags,
        _check_old_system,
    ):
        try:
            check(spec, step)
        except FastLaneValidationError as exc:
            blockers.append(str(exc))
    return blockers


def _check_execute_confirmation(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    del spec
    assert_execute_command_confirmed(step["command"], is_execute_step=step["is_execute_step"])


def _check_postgres_commit_flag(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    command = " ".join(step["command"]).lower()
    requires_flag = bool(step.get("requires_postgres_commit_enabled", False))
    if spec.bundle_kind == "n1" and step["is_execute_step"]:
        requires_flag = requires_flag or any(marker in command for marker in N1_POSTGRES_COMMIT_REQUIRED_MARKERS)
    assert_postgres_commit_enabled_when_required(
        step["command"],
        is_execute_step=step["is_execute_step"],
        requires_postgres_commit_enabled=requires_flag,
    )


def _check_forbidden_command(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    command = " ".join(step["command"]).lower()
    for marker in spec.forbidden_command_markers:
        if marker in command:
            raise FastLaneValidationError(f"forbidden_command:{step['step_id']}:{marker}")


def _check_quality(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    del spec
    assert_p0_zero(step["quality_summary"])


def _check_expected_actual_rows(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    del spec
    expected = step.get("expected_rows") or {}
    actual = step.get("actual_rows") or {}
    if expected or actual:
        assert_expected_actual_rows_match(expected, actual)


def _check_event_delta(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    del spec
    before = step.get("event_counts_before") or {}
    after = step.get("event_counts_after") or {}
    allowed = step.get("allowed_event_delta") or {}
    if before or after or allowed:
        assert_no_unexpected_event_delta(before, after, allowed)


def _check_downstream_refs(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    del spec
    assert_downstream_refs_zero(step.get("downstream_refs") or {})


def _check_side_effect_flags(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    del spec
    assert_forbidden_scope_false(step.get("side_effect_flags") or {})


def _check_old_system(spec: BundleSpec, step: Mapping[str, Any]) -> None:
    del spec
    assert_no_old_system_touch(
        command=step["command"],
        path_scan=step.get("path_scan") or [],
        service_scan=step.get("service_scan") or [],
    )


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def _quality(value: object) -> dict[str, int]:
    raw = dict(value or {}) if isinstance(value, Mapping) else {}
    return {
        "P0": int(raw.get("P0", 0)),
        "P1": int(raw.get("P1", 0)),
        "P2": int(raw.get("P2", 0)),
    }


def _merge_quality(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key in ("P0", "P1", "P2"):
        target[key] = max(int(target.get(key, 0)), int(source.get(key, 0)))


def _merge_side_effect_flags(target: dict[str, bool], source: Mapping[str, object]) -> None:
    for key, value in source.items():
        if key in target:
            target[key] = bool(target[key] or value)


def _prepare_subprocess_command(command: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    if len(command) == 1:
        command = shlex.split(command[0])
    env: dict[str, str] = {}
    argv = list(command)
    while argv and _is_env_assignment(argv[0]):
        key, value = argv.pop(0).split("=", 1)
        env[key] = value
    if not argv:
        raise FastLaneValidationError("child_command_empty_after_env_assignments")
    forbidden_shell_tokens = {"|", ">", "<", ">>", "&&", "||", ";"}
    if any(part in forbidden_shell_tokens for part in argv):
        raise FastLaneValidationError("child_command_shell_operator_blocked")
    return argv, env


def _is_env_assignment(value: str) -> bool:
    if "=" not in value:
        return False
    key, _ = value.split("=", 1)
    return key.replace("_", "").isalnum() and key[0].isalpha()


def _merge_child_report_fields(step: dict[str, Any]) -> None:
    for report_path in step.get("sub_report_paths", []):
        path = Path(report_path)
        if not path.exists() or path.suffix.lower() != ".json":
            continue
        try:
            report = load_json_file(path)
        except (json.JSONDecodeError, OSError):
            continue
        if not step.get("quality_summary") or step["quality_summary"] == {"P0": 0, "P1": 0, "P2": 0}:
            step["quality_summary"] = _extract_quality_summary(report)
        if not step.get("rollback_sql_path"):
            rollback_path = _first_string_value(report, ("rollback_sql_path", "rollback_path", "rollback_sql"))
            if rollback_path:
                step["rollback_sql_path"] = rollback_path
        if not step.get("expected_rows"):
            expected = report.get("expected_rows") or report.get("expected_row_counts") or {}
            if isinstance(expected, Mapping):
                step["expected_rows"] = dict(expected)
        if not step.get("actual_rows"):
            actual = report.get("actual_rows") or report.get("actual_row_counts") or {}
            if isinstance(actual, Mapping):
                step["actual_rows"] = dict(actual)
        if not step.get("downstream_refs"):
            refs = report.get("downstream_refs") or report.get("downstream_ref_counts") or {}
            if isinstance(refs, Mapping):
                step["downstream_refs"] = dict(refs)


def _extract_quality_summary(report: Mapping[str, Any]) -> dict[str, int]:
    candidates = [
        report.get("quality_summary"),
        report.get("p0_p1_p2"),
        report.get("quality"),
        report,
    ]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        lowered = {str(key).lower(): value for key, value in candidate.items()}
        keys = (
            ("p0", "p1", "p2"),
            ("p0_count", "p1_count", "p2_count"),
        )
        for key_set in keys:
            if all(key in lowered for key in key_set):
                return {
                    "P0": int(lowered[key_set[0]] or 0),
                    "P1": int(lowered[key_set[1]] or 0),
                    "P2": int(lowered[key_set[2]] or 0),
                }
    return {"P0": 0, "P1": 0, "P2": 0}


def _first_string_value(report: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = report.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _attach_orchestration_summary(
    report: dict[str, Any],
    *,
    executed_child_command_count: int,
    explicit_opt_in: bool,
) -> None:
    report["orchestration"] = {
        "mode": "real_child_command",
        "explicit_opt_in": explicit_opt_in,
        "executed_child_command_count": executed_child_command_count,
        "report_only_child_step_json_mode_preserved": True,
        "shell_execution_used": False,
    }
