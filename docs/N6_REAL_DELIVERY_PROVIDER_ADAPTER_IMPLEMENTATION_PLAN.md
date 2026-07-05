# N6 Real Delivery Provider Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. This gate itself is planning only and does not modify code.

**Goal:** Add a real delivery provider adapter framework and tests while keeping every real network send disabled by default.

**Architecture:** Keep the existing noop local preview runner as the only executable behavior. Add a separate provider adapter abstraction layer with noop, dry-run, and real-provider-skeleton adapters; every adapter exposes explicit capability flags, and real provider send fails closed unless a later final gate enables `can_send_network=true` and all policy hooks pass.

**Tech Stack:** Python dataclasses/protocols, existing `src/ashare_v3/user/delivery_execute.py`, `scripts/run_n6_delivery_once.py`, `unittest`, no provider SDK, no secret access, no DB write in this gate.

---

## Result

- result: `PLAN_PASS`
- blockers: `[]`
- planning only: `true`
- code modified: `false`
- DB write: `false`
- provider send: `false`
- secret read: `false`

## Prerequisite Proof

- implementation alignment: `ALIGNMENT_PASS`
- policy_design_chain_complete: `True`
- adapter abstraction: `CONTRACT_PASS`
- credential secret policy: `CONTRACT_PASS`
- consent allowlist policy: `CONTRACT_PASS`
- retry/failure-state policy: `CONTRACT_PASS`
- attempt audit schema contract: `CONTRACT_PASS`
- N5 outbox ack/status policy: `CONTRACT_PASS`
- rollback supersession policy: `CONTRACT_PASS`
- current runner mode: `noop_local_preview_materialization`

## File Plan For Next Gate

- Create `src/ashare_v3/user/delivery_provider.py`: provider protocol, capability model, provider-visible input/result dataclasses, noop/dry-run/real skeleton adapters, fail-closed guard helpers.
- Modify `src/ashare_v3/user/delivery_execute.py`: preserve existing noop materialization; optionally import provider capability helpers for preflight validation; do not add provider send calls to the existing execute path.
- Keep `scripts/run_n6_delivery_once.py` functionally noop-only unless a later final execute gate explicitly adds a real-send command surface.
- Modify `tests/test_n6_delivery_execute.py`: add provider framework tests and no-accidental-send tests with fake transport and fake secret resolver.
- Create next-gate proof artifacts `docs/N6_REAL_DELIVERY_PROVIDER_ADAPTER_IMPLEMENTATION.md/json` only during implementation gate.

## Provider Adapter Interface

Planned protocol: `DeliveryProviderAdapter`.

Required methods:

- `capability() -> ProviderCapability`
- `build_provider_visible_payload(input) -> dict`
- `send(input, *, final_gate_token=None) -> ProviderSendResult`

Capability fields:

- `provider_id`
- `adapter_kind`
- `channel`
- `can_materialize_preview`
- `can_send_network`
- `requires_credentials`
- `supports_provider_ack`
- `writes_provider_attempt_audit`
- `credential_ref_required`
- `consent_required`
- `retry_policy_required`
- `audit_policy_required`
- `n5_ack_policy_required`
- `rollback_supersession_required`

Send input uses only opaque `credential_ref`, never a secret value.

## Adapter Kinds

### noop_local_preview

- preserves existing behavior
- can materialize preview: `true`
- can send network: `false`
- requires credentials: `false`
- send behavior: no-op/block result, no network call

### dry_run_provider

- can send network: `false`
- requires credentials: `false`
- returns planned attempt metadata only
- `network_send_attempted=false`
- `provider_delivery_confirmed=false`

### real_provider_skeleton

- can send network default: `false`
- requires credentials: `true`
- accepts only opaque `credential_ref`
- secret value access remains forbidden
- blocks unless future final gate enables real send and all policy hooks pass

## Policy Hooks

- Credential: opaque credential ref only; no secret read/print/artifact.
- Consent: user/channel/provider allowlist must pass before send.
- Retry/failure: classify only; no retry loop or worker.
- Attempt audit: real send must be blocked if audit write path/policy is missing.
- N5 ack/status: no ack/update without a separate execute gate.
- Rollback/supersession: missing policy blocks real send.

## Fail-Closed Guards

- missing final execute gate
- `can_send_network=false`
- adapter kind not allowed for gate
- missing or disallowed credential ref
- secret-like value supplied to report/payload
- missing consent
- missing retry/failure policy
- missing attempt audit policy/write path
- missing N5 ack policy for status update
- missing rollback/supersession policy
- provider payload contains internal keys

## Task Plan For Next Gate

### Task 1: Provider Capability Tests

**Files:**
- Modify `tests/test_n6_delivery_execute.py`

- [ ] Add failing tests for capability defaults: noop/dry-run/real skeleton all have `can_send_network=false` by default.
- [ ] Add fake transport with call counter and assert no adapter calls it without explicit final gate enablement.
- [ ] Run `python3 -m unittest tests/test_n6_delivery_execute.py` and confirm the new tests fail before implementation.

### Task 2: Provider Adapter Module

**Files:**
- Create `src/ashare_v3/user/delivery_provider.py`

- [ ] Define `ProviderCapability`, `ProviderSendInput`, `ProviderSendResult` dataclasses.
- [ ] Define `DeliveryProviderAdapter` protocol.
- [ ] Implement `NoopLocalPreviewAdapter`, `DryRunProviderAdapter`, `RealProviderAdapterSkeleton`.
- [ ] Implement fail-closed guard helper returning explicit blockers.
- [ ] Run targeted tests and confirm pass.

### Task 3: Preserve Existing Delivery Runner

**Files:**
- Modify `src/ashare_v3/user/delivery_execute.py`
- Keep `scripts/run_n6_delivery_once.py` functionally unchanged

- [ ] Ensure existing noop materialization tests still pass.
- [ ] Ensure no provider transport is invoked from `run_delivery_materialization_execute`.
- [ ] Ensure missing `--execute` and missing `--user-confirmed` still block before repository read/commit.

### Task 4: Secret / Payload / Outbox Safety Tests

**Files:**
- Modify `tests/test_n6_delivery_execute.py`

- [ ] Add test that secret-like values never appear in reports/artifacts.
- [ ] Add test that only opaque `credential_ref` may pass through provider input.
- [ ] Add test that N5 outbox status update plan remains absent.
- [ ] Add test that provider-visible payload excludes trace/source/raw N5 payload.

### Task 5: Implementation Proof Artifact

**Files:**
- Create `docs/N6_REAL_DELIVERY_PROVIDER_ADAPTER_IMPLEMENTATION.md`
- Create `docs/N6_REAL_DELIVERY_PROVIDER_ADAPTER_IMPLEMENTATION.json`

- [ ] Record modified files, test results, static scans, and forbidden scope proof.
- [ ] Run `python3 -m compileall src scripts tests`.
- [ ] Run `python3 -m unittest tests/test_n6_delivery_execute.py`.
- [ ] Run JSON parse and `git diff --check`.

## Required Tests

- `test_missing_final_execute_gate_blocks_send`
- `test_can_send_network_false_blocks_real_send`
- `test_noop_and_dry_run_never_call_network`
- `test_real_provider_skeleton_without_explicit_enable_never_calls_network`
- `test_secret_values_never_appear_in_report_or_artifact`
- `test_n5_outbox_status_unchanged`
- `test_provider_payload_excludes_trace_source_raw_payload`
- `test_attempt_audit_required_before_real_send`
- `test_consent_retry_rollback_hooks_required_before_real_send`

## Forbidden Scope Proof

This planning gate did not and does not authorize:

- code modification
- database write
- provider send or network call
- secret read or credential materialization
- N5 outbox consume/update
- N5 inbox/checkpoint write
- worker startup
- delivery/push/voice/mobile
- sim/position/pnl/real_trade
- proposal/order/trade
- old system touch

## Recommended Next Gate

`N6_REAL_DELIVERY_PROVIDER_ADAPTER_IMPLEMENTATION_GATE`
