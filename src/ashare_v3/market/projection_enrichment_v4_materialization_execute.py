"""Execute N3 projection enrichment v4 row-level materialization.

The runner is intentionally conservative: it writes only the scoped market-data
run row, quality rows, and the three physical projection enrichment v4 metric
tables. It never writes event infra and never enters N4/N5/N6.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb


try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_PAYLOAD_PATH = "docs/N3_projection_enrichment_v4_20260603_row_payload.json"
DEFAULT_CONTRACT_PATH = "docs/N3_projection_enrichment_v4_20260603_materialization_contract.json"
DEFAULT_REPORT_PATH = "docs/N3_projection_enrichment_v4_20260603_materialization_execute_report.json"

SCRIPT_PATH = "scripts/run_n3_projection_enrichment_v4_materialization_execute.py"
EXECUTE_COMMAND = (
    "PYTHONPATH=src:scripts python3 scripts/run_n3_projection_enrichment_v4_materialization_execute.py "
    "--payload-path docs/N3_projection_enrichment_v4_20260603_row_payload.json "
    "--contract-path docs/N3_projection_enrichment_v4_20260603_materialization_contract.json "
    "--execute --user-confirmed"
)

TARGET_RUN_ID = (
    "projection_enrichment_v4_20260603_until_1500__"
    "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
)
DEFAULT_MATERIALIZATION_MODE = "create_projection_enrichment_run"
ATTACH_EXISTING_PROJECTION_RUN_MODE = "attach_to_existing_projection_run"
SUPPORTED_MATERIALIZATION_MODES = {
    DEFAULT_MATERIALIZATION_MODE,
    ATTACH_EXISTING_PROJECTION_RUN_MODE,
}
LEGACY_EXPECTED_COMPLETE_LINEAGE_ROWS = 5218
LEGACY_EXPECTED_BJ_QUALITY_VISIBLE_ROWS_BY_IDENTITY = {"index:BJ:899050": 2, "index:BJ:899601": 2}

ASSET_KINDS = ("stock", "index", "board")
MATERIALIZATION_TABLES = {
    "stock": "stock_projection_enrichment_v4_metric",
    "index": "index_projection_enrichment_v4_metric",
    "board": "board_projection_enrichment_v4_metric",
}
ALLOWED_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_projection_enrichment_v4_metric",
    "index_projection_enrichment_v4_metric",
    "board_projection_enrichment_v4_metric",
]
PROJECTION_ENRICHMENT_V4_WRITE_TABLES = [
    "stock_projection_enrichment_v4_metric",
    "index_projection_enrichment_v4_metric",
    "board_projection_enrichment_v4_metric",
]
FORBIDDEN_WRITE_SCOPES = [
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "stock/index/board_action_confirmation_projection_metric",
    "stock/index/board_realtime_projection_metric",
    "stock/index/board_realtime_daily_snapshot",
    "stock/index/board_minute_bar_1m",
    "N4/N5/N6",
    "worker",
    "old system",
    "real trading",
]

CANONICAL_SIGNAL_TYPES = {"BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT"}
SIGNAL_NORMALIZATION = {
    "B_BUY": "BUY",
    "B_BUY_30M_VOL": "BUY",
    "S_SELL": "SELL",
    "S_SELL_30M_SHRINK": "SELL",
}


@dataclass(frozen=True)
class PayloadValidation:
    valid: bool
    target_run_id: str | None
    materialization_mode: str
    spec_version: str | None
    policy_hash: str | None
    row_count: int
    row_count_by_asset_kind: dict[str, int]
    complete_lineage_rows: int
    bj_quality_visible_rows: int
    bj_quality_visible_rows_by_identity: dict[str, int]
    trigger_amount_chain_pass_rows: int
    projection_30m_coverage_rows: int
    source_freshness_distribution: dict[str, int]
    current_metric_quality_status_distribution: dict[str, int]
    metric_ready_distribution: dict[str, int]
    blocked_reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "target_run_id": self.target_run_id,
            "materialization_mode": self.materialization_mode,
            "spec_version": self.spec_version,
            "policy_hash": self.policy_hash,
            "row_count": self.row_count,
            "row_count_by_asset_kind": self.row_count_by_asset_kind,
            "complete_lineage_rows": self.complete_lineage_rows,
            "bj_quality_visible_rows": self.bj_quality_visible_rows,
            "bj_quality_visible_rows_by_identity": self.bj_quality_visible_rows_by_identity,
            "trigger_amount_chain_pass_rows": self.trigger_amount_chain_pass_rows,
            "projection_30m_coverage_rows": self.projection_30m_coverage_rows,
            "source_freshness_distribution": self.source_freshness_distribution,
            "current_metric_quality_status_distribution": self.current_metric_quality_status_distribution,
            "metric_ready_distribution": self.metric_ready_distribution,
            "blocked_reasons": self.blocked_reasons,
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute N3 projection enrichment v4 row-level materialization.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--payload-path", default=DEFAULT_PAYLOAD_PATH)
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--operator", default="codex")
    parser.add_argument("--confirmation-note", default="")
    parser.add_argument("--report-path", default=DEFAULT_REPORT_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = run(args)
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary_for_stdout(report), ensure_ascii=False, indent=2, default=str))
    return 0 if report["execute_result"] == "EXECUTED" else 2


def run(
    args: argparse.Namespace,
    *,
    connect: Callable[..., Any] = audited_n3_market_execute_connect,
) -> dict[str, Any]:
    flag_gate = validate_execute_flags(execute=bool(args.execute), user_confirmed=bool(args.user_confirmed))
    if flag_gate["gate_result"] != "PASS":
        return blocked_report(args, flag_gate["blocked_reasons"], blocked_before_database=True)

    contract = read_json(Path(args.contract_path))
    payload = read_json(Path(args.payload_path))
    rows = payload_rows(payload)
    validation = validate_payload(payload)
    if not validation["valid"]:
        return blocked_report(
            args,
            validation["blocked_reasons"],
            contract=contract,
            payload_validation=validation,
            blocked_before_database=True,
        )

    contract_blockers = validate_contract(contract, validation)
    if contract_blockers:
        return blocked_report(
            args,
            contract_blockers,
            contract=contract,
            payload_validation=validation,
            blocked_before_database=True,
        )

    with connect(args.dsn, row_factory=dict_row) as conn:
        preflight = execute_preflight(conn, contract, validation)
        if preflight["blocked_reasons"]:
            return blocked_report(
                args,
                preflight["blocked_reasons"],
                contract=contract,
                payload_validation=validation,
                preflight=preflight,
                blocked_before_database=False,
            )

        with conn.transaction():
            if validation["materialization_mode"] != ATTACH_EXISTING_PROJECTION_RUN_MODE:
                insert_run_row(conn, contract, payload, validation, preflight, args)
                insert_quality_rows(conn, contract, validation, args)
            insert_payload_rows(conn, rows)

    return {
        "execute_result": "EXECUTED",
        "layer_role": "N3_market_data",
        "materialization_mode": validation["materialization_mode"],
        "target_run_id": validation["target_run_id"],
        "run_status": "passed",
        "row_counts": validation["row_count_by_asset_kind"],
        "complete_lineage_rows": validation["complete_lineage_rows"],
        "bj_quality_visible_rows": validation["bj_quality_visible_rows"],
        "bj_quality_visible_rows_by_identity": validation["bj_quality_visible_rows_by_identity"],
        "quality": {"P0": 0, "P1": 1 if validation["bj_quality_visible_rows"] else 0, "P2": 0},
        "allowed_write_tables": allowed_write_tables_for_mode(str(validation["materialization_mode"])),
        "forbidden_write_scopes": FORBIDDEN_WRITE_SCOPES,
        "writes_performed": True,
        "common_event_outbox_written": False,
        "common_event_inbox_written": False,
        "common_event_consumer_checkpoint_written": False,
        "downstream_layers_touched": False,
        "worker_started": False,
        "rollback_sql_path": contract.get("rollback_sql_path"),
        "report_path": args.report_path,
    }


def validate_execute_flags(*, execute: bool, user_confirmed: bool) -> dict[str, Any]:
    blocked: list[str] = []
    if not execute:
        blocked.append("missing_execute_flag")
    if not user_confirmed:
        blocked.append("missing_user_confirmed_flag")
    return {"gate_result": "PASS" if not blocked else "BLOCKED", "blocked_reasons": blocked}


def validate_contract(contract: Mapping[str, Any], validation: Mapping[str, Any]) -> list[str]:
    blocked: list[str] = []
    materialization_mode = str(validation.get("materialization_mode") or DEFAULT_MATERIALIZATION_MODE)
    if contract.get("target_run_id") != validation["target_run_id"]:
        blocked.append("contract_target_run_id_mismatch")
    if int(contract.get("expected_rows") or 0) != validation["row_count"]:
        blocked.append("contract_expected_rows_mismatch")
    contract_mode = contract.get("materialization_mode")
    if contract_mode and str(contract_mode) != materialization_mode:
        blocked.append("contract_materialization_mode_mismatch")
    if (
        contract.get("allow_attach_with_payload_only_event_refs") is True
        and materialization_mode != ATTACH_EXISTING_PROJECTION_RUN_MODE
    ):
        blocked.append("contract_payload_only_event_ref_opt_in_requires_attach_mode")
    contract_write_tables = list(contract.get("future_execute_allowed_write_tables") or [])
    accepted_write_scopes = [
        ALLOWED_WRITE_TABLES,
        allowed_write_tables_for_mode(materialization_mode),
    ]
    if contract_write_tables not in accepted_write_scopes:
        blocked.append("contract_allowed_write_tables_mismatch")
    forbidden_writes = set(contract.get("forbidden_writes") or [])
    for forbidden in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint", "N4/N5/N6", "worker"):
        if forbidden not in forbidden_writes:
            blocked.append(f"contract_missing_forbidden_scope:{forbidden}")
    return blocked


def validate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload_rows(payload)
    target_run_id = payload.get("target_run_id")
    materialization_mode = str(payload.get("materialization_mode") or DEFAULT_MATERIALIZATION_MODE)
    row_count = len(rows)
    row_count_by_asset_kind = count_payload_rows(rows)
    complete_lineage_rows = sum(1 for row in rows if row.get("metric_ready") is True)
    bj_rows = [
        row
        for row in rows
        if row.get("identity_key") in {"index:BJ:899050", "index:BJ:899601"}
    ]
    bj_by_identity = Counter(str(row.get("identity_key")) for row in bj_rows)
    trigger_amount_chain_pass_rows = sum(
        1 for row in rows if isinstance(row.get("trigger_amount_chain_pass"), Mapping) and row["trigger_amount_chain_pass"].get("ready") is True
    )
    projection_30m_coverage_rows = sum(
        1
        for row in rows
        if row.get("projection_period") == "30m" and row.get("projection_30m_type") not in (None, "unknown")
    )
    freshness_distribution = Counter(str(row.get("source_freshness_status") or "unknown") for row in rows)
    metric_quality_distribution = Counter(str(row.get("current_metric_quality_status") or "unknown") for row in rows)
    metric_ready_distribution = Counter("ready" if row.get("metric_ready") else "not_ready" for row in rows)
    expected_complete_lineage_rows = payload.get("expected_complete_lineage_rows")
    if expected_complete_lineage_rows is None and target_run_id == TARGET_RUN_ID:
        expected_complete_lineage_rows = LEGACY_EXPECTED_COMPLETE_LINEAGE_ROWS
    expected_bj_rows_by_identity = payload.get("expected_bj_quality_visible_rows_by_identity")
    if expected_bj_rows_by_identity is None and target_run_id == TARGET_RUN_ID:
        expected_bj_rows_by_identity = LEGACY_EXPECTED_BJ_QUALITY_VISIBLE_ROWS_BY_IDENTITY
    expected_bj_row_keys = [str(value) for value in payload.get("expected_bj_quality_visible_row_keys") or []]
    actual_bj_row_keys = [bj_quality_visible_row_key(row) for row in bj_rows]
    expected_source_trigger_context_run_id = payload.get("expected_source_trigger_context_run_id")

    blocked: list[str] = []
    if payload.get("artifact_type") != "N3_projection_enrichment_v4_row_level_payload":
        blocked.append("payload_artifact_type_mismatch")
    if not target_run_id:
        blocked.append("payload_target_run_id_missing")
    if materialization_mode not in SUPPORTED_MATERIALIZATION_MODES:
        blocked.append("payload_materialization_mode_unsupported")
    expected_target_run_id = payload.get("expected_target_run_id")
    if expected_target_run_id and target_run_id != expected_target_run_id:
        blocked.append("payload_target_run_id_mismatch")
    if int(payload.get("expected_rows") or 0) != row_count:
        blocked.append("payload_expected_rows_mismatch")
    if expected_complete_lineage_rows is not None and complete_lineage_rows != int(expected_complete_lineage_rows):
        blocked.append("payload_complete_lineage_mismatch")
    if expected_bj_rows_by_identity is not None and dict(bj_by_identity) != dict(expected_bj_rows_by_identity):
        blocked.append("payload_bj_quality_visible_mismatch")
    if expected_bj_row_keys and sorted(actual_bj_row_keys) != sorted(expected_bj_row_keys):
        blocked.append("payload_bj_quality_visible_row_key_mismatch")
    for row in bj_rows:
        quality_visible = row.get("quality_visible")
        if not isinstance(quality_visible, Mapping) or quality_visible.get("status") != "missing" or quality_visible.get("severity") != "P1":
            blocked.append("payload_bj_quality_not_visible")
            break
    if expected_bj_row_keys:
        expected_bj_row_key_set = set(expected_bj_row_keys)
        if any(
            bj_quality_visible_row_key(row) in expected_bj_row_key_set
            and not is_declared_bj_quality_visible_proof(row, expected_source_trigger_context_run_id)
            for row in bj_rows
        ):
            blocked.append("payload_bj_quality_visible_proof_malformed")

    result = PayloadValidation(
        valid=not blocked,
        target_run_id=str(target_run_id) if target_run_id else None,
        materialization_mode=materialization_mode,
        spec_version=str(payload.get("spec_version")) if payload.get("spec_version") else None,
        policy_hash=str(payload.get("policy_hash")) if payload.get("policy_hash") else None,
        row_count=row_count,
        row_count_by_asset_kind=row_count_by_asset_kind,
        complete_lineage_rows=complete_lineage_rows,
        bj_quality_visible_rows=sum(bj_by_identity.values()),
        bj_quality_visible_rows_by_identity=dict(bj_by_identity),
        trigger_amount_chain_pass_rows=trigger_amount_chain_pass_rows,
        projection_30m_coverage_rows=projection_30m_coverage_rows,
        source_freshness_distribution=dict(freshness_distribution),
        current_metric_quality_status_distribution=dict(metric_quality_distribution),
        metric_ready_distribution=dict(metric_ready_distribution),
        blocked_reasons=blocked,
    )
    return result.as_dict()


def execute_preflight(
    conn: psycopg.Connection[dict[str, Any]],
    contract: Mapping[str, Any],
    validation_dict: Mapping[str, Any],
) -> dict[str, Any]:
    target_run_id = str(validation_dict["target_run_id"])
    materialization_mode = str(validation_dict.get("materialization_mode") or DEFAULT_MATERIALIZATION_MODE)
    blocked: list[str] = []
    warnings: list[str] = []
    table_counts: dict[str, int] = {}

    for table in ALLOWED_WRITE_TABLES:
        column = "projection_run_id" if table.endswith("_projection_enrichment_v4_metric") else "run_id"
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS count FROM {table} WHERE {column} = %s", (target_run_id,))
            table_counts[table] = int(cur.fetchone()["count"])
    if materialization_mode == ATTACH_EXISTING_PROJECTION_RUN_MODE:
        if table_counts["common_market_data_run"] != 1:
            blocked.append("attach_existing_projection_run_not_found")
        projection_counts = [table_counts[table] for table in PROJECTION_ENRICHMENT_V4_WRITE_TABLES]
        if any(projection_counts):
            blocked.append("scoped_projection_enrichment_v4_baseline_nonzero")
    elif any(table_counts.values()):
        blocked.append("scoped_baseline_nonzero")

    source_status = fetch_source_status(conn, contract)
    for source_name, status in source_status.items():
        if status not in {"passed", "passed_active"}:
            blocked.append(f"source_run_not_passed:{source_name}")

    event_refs = count_event_refs(conn, target_run_id)
    event_ref_blockers, event_ref_warnings = event_ref_gate_result(
        event_refs,
        materialization_mode=materialization_mode,
        allow_attach_with_payload_only_event_refs=contract.get("allow_attach_with_payload_only_event_refs") is True,
    )
    blocked.extend(event_ref_blockers)
    warnings.extend(event_ref_warnings)
    if materialization_mode != ATTACH_EXISTING_PROJECTION_RUN_MODE and any(event_refs.values()):
        blocked.append("scoped_event_infra_refs_nonzero")

    return {
        "blocked_reasons": blocked,
        "warnings": warnings,
        "target_rows": table_counts,
        "source_status": source_status,
        "event_refs": event_refs,
    }


def fetch_source_status(
    conn: psycopg.Connection[dict[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, str | None]:
    source_inputs = contract.get("source_inputs") if isinstance(contract.get("source_inputs"), Mapping) else {}
    source_condition_run_id = source_inputs.get("source_condition_run_id") or contract.get("source_condition_run_id")
    source_ids = {
        "source_condition": source_condition_run_id,
        "snapshot": source_inputs.get("snapshot_run_id"),
        "today_minute": source_inputs.get("today_minute_run_id"),
        "previous_day_minute": source_inputs.get("previous_day_minute_run_id"),
    }
    result: dict[str, str | None] = {}
    with conn.cursor() as cur:
        if source_condition_run_id:
            cur.execute("SELECT status FROM common_condition_run WHERE run_id = %s", (source_condition_run_id,))
            row = cur.fetchone()
            result["source_condition"] = row["status"] if row else None
        for source_name in ("snapshot", "today_minute", "previous_day_minute"):
            run_id = source_ids[source_name]
            if not run_id:
                result[source_name] = None
                continue
            cur.execute("SELECT status FROM common_market_data_run WHERE run_id = %s", (run_id,))
            row = cur.fetchone()
            result[source_name] = row["status"] if row else None
    return result


def count_event_refs(conn: psycopg.Connection[dict[str, Any]], target_run_id: str) -> dict[str, int]:
    like = f"%{target_run_id}%"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS count FROM common_event_outbox WHERE source_run_id = %s",
            (target_run_id,),
        )
        direct_outbox = int(cur.fetchone()["count"])
        cur.execute(
            """
            SELECT count(*) AS count
            FROM common_event_outbox
            WHERE source_run_id IS DISTINCT FROM %s
              AND payload_json::text LIKE %s
            """,
            (target_run_id, like),
        )
        payload_only_outbox = int(cur.fetchone()["count"])
        cur.execute(
            "SELECT count(*) AS count FROM common_event_inbox WHERE source_run_id = %s",
            (target_run_id,),
        )
        direct_inbox = int(cur.fetchone()["count"])
        cur.execute(
            """
            SELECT count(*) AS count
            FROM common_event_inbox
            WHERE source_run_id IS DISTINCT FROM %s
              AND (payload_json::text LIKE %s OR raw_json::text LIKE %s)
            """,
            (target_run_id, like, like),
        )
        payload_only_inbox = int(cur.fetchone()["count"])
        cur.execute(
            """
            SELECT count(*) AS count
            FROM common_event_consumer_checkpoint
            WHERE checkpoint_payload::text LIKE %s OR last_event_id LIKE %s
            """,
            (like, like),
        )
        checkpoint = int(cur.fetchone()["count"])
    return {
        "direct_outbox_source_run_id_refs": direct_outbox,
        "direct_inbox_source_run_id_refs": direct_inbox,
        "payload_only_outbox_refs": payload_only_outbox,
        "payload_only_inbox_refs": payload_only_inbox,
        "checkpoint_refs": checkpoint,
    }


def event_ref_gate_result(
    event_refs: Mapping[str, int],
    *,
    materialization_mode: str,
    allow_attach_with_payload_only_event_refs: bool,
) -> tuple[list[str], list[str]]:
    if materialization_mode != ATTACH_EXISTING_PROJECTION_RUN_MODE:
        return [], []

    blocked: list[str] = []
    warnings: list[str] = []
    direct_outbox = int(event_refs.get("direct_outbox_source_run_id_refs") or 0)
    direct_inbox = int(event_refs.get("direct_inbox_source_run_id_refs") or 0)
    payload_only = int(event_refs.get("payload_only_outbox_refs") or 0) + int(
        event_refs.get("payload_only_inbox_refs") or 0
    )
    checkpoint = int(event_refs.get("checkpoint_refs") or event_refs.get("checkpoint") or 0)

    if direct_outbox:
        blocked.append("direct_outbox_source_run_id_refs_nonzero")
    if direct_inbox:
        blocked.append("direct_inbox_source_run_id_refs_nonzero")
    if checkpoint:
        blocked.append("checkpoint_event_refs_nonzero")
    if payload_only:
        if allow_attach_with_payload_only_event_refs:
            warnings.append("payload_only_event_refs_allowed_by_contract")
        else:
            blocked.append("payload_only_event_refs_require_contract_opt_in")
    return blocked, warnings


def insert_run_row(
    conn: psycopg.Connection[dict[str, Any]],
    contract: Mapping[str, Any],
    payload: Mapping[str, Any],
    validation_dict: Mapping[str, Any],
    preflight: Mapping[str, Any],
    args: argparse.Namespace,
) -> None:
    source_inputs = contract.get("source_inputs") if isinstance(contract.get("source_inputs"), Mapping) else {}
    source_condition_run_id = str(source_inputs.get("source_condition_run_id") or payload.get("source_condition_run_id"))
    snapshot_run_id = str(source_inputs.get("snapshot_run_id") or payload.get("snapshot_run_id"))
    source_trade_date, prev_trade_date, for_trade_date = source_market_dates(conn, snapshot_run_id)
    p1_count = 1 if int(validation_dict["bj_quality_visible_rows"]) else 0
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO common_market_data_run (
              run_id, source_condition_run_id, for_trade_date, source_trade_date, prev_trade_date,
              mode, status, p0_count, p1_count, p2_count,
              source_scope_row_count, candidate_row_count, subscription_row_count,
              subscription_object_count, dedup_ratio, generated_by,
              market_data_pulled, market_data_fact_written, downstream_layers_touched,
              worker_started, started_at, finished_at, raw_json
            )
            VALUES (
              %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s, %(source_trade_date)s, %(prev_trade_date)s,
              'execute', 'passed', 0, %(p1_count)s, 0,
              %(source_scope_row_count)s, %(candidate_row_count)s, 0,
              %(subscription_object_count)s, 1, %(generated_by)s,
              false, true, false,
              false, now(), now(), %(raw_json)s
            )
            """,
            {
                "run_id": validation_dict["target_run_id"],
                "source_condition_run_id": source_condition_run_id,
                "for_trade_date": for_trade_date,
                "source_trade_date": source_trade_date,
                "prev_trade_date": prev_trade_date,
                "p1_count": p1_count,
                "source_scope_row_count": validation_dict["row_count"],
                "candidate_row_count": validation_dict["row_count"],
                "subscription_object_count": validation_dict["row_count"],
                "generated_by": SCRIPT_PATH,
                "raw_json": Jsonb(
                    {
                        "metric_scope": "projection_enrichment_v4_row_level",
                        "spec_version": validation_dict["spec_version"],
                        "policy_hash": validation_dict["policy_hash"],
                        "payload_path": args.payload_path,
                        "contract_path": args.contract_path,
                        "report_path": args.report_path,
                        "allowed_write_tables": ALLOWED_WRITE_TABLES,
                        "forbidden_write_scopes": FORBIDDEN_WRITE_SCOPES,
                        "validation": dict(validation_dict),
                        "source_status": preflight.get("source_status"),
                        "event_refs": preflight.get("event_refs"),
                    }
                ),
            },
        )


def source_market_dates(conn: psycopg.Connection[dict[str, Any]], snapshot_run_id: str) -> tuple[str, str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_trade_date, prev_trade_date, for_trade_date
            FROM common_market_data_run
            WHERE run_id = %s
            """,
            (snapshot_run_id,),
        )
        row = cur.fetchone()
    if not row:
        for_trade_date = extract_trade_date(snapshot_run_id)
        source_trade_date = previous_date_from_condition_run(snapshot_run_id) or for_trade_date
        return source_trade_date, source_trade_date, for_trade_date
    return str(row["source_trade_date"]), str(row["prev_trade_date"]), str(row["for_trade_date"])


def previous_date_from_condition_run(run_id: str) -> str | None:
    match = re.search(r"source_(\d{8})", run_id)
    return match.group(1) if match else None


def extract_trade_date(value: str) -> str:
    match = re.search(r"20\d{6}", value)
    if not match:
        raise ValueError(f"cannot infer trade date from {value!r}")
    return match.group(0)


def insert_quality_rows(
    conn: psycopg.Connection[dict[str, Any]],
    contract: Mapping[str, Any],
    validation_dict: Mapping[str, Any],
    args: argparse.Namespace,
) -> None:
    source_inputs = contract.get("source_inputs") if isinstance(contract.get("source_inputs"), Mapping) else {}
    source_condition_run_id = str(source_inputs.get("source_condition_run_id") or "")
    snapshot_run_id = str(source_inputs.get("snapshot_run_id") or "")
    source_trade_date, _prev_trade_date, for_trade_date = source_market_dates(conn, snapshot_run_id)
    rows = [
        {
            "gate_code": "projection_enrichment_v4_row_count",
            "gate_name": "projection enrichment v4 row count",
            "severity": "P0",
            "status": "passed",
            "expected_value": str(validation_dict["row_count"]),
            "actual_value": str(validation_dict["row_count"]),
            "details": {
                "metric_scope": "projection_enrichment_v4_row_level",
                "row_counts": validation_dict["row_count_by_asset_kind"],
                "payload_path": args.payload_path,
            },
        },
        {
            "gate_code": "projection_enrichment_v4_bj_quality_visible",
            "gate_name": "BJ quality-visible missing minute lineage",
            "severity": "P1",
            "status": "warning",
            "expected_value": "BJ 899050/899601 rows visible as P1 missing",
            "actual_value": json.dumps(validation_dict["bj_quality_visible_rows_by_identity"], ensure_ascii=False, sort_keys=True),
            "details": {
                "metric_scope": "projection_enrichment_v4_row_level",
                "quality_visible_rows": validation_dict["bj_quality_visible_rows"],
                "by_identity": validation_dict["bj_quality_visible_rows_by_identity"],
                "silent_fallback_allowed": False,
            },
        },
        {
            "gate_code": "projection_enrichment_v4_no_event_infra",
            "gate_name": "no outbox inbox checkpoint writes",
            "severity": "P0",
            "status": "passed",
            "expected_value": "0",
            "actual_value": "0",
            "details": {
                "metric_scope": "projection_enrichment_v4_row_level",
                "common_event_outbox_written": False,
                "common_event_inbox_written": False,
                "common_event_consumer_checkpoint_written": False,
                "downstream_layers_touched": False,
                "worker_started": False,
            },
        },
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO common_market_data_quality_item (
              run_id, source_condition_run_id, for_trade_date, source_trade_date,
              data_domain, layer_scope, table_name, gate_code, gate_name,
              severity, status, expected_value, actual_value, details
            )
            VALUES (
              %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s, %(source_trade_date)s,
              'common', 'market_data_run', %(table_name)s, %(gate_code)s, %(gate_name)s,
              %(severity)s, %(status)s, %(expected_value)s, %(actual_value)s, %(details)s
            )
            """,
            [
                {
                    **row,
                    "run_id": validation_dict["target_run_id"],
                    "source_condition_run_id": source_condition_run_id,
                    "for_trade_date": for_trade_date,
                    "source_trade_date": source_trade_date,
                    "table_name": "common_market_data_run",
                    "details": Jsonb(row["details"]),
                }
                for row in rows
            ],
        )


def insert_payload_rows(conn: psycopg.Connection[dict[str, Any]], rows: Sequence[Mapping[str, Any]]) -> None:
    for asset_kind in ASSET_KINDS:
        table = MATERIALIZATION_TABLES[asset_kind]
        identity_column = f"{asset_kind}_identity_key"
        domain_rows = [row for row in rows if row.get("asset_kind") == asset_kind]
        if not domain_rows:
            continue
        with conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {table} (
                  projection_run_id, spec_version, policy_hash,
                  source_condition_run_id, source_subscription_run_id,
                  source_snapshot_run_id, source_today_minute_run_id,
                  source_previous_day_minute_run_id, source_trigger_context_run_id,
                  source_trigger_context_id, source_condition_context_enrichment_id,
                  source_snapshot_id, for_trade_date, trade_date, asset_kind,
                  identity_key, {identity_column}, exchange, code, display_code, name,
                  direction, condition_key, allowed_signal_types, materialization_row_key,
                  current_price_or_close, current_amount_metric, current_metric_time,
                  current_metric_quality_status, projection_period, projection_30m_flag,
                  projection_30m_type, current_30m_virtual_amount, reference_30m_amount,
                  reference_30m_entity_high, reference_30m_entity_low,
                  trigger_amount_chain_pass, projection_lineage_json,
                  source_freshness_status, metric_ready, metric_quality_status,
                  quality_visible, quality_reason, payload_json, raw_json
                )
                VALUES (
                  %(projection_run_id)s, %(spec_version)s, %(policy_hash)s,
                  %(source_condition_run_id)s, %(source_subscription_run_id)s,
                  %(source_snapshot_run_id)s, %(source_today_minute_run_id)s,
                  %(source_previous_day_minute_run_id)s, %(source_trigger_context_run_id)s,
                  %(source_trigger_context_id)s, %(source_condition_context_enrichment_id)s,
                  %(source_snapshot_id)s, %(for_trade_date)s, %(trade_date)s, %(asset_kind)s,
                  %(identity_key)s, %(identity_key)s, %(exchange)s, %(code)s, %(display_code)s, %(name)s,
                  %(direction)s, %(condition_key)s, %(allowed_signal_types)s, %(materialization_row_key)s,
                  %(current_price_or_close)s, %(current_amount_metric)s, %(current_metric_time)s,
                  %(current_metric_quality_status)s, %(projection_period)s, %(projection_30m_flag)s,
                  %(projection_30m_type)s, %(current_30m_virtual_amount)s, %(reference_30m_amount)s,
                  %(reference_30m_entity_high)s, %(reference_30m_entity_low)s,
                  %(trigger_amount_chain_pass)s, %(projection_lineage_json)s,
                  %(source_freshness_status)s, %(metric_ready)s, %(metric_quality_status)s,
                  %(quality_visible)s, %(quality_reason)s, %(payload_json)s, %(raw_json)s
                )
                """,
                [row_insert_params(row) for row in domain_rows],
            )


def row_insert_params(row: Mapping[str, Any]) -> dict[str, Any]:
    lineage = row.get("projection_lineage_json") if isinstance(row.get("projection_lineage_json"), Mapping) else {}
    quality_visible_payload = row.get("quality_visible") if isinstance(row.get("quality_visible"), Mapping) else {}
    target_run_id = str(row.get("target_run_id"))
    for_trade_date = extract_trade_date(target_run_id)
    source_snapshot_run_id = str(row.get("source_snapshot_run_id"))
    db_signal_types = db_allowed_signal_types(row)
    return {
        "projection_run_id": target_run_id,
        "spec_version": row.get("spec_version"),
        "policy_hash": row.get("policy_hash"),
        "source_condition_run_id": row.get("source_condition_run_id"),
        "source_subscription_run_id": row.get("source_subscription_run_id")
        or infer_subscription_run_id(source_snapshot_run_id, for_trade_date),
        "source_snapshot_run_id": source_snapshot_run_id,
        "source_today_minute_run_id": row.get("source_minute_run_id"),
        "source_previous_day_minute_run_id": row.get("source_previous_day_minute_run_id"),
        "source_trigger_context_run_id": row.get("source_trigger_context_run_id"),
        "source_trigger_context_id": row.get("source_trigger_context_id"),
        "source_condition_context_enrichment_id": None,
        "source_snapshot_id": lineage.get("source_snapshot_id"),
        "for_trade_date": for_trade_date,
        "trade_date": for_trade_date,
        "asset_kind": row.get("asset_kind"),
        "identity_key": row.get("identity_key"),
        "exchange": row.get("exchange"),
        "code": row.get("code"),
        "display_code": row.get("display_code"),
        "name": row.get("name"),
        "direction": row.get("direction"),
        "condition_key": row.get("condition_key"),
        "allowed_signal_types": db_signal_types,
        "materialization_row_key": materialization_row_key(row),
        "current_price_or_close": row.get("current_price_or_close"),
        "current_amount_metric": row.get("current_amount_metric"),
        "current_metric_time": row.get("current_metric_time"),
        "current_metric_quality_status": row.get("current_metric_quality_status") or "missing",
        "projection_period": row.get("projection_period") or "30m",
        "projection_30m_flag": row.get("projection_30m_flag"),
        "projection_30m_type": row.get("projection_30m_type") or "unknown",
        "current_30m_virtual_amount": row.get("current_30m_virtual_amount"),
        "reference_30m_amount": row.get("reference_30m_amount"),
        "reference_30m_entity_high": row.get("reference_30m_entity_high"),
        "reference_30m_entity_low": row.get("reference_30m_entity_low"),
        "trigger_amount_chain_pass": Jsonb(row.get("trigger_amount_chain_pass") or {}),
        "projection_lineage_json": Jsonb(lineage),
        "source_freshness_status": row.get("source_freshness_status") or "unknown",
        "metric_ready": bool(row.get("metric_ready")),
        "metric_quality_status": "passed" if row.get("metric_ready") else (row.get("current_metric_quality_status") or "missing"),
        "quality_visible": quality_visible_payload.get("status") not in (None, "passed"),
        "quality_reason": quality_visible_payload.get("reason"),
        "payload_json": Jsonb(dict(row)),
        "raw_json": Jsonb(
            {
                "source_payload_row": dict(row),
                "original_allowed_signal_types": list(row.get("allowed_signal_types") or []),
                "db_allowed_signal_types": db_signal_types,
                "quality_visible_payload": quality_visible_payload,
                "n4_recompute_allowed": False,
            }
        ),
    }


def db_allowed_signal_types(row: Mapping[str, Any]) -> list[str]:
    normalized: list[str] = []
    for signal in row.get("allowed_signal_types") or []:
        canonical = SIGNAL_NORMALIZATION.get(str(signal), str(signal))
        if canonical in CANONICAL_SIGNAL_TYPES and canonical not in normalized:
            normalized.append(canonical)
    return normalized


def materialization_row_key(row: Mapping[str, Any]) -> str:
    source = "|".join(
        [
            str(row.get("target_run_id") or ""),
            str(row.get("spec_version") or ""),
            str(row.get("source_trigger_context_run_id") or ""),
            str(row.get("source_trigger_context_id") or ""),
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def infer_subscription_run_id(source_snapshot_run_id: str, for_trade_date: str) -> str | None:
    prefix = f"realtime_snapshot_{for_trade_date}_"
    if source_snapshot_run_id.startswith(prefix):
        return source_snapshot_run_id[len(prefix) :]
    return None


def allowed_write_tables_for_mode(materialization_mode: str) -> list[str]:
    if materialization_mode == ATTACH_EXISTING_PROJECTION_RUN_MODE:
        return list(PROJECTION_ENRICHMENT_V4_WRITE_TABLES)
    return list(ALLOWED_WRITE_TABLES)


def bj_quality_visible_row_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("identity_key") or ""),
            str(row.get("direction") or ""),
            str(row.get("condition_key") or ""),
        ]
    )


def is_declared_bj_quality_visible_proof(
    row: Mapping[str, Any],
    expected_source_trigger_context_run_id: Any,
) -> bool:
    quality_visible = row.get("quality_visible")
    if not isinstance(quality_visible, Mapping):
        return False
    if expected_source_trigger_context_run_id and row.get("source_trigger_context_run_id") != expected_source_trigger_context_run_id:
        return False
    return (
        row.get("asset_kind") == "index"
        and str(row.get("identity_key") or "").startswith("index:BJ:")
        and row.get("source_trigger_context_id") not in (None, "")
        and bool(row.get("source_subscription_run_id"))
        and row.get("metric_ready") is False
        and row.get("metric_quality_status") == "missing"
        and row.get("current_metric_quality_status") == "missing"
        and quality_visible.get("status") == "missing"
        and quality_visible.get("severity") == "P1"
        and row.get("source_freshness_status") == "source_minute_missing_quality_visible"
    )


def count_payload_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"stock": 0, "index": 0, "board": 0, "total": 0}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind in counts and asset_kind != "total":
            counts[asset_kind] += 1
            counts["total"] += 1
    return counts


def payload_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def blocked_report(
    args: argparse.Namespace,
    blocked_reasons: Sequence[str],
    *,
    contract: Mapping[str, Any] | None = None,
    payload_validation: Mapping[str, Any] | None = None,
    preflight: Mapping[str, Any] | None = None,
    blocked_before_database: bool,
) -> dict[str, Any]:
    return {
        "execute_result": "BLOCKED",
        "layer_role": "N3_market_data",
        "blocked_reasons": list(blocked_reasons),
        "payload_path": args.payload_path,
        "contract_path": args.contract_path,
        "target_run_id": (payload_validation or {}).get("target_run_id") or (contract or {}).get("target_run_id"),
        "payload_validation": dict(payload_validation or {}),
        "preflight": dict(preflight or {}),
        "allowed_write_tables": ALLOWED_WRITE_TABLES,
        "forbidden_write_scopes": FORBIDDEN_WRITE_SCOPES,
        "writes_performed": False,
        "will_execute_sql": False,
        "blocked_before_database_write": blocked_before_database,
    }


def summary_for_stdout(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "execute_result": report.get("execute_result"),
        "target_run_id": report.get("target_run_id"),
        "blocked_reasons": report.get("blocked_reasons", []),
        "row_counts": report.get("row_counts") or (report.get("payload_validation") or {}).get("row_count_by_asset_kind", {}),
        "quality": report.get("quality"),
        "writes_performed": report.get("writes_performed", False),
        "will_execute_sql": report.get("execute_result") == "EXECUTED",
        "blocked_before_database_write": report.get("blocked_before_database_write", False),
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
