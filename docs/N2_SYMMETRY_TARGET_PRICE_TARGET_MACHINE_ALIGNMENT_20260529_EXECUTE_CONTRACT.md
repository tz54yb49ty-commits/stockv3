# N2 Symmetry Target Price 20260529 v3 Execute Contract

status = DESIGN_PASS

```text
source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
target_run_id = condition_layer_20260529_source_20260529_v3
previous_active_run_id = condition_layer_20260529_source_20260529_v2
overwrite_semantics = lineage_supersede_only
n3_lineage_auto_switch = False
writes_performed = False
will_execute_sql = False
blocked_reasons = []
```

## Expected Rows With Display

```json
{
  "board_condition_basis": 428,
  "board_condition_display_basis": 127,
  "board_condition_pool": 284,
  "board_minute_target_scope": 284,
  "board_monitor_target": 428,
  "common_condition_quality_item": 106,
  "common_condition_run": 1,
  "index_condition_basis": 83,
  "index_condition_display_basis": 9,
  "index_condition_pool": 21,
  "index_minute_target_scope": 21,
  "index_monitor_target": 83,
  "stock_condition_basis": 5506,
  "stock_condition_display_basis": 1871,
  "stock_condition_pool": 4106,
  "stock_minute_target_scope": 4106,
  "stock_monitor_target": 5506
}
```

## Golden / Divergence

```json
{
  "golden_checks": {
    "000027_buy_target_8_45": true,
    "000543_break_20260526": true,
    "000543_buy_target_10_82": true,
    "000543_policy_official_high_low": true
  },
  "raw_high_low_divergence": {
    "000027": {
      "raw_high_low_target_price": "8.90",
      "target_machine_adjusted_body_boundary_target_price": "8.45"
    },
    "000543": {
      "raw_high_low_target_price": "11.14",
      "target_machine_adjusted_body_boundary_target_price": "10.82"
    },
    "interpretation": "OFFICIAL_HIGH_LOW is the target-machine canonical trace label for this gate, but current v3 N1 raw high/low must not be substituted for the target-machine adjusted body boundary without a separate N1/N2 alignment gate."
  }
}
```

## Rollback

- rollback_sql_path: `sql/N2_symmetry_target_price_target_machine_alignment_20260529_rollback.sql`
- delete_only_run_id: `condition_layer_20260529_source_20260529_v3`
- restore_previous_active_run_id: `condition_layer_20260529_source_20260529_v2`
- downstream refs guard: true
