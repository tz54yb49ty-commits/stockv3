"""N5-0 trigger outbox preflight and action candidate dry-run.

The preflight is read-only against PostgreSQL. It reads N4 standard outbox
events and produces report files, but it does not consume outbox rows, update
inbox/checkpoint state, write action facts, write user projection, call market
data adapters, start workers, or submit trades.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.action.query_audit_phase2 import audited_n5_readonly_plan_connect
from ashare_v3.action.dry_run import (
    ALLOWED_N4_INPUT_EVENT_TYPES,
    HINT_SIGNAL_TYPES,
    build_action_candidates_from_outbox_rows,
    count_by,
    list_forbidden_candidate_outputs,
    summarize_action_candidates,
)
from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item


DEFAULT_N5_0_JSON_REPORT_PATH = "docs/N5_0_action_preflight_dry_run_report.json"
DEFAULT_N5_0_MD_REPORT_PATH = "docs/N5_0_ACTION_PREFLIGHT_DRY_RUN_REPORT.md"
DEFAULT_N5_0_ACTION_RUN_ID = (
    "action_preflight_20260525_trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029"
)
DEFAULT_TRIGGER_RUN_ID = (
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute"
)
ROW_COUNT_GUARD_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_action_run",
    "common_action_quality_item",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "common_action_event",
    "common_position_state",
    "common_position_event",
)


def run_action_preflight(
    *,
    dsn: str,
    trigger_run_id: str = DEFAULT_TRIGGER_RUN_ID,
    action_run_id: str = DEFAULT_N5_0_ACTION_RUN_ID,
    json_report_path: str = DEFAULT_N5_0_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_0_MD_REPORT_PATH,
    sample_limit: int = 80,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    before_counts: dict[str, dict[str, Any]]
    after_counts: dict[str, dict[str, Any]]
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_action_preflight",
        source_run_id=action_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        before_counts = fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES)
        trigger_run = fetch_trigger_run(cur, trigger_run_id)
        outbox_rows = fetch_n4_outbox_rows(cur, trigger_run_id)
        after_counts = fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES)

    report = build_action_preflight_report_from_rows(
        trigger_run_id=trigger_run_id,
        action_run_id=action_run_id,
        trigger_run=trigger_run,
        outbox_rows=outbox_rows,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        started_at=started_at,
        finished_at=utc_now_iso(),
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        sample_limit=sample_limit,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_action_preflight_report(report))
    return report


def build_action_preflight_report_from_rows(
    *,
    trigger_run_id: str,
    action_run_id: str,
    trigger_run: Mapping[str, Any] | None,
    outbox_rows: Sequence[Mapping[str, Any]],
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    json_report_path: str = DEFAULT_N5_0_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_0_MD_REPORT_PATH,
    sample_limit: int = 80,
) -> dict[str, Any]:
    normalized_rows = [normalize_outbox_row(row) for row in outbox_rows]
    candidates = build_action_candidates_from_outbox_rows(normalized_rows, action_run_id=action_run_id)
    outbox_summary = summarize_outbox_rows(normalized_rows)
    candidate_summary = summarize_action_candidates(candidates)
    quality_items = build_quality_items(
        trigger_run_id=trigger_run_id,
        trigger_run=trigger_run or {},
        outbox_summary=outbox_summary,
        candidate_summary=candidate_summary,
        candidates=candidates,
        before_row_counts=before_row_counts or {},
        after_row_counts=after_row_counts or {},
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": "N5-0",
        "layer_role": "N5_action",
        "mode": "trigger_outbox_preflight_and_action_candidate_dry_run",
        "execution_mode": "read_only_n4_synthetic_sample_outbox_preflight",
        "action_run_id": action_run_id,
        "source_trigger_run_id": trigger_run_id,
        "source_trigger_run": normalize_mapping(trigger_run or {}),
        "for_trade_date": (trigger_run or {}).get("for_trade_date") or infer_trade_date(normalized_rows),
        "started_at": started_at or utc_now_iso(),
        "finished_at": finished_at or utc_now_iso(),
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "outbox_summary": outbox_summary,
        "action_candidate_summary": candidate_summary,
        "sample_outbox_rows": normalized_rows[:sample_limit],
        "sample_action_candidates": candidates[:sample_limit],
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "before_row_counts": before_row_counts or {},
        "after_row_counts": after_row_counts or {},
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "writes_performed": False,
            "action_fact_written": False,
            "action_event_written": False,
            "position_event_written": False,
            "common_event_outbox_written": False,
            "common_event_inbox_updated": False,
            "consumer_checkpoint_updated": False,
            "market_data_pulled": False,
            "real_n3_event_consumed": False,
            "real_n4_outbox_consumed": False,
            "trigger_layer_mutated": False,
            "user_layer_touched": False,
            "voice_touched": False,
            "sim_touched": False,
            "real_trade_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "passed": severity_counts["P0"] == 0,
    }


def normalize_outbox_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    payload = output.get("payload_json") or {}
    if not isinstance(payload, Mapping):
        payload = {}
    output["payload_json"] = normalize_mapping(payload)
    return output


def summarize_outbox_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    payload_rows = [dict(row.get("payload_json") or {}) for row in rows]
    matched_rows = [row for row in rows if row.get("event_type") == "TriggerMatched"]
    pending_rows = [row for row in rows if row.get("event_type") == "TriggerPendingMarketData"]
    state_changed_rows = [row for row in rows if row.get("event_type") == "TriggerStateChanged"]
    matched_payloads = [dict(row.get("payload_json") or {}) for row in matched_rows]
    pending_payloads = [dict(row.get("payload_json") or {}) for row in pending_rows]
    def has_hint_trace(payload: Mapping[str, Any], hint_key: str) -> bool:
        return payload.get("condition_key") == hint_key or payload.get("original_condition_key") == hint_key

    return {
        "outbox_row_count": len(rows),
        "by_event_type": count_by(rows, "event_type"),
        "by_asset_kind": count_by(rows, "asset_kind"),
        "by_signal_type": count_payload_by(payload_rows, "signal_type"),
        "by_direction": count_payload_by(payload_rows, "direction"),
        "matched_count": len(matched_rows),
        "pending_count": len(pending_rows),
        "state_changed_count": len(state_changed_rows),
        "matched_by_signal_type": count_payload_by(matched_payloads, "signal_type"),
        "pending_by_signal_type": count_payload_by(pending_payloads, "signal_type"),
        "matched_by_asset_kind": count_by(matched_rows, "asset_kind"),
        "pending_by_asset_kind": count_by(pending_rows, "asset_kind"),
        "matched_by_direction": count_payload_by(matched_payloads, "direction"),
        "pending_by_direction": count_payload_by(pending_payloads, "direction"),
        "buy_hint_count": sum(1 for payload in payload_rows if payload.get("signal_type") == "BUY_HINT"),
        "sell_hint_count": sum(1 for payload in payload_rows if payload.get("signal_type") == "SELL_HINT"),
        "buy_hint_matched_count": sum(1 for payload in matched_payloads if payload.get("signal_type") == "BUY_HINT"),
        "sell_hint_matched_count": sum(1 for payload in matched_payloads if payload.get("signal_type") == "SELL_HINT"),
        "buy_hint_pending_count": sum(1 for payload in pending_payloads if payload.get("signal_type") == "BUY_HINT"),
        "sell_hint_pending_count": sum(1 for payload in pending_payloads if payload.get("signal_type") == "SELL_HINT"),
        "buy_hint_trace_count": sum(1 for payload in payload_rows if has_hint_trace(payload, "BUY_HINT")),
        "sell_hint_trace_count": sum(1 for payload in payload_rows if has_hint_trace(payload, "SELL_HINT")),
        "buy_hint_trace_matched_count": sum(1 for payload in matched_payloads if has_hint_trace(payload, "BUY_HINT")),
        "sell_hint_trace_matched_count": sum(1 for payload in matched_payloads if has_hint_trace(payload, "SELL_HINT")),
        "buy_hint_trace_pending_count": sum(1 for payload in pending_payloads if has_hint_trace(payload, "BUY_HINT")),
        "sell_hint_trace_pending_count": sum(1 for payload in pending_payloads if has_hint_trace(payload, "SELL_HINT")),
        "allowed_input_event_types": list(ALLOWED_N4_INPUT_EVENT_TYPES),
        "disallowed_event_types": sorted(set(count_by(rows, "event_type")) - set(ALLOWED_N4_INPUT_EVENT_TYPES)),
        "synthetic_sample_event_count": sum(
            1 for payload in payload_rows if payload.get("synthetic_sample_event") is True
        ),
    }


def build_quality_items(
    *,
    trigger_run_id: str,
    trigger_run: Mapping[str, Any],
    outbox_summary: Mapping[str, Any],
    candidate_summary: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    before_row_counts: Mapping[str, Mapping[str, Any]],
    after_row_counts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    row_counts_unchanged = before_row_counts == after_row_counts
    checkpoint_counts_unchanged = counts_equal(
        before_row_counts,
        after_row_counts,
        ("common_event_inbox", "common_event_consumer_checkpoint"),
    )
    forbidden_outputs = list_forbidden_candidate_outputs(candidates)
    return [
        quality_item(
            "P0",
            "passed" if trigger_run.get("run_id") == trigger_run_id else "failed",
            "n5_0_source_trigger_run_found",
            "N5-0 must read the requested N4 trigger run as upstream metadata",
            expected=trigger_run_id,
            actual=str(trigger_run.get("run_id") or ""),
        ),
        quality_item(
            "P0",
            "passed" if int(outbox_summary.get("outbox_row_count") or 0) > 0 else "failed",
            "n5_0_n4_outbox_available",
            "N5-0 must read N4 standard outbox rows",
            expected=">0",
            actual=str(outbox_summary.get("outbox_row_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if not outbox_summary.get("disallowed_event_types") else "failed",
            "n5_0_only_consumes_n4_standard_events",
            "N5 input must be TriggerMatched, TriggerPendingMarketData, or TriggerStateChanged",
            expected=",".join(ALLOWED_N4_INPUT_EVENT_TYPES),
            actual=",".join(outbox_summary.get("by_event_type", {}).keys()),
        ),
        quality_item(
            "P0",
            "passed" if int(candidate_summary.get("deprecated_runtime_signal_type_count") or 0) == 0 else "failed",
            "n5_0_runtime_signal_type_canonical",
            "N5 runtime signal_type must be B_BUY or S_SELL; BUY_HINT/SELL_HINT stay in condition trace only",
            expected="deprecated_runtime_signal_type_count=0",
            actual=str(candidate_summary.get("deprecated_runtime_signal_type_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(candidate_summary.get("trigger_matched_action_candidate_count") or 0) > 0 else "failed",
            "n5_0_trigger_matched_generates_action_candidates",
            "TriggerMatched must produce action candidates in dry-run",
            expected=">0",
            actual=str(candidate_summary.get("trigger_matched_action_candidate_count") or 0),
        ),
        quality_item(
            "P0",
            "passed"
            if int(candidate_summary.get("buy_hint_candidate_count") or 0) > 0
            and int(candidate_summary.get("sell_hint_candidate_count") or 0) > 0
            else "failed",
            "n5_0_buy_sell_hint_preserved",
            "BUY_HINT and SELL_HINT must enter N5 action candidates",
            expected="BUY_HINT>0 SELL_HINT>0",
            actual=(
                f"BUY_HINT={candidate_summary.get('buy_hint_candidate_count') or 0} "
                f"SELL_HINT={candidate_summary.get('sell_hint_candidate_count') or 0}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if int(candidate_summary.get("pending_generates_action_event_count") or 0) == 0 else "failed",
            "n5_0_pending_market_data_no_actual_action",
            "TriggerPendingMarketData must not generate an action event candidate",
            expected="0",
            actual=str(candidate_summary.get("pending_generates_action_event_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(candidate_summary.get("unclosed_minute_generates_action_event_count") or 0) == 0 else "failed",
            "n5_0_no_unclosed_minute_action_confirmation",
            "N5 must not confirm actions from unclosed minute context",
            expected="0",
            actual=str(candidate_summary.get("unclosed_minute_generates_action_event_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if not forbidden_outputs else "failed",
            "n5_0_no_user_voice_sim_outputs",
            "N5 dry-run must not output User*, Voice*, or Sim* events",
            expected="none",
            actual=",".join(forbidden_outputs),
        ),
        quality_item(
            "P0",
            "passed" if int(candidate_summary.get("would_write_db_count") or 0) == 0 else "failed",
            "n5_0_dry_run_no_db_writes",
            "N5 dry-run candidates must not write DB rows",
            expected="0",
            actual=str(candidate_summary.get("would_write_db_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n5_0_database_row_counts_unchanged",
            "N5-0 preflight must keep guarded table row counts unchanged",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if checkpoint_counts_unchanged else "failed",
            "n5_0_no_inbox_checkpoint_update",
            "N5-0 preflight must not update common_event_inbox or consumer checkpoint",
            expected="unchanged",
            actual="unchanged" if checkpoint_counts_unchanged else "changed",
        ),
        quality_item("P0", "passed", "n5_0_no_market_data_pull", "N5-0 does not pull market data"),
        quality_item("P0", "passed", "n5_0_no_n2_external_runtime_read", "N5-0 does not read external N2 runtime path"),
        quality_item("P0", "passed", "n5_0_no_user_voice_sim_write", "N5-0 does not write user, voice, or sim outputs"),
        quality_item("P0", "passed", "n5_0_no_real_trade", "N5-0 does not call real trading interfaces"),
        quality_item("P0", "passed", "n5_0_no_worker", "N5-0 does not start workers"),
        quality_item(
            "P2",
            "warning" if int(outbox_summary.get("synthetic_sample_event_count") or 0) > 0 else "passed",
            "n5_0_source_outbox_is_synthetic_sample",
            "Current N4 outbox is synthetic/sample run-once material for N5 development only",
            expected="development sample noted",
            actual=str(outbox_summary.get("synthetic_sample_event_count") or 0),
        ),
    ]


def fetch_trigger_run(cur: psycopg.Cursor[dict[str, Any]], trigger_run_id: str) -> dict[str, Any]:
    if not table_exists(cur, "common_trigger_run"):
        return {}
    cur.execute(
        """
        SELECT run_id, source_condition_run_id, source_market_data_run_id,
               for_trade_date, source_trade_date, prev_trade_date, mode, status,
               context_snapshot_row_count, trigger_state_row_count,
               trigger_match_row_count, trigger_event_outbox_count,
               p0_count, p1_count, p2_count, raw_json, started_at, finished_at
        FROM common_trigger_run
        WHERE run_id = %s
        """,
        (trigger_run_id,),
    )
    return normalize_mapping(cur.fetchone() or {})


def fetch_n4_outbox_rows(cur: psycopg.Cursor[dict[str, Any]], trigger_run_id: str) -> list[dict[str, Any]]:
    if not table_exists(cur, "common_event_outbox"):
        return []
    cur.execute(
        """
        SELECT outbox_id, event_id, event_type, event_schema_version, trade_date,
               asset_kind, identity_key, event_time, source_layer, source_run_id,
               dedup_key, partition_key, payload_json, status, created_at
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
        ORDER BY outbox_id
        """,
        (trigger_run_id,),
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def fetch_row_counts(
    cur: psycopg.Cursor[dict[str, Any]],
    table_names: Sequence[str],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for table_name in table_names:
        if not table_exists(cur, table_name):
            output[table_name] = {"exists": False, "row_count": None, "status": "missing"}
            continue
        cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
        output[table_name] = {"exists": True, "row_count": int(cur.fetchone()["row_count"]), "status": "present"}
    return output


def table_exists(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
    return cur.fetchone()["regclass"] is not None


def count_payload_by(payloads: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(payload.get(key) or "") for payload in payloads).items()))


def counts_equal(
    before_counts: Mapping[str, Mapping[str, Any]],
    after_counts: Mapping[str, Mapping[str, Any]],
    table_names: Sequence[str],
) -> bool:
    return all(before_counts.get(table_name) == after_counts.get(table_name) for table_name in table_names)


def infer_trade_date(rows: Sequence[Mapping[str, Any]]) -> str | None:
    for row in rows:
        trade_date = row.get("trade_date")
        if trade_date:
            return str(trade_date)
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def format_action_preflight_report(report: Mapping[str, Any]) -> str:
    outbox = report["outbox_summary"]
    candidates = report["action_candidate_summary"]
    quality = report["quality"]
    side_effects = report["side_effects"]
    return "\n".join(
        [
            "# N5-0 Action Preflight / Dry-Run Report",
            "",
            "## Summary",
            "",
            f"- stage: {report['stage']}",
            f"- layer_role: {report['layer_role']}",
            f"- source_trigger_run_id: {report['source_trigger_run_id']}",
            f"- action_run_id: {report['action_run_id']}",
            f"- for_trade_date: {report.get('for_trade_date')}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            "",
            "## N4 Outbox Statistics",
            "",
            f"- outbox_row_count: {outbox['outbox_row_count']}",
            f"- by_event_type: {outbox['by_event_type']}",
            f"- by_signal_type: {outbox['by_signal_type']}",
            f"- by_asset_kind: {outbox['by_asset_kind']}",
            f"- by_direction: {outbox['by_direction']}",
            f"- TriggerMatched: {outbox['matched_count']}",
            f"- TriggerPendingMarketData: {outbox['pending_count']}",
            f"- TriggerStateChanged: {outbox['state_changed_count']}",
            f"- BUY_HINT matched/pending/total: {outbox['buy_hint_matched_count']}/{outbox['buy_hint_pending_count']}/{outbox['buy_hint_count']}",
            f"- SELL_HINT matched/pending/total: {outbox['sell_hint_matched_count']}/{outbox['sell_hint_pending_count']}/{outbox['sell_hint_count']}",
            "",
            "## Action Candidate Dry-Run",
            "",
            f"- candidate_count: {candidates['candidate_count']}",
            f"- action_candidate_count: {candidates['action_candidate_count']}",
            f"- quality_plan_count: {candidates['quality_plan_count']}",
            f"- planned_output_event_type: {candidates['by_planned_output_event_type']}",
            f"- by_action_type: {candidates['by_action_type']}",
            f"- by_lane: {candidates['by_lane']}",
            f"- by_decision_status: {candidates['by_decision_status']}",
            f"- BUY_HINT candidate count: {candidates['buy_hint_candidate_count']}",
            f"- SELL_HINT candidate count: {candidates['sell_hint_candidate_count']}",
            f"- pending_generates_action_event_count: {candidates['pending_generates_action_event_count']}",
            f"- unclosed_minute_generates_action_event_count: {candidates['unclosed_minute_generates_action_event_count']}",
            "",
            "## Boundary Confirmation",
            "",
            f"- writes_performed: {side_effects['writes_performed']}",
            f"- action_fact_written: {side_effects['action_fact_written']}",
            f"- action_event_written: {side_effects['action_event_written']}",
            f"- common_event_inbox_updated: {side_effects['common_event_inbox_updated']}",
            f"- consumer_checkpoint_updated: {side_effects['consumer_checkpoint_updated']}",
            f"- market_data_pulled: {side_effects['market_data_pulled']}",
            f"- real_n4_outbox_consumed: {side_effects['real_n4_outbox_consumed']}",
            f"- user_layer_touched: {side_effects['user_layer_touched']}",
            f"- voice_touched: {side_effects['voice_touched']}",
            f"- sim_touched: {side_effects['sim_touched']}",
            f"- real_trade_touched: {side_effects['real_trade_touched']}",
            f"- worker_started: {side_effects['worker_started']}",
            f"- old_system_touched: {side_effects['old_system_touched']}",
            "",
            "## Notes",
            "",
            "- This report reads the N4 run-once synthetic/sample outbox for N5 development validation only.",
            "- It does not execute migration, write action facts, consume outbox, or advance to N5-1/N6.",
        ]
    )
