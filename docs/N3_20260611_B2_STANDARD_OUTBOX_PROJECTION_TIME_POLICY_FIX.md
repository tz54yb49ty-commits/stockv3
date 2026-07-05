# N3 20260611 B2 Standard Outbox Projection Time Policy Fix

Result: `FIX_PASS`

## Root Cause

Trace-aligned standard B1 outbox stores observed_at/event_time after the close as snapshot_time. B2 previously used that source time directly as the projection bucket time and rejected `15:34` timestamps as outside trading buckets.

## Policy

- mode: `standard_outbox_observed_at_to_latest_closed_minute`
- bucket time source: `latest_closed_minute`
- latest closed minute: `2026-06-11T13:41:00+08:00`
- projection snapshot time: `2026-06-11T13:42:00+08:00`
- projection window: `20260611_1330_1400`
- source observed_at/snapshot_time remains trace-only
- B1 `MarketSnapshotUpdated` payload mutation: `false`

## Row Builder Proof

Read-only row-builder probe materialized `2100` rows.

- stock/index/board/total: `1890/83/127/2100`
- ready/not_ready: `283/1817`
- ready by asset stock/index/board: `250/19/14`
- not_ready by asset stock/index/board: `1640/64/113`
- sample event id retained: `evt_1b01a3df6009d75046d7c5d20c99737beaf20073`
- sample source snapshot time: `2026-06-11T15:34:16.368292+08:00`
- sample projection snapshot time: `2026-06-11T13:42:00+08:00`

## Contract Impact

- dry-run: `DRY_RUN_PASS`
- contract: `CONTRACT_PASS`
- preflight: `PREFLIGHT_PASS`
- P0/P1/P2: `0/1/0`

The only P1 is that source standard outbox event infra refs were observed read-only; this fix did not consume or update them.

## Forbidden Scope

This gate did not execute B2, did not write DB rows, did not consume/update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start workers, did not execute rollback SQL, and did not modify scheduler.

## Next Gate

`N3_20260611_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_EXECUTE_FINAL_GATE_REVIEW_AFTER_PROJECTION_TIME_POLICY_FIX`
