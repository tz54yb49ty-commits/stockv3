"""N3-C0 today 1 minute bar dry-run planner.

This module plans a bounded, run-once N3-C1 catch-up of today's closed 1m
facts. It never calls market-data adapters, writes minute facts, writes outbox
events, consumes events, or starts workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
import json
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.preload_plan import (
    MINUTE_FACT_TABLES,
    build_persisted_subscription_report,
    normalize_db_row,
)
from ashare_v3.market.subscription_plan import ADAPTER_NAMES, ASSET_KINDS, rows_section


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_N3_C0_MARKDOWN_REPORT_PATH = "docs/N3_C0_TODAY_MINUTE_BAR_1M_DRY_RUN_REPORT.md"
DEFAULT_N3_C0_JSON_REPORT_PATH = "docs/N3_C0_today_minute_bar_1m_dry_run.json"
REQUIRED_DATA_KIND = "minute_bar_1m"

MORNING_FIRST_BAR = time(9, 30)
MORNING_LAST_BAR = time(11, 29)
AFTERNOON_FIRST_BAR = time(13, 0)
AFTERNOON_LAST_BAR = time(14, 59)
TODAY_MINUTE_IGNORED_SOURCE_P0_GATE_CODES = {
    "n3_6_previous_day_subscription_rows_present",
    "n3_6_previous_day_pull_plan_rows_present",
}


def build_today_minute_bar_plan_dry_run(
    *,
    dsn: str,
    market_data_run_id: str,
    for_trade_date: str | None = None,
    as_of: datetime | None = None,
    include_rows: bool = True,
) -> dict[str, Any]:
    """Build an N3-C0 dry-run plan from persisted N3 subscription rows."""

    subscription_report = build_today_minute_subscription_report(
        dsn=dsn,
        market_data_run_id=market_data_run_id,
    )
    source_quality = today_minute_source_quality_summary(subscription_report)
    resolved_trade_date = for_trade_date or str(subscription_report.get("for_trade_date") or "")
    latest_closed_minute = calculate_latest_closed_minute(
        as_of=as_of or datetime.now(tz=ASIA_SHANGHAI),
        trade_date=resolved_trade_date,
    )
    expected_bar_times = build_expected_bar_times(
        trade_date=resolved_trade_date,
        latest_closed_minute=latest_closed_minute,
    )
    expected_bar_count_per_object = len(expected_bar_times)
    today_minute_run_id = build_planned_today_minute_run_id(
        for_trade_date=resolved_trade_date,
        latest_closed_minute=latest_closed_minute,
        source_run_id=market_data_run_id,
    )
    subscriptions = today_minute_subscriptions(subscription_report)
    pull_batches = build_today_minute_pull_batches(
        subscription_report=subscription_report,
        subscriptions=subscriptions,
        persisted_pull_plans=(subscription_report.get("today_minute_pull_plan") or {}).get("rows") or [],
        latest_closed_minute=latest_closed_minute,
        expected_bar_count_per_object=expected_bar_count_per_object,
    )
    target_audit = fetch_today_minute_target_audit(
        dsn=dsn,
        today_minute_run_id=today_minute_run_id,
    )
    quality_items = build_today_minute_quality_items(
        subscription_report=subscription_report,
        subscriptions=subscriptions,
        pull_batches=pull_batches,
        target_audit=target_audit,
        latest_closed_minute=latest_closed_minute,
        expected_bar_count_per_object=expected_bar_count_per_object,
        requested_for_trade_date=for_trade_date,
    )
    severity_counts = count_quality_severities(quality_items)
    object_counts_by_asset = asset_counts_by_asset(Counter(row["asset_kind"] for row in subscriptions))
    expected_rows_by_asset = {
        asset_kind: object_counts_by_asset[asset_kind] * expected_bar_count_per_object
        for asset_kind in ASSET_KINDS
    }
    estimated_write_tables_by_asset = {
        asset_kind: {"minute_fact_table": MINUTE_FACT_TABLES[asset_kind]}
        for asset_kind in ASSET_KINDS
    }
    return {
        "stage": "N3-C0",
        "layer_role": "N3_market_data",
        "plan_mode": "today_minute_bar_1m_run_once_dry_run",
        "mode": "dry_run",
        "source_market_data_run_id": market_data_run_id,
        "today_minute_run_id": today_minute_run_id,
        "source_condition_run_id": subscription_report.get("source_condition_run_id"),
        "source_trade_date": subscription_report.get("source_trade_date"),
        "for_trade_date": resolved_trade_date,
        "prev_trade_date": subscription_report.get("prev_trade_date"),
        "required_data_kind": REQUIRED_DATA_KIND,
        "latest_closed_minute": latest_closed_minute.isoformat() if latest_closed_minute else None,
        "latest_closed_minute_hhmm": latest_closed_minute.strftime("%H%M") if latest_closed_minute else None,
        "expected_bar_count_per_object": expected_bar_count_per_object,
        "expected_first_bar_time": expected_bar_times[0].isoformat() if expected_bar_times else None,
        "expected_last_bar_time": expected_bar_times[-1].isoformat() if expected_bar_times else None,
        "session_policy": {
            "timezone": "Asia/Shanghai",
            "minute_label_policy": "HH:MM label is closed only after HH:MM+1",
            "sessions": ["09:30-11:29", "13:00-14:59"],
            "lunch_window_skipped": True,
            "session_close_boundaries_not_physical_bars": ["11:30", "15:00"],
            "previous_trading_minute_of_13_00": "11:29",
            "next_trading_minute_of_11_29": "13:00",
        },
        "today_minute_subscription_count": len(subscriptions),
        "today_minute_object_count": len({(row["asset_kind"], row["identity_key"]) for row in subscriptions}),
        "today_minute_object_count_by_asset_kind": object_counts_by_asset,
        "expected_minute_rows": sum(expected_rows_by_asset.values()),
        "expected_minute_rows_by_asset_kind": expected_rows_by_asset,
        "source_subscription_plan": {
            "market_data_run_id": subscription_report.get("market_data_run_id"),
            "source_scope_row_count": subscription_report.get("source_scope_row_count"),
            "candidate_row_count": subscription_report.get("candidate_row_count"),
            "subscription_row_count": subscription_report.get("subscription_row_count"),
            "subscription_object_count": subscription_report.get("subscription_object_count"),
            "required_data_kind_counts": subscription_report.get("required_data_kind_counts"),
            "dedup_ratio": subscription_report.get("dedup_ratio"),
            "p0_count": source_quality["p0_count"],
            "p1_count": source_quality["p1_count"],
            "p2_count": source_quality["p2_count"],
            "ignored_source_p0_gate_codes": source_quality["ignored_p0_gate_codes"],
            "passed": source_quality["p0_count"] == 0,
        },
        "source_adapter_plan": rows_section(pull_batches, include_rows=include_rows),
        "estimated_write_tables": sorted(
            table_name
            for tables in estimated_write_tables_by_asset.values()
            for table_name in tables.values()
        ),
        "estimated_write_tables_by_asset_kind": estimated_write_tables_by_asset,
        "target_audit": target_audit,
        "execute_contract": build_today_minute_execute_contract(
            today_minute_run_id=today_minute_run_id,
            source_run_id=market_data_run_id,
        ),
        "rollback_contract": {
            "rollback_sql": build_today_minute_rollback_sql(today_minute_run_id),
            "requires_outbox_precheck": False,
            "reason": "N3-C1 fact catch-up writes_outbox=false by contract",
        },
        "event_outbox_write_planned_in_dry_run": False,
        "event_outbox_write_required_in_execute": False,
        "generated_event_types_for_execute": [],
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blocked": severity_counts["P0"] > 0,
        "execute_ready_for_preflight": severity_counts["P0"] == 0,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "minute_bar_written": False,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def build_today_minute_subscription_report(*, dsn: str, market_data_run_id: str) -> dict[str, Any]:
    report = build_persisted_subscription_report(dsn=dsn, market_data_run_id=market_data_run_id)
    if report.get("blocked"):
        return report
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        pull_plan_rows = fetch_today_minute_pull_plan_rows(cur, market_data_run_id)
    report["today_minute_pull_plan"] = rows_section(pull_plan_rows, include_rows=True)
    return report


def fetch_today_minute_pull_plan_rows(cur: psycopg.Cursor[dict[str, Any]], market_data_run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT pull_plan_id, run_id, source_condition_run_id, for_trade_date,
               source_trade_date, prev_trade_date, asset_kind, required_data_kind,
               data_trade_date, adapter_name, subscription_count, object_count,
               subscription_ids_sample, subscription_refs_sample, identity_keys_sample,
               plan_status, execute_allowed, selected_reason, raw_json
        FROM common_market_data_pull_plan
        WHERE run_id = %s
          AND required_data_kind = 'minute_bar_1m'
        ORDER BY asset_kind, data_trade_date, pull_plan_id
        """,
        (market_data_run_id,),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def today_minute_subscriptions(subscription_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = (subscription_report.get("market_data_subscription_dedup") or {}).get("rows") or []
    return [dict(row) for row in rows if row.get("required_data_kind") == REQUIRED_DATA_KIND]


def today_minute_source_quality_summary(subscription_report: Mapping[str, Any]) -> dict[str, Any]:
    """Return source quality relevant to C0 today-minute planning."""

    quality = subscription_report.get("quality") if isinstance(subscription_report.get("quality"), Mapping) else {}
    raw_items = quality.get("items") if isinstance(quality.get("items"), Sequence) else []
    blocking_p0: list[str] = []
    ignored_p0: list[str] = []
    p1_count = 0
    p2_count = 0
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        severity = str(item.get("severity") or "")
        status = str(item.get("status") or "")
        gate_code = str(item.get("gate_code") or "")
        if severity == "P0" and status != "passed":
            if gate_code in TODAY_MINUTE_IGNORED_SOURCE_P0_GATE_CODES:
                ignored_p0.append(gate_code)
            else:
                blocking_p0.append(gate_code)
        elif severity == "P1" and status != "passed":
            p1_count += 1
        elif severity == "P2" and status != "passed":
            p2_count += 1
    p0_count = len(blocking_p0) if raw_items else int(quality.get("p0_count") or 0)
    return {
        "p0_count": p0_count,
        "p1_count": p1_count,
        "p2_count": p2_count,
        "blocking_p0_gate_codes": blocking_p0,
        "ignored_p0_gate_codes": ignored_p0,
    }


def build_today_minute_pull_batches(
    *,
    subscription_report: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    persisted_pull_plans: Sequence[Mapping[str, Any]],
    latest_closed_minute: datetime | None,
    expected_bar_count_per_object: int,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for subscription in subscriptions:
        key = (str(subscription.get("asset_kind")), str(subscription.get("data_trade_date")))
        groups.setdefault(key, []).append(subscription)
    pull_plan_by_key = {
        (str(row.get("asset_kind")), str(row.get("data_trade_date"))): row
        for row in persisted_pull_plans
    }
    rows: list[dict[str, Any]] = []
    for (asset_kind, trade_date), group in sorted(groups.items()):
        identity_keys = [row.get("identity_key") for row in group]
        persisted = pull_plan_by_key.get((asset_kind, trade_date), {})
        rows.append(
            {
                "today_minute_pull_plan_ref": f"dry_run:today_minute_pull:{len(rows) + 1}",
                "source_pull_plan_id": persisted.get("pull_plan_id"),
                "market_data_run_id": subscription_report.get("market_data_run_id"),
                "source_condition_run_id": subscription_report.get("source_condition_run_id"),
                "for_trade_date": subscription_report.get("for_trade_date"),
                "trade_date": trade_date,
                "asset_kind": asset_kind,
                "required_data_kind": REQUIRED_DATA_KIND,
                "adapter_name": persisted.get("adapter_name") or ADAPTER_NAMES[asset_kind],
                "adapter_call": adapter_call_for_asset(asset_kind),
                "source_path": source_path_for_asset(asset_kind),
                "subscription_count": len(group),
                "object_count": len(set(identity_keys)),
                "latest_closed_minute": latest_closed_minute.isoformat() if latest_closed_minute else None,
                "expected_bar_count_per_object": expected_bar_count_per_object,
                "expected_minute_rows": len(set(identity_keys)) * expected_bar_count_per_object,
                "target_minute_table": MINUTE_FACT_TABLES[asset_kind],
                "estimated_write_tables": [MINUTE_FACT_TABLES[asset_kind]],
                "execute_contract": {
                    "write_minute_fact": True,
                    "is_previous_day_preload": False,
                    "writes_outbox": False,
                    "generated_event_types": [],
                    "adapter_call_planned_in_dry_run": False,
                    "dry_run_only": True,
                },
                "persisted_pull_plan": {
                    "pull_plan_id": persisted.get("pull_plan_id"),
                    "subscription_count": persisted.get("subscription_count"),
                    "object_count": persisted.get("object_count"),
                    "execute_allowed": persisted.get("execute_allowed"),
                    "plan_status": persisted.get("plan_status"),
                },
                "identity_keys_sample": identity_keys[:20],
                "execute_allowed": False,
                "selected_reason": "N3-C0 dry-run only; today minute adapter calls and writes require N3-C1 confirmation",
            }
        )
    return rows


def adapter_call_for_asset(asset_kind: str) -> str:
    if asset_kind == "stock":
        return "bars"
    if asset_kind in {"index", "board"}:
        return "index_bars"
    raise ValueError(f"unsupported asset_kind: {asset_kind}")


def source_path_for_asset(asset_kind: str) -> str:
    if asset_kind == "stock":
        return "std.bars"
    if asset_kind in {"index", "board"}:
        return "std.index_bars"
    raise ValueError(f"unsupported asset_kind: {asset_kind}")


def calculate_latest_closed_minute(*, as_of: datetime, trade_date: str) -> datetime | None:
    local_as_of = ensure_shanghai_timezone(as_of)
    trade_day = parse_trade_date(trade_date)
    if local_as_of.date() < trade_day:
        return None
    if local_as_of.date() > trade_day:
        return datetime.combine(trade_day, AFTERNOON_LAST_BAR, tzinfo=ASIA_SHANGHAI)
    candidate = local_as_of.replace(second=0, microsecond=0)
    candidate = candidate.replace(minute=candidate.minute)  # keep a plain datetime for subtraction below
    candidate = candidate - minute_delta()
    bar_times = all_session_bar_times(trade_date)
    eligible = [bar_time for bar_time in bar_times if bar_time <= candidate]
    return eligible[-1] if eligible else None


def minute_delta() -> Any:
    from datetime import timedelta

    return timedelta(minutes=1)


def build_expected_bar_times(*, trade_date: str, latest_closed_minute: datetime | None) -> list[datetime]:
    if latest_closed_minute is None:
        return []
    latest = ensure_shanghai_timezone(latest_closed_minute)
    return [bar_time for bar_time in all_session_bar_times(trade_date) if bar_time <= latest]


def all_session_bar_times(trade_date: str) -> list[datetime]:
    trade_day = parse_trade_date(trade_date)
    output: list[datetime] = []
    output.extend(iter_minute_labels(trade_day, MORNING_FIRST_BAR, MORNING_LAST_BAR))
    output.extend(iter_minute_labels(trade_day, AFTERNOON_FIRST_BAR, AFTERNOON_LAST_BAR))
    return output


def iter_minute_labels(trade_day: date, start: time, end: time) -> list[datetime]:
    from datetime import timedelta

    current = datetime.combine(trade_day, start, tzinfo=ASIA_SHANGHAI)
    final = datetime.combine(trade_day, end, tzinfo=ASIA_SHANGHAI)
    rows = []
    while current <= final:
        rows.append(current)
        current += timedelta(minutes=1)
    return rows


def build_planned_today_minute_run_id(
    *,
    for_trade_date: str,
    latest_closed_minute: datetime | None,
    source_run_id: str,
) -> str:
    hhmm = latest_closed_minute.strftime("%H%M") if latest_closed_minute else "none"
    return f"today_minute_bar_1m_{for_trade_date}_until_{hhmm}__{source_run_id}"


def build_today_minute_rollback_sql(today_minute_run_id: str) -> str:
    run_id = sql_literal(today_minute_run_id)
    return "\n".join(
        [
            "-- N3-C1 today minute_bar_1m rollback plan.",
            "-- Safe only before downstream MinuteBarClosed/C2 consumption; C1 itself writes no outbox.",
            "-- Hard-fail before DELETE when scoped event infra, C2/projection, N4/N5/N6, downstream, or worker refs exist.",
            "\\set ON_ERROR_STOP on",
            f"\\set today_minute_run_id {run_id}",
            "",
            "SELECT set_config('app.today_minute_run_id', :'today_minute_run_id', false);",
            "",
            "DO $$",
            "DECLARE",
            "  target_run_id TEXT := current_setting('app.today_minute_run_id');",
            "  outbox_refs BIGINT := 0;",
            "  inbox_refs BIGINT := 0;",
            "  checkpoint_refs BIGINT := 0;",
            "  closed_30m_refs BIGINT := 0;",
            "  realtime_projection_refs BIGINT := 0;",
            "  trigger_refs BIGINT := 0;",
            "  trigger_state_refs BIGINT := 0;",
            "  action_refs BIGINT := 0;",
            "  n6_refs BIGINT := 0;",
            "  downstream_touched_refs BIGINT := 0;",
            "  worker_started_refs BIGINT := 0;",
            "BEGIN",
            "  SELECT count(*) INTO outbox_refs",
            "  FROM common_event_outbox",
            "  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';",
            "",
            "  SELECT count(*) INTO inbox_refs",
            "  FROM common_event_inbox",
            "  WHERE source_run_id = target_run_id",
            "     OR payload_json::TEXT LIKE '%' || target_run_id || '%'",
            "     OR raw_json::TEXT LIKE '%' || target_run_id || '%';",
            "",
            "  SELECT count(*) INTO checkpoint_refs",
            "  FROM common_event_consumer_checkpoint",
            "  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%'",
            "     OR last_event_id LIKE '%' || target_run_id || '%';",
            "",
            "  IF to_regclass('stock_closed_30m_summary') IS NOT NULL THEN",
            "    EXECUTE 'SELECT count(*) FROM stock_closed_30m_summary WHERE to_jsonb(stock_closed_30m_summary)::TEXT LIKE $1'",
            "      INTO closed_30m_refs USING '%' || target_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('index_closed_30m_summary') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM index_closed_30m_summary WHERE to_jsonb(index_closed_30m_summary)::TEXT LIKE $2'",
            "      INTO closed_30m_refs USING closed_30m_refs, '%' || target_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('board_closed_30m_summary') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM board_closed_30m_summary WHERE to_jsonb(board_closed_30m_summary)::TEXT LIKE $2'",
            "      INTO closed_30m_refs USING closed_30m_refs, '%' || target_run_id || '%';",
            "  END IF;",
            "",
            "  IF to_regclass('stock_realtime_projection_metric') IS NOT NULL THEN",
            "    EXECUTE 'SELECT count(*) FROM stock_realtime_projection_metric WHERE to_jsonb(stock_realtime_projection_metric)::TEXT LIKE $1'",
            "      INTO realtime_projection_refs USING '%' || target_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('index_realtime_projection_metric') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM index_realtime_projection_metric WHERE to_jsonb(index_realtime_projection_metric)::TEXT LIKE $2'",
            "      INTO realtime_projection_refs USING realtime_projection_refs, '%' || target_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('board_realtime_projection_metric') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM board_realtime_projection_metric WHERE to_jsonb(board_realtime_projection_metric)::TEXT LIKE $2'",
            "      INTO realtime_projection_refs USING realtime_projection_refs, '%' || target_run_id || '%';",
            "  END IF;",
            "",
            "  SELECT count(*) INTO trigger_refs",
            "  FROM common_trigger_match",
            "  WHERE raw_json::TEXT LIKE '%' || target_run_id || '%'",
            "     OR source_event_id LIKE '%' || target_run_id || '%';",
            "",
            "  IF to_regclass('common_trigger_state') IS NOT NULL THEN",
            "    EXECUTE 'SELECT count(*) FROM common_trigger_state WHERE to_jsonb(common_trigger_state)::TEXT LIKE $1'",
            "      INTO trigger_state_refs USING '%' || target_run_id || '%';",
            "  END IF;",
            "",
            "  SELECT count(*) INTO action_refs",
            "  FROM common_action_event",
            "  WHERE source_market_data_run_id = target_run_id",
            "     OR source_market_trace::TEXT LIKE '%' || target_run_id || '%'",
            "     OR payload_json::TEXT LIKE '%' || target_run_id || '%'",
            "     OR trace_json::TEXT LIKE '%' || target_run_id || '%';",
            "",
            "  IF to_regclass('user_projection_run') IS NOT NULL THEN",
            "    EXECUTE 'SELECT count(*) FROM user_projection_run WHERE to_jsonb(user_projection_run)::TEXT LIKE $1'",
            "      INTO n6_refs USING '%' || target_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('user_signal_projection') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::TEXT LIKE $2'",
            "      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('user_signal_card') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM user_signal_card WHERE to_jsonb(user_signal_card)::TEXT LIKE $2'",
            "      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('user_notification_queue') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM user_notification_queue WHERE to_jsonb(user_notification_queue)::TEXT LIKE $2'",
            "      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';",
            "  END IF;",
            "",
            "  SELECT count(*) INTO downstream_touched_refs",
            "  FROM common_market_data_run",
            "  WHERE run_id = target_run_id AND downstream_layers_touched = true;",
            "",
            "  SELECT count(*) INTO worker_started_refs",
            "  FROM common_market_data_run",
            "  WHERE run_id = target_run_id AND worker_started = true;",
            "",
            "  IF outbox_refs <> 0",
            "     OR inbox_refs <> 0",
            "     OR checkpoint_refs <> 0",
            "     OR closed_30m_refs <> 0",
            "     OR realtime_projection_refs <> 0",
            "     OR trigger_refs <> 0",
            "     OR trigger_state_refs <> 0",
            "     OR action_refs <> 0",
            "     OR n6_refs <> 0",
            "     OR downstream_touched_refs <> 0",
            "     OR worker_started_refs <> 0 THEN",
            "    RAISE EXCEPTION",
            "      'N3-C1 rollback blocked for %, outbox=%, inbox=%, checkpoint=%, closed_30m=%, realtime_projection=%, trigger=%, trigger_state=%, action=%, n6=%, downstream_touched=%, worker=%',",
            "      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, closed_30m_refs, realtime_projection_refs,",
            "      trigger_refs, trigger_state_refs, action_refs, n6_refs, downstream_touched_refs, worker_started_refs;",
            "  END IF;",
            "END $$;",
            "",
            "BEGIN;",
            "",
            f"DELETE FROM common_market_data_quality_item WHERE run_id = {run_id};",
            f"DELETE FROM stock_minute_bar_1m WHERE run_id = {run_id} AND is_previous_day_preload = false;",
            f"DELETE FROM index_minute_bar_1m WHERE run_id = {run_id} AND is_previous_day_preload = false;",
            f"DELETE FROM board_minute_bar_1m WHERE run_id = {run_id} AND is_previous_day_preload = false;",
            f"DELETE FROM common_market_data_run WHERE run_id = {run_id} AND downstream_layers_touched = false AND worker_started = false;",
            "",
            "COMMIT;",
            "",
        ]
    )


def build_today_minute_execute_contract(*, today_minute_run_id: str, source_run_id: str) -> dict[str, Any]:
    return {
        "stage": "N3-C1-preflight",
        "layer_role": "N3_market_data",
        "today_minute_run_id": today_minute_run_id,
        "source_run_id": source_run_id,
        "run_once_only": True,
        "requires_execute_flag": True,
        "requires_user_confirmed_flag": True,
        "writes_outbox": False,
        "generated_event_types": [],
        "allowed_write_tables": [
            "common_market_data_run",
            "common_market_data_quality_item",
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
        ],
        "forbidden_write_tables": [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "stock_realtime_projection_metric",
            "index_realtime_projection_metric",
            "board_realtime_projection_metric",
            "trigger",
            "action",
            "user",
            "voice",
            "mobile",
            "sim",
            "position",
        ],
    }


def fetch_today_minute_target_audit(*, dsn: str, today_minute_run_id: str) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return {
            "today_minute_run_id": today_minute_run_id,
            "run_exists": market_data_run_exists(cur, today_minute_run_id),
            "target_run_row_counts": fetch_today_minute_run_row_counts(cur, today_minute_run_id),
            "outbox_rows_for_run": fetch_outbox_count(cur, today_minute_run_id),
            "inbox_rows_for_run": fetch_inbox_count(cur, today_minute_run_id),
        }


def market_data_run_exists(cur: Any, run_id: str) -> bool:
    cur.execute("SELECT 1 FROM common_market_data_run WHERE run_id = %s LIMIT 1", (run_id,))
    return cur.fetchone() is not None


def fetch_today_minute_run_row_counts(cur: Any, run_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in (*MINUTE_FACT_TABLES.values(), "common_market_data_quality_item", "common_market_data_run"):
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE run_id = %s", (run_id,))
        counts[table_name] = int(cur.fetchone()["row_count"])
    return counts


def fetch_outbox_count(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def fetch_inbox_count(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def build_today_minute_quality_items(
    *,
    subscription_report: Mapping[str, Any],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_batches: Sequence[Mapping[str, Any]],
    target_audit: Mapping[str, Any],
    latest_closed_minute: datetime | None,
    expected_bar_count_per_object: int,
    requested_for_trade_date: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    source_quality = today_minute_source_quality_summary(subscription_report)
    if int(source_quality["p0_count"] or 0) > 0:
        items.append(
            quality_item(
                gate_code="n3_c0_source_subscription_run_passed",
                gate_name="source N3 subscription run has no P0 blockers",
                severity="P0",
                status="failed",
                expected="p0_count=0",
                actual=f"p0_count={source_quality['p0_count']}",
            )
        )
    if requested_for_trade_date and requested_for_trade_date != str(subscription_report.get("for_trade_date") or ""):
        items.append(
            quality_item(
                gate_code="n3_c0_for_trade_date_matches_subscription",
                gate_name="requested for_trade_date matches source subscription run",
                severity="P0",
                status="failed",
                expected=str(subscription_report.get("for_trade_date") or ""),
                actual=requested_for_trade_date,
            )
        )
    if latest_closed_minute is None or expected_bar_count_per_object <= 0:
        items.append(
            quality_item(
                gate_code="n3_c0_latest_closed_minute_available",
                gate_name="at least one today 1m bar is closed",
                severity="P0",
                status="failed",
                expected="latest_closed_minute not null",
                actual=str(latest_closed_minute),
            )
        )
    if len(subscriptions) == 0:
        items.append(
            quality_item(
                gate_code="n3_c0_today_minute_subscriptions_present",
                gate_name="today minute_bar_1m subscriptions exist",
                severity="P0",
                status="failed",
                expected="subscription_count > 0",
                actual="0",
            )
        )
    object_counts_by_asset = asset_counts_by_asset(Counter(str(row.get("asset_kind") or "") for row in subscriptions))
    required_assets = {asset_kind for asset_kind in ASSET_KINDS if int(object_counts_by_asset.get(asset_kind) or 0) > 0}
    batch_assets = {str(row.get("asset_kind") or "") for row in pull_batches}
    if batch_assets != required_assets:
        items.append(
            quality_item(
                gate_code="n3_c0_today_minute_pull_plan_asset_coverage",
                gate_name="today minute pull plan covers asset kinds with object_count > 0",
                severity="P0",
                status="failed",
                expected=",".join(sorted(required_assets)),
                actual=",".join(sorted(str(item) for item in batch_assets)),
            )
        )
    if target_audit.get("run_exists"):
        items.append(
            quality_item(
                gate_code="n3_c0_today_minute_run_id_not_reused",
                gate_name="planned today minute run_id does not already exist",
                severity="P0",
                status="failed",
                expected="run_exists=false",
                actual="run_exists=true",
            )
        )
    dirty_targets = {
        table_name: count
        for table_name, count in (target_audit.get("target_run_row_counts") or {}).items()
        if int(count or 0) > 0
    }
    if dirty_targets:
        items.append(
            quality_item(
                gate_code="n3_c0_today_minute_target_empty",
                gate_name="planned today minute target run has no existing rows",
                severity="P0",
                status="failed",
                expected="all target row_count=0",
                actual=str(dirty_targets),
            )
        )
    if int(target_audit.get("outbox_rows_for_run") or 0) != 0:
        items.append(
            quality_item(
                gate_code="n3_c0_today_minute_outbox_empty",
                gate_name="planned today minute run has no outbox rows",
                severity="P0",
                status="failed",
                expected="0",
                actual=str(target_audit.get("outbox_rows_for_run")),
            )
        )
    if int(target_audit.get("inbox_rows_for_run") or 0) != 0:
        items.append(
            quality_item(
                gate_code="n3_c0_today_minute_inbox_empty",
                gate_name="planned today minute run has no inbox rows",
                severity="P0",
                status="failed",
                expected="0",
                actual=str(target_audit.get("inbox_rows_for_run")),
            )
        )
    if not items:
        items.append(
            quality_item(
                gate_code="n3_c0_today_minute_plan_ready",
                gate_name="today minute dry-run plan is ready for C1 preflight",
                severity="P2",
                status="passed",
                expected="ready",
                actual="ready",
            )
        )
    return items


def asset_counts_by_asset(counter: Counter[str]) -> dict[str, int]:
    return {asset_kind: int(counter.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}


def parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def ensure_shanghai_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ASIA_SHANGHAI)
    return value.astimezone(ASIA_SHANGHAI)


def parse_as_of(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return ensure_shanghai_timezone(parsed)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def write_report_files(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    markdown = Path(markdown_path)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(format_today_minute_markdown(report), encoding="utf-8")
    json_report = Path(json_path)
    json_report.parent.mkdir(parents=True, exist_ok=True)
    json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def format_today_minute_summary(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    return "\n".join(
        [
            "today minute_bar_1m dry-run",
            f"  stage={report.get('stage')}",
            f"  layer_role={report.get('layer_role')}",
            f"  source_market_data_run_id={report.get('source_market_data_run_id')}",
            f"  today_minute_run_id={report.get('today_minute_run_id')}",
            f"  for_trade_date={report.get('for_trade_date')}",
            f"  latest_closed_minute={report.get('latest_closed_minute')}",
            f"  expected_bar_count_per_object={report.get('expected_bar_count_per_object')}",
            f"  expected_minute_rows={report.get('expected_minute_rows')}",
            f"  object_count_by_asset={report.get('today_minute_object_count_by_asset_kind')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
            "  writes_performed=false market_data_pulled=false minute_bar_written=false "
            "event_outbox_written=false worker_started=false",
        ]
    )


def format_today_minute_markdown(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    lines = [
        "# N3-C0 Today Minute Bar 1m Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- stage: `{report.get('stage')}`",
        f"- layer_role: `{report.get('layer_role')}`",
        f"- result: `{'DRY_RUN_BLOCKED' if report.get('blocked') else 'DRY_RUN_PASS'}`",
        f"- source_market_data_run_id: `{report.get('source_market_data_run_id')}`",
        f"- today_minute_run_id: `{report.get('today_minute_run_id')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- latest_closed_minute: `{report.get('latest_closed_minute')}`",
        f"- expected_bar_count_per_object: `{report.get('expected_bar_count_per_object')}`",
        f"- expected_minute_rows: `{report.get('expected_minute_rows')}`",
        f"- object_count_by_asset: `{report.get('today_minute_object_count_by_asset_kind')}`",
        f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
        "",
        "## Boundary",
        "",
        "- market_data_pulled: `false`",
        "- minute_bar_written: `false`",
        "- event_outbox_written: `false`",
        "- outbox_consumed: `false`",
        "- downstream_layers_touched: `false`",
        "- worker_started: `false`",
        "",
        "## Execute Contract",
        "",
        "```text",
        "N3-C1 may only write common_market_data_run, common_market_data_quality_item,",
        "stock/index/board_minute_bar_1m with is_previous_day_preload=false.",
        "N3-C1 writes_outbox=false; MinuteBarClosed belongs to later N3-C2.",
        "```",
        "",
        "## Rollback SQL",
        "",
        "```sql",
        str((report.get("rollback_contract") or {}).get("rollback_sql") or "").strip(),
        "```",
        "",
    ]
    return "\n".join(lines)
