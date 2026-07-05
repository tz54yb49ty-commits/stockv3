# N6 20260603 Delivery / Notification Contract

Status: CONTRACT_MATERIALIZATION_PASS

Layer role: N6_user

Date: 2026-06-04

This contract defines a first no-op delivery materialization path from the
existing N6 `queued_only` notification rows. It does not authorize real
provider delivery.

## Source

```text
source_projection_run_id=user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
source_action_run_id=action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
delivery_materialization_run_id=n6_delivery_notification_materialization_20260603_v1__user_projection_shadow_20260603_v1
```

Input rows:

```text
user_notification_queue.notification_source=n5_action_blocked
user_notification_queue.queue_status=queued_only
user_notification_queue.channel=broadcast_queue
count=863
```

## Channel / Provider / User Policy

```text
delivery_channel=in_app_notification_preview
provider=noop_local_provider_v1
user_policy=admin_default_notification_preview_v1
target_user_scope=admin user_id=1 only for this MVP gate
actual_provider_delivery=false
push=false
voice=false
mobile=false
```

`noop_local_provider_v1` means future materialization may prepare rows for UI
inspection only. It must not call APNs, FCM, SMS, TTS, browser push, webhook,
or any external provider.

## Allowed Future Write Scope

Future execute, only after runtime-control final gate, may append materialized
no-op rows to:

```text
user_notification_queue
```

with:

```text
notification_source=n6_delivery_materialized_noop
queue_status=ready_for_future_push
channel=in_app_notification_preview
```

Forbidden writes:

```text
N5 outbox status
N5 inbox/checkpoint
user_signal_projection
user_signal_card
user_signal_decision
user_session
user_watchlist
user_sim_*
voice/mobile/provider delivery tables
position tables
N1-N5 facts
```

## Payload Contract

Future provider-visible payload may contain only:

```text
title
message
sanitized notification_payload_json
```

The sanitized `notification_payload_json` may contain display-safe keys:

```text
schema_version
delivery_materialization_run_id
dedup_key
provider
channel
policy
asset_kind
identity_key
action_state
display_state
retry.max_attempts=0
failure.status=not_attempted
```

It must not contain trace or internal audit payload:

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

## Dedup / Retry / Failure

Dedup key:

```text
sha256(delivery_materialization_run_id || user_id || source_user_notification_queue_id || provider)
```

Dedup scope:

```text
delivery_materialization_run_id + user_id + source queue row + provider
```

Retry policy:

```text
retry_policy=noop_provider_no_retry
max_attempts=0
attempt_count=0
next_retry_at=null
```

Failure handling:

```text
failure_status=not_attempted
failure_reason=null
```

Any real provider, retry, ack, device token, failure, or delivery attempt state
requires a later schema/runner contract and must not be smuggled into this
no-op path.

## Rollback

Rollback draft:

```text
sql/N6_20260603_delivery_notification_rollback.sql
```

Rollback is scoped by `delivery_materialization_run_id`. It deletes only
materialized no-op `user_notification_queue` rows and must hard-fail before the
first `DELETE` if provider delivery, push, voice, mobile, sim, position, or
real-trade refs exist.

## Execute Readiness

Current execute readiness:

```text
allow_runtime_control_delivery_execute_final_gate_review=true
runner=src/ashare_v3/user/delivery_execute.py
script=scripts/run_n6_delivery_once.py
requires_execute=true
requires_user_confirmed=true
blocker=null
```

Next allowed step is runtime_control delivery execute final gate review.
