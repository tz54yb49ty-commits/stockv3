# N2 Symmetry Secondary Anchor 20260529 V5 After N1 Repair Final Gate

Status: `PASS`

This review was read-only. It did not execute N2, did not write `condition_*`
business rows, did not pull market data, did not enter N3/N4/N5/N6, and did not
start a worker.

## Preflight

```text
target_run_id = condition_layer_20260529_source_20260529_v5
previous_active_run_id = condition_layer_20260529_source_20260529_v4
source_trade_date / for_trade_date / prev_trade_date = 20260529 / 20260601 / 20260529
schema_ready = true
030 secondary-anchor columns ready = true
v5 baseline rows = 0
current active = condition_layer_20260529_source_20260529_v4 / passed_active
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

```text
000600 / 20260529 = 12.93
000543 / 20260529 = 10.82
000027 / 20260529 = 8.45
```

After the N1 `20260525` 300327 repair, the previously blocked row now matches:

```text
300327 / 20260529:
  main_up_anchor = Y
  up_reference_period = Q
  up_trend_start_date = 20250102
  up_trend_end_date = 20260529
  up_segment_low/high = 19.25 / 34.28
  up_amplitude = 15.03
  up_base_price = 23.24
  buy_target_price = reference_target_price = 38.27

  up_secondary_anchor = W
  up_secondary_reference_period = D
  up_secondary_trend_start_date = 20260525
  up_secondary_trend_end_date = 20260529
  up_secondary_amplitude = 3.44
  up_secondary_base_price = 29.60
  up_secondary_target_price = secondary_target_price = 33.04
```

Trace:

```text
adjustment_policy = ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR
primary_current_adj_factor = 3.1316
secondary_current_adj_factor = 3.1316
```

## Rollback

Rollback SQL:

```text
sql/N2_symmetry_secondary_anchor_20260529_v5_rollback.sql
```

It only clears `condition_layer_20260529_source_20260529_v5` rows, restores
`condition_layer_20260529_source_20260529_v4` to `passed_active`, guards N3/N4/N5/N6
downstream refs, and does not touch outbox/inbox/checkpoint.

## Conclusion

`condition_layer_20260529_source_20260529_v5` may enter the execute user
confirmation point. Execute must be `lineage_supersede_only`; N3 lineage must
not auto-switch.
