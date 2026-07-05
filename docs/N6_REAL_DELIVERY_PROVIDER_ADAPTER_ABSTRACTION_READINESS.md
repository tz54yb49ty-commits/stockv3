# N6 Real Delivery Provider Adapter Abstraction Readiness

Gate: `N6_REAL_DELIVERY_PROVIDER_ADAPTER_ABSTRACTION_READINESS_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:07:00+08:00`  
Result: `READINESS_PASS`

## Read-Only Boundary

This gate only evaluates readiness for a provider adapter abstraction design contract. It did not execute N6, did not write the database, did not consume or update N5 outbox/inbox/checkpoint rows, did not start a worker, did not call a provider, did not perform delivery, push, voice, or mobile, and did not touch sim, position, PnL, real trade, proposal, order, or trade paths.

## Prerequisite Proof

- Real delivery provider policy alignment: `ALIGNMENT_PASS`
- Alignment decision: `DEFER_REAL_PROVIDER_DELIVERY_AND_SPLIT_DESIGN_GATES`
- Real provider delivery remains deferred: `true`
- Provider policy contract gate result: `BLOCKED`
- Provider policy preflight result: `PREFLIGHT_BLOCKED`
- Provider policy final gate result: `BLOCKED`
- Noop delivery rollout registration: `REGISTRATION_PASS`
- The next gate recommended by alignment is this adapter abstraction readiness gate.

The blocked provider policy contract produced seven P0 blockers for real delivery execution. This readiness gate does not waive those blockers; it splits the first prerequisite, provider adapter abstraction, into its own design track.

## Current Runner Boundary Proof

Current N6 delivery code is scoped to local no-op preview materialization:

- `src/ashare_v3/user/delivery_execute.py` declares the runner as no-op materialization only.
- `scripts/run_n6_delivery_once.py` states that it materializes local preview rows only.
- Current runner does not contact providers.
- Current runner does not consume or update N5 outbox status.
- Current runner does not write N5 inbox/checkpoint rows.
- Current runner does not start a worker.
- Current runner does not perform push, voice, mobile, sim, position, real trade, proposal, order, or trade work.
- Current provider identifier is `noop_local_provider_v1`.

Therefore a real provider adapter abstraction is required before any real delivery execute gate can be considered.

## Provider Adapter Gap Analysis

Required gaps before real delivery can move beyond policy design:

- Adapter interface is not frozen.
- Noop provider, dry-run provider, and real provider are not separated by an explicit contract.
- Real network send is not gated by an adapter capability flag.
- Credential/secret access is not attached to adapter selection.
- User/channel consent allowlist is not attached to send eligibility.
- Retry/backoff/failure classification is not frozen.
- Provider request/response audit event contract is not frozen.
- Idempotency key and provider attempt dedup policy are not frozen.
- Timeout and cancellation behavior are not frozen.
- N5 outbox ack/status remains a separate unapproved policy.
- Rollback/supersession semantics for external provider attempts are not frozen.

## Proposed Adapter Abstraction Scope

The next contract gate should define an adapter abstraction with these minimum fields and rules:

- Adapter kinds: `noop_local`, `dry_run_provider`, `real_provider`.
- Capability flags: `can_send_network`, `can_materialize_preview`, `requires_credentials`, `requires_consent`, `supports_retry`, `supports_provider_ack`, `can_update_n5_outbox_status`.
- Default capability state: `can_send_network=false`, `can_update_n5_outbox_status=false`.
- Idempotency key inputs: provider policy run id, source notification queue id, user id, channel, provider id, and source action run id.
- Timeout policy: connect timeout, send timeout, total timeout, cancellation behavior.
- Retry classification: `transient`, `rate_limited`, `credential_error`, `consent_blocked`, `permanent_payload_error`, `provider_unknown`, `policy_blocked`.
- Audit event contract: attempt id, adapter kind, provider id, capability snapshot, sanitized payload hash, idempotency key, request status, response class, retry class, and failure reason.
- Payload boundary: provider-visible payload must remain sanitized and must not expose upstream trace, raw N5 payload, source outbox internals, or action run internals.
- Real network send remains disabled until credential, consent, retry, ack/status, rollback/supersession, contract, preflight, final gate, and explicit user confirmation all pass.

## Safety Requirements

- The adapter contract gate must be design-only unless a later gate explicitly authorizes code changes.
- No provider network send may occur.
- No secrets may be loaded or printed.
- No N5 outbox status update may occur.
- No N5 inbox/checkpoint rows may be written.
- No delivery/push/voice/mobile provider side effect may occur.
- No sim/position/PnL/real_trade/proposal/order/trade path may be touched.
- Any future execute must have contract, preflight, final gate, rollback/supersession policy, and explicit user confirmation.

## Rollback / Supersession Planning

This readiness gate has no database write scope and no rollback execution.

Future real provider delivery cannot use smoke-style deletion as its only rollback model. The adapter design must require:

- Immutable provider attempt audit rows.
- Supersession or cancellation state for externally visible attempts.
- Guards for N5 outbox delivered/delivering or future ack states.
- Guards for delivery/push/voice/mobile downstream refs.
- Guards for sim/order/trade/position/PnL refs.
- Preservation of noop preview rows and registered smoke evidence.
- No `CASCADE`, `DROP`, or `TRUNCATE`.

## Quality

```text
P0=0
P1=7
P2=3
```

P1 items:

- adapter contract not frozen
- real provider implementation remains deferred
- credential/secret gate still required
- user/channel consent allowlist gate still required
- retry/backoff/failure-state gate still required
- N5 outbox ack/status policy still required
- rollback/supersession policy still required

P2 items:

- noop preview rows are registered evidence only
- `ready_for_future_push` is not provider send consent
- long-running delivery worker lifecycle remains unapproved

## Forbidden Scope Proof

- SQL executed: `false`
- database written: `false`
- N5 outbox/inbox/checkpoint consumed or updated: `false`
- N6 execute entered: `false`
- worker started: `false`
- long-running worker started: `false`
- provider network call: `false`
- actual delivery / push / voice / mobile: `false`
- sim / position / PnL / real trade: `false`
- proposal / order / trade: `false`
- rollback SQL executed: `false`
- old system touched: `false`

## Readiness Decision

`READINESS_PASS`: the project may enter the provider adapter abstraction contract/design gate.

This does not authorize real provider delivery, provider network calls, credential use, N5 outbox ack/status changes, N6 execute, delivery/push/voice/mobile, sim, position, PnL, real trade, proposal, order, trade, or a long-running worker.

## Recommended Next Gate

```text
N6_REAL_DELIVERY_PROVIDER_ADAPTER_ABSTRACTION_CONTRACT_GATE
```
