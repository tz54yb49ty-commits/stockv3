"""Scope-only policy repair for N2 minute_target_scope rows.

This module is intentionally narrow: it repairs scope rows into a new condition
run lineage without rewriting monitor targets, basis, pool, display rows, or
the old active run status.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import json
from typing import Any

from psycopg.rows import dict_row

from ashare_v3.condition.execute import SCOPE_COLUMNS, SCOPE_TABLE, insert_rows, jsonb, jsonb_or_none, to_jsonable


POLICY_COMMIT = "43b9a24"
RUNTIME_MONITOR_SCOPE_POLICY = "condition_pool_runtime_monitor_requires_minute"
DOMAINS = ("stock", "index", "board")
SCOPE_ID_COLUMNS = {
    "stock": "stock_minute_target_scope_id",
    "index": "index_minute_target_scope_id",
    "board": "board_minute_target_scope_id",
}
IDENTITY_COLUMNS = {"stock": "stock_identity_key", "index": "index_identity_key", "board": "board_identity_key"}

ALLOWED_WRITE_TABLES = (
    "common_condition_run",
    "common_condition_quality_item",
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
)
FORBIDDEN_WRITE_TABLES = (
    "stock_monitor_target",
    "index_monitor_target",
    "board_monitor_target",
    "stock_condition_basis",
    "index_condition_basis",
    "board_condition_basis",
    "stock_condition_pool",
    "index_condition_pool",
    "board_condition_pool",
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
)
ALLOWED_ROLLBACK_DELETE_TABLES = (
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
    "common_condition_quality_item",
    "common_condition_run",
)
DOWNSTREAM_REF_TABLES = (
    "common_market_data_run",
    "common_market_data_subscription",
    "common_market_data_subscription_candidate",
    "common_market_data_pull_plan",
    "stock_previous_day_minute_bar_1m",
    "index_previous_day_minute_bar_1m",
    "board_previous_day_minute_bar_1m",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "common_trigger_run",
    "common_trigger_state",
    "common_trigger_match",
    "common_action_run",
    "common_action_event",
    "common_event_outbox",
)


def build_scope_policy_repair_plan(
    *,
    source_run: Mapping[str, Any],
    source_run_id: str,
    repair_run_id: str,
    source_scope_rows_by_domain: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    blocked_reasons = validate_source_run(source_run=source_run, source_run_id=source_run_id, repair_run_id=repair_run_id)
    repair_rows_by_domain = {
        domain: [
            repair_scope_row(domain=domain, row=row, source_run_id=source_run_id, repair_run_id=repair_run_id)
            for row in source_scope_rows_by_domain.get(domain, [])
        ]
        for domain in DOMAINS
    }
    row_counts = {"common_condition_run": 1, "common_condition_quality_item": len(build_quality_items(repair_rows_by_domain))}
    for domain in DOMAINS:
        row_counts[SCOPE_TABLE[domain]] = len(repair_rows_by_domain[domain])
    object_counts = {
        domain: len(
            {
                str(row.get(IDENTITY_COLUMNS[domain]) or "")
                for row in repair_rows_by_domain[domain]
                if row.get(IDENTITY_COLUMNS[domain])
            }
        )
        for domain in DOMAINS
    }
    return {
        "stage": "N2_SCOPE_ONLY_POLICY_REPAIR_RUNNER_IMPLEMENTATION_GATE",
        "result": "BLOCKED" if blocked_reasons else "PREFLIGHT_PASS",
        "source_run_id": source_run_id,
        "repair_run_id": repair_run_id,
        "old_active_run_status": source_run.get("status"),
        "active_run_preserved": True,
        "basis_pool_display_reused": True,
        "blocked_reasons": blocked_reasons,
        "write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "row_counts": row_counts,
        "object_counts": object_counts,
        "repair_scope_rows_by_domain": repair_rows_by_domain,
        "repair_run_raw_json": build_repair_run_raw_json(source_run_id),
        "database_written": False,
        "worker_started": False,
        "downstream_layers_touched": False,
    }


def validate_source_run(*, source_run: Mapping[str, Any], source_run_id: str, repair_run_id: str) -> list[str]:
    reasons: list[str] = []
    if not source_run:
        reasons.append("source_run_missing")
        return reasons
    if str(source_run.get("run_id") or "") != source_run_id:
        reasons.append("source_run_id_mismatch")
    if source_run_id == repair_run_id:
        reasons.append("repair_run_id_must_differ")
    if str(source_run.get("status") or "") not in {"passed", "passed_active"}:
        reasons.append("source_run_not_passed")
    return reasons


def repair_scope_row(*, domain: str, row: Mapping[str, Any], source_run_id: str, repair_run_id: str) -> dict[str, Any]:
    if domain not in DOMAINS:
        raise ValueError(f"unsupported domain: {domain}")
    repaired = {column: row.get(column) for column in SCOPE_COLUMNS[domain]}
    repaired["run_id"] = repair_run_id
    repaired["condition_periods"] = list(row.get("condition_periods") or [])
    repaired["allowed_signal_types"] = list(row.get("allowed_signal_types") or [])
    repaired["daily_snapshot_required"] = True
    repaired["minute_required"] = True
    repaired["previous_day_minute_required"] = True
    repaired["previous_day_minute_date"] = row.get("prev_trade_date") or row.get("previous_day_minute_date")
    repaired["previous_day_minute_quality_required"] = True
    repaired["minute_scope_reason"] = RUNTIME_MONITOR_SCOPE_POLICY
    repaired["market_data_consumer"] = "both"
    repaired["raw_json"] = repair_scope_raw_json(row, source_run_id=source_run_id)
    return repaired


def repair_scope_raw_json(row: Mapping[str, Any], *, source_run_id: str) -> dict[str, Any]:
    raw_json = normalize_json_object(row.get("raw_json"))
    raw_json.update(
        {
            "scope_policy": RUNTIME_MONITOR_SCOPE_POLICY,
            "repaired_from_run_id": source_run_id,
            "repaired_from_scope_id": source_scope_id(row),
            "original_required_flags": {
                "daily_snapshot_required": bool(row.get("daily_snapshot_required")),
                "minute_required": bool(row.get("minute_required")),
                "previous_day_minute_required": bool(row.get("previous_day_minute_required")),
                "previous_day_minute_quality_required": bool(row.get("previous_day_minute_quality_required")),
                "market_data_consumer": row.get("market_data_consumer"),
            },
            "repair_commit": POLICY_COMMIT,
        }
    )
    return raw_json


def source_scope_id(row: Mapping[str, Any]) -> Any:
    for key in (
        "scope_id",
        "stock_minute_target_scope_id",
        "index_minute_target_scope_id",
        "board_minute_target_scope_id",
        "id",
    ):
        if row.get(key) is not None:
            return row.get(key)
    return None


def build_repair_run_raw_json(source_run_id: str) -> dict[str, Any]:
    return {
        "repair_type": "scope_only_policy_repair",
        "repaired_from_run_id": source_run_id,
        "policy_commit": POLICY_COMMIT,
        "active_run_preserved": True,
        "basis_pool_display_reused": True,
        "write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
    }


def build_quality_items(repair_rows_by_domain: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    items = [
        quality_item("P0", "passed", "active_run_preserved", "old active condition run is not updated"),
        quality_item("P0", "passed", "basis_pool_display_reused", "basis/pool/display rows are not rewritten"),
        quality_item("P0", "passed", "scope_policy_repair_only", "only minute_target_scope rows are repaired"),
    ]
    for domain in DOMAINS:
        rows = repair_rows_by_domain.get(domain, [])
        all_runtime_flags = all(
            bool(row.get("daily_snapshot_required"))
            and bool(row.get("minute_required"))
            and bool(row.get("previous_day_minute_required"))
            and bool(row.get("previous_day_minute_quality_required"))
            and row.get("market_data_consumer") == "both"
            for row in rows
        )
        items.append(
            quality_item(
                "P0",
                "passed" if all_runtime_flags else "failed",
                f"{domain}_runtime_scope_flags_repaired",
                f"{domain} scope rows require daily/minute/previous-day minute",
                actual=str(len(rows)),
            )
        )
    return items


def quality_item(
    severity: str,
    status: str,
    gate_code: str,
    gate_name: str,
    *,
    expected: Any = None,
    actual: Any = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "status": status,
        "gate_code": gate_code,
        "gate_name": gate_name,
        "expected_value": expected,
        "actual_value": actual,
    }


def normalize_json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def build_rollback_sql(repair_run_id: str) -> str:
    escaped = repair_run_id.replace("'", "''")
    downstream_checks = "\n".join(
        f"  v_ref_count := v_ref_count + count_downstream_refs('{table_name}', v_run_id);"
        for table_name in DOWNSTREAM_REF_TABLES
    )
    return f"""BEGIN;

CREATE OR REPLACE FUNCTION pg_temp.count_downstream_refs(p_table_name text, p_run_id text)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
  v_count bigint := 0;
  v_clauses text[] := ARRAY[]::text[];
  v_sql text;
BEGIN
  IF to_regclass('public.' || p_table_name) IS NULL THEN
    RETURN 0;
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = p_table_name AND column_name = 'run_id') THEN
    v_clauses := array_append(v_clauses, 'run_id = $1');
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = p_table_name AND column_name = 'source_condition_run_id') THEN
    v_clauses := array_append(v_clauses, 'source_condition_run_id = $1');
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = p_table_name AND column_name = 'raw_json') THEN
    v_clauses := array_append(v_clauses, 'raw_json::text LIKE ''%%'' || $1 || ''%%''');
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = p_table_name AND column_name = 'payload_json') THEN
    v_clauses := array_append(v_clauses, 'payload_json::text LIKE ''%%'' || $1 || ''%%''');
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = p_table_name AND column_name = 'trace_json') THEN
    v_clauses := array_append(v_clauses, 'trace_json::text LIKE ''%%'' || $1 || ''%%''');
  END IF;
  IF array_length(v_clauses, 1) IS NULL THEN
    RETURN 0;
  END IF;

  v_sql := format('SELECT count(*) FROM %I WHERE %s', p_table_name, array_to_string(v_clauses, ' OR '));
  EXECUTE v_sql INTO v_count USING p_run_id;
  RETURN COALESCE(v_count, 0);
END;
$$;

DO $$
DECLARE
  v_run_id text := '{escaped}';
  v_ref_count bigint := 0;
BEGIN
{downstream_checks}
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'N2 scope-only repair rollback blocked: downstream refs found for % (% refs)', v_run_id, v_ref_count;
  END IF;
END $$;

DELETE FROM stock_minute_target_scope WHERE run_id = '{escaped}';
DELETE FROM index_minute_target_scope WHERE run_id = '{escaped}';
DELETE FROM board_minute_target_scope WHERE run_id = '{escaped}';
DELETE FROM common_condition_quality_item WHERE run_id = '{escaped}';
DELETE FROM common_condition_run WHERE run_id = '{escaped}';

COMMIT;
"""


def run_scope_policy_repair(
    *,
    dsn: str,
    source_run_id: str,
    repair_run_id: str,
    execute: bool = False,
    user_confirmed: bool = False,
    rollback_sql_path: str | Path | None = None,
    json_report_path: str | Path | None = None,
    markdown_report_path: str | Path | None = None,
    connector: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    if execute and not user_confirmed:
        return blocked_report(
            source_run_id=source_run_id,
            repair_run_id=repair_run_id,
            reasons=["missing_user_confirmation"],
        )

    connect = connector or default_connector
    with connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            source_run = fetch_condition_run(cur, source_run_id)
            scope_rows = {domain: fetch_scope_rows(cur, domain, source_run_id) for domain in DOMAINS}
            plan = build_scope_policy_repair_plan(
                source_run=source_run or {},
                source_run_id=source_run_id,
                repair_run_id=repair_run_id,
                source_scope_rows_by_domain=scope_rows,
            )
            target_refs = fetch_repair_target_refs(cur, repair_run_id)
            if any(target_refs.values()):
                plan["result"] = "BLOCKED"
                plan.setdefault("blocked_reasons", []).append("repair_run_target_not_absent")
            if plan["blocked_reasons"]:
                report = finalize_report(plan, execute=execute, database_written=False, target_refs=target_refs)
            elif execute:
                downstream_ref_count = fetch_downstream_ref_count(cur, repair_run_id)
                if downstream_ref_count:
                    plan["result"] = "BLOCKED"
                    plan.setdefault("blocked_reasons", []).append("downstream_refs_exist_for_repair_run")
                    report = finalize_report(plan, execute=execute, database_written=False, target_refs=target_refs)
                else:
                    insert_repair_run(cur, source_run or {}, repair_run_id)
                    repair_rows_by_domain = plan["repair_scope_rows_by_domain"]
                    insert_repair_quality_items(cur, repair_run_id, source_run or {}, build_quality_items(repair_rows_by_domain))
                    for domain in DOMAINS:
                        insert_repair_scope_rows(cur, domain, repair_rows_by_domain[domain])
                    plan["result"] = "EXECUTED"
                    report = finalize_report(plan, execute=execute, database_written=True, target_refs=target_refs)
            else:
                report = finalize_report(plan, execute=False, database_written=False, target_refs=target_refs)

    rollback_sql = build_rollback_sql(repair_run_id)
    if rollback_sql_path:
        Path(rollback_sql_path).parent.mkdir(parents=True, exist_ok=True)
        Path(rollback_sql_path).write_text(rollback_sql, encoding="utf-8")
        report["rollback_sql_path"] = str(rollback_sql_path)
    if json_report_path:
        Path(json_report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if markdown_report_path:
        Path(markdown_report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(markdown_report_path).write_text(format_markdown_report(report), encoding="utf-8")
    return report


def default_connector(dsn: str) -> Any:
    import psycopg

    return psycopg.connect(dsn)


def blocked_report(*, source_run_id: str, repair_run_id: str, reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "stage": "N2_SCOPE_ONLY_POLICY_REPAIR",
        "result": "BLOCKED",
        "source_run_id": source_run_id,
        "repair_run_id": repair_run_id,
        "blocked_reasons": list(reasons),
        "database_written": False,
        "worker_started": False,
        "downstream_layers_touched": False,
    }


def finalize_report(
    plan: Mapping[str, Any],
    *,
    execute: bool,
    database_written: bool,
    target_refs: Mapping[str, int],
) -> dict[str, Any]:
    report = {key: value for key, value in plan.items() if key != "repair_scope_rows_by_domain"}
    report.update(
        {
            "execute_requested": bool(execute),
            "database_written": bool(database_written),
            "target_refs_before": dict(target_refs),
            "rollback_guard": {
                "hard_fail_on_downstream_refs": True,
                "downstream_ref_tables": list(DOWNSTREAM_REF_TABLES),
                "delete_tables": list(ALLOWED_ROLLBACK_DELETE_TABLES),
            },
        }
    )
    return report


def fetch_condition_run(cur: Any, run_id: str) -> dict[str, Any] | None:
    cur.execute("SELECT * FROM common_condition_run WHERE run_id = %s", (run_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_scope_rows(cur: Any, domain: str, run_id: str) -> list[dict[str, Any]]:
    table = SCOPE_TABLE[domain]
    id_column = SCOPE_ID_COLUMNS[domain]
    cur.execute(f"SELECT {id_column} AS scope_id, * FROM {table} WHERE run_id = %s ORDER BY {id_column}", (run_id,))
    return [dict(row) for row in cur.fetchall()]


def fetch_repair_target_refs(cur: Any, repair_run_id: str) -> dict[str, int]:
    refs: dict[str, int] = {}
    for table in ALLOWED_WRITE_TABLES:
        cur.execute(f"SELECT count(*) AS count FROM {table} WHERE run_id = %s", (repair_run_id,))
        refs[table] = int((cur.fetchone() or {}).get("count") or 0)
    return refs


def fetch_downstream_ref_count(cur: Any, repair_run_id: str) -> int:
    total = 0
    for table in DOWNSTREAM_REF_TABLES:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{table}",))
        exists = bool((cur.fetchone() or {}).get("exists"))
        if not exists:
            continue
        columns = table_columns(cur, table)
        clauses: list[str] = []
        params: list[str] = []
        for column in ("run_id", "source_condition_run_id"):
            if column in columns:
                clauses.append(f"{column} = %s")
                params.append(repair_run_id)
        for column in ("raw_json", "payload_json", "trace_json", "quality_summary_json"):
            if column in columns:
                clauses.append(f"{column}::text LIKE %s")
                params.append(f"%{repair_run_id}%")
        if not clauses:
            continue
        cur.execute(f"SELECT count(*) AS count FROM {table} WHERE {' OR '.join(clauses)}", params)
        total += int((cur.fetchone() or {}).get("count") or 0)
    return total


def table_columns(cur: Any, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return {str(row.get("column_name")) for row in cur.fetchall()}


def insert_repair_run(cur: Any, source_run: Mapping[str, Any], repair_run_id: str) -> None:
    cur.execute(
        """
        INSERT INTO common_condition_run (
          run_id, for_trade_date, source_trade_date, prev_trade_date,
          source_version, source_versions, source_ready_check, mode, status,
          p0_count, p1_count, p2_count, raw_json
        )
        VALUES (%(run_id)s, %(for_trade_date)s, %(source_trade_date)s, %(prev_trade_date)s,
          %(source_version)s, %(source_versions)s, %(source_ready_check)s, 'execute', 'passed',
          0, 0, 0, %(raw_json)s)
        """,
        {
            "run_id": repair_run_id,
            "for_trade_date": source_run.get("for_trade_date"),
            "source_trade_date": source_run.get("source_trade_date"),
            "prev_trade_date": source_run.get("prev_trade_date"),
            "source_version": source_run.get("source_version") or f"scope_policy_repair_{POLICY_COMMIT}",
            "source_versions": jsonb(source_run.get("source_versions") or {}),
            "source_ready_check": jsonb(source_run.get("source_ready_check") or {}),
            "raw_json": jsonb(build_repair_run_raw_json(str(source_run.get("run_id") or ""))),
        },
    )


def insert_repair_quality_items(
    cur: Any,
    repair_run_id: str,
    source_run: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
) -> int:
    rows = [
        {
            "run_id": repair_run_id,
            "for_trade_date": source_run.get("for_trade_date"),
            "source_trade_date": source_run.get("source_trade_date"),
            "data_domain": "common",
            "layer_scope": "minute_target_scope",
            "table_name": "common_condition_run",
            "gate_code": item.get("gate_code"),
            "gate_name": item.get("gate_name"),
            "severity": item.get("severity"),
            "status": item.get("status"),
            "expected_value": item.get("expected_value"),
            "actual_value": item.get("actual_value"),
            "identity_key": None,
            "details": jsonb(item),
        }
        for item in quality_items
    ]
    insert_rows(
        cur,
        "common_condition_quality_item",
        (
            "run_id",
            "for_trade_date",
            "source_trade_date",
            "data_domain",
            "layer_scope",
            "table_name",
            "gate_code",
            "gate_name",
            "severity",
            "status",
            "expected_value",
            "actual_value",
            "identity_key",
            "details",
        ),
        rows,
    )
    return len(rows)


def insert_repair_scope_rows(cur: Any, domain: str, rows: Sequence[Mapping[str, Any]]) -> int:
    insert_rows(cur, SCOPE_TABLE[domain], SCOPE_COLUMNS[domain], [scope_insert_row(domain, row) for row in rows])
    return len(rows)


def scope_insert_row(domain: str, row: Mapping[str, Any]) -> dict[str, Any]:
    output = {column: row.get(column) for column in SCOPE_COLUMNS[domain]}
    output["condition_periods"] = list(row.get("condition_periods") or [])
    output["allowed_signal_types"] = list(row.get("allowed_signal_types") or [])
    output["period_trigger_baseline_json"] = jsonb(row.get("period_trigger_baseline_json") or {})
    if "target_price_trace_json" in output:
        output["target_price_trace_json"] = jsonb(row.get("target_price_trace_json") or {})
    for key, value in list(output.items()):
        if key.endswith("_json") and key not in {"period_trigger_baseline_json", "target_price_trace_json", "raw_json"}:
            output[key] = jsonb_or_none(value)
    output["raw_json"] = jsonb(row.get("raw_json") or {})
    return output


def format_markdown_report(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N2 Scope-Only Policy Repair",
            "",
            f"- result: `{report.get('result')}`",
            f"- source_run_id: `{report.get('source_run_id')}`",
            f"- repair_run_id: `{report.get('repair_run_id')}`",
            f"- database_written: `{str(report.get('database_written')).lower()}`",
            f"- active_run_preserved: `{str(report.get('active_run_preserved')).lower()}`",
            f"- write_tables: `{', '.join(report.get('write_tables') or [])}`",
            f"- blocked_reasons: `{', '.join(report.get('blocked_reasons') or [])}`",
        ]
    )


def report_to_jsonable(report: Mapping[str, Any]) -> dict[str, Any]:
    return to_jsonable(report)
