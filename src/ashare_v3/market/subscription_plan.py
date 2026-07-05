"""N3-0 market data subscription dry-run planner.

The planner reads the active condition run and the physically separated
stock/index/board minute_target_scope tables, expands required data kinds,
deduplicates market data subscriptions, and builds a pull plan preview. It
does not call market data adapters and does not write market data facts.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item
from ashare_v3.ingestion.common import require_yyyymmdd


ASSET_KINDS = ("stock", "index", "board")
REQUIRED_DATA_KINDS = ("realtime_daily_snapshot", "minute_bar_1m", "previous_day_minute_bar_1m")
STANDARD_SIGNAL_TYPES = ("BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT")
ACTIVE_CONDITION_RUN_STATUSES = ("passed", "passed_active")
SCOPE_TABLES = {
    "stock": "stock_minute_target_scope",
    "index": "index_minute_target_scope",
    "board": "board_minute_target_scope",
}
SCOPE_ID_COLUMNS = {
    "stock": "stock_minute_target_scope_id",
    "index": "index_minute_target_scope_id",
    "board": "board_minute_target_scope_id",
}
POOL_ID_COLUMNS = {
    "stock": "stock_condition_pool_id",
    "index": "index_condition_pool_id",
    "board": "board_condition_pool_id",
}
ADAPTER_NAMES = {
    "stock": "StockMarketDataAdapter",
    "index": "IndexMarketDataAdapter",
    "board": "BoardMarketDataAdapter",
}


def build_market_data_subscription_plan_dry_run(
    *,
    dsn: str,
    run_id: str | None = None,
    source_trade_date: str | None = None,
    for_trade_date: str | None = None,
    include_rows: bool = True,
) -> dict[str, Any]:
    """Read active N2 scope and build an N3-0 dry-run report."""

    if source_trade_date:
        source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    if for_trade_date:
        for_trade_date = require_yyyymmdd(for_trade_date, "for_trade_date")

    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        active_runs = fetch_condition_run_candidates(
            cur,
            run_id=run_id,
            source_trade_date=source_trade_date,
            for_trade_date=for_trade_date,
        )
        active_run, active_quality = select_active_condition_run(active_runs, requested_run_id=run_id)
        if active_run is None:
            return build_blocked_report(active_quality, active_runs, include_rows=include_rows)

        table_status = fetch_scope_table_status(cur)
        missing_tables = [table for table, exists in table_status.items() if not exists]
        if missing_tables:
            quality_items = list(active_quality)
            quality_items.append(
                quality_item(
                    "P0",
                    "failed",
                    "scope_tables_exist",
                    "N3-0 requires stock/index/board minute_target_scope tables",
                    expected="all required scope tables exist",
                    actual=",".join(missing_tables),
                )
            )
            return build_blocked_report(quality_items, [active_run], include_rows=include_rows)

        scope_rows_by_asset = {
            asset_kind: fetch_scope_rows(cur, asset_kind, str(active_run["run_id"]))
            for asset_kind in ASSET_KINDS
        }
        trade_calendar_detail = fetch_trade_calendar_detail(cur, str(active_run["for_trade_date"]))

    return build_market_data_subscription_plan(
        active_run=active_run,
        scope_rows_by_asset=scope_rows_by_asset,
        preflight_quality_items=active_quality,
        table_status=table_status,
        trade_calendar_detail=trade_calendar_detail,
        include_rows=include_rows,
    )


def fetch_condition_run_candidates(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    run_id: str | None,
    source_trade_date: str | None,
    for_trade_date: str | None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if run_id:
        where.append("run_id = %s")
        params.append(run_id)
    else:
        where.append("status = ANY(%s)")
        params.append(list(ACTIVE_CONDITION_RUN_STATUSES))
    if source_trade_date:
        where.append("source_trade_date = %s")
        params.append(source_trade_date)
    if for_trade_date:
        where.append("for_trade_date = %s")
        params.append(for_trade_date)

    cur.execute(
        f"""
        SELECT run_id, source_trade_date, for_trade_date, prev_trade_date,
               status, p0_count, p1_count, p2_count, source_versions,
               raw_json, started_at, finished_at, created_at
        FROM common_condition_run
        WHERE {' AND '.join(where)}
        ORDER BY finished_at DESC NULLS LAST, created_at DESC, run_id DESC
        """,
        params,
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def select_active_condition_run(
    active_runs: Sequence[Mapping[str, Any]],
    *,
    requested_run_id: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    quality_items: list[dict[str, Any]] = []
    expected = "exactly one passed active condition run"
    if requested_run_id:
        expected = f"condition run {requested_run_id} exists and is passed"

    quality_items.append(
        quality_item(
            "P0",
            "passed" if len(active_runs) == 1 else "failed",
            "active_condition_run_unique",
            "N3-0 must start from exactly one active condition run",
            expected=expected,
            actual=str(len(active_runs)),
            details={"run_ids": [row.get("run_id") for row in active_runs[:10]]},
        )
    )
    if len(active_runs) != 1:
        return None, quality_items

    active_run = normalize_mapping(active_runs[0])
    status = str(active_run.get("status") or "")
    p0_count = int(active_run.get("p0_count") or 0)
    source_trade_date = str(active_run.get("source_trade_date") or "")
    prev_trade_date = str(active_run.get("prev_trade_date") or "")
    quality_items.extend(
        [
            quality_item(
                "P0",
                "passed" if status in ACTIVE_CONDITION_RUN_STATUSES else "failed",
                "active_condition_run_status_passed",
                "active condition run must be passed",
                expected="/".join(ACTIVE_CONDITION_RUN_STATUSES),
                actual=status,
            ),
            quality_item(
                "P0",
                "passed" if p0_count == 0 else "failed",
                "active_condition_run_p0_clean",
                "active condition run P0 count must be zero",
                expected="0",
                actual=str(p0_count),
            ),
            quality_item(
                "P0",
                "passed" if source_trade_date == prev_trade_date else "failed",
                "active_condition_run_prev_trade_date_contract",
                "source_trade_date must equal prev_trade_date for N2/N3 handoff",
                expected=source_trade_date,
                actual=prev_trade_date,
            ),
        ]
    )
    if count_quality_severities(quality_items)["P0"] > 0:
        return None, quality_items
    return active_run, quality_items


def fetch_scope_table_status(cur: psycopg.Cursor[dict[str, Any]]) -> dict[str, bool]:
    status: dict[str, bool] = {}
    for table_name in SCOPE_TABLES.values():
        cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
        status[table_name] = cur.fetchone()["regclass"] is not None
    return status


def fetch_trade_calendar_detail(cur: psycopg.Cursor[dict[str, Any]], trade_date: str) -> dict[str, Any]:
    cur.execute("SELECT to_regclass('public.common_trade_calendar') AS regclass")
    table_exists = cur.fetchone()["regclass"] is not None
    if not table_exists:
        return {
            "trade_date": trade_date,
            "table_exists": False,
            "row_exists": False,
            "row": None,
        }

    cur.execute(
        """
        SELECT to_jsonb(t) AS row
        FROM common_trade_calendar t
        WHERE trade_date = %s
        LIMIT 1
        """,
        (trade_date,),
    )
    fetched = cur.fetchone()
    row = normalize_mapping(fetched["row"]) if fetched and fetched.get("row") else None
    return {
        "trade_date": trade_date,
        "table_exists": True,
        "row_exists": row is not None,
        "row": row,
    }


def fetch_scope_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    asset_kind: str,
    condition_run_id: str,
) -> list[dict[str, Any]]:
    if asset_kind == "stock":
        query = """
            SELECT stock_minute_target_scope_id AS source_scope_id,
                   'stock_minute_target_scope' AS source_scope_table,
                   run_id, for_trade_date, source_trade_date, prev_trade_date,
                   'stock' AS asset_kind,
                   stock_identity_key AS identity_key,
                   exchange, code, code AS display_code, name,
                   lane, direction, condition_key, condition_periods,
                   allowed_signal_types, is_hint_scope, scope_source,
                   source_condition_pool_id, reason, total_mv,
                   daily_snapshot_required, minute_required,
                   previous_day_minute_required, previous_day_minute_date,
                   previous_day_minute_quality_required, minute_scope_reason,
                   market_data_consumer, source_version, scope_status,
                   raw_json, created_at
            FROM stock_minute_target_scope
            WHERE run_id = %s
            ORDER BY stock_identity_key, direction, condition_key, stock_minute_target_scope_id
        """
    elif asset_kind == "index":
        query = """
            SELECT index_minute_target_scope_id AS source_scope_id,
                   'index_minute_target_scope' AS source_scope_table,
                   run_id, for_trade_date, source_trade_date, prev_trade_date,
                   'index' AS asset_kind,
                   index_identity_key AS identity_key,
                   exchange, code, code AS display_code, name,
                   lane, direction, condition_key, condition_periods,
                   allowed_signal_types, is_hint_scope, scope_source,
                   source_condition_pool_id, reason, NULL::NUMERIC AS total_mv,
                   daily_snapshot_required, minute_required,
                   previous_day_minute_required, previous_day_minute_date,
                   previous_day_minute_quality_required, minute_scope_reason,
                   market_data_consumer, source_version, scope_status,
                   raw_json, created_at
            FROM index_minute_target_scope
            WHERE run_id = %s
            ORDER BY index_identity_key, direction, condition_key, index_minute_target_scope_id
        """
    elif asset_kind == "board":
        query = """
            SELECT board_minute_target_scope_id AS source_scope_id,
                   'board_minute_target_scope' AS source_scope_table,
                   run_id, for_trade_date, source_trade_date, prev_trade_date,
                   'board' AS asset_kind,
                   board_identity_key AS identity_key,
                   'TDX' AS exchange, board_code AS code, board_code AS display_code, board_name AS name,
                   lane, direction, condition_key, condition_periods,
                   allowed_signal_types, is_hint_scope, scope_source,
                   source_condition_pool_id, reason, NULL::NUMERIC AS total_mv,
                   daily_snapshot_required, minute_required,
                   previous_day_minute_required, previous_day_minute_date,
                   previous_day_minute_quality_required, minute_scope_reason,
                   market_data_consumer, source_version, scope_status,
                   raw_json, created_at
            FROM board_minute_target_scope
            WHERE run_id = %s
            ORDER BY board_identity_key, direction, condition_key, board_minute_target_scope_id
        """
    else:
        raise ValueError(f"unsupported asset_kind: {asset_kind}")

    cur.execute(query, (condition_run_id,))
    return [normalize_scope_row(row) for row in cur.fetchall()]


def normalize_scope_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["source_scope_id"] = int(output["source_scope_id"])
    output["source_condition_pool_id"] = (
        int(output["source_condition_pool_id"])
        if output.get("source_condition_pool_id") not in (None, "")
        else None
    )
    output["condition_periods"] = normalize_text_array(output.get("condition_periods"))
    output["allowed_signal_types"] = normalize_text_array(output.get("allowed_signal_types"))
    return output


def normalize_text_array(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item) for item in value]


def build_market_data_subscription_plan(
    *,
    active_run: Mapping[str, Any],
    scope_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    preflight_quality_items: Sequence[Mapping[str, Any]] | None = None,
    table_status: Mapping[str, bool] | None = None,
    trade_calendar_detail: Mapping[str, Any] | None = None,
    include_rows: bool = True,
) -> dict[str, Any]:
    active_run = normalize_mapping(active_run)
    market_data_run_id = f"market_data_subscription_{active_run['for_trade_date']}_{active_run['run_id']}_dry_run"
    scope_rows = flatten_scope_rows(scope_rows_by_asset)
    scope_quality = build_scope_contract_quality_items(active_run=active_run, scope_rows_by_asset=scope_rows_by_asset)
    candidates = build_subscription_candidates(market_data_run_id=market_data_run_id, active_run=active_run, scope_rows=scope_rows)
    subscriptions, dedup_conflicts = deduplicate_subscription_candidates(
        market_data_run_id=market_data_run_id,
        active_run=active_run,
        candidates=candidates,
    )
    pull_plan_rows = build_pull_plan_rows(
        market_data_run_id=market_data_run_id,
        active_run=active_run,
        subscriptions=subscriptions,
    )
    quality_items = list(preflight_quality_items or [])
    effective_table_status = table_status if table_status is not None else {table: True for table in SCOPE_TABLES.values()}
    quality_items.extend(build_table_status_quality(effective_table_status))
    quality_items.extend(build_trade_calendar_quality_items(trade_calendar_detail, active_run=active_run))
    quality_items.extend(scope_quality)
    quality_items.extend(
        build_subscription_quality_items(
            source_scope_row_count=len(scope_rows),
            candidates=candidates,
            subscriptions=subscriptions,
            dedup_conflicts=dedup_conflicts,
        )
    )
    severity_counts = count_quality_severities(quality_items)
    source_scope_row_count_by_asset = {
        asset_kind: len(scope_rows_by_asset.get(asset_kind, []))
        for asset_kind in ASSET_KINDS
    }
    required_kind_counts = dict(sorted(Counter(row["required_data_kind"] for row in subscriptions).items()))
    candidate_required_kind_counts = dict(sorted(Counter(row["required_data_kind"] for row in candidates).items()))
    subscription_object_keys = {
        (row["asset_kind"], row["identity_key"])
        for row in subscriptions
    }
    previous_day_summary = previous_day_minute_summary(scope_rows)
    dedup_ratio = ratio(len(subscriptions), len(candidates))
    report = {
        "stage": "N3-0",
        "plan_mode": "market_data_subscription_dry_run",
        "mode": "dry_run",
        "market_data_run_id": market_data_run_id,
        "source_condition_run_id": active_run.get("run_id"),
        "source_trade_date": active_run.get("source_trade_date"),
        "for_trade_date": active_run.get("for_trade_date"),
        "prev_trade_date": active_run.get("prev_trade_date"),
        "active_condition_run": summarize_active_run(active_run),
        "source_scope_row_count": len(scope_rows),
        "source_scope_row_count_by_asset_kind": source_scope_row_count_by_asset,
        "source_scope_object_count_by_asset_kind": object_count_by_asset_kind_from_rows(scope_rows),
        "candidate_row_count": len(candidates),
        "subscription_candidate_count": len(candidates),
        "candidate_row_count_by_required_data_kind": candidate_required_kind_counts,
        "subscription_row_count": len(subscriptions),
        "dedup_subscription_count": len(subscriptions),
        "subscription_object_count": len(subscription_object_keys),
        "object_count_by_asset_kind": object_count_by_asset_kind_from_rows(subscriptions),
        "subscription_object_count_by_required_data_kind": object_count_by_required_kind(subscriptions),
        "required_data_kind_counts": required_kind_counts,
        "previous_day_minute_required_count": previous_day_summary["scope_row_count"],
        "previous_day_minute_required_count_by_asset_kind": previous_day_summary["scope_row_count_by_asset_kind"],
        "previous_day_minute_required_object_count": previous_day_summary["object_count"],
        "previous_day_minute_required_object_count_by_asset_kind": previous_day_summary["object_count_by_asset_kind"],
        "previous_day_minute_date_counts": previous_day_summary["date_counts"],
        "previous_day_minute_date_counts_by_asset_kind": previous_day_summary["date_counts_by_asset_kind"],
        "trade_calendar_detail_check": normalize_mapping(trade_calendar_detail) if trade_calendar_detail is not None else None,
        "dedup_ratio": dedup_ratio,
        "dedup_reduction_ratio": ratio(len(candidates) - len(subscriptions), len(candidates)),
        "market_data_pull_plan_row_count": len(pull_plan_rows),
        "source_scope_ids_sample": source_scope_ids_sample(scope_rows),
        "source_condition_pool_ids_sample": source_condition_pool_ids_sample(scope_rows),
        "market_data_subscription_candidate": rows_section(candidates, include_rows=include_rows),
        "market_data_subscription_dedup": rows_section(subscriptions, include_rows=include_rows),
        "market_data_pull_plan": rows_section(pull_plan_rows, include_rows=include_rows),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blocked": severity_counts["P0"] > 0,
        "passed": severity_counts["P0"] == 0,
        "read_only_database_checks": True,
        "will_execute_sql": False,
        "migration_executed": False,
        "writes_performed": False,
        "market_data_pulled": False,
        "market_data_fact_written": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }
    return report


def flatten_scope_rows(scope_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset_kind in ASSET_KINDS:
        rows.extend(normalize_scope_row_like(row) for row in scope_rows_by_asset.get(asset_kind, []))
    return rows


def normalize_scope_row_like(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["condition_periods"] = normalize_text_array(output.get("condition_periods"))
    output["allowed_signal_types"] = normalize_text_array(output.get("allowed_signal_types"))
    return output


def build_subscription_candidates(
    *,
    market_data_run_id: str,
    active_run: Mapping[str, Any],
    scope_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for scope_row in scope_rows:
        for required_data_kind, data_trade_date in required_data_kinds_for_scope_row(scope_row):
            candidates.append(
                {
                    "candidate_ref": f"dry_run:candidate:{len(candidates) + 1}",
                    "run_id": market_data_run_id,
                    "source_condition_run_id": active_run.get("run_id"),
                    "for_trade_date": scope_row.get("for_trade_date"),
                    "source_trade_date": scope_row.get("source_trade_date"),
                    "prev_trade_date": scope_row.get("prev_trade_date"),
                    "asset_kind": scope_row.get("asset_kind"),
                    "identity_key": scope_row.get("identity_key"),
                    "exchange": scope_row.get("exchange"),
                    "code": scope_row.get("code"),
                    "display_code": scope_row.get("display_code") or scope_row.get("code"),
                    "name": scope_row.get("name"),
                    "required_data_kind": required_data_kind,
                    "data_trade_date": data_trade_date,
                    "source_scope_table": scope_row.get("source_scope_table"),
                    "source_scope_id": scope_row.get("source_scope_id"),
                    "source_scope_ref": f"{scope_row.get('source_scope_table')}:{scope_row.get('source_scope_id')}",
                    "source_condition_pool_id": scope_row.get("source_condition_pool_id"),
                    "direction": scope_row.get("direction"),
                    "condition_key": scope_row.get("condition_key"),
                    "allowed_signal_types": normalize_text_array(scope_row.get("allowed_signal_types")),
                    "source_scope_required_flags": {
                        "daily_snapshot_required": flag_is_true(scope_row.get("daily_snapshot_required")),
                        "minute_required": flag_is_true(scope_row.get("minute_required")),
                        "previous_day_minute_required": flag_is_true(scope_row.get("previous_day_minute_required")),
                        "previous_day_minute_date": scope_row.get("previous_day_minute_date"),
                    },
                    "candidate_status": "planned",
                    "selected_reason": "generated from minute_target_scope required flags",
                }
            )
    return candidates


def required_data_kinds_for_scope_row(scope_row: Mapping[str, Any]) -> list[tuple[str, str]]:
    kinds: list[tuple[str, str]] = []
    for_trade_date = str(scope_row.get("for_trade_date") or "")
    if flag_is_true(scope_row.get("daily_snapshot_required")):
        kinds.append(("realtime_daily_snapshot", for_trade_date))
    if flag_is_true(scope_row.get("minute_required")):
        kinds.append(("minute_bar_1m", for_trade_date))
    if flag_is_true(scope_row.get("previous_day_minute_required")):
        previous_day_minute_date = str(scope_row.get("previous_day_minute_date") or "")
        kinds.append(("previous_day_minute_bar_1m", previous_day_minute_date))
    return kinds


def flag_is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def deduplicate_subscription_candidates(
    *,
    market_data_run_id: str,
    active_run: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        key = (
            str(candidate.get("asset_kind")),
            str(candidate.get("identity_key")),
            str(candidate.get("required_data_kind")),
            str(candidate.get("for_trade_date")),
        )
        groups[key].append(candidate)

    subscriptions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for _, rows in sorted(groups.items()):
        data_trade_dates = unique_preserve_order(str(row.get("data_trade_date") or "") for row in rows)
        if len(data_trade_dates) != 1:
            conflicts.append(
                {
                    "dedup_key": {
                        "asset_kind": rows[0].get("asset_kind"),
                        "identity_key": rows[0].get("identity_key"),
                        "required_data_kind": rows[0].get("required_data_kind"),
                        "for_trade_date": rows[0].get("for_trade_date"),
                    },
                    "data_trade_dates": data_trade_dates,
                    "source_scope_refs": unique_preserve_order(row.get("source_scope_ref") for row in rows),
                }
            )
        first = rows[0]
        subscription = {
            "subscription_ref": f"dry_run:subscription:{len(subscriptions) + 1}",
            "run_id": market_data_run_id,
            "source_condition_run_id": active_run.get("run_id"),
            "for_trade_date": first.get("for_trade_date"),
            "source_trade_date": first.get("source_trade_date"),
            "prev_trade_date": first.get("prev_trade_date"),
            "asset_kind": first.get("asset_kind"),
            "identity_key": first.get("identity_key"),
            "exchange": first.get("exchange"),
            "code": first.get("code"),
            "display_code": first.get("display_code") or first.get("code"),
            "name": first.get("name"),
            "required_data_kind": first.get("required_data_kind"),
            "data_trade_date": data_trade_dates[0] if len(data_trade_dates) == 1 else None,
            "data_trade_dates": data_trade_dates,
            "source_scope_row_count": len(rows),
            "source_scope_tables": unique_preserve_order(row.get("source_scope_table") for row in rows),
            "source_scope_ids": unique_preserve_order(row.get("source_scope_id") for row in rows),
            "source_scope_refs": unique_preserve_order(row.get("source_scope_ref") for row in rows),
            "source_condition_pool_ids": unique_preserve_order(
                row.get("source_condition_pool_id") for row in rows if row.get("source_condition_pool_id") not in (None, "")
            ),
            "condition_keys": unique_preserve_order(row.get("condition_key") for row in rows),
            "directions": unique_preserve_order(row.get("direction") for row in rows),
            "allowed_signal_types": unique_preserve_order(
                signal_type
                for row in rows
                for signal_type in normalize_text_array(row.get("allowed_signal_types"))
            ),
            "priority": 100,
            "status": "planned",
            "selected_reason": "deduped by asset_kind + identity_key + required_data_kind + for_trade_date",
        }
        subscriptions.append(subscription)
    return subscriptions, conflicts


def build_pull_plan_rows(
    *,
    market_data_run_id: str,
    active_run: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for subscription in subscriptions:
        key = (
            str(subscription.get("asset_kind")),
            str(subscription.get("required_data_kind")),
            str(subscription.get("for_trade_date")),
            str(subscription.get("data_trade_date")),
        )
        groups[key].append(subscription)

    rows: list[dict[str, Any]] = []
    for (asset_kind, required_data_kind, for_trade_date, data_trade_date), group in sorted(groups.items()):
        identity_keys = unique_preserve_order(row.get("identity_key") for row in group)
        rows.append(
            {
                "pull_plan_ref": f"dry_run:pull_plan:{len(rows) + 1}",
                "run_id": market_data_run_id,
                "source_condition_run_id": active_run.get("run_id"),
                "for_trade_date": for_trade_date,
                "source_trade_date": active_run.get("source_trade_date"),
                "prev_trade_date": active_run.get("prev_trade_date"),
                "asset_kind": asset_kind,
                "required_data_kind": required_data_kind,
                "data_trade_date": data_trade_date,
                "adapter_name": ADAPTER_NAMES[asset_kind],
                "subscription_count": len(group),
                "object_count": len(identity_keys),
                "subscription_refs_sample": [row.get("subscription_ref") for row in group[:20]],
                "identity_keys_sample": identity_keys[:20],
                "plan_status": "planned",
                "execute_allowed": False,
                "selected_reason": "N3-0 dry-run only; no market data pull will be executed",
            }
        )
    return rows


def unique_preserve_order(values: Iterable[Any]) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        if key not in seen:
            output.append(value)
            seen.add(key)
    return output


def build_table_status_quality(table_status: Mapping[str, bool]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for table_name in SCOPE_TABLES.values():
        exists = bool(table_status.get(table_name))
        items.append(
            quality_item(
                "P0",
                "passed" if exists else "failed",
                f"{table_name}_exists",
                f"{table_name} must exist before N3-0 subscription planning",
                expected="exists",
                actual="exists" if exists else "missing",
            )
        )
    return items


def build_trade_calendar_quality_items(
    trade_calendar_detail: Mapping[str, Any] | None,
    *,
    active_run: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if trade_calendar_detail is None:
        return []

    table_exists = bool(trade_calendar_detail.get("table_exists"))
    row_exists = bool(trade_calendar_detail.get("row_exists"))
    row = trade_calendar_detail.get("row") or {}
    prev_trade_date = str(row.get("prev_trade_date") or "")
    is_open = row.get("is_open")
    expected_prev_trade_date = str(active_run.get("prev_trade_date") or "")
    items = [
        quality_item(
            "P1",
            "passed" if table_exists else "warning",
            "for_trade_calendar_table_exists",
            "N3-0 checks for_trade_date calendar detail but does not repair N1 calendar data",
            expected="common_trade_calendar exists",
            actual="exists" if table_exists else "missing",
        ),
        quality_item(
            "P1",
            "passed" if row_exists else "warning",
            "for_trade_calendar_row_exists",
            "for_trade_date calendar detail should exist for N3 reporting",
            expected=str(active_run.get("for_trade_date")),
            actual="exists" if row_exists else "missing",
        ),
    ]
    if row_exists:
        items.extend(
            [
                quality_item(
                    "P0",
                    "passed" if prev_trade_date in {"", expected_prev_trade_date} else "failed",
                    "for_trade_calendar_prev_trade_date_matches_active_run",
                    "calendar prev_trade_date must not contradict the active condition run",
                    expected=expected_prev_trade_date,
                    actual=prev_trade_date or "missing",
                ),
                quality_item(
                    "P0",
                    "passed" if is_open in (True, "true", "t", "1", 1) else "failed",
                    "for_trade_calendar_is_open",
                    "active run for_trade_date should be an open trading day when calendar detail exists",
                    expected="is_open=true",
                    actual=str(is_open),
                ),
            ]
        )
    else:
        items.extend(
            [
                quality_item(
                    "P0",
                    "skipped",
                    "for_trade_calendar_prev_trade_date_matches_active_run",
                    "calendar prev_trade_date comparison skipped because calendar detail is missing",
                    expected=expected_prev_trade_date,
                    actual="calendar row missing",
                ),
                quality_item(
                    "P0",
                    "skipped",
                    "for_trade_calendar_is_open",
                    "calendar open-day comparison skipped because calendar detail is missing",
                    expected="is_open=true",
                    actual="calendar row missing",
                ),
            ]
        )
    return items


def build_scope_contract_quality_items(
    *,
    active_run: Mapping[str, Any],
    scope_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    all_rows = flatten_scope_rows(scope_rows_by_asset)
    source_scope_count = len(all_rows)
    items.append(
        quality_item(
            "P0",
            "passed" if source_scope_count > 0 else "failed",
            "source_scope_rows_available",
            "active condition run must have minute_target_scope rows",
            expected=">0",
            actual=str(source_scope_count),
        )
    )
    for asset_kind in ASSET_KINDS:
        rows = [normalize_scope_row_like(row) for row in scope_rows_by_asset.get(asset_kind, [])]
        wrong_run_ids = sorted({str(row.get("run_id")) for row in rows if row.get("run_id") != active_run.get("run_id")})
        non_condition_pool = sorted({str(row.get("scope_source")) for row in rows if row.get("scope_source") != "condition_pool"})
        missing_pool_links = [row.get("source_scope_id") for row in rows if row.get("source_condition_pool_id") in (None, "")]
        items.extend(
            [
                quality_item(
                    "P0",
                    "passed" if not wrong_run_ids else "failed",
                    f"{asset_kind}_scope_run_id_match",
                    f"{asset_kind} scope rows must belong to the active condition run",
                    expected=str(active_run.get("run_id")),
                    actual="matched" if not wrong_run_ids else ",".join(wrong_run_ids[:10]),
                ),
                quality_item(
                    "P0",
                    "passed" if not non_condition_pool else "failed",
                    f"{asset_kind}_scope_source_condition_pool",
                    f"{asset_kind} scope rows must come from condition_pool",
                    expected="condition_pool",
                    actual="condition_pool" if not non_condition_pool else ",".join(non_condition_pool[:10]),
                ),
                quality_item(
                    "P0",
                    "passed" if not missing_pool_links else "failed",
                    f"{asset_kind}_scope_condition_pool_link_present",
                    f"{asset_kind} scope rows must preserve source_condition_pool_id",
                    expected="source_condition_pool_id present",
                    actual="present" if not missing_pool_links else ",".join(str(item) for item in missing_pool_links[:20]),
                ),
            ]
        )

    previous_day_mismatches = [
        row
        for row in all_rows
        if flag_is_true(row.get("previous_day_minute_required"))
        and row.get("previous_day_minute_date") != active_run.get("prev_trade_date")
    ]
    previous_day_missing = [
        row
        for row in all_rows
        if flag_is_true(row.get("previous_day_minute_required"))
        and not row.get("previous_day_minute_date")
    ]
    rows_without_required_kind = [
        row
        for row in all_rows
        if not required_data_kinds_for_scope_row(row)
    ]
    invalid_signal_types = sorted(
        {
            signal_type
            for row in all_rows
            for signal_type in normalize_text_array(row.get("allowed_signal_types"))
            if signal_type not in STANDARD_SIGNAL_TYPES
        }
    )
    items.extend(
        [
            quality_item(
                "P0",
                "passed" if not previous_day_missing else "failed",
                "previous_day_minute_date_present",
                "previous_day_minute_required=true must include previous_day_minute_date",
                expected="previous_day_minute_date present",
                actual="present" if not previous_day_missing else sample_scope_refs(previous_day_missing),
            ),
            quality_item(
                "P0",
                "passed" if not previous_day_mismatches else "failed",
                "previous_day_minute_date_equals_prev_trade_date",
                "previous_day_minute_date must equal active run prev_trade_date",
                expected=str(active_run.get("prev_trade_date")),
                actual="matched" if not previous_day_mismatches else sample_scope_refs(previous_day_mismatches),
            ),
            quality_item(
                "P0",
                "passed" if not rows_without_required_kind else "failed",
                "required_data_kind_generated_for_each_scope",
                "each scope row must generate at least one required_data_kind",
                expected="daily/minute/previous-day minute flag present",
                actual="generated" if not rows_without_required_kind else sample_scope_refs(rows_without_required_kind),
            ),
            quality_item(
                "P0",
                "passed" if not invalid_signal_types else "failed",
                "scope_allowed_signal_types_whitelist",
                "allowed_signal_types must stay in the v3 standard signal whitelist",
                expected=",".join(STANDARD_SIGNAL_TYPES),
                actual="whitelist_only" if not invalid_signal_types else ",".join(invalid_signal_types),
            ),
        ]
    )
    return items


def build_subscription_quality_items(
    *,
    source_scope_row_count: int,
    candidates: Sequence[Mapping[str, Any]],
    subscriptions: Sequence[Mapping[str, Any]],
    dedup_conflicts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    missing_candidate_trace = [
        row.get("candidate_ref")
        for row in candidates
        if row.get("source_scope_id") in (None, "")
        or row.get("source_condition_pool_id") in (None, "")
        or not row.get("condition_key")
        or not row.get("direction")
    ]
    missing_subscription_trace = [
        row.get("subscription_ref")
        for row in subscriptions
        if not row.get("source_scope_ids")
        or not row.get("source_condition_pool_ids")
        or not row.get("condition_keys")
        or not row.get("directions")
        or not row.get("allowed_signal_types")
    ]
    items = [
        quality_item(
            "P0",
            "passed" if source_scope_row_count == 0 or len(candidates) >= source_scope_row_count else "failed",
            "candidate_rows_generated_from_scope",
            "scope rows with required flags must expand into subscription candidates",
            expected="candidate_row_count >= source_scope_row_count",
            actual=str(len(candidates)),
        ),
        quality_item(
            "P0",
            "passed" if not missing_candidate_trace else "failed",
            "candidate_trace_fields_present",
            "subscription candidates must preserve source scope, condition pool, condition key, and direction",
            expected="trace fields present",
            actual="present" if not missing_candidate_trace else ",".join(str(item) for item in missing_candidate_trace[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not missing_subscription_trace else "failed",
            "subscription_trace_fields_present",
            "deduped subscriptions must preserve source_scope_ids/source_condition_pool_ids/condition_keys/directions/allowed_signal_types",
            expected="trace arrays present",
            actual="present" if not missing_subscription_trace else ",".join(str(item) for item in missing_subscription_trace[:20]),
        ),
        quality_item(
            "P0",
            "passed" if not dedup_conflicts else "failed",
            "dedup_key_data_trade_date_consistent",
            "one dedup key must not produce conflicting data_trade_date values",
            expected="single data_trade_date per dedup key",
            actual="consistent" if not dedup_conflicts else str(dedup_conflicts[:5]),
        ),
        quality_item(
            "P0",
            "passed" if len(subscriptions) <= len(candidates) else "failed",
            "subscription_dedup_not_expanding_candidates",
            "deduped subscription row count must be less than or equal to candidate row count",
            expected="subscription_row_count <= candidate_row_count",
            actual=f"{len(subscriptions)} <= {len(candidates)}",
        ),
        quality_item("P0", "passed", "no_external_market_data_call", "N3-0 dry-run does not call market data adapters"),
        quality_item("P0", "passed", "no_market_data_fact_write", "N3-0 dry-run does not write realtime/minute market data fact tables"),
        quality_item("P0", "passed", "no_downstream_layer_touch", "N3-0 dry-run does not enter trigger/action/mobile/voice/sim"),
        quality_item("P0", "passed", "no_worker_started", "N3-0 dry-run does not start workers or long-running services"),
    ]
    return items


def sample_scope_refs(rows: Sequence[Mapping[str, Any]], limit: int = 20) -> str:
    refs = [
        f"{row.get('source_scope_table')}:{row.get('source_scope_id')}"
        for row in rows[:limit]
    ]
    return ",".join(refs)


def rows_section(rows: Sequence[Mapping[str, Any]], *, include_rows: bool) -> dict[str, Any]:
    section = {
        "row_count": len(rows),
        "sample_rows": [normalize_mapping(row) for row in rows[:10]],
        "rows_included": include_rows,
    }
    if include_rows:
        section["rows"] = [normalize_mapping(row) for row in rows]
    return section


def object_count_by_required_kind(subscriptions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    grouped: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in subscriptions:
        grouped[str(row.get("required_data_kind"))].add((str(row.get("asset_kind")), str(row.get("identity_key"))))
    return {key: len(value) for key, value in sorted(grouped.items())}


def object_count_by_asset_kind_from_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    grouped: dict[str, set[str]] = {asset_kind: set() for asset_kind in ASSET_KINDS}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        identity_key = str(row.get("identity_key") or "")
        if asset_kind in grouped and identity_key:
            grouped[asset_kind].add(identity_key)
    return {asset_kind: len(grouped[asset_kind]) for asset_kind in ASSET_KINDS}


def previous_day_minute_summary(scope_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    previous_rows = [
        row
        for row in scope_rows
        if flag_is_true(row.get("previous_day_minute_required"))
    ]
    date_counts = Counter(str(row.get("previous_day_minute_date") or "<missing>") for row in previous_rows)
    date_counts_by_asset: dict[str, dict[str, int]] = {}
    row_counts_by_asset: dict[str, int] = {}
    object_counts_by_asset: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        asset_rows = [row for row in previous_rows if row.get("asset_kind") == asset_kind]
        row_counts_by_asset[asset_kind] = len(asset_rows)
        object_counts_by_asset[asset_kind] = len({str(row.get("identity_key")) for row in asset_rows if row.get("identity_key")})
        date_counts_by_asset[asset_kind] = dict(sorted(Counter(str(row.get("previous_day_minute_date") or "<missing>") for row in asset_rows).items()))
    return {
        "scope_row_count": len(previous_rows),
        "scope_row_count_by_asset_kind": row_counts_by_asset,
        "object_count": len({(row.get("asset_kind"), row.get("identity_key")) for row in previous_rows}),
        "object_count_by_asset_kind": object_counts_by_asset,
        "date_counts": dict(sorted(date_counts.items())),
        "date_counts_by_asset_kind": date_counts_by_asset,
    }


def source_scope_ids_sample(scope_rows: Sequence[Mapping[str, Any]], limit: int = 20) -> dict[str, list[Any]]:
    sample: dict[str, list[Any]] = {}
    for asset_kind in ASSET_KINDS:
        sample[asset_kind] = [
            row.get("source_scope_id")
            for row in scope_rows
            if row.get("asset_kind") == asset_kind
        ][:limit]
    return sample


def source_condition_pool_ids_sample(scope_rows: Sequence[Mapping[str, Any]], limit: int = 20) -> dict[str, list[Any]]:
    sample: dict[str, list[Any]] = {}
    for asset_kind in ASSET_KINDS:
        sample[asset_kind] = unique_preserve_order(
            row.get("source_condition_pool_id")
            for row in scope_rows
            if row.get("asset_kind") == asset_kind
        )[:limit]
    return sample


def summarize_active_run(active_run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": active_run.get("run_id"),
        "status": active_run.get("status"),
        "source_trade_date": active_run.get("source_trade_date"),
        "for_trade_date": active_run.get("for_trade_date"),
        "prev_trade_date": active_run.get("prev_trade_date"),
        "p0_count": active_run.get("p0_count"),
        "p1_count": active_run.get("p1_count"),
        "p2_count": active_run.get("p2_count"),
        "source_versions": active_run.get("source_versions") or {},
    }


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def build_blocked_report(
    quality_items: Sequence[Mapping[str, Any]],
    active_runs: Sequence[Mapping[str, Any]],
    *,
    include_rows: bool,
) -> dict[str, Any]:
    severity_counts = count_quality_severities(list(quality_items))
    active_run = normalize_mapping(active_runs[0]) if len(active_runs) == 1 else {}
    return {
        "stage": "N3-0",
        "plan_mode": "market_data_subscription_dry_run",
        "mode": "dry_run",
        "market_data_run_id": None,
        "source_condition_run_id": active_run.get("run_id"),
        "source_trade_date": active_run.get("source_trade_date"),
        "for_trade_date": active_run.get("for_trade_date"),
        "prev_trade_date": active_run.get("prev_trade_date"),
        "active_condition_run_candidates": [summarize_active_run(row) for row in active_runs],
        "source_scope_row_count": 0,
        "candidate_row_count": 0,
        "subscription_row_count": 0,
        "subscription_object_count": 0,
        "required_data_kind_counts": {},
        "dedup_ratio": 0.0,
        "market_data_subscription_candidate": rows_section([], include_rows=include_rows),
        "market_data_subscription_dedup": rows_section([], include_rows=include_rows),
        "market_data_pull_plan": rows_section([], include_rows=include_rows),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": list(quality_items),
        },
        "blocked": True,
        "passed": False,
        "read_only_database_checks": True,
        "will_execute_sql": False,
        "migration_executed": False,
        "writes_performed": False,
        "market_data_pulled": False,
        "market_data_fact_written": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }
