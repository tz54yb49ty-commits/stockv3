"""Read-only N6 UI v1 component models.

These helpers intentionally build display models from N6 projection tables and
reviewed artifacts only. They do not execute delivery, update outbox status, or
read market/raw account state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any
from zoneinfo import ZoneInfo

from ashare_v3.user.stale_active_lineage import (
    is_stale_source_action_run_id,
    is_stale_user_signal_row,
    stale_source_trigger_run_ids,
)


DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")

ACTION_BLOCKED_TITLE = "市场动作未确认"
ACTION_EXECUTED_TEXT = "市场动作确认成立"
APPROVED_BLOCKED_REASONS = {
    "price_confirmation_failed",
    "amount_confirmation_failed",
    "metric_missing",
    "metric_quality_failed",
    "lineage_mismatch",
    "missing_previous_session_reference",
}
FORBIDDEN_USER_LAYER_REASONS = {
    "no_position",
    "insufficient_cash",
    "t_plus_one_locked",
    "already_sold",
    "position_limit",
    "blacklist",
}
FORBIDDEN_PROVIDER_PAYLOAD_KEYS = {
    "trace_json",
    "trace",
    "source_payload_json",
    "source_raw_payload",
    "source_event_payload",
    "raw_payload",
    "n5_payload_json",
    "n5_outbox_payload",
    "action_run_payload",
    "internal_payload",
}
DISABLED_ENTRYPOINTS = {
    "delivery": True,
    "push": True,
    "voice": True,
    "mobile": True,
    "sim": True,
    "position": True,
    "real_trade": True,
}
READ_ONLY_SIDE_EFFECTS = {
    "writes_database": False,
    "outbox_status_updates": 0,
    "proposal_generated": False,
    "order_generated": False,
    "trade_generated": False,
    "position_updated": False,
    "pnl_generated": False,
    "delivery_triggered": False,
    "push_triggered": False,
    "voice_triggered": False,
    "mobile_triggered": False,
    "sim_written": False,
    "position_written": False,
    "real_trade_submitted": False,
}
VIRTUAL_ACCOUNT_SAFETY_LABELS = (
    "READ ONLY",
    "NO ORDER",
    "NO TRADE",
    "NO POSITION UPDATE",
    "NO REAL TRADE",
    "NOT INVESTMENT ADVICE",
)
STATUS_LABELS = {
    "blocked": {"label": "blocked", "text": "市场动作未确认", "tone": "warning"},
    "executed": {"label": "executed", "text": "市场动作确认成立", "tone": "success"},
    "eligible": {"label": "eligible", "text": "可关注", "tone": "info"},
    "skipped": {"label": "skipped", "text": "已跳过", "tone": "muted"},
    "queued_only": {"label": "queued_only", "text": "仅入队", "tone": "muted"},
    "preview": {"label": "preview", "text": "预览", "tone": "info"},
    "ready_for_future_push": {"label": "preview", "text": "预览", "tone": "info"},
    "delivered": {"label": "delivered", "text": "已投递记录", "tone": "success"},
    "rollback_safe": {"label": "rollback_safe", "text": "可回滚", "tone": "success"},
    "stale_artifact": {"label": "stale_artifact", "text": "artifact 可能过期", "tone": "warning"},
    "superseded": {"label": "superseded", "text": "已被新 run 覆盖", "tone": "muted"},
}
ROLLBACK_SQL_PATH = "sql/N6_projection_business_rollback.sql"


def signal_list_model(
    rows: list[dict[str, Any]],
    *,
    filters: dict[str, Any],
    pagination: dict[str, Any] | None = None,
    statistics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    visible_rows = [row for row in rows if not is_stale_user_signal_row(row)]
    excluded_stale_count = len(rows) - len(visible_rows)
    pagination_payload = pagination_model(
        pagination or {"total_count": len(visible_rows), "filtered_count": len(visible_rows)}
    )
    if pagination is None and excluded_stale_count:
        pagination_payload["excluded_stale_lineage_count"] = excluded_stale_count
    return {
        "ok": True,
        "component": "Signal List",
        "filters": {key: value for key, value in filters.items() if value},
        "statistics": signal_statistics_model(statistics or {}),
        "pagination": pagination_payload,
        "items": [signal_list_item(row) for row in visible_rows],
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def signal_list_item(row: dict[str, Any]) -> dict[str, Any]:
    action_state = normalized_action_state(row)
    queue_status = str(row.get("queue_status") or "—")
    rollback_safe = bool(row.get("rollback_safe", True))
    event_type = first_present_text(row, "event_type", "source_action_event_type")
    event_time = display_datetime(row.get("event_time") or row.get("trigger_time"))
    action = action_card(row)
    return {
        "user_signal_projection_id": row.get("user_signal_projection_id"),
        "event_type": event_type,
        "event_time": event_time,
        "status_label": action.get("title") or status_label(action_state)["text"],
        "trade_date": first_text(row, "trade_date"),
        "identity_key": first_text(row, "identity_key"),
        "asset_kind": first_text(row, "asset_kind"),
        "code": first_text(row, "code"),
        "name": first_text(row, "name"),
        "direction": first_text(row, "direction"),
        "signal_type": first_text(row, "signal_type"),
        "action_state": action_state,
        "action_mark": first_text(row, "action_mark"),
        "blocked_reason": safe_blocked_reason(row.get("blocked_reason")),
        "trigger_kind": first_text(row, "trigger_kind"),
        "condition_key": first_text(row, "condition_key"),
        "original_condition_key": first_text(row, "original_condition_key"),
        "triggered_periods": display_periods_text(row.get("triggered_periods")),
        "primary_trigger_period": first_text(row, "primary_trigger_period"),
        "trigger_time": display_datetime(row.get("trigger_time") or row.get("event_time")),
        "queue_status": queue_status,
        "delivery_status": first_text(row, "delivery_status", default="not_delivered"),
        "source_action_run_id": first_text(row, "source_action_run_id"),
        "source_event_id": first_text(row, "source_event_id"),
        "source_action_event_type": first_text(row, "source_action_event_type"),
        "target_price": number_or_none(row.get("target_price")),
        "current_price": number_or_none(row.get("current_price")),
        "expected_return_pct": number_or_none(row.get("expected_return_pct")),
        "board_code": first_text(row, "board_code"),
        "board_name": first_text(row, "board_name"),
        "status_labels": status_labels_for(action_state, queue_status, rollback_safe),
        "action_card": action,
        "detail_drawer": detail_drawer_model(row),
    }


def signal_detail_model(
    row: dict[str, Any],
    *,
    artifacts: dict[str, Any],
    rollback_summary: dict[str, Any],
) -> dict[str, Any]:
    item = signal_list_item(row)
    return {
        "ok": True,
        "component": "Signal Detail",
        "signal": item,
        "lineage": lineage_model(row),
        "action_card": item["action_card"],
        "detail_drawer": detail_drawer_model(row),
        "proposal_eligibility": proposal_eligibility_model(row, track="admin_console"),
        "notification_preview": notification_preview_model(row),
        "audit_panel": audit_panel_model(row, artifacts=artifacts, rollback_summary=rollback_summary),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
    }


def pagination_model(pagination: dict[str, Any]) -> dict[str, int]:
    return {
        "total_count": int(pagination.get("total_count") or 0),
        "filtered_count": int(pagination.get("filtered_count") or 0),
        "limit": int(pagination.get("limit") or 100),
        "offset": int(pagination.get("offset") or 0),
    }


def signal_statistics_model(statistics: dict[str, Any]) -> dict[str, Any]:
    distribution = dict(statistics.get("blocked_reason_distribution") or {})
    return {
        "ActionExecuted": int(statistics.get("ActionExecuted") or 0),
        "ActionBlocked": int(statistics.get("ActionBlocked") or 0),
        "TriggerMatched": int(statistics.get("TriggerMatched") or 0),
        "total_count": int(statistics.get("total_count") or 0),
        "blocked_reason_distribution": {
            "price_confirmation_failed": int(distribution.get("price_confirmation_failed") or 0),
            "metric_missing": int(distribution.get("metric_missing") or 0),
            "amount_confirmation_failed": int(distribution.get("amount_confirmation_failed") or 0),
        },
    }


def lineage_stats_model(stats: dict[str, Any]) -> dict[str, Any]:
    lineage_stats = dict(stats.get("lineage_stats") or {})
    n4_stats = dict(lineage_stats.get("N4") or {})
    n5_stats = dict(lineage_stats.get("N5") or {})
    legacy = dict(stats.get("legacy") or {})
    legacy_n4 = dict(legacy.get("N4") or {})
    blocked_reason = dict(stats.get("blocked_reason") or {})
    return {
        "ok": True,
        "component": "Full Lineage Message Stats",
        "title": "全链路消息统计",
        "source_runs": dict(stats.get("source_runs") or {}),
        "lineage_stats": {
            "N4": {
                "TriggerMatched": {
                    "pending": int(
                        dict(n4_stats.get("TriggerMatched") or {}).get("pending") or 0
                    )
                },
                "TriggerPendingMarketData": {
                    "pending": int(
                        dict(n4_stats.get("TriggerPendingMarketData") or {}).get("pending") or 0
                    )
                },
                "TriggerStateChanged": {
                    "pending": int(
                        dict(n4_stats.get("TriggerStateChanged") or {}).get("pending") or 0
                    )
                },
            },
            "N5": {
                "ActionExecuted": {
                    "pending": int(
                        dict(n5_stats.get("ActionExecuted") or {}).get("pending") or 0
                    )
                },
                "ActionBlocked": {
                    "pending": int(
                        dict(n5_stats.get("ActionBlocked") or {}).get("pending") or 0
                    )
                },
            },
        },
        "legacy": {
            "N4": {
                "TriggerCleared": {
                    "pending": int(
                        dict(legacy_n4.get("TriggerCleared") or {}).get("pending") or 0
                    ),
                    "display": str(
                        dict(legacy_n4.get("TriggerCleared") or {}).get("display")
                        or "hidden_by_default"
                    ),
                },
                "TriggerLiveChanged": {
                    "pending": int(
                        dict(legacy_n4.get("TriggerLiveChanged") or {}).get("pending") or 0
                    ),
                    "display": str(
                        dict(legacy_n4.get("TriggerLiveChanged") or {}).get("display")
                        or "hidden_by_default"
                    ),
                },
            }
        },
        "blocked_reason": {
            "price_confirmation_failed": int(blocked_reason.get("price_confirmation_failed") or 0),
            "amount_confirmation_failed": int(blocked_reason.get("amount_confirmation_failed") or 0),
            "metric_missing": int(blocked_reason.get("metric_missing") or 0),
        },
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
    }


def status_monitor_model(data: dict[str, Any], *, filters: dict[str, Any]) -> dict[str, Any]:
    event_summary = normalized_status_monitor_event_summary(
        dict(data.get("event_summary") or {})
    )
    relationship_summary = normalized_status_monitor_relationship_summary(
        dict(data.get("relationship_summary") or {})
    )
    status_summary = normalized_status_monitor_status_summary(
        dict(data.get("status_summary") or {})
    )
    pagination = pagination_model(
        data.get("pagination")
        or {"total_count": len(data.get("items") or []), "filtered_count": len(data.get("items") or [])}
    )
    return {
        "ok": True,
        "component": "N6 Status Monitor",
        "title": "N6 Status Monitor",
        "page_route": "/n6/status-monitor",
        "source_runs": dict(data.get("source_runs") or {}),
        "filters": {key: value for key, value in filters.items() if value},
        "event_summary": event_summary,
        "relationship_summary": relationship_summary,
        "status_summary": status_summary,
        "items": [status_monitor_item(row) for row in data.get("items") or []],
        "pagination": pagination,
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def normalized_status_monitor_event_summary(summary: dict[str, Any]) -> dict[str, Any]:
    n4 = dict(summary.get("N4") or {})
    n5 = dict(summary.get("N5") or {})
    return {
        "N4": {
            "TriggerMatched": status_monitor_count(n4, "TriggerMatched", action_entry=True),
            "TriggerPendingMarketData": status_monitor_count(
                n4, "TriggerPendingMarketData", action_entry=False
            ),
            "TriggerStateChanged": status_monitor_count(
                n4, "TriggerStateChanged", action_entry=False
            ),
        },
        "N5": {
            "ActionExecuted": status_monitor_count(n5, "ActionExecuted"),
            "ActionBlocked": status_monitor_count(n5, "ActionBlocked"),
        },
    }


def status_monitor_count(
    source: dict[str, Any],
    key: str,
    *,
    action_entry: bool | None = None,
) -> dict[str, Any]:
    item = dict(source.get(key) or {})
    result: dict[str, Any] = {"pending": int(item.get("pending") or 0)}
    if action_entry is not None:
        result["action_entry"] = bool(item.get("action_entry", action_entry))
    return result


def normalized_status_monitor_relationship_summary(summary: dict[str, Any]) -> dict[str, Any]:
    matched = dict(summary.get("matched_to_action") or {})
    status_only = dict(summary.get("status_only") or {})
    trigger_matched = int(matched.get("TriggerMatched") or 0)
    action_executed = int(matched.get("ActionExecuted") or 0)
    action_blocked = int(matched.get("ActionBlocked") or 0)
    unmatched = int(matched.get("unmatched") or max(trigger_matched - action_executed - action_blocked, 0))
    return {
        "matched_to_action": {
            "TriggerMatched": trigger_matched,
            "ActionExecuted": action_executed,
            "ActionBlocked": action_blocked,
            "unmatched": unmatched,
            "pass": bool(matched.get("pass", unmatched == 0)),
        },
        "status_only": {
            "TriggerPendingMarketData_action_entries": int(
                status_only.get("TriggerPendingMarketData_action_entries") or 0
            ),
            "TriggerStateChanged_action_entries": int(
                status_only.get("TriggerStateChanged_action_entries") or 0
            ),
        },
    }


def normalized_status_monitor_status_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "active": status_monitor_status_count(summary, "active", trigger_live=True),
        "pending_market_data": status_monitor_status_count(
            summary, "pending_market_data", trigger_live=False
        ),
        "inactive": status_monitor_status_count(summary, "inactive", trigger_live=False),
    }


def status_monitor_status_count(
    source: dict[str, Any],
    key: str,
    *,
    trigger_live: bool,
) -> dict[str, Any]:
    item = dict(source.get(key) or {})
    return {
        "count": int(item.get("count") or 0),
        "trigger_live": bool(item.get("trigger_live", trigger_live)),
    }


def status_monitor_item(row: dict[str, Any]) -> dict[str, Any]:
    source_layer = first_text(row, "source_layer")
    event_type = first_text(row, "event_type")
    identity_key = first_text(row, "identity_key")
    status_key = first_text(row, "status_key", default=row.get("status") or status_from_event(row))
    trigger_live = bool(row.get("trigger_live", status_key == "active"))
    relationship = as_mapping(row.get("n5_relationship"))
    action_event_type = first_present_text(row, "action_event_type", "event_type")
    action_state = first_present_text(row, "action_state", default=relationship.get("action_state") or "—")
    blocked_reason = safe_blocked_reason(row.get("blocked_reason") or relationship.get("blocked_reason"))
    related_n4_event_id = first_present_text(
        row,
        "related_n4_event_id",
        default=relationship.get("related_n4_event_id") or row.get("source_trigger_event_id") or "—",
    )
    if source_layer == "N4_trigger":
        related_n4_event_id = first_text(row, "event_id")
    return {
        "source_layer": source_layer,
        "event_type": event_type,
        "event_source": f"{source_layer} / {event_type}",
        "event_id": first_text(row, "event_id"),
        "event_time": display_datetime(row.get("event_time")),
        "outbox_status": first_text(row, "outbox_status", default=row.get("status") or "pending"),
        "status": status_key,
        "current_status": first_text(row, "current_status", default=status_to_current_status(status_key)),
        "trigger_live": trigger_live,
        "asset_kind": first_text(row, "asset_kind"),
        "identity_key": identity_key,
        "object": identity_key,
        "code": first_text(row, "code"),
        "name": first_text(row, "name"),
        "direction": first_text(row, "direction"),
        "signal_type": first_text(row, "signal_type"),
        "condition_key": first_text(row, "condition_key"),
        "source_run_id": first_text(row, "source_run_id"),
        "action_event_type": action_event_type if source_layer == "N5_action" else first_text(relationship, "action_event_type"),
        "action_state": action_state,
        "blocked_reason": blocked_reason,
        "related_n4_event_id": related_n4_event_id,
        "detail_drawer": {
            "event_source": f"{source_layer} / {event_type}",
            "event_id": first_text(row, "event_id"),
            "event_time": display_datetime(row.get("event_time")),
            "object": identity_key,
            "asset_kind": first_text(row, "asset_kind"),
            "identity_key": identity_key,
            "code": first_text(row, "code"),
            "name": first_text(row, "name"),
            "direction": first_text(row, "direction"),
            "signal_type": first_text(row, "signal_type"),
            "condition_key": first_text(row, "condition_key"),
            "source_run_id": first_text(row, "source_run_id"),
            "current_status": first_text(row, "current_status", default=status_to_current_status(status_key)),
            "trigger_live": trigger_live,
            "action_event_type": action_event_type,
            "action_state": action_state,
            "blocked_reason": blocked_reason,
            "related_n4_event_id": related_n4_event_id,
            "status_boundary": "No action entry" if event_type in {"TriggerPendingMarketData", "TriggerStateChanged"} else "Action entry only from TriggerMatched",
            "safety_banner": list(VIRTUAL_ACCOUNT_SAFETY_LABELS),
        },
    }


def status_from_event(row: dict[str, Any]) -> str:
    event_type = str(row.get("event_type") or "")
    current_status = str(row.get("current_status") or "")
    if event_type == "TriggerMatched" or current_status == "matched":
        return "active"
    if event_type == "TriggerPendingMarketData" or current_status == "pending_market_data":
        return "pending_market_data"
    if current_status == "inactive":
        return "inactive"
    return "active" if event_type in {"ActionExecuted", "ActionBlocked"} else "inactive"


def status_to_current_status(status_key: str) -> str:
    if status_key == "active":
        return "matched"
    if status_key == "pending_market_data":
        return "pending_market_data"
    if status_key == "inactive":
        return "inactive"
    return "—"


def detail_drawer_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "component": "Signal Detail Drawer",
        "event_id": first_text(row, "source_event_id"),
        "n4_trigger_event_id": first_text(row, "n4_trigger_event_id"),
        "n5_action_event_id": first_present_text(row, "source_action_event_id", "source_event_id"),
        "action_run_id": first_text(row, "source_action_run_id"),
        "source_action_status": first_text(row, "source_action_status"),
        "blocked_reason": safe_blocked_reason(row.get("blocked_reason")),
        "trigger_price": number_or_none(row.get("trigger_price")),
        "triggered_periods": first_text(row, "triggered_periods"),
        "baseline_source": first_text(row, "baseline_source"),
        "proposal_eligibility": proposal_eligibility_model(row, track="admin_console"),
        "safety_banner": list(VIRTUAL_ACCOUNT_SAFETY_LABELS),
        "missing_warnings": [
            warning
            for warning, value in (
                ("missing_n4_trigger_event_id", first_text(row, "n4_trigger_event_id")),
                ("missing_baseline_source", first_text(row, "baseline_source")),
            )
            if value == "—"
        ],
    }


def dashboard_metrics_model(metrics: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "today_signal_count": int(metrics.get("today_signal_count") or 0),
        "action_blocked": int(metrics.get("action_blocked") or 0),
        "action_executed": int(metrics.get("action_executed") or 0),
        "queued_only": int(metrics.get("queued_only") or 0),
        "pending_delivery": int(metrics.get("pending_delivery") or 0),
        "rollback_safe": bool(metrics.get("rollback_safe", False)),
        "latest_run_id": first_text(metrics, "latest_run_id"),
    }
    return {
        "ok": True,
        "component": "Dashboard",
        "metrics": normalized,
        "status_labels": status_labels_for(
            "rollback_safe" if normalized["rollback_safe"] else "stale_artifact",
            "queued_only",
            normalized["rollback_safe"],
        ),
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
    }


def message_dashboard_model(dashboard: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "component": "Message Dashboard",
        "safety_banner": {
            "read_only_preview": True,
            "outbox_consumed": False,
            "outbox_status_updated": False,
            "delivery_triggered": False,
            "push_triggered": False,
            "voice_triggered": False,
            "mobile_triggered": False,
            "sim_written": False,
            "position_written": False,
            "real_trade_submitted": False,
        },
        "admin_dashboard": admin_message_metrics_model(dict(dashboard.get("admin_dashboard") or {})),
        "message_dashboard": message_distribution_model(dict(dashboard.get("message_dashboard") or {})),
        "blocked_reason_distribution": [
            {"blocked_reason": first_text(row, "blocked_reason"), "count": int(row.get("count") or 0)}
            for row in list(dashboard.get("blocked_reason_distribution") or [])
        ],
        "recent_runs": [recent_run_model(row) for row in list(dashboard.get("recent_runs") or [])],
        "messages": [message_event_model(row) for row in list(dashboard.get("messages") or [])],
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def admin_message_metrics_model(metrics: dict[str, Any]) -> dict[str, Any]:
    int_keys = (
        "today_n4_trigger_matched_pending",
        "today_n5_action_blocked",
        "today_n5_action_executed",
        "n5_outbox_pending",
        "n6_shadow_projection_count",
        "n6_shadow_card_count",
        "n6_shadow_queue_count",
        "n6_queued_only",
        "n6_ready_for_future_push",
    )
    return {
        **{key: int(metrics.get(key) or 0) for key in int_keys},
        "latest_projection_run_id": first_text(metrics, "latest_projection_run_id"),
    }


def message_distribution_model(distribution: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_messages": int(distribution.get("total_messages") or 0),
        "event_distribution": [
            {
                "event_type": first_text(row, "event_type"),
                "status": first_text(row, "status"),
                "count": int(row.get("count") or 0),
            }
            for row in list(distribution.get("event_distribution") or [])
        ],
    }


def post_close_fastlane_status_model(data: dict[str, Any]) -> dict[str, Any]:
    status = dict(data.get("status") or {})
    effective_overlay = dict(data.get("effective_manual_overlay") or {})
    result = first_text(data, "result", default="NO_STATUS")
    selected_for_trade_date = first_text(data, "selected_for_trade_date")
    latest_for_trade_date = first_text(data, "latest_for_trade_date")
    normalized_status = {
        "result": result,
        "status_source": first_text(status, "status_source"),
        "current_effective_lineage": first_text(status, "current_effective_lineage"),
        "source_trade_date": first_text(status, "source_trade_date"),
        "for_trade_date": first_text(status, "for_trade_date", default=selected_for_trade_date),
        "failed_step_id": first_text(status, "failed_step_id"),
        "updated_at": first_text(status, "updated_at"),
        "n1_active_financial_source": first_text(status, "n1_active_financial_source"),
        "n2_active_condition_run": first_text(status, "n2_active_condition_run"),
        "n3_subscription_run": first_text(status, "n3_subscription_run"),
        "n3_a1_preload_run": first_text(status, "n3_a1_preload_run"),
        "original_oneshot_result": first_text(status, "original_oneshot_result"),
        "original_oneshot_status_path": first_text(status, "original_oneshot_status_path"),
        "original_oneshot_report_path": first_text(status, "original_oneshot_report_path"),
        "superseded_for_display_by_manual_overlay": bool(
            status.get("superseded_for_display_by_manual_overlay")
        ),
    }
    return {
        "ok": True,
        "component": "Post-Close Fast Lane Status",
        "title": "收盘后 Fast Lane 状态",
        "result": result,
        "result_tone": post_close_fastlane_result_tone(result),
        "selected_for_trade_date": selected_for_trade_date,
        "latest_for_trade_date": latest_for_trade_date,
        "latest_attempted_for_trade_date": first_text(data, "latest_attempted_for_trade_date"),
        "effective_manual_overlay": {
            "for_trade_date": first_text(effective_overlay, "for_trade_date"),
            "path": first_text(effective_overlay, "path"),
            "result": first_text(effective_overlay, "result"),
            "status_source": first_text(effective_overlay, "status_source"),
            "source_trade_date": first_text(effective_overlay, "source_trade_date"),
            "current_effective_lineage": first_text(effective_overlay, "current_effective_lineage"),
            "updated_at": first_text(effective_overlay, "updated_at"),
        },
        "docs_root": first_text(data, "docs_root"),
        "run_dir": first_text(data, "run_dir"),
        "status": normalized_status,
        "sub_steps": [post_close_fastlane_step_model(row) for row in list(data.get("sub_steps") or [])],
        "n3_a1_summary": post_close_fastlane_n3_a1_summary_model(
            dict(data.get("n3_a1_summary") or {})
        ),
        "n5_n3t_next_trade_day_readiness": post_close_fastlane_n5_n3t_readiness_model(
            dict(data.get("n5_n3t_next_trade_day_readiness") or {})
        ),
        "forbidden_scope_proof": dict(data.get("forbidden_scope_proof") or {}),
        "artifacts": [post_close_fastlane_artifact_model(row) for row in list(data.get("artifacts") or [])],
        "log_paths": [str(path) for path in list(data.get("log_paths") or [])],
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def runtime_archive_status_model(data: dict[str, Any]) -> dict[str, Any]:
    plan = dict(data.get("plan") or {})
    files = list(plan.get("files") or [])
    storage = dict(data.get("storage") or {})
    hot_cleanup = dict(data.get("hot_cleanup") or {})
    hot_cleanup_summary = runtime_hot_cleanup_summary_model(hot_cleanup)
    explicit_file_count = int(plan.get("file_count") or 0)
    explicit_total_rows = int(plan.get("total_rows") or 0)
    side_effects = {
        **dict(READ_ONLY_SIDE_EFFECTS),
        "writes_archive_files": False,
        "archive_files_written": False,
        "cleanup_local_runtime": False,
    }
    return {
        "ok": True,
        "component": "Runtime Hot Cleanup Status",
        "title": "Runtime Hot Cleanup Status",
        "result": first_text(data, "result", default="NO_STATUS"),
        "result_tone": runtime_archive_result_tone(first_text(data, "result", default="NO_STATUS")),
        "archive_state": first_text(data, "archive_state", default=first_text(data, "result", default="NO_STATUS")),
        "archive_execute_result": first_text(data, "archive_execute_result"),
        "row_count_match": bool(data.get("row_count_match") or plan.get("row_count_match")),
        "checksum_algorithm": first_text(data, "checksum_algorithm", default=first_text(plan, "checksum_algorithm")),
        "cleanup_executed": bool(data.get("cleanup_executed")),
        "local_cleanup_state": first_text(data, "local_cleanup_state", default=first_text(plan, "cleanup_state")),
        "post_cleanup": dict(data.get("post_cleanup") or {}),
        "hot_cleanup": hot_cleanup,
        "hot_cleanup_summary": hot_cleanup_summary,
        "hot_cleanup_source_path": first_text(data, "hot_cleanup_source_path"),
        "retained_metadata": dict(data.get("retained_metadata") or {}),
        "selected_trade_date": first_text(data, "selected_trade_date"),
        "latest_trade_date": first_text(data, "latest_trade_date"),
        "docs_root": first_text(data, "docs_root"),
        "run_dir": first_text(data, "run_dir"),
        "archive_root": first_text(data, "archive_root"),
        "hot_retention_days": int(data.get("hot_retention_days") or 5),
        "storage": {
            "archive_root": first_text(storage, "archive_root", default=first_text(data, "archive_root")),
            "mounted": bool(storage.get("mounted")),
            "writable": bool(storage.get("writable")),
            "free_bytes": int(storage.get("free_bytes") or 0),
            "minimum_free_bytes": int(storage.get("minimum_free_bytes") or 0),
            "free_space_ok": bool(storage.get("free_space_ok", True)),
        },
        "plan": {
            "status": first_text(plan, "status", default="HOT_ONLY"),
            "file_count": explicit_file_count or len(files),
            "total_rows": explicit_total_rows or sum(int(dict(file).get("row_count") or 0) for file in files if isinstance(file, dict)),
            "row_count_match": bool(plan.get("row_count_match")),
            "checksum_algorithm": first_text(plan, "checksum_algorithm"),
            "files": [runtime_archive_file_model(dict(file)) for file in files if isinstance(file, dict)],
            "manifest_path": first_text(plan, "manifest_path"),
            "report_path": first_text(plan, "report_path"),
            "blockers": [str(item) for item in list(plan.get("blockers") or [])],
            "cleanup_eligible": bool(plan.get("cleanup_eligible")),
            "cleanup_blockers": [str(item) for item in list(plan.get("cleanup_blockers") or [])],
            "cleanup_state": first_text(plan, "cleanup_state"),
        },
        "artifacts": [post_close_fastlane_artifact_model(row) for row in list(data.get("artifacts") or [])],
        "safety_labels": (
            "READ ONLY",
            "不执行归档",
            "不执行清理",
            "不写数据库",
            "不进入 N6 推送/语音/mobile/sim/trade",
        ),
        "side_effects": side_effects,
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def runtime_hot_cleanup_summary_model(hot_cleanup: dict[str, Any]) -> dict[str, Any]:
    result = first_text(hot_cleanup, "result", default="NO_CLEANUP_STATUS")
    summary_rows = list(hot_cleanup.get("deleted_table_summary") or [])
    if not summary_rows:
        summary_rows = summarize_hot_cleanup_deleted_rows(list(hot_cleanup.get("deleted_rows") or []))
    cleanup_success = bool(hot_cleanup.get("cleanup_success"))
    if "cleanup_success" not in hot_cleanup:
        cleanup_success = (
            result.endswith("EXECUTE_PASS")
            and bool(hot_cleanup.get("cleanup_executed"))
            and bool(hot_cleanup.get("cleanup_complete", True))
        )
    return {
        "result": result,
        "result_tone": runtime_archive_result_tone(result),
        "cleanup_success": cleanup_success,
        "cleanup_executed": bool(hot_cleanup.get("cleanup_executed")),
        "cleanup_complete": bool(hot_cleanup.get("cleanup_complete")),
        "direct_delete_no_archive": bool(hot_cleanup.get("direct_delete_no_archive")),
        "row_count_plan_skipped": bool(hot_cleanup.get("row_count_plan_skipped")),
        "retention_trade_days": int(hot_cleanup.get("retention_trade_days") or 5),
        "retained_trade_dates": [str(item) for item in list(hot_cleanup.get("retained_trade_dates") or [])],
        "cleanup_trade_dates": [str(item) for item in list(hot_cleanup.get("cleanup_trade_dates") or [])],
        "retained_trade_date_count": len(list(hot_cleanup.get("retained_trade_dates") or [])),
        "cleanup_trade_date_count": len(list(hot_cleanup.get("cleanup_trade_dates") or [])),
        "deleted_total_rows": int(hot_cleanup.get("deleted_total_rows") or 0),
        "deleted_table_summary": [hot_cleanup_table_summary_row(dict(row)) for row in summary_rows if isinstance(row, dict)],
        "deleted_table_summary_count": int(hot_cleanup.get("deleted_table_summary_count") or len(summary_rows)),
        "blockers": [str(item) for item in list(hot_cleanup.get("blockers") or [])],
        "started_at": first_text(hot_cleanup, "started_at"),
        "finished_at": first_text(hot_cleanup, "finished_at"),
        "duration_ms": number_or_none(hot_cleanup.get("duration_ms")),
    }


def summarize_hot_cleanup_deleted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        deleted_rows = int(row.get("deleted_rows") or 0)
        if deleted_rows <= 0:
            continue
        key = (first_text(row, "layer"), first_text(row, "table"))
        item = grouped.setdefault(key, {"layer": key[0], "table": key[1], "trade_dates": set(), "deleted_rows": 0})
        trade_date = first_text(row, "trade_date")
        if trade_date:
            item["trade_dates"].add(trade_date)
        item["deleted_rows"] += deleted_rows
    output: list[dict[str, Any]] = []
    for item in grouped.values():
        output.append(
            {
                "layer": item["layer"],
                "table": item["table"],
                "trade_date_count": len(item["trade_dates"]),
                "deleted_rows": int(item["deleted_rows"]),
            }
        )
    return sorted(output, key=lambda row: (str(row["layer"]), str(row["table"])))


def hot_cleanup_table_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "layer": first_text(row, "layer"),
        "table": first_text(row, "table"),
        "trade_date_count": int(row.get("trade_date_count") or 0),
        "deleted_rows": int(row.get("deleted_rows") or 0),
    }


def runtime_archive_result_tone(result: str) -> str:
    return {
        "EXECUTE_PASS": "success",
        "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS": "success",
        "ARCHIVE_PREFLIGHT_PASS": "success",
        "ARCHIVED_VERIFIED": "success",
        "CLEANUP_WAIT_CONFIRM": "warning",
        "LOCAL_CLEANED": "success",
        "LOCAL_CLEANED_METADATA_RETAINED": "success",
        "BLOCKED": "danger",
        "NO_STATUS": "muted",
        "NO_CLEANUP_STATUS": "muted",
        "HOT_ONLY": "muted",
    }.get(result, "warning")


def runtime_archive_file_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "layer": first_text(row, "layer"),
        "table": first_text(row, "table"),
        "row_count": int(row.get("row_count") or 0),
        "path": first_text(row, "path"),
    }


def post_close_fastlane_result_tone(result: str) -> str:
    return {
        "EXECUTE_PASS": "success",
        "NOOP": "muted",
        "BLOCKED": "danger",
        "PARTIAL_BLOCKED": "warning",
        "NO_STATUS": "muted",
    }.get(result, "warning")


def post_close_fastlane_step_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": first_text(row, "step_id"),
        "label": first_text(row, "label"),
        "layer_role": first_text(row, "layer_role"),
        "returncode": first_text(row, "returncode"),
        "status": first_text(row, "status", default="UNKNOWN"),
        "skipped": bool(row.get("skipped")),
        "skip_reason": first_text(row, "skip_reason"),
        "report_paths": [str(path) for path in list(row.get("report_paths") or [])],
        "stdout_tail": first_text(row, "stdout_tail"),
        "stderr_tail": first_text(row, "stderr_tail"),
    }


def post_close_fastlane_n3_a1_summary_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": first_text(row, "stage", default="N3-A1"),
        "objects_processed": int(row.get("objects_processed") or 0),
        "minute_rows_written": int(row.get("minute_rows_written") or 0),
        "preload_status_rows_written": int(row.get("preload_status_rows_written") or 0),
        "event_outbox_rows_written": int(row.get("event_outbox_rows_written") or 0),
        "P0": int(row.get("P0") or 0),
        "P1": int(row.get("P1") or 0),
        "P2": int(row.get("P2") or 0),
    }


def post_close_fastlane_n5_n3t_readiness_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(row),
        "source": first_text(row, "source"),
        "result": first_text(row, "result", default="NO_STATUS"),
        "next_trade_date": first_text(row, "next_trade_date"),
        "review_result": first_text(row, "review_result", default="NO_STATUS"),
        "active_worker_write_enabled_ready": first_text(row, "active_worker_write_enabled_ready", default="False"),
        "stable_activation_config_path": first_text(row, "stable_activation_config_path"),
        "active_worker_policy_review_path": first_text(row, "active_worker_policy_review_path"),
        "readiness_blocker": first_text(row, "readiness_blocker"),
        "launchd_live_state": first_text(row, "launchd_live_state", default="not_checked_by_status_page"),
    }


def post_close_fastlane_artifact_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": first_text(row, "label"),
        "file_name": first_text(row, "file_name"),
        "path": first_text(row, "path"),
        "exists": bool(row.get("exists")),
    }


def rag_search_model(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "component": "A-Track Read-only RAG",
        "answer_status": first_text(data, "answer_status", default="NO_EVIDENCE"),
        "query": first_text(data, "query"),
        "answer": first_text(data, "answer"),
        "evidence": [rag_evidence_model(dict(row)) for row in list(data.get("evidence") or [])],
        "safety": {
            "executes_commands": bool(dict(data.get("safety") or {}).get("executes_commands")),
            "writes_database": bool(dict(data.get("safety") or {}).get("writes_database")),
            "starts_worker": bool(dict(data.get("safety") or {}).get("starts_worker")),
            "reads_secret": bool(dict(data.get("safety") or {}).get("reads_secret")),
            "uses_external_llm": bool(dict(data.get("safety") or {}).get("uses_external_llm")),
            "updates_outbox_inbox_checkpoint": bool(
                dict(data.get("safety") or {}).get("updates_outbox_inbox_checkpoint")
            ),
        },
        "suggested_next_question": first_text(data, "suggested_next_question"),
        "disabled_entrypoints": dict(data.get("disabled_entrypoints") or {}),
    }


def rag_evidence_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": first_text(row, "path"),
        "title": first_text(row, "title"),
        "result": first_text(row, "result"),
        "artifact_type": first_text(row, "artifact_type"),
        "layer_role": first_text(row, "layer_role"),
        "gate_name": first_text(row, "gate_name"),
        "run_id": first_text(row, "run_id"),
        "matched_fields": [str(item) for item in list(row.get("matched_fields") or [])],
        "text_preview": first_text(row, "text_preview"),
    }


def recent_run_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "layer": first_text(row, "layer"),
        "run_id": first_text(row, "run_id"),
        "status": first_text(row, "status"),
        "created_at": display_datetime(row.get("created_at")),
        "finished_at": display_datetime(row.get("finished_at")),
    }


def message_event_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "outbox_id": row.get("outbox_id"),
        "event_id": first_text(row, "event_id"),
        "event_type": first_text(row, "event_type"),
        "trade_date": first_text(row, "trade_date"),
        "asset_kind": first_text(row, "asset_kind"),
        "identity_key": first_text(row, "identity_key"),
        "source_layer": first_text(row, "source_layer"),
        "source_run_id": first_text(row, "source_run_id"),
        "status": first_text(row, "status"),
        "direction": first_text(row, "direction"),
        "signal_type": first_text(row, "signal_type"),
        "action_state": first_text(row, "action_state"),
        "action_mark": first_text(row, "action_mark"),
        "condition_key": first_text(row, "condition_key"),
        "original_condition_key": first_text(row, "original_condition_key"),
        "event_time": display_datetime(row.get("event_time")),
        "created_at": display_datetime(row.get("created_at")),
    }


def n4_messages_model(data: dict[str, Any]) -> dict[str, Any]:
    items = [n4_message_item(row) for row in list(data.get("items") or [])]
    filters = dict(data.get("filters") or {})
    return {
        "ok": True,
        "component": "N4 Messages",
        "title": "N4 原始输出消息",
        "source_layer": "N4_trigger",
        "total_count": int(data.get("total_count") or 0),
        "filtered_count": int(data.get("filtered_count") or data.get("total_count") or 0),
        "returned_count": int(data.get("returned_count") or len(items)),
        "default_limit": int(data.get("default_limit") or 200),
        "include_all": bool(data.get("include_all")),
        "filters": filters,
        "filter_inputs": {
            "event_date": str(filters.get("event_date") or ""),
            "event_type": str(filters.get("event_type") or ""),
            "asset_kind": str(filters.get("asset_kind") or ""),
            "q": str(filters.get("q") or ""),
        },
        "latest_event_date": first_text(data, "latest_event_date"),
        "date_filter_defaulted": bool(data.get("date_filter_defaulted")),
        "event_types": list(data.get("event_types") or []),
        "standard_event_types": list(data.get("standard_event_types") or []),
        "legacy_event_types": list(data.get("legacy_event_types") or []),
        "items": items,
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def n3_messages_model(data: dict[str, Any]) -> dict[str, Any]:
    items = [n3_message_item(row) for row in list(data.get("items") or [])]
    filters = dict(data.get("filters") or {})
    return {
        "ok": True,
        "component": "N3 Messages",
        "title": "N3 行情输出消息",
        "source_layer": "N3_market_data",
        "total_count": int(data.get("total_count") or 0),
        "filtered_count": int(data.get("filtered_count") or data.get("total_count") or 0),
        "returned_count": int(data.get("returned_count") or len(items)),
        "default_limit": int(data.get("default_limit") or 200),
        "include_all": bool(data.get("include_all")),
        "filters": filters,
        "filter_inputs": {
            "event_date": str(filters.get("event_date") or ""),
            "event_type": str(filters.get("event_type") or ""),
            "status": str(filters.get("status") or ""),
            "asset_kind": str(filters.get("asset_kind") or ""),
            "q": str(filters.get("q") or ""),
        },
        "latest_event_date": first_text(data, "latest_event_date"),
        "date_filter_defaulted": bool(data.get("date_filter_defaulted")),
        "event_types": list(data.get("event_types") or []),
        "summary": n3_message_summary_model(data, items),
        "items": items,
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def n3_message_summary_model(data: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    raw_summary = dict(data.get("summary") or {})
    if raw_summary:
        return {
            "total": int(raw_summary.get("total") or data.get("filtered_count") or 0),
            "pending": int(raw_summary.get("pending") or 0),
            "MarketSnapshotUpdated": int(raw_summary.get("MarketSnapshotUpdated") or 0),
            "MinuteBarClosed": int(raw_summary.get("MinuteBarClosed") or 0),
            "MarketDisplaySnapshotUpdated": int(raw_summary.get("MarketDisplaySnapshotUpdated") or 0),
            "latest_event_time": display_datetime(raw_summary.get("latest_event_time")),
        }
    latest_event_time = ""
    event_times = [str(item.get("event_time") or "") for item in items if item.get("event_time")]
    if event_times:
        latest_event_time = max(event_times)
    return {
        "total": int(data.get("filtered_count") or len(items)),
        "pending": sum(1 for item in items if item.get("status") == "pending"),
        "MarketSnapshotUpdated": sum(1 for item in items if item.get("event_type") == "MarketSnapshotUpdated"),
        "MinuteBarClosed": sum(1 for item in items if item.get("event_type") == "MinuteBarClosed"),
        "MarketDisplaySnapshotUpdated": sum(
            1 for item in items if item.get("event_type") == "MarketDisplaySnapshotUpdated"
        ),
        "latest_event_time": latest_event_time,
    }


def n5_messages_model(data: dict[str, Any]) -> dict[str, Any]:
    items = [n5_message_item(row) for row in list(data.get("items") or [])]
    filters = dict(data.get("filters") or {})
    return {
        "ok": True,
        "component": "N5 Messages",
        "title": "N5消息中心",
        "source_layer": "N5_action",
        "total_count": int(data.get("total_count") or 0),
        "filtered_count": int(data.get("filtered_count") or data.get("total_count") or 0),
        "returned_count": int(data.get("returned_count") or len(items)),
        "default_limit": int(data.get("default_limit") or 200),
        "include_all": bool(data.get("include_all")),
        "filters": filters,
        "filter_inputs": {
            "event_date": str(filters.get("event_date") or ""),
            "event_type": str(filters.get("event_type") or ""),
            "status": str(filters.get("status") or ""),
            "asset_kind": str(filters.get("asset_kind") or ""),
            "q": str(filters.get("q") or ""),
        },
        "latest_event_date": first_text(data, "latest_event_date"),
        "date_filter_defaulted": bool(data.get("date_filter_defaulted")),
        "event_types": list(data.get("event_types") or []),
        "standard_event_types": list(data.get("standard_event_types") or []),
        "legacy_event_types": list(data.get("legacy_event_types") or []),
        "summary": n5_message_summary_model(data, items),
        "items": items,
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def n5_message_summary_model(data: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    raw_summary = dict(data.get("summary") or {})
    if raw_summary:
        return {
            "total": int(raw_summary.get("total") or data.get("filtered_count") or 0),
            "pending": int(raw_summary.get("pending") or 0),
            "ActionBlocked": int(raw_summary.get("ActionBlocked") or 0),
            "ActionExecuted": int(raw_summary.get("ActionExecuted") or 0),
            "legacy": int(raw_summary.get("legacy") or 0),
            "latest_event_time": display_datetime(raw_summary.get("latest_event_time")),
        }
    latest_event_time = ""
    event_times = [str(item.get("event_time") or "") for item in items if item.get("event_time")]
    if event_times:
        latest_event_time = max(event_times)
    return {
        "total": int(data.get("filtered_count") or len(items)),
        "pending": sum(1 for item in items if item.get("status") == "pending"),
        "ActionBlocked": sum(1 for item in items if item.get("event_type") == "ActionBlocked"),
        "ActionExecuted": sum(1 for item in items if item.get("event_type") == "ActionExecuted"),
        "legacy": sum(1 for item in items if item.get("legacy")),
        "latest_event_time": latest_event_time,
    }


def input_messages_model(data: dict[str, Any]) -> dict[str, Any]:
    items = [input_message_item(row) for row in list(data.get("items") or [])]
    filters = dict(data.get("filters") or {})
    return {
        "ok": True,
        "component": "N6 Input Messages",
        "title": "N6输入消息中心",
        "source_layers": list(data.get("source_layers") or ["N5_action", "N3_market_data"]),
        "total_count": int(data.get("total_count") or 0),
        "filtered_count": int(data.get("filtered_count") or data.get("total_count") or 0),
        "returned_count": int(data.get("returned_count") or len(items)),
        "default_limit": int(data.get("default_limit") or 200),
        "include_all": bool(data.get("include_all")),
        "filters": filters,
        "filter_inputs": {
            "event_date": str(filters.get("event_date") or ""),
            "source_layer": str(filters.get("source_layer") or ""),
            "input_group": str(filters.get("input_group") or ""),
            "event_type": str(filters.get("event_type") or ""),
            "status": str(filters.get("status") or ""),
            "asset_kind": str(filters.get("asset_kind") or ""),
            "q": str(filters.get("q") or ""),
        },
        "latest_event_date": first_text(data, "latest_event_date"),
        "date_filter_defaulted": bool(data.get("date_filter_defaulted")),
        "event_types": list(data.get("event_types") or []),
        "n5_canonical_event_types": list(data.get("n5_canonical_event_types") or []),
        "n5_legacy_event_types": list(data.get("n5_legacy_event_types") or []),
        "n3_display_event_types": list(data.get("n3_display_event_types") or []),
        "summary": input_message_summary_model(data, items),
        "items": items,
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def input_message_summary_model(data: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    raw_summary = dict(data.get("summary") or {})
    if raw_summary:
        return {
            "total": int(raw_summary.get("total") or data.get("filtered_count") or 0),
            "pending": int(raw_summary.get("pending") or 0),
            "n5_canonical": int(raw_summary.get("n5_canonical") or 0),
            "n5_legacy": int(raw_summary.get("n5_legacy") or 0),
            "n3_display_input": int(raw_summary.get("n3_display_input") or 0),
            "latest_event_time": display_datetime(raw_summary.get("latest_event_time")),
        }
    latest_event_time = ""
    event_times = [str(item.get("event_time") or "") for item in items if item.get("event_time")]
    if event_times:
        latest_event_time = max(event_times)
    return {
        "total": int(data.get("filtered_count") or len(items)),
        "pending": sum(1 for item in items if item.get("status") == "pending"),
        "n5_canonical": sum(1 for item in items if item.get("source_category") == "n5_canonical"),
        "n5_legacy": sum(1 for item in items if item.get("source_category") == "n5_legacy"),
        "n3_display_input": sum(1 for item in items if item.get("source_category") == "n3_display_input"),
        "latest_event_time": latest_event_time,
    }


def input_message_item(row: dict[str, Any]) -> dict[str, Any]:
    item = n5_message_item(row)
    event_type = item["event_type"]
    source_layer = item["source_layer"]
    payload = item["payload_json"]
    if source_layer == "N3_market_data" and event_type == "MarketDisplaySnapshotUpdated":
        source_category = "n3_display_input"
    elif event_type in {"ActionEvent", "HintEvent", "RiskEvent", "PositionEvent"}:
        source_category = "n5_legacy"
    else:
        source_category = "n5_canonical"
    item.update(
        {
            "source_category": source_category,
            "legacy": source_category == "n5_legacy",
            "action_state": first_text(payload, "action_state"),
            "blocked_reason": first_text(payload, "blocked_reason"),
            "action_mark": first_text(payload, "action_mark"),
            "signal_type": first_text(payload, "signal_type"),
            "direction": first_text(payload, "direction"),
        }
    )
    return item


def n2_condition_basis_model(data: dict[str, Any]) -> dict[str, Any]:
    filters = dict(data.get("filters") or {})
    items = [n2_condition_basis_item(row) for row in list(data.get("items") or [])]
    return {
        "ok": True,
        "component": "N2 Condition Basis",
        "title": "N2条件基础表",
        "source_layer": "N2_condition",
        "asset_kind": first_text(data, "asset_kind"),
        "asset_label": first_text(data, "asset_label"),
        "source_table": first_text(data, "source_table"),
        "total_count": int(data.get("total_count") or 0),
        "filtered_count": int(data.get("filtered_count") or data.get("total_count") or 0),
        "returned_count": int(data.get("returned_count") or len(items)),
        "default_limit": int(data.get("default_limit") or 200),
        "include_all": bool(data.get("include_all")),
        "filters": filters,
        "filter_inputs": {
            "source_trade_date": compact_trade_date_input(filters.get("source_trade_date")),
            "condition_key": str(filters.get("condition_key") or ""),
            "quality_status": str(filters.get("quality_status") or ""),
            "q": str(filters.get("q") or ""),
        },
        "latest_source_trade_date": first_text(data, "latest_source_trade_date"),
        "latest_source_trade_date_input": compact_trade_date_input(data.get("latest_source_trade_date")),
        "latest_source_trade_date_display": compact_trade_date_display(data.get("latest_source_trade_date")),
        "date_filter_defaulted": bool(data.get("date_filter_defaulted")),
        "asset_tabs": list(data.get("asset_tabs") or []),
        "items": items,
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
        "disabled_entrypoints": dict(DISABLED_ENTRYPOINTS),
    }


def n2_condition_basis_item(row: dict[str, Any]) -> dict[str, Any]:
    row_json = json_safe_value(row.get("row_json") or {})
    raw_json = json_safe_value(row.get("raw_json") or {})
    missing_fields_json = json_safe_value(row.get("missing_fields_json") or {})
    period_trigger_baseline_json = json_safe_value(row.get("period_trigger_baseline_json") or {})
    target_price_trace_json = json_safe_value(row.get("target_price_trace_json") or {})
    condition_keys = [
        key
        for key in (
            row.get("buy_necessary_key"),
            row.get("sell_necessary_key"),
            row.get("buy_full_necessary_key"),
            row.get("sell_full_necessary_key"),
            row.get("oversold_hint_key"),
            row.get("overbought_hint_key"),
        )
        if key
    ]
    direction_scope = row.get("direction_scope") or []
    if isinstance(direction_scope, str):
        direction_scope = [direction_scope]
    return {
        "asset_kind": first_text(row, "asset_kind"),
        "asset_label": first_text(row, "asset_label"),
        "source_table": first_text(row, "source_table"),
        "condition_basis_id": row.get("condition_basis_id"),
        "run_id": first_text(row, "run_id"),
        "for_trade_date": first_text(row, "for_trade_date"),
        "source_trade_date": first_text(row, "source_trade_date"),
        "source_trade_date_display": compact_trade_date_display(row.get("source_trade_date")),
        "prev_trade_date": first_text(row, "prev_trade_date"),
        "identity_key": first_text(row, "identity_key"),
        "code": first_text(row, "code"),
        "exchange": first_text(row, "exchange"),
        "name": first_text(row, "name"),
        "board_type": first_text(row, "board_type"),
        "lane": first_text(row, "lane"),
        "monitor_type": first_text(row, "monitor_type"),
        "monitor_status": first_text(row, "monitor_status"),
        "direction_scope": list(direction_scope),
        "direction_scope_text": " / ".join(str(item) for item in direction_scope) if direction_scope else "—",
        "period_keys": {
            "Y": first_text(row, "period_key_y"),
            "Q": first_text(row, "period_key_q"),
            "M": first_text(row, "period_key_m"),
            "W": first_text(row, "period_key_w"),
            "D": first_text(row, "period_key_d"),
        },
        "period_grades": {
            "Y": first_text(row, "period_grade_y"),
            "Q": first_text(row, "period_grade_q"),
            "M": first_text(row, "period_grade_m"),
            "W": first_text(row, "period_grade_w"),
            "D": first_text(row, "period_grade_d"),
        },
        "amount_quality_status": first_text(row, "amount_quality_status"),
        "buy_target_price": number_or_none(row.get("buy_target_price")),
        "buy_expected_return_pct": number_or_none(row.get("buy_expected_return_pct")),
        "sell_target_price": number_or_none(row.get("sell_target_price")),
        "sell_expected_return_pct": number_or_none(row.get("sell_expected_return_pct")),
        "up_sell_reference_period": first_text(row, "up_sell_reference_period"),
        "down_buy_reference_period": first_text(row, "down_buy_reference_period"),
        "condition_keys": condition_keys,
        "condition_keys_text": " / ".join(str(key) for key in condition_keys) if condition_keys else "—",
        "buy_necessary_key": first_text(row, "buy_necessary_key"),
        "sell_necessary_key": first_text(row, "sell_necessary_key"),
        "buy_full_necessary_key": first_text(row, "buy_full_necessary_key"),
        "sell_full_necessary_key": first_text(row, "sell_full_necessary_key"),
        "oversold_hint_key": first_text(row, "oversold_hint_key"),
        "overbought_hint_key": first_text(row, "overbought_hint_key"),
        "quality_status": first_text(row, "quality_status"),
        "quality_reason": first_text(row, "quality_reason"),
        "source_version": first_text(row, "source_version"),
        "source_batch_id": first_text(row, "source_batch_id"),
        "created_at": display_datetime(row.get("created_at")),
        "updated_at": display_datetime(row.get("updated_at")),
        "raw_json": raw_json,
        "missing_fields_json": missing_fields_json,
        "period_trigger_baseline_json": period_trigger_baseline_json,
        "target_price_trace_json": target_price_trace_json,
        "row_json": row_json,
        "row_json_text": json.dumps(row_json, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        "raw_json_text": json.dumps(raw_json, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        "period_trigger_baseline_json_text": json.dumps(
            period_trigger_baseline_json,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        "target_price_trace_json_text": json.dumps(
            target_price_trace_json,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ),
    }


def n3_message_item(row: dict[str, Any]) -> dict[str, Any]:
    payload = json_safe_value(row.get("payload_json") or {})
    display_payload = payload
    for hidden_key in ("dedup_key", "source_run_id", "event_id"):
        display_payload = redact_display_key(display_payload, hidden_key)
    return {
        "outbox_id": row.get("outbox_id"),
        "event_id": first_text(row, "event_id"),
        "event_type": first_text(row, "event_type"),
        "event_schema_version": first_text(row, "event_schema_version"),
        "trade_date": first_text(row, "trade_date"),
        "asset_kind": first_text(row, "asset_kind"),
        "identity_key": first_text(row, "identity_key"),
        "event_time": display_datetime(row.get("event_time")),
        "source_layer": first_text(row, "source_layer"),
        "source_run_id": first_text(row, "source_run_id"),
        "dedup_key": first_text(row, "dedup_key"),
        "partition_key": first_text(row, "partition_key"),
        "status": first_text(row, "status"),
        "attempt_count": int(row.get("attempt_count") or 0),
        "created_at": display_datetime(row.get("created_at")),
        "updated_at": display_datetime(row.get("updated_at")),
        "payload_json": payload,
        "payload_json_text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        "payload_json_display_text": json.dumps(
            display_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "output_fields": n3_output_fields(payload),
        "legacy": False,
    }


def n3_output_fields(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        return []
    field_keys = (
        "data_quality_status",
        "source_adapter",
        "subscription_id",
        "pull_plan_id",
        "snapshot_id",
        "minute_bar_id",
        "quality_item_id",
    )
    fields: list[dict[str, str]] = []
    for key in field_keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None or value == "":
            continue
        fields.append({"label": key, "value": n4_output_field_value(value)})
    return fields


def n4_message_item(row: dict[str, Any]) -> dict[str, Any]:
    payload = json_safe_value(row.get("payload_json") or {})
    display_payload = payload
    for hidden_key in ("dedup_key", "source_run_id", "event_id"):
        display_payload = redact_display_key(display_payload, hidden_key)
    stale_lineage = is_stale_n4_message_row(row, payload)
    output_fields = n4_output_fields(payload)
    if stale_lineage:
        output_fields.insert(0, {"label": "lineage_classification", "value": "STALE"})
    return {
        "outbox_id": row.get("outbox_id"),
        "event_id": first_text(row, "event_id"),
        "event_type": first_text(row, "event_type"),
        "event_schema_version": first_text(row, "event_schema_version"),
        "trade_date": first_text(row, "trade_date"),
        "asset_kind": first_text(row, "asset_kind"),
        "identity_key": first_text(row, "identity_key"),
        "event_time": display_datetime(row.get("event_time")),
        "trigger_time": display_payload_datetime(payload.get("trigger_time")) if isinstance(payload, dict) else "",
        "source_layer": first_text(row, "source_layer"),
        "source_run_id": first_text(row, "source_run_id"),
        "dedup_key": first_text(row, "dedup_key"),
        "partition_key": first_text(row, "partition_key"),
        "status": first_text(row, "status"),
        "attempt_count": int(row.get("attempt_count") or 0),
        "created_at": display_datetime(row.get("created_at")),
        "updated_at": display_datetime(row.get("updated_at")),
        "payload_json": payload,
        "payload_json_text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        "payload_json_display_text": json.dumps(
            display_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "output_fields": output_fields,
        "legacy": first_text(row, "event_type") in {"TriggerCleared", "TriggerLiveChanged"},
        "stale_lineage": stale_lineage,
        "lineage_classification": "STALE" if stale_lineage else "ACTIVE",
    }


def n4_output_fields(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        return []
    field_keys = (
        "current_status",
        "trigger_live",
        "trigger_time",
        "trigger_price",
        "triggered_periods",
        "quality_status",
        "condition_key",
        "baseline_source",
        "projection_30m_flag",
        "projection_30m_type",
        "trigger_mark_candidate",
    )
    fields: list[dict[str, str]] = []
    for key in field_keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None or value == "":
            continue
        fields.append({"label": key, "value": n4_output_field_value(value)})
    return fields


def n4_output_field_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def redact_display_key(value: Any, hidden_key: str) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_display_key(item, hidden_key)
            for key, item in value.items()
            if key != hidden_key
        }
    if isinstance(value, list):
        return [redact_display_key(item, hidden_key) for item in value]
    return value


def n5_message_item(row: dict[str, Any]) -> dict[str, Any]:
    payload = json_safe_value(row.get("payload_json") or {})
    display_payload = payload
    for hidden_key in ("dedup_key", "source_run_id", "event_id"):
        display_payload = redact_display_key(display_payload, hidden_key)
    stale_lineage = is_stale_n5_message_row(row, payload)
    output_fields = n5_output_fields(payload)
    if stale_lineage:
        output_fields.insert(0, {"label": "lineage_classification", "value": "STALE"})
    return {
        "outbox_id": row.get("outbox_id"),
        "event_id": first_text(row, "event_id"),
        "event_type": first_text(row, "event_type"),
        "event_schema_version": first_text(row, "event_schema_version"),
        "trade_date": first_text(row, "trade_date"),
        "asset_kind": first_text(row, "asset_kind"),
        "identity_key": first_text(row, "identity_key"),
        "event_time": display_datetime(row.get("event_time")),
        "source_layer": first_text(row, "source_layer"),
        "source_run_id": first_text(row, "source_run_id"),
        "dedup_key": first_text(row, "dedup_key"),
        "partition_key": first_text(row, "partition_key"),
        "status": first_text(row, "status"),
        "attempt_count": int(row.get("attempt_count") or 0),
        "created_at": display_datetime(row.get("created_at")),
        "updated_at": display_datetime(row.get("updated_at")),
        "payload_json": payload,
        "payload_json_text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        "payload_json_display_text": json.dumps(
            display_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        "output_fields": output_fields,
        "legacy": first_text(row, "event_type") in {"ActionEvent", "HintEvent", "RiskEvent", "PositionEvent"},
        "stale_lineage": stale_lineage,
        "lineage_classification": "STALE" if stale_lineage else "ACTIVE",
    }


def is_stale_n4_message_row(row: dict[str, Any], payload: Any) -> bool:
    source_run_id = first_text(row, "source_run_id")
    if source_run_id in stale_source_trigger_run_ids():
        return True
    if isinstance(payload, dict):
        payload_source_run_id = str(payload.get("source_run_id") or payload.get("trigger_run_id") or "")
        if payload_source_run_id in stale_source_trigger_run_ids():
            return True
    return False


def is_stale_n5_message_row(row: dict[str, Any], payload: Any) -> bool:
    source_run_id = first_text(row, "source_run_id")
    if is_stale_source_action_run_id(source_run_id):
        return True
    if isinstance(payload, dict):
        payload_source_run_id = str(payload.get("source_action_run_id") or payload.get("run_id") or "")
        if is_stale_source_action_run_id(payload_source_run_id):
            return True
    return False


def n5_output_fields(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        return []
    field_keys = (
        "action_state",
        "blocked_reason",
        "action_mark",
        "signal_type",
        "direction",
        "condition_key",
        "original_condition_key",
        "confirmation_status",
        "final_action_mark",
    )
    fields: list[dict[str, str]] = []
    for key in field_keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None or value == "":
            continue
        fields.append({"label": key, "value": n4_output_field_value(value)})
    return fields


def artifacts_model(artifacts: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "component": "Audit Panel",
        "artifacts": list(artifacts.get("artifacts") or []),
        "stale_artifact": bool(artifacts.get("stale_artifact", False)),
        "status_labels": [status_label("stale_artifact")] if artifacts.get("stale_artifact") else [],
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
    }


def rollback_summary_model(summary: dict[str, Any]) -> dict[str, Any]:
    rollback_summary = {
        "rollback_sql_path": str(summary.get("rollback_sql_path") or ROLLBACK_SQL_PATH),
        "rollback_safe": bool(summary.get("rollback_safe", False)),
        "delete_order": list(summary.get("delete_order") or []),
        "hard_fail_guards": list(summary.get("hard_fail_guards") or []),
    }
    return {
        "ok": True,
        "component": "Audit Panel",
        "rollback_summary": rollback_summary,
        "execute_enabled": False,
        "status_labels": [status_label("rollback_safe")] if rollback_summary["rollback_safe"] else [],
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
    }


def virtual_account_summary_model(
    account: dict[str, Any] | None,
    *,
    cash_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": account is not None,
        "component": "Virtual Account Summary",
        "readonly": True,
        "virtual_account": virtual_account_item(account),
        "cash_summary": cash_summary_item(cash_snapshot),
        "safety_banner": list(VIRTUAL_ACCOUNT_SAFETY_LABELS),
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
    }


def cash_snapshot_model(row: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "ok": row is not None,
        "component": "Cash Snapshot",
        "readonly": True,
        "cash_snapshot": cash_snapshot_item(row),
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
    }


def cash_ledger_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": True,
        "component": "Cash Ledger",
        "readonly": True,
        "items": [cash_ledger_item(row) for row in rows],
        "side_effects": dict(READ_ONLY_SIDE_EFFECTS),
    }


def virtual_account_item(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "virtual_account_id": None,
            "account_name": "—",
            "base_currency": "—",
            "initial_cash": None,
            "quality_status": "missing",
            "seed_run_id": "—",
        }
    return {
        "virtual_account_id": row.get("virtual_account_id"),
        "principal_id": row.get("principal_id"),
        "principal_type": first_text(row, "principal_type"),
        "account_name": first_text(row, "account_name"),
        "virtual_account_status": first_text(row, "virtual_account_status"),
        "base_currency": first_text(row, "base_currency"),
        "initial_cash": number_or_none(row.get("initial_cash")),
        "current_cash_snapshot_id": row.get("current_cash_snapshot_id"),
        "run_id": first_text(row, "run_id"),
        "seed_run_id": first_text(row, "run_id"),
        "policy_version": first_text(row, "policy_version"),
        "policy_hash": first_text(row, "policy_hash"),
        "rollback_scope": first_text(row, "rollback_scope"),
        "quality_status": first_text(row, "quality_status"),
        "created_at": display_datetime(row.get("created_at")),
        "updated_at": display_datetime(row.get("updated_at")),
    }


def cash_summary_item(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "available_cash": None,
            "frozen_cash": None,
            "total_cash": None,
            "currency": "—",
            "snapshot_status": "missing",
        }
    return {
        "cash_snapshot_id": row.get("cash_snapshot_id"),
        "available_cash": number_or_none(row.get("available_cash")),
        "frozen_cash": number_or_none(row.get("frozen_cash")),
        "total_cash": number_or_none(row.get("total_cash")),
        "currency": first_text(row, "currency"),
        "snapshot_status": first_text(row, "snapshot_status"),
        "snapshot_time": display_datetime(row.get("snapshot_time")),
        "source_ledger_max_id": row.get("source_ledger_max_id"),
    }


def cash_snapshot_item(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "cash_snapshot_id": None,
            "virtual_account_id": None,
            "available_cash": None,
            "frozen_cash": None,
            "total_cash": None,
            "currency": "—",
            "snapshot_status": "missing",
        }
    return {
        "cash_snapshot_id": row.get("cash_snapshot_id"),
        "virtual_account_id": row.get("virtual_account_id"),
        "snapshot_time": display_datetime(row.get("snapshot_time")),
        "trade_date": row.get("trade_date"),
        "available_cash": number_or_none(row.get("available_cash")),
        "frozen_cash": number_or_none(row.get("frozen_cash")),
        "total_cash": number_or_none(row.get("total_cash")),
        "currency": first_text(row, "currency"),
        "source_ledger_max_id": row.get("source_ledger_max_id"),
        "snapshot_status": first_text(row, "snapshot_status"),
        "run_id": first_text(row, "run_id"),
        "policy_version": first_text(row, "policy_version"),
        "policy_hash": first_text(row, "policy_hash"),
        "rollback_scope": first_text(row, "rollback_scope"),
        "quality_status": first_text(row, "quality_status"),
        "created_at": display_datetime(row.get("created_at")),
        "pointer_missing_warning": bool(row.get("pointer_missing_warning", False)),
    }


def cash_ledger_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "cash_ledger_id": row.get("cash_ledger_id"),
        "virtual_account_id": row.get("virtual_account_id"),
        "ledger_type": first_text(row, "ledger_type"),
        "amount": number_or_none(row.get("amount")),
        "currency": first_text(row, "currency"),
        "trade_date": row.get("trade_date"),
        "event_time": display_datetime(row.get("event_time")),
        "source_event_type": first_text(row, "source_event_type"),
        "source_event_id": row.get("source_event_id"),
        "source_virtual_order_id": row.get("source_virtual_order_id"),
        "source_virtual_trade_id": row.get("source_virtual_trade_id"),
        "run_id": first_text(row, "run_id"),
        "policy_version": first_text(row, "policy_version"),
        "policy_hash": first_text(row, "policy_hash"),
        "rollback_scope": first_text(row, "rollback_scope"),
        "quality_status": first_text(row, "quality_status"),
        "created_at": display_datetime(row.get("created_at")),
    }


def proposal_eligibility_model(row: dict[str, Any], *, track: str = "b_track") -> dict[str, Any]:
    event_type = first_text(row, "source_action_event_type")
    action_state = normalized_action_state(row)
    mapping = {
        "blocked": {
            "label": "ActionBlocked",
            "behavior": "display_only",
            "future_eligible": False,
            "display_text": "展示，不生成 proposal",
        },
        "executed": {
            "label": "ActionExecuted",
            "behavior": "proposal_candidate",
            "future_eligible": True,
            "display_text": "proposal candidate，仅未来复核资格提示",
        },
        "eligible": {
            "label": "ActionEligible",
            "behavior": "policy_candidate",
            "future_eligible": True,
            "display_text": "policy candidate，仅未来策略资格提示",
        },
        "skipped": {
            "label": "ActionSkipped",
            "behavior": "informational_only",
            "future_eligible": False,
            "display_text": "信息展示，不生成 proposal",
        },
    }
    if track == "admin_console" and action_state == "executed":
        mapping = dict(mapping)
        mapping["executed"] = {
            "label": "ActionExecuted",
            "behavior": "projection_only",
            "future_eligible": False,
            "display_text": "管理员只读投影，不生成 proposal / order / trade / position / PnL",
        }
    selected = dict(mapping.get(action_state, {
        "label": event_type,
        "behavior": "display_only",
        "future_eligible": False,
        "display_text": "仅展示，不生成 proposal",
    }))
    return {
        "component": "Proposal Eligibility",
        "source_action_event_type": event_type,
        "action_state": action_state,
        "label": selected["label"],
        "behavior": selected["behavior"],
        "future_eligible": selected["future_eligible"],
        "display_text": selected["display_text"],
        "proposal_generated": False,
        "order_generated": False,
        "trade_generated": False,
        "position_updated": False,
        "pnl_generated": False,
        "real_trade_submitted": False,
    }


def action_card(row: dict[str, Any]) -> dict[str, Any]:
    action_state = normalized_action_state(row)
    if action_state == "blocked":
        return action_blocked_card(row)
    if action_state == "executed":
        return action_executed_card(row)
    return {
        "component": "Shared Status Label",
        "title": STATUS_LABELS.get(action_state, {"text": action_state})["text"],
        "display_text": STATUS_LABELS.get(action_state, {"text": action_state})["text"],
        "decision_buttons_enabled": False,
        "delivery_enabled": False,
        "sim_enabled": False,
        "position_enabled": False,
        "real_trade_enabled": False,
    }


def action_blocked_card(row: dict[str, Any]) -> dict[str, Any]:
    blocked_reason = safe_blocked_reason(row.get("blocked_reason"))
    display_reason = blocked_reason if blocked_reason != "—" else "N5 市场动作未确认"
    return {
        "component": "ActionBlocked Card",
        "title": ACTION_BLOCKED_TITLE,
        "blocked_reason": blocked_reason,
        "display_text": f"{ACTION_BLOCKED_TITLE}：{display_reason}",
        "forbidden_user_reasons_hidden": True,
        "decision_buttons_enabled": False,
        "delivery_enabled": False,
        "sim_enabled": False,
        "position_enabled": False,
        "real_trade_enabled": False,
    }


def action_executed_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "component": "ActionExecuted Card",
        "title": ACTION_EXECUTED_TEXT,
        "display_text": f"{ACTION_EXECUTED_TEXT}。仅表示 N5 市场动作确认事实成立，不代表账户或持仓变化。",
        "decision_buttons_enabled": False,
        "delivery_enabled": False,
        "sim_enabled": False,
        "position_enabled": False,
        "real_trade_enabled": False,
    }


def notification_preview_model(row: dict[str, Any]) -> dict[str, Any]:
    payload = as_mapping(row.get("notification_payload_json"))
    sanitized_payload, dropped_keys = sanitize_provider_payload(payload)
    return {
        "component": "Notification Preview",
        "queue_status": first_text(row, "queue_status"),
        "delivery_status": first_text(row, "delivery_status", default="not_delivered"),
        "notification_source": first_text(row, "notification_source"),
        "channel": first_text(row, "channel"),
        "delivery_triggered": False,
        "provider_visible_payload": {
            "title": first_text(row, "title", default=payload.get("title") or ""),
            "message": first_text(row, "message", default=payload.get("message") or ""),
            "notification_payload_json": sanitized_payload,
        },
        "forbidden_payload_keys_present": sorted(dropped_keys),
    }


def audit_panel_model(
    row: dict[str, Any],
    *,
    artifacts: dict[str, Any],
    rollback_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "component": "Audit Panel",
        "run_id": first_text(row, "user_projection_run_id"),
        "event_id": first_text(row, "source_event_id"),
        "rollback_safe": bool(row.get("rollback_safe", rollback_summary.get("rollback_safe", False))),
        "rollback_sql_path": str(rollback_summary.get("rollback_sql_path") or ROLLBACK_SQL_PATH),
        "artifact_links": list(artifacts.get("artifacts") or []),
        "source_action_run_id": first_text(row, "source_action_run_id"),
        "source_action_event_type": first_text(row, "source_action_event_type"),
        "execute_enabled": False,
    }


def lineage_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "N4": {
            "run_id": first_text(row, "source_n4_run_id"),
            "trigger_kind": first_text(row, "trigger_kind"),
            "original_condition_key": first_text(row, "original_condition_key"),
            "primary_trigger_period": first_text(row, "primary_trigger_period"),
        },
        "N5": {
            "action_run_id": first_text(row, "source_action_run_id"),
            "event_id": first_text(row, "source_event_id"),
            "source_action_event_id": first_text(row, "source_action_event_id"),
            "event_type": first_text(row, "source_action_event_type"),
            "action_state": normalized_action_state(row),
            "action_mark": first_text(row, "action_mark"),
        },
        "N6": {
            "run_id": first_text(row, "user_projection_run_id"),
            "user_signal_projection_id": row.get("user_signal_projection_id"),
            "user_signal_card_id": row.get("user_signal_card_id"),
            "user_notification_queue_id": row.get("user_notification_queue_id"),
            "rollback_safe": bool(row.get("rollback_safe", True)),
        },
    }


def status_labels_for(action_state: str, queue_status: str, rollback_safe: bool) -> list[dict[str, str]]:
    labels = [status_label(action_state)]
    if queue_status and queue_status != "—":
        labels.append(status_label(queue_status))
    if rollback_safe:
        labels.append(status_label("rollback_safe"))
    return labels


def status_label(status: str) -> dict[str, str]:
    return dict(STATUS_LABELS.get(status, {"label": status or "unknown", "text": status or "未知", "tone": "muted"}))


def normalized_action_state(row: dict[str, Any]) -> str:
    value = str(row.get("action_state") or row.get("card_status") or "").strip()
    if value == "action_confirmed":
        return "executed"
    if value:
        return value
    event_type = str(row.get("source_action_event_type") or "")
    if event_type == "ActionBlocked":
        return "blocked"
    if event_type == "ActionExecuted":
        return "executed"
    if event_type == "ActionEligible":
        return "eligible"
    if event_type == "ActionSkipped":
        return "skipped"
    return "unknown"


def safe_blocked_reason(value: Any) -> str:
    reason = str(value or "").strip()
    if not reason:
        return "—"
    if reason in FORBIDDEN_USER_LAYER_REASONS:
        return "—"
    if reason not in APPROVED_BLOCKED_REASONS:
        return "—"
    return reason


def sanitize_provider_payload(value: Any) -> tuple[dict[str, Any], set[str]]:
    sanitized, dropped = sanitize_payload_value(as_mapping(value))
    return as_mapping(sanitized), dropped


def sanitize_payload_value(value: Any) -> tuple[Any, set[str]]:
    dropped: set[str] = set()
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if text_key in FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
                dropped.add(text_key)
                continue
            sanitized_item, child_dropped = sanitize_payload_value(item)
            dropped.update(child_dropped)
            result[text_key] = sanitized_item
        return result, dropped
    if isinstance(value, list):
        result_list = []
        for item in value:
            sanitized_item, child_dropped = sanitize_payload_value(item)
            dropped.update(child_dropped)
            result_list.append(sanitized_item)
        return result_list, dropped
    return json_safe_value(value), dropped


def as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_text(row: dict[str, Any], key: str, *, default: Any = "—") -> str:
    value = row.get(key)
    if value is None or value == "":
        value = default
    if value is None or value == "":
        return "—"
    return str(value)


def first_present_text(row: dict[str, Any], *keys: str, default: Any = "—") -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return str(value)
    if default is None or default == "":
        return "—"
    return str(default)


def display_periods_text(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ",".join(items) if items else "—"
    text = str(value).strip()
    if not text:
        return "—"
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return text
        if isinstance(parsed, list):
            items = [str(item).strip() for item in parsed if str(item).strip()]
            return ",".join(items) if items else "—"
    return text


def number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def display_datetime(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    return str(value)


def display_payload_datetime(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return display_datetime(value)
    text = str(value).strip()
    if not text:
        return ""
    normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def compact_trade_date_input(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    return ""


def compact_trade_date_display(value: Any) -> str:
    return compact_trade_date_input(value) or first_text({"value": value}, "value")


def json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return display_datetime(value)
    if isinstance(value, Decimal):
        return float(value)
    return value
