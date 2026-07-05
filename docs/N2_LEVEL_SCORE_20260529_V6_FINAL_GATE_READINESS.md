# N2 031 Level Score v6 Final Gate Readiness

status = PASS

```text
target_run_id = condition_layer_20260529_source_20260529_v6
previous_active_run_id = condition_layer_20260529_source_20260529_v5
schema_ready = True
level_score_fields_ready = True
v6_baseline_rows = 0
golden_passed = True
level_score_all_ready = True
P0/P1/P2 = 0/6/3
overwrite_semantics = lineage_supersede_only
n3_lineage_auto_switch = false
writes_performed = false
will_execute_sql = false
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 428,
  "board_condition_display_basis": 428,
  "board_condition_pool": 942,
  "board_minute_target_scope": 942,
  "board_monitor_target": 428,
  "common_condition_quality_item": 106,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 83,
  "index_condition_pool": 187,
  "index_minute_target_scope": 187,
  "index_monitor_target": 83,
  "stock_condition_basis": 5506,
  "stock_condition_display_basis": 1862,
  "stock_condition_pool": 4106,
  "stock_minute_target_scope": 4087,
  "stock_monitor_target": 5506
}
```

## Golden

```json
{
  "000543": {
    "actual": {
      "level_down_score": 0,
      "level_up_score": 3124,
      "period_transition_d": "volume_up",
      "period_transition_m": "volume_up",
      "period_transition_q": "volume_up",
      "period_transition_w": "volume_up",
      "period_transition_y": "volume_up"
    },
    "expected": {
      "level_down_score": 0,
      "level_up_score": 3124,
      "name": "皖能电力"
    },
    "found": true,
    "passed": true
  },
  "000600": {
    "actual": {
      "level_down_score": 0,
      "level_up_score": 3124,
      "period_transition_d": "volume_up",
      "period_transition_m": "volume_up",
      "period_transition_q": "volume_up",
      "period_transition_w": "volume_up",
      "period_transition_y": "volume_up"
    },
    "expected": {
      "level_down_score": 0,
      "level_up_score": 3124,
      "name": "建投能源"
    },
    "found": true,
    "passed": true
  },
  "300327": {
    "actual": {
      "level_down_score": 125,
      "level_up_score": 2999,
      "period_transition_d": "volume_up",
      "period_transition_m": "volume_up",
      "period_transition_q": "low_volume_up",
      "period_transition_w": "volume_up",
      "period_transition_y": "volume_up"
    },
    "expected": {
      "level_down_score": 125,
      "level_up_score": 2999,
      "name": "中颖电子"
    },
    "found": true,
    "passed": true
  }
}
```

## Rollback

```text
/Users/chuanfuchen/Documents/A股监控系统v3/sql/N2_level_score_20260529_v6_rollback.sql
```
