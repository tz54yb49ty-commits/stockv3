# N3_20260617_D_ANCHOR_REPAIR_SUBSCRIPTION_AND_FULL_DAY_C1_EXECUTE_FINAL_GATE_REVIEW

- result: `SUBSCRIPTION_C1_PASS`
- subscription_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- today_minute_run_id: `today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- planned_metric_run_id: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- stock/index/board minute rows: `441840` / `19440` / `30480`
- included identities: `1841` / `81` / `127`
- per-identity row count min/max: stock `240/240`, index `240/240`, board `240/240`
- full-day label range: stock `09:31..15:00`, index `09:31..15:00`, board `09:31..15:00`
- BJ excluded minute rows: `{'index:BJ:899050': 0, 'index:BJ:899601': 0}`
- BJ quality blocker rows: `2`
- B2 target clean: `{'common_market_data_run': 0, 'common_market_data_quality_item': 0, 'stock_action_confirmation_projection_metric': 0, 'index_action_confirmation_projection_metric': 0, 'board_action_confirmation_projection_metric': 0}`
- rollback_sql_path: `/Users/chuanfuchen/Documents/A股监控系统v3/sql/N3_20260617_full_day_rebuild_after_n2_d_anchor_repair_rollback.sql`
