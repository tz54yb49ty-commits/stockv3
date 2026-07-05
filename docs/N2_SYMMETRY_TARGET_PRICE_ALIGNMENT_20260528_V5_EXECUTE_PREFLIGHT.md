# N2 Symmetry Target Price Alignment v5 Execute Preflight

source_trade_date = 20260528
for_trade_date = 20260529
target_run_id = condition_layer_20260528_source_20260528_v5
previous_active_run_id = condition_layer_20260528_source_20260528_v4
overwrite_semantics = lineage_supersede_only
n3_lineage_auto_switch = false
writes_performed = false


status = PASS
execute_allowed = True
blocked_reasons = []

## Guards

```json
{
  "golden_target_price_passed": true,
  "trace_contains_target_components": true,
  "full_dry_run_p0_zero": true,
  "current_active_is_v4": true,
  "target_run_baseline_zero": true,
  "target_run_downstream_refs_zero": true,
  "passed_active_count_one": true,
  "rollback_sql_has_guard": true,
  "n3_lineage_auto_switch_false": true
}
```

## Baseline

```text
target_run_baseline_total = 0
downstream_ref_guard_total = 0
current_active_run_id = condition_layer_20260528_source_20260528_v4
current_active_status = passed_active
passed_active_count = 1
```

## Expected Rows

| Stage | Stock | Index | Board |
|---|---:|---:|---:|
| condition_basis | 5506 | 83 | 428 |
| condition_pool | 4271 | 18 | 263 |
| minute_target_scope | 4271 | 18 | 263 |
| condition_display_basis | 2021 | 9 | 127 |
