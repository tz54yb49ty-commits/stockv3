# N2 Condition Layer 20260526 V2 Execute Preflight

status = PREFLIGHT_PASS_AFTER_015_STATUS_MIGRATION

```text
source_trade_date = 20260526
for_trade_date = 20260527
prev_trade_date = 20260526
requested_run_id = condition_layer_20260526_source_20260526_v2
schema_ready = true
passed_active_status_supported = true
preflight_execute_allowed = true
blocked_reasons = []
writes_performed = false
will_execute_sql = false
read_only_database_checks = true
```

## Active Lineage

```text
canonical_active_status = passed_active
legacy_active_status = passed
canonical_active_run_count = 0
legacy_active_run_count = 1
current legacy active run = condition_layer_20260526_source_20260526_v1
blocked_by_multiple_passed_active = false
overwrite = true
```

The final execute may proceed only with explicit `--overwrite`, `--execute`, and
`--user-confirmed`. The overwrite semantics are lineage supersede only: v2 is
created as a new run, postchecked, then marked `passed_active`; v1 is marked
`superseded` and its rows remain preserved.

## Scoped Baseline

```text
v2 target rows total = 0
run_id_available = true
common_event_outbox refs for v2 = 0
common_event_inbox refs for v2 = 0
common_event_consumer_checkpoint refs for v2 = 0
N3/N4/N5/N6 refs for v2 = 0
```

## Expected Rows With Display

| Table | Rows |
|---|---:|
| `common_condition_run` | 1 |
| `common_condition_quality_item` | 104 |
| `stock_monitor_target` | 5504 |
| `index_monitor_target` | 83 |
| `board_monitor_target` | 428 |
| `stock_condition_basis` | 5504 |
| `index_condition_basis` | 83 |
| `board_condition_basis` | 428 |
| `stock_condition_pool` | 4291 |
| `index_condition_pool` | 19 |
| `board_condition_pool` | 264 |
| `index_minute_target_scope` | 19 |
| `board_minute_target_scope` | 264 |
| `stock_minute_target_scope` | 4291 |
| `stock_condition_display_basis` | 5504 |
| `index_condition_display_basis` | 83 |
| `board_condition_display_basis` | 428 |

## Quality

```text
p0_count = 0
p1_count = 3
p2_count = 3
P1/P2 are recorded warnings and do not block the final execute gate.
```

## Future Execute Semantics

```text
v2.status = passed_active
v1.status = superseded
delete_previous_rows = false
update_previous_rows = false
mark_previous_run_superseded_after_postcheck = true
n3_lineage_auto_switch = false
```

## Rollback Semantics

```text
delete only v2 rows by run_id/source_version
restore v1.status = passed_active
do not delete v1 rows
do not touch N3/A1/B1 v1 lineage
rollback is blocked if v2 has outbox/inbox/checkpoint refs
rollback is blocked if N3/N4/N5/N6 refs to v2 exist
rollback is blocked if v1 is missing
```

## Execute Command

```bash
PYTHONPATH=src python3 scripts/run_condition_layer_execute.py \
  --source-trade-date 20260526 \
  --run-id condition_layer_20260526_source_20260526_v2 \
  --execute \
  --user-confirmed \
  --overwrite \
  --operator codex \
  --confirmation-note 20260526-N2-v2-final-execute-passed-active
```

## Forbidden Writes

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
N3/N4/N5/N6
worker
old system
```
