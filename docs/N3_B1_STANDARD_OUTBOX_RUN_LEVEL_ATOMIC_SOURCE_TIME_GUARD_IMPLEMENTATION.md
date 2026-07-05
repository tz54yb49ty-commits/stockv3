# N3 B1 Standard Outbox Run-Level Atomic Source-Time Guard Implementation

- result: `IMPLEMENTATION_PASS`
- layer_role: `N3_market_data`
- gate: `N3_B1_STANDARD_OUTBOX_RUN_LEVEL_ATOMIC_SOURCE_TIME_GUARD_IMPLEMENTATION_GATE`

## Root Cause

The object-level `source_time_future` guard correctly blocked future board source timestamps, but the standard outbox runner wrote stock/index snapshot facts and `MarketSnapshotUpdated` rows before reaching the board objects. This left partial snapshot/outbox/run/quality rows when a later asset failed.

## Implementation

The B1 standard outbox execute path now performs a run-level source-time precheck before inserting `common_market_data_run` or writing snapshot/outbox/quality business rows.

- fetch and prepare stock/index/board snapshot evidence without DB writes
- evaluate source-time and aggregate object blockers across the full run
- if any object is `source_time_future`, date-mismatched, missing, or failed in a standard outbox run, return `BLOCKED` with P0 report evidence
- blocked precheck write policy: `NO_COMMON_MARKET_DATA_RUN_NO_QUALITY_ROWS_NO_SNAPSHOT_ROWS_NO_OUTBOX_ROWS`
- if all objects pass, write the prepared snapshot facts and `MarketSnapshotUpdated` outbox rows on the existing normal path

## Artifact Refresh

- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.md`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.json`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.md`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.json`

## Forbidden Scope

No B1 execute was run in this gate. No database writes, no outbox/inbox/checkpoint mutation, no worker, no N4/N5/N6, and no delivery/push/voice/mobile/proposal/order/trade/sim/position/PnL/real-trade path was touched.

## Validation

- targeted realtime snapshot execute tests: `PASS` (`59` tests)
- focused run-level atomic regression tests: `PASS`
- compileall: `PASS` (`scripts src tests`)
- JSON parse: `PASS`
- forbidden scope scan: `PASS`
- git diff --check: `PASS`
