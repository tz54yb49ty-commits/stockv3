# V3 20260612 Stale N5 Action Mark Run Rollback Execute Include Realtime Engine Consumer Report

Result: `ROLLBACK_PASS`

Generated at: `2026-06-13 10:23:52 +0800`

This gate executed only the scoped stale N5 rollback SQL. It did not consume or update N4 outbox status, did not restart the scheduler, did not enter N6, and did not touch voice/mobile/sim/position/trade.

## Scope

- Target action run: `v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`
- Source N4 trigger run: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- Reviewed stale consumers:
  - `n5_action_consumer_v1`
  - `v3_realtime_engine_n5_consumer_20260612`
- SQL executed: `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`
- DB target: `ashare_v3` on `127.0.0.1:5432` as `ashare_v3_user`

## Final Gate Proof

Read-only final gate artifact:

- `docs/V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_FINAL_GATE_REVIEW_INCLUDE_REALTIME_ENGINE_CONSUMER.json`
- result: `PASS`
- blockers: `null`
- allowed execute layer role: `N5_action`
- preserve N4 run: `true`
- preserve N3 projection run: `true`

## Execute Result

The rollback SQL completed with `COMMIT`.

SQL-reported deletes:

- `common_event_delivery_attempt=0`
- `common_event_consumer_checkpoint=43`
- `common_event_inbox=49`
- `common_event_outbox=43`
- `common_event_ledger=0`
- `common_action_event=43`
- `board_action_fact=10`
- `index_action_fact=0`
- `stock_action_fact=33`
- `common_action_quality_item=0`
- `common_action_run=1`

## Post-Review Row Counts

Stale N5 scope after rollback:

- `common_action_run=0`
- `common_action_quality_item=0`
- `stock_action_fact=0`
- `index_action_fact=0`
- `board_action_fact=0`
- `common_action_event=0`
- `N5 common_event_outbox=0`
- `N5 common_event_ledger=0`
- reviewed stale consumers' inbox refs for scoped N4 source: `0`
- reviewed stale consumers' checkpoint refs on scoped N4 partitions: `0`

Preserved non-stale refs:

- non-stale inbox refs for scoped N4 source: `0`
- non-stale checkpoint refs on scoped N4 partitions: `6279`

These non-stale checkpoint refs were intentionally preserved.

## N4 Preservation Proof

- `common_trigger_run=1`
- `common_trigger_match=4454`
- `common_trigger_state=4454`
- `N4 common_event_outbox=4454`
- `N4 outbox pending=4454`
- `N4 outbox delivered/delivering=0`

No N4 trigger facts or N4 outbox status were updated by this gate.

## Downstream Proof

- `N5 outbox delivered/delivering=0`
- `user_projection_run refs=0`
- `user_signal_projection refs=0`
- `user_signal_decision refs=0`
- `user_notification_queue refs=0`
- `user_sim_order refs=0`
- `user_sim_trade refs=0`
- `user_sim_position refs=0`
- `common_position_state refs=0`
- `common_position_event refs=0`

## Boundary Proof

- N3 projection / metric facts modified: `false`
- N4 outbox consumed or status-updated: `false`
- N5 outbox consumed: `false`
- scheduler restarted: `false`
- N6 entered: `false`
- voice/mobile/sim/position/trade touched: `false`
- old system modified by this gate: `false`

## Next Gate

Allowed next step:

`V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_POST_REVIEW_INCLUDE_REALTIME_ENGINE_CONSUMER`

After post-review registration, runtime_control can continue with the planned N3 repair SQL refresh route.
