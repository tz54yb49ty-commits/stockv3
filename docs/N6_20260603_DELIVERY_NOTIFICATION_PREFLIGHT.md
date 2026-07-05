# N6 20260603 Delivery / Notification Preflight

Status: EXECUTE_FINAL_PREFLIGHT_PASS

Layer role: N6_user

Date: 2026-06-04

This preflight is read-only. It did not materialize delivery rows and did not
send notifications.

## Source Queue

```text
source_projection_run_id=user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
delivery_materialization_run_id=n6_delivery_notification_materialization_20260603_v1__user_projection_shadow_20260603_v1
queued_only input rows=863
distinct_queue_ids=863
distinct_source_events=863
existing_materialized_rows=0
```

## Planned Future Writes

```text
allowed_write_tables=user_notification_queue
planned_insert_rows=863
notification_source=n6_delivery_materialized_noop
queue_status=ready_for_future_push
channel=in_app_notification_preview
provider=noop_local_provider_v1
provider_delivery_attempt=false
```

## Quality

```text
P0=0
P1=2
P2=3
```

P0 blocker:

```text
none
```

P1 warnings:

```text
source_queue_trace_json_present=863
source_payload_internal_source_outbox_id_present=863
```

P2 notes:

```text
noop_provider_only
retry_disabled_until_real_provider_contract
delivery_schema_uses_existing_user_notification_queue
```

## Boundary

```text
database_write=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
n5_inbox_checkpoint_written=false
provider_delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
real_trade=false
worker_started=false
```

## Execute Readiness

Runtime-control delivery execute final gate is allowed after review:

```text
allow_runtime_control_delivery_execute_final_gate_review=true
runner=src/ashare_v3/user/delivery_execute.py
script=scripts/run_n6_delivery_once.py
requires_execute=true
requires_user_confirmed=true
blocker=null
```

Next allowed step:

```text
runtime_control delivery execute final gate review
```
