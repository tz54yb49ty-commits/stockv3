# N2 Condition Layer 20260529 Execute Contract

- run_id_suggestion: `condition_layer_20260529_source_20260529_v1`
- execute_request_allowed: `False`
- user_confirmed: `False`
- overwrite: `False`
- overwrite_semantics: `new_run_no_overwrite`
- n3_lineage_auto_switch: `false`
- rollback_sql_path: `sql/N2_condition_layer_20260529_rollback.sql`
- boundary: no N3/N4/N5/N6, no worker, no outbox/inbox/checkpoint, no market data pull.

```json
{
  "expected_rows_with_display": {
    "board_condition_basis": 428,
    "board_condition_display_basis": 428,
    "board_condition_pool": 942,
    "board_minute_target_scope": 942,
    "board_monitor_target": 428,
    "common_condition_quality_item": 109,
    "common_condition_run": 1,
    "index_condition_basis": 83,
    "index_condition_display_basis": 83,
    "index_condition_pool": 187,
    "index_minute_target_scope": 187,
    "index_monitor_target": 83,
    "stock_condition_basis": 5506,
    "stock_condition_display_basis": 1973,
    "stock_condition_pool": 4342,
    "stock_minute_target_scope": 4323,
    "stock_monitor_target": 5506
  },
  "policy_metadata": {
    "policy_diff_summary": {
      "board": {
        "after_key_count": 18,
        "before_key_count": 18,
        "changed": false,
        "changed_keys": [],
        "summary": "unchanged"
      },
      "index": {
        "after_key_count": 16,
        "before_key_count": 16,
        "changed": false,
        "changed_keys": [],
        "summary": "unchanged"
      },
      "stock": {
        "after_key_count": 25,
        "before_key_count": 25,
        "changed": false,
        "changed_keys": [],
        "summary": "unchanged"
      }
    },
    "policy_hash": "ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576",
    "policy_id": "n2_default_policy",
    "policy_source": "8782_console",
    "policy_version": "v4",
    "previous_policy_hash": "ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576"
  }
}
```
