# N2 Period Context QFQ As-Of Alignment 20260615 Active Supersede Contract

- result: `CONTRACT_PASS`
- source_trade_date: `20260615`
- for_trade_date: `20260616`
- target_run_id: `condition_layer_20260615_source_20260615_for_20260616_v2`
- previous_active_run_id: `condition_layer_20260615_source_20260615_for_20260616_v1`
- overwrite: `true`
- overwrite_semantics: `lineage_supersede_only`
- n3_lineage_auto_switch: `false`
- writes_performed: `false`
- database_written: `false`

## Expected Rows

- `common_condition_run`: `1`
- `common_condition_quality_item`: `103`
- `stock_monitor_target`: `5504`
- `index_monitor_target`: `83`
- `board_monitor_target`: `427`
- `stock_condition_basis`: `5504`
- `index_condition_basis`: `83`
- `board_condition_basis`: `427`
- `stock_condition_pool`: `4215`
- `index_condition_pool`: `183`
- `board_condition_pool`: `307`
- `index_minute_target_scope`: `183`
- `board_minute_target_scope`: `307`
- `stock_minute_target_scope`: `4194`
- `stock_condition_display_basis`: `1822`
- `index_condition_display_basis`: `83`
- `board_condition_display_basis`: `127`

## Quality

- P0/P1/P2: `0/3/3`

## 002831 Golden

- status: `PASS`
- Q: `volume_up / volume_up`
- M: `low_volume_up / low_volume_up`
- W: `low_volume_up / volume_up`
- D: `low_volume_up / low_volume_up`
- Y: `volume_up / volume_up`
- level_up_score: `3098`

## Supersede Semantics

- `active_run_exists` is a prerequisite, not a blocker.
- Execute success writes v2 as `passed_active` and marks v1 as `superseded` after postcheck.
- Existing v1 rows are not deleted or rewritten.

## Rollback

- rollback_sql_path: `sql/N2_period_context_qfq_asof_alignment_20260615_active_supersede_rollback.sql`
- Deletes only v2 rows.
- Restores v1 status to `passed_active`.
- Hard-fails before DELETE/UPDATE if event infra or downstream refs exist.

## Forbidden Scope

No N1 facts, N3/N4/N5/N6 facts, outbox/inbox/checkpoint, market pull, worker, old system, or real trade are written by this artifact gate.
