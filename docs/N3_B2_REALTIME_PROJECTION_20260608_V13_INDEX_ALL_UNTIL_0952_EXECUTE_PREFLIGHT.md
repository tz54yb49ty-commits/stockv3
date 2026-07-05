# N3 B2 Realtime Projection 20260608 v13 Index-All Until 09:52 Execute Preflight

- result: `PREFLIGHT_PASS`
- projection_run_id: `realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- generated_at_utc: `2026-06-08T02:17:45.338490+00:00`

## Lineage Checks

- `subscription` `market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` passed=`True` expected_fact=`False`
- `snapshot` `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` passed=`True` expected_fact=`True`
- `preload` `previous_day_minute_preload_20260605__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` passed=`True` expected_fact=`True`
- `today_minute` `today_minute_bar_1m_20260608_until_0952__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` passed=`True` expected_fact=`True`

## Baseline

| key | value |
|---|---|
| projection_run_exists | `False` |
| projection_run_table_counts | `{"board_realtime_projection_metric": 0, "index_realtime_projection_metric": 0, "stock_realtime_projection_metric": 0}` |
| quality_rows_for_projection_run | `0` |
| outbox_rows_for_projection_run | `0` |
| inbox_rows_for_projection_run | `0` |
| checkpoint_refs_for_projection_run | `0` |
| snapshot_outbox_status | `{"pending": 2155}` |
| projection_table_counts_total_before | `{"board_realtime_projection_metric": 983, "index_realtime_projection_metric": 101, "stock_realtime_projection_metric": 5980}` |
| downstream_ref_baseline | `{"common_action_event": 0, "common_trigger_match": 0, "common_trigger_state": 0, "user_notification_queue": 0, "user_projection_run": 0, "user_signal_card": 0, "user_signal_projection": 0}` |

## Contract Summary

| key | value |
|---|---|
| projection_run_id | `realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute` |
| allowed_write_tables | `["common_market_data_run", "common_market_data_quality_item", "stock_realtime_projection_metric", "index_realtime_projection_metric", "board_realtime_projection_metric"]` |
| forbidden_write_tables | `["common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint", "stock_realtime_daily_snapshot", "index_realtime_daily_snapshot", "board_realtime_daily_snapshot", "stock_minute_bar_1m", "index_minute_bar_1m", "board_minute_bar_1m", "N4 trigger tables", "N5 action tables", "N6 projection/card tables", "delivery/push/voice/mobile", "sim/position/pnl/real_trade", "proposal/order/trade"]` |
| writes_outbox | `False` |
| updates_market_snapshot_payload | `False` |
| consumes_outbox | `False` |
| starts_worker | `False` |
| quality_data_domain_policy | `{"allowed_data_domains": ["common", "stock", "index", "board"], "forbidden_data_domains": ["market_data_projection"], "projection_semantics": "Projection quality uses existing data_domain values; metric scope is carried in details.metric_scope/table_name."}` |
| quality_layer_scope_policy | `{"allowed_layer_scopes": ["market_data_run"], "forbidden_layer_scopes": ["realtime_projection_metric"], "layer_scope": "market_data_run"}` |

## Quality

| key | value |
|---|---|
| p0_count | `0` |
| p1_count | `3` |
| p2_count | `0` |
