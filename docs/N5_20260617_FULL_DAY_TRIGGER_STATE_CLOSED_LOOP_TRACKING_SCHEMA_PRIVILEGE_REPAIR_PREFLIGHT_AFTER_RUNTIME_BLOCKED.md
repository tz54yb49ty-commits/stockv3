# N5 Tracking Schema Privilege Repair Preflight

Result: `PREFLIGHT_PASS`

## Inputs

- Blocked runtime preflight: `docs/N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_RUNTIME_PREFLIGHT_AFTER_TRACKING_IMPLEMENT_PASS.json`
- Tracking table: `common_action_tracking_state`
- Runtime role: `ashare_v3_user`
- Source trigger run: `trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- Planned action run: `action_consumer_dry_run_20260617_full_day_state_closed_loop__trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`

## Privilege Blocker Proof

- Prior runtime preflight result: `BLOCKED`
- Blocker count: `1`
- Blocker: `tracking_table_runtime_role_privileges_missing`
- Current runtime role privileges on `public.common_action_tracking_state`:
  - `SELECT=false`
  - `INSERT=false`
  - `UPDATE=false`
  - `DELETE=false`
- Required privileges: `SELECT, INSERT, UPDATE, DELETE`

## Table State Proof

- `common_action_tracking_state` exists.
- Required columns exist.
- Unique key is enforced on `(run_id, state_key)`.
- Table owner read-only count:
  - total rows: `0`
  - rows for planned action run or source trigger run: `0`

## SQL Outputs

- Grant SQL: `sql/N5_20260617_full_day_action_tracking_state_privilege_grant.sql`
- Rollback SQL: `sql/N5_20260617_full_day_action_tracking_state_privilege_grant_rollback.sql`

Grant scope:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.common_action_tracking_state
TO ashare_v3_user;
```

Rollback scope:

```sql
REVOKE SELECT, INSERT, UPDATE, DELETE
ON TABLE public.common_action_tracking_state
FROM ashare_v3_user;
```

## Forbidden Scope Proof

- GRANT executed: `false`
- REVOKE executed: `false`
- N5 runtime executed: `false`
- N4 outbox consumed/updated: `false`
- inbox/checkpoint written: `false`
- N6 entered: `false`
- worker/scheduler started: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- old system read/modified: `false`

## Allowed Next Prompt

```text
layer_role=N5_action.
Enter N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_TRACKING_SCHEMA_PRIVILEGE_REPAIR_EXECUTE_AFTER_PREFLIGHT_PASS.
Use:
- preflight_artifact=docs/N5_20260617_FULL_DAY_TRIGGER_STATE_CLOSED_LOOP_TRACKING_SCHEMA_PRIVILEGE_REPAIR_PREFLIGHT_AFTER_RUNTIME_BLOCKED.json
- grant_sql_path=sql/N5_20260617_full_day_action_tracking_state_privilege_grant.sql
- rollback_sql_path=sql/N5_20260617_full_day_action_tracking_state_privilege_grant_rollback.sql
- tracking_table=common_action_tracking_state
- runtime_role=ashare_v3_user
- source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- planned_action_run_id=action_consumer_dry_run_20260617_full_day_state_closed_loop__trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1

Task:
Execute the scoped tracking table privilege GRANT SQL only, then post-review privileges.

Forbidden:
- Do not execute N5 runtime.
- Do not consume/update N4 outbox.
- Do not write inbox/checkpoint.
- Do not enter N6.
- Do not start worker/scheduler.
- Do not touch voice/mobile/sim/position/order/real trade/old system.
```
