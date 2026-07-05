# N3 20260611 B1 MarketSnapshotUpdated Standard Outbox Dry Run

- result: `DRY_RUN_PASS`
- layer_role: `N3_market_data`
- for_trade_date: `20260611`
- source_condition_run_id: `condition_layer_20260610_source_20260610_for_20260611_v1`
- source_subscription_run_id: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- target_snapshot_run_id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

## Route

Selected route: B1 standard outbox snapshot refresh with reviewed observed-at board normalization.

Rejected routes:

- event repair
- outbox backfill from existing fact-only B1 rows
- modifying existing fact-only B1/C1/B2 runs

N4 bounded smoke requires a pending N3 standard `MarketSnapshotUpdated` outbox input. Existing 20260611 B1 runs were fact-only and wrote zero outbox rows, so this gate plans a new scoped B1 run.

Board `mootdx.quotes.index(frequency=9)` `datetime` is an untrusted period label. The reviewed route uses `observed_at`/`fetched_at` as board event time, keeps raw `15:00` as trace only, and exposes `board_source_time_label_normalized` as quality-visible evidence.

## Expected Rows

| asset | objects | snapshot rows | adapter |
|---|---:|---:|---|
| stock | 1890 | 1890 | `StockMarketDataAdapter` |
| index | 83 | 83 | `IndexMarketDataAdapter` |
| board | 127 | 127 | `BoardMarketDataAdapter` |
| total | 2100 | 2100 | |

Expected `MarketSnapshotUpdated` rows: `2100`.

## Event Contract

- `writes_outbox=true`
- required/generated event type: `MarketSnapshotUpdated`
- forbidden event types: `MarketDataDelayed`, `MarketDataMissing`, `MarketDisplaySnapshotUpdated`
- `event_outbox_rows_written` must equal successful snapshot fact rows
- source missing/delayed/error must block or fail this run, not create non-snapshot outbox rows

Required board payload/trace fields:

- `raw_snapshot_time_label`
- `raw_snapshot_time_semantics`
- `source_time_trust_level`
- `observed_at`
- `fetched_at`
- `normalized_event_time_reason`

## Planned Future Writes

Allowed tables only:

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_realtime_daily_snapshot`
- `index_realtime_daily_snapshot`
- `board_realtime_daily_snapshot`
- `common_event_outbox`

## Baseline Note

Live read-only evidence at `2026-06-11T15:21:12.434884+08:00` says target run/quality/snapshot/outbox rows are all `0`, scoped inbox/checkpoint refs are `0/0`, N4/N5/N6 refs are `0`, and current 20260611 `MarketSnapshotUpdated` total/pending remains `0/0`. The latest reference B1 run wrote `2100` snapshot rows with `writes_outbox=false`.

## Quality

- P0/P1/P2: `0/1/0`
- P1: `board_source_time_label_normalized`, expected board count `127`

## Forbidden Scope

This gate did not execute B1, did not write DB, did not pull market data, did not write/consume/update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start workers, and did not touch delivery, push, voice, mobile, proposal, order, trade, sim, position, PnL, real trading, or the old system.
