# N3-A1 Previous-Day Cumulative Amount Fastlane Report

- result: `EXECUTE_PASS`
- source_previous_day_minute_run_id: `previous_day_minute_preload_20260714_for_20260715__market_data_subscription_20260715_condition_layer_20260714_source_20260714_for_20260715_v1`
- source_trade_date: `20260714`
- for_trade_date: `20260715`
- write_action: `inserted`
- rollback_sql_path: `sql/N3_A1_previous_day_minute_cumulative_20260714_for_20260715_rollback.sql`

## Row Counts
- stock: `407520`
- index: `2160`
- board: `30480`

## Side Effects
- cumulative_table_written: `True`
- common_market_data_run_written: `False`
- common_market_data_quality_item_written: `False`
- outbox_written: `False`
- inbox_checkpoint_touched: `False`
- downstream_runtime_entered: `False`
- market_data_adapter_called: `False`
