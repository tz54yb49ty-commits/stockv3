#!/usr/bin/env python3
"""Classify N6 B-track changes and inspect delivery state without side effects."""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json"
REGISTRY_PATH = REPO_ROOT / "docs" / "N6_B_TRACK_BASELINE_REGISTRY_V1.json"
REQUIRED_BRIEF_FIELDS = (
    "page_or_feature",
    "users",
    "expected_behavior",
    "affects_virtual_money_proposals_or_positions",
)
PLISTS = {
    "web": Path.home() / "Library/LaunchAgents/com.ashare-v3.n6.user-web.plist",
    "quote_writer": Path.home() / "Library/LaunchAgents/com.ashare-v3.n6.virtual-quote-v1.plist",
    "virtual_executor": Path.home() / "Library/LaunchAgents/com.ashare-v3.n6.virtual-executor-v1.plist",
    "stop_loss": Path.home() / "Library/LaunchAgents/com.ashare-v3.n6.virtual-stop-v1.plist",
}


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def classify_request(payload: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_BRIEF_FIELDS if field not in payload]
    if missing:
        return decision("BLOCK", reason="missing_user_brief_fields", missing_fields=missing)

    profile = payload.get("change_profile") or {}
    if not isinstance(profile, dict):
        return decision("BLOCK", reason="change_profile_must_be_object")

    if bool(profile.get("real_broker")) or bool(profile.get("real_order")):
        return decision("REJECT", reason="real_trading_forbidden")
    if bool(profile.get("writes_n1_n5")):
        return decision("REJECT", reason="n6_upstream_writeback_forbidden")
    if bool(profile.get("automatic_proposal_creation")) or bool(
        profile.get("automatic_proposal_confirmation")
    ):
        return decision("REJECT", reason="automatic_proposal_creation_or_confirmation_forbidden")
    if bool(profile.get("requested_new_one_off_policy")):
        return decision("REJECT", reason="normal_delivery_must_reuse_lane_policy")

    virtual_effect = payload["affects_virtual_money_proposals_or_positions"]
    if not isinstance(virtual_effect, bool):
        return decision(
            "BLOCK",
            reason="affects_virtual_money_proposals_or_positions_must_be_boolean",
        )

    lane_candidates: list[str] = []
    if virtual_effect or any(
        bool(profile.get(field))
        for field in ("executor_change", "stop_loss_change", "automatic_virtual_execution")
    ):
        lane_candidates.append("L3")
    if any(
        bool(profile.get(field))
        for field in (
            "n6_schema_change",
            "n6_business_rule_change",
            "monitor_scope_write",
            "strategy_configuration_write",
        )
    ):
        lane_candidates.append("L2")
    if bool(profile.get("ui_only")) or bool(profile.get("read_only_query_only")):
        lane_candidates.append("L1")

    if not lane_candidates:
        return decision("BLOCK", reason="ambiguous_change_profile")
    if len(lane_candidates) != 1:
        return decision(
            "BLOCK",
            reason="mixed_delivery_lanes",
            lane_candidates=sorted(lane_candidates),
        )

    lane = lane_candidates[0]
    lane_contract = contract["lanes"][lane]
    return decision(
        "ACCEPT",
        reason="classified",
        lane=lane,
        policy_id=lane_contract["policy_id"],
        title=lane_contract["title"],
        required_sequence=lane_contract["required_sequence"],
        required_evidence=lane_contract["required_evidence"],
        forbidden_effects=lane_contract["forbidden_effects"],
    )


def decision(state: str, *, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": state == "ACCEPT",
        "decision": state,
        "reason": reason,
        **extra,
    }


def run_git(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def parse_worktree_porcelain(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in text.splitlines():
        if not raw_line:
            if current:
                rows.append(current)
                current = {}
            continue
        key, _, value = raw_line.partition(" ")
        current[key] = value
    if current:
        rows.append(current)
    return rows


def release_id_from_plist(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False}
    with path.open("rb") as handle:
        payload = plistlib.load(handle)
    working_directory = str(payload.get("WorkingDirectory") or "")
    release_id = Path(working_directory).name if working_directory else ""
    commit = release_id.rsplit("__", 1)[-1] if "__" in release_id else ""
    tree = ""
    if len(commit) == 40:
        result = run_git("show", "-s", "--format=%T", commit)
        if result.returncode == 0:
            tree = result.stdout.strip()
    return {
        "present": True,
        "working_directory": working_directory,
        "release_id": release_id,
        "commit": commit,
        "tree": tree,
    }


def inspect_state() -> dict[str, Any]:
    worktrees_result = run_git("worktree", "list", "--porcelain")
    if worktrees_result.returncode != 0:
        return decision("BLOCK", reason="git_worktree_inventory_failed")
    worktrees = parse_worktree_porcelain(worktrees_result.stdout)
    n6_worktrees = [
        row
        for row in worktrees
        if row.get("branch", "").startswith("refs/heads/codex/n6")
    ]
    services = {name: release_id_from_plist(path) for name, path in PLISTS.items()}
    releases = {
        row["release_id"]
        for row in services.values()
        if row.get("present") and row.get("release_id")
    }
    registry = load_json(REGISTRY_PATH)
    return {
        "ok": True,
        "decision": "READ_ONLY_INVENTORY",
        "side_effects": {
            "file_writes": 0,
            "database_connections": 0,
            "launchctl_calls": 0,
            "service_operations": 0,
        },
        "canonical_integration": registry["canonical_integration"],
        "worktrees": {
            "total": len(worktrees),
            "n6_prefixed": len(n6_worktrees),
            "managed_active_limit": registry["worktrees"]["managed_active_limit"],
            "cleanup_executed": False,
        },
        "services": services,
        "unified_release": len(releases) == 1 and len(services) == 4,
        "release_ids": sorted(releases),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    classify = subparsers.add_parser("classify", help="classify one JSON request")
    classify.add_argument(
        "--request-json",
        required=True,
        help="path to a request JSON object, or '-' for stdin",
    )
    subparsers.add_parser("inspect", help="print a read-only Git/plist inventory")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    contract = load_json(CONTRACT_PATH)
    if args.command == "classify":
        if args.request_json == "-":
            payload = json.load(sys.stdin)
        else:
            payload = load_json(Path(args.request_json))
        result = classify_request(payload, contract)
    else:
        result = inspect_state()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("decision") in {"ACCEPT", "READ_ONLY_INVENTORY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
