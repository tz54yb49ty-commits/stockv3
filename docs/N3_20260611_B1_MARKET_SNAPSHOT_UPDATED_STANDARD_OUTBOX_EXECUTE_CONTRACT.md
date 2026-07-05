# N3 20260611 B1 MarketSnapshotUpdated Standard Outbox Execute Contract

- contract_result: `CONTRACT_PASS`
- stage: `N3-B1-preflight`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- snapshot_run_id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- for_trade_date: `20260611`
- writes_outbox: `true`

## Expected Rows

| asset | objects | snapshot rows |
|---|---:|---:|
| stock | 1890 | 1890 |
| index | 83 | 83 |
| board | 127 | 127 |
| total | 2100 | 2100 |

Expected `MarketSnapshotUpdated`: `2100`.

## Source Adapter Plan

| asset | adapter | source_pull_plan_id | objects |
|---|---|---:|---:|
| stock | `StockMarketDataAdapter` | 169 | 1890 |
| index | `IndexMarketDataAdapter` | 166 | 83 |
| board | `BoardMarketDataAdapter` | 163 | 127 |

The B1 execute runner maps `pull_plan_id` into each snapshot fact and `MarketSnapshotUpdated.payload_json` from `source_adapter_plan[].source_pull_plan_id` by asset kind. This contract now covers stock/index/board with non-empty pull plan IDs.

## Source Time Policy

- mode: `strict_live`
- source_time_future_guard_enabled: `true`
- future_tolerance_seconds: `120`
- future_source_time_handling: `P0_BLOCK_NO_OUTBOX`
- board_source_time_label_handling: `NORMALIZE_TO_OBSERVED_AT`

`source_time` must match `for_trade_date` and must not be later than execution/current time plus the reviewed tolerance. A future source timestamp must fail the object as P0 and must not write a passed snapshot or `MarketSnapshotUpdated` outbox row.

## Board Source-Time Semantics

`BoardMarketDataAdapter` reads board snapshots through `mootdx.quotes.index(frequency=9)`. The returned `datetime` is treated as a TDX period label, not a trusted realtime update timestamp.

- raw label field: `raw_snapshot_time_label`
- raw label semantics: `tdx_index_frequency_9_period_label`
- observed fields: `observed_at`, `fetched_at`
- trusted source time field: none
- default handling: `NORMALIZE_TO_OBSERVED_AT`
- normalize to observed_at: `true`
- event time policy: `observed_at_for_board_untrusted_period_label`
- quality gate: `n3_b1_board_source_time_label_normalized`

With the reviewed normalization policy, a board raw label such as `15:00` remains trace-only. The B1 event time uses N3 `observed_at`/`fetched_at`, and the row is quality-visible as `board_source_time_label_normalized`. The raw label must not become `MarketSnapshotUpdated.event_time`.

## Run-Level Atomic Precheck

Standard outbox B1 execute must complete source-time evidence evaluation for all stock/index/board subscriptions before inserting `common_market_data_run` or writing any snapshot/outbox/quality business rows.

- enabled: `true`
- scope: all stock/index/board realtime snapshot subscriptions
- block_on_any_source_time_future: `true`
- block_on_any_p0_aggregate_object_issue: `true`
- blocked result: `BLOCKED`
- blocked write policy: `NO_COMMON_MARKET_DATA_RUN_NO_QUALITY_ROWS_NO_SNAPSHOT_ROWS_NO_OUTBOX_ROWS`
- future_source_time_handling: `P0_BLOCK_NO_DB_WRITE_NO_OUTBOX`

If any object fails this precheck, the runner may write only file-based report evidence and must leave scoped run/quality/snapshot/outbox rows at zero.

## Event Contract

Only `MarketSnapshotUpdated` is allowed for this run. `MarketDataDelayed`, `MarketDataMissing`, and `MarketDisplaySnapshotUpdated` are explicitly forbidden. Source issue rows must block or fail the run without emitting non-snapshot outbox events.

Each successful snapshot fact write must have a same-transaction `MarketSnapshotUpdated` outbox row.

Required payload trace fields are satisfiable:

- `subscription_id`: each persisted subscription row.
- `pull_plan_id`: `source_adapter_plan[].source_pull_plan_id`.
- `run_id`: `snapshot_run_id`.
- `source_adapter`: `source_adapter_plan[].adapter_name`.
- `data_quality_status`: snapshot fact quality status.
- `snapshot_id`: snapshot fact upsert result before outbox creation.
- `raw_snapshot_time_label`: board raw period label trace.
- `raw_snapshot_time_semantics`: `tdx_index_frequency_9_period_label`.
- `source_time_trust_level`: `untrusted_period_label`.
- `observed_at`: N3 observed time and board event-time source under reviewed normalization.
- `fetched_at`: adapter fetch time trace.
- `normalized_event_time_reason`: reviewed reason for using `observed_at`.

## Allowed Writes

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_realtime_daily_snapshot`
- `index_realtime_daily_snapshot`
- `board_realtime_daily_snapshot`
- `common_event_outbox`

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_realtime_daily_snapshot_once.py \
  --contract-path docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.json \
  --readiness-path docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.json \
  --for-trade-date 20260611 \
  --snapshot-run-id realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1 \
  --execute \
  --user-confirmed \
  --writes-outbox=true \
  --json-report-path docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_REPORT.json \
  --markdown-report-path docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_REPORT.md
```

Do not pass `--no-outbox`.

Required CLI compatibility proof:

- `--readiness-path docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.json`
- `--for-trade-date 20260611`
- `--snapshot-run-id realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- `--writes-outbox=true`

## Rollback

Rollback SQL: `sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql`

Rollback has a default hard-fail before executable delete/update and guards delivered outbox rows, inbox/checkpoint refs, N3-B/C/B2 refs, N4/N5/N6 refs, `downstream_layers_touched`, and `worker_started`.

Snapshot table delete scope is by `run_id` only. Delete scope is limited to this snapshot run's pending/failed/dead-letter `MarketSnapshotUpdated` outbox rows, realtime snapshot rows, quality rows, and run row.

`common_market_data_quality_item` delete scope is also by `run_id` only; the table does not have `source_run_id`.

## Quality

- P0/P1/P2: `0/1/0`
- P1: `board_source_time_label_normalized`, expected board count `127`.
- Live DB baseline refresh completed by observed-at normalization contract/preflight gate.
