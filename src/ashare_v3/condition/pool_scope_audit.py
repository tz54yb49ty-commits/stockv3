"""Read-only audit for condition_pool default object ranges.

N2-E4 checks whether an active condition run's condition_pool tables already
match the default object universe used by minute_target_scope. It only reads
PostgreSQL metadata and condition-layer rows.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.active_status import active_status_order_sql, active_status_sql_list


FIXED_INDEX_CODES = ("000905", "399303", "000001", "000852", "399001", "399006", "000300", "000016", "000688")
STOCK_MIN_TOTAL_MV_WAN = "1000000"


def fetch_active_condition_run_id(dsn: str, *, source_trade_date: str, for_trade_date: str) -> str:
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id
            FROM common_condition_run
            WHERE source_trade_date = %s
              AND for_trade_date = %s
              AND status IN (""" + active_status_sql_list() + """)
            ORDER BY """ + active_status_order_sql("status") + """,
                     finished_at DESC NULLS LAST,
                     created_at DESC
            LIMIT 1
            """,
            (source_trade_date, for_trade_date),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"no active condition run for {source_trade_date}->{for_trade_date}")
    return str(row["run_id"])


def fetch_condition_pool_scope_audit(dsn: str, *, run_id: str) -> dict[str, Any]:
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        run = fetch_run_row(cur, run_id)
        pool = {
            "index": fetch_index_pool_audit(cur, run_id),
            "board": fetch_board_pool_audit(cur, run_id),
            "stock": fetch_stock_pool_audit(cur, run_id),
        }
        scope = {
            "index": fetch_index_scope_audit(cur, run_id),
            "board": fetch_board_scope_audit(cur, run_id),
            "stock": fetch_stock_scope_audit(cur, run_id),
        }
    return build_condition_pool_scope_audit_report(run=run, pool=pool, scope=scope)


def build_condition_pool_scope_audit_report(
    *,
    run: Mapping[str, Any],
    pool: Mapping[str, Mapping[str, Any]],
    scope: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    quality_items = build_quality_items(pool=pool, scope=scope)
    severity_counts = count_severities(quality_items)
    needs_remediation = severity_counts["P0"] > 0
    return {
        "stage": "N2-E4",
        "plan_mode": "condition_pool_default_range_audit",
        "run_id": run.get("run_id"),
        "source_trade_date": run.get("source_trade_date"),
        "for_trade_date": run.get("for_trade_date"),
        "prev_trade_date": run.get("prev_trade_date"),
        "pool_audit": dict(pool),
        "scope_audit": dict(scope),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "needs_remediation": needs_remediation,
        "remediation_plan": remediation_plan(run, pool) if needs_remediation else {"required": False},
        "object_count_vs_row_count_note": {
            "index_minute_target_scope": "index scope rows are condition_pool-derived object + direction + condition_key rows; 18 only means 9 objects across two directions when the pool contains that shape",
            "board_minute_target_scope": "board scope rows are condition_pool-derived object + direction + condition_key rows",
            "condition_pool_rows": "pool rows are object + direction + condition_key rows, not object counts",
        },
        "read_only_database_checks": True,
        "will_execute_sql": False,
        "writes_performed": False,
        "overwrite_performed": False,
        "minute_kline_pulled": False,
        "downstream_layers_touched": False,
    }


def fetch_run_row(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT run_id, source_trade_date, for_trade_date, prev_trade_date, status,
               p0_count, p1_count, p2_count, source_versions, raw_json
        FROM common_condition_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"condition run not found: {run_id}")
    return normalize_row(row)


def fetch_index_pool_audit(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(DISTINCT index_identity_key)::bigint AS object_count,
               count(DISTINCT direction)::bigint AS direction_count,
               count(*) FILTER (WHERE code <> ALL(%s))::bigint AS out_of_range_row_count,
               count(DISTINCT index_identity_key) FILTER (WHERE code <> ALL(%s))::bigint AS out_of_range_object_count
        FROM index_condition_pool
        WHERE run_id = %s
        """,
        (list(FIXED_INDEX_CODES), list(FIXED_INDEX_CODES), run_id),
    )
    summary = normalize_row(cur.fetchone() or {})
    cur.execute(
        """
        SELECT DISTINCT code
        FROM index_condition_pool
        WHERE run_id = %s
        ORDER BY code
        """,
        (run_id,),
    )
    codes = [str(row["code"]) for row in cur.fetchall()]
    return {
        **summary,
        "expected_object_universe": list(FIXED_INDEX_CODES),
        "present_fixed_codes": [code for code in FIXED_INDEX_CODES if code in set(codes)],
        "missing_fixed_codes": [code for code in FIXED_INDEX_CODES if code not in set(codes)],
        "out_of_range_codes_sample": [code for code in codes if code not in FIXED_INDEX_CODES][:20],
        "condition_key_counts": fetch_counts(cur, "index_condition_pool", "condition_key", run_id),
        "direction_counts": fetch_counts(cur, "index_condition_pool", "direction", run_id),
    }


def fetch_board_pool_audit(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(DISTINCT board_identity_key)::bigint AS object_count,
               count(DISTINCT direction)::bigint AS direction_count,
               count(*) FILTER (WHERE board_type <> 'tdx_industry')::bigint AS out_of_range_row_count,
               count(DISTINCT board_identity_key) FILTER (WHERE board_type <> 'tdx_industry')::bigint AS out_of_range_object_count
        FROM board_condition_pool
        WHERE run_id = %s
        """,
        (run_id,),
    )
    summary = normalize_row(cur.fetchone() or {})
    cur.execute(
        """
        SELECT DISTINCT board_code, board_type
        FROM board_condition_pool
        WHERE run_id = %s
          AND board_type <> 'tdx_industry'
        ORDER BY board_type, board_code
        LIMIT 20
        """,
        (run_id,),
    )
    return {
        **summary,
        "expected_board_type": "tdx_industry",
        "out_of_range_board_codes_sample": [f"{row['board_code']}:{row['board_type']}" for row in cur.fetchall()],
        "condition_key_counts": fetch_counts(cur, "board_condition_pool", "condition_key", run_id),
        "direction_counts": fetch_counts(cur, "board_condition_pool", "direction", run_id),
    }


def fetch_stock_pool_audit(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(DISTINCT p.stock_identity_key)::bigint AS object_count,
               count(DISTINCT p.direction)::bigint AS direction_count,
               count(*) FILTER (WHERE b.total_mv IS NULL OR b.total_mv < %s)::bigint AS out_of_range_row_count,
               count(DISTINCT p.stock_identity_key) FILTER (WHERE b.total_mv IS NULL OR b.total_mv < %s)::bigint AS out_of_range_object_count,
               count(*) FILTER (WHERE b.total_mv >= %s)::bigint AS in_range_row_count,
               count(DISTINCT p.stock_identity_key) FILTER (WHERE b.total_mv >= %s)::bigint AS in_range_object_count
        FROM stock_condition_pool p
        JOIN stock_condition_basis b
          ON b.stock_condition_basis_id = p.source_condition_basis_id
        WHERE p.run_id = %s
        """,
        (STOCK_MIN_TOTAL_MV_WAN, STOCK_MIN_TOTAL_MV_WAN, STOCK_MIN_TOTAL_MV_WAN, STOCK_MIN_TOTAL_MV_WAN, run_id),
    )
    summary = normalize_row(cur.fetchone() or {})
    cur.execute(
        """
        SELECT p.code, p.name, b.total_mv, count(*)::bigint AS row_count
        FROM stock_condition_pool p
        JOIN stock_condition_basis b
          ON b.stock_condition_basis_id = p.source_condition_basis_id
        WHERE p.run_id = %s
          AND (b.total_mv IS NULL OR b.total_mv < %s)
        GROUP BY p.code, p.name, b.total_mv
        ORDER BY row_count DESC, p.code
        LIMIT 20
        """,
        (run_id, STOCK_MIN_TOTAL_MV_WAN),
    )
    return {
        **summary,
        "min_total_mv_wan": STOCK_MIN_TOTAL_MV_WAN,
        "out_of_range_samples": [normalize_row(row) for row in cur.fetchall()],
        "condition_key_counts": fetch_counts(cur, "stock_condition_pool", "condition_key", run_id),
        "direction_counts": fetch_counts(cur, "stock_condition_pool", "direction", run_id),
    }


def fetch_index_scope_audit(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(DISTINCT s.index_identity_key)::bigint AS object_count,
               count(DISTINCT s.direction)::bigint AS direction_count,
               count(*) FILTER (WHERE s.code <> ALL(%s))::bigint AS out_of_range_row_count,
               count(*) FILTER (WHERE p.index_condition_pool_id IS NULL OR p.run_id <> s.run_id)::bigint AS pool_link_violation_row_count
        FROM index_minute_target_scope s
        LEFT JOIN index_condition_pool p
          ON p.index_condition_pool_id = s.source_condition_pool_id
        WHERE s.run_id = %s
        """,
        (list(FIXED_INDEX_CODES), run_id),
    )
    summary = normalize_row(cur.fetchone() or {})
    object_count = int(summary.get("object_count") or 0)
    direction_count = int(summary.get("direction_count") or 0)
    return {
        **summary,
        "expected_object_count": len(FIXED_INDEX_CODES),
        "expected_row_formula": "index_condition_pool_object_count * direction_count_or_condition_key_rows",
        "expected_row_count_from_formula": object_count * direction_count,
        "object_count_row_count_explanation": f"{object_count} index objects across {direction_count} directions = {int(summary.get('row_count') or 0)} condition_pool-derived scope rows",
        "direction_counts": fetch_counts(cur, "index_minute_target_scope", "direction", run_id),
        "scope_source_counts": fetch_counts(cur, "index_minute_target_scope", "scope_source", run_id),
    }


def fetch_board_scope_audit(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(DISTINCT s.board_identity_key)::bigint AS object_count,
               count(DISTINCT s.direction)::bigint AS direction_count,
               count(*) FILTER (WHERE s.board_type <> 'tdx_industry')::bigint AS out_of_range_row_count,
               count(*) FILTER (WHERE p.board_condition_pool_id IS NULL OR p.run_id <> s.run_id)::bigint AS pool_link_violation_row_count
        FROM board_minute_target_scope s
        LEFT JOIN board_condition_pool p
          ON p.board_condition_pool_id = s.source_condition_pool_id
        WHERE s.run_id = %s
        """,
        (run_id,),
    )
    summary = normalize_row(cur.fetchone() or {})
    object_count = int(summary.get("object_count") or 0)
    direction_count = int(summary.get("direction_count") or 0)
    return {
        **summary,
        "expected_row_formula": "board_condition_pool_object_count * direction_count_or_condition_key_rows",
        "expected_row_count_from_formula": object_count * direction_count,
        "object_count_row_count_explanation": f"{object_count} board objects across {direction_count} directions = {int(summary.get('row_count') or 0)} condition_pool-derived scope rows",
        "direction_counts": fetch_counts(cur, "board_minute_target_scope", "direction", run_id),
        "scope_source_counts": fetch_counts(cur, "board_minute_target_scope", "scope_source", run_id),
    }


def fetch_stock_scope_audit(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count,
               count(DISTINCT s.stock_identity_key)::bigint AS object_count,
               count(DISTINCT s.direction)::bigint AS direction_count,
               count(*) FILTER (WHERE s.total_mv IS NULL OR s.total_mv < s.market_value_threshold)::bigint AS market_value_violation_row_count,
               count(*) FILTER (WHERE p.stock_condition_pool_id IS NULL OR p.run_id <> s.run_id)::bigint AS pool_link_violation_row_count
        FROM stock_minute_target_scope s
        LEFT JOIN stock_condition_pool p
          ON p.stock_condition_pool_id = s.source_condition_pool_id
        WHERE s.run_id = %s
        """,
        (run_id,),
    )
    summary = normalize_row(cur.fetchone() or {})
    return {
        **summary,
        "scope_source_counts": fetch_counts(cur, "stock_minute_target_scope", "scope_source", run_id),
        "direction_counts": fetch_counts(cur, "stock_minute_target_scope", "direction", run_id),
        "condition_key_counts": fetch_counts(cur, "stock_minute_target_scope", "condition_key", run_id),
    }


def fetch_counts(cur: psycopg.Cursor[dict[str, Any]], table: str, column: str, run_id: str) -> dict[str, int]:
    cur.execute(
        f"""
        SELECT {column}, count(*)::bigint AS count
        FROM {table}
        WHERE run_id = %s
        GROUP BY {column}
        ORDER BY count DESC, {column}
        """,
        (run_id,),
    )
    return {str(row[column]): int(row["count"]) for row in cur.fetchall()}


def build_quality_items(
    *,
    pool: Mapping[str, Mapping[str, Any]],
    scope: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    items = [
        quality_item(
            "P0",
            "passed" if int(pool["index"].get("out_of_range_row_count") or 0) == 0 else "failed",
            "index_condition_pool_default_universe",
            "index_condition_pool must only contain the fixed index object universe",
            expected="only fixed index codes; fixed codes may be absent when no eligible pool condition exists",
            actual=f"objects={pool['index'].get('object_count')} out_of_range_rows={pool['index'].get('out_of_range_row_count')}",
        ),
        quality_item(
            "P0",
            "passed" if int(pool["board"].get("out_of_range_row_count") or 0) == 0 else "failed",
            "board_condition_pool_default_universe",
            "board_condition_pool must only contain board_type=tdx_industry boards",
            expected="board_type=tdx_industry",
            actual=f"objects={pool['board'].get('object_count')} out_of_range_rows={pool['board'].get('out_of_range_row_count')}",
        ),
        quality_item(
            "P0",
            "passed" if int(pool["stock"].get("out_of_range_row_count") or 0) == 0 else "failed",
            "stock_condition_pool_default_universe",
            "stock_condition_pool must only contain stocks with total_mv >= 100 yi and eligible conditions",
            expected=f"total_mv >= {STOCK_MIN_TOTAL_MV_WAN}",
            actual=f"objects={pool['stock'].get('object_count')} out_of_range_rows={pool['stock'].get('out_of_range_row_count')}",
        ),
        quality_item(
            "P0",
            "passed" if int(scope["index"].get("out_of_range_row_count") or 0) == 0 and int(scope["index"].get("pool_link_violation_row_count") or 0) == 0 else "failed",
            "index_scope_pool_and_default_universe",
            "index_minute_target_scope must link to index_condition_pool and stay inside fixed index universe",
            expected="linked index_condition_pool rows and fixed index universe",
            actual=f"pool_link_violations={scope['index'].get('pool_link_violation_row_count')} out_of_range_rows={scope['index'].get('out_of_range_row_count')}",
        ),
        quality_item(
            "P0",
            "passed" if int(scope["board"].get("out_of_range_row_count") or 0) == 0 and int(scope["board"].get("pool_link_violation_row_count") or 0) == 0 else "failed",
            "board_scope_pool_and_default_universe",
            "board_minute_target_scope must link to board_condition_pool and stay inside board_type=tdx_industry boards",
            expected="linked board_condition_pool rows and board_type=tdx_industry",
            actual=f"pool_link_violations={scope['board'].get('pool_link_violation_row_count')} out_of_range_rows={scope['board'].get('out_of_range_row_count')}",
        ),
        quality_item(
            "P0",
            "passed" if int(scope["stock"].get("market_value_violation_row_count") or 0) == 0 and int(scope["stock"].get("pool_link_violation_row_count") or 0) == 0 else "failed",
            "stock_scope_pool_and_market_value",
            "stock_minute_target_scope must link to stock_condition_pool and keep total_mv threshold",
            expected="linked condition_pool rows and total_mv threshold",
            actual=f"pool_link_violations={scope['stock'].get('pool_link_violation_row_count')} market_value_violations={scope['stock'].get('market_value_violation_row_count')}",
        ),
        quality_item("P0", "passed", "read_only_audit", "N2-E4 audit is read-only and performs no overwrite"),
    ]
    return items


def remediation_plan(run: Mapping[str, Any], pool: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "required": True,
        "current_run_id": run.get("run_id"),
        "next_step": "prepare overwrite dry-run that filters condition_pool before writing a new active run",
        "do_not_execute_in_n2_e4": True,
        "recommended_filters": {
            "index_condition_pool": {"include_codes": list(FIXED_INDEX_CODES)},
            "board_condition_pool": {"board_type": "tdx_industry"},
            "stock_condition_pool": {"min_total_mv_wan": STOCK_MIN_TOTAL_MV_WAN, "condition_families": ["ordinary", "full", "hint"]},
        },
        "estimated_rows_to_exclude": {
            "index_condition_pool": int(pool["index"].get("out_of_range_row_count") or 0),
            "board_condition_pool": int(pool["board"].get("out_of_range_row_count") or 0),
            "stock_condition_pool": int(pool["stock"].get("out_of_range_row_count") or 0),
        },
        "overwrite_plan": {
            "requires_user_confirmation": True,
            "preserve_current_run_until_postcheck_passes": True,
            "new_run_should_supersede_current_run": True,
        },
    }


def quality_item(severity: str, status: str, gate_code: str, gate_name: str, *, expected: Any = None, actual: Any = None) -> dict[str, Any]:
    return {
        "severity": severity,
        "status": status,
        "gate_code": gate_code,
        "gate_name": gate_name,
        "expected_value": expected,
        "actual_value": actual,
    }


def count_severities(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        if item.get("status") in {"failed", "warning"}:
            counts[str(item.get("severity") or "")] += 1
    return {"P0": counts["P0"], "P1": counts["P1"], "P2": counts["P2"]}


def normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output
