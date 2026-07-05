#!/usr/bin/env python3
"""Static N3-1 event contract checker.

This script does not connect to PostgreSQL and does not execute migrations.
It only scans schema/code contract artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ashare_v3.events.models import N3_EVENT_TYPES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "sql" / "008_common_event_infra_schema.sql"
SCAN_PATHS = [
    PROJECT_ROOT / "sql",
    PROJECT_ROOT / "src" / "ashare_v3" / "events",
    PROJECT_ROOT / "src" / "ashare_v3" / "market",
]
FORBIDDEN_RUNTIME_TABLES = (
    "stock_minute_bar_1m_runtime",
    "index_minute_bar_1m_runtime",
    "board_minute_bar_1m_runtime",
    "stock_snapshot_runtime",
    "index_snapshot_runtime",
    "board_snapshot_runtime",
)
REQUIRED_OUTBOX_COLUMNS = (
    "event_id",
    "event_type",
    "event_schema_version",
    "trade_date",
    "asset_kind",
    "identity_key",
    "event_time",
    "source_layer",
    "source_run_id",
    "dedup_key",
    "partition_key",
    "payload_json",
    "created_at",
)
REQUIRED_PAYLOAD_KEYS = (
    "subscription_id",
    "pull_plan_id",
    "run_id",
    "source_adapter",
    "data_quality_status",
)
REQUIRED_FACT_WRITER_FUNCTIONS = (
    "write_market_snapshot_with_event",
    "write_minute_bar_closed_with_event",
    "write_market_quality_with_event",
)
REQUIRED_MINUTE_BAR_CLOSED_V2_TOKENS = (
    "closed_30m_summary_id",
    "source_minute_refs",
    "c2_run_id",
    "summary_id",
    "bucket_id",
    "event_schema_version",
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


def scan_forbidden_runtime_tables(files: list[Path]) -> list[str]:
    findings: list[str] = []
    create_runtime_pattern = re.compile(r"\bCREATE\s+TABLE\s+[^;\n]*_runtime\b", re.IGNORECASE)
    for path in files:
        text = path.read_text(encoding="utf-8")
        for name in FORBIDDEN_RUNTIME_TABLES:
            if name in text:
                findings.append(f"{path}: forbidden runtime table name {name}")
        if create_runtime_pattern.search(text):
            findings.append(f"{path}: CREATE TABLE uses *_runtime")
    return findings


def scan_forbidden_user_events(files: list[Path]) -> list[str]:
    findings: list[str] = []
    event_name_pattern = re.compile(r"['\"]User[A-Za-z0-9_]+['\"]")
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in event_name_pattern.finditer(text):
            findings.append(f"{path}: forbidden N3 User* event literal {match.group(0)}")
    return findings


def check_schema_contract(schema_text: str) -> list[str]:
    findings: list[str] = []
    for table_name in (
        "common_event_ledger",
        "common_event_outbox",
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "common_event_delivery_attempt",
    ):
        if f"CREATE TABLE {table_name}" not in schema_text:
            findings.append(f"missing table: {table_name}")

    for column in REQUIRED_OUTBOX_COLUMNS:
        if column not in schema_text:
            findings.append(f"common_event_outbox missing column text: {column}")

    for constraint in ("uq_common_event_outbox_event_id", "uq_common_event_outbox_dedup"):
        if constraint not in schema_text:
            findings.append(f"common_event_outbox missing unique constraint: {constraint}")

    for event_type in N3_EVENT_TYPES:
        if event_type not in schema_text:
            findings.append(f"schema missing N3 event type: {event_type}")

    return findings


def check_python_contract() -> list[str]:
    findings: list[str] = []
    factory_text = (PROJECT_ROOT / "src" / "ashare_v3" / "market" / "event_factory.py").read_text(
        encoding="utf-8"
    )
    models_text = (PROJECT_ROOT / "src" / "ashare_v3" / "events" / "models.py").read_text(encoding="utf-8")
    ids_text = (PROJECT_ROOT / "src" / "ashare_v3" / "events" / "ids.py").read_text(encoding="utf-8")
    fact_writer_text = (PROJECT_ROOT / "src" / "ashare_v3" / "market" / "fact_writer.py").read_text(
        encoding="utf-8"
    )
    contract_text = factory_text + "\n" + models_text + "\n" + ids_text + "\n" + fact_writer_text
    for key in REQUIRED_PAYLOAD_KEYS:
        if key not in contract_text:
            findings.append(f"N3 event factory missing payload trace key: {key}")
    for token in REQUIRED_MINUTE_BAR_CLOSED_V2_TOKENS:
        if token not in contract_text:
            findings.append(f"N3 MinuteBarClosed v2 contract missing token: {token}")
    for function_name in REQUIRED_FACT_WRITER_FUNCTIONS:
        if function_name not in fact_writer_text:
            findings.append(f"N3 fact writer missing function: {function_name}")
    return findings


def run_check() -> dict[str, Any]:
    files = iter_files(SCAN_PATHS)
    findings: list[str] = []
    if not SCHEMA_PATH.exists():
        findings.append(f"missing schema: {SCHEMA_PATH}")
        schema_text = ""
    else:
        schema_text = SCHEMA_PATH.read_text(encoding="utf-8")

    findings.extend(scan_forbidden_runtime_tables(files))
    findings.extend(scan_forbidden_user_events(files))
    findings.extend(check_schema_contract(schema_text))
    findings.extend(check_python_contract())

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
