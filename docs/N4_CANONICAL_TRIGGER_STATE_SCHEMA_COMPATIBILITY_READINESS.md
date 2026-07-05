# N4 Canonical Trigger State Schema Compatibility Readiness

Result: `DRAFT_PASS`

This draft aligns the trigger schema with the canonical `TriggerStateChanged` contract without executing a migration or writing business rows.

## Scope

Migration draft:

- `sql/024_trigger_canonical_state_compatibility_migration.sql`
- `sql/024_trigger_canonical_state_compatibility_rollback.sql`

Touched tables:

- `common_trigger_state`
- `common_trigger_match`

Untouched:

- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- N3 facts
- N5/N6 facts
- historical runtime rows

## Constraint Compatibility

The draft relaxes HINT constraints so both canonical and legacy rows remain valid:

- `BUY_HINT -> signal_type=B_BUY`
- `BUY_HINT -> signal_type=BUY_HINT`
- `SELL_HINT -> signal_type=S_SELL`
- `SELL_HINT -> signal_type=SELL_HINT`

Legacy rows stay valid for audit. New canonical business rows remain blocked until migration final gate and later N4 execute final gate.

## Additive Columns

`common_trigger_state` gains first-class state fields:

- `trigger_live BOOLEAN`
- `trigger_mark_candidate TEXT`
- `primary_trigger_period TEXT`
- `all_trigger_periods JSONB`
- `projection_30m_flag BOOLEAN`
- `projection_30m_type TEXT`

`common_trigger_match` gains:

- `trigger_mark_candidate TEXT`

These are compatibility fields for canonical payloads. Existing `raw_json` remains usable for trace details.

## Event Outbox

`common_event_outbox` does not need a migration. The event infra does not block `TriggerStateChanged` for `source_layer=N4_trigger`, and the code-level N4 event allowlist already owns canonical validation.

## Trigger Match Boundary

`common_trigger_match` intentionally remains outcome-only:

- records `TriggerMatched`
- records `TriggerPendingMarketData`
- does not record `TriggerStateChanged`

`TriggerStateChanged` is a state broadcast event and must not become a trigger match row.

## Rollback Guards

Rollback is blocked if canonical HINT rows exist:

- `BUY_HINT + signal_type=B_BUY`
- `SELL_HINT + signal_type=S_SELL`

Rollback is also blocked if any additive columns contain values. Business rollback must clear scoped runtime rows before schema rollback is eligible.

Rollback must not touch N3 facts, N5/N6 facts, outbox, inbox, checkpoint, or historical run rows.

## Execute Status

N4 business execute remains `BLOCKED`.

Allowed next step: return to migration final gate for user-confirmed schema execution review.

Still forbidden until a later final gate:

- N4 trigger execute
- common_event_outbox writes
- common_trigger_state / common_trigger_match business writes
- N5/N6 execution
- worker startup
