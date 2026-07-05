# N1 Condition Source 20260526 V2 Activation Contract

Result: `DESIGN_PASS`

- layer_role: `N1_ingestion`
- trade_date: `20260526`
- source_batch_id: `condition_source_activation_20260526_v2`
- source_versions: `{"stock_daily_basic": "stock_daily_basic_20260526_v2", "stock_financial": "stock_financial_20260526_v2", "index_membership": "index_membership_20260526_v2", "board_membership": "board_membership_20260526_v2"}`
- execute runner implemented: `True`
- final execute gate allowed: `True`
- allowed tables: `common_ingest_batch, common_quality_gate_result, common_active_source_version, stock_daily_basic, stock_financial_metrics_fact, index_membership_fact, board_membership_fact`
- forbidden: daily bar fact, Parquet, outbox/inbox/checkpoint, N2-N6, worker, old system, real trading

Expected rows:

```json
{
  "stock_daily_basic": 5504,
  "stock_financial": 5504,
  "index_membership": 12841,
  "board_membership": 56872,
  "total": 80721
}
```

Rollback SQL: `sql/N1_condition_source_20260526_v2_activation_rollback.sql`
