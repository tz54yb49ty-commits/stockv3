# N3 Index Route Contamination Supersession And Realtime Chain Repair Closeout

## Result

- result: `CLOSEOUT_PASS`
- decision: `READY_FOR_20260612_MARKET_TIME_AUTOMATIC_N3_TO_N5_FAST_LANE`

## Future Prevention

- SH/SZ index subscriptions now route through `IndexMarketDataAdapter`.
- The adapter uses `mootdx index(symbol, frequency=9)` instead of naked-code stock quotes.
- `identity_route_guard` blocks raw market/code/asset_kind mismatch before snapshot/outbox writes.
- BJ index keeps the Tushare fallback path.
- Stock and board routes remain separate.

Validation:

- realtime snapshot tests: `65 OK`
- chain wrapper tests: `9 OK`

## Historical Supersession

The contaminated 20260611 lineage was superseded, not deleted.

- N3 B1 standard outbox run: `superseded`
- N3 B2 trace-aligned projection run: `superseded`
- N4 production semantic replay run: `superseded`
- N5 action run: `superseded`

Outbox status:

- N3 `MarketSnapshotUpdated`: dead_letter `2100`, pending `0`
- N4 trigger outbox: dead_letter `799`, pending `0`
- N5 action outbox: dead_letter `548`, pending `0`

N4/N5 fact rows are retained as superseded historical evidence.

## Scheduler Strategy

Only one scheduler entrypoint is active:

- label: `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`
- program: `scripts/run_n3_n4_n5_realtime_chain_once.py`
- lineage: `--auto-resolve-lineage`
- interval: `60` seconds
- `KeepAlive=false`
- `RunAtLoad=false`
- current state: loaded, not running between passes
- observed runs: `3`
- latest exit code: `0`

The N4 standalone bounded-polling scheduler remains `not_loaded`.

## Latest 20260612 Observation

The natural scheduler pass generated:

- report: `docs/N3_N4_N5_REALTIME_CHAIN_REPORT_20260612.json`
- result: `NOOP_PASS`
- reason: `no_closed_minute_available`
- database_written: `false`
- N4 executed: `false`
- N5 executed: `false`
- N6 entered: `false`

This is expected before the first eligible closed minute.

Final DB boundary check:

- 20260612 N3 outbox rows: `0`
- 20260612 N4 production runs: `0`
- 20260612 N5 runs: `0`
- contaminated lineage pending outbox remaining: `0`

## Tomorrow Runtime Expectation

Before the first closed minute, the chain should continue returning `NOOP_PASS`.
After the first eligible closed minute, the same scheduler should attempt, in order:

1. N3 B1/C1/B2 facts
2. N3 B1 `MarketSnapshotUpdated` standard outbox
3. N3 trace-aligned B2 realtime projection
4. N4 production semantic matcher
5. N5 bounded action consumer

`MinuteBarClosed` is not a fast-lane blocker. N6, voice, mobile, sim, position, PnL, and real trade remain outside this chain.

## Rollback Registry

- supersession rollback SQL: `sql/N3_N4_N5_20260611_index_route_contamination_supersession_rollback.sql`
- rollback executed: `false`
- hard-fail before first `UPDATE`: `true`

## Forbidden Scope

- old system untouched
- N6 not entered
- delivery/push/voice/mobile untouched
- proposal/order/trade untouched
- sim/position/PnL/real trade untouched
- N4 standalone scheduler not enabled
