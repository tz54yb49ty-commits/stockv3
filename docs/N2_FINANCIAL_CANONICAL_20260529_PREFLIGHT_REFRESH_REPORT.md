# N2 Financial Canonical 20260529 Preflight Refresh Report

result = PREFLIGHT_PASS

- dry_run_result: `DRY_RUN_PASS`
- proposed_run_id: `condition_layer_20260529_source_20260529_v2`
- remaining_blockers: `[]`
- allow_enter_final_gate: `True`

```json
{
  "result": "PREFLIGHT_PASS",
  "dry_run_result": "DRY_RUN_PASS",
  "layer_role": "N2_condition",
  "generated_at": "2026-06-01T16:38:23",
  "source_trade_date": "20260529",
  "for_trade_date": "20260601",
  "prev_trade_date": "20260529",
  "proposed_run_id": "condition_layer_20260529_source_20260529_v2",
  "schema_ready": true,
  "stock_financial_fields_ready": true,
  "n1_active_stock_financial": "stock_financial_20260529_v2",
  "policy_source": "8782_console",
  "policy_id": "n2_default_policy",
  "policy_version": "v4",
  "policy_hash": "ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576",
  "current_active_n2": {
    "runs": [
      {
        "run_id": "condition_layer_20260529_source_20260529_v1",
        "status": "passed_active",
        "source_trade_date": "20260529",
        "for_trade_date": "20260601",
        "prev_trade_date": "20260529",
        "source_versions": {
          "board_daily": "board_daily_20260529_v1",
          "index_daily": "index_daily_20260529_v1",
          "stock_daily": "stock_daily_20260529_v1",
          "stock_financial": "stock_financial_20260529_v1",
          "board_membership": "board_membership_20260529_v1",
          "index_membership": "index_membership_20260529_v1",
          "stock_daily_basic": "stock_daily_basic_20260529_v1"
        },
        "p0_count": 0,
        "p1_count": 9,
        "p2_count": 3,
        "created_at": "2026-06-01T04:43:14.228258+08:00",
        "finished_at": "2026-06-01T04:43:14.228258+08:00"
      }
    ],
    "current_active_v1_status": "passed_active",
    "v2_run_row_count": 0
  },
  "v2_run_baseline_zero": true,
  "expected_row_counts": {
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
  "preflight": {
    "execute_allowed": true,
    "blocked_reasons": [],
    "will_execute_sql": false,
    "writes_performed": false,
    "run_id_status": {
      "requested_run_id": "condition_layer_20260529_source_20260529_v2",
      "table_counts": {
        "common_condition_run": 0,
        "common_condition_quality_item": 0,
        "stock_monitor_target": 0,
        "index_monitor_target": 0,
        "board_monitor_target": 0,
        "stock_condition_basis": 0,
        "index_condition_basis": 0,
        "board_condition_basis": 0,
        "stock_condition_pool": 0,
        "index_condition_pool": 0,
        "board_condition_pool": 0,
        "stock_minute_target_scope": 0,
        "index_minute_target_scope": 0,
        "board_minute_target_scope": 0,
        "stock_condition_display_basis": 0,
        "index_condition_display_basis": 0,
        "board_condition_display_basis": 0
      },
      "total_existing_rows": 0,
      "run_id_available": true,
      "read_only": true
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
  "outbox_inbox_checkpoint_before": {
    "common_event_outbox": 151341,
    "common_event_inbox": 56170,
    "common_event_consumer_checkpoint": 4368
  },
  "outbox_inbox_checkpoint_after": {
    "common_event_outbox": 151341,
    "common_event_inbox": 56170,
    "common_event_consumer_checkpoint": 4368
  },
  "outbox_inbox_checkpoint_unchanged": true,
  "writes_performed": false,
  "n2_execute_performed": false,
  "downstream_layers_touched": false,
  "remaining_blockers": [],
  "allow_enter_n2_financial_canonical_active_supersede_execute_final_gate": true,
  "artifacts": {
    "dry_json": "docs/N2_financial_canonical_20260529_dry_run_report.json",
    "dry_md": "docs/N2_FINANCIAL_CANONICAL_20260529_DRY_RUN_REPORT.md",
    "contract_json": "docs/N2_financial_canonical_20260529_execute_contract.json",
    "contract_md": "docs/N2_FINANCIAL_CANONICAL_20260529_EXECUTE_CONTRACT.md",
    "preflight_json": "docs/N2_financial_canonical_20260529_execute_preflight.json",
    "preflight_md": "docs/N2_FINANCIAL_CANONICAL_20260529_EXECUTE_PREFLIGHT.md",
    "final_preflight_json": "docs/N2_financial_canonical_20260529_execute_preflight_after_029.json",
    "refresh_json": "docs/N2_financial_canonical_20260529_preflight_refresh_report.json",
    "refresh_md": "docs/N2_FINANCIAL_CANONICAL_20260529_PREFLIGHT_REFRESH_REPORT.md",
    "rollback": "sql/N2_condition_layer_20260529_financial_v2_rollback.sql"
  }
}
```
