# N2 Financial Canonical 20260529 Execute Post-review

result = POST_REVIEW_PASS

```json
{
  "result": "POST_REVIEW_PASS",
  "run_id": "condition_layer_20260529_source_20260529_v2",
  "v2_status": "passed_active",
  "v1_status": "superseded",
  "active_passed_active_count": 1,
  "rows": {
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
    "stock_minute_target_scope": 4087,
    "index_minute_target_scope": 187,
    "board_minute_target_scope": 942,
    "stock_condition_display_basis": 1862,
    "index_condition_display_basis": 83,
    "board_condition_display_basis": 428
  },
  "expected_rows": {
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
  "row_mismatches": {},
  "quality_rows": 106,
  "quality_by_severity": {
    "P0": 91,
    "P1": 11,
    "P2": 4
  },
  "financial_canonical_pass_through": {
    "basis_mismatch_count": 0,
    "pool_mismatch_count": 0,
    "scope_mismatch_count": 0,
    "display_mismatch_count": 0,
    "canonical_financial_pass_through_mismatch": 0,
    "samples": {
      "basis": [],
      "pool": [],
      "scope": [],
      "display": []
    }
  },
  "event_counts_before": {
    "outbox": 151341,
    "inbox": 56170,
    "checkpoint": 4368
  },
  "event_counts_after": {
    "outbox": 151341,
    "inbox": 56170,
    "checkpoint": 4368
  },
  "event_delta": {
    "outbox": 0,
    "inbox": 0,
    "checkpoint": 0
  },
  "downstream_refs_v2": {
    "common_market_data_run": 0,
    "common_trigger_run": 0,
    "common_action_run": 0
  },
  "rollback_sql": "sql/N2_condition_layer_20260529_financial_v2_rollback.sql",
  "rollback_safe": true,
  "downstream_layers_touched": false,
  "market_data_pulled": false,
  "worker_started": false
}
```
