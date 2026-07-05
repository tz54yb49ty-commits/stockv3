# N6 20260603 V1 Market-Action-Confirmation Projection Contract

Status: ROLLBACK_ALIGNMENT_PASS

Layer role: N6_user

Date: 2026-06-04

This contract prepares N6 shadow user projection for the 20260603 N5 v1
market-action-confirmation run. This gate is readiness / dry-run / preflight
only:

```text
n6_business_write=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
worker_started=false
delivery_notification_push=false
voice_mobile=false
sim_position_real_trade=false
```

## Source Gate

```text
source_action_run_id=action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
source_trigger_run_id=trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
user_projection_run_id=user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
expected_n5_outbox_counts:
  ActionBlocked:pending=863
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
| ActionBlocked | blocked / 未确认 | n5_action_blocked | queued_only | disabled |

`queued_only` means a row would be queued for display only. It is not
delivery, push, voice/mobile delivery, sim, position, or real trade.

## Dry-Run Baseline

```text
result=DRY_RUN_PASS
input_events=863
ActionBlocked=863
planned_user_projection_run=1
planned_user_signal_projection=863
planned_user_signal_card=863
planned_user_notification_queue=863
planned_user_signal_decision=0
planned_sim_rows=0
P0/P1/P2=0/5/2
```

P1 warnings are display-field warnings only and do not authorize cross-layer
backfill:

```text
display_basis_missing=863
current_price_missing=863
target_price_missing=863
expected_return_pct_missing=863
board_context_missing=863
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
voice/mobile/push/delivery writes
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

Rollback must hard-fail before the first `DELETE` if linked
decision/sim/voice/mobile/position refs exist. Future voice/mobile/position
tables are checked with `to_regclass`, so absent tables do not falsely fail
rollback. Rollback never touches N5 outbox or N1-N5 facts.
