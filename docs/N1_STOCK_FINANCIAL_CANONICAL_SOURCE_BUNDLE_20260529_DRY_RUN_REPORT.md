# N1 Stock Financial Canonical Source Bundle Dry-Run Report

```json
{
  "result": "PASS",
  "source_trade_date": "20260529",
  "source_coverage": {
    "active_universe_count": 5506,
    "selected_symbol_count": 5506,
    "tdx_primary_count": 0,
    "tushare_fallback_count": 5506,
    "tushare_income_ok_count": 5506,
    "tushare_cashflow_ok_count": 5506,
    "forecast_ok_count": 4667,
    "daily_basic_ok_count": 5506,
    "cache_hit_count": 5506,
    "cache_miss_count": 0,
    "missing_line_item_count": 0,
    "missing_line_item_field_distribution": {},
    "missing_line_item_combo_distribution": {},
    "warning_distribution": {
      "finance_sector_policy_not_supported_v1": 2115,
      "historical_core_line_items_missing": 155,
      "latest_core_line_items_missing_fallback_prior_period": 3,
      "operating_cashflow_missing_historical": 160,
      "pre_revenue_or_missing_revenue_cost": 6,
      "rd_expense_missing_fallback_zero": 6912,
      "selling_expense_missing_fallback_zero": 3039
    },
    "finance_sector_policy_warning_count": 120,
    "finance_sector_policy_industry_distribution": {
      "保险": 5,
      "多元金融": 23,
      "证券": 50,
      "银行": 42
    },
    "pre_revenue_policy_warning_count": 1,
    "pre_revenue_policy_samples": [
      {
        "stock_identity_key": "stock:SH:688759",
        "industry": "生物制药",
        "missing": [
          "operating_cost",
          "operating_revenue"
        ]
      }
    ],
    "historical_core_line_item_missing_count": 155,
    "latest_core_line_item_missing_fallback_count": 3,
    "future_excluded_count": 0,
    "missing_announcement_date_excluded_count": 0,
    "forecast_coverage_count": 4667,
    "interest_expense_missing_finance_expense_used_count": 89261,
    "daily_basic_total_mv_missing_count": 0,
    "source_errors": []
  },
  "quality": {
    "p0_count": 0,
    "p1_count": 7,
    "p2_count": 1,
    "items": [
      {
        "gate_name": "canonical_source_line_items",
        "severity": "P0",
        "status": "passed",
        "expected_value": "0 missing",
        "actual_value": "0",
        "details": {
          "samples": []
        }
      },
      {
        "gate_name": "canonical_source_missing_identity",
        "severity": "P0",
        "status": "passed",
        "expected_value": "0 missing",
        "actual_value": "0",
        "details": {
          "samples": []
        }
      },
      {
        "gate_name": "daily_basic_total_mv_coverage",
        "severity": "P0",
        "status": "passed",
        "expected_value": "0 missing",
        "actual_value": "0",
        "details": {
          "samples": []
        }
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
        "actual_value": "5506",
        "details": {}
      },
      {
        "gate_name": "forecast_type_coverage",
        "severity": "P1",
        "status": "warning",
        "expected_value": "5506",
        "actual_value": "4667",
        "details": {
          "missing_count": 839
        }
      },
      {
        "gate_name": "interest_expense_missing_finance_expense_used",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "89261",
        "details": {}
      },
      {
        "gate_name": "line_item_fallback_warning_distribution",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "12390",
        "details": {
          "warning_distribution": {
            "finance_sector_policy_not_supported_v1": 2115,
            "historical_core_line_items_missing": 155,
            "latest_core_line_items_missing_fallback_prior_period": 3,
            "operating_cashflow_missing_historical": 160,
            "pre_revenue_or_missing_revenue_cost": 6,
            "rd_expense_missing_fallback_zero": 6912,
            "selling_expense_missing_fallback_zero": 3039
          }
        }
      },
      {
        "gate_name": "finance_sector_policy_not_supported_v1",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "120",
        "details": {
          "industry_distribution": {
            "保险": 5,
            "多元金融": 23,
            "证券": 50,
            "银行": 42
          }
        }
      },
      {
        "gate_name": "pre_revenue_or_missing_revenue_cost",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "1",
        "details": {
          "samples": [
            {
              "stock_identity_key": "stock:SH:688759",
              "industry": "生物制药",
              "missing": [
                "operating_cost",
                "operating_revenue"
              ]
            }
          ]
        }
      },
      {
        "gate_name": "latest_core_line_items_missing_fallback_prior_period",
        "severity": "P1",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "3",
        "details": {
          "reason": "latest report has missing core line items; prior as-of usable report period remains available"
        }
      },
      {
        "gate_name": "historical_core_line_items_missing",
        "severity": "P2",
        "status": "warning",
        "expected_value": "0",
        "actual_value": "155",
        "details": {
          "reason": "historical quarter gaps do not block latest canonical row readiness"
        }
      },
      {
        "gate_name": "asof_exclusions",
        "severity": "P2",
        "status": "passed",
        "expected_value": "0",
        "actual_value": "0",
        "details": {}
      }
    ]
  },
  "blockers": [],
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
