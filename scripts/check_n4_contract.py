#!/usr/bin/env python3
"""Static N4-0 trigger contract checker.

This script does not connect to PostgreSQL and does not execute migrations.
It only scans N4 trigger schema/code contract artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ashare_v3.events.models import N4_COMMON_PAYLOAD_KEYS, N4_EVENT_TYPES
from ashare_v3.trigger.context_preflight import INPUT_EVENT_TYPES, TARGET_CONTEXT_TABLES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "sql" / "010_trigger_layer_schema.sql"
SCAN_PATHS = [
    SCHEMA_PATH,
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "__init__.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "action_confirmation_metric_matcher.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "context_execute.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "context_preflight.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "c3_replay_audit_execute.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "c3_replay_plan.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "event_factory.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "canonical_signal.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "local_trigger_dry_run.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "projection_matcher.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "projection_matcher_execute.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "run_once_execute.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "standard_trigger_execute.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "trigger" / "synthetic_dry_run.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "events" / "models.py",
    PROJECT_ROOT / "src" / "ashare_v3" / "events" / "ids.py",
    PROJECT_ROOT / "scripts" / "run_trigger_context_snapshot_execute.py",
    PROJECT_ROOT / "scripts" / "run_trigger_context_snapshot_rebuild.py",
    PROJECT_ROOT / "scripts" / "run_c3_replay_audit_once.py",
    PROJECT_ROOT / "scripts" / "run_trigger_synthetic_once_execute.py",
    PROJECT_ROOT / "scripts" / "run_trigger_projection_matcher_once.py",
    PROJECT_ROOT / "scripts" / "run_20260528_trigger_v2_execute_once.py",
    PROJECT_ROOT / "scripts" / "run_trigger_action_confirmation_metric_once.py",
    PROJECT_ROOT / "scripts" / "plan_trigger_action_confirmation_metric_dry_run.py",
    PROJECT_ROOT / "scripts" / "plan_trigger_action_confirmation_metric_business_execute_gate.py",
    PROJECT_ROOT / "scripts" / "plan_local_trigger_dry_run.py",
    PROJECT_ROOT / "scripts" / "plan_c3_replay_dry_run.py",
    PROJECT_ROOT / "scripts" / "plan_trigger_projection_matcher_dry_run.py",
    PROJECT_ROOT / "scripts" / "plan_trigger_synthetic_event_dry_run.py",
    PROJECT_ROOT / "scripts" / "plan_trigger_context_preflight.py",
    PROJECT_ROOT / "sql" / "018_trigger_replay_audit_schema.sql",
    PROJECT_ROOT / "sql" / "N4_C3_replay_audit_business_rollback.sql",
    PROJECT_ROOT / "sql" / "N4_projection_matcher_rollback.sql",
    PROJECT_ROOT / "sql" / "N4_20260528_trigger_execute_rollback.sql",
]
FORBIDDEN_OUTPUT_EVENT_LITERALS = (
    "ActionEvent",
    "HintEvent",
    "RiskEvent",
    "PositionEvent",
)
FORBIDDEN_PREFIX_EVENT_LITERAL = re.compile(r"['\"](?:User|Voice|Sim)[A-Za-z0-9_]+['\"]")
FORBIDDEN_DOWNSTREAM_TABLE_PATTERN = re.compile(
    r"\b(?:CREATE\s+TABLE|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
    r"(?:common_)?(?:action|user|voice|sim|position)_[A-Za-z0-9_]*",
    re.IGNORECASE,
)
CREATE_RUNTIME_TABLE_PATTERN = re.compile(r"\bCREATE\s+TABLE\s+[^;\n]*_runtime\b", re.IGNORECASE)
N4_TRIGGER_MATCH_SCHEMA_EVENT_TYPES = ("TriggerMatched", "TriggerPendingMarketData")


def iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                sorted(
                    child
                    for child in path.rglob("*")
                    if child.is_file() and child.suffix in {".py", ".sql"}
                )
            )
    return files


def scan_forbidden_contracts(files: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for event_type in FORBIDDEN_OUTPUT_EVENT_LITERALS:
            if f"'{event_type}'" in text or f'"{event_type}"' in text:
                findings.append(f"{path}: forbidden N4 downstream event literal {event_type}")
        for match in FORBIDDEN_PREFIX_EVENT_LITERAL.finditer(text):
            findings.append(f"{path}: forbidden N4 prefixed event literal {match.group(0)}")
        if FORBIDDEN_DOWNSTREAM_TABLE_PATTERN.search(text):
            findings.append(f"{path}: N4 contract writes a downstream table")
        if CREATE_RUNTIME_TABLE_PATTERN.search(text):
            findings.append(f"{path}: CREATE TABLE uses *_runtime")
        if "/Volumes/MacRaid" in text:
            findings.append(f"{path}: N4 contract references external runtime path")
    return findings


def check_schema_contract(schema_text: str) -> list[str]:
    findings: list[str] = []
    required_tables = (
        "common_trigger_run",
        "common_trigger_quality_item",
        "common_trigger_state",
        "common_trigger_match",
        *TARGET_CONTEXT_TABLES.values(),
    )
    for table_name in required_tables:
        if f"CREATE TABLE {table_name}" not in schema_text:
            findings.append(f"missing N4 schema table: {table_name}")

    for event_type in N4_TRIGGER_MATCH_SCHEMA_EVENT_TYPES:
        if event_type not in schema_text:
            findings.append(f"schema missing N4 output event type: {event_type}")

    for event_type in INPUT_EVENT_TYPES:
        if event_type not in schema_text:
            findings.append(f"schema missing N4 input event type: {event_type}")

    for forbidden in ("market_data_pulled = false", "action_layer_touched = false", "user_layer_touched = false", "sim_touched = false"):
        if forbidden not in schema_text:
            findings.append(f"schema missing N4 boundary check text: {forbidden}")

    return findings


def check_python_contract(files: list[Path]) -> list[str]:
    findings: list[str] = []
    contract_text = "\n".join(path.read_text(encoding="utf-8") for path in files if path.suffix == ".py")
    for event_type in N4_EVENT_TYPES:
        if event_type not in contract_text:
            findings.append(f"python contract missing N4 event type: {event_type}")
    for key in N4_COMMON_PAYLOAD_KEYS:
        if key not in contract_text:
            findings.append(f"python contract missing N4 payload key: {key}")
    for event_type in INPUT_EVENT_TYPES:
        if event_type not in contract_text:
            findings.append(f"python contract missing N4 input event type: {event_type}")
    return findings


def run_check() -> dict[str, Any]:
    files = iter_files(SCAN_PATHS)
    findings: list[str] = []
    if not SCHEMA_PATH.exists():
        findings.append(f"missing schema: {SCHEMA_PATH}")
        schema_text = ""
    else:
        schema_text = SCHEMA_PATH.read_text(encoding="utf-8")

    findings.extend(scan_forbidden_contracts(files))
    findings.extend(check_schema_contract(schema_text))
    findings.extend(check_python_contract(files))

    return {
        "passed": not findings,
        "finding_count": len(findings),
        "findings": findings,
        "checked_files": [str(path.relative_to(PROJECT_ROOT)) for path in files],
    }


def main() -> int:
    result = run_check()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
