# N3 20260603 Projection Enrichment Refresh Report

- result: `REFRESH_PASS`
- source_condition_run_id: `condition_layer_20260602_source_20260602_v1`
- snapshot_run_id: `realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- today_minute_run_id: `today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1`
- previous_day_minute_run_id: `previous_day_minute_preload_20260602_for_20260603_full_context_expansion__market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1`
- expected_context_candidates: `5222`

## Row Summary
- projection row count: `5222`
- enrichment_rows: `5218`
- complete_lineage_rows: `5218`
- missing_source_minute_rows: `4`
- trigger_amount_chain_pass_rows: `5218`
- projection_30m_coverage_rows: `5218`

## BJ Quality Proof
- `index:BJ:899050` and `index:BJ:899601` remain explicit `missing` source-minute rows in both full-context C1 and previous-day preload evidence.
- They are classified as P1 quality-visible rows; no silent fallback is allowed.

## Quality
- P0/P1/P2: `0/2/0`
- P1: `n3_projection_enrichment_bj_source_minute_quality_visible` actual=`{'index:BJ:899050': 2, 'index:BJ:899601': 2}`
- P1: `n3_projection_enrichment_snapshot_event_trace_absent` actual=`0`

## Boundary
- read-only refresh; no DB business rows written
- no outbox/inbox/checkpoint writes or consumption
- no N4/N5/N6, no worker

## N4 Readiness
- n4_v4_full_lineage_dry_run_allowed: `true`
