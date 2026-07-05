# N4 20260603 Canonical Trigger Execute Rollback Report

- result: `ROLLBACK_PASS`
- layer_role: `N4_trigger`
- execute_run_id: `trigger_execute_20260603_condition_layer_20260602_source_20260602_v1`
- rollback_sql: `sql/N4_20260603_canonical_trigger_execute_rollback.sql`

## Execution

The first user-provided psql command failed before executing SQL because `ASHARE_V3_POSTGRES_DSN` was empty in the shell and psql attempted the default database `chuanfuchen`.

Executed against the v3 runtime database:

```bash
/opt/homebrew/Cellar/postgresql@16/16.14/bin/psql "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3" -v ON_ERROR_STOP=1 \
  -f sql/N4_20260603_canonical_trigger_execute_rollback.sql
```

psql delete summary:

- common_event_outbox: `20334`
- common_trigger_match: `10167`
- common_trigger_state: `10167`
- common_trigger_quality_item: `17`
- common_trigger_run: `1`
- committed: `true`

## Cleanup Summary

- common_trigger_run: `0`
- common_trigger_quality_item: `0`
- common_trigger_state: `0`
- common_trigger_match: `0`
- N4 common_event_outbox: `0`
- common_event_inbox refs: `0`
- common_event_consumer_checkpoint refs: `0`

## Upstream Preservation

N4 context remains passed:

- run_id: `trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1`
- status: `passed`
- P0/P1/P2: `0/0/0`
- context rows stock/index/board/total: `4164/168/890/5222`
- trigger_state/match/outbox counts on context run: `0/0/0`

B1 snapshot remains passed:

- run_id: `realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- status: `passed`
- P0/P1/P2: `0/1/0`
- rows stock/index/board/total: `1963/83/428/2474`
- outbox/inbox/checkpoint refs: `0/0/0`

N2 condition run remains active:

- run_id: `condition_layer_20260602_source_20260602_v1`
- status: `passed_active`
- P0/P1/P2: `0/9/3`

## Downstream Refs

- N5 common_action_run/common_action_event: `0/0`
- N6 user_projection_run/user_signal_projection/user_signal_card/user_notification_queue: `0/0/0/0`
- position refs common_position_event/common_position_state: `0/0`

## Boundary

- N4 matcher was not fixed in this step.
- N4 was not re-executed.
- N5/N6 were not executed.
- No outbox was consumed.
- No worker was started.
- No delivery, notification, push, voice, mobile, sim, position, or real trade path was touched.
- N1/N2/N3 facts and N4 context were not modified.

## Next Route

Return to `runtime_control` for N4 post-rollback review. Do not re-execute N4 until matcher fix and refreshed dry-run/preflight gates pass.
