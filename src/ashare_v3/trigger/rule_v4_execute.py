"""Run-once execute planning for N4 trigger rule spec v4.

The module deliberately separates pure execute planning from database writes.
It only persists rows whose v4 dry-run outcome is a valid N5-entry matched
trigger. Other v4 outcomes remain visible in reports/quality summaries until a
dedicated v4 audit schema is approved.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.events.ids import build_stable_event_id
from ashare_v3.events.models import DEFAULT_EVENT_SCHEMA_VERSION, N4_SOURCE_LAYER
from ashare_v3.trigger.rule_v4_matcher import RUNTIME_SIGNAL_TYPES, TRIGGER_RULE_POLICY_HASH, TRIGGER_RULE_SPEC_VERSION
from ashare_v3.trigger.standard_trigger_execute import (
    assert_no_existing_execute_outputs,
    build_execute_dedup_key,
    build_execute_event_envelope,
    insert_execute_match,
    insert_execute_quality_items,
    insert_outbox_envelope,
    jsonb,
    schema_data_quality_status,
    update_execute_state_last_match,
    upsert_execute_state,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_trigger_connect
from ashare_v3.trigger.v4_enforcement import V4EnforcementBlocked, assert_v4_write_plan_enforceable


class V4TriggerExecuteBlocked(RuntimeError):
    """Raised when v4 execute must stop before any write."""


class V4OutcomePersistenceStrategy:
    MATCHED_ONLY = "matched_only"


ALLOWED_V4_EXECUTE_WRITE_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
)

FORBIDDEN_V4_EXECUTE_WRITE_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "N2 condition tables",
    "N3 snapshot/projection/minute facts",
    "N5/N6/action/user/voice/mobile/sim/position/real-trade tables",
    "worker state",
)

SUPPORTED_PERSISTED_OUTCOMES = ("matched",)
BJ_QUALITY_VISIBLE_IDENTITIES = {"index:BJ:899050", "index:BJ:899601"}


@dataclass(frozen=True)
class V4ExecuteLineage:
    execute_run_id: str
    trigger_context_run_id: str
    snapshot_run_id: str
    source_condition_run_id: str
    for_trade_date: str


def assert_v4_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    """Block before writes unless both explicit execute confirmations are present."""

    if not execute:
        raise V4TriggerExecuteBlocked("N4 v4 execute blocked before writes: missing --execute")
    if not user_confirmed:
        raise V4TriggerExecuteBlocked("N4 v4 execute blocked before writes: missing --user-confirmed")


def is_valid_n5_entry(plan: Mapping[str, Any]) -> bool:
    return (
        plan.get("output_event_type") == "TriggerMatched"
        and plan.get("signal_type") in RUNTIME_SIGNAL_TYPES
        and plan.get("outcome_classification") == "matched"
        and plan.get("trigger_live") is True
        and plan.get("n5_entry_allowed") is True
    )


def build_v4_execute_write_plan(
    plans: Sequence[Mapping[str, Any]],
    *,
    execute_run_id: str,
    trigger_context_run_id: str,
    snapshot_run_id: str,
) -> dict[str, Any]:
    """Return the v4 matched-only write plan without touching the database."""

    outcome_counts = Counter(str(plan.get("outcome_classification")) for plan in plans)
    invalid_n5_entry_plans = [
        dict(plan)
        for plan in plans
        if plan.get("n5_entry_allowed") is True and not is_valid_n5_entry(plan)
    ]
    matched_write_plans = [
        normalize_v4_plan_for_standard_persistence(plan)
        for plan in plans
        if is_valid_n5_entry(plan)
    ]
    full_blocked_count = sum(
        1
        for plan in plans
        if plan.get("condition_key") in {"BUY:FULL", "SELL:FULL"}
        and plan.get("outcome_classification") == "quality_blocked"
    )
    bj_quality_blocked_count = sum(
        1
        for plan in plans
        if is_bj_quality_visible_identity(plan.get("identity_key"))
        and plan.get("outcome_classification") == "quality_blocked"
    )
    event_counts = Counter(str(plan.get("output_event_type")) for plan in matched_write_plans)
    return {
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "snapshot_run_id": snapshot_run_id,
        "trigger_rule_spec_version": TRIGGER_RULE_SPEC_VERSION,
        "trigger_rule_policy_hash": TRIGGER_RULE_POLICY_HASH,
        "outcome_persistence_strategy": V4OutcomePersistenceStrategy.MATCHED_ONLY,
        "strategy_reason": (
            "common_trigger_state current_status does not support no_op/quality_blocked; "
            "v4 execute persists only valid matched N5-entry rows and keeps all other "
            "outcomes in execute reports/quality summaries."
        ),
        "allowed_write_tables": list(ALLOWED_V4_EXECUTE_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_V4_EXECUTE_WRITE_TABLES),
        "input_plan_count": len(plans),
        "outcome_counts": dict(outcome_counts),
        "persisted_plan_count": len(matched_write_plans),
        "suppressed_counts": {
            "no_op": int(outcome_counts.get("no_op") or 0),
            "quality_blocked": int(outcome_counts.get("quality_blocked") or 0),
            "pending_market_data": int(outcome_counts.get("pending_market_data") or 0),
            "inactive": int(outcome_counts.get("inactive") or 0),
        },
        "write_counts": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": "quality rows only",
            "common_trigger_state": len(matched_write_plans),
            "common_trigger_match": len(matched_write_plans),
            "common_event_outbox": len(matched_write_plans),
            "TriggerMatched": int(event_counts.get("TriggerMatched") or 0),
            "TriggerPendingMarketData": 0,
            "TriggerStateChanged": 0,
        },
        "no_op_writes_trigger_matched": False,
        "quality_blocked_writes_trigger_matched": False,
        "pending_market_data_enters_n5": False,
        "inactive_enters_n5": False,
        "full_blocked_count": full_blocked_count,
        "full_blocked_writes_trigger_matched": False,
        "bj_quality_blocked_count": bj_quality_blocked_count,
        "bj_quality_blocked_visible": bj_quality_blocked_count > 0,
        "invalid_n5_entry_count": len(invalid_n5_entry_plans),
        "invalid_n5_entry_samples": invalid_n5_entry_plans[:10],
        "matched_write_plan_samples": matched_write_plans[:10],
        "matched_write_plans": matched_write_plans,
    }


def normalize_v4_plan_for_standard_persistence(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt a v4 matched plan to the current N4 state/match table contract."""

    trigger_period = (
        plan.get("primary_trigger_period")
        or plan.get("projection_period")
        or "D"
    )
    if trigger_period not in {"Y", "Q", "M", "W", "D", "30m"}:
        trigger_period = "D"
    source_event_id = plan.get("source_event_id")
    if source_event_id is None or str(source_event_id).strip() == "":
        source_event_id = (
            f"v4:{plan.get('source_market_data_run_id') or 'snapshot'}:"
            f"{plan.get('identity_key')}:{plan.get('condition_key')}"
        )
    normalized = dict(plan)
    normalized.update(
        {
            "output_event_type": "TriggerMatched",
            "current_status": "matched",
            "trigger_live": True,
            "trigger_period": str(trigger_period),
            "trigger_bucket": str(plan.get("trigger_bucket") or f"v4:{trigger_period}"),
            "source_event_id": str(source_event_id),
            "source_event_type": str(plan.get("source_event_type") or "MarketSnapshotUpdated"),
            "data_quality_status": schema_data_quality_status(plan.get("data_quality_status")),
            "match_basis": str(plan.get("match_basis") or "v4_context_projection_enrichment"),
        }
    )
    return normalized


def build_v4_quality_items(write_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    invalid_n5_count = int(write_plan.get("invalid_n5_entry_count") or 0)
    full_blocked_count = int(write_plan.get("full_blocked_count") or 0)
    bj_blocked_count = int(write_plan.get("bj_quality_blocked_count") or 0)
    return [
        quality_item(
            "P0",
            "passed" if invalid_n5_count == 0 else "failed",
            "n4_v4_invalid_n5_entry_zero",
            "N5 entry can only come from valid TriggerMatched B_BUY/S_SELL matched live rows",
            expected="0",
            actual=str(invalid_n5_count),
        ),
        quality_item(
            "P0",
            "passed",
            "n4_v4_matched_only_persistence_selected",
            "v4 execute uses matched-only persistence because current state schema does not support no_op/quality_blocked",
            expected=V4OutcomePersistenceStrategy.MATCHED_ONLY,
            actual=str(write_plan.get("outcome_persistence_strategy")),
        ),
        quality_item(
            "P1" if full_blocked_count else "P0",
            "warning" if full_blocked_count else "passed",
            "n4_v4_full_semantic_blocked_visible",
            "BUY:FULL / SELL:FULL rows that fail the D-only whitelist remain visible; compliant FULL may write TriggerMatched",
            expected="0 or visible semantic-blocked rows",
            actual=str(full_blocked_count),
        ),
        quality_item(
            "P0",
            "passed" if bj_blocked_count == 4 else "warning",
            "n4_v4_bj_quality_blocked_visible",
            "BJ quality-visible rows remain blocked; no silent fallback",
            expected="4",
            actual=str(bj_blocked_count),
        ),
    ]


def is_bj_quality_visible_identity(identity_key: Any) -> bool:
    text = str(identity_key or "")
    return text in BJ_QUALITY_VISIBLE_IDENTITIES or text.startswith("stock:BJ:920")


def execute_v4_matched_only_transaction(
    *,
    dsn: str,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    snapshot_run: Mapping[str, Any],
    write_plan: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Persist the already-validated matched-only v4 write plan."""

    plans = list(write_plan.get("matched_write_plans") or [])
    try:
        assert_v4_write_plan_enforceable(write_plan, created_at=datetime.now(timezone.utc))
    except V4EnforcementBlocked as exc:
        raise V4TriggerExecuteBlocked(str(exc)) from exc
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_rule_v4_matched_only_transaction",
        source_run_id=execute_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            assert_no_existing_execute_outputs(cur, execute_run_id)
            insert_v4_trigger_run(
                cur,
                execute_run_id=execute_run_id,
                trigger_context_run=trigger_context_run,
                snapshot_run=snapshot_run,
                input_plan_count=int(write_plan.get("input_plan_count") or len(plans)),
                persisted_plan_count=len(plans),
                quality_items=quality_items,
                write_plan=write_plan,
            )
            quality_count = insert_execute_quality_items(
                cur,
                execute_run_id=execute_run_id,
                source_condition_run_id=str(trigger_context_run.get("source_condition_run_id") or ""),
                for_trade_date=str(trigger_context_run.get("for_trade_date") or snapshot_run.get("for_trade_date") or ""),
                source_trade_date=str(trigger_context_run.get("source_trade_date") or snapshot_run.get("source_trade_date") or ""),
                items=quality_items,
            )
            state_count = 0
            match_count = 0
            outbox_count = 0
            for plan in plans:
                state_id = upsert_execute_state(
                    cur,
                    execute_run_id=execute_run_id,
                    trigger_context_run=trigger_context_run,
                    plan=plan,
                )
                dedup_key = build_execute_dedup_key(execute_run_id=execute_run_id, plan=plan)
                event_id = build_stable_event_id(
                    source_layer=N4_SOURCE_LAYER,
                    event_type="TriggerMatched",
                    source_run_id=execute_run_id,
                    dedup_key=dedup_key,
                    event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
                )
                match_id = insert_execute_match(
                    cur,
                    execute_run_id=execute_run_id,
                    trigger_context_run=trigger_context_run,
                    plan=plan,
                    trigger_state_id=state_id,
                    dedup_key=dedup_key,
                    output_event_id=event_id,
                )
                update_execute_state_last_match(cur, trigger_state_id=state_id, trigger_match_id=match_id)
                envelope = build_execute_event_envelope(
                    execute_run_id=execute_run_id,
                    trigger_context_run=trigger_context_run,
                    plan=plan,
                    trigger_state_id=state_id,
                    trigger_match_id=match_id,
                    output_event_id=event_id,
                    dedup_key=dedup_key,
                )
                insert_outbox_envelope(cur, envelope)
                state_count += 1
                match_count += 1
                outbox_count += 1
            cur.execute(
                """
                UPDATE common_trigger_run
                SET status = 'passed',
                    trigger_state_row_count = %s,
                    trigger_match_row_count = %s,
                    trigger_event_outbox_count = %s,
                    finished_at = now(),
                    updated_at = now()
                WHERE run_id = %s
                """,
                (state_count, match_count, outbox_count, execute_run_id),
            )
        conn.commit()
    return {
        "common_trigger_run": 1,
        "common_trigger_quality_item": quality_count,
        "common_trigger_state": state_count,
        "common_trigger_match": match_count,
        "common_event_outbox": outbox_count,
        "TriggerMatched": outbox_count,
        "TriggerPendingMarketData": 0,
        "TriggerStateChanged": 0,
    }


def insert_v4_trigger_run(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    trigger_context_run: Mapping[str, Any],
    snapshot_run: Mapping[str, Any],
    input_plan_count: int,
    persisted_plan_count: int,
    quality_items: Sequence[Mapping[str, Any]],
    write_plan: Mapping[str, Any],
) -> None:
    severity = count_quality_severities(quality_items)
    cur.execute(
        """
        INSERT INTO common_trigger_run (
          run_id, source_condition_run_id, source_market_data_run_id,
          for_trade_date, source_trade_date, prev_trade_date, mode, status,
          p0_count, p1_count, p2_count, source_condition_row_count,
          context_snapshot_row_count, trigger_state_row_count,
          trigger_match_row_count, trigger_event_outbox_count,
          generated_by, market_data_pulled, action_layer_touched,
          user_layer_touched, voice_touched, sim_touched, real_trade_touched,
          worker_started, raw_json, started_at, updated_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(source_market_data_run_id)s,
          %(for_trade_date)s, %(source_trade_date)s, %(prev_trade_date)s,
          'execute', 'running', %(p0_count)s, %(p1_count)s, %(p2_count)s,
          %(source_condition_row_count)s, 0, 0, 0, 0,
          'trigger_rule_v4_execute', false, false, false, false, false,
          false, false, %(raw_json)s, now(), now()
        )
        """,
        {
            "run_id": execute_run_id,
            "source_condition_run_id": trigger_context_run.get("source_condition_run_id"),
            "source_market_data_run_id": snapshot_run.get("run_id"),
            "for_trade_date": trigger_context_run.get("for_trade_date"),
            "source_trade_date": trigger_context_run.get("source_trade_date"),
            "prev_trade_date": trigger_context_run.get("prev_trade_date") or trigger_context_run.get("source_trade_date"),
            "p0_count": severity["P0"],
            "p1_count": severity["P1"],
            "p2_count": severity["P2"],
            "source_condition_row_count": input_plan_count,
            "raw_json": jsonb(
                {
                    "trigger_rule_spec_version": TRIGGER_RULE_SPEC_VERSION,
                    "trigger_rule_policy_hash": TRIGGER_RULE_POLICY_HASH,
                    "trigger_context_run_id": trigger_context_run.get("run_id"),
                    "snapshot_run_id": snapshot_run.get("run_id"),
                    "outcome_persistence_strategy": write_plan.get("outcome_persistence_strategy"),
                    "input_plan_count": input_plan_count,
                    "persisted_plan_count": persisted_plan_count,
                    "writes_outbox": True,
                    "consumes_n3_outbox": False,
                }
            ),
        },
    )


def build_v4_rollback_sql(execute_run_id: str) -> str:
    return f"""-- N4 trigger rule spec v4 execute rollback.
-- Scope: execute_run_id={execute_run_id}
-- Matched-only v4 persistence rollback. Does not touch N2/N3 facts,
-- v4 dry-run artifacts, trigger context snapshots, N5/N6, or historical runs.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := '{execute_run_id}';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 v4 execute rollback blocked: outbox delivered/delivering refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 v4 execute rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 v4 execute rollback blocked: downstream checkpoint refs = %', v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 execute rollback blocked: N5 action run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 execute rollback blocked: N5 action event refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_projection_run
      WHERE user_projection_run_id = $1
         OR source_action_run_id = $1
         OR source_n5_outbox_range::TEXT LIKE '%' || $1 || '%'
         OR quality_summary_json::TEXT LIKE '%' || $1 || '%'
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 execute rollback blocked: N6 user_projection_run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_projection WHERE raw_json::TEXT LIKE ''%'' || $1 || ''%'''
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 execute rollback blocked: N6 user_signal_projection refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_card WHERE raw_json::TEXT LIKE ''%'' || $1 || ''%'''
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 execute rollback blocked: N6 user_signal_card refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_notification_queue WHERE raw_json::TEXT LIKE ''%'' || $1 || ''%'''
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 v4 execute rollback blocked: N6 user_notification_queue refs = %', v_count;
    END IF;
  END IF;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = '{execute_run_id}';

DELETE FROM common_trigger_match
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_state
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_quality_item
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_run
WHERE run_id = '{execute_run_id}';

COMMIT;
"""
