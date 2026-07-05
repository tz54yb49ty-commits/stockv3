# N2 Condition Layer 20260529 Execute Preflight

- status: `BLOCKED`
- execute_allowed: `False`
- blocked_reasons: `['user_confirmation_required']`
- user_confirmation_required: `True`
- run_id_available: `True`
- active_run_exists: `False`
- writes_performed: `false`

```json
{
  "active_run_status": {
    "active_exists": false,
    "active_run_count": 0,
    "active_runs": [],
    "blocked_by_active_run": false,
    "blocked_by_multiple_passed_active": false,
    "canonical_active_run_count": 0,
    "canonical_active_status": "passed_active",
    "default_policy": "reject_if_active_exists",
    "legacy_active_run_count": 0,
    "legacy_active_status": "passed",
    "overwrite": false,
    "read_only": true,
    "table_exists": true
  },
  "expected_row_counts_by_stage": {
    "condition_basis": {
      "board": 428,
      "index": 83,
      "stock": 5506
    },
    "condition_display_basis": {
      "board": 428,
      "index": 83,
      "stock": 1973
    },
    "condition_pool": {
      "board": 942,
      "index": 187,
      "stock": 4342
    },
    "minute_target_scope": {
      "board": 942,
      "index": 187,
      "stock": 4323
    },
    "monitor_target": {
      "board": 428,
      "index": 83,
      "stock": 5506
    },
    "quality_item": 109
  },
  "run_id_status": {
    "read_only": true,
    "requested_run_id": "condition_layer_20260529_source_20260529_v1",
    "run_id_available": true,
    "table_counts": {
      "board_condition_basis": 0,
      "board_condition_display_basis": 0,
      "board_condition_pool": 0,
      "board_minute_target_scope": 0,
      "board_monitor_target": 0,
      "common_condition_quality_item": 0,
      "common_condition_run": 0,
      "index_condition_basis": 0,
      "index_condition_display_basis": 0,
      "index_condition_pool": 0,
      "index_minute_target_scope": 0,
      "index_monitor_target": 0,
      "stock_condition_basis": 0,
      "stock_condition_display_basis": 0,
      "stock_condition_pool": 0,
      "stock_minute_target_scope": 0,
      "stock_monitor_target": 0
    },
    "total_existing_rows": 0
  }
}
```
