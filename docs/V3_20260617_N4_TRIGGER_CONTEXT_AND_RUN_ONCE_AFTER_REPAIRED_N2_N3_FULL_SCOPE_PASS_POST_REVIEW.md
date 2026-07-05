# V3_20260617 N4 Trigger Context And Run Once After Repaired N2/N3 Full Scope Pass

Result: PASS

Layer: N4_trigger

## Run IDs

- trigger_context_run_id: `trigger_context_snapshot_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- execute_run_id: `trigger_action_confirmation_metric_execute_20260617_until_1352__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_condition_run_id: `condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_metric_run_id: `action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`

## Distribution

- TriggerMatched: 970
- TriggerPendingMarketData: 3356
- TriggerStateChanged: 0

State rows:

- matched / trigger_live=true / B_BUY: 399
- matched / trigger_live=true / S_SELL: 571
- pending_market_data / trigger_live=false / B_BUY: 1711
- pending_market_data / trigger_live=false / S_SELL: 1645

## Baseline Proof

`period_trigger_baseline_json.periods[P].trigger_previous_entity_high/low` uses the previous complete period entity high/low. `current_seed_entity_high/low` remains trace only.

For `board:TDX:881078`, W has:

- trigger_previous_entity_low: `632.78`
- trigger_previous_entity_high: `696.8`
- current_seed_entity_low: `706.84`
- current_seed_entity_high: `712.3`

The repaired N4 match for `SELL:Y,Q,M,W,D` is D-only:

- trigger_match_id: `334356`
- signal_type: `S_SELL`
- trigger_period: `D`
- triggered_periods: `["D"]`

## Inclusion Proof

- Ordinary BUY context rows: 1941; TriggerMatched: 343; TriggerPendingMarketData: 1598.
- Ordinary SELL context rows: 2023; TriggerMatched: 531; TriggerPendingMarketData: 1492.
- BUY:FULL context rows: 110; TriggerMatched: 49; TriggerPendingMarketData: 61.
- SELL:FULL context rows: 28; TriggerMatched: 18; TriggerPendingMarketData: 10.
- BUY_HINT context rows: 59; TriggerMatched: 7; TriggerPendingMarketData: 52.
- SELL_HINT context rows: 165; TriggerMatched: 22; TriggerPendingMarketData: 143.

BUY_HINT/SELL_HINT remained condition trace only; runtime signal_type is `B_BUY` or `S_SELL`.

## Pending Proof

- TriggerPendingMarketData outbox rows: 3356.
- `common_trigger_match` rows with `output_event_type=TriggerPendingMarketData`: 0.
- `common_action_run` rows referencing this execute_run_id: 0.
- `common_event_inbox` rows for this execute_run_id or new outbox event ids: 0.

## Rollback

- Context rollback SQL: `sql/V3_20260617_N4_context_after_repaired_n2_n3_full_scope_rollback.sql`
- Execute rollback SQL: `sql/V3_20260617_N4_after_repaired_n2_n3_full_scope_rollback.sql`
