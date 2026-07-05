"""N3 action-confirmation projection metric run-once executor.

The executor is bounded and inert unless both ``--execute`` and
``--user-confirmed`` are provided. It writes only the N3 action-confirmation
projection metric facts plus the scoped common_market_data_run / quality rows.
It never writes or consumes outbox/inbox/checkpoint rows, never pulls market
data, never enters N4/N5/N6, and never starts workers.
"""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.realtime_virtual_metric import (
    REALTIME_VIRTUAL_METRIC_DB_COLUMNS,
    canonicalize_realtime_virtual_metric_fields,
)
from ashare_v3.market.action_confirmation_projection_plan import (
    ASSET_KINDS,
    DEFAULT_DRY_RUN_JSON_PATH,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_ROLLBACK_SQL_PATH,
    DEFAULT_FOR_TRADE_DATE,
    METRIC_TABLES,
    build_action_confirmation_projection_rows_from_db,
    build_write_scope_contract,
    checkpoint_ref_count,
    normalize_jsonable,
    total_counts,
)
from ashare_v3.market.previous_day_preload_execute import utc_now_iso, write_json, write_text


DEFAULT_EXECUTE_CONTRACT_PATH = "docs/N3_action_confirmation_projection_writer_execute_contract.json"
DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH = "docs/N3_ACTION_CONFIRMATION_PROJECTION_WRITER_EXECUTE_CONTRACT.md"
DEFAULT_EXECUTE_PREFLIGHT_PATH = "docs/N3_action_confirmation_projection_writer_execute_preflight.json"
DEFAULT_EXECUTE_PREFLIGHT_MARKDOWN_PATH = "docs/N3_ACTION_CONFIRMATION_PROJECTION_WRITER_EXECUTE_PREFLIGHT.md"
DEFAULT_EXECUTE_REPORT_PATH = "docs/N3_action_confirmation_projection_writer_execute_report.json"
DEFAULT_EXECUTE_REPORT_MARKDOWN_PATH = "docs/N3_ACTION_CONFIRMATION_PROJECTION_WRITER_EXECUTE_REPORT.md"

ACTION_CONFIRMATION_METRIC_SCOPE = "action_confirmation_projection_metric"
ACTION_CONFIRMATION_QUALITY_LAYER_SCOPE = "market_data_run"
ACTION_CONFIRMATION_ALLOWED_WRITE_TABLES = tuple(build_write_scope_contract()["allowed_future_execute_write_tables"])
ACTION_CONFIRMATION_FORBIDDEN_WRITE_TABLES = tuple(build_write_scope_contract()["forbidden_write_tables"])


class ActionConfirmationProjectionExecuteError(RuntimeError):
    """Raised when the N3 action-confirmation writer execute gate is blocked."""


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ensure_action_confirmation_execute_authorized(*, execute: bool, user_confirmed: bool) -> None:
    if not execute:
        raise ActionConfirmationProjectionExecuteError(
            "N3 action-confirmation projection execute blocked: missing --execute"
        )
    if not user_confirmed:
        raise ActionConfirmationProjectionExecuteError(
            "N3 action-confirmation projection execute blocked: missing --user-confirmed"
        )


def build_action_confirmation_execute_contract(dry_run: Mapping[str, Any]) -> dict[str, Any]:
    expected_rows = dict(dry_run.get("would_write_rows") or dry_run.get("candidate_summary") or {})
    expected_rows.setdefault("total", total_counts(expected_rows))
    projection_run_id = str(dry_run["projection_run_id"])
    source_trade_date = infer_source_trade_date(
        str(dry_run.get("source_condition_run_id") or ""),
        str(dry_run.get("for_trade_date") or DEFAULT_FOR_TRADE_DATE),
    )
    return {
        "stage": "N3 action-confirmation projection writer execute contract",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if not dry_run.get("blocked") else "CONTRACT_BLOCKED",
        "execute_authorized_now": False,
        "execute_authorized_reason": "awaiting_final_gate_user_confirmation",
        "runner_exists": True,
        "runner_readiness": "ready",
        "projection_run_id": projection_run_id,
        "projection_schema_version": dry_run.get("projection_schema_version"),
        "for_trade_date": dry_run.get("for_trade_date"),
        "source_condition_run_id": dry_run.get("source_condition_run_id"),
        "source_subscription_run_id": dry_run.get("source_subscription_run_id"),
        "source_snapshot_run_id": dry_run.get("source_snapshot_run_id"),
        "source_today_minute_run_id": dry_run.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": dry_run.get("source_previous_day_minute_run_id"),
        "run_metadata": {
            "source_trade_date": source_trade_date,
            "prev_trade_date": source_trade_date,
            "mode": "execute",
            "generated_by": "N3-action-confirmation-projection-writer-execute",
        },
        "expected_rows": expected_rows,
        "metric_ready_expected": int((dry_run.get("metric_ready_distribution") or {}).get("ready_total") or 0),
        "metric_not_ready_expected": int((dry_run.get("metric_ready_distribution") or {}).get("not_ready_total") or 0),
        "allowed_write_tables": list(ACTION_CONFIRMATION_ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(ACTION_CONFIRMATION_FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "quality_rollback_predicate": {
            "layer_scope": ACTION_CONFIRMATION_QUALITY_LAYER_SCOPE,
            "details.metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
        },
        "run_row_contract": {
            "market_data_pulled": False,
            "market_data_fact_written": True,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
        "rollback": {
            "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH,
            "scope": "projection_run_id",
            "hard_fail_guard": "common_event_outbox/common_event_inbox/common_event_consumer_checkpoint refs nonzero",
        },
        "side_effects": {
            "writes_projection_business_rows": "future_execute_only",
            "writes_outbox": False,
            "consumes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "market_data_pulled": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def build_action_confirmation_execute_preflight(
    contract: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    refreshed_baseline: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    baseline = dict(refreshed_baseline or dry_run.get("baseline_summary") or {})
    quality_items = build_action_confirmation_execute_preflight_quality_items(contract, dry_run, baseline)
    quality_counts = count_quality_severities(quality_items)
    blockers = [
        item["gate_code"]
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    blocked = quality_counts["P0"] > 0
    return {
        "stage": "N3 action-confirmation projection writer execute preflight",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_BLOCKED" if blocked else "PREFLIGHT_PASS",
        "blocked": blocked,
        "blockers": blockers,
        "projection_run_id": contract.get("projection_run_id"),
        "projection_schema_version": contract.get("projection_schema_version"),
        "for_trade_date": contract.get("for_trade_date"),
        "source_condition_run_id": contract.get("source_condition_run_id"),
        "source_subscription_run_id": contract.get("source_subscription_run_id"),
        "source_snapshot_run_id": contract.get("source_snapshot_run_id"),
        "source_today_minute_run_id": contract.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": contract.get("source_previous_day_minute_run_id"),
        "would_write_rows": dry_run.get("would_write_rows"),
        "metric_ready_distribution": dry_run.get("metric_ready_distribution"),
        "trace_refs_proof": dry_run.get("trace_refs_proof"),
        "baseline_summary": baseline,
        "allowed_write_tables": contract.get("allowed_write_tables"),
        "forbidden_write_tables": contract.get("forbidden_write_tables"),
        "writes_outbox": False,
        "rollback": contract.get("rollback"),
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": contract.get("side_effects"),
        "generated_at": utc_now_iso(),
    }


def build_action_confirmation_execute_preflight_quality_items(
    contract: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    baseline: Mapping[str, int],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.append(
        quality_item(
            "P0",
            "passed" if dry_run.get("result") == "DRY_RUN_PASS" else "failed",
            "n3_action_confirmation_execute_dry_run_passed",
            "writer dry-run must pass before execute",
            expected="DRY_RUN_PASS",
            actual=str(dry_run.get("result")),
        )
    )
    expected_rows = contract.get("expected_rows") or {}
    would_rows = dry_run.get("would_write_rows") or {}
    items.append(
        quality_item(
            "P0",
            "passed" if expected_rows == would_rows else "failed",
            "n3_action_confirmation_execute_rows_match_contract",
            "would-write row counts must match execute contract",
            expected=json.dumps(expected_rows, sort_keys=True),
            actual=json.dumps(would_rows, sort_keys=True),
        )
    )
    ready = dry_run.get("metric_ready_distribution") or {}
    items.append(
        quality_item(
            "P0",
            "passed" if int(ready.get("not_ready_total") or 0) == 0 else "failed",
            "n3_action_confirmation_execute_metric_ready_all",
            "all would-write rows must be metric_ready",
            expected=str(contract.get("metric_ready_expected")),
            actual=str(ready.get("ready_total")),
        )
    )
    baseline_nonzero = {key: value for key, value in baseline.items() if int(value or 0) != 0}
    items.append(
        quality_item(
            "P0",
            "passed" if not baseline_nonzero else "failed",
            "n3_action_confirmation_execute_scoped_baseline_zero",
            "projection_run_id scoped run/quality/metric/outbox/inbox/checkpoint rows must be zero",
            expected="all scoped baseline counts 0",
            actual=json.dumps(baseline, sort_keys=True),
            details={"nonzero": baseline_nonzero},
        )
    )
    trace = dry_run.get("trace_refs_proof") or {}
    trace_ok = (
        int(trace.get("db_check_fail_total") or 0) == 0
        and int(trace.get("source_fact_ids_non_empty") or 0) == int(contract.get("metric_ready_expected") or 0)
        and int(trace.get("source_minute_refs_non_empty") or 0) == int(contract.get("metric_ready_expected") or 0)
        and int(trace.get("previous_day_refs_non_empty") or 0) >= int(trace.get("previous_day_refs_required") or 0)
    )
    items.append(
        quality_item(
            "P0",
            "passed" if trace_ok else "failed",
            "n3_action_confirmation_execute_trace_refs_complete",
            "trace refs and metric_ready DB CHECK simulation must pass",
            expected="complete trace refs and db_check_fail_total=0",
            actual=json.dumps(trace, sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed",
            "n3_action_confirmation_execute_no_event_downstream_writes",
            "execute writes no outbox/inbox/checkpoint and no N4/N5/N6 state",
            expected="event/downstream writes disabled",
            actual=json.dumps(
                {
                    "writes_outbox": contract.get("writes_outbox"),
                    "consumes_outbox": contract.get("consumes_outbox"),
                    "writes_inbox_or_checkpoint": contract.get("writes_inbox_or_checkpoint"),
                },
                sort_keys=True,
            ),
        )
    )
    return items


def build_action_confirmation_execute_quality_items(
    contract: Mapping[str, Any],
    dry_run: Mapping[str, Any],
) -> list[dict[str, Any]]:
    preflight = build_action_confirmation_execute_preflight(contract, dry_run)
    output: list[dict[str, Any]] = []
    for item in preflight["quality"]["items"]:
        details = dict(item.get("details") or {})
        details.setdefault("metric_scope", ACTION_CONFIRMATION_METRIC_SCOPE)
        details.setdefault("projection_run_id", contract["projection_run_id"])
        details.setdefault("projection_schema_version", contract.get("projection_schema_version"))
        output.append(
            {
                **dict(item),
                "run_id": contract["projection_run_id"],
                "source_condition_run_id": contract["source_condition_run_id"],
                "for_trade_date": contract["for_trade_date"],
                "source_trade_date": contract["run_metadata"]["source_trade_date"],
                "data_domain": "common",
                "layer_scope": ACTION_CONFIRMATION_QUALITY_LAYER_SCOPE,
                "table_name": "common_market_data_run",
                "details": details,
            }
        )
    return output


def infer_source_trade_date(source_condition_run_id: str, for_trade_date: str) -> str:
    match = re.search(r"source_(\d{8})", source_condition_run_id)
    return match.group(1) if match else for_trade_date


def write_action_confirmation_execute_contract_files(
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    contract_json_path: str | Path = DEFAULT_EXECUTE_CONTRACT_PATH,
    contract_markdown_path: str | Path = DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH,
    preflight_json_path: str | Path = DEFAULT_EXECUTE_PREFLIGHT_PATH,
    preflight_markdown_path: str | Path = DEFAULT_EXECUTE_PREFLIGHT_MARKDOWN_PATH,
) -> None:
    write_json(contract_json_path, normalize_jsonable(contract))
    write_text(contract_markdown_path, format_action_confirmation_execute_contract_markdown(contract))
    write_json(preflight_json_path, normalize_jsonable(preflight))
    write_text(preflight_markdown_path, format_action_confirmation_execute_preflight_markdown(preflight))


def format_action_confirmation_execute_contract_markdown(contract: Mapping[str, Any]) -> str:
    expected = contract.get("expected_rows") or {}
    return f"""# N3 Action-Confirmation Projection Writer Execute Contract

Status: {contract.get("contract_result")}

```text
projection_run_id={contract.get("projection_run_id")}
runner_exists={contract.get("runner_exists")}
runner_readiness={contract.get("runner_readiness")}
execute_authorized_now={contract.get("execute_authorized_now")}
expected_rows stock/index/board/total={expected.get("stock", 0)}/{expected.get("index", 0)}/{expected.get("board", 0)}/{expected.get("total", 0)}
metric_ready_expected={contract.get("metric_ready_expected")}
writes_outbox={contract.get("writes_outbox")}
quality rollback predicate: layer_scope={contract.get("quality_rollback_predicate", {}).get("layer_scope")}, details.metric_scope={contract.get("quality_rollback_predicate", {}).get("details.metric_scope")}
rollback_sql={contract.get("rollback", {}).get("rollback_sql_path")}
```
"""


def format_action_confirmation_execute_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    rows = preflight.get("would_write_rows") or {}
    quality = preflight.get("quality") or {}
    return f"""# N3 Action-Confirmation Projection Writer Execute Preflight

Status: {preflight.get("result")}

```text
projection_run_id={preflight.get("projection_run_id")}
would_write_rows stock/index/board/total={rows.get("stock", 0)}/{rows.get("index", 0)}/{rows.get("board", 0)}/{rows.get("total", 0)}
P0/P1/P2={quality.get("p0_count", 0)}/{quality.get("p1_count", 0)}/{quality.get("p2_count", 0)}
blockers={preflight.get("blockers", [])}
writes_outbox=false
```
"""


def run_action_confirmation_projection_execute(
    *,
    dsn: str,
    contract_path: str = DEFAULT_EXECUTE_CONTRACT_PATH,
    preflight_path: str = DEFAULT_EXECUTE_PREFLIGHT_PATH,
    dry_run_path: str = DEFAULT_DRY_RUN_JSON_PATH,
    json_report_path: str = DEFAULT_EXECUTE_REPORT_PATH,
    markdown_report_path: str = DEFAULT_EXECUTE_REPORT_MARKDOWN_PATH,
    execute: bool = False,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    contract = read_json(contract_path)
    preflight = read_json(preflight_path)
    dry_run = read_json(dry_run_path)
    ensure_action_confirmation_execute_authorized(execute=execute, user_confirmed=user_confirmed)
    ensure_contract_preflight_dry_run_match(contract, preflight, dry_run)
    refreshed_baseline = capture_action_confirmation_baseline(dsn, str(contract["projection_run_id"]))
    refreshed_preflight = build_action_confirmation_execute_preflight(contract, dry_run, refreshed_baseline)
    if refreshed_preflight["quality"]["p0_count"]:
        raise ActionConfirmationProjectionExecuteError("N3 action-confirmation projection execute blocked: P0 preflight blockers present")
    rows_by_asset = build_action_confirmation_projection_rows_from_db(dsn=dsn, readiness_report=dry_run)
    validate_rows_by_asset_against_contract(rows_by_asset, contract)
    quality_items = build_action_confirmation_execute_quality_items(contract, dry_run)
    quality_counts = count_quality_severities(quality_items)
    started_at = utc_now_iso()
    write_action_confirmation_execute_transaction(
        dsn=dsn,
        contract=contract,
        rows_by_asset=rows_by_asset,
        quality_items=quality_items,
        quality_counts=quality_counts,
        started_at=started_at,
    )
    post_baseline = capture_action_confirmation_baseline(dsn, str(contract["projection_run_id"]))
    report = {
        "stage": "N3 action-confirmation projection writer execute",
        "layer_role": "N3_market_data",
        "result": "EXECUTED",
        "projection_run_id": contract["projection_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "write_result": {
            "rows_written": contract["expected_rows"],
            "quality_rows_written": len(quality_items),
            "run_rows_written": 1,
            "writes_outbox": False,
            "outbox_rows_written": 0,
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "pre_execute_baseline": refreshed_baseline,
        "post_execute_baseline": post_baseline,
        "rollback": {
            "rollback_safe": post_baseline.get("common_event_outbox", 0) == 0
            and post_baseline.get("common_event_inbox", 0) == 0
            and post_baseline.get("common_event_consumer_checkpoint", 0) == 0,
            "rollback_sql_path": contract["rollback"]["rollback_sql_path"],
        },
        "side_effects": {
            "writes_database": True,
            "writes_projection_business_rows": True,
            "writes_run_or_quality": True,
            "writes_outbox": False,
            "consumes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "market_data_pulled": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "started_at": started_at,
        "finished_at": utc_now_iso(),
    }
    write_json(json_report_path, normalize_jsonable(report))
    write_text(markdown_report_path, format_action_confirmation_execute_report_markdown(report))
    return report


def ensure_contract_preflight_dry_run_match(
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
) -> None:
    if contract.get("projection_run_id") != dry_run.get("projection_run_id"):
        raise ActionConfirmationProjectionExecuteError("projection_run_id mismatch between contract and dry-run")
    if preflight.get("projection_run_id") != contract.get("projection_run_id"):
        raise ActionConfirmationProjectionExecuteError("projection_run_id mismatch between preflight and contract")
    if preflight.get("result") != "PREFLIGHT_PASS":
        raise ActionConfirmationProjectionExecuteError("execute preflight is not PREFLIGHT_PASS")
    if dry_run.get("result") != "DRY_RUN_PASS":
        raise ActionConfirmationProjectionExecuteError("dry-run is not DRY_RUN_PASS")


def validate_rows_by_asset_against_contract(rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]], contract: Mapping[str, Any]) -> None:
    actual = {asset: len(rows_by_asset.get(asset, [])) for asset in ASSET_KINDS}
    actual["total"] = total_counts(actual)
    expected = contract.get("expected_rows") or {}
    if actual != expected:
        raise ActionConfirmationProjectionExecuteError(
            f"would-write rows drifted before execute: expected={expected}, actual={actual}"
        )


def capture_action_confirmation_baseline(dsn: str, projection_run_id: str) -> dict[str, int]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        counts = {
            "common_market_data_run": count_where(cur, "common_market_data_run", "run_id = %s", (projection_run_id,)),
            "common_market_data_quality_item": count_where(cur, "common_market_data_quality_item", "run_id = %s", (projection_run_id,)),
            "common_event_outbox": count_where(cur, "common_event_outbox", "source_run_id = %s", (projection_run_id,)),
            "common_event_inbox": count_where(cur, "common_event_inbox", "source_run_id = %s", (projection_run_id,)),
            "common_event_consumer_checkpoint": checkpoint_ref_count(cur, projection_run_id),
        }
        for asset, table in METRIC_TABLES.items():
            counts[table] = count_where(cur, table, "projection_run_id = %s", (projection_run_id,))
    return counts


def count_where(cur: Any, table: str, where_sql: str, params: tuple[Any, ...]) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table} WHERE {where_sql}", params)
    return int(cur.fetchone()["row_count"])


def write_action_confirmation_execute_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    quality_items: Sequence[Mapping[str, Any]],
    quality_counts: Mapping[str, int],
    started_at: str,
) -> None:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                insert_action_confirmation_run(cur, contract=contract, started_at=started_at)
                for asset, rows in rows_by_asset.items():
                    insert_action_confirmation_metric_rows(cur, table=METRIC_TABLES[asset], rows=rows)
                insert_action_confirmation_quality_items(cur, quality_items)
                cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status = 'passed',
                        p0_count = %s,
                        p1_count = %s,
                        p2_count = %s,
                        market_data_pulled = false,
                        market_data_fact_written = true,
                        downstream_layers_touched = false,
                        worker_started = false,
                        finished_at = now(),
                        updated_at = now()
                    WHERE run_id = %s
                    """,
                    (
                        quality_counts["P0"],
                        quality_counts["P1"],
                        quality_counts["P2"],
                        contract["projection_run_id"],
                    ),
                )


def insert_action_confirmation_run(cur: Any, *, contract: Mapping[str, Any], started_at: str) -> None:
    metadata = contract["run_metadata"]
    expected = contract["expected_rows"]
    cur.execute(
        """
        INSERT INTO common_market_data_run (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          prev_trade_date, mode, status, p0_count, p1_count, p2_count,
          source_scope_row_count, candidate_row_count, subscription_row_count,
          subscription_object_count, dedup_ratio, generated_by,
          market_data_pulled, market_data_fact_written,
          downstream_layers_touched, worker_started, started_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, 'execute', 'running', 0, 0, 0,
                %s, %s, %s, %s, NULL, %s,
                false, false, false, false, %s, %s)
        """,
        (
            contract["projection_run_id"],
            contract["source_condition_run_id"],
            contract["for_trade_date"],
            metadata["source_trade_date"],
            metadata["prev_trade_date"],
            int(expected.get("total") or 0),
            int(expected.get("total") or 0),
            int(expected.get("total") or 0),
            int(expected.get("total") or 0),
            metadata["generated_by"],
            started_at,
            Jsonb(
                {
                    "stage": "N3-action-confirmation-projection-writer-execute",
                    "metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
                    "projection_schema_version": contract.get("projection_schema_version"),
                    "source_subscription_run_id": contract.get("source_subscription_run_id"),
                    "source_snapshot_run_id": contract.get("source_snapshot_run_id"),
                    "source_today_minute_run_id": contract.get("source_today_minute_run_id"),
                    "source_previous_day_minute_run_id": contract.get("source_previous_day_minute_run_id"),
                    "writes_outbox": False,
                    "run_once_only": True,
                }
            ),
        ),
    )


def insert_action_confirmation_metric_rows(cur: Any, *, table: str, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    canonical_rows = [canonicalize_realtime_virtual_metric_fields(row) for row in rows]
    columns = [
        "projection_run_id",
        "projection_schema_version",
        "source_condition_run_id",
        "source_subscription_run_id",
        "source_snapshot_run_id",
        "source_snapshot_id",
        "source_snapshot_event_id",
        "source_today_minute_run_id",
        "source_previous_day_minute_run_id",
        "for_trade_date",
        "trade_date",
        "asset_kind",
        "identity_key",
        "exchange",
        "code",
        "display_code",
        "name",
        "metric_time",
        "metric_minute_label",
        "current_price",
        "current_price_source",
        "current_price_time",
        "previous_120m_body_high",
        "previous_120m_body_low",
        "previous_30m_body_high",
        "previous_30m_body_low",
        "previous_5m_body_high",
        "previous_5m_body_low",
        "previous_1m_body_high",
        "previous_1m_body_low",
        "current_1m_amount",
        "previous_1m_amount",
        "current_5m_virtual_amount",
        "previous_5m_full_amount",
        "is_first_1m_of_day",
        "is_first_5m_of_day",
        "is_first_30m_of_day",
        "is_first_120m_of_day",
        "first_1m_amount_default_pass",
        "first_5m_amount_default_pass",
        "previous_1m_period_source",
        "previous_5m_period_source",
        "previous_30m_period_source",
        "previous_120m_period_source",
        "boundary_policy_version",
        "buy_120m_price_pass",
        "buy_30m_price_pass",
        "buy_5m_price_pass",
        "buy_5m_amount_pass",
        "buy_1m_price_pass",
        "buy_1m_amount_pass",
        "sell_120m_price_pass",
        "sell_30m_price_pass",
        "sell_5m_price_pass",
        "sell_5m_amount_pass",
        "sell_1m_price_pass",
        "sell_1m_amount_pass",
        "metric_quality_status",
        "metric_ready",
        "source_fact_ids",
        "source_minute_refs",
        "previous_day_minute_refs",
        "calculation_config_hash",
        "raw_json",
    ]
    optional_jsonb_columns = {"period_source", "deterministic_pass_flags", "trace_json"}
    for column in REALTIME_VIRTUAL_METRIC_DB_COLUMNS:
        if column in columns:
            continue
        if any(column in row for row in canonical_rows):
            columns.append(column)
    payload = []
    for row in canonical_rows:
        payload.append(
            tuple(
                Jsonb(row.get(column))
                if column in {"source_fact_ids", "source_minute_refs", "previous_day_minute_refs", "raw_json", *optional_jsonb_columns}
                else row.get(column)
                for column in columns
            )
        )
    cur.executemany(
        f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        payload,
    )


def insert_action_confirmation_quality_items(cur: Any, quality_items: Sequence[Mapping[str, Any]]) -> None:
    if not quality_items:
        return
    columns = (
        "run_id",
        "source_condition_run_id",
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
    )
    rows = [
        (
            item["run_id"],
            item["source_condition_run_id"],
            item["for_trade_date"],
            item["source_trade_date"],
            item.get("data_domain") or "common",
            item["layer_scope"],
            item.get("table_name"),
            item["gate_code"],
            item["gate_name"],
            item["severity"],
            item["status"],
            item.get("expected_value"),
            item.get("actual_value"),
            item.get("identity_key"),
            Jsonb(item.get("details") or {}),
        )
        for item in quality_items
    ]
    cur.executemany(
        f"""
        INSERT INTO common_market_data_quality_item ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        rows,
    )


def format_action_confirmation_execute_report_markdown(report: Mapping[str, Any]) -> str:
    rows = (report.get("write_result") or {}).get("rows_written") or {}
    quality = report.get("quality") or {}
    return f"""# N3 Action-Confirmation Projection Writer Execute Report

Status: {report.get("result")}

```text
projection_run_id={report.get("projection_run_id")}
rows stock/index/board/total={rows.get("stock", 0)}/{rows.get("index", 0)}/{rows.get("board", 0)}/{rows.get("total", 0)}
P0/P1/P2={quality.get("p0_count", 0)}/{quality.get("p1_count", 0)}/{quality.get("p2_count", 0)}
writes_outbox=false
rollback_safe={(report.get("rollback") or {}).get("rollback_safe")}
```
"""
