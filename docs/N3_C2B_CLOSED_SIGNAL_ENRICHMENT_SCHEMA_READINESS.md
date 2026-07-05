# N3-C2B Closed Signal Enrichment Schema Readiness

## Summary

- result: `SCHEMA_READINESS_PASS`
- layer_role: `N3_market_data`
- stage: `N3-C2B closed_signal_enrichment schema readiness`
- migration path: `sql/017_market_closed_30m_signal_enrichment_schema.sql`
- rollback path: `sql/017_market_closed_30m_signal_enrichment_rollback.sql`
- migration executed: `false`
- database business rows written: `false`
- outbox consumed: `false`
- downstream replay entered: `false`
- worker started: `false`

## Reason

N4 C3 replay dry-run is correctly blocked because C2/C3 closed summary currently lacks standardized closed signal fields.

```text
comparison candidates = 35970
not_ready = 35952
reason = closed_signal_status_missing
```

N4 must not compute this from raw minute rows or B2 projection. N3 should publish a standard closed signal enrichment fact.

## Recommended Schema

Add three physical N3 fact tables:

```text
stock_closed_30m_signal_enrichment
index_closed_30m_signal_enrichment
board_closed_30m_signal_enrichment
```

The tables use `c2b_run_id + identity_key + trade_date + bucket_id` as the unique grain and reference the existing C2 summary row through `current_summary_id`.

Core fields:

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
```

Status enums align with N3-B2 projection:

```text
closed_price_direction_status:
  up / down / flat / unknown

closed_market_shape_status and closed_signal_status:
  up_volume_expanding
  up_volume_flat
  up_volume_shrinking
  down_volume_expanding
  down_volume_flat
  down_volume_shrinking
  flat
  unknown

closed_signal_quality_status:
  passed / warning / missing / failed / blocked
```

## Calculation Contract

Future C2B execute should use:

```text
current bucket = current C2 closed_30m_summary amount / open / close
baseline bucket = previous-day same 30m bucket amount
closed_price_direction_status = close vs open
closed_amount_ratio = current_window_amount / baseline_window_amount
```

Thresholds:

```text
amount expanding >= 1.20
amount shrinking <= 0.80
flat price threshold abs(close/open - 1) <= 0.0010
```

Missing BJ 920xxx or missing baseline must stay explicit:

```text
closed_signal_status = unknown
closed_signal_quality_status = missing or warning
do not fabricate signal
```

## Future Execute Boundary

Allowed future C2B execute writes:

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

## Strictly Additive Check

`sql/017_market_closed_30m_signal_enrichment_schema.sql` contains only:

```text
CREATE TABLE IF NOT EXISTS
CREATE INDEX IF NOT EXISTS
```

It does not alter old tables, write business rows, write outbox/inbox/checkpoint rows, or touch downstream layers.

## Rollback

Schema rollback is available only if all three enrichment tables are empty. If C2B business rows exist later, use a C2B business rollback by `c2b_run_id` before schema rollback.

## Decision

`SCHEMA_READINESS_PASS`.

Allowed next gate: `N3-C2B 017 migration review / execute confirmation point`.
