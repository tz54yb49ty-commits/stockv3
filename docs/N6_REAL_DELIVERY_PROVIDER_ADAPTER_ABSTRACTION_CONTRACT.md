# N6 Real Delivery Provider Adapter Abstraction Contract

Gate: `N6_REAL_DELIVERY_PROVIDER_ADAPTER_ABSTRACTION_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:10:00+08:00`  
Result: `CONTRACT_PASS`

## Read-Only Boundary

This gate freezes a design contract for the provider adapter abstraction only. It did not execute N6, did not write the database, did not consume or update N5 outbox/inbox/checkpoint rows, did not start a worker, did not perform real provider delivery, push, voice, or mobile, did not read secrets, and did not touch sim, position, PnL, real trade, proposal, order, or trade paths.

## Prerequisite Proof

- Adapter abstraction readiness: `READINESS_PASS`
- Real delivery policy alignment: `ALIGNMENT_PASS`
- Alignment decision: `DEFER_REAL_PROVIDER_DELIVERY_AND_SPLIT_DESIGN_GATES`
- Real delivery policy contract: `BLOCKED`
- Real delivery policy preflight: `PREFLIGHT_BLOCKED`
- Existing N6 delivery runner: no-op local preview only
- Real provider delivery remains deferred: `true`

This contract resolves only the provider adapter abstraction design gap. It does not resolve credential/secret policy, consent allowlist, retry/failure-state policy, N5 outbox ack/status policy, provider attempt schema, rollback/supersession policy, or long-running worker lifecycle.

## Adapter Abstraction Contract

Contract version: `n6_provider_adapter_abstraction_v1`

The adapter abstraction defines a provider boundary between sanitized N6 notification payloads and any future delivery provider. The abstraction must not expose upstream raw payloads, trace internals, N5 outbox internals, or action-run internals to provider-visible payloads.

Minimum adapter interface:

- `adapter_id`
- `adapter_kind`
- `provider_id`
- `capabilities`
- `build_idempotency_key(input)`
- `validate_payload(input)`
- `prepare_attempt(input)`
- `send(input)`
- `classify_response(response_or_error)`
- `build_audit_event(attempt_context)`

The `send(input)` operation is forbidden unless all of these are true in a later execute contract:

- adapter kind is `real_provider`
- `can_send_network=true`
- credential/secret policy has passed
- user/channel consent allowlist has passed
- retry/failure-state policy has passed
- provider attempt audit contract has passed
- N5 outbox ack/status policy has passed if any ack mutation is planned
- rollback/supersession policy has passed
- final gate has produced a single allowed execute command
- user explicitly confirms execution

## Noop / Dry-Run / Real Provider Separation

`noop_local`:

- May materialize local preview rows when separately authorized.
- Must not call a network provider.
- Must not load credentials.
- Must not mutate N5 outbox status.
- Provider side effect is always `false`.

`dry_run_provider`:

- May validate payload shape and build audit-only attempt plans.
- Must not call a network provider.
- Must not load production credentials.
- Must not mutate N5 outbox status.
- May be used for future provider sandbox planning only after a separate contract.

`real_provider`:

- Represents an adapter capable of contacting a real provider.
- Default state is disabled.
- Requires credential, consent, retry/failure-state, audit, ack/status, rollback/supersession, preflight, final gate, and explicit user confirmation before any send.
- Must produce auditable provider attempt state before and after any real send.

## Capability Flags

Required flags:

- `can_send_network`
- `can_materialize_preview`
- `requires_credentials`
- `requires_consent`
- `supports_retry`
- `supports_provider_ack`
- `can_update_n5_outbox_status`
- `writes_provider_attempt_audit`
- `supports_dry_run`
- `supports_supersession`

Default capabilities:

```text
can_send_network=false
can_update_n5_outbox_status=false
writes_provider_attempt_audit=false
supports_retry=false
supports_provider_ack=false
```

No future gate may infer network permission from provider name alone. Permission must come from capability flags plus passed credential, consent, retry, rollback, and final execute gates.

## Idempotency / Timeout / Retry Classification

Idempotency key input fields:

- `provider_policy_run_id`
- `source_projection_run_id`
- `source_action_run_id`
- `source_notification_queue_id`
- `user_id`
- `channel`
- `provider_id`
- `adapter_kind`
- `sanitized_payload_hash`

Canonical key format:

```text
sha256(provider_policy_run_id | source_action_run_id | source_notification_queue_id | user_id | channel | provider_id | adapter_kind | sanitized_payload_hash)
```

Default timeout policy for future real provider planning:

- connect timeout: `3s`
- send timeout: `10s`
- total attempt timeout: `15s`
- cancellation policy: `fail_closed`

Retry classification:

- `policy_blocked`
- `credential_error`
- `consent_blocked`
- `payload_validation_failed`
- `rate_limited`
- `transient_provider_error`
- `provider_timeout`
- `provider_unknown`
- `permanent_provider_reject`
- `sent_acknowledged`

Retry execution remains disabled until the retry/backoff/failure-state policy gate passes.

## Provider Attempt Audit Contract

Future provider attempt audit rows or events must include:

- `attempt_id`
- `provider_policy_run_id`
- `source_projection_run_id`
- `source_action_run_id`
- `source_notification_queue_id`
- `adapter_id`
- `adapter_kind`
- `provider_id`
- `capability_snapshot_json`
- `idempotency_key`
- `sanitized_payload_hash`
- `request_status`
- `response_class`
- `retry_class`
- `failure_reason`
- `attempt_started_at`
- `attempt_finished_at`
- `network_send_attempted`
- `provider_delivery_confirmed`

The audit contract must be immutable for completed attempts. Real provider rollback must use supersession/cancellation state rather than silent deletion once external side effects are possible.

## Default Real Network Send Disabled Proof

- No adapter kind has implicit send permission.
- `can_send_network` defaults to `false`.
- Existing runner is no-op local preview only.
- Credential/secret policy has not passed.
- Consent allowlist policy has not passed.
- Retry/failure-state policy has not passed.
- N5 outbox ack/status policy has not passed.
- Rollback/supersession policy has not passed.
- No execute command is allowed by this gate.

## Planned Write Scope

This design contract plans no writes:

- provider attempt audit rows: `0`
- N5 outbox updates: `0`
- N5 inbox/checkpoint rows: `0`
- user notification rows: `0`
- delivery/push/voice/mobile rows: `0`
- sim/position/PnL/real_trade rows: `0`
- proposal/order/trade rows: `0`

## Forbidden Scope Proof

- SQL executed: `false`
- database written: `false`
- N5 outbox/inbox/checkpoint consumed or updated: `false`
- N6 execute entered: `false`
- worker started: `false`
- long-running worker started: `false`
- secret read: `false`
- provider network call: `false`
- actual delivery / push / voice / mobile: `false`
- sim / position / PnL / real trade: `false`
- proposal / order / trade: `false`
- rollback SQL executed: `false`
- old system touched: `false`

## Result

`CONTRACT_PASS`: the provider adapter abstraction design is frozen for the next design gate sequence.

This is not real provider delivery approval and does not allow entry to a real provider execute user confirmation gate.

## Recommended Next Gate

```text
N6_REAL_DELIVERY_CREDENTIAL_SECRET_POLICY_READINESS_GATE
```
