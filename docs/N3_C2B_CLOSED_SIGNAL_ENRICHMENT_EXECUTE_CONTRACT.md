# N3-C2B Closed Signal Enrichment Execute Contract

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- stage: `N3-C2B-closed-signal-enrichment-execute-contract`
- execute_authorized: `false`
- runner_exists: `true`
- runner_readiness: `ready`
- c2b_execute_allowed_now: `false`
- c2b_execute_allowed_reason: `awaiting_final_gate_user_confirmation`
- writes_outbox: `false`
- consumes_c3_outbox: `false`
- updates_c2_summary: `false`
- enters_n4_n5_n6: `false`

This contract defines what the C2B execute runner may do after dry-run,
preflight, rollback review, and explicit user confirmation. The runner exists
and is ready, but this document does not authorize execution.

## Run Identity

```text
c2b_run_id =
closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

The run id binds C2B to the current C2 replay run and current N3 subscription
lineage. It must not use stale or shortened lineage strings.

## Source Runs

Future execute must require all source runs to exist and be `passed`:

```text
source_condition_run_id =
condition_layer_20260522_to_20260525_20260525102249_execute

source_subscription_run_id =
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

c2_run_id =
closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_previous_day_minute_run_id =
previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

The C3 outbox run may remain pending and must not be consumed:

```text
c3_run_id =
minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

## Run Metadata Contract

`common_market_data_run` for C2B should use:

```text
for_trade_date = 20260525
source_trade_date = 20260522
prev_trade_date = 20260522
mode = execute
status = passed only after all rows and quality items commit
market_data_pulled = false
market_data_fact_written = true
downstream_layers_touched = false
worker_started = false
```

Previous-day provenance must also be recorded in `raw_json`, including:

```text
source_previous_day_minute_run_id
previous_day_minute_date
c2_run_id
c3_run_id
calculation_config_hash
```

## Execute Preconditions

Future execute runner must block with P0 if any condition fails:

```text
--execute flag missing
--user-confirmed flag missing
c2b_run_id already exists in common_market_data_run
c2b_run_id rows already exist in stock/index/board_closed_30m_signal_enrichment
c2b_run_id rows already exist in common_market_data_quality_item
common_event_outbox source_run_id=c2b_run_id count != 0
common_event_inbox source_run_id=c2b_run_id count != 0
common_event_consumer_checkpoint references c2b_run_id count != 0
source condition/subscription/A1/C2 runs are not passed or lineage mismatches
017 enrichment schema tables are missing
C2 summary rows do not equal 17504
previous-day preload fact rows are absent for all non-BJ closed objects
dry-run report missing or not reviewed
rollback SQL missing
```

Future execute must require double confirmation:

```text
--execute
--user-confirmed
```

## Allowed Writes

Future C2B execute may write only:

```text
common_market_data_run
common_market_data_quality_item
stock_closed_30m_signal_enrichment
index_closed_30m_signal_enrichment
board_closed_30m_signal_enrichment
```

## Forbidden Writes

Future C2B execute must not write or update:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
stock_realtime_projection_metric
index_realtime_projection_metric
board_realtime_projection_metric
stock_realtime_daily_snapshot
index_realtime_daily_snapshot
board_realtime_daily_snapshot
existing B1/B2/C2/C3/N4/N5 runtime rows
condition tables
trigger tables
action tables
user tables
voice/mobile/sim/position tables
external archive / Parquet
old system
worker / scheduler state
```

## Enrichment Row Contract

Expected enrichment rows:

```text
stock = 16416
index = 72
board = 1016
total = 17504
```

Each row must use the physical asset table and must preserve:

```text
c2b_run_id
c2_run_id
current_summary_id
source_condition_run_id
source_subscription_run_id
source_previous_day_minute_run_id
for_trade_date
trade_date
asset_kind
identity_key
exchange / code / display_code / name
bucket_id / bucket_start / bucket_end
```

Computed fields:

```text
current_window_amount
baseline_window_amount
closed_amount_ratio
closed_price_change_pct
closed_price_direction_status
closed_market_shape_status
closed_signal_status
closed_signal_quality_status
closed_signal_basis_json
baseline_trace_json
calculation_config_hash
raw_json
```

`closed_signal_basis_json` must include:

```text
price_flat_abs_threshold = 0.0010
amount_expanding_threshold = 1.20
amount_shrinking_threshold = 0.80
current_open
current_close
current_amount
baseline_amount
baseline_minute_count
current_summary_status
baseline_status
```

`baseline_trace_json` must include:

```text
source_previous_day_minute_run_id
previous_day_minute_date
baseline_bucket_id
baseline_bucket_start
baseline_bucket_end
baseline_minute_bar_ids
baseline_minute_count
baseline_amount
```

## Quality Strategy

Quality item contract:

```text
data_domain in common / stock / index / board
layer_scope = market_data_run
details.metric_scope = closed_signal_enrichment
gate_code prefix = n3_c2b_closed_signal_
```

P0 examples:

```text
lineage mismatch
source runs not passed
017 schema missing
expected enrichment row count mismatch
duplicate enrichment key
invalid status enum
missing baseline for all non-BJ closed rows
forbidden writes detected
outbox/inbox/checkpoint rows for c2b_run_id
N4/N5/N6 touched
```

P1 examples:

```text
BJ 920xxx current missing summaries remain unknown
individual closed row baseline missing or zero
current row written as unknown due incomplete current summary
```

P2 examples:

```text
signal distribution skew requiring manual review
baseline minute count warning that does not affect row integrity
```

## Rollback Strategy

Rollback is scoped by `c2b_run_id` and deletes only:

```text
stock_closed_30m_signal_enrichment
index_closed_30m_signal_enrichment
board_closed_30m_signal_enrichment
common_market_data_quality_item
common_market_data_run
```

Rollback must not touch:

```text
C2 closed summary
C2 delta minute rows
C3 outbox
B1/B2 runtime
N4/N5 runtime
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
```

If any downstream replay has already used C2B enrichment, N4/N5 replay
rollback must happen first under their own layer roles. C2B must not silently
remove evidence underneath a completed downstream replay.

## Decision

`DESIGN_PASS`.

Allowed next gate: `N3-C2B closed_signal_enrichment dry-run runner implementation`.
