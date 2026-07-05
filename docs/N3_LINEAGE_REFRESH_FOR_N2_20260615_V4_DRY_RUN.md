# N3 Lineage Refresh For N2 20260615 V4 Dry Run

- result: DRY_RUN_PASS
- layer_role: N3_market_data
- source_trade_date: 20260615
- for_trade_date: 20260616
- new_subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- new_preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- P0/P1/P2: 0/2/0

## Dry Run Summary
- source_scope_rows: {'stock': 4194, 'index': 183, 'board': 307}
- scope_objects: {'stock': 1822, 'index': 83, 'board': 127}
- subscription_counts: {'candidate': 5924, 'dedup_subscription': 3272, 'subscription_objects': 2032, 'pull_plan': 9}
- a1_objects: {'stock': 550, 'index': 17, 'board': 53, 'total': 620}
- a1_minute_rows: {'stock': 132000, 'index': 4080, 'board': 12720, 'total': 148800}

## A1 Preload Dry Run
- source_subscription_run_id: market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
- preload_run_id: previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
- previous_day_minute_date: 20260615
- required_data_kind: previous_day_minute_bar_1m
- objects: {'stock': 550, 'index': 17, 'board': 53, 'total': 620}
- expected_minute_rows: {'stock': 132000, 'index': 4080, 'board': 12720, 'total': 148800}
- expected_status_rows: {'stock': 550, 'index': 17, 'board': 53, 'total': 620}
- expected_bar_count_per_object: 240
- source_adapter_plan: [{'asset_kind': 'board', 'planned_pull_plan_ref': 'dry_run:pull_plan:2', 'source_pull_plan_id': None, 'source_pull_plan_id_available_after_stage1_execute': True, 'adapter_name': 'BoardMarketDataAdapter', 'previous_day_minute_date': '20260615', 'subscription_count': 53, 'object_count': 53, 'expected_minute_bar_rows': 12720, 'adapter_call_planned_in_preflight': False}, {'asset_kind': 'index', 'planned_pull_plan_ref': 'dry_run:pull_plan:5', 'source_pull_plan_id': None, 'source_pull_plan_id_available_after_stage1_execute': True, 'adapter_name': 'IndexMarketDataAdapter', 'previous_day_minute_date': '20260615', 'subscription_count': 17, 'object_count': 17, 'expected_minute_bar_rows': 4080, 'adapter_call_planned_in_preflight': False}, {'asset_kind': 'stock', 'planned_pull_plan_ref': 'dry_run:pull_plan:8', 'source_pull_plan_id': None, 'source_pull_plan_id_available_after_stage1_execute': True, 'adapter_name': 'StockMarketDataAdapter', 'previous_day_minute_date': '20260615', 'subscription_count': 550, 'object_count': 550, 'expected_minute_bar_rows': 132000, 'adapter_call_planned_in_preflight': False}]
- market_data_pulled: False
- market_data_fact_written: False
- event_outbox_written: False
- worker_started: False

## Forbidden Scope
- read_only_database_checks: True
- will_execute_sql: False
- writes_performed: False
- market_data_pulled: False
- market_data_fact_written: False
- event_outbox_written: False
- downstream_layers_touched: False
- worker_started: False
- old_system_touched: False
