# N3 B1 Realtime Snapshot Source Time Future Guard Implementation

## Result

IMPLEMENTATION_PASS

## Scope

Layer role: N3_market_data.

This gate implements a source_time future guard for N3 B1 realtime snapshot execution only. It does not execute B1, does not write database rows, does not consume or update event infra, and does not enter N4/N5/N6.

## Root Cause

The 20260611 B1 standard outbox attempt was rolled back after `BoardMarketDataAdapter` returned board snapshots with `snapshot_time=2026-06-11T15:00:00+08:00` while the run executed around 13:11 Asia/Shanghai.

Before this implementation, `build_snapshot_source_time_evidence` only verified that the source timestamp trade date matched `for_trade_date`. A future same-day timestamp could therefore be marked `source_time_confirmed`. The B1 writer then used `snapshot_time` as `MarketSnapshotUpdated.event_time`, which produced future-dated pending outbox events.

## Behavior

The B1 source time evidence now applies the following checks:

1. `source_time` must still match `for_trade_date`.
2. Date mismatch remains a hard failure and takes precedence.
3. If the date matches, `source_time` must be less than or equal to execution/default/current time plus the reviewed tolerance.
4. Default tolerance is 120 seconds.
5. Contract override is read from `source_time_policy.future_tolerance_seconds`.
6. The guard is enabled by default through `source_time_policy.source_time_future_guard_enabled=true`.

When the guard detects a future source timestamp:

- `source_time_status=source_time_future`
- `source_time_confirmed` is not emitted
- object status is `failed`
- object quality severity is `P0`
- no snapshot fact row is written for the object
- no `MarketSnapshotUpdated` outbox row is written for the object

Missing/pre-open source time behavior remains unchanged. Within-tolerance same-day source time remains allowed.

## Contract Policy

Generated B1 execute contracts now carry:

```json
{
  "source_time_future_guard_enabled": true,
  "future_tolerance_seconds": 120,
  "future_source_time_handling": "P0_BLOCK_NO_OUTBOX"
}
```

The policy is present for both strict live and pre-open fact-only modes.

## Modified Files

- `src/ashare_v3/market/realtime_snapshot_execute.py`
- `src/ashare_v3/market/realtime_snapshot_execute_contract.py`
- `tests/test_market_data_realtime_snapshot_execute.py`
- `tests/test_market_data_realtime_snapshot_execute_contract.py`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.md`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.json`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.md`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.json`
- `docs/N3_B1_REALTIME_SNAPSHOT_SOURCE_TIME_FUTURE_GUARD_IMPLEMENTATION.md`
- `docs/N3_B1_REALTIME_SNAPSHOT_SOURCE_TIME_FUTURE_GUARD_IMPLEMENTATION.json`

## Test Coverage

Added/updated coverage for:

- board raw `snapshot_time=15:00` with execution time `13:11` blocks as P0 and writes no outbox
- source time within 120 seconds tolerance remains confirmed
- source time date mismatch still blocks before the future guard
- missing/pre-open source time policy is not misclassified as future
- standard outbox path cannot write a future `MarketSnapshotUpdated.event_time` when the object is blocked
- generated contract carries future guard policy fields

Validation commands passed:

- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_market_data_realtime_snapshot_execute*.py'`
- `python3 -m compileall scripts src tests`
- `python3 -m json.tool docs/N3_B1_REALTIME_SNAPSHOT_SOURCE_TIME_FUTURE_GUARD_IMPLEMENTATION.json`
- scoped `git diff --check`
- full `git diff --check`

## Forbidden Scope

This implementation did not:

- execute B1
- write database rows
- consume or update `common_event_outbox`, `common_event_inbox`, or `common_event_consumer_checkpoint`
- start worker processes
- enter N4/N5/N6
- touch delivery, push, voice, mobile, proposal, order, trade, sim, position, PnL, real trade, or the old system

## Next Gate

Allowed next review gate:

`N3_B1_REALTIME_SNAPSHOT_SOURCE_TIME_FUTURE_GUARD_POST_REVIEW_GATE`
