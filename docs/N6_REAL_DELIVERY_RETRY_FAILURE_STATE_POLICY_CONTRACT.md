# N6 Real Delivery Retry / Failure-State Policy Contract

Gate: `N6_REAL_DELIVERY_RETRY_FAILURE_STATE_POLICY_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:32:00+08:00`  
Result: `CONTRACT_PASS`

## Contract

Retry policy version: `n6_real_delivery_retry_failure_state_policy_v1`.

Retry classes:

- retryable: `rate_limited`, `transient_provider_error`, `provider_timeout`, `provider_unknown`
- non-retryable: `policy_blocked`, `credential_error`, `consent_blocked`, `payload_validation_failed`, `permanent_provider_reject`, `sent_acknowledged`

Backoff policy:

- max attempts: `3`
- first retry delay: `60s`
- second retry delay: `300s`
- third retry delay: `900s`
- jitter: required for real provider implementation
- retry execution enabled by this gate: `false`

Terminal states:

- `sent_acknowledged`
- `failed_permanent`
- `policy_blocked`
- `superseded`
- `cancelled`

All policy, credential, consent, and payload failures fail closed.

## Planned Write Scope

All planned writes are zero. This is a design-only contract.

## Forbidden Scope

No provider call, no retry execution, no DB write, no N5 outbox mutation, no worker, no delivery/push/voice/mobile, no sim/trade.

Next gate:

```text
N6_REAL_DELIVERY_ATTEMPT_AUDIT_SCHEMA_READINESS_GATE
```
