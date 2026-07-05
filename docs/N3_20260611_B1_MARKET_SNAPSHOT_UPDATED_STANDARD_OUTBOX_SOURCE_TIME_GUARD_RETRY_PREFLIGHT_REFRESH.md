# N3 20260611 B1 Standard Outbox Source-Time Guard Retry Preflight Refresh

Result: `PREFLIGHT_REFRESH_PASS`

This runtime-control gate was read-only. It did not execute B1, did not write the database, did not execute rollback SQL, did not consume or update outbox/inbox/checkpoint, did not start a worker, and did not enter N4/N5/N6.

## Closure Proof

- rollback post-review: `POST_REVIEW_PASS`
- source-time future guard post-review: `POST_REVIEW_PASS`
- target `snapshot_run_id`: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

The previous standard-outbox run has been rollback-cleaned, and the source-time future guard is now registered in both contract and preflight.

## Source-Time Guard

- `source_time_future_guard_enabled=true`
- `future_tolerance_seconds=120`
- `future_source_time_handling=P0_BLOCK_NO_OUTBOX`
- mode: `strict_live`

Future same-day source timestamps must not be written as passed `MarketSnapshotUpdated` events.

## Live Baseline

Read-only DB proof: `ashare_v3 / ashare_v3_user / 127.0.0.1:5432`, `transaction_read_only=on`, observed at `2026-06-11T13:57:24.584256+08:00`.

| target | rows |
|---|---:|
| `common_market_data_run` | 0 |
| `common_market_data_quality_item` | 0 |
| stock snapshot | 0 |
| index snapshot | 0 |
| board snapshot | 0 |
| scoped `common_event_outbox` | 0 |
| scoped pending outbox | 0 |
| scoped `common_event_inbox` | 0 |
| scoped checkpoint refs | 0 |

20260611 `MarketSnapshotUpdated` total/pending: `0/0`

Downstream refs:

- N3-B2 stock/index/board refs: `0/0/0`
- N4 trigger run refs: `0`
- N5 action event refs: `0`

## Expected Rows

If executed later after final gate approval:

- stock snapshot: `1890`
- index snapshot: `83`
- board snapshot: `127`
- total snapshot: `2100`
- `MarketSnapshotUpdated` outbox rows: `2100`

## Rollback Proof

Rollback SQL: `sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql`

- hard-fail before first executable delete/update: `true`
- guards event infra: `true`
- guards downstream refs: `true`
- no `DROP/TRUNCATE/CASCADE`

## Decision

Preflight is refreshed to `PREFLIGHT_PASS` with `P0/P1/P2=0/0/0`.

Allowed next gate:

`N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_RETRY_FINAL_GATE_REVIEW`
