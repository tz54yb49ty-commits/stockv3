# N6 20260602 Action-Confirmation Projection Contract

Status: ROLLBACK_ALIGNMENT_PASS

Layer role: N6_user

Date: 2026-06-02

This contract aligns N6 user projection to the action-confirmation metric N5
run. It is contract/preflight alignment only:

```text
n6_business_write=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
worker_started=false
push_voice_mobile=false
sim_position_real_trade=false
```

## Source Gate

```text
source_action_run_id=action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
user_projection_run_id=user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
expected_n5_outbox_counts:
  ActionExecuted:pending=4
  ActionBlocked:pending=1
delivered/delivering=0/0
```

N6 may read only pending N5 action outbox events for the source action run:

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

N6 must not read N4/N3/N2 naked facts as substitutes. `BUY_HINT` and
`SELL_HINT` are trace/condition values only, not N6 input event types.

## Projection Policy

| N5 event | User card state | Notification source | Queue | Decisions / sim / trade |
|---|---|---|---|---|
| ActionExecuted | action_confirmed | n5_action_executed | queued_only | disabled |
| ActionBlocked | blocked / 未确认 | n5_action_blocked | queued_only | disabled |

`queued_only` means a row would be queued for display only. It is not push,
voice/mobile delivery, sim, position, or real trade.

## Dry-Run Baseline

```text
result=DRY_RUN_PASS
input_events=5
ActionExecuted=4
ActionBlocked=1
planned_user_projection_run=1
planned_user_signal_projection=5
planned_user_signal_card=5
planned_user_notification_queue=5
planned_user_signal_decision=0
planned_sim_rows=0
P0/P1/P2=0/5/2
```

P1 warnings are display-field warnings only and do not authorize cross-layer
backfill:

```text
display_basis_missing=5
current_price_missing=5
target_price_missing=5
expected_return_pct_missing=5
board_context_missing=5
```

## Future Execute Scope

Future execute, after a separate final gate, may write only:

```text
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
```

Future execute remains forbidden from:

```text
N5 outbox consumption/status update
N5 inbox/checkpoint writes
user_signal_decision writes
user_session writes
user_watchlist writes
user_sim_* writes
voice/mobile/push writes
position writes
real trade
worker start
N1-N5 writes
```

## Rollback

Rollback must use `sql/N6_projection_business_rollback.sql`, scoped by
`user_projection_run_id`, deleting in this order:

```text
user_notification_queue
user_signal_card
user_signal_projection
user_projection_run
```

Rollback must hard-fail if linked decision/sim/voice/mobile/position refs
exist. The executable rollback SQL now enforces these guards before the first
`DELETE`:

```text
decision refs: user_signal_decision
sim refs: user_sim_order / user_sim_trade / user_sim_position
voice refs: user_voice_delivery / user_voice_queue / user_voice_delivery_log
mobile refs: user_mobile_delivery / user_mobile_queue / user_device_ack / user_notification_delivery
position refs: user_position_projection / user_position_state / common_position_state / common_position_event
```

Future voice/mobile/position tables are checked with `to_regclass`, so absent
tables do not falsely fail rollback. If any optional table exists and has linked
refs through run/projection/card/queue/event/source-run identifiers, rollback
hard-fails. Rollback never touches N5 outbox or N1-N5 facts.
