# N4 20260611 MarketSnapshotUpdated Production Trigger Semantic Replay Dry Run

Result: `DRY_RUN_PASS`

Layer role: `N4_trigger`

Generated at: `2026-06-11T22:46:20+08:00`

This gate did not execute N4, did not start a worker, did not write the database, did not consume/update N3 outbox/inbox/checkpoint, and did not enter N5/N6.

## Replay Scope

- replay_run_id: `n4_production_semantic_replay_20260611_market_snapshot_updated_v1`
- consumer_name: `n4_trigger_production_semantic_replay_20260611_market_snapshot_updated_v1`
- source_run_id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- projection_run_id: `realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- trigger_context_run_id: `trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- source MarketSnapshotUpdated total/pending: `2100/2100`
- stock/index/board source events: `1890/83/127`

## Reviewed Counts

- candidate_context_rows: `4480`
- TriggerMatched: `548`
- TriggerPendingMarketData: `251`
- TriggerStateChanged: `0`
- no-op / not matched: `3681`
- output plan total: `799`

## Distribution

- matched_by_signal_type: `{'B_BUY': 489, 'S_SELL': 59}`
- pending_by_signal_type: `{'B_BUY': 126, 'S_SELL': 125}`
- matched_by_trigger_mark_candidate: `{'30m_shrink': 9, '30m_volume': 18, 'normal': 521}`
- pending_by_trigger_mark_candidate: `{'normal': 251}`
- matched_by_asset_kind: `{'board': 2, 'index': 54, 'stock': 492}`
- pending_by_asset_kind: `{'board': 251}`

## Trace Alignment Proof

Projection rows stock/index/board/total: `1890/83/127/2100`.

Each projection asset channel joins the standard MarketSnapshotUpdated source by both `snapshot_event_id -> event_id` and `snapshot_id + identity_key -> payload snapshot_id + identity_key` for all rows.

## Quality

- P0/P1/P2: `0/1/0`
- P1 note: board not-ready rows remain visible as TriggerPendingMarketData / no-match evidence; they are not promoted to TriggerMatched.

## Fixture Exclusion

Fixture smoke `n4_worker_bounded_smoke_20260611_trigger_semantic_probe` is excluded. These counts are production semantic replay counts from localized N4 context plus N3 trace-aligned B2 projection input, not fixture-derived market decisions.

## Forbidden Scope

- N4 executed: `false`
- database written: `false`
- N3 outbox consumed/updated: `false`
- worker started: `false`
- N5/N6 entered: `false/false`
- trade/sim/position/voice/mobile touched: `false`
