# N1 Condition Source 20260528 Activation Contract

Result: `DESIGN_PASS`

- layer_role: `N1_ingestion`
- trade_date: `20260529`
- source_batch_id: `condition_source_activation_20260529_v1`
- source_versions: `{"stock_daily_basic": "stock_daily_basic_20260529_v1", "stock_financial": "stock_financial_20260529_v1", "index_membership": "index_membership_20260529_v1", "board_membership": "board_membership_20260529_v1"}`
- execute runner implemented: `True`
- final execute gate allowed: `True`
- allowed tables: `common_ingest_batch, common_quality_gate_result, common_active_source_version, stock_daily_basic, stock_financial_metrics_fact, index_membership_fact, board_membership_fact`
- forbidden: daily bar fact, Parquet, outbox/inbox/checkpoint, N2-N6, worker, old system, real trading

Expected rows:

```json
{
  "stock_daily_basic": 5506,
  "stock_financial": 5506,
  "index_membership": 12841,
  "board_membership": 56960,
  "total": 80813
}
```

Rollback SQL: `sql/N1_condition_source_20260529_activation_rollback.sql`
