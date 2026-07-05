# N3 C1 Today Minute 20260605 B2 Stock/Index Lineage Expansion Execute Contract

- execute_authorized: false
- source_run_id: `market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`
- today_minute_run_id: `today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`
- expected rows: `{'stock': 195156, 'index': 819, 'board': 0}` total=`195975`
- allowed_write_tables: `['common_market_data_run', 'common_market_data_quality_item', 'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m']`
- writes_outbox: `false`
- rollback_sql_path: `sql/N3_C1_today_minute_bar_1m_20260605_b2_stock_index_lineage_expansion_rollback.sql`

```bash
PYTHONPATH=src:scripts python3 scripts/run_today_minute_bar_1m_once.py --c0-plan-path docs/N3_C0_today_minute_bar_1m_20260605_b2_stock_index_lineage_expansion_dry_run_report.json --for-trade-date 20260605 --today-minute-run-id today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1 --rollback-sql-path sql/N3_C1_today_minute_bar_1m_20260605_b2_stock_index_lineage_expansion_rollback.sql --json-report-path docs/N3_C1_today_minute_bar_1m_20260605_b2_stock_index_lineage_expansion_execute_report.json --markdown-report-path docs/N3_C1_TODAY_MINUTE_BAR_1M_20260605_B2_STOCK_INDEX_LINEAGE_EXPANSION_EXECUTE_REPORT.md --execute --user-confirmed
```
