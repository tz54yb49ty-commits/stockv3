# N5 Outbox Ack / Status Policy Contract

Gate: `N5_OUTBOX_ACK_STATUS_POLICY_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:34:00+08:00`  
Result: `CONTRACT_PASS`

## Contract

Default policy: N6 real delivery must not update N5 outbox status unless a later N5/N6 ack execute gate explicitly authorizes it.

Allowed future transition model, design-only:

- `pending -> delivering` only after final execute authorization.
- `delivering -> delivered` only after provider delivery confirmed.
- `delivering -> pending` only for retryable failure with audit.
- `delivering -> failed` only for terminal failure with audit.
- `pending` must remain unchanged for design-only and shadow runs.

Ack ownership belongs to a separately approved N5/N6 ack policy path, not to provider adapter design alone.

## Guards

- Delivered/delivering rows must block rollback unless reverse-order cleanup is approved.
- N5 outbox updates require source action run id and event id scoping.
- N6 must not rewrite N5 facts.
- N6 may only write its own audit/projection facts unless ack policy final gate authorizes status mutation.

## Planned Write Scope

All planned writes are zero.

Next gate:

```text
N6_REAL_DELIVERY_ROLLBACK_SUPERSESSION_POLICY_READINESS_GATE
```
