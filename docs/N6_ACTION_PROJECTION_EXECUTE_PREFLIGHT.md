# N6 Action Projection Execute Preflight

Status: EXECUTE_PREFLIGHT_PASS

Layer role: N6_user

Date: 2026-06-06

This preflight refresh is read-only. It confirms that the DB baseline is ready for the 20260605 N6 action projection execute contract and that the execute runner now supports the required `user_notification_queue=0 deferred` policy.

## Source

```text
source_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
user_projection_run_id=user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

## DB Preflight Result

```text
db_preflight_result=PASS
target_database=ashare_v3
target_user=ashare_v3_user
target_host=127.0.0.1
target_port=5432
common_action_run.status=passed
N5 P0/P1/P2=0/0/0
common_action_event rows=605
common_action_event distinct_event_id=605
ActionExecuted=1
ActionBlocked=604
N5 outbox pending=605
N5 outbox delivered=0
N5 outbox delivering=0
legacy event inputs=0
out_of_contract canonical events=0
```

## Baseline Guards

```text
user_projection_run refs by source_action_run_id=0
user_projection_run refs by run_id=0
user_signal_projection refs by source_action_run_id=0
user_signal_projection refs by run_id=0
user_signal_card refs by source_action_run_id=0
user_signal_card refs by run_id=0
user_notification_queue refs by source_action_run_id=0
user_notification_queue refs by run_id=0
N6 outbox refs by run_id=0
delivery attempt refs by run_id=0
user_signal_decision total=0
user_sim_order/user_sim_trade/user_sim_position=0/0/0
n6_virtual_order/n6_virtual_trade/n6_virtual_position/n6_virtual_pnl_snapshot refs by run_id=0/0/0/0
```

## Principal Scope

```text
admin user exists exactly one=true
admin user_id=1
admin role=admin
admin status=active
admin principal_id=1
admin principal_type=admin
admin principal_status=active
admin principal owner_user_id=1
principal_scope=admin-first-user
```

## 037 Readonly Role Proof

```text
n6_ui_readonly_role view grants:
  v_n6_stock_condition_display_basis=SELECT
  v_n6_index_condition_display_basis=SELECT
  v_n6_board_condition_display_basis=SELECT
  v_n6_index_membership_fact=SELECT
  v_n6_board_membership_fact=SELECT
```

## Runner Alignment

```text
runner_alignment_result=PASS
runner_readiness=true
queue_deferred_capability=true
notification_queue_policy=deferred
contract expected user_notification_queue=0
deferred runner write plan excludes user_notification_queue=true
deferred runner builds notification_rows=[]=true
deferred runner skips insert_notification=true
```

## Planned Writes

```text
user_projection_run=1
user_signal_projection=605
user_signal_card=605
user_notification_queue=0
```

No delivery, push, voice, mobile, sim, position, PnL, proposal, order, trade, or real trade rows are planned.

## Post-Review Expectations

```text
projection rows=605
card rows=605
notification rows=0
delivery refs=0
N5 outbox unchanged pending=605
N5 outbox delivered/delivering remains=0/0
N5 outbox status updated=false
```

## Forbidden Scope

```text
database_written=false
consume_n5_outbox=false
update_n5_outbox_status=false
write_n5_inbox_checkpoint=false
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

## Gate Result

```text
preflight_result=EXECUTE_PREFLIGHT_PASS
db_preflight_result=PASS
runner_alignment_result=PASS
remaining_blockers=none
allow_runtime_control_execute_final_gate_review=true
next_allowed_gate=N6_ACTION_PROJECTION_EXECUTE_FINAL_GATE_REVIEW
```
