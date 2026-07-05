# N3 A1/C1 Board Minute Lineage Pull Dry Run

## Summary

- stage: `N3_A1_C1_BOARD_MINUTE_LINEAGE_PULL_DRY_RUN`
- result: `DRY_RUN_PASS`
- blocked: `False`
- subscription_run_id: `market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1`
- previous_day_minute_run_id: `previous_day_minute_preload_20260604_for_20260605_action_metric_board_lineage_repair__market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1`
- today_minute_run_id: `today_minute_bar_1m_20260605_until_1127_action_metric_board_lineage_repair__market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1`
- previous_day_planned_rows: `6720`
- today_planned_rows_until_1127: `3276`

## Quality

- P0/P1/P2: `0/1/0`
- P0 passed a1_c1_board_scope_only: {"a1": {"board": {"expected_bar_count_per_object": 240, "expected_minute_bar_rows": 6720, "object_count": 28, "subscription_count": 28}, "index": {"expected_bar_count_per_object": 240, "expected_minute_bar_rows": 0, "object_count": 0, "subscription_count": 0}, "stock": {"expected_bar_count_per_object": 240, "expected_minute_bar_rows": 0, "object_count": 0, "subscription_count": 0}}, "c1": {"board": 28, "index": 0, "stock": 0}}
- P0 passed a1_c1_expected_rows_match: {"previous_day": 6720, "today": 3276}
- P0 passed a1_c1_source_scope_table_board_minute_target_scope: board_minute_target_scope for 56 scoped control rows
- P0 passed a1_c1_no_metric_v2_or_downstream_refs: 0 by A1 preflight baseline and prior readiness live proof
- P0 passed a1_c1_rollback_hardened_scope: sql/N3_A1_C1_board_minute_lineage_pull_20260605_rollback.sql
- P1 warning a1_contract_p1_carried: 1

## Forbidden Scope

- writes_database: `False`
- pulls_market_data: `False`
- writes_minute_rows: `False`
- writes_status_rows: `False`
- writes_quality_or_run_rows: `False`
- executes_metric_v2: `False`
- writes_outbox: `False`
- consumes_outbox: `False`
- writes_inbox_or_checkpoint: `False`
- starts_worker: `False`
- enters_n4_n5_n6: `False`
- delivery_push_voice_mobile: `False`
- sim_position_pnl_real_trade: `False`
- proposal_order_trade: `False`
- old_system_touched: `False`
