# N6 Shadow Projection Dry-Run

Status: DRY_RUN_PASS

Layer role: N6_user

Date: 2026-06-06

This dry-run evaluates the 20260605 canonical N5 action output against `docs/N6_ACTION_PROJECTION_CONTRACT.md`. It is read-only and does not write `user_projection_run`, `user_signal_projection`, `user_signal_card`, or `user_notification_queue`.

## Source

```text
source_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
planned_user_projection_run_id=user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

## Input Count Proof

Read-only DB proof:

```text
common_action_run.status=passed
N5 P0/P1/P2=0/0/0
common_action_event rows=605
common_action_event distinct event_id=605
ActionExecuted=1
ActionBlocked=604
legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0
ActionEligible/ActionSkipped=0
N5 outbox ActionExecuted pending=1
N5 outbox ActionBlocked pending=604
```

## Planned Outputs

This is a dry-run plan only:

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

## Semantic Mapping

| N5 event type | N6 dry-run card status | Display text | User-action semantics |
|---|---|---|---|
| ActionExecuted | `action_confirmed` | 市场动作确认成立 | display only; no order, no fill, no real trade, no virtual trade, no proposal/order/position/PnL |
| ActionBlocked | `blocked` | 市场动作未确认 | display only; show N5 blocked reason when present; not a failed trade |

`ActionExecuted` is a market-action confirmation fact. It is not:

```text
已下单
已成交
真实交易
虚拟交易
proposal generated
order generated
position updated
pnl generated
```

`ActionBlocked` is not a failed transaction. It must not be reinterpreted as user cash, position, T+1, blacklist, or account eligibility failure.

## Sample Cards

These are would-render samples only. They were not written to N6 tables.

### Sample 1: ActionExecuted

```text
card_status=action_confirmed
title=市场动作确认成立
event_type=ActionExecuted
asset=stock / stock:SZ:300910
direction=buy
signal_type=B_BUY
action_mark=normal
condition_key=BUY:Y,Q,M,W,D
original_condition_key=BUY:Y,Q,M,W,D
source_action_status=executed / passed
N4 trigger event id=evt_e8884501f5cca6aef53574cccab0a3fbe7da53ea
N5 action event id=evt_14581cc071ab335b100a3abeb83464021137446a
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

### Sample 2: ActionBlocked

```text
card_status=blocked
title=市场动作未确认
event_type=ActionBlocked
asset=stock / stock:SZ:002518
direction=buy
signal_type=B_BUY
blocked_reason=price_confirmation_failed
condition_key=BUY:W,D
original_condition_key=BUY:W,D
source_action_status=blocked / failed
N4 trigger event id=evt_065c15d917d043127989377332372dd242e0dd9b
N5 action event id=evt_0061de4d90c19c07527d8c85ef16114803f92971
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

### Sample 3: ActionBlocked

```text
card_status=blocked
title=市场动作未确认
event_type=ActionBlocked
asset=stock / stock:SH:600060
direction=buy
signal_type=B_BUY
blocked_reason=metric_missing
condition_key=BUY:Q,M,W,D
original_condition_key=BUY:Q,M,W,D
source_action_status=blocked / failed
N4 trigger event id=evt_657f3da2bdfec051b41b4d700d02f597bf96f21a
N5 action event id=evt_0095ec17e99aaef60bb388052c50fb06ffcd15ab
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

### Sample 4: ActionBlocked

```text
card_status=blocked
title=市场动作未确认
event_type=ActionBlocked
asset=stock / stock:SH:600572
direction=buy
signal_type=B_BUY
blocked_reason=metric_missing
condition_key=BUY:Y,Q,M,W,D
original_condition_key=BUY:Y,Q,M,W,D
source_action_status=blocked / failed
N4 trigger event id=evt_2808280f623a20cf5874594edb3015ec00e975e8
N5 action event id=evt_00a1bd40468ff77a8f2f65dc645a09806af7ca1b
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

## Baseline Proof

Read-only probes confirmed:

```text
user_projection_run refs by source_action_run_id=0
user_projection_run refs by planned run_id=0
user_signal_projection refs by source_action_run_id=0
user_signal_projection refs by planned run_id=0
user_signal_card refs by source_action_run_id=0
user_signal_card refs by planned run_id=0
user_notification_queue refs by source_action_run_id=0
user_notification_queue refs by planned run_id=0
N6 outbox refs by planned run_id=0
delivery attempt refs by planned run_id=0
user_signal_decision total=0
user_sim_order/user_sim_trade/user_sim_position=0/0/0
n6_virtual_order/n6_virtual_trade/n6_virtual_position/n6_virtual_pnl_snapshot refs by planned run_id=0/0/0/0
```

## Safety Proof

```text
database_written=false
write_user_projection_run=false
write_user_signal_projection=false
write_user_signal_card=false
write_user_notification_queue=false
consume_n5_outbox=false
update_n5_outbox_status=false
start_worker=false
delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
pnl=false
proposal=false
order=false
trade=false
real_trade=false
modify_n6_ui_v1=false
modify_b_track=false
```

## Warnings

```text
P0=0
P1=0
P2=0
notification_queue_deferred=true
```

The deferred queue policy is intentional and follows the current contract. It does not block projection execute contract design.

## Next Gate

Allowed next step:

```text
N6_ACTION_PROJECTION_EXECUTE_CONTRACT_GATE
```

Execute is still not allowed by this dry-run. A separate execute contract/final gate is required before any N6 write.
