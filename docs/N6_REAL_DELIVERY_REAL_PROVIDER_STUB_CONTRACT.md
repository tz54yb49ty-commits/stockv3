# N6 Real Delivery Real Provider Stub Contract

Result: `CONTRACT_PASS`

Gate: `N6_REAL_DELIVERY_REAL_PROVIDER_STUB_CONTRACT_GATE`

Generated at: `2026-06-10T23:44:42+08:00`

This contract covers only the disabled real provider skeleton. It generates no execute command.

## Stub Contract

- adapter class: `RealProviderAdapterSkeleton`
- provider_id: `real_provider_skeleton_v1`
- adapter_kind: `real_provider_skeleton`
- default `can_send_network=false`
- `network_send_enabled` remains not allowed in this gate
- credentials remain opaque `credential_ref` only
- real secret read is not allowed
- provider network call is not allowed
- execute command generated: `false`

If called without future gates, the skeleton must return `BLOCKED` with fail-closed blockers including missing final execute gate, network disabled, `can_send_network=false`, credential/consent/retry/audit/N5 ack/rollback policy missing.

## Planned Write Scope

All planned writes are zero: DB writes, local report artifacts, N5 outbox updates, provider attempt audit rows, worker starts.

Real provider execute remains blocked.
