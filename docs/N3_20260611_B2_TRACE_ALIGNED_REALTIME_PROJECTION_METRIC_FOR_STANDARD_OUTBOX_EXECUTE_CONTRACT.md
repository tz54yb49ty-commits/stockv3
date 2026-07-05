# N3 20260611 B2 Trace-Aligned Standard Outbox Execute Contract

Contract result: `CONTRACT_PASS`

The contract is ready for runtime_control final gate review. It preserves `MarketSnapshotUpdated.event_id / payload_json.snapshot_id / identity_key` trace and does not mutate the B1 standard outbox payload.

Runner-compatible stage: `N3-B2-realtime-projection-execute-contract`

## Target

- projection_run_id: `realtime_projection_metric_20260611_trace_aligned_standard_outbox__realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- source snapshot run: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- source today minute run: `today_minute_bar_1m_20260611_until_1341__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

## Projection Time Policy

- mode: `standard_outbox_observed_at_to_latest_closed_minute`
- bucket time source: `latest_closed_minute`
- latest closed minute: `2026-06-11T13:41:00+08:00`
- projection snapshot time: `2026-06-11T13:42:00+08:00`
- projection window: `20260611_1330_1400`
- stored projection metric `snapshot_time` semantics: `projection_bucket_time`
- source observed_at/snapshot_time is preserved in `raw_json.source_snapshot_time`
- B1 outbox payload mutation: `false`

## Trace Requirements

- Require `snapshot_event_id`: true
- Require `payload_json.snapshot_id`: true
- Require `identity_key` match: true
- Require `subscription_id`: true
- Require `pull_plan_id`: true
- Allow missing snapshot event id: false
- Update MarketSnapshotUpdated payload: false

Read-only proof shows `2100/2100` snapshot rows join to `MarketSnapshotUpdated` by `payload_json.snapshot_id + identity_key`.

## Expected Rows

- stock/index/board/total: `1890/83/127/2100`
- ready/not_ready: `283/1817`
- ready by asset stock/index/board: `250/19/14`
- not_ready by asset stock/index/board: `1640/64/113`

## Allowed Write Scope

Only after a separate execute final gate and user confirmation:

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_realtime_projection_metric`
- `index_realtime_projection_metric`
- `board_realtime_projection_metric`

## Forbidden Scope

- no outbox/inbox/checkpoint writes or consumption
- no snapshot/minute fact writes
- no N4/N5/N6 writes
- no worker
- no scheduler modification
