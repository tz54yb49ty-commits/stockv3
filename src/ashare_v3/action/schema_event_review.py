"""N5-2 action schema and event contract review.

The review is static. It reads N5 schema/code artifacts and writes reports
only; it does not execute migrations, consume N4 outbox rows, update
inbox/checkpoint state, write N5 facts/outbox rows, enter N6, or call trading
interfaces.
"""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from ashare_v3.action.dry_run import (
    ALLOWED_N4_INPUT_EVENT_TYPES,
    BUY_SIGNAL_TYPES,
    SELL_SIGNAL_TYPES,
)
from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.events.models import N5_COMMON_PAYLOAD_KEYS, N5_EVENT_TYPES


DEFAULT_N5_2_SCHEMA_PATH = "sql/011_action_layer_schema.sql"
DEFAULT_N5_2_JSON_REPORT_PATH = "docs/N5_2_action_schema_event_contract_review.json"
DEFAULT_N5_2_MD_REPORT_PATH = "docs/N5_2_ACTION_SCHEMA_EVENT_CONTRACT_REVIEW.md"

PROJECT_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_N5_SCHEMA_TABLES = (
    "common_action_run",
    "common_action_quality_item",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "common_action_event",
    "common_position_state",
    "common_position_event",
)

REQUIRED_ACTION_FACT_COLUMNS = (
    "run_id",
    "source_trigger_run_id",
    "source_trigger_event_id",
    "source_trigger_event_type",
    "event_schema_version",
    "source_trigger_match_id",
    "trigger_state_id",
    "source_trigger_state_id",
    "source_condition_run_id",
    "source_market_data_run_id",
    "source_market_trace",
    "asset_kind",
    "identity_key",
    "direction",
    "signal_type",
    "condition_key",
    "original_condition_key",
    "trigger_period",
    "trigger_mark_candidate",
    "action_mark",
    "action_state",
    "confirmation_status",
    "tracking_until",
    "last_checked_minute_label",
    "trace_json",
    "action_policy",
    "action_type",
    "lane",
    "decision_status",
    "data_quality_status",
    "closed_minute_required",
    "closed_minute_verified",
    "minute_context_status",
    "action_bucket",
    "action_key",
    "dedup_key",
    "source_payload_json",
)

REQUIRED_ACTION_EVENT_COLUMNS = (
    "event_id",
    "event_schema_version",
    "run_id",
    "source_trigger_run_id",
    "source_trigger_event_id",
    "source_trigger_match_id",
    "source_trigger_state_id",
    "source_condition_run_id",
    "source_market_data_run_id",
    "source_market_trace",
    "source_action_fact_table",
    "source_action_fact_id",
    "asset_kind",
    "identity_key",
    "direction",
    "signal_type",
    "condition_key",
    "original_condition_key",
    "trigger_period",
    "trigger_mark_candidate",
    "action_mark",
    "action_state",
    "confirmation_status",
    "tracking_until",
    "last_checked_minute_label",
    "trace_json",
    "action_policy",
    "event_type",
    "action_type",
    "lane",
    "data_quality_status",
    "action_key",
    "dedup_key",
    "partition_key",
    "payload_json",
)

REQUIRED_POSITION_EVENT_COLUMNS = (
    "event_id",
    "event_schema_version",
    "run_id",
    "source_trigger_event_id",
    "source_trigger_match_id",
    "source_condition_run_id",
    "source_market_data_run_id",
    "source_market_trace",
    "source_action_event_id",
    "asset_kind",
    "identity_key",
    "direction",
    "signal_type",
    "condition_key",
    "action_type",
    "lane",
    "position_event_type",
    "data_quality_status",
    "action_key",
    "dedup_key",
    "payload_json",
)

REQUIRED_PAYLOAD_KEYS = tuple(N5_COMMON_PAYLOAD_KEYS) + (
    "source_market_data_run_id",
    "source_market_trace",
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
FORBIDDEN_MARKET_DATA_ADAPTER_TERMS = ("moot" + "dx", "tus" + "hare")
FORBIDDEN_MARKET_DATA_ADAPTER_PATTERN = re.compile(
    r"\b(?:" + "|".join(FORBIDDEN_MARKET_DATA_ADAPTER_TERMS) + r")\b",
    re.IGNORECASE,
)
FORBIDDEN_REAL_TRADE_TERMS = (
    "broker" + "_client",
    "place" + "_order",
    "send" + "_order",
    "submit" + "_order",
    "order" + "_submit",
    "trade" + "_api",
    "real" + "_trade_client",
    "xt" + "quant",
    "c" + "tp",
)
FORBIDDEN_REAL_TRADE_PATTERN = re.compile(
    r"\b(?:" + "|".join(FORBIDDEN_REAL_TRADE_TERMS) + r")\b",
    re.IGNORECASE,
)


def run_n5_schema_event_contract_review(
    *,
    schema_path: str = DEFAULT_N5_2_SCHEMA_PATH,
    json_report_path: str = DEFAULT_N5_2_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_2_MD_REPORT_PATH,
) -> dict[str, Any]:
    schema_file = PROJECT_ROOT / schema_path
    schema_text = schema_file.read_text(encoding="utf-8")
    scan_files = default_scan_files()
    report = build_n5_schema_event_contract_review(
        schema_text=schema_text,
        schema_path=schema_path,
        scan_files=scan_files,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_n5_schema_event_contract_review(report))
    return report


def build_n5_schema_event_contract_review(
    *,
    schema_text: str,
    schema_path: str = DEFAULT_N5_2_SCHEMA_PATH,
    scan_files: Iterable[Path] | None = None,
    json_report_path: str = DEFAULT_N5_2_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_2_MD_REPORT_PATH,
) -> dict[str, Any]:
    executable_schema = strip_line_comments(schema_text)
    created_tables = extract_create_table_names(executable_schema)
    missing_tables = [
        table_name for table_name in REQUIRED_N5_SCHEMA_TABLES if table_name not in created_tables
    ]
    missing_columns = missing_required_columns(executable_schema)
    required_literals = missing_required_literals(executable_schema)
    forbidden_findings = scan_forbidden_contracts(list(scan_files or []), schema_text)
    quality_items = build_quality_items(
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        missing_required_literals=required_literals,
        forbidden_findings=forbidden_findings,
        schema_text=executable_schema,
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": "N5-2",
        "layer_role": "N5_action",
        "mode": "action_schema_event_contract_review",
        "execution_mode": "static_review_no_db_no_migration",
        "schema_path": schema_path,
        "schema_hash": sha256(schema_text.encode("utf-8")).hexdigest(),
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "schema_review": {
            "created_tables": created_tables,
            "required_tables": list(REQUIRED_N5_SCHEMA_TABLES),
            "missing_tables": missing_tables,
            "missing_columns_by_table": missing_columns,
            "missing_required_literals": required_literals,
            "physical_action_fact_tables": ["stock_action_fact", "index_action_fact", "board_action_fact"],
            "dedup_contract": "UNIQUE(run_id, dedup_key) and UNIQUE(run_id, action_key)",
        },
        "event_contract": build_event_contract_summary(),
        "boundary_review": {
            "forbidden_findings": forbidden_findings,
            "n6_outputs_forbidden": ["User*", "Voice*", "Sim*"],
            "n5_output_event_types": list(N5_EVENT_TYPES),
            "input_event_types": list(ALLOWED_N4_INPUT_EVENT_TYPES),
        },
        "side_effects": {
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "action_fact_written": False,
            "action_event_written": False,
            "common_event_outbox_written": False,
            "common_event_inbox_updated": False,
            "consumer_checkpoint_updated": False,
            "real_n4_outbox_consumed": False,
            "market_data_pulled": False,
            "n6_user_layer_touched": False,
            "voice_touched": False,
            "sim_touched": False,
            "real_trade_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "passed": severity_counts["P0"] == 0,
    }


def build_event_contract_summary() -> dict[str, Any]:
    return {
        "input_event_types": list(ALLOWED_N4_INPUT_EVENT_TYPES),
        "output_event_types": list(N5_EVENT_TYPES),
        "payload_required_keys": list(REQUIRED_PAYLOAD_KEYS),
        "market_trace_rule": "payload must include source_market_data_run_id or source_market_trace",
        "action_key_rule": "action_key is stable and paired with dedup_key for idempotent N5 output",
        "buy_signal_types": list(BUY_SIGNAL_TYPES),
        "sell_signal_types": list(SELL_SIGNAL_TYPES),
        "normalization": {
            "B_BUY": "canonical buy runtime signal",
            "S_SELL": "canonical sell runtime signal",
            "BUY_HINT": "condition_key/original_condition_key trace only; not an N5 output type",
            "SELL_HINT": "condition_key/original_condition_key trace only; not an N5 output type",
            "B_BUY_30M_VOL": "deprecated runtime signal; represented by action_mark=30m_volume after N5 confirmation",
            "S_SELL_30M_SHRINK": "deprecated runtime signal; represented by action_mark=30m_shrink after N5 confirmation",
        },
        "n6_decision_boundary": [
            "whether to present a hint",
            "whether to speak voice",
            "whether to write mobile/card projection",
            "whether to enter sim shadow",
        ],
        "n5_forbidden_execution": [
            "no user projection",
            "no voice",
            "no sim",
            "no true trading interface",
        ],
    }


def default_scan_files() -> list[Path]:
    scan_roots = [
        PROJECT_ROOT / "src" / "ashare_v3" / "action",
        PROJECT_ROOT / "src" / "ashare_v3" / "events" / "models.py",
        PROJECT_ROOT / "scripts" / "plan_action_preflight_dry_run.py",
        PROJECT_ROOT / "scripts" / "plan_action_consumer_dry_run.py",
    ]
    files: list[Path] = []
    for root in scan_roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(path for path in root.rglob("*.py") if path.is_file()))
    return files


def build_quality_items(
    *,
    missing_tables: list[str],
    missing_columns: Mapping[str, list[str]],
    missing_required_literals: list[str],
    forbidden_findings: list[str],
    schema_text: str,
) -> list[dict[str, Any]]:
    all_signals = set(BUY_SIGNAL_TYPES) | set(SELL_SIGNAL_TYPES)
    signal_literals_present = all(signal in schema_text for signal in all_signals)
    action_fact_unique_keys_present = all(
        unique_key_present(schema_text, table_name, "UNIQUE(run_id, dedup_key)")
        and unique_key_present(schema_text, table_name, "UNIQUE(run_id, action_key)")
        for table_name in ("stock_action_fact", "index_action_fact", "board_action_fact")
    )
    return [
        quality_item(
            "P0",
            "passed" if not missing_tables else "failed",
            "n5_2_required_schema_tables_present",
            "N5-2 schema must include action run, quality, physical action fact, action event, and position tables",
            expected=",".join(REQUIRED_N5_SCHEMA_TABLES),
            actual="missing=" + ",".join(missing_tables),
        ),
        quality_item(
            "P0",
            "passed" if not missing_columns else "failed",
            "n5_2_required_schema_columns_present",
            "N5-2 schema must carry trace, action key, dedup, and event contract columns",
            expected="no missing columns",
            actual=json.dumps(missing_columns, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if not missing_required_literals else "failed",
            "n5_2_required_contract_literals_present",
            "N5-2 schema must explicitly declare input/output event and payload contract literals",
            expected="all required literals present",
            actual="missing=" + ",".join(missing_required_literals),
        ),
        quality_item(
            "P0",
            "passed" if action_fact_unique_keys_present else "failed",
            "n5_2_action_fact_idempotency_keys_present",
            "Each action fact table must provide run_id scoped action_key and dedup_key uniqueness",
            expected="UNIQUE(run_id, action_key) and UNIQUE(run_id, dedup_key)",
            actual="present" if action_fact_unique_keys_present else "missing",
        ),
        quality_item(
            "P0",
            "passed" if signal_literals_present else "failed",
            "n5_2_buy_sell_hint_signal_contract_preserved",
            "N5 runtime signal_type must preserve canonical B_BUY/S_SELL; BUY_HINT/SELL_HINT stay in trace fields",
            expected=",".join(sorted(all_signals)),
            actual="present" if signal_literals_present else "missing",
        ),
        quality_item(
            "P0",
            "passed" if "minute_context_status <> 'unclosed' OR decision_status <> 'candidate'" in schema_text else "failed",
            "n5_2_no_unclosed_minute_action_confirmation",
            "N5 schema must not allow candidate confirmation from unclosed minute context",
            expected="unclosed minute guard",
            actual="present" if "minute_context_status <> 'unclosed' OR decision_status <> 'candidate'" in schema_text else "missing",
        ),
        quality_item(
            "P0",
            "passed" if not forbidden_findings else "failed",
            "n5_2_forbidden_boundaries_clean",
            "N5-2 must not output User*/Voice*/Sim*, write N6 tables, write inbox/checkpoint, pull data, use *_runtime tables, or reference trading interfaces",
            expected="no forbidden findings",
            actual="; ".join(forbidden_findings),
        ),
        quality_item(
            "P2",
            "warning",
            "n5_2_schema_review_only_not_migrated",
            "N5-2 intentionally stops before migration review and execute",
            expected="no migration executed",
            actual="static review only",
        ),
    ]


def missing_required_literals(schema_text: str) -> list[str]:
    required_literals = (
        *ALLOWED_N4_INPUT_EVENT_TYPES,
        *N5_EVENT_TYPES,
        *REQUIRED_PAYLOAD_KEYS,
        "source_market_data_run_id IS NOT NULL OR source_market_trace",
        "market_data_pulled = false",
        "user_layer_touched = false",
        "voice_touched = false",
        "sim_touched = false",
        "real_trade_touched = false",
        "worker_started = false",
    )
    return [literal for literal in required_literals if literal not in schema_text]


def missing_required_columns(schema_text: str) -> dict[str, list[str]]:
    required_by_table: dict[str, tuple[str, ...]] = {
        "stock_action_fact": REQUIRED_ACTION_FACT_COLUMNS,
        "index_action_fact": REQUIRED_ACTION_FACT_COLUMNS,
        "board_action_fact": REQUIRED_ACTION_FACT_COLUMNS,
        "common_action_event": REQUIRED_ACTION_EVENT_COLUMNS,
        "common_position_event": REQUIRED_POSITION_EVENT_COLUMNS,
    }
    missing: dict[str, list[str]] = {}
    for table_name, required_columns in required_by_table.items():
        columns = set(extract_columns_for_table(schema_text, table_name))
        table_missing = [column for column in required_columns if column not in columns]
        if table_missing:
            missing[table_name] = table_missing
    return missing


def scan_forbidden_contracts(files: list[Path], schema_text: str) -> list[str]:
    findings = scan_forbidden_text("<schema>", schema_text)
    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else str(path)
        findings.extend(scan_forbidden_text(rel, text, include_inbox_checkpoint_writes=False))
    return findings


def scan_forbidden_text(
    label: str,
    text: str,
    *,
    include_inbox_checkpoint_writes: bool = True,
) -> list[str]:
    findings: list[str] = []
    for match in FORBIDDEN_PREFIX_EVENT_LITERAL.finditer(text):
        findings.append(f"{label}: forbidden N5 prefixed event literal {match.group(0)}")
    if FORBIDDEN_N6_TABLE_WRITE_PATTERN.search(text):
        findings.append(f"{label}: N5 contract writes a user/voice/sim table")
    if include_inbox_checkpoint_writes and FORBIDDEN_CHECKPOINT_WRITE_PATTERN.search(text):
        findings.append(f"{label}: N5 contract updates common_event_inbox or checkpoint")
    if CREATE_RUNTIME_TABLE_PATTERN.search(text):
        findings.append(f"{label}: table name uses *_runtime suffix")
    if FORBIDDEN_MARKET_DATA_ADAPTER_PATTERN.search(text):
        findings.append(f"{label}: N5 contract directly references an external market-data adapter")
    if FORBIDDEN_REAL_TRADE_PATTERN.search(text):
        findings.append(f"{label}: N5 contract references a true trading interface")
    return findings


def extract_create_table_names(sql_text: str) -> list[str]:
    return re.findall(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        sql_text,
        flags=re.IGNORECASE,
    )


def extract_columns_for_table(sql_text: str, table_name: str) -> list[str]:
    pattern = re.compile(
        rf"\bCREATE\s+TABLE\s+{re.escape(table_name)}\s*\((.*?)\n\s*\);",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql_text)
    if not match:
        return []
    columns: list[str] = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip().rstrip(",")
        if not line:
            continue
        first_token = line.split()[0]
        if first_token.upper() in {"CHECK", "UNIQUE", "PRIMARY", "FOREIGN", "CONSTRAINT"}:
            continue
        columns.append(first_token)
    return columns


def unique_key_present(sql_text: str, table_name: str, unique_text: str) -> bool:
    pattern = re.compile(
        rf"\bCREATE\s+TABLE\s+{re.escape(table_name)}\s*\((.*?)\n\);",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql_text)
    return bool(match and unique_text in match.group(1))


def strip_line_comments(sql_text: str) -> str:
    return "\n".join(line for line in sql_text.splitlines() if not line.strip().startswith("--"))


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = PROJECT_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = PROJECT_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def format_n5_schema_event_contract_review(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    schema = report["schema_review"]
    contract = report["event_contract"]
    side_effects = report["side_effects"]
    return "\n".join(
        [
            "# N5-2 Action Schema / Event Contract Review",
            "",
            "## Summary",
            "",
            f"- stage: {report['stage']}",
            f"- layer_role: {report['layer_role']}",
            f"- execution_mode: {report['execution_mode']}",
            f"- schema_path: {report['schema_path']}",
            f"- schema_hash: {report['schema_hash']}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            f"- passed: {report['passed']}",
            "",
            "## Schema Contract",
            "",
            f"- required_tables: {schema['required_tables']}",
            f"- created_tables: {schema['created_tables']}",
            f"- missing_tables: {schema['missing_tables']}",
            f"- missing_columns_by_table: {schema['missing_columns_by_table']}",
            f"- missing_required_literals: {schema['missing_required_literals']}",
            f"- physical_action_fact_tables: {schema['physical_action_fact_tables']}",
            f"- dedup_contract: {schema['dedup_contract']}",
            "",
            "## Event Contract",
            "",
            f"- input_event_types: {contract['input_event_types']}",
            f"- output_event_types: {contract['output_event_types']}",
            f"- payload_required_keys: {contract['payload_required_keys']}",
            f"- market_trace_rule: {contract['market_trace_rule']}",
            f"- action_key_rule: {contract['action_key_rule']}",
            f"- buy_signal_types: {contract['buy_signal_types']}",
            f"- sell_signal_types: {contract['sell_signal_types']}",
            f"- normalization: {contract['normalization']}",
            "",
            "## N6 Boundary",
            "",
            f"- n6_decision_boundary: {contract['n6_decision_boundary']}",
            f"- n5_forbidden_execution: {contract['n5_forbidden_execution']}",
            "",
            "## Boundary Confirmation",
            "",
            f"- will_execute_sql: {side_effects['will_execute_sql']}",
            f"- migration_executed: {side_effects['migration_executed']}",
            f"- writes_performed: {side_effects['writes_performed']}",
            f"- action_fact_written: {side_effects['action_fact_written']}",
            f"- action_event_written: {side_effects['action_event_written']}",
            f"- common_event_outbox_written: {side_effects['common_event_outbox_written']}",
            f"- common_event_inbox_updated: {side_effects['common_event_inbox_updated']}",
            f"- consumer_checkpoint_updated: {side_effects['consumer_checkpoint_updated']}",
            f"- real_n4_outbox_consumed: {side_effects['real_n4_outbox_consumed']}",
            f"- market_data_pulled: {side_effects['market_data_pulled']}",
            f"- n6_user_layer_touched: {side_effects['n6_user_layer_touched']}",
            f"- voice_touched: {side_effects['voice_touched']}",
            f"- sim_touched: {side_effects['sim_touched']}",
            f"- real_trade_touched: {side_effects['real_trade_touched']}",
            f"- worker_started: {side_effects['worker_started']}",
            f"- old_system_touched: {side_effects['old_system_touched']}",
            "",
            "## Notes",
            "",
            "- N5-2 is schema and event contract review only.",
            "- No migration, N4 outbox consumption, inbox/checkpoint update, N5 outbox write, N6 write, worker, market pull, voice, sim, or true trade was executed.",
        ]
    )
