# N2 Display Scope Alignment 20260528 v3 Execute Preflight

layer_role = N2_condition
status = PASS

```text
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
run_id = condition_layer_20260528_source_20260528_v3
previous_active_run_id = condition_layer_20260528_source_20260528_v2
overwrite = true
overwrite_semantics = lineage_supersede_only
delete_previous_rows = false
update_previous_rows = false
mark_previous_run_superseded_after_postcheck = true
n3_lineage_auto_switch = false
execute_allowed = true
blocked_reasons = []
will_execute_sql = false
writes_performed = false
```

## Expected Rows

| Table family | Stock | Index | Board |
|---|---:|---:|---:|
| monitor_target | 5506 | 83 | 428 |
| condition_basis | 5506 | 83 | 428 |
| condition_pool | 4271 | 18 | 263 |
| minute_target_scope | 4271 | 18 | 263 |
| condition_display_basis | 2021 | 9 | 127 |

## Display Alignment

```text
condition_display_basis source = minute_target_scope selected identities
monitor_target semantics = full audit universe, not user display basis
N6 reads condition_display_basis
N3/N4/N5 do not read condition_display_basis
```

## Rollback

```text
rollback_sql = sql/N2_condition_layer_20260528_v3_display_scope_alignment_rollback.sql
strategy = delete v3 rows by run_id/source_version, then restore v2.status=passed_active
guard = BLOCK if v3 has N3/N4/N5/N6 downstream references
```

## Boundary

```text
common_event_outbox_written = false
common_event_inbox_written = false
common_event_consumer_checkpoint_written = false
N3/N4/N5/N6 entered = false
worker_started = false
old_system_touched = false
market_data_pulled = false
```

## Preflight Note

`execute_allowed=true` appears here only because this is the user-confirmed overwrite final gate artifact. This artifact still performs no SQL writes.
