# N6 20260603 Delivery / Notification Dry-Run Report

Status: DRY_RUN_PASS

Layer role: N6_user

Date: 2026-06-04

This gate is dry-run / contract materialization only:

```text
execute=false
database_write=false
provider_delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
real_trade=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
worker_started=false
```

## Source

```text
source_action_run_id=action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
source_projection_run_id=user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
delivery_materialization_run_id=n6_delivery_notification_materialization_20260603_v1__user_projection_shadow_20260603_v1
```

Input queue rows:

```text
notification_source=n5_action_blocked
queue_status=queued_only
channel=broadcast_queue
count=863
distinct_queue_ids=863
distinct_source_events=863
missing_title=0
missing_message=0
```

No existing delivery materialization rows were found for this
`delivery_materialization_run_id`.

## Planned Materialization

Future materialization, if separately implemented and approved, is append-only
into `user_notification_queue`:

```text
planned_insert_user_notification_queue=863
planned_queue_status=ready_for_future_push
planned_notification_source=n6_delivery_materialized_noop
planned_channel=in_app_notification_preview
provider=noop_local_provider_v1
actual_provider_delivery=false
retry_attempts=0
```

This is not push, voice, mobile, sim, position, or real trade.

## Payload Policy

Provider-visible payload is limited to:

```text
title
message
sanitized notification_payload_json
```

The sanitized payload must not include:

```text
trace_json
source_payload_json
card_payload_json
display_payload_json
raw N5 payload
source_outbox_id
source_event_id
source_action_event_id
source_action_run_id
source_event_dedup_key
```

Dry-run found that the source queue rows have internal audit fields that must
be stripped before any future provider payload:

```text
row_trace_json_nonnull=863
notification_payload_json.source_outbox_id=863
notification_payload_json.trace_json=0
notification_payload_json.payload_json=0
```

## Quality

```text
P0=0
P1=2
P2=3
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
delivery_execute_runner_not_implemented
```

## Execute Readiness

This dry-run does not authorize execute. A delivery execute runner is not yet
implemented, so runtime_control execute final gate is not allowed yet.

