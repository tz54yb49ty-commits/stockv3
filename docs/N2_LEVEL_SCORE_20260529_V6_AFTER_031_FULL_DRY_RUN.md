# N2 031 Level Score v6 Full Dry-run

status = FULL_DRY_RUN_PASS

```text
source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
target_run_id = condition_layer_20260529_source_20260529_v6
previous_active_run_id = condition_layer_20260529_source_20260529_v5
P0/P1/P2 = 0/6/3
writes_performed = false
will_execute_sql = false
```

## Row Counts

```json
{
  "condition_basis": {
    "board": 428,
    "index": 83,
    "stock": 5506
  },
  "condition_display_basis": {
    "board": 428,
    "index": 83,
    "stock": 1862
  },
  "condition_pool": {
    "board": 942,
    "index": 187,
    "stock": 4106
  },
  "minute_target_scope": {
    "board": 942,
    "index": 187,
    "stock": 4087
  }
}
```

## Level Score Golden

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

## Level Score Coverage

```json
{
  "condition_basis": {
    "board": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 428
    },
    "index": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 83
    },
    "stock": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 5506
    }
  },
  "condition_display_basis": {
    "board": {
      "level_score_inheritance": "from primary condition_basis via build_display_row",
      "row_count": 428,
      "row_payload_omitted": true
    },
    "index": {
      "level_score_inheritance": "from primary condition_basis via build_display_row",
      "row_count": 83,
      "row_payload_omitted": true
    },
    "stock": {
      "level_score_inheritance": "from primary condition_basis via build_display_row",
      "row_count": 1862,
      "row_payload_omitted": true
    }
  },
  "condition_pool": {
    "board": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 942
    },
    "index": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 187
    },
    "stock": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 4106
    }
  },
  "minute_target_scope": {
    "board": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 942
    },
    "index": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 187
    },
    "stock": {
      "invalid_level_down_score": 0,
      "invalid_level_up_score": 0,
      "level_down_score_missing": 0,
      "level_up_score_missing": 0,
      "row_count": 4087
    }
  }
}
```
