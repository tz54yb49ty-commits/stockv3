"""Read-only N2 condition_display_basis dry-run builder.

The display basis is generated from an existing active N2 run. It aggregates
condition_basis, condition_pool, and minute_target_scope into one display row
per object. This module never writes display tables.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import (
    STOCK_FINANCIAL_PASS_THROUGH_FIELDS,
    SYMMETRY_TARGET_FIELDS,
    period_trigger_baseline_has_required_shape,
)


DISPLAY_GENERATOR_VERSION = "n2_display_basis_v2_scope_aligned"
DOMAINS = ("stock", "index", "board")
PERIODS = ("y", "q", "m", "w", "d")
REFERENCE_PERIODS = {"Y", "Q", "M", "W", "D"}
SIGNAL_TYPES = {"BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT"}
CONDITION_KEY_RE = re.compile(r"^(BUY:((Y|Q|M|W|D)(,(Y|Q|M|W|D))*|FULL)|SELL:((Y|Q|M|W|D)(,(Y|Q|M|W|D))*|FULL)|BUY_HINT|SELL_HINT)$")
FORBIDDEN_DISPLAY_FIELDS = {
    "trigger_time",
    "trigger_period",
    "action_id",
    "action_status",
    "voice_status",
    "tts_text",
    "sim_trade_id",
    "position_id",
    "user_id",
    "device_id",
    "locked_target_price",
    "target_lock_status",
}


@dataclass(frozen=True)
class DomainConfig:
    domain: str
    basis_table: str
    pool_table: str
    scope_table: str
    display_table: str
    identity_col: str
    code_col: str
    name_col: str
    basis_id_col: str
    pool_id_col: str
    scope_id_col: str
    exchange_col: str | None = None
    board_type_col: str | None = None


DOMAIN_CONFIGS: dict[str, DomainConfig] = {
    "stock": DomainConfig(
        domain="stock",
        basis_table="stock_condition_basis",
        pool_table="stock_condition_pool",
        scope_table="stock_minute_target_scope",
        display_table="stock_condition_display_basis",
        identity_col="stock_identity_key",
        code_col="code",
        name_col="name",
        basis_id_col="stock_condition_basis_id",
        pool_id_col="stock_condition_pool_id",
        scope_id_col="stock_minute_target_scope_id",
        exchange_col="exchange",
    ),
    "index": DomainConfig(
        domain="index",
        basis_table="index_condition_basis",
        pool_table="index_condition_pool",
        scope_table="index_minute_target_scope",
        display_table="index_condition_display_basis",
        identity_col="index_identity_key",
        code_col="code",
        name_col="name",
        basis_id_col="index_condition_basis_id",
        pool_id_col="index_condition_pool_id",
        scope_id_col="index_minute_target_scope_id",
        exchange_col="exchange",
    ),
    "board": DomainConfig(
        domain="board",
        basis_table="board_condition_basis",
        pool_table="board_condition_pool",
        scope_table="board_minute_target_scope",
        display_table="board_condition_display_basis",
        identity_col="board_identity_key",
        code_col="board_code",
        name_col="board_name",
        basis_id_col="board_condition_basis_id",
        pool_id_col="board_condition_pool_id",
        scope_id_col="board_minute_target_scope_id",
        board_type_col="board_type",
    ),
}


def build_condition_display_basis_dry_run(*, dsn: str, run_id: str, include_rows: bool = True) -> dict[str, Any]:
    """Build a read-only display basis preview for an existing N2 run."""
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        run = fetch_condition_run(cur, run_id)
        display_before = fetch_display_table_counts(cur)
        domain_reports = {}
        for domain in DOMAINS:
            config = DOMAIN_CONFIGS[domain]
            basis_rows = fetch_table_rows(cur, config.basis_table, run_id)
            pool_rows = fetch_table_rows(cur, config.pool_table, run_id)
            scope_rows = fetch_table_rows(cur, config.scope_table, run_id)
            rows = build_display_rows_for_domain(config, basis_rows=basis_rows, pool_rows=pool_rows, scope_rows=scope_rows)
            domain_reports[domain] = build_domain_report(config, rows, include_rows=include_rows)
        display_after = fetch_display_table_counts(cur)

    quality = build_display_quality(domain_reports=domain_reports, before_counts=display_before, after_counts=display_after)
    passed = quality["p0_count"] == 0
    return {
        "stage": "N2-Display-3",
        "plan_mode": "condition_display_basis_dry_run",
        "run_id": run_id,
        "source_trade_date": run.get("source_trade_date"),
        "for_trade_date": run.get("for_trade_date"),
        "prev_trade_date": run.get("prev_trade_date"),
        "run_status": run.get("status"),
        "display_generator_version": DISPLAY_GENERATOR_VERSION,
        "display_table_row_counts_before": display_before,
        "display_table_row_counts_after": display_after,
        "display_preview": domain_reports,
        "quality": quality,
        "passed": passed,
        "writes_performed": False,
        "display_basis_written": False,
        "overwrite_performed": False,
        "downstream_layers_touched": False,
        "service_started": False,
        "worker_started": False,
        "can_enter_n2_full_dry_run": passed,
    }


def fetch_condition_run(cur: psycopg.Cursor[dict[str, Any]], run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT run_id, source_trade_date, for_trade_date, prev_trade_date, status,
               p0_count, p1_count, p2_count, source_version, source_versions
        FROM common_condition_run
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"condition run not found: {run_id}")
    return normalize_row(row)


def fetch_display_table_counts(cur: psycopg.Cursor[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for config in DOMAIN_CONFIGS.values():
        cur.execute(f"SELECT count(*)::bigint AS count FROM {config.display_table}")
        counts[config.display_table] = int(cur.fetchone()["count"])
    return counts


def fetch_table_rows(cur: psycopg.Cursor[dict[str, Any]], table_name: str, run_id: str) -> list[dict[str, Any]]:
    cur.execute(f"SELECT * FROM {table_name} WHERE run_id = %s ORDER BY 1", (run_id,))
    return [normalize_row(row) for row in cur.fetchall()]


def build_display_rows_for_domain(
    config: DomainConfig,
    *,
    basis_rows: Sequence[Mapping[str, Any]],
    pool_rows: Sequence[Mapping[str, Any]],
    scope_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    pool_by_identity = group_rows(pool_rows, config.identity_col)
    scope_by_identity = group_rows(scope_rows, config.identity_col)
    basis_by_identity = group_rows(basis_rows, config.identity_col)
    display_rows = []
    # condition_display_basis is the N6-facing view of the active runtime scope.
    # monitor_target/condition_basis remain the full audit universe; display only
    # includes identities that reached minute_target_scope.
    for identity_key in sorted(scope_by_identity):
        if identity_key not in basis_by_identity:
            continue
        basis_group = sorted(basis_by_identity[identity_key], key=lambda row: value_sort_key(row.get(config.basis_id_col)))
        primary_basis = basis_group[0]
        pool_group = sorted(pool_by_identity.get(identity_key, []), key=lambda row: value_sort_key(row.get(config.pool_id_col)))
        scope_group = sorted(scope_by_identity.get(identity_key, []), key=lambda row: value_sort_key(row.get(config.scope_id_col)))
        display_rows.append(build_display_row(config, primary_basis, basis_group, pool_group, scope_group))
    return display_rows


def build_display_row(
    config: DomainConfig,
    primary_basis: Mapping[str, Any],
    basis_group: Sequence[Mapping[str, Any]],
    pool_group: Sequence[Mapping[str, Any]],
    scope_group: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    identity_key = str(primary_basis.get(config.identity_col) or "")
    code = str(primary_basis.get(config.code_col) or "")
    name = str(primary_basis.get(config.name_col) or "")
    pool_ids = compact_ids(row.get(config.pool_id_col) for row in pool_group)
    scope_ids = compact_ids(row.get(config.scope_id_col) for row in scope_group)
    basis_ids = compact_ids(row.get(config.basis_id_col) for row in basis_group)
    selected_condition_keys = sorted_unique(row.get("condition_key") for row in pool_group)
    selected_signal_types = sorted_unique(flatten_array(row.get("allowed_signal_types") for row in pool_group))
    selected_directions = sorted_unique(row.get("direction") for row in pool_group) or sorted_unique(flatten_array(row.get("direction_scope") for row in basis_group))
    selected_lanes = sorted_unique(row.get("lane") for row in pool_group) or sorted_unique(row.get("lane") for row in basis_group)
    selected_monitor_types = sorted_unique(row.get("monitor_type") for row in pool_group) or sorted_unique(row.get("monitor_type") for row in basis_group)
    selected_reason = sorted_unique(flatten_array(row.get("selected_reason") for row in pool_group))
    excluded_reason = sorted_unique(flatten_array(row.get("excluded_reason") for row in pool_group))
    if not pool_group:
        excluded_reason = sorted(set(excluded_reason + ["no_condition_pool_rows_for_identity"]))
    display_scope_reason = display_scope_reason_for(pool_group, scope_group)
    primary_pool = pool_group[0] if pool_group else {}
    primary_scope = scope_group[0] if scope_group else {}
    reference = reference_period_fields(primary_basis)
    row: dict[str, Any] = {
        "run_id": primary_basis.get("run_id"),
        "for_trade_date": primary_basis.get("for_trade_date"),
        "source_trade_date": primary_basis.get("source_trade_date"),
        "prev_trade_date": primary_basis.get("prev_trade_date"),
        config.identity_col: identity_key,
        config.code_col: code,
        config.name_col: name,
        "display_code": code,
        "display_name": name,
        "display_title": f"{code} {name}".strip(),
        "display_summary": f"condition_keys={len(selected_condition_keys)} scope_rows={len(scope_group)}",
        "selected_directions": selected_directions,
        "selected_condition_keys": selected_condition_keys,
        "selected_signal_types": selected_signal_types,
        "selected_lanes": selected_lanes,
        "selected_monitor_types": selected_monitor_types,
        "condition_summary_json": condition_summary(pool_group=pool_group, scope_group=scope_group),
        "target_price_summary_json": target_price_summary(primary_basis),
        "reference_period_summary_json": reference,
        "period_grade_summary_json": period_summary(primary_basis, "period_grade"),
        "period_transition_summary_json": period_summary(primary_basis, "period_transition"),
        **period_columns(primary_basis),
        "level_up_score": primary_basis.get("level_up_score"),
        "level_down_score": primary_basis.get("level_down_score"),
        "prev_up_str": primary_basis.get("prev_up_str"),
        "prev_dn_str": primary_basis.get("prev_dn_str"),
        "buy_target_price": primary_basis.get("buy_target_price"),
        "buy_expected_return_pct": primary_basis.get("buy_expected_return_pct"),
        "sell_target_price": primary_basis.get("sell_target_price"),
        "up_sell_reference_period": reference.get("up_sell_reference_period") or "D",
        "down_buy_reference_period": reference.get("down_buy_reference_period") or "D",
        "clear_sell_ref_period": reference.get("clear_sell_ref_period") or reference.get("up_sell_reference_period") or "D",
        **canonical_target_display_fields(primary_basis),
        "period_trigger_baseline_json": primary_basis.get("period_trigger_baseline_json"),
        "display_policy_name": "default_condition_display_policy",
        "condition_pool_policy_name": primary_pool.get("policy_name"),
        "condition_pool_policy_hash": primary_pool.get("policy_hash"),
        "scope_policy_name": None,
        "scope_policy_hash": None,
        "display_scope_reason": display_scope_reason,
        "selected_reason": selected_reason,
        "excluded_reason": excluded_reason,
        "primary_source_condition_basis_id": basis_ids[0],
        "primary_source_condition_pool_id": pool_ids[0] if pool_ids else None,
        "primary_source_minute_target_scope_id": scope_ids[0] if scope_ids else None,
        "source_condition_basis_ids_json": basis_ids,
        "source_condition_pool_ids_json": pool_ids,
        "source_minute_target_scope_ids_json": scope_ids,
        "source_row_count_json": {
            "condition_basis": len(basis_group),
            "condition_pool": len(pool_group),
            "minute_target_scope": len(scope_group),
        },
        "source_version": primary_basis.get("source_version"),
        "display_status": "visible",
        "quality_status": "passed",
        "quality_reason": None,
        "missing_fields_json": {},
        "raw_json": {
            "display_generator_version": DISPLAY_GENERATOR_VERSION,
            "source_scope_traceability": display_scope_reason,
            "primary_scope_source_condition_pool_id": primary_scope.get("source_condition_pool_id"),
        },
    }
    if config.exchange_col:
        row[config.exchange_col] = primary_basis.get(config.exchange_col)
    if config.board_type_col:
        row[config.board_type_col] = primary_basis.get(config.board_type_col)
        row["is_industry_board"] = str(primary_basis.get(config.board_type_col) or "") == "tdx_industry"
    if config.domain == "index":
        row["fixed_index_member"] = identity_key in {
            "index:SH:000905",
            "index:SZ:399303",
            "index:SH:000001",
            "index:SH:000852",
            "index:SZ:399001",
            "index:SZ:399006",
            "index:SH:000300",
            "index:SH:000016",
            "index:SH:000688",
        }
    if config.domain == "stock":
        row.update(stock_display_fields(primary_basis))
    row["display_policy_hash"] = display_policy_hash(row)
    missing = display_missing_fields(row)
    if missing:
        row["quality_status"] = "warning"
        row["quality_reason"] = "missing_display_fields"
        row["missing_fields_json"] = {"missing_fields": missing}
    return row


def build_domain_report(config: DomainConfig, rows: Sequence[Mapping[str, Any]], *, include_rows: bool) -> dict[str, Any]:
    checks = validate_display_rows(config, rows)
    samples = [public_sample(row, config) for row in rows[:3]]
    report: dict[str, Any] = {
        "display_table": config.display_table,
        "row_count": len(rows),
        "object_count": len({row.get(config.identity_col) for row in rows}),
        "uniqueness": checks["uniqueness"],
        "field_integrity": checks["field_integrity"],
        "traceability": checks["traceability"],
        "forbidden_field_check": checks["forbidden_field_check"],
        "sample_rows": samples,
    }
    if include_rows:
        report["rows"] = [normalize_for_json(row) for row in rows]
    return report


def validate_display_rows(config: DomainConfig, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    keys = [(row.get("run_id"), row.get(config.identity_col)) for row in rows]
    duplicate_keys = sorted([key for key, count in Counter(keys).items() if count > 1])
    invalid_condition_keys = [
        {"identity_key": row.get(config.identity_col), "condition_key": key}
        for row in rows
        for key in row.get("selected_condition_keys", [])
        if not CONDITION_KEY_RE.match(str(key))
    ]
    invalid_signal_types = [
        {"identity_key": row.get(config.identity_col), "signal_type": signal_type}
        for row in rows
        for signal_type in row.get("selected_signal_types", [])
        if str(signal_type) not in SIGNAL_TYPES
    ]
    invalid_reference_rows = [
        row.get(config.identity_col)
        for row in rows
        if not reference_periods_valid(row)
    ]
    baseline_invalid_rows = [
        row.get(config.identity_col)
        for row in rows
        if not period_trigger_baseline_has_required_shape(row.get("period_trigger_baseline_json"))
    ]
    empty_basis_trace_rows = [
        row.get(config.identity_col)
        for row in rows
        if not row.get("source_condition_basis_ids_json")
    ]
    empty_scope_trace_rows = [
        {
            "identity_key": row.get(config.identity_col),
            "display_scope_reason": row.get("display_scope_reason"),
        }
        for row in rows
        if not row.get("source_minute_target_scope_ids_json")
    ]
    forbidden_keys = sorted(set().union(*(set(row) & FORBIDDEN_DISPLAY_FIELDS for row in rows))) if rows else []
    return {
        "uniqueness": {
            "checked": True,
            "duplicate_count": len(duplicate_keys),
            "duplicates_sample": duplicate_keys[:20],
        },
        "field_integrity": {
            "source_condition_basis_ids_missing": len(empty_basis_trace_rows),
            "selected_condition_keys_invalid": len(invalid_condition_keys),
            "selected_signal_types_invalid": len(invalid_signal_types),
            "period_trigger_baseline_invalid_shape": len(baseline_invalid_rows),
            "clear_sell_ref_period_mismatch": sum(1 for row in rows if row.get("clear_sell_ref_period") != row.get("up_sell_reference_period")),
            "invalid_reference_period": len(invalid_reference_rows),
            "invalid_condition_keys_sample": invalid_condition_keys[:20],
            "invalid_signal_types_sample": invalid_signal_types[:20],
        },
        "traceability": {
            "source_minute_target_scope_ids_empty_count": len(empty_scope_trace_rows),
            "source_minute_target_scope_ids_empty_samples": empty_scope_trace_rows[:20],
            "source_minute_target_scope_ids_empty_explained": all(row.get("display_scope_reason") for row in empty_scope_trace_rows),
        },
        "forbidden_field_check": {
            "forbidden_field_count": len(forbidden_keys),
            "forbidden_fields": forbidden_keys,
        },
    }


def build_display_quality(
    *,
    domain_reports: Mapping[str, Mapping[str, Any]],
    before_counts: Mapping[str, int],
    after_counts: Mapping[str, int],
) -> dict[str, Any]:
    items = []
    for domain, report in domain_reports.items():
        table = report["display_table"]
        checks = (report.get("uniqueness") or {}, report.get("field_integrity") or {}, report.get("traceability") or {}, report.get("forbidden_field_check") or {})
        uniqueness, integrity, traceability, forbidden = checks
        add_item(items, domain, "display_unique_identity", uniqueness.get("duplicate_count", 0) == 0, "0", str(uniqueness.get("duplicate_count", 0)), table)
        add_item(items, domain, "display_basis_trace_present", integrity.get("source_condition_basis_ids_missing", 0) == 0, "0", str(integrity.get("source_condition_basis_ids_missing", 0)), table)
        add_item(items, domain, "display_condition_keys_parseable", integrity.get("selected_condition_keys_invalid", 0) == 0, "0", str(integrity.get("selected_condition_keys_invalid", 0)), table)
        add_item(items, domain, "display_signal_types_parseable", integrity.get("selected_signal_types_invalid", 0) == 0, "0", str(integrity.get("selected_signal_types_invalid", 0)), table)
        add_item(items, domain, "display_baseline_shape_valid", integrity.get("period_trigger_baseline_invalid_shape", 0) == 0, "0", str(integrity.get("period_trigger_baseline_invalid_shape", 0)), table)
        add_item(items, domain, "display_clear_sell_alias_match", integrity.get("clear_sell_ref_period_mismatch", 0) == 0, "0", str(integrity.get("clear_sell_ref_period_mismatch", 0)), table)
        add_item(items, domain, "display_reference_period_valid", integrity.get("invalid_reference_period", 0) == 0, "0", str(integrity.get("invalid_reference_period", 0)), table)
        add_item(items, domain, "display_forbidden_fields_absent", forbidden.get("forbidden_field_count", 0) == 0, "0", str(forbidden.get("forbidden_field_count", 0)), table)
        add_item(
            items,
            domain,
            "display_scope_trace_empty_explained",
            bool(traceability.get("source_minute_target_scope_ids_empty_explained", False)),
            "true",
            str(traceability.get("source_minute_target_scope_ids_empty_explained", False)).lower(),
            table,
            severity="P1",
        )
    before_after_changed = {
        table: {"before": before_counts.get(table), "after": after_counts.get(table)}
        for table in sorted(set(before_counts) | set(after_counts))
        if before_counts.get(table) != after_counts.get(table)
    }
    add_item(
        items,
        "common",
        "display_tables_unchanged",
        not before_after_changed,
        "no display table row_count changes during dry-run",
        json.dumps(before_after_changed, sort_keys=True),
        "stock/index/board_condition_display_basis",
    )
    counts = Counter(item["severity"] for item in items if item["status"] == "failed")
    return {
        "p0_count": counts["P0"],
        "p1_count": counts["P1"],
        "p2_count": counts["P2"],
        "items": items,
    }


def add_item(
    items: list[dict[str, Any]],
    domain: str,
    gate_code: str,
    passed: bool,
    expected: str,
    actual: str,
    table_name: str,
    *,
    severity: str = "P0",
) -> None:
    items.append(
        {
            "data_domain": domain,
            "layer_scope": "condition_display_basis",
            "table_name": table_name,
            "gate_code": gate_code,
            "gate_name": gate_code.replace("_", " "),
            "severity": severity,
            "status": "passed" if passed else "failed",
            "expected_value": expected,
            "actual_value": actual,
        }
    )


def display_scope_reason_for(pool_group: Sequence[Mapping[str, Any]], scope_group: Sequence[Mapping[str, Any]]) -> str:
    if scope_group:
        return "source_minute_target_scope_ids_present"
    if pool_group:
        return "condition_pool_rows_present_but_no_minute_target_scope_rows"
    return "basis_only_no_condition_pool_or_scope_rows"


def condition_summary(*, pool_group: Sequence[Mapping[str, Any]], scope_group: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "condition_pool_row_count": len(pool_group),
        "minute_target_scope_row_count": len(scope_group),
        "condition_key_counts": dict(Counter(str(row.get("condition_key")) for row in pool_group if row.get("condition_key"))),
        "direction_counts": dict(Counter(str(row.get("direction")) for row in pool_group if row.get("direction"))),
        "scope_condition_key_counts": dict(Counter(str(row.get("condition_key")) for row in scope_group if row.get("condition_key"))),
    }


def target_price_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "buy_target_price": row.get("buy_target_price"),
        "buy_expected_return_pct": row.get("buy_expected_return_pct"),
        "sell_target_price": row.get("sell_target_price"),
        "sell_expected_return_pct": row.get("sell_expected_return_pct"),
        "symmetry_anchor": row.get("symmetry_anchor"),
        "secondary_symmetry_anchor": row.get("secondary_symmetry_anchor"),
        "amplitude_source_period": row.get("amplitude_source_period"),
        "base_price_policy": row.get("base_price_policy"),
        "base_price": row.get("base_price"),
        "reference_target_price": row.get("reference_target_price"),
        "secondary_target_price": row.get("secondary_target_price"),
        "target_price_trace_json": row.get("target_price_trace_json"),
    }
    for field in SYMMETRY_TARGET_FIELDS:
        if field.startswith(("up_secondary_", "down_secondary_")):
            summary[field] = row.get(field)
    return summary


def canonical_target_display_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in SYMMETRY_TARGET_FIELDS}


def reference_period_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    up = row.get("up_sell_reference_period") or "D"
    clear = row.get("clear_sell_ref_period") or up
    return {
        "main_up_anchor": row.get("main_up_anchor"),
        "up_reference_period": row.get("up_reference_period"),
        "up_sell_reference_period": up,
        "main_down_anchor": row.get("main_down_anchor"),
        "down_reference_period": row.get("down_reference_period"),
        "down_buy_reference_period": row.get("down_buy_reference_period") or "D",
        "clear_sell_ref_period": clear,
    }


def period_summary(row: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    return {period.upper(): row.get(f"{prefix}_{period}") for period in PERIODS}


def period_columns(row: Mapping[str, Any]) -> dict[str, Any]:
    output = {}
    for prefix in ("period_grade", "period_transition"):
        for period in PERIODS:
            output[f"{prefix}_{period}"] = row.get(f"{prefix}_{period}")
    return output


def stock_display_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "total_mv": row.get("total_mv"),
        "circ_mv": row.get("circ_mv"),
        "pe_core": row.get("pe_core"),
        "score": row.get("score"),
        "recommendation_level": row.get("recommendation_level"),
        "recommendation_reason": row.get("recommendation_reason"),
        "is_st": row.get("is_st") or False,
        "stock_status": row.get("stock_status") or "unknown",
        "official_daily_proof": row.get("official_daily_proof") or False,
        "financial_quality_status": row.get("financial_quality_status"),
        **{field: row.get(field) for field in STOCK_FINANCIAL_PASS_THROUGH_FIELDS},
        "main_index_identity_key": row.get("main_index_identity_key"),
        "main_index_code": row.get("main_index_code"),
        "main_index_name": row.get("main_index_name"),
        "preferred_board_identity_key": row.get("preferred_board_identity_key"),
        "preferred_board_code": row.get("preferred_board_code"),
        "preferred_board_name": row.get("preferred_board_name"),
        "linked_board_identity_keys": row.get("linked_board_identity_keys") or [],
    }


def reference_periods_valid(row: Mapping[str, Any]) -> bool:
    return (
        row.get("up_sell_reference_period") in REFERENCE_PERIODS
        and row.get("down_buy_reference_period") in REFERENCE_PERIODS
        and row.get("clear_sell_ref_period") in REFERENCE_PERIODS
        and row.get("clear_sell_ref_period") == row.get("up_sell_reference_period")
    )


def display_missing_fields(row: Mapping[str, Any]) -> list[str]:
    required = ("run_id", "for_trade_date", "source_trade_date", "prev_trade_date", "source_version", "primary_source_condition_basis_id")
    return [field for field in required if row.get(field) in (None, "", [])]


def display_policy_hash(row: Mapping[str, Any]) -> str:
    payload = {
        "version": DISPLAY_GENERATOR_VERSION,
        "run_id": row.get("run_id"),
        "identity_key": identity_from_row(row),
        "basis_ids": row.get("source_condition_basis_ids_json"),
        "pool_ids": row.get("source_condition_pool_ids_json"),
        "scope_ids": row.get("source_minute_target_scope_ids_json"),
    }
    text = json.dumps(normalize_for_json(payload), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def identity_from_row(row: Mapping[str, Any]) -> Any:
    for key in ("stock_identity_key", "index_identity_key", "board_identity_key"):
        if key in row:
            return row.get(key)
    return None


def public_sample(row: Mapping[str, Any], config: DomainConfig) -> dict[str, Any]:
    return normalize_for_json(
        {
            "identity_key": row.get(config.identity_col),
            "code": row.get(config.code_col),
            "name": row.get(config.name_col),
            "selected_condition_keys": row.get("selected_condition_keys"),
            "selected_signal_types": row.get("selected_signal_types"),
            "source_condition_basis_ids_json": row.get("source_condition_basis_ids_json"),
            "source_condition_pool_ids_json": row.get("source_condition_pool_ids_json"),
            "source_minute_target_scope_ids_json": row.get("source_minute_target_scope_ids_json"),
            "display_scope_reason": row.get("display_scope_reason"),
            "buy_target_price": row.get("buy_target_price"),
            "sell_target_price": row.get("sell_target_price"),
            "up_sell_reference_period": row.get("up_sell_reference_period"),
            "down_buy_reference_period": row.get("down_buy_reference_period"),
            "quality_status": row.get("quality_status"),
        }
    )


def group_rows(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "")].append(row)
    grouped.pop("", None)
    return dict(grouped)


def flatten_array(values: Iterable[Any]) -> list[Any]:
    output = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            output.extend(value)
        else:
            output.append(value)
    return output


def sorted_unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value) for value in values if value not in (None, "")})


def compact_ids(values: Iterable[Any]) -> list[int]:
    output = []
    for value in values:
        if value in (None, ""):
            continue
        output.append(int(value))
    return output


def value_sort_key(value: Any) -> tuple[int, str]:
    if value in (None, ""):
        return (1, "")
    return (0, str(value).zfill(20))


def normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: normalize_value(value) for key, value in dict(row).items()}


def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in value.items()}
    return value


def normalize_for_json(value: Any) -> Any:
    return normalize_value(value)
