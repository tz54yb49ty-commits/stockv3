# N3 20260611 B1 MarketSnapshotUpdated Future Event Time Decision

Result: `DECISION_PASS`

This runtime-control gate was read-only. It did not execute rollback SQL, did not modify DB rows, did not consume or update outbox/inbox/checkpoint, did not start a worker, and did not enter N4/N5/N6.

## Target

- `for_trade_date=20260611`
- `snapshot_run_id=realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- DB proof: `ashare_v3 / ashare_v3_user / 127.0.0.1:5432`
- read-only transaction: `on`
- DB observation time: `2026-06-11T13:26:47.201816+08:00`

## Future Event-Time Proof

The B1 standard outbox run is `passed` with `P0/P1/P2=0/0/0`, but board events carry a future event time.

| asset_kind | outbox rows | pending | min event_time | max event_time | event_time > now | event_time > created_at + 5m |
|---|---:|---:|---|---|---:|---:|
| board | 127 | 127 | 2026-06-11T15:00:00+08:00 | 2026-06-11T15:00:00+08:00 | 127 | 127 |
| index | 83 | 83 | 2026-06-11T13:11:13.650909+08:00 | 2026-06-11T13:11:18.961917+08:00 | 0 | 0 |
| stock | 1890 | 1890 | 2026-06-11T13:11:19.025517+08:00 | 2026-06-11T13:13:11.420986+08:00 | 0 | 0 |

Sample affected event:

- `asset_kind=board`
- `identity_key=board:TDX:881478`
- `event_time=2026-06-11T15:00:00+08:00`
- `created_at=2026-06-11T13:11:13.644276+08:00`
- `status=pending`
- `source_adapter=BoardMarketDataAdapter`
- `data_quality_status=passed`
- `snapshot_id=7950`
- `pull_plan_id=163`

## Snapshot Fact Proof

The future timestamp is also present in the board snapshot facts, not only the outbox.

| asset_kind | snapshot rows | min snapshot_time | max snapshot_time | snapshot_time > now | snapshot_time > created_at + 5m |
|---|---:|---|---|---:|---:|
| board | 127 | 2026-06-11T15:00:00+08:00 | 2026-06-11T15:00:00+08:00 | 127 | 127 |
| index | 83 | 2026-06-11T13:11:13.650909+08:00 | 2026-06-11T13:11:18.961917+08:00 | 0 | 0 |
| stock | 1890 | 2026-06-11T13:11:19.025517+08:00 | 2026-06-11T13:13:11.420986+08:00 | 0 | 0 |

Sample board snapshot:

- `identity_key=board:TDX:881478`
- `snapshot_id=7950`
- `snapshot_time=2026-06-11T15:00:00+08:00`
- `created_at=2026-06-11T13:11:13.627809+08:00`
- `source_adapter=BoardMarketDataAdapter`
- `quality_status=passed`
- `raw_json.source_snapshot_time=2026-06-11T15:00:00+08:00`
- `raw_payload.snapshot_time=2026-06-11T15:00:00+08:00`

## Affected Scope

Only `board` is affected in this proof:

- board affected rows: `127`
- stock future rows: `0`
- index future rows: `0`

Root cause hypothesis:

- `src/ashare_v3/market/realtime_snapshot_execute.py::build_snapshot_source_time_evidence` marks a source time as confirmed when its trade date equals `for_trade_date`.
- It does not currently block a source timestamp later than execution/current time.
- `src/ashare_v3/market/fact_writer.py::write_market_snapshot_with_event` writes `snapshot_time` directly as `MarketSnapshotUpdated.event_time`.

## Consumption Safety Decision

Decision: `BLOCK_N4_CONSUMPTION`

Reason: there are still `127` pending board `MarketSnapshotUpdated` rows with future `event_time` and `data_quality_status=passed`. N4 bounded smoke must not consume this batch.

Current consumption/downstream refs:

- outbox total/pending: `2100/2100`
- delivered/delivering outbox: `0`
- inbox refs: `0`
- checkpoint refs: `0`
- B2 projection refs stock/index/board: `0/0/0`
- N4 trigger run refs: `0`
- N5 action event refs: `0`
- N6/user/sim/virtual refs: `0`

## Rollback Safety

Rollback SQL: `sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql`

Static proof:

- hard-fail before first `DELETE/UPDATE`: `true`
- guards event infra: `true`
- guards N3-B2/N4/N5/N6/user/sim/virtual refs: `true`
- no `DROP/TRUNCATE/CASCADE`

Rollback scope:

- scoped `MarketSnapshotUpdated` outbox rows
- scoped stock/index/board realtime snapshot rows by `run_id`
- scoped `common_market_data_quality_item`
- scoped `common_market_data_run`

## Recommended Decision

Recommended decision: `ROLLBACK_THEN_FIX_SOURCE_TIME_GUARD`

Rationale:

- The event ledger is a cross-layer protocol; N4 should not partially consume a mixed-validity event batch.
- The bad board rows are still pending and unconsumed, so scoped rollback is still available.
- In-place repair would mutate already-written snapshot facts and outbox rows. A scoped rollback plus source-time guard fix and clean rerun is safer and more auditable.

Required N3 policy before rerun:

- source time must match `for_trade_date`
- source time must not exceed execution/current time plus reviewed tolerance
- future source time must produce P0 BLOCK or quality failed without passed `MarketSnapshotUpdated`
- policy applies to stock/index/board

## Forbidden Scope Proof

- rollback executed: `false`
- database written by this gate: `false`
- outbox consumed or updated: `false`
- inbox/checkpoint consumed or updated: `false`
- worker started: `false`
- N4/N5/N6 entered: `false`
- delivery/push/voice/mobile touched: `false`
- proposal/order/trade/sim/position/PnL/real trade touched: `false`
- old system touched: `false`

## Next Gate

`N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_ROLLBACK_FINAL_GATE_REVIEW`
