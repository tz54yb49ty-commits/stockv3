# N6 Real Delivery Rollback / Supersession Policy Contract

Gate: `N6_REAL_DELIVERY_ROLLBACK_SUPERSESSION_POLICY_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:35:00+08:00`  
Result: `CONTRACT_PASS`

## Contract

Rollback/supersession policy version: `n6_real_delivery_rollback_supersession_policy_v1`.

Rules:

- Before any provider network send, scoped cleanup may be allowed only by a rollback final gate.
- After `network_send_attempted=true`, silent deletion is forbidden.
- After `provider_delivery_confirmed=true`, rollback must be supersession/cancellation/audit-only.
- Source noop preview rows must be preserved unless a separate rollback gate authorizes cleanup.
- N5 outbox delivered/delivering or future ack states must guard rollback.
- Delivery/push/voice/mobile refs must guard rollback.
- Sim/order/trade/position/PnL refs must guard rollback.
- If downstream refs exist, rollback proceeds reverse order.

## Supersession States

- `active`
- `superseded`
- `cancelled`
- `policy_blocked`
- `incident_disabled`

## Planned Write Scope

All planned writes are zero.

Next gate:

```text
N6_REAL_DELIVERY_PROVIDER_POLICY_REFRESH_READINESS_GATE
```
