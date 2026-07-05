# N3-C2B Closed Signal Enrichment Dry-Run Plan

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- stage: `N3-C2B closed_signal_enrichment business dry-run design`
- execute_authorized: `false`
- database_written: `false`
- enrichment_rows_written: `false`
- outbox_written: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`

This document designs the dry-run for C2B. It does not authorize business
execute.

## Run Identity

```text
c2b_run_id =
closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

Source lineage:

```text
source_condition_run_id =
condition_layer_20260522_to_20260525_20260525102249_execute

source_subscription_run_id =
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

c2_run_id =
closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_previous_day_minute_run_id =
previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

for_trade_date = 20260525
previous_day_minute_date = 20260522
```

## Inputs

C2B dry-run may only read:

```text
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
stock_minute_bar_1m previous-day preload rows
index_minute_bar_1m previous-day preload rows
board_minute_bar_1m previous-day preload rows
common_market_data_run source run metadata
common_market_data_quality_item source quality metadata
```

The dry-run must not read raw external market adapters, old system data, N4/N5
facts, user tables, or C3 outbox as a mutation target. C3 outbox may remain
pending and must not be consumed.

## Expected Rows

C2B enrichment rows must align one-to-one with C2 summary rows:

```text
stock = 16416
index = 72
board = 1016
total = 17504
```

C2 current summary status:

```text
closed = 17432
missing = 72
partial = 0
failed = 0
```

Initial dry-run estimate:

```text
computable_rows = 17432
unknown_or_missing_rows = 72
baseline_missing_rows_expected = 0 for non-BJ closed rows, subject to dry-run join proof
```

The dry-run runner must recompute those counts from the database and must not
silently trust the estimate.

## Calculation Contract

For each C2 summary row:

```text
current_window_amount = C2 summary amount
baseline_window_amount = previous-day same object same 30m bucket amount
closed_amount_ratio = current_window_amount / baseline_window_amount
closed_price_change_pct = current close / current open - 1
```

Price direction:

```text
abs(closed_price_change_pct) <= 0.0010 -> flat
closed_price_change_pct > 0.0010 -> up
closed_price_change_pct < -0.0010 -> down
missing open/close or open=0 -> unknown
```

Amount shape:

```text
closed_amount_ratio >= 1.20 -> volume_expanding
closed_amount_ratio <= 0.80 -> volume_shrinking
otherwise -> volume_flat
missing or zero baseline -> unknown
```

Closed market shape and closed signal status:

```text
up + volume_expanding -> up_volume_expanding
up + volume_flat -> up_volume_flat
up + volume_shrinking -> up_volume_shrinking
down + volume_expanding -> down_volume_expanding
down + volume_flat -> down_volume_flat
down + volume_shrinking -> down_volume_shrinking
flat + any valid amount shape -> flat
unknown current or baseline basis -> unknown
```

The same value is written to `closed_market_shape_status` and
`closed_signal_status` in v1. A future schema version may split those concepts
only with an explicit contract change.

## Baseline Contract

The baseline bucket is built from previous-day minute facts:

```text
run_id = source_previous_day_minute_run_id
trade_date = 20260522
is_previous_day_preload = true
same asset physical table
same identity_key
same bucket_id mapped onto previous-day bar_time labels
```

Baseline aggregation:

```text
baseline_window_amount = sum(previous-day amount)
baseline_minute_count = count(valid previous-day minute rows)
baseline_window_open = first previous-day open
baseline_window_close = last previous-day close
baseline_trace_json.baseline_minute_bar_ids = previous-day bar ids used
```

If the baseline bucket is missing, partial, has amount null, or has
`baseline_window_amount <= 0`, C2B still writes an enrichment row, but:

```text
closed_signal_status = unknown
closed_signal_quality_status = warning
```

N4 must not backfill or infer the missing signal from raw minute rows or B2
projection facts.

## Current Missing Policy

If the C2 summary row has:

```text
closed_status in ('missing', 'partial', 'failed')
or current open/close/amount is unavailable
```

C2B still writes an enrichment row with:

```text
closed_signal_status = unknown
closed_signal_quality_status = missing for missing current summary
closed_signal_quality_status = warning for partial current summary
closed_signal_quality_status = failed for failed current summary
```

BJ `920xxx` missing summaries remain explicit. C2B must not fabricate signal
values or minute rows.

## Dry-Run Output

The dry-run report must output:

```text
expected_rows
current_summary_rows
baseline_bucket_rows
computable_rows
unknown_rows
missing_rows
baseline_missing_rows
signal_distribution
price_direction_distribution
quality_distribution
P0/P1/P2
blockers
N4 replay unblock estimate
```

The N4 replay unblock estimate should show:

```text
closed_signal_status_missing before C2B = 35952
closed_signal_status_missing after successful C2B = estimated 0 for accepted C3 rows
c3_event_missing remains = 18
```

C2B only produces N3 standard enrichment facts. It does not replay N4, rewrite
C3 outbox, or consume any event.

## Future Execute Scope

Future C2B execute may write only:

```text
common_market_data_run
common_market_data_quality_item
stock_closed_30m_signal_enrichment
index_closed_30m_signal_enrichment
board_closed_30m_signal_enrichment
```

Forbidden:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
stock/index/board_closed_30m_summary
stock/index/board_minute_bar_1m
stock/index/board_realtime_projection_metric
stock/index/board_realtime_daily_snapshot
N4/N5/N6
worker
old system
```

## Decision

`DESIGN_PASS`.

Allowed next gate: `N3-C2B closed_signal_enrichment dry-run runner implementation`.
