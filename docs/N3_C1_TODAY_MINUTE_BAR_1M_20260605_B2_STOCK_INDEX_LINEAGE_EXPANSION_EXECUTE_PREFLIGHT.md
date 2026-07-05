# N3 C1 Today Minute 20260605 B2 Stock/Index Lineage Expansion Execute Preflight

- result: `PREFLIGHT_PASS`
- ready: `true`
- blockers: `none`
- today_minute_run_id: `today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`
- expected rows: `{'stock': 195156, 'index': 819, 'board': 0}` total=`195975`
- baseline: `{'common_market_data_run': 0, 'common_market_data_quality_item': 0, 'stock_minute_bar_1m': 0, 'index_minute_bar_1m': 0, 'board_minute_bar_1m': 0, 'common_event_outbox_refs': 0, 'common_event_inbox_refs': 0, 'common_event_consumer_checkpoint_refs': 0}`
- duplicate_risk: `none`
- P0/P1/P2: `0/0/0`
- rollback_sql_path: `sql/N3_C1_today_minute_bar_1m_20260605_b2_stock_index_lineage_expansion_rollback.sql`
