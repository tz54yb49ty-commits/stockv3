# N2 Condition Layer 20260526 V2 Execute Contract

status = DESIGN_PASS
execute_status = FINAL_GATE_READY_AFTER_PASSED_ACTIVE_ALIGNMENT

```text
source_trade_date = 20260526
for_trade_date = 20260527
prev_trade_date = 20260526
run_id = condition_layer_20260526_source_20260526_v2
previous_active_run_id = condition_layer_20260526_source_20260526_v1
execute_requires_explicit_overwrite = true
schema_ready = true
passed_active_status_supported = true
preflight_execute_allowed = true
blocked_reasons = []
writes_performed = false
will_execute_sql = false
common_event_outbox_written = false
```

## Rerun Reason

N1 active `index_daily` has expanded from `index_daily_20260526_v2` (9 rows) to `index_daily_20260526_v3` (83 rows). N2 v1 froze the old source version, so v2 must be a new condition run.

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

## Lineage Contract

```json
{
  "rerun_run_id": "condition_layer_20260526_source_20260526_v2",
  "previous_active_run_id": "condition_layer_20260526_source_20260526_v1",
  "new_run_required": true,
  "reuse_or_update_v1_rows": false,
  "delete_v1_rows": false,
  "v1_lineage_remains_auditable": true,
  "n3_lineage_auto_switch": false,
  "overwrite_semantics": "lineage_supersede_only",
  "delete_previous_rows": false,
  "update_previous_rows": false,
  "mark_previous_run_superseded_after_postcheck": true,
  "strict_preserve_v1_active_status_execute_allowed": false,
  "strict_preserve_v1_active_status_blocker": "active_run_exists",
  "future_execute_requires_explicit_overwrite_flag": true,
  "future_execute_status_effect": "after new v2 postcheck passes, common_condition_run.status for v1 becomes superseded and v2 becomes passed_active; v1 rows remain preserved",
  "active_selection_policy": "passed_active > passed",
  "rollback_sql_scope": "delete v2 rows by run_id/source_version only; does not delete v1 rows",
  "optional_restore_previous_active_requires_separate_confirmation": false,
  "rollback_restore_status": "passed_active"
}
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

## Quality

```text
p0_count = 0
p1_count = 3
p2_count = 3
```

## Boundary

- Does not update or delete v1 rows.
- Future execute with `--overwrite` may mark v1 `superseded` only after v2 postcheck passes; v2 becomes `passed_active`.
- New canonical active status is `passed_active`; legacy `passed` remains readable but is not the future active write status.
- `sql/015_condition_run_passed_active_status_migration.sql` has been post-reviewed; schema support is now a required preflight input.
- Does not switch N3/A1/B1 lineage automatically.
- Does not write `common_event_outbox`, `common_event_inbox`, or `common_event_consumer_checkpoint`.
- Rollback must delete only v2 rows, restore v1 to `passed_active`, and block if scoped event/downstream refs to v2 exist.
