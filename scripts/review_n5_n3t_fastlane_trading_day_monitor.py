#!/usr/bin/env python3
"""Read-only monitor review for N5/N3T Fastlane trading-day automation."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import subprocess
from pathlib import Path
from typing import Any, Sequence

from ashare_v3.runtime_control.n5_n3t_fastlane import (
    FASTLANE_LABELS,
    build_fastlane_chain_evidence,
    build_fastlane_active_worker_policy_review,
    build_fastlane_trading_day_monitor_review,
    classify_fastlane_session_phase,
)
from generate_n5_n3t_fastlane_db_artifact_summary import (
    build_artifact_summary,
    build_db_summary,
    _load_raw_db_snapshot,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review N5/N3T Fastlane trading-day monitor evidence.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--current-exchange-time", required=True)
    parser.add_argument("--launchagents-dir", default=str(Path.home() / "Library" / "LaunchAgents"))
    parser.add_argument("--log-dir", default="tmp")
    parser.add_argument("--launchd-state-path")
    parser.add_argument("--chain-evidence-path")
    parser.add_argument("--raw-db-snapshot-path", default="")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--n5-action-run-id-like", default="")
    parser.add_argument("--n3t-metric-run-id-like", default="")
    parser.add_argument("--n5-active-scope-artifact-dir", default="")
    parser.add_argument("--n3-c1-n3t-artifact-dir", default="")
    parser.add_argument("--trigger-time", default="")
    parser.add_argument("--trade-calendar-is-open", choices=("true", "false"))
    parser.add_argument("--session-phase", default="")
    parser.add_argument("--closed-minute-available", choices=("auto", "true", "false"), default="auto")
    parser.add_argument("--active-worker-policy-review-output-path")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    launchd_states = _load_launchd_states(args.launchd_state_path)
    plist_summaries = _read_plist_summaries(Path(args.launchagents_dir))
    recent_log_manifests = _read_recent_log_manifests(Path(args.log_dir))
    stderr_snapshots = _read_recent_stderr_snapshots(Path(args.log_dir))
    chain_evidence = _load_chain_evidence(args)
    report = build_fastlane_trading_day_monitor_review(
        for_trade_date=args.for_trade_date,
        current_exchange_time=args.current_exchange_time,
        launchd_states=launchd_states,
        plist_summaries=plist_summaries,
        recent_log_manifests=recent_log_manifests,
        stderr_snapshots=stderr_snapshots,
        chain_evidence=chain_evidence,
    )
    report["chain_evidence_source"] = chain_evidence.get("evidence_source", "chain_evidence_path")
    report["active_worker_policy_review"] = build_fastlane_active_worker_policy_review(
        for_trade_date=args.for_trade_date,
        monitor_review=report,
    )
    if args.active_worker_policy_review_output_path:
        output_path = Path(args.active_worker_policy_review_output_path)
        payload = _write_json_artifact(output_path, report["active_worker_policy_review"])
        report["active_worker_policy_review_output_path"] = str(output_path)
        report["active_worker_policy_review_sha256"] = hashlib.sha256(payload).hexdigest()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"result={report['result']} final_verdict={report['final_verdict']}")
    return 0


def _load_chain_evidence(args: argparse.Namespace) -> dict[str, Any]:
    if args.chain_evidence_path:
        evidence = _read_json_object(Path(args.chain_evidence_path))
        evidence.setdefault("evidence_source", "chain_evidence_path")
        return evidence

    required = {
        "--n5-active-scope-artifact-dir": args.n5_active_scope_artifact_dir,
        "--n3-c1-n3t-artifact-dir": args.n3_c1_n3t_artifact_dir,
        "--trade-calendar-is-open": args.trade_calendar_is_open,
    }
    missing = [name for name, value in required.items() if not str(value or "").strip()]
    if missing:
        raise SystemExit(
            "either --chain-evidence-path or read-only evidence inputs are required; missing "
            + ", ".join(missing)
        )

    db_summary = build_db_summary(_load_raw_db_snapshot(args))
    artifact_summary = build_artifact_summary(
        n5_active_scope_artifact_dir=Path(args.n5_active_scope_artifact_dir),
        n3_c1_n3t_artifact_dir=Path(args.n3_c1_n3t_artifact_dir),
    )
    trigger_time = str(args.trigger_time or args.current_exchange_time)
    session_phase = str(args.session_phase or "").strip()
    if not session_phase:
        session_phase = str(
            classify_fastlane_session_phase(
                for_trade_date=args.for_trade_date,
                trigger_time=trigger_time,
                current_exchange_time=args.current_exchange_time,
                trade_calendar_is_open=args.trade_calendar_is_open == "true",
            )["phase"]
        )
    evidence = build_fastlane_chain_evidence(
        for_trade_date=args.for_trade_date,
        session_phase=session_phase,
        closed_minute_available=_resolve_closed_minute_available(
            args.closed_minute_available,
            current_exchange_time=args.current_exchange_time,
            session_phase=session_phase,
        ),
        db_summary=db_summary,
        artifact_summary=artifact_summary,
    )
    evidence["evidence_source"] = "read_only_db_artifact_inputs"
    return evidence


def _resolve_closed_minute_available(value: str, *, current_exchange_time: str, session_phase: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    if session_phase in {"closed_day_or_non_trading", "pre_open_before_0925", "pre_open_call_auction_after_0925"}:
        return False
    hhmm = _extract_hhmm(current_exchange_time)
    return hhmm >= 931


def _extract_hhmm(value: str) -> int:
    match = re.search(r"(?:^|[^0-9])([0-2][0-9]):([0-5][0-9])", str(value or ""))
    if not match:
        return 0
    return int(match.group(1) + match.group(2))


def _load_launchd_states(path: str | None) -> dict[str, Any]:
    if path:
        return _read_json_object(Path(path))
    return {label: _read_launchctl_state(label) for label in FASTLANE_LABELS.values()}


def _read_launchctl_state(label: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["launchctl", "print", f"gui/{_uid()}/{label}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return {"loaded": False, "pid": None, "runs": 0, "last_exit_code": completed.returncode}
    text = completed.stdout
    return {
        "loaded": True,
        "pid": _extract_int(text, r"\bpid = (\d+)"),
        "runs": _extract_int(text, r"\bruns = (\d+)") or 0,
        "last_exit_code": _extract_int(text, r"\blast exit code = (-?\d+)") or 0,
    }


def _uid() -> str:
    completed = subprocess.run(["id", "-u"], check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _read_plist_summaries(launchagents_dir: Path) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for label in FASTLANE_LABELS.values():
        path = launchagents_dir / f"{label}.plist"
        if not path.exists():
            summaries[label] = {"label": label, "missing": True}
            continue
        plist = plistlib.loads(path.read_bytes())
        encoded = json.dumps(plist, ensure_ascii=False, sort_keys=True)
        args = plist.get("ProgramArguments") or []
        summary = {
            "label": plist.get("Label"),
            "start_interval": plist.get("StartInterval"),
            "run_at_load": plist.get("RunAtLoad"),
            "keep_alive": plist.get("KeepAlive"),
            "uses_activation_config": "--activation-config" in args,
            "scheduler_quiet": "--scheduler-quiet" in args,
            "has_placeholder": bool(re.search(r"__[A-Z0-9_]+__", encoded)),
            "has_secret_literal": "postgresql://" in encoded or "postgres://" in encoded,
            "has_old_runner_ref": any(
                token in encoded
                for token in (
                    "run_n3_intraday_proof_poller_once.py",
                    "run_n4_intraday_proof_discovery_poll_once.py",
                    "run_n3_intraday_b1_c1_b2_auto_poll_once.py",
                )
            ),
        }
        activation_config_path = _argument_value_after(args, "--activation-config")
        if activation_config_path:
            summary["activation_config_path"] = activation_config_path
            for trade_date in sorted(set(re.findall(r"20\d{6}", activation_config_path))):
                summary[f"activation_config_{trade_date}"] = True
        summaries[label] = summary
    return summaries


def _argument_value_after(args: list[Any], flag: str) -> str:
    for index, value in enumerate(args):
        if value == flag and index + 1 < len(args):
            return str(args[index + 1])
    return ""


def _read_recent_log_manifests(log_dir: Path) -> dict[str, Any]:
    manifests: dict[str, Any] = {}
    for label in FASTLANE_LABELS.values():
        path = log_dir / f"{label}.out.log"
        manifests[label] = _tail_json_lines(path)
    return manifests


def _read_recent_stderr_snapshots(log_dir: Path) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for label in FASTLANE_LABELS.values():
        path = log_dir / f"{label}.err.log"
        if not path.exists():
            snapshots[label] = {"exists": False, "size": 0, "has_current_error": False}
            continue
        stat = path.stat()
        tail = _tail_text(path)
        has_runtime_error = bool(
            re.search(r"\b(?:Traceback|Error|Exception|TabError|SyntaxError|NameError|AttributeError)\b", tail)
        )
        source_mtime = _source_mtime_for_label(label)
        snapshots[label] = {
            "exists": True,
            "size": stat.st_size,
            "mtime_epoch": stat.st_mtime,
            "source_mtime_epoch": source_mtime,
            "has_runtime_error": has_runtime_error,
            "has_current_error": has_runtime_error and stat.st_mtime >= source_mtime,
        }
    return snapshots


def _tail_json_lines(path: Path, *, max_bytes: int = 131072, max_lines: int = 10) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        handle.seek(0, 2)
        end = handle.tell()
        handle.seek(max(0, end - max_bytes))
        text = handle.read().decode("utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows[-max_lines:]


def _tail_text(path: Path, *, max_bytes: int = 131072) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        end = handle.tell()
        handle.seek(max(0, end - max_bytes))
        return handle.read().decode("utf-8", errors="replace")


def _source_mtime_for_label(label: str) -> float:
    if label == FASTLANE_LABELS["n3_c1_n3t"]:
        paths = [
            Path("scripts/run_n3_c1_n3t_action_confirmation_fastlane_once.py"),
            Path("src/ashare_v3/runtime_control/n5_n3t_fastlane.py"),
        ]
    else:
        paths = [
            Path("scripts/run_n5_live_tracking_poller_once.py"),
            Path("src/ashare_v3/action/live_tracking_poller.py"),
            Path("src/ashare_v3/runtime_control/n5_n3t_fastlane.py"),
        ]
    mtimes = [path.stat().st_mtime for path in paths if path.exists()]
    return max(mtimes) if mtimes else 0.0


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def _write_json_artifact(path: Path, payload: dict[str, Any]) -> bytes:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return encoded


def _extract_int(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return int(match.group(1))


if __name__ == "__main__":
    raise SystemExit(main())
