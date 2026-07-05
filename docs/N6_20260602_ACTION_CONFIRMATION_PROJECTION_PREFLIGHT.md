# N6 20260602 Action-Confirmation Projection Preflight

Status: EXECUTE_FINAL_PREFLIGHT_PASS

Layer role: N6_user

Date: 2026-06-02

This preflight is read-only and did not execute N6 business writes.

## Required Baseline

```text
source_action_run_id=action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
user_projection_run_id=user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
expected_n5_outbox:
  ActionExecuted:pending=4
  ActionBlocked:pending=1
delivered=0
delivering=0
```

## Dry-Run Result

```text
result=DRY_RUN_PASS
P0/P1/P2=0/5/2
planned_user_projection_run=1
planned_user_signal_projection=5
planned_user_signal_card=5
planned_user_notification_queue=5
planned_user_signal_decision=0
planned_sim_rows=0
```

The old 20260529 baseline blocker is resolved by explicit gate counts:

```text
expected_source=explicit_gate
expected={"ActionExecuted:pending":4,"ActionBlocked:pending":1}
actual={"ActionExecuted:pending":4,"ActionBlocked:pending":1}
```

## Baseline Guards

Read-only probes confirmed:

```text
admin=admin user_id=1 active
default admin filter profile active=1
target projection scoped rows=0
N6 refs for source_action_run_id=0
linked decision/sim/watchlist refs=0
event_id total/distinct=5/5
```

## Rollback Static Check

```text
rollback_sql=sql/N6_projection_business_rollback.sql
guard_before_first_delete=true
raise_exception_before_first_delete=true
to_regclass_optional_table_checks=true
decision_refs_guard=true
sim_refs_guard=true
voice_refs_guard=true
mobile_refs_guard=true
position_refs_guard=true
delete_order=user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run
touches_n5_outbox=false
touches_n1_to_n5=false
```

## Boundary

```text
write_database=false
write_user_projection_run=false
write_user_signal_projection=false
write_user_signal_card=false
write_user_notification_queue=false
write_user_signal_decision=false
write_user_session=false
write_user_watchlist=false
write_user_sim_tables=false
consume_n5_outbox=false
update_n5_outbox_status=false
write_n5_inbox_checkpoint=false
start_worker=false
push_voice_mobile=false
position=false
real_trade=false
write_n1_to_n5=false
```

## Execute Command Candidate

Future execute final gate must include the explicit expected counts:

```text
ASHARE_V3_POSTGRES_DSN='postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3' \
PYTHONPATH=src:scripts \
python3 scripts/run_n6_projection_once.py \
  --projection-run-id user_projection_shadow_20260602_1105__action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1 \
  --source-action-run-id action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1 \
  --contract-json-path docs/N6_20260602_action_confirmation_projection_contract.json \
  --preflight-json-path docs/N6_20260602_action_confirmation_projection_preflight.json \
  --expected-n5-outbox-count ActionExecuted:pending=4 \
  --expected-n5-outbox-count ActionBlocked:pending=1 \
  --execute \
  --user-confirmed
```

Do not execute this command without a separate user final gate.
