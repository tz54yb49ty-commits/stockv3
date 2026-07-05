# N2 Symmetry Target Price Alignment 20260528 v5 Execute Post-review

- result: `POST_REVIEW_PASS`
- run_id: `condition_layer_20260528_source_20260528_v5`
- previous_active_run_id: `condition_layer_20260528_source_20260528_v4`
- passed_active_count: `1`
- rollback_sql: `sql/N2_symmetry_target_price_alignment_20260528_v5_rollback.sql`
- rollback_safe: `True`
- blockers: `[]`

## Run Status
- `condition_layer_20260528_source_20260528_v4`: `superseded` P0/P1/P2=`0/3/3`
- `condition_layer_20260528_source_20260528_v5`: `passed_active` P0/P1/P2=`0/3/3`

## Row Counts
- `common_condition_run`: `1`
- `common_condition_quality_item`: `103`
- `stock_condition_basis`: `5506`
- `index_condition_basis`: `83`
- `board_condition_basis`: `428`
- `stock_condition_pool`: `4271`
- `index_condition_pool`: `169`
- `board_condition_pool`: `875`
- `stock_minute_target_scope`: `4251`
- `index_minute_target_scope`: `169`
- `board_minute_target_scope`: `875`
- `stock_condition_display_basis`: `2011`
- `index_condition_display_basis`: `83`
- `board_condition_display_basis`: `428`
- `stock_monitor_target`: `5506`
- `index_monitor_target`: `83`
- `board_monitor_target`: `428`

## 000027 Golden
- `main_up_anchor`: `W`
- `up_reference_period`: `D`
- `up_trend_start_date`: `20260506`
- `up_trend_end_date`: `20260528`
- `up_amplitude`: `1.17`
- `up_base_price`: `7.25`
- `buy_target_price`: `8.42`
- `reference_target_price`: `8.42`

## Boundary Proof
- `common_event_outbox` refs: `0`
- `common_event_inbox` refs: `0`
- `common_event_consumer_checkpoint` refs: `{'no_ref_columns': ['checkpoint_payload', 'consumer_name', 'last_event_id', 'last_event_time', 'last_outbox_id', 'partition_key', 'source_layer', 'updated_at']}`
- `common_market_data_run` refs: `0`
- `common_trigger_run` refs: `0`
- `common_action_run` refs: `0`

## Checks
- alias_mismatches_total: `0`
- invalid_reference_period_total: `0`
- negative_numeric_rows_total: `0`
- forbidden_columns_present: `{'stock_condition_basis': [], 'index_condition_basis': [], 'board_condition_basis': [], 'stock_condition_pool': [], 'index_condition_pool': [], 'board_condition_pool': [], 'stock_minute_target_scope': [], 'index_minute_target_scope': [], 'board_minute_target_scope': [], 'stock_condition_display_basis': [], 'index_condition_display_basis': [], 'board_condition_display_basis': []}`
- deprecated_signal_rows_total: `0`
