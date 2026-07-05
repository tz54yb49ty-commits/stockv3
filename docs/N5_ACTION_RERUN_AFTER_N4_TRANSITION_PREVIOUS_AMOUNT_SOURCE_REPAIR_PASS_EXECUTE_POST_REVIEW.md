# N5 Action Execute Post-Review

Result: PASS / EXECUTED

- layer_role: N5_action
- trade_date: 20260617
- action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_trigger_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_metric_run_id: `action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- rollback SQL: `sql/N5_action_rerun_after_n4_transition_previous_amount_source_repair_rollback.sql`

## Scope

N5 run-once consumed only N4 `TriggerMatched` rows from the supplied source trigger run.

- consumed `TriggerMatched`: 491
- ignored `TriggerPendingMarketData`: 3835 remained pending, 0 N5 facts
- ignored `TriggerStateChanged`: 0
- N4 outbox delivered/delivering after execute: 0
- N5 outbox consumption: not performed
- N6: deferred / not entered

## Inserted Rows

- common_action_run: 1
- stock_action_fact: 418
- index_action_fact: 17
- board_action_fact: 56
- common_action_event: 491
- common_event_outbox: 491
- common_event_inbox: 491
- common_event_consumer_checkpoint scoped refs: 486

## Distributions

Action state:

- blocked: 469
- executed: 22

Action events:

- ActionBlocked: 469
- ActionExecuted: 22

Final action_mark:

- 30m_shrink: 6
- 30m_volume: 11
- normal: 5
- null: 469

Runtime signal_type:

- B_BUY: 157
- S_SELL: 334

Trace preservation:

- BUY trace rows: 157
- SELL trace rows: 334
- BUY_HINT trace rows: 7
- SELL_HINT trace rows: 22
- non-runtime signal rows: 0
- Hint remained trace-only; no HintEvent emitted.

## N3 Metric Proof

All 491 action facts have `trace_json.source_projection_run_id` equal to the supplied N3 metric run. `action_mark_source` is `n5_action_confirmation_metric` and `action_mark_basis` is `previous_day_same_window_amount` for all 491 facts. No final `action_mark` was inferred from `condition_key`, `original_condition_key`, or `required_periods`.

## Target Proofs

- `stock:SZ:301611 BUY:M,W,D`: N4 `TriggerMatched`, triggered_periods `M/W/D`, primary `M`; created one N5 stock action fact, state `blocked`, signal `B_BUY`.
- `stock:SZ:300684 BUY:M,D`: N4 `TriggerPendingMarketData`, triggered_periods empty; no N5 fact.
- `stock:SZ:300687 BUY:Y,M,D`: N4 `TriggerPendingMarketData`, triggered_periods empty; no N5 fact.

## Forbidden Scope

- N6/user projection: not entered
- N5 outbox: not consumed, all 491 rows remain pending
- N4 outbox status: not updated
- scheduler/worker: not started
- N1/N2/N3/N4 writes: not touched
- voice/mobile/sim/order/real trade: not touched
- position_event rows: 0
- old system: not read or modified
- forbidden ref scan: 25 relevant tables scanned, 0 refs

## Artifacts

- execute report JSON: `docs/N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_EXECUTE_REPORT.json`
- execute report MD: `docs/N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_EXECUTE_REPORT.md`
- post-review JSON: `docs/N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_EXECUTE_POST_REVIEW.json`
- post-review MD: `docs/N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_EXECUTE_POST_REVIEW.md`
