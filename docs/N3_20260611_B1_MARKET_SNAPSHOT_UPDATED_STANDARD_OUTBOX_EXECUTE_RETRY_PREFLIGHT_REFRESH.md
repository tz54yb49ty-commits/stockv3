# N3 20260611 B1 MarketSnapshotUpdated Standard Outbox Execute Retry Preflight Refresh

- result: `PREFLIGHT_REFRESH_PASS`
- layer_role: `N3_market_data`
- snapshot_run_id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- for_trade_date: `20260611`
- source subscription: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

## Cleanup Closure

Cleanup post-review registration is `POST_REVIEW_PASS`.

```text
docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PARTIAL_RUN_CLEANUP_POST_REVIEW_REGISTRATION.json
```

The partial running `common_market_data_run` row was removed by the scoped cleanup; no snapshot, quality, outbox, inbox, checkpoint, N4, N5, or N6 rows were deleted or updated.

## Live Baseline

| target | rows |
|---|---:|
| `common_market_data_run` | 0 |
| `common_market_data_quality_item` | 0 |
| stock snapshot | 0 |
| index snapshot | 0 |
| board snapshot | 0 |
| scoped outbox | 0 |
| scoped outbox pending | 0 |
| scoped inbox | 0 |
| scoped checkpoint refs | 0 |
| global 20260611 `MarketSnapshotUpdated` total/pending | 0/0 |
| B2 projection refs stock/index/board | 0/0/0 |
| N4/N5 direct refs | 0 |

## Source Adapter Plan

| asset | adapter | source_pull_plan_id | objects |
|---|---|---:|---:|
| stock | `StockMarketDataAdapter` | 169 | 1890 |
| index | `IndexMarketDataAdapter` | 166 | 83 |
| board | `BoardMarketDataAdapter` | 163 | 127 |

This satisfies `MarketSnapshotUpdated` payload trace requirements for `subscription_id`, `pull_plan_id`, `run_id`, `source_adapter`, `data_quality_status`, and `snapshot_id`.

## Expected Rows

| target | rows |
|---|---:|
| stock snapshot | 1890 |
| index snapshot | 83 |
| board snapshot | 127 |
| total snapshot | 2100 |
| `MarketSnapshotUpdated` outbox | 2100 |

## Rollback

Rollback SQL:

```text
sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql
```

The rollback SQL hard-fails before executable delete/update, uses `run_id` for snapshot and quality scopes, guards event infra, N3-B/C/B2 refs, N4/N5/N6 refs, downstream flags and worker flags, and contains no `DROP`, `TRUNCATE`, or `CASCADE`.

## Forbidden Scope

This refresh did not execute B1, did not write snapshot/outbox rows, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start a worker, and did not touch old-system or trade paths.

## Decision

The target is retry-ready for runtime_control B1 standard outbox execute retry final gate review.
