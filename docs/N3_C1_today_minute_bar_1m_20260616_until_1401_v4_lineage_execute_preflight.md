# N3 C1 20260616 Until 14:01 V4 Lineage Execute Preflight

- result: `PREFLIGHT_BLOCKED`
- execute_ready: `false`
- blocked_reason: `b1_v4_readiness_blocked_current_date_after_for_trade_date`
- target baseline: `{"today_minute_run_id": "today_minute_bar_1m_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4", "run_exists": false, "target_run_row_counts": {"stock_minute_bar_1m": 0, "index_minute_bar_1m": 0, "board_minute_bar_1m": 0, "common_market_data_quality_item": 0, "common_market_data_run": 0}, "outbox_rows_for_run": 0, "inbox_rows_for_run": 0}`
- expected rows stock/index/board/total: `99550/3077/9593/112220`
- rollback_sql_path: `sql/N3_C1_today_minute_bar_1m_20260616_until_1401_v4_lineage_rollback.sql`

