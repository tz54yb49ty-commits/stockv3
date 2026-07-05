# N6 Action Projection Contract

Status: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-06

This gate only freezes the N6 projection contract for the current 20260605 canonical N5 action output. It does not execute N6, write projection rows, consume N5 outbox, start workers, push notifications, create virtual trades, or change A-track/B-track UI behavior.

## Source Lineage

```text
source_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
proposed_user_projection_run_id=user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

## Input Scope

N6 may only read canonical N5 action events for this gate:

```text
ActionExecuted pending=1
ActionBlocked pending=604
total pending input events=605
```

Out of scope for this contract:

```text
ActionEligible
ActionSkipped
ActionEvent
HintEvent
RiskEvent
PositionEvent
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
MarketSnapshotUpdated
MinuteBarClosed
BUY_HINT
SELL_HINT
```

`BUY_HINT` and `SELL_HINT` may appear only as trace or condition context inside reviewed N5 payloads. They are not N6 input event types.

N6 must not scan N4/N3/N2 raw facts to replace N5 event input. If any required display field is missing, the dry-run must record a warning and must not backfill by crossing layer boundaries.

## Projection Semantics

### ActionExecuted

Display meaning:

```text
市场动作确认成立
```

This means only that the N5 market action confirmation fact was established. It does not mean:

```text
已下单
已成交
真实交易
虚拟交易
proposal accepted
order created
position updated
pnl generated
```

N6 must not automatically create proposal, order, trade, position, PnL, delivery, push, voice, mobile, or sim output from `ActionExecuted`.

### ActionBlocked

Display meaning:

```text
市场动作未确认
```

N6 may show the N5 blocked reason if present in the reviewed event payload or trace. N6 must not reinterpret the blocked reason as user account, cash, position, T+1, blacklist, or trading eligibility failure.

## Planned Outputs

This contract defines would-write counts for a later dry-run. This gate writes nothing.

```text
planned_user_projection_run=1
planned_user_signal_projection=605
planned_user_signal_card=605
planned_user_notification_queue=0 deferred
planned_user_signal_decision=0
planned_proposal=0
planned_virtual_order=0
planned_virtual_trade=0
planned_virtual_position=0
planned_virtual_pnl=0
planned_delivery_push_voice_mobile=0
planned_real_trade=0
planned_n5_outbox_status_update=0
```

Notification queue materialization is deferred in this contract. A later gate must explicitly approve queue rows if product policy wants them.

## Principal And User Scope

Initial scope is admin-first-user only:

```text
principal_scope=admin
principal_cross_read_allowed=false
principal_cross_write_allowed=false
B_track_user_mutation_allowed=false
```

This contract does not create or mutate human users, AI users, watchlists, strategies, proposals, virtual orders, virtual trades, positions, PnL, or leaderboards.

## Read-Only UI Boundary

N6_UI_v1 remains an A-track admin read-only console. It may display reviewed projection data after a separately approved dry-run/execute path, but this gate does not modify UI code or routes.

The following hidden modules remain hidden:

```text
监控筛选
持仓
手机播报
```

This contract does not enter B-track `/n6/app/...` user front-end work and does not modify `/api/n6/ui/v1/...` or `/api/n6/app/v1/...`.

## Future Execute Scope

This gate does not allow execute. A future execute final gate would need refreshed read-only preflight proof and an explicit user confirmation.

If a future execute is approved under this contract, allowed writes are limited to:

```text
user_projection_run
user_signal_projection
user_signal_card
```

Forbidden writes remain:

```text
user_notification_queue
user_signal_decision
user_session
user_watchlist
user_sim_*
n6_virtual_order
n6_virtual_trade
n6_virtual_position
n6_virtual_pnl_snapshot
N5 outbox status
N5 inbox/checkpoint
N1-N5 facts
```

## Rollback Design

Rollback is scoped by `user_projection_run_id` and must not touch N5/N4/N3/N2/N1.

For this contract, notification queue is deferred, so rollback scope is:

```text
user_signal_card
user_signal_projection
user_projection_run
```

Delete order:

```text
user_signal_card -> user_signal_projection -> user_projection_run
```

Rollback must hard-fail before the first delete if any linked downstream refs exist:

```text
delivery refs
push refs
voice refs
mobile refs
sim refs
position refs
virtual account/order/trade/position/pnl refs
proposal refs
user_signal_decision refs
```

If any `user_notification_queue` rows exist for this `user_projection_run_id`, rollback must block because queue materialization is outside this contract and requires a separate queue-aware rollback gate.

## Preflight Design

The next dry-run gate must refresh read-only proof for:

```text
N5 action_run exists and status=passed
N5 outbox pending total=605
N5 outbox ActionExecuted pending=1
N5 outbox ActionBlocked pending=604
N5 outbox status not consumed or updated
N6 refs for source_action_run_id=0
target projection_run_id scoped baseline=0
event_id total/distinct=605/605
delivery refs=0
sim refs=0
position refs=0
virtual refs=0
proposal/order/trade refs=0
037 readonly role proof still safe if UI read path is used
```

Any mismatch in event counts, action_run status, duplicate event ids, baseline rows, or downstream refs is P0 and blocks execute.

## Boundary Proof

```text
execute_performed=false
business_write_performed=false
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

## Next Gate

Allowed next step:

```text
N6_SHADOW_PROJECTION_DRY_RUN_GATE
```

The next gate remains dry-run only unless runtime_control later approves a separate execute final gate.
