"""N3-A1 current-lineage previous-day minute fill-facts executor.

This runner is a resume path for a reviewed metadata-only preload run. It keeps
the current preload_run_id, fills previous-day minute facts/status/quality, and
does not write event outbox rows or enter downstream layers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from typing import Any

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.migration_execute import stable_json_hash
from ashare_v3.market.preload_execute_contract import read_json
from ashare_v3.market.preload_plan import MINUTE_FACT_TABLES, PRELOAD_STATUS_TABLES, build_persisted_subscription_report, previous_day_subscriptions
from ashare_v3.market.previous_day_preload_execute import (
    MootdxPreviousDayMinuteAdapter,
    build_post_execute_checks,
    build_post_execute_quality_items,
    capture_preload_execute_backup,
    execute_subscription_preloads,
    format_previous_day_minute_execute_report,
    insert_quality_items,
    json_safe,
    summarize_actual_asset_counts,
    summarize_write_result,
    utc_now_iso,
    write_json,
    write_text,
)
from ashare_v3.market.previous_day_preload_execute import ensure_subscription_counts_match_contract
from ashare_v3.market.repositories import ASSET_FACT_TABLES
from ashare_v3.market.subscription_plan import ASSET_KINDS


DEFAULT_CURRENT_A1_FILL_CONTRACT_PATH = "docs/N3_A1_AFTER_N2_DISPLAY_current_previous_day_minute_execute_contract.json"
DEFAULT_CURRENT_A1_FILL_PRE_BACKUP_PATH = "docs/N3_A1_current_previous_day_minute_fill_facts_backup_before.json"
DEFAULT_CURRENT_A1_FILL_POST_BACKUP_PATH = "docs/N3_A1_current_previous_day_minute_fill_facts_backup_after.json"
DEFAULT_CURRENT_A1_FILL_STATUS_SNAPSHOT_PATH = "docs/N3_A1_current_previous_day_minute_fill_status_snapshot_before.json"
DEFAULT_CURRENT_A1_FILL_JSON_REPORT_PATH = "docs/N3_A1_current_previous_day_minute_fill_facts_execute_report.json"
DEFAULT_CURRENT_A1_FILL_MD_REPORT_PATH = "docs/N3_A1_CURRENT_PREVIOUS_DAY_MINUTE_FILL_FACTS_EXECUTE_REPORT.md"
DEFAULT_CURRENT_A1_FILL_ROLLBACK_SQL_PATH = "sql/N3_A1_AFTER_N2_DISPLAY_current_previous_day_minute_rollback.sql"

FILL_QUALITY_PREFIX = "n3_a1_current_fill_"


class PreviousDayMinutePreloadFillError(RuntimeError):
    """Raised when the current-lineage fill-facts runner violates its contract."""


def run_previous_day_minute_preload_fill_facts(
    *,
    dsn: str,
    contract_path: str = DEFAULT_CURRENT_A1_FILL_CONTRACT_PATH,
    pre_backup_path: str = DEFAULT_CURRENT_A1_FILL_PRE_BACKUP_PATH,
    post_backup_path: str = DEFAULT_CURRENT_A1_FILL_POST_BACKUP_PATH,
    status_snapshot_path: str = DEFAULT_CURRENT_A1_FILL_STATUS_SNAPSHOT_PATH,
    json_report_path: str = DEFAULT_CURRENT_A1_FILL_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_CURRENT_A1_FILL_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_CURRENT_A1_FILL_ROLLBACK_SQL_PATH,
    for_trade_date: str | None = None,
    preload_run_id: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    adapter: Any | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 100,
) -> dict[str, Any]:
    """Fill facts for the reviewed current-lineage metadata-only preload run."""

    contract = read_json(contract_path)
    ensure_fill_facts_contract(
        contract,
        execute=execute,
        user_confirmed=user_confirmed,
        preload_run_id=preload_run_id,
        for_trade_date=for_trade_date,
    )
    source_run_id = str(contract["source_run_id"])
    resolved_preload_run_id = str(contract["preload_run_id"])
    previous_day_minute_date = str(contract["previous_day_minute_date"])
    started_at = utc_now_iso()

    pre_backup = capture_fill_facts_backup(
        dsn,
        phase="before_n3_a1_current_fill",
        preload_run_id=resolved_preload_run_id,
        source_run_id=source_run_id,
        previous_day_minute_date=previous_day_minute_date,
    )
    ensure_metadata_only_fill_target(pre_backup)
    write_json(pre_backup_path, pre_backup)
    write_json(status_snapshot_path, pre_backup["preload_status_snapshot"])
    write_text(
        rollback_sql_path,
        build_status_restore_rollback_sql(
            preload_run_id=resolved_preload_run_id,
            previous_day_minute_date=previous_day_minute_date,
            status_snapshot=pre_backup["preload_status_snapshot"],
        ),
    )

    subscription_report = build_persisted_subscription_report(dsn=dsn, market_data_run_id=source_run_id)
    subscriptions = previous_day_subscriptions(subscription_report)
    ensure_subscription_counts_match_contract(subscriptions, contract)

    resolved_adapter = adapter or MootdxPreviousDayMinuteAdapter()
    object_results = execute_subscription_preloads(
        dsn=dsn,
        contract=contract,
        subscriptions=subscriptions,
        adapter=resolved_adapter,
        progress_callback=progress_callback,
        progress_every=progress_every,
    )

    data_snapshot = capture_fill_facts_backup(
        dsn,
        phase="after_n3_a1_current_fill_data_before_quality",
        preload_run_id=resolved_preload_run_id,
        source_run_id=source_run_id,
        previous_day_minute_date=previous_day_minute_date,
    )
    post_checks = build_fill_post_execute_checks(
        contract=contract,
        pre_backup=pre_backup,
        data_snapshot=data_snapshot,
        object_results=object_results,
    )
    quality_items = build_fill_quality_items(
        contract=contract,
        post_checks=post_checks,
        object_results=object_results,
    )
    quality_counts = count_quality_severities(quality_items)
    write_fill_quality_and_finalize_run(
        dsn,
        contract=contract,
        quality_items=quality_items,
        object_results=object_results,
        status="passed" if quality_counts["P0"] == 0 else "failed",
        contract_path=contract_path,
        status_snapshot_path=status_snapshot_path,
        rollback_sql_path=rollback_sql_path,
    )

    post_backup = capture_fill_facts_backup(
        dsn,
        phase="after_n3_a1_current_fill",
        preload_run_id=resolved_preload_run_id,
        source_run_id=source_run_id,
        previous_day_minute_date=previous_day_minute_date,
    )
    write_json(post_backup_path, post_backup)

    report = {
        "stage": "N3-A1-current-lineage-fill-facts",
        "layer_role": "N3_market_data",
        "execution_mode": "previous_day_minute_preload_fill_facts_resume",
        "source_run_id": source_run_id,
        "preload_run_id": resolved_preload_run_id,
        "source_condition_run_id": contract["source_condition_run_id"],
        "for_trade_date": contract["for_trade_date"],
        "source_trade_date": contract["source_trade_date"],
        "previous_day_minute_date": previous_day_minute_date,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "contract_path": contract_path,
        "pre_backup_path": pre_backup_path,
        "post_backup_path": post_backup_path,
        "status_snapshot_path": status_snapshot_path,
        "rollback_sql_path": rollback_sql_path,
        "expected_asset_counts": contract["expected_asset_counts"],
        "actual_asset_counts": summarize_actual_asset_counts(object_results),
        "write_result": summarize_write_result(object_results, quality_items),
        "post_checks": post_checks,
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "pre_execute": {
            "active_snapshot_hash": stable_json_hash(pre_backup["active_snapshot"]),
            "target_preload_run_row_counts": pre_backup["target_preload_run_row_counts"],
            "outbox_rows_for_run": pre_backup["outbox_rows_for_run"],
            "inbox_rows_for_run": pre_backup["inbox_rows_for_run"],
            "global_outbox_count_observed_not_blocking": pre_backup["common_event_outbox_row_count"],
        },
        "post_execute": {
            "active_snapshot_hash": stable_json_hash(post_backup["active_snapshot"]),
            "target_preload_run_row_counts": post_backup["target_preload_run_row_counts"],
            "outbox_rows_for_run": post_backup["outbox_rows_for_run"],
            "inbox_rows_for_run": post_backup["inbox_rows_for_run"],
            "preload_run_row": post_backup["preload_run_row"],
        },
        "side_effects": {
            "writes_performed": True,
            "migration_executed": False,
            "market_data_pulled": True,
            "market_data_fact_written": any(int(item.get("minute_rows_written") or 0) > 0 for item in object_results),
            "event_outbox_written": False,
            "event_inbox_written": False,
            "projection_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_fill_facts_execute_report(report))
    return report


def ensure_fill_facts_contract(
    contract: Mapping[str, Any],
    *,
    execute: bool,
    user_confirmed: bool,
    preload_run_id: str | None,
    for_trade_date: str | None,
) -> None:
    if not execute:
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts requires explicit --execute")
    if not user_confirmed:
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts requires explicit --user-confirmed")
    if contract.get("stage") != "N3-A1-current-lineage-preflight-correction":
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: contract stage mismatch")
    if contract.get("layer_role") != "N3_market_data":
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: layer_role mismatch")
    if contract.get("result") != "PREFLIGHT_PASS":
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: preflight did not pass")
    if contract.get("execution_mode") != "previous_day_minute_preload_fill_facts_for_existing_metadata_run":
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: execution_mode mismatch")
    if contract.get("recommended_metadata_only_run_handling") != "scheme_b_fill_facts_resume_existing_run":
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: scheme B is not selected")
    if bool(contract.get("writes_outbox")) or contract.get("generated_event_types") not in ([], None):
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: contract must not write outbox")
    if int((contract.get("quality") or {}).get("p0_count") or 0) > 0:
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: contract has P0 findings")
    if preload_run_id and preload_run_id != str(contract.get("preload_run_id") or ""):
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: CLI preload_run_id does not match contract")
    if for_trade_date and for_trade_date != str(contract.get("for_trade_date") or ""):
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: CLI for_trade_date does not match contract")


def ensure_metadata_only_fill_target(backup: Mapping[str, Any]) -> None:
    preload_run_id = str(backup.get("preload_run_id") or "")
    if not backup.get("preload_run_exists"):
        raise PreviousDayMinutePreloadFillError(f"N3-A1 fill-facts blocked: preload run missing: {preload_run_id}")
    run_row = backup.get("preload_run_row") or {}
    if run_row.get("status") != "passed":
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: preload run status is not passed")
    if bool(run_row.get("market_data_pulled")) or bool(run_row.get("market_data_fact_written")):
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: preload run is not metadata-only")
    if bool(run_row.get("downstream_layers_touched")) or bool(run_row.get("worker_started")):
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: downstream layer or worker flag is set")
    counts_by_asset = backup.get("target_preload_run_row_counts_by_asset") or {}
    minute_rows = {
        asset_kind: int((counts_by_asset.get(asset_kind) or {}).get("minute_row_count") or 0)
        for asset_kind in ASSET_KINDS
    }
    if any(count != 0 for count in minute_rows.values()):
        raise PreviousDayMinutePreloadFillError(f"N3-A1 fill-facts blocked: minute fact rows already exist: {minute_rows}")
    status_objects = {
        asset_kind: int((counts_by_asset.get(asset_kind) or {}).get("preload_status_object_count") or 0)
        for asset_kind in ASSET_KINDS
    }
    if sum(status_objects.values()) == 0:
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: metadata status rows are missing")
    if int(backup.get("outbox_rows_for_run") or 0) != 0:
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: outbox rows exist for this preload_run_id")
    if int(backup.get("inbox_rows_for_run") or 0) != 0:
        raise PreviousDayMinutePreloadFillError("N3-A1 fill-facts blocked: inbox rows exist for this preload_run_id")


def capture_fill_facts_backup(
    dsn: str,
    *,
    phase: str,
    preload_run_id: str,
    source_run_id: str,
    previous_day_minute_date: str,
) -> dict[str, Any]:
    backup = capture_preload_execute_backup(
        dsn,
        phase=phase,
        preload_run_id=preload_run_id,
        source_run_id=source_run_id,
        previous_day_minute_date=previous_day_minute_date,
    )
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        backup["outbox_rows_for_run"] = fetch_outbox_count_for_run(cur, preload_run_id)
        backup["inbox_rows_for_run"] = fetch_inbox_count_for_run(cur, preload_run_id)
        backup["preload_status_snapshot"] = fetch_preload_status_snapshot(
            cur,
            preload_run_id=preload_run_id,
            trade_date=previous_day_minute_date,
        )
    return backup


def fetch_outbox_count_for_run(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def fetch_inbox_count_for_run(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def fetch_preload_status_snapshot(cur: Any, *, preload_run_id: str, trade_date: str) -> dict[str, list[dict[str, Any]]]:
    snapshot: dict[str, list[dict[str, Any]]] = {}
    for asset_kind in ASSET_KINDS:
        table_name, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["preload_status"]
        cur.execute(
            f"""
            SELECT run_id, subscription_id, source_condition_run_id, for_trade_date, trade_date,
                   {identity_column}, exchange, code, display_code, name,
                   expected_bar_count, actual_bar_count, missing_bar_count,
                   first_bar_time, last_bar_time, status, quality_status, source_adapter,
                   error_message, source_scope_ids, source_condition_pool_ids, raw_json
            FROM {table_name}
            WHERE run_id = %s AND trade_date = %s
            ORDER BY {identity_column}, source_adapter
            """,
            (preload_run_id, trade_date),
        )
        snapshot[asset_kind] = [json_safe(dict(row)) for row in cur.fetchall()]
    return snapshot


def build_fill_post_execute_checks(
    *,
    contract: Mapping[str, Any],
    pre_backup: Mapping[str, Any],
    data_snapshot: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    checks = build_post_execute_checks(
        contract=contract,
        pre_backup=pre_backup,
        data_snapshot=data_snapshot,
        object_results=object_results,
    )
    checks["n3_a1_outbox_rows_zero"] = int(pre_backup.get("outbox_rows_for_run") or 0) == 0 and int(
        data_snapshot.get("outbox_rows_for_run") or 0
    ) == 0
    checks["n3_a1_inbox_rows_zero"] = int(pre_backup.get("inbox_rows_for_run") or 0) == 0 and int(
        data_snapshot.get("inbox_rows_for_run") or 0
    ) == 0
    checks["n3_a1_global_outbox_count_observed_not_blocking"] = {
        "before": int(pre_backup.get("common_event_outbox_row_count") or 0),
        "after": int(data_snapshot.get("common_event_outbox_row_count") or 0),
    }
    return checks


def build_fill_quality_items(
    *,
    contract: Mapping[str, Any],
    post_checks: Mapping[str, Any],
    object_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    items = build_post_execute_quality_items(
        contract=contract,
        post_checks=post_checks,
        object_results=object_results,
    )
    items.append(
        quality_item(
            "P0",
            "passed" if post_checks["n3_a1_inbox_rows_zero"] else "failed",
            "n3_a1_inbox_rows_zero",
            "N3-A1 fill-facts must not create inbox consumption rows",
            expected="0",
            actual="0" if post_checks["n3_a1_inbox_rows_zero"] else "non-zero",
        )
    )
    return prefix_fill_quality_items(items)


def prefix_fill_quality_items(quality_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in quality_items:
        row = dict(item)
        gate_code = str(row.get("gate_code") or "")
        if not gate_code.startswith(FILL_QUALITY_PREFIX):
            gate_code = gate_code.removeprefix("n3_a1_")
            row["gate_code"] = f"{FILL_QUALITY_PREFIX}{gate_code}"
        output.append(row)
    return output


def write_fill_quality_and_finalize_run(
    dsn: str,
    *,
    contract: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
    object_results: Sequence[Mapping[str, Any]],
    status: str,
    contract_path: str,
    status_snapshot_path: str,
    rollback_sql_path: str,
) -> None:
    quality_counts = count_quality_severities(quality_items)
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                insert_quality_items(cur, contract=contract, quality_items=quality_items)
                cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status = %s,
                        p0_count = %s,
                        p1_count = %s,
                        p2_count = %s,
                        market_data_pulled = true,
                        market_data_fact_written = %s,
                        downstream_layers_touched = false,
                        worker_started = false,
                        finished_at = now(),
                        updated_at = now(),
                        raw_json = %s
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        quality_counts["P0"],
                        quality_counts["P1"],
                        quality_counts["P2"],
                        any(int(row.get("minute_rows_written") or 0) > 0 for row in object_results),
                        Jsonb(
                            {
                                "stage": "N3-A1-current-lineage-fill-facts",
                                "source_run_id": contract["source_run_id"],
                                "preload_run_id": contract["preload_run_id"],
                                "execution_mode": "previous_day_minute_preload_fill_facts_resume",
                                "contract_path": contract_path,
                                "status_snapshot_path": status_snapshot_path,
                                "rollback_sql_path": rollback_sql_path,
                                "writes_outbox": False,
                                "generated_event_types": [],
                                "write_result": summarize_write_result(object_results, quality_items),
                                "actual_asset_counts": summarize_actual_asset_counts(object_results),
                            }
                        ),
                        contract["preload_run_id"],
                    ),
                )


def build_status_restore_rollback_sql(
    *,
    preload_run_id: str,
    previous_day_minute_date: str,
    status_snapshot: Mapping[str, Sequence[Mapping[str, Any]]],
) -> str:
    lines = [
        "-- N3-A1 current-lineage fill-facts rollback.",
        "-- Restores the metadata-only preload status snapshot captured before fill.",
        "BEGIN;",
        "",
        "DELETE FROM common_market_data_quality_item",
        f"WHERE run_id = {sql_literal(preload_run_id)}",
        f"  AND gate_code LIKE {sql_literal(FILL_QUALITY_PREFIX + '%')};",
        "",
    ]
    for asset_kind in ASSET_KINDS:
        table_name = MINUTE_FACT_TABLES[asset_kind]
        lines.extend(
            [
                f"DELETE FROM {table_name}",
                f"WHERE run_id = {sql_literal(preload_run_id)}",
                f"  AND trade_date = {sql_literal(previous_day_minute_date)}",
                "  AND is_previous_day_preload = true;",
                "",
            ]
        )
    for asset_kind in ASSET_KINDS:
        table_name = PRELOAD_STATUS_TABLES[asset_kind]
        identity_column = ASSET_FACT_TABLES[asset_kind]["preload_status"][1]
        rows = list(status_snapshot.get(asset_kind) or [])
        lines.extend(
            [
                f"DELETE FROM {table_name}",
                f"WHERE run_id = {sql_literal(preload_run_id)}",
                f"  AND trade_date = {sql_literal(previous_day_minute_date)};",
                "",
            ]
        )
        if rows:
            columns = status_restore_columns(identity_column)
            values = ",\n".join(f"  ({', '.join(sql_value(row.get(column)) for column in columns)})" for row in rows)
            update_columns = tuple(column for column in columns if column not in {"run_id", "trade_date", identity_column, "source_adapter"})
            assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
            lines.extend(
                [
                    f"INSERT INTO {table_name} ({', '.join(columns)})",
                    "VALUES",
                    values,
                    f"ON CONFLICT (run_id, trade_date, {identity_column}, source_adapter)",
                    f"DO UPDATE SET {assignments};",
                    "",
                ]
            )
    lines.extend(
        [
            "UPDATE common_market_data_run",
            "SET status = 'passed',",
            "    p0_count = 0,",
            "    p1_count = 2,",
            "    p2_count = 0,",
            "    market_data_pulled = false,",
            "    market_data_fact_written = false,",
            "    downstream_layers_touched = false,",
            "    worker_started = false,",
            "    finished_at = NULL,",
            "    updated_at = now(),",
            "    raw_json = jsonb_set(",
            "      jsonb_set(COALESCE(raw_json, '{}'::jsonb), '{market_data_pulled}', 'false'::jsonb, true),",
            "      '{market_data_fact_written}', 'false'::jsonb, true",
            "    )",
            f"WHERE run_id = {sql_literal(preload_run_id)};",
            "",
            "COMMIT;",
            "",
        ]
    )
    return "\n".join(lines)


def status_restore_columns(identity_column: str) -> tuple[str, ...]:
    return (
        "run_id",
        "subscription_id",
        "source_condition_run_id",
        "for_trade_date",
        "trade_date",
        identity_column,
        "exchange",
        "code",
        "display_code",
        "name",
        "expected_bar_count",
        "actual_bar_count",
        "missing_bar_count",
        "first_bar_time",
        "last_bar_time",
        "status",
        "quality_status",
        "source_adapter",
        "error_message",
        "source_scope_ids",
        "source_condition_pool_ids",
        "raw_json",
    )


def sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list) and all(isinstance(item, int) for item in value):
        return f"ARRAY[{', '.join(str(item) for item in value)}]::BIGINT[]"
    if isinstance(value, (dict, list)):
        return f"{sql_literal(json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True))}::jsonb"
    return sql_literal(str(value))


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def format_fill_facts_execute_report(report: Mapping[str, Any]) -> str:
    lines = format_previous_day_minute_execute_report(report).splitlines()
    if lines:
        lines[0] = "# N3-A1 Current-Lineage Previous-Day Minute Fill-Facts Execute Report"
    if "## Rollback" in lines:
        lines = lines[: lines.index("## Rollback")]
    lines.extend(
        [
            "## Rollback",
            "",
            f"- rollback_sql_path: `{report['rollback_sql_path']}`",
            "- rollback key: current `preload_run_id + trade_date + is_previous_day_preload=true`.",
            "- status rows restore from the captured metadata-only snapshot.",
            "- common_event_outbox is not touched by N3-A1 fill-facts rollback.",
            "",
            "## Fill-Facts Resume",
            "",
            f"- status_snapshot_path: `{report['status_snapshot_path']}`",
            "- common_event_outbox is not written or consumed by this runner.",
            "",
        ]
    )
    return "\n".join(lines)
