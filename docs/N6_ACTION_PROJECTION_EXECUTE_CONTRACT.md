# N6 Action Projection Execute Contract

Status: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-06

This gate refreshes the execute contract for the 20260605 N6 action projection path after `N6_ACTION_PROJECTION_RUNNER_QUEUE_DEFERRED_ALIGNMENT_PASS`. It does not execute N6, write N6 projection rows, consume N5 outbox, start workers, send delivery/push/voice/mobile, create sim/position/PnL, generate proposal/order/trade, or modify N6_UI_v1/B-track.

The previous blocker was that the execute runner would materialize `user_notification_queue=605`. The runner now supports `notification_queue_policy=deferred`, so this contract is aligned with `user_notification_queue=0` and may proceed to runtime_control final gate review.

## Source Lineage

```text
source_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
user_projection_run_id=user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

## Planned Writes

Allowed future writes, if and only if a later final execute gate is approved:

```text
user_projection_run=1
user_signal_projection=605
user_signal_card=605
user_notification_queue=0
```

Queue policy:

```text
notification_queue_policy=deferred
queue_deferred_capability=true
```

All other rows remain zero:

```text
user_signal_decision=0
proposal=0
virtual_order=0
virtual_trade=0
virtual_position=0
virtual_pnl=0
delivery/push/voice/mobile=0
real_trade=0
N5 outbox status updates=0
```

## Input Semantics

Accepted input event types:

```text
ActionExecuted
ActionBlocked
```

Input count:

```text
ActionExecuted=1
ActionBlocked=604
total=605
```

Rejected input event types:

```text
ActionEvent
HintEvent
RiskEvent
PositionEvent
ActionEligible
ActionSkipped
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
MarketSnapshotUpdated
MinuteBarClosed
```

`ActionExecuted` maps to:

```text
projection_state=market_action_confirmed
card_status=action_confirmed
display_text=市场动作确认成立
```

It is display-only and must not generate proposal, virtual order, virtual trade, position, PnL, sim, delivery, push, voice, mobile, or real trade.

`ActionBlocked` maps to:

```text
projection_state=market_action_not_confirmed
card_status=blocked
display_text=市场动作未确认
```

It may display N5 `blocked_reason`, but it is not a failed trade and must not be reinterpreted as user cash, user position, account eligibility, T+1, blacklist, or order failure.

## Preflight Guards

DB-side read-only preflight result:

```text
db_preflight_result=PASS
common_action_run.status=passed
N5 P0/P1/P2=0/0/0
common_action_event rows=605
common_action_event distinct event_id=605
N5 outbox pending=605
N5 outbox delivered=0
N5 outbox delivering=0
ActionExecuted pending=1
ActionBlocked pending=604
legacy event inputs=0
out_of_contract canonical events=0
N6 source refs=0
N6 scoped projection_run_id refs=0
delivery attempt refs=0
sim refs=0
position refs=0
virtual order/trade/position/pnl refs=0
admin user active=true
admin principal active=true
037 readonly role SELECT-only proof=passed
```

Runner alignment result:

```text
runner_alignment=PASS
notification_queue_policy=deferred
runner readiness=true
queue deferred capability=true
```

Static proof:

```text
DEFERRED_NOTIFICATION_WRITE_TABLES excludes user_notification_queue=true
build_write_plan(notification_queue_policy=deferred) builds notification_rows=[]=true
write_counts.user_notification_queue=0=true
commit path skips insert_notification when deferred=true
contract deferred planned queue > 0 blocks before DB write=true
```

## Execute Requirements

The future execute command must still be reviewed and explicitly confirmed in a separate final gate. The runner must be invoked with:

```text
--execute
--user-confirmed
--projection-run-id=user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
--source-action-run-id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
--contract-json-path=docs/N6_ACTION_PROJECTION_EXECUTE_CONTRACT.json
--preflight-json-path=docs/N6_ACTION_PROJECTION_EXECUTE_PREFLIGHT.json
```

Before commit, the runner must re-check:

```text
N5 action_run passed=true
N5 outbox pending=605
N5 outbox delivered/delivering=0/0
N6 source/run baseline refs=0
notification_queue_policy=deferred
planned user_notification_queue=0
P0=0
```

## Post-Review Expectations

If a later final gate is approved and executed, post-review must verify:

```text
user_projection_run rows for run_id=1
user_signal_projection rows for run_id=605
user_signal_card rows for run_id=605
user_notification_queue rows for run_id=0
ActionExecuted projection count=1
ActionBlocked projection count=604
N5 outbox pending remains=605
N5 outbox delivered/delivering remains=0/0
N5 outbox status updated=false
worker_started=false
delivery refs=0
push refs=0
voice refs=0
mobile refs=0
sim/position refs=0
virtual order/trade/position/pnl refs=0
proposal/order/trade generated=false
N6_UI_v1/B-track modified=false
```

## Rollback

Rollback SQL:

```text
sql/N6_ACTION_PROJECTION_20260605_ROLLBACK.sql
```

Rollback scope is exactly the fixed `user_projection_run_id` for this 20260605 projection. It deletes only:

```text
user_signal_card
user_signal_projection
user_projection_run
```

Delete order:

```text
user_signal_card -> user_signal_projection -> user_projection_run
```

Rollback hard-fails before the first delete when any of these exist:

```text
user_notification_queue rows for the run
delivery refs
push refs
voice refs
mobile refs
sim refs
position refs
virtual order/trade/position/pnl refs
proposal/order/trade refs
user_signal_decision refs
```

Rollback does not touch N5 outbox, N5 inbox/checkpoint, N4/N3/N2/N1 facts, N6_UI_v1, B-track schema, or worker/delivery state.

## Boundary

```text
execute_performed=false
database_written=false
write_user_projection_run=false
write_user_signal_projection=false
write_user_signal_card=false
write_user_notification_queue=false
consume_n5_outbox=false
update_n5_outbox_status=false
start_worker=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
modify_n6_ui_v1=false
modify_b_track=false
write_n1_to_n5=false
```

## Gate Result

```text
contract_result=CONTRACT_PASS
db_preflight_result=PASS
preflight_result=EXECUTE_PREFLIGHT_PASS
runner_alignment_result=PASS
remaining_blockers=none
allow_runtime_control_execute_final_gate_review=true
next_allowed_gate=N6_ACTION_PROJECTION_EXECUTE_FINAL_GATE_REVIEW
```
