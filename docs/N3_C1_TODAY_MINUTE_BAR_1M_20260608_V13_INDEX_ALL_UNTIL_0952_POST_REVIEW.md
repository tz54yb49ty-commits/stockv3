# N3-C1 Today Minute 20260608 v13 Index-All Until 09:52 Post Review

Result: `POST_REVIEW_PASS`

This runtime_control review is read-only. It did not execute N3 commands, rollback SQL, outbox consumption, workers, or any N4/N5/N6 downstream step.

## Lineage

- source_condition_run_id: `condition_layer_20260605_to_20260608_v13_index_all_execute`
- source_subscription_run_id: `market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- source_snapshot_run_id: `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- today_minute_run_id: `today_minute_bar_1m_20260608_until_0952__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- latest_closed_minute: `2026-06-08T09:52:00+08:00`

## Execute Proof

- execute report JSON parse: `PASS`
- status: `passed`
- P0/P1/P2: `0/0/0`
- objects passed/partial/missing/failed: `372/0/0/0`
- C1 writes_outbox: `false`

Live DB row counts:

| table | rows | objects |
| --- | ---: | ---: |
| stock_minute_bar_1m | 7766 | 353 |
| index_minute_bar_1m | 132 | 6 |
| board_minute_bar_1m | 286 | 13 |
| total | 8184 | 372 |

Bar time range for all three physical tables is `2026-06-08 09:31:00+08:00` through `2026-06-08 09:52:00+08:00`.

Duplicate minute key groups:

| asset | duplicate groups |
| --- | ---: |
| stock | 0 |
| index | 0 |
| board | 0 |

## Event Boundary

- C1 outbox rows: `0`
- C1 inbox refs: `0`
- C1 checkpoint refs: `0`
- B1 `MarketSnapshotUpdated` pending outbox rows remain: `2155`
- B1 outbox consumed: `false`

## Downstream Boundary

- N4 trigger refs for B1 snapshot run: `0`
- N4 trigger refs for C1 today-minute run: `0`
- N5 refs: `0`
- N6 refs: `0`
- downstream_layers_touched: `false`
- worker_started: `false`

## Rollback Proof

Rollback SQL: `sql/N3_C1_today_minute_bar_1m_20260608_v13_index_all_until_0952_rollback.sql`

- hard-fail guard before first row-removal SQL: `PASS`
- no `CASCADE` / `DROP` / `TRUNCATE`: `PASS`
- delete scope only:
  - stock/index/board minute rows for this `today_minute_run_id`
  - scoped quality/run rows
- does not delete subscription control rows
- does not delete B1 snapshot or B1 outbox rows
- blocks if event infra, projection, trigger, action, or N6 refs exist

## Decision

N3-C1 today-minute pull can be marked complete.

Recommended next gate:

`N3_REALTIME_PROJECTION_METRIC_READINESS_GATE_FOR_20260608_V13_INDEX_ALL`
