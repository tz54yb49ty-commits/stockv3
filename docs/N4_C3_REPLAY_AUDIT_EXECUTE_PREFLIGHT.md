# N4 C3 Replay Audit Execute Preflight

- result: `EXECUTED`
- layer_role: `N4_trigger`
- replay_run_id: `trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b`
- allowed_c3_run_id: `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- c2b_run_id: `closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- source_n4_projection_run_id: `trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`
- source_n5_action_run_id: `action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249`
- rollback_sql_path: `sql/N4_C3_replay_audit_business_rollback.sql`

## Audit Plan

- total: `35970`
- by_classification: `{'would_match': 4734, 'would_clear': 245, 'would_change': 243, 'unchanged': 30730, 'missing': 18, 'not_ready': 0}`
- by_target_table: `{'board_trigger_replay_audit': 2064, 'index_trigger_replay_audit': 144, 'stock_trigger_replay_audit': 33762}`

## Boundary

- planned_write_tables: `['common_trigger_run', 'common_trigger_quality_item', 'stock_trigger_replay_audit', 'index_trigger_replay_audit', 'board_trigger_replay_audit']`
- planned_standard_n4_outbox_counts: `{'TriggerMatched': 0, 'TriggerPendingMarketData': 0, 'TriggerCleared': 0}`
- writes_performed: `True`
- common_event_outbox_written: `False`
- common_event_inbox_written: `False`
- checkpoint_written: `False`
- trigger_match_written: `False`
- trigger_state_written: `False`
- n5_n6_touched: `False`

## Quality

- P0/P1/P2: `0/1/0`
- quality_items: `13`

## Next Gate

- allow_execute_final_gate: `True`
- execute still requires explicit final gate and both `--execute` / `--user-confirmed`.