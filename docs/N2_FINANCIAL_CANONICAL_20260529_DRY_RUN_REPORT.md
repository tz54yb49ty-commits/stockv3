# N2 Financial Canonical 20260529 Dry-run Report

result = DRY_RUN_PASS

- source_trade_date / for_trade_date: `20260529` / `20260601`
- proposed_run_id: `condition_layer_20260529_source_20260529_v2`
- expected rows with display: `{'common_condition_run': 1, 'common_condition_quality_item': 106, 'stock_monitor_target': 5506, 'index_monitor_target': 83, 'board_monitor_target': 428, 'stock_condition_basis': 5506, 'index_condition_basis': 83, 'board_condition_basis': 428, 'stock_condition_pool': 4106, 'index_condition_pool': 187, 'board_condition_pool': 942, 'index_minute_target_scope': 187, 'board_minute_target_scope': 942, 'stock_minute_target_scope': 4087, 'stock_condition_display_basis': 1862, 'index_condition_display_basis': 83, 'board_condition_display_basis': 428}`
- financial canonical mismatch: `0`
- writes_performed=false; will_execute_sql=false

```json
{
  "stage": "N2-financial-canonical-after-029-full-dry-run",
  "status": "DRY_RUN_PASS",
  "passed": true,
  "source_trade_date": "20260529",
  "for_trade_date": "20260601",
  "prev_trade_date": "20260529",
  "run_id_suggestion": "condition_layer_20260529_source_20260529_v2",
  "source_ready": {
    "passed": true,
    "expected_condition_stock_universe": 5506,
    "excluded_from_condition_universe": 0
  },
  "source_versions": {
    "stock_daily": "stock_daily_20260529_v1",
    "stock_daily_basic": "stock_daily_basic_20260529_v1",
    "stock_financial": "stock_financial_20260529_v2",
    "index_daily": "index_daily_20260529_v1",
    "index_membership": "index_membership_20260529_v1",
    "board_daily": "board_daily_20260529_v1",
    "board_membership": "board_membership_20260529_v1"
  },
  "policy_source": "8782_console",
  "policy_id": "n2_default_policy",
  "policy_version": "v4",
  "policy_hash": "ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576",
  "stage_counts": {
    "condition_basis": {
      "stock": 5506,
      "index": 83,
      "board": 428
    },
    "condition_pool": {
      "stock": 4106,
      "index": 187,
      "board": 942
    },
    "minute_target_scope": {
      "stock": 4087,
      "index": 187,
      "board": 942
    },
    "condition_display_basis": {
      "stock": 1862,
      "index": 83,
      "board": 428
    }
  },
  "expected_rows_with_display": {
    "common_condition_run": 1,
    "common_condition_quality_item": 106,
    "stock_monitor_target": 5506,
    "index_monitor_target": 83,
    "board_monitor_target": 428,
    "stock_condition_basis": 5506,
    "index_condition_basis": 83,
    "board_condition_basis": 428,
    "stock_condition_pool": 4106,
    "index_condition_pool": 187,
    "board_condition_pool": 942,
    "index_minute_target_scope": 187,
    "board_minute_target_scope": 942,
    "stock_minute_target_scope": 4087,
    "stock_condition_display_basis": 1862,
    "index_condition_display_basis": 83,
    "board_condition_display_basis": 428
  },
  "quality_summary": {
    "p0_count": 0,
    "p1_count": 6,
    "p2_count": 3,
    "quality_item_count": 106,
    "by_stage": {
      "condition_basis": {
        "p0_count": 0,
        "p1_count": 4,
        "p2_count": 1,
        "quality_item_count": 24
      },
      "condition_pool": {
        "p0_count": 0,
        "p1_count": 1,
        "p2_count": 1,
        "quality_item_count": 25
      },
      "minute_target_scope": {
        "p0_count": 0,
        "p1_count": 1,
        "p2_count": 1,
        "quality_item_count": 19
      }
    }
  },
  "financial_canonical_pass_through": {
    "n1_stock_financial_rows": 5506,
    "basis_rows": 5506,
    "pool_rows": 4106,
    "scope_rows": 4087,
    "display_rows": 1862,
    "basis_mismatch_count": 0,
    "pool_mismatch_count": 0,
    "scope_mismatch_count": 0,
    "display_mismatch_count": 0,
    "mismatch_samples": {
      "basis": [],
      "pool": [],
      "scope": [],
      "display": []
    },
    "finance_sector_warning_rows": 120,
    "pre_revenue_warning_rows": 1,
    "warning_preservation_missing_count": 0,
    "warning_preservation_missing_samples": [],
    "non_stock_financial_columns": {},
    "financial_quality_status_mapping": "N1 stock_financial_metrics_fact.quality_status -> N2 financial_quality_status",
    "numeric_comparison": "Decimal semantic equality for numeric fields",
    "canonical_financial_pass_through_mismatch": 0
  },
  "writes_performed": false,
  "will_execute_sql": false,
  "outbox_written": false,
  "downstream_layers_touched": false,
  "worker_started": false
}
```
