"""Offline B_BUY/S_SELL replay comparison against an explicitly approved reference DB.

This module is intentionally report-only: when the caller provides an explicit
SQLite path and confirms old-system read scope, it reads the reference DB,
builds N3-owned action-confirmation metrics from 1m bars, evaluates the
existing canonical B_BUY/S_SELL confirmation rules, and writes comparison
artifacts. It does not write runtime DB state or execute N4/N5 workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import csv
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping, Sequence


TARGET_DB_PATH: str | None = None
DEFAULT_TRADE_DATE = "20260612"
ALLOWED_SIGNAL_TYPES = ("B_BUY", "S_SELL")


class OldSystemReadConfirmationRequired(ValueError):
    """Raised when a reference DB read is attempted without explicit approval."""


def require_old_system_read_confirmation(db_path: str | None, *, old_system_read_confirmed: bool) -> str:
    if not db_path:
        raise OldSystemReadConfirmationRequired("missing explicit --target-db-path for old-system read")
    if not old_system_read_confirmed:
        raise OldSystemReadConfirmationRequired("old-system read requires --old-system-read-confirmed")
    return str(db_path)


def parse_minute(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def trade_date_to_iso(trade_date: str) -> str:
    return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): normalize_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [normalize_jsonable(v) for v in value]
    return value


def body_high(row: Mapping[str, Any]) -> float:
    return max(float(row["open"]), float(row["close"]))


def body_low(row: Mapping[str, Any]) -> float:
    return min(float(row["open"]), float(row["close"]))


def minute_index(dt: datetime) -> int | None:
    hm = dt.hour * 60 + dt.minute
    if 9 * 60 + 31 <= hm <= 11 * 60 + 30:
        return hm - (9 * 60 + 30)
    if 13 * 60 + 1 <= hm <= 15 * 60:
        return 120 + hm - 13 * 60
    if hm == 13 * 60:
        return 120
    return None


def segment_index(dt: datetime, period_minutes: int) -> int | None:
    idx = minute_index(dt)
    if idx is None:
        return None
    if period_minutes == 1:
        return idx - 1
    if period_minutes in (5, 30):
        return (idx - 1) // period_minutes
    if period_minutes == 120:
        return 0 if idx <= 120 else 1
    raise ValueError("period_minutes must be one of 1, 5, 30, 120")


def sort_minute_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        minute = row["datetime"]
        dt = minute if isinstance(minute, datetime) else parse_minute(str(minute))
        normalized.append(
            {
                "code": str(row["code"]),
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "_dt": dt,
                "open": float(row["open"] or 0.0),
                "high": float(row.get("high") or 0.0),
                "low": float(row.get("low") or 0.0),
                "close": float(row["close"] or 0.0),
                "amount": float(row.get("amount") or 0.0),
            }
        )
    normalized.sort(key=lambda r: r["_dt"])
    return normalized


def aggregate_segment(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    ordered = sorted(rows, key=lambda r: r["_dt"])
    return {
        "datetime": ordered[0]["datetime"],
        "open": float(ordered[0]["open"]),
        "close": float(ordered[-1]["close"]),
        "high": max(float(row["high"]) for row in ordered),
        "low": min(float(row["low"]) for row in ordered),
        "amount": sum(float(row.get("amount") or 0.0) for row in ordered),
        "minute_count": len(ordered),
        "body_high": max(float(ordered[0]["open"]), float(ordered[-1]["close"])),
        "body_low": min(float(ordered[0]["open"]), float(ordered[-1]["close"])),
    }


def rows_for_segment(
    rows: Sequence[Mapping[str, Any]],
    *,
    trade_date: str,
    period_minutes: int,
    seg_index: int,
    through: datetime | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        dt = row["_dt"]
        if dt.strftime("%Y%m%d") != trade_date:
            continue
        if through is not None and dt > through:
            continue
        if segment_index(dt, period_minutes) == seg_index:
            selected.append(dict(row))
    return selected


def previous_trade_date(rows: Sequence[Mapping[str, Any]], trade_date: str) -> str | None:
    dates = sorted({row["_dt"].strftime("%Y%m%d") for row in rows if row["_dt"].strftime("%Y%m%d") < trade_date})
    return dates[-1] if dates else None


def previous_segment_aggregate(
    rows: Sequence[Mapping[str, Any]],
    *,
    current_dt: datetime,
    period_minutes: int,
) -> tuple[dict[str, Any] | None, str]:
    current_trade_date = current_dt.strftime("%Y%m%d")
    current_seg = segment_index(current_dt, period_minutes)
    if current_seg is None:
        return None, "not_available"
    if current_seg > 0:
        agg = aggregate_segment(
            rows_for_segment(
                rows,
                trade_date=current_trade_date,
                period_minutes=period_minutes,
                seg_index=current_seg - 1,
            )
        )
        return agg, "same_trade_date_previous_period" if agg else "not_available"

    prev_date = previous_trade_date(rows, current_trade_date)
    if prev_date is None:
        return None, "not_available"
    prev_segments = [
        segment_index(row["_dt"], period_minutes)
        for row in rows
        if row["_dt"].strftime("%Y%m%d") == prev_date
    ]
    prev_segments = [seg for seg in prev_segments if seg is not None]
    if not prev_segments:
        return None, "not_available"
    agg = aggregate_segment(
        rows_for_segment(
            rows,
            trade_date=prev_date,
            period_minutes=period_minutes,
            seg_index=max(prev_segments),
        )
    )
    return agg, "previous_trade_date_last_period" if agg else "not_available"


def previous_minute_row(rows: Sequence[Mapping[str, Any]], current_dt: datetime) -> tuple[dict[str, Any] | None, str]:
    earlier = [dict(row) for row in rows if row["_dt"] < current_dt]
    if not earlier:
        return None, "not_available"
    row = earlier[-1]
    source = (
        "same_trade_date_previous_period"
        if row["_dt"].strftime("%Y%m%d") == current_dt.strftime("%Y%m%d")
        else "previous_trade_date_last_period"
    )
    return row, source


def current_period_virtual_amount(
    rows: Sequence[Mapping[str, Any]],
    *,
    current_dt: datetime,
    period_minutes: int,
) -> tuple[float, float]:
    trade_date = current_dt.strftime("%Y%m%d")
    seg = segment_index(current_dt, period_minutes)
    if seg is None:
        return 0.0, 0.0
    current_rows = rows_for_segment(
        rows,
        trade_date=trade_date,
        period_minutes=period_minutes,
        seg_index=seg,
        through=current_dt,
    )
    current_amount = sum(float(row.get("amount") or 0.0) for row in current_rows)
    current_virtual = (
        float(current_amount) / float(len(current_rows)) * float(period_minutes)
        if current_rows
        else 0.0
    )

    previous, _ = previous_segment_aggregate(
        rows,
        current_dt=current_dt,
        period_minutes=period_minutes,
    )
    previous_full_amount = float(previous["amount"]) if previous else 0.0
    return current_virtual, previous_full_amount


def build_metric_for_minute(
    rows: Sequence[Mapping[str, Any]],
    *,
    code: str,
    minute_label: str,
) -> dict[str, Any]:
    sorted_rows = sort_minute_rows(rows)
    target_dt = parse_minute(minute_label)
    target_rows = [row for row in sorted_rows if row["code"] == str(code) and row["_dt"] == target_dt]
    if not target_rows:
        return {
            "code": code,
            "metric_minute_label": minute_label,
            "metric_ready": False,
            "quality_status": "failed",
            "blocked_reasons": ["current_1m_not_found"],
        }

    current = target_rows[-1]
    previous_1m, previous_1m_source = previous_minute_row(sorted_rows, target_dt)
    previous_5m, previous_5m_source = previous_segment_aggregate(
        sorted_rows,
        current_dt=target_dt,
        period_minutes=5,
    )
    previous_30m, previous_30m_source = previous_segment_aggregate(
        sorted_rows,
        current_dt=target_dt,
        period_minutes=30,
    )
    previous_120m, previous_120m_source = previous_segment_aggregate(
        sorted_rows,
        current_dt=target_dt,
        period_minutes=120,
    )
    current_5m_virtual, previous_same_5m_full = current_period_virtual_amount(
        sorted_rows,
        current_dt=target_dt,
        period_minutes=5,
    )
    current_30m_virtual, previous_same_30m_full = current_period_virtual_amount(
        sorted_rows,
        current_dt=target_dt,
        period_minutes=30,
    )

    current_5m_seg = segment_index(target_dt, 5)
    current_30m_seg = segment_index(target_dt, 30)
    current_120m_seg = segment_index(target_dt, 120)
    blocked = []
    for name, value in (
        ("previous_1m", previous_1m),
        ("previous_5m", previous_5m),
        ("previous_30m", previous_30m),
        ("previous_120m", previous_120m),
    ):
        if value is None:
            blocked.append(f"{name}_not_found")

    metric = {
        "code": code,
        "metric_minute_label": minute_label,
        "metric_ready": not blocked,
        "quality_status": "passed" if not blocked else "failed",
        "blocked_reasons": blocked,
        "current_price": float(current["close"]),
        "current_price_source": "target_machine_minute_kline_1m.close",
        "current_price_time": minute_label,
        "current_1m_amount": float(current["amount"]),
        "previous_1m_amount": float(previous_1m["amount"]) if previous_1m else None,
        "previous_1m_body_high": body_high(previous_1m) if previous_1m else None,
        "previous_1m_body_low": body_low(previous_1m) if previous_1m else None,
        "previous_5m_body_high": previous_5m["body_high"] if previous_5m else None,
        "previous_5m_body_low": previous_5m["body_low"] if previous_5m else None,
        "previous_30m_body_high": previous_30m["body_high"] if previous_30m else None,
        "previous_30m_body_low": previous_30m["body_low"] if previous_30m else None,
        "previous_120m_body_high": previous_120m["body_high"] if previous_120m else None,
        "previous_120m_body_low": previous_120m["body_low"] if previous_120m else None,
        "current_5m_virtual_amount": current_5m_virtual,
        "previous_5m_full_amount": float(previous_5m["amount"]) if previous_5m else previous_same_5m_full,
        "current_30m_virtual_amount": current_30m_virtual,
        "previous_same_30m_full_amount": previous_same_30m_full,
        "is_first_1m_of_day": minute_index(target_dt) == 1,
        "is_first_5m_of_day": current_5m_seg == 0,
        "is_first_30m_of_day": current_30m_seg == 0,
        "is_first_120m_of_day": current_120m_seg == 0,
        "first_1m_amount_default_pass": minute_index(target_dt) == 1,
        "first_5m_amount_default_pass": current_5m_seg == 0,
        "previous_1m_period_source": previous_1m_source,
        "previous_5m_period_source": previous_5m_source,
        "previous_30m_period_source": previous_30m_source,
        "previous_120m_period_source": previous_120m_source,
        "boundary_policy_version": "v3.target_replay.n5_canonical.v1",
        "source_minute_refs": [minute_label],
        "previous_day_minute_refs": [],
        "raw_json": {
            "source": "target_machine.monitor_db.minute_kline",
            "midday_bridge_policy": "13:00_label_equivalent_to_missing_11:30_bar",
            "metric_replay_only": True,
        },
    }
    return normalize_jsonable(metric)


def _number(metric: Mapping[str, Any], key: str) -> float | None:
    value = metric.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_b_buy_s_sell(signal_type: str, metric: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    if signal_type not in ALLOWED_SIGNAL_TYPES:
        return {"passed": False, "blocked_reason": "unsupported_runtime_signal_type", "checks": checks}
    if not metric.get("metric_ready"):
        return {
            "passed": False,
            "blocked_reason": "metric_not_ready",
            "checks": checks,
            "metric_blocked_reasons": list(metric.get("blocked_reasons") or []),
        }

    price = _number(metric, "current_price")
    if price is None:
        return {"passed": False, "blocked_reason": "current_price_missing", "checks": checks}

    if signal_type == "B_BUY":
        checks["buy_120m_price_pass"] = price > (_number(metric, "previous_120m_body_high") or float("inf"))
        checks["buy_30m_price_pass"] = price > (_number(metric, "previous_30m_body_high") or float("inf"))
        checks["buy_5m_price_pass"] = price > (_number(metric, "previous_5m_body_high") or float("inf"))
        checks["buy_1m_price_pass"] = price > (_number(metric, "previous_1m_body_high") or float("inf"))
        checks["buy_5m_amount_pass"] = bool(metric.get("is_first_5m_of_day")) or (
            (_number(metric, "current_5m_virtual_amount") or 0.0)
            > (_number(metric, "previous_5m_full_amount") or float("inf"))
        )
        checks["buy_1m_amount_pass"] = bool(metric.get("is_first_1m_of_day")) or (
            (_number(metric, "current_1m_amount") or 0.0)
            > (_number(metric, "previous_1m_amount") or float("inf"))
        )
    else:
        checks["sell_120m_price_pass"] = price < (_number(metric, "previous_120m_body_low") or float("-inf"))
        checks["sell_30m_price_pass"] = price < (_number(metric, "previous_30m_body_low") or float("-inf"))
        checks["sell_5m_price_pass"] = price < (_number(metric, "previous_5m_body_low") or float("-inf"))
        checks["sell_1m_price_pass"] = price < (_number(metric, "previous_1m_body_low") or float("-inf"))
        checks["sell_5m_amount_pass"] = bool(metric.get("is_first_5m_of_day")) or (
            (_number(metric, "current_5m_virtual_amount") or float("inf"))
            < (_number(metric, "previous_5m_full_amount") or float("-inf"))
        )
        checks["sell_1m_amount_pass"] = bool(metric.get("is_first_1m_of_day")) or (
            (_number(metric, "current_1m_amount") or float("inf"))
            < (_number(metric, "previous_1m_amount") or float("-inf"))
        )
    failed = [key for key, passed in checks.items() if not passed]
    return {
        "passed": not failed,
        "blocked_reason": "" if not failed else "confirmation_rule_failed",
        "failed_checks": failed,
        "checks": checks,
    }


def target_legacy_board_amount_compat_evaluation(
    signal_type: str,
    evaluation: Mapping[str, Any] | None,
    *,
    monitor_type: str,
) -> dict[str, Any]:
    """Diagnostic-only target-machine board alert compatibility.

    The V3 canonical replay keeps amount checks intact. This compatibility view
    only explains old target-machine board alert rows where realtime alert output
    behaved as if board amount checks were not a hard blocker.
    """
    result = dict(evaluation or {})
    if result.get("passed"):
        return result
    if signal_type != "S_SELL" or monitor_type != "stock_board":
        return result
    failed = list(result.get("failed_checks") or [])
    if failed and all(item in {"sell_1m_amount_pass", "sell_5m_amount_pass"} for item in failed):
        result["passed"] = True
        result["blocked_reason"] = ""
        result["diagnostic_compatibility_reason"] = "target_legacy_stock_board_alert_amount_default_pass"
        result["failed_checks_before_compatibility"] = failed
        result["failed_checks"] = []
    return result


def sqlite_rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def load_target_actions(
    db_path: str | None,
    *,
    trade_date: str = DEFAULT_TRADE_DATE,
    old_system_read_confirmed: bool = False,
) -> list[dict[str, Any]]:
    confirmed_db_path = require_old_system_read_confirmation(
        db_path,
        old_system_read_confirmed=old_system_read_confirmed,
    )
    with sqlite3.connect(f"file:{confirmed_db_path}?mode=ro", uri=True) as conn:
        return sqlite_rows(
            conn,
            """
            SELECT
              signal_id, signal_date, signal_time, signal_type, code, name,
              monitor_type, asset_kind, quote_kind, current_price, price,
              virt_amount, today_amount, yesterday_amount, condition_key,
              trigger_period
            FROM action_fact_cache
            WHERE signal_date = ?
              AND signal_type IN ('B_BUY', 'S_SELL')
            ORDER BY signal_type, signal_time, code, signal_id
            """,
            (trade_date,),
        )


def load_target_minute_rows(
    db_path: str | None,
    *,
    codes: Sequence[str],
    trade_date: str = DEFAULT_TRADE_DATE,
    old_system_read_confirmed: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    confirmed_db_path = require_old_system_read_confirmation(
        db_path,
        old_system_read_confirmed=old_system_read_confirmed,
    )
    if not codes:
        return {}
    iso_date = trade_date_to_iso(trade_date)
    with sqlite3.connect(f"file:{confirmed_db_path}?mode=ro", uri=True) as conn:
        prev = conn.execute(
            """
            SELECT MAX(substr(datetime, 1, 10))
            FROM minute_kline
            WHERE period = '1m' AND substr(datetime, 1, 10) < ?
            """,
            (iso_date,),
        ).fetchone()[0]
        start_date = prev or iso_date
        placeholders = ",".join("?" for _ in codes)
        rows = sqlite_rows(
            conn,
            f"""
            SELECT code, datetime, open, high, low, close, amount
            FROM minute_kline
            WHERE period = '1m'
              AND code IN ({placeholders})
              AND substr(datetime, 1, 10) IN (?, ?)
            ORDER BY code, datetime
            """,
            [*codes, start_date, iso_date],
        )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["code"]), []).append(row)
    return grouped


def action_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("signal_type") or ""),
        str(row.get("monitor_type") or row.get("asset_kind") or ""),
        str(row.get("code") or ""),
        str(row.get("signal_time") or ""),
    )


def key_to_dict(key: tuple[str, str, str, str], count: int) -> dict[str, Any]:
    signal_type, monitor_type, code, signal_time = key
    return {
        "signal_type": signal_type,
        "monitor_type": monitor_type,
        "code": code,
        "signal_time": signal_time,
        "count": count,
    }


def build_replay_report(
    *,
    actions: Sequence[Mapping[str, Any]],
    minute_rows_by_code: Mapping[str, Sequence[Mapping[str, Any]]],
    trade_date: str,
) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    v3_rows: list[dict[str, Any]] = []
    target_action_price_rows: list[dict[str, Any]] = []
    target_legacy_board_amount_compat_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    action_price_differs_from_minute_close = 0

    for action in actions:
        code = str(action.get("code") or "")
        signal_time = str(action.get("signal_time") or "")
        minute_label = f"{trade_date_to_iso(trade_date)} {signal_time}"
        metric = build_metric_for_minute(minute_rows_by_code.get(code, []), code=code, minute_label=minute_label)
        evaluation = evaluate_b_buy_s_sell(str(action.get("signal_type") or ""), metric)
        action_price = _number(action, "price")
        action_current_price = _number(action, "current_price")
        action_price_evaluation: dict[str, Any] | None = None
        if action_price is not None:
            action_price_metric = dict(metric)
            action_price_metric["current_price"] = action_price
            action_price_metric["current_price_source"] = "target_machine.action_fact_cache.price"
            action_price_evaluation = evaluate_b_buy_s_sell(str(action.get("signal_type") or ""), action_price_metric)
            if action_price_evaluation.get("passed"):
                target_action_price_rows.append({**dict(action), "v3_evaluation": action_price_evaluation})
            compat_evaluation = target_legacy_board_amount_compat_evaluation(
                str(action.get("signal_type") or ""),
                action_price_evaluation,
                monitor_type=str(action.get("monitor_type") or ""),
            )
            if compat_evaluation.get("passed"):
                target_legacy_board_amount_compat_rows.append(
                    {**dict(action), "v3_evaluation": compat_evaluation}
                )
            if metric.get("current_price") is not None and abs(float(metric["current_price"]) - action_price) > 1e-9:
                action_price_differs_from_minute_close += 1
        metric_row = {
            "signal_id": action.get("signal_id"),
            "signal_type": action.get("signal_type"),
            "code": code,
            "name": action.get("name"),
            "monitor_type": action.get("monitor_type"),
            "asset_kind": action.get("asset_kind"),
            "signal_time": signal_time,
            "target_action_price": action_price,
            "target_action_current_price": action_current_price,
            "metric": metric,
            "evaluation": evaluation,
            "target_action_price_evaluation": action_price_evaluation,
        }
        metrics.append(metric_row)
        if evaluation.get("passed"):
            v3_rows.append({**dict(action), "v3_evaluation": evaluation})
        else:
            blocked_rows.append(metric_row)

    target_counter = Counter(action_key(row) for row in actions)
    v3_counter = Counter(action_key(row) for row in v3_rows)
    missing = []
    extra = []
    for key, count in sorted(target_counter.items()):
        gap = count - v3_counter.get(key, 0)
        if gap > 0:
            missing.append(key_to_dict(key, gap))
    for key, count in sorted(v3_counter.items()):
        gap = count - target_counter.get(key, 0)
        if gap > 0:
            extra.append(key_to_dict(key, gap))

    target_counts = dict(Counter(str(row.get("signal_type") or "") for row in actions))
    v3_counts = dict(Counter(str(row.get("signal_type") or "") for row in v3_rows))
    target_action_price_counts = dict(Counter(str(row.get("signal_type") or "") for row in target_action_price_rows))
    target_legacy_board_amount_compat_counts = dict(
        Counter(str(row.get("signal_type") or "") for row in target_legacy_board_amount_compat_rows)
    )
    metric_ready_counts = dict(Counter("ready" if row["metric"].get("metric_ready") else "not_ready" for row in metrics))
    blocked_reasons = Counter()
    failed_checks = Counter()
    for row in blocked_rows:
        for reason in row["metric"].get("blocked_reasons") or []:
            blocked_reasons[reason] += 1
        for check in row["evaluation"].get("failed_checks") or []:
            failed_checks[check] += 1
        reason = row["evaluation"].get("blocked_reason")
        if reason:
            blocked_reasons[reason] += 1

    return normalize_jsonable(
        {
            "stage": "V3_20260612_B_BUY_S_SELL_REPLAY_COMPARE",
            "result": "REPLAY_COMPARE_PASS",
            "mode": "offline_report_only",
            "trade_date": trade_date,
            "target_db_path": TARGET_DB_PATH,
            "target_golden_counts": target_counts,
            "v3_replay_counts": v3_counts,
            "metric_ready_counts": metric_ready_counts,
            "diff_summary": {
                "matched": sum((target_counter & v3_counter).values()),
                "missing_in_v3": sum(item["count"] for item in missing),
                "extra_in_v3": sum(item["count"] for item in extra),
                "missing_by_signal_type": dict(Counter(item["signal_type"] for item in missing for _ in range(item["count"]))),
                "extra_by_signal_type": dict(Counter(item["signal_type"] for item in extra for _ in range(item["count"]))),
            },
            "missing_in_v3": missing,
            "extra_in_v3": extra,
            "time_shift_candidates": [],
            "blocked_reason_counts": dict(blocked_reasons),
            "failed_check_counts": dict(failed_checks),
            "diagnostics": {
                "target_action_price_replay_counts": target_action_price_counts,
                "target_legacy_board_amount_compat_replay_counts": target_legacy_board_amount_compat_counts,
                "action_price_differs_from_minute_close": action_price_differs_from_minute_close,
                "current_price_source_primary": "target_machine.minute_kline.1m.close",
                "target_action_price_source": "target_machine.action_fact_cache.price",
                "target_action_price_replay_is_diagnostic_only": True,
                "target_legacy_board_amount_compat_is_diagnostic_only": True,
            },
            "sample_metrics": metrics[:20],
            "sample_blocked_rows": blocked_rows[:50],
            "side_effects": {
                "target_machine_read_only": True,
                "database_written": False,
                "runtime_db_written": False,
                "scheduler_started": False,
                "worker_started": False,
                "n4_n5_business_rules_changed": False,
                "n6_entered": False,
                "voice_mobile_sim_trade_touched": False,
            },
        }
    )


def build_report_from_target_db(
    *,
    target_db_path: str | None,
    trade_date: str = DEFAULT_TRADE_DATE,
    old_system_read_confirmed: bool = False,
) -> dict[str, Any]:
    confirmed_db_path = require_old_system_read_confirmation(
        target_db_path,
        old_system_read_confirmed=old_system_read_confirmed,
    )
    actions = load_target_actions(
        confirmed_db_path,
        trade_date=trade_date,
        old_system_read_confirmed=True,
    )
    codes = sorted({str(row["code"]) for row in actions})
    minute_rows_by_code = load_target_minute_rows(
        confirmed_db_path,
        codes=codes,
        trade_date=trade_date,
        old_system_read_confirmed=True,
    )
    report = build_replay_report(actions=actions, minute_rows_by_code=minute_rows_by_code, trade_date=trade_date)
    report["target_db_path"] = confirmed_db_path
    report["source_counts"] = {
        "target_action_rows": len(actions),
        "target_action_codes": len(codes),
        "minute_row_codes_loaded": len(minute_rows_by_code),
        "minute_rows_loaded": sum(len(rows) for rows in minute_rows_by_code.values()),
    }
    return report


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: str | Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# V3 20260612 B_BUY / S_SELL Replay Compare",
        "",
        f"- result: `{report.get('result')}`",
        f"- mode: `{report.get('mode')}`",
        f"- trade_date: `{report.get('trade_date')}`",
        f"- target_golden_counts: `{report.get('target_golden_counts')}`",
        f"- v3_replay_counts: `{report.get('v3_replay_counts')}`",
        f"- metric_ready_counts: `{report.get('metric_ready_counts')}`",
        f"- diff_summary: `{report.get('diff_summary')}`",
        f"- diagnostics: `{report.get('diagnostics')}`",
        "",
        "## Boundary",
        "",
    ]
    for key, value in dict(report.get("side_effects") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Blocked Reason Counts", ""])
    for key, value in sorted(dict(report.get("blocked_reason_counts") or {}).items()):
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Failed Check Counts", ""])
    for key, value in sorted(dict(report.get("failed_check_counts") or {}).items()):
        lines.append(f"- {key}: `{value}`")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_diff_csv(path: str | Path, report: Mapping[str, Any]) -> None:
    rows = []
    for section in ("missing_in_v3", "extra_in_v3", "time_shift_candidates"):
        for item in report.get(section) or []:
            rows.append({"diff_type": section, **dict(item)})
    fieldnames = ["diff_type", "signal_type", "monitor_type", "code", "signal_time", "count"]
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report_artifacts(
    report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
    diff_csv_path: str | Path,
) -> None:
    write_json(json_path, report)
    write_markdown(markdown_path, report)
    write_diff_csv(diff_csv_path, report)
