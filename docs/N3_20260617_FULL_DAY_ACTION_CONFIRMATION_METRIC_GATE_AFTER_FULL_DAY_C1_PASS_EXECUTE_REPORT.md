# N3 20260617 Full-Day B2 Action-Confirmation Metric Execute Report

- result: `B2_METRIC_PASS`
- metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- rows stock/index/board/total: `441840/19440/30480/491760`
- canonical full_scope: `{'BUY': 1941, 'SELL': 2023, 'BUY:FULL': 110, 'SELL:FULL': 28, 'BUY_HINT': 59, 'SELL_HINT': 165}`
- canonical included_metric_scope: `{'BUY': 1939, 'SELL': 2021, 'BUY:FULL': 110, 'SELL:FULL': 28, 'BUY_HINT': 59, 'SELL_HINT': 165}`
- BJ blockers: `{'excluded_identities': ['index:BJ:899050', 'index:BJ:899601'], 'c1_bj_blocker_proof': {'excluded_identities': ['index:BJ:899050', 'index:BJ:899601'], 'minute_rows_for_c1': {'index:BJ:899050': 0, 'index:BJ:899601': 0}, 'quality_rows_c1': {'rows': 2, 'p1_warning': 2}, 'condition_rows': [{'identity_key': 'index:BJ:899050', 'signal_types': ['BUY', 'SELL'], 'condition_rows': 2}, {'identity_key': 'index:BJ:899601', 'signal_types': ['BUY', 'SELL'], 'condition_rows': 2}]}, 'b2_bj_metric_rows': {'index:BJ:899050': 0, 'index:BJ:899601': 0}, 'b2_quality_rows': {'rows': 4, 'p1_warning': 2, 'identities': ['index:BJ:899050', 'index:BJ:899601']}, 'blocker_canonical_distribution': {'BUY': 2, 'SELL': 2, 'BUY:FULL': 0, 'SELL:FULL': 0, 'BUY_HINT': 0, 'SELL_HINT': 0}}`
- rollback_sql: `sql/N3_20260617_full_day_action_confirmation_metric_after_c1_pass_rollback.sql`
- writes_outbox: `false`
- N4/N5/N6 entered: `false`
