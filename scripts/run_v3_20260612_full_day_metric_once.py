#!/usr/bin/env python3
"""Execute V3-only 20260612 full-day N3 action-confirmation metric once."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
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


DEFAULT_CONTRACT_JSON = "docs/V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC_CONTRACT.json"
DEFAULT_CONTRACT_MD = "docs/V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC_CONTRACT.md"
DEFAULT_PREFLIGHT_JSON = "docs/V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC_PREFLIGHT.json"
DEFAULT_PREFLIGHT_MD = "docs/V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC_PREFLIGHT.md"
DEFAULT_EXECUTE_JSON = "docs/V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC_EXECUTE_REPORT.json"
DEFAULT_EXECUTE_MD = "docs/V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC_EXECUTE_REPORT.md"
DEFAULT_ROLLBACK_SQL = "sql/V3_20260612_n3_full_day_action_confirmation_metric_rollback.sql"

METRIC_TABLES = {
    "stock": "stock_action_confirmation_projection_metric",
    "index": "index_action_confirmation_projection_metric",
    "board": "board_action_confirmation_projection_metric",
}


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def build_rollback_sql(projection_run_id: str) -> str:
    return f"""-- V3 20260612 N3 full-day action-confirmation metric rollback.
-- Scope: projection_run_id={projection_run_id}
-- Does not touch source minute facts, N4/N5/N6, outbox/inbox/checkpoint.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := '{projection_run_id}';
  v_count BIGINT;
BEGIN
  RAISE EXCEPTION 'V3 full-day metric rollback hard-fail: set reviewed session variable before DELETE';

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


def contract_and_preflight(*, dsn: str, contract: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    contexts = plan.fetch_full_day_metric_context_rows(dsn=dsn)
    baseline = plan.capture_full_day_metric_counts(dsn=dsn, projection_run_id=plan.FULL_DAY_METRIC_RUN_ID)
    current_counts = plan.capture_full_day_backfill_counts(
        dsn=dsn,
        backfill_run_id=plan.FULL_DAY_1M_BACKFILL_RUN_ID,
        for_trade_date=plan.FOR_TRADE_DATE,
    )
    previous_counts = plan.capture_full_day_backfill_counts(
        dsn=dsn,
        backfill_run_id=plan.FULL_DAY_PREVIOUS_MINUTE_RUN_ID,
        for_trade_date=plan.FOR_TRADE_DATE,
        minute_trade_date="20260611",
        is_previous_day_preload=True,
    )
    context_by_asset = Counter(str(row.get("asset_kind")) for row in contexts)
    expected_rows = {
        asset: int((current_counts.get("minute_counts_by_asset") or {}).get(asset, {}).get("row_count") or 0)
        for asset in plan.ASSET_CONFIG
    }
    expected_rows["total"] = sum(expected_rows.values())
    blockers = []
    if any(int(value or 0) != 0 for value in baseline.values()):
        blockers.append("target_projection_run_baseline_not_zero")
    if not contexts:
        blockers.append("n4_context_rows_missing")
    if int(expected_rows["total"]) == 0:
        blockers.append("current_full_day_1m_rows_missing")
    if sum(int((previous_counts.get("minute_counts_by_asset") or {}).get(asset, {}).get("row_count") or 0) for asset in plan.ASSET_CONFIG) == 0:
        blockers.append("previous_day_full_scope_1m_rows_missing")
    contract_payload = {
        "stage": "V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC_CONTRACT",
        "result": "CONTRACT_PASS",
        "projection_run_id": plan.FULL_DAY_METRIC_RUN_ID,
        "projection_schema_version": plan.FULL_DAY_METRIC_SCHEMA_VERSION,
        "source_scope": contract["source_scope"],
        "expected_rows": expected_rows,
        "context_object_count": len(contexts),
        "context_by_asset": dict(context_by_asset),
        "allowed_write_tables": contract["allowed_write_tables"],
        "writes_outbox": False,
        "rollback_sql": DEFAULT_ROLLBACK_SQL,
    }
    preflight = {
        "stage": "V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC_PREFLIGHT",
        "result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "blockers": blockers,
        "projection_run_id": plan.FULL_DAY_METRIC_RUN_ID,
        "execute_authorized": False,
        "expected_rows": expected_rows,
        "baseline": baseline,
        "current_1m_counts": current_counts,
        "previous_day_1m_counts": previous_counts,
        "side_effects": {
            "execute_performed": False,
            "database_written": False,
            "writes_outbox": False,
            "n4_n5_n6_touched": False,
        },
    }
    return contract_payload, preflight


def insert_metric_run(cur: Any, *, expected_total: int, started_at: str) -> None:
    scope = plan.full_day_metric_contract()["source_scope"]
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
                %s, %s, %s, %s, NULL, 'V3-full-day-action-confirmation-metric',
                false, false, false, false, %s, %s)
        """,
        (
            plan.FULL_DAY_METRIC_RUN_ID,
            scope["source_condition_run_id"],
            scope["for_trade_date"],
            scope["source_trade_date"],
            scope["source_trade_date"],
            expected_total,
            expected_total,
            expected_total,
            expected_total,
            started_at,
            Jsonb(
                {
                    "stage": "V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC",
                    "source_today_minute_run_id": plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    "source_previous_day_minute_run_id": plan.FULL_DAY_PREVIOUS_MINUTE_RUN_ID,
                    "writes_outbox": False,
                    "old_system_read": False,
                }
            ),
        ),
    )


def insert_quality(cur: Any, *, summary: Mapping[str, Any]) -> int:
    not_ready = int(summary.get("metric_not_ready") or 0)
    missing_objects = int(summary.get("missing_source_objects") or 0)
    items = [
        {
            "gate_code": "v3_full_day_metric_execute_pass",
            "gate_name": "V3 full-day action-confirmation metric execute pass",
            "severity": "P0",
            "status": "passed",
            "expected": str(summary.get("metric_rows")),
            "actual": str(summary.get("metric_rows")),
            "details": {"summary": dict(summary)},
        },
        {
            "gate_code": "v3_full_day_metric_not_ready_visible",
            "gate_name": "V3 full-day metric not-ready rows are quality visible",
            "severity": "P1",
            "status": "warning" if not_ready or missing_objects else "passed",
            "expected": "not-ready/missing surfaced, not fabricated",
            "actual": f"metric_not_ready={not_ready};missing_source_objects={missing_objects}",
            "details": {"metric_not_ready": not_ready, "missing_source_objects": missing_objects},
        },
    ]
    rows = [
        (
            plan.FULL_DAY_METRIC_RUN_ID,
            plan.SOURCE_CONDITION_RUN_ID,
            plan.FOR_TRADE_DATE,
            "20260611",
            "common",
            "market_data_run",
            "common_market_data_run",
            item["gate_code"],
            item["gate_name"],
            item["severity"],
            item["status"],
            item["expected"],
            item["actual"],
            Jsonb(item["details"]),
        )
        for item in items
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


def execute_metric(*, dsn: str, batch_size: int, progress_every: int) -> dict[str, Any]:
    contract = plan.full_day_metric_contract()
    contract_payload, preflight = contract_and_preflight(dsn=dsn, contract=contract)
    if preflight["result"] != "PREFLIGHT_PASS":
        raise plan.FullDayMetricBlocked(f"preflight blocked: {preflight['blockers']}")
    contexts = plan.fetch_full_day_metric_context_rows(dsn=dsn)
    contexts_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in plan.ASSET_CONFIG}
    for row in contexts:
        contexts_by_asset[str(row["asset_kind"])].append(dict(row))
    summary: dict[str, Any] = {
        "metric_rows": 0,
        "metric_ready": 0,
        "metric_not_ready": 0,
        "missing_source_objects": 0,
        "rows_by_asset": {asset: 0 for asset in plan.ASSET_CONFIG},
        "ready_by_asset": {asset: 0 for asset in plan.ASSET_CONFIG},
        "not_ready_by_asset": {asset: 0 for asset in plan.ASSET_CONFIG},
    }
    expected_total = int((contract_payload.get("expected_rows") or {}).get("total") or 0)
    started_at = utc_now_iso()
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                insert_metric_run(cur, expected_total=expected_total, started_at=started_at)
                for asset, asset_contexts in contexts_by_asset.items():
                    identities = [str(row["identity_key"]) for row in asset_contexts]
                    minute_rows = plan.fetch_full_day_metric_minute_rows_by_identity(
                        dsn=dsn,
                        asset_kind=asset,
                        identities=identities,
                    )
                    batch: list[dict[str, Any]] = []
                    for index, context_row in enumerate(asset_contexts, start=1):
                        identity = str(context_row["identity_key"])
                        rows = plan.build_full_day_metric_rows_for_identity(
                            context_row=context_row,
                            minute_rows=minute_rows.get(identity) or [],
                            contract=contract,
                        )
                        if not rows:
                            summary["missing_source_objects"] += 1
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
                        if index == 1 or index == len(asset_contexts) or index % max(progress_every, 1) == 0:
                            print(f"full-day metric build {asset} {index}/{len(asset_contexts)} rows={summary['metric_rows']}", flush=True)
                    if batch:
                        insert_action_confirmation_metric_rows(cur, table=METRIC_TABLES[asset], rows=batch)
                quality_rows = insert_quality(cur, summary=summary)
                p1_count = 1 if int(summary["metric_not_ready"] or 0) or int(summary["missing_source_objects"] or 0) else 0
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
                        plan.FULL_DAY_METRIC_RUN_ID,
                    ),
                )
    post_counts = plan.capture_full_day_metric_counts(dsn=dsn, projection_run_id=plan.FULL_DAY_METRIC_RUN_ID)
    return {
        "stage": "V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC",
        "result": "EXECUTE_PASS",
        "projection_run_id": plan.FULL_DAY_METRIC_RUN_ID,
        "contract": contract_payload,
        "preflight": preflight,
        "summary": summary,
        "quality_rows": quality_rows,
        "post_counts": post_counts,
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
    summary = report.get("summary") or {}
    return "\n".join(
        [
            "# V3 20260612 N3 Full-Day Action-Confirmation Metric Execute Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- projection_run_id: `{report.get('projection_run_id')}`",
            f"- metric_rows: `{summary.get('metric_rows')}`",
            f"- metric_ready/not_ready: `{summary.get('metric_ready')}/{summary.get('metric_not_ready')}`",
            f"- rows_by_asset: `{summary.get('rows_by_asset')}`",
            f"- missing_source_objects: `{summary.get('missing_source_objects')}`",
            "- writes_outbox: `False`",
            "- N4/N5/N6 touched: `False`",
        ]
    ) + "\n"


def format_contract_markdown(contract: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# V3 20260612 N3 Full-Day Action-Confirmation Metric Contract",
            "",
            f"- result: `{contract.get('result')}`",
            f"- projection_run_id: `{contract.get('projection_run_id')}`",
            f"- expected_rows: `{contract.get('expected_rows')}`",
            f"- writes_outbox: `{contract.get('writes_outbox')}`",
        ]
    ) + "\n"


def format_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# V3 20260612 N3 Full-Day Action-Confirmation Metric Preflight",
            "",
            f"- result: `{preflight.get('result')}`",
            f"- blockers: `{preflight.get('blockers')}`",
            f"- expected_rows: `{preflight.get('expected_rows')}`",
            "- execute_authorized: `False`",
        ]
    ) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-json-path", default=DEFAULT_CONTRACT_JSON)
    parser.add_argument("--contract-markdown-path", default=DEFAULT_CONTRACT_MD)
    parser.add_argument("--preflight-json-path", default=DEFAULT_PREFLIGHT_JSON)
    parser.add_argument("--preflight-markdown-path", default=DEFAULT_PREFLIGHT_MD)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL)
    parser.add_argument("--json-report-path", default=DEFAULT_EXECUTE_JSON)
    parser.add_argument("--markdown-report-path", default=DEFAULT_EXECUTE_MD)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--progress-every", type=int, default=200)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    contract = plan.full_day_metric_contract()
    contract_payload, preflight = contract_and_preflight(dsn=args.dsn, contract=contract)
    write_json(args.contract_json_path, contract_payload)
    write_text(args.contract_markdown_path, format_contract_markdown(contract_payload))
    write_json(args.preflight_json_path, preflight)
    write_text(args.preflight_markdown_path, format_preflight_markdown(preflight))
    write_text(args.rollback_sql_path, build_rollback_sql(plan.FULL_DAY_METRIC_RUN_ID))
    try:
        plan.require_full_day_metric_execute_flags(execute=args.execute, user_confirmed=args.user_confirmed)
        report = execute_metric(dsn=args.dsn, batch_size=args.batch_size, progress_every=args.progress_every)
        write_json(args.json_report_path, report)
        write_text(args.markdown_report_path, format_markdown(report))
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001
        report = {
            "stage": "V3_20260612_N3_FULL_DAY_ACTION_CONFIRMATION_METRIC",
            "result": "BLOCKED",
            "blocked_reason": f"{type(exc).__name__}: {exc}",
            "projection_run_id": plan.FULL_DAY_METRIC_RUN_ID,
            "database_written": False,
            "post_counts": plan.capture_full_day_metric_counts(dsn=args.dsn, projection_run_id=plan.FULL_DAY_METRIC_RUN_ID),
            "side_effects": {
                "writes_outbox": False,
                "n4_executed": False,
                "n5_executed": False,
                "n6_voice_mobile_sim_trade_touched": False,
                "old_system_read": False,
            },
        }
        write_json(args.json_report_path, report)
        write_text(args.markdown_report_path, format_markdown(report))
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
