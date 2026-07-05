# N4_WORKER_BOUNDED_SMOKE_PENDING_STATE_CHANGED_SEMANTIC_FIXTURE_PREFLIGHT

Result: `PREFLIGHT_PASS`

## Baseline

Target scoped rows are all zero:

- run/quality/state/match/outbox/inbox/checkpoint = `0/0/0/0/0/0/0`

## Source

- pending N3 `MarketSnapshotUpdated`: `2155`
- selected source events: `6`
- selected source events pending: `6`
- delivered/delivering: `0`

## Planned Scope

- `common_trigger_run=1`
- `common_trigger_quality_item=2`
- `common_event_inbox=6`
- `common_event_consumer_checkpoint=6`
- `common_trigger_state=6`
- `common_trigger_match=0`
- `common_event_outbox=8`

## Semantic Guards

- `TriggerPendingMarketData` match rows: `0`
- `TriggerStateChanged` match rows: `0`
- `n5_entry_allowed=true`: `0`
- N5 entry: `0`
- state unique keys: `6`
- transition events / outbox events: `8/8`
- duplicate state unique key in planned writes: `0`

P0/P1/P2 = `0/0/0`
