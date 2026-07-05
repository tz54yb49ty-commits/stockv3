
# V3 20260616 Realtime Virtual Metric Writer Payload

- result: `SOURCE_PAYLOAD_PREFLIGHT_PASS`
- target_run_id: `action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- source lineage: B1 `realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`, C1 `today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`, previous-day `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`, N2 `condition_layer_20260615_source_20260615_for_20260616_v1`
- candidates stock/index/board/total: `564/17/53/634`
- signal distribution: `{'S_SELL': 590, 'B_BUY': 44}`
- source records: `266280` rows across `634` codes
- D/W/M/Q/Y context coverage: `True`
- side effects: no DB write, no outbox/inbox/checkpoint consume/update, no N4/N5/N6, no scheduler/worker
