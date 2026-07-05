# N1 Condition Source 20260526 Activation Contract

Result: `DESIGN_PASS`

- layer_role: `N1_ingestion`
- trade_date: `20260526`
- source_batch_id: `condition_source_activation_20260526_v1`
- execute runner implemented: `true`
- final execute gate allowed: `True`
- allowed tables: `common_ingest_batch, common_quality_gate_result, common_active_source_version, stock_daily_basic, stock_financial_metrics_fact, index_membership_fact, board_membership_fact`
- forbidden: `stock_daily_bar_fact, index_daily_bar_fact, board_daily_bar_fact, Parquet, common_event_outbox, common_event_inbox, common_event_consumer_checkpoint, N2_condition_tables, N3_market_data_tables, N4_trigger_tables, N5_action_tables, N6_user_tables, worker, old_system, real_trading`

Expected rows:

```json
{
  "stock_daily_basic": 5520,
  "stock_financial": 5520,
  "index_membership": 12841,
  "board_membership": 56872,
  "total": 80753
}
```

Rollback SQL: `sql/N1_condition_source_20260526_activation_rollback.sql`
