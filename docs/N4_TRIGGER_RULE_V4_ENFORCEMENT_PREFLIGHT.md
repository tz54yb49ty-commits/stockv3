# N4 Trigger Rule v4 Enforcement Preflight

Status: PREFLIGHT_BLOCKED

Layer role: `N4_trigger`

This is a strict enforcement preflight after rollback of the noncompliant
20260605 N4 execute run. No database writes are authorized.

## Result

The enforcement layer is installed, but the current stale 20260605 dry-run /
execute artifacts are not v4-compliant and must not be executed.

## Current Stale Artifact Findings

- candidate matched plans: `1537`
- persisted write plans after strict N5 entry guard: `0`
- invalid N5 entry candidates: `1537`

Violation counts observed from the stale candidate set:

- `missing_trigger_price`: `1537`
- `missing_trigger_kind`: `1537`
- `missing_triggered_periods`: `1537`
- `missing_n5_entry_allowed`: `1537`
- `invalid_trigger_kind`: `1537`
- `invalid_n5_entry_contract`: `1537`
- `trigger_price_source_missing`: `1537`
- `historical_full_candidates_before_whitelist_repair`: `29`
- `event_time_after_created_at`: `63`
- `missing_all_trigger_periods`: `275`
- `missing_primary_trigger_period`: `275`
- `missing_trigger_live`: `275`
- `missing_current_status`: `275`

## Boundary Proof

- N4 execute: not authorized
- DB writes: not authorized
- outbox consumption: not authorized
- N5/N6: not entered
- worker: not started
- delivery / push / voice / mobile / sim / position / real trade: forbidden

## Next Step

Allowed next route:

```text
N4 corrected dry-run gate
```

The corrected dry-run must regenerate v4-compliant plans with first-class
`trigger_price`, `trigger_kind`, `triggered_periods`, `n5_entry_allowed`,
bounded `event_time/trigger_time`, and reviewed N3 price lineage before any
execute preflight can pass.
