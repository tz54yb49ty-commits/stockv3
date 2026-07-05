# N3 Action-Confirmation Projection Facts Preflight Draft

Status: DRAFT_PASS

Generated at: 2026-06-02

Layer role: N3_market_data

This preflight draft defines the future dry-run / execute gate for N3 action-confirmation projection facts. It is documentation only and performs no database write.

## Candidate Run Id

Future run ids should be explicit and lineage-bound:

```text
action_confirmation_projection_metric_{for_trade_date}_{minute_label}__{source_snapshot_run_id}
```

Example:

```text
action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_...
```

## Required Inputs

Future dry-run/preflight must read only:

```text
common_market_data_run
common_market_data_subscription
common_market_data_pull_plan
stock/index/board_realtime_daily_snapshot
stock/index/board_minute_bar_1m
previous-day stock/index/board_minute_bar_1m rows scoped by source_previous_day_minute_run_id
common_event_outbox only for source_snapshot_event_id trace
```

Required source runs:

```text
source subscription run: passed
source snapshot run: passed
source today minute run: passed
source previous-day minute preload run: passed
```

## Baseline Guard

Future execute must block unless scoped baseline is zero:

```text
common_market_data_run.run_id = projection_run_id -> 0
common_market_data_quality_item.run_id = projection_run_id -> 0
stock_action_confirmation_projection_metric.projection_run_id -> 0
index_action_confirmation_projection_metric.projection_run_id -> 0
board_action_confirmation_projection_metric.projection_run_id -> 0
common_event_outbox.source_run_id = projection_run_id -> 0
common_event_inbox.source_run_id = projection_run_id -> 0
common_event_consumer_checkpoint references projection_run_id -> 0
```

## Calculation Readiness

Each metric candidate must produce:

```text
current_price / current_price_source / current_price_time
previous 1m / 5m / 30m / 120m body high/low
current_1m_amount / previous_1m_amount unless first 1m
current_5m_virtual_amount / previous_5m_full_amount unless first 5m
first-period boundary flags and previous-period source fields
source_fact_ids / source_minute_refs / previous_day_minute_refs
metric_quality_status / metric_ready
```

Metric readiness rules:

```text
metric_ready=true only when every required numeric field, boundary source, and trace field is present.
metric_ready=true must satisfy the DB hard guard for non-empty source_fact_ids and source_minute_refs.
metric_ready=true must have non-empty previous_day_minute_refs when any previous_*_period_source uses previous_trade_date_last_period.
metric_ready=false when previous period body high/low is missing.
metric_ready=false when amount comparison field is missing outside first 1m/5m.
metric_ready=false when previous_*_period_source=not_available.
metric_ready=false when source refs are untraceable.
```

Trace refs strategy:

```text
mode=db_hard_guard_plus_preflight_p0
preflight blocks P0 for trace incompleteness before execute
schema CHECK hard-fails any metric_ready=true row that lacks required trace refs
```

First-period rules:

```text
first 1m: first_1m_amount_default_pass=true, previous_1m_period_source=previous_trade_date_last_period
first 5m: first_5m_amount_default_pass=true, previous_5m_period_source=previous_trade_date_last_period
first 30m: previous_30m_period_source=previous_trade_date_last_period
first 120m: previous_120m_period_source=previous_trade_date_last_period
```

Non-first-period rules:

```text
previous_*_period_source=same_trade_date_previous_period
first_1m_amount_default_pass=false
first_5m_amount_default_pass=false
```

## Future Execute Write Scope

Allowed writes:

```text
common_market_data_run
common_market_data_quality_item
stock_action_confirmation_projection_metric
index_action_confirmation_projection_metric
board_action_confirmation_projection_metric
```

Forbidden writes:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
stock/index/board_realtime_daily_snapshot
stock/index/board_minute_bar_1m
stock/index/board_realtime_projection_metric
stock/index/board_closed_30m_summary
stock/index/board_closed_30m_signal_enrichment
N4/N5/N6 tables
worker state
old system
real trade
```

## Quality Gates

Expected P0 gates:

```text
n3_action_confirmation_schema_tables_exist
n3_action_confirmation_source_runs_passed
n3_action_confirmation_projection_run_id_absent
n3_action_confirmation_scoped_event_refs_zero
n3_action_confirmation_metric_ready_has_required_fields
n3_action_confirmation_first_period_boundary_consistent
n3_action_confirmation_trace_refs_complete
n3_action_confirmation_physical_table_isolation
n3_action_confirmation_no_outbox
n3_action_confirmation_no_n4_n5_n6_writes
```

Expected P1 gates:

```text
n3_action_confirmation_metric_not_ready_count
n3_action_confirmation_missing_previous_period_samples
n3_action_confirmation_source_time_warning_samples
```

Expected output summaries:

```text
candidate rows by asset_kind
metric_ready / metric_not_ready distribution
metric_quality_status distribution
first-period boundary counts
current_price_source distribution
previous_*_period_source distribution
trace completeness summary
N4/N5 unblock estimate
rollback safety
```

## N4 / N5 Boundary

N4 may consume only metric identifiers and standard numeric fields:

```text
source_action_confirmation_metric_id
projection_run_id
projection_schema_version
metric_quality_status
metric_ready
current_price and previous body/amount fields
```

N4 must not read raw minute rows to repair missing metrics.

N5 may evaluate final action confirmation using these N3 facts plus `TriggerMatched`. N5 must not trust opaque `payload.action_confirmation` as proof and must not reconstruct the 1m / 5m / 30m / 120m indicators itself.

## Rollback

Business rollback is:

```text
sql/N3_action_confirmation_projection_metric_business_rollback.sql
```

It deletes only metric rows, scoped quality rows, and the N3 run row by `projection_run_id`, and blocks if outbox/inbox/checkpoint refs exist.

The rollback SQL must hard-fail with `DO $$ ... RAISE EXCEPTION ... $$` before DELETE when scoped outbox / inbox / checkpoint refs are nonzero.
