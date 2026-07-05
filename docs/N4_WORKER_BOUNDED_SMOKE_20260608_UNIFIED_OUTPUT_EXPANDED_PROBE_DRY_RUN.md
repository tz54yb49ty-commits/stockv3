# N4 Worker Bounded Smoke Expanded Probe Dry Run

Result: `DRY_RUN_PASS`

Generated at: `2026-06-10T08:29:23.262173+08:00`

## Scope

- smoke_run_id: `n4_worker_bounded_smoke_20260608_unified_output_expanded_probe`
- consumer_name: `n4_trigger_worker_v1_bounded_smoke_expanded_probe`
- max_events: `50`

## Source Readiness

- N3 MarketSnapshotUpdated pending: `2155`
- selected source events: `50`
- projection_trace absent: `50/50` as P1 non-blocking warning

## Dry-Run Summary

- TriggerMatched: `0`
- TriggerPendingMarketData: `0`
- TriggerStateChanged: `0`
- No projection join was performed; trigger transition plans remain zero.

## Forbidden Scope

- worker_started=false
- database_write=false
- N3 outbox update=false
- N5/N6=false
