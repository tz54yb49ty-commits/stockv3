# N1 Stock Financial Canonical Metrics Execute Preflight

```json
{
  "result": "PREFLIGHT_PASS",
  "source_trade_date": "20260617",
  "source_batch_id": "stock_financial_canonical_20260617_v1",
  "source_version": "stock_financial_20260617_v2",
  "previous_source_version": "stock_financial_20260617_v1",
  "commit_result": null,
  "quality": {
    "p0_count": 0,
    "p1_count": 8,
    "p2_count": 2,
    "items": [
      {
        "gate_name": "canonical_core_line_items_available",
        "severity": "P0",
        "status": "passed",
        "expected_value": "all expected identities",
        "actual_value": "5505",
        "details": {}
      },
      {
        "gate_name": "duplicate_identity_key",
        "severity": "P0",
        "status": "passed",
        "expected_value": "0",
        "actual_value": "0",
        "details": {}
      },
      {
        "gate_name": "tushare_fallback_used",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "76449",
        "details": {}
      },
      {
        "gate_name": "interest_expense_missing_fallback",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "72868",
        "details": {}
      },
      {
        "gate_name": "rd_expense_missing_fallback_zero",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "3941",
        "details": {}
      },
      {
        "gate_name": "selling_expense_missing_fallback_zero",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "984",
        "details": {}
      },
      {
        "gate_name": "finance_sector_policy_not_supported_v1",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "120",
        "details": {}
      },
      {
        "gate_name": "pre_revenue_or_missing_revenue_cost",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "1",
        "details": {}
      },
      {
        "gate_name": "latest_core_line_items_missing_fallback_prior_period",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "3",
        "details": {}
      },
      {
        "gate_name": "ttm_annualized",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "16",
        "details": {}
      },
      {
        "gate_name": "asof_exclusions",
        "severity": "P2",
        "status": "passed",
        "expected_value": "0",
        "actual_value": "0",
        "details": {
          "future": 0,
          "missing_announcement": 0
        }
      },
      {
        "gate_name": "operating_cashflow_missing_historical",
        "severity": "P2",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "126",
        "details": {}
      },
      {
        "gate_name": "historical_core_line_items_missing",
        "severity": "P2",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "143",
        "details": {}
      }
    ]
  },
  "side_effects": {
    "writes_performed": false,
    "writes_postgres": false,
    "writes_stock_financial_metrics_fact": false,
    "updates_active_source_version": false,
    "writes_condition_tables": false,
    "writes_parquet": false,
    "writes_outbox": false,
    "writes_inbox_or_checkpoint": false,
    "enters_n2_n3_n4_n5_n6": false,
    "worker_started": false,
    "old_system_touched": false,
    "real_trading": false
  }
}
```
