# N6 20260603 Canonical Projection Preflight

Status: EXECUTE_FINAL_PREFLIGHT_PASS

Layer role: N6_user

Date: 2026-06-03

This preflight is read-only and did not execute N6 business writes.

## Required Baseline

```text
source_action_run_id=action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
user_projection_run_id=user_projection_shadow_20260603__action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1
expected_n5_outbox:
  ActionBlocked:pending=1252
delivered=0
delivering=0
```

## N5 Readiness

```text
common_action_run.status=passed
N5 P0/P1/P2=0/0/0
action_fact_row_count=1252
action_event_outbox_count=1252
ActionBlocked pending=1252
ActionEligible/ActionExecuted/ActionSkipped=0/0/0
user_layer_touched=false
voice_touched=false
sim_touched=false
real_trade_touched=false
worker_started=false
```

## Dry-Run Result

```text
result=DRY_RUN_PASS
P0/P1/P2=0/5/2
planned_user_projection_run=1
planned_user_signal_projection=1252
planned_user_signal_card=1252
planned_user_notification_queue=1252
planned_user_signal_decision=0
planned_sim_rows=0
```

## Baseline Guards

Read-only probes confirmed:

```text
target projection scoped rows=0
N6 refs for source_action_run_id=0
linked decision/sim/watchlist refs=0
N5 outbox unchanged=true
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

Future execute final gate must include the explicit expected count:

```text
ASHARE_V3_POSTGRES_DSN='postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3' \
PYTHONPATH=src:scripts \
python3 scripts/run_n6_projection_once.py \
  --projection-run-id user_projection_shadow_20260603__action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1 \
  --source-action-run-id action_consumer_canonical_20260603_trigger_execute_20260603_condition_layer_20260602_source_20260602_v1 \
  --contract-json-path docs/N6_20260603_canonical_projection_contract.json \
  --preflight-json-path docs/N6_20260603_canonical_projection_preflight.json \
  --expected-n5-outbox-count ActionBlocked:pending=1252 \
  --execute \
  --user-confirmed
```

Do not execute this command without a separate user final gate.
