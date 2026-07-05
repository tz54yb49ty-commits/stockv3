# N2 Target Price Double Adjustment 20260615 Active Supersede Preflight

status = PREFLIGHT_READY_FOR_USER_CONFIRMATION

```text
source_trade_date = 20260615
for_trade_date = 20260616
target_run_id = condition_layer_20260615_source_20260615_for_20260616_v3
previous_active_run_id = condition_layer_20260615_source_20260615_for_20260616_v2
overwrite = true
overwrite_semantics = lineage_supersede_only
active_run_exists_is_blocker = false
blocked_reasons = [user_confirmation_required]
execute_allowed = false only because user_confirmation_required
writes_performed = false
will_execute_sql = false
n3_lineage_auto_switch = false
```

## 002831 Proof

```text
old active v2 buy / secondary = 44.87 / 33.90
repaired preview buy / secondary = 40.67 / 33.90
Q segment = 20251009 -> 20260615
Q low = 20251021 / 17.86
Q high = 20260520 / 31.65
amplitude = 13.79
base_price = 26.88
target = 40.67
low point raw date = 20251021
single adjusted entity low = 17.86
double adjusted entity low = 12.51
```

## Dry-run / Quality

```text
full_dry_run = FULL_DRY_RUN_PASS
changed_count_vs_active_v2 = 814
P0/P1/P2 = 0/3/3
```

## Expected Rows

```json
{
  "board_condition_basis": 427,
  "board_condition_display_basis": 127,
  "board_condition_pool": 307,
  "board_minute_target_scope": 307,
  "board_monitor_target": 427,
  "common_condition_quality_item": 103,
  "common_condition_run": 1,
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

## Rollback

```text
rollback_sql_path = sql/N2_target_price_double_adjustment_20260615_v3_active_supersede_rollback.sql
rollback_scope = delete only target v3 rows and restore v2.status=passed_active
hard_fail_before_delete_or_update = true
guard_outbox_inbox_checkpoint = true
guard_N3_N4_N5_N6_refs = true
no_drop_truncate_cascade = true
```
