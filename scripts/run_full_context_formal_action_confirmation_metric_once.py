#!/usr/bin/env python3
"""Plan or execute N3 full-context formal action-confirmation metric once."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.market import v3_full_day_replay_plan as plan
from ashare_v3.market.action_confirmation_projection_execute import insert_action_confirmation_metric_rows
from ashare_v3.market.previous_day_preload_execute import utc_now_iso

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


METRIC_TABLES = {
    "stock": "stock_action_confirmation_projection_metric",
    "index": "index_action_confirmation_projection_metric",
    "board": "board_action_confirmation_projection_metric",
}


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_text(path: str | Path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def build_rollback_sql(projection_run_id: str) -> str:
    return f"""-- N3 full-context formal action-confirmation metric rollback.
-- Scope: projection_run_id={projection_run_id}
-- Does not touch source minute facts, N4/N5/N6, outbox/inbox/checkpoint.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := '{projection_run_id}';
  v_count BIGINT;
BEGIN
  RAISE EXCEPTION 'full-context formal metric rollback hard-fail: set reviewed session variable before DELETE';

  SELECT count(*) INTO v_count FROM common_event_outbox
  WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: outbox refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_inbox
  WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: inbox refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: checkpoint refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_run
  WHERE source_market_data_run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N4 refs=%', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_action_run
  WHERE source_trigger_run_id = v_run_id OR raw_json::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N5 refs=%', v_count;
  END IF;
END $$;

DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = '{projection_run_id}';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = '{projection_run_id}';
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = '{projection_run_id}';
DELETE FROM common_market_data_quality_item WHERE run_id = '{projection_run_id}';
DELETE FROM common_market_data_run WHERE run_id = '{projection_run_id}';

COMMIT;
"""


def lineage_from_args(args: argparse.Namespace) -> plan.FullContextFormalMetricLineage:
    return plan.FullContextFormalMetricLineage(
        for_trade_date=args.for_trade_date,
        source_trade_date=args.source_trade_date,
        previous_trade_date=args.previous_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        source_subscription_run_id=args.source_subscription_run_id,
        source_today_minute_run_id=args.source_today_minute_run_id,
        source_previous_day_minute_run_id=args.source_previous_day_minute_run_id,
        trigger_context_run_id=args.trigger_context_run_id,
        projection_run_id=args.projection_run_id,
        source_snapshot_run_id=args.source_snapshot_run_id,
        projection_schema_version=args.projection_schema_version,
    )


def insert_metric_run(cur: Any, *, lineage: plan.FullContextFormalMetricLineage, expected_total: int, started_at: str) -> None:
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
                %s, %s, %s, %s, NULL, 'N3-full-context-formal-action-confirmation-metric',
                false, false, false, false, %s, %s)
        """,
        (
            lineage.projection_run_id,
            lineage.source_condition_run_id,
            lineage.for_trade_date,
            lineage.source_trade_date,
            lineage.previous_trade_date,
            expected_total,
            expected_total,
            expected_total,
            expected_total,
            started_at,
            Jsonb(
                {
                    "stage": "N3_full_context_formal_action_confirmation_metric",
                    "projection_schema_version": lineage.projection_schema_version,
                    "source_scope": lineage.source_scope(),
                    "writes_outbox": False,
                    "old_system_read": False,
                }
            ),
        ),
    )


def insert_quality(
    cur: Any,
    *,
    lineage: plan.FullContextFormalMetricLineage,
    summary: Mapping[str, Any],
) -> int:
    not_ready = int(summary.get("metric_not_ready") or 0)
    rows = [
        (
            lineage.projection_run_id,
            lineage.source_condition_run_id,
            lineage.for_trade_date,
            lineage.source_trade_date,
            "common",
            "market_data_run",
            "common_market_data_run",
            "n3_full_context_formal_metric_execute_pass",
            "N3 full-context formal action-confirmation metric execute pass",
            "P0",
            "passed",
            str(summary.get("metric_rows")),
            str(summary.get("metric_rows")),
            Jsonb({"summary": dict(summary)}),
        ),
        (
            lineage.projection_run_id,
            lineage.source_condition_run_id,
            lineage.for_trade_date,
            lineage.source_trade_date,
            "common",
            "market_data_run",
            "common_market_data_run",
            "n3_full_context_formal_metric_not_ready_visible",
            "N3 full-context formal metric not-ready rows are quality visible",
            "P1",
            "warning" if not_ready else "passed",
            "not-ready rows surfaced, not fabricated",
            f"metric_not_ready={not_ready}",
            Jsonb({"metric_not_ready": not_ready}),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO common_market_data_quality_item (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          data_domain, layer_scope, table_name, gate_code, gate_name,
          severity, status, expected_value, actual_value, details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return len(rows)


def execute_full_context_formal_metric(
    *,
    dsn: str,
    lineage: plan.FullContextFormalMetricLineage,
    batch_size: int,
    progress_every: int,
) -> dict[str, Any]:
    preflight = plan.build_full_context_formal_metric_plan_from_db(dsn=dsn, lineage=lineage)
    if preflight["result"] != "PLAN_PASS":
        raise plan.FullDayMetricBlocked(f"preflight blocked: {preflight['blockers']}")
    contract = plan.full_day_metric_contract(lineage)
    contexts = plan.fetch_full_day_metric_context_rows(
        dsn=dsn,
        trigger_context_run_id=lineage.trigger_context_run_id,
        for_trade_date=lineage.for_trade_date,
    )
    contexts_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in plan.ASSET_CONFIG}
    for row in contexts:
        contexts_by_asset[str(row["asset_kind"])].append(dict(row))
    summary: dict[str, Any] = {
        "metric_rows": 0,
        "metric_ready": 0,
        "metric_not_ready": 0,
        "rows_by_asset": {asset: 0 for asset in plan.ASSET_CONFIG},
        "ready_by_asset": {asset: 0 for asset in plan.ASSET_CONFIG},
        "not_ready_by_asset": {asset: 0 for asset in plan.ASSET_CONFIG},
    }
    started_at = utc_now_iso()
    expected_total = int((preflight.get("expected_rows") or {}).get("total") or 0)
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                insert_metric_run(cur, lineage=lineage, expected_total=expected_total, started_at=started_at)
                for asset, asset_contexts in contexts_by_asset.items():
                    identities = [str(row["identity_key"]) for row in asset_contexts]
                    minute_rows = plan.fetch_full_day_metric_minute_rows_by_identity(
                        dsn=dsn,
                        asset_kind=asset,
                        identities=identities,
                        today_run_id=lineage.source_today_minute_run_id,
                        previous_run_id=lineage.source_previous_day_minute_run_id,
                        for_trade_date=lineage.for_trade_date,
                        previous_trade_date=lineage.previous_trade_date,
                    )
                    batch: list[dict[str, Any]] = []
                    for index, context_row in enumerate(asset_contexts, start=1):
                        rows = plan.build_full_day_metric_rows_for_identity(
                            context_row=context_row,
                            minute_rows=minute_rows.get(str(context_row["identity_key"])) or [],
                            contract=contract,
                            for_trade_date=lineage.for_trade_date,
                            source_today_minute_run_id=lineage.source_today_minute_run_id,
                            source_previous_day_minute_run_id=lineage.source_previous_day_minute_run_id,
                            source_snapshot_run_id=lineage.resolved_source_snapshot_run_id,
                        )
                        for row in rows:
                            summary["metric_rows"] += 1
                            summary["rows_by_asset"][asset] += 1
                            if row.get("metric_ready"):
                                summary["metric_ready"] += 1
                                summary["ready_by_asset"][asset] += 1
                            else:
                                summary["metric_not_ready"] += 1
                                summary["not_ready_by_asset"][asset] += 1
                            batch.append(row)
                            if len(batch) >= batch_size:
                                insert_action_confirmation_metric_rows(cur, table=METRIC_TABLES[asset], rows=batch)
                                batch.clear()
                        if progress_every and (index == 1 or index == len(asset_contexts) or index % progress_every == 0):
                            print(
                                f"full-context formal metric build {asset} {index}/{len(asset_contexts)} "
                                f"rows={summary['metric_rows']}",
                                flush=True,
                            )
                    if batch:
                        insert_action_confirmation_metric_rows(cur, table=METRIC_TABLES[asset], rows=batch)
                if int(summary["metric_rows"]) != expected_total:
                    raise plan.FullDayMetricBlocked(
                        f"built metric row count mismatch: expected={expected_total}; actual={summary['metric_rows']}"
                    )
                quality_rows = insert_quality(cur, lineage=lineage, summary=summary)
                p1_count = 1 if int(summary["metric_not_ready"] or 0) else 0
                finished_at = utc_now_iso()
                cur.execute(
                    """
                    UPDATE common_market_data_run
                    SET status='passed',
                        p0_count=0,
                        p1_count=%s,
                        p2_count=0,
                        source_scope_row_count=%s,
                        candidate_row_count=%s,
                        subscription_row_count=%s,
                        subscription_object_count=%s,
                        market_data_fact_written=true,
                        finished_at=%s,
                        updated_at=%s,
                        raw_json = raw_json || %s
                    WHERE run_id=%s
                    """,
                    (
                        p1_count,
                        len(contexts),
                        int(summary["metric_rows"]),
                        int(summary["metric_rows"]),
                        len(contexts),
                        finished_at,
                        finished_at,
                        Jsonb({"execute_summary": summary}),
                        lineage.projection_run_id,
                    ),
                )
    return {
        "stage": "N3 full-context formal action-confirmation metric execute",
        "result": "EXECUTE_PASS",
        "projection_run_id": lineage.projection_run_id,
        "projection_schema_version": lineage.projection_schema_version,
        "preflight": preflight,
        "summary": summary,
        "quality_rows": quality_rows,
        "post_counts": plan.capture_full_day_metric_counts(dsn=dsn, projection_run_id=lineage.projection_run_id),
        "side_effects": {
            "database_written": True,
            "writes_outbox": False,
            "outbox_inbox_checkpoint_consumed_or_updated": False,
            "n4_executed": False,
            "n5_executed": False,
            "n6_voice_mobile_sim_trade_touched": False,
            "old_system_read": False,
        },
    }


def format_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N3 Full-Context Formal Action-Confirmation Metric Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- projection_run_id: `{report.get('projection_run_id')}`",
            f"- projection_schema_version: `{report.get('projection_schema_version')}`",
            f"- expected_rows: `{report.get('expected_rows')}`",
            f"- blockers: `{report.get('blockers')}`",
            f"- writes_outbox: `{(report.get('write_scope') or report.get('side_effects') or {}).get('writes_outbox')}`",
        ]
    ) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--source-trade-date", required=True)
    parser.add_argument("--previous-trade-date", required=True)
    parser.add_argument("--source-condition-run-id", required=True)
    parser.add_argument("--source-subscription-run-id", required=True)
    parser.add_argument("--source-today-minute-run-id", required=True)
    parser.add_argument("--source-previous-day-minute-run-id", required=True)
    parser.add_argument("--trigger-context-run-id", required=True)
    parser.add_argument("--projection-run-id", required=True)
    parser.add_argument("--source-snapshot-run-id")
    parser.add_argument("--projection-schema-version", default=plan.TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION)
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--markdown-report-path", required=True)
    parser.add_argument("--rollback-sql-path", required=True)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--progress-every", type=int, default=200)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lineage = lineage_from_args(args)
    report = plan.build_full_context_formal_metric_plan_from_db(dsn=args.dsn, lineage=lineage)
    write_json(args.json_report_path, report)
    write_text(args.markdown_report_path, format_markdown(report))
    write_text(args.rollback_sql_path, build_rollback_sql(lineage.projection_run_id))
    if not args.execute and not args.user_confirmed:
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0 if report.get("result") == "PLAN_PASS" else 2
    try:
        plan.require_full_day_metric_execute_flags(execute=args.execute, user_confirmed=args.user_confirmed)
        execute_report = execute_full_context_formal_metric(
            dsn=args.dsn,
            lineage=lineage,
            batch_size=args.batch_size,
            progress_every=args.progress_every,
        )
        write_json(args.json_report_path, execute_report)
        write_text(args.markdown_report_path, format_markdown(execute_report))
        if args.json:
            print(json.dumps(execute_report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        blocked = {
            "stage": "N3 full-context formal action-confirmation metric execute",
            "result": "BLOCKED",
            "blocked_reason": f"{type(exc).__name__}: {exc}",
            "projection_run_id": lineage.projection_run_id,
            "database_written": False,
            "post_counts": plan.capture_full_day_metric_counts(dsn=args.dsn, projection_run_id=lineage.projection_run_id),
            "side_effects": {
                "writes_outbox": False,
                "n4_executed": False,
                "n5_executed": False,
                "n6_voice_mobile_sim_trade_touched": False,
                "old_system_read": False,
            },
        }
        write_json(args.json_report_path, blocked)
        write_text(args.markdown_report_path, format_markdown(blocked))
        if args.json:
            print(json.dumps(blocked, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
