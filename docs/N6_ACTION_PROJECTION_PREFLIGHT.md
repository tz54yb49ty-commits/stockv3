# N6 Action Projection Preflight

Status: PREFLIGHT_DESIGN_PASS

Layer role: N6_user

Date: 2026-06-06

This artifact records the required read-only preflight for the 20260605 N6 action projection dry-run. It does not execute N6 and does not write database rows.

## Provided Readiness Baseline

```text
readiness_status=READINESS_PASS
source_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
N5 action_run=passed
common_action_event=605
ActionExecuted=1
ActionBlocked=604
N5 outbox pending=605
N6/user refs=0
P0/P1/P2=0/0/0
```

## Required Fresh Checks For Dry-Run

The next gate must refresh these checks with read-only probes:

```text
N5 action_run exists=true
N5 action_run.status=passed
N5 outbox pending total=605
N5 outbox ActionExecuted pending=1
N5 outbox ActionBlocked pending=604
legacy ActionEvent/HintEvent/RiskEvent/PositionEvent count=0 for this source run
N5 outbox status updates=0
source event_id total/distinct=605/605
N6 refs for source_action_run_id=0
target projection_run_id scoped rows=0
delivery refs=0
push refs=0
voice refs=0
mobile refs=0
sim refs=0
position refs=0
virtual order/trade/position/pnl refs=0
proposal refs=0
037 readonly role proof still safe if UI display path is used
```

## P0 Blockers

Any of the following blocks dry-run or future execute:

```text
action_run_missing_or_not_passed
n5_outbox_count_mismatch
unexpected_legacy_event_input
event_id_duplicate
n6_baseline_nonzero
source_run_already_projected
delivery_or_push_refs_exist
voice_or_mobile_refs_exist
sim_or_position_refs_exist
virtual_refs_exist
proposal_order_trade_refs_exist
n5_outbox_consumed_or_status_updated
attempt_to_scan_n4_n3_n2_raw_facts_as_event_substitute
```

## Planned Counts

This preflight supports a dry-run plan only:

```text
planned_user_projection_run=1
planned_user_signal_projection=605
planned_user_signal_card=605
planned_user_notification_queue=0 deferred
planned_user_signal_decision=0
planned_proposal/order/trade=0
planned_position/pnl=0
planned_delivery/push/voice/mobile=0
planned_real_trade=0
planned_n5_outbox_status_updates=0
```

## Boundary

```text
write_database=false
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
write_n1_to_n5=false
```

## Rollback Readiness

Rollback is design-only in this gate. If a later projection execute is approved, rollback must be scoped by `user_projection_run_id`, must delete only N6 projection/card/run rows, and must hard-fail before delete when downstream refs exist.

Because notification queue is deferred in this contract, any queue rows linked to the run are a P0 rollback blocker and require a separate queue-aware rollback gate.

## Gate Result

```text
preflight_design_result=PREFLIGHT_DESIGN_PASS
remaining_blockers=0
next_allowed_gate=N6_SHADOW_PROJECTION_DRY_RUN_GATE
```
