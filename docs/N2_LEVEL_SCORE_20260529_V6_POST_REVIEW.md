# N2 Level Score v6 Post-review

status = POST_REVIEW_PASS

```text
target_run_id = condition_layer_20260529_source_20260529_v6
previous_active_run_id = condition_layer_20260529_source_20260529_v5
active_passed_count = 1
row_match = true
level_score_ok = true
golden_ok = true
outbox_inbox_checkpoint_delta = {'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}
rollback_safe = true
n3_lineage_auto_switch = false
market_data_pulled = false
```

## Rows

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
  },
  "monitor_target": {
    "board": 428,
    "index": 83,
    "stock": 5506
  }
}
```

## Golden

```json
{
  "000543": {
    "code": "000543",
    "level_down_score": 0,
    "level_up_score": 3124,
    "name": "皖能电力",
    "period_transition_d": "volume_up",
    "period_transition_m": "volume_up",
    "period_transition_q": "volume_up",
    "period_transition_w": "volume_up",
    "period_transition_y": "volume_up"
  },
  "000600": {
    "code": "000600",
    "level_down_score": 0,
    "level_up_score": 3124,
    "name": "建投能源",
    "period_transition_d": "volume_up",
    "period_transition_m": "volume_up",
    "period_transition_q": "volume_up",
    "period_transition_w": "volume_up",
    "period_transition_y": "volume_up"
  },
  "300327": {
    "code": "300327",
    "level_down_score": 125,
    "level_up_score": 2999,
    "name": "中颖电子",
    "period_transition_d": "volume_up",
    "period_transition_m": "volume_up",
    "period_transition_q": "low_volume_up",
    "period_transition_w": "volume_up",
    "period_transition_y": "volume_up"
  }
}
```

## Rollback

```text
/Users/chuanfuchen/Documents/A股监控系统v3/sql/N2_level_score_20260529_v6_rollback.sql
```
