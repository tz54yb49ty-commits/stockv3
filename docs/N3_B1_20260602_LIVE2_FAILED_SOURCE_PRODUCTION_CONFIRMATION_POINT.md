# N3-B1 20260602 live2 Failed Source Production Confirmation Point

## Status

- status: WAIT_USER_CONFIRMATION_FOR_PRODUCTION_ROLLBACK_RETRY
- failed_snapshot_run_id: `realtime_snapshot_20260602_live2_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`
- rollback_sql: `sql/N3_B1_realtime_snapshot_20260602_live2_outbox_rollback.sql`

## Current Evidence

```text
common_market_data_run.status = failed
P0 = 2
snapshot rows = stock 1976 / index 81 / board 428 / total 2485
outbox pending MarketSnapshotUpdated = 2485
inbox refs = 0
checkpoint refs = 0
N4 trigger refs = 0
```

Root cause: TUSHARE_TOKEN was not visible to the execute shell, so BJ index fallback failed for `index:BJ:899050` and `index:BJ:899601`.

## Mock Chain Result

```text
N3-B2 mock = DRY_RUN_PASS, production blocked by failed B1 source
N4 strict mock = DRY_RUN_PASS, 969 TriggerPendingMarketData / 0 TriggerMatched
N5 synthetic sample = passed, P0/P1/P2 = 0/0/1
```

Artifacts:

- `docs/N3_B2_20260602_mock_from_failed_live2_dry_run.json`
- `docs/N4_20260602_mock_projection_matcher_dry_run_report.json`
- `docs/N5_20260602_synthetic_action_preflight_dry_run_report.json`

## Production Route After Confirmation

1. Roll back failed B1 live2 source rows/outbox using `sql/N3_B1_realtime_snapshot_20260602_live2_outbox_rollback.sql`.
2. Source `/Users/chuanfuchen/.secrets/ashare_v3_tushare.env` without printing token.
3. Rebuild and execute a new B1 live outbox run, preferably `live3`.
4. Generate B2 projection contract/preflight from passed B1 live3 and C1 today minute.
5. Continue N4 context localization / projection matcher and N5 action gates.

## Boundary

No production rollback or retry was executed in this report. No worker, N6, old system, or real trading.
