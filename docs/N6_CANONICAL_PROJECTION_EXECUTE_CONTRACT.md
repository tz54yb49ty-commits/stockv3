# N6 Canonical Projection Execute Contract Draft

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-05-29

This is a contract draft only:

```text
n6_execute=false
database_written=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
n5_inbox_checkpoint_written=false
worker_started=false
push_voice_mobile=false
sim_position_real_trade=false
```

## Source Gate

```text
action_run_id=action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
source_n4_run_id=trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
for_trade_date=20260529
N5 pending ActionBlocked=4309
ActionEligible=0
ActionExecuted=0
ActionSkipped=0
legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0
```

## Input Contract

N6 canonical projection execute may read only pending N5 action outbox events:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Legacy replay compatibility remains read-only:

```text
ActionEvent
HintEvent
```

N6 must not use as input event types:

```text
BUY_HINT
SELL_HINT
RiskEvent
PositionEvent
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
MarketSnapshotUpdated
MinuteBarClosed
```

`BUY_HINT / SELL_HINT` may only appear in `condition_key`,
`original_condition_key`, or trace JSON for display provenance. They are not
N6 input event types.

The canonical runner must not scan N4/N3/N2 naked facts as event substitutes.

## Projection Policy

| N5 event | User card state | Notification | Decisions | Sim / real trade |
|---|---|---|---|---|
| `ActionBlocked` | `blocked / 未确认` | `queued_only`, no push | disabled | disabled |
| `ActionEligible` | `candidate / 可关注` | `queued_only`, no push | disabled until later gate | disabled |
| `ActionExecuted` | `action_confirmed` | `queued_only`, no push | disabled | disabled |
| `ActionSkipped` | `skipped / expired` | `queued_only`, no push | disabled | disabled |

Current 20260529 execute candidate therefore plans only:

```text
user_projection_run=1
user_signal_projection=4309
user_signal_card=4309
user_notification_queue=4309
user_signal_decision=0
user_sim_rows=0
```

## Future Execute Write Scope

Future execute, after a separate final gate, may write only:

```text
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
```

Every row must be scoped by `user_projection_run_id` and retain:

```text
source_action_run_id
source_event_id
source_action_event_id
source_action_event_type
action_state
action_mark
condition_key
original_condition_key
trace_json
projection_policy
```

## Forbidden Scope

Future execute remains forbidden from:

```text
N5 outbox consumption
N5 outbox status update
N5 inbox/checkpoint writes
user_signal_decision writes
user_session writes
user_watchlist writes
user_sim_* writes
voice/mobile push writes
position writes
real trade
worker start
N1-N5 writes
```

## Rollback Strategy

Business rollback must use:

```text
sql/N6_projection_business_rollback.sql
```

Rollback deletes only the target `user_projection_run_id` scope:

```text
user_notification_queue
user_signal_card
user_signal_projection
user_projection_run
```

Rollback must BLOCK if linked decision, sim, voice/mobile, position, or other
downstream references exist. It never touches N5 outbox, N5 inbox/checkpoint,
or N1-N5 facts.
