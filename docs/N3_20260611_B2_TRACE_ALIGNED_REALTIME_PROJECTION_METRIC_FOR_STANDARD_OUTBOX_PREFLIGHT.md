# N3 20260611 B2 Trace-Aligned Standard Outbox Preflight

Result: `PREFLIGHT_PASS`

Runner-compatible stage: `N3-B2-realtime-projection-execute-preflight`

## Passed Checks

- Standard B1 snapshot run exists and is passed.
- Standard `MarketSnapshotUpdated` rows: `2100`
- Snapshot/outbox trace join by `payload_json.snapshot_id + identity_key`: `2100/2100`
- Missing `pull_plan_id`: `0`
- Missing `subscription_id`: `0`
- Target B2 scoped baseline is zero:
  - run/quality/stock/index/board projection rows: `0/0/0/0/0`
- Projection time policy is reviewed and runner-compatible.

## Projection Time Policy

B2 now uses `latest_closed_minute=2026-06-11T13:41:00+08:00` to derive `projection_snapshot_time=2026-06-11T13:42:00+08:00` and projection window `20260611_1330_1400`. The source standard outbox observed_at time remains trace-only and the B1 payload is not modified.

## Row Builder Proof

- materialized rows: `2100`
- stock/index/board/total: `1890/83/127/2100`
- ready/not_ready: `283/1817`
- ready by asset stock/index/board: `250/19/14`
- not_ready by asset stock/index/board: `1640/64/113`

## Quality

- P0/P1/P2: `0/1/0`
- P1: source standard outbox already has event infra refs observed read-only (`inbox_refs=4206`, `checkpoint_refs=4206`)

## Rollback

Rollback draft:

```text
sql/N3_20260611_B2_trace_aligned_realtime_projection_metric_for_standard_outbox_rollback.sql
```

It is scoped to the target projection run and defaults to hard-fail before any DELETE/UPDATE.

## Forbidden Scope

This preflight did not execute B2, did not write DB rows, did not consume/update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start workers, and did not modify scheduler.

## Decision

Ready for runtime_control execute final gate review. This preflight does not authorize direct B2 execute.
