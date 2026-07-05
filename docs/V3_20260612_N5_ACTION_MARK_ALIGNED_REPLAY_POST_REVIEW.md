# V3 20260612 N5 Action Mark Aligned Replay Post-Review

Result: `POST_REVIEW_PASS`

## Scope

- source N4 run: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- N5 action run: `v3_n5_action_mark_aligned_replay_20260612_from_n4_action_confirmation_metric_after_n3_repair_v1`
- consumer: `n5_action_consumer_v1`
- execute report: `docs/V3_20260612_N5_ACTION_MARK_ALIGNED_REPLAY_EXECUTE_REPORT.json`

## Execute Proof

- runner result: `EXECUTED`
- `common_action_run.status`: `passed`
- P0/P1/P2 failed: `0/0/0`
- worker started: `false`
- N6 touched: `false`
- real trade touched: `false`

## Actual Rows

- `common_action_run`: `1`
- `common_action_quality_item`: `4405`
- `stock_action_fact`: `33`
- `index_action_fact`: `0`
- `board_action_fact`: `10`
- `common_action_event`: `43`
- N5 `common_event_outbox`: `43`
- N5 `common_event_inbox`: `4454`
- scoped N5 checkpoint rows by inbox partitions: `2082`
- `common_position_state/common_position_event`: `0/0`

The checkpoint table has no `source_run_id` column, so the scoped proof uses this run's inbox partitions. Consumer-wide checkpoint rows are not the same metric.

## Event Distribution

- `ActionExecuted`: `43`
- `ActionBlocked`: `0`
- `ActionEligible`: `0`
- `ActionSkipped`: `0`
- legacy `ActionEvent/HintEvent/RiskEvent/PositionEvent`: `0`

N5 outbox:

- pending: `43`
- delivering / delivered: `0 / 0`

## Action Mark Distribution

- `normal`: `38`
- `30m_volume`: `5`
- `30m_shrink`: `0`
- null: `0`

By fact table:

- stock: `normal=30`, `30m_volume=3`
- board: `normal=8`, `30m_volume=2`
- index: `0`

## Boundary Proof

N4 outbox was not consumed or status-updated:

- `TriggerMatched pending`: `49`
- `TriggerPendingMarketData pending`: `4405`
- delivered / delivering: `0 / 0`

Forbidden downstream refs remain clear:

- N6 user signal refs: `0`
- position state/event refs: `0/0`
- voice/mobile/sim/real trade: `0`

## Rollback

Rollback SQL: `sql/V3_20260612_n5_action_mark_aligned_replay_rollback.sql`

Static proof:

- hard-fail before first DELETE
- guards N5 outbox delivered/delivering
- guards downstream inbox/checkpoint refs
- does not touch N4/N3/N6

Rollback was not executed.

This post-review can be returned to runtime_control for registration.
