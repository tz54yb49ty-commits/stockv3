# N4 20260611 Production Trigger Semantic Replay Contract

Result: `CONTRACT_PASS`

This contract is read-only and does not authorize N4/N5 execute, scheduler changes, database writes, rollback, outbox consumption, or worker start.

## Source Replay Scope

- source event: `N3_market_data / MarketSnapshotUpdated`
- source run: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- trade date: `20260611`
- source rows: `2100`, all `pending`
- asset rows: stock `1890`, index `83`, board `127`
- max-events: `2100`
- N3 outbox status update: not allowed

## New Consumer Policy

Use a new reviewed consumer:

`n4_trigger_production_semantic_replay_20260611_market_snapshot_updated_v1`

Replay run:

`n4_production_semantic_replay_20260611_market_snapshot_updated_v1`

The replay must not reuse:

- `n4_trigger_worker_v1_bounded_polling_20260611`
- `n4_worker_bounded_smoke_20260611_trigger_semantic_probe`

Baseline must be zero for inbox, checkpoint, trigger run, quality, trigger state, trigger match, and N4 outbox before any execute final gate.

## Output Policy

Allowed N4 events:

- `TriggerMatched`
- `TriggerPendingMarketData`
- `TriggerStateChanged`

Forbidden from this N4 replay:

- N5 action events
- N6/user events
- legacy trigger clear/live-change events as new canonical output
- any trade/sim/position/voice/mobile path

`TriggerMatched` is the only possible N5 entry, and only after production replay post-review passes. Fixture smoke rows are excluded.

## Rollback Requirements

Rollback draft:

`sql/N4_20260611_market_snapshot_updated_production_trigger_semantic_replay_rollback.sql`

It must hard-fail before row removal, delete only this replay run and new consumer scope, guard N5/N6/downstream refs, and must not touch N3 source outbox, bounded polling evidence, fixture smoke rows, or historical runs.
