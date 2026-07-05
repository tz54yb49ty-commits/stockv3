# N3 Lineage Refresh For N2 20260615 V4 Contract

- result: CONTRACT_PASS
- layer_role: N3_market_data
- source_trade_date: 20260615
- for_trade_date: 20260616
- source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v4`
- source_subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- P0/P1/P2: 0/2/0

## Staged Execution Contract
- stage_order: ['subscription_control_rows', 'a1_previous_day_minute_preload']
- stage1_subscription_control_run: {'run_id': 'market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4', 'execute_runner': 'scripts/run_market_data_subscription_execute.py', 'execute_requires_flags': ['--execute', '--user-confirmed'], 'planned_rows': {'common_market_data_run': 1, 'common_market_data_quality_item': 34, 'common_market_data_subscription_candidate': 5924, 'common_market_data_subscription': 3272, 'common_market_data_pull_plan': 9}, 'market_data_pulled': False, 'market_data_fact_written': False, 'writes_outbox': False}
- stage2_a1_preload_run: {'run_id': 'previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4', 'execute_runner': 'scripts/run_previous_day_minute_preload_execute.py', 'execute_requires_flags': ['--execute', '--user-confirmed'], 'execute_requires_stage1_passed': True, 'planned_rows': {'common_market_data_run': 1, 'stock_minute_bar_1m': 132000, 'index_minute_bar_1m': 4080, 'board_minute_bar_1m': 12720, 'stock_previous_day_minute_preload_status': 550, 'index_previous_day_minute_preload_status': 17, 'board_previous_day_minute_preload_status': 53}, 'writes_outbox': False}

## Planned Write Scope
- allowed: ['common_market_data_run', 'common_market_data_quality_item', 'common_market_data_subscription_candidate', 'common_market_data_subscription', 'common_market_data_pull_plan', 'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m', 'stock_previous_day_minute_preload_status', 'index_previous_day_minute_preload_status', 'board_previous_day_minute_preload_status']
- forbidden: ['stock_realtime_daily_snapshot', 'index_realtime_daily_snapshot', 'board_realtime_daily_snapshot', 'stock_realtime_projection_metric', 'index_realtime_projection_metric', 'board_realtime_projection_metric', 'stock_action_confirmation_projection_metric', 'index_action_confirmation_projection_metric', 'board_action_confirmation_projection_metric', 'common_event_outbox', 'common_event_inbox', 'common_event_consumer_checkpoint', 'N3-B/C/B2', 'N4 tables', 'N5 tables', 'N6 tables', 'worker', 'voice/mobile/sim/position/order/real_trade', 'old system']

## Rollback Policy
- scope: new v4 subscription control rows and new v4 A1 preload rows only
- preserves_previous_v1_v2_v3_lineage: True
- hard_fail_before_delete_update: True
- guards_event_infra: True
- guards_n3_b_c_b2_refs: True
- guards_n4_n5_n6_refs: True
- guards_worker_downstream_flags: True
- no_drop_truncate_cascade: True
