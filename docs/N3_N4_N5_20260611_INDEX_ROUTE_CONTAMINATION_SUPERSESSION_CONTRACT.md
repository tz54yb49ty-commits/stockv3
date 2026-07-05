# N3/N4/N5 20260611 Index Route Contamination Supersession Contract

## Result

- result: `CONTRACT_PREFLIGHT_PASS`
- decision: `ALLOW_SCOPED_SUPERSESSION_EXECUTE_AFTER_LIVE_REF_REFRESH`
- scope: N3 B1 standard outbox, N3 B2 trace-aligned projection, N4 production semantic replay, N5 action run derived from the contaminated lineage

## Root Cause

N3 B1 index realtime snapshot used a naked-code quote route for SH/SZ index subscriptions. Same-code stock quotes could therefore be written under index identities, for example `index:SH:000009 / 上证380` carrying the price of `stock:SZ:000009 / 中国宝安`.

## Future Guard Fix

- `IndexMarketDataAdapter` now routes SH/SZ index subscriptions through `mootdx.index(symbol=..., frequency=9)`.
- `AssetRoutingRealtimeSnapshotAdapter` routes stock/default, SH/SZ index, BJ index, and TDX board separately.
- `identity_route_guard` blocks raw market/code/asset_kind mismatch before snapshot/outbox writes.
- TDX index period labels remain trace-only and are not trusted `event_time`.

## Contaminated Lineage

- N3 standard outbox run: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- N3 B2 projection run: `realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- N4 production run: `n4_production_semantic_replay_20260611_market_snapshot_updated_v1`
- N5 action run: `n5_action_bounded_20260611_from_n4_production_semantic_replay_v1`

## Live Preflight Proof

- N3 `MarketSnapshotUpdated`: `2100`, pending `2100`
- N4 production semantic rows: state `799`, match `548`, outbox `799`
- N5 action events: `548`
- N5 action outbox pending: `548`
- N5 downstream inbox/checkpoint refs: `0`
- N3 scheduler: `not_loaded`
- N4 scheduler: `not_loaded`

## Supersession Plan

The repair is a supersession, not deletion:

- N3 source `MarketSnapshotUpdated` pending rows become `dead_letter` with supersession trace.
- N3 B1 standard outbox and N3 B2 trace-aligned projection runs become `superseded`.
- N4 production semantic replay run becomes `superseded`; pending N4 outbox rows become `dead_letter`.
- N5 action run becomes `superseded`; pending N5 action outbox rows become `dead_letter`.
- Existing facts/events remain for audit.

## SQL Registry

- execute SQL: `sql/N3_N4_N5_20260611_index_route_contamination_supersession.sql`
- rollback SQL: `sql/N3_N4_N5_20260611_index_route_contamination_supersession_rollback.sql`

Both SQL files hard-fail before the first `UPDATE` and contain no `DROP`, `TRUNCATE`, or `CASCADE`.

## Forbidden Scope

- no row deletion
- no rollback execution by this contract
- no N6/user projection
- no voice/mobile/sim/trade
- old system untouched
