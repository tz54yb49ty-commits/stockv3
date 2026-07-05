# N2 Target Price Double Adjustment 20260615 v3 Active Supersede Post Review

status = POST_REVIEW_PASS

```text
execute_run_id = condition_layer_20260615_source_20260615_for_20260616_v3
source_trade_date = 20260615
for_trade_date = 20260616
writes_performed = true
will_execute_sql = true
migration_performed = false
minute_kline_pulled = false
downstream_layers_touched = false
n3_lineage_auto_switch = false
```

## Active Supersede

```json
[
  {
    "run_id": "condition_layer_20260615_source_20260615_for_20260616_v2",
    "status": "superseded",
    "source_trade_date": "20260615",
    "for_trade_date": "20260616"
  },
  {
    "run_id": "condition_layer_20260615_source_20260615_for_20260616_v3",
    "status": "passed_active",
    "source_trade_date": "20260615",
    "for_trade_date": "20260616"
  }
]
```

```text
active_run_count = 1
```

## Row Counts

```json
{
  "board_condition_basis": 427,
  "board_condition_display_basis": 127,
  "board_condition_pool": 307,
  "board_minute_target_scope": 307,
  "board_monitor_target": 427,
  "common_condition_quality_item": 103,
  "index_condition_basis": 83,
  "index_condition_display_basis": 83,
  "index_condition_pool": 183,
  "index_minute_target_scope": 183,
  "index_monitor_target": 83,
  "stock_condition_basis": 5504,
  "stock_condition_display_basis": 1822,
  "stock_condition_pool": 4215,
  "stock_minute_target_scope": 4194,
  "stock_monitor_target": 5504
}
```

## Quality

```json
[
  {
    "severity": "P0",
    "status": "passed",
    "count": 91
  },
  {
    "severity": "P1",
    "status": "passed",
    "count": 4
  },
  {
    "severity": "P1",
    "status": "warning",
    "count": 4
  },
  {
    "severity": "P2",
    "status": "warning",
    "count": 4
  }
]
```

## 002831 Live Proof

```text
buy_target_price = 40.67
reference_target_price = 40.67
secondary_target_price = 33.9
Q segment = 20251009 -> 20260615
Q low = 20251021 / 17.86
Q high = 20260520 / 31.65
amplitude = 13.79
base_price = 26.88
target = 40.67
```

## Live Diff Proof

```json
{
  "buy_target_price": 787,
  "reference_target_price": 1252,
  "secondary_target_price": 58,
  "sell_target_price": 775
}
```

Note: dry-run aggregate changed_count_vs_active_v2 = 814 is historical dry-run aggregate evidence, not the post-execute field-level diff.

## Boundary Proof

```json
{
  "event_delta": {"common_event_outbox": 0, "common_event_inbox": 0, "common_event_consumer_checkpoint": 0},
  "v3_downstream_refs": {"common_market_data_run": 0, "common_trigger_run": 0, "common_action_run": 0, "user_projection_run": 0},
  "market_data_pulled": false,
  "worker_started": false
}
```

## Rollback

```text
rollback_sql_path = sql/N2_target_price_double_adjustment_20260615_v3_active_supersede_rollback.sql
rollback_sql_executed = false
restores_v2_status_passed_active = true
guards_event_infra_and_downstream_refs = true
no_DROP_TRUNCATE_CASCADE = true
```

Recommended next gate: N3_LINEAGE_REFRESH_FOR_N2_20260615_V3_READINESS_GATE
