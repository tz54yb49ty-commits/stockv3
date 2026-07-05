# N2 Symmetry Secondary Anchor 20260529 V5 Preflight Review

Status: `BLOCKED`

This review reran the N2 v5 full dry-run / execute preflight after 030 schema
migration. It did not execute N2, did not write condition business rows, did
not pull market data, and did not enter N3/N4/N5/N6.

## Preflight

```text
target_run_id = condition_layer_20260529_source_20260529_v5
previous_active_run_id = condition_layer_20260529_source_20260529_v4
source_trade_date / for_trade_date / prev_trade_date = 20260529 / 20260601 / 20260529
schema_ready = true
030 secondary-anchor columns ready = true
v5 baseline rows = 0
execute_allowed = true
blocked_reasons = []
writes_performed = false
will_execute_sql = false
```

Expected rows from the refreshed preflight:

```text
common_condition_run = 1
common_condition_quality_item = 78
stock_monitor_target = 5506
index_monitor_target = 83
board_monitor_target = 428
stock_condition_basis = 5506
index_condition_basis = 83
board_condition_basis = 428
stock_condition_pool = 4106
index_condition_pool = 187
board_condition_pool = 942
stock_minute_target_scope = 4087
index_minute_target_scope = 187
board_minute_target_scope = 942
P0/P1/P2 = 0/6/3
```

## Golden Review

Preserved golden rows:

```text
000600 / 20260529 = 12.93
000543 / 20260529 = 10.82
000027 / 20260529 = 8.45
```

Blocked golden row:

```text
300327 / 20260529 expected:
  buy_target_price = 38.27
  reference_target_price = 38.27
  up_secondary_target_price = 33.04

300327 / 20260529 actual live dry-run:
  buy_target_price = 38.11
  reference_target_price = 38.11
  up_secondary_target_price = 32.98
```

Live trace for 300327:

```text
main_up_anchor = Y
up_reference_period = Q
up_trend_start_date = 20250102
up_trend_end_date = 20260529
up_segment_high = 34.28
up_segment_low = 19.41
up_amplitude = 14.87
up_trend_break_date = 20251231
up_base_price = 23.24

up_secondary_anchor = W
up_secondary_reference_period = D
up_secondary_trend_start_date = 20260526
up_secondary_trend_end_date = 20260529
up_secondary_amplitude = 3.38
up_secondary_base_price = 29.60
up_secondary_target_price = 32.98
```

## Conclusion

The schema and preflight gates are clean, but the target-machine golden for
300327 is not matched on live N1 facts. Therefore the active supersede final
gate must remain blocked until the 300327 source/golden divergence is resolved.

Next step:

```text
N2 300327 target-machine parity investigation
```

This should compare the target-machine source series and boundary policy for
300327 against N1 `stock_daily_bar_fact` without reading old-system data unless
explicitly authorized.
