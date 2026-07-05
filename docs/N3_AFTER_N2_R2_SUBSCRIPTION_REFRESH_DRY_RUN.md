# N3 After N2-R2 Subscription Refresh Dry-Run

## Summary

- stage: `N3-after-N2-R2-subscription-refresh-dry-run`
- layer_role: `N3_market_data`
- new_condition_run_id: `condition_layer_20260522_to_20260525_20260524181321_execute`
- dry_run_market_data_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260524181321_execute_dry_run`
- suggested_execute_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260524181321_execute`
- source_trade_date: `20260522`
- for_trade_date: `20260525`
- prev_trade_date: `20260522`
- P0/P1/P2: `0/3/0`
- passed: `true`

## Active N2 Check

- is_new_active_run: `true`
- passed_run_count: `1`

## Counts

- expected_scope_counts: `{'stock': 4236, 'index': 18, 'board': 258}`
- actual_scope_counts: `{'stock': 4236, 'index': 18, 'board': 258}`
- expected_object_counts: `{'stock': 2052, 'index': 9, 'board': 127}`
- actual_object_counts: `{'stock': 2052, 'index': 9, 'board': 127}`
- source_scope_row_count: `4512`
- subscription_candidate_count: `13536`
- dedup_subscription_count: `6564`
- subscription_object_count: `2188`
- required_data_kind_counts: `{'minute_bar_1m': 2188, 'previous_day_minute_bar_1m': 2188, 'realtime_daily_snapshot': 2188}`
- market_data_pull_plan_row_count: `9`
- dedup_ratio: `0.484929`

## Old N3 Run

- old_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260524014029_execute`
- old_source_condition_run_id: `condition_layer_20260522_to_20260525_20260524014029_execute`
- old_n3_subscription_run_is_stale: `true`
- old_run_can_continue_as_final_chain: `false`

## Old Vs New Comparison

- comparison: `{'old_run_present': True, 'old_run_id': 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260524014029_execute', 'old_source_condition_run_id': 'condition_layer_20260522_to_20260525_20260524014029_execute', 'new_source_condition_run_id': 'condition_layer_20260522_to_20260525_20260524181321_execute', 'old_counts': {'source_scope_row_count': 4512, 'candidate_row_count': 13536, 'subscription_row_count': 6564, 'subscription_object_count': 2188, 'pull_plan_row_count': 9}, 'new_counts': {'source_scope_row_count': 4512, 'candidate_row_count': 13536, 'subscription_row_count': 6564, 'subscription_object_count': 2188, 'pull_plan_row_count': 9}, 'delta': {'source_scope_row_count': 0, 'candidate_row_count': 0, 'subscription_row_count': 0, 'subscription_object_count': 0, 'pull_plan_row_count': 0}, 'lineage_changed': True}`

## Quality

- P1 warning for_trade_calendar_row_exists: expected=20260525 actual=missing
- P0 passed n3_after_n2_r2_active_condition_run_is_new: expected=condition_layer_20260522_to_20260525_20260524181321_execute actual=condition_layer_20260522_to_20260525_20260524181321_execute
- P0 passed n3_after_n2_r2_dry_run_source_run_matches_new: expected=condition_layer_20260522_to_20260525_20260524181321_execute actual=condition_layer_20260522_to_20260525_20260524181321_execute
- P0 passed n3_after_n2_r2_scope_row_counts_match_expected: expected={'stock': 4236, 'index': 18, 'board': 258} actual={'stock': 4236, 'index': 18, 'board': 258}
- P0 passed n3_after_n2_r2_object_counts_match_expected: expected={'stock': 2052, 'index': 9, 'board': 127} actual={'stock': 2052, 'index': 9, 'board': 127}
- P0 passed n3_after_n2_r2_subscription_and_pull_plan_generated: expected=all row counts > 0 actual=candidate=13536 subscription=6564 pull_plan=9
- P0 passed n3_after_n2_r2_subscription_dry_run_p0_zero: expected=P0=0 passed=true actual=P0=0 passed=True
- P0 passed n3_after_n2_r2_no_market_fact_outbox_or_worker: expected=all side-effect flags false actual=market_data_pulled=False,market_data_fact_written=False,downstream_layers_touched=False,worker_started=False
- P1 warning n3_after_n2_r2_old_n3_subscription_run_stale: expected=source_condition_run_id=condition_layer_20260522_to_20260525_20260524181321_execute actual=condition_layer_20260522_to_20260525_20260524014029_execute
- P1 warning n3_after_n2_r2_new_n3_execute_not_yet_persisted: expected=new N3 control run persisted before final chain actual=not persisted

## Boundary

- read_only_database_checks: `true`
- will_execute_sql: `false`
- migration_executed: `false`
- writes_performed: `false`
- market_data_pulled: `false`
- market_data_fact_written: `false`
- event_outbox_written: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
- old_system_touched: `false`
