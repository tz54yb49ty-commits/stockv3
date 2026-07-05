# N2 Condition Layer 20260526 Full Dry-run Report

status = FULL_DRY_RUN_PASS

```text
source_trade_date = 20260610
for_trade_date = 20260611
prev_trade_date = 20260610
planned_run_id = condition_layer_20260610_to_20260611_execute
run_id_suggestion = condition_layer_20260610_source_20260610_for_20260611_v1
writes_performed = false
common_event_outbox_written = false
downstream_layers_touched = false
worker_started = false
```

## Source Readiness

```text
ready_passed = True
missing_data_types = []
expected_condition_stock_universe = 5510
excluded_from_condition_universe = 0
```

## Row Counts

| Stage | Stock | Index | Board |
|---|---:|---:|---:|
| condition_basis | 5510 | 83 | 428 |
| condition_pool | 4046 | 185 | 268 |
| minute_target_scope | 4027 | 185 | 268 |
| condition_display_basis | 1890 | 83 | 127 |

## Quality

```text
p0_count = 0
p1_count = 6
p2_count = 3
```

## Display Basis

`condition_display_basis` is N6 read-only input and does not enter N3/N4/N5.
