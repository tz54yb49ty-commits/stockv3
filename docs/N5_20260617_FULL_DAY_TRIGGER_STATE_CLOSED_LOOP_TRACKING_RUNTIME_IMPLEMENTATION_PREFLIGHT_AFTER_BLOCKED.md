# N5 Tracking Runtime Implementation Preflight

Result: `PREFLIGHT_PASS`

## Scope

- Layer: `N5_action`
- Operation: implementation preflight only
- Tracking table: `common_action_tracking_state`
- Source trigger run: `trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- Planned action run: `action_consumer_dry_run_20260617_full_day_state_closed_loop__trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`

## Blocked Artifact Proof

- Prior runtime preflight result: `BLOCKED`
- Blockers:
  - `tracking_state_persistence_not_implemented`
  - `tracking_state_unique_key_duplicate_plan`
- Duplicate evidence: `1661` planned create rows, `216` distinct state keys, `1445` duplicate extra rows.

## Upsert/Dedup Contract

- Tracking identity is `(run_id, state_key)`.
- `state_key` must include `trade_date`, `asset_kind`, `identity_key`, `direction`, `signal_type`, and `condition_key`.
- `TriggerMatched` is the only source event type that may create action confirmation facts/events.
- Repeated `TriggerMatched` rows for the same `(run_id,state_key)` must update the tracking row instead of inserting duplicates.
- `TriggerStateChanged` never creates action confirmation from scratch.
- `TriggerStateChanged(trigger_live=false)` may expire only unfinished tracking.
- `TriggerPendingMarketData` remains quality/no-op and writes no action fact or tracking state.
- `executed` must not be downgraded by later blocked/state-gate rows; a later confirmed `TriggerMatched` may upgrade a non-executed tracking row to `executed`.

## Implementation Plan

- `src/ashare_v3/action/dry_run.py`
  - Mark duplicate `TriggerMatched` state keys as tracking updates rather than repeated creates.
  - Keep duplicate event-id idempotency unchanged.
- `src/ashare_v3/action/run_once_dry_run.py`
  - Surface deduped tracking insert/update/expire counts.
- `src/ashare_v3/action/execute.py`
  - Add `upsert_action_tracking_states`.
  - Use `INSERT ... ON CONFLICT (run_id,state_key) DO UPDATE`.
  - Call it inside `execute_action_transaction` in the same transaction as N5 facts/events.
  - Do not touch N4 outbox status.
- Tests
  - Add planner and execute tests for duplicate state-key dedup, pending no-op, ON CONFLICT SQL, terminal precedence, and inserted count reporting.

## Rollback Plan

- Rollback SQL draft: `sql/N5_20260617_full_day_trigger_state_closed_loop_tracking_runtime_rollback.sql`
- Scope: exact `planned_action_run_id` and `source_trigger_run_id`.
- Expected future delete upper bound: `216` tracking rows.
- Hard-fail if target `run_id` rows reference a different `source_trigger_run_id`.
- Does not touch N4 outbox, N5 action facts/events/outbox/inbox/checkpoint, N6, voice/mobile/sim/position/order, real trade, or old system tables.

## Forbidden Scope Proof

- No N5 runtime executed.
- `common_action_tracking_state` was not written.
- No N4 outbox consumed or updated.
- No inbox/checkpoint written.
- No N6 entered.
- No worker/scheduler started.
- No voice/mobile/sim/position/order/real trade/old system touched.

## Allowed Next Prompt

```text
layer_role=N5_action.
Enter N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_TRACKING_RUNTIME_IMPLEMENT_AFTER_PREFLIGHT_PASS.

Use:
- implementation_preflight_artifact=docs/N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_TRACKING_RUNTIME_IMPLEMENTATION_PREFLIGHT_AFTER_BLOCKED.json
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- planned_action_run_id=action_consumer_dry_run_20260617_full_day_state_closed_loop__trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- tracking_table=common_action_tracking_state
- rollback_sql_path=sql/N5_20260617_full_day_trigger_state_closed_loop_tracking_runtime_rollback.sql

Task:
Implement N5-only tracking-state persistence/upsert/dedup code and tests only.

Forbidden:
- Do not execute N5 runtime.
- Do not consume/update N4 outbox.
- Do not enter N6.
- Do not start worker/scheduler.
- Do not touch voice/mobile/sim/position/order/real trade/old system.
```

