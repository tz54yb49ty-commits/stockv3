# N6 Real Delivery Credential / Secret Policy Readiness

Gate: `N6_REAL_DELIVERY_CREDENTIAL_SECRET_POLICY_READINESS_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:19:00+08:00`  
Result: `READINESS_PASS`

## Read-Only Boundary

This gate only evaluates readiness for a real provider delivery credential / secret policy contract. It did not execute N6, did not write the database, did not consume or update N5 outbox/inbox/checkpoint rows, did not start a worker, did not read real secrets, did not call a provider, did not perform delivery, push, voice, or mobile, and did not touch sim, position, PnL, real trade, proposal, order, or trade paths.

## Prerequisite Proof

- Provider adapter abstraction contract: `CONTRACT_PASS`
- Provider adapter abstraction preflight: `PREFLIGHT_PASS`
- Provider adapter abstraction final gate review: `CONTRACT_PASS`
- Adapter abstraction execute user confirmation allowed: `false`
- Real provider delivery remains deferred: `true`
- Provider network call authorized: `false`
- Credential use authorized: `false`
- N5 outbox ack/status change authorized: `false`
- Real delivery policy alignment: `ALIGNMENT_PASS`
- Real delivery provider policy readiness previously identified credential/secret policy as a required P1 design gate.

The adapter abstraction contract froze a provider boundary, but it explicitly kept real network send and credential use disabled. This readiness gate therefore may proceed to credential policy design without reading, loading, printing, or validating any real secret value.

## Credential / Secret Policy Gap Analysis

The following items are not yet frozen and must be handled before any provider adapter can receive credentials:

- Credential source policy is missing.
- Secret storage location and access boundary are missing.
- Secret naming and provider identity binding are missing.
- Secret value redaction rules for logs, JSON artifacts, Markdown artifacts, command output, errors, and audit rows are missing.
- Credential rotation and revocation policy is missing.
- Least-privilege runtime access policy is missing.
- Local development / dry-run credential policy is missing.
- Production credential use approval gate is missing.
- Credential failure classification is missing.
- Provider adapter handoff policy is missing.
- Secret audit metadata policy is missing.
- Incident response and emergency disable policy is missing.

## Proposed Credential Policy Scope

The next contract gate should freeze a policy with these minimum sections:

- Credential identifiers only, never credential values, may appear in artifacts.
- Secret values must never be written to docs, JSON reports, logs, stdout, stderr, SQL, rollback SQL, git diff, or provider attempt audit rows.
- Credential source must be one of an explicitly approved secret provider, environment variable reference, or OS keychain reference.
- Secret references must be provider-scoped and environment-scoped.
- Adapter may receive only an opaque credential handle after credential policy, consent policy, retry policy, rollback/supersession policy, final gate, and user confirmation pass.
- Dry-run and noop adapters must not require or receive production credentials.
- Real provider adapter must fail closed if credential reference is missing, expired, revoked, or not approved for the channel.
- Credential rotation must preserve audit lineage without exposing prior values.
- Revocation must block future sends and mark pending attempts as policy-blocked or superseded.
- Any future command must redact secret-like values before writing artifacts.

## Redaction / Audit Requirements

Required redaction rules:

- Store and display only credential reference ids.
- Store and display only secret hash fingerprints if explicitly needed, never full hashes of raw secret values unless policy allows a non-reversible fingerprint.
- Replace accidental secret-like values with `[REDACTED_SECRET]`.
- Treat provider tokens, webhook URLs, API keys, signing secrets, phone provider credentials, push certificates, and SMTP passwords as secrets.
- Redaction must apply before Markdown/JSON artifact write.
- Redaction must apply before provider attempt audit write.
- Redaction must apply to exception text and validation errors.

Required audit metadata:

- `credential_ref`
- `provider_id`
- `adapter_kind`
- `environment`
- `secret_policy_version`
- `rotation_generation`
- `credential_status`
- `access_decision`
- `access_reason`
- `secret_value_materialized=false` for readiness/contract gates

## Safety Requirements

- No real secret may be read in this gate.
- No credential may be printed or copied into artifacts.
- No provider network send may occur.
- No provider adapter may receive credentials.
- No N5 outbox status update may occur.
- No N5 inbox/checkpoint rows may be written.
- No delivery/push/voice/mobile side effect may occur.
- No sim/position/PnL/real_trade/proposal/order/trade path may be touched.
- Any future credential-bearing execute must have credential contract, consent contract, retry/failure contract, rollback/supersession contract, preflight, final gate, and explicit user confirmation.

## Rollback / Supersession Planning

This readiness gate has no write scope and no rollback execution.

Future credential policy must define:

- Emergency credential revocation.
- Adapter-level kill switch.
- Provider-level disable flag.
- Supersession of pending delivery attempts after credential revocation.
- Audit preservation for credential access decisions.
- No deletion of credential access audit after external provider side effects are possible.
- Preservation of noop preview evidence and N5 outbox state.

## Quality

```text
P0=0
P1=8
P2=3
```

P1 items:

- credential source policy not frozen
- secret storage/access boundary not frozen
- redaction policy not frozen
- rotation/revocation policy not frozen
- least-privilege runtime access policy not frozen
- adapter credential handoff policy not frozen
- credential failure classification not frozen
- credential audit metadata policy not frozen

P2 items:

- real provider delivery remains deferred
- credential contract will still not authorize send by itself
- long-running delivery worker lifecycle remains unapproved

## Forbidden Scope Proof

- SQL executed: `false`
- database written: `false`
- N5 outbox/inbox/checkpoint consumed or updated: `false`
- N6 execute entered: `false`
- worker started: `false`
- long-running worker started: `false`
- real secret read: `false`
- secret value printed or stored: `false`
- provider adapter received credential: `false`
- provider network call: `false`
- actual delivery / push / voice / mobile: `false`
- sim / position / PnL / real trade: `false`
- proposal / order / trade: `false`
- rollback SQL executed: `false`
- old system touched: `false`

## Readiness Decision

`READINESS_PASS`: the project may enter the credential / secret policy contract gate.

This does not authorize real provider delivery, provider network calls, credential reads, credential handoff to adapters, N5 outbox ack/status changes, delivery/push/voice/mobile, sim, position, PnL, real trade, proposal, order, trade, or a long-running worker.

## Recommended Next Gate

```text
N6_REAL_DELIVERY_CREDENTIAL_SECRET_POLICY_CONTRACT_GATE
```
