# V3 20260612 Stale N5 Trigger Period Fabrication Rollback Execute Report

Result: `ROLLBACK_PASS`

Executed SQL:

```text
sql/V3_20260612_stale_n5_trigger_period_fabrication_rollback.sql
```

Only the authorized rollback SQL was executed. No N4/N5/N6 runner was executed, no scheduler/worker was started, no N4 outbox was consumed or status-updated, and no voice/mobile/sim/position/order/real trade scope was touched.

## Deleted Rows

- `common_action_run`: `2`
- `common_action_quality_item`: `4449`
- `stock_action_fact`: `22226`
- `index_action_fact`: `975`
- `board_action_fact`: `1831`
- `common_action_event`: `25032`
- N5 `common_event_outbox`: `25032`
- `common_event_ledger`: `0`
- `common_event_delivery_attempt`: `0`
- reviewed stale consumer inbox/checkpoint: `25282/2078`

## Post-Check

Scoped stale N5 rows are now zero:

- `common_action_run=0`
- `common_action_quality_item=0`
- `stock/index/board_action_fact=0/0/0`
- `common_action_event=0`
- N5 outbox/ledger: `0/0`
- reviewed stale consumer inbox/checkpoint: `0/0`

## N4 Preservation

`v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3` remains:

- status: `passed`
- trigger match/state/outbox: `25282/89275/45006`
- outbox pending:
  - `TriggerMatched=25282`
  - `TriggerPendingMarketData=4`
  - `TriggerStateChanged=19720`

`v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1` remains:

- status: `passed`
- trigger match/state/outbox: `4454/4454/4454`
- outbox pending:
  - `TriggerMatched=5`
  - `TriggerPendingMarketData=4449`

N4 outbox status was not updated and N4 outbox was not consumed.

## N3 Preservation

Rollback SQL did not touch N3 tables. N3 historical evidence is preserved.

## Downstream Refs

Post-rollback refs remain clear:

- N6/user projection refs: `0`
- user signal/card/notification refs: `0`
- position state/event refs: `0/0`
- voice/mobile/sim/order/trade/PnL refs: `0`

## Boundary

- N4 runner executed: `false`
- N5 runner executed: `false`
- N6 runner executed: `false`
- scheduler/worker started: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- old system touched: `false`

Rollback is safe after execution. Return to runtime_control for rollback post-review, then proceed to N4 fixed replay contract/preflight in a separate gate.
