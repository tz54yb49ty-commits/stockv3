# N5 Action Rerun After N4 Transition Previous Amount Source Repair Pass Preflight

Result: **PASS**

## Scope

- layer_role: `N5_action`
- trade_date: `20260617`
- source_trigger_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- planned_action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_event_type_filter: `TriggerMatched`
- N5 execute in this preflight: `false`

## Proofs

- N4 post-review: `PASS`
- Source outbox: `TriggerMatched=491`, `TriggerPendingMarketData=3835`, `TriggerStateChanged=0`
- N4 outbox delivered/delivering: `0`
- Existing planned N5 rows: all `0`
- N5 plan reads only `TriggerMatched=491`; `TriggerPendingMarketData` and `TriggerStateChanged` create no N5 entries
- Runtime signal types: `{'B_BUY': 157, 'S_SELL': 334}`
- Hint traces: `[{'condition_key': 'BUY_HINT', 'original_condition_key': 'BUY_HINT', 'signal_type': 'B_BUY', 'c': 7}, {'condition_key': 'SELL_HINT', 'original_condition_key': 'SELL_HINT', 'signal_type': 'S_SELL', 'c': 22}]`
- Planned action_state: `{'blocked': 469, 'executed': 22}`
- Planned events: `{'ActionBlocked': 469, 'ActionExecuted': 22}`
- Planned final action_mark: `{'30m_shrink': 6, '30m_volume': 11, 'normal': 5, 'null': 469}`
- Action mark source: `{'n5_action_confirmation_metric': 491}`
- Action mark basis: `{'previous_day_same_window_amount': 491}`

## Target Rows

- `stock:SZ:301611 BUY:M,W,D`: `TriggerMatched`, triggered_periods include `M/W/D`, primary=`M`, planned N5 entry count=`1`
- `stock:SZ:300684 BUY:M,D`: no `TriggerMatched`; only pending-market-data, planned N5 entry count=`0`
- `stock:SZ:300687 BUY:Y,M,D`: no `TriggerMatched`; only pending-market-data, planned N5 entry count=`0`

## Artifacts

- baseline: `docs/N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_BASELINE.json`
- rollback SQL: `sql/N5_action_rerun_after_n4_transition_previous_amount_source_repair_rollback.sql`

## Forbidden Scope

- N5 execute: `not_executed`
- N6: `not_entered`
- N5 outbox consumption: `not_consumed`
- N4 outbox status update: `not_updated`
- scheduler/worker: `not_started`
- N1/N2/N3/N4 writes: `not_touched`
- voice/mobile/sim/position/order/real trade: `not_touched`
- old system: `not_read_or_modified`

## Allowed Execute Prompt

```text
layer_role=N5_action.
Enter N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_EXECUTE.

Use:
- trade_date=20260617
- action_run_id=action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_metric_run_id=action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- consumer_name=n5_action_consumer_v1
- source_event_type=TriggerMatched
- expected_read_event_count=491
- n5_preflight_artifact=docs/N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_PREFLIGHT.json
- n5_baseline_artifact=docs/N5_ACTION_RERUN_AFTER_N4_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_BASELINE.json
- rollback_sql_path=sql/N5_action_rerun_after_n4_transition_previous_amount_source_repair_rollback.sql

Execute N5 action run-once only.

Must preserve:
- consume only `TriggerMatched=491`
- ignore `TriggerPendingMarketData=3835`
- ignore `TriggerStateChanged=0`
- planned action_state: `{'blocked': 469, 'executed': 22}`
- planned events: `{'ActionBlocked': 469, 'ActionExecuted': 22}`
- planned final marks: `{'30m_shrink': 6, '30m_volume': 11, 'normal': 5, 'null': 469}`
- runtime signal types only `B_BUY/S_SELL`
- `stock:SZ:301611 BUY:M,W,D` remains an N5 entry with primary=M and triggered_periods including M/W/D
- `stock:SZ:300684 BUY:M,D` and `stock:SZ:300687 BUY:Y,M,D` remain non-entries

Boundaries:
- Do not enter N6.
- Do not consume N5 outbox.
- Do not update N4 outbox status.
- Do not start scheduler/worker.
- Do not touch N1/N2/N3/N4 writes.
- Do not touch voice/mobile/sim/position/order/real trade.
- Do not read or modify old system.
```
