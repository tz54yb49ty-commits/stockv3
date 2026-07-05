# N5 Full-Day Tracking Runtime Preflight

Result: `BLOCKED`

## Scope

- Layer: `N5_action`
- Source trigger run: `trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- Planned action run: `action_consumer_dry_run_20260617_full_day_state_closed_loop__trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- Tracking table: `common_action_tracking_state`

## Schema Proof

- Schema post-review: `SCHEMA_EXECUTE_PASS`
- `common_action_tracking_state` exists.
- `trade_date` and `state_key` exist.
- Unique key exists: `UNIQUE (run_id, state_key)`.
- Current tracking table row count: `0`.

## Runtime Plan Proof

- Action-entry mode reads only `TriggerMatched=1661`.
- `TriggerPendingMarketData=1017925` remains no-op and is not loaded as action entry/state gate.
- State-gate mode reads `TriggerStateChanged=13046`.
- State-gate creates `0` action facts from scratch.
- Planned action facts from `TriggerMatched`: `1661`.
- Planned output events from `TriggerMatched`: `ActionBlocked=1450`, `ActionExecuted=211`.
- Closed-loop tracking plan: create `1661`, update `1006`, expire `0`.

## Blockers

1. `tracking_state_persistence_not_implemented`

   Static code search found tracking-state persistence only in dry-run/planner code. `src/ashare_v3/action/execute.py` has no write path for `common_action_tracking_state`.

2. `tracking_state_unique_key_duplicate_plan`

   The `TriggerMatched` tracking plan has `1661` create rows but only `216` distinct `state_key` values. There are `205` duplicate state-key groups and `1445` duplicate extra rows under `UNIQUE(run_id,state_key)`.

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
Enter N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_TRACKING_RUNTIME_IMPLEMENTATION_PREFLIGHT_AFTER_BLOCKED.

Use:
- blocked_runtime_preflight_artifact=docs/N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_RUNTIME_PREFLIGHT_AFTER_TRACKING_SCHEMA_PASS.json
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- planned_action_run_id=action_consumer_dry_run_20260617_full_day_state_closed_loop__trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- tracking_table=common_action_tracking_state

Task:
Prepare N5-only runtime implementation preflight for tracking-state persistence with explicit upsert/dedup semantics for UNIQUE(run_id,state_key), rollback plan, and tests.

Forbidden:
- Do not execute N5 runtime.
- Do not consume/update N4 outbox.
- Do not enter N6.
- Do not start worker/scheduler.
- Do not touch voice/mobile/sim/position/order/real trade/old system.
```

