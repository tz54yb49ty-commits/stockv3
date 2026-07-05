#!/usr/bin/env python3
"""Execute N3-A1 previous-day cumulative amount materialization.

This fastlane adapter reads already-written A1 previous-day minute facts and
materializes only the stock/index/board cumulative tables. It does not pull
market data, write common_market_data_run, write outbox, or enter N3P/N4/N5/N6.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ashare_v3.market.previous_day_cumulative_amount_writer import (
    A1_CUMULATIVE_ASSET_KINDS,
    A1_CUMULATIVE_TABLES,
    A1CumulativeAmountWriterBlocked,
    build_previous_day_cumulative_amount_rollback_sql,
    build_previous_day_cumulative_amount_write_plan,
    write_previous_day_cumulative_amount_rows,
)
from ashare_v3.market.repositories import ASSET_FACT_TABLES
from check_condition_source_ready import DEFAULT_DSN


class PreviousDayCumulativeAmountExecuteError(RuntimeError):
    """Raised when the fastlane cumulative step must fail closed."""


def ensure_execute_authorized(*, execute: bool, user_confirmed: bool) -> None:
    missing = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise PreviousDayCumulativeAmountExecuteError("missing explicit authorization: " + ", ".join(missing))


def fetch_previous_day_minute_rows_by_asset(
    cur: Any,
    *,
    source_previous_day_minute_run_id: str,
    source_trade_date: str,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_asset: dict[str, list[dict[str, Any]]] = {}
    for asset_kind in A1_CUMULATIVE_ASSET_KINDS:
        table_name, identity_column, _ = ASSET_FACT_TABLES[asset_kind]["minute"]
        cur.execute(
            f"""
            SELECT
              run_id,
              subscription_id,
              source_condition_run_id,
              for_trade_date,
              trade_date,
              bar_time,
              {identity_column} AS identity_key,
              exchange,
              code,
              display_code,
              name,
              open,
              high,
              low,
              close,
              volume,
              amount,
              source_adapter,
              source_version,
              quality_status,
              is_previous_day_preload,
              source_scope_ids,
              source_condition_pool_ids,
              raw_json
            FROM {table_name}
            WHERE run_id = %s
              AND trade_date = %s
              AND is_previous_day_preload = true
            ORDER BY {identity_column}, bar_time
            """,
            (source_previous_day_minute_run_id, source_trade_date),
        )
        rows_by_asset[asset_kind] = [dict(row) for row in cur.fetchall()]
    return rows_by_asset


def assert_source_run_passed(cur: Any, source_previous_day_minute_run_id: str) -> None:
    cur.execute(
        """
        SELECT run_id, status
        FROM common_market_data_run
        WHERE run_id = %s
        """,
        (source_previous_day_minute_run_id,),
    )
    row = cur.fetchone()
    if not row:
        raise PreviousDayCumulativeAmountExecuteError(
            f"BLOCKED_A1_CUMULATIVE_SOURCE_RUN_MISSING:{source_previous_day_minute_run_id}"
        )
    if str(row.get("status") or "") != "passed":
        raise PreviousDayCumulativeAmountExecuteError(
            f"BLOCKED_A1_CUMULATIVE_SOURCE_RUN_NOT_PASSED:{source_previous_day_minute_run_id}"
        )


def assert_target_tables_exist(cur: Any) -> None:
    missing = []
    for table_name in A1_CUMULATIVE_TABLES.values():
        cur.execute("SELECT to_regclass(%s) AS relation_name", (table_name,))
        row = cur.fetchone()
        if not row or not row.get("relation_name"):
            missing.append(table_name)
    if missing:
        raise PreviousDayCumulativeAmountExecuteError("BLOCKED_A1_CUMULATIVE_SCHEMA_MISSING:" + ",".join(missing))


def count_tables(cur: Any, table_names: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in table_names:
        cur.execute(f"SELECT count(*) AS count FROM {table_name}")
        row = cur.fetchone()
        counts[table_name] = int((row or {}).get("count") or 0)
    return counts


def assert_no_forbidden_count_delta(pre_counts: Mapping[str, int], post_counts: Mapping[str, int]) -> None:
    forbidden_tables = (
        "common_market_data_run",
        "common_market_data_quality_item",
        "common_event_outbox",
        "common_event_inbox",
        "common_event_consumer_checkpoint",
    )
    changed = [
        table_name
        for table_name in forbidden_tables
        if int(pre_counts.get(table_name) or 0) != int(post_counts.get(table_name) or 0)
    ]
    if changed:
        raise PreviousDayCumulativeAmountExecuteError(
            "BLOCKED_A1_CUMULATIVE_FORBIDDEN_TABLE_MUTATION:" + ",".join(changed)
        )


def summarize_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    rows_by_asset = {
        asset_kind: list((plan.get("rows_by_asset") or {}).get(asset_kind) or [])
        for asset_kind in A1_CUMULATIVE_ASSET_KINDS
    }
    all_rows = [row for rows in rows_by_asset.values() for row in rows]
    keys = [
        (
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
            str(row.get("canonical_minute_label") or ""),
        )
        for row in all_rows
    ]
    duplicate_key_count = sum(count - 1 for count in Counter(keys).values() if count > 1)
    unit_distribution = Counter(str(row.get("source_amount_unit") or "") for row in all_rows)
    return {
        "row_count_by_asset": {asset_kind: len(rows_by_asset[asset_kind]) for asset_kind in A1_CUMULATIVE_ASSET_KINDS},
        "object_count_by_asset": {
            asset_kind: len({str(row.get("identity_key") or "") for row in rows_by_asset[asset_kind] if row.get("identity_key")})
            for asset_kind in A1_CUMULATIVE_ASSET_KINDS
        },
        "canonical_1130_count": sum(1 for row in all_rows if str(row.get("canonical_minute_label") or "").endswith(" 11:30")),
        "canonical_1300_count": sum(1 for row in all_rows if str(row.get("canonical_minute_label") or "").endswith(" 13:00")),
        "raw_1130_to_1300_count": sum(
            1
            for row in all_rows
            if str(row.get("raw_bar_time") or "").endswith(" 11:30")
            and str(row.get("canonical_minute_label") or "").endswith(" 13:00")
        ),
        "full_count_bad_rows": sum(1 for row in all_rows if int(row.get("full_count") or 0) != 240),
        "duplicate_key_count": duplicate_key_count,
        "invalid_amount_count": sum(1 for row in all_rows if float(row.get("cumulative_amount_yuan") or 0) < 0),
        "unit_distribution": dict(sorted(unit_distribution.items())),
    }


def build_report(
    *,
    writer_report: Mapping[str, Any],
    plan_summary: Mapping[str, Any],
    rollback_sql_path: str,
    pre_counts: Mapping[str, int],
    post_counts: Mapping[str, int],
) -> dict[str, Any]:
    write_action = str(writer_report.get("write_action") or "")
    return {
        "result": "IDEMPOTENT_PASS" if write_action == "idempotent_noop" else "EXECUTE_PASS",
        "stage": "N3_A1_previous_day_cumulative_amount_fastlane",
        "layer_role": "N3_market_data",
        "source_previous_day_minute_run_id": writer_report.get("source_previous_day_minute_run_id"),
        "for_trade_date": writer_report.get("for_trade_date"),
        "source_trade_date": writer_report.get("source_trade_date"),
        "status": writer_report.get("status"),
        "write_action": write_action,
        "row_count_by_asset": dict(plan_summary.get("row_count_by_asset") or {}),
        "inserted_row_count_by_asset": dict(writer_report.get("inserted_row_count_by_asset") or {}),
        "object_count_by_asset": dict(plan_summary.get("object_count_by_asset") or {}),
        "canonical_1130_count": plan_summary.get("canonical_1130_count"),
        "canonical_1300_count": plan_summary.get("canonical_1300_count"),
        "raw_1130_to_1300_count": plan_summary.get("raw_1130_to_1300_count"),
        "full_count_bad_rows": plan_summary.get("full_count_bad_rows"),
        "duplicate_key_count": plan_summary.get("duplicate_key_count"),
        "invalid_amount_count": plan_summary.get("invalid_amount_count"),
        "unit_distribution": dict(plan_summary.get("unit_distribution") or {}),
        "rollback_sql_path": rollback_sql_path,
        "pre_counts": dict(pre_counts),
        "post_counts": dict(post_counts),
        "side_effect_guard": {
            "cumulative_table_written": write_action == "inserted",
            "common_market_data_run_written": False,
            "common_market_data_quality_item_written": False,
            "outbox_written": False,
            "inbox_checkpoint_touched": False,
            "downstream_runtime_entered": False,
            "market_data_adapter_called": False,
        },
    }


def render_markdown_report(report: Mapping[str, Any]) -> str:
    lines = [
        "# N3-A1 Previous-Day Cumulative Amount Fastlane Report",
        "",
        f"- result: `{report.get('result')}`",
        f"- source_previous_day_minute_run_id: `{report.get('source_previous_day_minute_run_id')}`",
        f"- source_trade_date: `{report.get('source_trade_date')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- write_action: `{report.get('write_action')}`",
        f"- rollback_sql_path: `{report.get('rollback_sql_path')}`",
        "",
        "## Row Counts",
    ]
    for asset_kind, count in (report.get("row_count_by_asset") or {}).items():
        lines.append(f"- {asset_kind}: `{count}`")
    lines.extend(["", "## Side Effects"])
    for key, value in (report.get("side_effect_guard") or {}).items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def write_json_and_markdown_reports(report: Mapping[str, Any], *, json_report_path: str, markdown_report_path: str) -> None:
    json_path = Path(json_report_path)
    md_path = Path(markdown_report_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")


def run_previous_day_cumulative_amount_execute(
    *,
    dsn: str,
    source_previous_day_minute_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    json_report_path: str,
    markdown_report_path: str,
    rollback_sql_path: str,
    execute: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    ensure_execute_authorized(execute=execute, user_confirmed=user_confirmed)
    rollback_sql = build_previous_day_cumulative_amount_rollback_sql(source_previous_day_minute_run_id)
    rollback_path = Path(rollback_sql_path)
    rollback_path.parent.mkdir(parents=True, exist_ok=True)
    rollback_path.write_text(rollback_sql, encoding="utf-8")

    guard_tables = (
        "common_market_data_run",
        "common_market_data_quality_item",
        "common_event_outbox",
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        *A1_CUMULATIVE_TABLES.values(),
    )
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                assert_source_run_passed(cur, source_previous_day_minute_run_id)
                assert_target_tables_exist(cur)
                pre_counts = count_tables(cur, guard_tables)
                rows_by_asset = fetch_previous_day_minute_rows_by_asset(
                    cur,
                    source_previous_day_minute_run_id=source_previous_day_minute_run_id,
                    source_trade_date=source_trade_date,
                )
                plan = build_previous_day_cumulative_amount_write_plan(
                    rows_by_asset,
                    source_previous_day_minute_run_id=source_previous_day_minute_run_id,
                    for_trade_date=for_trade_date,
                    source_trade_date=source_trade_date,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                plan_summary = summarize_plan(plan)
                writer_report = write_previous_day_cumulative_amount_rows(
                    cur,
                    rows_by_asset,
                    source_previous_day_minute_run_id=source_previous_day_minute_run_id,
                    for_trade_date=for_trade_date,
                    source_trade_date=source_trade_date,
                )
                post_counts = count_tables(cur, guard_tables)
                assert_no_forbidden_count_delta(pre_counts, post_counts)
    report = build_report(
        writer_report=writer_report,
        plan_summary=plan_summary,
        rollback_sql_path=rollback_sql_path,
        pre_counts=pre_counts,
        post_counts=post_counts,
    )
    write_json_and_markdown_reports(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
    return report


def blocked_report(reason: str, *, json_report_path: str, markdown_report_path: str) -> dict[str, Any]:
    report = {
        "result": "BLOCKED",
        "stage": "N3_A1_previous_day_cumulative_amount_fastlane",
        "layer_role": "N3_market_data",
        "reason": reason,
        "writes_performed": False,
        "market_data_adapter_called": False,
        "common_market_data_run_written": False,
        "event_outbox_written": False,
        "inbox_checkpoint_touched": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }
    write_json_and_markdown_reports(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute N3-A1 previous-day cumulative amount materialization.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--source-previous-day-minute-run-id", required=True)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--source-trade-date", required=True)
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--markdown-report-path", required=True)
    parser.add_argument("--rollback-sql-path", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        report = run_previous_day_cumulative_amount_execute(
            dsn=args.dsn,
            source_previous_day_minute_run_id=args.source_previous_day_minute_run_id,
            for_trade_date=args.for_trade_date,
            source_trade_date=args.source_trade_date,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    except (A1CumulativeAmountWriterBlocked, PreviousDayCumulativeAmountExecuteError, psycopg.Error) as exc:
        report = blocked_report(
            str(exc),
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"n3-a1 cumulative amount {report['result']} {report['write_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
