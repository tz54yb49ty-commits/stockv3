# N3-C2 Closed 30m Summary Schema Readiness

## Summary

- result: `SCHEMA_READINESS_PASS`
- layer_role: `N3_market_data`
- generated_at: `2026-05-26T05:12:54+08:00`
- migration_path: `sql/016_market_closed_30m_summary_schema.sql`
- rollback_path: `sql/016_market_closed_30m_summary_rollback.sql`
- migration_execute_authorized: `false`
- c2_execute_authorized: `false`

## Current Lineage

- N2 active: `condition_layer_20260522_to_20260525_20260525102249_execute`
- N3 subscription: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- N3 C1 today minute run: `today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- N3 B2 projection run: `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`

## Existing Schema Check

- `stock_closed_30m_summary`: absent
- `index_closed_30m_summary`: absent
- `board_closed_30m_summary`: absent

The 016 draft is therefore strictly additive for these target tables.

## Designed Tables

The migration drafts three physical tables:

```text
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
```

Each table keeps the asset-specific identity column:

```text
stock_identity_key
index_identity_key
board_identity_key
```

and also stores `asset_kind` with an asset-specific CHECK constraint.

## Required Columns

Each table includes:

```text
summary_id
run_id
source_condition_run_id
source_subscription_run_id
source_today_minute_run_ids
for_trade_date
trade_date
asset_kind
asset-specific identity_key
exchange
code
display_code
name
bucket_id
bucket_start
bucket_end
expected_minute_count
actual_minute_count
missing_minute_count
open
high
low
close
volume
amount
closed_status
quality_status
source_minute_bar_ids
replay_diff_json
raw_json
created_at
updated_at
```

## Bucket Contract

Allowed `bucket_id` values:

```text
0931_1000
1001_1030
1031_1100
1101_1130
1301_1330
1331_1400
1401_1430
1431_1500
```

Each bucket defaults to `expected_minute_count=30`.

## Status Contract

`closed_status`:

```text
closed
partial
missing
failed
```

`quality_status`:

```text
pending
passed
warning
partial
missing
failed
blocked
```

Count constraints:

```text
actual_minute_count <= expected_minute_count
missing_minute_count <= expected_minute_count
closed_status=failed OR actual_minute_count + missing_minute_count = expected_minute_count
closed_status=closed -> actual=expected and missing=0
closed_status=missing -> actual=0
```

## Keys And Indexes

Unique key per physical table:

```text
run_id + identity_key + trade_date + bucket_id
```

Indexes:

```text
run_id
trade_date + bucket_id
identity_key + trade_date
closed_status
quality_status
```

## Strictly Additive Check

The schema draft contains only:

```text
CREATE TABLE IF NOT EXISTS
CREATE INDEX IF NOT EXISTS
```

It does not contain:

```text
ALTER
DROP
INSERT
UPDATE
DELETE
TRUNCATE
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
trigger/action/user/voice/mobile/sim/position tables
```

## Future C2 Execute Boundary

Future C2 execute may write only:

```text
common_market_data_run
common_market_data_quality_item
stock/index/board_minute_bar_1m delta rows
stock/index/board_closed_30m_summary
```

Future C2 execute remains forbidden from writing:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
stock/index/board_realtime_projection_metric
stock/index/board_realtime_daily_snapshot
B1/B2/N4/N5 existing runtime rows
condition / trigger / action / user / voice / mobile / sim / position
worker / long-running service
```

## Rollback

Schema rollback path:

```text
sql/016_market_closed_30m_summary_rollback.sql
```

The rollback refuses to drop any of the three tables if row_count is nonzero.
If C2 business rows exist, first run a business rollback scoped by `c2_run_id`,
then run the schema rollback.

## Readiness Decision

- P0 blockers: `0`
- P1 warnings: `0`
- P2 notes: `0`
- schema migration safe for review: `true`
- execute confirmation point allowed: `migration review only`

Next allowed step:

```text
N3-C2 016 migration review / execute confirmation point
```

This readiness report does not authorize migration execution and does not
authorize C2 business execute.
