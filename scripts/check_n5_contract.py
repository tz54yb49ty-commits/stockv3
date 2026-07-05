#!/usr/bin/env python3
"""Static N5 action contract checker.

This script does not connect to PostgreSQL and does not execute migrations. It
only scans N5 schema/code contract artifacts for the current N5 boundary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ashare_v3.action.dry_run import ALLOWED_N4_INPUT_EVENT_TYPES
from ashare_v3.events.models import N5_COMMON_PAYLOAD_KEYS, N5_EVENT_TYPES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "sql" / "011_action_layer_schema.sql"
SCAN_PATHS = [
    SCHEMA_PATH,
    PROJECT_ROOT / "src" / "ashare_v3" / "action",
    PROJECT_ROOT / "src" / "ashare_v3" / "events" / "models.py",
    PROJECT_ROOT / "scripts" / "plan_action_preflight_dry_run.py",
    PROJECT_ROOT / "scripts" / "plan_action_consumer_dry_run.py",
    PROJECT_ROOT / "scripts" / "plan_action_consumer_run_once_dry_run.py",
    PROJECT_ROOT / "scripts" / "run_action_consumer_once.py",
    PROJECT_ROOT / "scripts" / "review_action_execute_preflight.py",
    PROJECT_ROOT / "scripts" / "review_action_schema_event_contract.py",
    PROJECT_ROOT / "scripts" / "review_action_schema_migration.py",
    PROJECT_ROOT / "scripts" / "run_action_schema_011_migration.py",
]
REQUIRED_SCHEMA_TABLES = (
    "common_action_run",
    "common_action_quality_item",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "common_action_event",
    "common_position_state",
    "common_position_event",
)
FORBIDDEN_PREFIX_EVENT_LITERAL = re.compile(r"['\"](?:User|Voice|Sim)[A-Za-z0-9_]+['\"]")
FORBIDDEN_N6_TABLE_WRITE_PATTERN = re.compile(
    r"\b(?:CREATE\s+TABLE|INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+"
    r"(?:common_)?(?:user|voice|sim)_[A-Za-z0-9_]*",
    re.IGNORECASE,
)
FORBIDDEN_CHECKPOINT_WRITE_PATTERN = re.compile(
    r"(?m)^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+common_event_(?:inbox|consumer_checkpoint)\b",
    re.IGNORECASE,
)
CREATE_RUNTIME_TABLE_PATTERN = re.compile(r"\bCREATE\s+TABLE\s+[^;\n]*_runtime\b", re.IGNORECASE)
FORBIDDEN_MARKET_DATA_ADAPTER_PATTERN = re.compile(r"\b(?:mootdx|tushare)\b", re.IGNORECASE)
FORBIDDEN_REAL_TRADE_PATTERN = re.compile(
    r"\b(?:broker_client|place_order|send_order|submit_order|order_submit|trade_api|real_trade_client|xtquant|ctp)\b",
    re.IGNORECASE,
)


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
        for match in FORBIDDEN_PREFIX_EVENT_LITERAL.finditer(text):
            findings.append(f"{path}: forbidden N5 prefixed event literal {match.group(0)}")
        if FORBIDDEN_N6_TABLE_WRITE_PATTERN.search(text):
            findings.append(f"{path}: N5 contract writes a user/voice/sim table")
        checkpoint_write_allowed = path.name in {"execute.py", "run_action_consumer_once.py"}
        if FORBIDDEN_CHECKPOINT_WRITE_PATTERN.search(text) and not checkpoint_write_allowed:
            findings.append(f"{path}: N5 updates common_event_inbox or checkpoint")
        if CREATE_RUNTIME_TABLE_PATTERN.search(text):
            findings.append(f"{path}: CREATE TABLE uses *_runtime")
        if FORBIDDEN_MARKET_DATA_ADAPTER_PATTERN.search(text):
            findings.append(f"{path}: N5 contract directly references mootdx/Tushare")
        if FORBIDDEN_REAL_TRADE_PATTERN.search(text):
            findings.append(f"{path}: N5 contract references a real trading interface")
    return findings


def check_schema_contract(schema_text: str) -> list[str]:
    findings: list[str] = []
    for table_name in REQUIRED_SCHEMA_TABLES:
        if f"CREATE TABLE {table_name}" not in schema_text:
            findings.append(f"missing N5 schema table: {table_name}")

    for event_type in N5_EVENT_TYPES:
        if event_type not in schema_text:
            findings.append(f"schema missing N5 output event type: {event_type}")

    for event_type in ALLOWED_N4_INPUT_EVENT_TYPES:
        if event_type not in schema_text:
            findings.append(f"schema missing N5 input trigger event type: {event_type}")

    for required_text in (
        "market_data_pulled = false",
        "trigger_layer_mutated = false",
        "user_layer_touched = false",
        "voice_touched = false",
        "sim_touched = false",
        "real_trade_touched = false",
        "consumer_checkpoint_updated = false",
        "common_event_inbox_updated = false",
    ):
        if required_text not in schema_text:
            findings.append(f"schema missing N5 boundary check text: {required_text}")

    for table_name in ("stock_action_fact", "index_action_fact", "board_action_fact"):
        unique_marker = f"CREATE TABLE {table_name}"
        if unique_marker in schema_text and "UNIQUE(run_id, dedup_key)" not in schema_text:
            findings.append(f"{table_name} missing run_id + dedup_key unique key")

    for required_text in (
        "source_trigger_match_id",
        "source_condition_run_id",
        "source_market_data_run_id",
        "source_market_trace",
        "action_key",
        "event_schema_version",
    ):
        if required_text not in schema_text:
            findings.append(f"schema missing N5-2 review field: {required_text}")

    return findings


def check_python_contract(files: list[Path]) -> list[str]:
    findings: list[str] = []
    contract_text = "\n".join(path.read_text(encoding="utf-8") for path in files if path.suffix == ".py")
    for event_type in N5_EVENT_TYPES:
        if event_type not in contract_text:
            findings.append(f"python contract missing N5 event type: {event_type}")
    for event_type in ALLOWED_N4_INPUT_EVENT_TYPES:
        if event_type not in contract_text:
            findings.append(f"python contract missing N4 input event type: {event_type}")
    for key in N5_COMMON_PAYLOAD_KEYS:
        if key not in contract_text:
            findings.append(f"python contract missing N5 payload key: {key}")
    for required_text in (
        "would_pull_market_data",
        "consumer_name",
        "partition_key",
        "watermark",
        "would_insert_common_event_inbox",
        "would_update_common_event_inbox",
        "would_update_consumer_checkpoint",
        "would_write_user_projection",
        "would_write_voice",
        "would_write_sim",
        "would_submit_real_trade",
        "minute_context_status",
        "action_fact_written",
        "source_trigger_match_id",
        "source_condition_run_id",
        "source_market_data_run_id",
        "source_market_trace",
        "action_key",
        "event_schema_version",
    ):
        if required_text not in contract_text:
            findings.append(f"python contract missing N5 dry-run boundary field: {required_text}")
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
