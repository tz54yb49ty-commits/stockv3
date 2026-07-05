# V3 20260617 N3 Rebuild After N2 Semantic Repair Post Review

- result: `PASS`
- new subscription_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- B1 snapshot_run_id: `realtime_daily_snapshot_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- C1 today_minute_run_id: `today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- B2 metric_run_id: `action_confirmation_projection_metric_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- canonical distribution: `{'BUY': 1939, 'SELL': 2021, 'BUY:FULL': 110, 'SELL:FULL': 28, 'BUY_HINT': 59, 'SELL_HINT': 165}`
- quality-visible blockers: `{'count': 4, 'by_canonical_condition_type': {'BUY': 2, 'SELL': 2}, 'sample': [{'asset_kind': 'index', 'identity_key': 'index:BJ:899050', 'canonical_condition_type': 'BUY', 'today_run_rows': 0, 'previous_run_rows': 0}, {'asset_kind': 'index', 'identity_key': 'index:BJ:899050', 'canonical_condition_type': 'SELL', 'today_run_rows': 0, 'previous_run_rows': 0}, {'asset_kind': 'index', 'identity_key': 'index:BJ:899601', 'canonical_condition_type': 'BUY', 'today_run_rows': 0, 'previous_run_rows': 0}, {'asset_kind': 'index', 'identity_key': 'index:BJ:899601', 'canonical_condition_type': 'SELL', 'today_run_rows': 0, 'previous_run_rows': 0}], 'do_not_write_incomplete_minute_facts': True}`
- rollback_sql: `sql/V3_20260617_N3_rebuild_after_n2_repair_rollback.sql`
- forbidden scope: no N4/N5/N6, no outbox/inbox/checkpoint consumption, no worker, no old system, no voice/mobile/sim/order/trade
