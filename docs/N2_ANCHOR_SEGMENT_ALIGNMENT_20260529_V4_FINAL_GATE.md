# N2 Anchor Segment Alignment 20260529 V4 Active Supersede Final Gate

Status: PASS

```text
source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
target_run_id = condition_layer_20260529_source_20260529_v4
previous_active_run_id = condition_layer_20260529_source_20260529_v3
overwrite_semantics = lineage_supersede_only
n3_lineage_auto_switch = false
will_execute_sql = false
writes_performed = false
```

## Expected Rows

```json
{
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
}
```

## Golden Proof

- 000600 target: 12.93 / segment 20260518 -> 20260529
- 000543 target: 10.82
- 000027 target: 8.45

## Preflight

```text
execute_allowed_after_confirmation = True
blocked_reasons = []
run_id_available = True
```

## Rollback

Rollback SQL: `sql/N2_anchor_segment_alignment_20260529_v4_rollback.sql`

The rollback clears only v4 rows, restores v3 to `passed_active`, and guards N3/N4/N5/N6 downstream refs.
