#!/usr/bin/env python3
"""Check whether ingestion data is ready for the condition layer.

This is a read-only ingress contract check. It does not compute conditions,
write condition tables, pull external data, start workers, or read the old
system.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import re
from typing import Any, Mapping

import psycopg


DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"
REQUIRED_DATA_TYPES = (
    "stock_daily",
    "stock_daily_basic",
    "stock_financial",
    "index_daily",
    "index_membership",
    "board_daily",
    "board_membership",
)
DATA_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "stock_daily": ("stock_daily", "stock_daily_bar_fact"),
    "stock_daily_basic": ("stock_daily_basic",),
    "stock_financial": ("stock_financial", "stock_financial_metrics_fact"),
    "index_daily": ("index_daily", "index_daily_bar_fact"),
    "index_membership": ("index_membership", "index_membership_fact"),
    "board_daily": ("board_daily", "board_daily_bar_fact"),
    "board_membership": ("board_membership", "board_membership_fact"),
}
CANONICAL_DATA_TYPE = {
    alias: canonical
    for canonical, aliases in DATA_TYPE_ALIASES.items()
    for alias in aliases
}
STOCK_CANONICAL_FINANCIAL_FIELDS = (
    "cash_realization_rate",
    "pe_core",
    "revenue_yoy_pct",
    "core_profit_yoy_pct",
    "report_core_revenue",
    "report_core_profit",
    "core_profit_ttm",
    "core_gt_revenue_yoy",
    "revenue_growth_streak_q",
    "core_growth_streak_q",
    "core_gt_revenue_streak_q",
    "forecast_type",
    "forecast_score",
    "score",
    "score_breakdown_json",
    "financial_warning_json",
    "financial_metric_version",
)
STOCK_CANONICAL_FINANCIAL_CONTENT_FIELDS = tuple(
    field for field in STOCK_CANONICAL_FINANCIAL_FIELDS if field != "financial_metric_version"
)


@dataclass(frozen=True)
class FactSpec:
    table_name: str
    date_column: str
    identity_key_column: str
    date_mode: str = "equal"


FACT_SPECS: dict[str, FactSpec] = {
    "stock_daily": FactSpec("stock_daily_bar_fact", "trade_date", "stock_identity_key"),
    "stock_daily_basic": FactSpec("stock_daily_basic", "trade_date", "stock_identity_key"),
    "stock_financial": FactSpec("stock_financial_metrics_fact", "source_trade_date", "stock_identity_key"),
    "index_daily": FactSpec("index_daily_bar_fact", "trade_date", "index_identity_key"),
    "index_membership": FactSpec("index_membership_fact", "trade_date", "index_identity_key"),
    "board_daily": FactSpec("board_daily_bar_fact", "trade_date", "board_identity_key"),
    "board_membership": FactSpec("board_membership_fact", "trade_date", "board_identity_key"),
}


def require_yyyymmdd(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"source trade date must be YYYYMMDD: {value!r}")
    return value


def fetch_active_versions(
    cur: psycopg.Cursor[Any],
    source_trade_date: str,
    *,
    registry_relation: str = "common_condition_active_source_version_view",
) -> dict[str, dict[str, Any]]:
    aliases = sorted(CANONICAL_DATA_TYPE)
    if registry_relation == "common_condition_active_source_version_view":
        cur.execute(
            """
        SELECT source_trade_date, data_domain, data_type, active_source_version,
               source_batch_id, activated_at, activated_by
        FROM common_condition_active_source_version_view
        WHERE source_trade_date = %s
          AND data_type = ANY(%s)
        ORDER BY data_type, activated_at DESC
            """,
            (source_trade_date, aliases),
        )
    elif registry_relation == "common_active_source_version":
        cur.execute(
            """
        SELECT scope_key AS source_trade_date, data_domain, data_type,
               source_version AS active_source_version,
               source_batch_id, activated_at, activated_by
        FROM common_active_source_version
        WHERE scope_key = %s
          AND data_type = ANY(%s)
        ORDER BY data_type, activated_at DESC
            """,
            (source_trade_date, aliases),
        )
    else:
        raise ValueError(f"unsupported active source registry: {registry_relation}")
    active: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        source_data_type = str(row[2])
        data_type = CANONICAL_DATA_TYPE.get(source_data_type)
        if data_type is None:
            continue
        active.setdefault(
            data_type,
            {
                "source_trade_date": row[0],
                "data_domain": row[1],
                "data_type": data_type,
                "source_data_type": source_data_type,
                "active_source_version": row[3],
                "source_batch_id": row[4],
                "activated_at": row[5].isoformat() if row[5] else None,
                "activated_by": row[6],
            },
        )
    return active


def is_windows_n1_source_version(source_version: str) -> bool:
    return str(source_version or "").startswith("windows_n1_")


def check_fact_rows(
    cur: psycopg.Cursor[Any],
    *,
    data_type: str,
    active_source_version: str,
    source_trade_date: str,
) -> dict[str, Any]:
    spec = FACT_SPECS[data_type]
    operator = "=" if spec.date_mode == "equal" else "<="
    cur.execute(
        f"""
        SELECT count(*)::bigint,
               count(*) FILTER (
                 WHERE {spec.identity_key_column} IS NULL
                    OR {spec.identity_key_column} = ''
               )::bigint
        FROM {spec.table_name}
        WHERE source_version = %s
          AND {spec.date_column} {operator} %s
        """,
        (active_source_version, source_trade_date),
    )
    row_count, missing_identity_count = cur.fetchone()
    row_count = int(row_count)
    missing_identity_count = int(missing_identity_count)
    return {
        "table_name": spec.table_name,
        "date_column": spec.date_column,
        "date_mode": spec.date_mode,
        "row_count": row_count,
        "row_count_gt_zero": row_count > 0,
        "identity_key_column": spec.identity_key_column,
        "missing_identity_key_count": missing_identity_count,
        "identity_key_coverage_100pct": missing_identity_count == 0,
    }


def is_canonical_stock_financial_source_version(source_version: str, source_trade_date: str) -> bool:
    match = re.fullmatch(rf"stock_financial_{re.escape(source_trade_date)}_v(\d+)", str(source_version or ""))
    return bool(match and int(match.group(1)) >= 2)


def evaluate_stock_financial_canonical_readiness(
    *,
    active_source_version: str,
    source_trade_date: str,
    row_count: int,
    missing_columns: list[str],
    financial_metric_version_present_count: int,
    canonical_content_present_count: int,
    canonical_all_empty_count: int,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not is_canonical_stock_financial_source_version(active_source_version, source_trade_date):
        reasons.append("active stock_financial source is not canonical v2+")
    if missing_columns:
        reasons.append("canonical financial columns missing")
    if row_count <= 0:
        reasons.append("stock_financial row_count is 0")
    if row_count > 0 and financial_metric_version_present_count != row_count:
        reasons.append("financial_metric_version coverage is not 100%")
    if row_count > 0 and canonical_content_present_count != row_count:
        reasons.append("canonical financial content_or_warning coverage is not 100%")
    if canonical_all_empty_count:
        reasons.append("canonical_financial_fields_all_empty")
    return {
        "passed": not reasons,
        "active_source_version": active_source_version,
        "source_trade_date": source_trade_date,
        "canonical_source_version_v2_or_higher": is_canonical_stock_financial_source_version(
            active_source_version,
            source_trade_date,
        ),
        "required_columns": list(STOCK_CANONICAL_FINANCIAL_FIELDS),
        "missing_columns": missing_columns,
        "row_count": row_count,
        "financial_metric_version_present_count": financial_metric_version_present_count,
        "canonical_content_present_count": canonical_content_present_count,
        "canonical_all_empty_count": canonical_all_empty_count,
        "failure_reasons": reasons,
    }


def check_stock_financial_canonical_readiness(
    cur: psycopg.Cursor[Any],
    *,
    active_source_version: str,
    source_trade_date: str,
    row_count: int,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'stock_financial_metrics_fact'
          AND column_name = ANY(%s)
        """,
        (list(STOCK_CANONICAL_FINANCIAL_FIELDS),),
    )
    existing_columns = {str(row[0]) for row in cur.fetchall()}
    missing_columns = sorted(set(STOCK_CANONICAL_FINANCIAL_FIELDS) - existing_columns)
    if missing_columns:
        return evaluate_stock_financial_canonical_readiness(
            active_source_version=active_source_version,
            source_trade_date=source_trade_date,
            row_count=row_count,
            missing_columns=missing_columns,
            financial_metric_version_present_count=0,
            canonical_content_present_count=0,
            canonical_all_empty_count=row_count,
        )

    def present_sql(column: str) -> str:
        return (
            f"({column} IS NOT NULL "
            f"AND NULLIF({column}::text, '') IS NOT NULL "
            f"AND {column}::text NOT IN ('null', '{{}}', '[]'))"
        )

    metric_version_present = present_sql("financial_metric_version")
    content_present = " OR ".join(present_sql(column) for column in STOCK_CANONICAL_FINANCIAL_CONTENT_FIELDS)
    cur.execute(
        f"""
        SELECT
          count(*) FILTER (WHERE {metric_version_present})::bigint,
          count(*) FILTER (WHERE {content_present})::bigint,
          count(*) FILTER (WHERE NOT ({content_present}))::bigint
        FROM stock_financial_metrics_fact
        WHERE source_trade_date = %s
          AND source_version = %s
        """,
        (source_trade_date, active_source_version),
    )
    financial_metric_version_present_count, canonical_content_present_count, canonical_all_empty_count = cur.fetchone()
    return evaluate_stock_financial_canonical_readiness(
        active_source_version=active_source_version,
        source_trade_date=source_trade_date,
        row_count=row_count,
        missing_columns=[],
        financial_metric_version_present_count=int(financial_metric_version_present_count or 0),
        canonical_content_present_count=int(canonical_content_present_count or 0),
        canonical_all_empty_count=int(canonical_all_empty_count or 0),
    )


def fetch_condition_source_gap_manifest(
    cur: psycopg.Cursor[Any],
    active: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Fetch the N1-declared rows excluded from the N2 condition universe."""
    source_batch_ids = sorted(
        {
            str(active_row.get("source_batch_id") or "")
            for data_type, active_row in active.items()
            if data_type in {"stock_daily_basic", "stock_financial"} and active_row.get("source_batch_id")
        }
    )
    if not source_batch_ids:
        return empty_condition_source_gap_manifest()
    cur.execute(
        """
        SELECT gate_name, status, actual_value, details
        FROM common_quality_gate_result
        WHERE source_batch_id = ANY(%s)
          AND gate_name = 'condition_source_gap_manifest'
        """,
        (source_batch_ids,),
    )
    manifest_rows: list[dict[str, Any]] = []
    statuses: list[str] = []
    actual_values: list[str] = []
    for row in cur.fetchall():
        statuses.append(str(row[1]))
        actual_values.append(str(row[2]))
        details = parse_json_details(row[3])
        manifest = details.get("manifest") if isinstance(details, dict) else None
        if isinstance(manifest, list):
            manifest_rows.extend(dict(item) for item in manifest if isinstance(item, dict))
    excluded_rows = [
        row
        for row in manifest_rows
        if str(row.get("action") or "") == "exclude_from_condition_universe"
    ]
    return {
        "quality_gate_found": bool(manifest_rows),
        "source_batch_ids": source_batch_ids,
        "statuses": statuses,
        "actual_values": actual_values,
        "manifest_count": len(manifest_rows),
        "excluded_from_condition_universe": len(excluded_rows),
        "valid_exclusion_actions": bool(manifest_rows) and len(excluded_rows) == len(manifest_rows),
        "identity_keys": [str(row.get("identity_key") or "") for row in excluded_rows if row.get("identity_key")],
    }


def empty_condition_source_gap_manifest() -> dict[str, Any]:
    return {
        "quality_gate_found": False,
        "source_batch_ids": [],
        "statuses": [],
        "actual_values": [],
        "manifest_count": 0,
        "excluded_from_condition_universe": 0,
        "valid_exclusion_actions": False,
        "identity_keys": [],
    }


def parse_json_details(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def evaluate_stock_condition_universe(
    *,
    stock_daily_count: int,
    stock_daily_basic_count: int,
    stock_financial_count: int,
    gap_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the stock universe that N2 can actually compute conditions for."""
    reasons: list[str] = []
    expected_condition_stock_universe = stock_daily_basic_count if stock_daily_basic_count == stock_financial_count else min(stock_daily_basic_count, stock_financial_count)
    excluded_from_condition_universe = max(stock_daily_count - expected_condition_stock_universe, 0)
    if stock_daily_basic_count != stock_financial_count:
        reasons.append("stock_daily_basic row_count does not match stock_financial row_count")
    if expected_condition_stock_universe > stock_daily_count:
        reasons.append("condition stock universe exceeds stock_daily universe")
    if excluded_from_condition_universe:
        manifest_excluded = int(gap_manifest.get("excluded_from_condition_universe") or 0)
        manifest_valid = bool(gap_manifest.get("quality_gate_found")) and bool(gap_manifest.get("valid_exclusion_actions"))
        if not manifest_valid or manifest_excluded != excluded_from_condition_universe:
            reasons.append("condition stock universe gap is not covered by condition_source_gap_manifest")
    return {
        "passed": not reasons,
        "stock_daily_row_count": stock_daily_count,
        "stock_daily_basic_row_count": stock_daily_basic_count,
        "stock_financial_row_count": stock_financial_count,
        "expected_condition_stock_universe": expected_condition_stock_universe,
        "excluded_from_condition_universe": excluded_from_condition_universe,
        "condition_source_gap_manifest_count": int(gap_manifest.get("manifest_count") or 0),
        "condition_source_gap_manifest_covers_difference": not excluded_from_condition_universe
        or (
            bool(gap_manifest.get("quality_gate_found"))
            and bool(gap_manifest.get("valid_exclusion_actions"))
            and int(gap_manifest.get("excluded_from_condition_universe") or 0) == excluded_from_condition_universe
        ),
        "failure_reasons": reasons,
    }


def apply_stock_condition_universe_policy(
    checks: list[dict[str, Any]],
    gap_manifest: Mapping[str, Any],
    *,
    windows_n1: bool = False,
) -> dict[str, Any]:
    by_type = {str(item.get("data_type")): item for item in checks if item.get("active_exists")}
    required = ("stock_daily", "stock_daily_basic", "stock_financial")
    if not all(data_type in by_type and isinstance(by_type[data_type].get("fact"), dict) for data_type in required):
        return {}
    stock_daily_count = int(by_type["stock_daily"]["fact"].get("row_count") or 0)
    stock_daily_basic_count = int(by_type["stock_daily_basic"]["fact"].get("row_count") or 0)
    stock_financial_count = int(by_type["stock_financial"]["fact"].get("row_count") or 0)
    if windows_n1:
        evaluation = {
            "passed": True,
            "mode": "full_history_latest_k",
            "stock_daily_row_count": stock_daily_count,
            "stock_daily_basic_row_count": stock_daily_basic_count,
            "stock_financial_row_count": stock_financial_count,
            "expected_condition_stock_universe": stock_daily_count,
            "excluded_from_condition_universe": 0,
            "condition_source_gap_manifest_count": int(gap_manifest.get("manifest_count") or 0),
            "condition_source_gap_manifest_covers_difference": True,
            "failure_reasons": [],
        }
    else:
        evaluation = evaluate_stock_condition_universe(
            stock_daily_count=stock_daily_count,
            stock_daily_basic_count=stock_daily_basic_count,
            stock_financial_count=stock_financial_count,
            gap_manifest=gap_manifest,
        )
    for data_type in required:
        by_type[data_type]["fact"].update(
            {
                "expected_condition_stock_universe": evaluation["expected_condition_stock_universe"],
                "excluded_from_condition_universe": evaluation["excluded_from_condition_universe"],
                "condition_source_gap_manifest_count": evaluation["condition_source_gap_manifest_count"],
                "condition_source_gap_manifest_covers_difference": evaluation["condition_source_gap_manifest_covers_difference"],
            }
        )
    if not evaluation["passed"]:
        target = by_type["stock_financial"]
        existing_reasons = list(target.get("failure_reasons") or [])
        for reason in evaluation["failure_reasons"]:
            if reason not in existing_reasons:
                existing_reasons.append(reason)
        target["failure_reasons"] = existing_reasons
    for item in by_type.values():
        item["passed"] = not item.get("failure_reasons")
    return evaluation


def run_check(dsn: str, source_trade_date: str) -> dict[str, Any]:
    source_trade_date = require_yyyymmdd(source_trade_date)
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on") as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT to_regclass('public.common_condition_active_source_version_view'), "
            "to_regclass('public.common_active_source_version')"
        )
        view_relation, active_relation = cur.fetchone()
        view_exists = view_relation is not None
        registry_relation = (
            "common_condition_active_source_version_view"
            if view_exists
            else "common_active_source_version" if active_relation is not None else None
        )
        if registry_relation is None:
            return {
                "source_trade_date": source_trade_date,
                "passed": False,
                "view_exists": False,
                "missing_data_types": list(REQUIRED_DATA_TYPES),
                "checks": [],
            }

        active = fetch_active_versions(cur, source_trade_date, registry_relation=registry_relation)
        windows_n1 = bool(active) and all(
            is_windows_n1_source_version(str(row.get("active_source_version") or ""))
            for row in active.values()
        )
        checks: list[dict[str, Any]] = []
        for data_type in REQUIRED_DATA_TYPES:
            active_row = active.get(data_type)
            if active_row is None:
                checks.append(
                    {
                        "data_type": data_type,
                        "active_exists": False,
                        "passed": False,
                        "failure_reasons": ["active source version missing"],
                    }
                )
                continue
            fact = check_fact_rows(
                cur,
                data_type=data_type,
                active_source_version=str(active_row["active_source_version"]),
                source_trade_date=source_trade_date,
            )
            reasons: list[str] = []
            if not fact["row_count_gt_zero"]:
                reasons.append("fact row_count is 0")
            if not fact["identity_key_coverage_100pct"]:
                reasons.append("identity_key coverage is not 100%")
            if data_type == "stock_financial" and not windows_n1:
                canonical_financial = check_stock_financial_canonical_readiness(
                    cur,
                    active_source_version=str(active_row["active_source_version"]),
                    source_trade_date=source_trade_date,
                    row_count=int(fact.get("row_count") or 0),
                )
                fact["canonical_financial"] = canonical_financial
                reasons.extend(canonical_financial.get("failure_reasons") or [])
            checks.append(
                {
                    **active_row,
                    "active_exists": True,
                    "fact": fact,
                    "passed": not reasons,
                    "failure_reasons": reasons,
                }
            )
        gap_manifest = fetch_condition_source_gap_manifest(cur, active)
        stock_condition_universe = apply_stock_condition_universe_policy(
            checks,
            gap_manifest,
            windows_n1=windows_n1,
        )
    missing = [data_type for data_type in REQUIRED_DATA_TYPES if data_type not in active]
    return {
        "source_trade_date": source_trade_date,
        "passed": registry_relation is not None and not missing and all(item["passed"] for item in checks),
        "view_exists": view_exists,
        "active_source_registry": registry_relation,
        "windows_n1_compatibility": windows_n1,
        "required_data_types": list(REQUIRED_DATA_TYPES),
        "missing_data_types": missing,
        "condition_source_gap_manifest": gap_manifest,
        "stock_condition_universe": stock_condition_universe,
        "expected_condition_stock_universe": stock_condition_universe.get("expected_condition_stock_universe"),
        "excluded_from_condition_universe": stock_condition_universe.get("excluded_from_condition_universe"),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-trade-date", required=True)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args()

    result = run_check(args.dsn, args.source_trade_date)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
