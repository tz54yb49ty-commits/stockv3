"""Scoped N1 stock_financial 002831 TDX parity repair runner.

This module is deliberately narrow. It builds a complete
stock_financial_20260615_v3 snapshot by copying the active v2 rows and applying
one TDX line-item repair to stock:SZ:002831. It performs no writes unless the
caller passes the explicit execute confirmations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.ingestion.stock_financial_canonical_metrics import json_safe, stock_financial_jsonb_row


SOURCE_TRADE_DATE = "20260615"
TARGET_IDENTITY_KEY = "stock:SZ:002831"
TARGET_TS_CODE = "002831.SZ"
SOURCE_BATCH_ID = "stock_financial_002831_tdx_parity_repair_20260615_v1"
PREVIOUS_SOURCE_VERSION = "stock_financial_20260615_v2"
TARGET_SOURCE_VERSION = "stock_financial_20260615_v3"
EXPECTED_ROW_COUNT = 5504
FINANCIAL_METRIC_VERSION = "financial_metric_v1"
DEFAULT_PROOF_JSON = Path("docs/N1_STOCK_FINANCIAL_002831_TDX_FULL_LINE_ITEM_SOURCE_PROOF.json")
DEFAULT_PROOF_MD = Path("docs/N1_STOCK_FINANCIAL_002831_TDX_FULL_LINE_ITEM_SOURCE_PROOF.md")
DEFAULT_ROLLBACK_SQL = Path("sql/N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql")

ALLOWED_WRITE_TABLES = (
    "stock_financial_metrics_fact",
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
)


class StockFinancial002831RepairBlocked(Exception):
    """Raised when the scoped parity repair guard blocks."""


def validate_execute_flags(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    if not execute_requested:
        raise StockFinancial002831RepairBlocked("missing required final flag: --execute")
    if not user_confirmed:
        raise StockFinancial002831RepairBlocked("missing required final flag: --user-confirmed")
    if not postgres_commit_enabled:
        raise StockFinancial002831RepairBlocked("missing required final flag: --postgres-commit-enabled")


def load_source_proof(path: Path | str, *, source_trade_date: str, stock_identity_key: str) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("source_trade_date") != source_trade_date:
        raise StockFinancial002831RepairBlocked(
            f"source_trade_date_mismatch: expected={source_trade_date}, actual={payload.get('source_trade_date')}"
        )
    if payload.get("stock_identity_key") != stock_identity_key:
        raise StockFinancial002831RepairBlocked(
            f"stock_identity_key_mismatch: expected={stock_identity_key}, actual={payload.get('stock_identity_key')}"
        )
    if payload.get("source_type") != "tdx_financial_package":
        raise StockFinancial002831RepairBlocked("tdx_full_line_item_source_proof_missing")
    announcement_date = require_yyyymmdd(str(payload.get("announcement_date") or ""), "announcement_date")
    if announcement_date > source_trade_date:
        raise StockFinancial002831RepairBlocked("tdx_source_proof_future_announcement_date")
    line_items = payload.get("line_items") or {}
    if str(line_items.get("interest_expense")) != "19744658":
        raise StockFinancial002831RepairBlocked("tdx_interest_expense_proof_mismatch")
    if bool(line_items.get("finance_expense_used_as_interest")):
        raise StockFinancial002831RepairBlocked("finance_expense_used_as_interest_forbidden")
    metrics = payload.get("expected_metrics") or {}
    if str(metrics.get("score")) != "87":
        raise StockFinancial002831RepairBlocked("tdx_score_proof_mismatch")
    if str(metrics.get("core_profit_ttm")) != "1940382164":
        raise StockFinancial002831RepairBlocked("tdx_core_profit_ttm_proof_mismatch")
    return payload


def build_repair_commit_plan(
    *,
    previous_rows: Sequence[Mapping[str, Any]],
    proof: Mapping[str, Any],
    source_trade_date: str,
    previous_source_version: str,
    target_source_version: str,
) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    if previous_source_version != PREVIOUS_SOURCE_VERSION:
        raise StockFinancial002831RepairBlocked("previous_source_version_mismatch")
    if target_source_version != TARGET_SOURCE_VERSION:
        raise StockFinancial002831RepairBlocked("target_source_version_mismatch")
    if len(previous_rows) != EXPECTED_ROW_COUNT:
        raise StockFinancial002831RepairBlocked(
            f"previous_source_version_row_count_mismatch: expected={EXPECTED_ROW_COUNT}, actual={len(previous_rows)}"
        )
    target_rows = [row for row in previous_rows if row.get("stock_identity_key") == TARGET_IDENTITY_KEY]
    if len(target_rows) != 1:
        raise StockFinancial002831RepairBlocked(f"target_identity_row_count_mismatch: actual={len(target_rows)}")

    repaired_rows: list[dict[str, Any]] = []
    semantic_changed_rows_count = 0
    for row in previous_rows:
        original = json_safe(dict(row))
        copied = dict(original)
        copied["source_batch_id"] = SOURCE_BATCH_ID
        copied["source_version"] = target_source_version
        copied["financial_metric_version"] = FINANCIAL_METRIC_VERSION
        if copied.get("stock_identity_key") == TARGET_IDENTITY_KEY:
            copied = build_repaired_002831_row(copied, proof, source_trade_date=source_trade_date)
        if semantic_fingerprint(original) != semantic_fingerprint(copied):
            semantic_changed_rows_count += 1
        repaired_rows.append(copied)

    if len(repaired_rows) != EXPECTED_ROW_COUNT:
        raise StockFinancial002831RepairBlocked("v3_commit_plan_row_count_mismatch")
    if semantic_changed_rows_count != 1:
        raise StockFinancial002831RepairBlocked(
            f"semantic_changed_rows_count_mismatch: expected=1, actual={semantic_changed_rows_count}"
        )
    quality_rows = build_quality_rows(proof=proof, semantic_changed_rows_count=semantic_changed_rows_count)
    return {
        "source_trade_date": source_trade_date,
        "source_batch_id": SOURCE_BATCH_ID,
        "source_version": target_source_version,
        "previous_source_version": previous_source_version,
        "allowed_tables": list(ALLOWED_WRITE_TABLES),
        "stock_financial_rows": repaired_rows,
        "quality_rows": quality_rows,
        "active_source_version_row": {
            "data_domain": "stock",
            "data_type": "stock_financial",
            "scope_key": source_trade_date,
            "source_version": target_source_version,
            "source_batch_id": SOURCE_BATCH_ID,
            "previous_source_version": previous_source_version,
            "activated_by": "n1_stock_financial_002831_tdx_parity_repair_runner",
        },
        "row_counts": {"stock_financial_metrics_fact": len(repaired_rows)},
        "semantic_changed_rows_count": semantic_changed_rows_count,
        "quality_summary": {"P0": 0, "P1": 1, "P2": 0},
        "rollback_sql": str(DEFAULT_ROLLBACK_SQL),
    }


def build_repaired_002831_row(row: Mapping[str, Any], proof: Mapping[str, Any], *, source_trade_date: str) -> dict[str, Any]:
    line_items = proof["line_items"]
    metrics = proof["expected_metrics"]
    total_mv = decimal_text(row.get("total_mv"))
    total_mv_yuan = (Decimal(total_mv) * Decimal("10000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    pe_core = quantized_decimal(total_mv_yuan / Decimal(str(metrics["core_profit_ttm"])))
    raw_payload = dict(row.get("raw_payload") or {})
    raw_payload["latest_source"] = {
        "source_type": "tdx_financial_package",
        "source_name": "TDX财务包",
        "stock_identity_key": TARGET_IDENTITY_KEY,
        "ts_code": TARGET_TS_CODE,
        "report_period": proof["report_period"],
        "announcement_date": proof["announcement_date"],
        "operating_revenue": line_items["operating_revenue"],
        "operating_cost": line_items["operating_cost"],
        "tax_surcharges": line_items["tax_surcharges"],
        "selling_expense": line_items["selling_expense"],
        "admin_expense": line_items["admin_expense"],
        "rd_expense": line_items["rd_expense"],
        "interest_expense": line_items["interest_expense"],
        "finance_expense": line_items["finance_expense"],
        "finance_expense_used_as_interest": False,
        "operating_cashflow": line_items["operating_cashflow"],
    }
    raw_payload["tdx_parity_repair"] = {
        "source_proof_artifact": str(DEFAULT_PROOF_JSON),
        "previous_source_version": PREVIOUS_SOURCE_VERSION,
        "target_source_version": TARGET_SOURCE_VERSION,
        "ttm_quarters": proof["ttm_quarters"],
    }
    warning_json = {
        "warnings": ["forecast_missing"],
        "tdx_parity_repair": True,
        "source_type": "tdx_financial_package",
        "interest_expense_used": line_items["interest_expense"],
    }
    score_breakdown = {
        "tdx_parity_score": metrics["score"],
        "pe_core": str(pe_core),
        "cash_realization_rate": metrics["cash_realization_rate"],
        "core_profit_yoy_pct": metrics["core_profit_yoy_pct"],
    }
    repaired = dict(row)
    repaired.update(
        {
            "asof_date": source_trade_date,
            "source_trade_date": source_trade_date,
            "announcement_date": proof["announcement_date"],
            "report_period": proof["report_period"],
            "ts_code": TARGET_TS_CODE,
            "code": "002831",
            "exchange": "SZ",
            "revenue_yoy": metrics["revenue_yoy_pct"],
            "profit_yoy": metrics["core_profit_yoy_pct"],
            "total_revenue": line_items["operating_revenue"],
            "pe_core": str(pe_core),
            "score": metrics["score"],
            "warning": "forecast_missing",
            "quality_status": "warning",
            "source": "stock_financial_canonical.tdx_mootdx_first.tdx_financial_package",
            "source_batch_id": SOURCE_BATCH_ID,
            "source_version": TARGET_SOURCE_VERSION,
            "raw_payload": raw_payload,
            "cash_realization_rate": metrics["cash_realization_rate"],
            "revenue_yoy_pct": metrics["revenue_yoy_pct"],
            "core_profit_yoy_pct": metrics["core_profit_yoy_pct"],
            "report_core_revenue": line_items["operating_revenue"],
            "report_core_profit": metrics["report_core_profit"],
            "core_profit_ttm": metrics["core_profit_ttm"],
            "core_gt_revenue_yoy": True,
            "revenue_growth_streak_q": metrics["revenue_growth_streak_q"],
            "core_growth_streak_q": metrics["core_growth_streak_q"],
            "core_gt_revenue_streak_q": metrics["core_gt_revenue_streak_q"],
            "forecast_type": None,
            "forecast_score": "0",
            "score_breakdown_json": score_breakdown,
            "financial_warning_json": warning_json,
            "financial_metric_version": FINANCIAL_METRIC_VERSION,
        }
    )
    return json_safe(repaired)


def semantic_fingerprint(row: Mapping[str, Any]) -> str:
    ignored = {"source_batch_id", "source_version"}
    comparable = {key: json_safe(value) for key, value in row.items() if key not in ignored}
    return json.dumps(comparable, ensure_ascii=False, sort_keys=True, default=str)


def build_quality_rows(*, proof: Mapping[str, Any], semantic_changed_rows_count: int) -> list[dict[str, Any]]:
    base = {
        "source_batch_id": SOURCE_BATCH_ID,
        "source_version": TARGET_SOURCE_VERSION,
        "data_domain": "stock",
        "data_type": "stock_financial_canonical_metrics",
    }
    return [
        {
            **base,
            "gate_name": "tdx_line_item_source_proof",
            "severity": "P0",
            "status": "passed",
            "expected_value": "interest_expense=19744658 and announcement_date<=20260615",
            "actual_value": f"interest_expense={proof['line_items']['interest_expense']};announcement_date={proof['announcement_date']}",
            "details": {"source_type": proof["source_type"], "report_period": proof["report_period"]},
        },
        {
            **base,
            "gate_name": "full_v3_row_count",
            "severity": "P0",
            "status": "passed",
            "expected_value": str(EXPECTED_ROW_COUNT),
            "actual_value": str(EXPECTED_ROW_COUNT),
            "details": {},
        },
        {
            **base,
            "gate_name": "semantic_changed_rows",
            "severity": "P0",
            "status": "passed",
            "expected_value": "1",
            "actual_value": str(semantic_changed_rows_count),
            "details": {"changed_identity": TARGET_IDENTITY_KEY},
        },
        {
            **base,
            "gate_name": "tdx_parity_repair_scope",
            "severity": "P1",
            "status": "warning",
            "expected_value": "scoped repair one identity",
            "actual_value": TARGET_IDENTITY_KEY,
            "details": {"reason": "target_machine_tdx_parity_alignment"},
        },
    ]


def read_previous_rows(conn: Any, *, source_trade_date: str, previous_source_version: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *
            FROM stock_financial_metrics_fact
            WHERE source_trade_date = %s
              AND source_version = %s
            ORDER BY stock_identity_key
            """,
            (source_trade_date, previous_source_version),
        )
        return [dict(row) for row in cur.fetchall()]


def read_preflight_baseline(conn: Any, *, source_trade_date: str) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM stock_financial_metrics_fact WHERE source_trade_date = %(trade_date)s AND source_version = %(target_version)s) AS target_rows,
              (SELECT count(*) FROM common_ingest_batch WHERE batch_id = %(batch_id)s OR source_version = %(target_version)s) AS batch_conflicts,
              (SELECT count(*) FROM common_quality_gate_result WHERE source_batch_id = %(batch_id)s OR source_version = %(target_version)s) AS quality_conflicts,
              (SELECT count(*) FROM common_active_source_version WHERE data_domain='stock' AND data_type='stock_financial' AND scope_key=%(trade_date)s AND source_version=%(target_version)s) AS active_conflicts,
              (SELECT count(*) FROM common_active_source_version WHERE data_domain='stock' AND data_type='stock_financial' AND scope_key=%(trade_date)s AND source_version=%(previous_version)s) AS active_previous_rows
            """,
            {
                "trade_date": source_trade_date,
                "target_version": TARGET_SOURCE_VERSION,
                "previous_version": PREVIOUS_SOURCE_VERSION,
                "batch_id": SOURCE_BATCH_ID,
            },
        )
        return dict(cur.fetchone())


def validate_preflight_baseline(baseline: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if int(baseline.get("target_rows") or 0) != 0:
        blockers.append("target_v3_rows_exist")
    if int(baseline.get("batch_conflicts") or 0) != 0:
        blockers.append("batch_conflict")
    if int(baseline.get("quality_conflicts") or 0) != 0:
        blockers.append("quality_conflict")
    if int(baseline.get("active_conflicts") or 0) != 0:
        blockers.append("active_v3_conflict")
    if int(baseline.get("active_previous_rows") or 0) != 1:
        blockers.append("active_v2_missing")
    return blockers


def build_preflight_report(*, baseline: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    blockers = validate_preflight_baseline(baseline)
    p0 = len(blockers)
    return {
        "preflight": "N1_STOCK_FINANCIAL_002831_TDX_PARITY_REPAIR_PREFLIGHT",
        "result": "PREFLIGHT_PASS" if p0 == 0 else "BLOCKED",
        "layer_role": "N1_ingestion",
        "source_trade_date": SOURCE_TRADE_DATE,
        "source_batch_id": SOURCE_BATCH_ID,
        "source_version": TARGET_SOURCE_VERSION,
        "previous_source_version": PREVIOUS_SOURCE_VERSION,
        "runner_readiness": "ready_for_final_gate" if p0 == 0 else "blocked",
        "final_execute_gate_allowed": p0 == 0,
        "expected_rows": EXPECTED_ROW_COUNT,
        "changed_rows": plan.get("semantic_changed_rows_count"),
        "baseline": dict(baseline),
        "blockers": blockers,
        "quality": {"P0": p0, "P1": 1, "P2": 0},
        "allowed_future_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_scope": [
            "condition_*",
            "stock/index/board_daily_bar_fact",
            "outbox/inbox/checkpoint",
            "N2/N3/N4/N5/N6",
            "worker",
            "old_system",
            "real_trading",
        ],
        "rollback_sql": str(DEFAULT_ROLLBACK_SQL),
    }


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_flags(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    unexpected = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_WRITE_TABLES))
    if unexpected:
        raise StockFinancial002831RepairBlocked(f"unexpected_write_tables: {unexpected}")
    if int((commit_plan.get("row_counts") or {}).get("stock_financial_metrics_fact") or 0) != EXPECTED_ROW_COUNT:
        raise StockFinancial002831RepairBlocked("empty_or_incomplete_fact_plan_blocked")
    cur = conn.cursor()
    try:
        insert_ingest_batch(cur, commit_plan)
        insert_stock_financial_rows(cur, list(commit_plan.get("stock_financial_rows") or []))
        insert_quality_rows(cur, list(commit_plan.get("quality_rows") or []))
        upsert_active_source_version(cur, dict(commit_plan.get("active_source_version_row") or {}))
        mark_ingest_batch_passed(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "committed": True,
        "source_batch_id": SOURCE_BATCH_ID,
        "source_version": TARGET_SOURCE_VERSION,
        "previous_source_version": PREVIOUS_SOURCE_VERSION,
        "row_counts": dict(commit_plan.get("row_counts") or {}),
        "written_tables": list(ALLOWED_WRITE_TABLES),
        "rollback_safe": True,
        "rollback_sql": str(DEFAULT_ROLLBACK_SQL),
    }


def insert_ingest_batch(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_path, source_params, raw_hash, row_count, error_count,
          quality_gate_summary, error_summary, rollback_strategy, status, started_at
        )
        VALUES (
          %(batch_id)s, %(trade_date)s, 'stock', 'stock_financial_canonical_metrics',
          'n1.stock_financial_002831_tdx_parity_repair', %(source_version)s,
          NULL, %(source_params)s, NULL, %(row_count)s, 0,
          %(quality_gate_summary)s, NULL, %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": SOURCE_BATCH_ID,
            "trade_date": SOURCE_TRADE_DATE,
            "source_version": TARGET_SOURCE_VERSION,
            "source_params": Jsonb(json_safe({"repair_identity": TARGET_IDENTITY_KEY, "previous_source_version": PREVIOUS_SOURCE_VERSION})),
            "row_count": int((commit_plan.get("row_counts") or {}).get("stock_financial_metrics_fact") or 0),
            "quality_gate_summary": Jsonb(json_safe(commit_plan.get("quality_summary") or {})),
            "rollback_strategy": str(DEFAULT_ROLLBACK_SQL),
        },
    )


def insert_stock_financial_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    if len(rows) != EXPECTED_ROW_COUNT:
        raise StockFinancial002831RepairBlocked("stock_financial_commit_plan_incomplete")
    cur.executemany(
        """
        INSERT INTO stock_financial_metrics_fact (
          stock_identity_key, asof_date, source_trade_date, announcement_date, report_period,
          ts_code, code, exchange, roe, revenue_yoy, profit_yoy, total_revenue,
          net_profit, net_assets, eps, bps, pe_core, total_mv, circ_mv,
          score, warning, quality_status, source, source_batch_id, source_version, raw_payload,
          cash_realization_rate, revenue_yoy_pct, core_profit_yoy_pct, report_core_revenue,
          report_core_profit, core_profit_ttm, core_gt_revenue_yoy, revenue_growth_streak_q,
          core_growth_streak_q, core_gt_revenue_streak_q, forecast_type, forecast_score,
          score_breakdown_json, financial_warning_json, financial_metric_version
        )
        VALUES (
          %(stock_identity_key)s, %(asof_date)s, %(source_trade_date)s, %(announcement_date)s, %(report_period)s,
          %(ts_code)s, %(code)s, %(exchange)s, %(roe)s, %(revenue_yoy)s, %(profit_yoy)s, %(total_revenue)s,
          %(net_profit)s, %(net_assets)s, %(eps)s, %(bps)s, %(pe_core)s, %(total_mv)s, %(circ_mv)s,
          %(score)s, %(warning)s, %(quality_status)s, %(source)s, %(source_batch_id)s, %(source_version)s, %(raw_payload)s,
          %(cash_realization_rate)s, %(revenue_yoy_pct)s, %(core_profit_yoy_pct)s, %(report_core_revenue)s,
          %(report_core_profit)s, %(core_profit_ttm)s, %(core_gt_revenue_yoy)s, %(revenue_growth_streak_q)s,
          %(core_growth_streak_q)s, %(core_gt_revenue_streak_q)s, %(forecast_type)s, %(forecast_score)s,
          %(score_breakdown_json)s, %(financial_warning_json)s, %(financial_metric_version)s
        )
        """,
        [stock_financial_jsonb_row(row) for row in rows],
    )


def insert_quality_rows(cur: Any, rows: list[Mapping[str, Any]]) -> None:
    cur.executemany(
        """
        INSERT INTO common_quality_gate_result (
          source_batch_id, source_version, data_domain, data_type, gate_name,
          severity, status, expected_value, actual_value, details
        )
        VALUES (
          %(source_batch_id)s, %(source_version)s, %(data_domain)s, %(data_type)s,
          %(gate_name)s, %(severity)s, %(status)s, %(expected_value)s, %(actual_value)s, %(details)s
        )
        """,
        [{**dict(row), "details": Jsonb(json_safe(row.get("details") or {}))} for row in rows],
    )


def upsert_active_source_version(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_active_source_version (
          data_domain, data_type, scope_key, source_version, source_batch_id,
          previous_source_version, activated_at, activated_by
        )
        VALUES (
          %(data_domain)s, %(data_type)s, %(scope_key)s, %(source_version)s, %(source_batch_id)s,
          %(previous_source_version)s, now(), %(activated_by)s
        )
        ON CONFLICT (data_domain, data_type, scope_key)
        DO UPDATE SET
          previous_source_version = common_active_source_version.source_version,
          source_version = EXCLUDED.source_version,
          source_batch_id = EXCLUDED.source_batch_id,
          activated_at = now(),
          activated_by = EXCLUDED.activated_by
        """,
        dict(row),
    )


def mark_ingest_batch_passed(cur: Any) -> None:
    cur.execute(
        """
        UPDATE common_ingest_batch
        SET status = 'passed',
            finished_at = now()
        WHERE batch_id = %s
        """,
        (SOURCE_BATCH_ID,),
    )


def validate_rollback_sql_static(path: Path | str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    stripped = strip_sql_comments(text).upper()
    destructive_positions = [pos for token in ("DELETE", "UPDATE") if (pos := stripped.find(token)) != -1]
    first_destructive = min(destructive_positions) if destructive_positions else -1
    raise_pos = stripped.find("RAISE EXCEPTION")
    forbidden_tokens = [
        token
        for token in ("DROP ", "TRUNCATE", "CASCADE")
        if token in stripped
    ]
    forbidden_dml = []
    for table_token in ("COMMON_EVENT_OUTBOX", "COMMON_EVENT_INBOX", "COMMON_EVENT_CONSUMER_CHECKPOINT", "CONDITION_"):
        for verb in ("DELETE", "UPDATE", "INSERT"):
            if f"{verb} FROM {table_token}" in stripped or f"{verb} INTO {table_token}" in stripped or f"UPDATE {table_token}" in stripped:
                forbidden_dml.append(f"{verb}:{table_token}")
    return {
        "raise_before_delete_or_update": raise_pos != -1 and first_destructive != -1 and raise_pos < first_destructive,
        "forbidden_tokens": forbidden_tokens + forbidden_dml,
    }


def strip_sql_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if "--" in line:
            line = line.split("--", 1)[0]
        lines.append(line)
    return "\n".join(lines)


def decimal_text(value: Any) -> str:
    if value is None:
        raise StockFinancial002831RepairBlocked("decimal_value_missing")
    return str(value)


def quantized_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP).normalize()


def write_json(path: Path | str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path | str, title: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "result": payload.get("result"),
        "source_trade_date": payload.get("source_trade_date"),
        "source_batch_id": payload.get("source_batch_id"),
        "source_version": payload.get("source_version"),
        "previous_source_version": payload.get("previous_source_version"),
        "row_counts": payload.get("row_counts"),
        "quality": payload.get("quality"),
        "commit_result": payload.get("commit_result"),
    }
    target.write_text(f"# {title}\n\n```json\n{json.dumps(json_safe(summary), ensure_ascii=False, indent=2)}\n```\n", encoding="utf-8")


def run_once(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    source_trade_date = require_yyyymmdd(args.source_trade_date, "source_trade_date")
    if source_trade_date != SOURCE_TRADE_DATE:
        raise StockFinancial002831RepairBlocked(f"wrong_source_trade_date: expected={SOURCE_TRADE_DATE}, actual={source_trade_date}")
    if args.stock_identity_key != TARGET_IDENTITY_KEY:
        raise StockFinancial002831RepairBlocked("wrong_stock_identity_key")
    if args.previous_source_version != PREVIOUS_SOURCE_VERSION:
        raise StockFinancial002831RepairBlocked("wrong_previous_source_version")
    if args.target_source_version != TARGET_SOURCE_VERSION:
        raise StockFinancial002831RepairBlocked("wrong_target_source_version")
    proof = load_source_proof(args.source_proof_json, source_trade_date=source_trade_date, stock_identity_key=args.stock_identity_key)
    with psycopg.connect(args.dsn, row_factory=dict_row, connect_timeout=10) as conn:
        previous_rows = read_previous_rows(conn, source_trade_date=source_trade_date, previous_source_version=args.previous_source_version)
        plan = build_repair_commit_plan(
            previous_rows=previous_rows,
            proof=proof,
            source_trade_date=source_trade_date,
            previous_source_version=args.previous_source_version,
            target_source_version=args.target_source_version,
        )
        baseline = read_preflight_baseline(conn, source_trade_date=source_trade_date)
        preflight = build_preflight_report(baseline=baseline, plan=plan)
        if preflight["result"] != "PREFLIGHT_PASS":
            return 2, preflight
        if not args.execute:
            return 0, preflight
        commit_result = execute_commit_transaction(
            conn,
            commit_plan=plan,
            execute_requested=args.execute,
            user_confirmed=args.user_confirmed,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
    execute_report = {
        "result": "EXECUTE_PASS",
        "layer_role": "N1_ingestion",
        "source_trade_date": source_trade_date,
        "source_batch_id": SOURCE_BATCH_ID,
        "source_version": TARGET_SOURCE_VERSION,
        "previous_source_version": PREVIOUS_SOURCE_VERSION,
        "commit_result": commit_result,
        "row_counts": commit_result["row_counts"],
        "quality": plan["quality_summary"],
        "side_effects": {
            "writes_postgres": True,
            "writes_condition_tables": False,
            "writes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "writes_parquet": False,
            "enters_n2_n3_n4_n5_n6": False,
            "worker_started": False,
            "old_system_touched": False,
            "real_trading": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return 0, execute_report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3")
    parser.add_argument("--source-trade-date", required=True)
    parser.add_argument("--stock-identity-key", required=True)
    parser.add_argument("--previous-source-version", required=True)
    parser.add_argument("--target-source-version", required=True)
    parser.add_argument("--source-proof-json", default=str(DEFAULT_PROOF_JSON))
    parser.add_argument("--json-report-path")
    parser.add_argument("--markdown-report-path")
    parser.add_argument("--rollback-sql-path", default=str(DEFAULT_ROLLBACK_SQL))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--postgres-commit-enabled", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.execute:
        validate_execute_flags(
            execute_requested=args.execute,
            user_confirmed=args.user_confirmed,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
    try:
        code, payload = run_once(args)
    except StockFinancial002831RepairBlocked as exc:
        print(f"BLOCKED: {exc}")
        return 2
    write_json(args.json_report_path, payload) if args.json_report_path else None
    write_markdown(args.markdown_report_path, "N1 Stock Financial 002831 TDX Parity Repair Report", payload) if args.markdown_report_path else None
    print(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
