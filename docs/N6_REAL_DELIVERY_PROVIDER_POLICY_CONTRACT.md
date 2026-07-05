# N6 Real Delivery Provider Policy Contract

Gate: `N6_REAL_DELIVERY_PROVIDER_POLICY_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated at: `2026-06-10T21:58:00+08:00`  
Result: `BLOCKED`

## Contract Decision

The source preview evidence is clean, but the real provider delivery contract is not executable. This gate therefore blocks entry to `N6_REAL_DELIVERY_PROVIDER_POLICY_EXECUTE_USER_CONFIRMATION_GATE`.

No allowed execute command is produced.

## Prerequisite Proof

- N6 real delivery provider policy readiness: `READINESS_PASS`
- N6 delivery noop rollback readiness: `READINESS_PASS`
- N6 delivery noop rollout registration: `REGISTRATION_PASS`
- N6 delivery noop post-review: `POST_REVIEW_PASS`
- N6 runtime spec confirms delivery/push/voice/mobile policy belongs only to N6.
- Noop rows are registered evidence, not real send authorization.

## Source Noop Preview Proof

- source rows: `50`
- notification_source: `n6_delivery_materialized_noop`
- queue_status: `ready_for_future_push`
- channel: `in_app_notification_preview`
- projection_policy: `noop_local_preview_materialized_no_delivery`
- provider: `noop_local_provider_v1`

N5 source preservation:

- N5 outbox pending: `50`
- N5 outbox delivered/delivering: `0/0`
- N5 outbox consumed/update: `false`

## Provider Policy Contract

This contract freezes the following default policy:

- real provider delivery remains disabled
- push / voice / mobile remain disabled
- N5 outbox ack/status update remains disabled
- delivery attempts are not materialized
- source noop preview rows are read-only registered evidence
- provider payload must remain sanitized and must not expose upstream raw payloads or traces
- any future real provider delivery must use a separate provider adapter alignment gate, contract, preflight, final gate, rollback SQL, and explicit user confirmation

## Contract Blockers

The following P0 blockers prevent an execute gate:

- `real_provider_adapter_missing_or_not_authorized`
- `credential_secret_policy_missing`
- `user_channel_consent_allowlist_policy_missing`
- `retry_backoff_failure_state_policy_missing`
- `provider_delivery_attempt_write_contract_missing`
- `n5_outbox_ack_status_policy_not_approved`
- `provider_delivery_rollback_supersession_policy_missing`

## Planned Write Scope

Because the contract is blocked, planned writes are all zero:

- provider delivery / attempt rows: `0`
- user push / voice / mobile rows: `0`
- N5 outbox status updates: `0`
- N5 inbox/checkpoint rows: `0`
- sim / position / PnL / real trade rows: `0`
- proposal / order / trade rows: `0`

## Rollback Proof

Rollback SQL was generated as a disabled-by-default safety placeholder:

```text
sql/N6_real_delivery_provider_policy_20260608_chained_shadow_probe_rollback.sql
```

It hard-fails before any destructive statement, contains the target run/source lineage literals, preserves source noop preview rows and N5 outbox state, and contains no `CASCADE`, `DROP`, or `TRUNCATE`.

## Forbidden Scope Proof

- SQL executed: `false`
- database written: `false`
- N5 outbox/inbox/checkpoint consumed or updated: `false`
- N6 execute entered: `false`
- worker started: `false`
- long-running worker started: `false`
- actual delivery / push / voice / mobile: `false`
- sim / position / PnL / real trade: `false`
- proposal / order / trade: `false`
- rollback SQL executed: `false`
- old system touched: `false`

## Result

`BLOCKED`: contract artifacts are generated, but real provider delivery execution is not allowed.

