# N3 20260611 B2 Trace-Aligned Realtime Projection For Standard Outbox Dry Run

Result: `DRY_RUN_PASS`

This dry-run is read-only. It did not execute B2, did not write database rows, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, and did not modify the scheduler.

Runner-compatible `projection_run_id_candidate` is present and matches the execute contract projection run id.

## Lineage

- projection_run_id: `realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- source_condition_run_id: `condition_layer_20260610_source_20260610_for_20260611_v1`
- subscription_run_id: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- preload_run_id: `previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- today_minute_run_id: `today_minute_bar_1m_20260611_until_1341__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- snapshot_run_id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

## Trace Proof

- snapshot rows stock/index/board/total: `1890/83/127/2100`
- `MarketSnapshotUpdated` rows: `2100`, pending: `2100`
- snapshot-to-outbox join by `payload_json.snapshot_id + identity_key`: `2100/2100`
- missing `pull_plan_id`: `0`
- missing `subscription_id`: `0`
- board normalized trace rows: `127/127`

## Projection Time Policy

- mode: `standard_outbox_observed_at_to_latest_closed_minute`
- bucket time source: `latest_closed_minute`
- latest closed minute: `2026-06-11T13:41:00+08:00`
- projection snapshot time: `2026-06-11T13:42:00+08:00`
- projection window: `20260611_1330_1400`
- B1 outbox payload mutation: `false`
- source observed_at/snapshot_time is preserved in trace fields.

## Row Builder Probe

Read-only `build_projection_rows` now materializes `2100` rows.

- stock/index/board/total: `1890/83/127/2100`
- ready/not_ready: `283/1817`
- ready by asset stock/index/board: `250/19/14`
- not_ready by asset stock/index/board: `1640/64/113`
- sample source snapshot time: `2026-06-11T15:34:16.368292+08:00`
- sample projection snapshot time: `2026-06-11T13:42:00+08:00`

## Quality

- P0/P1/P2: `0/1/0`
- P1: source standard outbox already has event infra refs observed read-only (`inbox_refs=4206`, `checkpoint_refs=4206`)

## Decision

This dry-run is ready for runtime_control execute final gate review. It does not authorize direct B2 execute.
