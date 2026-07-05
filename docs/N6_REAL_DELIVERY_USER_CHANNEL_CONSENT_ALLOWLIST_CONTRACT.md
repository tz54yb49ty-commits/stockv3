# N6 Real Delivery User / Channel Consent Allowlist Contract

Gate: `N6_REAL_DELIVERY_USER_CHANNEL_CONSENT_ALLOWLIST_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:31:00+08:00`  
Result: `CONTRACT_PASS`

## Contract

Real provider delivery requires explicit allowlist proof before a provider adapter may send. The allowlist must bind `user_id`, `channel`, `provider_id`, `environment`, `policy_version`, consent status, and effective time window.

Consent states:

- `allowed`
- `blocked`
- `revoked`
- `expired`
- `unknown`

Only `allowed` can proceed. All other states fail closed.

`ready_for_future_push` is not consent. `queued_only` is not consent. Noop preview materialization is not consent.

## Required Checks

- user allowlist status
- channel allowlist status
- provider allowlist status
- environment match
- policy version match
- quiet-hours rule
- market-hours rule
- emergency disable flag
- per-user opt-out flag
- audit metadata presence

## Planned Write Scope

All planned writes are zero. This is a policy-only contract.

## Forbidden Scope Proof

No SQL, DB write, N5 outbox mutation, N6 execute, secret read, provider call, worker, delivery/push/voice/mobile, sim/trade, or rollback execution occurred.

## Recommended Next Gate

```text
N6_REAL_DELIVERY_RETRY_FAILURE_STATE_POLICY_READINESS_GATE
```
