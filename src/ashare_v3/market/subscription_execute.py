"""N3-6 executor for market-data subscription control rows.

This stage persists the already reviewed N3-0 subscription dry-run output into
N3 control tables only. It does not pull quotes, write market facts, emit
outbox events, start workers, or enter downstream layers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_execute_connect
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.migration_execute import (
    N3_TARGET_TABLES,
    fetch_n1_n2_active_snapshot,
    fetch_n3_target_row_counts,
    stable_json_hash,
)
from ashare_v3.market.subscription_plan import build_market_data_subscription_plan_dry_run


DEFAULT_N3_6_PRE_BACKUP_PATH = "docs/N3_6_subscription_execute_backup_before.json"
DEFAULT_N3_6_POST_BACKUP_PATH = "docs/N3_6_subscription_execute_backup_after.json"
DEFAULT_N3_6_JSON_REPORT_PATH = "docs/N3_6_market_data_subscription_execute_report.json"
DEFAULT_N3_6_MD_REPORT_PATH = "docs/N3_6_MARKET_DATA_SUBSCRIPTION_EXECUTE_REPORT.md"

N3_CONTROL_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "common_market_data_subscription_candidate",
    "common_market_data_subscription",
    "common_market_data_pull_plan",
)
N3_FACT_AND_EVENT_TABLES = (
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_previous_day_minute_preload_status",
    "index_previous_day_minute_preload_status",
    "board_previous_day_minute_preload_status",
    "common_event_ledger",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
)


def run_market_data_subscription_execute(
    *,
    dsn: str,
    condition_run_id: str | None = None,
    source_trade_date: str | None = None,
    for_trade_date: str | None = None,
    execute_run_id: str | None = None,
    pre_backup_path: str = DEFAULT_N3_6_PRE_BACKUP_PATH,
    post_backup_path: str = DEFAULT_N3_6_POST_BACKUP_PATH,
    json_report_path: str = DEFAULT_N3_6_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N3_6_MD_REPORT_PATH,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    dry_run_report = build_market_data_subscription_plan_dry_run(
        dsn=dsn,
        run_id=condition_run_id,
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        include_rows=True,
    )
    ensure_executable_dry_run_report(dry_run_report)
    resolved_run_id = execute_run_id or derive_execute_run_id(dry_run_report)

    pre_backup = capture_subscription_execution_backup(dsn, phase="before_n3_6", execute_run_id=resolved_run_id)
    if bool(pre_backup["target_run_exists"]):
        raise RuntimeError(f"N3-6 blocked: market data run already exists: {resolved_run_id}")
    write_json(pre_backup_path, pre_backup)

    write_result = persist_subscription_plan(
        dsn=dsn,
        dry_run_report=dry_run_report,
        execute_run_id=resolved_run_id,
    )

    post_backup = capture_subscription_execution_backup(dsn, phase="after_n3_6", execute_run_id=resolved_run_id)
    write_json(post_backup_path, post_backup)

    post_checks = build_post_subscription_execute_checks(
        pre_backup=pre_backup,
        post_backup=post_backup,
        dry_run_report=dry_run_report,
        write_result=write_result,
        execute_run_id=resolved_run_id,
    )
    post_quality_items = build_post_quality_items(post_checks)
    all_quality_items = list(dry_run_report["quality"]["items"]) + post_quality_items
    severity_counts = count_quality_severities(all_quality_items)
    report = {
        "stage": "N3-6",
        "layer_role": "N3_market_data",
        "execution_mode": "market_data_subscription_pull_plan_execute",
        "market_data_run_id": resolved_run_id,
        "source_condition_run_id": dry_run_report["source_condition_run_id"],
        "source_trade_date": dry_run_report["source_trade_date"],
        "for_trade_date": dry_run_report["for_trade_date"],
        "prev_trade_date": dry_run_report["prev_trade_date"],
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "pre_backup_path": pre_backup_path,
        "post_backup_path": post_backup_path,
        "dry_run_summary": summarize_dry_run_report(dry_run_report),
        "write_result": write_result,
        "pre_execute": {
            "active_snapshot_hash": stable_json_hash(pre_backup["active_snapshot"]),
            "target_run_exists": pre_backup["target_run_exists"],
            "n3_fact_and_event_row_counts": pre_backup["n3_fact_and_event_row_counts"],
        },
        "post_execute": {
            "active_snapshot_hash": stable_json_hash(post_backup["active_snapshot"]),
            "target_run_row_counts": post_backup["target_run_row_counts"],
            "n3_fact_and_event_row_counts": post_backup["n3_fact_and_event_row_counts"],
            "market_data_run_row": post_backup["market_data_run_row"],
        },
        "post_checks": post_checks,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": all_quality_items,
        },
        "side_effects": {
            "writes_performed": True,
            "migration_executed": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_market_data_subscription_execute_report(report))
    return report


def ensure_executable_dry_run_report(report: Mapping[str, Any]) -> None:
    if report.get("mode") != "dry_run":
        raise RuntimeError("N3-6 blocked: input report is not an N3-0 dry-run report")
    if bool(report.get("blocked")) or not bool(report.get("passed")):
        raise RuntimeError("N3-6 blocked: N3-0 dry-run did not pass")
    if int(report["quality"]["p0_count"]) > 0:
        raise RuntimeError("N3-6 blocked: N3-0 dry-run has P0 quality findings")
    for section_name in (
        "market_data_subscription_candidate",
        "market_data_subscription_dedup",
        "market_data_pull_plan",
    ):
        section = report.get(section_name) or {}
        if not bool(section.get("rows_included")):
            raise RuntimeError(f"N3-6 blocked: {section_name} rows are not included")
        if len(section.get("rows") or []) != int(section.get("row_count") or 0):
            raise RuntimeError(f"N3-6 blocked: {section_name} row_count does not match included rows")


def derive_execute_run_id(report: Mapping[str, Any]) -> str:
    source_condition_run_id = str(report.get("source_condition_run_id") or "")
    for_trade_date = str(report.get("for_trade_date") or "")
    if not source_condition_run_id or not for_trade_date:
        raise RuntimeError("N3-6 blocked: dry-run report missing source_condition_run_id or for_trade_date")
    return f"market_data_subscription_{for_trade_date}_{source_condition_run_id}"


def persist_subscription_plan(
    *,
    dsn: str,
    dry_run_report: Mapping[str, Any],
    execute_run_id: str,
) -> dict[str, Any]:
    with audited_n3_market_execute_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                if run_exists(cur, execute_run_id):
                    raise RuntimeError(f"N3-6 blocked: market data run already exists: {execute_run_id}")
                insert_market_data_run(cur, dry_run_report, execute_run_id)
                quality_count = insert_quality_items(cur, dry_run_report, execute_run_id)
                candidate_count = insert_subscription_candidates(cur, dry_run_report, execute_run_id)
                subscription_ref_to_id = insert_subscriptions(cur, dry_run_report, execute_run_id)
                pull_plan_count = insert_pull_plans(
                    cur,
                    dry_run_report,
                    execute_run_id,
                    subscription_ref_to_id,
                )
    return {
        "market_data_run_rows_written": 1,
        "quality_item_rows_written": quality_count,
        "candidate_rows_written": candidate_count,
        "subscription_rows_written": len(subscription_ref_to_id),
        "pull_plan_rows_written": pull_plan_count,
        "market_data_fact_rows_written": 0,
        "event_outbox_rows_written": 0,
    }


def run_exists(cur: Any, run_id: str) -> bool:
    cur.execute("SELECT 1 FROM common_market_data_run WHERE run_id = %s LIMIT 1", (run_id,))
    return cur.fetchone() is not None


def insert_market_data_run(cur: Any, report: Mapping[str, Any], execute_run_id: str) -> None:
    columns = (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "mode",
        "status",
        "p0_count",
        "p1_count",
        "p2_count",
        "source_scope_row_count",
        "candidate_row_count",
        "subscription_row_count",
        "subscription_object_count",
        "dedup_ratio",
        "generated_by",
        "market_data_pulled",
        "market_data_fact_written",
        "downstream_layers_touched",
        "worker_started",
        "finished_at",
        "raw_json",
    )
    values = (
        execute_run_id,
        report["source_condition_run_id"],
        report["for_trade_date"],
        report["source_trade_date"],
        report["prev_trade_date"],
        "execute",
        "passed",
        int(report["quality"]["p0_count"]),
        int(report["quality"]["p1_count"]),
        int(report["quality"]["p2_count"]),
        int(report["source_scope_row_count"]),
        int(report["candidate_row_count"]),
        int(report["subscription_row_count"]),
        int(report["subscription_object_count"]),
        report.get("dedup_ratio"),
        "market_data_layer",
        False,
        False,
        False,
        False,
        datetime.now(timezone.utc),
        Jsonb(build_run_raw_json(report, execute_run_id)),
    )
    cur.execute(
        f"""
        INSERT INTO common_market_data_run ({", ".join(columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        """,
        values,
    )


def insert_quality_items(cur: Any, report: Mapping[str, Any], execute_run_id: str) -> int:
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
    rows = []
    for item in report["quality"]["items"]:
        gate_code = str(item.get("gate_code") or "")
        rows.append(
            (
                execute_run_id,
                report["source_condition_run_id"],
                report["for_trade_date"],
                report["source_trade_date"],
                infer_data_domain(gate_code),
                infer_layer_scope(gate_code),
                infer_table_name(gate_code),
                gate_code,
                item.get("gate_name"),
                item.get("severity"),
                item.get("status"),
                item.get("expected_value"),
                item.get("actual_value"),
                item.get("identity_key"),
                Jsonb(item.get("details") or {}),
            )
        )
    if rows:
        cur.executemany(
            f"""
            INSERT INTO common_market_data_quality_item ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
            """,
            rows,
        )
    return len(rows)


def insert_subscription_candidates(cur: Any, report: Mapping[str, Any], execute_run_id: str) -> int:
    rows = (report["market_data_subscription_candidate"] or {}).get("rows") or []
    columns = (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "asset_kind",
        "identity_key",
        "exchange",
        "code",
        "display_code",
        "name",
        "required_data_kind",
        "data_trade_date",
        "source_scope_table",
        "source_scope_id",
        "source_condition_pool_id",
        "direction",
        "condition_key",
        "allowed_signal_types",
        "source_scope_required_flags",
        "candidate_status",
        "selected_reason",
        "raw_json",
    )
    values = []
    for row in rows:
        values.append(
            (
                execute_run_id,
                row["source_condition_run_id"],
                row["for_trade_date"],
                row["source_trade_date"],
                row["prev_trade_date"],
                row["asset_kind"],
                row["identity_key"],
                row["exchange"],
                row["code"],
                row.get("display_code"),
                row.get("name"),
                row["required_data_kind"],
                row["data_trade_date"],
                row["source_scope_table"],
                int(row["source_scope_id"]),
                int(row["source_condition_pool_id"]),
                row["direction"],
                row["condition_key"],
                list(row.get("allowed_signal_types") or []),
                Jsonb(row.get("source_scope_required_flags") or {}),
                row.get("candidate_status") or "planned",
                row.get("selected_reason"),
                Jsonb(build_candidate_raw_json(row)),
            )
        )
    if values:
        cur.executemany(
            f"""
            INSERT INTO common_market_data_subscription_candidate ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
            """,
            values,
        )
    return len(values)


def insert_subscriptions(cur: Any, report: Mapping[str, Any], execute_run_id: str) -> dict[str, int]:
    rows = (report["market_data_subscription_dedup"] or {}).get("rows") or []
    columns = (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "asset_kind",
        "identity_key",
        "exchange",
        "code",
        "display_code",
        "name",
        "required_data_kind",
        "data_trade_date",
        "source_scope_row_count",
        "source_scope_tables",
        "source_scope_ids",
        "source_condition_pool_ids",
        "condition_keys",
        "directions",
        "allowed_signal_types",
        "priority",
        "status",
        "selected_reason",
        "raw_json",
    )
    mapping: dict[str, int] = {}
    for row in rows:
        values = (
            execute_run_id,
            row["source_condition_run_id"],
            row["for_trade_date"],
            row["source_trade_date"],
            row["prev_trade_date"],
            row["asset_kind"],
            row["identity_key"],
            row["exchange"],
            row["code"],
            row.get("display_code"),
            row.get("name"),
            row["required_data_kind"],
            row["data_trade_date"],
            int(row["source_scope_row_count"]),
            list(row.get("source_scope_tables") or []),
            [int(item) for item in row.get("source_scope_ids") or []],
            [int(item) for item in row.get("source_condition_pool_ids") or []],
            list(row.get("condition_keys") or []),
            list(row.get("directions") or []),
            list(row.get("allowed_signal_types") or []),
            int(row.get("priority") or 100),
            row.get("status") or "planned",
            row.get("selected_reason"),
            Jsonb(build_subscription_raw_json(row)),
        )
        cur.execute(
            f"""
            INSERT INTO common_market_data_subscription ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
            RETURNING subscription_id
            """,
            values,
        )
        fetched = cur.fetchone()
        mapping[str(row["subscription_ref"])] = int(fetched["subscription_id"])
    return mapping


def insert_pull_plans(
    cur: Any,
    report: Mapping[str, Any],
    execute_run_id: str,
    subscription_ref_to_id: Mapping[str, int],
) -> int:
    rows = (report["market_data_pull_plan"] or {}).get("rows") or []
    columns = (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "asset_kind",
        "required_data_kind",
        "data_trade_date",
        "adapter_name",
        "subscription_count",
        "object_count",
        "subscription_ids_sample",
        "subscription_refs_sample",
        "identity_keys_sample",
        "plan_status",
        "execute_allowed",
        "selected_reason",
        "raw_json",
    )
    values = []
    for row in rows:
        refs_sample = [str(item) for item in row.get("subscription_refs_sample") or []]
        values.append(
            (
                execute_run_id,
                row["source_condition_run_id"],
                row["for_trade_date"],
                row["source_trade_date"],
                row["prev_trade_date"],
                row["asset_kind"],
                row["required_data_kind"],
                row["data_trade_date"],
                row["adapter_name"],
                int(row["subscription_count"]),
                int(row["object_count"]),
                [int(subscription_ref_to_id[ref]) for ref in refs_sample if ref in subscription_ref_to_id],
                Jsonb(refs_sample),
                Jsonb(row.get("identity_keys_sample") or []),
                row.get("plan_status") or "planned",
                False,
                row.get("selected_reason"),
                Jsonb(build_pull_plan_raw_json(row)),
            )
        )
    if values:
        cur.executemany(
            f"""
            INSERT INTO common_market_data_pull_plan ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
            """,
            values,
        )
    return len(values)


def build_candidate_raw_json(row: Mapping[str, Any]) -> dict[str, Any]:
    return _merge_source_trace(
        {
            "candidate_ref": row.get("candidate_ref"),
            "source_scope_ref": row.get("source_scope_ref"),
            "dry_run_run_id": row.get("run_id"),
        },
        row.get("raw_json"),
    )


def build_subscription_raw_json(row: Mapping[str, Any]) -> dict[str, Any]:
    return _merge_source_trace(
        {
            "subscription_ref": row.get("subscription_ref"),
            "source_scope_refs": row.get("source_scope_refs") or [],
            "data_trade_dates": row.get("data_trade_dates") or [],
            "dry_run_run_id": row.get("run_id"),
        },
        row.get("raw_json"),
    )


def build_pull_plan_raw_json(row: Mapping[str, Any]) -> dict[str, Any]:
    return _merge_source_trace(
        {
            "pull_plan_ref": row.get("pull_plan_ref"),
            "dry_run_run_id": row.get("run_id"),
        },
        row.get("raw_json"),
    )


def _merge_source_trace(base: Mapping[str, Any], source_trace: Any) -> dict[str, Any]:
    payload = dict(base)
    if source_trace in (None, ""):
        return payload
    if isinstance(source_trace, Mapping):
        payload["source_trace"] = dict(source_trace)
    else:
        payload["source_trace"] = {"value": source_trace}
    return payload


def capture_subscription_execution_backup(dsn: str, *, phase: str, execute_run_id: str) -> dict[str, Any]:
    with audited_n3_market_execute_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return {
            "phase": phase,
            "captured_at": utc_now_iso(),
            "execute_run_id": execute_run_id,
            "active_snapshot": fetch_n1_n2_active_snapshot(cur),
            "n3_target_row_counts": fetch_n3_target_row_counts(cur),
            "target_run_exists": run_exists(cur, execute_run_id),
            "target_run_row_counts": fetch_target_run_row_counts(cur, execute_run_id),
            "n3_fact_and_event_row_counts": fetch_table_row_counts(cur, N3_FACT_AND_EVENT_TABLES),
            "market_data_run_row": fetch_market_data_run_row(cur, execute_run_id),
        }


def fetch_target_run_row_counts(cur: Any, run_id: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for table_name in N3_CONTROL_TABLES:
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE run_id = %s", (run_id,))
        output[table_name] = int(cur.fetchone()["row_count"])
    return output


def fetch_table_row_counts(cur: Any, table_names: Sequence[str]) -> dict[str, int]:
    output: dict[str, int] = {}
    for table_name in table_names:
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
        output[table_name] = int(cur.fetchone()["row_count"])
    return output


def fetch_market_data_run_row(cur: Any, run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
               prev_trade_date, mode, status, p0_count, p1_count, p2_count,
               source_scope_row_count, candidate_row_count, subscription_row_count,
               subscription_object_count, dedup_ratio, market_data_pulled,
               market_data_fact_written, downstream_layers_touched, worker_started
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def build_post_subscription_execute_checks(
    *,
    pre_backup: Mapping[str, Any],
    post_backup: Mapping[str, Any],
    dry_run_report: Mapping[str, Any],
    write_result: Mapping[str, Any],
    execute_run_id: str,
) -> dict[str, bool]:
    run_counts = post_backup["target_run_row_counts"]
    run_row = post_backup.get("market_data_run_row") or {}
    expected_quality_count = len(dry_run_report["quality"]["items"])
    return {
        "n3_6_preflight_p0_zero": int(dry_run_report["quality"]["p0_count"]) == 0,
        "n3_6_target_run_created_once": run_counts["common_market_data_run"] == 1,
        "n3_6_candidate_row_count_matches": run_counts["common_market_data_subscription_candidate"]
        == int(dry_run_report["candidate_row_count"])
        == int(write_result["candidate_rows_written"]),
        "n3_6_subscription_row_count_matches": run_counts["common_market_data_subscription"]
        == int(dry_run_report["subscription_row_count"])
        == int(write_result["subscription_rows_written"]),
        "n3_6_pull_plan_row_count_matches": run_counts["common_market_data_pull_plan"]
        == int(dry_run_report["market_data_pull_plan_row_count"])
        == int(write_result["pull_plan_rows_written"]),
        "n3_6_quality_item_count_matches": run_counts["common_market_data_quality_item"]
        == expected_quality_count
        == int(write_result["quality_item_rows_written"]),
        "n3_6_run_id_matches_expected": str(run_row.get("run_id") or "") == execute_run_id,
        "n3_6_run_mode_execute": run_row.get("mode") == "execute",
        "n3_6_run_status_passed": run_row.get("status") == "passed",
        "n3_6_run_flags_no_market_pull_or_fact": run_row.get("market_data_pulled") is False
        and run_row.get("market_data_fact_written") is False
        and run_row.get("downstream_layers_touched") is False
        and run_row.get("worker_started") is False,
        "n3_6_n1_n2_active_snapshot_unchanged": pre_backup["active_snapshot"] == post_backup["active_snapshot"],
        "n3_6_no_market_fact_or_event_rows_written": pre_backup["n3_fact_and_event_row_counts"]
        == post_backup["n3_fact_and_event_row_counts"],
    }


def build_post_quality_items(post_checks: Mapping[str, bool]) -> list[dict[str, Any]]:
    return [
        quality_item(
            "P0",
            "passed" if passed else "failed",
            gate_code,
            f"N3-6 post execute check: {gate_code}",
            expected="true",
            actual=str(passed).lower(),
        )
        for gate_code, passed in post_checks.items()
    ]


def summarize_dry_run_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "market_data_run_id": report.get("market_data_run_id"),
        "source_scope_row_count": report.get("source_scope_row_count"),
        "source_scope_row_count_by_asset_kind": report.get("source_scope_row_count_by_asset_kind"),
        "subscription_candidate_count": report.get("subscription_candidate_count"),
        "dedup_subscription_count": report.get("dedup_subscription_count"),
        "subscription_object_count": report.get("subscription_object_count"),
        "object_count_by_asset_kind": report.get("object_count_by_asset_kind"),
        "required_data_kind_counts": report.get("required_data_kind_counts"),
        "previous_day_minute_required_count": report.get("previous_day_minute_required_count"),
        "previous_day_minute_date_counts": report.get("previous_day_minute_date_counts"),
        "dedup_ratio": report.get("dedup_ratio"),
        "dedup_reduction_ratio": report.get("dedup_reduction_ratio"),
        "market_data_pull_plan_row_count": report.get("market_data_pull_plan_row_count"),
        "quality": {
            "p0_count": report["quality"]["p0_count"],
            "p1_count": report["quality"]["p1_count"],
            "p2_count": report["quality"]["p2_count"],
        },
    }


def build_run_raw_json(report: Mapping[str, Any], execute_run_id: str) -> dict[str, Any]:
    return {
        "stage": "N3-6",
        "execute_run_id": execute_run_id,
        "dry_run_summary": summarize_dry_run_report(report),
        "dry_run_market_data_run_id": report.get("market_data_run_id"),
        "trade_calendar_detail_check": report.get("trade_calendar_detail_check"),
        "source_scope_ids_sample": report.get("source_scope_ids_sample"),
        "source_condition_pool_ids_sample": report.get("source_condition_pool_ids_sample"),
        "boundary": {
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
    }


def infer_data_domain(gate_code: str) -> str:
    for domain in ("stock", "index", "board"):
        if gate_code.startswith(f"{domain}_"):
            return domain
    return "common"


def infer_layer_scope(gate_code: str) -> str:
    if gate_code.startswith("active_condition_run"):
        return "active_condition_run"
    if gate_code.startswith("candidate_"):
        return "market_data_subscription_candidate"
    if gate_code.startswith("subscription_") or gate_code.startswith("dedup_"):
        return "market_data_subscription_dedup"
    if gate_code.startswith("pull_plan_") or gate_code.startswith("market_data_pull_plan"):
        return "market_data_pull_plan"
    return "market_data_run"


def infer_table_name(gate_code: str) -> str | None:
    for table_name in (
        "stock_minute_target_scope",
        "index_minute_target_scope",
        "board_minute_target_scope",
    ):
        if gate_code.startswith(table_name):
            return table_name
    return None


def format_market_data_subscription_execute_report(report: Mapping[str, Any]) -> str:
    dry = report["dry_run_summary"]
    quality = report["quality"]
    write = report["write_result"]
    lines = [
        "# N3-6 Market Data Subscription Execute Report",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- market_data_run_id: {report['market_data_run_id']}",
        f"- source_condition_run_id: {report['source_condition_run_id']}",
        f"- for_trade_date: {report['for_trade_date']}",
        f"- source_trade_date: {report['source_trade_date']}",
        f"- prev_trade_date: {report['prev_trade_date']}",
        f"- started_at: {report['started_at']}",
        f"- finished_at: {report['finished_at']}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Dry-Run Input",
        "",
        f"- source_scope_row_count: {dry['source_scope_row_count']}",
        f"- source_scope_row_count_by_asset_kind: {dry['source_scope_row_count_by_asset_kind']}",
        f"- subscription_candidate_count: {dry['subscription_candidate_count']}",
        f"- dedup_subscription_count: {dry['dedup_subscription_count']}",
        f"- subscription_object_count: {dry['subscription_object_count']}",
        f"- object_count_by_asset_kind: {dry['object_count_by_asset_kind']}",
        f"- required_data_kind_counts: {dry['required_data_kind_counts']}",
        f"- previous_day_minute_required_count: {dry['previous_day_minute_required_count']}",
        f"- previous_day_minute_date_counts: {dry['previous_day_minute_date_counts']}",
        f"- dedup_ratio: {dry['dedup_ratio']}",
        f"- market_data_pull_plan_row_count: {dry['market_data_pull_plan_row_count']}",
        "",
        "## Rows Written",
        "",
        f"- common_market_data_run: {write['market_data_run_rows_written']}",
        f"- common_market_data_quality_item: {write['quality_item_rows_written']}",
        f"- common_market_data_subscription_candidate: {write['candidate_rows_written']}",
        f"- common_market_data_subscription: {write['subscription_rows_written']}",
        f"- common_market_data_pull_plan: {write['pull_plan_rows_written']}",
        f"- market_data_fact_rows_written: {write['market_data_fact_rows_written']}",
        f"- event_outbox_rows_written: {write['event_outbox_rows_written']}",
        "",
        "## Post Checks",
        "",
    ]
    for check_name, passed in report["post_checks"].items():
        lines.append(f"- {check_name}: {str(passed).lower()}")
    lines.extend(["", "## Boundary Confirmation", ""])
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.extend(
        [
            "",
            "## Rollback",
            "",
            "Delete this N3-6 run by run_id in dependency order. This removes only N3 control rows:",
            "",
            "```sql",
            f"DELETE FROM common_market_data_pull_plan WHERE run_id = '{report['market_data_run_id']}';",
            f"DELETE FROM common_market_data_subscription WHERE run_id = '{report['market_data_run_id']}';",
            f"DELETE FROM common_market_data_subscription_candidate WHERE run_id = '{report['market_data_run_id']}';",
            f"DELETE FROM common_market_data_quality_item WHERE run_id = '{report['market_data_run_id']}';",
            f"DELETE FROM common_market_data_run WHERE run_id = '{report['market_data_run_id']}';",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
