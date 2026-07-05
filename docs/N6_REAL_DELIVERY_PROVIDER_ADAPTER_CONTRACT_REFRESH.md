# N6 Real Delivery Provider Adapter Contract Refresh

Gate: `N6_REAL_DELIVERY_PROVIDER_ADAPTER_CONTRACT_REFRESH_GATE`  
Layer role: `N6_user`  
Generated at: `2026-06-10T23:06:17+08:00`  
Result: `CONTRACT_PASS`

## Boundary

This gate refreshes the provider adapter abstraction contract using the implemented framework evidence. It did not execute N6, write database rows, read real secrets, call providers, consume/update N5 outbox/inbox/checkpoint rows, start a worker, perform delivery/push/voice/mobile, touch sim/position/PnL/real trade, create proposal/order/trade, or touch the old system.

## Prerequisite Proof

- implementation post-review: `POST_REVIEW_PASS`
- implementation report: `IMPLEMENTATION_PASS`
- provider adapter framework complete: `true`
- previous adapter abstraction contract: `CONTRACT_PASS`
- real provider policy refresh contract: `BLOCKED`
- policy design chain complete: `true`

## Implemented Adapter Evidence

- `DeliveryProviderAdapter` interface exists.
- `NoopLocalPreviewAdapter` exists and remains no-network.
- `DryRunProviderAdapter` exists and remains no-network.
- `RealProviderAdapterSkeleton` exists and defaults `can_send_network=false`.
- No HTTP/provider SDK was introduced.
- Fake transport call count remains `0`.
- Credential handling is opaque `credential_ref` only.
- No real secret read path exists.
- N5 outbox update path is absent.

## Refreshed Adapter Contract Summary

Contract version: `n6_provider_adapter_abstraction_v2_implemented_framework`

The adapter abstraction is now refreshed from design-only to implemented-framework evidence:

- Protocol: `DeliveryProviderAdapter`
- Methods:
  - `capability() -> ProviderCapability`
  - `build_provider_visible_payload(input) -> dict`
  - `send(input, *, final_gate_token=None) -> ProviderSendResult`
- Required capability defaults:
  - `can_send_network=false`
  - `can_update_n5_outbox_status=false`
  - `writes_provider_attempt_audit=false`
  - `supports_provider_ack=false`

Implemented adapter kinds:

| adapter | provider_id | send result | network |
|---|---|---|---|
| noop local preview | `noop_local_provider_v1` | `NOOP` | disabled |
| dry-run provider | `dry_run_provider_v1` | `DRY_RUN` | disabled |
| real provider skeleton | `real_provider_skeleton_v1` | `BLOCKED` until future gates | disabled by default |

Provider-visible payload policy:

- allowed surface: schema version, materialization run id, source queue id, provider id, channel, title, message
- forbidden families: trace, source payload, raw/card/display payload, N5 raw payload, outbox internals, action-run internals, credential/secret material
- guard: `provider_payload_has_forbidden_keys`
- report redaction: `redact_provider_report`

Fail-closed guards:

- `missing_final_execute_gate`
- `network_send_not_enabled`
- `can_send_network_false`
- `credential_ref_missing`
- `credential_ref_not_opaque`
- `secret_supplied`
- `consent_not_allowed`
- `retry_policy_missing`
- `attempt_audit_policy_missing`
- `n5_ack_policy_missing`
- `rollback_supersession_policy_missing`
- `provider_payload_contains_forbidden_keys`

## Real Provider Execute Blocker Summary

Real provider execute remains blocked. The implementation framework is complete, but real delivery cannot enter execute until all required runtime gates are passed.

Current blockers:

- dry-run provider bounded smoke has not passed yet
- real credential materialization is not authorized
- real consent materialization is not authorized
- provider attempt audit schema is not executed if writes are required
- N5 outbox ack/status mutation remains disabled
- real provider final execute gate is missing
- `can_send_network` defaults to `false`

Still required before any real send:

- `N6_REAL_DELIVERY_DRY_RUN_PROVIDER_BOUNDED_SMOKE_READINESS_GATE`
- bounded dry-run provider smoke
- credential materialization gate
- consent materialization gate
- provider attempt audit schema execute/post-review if writes are required
- N5 outbox ack/status final gate if status mutation is requested
- real provider final execute gate with explicit user confirmation

## Dry-Run Provider Bounded Smoke Readiness

This contract refresh allows entry to:

```text
N6_REAL_DELIVERY_DRY_RUN_PROVIDER_BOUNDED_SMOKE_READINESS_GATE
```

Scope for the next gate:

- adapter: `DryRunProviderAdapter`
- no network
- no real secret
- no database write
- no N5 outbox mutation
- expected fake transport call count: `0`

## Validation

- JSON parse: `PASS`
- `python3 -m unittest tests/test_n6_delivery_execute.py`: `PASS`
- `python3 -m compileall src scripts tests`: `PASS`
- network SDK scan: `PASS`
- provider post-review probe: `PASS`
- N5 outbox update path scan: `PASS`
- `git diff --check`: `PASS`

## Forbidden Scope Proof

- N6 execute: `false`
- database write: `false`
- real secret read: `false`
- provider call: `false`
- provider network send: `false`
- N5 outbox consumed/updated: `false`
- N5 inbox/checkpoint write: `false`
- worker started: `false`
- delivery/push/voice/mobile: `false`
- sim/position/PnL/real trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Decision

`CONTRACT_PASS`

The provider adapter abstraction contract is refreshed with implemented-framework evidence. Real provider execution remains blocked, but this can be used as evidence for the next readiness gate:

```text
N6_REAL_DELIVERY_DRY_RUN_PROVIDER_BOUNDED_SMOKE_READINESS_GATE
```
