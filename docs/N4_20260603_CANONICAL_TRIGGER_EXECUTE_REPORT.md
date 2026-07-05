# N4 20260603 Canonical Trigger Execute Report

- result: `EXECUTE_PASS`
- layer_role: `N4_trigger`
- execute_run_id: `trigger_execute_20260603_condition_layer_20260602_source_20260602_v1`
- context_run_id: `trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1`
- snapshot_run_id: `realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- market_subscription_run_id: `market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- for_trade_date: `20260603`

## Run

- common_trigger_run.status: `passed`
- P0/P1/P2: `0/1/0`
- quality rows: `17`
- quality distribution: `P0 passed=16`, `P1 warning=1`

## Rows

- common_trigger_state: `10167`
- common_trigger_match: `10167`
- common_event_outbox: `20334`

## Event Distribution

- TriggerMatched: `1252`
- TriggerPendingMarketData: `8915`
- TriggerStateChanged: `10167`

## Outbox Status

- pending: `20334`
- delivered: `0`
- delivering: `0`

## Canonical Checks

- runtime signal_type: `B_BUY=5164`, `S_SELL=5003`
- deprecated runtime signal count: `0`
- trigger_mark_candidate: `normal=5222`, `30m_volume=2474`, `30m_shrink=2471`
- pending_market_data trigger_live=false: `8915`
- matched trigger_live=true: `1252`
- TriggerStateChanged rows in common_trigger_match: `0`
- final action_mark columns in trigger_state/match: `0`

## Anomaly Proof

- matched rows checked: `1252`
- B_BUY current_price/close <= open anomaly: `0`
- S_SELL current_price/close >= open anomaly: `0`
- B_BUY amount below localized baseline anomaly: `0`
- S_SELL amount above localized baseline anomaly: `0`

## Boundary Proof

- common_event_inbox refs: `0`
- common_event_consumer_checkpoint refs: `0`
- source snapshot outbox/inbox/checkpoint refs: `0/0/0`
- N5 common_action_run/common_action_event refs: `0/0`
- N6 user_projection_run/user_signal_projection/user_signal_card/user_notification_queue refs: `0/0/0/0`
- market_data_pulled: `false`
- action_layer_touched: `false`
- user_layer_touched: `false`
- voice_touched: `false`
- sim_touched: `false`
- real_trade_touched: `false`
- worker_started: `false`

## Rollback

- rollback_safe: `true`
- rollback_sql: `sql/N4_20260603_canonical_trigger_execute_rollback.sql`
- rollback is safe only before downstream outbox consumption.
- hard-fail guards cover delivered/delivering outbox, inbox/checkpoint, N5 action run/event refs, and optional N6 projection/card/queue refs.
- delete scope only covers N4 execute output: common_event_outbox, common_trigger_match, common_trigger_state, common_trigger_quality_item, common_trigger_run.

## Next Route

Return to `runtime_control` registration. Do not enter N5/N6 from this N4 session.
