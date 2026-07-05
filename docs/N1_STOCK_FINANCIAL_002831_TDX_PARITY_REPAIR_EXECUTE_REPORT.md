# N1 Stock Financial 002831 TDX Parity Repair Report

```json
{
  "result": "EXECUTE_PASS",
  "source_trade_date": "20260615",
  "source_batch_id": "stock_financial_002831_tdx_parity_repair_20260615_v1",
  "source_version": "stock_financial_20260615_v3",
  "previous_source_version": "stock_financial_20260615_v2",
  "row_counts": {
    "stock_financial_metrics_fact": 5504
  },
  "quality": {
    "P0": 0,
    "P1": 1,
    "P2": 0
  },
  "commit_result": {
    "committed": true,
    "source_batch_id": "stock_financial_002831_tdx_parity_repair_20260615_v1",
    "source_version": "stock_financial_20260615_v3",
    "previous_source_version": "stock_financial_20260615_v2",
    "row_counts": {
      "stock_financial_metrics_fact": 5504
    },
    "written_tables": [
      "stock_financial_metrics_fact",
      "common_ingest_batch",
      "common_quality_gate_result",
      "common_active_source_version"
    ],
    "rollback_safe": true,
    "rollback_sql": "sql/N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql"
  }
}
```
