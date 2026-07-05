# N3-EOD Snapshot Refresh Execute Contract

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- runner_exists: `true`
- runner_readiness: `ready`
- execute_authorized: `false`
- eod_execute_allowed_now: `false`
- eod_execute_allowed_reason: `awaiting_final_gate_user_confirmation`
- eod_run_id: `eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`

## Run Metadata

`common_market_data_run` uses:

- source_trade_date: `20260525`
- prev_trade_date: `20260525`
- market_data_pulled: `false`
- market_data_fact_written: `true`
- downstream_layers_touched: `false`
- worker_started: `false`

Previous-day provenance remains in lineage and raw JSON trace, not in `prev_trade_date`.

## Allowed Writes

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_eod_snapshot`
- `index_eod_snapshot`
- `board_eod_snapshot`
- `stock_eod_reconciliation_item`
- `index_eod_reconciliation_item`
- `board_eod_reconciliation_item`

## Forbidden

- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- realtime snapshot / projection
- closed summary / closed signal enrichment
- minute bars
- N4/N5/N6
- worker
- voice / mobile / sim / position / real trade

## Quality

Official daily coverage must be complete: `stock=2052 index=9 board=127 total=2188 missing=0`.

C2 missing summaries `72` and N4 replay audit missing `18` are P1 reconciliation warnings only. They do not block EOD execute and do not mutate prior runtime.

## Rollback

Use `sql/N3_EOD_snapshot_business_rollback.sql`. Rollback deletes only EOD snapshot rows, EOD reconciliation rows, quality rows, and the EOD run row by `eod_run_id`. It includes guards for outbox, inbox, and checkpoint references.
