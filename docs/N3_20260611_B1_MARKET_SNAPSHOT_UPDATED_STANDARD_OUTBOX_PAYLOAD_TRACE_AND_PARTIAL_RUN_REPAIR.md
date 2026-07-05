# N3 20260611 B1 MarketSnapshotUpdated Standard Outbox Payload Trace And Partial Run Repair

- repair_result: `REPAIR_PASS`
- layer_role: `N3_market_data`
- snapshot_run_id: `realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- source subscription: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`

## Root Cause

The blocked execute failed because `MarketSnapshotUpdated.payload_json.pull_plan_id` was missing. The B1 runner maps `pull_plan_id` from `contract.source_adapter_plan[].source_pull_plan_id` by `asset_kind`, but the standard outbox execute contract did not include `source_adapter_plan`.

## Contract Trace Repair

| asset | adapter | source_pull_plan_id | object_count |
|---|---|---:|---:|
| stock | `StockMarketDataAdapter` | 169 | 1890 |
| index | `IndexMarketDataAdapter` | 166 | 83 |
| board | `BoardMarketDataAdapter` | 163 | 127 |

`MarketSnapshotUpdated` required trace fields are now contract-satisfiable:

- `subscription_id`: persisted subscription row.
- `pull_plan_id`: `source_adapter_plan[].source_pull_plan_id`.
- `run_id`: target `snapshot_run_id`.
- `source_adapter`: `source_adapter_plan[].adapter_name`.
- `data_quality_status`: snapshot fact quality status.
- `snapshot_id`: snapshot fact upsert result before outbox insert.

## Partial Run Cleanup

The blocked attempt left exactly one scoped `common_market_data_run` row with `status=running`, and no scoped snapshot/outbox/quality rows. Cleanup SQL:

```text
sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_partial_run_cleanup.sql
```

Cleanup SQL hard-fails before delete unless all of the following remain true:

- target run row is exactly one safe `running` row;
- `market_data_pulled=false`;
- `market_data_fact_written=false`;
- `downstream_layers_touched=false`;
- `worker_started=false`;
- stock/index/board snapshot rows are zero;
- quality/outbox/inbox/checkpoint refs are zero;
- N3-B/C/B2, N4/N5/N6, user/sim/virtual refs are zero.

Delete scope is only the target `common_market_data_run` row. It does not delete snapshot facts, quality rows, outbox/inbox/checkpoint rows, existing fact-only B1/C1/B2 runs, N2 facts, or N4/N5/N6 facts.

## Retry Policy

Direct execute retry is not allowed from this artifact state. The correct route is:

1. runtime_control reviews the cleanup SQL final gate;
2. N3 executes only the scoped partial-run cleanup if approved;
3. N3 refreshes B1 standard outbox preflight and baseline;
4. runtime_control reviews the execute retry final gate.

## Forbidden Scope

This repair gate did not execute B1, did not write snapshot/outbox rows, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, did not start a worker, and did not touch old-system or trade paths.
