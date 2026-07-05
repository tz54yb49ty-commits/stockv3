# V3 20260612 Pre-New-Plan Runtime Messages Cleanup Execute Report

Result: `EXECUTE_PASS`

Cleanup run: `v3_20260612_pre_new_plan_runtime_messages_cleanup_v1`

The scoped cleanup executed in one transaction and committed. It removed only the approved N5 -> N4 -> N3 derived runtime rows after backing them up to `common_runtime_cleanup_backup`.

## Before Counts

- `n6_user_refs`:
  - `user_projection_run` = `0`
  - `user_signal_projection` = `0`
  - `user_signal_card` = `0`
  - `user_notification_queue` = `0`
- `n6_virtual_sim_refs`:
  - `n6_virtual_order` = `0`
  - `n6_virtual_trade` = `0`
  - `n6_virtual_position` = `0`
  - `n6_virtual_position_event` = `0`
  - `n6_virtual_pnl_snapshot` = `0`
  - `user_sim_order` = `0`
  - `user_sim_trade` = `0`
  - `user_sim_position` = `0`
- `n5_scope`:
  - `common_action_run` = `3`
  - `common_action_quality_item` = `0`
  - `stock_action_fact` = `2436`
  - `index_action_fact` = `0`
  - `board_action_fact` = `1`
  - `common_action_event` = `2437`
  - `common_event_outbox` = `2437`
  - `common_event_inbox` = `2437`
  - `common_event_consumer_checkpoint` = `2402`
- `n5_outbox_downstream_refs`:
  - `inbox` = `0`
  - `checkpoint` = `0`
- `n4_scope`:
  - `common_trigger_run` = `4`
  - `common_trigger_quality_item` = `36`
  - `common_trigger_state` = `4865`
  - `common_trigger_match` = `3249`
  - `common_event_outbox` = `4865`
  - `common_event_inbox` = `8328`
  - `common_event_consumer_checkpoint` = `8328`
  - `downstream_action_run_refs` = `3`
- `n3_derived_scope`:
  - `common_market_data_run_standard` = `11`
  - `common_market_data_run_trace_b2` = `4`
  - `common_market_data_quality_item_standard` = `110`
  - `common_market_data_quality_item_trace_b2` = `28`
  - `stock_realtime_daily_snapshot_standard` = `20592`
  - `index_realtime_daily_snapshot_standard` = `913`
  - `board_realtime_daily_snapshot_standard` = `1397`
  - `market_snapshot_updated_outbox` = `22902`
  - `stock_realtime_projection_metric_trace_b2` = `7488`
  - `index_realtime_projection_metric_trace_b2` = `332`
  - `board_realtime_projection_metric_trace_b2` = `508`
  - `downstream_inbox_from_standard_outbox` = `8328`
  - `downstream_checkpoint_from_standard_outbox` = `8328`
- `preserved_source_facts_sample`:
  - `stock_minute_bar_1m_20260612` = `705120`
  - `index_minute_bar_1m_20260612` = `90144`
  - `board_minute_bar_1m_20260612` = `56832`
  - `market_data_subscription_20260612` = `2676`

## After Counts

- `n6_user_refs`:
  - `user_projection_run` = `0`
  - `user_signal_projection` = `0`
  - `user_signal_card` = `0`
  - `user_notification_queue` = `0`
- `n6_virtual_sim_refs`:
  - `n6_virtual_order` = `0`
  - `n6_virtual_trade` = `0`
  - `n6_virtual_position` = `0`
  - `n6_virtual_position_event` = `0`
  - `n6_virtual_pnl_snapshot` = `0`
  - `user_sim_order` = `0`
  - `user_sim_trade` = `0`
  - `user_sim_position` = `0`
- `n5_scope`:
  - `common_action_run` = `0`
  - `common_action_quality_item` = `0`
  - `stock_action_fact` = `0`
  - `index_action_fact` = `0`
  - `board_action_fact` = `0`
  - `common_action_event` = `0`
  - `common_event_outbox` = `0`
  - `common_event_inbox` = `0`
  - `common_event_consumer_checkpoint` = `0`
- `n5_outbox_downstream_refs`:
  - `inbox` = `0`
  - `checkpoint` = `0`
- `n4_scope`:
  - `common_trigger_run` = `0`
  - `common_trigger_quality_item` = `0`
  - `common_trigger_state` = `0`
  - `common_trigger_match` = `0`
  - `common_event_outbox` = `0`
  - `common_event_inbox` = `0`
  - `common_event_consumer_checkpoint` = `0`
  - `downstream_action_run_refs` = `0`
- `n3_derived_scope`:
  - `common_market_data_run_standard` = `0`
  - `common_market_data_run_trace_b2` = `0`
  - `common_market_data_quality_item_standard` = `0`
  - `common_market_data_quality_item_trace_b2` = `0`
  - `stock_realtime_daily_snapshot_standard` = `0`
  - `index_realtime_daily_snapshot_standard` = `0`
  - `board_realtime_daily_snapshot_standard` = `0`
  - `market_snapshot_updated_outbox` = `0`
  - `stock_realtime_projection_metric_trace_b2` = `0`
  - `index_realtime_projection_metric_trace_b2` = `0`
  - `board_realtime_projection_metric_trace_b2` = `0`
  - `downstream_inbox_from_standard_outbox` = `0`
  - `downstream_checkpoint_from_standard_outbox` = `0`
- `preserved_source_facts_sample`:
  - `stock_minute_bar_1m_20260612` = `705120`
  - `index_minute_bar_1m_20260612` = `90144`
  - `board_minute_bar_1m_20260612` = `56832`
  - `market_data_subscription_20260612` = `2676`

## Backup Counts

- `board_action_fact`:
  - `1`
- `board_realtime_daily_snapshot`:
  - `1397`
- `board_realtime_projection_metric`:
  - `508`
- `common_action_event`:
  - `2437`
- `common_action_run`:
  - `3`
- `common_event_consumer_checkpoint`:
  - `10730`
- `common_event_inbox`:
  - `10765`
- `common_event_outbox`:
  - `30204`
- `common_market_data_quality_item`:
  - `138`
- `common_market_data_run`:
  - `15`
- `common_trigger_match`:
  - `3249`
- `common_trigger_quality_item`:
  - `36`
- `common_trigger_run`:
  - `4`
- `common_trigger_state`:
  - `4865`
- `index_realtime_daily_snapshot`:
  - `913`
- `index_realtime_projection_metric`:
  - `332`
- `stock_action_fact`:
  - `2436`
- `stock_realtime_daily_snapshot`:
  - `20592`
- `stock_realtime_projection_metric`:
  - `7488`

## Preserved Source Fact Delta

- `stock_minute_bar_1m_20260612`:
  - `0`
- `index_minute_bar_1m_20260612`:
  - `0`
- `board_minute_bar_1m_20260612`:
  - `0`
- `market_data_subscription_20260612`:
  - `0`

## Boundary

- scheduler remained `not_loaded`
- wrapper/N3/N4/N5 were not manually executed
- rollback SQL was not executed
- no N6/voice/mobile/sim/trade path was entered
- old system was not touched

Rollback SQL: `sql/V3_20260612_pre_new_plan_runtime_messages_cleanup_rollback.sql`
