# N3-EOD Snapshot Refresh Contract

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- stage: `N3-EOD snapshot refresh contract design`
- eod_run_id: `eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- positioning: `settlement fact / official close confirmation`
- execute_authorized: `false`
- writes_outbox: `false`
- consumes_c3_outbox: `false`
- supersedes_b1_b2_n4_n5: `false`
- starts_worker: `false`

EOD is a settlement and official-close confirmation substage. It is not a C2/C3
replay replacement, does not auto-correct B1/B2/N4/N5, and does not consume C3
outbox. Any stale or replay decision remains a separate total-control gate.

## Source Lineage

EOD v1 is allowed to read only this explicit lineage:

```text
source_condition_run_id =
condition_layer_20260522_to_20260525_20260525102249_execute

source_subscription_run_id =
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_b1_snapshot_run_id =
realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_c2_run_id =
closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_c2b_run_id =
closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_c3_run_id =
minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_n4_replay_audit_run_id =
trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b
```

`official_daily_run_id` is nullable in schema because N1 official daily close may
not exist at dry-run time. EOD dry-run must report `missing_official_daily_fact`
instead of pulling行情 or fixing N1. EOD execute in official-confirm mode must be
blocked until the N1 official daily ingestion gate produces an accepted source.

## Architecture

Recommended storage is independent EOD facts:

```text
stock_eod_snapshot
index_eod_snapshot
board_eod_snapshot

stock_eod_reconciliation_item
index_eod_reconciliation_item
board_eod_reconciliation_item
```

Do not reuse `stock/index/board_realtime_daily_snapshot`; B1 is a realtime
snapshot fact, while EOD is a settlement confirmation fact.

## EOD Snapshot Contract

Expected snapshot grain:

```text
asset_kind + identity_key + trade_date + eod_run_id
```

Expected rows from current subscription objects:

```text
stock=2052
index=9
board=127
total=2188
```

EOD snapshot facts should combine N3 runtime close material with official daily
fields when available:

```text
open / high / low / close / volume / amount
official_close_price / official_volume / official_amount
eod_source_status
settlement_quality_status
stale_candidate
raw_json
```

`stale_candidate=true` is evidence only. It must not mutate B1/B2/C2/C2B/C3/N4/N5
state and must not trigger replay.

## Reconciliation Contract

Reconciliation items are audit evidence, not commands. They may record:

```text
official_daily_missing
official_price_diff
official_volume_diff
official_amount_diff
b1_snapshot_diff
c2_closed_summary_diff
c2b_signal_enrichment_diff
c3_outbox_status
n4_replay_audit_diff
stale_candidate
boundary_check
```

Each item stores expected/actual JSON and trace JSON. `diff_severity=P0/P1/P2`
means review severity inside EOD only; it does not authorize downstream changes.

## Future Execute Writes

Future EOD execute may write only:

```text
common_market_data_run
common_market_data_quality_item
stock/index/board_eod_snapshot
stock/index/board_eod_reconciliation_item
```

## Forbidden Writes

Future EOD execute must not write or update:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
stock/index/board_realtime_projection_metric
stock/index/board_realtime_daily_snapshot
stock/index/board_closed_30m_summary
stock/index/board_closed_30m_signal_enrichment
stock/index/board_minute_bar_1m
C3 outbox
condition tables
trigger tables
action tables
user tables
voice/mobile/sim/position tables
external archive / Parquet
old system
worker / scheduler state
```

## Quality Gates

P0 examples:

```text
source lineage mismatch
required source run not passed
019 schema missing
eod_run_id already exists
EOD scoped rows already exist
common_event_outbox/inbox/checkpoint rows for eod_run_id
C3 outbox delivered or consumed unexpectedly
official daily source run absent when official-confirm execute is requested
duplicate EOD snapshot key
forbidden write scope detected
```

P1 examples:

```text
official daily exists but individual object official row is missing
official close/volume/amount differs from N3 runtime close material
BJ 920xxx remains missing in settlement evidence
N4 C3 audit reports missing comparison rows
```

P2 examples:

```text
minor rounding tolerance review
manual stale review recommended
```

## Rollback

Business rollback is scoped by `eod_run_id` and deletes only:

```text
stock/index/board_eod_reconciliation_item
stock/index/board_eod_snapshot
common_market_data_quality_item
common_market_data_run
```

Rollback must block if any `common_event_outbox`, `common_event_inbox`, or
`common_event_consumer_checkpoint` row references `eod_run_id`.

## Decision

`DESIGN_PASS`. 019 migration review is allowed. EOD business execute remains
blocked until schema migration review/execute, dry-run runner, preflight, and
explicit final gate.
