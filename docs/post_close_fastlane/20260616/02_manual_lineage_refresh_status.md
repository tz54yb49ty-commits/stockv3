# Post-Close Fast Lane Manual Lineage Refresh Status

Result: `EXECUTE_PASS`

Status source: `manual_lineage_refresh_overlay`

This file is an overlay status for `20260615 -> 20260616`. It does not rewrite the original one-shot evidence:

- `docs/post_close_fastlane/20260616/00_status.json`
- `docs/post_close_fastlane/20260616/01_oneshot_execute_report.json`

The original one-shot result remains `EXECUTE_PASS`, but it is superseded for display by this manual lineage refresh overlay.

## Current Effective Lineage

- Source trade date: `20260615`
- For trade date: `20260616`
- Current effective lineage: `v4`
- N1 active financial source: `stock_financial_20260615_v3`
- N2 active condition run: `condition_layer_20260615_source_20260615_for_20260616_v4`
- N3 subscription run: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- N3 A1 preload run: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`

## Boundary

```text
database_written_by_status_refresh=false
n1_n2_n3_executed_by_status_refresh=false
common_event_outbox_inbox_checkpoint_consumed_or_updated=false
n3_b_c_b2_authorized=false
n4_n5_n6_authorized=false
worker_authorized=false
rollback_executed=false
```

## Rollback

No rollback was executed.

- N1 rollback path: `sql/N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql`
- N2 rollback path: `sql/N2_condition_source_refresh_for_stock_financial_20260615_v3_rollback.sql`
- N3 rollback path: `sql/N3_lineage_refresh_for_N2_20260615_v4_rollback.sql`

## UI Caveat

If the 8786 status page only reads `00_status.json`, it may need a small read-side enhancement to prefer `02_manual_lineage_refresh_status.json` when this overlay exists.
