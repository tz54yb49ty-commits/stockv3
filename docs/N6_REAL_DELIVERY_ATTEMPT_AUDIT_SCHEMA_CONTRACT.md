# N6 Real Delivery Attempt Audit Schema Contract

Gate: `N6_REAL_DELIVERY_ATTEMPT_AUDIT_SCHEMA_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:33:00+08:00`  
Result: `CONTRACT_PASS`

## Schema Contract

Proposed logical table: `common_event_delivery_attempt`.

Required logical fields:

- `delivery_attempt_id`
- `provider_policy_run_id`
- `source_projection_run_id`
- `source_action_run_id`
- `source_notification_queue_id`
- `user_id`
- `channel`
- `adapter_id`
- `adapter_kind`
- `provider_id`
- `capability_snapshot_json`
- `credential_ref`
- `consent_policy_ref`
- `idempotency_key`
- `sanitized_payload_hash`
- `request_status`
- `response_class`
- `retry_class`
- `failure_reason`
- `attempt_number`
- `attempt_started_at`
- `attempt_finished_at`
- `network_send_attempted`
- `provider_delivery_confirmed`
- `supersedes_attempt_id`
- `superseded_by_attempt_id`
- `created_at`

Completed attempts are immutable. External side effects must be preserved by audit and supersession, not silent deletion.

## Migration Boundary

This contract does not execute schema migration and does not create or alter tables.

## Forbidden Scope

No SQL, DB write, schema migration, provider call, N5 outbox mutation, worker, delivery/push/voice/mobile, sim/trade.

Next gate:

```text
N5_OUTBOX_ACK_STATUS_POLICY_READINESS_GATE
```
