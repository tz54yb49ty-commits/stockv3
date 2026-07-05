# N4 Projection Matcher 20260608 Until 15:00 Unified Output Retry Rollback SQL Regeneration Report

## Result

REGENERATION_PASS

## Target

- target_run_id: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- scoped_consumer_name: `n4_projection_matcher_consumer_v1_until_1500_unified_output_retry`
- rollback SQL: `sql/N4_projection_matcher_20260608_until_1500_unified_output_retry_rollback.sql`

## SQL Repair Summary

- Replaced the runner-overwritten manual hard-fail template with downstream-aware scoped rollback SQL.
- The SQL hard-fails before the first executable DELETE/UPDATE.
- The SQL excludes this run's scoped N4 consumer checkpoint from downstream checkpoint guards:
  - `consumer_name=n4_projection_matcher_consumer_v1_until_1500_unified_output_retry`
  - `source_layer=N3_market_data`
  - `checkpoint_payload.execute_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- The SQL preserves N3 facts, this source run's N3 MarketSnapshotUpdated outbox rows, N2/N1 facts, and the old FULL repair retry lineage.
- The SQL contains no `DROP`, `TRUNCATE`, or `CASCADE`.

## Live Readiness Proof

| Proof | Value |
|---|---:|
| common_trigger_run | 1 |
| common_trigger_quality_item | 10 |
| common_trigger_state | 556 |
| common_trigger_match | 556 |
| common_event_outbox | 556 |
| common_event_inbox | 2155 |
| common_event_consumer_checkpoint | 2155 |
| N4 outbox pending | 556 |
| N4 outbox delivered/delivering | 0 |
| N5 refs total | 0 |
| N6/user/sim/position refs total | 0 |
| event ledger refs | 0 |
| delivery attempt refs | 0 |
| N3 MarketSnapshotUpdated source run pending | 2155 |
| old FULL repair retry run rows | 1 |
| old FULL repair retry outbox rows | 556 |

N3 source run used for preservation proof:

`realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`

## Rollback Guard Proof

- hard-fail before first DELETE/UPDATE: `True`
- guards target N4 outbox delivered/delivering: `True`
- guards event ledger if table exists: `True`
- guards delivery attempts if table exists: `True`
- guards N5 action run/event/fact/outbox refs: `True`
- guards downstream inbox/checkpoint refs: `True`
- excludes scoped N4 checkpoint false positive: `True`
- guards N6/user/sim/position refs: `True`
- deletes only scoped N4 retry rows: `True`
- no CASCADE/DROP/TRUNCATE: `True`

## Delete Scope

The rollback SQL may delete only:

- `common_event_outbox` where `source_layer='N4_trigger'` and `source_run_id=target_run_id`
- `common_trigger_match` where `run_id=target_run_id`
- `common_trigger_state` where `run_id=target_run_id`
- `common_trigger_quality_item` where `run_id=target_run_id`
- `common_event_inbox` for scoped N4 consumer and target `execute_run_id`
- `common_event_consumer_checkpoint` for scoped N4 consumer and target `execute_run_id`
- `common_trigger_run` target row

## Forbidden Scope Proof

- rollback executed: `false`
- DB business write performed: `false`
- N4 execute performed: `false`
- N5/N6 entered: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- worker started: `false`
- delivery/push/voice/mobile: `false`
- sim/position/pnl/real_trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Validation

- source JSON parse: `PASS`
- rollback SQL static check: `PASS`
- live DB readiness proof: `PASS`
- git diff --check: `PASS`

## Next Gate

Allow re-entering `N4_PROJECTION_MATCHER_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_POST_REVIEW_GATE`.
