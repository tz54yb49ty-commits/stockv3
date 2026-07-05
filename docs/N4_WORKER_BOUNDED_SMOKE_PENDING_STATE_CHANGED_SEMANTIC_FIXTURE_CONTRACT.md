# N4_WORKER_BOUNDED_SMOKE_PENDING_STATE_CHANGED_SEMANTIC_FIXTURE_CONTRACT

Result: `CONTRACT_PASS`

## Scope

- smoke run: `n4_worker_bounded_smoke_20260608_pending_state_changed_semantic_fixture_probe`
- consumer: `n4_trigger_worker_v1_bounded_smoke_pending_state_changed_probe`
- source: `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- semantic fixture: `docs/N4_WORKER_BOUNDED_SMOKE_PENDING_STATE_CHANGED_SEMANTIC_FIXTURE.json`
- max events: `6`

## Requirements

- selected source events must remain pending N3 `MarketSnapshotUpdated`.
- fixture must be deterministic, `fixture_only=true`, `not_new_market_decision=true`.
- planned `TriggerPendingMarketData >= 1`.
- planned `TriggerStateChanged >= 1`.
- planned `TriggerMatched=0`.
- planned `common_trigger_match=0`.
- planned `N5 entry=0`.
- no N3 outbox update or consumption.
- no N5/N6, no worker long-run, no delivery/sim/trade path.

## Planned Writes If Future Execute Is Authorized

- `common_trigger_run=1`
- `common_trigger_quality_item=2`
- `common_event_inbox=6`
- `common_event_consumer_checkpoint=6`
- `common_trigger_state=6`
- `common_trigger_match=0`
- `common_event_outbox=8`

Coalesced state requirement: transition events remain `8`, but state unique keys are `6`; pending/state_changed same-key pairs must write one state row and two outbox events.

P0/P1/P2 = `0/0/0`
