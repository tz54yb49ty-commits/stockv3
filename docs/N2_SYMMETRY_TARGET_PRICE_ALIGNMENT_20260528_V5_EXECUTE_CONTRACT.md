# N2 Symmetry Target Price Alignment v5 Execute Contract

source_trade_date = 20260528
for_trade_date = 20260529
target_run_id = condition_layer_20260528_source_20260528_v5
previous_active_run_id = condition_layer_20260528_source_20260528_v4
overwrite_semantics = lineage_supersede_only
n3_lineage_auto_switch = false
writes_performed = false


status = PASS
blocked_reasons = []

## Golden

```text
000027 buy_target_price/reference_target_price = 8.42 / 8.42
target_price_match = True
```

## Expected Rows

| Stage | Stock | Index | Board |
|---|---:|---:|---:|
| condition_basis | 5506 | 83 | 428 |
| condition_pool | 4271 | 18 | 263 |
| minute_target_scope | 4271 | 18 | 263 |
| condition_display_basis | 2021 | 9 | 127 |

## Write Scope

Only N2 condition-layer run/quality/monitor_target/basis/pool/scope/display tables.

## Rollback

- rollback_sql_path = sql/N2_symmetry_target_price_alignment_20260528_v5_rollback.sql
- delete only v5 rows
- restore v4.status = passed_active
- guard N3/N4/N5/N6 refs
- do not touch outbox/inbox/checkpoint
