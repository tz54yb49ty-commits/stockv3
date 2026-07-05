# N3 20260611 B1 MarketSnapshotUpdated Standard Outbox Preflight

- preflight_result: `PREFLIGHT_PASS`
- ready: `true`
- blocked: `false`
- blockers: `[]`
- P0/P1/P2: `0/1/0`
- snapshot_run_id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

## Readiness Summary

- source subscription: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- source subscription status: `passed`
- A1 preload: `previous_day_minute_preload_20260610_for_20260611__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- reference fact-only B1: `realtime_daily_snapshot_20260611_until_1130__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- reference fact-only B1 rows: stock/index/board/total = `1890/83/127/2100`
- reference fact-only B1 wrote outbox: `false`

## Expected Writes If Executed Later

| target | rows |
|---|---:|
| stock snapshot | 1890 |
| index snapshot | 83 |
| board snapshot | 127 |
| total snapshot | 2100 |
| `MarketSnapshotUpdated` outbox | 2100 |

## Source Adapter Plan

| asset | adapter | source_pull_plan_id | objects |
|---|---|---:|---:|
| stock | `StockMarketDataAdapter` | 169 | 1890 |
| index | `IndexMarketDataAdapter` | 166 | 83 |
| board | `BoardMarketDataAdapter` | 163 | 127 |

`MarketSnapshotUpdated` payload trace fields are contract-satisfiable: `subscription_id` comes from persisted subscriptions, `pull_plan_id` comes from `source_adapter_plan[].source_pull_plan_id`, `run_id` is the snapshot run id, `source_adapter` comes from the adapter plan, `data_quality_status` comes from the snapshot quality status, and `snapshot_id` is created by the snapshot upsert before outbox insertion.

## Source Time Policy

- mode: `strict_live`
- source_time_future_guard_enabled: `true`
- future_tolerance_seconds: `120`
- future_source_time_handling: `P0_BLOCK_NO_OUTBOX`
- board_source_time_label_handling: `NORMALIZE_TO_OBSERVED_AT`

Future same-day source timestamps are not retry-ready as passed rows. They must P0-block the object and write no `MarketSnapshotUpdated` event. Board raw period labels follow the reviewed normalization policy below; the raw label remains trace-only.

## Board Source-Time Semantics

Board `mootdx.quotes.index(frequency=9)` `datetime` values are period labels, not trusted realtime update timestamps.

- raw label field: `raw_snapshot_time_label`
- raw label semantics: `tdx_index_frequency_9_period_label`
- observed fields: `observed_at`, `fetched_at`
- trusted source time field: none
- default handling: `NORMALIZE_TO_OBSERVED_AT`
- normalize to observed_at: `true`
- event time policy: `observed_at_for_board_untrusted_period_label`
- quality gate: `n3_b1_board_source_time_label_normalized`

Therefore a board raw label such as `15:00` before 15:00 is retry-ready only under the explicit reviewed normalization policy: event time uses `observed_at`/`fetched_at`, the raw label remains trace-only, and quality exposes `board_source_time_label_normalized`.

Required board payload/trace fields:

- `raw_snapshot_time_label`
- `raw_snapshot_time_semantics`
- `source_time_trust_level`
- `observed_at`
- `fetched_at`
- `normalized_event_time_reason`

## Run-Level Atomic Precheck

The refreshed runner contract requires a run-level source-time precheck before any DB write in the standard outbox path.

- enabled: `true`
- scope: all stock/index/board realtime snapshot subscriptions
- block_on_any_source_time_future: `true`
- block_on_any_p0_aggregate_object_issue: `true`
- blocked result: `BLOCKED`
- blocked write policy: `NO_COMMON_MARKET_DATA_RUN_NO_QUALITY_ROWS_NO_SNAPSHOT_ROWS_NO_OUTBOX_ROWS`

If the precheck blocks, the target scoped baseline must remain zero for `common_market_data_run`, `common_market_data_quality_item`, stock/index/board snapshot rows, and `common_event_outbox`.

## Baseline

Rollback post-review is `POST_REVIEW_PASS`, source-time future guard post-review is `POST_REVIEW_PASS`, board source-time semantics post-review is `POST_REVIEW_PASS`, and the target scoped baseline is clean for retry. Live evidence from a read-only transaction at `2026-06-11T15:21:12.434884+08:00` shows:

| target | actual rows |
|---|---:|
| `common_market_data_run` | 0 |
| `common_market_data_quality_item` | 0 |
| stock snapshot | 0 |
| index snapshot | 0 |
| board snapshot | 0 |
| scoped `common_event_outbox` | 0 |
| scoped `common_event_inbox` | 0 |
| scoped checkpoint refs | 0 |
| N4/N5/N6 refs | 0 |

Existing 20260611 `MarketSnapshotUpdated` total/pending remains `0/0`. The previous future `event_time=15:00` run has been rollback-cleaned. The source-time future guard, board source-time semantics fix, and reviewed observed-at normalization route are registered in contract and preflight.

Rollback and guard artifacts:

```text
docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_ROLLBACK_POST_REVIEW.json
docs/N3_B1_REALTIME_SNAPSHOT_SOURCE_TIME_FUTURE_GUARD_POST_REVIEW.json
docs/N3_B1_BOARD_SOURCE_TIME_SEMANTICS_AND_EVENT_TIME_POLICY_FIX_POST_REVIEW.json
docs/N3_20260611_B1_BOARD_MARKET_SNAPSHOT_UPDATED_EVENT_ROUTE_DECISION.json
```

## Rollback

- path: `sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql`
- default hard-fail before first executable delete/update: yes
- snapshot table scoped key: `run_id`
- quality item scoped key: `run_id`
- guards: event infra, N3-B/C/B2 refs, N4/N5/N6 refs, downstream flags, worker flags
- delete scope: only this snapshot run's pending/failed/dead-letter `MarketSnapshotUpdated` outbox rows, snapshot rows, quality rows, and run row

## Quality

- P0/P1/P2: `0/1/0`
- P1: `board_source_time_label_normalized`, expected board count `127`.

## Forbidden Scope

No B1 execute happened in this gate. No DB writes, no market pull, no outbox/inbox/checkpoint mutation, no N4/N5/N6, no worker, no delivery/push/voice/mobile, no proposal/order/trade, no sim/position/PnL/real trade, and no old-system touch.
