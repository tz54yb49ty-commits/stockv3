# N6 Delivery Noop Or Notification Policy Contract

Result: `CONTRACT_PASS`

Runner status: `CONTRACT_MATERIALIZATION_PASS`

Generated at: `2026-06-10T21:25:49+08:00`

Layer role: `runtime_control`

This contract is an artifact-only gate. It did not execute N6, did not write database rows, did not consume or update N5 outbox, inbox, or checkpoint rows, did not start a worker, and did not perform provider delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade.

## Prerequisite Proof

```text
readiness=READINESS_PASS
dry-run=DRY_RUN_PASS
chained shadow rollout registration=REGISTRATION_PASS
chained shadow rollback readiness=READINESS_PASS
chained shadow amended post-review=POST_REVIEW_PASS
runner static no-op scope proof=PASS
```

## Contract Scope

```text
delivery_materialization_run_id=n6_delivery_noop_materialization_20260608_chained_shadow_probe
source_projection_run_id=n4_n5_n6_chained_shadow_smoke_20260608_projection_probe
source_action_run_id=n4_n5_n6_chained_shadow_smoke_20260608_action_probe
source_notification_source=n5_action_blocked
source_queue_status=queued_only
source_channel=broadcast_queue
expected_source_count=50
mode=noop_local_preview_materialization
provider=noop_local_provider_v1
```

This contract allows only a future local no-op preview materialization if a later final gate and user confirmation explicitly authorize it. It does not authorize real delivery.

## Allowed Future Write Scope

```text
table=user_notification_queue
write_mode=append_only
planned_rows=50
notification_source=n6_delivery_materialized_noop
queue_status=ready_for_future_push
channel=in_app_notification_preview
projection_policy=noop_local_preview_materialized_no_delivery
```

## Forbidden Future Write Scope

```text
N5 outbox status update=false
N5 outbox consumption=false
N5 inbox/checkpoint write=false
user_signal_projection/card/decision write=false
provider delivery tables=false
push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
N1-N5 facts=false
worker start=false
```

## Payload Contract

Provider-visible preview payload may contain only sanitized keys:

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
retry
failure
```

Forbidden provider-visible keys include source outbox identifiers, raw N5 payloads, trace_json, source payloads, card payloads, and action-run internals.

## Dedup / Retry Policy

```text
dedup_key_formula=sha256(delivery_materialization_run_id || user_id || source_user_notification_queue_id || provider)
dedup_scope=delivery_materialization_run_id + user_id + source queue row + provider
retry_policy=noop_provider_no_retry
max_attempts=0
attempt_count=0
failure_status=not_attempted
```

## Rollback Contract

```text
rollback_sql_path=sql/N6_delivery_noop_notification_policy_20260608_chained_shadow_probe_rollback.sql
scope=delivery_materialization_run_id + source_projection_run_id + source_action_run_id
delete_tables=user_notification_queue only
hard_fail_before_first_delete=true
guard_N5_outbox_delivered_delivering=true
guard_delivery_push_voice_mobile_refs=true
guard_sim_order_trade_position_refs=true
preserve_source_queued_only_rows=true
preserve_N4_N5_N6_registered_evidence=true
```

## Execute Readiness

```text
allow_execute_user_confirmation_gate=true
script=scripts/run_n6_delivery_once.py
runner=src/ashare_v3/user/delivery_execute.py
requires_execute=true
requires_user_confirmed=true
contract_json_path=docs/N6_DELIVERY_NOOP_OR_NOTIFICATION_POLICY_CONTRACT.json
preflight_json_path=docs/N6_DELIVERY_NOOP_OR_NOTIFICATION_POLICY_PREFLIGHT.json
rollback_sql_path=sql/N6_delivery_noop_notification_policy_20260608_chained_shadow_probe_rollback.sql
```

Recommended next artifact:

```text
N6_DELIVERY_NOOP_OR_NOTIFICATION_POLICY_PREFLIGHT
```
