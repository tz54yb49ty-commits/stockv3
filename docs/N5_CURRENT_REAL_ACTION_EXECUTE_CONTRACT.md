# N5 Current-Real Action Execute Contract

## Summary

- stage: N5 current-real action execute runner implementation
- layer_role: N5_action
- runner_mode: run_once
- source_trigger_run_id: trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
- action_run_id: action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
- consumer_name: n5_action_consumer_v1
- implementation_status: ready for execute preflight refresh

## Execute Gates

- Must pass both CLI flags: `--execute` and `--user-confirmed`.
- Missing either flag blocks before any database write.
- The runner is run-once only and does not start a worker.

## Source Guards

- allowlist:
  - trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
- denylist:
  - trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
  - trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute
- Input query must use `source_layer='N4_trigger'`, the current real source_run_id, and `status='pending'`.
- Delivered, delivering, failed, dead-letter, archived, or any other non-pending rows are not consumable by this runner.

## Input Mapping

- `TriggerMatched` -> action fact + `common_action_event` + N5 `common_event_outbox`.
- `TriggerPendingMarketData` -> `common_action_quality_item` only.
- `TriggerPendingMarketData` must not generate action fact, `common_action_event`, or N5 outbox event.
- Current-real expected input:
  - read_event_count: 764
  - TriggerMatched: 488
  - TriggerPendingMarketData: 276

## Output Mapping

- `B_BUY_30M_VOL` -> `ActionEvent`
- `S_SELL_30M_SHRINK` -> `ActionEvent`
- `BUY_HINT` -> `HintEvent`
- `SELL_HINT` -> `HintEvent`
- Current-real expected output:
  - action fact: 488
  - quality only: 276
  - ActionEvent: 479
  - HintEvent: 9
  - RiskEvent: 0
  - PositionEvent: 0

## Planned Write Scope

- `common_action_run`: 1
- `common_action_quality_item`: 276
- `stock_action_fact`: 488
- `index_action_fact`: 0
- `board_action_fact`: 0
- `common_action_event`: 488
- `common_event_outbox`: 488
- `common_event_inbox`: 764
- `common_event_consumer_checkpoint`: 615

Forbidden writes:

- `common_position_state`
- `common_position_event`
- user projection
- voice/mobile
- sim
- real trade/order
- N2/N3/N4 facts
- old synthetic outbox

## Idempotency

- Existing `common_event_inbox(consumer_name, event_id)` rows skip repeat consumption.
- Action facts keep `UNIQUE(run_id, action_key)` and `UNIQUE(run_id, dedup_key)`.
- `common_action_event` keeps `UNIQUE(run_id, action_key)` and `UNIQUE(run_id, dedup_key)`.
- N5 outbox uses stable event id and common outbox dedup constraints.
- Checkpoint updates only advance when the incoming `last_outbox_id` is greater.

## Rollback

- rollback_sql_path: `sql/N5_current_real_action_execute_rollback.sql`
- rollback scope is limited to:
  - `action_run_id`
  - `source_trigger_run_id`
  - `consumer_name`
- Rollback deletes N5 outbox, `common_action_event`, action fact tables, quality rows, N5 consumer inbox/checkpoint, and `common_action_run`.
- Rollback does not touch N4 trigger facts, N4 outbox status, N3 facts, N6/user, voice, sim, mobile, or true-trade tables.

## Boundary Confirmation

- No execute was run while creating this contract.
- No N4 outbox was consumed.
- No inbox/checkpoint/action fact/N5 outbox rows were written.
- No position, sim, voice/mobile/N6, real trade, worker, N2/N3/N4 facts, or old system state was touched.
