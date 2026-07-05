# N6 Real Delivery Credential / Secret Policy Contract

Gate: `N6_REAL_DELIVERY_CREDENTIAL_SECRET_POLICY_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T22:30:00+08:00`  
Result: `CONTRACT_PASS`

## Boundary

This is a policy-only contract. It did not execute N6, did not write the database, did not consume or update N5 outbox/inbox/checkpoint rows, did not start a worker, did not read or print real secrets, did not call a provider, and did not perform delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade work.

## Prerequisite Proof

- Credential / secret policy readiness: `READINESS_PASS`
- Adapter abstraction contract: `CONTRACT_PASS`
- Adapter preflight: `PREFLIGHT_PASS`
- Adapter final gate: `CONTRACT_PASS`
- Real provider delivery remains deferred: `true`
- Credential read authorized: `false`
- Provider network send authorized: `false`

## Credential Source / Storage Policy

Allowed credential source references:

- `approved_secret_provider_ref`
- `environment_variable_ref`
- `os_keychain_ref`

Only references may be stored in artifacts. Secret values must never be copied to Markdown, JSON, SQL, logs, stdout, stderr, git diff, provider attempt audit rows, or rollback SQL. Every credential reference must be scoped by provider, channel, environment, and policy version.

No production credential may be provided to `noop_local` or `dry_run_provider` adapters. A `real_provider` adapter may receive only an opaque credential handle, and only after credential, consent, retry, audit, ack/status, rollback/supersession, final gate, and explicit user confirmation all pass.

## Redaction / No-Secret-Artifact Proof

Required redaction token: `[REDACTED_SECRET]`.

Secret-like values include provider tokens, API keys, webhook URLs, signing secrets, SMTP passwords, push certificates, voice/mobile provider credentials, private keys, and bearer tokens.

Redaction must run before:

- Markdown artifact write
- JSON artifact write
- provider attempt audit write
- exception reporting
- validation error reporting
- command summary output

This contract contains no secret values and authorizes no secret read.

## Rotation / Revocation Policy

- Credential references must carry `rotation_generation`.
- Revoked credentials must fail closed.
- Expired credentials must fail closed.
- Rotation must preserve historical audit lineage without exposing old values.
- Emergency revocation must block future sends.
- Pending attempts after revocation must become `policy_blocked` or `superseded`.
- A provider-level disable switch must override all credential references.

## Adapter Credential Handoff Policy

The adapter handoff object may contain:

- `credential_ref`
- `provider_id`
- `channel`
- `environment`
- `secret_policy_version`
- `rotation_generation`
- `access_decision`
- `access_reason`

It must not contain:

- raw secret value
- decoded token
- webhook URL value
- private key material
- bearer token
- password

## Credential Failure Classification

Canonical credential failure classes:

- `credential_policy_blocked`
- `credential_ref_missing`
- `credential_ref_not_allowed_for_provider`
- `credential_ref_not_allowed_for_channel`
- `credential_expired`
- `credential_revoked`
- `credential_provider_unavailable`
- `credential_redaction_violation`
- `credential_access_audit_failed`

All credential failure states must fail closed and prevent provider send.

## Credential Audit Metadata Contract

Required audit metadata:

- `credential_ref`
- `provider_id`
- `adapter_kind`
- `channel`
- `environment`
- `secret_policy_version`
- `rotation_generation`
- `credential_status`
- `access_decision`
- `access_reason`
- `secret_value_materialized`

For this gate, `secret_value_materialized=false`.

## Planned Write Scope

- credential rows: `0`
- provider attempt rows: `0`
- N5 outbox updates: `0`
- N5 inbox/checkpoint rows: `0`
- delivery/push/voice/mobile rows: `0`
- sim/position/PnL/real_trade rows: `0`
- proposal/order/trade rows: `0`

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

## Recommended Next Gate

```text
N6_REAL_DELIVERY_USER_CHANNEL_CONSENT_ALLOWLIST_READINESS_GATE
```
