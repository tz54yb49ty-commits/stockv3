# N6 Real Delivery Provider Implementation Alignment

- result: `ALIGNMENT_PASS`
- layer_role: `N6_user`
- mode: implementation alignment / design only
- generated_at: `2026-06-10T14:37:26.188422+00:00`

## Prerequisite Proof

- provider policy refresh contract: `BLOCKED`
- provider policy refresh preflight: `PREFLIGHT_BLOCKED_FOR_EXECUTE`
- policy_design_chain_complete: `true`
- adapter abstraction: `CONTRACT_PASS`
- credential / secret policy: `CONTRACT_PASS`
- consent allowlist policy: `CONTRACT_PASS`
- retry / failure-state policy: `CONTRACT_PASS`
- attempt audit schema contract: `CONTRACT_PASS`
- N5 outbox ack/status policy: `CONTRACT_PASS`
- rollback / supersession policy: `CONTRACT_PASS`

## Implementation Gap Analysis

Current `src/ashare_v3/user/delivery_execute.py` and `scripts/run_n6_delivery_once.py` implement only `noop_local_preview_materialization`:

- current provider: `noop_local_provider_v1`
- current write scope: append-only preview rows in `user_notification_queue`
- real provider adapter: missing
- provider network send: missing and unauthorized
- real secret read / credential handoff: missing and unauthorized
- N5 outbox ack/status update: missing and unauthorized
- long-running worker: missing and unauthorized

This is the expected blocker state: the policy design chain is complete, but executable real delivery is still blocked until implementation, tests, schema/permission gates where applicable, final gate review, and explicit user confirmation.

## Proposed Implementation Scope

Allowed in the next implementation-planning gate:

- introduce provider adapter interfaces/classes while keeping network send disabled by default
- keep noop local preview adapter unchanged and first-class
- add dry-run provider adapter that can produce planned attempt metadata but cannot send network
- add real provider adapter skeleton behind `can_send_network=false` default and final-gate guard
- add capability snapshot fields: provider_id, adapter_kind, can_send_network, can_materialize_preview, requires_credentials, supports_provider_ack, writes_provider_attempt_audit
- add fail-closed checks for missing credential_ref, consent allowlist, attempt audit policy, retry/failure policy, rollback/supersession policy, final gate, or `can_send_network=false`

Still forbidden here:

- no provider send
- no secret read
- no DB write or migration
- no N5 outbox ack/status update
- no worker
- no delivery/push/voice/mobile side effect
- no sim/position/pnl/real_trade
- no proposal/order/trade

## Default-Disabled Network Proof

- implicit send permission: `false`
- default `can_send_network`: `false`
- real secret read authorized: `false`
- provider network send authorized: `false`
- real provider delivery authorized: `false`
- provider name alone is not permission: `true`
- noop can materialize preview: `true`
- noop can send network: `false`
- dry-run can send network: `false`
- real adapter skeleton must fail closed until final gate: `true`

## Required Tests

- current runner remains noop-only and makes no provider call
- missing `--execute` blocks before repository commit
- missing `--user-confirmed` blocks before repository commit
- real provider adapter default `can_send_network=false` blocks send
- real provider send requires explicit final gate flag
- no secret read without credential gate and opaque credential ref
- no provider transport call when `can_send_network=false`
- no N5 outbox status update without ack policy execute gate
- sanitizer excludes trace/source/raw N5 payload
- noop / dry-run / real provider separation is enforced
- consent, retry/failure, attempt audit, rollback/supersession policies are required before real send

## Forbidden Scope Proof

All false for this gate: DB write, provider send, network call, secret read, N5 outbox consumption/update, inbox/checkpoint write, worker, delivery/push/voice/mobile, sim/position/pnl/real_trade, proposal/order/trade, old system touch.

## Recommended Next Gate

`N6_REAL_DELIVERY_PROVIDER_ADAPTER_IMPLEMENTATION_PLAN_GATE`
