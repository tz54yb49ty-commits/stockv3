#!/usr/bin/env python3
"""Generate N4 20260605 v4 corrected execute contract/preflight artifacts.

The script performs only read-only PostgreSQL baseline checks and writes docs
artifacts plus rollback SQL. It does not execute N4 business writes.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect
from ashare_v3.trigger.synthetic_dry_run import write_json, write_text
from ashare_v3.trigger.v4_corrected_execute_contract import (
    DEFAULT_CONTRACT_PATH,
    DEFAULT_DRY_RUN_PATH,
    DEFAULT_PREFLIGHT_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    DEFAULT_RUNNER_PATH,
    build_corrected_execute_contract,
    build_corrected_execute_preflight,
    build_corrected_execute_rollback_sql,
)
from check_condition_source_ready import DEFAULT_DSN


DEFAULT_CONTRACT_MD_PATH = "docs/N4_20260605_V4_CORRECTED_EXECUTE_CONTRACT.md"
DEFAULT_PREFLIGHT_MD_PATH = "docs/N4_20260605_V4_CORRECTED_EXECUTE_PREFLIGHT.md"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan N4 20260605 v4 corrected execute contract/preflight.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--dry-run-json-path", default=DEFAULT_DRY_RUN_PATH)
    parser.add_argument("--contract-json-path", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--contract-md-path", default=DEFAULT_CONTRACT_MD_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_PREFLIGHT_PATH)
    parser.add_argument("--preflight-md-path", default=DEFAULT_PREFLIGHT_MD_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--runner-path", default=DEFAULT_RUNNER_PATH)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    generated_at = datetime.now(timezone.utc)
    dry_run = json.loads(Path(args.dry_run_json_path).read_text(encoding="utf-8"))
    contract = build_corrected_execute_contract(
        dry_run,
        contract_path=args.contract_json_path,
        preflight_path=args.preflight_json_path,
        dry_run_path=args.dry_run_json_path,
        rollback_sql_path=args.rollback_sql_path,
        runner_path=args.runner_path,
        generated_at=generated_at,
    )
    baseline = capture_corrected_execute_baseline(args.dsn, str(contract["execute_run_id"]))
    runner_exists = Path(args.runner_path).exists()
    preflight = build_corrected_execute_preflight(
        contract,
        baseline_refs=baseline,
        runner_exists=runner_exists,
        generated_at=generated_at,
    )
    rollback_sql = build_corrected_execute_rollback_sql(str(contract["execute_run_id"]))
    write_json(Path(args.contract_json_path), contract)
    write_text(Path(args.contract_md_path), format_contract_markdown(contract))
    write_json(Path(args.preflight_json_path), preflight)
    write_text(Path(args.preflight_md_path), format_preflight_markdown(preflight))
    write_text(Path(args.rollback_sql_path), rollback_sql)
    summary = {
        "contract_result": contract["result"],
        "preflight_result": preflight["result"],
        "execute_run_id": contract["execute_run_id"],
        "planned_writes": contract["planned_writes"],
        "baseline_refs": baseline,
        "runner_readiness": preflight["runner_readiness"],
        "blockers": preflight["blockers"],
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_summary(summary))
    return 0 if contract["result"] == "CONTRACT_PASS" else 2


def capture_corrected_execute_baseline(dsn: str, execute_run_id: str) -> dict[str, int]:
    refs = {
        "common_trigger_run": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_trigger_run WHERE run_id = %s", (execute_run_id,)),
        "common_trigger_quality_item": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_trigger_quality_item WHERE run_id = %s",
            (execute_run_id,),
        ),
        "common_trigger_state": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_trigger_state WHERE run_id = %s", (execute_run_id,)),
        "common_trigger_match": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_trigger_match WHERE run_id = %s", (execute_run_id,)),
        "common_event_outbox": scalar_count(dsn, "SELECT count(*)::bigint AS n FROM common_event_outbox WHERE source_run_id = %s", (execute_run_id,)),
        "common_event_inbox": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_inbox WHERE source_layer = 'N4_trigger' AND source_run_id = %s",
            (execute_run_id,),
        ),
        "common_event_consumer_checkpoint": scalar_count(
            dsn,
            "SELECT count(*)::bigint AS n FROM common_event_consumer_checkpoint WHERE source_layer = 'N4_trigger' AND checkpoint_payload::TEXT LIKE %s",
            (f"%{execute_run_id}%",),
        ),
        "n5_refs": optional_table_count(
            dsn,
            table_name="common_action_run",
            sql="SELECT count(*)::bigint AS n FROM common_action_run WHERE source_trigger_run_id = %s",
            params=(execute_run_id,),
        )
        + optional_table_count(
            dsn,
            table_name="common_action_event",
            sql="SELECT count(*)::bigint AS n FROM common_action_event WHERE source_trigger_run_id = %s",
            params=(execute_run_id,),
        ),
        "n6_refs": n6_optional_refs(dsn, execute_run_id),
    }
    return refs


def scalar_count(dsn: str, sql: str, params: tuple[Any, ...]) -> int:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_20260605_corrected_contract_scalar_count",
        source_run_id="n4_20260605_corrected_execute_contract",
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return int((cur.fetchone() or {}).get("n") or 0)


def optional_table_count(dsn: str, *, table_name: str, sql: str, params: tuple[Any, ...]) -> int:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_20260605_corrected_contract_optional_table_count",
        source_run_id=table_name,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table_name}",))
        if not (cur.fetchone() or {}).get("table_name"):
            return 0
        cur.execute(sql, params)
        return int((cur.fetchone() or {}).get("n") or 0)


def n6_optional_refs(dsn: str, execute_run_id: str) -> int:
    like = f"%{execute_run_id}%"
    checks = [
        (
            "user_projection_run",
            """
            SELECT count(*)::bigint AS n
            FROM user_projection_run
            WHERE source_action_run_id = %s
               OR source_n5_outbox_range::TEXT LIKE %s
               OR quality_summary_json::TEXT LIKE %s
            """,
            (execute_run_id, like, like),
        ),
        (
            "user_signal_projection",
            """
            SELECT count(*)::bigint AS n
            FROM user_signal_projection
            WHERE source_action_run_id = %s
               OR source_event_id = %s
               OR source_payload_json::TEXT LIKE %s
               OR display_payload_json::TEXT LIKE %s
            """,
            (execute_run_id, execute_run_id, like, like),
        ),
        (
            "user_signal_card",
            """
            SELECT count(*)::bigint AS n
            FROM user_signal_card
            WHERE source_action_run_id = %s
               OR source_event_id = %s
               OR card_payload_json::TEXT LIKE %s
            """,
            (execute_run_id, execute_run_id, like),
        ),
        (
            "user_notification_queue",
            """
            SELECT count(*)::bigint AS n
            FROM user_notification_queue
            WHERE source_action_run_id = %s
               OR source_event_id = %s
               OR notification_payload_json::TEXT LIKE %s
            """,
            (execute_run_id, execute_run_id, like),
        ),
    ]
    total = 0
    for table_name, sql, params in checks:
        total += optional_table_count(dsn, table_name=table_name, sql=sql, params=params)
    return total


def format_contract_markdown(contract: Mapping[str, Any]) -> str:
    planned = contract.get("planned_writes") or {}
    blocked = contract.get("blocked_candidates") or {}
    return "\n".join(
        [
            "# N4 20260605 V4 Corrected Execute Contract",
            "",
            f"- result: {contract.get('result')}",
            f"- execute_run_id: {contract.get('execute_run_id')}",
            f"- dry_run_artifact_path: {contract.get('dry_run_artifact_path')}",
            f"- rollback_sql_path: {contract.get('rollback_sql_path')}",
            "",
            "## Planned Writes",
            "",
            *(f"- {key}: {value}" for key, value in planned.items()),
            "",
            "## Blocked Candidates",
            "",
            f"- total: {blocked.get('total')}",
            f"- by_reason: {blocked.get('by_reason')}",
            f"- reason_counts_are_non_exclusive: {blocked.get('reason_counts_are_non_exclusive')}",
            "",
            "## P0 Guards",
            "",
            *(f"- {item}" for item in contract.get("p0_guards") or []),
            "",
            "## N5 Entry Contract",
            "",
            f"- required: {(contract.get('n5_entry_contract') or {}).get('required')}",
            f"- invalid_n5_entry_count: {(contract.get('n5_entry_contract') or {}).get('invalid_n5_entry_count')}",
            "",
            "## Execute Command Candidate",
            "",
            "```bash",
            str(contract.get("execute_command_candidate")),
            "```",
            "",
            "## Post Review Checks",
            "",
            f"- {contract.get('post_review_checks')}",
            "",
        ]
    )


def format_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    quality = preflight.get("quality") or {}
    return "\n".join(
        [
            "# N4 20260605 V4 Corrected Execute Preflight",
            "",
            f"- result: {preflight.get('result')}",
            f"- execute_run_id: {preflight.get('execute_run_id')}",
            f"- execute_authorized: {str(preflight.get('execute_authorized')).lower()}",
            f"- runner_readiness: {preflight.get('runner_readiness')}",
            f"- blockers: {preflight.get('blockers')}",
            f"- P0/P1/P2: {quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
            "",
            "## Baseline Refs",
            "",
            f"- {preflight.get('baseline_refs')}",
            "",
            "## Planned Writes",
            "",
            f"- {preflight.get('planned_writes')}",
            "",
            "## Rollback",
            "",
            f"- rollback_sql_path: {preflight.get('rollback_sql_path')}",
            "- hard_fail_before_delete: true",
            "",
            "## Next Gate",
            "",
            f"- {preflight.get('next_gate')}",
            "",
        ]
    )


def format_summary(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "N4 20260605 v4 corrected execute contract/preflight",
            f"  contract={summary.get('contract_result')}",
            f"  preflight={summary.get('preflight_result')}",
            f"  execute_run_id={summary.get('execute_run_id')}",
            f"  planned_writes={summary.get('planned_writes')}",
            f"  baseline_refs={summary.get('baseline_refs')}",
            f"  runner_readiness={summary.get('runner_readiness')}",
            f"  blockers={summary.get('blockers')}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
